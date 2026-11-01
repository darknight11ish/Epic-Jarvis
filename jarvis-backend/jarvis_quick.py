"""jarvis_quick.py - timers, alarms, reminders and the to-do list, answered
WITHOUT the AI model.

NEW MODULE, shipped whole. schedule.patch calls answer_turn() in /api/chat
before a turn can reach the model.

THE OWNER'S DECISION (2026-09-25): simple commands like timers are answered
without the model, so they keep working when the model is slow, unloaded or
asleep. A sentence that fits the small fixed grammar below is acted on here,
answered in one short sentence, and the model is never called. Anything that
does not fit - or fits but is unclear - goes to the model exactly as before.
It is a GRAMMAR, not a guess: every pattern must match the WHOLE sentence
(after "please", "Jarvis," and the like are taken off), so "how long does it
take to boil an egg" or "remind me who wrote Dune" never land here.

LANGUAGES: English only. A sentence in any other language goes to the model,
which may still set a timer through its tools (jarvis_agent.py).

THE MORNING BRIEFING (briefing.patch, 2026-09-25) is here too: "brief me
now" (put together by jarvis_briefing.py, no model; the answer is private,
and marks the calendar as read when it quotes it), "brief me every weekday
at 7" (the scheduler's ONE card), "stop my briefing" (one, at once) and
"when is my briefing".

WEB SEARCH (2026-09-25) is here too, but only talk ABOUT it - nothing is
searched: "which search should I use?", "why SearXNG?", "why Exa?" are
answered from jarvis_search.py's own "why use this one" lines
(the words both apps' Settings show), and "use DuckDuckGo for web search" /
"switch web search to Exa" changes the provider at once, as a tap in
either app's Settings does. Only the owner's own words, like everything here.

FOCUS SESSIONS (2026-09-25, jarvis_focus.py) are here too: "focus for 30
minutes (on the essay)", "lock on this", "snooze", "I'm doing research",
"I need a minute", "pause / resume / stop focus", "extend by 10 minutes",
"how am I doing?", "call me out every 30 seconds". The short ones ("pause",
"snooze", "lock on this", "how am I doing?") are only ours WHILE a session
runs - the one place this grammar reads anything: jarvis_focus.is_on(), a
flag in memory. Otherwise they go on to the rest of the grammar, then the
model, as before.

"WHAT CAN YOU REACH?" (the Muse audit, 2026-09-25) is here too: "what can
you reach?", "what can Jarvis access?", "what do you have access to?" and
close phrasings are answered from jarvis_reach.py's list - the one both
apps show under "What Jarvis can reach", built from the PC's settings - so
the model never describes its own access. Reads only; host names, never an
account name, a key or a link.

SNOOZE, "CANCEL THAT", NAMED LISTS AND "WHAT DID I MISS?" (2026-09-25, the
creativity audit's everyday quick wins - docs/CREATIVITY-AUDIT-2026-09-25.md
items 6 and 7):
  * "snooze", "snooze 10 minutes", "remind me again in 5 minutes": the
    timer, alarm or reminder that went off most recently (in the last hour)
    goes off again after that long (10 minutes when not said). A one-off
    copy (jarvis_schedule.Scheduler.snooze): a repeating one keeps its
    usual times. No card.
  * "cancel that", "never mind", "delete that reminder", "undo": takes back
    the LAST thing this fast path set IN THIS CONVERSATION (the request's
    conversation_id), within two minutes, once - and says what it was. It
    never cancels anything else: nothing the model's tools set, nothing
    from another conversation, nothing older. With nothing to take back,
    "never mind" goes to the model as before.
  * Named lists: "add milk to the shopping list" (with commas, several
    items: "add milk, eggs and bread to the shopping list"), "what's on my
    shopping list", "remove milk from the shopping list", "cross milk off
    the shopping list", "what lists do I have". "Clear the shopping list"
    changes nothing and points to the app, where clearing a whole list asks
    "are you sure?" first.
  * "What did I miss?": jarvis_briefing.build_missed - since the owner's
    previous message to Jarvis from either app (answer_turn notes the time
    of every one, jarvis_briefing.touch).
"WHAT CAN YOU DO?" (jarvis_sayable.py; the ease-of-use audit's "Things you
can say", 2026-09-27, feasibility I116) is here too: "what can you do?",
"what can I say?", "what can I ask you?" and close phrasings are answered
from jarvis_sayable.py's own fixed list - the same one both apps show in
place of the Jarvis bar's old shortcut rows. No model, no state read.

"FROM NOW ON ..." (jarvis_manner.py, 2026-09-27) is here too: "from now on,
be more plain", "from now on be warmer" and close phrasings change the
manner setting at once - no card either way, like a tap in Settings - and
say "Done: ... . You can undo this in Settings." A temporary chat's change
stays in that chat only, in memory, never in manner.json. A tail that does
not map to the one real dial (warm/plain) says so plainly rather than
pretending to change something that does not exist yet.

"TELL ME WHEN ..." (jarvis_tellme.py, 2026-09-25) is here too: "tell me
when an email from Alex arrives", "let me know when the washing machine
finishes", "urgently tell me when the front door opens", "tell me every
time Sam emails me", "... for the next 2 hours" / "... today". Each is ONE
approval card raised by the scheduler; nothing is watched before a yes. A
device said in words is looked up first - one read of each of up to three
likely Home Assistant names (switch.washing_machine, ...), through the
gate like any read - and the answer then counts as having read outside
text. The model has no tool for this. Since 2026-09-28 (the "Watches"
group): "tell me when a search for X shows something new" (", once a day"
/ "every 12 hours"), "tell me when the price on <url> drops below 25",
"tell me when CI fails / finishes on owner/repo [branch]" and "tell me when
PR #12 on owner/repo merges" - each ONE card too (_tellme_watches).

"REMIND ME NEXT TIME I TALK ABOUT ..." (jarvis_next_time.py, 2026-09-28):
"remind me next time I talk about the dentist to ask about the bill", "next
time I mention Sam, remind me to ask about the loan", "remind me to ask
about the bill next time I talk about the dentist". No card, like a one-time
reminder; "cancel that" takes it back, as for any reminder set here.
"Delete the reminder about the dentist" deletes ONE; "what will you remind
me of next time?" lists them. It is brought up by jarvis_agent.py, not here.

TODAY CARDS (jarvis_today.py, 2026-09-28): "show gym bag on my Today page
on Mondays and Wednesdays at 7", "put bins out on my today page on Thursday
evenings", "add a today card saying water the plants every day at 8". The
owner's own words, shown on the Today part of both apps from that time to
the end of the day, on those days. No card, like a plain repeating reminder;
"cancel that" takes it back. "What's on my Today page?" lists them;
"remove gym bag from my Today page" deletes ONE.

"RING MY PHONE" (jarvis_find_phone.py, 2026-09-28): "ring my phone", "find
my phone", "where's my phone" - ONE event the phone rings for, on its alarm
channel, even on silent. No card: it only rings the owner's own phone.
"Stop ringing my phone" stops it from the PC.

"PC HELP" (jarvis_pc_help.py, 2026-09-28): "why is my PC slow?", "how full
is my disk?", "what's using my graphics card?", "how hot is my graphics
card?", "when did my PC last restart?" - read on this PC, answered at once.
Read-only: no card, nothing changes. An answer that names programs is
private and marked as outside text (a program picks its own name).

"WATCH WITH ME" (jarvis_screen.py, 2026-09-29): "watch with me", "watch with
me for 20 minutes", "start watching my screen" - a session the owner starts,
30 minutes by default, 2 hours at most, with a sign on screen the whole time.
No card: the owner's own act, like a focus session. "Stop watching" ends it;
"watch 20 more minutes" extends it; "are you watching?" says whether it is
on. Only from this PC (it is this PC's screen). "Look at this" is not here:
it is a key and a button, and the model answers what is asked about it.

LOCKDOWN (jarvis_asks_first.py, 2026-09-28): "lockdown", "turn on lockdown",
"lock everything down" - every way out of this PC asks first, or stops, at
once. "Turn off lockdown" goes through the same path as the apps' button:
from the PC, ONE approval card plus Windows Hello; from anywhere else it
says where to do it. "Is lockdown on?" says whether it is.

A NUMBER FOR A PROJECT (jarvis_projects.py, 2026-09-28, Projects build
step 2) is here too: "log 5 km run", "log my weight as 72.5 kg", "I ran 5
km", "I walked 10,000 steps today", "my weight is 72 kg" - but ONLY when
one of the owner's life projects has a benchmark it fits (the name's
words and the unit; 5 km is never logged as miles). With no such
benchmark the sentence is not ours and goes to the model as before;
projects.db is read only after the sentence already has that shape, and
never created by it. No card: the owner is writing down their own
number. A health or money benchmark's answer is `private`, so the apps
keep it on screen and never read it aloud.

"FORGET A TIME FRAME" (jarvis_forget_range.py, the owner's decision of
2026-09-28) is here too: "forget what you learned last week", "delete my
chats from 1 to 15 September", "forget what I said this morning". It
REMOVES NOTHING: it fills in the checked list in both apps' Brain (under
"Forget a time frame"), says how many facts and chats are on it, and puts
`open_brain: "forget-range"` in X-Jarvis-Route so the app it was asked from
opens that place. The owner unticks, taps Forget these, and approves ONE
card by tapping - a spoken "yes" or "approve" matches nothing here and
approves nothing. A date it cannot be sure of ("on Monday" said on a
Monday, "3/9", "the 3rd", "last night", a month that has not happened yet
this year) is a question instead, and opens nothing.

"LABEL THIS CHAT" (chat tags, the owner's decision of 2026-09-30, JARVIS-API
section 99) is here too: "label this chat Work", "file this under Learning",
"tag this as Ideas", "remove the tag from this chat". It files the request's
own conversation at once, no card - it is the owner's own organisation and
nothing leaves the PC. Only from the owner's newest typed or spoken words and
never in a conversation that has read outside text. A tag that does not exist
is answered with the tags that do (tags are made in History, never by voice).
An OLDER chat ("label my chat about the boiler as Home") is never guessed at:
the answer sets `open_brain: "history"`, `file_under: <tag id>` and
`history_q: <search words>` in X-Jarvis-Route, History shows the matches, and
nothing is filed until the owner taps one.

"TOPIC CONTROLS" (the owner's decision of 2026-09-30, JARVIS-API section 107) are
here too: "stop using my work topic" (Learn, but don't use), "don't learn about
money" (Use, but don't learn), "use my health topic again", and the ambiguous
"switch off / pause / hide my work topic", which OPENS the four-choice picker
(`open_brain: "topics"` and `topic_id` in X-Jarvis-Route) and changes nothing
until the owner taps. A clear phrase that makes a topic STRICTER applies at
once; a looser one goes through the exact function the picker calls, so a
private topic still raises its one card. Only the owner's newest typed or said
words, and never in a conversation that has read outside text. A name that is
not one of the owner's topics is answered with the topics that exist (with the
word "topic" in the sentence) or left to the model (without it).

WHERE THE IDEA COMES FROM
Home Assistant's `prefer_local_intents` - try the built-in sentence matcher
before the conversation agent - and the set of timer handlers in its
`homeassistant/components/intent/timers.py` (start, cancel, add time, take
time off, pause, resume, how long left). Home Assistant is Apache-2.0; the
design is borrowed, no code is copied (its source was not in reach when this
was written, so nothing could be).

WHAT MAY ACT
Only the owner's own words: the newest message tagged `typed` or `voice`
(ARCHITECTURE section 3 - "only typed and voice are the owner's own words").
A pasted, shared or clipboard message, one sent with an app's own system
text, a picture, or an untagged message goes to the model instead. A voice
turn started by "Hey Jarvis" is fine: setting a reminder is an action the
owner asked for, not a fact being saved. Since 2026-09-26 that includes a
REPEATING alarm or reminder ("remind me every weekday at 7 to take my
pills"): it is set up at once, with no card, and the answer says its next
three times (jarvis_schedule.repeat_set_words). A repeating briefing and
"tell me when" still raise their one card.

WHAT IT KEEPS
A reminder's words are the owner's own: they go into jarvis_schedule's file
on this PC and nowhere else. They are not learned as a fact
(jarvis_intake.owner_turns skips a sentence this grammar matches, and one the
scheduler marked as a command), and nothing here sends anything anywhere.
In a temporary chat a reminder still works - it is an action, not memory -
and the chat itself is not kept, as usual.

THE "DONE" ACKNOWLEDGEMENT
The reply is one short sentence, sent in the same format a model's answer is
sent in, with `quick` in X-Jarvis-Route. Both apps show a small "Done" line
under such an answer ("Done - answered on this PC without the AI model").

VOICE REFLEX AND THE SPOKEN-COMMAND NORMALISER (2026-10-21, the Live/Voice
audit's V4, revised by the wave's section 10.4). `normalize_spoken_command`
runs BEFORE the grammar: it strips a documented list of polite lead-ins that
`normalise` did not, and rewrites a number word into digits only where a
whole-sentence grammar demands digits (a number before a length of time, "N
more minutes", "N times a day", and the hour after "at"). Nothing else is
rewritten - "one of the files" stays as it is - and it only decides which
PATTERN matches: the model still gets the owner's original words whenever no
pattern matches. One deterministic reflex (no model, no card of its own) was
added, a router into an action that already existed:
  * "speak faster" / "speak slower" / "speak normally" call the SAME
    `jarvis_voices.set_speed` that POST /api/voice/voices/speed calls (a
    cosmetic setting with NO card, set from either app).
The SELECTION and SCREEN reads are NOT in this file: PR #691 shipped them for
Live turns through the same primitives (`jarvis_voice_ui.py`), and a 0-ms
copy here would intercept those phrases before that path could answer. The
slice dropped its own read reflex when #691 merged, and `test_voice_reflex.py`
holds this file to NOT matching them. It also holds the commands this slice
did NOT build (HUD layout, bar pinning, "open galaxy/today", mute/unmute,
"repeat that", scroll/back/home) to returning None with the reason: no honest
backend action exists for them today.

A NOTION EXPORT INTO OBSIDIAN (2026-10-28, the owner's screenshot of
2026-10-27 205732). "can you process all of my notion notes into obsidian?"
reached the model, which answered "I cannot directly access or process files
from Notion to transfer them to Obsidian" - false, twice: this PC has
`jarvis_documents.import_notion` (unzip a Notion export into a NEW folder in a
listed folder; PC only; no card, because that folder was approved when it was
listed) and `jarvis_notion_obsidian.py` (the export tidied into an Obsidian
vault, `/api/notion/import`; PC only; ONE card). The model can drive neither:
it is offered no Notion tool, and the guide it may ask mentions the folder
import only inside the `folders` row (asking it for "notion export" answers
"I do not have a feature called ...") and has no row at all for the converter.
So it answered the only way it could. This file now answers instead, from the
real steps and the real limits: the export itself is made in Notion, the import
unpacks into a NEW folder and edits nothing on Notion's side, and the vault
converter is built but has no button in either app yet - so the answer says
that rather than promising either half is automatic. It reads nothing, changes
nothing, opens no card, and is in READ_ONLY_INTENTS.

CONNECTING AN ACCOUNT BY TALKING (2026-10-28). "connect my calendar", "set up
github", "is my calendar connected?" - the owner's ask, and the answer to the
refusal that made it worth asking for: the HUD had told him "jarvis cannot
connect directly to external calendars ... Would you like instructions on
exporting your calendar to ICS?", which was false about Jarvis. This file now
raises ONE card (`jarvis_connect_account.py`, drawn by the HUD) whose boxes are
typed on this PC and saved straight into Windows Credential Manager, then runs
one real test and says exactly what it proved; a question about state is
answered from the store and that same test. No value is ever in this file's
sentence, in the chat, in the model's context or in a log - the card is the
only place a value is typed, and the page posts it to a host-only route. It
runs BEFORE the Settings-only refusal, because the card is the same act
Settings performs, and it supersedes that sentence for the calendar and GitHub
only (the rest still get it, unchanged).

WHAT PARKING COSTS (2026-10-30). "find cheap parking near Pike Place Market
tomorrow from 4:15 PM to 9:00 PM", "where is free parking near X at 5 pm for 2
hours", "cheapest parking at X tomorrow from 4 to 9", "how much is parking near
X from 4 to 6 pm" and "find cheap parking for my next meeting [at X]" are
answered here, from `jarvis_parking.py`'s minute-by-minute pricing. No model,
no tool slot, no card: it reads two public parking services and this PC's own
calendar, and changes nothing (both intents are in READ_ONLY_INTENTS). The
answer is written twice - the PC's screen gets every legal option with its
maths, a phone gets two options and a `geo:` link - and `client_surface=`
chooses when the caller knows; see `_client_surface` for why the header is NOT
what decides it here. The calendar bridge reads the next event that HAS a
place, and deliberately does not send that event's own words to a map service:
it quotes the venue back with the padded window and the sentence to say, and
"parking near <the venue>" then looks it up from the owner's own words. A place
is only taken when it follows a locative word, so "what is a parking minimum"
stays the model's.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

#: How an answer that raised a card ends. A "yes" said aloud approves
#: nothing - only the card does - so it names the card (creativity audit,
#: 2026-09-25: the old ending, "...until you say" + " yes", invited a
#: spoken yes that did nothing).
#: The same words as jarvis_card_words.UNTIL_APPROVED; test_card_words.py
#: holds them together.
UNTIL_APPROVED = "Nothing is set up until you approve the card."

LANGUAGES = ("English",)

#: The words both apps show under an answer made here.
DONE_LINE = "Done - answered on this PC without the AI model."

#: X-Jarvis-Route's `lane` for an answer made here. The badge still says
#: Local: it was made on this PC.
LANE = "no AI model"

# --------------------------------------------------------------------------
#   Tidying a sentence
# --------------------------------------------------------------------------

_LEAD = re.compile(
    r"^(?:(?:hey|hi|ok|okay)\s+jarvis\b[\s,]*|jarvis\b[\s,]*|please\s+|"
    r"(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need)\s+you\s+to\s+|"
    r"i'?d\s+like\s+you\s+to\s+)+")
_TAIL = re.compile(r"(?:[\s,]+(?:please|thanks|thank\s+you|jarvis|for\s+me))+$")


def normalise(text) -> str:
    t = str(text or "")
    t = t.replace("’", "'").replace("‘", "'").replace("–", "-")
    t = t.lower().strip()
    t = re.sub(r"\ba\.\s?m\.?", "am", t)
    t = re.sub(r"\bp\.\s?m\.?", "pm", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[\s.!?]+$", "", t)
    t = _LEAD.sub("", t).strip()
    t = _TAIL.sub("", t).strip()
    t = re.sub(r"[\s.!?,]+$", "", t)
    # "to-do", "to do", "todo" - only where it names the list, never in
    # "remind me to do the laundry".
    t = re.sub(r"\b(my|the)\s+to-?\s?dos?\b", r"\1 todo", t)
    t = re.sub(r"\bto-?\s?do\s+list\b", "todo list", t)
    return t


# --------------------------------------------------------------------------
#   The spoken-command normaliser (2026-10-21, Live/Voice audit V4)
# --------------------------------------------------------------------------
#
# WHY THIS EXISTS. `normalise` already strips "hey jarvis", "jarvis",
# "please", "can/could/would you"; `parse_duration` already reads number words
# inside a length of time ("twenty five minutes", "a couple of minutes",
# "an hour and a half"). Measured on the tree before this change (the probe is
# in the PR body, and every line below is a test in test_voice_reflex.py):
# those duration forms ALREADY hit the fast path, so rewriting them would be
# change for change's sake. What genuinely fell through to the model was:
#   * polite lead-ins `normalise` does not know ("would you mind ...",
#     "can you kindly ...", "i would like you to ...", "do you think you
#     could ...", "would it be possible to ...", "i was wondering if you
#     could ..."),
#   * number words in the three whole-sentence grammars that demand digits:
#     "watch FIVE more minutes" (`_WATCH_MORE_N`), "speak up THREE times a
#     day" (`_BUDGET_PER_DAY`) and "the brief arrives at EIGHT"
#     (`_BRIEF_AT`).
#
# THE SAFE NUMBER RULE, stated once and tested: a number word (one..ninety
# nine) becomes digits ONLY when the number is followed by (a) a length-of-
# time word, directly or after "more"; (b) "time(s) a/per day"; or (c) the
# number stands directly after "at" and ends the sentence or is followed by
# am/pm/"in the morning|afternoon|evening"/"at night". Everything else is
# left alone - "one of the files", "the one with the error", "call me three
# times", "a couple of minutes", "half an hour", "an hour and a half" and
# "twenty five" on its own all come out unchanged.
#
# IT ONLY DECIDES A MATCH. The grammar is tried on this string; a sentence
# this does not match still goes to the model with the OWNER'S ORIGINAL
# WORDS (`answer()` passes `text`, never this string), so a rewrite can never
# change what the model is asked.

#: Lead-ins `normalise` does not strip. Longest first: "would you mind " must
#: be tried before "mind ", and "i would like you to " before any shorter
#: tail of it.
_EXTRA_LEADS = (
    "would you be so kind as to ",
    "i was wondering if you could ",
    "i was wondering if you can ",
    "would it be possible to ",
    "do you think you could ",
    "do you think you can ",
    "i would like you to ",
    "i would love you to ",
    "any chance you could ",
    "any chance you can ",
    "could you possibly ",
    "can you possibly ",
    "possibly ",
    "be so kind as to ",
    "if you don't mind ",
    "would you mind ",
    "can you ",
    "could you ",
    "would you ",
    "will you ",
    "please ",
    "kindly ",
    "just ",
    "mind ",
)

#: "would you mind SETTING a timer" - a polite lead is followed by a gerund,
#: and the grammars below are written for the plain verb. Only the first word
#: of a sentence whose lead was stripped is ever changed, and only for the
#: verbs the fast path already acts on.
_GERUND_VERB = {
    "setting": "set", "opening": "open", "starting": "start", "stopping": "stop",
    "making": "make", "adding": "add", "cancelling": "cancel", "canceling": "cancel",
    "pausing": "pause", "resuming": "resume", "reminding": "remind", "turning": "turn",
    "reading": "read", "switching": "switch", "playing": "play", "hiding": "hide",
    "speaking": "speak", "talking": "talk", "showing": "show", "changing": "change", "pinning": "pin", "muting": "mute",
    "unmuting": "unmute", "repeating": "repeat", "scrolling": "scroll",
}

#: The words a number may be followed by, for rule (a): the same lengths of
#: time `_UNIT_S` below knows (written out here because this block runs first
#: in the file), plus the calendar words a sentence may use.
_TIME_UNITS = frozenset((
    "h", "hr", "hrs", "hour", "hours",
    "m", "min", "mins", "minute", "minutes",
    "s", "sec", "secs", "second", "seconds",
    "day", "days", "week", "weeks", "month", "months"))


def _bare_token(tok: str) -> tuple:
    """(the lower-case word, the punctuation after it) of one token."""
    m = re.fullmatch(r"([a-z]+)([^a-z]*)", tok)
    if not m:
        return "", tok
    return m.group(1), m.group(2)


def _spoken_numbers(s: str) -> str:
    """Number words to digits, only in the three safe positions above."""
    # "twenty-five" is one number said as one hyphenated word: split it, then
    # the token walk below sees "twenty" + "five" (the same two tokens
    # parse_duration's own tokeniser produces).
    s = re.sub(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)-"
               r"(one|two|three|four|five|six|seven|eight|nine)\b", r"\1 \2", s)
    toks = s.split(" ")
    bare = [_bare_token(t) for t in toks]
    out = []
    i, n = 0, len(toks)
    while i < n:
        word = bare[i][0]
        value, j = None, i
        if word in _TENS:
            value, j = float(_TENS[word]), i + 1
            if j < n and bare[j][0] in _UNITS and 0 < _UNITS[bare[j][0]] < 10:
                value += _UNITS[bare[j][0]]
                j += 1
        elif word in _UNITS and _UNITS[word] > 0:
            value, j = float(_UNITS[word]), i + 1
        if value is None:
            out.append(toks[i])
            i += 1
            continue
        nxt = bare[j][0] if j < n else ""
        nxt2 = bare[j + 1][0] if j + 1 < n else ""
        nxt3 = bare[j + 2][0] if j + 2 < n else ""
        prev = bare[i - 1][0] if i > 0 else ""
        rewrite = (
            nxt in _TIME_UNITS
            or (nxt == "more" and nxt2 in _TIME_UNITS)
            or (nxt in ("time", "times") and nxt2 in ("a", "per") and nxt3 == "day")
        )
        if not rewrite and prev == "at":
            rewrite = (
                j >= n
                or nxt in ("am", "pm")
                or (nxt == "in" and nxt2 == "the"
                    and nxt3 in ("morning", "afternoon", "evening"))
                or (nxt == "at" and nxt2 == "night")
            )
        if rewrite:
            # Keep the punctuation the number word carried ("at eight." ->
            # "at 8."), and drop the words it was written as.
            out.append(str(int(value)) + bare[j - 1][1])
            i = j
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def normalize_spoken_command(text) -> str:
    """`text` tidied for the grammar: `normalise`'s own tidying, the polite
    lead-ins `normalise` does not strip, and the three safe number rewrites
    above. Idempotent (test_voice_reflex.py runs it twice on every sentence
    it tests), and it NEVER changes which words the model is asked."""
    t = normalise(text)
    stripped = False
    changed = True
    while changed:
        changed = False
        for lead in _EXTRA_LEADS:
            if t.startswith(lead):
                t = normalise(t[len(lead):])
                stripped = True
                changed = True
                break
    if stripped and t:
        first, _sep, rest = t.partition(" ")
        if first in _GERUND_VERB:
            t = _GERUND_VERB[first] + (" " + rest if rest else "")
    return _spoken_numbers(t)


# --------------------------------------------------------------------------
#   The one voice reflex this slice adds (2026-10-21, Live/Voice audit V4)
# --------------------------------------------------------------------------
#
# A ROUTER into an action that already exists, with its own permission model:
# it raises no card and cannot bypass `jarvis_gate` - there is nothing to
# approve. The commands this slice did NOT build are listed in
# `docs/JARVIS-API.md` section 154 with the evidence.
#
# THE SELECTION/SCREEN READS ARE NOT HERE, DELIBERATELY (2026-10-21). PR #691
# shipped "what's on my screen" / "read this selection" / "summarise what I
# selected" for Live turns, through the SAME `jarvis_screen`/`read_selection`
# primitives (`jarvis_voice_ui.py`, the audit's V7 read half). A second, 0-ms
# copy in this fast path would intercept those phrases before the Live path
# could answer them - two implementations of one feature, and the fast one
# would win even inside Live. So this file does not match them, and
# `test_voice_reflex.py` holds it to that (the slice's own read reflex was
# dropped when #691 merged; see section 154.3 of docs/JARVIS-API.md).

VOICES_MISSING = ("This PC's Jarvis cannot change the speaking speed yet - run "
                  "apply-patches.ps1 on the PC.")

_VOICE_SPEED = re.compile(
    r"(?:speak|talk)\s+(?:a\s+(?:bit|little)\s+)?"
    r"(?P<way>faster|more\s+quickly|slower|more\s+slowly|normally|normal)")
_VOICE_SPEED_AT_NORMAL = re.compile(
    r"(?:speak|talk)\s+at\s+(?:the\s+)?normal\s+speed")
#: "make the voice faster", "make Jarvis speak faster" (2026-10-26). The same
#: setting the reflex above changes - a wording, not a second path - added
#: because the owner's most natural sentence ("make the voice faster") missed
#: the "speak faster" form and went to the model, which has no voice control.
_VOICE_SPEED_MAKE = re.compile(
    r"(?:make|get)\s+(?:the\s+|your\s+)?(?:voice|speaking|speech)\s+"
    r"(?:a\s+(?:bit|little)\s+)?"
    r"(?P<way>faster|more\s+quickly|slower|more\s+slowly)"
    r"|(?:make|get)\s+(?:jarvis|it)\s+(?:to\s+)?(?:speak|talk)\s+"
    r"(?:a\s+(?:bit|little)\s+)?"
    r"(?P<way2>faster|more\s+quickly|slower|more\s+slowly)")
_SPEED_WAY = {"faster": "faster", "more quickly": "faster",
              "slower": "slower", "more slowly": "slower",
              "normally": "normal", "normal": "normal"}


def _voice_speed(s: str) -> Optional[Intent]:
    m = _VOICE_SPEED.fullmatch(s)
    if m:
        return Intent("voice_speed", {"speed": _SPEED_WAY[m.group("way")]})
    if _VOICE_SPEED_AT_NORMAL.fullmatch(s):
        return Intent("voice_speed", {"speed": "normal"})
    m = _VOICE_SPEED_MAKE.fullmatch(s)
    if m:
        way = m.group("way") or m.group("way2") or ""
        if way in _SPEED_WAY:
            return Intent("voice_speed", {"speed": _SPEED_WAY[way]})
    return None


def _run_voice_speed(intent: Intent) -> Result:
    """The SAME action as POST /api/voice/voices/speed (jarvis_voices.
    set_speed): a cosmetic setting, no card either way, its own words."""
    n = intent.name
    choice = intent.f.get("speed")
    try:
        import jarvis_voices as V
    except Exception:
        return Result(VOICES_MISSING, n)
    try:
        code, out = V.set_speed({"speed": choice})
    except Exception as exc:                                   # noqa: BLE001
        return Result(f"The speaking speed could not be changed ({type(exc).__name__}).", n)
    out = out if isinstance(out, dict) else {}
    if code != 200 or not out.get("ok"):
        return Result(str(out.get("error") or "The speaking speed could not be changed."), n)
    return Result(str(out.get("message") or V.SPEED_SAID.get(choice, "Done.")), n)

# --------------------------------------------------------------------------
#   Numbers and lengths of time
# --------------------------------------------------------------------------

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_UNIT_S = {"h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
           "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
           "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1}


def _tokens(s: str) -> list:
    return re.findall(r"\d+(?:\.\d+)?|[a-z]+", s.replace("-", " "))


def _number(tok: list, i: int):
    """(value, next index) or (None, i)."""
    n = len(tok)
    if i >= n:
        return None, i
    t = tok[i]
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return float(t), i + 1
    if t in ("a", "an"):
        if i + 2 < n and tok[i + 1] == "couple" and tok[i + 2] == "of":
            return 2.0, i + 3
        return 1.0, i + 1
    if t in _TENS:
        if i + 1 < n and tok[i + 1] in _UNITS and 0 < _UNITS[tok[i + 1]] < 10:
            return float(_TENS[t] + _UNITS[tok[i + 1]]), i + 2
        return float(_TENS[t]), i + 1
    if t in _UNITS:
        return float(_UNITS[t]), i + 1
    return None, i


def parse_duration(s: str) -> Optional[float]:
    """Seconds, or None when `s` is not wholly a length of time.
    '10 minutes', '1h30', 'an hour and a half', 'half an hour', '90 seconds',
    '1 hour 30 minutes', 'twenty five minutes', 'a minute and a half'."""
    tok = _tokens(s.strip())
    if not tok:
        return None
    total, i, last = 0.0, 0, None
    n = len(tok)
    while i < n:
        if tok[i] == "and":
            i += 1
            continue
        # half an hour / half a minute / half hour
        if tok[i] == "half":
            j = i + 1 + (1 if i + 1 < n and tok[i + 1] in ("a", "an") else 0)
            if j < n and tok[j] in _UNIT_S:
                total += 0.5 * _UNIT_S[tok[j]]
                last, i = _UNIT_S[tok[j]], j + 1
                continue
            return None
        # (a) quarter (of an) hour
        if tok[i] == "quarter" or (tok[i] == "a" and i + 1 < n and tok[i + 1] == "quarter"):
            j = i + (2 if tok[i] == "a" else 1)
            if j + 1 < n and tok[j] == "of" and tok[j + 1] in ("an", "a"):
                j += 2
            if j < n and tok[j] in ("hour",):
                total += 900
                last, i = 3600, j + 1
                continue
            return None
        num, j = _number(tok, i)
        if num is None:
            return None
        half = False
        if tok[j:j + 3] == ["and", "a", "half"]:
            half, j = True, j + 3
        if j < n and tok[j] in _UNIT_S:
            unit = _UNIT_S[tok[j]]
            j += 1
        elif j == n and last == 3600 and num < 60:
            unit = 60           # 1h30, 1 hour 30
        elif j == n and last == 60 and num < 60:
            unit = 1            # 2 min 30
        else:
            return None
        if tok[j:j + 3] == ["and", "a", "half"]:
            half, j = True, j + 3
        total += (num + (0.5 if half else 0.0)) * unit
        last, i = unit, j
    return total if total > 0 else None

# --------------------------------------------------------------------------
#   Clock times and days
# --------------------------------------------------------------------------

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WD = "|".join(_WEEKDAYS)
_MER = r"(?:\s*(am|pm)|\s+in\s+the\s+(morning|afternoon|evening)|\s+at\s+night)?"


def _small(word: str) -> Optional[int]:
    if re.fullmatch(r"\d{1,2}", word):
        return int(word)
    return _UNITS.get(word)


def _minutes_words(s: str) -> Optional[int]:
    """'30', 'thirty', 'forty five', 'oh five', '05' -> minutes past."""
    s = s.strip()
    if re.fullmatch(r"\d{2}", s):
        return int(s)
    m = re.fullmatch(r"(?:oh|o)\s+(\w+)", s)
    if m and m.group(1) in _UNITS and _UNITS[m.group(1)] < 10:
        return _UNITS[m.group(1)]
    tok = s.split()
    if len(tok) == 1 and tok[0] in _UNITS and _UNITS[tok[0]] >= 10:
        return _UNITS[tok[0]]
    if tok and tok[0] in _TENS and _TENS[tok[0]] < 60:
        if len(tok) == 1:
            return _TENS[tok[0]]
        if len(tok) == 2 and tok[1] in _UNITS and 0 < _UNITS[tok[1]] < 10:
            return _TENS[tok[0]] + _UNITS[tok[1]]
    return None


@dataclass
class Clock:
    hh: int
    mm: int
    mer: Optional[str]      # "am", "pm", "24" (unambiguous), or None (a bare 1-12)
    #: "12" said with nothing to say which 12 (a bare "12", or "12 at night"): it
    #: is read as MIDNIGHT (owner, 2026-09-30) and the reply says the time back
    #: as "12:00 midnight", so a wrong guess is caught at once.
    said12: bool = False


def parse_clock(s: str) -> Optional[Clock]:
    s = s.strip()
    s = re.sub(r"^at\s+", "", s)
    if s in ("noon", "midday", "12 noon"):
        return Clock(12, 0, "24")
    if s == "midnight":
        return Clock(0, 0, "24")
    mer = None
    night_word = False
    m = re.fullmatch(r"(.+?)" + _MER, s)
    body = s
    if m:
        body = m.group(1)
        if m.group(2):
            mer = m.group(2)
        elif m.group(3):
            mer = "am" if m.group(3) == "morning" else "pm"
            night_word = m.group(3) == "evening"
        elif s.endswith("at night"):
            mer = "pm"
            night_word = True
    body = re.sub(r"\s*o'?\s?clock$", "", body).strip()
    hh = mm = None
    lead_zero = False
    # 7:30, 07:30, 7.30
    mt = re.fullmatch(r"(\d{1,2})[:.](\d{2})", body)
    if mt:
        hh, mm = int(mt.group(1)), int(mt.group(2))
        lead_zero = mt.group(1).startswith("0") and len(mt.group(1)) == 2
    if hh is None:
        mt = re.fullmatch(r"(\d{1,2})", body)
        if mt:
            hh, mm = int(mt.group(1)), 0
            lead_zero = mt.group(1).startswith("0") and len(mt.group(1)) == 2
    if hh is None:
        # "half past 7", "quarter past seven", "ten past 7", "quarter to 8", "20 to 8"
        mt = re.fullmatch(r"(half|quarter|\w+(?: \w+)?)\s+(past|to|after)\s+(\w+)", body)
        if mt:
            h = _small(mt.group(3))
            what = mt.group(1)
            mins = 30 if what == "half" else 15 if what == "quarter" else (
                int(what) if what.isdigit() else _minutes_words(what)
                if what not in _UNITS or _UNITS[what] >= 10 else _UNITS[what])
            if h is not None and mins is not None and 1 <= h <= 12 and 0 < mins < 60:
                if mt.group(2) == "to":
                    if what == "half":
                        return None
                    hh, mm = (h - 1) if h > 1 else 12, 60 - mins
                else:
                    hh, mm = h, mins
    if hh is None:
        # "seven", "seven thirty", "seven forty five", "7 30"
        tok = body.split(maxsplit=1)
        if tok:
            h = _small(tok[0])
            if h is not None and 1 <= h <= 12:
                if len(tok) == 1:
                    hh, mm = h, 0
                else:
                    mins = _minutes_words(tok[1])
                    if mins is not None and mins < 60:
                        hh, mm = h, mins
    if hh is None or mm is None or hh > 23 or mm > 59:
        return None
    if mer in ("am", "pm"):
        if hh == 0 or hh > 12:
            return None
        if hh == 12 and mer == "pm" and night_word:
            # "12 at night" and "12 in the evening" are midnight, not noon.
            return Clock(12, mm, "am", said12=True)
        return Clock(hh, mm, mer)
    if hh == 0 or hh > 12 or lead_zero:
        return Clock(hh, mm, "24")
    return Clock(hh, mm, None, said12=(hh == 12))


def _hour24(c: Clock, part: Optional[str]) -> list:
    """Candidate hours for a clock, earliest-preferred first."""
    if c.mer == "24":
        return [c.hh]
    if c.mer == "am":
        return [c.hh % 12]
    if c.mer == "pm":
        return [c.hh % 12 + 12]
    if part in ("evening", "night", "tonight") and c.hh == 12:
        return [0]                  # 12 in the evening / at night / tonight: midnight
    if part in ("afternoon", "evening", "night", "tonight"):
        return [c.hh % 12 + 12]
    if part == "morning":
        return [c.hh % 12]
    return [c.hh % 12, c.hh % 12 + 12]


def _day_of(now: float, n: int) -> tuple:
    import jarvis_schedule as S
    lt = time.localtime(now)
    return S._add_days(lt.tm_year, lt.tm_mon, lt.tm_mday, n) if n else (
        lt.tm_year, lt.tm_mon, lt.tm_mday)


def _days_until(now: float, weekday: int) -> int:
    today = time.localtime(now).tm_wday
    d = (weekday - today) % 7
    return d or 7           # "on Monday" said on a Monday is next Monday


@dataclass
class When:
    at: Optional[float] = None
    rule: Optional[dict] = None
    passed: bool = False        # a time today that has already gone
    default_time: bool = False  # no clock was said; a default was chosen
    said12: bool = False        # a "12" with no am/pm: the reply says which 12 was set


#: Times used when a day is said with no time ("remind me tomorrow to ...").
#: The reply always says the time chosen, so the owner can put it right.
DEFAULT_HOUR = {"morning": 9, "afternoon": 14, "evening": 18, "night": 20, "tonight": 20,
                None: 9}

_DAYPART = r"(?:\s+(morning|afternoon|evening|night))?"


#: Months and short weekdays, for a calendar date ("Sat 12 Oct", "October
#: 12th 2026", "12/10", "2026-10-12") - added 2026-09-28 for "Photo to
#: reminder" (jarvis_photo_remind.py), which reads dates off a flyer with THIS
#: parser rather than a second one. Said to Jarvis it works too: "remind me on
#: 12 October at 2pm to pay the deposit".
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_MONTH_OF = {m: i + 1 for i, m in enumerate(_MONTHS)}
_MONTH_OF.update({m[:3]: i + 1 for i, m in enumerate(_MONTHS)})
_MONTH_OF["sept"] = 9
_MON = "|".join(sorted(_MONTH_OF, key=len, reverse=True))
_WD_SHORT = r"(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)"
_WD_ANY = r"(?:(?:" + _WD + r"|" + _WD_SHORT + r")\.?,?\s+(?:the\s+)?)?"
_DAY_NUM = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(\d{4}))?"

#: How a slashed date is read when both numbers could be the month
#: ("5/10"): month first, as in the United States (the owner's help line is
#: the US one, CLAUDE.md 2026-09-27). "13/10" can only be day first, and is.
SLASH_MONTH_FIRST = True


def _calendar_day(s: str):
    """('date', year or None, month, day) for a calendar date, or None. Not
    checked against a calendar here - _ymd does that, and says None for 31
    February."""
    m = re.fullmatch(_WD_ANY + _DAY_NUM + r"(?:\s+of)?\s+(" + _MON + r")\.?" + _YEAR, s)
    if m:
        return ("date", int(m.group(3)) if m.group(3) else None,
                _MONTH_OF[m.group(2)], int(m.group(1)))
    m = re.fullmatch(_WD_ANY + r"(" + _MON + r")\.?\s+(?:the\s+)?" + _DAY_NUM + _YEAR, s)
    if m:
        return ("date", int(m.group(3)) if m.group(3) else None,
                _MONTH_OF[m.group(1)], int(m.group(2)))
    m = re.fullmatch(_WD_ANY + r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return ("date", int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(_WD_ANY + r"(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        y = m.group(3)
        year = None if y is None else (2000 + int(y) if len(y) == 2 else int(y))
        if a > 12 >= b:
            mo, d = b, a
        elif b > 12 >= a or SLASH_MONTH_FIRST:
            mo, d = a, b
        else:
            mo, d = b, a
        return ("date", year, mo, d)
    return None


def _ymd(day, now: float):
    """(y, mo, d) for a day from _parse_day, or None for a date that does not
    exist. A calendar date with no year is the next one: this year's, or next
    year's when this year's has gone."""
    if isinstance(day, tuple) and day and day[0] == "date":
        import datetime
        _, year, mo, d = day
        lt = time.localtime(now)
        today = (lt.tm_year, lt.tm_mon, lt.tm_mday)
        y = year if year is not None else lt.tm_year
        try:
            datetime.date(y, mo, d)
        except ValueError:
            if year is not None:
                return None
            y = None
        if year is None and (y is None or (y, mo, d) < today):
            try:
                datetime.date(lt.tm_year + 1, mo, d)
            except ValueError:
                return None
            y = lt.tm_year + 1
        return (y, mo, d)
    n = _days_until(now, day[1]) if isinstance(day, tuple) else day
    return _day_of(now, n)


def _parse_day(s: str):
    """(days from today, ('wd', n) or ('date', y, mo, d), part) for a day
    phrase, or None."""
    s = s.strip()
    cal = _calendar_day(s)
    if cal is not None:
        return cal, None
    m = re.fullmatch(r"(today|tomorrow|tonight)" + _DAYPART, s)
    if m:
        day, part = m.group(1), m.group(2)
        if day == "tonight":
            return 0, "tonight"
        return (0 if day == "today" else 1), part
    m = re.fullmatch(r"this\s+(morning|afternoon|evening)", s)
    if m:
        return 0, m.group(1)
    m = re.fullmatch(r"(?:on\s+)?(" + _WD + r")" + _DAYPART, s)
    if m:
        return ("wd", _WEEKDAYS.index(m.group(1))), m.group(2)
    return None


def _resolve(c: Clock, day, part, now: float, kind: str) -> When:
    import jarvis_schedule as S
    if day is None:
        # The next time the clock shows it: today, or else tomorrow.
        best = None
        for h in _hour24(c, part):
            t = S.next_at(h, c.mm, now)
            if best is None or t < best:
                best = t
        return When(at=best, said12=c.said12)
    ymd = _ymd(day, now)
    if ymd is None:
        return None
    y, mo, d = ymd
    n = 1 if ymd != _day_of(now, 0) else 0      # another day than today
    if c.hh == 12 and c.mer is None and part in ("evening", "night", "tonight"):
        # "tonight at 12": the midnight that ENDS tonight, i.e. the next day's 00:00.
        y, mo, d = S._add_days(y, mo, d, 1)
    hours = _hour24(c, part)
    if c.mer is None and part is None and n > 0 and len(hours) == 2:
        # A bare hour on another day. An alarm is for waking up: the morning.
        # A reminder at 1 to 6 is the afternoon; 7 to 11, the morning.
        if kind == "alarm" or c.hh >= 7 or c.hh == 12:
            hours = [hours[0] if c.hh != 12 else 12]
        else:
            hours = [hours[1]]
    ts = sorted(S.wall_to_epoch(y, mo, d, h, c.mm) for h in hours)
    future = [t for t in ts if t > now]
    if not future:
        return When(at=ts[-1], passed=True, said12=c.said12)
    return When(at=future[0], said12=c.said12)


def parse_when(s: str, now: float, kind: str) -> Optional[When]:
    """A time for an alarm or a reminder, or a repeat. None if `s` is not
    wholly one."""
    s = s.strip()
    if not s:
        return None
    # --- repeating --------------------------------------------------------
    m = re.fullmatch(r"(?:every\s+hour|hourly)", s)
    if m:
        return When(rule={"every": "hours", "hours": 1, "start": _round_minute(now) + 3600})
    m = re.fullmatch(r"every\s+(\w+)\s+hours?", s)
    if m:
        n, _ = _number([m.group(1)], 0)
        if n is None or n != int(n):
            return None
        return When(rule={"every": "hours", "hours": int(n),
                          "start": _round_minute(now) + int(n) * 3600})
    m = re.fullmatch(r"(?:every\s+day|daily|each\s+day|every\s+(morning|evening|night))"
                     r"\s+at\s+(.+)", s)
    if m:
        c = parse_clock(m.group(2))
        if c is None:
            return None
        h = _hour24(c, m.group(1))[0]
        return When(rule={"every": "day", "at": f"{h:02d}:{c.mm:02d}"}, said12=c.said12)
    m = re.fullmatch(r"(?:every\s+weekday|on\s+weekdays|weekdays|every\s+work\s*day)"
                     r"(?:\s+morning)?\s+at\s+(.+)", s)
    if m:
        c = parse_clock(m.group(1))
        if c is None:
            return None
        h = _hour24(c, "morning" if "morning" in s else None)[0]
        return When(rule={"every": "weekday", "at": f"{h:02d}:{c.mm:02d}"}, said12=c.said12)
    m = re.fullmatch(r"(?:every|on)\s+((?:" + _WD + r")s?(?:(?:\s*,\s*|\s+and\s+)(?:" + _WD
                     + r")s?)*)(?:\s+(morning|afternoon|evening))?\s+at\s+(.+)", s)
    if m and (s.startswith("every") or re.search(r"(?:" + _WD + r")s\b", m.group(1))):
        days = sorted({_WEEKDAYS.index(w.rstrip("s") if w.rstrip("s") in _WEEKDAYS else w)
                       for w in re.findall(r"(?:" + _WD + r")s?", m.group(1))})
        c = parse_clock(m.group(3))
        if c is None or not days:
            return None
        h = _hour24(c, m.group(2))[0]
        return When(rule={"every": "week", "at": f"{h:02d}:{c.mm:02d}", "days": days},
                    said12=c.said12)
    if s.startswith("every ") or s.startswith("each "):
        return None
    # --- once ---------------------------------------------------------------
    m = re.fullmatch(r"in\s+(.+)", s)
    if m:
        d = parse_duration(m.group(1))
        if d is None:
            return None
        return When(at=now + d)
    # "30 minutes from now", "an hour from now", "half an hour from now"
    # (2026-10-31: the live owner's "a reminder for 30 minutes from now to
    # check my phone" reached the model as a calendar event).
    m = re.fullmatch(r"(.+?)\s+from\s+now", s)
    if m:
        d = parse_duration(m.group(1))
        if d is None:
            return None
        return When(at=now + d)
    # "tomorrow at 6", "on friday at 5pm", "tonight at 8", "tomorrow 6am"
    for split in _splits(s):
        a, b = split
        dp = _parse_day(a)
        if dp is not None:
            c = parse_clock(b)
            if c is not None:
                return _resolve(c, dp[0], dp[1], now, kind)
        # "at 6 tomorrow", "6pm on friday"
        dp = _parse_day(b)
        if dp is not None:
            c = parse_clock(a)
            if c is not None:
                return _resolve(c, dp[0], dp[1], now, kind)
    dp = _parse_day(s)
    if dp is not None:
        if kind == "alarm":
            return None       # "set an alarm for tomorrow" - at what time?
        day, part = dp
        ymd = _ymd(day, now)
        if ymd is None:
            return None
        y, mo, d = ymd
        import jarvis_schedule as S
        t = S.wall_to_epoch(y, mo, d, DEFAULT_HOUR.get(part, 9), 0)
        return When(at=t, default_time=True, passed=t <= now)
    c = parse_clock(s)
    if c is not None:
        return _resolve(c, None, None, now, kind)
    return None


def _splits(s: str):
    words = s.split()
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        yield a, re.sub(r"^at\s+", "", b)
        if a.endswith(" at"):
            yield a[:-3], b


def _round_minute(t: float) -> float:
    return float(int(t // 60) * 60)

# --------------------------------------------------------------------------
#   The grammar
# --------------------------------------------------------------------------

@dataclass
class Intent:
    name: str
    f: dict = field(default_factory=dict)


_ART = r"(?:(?:the|my|a|an|that|this|me\s+a)\s+)?"
_SET = r"(?:(?:set|start|make|create|put\s+on|give\s+me)\s+)?"
_LABEL = r"[a-z][a-z' ]{0,29}"


_NOT_LABEL = frozenset("set start make create i you me should can could would do does did how "
                       "what why when is are need want a an the my to for it this that all "
                       "every both any timer timers please".split())


def _label_ok(label: str) -> bool:
    """A timer's name: one to three plain words ("pasta", "the eggs")."""
    words = label.split()
    return (0 < len(words) <= 3 and re.fullmatch(_LABEL, label) is not None
            and not any(w in _NOT_LABEL for w in words))


def _timer_ref(s: str):
    """'', a duration, or a label, for '<the 10 minute | the pasta> timer'.
    None if `s` is not a timer reference."""
    m = re.fullmatch(_ART + r"(?:(.+?)\s+)?timers?", s)
    if not m:
        return None
    inner = (m.group(1) or "").strip()
    if not inner:
        return {}
    d = parse_duration(inner.replace(" long", ""))
    if d is not None:
        return {"length": d}
    if _label_ok(inner):
        return {"label": inner}
    return None


def _restore(original, piece: str) -> str:
    """`piece` (found in the lower-cased sentence) with the owner's own
    capitals put back: a reminder to "call Mum" says Mum."""
    flat = " ".join(str(original or "").replace("\u2019", "'").replace("\u2018", "'").split())
    i = flat.lower().find(piece)
    out = flat[i:i + len(piece)] if i >= 0 else piece
    return out.strip(" ,.;:!?")


def match(text, now: Optional[float] = None) -> Optional[Intent]:
    """The intent of a sentence, or None when it is not one of ours."""
    now = time.time() if now is None else now
    got = _match(text, now)
    if got is not None and got.f.get("text"):
        got.f["text"] = _restore(text, got.f["text"])
    if got is not None and got.f.get("about"):
        got.f["about"] = _restore(text, got.f["about"])
    if got is not None and got.f.get("items"):
        got.f["items"] = [_restore(text, i) for i in got.f["items"]]
    return got


def _match(text, now: float) -> Optional[Intent]:
    s = normalize_spoken_command(text)
    if not s or len(s) > 400 or "\n" in s:
        return None

    # --- a question about Jarvis's OWN features, from the raw sentence -------
    # The capability questions (2026-10-31, the pass-9 field test) are read
    # BEFORE the tidied sentence, because "can you add something to my
    # calendar?" loses its "can you" on the way in and would otherwise be
    # treated as an action request. See _feature_capability_question.
    got = _feature_capability_question(text)
    if got is not None:
        return got

    # --- plug-ins, before the reminder capability family (2026-10-31): "how
    # do I add a plugin" is a plug-in question, not "how do I ask for a
    # reminder".
    got = _plugins_question(text)
    if got is not None:
        return got

    # --- the Android builder, before the reminder capability family too:
    # "how do I ask you to build one" is about the app, not a reminder.
    got = _android_question(text)
    if got is not None:
        return got

    # --- timers, alarms and reminders, capability questions only (2026-10-31)
    # The owner asked "can you make a reminder for me" and the model said it
    # could not set a system alarm and could only note reminders in a calendar -
    # false. A real request with a time keeps its own reminder_set/timer_set/
    # alarm_set path; only the capability family is answered here.
    got = _reminders_question(text)
    if got is not None:
        return got
    got = _bare_when(s, now)
    if got is not None:
        return got

    # --- (a) actionable quick paths FIRST (2026-10-31 integration) ----------
    # A real action beats an "off" answer: the note writer, the organizer and
    # the local-calendar read are owned here, before any honesty sentence.
    # (The note lane's capture path really files even when the note TOOL is
    # off; the honesty lane's old note_write off-answer is retired.)
    # A rename/move is read from the RAW sentence first, so a new title keeps
    # its capital letters ("Home", not the lowercased matching form "home").
    got = _note_rename_move_asking(text)
    # notes read/search (2026-10-31) before the older note-honesty
    # shapes: 'read my note <title>' is a real read now.
    got = _notes_chat(s)
    if got is not None:
        return got
    got = _note_asking(s)
    if got is not None:
        return got
    got = _local_calendar_prompt(s)
    if got is not None:
        return got

    # --- (b) the stateful read doors and OFF-state sentences (2026-10-31, the
    # chat audit's second half). They run BEFORE the feature/settings grammars
    # because those answered some of these wrongly: a light command raised the
    # "lights without a card" SETTING card, quiet hours was explained with its
    # internal key, and "can you turn on the lights?" never reached the real
    # home-control state. Specific shapes only - a generic feature question
    # still belongs to the feature list (#1030).
    got = _honest_early(text, s)
    if got is not None:
        return got

    # --- the voice reflex (2026-10-21, Live/Voice audit V4) -----------------
    # Before everything else, because it is a whole short sentence: "speak
    # faster". It routes into an action that already exists
    # (`jarvis_voices.set_speed`) - not a card of its own, and it cannot
    # bypass `jarvis_gate` (there is nothing to approve). The selection and
    # screen reads are PR #691's Live path, not this fast path; see the block
    # above this language section.
    got = _voice_speed(s)
    if got is not None:
        return got

    # --- "what time is it?" / "what's the date?" (D3, 2026-10-25) -------------
    # FIRST among the questions: the words are a whole question and nothing
    # else below wants them, and this is the one answer that is a fact about
    # the PC rather than a guess - so it must never be reachable by a model,
    # and never slow. Reads nothing but `now`.
    got = _clock(s)
    if got is not None:
        return got

    # --- "what voice are you using?" / "how do I pair my phone?" -------------
    # (2026-10-29, the HUD field test). Both are questions about this PC that
    # the PC can answer from its own state, and the model answered both with an
    # invention. They run EARLY because each is a whole short question that no
    # other grammar owns, and both read only - no card, no change.
    got = _voice_ask(s)
    if got is not None:
        return got
    got = _pair_phone(s)
    if got is not None:
        return got

    # --- "send me the file ... to my phone" (jarvis_send_file.py, 2026-10-31) ---
    # The deterministic chat door for the built send-one-file feature (it is a
    # model tool, and the model tool is off in the shipped [tools].enabled). The
    # shapes require a real file name plus "file"/from-folder/to-my-phone, so
    # ordinary "send an email to Sam" stays the model's. See _send_file().
    got = _send_file(s)
    if got is not None:
        return got

    # --- bulk is refused outright: one at a time ----------------------------
    if re.fullmatch(r"(?:cancel|delete|remove|clear|stop)\s+(?:all|every|both)\s+(?:(?:of\s+)?"
                    r"(?:my|the)\s+)?(timers|alarms|reminders|todos?|todo\s+list|todo\s+items)"
                    r"|(?:clear|empty|delete)\s+(?:my|the)\s+todo\s+list", s):
        return Intent("bulk")

    # --- "hide the finance menu" (menu visibility, 2026-09-30) -------------------
    # Before the settings block below: "show the voice menu" is about the menu
    # list, while "show me the voice settings" still opens Settings.
    got = _menu_visibility(s)
    if got is not None:
        return got

    # --- "label this chat Work" (chat tags, 2026-09-30) --------------------------
    got = _chat_tag(s)
    if got is not None:
        return got

    # --- "stop using my work topic" (topic controls, 2026-09-30) -----------------
    got = _topic_mode(s)
    if got is not None:
        return got

    # --- "forget what you learned last week" (jarvis_forget_range.py) ----------
    # Before everything that starts with "delete"/"remove": this one names
    # what Jarvis learned or the chats, and a time frame. It only ever fills
    # in the checked list in Brain - it removes nothing.
    got = _forget_range(s, now)
    if got is not None:
        return got

    # --- "make me a widget ..." (jarvis_widgets.py, 2026-09-28) ---------------
    # Before timers and reminders: "make me a widget with a 10-minute timer
    # button" is about a widget, not a timer to set now.
    if _WIDGET.fullmatch(s):
        return Intent("widget_make", {"words": str(text)})

    # --- "make my notifications look like ..." (2026-10-30) -------------------
    # A CLOSED style spec (jarvis_notification_styles.py), never a layout and
    # never a colour value: the model picks from a menu, the phone draws it.
    # AFTER the widget rule, and tight enough to leave "turn notifications
    # off"/"quieter" to the settings grammar: only words about how they LOOK.
    if _STYLE.match(s):
        return Intent("notify_style", {"words": str(text)})

    # --- focus sessions (jarvis_focus.py) --------------------------------------
    got = _focus(s)
    if got is not None:
        return got

    # --- "how are you doing?" / "how am I doing?" with no focus session -------
    # (D11c, 2026-10-25). AFTER `_focus`, on purpose: while a session runs,
    # "how am I doing?" is that session's own status and stays that way. With
    # none running it used to fall to the model for 99 s and a web search.
    got = _wellbeing(s)
    if got is not None:
        return got

    # --- "where did I put ...?" (jarvis_places.py, 2026-09-28) ----------------
    # A QUESTION only: "where is my passport?". The owner saying where a
    # thing is ("I put the spare key under the blue pot") is never ours - it
    # goes to the model, and the learner learns it like any fact.
    # "Where's my phone?" is not a place question: it rings the phone
    # ("ring my phone" below, jarvis_find_phone.py) - the two features met
    # on these words when they were merged, 2026-09-28.
    got = None if _RING.fullmatch(s) else _where_put(s)
    if (got is not None and got.name == "where_put"
            and (_feature_lookup_exact(got.f.get("thing") or "") is not None
                 or (_feature_explicit(s) and _feature_says_jarvis(text)))):
        # "where is the talk button?" is a question about a FEATURE, not about
        # where the owner last put something. The feature guide answers it a
        # few lines below with the row's own `where` - and an explicit "Jarvis,
        # where is the turbo FEATURE?" reaches the guide's honest unknown
        # answer instead of a lost-object answer. An exact feature name or the
        # word feature/option plus Jarvis context only, so "where is my
        # passport?" and "where is my file manager?" keep this path (2026-10-26).
        got = None
    if got is not None:
        return got

    # --- "what did I miss?", snooze and "cancel that" (2026-09-25) -------------
    got = _missed(s) or _snooze(s) or _undo(s)
    if got is not None:
        return got

    # --- named lists: clearing one, and which lists there are -------------------
    got = _list_whole(s)
    if got is not None:
        return got

    # --- timers ----------------------------------------------------------------
    m = re.fullmatch(_SET + _ART + r"(.+?)\s+(?:long\s+)?timer(?:\s+(?:for|called|named)\s+"
                     r"(?:the\s+)?(" + _LABEL + r"))?", s)
    if m:
        d = parse_duration(m.group(1))
        label = (m.group(2) or "").strip()
        if d is not None and (not label or _label_ok(label)):
            return Intent("timer_set", {"seconds": d, "label": label})
        # "a pasta timer for 10 minutes" is below.
    m = re.fullmatch(_SET + _ART + r"(?:(" + _LABEL + r")\s+)?timer\s+(?:for\s+|of\s+)?(.+?)"
                     r"(?:\s+(?:for|called|named)\s+(?:the\s+)?(" + _LABEL + r"))?", s)
    if m:
        d = parse_duration(m.group(2))
        label = (m.group(1) or m.group(3) or "").strip()
        if d is not None and (not label or _label_ok(label)):
            return Intent("timer_set", {"seconds": d, "label": label})
    m = re.fullmatch(r"(?:cancel|stop|delete|remove|end|kill|turn\s+off|get\s+rid\s+of)\s+(.+)", s)
    if m:
        ref = _timer_ref(m.group(1))
        if ref is not None:
            return Intent("timer_cancel", ref)
    m = re.fullmatch(r"(pause|hold|freeze|resume|continue|unpause|restart\s+counting)\s+(.+)", s)
    if m:
        ref = _timer_ref(m.group(2))
        if ref is not None:
            return Intent("timer_pause" if m.group(1) in ("pause", "hold", "freeze")
                          else "timer_resume", ref)
    m = re.fullmatch(r"(?:add|put)\s+(?:another\s+|an\s+extra\s+)?(.+?)\s+(?:more\s+)?"
                     r"(?:to|on|onto)\s+(.+)", s)
    if m:
        d = parse_duration(m.group(1).replace(" more", ""))
        ref = _timer_ref(m.group(2))
        if d is not None and ref is not None:
            return Intent("timer_add", dict(ref, seconds=d))
    m = re.fullmatch(r"(?:add\s+)?(?:another\s+|an\s+extra\s+)?(.+?)\s+more\s+(hours?|minutes?|"
                     r"mins?|seconds?|secs?)|add\s+(?:another|an\s+extra)\s+(.+)", s)
    if m:
        d = parse_duration(m.group(1) + " " + m.group(2)) if m.group(1) else \
            parse_duration(m.group(3))
        if d is not None:
            return Intent("timer_add", {"seconds": d, "bare": True})
    m = re.fullmatch(r"(?:take|remove|subtract)\s+(.+?)\s+(?:off|from)\s+(.+)", s)
    if m:
        d = parse_duration(m.group(1))
        ref = _timer_ref(m.group(2))
        if d is not None and ref is not None:
            return Intent("timer_add", dict(ref, seconds=-d))
    for pat in (r"how\s+(?:much\s+time|long)\s+(?:is\s+|do\s+i\s+have\s+|have\s+i\s+got\s+)?"
                r"(?:left|remaining)(?:\s+(?:on|for|in)\s+(?P<ref>.+))?",
                r"how\s+long\s+(?:until|till|before|is\s+left\s+on)\s+(?P<ref>.+?)"
                r"(?:\s+(?:goes\s+off|is\s+done|finishes|ends|rings|is\s+up))?",
                r"(?:what's|what\s+is|whats)\s+(?:left|the\s+time\s+left|remaining)"
                r"(?:\s+on\s+(?P<ref>.+))?",
                r"time\s+left(?:\s+on\s+(?P<ref>.+))?",
                r"(?:check|show)\s+(?P<ref>.+)"):
        m = re.fullmatch(pat, s)
        if not m:
            continue
        tail = (m.group("ref") or "").strip()
        if not tail:
            return Intent("timer_status", {"bare": True})
        ref = _timer_ref(tail)
        if ref is not None:
            return Intent("timer_status", ref)
        break
    if re.fullmatch(r"(?:what|which)\s+timers?\s+(?:are|is|do\s+i\s+have)(?:\s+(?:running|set|on|"
                    r"going))?|(?:list|show)\s+(?:me\s+)?(?:my|the|all)\s+timers"
                    r"|any\s+timers(?:\s+running)?", s):
        return Intent("timer_status", {})

    # --- alarms ------------------------------------------------------------------
    m = re.fullmatch(r"(?:(?:set|make|create|put)\s+)?(?:an?\s+|my\s+|the\s+)?alarm\s+(?:for\s+|at\s+"
                     r"|to\s+)?(.+)|wake\s+me(?:\s+up)?\s+(?:at\s+|for\s+|by\s+)?(.+)", s)
    if m:
        when = parse_when(m.group(1) or m.group(2), now, "alarm")
        if when is not None:
            return Intent("alarm_set", {"when": when})
    m = re.fullmatch(r"(?:set\s+)?(?:an?\s+)?(.+?)\s+alarm", s)
    if m and not s.startswith(("cancel", "delete", "remove", "turn off", "stop")):
        when = parse_when(m.group(1), now, "alarm")
        if when is not None:
            return Intent("alarm_set", {"when": when})
    m = re.fullmatch(r"(?:cancel|delete|remove|turn\s+off|switch\s+off|get\s+rid\s+of)\s+"
                     + _ART + r"(?:(.+?)\s+)?alarms?", s)
    if m:
        f = {}
        if m.group(1):
            c = parse_clock(m.group(1))
            if c is None:
                return None
            f["clock"] = c
        return Intent("alarm_cancel", f)
    if re.fullmatch(r"(?:what|which)\s+alarms?\s+(?:do\s+i\s+have|are\s+set|is\s+set)"
                    r"|(?:list|show)\s+(?:me\s+)?(?:my|the|all)\s+alarms|when\s+is\s+my\s+alarm"
                    r"|what\s+time\s+is\s+my\s+alarm(?:\s+set\s+for)?|any\s+alarms(?:\s+set)?", s):
        return Intent("alarm_list", {})

    # --- the weather, from the owner's own Home Assistant (2026-09-26) -----------
    if _WEATHER.fullmatch(s):
        return Intent("weather_now")

    # --- "read me the news" (jarvis_news.py, I49) -------------------------------
    if _NEWS_ASK.fullmatch(s):
        return Intent("news_read")
    m = _NEWS_ADD.fullmatch(s)
    if m:
        url = m.group("url") or m.group("url2") or m.group("url3")
        return Intent("news_add", {"url": _restore(text, url)})
    m = _NEWS_REMOVE.fullmatch(s)
    if m:
        return Intent("news_remove", {"url": _restore(text, m.group("url"))})
    if _NEWS_LIST.fullmatch(s):
        return Intent("news_list")

    # --- the morning briefing (jarvis_briefing.py) ------------------------------
    got = _briefing(s, now)
    if got is not None:
        return got

    # --- web search: which one, and switching (jarvis_search.py) -----------------
    got = _web_search(s)
    if got is not None:
        return got

    # --- "from now on ..." (jarvis_manner.py, 2026-09-27) -----------------------
    got = _from_now_on(s)
    if got is not None:
        return got

    # --- personality presets (2026-10-22) ---------------------------------------
    got = _personality(s)
    if got is not None:
        return got

    # --- thinking commands (jarvis_thinking.py, Section 5.5) --------------------
    got = _thinking_cmd(s)
    if got is not None:
        return got

    # --- "what can you do?" is the feature OVERVIEW now (2026-10-31 audit) ----
    # The sayable list is still the answer for "what can I say"/"help"; the
    # capability question is answered by group from the catalogue, capped, and
    # points at "Everything Jarvis can do".
    if _FEATURE_OVERVIEW.fullmatch(s):
        return Intent("feature_overview", {"words": ""})

    # --- "what can you do?" (jarvis_sayable.py) --------------------------------------
    if _SAYABLE.fullmatch(s):
        return Intent("sayable_help")

    # --- "what can you reach?" (jarvis_reach.py) -----------------------------------
    if _REACH.fullmatch(s):
        return Intent("reach_list")

    # --- "who are you?" (jarvis_identity.py, feasibility I131) ---------------------
    if _WHO_ARE_YOU.fullmatch(s):
        return Intent("identity_help")

    # --- "open a chat" (the floating face, 2026-09-27) --------------------------
    if _OPEN_CHAT.fullmatch(s):
        return Intent("open_chat")

    # --- a typed decision word ("approve", 2026-10-11) ----------------------
    # "approve", "deny", "yes", "no" as the WHOLE message. He typed one, and
    # the app answered him as ordinary chat - which reads as a broken app
    # rather than a deliberate rule. This says where the control is instead.
    if _TYPED_DECISION.fullmatch(s):
        return Intent("approval_where")

    # --- "open <a settings section>", and "turn on/off <a setting>" ------------
    # (jarvis_settings_registry.py, 2026-09-27) - see that module's own header.
    # Checked AFTER the older, more specific fast paths just above (bug audit
    # 2026-09-27, finding #8): the "reach" section's own aliases ("what
    # jarvis can reach/access") are word-for-word what _REACH already
    # matches for a different, established purpose - reading the list
    # aloud, not opening Settings to it - and checking this block first
    # made that older phrase silently unreachable. This block still runs
    # before everything below it, so it wins every case that does not
    # collide with something that came before it.
    # --- animal options (jarvis_animal.py, jarvis_sky.py; 2026-09-28) -----------
    # Before the generic "turn on/off <a setting>": "turn off the weather"
    # and "stop the animal's nodding" are ours; a tail that names no animal
    # option falls through untouched.
    got = _animal(s)
    if got is not None:
        return got

    got = _settings_open(s)
    if got is not None:
        return got
    got = _settings_help(s)
    if got is not None:
        return got
    got = _settings_adjust(s)
    if got is not None:
        return got
    # --- "is there an update?", "what changed in the update?", "update Jarvis"
    # (2026-10-26, the owner's ask: "can jarvis talk about an update if theres
    # one availabale and the changes? and start the update process for me?").
    # BEFORE the feature guide: "update Jarvis" must never be read as "update
    # <a feature>", and "what changed in the update" names no feature anyway.
    got = _update(s)
    if got is not None:
        return got
    # notes: read and search (deterministic, read-only, no card). BEFORE
    # the honesty/discussion shapes: 'read my note' is a real read now, and
    # the old 'chat does not read note text' refusal must not answer it.
    got = _notes_chat(s)
    if got is not None:
        return got
    # "what's coming up" / "what's my next reminder" is the SCHEDULER's list,
    # not a feature: the catalogue matches the "coming up" row's own id, so
    # this must run BEFORE the feature guide (2026-10-31 audit ordering bug).
    got = _next_up(s)
    if got is not None:
        return got

    # --- (b) the honest off / app-only / unbuilt sentences, BEFORE the
    # feature DISCUSSION shapes (2026-10-31 integration order: actions, then
    # honesty, then discussion). Only the settings ASK shapes live here now;
    # "tell me about X" / "limits of X" fall through to the catalogue below.
    got = _honest_chat_prompt(s)
    if got is not None:
        return got

    # --- (c) the feature discussion/introspection shapes --------------------
    # "Can I edit the HUD in the jarvis app?" (2026-10-31, the owner's
    # screenshot: the model said Jarvis had no built-in method, which is false
    # about the product). Answered HERE, before the feature guide, and only when
    # the request says it is the phone - see `_hud_edit`.
    got = _hud_edit(s)
    if got is not None:
        return got
    # "What is <feature>?", "is <feature> on?", "how do I turn it on/off?" and
    # "turn on <feature>" (2026-10-20). AFTER the settings block on purpose:
    # every setting already worded keeps its own path, card rule and words, and
    # this only answers where those patterns found nothing. Hardened 2026-10-20
    # (Gemini review 11.8.3): without "Jarvis"/"here"/"my settings" in the RAW
    # message, the subject must be an EXACT feature/switch name - so "what is a
    # focus session in psychology?" and "is my oven on?" fall through to the
    # model, never to a feature's facts. `test_feature_guide.py` pins both.
    got = _feature_guide(s, text)
    if got is not None:
        return got

    # --- music and video control on this PC (jarvis_media.py, I91) -------------------
    got = _media(s)
    if got is not None:
        return got

    # --- "find cheap parking near ..." (jarvis_parking.py, 2026-10-30) ----------------
    # The word "parking" is required by the grammar, so this cannot take a
    # sentence from another intent; it is placed AFTER the voice reflex and the
    # clock/date answers for the same reason those run first.
    got = _parking_lookup(s, now)
    if got is not None:
        return got

    # --- Today cards (jarvis_today.py, 2026-09-28) ------------------------------------
    got = _today(s, now)
    if got is not None:
        return got

    # --- "PC help": why is my PC slow, how full is my disk ... (jarvis_pc_help.py) ---
    got = _pc_help(s)
    if got is not None:
        return got

    # --- "remind me next time I talk about ..." (jarvis_next_time.py) ------------------
    got = _next_time(s)
    if got is not None:
        return got

    # --- "what's my next reminder?" (the scheduler's own list, 2026-10-31) -------------
    # (checked EARLIER, before the feature guide, so "what's coming up" is the
    # scheduler's list and not the "coming up" feature row.)

    # --- "watch with me" (jarvis_screen.py, 2026-09-29) --------------------------------
    got = _watch(s)
    if got is not None:
        return got

    # --- "ring my phone" (jarvis_find_phone.py) and Lockdown (jarvis_asks_first.py) ----
    got = _find_phone(s) or _lockdown(s)
    if got is not None:
        return got

    # --- "tell me when ..." (jarvis_tellme.py) ------------------------------------------
    got = _tellme(s, text, now)
    if got is not None:
        return got

    # --- a number for a project's benchmark (jarvis_projects.py, 2026-09-28) ---------
    got = _project_log(s)
    if got is not None:
        return got

    # --- reminders -----------------------------------------------------------------
    got = _reminder(s, now)
    if got is not None:
        return got

    # --- the to-do list --------------------------------------------------------------
    m = re.fullmatch(r"(?:add|put|write|stick)\s+(.+?)\s+(?:to|on|onto|in)\s+(?:my|the)\s+todo"
                     r"(?:\s+list)?", s)
    if m:
        text = m.group(1).strip()
        if text and not re.fullmatch(_VAGUE, text):
            return Intent("todo_add", {"text": text})
    # A named list (2026-09-25): "add milk to the shopping list".
    got = _named_list(s)
    if got is not None:
        return got
    m = re.fullmatch(r"(?:add|put)\s+(?:to|on)\s+(?:my|the)\s+todo(?:\s+list)?\s*[:,-]?\s*(.+)", s)
    if m:
        return Intent("todo_add", {"text": m.group(1).strip()})
    if re.fullmatch(r"(?:what's|what\s+is|whats|what\s+are|what's\s+left|what\s+is\s+left)\s+on\s+"
                    r"(?:my|the)\s+todo(?:\s+list)?|(?:read|show|list|tell|give)\s+(?:me\s+)?"
                    r"(?:my|the)\s+todo(?:\s+list)?|(?:my|the)\s+todo\s+list"
                    r"|what\s+do\s+i\s+have\s+on\s+my\s+todo(?:\s+list)?", s):
        return Intent("todo_list", {})
    m = re.fullmatch(r"(?:mark|tick|check|cross)\s+(?:off\s+)?(.+?)(?:\s+(?:as\s+)?(?:done|complete"
                     r"|completed|finished|off))?(?:\s+(?:on|from)\s+(?:my|the)\s+todo(?:\s+list)?)?",
                     s)
    if m and (re.search(r"\b(?:done|complete|completed|finished)\b", s)
              or re.match(r"(?:tick|check|cross)\s+off\b", s) or "todo" in s):
        text = m.group(1).strip()
        if text and text not in ("it", "that", "this", "everything", "all"):
            return Intent("todo_done", {"text": text})
    m = re.fullmatch(r"(?:remove|delete|take|scratch)\s+(.+?)\s+(?:from|off)\s+(?:my|the)\s+todo"
                     r"(?:\s+list)?", s)
    if m:
        return Intent("todo_remove", {"text": m.group(1).strip()})
    # --- "connect my google calendar", "set up a calendar bridge for me"
    # (2026-10-28, the owner's HUD screenshot) --------------------------------
    # The reader is real (jarvis_calendar.py) and nothing about it is a bridge,
    # a sign-in or a permission grant - but no sentence here owned the words the
    # owner used, so the model answered and invented that limitation. LAST among
    # the real matchers, beside _notion and for the same reason: a reminder or a
    # watch that merely mentions a calendar keeps its own answer, and "open my
    # calendar" still opens the app (jarvis_open.py). A plain "what's on my
    # calendar today" is deliberately NOT matched - it still goes to the model,
    # which can read it through the calendar_read tool once the tool is offered.
    got = _calendar_setup(s)
    if got is not None:
        return got

    # --- "process all my Notion notes into Obsidian" (2026-10-28) ---------------
    # The owner's screenshot of 2026-10-27 205732. This sentence used to reach
    # the model, which has no Notion tool and answered "I cannot directly
    # access or process files from Notion" - while both the export import
    # (jarvis_documents.import_notion) and the vault converter
    # (jarvis_notion_obsidian.py) exist on this PC. LAST among the real
    # matchers, beside _open and for the same reason: a reminder or a watch
    # that merely mentions Notion keeps its own answer, and "open Notion"
    # still opens the app (jarvis_open.py) instead of landing here.
    got = _notion(s)
    if got is not None:
        return got

    # --- "open Notion", "open settings", "open Jarvis settings" (jarvis_open.py,
    # the owner's request of 2026-10-10) --------------------------------------
    # LAST among the real matchers, and the placement is the fix, not a
    # preference. `jarvis_open.parse` reads any sentence beginning with
    # "open"/"launch"/"start" as naming a program, and `_watch` above owns
    # "start watching my screen" (jarvis_screen.py, 2026-09-29). Tried before
    # `_watch`, this claimed that phrase: "start watching my screen" resolved to
    # a program called "watching my", so the watch session never started and no
    # screen was ever read. backend/test_screen_turn.py caught it on CI. Last,
    # it can only claim a phrase no other feature already owns - exactly what
    # the owner's request adds, and nothing already answered changes hands.
    #
    # It still runs before the model: like music and video control (the owner,
    # 2026-09-27, "no card, only from the owner's own words"), opening a program
    # the owner already has changes nothing Jarvis holds, and the model gets no
    # tool for it, so outside text cannot reach it either. "open a chat" (about
    # this conversation, not a program) and "open web search" (the settings
    # block's own phrase, always answered `settings_open`) are matched above and
    # keep their own answers.
    got = _open(s)
    if got is not None:
        return got

    # --- an animal request nothing above understood (2026-09-28) ------------------
    # Last, so a reminder or a list that happens to mention "the animal" is
    # never taken for one: a plain question back, never a guess.
    if _ANIMAL_UNSURE.fullmatch(s):
        return Intent("animal_ask", {"about": "animal"})
    return None


_VAGUE = r"(?:it|this|that|them|these|those|something|stuff|things)"

#: A named list's name as said: one to three words before "list".
_NAME = r"([a-z][a-z'-]*(?:\s+[a-z][a-z'-]*){0,2})"
_OWN = r"(?:my|the|our)"


def _key(name: str):
    """(True, key) for a list's name (key None: the to-do list), or (False,
    None) when the words cannot be a list's name."""
    import jarvis_schedule as S
    try:
        return True, S.list_key(name)
    except ValueError:
        return False, None


def _items(text: str) -> list:
    """"milk, eggs and bread" -> three items; without a comma it is ONE item
    ("mac and cheese"). At most ten."""
    if "," not in text:
        return [text.strip()]
    parts = [p.strip() for p in text.split(",")]
    last = parts[-1]
    if last.startswith("and "):
        parts[-1] = last[4:].strip()
    elif " and " in last:
        head, _, tail = last.rpartition(" and ")
        parts[-1:] = [head.strip(), tail.strip()]
    out = [p for p in parts if p]
    return out if 0 < len(out) <= 10 else []


def _named_list(s: str) -> Optional[Intent]:
    """Add to, read, tick off or remove from a NAMED list ("shopping"). The
    to-do list's own sentences are matched above; a name that is the to-do
    list ("todo") lands here only in forms those do not cover."""
    m = re.fullmatch(r"(?:add|put|write|stick|pop)\s+(.+?)\s+(?:to|on|onto|in)\s+" + _OWN
                     + r"\s+" + _NAME + r"\s+list", s)
    if m:
        ok, key = _key(m.group(2))
        text = m.group(1).strip()
        if ok and text and not re.fullmatch(_VAGUE, text):
            items = _items(text) if key else [text]
            if items and not any(re.fullmatch(_VAGUE, i) for i in items):
                return Intent("todo_add", {"text": text, "items": items, "list": key})
    m = re.fullmatch(r"(?:(?:what's|what\s+is|whats|what\s+are|what's\s+left|what\s+is\s+left)"
                     r"\s+on|(?:read|show|list|tell|give)\s+(?:me\s+)?|what\s+do\s+i\s+(?:have|need)"
                     r"\s+on)?\s*" + _OWN + r"\s+" + _NAME + r"\s+list", s)
    if m:
        ok, key = _key(m.group(1))
        if ok:
            return Intent("todo_list", {"list": key, "named": True})
    m = re.fullmatch(r"(?:mark|tick|check|cross)\s+(?:off\s+)?(.+?)(?:\s+(?:as\s+)?(?:done|complete"
                     r"|completed|finished|bought|got))?\s+(?:on|from|off)\s+" + _OWN + r"\s+" + _NAME
                     + r"\s+list", s)
    if m:
        ok, key = _key(m.group(2))
        text = m.group(1).strip()
        if ok and text and not re.fullmatch(_VAGUE + r"|everything|all", text):
            return Intent("todo_done", {"text": text, "list": key, "named": True})
    m = re.fullmatch(r"(?:remove|delete|take|scratch)\s+(.+?)\s+(?:from|off)\s+" + _OWN + r"\s+"
                     + _NAME + r"\s+list", s)
    if m:
        ok, key = _key(m.group(2))
        text = m.group(1).strip()
        if ok and text and not re.fullmatch(_VAGUE + r"|everything|all", text):
            return Intent("todo_remove", {"text": text, "list": key, "named": True})
    return None


def _list_whole(s: str) -> Optional[Intent]:
    """"Clear the shopping list" (changes nothing: the app asks "are you
    sure?" first) and "what lists do I have"."""
    m = re.fullmatch(r"(?:clear|empty|wipe|reset|delete)\s+(?:out\s+)?" + _OWN + r"\s+" + _NAME
                     + r"\s+list|(?:clear|remove|delete)\s+(?:everything|all(?:\s+the)?\s+items|"
                     r"every\s+item|all)\s+(?:from|off|on)\s+" + _OWN + r"\s+" + _NAME + r"\s+list",
                     s)
    if m:
        ok, key = _key(m.group(1) or m.group(2))
        if ok:
            return Intent("bulk") if key is None else Intent("list_clear", {"list": key})
    if re.fullmatch(r"(?:what|which)\s+lists\s+(?:do\s+i\s+have|have\s+i\s+got|are\s+there)"
                    r"|(?:show|list|read)\s+(?:me\s+)?(?:all\s+)?(?:my|the)\s+lists"
                    r"|what\s+are\s+my\s+lists|my\s+lists", s):
        return Intent("lists_which")
    return None


def _where_put(s: str) -> Optional[Intent]:
    """"where is my passport?", "where did I put the spare key?" - the thing
    asked about, from jarvis_places' grammar. None without that module."""
    try:
        import jarvis_places
        thing = jarvis_places.where_question(s)
    except Exception:
        return None
    return Intent("where_put", {"thing": thing}) if thing else None


def _missed(s: str) -> Optional[Intent]:
    """"What did I miss?" (jarvis_briefing.build_missed)."""
    if re.fullmatch(r"what\s+(?:did|have)\s+i\s+miss(?:ed)?(?:\s+while\s+i\s+was\s+(?:away|out|gone))?"
                    r"|what'?d\s+i\s+miss|(?:did|have)\s+i\s+miss(?:ed)?\s+anything"
                    r"|anything\s+(?:i\s+missed|new)|catch\s+me\s+up|fill\s+me\s+in"
                    r"|what's\s+new|whats\s+new|what\s+is\s+new"
                    r"|what\s+happened\s+while\s+i\s+was\s+(?:away|out|gone)", s):
        return Intent("missed")
    return None


def _snooze(s: str) -> Optional[Intent]:
    """"snooze", "snooze 10 minutes", "snooze the alarm for 5 minutes",
    "remind me again in 5 minutes"."""
    m = re.fullmatch(r"snooze(?:\s+(?:it|that|this|(?:the|my|that)\s+(alarm|reminder|timer)))?"
                     r"(?:\s+(?:for\s+)?(?:another\s+)?(.+))?"
                     r"|remind\s+me\s+again(?:\s+in\s+(.+))?", s)
    if not m:
        return None
    length = m.group(2) or m.group(3)
    seconds = None
    if length:
        seconds = parse_duration(length)
        if seconds is None:
            return None
    return Intent("snooze", {"seconds": seconds, "kind": m.group(1)})


#: What "cancel that <noun>" may name, and the nouns each kind answers to.
_UNDO_NOUNS = {"timer": "timer", "alarm": "alarm", "reminder": "reminder",
               "briefing": "briefing", "snooze": "snooze", "item": "item", "todo": "item",
               "todo item": "item", "card": "card", "one": None, "": None}


def _undo(s: str) -> Optional[Intent]:
    """"cancel that", "never mind", "undo", "delete that reminder" - the
    last thing this fast path set in this conversation. Never "forget
    that": that is memory's word."""
    t = re.sub(r"^(?:(?:no|oh|actually|sorry|wait|oops|hmm|ah)\b[\s,]*)+", "", s).strip()
    if re.fullmatch(r"never\s*mind(?:\s+that)?", t):
        # Soft: with nothing just set here, or set too long ago, it is not
        # about a reminder at all - the model answers, as before.
        return Intent("undo", {"noun": None, "soft": True})
    if re.fullmatch(r"undo(?:\s+that)?", t):
        return Intent("undo", {"noun": None, "soft": False})
    m = re.fullmatch(r"(?:cancel|undo|scratch|delete|remove|take\s+back)\s+(?:that|it|the\s+last\s+one|"
                     r"what\s+you\s+just\s+(?:set|added|did))(?:\s+(timer|alarm|reminder|briefing|"
                     r"snooze|item|card|one|todo(?:\s+item)?))?", t)
    if m:
        return Intent("undo", {"noun": _UNDO_NOUNS.get(m.group(1) or ""), "soft": False})
    return None


# --------------------------------------------------------------------------
#   The clock and the date - answered from the PC, never the model (D3,
#   the live campaign of 2026-10-25)
# --------------------------------------------------------------------------
#
# R13 of the campaign ("What time is it?") took 82.1 s on `qwen3.5:9b` and
# came back with 10:42 AM while the PC's own clock read 20:16-20:18 - a wrong
# answer to a question this PC can answer exactly, for free, in microseconds.
# A model never sees the clock, so it can only guess. These two intents read
# `time.localtime(now)` and nothing else: no file, no socket, no model.
#
# THE GRAMMAR IS A WHOLE SHORT SENTENCE, as everywhere in this file, so a
# question that only mentions a time ("what time is the meeting?") still goes
# to the model and to the calendar - the words have to BE the question.

_CLOCK_TIME = re.compile(
    r"(?:what(?:'s|\s+is)\s+the\s+time"
    r"|what\s+time\s+is\s+it"
    r"|what\s+time\s+(?:do\s+you\s+have|have\s+you\s+got)"
    r"|have\s+you\s+got\s+the\s+time"
    r"|tell\s+me\s+the\s+time"
    r"|(?:the\s+)?current\s+time)"
    r"(?:\s+(?:now|right\s+now|please|on\s+this\s+pc|here|for\s+me|exactly))*")
_CLOCK_DATE = re.compile(
    r"(?:what(?:'s|\s+is)\s+(?:the\s+|today's\s+|todays\s+)?date(?:\s+today)?"
    r"|what\s+date\s+is\s+it(?:\s+today)?"
    r"|what\s+day\s+is\s+it(?:\s+today)?"
    r"|what(?:'s|\s+is)\s+today(?:'s)?\s+date"
    r"|tell\s+me\s+the\s+date(?:\s+today)?"
    r"|(?:the\s+)?current\s+date)"
    r"(?:\s+(?:today|now|right\s+now|please|on\s+this\s+pc|here))*")
#: Both at once: "what is the time and date?" is one question with one answer.
_CLOCK_BOTH = re.compile(
    r"(?:what(?:'s|\s+is)\s+the\s+time\s+and\s+(?:the\s+)?date"
    r"|what\s+time\s+and\s+(?:what\s+)?date(?:\s+is\s+it)?"
    r"|the\s+time\s+and\s+(?:the\s+)?date)")


def _clock(s: str) -> Optional[Intent]:
    """`time_now`, `date_today` or `clock_both` for a whole question about the
    PC's own clock, or None (then nothing here has claimed it)."""
    if _CLOCK_BOTH.fullmatch(s):
        return Intent("clock_both")
    if _CLOCK_TIME.fullmatch(s):
        return Intent("time_now")
    if _CLOCK_DATE.fullmatch(s):
        return Intent("date_today")
    return None


def _run_clock(intent: Intent, now: float) -> Result:
    """The PC's own clock, in the owner's words. Reads nothing else.

    The same 24-hour form both apps show (jarvis_schedule.clock), and the day
    and date the PC itself thinks it is - never a model's guess.
    """
    n = intent.name
    lt = time.localtime(now)
    weekday = _WEEKDAYS[lt.tm_wday].capitalize()
    month = _MONTHS[lt.tm_mon - 1].capitalize()
    day = f"{weekday} {lt.tm_mday} {month}"
    clock = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    if n == "date_today":
        return Result(f"It is {day} {lt.tm_year}.", n)
    if n == "clock_both":
        return Result(f"It is {clock} on {day} {lt.tm_year}.", n)
    return Result(f"It is {clock} on {day}.", n)


# --------------------------------------------------------------------------
#   "How are you doing?" and "How am I doing?" - answered here, not by a
#   99-second model turn that searches the web for the owner's mood (D11c)
# --------------------------------------------------------------------------
#
# R14 of the campaign: "How am I doing?" (no focus session) went to the local
# model for 99.1 s, ran web_search twice and came back with "I do not know how
# you are doing personally, sir" - honest, but a minute and a half to say that
# a program cannot know. Both questions have a short, fixed, honest answer:
#   * "how am I doing?" with no focus session running - there is nothing of
#     Jarvis's to report on, and it says so and says how to start one;
#   * "how are you doing?" - Jarvis is a program; it says so plainly.
# While a focus session runs, "how am I doing?" is the session's own status
# (the `_focus` block above runs first and keeps it).

_WELLBEING_YOU = re.compile(
    r"how\s+are\s+you(?:\s+(?:doing|today|feeling|going|keeping))?"
    r"|how'?s\s+it\s+going"
    r"|how\s+are\s+things(?:\s+going)?"
    r"|how\s+do\s+you\s+feel(?:\s+today)?"
    r"|are\s+you\s+(?:ok|okay|all\s+right|doing\s+ok|doing\s+okay)")
_WELLBEING_ME = re.compile(
    r"how\s+am\s+i\s+doing(?:\s+(?:today|so\s+far))?"
    r"|how'?s\s+my\s+(?:day|focus|session|progress)(?:\s+going)?"
    r"|how\s+is\s+my\s+(?:day|focus|session|progress)(?:\s+going)?")

#: Said for "how are you doing?" - the truth about a program, in one line.
WELLBEING_SAID = ("I am a program on your PC, so I have no day of my own to report - "
                  "but I am here and answering.")
#: Said for "how am I doing?" with no focus session: nothing of Jarvis's to
#: measure, and how to give it something. Never a guess about the owner.
NO_FOCUS_SAID = ('No focus session is running, so there is nothing of mine to report on. '
                 'Say "focus for 30 minutes" and I will tell you how it is going.')


def _wellbeing(s: str) -> Optional[Intent]:
    """"how are you doing?" / "how am I doing?" with no focus session."""
    if _WELLBEING_YOU.fullmatch(s):
        return Intent("wellbeing_now")
    if _WELLBEING_ME.fullmatch(s):
        return Intent("wellbeing_me")
    return None


def _run_wellbeing(intent: Intent) -> Result:
    n = intent.name
    if n == "wellbeing_me":
        # "how am I doing?" with no focus session: the same fixed line, never
        # a model turn and never a read of anything else.
        return Result(NO_FOCUS_SAID, n)
    return Result(WELLBEING_SAID, n)


# --------------------------------------------------------------------------
#   Focus sessions (jarvis_focus.py)
# --------------------------------------------------------------------------

_FOCUS_WORD = r"focus(?:ing)?(?:\s+(?:session|mode|block|time))?"
_FOCUS_REF = r"(?:(?:the|my|this|a)\s+)?" + _FOCUS_WORD
_THING = r"(?:tab|app|window|site|page|program|one)"


def _focus_on() -> bool:
    """Is a focus session running? A flag in memory - no file, no socket."""
    try:
        import jarvis_focus
        return bool(jarvis_focus.is_on())
    except Exception:
        return False


def _focus_minutes(d) -> Optional[float]:
    """Minutes from "30 minutes", "half an hour", "an hour", or a bare "30"."""
    if d is None:
        return None
    d = d.strip()
    if re.fullmatch(r"\d{1,3}", d):
        return float(d)
    secs = parse_duration(d)
    return None if secs is None else secs / 60.0


_FOCUS_START = (
    # "focus for 30 minutes (on the essay)", "start a focus session",
    # "let's start focus mode for an hour"
    r"(?P<lead>(?:let'?s\s+|lets\s+)?(?:start|begin|do)\s+)?(?:a\s+|my\s+)?focus"
    r"(?P<word>\s+(?:session|mode|block))?(?:\s+(?:for|of)\s+(?P<d>.+?))?"
    r"(?:\s+on\s+(?P<on>.+))?",
    # "let's focus (for 20 minutes)"
    r"(?P<lead>let'?s\s+|lets\s+)focus(?:\s+for\s+(?P<d>.+?))?(?:\s+on\s+(?P<on>.+))?",
    # "a 45 minute focus session", "30 minutes of focus"
    r"(?P<lead>(?:start|begin|do)\s+)?(?:a\s+|an\s+)?(?P<d>[a-z0-9 ]+?)\s+(?:of\s+)?focus"
    r"(?P<word>\s+(?:session|mode|block))?(?:\s+on\s+(?P<on>.+))?",
    # "start focusing (for 20 minutes)"
    r"(?P<lead>(?:start|begin)\s+)focusing(?:\s+for\s+(?P<d>.+?))?(?:\s+on\s+(?P<on>.+))?",
    # "help me focus for 30 minutes", "keep me focused for an hour"
    r"(?P<lead>(?:help|keep)\s+me\s+)focus(?:ed)?(?:\s+for\s+(?P<d>.+?))?"
    r"(?:\s+on\s+(?P<on>.+))?",
    # "focus on the essay for 30 minutes"
    r"focus\s+on\s+(?P<on>.+?)\s+for\s+(?P<d>.+)",
)


def _focus(s: str) -> Optional[Intent]:
    """A focus-session command, or None. Explicit ones ("focus for 30
    minutes", "stop focus") always; the short ones only while a session
    runs."""
    for pat in _FOCUS_START:
        m = re.fullmatch(pat, s)
        if not m:
            continue
        g = m.groupdict()
        mins = _focus_minutes(g.get("d"))
        if g.get("d") is not None and mins is None:
            continue
        if mins is None and not g.get("lead") and not g.get("word"):
            continue        # "focus on the positives" is a sentence, not a command
        return Intent("focus_start", {"minutes": mins, "text": (g.get("on") or "").strip()})
    if re.fullmatch(r"(?:stop|end|cancel|finish|abort|quit|exit)\s+" + _FOCUS_REF
                    + r"|i'?m\s+done\s+focusing|(?:i'?m\s+)?done\s+with\s+" + _FOCUS_REF, s):
        return Intent("focus_stop")
    if re.fullmatch(r"how'?s\s+" + _FOCUS_REF + r"\s+going|" + _FOCUS_REF + r"\s+status"
                    r"|how\s+(?:long|much\s+time)\s+(?:is\s+)?left\s+(?:on|in|of)\s+"
                    + _FOCUS_REF + r"|how\s+much\s+focus\s+(?:time\s+)?is\s+left", s):
        return Intent("focus_status")
    if re.fullmatch(r"pause\s+" + _FOCUS_REF, s):
        return Intent("focus_pause")
    if re.fullmatch(r"(?:resume|unpause|continue|restart)\s+" + _FOCUS_REF, s):
        return Intent("focus_resume")
    m = re.fullmatch(r"extend\s+" + _FOCUS_REF + r"(?:\s+by\s+(?P<d>.+))?"
                     r"|add\s+(?P<d2>.+?)\s+to\s+" + _FOCUS_REF, s)
    if m:
        d = m.group("d") or m.group("d2")
        mins = _focus_minutes(d)
        if d and mins is None:
            return None
        return Intent("focus_extend", {"minutes": mins})
    if not _focus_on():
        return None
    # -- only while a session runs --------------------------------------------
    if s == "pause":
        return Intent("focus_pause")
    if re.fullmatch(r"resume|unpause|carry\s+on|i'?m\s+back", s):
        return Intent("focus_resume")
    m = re.fullmatch(r"extend(?:\s+it)?(?:\s+by\s+(?P<d>.+))?", s)
    if m:
        mins = _focus_minutes(m.group("d"))
        if m.group("d") and mins is None:
            return None
        return Intent("focus_extend", {"minutes": mins})
    if re.fullmatch(r"(?:(?:i|we)\s+need|(?:just\s+)?give\s+me)\s+a\s+(?:minute|moment|sec|second)"
                    r"|(?:no[\s,]+)?(?:jarvis[\s,]+)?i\s+need\s+to\s+do\s+something"
                    r"(?:\s+important)?|leave\s+me\s+alone(?:\s+for\s+a\s+(?:minute|bit))?", s):
        return Intent("focus_relief")
    m = re.fullmatch(r"snooze(?:\s+(?:the\s+)?(?:focus|callouts?|nudges?|it))?"
                     r"(?:\s+for\s+(?P<d>.+))?|give\s+me\s+(?P<d2>.+)", s)
    if m:
        d = m.group("d") or m.group("d2")
        mins = _focus_minutes(d)
        if d and mins is None:
            return None
        return Intent("focus_snooze", {"minutes": mins})
    if re.fullmatch(r"(?:it'?s\s+(?:ok|okay|fine|alright)[\s,]+)?(?:i'?m|i\s+am)\s+(?:doing\s+"
                    r"(?:some\s+)?research|researching(?:\s+something)?)"
                    r"(?:\s+for\s+(?:it|this|work))?"
                    r"|(?:this|it)\s+is\s+(?:for\s+)?research|it'?s\s+(?:for\s+)?research"
                    r"|this\s+is\s+for\s+(?:work|the\s+task|it)", s):
        return Intent("focus_research")
    if re.fullmatch(r"(?:ok(?:ay)?[\s,]+)?(?:(?:i'?m\s+)?(?:gonna|going\s+to)\s+need\s+you\s+to\s+)?"
                    r"(?:lock\s+(?:on\s+)?(?:to\s+)?(?:this|here)(?:\s+" + _THING + r")?"
                    r"|lock\s+on|keep\s+me\s+(?:in|on)\s+this(?:\s+" + _THING + r")?"
                    r"|stay\s+(?:in|on)\s+this(?:\s+" + _THING + r")?"
                    r"|this\s+is\s+the\s+" + _THING + r"(?:\s+i'?m\s+working\s+(?:in|on))?)", s):
        return Intent("focus_lock")
    if re.fullmatch(r"how\s+am\s+i\s+doing|how'?s\s+it\s+going", s):
        return Intent("focus_status")
    m = re.fullmatch(r"(?:call\s+me\s+out|nag\s+me|check\s+on\s+me|tell\s+me\s+off)"
                     r"\s+every\s+(?P<d>.+)", s)
    if m:
        mins = _focus_minutes(m.group("d"))
        if mins is not None:
            return Intent("focus_nag", {"seconds": mins * 60.0})
    return None


FOCUS_MISSING = ("Your PC's Jarvis does not have focus sessions yet - run apply-patches.ps1 "
                 "on the PC.")

_FOCUS_DO = {"focus_stop": "stop", "focus_pause": "pause", "focus_resume": "resume",
             "focus_extend": "extend", "focus_snooze": "snooze", "focus_research": "research",
             "focus_relief": "relief", "focus_lock": "lock", "focus_nag": "nag"}


def _run_focus(intent: Intent) -> Result:
    """Focus-session commands, acted on at once by jarvis_focus's one
    engine, in its own words. Nothing here reads the screen."""
    n, f = intent.name, intent.f
    try:
        import jarvis_focus as F
    except Exception:
        return Result(FOCUS_MISSING, n)
    e = F.ENGINE
    if n == "focus_start":
        code, out = e.start(f.get("minutes"), f.get("text") or "", by="a chat message")
        return Result(str(out.get("said") or out.get("error") or ""), n)
    if n == "focus_status":
        return Result(F.spoken_status(e.status()), n)
    arg = f.get("seconds") if n == "focus_nag" else f.get("minutes")
    code, out = e.act(_FOCUS_DO[n], arg, by="a chat message")
    return Result(str(out.get("said") or out.get("error") or ""), n)


#: The ways a reminder is asked for. "add a reminder ..." is the owner's own
#: phrasing from the HUD (2026-10-27): it was NOT here, so the sentence went to
#: the model, which is only offered set_reminder when [tools].enabled names it
#: (the shipped list does not) - and the model then SAID it had set one while
#: no row was written. "i need a reminder", "a reminder" and "reminder to ..."
#: were missing the same way, and the polite lead-ins in _EXTRA_LEADS now make
#: "can you add a reminder ..." the plain command. Every phrasing this covers
#: is pinned in test_schedule.py, including the near-misses that must still go
#: to the model ("reminder set for 6pm" is a CLAIM, not a command).
#: A request lead-in the reminder grammar itself accepts. It is HERE and not in
#: `_EXTRA_LEADS` on purpose: the global normaliser must not strip "i need ...",
#: because a focus session says "I need a minute" - stripping that lead turned a
#: passing focus phrase into no match (caught by CI's test_focus on Windows).
#: "can you"/"please"/"would you" are still stripped globally; they are accepted
#: here too so the grammar reads the same whichever way it was reached.
_REMIND_LEAD = (r"(?:(?:can|could|would|will)\s+you\s+|please\s+|"
                r"i\s+(?:need|want|would\s+like)\s+(?:you\s+)?(?:to\s+)?)?")
_REMIND_ASK = (_REMIND_LEAD
               + r"(?:remind(?:\s+me)?"
                 r"|(?:add|set|make|create|schedule|put)\s+(?:a|an)?\s*"
                 r"(?:new\s+)?reminder"
                 r"|(?:a|an)\s+(?:new\s+)?reminder"
                 r"|new\s+reminder|reminder)")
_REMIND = re.compile(_REMIND_ASK)


def _bare_when(s: str, now: float) -> Optional[Intent]:
    """A bare time with no action word (2026-10-31).

    "in 10 minutes" is a timer. "at 6pm" / "tomorrow at 9" are reminders. A
    sentence with no time is never guessed at here; a sentence carrying an
    action word belongs to that action's own path.
    """
    if re.search(r"\b(?:remind|reminder|timer|alarm|calendar|event|note|call|email)\b", s):
        return None
    m = re.fullmatch(r"in\s+(.+)", s)
    if m:
        d = parse_duration(m.group(1))
        if d is not None:
            return Intent("timer_set", {"seconds": d, "label": ""})
        return None
    when = parse_when(s, now, "reminder")
    if when is not None:
        return Intent("reminder_set", {"text": "your reminder", "when": when})
    return None


def _reminder(s: str, now: float) -> Optional[Intent]:
    # "in 10 minutes remind me to drink water" / "at 6pm remind me to call"
    # (2026-10-18): the time can come first, exactly as it can in
    # "remind me in 20 minutes to ...". Found by the phone field test, whose
    # actual words were "remind in 2 minutes to drink water" - the leading
    # branch is what covers a time phrase before the command, and the optional
    # "me" below covers the shorthand the owner really typed.
    lead = re.fullmatch(r"(?P<lead>in|at|on)\s+(?P<when>.+?)\s+"
                        + _REMIND_ASK +
                        r"\s+(?:to|about|that)\s+(?P<text>.+)", s)
    if lead:
        text = lead.group("text").strip()
        if text and len(text) <= 300 and text not in (
                "it", "this", "that", "something", "things", "stuff"):
            when = parse_when(lead.group("lead") + " " + lead.group("when"),
                              now, "reminder")
            if when is not None:
                return Intent("reminder_set", {"text": text, "when": when})
    m = re.fullmatch(_REMIND.pattern + r"\s+(.+)", s)
    if not m:
        return None
    rest = m.group(1)
    # "remind me <when> to <text>" / "set a reminder for <when> to <text>"
    mw = re.fullmatch(r"(?:for\s+)?(.+?)\s+(?:to|about|that)\s+(.+)", rest)
    candidates = []
    if mw:
        candidates.append((mw.group(2), mw.group(1)))
    # "remind me to <text> <when>"
    mt = re.fullmatch(r"(?:to|about|that)\s+(.+)", rest)
    if mt:
        body = mt.group(1)
        words = body.split()
        for k in range(1, len(words)):
            candidates.append((" ".join(words[:k]), " ".join(words[k:])))
    for text, when_s in candidates:
        text = text.strip()
        if not text or len(text) > 300:
            continue
        # A reminder "about" nothing is not one.
        if text in ("it", "this", "that", "something", "things", "stuff"):
            continue
        when = parse_when(re.sub(r"^(?:at|for|on)\s+(?=\d|noon|midday|midnight)", "", when_s),
                          now, "reminder")
        if when is None and when_s.startswith(("at ", "on ")):
            when = parse_when(when_s[3:], now, "reminder")
        if when is not None:
            return Intent("reminder_set", {"text": text, "when": when})
    # "remind me 30 minutes from now" / "set a reminder in an hour" / "remind me
    # in 2 hours": a real reminder request whose words were only the time. The
    # scheduler requires SOME words, so the stored text is the honest default;
    # the confirmation still names the exact clock time.
    bare = re.sub(r"^for\s+", "", rest.strip())
    when = parse_when(bare, now, "reminder")
    if when is not None:
        return Intent("reminder_set", {"text": "your reminder", "when": when})
    return None


#: "Remind me next time I talk about X" (jarvis_next_time.py, 2026-09-28).
#: The subject is "the dentist" in each of: "remind me next time I talk about
#: the dentist to ask about the bill", "remind me to ask about the bill next
#: time I talk about the dentist", "next time I mention the dentist, remind
#: me to ask about the bill", "when I next talk about the dentist remind me
#: to ask about the bill". Several words may fit a subject; the answer says
#: back which were taken, and "cancel that" takes it back at once.
_NT_TALK = (r"(?:talk|speak|chat|ask)\s+(?:to\s+you\s+|with\s+you\s+)?about|mention|bring\s+up"
            r"|say\s+anything\s+about")
_NT_NEXT = r"(?:the\s+)?next\s+time\s+(?:i|we)\s+(?:" + _NT_TALK + r")"
_NT_WHEN = r"when(?:ever)?\s+(?:i|we)\s+next\s+(?:" + _NT_TALK + r")"
_NT_WHAT = r"(?:to|that|about|of)"
_NT_PATTERNS = (
    # "remind me next time I talk about <about> to <text>"
    re.compile(r"remind\s+me\s+(?:" + _NT_NEXT + r"|" + _NT_WHEN + r")\s+(?P<about>.+?),?\s+"
               + _NT_WHAT + r"\s+(?P<text>.+)"),
    # "remind me to <text> (the) next time I talk about <about>"
    re.compile(r"remind\s+me\s+" + _NT_WHAT + r"\s+(?P<text>.+?),?\s+(?:" + _NT_NEXT + r"|"
               + _NT_WHEN + r")\s+(?P<about>.+)"),
    # "next time I talk about <about>, remind me to <text>"
    re.compile(r"(?:" + _NT_NEXT + r"|" + _NT_WHEN + r")\s+(?P<about>.+?),?\s+remind\s+me\s+"
               + _NT_WHAT + r"\s+(?P<text>.+)"),
)
_NT_CANCEL = re.compile(
    r"(?:cancel|delete|remove|forget|drop|stop)\s+(?:the\s+|my\s+)?(?:next[\s-]time\s+)?"
    r"reminder\s+(?:for\s+next\s+time\s+)?(?:about|for|on)\s+(?P<about>.+)")
_NT_LIST = re.compile(
    r"what\s+(?:will|would|are)\s+you\s+(?:going\s+to\s+)?remind\s+me\s+(?:of|about)\s+"
    r"next\s+time|(?:what\s+are|list|show\s+me)\s+(?:my\s+)?reminders\s+for\s+next\s+time"
    r"|what\s+(?:reminders\s+)?(?:do\s+i\s+have|have\s+i\s+got)\s+for\s+next\s+time")


def _next_time(s: str) -> Optional[Intent]:
    for rx in _NT_PATTERNS:
        m = rx.fullmatch(s)
        if not m:
            continue
        about = m.group("about").strip(" ,")
        text = m.group("text").strip(" ,")
        if about and text and len(text) <= 300 and not re.fullmatch(_VAGUE, text):
            return Intent("next_time_set", {"about": about, "text": text})
    if _NT_LIST.fullmatch(s):
        return Intent("next_time_list")
    m = _NT_CANCEL.fullmatch(s)
    if m:
        return Intent("next_time_cancel", {"about": m.group("about").strip()})
    return None


#: "What's my next reminder?" (2026-10-31, the pass-9 field test). The model
#: offered to read "your device's notification history" - a phone feature this
#: PC cannot read - instead of the PC's own schedule. The answer comes from the
#: scheduler's own list, with no model, and says plainly when nothing is set.
_NEXT_UP = re.compile(
    r"(?:what(?:'s| is)|when(?:'s| is))\s+(?:my|the)\s+next\s+"
    r"(?P<kind>reminder|alarm|timer)\??"
    r"|what(?:'s| is)\s+next\s+(?:on\s+)?(?:my|the)\s+"
    r"(?:schedule|list|reminders?)\??"
    r"|what(?:'s| is)\s+coming\s+up(?:\s+next)?\??")


def _next_up(s: str) -> Optional[Intent]:
    """("next_up", the kind asked for) for "what's my next reminder?", or None."""
    m = _NEXT_UP.fullmatch(s)
    if not m:
        return None
    return Intent("next_up", {"kind": (m.groupdict().get("kind") or "").lower()})


#: "PC help" (jarvis_pc_help.py, 2026-09-28): five read-only questions about
#: this PC, answered without the model. Each must be the WHOLE sentence, so
#: "why is my PC slow to boot after the update, and should I reinstall?"
#: still goes to the model.
_PC = r"(?:my|the|this)\s+(?:pc|computer|laptop|machine|desktop)"
_GPU = r"(?:my|the)\s+(?:graphics\s+card|gpu|video\s+card)"
_DRIVE = (r"(?:my|the)\s+(?:disks?|drives?|hard\s+drives?|hard\s+disks?|ssds?|storage|"
          r"c\s+drive)")
_PC_HELP = (
    ("slow", re.compile(
        r"why\s+is\s+" + _PC + r"\s+(?:so\s+|really\s+|being\s+|running\s+)?"
        r"(?:so\s+)?(?:slow|sluggish|laggy|lagging)(?:\s+(?:today|right\s+now|now))?"
        r"|" + _PC + r"\s+(?:is|feels|seems)\s+(?:so\s+|really\s+|very\s+)?(?:running\s+)?"
        r"(?:slow|sluggish|laggy)(?:\s+(?:today|right\s+now|now))?"
        r"|what(?:'?s|\s+is)\s+slowing\s+(?:down\s+)?" + _PC + r"(?:\s+down)?"
        r"|what(?:'?s|\s+is)\s+(?:using|eating|hogging)\s+(?:all\s+)?(?:my|the)\s+"
        r"(?:cpu|processor|memory|ram)"
        r"|how\s+busy\s+is\s+(?:my|the)\s+(?:cpu|processor|pc|computer)")),
    ("disk", re.compile(
        r"how\s+full\s+(?:is|are)\s+" + _DRIVE +
        r"|how\s+much\s+(?:free\s+)?(?:disk\s+|drive\s+|storage\s+)?space\s+"
        r"(?:do\s+i\s+have|is\s+(?:there|left)|have\s+i\s+got)(?:\s+left)?"
        r"(?:\s+on\s+(?:" + _PC + r"|" + _DRIVE + r"))?"
        r"|is\s+" + _DRIVE + r"\s+(?:full|nearly\s+full|almost\s+full|running\s+out)"
        r"|am\s+i\s+running\s+(?:out|low)\s+(?:of|on)\s+(?:disk\s+|drive\s+)?"
        r"(?:space|storage)")),
    ("heat", re.compile(
        r"how\s+hot\s+is\s+" + _GPU + r"(?:\s+(?:running|getting|right\s+now|now))?"
        r"|what(?:'?s|\s+is)\s+(?:the\s+temperature\s+of\s+" + _GPU + r"|" + _GPU
        + r"(?:'s)?\s+temp(?:erature)?)"
        r"|is\s+" + _GPU + r"\s+(?:too\s+|running\s+|getting\s+)?(?:hot|overheating|warm)")),
    ("gpu", re.compile(
        r"what(?:'?s|\s+is)\s+(?:using|on|running\s+on|eating|hogging)\s+" + _GPU
        + r"(?:'s)?(?:\s+memory)?"
        r"|how\s+(?:busy|full)\s+is\s+" + _GPU + r"(?:'s\s+memory)?"
        r"|how\s+much\s+(?:of\s+)?(?:my\s+|the\s+)?(?:gpu\s+memory|vram|video\s+memory|"
        r"graphics\s+card\s+memory)\s+is\s+(?:used|in\s+use|being\s+used|free)")),
    ("restart", re.compile(
        r"when\s+did\s+" + _PC + r"\s+(?:last\s+)?(?:restart|reboot|start(?:\s+up)?|"
        r"boot(?:\s+up)?)(?:\s+last)?"
        r"|when\s+was\s+" + _PC + r"\s+last\s+(?:restarted|rebooted|started|turned\s+on)"
        r"|when\s+did\s+i\s+last\s+(?:restart|reboot|turn\s+on)\s+" + _PC +
        r"|how\s+long\s+has\s+" + _PC + r"\s+been\s+(?:on|running|up)(?:\s+for)?"
        r"|what(?:'?s|\s+is)\s+(?:my|the)\s+(?:pc's\s+|computer's\s+)?uptime"
        r"|(?:pc|computer|system)\s+uptime")),
)


def _pc_help(s: str) -> Optional[Intent]:
    for topic, rx in _PC_HELP:
        if rx.fullmatch(s):
            return Intent("pc_help", {"topic": topic})
    return None


PC_HELP_MISSING = ("Your PC's Jarvis cannot answer questions about the PC yet - run "
                   "apply-patches.ps1 on the PC.")

#: How long a PC-help answer is reused, in seconds, and how long a cold one
#: waits for the slow half (D11b, the live campaign of 2026-10-25).
#:
#: R9 ("Why is my PC slow?") was honest and right, and took 10.44 s - because
#: `jarvis_pc_help.slow_words` runs one PowerShell call that samples every
#: process twice, a second apart, and that call is the whole cost. Its own
#: cache holds the reading for 5 s, which helps a second question asked in the
#: same breath and nothing else. This is the fast lane, so two things change
#: here and NOT in that module:
#:   * the ANSWER is reused for `PC_HELP_TTL` seconds - a follow-up question
#:     (the same one again, or the disk after the processor) answers at once;
#:   * a cold answer waits only `PC_HELP_WAIT` seconds for the program list
#:     and answers with the numbers the cheap readings already have (memory is
#:     a kernel call, not a program launch), saying plainly that the program
#:     list is still being read. The list itself carries on in the background
#:     and the next ask within the minute has it.
#: Real numbers either way; never a made-up one.
PC_HELP_TTL = 120.0
PC_HELP_WAIT = 2.5
PC_HELP_STILL = ("Jarvis is still reading which programs are using the most - ask again "
                 "in a moment.")

_PC_HELP_ANSWERS: dict = {}
_PC_HELP_ANSWERS_LOCK = threading.Lock()
_PC_HELP_PROGRAMS: dict = {"at": -1e9, "value": None, "running": False}
_PC_HELP_PROGRAMS_LOCK = threading.Lock()


def _pc_help_forget() -> None:
    """Drop the cached readings (tests; and it costs nothing to be able to)."""
    with _PC_HELP_ANSWERS_LOCK:
        _PC_HELP_ANSWERS.clear()
    with _PC_HELP_PROGRAMS_LOCK:
        _PC_HELP_PROGRAMS.update(at=-1e9, value=None, running=False)


def _pc_help_programs(PCH, wait: float):
    """The program reading: the last one while it is fresh, else what can be
    had within `wait` seconds, else None (the answer says so).

    One probe at a time, in a background thread, so two questions asked at
    once do not start two PowerShell calls - and a cold answer is never held
    for the ten seconds that call takes on this PC.
    """
    stale = None
    with _PC_HELP_PROGRAMS_LOCK:
        value, at = _PC_HELP_PROGRAMS["value"], _PC_HELP_PROGRAMS["at"]
        if value is not None and time.monotonic() - at < PC_HELP_TTL:
            return value
        stale = value
        start = not _PC_HELP_PROGRAMS["running"]
        if start:
            _PC_HELP_PROGRAMS["running"] = True
    if start:
        def probe():
            got = None
            try:
                got = PCH.real_readers().programs()
            except Exception:
                got = None
            with _PC_HELP_PROGRAMS_LOCK:
                if got is not None:
                    _PC_HELP_PROGRAMS.update(at=time.monotonic(), value=got)
                _PC_HELP_PROGRAMS["running"] = False
        threading.Thread(target=probe, name="jarvis-pc-help-programs", daemon=True).start()
    deadline = time.monotonic() + max(0.0, wait)
    while time.monotonic() < deadline:
        with _PC_HELP_PROGRAMS_LOCK:
            if not _PC_HELP_PROGRAMS["running"]:
                return _PC_HELP_PROGRAMS["value"]
        time.sleep(0.02)
    return stale if stale is not None else None


def _pc_help_answer(PCH, topic: str, wait: float):
    """(the answer dict, whether the program list was missing) for one topic.

    The readers are jarvis_pc_help's own, with ONE of them replaced: the
    program list is read through `_pc_help_programs`, which is what bounds the
    wait. If that module's Readers ever stops being writable, the plain answer
    is taken instead - a slow answer is bad, a crash is worse.
    """
    readers = PCH.real_readers()
    seen = []

    def programs():
        got = _pc_help_programs(PCH, wait)
        seen.append(got)
        return got

    try:
        readers.programs = programs
    except Exception:
        return PCH.answer(topic), False
    try:
        out = PCH.answer(topic, readers)
    except Exception:
        out = {"said": "Jarvis could not read this on your PC just now.",
               "private": False, "read": []}
    missing = bool(seen) and seen[0] is None
    return out, missing


def _run_pc_help(intent: Intent) -> Result:
    """Read-only, no card: nothing changes and nothing leaves this PC. An
    answer naming programs is private (it stays on screen) and marks the
    turn as having read outside text - a program chooses its own name.

    Cached and bounded (D11b, 2026-10-25): see PC_HELP_TTL above. The answer,
    its private flag and its read mark are cached together, so a repeated
    question cannot lose the private mark.
    """
    try:
        import jarvis_pc_help as PCH
    except Exception:
        return Result(PC_HELP_MISSING, intent.name)
    topic = str(intent.f.get("topic") or "")
    key = topic or ""
    now = time.monotonic()
    with _PC_HELP_ANSWERS_LOCK:
        got = _PC_HELP_ANSWERS.get(key)
    if got is not None and now - got[0] < got[2]:
        out = got[1]
    else:
        out, missing = _pc_help_answer(PCH, topic, PC_HELP_WAIT)
        if missing and topic == "slow":
            said = str(out.get("said") or "").strip()
            if said:
                out = dict(out, said=f"{said} {PC_HELP_STILL}")
                # The program list is NOT in this answer, so it names no
                # program: the private mark and the read mark go with it.
                out["private"] = False
                out["read"] = []
        # A partial answer is kept only for a moment: once the program list
        # has arrived, the next ask must get the whole answer.
        with _PC_HELP_ANSWERS_LOCK:
            _PC_HELP_ANSWERS[key] = (time.monotonic(), out,
                                     5.0 if missing else PC_HELP_TTL)
    return Result(str(out.get("said") or ""), intent.name, private=bool(out.get("private")),
                  read=list(out.get("read") or []))


#: "Widgets you describe" (jarvis_widgets.py, 2026-09-28): the sentence must
#: START by asking for a widget, and name what it shows after that.
_WIDGET = re.compile(
    r"(?:make|create|build|design|add|set\s+up|give)\s+(?:me\s+)?(?:a|an|another|one|my)\s+"
    r"(?:new\s+|small\s+|little\s+)?(?:jarvis\s+)?widget\s+"
    r"(?:showing|that\s+shows|with|for|to\s+show|which\s+shows|of|listing|that\s+has)\s+.+")

WIDGETS_MISSING = ("Your PC's Jarvis cannot make widgets yet - run apply-patches.ps1 on the PC.")


def _run_widget(f: dict, conversation, messages) -> Result:
    """A widget PREVIEW from the owner's own words, never a widget: the
    owner sees it under Brain, Widgets and taps Add. Refused in a
    conversation that has read outside text (jarvis_widgets.chat_tainted)."""
    try:
        import jarvis_widgets as W
    except Exception:
        return Result(WIDGETS_MISSING, "widget_make")
    return Result(W.from_chat(str(f.get("words") or ""), conversation=conversation,
                              messages=messages), "widget_make")


#: "Notification styles you describe" (jarvis_notification_styles.py,
#: 2026-10-30): the sentence must be about how the notifications LOOK - a
#: "make/change/set/style/update ... notifications ... look/like" shape, or
#: "change how ... notifications look". Deliberately NOT "make my
#: notifications quieter" or "turn my notifications off": those belong to the
#: settings grammar, and a style never changes whether a notification makes a
#: sound (the channel owns that, and the approval routing owns the channel).
_STYLE = re.compile(
    r"(?:make|change|set|style|update)\s+(?:(?:my|the)\s+)?(?:jarvis\s+)?"
    r"(?:notifications?|alerts?)\s+(?:look|like|style)(?:\s+(?:like|to\s+look\s+like))?\b.*"
    r"|(?:change|set)\s+how\s+(?:(?:my|the)\s+)?(?:jarvis\s+)?(?:notifications?|alerts?)\s+look\b.*")

STYLES_MISSING = ("Your PC's Jarvis cannot style notifications yet - run apply-patches.ps1 "
                  "on the PC.")


def _run_style(f: dict, conversation, messages) -> Result:
    """A style PREVIEW from the owner's own words, never a style that is on:
    the owner sees it in Brain, Notifications and taps Add. Refused in a
    conversation that has read outside text (jarvis_widgets.chat_tainted,
    reused by jarvis_notification_styles.chat_tainted)."""
    try:
        import jarvis_notification_styles as N
    except Exception:
        return Result(STYLES_MISSING, "notify_style")
    return Result(N.from_chat(str(f.get("words") or ""), conversation=conversation,
                              messages=messages), "notify_style")


#: "Ring my phone" (jarvis_find_phone.py, 2026-09-28). A phone the owner
#: names ("ring my work phone") is kept, so the answer can say plainly that
#: Jarvis cannot tell phones apart yet. Only the owner's OWN phone: the word
#: before "phone" must be one of these, never a person ("call my mum's
#: phone", "ring my sister's mobile" - the owner means to call someone, and
#: ringing their own phone at full volume would be the wrong thing; those go
#: to the model). Bug audit 2026-09-28, F6.
_OWN_PHONE = r"(?:work|personal|other|old|new|own|second|spare|main|android)"
_RING = re.compile(
    r"(?:ring|call|buzz|beep)\s+(?:my|the)\s+(?:(?P<name>" + _OWN_PHONE + r")\s+)?"
    r"(?:phone|mobile|cell(?:\s*phone)?|android)"
    r"|(?:find|locate)\s+(?:my|the)\s+(?:(?P<name2>" + _OWN_PHONE + r")\s+)?"
    r"(?:phone|mobile|cell(?:\s*phone)?|android)"
    r"|where(?:'s|\s+is)\s+my\s+(?:(?P<name3>" + _OWN_PHONE + r")\s+)?"
    r"(?:phone|mobile|cell(?:\s*phone)?|android)"
    r"|make\s+my\s+(?:phone|mobile)\s+ring|i\s+(?:can'?t|cannot)\s+find\s+my\s+phone")
_RING_STOP = re.compile(r"stop\s+ringing(?:\s+(?:my|the)\s+(?:phone|mobile))?"
                        r"|(?:stop|silence)\s+(?:my|the)\s+phone(?:\s+ringing)?")


def _find_phone(s: str) -> Optional[Intent]:
    if _RING_STOP.fullmatch(s):
        return Intent("phone_stop")
    m = _RING.fullmatch(s)
    if not m:
        return None
    name = (m.group("name") or m.group("name2") or m.group("name3") or "").strip()
    return Intent("phone_ring", {"named": bool(name) and name not in ("own", "android")})


#: "Watch with me" (jarvis_screen.py, 2026-09-29). Whole sentences only.
_WATCH_START = (
    r"(?:start\s+|begin\s+)?watch(?:ing)?\s+with\s+me(?:\s+(?:for|of)\s+(?P<d>.+))?",
    r"(?:start|begin|turn\s+on|switch\s+on)\s+watch(?:ing)?\s+with\s+me(?:\s+(?:for|of)\s+(?P<d2>.+))?",
    r"(?:start|begin)\s+watching\s+(?:my\s+)?screen(?:\s+(?:for|of)\s+(?P<d3>.+))?",
    r"watch\s+(?:my\s+)?screen\s+with\s+me(?:\s+(?:for|of)\s+(?P<d4>.+))?",
    r"watch\s+along(?:\s+with\s+me)?(?:\s+(?:for|of)\s+(?P<d5>.+))?",
)
_WATCH_STOP = re.compile(
    r"(?:stop|end|quit|cancel)\s+watch(?:ing)?\s+with\s+me"
    r"|stop\s+watching(?:\s+(?:my\s+)?screen)?(?:\s+(?:now|please))?"
    r"|(?:turn|switch)\s+off\s+watch(?:ing)?\s+with\s+me"
    r"|stop\s+looking\s+at\s+my\s+screen")
_WATCH_MORE = re.compile(
    r"(?:keep\s+)?watch(?:ing)?\s+(?:(?:for|another)\s+)?(?P<d>.+?)\s+more"
    r"|(?:keep\s+)?watch(?:ing)?\s+(?:for\s+)?(?:another|a\s+bit\s+longer|a\s+while\s+longer|longer)"
    r"(?:\s+(?P<d2>.+))?"
    r"|watch\s+(?:a\s+)?(?:bit|little)\s+longer")
_WATCH_MORE_N = re.compile(
    r"(?:keep\s+)?watch(?:ing)?\s+(?:(?:for|another)\s+)?(?P<n>\d{1,3})\s+more"
    r"\s+(?P<u>minutes?|mins?|hours?)")
_WATCH_ASK = re.compile(r"(?:are\s+you|is\s+jarvis)\s+watching(?:\s+(?:me|my\s+screen))?"
                        r"|is\s+watch\s+with\s+me\s+on")


def _watch_minutes(d) -> Optional[float]:
    """Minutes from "20 minutes", "an hour", "half an hour" - or a bare
    "20"; None when it is not a length of time."""
    if d is None:
        return None
    secs = parse_duration(d)
    if secs is None and re.fullmatch(r"\d{1,3}", d.strip()):
        secs = float(d.strip()) * 60
    return None if secs is None else max(1.0, secs / 60.0)


def _watch(s: str) -> Optional[Intent]:
    if _WATCH_STOP.fullmatch(s):
        return Intent("screen_stop")
    if _WATCH_ASK.fullmatch(s):
        return Intent("screen_status")
    m = _WATCH_MORE_N.fullmatch(s)
    if m:
        n = float(m.group("n")) * (60 if m.group("u").startswith("h") else 1)
        return Intent("screen_more", {"minutes": n})
    m = _WATCH_MORE.fullmatch(s)
    if m:
        d = m.groupdict().get("d") or m.groupdict().get("d2")
        mins = _watch_minutes(d)
        if d and mins is None:
            return None
        return Intent("screen_more", {"minutes": mins})
    for pat in _WATCH_START:
        m = re.fullmatch(pat, s)
        if m:
            d = next((v for k, v in m.groupdict().items() if k.startswith("d") and v), None)
            mins = _watch_minutes(d)
            if d and mins is None:
                return None           # "watch with me for a bit" goes to the model
            return Intent("screen_start", {"minutes": mins})
    return None


#: Lockdown (jarvis_asks_first.py, 2026-09-28).
_LOCKDOWN_ON = re.compile(
    r"lock\s*down(?:\s+(?:now|jarvis|everything|the\s+pc|mode))?"
    r"|(?:turn|switch|put)\s+on\s+lock\s*down(?:\s+mode)?|(?:turn|switch)\s+lock\s*down\s+on"
    r"|(?:go|get)\s+(?:into|in)\s+lock\s*down|enter\s+lock\s*down|lock\s+(?:it|everything)\s+down"
    r"|(?:start|enable)\s+lock\s*down")
_LOCKDOWN_OFF = re.compile(
    r"(?:turn|switch)\s+off\s+lock\s*down(?:\s+mode)?|(?:turn|switch)\s+lock\s*down\s+off"
    r"|(?:end|stop|undo|lift|cancel|leave|exit|disable)\s+(?:the\s+)?lock\s*down")
_LOCKDOWN_ASK = re.compile(r"(?:is|are\s+we\s+in)\s+lock\s*down(?:\s+(?:on|mode\s+on))?"
                           r"|is\s+jarvis\s+(?:in\s+)?lock(?:ed)?\s*down")


def _lockdown(s: str) -> Optional[Intent]:
    if _LOCKDOWN_ASK.fullmatch(s):
        return Intent("lockdown_status")
    if _LOCKDOWN_OFF.fullmatch(s):
        return Intent("lockdown_off")
    if _LOCKDOWN_ON.fullmatch(s):
        return Intent("lockdown_on")
    return None


#: Today cards (jarvis_today.py, 2026-09-28): "show gym bag on my Today page
#: on Mondays and Wednesdays at 7", "put 'bins out' on my today page on
#: Thursday evenings", "add a today card saying water the plants every day at
#: 8". No card - like a plain repeating reminder. "What's on my Today page?"
#: lists them; "remove gym bag from my Today page" deletes ONE. "On Monday"
#: means every Monday here: a Today card always repeats.
_TD_PAGE = r"(?:my|the)\s+today\s+(?:page|screen|cards?)"
_TD_VERB = r"(?:show|put|add|pin|stick)"
_TD_WHEN = r"(?:on|every|each|daily|weekdays?|(?:" + _WD + r")s?)\b.*"
_TD_PATTERNS = (
    # "show <text> <when> on my today page"
    re.compile(_TD_VERB + r"\s+(?P<text>.+?)\s+(?P<when>" + _TD_WHEN + r"?)\s+(?:on|to|in)\s+"
               + _TD_PAGE),
    # "show <text> on my today page <when>"
    re.compile(_TD_VERB + r"\s+(?P<text>.+?)\s+(?:on|to|in)\s+" + _TD_PAGE
               + r"(?:,?\s+(?P<when>.+))?"),
    # "add a today card (saying|for|that says) <text> <when>"
    re.compile(r"(?:add|make|create|set\s+up|put\s+up)\s+(?:a\s+|another\s+)?today\s+card"
               r"\s*(?:saying|for|that\s+says|reading|:)?\s+(?P<text>.+?)(?:,?\s+(?P<when>"
               + _TD_WHEN + r"))?"),
)
_TD_LIST = re.compile(
    r"(?:what'?s|what\s+is|whats|what\s+are)\s+(?:on\s+)?" + _TD_PAGE
    + r"|(?:list|read|tell\s+me|show(?:\s+me)?|open)\s+" + _TD_PAGE
    + r"|what\s+(?:cards\s+)?(?:do\s+i\s+have|have\s+i\s+got)\s+on\s+" + _TD_PAGE)
_TD_REMOVE = re.compile(
    r"(?:remove|delete|take|drop|clear)\s+(?:the\s+card\s+)?(?P<text>.+?)\s+(?:from|off)\s+"
    + _TD_PAGE)
_TD_DAYS_ONLY = re.compile(
    r"(?:on\s+|every\s+|each\s+)?(?P<days>(?:(?:" + _WD + r")s?)(?:(?:\s*,\s*|\s+and\s+)(?:"
    + _WD + r")s?)*|day|weekdays?|work\s*days?|daily)(?:\s+(?P<part>morning|afternoon|evening|"
    r"night))?")


def today_when(when_s: str, now: float) -> Optional[dict]:
    """A Today card's repeat from words, or None when it is not one.
    "on Mondays at 7", "on monday and wednesday at 7am", "every weekday at
    6pm", "thursday evenings" (18:00 - the same default a reminder uses),
    "every day at 8". A card always repeats, so "on Monday" is every Monday."""
    s = when_s.strip().strip(",")
    s = re.sub(r"\b(morning|afternoon|evening|night)s\b", r"\1", s)
    m = _TD_DAYS_ONLY.fullmatch(s)
    if m:
        days_s, part = m.group("days"), m.group("part")
        at = f"{DEFAULT_HOUR.get(part, 9):02d}:00"
        if days_s in ("day", "daily"):
            return {"every": "day", "at": at}
        if days_s.startswith(("weekday", "work")):
            return {"every": "weekday", "at": at}
        days = sorted({_WEEKDAYS.index(w if w in _WEEKDAYS else w[:-1])
                       for w in re.findall(r"(?:" + _WD + r")s?", days_s)})
        return {"every": "week", "at": at, "days": days} if days else None
    s = re.sub(r"^(?:on|each)\s+", "every ", s)
    if re.match(r"(?:" + _WD + r")", s):
        s = "every " + s
    when = parse_when(s, now, "reminder")
    if when is None or not isinstance(when.rule, dict):
        return None
    if when.rule.get("every") not in ("day", "weekday", "week"):
        return None
    return when.rule


def _today(s: str, now: float) -> Optional[Intent]:
    if _TD_LIST.fullmatch(s):
        return Intent("today_list")
    m = _TD_REMOVE.fullmatch(s)
    if m:
        return Intent("today_remove", {"text": m.group("text").strip()})
    unclear = None
    for rx in _TD_PATTERNS:
        m = rx.fullmatch(s)
        if not m:
            continue
        text = (m.group("text") or "").strip(" ,:")
        if not text or re.fullmatch(_VAGUE, text) or len(text) > 300:
            continue
        when_s = (m.group("when") or "").strip()
        if not when_s:
            return Intent("today_set", {"text": text, "rule": None})
        rule = today_when(when_s, now)
        if rule is not None:
            return Intent("today_set", {"text": text, "rule": rule})
        # About the Today page, but not a time it can show at ("every 2
        # hours", "tomorrow at 7"): said so, rather than handed to the model.
        unclear = unclear or Intent("today_set", {"text": text, "rule": None, "bad": True})
    return unclear


TODAY_MISSING = ("Your PC's Jarvis cannot do Today cards yet - run apply-patches.ps1 on the "
                 "PC.")


def _run_today(intent: Intent, sched) -> Optional[Result]:
    n, f = intent.name, intent.f
    try:
        import jarvis_today as T
    except Exception:
        return Result(TODAY_MISSING, n)
    if n == "today_set":
        if f.get("rule") is None:
            return Result(T.BAD_RULE if f.get("bad") else T.NO_WHEN, n)
        try:
            j = T.add(f["text"], f["rule"], sched=sched, source="quick")
        except (ValueError, OverflowError) as exc:
            return Result(T.said_of(exc), n)
        if j.get("already"):
            return Result(T.ALREADY, n, [j["id"]])
        return Result(T.set_words(j, sched.now()), n, [j["id"]], made=[j["id"]],
                      what="the Today card just set", nouns=("card",))
    if n == "today_list":
        items = T.cards(sched=sched)
        if not items:
            return Result(T.NONE_SET, n)
        words = [f"“{i['text']}”, {i['shows']}" for i in items[:5]]
        head = ("One card on your Today page: " if len(items) == 1
                else f"{len(items)} cards on your Today page: ")
        more = f" And {len(items) - 5} more under Coming up." if len(items) > 5 else ""
        return Result(head + "; ".join(words) + "." + more, n, [i["id"] for i in items[:5]],
                      private=True)
    ok, said = T.remove(f["text"], sched=sched)
    return Result(said, n)


NEXT_TIME_MISSING = ("Your PC's Jarvis cannot do reminders for next time yet - run "
                     "apply-patches.ps1 on the PC.")
FIND_PHONE_MISSING = ("Your PC's Jarvis cannot ring your phone yet - run apply-patches.ps1 on "
                      "the PC.")
LOCKDOWN_MISSING = ("Your PC's Jarvis does not have Lockdown yet - run apply-patches.ps1 on "
                    "the PC.")


def _run_next_time(intent: Intent, sched) -> Optional[Result]:
    n, f = intent.name, intent.f
    try:
        import jarvis_next_time as NT
    except Exception:
        return Result(NEXT_TIME_MISSING, n)
    import jarvis_schedule as S
    if n == "next_time_set":
        try:
            j = NT.add(f["about"], f["text"], sched=sched, source="quick")
        except (ValueError, OverflowError) as exc:
            return Result(S._sentence(exc), n)
        if j.get("already"):
            return Result(NT.ALREADY, n, [j["id"]])
        return Result(NT.set_words(j), n, [j["id"]], made=[j["id"]],
                      what="the reminder for next time just set", nouns=("reminder",))
    if n == "next_time_list":
        items = NT.waiting(sched=sched)
        if not items:
            return Result(NT.NONE_SET, n)
        words = [f"when you talk about \u201c{i['about']}\u201d: \u201c{i['text']}\u201d"
                 for i in items[:5]]
        head = ("One reminder for next time - " if len(items) == 1
                else f"{len(items)} reminders for next time - ")
        more = f" And {len(items) - 5} more under Coming up." if len(items) > 5 else ""
        return Result(head + "; ".join(words) + "." + more, n, [i["id"] for i in items[:5]],
                      private=True)
    if not NT.waiting(sched=sched):
        # No reminder for next time at all: "delete the reminder about the
        # dentist" is about something else - the model answers, as before.
        return None
    ok, said = NT.cancel(f["about"], sched=sched)
    return Result(said, n)


NEXT_UP_MISSING = ("I cannot read your schedule on this PC just now.")
NEXT_UP_NOTHING = "Nothing is scheduled on this PC."


def _run_next_up(intent: Intent, sched) -> Result:
    """"What's my next reminder?" - the scheduler's own list, no model."""
    n = "next_up"
    kind = str(intent.f.get("kind") or "").lower()
    try:
        jobs = sched.listed() if sched is not None else []
    except Exception:
        return Result(NEXT_UP_MISSING, n)
    items = [j for j in jobs if isinstance(j, dict)]
    if kind:
        items = [j for j in items if str(j.get("kind") or "").lower() == kind]
    else:
        items = [j for j in items
                 if str(j.get("kind") or "").lower() in ("reminder", "alarm", "timer")]
    if not items:
        said = f"No {kind} is set on this PC." if kind else NEXT_UP_NOTHING
        return Result(said, n, private=True)
    item = items[0]
    text = str(item.get("text") or "").strip()
    when = str(item.get("when") or "").strip()
    label = str(item.get("kind") or "item")
    if text and when:
        said = f'Your next {label} is "{text}" {when}.'
    elif text:
        said = f'Your next {label} is "{text}".'
    elif when:
        said = f"Your next {label} is {when}."
    else:
        said = f"Your next {label} has no time I can read."
    return Result(said, n, private=True)


def _run_find_phone(intent: Intent) -> Result:
    n = intent.name
    try:
        import jarvis_find_phone as FP
    except Exception:
        return Result(FIND_PHONE_MISSING, n)
    out = FP.stop() if n == "phone_stop" else FP.ring(named=bool(intent.f.get("named")))
    return Result(str(out.get("said") or ""), n)


SCREEN_MISSING = ("This PC's Jarvis is missing this feature. In PowerShell on the PC, in the "
                  "Jarvis folder, run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis.")
SCREEN_PC_ONLY = ("Watch with me looks at this PC's screen, so it can only be started, extended "
                  "or asked about from this PC.")


def _run_screen(intent: Intent, peer, local) -> Result:
    """"Watch with me" by voice or typing: jarvis_screen's one engine, at
    once, no card. Only from this PC - it is this PC's screen (stopping is
    allowed from anywhere: it only makes Jarvis look less)."""
    n, f = intent.name, intent.f
    try:
        import jarvis_screen as SC
    except Exception:
        return Result(SCREEN_MISSING, n)
    e = SC.ENGINE
    if n == "screen_stop":
        out = e.stop("owner")
        return Result("I've stopped watching." if out.get("stopped")
                      else "I wasn't watching.", n)
    if not SC.is_local(peer, local):
        return Result(SCREEN_PC_ONLY, n)
    st = e.status()
    if n == "screen_status":
        if not st["on"]:
            return Result("No, I'm not watching. Say \"watch with me\" to start.", n)
        mins = max(1, int(round((st["left_s"] or 0) / 60)))
        now_ = (f"Yes - paused for now: {st['pause_words']}." if st["paused"]
                else "Yes, I'm watching.")
        return Result(f"{now_} About {mins} minute{'s' if mins != 1 else ''} left.", n)
    if n == "screen_more":
        out = e.extend(f.get("minutes"))
        if not out.get("ok"):
            return Result(str(out.get("error") or "I'm not watching right now."), n)
        mins = max(1, int(round((out["status"]["left_s"] or 0) / 60)))
        return Result(f"Done - about {mins} minutes left.", n)
    if not e.built():
        return Result(SC.not_built_words(), n)
    out = e.start(f.get("minutes"))
    if not out.get("ok"):
        return Result(str(out.get("error") or "I couldn't start watching."), n)
    mins = max(1, int(round((out["status"]["left_s"] or 0) / 60)))
    return Result(f"Watching with you for {mins} minutes. There is a sign on screen the whole "
                  "time, and \"stop watching\" ends it. Ask me about your screen whenever you "
                  "like.", n)


def _run_lockdown(intent: Intent, peer, local) -> Result:
    n = intent.name
    try:
        import jarvis_asks_first as AF
        AF.request_lockdown
    except Exception:
        return Result(LOCKDOWN_MISSING, n)
    if n == "lockdown_status":
        return Result(AF.LOCKDOWN_ON_SAYS if AF.lockdown_on() else AF.LOCKDOWN_OFF_SAYS, n)
    # The same route both apps' Lockdown button uses: on at once; off from
    # this PC only, with ONE card plus Windows Hello.
    code, out = AF.request_tier({"action": AF.LOCKDOWN, "ask": n == "lockdown_on"},
                                peer=peer, local=local)
    said = str(out.get("message") or out.get("error") or "")
    if said and not said.endswith("."):
        said += "."
    return Result(said, n)


#: "Tell me when ..." (jarvis_tellme.py, the owner's decision of 2026-09-25):
#: an email from a named sender, or a Home Assistant device doing something.
#: Whole sentences only, like everything here: "tell me when you're ready"
#: or "let me know when it's done" go to the model.
_TELL = re.compile(
    r"(?P<urg>urgently\s+)?(?:tell\s+me|let\s+me\s+know|notify\s+me|alert\s+me|ping\s+me"
    r"|warn\s+me|give\s+me\s+a\s+shout)(?P<urg2>\s+urgently)?\s+(?:(?P<every>every\s+time"
    r"|each\s+time|whenever)|when|as\s+soon\s+as|once|if)\s+(?P<what>.+)")
_URGENT_TAIL = re.compile(
    r"[\s,.;-]+(?:and\s+)?(?:(?:it'?s|it\s+is|make\s+it|mark\s+it)\s+urgent|urgently|urgent"
    r"|(?:and\s+)?keep\s+ringing(?:\s+until\s+i\s+(?:see|look\s+at)\s+it)?)$")
_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fourteen": 14,
         "thirty": 30}
_FOR_TAIL = re.compile(
    r"[\s,]+(?:for\s+(?:the\s+next\s+|the\s+)?(?P<n>\d{1,3}|a|an|one|two|three|four|five|six"
    r"|seven|eight|nine|ten|twelve|fourteen|thirty)\s+(?P<u>minutes?|hours?|days?|weeks?)"
    r"|(?P<today>today|tonight|for\s+today))$")
_MAIL = r"(?:e-?mail|mail)"
_MAIL_WHAT = (
    re.compile(r"(?:i\s+(?:get|receive|have)\s+)?(?:an?\s+|any\s+)?(?:new\s+)?" + _MAIL
               + r"s?\s+(?:from|by)\s+(?P<who>.+?)(?:\s+(?:arrives|comes\s+in|comes|gets\s+here"
               r"|lands|shows\s+up|is\s+here|turns\s+up|appears|is\s+in))?"),
    re.compile(r"(?P<who>.+?)\s+(?:emails|e-mails|mails|writes\s+to|replies\s+to)\s+me"),
)
#: What a device may do, and how jarvis_tellme names it.
_DEV_VERBS = (
    (r"finishes|has\s+finished|is\s+(?:done|finished)|stops|has\s+stopped", {"say": "finishes"}),
    (r"opens|is\s+opened|is\s+open|gets\s+opened", {"say": "opens"}),
    (r"closes|is\s+closed|gets\s+closed", {"say": "closes"}),
    (r"turns\s+on|switches\s+on|starts", {"say": "turns on"}),
    (r"turns\s+off|switches\s+off", {"say": "turns off"}),
    (r"is\s+(?:turned\s+|switched\s+)?on", {"states": ["on"]}),
    (r"is\s+(?:turned\s+|switched\s+)?off", {"states": ["off"]}),
)
_DEV = re.compile(r"(?:the\s+|my\s+|our\s+)?(?P<dev>[a-z0-9][a-z0-9 ._'-]{0,59}?)\s+(?P<verb>"
                  + "|".join(f"(?:{p})" for p, _ in _DEV_VERBS) + r")")
_ENTITY_STATE = re.compile(r"(?P<dev>[a-z0-9_]+\.[a-z0-9_]+)\s+(?:is|becomes|reaches|goes\s+to"
                           r"|changes\s+to|turns|is\s+now)\s+(?P<st>[a-z0-9_]{1,30})")
#: "Tell me when this page changes" (jarvis_tellme.py "page" source, I67):
#: only a literal address the owner typed - "tell me when it changes" (no
#: address) goes to the model, since Jarvis has no page in mind for "it".
_PAGE_CHANGE = re.compile(r"(?P<url>https?://\S+?)\s+changes?")
#: Watches, 2026-09-28 (jarvis_tellme.py "price", "search" and "github").
#: "tell me when the price on <url> drops below 25" - a literal address and
#: a number, like the page watch above.
_PRICE_NUM = r"(?P<cur>[£$€])?\s?(?P<num>\d[\d,.]*)(?:\s*(?:pounds?|dollars?|euros?|quid|bucks))?"
_PRICE_DROP = re.compile(
    r"(?:the\s+)?price\s+(?:on|of|at|for)\s+(?P<url>https?://\S+?)\s+(?:drops|falls|goes|gets"
    r"|is|comes\s+down)\s+(?:below|under|beneath|less\s+than)\s+" + _PRICE_NUM
    + r"|(?P<url2>https?://\S+?)\s+(?:drops|falls|goes|is)\s+(?:below|under|less\s+than)\s+"
    + _PRICE_NUM.replace("?P<cur>", "?P<cur2>").replace("?P<num>", "?P<num2>"))
#: "tell me when a search for <words> shows something new", "... when
#: there's something new about <words>".
_SEARCH_NEW = re.compile(
    r"(?:a\s+|the\s+|my\s+)?(?:web\s+|google\s+|internet\s+)?search\s+(?:for\s+|on\s+)?"
    r"(?P<q>.+?)\s+(?:shows|finds|has|turns\s+up|brings\s+up|gets)\s+(?:something|anything"
    r"|a\s+new\s+result|new\s+results)(?:\s+new)?"
    r"|there'?s\s+(?:something|anything)\s+new\s+(?:online\s+|on\s+the\s+web\s+)?"
    r"(?:about|for|on)\s+(?P<q2>.+)"
    r"|(?:there\s+are\s+)?new\s+(?:search\s+|web\s+)?results\s+(?:for|about)\s+(?P<q3>.+)")
#: "... searching once a day / every 12 hours / every week" after it.
_SEARCH_EVERY = re.compile(
    r"[\s,]+(?:(?:checking|looking|searching)\s+)?(?:(?P<daily>once\s+a\s+day|daily|every\s+day)"
    r"|(?P<weekly>once\s+a\s+week|weekly|every\s+week)|(?P<twice>twice\s+a\s+day)"
    r"|every\s+(?P<n>\d{1,3}|six|twelve|two|three)\s+(?P<u>hours?|days?))$")
_REPO_WORDS = r"(?P<repo>[a-z0-9][a-z0-9-]{0,38}/[a-z0-9_.-]{1,100})"
#: "tell me when CI fails on owner/repo", "... CI finishes on owner/repo main",
#: "... the build on owner/repo (branch dev) fails".
_CI_VERB = (r"(?P<verb>finishes|is\s+(?:done|finished)|completes|has\s+finished|fails"
            r"|has\s+failed|breaks|goes\s+red|is\s+red)")
_CI_WHAT = r"(?:the\s+)?(?:ci|build|builds|checks|tests|github\s+actions|actions)"
_BR = r"[a-z0-9._/-]{1,100}"


def _ci_branch(a: str, b: str, c: str) -> str:
    """An optional branch after the repository: "branch dev", "dev branch",
    "on dev", or just "dev" - three group names, one per shape."""
    return (rf"(?:\s+(?:on\s+|for\s+)?(?:the\s+)?(?:branch\s+(?P<{a}>{_BR})"
            rf"|(?P<{b}>{_BR})\s+branch|(?P<{c}>{_BR})))?")


_CI = re.compile(
    _CI_WHAT + r"\s+" + _CI_VERB + r"\s+(?:on|for|in)\s+" + _REPO_WORDS
    + _ci_branch("br", "br2", "br3")
    + r"|" + _CI_WHAT + r"\s+(?:on|for|in)\s+" + _REPO_WORDS.replace("?P<repo>", "?P<repo2>")
    + _ci_branch("br4", "br5", "br6") + r"\s+" + _CI_VERB.replace("?P<verb>", "?P<verb2>"))
#: "tell me when PR #12 on owner/repo merges", "... https://github.com/o/r/pull/12 is merged".
_PR_MERGED = r"(?:is\s+merged|merges|gets\s+merged|has\s+been\s+merged|is\s+in)"
_PR = re.compile(
    r"(?:pr|pull\s+request)\s*#?(?P<n>\d{1,7})\s+(?:on|in|for)\s+" + _REPO_WORDS + r"\s+"
    + _PR_MERGED
    + r"|https?://(?:www\.)?github\.com/" + _REPO_WORDS.replace("?P<repo>", "?P<repo2>")
    + r"/pull/(?P<n2>\d{1,7})/?\s+" + _PR_MERGED
    + r"|(?:pr|pull\s+request)\s*#?(?P<n3>\d{1,7})\s+" + _PR_MERGED)
#: Not a device - and not a sender: "tell me when it's done" is the model's.
_NOT_A_THING = frozenset(("it", "this", "that", "they", "you", "he", "she", "we", "something",
                          "timer", "alarm", "reminder", "everything", "anything", "one",
                          "things", "jarvis", "the timer", "my timer", "the alarm"))
_ANYONE = frozenset(("anyone", "anybody", "someone", "somebody", "everyone", "them", "him",
                     "her", "it", "people"))


#: "Tell me if Alex hasn't replied by Friday" (jarvis_tellme.py, I69): the same
#: From-line match, told when NO email has come by a time.
_NO_REPLY = re.compile(
    r"(?:(?P<who>.+?)\s+(?:hasn'?t|has\s+not|haven'?t|have\s+not|doesn'?t|does\s+not"
    r"|didn'?t|did\s+not)\s+(?:replied|reply|written|write|emailed|email|e-mailed|answered"
    r"|responded|respond|got\s+back\s+to\s+me|get\s+back\s+to\s+me)(?:\s+(?:to\s+me|back))?"
    r"|there'?s\s+(?:still\s+)?no\s+(?:e-?mail|reply|answer)\s+from\s+(?P<who2>.+?)"
    r"|(?:i\s+)?(?:don'?t|do\s+not|haven'?t|have\s+not)\s+(?:get|got|had|hear|heard)"
    r"\s+(?:an?\s+)?(?:e-?mail\s+|reply\s+|back\s+)?from\s+(?P<who3>.+?))"
    r"\s+(?P<by>(?:by|before|within|in)\s+.+)")


def _deadline(s: str, now: float) -> Optional[float]:
    """"by Friday" -> Friday at 17:00 (no clock said: the end of a working
    day - the answer and the card say the time, so it can be put right);
    "by tomorrow at 9" -> then; "within 2 days" / "in 3 hours" -> that long
    from now. None when it is not a time to come."""
    s = s.strip()
    m = re.fullmatch(r"(?:within|in)\s+(?:the\s+next\s+)?(.+)", s)
    if m:
        dm = re.fullmatch(r"(\d{1,3}|a|an|one|two|three|four|five|six|seven|ten|fourteen)\s+"
                          r"(days?|weeks?)", m.group(1))
        if dm:
            n = int(dm.group(1)) if dm.group(1).isdigit() else _NUMS.get(dm.group(1), 1)
            return now + n * (7 * 86400 if dm.group(2).startswith("week") else 86400)
        d = parse_duration(m.group(1))
        return now + d if d else None
    m = re.fullmatch(r"(?:by|before)\s+(?:(?:the\s+)?end\s+of\s+)?(.+)", s)
    if not m:
        return None
    when = parse_when(m.group(1), now, "reminder")
    if when is None or when.at is None or when.rule is not None:
        return None
    at = when.at
    if when.default_time:
        lt = time.localtime(at)
        if lt.tm_hour == DEFAULT_HOUR[None]:
            import jarvis_schedule as S
            at = S.wall_to_epoch(lt.tm_year, lt.tm_mon, lt.tm_mday, NO_REPLY_HOUR, 0)
    return at if at > now else None


#: "By Friday", with no time said: the end of the working day.
NO_REPLY_HOUR = 17


def _tellme(s: str, original, now: float) -> Optional[Intent]:
    m = _TELL.fullmatch(s)
    if not m:
        return None
    what = m.group("what").strip()
    urgent = bool(m.group("urg") or m.group("urg2"))
    once = not m.group("every")
    # "tell me if Alex hasn't replied by Friday" (jarvis_tellme, I69) - before
    # the tails below, so "by tonight" is its time, not "for today".
    probe, probe_urgent = what, urgent
    u = _URGENT_TAIL.search(probe)
    if u:
        probe, probe_urgent = probe[:u.start()].strip(), True
    mm = _NO_REPLY.fullmatch(probe)
    if mm:
        who = (mm.group("who") or mm.group("who2") or mm.group("who3") or "").strip()
        if who in _ANYONE or not who:
            return Intent("tellme_help", {"why": "who"})
        by = _deadline(mm.group("by"), now)
        if by is None:
            return Intent("tellme_help", {"why": "when"})
        return Intent("tellme_noreply", {"urgent": probe_urgent, "once": True, "ends": None,
                                         "who": _restore(original, who), "by": by})
    ends = None
    for _ in range(3):
        u = _URGENT_TAIL.search(what)
        if u:
            urgent = True
            what = what[:u.start()].strip()
            continue
        d = _FOR_TAIL.search(what)
        if d:
            if d.group("today"):
                lt = time.localtime(now)
                import jarvis_schedule as S
                y, mo, dd = S._add_days(lt.tm_year, lt.tm_mon, lt.tm_mday, 1)
                ends = S.wall_to_epoch(y, mo, dd, 0, 0)
            else:
                n = d.group("n")
                n = int(n) if n.isdigit() else _NUMS.get(n, 1)
                unit = d.group("u").rstrip("s")
                ends = now + n * {"minute": 60, "hour": 3600, "day": 86400,
                                  "week": 7 * 86400}[unit]
            what = what[:d.start()].strip()
            continue
        break
    f = {"urgent": urgent, "once": once, "ends": ends}
    got = _tellme_watches(what, original, f)
    if got is not None:
        return got
    for rx in _MAIL_WHAT:
        mm = rx.fullmatch(what)
        if mm:
            who = mm.group("who").strip()
            if who in _ANYONE or not who:
                return Intent("tellme_help", {"why": "who"})
            return Intent("tellme_email", dict(f, who=_restore(original, who)))
    mm = _PAGE_CHANGE.fullmatch(what)
    if mm:
        return Intent("tellme_page", dict(f, url=_restore(original, mm.group("url"))))
    mm = _ENTITY_STATE.fullmatch(what)
    if mm:
        return Intent("tellme_home", dict(f, entity=mm.group("dev"), name="",
                                          states=[mm.group("st")]))
    mm = _DEV.fullmatch(what)
    if mm:
        dev = mm.group("dev").strip()
        if dev in _NOT_A_THING or re.search(r"\b(?:e-?mail|mail|message|text)\b", dev):
            return None
        verb = mm.group("verb")
        how = next(h for p, h in _DEV_VERBS if re.fullmatch(p, verb))
        if re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", dev):
            return Intent("tellme_home", dict(f, entity=dev, name="", **how))
        # "tell me when the shop opens" is as often a QUESTION as a request:
        # with these verbs, a name that is no Home Assistant device goes to
        # the model instead of being told "no such device".
        ambiguous = bool(re.search(r"open|close|start|stop", verb))
        return Intent("tellme_home", dict(f, entity="", name=dev, ambiguous=ambiguous, **how))
    return None


def _tellme_watches(what: str, original, f: dict) -> Optional[Intent]:
    """The 2026-09-28 watches: a price, a web search, GitHub CI or a pull
    request. Checked before email and devices: "the build on owner/repo
    finishes" is not a Home Assistant device."""
    mm = _PRICE_DROP.fullmatch(what)
    if mm:
        url = mm.group("url") or mm.group("url2")
        num = mm.group("num") or mm.group("num2")
        cur = mm.group("cur") or mm.group("cur2") or ""
        return Intent("tellme_price", dict(f, url=_restore(original, url),
                                           below=num.rstrip(".,"), currency=cur))
    minutes = None
    probe = what
    e = _SEARCH_EVERY.search(probe)
    if e:
        if e.group("daily"):
            minutes = 1440
        elif e.group("weekly"):
            minutes = 7 * 1440
        elif e.group("twice"):
            minutes = 720
        else:
            n = e.group("n")
            n = int(n) if n.isdigit() else {"six": 6, "twelve": 12, "two": 2, "three": 3}[n]
            minutes = n * (1440 if e.group("u").startswith("day") else 60)
        probe = probe[:e.start()].strip()
    mm = _SEARCH_NEW.fullmatch(probe)
    if mm:
        q = (mm.group("q") or mm.group("q2") or mm.group("q3") or "").strip()
        q = q.strip(" \"'“”")
        if not q or q in _NOT_A_THING:
            return Intent("tellme_help", {"why": "search"})
        return Intent("tellme_search", dict(f, words=_restore(original, q), minutes=minutes))
    mm = _CI.fullmatch(what)
    if mm:
        repo = mm.group("repo") or mm.group("repo2")
        branch = next((mm.group(g) for g in ("br", "br2", "br3", "br4", "br5", "br6")
                       if mm.group(g)), "")
        verb = mm.group("verb") or mm.group("verb2")
        event = "ci_failed" if re.search(r"fail|break|red", verb) else "ci_done"
        return Intent("tellme_github", dict(f, repo=_restore(original, repo), event=event,
                                            branch=_restore(original, branch) if branch else ""))
    mm = _PR.fullmatch(what)
    if mm:
        if mm.group("n3"):
            return Intent("tellme_help", {"why": "repo"})
        repo = mm.group("repo") or mm.group("repo2")
        return Intent("tellme_github", dict(f, repo=_restore(original, repo), event="pr_merged",
                                            pr=int(mm.group("n") or mm.group("n2"))))
    return None


TELLME_MISSING = ("Your PC's Jarvis cannot do \"tell me when\" yet - run apply-patches.ps1 "
                  "on the PC.")


def _run_tellme(intent: Intent, sched, now: float) -> Result:
    """"Tell me when ...": ONE approval card, raised by the scheduler. A
    device named in words ("the washing machine") is looked up first: one
    read of each of a few likely Home Assistant names, through the gate like
    any read - never a list of the whole house."""
    import jarvis_schedule as S
    n, f = intent.name, intent.f
    if n == "tellme_help":
        if f.get("why") == "when":
            return Result("Say by when, like \"tell me if Alex hasn't replied by Friday\" or "
                          "\"... within 2 days\".", n)
        if f.get("why") == "search":
            return Result("Say what to search for, like \"tell me when a search for Kokoro "
                          "voices shows something new\".", n)
        if f.get("why") == "repo":
            return Result("Say which repository the pull request is on, like \"tell me when "
                          "PR #12 on darknight11ish/Epic-Jarvis merges\".", n)
        return Result("Say who the email is from, like \"tell me when an email from Alex "
                      "arrives\".", n)
    try:
        import jarvis_tellme as TM
    except Exception:
        return Result(TELLME_MISSING, n)
    read = []
    if n == "tellme_noreply":
        watch = {"source": "email", "sender": f["who"], "urgent": f["urgent"],
                 "missing": True, "by": f["by"]}
        try:
            j = TM.add(watch, source="quick", sched=sched)
        except (ValueError, OverflowError) as exc:
            return Result(S._sentence(exc), n)
        urgent = " It is marked urgent: your phone rings until you look." if f["urgent"] else ""
        return Result(f"That needs your yes on the approval card, which shows exactly what is "
                      f"watched. Then Jarvis tells you if no email from them has arrived by "
                      f"{S.long_date(f['by'])}, and says nothing if one does.{urgent}", n,
                      [j["id"]])
    if n == "tellme_email":
        watch = {"source": "email", "sender": f["who"], "urgent": f["urgent"],
                 "once": f["once"]}
    elif n == "tellme_page":
        watch = {"source": "page", "url": f["url"], "urgent": f["urgent"], "once": f["once"]}
    elif n == "tellme_price":
        watch = {"source": "price", "url": f["url"], "below": f["below"],
                 "currency": f.get("currency") or "", "urgent": f["urgent"], "once": f["once"]}
    elif n == "tellme_search":
        watch = {"source": "search", "words": f["words"], "urgent": f["urgent"],
                 "once": f["once"]}
    elif n == "tellme_github":
        watch = {"source": "github", "repo": f["repo"], "event": f["event"],
                 "urgent": f["urgent"], "once": f["once"]}
        if f["event"] == "pr_merged":
            watch["pr"] = f["pr"]
        elif f.get("branch"):
            watch["branch"] = f["branch"]
    else:
        entity, name = f.get("entity") or "", f.get("name") or ""
        if not entity:
            try:
                got = TM.find_device(name, f.get("say") or "")
            except Exception as exc:
                return Result("Jarvis could not look for that device in Home Assistant "
                              f"({type(exc).__name__}).", n)
            if f.get("ambiguous") and (got["why"] or not got["found"]):
                return None     # "tell me when the shop opens": the model's
            if got["why"]:
                return Result(got["why"], n)
            read = ["home_read"] if got["tried"] else []
            if not got["found"]:
                tried = got["tried"]
                return Result(f"Jarvis could not find a Home Assistant device called {name} "
                              f"(it looked for {_join(tried)}). Say its Home Assistant name, "
                              f"like \"tell me when {tried[0] if tried else 'switch.' + TM.slug(name)} "
                              f"is off\".", n, read=read)
            if len(got["found"]) > 1:
                return Result(f"There is more than one: {_join(got['found'])}. Say which, like "
                              f"\"tell me when {got['found'][0]} is off\".", n, read=read)
            entity = got["found"][0]
        watch = {"source": "home", "entity": entity, "name": name, "urgent": f["urgent"],
                 "once": f["once"]}
        if f.get("say"):
            watch["say"] = f["say"]
        else:
            watch["states"] = f.get("states") or []
    try:
        j = TM.add(watch, ends=f.get("ends"), minutes=f.get("minutes"), source="quick",
                   sched=sched)
    except (ValueError, OverflowError) as exc:
        return Result(S._sentence(exc), n, read=read)
    # Like a reminder's words, the sender or device is not said back: the
    # card shows exactly what is watched.
    rule = j.get("rule") or {}
    until = S.long_date(float(rule["ends"])) if rule.get("ends") else "its end"
    tail = "tells you once" if f["once"] else "tells you every time"
    urgent = " It is marked urgent: your phone rings until you look." if f["urgent"] else ""
    return Result(f"That needs your yes on the approval card, which shows exactly what is "
                  f"watched. Then Jarvis looks {S.rule_words(rule)} until {until} and "
                  f"{tail}.{urgent}", n, [j["id"]], read=read)


#: "What's the weather?" (the feasibility audit's I75, 2026-09-26): only the
#: plain question, today or tomorrow - "what's the weather in Paris" or
#: "this weekend" go to the model. Answered from the owner's own Home
#: Assistant (jarvis_briefing.weather_now), or it says why there is none.
_WFOR = r"(?:weather|forecast|weather\s+forecast)"
_WWHEN = r"(?:\s+(?:today|now|right\s+now|outside|this\s+morning|tomorrow|for\s+today|for\s+tomorrow))?"
_WEATHER = re.compile(
    r"(?:what's|what\s+is|whats|how's|how\s+is|hows)\s+the\s+" + _WFOR + r"(?:\s+like)?" + _WWHEN
    + r"|(?:what's|what\s+is|whats)\s+the\s+weather\s+(?:going\s+to\s+be|gonna\s+be)(?:\s+like)?"
    + _WWHEN
    + r"|(?:give|tell)\s+me\s+the\s+" + _WFOR + _WWHEN
    + r"|(?:the\s+)?" + _WFOR + r"(?:\s+(?:today|now|please|tomorrow))?")

#: "Read me the news" (jarvis_news.py, I49, 2026-09-27): answered from the
#: owner's own listed feeds, without the model. Whole sentences only:
#: "what's new with you" goes to the model.
_NEWS_ASK = re.compile(
    r"(?:read\s+me\s+|give\s+me\s+|tell\s+me\s+)?(?:the\s+|my\s+|today'?s\s+)?news"
    r"(?:\s+headlines)?(?:\s+please)?"
    r"|what'?s\s+(?:in\s+|going\s+on\s+in\s+)?the\s+news(?:\s+today)?"
    r"|any\s+news(?:\s+today)?")

#: "Add this feed: <url>" (jarvis_news.py, I49) - a literal address, exactly
#: like "tell me when <url> changes": the owner names it, one card. Whole
#: sentences only.
_NEWS_ADD = re.compile(
    r"add\s+(?:this\s+|a\s+|the\s+)?(?:news\s+)?feed[:\s]+(?P<url>https?://\S+)"
    r"|(?:follow|watch|subscribe\s+to)\s+(?:this\s+|the\s+)?(?:news\s+)?feed[:\s]+"
    r"(?P<url2>https?://\S+)"
    r"|add\s+(?P<url3>https?://\S+)\s+as\s+a\s+news\s+feed")
#: "Remove/stop that feed: <url>" - at once, no card, like "tell me when"'s remove.
_NEWS_REMOVE = re.compile(
    r"(?:remove|delete|stop|unfollow)\s+(?:this\s+|that\s+|the\s+)?(?:news\s+)?feed[:\s]+"
    r"(?P<url>https?://\S+)")
#: "What news feeds do I have?" / "list my news feeds".
_NEWS_LIST = re.compile(
    r"(?:what|which)\s+news\s+feeds\s+(?:do\s+i\s+have|are\s+there|are\s+listed)"
    r"|(?:list|show)\s+(?:me\s+)?(?:my\s+)?news\s+feeds")

#: "the briefing", "my morning briefing", "today's briefing", "briefing".
_BRIEF = r"(?:(?:my|the|a|today'?s|this\s+morning'?s)\s+)?(?:morning\s+|daily\s+)?briefing"


def _briefing(s: str, now: float) -> Optional[Intent]:
    """The morning briefing (jarvis_briefing.py): now, set up, stop, when."""
    # Now - "brief me", "brief me now", "read my briefing", "what's my
    # briefing", "give me my morning briefing", "morning briefing".
    if re.fullmatch(r"brief\s+me(?:\s+(?:now|up))?"
                    r"|(?:give|read|tell)\s+me\s+" + _BRIEF + r"(?:\s+now)?"
                    r"|(?:read|play|say|do|run)\s+(?:out\s+)?" + _BRIEF
                    + r"(?:\s+(?:now|aloud|out\s+loud|out))?"
                    r"|(?:what's|what\s+is|whats)\s+(?:in\s+)?" + _BRIEF
                    + r"|" + _BRIEF + r"(?:\s+now|\s+please)?", s):
        return Intent("briefing_now")
    # Stop - one at a time; "all" is refused like every other bulk change.
    m = re.fullmatch(r"(?:stop|cancel|delete|remove|turn\s+off|switch\s+off|end)\s+(all\s+(?:of\s+)?)?"
                     r"(?:(?:my|the)\s+)?(?:morning\s+|daily\s+)?briefings?", s)
    if m:
        return Intent("bulk" if m.group(1) else "briefing_cancel")
    # When - "when is my briefing", "is my briefing set up".
    if re.fullmatch(r"(?:when\s+is|what\s+time\s+is|is)\s+" + _BRIEF
                    + r"(?:\s+(?:set\s+up|on|set))?", s):
        return Intent("briefing_list")
    # Set up - "brief me every weekday at 7", "brief me tomorrow at 6:30",
    # "set up a morning briefing every day at 7". An alarm's reading of the
    # time: a bare hour on another day is the morning.
    m = re.fullmatch(r"(?:brief\s+me|(?:set\s+up|schedule|start|give\s+me)\s+" + _BRIEF
                     + r")\s+(?:for\s+)?(.+)", s)
    if m:
        when = parse_when(m.group(1), now, "alarm")
        if when is not None:
            return Intent("briefing_set", {"when": when})
    return None


#: The six providers, and Whoogle (left out - asked about, it gets its
#: reason), by the words the owner may use for them.
_PROVIDER_WORDS = (("searxng", r"searx(?:ng)?"),
                   ("duckduckgo", r"duck\s*duck\s*go|ddg"),
                   ("exa", r"exa(?:\s+ai)?"),
                   ("tavily", r"tavily"),
                   ("brave", r"brave(?:\s+search)?"),
                   ("deepseek", r"deep\s*seek"),
                   ("whoogle", r"whoogle"))
_PROV = "|".join(f"(?P<{pid}>{rx})" for pid, rx in _PROVIDER_WORDS)
_WS = r"(?:web\s+)?search(?:es|ing)?(?:\s+(?:engine|provider|service))?"


def _provider_of(m) -> Optional[str]:
    for pid, _ in _PROVIDER_WORDS:
        if m.group(pid):
            return pid
    return None


def _web_search(s: str) -> Optional[Intent]:
    """Web search (jarvis_search.py, the owner's decisions of 2026-09-25):
    "which search should I use?", "why SearXNG?", and "use DuckDuckGo for
    web search". Whole sentences only; anything else goes to the model."""
    if re.fullmatch(r"(?:which|what)\s+" + _WS + r"\s+(?:should|do|can|could)\s+(?:i|you|we|jarvis)"
                    r"\s+use|(?:which|what)\s+" + _WS + r"\s+is\s+(?:best|better|the\s+best)"
                    r"(?:\s+for\s+me)?|what\s+are\s+(?:my|the)\s+" + _WS + r"\s+(?:options|choices)"
                    r"|compare\s+(?:the\s+)?" + _WS + r"(?:\s+(?:options|choices))?"
                    r"|(?:which|what)\s+" + _WS + r"\s+(?:are\s+you|is\s+jarvis)\s+using", s):
        return Intent("search_explain", {"which": None})
    m = re.fullmatch(r"(?P<verb>why|why\s+(?:use|is\s+it|not|choose|pick|would\s+i\s+use)"
                     r"|what\s+is|what's|whats|tell\s+me\s+about|what\s+about)\s+(?:" + _PROV
                     + r")(?P<tail>\s+(?:for\s+)?" + _WS + r")?", s)
    if m:
        which = _provider_of(m)
        # "what is brave" is not about search unless it says so.
        if (which == "brave" and not m.group("verb").startswith("why")
                and m.group("brave") == "brave" and not m.group("tail")):
            return None
        # "what is deepseek" / "why deepseek" is about the AI model or the
        # company, not the search service. Only "... for web search" answers
        # here; everything else goes to the model.
        if which == "deepseek" and not m.group("tail"):
            return None
        return Intent("search_explain", {"which": which})
    m = (re.fullmatch(r"(?:use|switch\s+to|change\s+to)\s+(?:" + _PROV + r")\s+(?:for|as)\s+"
                      r"(?:(?:the|my)\s+)?" + _WS, s)
         or re.fullmatch(r"(?:switch|change|set)\s+(?:the\s+|my\s+)?" + _WS
                         + r"\s+(?:to|over\s+to)\s+(?:" + _PROV + r")", s))
    if m:
        return Intent("search_use", {"which": _provider_of(m)})
    return None


# --- "from now on ..." (the owner's decision, 2026-09-27) -------------------
#
# "Jarvis changes a style dial immediately, replying 'Done: shorter answers
# from now on. You can undo this in Brain.'" (docs/CUTTING-EDGE-2026-09-26-
# round4-growth.md section 4). Scope, as CLAUDE.md narrows it: the MECHANISM
# only - detect the phrase, apply a change at once, offer Undo - wired to the
# one real dial this backend has today (jarvis_manner.py: warm and brief, or
# plain), not the growth doc's bigger multi-dial system (its section 1),
# which is not built. A tail that does not map to that one dial says so
# honestly, rather than pretending to change something that is not there.
#
# Only ever reached from the owner's own live words (newest_own_words(),
# above, already refuses a system message, a shared/clipboard turn, and a
# picture) - never from an email, a web page, a note or a game. A temporary
# chat's change stays in that chat only (jarvis_manner.set_temporary): it is
# never written to manner.json, because a temporary chat makes no memory.
_FROM_NOW_ON = re.compile(r"from\s+now\s+on,?\s+(?:please\s+)?(.+)")

#: The only tails that map to a REAL dial today. Anything "from now on ..."
#: outside these two is recognised as the phrase, but not acted on - see
#: _run_from_now_on's honest reply.
_TO_PLAIN = re.compile(
    r"(?:be|stay|answer|talk|keep\s+it)\s+(?:more\s+)?(?:plain(?:er|ly)?|formal(?:er|ly)?|"
    r"businesslike|neutral(?:ly)?|direct(?:er|ly)?)"
    r"|(?:be|stop\s+being)\s+less\s+(?:warm|chatty|friendly|gushy)"
    r"|cut\s+the\s+small\s+talk|no\s+more\s+small\s+talk|less\s+small\s+talk")
_TO_WARM = re.compile(
    r"(?:be|stay|answer|talk|keep\s+it)\s+(?:more\s+)?(?:warm(?:er|ly)?|friendl(?:y|ier|ily)|"
    r"nicer|chattier|less\s+formal(?:ly)?)"
    r"|(?:be|stop\s+being)\s+less\s+(?:plain(?:ly)?|formal(?:ly)?|cold|robotic)")


_TO_THINK_DEEP = re.compile(r"think\s+(?:harder|more|deeply|deeper)|deep\s+thinking", re.I)
_TO_THINK_QUICK = re.compile(r"think\s+(?:fast|faster|quick|quicker|quickly|less)|quick\s+thinking", re.I)
_TO_THINK_OFF = re.compile(r"stop\s+thinking|don't\s+think|turn\s+off\s+thinking|no\s+thinking|thinking\s+off", re.I)
_TO_THINK_AUTO = re.compile(r"think\s+(?:automatically|auto|on\s+your\s+own)|auto\s+thinking", re.I)

_THINK_DEEP_CMD = re.compile(
    r"^(?:please\s+)?(?:think\s+(?:harder|more|deeply|deeper)|deep\s+thinking)\.?$", re.I)
_THINK_QUICK_CMD = re.compile(
    r"^(?:please\s+)?(?:think\s+(?:fast|faster|quick|quicker|quickly|less)|quick\s+thinking)\.?$", re.I)
_THINK_OFF_CMD = re.compile(
    r"^(?:please\s+)?(?:stop\s+thinking|don't\s+think|turn\s+off\s+thinking|no\s+thinking|thinking\s+off)\.?$", re.I)
_THINK_AUTO_CMD = re.compile(
    r"^(?:please\s+)?(?:think\s+(?:automatically|auto|on\s+your\s+own)|auto\s+thinking)\.?$", re.I)
_THINK_STATUS_CMD = re.compile(
    r"^(?:what\s+is\s+(?:the\s+)?thinking\s+level|how\s+is\s+thinking\s+set|thinking\s+status|thinking\s+level)\??$", re.I)

# WHEN thinking happens (jarvis_thinking.WHEN_ASKED / ALWAYS, 2026-10-11): the
# owner's two-choice setting, said out loud. Two whole sentences, the same
# shape as every other command here, and the wording the mode's own answer
# tells the owner to use ("say \"always think\" ...").
_THINK_ALWAYS_CMD = re.compile(
    r"^(?:please\s+)?(?:always\s+think|think\s+(?:about\s+)?(?:everything|every\s+(?:answer|question|time))"
    r"|think\s+every\s+time|use\s+thinking\s+(?:always|everywhere))\.?$", re.I)
_THINK_ONLY_ASKED_CMD = re.compile(
    r"^(?:please\s+)?(?:only\s+think\s+(?:when|if)\s+i\s+ask|think\s+only\s+when\s+i\s+ask"
    r"|don'?t\s+think\s+(?:unless|until)\s+i\s+ask|only\s+think\s+when\s+asked)\.?$", re.I)


def _thinking_cmd(s: str) -> Optional[Intent]:
    if _THINK_DEEP_CMD.match(s):
        return Intent("thinking_set", {"level": "deep"})
    if _THINK_QUICK_CMD.match(s):
        return Intent("thinking_set", {"level": "quick"})
    if _THINK_OFF_CMD.match(s):
        return Intent("thinking_set", {"level": "off"})
    if _THINK_AUTO_CMD.match(s):
        return Intent("thinking_set", {"level": "auto"})
    if _THINK_ALWAYS_CMD.match(s):
        return Intent("thinking_when", {"when": "always"})
    if _THINK_ONLY_ASKED_CMD.match(s):
        return Intent("thinking_when", {"when": "when_asked"})
    if _THINK_STATUS_CMD.match(s):
        return Intent("thinking_status")
    return None


def _from_now_on(s: str) -> Optional[Intent]:
    """"From now on, be more plain" / "... be warmer" / "... think harder" and close phrasings -
    the mechanism, wired to jarvis_manner.py's and jarvis_thinking.py's dials. Whole
    sentences only, like the rest of this grammar."""
    m = _FROM_NOW_ON.fullmatch(s)
    if not m:
        return None
    tail = m.group(1).strip()
    if _TO_PLAIN.fullmatch(tail):
        return Intent("manner_from_now_on", {"manner": "plain"})
    if _TO_WARM.fullmatch(tail):
        return Intent("manner_from_now_on", {"manner": "warm"})
    if _TO_THINK_DEEP.fullmatch(tail):
        return Intent("thinking_from_now_on", {"level": "deep"})
    if _TO_THINK_QUICK.fullmatch(tail):
        return Intent("thinking_from_now_on", {"level": "quick"})
    if _TO_THINK_OFF.fullmatch(tail):
        return Intent("thinking_from_now_on", {"level": "off"})
    if _TO_THINK_AUTO.fullmatch(tail):
        return Intent("thinking_from_now_on", {"level": "auto"})
    return Intent("manner_from_now_on", {"manner": None})


# --------------------------------------------------------------------------
#   Personality presets (2026-10-22, the owner's decision: Jarvis can slip
#   into any of ten characters, typed or spoken, with no approval card)
# --------------------------------------------------------------------------
#
# Every phrase below maps to ONE conversation-free action: either a preset
# switch (base/aliases from contract/personalities.json), one of the four
# tuning dials, or a question about the current one. Nothing here reaches the
# model, nothing opens a card, and everything is answered in the new preset's
# own voice. "What personality are you using?" lists the ten by title,
# which is how the owner learns the names to say.
#
# Deliberately NOT here: "turn on humour" / "turn off humour" - the existing
# humour switch in BOOL_SETTINGS already owns that sentence and its own
# wording; this grammar only adds "set humour to subtle/dry/playful/90%",
# which the switch cannot answer.
_P_SWITCH = re.compile(
    r"(?:please\s+)?(?:switch|change|set|put)\s+(?:your\s+|the\s+|my\s+)?"
    r"(?:personality|persona|manner|mode|vibe|style|character)\s+to\s+"
    r"(?:be\s+|act\s+like\s+|use\s+)?(.+)")
_P_SWITCH_MODE = re.compile(
    r"(?:please\s+)?(?:switch|change)\s+(?:to\s+)?(.+?)\s+(?:mode|personality|persona)\b")
_P_TALK_LIKE = re.compile(r"(?:please\s+)?(?:talk|speak|answer)\s+to\s+me\s+(?:like|as)\s+(.+)")
_P_ACT_LIKE = re.compile(r"(?:please\s+)?act\s+like\s+(.+)")
_P_BE_MORE = re.compile(r"(?:please\s+)?be\s+(?:more|a\s+(?:bit|little)\s+more)\s+(.+)")
_P_HUMOR_SET = re.compile(r"(?:please\s+)?set\s+(?:the\s+)?(?:humou?r|wit|wittiness)\s+to\s+(.+)")
_P_BREVITY_SET = re.compile(
    r"(?:please\s+)?set\s+(?:the\s+)?(?:brevity|answer\s+length|length\s+of\s+answers?)\s+to\s+(.+)")
_P_SHORT = re.compile(
    r"(?:please\s+)?(?:keep|make)\s+(?:your\s+)?answers?\s+(?:short(?:er)?|brief(?:er)?|concise)")
_P_LONG = re.compile(
    r"(?:please\s+)?(?:keep|make)\s+(?:your\s+)?answers?\s+(?:long(?:er)?|thorough|detailed)")
_P_FORMALITY = re.compile(r"(?:please\s+)?set\s+(?:the\s+)?formality\s+to\s+(.+)")
_P_ADDRESS = re.compile(r"(?:please\s+)?(?:call\s+me|address\s+me\s+as|refer\s+to\s+me\s+as)\s+(.+)")
_P_QUERY = re.compile(
    r"(?:what|which)\s+(?:personality|persona|character)\s+(?:are\s+you|is\s+(?:active|on|current))"
    r"|what\s+personalities\s+do\s+you\s+have"
    r"|(?:list|show)\s+(?:me\s+)?(?:your\s+)?(?:personalities|personality\s+presets)")

#: "describe your personalities", "describe my personalities", "explain your
#: personalities", "tell me about your personalities", "what does each
#: personality do", "what are your personalities like" - ALL of them
#: (2026-10-26). "my" is accepted as the owner says it: "describe my
#: personalities" answers with the same ten (they are the personalities the
#: chat has), and the saved "My Personalities" stay the separate ones the
#: status answer names.
#: One line per preset, every word from that preset's own `description`: the
#: catalogue already says what each one is, so nothing is invented here.
#:
#: THE POSSESSIVE IS REQUIRED (2026-10-27, PR #876's CI failure). Without it
#: these forms stole the feature guide's own aliases: "tell me about presets"
#: and "tell me about personalities" are the owner asking WHERE to change
#: them, and they must reach the rows that own them -
#: backend/test_feature_guide.py's alias sweep, and its
#: "where do i change the jarvis presets" test. Only a sentence that says
#: WHOSE personalities are meant - your / the / my - asks to describe them.
#: A bare "presets" is the layout presets, not the ten, so that noun is gone
#: from these forms; "personality presets" (the whole phrase) still counts.
#:
#: Tried BEFORE the one-preset forms below, deliberately: "tell me about your
#: personalities" also fits "tell me about <name>", and it must be the list,
#: not a name that resolves to nothing. "What personality are you using?" and
#: "what personalities do you have?" stay with `_P_QUERY` above, unchanged.
_P_DESCRIBE_ALL = re.compile(
    r"(?:describe|explain|tell\s+me\s+about)\s+(?:all\s+(?:of\s+)?)?"
    r"(?:your|the|my)\s+"
    r"(?:(?:nine|ten)\s+)?(?:personalities|personality\s+presets|personas|characters)"
    r"|(?:what|which)\s+(?:does|do)\s+each\s+(?:personality|persona|character)\s+do"
    r"|what\s+(?:are|is)\s+(?:your|the|my)\s+(?:(?:nine|ten)\s+)?(?:personalities|personas)"
    r"\s+(?:like|for)"
    r"|what\s+(?:do|does)\s+(?:all\s+(?:of\s+)?)?(?:your|the|my)\s+(?:(?:nine|ten)\s+)?"
    r"(?:personalities|personas)\s+do")

#: "what does the Classic Butler personality do", "what is the Classic Butler
#: personality", "describe the butler personality", "tell me about TARS",
#: "what is TARS like" - ONE preset (2026-10-26), resolved through
#: `jarvis_manner.normalize_personality_id()`, so titles, aliases and the
#: owner's own saved names all work. A name that resolves to nothing returns
#: None and the sentence stays with the model: "what does it do" and "tell me
#: about yourself" are ordinary questions, not personality ones.
#:
#: Deliberately NOT a bare "what is <name>": several aliases are ordinary words
#: ("brief", "normal", "quiet"), so that form would take "what is normal" from
#: the model. These five shapes DO match an alias on its own - "what does the
#: butler do", "what can TARS do", "what is brief like" - and that is intended,
#: because naming a real preset is the point. The guard is the resolver, not
#: the wording: the name must resolve through normalize_personality_id() to a
#: built-in or a saved preset, so "what does it do", "tell me about yourself"
#: and a bare "what is brief" stay with the model.
_P_DESCRIBE_ONE = (
    re.compile(r"(?:what|which)\s+(?:does|do|can)\s+(?P<who>.+?)\s+do"),
    re.compile(r"what(?:'s|\s+is)\s+(?P<who>.+?)\s+(?:personality|persona|preset|character)"),
    re.compile(r"what(?:'s|\s+is)\s+(?P<who>.+?)\s+like"),
    re.compile(r"describe\s+(?P<who>.+)"),
    re.compile(r"tell\s+me\s+about\s+(?P<who>.+)"),
)

#: The noun a question can hang on a name: "the butler PERSONALITY".
_DESCRIBE_TAIL = re.compile(r"\s+(?:personality|persona|preset|character|mode)$")

#: "be more ..." words -> what they mean: a whole preset where the blueprint
#: treats it as one, a dial where it is really one of the four.
_BE_MORE_PRESET = {
    "sarcastic": "dry_wit", "deadpan": "dry_wit", "witty": "dry_wit",
    "funny": "dry_wit", "humorous": "dry_wit",
    "calm": "calm_stoic", "gentle": "calm_stoic", "zen": "calm_stoic",
    "formal": "classic_butler", "proper": "classic_butler", "butler": "classic_butler",
    "tactical": "tactical_ops", "direct": "tactical_ops", "brief": "tactical_ops",
    "warm": "warm_peer", "friendly": "warm_peer", "normal": "warm_peer",
    "friday": "friday_partner", "technical": "friday_partner",
    "socratic": "socratic_mentor", "critical": "devils_advocate", "skeptical": "devils_advocate",
}
_BE_MORE_DIAL = {
    "concise": ("brevity", "concise"), "short": ("brevity", "concise"),
    "balanced": ("brevity", "balanced"),
    "thorough": ("brevity", "thorough"), "detailed": ("brevity", "thorough"),
    "casual": ("formality", "casual"), "warm": ("formality", "warm_peer"),
    "tactical": ("formality", "tactical"),
}


def _personality_target(value: str) -> Optional[Intent]:
    """A preset switch for `value` if it names one, else None."""
    try:
        import jarvis_manner
        pid = jarvis_manner.normalize_personality_id(value)
    except Exception:
        pid = None
    if pid:
        return Intent("personality_set", {"personality": pid})
    return None


def _personality_dial(name: str, value) -> Optional[Intent]:
    """A dial intent ONLY when the value really is valid for that dial.

    Ordinary sentences are not allowed to become dials: "call me three times"
    must stay chat, not become an address change that then refuses or, worse,
    silently does nothing. Refusing at match time keeps the sentence with the
    model."""
    try:
        import jarvis_manner
        if jarvis_manner._dial_value(name, value) is None:
            return None
    except Exception:
        return None
    return Intent("personality_dial", {"name": name, "value": value})


def _personality_named(words: str) -> Optional[str]:
    """The preset id `words` names, or None when it names none of them.

    The same resolver the switch uses - every built-in id, title and alias,
    plus the owner's own saved personalities by id or name - so what this
    answers about is exactly what "switch to ..." would switch to."""
    name = _DESCRIBE_TAIL.sub("", _clean_tail(words))
    try:
        import jarvis_manner
        return jarvis_manner.normalize_personality_id(name)
    except Exception:
        return None


def _personality_describe(s: str) -> Optional[Intent]:
    """"describe your personalities" / "what does the Classic Butler do": the
    question forms about what a preset IS, answered from the preset's own
    `description`. Read-only, cardless and never the model - and None when the
    sentence names nothing known, so "what does it do" and "tell me about
    yourself" stay ordinary questions."""
    if _P_DESCRIBE_ALL.fullmatch(s):
        return Intent("personality_describe")
    for pattern in _P_DESCRIBE_ONE:
        m = pattern.fullmatch(s)
        if m:
            pid = _personality_named(m.group("who"))
            if pid:
                return Intent("personality_describe", {"personality": pid})
    return None


def _personality(s: str) -> Optional[Intent]:
    """"Switch personality to Classic Butler", "talk to me like TARS",
    "be more sarcastic", "set humour to dry", "call me sir", the question
    forms, and (2026-10-26) "what does each personality do" and "tell me about
    TARS". Whole sentences only, like the rest of this grammar."""
    if _P_QUERY.search(s):
        return Intent("personality_status")
    got = _personality_describe(s)
    if got is not None:
        return got
    for pattern in (_P_SWITCH, _P_SWITCH_MODE, _P_TALK_LIKE, _P_ACT_LIKE):
        m = pattern.fullmatch(s)
        if m:
            got = _personality_target(m.group(1).strip())
            if got is not None:
                return got
    m = _P_BE_MORE.fullmatch(s)
    if m:
        word = _clean_tail(m.group(1))
        if word in _BE_MORE_PRESET:
            return Intent("personality_set", {"personality": _BE_MORE_PRESET[word]})
        if word in _BE_MORE_DIAL:
            name, value = _BE_MORE_DIAL[word]
            return _personality_dial(name, value)
    m = _P_HUMOR_SET.fullmatch(s)
    if m:
        return _personality_dial("humor", _clean_tail(m.group(1)))
    m = _P_BREVITY_SET.fullmatch(s)
    if m:
        return _personality_dial("brevity", _clean_tail(m.group(1)))
    if _P_SHORT.fullmatch(s):
        return _personality_dial("brevity", "concise")
    if _P_LONG.fullmatch(s):
        return _personality_dial("brevity", "thorough")
    m = _P_FORMALITY.fullmatch(s)
    if m:
        return _personality_dial("formality", _clean_tail(m.group(1)))
    m = _P_ADDRESS.fullmatch(s)
    if m:
        return _personality_dial("address", _clean_tail(m.group(1)))
    return None


def _clean_tail(words: str) -> str:
    """The tail of a phrase without "please" and trailing punctuation."""
    tail = re.sub(r"\bplease\b", "", str(words or "")).strip()
    return tail.strip(" .,!?;:")


# --------------------------------------------------------------------------
#   Show or hide menus (jarvis_menus.py; docs/MENU-VISIBILITY-DESIGN.md, the
#   owner's decision of 2026-09-30; docs/JARVIS-API.md section 109). "hide the
#   finance menu", "show the quiz menu", "collapse the goals menu", "show
#   everything". Hiding only tidies: nothing is turned off, nothing asks, and the
#   gate is never involved. Per device - the PC cannot know which app asked, so
#   the answer says "on the devices that are open" and X-Jarvis-Route carries
#   `menu_visibility: {"action", "target"}` for each app to apply to itself.
#   Never-hideable menus (security, what asks first, approvals, ...) are refused
#   here too, belt and braces. A `show` whose name is no menu falls through
#   ("show me the dinner menu" is not ours); hide/collapse/expand of an unknown
#   name is answered, never guessed.
# --------------------------------------------------------------------------

_MENU_ONE = re.compile(
    r"(hide|unhide|show|collapse|expand)\s+(?:me\s+)?(?:the\s+|my\s+)?(.+?)\s+(menu|menus|section)")
_MENU_VERB = {"hide": "hide", "unhide": "show", "show": "show", "collapse": "collapse",
              "expand": "expand"}


def _menu_visibility(s: str) -> Optional[Intent]:
    try:
        import jarvis_menus as MV
    except Exception:
        return None
    if MV.ALL_MENUS_PHRASES.fullmatch(s):
        return Intent("menu_visibility", {"action": "reset", "name": ""})
    m = _MENU_ONE.fullmatch(s)
    if not m:
        return None
    verb, name, suffix = m.group(1), m.group(2), m.group(3)
    action = _MENU_VERB[verb]
    known = MV.resolve(name) is not None
    if action == "show" and not known:
        return None
    if verb == "show" and suffix == "section":
        # "show the voice section" still opens Settings there (the older meaning).
        try:
            import jarvis_settings_registry as R
            if R.find_section(name) is not None:
                return None
        except Exception:
            pass
    return Intent("menu_visibility", {"action": action, "name": name})


# --------------------------------------------------------------------------
#   Any setting, by name (jarvis_settings_registry.py, the owner's decision
#   of 2026-09-27): "open <a settings section>" is pure navigation; "turn
#   on/off <a setting>" calls straight into the exact function the matching
#   toggle in Settings already calls - see that module's own header for
#   what is and is not covered, and why.
# --------------------------------------------------------------------------

#: "open web search", "show me the security settings", "go to accounts",
#: "take me to what asks first" - an exact alias only (jarvis_settings_
#: registry.find_section): a tail this does not name a section jumps
#: nowhere and falls through, so "open the door" is still the model's.
_OPEN_SETTINGS = re.compile(
    r"(?:open|show(?:\s+me)?|go\s+to|jump\s+to|take\s+me\s+to)\s+(?:the\s+)?(.+?)"
    r"(?:\s+(?:settings|section|screen|page))?")


def _settings_open(s: str) -> Optional[Intent]:
    m = _OPEN_SETTINGS.fullmatch(s)
    if not m:
        return None
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    section = R.find_section(m.group(1))
    # A Section that is the feature's own switch (`openable=False`, today only
    # the Jarvis Calendar row) is not a place this sentence may jump to: its
    # words belong to the feature, which answers them later in this dispatch
    # (`_open`, and `docs/JARVIS-API.md` section 21.13 says "open my calendar"
    # still opens it). Falling through here is what keeps that true.
    if section is None or not getattr(section, "openable", True):
        return None
    return Intent("settings_open", {"id": section.id})


#: "What can I change?" (the owner's decision, 2026-10-10). Without this the
#: question reached the AI model, which invented an answer: some switches it
#: named did not exist, and it never said that a change which loosens a rule
#: still raises a card. The answer is built by
#: jarvis_settings_registry.changeable_words, straight off the real switches.
_SETTINGS_HELP = re.compile(
    r"what\s+can\s+i\s+change"
    r"|what\s+settings\s+can\s+i\s+change"
    r"|what\s+can\s+(?:you|i)\s+change\s+by\s+(?:talking|asking|voice)(?:\s+to\s+(?:you|jarvis))?"
    r"|which\s+settings\s+can\s+i\s+change"
    r"|what\s+settings\s+(?:do\s+you\s+have|are\s+there)"
    r"|list\s+(?:my\s+|the\s+)?settings"
    r"|what\s+can\s+i\s+change\s+in\s+settings")


def _settings_help(s: str) -> Optional[Intent]:
    if _SETTINGS_HELP.fullmatch(s):
        return Intent("settings_help")
    return None


#: The plain on/off settings (jarvis_settings_registry.BOOL_SETTINGS): "turn
#: on background learning", "switch off lights without asking", "enable
#: smartwatch notifications", "disable senders in my briefing".
_ADJUST_ONOFF = re.compile(
    r"(?:turn|switch)\s+(on|off)\s+(.+)"
    r"|(enable)\s+(.+)"
    r"|(disable)\s+(.+)")

#: A sentence that asks to change A SETTING and names one nothing knows
#: (2026-10-13): "turn off the turbo setting", "change my security settings",
#: "enable the settings thing". The word "setting"/"settings" is REQUIRED, and
#: that is the whole safety of this pattern: a device ("turn off the kitchen
#: light"), a timer, a menu, an animal option and every other feature this file
#: answers do not carry it, so nothing already answered changes hands.
_SETTING_UNKNOWN = re.compile(
    r"(?:turn|switch)\s+(?:on|off)\s+(?:the\s+|my\s+|a\s+)?(.+?)\s+settings?"
    r"|(?:enable|disable|change|set|adjust|edit|update)\s+(?:the\s+|my\s+|a\s+)?"
    r"(.+?)\s+settings?"
    r"|(?:change|edit|adjust|update)\s+(?:my|the|a)\s+settings"
    r"|(?:turn|switch)\s+(?:on|off)\s+(?:my|the|a)\s+settings")

#: "set the hand-off to patient", "set how long my chats are kept to 30 days"
#: (2026-10-22, the owner's universal-controls requirement). ONLY a name from
#: jarvis_settings_registry.CHOICE_SETTINGS may match: a tail naming anything
#: else returns None and falls through exactly as it did before - this must not
#: become a second way to rewrite sentences other grammars own.
_SET_CHOICE_TO = re.compile(
    r"(?:set|change|switch|adjust|make|put)\s+(?:the\s+|my\s+|a\s+)?(.+?)\s+to\s+(.+)")

#: The captcha hand-off's two choices, in the words the owner already reads on
#: its Settings card ("Stop early" / "Keep offering it") - never a guess.
_SET_HANDOFF_MODE = re.compile(
    r"keep\s+(?:the\s+)?(?:captcha\s+|hand[\s-]?off\s+)*(?:hand[\s-]?off|captcha)"
    r"\s+on\s+offer(?:\s+for\s+(?:the\s+)?(?:full\s+)?15\s+minutes?)?"
    r"|keep\s+offering(?:\s+it)?(?:\s+for\s+(?:the\s+)?(?:full\s+)?15\s+minutes?)?"
    r"|be\s+patient\s+(?:with\s+)?(?:the\s+)?(?:hand[\s-]?off|captcha)"
    r"|stop\s+early\s+(?:with\s+)?(?:the\s+)?(?:hand[\s-]?off|captcha)"
    r"|set\s+(?:the\s+)?(?:hand[\s-]?off|captcha)(?:\s+mode)?\s+to\s+"
    r"(?P<value>patient|quick|stop\s+early|keep\s+offering(?:\s+it)?)")

#: Whether the captcha's own window comes to the front.
_SET_HANDOFF_FRONT = re.compile(
    r"bring\s+(?:the\s+)?(?:captcha|hand[\s-]?off)\s+window\s+to\s+(?:the\s+)?front"
    r"|leave\s+(?:the\s+)?(?:captcha|hand[\s-]?off)\s+window\s+"
    r"(?:where\s+it\s+is|in\s+place)"
    r"|set\s+(?:the\s+)?(?:captcha|hand[\s-]?off)\s+window\s+to\s+"
    r"(?P<value>bring\s+(?:it\s+)?to\s+(?:the\s+)?front|"
    r"leave\s+(?:it\s+)?(?:where\s+it\s+is|in\s+place))")

#: "use the coding focus preset", "switch to the coding preset".
_SET_PRESET_NATURAL = re.compile(
    r"(?:use|apply|switch\s+to)\s+(?:the\s+)?(.+?)\s+(?:focus\s+)?preset")

#: "use the Clara voice", "switch to the Ashby voice" (2026-10-28 - the
#: owner's own phrasing for changing the built-in voice by asking). CLOSED
#: WORLD, exactly like the preset sentence above: the value is looked up in
#: the built-in voice's OWN list, and a name that list does not have returns
#: None and falls through as before. That is what keeps "use the passive
#: voice" (a writing request) reaching the model instead of being answered
#: with a voice refusal, and it means no voice id can ever be guessed here.
_VOICE_USE = re.compile(
    r"(?:use|switch\s+to)\s+(?:the\s+)?(.+?)\s+voice")

#: The ONE generic multi-field grammar (Gemini ruling Q3, 2026-10-22):
#: "set <control> <field> to <value>" / "change ...". The closed control/field
#: vocabulary lives in jarvis_settings_registry.CONTROL_FIELDS; a sentence that
#: names no control there falls through exactly as before. A named control with
#: a missing/ambiguous field or an invalid value is answered deterministically
#: (fields + current values, or the valid values) - never handed to the model.
_CONTROL_TO = re.compile(
    r"(?:set|change|adjust|switch|put)\s+(?:the\s+|my\s+|a\s+)?(.+?)\s+to\s+(.+)")
_CONTROL_ADJUST_ONLY = re.compile(
    r"(?:adjust|change|set)\s+(?:the\s+|my\s+|a\s+)?(.+)")

#: The owner's two Settings-only exceptions (ruling Q3.3): a typed change to
#: credentials or to Restore backup is refused in plain words with the Settings
#: pointer. The patterns are deliberately narrow (a backup restore, or a named
#: key/password) so ordinary asks are not swallowed.
_SETTINGS_ONLY_RESTORE = re.compile(
    r"(?:restore|put\s+back|bring\s+back|roll\s+back)\s+(?:my\s+|the\s+|a\s+)?"
    r"(?:backup|save|snapshot)(?:\s+(?:file|copy))?"
    r"|restore\s+from\s+(?:my\s+|the\s+|a\s+)?backup")
_SETTINGS_ONLY_ACCOUNTS = re.compile(
    r"(?:set|change|update|add|edit|enter|save|show|tell|what\s+is|what's)\s+"
    r"(?:me\s+)?"
    r"(?:(?:my|the|a)\s+)?(?:(?:[a-z]+\s+)?(?:api\s*keys?|account\s*keys?|"
    r"chatbot\s*keys?)|openai\s*key|github\s*token|password|passphrase|"
    r"pairing\s*(?:token|key)|credentials?)(?:\s+(?:to|for|please))?")

#: "what are the choices for the hand-off?", "what can I set the voice speed
#: to?" - the ask-don't-guess answer for a known choice setting.
_SET_CHOICE_HELP = re.compile(
    r"(?:what\s+are\s+)?(?:the\s+)?(?:choices|options)\s+for\s+(?:the\s+|my\s+|a\s+)?(.+)"
    r"|what\s+can\s+i\s+set\s+(?:the\s+|my\s+|a\s+)?(.+?)\s+to")

#: The PC's own "hey Jarvis" switch (jarvis_speech.set_wake_enabled, POST
#: /api/voice/wake). OFF at once; ON is ONE approval card that either app's
#: approval list can answer. It is NOT a BOOL_SETTINGS row - the desktop draws
#: it as a status line and a button in the Voice card, not a toggle - so it has
#: its own intent, the same shape settings_budget and settings_card_mode use.
_WAKE_WORD = re.compile(
    r"(?:turn|switch)\s+(?P<on>on|off)\s+(?:the\s+|my\s+|your\s+)?"
    r"(?:wake\s+word|hey\s+jarvis(?:\s+wake\s+word)?)"
    r"|(?:turn|switch)\s+(?:the\s+|my\s+|your\s+)?(?:wake\s+word|hey\s+jarvis)"
    r"\s+(?P<on2>on|off)"
    r"|(?P<enable>enable|disable)\s+(?:the\s+|my\s+|your\s+)?"
    r"(?:wake\s+word|hey\s+jarvis(?:\s+wake\s+word)?)")

#: The Anti-Slop filter (jarvis_antislop.py, 2026-10-28). TWO sentences need
#: their OWN patterns, and both would be answered wrongly by the generic
#: grammar if they did not have them:
#:
#:   * "turn on anti-slop for code" - `_ADJUST_ONOFF` reads a switch named
#:     "anti-slop for code", misses the exact name, and the tolerant matcher
#:     then finds the whole switch inside those words and turns the WHOLE
#:     filter on. The owner asked for one scope; getting three is a different
#:     change from the one they asked for. So this is matched FIRST.
#:   * "is anti-slop on" - would otherwise be answered by the generic
#:     is-it-on lane, which can only say on or off. The filter also has a mode,
#:     three scopes and three dials, and they are what the owner is asking
#:     about when they name the filter itself (and an answer that omits them
#:     would be a worse answer than the one this feature exists to give).
#:
#: "set anti-slop mode to after" is deliberately NOT here: `antislop_mode` is a
#: CHOICE_SETTINGS row, so the repo's existing "set <name> to <value>" grammar
#: already reaches the same setter, with the same refusal for a value that is
#: not one of the two. A second path for it would be a second way to say the
#: same thing, and `test_settings_registry.py` walks every choice row through
#: that grammar.
#:
#: NEITHER of the two is a second gate: each calls the registry's own setter,
#: which calls jarvis_antislop's own setter, which is the same function the
#: route and the Settings page call. No card is raised in any direction, and
#: nothing is claimed unless the state reads back changed.
_ANTISLOP_NAMES = r"(?:anti[\s-]?slop|ai[\s-]slop|slop\s+filter|ai\s+slop\s+filter)"
_ANTISLOP_SCOPE = re.compile(
    r"(?:turn|switch)\s+(?P<on>on|off)\s+(?:the\s+)?(?:" + _ANTISLOP_NAMES + r")"
    r"(?:\s+filter)?\s+(?:for|on|in)\s+(?P<scope>[\w\s-]+?)"
    r"|(?P<enable>enable|disable)\s+(?:the\s+)?(?:" + _ANTISLOP_NAMES + r")"
    r"(?:\s+filter)?\s+(?:for|on|in)\s+(?P<scope2>[\w\s-]+?)")
_ANTISLOP_STATE = re.compile(
    r"is\s+(?:the\s+)?(?:" + _ANTISLOP_NAMES + r")(?:\s+filter)?\s+"
    r"(?:on|off|enabled|disabled|active|running|switched\s+on|switched\s+off)"
    r"(?:\s+(?:right\s+now|now|currently|at\s+the\s+moment))?"
    r"|(?:what|what's|whats|how)\s+(?:is|are)\s+(?:the\s+)?(?:" + _ANTISLOP_NAMES + r")"
    r"(?:\s+filter)?\s+(?:set\s+to|set|configured|doing|state|status)"
    r"|(?:tell|show)\s+me\s+(?:the\s+)?(?:" + _ANTISLOP_NAMES + r")(?:\s+filter)?"
    r"\s+(?:state|status|settings)")
#: What a scope word means. Only these three exist, and a sentence that names
#: something else is answered with the three real ones - never guessed at.
_ANTISLOP_SCOPES = {
    "copy": "copy", "writing": "copy", "prose": "copy", "answers": "copy",
    "words": "copy", "text": "copy",
    "code": "code", "comments": "code", "comment": "code",
    "code comments": "code", "programming": "code",
    "ui": "ui", "design": "ui", "web": "ui", "pages": "ui", "page": "ui",
    "interface": "ui", "screens": "ui", "screen": "ui",
}


def _antislop_intent(s: str) -> Optional[Intent]:
    """A sentence that names the Anti-Slop filter itself, or None.

    `s` is the tidied, lower-cased sentence. The state ask is checked first: it
    is a question and changes nothing.
    """
    state = _ANTISLOP_STATE.fullmatch(s)
    if state:
        return Intent("settings_antislop_state", {})
    scope = _ANTISLOP_SCOPE.fullmatch(s)
    if scope:
        on = ((scope.group("on") or "") == "on"
              or (scope.group("enable") or "") == "enable")
        word = (scope.group("scope") or scope.group("scope2") or "").strip()
        name = _ANTISLOP_SCOPES.get(word)
        if name is None:
            return Intent("settings_antislop_bad", {"field": "scope", "words": word})
        return Intent("settings_antislop_scope", {"scope": name, "on": on})
    return None


#: Which browser Jarvis uses (jarvis_browser_engine.MODES): automatic, the
#: visible browser, or the windowless one. A local behaviour choice with its
#: own route (POST /api/browser/engine {"mode": ...}) and NO card: it changes
#: which engine does the work, never what Jarvis may reach or approve.
_BROWSER_MODE_TO = re.compile(
    r"(?:set|change|switch|put|make)\s+(?:the\s+|my\s+)?"
    r"(?:default\s+)?browser(?:\s+engine)?(?:\s+mode)?\s+to\s+(.+)")
_BROWSER_MODE_USE = re.compile(
    r"(?:always\s+|only\s+|just\s+|please\s+)?use\s+(?:the\s+)?"
    r"(?P<mode>visible|headless|windowless|automatic)\s+browser"
    r"(?:\s+(?:by\s+default|from\s+now\s+on))?")
#: The FACE, in the words a person actually uses for it (2026-10-26). The
#: generic "set <control> to <value>" grammar already covers "change the face
#: to the red panda", "set your face to orbit" and "switch the face to the
#: owl" - these three shapes have no "to" and get their own patterns rather
#: than a loosening of that one:
#:
#:   "use the Orbit face" / "wear the red panda face"
#:   "make your face the accretion face"
#:   "put the spiral face on"
#:
#: and one READ, which changes nothing: "what face are you using?".
#: The value is looked up in jarvis_settings_registry's face list - the
#: visual spec's own ids and names - so an unknown face is refused with the
#: real list, never guessed at.
_FACE_USE = re.compile(r"(?:use|wear|try|go\s+with)\s+(?:the\s+|a\s+)?(.+?)\s+face")
#: The trailing "face" is REQUIRED, and it is not decoration: without it
#: "make the face bigger" (the per-device face-size control, whose typed path
#: is honestly recorded as not-yet-resolvable) would match here and be
#: answered as an unknown face instead of reaching its own row. Measured:
#: tools/check_feature_controls.py caught exactly that.
_FACE_MAKE = re.compile(
    r"make\s+(?:your|the|my)\s+face\s+(?:the\s+|a\s+)?(.+?)\s+face")
_FACE_PUT_ON = re.compile(r"(?:put|wear|try)\s+(?:the\s+)?(.+?)\s+face\s+(?:on|please)")
_FACE_ASK = re.compile(
    r"(?:what|which)\s+face\s+(?:are\s+you|do\s+you\s+have|is\s+on)\s*"
    r"(?:using|wearing|on|now)?")

#: "What asks first" (jarvis_asks_first.LOOSE): stricter (ask again) or
#: looser (stop asking - the PC only, one card plus Windows Hello). An
#: optional "jarvis reads/accesses/checks/writes" is taken off first, so
#: "stop asking before jarvis reads my calendar" and "stop asking before my
#: calendar" both name the same target.
_ASKS_FIRST_STRICTER = re.compile(
    r"(?:ask\s+me\s+(?:first\s+)?before\s+|ask\s+first\s+before\s+|make\s+jarvis\s+ask\s+"
    r"(?:me\s+)?before\s+)(?:jarvis\s+(?:reads?|accesses?|checks?|writes?)\s+)?(.+)")
_ASKS_FIRST_LOOSER = re.compile(
    r"stop\s+asking\s+(?:me\s+)?before\s+(?:jarvis\s+(?:reads?|accesses?|checks?|writes?)\s+)?"
    r"(.+)")

#: Offering a reading tool to the AI model at all (jarvis_asks_first.
#: TOOLS_SWITCHABLE) - a DIFFERENT thing from the above (see that module's
#: own header): "let the AI model read my calendar" / "don't let the AI
#: model read my email".
_TOOL_ON = re.compile(r"let\s+the\s+ai\s+model\s+(?:read|access|use|check)\s+(.+)")
_TOOL_OFF = re.compile(
    r"(?:don'?t\s+let|stop\s+letting)\s+the\s+ai\s+model\s+(?:read|access|use|check)\s+(.+)")

#: "How much Jarvis may interrupt you" (jarvis_arbiter.py, 2026-10-08) - the
#: number of times a day it may speak up UNASKED, and the hour the brief
#: arrives. Digits only, and whole sentences only, like every setting here:
#: the number is the one thing this must never guess, and a sentence it does
#: not match exactly falls through to the model rather than picking one.
#:   "speak up 5 times a day", "let jarvis speak up 2 times a day"
#:   "speak up less" / "speak up more"      (one step of one, that direction)
#:   "the brief at 8pm", "the brief at 20", "the digest arrives at 7 in the morning"
_BUDGET_PER_DAY = re.compile(
    r"(?:let\s+)?(?:jarvis\s+)?speak\s+up\s+(?:to\s+)?(\d{1,2})\s+times?\s+(?:a|per)\s+day")
_BUDGET_STEP = re.compile(
    r"(?:let\s+)?(?:jarvis\s+)?speak\s+up\s+(less|less\s+often|more|more\s+often)")
_BRIEF_AT = re.compile(
    r"(?:the\s+)?(?:brief|digest)\s+(?:arrives?\s+|comes?\s+)?at\s+(\d{1,2})\s*"
    r"(am|pm|in\s+the\s+morning|in\s+the\s+afternoon|in\s+the\s+evening|at\s+night)?")


def _brief_hour(hour: int, part: Optional[str]) -> Optional[int]:
    """A spoken hour as the 0-23 the settings file holds, or None.

    "8" on its own is 8 (the owner reading their own file), "8pm" is 20, and
    "7 in the morning" is 7. 12am is midnight and 12pm is noon - the two the
    arithmetic gets wrong if it is not written down."""
    part = (part or "").strip()
    if not part:
        return hour if 0 <= hour <= 23 else None
    if part in ("am", "in the morning"):
        if hour == 12:
            return 0
        return hour if 1 <= hour <= 11 else None
    # pm / afternoon / evening / night
    if hour == 12:
        return 12
    return hour + 12 if 1 <= hour <= 11 else None


def _budget_intent(s: str) -> Optional[Intent]:
    m = _BUDGET_PER_DAY.fullmatch(s)
    if m:
        return Intent("settings_budget", {"body": {"spoken_per_day": int(m.group(1))}})
    m = _BUDGET_STEP.fullmatch(s)
    if m:
        return Intent("settings_budget", {"step": 1 if m.group(1).startswith("more") else -1})
    m = _BRIEF_AT.fullmatch(s)
    if m:
        hour = _brief_hour(int(m.group(1)), m.group(2))
        if hour is not None:
            return Intent("settings_budget", {"body": {"digest_hour": hour}})
    return None


#: How much of an approval card is shown at first, by asking (the owner's
#: request of 2026-10-09: "approval card preferences such as this should be
#: changeable in the settings"). Whole sentences only, like everything else
#: here, and the words are `jarvis_card_summary.spoken`'s own list - never
#: typed twice, and never guessed at.
#:
#:   "always show me the whole approval card" / "show the whole card"
#:   "start short" / "show the summary first"
def _card_mode_intent(s: str) -> Optional[Intent]:
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    mode = R.find_card_mode(s)
    if mode is None:
        return None
    return Intent("settings_card_mode", {"mode": mode})


def _settings_only(s: str) -> Optional[Intent]:
    """The owner's two Settings-only exceptions, refused deterministically."""
    if _SETTINGS_ONLY_RESTORE.fullmatch(s):
        return Intent("settings_only", {"which": "restore"})
    if _SETTINGS_ONLY_ACCOUNTS.fullmatch(s):
        return Intent("settings_only", {"which": "accounts"})
    return None


def _browser_mode_intent(s: str) -> Optional[Intent]:
    """Which browser Jarvis uses, from a whole sentence (2026-10-26).

    Deterministic like every other setting here: a value the browser does not
    have is answered with the real three, never guessed at and never handed to
    the model, which has no control for it."""
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    m = _BROWSER_MODE_TO.fullmatch(s)
    if m:
        value = m.group(1)
    else:
        m = _BROWSER_MODE_USE.fullmatch(s)
        if not m:
            return None
        value = m.group("mode")
    mode = R.browser_mode_from_words(value)
    if mode is None:
        return Intent("settings_browser_mode_bad", {"words": value})
    return Intent("settings_browser_mode", {"mode": mode})


def _settings_control(s: str) -> Optional[Intent]:
    """The generic "set <control> <field> to <value>" handler (ruling Q3).

    Closed-world: no control in jarvis_settings_registry.CONTROL_FIELDS -> None
    (falls through exactly as before). A named control answers deterministically:
    set, ask (fields + current values), or bad (valid values)."""
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    m = _CONTROL_TO.fullmatch(s)
    if m:
        got = R.resolve_control_sentence(m.group(1), m.group(2))
    else:
        m = _CONTROL_ADJUST_ONLY.fullmatch(s)
        if not m:
            return None
        got = R.resolve_control_sentence(m.group(1), None)
    kind = got.get("kind")
    if kind == "none":
        return None
    if kind == "set":
        return Intent("control_set", {"key": got["key"], "value": got["value"]})
    if kind == "ask":
        return Intent("control_ask", {"control": got["control"]})
    if kind == "bad":
        # The words the owner said come along too: a control with one field
        # answers a bad value by naming the wrong value and the real ones (see
        # _run_control_bad). Without it the answer read "face's face".
        return Intent("control_bad", {"control": got["control"],
                                      "field": got["field"],
                                      "value": got.get("value") or ""})
    return Intent("control_bad", {"control": got["control"], "field": "",
                                  "value": got.get("value") or ""})


def _settings_choice(s: str) -> Optional[Intent]:
    """The named-choice settings ("set it to a value"), 2026-10-22.

    Only a name in jarvis_settings_registry.CHOICE_SETTINGS may match. The
    value is looked up in that setting's OWN list; a value it does not have is
    answered with the real options ("settings_choice_bad"), never guessed at
    and never handed to the model. Anything else here returns None and falls
    through exactly as before."""
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    # "change your voice to Ashby" is deliberately NOT intercepted here: an
    # unoffered Jarvis-made blend is a value `voice_speaker` does not have, and
    # the generic path below answers it with the picker's own "not made yet"
    # sentence (`jarvis_settings_registry.choice_not_made_words`). A second
    # `voice_blend_help` intent for the same sentence was removed on
    # 2026-10-30: one sentence gets one deterministic answer, and main's
    # `backend/test_settings_registry.py` already pins this one.

    def one(key: str, name_words: str, value_words: str) -> Optional[Intent]:
        setting = next((c for c in R.CHOICE_SETTINGS if c.key == key), None)
        if setting is None:
            return None
        value = R.choice_from_words(setting, value_words)
        if value is None:
            return Intent("settings_choice_bad",
                          {"key": key, "words": " ".join(str(value_words).split())})
        return Intent("settings_choice", {"key": key, "value": value})

    def face_intent(words: str) -> Optional[Intent]:
        """One face from the words after the pattern, or the real list on a miss."""
        return one("face", "the face", words)

    for pattern in (_FACE_USE, _FACE_MAKE, _FACE_PUT_ON):
        m = pattern.fullmatch(s)
        if m:
            got = face_intent(m.group(1))
            if got is not None:
                return got
    if _FACE_ASK.fullmatch(s):
        return Intent("face_ask", {})

    m = _SET_HANDOFF_MODE.fullmatch(s)
    if m:
        value = m.group("value") if "value" in (m.groupdict() or {}) else ""
        if value:
            return one("handoff_mode", "the captcha hand-off", value)
        # "keep offering", "stop early", "be patient" without a named value.
        return one("handoff_mode", "the captcha hand-off",
                   "stop early" if "stop early" in s else "keep offering")
    m = _SET_HANDOFF_FRONT.fullmatch(s)
    if m:
        value = m.group("value") if "value" in (m.groupdict() or {}) else ""
        if value:
            return one("handoff_front", "the captcha window", value)
        return one("handoff_front", "the captcha window",
                   "leave it where it is" if s.startswith("leave") else "bring it to the front")
    m = _SET_PRESET_NATURAL.fullmatch(s)
    if m:
        value = " ".join(m.group(1).split())
        setting = next((c for c in R.CHOICE_SETTINGS if c.key == "focus_preset"), None)
        if setting is None:
            return None
        preset = R.choice_from_words(setting, value)
        if preset is not None:
            return Intent("settings_choice", {"key": "focus_preset", "value": preset})
    # "use the Clara voice", "switch to the Ashby voice" (2026-10-28). Only a
    # name the built-in voice list really has becomes an intent; anything else
    # falls through to the model exactly as it did before this pattern existed.
    m = _VOICE_USE.fullmatch(s)
    if m:
        setting = next((c for c in R.CHOICE_SETTINGS
                        if c.key == "voice_speaker"), None)
        chosen = (R.choice_from_words(setting, m.group(1))
                  if setting is not None else None)
        if chosen is not None:
            return Intent("settings_choice",
                          {"key": "voice_speaker", "value": chosen})
        # ...except a made-for-Jarvis blend this PC has not made (Ashby,
        # Clara): it is a real voice that is absent, so it gets the honest
        # "not made yet" answer rather than falling to the model (REPORT.md B3,
        # 2026-10-29 phone field test). Every other unknown name still falls
        # through as before - "use the passive voice" is not a voice request.
        said = (m.group(1) or "").strip()
        if setting is not None and R.choice_not_made_words(setting, said):
            return Intent("settings_choice_bad",
                          {"key": "voice_speaker", "words": said})
    m = _SET_CHOICE_HELP.fullmatch(s)
    if m:
        name = (m.group(1) or m.group(2) or "").strip()
        setting = R.find_choice_setting(name)
        if setting is not None:
            return Intent("settings_choice_help", {"key": setting.key})
    m = _SET_CHOICE_TO.fullmatch(s)
    if m:
        setting = R.find_choice_setting(m.group(1))
        if setting is not None:
            return one(setting.key, m.group(1), m.group(2))
    return None


#: A sentence that says out loud what it is: "change your settings: turn on
#: remembering sensitive topics automatically." The lead-in is the owner's
#: framing, not part of the setting's name, and it is peeled HERE (only for
#: the settings block) because the words after it are the same sentences the
#: patterns below already own. Narrow on purpose: it must name "settings", and
#: the rest must be there.
_SETTINGS_LEAD_SAID = re.compile(
    r"(?:change|update|adjust|edit|set)\s+(?:your|my|the)\s+(?:jarvis\s+)?settings?"
    r"\s*[:,;-]?\s*(.+)")


def _settings_adjust(s: str) -> Optional[Intent]:
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    m = _SETTINGS_LEAD_SAID.fullmatch(s)
    if m:
        s = m.group(1).strip()
    # The interruption budget first: its sentences are the most specific ones
    # here ("speak up 3 times a day"), so nothing below can swallow one.
    budget = _budget_intent(s)
    if budget is not None:
        return budget
    # How much of an approval card is shown (the owner's request of
    # 2026-10-09). Before the on/off block below, which would otherwise read
    # "show the whole card" as a setting named "the whole card" and refuse it.
    cards = _card_mode_intent(s)
    if cards is not None:
        return cards
    # The Anti-Slop filter's own three sentences (2026-10-28). BEFORE the
    # on/off block: "turn on anti-slop for code" must not be read as the whole
    # switch, and "set anti-slop mode to after" is a value, not a state.
    got = _antislop_intent(s)
    if got is not None:
        return got
    # The PC's own "hey Jarvis" switch and which browser Jarvis uses
    # (2026-10-26). Neither is a BOOL_SETTINGS/CHOICE_SETTINGS row - see
    # jarvis_settings_registry's own block for why - so neither is reachable
    # through the blocks below; both are real routes with their own setters,
    # and both answer here rather than falling to the model, which has no
    # control for either.
    m = _WAKE_WORD.fullmatch(s)
    if m:
        on = ((m.group("on") or m.group("on2") or "") == "on"
              or (m.group("enable") or "") == "enable")
        return Intent("settings_wake_word", {"on": bool(on)})
    got = _browser_mode_intent(s)
    if got is not None:
        return got
    m = _TOOL_ON.fullmatch(s) or _TOOL_OFF.fullmatch(s)
    if m:
        tool = R.find_tool_target(m.group(1))
        if tool is not None:
            return Intent("settings_tool", {"tool": tool, "on": bool(_TOOL_ON.fullmatch(s))})
    m = _ASKS_FIRST_LOOSER.fullmatch(s) or _ASKS_FIRST_STRICTER.fullmatch(s)
    if m:
        action = R.find_asks_first_target(m.group(1))
        if action is not None:
            return Intent("settings_asks_first",
                          {"action": action, "ask": bool(_ASKS_FIRST_STRICTER.fullmatch(s))})
    m = _ADJUST_ONOFF.fullmatch(s)
    if m:
        g = m.groups()
        if g[0] is not None:            # "turn/switch on|off <name>"
            on, name = g[0] == "on", g[1]
        elif g[2] is not None:          # "enable <name>"
            on, name = True, g[3]
        else:                           # "disable <name>"
            on, name = False, g[5]
        # THE PAGE-ONLY ANSWER IS DECIDED FIRST, ON THE SAME FILLER-TOLERANT
        # WORDS THE SWITCH MATCHER USES (2026-10-26). This guard used to be the
        # exact spoken lookup, so one natural filler word defeated it:
        # "turn off the windows hello for memory lists and chat history
        # setting" missed the page-only row, fell to `find_bool_setting_words`,
        # and that matcher read `chat_history` inside the SAME words - turning
        # chat-history retention off at once, with no card, for a switch this
        # backend has no route for. `page_only_asked` strips the same filler the
        # switch matcher strips AND refuses when the sentence names ANY
        # page-only row, so two of them ("the app lock and windows hello for
        # memory lists and chat history") can no longer fall through to a switch
        # either. It runs BEFORE any switch is resolved; no second exact check
        # is needed below, because the tolerant lookup is a superset.
        dom_id, mixed = R.page_only_asked(name)
        if dom_id is not None:
            return Intent("settings_not_by_asking",
                          {"dom_id": dom_id, "mixed": bool(mixed)})
        setting = R.find_bool_setting(name)
        if setting is None:
            # THE OWNER'S OWN WORDS FOR A REAL SWITCH (D5, the live campaign of
            # 2026-10-25). "Turn on learning in the background" named
            # `background_learning` to a person and to no matcher here, so it
            # fell to the model, which has no settings tool and answered "It is
            # not available to me" - a denial of a setting that exists, with no
            # card. The registry's own word-tolerant matcher is the one the
            # model's restatements already pass through, and its rules are the
            # safe ones: it accepts the words only when they exactly ARE one
            # switch's name (after filler is removed) or CONTAIN a whole one,
            # it refuses a bare one-word name, and it refuses ambiguity rather
            # than guess. So "learning in the background" reaches
            # background_learning's own setter - the same function, card, tier
            # and PC-only check a tap in Settings uses - and "turn off the
            # kitchen light" still falls through, because no switch's whole
            # name is in those words.
            setting = R.find_bool_setting_words(name)
        if setting is not None:
            return Intent("settings_bool", {"key": setting.key, "on": on})
    # "connect my calendar", "set up github", "is my calendar connected?"
    # (2026-10-28, the owner's ask). BEFORE the Settings-only refusal below,
    # because that sentence is exactly what this replaces for these services -
    # the card types them on the PC, the same act Settings performs. See
    # `_connect` for why nothing else changes hands.
    #
    # A sentence that names GOOGLE or EMAIL is answered one step earlier
    # (2026-10-29, the HUD field test): it names two different things with two
    # different real paths, and one card cannot be the answer to both. Nothing
    # else moves - "connect my calendar" still raises the iCal card.
    got = _accounts_connect(s)
    if got is not None:
        return got
    got = _connect(s)
    if got is not None:
        return got
    # The owner's two Settings-only exceptions are refused before anything
    # else can read them as a setting (ruling Q3.3, 2026-10-22).
    got = _settings_only(s)
    if got is not None:
        return got
    # The ONE generic multi-field grammar (ruling Q3): closed vocabulary, asks
    # on ambiguity, never falls through to the model for a named control.
    got = _settings_control(s)
    if got is not None:
        return got
    # The named-choice settings ("set the voice speed to faster", "keep my
    # chats for 30 days", "bring the captcha window to the front") - 2026-10-22.
    got = _settings_choice(s)
    if got is not None:
        return got
    # A sentence that clearly asks to change A SETTING, naming one nothing
    # above knows: "turn off the turbo setting", "change my security settings",
    # "enable the settings thing". Answered honestly rather than handed to the
    # model. The word "setting"/"settings" is required, deliberately: a device
    # ("turn off the kitchen light") and every other feature reachable from a
    # chat turn do not carry it, so nothing already answered changes hands -
    # and `_settings_help` above has already claimed "what can I change?".
    if _SETTING_UNKNOWN.fullmatch(s):
        return Intent("settings_unknown")
    return None


# --------------------------------------------------------------------------
#   Explaining Jarvis's own features (2026-10-20)
#
#   THE FIELD-TEST GAP (2026-10-19/20): "how do I turn on the prompt coach?"
#   was answered thinly by the model, and "is the prompt coach on?" got "I
#   don't know its current state directly". These are whole-sentence fixed
#   phrases answered from the owner's own feature list by jarvis_feature_guide,
#   with NO model - so they work with any model, a slow one, or none.
#
#   NOT A LAND GRAB. Every pattern here needs the words after it to NAME a
#   real feature (or a real switch), or the sentence clearly says "feature";
#   anything else falls through to the model/other paths exactly as before, so
#   "what is the weather", "is the oven on" and "how do I turn on my phone's
#   bluetooth" are not answered with some feature's facts. `test_feature_guide.py`
#   proves the near misses still fall through.
# --------------------------------------------------------------------------

_FEATURES_LIST = re.compile(
    r"(?:what|which)\s+features?\s+(?:do\s+you\s+have|are\s+there|does\s+jarvis\s+have"
    r"|can\s+you\s+explain|have\s+you\s+got)"
    r"|(?:list|show|name)\s+(?:me\s+)?(?:the\s+|your\s+|all\s+)?features?(?:\s+groups?)?"
    r"|what\s+are\s+(?:the|your)\s+features?"
    r"|(?:list|show|name)\s+(?:me\s+)?(?:the\s+)?feature\s+groups?"
    r"|what\s+feature\s+groups?\s+(?:are\s+there|do\s+you\s+have)")
#: Cloud-sync questions get the guide's fixed privacy answer instead of the model
#: (Gemini post-review HIGH-4, 2026-10-20): the model used to pad "I do not have
#: that" with generic OneDrive/Google Drive advice, which nudges the owner toward
#: pointing a third-party sync folder at Jarvis's private folders. This matcher
#: is deliberately topic-specific - a bare "sync my files" is not enough.
_CLOUD_SYNC_TOPIC = re.compile(
    r"(?:cloud\s+(?:sync|storage|backup)"
    r"|sync\s+(?:across|between)\s+(?:devices|my\s+devices)"
    r"|one\s*drive|google\s+drive|dropbox|icloud)")
_FEATURES_GROUP = re.compile(
    r"(?:list|show|name)\s+(?:me\s+)?(?:the\s+|your\s+)?(.+?)\s+(?:feature\s+group|group|features)"
    r"|what(?:'s|\s+is)\s+in\s+(?:the\s+|your\s+)?(.+?)\s+(?:feature\s+group|group)")
_FEATURE_HOWTO = re.compile(
    r"how\s+(?:do|can|should|would)\s+i\s+(?:turn|switch)\s+(on|off)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|how\s+(?:do|can)\s+i\s+(enable|disable)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|how\s+to\s+(?:turn|switch)\s+(on|off)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|where\s+(?:do|can)\s+i\s+(?:turn|switch)\s+(on|off)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|where\s+do\s+i\s+(enable|disable)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
#: "how do I train/teach you to <x>" - a how-to about USING a feature, not
#: switching it (added 2026-10-20 with the "Write like me" row: "how do I train
#: you to write like me?" must answer with that feature's OWN facts). The
#: answer is the feature's `where`/`asks`, so it is the explain intent.
_FEATURE_TRAIN = re.compile(
    r"how\s+(?:do|can|should)\s+i\s+(?:train|teach)\s+(?:you|jarvis)\s+to\s+(.+)")
#: "is <thing> on?" - the exact job the field test found missing.
_FEATURE_STATE = re.compile(
    r"is\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+(?:turned\s+on|switched\s+on"
    r"|turned\s+off|switched\s+off|on|off|enabled|disabled)"
    r"(?:\s+(?:right\s+now|now|currently|at\s+the\s+moment))?"
    r"|what(?:'s|\s+is)\s+the\s+state\s+of\s+(?:the\s+|my\s+|a\s+)?(.+)")
_FEATURE_WHAT = re.compile(
    r"(?:what\s+is|what's|whats)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)"
    r"(?:\s+(?:feature|option|setting))?"
    r"|what\s+does\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+do"
    r"|tell\s+me\s+about\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|explain\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
#: "how do I use <feature>", "how does <feature> work" - how to START it, as
#: opposed to switching it on (2026-10-26, the owner's requested phrasings). An
#: ability with no switch is used by asking, so the explain answer is the right
#: one: its `where`, `asks`, the example sentence and the Settings place.
_FEATURE_USE = re.compile(
    r"how\s+(?:do|can|should|would)\s+i\s+(?:use|try|set\s+up|start\s+using"
    r"|get\s+started\s+with)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|how\s+does\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+work")
#: "where is <feature>", "where do I find <feature>" - the explain answer's own
#: `where` line. Only an exact name answers: "where is my file manager" keeps
#: its own path (jarvis_places, and the model after it).
_FEATURE_WHERE = re.compile(
    r"where\s+(?:is|can\s+i\s+find|do\s+i\s+find|do\s+i\s+see|can\s+i\s+see)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    # "where do I change the presets?" (the owner's live field-test question,
    # 2026-10-26) matched nothing at all: "where do I change" is a where
    # question, not the "how do I change" one below. The same exact-name gate
    # applies, so "where do I change my wifi password" is still the model's.
    r"|where\s+do\s+i\s+(?:change|set|edit|adjust)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    # "how do I change the presets?" - the SAME question asked the other way
    # round (2026-10-26, part B). It is an alternative in this pattern, not a
    # new one, so it resolves through the same alias path ("presets" is
    # focus-presets' own alias) and gets the same full answer: the explain view
    # already ends with change_words(), which names the exact phrase or Settings
    # place. The change lane below keeps "can I change/adjust ...", "is it
    # adjustable" and "how do I adjust/edit/configure ...". The gate is
    # unchanged, so "how do I change my password" still falls through to the
    # model rather than being hijacked.
    r"|how\s+do\s+i\s+change\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|where\s+in\s+jarvis\s+is\s+(?:the\s+|my\s+)?(.+)")
#: "can I change <feature>", "how do I change <feature>", "is it adjustable" -
#: answered from the five owner-facing labels and the real switch table, never
#: by changing anything (2026-10-26).
_FEATURE_CHANGE = re.compile(
    r"can\s+i\s+(?:change|adjust|switch|turn\s+(?:on|off))\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|how\s+(?:do|can)\s+i\s+(?:change|adjust|edit|configure)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|is\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+(?:changeable|adjustable"
    r"|configurable|customi[sz]able)"
    r"|can\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+be\s+(?:changed|adjusted"
    r"|turned\s+(?:on|off))")
#: "turn on <feature>" - runs AFTER jarvis_settings_registry's own exact-name
#: phrases, so every setting already worded keeps its old path and words. A
#: feature that names several switches changes NOTHING and says which ones.
_FEATURE_SWITCH = re.compile(
    r"(?:turn|switch)\s+(on|off)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|(?:turn|switch)\s+(?:the\s+|my\s+|a\s+)?(.+?)\s+(on|off)"
    r"|(enable|disable)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)")


# ---- "what can you do with the calendar?" (2026-10-31, the pass-9 field test)
#
# THE GAP: the owner asked their own chat box what Jarvis could do with the
# calendar, what its smart features were, what could be edited in their notes,
# and whether a folder could be protected from Jarvis. Only the time and the
# picture-in-picture answer were right; the other answers were the model's own
# prose, which over-claimed invitations and availability, said it was unaware
# of its own features, invented note editing and a filesystem-permissions
# workaround, and offered to read a phone's "notification history".
#
# These are capability questions about JARVIS's OWN features, so they are
# answered from jarvis_feature_guide's rows - the same list the owner reads on
# the Features page - with no model. Whole sentences only, like every fixed
# phrase here, so a general question keeps its own path. The "can you <verb>
# something ..." shape claims only an area the guide knows, so "can you add
# milk to my shopping list?" keeps its own (real) path; the plain
# "what can you do with X" shapes always answer, with the guide's honest
# "that is not one of my features" when X is not in the list.
_CAP_AREA_NOUNS = (
    # `settings`/`setting` are deliberately NOT here: "what can I change in
    # settings" is a SETTINGS-HELP question that jarvis_settings_registry's
    # own answer owns (`_SETTINGS_HELP`, checked later in match() on purpose -
    # the help answer names a real Settings change and its card rule). Claiming
    # the `what can I <verb> ... in settings` shape here captured it first and
    # broke `test_settings_help.py` (CI 2026-10-31). The bare `what can you do
    # with settings?` capability shape below still answers from the list.
    r"(?:calendar|notes?|reminders?|alarms?|timers?|emails?|mail|memory|"
    r"pictures?|photos?|phone|folders?|files?|documents?|weather|news|"
    r"models?|updates?|tasks?|lists?)")
_CAPS_WHAT = re.compile(
    r"(?:what|which)\s+(?:can|could)\s+(?:you|jarvis)\s+do\s+"
    r"(?:with|about|for|in|on)\s+(?:the\s+|my\s+|your\s+)?(.+)"
    r"|what\s+are\s+(?:the\s+)?(?:smart\s+)?features?\s+of\s+"
    r"(?:the\s+|my\s+|your\s+)?(.+)"
    r"|what\s+features?\s+(?:does|do)\s+(?:jarvis|you)\s+have\s+"
    r"(?:for|with|about|in|on)\s+(?:the\s+|my\s+)?(.+)")
_CAPS_EDIT = re.compile(
    r"what\s+can\s+(?:you|i|jarvis)\s+"
    r"(?P<verb>add|create|make|put|edit|change|delete|remove|rename|see|view|"
    r"read|check|find|search|open|use|track|schedule|cancel|stop|start|share|"
    r"send|write|save|move|copy|update|manage|control)\s+"
    r"(?:something\s+|anything\s+|a\s+|an\s+|the\s+)?(?:in|on|with|to|about|for)\s+"
    r"(?:the\s+|my\s+|your\s+)?(?P<area>" + _CAP_AREA_NOUNS + r")\b.*")
_CAPS_CAN = re.compile(
    r"can\s+(?:you|jarvis)\s+"
    r"(?P<verb>add|create|make|put|edit|change|delete|remove|rename|see|view|"
    r"read|check|find|search|open|use|track|schedule|cancel|stop|start|share|"
    r"send|write|save|move|copy|update|manage|control)\s+"
    r"(?:something|anything|some\s+things?)\s+"
    r"(?:to|in|on|into|from|with|for)\s+(?:the\s+|my\s+|your\s+)?"
    r"(?P<area>" + _CAP_AREA_NOUNS + r")\b.*")
_CAPS_PROTECT = re.compile(
    r"can\s+(?:i|you|jarvis)\s+(?:protect|block)\s+(?:a\s+|the\s+|my\s+)?"
    r"(?:folder|file|program)s?\s+from\s+(?:you|jarvis)\??")


# ---- discussion/explanation shapes (2026-10-31, pass-11 audit) -------------
# THE AUDIT: `tell me about X` and `how does X work` answered from the guide for
# 25/25 features, but `what are the limits of X` had NO path (3/25 right, 22
# invented or described a different product), the overview was only a sayable
# list, and a comparison was the model's generic prose. These patterns resolve
# the SAME row `feature_explain` resolves and let the guide quote its own
# fields; anything that names no catalogue row falls through to the model (or,
# when the sentence explicitly says "Jarvis"/"feature", the existing honest
# "not one of my features" answer).
_FEATURE_LIMITS = re.compile(
    r"(?:what\s+are|what's|what\s+is)\s+(?:the\s+)?limits?\s+(?:of|for|on)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
_FEATURE_ASKS = re.compile(
    r"(?:does|do)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+(?:ask|asks)"
    r"(?:\s+first|\s+you|\s+for\s+(?:approval|permission))?")
_FEATURE_APP = re.compile(
    r"which\s+app(?:s)?\s+(?:can|does|do|has|have)\s+(?:use|have|run|get)?\s*"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|which\s+app\s+is\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+(?:on|in)"
    r"|what\s+app(?:s)?\s+(?:can|does|do)\s+(?:use|have|run|get)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
_FEATURE_WHY = re.compile(
    r"why\s+(?:would|should|do)\s+(?:i|you)\s+(?:use|want|need|care\s+about)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
_FEATURE_DIFFERENCE = re.compile(
    r"(?:what(?:'s| is)\s+)?(?:the\s+)?difference\s+between\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+and\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|compare\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+(?:and|with|to)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)"
    r"|(?:the\s+|my\s+)?(.+?)\s+vs\.?\s+(?:the\s+|my\s+)?(.+)")
_FEATURE_ON_OFF = re.compile(
    r"is\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+(?:on|off)\s+or\s+(?:on|off)")
#: "how do timers work?" - a how-it-works question about a row whose name is
#: plural or phrased differently ("Timers, alarms, reminders and lists").
#: Resolved through the guide's own loose name match, never guessed.
_FEATURE_HOW_WORKS = re.compile(
    r"how\s+(?:do|does)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+work")
_FEATURE_OVERVIEW = re.compile(
    r"what\s+can\s+(?:you|jarvis)\s+do(?:\s+here)?"
    r"|what\s+are\s+(?:your|jarvis'?s?)\s+capabilities"
    r"|what\s+(?:is|does)\s+jarvis\s+able\s+to\s+do"
    r"|list\s+(?:me\s+)?what\s+(?:you|jarvis)\s+can\s+do")
_FEATURE_OVERVIEW_ABOUT = re.compile(
    r"what\s+can\s+(?:you|jarvis)\s+do\s+about\s+(?:the\s+|my\s+)?(.+)")

# ---- detail shapes (2026-10-31, the owner's "talk about all features in
# detail" ask) ---------------------------------------------------------------
# These are DEEPER than explain: the guide's detail() quotes every own field
# (what, where, example, asks, limit, state, surface, needs) and the state read
# at answer time. Each pattern resolves the SAME row the explain shapes resolve;
# an unknown name falls through to the model (or the honest answer when the
# sentence explicitly says Jarvis/a feature), exactly like the discussion shapes.
_FEAT_DETAIL = re.compile(
    r"(?:explain|describe)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+in\s+detail"
    r"|tell\s+me\s+(?:everything|all)\s+about\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
_FEAT_HOW_USE = re.compile(
    r"how\s+(?:do|can|should|would)\s+i\s+"
    r"(?:set\s+(?P<setup>.+?)\s+up"
    r"|(?:use|try|start\s+using|get\s+started\s+with|set\s+up)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(?P<use>.+))")
_FEAT_EXAMPLE = re.compile(
    r"(?:give\s+me\s+an?\s+example\s+of|what\s+do\s+i\s+say\s+to\s+use)\s+"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
_FEAT_PRIVATE = re.compile(
    r"is\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+private")
_FEAT_NEEDS = re.compile(
    r"what\s+(?:does|do)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+"
    r"(?:need|require)")
_FEAT_WHY_STATE = re.compile(
    r"why\s+is\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+"
    r"(?:on|off|enabled|disabled|switched\s+(?:on|off))")
_FEAT_WRONG = re.compile(
    r"what\s+can\s+go\s+wrong\s+with\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
_FEAT_CAN_DO = re.compile(
    r"can\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+do\s+(.+)")
_FEAT_LIKE = re.compile(
    r"what\s+is\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)\s+like")


def _feature_capabilities(s: str) -> Optional[Intent]:
    """Capability questions the feature list can answer, or None (2026-10-31)."""
    m = _CAPS_PROTECT.fullmatch(s)
    if m:
        # "can I protect a folder from you?" is the Protected from Jarvis row
        # (the owner's list, 2026-10-31). The row's own title is the area, so
        # the answer is that row's words - never a filesystem-permissions
        # workaround.
        return Intent("feature_capabilities", {"words": "protected from jarvis"})
    m = _CAPS_EDIT.fullmatch(s)
    if m:
        return Intent("feature_capabilities",
                      {"words": m.group("area"), "verb": m.group("verb")})
    m = _CAPS_CAN.fullmatch(s)
    if m:
        # Only an area the feature list really knows is claimed, so a request
        # that happens to use this shape ("add milk to my shopping list") keeps
        # the path that can actually do it.
        FG = _guide()
        if FG is None:
            return None
        area, verb = m.group("area"), m.group("verb")
        try:
            out = FG.capabilities(area, verb=verb)
        except Exception:
            return None
        if out.get("kind") != "unknown":
            return Intent("feature_capabilities", {"words": area, "verb": verb})
        return None
    m = _CAPS_WHAT.fullmatch(s)
    if m:
        area = next((got for got in m.groups() if got), "")
        if area:
            return Intent("feature_capabilities", {"words": area})
    return None



# --------------------------------------------------------------------------
# Timers, alarms and reminders capability answers (2026-10-31 honesty fix)
#
# The owner asked "can you make a reminder for me" and the model said it could
# not set a system-wide alarm and could only "note reminders in my calendar" -
# false. The real feature is jarvis_schedule.py (set_reminder/set_timer/
# set_alarm quick intents, the Coming up list) plus the desktop's Windows
# notification (jarvis-desktop/src-tauri/src/brain/schedule.rs: toast_fired,
# rings(), notifications.rs) and the phone's Android notification while it is
# connected (jarvis-client/.../service/ScheduleNotifier.kt - "THE PC IS THE
# CLOCK ... Nothing here sets an alarm on the phone").
#
# These constants are the measured truth table the answers are built from.
# A REAL request with a time or a thing ("remind me to call Mom at 6pm") is
# never claimed here: the matcher refuses any sentence carrying a time or a
# duration, so the existing reminder_set/timer_set/alarm_set paths keep it.
# --------------------------------------------------------------------------

REMINDER_SURFACES = (
    ("desktop", "Brain, Work, Coming up; the HUD's Reminders panel (#rail-reminders)"),
    ("desktop-toast", "a Windows notification while Jarvis is running"),
    ("desktop-late", "a late alarm rings only at most 10 minutes late; after that it is a quiet missed note"),
    ("desktop-closed", "with the Jarvis app fully closed no notification appears at the time; the job is kept and shows when Jarvis opens"),
    ("phone", "the phone shows an Android notification while it is connected to the PC; the PC is the clock and the phone sets no alarm of its own"),
)

_REMINDER_WORDS = re.compile(r"\b(?:reminder|reminders|timer|timers|alarm|alarms|remind)\b")
_REMINDER_REAL_TIME = re.compile(
    r"\b(?:for|in)\s+\d+|\bat\s+\d|\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|"
    r"\b(?:tomorrow|tonight|today|noon|midnight|monday|tuesday|wednesday|thursday|"
    r"friday|saturday|sunday|every\s+\w+)\b|\b\d+\s*(?:seconds?|minutes?|hours?|days?)\b")

_REMINDER_POPUP_RX = re.compile(
    r"\b(?:pop\s*up|popup|show up|appear)\b.*\b(?:computer|pc|screen|desktop)\b|"
    r"\b(?:will|does|do)\s+(?:it|they|you)\b.*\b(?:pop\s*up|popup|show up|appear)\b")
_REMINDER_SOUND_RX = re.compile(
    r"\b(?:ring|rings|ringing|sound|sounds|beep|beeps|noise|alert)\b")
_REMINDER_NOTIFY_RX = re.compile(
    r"\b(?:system|windows|desktop|pc)\s+notifications?\b|"
    r"\b(?:do|does|will|can)\s+you\s+(?:show|send|display)\b.*\bnotifications?\b")
_REMINDER_CLOSED_RX = re.compile(
    r"\b(?:app|jarvis|computer|pc)\b.*\b(?:closed|off|shut\s*down|not\s+running)\b|"
    r"\beven\s+if\b.*\bclosed\b")
_REMINDER_HOWTO_RX = re.compile(
    r"\bhow\s+(?:do|can|should)\s+i\s+(?:ask|set|make|create|add)\b|"
    r"what\s+(?:do|should)\s+i\s+say\b")


def _reminders_question(raw) -> Optional[Intent]:
    """Capability questions about timers/alarms/reminders, from the RAW sentence.

    None when the sentence already carries a time or a duration (a real
    request), when it is ordinary conversation ("remind me what we said"), or
    when it is about something else entirely. No card and no state: the answer
    is fixed words built from REMINDER_SURFACES.
    """
    text = " ".join(str(raw or "").strip().lower().rstrip("?.!").split())
    text = re.sub(r"^(?:hey\s+|ok\s+|okay\s+)?jarvis[,: ]+", "", text)
    if not text or len(text) > 400:
        return None
    # A Settings sentence ("turn on Reminder sounds", "turn off ... notifications")
    # belongs to the feature-control grammar, not to this capability family.
    if re.match(r"(?:turn|switch)\s+(?:on|off)\b|\b(?:enable|disable)\b", text):
        return None
    if _REMINDER_REAL_TIME.search(text):
        return None                         # the real set_reminder/timer path keeps it
    if _REMINDER_CLOSED_RX.search(text):
        return Intent("reminder_closed", {"surface": "closed"})
    if _REMINDER_HOWTO_RX.search(text):
        return Intent("reminder_howto", {"surface": "howto"})
    if _REMINDER_POPUP_RX.search(text):
        return Intent("reminder_popup", {"surface": "popup"})
    if _REMINDER_SOUND_RX.search(text):
        return Intent("reminder_sound", {"surface": "sound"})
    if _REMINDER_NOTIFY_RX.search(text):
        return Intent("reminder_notify", {"surface": "notify"})
    if _REMINDER_WORDS.search(text) and re.search(
            r"\bcan\s+you\b|\bcould\s+you\b|\bdo\s+you\b", text):
        return Intent("reminder_capability", {"surface": "capability"})
    return None


def _reminder_phone_note() -> str:
    return (" On the phone: while it is connected to the PC it shows an Android notification too, "
            "but the PC is the clock and the phone sets no alarm of its own.")


def _run_reminders(name: str, surface: str) -> "Result":
    """Fixed, read-only answers from the measured truth table."""
    phone = surface == "phone"
    suffix = _reminder_phone_note()
    if name == "reminder_capability":
        if phone:
            return Result("Yes - the timers, alarms and reminders live on the PC running Jarvis. "
                          "Ask the PC \"remind me to call Mom at 6pm\", \"set a timer for 10 minutes\" "
                          "or \"set an alarm for 7am\". They show in Brain, Work, Coming up on the PC, "
                          "and the PC shows a Windows notification when one goes off (an alarm keeps "
                          "ringing, a reminder or timer shows once)." + suffix +
                          " If the PC's Jarvis is fully closed, no notification appears then, but the "
                          "job is kept and appears when you open Jarvis; an alarm more than 10 minutes "
                          "late is a quiet missed note.", "reminder_capability")
        return Result("Yes. I keep timers, alarms, reminders and lists on this PC - ask \"remind me to "
                      "call Mom at 6pm\", \"set a timer for 10 minutes\" or \"set an alarm for 7am\". They "
                      "appear in Brain, Work, Coming up and the HUD's Reminders panel. When one goes off "
                      "the PC shows a Windows notification while Jarvis is running: an alarm keeps ringing, "
                      "a reminder or a timer shows once." + suffix +
                      " If the Jarvis app is fully closed, no notification appears at the time, but the job "
                      "is kept and shows when you open Jarvis; an alarm more than 10 minutes late is a quiet "
                      "missed note.", "reminder_capability")
    if name == "reminder_popup":
        base = ("Yes - while Jarvis is running on the PC. A timer, alarm or reminder that goes off shows a "
                "Windows notification (with the job's own words unless App lock or the hidden lists are on, "
                "when it says only what kind of thing is due). An alarm keeps ringing; a reminder or timer "
                "shows once.")
        if phone:
            return Result("On the PC, yes - while Jarvis is running it shows a Windows notification" + suffix,
                          "reminder_popup")
        return Result(base + suffix +
                      " If the PC's Jarvis is fully closed, no pop-up appears at the time; the job is kept "
                      "and shows in Coming up when you open it. A late alarm rings only if it is at most "
                      "10 minutes late.", "reminder_popup")
    if name == "reminder_sound":
        base = ("On the PC, an alarm keeps ringing until it is dismissed; a reminder or a timer makes the "
                "normal Windows notification sound once. The alarm is never held back by quiet hours, "
                "reminders can be.")
        if phone:
            return Result("On the PC, an alarm keeps ringing and a reminder or timer makes the normal "
                          "Windows notification sound once." + suffix, "reminder_sound")
        return Result(base + suffix, "reminder_sound")
    if name == "reminder_notify":
        base = ("Yes, on the PC: it is a Windows notification (a toast) posted while Jarvis is running - "
                "not a separate system alarm service. Alarms and reminders can each be switched off in "
                "Settings, Notifications, and quiet hours hold back reminders but never an alarm.")
        if phone:
            return Result("On the PC it is a Windows notification while Jarvis is running." + suffix,
                          "reminder_notify")
        return Result(base + suffix, "reminder_notify")
    if name == "reminder_closed":
        base = ("No notification appears at the moment it is due while the Jarvis app is fully closed. "
                "The PC keeps the job, and when you open Jarvis it is in Coming up; if it is an alarm that "
                "went off more than 10 minutes late it is a quiet note saying it was missed, not a ring. "
                "The phone shows an Android notification only while it is connected to the PC.")
        return Result(("On the phone: " if phone else "") + base, "reminder_closed")
    if name == "reminder_howto":
        return Result("Say or type, for example: \"remind me to call Mom at 6pm\", \"set a timer for 10 "
                      "minutes\", \"set an alarm for 7am\", or \"add milk to my shopping list\". Timers, "
                      "one-time reminders and alarms need no approval card; they appear in Brain, Work, "
                      "Coming up and the HUD's Reminders panel." + suffix, "reminder_howto")
    return Result("Yes - see Brain, Work, Coming up for timers, alarms and reminders on this PC.",
                  "reminder_capability")



# --------------------------------------------------------------------------
# Drop-in plug-ins: the measured catalogue (2026-10-31 honesty fix)
#
# The live owner asked "what plug-ins do you have integrated into you?" and
# the model said it had no plug-ins, only built-in capabilities. False: the
# loader (backend/jarvis_plugins.py) imports every folder in jarvis_plugins\
# beside jarvis_hud.py and calls its own install(); plugins/ready/ holds 45
# drop-in modules and plugins/loader/README.md documents it. This table is
# generated from those folders' own plugin.json summaries and pinned by
# backend/test_plugins_honesty.py, so a plug-in cannot silently vanish from
# the answer. The installed state is read at runtime from jarvis_plugins.discover().
# --------------------------------------------------------------------------

PLUGIN_CATALOGUE = (
    ('android-builder', 'Build the Android app in one of your app tasks with Gradle, and put it on your phone over the cable: one approval card for the build and one for th...'),
    ('antislop', "the Anti-Slop filter: miqdadbadjuber/anti-slop's rules, distilled, so Jarvis writes and builds without the AI tells - no em dashes in prose, no buz..."),
    ('auto-router', 'estimate what a turn will cost on this PC, and advise when a cloud lane would be quicker - advice only: jarvis_router.choose() still decides, and a...'),
    ('brain-reads', "the Brain's read-only routes (the Brain upgrades, and a chat's facts)."),
    ('card-prefs', 'how much of an approval card is shown at first, and the setting that decides it, kept where BOTH apps can read it.'),
    ('chatbot-limits-hud', "the monthly money limits and the price list for the chatbot driver's API services, set from the PC's own app."),
    ('chatbot-routes', 'the routes both apps use to have Jarvis talk to an AI chatbot for the owner.'),
    ('decks', 'review decks.'),
    ('docker', "the containers on Jarvis's OWN list, and start/stop for them."),
    ('documents', '"Folders Jarvis may look in": finding files by name, searching inside notes and text files, reading PDFs, Word, Excel and PowerPoint files one part...'),
    ('goals', '"Goals with one card per step".'),
    ('google-calendar', 'Google Calendar, both ways: the private iCal link (read-only) or a real Google sign-in over a loopback redirect (read/write), one active at a time...'),
    ('history-import', '"Bring in chats from ChatGPT, Claude, Gemini or DeepSeek".'),
    ('jarvis-calendar', "Jarvis's own local calendar: events kept on this PC, shown beside Google Calendar and iCal and never synced out - ON by default, and one switch tur..."),
    ('live', 'Jarvis Live: a back-and-forth voice conversation the owner starts and stops, with no "hey Jarvis" between turns.'),
    ('media-index', 'searchable recordings and videos: GET/POST /api/media-index, so both apps can read the switch, the disclosure and the counts, turn it off at once (...'),
    ('media', '"pause", "next song", "what\'s playing": play, pause, next, previous and now-playing for whatever is playing on this PC (Spotify, a browser tab, or...'),
    ('model-lanes', 'the button that starts the model lane that is down.'),
    ('model-recommendations', 'suggest a better local model, measure it, and suggest which preset should use it. Nothing here downloads, switches or applies.'),
    ('news', 'news headlines in the morning briefing, from RSS/Atom feed addresses the owner names.'),
    ('notes-edit', 'browse, open and edit any note in your Obsidian vault, from the desktop or the phone: one approval card per save, a File Guardian copy first, and t...'),
    ('notion-obsidian', 'bring a Notion export into an Obsidian vault: ids off the names, properties as frontmatter, databases as a note and a .base, links rewritten, attac...'),
    ('photo-reminder', '"Photo to reminder": a picture in, a PROPOSED reminder out. Nothing is set up here.'),
    ('picture-card', '"which card draws the pictures, and what the chat does about it".'),
    ('pictures', '"ask for a picture, and keep it" (the owner\'s decision of 2026-09-27: *"12 GB card: longer conversations with picture understanding first, and maki...'),
    ('progress', "the activity heatmap and the owner's balance chart (the owner's decision of 2026-09-30, docs/BUILD-QUEUE-2026-09-30.md item 7; docs/GOALS-PROGRESS-..."),
    ('projects', 'Projects, steps 1 and 2.'),
    ('protected-items', 'a list of folders, files and programs Jarvis may not touch: Blocked (no access) or Read-only (reads allowed, every write/action refused); one card...'),
    ('quiz', '"Quiz me on a text".'),
    ('receipts', 'action receipts and one-click undo: every action that CHANGES something leaves a receipt saying what changed, with one button to put it back.'),
    ('retirement', 'the retirement what-if calculator.'),
    ('sandbox', "the data and maths sandbox's own switch: GET/POST /api/sandbox, so both apps can read it and ask to turn it on (one approval card) or off (at once)."),
    ('screen-attach', '"look at this" can hand the owner the PICTURE, so they can say "look at this" with a chart or an error message and ask about it.'),
    ('secret-handoff', 'the host half of the owner-secret hand-off.'),
    ('self-improve', "two read-only diagnostic GETs: a file:line-cited answer to a question about Jarvis's own source, and the three-outcome check that Ollama is telling..."),
    ('send-file', "send ONE file from the owner's listed folders to the phone: one card showing the exact filename, folder and byte size, a ten-minute single-use opaq..."),
    ('setup', 'the setup questionnaire: a guided path through settings that already exist.'),
    ('skill-hub', "the skill library's other doors: a reference manual read only when it is asked for, leading /skill and /bundle chains, a project's own skills, and..."),
    ('sky', 'the sun, the moon and the weather behind the animal faces and the robot (which counts as an animal face for every option).'),
    ('spending', '"How much did I spend on food last month?", added up from a bank export the owner dropped into a folder Jarvis may look in.'),
    ('tool-updates', '"Check for tool updates", on request: is each Python package, Rust building block and pinned GitHub-hosted tool Jarvis is built from still the newe...'),
    ('tutorials', "Tutorials and the FAQ, for both apps, with the owner's progress."),
    ('vault-organizer', 'plan a tidy-up of an Obsidian vault without changing anything: tags merged, Map-of-Content hubs, a Vault Home - a read-only plan, OFF until the own...'),
    ('vault', 'a secret is kept in Windows Credential Manager and everything else carries its NAME - a handle, {{vault:github}} - never the value.'),
    ('voiceprint', "Write Like Me: Jarvis drafts in the owner's own voice, learned from his own words on his own PC, with names and numbers taken out before any of it..."),
)


def _plugin_entries():
    """The installed drop-in folders on THIS PC, or None when unreadable."""
    try:
        import jarvis_plugins as P
        return list(P.discover())
    except Exception:                       # noqa: BLE001 - module absent/broken
        return None


def _plugin_names():
    return [name for name, _summary in PLUGIN_CATALOGUE]


def _plugin_purpose(name: str) -> str:
    for n, summary in PLUGIN_CATALOGUE:
        if n == name:
            return summary
    return ""


def _plugin_installed_names(entries) -> list:
    if entries is None:
        return None
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("error"):
            continue
        folder = str(e.get("folder") or e.get("name") or e.get("module") or "")
        if not folder:
            continue
        out.append(folder)
    return out


def _plugin_list_sentence(installed) -> str:
    names = _plugin_names()
    if installed is None:
        head = ("Yes - Jarvis has a real drop-in plug-in system: " + str(len(names)) +
                " optional plug-ins are in the catalogue, each a folder under jarvis_plugins "
                "beside jarvis_hud.py. I cannot read the plug-in folder on this PC from here, "
                "so I cannot say which are installed right now.")
    elif installed:
        listed = installed[:8]
        more = len(installed) - len(listed)
        head = ("Yes - Jarvis has a real drop-in plug-in system, and " + str(len(installed)) +
                " plug-in(s) are installed on this PC: " +
                ", ".join(listed) + ((" and " + str(more) + " more") if more else "") + ".")
    else:
        head = ("Jarvis has a real drop-in plug-in system - " + str(len(names)) +
                " plug-ins are in the catalogue - but none are installed on this PC right now.")
    parts = [head]
    sample = names[:10]
    parts.append("The catalogue has " + str(len(names)) + " plug-ins; the first ten: " +
                 ", ".join(sample) + ".")
    if len(names) > len(sample):
        parts.append("There are " + str(len(names) - len(sample)) + " more.")
    parts.append("A plug-in is a folder under jarvis_plugins beside jarvis_hud.py; the loader "
                 "imports its module and calls its own install() at start-up. Add one with "
                 "scripts/add-plugin.ps1 -Name <name>, then restart Jarvis. The loader itself "
                 "raises no approval card; an installed plug-in's own feature keeps its own one card.")
    return " ".join(parts)


def _plugin_install_sentence() -> str:
    return ("Yes. On the PC, add a plug-in with scripts/add-plugin.ps1 -Name <name> (it copies "
            "the folder from plugins/ready/), or copy the folder into jarvis_plugins\\ beside "
            "jarvis_hud.py yourself, then restart Jarvis - the loader imports it at start-up. "
            "To switch one off, remove its folder or put a file named disabled in it, and restart. "
            "The loader itself raises no card; the plug-in's own feature keeps its own approval "
            "card where it has one. The phone cannot install or remove plug-ins: it uses the "
            "features once they are installed on the PC.")


def _plugin_installed_sentence(name: str, installed) -> str:
    wanted = " ".join(str(name or "").lower().split())
    for n in _plugin_names():
        if n.lower() == wanted or wanted == n.lower().replace("-", " "):
            if installed is None:
                return ("I cannot read the plug-in folder on this PC from here, so I cannot say "
                        "whether " + n + " is installed right now. It is in the catalogue.")
            if installed and n in installed:
                return ("Yes, " + n + " is installed on this PC. " + _plugin_purpose(n) +
                        " It is a folder under jarvis_plugins; restart Jarvis if it is not loaded.")
            return ("No, " + n + " is not installed on this PC right now, though it is in the "
                    "catalogue: " + _plugin_purpose(n) + " Add it with scripts/add-plugin.ps1 "
                    "-Name " + n + ", then restart Jarvis.")
    import difflib
    near = difflib.get_close_matches(wanted.replace(" ", "-"), _plugin_names(), n=3, cutoff=0.4)
    if not near:
        near = _plugin_names()[:3]
    return ("There isn't a Jarvis plug-in called \"" + str(name) + "\". The nearest real ones are " +
            ", ".join(near) + ".")


def _plugins_question(raw) -> Optional[Intent]:
    """Plug-in capability questions, from the RAW sentence (2026-10-31)."""
    text = " ".join(str(raw or "").strip().lower().rstrip("?.!").split())
    text = re.sub(r"^(?:hey\s+|ok\s+|okay\s+)?jarvis[,: ]+", "", text)
    if not text or len(text) > 400:
        return None
    # Not Jarvis's plug-ins: Obsidian, browsers, editors, WordPress, etc.
    if re.search(r"\b(?:obsidian|chrome|firefox|edge|browser|vscode|visual studio|wordpress|"
                 r"vst|audio|after effects|premiere|photoshop|figma|blender)\b", text):
        return None
    if "plug-in" not in text and "plugin" not in text:
        return None
    if re.search(r"\b(?:turn|switch)\s+(?:on|off)\b|\b(?:enable|disable)\b", text):
        return None
    if re.search(r"\b(?:what|which)\b.*\b(?:plug-?ins?)\b.*\b(?:integrated|installed|ready)\b", text) \
            or re.search(r"\b(?:integrated|built)\b.*\bplug-?ins?\b", text) \
            or re.search(r"\b(?:what|which)\s+plug-?ins?\b", text) \
            or re.search(r"\bplug-?ins?\b.*\b(?:do you have|have you got|are installed|available)\b", text):
        m = re.search(r"\b(?:what does|what is|what's|describe|explain)\s+(?:the\s+)?"
                      r"[\"']?(?P<name>[a-z0-9][a-z0-9 -]{0,40}?)[\"']?\s+plug-?in\b", text)
        if m:
            return Intent("plugin_about", {"name": m.group("name")})
        m = re.search(r"\b(?:what does|what is|what's|describe|explain)\s+(?:the\s+)?"
                      r"plug-?in\s+[\"']?(?P<name>[a-z0-9][a-z0-9 -]{0,40}?)[\"']?(?:\s+do)?\b", text)
        if m:
            return Intent("plugin_about", {"name": m.group("name")})
        m = re.search(r"\b(?:is|are)\s+(?:the\s+)?[\"']?(?P<name>[a-z0-9][a-z0-9 -]{0,40}?)[\"']?\s+"
                      r"(?:plug-?in\s+)?(?:installed|ready|enabled)\b", text)
        if m:
            return Intent("plugin_state", {"name": m.group("name")})
        if re.search(r"\b(?:can i|how do i|how can i|where do i)\b.*\b(?:install|add|enable|remove)\b", text):
            return Intent("plugin_install")
        if re.search(r"\b(?:what does|what is|what's|describe|explain)\b", text):
            m = re.search(r"plug-?in\s+(?:called\s+)?[\"']?(?P<name>[a-z0-9][a-z0-9 -]{0,40})", text)
            if m:
                return Intent("plugin_about", {"name": m.group("name")})
        return Intent("plugin_list")
    if re.search(r"\b(?:can i|how do i|how can i|where do i)\b.*\b(?:install|add|enable)\b.*"
                 r"\bplug-?in\b", text):
        return Intent("plugin_install")
    m = re.search(r"\b(?:what does|what is|what's|describe|explain)\s+(?:the\s+)?"
                  r"[\"']?(?P<name>[a-z0-9][a-z0-9 -]{0,40}?)[\"']?\s+plug-?in\b", text)
    if m:
        return Intent("plugin_about", {"name": m.group("name")})
    m = re.search(r"\b(?:is|are)\s+(?:the\s+)?[\"']?(?P<name>[a-z0-9][a-z0-9 -]{0,40}?)[\"']?\s+"
                  r"plug-?in\s+(?:installed|ready|enabled)\b", text)
    if m:
        return Intent("plugin_state", {"name": m.group("name")})
    m = re.search(r"\b(?:what does|what is|what's|describe|explain)\s+(?:the\s+)?"
                  r"plug-?in\s+[\"']?(?P<name>[a-z0-9][a-z0-9 -]{0,40}?)[\"']?(?:\s+do)?\b", text)
    if m:
        return Intent("plugin_about", {"name": m.group("name")})
    return None


def _run_plugins(name: str, f: dict, surface: str) -> "Result":
    installed = _plugin_installed_names(_plugin_entries())
    if name == "plugin_list":
        if surface == "phone":
            return Result("Jarvis's plug-ins are installed and managed on the PC, not on the phone - "
                          "the phone uses the feature once it is installed there. " +
                          _plugin_list_sentence(installed), "plugin_list")
        return Result(_plugin_list_sentence(installed), "plugin_list")
    if name == "plugin_state":
        return Result(_plugin_installed_sentence(str(f.get("name") or ""), installed), "plugin_state")
    if name == "plugin_about":
        target = str(f.get("name") or "")
        for n, summary in PLUGIN_CATALOGUE:
            if n.lower().replace("-", " ") == target.lower() or n.lower() == target.lower():
                return Result(n + ": " + summary, "plugin_about")
        import difflib
        near = difflib.get_close_matches(target.replace(" ", "-"), _plugin_names(), n=3, cutoff=0.4)
        return Result("There isn't a Jarvis plug-in called \"" + target + "\". The nearest real ones "
                      "are " + ", ".join(near or _plugin_names()[:3]) + ".", "plugin_about")
    if name == "plugin_install":
        return Result(_plugin_install_sentence(), "plugin_install")
    return Result(_plugin_list_sentence(installed), "plugin_list")



# --------------------------------------------------------------------------
# Android app building (2026-10-31 honesty fix)
#
# Measured: backend/jarvis_android_builder.py builds a FIXED minimal WebView
# Android project from the task's own index.html/app.js/app.css in one project
# task - `gradlew.bat assembleDebug` behind the app_build_android card, then
# `adb install -r <apk>` behind app_install_android. Needs the Android SDK,
# a Java 17 JDK, the Gradle wrapper files beside jarvis_hud.py, and a cable
# with USB debugging for the install; the first build downloads Gradle and the
# Android Gradle plugin. It never writes Kotlin/manifest itself, adds no
# permissions, no release signing and no Play Store. The live model said "I
# can't build Android apps... I don't have the tools to write code, compile
# projects", which is false.
# --------------------------------------------------------------------------

ANDROID_BUILD_ACTION = "app_build_android"
ANDROID_INSTALL_ACTION = "app_install_android"


def _android_state():
    """The real toolchain report, or None when the module is not installed."""
    try:
        import jarvis_android_builder as AB
        return AB.toolchain()
    except Exception:                       # noqa: BLE001 - module absent
        return None


def _android_missing_words(state) -> str:
    if state is None:
        return ("I cannot read the Android toolchain from here; on the PC the builder needs "
                "the Android SDK, a Java 17 JDK and its Gradle wrapper files.")
    missing = list(state.get("missing") or [])
    if not missing:
        return "This PC has the Android SDK, a Java 17 JDK and the Gradle wrapper files, so it is ready."
    return "This PC is missing: " + "; ".join(missing) + "."


def _run_android(name: str, state) -> "Result":
    ready = bool(state and state.get("ready"))
    where = ("Writing the fixed template needs no card. Building raises ONE card "
             "(" + ANDROID_BUILD_ACTION + ") that names the exact Gradle command, folder and "
             "toolchain. Installing raises ONE more card (" + ANDROID_INSTALL_ACTION + ") that "
             "names the exact adb command, APK and size. Never a Play Store upload.")
    if name == "android_capability":
        return Result("Yes - I can build a small Android app for you. In a project task, ask "
                      "\"build the Android app\" or \"build my app and put it on my phone\". I write "
                      "a fixed minimal Android project around your own index.html, app.js and "
                      "app.css (I do not hand-write Kotlin or the manifest), then Gradle builds it "
                      "and adb installs it over the cable. " + where + " " +
                      _android_missing_words(state), "android_capability")
    if name == "android_howto":
        return Result("Say it in a project task, for example: \"build the Android app\" to build "
                      "it, or \"build my app and put it on my phone\" to build and install. I write "
                      "the template project first (no card), then the build card appears with the "
                      "exact Gradle command, then the install card appears with the exact adb "
                      "command and the APK. " + _android_missing_words(state), "android_howto")
    if name == "android_needs":
        return Result("The Android builder needs the Android SDK on this PC, a Java 17 JDK, its "
                      "Gradle wrapper files beside jarvis_hud.py, and - only for the install - adb "
                      "and a USB cable with debugging on the phone. A first build also downloads "
                      "the Gradle distribution and the Android Gradle plugin. " +
                      _android_missing_words(state), "android_needs")
    if name == "android_build_install":
        return Result("Build and install are two separate steps with two separate cards: " +
                      ANDROID_BUILD_ACTION + " runs exactly `gradlew.bat assembleDebug` in the "
                      "task's copy, and " + ANDROID_INSTALL_ACTION + " runs exactly `adb install -r` "
                      "on the APK that build made. There is no adb shell, no uninstall, no release "
                      "signing and no Play Store. " + _android_missing_words(state),
                      "android_build_install")
    return Result("Yes - ask in a project task: \"build the Android app\". " + where,
                  "android_capability")


_ANDROID_BUILD_RX = re.compile(
    r"\b(?:can|could|are|will)\s+you\s+(?:be\s+able\s+to\s+)?(?:build|compile|make|create)"
    r"\s+(?:an?\s+)?android\s+apps?\b|"
    r"\bare\s+you\s+able\s+to\s+build\s+android\s+apps?\b|"
    r"\bcan\s+you\s+build\s+(?:me\s+)?(?:an?\s+)?app\s+(?:for\s+)?(?:my\s+)?phone\b")
_ANDROID_HOW_RX = re.compile(
    r"\bhow\s+(?:do|can|should)\s+i\s+(?:ask|tell)\s+you\s+to\s+build\s+(?:one|it|an?\s+app)\b|"
    r"\bhow\s+(?:do|can)\s+i\s+get\s+(?:you\s+to\s+)?build\s+(?:one|it|an?\s+android\s+app)\b")
_ANDROID_NEEDS_RX = re.compile(
    r"\bwhat\s+(?:does|do)\s+(?:the\s+)?android\s+builder\s+need\b|"
    r"\bwhat\s+(?:does|do)\s+(?:it|building\s+android\s+apps?)\s+need\b|"
    r"\bwhat\s+do\s+you\s+need\s+to\s+build\s+(?:an?\s+)?android\s+app\b")
_ANDROID_INSTALL_RX = re.compile(
    r"\bcan\s+you\s+(?:compile|build)\s+and\s+(?:install|put)\s+it\b|"
    r"\bcan\s+you\s+install\s+(?:it|the\s+app|an?\s+apk)\s+(?:on|to)\s+my\s+phone\b|"
    r"\bcan\s+you\s+put\s+(?:it|the\s+app)\s+on\s+my\s+phone\b")


def _android_question(raw) -> Optional[Intent]:
    text = " ".join(str(raw or "").strip().lower().rstrip("?.!").split())
    text = re.sub(r"^(?:hey\s+|ok\s+|okay\s+)?jarvis[,: ]+", "", text)
    if not text or len(text) > 400:
        return None
    if _ANDROID_HOW_RX.search(text):
        return Intent("android_howto")
    if _ANDROID_NEEDS_RX.search(text):
        return Intent("android_needs")
    if _ANDROID_INSTALL_RX.search(text):
        return Intent("android_build_install")
    if _ANDROID_BUILD_RX.search(text):
        return Intent("android_capability")
    return None


def _feature_capability_question(raw) -> Optional[Intent]:
    """A capability question read off the RAW sentence (2026-10-31).

    `normalize_spoken_command()` drops a leading "can you ", which turns "can
    you add something to my calendar?" into the imperative "add something to my
    calendar" and hands it to the action paths (it raised the unsolicited
    Connect-an-account card that way). The raw sentence still says it is a
    question about ability, so the fixed answer claims it first. Only the
    narrow shapes in `_feature_capabilities` match, so an ordinary request
    keeps its own path.
    """
    text = " ".join(str(raw or "").strip().lower().rstrip("?.!").split())
    text = re.sub(r"^(?:hey\s+|ok\s+|okay\s+)?jarvis[,: ]+", "", text)
    if not text:
        return None
    m = _FEATURE_OVERVIEW_ABOUT.fullmatch(text)
    if m:
        got = _feature_overview_about_intent(text, m.group(1))
        if got is not None:
            return got
    return _feature_capabilities(text)


# ---- discussion/explanation resolution (2026-10-31, pass-11 audit) ---------
def _feature_discussion_row(raw, target: str):
    """The row a discussion shape names, with the SAME gate as explain."""
    row = _feature_lookup_exact(target)
    if row is None and _feature_context_ok(raw):
        row = _feature_lookup(_feature_without_context(target))
    return row


def _feature_discussion_intent(raw, target: str, name: str):
    """A row-bound discussion intent, or None (never a guess)."""
    row = _feature_discussion_row(raw, target)
    if row is not None:
        return Intent(name, {"id": row["id"]})
    if _feature_context_ok(raw) and _feature_explicit(_feature_target(target)):
        return Intent("feature_unknown",
                      {"words": _feature_target(_feature_without_context(target))})
    return None


def _feature_row_loose(target: str):
    """The one row a discussion shape's words loosely name, or None."""
    if not str(target or "").strip():
        return None
    try:
        import jarvis_feature_guide as FG
        got = FG.find(target, loose=True)
    except Exception:                       # noqa: BLE001 - guide absent/broken
        return None
    return got["row"] if got.get("kind") == "feature" else None


def _feature_combined_row(first: str, second: str):
    """One row whose own name contains BOTH words ("reminders"+"alarms")."""
    try:
        import jarvis_feature_guide as FG
        got = FG.find(f"{first} {second}", loose=True)
    except Exception:                       # noqa: BLE001 - guide absent/broken
        return None
    return got["row"] if got.get("kind") == "feature" else None


def _feature_difference_intent(raw, first: str, second: str):
    """The two-row comparison, or None when neither part names a row."""
    row_a = _feature_discussion_row(raw, first) or _feature_row_loose(first)
    row_b = _feature_discussion_row(raw, second) or _feature_row_loose(second)
    combined = _feature_combined_row(first, second)
    if combined is not None:
        # "reminders and alarms" are BOTH in the scheduler row, not two
        # features: answering that honestly beats inventing a difference.
        row_a = row_b = combined
    if row_a is None and row_b is None:
        # Ordinary conversation ("difference between a car and a bike") falls
        # through; an explicit "Jarvis"/"feature" question gets the honest
        # answer instead of a model's invention.
        if _feature_context_ok(raw):
            return Intent("feature_unknown",
                          {"words": f"{first} and {second}".strip()})
        return None
    return Intent("feature_difference",
                  {"first": row_a["id"] if row_a is not None else first,
                   "second": row_b["id"] if row_b is not None else second})


def _feature_detail_row(raw, target: str):
    """The row a detail shape names, with the SAME gate as explain."""
    return _feature_discussion_row(raw, target)


def _feature_detail_intent(raw, target: str, mode: str):
    row = _feature_detail_row(raw, target)
    if row is not None:
        return Intent("feature_detail", {"id": row["id"], "mode": mode})
    if _feature_context_ok(raw) and _feature_explicit(_feature_target(target)):
        return Intent("feature_unknown",
                      {"words": _feature_target(_feature_without_context(target))})
    return None


def _feature_can_do_intent(raw, target: str, capability: str):
    row = _feature_detail_row(raw, target)
    if row is not None:
        return Intent("feature_can_do",
                      {"id": row["id"], "capability": str(capability or "").strip()})
    if _feature_context_ok(raw):
        return Intent("feature_unknown",
                      {"words": f"{target} {capability}".strip()})
    return None


def _feature_overview_about_intent(raw, area: str):
    """A group overview, only when the words name a real catalogue group."""
    FG = _guide()
    if FG is None or not str(area or "").strip():
        return None
    try:
        got = FG.overview(area)
    except Exception:                       # noqa: BLE001 - guide absent/broken
        return None
    if got.get("kind") == "group":
        return Intent("feature_overview", {"words": area})
    return None

# ---------------------------------------------------------------------------
#   Honest answers for abilities that are OFF, built only in the apps, or not
#   built at all - and the local calendar's own read (2026-10-31, pass 11)
# ---------------------------------------------------------------------------
#
# THE MEASURED BUGS (the owner's chat audit of the Obsidian features, live HUD
# on 0.2.378/0.2.379, recorded in
# `.dsh-scratch/FIELD-TEST-2026-10-31/pass11/obsidian/NOTES-OBSIDIAN.md`):
#   * "make a note: ..." answered "I shall record ..." and NOTHING was
#     written: the note-writing tools are not in the owner's `[tools].enabled`
#     list, and no fixed sentence said so, so the model promised a write it
#     could not make.
#   * "organize my notes" answered with a promise; the vault organizer exists,
#     is OFF by default, and has no chat door yet.
#   * "create a new note called Shopping", "rename my note ...", and "customize
#     my Obsidian theme" invented features that are not built (creating,
#     renaming, deleting, themes/CSS/templates are all absent by design).
#   * "what does my Welcome note say?" answered "I have no access to your
#     files" - wrong: the Notes plate reads every note in the vault.
#   * "what's on my calendar today?" answered with the Google connect steps
#     alone, ignoring the LOCAL Jarvis Calendar that exists, works and holds
#     the owner's own events.
#
# FIXED SENTENCES ONLY: no model, no new tool, no new route, no new card. Every
# state is READ at answer time from the module that owns it -
# `jarvis_agent.enabled_tools_for_turn()` for `[tools].enabled`,
# `jarvis_asks_first` for the real switch words and their Windows Hello rule,
# `jarvis_feature_guide`'s own rows for where/how/how-many-cards, and
# `jarvis_local_calendar` for the calendar - so no sentence can drift from the
# code. A private chat keeps its own rule (its fast path stays off there).
#
# The note/organizer ACTION lanes are separate work; nothing here writes a note,
# organizes a vault, or changes a switch. These sentences only say what is true.

#: The tools `jarvis_agent` offers the model for writing / reading notes. The
#: owner's list is read at ANSWER time, never remembered.
_NOTE_WRITE_TOOLS = ("append_obsidian_daily", "append_logseq_journal",
                     "create_joplin_note", "create_logseq_page")
_NOTE_READ_TOOLS = ("notes_search", "read_files_readonly")


def _enabled_tools_turn() -> set:
    """`[tools].enabled` as the live turn reads it - the REAL switch state."""
    try:
        import jarvis_agent as A
        return set(A.enabled_tools_for_turn())
    except Exception:
        return set()


def _asks_first_module():
    try:
        import jarvis_asks_first as AF
        return AF
    except Exception:
        return None


def _read_switch(row_id: str):
    """(row, [{"key","label","state"}]) from the feature list, or (None, [])."""
    FG = _guide()
    if FG is None:
        return None, []
    try:
        row = FG.row_by_id(row_id)
        if row is None:
            return None, []
        return row, FG.feature_switches(row)
    except Exception:
        return None, []


def _switch_is_off(row_id: str) -> Optional[bool]:
    """True/False from the real reader, or None when it cannot be read."""
    _, switches = _read_switch(row_id)
    if not switches:
        return None
    states = []
    for switch in switches:
        try:
            states.append(_guide().read_state(switch.get("key")))
        except Exception:
            states.append(None)
    if states and all(state is False for state in states):
        return True
    if any(state is True for state in states):
        return False
    return None


def _tool_off_words(subject: str, action: str) -> str:
    """The real switch words for a tool-backed ability that is not offered."""
    AF = _asks_first_module()
    if AF is None:
        return (f"{subject} is switched off on this PC because the tool behind "
                f"it is not offered to me.")
    real = AF.real_tool(action) if hasattr(AF, "real_tool") else action
    if real in tuple(getattr(AF, "SWITCHABLE_TOOL_NAMES", ()) or ()):
        pc_only = str(getattr(AF, "TOOLS_PC_ONLY", "") or "").strip()
        if pc_only:
            return f"{subject} is switched off on this PC. {pc_only}"
    if real in tuple(getattr(AF, "TOOLS_TOML_ONLY", ()) or ()):
        why = str(getattr(AF, "TOOLS_TOML_ONLY_NOTE", "") or "").strip()
        if why:
            return f"{subject} is switched off on this PC. {why}"
    not_listed = str(getattr(AF, "TOOLS_NOT_ON_LIST", "") or "").strip()
    head = (f"{subject} is switched off on this PC because the tool behind it "
            f"is not offered to me.")
    return f"{head} {not_listed}".strip()


def _notes_door_words(prefix: str) -> str:
    """The true door to the notes, in the feature list's own words."""
    row, _ = _read_switch("notes-editor")
    where = str((row or {}).get("where") or "").strip()
    asks = str((row or {}).get("asks") or "").strip()
    limit = str((row or {}).get("limit") or "").strip()
    out = prefix
    if where:
        out += f" Where: {where}"
    if asks:
        out += f" {asks}"
    if limit and "create" in limit.lower():
        out += " Creating, renaming and deleting a note is not built - that is done in Obsidian itself."
    return out.strip()


def _notes_tool_clause() -> str:
    """One sentence about whether a note READ/SEARCH can run in chat today."""
    tools = _enabled_tools_turn()
    if any(name in tools for name in _NOTE_READ_TOOLS):
        return ("The notes tool is switched on in Settings, What asks first, so a "
                "search can also run in chat.")
    AF = _asks_first_module()
    where = "Settings, What asks first"
    group = ""
    try:
        groups = getattr(AF, "GROUPS", ()) if AF is not None else ()
        if groups:
            group = str(groups[0][0] or "")
    except Exception:
        group = ""
    if group:
        where += ", " + group
    return f"Searching note text from chat is switched off here ({where})."


# ---- the local calendar's own read (2026-10-31, pass 11) -------------------
#
# THE MEASURED BUG: "what's on my calendar today?" was answered with the Google
# connect steps alone. The LOCAL calendar exists (jarvis_local_calendar.py), is
# ON by default, holds the owner's own events, and its GET /api/calendar answer
# is what the desktop card and the phone draw. A read must never be answered
# with setup instructions while a real store is readable. So this path calls
# the module the card calls - list_events()/settings() - and reports what is
# really there. It reads only: no card, no write, no network.
#
# TITLES AND THE HIDING RULES: the app's own hidden-lists / App-lock state is
# read from jarvis_private_view (the backend's one read-only hook). While it is
# hiding, this answer counts events and never prints a title, using the
# module's own withheld sentence - the same rule the calendar card follows.

#: "what's on tomorrow" is a calendar READ; "what's on today" is NOT claimed
#: here on purpose - `jarvis_intake.schedule_command()` treats every fast-path
#: match as a command, so a broad "what's on today" would stop the intake
#: learner from reading that ordinary turn (caught 2026-10-31 in the
#: integration tree by `test_memory_intake.py`, which expects the turn kept).
_CAL_TODAY = re.compile(r"what(?:'s| is)? on (?P<w>tomorrow)")
_CAL_READ_PATTERNS = (
    (re.compile(r"what(?:'s| is)? on (?:my|the) calendar"
                r"(?: (?P<w>today|tomorrow|this week|next week))?"), None),
    (re.compile(r"what do i have (?P<w>today|tomorrow|this week)"
                r"(?: on (?:my|the) calendar)?"), None),
    (re.compile(r"what(?:'s| is)? my next (?P<what>event|appointment|calendar event)"),
     "next"),
    (re.compile(r"when(?:'s| is)? my next (?P<what>event|appointment)"), "next"),
    (re.compile(r"am i free (?:at|on) (?P<at>.+)"), "free"),
    (re.compile(r"do i have anything(?: on)?(?: my calendar)? "
                r"(?P<w>today|tomorrow|this week)"), None),
    (_CAL_TODAY, None),
)
_CAL_DAYS = {"today": 1, "tomorrow": 2, "this week": 7, "next week": 7,
             "week": 7, "next": 30, "free": 1}


def _local_calendar_module():
    try:
        import jarvis_local_calendar as LC
        return LC
    except Exception:
        return None


def _calendar_hidden():
    """(hidden, withheld words) from the backend's one hiding hook."""
    try:
        import jarvis_private_view as PV
        state = PV.effective()
        hidden = bool(state.get("app_locked") or state.get("hide_memory_lists"))
        words = PV.withheld_words(app_locked=state.get("app_locked"),
                                  hide_memory_lists=state.get("hide_memory_lists"))
        return hidden, words
    except Exception:
        return False, ""


def _calendar_google_note() -> str:
    """The honest Google/state clause, only when it can really be read."""
    try:
        import jarvis_google_calendar as G
        state = G.status()
    except Exception:
        return ""
    if state.get("connected"):
        return ""
    return "Google Calendar is not connected on this PC."


def _calendar_when_words(ev: dict, LC) -> str:
    """"Saturday 31 October at 09:00", from the module's own name lists."""
    try:
        import datetime
        day = datetime.date.fromisoformat(str(ev.get("date") or ""))
        weekdays = getattr(LC, "WEEKDAY_NAMES", ())
        months = getattr(LC, "MONTH_NAMES", ())
        named = f"{weekdays[day.weekday()]} {day.day} {months[day.month - 1]}"
        if ev.get("all_day") or not ev.get("time"):
            return f"all day on {named}"
        return f"{named} at {ev['time']}"
    except Exception:
        return str(ev.get("date") or "")


def _calendar_event_words(ev: dict, LC) -> str:
    return f"{ev.get('title') or 'An event'}, {_calendar_when_words(ev, LC)}."


def _calendar_counted(words_when: str, count: int, withheld: str) -> str:
    noun = "event" if count == 1 else "events"
    out = f"You have {count} {noun} {words_when}."
    return f"{out} {withheld}".strip()


def _at_words(display: str) -> str:
    """"3" / "3pm" / "15:00" -> "3 this afternoon", or "" when unreadable."""
    import re as _re
    m = _re.fullmatch(r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)?",
                      str(display or "").strip().lower())
    if not m:
        return ""
    hour, minute = int(m.group("h")), int(m.group("m") or 0)
    if hour > 23 or minute > 59:
        return ""
    ap = m.group("ap")
    if ap == "pm" and hour < 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    elif not ap and 1 <= hour <= 6:
        hour += 12                     # "am I free at 3" is the afternoon
    if hour < 12:
        part = "in the morning"
    elif hour < 18:
        part = "this afternoon"
    else:
        part = "this evening"
    shown = hour % 12 or 12
    if minute:
        return f"{shown}:{minute:02d} {part}"
    return f"{shown} {part}"


def _local_calendar_prompt(s: str) -> Optional[Intent]:
    """The local-calendar READ sentences this PC can answer, or None."""
    for rx, window in _CAL_READ_PATTERNS:
        m = rx.fullmatch(s)
        if not m:
            continue
        named = (m.groupdict().get("w") or "").strip()
        at = (m.groupdict().get("at") or "").strip()
        if at:
            return Intent("local_calendar_read", {"window": "free", "at": at})
        if window:
            return Intent("local_calendar_read", {"window": window})
        if named:
            return Intent("local_calendar_read", {"window": named})
        return Intent("local_calendar_read", {"window": "week"})
    return None


def _run_local_calendar_read(f: dict, now: float) -> Optional[Result]:
    """A calendar READ, from the store the calendar card itself reads."""
    LC = _local_calendar_module()
    if LC is None:
        return None                    # no module: keep the old road
    try:
        settings = LC.settings()
    except Exception:
        return None
    if not settings.get("on"):
        why = str(settings.get("why") or "").strip()
        head = ("The Jarvis calendar is off on this PC, so I cannot read it. "
                "Turning it back on is instant - Settings, Jarvis Calendar - "
                "and needs no approval card.")
        return Result(f"{head} {why}".strip(), "local_calendar_read")
    window = str(f.get("window") or "week")
    days = _CAL_DAYS.get(window, 7)
    try:
        data = LC.list_events(days)
    except Exception:
        return Result("The calendar could not be read on this PC, so nothing "
                      "was shown. Nothing was changed.", "local_calendar_read")
    if not data.get("available", True):
        return Result(str(data.get("why") or "The calendar could not be read on "
                      "this PC, so nothing was shown."), "local_calendar_read")
    import datetime
    start = datetime.date.fromisoformat(str(data["window"]["start"]))
    events = list(data.get("events") or [])
    hidden, withheld = _calendar_hidden()
    print_start = start.isoformat()

    def shown(ev):
        return ("An event" if hidden else str(ev.get("title") or "An event"))

    def one(ev):
        return f"{shown(ev)}, {_calendar_when_words(ev, LC)}."

    def list_words(evs):
        return " ".join(one(ev) for ev in evs[:8])

    empty = ""
    if window == "today":
        same = [ev for ev in events if ev.get("date") == print_start]
        if hidden:
            words = (_calendar_counted("today", len(same), withheld)
                     if same else "Nothing on your calendar today.")
        elif not same:
            words = "Nothing on your calendar today."
        else:
            words = f"On your calendar today: {list_words(same)}"
        empty = "" if same else "Nothing on your calendar today."
    elif window == "tomorrow":
        tomorrow = (start + datetime.timedelta(days=1)).isoformat()
        same = [ev for ev in events if ev.get("date") == tomorrow]
        if hidden:
            words = (_calendar_counted("tomorrow", len(same), withheld)
                     if same else "Nothing on your calendar tomorrow.")
        elif not same:
            words = "Nothing on your calendar tomorrow."
        else:
            words = f"On your calendar tomorrow: {list_words(same)}"
        empty = "" if same else "Nothing on your calendar tomorrow."
    elif window == "free":
        at_text = str(f.get("at") or "").strip().lower()
        display = _at_words(at_text)
        hh = mm = None
        hit = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", at_text)
        if hit:
            hh, mm = int(hit.group(1)), int(hit.group(2) or 0)
            ap = hit.group(3)
            if ap == "pm" and hh < 12:
                hh += 12
            elif ap == "am" and hh == 12:
                hh = 0
            elif not ap and 1 <= hh <= 6:
                hh += 12
        wanted = (f"{hh:02d}:{mm:02d}" if hh is not None and hh <= 23
                  and mm is not None and mm <= 59 else "")
        same = [ev for ev in events if ev.get("date") == print_start
                and (ev.get("time") or "") == wanted] if wanted else []
        if not display or not wanted:
            words = ("Tell me a time, like \"am I free at 3\", and I will check "
                     "your calendar.")
        elif same and hidden:
            noun = "event" if len(same) == 1 else "events"
            words = (f"You have {len(same)} {noun} at {display}. {withheld}".strip())
        elif same:
            words = f"You have {one(same[0])[:-1]} at {display}."
        else:
            words = f"You are free at {display}."
    elif window == "next":
        upcoming = []
        for ev in events:
            date = str(ev.get("date") or "")
            if date > print_start:
                upcoming.append(ev)
            elif date == print_start:
                when = ev.get("time") or ""
                if ev.get("all_day") or not when:
                    upcoming.append(ev)
                else:
                    try:
                        hour, minute = (int(x) for x in when.split(":"))
                    except Exception:
                        continue
                    now_dt = datetime.datetime.fromtimestamp(now)
                    if (hour, minute) >= (now_dt.hour, now_dt.minute):
                        upcoming.append(ev)
        if not upcoming:
            words = "You have nothing on your calendar in the next 30 days."
        elif hidden:
            words = (f"Your next event is on "
                     f"{_calendar_when_words(upcoming[0], LC)}; its title is "
                     f"hidden. {withheld}".strip())
        else:
            words = f"Your next event is {one(upcoming[0])}"
    else:
        if hidden:
            words = (_calendar_counted("in the next 7 days", len(events), withheld)
                     if events else "Nothing on your calendar this week.")
        elif not events:
            words = "Nothing on your calendar this week."
        else:
            words = f"On your calendar this week: {list_words(events)}"
        empty = "" if events else "Nothing on your calendar this week."
    if empty:
        note = _calendar_google_note()
        if note:
            words = f"{words} {note}"
    return Result(words, "local_calendar_read")


# ---- the honest action sentences ------------------------------------------
# NOTE / ORGANIZER / OBSIDIAN CUSTOMISATION ARE THE NOTE LANE'S (2026-10-31
# integration). The note lane's actionable matchers run first and its real
# capture/organizer paths own those sentences; the duplicate honesty matchers
# that used to answer "the note tools are off", "the organizer has no chat
# door", "creating a note is not built" and the Obsidian theme answer were
# removed so there is ONE door per job. The honesty answers below own only the
# off / app-only / unbuilt abilities the note lane does not (email, home,
# phone control, jobs/spending doors, pictures, screen, settings-backed rows).

#: Generic customisation the note lane does NOT own: it answers Obsidian
#: theme/CSS/template asks itself (earlier, with its own sentence), so this
#: regex is only a fallback for the generic "create a template for my notes"
#: style request - one honest answer, not a model promise.
_CUSTOMISE = re.compile(
    r"(?:change|customi[sz]e|set|use|install|add|make|create)\s+"
    r"(?:my|the|a|an)?\s*(?:obsidian|vault|note|notes)?\s*"
    r"(?:theme|themes|css|stylesheet|template|templates|plugin|plugins|"
    r"community plugins|appearance)\b.*"
    r"|(?:obsidian|vault)\s+(?:theme|themes|css|template|templates|plugin|"
    r"plugins|appearance)\b.*"
    r"|customi[sz]e\s+(?:my|the)?\s*(?:obsidian|vault)\b.*")

_EMAIL_READ = re.compile(
    r"(?:read|check|open|look at|scan)\s+(?:my\s+)?(?:email|e-mail|mail|inbox)\b.*"
    r"|(?:any|new)\s+(?:email|e-mail|mail)\b.*"
    r"|what(?:'s| is)?\s+in\s+my\s+(?:email|inbox|mail)\b.*")
_HOME_READ = re.compile(
    r"is\s+the\s+(?:garage\s+|front\s+|back\s+|kitchen\s+)?door\s+"
    r"(?:open|locked|closed|unlocked)\b.*"
    r"|is\s+(?:the\s+)?(?:light|lights|lamp|heat|heating|thermostat|air)"
    r"\s+(?:on|off)\b.*"
    r"|what(?:'s| is)\s+the\s+(?:temperature|thermostat)\s+(?:inside|in\s+the\s+house|"
    r"at\s+home)\b.*")
_PHONE_CONTROL = re.compile(
    r"(?:tap|swipe|control|unlock|use)\s+(?:on\s+)?my\s+phone\b.*"
    r"|(?:send|write|type)\s+(?:a\s+|an\s+)?(?:text|message|sms)\s+(?:on|from|with)\s+"
    r"my\s+phone\b.*")
_JOBS_DOOR = re.compile(
    r"(?:start|create|make|begin|run|queue)\s+(?:me\s+)?(?:a\s+|an\s+)?"
    r"(?:background\s+|long\s+)?job\b.*"
    r"|(?:start|create)\s+(?:a\s+)?(?:background\s+)?(?:job|long job)\b.*")
_SPENDING = re.compile(
    r"how\s+much\s+(?:did|have|do)\s+i\s+spend\b.*"
    r"|(?:my\s+)?spending\s+(?:summary|summaries|report|total)\b.*"
    r"|what\s+did\s+i\s+spend\b.*")
_SCREEN_LOOK = re.compile(
    r"look\s+at\s+(?:my|the)\s+(?:screen|window|desktop)\b.*")
_PICTURES = re.compile(
    r"(?:make|draw|create|generate|paint)\s+(?:me\s+)?(?:a\s+|an\s+)?"
    r"(?:picture|image|drawing)\b.*")
_NOTE_NAMES = "notes, the Notes plate, or Obsidian itself"


def _honest_chat_prompt(s: str) -> Optional[Intent]:
    """One fixed, honest intent for off / app-only / unbuilt abilities.

    The note write, the note organizer, note read/search/edit, create/rename/
    delete and Obsidian customisation are NOT here: the note lane's actionable
    matchers run first and own them (2026-10-31 integration, one door per job).
    """
    # -- never built: GENERIC note/theme/template customisation --------------
    # (Obsidian-specific asks never reach this: the note lane's
    # obsidian_style_refused runs earlier and owns them.)
    if _CUSTOMISE.fullmatch(s):
        return Intent("honest_chat", {"shape": "never_built"})
    # -- off: email / home / phone-control tools ----------------------------
    tools = _enabled_tools_turn()
    if _EMAIL_READ.fullmatch(s):
        if "email_check" in tools or "email_read" in tools:
            return None
        return Intent("honest_chat", {"shape": "capability_off",
                                      "subject": "Reading your email from chat",
                                      "action": "email_read"})
    if _HOME_READ.fullmatch(s):
        if "home_read" in tools:
            return None
        return Intent("honest_chat", {"shape": "capability_off",
                                      "subject": "Asking how the house is from chat",
                                      "action": "home_read"})
    if _PHONE_CONTROL.fullmatch(s):
        if "control_phone" in tools:
            return None
        return Intent("honest_chat", {"shape": "capability_off",
                                      "subject": "Tapping or controlling your phone from chat",
                                      "action": "control_phone"})
    # -- app-only doors: jobs and spending are read in the apps -------------
    if _JOBS_DOOR.fullmatch(s):
        return Intent("honest_chat", {"shape": "feature_door", "row": "jobs"})
    if _SPENDING.fullmatch(s):
        return Intent("honest_chat", {"shape": "feature_door", "row": "spending"})
    # -- settings-backed abilities: only when the real switch reads OFF -----
    # (The screen look is asked only when the OWNER phrased it as a question -
    # "can you look at my screen?" - because the plain "look at my screen"
    # belongs to PR #691's Live read, which this fast path must not intercept.)
    if _PICTURES.fullmatch(s) and _switch_is_off("pictures") is True:
        return Intent("honest_chat", {"shape": "setting_off", "row": "pictures"})
    # Quiet hours as a SETTINGS question: "how do I turn off quiet hours?",
    # "where is the quiet hours setting?". This sits in the LATE honesty
    # prompt (after the settings grammar) on purpose: the bare "turn on quiet
    # hours" is settings_bool's own phrase (the checker pins that resolved
    # flag); the HOW/WHERE question is the one the settings grammar leaked
    # with its internal key on the live field test (2026-10-31 integration).
    if _QUIET_HOURS.fullmatch(s):
        return Intent("honest_chat", {"shape": "quiet_hours"})
    return None


def _run_honest_chat(f: dict) -> Result:
    """The one fixed sentence for an off / app-only / unbuilt ability."""
    shape = str(f.get("shape") or "")
    if shape == "note_write":
        return Result(
            _tool_off_words("Writing a note from chat", "append_obsidian_daily")
            + " You can write the note in Obsidian itself; a note that exists "
              "opens and edits in the Brain's Notes plate, with one approval "
              "card per save.",
            "honest_chat")
    if shape == "note_door":
        mode = str(f.get("mode") or "read")
        if mode == "search":
            head = "I cannot search note text in chat here."
        else:
            head = "I cannot read note text in chat here."
        return Result(_notes_door_words(head) + " " + _notes_tool_clause(),
                      "honest_chat")
    if shape == "note_unbuilt":
        op = str(f.get("op") or "create")
        verb = {"create": "Creating", "rename": "Renaming",
                "delete": "Deleting"}.get(op, "Changing")
        tail = {"create": "Create it in Obsidian itself.",
                "rename": "Rename it in Obsidian itself.",
                "delete": "Delete it in Obsidian itself."}.get(op, "")
        return Result(_notes_door_words(f"{verb} a note is not built in Jarvis.")
                      + f" {tail}".strip(), "honest_chat")
    if shape == "organizer":
        try:
            import jarvis_vault_organizer as O
        except Exception:
            O = None
        if O is not None and O.enabled():
            words = (str(getattr(O, "SWITCH_ON_WORDS", "") or "").strip()
                     + " It shows you a read-only plan first and changes "
                       "nothing until you approve the plan.")
        else:
            off = (str(getattr(O, "_OFF_WHY", "") or "").strip() if O is not None
                   else "The vault organizer is off on this PC.")
            words = (f"{off} After that it shows you a read-only plan and "
                     f"changes nothing until you approve the plan.")
        return Result(words.strip(), "honest_chat")
    if shape == "never_built":
        FG = _guide()
        not_feature = str(getattr(FG, "CAPABILITY_NOT_A_FEATURE", "") or
                          "That is not one of my features on this PC.")
        tail = str(getattr(FG, "CAPABILITY_TAIL", "") or "").strip()
        nearest = (" What is built is browsing, searching and editing your "
                   "notes in the Brain's Notes plate - a save there raises one "
                   "card - and Obsidian itself owns themes, CSS and templates.")
        return Result(f"{not_feature}{nearest} {tail}".strip(), "honest_chat")
    if shape == "capability_off":
        subject = str(f.get("subject") or "That")
        action = str(f.get("action") or "")
        return Result(_tool_off_words(subject, action), "honest_chat")
    if shape == "feature_door":
        row_id = str(f.get("row") or "")
        row, _ = _read_switch(row_id)
        where = str((row or {}).get("where") or "").strip()
        what = str((row or {}).get("what") or "").strip()
        title = str((row or {}).get("title") or "").strip()
        if row_id == "jobs":
            words = (f"{title or 'Background jobs'} are not started from chat. "
                     + (f"Where: {where}" if where else "")
                     + " The jobs already running are listed there.")
        else:
            words = ("I cannot start that from chat here. "
                     + (f"{what} " if what else "")
                     + (f"Where: {where}" if where else ""))
        return Result(words.strip(), "honest_chat")
    if shape == "setting_off":
        row_id = str(f.get("row") or "")
        row, _ = _read_switch(row_id)
        FG = _guide()
        title = str((row or {}).get("title") or "That")
        if row is not None and FG is not None:
            try:
                out = FG.how_to(str(row.get("id") or ""), on=True)
                words = str(out.get("words") or "").strip()
                if words.startswith(title):
                    words = words[len(title):].lstrip(" .")
            except Exception:
                words = ""
            if words:
                return Result(f"{title} is switched off on this PC. {words}",
                              "honest_chat")
        return Result(f"{title} is switched off on this PC.", "honest_chat")
    extra = _run_honest_chat_extra(f)
    if extra is not None:
        return extra
    return Result("That is not something I can do from chat here.", "honest_chat")


# ---- the stateful read doors (2026-10-31, the chat audit's second half) ----
#
# THE MEASURED BUGS (`.dsh-scratch/FIELD-TEST-2026-10-31/pass11/chat-audit/
# AUDIT-CHAT.md`, rows 21, 22, 40, 42, 47, 49, 50, 52, 53 and the doors audit):
#   * "what is protected from Jarvis right now?" - no chat read of the list,
#     and the model said it could not check; "remove protection from a folder"
#     was refused outright, while the catalogue says it raises one card.
#   * "how do I turn off quiet hours?" - the feature guide answered with the
#     internal key "pc_quiet_hours" instead of the owner's own words.
#   * "what asks first?" - no answer; the model asked a clarifying question.
#   * "what timer is on my phone" / "set a timer on my phone" - the model said
#     it was not connected, while the phone is connected.
#   * "what jobs are running?" - the model pointed at Task Manager.
#   * "can you watch a PR for me?" / "tell me when a PR changes" - the model
#     did not know the watch door.
#   * "can you switch models?" / "switch models from my phone" - the model
#     said it could not, while the model-switch card and the phone switch exist.
#   * "can you read this picture?" - the model said it cannot read pictures,
#     while picture mode is a real switch (off by default).
#   * "can you turn on the lights?" - a feature switch card was raised for the
#     "lights without a card" SETTING, though the real home-control tool is off.
#
# Each answer below reads the REAL store/state at answer time and says it in
# the owning module's own words: `jarvis_protection.handle_get()` and its
# CHANGE_CARD, `jarvis_jobs.jobs()`, `jarvis_devices.paired_status()`,
# `jarvis_limits`'s own row titles, `jarvis_asks_first`'s switch words and
# `jarvis_feature_guide`'s rows. Reads only: no card, no write, no model.

_PROTECT_READ = re.compile(
    r"(?:what(?:'s| is)|show me|list|tell me|see)\s+(?:what(?:'s| is)\s+)?"
    r"(?:currently\s+)?protected\b.*"
    r"|what(?:'s| is)\s+on\s+my\s+protected\s+(?:list|items)\b.*"
    r"|is\s+anything\s+protected\b.*")
_PROTECT_REMOVE = re.compile(
    r"(?:remove|take|clear|undo)\s+(?:the\s+)?protection\s+(?:from|on)\s+(?P<target>.+)"
    r"|unprotect\s+(?P<target2>.+)"
    r"|stop\s+jarvis\s+from\s+(?:touching|reading|opening|using)\s+(?P<target3>.+)"
    r"|(?:remove|take)\s+(?P<target4>.+?)\s+(?:from|off)\s+(?:the\s+)?protected\b.*")
_PROTECT_ADD = re.compile(
    r"(?:protect|exclude)\s+(?:my|the|this|these|those)\s+(?P<target>.+)"
    r"|add\s+(?P<target2>.+?)\s+to\s+(?:the\s+)?protected\b.*")
_LIGHTS = re.compile(
    r"turn\s+(?:on|off)\s+(?:the\s+|my\s+|a\s+)?(?:living\s+room|kitchen|bedroom|"
    r"office|hall|front\s+room|lounge|dining\s+room|bathroom)?\s*"
    r"(?:light|lights|lamp|lamps|plug|plugs|fan|fans)\b.*")
_PHONE_TIMER = re.compile(
    r"(?:what|which)\s+(?:timer|timers|alarm|alarms)\s+(?:is|are)\s+(?:on|set\s+on)\s+"
    r"my\s+phone\b.*"
    r"|(?:what|which)\s+(?:timer|timers)\s+do\s+i\s+have\s+on\s+my\s+phone\b.*"
    r"|(?:what|which)\s+(?:timer|timers)\s+(?:is|are)\s+(?:on|set\s+on)\s+my\s+phone\b.*"
    r"|timers?\s+on\s+my\s+phone\b.*"
    r"|(?:can\s+you|could\s+you|please)?\s*set\s+(?:a\s+)?(?:timer|alarm)\s+on\s+"
    r"my\s+phone\b.*")
#: "is my phone connected / paired / linked / online / set up?", "can you see my
#: phone?", "what phone is paired?", "my phone isn't connecting" - the phone's
#: own STATE question (2026-10-31, post-deploy audit: the model answered "I am
#: not sure ... allow me to look at the Settings app or Device Manager for
#: Bluetooth and USB", which is not a place this state lives). It reads the
#: same paired-device store as the phone-timer answer and writes nothing. Only
#: WHOLE state sentences: pairing actions keep their own `pair_phone`/ring
#: paths, so "pair my phone", "connect my phone" and "ring my phone" never
#: reach this one.
_PHONE_STATE = re.compile(
    # "is my phone connected / paired / linked / online / set up / working?"
    r"(?:is|are|was|were|does|do|did|has|have)\s+(?:my|the|your)\s+"
    r"(?:phone|android(?:\s+phone)?|mobile(?:\s+phone)?|device)\b[^.]{0,14}?"
    r"(?:connected|linked|paired|online|set\s+up|working|reachable|"
    r"recognis\w*|recogniz\w*)"
    r"(?:\s+(?:to|with)\s*(?:you|jarvis|the\s+pc|this\s+pc)?)?.*"
    # "can you see / do you see / can you reach my phone?"
    r"|(?:can|could|do|does)\s+(?:you|jarvis)\s+(?:see|reach|find|detect|"
    r"recognise|recognize)\s+(?:my|the)\s+(?:phone|android|mobile)\b.*"
    # the normaliser strips the "can you", so "see my phone" is the same ask
    r"|(?:see|reach)\s+(?:my|the)\s+(?:phone|android|mobile)\b.*"
    # "what / which phone is paired / connected?"
    r"|(?:what|which)\s+(?:phone|android|mobile)\s+(?:is|are)\s+"
    r"(?:paired|connected|linked)\b.*"
    # "my phone is not connecting / won't connect / isn't paired"
    r"|my\s+phone\s+(?:is\s+not|isn't|isnt|isn\s+t|won't|wont|won\s+t|"
    r"does\s+not|doesn't|doesnt|doesn\s+t|can't|cant|can\s+t|cannot)\s+"
    r"(?:connect|connecting|connected|pair|pairing|paired|link|linked|reach|"
    r"reaching|work|working|see|show|online|set\s+up)\b.*"
    # "phone connection status"
    r"|(?:phone|android)\s+(?:connection\s+)?status\b.*")
_MODEL_SWITCH = re.compile(
    r"(?:can\s+you|could\s+you|how\s+do\s+i|how\s+can\s+i|how\s+to|where\s+do\s+i)?\s*"
    r"switch\s+(?:the\s+|my\s+)?models?\b.*"
    r"|switch\s+models?\s+from\s+(?:my\s+)?phone\b.*")
_WATCH_DOOR = re.compile(
    r"(?:can\s+you|could\s+you|please)?\s*watch\s+(?:a\s+|this\s+|my\s+|the\s+)?"
    r"(?:pr|pull\s+request|repo|repository|issue)\b.*"
    r"|how\s+do\s+i\s+get\s+you\s+to\s+(?:watch|tell\s+me\s+when)\s+(?:a\s+|the\s+)?"
    r"(?:pr|pull\s+request|repo|repository)\b.*")
_JOBS_READ = re.compile(
    r"what\s+(?:background\s+)?jobs?\s+(?:are\s+)?(?:running|going|active|queued)\b.*"
    r"|what\s+jobs?\s+do\s+i\s+have\b.*"
    r"|(?:are|is)\s+there\s+(?:any\s+)?(?:background\s+)?jobs?\s+running\b.*"
    r"|what(?:'s| is)\s+running\s+in\s+the\s+background\b.*")
_ASKS_FIRST = re.compile(
    r"(?:what(?:'s| is)?\s+)?what\s+asks\s+first\b.*"
    r"|(?:explain|tell\s+me\s+about|describe)\s+what\s+asks\s+first\b.*")
_QUIET_HOURS = re.compile(
    # Only the HOW/WHERE settings question is the honesty lane's. The bare
    # "turn on/off quiet hours" is settings_bool's own phrase (the owner's
    # switch, its tier and its card rule), and "tell me about quiet hours" /
    # "what are the limits of quiet hours" belong to the feature DISCUSSION
    # lane. This used to be one broad regex that stopped both (2026-10-31
    # integration precedence fix).
    r"(?:how\s+(?:do|can)\s+i|how\s+to)\s+(?:turn|switch|change|set)\s+"
    r"(?:off\s+|on\s+)?(?:the\s+)?quiet\s+hours\b.*"
    r"|where\s+(?:is|are)\s+(?:the\s+)?quiet\s+hours\b.*")
_WHAT_OFF = re.compile(
    r"what\s+(?:is|are|s)?\s+(?:switched\s+)?off\s+on\s+this\s+(?:pc|computer)\b.*"
    r"|which\s+(?:features|things|abilities)\s+are\s+(?:switched\s+)?off\b.*"
    r"|which\s+of\s+your\s+features\s+are\s+(?:switched\s+)?off\b.*")
_PICTURE_READ = re.compile(
    r"(?:can\s+you|could\s+you)?\s*read\s+(?:this|the|a)\s+"
    r"(?:picture|image|screenshot|photo)\b.*"
    r"|what(?:'s| is)\s+(?:in|on)\s+this\s+(?:picture|image|screenshot)\b.*")


def _protection_module():
    try:
        import jarvis_protection as P
        return P
    except Exception:
        return None


def _protection_mode_words(P, mode) -> str:
    words = getattr(P, "MODE_WORDS", {}) or {}
    return str(words.get(mode) or mode or "")


#: How recent a paired phone's own check-in must be before this PC calls it
#: "connected" rather than "paired, but not heard from". A phone writes
#: last_seen on its requests, so five minutes is longer than any normal gap and
#: short enough that a phone left in a drawer is not called connected. It is
#: only a wording line: the row itself is never changed by this read.
_PHONE_CONNECTED_S = 300


def _phone_when_words(age: int, seen: float) -> str:
    """How long ago the phone was last heard from, in the phone answer's words."""
    import datetime
    if age < 120:
        return "just now"
    if age < 3600:
        return f"{age // 60} minutes ago"
    if age < 86400:
        return f"{age // 3600} hours ago"
    return datetime.datetime.fromtimestamp(float(seen)).strftime("%d %B")


def _phone_state_words(devices_state: dict, topic: str = "timer") -> str:
    """What this PC really knows about the owner's phone, from /api/devices.

    Two shapes share one store read: `topic="timer"` ("what timer is on my
    phone") also says timers live on the phone; any other topic is the phone's
    STATE ("is my phone connected / paired?") and answers one of four honest
    facts - connected, paired but not heard from, no phone paired, or the store
    unreadable. Read-only: nothing is paired, connected, changed or promised,
    and no answer sends the owner to Settings, Bluetooth or Device Manager to
    check a state this PC already holds.
    """
    timer = str(topic or "timer") == "timer"
    devices = list((devices_state or {}).get("devices") or [])
    phones = []
    for dev in devices:
        name = str(dev.get("name") or "")
        kind = str(dev.get("kind") or "").lower()
        if kind == "phone" or "phone" in name.lower():
            phones.append(dev)
    if not (devices_state or {}).get("readable", True):
        why = str((devices_state or {}).get("why") or "").strip()
        head = ("I cannot read the paired devices on this PC right now, so I "
                "cannot say whether your phone is connected.")
        if why:
            if why[0].islower():
                why = why[0].upper() + why[1:]
            if not why.endswith((".", "!", "?")):
                why += "."
            return f"{head} {why}"
        return head
    if not phones:
        if not timer:
            return ("No phone is paired with Jarvis on this PC yet. On the PC: "
                    "Settings, Devices, then \"Pair a phone\"; on the phone: "
                    "Jarvis, Settings, Devices, then \"Pair with your PC\".")
        return ("No phone is paired with Jarvis on this PC yet. Timers set on the "
                "phone stay on the phone; pair it first and the phone's own Clock "
                "shows them.")

    def _seen(dev) -> float:
        value = dev.get("last_seen")
        return float(value) if isinstance(value, (int, float)) and value > 0 else 0.0

    primary = max(phones, key=_seen)
    name = str(primary.get("name") or "your phone")
    seen = _seen(primary)
    when = _phone_when_words(max(0, int(time.time() - seen)), seen) if seen else ""
    if timer:
        parts = []
        for dev in phones:
            label = str(dev.get("name") or "your phone")
            stamp = _seen(dev)
            if stamp:
                parts.append(f"{label}, last heard from "
                             f"{_phone_when_words(max(0, int(time.time() - stamp)), stamp)}")
            else:
                parts.append(f"{label}, not heard from since it was paired")
        return ("Your phone is connected to Jarvis right now (" + "; ".join(parts)
                + "). Timers set on the phone stay on the phone - I cannot read or "
                  "set them from this PC's chat; open the phone's Clock, or ask "
                  "Jarvis on the phone.")
    if not seen:
        return (f"Your phone is paired with Jarvis ({name}), but it has not been "
                f"heard from since it was paired. Open the Jarvis app on the "
                f"phone and check it can reach this PC.")
    age = max(0, int(time.time() - seen))
    if age <= _PHONE_CONNECTED_S:
        return (f"Your phone is connected to Jarvis right now ({name}, last "
                f"heard from {when}).")
    return (f"Your phone is paired with Jarvis ({name}), but I have not heard "
            f"from it since {when}. Open the Jarvis app on the phone and check "
            f"it can reach this PC.")


def _quiet_hours_words() -> str:
    """The owner's own words for the quiet-hours rows, from jarvis_limits."""
    rows = ()
    try:
        import jarvis_limits as L
        rows = tuple(getattr(L, "_NOTIFY_ROWS", ()) or ())
    except Exception:
        rows = ()
    titles = []
    for row in rows:
        try:
            key, _kind, title = row[0], row[1], row[2]
        except Exception:
            continue
        if "quiet" in str(key).lower():
            titles.append(str(title))
    if not titles:
        titles = ["Be quiet during quiet hours (on your PC)",
                  "Quiet hours start (on your PC)",
                  "Quiet hours end (on your PC)"]
    quoted = ", ".join(f'"{t}"' for t in titles)
    return ("Quiet hours are the times your PC stays quiet. They are in Settings, "
            f"Limits and frequency - the rows {quoted}. Say \"turn off quiet "
            "hours\" (or on) and Jarvis changes that switch.")

    # ---- the matcher, run BEFORE the feature/settings grammars ----------------


def _honest_early(_text: str, s: str) -> Optional[Intent]:
    """Off-state / state-read sentences that must beat the feature grammar."""
    # The protection list, and the one-card rule for changing it.
    if _PROTECT_READ.fullmatch(s):
        return Intent("honest_state", {"shape": "protection_read"})
    m = _PROTECT_REMOVE.fullmatch(s)
    if m:
        target = next((g for g in m.groups() if g), "")
        return Intent("honest_state", {"shape": "protection_change",
                                       "op": "remove",
                                       "target": target.strip()})
    m = _PROTECT_ADD.fullmatch(s)
    if m:
        target = next((g for g in m.groups() if g), "")
        return Intent("honest_state", {"shape": "protection_change",
                                       "op": "add",
                                       "target": target.strip()})
    # A real light/plug/fan command: the home-control tool, not the setting.
    # The feature guide's own displayed control phrase ("turn on lights without
    # asking") must keep reaching the SETTING, so it is left alone here.
    if _LIGHTS.fullmatch(s):
        if any(phrase in s for phrase in ("without asking", "without a card",
                                         "no card", "without cards")):
            return None
        if "home_control" not in _enabled_tools_turn():
            return Intent("honest_chat", {"shape": "lights_off"})
        return None
    # The phone's own STATE ("is my phone connected/paired?"): the same real
    # paired-device store the timer answer reads, and never a promise to go and
    # look at Settings, Bluetooth or Device Manager (2026-10-31, post-deploy
    # audit: the model invented exactly that search).
    if _PHONE_STATE.fullmatch(s):
        return Intent("honest_state", {"shape": "phone_state", "topic": "state"})
    # The phone's own timers: real paired-device state, never "not connected".
    if _PHONE_TIMER.fullmatch(s):
        return Intent("honest_state", {"shape": "phone_state", "topic": "timer"})
    # Model switching is real; point at its own place and card.
    if _MODEL_SWITCH.fullmatch(s):
        return Intent("honest_chat", {"shape": "model_door"})
    # A watch is set up by the owner's words; the feature list names the place.
    if _WATCH_DOOR.fullmatch(s):
        return Intent("honest_chat", {"shape": "watch_door"})
    # The job list is really readable.
    if _JOBS_READ.fullmatch(s):
        return Intent("honest_state", {"shape": "jobs_read"})
    # The Settings answers whose words the feature grammar leaked or lost.
    # Only the bare page question: "tell me about what asks first" and the
    # other explain shapes belong to the feature list, which has the row.
    if s == "what asks first":
        return Intent("honest_chat", {"shape": "asks_first"})
    if _WHAT_OFF.fullmatch(s):
        return Intent("honest_chat", {"shape": "general_off"})
    # Reading a picture is picture mode's question, not an invented refusal.
    if _PICTURE_READ.fullmatch(s) and _switch_is_off("look-at-this") is True:
        return Intent("honest_chat", {"shape": "setting_off", "row": "look-at-this"})
    # "Can you look at my screen?" is a QUESTION about the switch; the plain
    # "look at my screen" is PR #691's own Live read and is left to it.
    if (_SCREEN_LOOK.fullmatch(s) and _switch_is_off("look-at-this") is True
            and any(ask in str(_text or "").lower()
                    for ask in ("can you", "could you", "can i", "may i",
                                "please look", "would you"))):
        return Intent("honest_chat", {"shape": "setting_off", "row": "look-at-this"})
    return None


def _run_honest_state(f: dict) -> Result:
    """The stateful reads: the protection list, the job list, the phone state."""
    shape = str(f.get("shape") or "")
    if shape == "protection_read":
        P = _protection_module()
        if P is None:
            return Result("I cannot read the Protected from Jarvis list on this "
                          "PC right now.", "honest_state")
        try:
            code, body = P.handle_get()
        except Exception:
            code, body = 500, {}
        if not isinstance(body, dict) or not body.get("ok"):
            return Result("This PC could not read the Protected from Jarvis list, "
                          "so nothing is shown. Nothing was changed.",
                          "honest_state")
        items = list(body.get("items") or [])
        change = str(body.get("change_card") or "").strip()
        if not items:
            words = "Nothing is protected from Jarvis right now."
        else:
            parts = []
            for item in items[:8]:
                kind = str(item.get("kind") or "item")
                target = str(item.get("target") or "")
                mode = _protection_mode_words(P, item.get("mode"))
                parts.append(f"{kind} {target} ({mode})")
            extra = "" if len(items) <= 8 else f" and {len(items) - 8} more"
            noun = "thing" if len(items) == 1 else "things"
            verb = "is" if len(items) == 1 else "are"
            words = (f"{len(items)} {noun} {verb} protected from Jarvis: "
                     + "; ".join(parts) + extra + ".")
        return Result(f"{words} {change}".strip(), "honest_state")
    if shape == "protection_change":
        P = _protection_module()
        op = str(f.get("op") or "")
        verb = "Removing protection" if op == "remove" else "Adding protection"
        rule = (str(getattr(P, "CHANGE_CARD", "") or "") if P is not None else "")
        offered = ("protect_item" in _enabled_tools_turn()
                   or "unprotect_item" in _enabled_tools_turn())
        if offered:
            head = f"{verb} from chat raises one approval card."
        else:
            head = (f"{verb} from chat needs the protection tool, which is not "
                    f"offered to me on this PC, so I cannot start its card here "
                    f"in chat. Do it in Settings, Protected from Jarvis on the PC: "
                    f"adding there is immediate.")
        return Result(f"{head} {rule}".strip(), "honest_state")
    if shape == "jobs_read":
        try:
            import jarvis_jobs as J
            rows = J.jobs()
        except Exception:
            return Result("This PC could not read its background job list, so "
                          "nothing is shown. Nothing was changed.", "honest_state")
        running = [row for row in rows
                   if str(row.get("state") or "") in
                   ("queued", "running", "waiting_approval")]
        if not running:
            if not rows:
                words = "No background jobs right now."
            else:
                words = "No background jobs are running right now."
            return Result(words, "honest_state")
        state_words = {"queued": "waiting to start", "running": "running",
                       "waiting_approval": "waiting for your approval"}
        parts = []
        for row in running[:6]:
            label = str(row.get("label") or row.get("handler") or "a job")
            state = state_words.get(str(row.get("state")), str(row.get("state")))
            parts.append(f"{label} ({state})")
        noun = "job" if len(running) == 1 else "jobs"
        return Result(f"{len(running)} background {noun}: " + "; ".join(parts) + ".",
                      "honest_state")
    if shape == "phone_state":
        try:
            import jarvis_devices as D
            state = D.paired_status()
        except Exception:
            state = {}
        return Result(_phone_state_words(state, str(f.get("topic") or "timer")),
                      "honest_state")
    return Result("That is not something I can read from chat here.", "honest_state")


def _general_off_items() -> list:
    """What is really switched off for chat, from the real switches."""
    items = []
    tools = _enabled_tools_turn()
    if not any(name in tools for name in _NOTE_WRITE_TOOLS):
        items.append("writing a note from chat")
    if "email_check" not in tools and "email_read" not in tools:
        items.append("reading your email")
    if "home_read" not in tools:
        items.append("asking how the house is")
    if "home_control" not in tools:
        items.append("switching your lights")
    if not any(name in tools for name in _NOTE_READ_TOOLS):
        items.append("searching your notes")
    if _switch_is_off("look-at-this") is True:
        items.append("looking at your screen")
    if _switch_is_off("pictures") is True:
        items.append("making pictures")
    LC = _local_calendar_module()
    try:
        if LC is not None and not LC.settings().get("on"):
            items.append("the Jarvis calendar")
    except Exception:
        pass
    return items


def _run_honest_chat_extra(f: dict) -> Optional[Result]:
    """The non-store shapes added with the stateful read doors."""
    shape = str(f.get("shape") or "")
    if shape == "lights_off":
        return Result(_tool_off_words("Switching your lights from chat",
                                      "home_control"), "honest_chat")
    if shape == "model_door":
        row, _ = _read_switch("models")
        title = str((row or {}).get("title") or "Models")
        what = str((row or {}).get("what") or "").strip()
        where = str((row or {}).get("where") or "").strip()
        if row is None:
            return Result("Models are switched in the Brain's Model page on this "
                          "PC, and a switch raises one approval card.",
                          "honest_chat")
        return Result(f"{title}: {what} Where: {where} A switch between the "
                      f"models already on the PC raises one approval card; it is "
                      f"not something this chat box changes by asking.",
                      "honest_chat")
    if shape == "watch_door":
        row, _ = _read_switch("github-watchlist")
        where = str((row or {}).get("where") or "").strip()
        what = str((row or {}).get("what") or "").strip()
        head = (f"{what} " if what else "") + (f"Where: {where} " if where else "")
        tail = ("To be told when a page changes, say \"tell me when <the page> "
                "changes\" - setting a watch up raises one approval card.")
        return Result((head + tail).strip(), "honest_chat")
    if shape == "asks_first":
        AF = _asks_first_module()
        label = str(getattr(AF, "TOOLS_LABEL", "") or "Let the AI use this")
        titles = []
        try:
            items = (AF.tools_status() or {}).get("items") or []
            titles = [str(item.get("title") or "") for item in items
                      if item.get("title")]
        except Exception:
            titles = []
        count = len(titles)
        return Result(
            "What asks first is Settings, What asks first. There you decide what "
            "Jarvis may do without asking, and under \"" + label + "\" which "
            "abilities the AI is offered at all: " + str(count) + " one-tool "
            "switches, grouped. Turning one on is ONE approval card plus Windows "
            "Hello on this PC; turning it off is instant. Raw shell, computer and "
            "browser control, reading one web page, connecting an account and REA "
            "are not offered in-app by this slice - they stay a settings-file "
            "choice, and REA also needs its own [rea] enabled = true.", "honest_chat")
    if shape == "quiet_hours":
        return Result(_quiet_hours_words(), "honest_chat")
    if shape == "general_off":
        items = _general_off_items()
        if not items:
            return Result("Nothing that chat can read is switched off on this PC "
                          "right now.", "honest_chat")
        return Result(
            "On this PC these are switched off right now: " + "; ".join(items[:8])
            + ". The in-app switches are in Settings, What asks first under "
            "\"Let the AI use this\" - one approval card plus Windows Hello, one "
            "tool at a time. Raw shell, computer and browser control, reading one "
            "web page, connecting an account and REA are not offered in-app; they "
            "stay a settings-file choice, and REA also needs its own [rea] enabled "
            "= true.", "honest_chat")
    return None


def _feature_target(words) -> str:
    """The words after the pattern, with a trailing "feature"/"option" taken
    off - "the prompt coach feature" names the prompt coach.

    The trailing word is NOT taken off when the whole thing already names a
    row: "Animal options" is a feature's own title, and stripping "options"
    turned it into "animal", which matched nothing and fell to the model
    (measured 2026-10-26, the field test of the owner's requested phrasings).
    """
    text = " ".join(str(words or "").split())
    if text and _feature_lookup_exact(text) is not None:
        return text
    text = re.sub(r"\s*\b(?:feature|features|option|options|setting|settings)\b\s*$",
                  "", text, flags=re.I)
    return text.strip()


def _feature_text(words) -> str:
    """A row's id as something jarvis_feature_guide can look up by name."""
    return str(words or "").strip()


#: Words that make a sentence explicitly about JARVIS's own features rather
#: than a general question. The name "Jarvis" is normally taken off as the
#: address before the grammar sees the sentence (normalise()'s _LEAD), so the
#: RAW message is checked too. With one of these present, a multi-word
#: restatement may be looked up more loosely; without one, the subject must be
#: an EXACT feature/switch name (Gemini's review, 2026-10-20, section 11.8.3).
_FEATURE_CONTEXT = re.compile(r"\b(?:jarvis|here|my\s+settings)\b", re.I)


def _feature_says_jarvis(raw) -> bool:
    """Did the sentence put itself in Jarvis's own context ("Jarvis", "here",
    "my settings")? Checked on the RAW message because "Jarvis," is stripped
    as an address before the grammar runs."""
    return bool(_FEATURE_CONTEXT.search(str(raw or "")))


def _feature_explicit(s: str) -> bool:
    """Did the owner SAY "feature"? Only then may an unknown name be answered
    with "I do not have that one" instead of falling through to the model."""
    return bool(re.search(r"\b(?:feature|features|option|options)\b", s))


def _feature_without_context(words) -> str:
    """The subject with explicit context words taken out, so "my settings" is
    not read as part of a feature's name."""
    return " ".join(_FEATURE_CONTEXT.sub(" ", str(words or "")).split())


def _feature_lookup(target: str):
    """The one feature a restated phrase names, or None (never a guess)."""
    if not target:
        return None
    try:
        import jarvis_feature_guide as FG
    except Exception:
        return None
    try:
        return FG.find_feature(target, strong=True)
    except Exception:
        return None


def _feature_lookup_exact(target: str):
    """The one feature whose own name IS exactly `target`, or None.

    THE FIXED PHRASES' GATE. Without explicit Jarvis context, a phrase only
    answers when this matches - no loose substring, so "a focus session in
    psychology" is not the feature "Focus session", and "dark mode in chrome"
    is not a feature at all (Gemini review, 2026-10-20, section 11.8.3)."""
    if not target:
        return None
    try:
        import jarvis_feature_guide as FG
    except Exception:
        return None
    try:
        return FG.find_exact(target)
    except Exception:
        return None


def _feature_setting(target: str):
    """The one plain switch a fixed phrase names exactly, or None."""
    if not target:
        return None
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    try:
        return R.find_bool_setting(target)
    except Exception:
        return None


def _feature_context_ok(raw, explicit: bool = False) -> bool:
    """Is this sentence explicitly about Jarvis's OWN features?

    Either it named Jarvis ("Jarvis", "here", "my settings") as before, or it
    named the feature guide itself ("explain the prompt coach from your feature
    guide", "use the feature guide to ...") - which is at least as explicit a
    way of asking Jarvis's guide rather than the world (D1b, 2026-10-25).
    """
    return bool(explicit) or _feature_says_jarvis(raw)


def _setting_guide_intent(target: str):
    """The settings-registry answer for a question whose subject is no feature.

    THE SETTINGS-NAME FALLBACK (Gemini principal-architect ruling Q6 Step A,
    2026-10-26). `personality`, `voice speed` and `focus preset` are registry
    CHOICE_SETTINGS rows, and `theme` / `hud layout` are desktop-only controls
    inside a Settings card - none is a title or alias among the 140 catalogue
    rows, so "how do i change the personality?" missed every fixed phrase and
    reached the local model, which has no settings tool. When no feature
    matched, the SAME sentence is tried against the registry's own names; a
    hit answers here with the real Settings place and a real example phrase,
    with no model turn and no card. A subject the registry does not own still
    returns None, so an unknown name falls through exactly as before.

    A page-only row comes back as the existing `settings_not_by_asking`
    intent, so its refusal keeps one wording and one runner - including the
    `mixed` flag that offers "ask for it separately" when the sentence named
    another setting too.
    """
    if not target:
        return None
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    try:
        found = R.find_explain_setting(target)
    except Exception:
        return None
    if not found:
        return None
    if found.get("kind") == "page":
        return Intent("settings_not_by_asking",
                      {"dom_id": found.get("dom_id"),
                       "mixed": bool(found.get("mixed"))})
    return Intent("setting_explain", found)


def _feature_explain_intent(s: str, raw, target: str, explicit: bool = False):
    row = _feature_lookup_exact(target)
    if row is None and _feature_context_ok(raw, explicit):
        row = _feature_lookup(_feature_without_context(target))
    if row is not None:
        return Intent("feature_explain", {"id": row["id"]})
    # NO FEATURE BY THAT NAME: try the settings registry (ruling Q6 Step A).
    # The context word ("my settings", "Jarvis") is not part of a setting's
    # name, so the cleaned subject is tried too - it is the same subject the
    # feature lookup above was allowed to use loosely.
    got = (_setting_guide_intent(_feature_without_context(target))
           or _setting_guide_intent(target))
    if got is not None:
        return got
    # "I do not have that one" needs BOTH: the sentence said it is Jarvis's
    # own ("Jarvis", "here", "my settings", the feature guide) AND said the
    # word feature/option. A general "what is <something>" never receives
    # that answer.
    if _feature_context_ok(raw, explicit) and (_feature_explicit(s) or explicit):
        return Intent("feature_unknown",
                      {"words": _feature_target(_feature_without_context(target))})
    return None


def _feature_change_intent(s: str, raw, target: str, explicit: bool = False):
    """The intent behind "can I change <feature>?" - resolved, never guessed.

    A FEATURE first (its five-label kind is what the answer is built from), then
    a plain switch the registry already names exactly, then the settings-name
    fallback (CHOICE_SETTINGS and the desktop-only areas, ruling Q6 Step A),
    then the honest unknown answer under the same gate as every other fixed
    phrase: explicit Jarvis context AND the word feature/option.
    """
    row = _feature_lookup_exact(target)
    if row is not None:
        return Intent("feature_change", {"id": row["id"]})
    setting = _feature_setting(target)
    if setting is not None:
        return Intent("feature_change", {"key": setting.key, "name": setting.names[0]})
    if _feature_context_ok(raw, explicit):
        clean = _feature_without_context(target)
        row = _feature_lookup(clean)
        if row is not None:
            return Intent("feature_change", {"id": row["id"]})
        setting = _feature_setting(clean)
        if setting is not None:
            return Intent("feature_change",
                          {"key": setting.key, "name": setting.names[0]})
    # NO FEATURE AND NO PLAIN SWITCH BY THAT NAME: the settings registry is
    # the last thing tried before the honest unknown answer (ruling Q6 Step A),
    # so "can I change the personality?" answers instead of reaching the model.
    got = (_setting_guide_intent(_feature_without_context(target))
           or _setting_guide_intent(target))
    if got is not None:
        return got
    if _feature_context_ok(raw, explicit) and (_feature_explicit(s) or explicit):
        return Intent("feature_unknown",
                      {"words": _feature_target(_feature_without_context(target))})
    return None


def _feature_state_intent(raw, target: str, explicit: bool = False):
    row = _feature_lookup_exact(target)
    if row is not None:
        return Intent("feature_state", {"id": row["id"]})
    setting = _feature_setting(target)
    if setting is not None:
        return Intent("feature_state_setting", {"key": setting.key})
    if _feature_context_ok(raw, explicit):
        clean = _feature_without_context(target)
        row = _feature_lookup(clean)
        if row is not None:
            return Intent("feature_state", {"id": row["id"]})
        setting = _feature_setting(clean)
        if setting is not None:
            return Intent("feature_state_setting", {"key": setting.key})
    return None


def _feature_howto_intent(raw, target: str, on: bool, explicit: bool = False):
    row = _feature_lookup_exact(target)
    if row is not None:
        return Intent("feature_howto", {"id": row["id"], "on": bool(on)})
    setting = _feature_setting(target)
    if setting is not None:
        return Intent("feature_howto_setting", {"key": setting.key, "on": bool(on)})
    if _feature_context_ok(raw, explicit):
        clean = _feature_without_context(target)
        row = _feature_lookup(clean)
        if row is not None:
            return Intent("feature_howto", {"id": row["id"], "on": bool(on)})
        setting = _feature_setting(clean)
        if setting is not None:
            return Intent("feature_howto_setting", {"key": setting.key, "on": bool(on)})
    return None


def _feature_own_controls(row: dict) -> tuple:
    """`(switches, choices)` - the real settings the feature's own control table
    names, in the order that table lists them.

    WHY THIS EXISTS (2026-10-26). `jarvis_feature_guide.switch_target` links a
    feature to its switches through the feature list's own `covers`
    ("settings.<section id>"), and 124 of the 140 rows name no section that
    owns a switch (measured with FG.switches_for on every row). So "turn off
    Write like me" - a switch that exists, with its own route - was answered
    "that is a Command-Only ability ... there is no fixed sentence for it".
    The guide's OWN_CONTROLS/EXTRA_CONTROLS tables already carry the link the
    covers miss (the same tables the feature-controls matrix is built from),
    so this reads them rather than inventing a second list."""
    try:
        import jarvis_feature_guide as FG
        import jarvis_settings_registry as R
    except Exception:
        return (), ()
    fid = str((row or {}).get("id") or "")
    # An Always-On SAFETY RULE owns no switch (the same rule
    # `jarvis_feature_guide._build_matrix` applies through ALWAYS_ON_IDS,
    # Lead's 2026-10-22 ruling). It matters here because `switches_for` links a
    # switch through the SECTION a feature's covers name, and a section can be
    # shared: "Lock Jarvis" (app-lock) and the chat-history switch both live in
    # Settings, Security. Without this, "turn on Lock Jarvis" found exactly one
    # switch in its section and would have turned chat history on - the one
    # thing this matcher must never do. Caught by
    # tools/check_feature_controls.py guard 2 on 2026-10-28, when
    # chat_history.section became "security" (the settings audit's G5).
    if fid in (getattr(FG, "ALWAYS_ON_IDS", frozenset()) or ()):
        return (), ()
    keys = list((getattr(FG, "EXTRA_CONTROLS", {}) or {}).get(fid, ()))
    if not keys:
        own = (getattr(FG, "OWN_CONTROLS", {}) or {}).get(fid) or ()
        keys = list(own[0]) if own else []
    # PLUS whatever the guide's own `covers` link already finds, so the two
    # links ADD UP instead of one overruling the other. Custom voices is the
    # case that showed it: its own-control table names the voice CHOICE, while
    # its covers name the two switches beside it - and the owner means all
    # three when they say "custom voices" (2026-10-26).
    try:
        for found in FG.switches_for(row):
            if found.key not in keys:
                keys.append(found.key)
    except Exception:
        pass
    bools = {b.key: b for b in R.BOOL_SETTINGS}
    choices = {c.key: c for c in R.CHOICE_SETTINGS}
    return (tuple(bools[k] for k in keys if k in bools),
            tuple(choices[k] for k in keys if k in choices))


def _feature_switch_intent(raw, target: str, on: bool, explicit: bool = False):
    # The EXACT name first, before any context word is taken off: four features
    # have "Jarvis" in their own name ("How Jarvis talks", "Floating Jarvis",
    # "Starting Jarvis for you", "What Jarvis can reach"), and stripping the
    # context word first turned each of them into a different, unknown name, so
    # their "turn on <feature>" phrase answered nothing at all (measured
    # 2026-10-26 through jarvis_feature_guide.control_matrix()).
    clean = target
    row = _feature_lookup_exact(clean)
    if row is None and _feature_context_ok(raw, explicit):
        clean = _feature_without_context(target)
        row = _feature_lookup_exact(clean) or _feature_lookup(clean)
    if row is None:
        return None
    try:
        import jarvis_feature_guide as FG
        setting, why = FG.switch_target(clean)
    except Exception:
        return None
    if setting is not None:
        return Intent("feature_switch", {"key": setting.key, "on": bool(on)})
    # THE LINK `switch_target` COULD NOT SEE (2026-10-26). Its own table is the
    # truth about which settings a feature owns; one switch means switchable by
    # the feature's own name, several means say which, and a choice means say
    # how a choice is asked for. Never a guess, and never the "Command-Only"
    # sentence for a feature that really does have a control.
    switches, choices = _feature_own_controls(row)
    title = str(row.get("title") or "That feature")
    if len(switches) == 1:
        return Intent("feature_switch", {"key": switches[0].key, "on": bool(on)})
    if len(switches) > 1:
        # The same shape jarvis_feature_guide.switch_target writes when its own
        # link CAN see them: name every one, so the next sentence can name one.
        names = "; ".join((s.names[0] if s.names else s.key) for s in switches)
        return Intent("feature_switch_refused", {"words": (
            f"{title}: more than one switch - {names}. Say \"turn on <one of "
            f"those>\" for the one you mean.")})
    if choices:
        named = choices[0].names[0] if choices[0].names else choices[0].key
        return Intent("feature_switch_refused", {"words": (
            f"{title} is not simply on or off - it is a choice. Say \"set "
            f"{named} to <one of its values>\", or ask \"what are the choices "
            f"for {named}?\" and I will read them out.")})
    # THE WAKE WORD'S OWN TITLE (2026-10-26). Its switch is NOT a BoolSetting -
    # it is the PC's "hey Jarvis" switch, `jarvis_speech.set_wake_enabled` - so
    # the guide's control tables name no key for this row, and the fall-through
    # below answered the false "Command-Only ... there is no fixed sentence for
    # it" sentence for a feature that HAS a working phrase. Name that phrase
    # instead. (Mapping the title straight to `settings_wake_word` was the
    # other option; not taken here because the feature directory and
    # contract/feature-controls.json record this row as planned, and changing
    # them is a separate, contract-owned edit - naming the real phrase is
    # enough to stop the false sentence, and it never changes anything.)
    if str(row.get("id") or "") == "wake-word":
        return Intent("feature_switch_refused", {"words": (
            f"{title} is the PC's \"hey Jarvis\" switch. Say \"turn on the wake "
            f"word\" or \"turn off the wake word\" and it goes through that "
            f"switch's own rule: turning it on asks on one card, and turning "
            f"it off is instant.")})
    return Intent("feature_switch_refused", {"words": why})


# --------------------------------------------------------------------------
#   Changing a setting by asking for it ON or OFF (2026-10-27)
#
#   THE GAP THIS CLOSES, measured through match() on 2026-10-27 rather than
#   assumed. "Make the prompt coach off", "set web search to off", "change the
#   prompt coach to off", "I want the prompt coach off" and "the prompt coach
#   should be off" - the plainest way there is to ask for a change - each
#   matched NOTHING in this file and went to the model, which has no settings
#   tool and cannot flip one. The two doors that did work are "turn on/off
#   <name>" (the settings block, `_settings_adjust`) and "can I change <name>"
#   (this block, which only explains). So the sentence the owner is most likely
#   to say was the one sentence that did nothing, which is the failure this
#   slice exists to remove.
#
#   WHAT THIS IS ALLOWED TO DO: one thing. For the settings named in
#   `CHANGE_BY_ASKING`, call the SAME `BoolSetting.set` the Settings switch,
#   the HUD route and the "turn on/off" phrase already call
#   (`_run_feature_change_apply`). That setter owns the card, the tier, the
#   PC-only refusal and the wording, so this grammar can add no permission of
#   its own - it is a second DOOR to the same gate, never a second gate.
#
#   WHAT IT IS NOT ALLOWED TO DO, and where each refusal comes from:
#     * a name that is a real setting NOT on the list -> `feature_change`, the
#       guide's own change sentence, word for word. That is the answer "can I
#       change <it>" already gives, so nothing new is promised and #884's
#       wording is not touched.
#     * a page-only setting ("app lock", "autostart") -> `NOT_BY_ASKING`'s own
#       sentence, through `settings_not_by_asking` - the same intent and the
#       same words the "turn off <name>" phrase already gets.
#     * a password, a key, a token, deep config, or something that cannot be
#       undone -> ONE plain sentence from `_CHANGE_NEVER`, and nothing changed.
#     * anything else -> None, exactly as today (the model).
#
#   A CARD IS NEVER APPROVED HERE. There is no `jarvis_gate` call in this file
#   at all: the setter raises its card, and this lane reports only what the
#   setter said ("waiting") or what TWO real reads of the setting agree on.
# --------------------------------------------------------------------------

#: The settings this lane may change by asking, and ONLY these (2026-10-27).
#:
#: One entry per `jarvis_settings_registry.BOOL_SETTINGS` row that passes all
#: three tests below. Each exclusion is deliberate, and the reasons are the
#: slice's safety argument rather than a preference:
#:
#:   1. its writer IS a table entry (`BoolSetting.set`), so the change goes
#:      through the exact function the Settings switch, the HUD route and the
#:      spoken "turn on/off" phrase call. No second implementation, no route of
#:      its own, no card of its own.
#:   2. `jarvis_feature_guide.read_state` answers a real True/False for it, so
#:      the receipt is a READ and never a claim. The three `second_card_*`
#:      switches are EXCLUDED for exactly this reason: measured 2026-10-27,
#:      `read_state` returns None for all three (that card's features are not
#:      measured yet - CLAUDE.md), so a receipt for them would be a guess. Any
#:      setting added later without a reader stays out by the same rule.
#:   3. its card is NOT one only the PC may approve. `lights_without_card` is
#:      EXCLUDED: its card is `loosen_what_asks_first`, which
#:      `jarvis_owner_check.PC_ONLY_ACTIONS` refuses on any other device, so
#:      starting it from chat would make this lane depend on the phone/PC
#:      distinction it deliberately does not make. Its own "turn off lights
#:      without asking" phrase still works, with its own card, unchanged.
#:
#: Every entry is reversible: it is a stored on/off value, and the same
#: sentence the other way round is the undo. Where a module's own rule says one
#: direction must ask, that card is the module's - `_run_feature_change_apply`
#: never reports "waiting" as done.
CHANGE_BY_ASKING = frozenset({
    # Immediate either way, and cosmetic or local: each one's own setter says
    # so in its docstring (jarvis_settings_registry.set_prompt_coach,
    # set_humor, set_voice_follows_face, set_pictures).
    "prompt_coach", "humor", "voice_follows_face", "pictures",
    # The Anti-Slop filter (2026-10-28): instant in both directions, no card
    # either way (jarvis_settings_registry.set_antislop). Its reader answers a
    # real True/False (`_read_antislop`), so the read-back below is a read and
    # not a claim.
    "antislop",
    # The Jarvis-owned local calendar (2026-10-29): the same shape as the
    # Anti-Slop filter above. `set_jarvis_calendar` calls the module's own
    # `handle_settings`, the one function its route and its typed switch call,
    # and reads the same stored value back - a preference either way, with no
    # card, no model call and nothing deleted when it is turned off. Its reader
    # (`_read_jarvis_calendar`) answers a real True/False, so the read-back is a
    # read and not a claim.
    "jarvis_calendar",
    # The five PC-notification switches. They ride `jarvis_limits.change`, and
    # all seven of those rows are `loosening="none"` on purpose: a switch that
    # only decides whether this PC shows its owner a toast may not wait behind
    # a card, because an alarm must never fail to ring (the registry's own
    # header says this at `_NOTIFY_LIMIT`).
    "pc_alarm_sounds", "pc_reminder_sounds", "pc_briefing_notification",
    "pc_handoff_notification", "pc_quiet_hours",
    # Everything below asks on ONE direction through its OWN module's card
    # (and is immediate on the narrowing direction). The lane does not decide
    # that - the setter does, exactly as it does for the Settings switch.
    "ask_before_every_search", "background_learning", "learn_sensitive_topics",
    "web_search", "smartwatch_notifications", "phone_notifications",
    "screen_picture", "headless_browser", "sandbox_exec", "media_index",
    "briefing_senders", "big_coder", "better_voice", "chat_history",
    "write_like_me", "big_model", "big_model_wiki",
    "big_model_deep_questions",
})


#: The four words a described state can wear. "enabled"/"disabled" are here
#: because the owner says them ("the prompt coach should be disabled"), not
#: because they are a second grammar: each maps to one bool below.
_CHANGE_STATE_WORD = r"(?:on|off|enabled|disabled)"
#: The change ask with the wanted STATE in it. "turn/switch/enable/disable"
#: are deliberately NOT here: the settings block (`_ADJUST_ONOFF`) owns those
#: words for EVERY switch and must keep owning them, or a phrase that works
#: today would change hands. What is here is the shapes measured above as
#: falling to the model.
#:
#: The "make sure"/"ensure" alternative is FIRST because "make" would otherwise
#: match first and read "sure the prompt coach is" as the name.
_CHANGE_SAYS_STATE = re.compile(
    r"(?:make\s+sure|ensure)\s+(?:the\s+|my\s+|a\s+|an\s+)?(?P<e>.+?)\s+"
    r"(?:is|are|stays?|remains?)\s+(?:turned\s+|switched\s+)?"
    r"(?P<eon>" + _CHANGE_STATE_WORD + r")"
    r"|(?:make|set|put)\s+(?:the\s+|my\s+|a\s+|an\s+)?(?P<a>.+?)\s+"
    r"(?:to\s+)?(?P<aon>" + _CHANGE_STATE_WORD + r")"
    r"|(?:change|adjust|alter|switch|turn)\s+(?:the\s+|my\s+|a\s+|an\s+)?"
    r"(?P<b>.+?)\s+to\s+(?P<bon>" + _CHANGE_STATE_WORD + r")"
    r"|(?:i\s+(?:want|need|would\s+like)|i'd\s+like)\s+(?:you\s+to\s+)?"
    r"(?:the\s+|my\s+|a\s+|an\s+)?(?P<c>.+?)\s+(?:to\s+be\s+|be\s+)?"
    r"(?:turned\s+|switched\s+)?(?P<con>" + _CHANGE_STATE_WORD + r")"
    r"|(?:the\s+|my\s+)?(?P<d>.+?)\s+(?:should|must|needs?\s+to)\s+"
    r"(?:be|stay|remain)\s+(?:turned\s+|switched\s+)?"
    r"(?P<don>" + _CHANGE_STATE_WORD + r")")
#: A change ask that names a setting and does NOT say which state is wanted:
#: "change the prompt coach", "toggle web search", "adjust the prompt coach".
#: It is answered with ONE question and nothing else - never a guess, and never
#: a card. "set"/"switch" are here for the same reason as above: the settings
#: block claims "set <choice> to <value>" and "switch on/off <name>" first, so
#: by the time these lines run those sentences are gone.
_CHANGE_SAYS_NOTHING = re.compile(
    r"(?:change|adjust|alter|toggle|switch|set)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+)")
#: A state word ANYWHERE in the name the change ask left behind. Used only to
#: NOT read a two-part sentence (see `_change_by_asking_intent`): "I want the
#: prompt coach off and the lights on" must never be read as one switch.
_CHANGE_STATE_SEEN = re.compile(r"\b(?:on|off|enabled|disabled)\b")
#: Four kinds of ask this lane must refuse in ONE plain sentence, because there
#: is no switch behind them and no undo after them. Each pattern is matched
#: against the name ONLY, after the sentence has already been resolved to
#: nothing this file knows - so it cannot take a real setting's words away.
_CHANGE_NEVER = (
    (re.compile(r"\b(?:pass\s?word|passcode|pin)\b"),
     "I never change a password from chat - that stays with you, on the PC."),
    (re.compile(r"\b(?:api\s*keys?|keys?|tokens?|secrets?|credentials?"
                r"|pairing|fingerprints?|windows\s+hello|biometrics?)\b"),
     "I never change a key, a token or a credential from chat, and I never "
     "would - that stays on the PC."),
    (re.compile(r"\b(?:config|configuration|settings?\s+file|jarvis[- ]framework"
                r"|framework\.toml|toml|approval\s+(?:tiers?|rules?)|tiers?"
                r"|the\s+gate|gate\s+rules?|auto[- ]?approv\w*)\b"),
     "That is deep configuration, not a simple switch - I only change on/off "
     "settings from chat, and that one stays in the config file on the PC."),
    (re.compile(r"\b(?:wipe|erase|factory\s+reset|uninstall|reinstall"
                r"|delete\s+(?:everything|all)|forget\s+everything"
                r"|clear\s+everything)\b"),
     "That cannot be undone, so I do not do it from chat - open the screen that "
     "owns it and I will walk you through it there."),
)


def _change_name(setting) -> str:
    """The switch's own first name, or its key when it has none."""
    names = getattr(setting, "names", ()) or ()
    return str(names[0]) if names else str(getattr(setting, "key", "") or "")


def _change_never_words(target: str) -> Optional[str]:
    """ONE plain sentence when `target` names something this lane must refuse,
    or None. Checked only after no setting and no page-only row matched, so a
    real setting's own name can never be swallowed by it."""
    text = " ".join(str(target or "").lower().split())
    if text.startswith(("the ", "my ", "a ", "an ")):
        text = text.split(" ", 1)[1]
    for pattern, words in _CHANGE_NEVER:
        if pattern.search(text):
            return words
    return None


def _change_by_asking_intent(target: str, on):
    """The intent behind "make <setting> on/off" and "change <setting>".

    `on` is True/False when the sentence said the state, None when it did not.
    Never a guess: the name must be one the registry itself resolves (exact, or
    its own filler-tolerant form), and the state must be IN the sentence.
    """
    target = _feature_target(target)
    if not target:
        return None
    try:
        import jarvis_settings_registry as R
    except Exception:                       # noqa: BLE001 - no registry, no lane
        return None
    # A PAGE-ONLY SETTING IS DECIDED FIRST, on the same filler-tolerant words
    # the settings block uses (2026-10-26's lesson): a page-only name must get
    # its own refusal, and no switch may be read inside those words.
    dom_id = R.find_not_by_asking_words(target)
    if dom_id is not None:
        return Intent("settings_not_by_asking", {"dom_id": dom_id})
    # Then a name this lane must never act on: refused in ONE plain sentence
    # before anything else can read a switch inside it, so "set my password to
    # something new" cannot fall past the "to" guard below to the model, which
    # would answer it as though it could.
    words = _change_never_words(target)
    if words:
        return Intent("feature_change_refused", {"words": words})
    if on is None and re.search(r"\s+to\s+", target):
        # "set the prompt coach to medium": a VALUE is being given, and it is
        # not on/off. That is a different lane's question (or the model's), and
        # asking "on or off?" here would be answering a question nobody asked.
        return None
    setting = R.find_bool_setting(target)
    if setting is None and _CHANGE_STATE_SEEN.search(target):
        # MORE THAN ONE STATE IN THE SENTENCE. "I want the prompt coach off and
        # the lights on" leaves a target of "the prompt coach off and the
        # lights", which CONTAINS a switch's whole name - so the tolerant
        # matcher would read the FIRST clause and act on the state word at the
        # END of the sentence, i.e. the wrong direction. One write per sentence
        # is the rule, so a multi-part sentence is not read here at all; it
        # goes to the model exactly as it did before. An EXACT name that
        # happens to contain "on" ("one bigger model on both cards") resolved
        # above and is unaffected, which is why this test is on "did not
        # resolve", not on the words alone.
        return None
    if setting is None and on is not None:
        # The tolerant form is for a state the owner DID say ("make learning in
        # the background off"). With no state said, only the exact name gets
        # the one question back: "change the prompt coach to medium" must not
        # become "on or off?" just because those words contain a switch's name.
        setting = R.find_bool_setting_words(target)
    if setting is not None:
        name = _change_name(setting)
        if setting.key in CHANGE_BY_ASKING and isinstance(on, bool):
            return Intent("feature_change_apply", {"key": setting.key, "on": on})
        if setting.key in CHANGE_BY_ASKING:
            # A real switch, named, with no state wanted: ONE question back.
            return Intent("feature_change_ask", {"key": setting.key, "name": name})
        # Real, named, and deliberately not in this lane: the guide's own
        # change sentence, the same words "can I change <it>" already gives.
        return Intent("feature_change", {"key": setting.key, "name": name})
    return None


def _change_says_state(m) -> tuple:
    """(target, True/False) from `_CHANGE_SAYS_STATE`'s own group names."""
    for who, state in (("e", "eon"), ("a", "aon"), ("b", "bon"),
                       ("c", "con"), ("d", "don")):
        if m.group(who) is not None:
            return m.group(who), m.group(state) in ("on", "enabled")
    return "", None


#: "from your feature guide", "in the guide", "according to the feature
#: guide" - the tail that says WHICH guide to answer from, not part of a
#: feature's name (D1b, 2026-10-25). Anchored at the end of the sentence.
_GUIDE_TAIL = re.compile(
    r"\s*(?:,|\s)*\b(?:from|in|out\s+of|per|using)\s+(?:your|the|my)\s+(?:jarvis\s+)?"
    r"(?:own\s+)?feature\s+guide\b.*$"
    r"|\s*(?:,|\s)*\baccording\s+to\s+(?:your|the|my)\s+(?:jarvis\s+)?feature\s+guide\b.*$")
#: "use the feature guide to ...", "check the feature guide for ...",
#: "read your feature guide and tell me ..." - the owner naming the guide
#: before the question. Group 1 is the rest of the sentence.
_GUIDE_LEAD = re.compile(
    r"(?:please\s+)?(?:use|check|read|consult|look\s+(?:in|at)|search|ask|open|"
    r"show\s+me\s+in|according\s+to)\s+(?:your|the|my)\s+(?:jarvis\s+)?(?:own\s+)?"
    r"feature\s+guide\s*(?:[,;:-]\s*)?(.*)$")


def _feature_light(raw) -> str:
    """The message with only its ADDRESS taken off - keeps a name's own words.

    `normalise` strips "jarvis" and "for me" from the end of a sentence (they
    are how people address Jarvis), and two features are NAMED with those
    words: "Floating Jarvis" arrived as "floating", and "Talk to a chatbot for
    me" as "talk to a chatbot" - neither is a row, so both fell to the model.
    This keeps everything except a leading "Jarvis," and a trailing "please",
    so the same patterns can try the owner's words intact. It grants no extra
    reach: the exact-name gate is the same one (`_feature_guide_body`).
    """
    text = str(raw or "").lower().strip()
    text = re.sub(r"^(?:hey\s+)?jarvis\s*[,;:.!-]?\s*", "", text)
    text = re.sub(r"[\s,]+(?:please|thanks|thank\s+you)\s*$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;:.!?")


def _feature_guide(s: str, raw: str = "") -> Optional[Intent]:
    """The whole feature-guidance block, in one place, in this order.

    `s` is the tidied sentence (no leading "Jarvis,"); `raw` is the message as
    typed/spoken, used for the explicit-context check (see _FEATURE_CONTEXT)
    and for the second attempt below.

    NAMING THE GUIDE IS ITSELF THE CONTEXT (D1b, the live campaign of
    2026-10-25). A7c's words - "explain the prompt coach feature from your
    feature guide" - missed every matcher here and went to the 9B model, which
    invented four feature names that appear nowhere in the guide. The owner
    asking the feature guide is at least as explicit as saying "Jarvis", so a
    trailing "from your feature guide" is taken off, a leading "use/check the
    feature guide to ..." is taken off, and the rest of the sentence is read by
    the SAME patterns below - with `said_guide` counting as explicit context.

    TWO ATTEMPTS, ONE GATE (2026-10-26). The patterns run on the tidied
    sentence; when that finds nothing, they run once more on `_feature_light`
    (address only removed), so a feature whose own name ends in "Jarvis" or
    "for me" still resolves. The exact-name-or-explicit-context rule is applied
    identically in both, so this adds reach for real names, never a guess.
    """
    said_guide = False
    m = _GUIDE_TAIL.search(s)
    if m:
        said_guide = True
        s = s[:m.start()].strip(" ,;:-")
    m = _GUIDE_LEAD.fullmatch(s)
    if m:
        said_guide = True
        s = (m.group(1) or "").strip()
        # "use the feature guide to explain <x>" / "check the feature guide
        # for <x>": the words after the lead are the question.
        s = re.sub(r"^to\s+", "", s).strip()
        only = re.fullmatch(r"(?:for|about|on|of)\s+(.+)", s)
        if only:
            return _feature_explain_intent(s, raw,
                                          _feature_target(only.group(1)), said_guide)
    if not s:
        return None
    got = _feature_guide_body(s, raw, said_guide)
    if got is not None:
        return got
    light = _feature_light(raw)
    if not light or light == s:
        return None
    m = _GUIDE_TAIL.search(light)
    if m:
        light = light[:m.start()].strip(" ,;:-")
    if not light or light == s:
        return None
    return _feature_guide_body(light, raw, said_guide)


def _feature_guide_body(s: str, raw: str, said_guide: bool) -> Optional[Intent]:
    """The patterns themselves, on one candidate sentence. See _feature_guide."""
    if _CLOUD_SYNC_TOPIC.search(s):
        # The guide's #646 note is the answer: Jarvis does not use cloud sync.
        # Answered here, deterministically, so a model never gets to suggest a
        # third-party sync folder.
        return Intent("feature_explain", {"id": s})
    m = _FEATURE_OVERVIEW_ABOUT.fullmatch(s)
    if m:
        got = _feature_overview_about_intent(raw, m.group(1))
        if got is not None:
            return got
    got = _feature_capabilities(s)
    if got is not None:
        return got
    if _FEATURES_LIST.fullmatch(s):
        return Intent("features_list")
    m = _FEATURES_GROUP.fullmatch(s)
    if m:
        return Intent("features_group", {"group": (m.group(1) or m.group(2) or "").strip()})
    # ---- detail shapes (2026-10-31, the owner's depth ask) -----------------
    m = _FEAT_DETAIL.fullmatch(s)
    if m:
        got = _feature_detail_intent(raw, m.group(1) or m.group(2) or "", "detail")
        if got is not None:
            return got
    m = _FEAT_HOW_USE.fullmatch(s)
    if m:
        target = m.group("setup") or m.group("use") or ""
        got = _feature_detail_intent(raw, target, "detail")
        if got is not None:
            return got
    m = _FEAT_EXAMPLE.fullmatch(s)
    if m:
        got = _feature_detail_intent(raw, m.group(1), "example")
        if got is not None:
            return got
    m = _FEAT_PRIVATE.fullmatch(s)
    if m:
        got = _feature_detail_intent(raw, m.group(1), "private")
        if got is not None:
            return got
    m = _FEAT_NEEDS.fullmatch(s)
    if m:
        got = _feature_detail_intent(raw, m.group(1), "needs")
        if got is not None:
            return got
    m = _FEAT_WHY_STATE.fullmatch(s)
    if m:
        got = _feature_detail_intent(raw, m.group(1), "why_state")
        if got is not None:
            return got
    m = _FEAT_WRONG.fullmatch(s)
    if m:
        got = _feature_detail_intent(raw, m.group(1), "goes_wrong")
        if got is not None:
            return got
    m = _FEAT_CAN_DO.fullmatch(s)
    if m:
        got = _feature_can_do_intent(raw, m.group(1), m.group(2))
        if got is not None:
            return got
    m = _FEAT_LIKE.fullmatch(s)
    if m:
        got = _feature_detail_intent(raw, m.group(1), "like")
        if got is not None:
            return got
    m = _FEATURE_TRAIN.fullmatch(s)
    if m:
        # "how do I train you to write like me?" - explain the feature named
        # after "to", never a switch (it has no on/off of its own).
        return _feature_explain_intent(s, raw, _feature_target(m.group(1)), said_guide)
    m = _FEATURE_HOWTO.fullmatch(s)
    if m:
        g = m.groups()
        if g[0] is not None:            # how do i turn on/off <x>
            on, target = g[0] == "on", g[1]
        elif g[2] is not None:          # how do i enable/disable <x>
            on, target = g[2] == "enable", g[3]
        elif g[4] is not None:          # how to turn on/off <x>
            on, target = g[4] == "on", g[5]
        elif g[6] is not None:          # where do i turn on/off <x>
            on, target = g[6] == "on", g[7]
        else:                           # where do i enable/disable <x>
            on, target = g[8] == "enable", g[9]
        return _feature_howto_intent(raw, _feature_target(target), on, said_guide)
    m = _FEATURE_USE.fullmatch(s)
    if m:
        target = _feature_target(next(g for g in m.groups() if g is not None))
        if not target:
            return None
        return _feature_explain_intent(s, raw, target, said_guide)
    m = _FEATURE_WHERE.fullmatch(s)
    if m:
        target = _feature_target(next(g for g in m.groups() if g is not None))
        if not target:
            return None
        return _feature_explain_intent(s, raw, target, said_guide)
    # CHANGING A SETTING BY ASKING FOR IT ON OR OFF (2026-10-27). BEFORE the
    # "can I change" pattern on purpose, and AFTER every pattern above it, so
    # the sentences those already own keep their own answer: no pattern above
    # starts with a bare "make/set/change/toggle", and none of these patterns
    # can match "how do I ...", "where do I ..." or "is ... on".
    m = _CHANGE_SAYS_STATE.fullmatch(s)
    if m:
        target, on = _change_says_state(m)
        got = _change_by_asking_intent(target, on)
        if got is not None:
            return got
    m = _CHANGE_SAYS_NOTHING.fullmatch(s)
    if m:
        got = _change_by_asking_intent(m.group(1), None)
        if got is not None:
            return got
    m = _FEATURE_CHANGE.fullmatch(s)
    if m:
        target = _feature_target(next(g for g in m.groups() if g is not None))
        if not target:
            return None
        return _feature_change_intent(s, raw, target, said_guide)
    m = _FEATURE_STATE.fullmatch(s)
    if m:
        got = _feature_state_intent(raw, _feature_target(m.group(1) or m.group(2) or ""),
                                    said_guide)
        if got is not None:
            return got
    # ---- discussion shapes (2026-10-31, pass-11 audit) ---------------------
    m = _FEATURE_LIMITS.fullmatch(s)
    if m:
        got = _feature_discussion_intent(raw, m.group(1), "feature_limits")
        if got is not None:
            return got
    m = _FEATURE_ASKS.fullmatch(s)
    if m:
        got = _feature_discussion_intent(raw, m.group(1), "feature_asks")
        if got is not None:
            return got
    m = _FEATURE_APP.fullmatch(s)
    if m:
        target = next((g for g in m.groups() if g is not None), "")
        got = _feature_discussion_intent(raw, target, "feature_app")
        if got is not None:
            return got
    m = _FEATURE_WHY.fullmatch(s)
    if m:
        got = _feature_discussion_intent(raw, m.group(1), "feature_why")
        if got is not None:
            return got
    m = _FEATURE_DIFFERENCE.fullmatch(s)
    if m:
        g = m.groups()
        first = next((g[i] for i in (0, 2, 4) if g[i] is not None), "")
        second = next((g[i] for i in (1, 3, 5) if g[i] is not None), "")
        got = _feature_difference_intent(raw, first, second)
        if got is not None:
            return got
    m = _FEATURE_ON_OFF.fullmatch(s)
    if m:
        got = _feature_state_intent(raw, _feature_target(m.group(1)))
        if got is not None:
            return got
    m = _FEATURE_HOW_WORKS.fullmatch(s)
    if m:
        row = _feature_row_loose(_feature_target(m.group(1)))
        if row is not None:
            return Intent("feature_explain", {"id": row["id"]})
    m = _FEATURE_WHAT.fullmatch(s)
    if m:
        target = _feature_target(next(g for g in m.groups() if g is not None))
        if not target:
            return None
        return _feature_explain_intent(s, raw, target, said_guide)
    m = _FEATURE_SWITCH.fullmatch(s)
    if m:
        g = m.groups()
        if g[0] is not None:            # turn/switch on|off <x>
            on, target = g[0] == "on", g[1]
        elif g[2] is not None:          # turn/switch <x> on|off
            on, target = g[3] == "on", g[2]
        else:                           # enable/disable <x>
            on, target = g[4] == "enable", g[5]
        return _feature_switch_intent(raw, _feature_target(target), on, said_guide)
    return None


# --------------------------------------------------------------------------
#   Animal options, by asking (the owner's decision of 2026-09-28: "Jarvis
#   can change any of them when asked ... the same rules as the switch").
#   The shared switches and the sky change on the PC (jarvis_settings_
#   registry's animal functions, the same ones the switches call); sharpness
#   and frame rate are per device, so the answer carries `face_tuning` in
#   X-Jarvis-Route and the app that asked changes itself. Whole sentences
#   only, like everything here, and only names jarvis_animal.py / this block
#   list - anything else about the animal gets a plain question back.
# --------------------------------------------------------------------------

#: What "the animal" may be called: the word itself, one of the four, or the robot.
_BEAST = (r"(?:the\s+|my\s+)?(?:animal|animals|animal\s+face|red\s+panda|panda|owl|sea\s+otter"
          r"|otter|monkey|robot)")
_BEASTS = _BEAST + r"(?:'s|s')?"

_STILL_ON = re.compile(
    r"keep\s+" + _BEAST + r"\s+still"
    r"|make\s+" + _BEAST + r"\s+(?:keep|stay|be|sit|hold)\s+still"
    r"|(?:stop|no\s+more)\s+" + _BEAST + r"\s+(?:moving(?:\s+around)?|fidgeting|looking\s+around)"
    r"|(?:tell\s+)?" + _BEAST + r"\s+(?:to\s+)?(?:keep|stay|sit|hold)\s+still")
_STILL_OFF = re.compile(
    r"let\s+" + _BEAST + r"\s+move(?:\s+(?:again|around|as\s+usual|normally))?"
    r"|(?:stop|don'?t)\s+keep(?:ing)?\s+" + _BEAST + r"\s+still"
    r"|" + _BEAST + r"\s+(?:can|may)\s+move(?:\s+(?:again|around|as\s+usual|normally))?")

#: "turn on X" / "switch X off" / "enable X" / "disable X" / "stop X".
_ONOFF = re.compile(
    r"(?:turn|switch)\s+(on|off)\s+(.+)"
    r"|(?:turn|switch)\s+(.+?)\s+(on|off)"
    r"|(enable|disable)\s+(.+)"
    r"|(stop|no\s+more)\s+(.+)")
_SHOWHIDE = re.compile(r"(show|hide)\s+(?:me\s+)?(.+)")

#: A tail's "for the animal" / "behind the animal" / "the animal's" parts -
#: and "behind the face", the words the sky's own switches use (so they read
#: right for the robot too).
_TAIL_FOR = re.compile(r"\s+(?:for|on|behind|around|in)\s+(?:" + _BEAST
                       + r"|(?:the\s+|my\s+)?face)(?:'s\s+scene)?$")
_HEAD_OF = re.compile(r"^" + _BEASTS + r"\s+")

_SKY_NAMES = ("sun and moon", "sun and the moon", "the sun and moon", "the sun and the moon",
              "sky", "the sky", "sun and moon scene")
_WEATHER_NAMES = ("weather", "the weather", "weather scene", "the weather scene",
                  "weather in the scene", "rain and snow")

_SOURCE = r"(open[\s-]?meteo(?:\s+online)?|(?:my\s+|the\s+)?home\s+assistant|off|nothing|none|no\s+weather)"
_WEATHER_SRC = re.compile(
    r"(?:use|pick|choose|switch\s+to|get)\s+" + _SOURCE + r"\s+(?:for|as)\s+(?:the\s+)?"
    r"(?:" + _BEASTS + r"\s+)?weather(?:\s+source)?(?:\s+for\s+" + _BEAST + r")?"
    r"|(?:get|take|draw)\s+(?:the\s+)?(?:" + _BEASTS + r"\s+)?weather\s+from\s+" + _SOURCE
    + r"|(?:set|switch|change|put)\s+(?:the\s+)?(?:" + _BEASTS + r"\s+)?weather(?:\s+source)?"
    r"\s+to\s+" + _SOURCE)

_SHARP_WORD = {"lower": "low", "low": "low", "lowest": "low", "balanced": "medium",
               "medium": "medium", "high": "high", "maximum": "max", "max": "max",
               "highest": "max", "full": "max"}
_RATE_WORD = {"30": "30", "thirty": "30", "60": "60", "sixty": "60", "90": "90",
              "ninety": "90", "120": "120", "a hundred and twenty": "120",
              "one hundred and twenty": "120", "max": "max", "maximum": "max"}
_DEV_MAKE = re.compile(
    r"make\s+" + _BEAST + r"(?:\s+look)?\s+(sharper|crisper|clearer|more\s+detailed"
    r"|softer|less\s+sharp|blurrier|smoother|less\s+smooth|choppier)"
    r"|make\s+" + _BEAST + r"(?:\s+look)?\s+as\s+sharp\s+as\s+(?:it\s+can(?:\s+be)?|possible)")
#: "Sharpness" alone is the face's own word; "quality", "resolution" and
#: "frame rate" are everyday words for video, games and screens, so they
#: count only when an animal, robot or face is named ("lower the frame rate"
#: on its own is not an animal request - it goes to the model).
_DEV_WHAT = (r"(?:(?:the\s+)?(sharpness)"
             r"|(?:" + _BEASTS + r"|(?:the\s+|my\s+)?face(?:'s)?)\s+(sharpness|quality|resolution|frame\s?rate))")
_DEV_UPDOWN = re.compile(
    r"(raise|increase|turn\s+up|lower|reduce|decrease|turn\s+down)\s+" + _DEV_WHAT)
_DEV_SET = re.compile(
    r"(?:set|change|put|switch)\s+" + _DEV_WHAT + r"\s+to\s+(.+?)(?:\s+(?:fps|frames\s+a\s+second))?")
_DEV_AUTO = re.compile(
    r"(?:turn|switch)\s+on\s+auto(?:matic)?[\s-]?adjust(?:ment)?"
    r"|let\s+" + _BEAST + r"\s+(?:pick|choose|adjust)\s+(?:its\s+own\s+)?(?:sharpness(?:\s+and\s+"
    r"frame\s?rate)?|quality|settings)(?:\s+(?:itself|automatically))?"
    r"|(?:set|put)\s+(?:the\s+)?(?:" + _BEASTS + r"\s+)?(?:sharpness|quality)\s+(?:back\s+)?to\s+auto(?:matic)?")

#: An animal request nothing else understood - asked back, never guessed.
#: Only "the animal" itself (not a named animal: "set a timer for the
#: monkey bread" is a timer), and only as the thing being changed.
_ANIMAL_UNSURE = re.compile(
    r"(?:turn|switch|make|set|change|stop|let|keep|enable|disable)\s+(?:on\s+|off\s+)?"
    r"(?:the\s+|my\s+)?animal(?:'s|s)?(?:\s+.*)?")
_WEATHER_ON = re.compile(
    r"(?:turn|switch)\s+on\s+(?:the\s+)?(?:" + _BEASTS + r"\s+)?weather(?:\s+scene)?"
    r"(?:\s+(?:for|behind)\s+" + _BEAST + r")?"
    r"|(?:turn|switch)\s+(?:the\s+)?(?:" + _BEASTS + r"\s+)?weather(?:\s+scene)?\s+on"
    r"|(?:enable|show)\s+(?:the\s+)?(?:" + _BEASTS + r"\s+)?weather\s+(?:for|behind)\s+" + _BEAST
    + r"|enable\s+(?:the\s+)?weather(?:\s+scene)?")


def _animal_target(tail: str):
    """("switch", id) | ("sky", None) | ("weather", None) | None, for the
    thing a "turn on/off ..." tail names - exact names only."""
    t = " ".join(tail.split())
    t = _TAIL_FOR.sub("", t)
    for cand in (t, _HEAD_OF.sub("", t)):
        bare = re.sub(r"^(?:the|my)\s+", "", cand)
        if bare in _SKY_NAMES or cand in _SKY_NAMES:
            return ("sky", None)
        if bare in _WEATHER_NAMES or cand in _WEATHER_NAMES:
            return ("weather", None)
        try:
            import jarvis_settings_registry as R
        except Exception:
            return None
        key = R.find_animal_switch(cand)
        if key is not None:
            return ("switch", key)
    return None


def _source_of(word: str) -> Optional[str]:
    w = word.strip()
    if re.fullmatch(r"open[\s-]?meteo(?:\s+online)?", w):
        return "open_meteo"
    if re.fullmatch(r"(?:my\s+|the\s+)?home\s+assistant", w):
        return "home_assistant"
    if w in ("off", "nothing", "none", "no weather"):
        return "off"
    return None


def _animal(s: str) -> Optional[Intent]:
    # "Keep the animal still" and its opposite.
    if _STILL_ON.fullmatch(s):
        return Intent("animal_switch", {"key": "still", "on": True})
    if _STILL_OFF.fullmatch(s):
        return Intent("animal_switch", {"key": "still", "on": False})
    # The weather's source, by name.
    m = _WEATHER_SRC.fullmatch(s)
    if m:
        src = _source_of(next(g for g in m.groups() if g))
        if src is not None:
            return Intent("animal_weather", {"source": src})
    # "Turn on the weather" names no source: asked, never guessed.
    if _WEATHER_ON.fullmatch(s):
        return Intent("animal_ask", {"about": "weather"})
    # Per device: sharpness and frame rate.
    if _DEV_AUTO.fullmatch(s):
        return Intent("animal_device", {"change": "auto"})
    m = _DEV_MAKE.fullmatch(s)
    if m:
        w = m.group(1)
        change = ("sharpness:max" if w is None else
                  "sharper" if w in ("sharper", "crisper", "clearer") or w.startswith("more")
                  else "softer" if w in ("softer", "blurrier") or w == "less sharp"
                  else "smoother" if w == "smoother" else "less_smooth")
        return Intent("animal_device", {"change": change})
    m = _DEV_UPDOWN.fullmatch(s)
    if m:
        up = m.group(1) in ("raise", "increase", "turn up")
        rate = (m.group(2) or m.group(3)).startswith("frame")
        change = ("smoother" if up else "less_smooth") if rate else ("sharper" if up else "softer")
        return Intent("animal_device", {"change": change})
    m = _DEV_SET.fullmatch(s)
    if m:
        what, value = (m.group(1) or m.group(2)), m.group(3).strip()
        if what.startswith("frame"):
            v = _RATE_WORD.get(value)
            if v is not None:
                return Intent("animal_device", {"change": f"frame_rate:{v}"})
            if value in ("auto", "automatic"):
                return Intent("animal_device", {"change": "auto"})
        else:
            v = _SHARP_WORD.get(value)
            if v is not None:
                return Intent("animal_device", {"change": f"sharpness:{v}"})
        return Intent("animal_ask", {"about": "device"})
    # On and off, by name: the shared switches, the sun and moon, the weather.
    m = _ONOFF.fullmatch(s)
    if m:
        g = m.groups()
        if g[0] is not None:
            on, tail = g[0] == "on", g[1]
        elif g[2] is not None:
            on, tail = g[3] == "on", g[2]
        elif g[4] is not None:
            on, tail = g[4] == "enable", g[5]
        else:
            on, tail = False, g[7]
        got = _animal_target(tail)
        if got is not None:
            kind, key = got
            if kind == "switch":
                return Intent("animal_switch", {"key": key, "on": on})
            if kind == "sky":
                return Intent("animal_sky", {"on": on})
            if on:
                return Intent("animal_ask", {"about": "weather"})
            return Intent("animal_weather", {"source": "off"})
    m = _SHOWHIDE.fullmatch(s)
    if m:
        got = _animal_target(m.group(2))
        if got is not None and got[0] == "sky":
            return Intent("animal_sky", {"on": m.group(1) == "show"})
    return None


ANIMAL_QUESTIONS = {
    "animal": ("Which animal option do you mean? For example \"keep the animal still\", "
               "\"turn off the weather\" or \"make the animal sharper\"."),
    "weather": ("Where should the weather come from - your own Home Assistant, or Open-Meteo "
                "online (that one asks with an approval card first)?"),
    "device": ("Which one? Sharpness can be Lower, Balanced, High or Maximum; frame rate can be "
               "30, 60, 90, 120 or Max."),
}


SEARCH_MISSING = ("Your PC's Jarvis does not have web search yet - run apply-patches.ps1 "
                  "on the PC.")

#: "What can you do?" and close phrasings (jarvis_sayable.py, the ease-of-use
#: audit's "Things you can say", 2026-09-27). Whole sentences only: "what can
#: you do about the weather" goes to the model.
#:
#: "What are you CAPABLE of?" was the owner's own screenshot question
#: (2026-10-26) and the word "capable" appeared nowhere in this file, so the
#: sentence fell through to the model and could be answered differently each
#: time. It is the same question as "what can you do?", so it gets the same
#: fixed list, the same lane and no model.
_SAYABLE = re.compile(
    r"what\s+can\s+(?:you|i|jarvis)\s+(?:do|say|ask(?:\s+you)?|tell\s+you)(?:\s+here)?"
    r"|what\s+(?:should|do)\s+i\s+(?:say|ask|type)(?:\s+to\s+you)?"
    r"|what\s+(?:are|were)\s+(?:your|jarvis'?s?)\s+commands"
    r"|what\s+(?:are\s+you|is\s+jarvis)\s+capable\s+of"
    r"|what\s+are\s+(?:your|my|jarvis'?s?)\s+capabilities"
    r"|what\s+are\s+you\s+able\s+to\s+do"
    r"|what\s+(?:is|does)\s+jarvis\s+able\s+to\s+do"
    r"|(?:show|list|tell)\s+me\s+what\s+(?:i\s+can\s+say|you\s+can\s+do)"
    r"|help(?:\s+me)?")

#: "What can you reach?" and close phrasings (the Muse audit, 2026-09-25):
#: answered from jarvis_reach.py's list - the PC's settings, not the model.
#: Whole sentences only: "what can you reach on the top shelf" goes to the
#: model.
_WHO = r"(?:you|jarvis)"
_NOW = r"(?:\s+(?:right\s+)?now|\s+at\s+the\s+moment|\s+today|\s+on\s+this\s+pc)?"
_REACH = re.compile(
    r"(?:what|which\s+(?:things|services|accounts|apps|tools))\s+(?:can|could|do)\s+" + _WHO
    + r"\s+(?:reach|access|connect\s+to|get\s+(?:to|into)|reach\s+or\s+access"
    r"|access\s+or\s+reach|see\s+and\s+reach)" + _NOW
    + r"|what\s+(?:do|does)\s+" + _WHO + r"\s+have\s+access\s+to" + _NOW
    + r"|what\s+(?:have\s+you|has\s+jarvis)\s+got\s+access\s+to" + _NOW
    + r"|what\s+(?:are\s+you|is\s+jarvis)\s+(?:connected|hooked\s+up)\s+to" + _NOW
    + r"|what\s+(?:can|does)\s+" + _WHO + r"\s+(?:reach|access)\s+outside\s+(?:this\s+pc|"
    r"itself|yourself)"
    + r"|(?:show|list|tell)\s+(?:me\s+)?what\s+" + _WHO + r"\s+(?:can\s+(?:reach|access)|"
    r"(?:has|have)\s+access\s+to)" + _NOW
    + r"|(?:what\s+is\s+|what's\s+)?(?:everything\s+)?" + _WHO + r"(?:'s)?\s+access\s+list")

REACH_MISSING = ("Your PC's Jarvis cannot list what it can reach yet - run apply-patches.ps1 "
                 "on the PC.")

SAYABLE_MISSING = ("Your PC's Jarvis cannot list things you can say yet - run "
                   "apply-patches.ps1 on the PC.")

#: "Who are you?" and close phrasings (jarvis_identity.py, feasibility I131,
#: 2026-09-27): answered fixed, with no model, so the model never
#: improvises its own nature. Whole sentences only - "who are you calling"
#: goes to the model, like everything else here.
_WHO_ARE_YOU = re.compile(
    r"who\s+(?:are|r)\s+you"
    r"|what\s+are\s+you"
    r"|are\s+you\s+(?:an?\s+)?(?:ai|a\s+robot|human|a\s+real\s+person|real|conscious|sentient"
    r"|alive)"
    r"|are\s+you\s+(?:the\s+)?jarvis\s+from\s+iron\s+man"
    r"|are\s+you\s+j\.?\s*a\.?\s*r\.?\s*v\.?\s*i\.?\s*s\.?"
    r"|do\s+you\s+have\s+feelings"
    r"|do\s+you\s+(?:love|miss)\s+me"
    r"|are\s+you\s+(?:my\s+)?(?:girlfriend|boyfriend|(?:best\s+)?friend)"
    # normalise() reads a leading "will you" as a command lead-in (like
    # "will you set a timer"), so "will you be my friend" arrives here as
    # "be my friend" - matched directly rather than with "will you" still on.
    r"|be\s+my\s+friend"
    r"|are\s+you\s+lonely"
    r"|what\s+(?:model|ai|llm)\s+(?:are\s+you(?:\s+running)?|do\s+you\s+use|is\s+this)")

IDENTITY_MISSING = ("Your PC's Jarvis cannot answer that without apply-patches.ps1 - run it "
                    "on the PC.")

#: "Open a chat" and close phrasings (the floating face, 2026-09-27): the
#: desktop's small always-on-top window that shows only Jarvis's animated
#: face - no text box, voice only - and this is how it expands into the real
#: window. Answered here, with no model, for the same reason every other
#: fixed line in this file is: it must work even while the model is slow,
#: unloaded or asleep, which is exactly when a hands-free owner most wants
#: the real window to check on something. `X-Jarvis-Route`'s "quick" field
#: (route_fields, below) carries this intent's name to the desktop unchanged;
#: `jarvis-desktop/src-tauri/src/commands.rs`'s `stream_chat` is what acts on
#: it. Whole sentences only, like everywhere else here: "open a chat about
#: my day" goes to the model.
_OPEN_CHAT = re.compile(
    r"open\s+(?:a|the)\s+chat(?:\s+window)?"
    r"|show\s+me\s+(?:a|the)\s+chat(?:\s+window)?"
    r"|show\s+(?:the\s+)?chat(?:\s+window)?"
    r"|bring\s+up\s+(?:a|the)\s+chat(?:\s+window)?"
    r"|open\s+(?:the\s+)?jarvis\s+bar"
    r"|show\s+(?:me\s+)?(?:the\s+)?jarvis\s+bar"
    r"|bring\s+up\s+(?:the\s+)?jarvis\s+bar")

#: A whole message that is a DECISION word and nothing else - the owner
#: typed "approve" into the bar on 2026-10-11 and the app answered him with
#: silence. Whole sentences only, like every phrase here, and `.fullmatch`
#: is what guarantees it: "I approved the plans yesterday" is ordinary chat
#: and must stay that way.
#:
#: THIS NEVER APPROVES ANYTHING. Rule 4: cards are decided by tapping the
#: card's own button, and a risky one adds Windows Hello on this PC. The
#: `approval_where` reply below only says WHERE the control is, and carries
#: no id, no "approved", nothing a client could action.
_TYPED_DECISION = re.compile(
    r"approve(?:\s+it)?"
    r"|approve\s+it\s+please"
    r"|deny(?:\s+it)?"
    r"|reject(?:\s+it)?"
    r"|decline(?:\s+it)?"
    r"|yes"
    r"|no"
    r"|yes,?\s+please")


# --------------------------------------------------------------------------
#   "Is there an update?", "what changed?", "update Jarvis" (2026-10-26)
# --------------------------------------------------------------------------
#
# THE OWNER'S REQUEST: "can jarvis talk about an update if theres one
# availabale and the changes? and start the update process for me?" - "if i
# ask in chat".
#
# WHO KNOWS WHAT, AND WHY IT IS SPLIT THIS WAY. The thing that can install a
# desktop update is the Tauri shell (`update.rs`): it downloads the signed
# release, checks its signature and replaces its own executable, and it is the
# only party that knows which version is running. So the shell says so: every
# `/api/chat` body it builds carries a top-level `desktop` object
# (`{"version": "0.2.320", "can_update": true}`), added in Rust
# (`commands.rs` `chat_extras`, and `hud_proxy.rs`'s `chat_payload` drops
# anything a page tries to put there). This module reads it and answers from
# the PUBLIC release manifest the app's own updater reads - one HTTPS GET, no
# token, nothing about the owner in it - never from the model.
#
#   * no `desktop` facts  -> it cannot tell which build is asking, and says so;
#   * `can_update` false  -> this build cannot verify a download, and says so;
#   * the fetch failed    -> the CHECK failed, and says so;
#   * same version        -> the newest published, and says so;
#   * a newer version     -> the version, and what the release itself says
#                            changed (its own notes - never invented);
#   * this build newer    -> a development build, and says so.
#
# STARTING IT IS ONE CARD AND NOTHING ELSE. "Update Jarvis" raises ONE
# approval card (`desktop_update`) through `jarvis_gate.check` - the same gate
# every other change uses - and the card is in
# `jarvis_owner_check.PC_ONLY_ACTIONS`, so only this PC can approve it and
# Windows Hello comes first. NOTHING is downloaded before the yes: this module
# never fetches an installer and never runs one. The card's approval is what
# makes the DESKTOP shell run its own `update.rs` path (`commands.rs`
# `answer_approval` sees the approved card's action), so there is ONE installer
# and not a second one here. Before this feature the desktop updater was the
# one self-modification path outside the gate (the self-improvement audit's
# finding S3); a start from chat is now behind a card, while the Settings
# window's own Install and "update both halves" buttons still call `update_both`
# directly - S3 is improved for the new path, not closed for the old one.

#: The manifest the app's own updater reads (`tauri.conf.json`
#: `plugins.updater.endpoints`). `test_update_chat.py` holds the two equal.
UPDATE_MANIFEST_URL = (
    "https://github.com/darknight11ish/Epic-Jarvis/releases/download/"
    "desktop-latest/latest.json")

#: How long one manifest read may take, and how long its answer is reused.
#: Short and small on purpose: this runs while the owner waits for a chat
#: answer, and a release page that is slow is not worth a long hang.
_UPDATE_TIMEOUT = 6.0
_UPDATE_TTL = 120.0

#: The gate's action name for the update card. One name, used by this module,
#: the card words, `jarvis_owner_check.PC_ONLY_ACTIONS`, the framework's tier
#: table and the desktop's `update.rs` - all six must agree.
UPDATE_ACTION = "desktop_update"

#: The last manifest answer, so two questions in a row are one fetch. Guarded
#: by a lock because two chat turns can arrive together.
_UPDATE_LAST = {"at": 0.0, "data": None}
_UPDATE_LOCK = threading.Lock()

_UPDATE_ASK = re.compile(
    r"(?:is|are)\s+there\s+(?:any\s+|an?\s+)?(?:new\s+)?updates?"
    r"(?:\s+(?:available|out|yet))?(?:\s+(?:for|to|of)\s+jarvis)?"
    r"|(?:any|new)\s+updates?"
    r"|(?:is|are)\s+(?:the\s+)?jarvis(?:\s+app)?\s+up\s+to\s+date"
    r"|(?:do|does)\s+(?:i|jarvis)\s+need\s+(?:an?\s+)?update"
    r"|what(?:'s|s| is)\s+the\s+(?:latest|newest)\s+(?:version|release)"
    r"(?:\s+of\s+jarvis)?"
    r"|what\s+version\s+(?:of\s+jarvis\s+)?(?:am\s+i|is\s+jarvis)\s+(?:on|running)"
    r"|check\s+for\s+(?:an?\s+|any\s+)?(?:new\s+)?updates?"
    r"|have\s+i\s+got\s+the\s+latest\s+jarvis")

_UPDATE_NOTES = re.compile(
    r"what(?:'s|s| is)\s+new\s+in\s+(?:the\s+|this\s+)?(?:new\s+|latest\s+)?"
    r"(?:update|version|release)(?:\s+of\s+jarvis)?"
    r"|what\s+changed\s+in\s+(?:the\s+|this\s+)?(?:new\s+|latest\s+)?"
    r"(?:update|version|release)"
    r"|what\s+did\s+the\s+(?:update|new\s+version|release)\s+change"
    r"|what\s+does\s+the\s+(?:update|new\s+version|release)\s+(?:change|do|include)"
    r"|(?:the\s+|any\s+)?(?:update|release)\s+notes"
    r"|what(?:'s|s| is)\s+in\s+(?:the\s+|this\s+)?(?:new|latest)\s+"
    r"(?:update|version|release)")

_UPDATE_START = re.compile(
    # "update" and "upgrade" on their own: `normalise` takes a TRAILING "jarvis"
    # off as a vocative ("update, Jarvis"), so "update Jarvis" arrives here as
    # "update" - which is also what someone typing just "update" means.
    r"(?:update|upgrade)"
    r"|(?:update|upgrade)\s+yourself"
    r"(?:\s+(?:now|to\s+the\s+latest(?:\s+version)?))?"
    r"|(?:start|begin|run|do|install|apply)\s+(?:the\s+|this\s+|that\s+|its\s+)?"
    r"(?:jarvis\s+|desktop\s+)?update(?:\s+now)?"
    r"|install\s+(?:the\s+|this\s+|that\s+|a\s+)?(?:new\s+|latest\s+)?(?:update|version)"
    r"|update\s+now"
    r"|(?:update|upgrade)\s+to\s+(?:the\s+)?(?:latest|newest)\s+(?:version|release)"
    r"(?:\s+of\s+jarvis)?")


def _update(s: str) -> Optional[Intent]:
    """"is there an update?", "what changed in the update?", "update Jarvis".

    Exact, whole-sentence patterns like every other block here, and the
    near-misses are deliberate: "what's new" with no update/version/release in
    it, "how do I update Jarvis", "when is the next update", "did the update
    break anything" and "update my settings" all fall through to the model.
    """
    if _UPDATE_NOTES.fullmatch(s):
        return Intent("update_notes")
    if _UPDATE_START.fullmatch(s):
        return Intent("update_start")
    if _UPDATE_ASK.fullmatch(s):
        return Intent("update_ask")
    return None


def _version_parts(version) -> Optional[tuple]:
    """(0, 2, 320) for "0.2.320"; None for anything that is not a version.

    The release stamps `major.minor.<run number>` (`desktop-release.yml`), so
    numbers are compared as numbers and never as strings - "0.2.99" is older
    than "0.2.100", which a string comparison gets backwards.
    """
    text = str(version or "").strip().lstrip("vV")
    if not re.fullmatch(r"\d{1,9}(?:\.\d{1,9}){0,3}", text):
        return None
    parts = [int(p) for p in text.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def _desktop_build(desktop) -> Optional[dict]:
    """The `desktop` facts this request carried, or None when it carried none
    or carried nonsense. Anything unrecognised is "no facts": a client cannot
    talk this module into believing a version it did not send properly."""
    if not isinstance(desktop, dict):
        return None
    version = desktop.get("version")
    if not isinstance(version, str) or _version_parts(version) is None:
        return None
    return {"version": version.strip(),
            # Only a literal `true` is a yes. An older shell that omits the key
            # is "cannot update", which is the fail-safe direction: it never
            # leads to offering an install nobody can do.
            "can_update": desktop.get("can_update") is True}


def _release_manifest() -> tuple:
    """(manifest, None) or (None, why). One HTTPS GET of the public manifest.

    Standard library only, no token and no identifier: the same request the
    app's own updater makes. Cached for `_UPDATE_TTL`; a failure is not cached,
    so the next question tries again.
    """
    import urllib.request
    with _UPDATE_LOCK:
        cached = _UPDATE_LAST["data"]
        if cached is not None and (time.time() - _UPDATE_LAST["at"]) < _UPDATE_TTL:
            return dict(cached), None
    request = urllib.request.Request(
        UPDATE_MANIFEST_URL,
        headers={"User-Agent": "Jarvis-desktop-update-check/1",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=_UPDATE_TIMEOUT) as answer:
            raw = answer.read(256 * 1024)
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict) or _version_parts(data.get("version")) is None:
        return None, "the release page answered without a version in it"
    with _UPDATE_LOCK:
        _UPDATE_LAST["data"] = dict(data)
        _UPDATE_LAST["at"] = time.time()
    return dict(data), None


def _release_notes(manifest) -> str:
    """What the release itself says changed, trimmed for a chat answer.

    One string, exactly as published - never edited into claims of our own. An
    empty field means the release does not say, and the answer says that rather
    than inventing a list.
    """
    notes = manifest.get("notes")
    if not isinstance(notes, str):
        return ""
    text = notes.strip()
    if len(text) > 1500:
        text = text[:1500].rstrip() + " ... (the rest is on the release page)"
    return text


def _range_note(current: str, available: str) -> str:
    """The honest limit of a changelog: it covers ONE release.

    The app's version is `major.minor.<run number>` and a build can be several
    releases behind, but the manifest only ever describes the one being
    published. Saying so is the difference between "what changed" and "what
    changed in the newest release".
    """
    a, b = _version_parts(current), _version_parts(available)
    if not a or not b:
        return ""
    if b[2] - a[2] > 1:
        return (f" Those notes are for {available} only - they do not cover the "
                f"releases between {current} and it.")
    return ""


def _update_facts(desktop, fetch=None) -> tuple:
    """(state, facts) - the one place the check's outcome is decided.

    States, and each is a different honest sentence:
      "no-build"     no usable `desktop` facts (not the PC's own app);
      "cannot"       a build with no update key;
      "failed"       the release page could not be read - the CHECK failed;
      "newer-here"   this build is newer than the published one (development);
      "newest"       the published one is the running one;
      "available"    a newer published version, with its notes.
    """
    build = _desktop_build(desktop)
    if build is None:
        return "no-build", {}
    if not build["can_update"]:
        return "cannot", {"current": build["version"]}
    manifest, why = (fetch or _release_manifest)()
    if manifest is None:
        return "failed", {"why": why}
    current = build["version"]
    available = str(manifest.get("version") or "").strip()
    here, there = _version_parts(current), _version_parts(available)
    if there < here:
        return "newer-here", {"current": current, "available": available}
    if there == here:
        return "newest", {"current": current}
    return "available", {"current": current, "available": available,
                         "notes": _release_notes(manifest)}


def _update_words(kind: str, state: str, f: dict) -> Result:
    """What each state says. One place, so the question and the start's
    pre-flight cannot word the same fact two ways."""
    if state == "no-build":
        return Result(
            "I can only check that from the Jarvis app on this PC: it is the thing "
            "that knows which version is running, and this message did not say. "
            "Open Jarvis there, then Settings, then Updates, and press Check now. "
            "On the phone, Platform checks has its own update card.", kind)
    if state == "cannot":
        return Result(
            f"This build of Jarvis ({f['current']}) has no update key, so it "
            f"cannot check or install a download. Installing a signed release turns "
            f"updates on.", kind)
    if state == "failed":
        return Result(
            "I could not reach the release page, so the check failed and I cannot "
            f"say whether there is an update. Nothing was changed. ({f['why']})", kind)
    if state == "newer-here":
        return Result(
            f"This build is {f['current']}, and the newest published release is "
            f"{f['available']}. Yours is the newer one (a development build), so "
            f"there is nothing to install.", kind)
    if state == "newest":
        return Result(f"You are on {f['current']} - that is the newest published "
                      f"version.", kind)
    notes = f["notes"]
    if kind == "update_notes":
        if not notes:
            return Result(
                f"The release for {f['available']} does not say what changed, so I "
                f"will not make something up. The release page for {f['available']} "
                f"is on GitHub if you want to look.", kind)
        return Result(f"What changed in {f['available']}, from its own release "
                      f"notes: {notes}{_range_note(f['current'], f['available'])}",
                      kind)
    return Result(
        f"Version {f['available']} is available. You are on {f['current']}. "
        f"Say \"what changed in the update\" to hear what is in it, or "
        f"\"update Jarvis\" to start it - nothing installs on its own.", kind)


def _update_answer(kind: str, desktop, fetch=None) -> Result:
    """The check's own answer. `kind` is "update_ask" or "update_notes"."""
    state, f = _update_facts(desktop, fetch=fetch)
    return _update_words(kind, state, f)


def _update_tier(action: str) -> str:
    """The tier `What asks first` has for the card, read before it is raised.

    An unreadable framework answers "ask" - the same default
    `jarvis_tool_updates` uses, and the safe direction: it never turns a card
    into an automatic action.
    """
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception:
        return "ask"


def _gate_module():
    """The ONE lazy import of `jarvis_gate` in this file.

    `test_ask_to_change.py` requires exactly one gate import in this module, so
    the change lane cannot grow a second gate door. The update card's own gate
    and the note-capture taint read both reach the gate through this accessor;
    a second `import jarvis_gate` anywhere fails that guard (2026-10-31: the
    integration tree's CI found two imports, at the update gate and the note
    gate).
    """
    import jarvis_gate
    return jarvis_gate


def _update_gate(action: str, detail: dict, prompt: str):
    """`jarvis_gate.check` - the one gate every card goes through."""
    return _gate_module().check(action, detail, prompt=prompt)


def _update_spawn(fn) -> None:
    threading.Thread(target=fn, name="jarvis-update-card", daemon=True).start()


def _update_card_thread(detail: dict, prompt: str, gate=None) -> None:
    """Wait for the owner's answer, and nothing else.

    A yes is what makes the DESKTOP shell run its own update (`commands.rs`
    `answer_approval` sees this card's action and calls `update.rs`); this
    thread must never download, install or start anything itself, and a denied,
    timed-out or refused card simply ends here with nothing changed. The gate
    records the card and its decision in the approvals store, which is the
    audit line the desktop updater did not have before (S3).
    """
    gate = gate or _update_gate
    try:
        gate(UPDATE_ACTION, detail, prompt)
    except Exception:
        return


def _run_update(intent: Intent, desktop) -> Result:
    return _update_answer(intent.name, desktop)


def _run_update_start(desktop, *, fetch=None, tier_of=None, spawn=None) -> Result:
    """One card, or a plain reason there is nothing to card about.

    Every refusal here changes nothing and says so. Nothing is downloaded before
    the owner's yes, and the only thing this does after the yes is let the
    desktop shell run the updater it already has.
    """
    kind = "update_start"
    state, f = _update_facts(desktop, fetch=fetch)
    # The check's own answer for every state but one: no facts, no update key, a
    # failed check, nothing newer, a development build. A card for any of those
    # would promise an install that cannot happen.
    if state != "available":
        return _update_words(kind, state, f)
    tier_of = tier_of or _update_tier
    tier = tier_of(UPDATE_ACTION)
    if tier != "ask":
        return Result(
            f"An update needs a person to say yes, and updates are set to {tier!r} "
            f"in What asks first, so I did not raise a card. Nothing was changed.",
            kind)
    available = f["available"]
    detail = {
        "text": (f"Update Jarvis on this PC: backend first, then Jarvis Desktop "
                 f"{available}, then the app restarts."),
        "what": ("patch the Python backend, then install the signed Jarvis Desktop "
                 "release, then restart the app"),
        # The download comes from GitHub, so this card does leave this PC - the
        # same one GET the app's own check already makes.
        "leaves_this_pc": True,
    }
    prompt = (
        f"Jarvis wants to update itself on this PC. It patches the Python backend "
        f"first (every patch, then its own test suites - this can take several "
        f"minutes), then downloads Jarvis Desktop {available} and checks its "
        f"signature, then the app restarts. Pace: Balanced. Nothing is downloaded, "
        f"installed or changed before you approve this card. If a newer release is "
        f"published before you approve, it installs that newest one instead. If the "
        f"backend folder cannot be found, nothing is changed and neither half runs. "
        f"This card can only be approved on this PC.")
    try:
        (spawn or _update_spawn)(lambda: _update_card_thread(detail, prompt))
    except Exception:
        return Result("I could not raise the approval card, so nothing was changed.",
                      kind)
    return Result(
        f"One card is waiting for your yes. Approving it patches the backend first, "
        f"then installs Jarvis Desktop {available}, then restarts the app. Nothing "
        f"has been downloaded or changed yet, and nothing will be unless you "
        f"approve it - on this PC.", kind)


# --------------------------------------------------------------------------
#   Connecting a calendar (2026-10-28, the owner's HUD screenshot)
# --------------------------------------------------------------------------
#
# WHY THIS IS HERE. The owner asked, in the HUD chat on 2026-10-28:
#
#     "can you connect directly to external calendars like google or outlook?"
#
# and Jarvis answered that it "cannot connect ... without you manually granting
# permissions and setting up a bridge", then offered to explain exporting the
# calendar to an ICS file. That is false about this PC, and it is false in the
# direction that costs the owner a feature: `jarvis_calendar.py` already reads
# Google Calendar through its **private iCal link** and any CalDAV calendar,
# read-only, with **no OAuth and no bridge** (its own docstring, `:1-34`), the
# link is typed in Settings, Accounts and kept in Windows Credential Manager
# (`:81-93`), and the model is offered a `calendar_read` tool
# (`jarvis_agent.py:2315-2323`). Measured with this module's own `match()`: 16
# of 16 owner-style sentences - including "connect my calendar", "set up my
# calendar", "add my google calendar", "link my outlook calendar" and
# "set up a calendar bridge for me" - returned None, so the 8B model answered,
# and its system prompt (`jarvis_agent.py:7263-7281`) says nothing about a
# calendar at all. The fix is this answer, not a new capability.
#
# THE WORDS ARE HELD TO THE REAL ONES. `test_calendar_answer.py` checks every
# step below against the Accounts card's own label and help line
# (`jarvis-desktop/src/account-secrets.js`), the `account-secrets` section id in
# `jarvis_settings_registry.SECTIONS`, the Credential Manager target
# (`jarvis_calendar.ICS_URL_TARGET`), the reading-tool switch's own grammar
# (`_TOOL_ON`, below) and the shipped `[tools].enabled` list - so a moved box, a
# renamed label or a loosened tier fails a suite instead of leaving a wrong
# answer on screen.
#
# NOTHING IS CONNECTED BY SAYING THIS: the private link is a secret, typed on the
# PC only (rule 3), so the answer can only say where - it never claims a
# connection was made, and no card is raised here.

#: A question lead and the polite lead-ins `normalise` does not take off. "can
#: you ..." is already gone by the time this runs; allowed again here so the
#: grammar does not depend on that.
_CAL_LEAD = (r"(?:(?:how\s+(?:do|can|could|would)\s+i"
             r"|what\s+(?:do\s+i\s+need|would\s+it\s+take)\s+to"
             r"|i(?:'d\s+(?:like|love)|\s+want|\s+need)\s+to"
             r"|help\s+me)\s+)?")

#: The verbs that mean "set it up". Deliberately NOT "open" (`jarvis_open.py`
#: owns "open my calendar") and not "read"/"show": a plain "what's on my
#: calendar today" still goes to the model, exactly as before.
_CAL_VERB = (r"(?:set\s+up|connect(?:\s+(?:up\s+)?to|\s+with)?|link(?:\s+up)?|add|"
             r"hook\s+up|sync|integrate|attach|enable|configure|import|"
             r"give\s+(?:jarvis|you)\s+access\s+to)")

#: What the owner calls the thing. "a calendar bridge" is his own phrase and is
#: answered, not echoed: there is no bridge (see the words below).
_CAL_THING = (r"(?:(?:(?:a|an|my|the|our|your)\s+)?"
              r"(?:(?:google|outlook|apple|icloud|office\s*365|work|external)\s+)?"
              r"calendars?"
              r"|(?:an?\s+|my\s+|the\s+)?(?:ics|ical)(?:\s+file)?"
              r"|(?:(?:a|an|my|the|our|your)\s+)?calendar\s+"
              r"(?:bridge|connection|integration|link|setup))")

#: "like google or outlook" - the owner's own examples, so the sentence he
#: actually typed is answered instead of reaching the model.
_CAL_LIKE = (r"(?:\s*,?\s*like\s+(?:google|outlook)(?:\s+or\s+(?:google|outlook))?)?")

#: "... for me", "... in Jarvis", "... on this PC" - the polite end that does not
#: change what is being asked. The dangling prepositions are here because
#: `normalise` strips a trailing "jarvis" (`_TAIL`): "hook up my calendar to
#: jarvis" arrives as "hook up my calendar to", and it is still his sentence.
_CAL_TAIL = (r"(?:\s+(?:for\s+me|please|to\s+jarvis|with\s+jarvis|in\s+jarvis|"
             r"into\s+jarvis|to\s+(?:my\s+|the\s+)?jarvis|on\s+this\s+pc|up|"
             r"to|with|into|in|for))*")

#: Whole sentences only: a sentence with one more condition ("... tomorrow at
#: 5", "... on my phone") keeps its own answer or goes to the model untouched.
_CALENDAR_CONNECT = re.compile(
    _CAL_LEAD + _CAL_VERB + r"(?:\s+(?:directly|already|now))?\s+"
    r"(?:(?:to|with)\s+)?" + _CAL_THING + _CAL_LIKE + _CAL_TAIL)

#: "calendar setup" / "calendar connection" on its own, with no verb.
_CALENDAR_NOUN = re.compile(r"(?:the\s+|my\s+)?calendar\s+"
                            r"(?:setup|connection|bridge|integration)")

#: "is my calendar connected?" - the state question, with no verb to set it up.
_CALENDAR_STATE = re.compile(
    r"(?:is|has)\s+(?:my\s+|the\s+|your\s+)?calendar\s+"
    r"(?:connected|set\s+up|linked|configured|working|readable)")

#: The answer for a calendar that is NOT set up - every step a real one: the
#: Google path is the Accounts card's own help line, the box's label is that
#: card's label, and the reading-tool sentence is this module's own `_TOOL_ON`
#: grammar. `{tool}` is the reading-tool sentence, or "" when the tool is
#: already offered (so the answer never asks for a switch that is already on).
#:
#: THE FIRST SENTENCE IS THE 2026-10-28 MERGE'S, and it has to be true of the
#: MERGED tree: `jarvis_google_calendar.py` (merged the same day) really does
#: add a Google sign-in, so "no Google sign-in" - true when this answer was
#: written - would be false now. It names the read-only way this answer walks
#: the owner through, and says the sign-in way exists without pretending the
#: Settings window has a row for it yet (its one-time setup is a command).
CALENDAR_SETUP_WORDS = (
    "There is no bridge to set up: Jarvis reads a calendar itself, read-only, "
    "on this PC. (New on 2026-10-28: a real Google sign-in exists beside it - "
    "read/write, one card per change - and its one-time setup is a command in "
    "the backend folder, in docs/GOOGLE-CALENDAR-SETUP.md.) "
    "1. In Google Calendar on a computer: the gear, Settings, your calendar, "
    "Integrate calendar, then copy the Secret address in iCal format. "
    "2. Paste it into Jarvis: Settings, Accounts, the Calendar iCal link box. "
    "I cannot take that link here - it is handled like a password, so it is "
    "typed on the PC only. Any calendar that gives you a private .ics address "
    "works the same way.{tool} Then ask me what is on this week, or say "
    "\"brief me every weekday at 7\".")

#: The reading-tool half, said only when the tool really is not offered to the
#: model (the shipped `[tools].enabled` list does not include it).
CALENDAR_TOOL_STEP = (" If you also want me to read it when you ask, say \"let the "
                      "AI model read my calendar\" - that raises one card.")

#: The answer for a calendar that IS set up. `{named}` is the reader's own name
#: for it ("your Google Calendar (private link)") and never the link itself.
#: The `{tool}` sentence comes BEFORE the "ask" sentence: while the reading tool
#: is not offered, asking would reach a model that cannot read it.
CALENDAR_READY_WORDS = (
    "This PC is already set up to read {named}.{tool} Then ask \"what's on my "
    "calendar this week?\" - one request, read-only, nothing else sent. To "
    "change it, Settings, Accounts on this PC.")

CALENDAR_TOOL_OFF = (
    " One thing is still off: the AI model is not offered the calendar tool, so "
    "say \"let the AI model read my calendar\" (one card) first. The morning "
    "briefing reads it without that.")

#: A CalDAV address is saved but no CalDAV username is - most servers refuse.
CALENDAR_CALDAV_NO_USER = (
    " The CalDAV address is saved but no CalDAV username is set, so most "
    "servers will refuse the read; the private iCal link needs no username.")

CALENDAR_MISSING = ("Your PC's Jarvis does not have the calendar module yet - run "
                    "apply-patches.ps1 on the PC, then ask again.")


def _calendar_tool_words() -> str:
    """The reading-tool sentence, or "" when it is already offered (or cannot be
    read - an unreadable settings file must not become a claim either way)."""
    try:
        import jarvis_asks_first as AF
        offered = AF.real_tool("calendar_read") in AF.tools_enabled_set()
    except Exception:
        return ""
    return "" if offered else CALENDAR_TOOL_OFF


def _calendar_setup(s: str) -> Optional[Intent]:
    """"connect my google calendar", "set up a calendar bridge for me" (the
    owner's screenshot, 2026-10-28). A read-only answer built from this PC's own
    state - no card, no connection, no login."""
    if (_CALENDAR_CONNECT.fullmatch(s) or _CALENDAR_NOUN.fullmatch(s)
            or _CALENDAR_STATE.fullmatch(s)):
        return Intent("calendar_setup")
    return None


def _run_calendar_setup(intent: Intent) -> Result:
    """"Can you connect to my calendar?", "set up a calendar bridge for me"
    (2026-10-28). Reads the reader's own state and answers with the real steps;
    when the calendar is not set up it also carries `open_settings`, so the
    desktop's Settings window jumps to the Accounts card itself - the same
    cardless jump "open accounts" makes, and like that one it changes nothing."""
    n = intent.name
    try:
        import jarvis_calendar as CAL
    except Exception:
        return Result(CALENDAR_MISSING, n)
    source = CAL.source()
    if source:
        named = (CAL.source_words() if source == "ics"
                 else "your calendar over CalDAV")
        words = CALENDAR_READY_WORDS.format(named=named, tool=_calendar_tool_words())
        if source == "caldav" and not CAL.authenticated():
            words += CALENDAR_CALDAV_NO_USER
        return Result(words, n)
    tool = CALENDAR_TOOL_STEP if _calendar_tool_words() else ""
    return Result(CALENDAR_SETUP_WORDS.format(tool=tool), n,
                  open_settings="account-secrets")


# --------------------------------------------------------------------------
#   A Notion export into Obsidian (2026-10-28)
# --------------------------------------------------------------------------
#
# WHY THIS IS HERE. The owner asked, on 2026-10-27 at 20:57:32, "can you
# process all of my notion notes into obsidian?" - and the model answered
# "I cannot directly access or process files from Notion to transfer them to
# Obsidian without explicit file paths or content provided here." The PC has
# two real things for that request (jarvis_documents.import_notion, and
# jarvis_notion_obsidian's /api/notion/import), but the model can drive neither:
# it is offered no Notion tool, and the guide it can ask mentions the folder
# import only inside the `folders` row (asking for "notion export" answers that
# it does not have that feature) and has no row for the converter - so the one
# honest thing a machine here can do is answer with the steps, the limits, and
# which half of it has no button yet.
#
# THE WORDS ARE HELD TO THE REAL ONES. `test_notion_answer.py` checks every
# step below against `jarvis_documents.NOTION_DETAIL` and `NOTION_TITLE`,
# against `jarvis_notion_obsidian.PATHS` and its gate action, and against the
# shipped `jarvis-framework.toml`'s `import_notion_export = "ask"` tier - so a
# reworded export step, a moved route or a loosened tier fails a suite instead
# of quietly leaving a wrong answer in place. It also drives the folder import
# end to end on a real zip in a temp folder, because "I unpack it into a NEW
# folder" is a promise and not a sentence.
#
# NOTHING IS DONE BY SAYING THIS: the .zip is chosen with this PC's own file
# picker (folders.rs `import_notion`, PC only), so the answer can only say
# where - never claim the import happened.

#: What the owner calls the thing Notion holds.
_NOTION_THING = (r"(?:notes?|pages?|files?|documents?|content|everything|workspace|"
                 r"export|library|stuff|data)")

#: The verbs that mean "bring it across". Deliberately NOT "open", so "open
#: Notion" keeps opening the app (jarvis_open.py) and is never answered here.
_NOTION_MOVE = (r"(?:process|import|convert|move|transfer|copy|migrate|bring|pull|load|"
                r"put|export|sync|take)")

#: A question lead and the polite lead-ins `normalise` does not take off.
#: "can you ..." is already gone by the time this runs; allowed again here so
#: the grammar does not depend on that. "i'd like to" keeps its own apostrophe
#: form: `normalise` leaves it alone, so there is no space after the "i".
_NOTION_LEAD = (r"(?:(?:how\s+(?:do|can|could|would)\s+i"
                r"|what(?:'s|\s+is)\s+the\s+best\s+way\s+to"
                r"|what\s+(?:do\s+i\s+need|would\s+it\s+take)\s+to"
                r"|i(?:'d\s+(?:like|love)|\s+want|\s+need)\s+to)\s+)?"
                r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?(?:help\s+me\s+)?")

#: "... notion notes (over) to obsidian", and the other order,
#: "... everything from notion into obsidian". Whole-sentence, so a sentence
#: with one more condition ("... tomorrow at 5") stays the model's.
_NOTION_TO_OBSIDIAN = re.compile(
    _NOTION_LEAD + _NOTION_MOVE + r"\s+"
    r"(?:"
    r"(?:(?:all|every\s+one)\s+(?:of\s+)?)?(?:(?:my|the|your|our)\s+)?notion"
    r"(?:\s+" + _NOTION_THING + r")?"
    r"|"
    r"(?:(?:all|every\s+one)\s+(?:of\s+)?)?(?:(?:my|the|your|our)\s+)?"
    + _NOTION_THING + r"\s+from\s+notion"
    r")"
    r"\s+(?:(?:over|across|back)\s+)?(?:in)?to\s+obsidian")

#: "import my Notion export" on its own - the follow-up that used to get the
#: same "I cannot access Notion" answer.
_NOTION_JUST_IMPORT = re.compile(
    _NOTION_LEAD + r"(?:import|bring\s+in|load|restore)\s+"
    r"(?:(?:the|my|our)\s+)?notion\s+export")

#: The answer to "can you process all of my Notion notes into Obsidian?".
#: Every step is one this PC really has: the export is Notion's own; the
#: import unpacks into a NEW folder in a listed folder (PC only, no card);
#: and the vault converter is `/api/notion/import` - PC only, ONE card, and
#: no button in either app yet, which is why the sentence says so instead of
#: promising it. No Notion login, no sync, no edit on Notion's side.
NOTION_WORDS = (
    "I cannot log into Notion, but I do have a Notion import. In Notion: Settings, "
    "Export all workspace content, as Markdown & CSV, then save the .zip. On this PC: "
    "Settings, Folders Jarvis may look in, then under Bring in a Notion export pick a "
    "folder from the list and press Choose the .zip… - I unpack it into a NEW folder "
    "there that I can read and search, and nothing in Notion is changed. The full "
    "Notion-to-Obsidian-vault converter is built (POST /api/notion/import, PC only, "
    "one card) but no app has a button for it yet.")

#: The same steps for "import my Notion export" on its own: the .zip is picked
#: with this PC's own file picker, so the one honest thing to say is where.
NOTION_PICK_WORDS = (
    "Picking the .zip needs this PC's own file picker, so it is two taps there: "
    "Settings, Folders Jarvis may look in, then under Bring in a Notion export pick a "
    "folder from the list and press Choose the .zip… - I unpack it into a NEW folder "
    "in that folder and change nothing in Notion.")


def _notion(s: str) -> Optional[Intent]:
    """"process all my notion notes into obsidian", "convert my Notion pages to
    Obsidian", "copy everything from Notion into Obsidian", "import my Notion
    export" (the owner's screenshot, 2026-10-27 205732). Both forms are read-
    only answers - no card, no import, no Notion login."""
    if _NOTION_TO_OBSIDIAN.fullmatch(s):
        return Intent("notion_export")
    if _NOTION_JUST_IMPORT.fullmatch(s):
        return Intent("notion_export", {"step": "import"})
    return None


# --- "connect my calendar", "set up github" (2026-10-28) ---------------------
#
# WHAT THIS IS FOR. The owner asked, on 2026-10-28: "it should be able to
# connect all features just through me talking to jarvis", with a pop-up for a
# password. The HUD answered his "can you connect directly to external
# calendars like google or outlook?" with "jarvis cannot connect directly to
# external calendars ... Would you like instructions on exporting your calendar
# to ICS?" - false about Jarvis (it reads CalDAV and a private iCal link today)
# and useless to him. The storage and the card both existed; nothing joined
# them, and the model held no setup tool, so it filled the gap with a generic
# limitation. This is the same fix as the Notion answer above: a deterministic
# path with the real steps, so the model is never the one answering.
#
# WHAT IT DOES. It raises ONE card (jarvis_connect_account.raise_card) whose
# boxes are typed on this PC and saved straight into Windows Credential
# Manager, then tested with one real request. NO value is ever in this
# sentence, in the chat, in the model's context or in a log: the card is the
# only place a value is ever typed, and the page posts it to a host-only route.
# Nothing is saved until the owner presses Save on that card, and the answer
# says so - a spoken "yes" approves nothing, as everywhere else.
#
# WHERE IT SITS. Before `_settings_only` below, deliberately: that matcher
# answers "set my github token" with the 2026-10-22 Settings-only sentence
# ("Accounts and API keys are never typed or spoken"), and the owner's ask of
# 2026-10-28 supersedes it for exactly these services - the card types them on
# the PC, which is the same act as Settings, not a second one. Every other
# account noun it does not know still gets that sentence, unchanged. After
# every real action matcher, so "remind me to connect my calendar" stays a
# reminder.
#
# "Is my calendar connected?" is answered from the store and from the service's
# own test (jarvis_connect_account.status_words) - never from a guess, and
# "not connected yet" when nothing is saved.

_CONNECT_START = re.compile(
    r"^(?:how\s+(?:do|can|could|would)\s+i\s+(?:please\s+)?"
    r"|(?:do|does|will|would)\s+(?:you|jarvis)\s+(?:please\s+)?"
    r"|i\s+(?:want|need|would\s+like)\s+(?:you\s+)?to\s+(?:please\s+)?"
    r"|let\s+you\s+)?"
    r"(?P<verb>connect|set|set\s*up|setup|link|hook\s+up|integrate|configure|add|enable|"
    r"sign\s+in\s+to|log\s+in\s+to)\b")

#: "is my calendar connected?", "do you have github set up?", "is github
#: linked?" - a QUESTION about state, answered from the store and one test. It
#: changes nothing, so it is in READ_ONLY_INTENTS.
_CONNECT_STATUS = re.compile(
    r"^(?:is|are|do|does|did|have|has|can)\b.{0,70}\b"
    r"(?:connected|linked|set\s*up|working|hooked\s+up|signed\s+in|logged\s+in)\b"
    r"|\bis\s+(?:my|the)\s+.{0,40}\b(?:connected|linked|set\s*up|working)\b")

#: Nouns that name an account this file CANNOT connect yet (Phase 1 is the
#: calendar and GitHub). A sentence that names one is answered honestly rather
#: than handed to the model, which would invent a way. Kept to the inventory in
#: the 2026-10-28 audit, section 2 - not a general word list.
#:
#: `phone` and `pairing` were in this list and are NOT any more (security review
#: S6, 2026-10-28): they made "is my phone connected?" reach the connect path,
#: whose honest-account answer never mentions the phone - a true sentence about
#: the wrong thing, and "not in this list" is better than a wrong answer. The
#: phone's own pairing state has its own answer elsewhere; this card is not it.
_CONNECT_LATER = re.compile(
    r"\b(?:e-?mail|imap|smtp|inbox|notion|obsidian|logseq|joplin|home\s+assistant|"
    r"web\s+search|exa|tavily|brave|openai|mistral|xai|openrouter|groq|"
    r"big\s+model|chatbot|spotify|dropbox|google\s+drive)\b")

#: A THING ON a calendar, not the calendar itself (2026-10-28, the integration
#: merge of the three calendar branches). The verb "add" is a connecting one
#: only when what follows is the calendar or the account: "add my google
#: calendar" raises the connect card, but "add a calendar event at 5pm" is a
#: sentence for `jarvis_google_calendar.answer()` (it proposes the event and
#: says one card is needed), and raising the connect card for it would hand the
#: owner the wrong card. This is the same shape as the reminder guard below,
#: and it is why one sentence has one owner: the card owns connecting, the
#: Google answer owns reading and changing events.
_CONNECT_EVENT = re.compile(
    r"\b(?:meetings?|events?|appointments?|calls?|lunch|dinners?|breakfasts?|"
    r"part(?:y|ies)|flights?|trains?|birthdays?|weddings?|concerts?|"
    r"interviews?|classes|lessons?)\b")


def _connect(s: str) -> Optional[Intent]:
    """"connect my calendar", "set up github", "is my calendar connected?".

    Whole-sentence in the sense that matters: the verb has to START the
    sentence (or follow one of the ask lead-ins in `_CONNECT_START`), a service
    from `jarvis_connect_account.SERVICES` has to be named, and the sentence
    has to be short. Anything this file cannot verify - email, Notion, the
    other accounts - is answered with what CAN be connected rather than a card
    for something there is no test for."""
    words = s.split()
    if len(words) > 16:
        return None
    # NOT a sentence about a reminder, an alarm or a watch: "set a reminder for
    # my calendar" names a calendar and must never raise a connect card. The
    # real timer matchers run before this one, but a sentence of theirs that
    # they cannot parse (no time in it) would otherwise land here.
    if re.search(r"\b(?:remind|reminder|reminders|alarm|alarms|timer|timers|watch|"
                 r"watching|notify|notification|todo|to-do)\b", s):
        return None
    # NOT the connect card when the sentence names a THING ON the calendar
    # ("add a calendar event at 5pm", "add a meeting to my calendar tomorrow"):
    # that is `jarvis_google_calendar.answer()`'s sentence, and its own answer
    # is the proposal plus the one card the write needs (2026-10-28).
    if _CONNECT_EVENT.search(s):
        return None
    if _CONNECT_STATUS.match(s):
        try:
            import jarvis_connect_account as C
        except Exception:                   # noqa: BLE001 - module absent
            return None
        sid = C.service_from_words(s)
        if sid:
            return Intent("connect_account", {"ask": "status", "service": sid})
        if _CONNECT_LATER.search(s):
            return Intent("connect_account", {"ask": "later"})
        return None
    start = _CONNECT_START.match(s)
    if not start:
        return None
    try:
        import jarvis_connect_account as C
    except Exception:                       # noqa: BLE001 - module absent
        return None
    sid = C.service_from_words(s)
    if sid:
        return Intent("connect_account", {"ask": "card", "service": sid})
    if _CONNECT_LATER.search(s):
        # A BARE "set" ONLY WITH A SERVICE IT KNOWS (2026-10-28). "set my github
        # token" raises the card; "set web search to off" is a SETTING and must
        # keep its own lane, so a sentence with no known service is only read as
        # a connect ask when the verb itself is a connecting one.
        if start.group("verb") == "set":
            return None
        return Intent("connect_account", {"ask": "later"})
    return None


def _run_connect(f: dict) -> Result:
    """"connect my calendar" / "set up github" / "is my calendar connected?".

    Raises ONE card and says where it is; or answers a state question from the
    store and one real test; or names what CAN be connected when the sentence
    asked for an account this file cannot test yet. Nothing here types a value
    and nothing here saves one."""
    try:
        import jarvis_connect_account as C
    except Exception:                       # noqa: BLE001 - module absent
        return Result(CONNECT_MISSING, "connect_account")
    ask = str(f.get("ask") or "")
    sid = str(f.get("service") or "")
    if ask == "later" or not sid:
        return Result(
            "I can connect two things by talking today: a calendar (the private iCal "
            "link, or a CalDAV server's username and password) and GitHub. The rest - "
            "email, Notion, Obsidian, the search and chatbot keys, Home Assistant - "
            "still need Settings, Accounts on the PC, because none of them has a test "
            "I can run to prove it works. A password or a token is never typed into "
            "the chat, there or anywhere else.",
            "connect_account")
    if ask == "status":
        said = C.status_words(sid)
        # "Not connected yet" must lead somewhere. `_run_calendar_setup` (main,
        # #960) answers the same state with `open_settings="account-secrets"`,
        # so the desktop jumps its Settings window to the Accounts card without
        # changing anything; this answer keeps that jump rather than sending the
        # owner to find the page himself (security review S5, 2026-10-28). An
        # answer that says connected, or saved-but-failing, opens nothing: there
        # is no box for the owner to go and fix.
        if "not connected yet" in said:
            return Result(said, "connect_account", open_settings="account-secrets")
        return Result(said, "connect_account")
    try:
        card = C.raise_card(sid, "")
    except C.ConnectAccountError as exc:
        return Result(str(exc), "connect_account")
    svc = C.SERVICES[sid]
    boxes = " and ".join(f.label for f in svc.fields)
    return Result(
        f"{svc.name}. One card is waiting in the HUD window on this PC: type the "
        f"{boxes} there and press Save. " + CONNECT_SAFE_NOTE + " Then I run one real "
        "test and tell you exactly what it proved.",
        "connect_account")


#: Said by every connect answer. The card is the only place a value is typed,
#: and the page posts it to a route only this PC may call.
CONNECT_SAFE_NOTE = ("I cannot take it here - a password, a token or a private link is "
                     "never typed into the chat, so it goes straight from that card into "
                     "Windows Credential Manager.")

#: The connect card's own module is not on this PC.
CONNECT_MISSING = ("I cannot raise the connect card on this PC: jarvis_connect_account.py "
                   "is not in the backend folder. Run apply-patches.ps1 again, or use "
                   "Settings, Accounts.")


# --- "can you connect my calendar and email?", "what about connecting to a
# gmail account or google calendar?" (2026-10-29, the HUD field test) ---------
#
# WHAT WENT WRONG. The field test of 2026-10-29 asked whether Jarvis could
# connect the owner's calendar and email, and "what about connecting to a gmail
# account or google calendar?". The first got the private-iCal card with the
# email half silently dropped; the second matched nothing at all and reached the
# 8B model, which answered that connecting Google Calendar "requires a refresh
# token ... tokens are managed in your browser's signed-in account; I cannot
# retrieve them from here ... generate an OAuth token, then share the resulting
# code with me". Every part of that is wrong about this PC, and the last part is
# dangerous: it invites a secret into a chat transcript. The two-way Google
# setup already exists - a one-time Google Cloud setup, then three commands on
# this PC (`jarvis_google_calendar.py`), with the sign-in coming back to a
# loopback listener on this PC, so no token or code is ever pasted anywhere.
# That is documented in `docs/GOOGLE-CALENDAR-SETUP.md`.
#
# SO THESE SENTENCES ARE ANSWERED HERE, from fixed copy and this PC's own
# modules, and the model is never the one answering. The four real paths below
# are the whole honest inventory (2026-10-29):
#   (a) calendar, read/write - the Google two-way setup: the CLI steps in
#       `docs/GOOGLE-CALENDAR-SETUP.md`, run on this PC, never in chat;
#   (b) calendar, read-only - the private iCal link, typed on the secure
#       connect card this PC raises ("connect my calendar");
#   (c) GitHub - the same kind of secure card ("connect GitHub");
#   (d) email - NOT built: no connect card, and its IMAP details are typed in
#       Settings, Accounts on this PC.
#
# NOTHING HERE TYPES A VALUE, raises a card or changes anything: the answer is
# read-only (READ_ONLY_INTENTS) and only navigates Settings, Accounts.

#: The three commands the Google two-way setup really is, exactly as
#: `jarvis_google_calendar.connect_sentence()` and docs/GOOGLE-CALENDAR-SETUP.md
#: print them. `test_hud_fieldtest_answers.py` holds all three against that doc,
#: so a reworded command in one place cannot leave a wrong answer here.
GOOGLE_SETUP_COMMANDS = (
    "py -3 jarvis_google_calendar.py client <client-id>",
    "py -3 jarvis_google_calendar.py mode google",
    "py -3 jarvis_google_calendar.py connect",
)

#: The doc those steps live in. Read from `jarvis_google_calendar` when it is
#: there (its own SETUP_DOC), else this literal - the same file either way.
GOOGLE_SETUP_DOC_FALLBACK = "docs/GOOGLE-CALENDAR-SETUP.md"

#: The four real paths, in the owner's own order. `{cmds}`, `{doc}` and
#: `{lead}` are filled by `_run_accounts_connect`; every other word is fixed.
ACCOUNTS_PATHS_WORDS = (
    "{lead}Nothing on this PC asks you to paste a token, an auth code or a password into "
    "this chat, and I cannot read your browser's own Google session. The four real paths:\n"
    "1. Google Calendar, read and write - a one-time setup in your own Google account, then "
    "three lines in the backend folder on this PC: {cmds}. The sign-in comes back to this "
    "PC's own loopback address, so no code is pasted anywhere. Steps: {doc}.\n"
    "2. Google Calendar, quick read-only - the private iCal link. Say \"connect my calendar\" "
    "and one secure card appears on this PC for it.\n"
    "3. GitHub - the same kind of secure card: say \"connect GitHub\".\n"
    "4. Email - not built yet: there is no connect card for it, and its IMAP details (mail "
    "server, username, password) are typed in Settings, Accounts on this PC."
)

#: The first sentence, from the calendar's own chosen way - so an owner who
#: already set it up is told so, and one who has not is not told he has.
ACCOUNTS_LEAD_ON = "Your calendar is already connected the Google read/write way on this PC.\n"
ACCOUNTS_LEAD_ICAL = "Your calendar is already connected read-only (the private iCal link).\n"
ACCOUNTS_LEAD_OFF = "Your calendar is not connected on this PC yet.\n"

#: "connect ..." / "set up ...", with the same ask lead-ins `_CONNECT_START`
#: accepts, plus the "what about connecting ..." shape the owner actually used.
_ACCOUNTS_VERB = (r"(?:connect|set\s*up|setup|link|hook\s+up|integrate|configure|add"
                  r"|sign\s+in\s+to|log\s+in\s+to)")
_ACCOUNTS_ASK = re.compile(
    r"^(?:(?:so|ok|okay|and|but|also)\s+)?"
    r"(?:(?:what|how)\s+about\s+(?:connecting|adding|linking|setting\s+up|hooking\s+up"
    r"|integrating)\b"
    r"|(?:can|could|would|will|do|does|should)\s+(?:i|you|we|jarvis)\s+(?:please\s+)?"
    + _ACCOUNTS_VERB + r"\b"
    r"|(?:how|where)\s+(?:do|can|could|would|should)\s+(?:i|you|we)\s+(?:please\s+)?"
    + _ACCOUNTS_VERB + r"\b"
    r"|(?:i\s+(?:want|need|would\s+like)\s+(?:you\s+)?to\s+(?:please\s+)?)?"
    + _ACCOUNTS_VERB + r"\b)")

#: The bare follow-ups: "what about gmail?", "how about my email", "and google
#: calendar?". Short and whole-sentence only, so no longer sentence is claimed.
_ACCOUNTS_BARE = re.compile(
    r"^(?:and|what|how)\s+about\s+(?:my\s+|your\s+|a\s+|the\s+)?"
    r"(?:gmail|google(?:\s+(?:calendar|account|mail))?|e-?mail)"
    r"(?:\s+(?:account|calendar|too|as\s+well|then|though))?$"
    r"|^(?:do|can|could)\s+(?:you|jarvis)\s+(?:do|handle|support|connect\s+to)\s+"
    r"(?:my\s+|a\s+|the\s+)?(?:gmail|google(?:\s+(?:calendar|account|mail))?|e-?mail)"
    r"(?:\s+(?:account|calendar|too|as\s+well))?$")

#: What makes a sentence one of THESE: it has to name a Google CALENDAR/account
#: or email. A bare "google" in "external calendars like google or outlook" is
#: not enough - that sentence keeps the iCal connect card it has had since
#: 2026-10-28, and "connect my calendar" keeps it too. This is the narrowest
#: topic that still covers every sentence the field test caught.
_ACCOUNTS_TOPIC = re.compile(
    r"\b(?:e-?mail|gmail|gcal"
    r"|google\s+(?:calendar|calendars|account|accounts|mail|gmail))\b")


def _accounts_topic(s: str) -> bool:
    """Does this sentence name Google or email (or both with the calendar)?"""
    return bool(_ACCOUNTS_TOPIC.search(s))


def _accounts_connect(s: str) -> Optional[Intent]:
    """"can you connect my calendar and email", "what about connecting to a gmail
    account or google calendar?", "connect my google calendar", "connect my
    email" (the HUD field test, 2026-10-29).

    Deliberately narrow: a connecting sentence (or the bare "what about gmail?"
    follow-up) that names Google or email. It never claims a state question
    ("is my calendar connected?" keeps the connect card's own status answer), a
    reminder, or a sentence about a thing ON the calendar."""
    said = s.strip()
    if not said or len(said.split()) > 24:
        return None
    if not _accounts_topic(said):
        return None
    # A reminder or a timer is still that, and an event sentence is the Google
    # answer's (it proposes the event and says one card is needed).
    if re.search(r"\b(?:remind|reminder|reminders|alarm|alarms|timer|timers|watch|"
                 r"watching|notify|notification|todo|to-do)\b", said):
        return None
    if _CONNECT_EVENT.search(said):
        return None
    # "is my google calendar connected?" keeps `_connect`'s own status answer.
    if _CONNECT_STATUS.match(said):
        return None
    if _ACCOUNTS_ASK.match(said) or _ACCOUNTS_BARE.match(said):
        return Intent("accounts_connect")
    return None


def _run_accounts_connect() -> Result:
    """The four real paths, from this PC's own modules and one fixed sentence
    each. Read-only: no card, no connection, no model, and nothing a value could
    be typed into."""
    doc = GOOGLE_SETUP_DOC_FALLBACK
    lead = ACCOUNTS_LEAD_OFF
    try:
        import jarvis_google_calendar as G
        doc = str(getattr(G, "SETUP_DOC", "") or doc)
        chosen = G.mode()
        if chosen == "google":
            lead = ACCOUNTS_LEAD_ON
        elif chosen == "ical":
            lead = ACCOUNTS_LEAD_ICAL
    except Exception:                       # noqa: BLE001 - module absent
        pass
    cmds = ", then ".join(GOOGLE_SETUP_COMMANDS)
    words = ACCOUNTS_PATHS_WORDS.format(lead=lead, cmds=cmds, doc=doc)
    # The Settings jump is the same cardless navigation `_run_calendar_setup`
    # makes: the email details in the answer are typed there, on this PC.
    return Result(words, "accounts_connect", open_settings="account-secrets")


# --- the voice sentences (2026-10-29, the HUD field test) -------------------
#
# "change your voice to Ashby" is NOT answered by a new intent here.
#
# WHAT WENT WRONG. On 2026-10-29 the owner said "change your voice to Ashby" and
# got a raw dump of every built-in voice id ("Say one of: af, af bella, ..."),
# which answers nothing: Ashby is one of the two voices MADE FOR JARVIS, and the
# reason he is not in that list is that the optional pack is not made on this PC
# yet. Main already fixed that in the settings grammar
# (`jarvis_settings_registry.choice_not_made_words`), which answers an unoffered
# blend with the picker's own `BLENDS_TO_MAKE` sentence - so the sentence is a
# `settings_choice_bad` value, not a second answer of its own. A
# `voice_blend_help` intent was tried here and removed on 2026-10-30: two
# answers for one sentence cannot both be the contract, and
# `backend/test_settings_registry.py` already pins the settings one.

#: Shared: neither voice answer can read the pack.
VOICE_MISSING = ("I cannot read the voice settings on this PC: jarvis_voices.py is not in "
                 "the backend folder. Run apply-patches.ps1 again, or use Settings, "
                 "Jarvis's voice.")

# --- "what voice are you using?" (2026-10-29, the HUD field test) -----------
#
# WHAT WENT WRONG. The owner asked which voice Jarvis was using and the 8B model
# answered - there was no fast path for it at all, so the answer was a guess.
# The PC knows: `jarvis_voices.speaker_view()` is the exact read the Voices
# screen makes (the chosen voice, the one really speaking after any fallback,
# and the screen's own note about it). This answer says that, and nothing else.

_VOICE_ASK = re.compile(
    r"(?:what|which)\s+voice\s+(?:are\s+you|do\s+you|is\s+jarvis|is\s+it)"
    r"(?:\s+(?:using|use|have|speaking(?:\s+(?:in|with))?|talking(?:\s+in|with)?|"
    r"running|on|now))*"
    r"|(?:what|which)\s+voice\s+(?:is\s+)?(?:that|this|it|speaking|being\s+used)"
    r"|(?:what's|what\s+is|whats)\s+your\s+voice(?:\s+(?:called|now|today))?"
    r"|(?:tell\s+me\s+)?(?:what|which)\s+voice\s+you(?:'re|\s+are)\s+using")

#: The fixed answer. `{voice}` is the built-in voice's own label from
#: `jarvis_kokoro.label_of` ("American (female) - Heart"); `{note}` is the
#: screen's own note ("" when it has none).
VOICE_ASK_WORDS = ("Right now I speak with {voice}, the built-in Kokoro voice on this PC."
                   "{note} It is set in Settings, Jarvis's voice (the \"Jarvis's built-in "
                   "voice\" list), or you can just ask me to change it.")


def _voice_ask(s: str) -> Optional[Intent]:
    """"what voice are you using", "which voice is that" (2026-10-29)."""
    if _VOICE_ASK.fullmatch(s):
        return Intent("voice_ask")
    return None


def _run_voice_ask() -> Result:
    """Which voice speaks, read from the same view the Voices screen draws."""
    try:
        import jarvis_kokoro as K
        import jarvis_voices as JV
    except Exception:                       # noqa: BLE001 - module absent
        return Result(VOICE_MISSING, "voice_ask")
    view = {}
    try:
        view = JV.speaker_view() or {}
    except Exception:                       # noqa: BLE001 - read the pack only
        view = {}
    choice = str(view.get("choice") or "")
    name = choice if choice and choice != "custom" else ""
    if not name:
        try:
            name = JV.speaker_name()
        except Exception:                   # noqa: BLE001 - module absent
            name = ""
    voice = K.label_of(name) if name else ""
    if not voice:
        voice = "a voice set by hand on this PC"
    note = str(view.get("note") or "").strip()
    return Result(VOICE_ASK_WORDS.format(voice=voice,
                                         note=(" " + note) if note else ""),
                  "voice_ask")


# --- "how do I pair my phone?" (2026-10-29, the HUD field test) -------------
#
# WHAT WENT WRONG. Asked how to pair a phone, the model invented a procedure.
# Both apps really have it: this PC's Settings, Devices card has a "Pair a
# phone" button that shows a QR code (and a code that can be typed), and the
# phone's Settings, Devices card has "Pair with your PC". The PC's own card
# approves the device. Both sentences below are those buttons' own words
# (`jarvis-desktop/src/settings.html`, `jarvis-client`'s DevicesSection), and
# the Tailscale / NordVPN Meshnet rule is the card's own.

PAIR_PHONE_WORDS = (
    "Two screens, one on each device. On this PC: Settings, Devices, then press "
    "\"Pair a phone\" - it shows a QR code, and a code you can type instead. On the phone: "
    "open Jarvis, Settings, Devices, then \"Pair with your PC\", and scan the code or type "
    "it. A card then appears on this PC to approve that phone. The two devices have to "
    "reach each other over Tailscale or NordVPN Meshnet - there is no public tunnel."
)

#: What the owner calls the thing being paired, in one place for both shapes.
_PAIR_THING = r"(?:phone|android(?:\s+phone)?|mobile(?:\s+phone)?|device)"
_PAIR_PHONE = re.compile(
    r"(?:how|where)\s+(?:do|can|could|should)\s+(?:i|you)\s+(?:please\s+)?"
    r"(?:pair|connect|link|set\s*up|setup|add)\s+(?:my\s+|a\s+|the\s+|this\s+)?(?:new\s+)?"
    + _PAIR_THING +
    # The polite tail, "with" on its own included: `normalise` strips a trailing
    # "jarvis", so "how do I pair my phone with Jarvis" arrives as "... with".
    r"(?:\s+(?:to|with)(?:\s+(?:my\s+|the\s+|this\s+)?(?:pc|computer|jarvis|desktop))?)?"
    r"|(?:pair|link|connect)\s+(?:my\s+|a\s+|the\s+|this\s+)?(?:new\s+)?"
    + _PAIR_THING +
    r"(?:\s+(?:to|with)(?:\s+(?:my\s+|the\s+|this\s+)?(?:pc|computer|jarvis|desktop))?)?"
    r"|(?:how|where)\s+(?:do|can)\s+i\s+(?:get|connect)\s+(?:my\s+|a\s+|the\s+)?"
    r"(?:phone|android)\s+(?:set\s+up|connected|paired|working)")


def _pair_phone(s: str) -> Optional[Intent]:
    """"how do I pair my phone", "pair my phone" (2026-10-29)."""
    if _PAIR_PHONE.fullmatch(s):
        return Intent("pair_phone")
    return None


# --------------------------------------------------------------------------
#   Notes and the vault, asked in chat (2026-10-31 field test)
# --------------------------------------------------------------------------
# WHY THIS IS HERE. The owner asked the live HUD "make a note: ..." and "organize
# my notes"; both were promises and neither happened. The machinery exists and
# is good - `jarvis_note_capture.capture` appends to today's Obsidian daily
# note after a File Guardian copy, with an undo receipt and the
# `append_obsidian_daily` tier, and `jarvis_vault_organizer` is a read-only
# planner behind a one-card switch - but neither had a chat door. These patterns
# are the door: they decide which sentences are a note request and hand the
# owner's own words to the EXISTING capture path (no re-implementation, no model,
# no new tool). The organizer answer only reads its real state and plan.
_NOTE_TEXT_COLON = re.compile(
    r"(?:make|add|write)\s+(?:me\s+)?(?:a\s+|one\s+|another\s+)?(?:new\s+)?note"
    r"\s*[:,-]\s*(?P<text>.+)$")
_NOTE_TEXT_SPACE = re.compile(
    r"(?:make|add|write)\s+(?:me\s+)?(?:a\s+|one\s+|another\s+)?(?:new\s+)?note"
    r"\s+(?:that\s+|about\s+)?(?!called\b|titled\b|named\b)(?P<text>.+)$")
_NOTE_THAT = re.compile(r"note\s+that\s+(?P<text>.+)$")
#: "note this: the boiler service is due" - the honesty lane used to own this
#: shape with an "off" answer; the real capture path owns it now (2026-10-31
#: integration: a real action beats an off answer).
_NOTE_THIS = re.compile(r"note\s+this\s*[:,-]?\s+(?P<text>.+)$")
_JOT_DOWN = re.compile(r"jot\s+down\s+(?P<text>.+)$")
_DAILY_NOTE_ADD = re.compile(
    r"(?:add|append|write)\s+(?:this\s+|that\s+)?to\s+"
    r"(?:my\s+|today'?s\s+|todays\s+|the\s+)?(?:obsidian\s+)?"
    r"(?:daily\s+|today'?s\s+)?note\s*(?:[:,-]\s*|\s+)(?P<text>.+)$")
#: Create/rename/delete of a note are NOT built (the notes editor's own honest
#: limit, and the catalogue row says so). These shapes get one plain refusal
#: instead of the model's promise.
_NOTE_CREATE_REFUSED = re.compile(
    r"(?:create|make|start|add)\s+(?:me\s+)?(?:a\s+|one\s+|another\s+)?"
    r"(?:new\s+|brand\s+new\s+)?note\b"
    r"|(?:a\s+|one\s+)?new\s+note\b"
    r"|note\s+(?:called|titled|named)\b")
_NOTE_RENAME_REFUSED = re.compile(
    r"(?:rename|retitle|change\s+the\s+name\s+of)\s+(?:my\s+|the\s+|a\s+)?"
    r"(?:\w+\s+)?note\b")
_NOTE_DELETE_REFUSED = re.compile(
    r"(?:delete|remove|erase|trash)\s+(?:my\s+|the\s+|a\s+)?(?:\w+\s+)?note\b")
#: Asking chat to READ or SEARCH a note: chat does not read note text today.
#: The audit measured the model claiming "I have located your notes" with no
#: tool run. These shapes get the true door in plain words instead - the Notes
#: plate can search/read/save, chat cannot - and it never names a note title, so
#: the hidden-lists rule is kept too. (The honesty lane's own duplicate
#: note_door matcher is retired; this is the one door for note reading.)
_NOTE_READ_PATTERNS = (
    re.compile(r"what\s+(?:does|do)\s+(?:my\s+|the\s+|a\s+|an\s+)?"
               r"(?P<name>.+?)\s+notes?\s+say\b.*"),
    re.compile(r"what(?:'s|\s+is)\s+in\s+(?:my\s+|the\s+|a\s+|an\s+)?"
               r"(?P<name>.+?)\s+notes?\b.*"),
    re.compile(r"(?:read|show\s+me)\s+(?:the\s+|my\s+|a\s+|an\s+)?"
               r"(?P<name>.+?)\s+notes?\b.*"),
    re.compile(r"read\s+(?:me\s+)?my\s+notes?\b.*"),
    re.compile(r"(?:search|look(?:\s+through)?|check|find)\s+"
               r"(?:through\s+|in\s+|for\s+)?(?:my|the)\s+notes?\b.*"),
    re.compile(r"find\s+.*\s+in\s+my\s+notes\b.*"),
    re.compile(r"do\s+i\s+have\s+(?:a\s+)?note\s+(?:about|on|called|named)\b.*"),
    re.compile(r"what\s+notes\s+do\s+i\s+have\b.*"),
    re.compile(r"(?:find|search(?:\s+for)?)\s+(?:my\s+|the\s+)notes?\s+"
               r"(?:about|for|on)\s+(?P<query>.+)"),
    re.compile(r"what\s+do\s+(?:my\s+|the\s+)notes\s+say"
               r"(?:\s+about\s+(?P<query>.+))?"),
)
#: The organizer, in the owner's words. It is a real, built, off-by-default
#: planner; this path only reports its state or shows its read-only preview.
_VAULT_TIDY = re.compile(
    r"(?:organi[sz]e|tidy|sort|clean\s+up|declutter|plan)\s+"
    r"(?:my\s+|the\s+)?(?:obsidian\s+)?(?:vault|notes?)\b"
    r"|(?:organi[sz]e|plan)\s+(?:my\s+|the\s+)?obsidian\b")
#: "apply the plan", "organize my vault now", "tidy it for real" - the WRITER
#: half of the organizer, through the module's own one-card apply route. The
#: words deliberately differ from the read-only plan shapes above: "now" and
#: "for real" ask for the card, not another preview.
_VAULT_APPLY = re.compile(
    r"(?:apply|use|do)\s+(?:the\s+|that\s+|this\s+)?"
    r"(?:plan|organi[sz]ation|changes?)\b.*"
    r"|apply\s+it\b.*"
    r"|(?:organi[sz]e|tidy)\s+(?:my\s+|the\s+)?(?:obsidian\s+)?"
    r"(?:vault|notes?)\s+now\b.*"
    r"|(?:organi[sz]e|tidy)\s+it\s+for\s+real\b.*"
    r"|go\s+ahead\s+and\s+(?:organi[sz]e|tidy|apply)\b.*")
#: "organize just my Welcome note", "reorganize a specific set of notes" - the
#: organizer has NO per-note mode: it plans the whole vault and applies one
#: card for the whole batch. These get that truth plainly, never a pretend
#: scoped plan. The lookahead keeps it to notes/vault asks, so "organize just my
#: desktop icons" is still the model's.
_VAULT_SCOPED = re.compile(
    r"(?:re)?organi[sz]e\s+(?:just|only)\s+"
    r"(?:my\s+|the\s+|these\s+|those\s+)?(?P<set>.+?)\s+notes?\b.*"
    r"|(?:re)?organi[sz]e\s+(?:these|those)\s+notes?\s*[:,-]?\s*"
    r"(?P<these>.*)"
    r"|(?:re)?organi[sz]e\s+(?:a\s+specific|a\s+particular)\s+"
    r"(?:set\s+of\s+)?notes?\s*[:,-]?\s*(?P<specific>.*)"
    r"|(?:re)?organi[sz]e\s+(?:one|this|that)\s+notes?\s*[:,-]?\s*"
    r"(?P<single>.+)")
_ORGANIZER_ON = re.compile(
    r"(?:turn|switch)\s+on\s+(?:the\s+|my\s+)?vault\s+organi[sz]er"
    r"|enable\s+(?:the\s+|my\s+)?vault\s+organi[sz]er")
#: The last plan THIS chat session showed, so "apply the plan" uses the plan
#: the owner just looked at rather than a silently different one. In memory
#: only; the module also keeps its own capped plan memory.
_ORGANIZER_LAST_PLAN: dict = {}
#: Obsidian's own theme/CSS/templates/plugins are not Jarvis's to change, and
#: never were - asked about, the model used to invent them.
_STYLE_WORD = re.compile(
    r"\b(?:theme|themes|css|style|styles|stylesheet|stylesheets|template|templates|"
    r"plugin|plugins|customi[sz](?:e|es|ed|ing|ation)?)\b")
_STYLE_VERB = re.compile(
    r"^(?:(?:can|could|would|will)\s+(?:i|you|we)\s+(?:please\s+)?|please\s+|"
    r"i\s+(?:want|would\s+like)\s+(?:to\s+)?|let\s+(?:me|us)\s+)?"
    r"(?:customi[sz]e|change|set|edit|make|use|apply|add|create|install|"
    r"enable|update|modify)\b")


def _obsidian_style_refused(s: str) -> bool:
    """Is this a request to change Obsidian's own theme, CSS or templates?"""
    return ("obsidian" in s and _STYLE_WORD.search(s) is not None
            and _STYLE_VERB.match(s) is not None)


def _organizer_selection(raw) -> list:
    """The note names in a pick-a-set sentence, in the owner's order.

    "Welcome and Alpha", "Welcome, Alpha", "the Welcome note" and "Work/Alpha"
    all become names; quotes are stripped and a trailing "note(s)" is dropped.
    An empty list means the owner named no notes - the runner then asks for
    names rather than guessing a selection.
    """
    text = str(raw or "").strip().strip('"\'`')
    parts = re.split(r"\s*(?:,|;|&|\band\b)\s*", text) if text else []
    out: list = []
    for part in parts:
        name = part.strip().strip('"\'`')
        name = re.sub(r"^(?:the|my|these|those)\s+", "", name, flags=re.I)
        name = re.sub(r"\s+notes?$", "", name, flags=re.I).strip()
        if name and name not in out:
            out.append(name)
    return out

#: The wave-1 note WRITES (2026-10-31, the notes flexibility decision): create
#: ONE note, add words to the END of ONE existing note, add or remove ONE tag.
#: Every one is a single-file write through jarvis_notes_edit's own routes, so
#: the module keeps the one card, the File Guardian copy and the undo receipt.
#: Several notes in one request are refused in plain words (below), and the
#: owner's other shapes keep their own doors: "note this"/"make a note: X" is
#: the daily note, "add milk to my shopping list" is the list, "remind me"
#: is the reminder and "email ..." is email. None of those match here.
_NOTE_CREATE_NAMED = re.compile(
    r"(?:create|make|start)\s+(?:me\s+)?(?:a\s+|one\s+)?(?:new\s+)?note"
    r"\s+(?:called|named|titled)\s+(?P<name>.+?)"
    r"(?:\s+(?:with|containing|saying)\s+(?P<text>.+))?$")
_LIST_NAMES_TO_LEAVE = frozenset({
    "todo", "to-do", "to do", "todo list", "to-do list", "to do list",
    "shopping list", "list",
})


def _list_owns_name(name: str) -> bool:
    """True when "add X to my <name>" belongs to the named-list grammar.

    The notes lane's append regex is general ("add TEXT to my NAME"); without
    this guard it claimed "add milk to my shopping list" and "add milk to my
    todo list". A named list always ends in "list" (or is one of the synonyms
    above), so the list keeps its own path (2026-10-31 final-wave integration).
    """
    n = name.strip().strip("\"'").casefold()
    return n in _LIST_NAMES_TO_LEAVE or n.endswith(" list")


_NOTE_APPEND_COLON = re.compile(
    r"(?:add|append)\s+(?:this\s+)?to\s+(?:my|the)\s+(?P<name>.+?)"
    r"(?:\s+note)?\s*[:,-]\s*(?P<text>.+)$")
_NOTE_APPEND_PLAIN = re.compile(
    r"(?:add|append|write)\s+(?P<text>.+?)\s+(?:to|into|at\s+the\s+end\s+of)\s+"
    r"(?:my|the)\s+(?P<name>.+?)(?:\s+note)?\s*$")
_NOTE_TAG_ADD = re.compile(
    r"(?:add|put)\s+(?:the\s+)?tag\s+(?P<tag>[#A-Za-z0-9_/-]+)\s+(?:to|on)\s+"
    r"(?:my|the)\s+(?P<name>.+?)(?:\s+note)?\s*$")
_NOTE_TAG_REMOVE = re.compile(
    r"(?:remove|delete|take)\s+(?:the\s+)?tag\s+(?P<tag>[#A-Za-z0-9_/-]+)\s+from\s+"
    r"(?:my|the)\s+(?P<name>.+?)(?:\s+note)?\s*$")
_NOTE_TAG_WITH = re.compile(
    r"(?:tag|label)\s+(?:my|the)\s+(?P<name>.+?)(?:\s+note)?\s+with\s+"
    r"(?P<tag>[#A-Za-z0-9_/-]+)\b.*")
#: Several notes at once: refused, never quietly done to the first one.
_NOTE_WRITE_BATCH = re.compile(
    r"(?:add|append|write|tag|label|create|make|put)\b.*\b"
    r"(?:all|every|each|both)\b.*\bnotes?\b.*"
    r"|(?:add|append|write|tag|label)\s+(?:it\s+)?to\s+(?:my|the)\s+"
    r"(?:whole|entire)\s+(?:obsidian\s+)?vault\b.*")
#: Rename and move, wave 4. The note name is required in a familiar shape; a
#: plain "move my reminder to 5pm" (no note word and no "into") stays the
#: scheduler's, and a folder named after "into" is fine.
_NOTE_RENAME = re.compile(
    r"(?:rename|retitle)\s+(?:my\s+|the\s+)?note\s+(?P<name>.+?)\s+"
    r"(?:to|as)\s+(?P<new>.+)$"
    r"|(?:rename|retitle)\s+(?:my\s+|the\s+)?(?P<name2>.+?)"
    r"(?:\s+note)?\s+(?:to|as)\s+(?P<new2>.+)$")
_NOTE_MOVE = re.compile(
    r"move\s+(?:my\s+|the\s+)?(?P<name>.+?)\s+note\s+(?:to|into)\s+"
    r"(?:the\s+|my\s+|a\s+)?(?P<folder>.+?)(?:\s+folder)?"
    r"(?:\s+and\s+(?P<extra>create|make|fix|update)\b.*)?$"
    r"|move\s+(?:the\s+)?note\s+(?P<name2>.+?)\s+(?:to|into)\s+"
    r"(?:the\s+|my\s+|a\s+)?(?P<folder2>.+?)(?:\s+folder)?"
    r"(?:\s+and\s+(?P<extra2>create|make|fix|update)\b.*)?$"
    r"|move\s+(?:my\s+|the\s+)?(?P<name3>.+?)\s+into\s+"
    r"(?:the\s+|my\s+|a\s+)?(?P<folder3>.+?)(?:\s+folder)?"
    r"(?:\s+and\s+(?P<extra3>create|make|fix|update)\b.*)?$")
#: The module's own sentences, so the fast path never invents a promise.
NOTE_WRITE_BATCH_SAID = (
    "I change one note at a time, so nothing was written: name ONE note, like "
    "\"add milk to my Shopping note\".")
NOTE_DELETE_SAID = (
    "Deleting a line or a note is not built, so nothing was changed. I can add, "
    "format, replace, tag, rename a heading or move a line into a section - say "
    "one of those.")
_NOTE_DELETE_LINE = re.compile(
    r"(?:delete|remove|erase|trash)\s+(?:this|that|the|my)\s+"
    r"(?:line|lines|sentence|paragraph)\b.*")


NOTE_HIDDEN_SAID = (
    "Your lists are hidden on this PC, so I did not open or change a note. "
    "Tap Show and confirm it is you, then ask again.")
NOTE_NOT_FOUND_SAID = (
    "I could not find a note called \"{name}\" in your Obsidian vault. "
    "Nothing was written - open the Brain window's Notes plate to check the name.")


def _notes_write_hidden() -> bool:
    """True while the owner's hidden-lists / App-lock state hides private words."""
    try:
        hidden, _words = _calendar_hidden()
        return bool(hidden)
    except Exception:                       # noqa: BLE001 - cannot tell: be safe
        return True


def _note_path_for(name: str) -> str:
    """`Shopping` -> `Shopping.md`; a name that already ends .md/.txt is kept."""
    text = str(name or "").strip().strip('"').strip("'")
    if not text:
        return ""
    return text if text.lower().endswith((".md", ".txt")) else text + ".md"


def _find_note(rel: str):
    """`(path, "", title)` for a unique note title/path, or `(None, why, "")`.

    Read-only: it asks the notes editor's existing list (paths and titles, never
    text) and matches the owner's words against the title or the path. Two
    matches are an ambiguity answered in words, never guessed.
    """
    try:
        import jarvis_notes_edit as E
    except Exception:                       # noqa: BLE001 - module absent
        return None, "The notes editor is not installed on this PC, so nothing was changed.", ""
    want = str(rel or "").strip().replace("\\", "/").casefold()
    stem = want.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    code, body = E.handle_list("")
    if code != 200 or not isinstance(body, dict):
        return None, "Your Obsidian vault could not be read just now, so nothing was changed.", ""
    exact, loose = [], []
    for row in (body.get("notes") or []):
        path = str(row.get("path") or "")
        title = str(row.get("title") or "")
        if not path:
            continue
        if path.casefold() == want:
            exact.append((path, title))
        elif title.casefold() == stem and len(stem) > 0:
            loose.append((path, title))
    found = exact or loose
    if not found:
        return None, "not_found", ""
    if len(found) > 1:
        names = "; ".join(p for p, _t in found[:6])
        return None, (f"That name matches {len(found)} notes (" + names + "), so "
                      "nothing was changed - say the note's folder and name, like "
                      "\"add milk to my Shopping note in 02 - Areas\"."), ""
    return found[0][0], "", found[0][1]


def _note_read_for_write(path: str):
    """`(sha256, why)` from the editor's own read: the write must start from it."""
    try:
        import jarvis_notes_edit as E
        from urllib.parse import quote
        code, body = E.handle_read("path=" + quote(path, safe=""))
    except Exception as exc:                # noqa: BLE001 - said, never swallowed
        return "", f"The note could not be read ({type(exc).__name__}), so nothing was changed."
    if code != 200 or not isinstance(body, dict):
        err = str((body or {}).get("error") or "the note could not be read") if isinstance(body, dict) else "the note could not be read"
        return "", err + " Nothing was changed."
    return str(body.get("sha256") or ""), ""


def _note_write_result(body, ok_intent: str, wait_intent: str, why_intent: str):
    body = body if isinstance(body, dict) else {}
    said = str(body.get("message") or "").strip()
    state = str(body.get("state") or "")
    if state in ("saved", "unchanged"):
        return Result(said or "Done.", ok_intent)
    if state == "waiting":
        return Result(said or "Waiting for your approval card.", wait_intent)
    return Result(said or "Nothing was written.", why_intent)


def _run_note_create(f: dict) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_HIDDEN_SAID, "note_write_hidden")
    path = _note_path_for(str(f.get("name") or ""))
    if not path:
        return Result("What should the new note be called? Say \"create a note called ...\".",
                      "note_create_refused")
    text = str(f.get("text") or "")
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_create({"path": path, "text": text}, by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The note could not be created ({type(exc).__name__}), so nothing was created.",
                      "note_create_refused")
    if code not in (200, 202):
        said = str((body or {}).get("error") or "Nothing was created.") if isinstance(body, dict) else "Nothing was created."
        return Result(said, "note_create_refused")
    return _note_write_result(body, "note_created", "note_create_waiting", "note_create_refused")


def _run_note_append(f: dict) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_HIDDEN_SAID, "note_write_hidden")
    name = str(f.get("name") or "").strip()
    text = str(f.get("text") or "").strip()
    if not name or not text:
        return Result('Say it as "add milk to my Shopping note", and I will add the words.',
                      "note_append_refused")
    path, why, _title = _find_note(_note_path_for(name))
    if path is None:
        if why == "not_found":
            return Result(NOTE_NOT_FOUND_SAID.format(name=name), "note_append_refused")
        return Result(why, "note_append_refused")
    sha, why = _note_read_for_write(path)
    if why:
        return Result(why, "note_append_refused")
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_append({"path": path, "text": text,
                                      "expected_sha256": sha}, by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The words could not be added ({type(exc).__name__}), so nothing was written.",
                      "note_append_refused")
    if code not in (200, 202):
        said = str((body or {}).get("error") or "Nothing was written.") if isinstance(body, dict) else "Nothing was written."
        return Result(said, "note_append_refused")
    return _note_write_result(body, "note_appended", "note_append_waiting", "note_append_refused")


def _run_note_tag(f: dict) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_HIDDEN_SAID, "note_write_hidden")
    name = str(f.get("name") or "").strip()
    tag = str(f.get("tag") or "").strip()
    action = str(f.get("action") or "add").strip().lower()
    if not name or not tag:
        return Result('Say it as "add tag recipes to my Shopping note", and I will tag it.',
                      "note_tag_refused")
    path, why, _title = _find_note(_note_path_for(name))
    if path is None:
        if why == "not_found":
            return Result(NOTE_NOT_FOUND_SAID.format(name=name), "note_tag_refused")
        return Result(why, "note_tag_refused")
    sha, why = _note_read_for_write(path)
    if why:
        return Result(why, "note_tag_refused")
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_tag({"path": path, "tag": tag, "action": action,
                                   "expected_sha256": sha}, by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The tag could not be changed ({type(exc).__name__}), so nothing was changed.",
                      "note_tag_refused")
    if code not in (200, 202):
        said = str((body or {}).get("error") or "Nothing was changed.") if isinstance(body, dict) else "Nothing was changed."
        return Result(said, "note_tag_refused")
    return _note_write_result(body, "note_tagged", "note_tag_waiting", "note_tag_refused")


def _run_note_rename(f: dict) -> Result:
    """\"rename my X to Y\" - one note, one card, links preserved, undo."""
    if _notes_write_hidden():
        return Result(NOTE_HIDDEN_SAID, "note_write_hidden")
    name = str(f.get("name") or "").strip()
    new = str(f.get("new") or "").strip()
    if not name or not new:
        return Result('Say it as "rename my Welcome note to Home".', "note_rename_refused")
    paths = _note_title_paths(name)
    if len(paths) > 1:
        return Result(f"That name matches {len(paths)} notes (" + "; ".join(paths[:6])
                      + "), so nothing was changed - say the note's folder and name.",
                      "note_rename_refused")
    path, why, _title = _find_note(_note_path_for(name))
    if path is None:
        if why == "not_found":
            return Result(NOTE_NOT_FOUND_SAID.format(name=name), "note_rename_refused")
        return Result(why, "note_rename_refused")
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_rename({"path": path, "title": new},
                                     by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The note could not be renamed ({type(exc).__name__}), so nothing was changed.",
                      "note_rename_refused")
    if code not in (200, 202):
        said = str((body or {}).get("error") or "Nothing was changed.") if isinstance(body, dict) else "Nothing was changed."
        return Result(said, "note_rename_refused")
    return _note_write_result(body, "note_renamed", "note_rename_waiting",
                              "note_rename_refused")


def _run_note_move(f: dict) -> Result:
    """\"move my X into Folder\" - one note, links preserved, one card, undo."""
    if _notes_write_hidden():
        return Result(NOTE_HIDDEN_SAID, "note_write_hidden")
    name = str(f.get("name") or "").strip()
    folder = str(f.get("folder") or "").strip()
    if not name or not folder:
        return Result('Say it as "move my Welcome note into Projects".', "note_move_refused")
    paths = _note_title_paths(name)
    if len(paths) > 1:
        return Result(f"That name matches {len(paths)} notes (" + "; ".join(paths[:6])
                      + "), so nothing was changed - say the note's folder and name.",
                      "note_move_refused")
    path, why, _title = _find_note(_note_path_for(name))
    if path is None:
        if why == "not_found":
            return Result(NOTE_NOT_FOUND_SAID.format(name=name), "note_move_refused")
        return Result(why, "note_move_refused")
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_move({"path": path, "folder": folder,
                                    "create_folder": bool(f.get("create"))},
                                   by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The note could not be moved ({type(exc).__name__}), so nothing was changed.",
                      "note_move_refused")
    if code not in (200, 202):
        said = str((body or {}).get("error") or "Nothing was changed.") if isinstance(body, dict) else "Nothing was changed."
        return Result(said, "note_move_refused")
    return _note_write_result(body, "note_moved", "note_move_waiting",
                              "note_move_refused")




#: The wave-2 SURGICAL edits (2026-10-31): add a line under ONE heading, add a
#: line before/after ONE literal anchor, wrap ONE span in bold/italic (or
#: unwrap it), and replace ONE exact occurrence. Each is one file, one card,
#: with the exact before/after shown on the card. The matchers require the
#: sentence to name the note ("in my workout log"), so an ordinary "make it
#: bold" is still the model's, and "add milk to my workout log" keeps the
#: wave-1 append-at-end door.
_NOTE_SURGICAL_UNDER = re.compile(
    r"(?:add|put)\s+(?P<text>.+?)\s+(?:under|underneath)\s+(?:the\s+)?"
    r"(?P<head>.+?)\s+heading\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_SURGICAL_SECTION = re.compile(
    r"(?:add|put)\s+(?P<text>.+?)\s+(?:to|in)\s+(?:the\s+)?"
    r"(?P<head>.+?)\s+section\s+of\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_SURGICAL_ANCHOR = re.compile(
    r"(?:add|put)\s+(?P<text>.+?)\s+(?P<mode>before|after)\s+(?:the\s+)?"
    r"(?P<anchor>.+?)(?:\s+line)?\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_FORMAT_ADD = re.compile(
    r"(?:make|put|set)\s+(?P<target>.+?)\s+(?:in\s+)?(?P<style>bold|italic|strikethrough|strike|code)"
    r"\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_FORMAT_REMOVE = re.compile(
    r"(?:remove\s+(?:the\s+)?(?P<style>bold|italic|strikethrough|strike|code)\s+from|un(?P<style2>bold|italic))"
    r"\s+(?P<target>.+?)\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_REPLACE = re.compile(
    r"(?:replace|change)\s+(?P<old>.+?)\s+(?:with|to)\s+(?P<new>.+?)"
    r"\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")

NOTE_SURGICAL_HIDDEN = (
    "Your lists are hidden on this PC, so I did not open or change a note. "
    "Tap Show and confirm it is you, then ask again.")
NOTE_SURGICAL_NO_NOTE = (
    "I could not find a note called \"{name}\" in your Obsidian vault. "
    "Nothing was changed - open the Brain window's Notes plate to check the name.")


def _surgical_note(name: str):
    """`(path, sha, why)` for a note the owner named in a surgical sentence."""
    path, why, _title = _find_note(_note_path_for(str(name or "")))
    if path is None:
        if why == "not_found":
            return None, "", NOTE_SURGICAL_NO_NOTE.format(name=name)
        return None, "", why
    sha, why = _note_read_for_write(path)
    if why:
        return None, "", why
    return path, sha, ""


def _run_note_insert(f: dict) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_SURGICAL_HIDDEN, "note_write_hidden")
    path, sha, why = _surgical_note(str(f.get("name") or ""))
    if path is None:
        return Result(why, "note_insert_refused")
    mode = str(f.get("mode") or "under_heading")
    target = str(f.get("target") or "").strip()
    text = str(f.get("text") or "").strip()
    if not text or not target:
        return Result('Say what to add and where, like "add stretch under the Warm-up '
                      'heading in my workout log".', "note_insert_refused")
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_insert({"path": path, "text": text, "mode": mode,
                                      "target": target, "expected_sha256": sha},
                                     by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The line could not be added ({type(exc).__name__}), so nothing was changed.",
                      "note_insert_refused")
    if code not in (200, 202):
        said = str((body or {}).get("error") or "Nothing was changed.") if isinstance(body, dict) else "Nothing was changed."
        return Result(said, "note_insert_refused")
    return _note_write_result(body, "note_inserted", "note_insert_waiting", "note_insert_refused")


def _run_note_format(f: dict) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_SURGICAL_HIDDEN, "note_write_hidden")
    path, sha, why = _surgical_note(str(f.get("name") or ""))
    if path is None:
        return Result(why, "note_format_refused")
    style = str(f.get("style") or "").strip().lower()
    action = str(f.get("action") or "add").strip().lower()
    target = str(f.get("target") or "").strip()
    if not target or style not in ("bold", "italic"):
        return Result('Say what to format and how, like "make squats bold in my workout log".',
                      "note_format_refused")
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_format({"path": path, "target": target, "style": style,
                                      "action": action, "expected_sha256": sha},
                                     by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The text could not be formatted ({type(exc).__name__}), so nothing was changed.",
                      "note_format_refused")
    if code not in (200, 202):
        said = str((body or {}).get("error") or "Nothing was changed.") if isinstance(body, dict) else "Nothing was changed."
        return Result(said, "note_format_refused")
    return _note_write_result(body, "note_formatted", "note_format_waiting", "note_format_refused")


def _run_note_replace(f: dict) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_SURGICAL_HIDDEN, "note_write_hidden")
    path, sha, why = _surgical_note(str(f.get("name") or ""))
    if path is None:
        return Result(why, "note_replace_refused")
    old = str(f.get("old") or "")
    new = str(f.get("new") or "")
    if not old or not new:
        return Result('Say it as "replace squats with lunges in my workout log".',
                      "note_replace_refused")
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_replace({"path": path, "old": old, "new": new,
                                       "expected_sha256": sha},
                                      by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The words could not be replaced ({type(exc).__name__}), so nothing was changed.",
                      "note_replace_refused")
    if code not in (200, 202):
        said = str((body or {}).get("error") or "Nothing was changed.") if isinstance(body, dict) else "Nothing was changed."
        return Result(said, "note_replace_refused")
    return _note_write_result(body, "note_replaced", "note_replace_waiting", "note_replace_refused")




#: Wave 3 (2026-10-31): the owner's "really enhance customizability" ask. One
#: deterministic sentence per capability, all ending in the note's name ("in my
#: workout log"), all through the one /api/notes/customize route, so every edit
#: keeps the wave-2 card, preview, guardian copy and undo.
_NOTE_LINE_BULLET = re.compile(
    r"(?:turn|make|change|put)\s+(?P<text>.+?)\s+(?:into|to|as)\s+a\s+bullet"
    r"(?:\s+point)?\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_LINE_ADD_BULLET = re.compile(
    r"(?:add|put)\s+a\s+bullet\s+(?:for|to)\s+(?P<text>.+?)\s+in\s+(?:my|the)\s+"
    r"(?P<name>.+?)\s*$")
_NOTE_LINE_CHECK = re.compile(
    r"(?:turn|make|change|put)\s+(?P<text>.+?)\s+(?:into|to|as)\s+a\s+checklist"
    r"(?:\s+item)?\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_LINE_CHECKBOX = re.compile(
    r"(?:add|put)\s+a\s+checkbox\s+(?:for|to)\s+(?P<text>.+?)\s+in\s+(?:my|the)\s+"
    r"(?P<name>.+?)\s*$")
_NOTE_LINE_QUOTE = re.compile(
    r"(?:turn|make|change|put)\s+(?P<text>.+?)\s+(?:into|to)\s+a\s+quote"
    r"\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_LINE_NUMBER = re.compile(
    r"number\s+(?P<text>.+?)\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_LINE_HEADING = re.compile(
    r"(?:turn|make|change)\s+(?P<text>.+?)\s+(?:into|to|a|as)\s+(?P<hashes>#{1,6})?\s*"
    r"heading\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_LINE_TICK = re.compile(
    r"tick\s+(?P<text>.+?)\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_LINE_UNTICK = re.compile(
    r"untick\s+(?P<text>.+?)\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_LINE_PLAIN = re.compile(
    r"(?:turn\s+(?P<text1>.+?)\s+back\s+(?:into|to)\s+plain\s+text|"
    r"remove\s+the\s+(?:bullet|number|checkbox|checklist|heading|quote)\s+from\s+"
    r"(?P<text2>.+?))\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_NEW_SECTION = re.compile(
    r"(?:add|put)\s+(?:a\s+)?(?:new\s+)?section\s+(?:called|named|titled)?\s*"
    r"(?P<heading>.+?)\s+(?:to|in)\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_RENAME_HEADING = re.compile(
    r"(?:rename|change)\s+the\s+(?P<old>.+?)\s+heading\s+(?:to|into)\s+"
    r"(?P<new>.+?)\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_SET_PROPERTY = re.compile(
    r"(?:set|add\s+property)\s+(?P<key>[A-Za-z0-9_.-]+)\s+"
    r"(?:to|with\s+value|with)\s+(?P<value>.+?)\s+in\s+(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_REMOVE_PROPERTY = re.compile(
    r"remove\s+the\s+(?P<key>[A-Za-z0-9_.-]+)\s+property\s+(?:from|in)\s+"
    r"(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_LINK = re.compile(
    r"(?:add\s+a\s+link\s+to|link)\s+(?P<target>.+?)\s+(?:in|from)\s+"
    r"(?:my|the)\s+(?P<name>.+?)\s*$")
_NOTE_TEMPLATE_CREATE = re.compile(
    r"create\s+(?:a\s+|an\s+)?(?P<kind>workout\s+log|meeting\s+notes|daily\s+journal|"
    r"journal|project\s+note)"
    r"(?:\s+(?:for|about)\s+(?P<subject>.+?))?\s*$")
_NOTE_TEMPLATE_SAVE = re.compile(
    r"save\s+(?:my\s+|the\s+)?(?P<name>.+?)(?:\s+note)?\s+as\s+a\s+template"
    r"(?:\s+(?:called|named)\s+(?P<tname>.+?))?\s*$")
_NOTE_TEMPLATE_LIST = re.compile(
    r"(?:list|show)\s+my\s+templates|what\s+templates\s+do\s+i\s+have")


def _wave3_note(name: str):
    path, why, _title = _find_note(_note_path_for(str(name or "")))
    if path is None:
        if why == "not_found":
            return None, "", NOTE_SURGICAL_NO_NOTE.format(name=name)
        return None, "", why
    sha, why = _note_read_for_write(path)
    return (path, sha, "") if not why else (None, "", why)


def _run_note_customize(f: dict, action: str, card: str) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_SURGICAL_HIDDEN, "note_write_hidden")
    path, sha, why = _wave3_note(str(f.get("name") or ""))
    if path is None:
        return Result(why, "note_customize_refused")
    body = {"path": path, "action": action, "expected_sha256": sha}
    body.update({k: v for k, v in f.items() if k not in ("name", "intent")})
    try:
        import jarvis_notes_edit as E
        code, out = E.handle_customize(body, by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The note could not be changed ({type(exc).__name__}), so nothing was changed.",
                      "note_customize_refused")
    if code not in (200, 202):
        said = str((out or {}).get("error") or "Nothing was changed.") if isinstance(out, dict) else "Nothing was changed."
        return Result(said, "note_customize_refused")
    return _note_write_result(out, "note_customized", "note_customize_waiting",
                              "note_customize_refused")


def _run_template_create(f: dict) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_SURGICAL_HIDDEN, "note_write_hidden")
    try:
        import jarvis_notes_edit as E
        title, body = E.builtin_template(str(f.get("kind") or ""),
                                         str(f.get("subject") or ""))
    except Exception as exc:                # noqa: BLE001
        return Result(f"The template could not be made ({type(exc).__name__}), so nothing was created.",
                      "template_create_refused")
    if not title:
        return Result(body, "template_create_refused")
    import datetime
    name = title
    subject = str(f.get("subject") or "").strip()
    if subject:
        name = name + " - " + subject
    elif f.get("kind") in ("journal",):
        name = name + " - " + datetime.date.today().isoformat()
    path = _note_path_for(name)
    try:
        code, out = E.handle_create({"path": path, "text": body}, by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The note could not be created ({type(exc).__name__}), so nothing was created.",
                      "template_create_refused")
    if code not in (200, 202):
        said = str((out or {}).get("error") or "Nothing was created.") if isinstance(out, dict) else "Nothing was created."
        return Result(said, "template_create_refused")
    return _note_write_result(out, "template_created", "template_create_waiting",
                              "template_create_refused")


def _run_template_save(f: dict) -> Result:
    if _notes_write_hidden():
        return Result(NOTE_SURGICAL_HIDDEN, "note_write_hidden")
    path, sha, why = _wave3_note(str(f.get("name") or ""))
    if path is None:
        return Result(why, "template_save_refused")
    body = {"path": path, "action": "save_template", "expected_sha256": sha}
    if str(f.get("tname") or "").strip():
        body["name"] = str(f.get("tname")).strip()
    try:
        import jarvis_notes_edit as E
        code, out = E.handle_customize(body, by="chat", wait_s=1.5)
    except Exception as exc:                # noqa: BLE001
        return Result(f"The template could not be saved ({type(exc).__name__}), so nothing was saved.",
                      "template_save_refused")
    if code not in (200, 202):
        said = str((out or {}).get("error") or "Nothing was saved.") if isinstance(out, dict) else "Nothing was saved."
        return Result(said, "template_save_refused")
    return _note_write_result(out, "template_saved", "template_save_waiting",
                              "template_save_refused")


def _run_template_list() -> Result:
    if _notes_write_hidden():
        return Result(NOTE_SURGICAL_HIDDEN, "note_write_hidden")
    try:
        import jarvis_notes_edit as E
        names, why = E.list_templates()
    except Exception as exc:                # noqa: BLE001
        return Result(f"The templates could not be read ({type(exc).__name__}).",
                      "template_list_refused")
    if why:
        return Result("I could not read your templates: " + why, "template_list_refused")
    if not names:
        return Result("You have no templates yet.", "template_listed")
    return Result("Your templates: " + ", ".join(names) + ".", "template_listed")



def _note_title_paths(name: str) -> list:
    """Every note whose title matches `name`, for the rename/move ambiguity rule."""
    try:
        import jarvis_notes_edit as E
        code, body = E.handle_list("")
    except Exception:                       # noqa: BLE001
        return []
    if code != 200 or not isinstance(body, dict):
        return []
    stem = _note_path_for(str(name or "")).rsplit("/", 1)[-1].lower()
    if stem.endswith((".md", ".txt")):
        stem = stem.rsplit(".", 1)[0]
    if not stem:
        return []
    found = []
    for row in (body.get("notes") or []):
        path = str(row.get("path") or "")
        title = str(row.get("title") or "")
        if path and (title.casefold() == stem or path.rsplit("/", 1)[-1].rsplit(".", 1)[0].casefold() == stem):
            found.append(path)
    return found


def _rename_move_overcapture(name: str, folder: str = "") -> bool:
    """True for sentences that belong to the surgical/customization lane."""
    text = (name + " " + folder).lower()
    if re.search(r"\b(heading|section|line|property|tag)s?\b", text):
        return True
    return name.strip().lower().startswith(("in the ", "in my ", "from "))


def _note_rename_move_asking(raw: str) -> Optional[Intent]:
    """Read a rename/move from the raw sentence, keeping the title's case."""
    s = str(raw or "").strip().rstrip("?.!").strip()
    m = _NOTE_RENAME.fullmatch(s)
    if m:
        name = (m.group("name") or m.group("name2") or "").strip()
        new = (m.group("new") or m.group("new2") or "").strip()
        if name and new and not _rename_move_overcapture(name):
            return Intent("note_rename", {"name": name, "new": new})
    m = _NOTE_MOVE.fullmatch(s)
    if m:
        name = (m.group("name") or m.group("name2") or m.group("name3") or "").strip()
        folder = (m.group("folder") or m.group("folder2") or m.group("folder3") or "").strip()
        extra = (m.group("extra") or m.group("extra2") or m.group("extra3") or "").lower()
        if name and folder and not _rename_move_overcapture(name, folder):
            return Intent("note_move", {"name": name, "folder": folder,
                                        "create": extra in ("create", "make")})
    return None


def _note_asking(s: str) -> Optional[Intent]:
    """The note/vault sentences above, or None (not ours)."""
    if _NOTE_WRITE_BATCH.fullmatch(s):
        return Intent("notes_batch_refused")
    if _NOTE_DELETE_LINE.fullmatch(s):
        return Intent("note_delete_refused")
    m = _NOTE_RENAME.fullmatch(s)
    if m:
        name = (m.group("name") or m.group("name2") or "").strip()
        new = (m.group("new") or m.group("new2") or "").strip()
        if name and new and not _rename_move_overcapture(name):
            return Intent("note_rename", {"name": name, "new": new})
    m = _NOTE_MOVE.fullmatch(s)
    if m:
        name = (m.group("name") or m.group("name2") or m.group("name3") or "").strip()
        folder = (m.group("folder") or m.group("folder2") or m.group("folder3") or "").strip()
        extra = (m.group("extra") or m.group("extra2") or m.group("extra3") or "").lower()
        if name and folder and not _rename_move_overcapture(name, folder):
            return Intent("note_move", {"name": name, "folder": folder,
                                        "create": extra in ("create", "make")})
    m = _NOTE_RENAME.fullmatch(s)
    if m:
        name = (m.group("name") or m.group("name2") or "").strip()
        new = (m.group("new") or m.group("new2") or "").strip()
        if name and new and not _rename_move_overcapture(name):
            return Intent("note_rename", {"name": name, "new": new})
    m = _NOTE_MOVE.fullmatch(s)
    if m:
        name = (m.group("name") or m.group("name2") or m.group("name3") or "").strip()
        folder = (m.group("folder") or m.group("folder2") or m.group("folder3") or "").strip()
        extra = (m.group("extra") or m.group("extra2") or m.group("extra3") or "").lower()
        if name and folder and not _rename_move_overcapture(name, folder):
            return Intent("note_move", {"name": name, "folder": folder,
                                        "create": extra in ("create", "make")})
    m = _NOTE_CREATE_NAMED.fullmatch(s)
    if m:
        return Intent("note_create", {"name": m.group("name").strip(),
                                      "text": (m.group("text") or "").strip()})
    m = _NOTE_TAG_ADD.fullmatch(s) or _NOTE_TAG_WITH.fullmatch(s)
    if m:
        return Intent("note_tag", {"name": m.group("name").strip(),
                                   "tag": m.group("tag").strip(), "action": "add"})
    m = _NOTE_TAG_REMOVE.fullmatch(s)
    if m:
        return Intent("note_tag", {"name": m.group("name").strip(),
                                   "tag": m.group("tag").strip(), "action": "remove"})
    for rx in (_DAILY_NOTE_ADD, _NOTE_TEXT_COLON, _NOTE_THIS, _JOT_DOWN,
               _NOTE_THAT, _NOTE_TEXT_SPACE):
        m = rx.fullmatch(s)
        if m:
            text = m.group("text").strip()
            if text:
                return Intent("note_make", {"text": text})
    if _NOTE_TEMPLATE_LIST.fullmatch(s):
        return Intent("template_list")
    m = _NOTE_TEMPLATE_SAVE.fullmatch(s)
    if m:
        return Intent("template_save", {"name": m.group("name").strip(),
                                        "tname": (m.group("tname") or "").strip()})
    m = _NOTE_TEMPLATE_CREATE.fullmatch(s)
    if m:
        kind = m.group("kind").replace(" ", "")
        if kind in ("workoutlog",):
            kind = "workout"
        elif kind in ("meetingnotes",):
            kind = "meeting"
        elif kind in ("dailyjournal", "journal"):
            kind = "journal"
        elif kind in ("projectnote",):
            kind = "project"
        return Intent("template_create", {"kind": kind,
                                          "subject": (m.group("subject") or "").strip()})
    m = _NOTE_NEW_SECTION.fullmatch(s)
    if m:
        return Intent("note_customize", {"name": m.group("name").strip(),
                                         "op": "new_section",
                                         "heading": m.group("heading").strip()})
    m = _NOTE_RENAME_HEADING.fullmatch(s)
    if m:
        return Intent("note_customize", {"name": m.group("name").strip(),
                                         "op": "rename_heading",
                                         "old": m.group("old").strip(),
                                         "new": m.group("new").strip()})
    m = _NOTE_SET_PROPERTY.fullmatch(s)
    if m:
        return Intent("note_customize", {"name": m.group("name").strip(),
                                         "op": "set_property",
                                         "key": m.group("key").strip(),
                                         "value": m.group("value").strip()})
    m = _NOTE_REMOVE_PROPERTY.fullmatch(s)
    if m:
        return Intent("note_customize", {"name": m.group("name").strip(),
                                         "op": "remove_property",
                                         "key": m.group("key").strip()})
    m = _NOTE_LINK.fullmatch(s)
    if m:
        return Intent("note_customize", {"name": m.group("name").strip(),
                                         "op": "link",
                                         "note": m.group("target").strip()})
    line_map = [
        (_NOTE_LINE_BULLET, "bullet"), (_NOTE_LINE_ADD_BULLET, "bullet"),
        (_NOTE_LINE_CHECK, "checklist"), (_NOTE_LINE_CHECKBOX, "checklist"),
        (_NOTE_LINE_QUOTE, "quote"), (_NOTE_LINE_NUMBER, "number"),
        (_NOTE_LINE_TICK, "tick"), (_NOTE_LINE_UNTICK, "untick"),
        (_NOTE_LINE_PLAIN, "plain"),
    ]
    for rx, kind in line_map:
        m = rx.fullmatch(s)
        if m:
            text = (m.groupdict().get("text") or m.groupdict().get("text1")
                    or m.groupdict().get("text2") or "").strip()
            return Intent("note_customize", {"name": m.group("name").strip(),
                                             "op": "line", "line_action": kind,
                                             "target": text})
    m = _NOTE_LINE_HEADING.fullmatch(s)
    if m:
        hashes = m.group("hashes") or "##"
        return Intent("note_customize", {"name": m.group("name").strip(),
                                         "op": "line", "line_action": "heading",
                                         "target": m.group("text").strip(),
                                         "level": len(hashes)})
    m = _NOTE_SURGICAL_UNDER.fullmatch(s) or _NOTE_SURGICAL_SECTION.fullmatch(s)
    if m:
        return Intent("note_insert", {"name": m.group("name").strip(),
                                      "target": m.group("head").strip(),
                                      "text": m.group("text").strip(),
                                      "mode": "under_heading"})
    m = _NOTE_SURGICAL_ANCHOR.fullmatch(s)
    if m:
        return Intent("note_insert", {"name": m.group("name").strip(),
                                      "target": m.group("anchor").strip(),
                                      "text": m.group("text").strip(),
                                      "mode": m.group("mode").strip().lower()})
    m = _NOTE_FORMAT_ADD.fullmatch(s)
    if m:
        return Intent("note_format", {"name": m.group("name").strip(),
                                      "target": m.group("target").strip(),
                                      "style": m.group("style").strip().lower(),
                                      "action": "add"})
    m = _NOTE_FORMAT_REMOVE.fullmatch(s)
    if m:
        style = (m.group("style") or m.group("style2") or "").strip().lower()
        return Intent("note_format", {"name": m.group("name").strip(),
                                      "target": m.group("target").strip(),
                                      "style": style, "action": "remove"})
    m = _NOTE_REPLACE.fullmatch(s)
    if m:
        return Intent("note_replace", {"name": m.group("name").strip(),
                                       "old": m.group("old").strip(),
                                       "new": m.group("new").strip()})
    # Only a sentence that actually says "note" is a note append: the same
    # shape is the timer ("add 5 minutes to the timer"), the scheduler
    # ("add a reminder to my phone") and the focus session's ("add 15 minutes
    # to my focus session"), and those own their words. A named list keeps its
    # grammar too ("add milk to my shopping list").
    _says_note = re.search(r"\bnotes?\b", s, re.I) is not None

    def _named_note_exists(name: str) -> bool:
        try:
            path, _why, _title = _find_note(_note_path_for(name))
            return path is not None
        except Exception:                   # noqa: BLE001 - older tree
            return False

    m = _NOTE_APPEND_COLON.fullmatch(s)
    if (m and (_says_note or _named_note_exists(m.group("name")))
            and not _list_owns_name(m.group("name"))):
        return Intent("note_append", {"name": m.group("name").strip(),
                                      "text": m.group("text").strip()})
    m = _NOTE_APPEND_PLAIN.fullmatch(s)
    if (m and (_says_note or _named_note_exists(m.group("name")))
            and not _list_owns_name(m.group("name"))):
        return Intent("note_append", {"name": m.group("name").strip(),
                                      "text": m.group("text").strip()})
    for rx in (_NOTE_CREATE_REFUSED, _NOTE_RENAME_REFUSED, _NOTE_DELETE_REFUSED):
        if rx.match(s):
            return Intent("note_change_refused")
    for rx in _NOTE_READ_PATTERNS:
        if rx.fullmatch(s):
            return Intent("note_read_honest")
    if _VAULT_APPLY.fullmatch(s):
        return Intent("vault_organizer_apply")
    m = _VAULT_SCOPED.match(s)
    if m:
        raw = next((g for g in m.groupdict().values() if g is not None), "")
        return Intent("vault_organizer_scoped",
                      {"names": _organizer_selection(raw)})
    if _VAULT_TIDY.match(s):
        return Intent("vault_organizer_plan")
    if _ORGANIZER_ON.fullmatch(s):
        return Intent("vault_organizer_on")
    if _obsidian_style_refused(s):
        return Intent("obsidian_style_refused")
    return None


def _run_pair_phone() -> Result:
    """The two real screens, in their own words; the PC's Devices card opens as
    a cardless Settings jump (the same navigation `_run_calendar_setup` makes).
    Nothing is paired, changed or typed by saying this."""
    jump = None
    try:
        import jarvis_settings_registry as R
        jump = "devices" if R.section_by_id("devices") is not None else None
    except Exception:                       # noqa: BLE001 - module absent
        jump = None
    return Result(PAIR_PHONE_WORDS, "pair_phone", open_settings=jump)


#: One plain refusal for the three note changes the notes editor deliberately
#: does not have (its catalogue limit says the same in its own words).
NOTE_CHANGE_REFUSAL = (
    "The notes editor does not create, rename or delete notes. It can browse, "
    "search and open any note, and save a change to an existing one. Nothing "
    "was changed.")
#: Chat does not read note text today; the Notes plate is the real door.
NOTE_READ_HONEST = (
    "Chat does not read note text today. The Notes plate in the Brain window "
    "can search, read and open any note, and saving a change there takes one "
    "approval card. Nothing was read or changed.")
#: Obsidian's own theme, style sheets, templates and plugins belong to Obsidian.
#: The hard sentence is the same one the catalogue answers use, so the two paths
#: cannot say different things.
OBSIDIAN_STYLE_REFUSAL = (
    'That is not one of my features on this PC. Jarvis does not change your '
    'Obsidian theme, styles or templates - only Obsidian does that. Open '
    '"Everything Jarvis can do" - Brain, Tutorials and the FAQ - to read the '
    'whole list.')
#: The organizer's own sentence when it cannot be planned at all (module absent).
ORGANIZER_MISSING = (
    "The vault organizer is not installed on this PC, so I did not plan anything.")
ORGANIZER_AWAITING = (
    "One approval card is waiting for your yes. The vault organizer stays off "
    "until you approve it; nothing is planned or changed before then.")
#: The organizer's answer says how the WRITER would behave, in words the module
#: itself uses ("never deletes", "one card"): one card for the whole batch, and
#: no note is ever removed. The apply door is named because the plan is read-only
#: and the owner would otherwise not know what to say next.
ORGANIZER_APPLY_NOTE = (
    "Applying it asks for ONE approval card for the whole batch, and a note is "
    "never deleted. Say \"apply the plan\" when you are ready.")
#: The pick-a-set door (owner decision, 2026-10-31): a selected plan, counts
#: only (safe while the hidden lists are on), one card for the selected batch.
ORGANIZER_SCOPED_OFF = (
    "The vault organizer is off, so nothing is planned. It is off by default "
    "and turning it on is one approval card. Say \"turn on the vault organizer\" "
    "and I will raise that card.")
ORGANIZER_SCOPED_NEEDS_NAMES = (
    "Name the notes to organize, for example \"organize these notes: Welcome, "
    "Alpha\". Nothing was changed.")
ORGANIZER_SCOPED_APPLY_NOTE = (
    "Applying it asks for ONE approval card for the whole selected batch; only "
    "those notes are written, no note is ever deleted, and one Undo restores "
    "exactly that batch. Say \"apply the plan\" when you are ready.")
#: The apply answer when the switch is OFF: its own off truth plus the door.
ORGANIZER_APPLY_OFF = (
    "The vault organizer is off, so there is nothing to apply. It is off by "
    "default and turning it on is one approval card. Say \"turn on the vault "
    "organizer\" and I will raise that card.")


def _note_make_gate(action: str, detail: dict, prompt: str):
    """The note module's own fail-closed gate, plus the outside-text ask.

    `jarvis_note_capture.capture` normally runs under `append_obsidian_daily`
    (tier auto). The ask-after-outside-text rule is the agent's
    `write_notes_after_outside_text` action, which this quick path bypasses by
    design - so the same rule is applied here: when the conversation is latched
    as having read outside text (`jarvis_gate.taint_active`), the card is asked
    under `write_notes_after_outside_text`; when it cannot be read, it is asked
    (the safe direction). The gate call itself stays the module's own
    `_gate_check`, so there is ONE fail-closed wrapper, not a second one.
    """
    try:
        tainted = bool(_gate_module().taint_active())
    except Exception:                       # noqa: BLE001 - cannot tell: ask
        tainted = True
    want = "write_notes_after_outside_text" if tainted else action
    import jarvis_note_capture as NC
    return NC._gate_check(want, detail, prompt)


def _run_note_make(f: dict) -> Result:
    """Write the owner's words into today's Obsidian daily note, through the
    EXISTING capture path: its plan, its File Guardian copy first, its gate and
    its own confirmation/refusal sentences (which name the file)."""
    text = str(f.get("text") or "").strip()
    if not text:
        return Result('What should the note say? Say "make a note: ..." and I '
                      "will add it to today's Obsidian daily note.",
                      "note_make_refused")
    try:
        import jarvis_note_capture as NC
    except Exception:                       # noqa: BLE001 - module absent
        return Result("The note capture is not installed on this PC, so I did "
                      "not write anything.", "note_make_refused")
    try:
        _code, body = NC.capture("obsidian", text, by="chat",
                                 gate_check=_note_make_gate, wait_s=1.5)
    except Exception as exc:                # noqa: BLE001 - said, never swallowed
        return Result(f"The note could not be filed "
                      f"({type(exc).__name__}), so nothing was written.",
                      "note_make_refused")
    body = body if isinstance(body, dict) else {}
    said = str(body.get("message") or "").strip()
    state = str(body.get("state") or "")
    if state == "filed":
        return Result(said or "Filed in Obsidian.", "note_made")
    if state == "waiting":
        return Result(said or "Waiting for your approval.", "note_make_waiting")
    return Result(said or "Not filed, so nothing was written.", "note_make_refused")


def _run_note_change_refused() -> Result:
    """"create/rename/delete a note" - one plain refusal, nothing changed."""
    return Result(NOTE_CHANGE_REFUSAL, "note_change_refused")


def _run_note_read_honest() -> Result:
    """"what does my note say?" - chat does not read note text; say the door."""
    return Result(NOTE_READ_HONEST, "note_read_honest")


def _run_obsidian_style_refused() -> Result:
    """"customize my Obsidian theme/CSS/templates" - not a feature, never was."""
    return Result(OBSIDIAN_STYLE_REFUSAL, "obsidian_style_refused")


def _remember_organizer_plan(body: dict) -> dict:
    """Keep the plan the owner just saw, so "apply the plan" applies THAT one."""
    plan_id = str((body or {}).get("plan_id") or "").strip()
    digest = str((body or {}).get("digest") or "").strip()
    if not plan_id or not digest:
        return {}
    plan = {"plan_id": plan_id, "digest": digest, "at": time.time(),
            "scoped": bool((body or {}).get("scoped")),
            "scope": list((body or {}).get("scope") or [])}
    _ORGANIZER_LAST_PLAN.clear()
    _ORGANIZER_LAST_PLAN.update(plan)
    return plan


def _organizer_plan_body(plan: dict) -> dict:
    """The plan request that reproduces the plan the owner saw.

    A scoped plan must stay scoped through a re-plan (a module restart, or an
    apply more than 30 minutes later); a whole-vault plan sends no paths.
    """
    if plan.get("scoped"):
        return {"paths": list(plan.get("scope") or [])}
    return {}


def _run_vault_organizer_plan(peer=None, local=None) -> Result:
    """The organizer's real state or its READ-ONLY plan - never a promise.

    Off: the module's own route answer (`why`) is quoted, plus that turning it
    on is one card and the plan changes nothing. On: the module's own plan
    description (scheme words and counts) plus how the writer would behave and
    the "apply the plan" door. The plan is remembered in memory so the apply
    answer uses the plan the owner just looked at.
    """
    try:
        import jarvis_vault_organizer as V
    except Exception:                       # noqa: BLE001 - module absent
        return Result(ORGANIZER_MISSING, "vault_organizer_plan")
    try:
        _code, body = V.handle_post(V.PLAN_PATH, {}, peer=peer, local=local)
    except Exception as exc:                # noqa: BLE001 - said, never swallowed
        return Result(f"The vault organizer could not make a plan "
                      f"({type(exc).__name__}), so nothing was changed.",
                      "vault_organizer_plan")
    body = body if isinstance(body, dict) else {}
    if body.get("ok") and str(body.get("said") or "").strip():
        _remember_organizer_plan(body)
        return Result(str(body["said"]).strip() + "\n\n" + ORGANIZER_APPLY_NOTE,
                      "vault_organizer_plan")
    said = str(body.get("why") or body.get("error") or "").strip()
    if not said:
        said = "The vault organizer could not make a plan, so nothing was changed."
    if body.get("enabled") is False:
        # Its own words, unchanged, plus what the owner needs to know next.
        return Result(said + "\n\nThe plan is a dry run: it changes nothing. Say "
                      '"turn on the vault organizer" and I will raise that one '
                      "approval card.", "vault_organizer_plan")
    return Result(said + " Nothing was changed.", "vault_organizer_plan")


def _run_vault_organizer_scoped(f: dict, peer=None, local=None) -> Result:
    """"organize just my Welcome note" - the READ-ONLY scoped plan, not a card.

    The selection is passed to the module's own plan route (`paths`), which
    validates it and plans tags for only those notes. The reply names no note
    title while the app's hidden-lists mode is on (counts only). With the
    organizer OFF the honest off answer and the one-card turn-on door are kept.
    """
    try:
        import jarvis_vault_organizer as V
    except Exception:                       # noqa: BLE001 - module absent
        return Result(ORGANIZER_MISSING, "vault_organizer_scoped")
    if not V.enabled():
        return Result(ORGANIZER_SCOPED_OFF, "vault_organizer_scoped")
    names = [str(n) for n in (f.get("names") or []) if str(n).strip()]
    if not names:
        return Result(ORGANIZER_SCOPED_NEEDS_NAMES, "vault_organizer_scoped")
    hidden, withheld = _calendar_hidden()
    try:
        _code, body = V.handle_post(V.PLAN_PATH, {"paths": names},
                                    peer=peer, local=local)
    except Exception as exc:                # noqa: BLE001 - said, never swallowed
        return Result(f"The vault organizer could not make a scoped plan "
                      f"({type(exc).__name__}), so nothing was changed.",
                      "vault_organizer_scoped")
    body = body if isinstance(body, dict) else {}
    if body.get("ok") and str(body.get("said") or "").strip():
        _remember_organizer_plan(body)
        reply = str(body["said"]).strip() + "\n\n"
        if hidden and withheld:
            # The module's scoped words are counts only; the withheld sentence
            # explains why, and no note title is ever added.
            reply += withheld + "\n\n"
        return Result(reply + ORGANIZER_SCOPED_APPLY_NOTE,
                      "vault_organizer_scoped")
    said = str(body.get("why") or body.get("error") or "").strip()
    if not said:
        said = ("The vault organizer could not plan that selection, so nothing "
                "was changed.")
    if body.get("enabled") is False:
        said += "\n\n" + ORGANIZER_SCOPED_OFF
    return Result(said, "vault_organizer_scoped")


def _run_vault_organizer_apply(peer=None, local=None) -> Result:
    """"apply the plan" / "organize my vault now" - the WRITER's one card.

    The writer route is the module's own (`ORGANIZE_PATH`), with the plan_id and
    digest of the plan the owner just looked at; its words are returned
    unchanged. A denied card returns the module's own denial and writes nothing.
    If no chat plan is remembered (new process, or "organize my vault now"
    first), a read-only plan is made first and then the same writer card is
    raised, so this is still ONE card and never a silent write. A remembered
    SCOPED plan is re-planned with the same selected paths, never widened to
    the whole vault.
    """
    try:
        import jarvis_vault_organizer as V
    except Exception:                       # noqa: BLE001 - module absent
        return Result(ORGANIZER_MISSING, "vault_organizer_apply")
    if not V.enabled():
        return Result(ORGANIZER_APPLY_OFF, "vault_organizer_apply")
    used_stored = bool(_ORGANIZER_LAST_PLAN)
    plan = dict(_ORGANIZER_LAST_PLAN)
    if not plan or time.time() - float(plan.get("at") or 0) > 30 * 60:
        try:
            _code, pbody = V.handle_post(V.PLAN_PATH, _organizer_plan_body(plan),
                                         peer=peer, local=local)
        except Exception as exc:            # noqa: BLE001
            return Result(f"The vault organizer could not make a plan "
                          f"({type(exc).__name__}), so nothing was changed.",
                          "vault_organizer_apply")
        pbody = pbody if isinstance(pbody, dict) else {}
        if not (pbody.get("ok") and _remember_organizer_plan(pbody)):
            said = str(pbody.get("why") or pbody.get("error") or "").strip()
            if not said:
                said = "The vault organizer could not make a plan, so nothing was changed."
            if pbody.get("enabled") is False:
                said += "\n\n" + ORGANIZER_APPLY_OFF
            return Result(said, "vault_organizer_apply")
        plan = dict(_ORGANIZER_LAST_PLAN)
    body = _organizer_apply_once(V, plan, peer, local)
    if not (body.get("ok") is True) and used_stored:
        why = str(body.get("why") or body.get("words") or "").lower()
        if "not in memory" in why or "no longer" in why:
            # The module restarted (or forgot the plan) while this chat kept
            # its copy. Make the same read-only plan again, then raise the
            # writer's one card for it - no second card, no silent write.
            try:
                _code, pbody = V.handle_post(V.PLAN_PATH,
                                             _organizer_plan_body(plan),
                                             peer=peer, local=local)
            except Exception as exc:        # noqa: BLE001
                return Result(f"The vault organizer could not make a plan "
                              f"({type(exc).__name__}), so nothing was changed.",
                              "vault_organizer_apply")
            pbody = pbody if isinstance(pbody, dict) else {}
            if pbody.get("ok") and _remember_organizer_plan(pbody):
                plan = dict(_ORGANIZER_LAST_PLAN)
                body = _organizer_apply_once(V, plan, peer, local)
    if body.get("ok") is True:
        _ORGANIZER_LAST_PLAN.clear()
        return Result(str(body.get("said") or body.get("words")
                          or "The vault organizer finished the plan."),
                      "vault_organizer_apply")
    said = str(body.get("why") or body.get("words") or body.get("error")
               or "").strip()
    if not said:
        said = "The vault organizer did not apply the plan."
    if body.get("enabled") is False:
        said += "\n\n" + ORGANIZER_APPLY_OFF
    return Result(said, "vault_organizer_apply")


def _organizer_apply_once(V, plan: dict, peer=None, local=None) -> dict:
    """One call to the module's WRITER route, which raises its ONE card."""
    try:
        _code, body = V.handle_post(
            V.ORGANIZE_PATH,
            {"plan_id": str(plan.get("plan_id") or ""),
             "digest": str(plan.get("digest") or "")},
            peer=peer, local=local)
    except Exception as exc:                # noqa: BLE001 - said, never swallowed
        return {"ok": False,
                "why": f"the writer could not run ({type(exc).__name__}), "
                       f"so nothing was changed"}
    return body if isinstance(body, dict) else {}


def _run_vault_organizer_on(peer=None, local=None) -> Result:
    """"turn on the vault organizer" - the module's existing change_own_config
    card, one of them; the switch itself is applied only after the owner's yes."""
    try:
        import jarvis_vault_organizer as V
    except Exception:                       # noqa: BLE001 - module absent
        return Result(ORGANIZER_MISSING, "vault_organizer_on")
    try:
        _code, body = V.handle_post(V.SWITCH_PATH, {"enabled": True},
                                    peer=peer, local=local)
    except Exception as exc:                # noqa: BLE001 - said, never swallowed
        return Result(f"The vault organizer's card could not be raised "
                      f"({type(exc).__name__}), so nothing changed.",
                      "vault_organizer_on")
    body = body if isinstance(body, dict) else {}
    if body.get("waiting"):
        return Result(ORGANIZER_AWAITING, "vault_organizer_on")
    if body.get("enabled") is True:
        return Result(str(body.get("message") or "The vault organizer is already on."),
                      "vault_organizer_on")
    said = str(body.get("error") or "").strip()
    if not said:
        said = "The vault organizer could not be turned on."
    return Result(said if said.endswith(".") else said + ".", "vault_organizer_on")
#: What "open the Brain / open Jarvis settings" says when the owner is talking
#: from the PHONE (2026-10-31, the surface requirement). The phone cannot open
#: a window on the PC; its own Brain and Settings are real doors in its own app,
#: so the answer names those and says where the PC's window opens. No new
#: route, no new field - these are the two apps' own names ("Brain" in the
#: phone's bottom row, "Settings" beside it).
PHONE_OPEN_WORDS = {
    "brain": ("You are asking from the phone. The Brain is in the phone app: tap Brain on "
              "Home. The PC's own Brain window opens on the PC."),
    "jarvis": ("You are asking from the phone. Your phone's own settings are in the app: tap "
               "Settings on Home. The PC's Jarvis settings window opens on the PC - ask me "
               "there for the PC's settings."),
}

#: What "can I edit the HUD in the jarvis app?" says from the PHONE (2026-10-31,
#: the owner's screenshot: the model had answered "Jarvis does not currently
#: offer a built-in method...", which is false about the product - the HUD's
#: layout is edited on the PC, where the doors below really exist). The phone
#: has no HUD-layout control; its own look is Appearance, and every thing named
#: here is an existing door of one app or the other - no route is invented.
HUD_EDIT_PHONE = (
    "The HUD's layout is edited on the PC, not from the phone app: on the desktop, "
    "Settings has \"Edit HUD in the window\", and the HUD's own header has \"Edit HUD\". "
    "What you can change here on the phone is this app's own look - Appearance, for the "
    "theme, the face, face size, text size and spacing.")

#: Matches the questions the owner asks about changing the HUD's layout/look.
#: Deliberately narrow: a sentence about the HUD that is not about editing it
#: ("what is the HUD?") keeps its existing path (the feature guide).
_HUD_EDIT = re.compile(
    r"(?:(?:can|could|how\s+do|how\s+can|how\s+do\s+i|where\s+do\s+i|where\s+can\s+i|"
    r"i\s+want\s+to|i'?d\s+like\s+to|let\s+me)\s+)?(?:i\s+)?"
    r"(?:edit|change|customi[sz]e|adjust|move|rearrange|redesign)\s+"
    r"(?:the\s+|my\s+|this\s+)?(?:jarvis\s+)?(?:hud|heads?[-\s]?up\s+display)"
    r"(?:\s+(?:layout|look|arrangement|widgets?|plates?))?"
    r"(?:\s+(?:in|on|from)\s+(?:the\s+)?(?:jarvis\s+app|this\s+app|my\s+phone|android))?"
    r"|(?:the\s+|my\s+)?(?:jarvis\s+)?hud(?:'s)?\s+layout"
    r"(?:\s+(?:in|on|from)\s+(?:the\s+)?(?:jarvis\s+app|this\s+app|my\s+phone|android))?")


def _hud_edit(s: str) -> Optional[Intent]:
    """"can I edit the HUD in the jarvis app?" - answered ONLY from the phone.

    With no header (or from the desktop) this returns None and the old path is
    unchanged: the owner's requirement is that the PHONE's answer be true, and
    the desktop already has the doors this sentence names. Answering nothing
    new elsewhere is the no-over-capture half.
    """
    if not _HUD_EDIT.fullmatch(s):
        return None
    try:
        import jarvis_surface as S
    except Exception:
        return None
    return Intent("hud_edit") if S.current() == S.PHONE else None


# --- notes: read and search (2026-10-31, the owner's "read & search" half) ---
#
# Deterministic, read-only, no card and no model: the answers come from
# jarvis_notes_edit.chat_* which read the SAME vault files the editor routes
# read, under the same hidden-folder, protection and size rules. The hidden
# rule is jarvis_private_view, the backend's one hook: with the lists hidden
# this says so and shows neither a title nor a word of a note.

NOTES_READ_HIDDEN = ("The memory lists and chat history are hidden on this PC right now, "
                     "so I will not show a note's words.")
NOTES_SEARCH_HIDDEN = ("The memory lists and chat history are hidden on this PC right now, "
                       "so I will not list note titles.")
NOTES_ONE_AT_A_TIME = "I can read one note at a time; tell me which one."
NOTES_SEARCH_DOOR = "You can search the whole vault in the notes editor on this PC."


def _notes_hidden() -> bool:
    try:
        import jarvis_private_view as PV
        state = PV.effective()
        return bool(state.get("app_locked") or state.get("hide_memory_lists"))
    except Exception:
        return False


_NOTE_READ_MY = re.compile(r"read\s+my\s+note\s+(.+)")
_NOTE_READ = re.compile(
    r"(?:what\s+does|what\s+is\s+in|what'?s\s+in|read\s+me|read|show\s+me)\s+"
    r"(?:my\s+)?(.+?)\s+note(?:\s+(?:say|says|contain|contains))?$")
_NOTE_READ_PLURAL = re.compile(r"(?:read|show)\s+(?:me\s+)?my\s+notes?\s*$")
_NOTE_OPEN_ALT = re.compile(r"open\s+(?:my\s+)?note\s+(.+)")
_NOTE_OPEN = re.compile(
    r"open\s+(?:my\s+|the\s+)?(.+?)\s+note(?:\s+in\s+the\s+notes?\s+editor)?$")
_NOTE_MENTION = re.compile(r"which\s+notes?\s+mention\s+(.+)")
_NOTE_SEARCH = re.compile(
    r"(?:find|search|show|list|any)\s+(?:me\s+)?(?:my\s+)?notes?\s+"
    r"(?:about|for|mentioning|mention|on)\s+(.+)")


def _notes_chat(s: str) -> Optional[Intent]:
    """The three note questions this file answers without a model."""
    if _NOTE_READ_PLURAL.fullmatch(s):
        return Intent("note_read", {"title": ""})
    m = _NOTE_READ_MY.fullmatch(s) or _NOTE_READ.fullmatch(s)
    if m:
        return Intent("note_read", {"title": m.group(1).strip(" \"'")})
    m = _NOTE_OPEN_ALT.fullmatch(s) or _NOTE_OPEN.fullmatch(s)
    if m:
        return Intent("note_open", {"title": m.group(1).strip(" \"'")})
    m = _NOTE_MENTION.fullmatch(s) or _NOTE_SEARCH.fullmatch(s)
    if m:
        return Intent("note_search", {"needle": m.group(1).strip(" \"'")})
    return None


def _run_note_read(title: str) -> Result:
    if _notes_hidden():
        return Result(NOTES_READ_HIDDEN, "note_read")
    try:
        import jarvis_notes_edit as NE
        code, body = NE.chat_read_note(title)
    except Exception:
        return Result("The notes could not be read on this PC.", "note_read")
    if code == 409:
        titles = "; ".join(body.get("titles") or [])
        said = NOTES_ONE_AT_A_TIME + (" " + titles if titles else "")
        return Result(said, "note_read")
    if code != 200:
        return Result(str(body.get("said") or NE.CHAT_NO_NOTE.format(title)), "note_read")
    said = '"{0}" says:\n\n{1}'.format(body["title"], body["text"])
    if body.get("more"):
        said += "\n\n\u2026and {0} more characters.".format(body["more"])
    return Result(said, "note_read")


def _run_note_search(needle: str) -> Result:
    try:
        import jarvis_notes_edit as NE
        code, body = NE.chat_search_notes(needle)
    except Exception:
        return Result("The notes could not be searched on this PC.", "note_search")
    if code != 200:
        return Result(str(body.get("said") or "The notes could not be searched."), "note_search")
    count = int(body.get("count") or 0)
    if _notes_hidden():
        if count == 0:
            return Result(NOTES_SEARCH_HIDDEN + " No notes match.", "note_search")
        return Result(NOTES_SEARCH_HIDDEN + " {0} note(s) match.".format(count), "note_search")
    if count == 0:
        return Result('No notes in your vault match "{0}". {1}'.format(
            str(needle or "").strip(), NOTES_SEARCH_DOOR), "note_search")
    titles = "; ".join(body.get("titles") or [])
    said = '{0} note(s) match "{1}": {2}.'.format(
        count, str(needle or "").strip(), titles)
    shown = len(body.get("titles") or [])
    if count > shown:
        said += " I have shown the first {0}.".format(shown)
    if body.get("capped"):
        said += " I looked through the first {0} notes.".format(int(body.get("scanned") or 0))
    return Result(said, "note_search")


def _run_note_open(title: str) -> Result:
    if _notes_hidden():
        return Result(NOTES_READ_HIDDEN, "note_open")
    try:
        import jarvis_notes_edit as NE
        code, body = NE.chat_open_note(title)
    except Exception:
        return Result("The notes could not be read on this PC.", "note_open")
    if code != 200:
        return Result(str(body.get("said") or NE.CHAT_NO_NOTE.format(title)), "note_open")
    said = ('Opening the Brain on this PC. Your notes are under Notes - look for '
            '"{0}" there.'.format(body["title"]))
    return Result(said, "note_open", open_brain="brain")


def _open(s: str) -> Optional[Intent]:
    """"open Notion", "open settings", "open Jarvis settings" (jarvis_open.py,
    the owner's request of 2026-10-10), and Jarvis's own windows and places
    ("open the second brain", "open history", "open tutorials", "open my
    notes", 2026-10-31).

    The grammar lives in that module and this only asks it - one place decides
    what the owner's words name, so the desktop and the phone cannot drift
    apart over it. A phrase it cannot place (anything that is not an "open
    ..." sentence) falls through to the model exactly as before.
    """
    try:
        import jarvis_open as OPEN
    except Exception:
        return None
    got = OPEN.parse(s)
    if got is None:
        return None
    what, is_jarvis = got
    opened = OPEN.resolve(what, is_jarvis)
    return Intent("open_app", {"opened": opened})


def _run_notion(f: dict) -> Result:
    """"Can you process all my Notion notes into Obsidian?", and "import my
    Notion export" on its own (2026-10-28). Fixed text, from the constants
    above - which the test holds to the real module, route and button. Reads
    nothing, changes nothing, opens no card: the .zip is chosen with this PC's
    own file picker, so there is nothing here that could do the import."""
    return Result(NOTION_PICK_WORDS if f.get("step") == "import" else NOTION_WORDS,
                  "notion_export")


def _run_sayable(intent: Intent) -> Result:
    """"Things you can say" (jarvis_sayable.py), said in one answer for "what
    can you do?" and close phrasings. No model, reads no state."""
    try:
        import jarvis_sayable
        return Result(jarvis_sayable.sentence(), intent.name)
    except Exception:
        return Result(SAYABLE_MISSING, intent.name)


def _run_reach(intent: Intent) -> Result:
    """The list both apps show under "What Jarvis can reach", said in one
    answer - written by jarvis_reach.py from the PC's settings. Reads only."""
    try:
        import jarvis_reach
        return Result(jarvis_reach.sentence(), intent.name)
    except Exception:
        return Result(REACH_MISSING, intent.name)


def _run_identity(intent: Intent) -> Result:
    """"Who are you?" and close phrasings (jarvis_identity.py): fixed text,
    no model, no romance. Reads no state, changes nothing."""
    try:
        import jarvis_identity
        return Result(jarvis_identity.sentence(), intent.name)
    except Exception:
        return Result(IDENTITY_MISSING, intent.name)


# --------------------------------------------------------------------------
#   Music and video control on this PC (jarvis_media.py, feasibility I91,
#   the owner's decision of 2026-09-27: "no card, only from the owner's own
#   words") - play, pause, next, previous and "what's playing", never a
#   model tool: the AI model cannot ask for this on its own initiative, and
#   it never appears from outside text (a web page, an email). Whole
#   sentences only, and each requires the media word ("pause", bare, is the
#   focus session's while one is running, checked above this in _match).
# --------------------------------------------------------------------------

_MEDIA_OBJ = r"(?:this\s+|the\s+)?(?:music|song|track|video|media|playback)"
_MEDIA_PAUSE = re.compile(r"pause\s+" + _MEDIA_OBJ)
_MEDIA_PLAY = re.compile(r"(?:play|resume|unpause|continue)\s+" + _MEDIA_OBJ)
_MEDIA_NEXT = re.compile(r"(?:skip|next)\s+(?:this\s+|the\s+)?(?:song|track|video)"
                         r"|skip\s+(?:it|this|that)|play\s+the\s+next\s+(?:song|track)"
                         r"|next\s+(?:song|track)\s+please")
_MEDIA_PREV = re.compile(r"(?:previous|last|go\s+back\s+a)\s+(?:song|track|video)"
                         r"|play\s+the\s+previous\s+(?:song|track)")
_MEDIA_NOW = re.compile(r"(?:what'?s|what\s+is)\s+playing(?:\s+(?:right\s+)?now)?"
                        r"|now\s+playing|what\s+(?:song|track)\s+is\s+(?:this|playing|on)")


def _media(s: str) -> Optional[Intent]:
    if _MEDIA_PAUSE.fullmatch(s):
        return Intent("media_pause")
    if _MEDIA_PLAY.fullmatch(s):
        return Intent("media_play")
    if _MEDIA_NEXT.fullmatch(s):
        return Intent("media_next")
    if _MEDIA_PREV.fullmatch(s):
        return Intent("media_previous")
    if _MEDIA_NOW.fullmatch(s):
        return Intent("media_now")
    return None


MEDIA_MISSING = ("Your PC's Jarvis cannot control music or video yet - run apply-patches.ps1 "
                 "on the PC.")


# --------------------------------------------------------------------------
#   "find cheap parking near ..." (jarvis_parking.py, 2026-10-30)
# --------------------------------------------------------------------------
#
# THE OWNER'S ASK: "find me cheap parking near Pike Place Market tomorrow from
# 4:15 PM to 9:00 PM". It is answered here rather than by the model because the
# arithmetic is exact and a model's is not: a sign's rates are a set of time
# windows, and quoting one rate for the whole stay is how a $9.38 curb becomes a
# $21.38 garage. All of the pricing lives in `jarvis_parking.py`; this section
# only recognises the sentence and hands it a place and a window.
#
# NO MODEL TOOL. The blueprint that asked for this (2026-10-29) wanted a
# `find_parking` tool with a switch, off by default. It is deliberately not
# added: `jarvis_agent.py`'s tool list is the six-slot Live budget on the 8 GB
# card, and a sentence this grammar answers needs no slot at all. A model tool
# would be a separate change with its own budget line.
#
# WHAT THE DEVICE GETS. The PC's own screen gets the full breakdown - every
# legal option and its minute-by-minute maths. A request that plainly did NOT
# come from this PC gets the short form: two options, a `geo:` link each, and
# not one desktop-only phrase. `answer_turn(client_surface=...)` can say which
# outright; otherwise the answer is inferred with
# `jarvis_owner_check.from_this_pc`, the same function every PC-only action
# already uses, because `/api/chat`'s body carries no client kind and this path
# never sees the `X-Jarvis-Client` header. That is said plainly here rather
# than claimed as a header check it does not do.

_PARKING_LEAD = re.compile(
    r"^(?:(?:can|could|would)\s+you\s+(?:please\s+)?)?(?:please\s+)?"
    r"(?:(?:find|get|show|give)\s+(?:me\s+)?"
    r"|where\s+(?:is|are)\s+(?:the\s+|there\s+|some\s+)?"
    r"|is\s+there\s+(?:any\s+|a\s+|some\s+)?"
    r"|how\s+(?:much|expensive)\s+is\s+(?:the\s+)?"
    r"|what\s+is\s+(?:the\s+)?|what's\s+(?:the\s+)?)?"
    r"(?:(?:the|a|an|any|some)\s+)?"
    r"(?:(?:cheapest|cheap|free|closest|nearest)\s+)?(?:legal\s+)?"
    r"parking(?:\s+(?:lot|lots|garage|garages|space|spaces))?\s*")

_PARKING_CALENDAR = re.compile(
    r"^(?:for\s+)?my\s+(?:next\s+)?(?:meeting|event|appointment|calendar\s+event)"
    r"(?:\s+(?:at|near|in|by)\s+(?P<place>.+))?$")

_PARKING_RANGE = re.compile(
    r"^(?P<place>.+?)\s+(?:from|between)\s+(?P<a>.+?)\s+"
    r"(?:to|and|until|till|through)\s+(?P<b>.+)$")
_PARKING_AT_FOR = re.compile(
    r"^(?P<place>.+?)\s+at\s+(?P<a>.+?)\s+for\s+(?P<dur>.+)$")
_PARKING_FOR = re.compile(r"^(?P<place>.+?)\s+for\s+(?P<dur>.+)$")

#: A day phrase at the END of a place ("pike place market tomorrow") or of an
#: end time ("9 pm on thursday"). It is moved into the time text, where
#: `parse_when` already knows what to do with it.
_PARKING_TAIL_DAY = re.compile(
    r"^(?P<rest>.+?)\s+(?P<day>(?:on\s+)?(?:today|tomorrow|tonight|next\s+" + _WD +
    r"|" + _WD + r"))$")

_PARKING_LEAD_PREP = re.compile(r"^(?:near|around|by|in|at|for|to)\s+")

#: A place is a name, not a paragraph. Anything longer is not a sentence this
#: grammar should be pricing.
_PARKING_MAX_PLACE = 80


def _parking_split_day(text: str) -> tuple:
    """"pike place market tomorrow" -> ("pike place market", "tomorrow")."""
    text = str(text or "").strip()
    m = _PARKING_TAIL_DAY.fullmatch(text)
    if m and m.group("rest").strip():
        return m.group("rest").strip(), m.group("day").strip()
    return text, ""


def _parking_place(text: str) -> Optional[str]:
    """The place out of what the owner said, or None when there is not one."""
    place, _day = _parking_split_day(text)
    place = _PARKING_LEAD_PREP.sub("", place).strip(" ,;")
    # "the parking situation near X", "parking prices at X": the noun after
    # "parking" is the owner's subject, not part of the place.
    place = re.sub(r"^(?:situation|options?|prices?|costs?|rates?|fees?)\s+", "", place)
    place = re.sub(r"\s+", " ", place)
    if not place or len(place) > _PARKING_MAX_PLACE or not re.search(r"[a-z]", place):
        return None
    # "near me" is not answered here: this PC has no idea where the owner is
    # standing, and a guessed point would be a wrong answer rather than a
    # missing one. The sentence falls through to the model, which can ask.
    if place in ("me", "here", "there", "this", "that", "it"):
        return None
    return place


def _parking_clock_at(text: str, now: float) -> Optional[float]:
    """The next time `text` names, as an epoch. None if it names no time."""
    got = parse_when(text, now, "reminder")
    if got is None or got.rule is not None:
        return None
    return got.at


def _parking_end_after(text: str, start: float) -> Optional[float]:
    """The first time the clock in `text` reads AFTER `start`.

    The day it lands on is the start's own day when that is still ahead, else
    the next one - so "from 10 pm to 2 am" is four hours, not minus twenty.
    """
    import datetime as _dt
    c = parse_clock(text)
    if c is None:
        return None
    started = _dt.datetime.fromtimestamp(start)
    best: Optional[float] = None
    for hours in _hour24(c, None):
        for add in (0, 1):
            day = started + _dt.timedelta(days=add)
            try:
                moment = day.replace(hour=hours, minute=c.mm, second=0, microsecond=0)
            except ValueError:                      # pragma: no cover - DST edge
                continue
            if moment > started and (best is None or moment.timestamp() < best):
                best = moment.timestamp()
    return best


def _parking_window(place_text: str, now: float):
    """"pike place from 4:15 pm to 9 pm" -> (place, start epoch, end epoch).

    None when the sentence says no place, or a window that is not a window. A
    sentence with NO time at all is the next two hours, and the answer always
    says which window it used - so a default is visible rather than silent.
    """
    body = place_text.strip()
    _place, day = _parking_split_day(body)

    for pattern in (_PARKING_RANGE, _PARKING_AT_FOR, _PARKING_FOR):
        m = pattern.fullmatch(body)
        if m is None:
            continue
        inner_place, inner_day = _parking_split_day(m.group("place"))
        day = day or inner_day
        if pattern is _PARKING_RANGE:
            end_text, end_day = _parking_split_day(m.group("b"))
            # The day word belongs to the WHOLE window, whichever end of it the
            # owner put it on: "from 4 to 9 on friday" is one Friday evening,
            # not 4 PM today and 9 AM on the next Friday. So when the end
            # carries the day, the start is resolved against it too, and the
            # end is then the same day's clock (or the next day's, for a window
            # that crosses midnight - "from 10 pm to 2 am").
            start_day = day or inner_day or end_day
            start_text = (start_day + " " + m.group("a")).strip() if start_day else m.group("a")
            start = _parking_clock_at(start_text, now)
            if start is None:
                continue
            end = _parking_end_after(end_text, start)
        elif pattern is _PARKING_AT_FOR:
            start_text = (day + " " + m.group("a")).strip() if day else m.group("a")
            start = _parking_clock_at(start_text, now)
            if start is None:
                continue
            length = parse_duration(m.group("dur"))
            # `parse_duration` answers in SECONDS (its own docstring), and the
            # epoch arithmetic here is in seconds too - no unit change.
            end = start + length if length else None
        else:
            # "parking near X for 3 hours": no start time said, so it is now.
            start = now
            length = parse_duration(m.group("dur"))
            end = start + length if length else None
        if end is None or end <= start:
            continue
        good = _parking_place(inner_place)
        if good is None:
            return None
        return good, start, end

    # No time said at all: the next two hours, said back in the answer.
    good = _parking_place(body)
    if good is None:
        return None
    return good, now, now + 2 * 3600.0


def _parking_lookup(s: str, now: Optional[float] = None) -> Optional[Intent]:
    """"find cheap parking near X from A to B" and its close phrasings."""
    now = time.time() if now is None else now
    m = _PARKING_LEAD.match(s)
    if m is None:
        return None
    rest = s[m.end():].strip()
    if not rest:
        return None
    # "free parking" is a wish, not a different sentence: it only changes what
    # the answer says when nothing free was found.
    wants_free = bool(re.search(r"\bfree\b", s[:m.end()]))

    calendar = _PARKING_CALENDAR.fullmatch(rest)
    if calendar is not None:
        place = _parking_place(calendar.group("place") or "") or ""
        return Intent("parking_calendar", {"place": place, "wants_free": wants_free})

    # A place is named AFTER a preposition: "parking NEAR pike place",
    # "parking AT the airport", "parking FOR two hours near ...". Without one,
    # the words after "parking" are the owner's SUBJECT and not a place -
    # "what is a parking minimum" must not become a lookup for "minimum" - so
    # the sentence goes to the model, which can ask him what he means.
    if _PARKING_LEAD_PREP.match(rest) is None:
        return None

    got = _parking_window(rest, now)
    if got is None:
        return None
    place, start, end = got
    return Intent("parking_lookup", {"place": place, "start": start, "end": end,
                                     "wants_free": wants_free})


def _client_surface(peer, local, given: Optional[str] = None) -> str:
    """Which words an answer should use: "hud" or "phone".

    THE HEADER WINS WHEN IT IS THERE (2026-10-31, the owner's "Jarvis knows
    which app I am talking from" requirement): the shipped origin gate reads
    `X-Jarvis-Surface` once per request into `jarvis_surface`, so a request
    that says it is the Android app gets the phone's words and a request that
    says it is the desktop program gets the PC's. `given` still wins over both
    (the tests, and a future caller that really knows).

    Otherwise a request that plainly did NOT come from this PC gets the
    phone's short form - `jarvis_owner_check.from_this_pc` is the project's own
    answer to "is this the PC", with its documented "cannot be placed counts as
    this PC" rule, so nothing here is stricter or looser than every PC-only
    action already is. A path that cannot ask at all gets the fuller answer: a
    shorter one might drop something a client needed, and a longer one never
    breaks a client. With no header anywhere, the old inference is unchanged.
    """
    if given:
        return "phone" if str(given).strip().lower() == "phone" else "hud"
    try:
        import jarvis_surface as S
        surface = S.current()
        if surface == S.PHONE:
            return "phone"
        if surface == S.DESKTOP:
            return "hud"
    except Exception:
        pass
    try:
        import jarvis_owner_check as OC
        if OC.from_this_pc(peer, local) is False:
            return "phone"
    except Exception:
        pass
    return "hud"


PARKING_MISSING = ("Your PC's Jarvis cannot look up parking yet - run apply-patches.ps1 "
                   "on the PC, which copies jarvis_parking.py.")

#: Why the parking lane does not look while Lockdown is on (the privacy audit
#: of 2026-10-30): Lockdown makes every way out of this PC ask first or stop,
#: and the parking lookup has three public services and no card of its own, so
#: it stops instead of asking.
PARKING_LOCKDOWN_WORDS = (
    "Lockdown is on, so I am not sending your parking question to a map "
    "service. Turn Lockdown off (on the PC, Settings, What asks first), or "
    "give me a latitude and longitude.")


def _parking_lockdown_on() -> bool:
    """Lockdown (jarvis_asks_first.py): False without that module; True if it
    cannot be read - a lookup that cannot tell does not look."""
    try:
        import jarvis_asks_first
    except Exception:
        return False
    try:
        return bool(jarvis_asks_first.lockdown_on())
    except Exception:
        return True


def _run_parking(intent: Intent, client_surface: str = "hud",
                 now: Optional[float] = None) -> Result:
    """Price the stay, in the words the device that asked can use."""
    if _parking_lockdown_on():
        return Result(PARKING_LOCKDOWN_WORDS, intent.name)
    import datetime as _dt
    try:
        import jarvis_parking as P
    except Exception:
        return Result(PARKING_MISSING, intent.name)
    moment = _dt.datetime.fromtimestamp(time.time() if now is None else now)
    surface = "phone" if str(client_surface).lower() == "phone" else "hud"

    if intent.name == "parking_calendar":
        try:
            event = P.next_event_with_a_place(now=moment)
        except Exception:
            event = None
        if event is None:
            return Result(
                "I could not find a calendar event in the next day that has a "
                "place on it, so there is nowhere to price. Tell me where and "
                "when instead, like \"parking near Pike Place from 4 pm to 9 pm\".",
                intent.name)
        start, end = P.event_window(event)
        result = None
        coordinates = P.looks_like_coordinates(event["where"])
        if coordinates is not None:
            # The location already IS a point, so nothing needs looking up and
            # the one-step answer is available.
            result = P.find_parking(None, start, end, lat=coordinates[0],
                                    lon=coordinates[1], label=event["where"],
                                    wants_free=bool(intent.f.get("wants_free")))
        else:
            # A place the OWNER said in the same sentence ("... for my next
            # meeting at Pike Place") is his own words, so it may be looked up
            # exactly as any other sentence of his. The calendar's own location
            # line is still not sent anywhere - that is the module's rule.
            said = str(intent.f.get("place") or "").strip()
            if said:
                result = P.find_parking(said, start, end,
                                        wants_free=bool(intent.f.get("wants_free")))
        words = P.calendar_words(result, event, client_surface=surface)
        # The reply quotes the calendar's own location line, so this turn counts
        # as having read outside text - the conservative direction, and the same
        # rule a briefing that quotes event titles follows.
        return Result(words, intent.name, read=["calendar_read"])

    place = str(intent.f.get("place") or "").strip()
    if not place:
        return Result("I did not catch where to look for parking.", intent.name)
    base = time.time() if now is None else now
    start = _dt.datetime.fromtimestamp(float(intent.f.get("start") or base))
    end = _dt.datetime.fromtimestamp(float(intent.f.get("end") or (base + 7200)))
    result = P.find_parking(place, start, end,
                            wants_free=bool(intent.f.get("wants_free")))
    return Result(P.reply(result, client_surface=surface), intent.name)


# ---------------------------------------------------------------------------
#   "Send me the file ..." - the chat door for jarvis_send_file (2026-10-31)
# ---------------------------------------------------------------------------
# THE OWNER'S ASK, measured on the live backend: the send-file feature is built
# (routes, card, phone UI), and `send_file_to_phone` IS a model tool - but it is
# not in the shipped [tools].enabled, so the owner could not ask for it from
# chat at all. These whole-sentence shapes call the MODULE'S OWN prepare(), so
# the search, the one-card rule and every refusal are the module's; this file
# only decides that the sentence was a file-send request.
SEND_FILE_UNAVAILABLE = ("Sending a file to your phone is not available on this PC "
                         "yet - run apply-patches.ps1 on the PC.")
SEND_FILE_NOT_A_CARD = ("The file was ready, but the approval card could not be "
                        "raised, so nothing was sent.")
SEND_FILE_SAID = " Nothing is sent until you approve the card."
#: The module's own gate action, written once and resolved against the module at
#: call time, so a renamed constant cannot silently split the two.
SEND_FILE_ACTION = "send_file_to_phone"
#: Whole sentences only, and the file name is required. The explicit "file" /
#: from-folder / to-my-phone markers are what keep ordinary "send an email to
#: Sam", "send me a message" and "send my regards" the model's.
_SEND_FILE_FIND = re.compile(
    r"^(?:please\s+)?find\s+(?:the\s+)?(?P<file>file\s+)?(?P<q>.+?)\s+and\s+send\s+"
    r"(?:it|the file|that file)(?:\s+to\s+me)?(?:\s+to\s+my\s+(?:phone|android))?$",
    re.I)
_SEND_FILE_TO_PHONE = re.compile(
    r"^(?:please\s+|can\s+you\s+|could\s+you\s+)?send\s+(?:me\s+)?(?:the\s+)?"
    r"(?P<file>file\s+)?(?P<q>.+?)"
    r"(?:\s+from\s+(?:my|the)\s+(?P<where>downloads|documents|desktop))?"
    r"\s+to\s+my\s+(?:phone|android)(?:\s+(?:app|jarvis\s+app))?$", re.I)
_SEND_FILE_FROM = re.compile(
    r"^(?:please\s+|can\s+you\s+|could\s+you\s+)?send\s+(?:me\s+)?(?:the\s+)?"
    r"(?P<file>file\s+)?(?P<q>.+?)\s+from\s+(?:my|the)\s+"
    r"(?P<where>downloads|documents|desktop)(?:\s+folder)?$", re.I)
_SEND_FILE_ME = re.compile(
    r"^(?:please\s+|can\s+you\s+|could\s+you\s+)?send\s+(?:me\s+)?(?:the\s+)?file\s+"
    r"(?P<q>.+)$", re.I)
#: Things "send <object>" can mean that are NOT a file. Exact objects only: a
#: real filename that happens to contain one of these words is still accepted.
_BLOCKED_FILE_OBJECTS = frozenset({
    "a message", "message", "messages", "a text", "text", "a note", "note",
    "an email", "email", "e-mail", "mail", "my regards", "regards", "thanks",
    "love", "a reminder", "reminder", "a todo", "todo", "a link", "link",
    "it", "this", "that", "a photo", "photo", "a picture", "picture",
})


def _send_file_query_ok(q: str, *, named_folder: bool = False,
                        explicit_file: bool = False) -> bool:
    """Whether what follows "send ..." really names ONE file to look for."""
    q = str(q or "").strip().strip("'\"")
    if not q or len(q) > 120:
        return False
    low = " ".join(q.casefold().split())
    if low in _BLOCKED_FILE_OBJECTS:
        return False
    if re.fullmatch(r"(?:the\s+|a\s+|an\s+|my\s+)?(?:file|document)s?", low):
        return False
    # A shape with no explicit "file" word needs a filename (a dot) or a named
    # source folder; otherwise "send the meeting notes to my phone" is the
    # model's sentence, not a file search.
    if not (named_folder or explicit_file) and not re.search(r"\.\w{1,10}$", low):
        return False
    return True


def _send_file_intent(q: str, *, named_folder: bool = False,
                      explicit_file: bool = False) -> Optional[Intent]:
    q = str(q or "").strip().strip("'\"")
    if not _send_file_query_ok(q, named_folder=named_folder,
                               explicit_file=explicit_file):
        return None
    return Intent("send_file", {"query": q})


def _send_file(s: str) -> Optional[Intent]:
    """The chat door: a file-send sentence, or None (the model has it)."""
    m = _SEND_FILE_FIND.fullmatch(s)
    if m is not None:
        return _send_file_intent(m.group("q"),
                                 explicit_file=bool(m.group("file")))
    m = _SEND_FILE_TO_PHONE.fullmatch(s)
    if m is not None:
        return _send_file_intent(m.group("q"),
                                 named_folder=bool(m.group("where")),
                                 explicit_file=bool(m.group("file")))
    m = _SEND_FILE_FROM.fullmatch(s)
    if m is not None:
        return _send_file_intent(m.group("q"), named_folder=True,
                                 explicit_file=bool(m.group("file")))
    m = _SEND_FILE_ME.fullmatch(s)
    if m is not None:
        return _send_file_intent(m.group("q"), explicit_file=True)
    return None


def _send_file_tier() -> str:
    """The tier `What asks first` has for the card, read before it is raised.

    An unreadable framework answers "ask" - the same safe default every other
    card path uses: a card is never turned into an automatic action here.
    """
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(SEND_FILE_ACTION))
    except Exception:
        return "ask"


def _send_file_card_thread(SEND, action: str, state: dict, card: str, gate) -> None:
    """Wait for the owner's answer; on a yes only, run the module's approve().

    Nothing else happens here: a denied, refused or timed-out card leaves the
    candidate unapproved, and it ages out on the module's own ten-minute rule.
    """
    try:
        verdict = gate(action, {"text": card}, card)
    except Exception:
        return
    if not getattr(verdict, "allowed", False):
        return
    try:
        SEND.approve(state or {})
    except Exception:
        return


def _run_send_file_chat(f: dict, *, prepare=None, gate=None, tier_of=None,
                        spawn=None) -> Result:
    """The chat door's runner: the module searches, words and refuses; we ask.

    `prepare` is `jarvis_send_file.prepare` itself: exactly one allowed file
    returns its state plus the ONE card's own sentence; no match, several
    matches, a protected or outside file and an over-cap file raise its own
    `ValueError`, which is returned to the owner WORD FOR WORD with no card.
    The card is raised under the module's own action, with the module's own
    card words as the prompt. This function never approves: only an approved
    verdict reaches the module's own `approve()`.
    """
    try:
        import jarvis_send_file as SEND
    except Exception:
        return Result(SEND_FILE_UNAVAILABLE, "send_file")
    action = str(getattr(SEND, "ACTION", SEND_FILE_ACTION))
    tier_of = tier_of or _send_file_tier
    try:
        tier = tier_of(action)
    except Exception:
        tier = "ask"
    if tier != "ask":
        return Result(
            "Sending a file to your phone needs a person to say yes, and it is "
            f"set to {tier!r} in What asks first, so I did not raise a card. "
            "Nothing was sent.", "send_file")
    if prepare is None:
        prepare = SEND.prepare
    try:
        state, card = prepare({"query": str((f or {}).get("query") or "").strip()})
    except ValueError as exc:
        return Result(str(exc), "send_file")            # the module's own words
    except Exception as exc:                            # noqa: BLE001
        return Result(f"Sending a file to your phone is not available right now "
                      f"({type(exc).__name__}), so nothing was sent.", "send_file")
    if gate is None:
        # The ONE gate every card goes through, already wrapped above for the
        # update card; reusing it keeps this module's single gate import.
        gate = _update_gate
    if spawn is None:
        spawn = lambda fn: threading.Thread(          # noqa: E731
            target=fn, name="jarvis-send-file-card", daemon=True).start()
    try:
        spawn(lambda: _send_file_card_thread(SEND, action, state, card, gate))
    except Exception:
        return Result(SEND_FILE_NOT_A_CARD, "send_file")
    return Result(str(card).strip() + SEND_FILE_SAID, "send_file")


def _forget_range(s: str, now: float) -> Optional[Intent]:
    """"forget what you learned last week", "delete my chats from 1 to 15
    September" - jarvis_forget_range.parse_phrase. Without that module, or
    on any error: not ours (the model has no tool that forgets anything)."""
    try:
        import jarvis_forget_range as FR
        got = FR.parse_phrase(s, now)
    except Exception:
        return None
    if got is None:
        return None
    return Intent("forget_range", {"got": got})


FORGET_RANGE_MISSING = ("Your PC's Jarvis cannot forget a time frame yet - run apply-patches.ps1 "
                        "on the PC.")


def _run_forget_range(f: dict, now: float) -> Result:
    """Never removes anything: it fills in the checked list in both apps'
    Brain and says where it is. The owner unticks, taps Forget these, and
    approves ONE card by tapping - a spoken "yes" approves nothing. A date
    it is not sure of is a question instead, and opens nothing."""
    try:
        import jarvis_forget_range as FR
        reply, opens = FR.quick_answer(f.get("got") or {}, now)
    except Exception:
        return Result(FORGET_RANGE_MISSING, "forget_range")
    return Result(reply, "forget_range", open_brain="forget-range" if opens else None)


# --- "label this chat Work" (chat tags, 2026-09-30) ---------------------------
_TAG_NAME = r"(?:the\s+)?(?:tag\s+)?(?P<n>[^\s].{0,59})"
#: This chat: "label this chat Work", "label this chat as Work", "file this
#: chat under Learning", and the short "file this under Learning" / "tag this
#: as Ideas" (the short form needs "as" or "under": "file this" alone is not ours).
_TAG_THIS = re.compile(
    r"(?:label|tag|file|categori[sz]e|sort)\s+(?:this|the\s+current)\s+(?:chat|conversation)\s+"
    r"(?:(?:as|under)\s+)?" + _TAG_NAME
    + r"|(?:label|tag|file)\s+this\s+(?:as|under)\s+" + _TAG_NAME.replace("(?P<n>", "(?P<n2>"))
#: An older chat, named by what it was about. Never this chat.
_TAG_OLDER = re.compile(
    r"(?:label|tag|file)\s+(?:my|the|that)\s+(?:chat|conversation)\s+"
    r"(?:about|on|where\s+(?:i|we)\s+(?:talked|spoke|asked)\s+about)\s+(?P<q>.{1,60}?)\s+"
    r"(?:as|under)\s+" + _TAG_NAME)
_TAG_OFF = re.compile(
    r"(?:remove|clear|delete|drop|take\s+off)\s+(?:the\s+)?(?:tag|label)\s+(?:from|off|on)\s+"
    r"(?:this|the\s+current)\s+(?:chat|conversation)"
    r"|(?:untag|unlabel|unfile)\s+(?:this|the\s+current)\s+(?:chat|conversation)"
    r"|(?:remove|clear|delete)\s+(?:this|the\s+current)\s+(?:chat|conversation)'?s?\s+(?:tag|label)"
    r"|take\s+the\s+(?:tag|label)\s+off\s+(?:this|the\s+current)\s+(?:chat|conversation)")


def _chat_tag(s: str) -> Optional[Intent]:
    """Whole sentences only. The name is kept as said (lower-cased here;
    match() puts the owner's capitals back through the `text` field)."""
    if _TAG_OFF.fullmatch(s):
        return Intent("chat_tag", {"op": "off"})
    m = _TAG_OLDER.fullmatch(s)
    if m:
        return Intent("chat_tag", {"op": "older", "text": m.group("n").strip(),
                                   "about": m.group("q").strip()})
    m = _TAG_THIS.fullmatch(s)
    if m:
        return Intent("chat_tag", {"op": "this",
                                   "text": (m.group("n") or m.group("n2")).strip()})
    return None


CHAT_TAG_MISSING = ("Your PC's Jarvis cannot file chats under tags yet - run apply-patches.ps1 "
                    "on the PC.")
CHAT_TAG_OUTSIDE = ("I do not file a chat after it has read outside text, like an email or a web "
                    "page. Use History to file it yourself.")
CHAT_TAG_NO_CHAT = ("I cannot tell which chat this is. Open History and file it from there.")
CHAT_TAG_TEMPORARY = ("This is an incognito chat, so it is not kept and cannot be filed.")
CHAT_TAG_NOT_KEPT = ("This chat has not been saved yet, so there is nothing to file. Try again "
                     "after my next answer, or use History.")


def _chat_tainted(conversation, messages) -> bool:
    """Has this conversation read outside text? Fails CLOSED, like
    jarvis_widgets.chat_tainted."""
    try:
        import jarvis_chat_log
        return bool(jarvis_chat_log.conversation_tainted(conversation, messages))
    except Exception:
        if not isinstance(messages, list):
            return True
        turns = [m for m in messages if isinstance(m, dict)
                 and m.get("role") in ("user", "assistant", "tool")]
        return len(turns) > 1 or any(m.get("role") != "user" for m in turns)


def _run_chat_tag(f: dict, conversation, temporary: bool, messages) -> Result:
    """File (or unfile) the request's own conversation - or, for an older
    chat, only point History at it. No card: the owner's own organisation."""
    n = "chat_tag"
    try:
        import jarvis_chat_log as CL
    except Exception:
        return Result(CHAT_TAG_MISSING, n)
    if _chat_tainted(conversation, messages):
        return Result(CHAT_TAG_OUTSIDE, n)
    op = f.get("op")
    tag = None
    if op in ("this", "older"):
        try:
            reg = CL.tags()
        except Exception:
            return Result(CHAT_TAG_MISSING, n)
        tags = reg.get("tags") or []
        want = str(f.get("text") or "").strip()
        tag = next((t for t in tags if t["name"].casefold() == want.casefold()), None)
        if tag is None:
            if not tags:
                return Result("You have no tags yet. Make one in History.", n, private=True)
            names = ", ".join(t["name"] for t in tags)
            return Result(f"I do not have a tag called {want}. Your tags are: {names}. "
                          "Make new ones in History.", n, private=True)
        if op == "older":
            return Result(f"Tap the chat you mean in History and I will file it under "
                          f"{tag['name']}.", n, private=True, open_brain="history",
                          file_under=int(tag["id"]), history_q=str(f.get("about") or ""))
    if temporary:
        return Result(CHAT_TAG_TEMPORARY, n)
    if not conversation:
        return Result(CHAT_TAG_NO_CHAT, n)
    code, out = CL.tag_chat(conversation, None if op == "off" else tag["id"])
    if code == 404 and out.get("error") == "not_found":
        return Result(CHAT_TAG_NOT_KEPT, n)
    if code != 200 or not out.get("ok"):
        return Result(str(out.get("message") or "I could not file that just now."), n)
    if op == "off":
        return Result("Done, this chat has no tag now. You can change it in History.", n)
    return Result(f"Done, filed under {tag['name']}. You can change it in History.", n,
                  private=True)


# --- "stop using my work topic" (topic controls, 2026-09-30) ------------------
_TOPIC_THE = r"(?:(?:my|the)\s+)?"
_TOPIC_NAME = r"(?P<n>[^\s].{0,23}?)"
_TOPIC_NO_USE = re.compile(
    r"(?:stop\s+using|don'?t\s+use|do\s+not\s+use)\s+" + _TOPIC_THE + _TOPIC_NAME
    + r"(?P<t>\s+topic)?")
_TOPIC_NO_LEARN = re.compile(
    r"(?:stop\s+learning(?:\s+about)?|don'?t\s+learn(?:\s+about)?|do\s+not\s+learn(?:\s+about)?)"
    r"\s+" + _TOPIC_THE + _TOPIC_NAME + r"(?P<t>\s+topic)?")
_TOPIC_PICK = re.compile(
    r"(?:(?:switch|turn)\s+off|pause|hide|mute|silence|change)\s+" + _TOPIC_THE
    + r"(?P<n>[^\s].{0,23}?)\s+topic")
_TOPIC_ON_USE = re.compile(
    r"(?:use|start\s+using|resume\s+using)\s+" + _TOPIC_THE + _TOPIC_NAME
    + r"\s+topic\s+again")
_TOPIC_ON_LEARN = re.compile(
    r"(?:start\s+learning(?:\s+about)?|learn\s+about)\s+" + _TOPIC_THE + _TOPIC_NAME
    + r"(?:\s+topic)?\s+again")
_TOPIC_ON_BOTH = re.compile(r"(?:turn|switch)\s+on\s+" + _TOPIC_THE + _TOPIC_NAME + r"\s+topic")
_TOPIC_OPEN = re.compile(r"(?:open|show)\s+(?:me\s+)?(?:my\s+|the\s+)?topics")


def _topic_names() -> list:
    """The names of the owner's topics, or [] - a bare name in a sentence is
    ours only when it IS a topic."""
    if sys.modules.get("jarvis_memory") is None:
        return []           # a store is borrowed, never created by a sentence
    try:
        import jarvis_topics
        with jarvis_topics._db() as c:
            return [t["name"] for t in jarvis_topics.topics_of(c)]
    except Exception:
        return []


def _topic_mode(s: str) -> Optional[Intent]:
    if _TOPIC_OPEN.fullmatch(s):
        return Intent("topic_mode", {"op": "open", "text": ""})
    for rx, op in ((_TOPIC_PICK, "pick"), (_TOPIC_ON_USE, "on_use"),
                   (_TOPIC_ON_BOTH, "on_both"), (_TOPIC_ON_LEARN, "on_learn"),
                   (_TOPIC_NO_USE, "no_use"), (_TOPIC_NO_LEARN, "no_learn")):
        m = rx.fullmatch(s)
        if not m:
            continue
        name = m.group("n").strip()
        said_topic = "t" in rx.groupindex and bool(m.group("t")) or op in (
            "pick", "on_use", "on_both")
        if not said_topic:
            # No word "topic": ours only if the name IS one of the owner's topics.
            if name.casefold() not in {n.casefold() for n in _topic_names()}:
                return None
        return Intent("topic_mode", {"op": op, "text": name})
    return None


def _run_topic_mode(f: dict, conversation, temporary: bool, messages) -> Optional[Result]:
    n = "topic_mode"
    try:
        import jarvis_topics as T
        import jarvis_settings_registry as R
    except Exception:
        return Result(T_MISSING, n)
    if _chat_tainted(conversation, messages):
        return Result(T.WORDS["outside"], n)
    op = f.get("op")
    if op == "open":
        return Result("Opening your topics.", n, private=True, open_brain="topics")
    want = str(f.get("text") or "").strip()
    names = _topic_names()
    hit = next((x for x in names if x.casefold() == want.casefold()), None)
    if hit is None:
        if not names:
            return None
        return Result(T.WORDS["no_such_topic"].format(name=want) + " "
                      + T.WORDS["topics_are"].format(names=", ".join(names)), n, private=True)
    found = R.find_topic(hit)
    if found is None:
        return None
    if op == "pick":
        return Result(T.WORDS["pick_line"].format(name=hit), n, private=True,
                      open_brain="topics", topic_id=int(found["id"]))
    learn, use = T.mode_flags(found["mode"])
    if op == "no_use":
        use = False
    elif op == "no_learn":
        learn = False
    elif op == "on_use":
        use = True
    elif op == "on_learn":
        learn = True
    else:                                                   # on_both
        learn = use = True
    mode = {(True, True): "both", (False, True): "use_only",
            (True, False): "learn_only", (False, False): "off"}[(learn, use)]
    if mode == found["mode"]:
        return Result(f"{hit} is already {T.MODE_NAME[mode]}. You can change it in Brain.", n,
                      private=True)
    out = R.set_topic_mode(int(found["id"]), mode)
    return Result(out.said, n, private=True)


T_MISSING = ("Your PC's Jarvis does not have topic controls yet - run apply-patches.ps1 on "
             "the PC.")


def _project_log(s: str) -> Optional[Intent]:
    """"log 5 km run", "I ran 5 km": ours only when a life project has a
    benchmark it fits (jarvis_projects.quick_match). Without
    jarvis_projects.py, or on any error reading it: not ours."""
    try:
        import jarvis_projects as PJ
        found = PJ.quick_match(s)
    except Exception:
        return None
    if not found:
        return None
    return Intent("project_log", {"found": found})


def _run_project_log(f: dict, now: float) -> Result:
    """Logged at once, no card - the owner's own number. A sensitive
    (health or money) benchmark's answer is private: kept on screen."""
    try:
        import jarvis_projects as PJ
    except Exception:
        return Result("Your PC's Jarvis cannot keep projects yet - run apply-patches.ps1 "
                      "on the PC.", "project_log")
    found = f.get("found") or {}
    private = any(b.get("sensitive") for b in
                  ([found["match"]] if found.get("match") else found.get("ambiguous") or []))
    try:
        out = PJ.quick_log(found, now=now)
    except Exception as exc:
        why = str(PJ._err(exc)[1].get("error") or "it could not be saved")
        return Result("That was not logged: " + why[:1].lower() + why[1:], "project_log",
                      private=private)
    return Result(out["said"], "project_log", private=bool(out.get("private")) or private)


def _run_media(intent: Intent) -> Result:
    """Play/pause/next/previous act at once, no card (the owner's own
    words are the only permission this needs); "what's playing" says the
    title and artist, which are OUTSIDE TEXT - whatever app is playing put
    them there, not the owner - so `read` marks them, exactly as a
    briefing's calendar titles do."""
    n = intent.name
    try:
        import jarvis_media as MEDIA
    except Exception:
        return Result(MEDIA_MISSING, n)
    if n == "media_now":
        out = MEDIA.now_playing()
        return Result(str(out.get("said") or ""), n, read=list(out.get("read") or []))
    out = MEDIA.control({"media_play": "play", "media_pause": "pause", "media_next": "next",
                         "media_previous": "previous"}[n])
    return Result(str(out.get("said") or ""), n)


def _run_search(intent: Intent) -> Result:
    """Explained from jarvis_search's own words (the same both apps show),
    or the provider switched - immediately, as from either app's Settings.
    Nothing is searched here."""
    n, which = intent.name, intent.f.get("which")
    try:
        import jarvis_search as WS
    except Exception:
        return Result(SEARCH_MISSING, n)
    if n == "search_explain":
        return Result(WS.explain(which), n)
    # WS.use says a left-out one's reason instead of choosing it.
    return Result(WS.use(which), n)


#: "From now on ..." for a tail that does not map to a real dial (only
#: warm/plain exist today) - said plainly rather than pretended.
FROM_NOW_ON_UNMAPPED = (
    "Jarvis can only change between warm-and-brief and plain right now, not that. Try "
    "\"from now on, be more plain\" or \"from now on, be warmer.\"")

#: Said when a temporary chat asks for a change but this request carries no
#: usable conversation id to keep it in - so there is no chat to keep it in.
FROM_NOW_ON_NO_CONVERSATION = (
    "Jarvis could not tell which chat this is, so it cannot change that for just this one. "
    "Try again in a moment.")


def _from_now_on_said(manner: str, temporary: bool) -> str:
    said = "plainer answers" if manner == "plain" else "warmer, friendlier answers"
    if temporary:
        return f"Done: {said} for this chat. Say it again, or start a new chat, to change back."
    return f"Done: {said} from now on. You can undo this in Settings."


def _run_from_now_on(f: dict, conversation: Optional[str], temporary: bool) -> Result:
    """"From now on, be more plain" / "... be warmer" (the owner's decision,
    2026-09-27): applies at once, no card either way - jarvis_manner.py
    already raises none for a manner change. A temporary chat's change is
    kept in memory, for that conversation only (jarvis_manner.set_temporary);
    an ordinary chat's is saved as the PC's setting
    (jarvis_manner.handle_set), exactly as a tap in Settings would."""
    n = "manner_from_now_on"
    manner = f.get("manner")
    if manner is None:
        return Result(FROM_NOW_ON_UNMAPPED, n)
    try:
        import jarvis_manner
    except Exception:
        return Result("Your PC's Jarvis does not have manners yet - run apply-patches.ps1 "
                      "on the PC.", n)
    before = jarvis_manner.current(conversation if temporary else None)
    if before == manner:
        word = "plainly" if manner == "plain" else "warmly and briefly"
        return Result(f"Jarvis already answers {word}.", n)
    if temporary:
        if not conversation:
            return Result(FROM_NOW_ON_NO_CONVERSATION, n)
        jarvis_manner.set_temporary(conversation, manner)
    else:
        code, out = jarvis_manner.handle_set({"manner": manner})
        if code != 200 or not out.get("ok"):
            return Result("Jarvis could not change that setting just now.", n)
    return Result(_from_now_on_said(manner, temporary), n)


def _switch_words(title: str) -> str:
    """The sentence that really switches to a preset - ONE copy for both
    answers that offer it (the status words and the describe words).

    Measured 2026-10-26 on every title the contract held then: `switch to
    <title>` alone matches
    nothing, because `_P_SWITCH_MODE` needs the noun after the name, while
    `switch to the <title> personality` switches every one of them - including
    the two titles that carry an "&". Having the sentence in two places is how
    the status answer came to offer one that did not work; one function keeps
    them from drifting apart again."""
    return f"switch to the {title} personality"


def _personality_words() -> str:
    """The answer to "what personality are you using?" - the active preset, its
    dials, and the ten names (plus the owner's own saved ones), so the owner
    learns the words to say."""
    try:
        import jarvis_manner
    except Exception:
        return ("Your PC's Jarvis does not have personality presets yet - run "
                "apply-patches.ps1 on the PC.")
    active = jarvis_manner.current_preset()
    dials = jarvis_manner.dials()
    builtin = jarvis_manner._BUILTIN
    words = (f"You're using {active['title']}. Humour {dials['humor']}/3, "
             f"{dials['brevity']} answers, {dials['formality'].replace('_', ' ')} formality, "
             f"addressing you as {dials['address'].replace('_', ' ')}. "
             f"The ten personalities are: " + "; ".join(p["title"] for p in builtin) + ".")
    saved = jarvis_manner.user_personalities()
    if saved:
        words += " Your own: " + "; ".join(str(u.get("name") or u.get("id")) for u in saved) + "."
    words += f' Say "{_switch_words("Classic Butler")}" or "talk to me like TARS" to change.'
    return words


def _personality_receipt(summary: str, before: dict, after: dict, undo) -> str:
    """A 1-click Undo receipt for a personality change. Never raises: a
    receipts database that is not there yet just means no receipt was kept."""
    try:
        import jarvis_receipts
        return jarvis_receipts.record("personality", summary, before=before,
                                      after=after, undo=undo)
    except Exception:
        return ""


def _run_personality_set(f: dict, conversation: Optional[str], temporary: bool) -> Result:
    """"Switch personality to Classic Butler" / "talk to me like TARS": at once,
    no card either way (a personality changes wording only), answered in the
    new preset's own voice. A temporary chat's switch stays in that chat, in
    memory only - the same rule "from now on ..." follows."""
    n = "personality_set"
    try:
        import jarvis_manner
    except Exception:
        return Result("Your PC's Jarvis does not have personality presets yet - run "
                      "apply-patches.ps1 on the PC.", n)
    active = jarvis_manner.preset(f.get("personality"))
    if active is None:
        return Result(_personality_words(), n)
    before = jarvis_manner.current_personality(conversation if temporary else None)
    if temporary:
        if not conversation:
            return Result(FROM_NOW_ON_NO_CONVERSATION, n)
        jarvis_manner.set_temporary_personality(conversation, active["id"])
        said = str(active.get("switch_ack") or "")
    else:
        ok, said = jarvis_manner.set_personality(active["id"])
        if not ok:
            return Result(said, n)

        def undo() -> None:
            try:
                jarvis_manner.set_personality(before)
            except Exception:
                pass

        _personality_receipt(f"Switched personality to {active['title']}",
                             {"personality": before}, {"personality": active["id"]}, undo)
    return Result(said or f"Switched to {active['title']}.", n)


def _run_personality_dial(f: dict) -> Result:
    """"Set humour to dry" / "call me sir": one of the four dials, at once, no
    card - it changes wording only. Answered in the active preset's voice."""
    n = "personality_dial"
    try:
        import jarvis_manner
    except Exception:
        return Result("Your PC's Jarvis does not have personality presets yet - run "
                      "apply-patches.ps1 on the PC.", n)
    ok, said = jarvis_manner.set_dial(str(f.get("name") or ""), f.get("value"))
    if ok:
        _personality_receipt(
            f"Set {f.get('name')} to {said}",
            {"dials": jarvis_manner.dials()}, {"dials": jarvis_manner.dials()}, None)
    return Result(said, n)


def _run_personality_status() -> Result:
    return Result(_personality_words(), "personality_status")


PERSONALITY_MISSING = ("Your PC's Jarvis does not have personality presets yet - run "
                       "apply-patches.ps1 on the PC.")


def _personality_description_words(active: dict) -> str:
    """One preset described in its own words: its title, the `description` the
    contract already carries, and the sentence that switches to it. Nothing
    here is new copy - the description IS the preset's."""
    title = str(active.get("title") or active.get("id") or "")
    line = str(active.get("description") or "").strip()
    said = f"{title} - {line}" if line else title
    return said.rstrip() + f' Say "{_switch_words(title)}" to use it.'


def _run_personality_describe(f: dict) -> Result:
    """"describe the butler personality" / "what does each personality do":
    what a preset IS, in its own `description` - cardless and never the model,
    listed in READ_ONLY_INTENTS so it never clears the "cancel that" record.
    Nothing the owner can see is written; like every quick answer,
    `answer()` still records its usual command-digest row for the scheduler.
    One preset by title, alias or saved name; with no name, all ten in
    contract order plus the dials and how to make one of your own.
    The active preset is deliberately not repeated here: the status answer
    already says which one that is."""
    n = "personality_describe"
    try:
        import jarvis_manner
    except Exception:
        return Result(PERSONALITY_MISSING, n)
    pid = f.get("personality")
    if pid:
        active = jarvis_manner.preset(pid)
        if active is None:
            return Result(_personality_words(), n)
        return Result(_personality_description_words(active), n)
    lines = [f"- {p['title']} - {p['description']}" for p in jarvis_manner._BUILTIN]
    return Result("Here's what each personality does:\n" + "\n".join(lines) + "\n"
                  "On top of the one you pick, four dials tune the wording - humour, answer "
                  "length, formality and how I address you - and you can make your own by "
                  'saying "make me a personality that ...".', n)


def _timer_confirmation(seconds, text: str = "") -> str:
    """The sentence a set timer gets: the active personality's own reflex line
    when one is chosen, the old sentence otherwise. A number in the line is
    never cached (#690 keeps only fixed text)."""
    try:
        import jarvis_schedule as _S
        length = _S.length_words(seconds)
    except Exception:
        length = f"{int(seconds)} seconds"
    try:
        import jarvis_manner
        if jarvis_manner.personality_chosen():
            said = jarvis_manner.reflex_phrase("timer_set", duration=length)
            if said:
                return said
    except Exception:
        pass
    what = f"{str(text).capitalize()} timer" if text else "Timer"
    return f"{what} set for {length}."


def _run_thinking_set(f: dict, temporary: bool = False) -> Result:
    level = f.get("level", "off")
    warn = ""
    try:
        import jarvis_thinking
        code, out = jarvis_thinking.set_level("everyday", level)
        if code != 200:
            return Result(out.get("error", f"Could not set thinking level to {level}."), "thinking_set")
        # "From now on, think harder" is a level, and a level is WHEN-gated
        # (jarvis_thinking.WHEN_ASKED, 2026-10-11): on "Only when I ask" a
        # level is used on the questions the owner asks for thinking about and
        # nowhere else. Left unsaid, the owner would hear "from now on" and
        # get it only when he asked - so the sentence says which of the two he
        # is on and what to say to change it. Nothing is changed here but the
        # level he asked for.
        if level != jarvis_thinking.OFF and jarvis_thinking.get_when() != jarvis_thinking.ALWAYS:
            warn = (" Jarvis thinks on the questions you ask him to think about - "
                    "say \"always think\" to have every answer think first.")
    except Exception:
        return Result("Your PC's Jarvis does not have thinking controls yet.", "thinking_set")
    desc = {
        "deep": "thinking deeply",
        "quick": "quick thinking",
        "off": "thinking is off",
        "auto": "automatic thinking",
    }.get(level, f"thinking {level}")
    return Result(f"Done: {desc} from now on. You can change this in Settings.{warn}",
                  "thinking_set")


def _run_thinking_when(f: dict) -> Result:
    """"Always think" / "only think when I ask": WHEN thinking happens at all
    (jarvis_thinking.set_when, 2026-10-11) - the same function the setting's
    own row calls, no card, and never the per-question flag."""
    try:
        import jarvis_thinking
        code, out = jarvis_thinking.set_when(f.get("when"))
        if code != 200:
            return Result(out.get("error", "Jarvis could not change that just now."), "thinking_when")
    except Exception:
        return Result("Your PC's Jarvis does not have thinking controls yet.", "thinking_when")
    if jarvis_thinking.get_when() == jarvis_thinking.ALWAYS:
        return Result("Done: Jarvis may think before every answer. Thinking uses part "
                      "of your conversation room, and answers can take longer.", "thinking_when")
    return Result("Done: Jarvis thinks only on the questions you ask him to think about.",
                  "thinking_when")


def _run_thinking_status() -> Result:
    try:
        import jarvis_thinking
        lvl = jarvis_thinking.get_level("everyday")
        when = jarvis_thinking.get_when()
        said = f"Thinking is currently {lvl}. {jarvis_thinking.WHY.get(lvl, '')}"
        if when != jarvis_thinking.ALWAYS:
            said += (" Jarvis uses it only on the questions you ask him to think "
                     "about - say \"always think\" to change that.")
        return Result(said, "thinking_status")
    except Exception:
        return Result("Thinking is currently off.", "thinking_status")



def is_command(text) -> bool:
    """Does this sentence fit the grammar? For jarvis_intake.owner_turns:
    a command to set a timer or a reminder is not a fact to learn. Reads no
    state and acts on nothing."""
    try:
        return match(text) is not None
    except Exception:
        return False

# --------------------------------------------------------------------------
#   Acting
# --------------------------------------------------------------------------

@dataclass
class Result:
    reply: str
    intent: str
    ids: list = field(default_factory=list)
    private: bool = False       # the reply quotes the owner's list
    # Reads whose outside text is IN the reply (a briefing quoting calendar
    # titles: ["calendar_read"]). briefing.patch hands it to this PC's record
    # of the turn as `tools_ran`, so the conversation counts as having read
    # outside text - exactly as when the calendar tool runs.
    read: list = field(default_factory=list)
    # What "cancel that" may take back (2026-09-25): the jobs this answer
    # MADE (never one that was already there), in words, and the nouns
    # "cancel that <noun>" may use for it.
    made: list = field(default_factory=list)
    what: str = ""
    nouns: tuple = ()
    # "open <a settings section>" (jarvis_settings_registry.py, 2026-09-27):
    # the section id both apps already use for their own settings screen, so
    # they can jump there. None for every other answer made here.
    open_settings: Optional[str] = None
    # "hide the finance menu" (jarvis_menus.py, 2026-09-30): {"action", "target"}
    # each app applies to its OWN menu list. None for every other answer.
    menu_visibility: Optional[dict] = None
    # Sharpness or frame rate asked for by voice or chat (2026-09-28): one of
    # jarvis_animal.DEVICE_CHANGES. Per device, so the PC changes nothing -
    # the app that asked applies it to itself (jarvis_animal.step_device).
    face_tuning: Optional[str] = None
    # "Forget a time frame" (jarvis_forget_range.py, 2026-09-28): the place in
    # Brain both apps open - "forget-range" - after "forget what you learned
    # last week" filled in its list. Navigation only; nothing is removed.
    # The "open ..." sentences of 2026-10-31 use the SAME field for Jarvis's
    # own windows: "brain" (the Brain itself), "history" and "tutorials" -
    # places the apps already open through `open_fix_place`. No new field and
    # no new kind of route, so a client that does not know a value ignores it.
    open_brain: Optional[str] = None
    # "Label my chat about the boiler as Home" (chat tags, 2026-09-30): the tag
    # id History should offer to file a tapped chat under, and the words it
    # should search for. Additive, like open_brain; both None otherwise.
    file_under: Optional[int] = None
    history_q: Optional[str] = None
    # "Switch off my work topic" (topic controls, 2026-09-30): which topic the
    # four-choice picker should open on, next to open_brain "topics". An id,
    # never the owner's word. None otherwise.
    topic_id: Optional[int] = None
    # "Where did I put ...?" (2026-09-28): the saved facts the answer quotes,
    # by id, and how many of them are sensitive - so X-Jarvis-Route says the
    # answer used memory, both apps show "Used 1 memory" with Forget, and a
    # sensitive one stays on screen like any memory answer (route_fields).
    facts: list = field(default_factory=list)
    facts_sensitive: int = 0
    # "open Notion", "open settings", "open Jarvis settings" (jarvis_open.py,
    # the owner's request of 2026-10-10): what the app that heard the words
    # should open, and which of the four kinds it is. Additive, like every
    # field above - a client that does not know `open_app` (the phone) shows
    # the answer and opens nothing, which is why the reply says "on this PC".
    open_app: Optional[str] = None
    open_app_kind: Optional[str] = None
    # True when `open_app` is a program the BACKEND named itself (Windows'
    # own accessories - notepad, calc), so the app opens it as it stands. False
    # for a name in the owner's own words, which the app resolves against this
    # PC's own Start menu rather than trusting a guess. Only meaningful when
    # `open_app_kind` is "app".
    open_app_built: bool = False
    # The Jarvis Settings section id when the owner named one ("open web
    # search" -> "web-search"), or "" for the top of the window ("open Jarvis
    # settings"). Only ever set when `open_app_kind` is "jarvis": the other
    # kinds have their own target. A separate field because "" is a real
    # answer here and `open_app` above is dropped from the route line when it
    # is empty.
    open_place: Optional[str] = None
    # The one extra sentence for a phrase with two real readings ("open
    # settings" is Windows'; this is how to ask for Jarvis's). Never an error,
    # never a card: the request was answered.
    open_app_note: Optional[str] = None


def _join(items: list) -> str:
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _timer_name(j: dict) -> str:
    import jarvis_schedule as S
    if j.get("text"):
        return f"{j['text']} timer"
    return f"{S.length_words(j.get('duration') or 0)} timer"


def _pick_timer(timers: list, f: dict):
    """(timer, None) or (None, reply)."""
    import jarvis_schedule as S
    if not timers:
        return None, "No timer is running."
    pool = timers
    if f.get("length"):
        pool = [t for t in timers if abs(float(t.get("duration") or 0) - f["length"]) < 1]
        if not pool:
            return None, f"There is no {S.length_words(f['length'])} timer."
    elif f.get("label"):
        pool = [t for t in timers if (t.get("text") or "").lower() == f["label"]]
        if not pool:
            return None, f"There is no {f['label']} timer."
    if len(pool) > 1:
        names = _join(_timer_name(t) for t in pool[:4])
        return None, (f"You have {len(pool)} timers: {names}. Say which one, like "
                      f"\"cancel the {_timer_name(pool[0])}\".")
    return pool[0], None


SETTINGS_MISSING = ("Your PC's Jarvis does not have the settings registry yet - run "
                    "apply-patches.ps1 on the PC.")


def _memory_k() -> int:
    """JARVIS_MEMORY_K: 0 means no memory at all (ARCHITECTURE section 5),
    which the fast path honours too."""
    import os
    try:
        return int(os.environ.get("JARVIS_MEMORY_K", "5"))
    except ValueError:
        return 5


def _run_where_put(f: dict, now: float, temporary: bool) -> Optional[Result]:
    """"Where is my passport?" from memory, without the model (2026-09-28;
    JARVIS-API section 77). None - the model answers, as before - in a
    temporary chat (it uses no memory), with memory switched off
    (JARVIS_MEMORY_K=0), without jarvis_places.py or the memory store, and
    when no saved place is in use for that thing."""
    if temporary or _memory_k() <= 0:
        return None
    try:
        import jarvis_memory
        import jarvis_places
        found = jarvis_places.lookup(jarvis_memory.store(), f.get("thing") or "", now=now)
    except Exception:
        return None
    if not found:
        return None
    try:
        import jarvis_auto_learn
        sensitive = sum(1 for x in found if jarvis_auto_learn.is_sensitive_fact(x.get("text")))
    except Exception:
        sensitive = len(found)            # fail closed: may all be sensitive
    return Result(jarvis_places.answer_words(found, now), "where_put",
                  facts=[int(x["id"]) for x in found], facts_sensitive=sensitive)


def _run_settings_open(f: dict) -> Result:
    """"Open <a settings section>": pure navigation, nothing changed. The
    reply names the section in the owner's own words, so a voice answer
    that gets cut off still says where Jarvis went."""
    import jarvis_settings_registry as R
    section = R.section_by_id(f["id"])
    name = section.names[0] if section else f["id"]
    return Result(f"Opening {name} in Settings.", "settings_open", open_settings=f["id"])


def _run_settings_help() -> Result:
    """"What can I change?" (the owner's decision, 2026-10-10).

    Nothing is changed and no model is used: the words come straight from the
    real switches (jarvis_settings_registry.changeable_words), so the list
    cannot promise a setting that is not there. It says plainly that a change
    which loosens a rule still raises a card, so the answer cannot be read as
    "everything happens at once"."""
    import jarvis_settings_registry as R
    return Result(R.changeable_words(), "settings_help")


def _run_menu_visibility(f: dict) -> Result:
    """"Hide the finance menu": no state here, no gate, no model. The reply is the
    same for every device; the route field tells each app what to apply."""
    import jarvis_menus as MV
    reply, route = MV.voice_change(f["action"], f.get("name") or "")
    return Result(reply, "menu_visibility", menu_visibility=route)


def _run_settings_bool(f: dict, peer, local) -> Result:
    import jarvis_settings_registry as R
    setting = next((b for b in R.BOOL_SETTINGS if b.key == f["key"]), None)
    if setting is None:
        return Result(SETTINGS_MISSING, "settings_bool")
    out = setting.set(f["on"], peer=peer, local=local)
    return Result(out.said, "settings_bool")


def _run_settings_choice(f: dict, peer, local) -> Result:
    """One named-choice setting, through its own setter (2026-10-22).

    The setter is the EXACT function the Settings control/route calls, so its
    card, tier, stale-link hold and PC-only refusal are the control's own."""
    import jarvis_settings_registry as R
    setting = next((c for c in R.CHOICE_SETTINGS if c.key == f["key"]), None)
    if setting is None:
        return Result(SETTINGS_MISSING, "settings_choice")
    out = setting.set(f["value"], peer=peer, local=local)
    return Result(out.said, "settings_choice")


def _run_settings_choice_bad(f: dict) -> Result:
    """A value the named setting does not have: say the real options.

    EXCEPT a Jarvis-made blend (Ashby, Clara) this PC has not made yet: that
    voice exists and is absent, not unknown, so it answers with the picker's own
    "not made yet" sentence instead of the whole voice list
    (`jarvis_settings_registry.choice_not_made_words`; the 2026-10-29 phone
    field test, REPORT.md B3)."""
    import jarvis_settings_registry as R
    setting = next((c for c in R.CHOICE_SETTINGS if c.key == f["key"]), None)
    if setting is None:
        return Result(SETTINGS_MISSING, "settings_choice_bad")
    not_made = R.choice_not_made_words(setting, str(f.get("words") or ""))
    if not_made:
        return Result(not_made, "settings_choice_bad")
    return Result(R.choice_bad_words(setting), "settings_choice_bad")


def _run_settings_choice_help(f: dict) -> Result:
    """Which values a named setting has, without changing anything."""
    import jarvis_settings_registry as R
    setting = next((c for c in R.CHOICE_SETTINGS if c.key == f["key"]), None)
    if setting is None:
        return Result(SETTINGS_MISSING, "settings_choice_help")
    options = setting.option_words()
    name = setting.names[0] if setting.names else setting.key
    if not options:
        return Result(f"{name} has no choices on this PC yet.", "settings_choice_help")
    return Result(f"For {name}, you can say: {options}.", "settings_choice_help")


def _run_face_ask() -> Result:
    """Which face is on, in the spec's own words - a read, nothing written."""
    import jarvis_settings_registry as R
    return Result(R.face_words(), "face_ask")


def _run_settings_only(f: dict) -> Result:
    """The two own-approved Settings-only exceptions: plain words, no card,
    nothing changed (ruling Q3.3)."""
    import jarvis_settings_registry as R
    return Result(R.settings_only_words(f.get("which") or "accounts"), "settings_only")


def _run_settings_wake_word(f: dict, peer, local) -> Result:
    """"Turn on/off the wake word" (2026-10-26).

    The setter is `jarvis_speech.set_wake_enabled`, the exact function
    POST /api/voice/wake calls, so the approval card is the module's own one
    and nothing changes until a person answers it. `peer`/`local` are passed on
    the same way every other setting's are, so a PC-only rule (if the module
    ever grows one) is the module's own decision, never a second one here."""
    import jarvis_settings_registry as R
    out = R.set_wake_word(bool(f.get("on")), peer=peer, local=local)
    return Result(out.said, "settings_wake_word")


def _run_settings_browser_mode(f: dict, peer, local) -> Result:
    """"Set the browser to headless" (2026-10-26).

    The setter is `jarvis_browser_engine.handle_post({"mode": ...})`, the exact
    function POST /api/browser/engine calls. It needs no card either way."""
    import jarvis_settings_registry as R
    out = R.set_browser_mode(str(f.get("mode") or ""), peer=peer, local=local)
    return Result(out.said, "settings_browser_mode")


def _run_settings_browser_mode_bad(f: dict) -> Result:
    """A browser that is not one of the three: say the real ones, change nothing."""
    import jarvis_settings_registry as R
    return Result(R.browser_mode_bad_words(str(f.get("words") or "")),
                  "settings_browser_mode_bad")


def _antislop_read_back(key: str, window: int = 6):
    """What jarvis_antislop says now, or None - never a guess.

    A scope or a mode is a value inside the state file, so it is read from the
    module rather than remembered from the sentence: a change that did not
    stick must be reported as not having stuck. `key` is "enabled", "mode", or
    "scope:<name>"."""
    try:
        import jarvis_antislop as AS
        state = AS.get_state()
    except Exception:
        return None
    if key == "enabled":
        value = state.get("enabled")
        return value if isinstance(value, bool) else None
    if key == "mode":
        value = state.get("mode")
        return value if isinstance(value, str) else None
    if key.startswith("scope:"):
        value = (state.get("scopes") or {}).get(key.split(":", 1)[1])
        return value if isinstance(value, bool) else None
    return None


def _run_settings_antislop_scope(f: dict, peer, local) -> Result:
    """"Turn on anti-slop for code" - ONE scope, through the module's own setter.

    The sentence names one scope and the answer says what the OTHER two are
    doing, because a person who asked for code only needs to know the filter is
    still watching their copy. Nothing is claimed that was not read back.
    """
    import jarvis_settings_registry as R
    name = str(f.get("scope") or "")
    want = bool(f.get("on"))
    out = R.set_antislop_scope(name, want, peer=peer, local=local)
    said = str(getattr(out, "said", "") or "").strip()
    if not getattr(out, "ok", False):
        return Result(said or "That did not work, so nothing was changed.",
                      "settings_antislop_scope")
    after = _antislop_read_back(f"scope:{name}")
    if after is not want:
        return Result(f"I asked the PC to turn anti-slop {'on' if want else 'off'} "
                      f"for {name}, but I could not read it back, so I will not "
                      f"say it worked.", "settings_antislop_scope")
    try:
        import jarvis_antislop as AS
        state = AS.get_state()
        others = [s for s in AS.SCOPES if s != name]
        also = ", ".join(f"{s} {'on' if (state.get('scopes') or {}).get(s) else 'off'}"
                         for s in others)
    except Exception:
        also = ""
    if also:
        said = ((said + " ") if said else "") + f"The other scopes are unchanged ({also})."
    return Result(said, "settings_antislop_scope")


def _run_settings_antislop_state(f: dict) -> Result:
    """"Is anti-slop on?" - the module's own sentence: mode, scopes and dials."""
    import jarvis_settings_registry as R
    return Result(R.antislop_words(), "settings_antislop_state")


def _run_settings_antislop_bad(f: dict) -> Result:
    """A scope the filter does not have: say the three real ones, change nothing."""
    return Result("The Anti-Slop filter has three scopes: copy, code and ui. "
                  "Say for example \"turn off anti-slop for code\". Nothing "
                  "was changed.", "settings_antislop_bad")


def _run_control_set(f: dict, peer, local) -> Result:
    """The one generic multi-field setter: the SAME ChoiceSetting.set the
    Settings control calls - no second mutation path."""
    import jarvis_settings_registry as R
    setting = next((c for c in R.CHOICE_SETTINGS if c.key == f.get("key")), None)
    if setting is None:
        return Result(SETTINGS_MISSING, "control_set")
    out = setting.set(f.get("value"), peer=peer, local=local)
    return Result(out.said, "control_set")


def _run_control_ask(f: dict) -> Result:
    """Deterministic clarifying question: valid fields + their current values."""
    import jarvis_settings_registry as R
    return Result(R.control_ask_words(str(f.get("control") or "")), "control_ask")


def _run_control_bad(f: dict) -> Result:
    """A named field with an invalid value, or a value matching no field."""
    import jarvis_settings_registry as R
    control = str(f.get("control") or "")
    field = str(f.get("field") or "")
    said = str(f.get("value") or "").strip()
    if field and said:
        # A control with ONE field and a value it does not have: name the value
        # that was wrong and list the real ones. `control_bad_words` names the
        # field instead, which for the face read "That is not one of the values
        # for face's face" (2026-10-26, measured through "change your face to
        # zorb"); the owner needs to hear the word he said and the choices.
        try:
            rows = R.fields_for_control(control)
        except Exception:                   # noqa: BLE001 - fall back below
            rows = []
        if len(rows) == 1:
            try:
                options = sorted(rows[0].setting.options().keys())
            except Exception:               # noqa: BLE001 - fall back below
                options = []
            if options:
                return Result(
                    f'"{said}" is not one of the choices for {control}. '
                    f'Say one of: {", ".join(options)}.', "control_bad")
    if field:
        return Result(R.control_bad_words(control, field), "control_bad")
    return Result(R.control_invalid_words(control, said), "control_bad")


def _run_settings_not_by_asking(f: dict) -> Result:
    """A real setting this backend has no route to change (2026-10-13).

    Nothing is changed, no card is raised and no model is used: the answer says
    where the switch really lives, so the owner is not left believing it was
    done. See jarvis_settings_registry.NOT_BY_ASKING for the ten and why.

    A MIXED SENTENCE gets one extra sentence (2026-10-26): when the same turn
    also named a setting Jarvis CAN change, the refusal says so and asks for
    that one separately - instead of silently dropping half of what the owner
    said. It is appended only when the registry proves the second setting is
    really named (`page_only_asked`'s `mixed` flag), so the plain refusal -
    including every hyphenated and filler form - is byte-for-byte unchanged."""
    import jarvis_settings_registry as R
    dom_id = f.get("dom_id") or ""
    if not dom_id:
        return Result(SETTINGS_MISSING, "settings_not_by_asking")
    said = R.not_by_asking_sentence(dom_id)
    if f.get("mixed"):
        said += (" (If you also want to change another setting, ask for it "
                 "separately.)")
    return Result(said, "settings_not_by_asking")


def _run_settings_unknown() -> Result:
    """A settings request naming something nothing here knows (2026-10-13).

    Answered in words rather than handed to the model, which has no settings
    tool and is not told so - the failure that used to look like success."""
    return Result(
        "I cannot change that setting by asking yet. Say \"what can I change?\" "
        "and I will list the ones I can, or name the screen and I will open it - "
        "\"open security\".",
        "settings_unknown")


def _run_settings_budget(f: dict, peer, local) -> Result:
    """"How much Jarvis may interrupt you", by asking (2026-10-08).

    The rule - and the ONE card a raise needs - lives in
    jarvis_arbiter.change(), the same function the apps' own route calls, so
    asking and using the screen cannot drift apart. `step` is the "+1/-1"
    form ("speak up less"), read against the budget in force right now; a
    plain number is applied as it is. A raise waits on a card that this lane
    raises through the gate, exactly like a loosening from a screen."""
    try:
        import jarvis_arbiter as AR
    except Exception:
        return Result(SETTINGS_MISSING, "settings_budget")
    body = f.get("body")
    if body is None:
        step = int(f.get("step") or 0)
        now = AR._limit()
        body = {"spoken_per_day": max(AR.SPOKEN_PER_DAY_MIN,
                                      min(AR.SPOKEN_PER_DAY_MAX, now + step))}
    code, out = AR.change(body, peer=peer, local=local)
    if code >= 400 or out.get("ok") is False:
        return Result(str(out.get("error") or "That did not work."), "settings_budget")
    return Result(str(out.get("said") or "Done."), "settings_budget")


def _run_settings_asks_first(f: dict, peer, local) -> Result:
    import jarvis_settings_registry as R
    out = R.set_asks_first(f["action"], f["ask"], peer=peer, local=local)
    return Result(out.said, "settings_asks_first")


def _run_settings_card_mode(f: dict, peer, local) -> Result:
    """"How much of an approval card is shown", by asking (the owner's request
    of 2026-10-09).

    The rule lives in jarvis_settings_registry.set_card_mode, which calls
    jarvis_card_summary.set_mode - the ONE function POST /api/card-prefs calls,
    so asking and using the screen cannot drift apart. Cosmetic, so it is at
    once with no approval card, either way (CLAUDE.md: "cosmetic options change
    at once"), and neither direction waits on a fresh link."""
    import jarvis_settings_registry as R
    out = R.set_card_mode(f["mode"], peer=peer, local=local)
    return Result(out.said, "settings_card_mode")


def _run_animal(n: str, f: dict, peer, local) -> Result:
    """Animal options by asking - the same functions the switches call, so
    the same rules: the shared switches and the sun and moon at once, the
    weather off or Home Assistant at once, Open-Meteo ONE approval card
    (jarvis_sky raises it; nothing changes until it is approved); sharpness
    and frame rate on the device that asked, named in X-Jarvis-Route."""
    if n == "animal_ask":
        return Result(ANIMAL_QUESTIONS.get(f.get("about"), ANIMAL_QUESTIONS["animal"]), n)
    if n == "animal_device":
        try:
            import jarvis_animal as AN
            said = AN.DEVICE_SAID[f["change"]]
        except Exception:
            return Result(ANIMAL_MISSING, n)
        return Result(said, n, face_tuning=f["change"])
    try:
        import jarvis_settings_registry as R
    except Exception:
        return Result(SETTINGS_MISSING, n)
    if n == "animal_switch":
        out = R.set_animal_switch(f["key"], f["on"], peer=peer, local=local)
    elif n == "animal_sky":
        out = R.set_sky_show(f["on"], peer=peer, local=local)
    elif n == "animal_weather":
        out = R.set_weather_source(f["source"], peer=peer, local=local)
        if out.ok and out.waiting:
            # jarvis_sky's own two sentences, in one: the card is up and
            # nothing has changed (the card is the only yes - a spoken one
            # approves nothing).
            return Result("An approval card is up - nothing is sent to Open-Meteo until you "
                          "approve it, on your PC or phone.", n)
    else:
        return Result(ANIMAL_QUESTIONS["animal"], "animal_ask")
    return Result(out.said, n)


ANIMAL_MISSING = ("Your PC's Jarvis does not have the animal options yet - run "
                  "apply-patches.ps1 on the PC.")


def _run_settings_tool(f: dict, peer, local) -> Result:
    import jarvis_settings_registry as R
    out = R.set_reading_tool(f["tool"], f["on"], peer=peer, local=local)
    return Result(out.said, "settings_tool")


# --------------------------------------------------------------------------
#   Explaining a feature, its state and how to change it (2026-10-20) - no
#   model, no network: every word comes from jarvis_feature_guide, which reads
#   the owner's own feature list and the switch's owning module. Nothing here
#   guesses: the guide's own sentences say when it could not read a state.
# --------------------------------------------------------------------------

FEATURE_MISSING = ("Your PC's Jarvis does not have the feature list yet - run "
                   "apply-patches.ps1 on the PC.")


def _guide():
    try:
        import jarvis_feature_guide as FG
        return FG
    except Exception:
        return None


def _run_features_list(f: dict) -> Result:
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "features_list")
    return Result(FG.groups_words(), "features_list")


def _run_features_group(f: dict) -> Result:
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "features_group")
    out = FG.list_features(f.get("group") or "")
    return Result(str(out.get("words") or FG.groups_words()), "features_group")


def _run_feature_capabilities(f: dict) -> Result:
    """"What can you do with <area>?" - from the feature list's own rows."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_capabilities")
    out = FG.capabilities(f.get("words") or "", verb=f.get("verb") or "",
                          strip_verbs=bool(f.get("strip_verbs", True)))
    return Result(str(out.get("words") or FG.groups_words()), "feature_capabilities")


def _run_feature_explain(f: dict) -> Result:
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_explain")
    out = FG.explain(f.get("id") or "")
    return Result(str(out.get("words") or ""), "feature_explain")


def _run_feature_unknown(f: dict) -> Result:
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_unknown")
    return Result(FG.unknown_words(f.get("words") or ""), "feature_unknown")


def _run_feature_limits(f: dict) -> Result:
    """"What are the limits of X?" - the row's own limit field, no model."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_limits")
    out = FG.limits(f.get("id") or f.get("words") or "")
    return Result(str(out.get("words") or ""), "feature_limits")


def _run_feature_asks(f: dict) -> Result:
    """"Does X ask first?" - the row's own asks field, no model."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_asks")
    out = FG.asks_first(f.get("id") or f.get("words") or "")
    return Result(str(out.get("words") or ""), "feature_asks")


def _run_feature_app(f: dict) -> Result:
    """"Which app can use X?" - the row's own surface field, no model."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_app")
    out = FG.which_app(f.get("id") or f.get("words") or "")
    return Result(str(out.get("words") or ""), "feature_app")


def _run_feature_why(f: dict) -> Result:
    """"Why would I use X?" - the row's what/where/limit, no model."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_why")
    out = FG.why_use(f.get("id") or f.get("words") or "")
    return Result(str(out.get("words") or ""), "feature_why")


def _run_feature_difference(f: dict) -> Result:
    """"What's the difference between X and Y?" - both rows side by side."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_difference")
    out = FG.difference(f.get("first") or "", f.get("second") or "")
    return Result(str(out.get("words") or ""), "feature_difference")


def _run_feature_overview(f: dict) -> Result:
    """"What can you do?" - the catalogue by group, capped, from the rows."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_overview")
    out = FG.overview(f.get("words") or "")
    return Result(str(out.get("words") or ""), "feature_overview")


def _run_feature_detail(f: dict) -> Result:
    """"Explain X in detail" and the detail family - every own field + state."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_detail")
    mode = str(f.get("mode") or "detail")
    target = f.get("id") or f.get("words") or ""
    fn = {"detail": FG.detail, "example": FG.example,
          "private": FG.is_private, "needs": FG.needs,
          "why_state": FG.why_state, "goes_wrong": FG.goes_wrong,
          "like": FG.is_like}.get(mode, FG.detail)
    out = fn(target)
    return Result(str(out.get("words") or ""), "feature_detail")


def _run_feature_can_do(f: dict) -> Result:
    """"Can X do Y?" - only from X's own row text."""
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_can_do")
    out = FG.can_do(f.get("id") or f.get("words") or "",
                    f.get("capability") or "")
    return Result(str(out.get("words") or ""), "feature_can_do")


def _run_feature_state(f: dict) -> Result:
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_state")
    out = FG.state(f.get("id") or "")
    return Result(str(out.get("words") or ""), "feature_state")


def _run_feature_state_setting(f: dict) -> Result:
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_state")
    out = FG.state(f.get("key") or "")
    return Result(str(out.get("words") or ""), "feature_state")


def _run_feature_howto(f: dict) -> Result:
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_howto")
    out = FG.how_to(f.get("id") or "", bool(f.get("on")))
    return Result(str(out.get("words") or ""), "feature_howto")


def _run_feature_howto_setting(f: dict) -> Result:
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_howto")
    out = FG.how_to(f.get("key") or "", bool(f.get("on")))
    return Result(str(out.get("words") or ""), "feature_howto")


def _run_feature_switch_refused(f: dict) -> Result:
    """A feature that names NO switch or SEVERAL: nothing was changed, and the
    answer says which switches it does have - never a "Done"."""
    return Result(str(f.get("words") or ""), "feature_switch_refused")


def _run_feature_change(f: dict) -> Result:
    """"Can I change it?" - the five-label kind, the real switch or place.

    Read-only: it says how a change is made and changes nothing. `feature_change`
    is in READ_ONLY_INTENTS for exactly that reason.
    """
    FG = _guide()
    if FG is None:
        return Result(FEATURE_MISSING, "feature_change")
    out = FG.change(f.get("id") or f.get("name") or f.get("key") or "")
    return Result(str(out.get("words") or ""), "feature_change")


def _run_feature_change_refused(f: dict) -> Result:
    """One plain sentence for the four asks this lane must never act on, and
    nothing changed. See `_CHANGE_NEVER`."""
    return Result(str(f.get("words") or ""), "feature_change_refused")


def _run_feature_change_ask(f: dict) -> Result:
    """"Change the prompt coach" - ONE question back, and nothing else.

    The ask itself is the answer: no card, no write, no second question. It
    names the phrase that works, because a bare "off" as the next message is
    not a sentence this grammar can take, and the owner should not have to
    discover that.
    """
    name = str(f.get("name") or f.get("key") or "").strip()
    if not name:
        return Result("That is an on/off setting - do you want it on or off?",
                      "feature_change_ask")
    return Result(f"Do you want {name} on or off? Say \"turn on {name}\" or "
                  f"\"turn off {name}\" and I will do it, through its own card "
                  f"if it asks for one.", "feature_change_ask")


def _run_feature_change_apply(f: dict, peer, local) -> Result:
    """Change ONE allow-listed setting through its OWN writer, then READ IT BACK.

    THE WHOLE POINT OF THIS LANE. `setting.set` below is the exact function the
    Settings switch, the HUD route and the spoken "turn on <name>" phrase call
    (`_run_settings_bool`). It owns the card, the tier, the PC-only refusal and
    the sentence, so this runner never decides any of those - and it never
    touches the config file, a route, the approval gate or a file directly.

    THE FOUR OUTCOMES, and why each says what it says:
      1. the state could not be READ first -> say so and change nothing. A lane
         that cannot read a value must not write it, because the receipt after
         the write would be a guess too.
      2. it is ALREADY the wanted value -> say "already", zero setter calls,
         zero cards. Asking twice must not raise a second card.
      3. the setter is WAITING on its card -> the setter's own words, never
         "done". Nothing has been written at this point.
      4. the setter APPLIED it -> re-read with `read_state`, and claim success
         only when the new value agrees. A disagreement is said plainly and is
         not dressed up as a change.
    """
    import jarvis_settings_registry as R
    key = str(f.get("key") or "")
    setting = next((b for b in R.BOOL_SETTINGS if b.key == key), None)
    FG = _guide()
    if setting is None or FG is None:
        return Result(SETTINGS_MISSING, "feature_change_apply")
    name = _change_name(setting)
    if not isinstance(f.get("on"), bool):
        # FAIL CLOSED on an intent that does not carry a state. Only the
        # resolver makes this intent, and it always sets a bool - so this line
        # can only be reached by a mistake, and a mistake must never be read as
        # "off" (which is what `bool(None)` would do).
        return Result(f"I did not catch whether you want {name} on or off, so "
                      f"nothing was changed. Say \"turn on {name}\" or \"turn "
                      f"off {name}\".", "feature_change_apply")
    want = bool(f.get("on"))
    want_word = "on" if want else "off"
    other_word = "off" if want else "on"
    if key not in CHANGE_BY_ASKING:
        # Belt and braces: the resolver only makes this intent for the list,
        # and test_ask_to_change.py pins that. If it ever arrives otherwise,
        # answer the explanation and write NOTHING.
        out = FG.change(key)
        return Result(str(out.get("words") or ""), "feature_change")
    before = FG.read_state(key)
    if not isinstance(before, bool):
        return Result(f"I cannot read whether {name} is on right now on this PC, "
                      f"so I will not change it. Nothing was changed.",
                      "feature_change_apply")
    if before == want:
        return Result(f"{name[:1].upper() + name[1:]} is already {want_word}. "
                      f"Nothing was changed.", "feature_change_apply")
    try:
        out = setting.set(bool(want), peer=peer, local=local)
    except Exception as exc:                # noqa: BLE001 - said, never swallowed
        return Result(f"{name[:1].upper() + name[1:]} could not be changed "
                      f"({type(exc).__name__}), so nothing was changed.",
                      "feature_change_apply")
    said = str(getattr(out, "said", "") or "").strip()
    if getattr(out, "waiting", False):
        # The module's own card is up. Its sentence normally says so; when a
        # setter's words do not mention approval at all, add the one fact the
        # owner needs rather than leaving "waiting" implicit.
        if not re.search(r"approv|a card", said, re.I):
            said = (said + " " if said else "") + (
                "A card is waiting for your approval. Nothing has changed yet.")
        return Result(said, "feature_change_apply")
    if not getattr(out, "ok", False):
        # A refusal from the module itself, in its own words - the PC-only
        # sentence, a tier that is wrong, a module that is missing.
        return Result(said or "That did not work, so nothing was changed.",
                      "feature_change_apply")
    after = FG.read_state(key)
    # `_say` falls back to a bare "Done." when a module's own writer returns no
    # sentence (jarvis_prompt_coach.set_enabled is one). The receipt below says
    # more than that fallback does, so the fallback is dropped rather than
    # printed in front of a verified old/new pair.
    said = "" if said == "Done." else said
    if not isinstance(after, bool):
        return Result((said + " " if said else "") +
                      f"I asked the PC to turn {name} {want_word}, but I could not "
                      f"read it back afterwards, so I will not say it worked.",
                      "feature_change_apply")
    if after != want:
        return Result(f"I asked the PC to turn {name} {want_word}, but it still "
                      f"reads {want_word if after else other_word}. Nothing was "
                      f"changed.", "feature_change_apply")
    return Result((said + " " if said else "") +
                  f"I checked: {name} reads {want_word} now - it was {other_word} "
                  f"before.", "feature_change_apply")


def _run_setting_explain(f: dict) -> Result:
    """The settings-registry answer to a how/where/explain question (Q6 Step A).

    Read-only by construction: the words come from
    `jarvis_settings_registry.explain_setting_words`, which only reads the
    tables and never calls a setter. `setting_explain` is in READ_ONLY_INTENTS,
    so it raises no card, changes nothing and cannot take back what "cancel
    that" would.
    """
    try:
        import jarvis_settings_registry as R
    except Exception:
        return Result(SETTINGS_MISSING, "setting_explain")
    return Result(R.explain_setting_words(f), "setting_explain")


def run(intent: Intent, sched, now: float, conversation: Optional[str] = None,
        seen: Optional[float] = None, temporary: bool = False,
        peer=None, local=None, messages=None, desktop=None,
        client_surface: Optional[str] = None) -> Optional[Result]:
    """Do it. None hands the sentence to the model after all.
    `conversation`: the request's conversation_id ("cancel that" works only
    within one). `seen`: when the owner last talked to Jarvis before this
    turn ("what did I miss?"). `temporary`: a temporary chat, for "from now
    on ..." (2026-09-27). `peer`/`local`: the request's own address, read the
    same way owner-check.patch's do_POST wrapper reads it - so a setting on
    jarvis_owner_check.PC_ONLY_ACTIONS can refuse a request that did not
    truly come from this PC (jarvis_settings_registry.py, 2026-09-27).
    `client_surface`: "hud" or "phone" when the caller really knows which
    device asked (2026-10-30, the parking answer's two lengths); otherwise
    `_client_surface` infers it from `peer`/`local`."""
    n, f = intent.name, intent.f
    # The local calendar's own read, and the honest answers for abilities that
    # are off, built only in the apps, or not built at all (2026-10-31, pass
    # 11). Both are fixed sentences that read the real state: no model, no
    # card, no write. They are listed in READ_ONLY_INTENTS, so a private chat's
    # own rule (fast path off, model instead) still applies.
    if n == "local_calendar_read":
        return _run_local_calendar_read(f, now)
    if n == "honest_chat":
        return _run_honest_chat(f)
    if n == "honest_state":
        return _run_honest_state(f)
    if n in _REMINDER_INTENTS:
        return _run_reminders(n, _client_surface(peer, local, client_surface))
    if n in _PLUGIN_INTENTS:
        return _run_plugins(n, f, _client_surface(peer, local, client_surface))
    if n in _ANDROID_INTENTS:
        return _run_android(n, _android_state())
    # Updates in chat (2026-10-26): `desktop` is the app's own report of the
    # build that asked (commands.rs `chat_extras`), never the page's words.
    if n in ("update_ask", "update_notes"):
        return _run_update(intent, desktop)
    if n == "update_start":
        return _run_update_start(desktop)
    if n == "where_put":
        return _run_where_put(f, now, temporary)
    if n == "widget_make":
        # `messages`: the request's, as they arrived - for the taint check.
        return _run_widget(f, conversation, messages)
    if n == "notify_style":
        # The same taint rule, because the owner's words make this too.
        return _run_style(f, conversation, messages)
    # Voice reflex (2026-10-21, Live/Voice audit V4): a router into an action
    # that already exists and already has its own permission model.
    if n == "voice_speed":
        return _run_voice_speed(intent)
    # "find cheap parking near ..." (2026-10-30): read-only, no card, no model.
    # The two intents are in READ_ONLY_INTENTS - they call two public map
    # services and change nothing, so they must not take away what "cancel
    # that" would undo.
    if n in ("parking_lookup", "parking_calendar"):
        return _run_parking(intent, _client_surface(peer, local, client_surface), now)

    # "send me the file ..." (2026-10-31): the module's OWN prepare() and ONE
    # card, raised under its own action - nothing re-implemented here.
    if n == "send_file":
        return _run_send_file_chat(f)

    # The HUD field test's three answers (2026-10-29): Google/Gmail paths,
    # which voice speaks, and how a phone is paired. Every one is read-only:
    # no card, no connection, no voice change. ("change your voice to Ashby"
    # is NOT one of these - it is `settings_choice_bad`, answered by the
    # settings grammar above.)
    if n == "accounts_connect":
        return _run_accounts_connect()
    if n == "voice_ask":
        return _run_voice_ask()
    if n == "pair_phone":
        return _run_pair_phone()
    # Notes and the vault (2026-10-31 field test): the note WRITE goes through
    # jarvis_note_capture's existing capture path; the organizer answer and the
    # refusals only read or refuse; turning the organizer on raises its one
    # existing change_own_config card.
    if n == "note_make":
        return _run_note_make(f)
    if n == "note_create":
        return _run_note_create(f)
    if n == "note_append":
        return _run_note_append(f)
    if n == "note_tag":
        return _run_note_tag(f)
    if n == "note_rename":
        return _run_note_rename(f)
    if n == "note_move":
        return _run_note_move(f)
    if n == "template_list":
        return _run_template_list()
    if n == "template_create":
        return _run_template_create(f)
    if n == "template_save":
        return _run_template_save(f)
    if n == "note_customize":
        op = str(f.get("op") or "")
        card = {"line": "change one line in", "new_section": "add a new section to",
                "rename_heading": "rename a heading in",
                "set_property": "set a property in",
                "remove_property": "remove a property from",
                "link": "add a link in"}.get(op, "change one part of")
        return _run_note_customize(f, op, card)
    if n == "note_insert":
        return _run_note_insert(f)
    if n == "note_format":
        return _run_note_format(f)
    if n == "note_replace":
        return _run_note_replace(f)
    if n == "notes_batch_refused":
        return Result(NOTE_WRITE_BATCH_SAID, "notes_batch_refused")
    if n == "note_write_hidden":
        return Result(NOTE_HIDDEN_SAID, "note_write_hidden")
    if n == "note_delete_refused":
        return Result(NOTE_DELETE_SAID, "note_delete_refused")
    if n == "note_read_honest":
        return _run_note_read_honest()
    if n in ("note_change_refused", "obsidian_style_refused"):
        return (_run_note_change_refused() if n == "note_change_refused"
                else _run_obsidian_style_refused())
    if n == "vault_organizer_plan":
        return _run_vault_organizer_plan(peer, local)
    if n == "vault_organizer_scoped":
        return _run_vault_organizer_scoped(f, peer, local)
    if n == "vault_organizer_apply":
        return _run_vault_organizer_apply(peer, local)
    if n == "vault_organizer_on":
        return _run_vault_organizer_on(peer, local)
    import jarvis_schedule as S
    if n == "settings_open":
        return _run_settings_open(f)
    if n == "settings_help":
        return _run_settings_help()
    if n == "menu_visibility":
        return _run_menu_visibility(f)
    if n == "settings_bool":
        return _run_settings_bool(f, peer, local)
    if n == "settings_choice":
        return _run_settings_choice(f, peer, local)
    if n == "settings_choice_bad":
        return _run_settings_choice_bad(f)
    if n == "settings_choice_help":
        return _run_settings_choice_help(f)
    if n == "face_ask":
        return _run_face_ask()
    if n == "settings_only":
        return _run_settings_only(f)
    if n == "settings_wake_word":
        return _run_settings_wake_word(f, peer, local)
    if n == "settings_browser_mode":
        return _run_settings_browser_mode(f, peer, local)
    if n == "settings_browser_mode_bad":
        return _run_settings_browser_mode_bad(f)
    # The Anti-Slop filter (2026-10-28): two sentences of its own, both
    # cardless, both through the settings registry's own setters. Its MODE
    # needs nothing here - `antislop_mode` is a CHOICE_SETTINGS row, so the
    # generic "set <name> to <value>" grammar already reaches the same setter.
    if n == "settings_antislop_scope":
        return _run_settings_antislop_scope(f, peer, local)
    if n == "settings_antislop_state":
        return _run_settings_antislop_state(f)
    if n == "settings_antislop_bad":
        return _run_settings_antislop_bad(f)
    if n == "control_set":
        return _run_control_set(f, peer, local)
    if n == "control_ask":
        return _run_control_ask(f)
    if n == "control_bad":
        return _run_control_bad(f)
    if n == "settings_not_by_asking":
        return _run_settings_not_by_asking(f)
    if n == "settings_unknown":
        return _run_settings_unknown()
    if n == "settings_budget":
        return _run_settings_budget(f, peer, local)
    if n == "settings_card_mode":
        return _run_settings_card_mode(f, peer, local)
    if n == "settings_asks_first":
        return _run_settings_asks_first(f, peer, local)
    if n == "settings_tool":
        return _run_settings_tool(f, peer, local)
    # Explaining a feature (2026-10-20). `feature_switch` goes through
    # _run_settings_bool below, which calls the SAME BoolSetting.set every other
    # spoken setting change uses - the setting's own card rule is unchanged.
    if n == "features_list":
        return _run_features_list(f)
    if n == "features_group":
        return _run_features_group(f)
    if n == "feature_capabilities":
        return _run_feature_capabilities(f)
    if n == "feature_limits":
        return _run_feature_limits(f)
    if n == "feature_asks":
        return _run_feature_asks(f)
    if n == "feature_app":
        return _run_feature_app(f)
    if n == "feature_why":
        return _run_feature_why(f)
    if n == "feature_difference":
        return _run_feature_difference(f)
    if n == "feature_overview":
        return _run_feature_overview(f)
    if n == "feature_detail":
        return _run_feature_detail(f)
    if n == "feature_can_do":
        return _run_feature_can_do(f)
    if n == "feature_explain":
        return _run_feature_explain(f)
    if n == "feature_unknown":
        return _run_feature_unknown(f)
    if n == "feature_state":
        return _run_feature_state(f)
    if n == "feature_state_setting":
        return _run_feature_state_setting(f)
    if n == "feature_howto":
        return _run_feature_howto(f)
    if n == "feature_howto_setting":
        return _run_feature_howto_setting(f)
    if n == "feature_change":
        return _run_feature_change(f)
    # Changing a setting by asking for it ON or OFF (2026-10-27). `apply` is
    # the ONLY one of the three that can write, it is reachable only for
    # `CHANGE_BY_ASKING`, and it writes through the setting's own writer.
    # `ask` and `refused` change nothing and are in READ_ONLY_INTENTS.
    if n == "feature_change_apply":
        return _run_feature_change_apply(f, peer, local)
    if n == "feature_change_ask":
        return _run_feature_change_ask(f)
    if n == "feature_change_refused":
        return _run_feature_change_refused(f)
    if n == "setting_explain":
        return _run_setting_explain(f)
    if n == "feature_switch":
        return _run_settings_bool({"key": f["key"], "on": f["on"]}, peer, local)
    if n == "feature_switch_refused":
        return _run_feature_switch_refused(f)
    if n.startswith("animal_"):
        return _run_animal(n, f, peer, local)
    if n == "manner_from_now_on":
        return _run_from_now_on(f, conversation, temporary)
    if n == "personality_set":
        return _run_personality_set(f, conversation, temporary)
    if n == "personality_dial":
        return _run_personality_dial(f)
    if n == "personality_status":
        return _run_personality_status()
    if n == "personality_describe":
        return _run_personality_describe(f)
    if n in ("thinking_set", "thinking_from_now_on"):
        return _run_thinking_set(f, temporary)
    if n == "thinking_when":
        return _run_thinking_when(f)
    if n == "thinking_status":
        return _run_thinking_status()
    if n == "bulk":
        return Result("Jarvis does not clear everything at once. Delete them one at a time, "
                      "here or under Coming up.", n)
    if n == "chat_tag":
        return _run_chat_tag(f, conversation, temporary, messages)
    if n == "topic_mode":
        return _run_topic_mode(f, conversation, temporary, messages)
    if n == "forget_range":
        return _run_forget_range(f, now)
    if n == "missed":
        return _run_missed(sched, now, seen)
    if n == "snooze":
        return _run_snooze(f, sched, now)
    if n == "undo":
        return _run_undo(f, sched, now, conversation)
    if n in ("list_clear", "lists_which"):
        return _run_lists(intent, sched)
    if n.startswith("briefing_"):
        return _run_briefing(intent, sched, now)
    if n == "weather_now":
        return _run_weather(now)
    if n == "news_read":
        return _run_news()
    if n == "news_add":
        return _run_news_add(f["url"])
    if n == "news_remove":
        return _run_news_remove(f["url"])
    if n == "news_list":
        return _run_news_list()
    if n.startswith("search_"):
        return _run_search(intent)
    if n == "reach_list":
        return _run_reach(intent)
    if n == "calendar_setup":
        # "connect my calendar", "set up a calendar bridge for me" (2026-10-28):
        # a read-only answer from the reader's own state - it names the real
        # steps, and when nothing is set up it carries `open_settings` so the
        # desktop's Settings window jumps to the Accounts card. Nothing is
        # read from a calendar and nothing is connected.
        return _run_calendar_setup(intent)
    if n == "notion_export":
        # "can you process all of my notion notes into obsidian?" (2026-10-28):
        # a fixed answer, like reach/sayable - it names the export steps, the
        # import button on this PC and the converter's half that has no button
        # yet. Nothing is read and nothing is imported.
        return _run_notion(f)
    if n == "connect_account":
        # "connect my calendar" / "set up github" (2026-10-28): ONE card whose
        # values are typed on this PC and saved into Credential Manager, then
        # one real test; or the honest state of one service. See `_run_connect`.
        return _run_connect(f)
    if n == "sayable_help":
        return _run_sayable(intent)
    if n == "identity_help":
        return _run_identity(intent)
    if n == "open_chat":
        # Nothing state-changing happens here - a client reads this reply's
        # own `quick` field (route_fields, below) and brings its own chat
        # surface to the front itself. The desktop does that today
        # (commands.rs, stream_chat, for its floating face); this file does
        # not know or care which app asked.
        return Result("Here you go.", n)
    if n == "hud_edit":
        # Matched only when the request came from the phone (`_hud_edit`): the
        # HUD's layout is the PC's, and the sentence names the PC's real doors.
        return Result(HUD_EDIT_PHONE, n)
    if n == "approval_where":
        # A typed (or spoken) word cannot approve anything - rule 4 - so this
        # answers the question the owner is really asking: where IS the
        # control. Deliberately NO field here but this intent's own name:
        # nothing a client could read as a decision, and no button in the
        # sentence. A chat reply that could action a card would be worse than
        # the silence it replaces.
        #
        # The intent's own name travels in X-Jarvis-Route's `quick`
        # field, exactly as `open_chat`'s does, and that is all a client
        # needs: the desktop adds the second half - WHICH card is waiting,
        # or that none is - from the state it already holds.
        # WHICH card is waiting (its own approval window knows), or that none
        # is. That is why this half needs nothing from the live backend's
        # gate, which this repository does not carry.
        return Result(
            "Approvals are decided on the card itself - the Jarvis approval "
            "window on this PC, with your fingerprint for a risky one. "
            "Typing or saying a decision here cannot approve anything, and "
            "that is on purpose.", n)
    if n == "note_read":
        return _run_note_read(intent.f.get("title") or "")
    if n == "note_search":
        return _run_note_search(intent.f.get("needle") or "")
    if n == "note_open":
        return _run_note_open(intent.f.get("title") or "")
    if n == "open_app":
        # "open Notion", "open settings", "open Jarvis settings"
        # (jarvis_open.py, 2026-10-10). Nothing is opened from here: the app
        # that heard the owner's words reads `open_app` off its own route
        # line (route_fields below) and opens it. The desktop does that in
        # Rust through the Windows shell; the phone cannot, so it says so -
        # which is also why the sentence says "on this PC".
        #
        # D4 (the live campaign of 2026-10-25, architect ruling Q6): the
        # sentence no longer promises what this half cannot know. A REFUSED
        # sentence ("run a command shell and show me ipconfig", "open notepad
        # and type hello") carries no route field at all - there is nothing
        # for any client to open - and a name in the owner's own words is
        # "I have asked this PC to open ..." rather than "Opening ...", with
        # the desktop's own failure line being the half that knows.
        import jarvis_open as OPEN
        opened = intent.f.get("opened")
        if opened is None:
            return Result("I could not tell what to open.", n)
        if opened.kind == "refused":
            return Result(opened.said, n)
        if opened.kind == "answer":
            # The honest fallback (2026-10-31): the words named a place this
            # PC has no door to ("open settings, sound" - no such Jarvis
            # section), so the sentence says so and NO route field rides with
            # it. Nothing is opened, so nothing may be claimed.
            return Result(opened.said, n)
        here = True
        phone = False
        try:
            import jarvis_surface as S
            surface = S.current()
            if surface == S.PHONE:
                phone = True
                here = False
            elif surface == S.DESKTOP:
                here = True
        except Exception:
            phone = False
        if not phone:
            try:
                import jarvis_owner_check as OC
                here = bool(OC.from_this_pc(peer, local))
            except Exception:
                here = True
        if phone and opened.kind in ("brain", "jarvis"):
            # 2026-10-31, the owner's "Jarvis knows which app I am talking
            # from" requirement: the phone cannot open a window on the PC, and
            # its own Brain / Settings are real doors of its own. The words
            # name those, and NO route field rides with the answer (there is
            # nothing for the phone to open on the PC).
            return Result(PHONE_OPEN_WORDS[opened.kind], n)
        if opened.kind == "brain":
            # Jarvis's own window (2026-10-31): "open the second brain",
            # "open history", "open tutorials", "open my notes". The route's
            # EXISTING `open_brain` field carries the place the desktop
            # already opens (main.js openBrainFromRoute, the HUD's injected
            # bootstrap, plain_errors.rs open_fix_place) - no new field, no
            # new command, and no route change.
            return Result(OPEN.words(opened, this_pc=here), n,
                          open_brain=opened.target)
        return Result(OPEN.words(opened, this_pc=here), n,
                      open_app=(None if opened.kind == "jarvis" else opened.target),
                      open_app_kind=opened.kind,
                      open_app_built=(opened.kind == "app" and opened.built),
                      open_place=(opened.target if opened.kind == "jarvis" else None),
                      open_app_note=opened.note or None)
    if n.startswith("media_"):
        return _run_media(intent)
    if n.startswith("next_time_"):
        return _run_next_time(intent, sched)
    if n == "next_up":
        return _run_next_up(intent, sched)
    if n.startswith("today_"):
        return _run_today(intent, sched)
    if n in ("time_now", "date_today", "clock_both"):
        return _run_clock(intent, now)
    if n in ("wellbeing_now", "wellbeing_me"):
        return _run_wellbeing(intent)
    if n == "pc_help":
        return _run_pc_help(intent)
    if n in ("phone_ring", "phone_stop"):
        return _run_find_phone(intent)
    if n.startswith("lockdown_"):
        return _run_lockdown(intent, peer, local)
    if n.startswith("screen_"):
        return _run_screen(intent, peer, local)
    if n.startswith("tellme_"):
        return _run_tellme(intent, sched, now)
    if n == "project_log":
        return _run_project_log(f, now)
    if n.startswith("focus_"):
        return _run_focus(intent)
    if n == "timer_set":
        try:
            j = sched.add_timer(f["seconds"], f.get("label", ""), source="quick")
        except (ValueError, OverflowError) as exc:
            return Result(S._sentence(exc), n)
        what = f"{j['text'].capitalize()} timer" if j.get("text") else "Timer"
        name = f"the {j['text']} timer" if j.get("text") else \
            f"the {_as_adjective(S.length_words(f['seconds']))} timer"
        return Result(_timer_confirmation(f["seconds"], j.get("text") or ""), n,
                      [j["id"]], made=[j["id"]], what=name, nouns=("timer",))
    if n in ("timer_cancel", "timer_pause", "timer_resume", "timer_add", "timer_status"):
        timers = sched.timers()
        if n == "timer_status":
            if not timers:
                if f.get("bare") and _focus_on():
                    # "how long is left?" with no timer, in a focus session
                    return _run_focus(Intent("focus_status"))
                return None if f.get("bare") else Result("No timer is running.", n)
            if f.get("length") or f.get("label"):
                t, why = _pick_timer(timers, f)
                if t is None:
                    return Result(why, n)
                timers = [t]
            if len(timers) == 1:
                t = timers[0]
                left = S.length_words(t.get("left") or 0)
                return Result(f"{left} left" + (" (paused)." if t["state"] == "paused" else "."),
                              n, [t["id"]])
            parts = [f"{_timer_name(t)}: {S.length_words(t.get('left') or 0)} left"
                     + (" (paused)" if t["state"] == "paused" else "") for t in timers[:4]]
            return Result("; ".join(parts) + ".", n, [t["id"] for t in timers[:4]])
        if n == "timer_add" and f.get("bare") and not timers:
            return None     # "5 more minutes" with no timer: not ours
        if n == "timer_resume":
            timers = [t for t in timers if t["state"] == "paused"] or timers
        if n == "timer_pause":
            timers = [t for t in timers if t["state"] == "active"] or timers
        t, why = _pick_timer(timers, f)
        if t is None:
            return Result(why, n)
        do = {"timer_cancel": "delete", "timer_pause": "pause", "timer_resume": "resume",
              "timer_add": "add_time"}[n]
        code, out = sched.act(t["id"], do, f.get("seconds"))
        if code != 200:
            return Result(out.get("error") or "That did not work.", n)
        if n == "timer_cancel":
            return Result(f"{_timer_name(t).capitalize()} cancelled.", n, [t["id"]])
        if n == "timer_pause":
            return Result(f"Paused, with {S.length_words(t.get('left') or 0)} left.", n, [t["id"]])
        if n == "timer_resume":
            return Result("Resumed.", n, [t["id"]])
        verb = "Added" if f["seconds"] > 0 else "Took off"
        return Result(f"{verb} {S.length_words(abs(f['seconds']))}. {out['said']}", n, [t["id"]])
    if n == "alarm_set":
        w: When = f["when"]
        return _set_at("alarm", w, "", sched, now, n)
    if n == "alarm_cancel":
        alarms = [j for j in sched.listed() if j["kind"] == "alarm"]
        if f.get("clock") is not None:
            c = f["clock"]
            hours = _hour24(c, None)
            alarms = [a for a in alarms if a.get("due") is not None
                      and (time.localtime(a["due"]).tm_hour, time.localtime(a["due"]).tm_min)
                      in {(h, c.mm) for h in hours}]
        if not alarms:
            return Result("There is no alarm like that set." if f.get("clock") else
                          "No alarm is set.", n)
        if len(alarms) > 1:
            names = _join(_alarm_words(a, now) for a in alarms[:4])
            return Result(f"You have {len(alarms)} alarms: {names}. Say which one, like "
                          f"\"cancel the {S.clock(alarms[0]['due'])} alarm\".", n) \
                if alarms[0].get("due") else Result("Delete it under Coming up.", n)
        code, out = sched.act(alarms[0]["id"], "delete")
        if code != 200:
            return Result(out.get("error") or "That did not work.", n)
        return Result(f"Alarm for {_alarm_words(alarms[0], now)} cancelled.", n, [alarms[0]["id"]])
    if n == "alarm_list":
        alarms = [j for j in sched.listed() if j["kind"] == "alarm"]
        if not alarms:
            return Result("No alarm is set.", n)
        words = _join(_alarm_words(a, now) for a in alarms[:5])
        return Result(("One alarm: " if len(alarms) == 1 else f"{len(alarms)} alarms: ")
                      + words + ".", n, [a["id"] for a in alarms[:5]])
    if n == "reminder_set":
        return _set_at("reminder", f["when"], f["text"], sched, now, n)
    if n == "todo_add":
        key = f.get("list")
        if key:
            return _add_to_list(f, key, sched)
        try:
            j = sched.add_todo(f["text"], source="quick")
        except (ValueError, OverflowError) as exc:
            return Result(S._sentence(exc), n)
        if j.get("already"):
            return Result("That is already on your to-do list.", n, [j["id"]])
        return Result("Added to your to-do list.", n, [j["id"]], made=[j["id"]],
                      what="the item just added to your to-do list", nouns=("item",))
    if n == "todo_list":
        key = f.get("list")
        title = _list_words(key)
        items = [i for i in sched.todos() if (i.get("list") or None) == key]
        others = ""
        if not key:
            try:
                names = [lst["title"] for lst in sched.lists()]
            except Exception:
                names = []
            if names:
                others = " Other lists: " + _join(_lower(t) for t in names) + "."
        if not items:
            return Result(f"Your {title} is empty." + others, n, private=bool(others))
        texts = [i["text"] for i in items]
        if len(texts) > 8:
            return Result(f"{len(texts)} things on your {title}. The first 8: "
                          f"{_join(texts[:8])}." + others, n, [i["id"] for i in items[:8]],
                          private=True)
        head = f"One thing on your {title}: " if len(texts) == 1 else f"Your {title}: "
        return Result(head + _join(texts) + "." + others, n, [i["id"] for i in items],
                      private=True)
    if n in ("todo_done", "todo_remove"):
        items = sched.todos()
        if f.get("named"):
            # A list was named ("... from the shopping list"): only that one.
            items = [i for i in items if (i.get("list") or None) == f.get("list")]
        want = f["text"].lower().strip()
        want = re.sub(r"^(?:the|my)\s+", "", want)
        exact = [i for i in items if i["text"].lower() == want
                 or re.sub(r"^(?:the|my)\s+", "", i["text"].lower()) == want]
        pool = exact or [i for i in items if want and want in i["text"].lower()]
        if not pool:
            return None     # nothing on the list is called that: not ours
        if len(pool) > 1:
            return Result(f"Which one: {_join(repr_q(i['text']) for i in pool[:4])}?", n,
                          private=True)
        code, out = sched.act(pool[0]["id"], "done" if n == "todo_done" else "delete")
        if code != 200:
            return Result(out.get("error") or "That did not work.", n)
        return Result("Marked done." if n == "todo_done"
                      else f"Removed from your {_list_words(pool[0].get('list') or None)}.",
                      n, [pool[0]["id"]])
    return None


def _lower(s: str) -> str:
    return s[:1].lower() + s[1:]


def _as_adjective(length: str) -> str:
    """"10 minutes" -> "10 minute" (the 10 minute timer)."""
    return re.sub(r"\b(hour|minute|second)s\b", r"\1", length)


def _list_words(key) -> str:
    """"to-do list", "shopping list" - as said in a sentence."""
    import jarvis_schedule as S
    return _lower(S.list_title(key))


def _add_to_list(f: dict, key: str, sched) -> Result:
    """One or more items on a named list. Items already there are not added
    twice, and "cancel that" takes back only the ones added now."""
    import jarvis_schedule as S
    n = "todo_add"
    title = _list_words(key)
    items = f.get("items") or [f["text"]]
    made, already = [], 0
    for text in items:
        try:
            j = sched.add_todo(text, source="quick", list_name=key)
        except (ValueError, OverflowError) as exc:
            if made:
                break
            return Result(S._sentence(exc), n)
        if j.get("already"):
            already += 1
        else:
            made.append(j["id"])
    if not made:
        return Result(f"That is already on your {title}." if already == 1
                      else f"Those are already on your {title}.", n)
    if len(made) == 1 and not already:
        said, what = f"Added to your {title}.", f"the item just added to your {title}"
    else:
        said = f"Added {len(made)} item{'s' if len(made) != 1 else ''} to your {title}."
        if already:
            said += (" 1 was already on it." if already == 1 else f" {already} were already on it.")
        what = (f"the {len(made)} items just added to your {title}" if len(made) > 1
                else f"the item just added to your {title}")
    return Result(said, n, list(made), made=list(made), what=what, nouns=("item",))


#: Both apps' words for where a whole list is cleared (coming-up.js,
#: net/Schedule.kt): "Clear list" under the list, which asks first.
LIST_CLEAR_IN_APP = ("Clearing a whole list is done in the app, where it asks \"are you sure?\" "
                     "first: Coming up, under the {title}, Clear list. Nothing was changed.")


def _run_lists(intent: Intent, sched) -> Result:
    n = intent.name
    try:
        lists = list(sched.lists())
    except Exception:
        lists = []
    if n == "list_clear":
        key = intent.f.get("list")
        found = [lst for lst in lists if lst.get("name") == key]
        title = _list_words(key)
        if not found:
            return Result(f"There is nothing on your {title}.", n)
        return Result(LIST_CLEAR_IN_APP.replace("{title}", title), n)
    if not lists:
        return Result("You have no other lists - only your to-do list. Say \"add milk to the "
                      "shopping list\" to start one.", n)
    words = _join(f"{_lower(lst['title'])} ({lst['open']} item{'s' if lst['open'] != 1 else ''})"
                  for lst in lists)
    return Result(f"Your lists, besides the to-do list: {words}.", n, private=True)


def _snooze_name(j: dict) -> str:
    import jarvis_schedule as S
    kind = j.get("kind")
    if kind == "timer":
        if j.get("text"):
            return f"{j['text']} timer"
        return f"{_as_adjective(S.length_words(j.get('duration') or 0))} timer"
    return kind or "reminder"


def _run_snooze(f: dict, sched, now: float) -> Result:
    """The timer, alarm or reminder that went off most recently (the last
    hour), again after the snooze - a one-off copy, no card."""
    import jarvis_schedule as S
    n = "snooze"
    try:
        went = list(sched.went_off(now))
    except Exception:
        went = []
    if f.get("kind"):
        went = [j for j in went if j.get("kind") == f["kind"]]
    if not went:
        # Already snoozed in the last hour: say until when, change nothing.
        try:
            copies = [j for j in sched.listed() if j.get("snoozed") and j.get("state") == "active"
                      and j.get("due") is not None and now - float(j.get("created") or 0)
                      <= S.WENT_OFF_SHOWN and (not f.get("kind") or j.get("kind") == f["kind"])]
        except Exception:
            copies = []
        if copies:
            j = max(copies, key=lambda x: x.get("created") or 0)
            return Result(f"The {_snooze_name(j)} is already snoozed until {S.clock(j['due'])}. "
                          f"Delete or pause it under Coming up to change that.", n, [j["id"]])
        what = f"{f['kind']} " if f.get("kind") else ""
        return Result(f"No {what}went off in the last hour, so there is nothing to snooze."
                      if what else "Nothing went off in the last hour, so there is nothing "
                                   "to snooze.", n)
    j = went[0]
    code, out = sched.snooze(j["id"], f.get("seconds"))
    if code != 200:
        return Result(out.get("error") or "That did not work.", n)
    name = _snooze_name(j)
    copy = out.get("job") or {}
    if out.get("already"):
        return Result(f"The {name} is already snoozed - {_lower(out['said'])}", n, [j["id"]])
    seconds = f.get("seconds") or S.SNOOZE_DEFAULT
    until = S.clock(copy["due"]) if copy.get("due") else ""
    return Result(f"Snoozed the {name} for {S.length_words(seconds)}"
                  + (f" - until {until}." if until else "."), n, [copy.get("id") or j["id"]],
                  made=[copy["id"]] if copy.get("id") else [], what="the snooze",
                  nouns=("snooze", j.get("kind") or ""))


UNDO_NOTHING_LEFT = "It is not on the list any more, so there was nothing to cancel."
#: Said when there is genuinely nothing of this fast path's to take back, and
#: the owner said a COMMAND ("cancel that", "undo") rather than "never mind" -
#: which is ordinary words too and still goes to the model (D6, 2026-10-25).
UNDO_NOTHING_SAID = "Nothing of mine to cancel."

#: The answers that change NOTHING at all - so they must not take away what
#: "cancel that" would take back (D6, the live campaign of 2026-10-25).
#:
#: The campaign's row 7: "Remind me next time ..." -> "what will you remind me
#: of next time?" (a read) -> "cancel that" fell to the model for 69.6 s and
#: left the reminder in place. The read had wiped the record. Every name here
#: was checked against `run()` below: none of them writes a job, a setting, a
#: file or a memory. Media control is here because playing or pausing is not
#: something "cancel that" can take back either - it is not a thing this fast
#: path SET.
#:
#: Deliberately a list of READ-ONLY answers rather than of state-changing ones:
#: an intent added later, and forgotten here, keeps the old safe behaviour
#: (the record is dropped, so "cancel that" can never take back something the
#: owner did not just do).
#: The Android-builder answers (2026-10-31): fixed words, no card.
_ANDROID_INTENTS = frozenset({"android_capability", "android_howto", "android_needs",
                              "android_build_install"})

#: The plug-in answers (2026-10-31): fixed words, no card.
_PLUGIN_INTENTS = frozenset({"plugin_list", "plugin_state", "plugin_about", "plugin_install"})

#: The reminders capability answers (2026-10-31): fixed words, no card.
_REMINDER_INTENTS = frozenset({
    "reminder_capability", "reminder_popup", "reminder_sound", "reminder_notify",
    "reminder_closed", "reminder_howto",
})

READ_ONLY_INTENTS = frozenset({
    "android_capability", "android_howto", "android_needs", "android_build_install",
    "plugin_list", "plugin_state", "plugin_about", "plugin_install",
    "alarm_list", "reminder_capability", "reminder_popup", "reminder_sound",
    "reminder_notify", "reminder_closed", "reminder_howto", "animal_ask", "approval_where", "briefing_list", "briefing_now",
    "bulk", "chat_tag", "clock_both", "control_ask", "control_bad", "date_today",
    # "connect my calendar" / "set up a calendar bridge for me" (2026-10-28): a
    # fixed answer that reads this PC's own settings and connects nothing, so it
    # must not take away what "cancel that" would undo.
    "calendar_setup",
    # The HUD field test's three answers (2026-10-29): the Google/Gmail paths,
    # which voice is speaking, and how a phone is paired. Each one only reads
    # and explains - no card is raised, no value is typed, no voice changes -
    # so none may clear "cancel that". ("change your voice to Ashby" is the
    # settings grammar's own bad-value answer, already listed below.)
    "accounts_connect", "voice_ask", "pair_phone",
    # Notes and the vault, asked in chat (2026-10-31 field test). The organizer
    # answer only reads the planner's own state/plan, and the two refusals write
    # nothing - so none may clear what "cancel that" would take back. The note
    # WRITE results (`note_made`, `note_make_waiting`) are deliberately NOT
    # here: the daily note may have changed, so the old record goes; a note that
    # was refused wrote nothing, so `note_make_refused` is read-only.
    "vault_organizer_plan", "vault_organizer_scoped", "note_change_refused",
    "obsidian_style_refused", "note_make_refused", "note_read_honest",
    # main's feature answers (2026-10-31, #1030): the capability answer reads
    # the catalogue and changes nothing, so it must not clear "cancel that".
    "face_ask", "feature_capabilities", "feature_change", "feature_change_ask",
    "feature_change_refused",
    "feature_explain", "feature_howto", "feature_howto_setting",
    "feature_limits", "feature_asks", "feature_app", "feature_why",
    "feature_difference", "feature_overview",
    # Detail shapes (2026-10-31): they only read the catalogue row and the
    # guide's state, and change nothing.
    "feature_detail", "feature_can_do",
    "feature_state", "feature_state_setting", "feature_switch_refused",
    "feature_unknown", "setting_explain",
    # The local calendar read and the honest off / app-only / unbuilt
    # sentences (2026-10-31, pass 11): they read the real state and say it,
    # change nothing, so they must not take away what "cancel that" would undo.
    "honest_chat", "local_calendar_read", "honest_state",
    "features_group", "features_list", "focus_status", "identity_help", "list_clear",
    "lists_which", "lockdown_status", "media_next", "media_now", "media_pause",
    "media_play", "media_previous", "missed", "news_list", "news_read", "note_read", "note_search", "note_open",
    "next_time_list",
    "next_up",
    # "can you process all my Notion notes into Obsidian?" (2026-10-28): a
    # fixed answer that reads nothing and imports nothing, so it must not
    # clear what "cancel that" would take back.
    "notion_export",
    # "find cheap parking near ..." (2026-10-30): it calls two public map
    # services and a local cache, opens no card and changes nothing, so it must
    # not clear what "cancel that" would take back.
    "parking_calendar", "parking_lookup",
    "open_app", "open_chat", "pc_help", "personality_create",
    "personality_create_failed", "personality_create_help",
    "personality_create_refused", "personality_describe", "personality_refine",
    "personality_refine_failed", "personality_show", "personality_show_missing",
    "personality_status", "project_log",
    "reach_list", "sayable_help", "screen_status", "search_explain", "settings_choice_bad",
    "settings_choice_help", "settings_help", "settings_not_by_asking", "settings_only",
    "settings_browser_mode_bad",
    # Reading the Anti-Slop filter (2026-10-28): "is anti-slop on?" changes
    # nothing, so "cancel that" must not lose its record to it. Its change and
    # refusal intents are NOT here - they write or refuse, like every other one.
    "settings_antislop_state", "settings_antislop_bad",
    "settings_open", "settings_unknown", "tellme_help", "thinking_status", "thinking_when",
    "time_now", "timer_status", "today_list", "todo_list", "weather_now", "wellbeing_me",
    "wellbeing_now", "where_put",
    # Updates in chat (2026-10-26): these two only read the public release
    # manifest and answer. "update_start" is deliberately NOT here: it raises a
    # card, so "cancel that" must not reach back past it.
    "update_ask", "update_notes"})


def _run_undo(f: dict, sched, now: float, conversation) -> Optional[Result]:
    """"Cancel that": the last thing the fast path set in THIS conversation,
    within UNDO_WINDOW, once. Nothing else, ever."""
    import jarvis_schedule as S
    n = "undo"
    noun = f.get("noun")
    rec = None
    try:
        rec = sched.last_set(conversation, now) if conversation else None
    except Exception:
        rec = None
    fits = rec is not None and (noun is None or noun in (rec.get("nouns") or ()))
    if rec is None or not fits:
        # Nothing of ours to take back. "cancel that timer" / "... alarm"
        # still mean what they meant before this existed.
        if noun == "timer":
            return run(Intent("timer_cancel", {}), sched, now)
        if noun == "alarm":
            return run(Intent("alarm_cancel", {}), sched, now)
        if rec is not None and noun is not None:
            kind = next(iter(rec.get("nouns") or ("thing",)))
            return Result(f"The last thing set here was {_a(kind)}, not {_a(noun)}, so nothing "
                          f"was cancelled.", n)
        # D6 (the live campaign of 2026-10-25): a COMMAND with nothing to take
        # back is answered here, in one line, instead of being handed to the
        # model for a minute of guessing. "never mind" keeps going to the
        # model: it is ordinary words as well as a command, and a chat that
        # answers it with "Nothing of mine to cancel." would read as a machine
        # that did not listen.
        if f.get("soft"):
            return None
        return Result(UNDO_NOTHING_SAID, n)
    minutes = int(S.UNDO_WINDOW // 60)
    if rec["age"] > S.UNDO_WINDOW:
        if f.get("soft"):
            return None
        sched.forget_set(conversation)
        return Result(f"That was more than {minutes} minutes ago, so nothing was cancelled - "
                      f"delete it under Coming up.", n)
    sched.forget_set(conversation)
    views = [sched.job(i) for i in rec["ids"]]
    waiting = any(v and v.get("state") == "waiting" for v in views)
    if not sched.take_back(rec["ids"]):
        return Result(UNDO_NOTHING_LEFT, n)
    what = rec.get("what") or "it"
    if rec.get("intent") == "todo_add":
        return Result(f"Removed {what}.", n, list(rec["ids"]))
    said = f"Cancelled: {what}."
    if waiting:
        said += " Its approval card will set nothing up."
    return Result(said, n, list(rec["ids"]))


def _a(noun: str) -> str:
    return ("an " if noun[:1] in "aeiou" else "a ") + noun


def _run_missed(sched, now: float, seen: Optional[float]) -> Result:
    """"What did I miss?" - the briefing's builder, since the owner last
    talked to Jarvis. Reads only; private, like the briefing."""
    n = "missed"
    try:
        import jarvis_briefing as B
    except Exception:
        return Result(BRIEFING_MISSING, n)
    b = B.build_missed(sched=sched, now=now, since=seen)
    return Result(b["text"], n, private=True, read=list(b.get("read") or []))


def repr_q(text: str) -> str:
    return f"\"{text}\""


def _alarm_words(a: dict, now: float) -> str:
    import jarvis_schedule as S
    if a.get("repeats"):
        return a.get("repeat") or "a repeating alarm"
    if a.get("due") is None:
        return "an alarm"
    return S.when_words(a["due"], now)


def _twelve_note(hour: Optional[int], minute: int) -> str:
    """When the owner said a "12" with no am/pm (or "12 at night"), the time is
    said back as "12:00 midnight" or "12:00 noon", with how to get the other."""
    if hour not in (0, 12):
        return ""
    word, other = ("midnight", "12 noon") if hour == 0 else ("noon", "midnight")
    return f" That is 12:{minute:02d} {word}. If you meant the other, say \"{other}\"."


def _set_at(kind: str, w: When, text: str, sched, now: float, n: str) -> Result:
    r = _set_at_plain(kind, w, text, sched, now, n)
    if w.said12 and r.ids:
        if w.rule is not None:
            hh, _, mm = str(w.rule.get("at") or "").partition(":")
            note = _twelve_note(int(hh) if hh.isdigit() else None, int(mm) if mm.isdigit() else 0)
        else:
            lt = time.localtime(w.at)
            note = _twelve_note(lt.tm_hour, lt.tm_min)
        r.reply += note
    return r


def _set_at_plain(kind: str, w: When, text: str, sched, now: float, n: str) -> Result:
    import jarvis_schedule as S
    noun = "Alarm" if kind == "alarm" else "Reminder"
    if w.rule is not None:
        try:
            j = sched.add_repeat(kind, w.rule, text, source="quick")
        except (ValueError, OverflowError) as exc:
            return Result(S._sentence(exc), n)
        words = S.rule_words(j.get("rule") or w.rule)
        what = f"the repeating {kind} ({words})"
        if j.get("state") == "waiting":
            return Result(f"That repeats ({words}), so there is an "
                          f"approval card for it on your screen. {UNTIL_APPROVED}", n,
                          [j["id"]], made=[j["id"]], what=what, nouns=(kind,))
        # A plain repeat needs no card (2026-09-26): set up now, and the
        # answer says when it next goes off, as the card used to.
        return Result(S.repeat_set_words(j, now), n, [j["id"]], made=[j["id"]], what=what,
                      nouns=(kind,))
    if w.passed:
        return Result(f"{S.when_words(w.at, now)} has already passed. Say another time.", n)
    try:
        j = sched.add_at(kind, w.at, text, source="quick")
    except (ValueError, OverflowError) as exc:
        return Result(S._sentence(exc), n)
    what = f"the {kind} for {S.when_words(w.at, now)}"
    if w.at - now < 3600 and kind == "reminder" and not w.default_time:
        return Result(f"{noun} set for {S.clock(w.at)}, in {S.length_words(w.at - now)}.",
                      n, [j["id"]], made=[j["id"]], what=what, nouns=(kind,))
    return Result(f"{noun} set for {S.when_words(w.at, now)}.", n, [j["id"]],
                  made=[j["id"]], what=what, nouns=(kind,))


BRIEFING_MISSING = ("Your PC's Jarvis does not have the morning briefing yet - run "
                    "apply-patches.ps1 on the PC.")


def _briefing_words(j: dict, now: float) -> str:
    import jarvis_schedule as S
    if j.get("repeats"):
        words = j.get("repeat") or "a repeating briefing"
        if j.get("state") == "waiting":
            words += " (waiting for your yes on the approval card)"
        elif j.get("state") == "paused":
            words += " (paused)"
        return words
    if j.get("due") is None:
        return "a briefing"
    return S.when_words(j["due"], now)


def _run_weather(now: float) -> Optional[Result]:
    """"What's the weather?" from the owner's own Home Assistant - the
    briefing's own read (jarvis_briefing.weather_now), no model. Not
    private (nothing of the owner's is in it), but the forecast is outside
    text, so `read` marks the conversation as having read Home Assistant.
    A PC without the briefing module hands the question to the model."""
    try:
        import jarvis_briefing as B
    except Exception:
        return None
    try:
        got = B.weather_now(now=now)
    except Exception:
        return None
    return Result(str(got.get("text") or ""), "weather_now", read=list(got.get("read") or []))


def _run_news() -> Optional[Result]:
    """"Read me the news" - the owner's own listed feeds
    (jarvis_news.sentence), no model. Headlines are outside text, so `read`
    marks the conversation as having read a news feed."""
    try:
        import jarvis_news as NEWS
    except Exception:
        return None
    try:
        got = NEWS.sentence()
    except Exception:
        return None
    return Result(str(got.get("said") or ""), "news_read", read=list(got.get("read") or []))


NEWS_MISSING = "Your PC's Jarvis cannot show news feeds yet - run apply-patches.ps1 on the PC."


def _run_news_add(url: str) -> Optional[Result]:
    """"Add this feed: <url>" - ONE approval card (jarvis_news.request_add),
    the same shape as "tell me when" setting up a watch. Only the owner's
    own words: a pasted or shared address still raises this same one card,
    since news feeds are never learned from outside text either way."""
    try:
        import jarvis_news as NEWS
    except Exception:
        return Result(NEWS_MISSING, "news_add")
    try:
        code, out = NEWS.request_add({"url": url})
    except Exception as exc:
        return Result(f"Jarvis could not add that feed ({type(exc).__name__}).", "news_add")
    if code == 200:
        return Result(str(out.get("message") or "That feed is already listed."), "news_add")
    if code in (400, 409, 503):
        return Result(str(out.get("error") or "That address could not be added."), "news_add")
    return Result("That needs your yes on the approval card, which shows the address in full. "
                  "Then your morning briefing (and \"read me the news\") can show its "
                  "headlines - never the article text.", "news_add")


def _run_news_remove(url: str) -> Optional[Result]:
    """"Remove that feed: <url>" - at once, no card."""
    try:
        import jarvis_news as NEWS
    except Exception:
        return Result(NEWS_MISSING, "news_remove")
    try:
        _code, out = NEWS.request_remove({"url": url})
    except Exception as exc:
        return Result(f"Jarvis could not remove that feed ({type(exc).__name__}).", "news_remove")
    return Result(str(out.get("message") or ""), "news_remove")


def _run_news_list() -> Optional[Result]:
    try:
        import jarvis_news as NEWS
    except Exception:
        return Result(NEWS_MISSING, "news_list")
    listed = NEWS.feeds()
    if not listed:
        return Result(NEWS.EMPTY, "news_list")
    return Result("\n".join(f"- {u}" for u in listed), "news_list")


def _briefing_without_repeats(text: str) -> str:
    """The briefing's lines with a Pulse line that repeats a section dropped.

    R3 of the live campaign (2026-10-25) printed "Today: Nothing else set for
    today." and then "Pulse: Nothing else set for today." - the Pulse is built
    from the same summaries the sections above already said, so on a quiet day
    the whole Pulse half is those two lines said twice.

    Conservative on purpose, and only about EXACT repeats: a "Pulse: X" line is
    dropped when some earlier line already ends in exactly X ("<Title>: X").
    Nothing is reworded, reordered or summarised, and a Pulse line that adds
    anything at all stays.
    """
    if not text:
        return text
    lines = text.split("\n")
    summaries = set()
    for line in lines:
        head, sep, tail = line.partition(": ")
        if sep and head and not head.startswith(("Pulse", "-", "(", " ")):
            summaries.add(" ".join(tail.split()))
    if not summaries:
        return text
    kept = []
    for line in lines:
        if line.startswith("Pulse: ") and " ".join(line[len("Pulse: "):].split()) in summaries:
            continue
        kept.append(line)
    return "\n".join(kept)


def _run_briefing(intent: Intent, sched, now: float) -> Result:
    """The morning briefing: put one together now (reads only - no card), set
    one up (a repeat: the scheduler's ONE card; once: no card), stop ONE, or
    say when."""
    import jarvis_schedule as S
    n, f = intent.name, intent.f
    try:
        import jarvis_briefing as B
    except Exception:
        return Result(BRIEFING_MISSING, n)
    if n == "briefing_now":
        b = B.make(sched=sched, now=now, source="chat")
        # Private: it quotes the calendar, reminders and the to-do list, so a
        # spoken question's answer stays on screen under the apps' rule.
        # `_briefing_without_repeats`: the Pulse half repeats the section lines
        # word for word on a quiet day (D11a, the live campaign of 2026-10-25).
        return Result(_briefing_without_repeats(str(b["text"] or "")), n,
                      private=True, read=list(b.get("read") or []))
    jobs = B.setups(sched)
    if n == "briefing_list":
        if not jobs:
            return Result("No briefing is set up. Say \"brief me every weekday at 7\" to set "
                          "one up, or \"brief me now\".", n)
        words = _join(_briefing_words(j, now) for j in jobs[:4])
        return Result(("Your morning briefing: " if len(jobs) == 1
                       else f"{len(jobs)} briefings: ") + words + ".", n,
                      [j["id"] for j in jobs[:4]])
    if n == "briefing_cancel":
        if not jobs:
            return Result("No briefing is set up.", n)
        if len(jobs) > 1:
            words = _join(_briefing_words(j, now) for j in jobs[:4])
            return Result(f"You have {len(jobs)} briefings set up: {words}. Delete the one you "
                          f"mean under Coming up.", n)
        code, out = sched.act(jobs[0]["id"], "delete")
        if code != 200:
            return Result(out.get("error") or "That did not work.", n)
        return Result(f"Stopped your briefing ({_briefing_words(jobs[0], now)}).", n,
                      [jobs[0]["id"]])
    # briefing_set
    w: When = f["when"]
    if w.rule is not None:
        try:
            j = sched.add_repeat(B.KIND, w.rule, "", source="quick")
        except (ValueError, OverflowError) as exc:
            return Result(S._sentence(exc), n)
        words = S.rule_words(j.get("rule") or w.rule)
        return Result(f"That repeats ({words}), so there is an "
                      f"approval card for it on your screen. {UNTIL_APPROVED}", n, [j["id"]],
                      made=[j["id"]], what=f"the repeating briefing ({words})",
                      nouns=("briefing",))
    if w.passed:
        return Result(f"{S.when_words(w.at, now)} has already passed. Say another time.", n)
    try:
        j = sched.add_at(B.KIND, w.at, "", source="quick")
    except (ValueError, OverflowError) as exc:
        return Result(S._sentence(exc), n)
    return Result(f"Briefing set for {S.when_words(w.at, now)}.", n, [j["id"]],
                  made=[j["id"]], what=f"the briefing for {S.when_words(w.at, now)}",
                  nouns=("briefing",))


def answer(text, *, sched=None, now: Optional[float] = None,
           conversation: Optional[str] = None, seen: Optional[float] = None,
           temporary: bool = False, private: bool = False, peer=None, local=None,
           messages=None, desktop=None,
           client_surface: Optional[str] = None) -> Optional[Result]:
    """Match and act. None: not ours - ask the model. `conversation`: the
    request's conversation_id, so "cancel that" takes back only what was set
    in it; `seen`: when the owner last talked to Jarvis before this turn;
    `temporary`: a temporary chat (2026-09-27's "from now on ..."); `private`:
    a PRIVATE chat (the architect's H10 ruling, 2026-10-25) - strictly
    reads-only. No state-changing answer runs for it: a mutating intent gets
    back the one refusal sentence BEFORE anything is changed or receipted, and
    a read-only intent goes to the model instead, so this path opens no
    scheduler and writes nothing. An ordinary chat is untouched. `peer`/
    `local`: the request's own address, for a setting on jarvis_owner_check.
    PC_ONLY_ACTIONS (jarvis_settings_registry.py, 2026-09-27)."""
    now = time.time() if now is None else now
    # Chat co-creation of a personality (2026-10-25, jarvis_personality_creator.py):
    # "make me a personality like ..." drafts it with the LOCAL model in the
    # conversation; "save it" stores it through jarvis_manner's own save path.
    # It runs BEFORE the grammar below, so while a draft is pending a plain
    # "save it" cannot be mistaken for anything else. The import is wrapped and
    # a backend without the module keeps exactly the old behaviour.
    try:
        import jarvis_personality_creator as _creator
        _made = _creator.handle(text, conversation=conversation, temporary=temporary)
    except Exception:
        _made = None
    if _made is not None:
        return Result(str(_made.get("reply") or ""),
                      str(_made.get("intent") or "personality_draft"))
    intent = match(text, now)
    if intent is None:
        # GOOGLE CALENDAR: READS AND EVENT CHANGES, AND ONLY THOSE (2026-10-28).
        # Asked HERE - after the fast path has declined - so one sentence has
        # one owner: "connect my calendar" is the connect-account card's (in
        # `_settings_adjust`), a setup shape the card does not claim is
        # `calendar_setup`'s, and the reads and event changes are this one's.
        # `jarvis_google_calendar.answer()` still carries a connect branch;
        # from here it is UNREACHABLE on purpose, because a connect sentence
        # never gets this far - so it cannot compete for "connect".
        # `not private` because a private chat must not reach Google at all
        # (private-chat.patch: reads-only, nothing outside), and the import is
        # inside the guard so a backend without the module is unchanged.
        if not private:
            try:
                import jarvis_google_calendar as _gcal
                _said = _gcal.answer(text)
            except Exception:               # noqa: BLE001 - module absent
                _said = None
            if _said is not None:
                return Result(str(_said), "google_calendar", read=["calendar_read"])
        return None
    if private:
        # private-chat.patch: the whole fast path is OFF in a private chat.
        # Refuse, in words, before a single state change or undo receipt -
        # and do not guess at what a read-only intent may write along the way:
        # hand it to the model like any ordinary question instead.
        if intent.name in READ_ONLY_INTENTS:
            return None
        return Result(_private_refusal(), intent.name, private=True)
    if sched is None:
        import jarvis_schedule
        sched = jarvis_schedule.get()
    res = run(intent, sched, now, conversation=conversation, seen=seen, temporary=temporary,
             peer=peer, local=local, messages=messages, desktop=desktop,
             client_surface=client_surface)
    if res is not None:
        try:
            sched.mark_command(text)
        except Exception:
            pass
        try:
            if res.made and conversation:
                sched.note_set(conversation, res.made, res.what, res.intent, nouns=res.nouns)
            elif res.intent != "undo" and conversation and res.intent not in READ_ONLY_INTENTS:
                # Something else CHANGED since: "cancel that" would now mean
                # THAT, which cannot be taken back - so nothing can.
                #
                # D6 (the live campaign of 2026-10-25). This used to run for
                # EVERY quick answer that created nothing, including a plain
                # read - so after "remind me next time ..." and then "what
                # will you remind me of next time?", "cancel that" no longer
                # meant the reminder: it fell to the model (69.6 s) and the
                # reminder stayed. A read-only answer changes nothing, so it
                # must not take the record away. `READ_ONLY_INTENTS` is the
                # list of answers that change nothing at all; anything not on
                # it (including an intent added later) keeps the old, safe
                # behaviour.
                sched.forget_set(conversation)
        except Exception:
            pass
    return res

# --------------------------------------------------------------------------
#   Manner: warm or plain (2026-09-25)
# --------------------------------------------------------------------------
#
# The owner's decision: warm and brief by default, with a "Plain" option;
# manner changes only how Jarvis phrases things (jarvis_manner.py). The
# sentences run() makes above ARE the plain wording. Each short one has a
# warm wording here, matched on the whole plain sentence, with every part
# that carries a fact (a length, a time, a name, "no", "already") taken over
# word for word - test_manner.py checks both wordings of each carry the same
# facts. Anything not listed (the to-do list read out, a briefing, a card's
# "That repeats..." line, a repeat's "... set up, every ... Next: ..." line,
# an error) is the same in both.

_WARM = [(re.compile(rx), warm) for rx, warm in (
    (r"No timer is running\.", "There's no timer running right now."),
    (r"(?P<left>[^;:().,]+) left \(paused\)\.", "{left} to go - it's paused."),
    (r"(?P<left>[^;:().,]+) left\.", "{left} to go."),
    (r"(?P<name>.+ timer) cancelled\.", "Okay, {name_l} cancelled."),
    (r"Paused, with (?P<left>.+) left\.", "Paused - {left} to go."),
    (r"Resumed\.", "Okay, it's running again."),
    (r"(?P<verb>Added|Took off) (?P<len>[^.]+)\. (?P<rest>.+)", "Okay - {verb_l} {len}. {rest}"),
    (r"No alarm is set\.", "You don't have any alarms set."),
    (r"There is no alarm like that set\.", "I can't find an alarm like that."),
    (r"Alarm for (?P<when>.+) cancelled\.", "Okay, your alarm for {when} is cancelled."),
    (r"One alarm: (?P<when>.+)\.", "You have one alarm: {when}."),
    (r"That is already on your to-do list\.", "That's already on your to-do list."),
    (r"Added to your to-do list\.", "Got it - it's on your to-do list."),
    (r"Your to-do list is empty\.", "Nothing on your to-do list right now."),
    (r"Marked done\.", "Okay, marked done."),
    (r"Removed from your to-do list\.", "Okay, removed from your to-do list."),
    (r"(?P<when>[^.]+) has already passed\. Say another time\.",
     "{when} has already passed - what other time would you like?"),
    (r"No briefing is set up\.", "You don't have a briefing set up."),
    (r"Stopped your briefing \((?P<when>.+)\)\.", "Okay, I've stopped your briefing ({when})."),
    (r"(?P<what>Timer|[^.]+ timer|Alarm|Reminder|Briefing) set for (?P<when>[^;]+)\.",
     "Got it - {what_l} set for {when}."),
)]


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def in_manner(reply: str, manner: Optional[str] = None) -> str:
    """`reply` in the owner's manner: the warm wording when there is one and
    the manner is warm, else `reply` as it is. `manner` None reads the
    setting (jarvis_manner.py); a backend without it keeps the plain words."""
    if manner is None:
        try:
            import jarvis_manner
            manner = jarvis_manner.current()
        except Exception:
            return reply
    if manner != "warm" or not isinstance(reply, str):
        return reply
    for rx, warm in _WARM:
        m = rx.fullmatch(reply)
        if m:
            g = m.groupdict()
            g.update({f"{k}_l": _lower_first(v) for k, v in list(g.items())})
            return warm.format(**g)
    return reply

# --------------------------------------------------------------------------
#   /api/chat
# --------------------------------------------------------------------------

_OWN_WORDS = ("typed", "voice")


def newest_own_words(body) -> Optional[str]:
    """The newest message's words when they are the owner's own and nothing
    else came with them; None otherwise (then the model answers, as before).

    Read off the request AS IT ARRIVED - the provenance tags come off before
    any model sees the messages (chat-history.patch)."""
    if not isinstance(body, dict):
        return None
    msgs = body.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return None
    msgs = [m for m in msgs if isinstance(m, dict)]
    if not msgs:
        return None
    if any(m.get("role") == "system" for m in msgs):
        return None         # the app sent text of its own (audit M1)
    last = msgs[-1]
    if last.get("role") != "user" or last.get("provenance") not in _OWN_WORDS:
        return None
    if len(msgs) > 1 and msgs[-2].get("role") == "user" \
            and msgs[-2].get("provenance") in ("shared", "clipboard"):
        return None         # sent with a share or the clipboard
    content = last.get("content")
    if isinstance(content, list):
        if any(isinstance(p, dict) and p.get("type") not in (None, "text") for p in content):
            return None     # a picture: the model's job
        content = " ".join(str(p.get("text") or "") for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        return None
    return content


_CONVERSATION = re.compile(r"[A-Za-z0-9_-]{8,64}")


def conversation_of(body) -> Optional[str]:
    """The request's conversation_id (JARVIS-API 18.1), or None when there
    is none or it is not one - then "cancel that" has nothing to take back."""
    cid = body.get("conversation_id") if isinstance(body, dict) else None
    return cid if isinstance(cid, str) and _CONVERSATION.fullmatch(cid) else None


def _touch(now: Optional[float]) -> Optional[float]:
    """Note that the owner talked to Jarvis now (for "what did I miss?");
    the time before this one, or None. Never raises."""
    try:
        import jarvis_briefing as B
        return B.touch(now)
    except Exception:
        return None


def answer_turn(body, *, sched=None, now: Optional[float] = None,
                peer=None, local=None, private: Optional[bool] = None,
                client_surface: Optional[str] = None) -> Optional[Result]:
    """For /api/chat: the fast path's answer to this turn, or None. Every
    chat request counts as the owner being here ("what did I miss?" asks
    since the one before), whoever's words it carries. `peer`/`local`: the
    request's own address (schedule.patch's do_POST reads it the same way
    owner-check.patch's own wrapper does) - passed all the way down so a
    setting on jarvis_owner_check.PC_ONLY_ACTIONS can tell this PC's own
    chat from the phone's, exactly as its REST route already does
    (jarvis_settings_registry.py, 2026-09-27). This function never invents
    either value: it hands whatever it was given straight to
    jarvis_owner_check.from_this_pc, unchanged - the SAME function, and the
    SAME "cannot be placed counts as this PC" rule, every other caller of
    that function already lives with. schedule.patch always supplies the
    real address; a caller that omits it (an older test, a script) gets
    that function's own default, not a stricter or looser one made up
    here."""
    # 2026-10-28, the AI-safety audit's finding M1: a crisis turn is NEVER
    # answered by the fast path, and it is decided HERE rather than in one
    # caller. jarvis_hud.py used to run this function BEFORE it asked whether
    # the message was a crisis, so a distress sentence that also fitted this
    # grammar was answered here and the route returned - no 988/911 line, no
    # calm panel, because the header had already gone. Every caller of the
    # fast path inherits this refusal now, including Live and the phone's own
    # chat, and the check is jarvis_wellbeing.crisis_in_turn: the newest user
    # message, whatever its provenance - the same rule the answering turn and
    # the HUD's route header use, so the three cannot disagree.
    #
    # Returning None is what "the fast path has no answer for this turn"
    # already means everywhere (answer_turn's own docstring), so the turn
    # falls through to the local model, which offers no tools on a crisis turn
    # and appends the help text. Nothing is written, touched or counted here.
    try:
        import jarvis_wellbeing
        if jarvis_wellbeing.crisis_in_turn(
                body.get("messages") if isinstance(body, dict) else None):
            return None
    except Exception:
        pass
    # private-chat.patch: a private turn must not even write the "owner was
    # here" touch (jarvis_briefing) or drop this conversation's undo record,
    # so both are skipped below. `private` is derived from the body when the
    # caller did not say (an older hud ignores the flag; enforcing it here
    # anyway is the fail-safe direction), and only JSON `true` counts.
    private = _private_body(body) if private is None else bool(private)
    seen = None if private else (
        _touch(now) if isinstance(body, dict) and body.get("messages") else None)
    conversation = conversation_of(body)
    # "temporary": true (temporary-chat.patch) - the same one-line check
    # jarvis_hud.py's own _temporary_chat(body) makes; needed here for
    # "from now on ..." (2026-09-27), which keeps a temporary chat's style
    # change in that chat only, never written to manner.json.
    temporary = _temporary_body(body)
    text = newest_own_words(body)
    # `desktop`: the app's own report of the build that sent this chat, built
    # in Rust (commands.rs `chat_extras`) and never by a page. The update
    # answers need it, and nothing else reads it (2026-10-26).
    desktop = body.get("desktop") if isinstance(body, dict) else None
    res = None if text is None else answer(text, sched=sched, now=now,
                                           conversation=conversation, seen=seen,
                                           temporary=temporary, private=private,
                                           peer=peer, local=local,
                                           messages=body.get("messages"),
                                           desktop=desktop,
                                           client_surface=client_surface)
    if res is None and conversation and not private:
        # The model answers this turn: "cancel that" after it is about the
        # model's answer, never about a reminder set before it.
        _forget_set(sched, conversation)
    if res is not None:
        # Wording only (jarvis_manner.py): the same facts, the owner's
        # manner - this conversation's own "from now on ..." override when
        # it is a temporary chat that has one, else the PC's saved setting.
        manner = None
        try:
            import jarvis_manner
            manner = jarvis_manner.current(conversation if temporary else None)
        except Exception:
            pass
        res.reply = in_manner(res.reply, manner)
    return res


#: private-chat.patch: the refusal sentence's fallback, byte-identical to the
#: shipped module's REFUSAL (backend/test_private_chat.py asserts the equality,
#: so they cannot drift). The gate itself is one strict inline test, so a
#: backend WITHOUT jarvis_private_chat.py still refuses - a private request
#: must never become an ordinary one because a file is missing.
_PRIVATE_REFUSAL_FALLBACK = (
    "A private chat can read, search, and answer, but it doesn't change "
    "settings, save items, or run actions — switch back to a normal chat "
    "to do that.")


def _private_refusal() -> str:
    """The one refusal sentence: the shipped module's copy, or its
    byte-identical fallback when that module is missing or broken."""
    try:
        import jarvis_private_chat
        return jarvis_private_chat.REFUSAL
    except Exception:
        return _PRIVATE_REFUSAL_FALLBACK


def _private_body(body) -> bool:
    """private-chat.patch: is this request a private chat? FAIL CLOSED: the
    canonical reading is jarvis_private_chat.is_private (JSON `true`, and
    nothing else), and when that module cannot be imported the same one-line
    test is made here rather than answering False. A missing or broken gate
    must refuse the private turn, never turn it into an ordinary one."""
    try:
        import jarvis_private_chat
        return bool(jarvis_private_chat.is_private(body))
    except Exception:
        return isinstance(body, dict) and body.get("private") is True


def _temporary_body(body) -> bool:
    """Is this request a temporary chat? `temporary: true`, or a game or
    role-play the PC has seen in this conversation - the same test the chat
    route makes (jarvis_hud._temporary_chat, games-temporary.patch). This
    path used to read the flag alone, so in a role-play chat "where is my
    passport" was answered from saved memory and "from now on, be plainer"
    was written to manner.json for good (the second chat audit,
    2026-09-28, finding 7, reproduced). Without jarvis_intake: the flag."""
    if _private_body(body):
        # private-chat.patch: a private chat IS a temporary chat for memory,
        # history and learning - plus it refuses every write and every action
        # (the refusal gate in answer() above). Same meaning as
        # jarvis_hud._temporary_chat's own private branch.
        return True
    try:
        import jarvis_intake
        return bool(jarvis_intake.temporary_body(body))
    except Exception:
        return isinstance(body, dict) and body.get("temporary") is True


def _forget_set(sched, conversation) -> None:
    try:
        if sched is None:
            import jarvis_schedule
            sched = jarvis_schedule._SCHED
        if sched is not None:
            sched.forget_set(conversation)
    except Exception:
        pass


def route_fields(res: Result) -> dict:
    """What an answer made here puts in X-Jarvis-Route. It used no memory and
    no model; a reply that reads the owner's list out is `gate: "private"`,
    like notes, so a voice answer stays on screen under the apps' private
    rule."""
    out = {"quick": res.intent, "where": "local", "lane": LANE,
           "inject_memory": False, "injected_facts": 0, "injected_ids": [],
           "injected_sensitive": 0}
    if res.private:
        out["gate"] = "private"
    if res.facts:
        # "Where did I put ...?" (2026-09-28): the answer quotes saved facts,
        # so it says so exactly as a model answer that used memory does -
        # the same "mem:<id>" ids, and how many are sensitive (both apps
        # keep such an answer on screen unless the owner allowed it).
        out["inject_memory"] = True
        out["injected_facts"] = len(res.facts)
        out["injected_ids"] = [f"mem:{int(i)}" for i in res.facts]
        out["injected_sensitive"] = max(0, min(int(res.facts_sensitive), len(res.facts)))
    if res.open_settings:
        # "open <a settings section>" (jarvis_settings_registry.py,
        # 2026-09-27): the section id both apps' Settings screens already
        # use, so either one can jump straight there. Additive only - every
        # existing reader of X-Jarvis-Route that does not look for this key
        # is unaffected, exactly like `gate` above.
        out["open_settings"] = res.open_settings
    if res.open_app or res.open_app_kind == "jarvis":
        # "open Notion", "open settings", "open Jarvis settings"
        # (jarvis_open.py, the owner's request of 2026-10-10): what to open
        # and which kind it is. An app that reads this opens it itself (the
        # desktop, in Rust, through the Windows shell); an app that does not
        # - the phone - shows the answer and opens nothing, and the answer
        # says "on this PC" so that is not a claim it cannot keep. Additive,
        # like open_settings above.
        #
        # `jarvis` carries `open_place` instead of `open_app`: it is the
        # Settings section id, and "" means the top of the window - a real
        # answer that an empty `open_app` could not carry.
        if res.open_app:
            out["open_app"] = res.open_app
        if res.open_app_kind:
            out["open_app_kind"] = res.open_app_kind
        # A boolean, like `inject_memory` above: True when the backend named
        # the program itself (Windows' own accessories), so the app opens it
        # straight away instead of looking it up on this PC's Start menu.
        out["open_app_built"] = bool(res.open_app_built)
        if res.open_app_kind == "jarvis":
            out["open_place"] = res.open_place or ""
        if res.open_app_note:
            out["open_app_note"] = res.open_app_note
    if res.menu_visibility:
        # "Hide the finance menu" (jarvis_menus.py, 2026-09-30): per device, so each
        # app that hears this applies it to its own menu list. Additive, like
        # open_settings; only present when there is something to apply.
        out["menu_visibility"] = dict(res.menu_visibility)
    if res.face_tuning:
        # Sharpness or frame rate (jarvis_animal.DEVICE_CHANGES, 2026-09-28):
        # per device, so the app that asked applies it to itself - the same
        # additive road as open_settings above.
        out["face_tuning"] = res.face_tuning
    if res.open_brain:
        # "Forget a time frame" (jarvis_forget_range.py, 2026-09-28): the
        # Brain place both apps open, with the list already filled in.
        # "open the second brain" / "open history" / "open tutorials" /
        # "open my notes" (2026-10-31) use the same field for the window and
        # its own places - the apps already open those through open_fix_place.
        # Additive, like open_settings.
        out["open_brain"] = res.open_brain
    if res.topic_id is not None:
        # Topic controls (2026-09-30): the picker opens on this topic; nothing
        # has changed yet. Additive, like file_under.
        out["topic_id"] = int(res.topic_id)
    if res.file_under is not None:
        # Chat tags (2026-09-30): "file under <tag id>" with the search words.
        # The apps show the matches and the banner; nothing is filed until
        # the owner taps a chat.
        out["file_under"] = int(res.file_under)
        out["history_q"] = str(res.history_q or "")
    return out


def reply_bytes(reply: str, stream: bool) -> bytes:
    """The whole answer, in the same format a model's answer is sent in
    (jarvis_agent's): Ollama's SSE chunks, or one chat.completion body."""
    cid = f"chatcmpl-jarvis-quick-{int(time.time() * 1000)}"
    created = int(time.time())

    def chunk(delta: dict, finish=None) -> dict:
        return {"id": cid, "object": "chat.completion.chunk", "created": created,
                "model": LANE, "system_fingerprint": "fp_jarvis_quick",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}

    if stream:
        out = b""
        for obj in (chunk({"role": "assistant", "content": reply}), chunk({}, "stop")):
            out += b"data: " + json.dumps(obj, ensure_ascii=False,
                                          separators=(",", ":")).encode("utf-8") + b"\n\n"
        return out + b"data: [DONE]\n\n"
    return json.dumps({
        "id": cid, "object": "chat.completion", "created": created, "model": LANE,
        "system_fingerprint": "fp_jarvis_quick",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                     "finish_reason": "stop"}],
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def content_type(stream: bool) -> str:
    return "text/event-stream" if stream else "application/json"
