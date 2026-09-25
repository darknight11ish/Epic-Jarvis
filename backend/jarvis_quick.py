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
owner asked for, not a fact being saved.

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
import time
from dataclasses import dataclass, field
from typing import Optional

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


def _parse_day(s: str):
    """(days from today or ('wd', n), part) for a day phrase, or None."""
    s = s.strip()
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
    if isinstance(day, tuple):
        n = _days_until(now, day[1])
    else:
        n = day
    y, mo, d = _day_of(now, n)
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
        n = _days_until(now, day[1]) if isinstance(day, tuple) else day
        y, mo, d = _day_of(now, n)
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

    # --- the morning briefing (jarvis_briefing.py) ------------------------------
    got = _briefing(s, now)
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
        if text and not re.fullmatch(r"(?:it|this|that|them|these|those|something)", text):
            return Intent("todo_add", {"text": text})
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
    return None


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


def run(intent: Intent, sched, now: float) -> Optional[Result]:
    """Do it. None hands the sentence to the model after all."""
    import jarvis_schedule as S
    n, f = intent.name, intent.f
    if n == "bulk":
        return Result("Jarvis does not clear everything at once. Delete them one at a time, "
                      "here or under Coming up.", n)
    if n.startswith("briefing_"):
        return _run_briefing(intent, sched, now)
    if n == "timer_set":
        try:
            j = sched.add_timer(f["seconds"], f.get("label", ""), source="quick")
        except (ValueError, OverflowError) as exc:
            return Result(S._sentence(exc), n)
        what = f"{j['text'].capitalize()} timer" if j.get("text") else "Timer"
        return Result(f"{what} set for {S.length_words(f['seconds'])}.", n, [j["id"]])
    if n in ("timer_cancel", "timer_pause", "timer_resume", "timer_add", "timer_status"):
        timers = sched.timers()
        if n == "timer_status":
            if not timers:
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
        try:
            j = sched.add_todo(f["text"], source="quick")
        except (ValueError, OverflowError) as exc:
            return Result(S._sentence(exc), n)
        if j.get("already"):
            return Result("That is already on your to-do list.", n, [j["id"]])
        return Result("Added to your to-do list.", n, [j["id"]])
    if n == "todo_list":
        items = sched.todos()
        if not items:
            return Result("Your to-do list is empty.", n)
        texts = [i["text"] for i in items]
        if len(texts) > 8:
            return Result(f"{len(texts)} things on your to-do list. The first 8: "
                          f"{_join(texts[:8])}.", n, [i["id"] for i in items[:8]], private=True)
        head = "One thing on your to-do list: " if len(texts) == 1 else "Your to-do list: "
        return Result(head + _join(texts) + ".", n, [i["id"] for i in items], private=True)
    if n in ("todo_done", "todo_remove"):
        items = sched.todos()
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
        return Result("Marked done." if n == "todo_done" else "Removed from your to-do list.",
                      n, [pool[0]["id"]])
    return None


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
        return Result(f"That repeats ({S.rule_words(j.get('rule') or w.rule)}), so there is an "
                      f"approval card for it. Nothing is set up until you say yes.", n, [j["id"]])
    if w.passed:
        return Result(f"{S.when_words(w.at, now)} has already passed. Say another time.", n)
    try:
        j = sched.add_at(kind, w.at, text, source="quick")
    except (ValueError, OverflowError) as exc:
        return Result(S._sentence(exc), n)
    if w.at - now < 3600 and kind == "reminder" and not w.default_time:
        return Result(f"{noun} set for {S.clock(w.at)}, in {S.length_words(w.at - now)}.",
                      n, [j["id"]])
    return Result(f"{noun} set for {S.when_words(w.at, now)}.", n, [j["id"]])


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
        return Result(f"That repeats ({S.rule_words(j.get('rule') or w.rule)}), so there is an "
                      f"approval card for it. Nothing is set up until you say yes.", n, [j["id"]])
    if w.passed:
        return Result(f"{S.when_words(w.at, now)} has already passed. Say another time.", n)
    try:
        j = sched.add_at(B.KIND, w.at, "", source="quick")
    except (ValueError, OverflowError) as exc:
        return Result(S._sentence(exc), n)
    return Result(f"Briefing set for {S.when_words(w.at, now)}.", n, [j["id"]])


def answer(text, *, sched=None, now: Optional[float] = None) -> Optional[Result]:
    """Match and act. None: not ours - ask the model."""
    now = time.time() if now is None else now
    intent = match(text, now)
    if intent is None:
        return None
    if sched is None:
        import jarvis_schedule
        sched = jarvis_schedule.get()
    res = run(intent, sched, now)
    if res is not None:
        try:
            sched.mark_command(text)
        except Exception:
            pass
    return res

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


def answer_turn(body, *, sched=None, now: Optional[float] = None) -> Optional[Result]:
    """For /api/chat: the fast path's answer to this turn, or None."""
    text = newest_own_words(body)
    if text is None:
        return None
    return answer(text, sched=sched, now=now)


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
