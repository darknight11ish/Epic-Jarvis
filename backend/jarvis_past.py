"""jarvis_past.py - questions about the past get the facts that used to be true.

WHAT IT DOES

Chat recall asks the memory store for CURRENT facts only
(memory-prefix.patch: `store().search(query, k=MEMORY_K)`). That is right
for "where do I live?" and wrong for "where did I live before?": the old
address is still in the store - facts are retired, never deleted - but a
retired fact was never brought back into a chat. So Jarvis answered a
question about the past with only the present.

recall() below is what the chat turn calls now (past-recall.patch). For an
ordinary question it is exactly the old call and returns exactly the old
facts. For a question about the past - a strict word check, below - it
ALSO brings back up to PAST_K retired facts that match, each one with
"(no longer true since <date>)" on the end, so the model cannot mistake
history for the present.

And a simple date in the question narrows it: "where did I live in June",
"what did I believe last year", "back in 2025". A fixed parser turns those
into a time window; no model is asked, ever. "What did I believe / think /
say / tell you ..." is about what JARVIS KNEW then, so it searches as of
that moment (MemoryStore.search(known_at=...)); any other past question is
about what was TRUE then, so it keeps the retired facts whose true-from /
true-until dates overlap the window.

THE WORD CHECK IS STRICT ON PURPOSE. A false "yes" costs a few old,
labelled facts in one prompt; the owner's rule is still that ordinary turns
are unchanged. So:

  * A bare month or year is NOT a past cue: "remind me in June" is the
    future. It only sets the window when something else already says past -
    "did I", "was I", "used to", "last year", "back in", "before",
    "previously", "... ago". ("back in June" and "June 2025" count, because
    they can only mean the past.)
  * "before" does not count before a time that is still to come - "before
    tomorrow", "before the meeting", "before 5".
  * English, plus the commonest forms in the seven other languages the
    sensitive-topic check knows (Spanish, French, German, Italian,
    Portuguese, Dutch, Polish). Anything it misses is an ordinary turn -
    the old behaviour, not a failure.

Standard library only. Nothing here writes anything or logs any words.
"""
from __future__ import annotations

import re
import time
import unicodedata
from typing import Optional

#: How many retired facts a past question may add, at most - and never more
#: than the recall width itself, so JARVIS_MEMORY_K=0 still means none.
PAST_K = 3

#: How many candidates to look through for retired ones. Current facts rank
#: alongside them, so this is wider than PAST_K.
_WIDE = 40


def _norm(text: str) -> str:
    """Lower case, accents off (NFKD), one kind of apostrophe, one space.
    "Früher" -> "fruher", "año" -> "ano", "l’année" -> "l'annee". Polish
    "ł" has no decomposition, so the patterns spell both."""
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.replace("’", "'").replace("‘", "'")
    return " ".join(t.split())


# ---------------------------------------------------------------- the cues --

_NOT_YET = (r"(?:tomorrow|tonight|today|next|noon|midnight|lunch|dinner|bed|"
            r"the (?:meeting|deadline|end)|\d|monday|tuesday|wednesday|thursday|"
            r"friday|saturday|sunday|i (?:go|leave)|we (?:go|leave)|you (?:go|leave))")

_PAST = [re.compile(p) for p in (
    # English
    r"\bused to\b",
    r"\bdid (?:i|we)\b",
    r"\b(?:was i|were we|had i)\b",
    r"\blast (?:year|month|week|summer|winter|spring|autumn|fall|time)\b",
    r"\bago\b",
    r"\bback (?:in|then|when)\b",
    rf"\bbefore\b(?! {_NOT_YET})",
    r"\b(?:previously|formerly|in the past)\b",
    r"\bwhat did (?:i|you) (?:believe|think|say|tell|know)\b",
    # Spanish
    r"\bsolias?\b|\bsoliamos\b",
    r"\b(?:el )?ano pasado\b",
    r"\b(?:antes|anteriormente|antiguamente|en el pasado)\b",
    r"\bhace (?:un|una|dos|tres|\d+) (?:anos?|mes|meses|semanas?)\b",
    # French
    r"\b(?:autrefois|auparavant|dans le passe)\b",
    r"\bavant\b(?! (?:demain|ce soir|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|\d))",
    r"\bl'?an(?:nee)? (?:derniere?|passee)\b",
    r"\bil y a (?:un|une|deux|trois|\d+) (?:ans?|mois|semaines?)\b",
    # German
    r"\b(?:fruher|frueher|vorher|zuvor|damals|in der vergangenheit)\b",
    r"\bletzte[sn]? jahr\b",
    r"\bvor (?:einem|einer|zwei|drei|\d+) (?:jahr|jahren|monat|monaten|woche|wochen)\b",
    # Italian ("prima" alone, not "la prima volta" - that is "the first time")
    r"\b(?:l'?anno scorso|in passato|precedentemente)\b",
    r"(?<!la )(?<!il )(?<!per )\bprima\b(?! volta)",
    r"\b(?:un|due|tre|\d+) (?:anno|anni|mese|mesi|settimana|settimane) fa\b",
    # Portuguese ("antes" is above, with Spanish)
    r"\b(?:antigamente|no passado|costumava|costumavam)\b",
    r"\b(?:no )?ano passado\b",
    r"\bha (?:um|uma|dois|tres|\d+) (?:anos?|mes|meses|semanas?)\b",
    # Dutch
    r"\b(?:vroeger|voorheen|toen|in het verleden)\b",
    r"\bvorige? jaar\b",
    r"\b(?:een|twee|drie|\d+) (?:jaar|maand|maanden|week|weken) geleden\b",
    # Polish ("kiedys" is left out: it is "once" and "some day")
    r"\b(?:w )?zesz[lł]ym roku\b",
    r"\b(?:wczesniej|przedtem|poprzednio|dawniej|w przeszlosci)\b",
    r"\btemu\b",
)]

#: "What did JARVIS know then" rather than "what was true then".
_BELIEF = [re.compile(p) for p in (
    r"\bwhat did (?:i|you) (?:believe|think|say|tell|know)\b",
    r"\bwhat did jarvis (?:believe|think|know)\b",
    r"\bwhat (?:was i|were you) (?:told|thinking)\b",
    r"\bwhat had i (?:said|told)\b",
)]


# ---------------------------------------------------------------- the dates --

_MONTHS = {
    1: ("january", "enero", "janvier", "januar", "janner", "gennaio", "janeiro",
        "januari", "styczen", "styczniu"),
    2: ("february", "febrero", "fevrier", "februar", "febbraio", "fevereiro",
        "februari", "luty", "lutym"),
    3: ("march", "marzo", "mars", "marz", "maerz", "marco", "maart", "marzec", "marcu"),
    4: ("april", "abril", "avril", "aprile", "kwiecien", "kwietniu"),
    5: ("may", "mayo", "mai", "maggio", "maio", "mei", "maj", "maju"),
    6: ("june", "junio", "juin", "juni", "giugno", "junho", "czerwiec", "czerwcu"),
    7: ("july", "julio", "juillet", "juli", "luglio", "julho", "lipiec", "lipcu"),
    8: ("august", "agosto", "aout", "augustus", "sierpien", "sierpniu"),
    9: ("september", "septiembre", "setiembre", "septembre", "settembre", "setembro",
        "wrzesien", "wrzesniu"),
    10: ("october", "octubre", "octobre", "oktober", "ottobre", "outubro",
         "pazdziernik", "pazdzierniku"),
    11: ("november", "noviembre", "novembre", "novembro", "listopad", "listopadzie"),
    12: ("december", "diciembre", "decembre", "dezember", "dicembre", "dezembro",
         "grudzien", "grudniu"),
}
_MONTH_OF = {name: m for m, names in _MONTHS.items() for name in names}
_MONTH_RX = "|".join(sorted(_MONTH_OF, key=len, reverse=True))
#: "in", and its partners in the other seven languages - so "may" the verb
#: and "mars" the planet are not read as months on their own.
_PREP = (r"(?:in|during|back in|since|en|au mois de|im|nel|nel mese di|a|em|no mes de|"
         r"w|we)")

_RX_MONTH_YEAR = re.compile(rf"\b({_MONTH_RX})\s+((?:19|20)\d\d)\b")
_RX_LAST_MONTH_NAME = re.compile(rf"\blast ({_MONTH_RX})\b")
_RX_BACK_MONTH = re.compile(rf"\bback in ({_MONTH_RX})\b")
_RX_PREP_MONTH = re.compile(rf"\b{_PREP}\s+({_MONTH_RX})\b")
_RX_YEAR = re.compile(rf"\b{_PREP}\s+((?:19|20)\d\d)\b")
_RX_LAST_YEAR = re.compile(
    r"\blast year\b|\b(?:el )?ano pasado\b|\bl'?an(?:nee)? (?:derniere?|passee)\b"
    r"|\bletzte[sn]? jahr\b|\bl'?anno scorso\b|\bvorige? jaar\b"
    r"|\bzesz[lł]ym roku\b")
_RX_LAST_MONTH = re.compile(r"\blast month\b")
_RX_LAST_WEEK = re.compile(r"\blast week\b")


def _local(y: int, m: int, d: int = 1) -> float:
    """Midnight at the start of that day, in this PC's own time zone -
    the same calendar the owner means when they say "in June"."""
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 12
    return time.mktime((y, m, d, 0, 0, 0, 0, 0, -1))


def _month_window(y: int, m: int) -> tuple:
    return (_local(y, m), _local(y, m + 1))


def when(text: str, now: Optional[float] = None) -> Optional[tuple]:
    """The time window a question names, as (start, end) epoch seconds with
    the end exclusive - or None. A fixed parser, never a model:

        "last year" (and in the seven other languages)   that calendar year
        "last month" / "last week"                        that month / week
        "June 2025", "in 2025", "back in 2025"            as written
        "in June", "back in June"   the most recent June that has begun
        "last June"                 the most recent June that has ended

    A window that has not started yet is None: a question about the past
    cannot be about next June."""
    t = _norm(text)
    now = time.time() if now is None else float(now)
    lt = time.localtime(now)
    y, mo = lt.tm_year, lt.tm_mon
    out = None
    m = _RX_MONTH_YEAR.search(t)
    if m:
        out = _month_window(int(m.group(2)), _MONTH_OF[m.group(1)])
    elif _RX_LAST_YEAR.search(t):
        out = (_local(y - 1, 1), _local(y, 1))
    elif _RX_LAST_MONTH.search(t):
        out = _month_window(y, mo - 1)
    elif _RX_LAST_WEEK.search(t):
        today = _local(y, mo, lt.tm_mday)
        monday = today - lt.tm_wday * 86400
        # mktime for the day boundaries, not "- 7 * 86400": a week that
        # crosses a clock change is 167 or 169 hours long.
        s = time.localtime(monday - 7 * 86400 + 12 * 3600)
        out = (_local(s.tm_year, s.tm_mon, s.tm_mday), monday)
    else:
        m = _RX_LAST_MONTH_NAME.search(t)
        if m:
            n = _MONTH_OF[m.group(1)]
            out = _month_window(y if n < mo else y - 1, n)
        else:
            m = _RX_BACK_MONTH.search(t) or _RX_PREP_MONTH.search(t)
            if m:
                n = _MONTH_OF[m.group(1)]
                out = _month_window(y if n <= mo else y - 1, n)
            else:
                m = _RX_YEAR.search(t)
                if m:
                    out = (_local(int(m.group(1)), 1), _local(int(m.group(1)) + 1, 1))
    if out is None or out[0] > now:
        return None
    return out


def is_past_question(text: str, now: Optional[float] = None) -> bool:
    """Is this question about the past? The strict word check (see the
    module docstring): a past cue, or a date that can only be the past
    ("back in June", "June 2025", "in 2019")."""
    now = time.time() if now is None else float(now)
    t = _norm(text)
    if not t:
        return False
    if any(rx.search(t) for rx in _PAST):
        return True
    # A month WITH a year, or a year, that has already ended.
    m = _RX_MONTH_YEAR.search(t) or _RX_YEAR.search(t)
    if m:
        w = when(t, now)
        return w is not None and w[1] <= now
    return False


def is_belief_question(text: str) -> bool:
    """"What did I tell you / what did you think": about what Jarvis KNEW,
    not about what was true."""
    t = _norm(text)
    return any(rx.search(t) for rx in _BELIEF)


# ---------------------------------------------------------------- recall --

def _day(ts) -> str:
    try:
        return time.strftime("%Y-%m-%d", time.localtime(float(ts)))
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def label(fact: dict) -> str:
    """A retired fact's words, with when it stopped being true on the end.
    valid_to is that date (retire() sets it; retired_at is only when Jarvis
    was told)."""
    text = str(fact.get("text", ""))
    day = _day(fact.get("valid_to") or fact.get("retired_at"))
    return f"{text} (no longer true since {day})" if day else f"{text} (no longer true)"


def past_hits(store, query: str, *, k: int = PAST_K, now: Optional[float] = None,
              exclude=()) -> list:
    """Retired facts that match a question about the past, newest-believed
    first as search ranks them, at most `k`. Each is a copy with its text
    labelled and `past: True`."""
    if k <= 0:
        return []
    now = time.time() if now is None else float(now)
    window = when(query, now)
    if window is not None and is_belief_question(query):
        # What Jarvis believed at the END of that window - the latest moment
        # the question covers, and never later than now.
        cands = _search(store, query, k=_WIDE, known_at=min(window[1], now) - 0.001)
    else:
        cands = _search(store, query, k=_WIDE, include_retired=True)
    skip = set(exclude)
    out = []
    for f in cands:
        if f.get("current") or f.get("id") in skip:
            continue
        if window is not None and not is_belief_question(query):
            start, end = window
            vf = f.get("valid_from") or 0
            vt = f.get("valid_to")
            # True at some point in the window: began before it ended, and
            # ended after it began.
            if not (vf < end and (vt is None or vt > start)):
                continue
        g = dict(f)
        g["past"] = True
        g["no_longer_true_since"] = g.get("valid_to") or g.get("retired_at")
        g["text"] = label(f)
        out.append(g)
        if len(out) >= k:
            break
    return out


def _search(store, query: str, **kw) -> list:
    """store.search with the entity layer on (memory wave 3, 2026-09-25):
    "my sister" also finds what is saved about Priya - the alias table
    looked up, the names added to the question, the linked facts a third
    list. No model is asked (jarvis_memory.py, "The entity layer"). A store
    from before the entity layer does not take the argument: the old
    search, unchanged."""
    try:
        return store.search(query, entities=True, **kw)
    except TypeError:
        return store.search(query, **kw)


def recall(store, query: str, k: int, now: Optional[float] = None) -> list:
    """What a chat turn recalls. Exactly store.search(query, k=k,
    entities=True) for an ordinary question; for a question about the past,
    that plus up to min(PAST_K, k) retired facts, labelled. k <= 0 is none
    at all.

    Only the current search can raise (as it always could - the caller
    already handles that). Anything going wrong in the past half gives the
    current facts alone: the old behaviour."""
    hits = _search(store, query, k=k)
    if k <= 0:
        return hits
    try:
        if not is_past_question(query, now):
            return hits
        return hits + past_hits(store, query, k=min(PAST_K, k), now=now,
                                exclude={h.get("id") for h in hits})
    except Exception:
        return hits
