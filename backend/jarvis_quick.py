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
"""
from __future__ import annotations

import json
import re
import sys
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


def parse_clock(s: str) -> Optional[Clock]:
    s = s.strip()
    s = re.sub(r"^at\s+", "", s)
    if s in ("noon", "midday", "12 noon"):
        return Clock(12, 0, "24")
    if s == "midnight":
        return Clock(0, 0, "24")
    mer = None
    m = re.fullmatch(r"(.+?)" + _MER, s)
    body = s
    if m:
        body = m.group(1)
        if m.group(2):
            mer = m.group(2)
        elif m.group(3):
            mer = "am" if m.group(3) == "morning" else "pm"
        elif s.endswith("at night"):
            mer = "pm"
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
        return Clock(hh, mm, mer)
    if hh == 0 or hh > 12 or lead_zero:
        return Clock(hh, mm, "24")
    return Clock(hh, mm, None)


def _hour24(c: Clock, part: Optional[str]) -> list:
    """Candidate hours for a clock, earliest-preferred first."""
    if c.mer == "24":
        return [c.hh]
    if c.mer == "am":
        return [c.hh % 12]
    if c.mer == "pm":
        return [c.hh % 12 + 12]
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
        return When(at=best)
    ymd = _ymd(day, now)
    if ymd is None:
        return None
    y, mo, d = ymd
    n = 1 if ymd != _day_of(now, 0) else 0      # another day than today
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
        return When(at=ts[-1], passed=True)
    return When(at=future[0])


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
        return When(rule={"every": "day", "at": f"{h:02d}:{c.mm:02d}"})
    m = re.fullmatch(r"(?:every\s+weekday|on\s+weekdays|weekdays|every\s+work\s*day)"
                     r"(?:\s+morning)?\s+at\s+(.+)", s)
    if m:
        c = parse_clock(m.group(1))
        if c is None:
            return None
        h = _hour24(c, "morning" if "morning" in s else None)[0]
        return When(rule={"every": "weekday", "at": f"{h:02d}:{c.mm:02d}"})
    m = re.fullmatch(r"(?:every|on)\s+((?:" + _WD + r")s?(?:(?:\s*,\s*|\s+and\s+)(?:" + _WD
                     + r")s?)*)(?:\s+(morning|afternoon|evening))?\s+at\s+(.+)", s)
    if m and (s.startswith("every") or re.search(r"(?:" + _WD + r")s\b", m.group(1))):
        days = sorted({_WEEKDAYS.index(w.rstrip("s") if w.rstrip("s") in _WEEKDAYS else w)
                       for w in re.findall(r"(?:" + _WD + r")s?", m.group(1))})
        c = parse_clock(m.group(3))
        if c is None or not days:
            return None
        h = _hour24(c, m.group(2))[0]
        return When(rule={"every": "week", "at": f"{h:02d}:{c.mm:02d}", "days": days})
    if s.startswith("every ") or s.startswith("each "):
        return None
    # --- once ---------------------------------------------------------------
    m = re.fullmatch(r"in\s+(.+)", s)
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
    s = normalise(text)
    if not s or len(s) > 400 or "\n" in s:
        return None

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

    # --- focus sessions (jarvis_focus.py) --------------------------------------
    got = _focus(s)
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
    got = _settings_adjust(s)
    if got is not None:
        return got

    # --- music and video control on this PC (jarvis_media.py, I91) -------------------
    got = _media(s)
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


_REMIND = re.compile(r"(?:remind\s+me|set\s+(?:a|an)\s+reminder|make\s+(?:a|an)\s+reminder"
                     r"|create\s+(?:a|an)\s+reminder)")


def _reminder(s: str, now: float) -> Optional[Intent]:
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


def _run_pc_help(intent: Intent) -> Result:
    """Read-only, no card: nothing changes and nothing leaves this PC. An
    answer naming programs is private (it stays on screen) and marks the
    turn as having read outside text - a program chooses its own name."""
    try:
        import jarvis_pc_help as PCH
    except Exception:
        return Result(PC_HELP_MISSING, intent.name)
    out = PCH.answer(str(intent.f.get("topic") or ""))
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


#: The five providers, and Whoogle (left out - asked about, it gets its
#: reason), by the words the owner may use for them.
_PROVIDER_WORDS = (("searxng", r"searx(?:ng)?"),
                   ("duckduckgo", r"duck\s*duck\s*go|ddg"),
                   ("exa", r"exa(?:\s+ai)?"),
                   ("tavily", r"tavily"),
                   ("brave", r"brave(?:\s+search)?"),
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


def _from_now_on(s: str) -> Optional[Intent]:
    """"From now on, be more plain" / "... be warmer" and close phrasings -
    the mechanism, wired to jarvis_manner.py's one real dial. Whole
    sentences only, like the rest of this grammar."""
    m = _FROM_NOW_ON.fullmatch(s)
    if not m:
        return None
    tail = m.group(1)
    if _TO_PLAIN.fullmatch(tail):
        return Intent("manner_from_now_on", {"manner": "plain"})
    if _TO_WARM.fullmatch(tail):
        return Intent("manner_from_now_on", {"manner": "warm"})
    return Intent("manner_from_now_on", {"manner": None})


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
    if section is None:
        return None
    return Intent("settings_open", {"id": section.id})


#: The plain on/off settings (jarvis_settings_registry.BOOL_SETTINGS): "turn
#: on background learning", "switch off lights without asking", "enable
#: smartwatch notifications", "disable senders in my briefing".
_ADJUST_ONOFF = re.compile(
    r"(?:turn|switch)\s+(on|off)\s+(.+)"
    r"|(enable)\s+(.+)"
    r"|(disable)\s+(.+)")

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


def _settings_adjust(s: str) -> Optional[Intent]:
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
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
        setting = R.find_bool_setting(name)
        if setting is not None:
            return Intent("settings_bool", {"key": setting.key, "on": on})
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
_SAYABLE = re.compile(
    r"what\s+can\s+(?:you|i|jarvis)\s+(?:do|say|ask(?:\s+you)?|tell\s+you)(?:\s+here)?"
    r"|what\s+(?:should|do)\s+i\s+(?:say|ask|type)(?:\s+to\s+you)?"
    r"|what\s+(?:are|were)\s+(?:your|jarvis'?s?)\s+commands"
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
CHAT_TAG_TEMPORARY = ("This is a temporary chat, so it is not kept and cannot be filed.")
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


def _run_settings_asks_first(f: dict, peer, local) -> Result:
    import jarvis_settings_registry as R
    out = R.set_asks_first(f["action"], f["ask"], peer=peer, local=local)
    return Result(out.said, "settings_asks_first")


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


def run(intent: Intent, sched, now: float, conversation: Optional[str] = None,
        seen: Optional[float] = None, temporary: bool = False,
        peer=None, local=None, messages=None) -> Optional[Result]:
    """Do it. None hands the sentence to the model after all.
    `conversation`: the request's conversation_id ("cancel that" works only
    within one). `seen`: when the owner last talked to Jarvis before this
    turn ("what did I miss?"). `temporary`: a temporary chat, for "from now
    on ..." (2026-09-27). `peer`/`local`: the request's own address, read the
    same way owner-check.patch's do_POST wrapper reads it - so a setting on
    jarvis_owner_check.PC_ONLY_ACTIONS can refuse a request that did not
    truly come from this PC (jarvis_settings_registry.py, 2026-09-27)."""
    n, f = intent.name, intent.f
    if n == "where_put":
        return _run_where_put(f, now, temporary)
    if n == "widget_make":
        # `messages`: the request's, as they arrived - for the taint check.
        return _run_widget(f, conversation, messages)
    import jarvis_schedule as S
    if n == "settings_open":
        return _run_settings_open(f)
    if n == "menu_visibility":
        return _run_menu_visibility(f)
    if n == "settings_bool":
        return _run_settings_bool(f, peer, local)
    if n == "settings_asks_first":
        return _run_settings_asks_first(f, peer, local)
    if n == "settings_tool":
        return _run_settings_tool(f, peer, local)
    if n.startswith("animal_"):
        return _run_animal(n, f, peer, local)
    if n == "manner_from_now_on":
        return _run_from_now_on(f, conversation, temporary)
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
    if n.startswith("media_"):
        return _run_media(intent)
    if n.startswith("next_time_"):
        return _run_next_time(intent, sched)
    if n.startswith("today_"):
        return _run_today(intent, sched)
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
        return Result(f"{what} set for {S.length_words(f['seconds'])}.", n, [j["id"]],
                      made=[j["id"]], what=name, nouns=("timer",))
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
        return None
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


def _set_at(kind: str, w: When, text: str, sched, now: float, n: str) -> Result:
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
        return Result(b["text"], n, private=True, read=list(b.get("read") or []))
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
           temporary: bool = False, peer=None, local=None, messages=None) -> Optional[Result]:
    """Match and act. None: not ours - ask the model. `conversation`: the
    request's conversation_id, so "cancel that" takes back only what was set
    in it; `seen`: when the owner last talked to Jarvis before this turn;
    `temporary`: a temporary chat (2026-09-27's "from now on ..."); `peer`/
    `local`: the request's own address, for a setting on jarvis_owner_check.
    PC_ONLY_ACTIONS (jarvis_settings_registry.py, 2026-09-27)."""
    now = time.time() if now is None else now
    intent = match(text, now)
    if intent is None:
        return None
    if sched is None:
        import jarvis_schedule
        sched = jarvis_schedule.get()
    res = run(intent, sched, now, conversation=conversation, seen=seen, temporary=temporary,
             peer=peer, local=local, messages=messages)
    if res is not None:
        try:
            sched.mark_command(text)
        except Exception:
            pass
        try:
            if res.made and conversation:
                sched.note_set(conversation, res.made, res.what, res.intent, nouns=res.nouns)
            elif res.intent != "undo" and conversation:
                # Something else happened since: "cancel that" would now
                # mean THAT, which cannot be taken back - so nothing can.
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
                peer=None, local=None) -> Optional[Result]:
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
    seen = _touch(now) if isinstance(body, dict) and body.get("messages") else None
    conversation = conversation_of(body)
    # "temporary": true (temporary-chat.patch) - the same one-line check
    # jarvis_hud.py's own _temporary_chat(body) makes; needed here for
    # "from now on ..." (2026-09-27), which keeps a temporary chat's style
    # change in that chat only, never written to manner.json.
    temporary = _temporary_body(body)
    text = newest_own_words(body)
    res = None if text is None else answer(text, sched=sched, now=now,
                                           conversation=conversation, seen=seen,
                                           temporary=temporary, peer=peer, local=local,
                                           messages=body.get("messages"))
    if res is None and conversation:
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


def _temporary_body(body) -> bool:
    """Is this request a temporary chat? `temporary: true`, or a game or
    role-play the PC has seen in this conversation - the same test the chat
    route makes (jarvis_hud._temporary_chat, games-temporary.patch). This
    path used to read the flag alone, so in a role-play chat "where is my
    passport" was answered from saved memory and "from now on, be plainer"
    was written to manner.json for good (the second chat audit,
    2026-09-28, finding 7, reproduced). Without jarvis_intake: the flag."""
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
