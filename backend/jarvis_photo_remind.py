"""jarvis_photo_remind.py - "Photo to reminder": a picture in, a PROPOSED
reminder out. Nothing is set up here.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).
photo-reminder.patch installs its one route, POST /api/photo/scan
(docs/JARVIS-API.md section 83).

THE OWNER'S CHOICE (2026-09-28, the research audit's idea 11, after Siri's
Visual Intelligence): the owner gives Jarvis a picture - a screenshot or an
image file on the PC, a photo or screenshot shared to Jarvis on the phone -
and Jarvis finds the event in it ("Summer fair, Sat 12 Oct, 2pm") and
PROPOSES a reminder. The owner edits it and taps to add it; nothing is set
up without that tap.

HOW, all on this PC and none of it by the AI model:
  1. The words in the picture are read by Windows' own text recognition
     (jarvis_ocr.read_text - the same reader chat uses; the picture goes to
     it on standard input and is never written to disk).
  2. Dates and times are found by PLAIN CODE: every short run of words is
     tried against jarvis_quick's own date and time parser (_parse_day,
     parse_clock) - the same one "remind me on 12 October at 2pm" uses.
     There is no second date parser.
  3. A title is picked by plain code too: the words left on the date's own
     line, or else the first line that looks like a heading.

OUTSIDE TEXT. Everything read from a picture is outside text (ARCHITECTURE
section 3): someone else wrote it. So:
  * nothing in it ever makes Jarvis act. The words are matched against the
    date grammar and shown; they never reach a tool, a command, the model or
    the gate. "Delete all my reminders" printed on a flyer is just a title
    suggestion the owner can see and change;
  * it is never learned from: this module never calls the learner, memory or
    the chat log, and the route is not a chat turn, so jarvis_intake never
    sees it;
  * it is marked: the answer carries `"outside": true` and OUTSIDE_NOTE, the
    words both apps show under the proposal.

NOTHING KEPT. The picture and the words read from it live only for the
length of the request: nothing here writes a file, a database row or a log
line with them. The apps hold the proposal on screen only, and drop it when
it is closed. What IS kept is what the owner adds by tapping - one ordinary
reminder, through POST /api/schedule/add like any other.

NOT CHECKED HERE: Windows' own reading of a real picture (no Windows in the
dev container). test_photo_remind.py drives everything else with a stand-in
reader.
"""
from __future__ import annotations

import re
import time
from typing import Callable, Optional

import jarvis_ocr
import jarvis_quick as Q

#: The route (photo-reminder.patch).
PATH = "/api/photo/scan"

#: At most this many dates are proposed from one picture.
MAX_FOUND = 3

#: A title is at most this long; the owner can type more.
MAX_TITLE = 80

#: The longest run of words tried as one date or time ("Saturday the 12th of
#: October 2026" is six).
MAX_WINDOW = 6

#: How big a picture may be, after base64 - the PC refuses any request over
#: 4 MiB anyway (jarvis_hud MAX_BODY); jarvis_ocr checks its own limit too.
MAX_URI_CHARS = 4 * 1024 * 1024

# ---- the words both apps show (test_photo_remind.py checks both use these) --

TITLE = "Photo to reminder"
FIND_LABEL = "Find a date in it"
OUTSIDE_NOTE = ("Read from a picture on your PC, by plain code - not by the AI model. These "
                "words count as outside text: Jarvis never acts on them, and nothing is kept "
                "once you close this.")
NOTHING_FOUND = ("No date or time found in the picture. You can still type one in and add "
                 "the reminder yourself.")
NO_WORDS = "No words could be read in the picture."
FOUND_ONE = "Found a date. Check it, change anything, then tap to add it."
FOUND_MANY = "Found {n} dates. Check the first, or pick another, then tap to add it."
NO_TIME = "No time found - 09:00 is filled in. Change it if you need to."
PASSED = "That time has already passed - change the date or time."
ADD_LABEL = "Add a Jarvis reminder"
CLOSE_LABEL = "Close"
BAD_IMAGE = "That is not a picture Jarvis can read (a JPEG or PNG, sent as a data: address)."
TOO_BIG = "The picture is too big. Try a smaller screenshot or photo."
MISSING = ("Your PC's Jarvis cannot read dates in pictures yet - run apply-patches.ps1 on "
           "the PC.")

# ---- finding -------------------------------------------------------------------

#: A clock time counts only when it is plainly one: "2pm", "14:00", "7.30",
#: "noon". A bare "7" on a flyer is a house number as often as a time.
_CLOCKLIKE = re.compile(r"\d[:.]\d\d|\d\s*(?:am|pm)\b|\b(?:noon|midday|midnight)\b")

#: A time range's start: "2-5pm" and "2 - 5 pm" become "2pm", "10am-4pm"
#: stays "10am", before any window is tried.
_RANGE = re.compile(r"(?i)\b(\d{1,2}(?:[:.]\d\d)?)\s*(?:-|to|until|till)\s*"
                    r"\d{1,2}(?:[:.]\d\d)?\s*(am|pm)\b")
_RANGE_FULL = re.compile(r"(?i)\b(\d{1,2}(?:[:.]\d\d)?\s*(?:am|pm))\s*(?:-|to|until|till)\s*"
                         r"\d{1,2}(?:[:.]\d\d)?\s*(?:am|pm)\b")
_RANGE_24 = re.compile(r"\b(\d{1,2}[:.]\d\d)\s*(?:-|to|until|till)\s*\d{1,2}[:.]\d\d\b")

#: Punctuation a token may carry on its edges and still be a date word.
_EDGE = "\"'()[]{}<>|*•·,;:!?"

#: Lines that are not a heading: a web or mail address, a phone number, a price.
_NOT_TITLE = re.compile(r"https?://|www\.|@|\b\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}\b|[£$€]\s?\d")


def _token_norm(tok: str) -> str:
    """One word as the parser reads it: lower case, edge punctuation off,
    a.m./p.m. joined. A dot inside ("7.30") and a final dot ("Oct.") are
    kept and dropped as the parser needs."""
    t = tok.strip(_EDGE).lower()
    t = t.replace("’", "'").replace("–", "-").replace("—", "-")
    t = re.sub(r"^a\.m\.?$", "am", t)
    t = re.sub(r"^p\.m\.?$", "pm", t)
    t = re.sub(r"(\d)a\.m\.?$", r"\1am", t)
    t = re.sub(r"(\d)p\.m\.?$", r"\1pm", t)
    return t.rstrip(".")


def _line_tokens(line: str) -> tuple:
    """(original words, normalised words) for one line, same length. A time
    range is cut to its start first, and a dash between words is its own
    token, so "Sat 12 Oct - 2pm" still has "2pm" on its own."""
    text = line.replace("–", "-").replace("—", "-")
    text = _RANGE_FULL.sub(lambda m: m.group(1), text)
    text = _RANGE_24.sub(lambda m: m.group(1), text)
    text = _RANGE.sub(lambda m: m.group(1) + m.group(2), text)
    text = re.sub(r"(?i)(am|pm)\s*-\s*(?=\d)", r"\1 - ", text)
    text = re.sub(r"(?<=\D)-(?=\s)|(?<=\s)-(?=\D)", " - ", text)
    orig = text.split()
    return orig, [_token_norm(t) for t in orig]


def _is_clock(words: str) -> Optional[Q.Clock]:
    if not _CLOCKLIKE.search(words):
        return None
    c = Q.parse_clock(words)
    return c


def _spans(norm: list) -> tuple:
    """([(start, end, day)], [(start, end, clock)]) in one line: the longest
    date and the longest time at each place, never overlapping."""
    days, clocks = [], []
    used = [False] * len(norm)
    i = 0
    while i < len(norm):
        hit = None
        for w in range(min(MAX_WINDOW, len(norm) - i), 0, -1):
            words = " ".join(t for t in norm[i:i + w] if t)
            if not words or not re.search(r"[a-z0-9]", words):
                continue
            dp = Q._parse_day(words)
            if dp is not None and _real_day(dp[0]):
                hit = ("day", w, dp)
                break
            c = _is_clock(words)
            if c is not None:
                hit = ("clock", w, c)
                break
        if hit is None:
            i += 1
            continue
        kind, w, val = hit
        (days if kind == "day" else clocks).append((i, i + w, val))
        for k in range(i, i + w):
            used[k] = True
        i += w
    return days, clocks


def _real_day(day) -> bool:
    """Only a calendar date or a named weekday counts on a picture: "today"
    and "tomorrow" there meant the day it was made, which is not known."""
    return isinstance(day, tuple) and day[0] in ("date", "wd")


def _tidy_title(words: list) -> str:
    t = " ".join(words)
    t = re.sub(r"\s+-\s+|\s+-$|^-\s+", " ", t)
    t = re.sub(r"^[\s,;:|/·•-]+|[\s,;:|/·•-]+$", "", t)
    t = " ".join(t.split())
    if len(re.findall(r"[A-Za-z]", t)) < 3:
        return ""
    if t.isupper():
        t = t[0] + t[1:].lower()
    if len(t) > MAX_TITLE:
        t = t[:MAX_TITLE].rsplit(" ", 1)[0].rstrip(",;:-") or t[:MAX_TITLE]
    return t


def _heading(lines: list, skip: set) -> str:
    """The first line near the top that reads like a heading."""
    for n, line in enumerate(lines[:8]):
        if n in skip or _NOT_TITLE.search(line):
            continue
        t = _tidy_title(line.split())
        if t and len(t.split()) <= 10:
            return t
    return ""


def _when(day, clock: Optional[Q.Clock], now: float) -> Optional[dict]:
    ymd = Q._ymd(day, now)
    if ymd is None:
        return None
    y, mo, d = ymd
    import jarvis_schedule as S
    if clock is None:
        hh, mm, time_found = Q.DEFAULT_HOUR[None], 0, False
    else:
        hours = Q._hour24(clock, None)
        # A bare hour with no am/pm on an event: 1 to 6 is the afternoon,
        # and 12 is midday, never half past midnight.
        hh = hours[-1] if len(hours) == 2 and (1 <= clock.hh <= 6 or clock.hh == 12) \
            else hours[0]
        mm, time_found = clock.mm, True
    at = S.wall_to_epoch(y, mo, d, hh, mm)
    return {"date": f"{y:04d}-{mo:02d}-{d:02d}", "time": f"{hh:02d}:{mm:02d}",
            "at": at, "time_found": time_found, "passed": at <= now,
            "when": S.long_date(at)}


def find(text: str, now: Optional[float] = None) -> list:
    """Up to MAX_FOUND proposals in `text` - the words read from a picture -
    each {"title", "date", "time", "at", "time_found", "passed", "when",
    "line"}, in the order they appear. Pure: reads nothing, keeps nothing."""
    now = time.time() if now is None else now
    lines = [ln for ln in str(text or "").splitlines() if ln.strip()]
    parsed = []
    for ln in lines:
        orig, norm = _line_tokens(ln)
        days, clocks = _spans(norm)
        parsed.append((orig, norm, days, clocks))
    out, seen = [], set()
    for n, (orig, norm, days, clocks) in enumerate(parsed):
        for (a, b, dp) in days:
            # The time: on the same line (the nearest after the date, else
            # the first before it - a range's start), else on one of the
            # next two lines, else the line before.
            clock = None
            after = [c for c in clocks if c[0] >= b]
            before = [c for c in clocks if c[1] <= a]
            clock_line, cspan = None, None
            if after:
                cspan, clock_line = after[0], n
            elif before:
                cspan, clock_line = before[0], n
            else:
                for m in (n + 1, n + 2, n - 1):
                    if 0 <= m < len(parsed) and parsed[m][3] and not parsed[m][2]:
                        cspan, clock_line = parsed[m][3][0], m
                        break
            if cspan is not None:
                clock = cspan[2]
            w = _when(dp[0], clock, now)
            if w is None:
                continue
            key = (w["date"], w["time"])
            if key in seen:
                continue
            seen.add(key)
            # The title: the words left on the date's own line, or a heading.
            # Every date and time on the line is left out of it, and so is
            # an address, a phone number or a price.
            taken = set(range(a, b))
            for (ca, cb, _) in clocks + [(da, db, None) for (da, db, _) in days]:
                taken |= set(range(ca, cb))
            left = [orig[k] for k in range(len(orig)) if k not in taken
                    and norm[k] not in ("at", "on", "from", "-", "@", "until", "till", "to")
                    and not _NOT_TITLE.search(orig[k])]
            title = _tidy_title(left)
            if not title:
                skip = {n} | ({clock_line} if clock_line is not None else set())
                title = _heading(lines, skip)
            w.update({"title": title, "line": " ".join(orig)[:200]})
            out.append(w)
            if len(out) >= MAX_FOUND:
                return out
    return out


def said(found: list) -> str:
    """The one sentence above the proposal."""
    if not found:
        return NOTHING_FOUND
    return FOUND_ONE if len(found) == 1 else FOUND_MANY.format(n=len(found))


# ---- the route -----------------------------------------------------------------

def scan(body, *, reader: Optional[Callable[[bytes], dict]] = None,
         now: Optional[float] = None) -> tuple:
    """POST /api/photo/scan {"image": "data:image/jpeg;base64,..."} ->
    (code, body). 200 {"ok": true, "outside": true, "found": [...], "said",
    "note", "text", "left_out"}; 400 no picture; 413 too big; 503 the words
    could not be read (`error`, a sentence). Sets nothing up."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": BAD_IMAGE}
    uri = body.get("image")
    if not isinstance(uri, str) or not uri.strip():
        return 400, {"ok": False, "error": BAD_IMAGE}
    if len(uri) > MAX_URI_CHARS:
        return 413, {"ok": False, "error": TOO_BIG}
    image = jarvis_ocr.image_bytes({"type": "image_url", "image_url": {"url": uri}})
    if not image:
        return 400, {"ok": False, "error": BAD_IMAGE}
    read = (reader or jarvis_ocr.read_text)(image)
    if not isinstance(read, dict) or not read.get("ok"):
        why = read.get("why") if isinstance(read, dict) else ""
        return 503, {"ok": False, "error": why or jarvis_ocr.FAILED}
    text = str(read.get("text") or "")
    if not text.strip():
        return 200, {"ok": True, "outside": True, "found": [], "said": NO_WORDS,
                     "note": OUTSIDE_NOTE, "text": "", "left_out": 0}
    found = find(text, now)
    return 200, {"ok": True, "outside": True, "found": found, "said": said(found),
                 "note": OUTSIDE_NOTE, "text": text,
                 "left_out": int(read.get("left_out") or 0)}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_POST` so PATH is answered here, after the
    server's own origin and token checks; everything else goes straight to
    the original. No gate and no card: it reads a picture and proposes -
    it sets nothing up."""
    post0 = handler_cls.do_POST
    if getattr(post0, "_jarvis_photo_remind", False):
        return "  photo      Photo to reminder (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_POST(self):
        from urllib.parse import urlsplit
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            import json
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = scan(body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_POST._jarvis_photo_remind = True
    handler_cls.do_POST = do_POST
    return "  photo      Photo to reminder: dates read from a picture, proposed, never set by itself"
