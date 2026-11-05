"""Quotes (2026-11-05): a local corpus of public-domain quotations, a `quote`
kind on the one scheduler, and the words "send me a quote" answers with.

WHAT THIS IS, AND WHAT IT IS NOT
================================
A quotation is a short excerpt from a work that is out of copyright. The
corpus is a JSON file beside this module (`quotes_corpus.json`), read once at
import. Nothing is fetched, no model is called, nothing leaves this PC, and
nothing is written: the picker below is pure arithmetic on the day number, so
the same day gives the same quote on every run and on every copy of this file.

THE LICENCES
============
Every entry carries a `licence` from `LICENCES`. Only two are allowed, and
neither asks anything of a reader:

  public-domain   the work was first published in or before 1929, so it is out
                  of copyright in the United States (works published through
                  1929 entered the public domain on 2025-01-01), and the text
                  is taken from a public-domain edition or transcription.
  cc0-1.0         the same, from a Standard Ebooks edition, which dedicates
                  its own editorial work to the public domain (CC0 1.0).

Every entry also carries who said it, in what work, and in what year. Those
three are required fields: a quotation that cannot be attributed is refused at
load time, because "someone wise once said" is a rumour with a font. A quote
from a model would be the worst failure this feature could have - a confident,
well-formed sentence attributed to somebody who never said it - so no model
ever writes one of these.

WHERE THE TEXT COMES FROM
=========================
`source_id` is "<scheme>:<work-slug>". The scheme names the kind of edition the
words were taken from; the slug names the work. The schemes are:

  se        Standard Ebooks (CC0 edition)
  pg        Project Gutenberg (the public-domain body text, with every
            Gutenberg header, footer, licence paragraph and trademark
            reference removed - see `GUTENBERG_MARKS`, which the loader
            refuses)
  ws        a Wikisource page that states the work is public domain
  bartlett  a nineteenth-century edition of Bartlett's Familiar Quotations

Wikiquote, ZenQuotes, quotable and the general quote websites are deliberately
NOT used: Wikiquote's selection is CC BY-SA and much of it is fair use,
ZenQuotes is all rights reserved, and quotable publishes no data licence. The
reasoning is in docs/ARCHITECTURE.md, "Quotes".

THE PICKER
==========
`pick(day)` is `(day * STEP + OFFSET) % SIZE`. STEP shares no factor with the
corpus size (`math.gcd(STEP, SIZE) == 1`), so walking day by day visits every
entry exactly once before any entry repeats - with no state file, no "last
quote" record, and nothing to keep in step between the PC and the phone. A
plain `day % SIZE` was refused: it makes consecutive days adjacent entries,
which reads as a pattern.

THE SCHEDULER
=============
`quote` is a KIND of job on jarvis_schedule's one clock (register_kind), so a
scheduled quote has the same missed-while-off rule, the same `schedule` event
and the same Coming up list as a reminder. A REPEATING quote asks ONE
`schedule_repeat` card (repeatable=True, plain_repeat left off), the same card
the morning briefing raises; a one-off needs none. When it goes off, the
scheduler publishes its usual state:"fired" event, and this kind's `say` adds
the words for that firing - one event, no "ready" step, because unlike a
briefing there is nothing to assemble.
"""
from __future__ import annotations

import datetime
import json
import math
from pathlib import Path
from typing import Optional

try:
    import jarvis_schedule as S
except Exception:                                    # pragma: no cover - tests
    S = None

#: The file beside this module. It travels with the module (BESIDE in
#: tools/gen_base_from_backend.py), so a fresh install finds it too.
CORPUS_NAME = "quotes_corpus.json"

#: The only licences an entry may carry. Both ask nothing of a reader.
LICENCES = frozenset({"public-domain", "cc0-1.0"})

#: The edition families a source_id may name. See the module docstring.
SOURCES = {
    "se": "Standard Ebooks, CC0 edition",
    "pg": "Project Gutenberg public-domain text, Gutenberg marks removed",
    "ws": "Wikisource page stating the work is public domain",
    "bartlett": "Bartlett's Familiar Quotations, nineteenth-century edition",
}

#: The newest year a work may have been published in and still be in here:
#: works published through 1929 are out of copyright in the United States.
MAX_YEAR = 1929

#: The required fields, in the order the file holds them.
FIELDS = ("text", "author", "work", "year", "source_id", "licence")

#: A Gutenberg ebook is the public-domain text PLUS a trademark and licence
#: wrapper. The wrapper must never travel with a quotation, so the loader
#: refuses any entry whose words carry a trace of it.
GUTENBERG_MARKS = ("project gutenberg", "gutenberg-tm", "gutenberg.org",
                   "gutenberg literary", "*** start of", "*** end of")

#: How long one answer may be. A quote is short; anything longer is a mistake.
MAX_TEXT = 300
MAX_AUTHOR = 80
MAX_WORK = 120

#: A day, in seconds (the scheduler's own clock, not used by the picker).
DAY = 86400

#: The picker's fixed step and offset. STEP is chosen at load so that it shares
#: no factor with the corpus size; see `_step`.
OFFSET = 11


def _step(size: int) -> int:
    """A step that shares no factor with `size`, so day by day walks the whole
    corpus before repeating. 17 first (a prime, so it only fails on a size
    divisible by 17), then smaller primes, then 1 - which is coprime with
    everything and is the honest last resort."""
    for step in (17, 13, 11, 7, 5, 3, 1):
        if math.gcd(step, size) == 1:
            return step
    return 1


def _clean(text: str) -> str:
    return " ".join(str(text).split())


def _check(entry: dict, where: str) -> dict:
    """One entry, validated. A missing author or work is a load-time error,
    never a quote that says "Unknown"."""
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: an entry must be an object")
    missing = [key for key in FIELDS if key not in entry]
    if missing:
        raise ValueError(f"{where}: missing {', '.join(missing)}")
    extra = [key for key in entry if key not in FIELDS]
    if extra:
        raise ValueError(f"{where}: unexpected {', '.join(sorted(extra))}")
    for key in ("text", "author", "work", "source_id", "licence"):
        if not isinstance(entry[key], str) or not _clean(entry[key]):
            raise ValueError(f"{where}: {key} must be words")
        if entry[key] != _clean(entry[key]):
            raise ValueError(f"{where}: {key} has stray spaces")
    if len(entry["text"]) > MAX_TEXT:
        raise ValueError(f"{where}: the quote is longer than {MAX_TEXT} characters")
    if len(entry["author"]) > MAX_AUTHOR:
        raise ValueError(f"{where}: the author is longer than {MAX_AUTHOR} characters")
    if len(entry["work"]) > MAX_WORK:
        raise ValueError(f"{where}: the work is longer than {MAX_WORK} characters")
    year = entry["year"]
    if isinstance(year, bool) or not isinstance(year, int):
        raise ValueError(f"{where}: year must be a whole number")
    if not 1 <= year <= MAX_YEAR:
        raise ValueError(f"{where}: {year} is not a public-domain year (1-{MAX_YEAR})")
    licence = entry["licence"]
    if licence not in LICENCES:
        raise ValueError(f"{where}: {licence!r} is not one of {sorted(LICENCES)}")
    scheme = str(entry["source_id"]).split(":", 1)[0]
    if ":" not in entry["source_id"] or scheme not in SOURCES:
        raise ValueError(f"{where}: source_id must be <{'|'.join(SOURCES)}>:<work>")
    folded = _clean(entry["text"]).lower()
    for mark in GUTENBERG_MARKS:
        if mark in folded:
            raise ValueError(f"{where}: the words still carry {mark!r}")
    return dict(entry)


def load(path: Optional[Path] = None) -> tuple:
    """The corpus, validated. Raises ValueError on anything that would make a
    quotation unattributable, unlicensed or not public domain."""
    where = Path(path) if path is not None else Path(__file__).resolve().with_name(CORPUS_NAME)
    raw = json.loads(where.read_text(encoding="utf-8"))
    rows = raw.get("quotes") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{where.name}: no quotes")
    seen = set()
    out = []
    for index, row in enumerate(rows, 1):
        entry = _check(row, f"{where.name} #{index}")
        key = _clean(entry["text"]).lower()
        if key in seen:
            raise ValueError(f"{where.name} #{index}: the same words are already in the corpus")
        seen.add(key)
        out.append(entry)
    return tuple(out)


CORPUS = load()
SIZE = len(CORPUS)
STEP = _step(SIZE)
assert math.gcd(STEP, SIZE) == 1, "the picker would not visit every quote"


def day_index(now: Optional[float] = None) -> int:
    """The PC's local day, as one whole number, so the same calendar day gives
    the same quote from midnight to midnight (the picker is stateless)."""
    if now is None:
        return datetime.date.today().toordinal()
    return datetime.date.fromtimestamp(float(now)).toordinal()


def pick(day: int) -> dict:
    """The quote for one day number - the same one every time, everywhere."""
    return CORPUS[(int(day) * STEP + OFFSET) % SIZE]


def for_now(now: Optional[float] = None) -> dict:
    """The quote for right now."""
    return pick(day_index(now))


def byline(entry: dict) -> str:
    """"Author - Work (Year)", the line that makes it a quote and not a
    sentence somebody made up."""
    return f"{entry['author']} - {entry['work']} ({entry['year']})"


def line(entry: dict) -> str:
    """The words and the attribution as one string - what a chat answer, a
    notification body and a coming-up row all show."""
    return f"{entry['text']} - {byline(entry)}"


def today_line(now: Optional[float] = None) -> str:
    return line(for_now(now))


# --------------------------------------------------------------------------
#   The schedule kind
# --------------------------------------------------------------------------
# The shape is the morning briefing's (jarvis_briefing.py): owner-listed, one
# kind on the one clock, repeatable through the ONE schedule_repeat card. The
# one addition is `say`: the words for THIS firing. A quote is different every
# day, so the job's own text would be the first day's quote forever; the
# scheduler puts `say`'s words on the fired event instead, as an additive key
# an older client ignores, and both apps read it before the job's text.

KIND = "quote"
NOUN = "quote of the day"
#: All a locked phone, or a toast while App lock is on, may show.
LOCK_SCREEN = "Jarvis: a quote is ready."
CARD_NOTE = (
    "Each time, Jarvis picks a quote from a list kept on your PC - real, "
    "public-domain quotations with the author, the work and the year. The same "
    "day always gives the same quote, and nothing is written down to remember it.",
    "Nothing is sent anywhere, no AI model is asked for the words, and the "
    "list is never downloaded or updated by itself.",
)


def _say(job_id: str) -> str:
    """The words for one firing: the quote for the day the SCHEDULER says it is.

    Never `time.time()` directly: a job missed while the PC was off goes off
    late, and the words belong to the day it actually went off on, which is the
    scheduler's own clock. The same clock both apps read the row's "next" from.
    """
    now = None
    try:
        sched = S.get() if S is not None else None
        if sched is not None and callable(getattr(sched, "now", None)):
            now = sched.now()
    except Exception:
        now = None
    return today_line(now)


def setups(sched=None) -> list:
    """The quote jobs on the list (active, paused, or waiting for a card) -
    the same shape jarvis_briefing.setups returns."""
    sched = sched or (S.get() if S is not None else None)
    if sched is None:
        return []
    return [j for j in sched.listed() if j.get("kind") == KIND]


if S is not None:
    S.register_kind(KIND, NOUN, LOCK_SCREEN, has_text=False, owner_listed=True,
                    repeatable=True, card_note=CARD_NOTE, say=_say,
                    about=("A quote arrives as one notification with the words in it - "
                           "there is nothing to put together, so it does not wait.",
                           "A quote in a chat is word for word from the same list; "
                           "no AI model writes one."))
