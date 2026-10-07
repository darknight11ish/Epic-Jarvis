"""jarvis_places.py - "Where did I put ...?" (2026-09-28; docs/JARVIS-API.md
section 77).

NEW MODULE, shipped whole, no patch of its own. jarvis_quick.py asks it for
"where is my passport?" and jarvis_auto_learn.py asks it whether a newly
learned fact only MOVES a thing the owner already told Jarvis about.

THE OWNER'S CHOICE (2026-09-28, docs/RESEARCH-AUDIT-2026-09-28.md section 3,
idea 4): from the owner's own words - "the passport is in the top drawer",
"I put the spare key under the blue pot" - Jarvis keeps where a thing is. A
NEWER place replaces the older one (older news is kept as history and never
overwrites newer news), and "where is my passport?" / "where did I put the
spare key?" is answered WITHOUT the AI model, plainly, with when it was
said: "You said on Tuesday: in the top drawer."

IT IS ORDINARY MEMORY. Nothing here saves anything. A place is a fact the
learner proposed from the owner's own words, saved (or left as a card) by
every check automatic learning already makes: the owner's own live words,
grounded, not sensitive - "the spare key is under the flowerpot" is a
home-security detail and waits for a yes, like any sensitive fact - and
listed under "Saved automatically" with Forget and "Erase the words". What
is new is only this:

  * place_of(fact) reads a fact's words with FIXED RULES (no model): which
    thing, and where. "Owner's passport is in the top drawer", "The spare
    key is under the blue pot", "Owner put the spare key under the blue
    pot", "Owner keeps their glasses on the hall table", "Owner's car keys
    are with Dave". English only. A thing that is a person, a pet or an
    event, and a "place" that is a date or a time ("the wedding is in May"),
    is not a place - so those still get every card they got before.
  * moved(new, old): both are places of the SAME thing, somewhere
    different. automatic learning (jarvis_auto_learn.after_pass) then saves
    the new place WITHOUT the correction card a changed fact otherwise gets
    (the owner's choice: things move, and asking every time the keys move
    would be a nag), and the older place is ended as history by
    apply_move() - using the "true from" rules every correction uses, so
    OLDER news (a place the owner's words date before the one Jarvis keeps)
    is filed as history and never replaces the newer place.
  * where_question(text) is the fast path's grammar: "where is my
    passport?", "where did I put the spare key?", "where are my car keys?",
    "do you know where my glasses are?". Only with "my", "the" or "our" in
    front of the thing, so "where is Paris?" is never ours.
  * lookup(store, thing) finds the place facts in use for that thing -
    current, not erased, not forgotten - newest first. None found: the fast
    path hands the question to the model, exactly as before.

NOTHING LEAVES THIS PC, and nothing here writes except apply_move(), which
ends ONE older place through MemoryStore.retire() - never a delete, never
the words.
"""
from __future__ import annotations

import json
import re
import time
from contextlib import closing
from typing import Optional

#: The most places one answer names ("where are my keys?" with a car key and
#: a spare key saved).
ANSWER_MAX = 3

#: How far back lookup() reads, newest first - a bound, not a filter.
SCAN_MAX = 400

#: Where a thing can be. Longest first, so "on top of" wins over "on".
_PREPS = ("in the back of", "at the back of", "in front of", "on top of", "next to",
          "underneath", "beneath", "behind", "beside", "inside", "under", "above", "below",
          "into", "onto", "with", "near", "in", "on", "at", "by", "to")
_PREP_RX = "|".join(p.replace(" ", r"\s+") for p in _PREPS)

_OWN = r"(?:the\s+)?(?:owner|user)(?:'s|s')?|my|our|their|his|her|the"
_THING = r"[a-z][a-z0-9'\- ]{0,40}?"

#: "Owner's passport is in the top drawer" / "The spare keys are under the pot"
_BE = re.compile(
    rf"^(?:{_OWN})\s+(?P<thing>{_THING})\s+(?:is|are|was|were|has\s+been|have\s+been)"
    rf"(?:\s+(?:now|kept|stored|always|usually|currently))*\s+(?P<prep>{_PREP_RX})\s+"
    r"(?P<place>.+)$", re.I)
#: "Owner put the spare key under the blue pot" / "Owner keeps their glasses ..."
_DID = re.compile(
    r"^(?:the\s+)?(?:owner|user|i)\s+(?:(?:has|have|had|just|now|always|usually)\s+)*"
    r"(?:put|puts|left|leaves|placed|places|keeps|keep|kept|stores|stored|store|stashed"
    r"|stashes|hid|hides|hidden|moved|moves|parked|parks)\s+"
    rf"(?:(?:the|their|his|her|my|our|a|an)\s+)?(?P<thing>{_THING})\s+"
    rf"(?P<prep>{_PREP_RX})\s+(?P<place>.+)$", re.I)

#: Things that are not things: people, pets, events, and what Jarvis already
#: keeps one of in its own slot (where the owner lives or works).
_NOT_THINGS = set("""
sister brother mum mom mother dad father parents parent wife husband partner son daughter
child children kid kids baby family friend friends boss manager colleague neighbour neighbor
aunt uncle cousin nan gran grandma grandad grandpa grandmother grandfather girlfriend
boyfriend flatmate roommate housemate doctor gp dentist landlord landlady teacher
cat dog puppy kitten rabbit hamster parrot horse pet pets
wedding meeting party appointment birthday holiday holidays vacation trip exam exams
interview flight train bus gig concert match game class classes lesson lessons course
shift shifts funeral event events conference deadline anniversary
job work office house home flat apartment family company team school university college
""".split())
#: A "place" that is a date or a time is not a place.
_WHEN_WORDS = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november"
    r"|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow"
    r"|tonight|yesterday|morning|afternoon|evening|week|weekend|month|year|spring|summer"
    r"|autumn|fall|winter)s?\b|\b(?:\d{1,2}(?::\d\d)?\s*(?:am|pm)|(?:19|20)\d\d)\b", re.I)
_WHEN_WORD = (r"(?:january|february|march|april|may|june|july|august|september|october"
              r"|november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
              r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)")
#: A time on the END of a place: "... in January 2026", "... on Tuesday",
#: "... last week", "... yesterday", "... now".
_TRAILING_WHEN = re.compile(
    r"\s+(?:(?:in|on|during|since|back\s+in|last|this|early|late|mid)\s+"
    rf"(?:{_WHEN_WORD}(?:\s+(?:19|20)\d\d)?|(?:19|20)\d\d|week|weekend|month|year|morning"
    r"|afternoon|evening|night)"
    r"|(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _WHEN_WORD + r"(?:\s+(?:19|20)\d\d)?)"
    r"|yesterday|today|tonight|this\s+morning|last\s+night|earlier|recently|just\s+now"
    r"|now|for\s+now|at\s+the\s+moment|these\s+days|currently)$", re.I)
#: How a place begins: "the", "my", ... - or a word that is a place by
#: itself ("at work", "in storage"), or a name ("with Dave", "at Priya's").
#: "keeps fit by running" and "is on silent" are not places.
_PLACE_START = {"the", "my", "our", "a", "an", "his", "her", "their", "this", "that",
                "one", "some", "home", "work", "school", "bed", "storage", "town"}
_NOT_PLACES = {"silent", "charge", "loan", "sale", "hold", "mute", "standby", "order", "fire",
               "time", "track", "call", "board"}
#: Pronouns and other words a thing can never be.
_NOT_A_THING = {"it", "this", "that", "these", "those", "they", "them", "he", "she", "you",
                "i", "we", "one", "stuff", "things", "something", "everything", "anything",
                # "moved back to Leeds", "moved out to York": where the OWNER
                # went, which is where they live - a card, as it always was.
                "back", "away", "out", "over", "up", "down", "abroad", "there", "here",
                "myself", "themselves", "herself", "himself", "everyone", "everybody"}

_ADDED = re.compile(r"\s*\((?:(?:week|weekend) of |around |as of )?\d{4}(?:-\d{2}){0,2}\)")


def _tidy(text) -> str:
    """One space, curly quotes straight, our date brackets and the end
    punctuation off - the case kept (a place may start with a name)."""
    t = str(text or "").replace("’", "'").replace("‘", "'")
    t = _ADDED.sub(" ", t)
    t = re.sub(r"[.!?]+\s*$", "", t.strip())
    return " ".join(t.split())


def _plain(text) -> str:
    return _tidy(text).lower()


def _stem(word: str) -> str:
    """keys -> key, batteries -> battery; glasses stays one word either way."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def thing_key(thing: str) -> str:
    """The thing, as it is matched: lower case, no "my"/"the", each word
    singular. "My car keys" -> "car key"."""
    words = [w for w in re.findall(r"[a-z0-9][a-z0-9'\-]*", _plain(thing))
             if w not in ("my", "the", "our", "their", "his", "her", "a", "an", "owner's",
                          "owners", "user's")]
    return " ".join(_stem(w.rstrip("'")) for w in words)


def _good_thing(thing: str) -> bool:
    words = thing_key(thing).split()
    if not words or len(words) > 4:
        return False
    if words[0] in _NOT_A_THING or words[-1] in _NOT_A_THING:
        return False
    return not any(w in _NOT_THINGS or _stem(w) in _NOT_THINGS for w in words)


def _good_place(place: str) -> bool:
    p = place.strip(" ,;")
    if not p or len(p) > 80 or len(p.split()) > 10:
        return False
    first = p.split()[0]
    if first.lower() in _NOT_PLACES:
        return False
    if first.lower() not in _PLACE_START and not first[:1].isupper():
        return False
    return not _WHEN_WORDS.search(p)


def place_of(fact) -> Optional[dict]:
    """{"thing": "spare key", "key": "spare key", "prep": "under", "place":
    "the blue pot", "where": "under the blue pot"} for a fact that says
    where a thing is - else None. Fixed rules; see the module docstring."""
    t = _tidy(fact)
    if not t or len(t) > 200:
        return None
    for rx in (_BE, _DID):
        m = rx.match(t)
        if not m:
            continue
        thing = m.group("thing").strip().lower()
        prep = " ".join(m.group("prep").split()).lower()
        place = m.group("place").strip(" ,;")
        # "is in the top drawer now" / "for now", and WHEN it was put there
        # ("... in January 2026", "... last week", "... yesterday") - that is
        # the fact's "true from" date (jarvis_memory.true_from), not the place.
        for _ in range(2):
            place = _TRAILING_WHEN.sub("", place).strip(" ,;")
        if place.split()[:1] and place.split()[0].lower() in _PLACE_START:
            place = place[0].lower() + place[1:]
        if not _good_thing(thing) or not _good_place(place):
            return None
        # "moved the passport to the safe" / "into the lounge": where it
        # IS now is "in the safe", "in the lounge".
        said_prep = {"into": "in", "onto": "on", "to": "in"}.get(prep, prep)
        return {"thing": thing, "key": thing_key(thing), "prep": said_prep, "place": place,
                "where": f"{said_prep} {place}"}
    return None


def same_thing(a: str, b: str) -> bool:
    """Do two thing keys name the same thing? Exactly, word for word."""
    return bool(a) and a == b


def moved(new_fact, old_fact) -> bool:
    """Is `new_fact` the same thing as `old_fact`, somewhere else?"""
    n, o = place_of(new_fact), place_of(old_fact)
    return bool(n and o and same_thing(n["key"], o["key"])
                and _plain(n["where"]) != _plain(o["where"]))

# --------------------------------------------------------------------------
#   Finding a thing's place
# --------------------------------------------------------------------------


def _meta(raw) -> dict:
    try:
        m = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
    except (TypeError, ValueError):
        return {}
    return m if isinstance(m, dict) else {}


def lookup(store, thing: str, now: Optional[float] = None,
           exclude: tuple = ()) -> list:
    """The place facts IN USE for `thing` - current (valid_to empty or
    ahead), not erased, not forgotten - newest first, each a dict {"id",
    "text", "created", "valid_from", "meta", "place": place_of(...)}. An
    exact thing first; otherwise every thing whose words include all of
    the asked-for words ("keys" finds "car key" and "spare key"). [] when
    there is none. Never raises."""
    want = thing_key(thing)
    if not want:
        return []
    now = time.time() if now is None else float(now)
    head = want.split()[-1]
    try:
        with closing(store._connect()) as c:
            rows = c.execute(
                "SELECT id, text, created, valid_from, meta FROM facts"
                " WHERE erased_at IS NULL AND (valid_to IS NULL OR valid_to > ?)"
                " AND lower(text) LIKE ? ORDER BY valid_from DESC, created DESC, id DESC"
                " LIMIT ?", (now, f"%{head[:-1] if len(head) > 3 else head}%", SCAN_MAX)
            ).fetchall()
    except Exception:
        return []
    # Topic controls (docs/TOPIC-CONTROLS-DESIGN.md 4.4): this reader has its
    # own SQL, so it asks for the facts of topics that may not be USED and
    # leaves them out - "where is my passport?" is not answered from a topic
    # the owner switched off.
    try:
        hide = store.topic_blocked("use")
    except Exception:
        hide = frozenset()
    exact, wider = [], []
    for r in rows:
        r = dict(r)
        if int(r["id"]) in exclude or _meta(r.get("meta")).get("forgotten_at"):
            continue
        if int(r["id"]) in hide:
            continue
        p = place_of(r.get("text"))
        if p is None:
            continue
        r["place"] = p
        if same_thing(p["key"], want):
            exact.append(r)
        elif set(want.split()) <= set(p["key"].split()):
            wider.append(r)
    if exact:
        # One thing is in one place: the newest place said. Anything older
        # still in use (two places, neither ended) is left out of the answer
        # but not touched.
        return exact[:1]
    out, seen = [], set()
    for r in wider:
        if r["place"]["key"] in seen:
            continue
        seen.add(r["place"]["key"])
        out.append(r)
        if len(out) >= ANSWER_MAX:
            break
    return out


# --------------------------------------------------------------------------
#   The question, and the answer
# --------------------------------------------------------------------------

_DET = r"(?:my|the|our)"
_Q_THING = r"(?P<thing>[a-z][a-z0-9'\- ]{0,40}?)"
_WHERE = [re.compile(p) for p in (
    rf"where(?:'s|'re|\s+is|\s+are|\s+was|\s+were)\s+{_DET}\s+{_Q_THING}"
    r"(?:\s+(?:now|again|kept|stored|at\s+the\s+moment))?",
    rf"where\s+(?:did|do|have|had|would)\s+i\s+(?:(?:have|last)\s+)?(?:put|leave|left|keep"
    rf"|kept|hide|hid|stash|store|stored|park|parked)\s+{_DET}\s+{_Q_THING}"
    r"(?:\s+(?:last\s+time|again|this\s+time))?",
    rf"(?:do\s+you\s+know|can\s+you\s+tell\s+me|(?:can\s+you\s+)?remind\s+me|tell\s+me)\s+"
    rf"where\s+(?:i\s+(?:put|left|keep|kept|hid|stashed|stored|parked)\s+{_DET}\s+{_Q_THING}"
    rf"|{_DET}\s+{_Q_THING.replace('?P<thing>', '?P<thing2>')}\s+(?:is|are|was|were))",
)]
#: What "where is the ..." is often about that is never a thing put away.
_NOT_ASKED = re.compile(r"^(?:nearest|closest|best|cheapest|next|last|first|nicest|biggest"
                        r"|toilet|bathroom|loo|exit|station|airport|party|meeting|wedding"
                        r"|remote\s+control\s+for)\b")


def where_question(text) -> Optional[str]:
    """The thing asked about in "where is my passport?" and the like, or
    None when the sentence is not that question. Expects the fast path's
    normalised sentence (lower case, "please"/"Jarvis" off, no end
    punctuation) and reads the WHOLE of it."""
    s = _plain(text)
    s = re.sub(r"[?]+$", "", s).strip()
    for rx in _WHERE:
        m = rx.fullmatch(s)
        if not m:
            continue
        thing = next((g for g in m.groups() if g), "").strip()
        if not thing or _NOT_ASKED.match(thing) or not _good_thing(thing):
            return None
        return thing
    return None


_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")


def when_said(at, now: Optional[float] = None) -> str:
    """"today", "yesterday", "on Tuesday" (the last six days), "on 12
    September", or "on 12 September 2025" - when the owner said it."""
    now = time.time() if now is None else float(now)
    try:
        at = float(at)
        t, n = time.localtime(at), time.localtime(now)
    except (TypeError, ValueError, OverflowError, OSError):
        return ""
    import datetime as _dt
    days = (_dt.date(n.tm_year, n.tm_mon, n.tm_mday)
            - _dt.date(t.tm_year, t.tm_mon, t.tm_mday)).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"on {_WEEKDAYS[t.tm_wday]}"
    day = f"on {t.tm_mday} {_MONTHS[t.tm_mon - 1]}"
    return day if t.tm_year == n.tm_year else f"{day} {t.tm_year}"


def answer_words(found: list, now: Optional[float] = None) -> str:
    """The fast path's sentence for lookup()'s facts, plainly, with when
    each was said: "You said on Tuesday: in the top drawer." For several
    things: "You said: the car key, on the hook (on Tuesday); the spare key,
    with Dave (on 3 September)." Uses the fact's own place words only."""
    if not found:
        return ""
    if len(found) == 1:
        f = found[0]
        when = when_said(f.get("created"), now)
        lead = f"You said {when}" if when else "You said"
        return f"{lead}: {f['place']['where']}."
    parts = []
    for f in found[:ANSWER_MAX]:
        when = when_said(f.get("created"), now)
        parts.append(f"the {f['place']['thing']}, {f['place']['where']}"
                     + (f" ({when})" if when else ""))
    return "You said: " + "; ".join(parts) + "."

# --------------------------------------------------------------------------
#   A thing that moved (jarvis_auto_learn.after_pass)
# --------------------------------------------------------------------------


def older_place(store, fact: str, exclude: tuple = ()) -> Optional[dict]:
    """The place fact in use that `fact` would MOVE - the same thing,
    somewhere else - or None. Only an exact thing: "car key" never moves
    "spare key"."""
    p = place_of(fact)
    if p is None:
        return None
    for r in lookup(store, p["thing"], exclude=exclude):
        if same_thing(r["place"]["key"], p["key"]) and \
                _plain(r["place"]["where"]) != _plain(p["where"]):
            return r
    return None


def apply_move(store, new_id: int, old_id: int) -> str:
    """End the older place now that the newer one is saved - the owner's
    words, a thing that moved. Returns what was done: "moved" (the old
    place is history, replaced by the new one), "older_news" (the NEW
    fact's own words date it before the old one's - so the new one is filed
    as history and the old place stays in use: older news never replaces
    newer), or "" (nothing to do, or it could not be done).

    Dates, by the rules add(supersedes=) uses for every correction
    (jarvis_memory.py, "true from"): the old place ends when the new one's
    words say it began, if they say and it is after the old one began, and
    otherwise now. Never a delete; only MemoryStore.retire()."""
    try:
        new = store.get(int(new_id))
        old = store.get(int(old_id))
        if not new or not old:
            return ""
        now = time.time()
        if old.get("valid_to") is not None and float(old["valid_to"]) <= now:
            return ""
        import jarvis_memory as M
        said_new = M.said_from(new.get("meta"))
        said_old = M.said_from(old.get("meta"))
        nvf, ovf = float(new["valid_from"]), float(old["valid_from"])
        if said_new and said_old and nvf < ovf:
            done = store.retire(int(new_id), replaced_by=int(old_id), valid_to=ovf)
            return "older_news" if done else ""
        end = nvf if (said_new and ovf < nvf <= now) else now
        done = store.retire(int(old_id), replaced_by=int(new_id), valid_to=end)
        return "moved" if done else ""
    except Exception:
        return ""
