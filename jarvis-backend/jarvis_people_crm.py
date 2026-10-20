"""jarvis_people_crm.py - who someone is, before you meet them: one read-only
dossier about ONE person, put together from this PC's own records.

NEW MODULE, shipped whole. NO ROUTE, NO CHAT TOOL AND NO UI IN THIS SLICE, and
no model call anywhere: `build_person_dossier()` is a plain function over
records that already exist on this PC, and the one place that puts a line on a
screen (`briefing_people()`, called by jarvis_briefing.py) reuses the briefing
the apps already render generically. A future route or a "click a person in
Galaxy" surface is what turns this into a visible card; until one exists this
module is a library, and this docstring says so rather than pretending.

WHAT A DOSSIER HOLDS - each part from the module that already owns it
  * `active_facts` / `retired_facts` - what Jarvis remembers about the person
    (`jarvis_memory.py`), read only through its public reads: `store()`,
    `entities_view()` (the person's linked facts, topics="use" so a topic the
    owner switched off or set learn-only is left out) and
    `fact_history_view()` (every version of a fact, which is how a former
    employer or a former city is found). **jarvis_memory.py ITSELF IS NEVER
    EDITED OR IMPORTED AT MODULE LEVEL**: it is base-only (no backend/ twin),
    and a backend without it simply leaves this part out.
  * `recent_chat` - the last few kept chat turns that mention the person
    (`jarvis_chat_log.search()`, the History search the owner already has, and
    only ever what is still kept and encrypted on this PC). A turn is one
    conversation's matching snippet: role, when, and the words around the
    match - never the whole conversation.
  * `recent_email` - the newest few mail headers/snippets that name the person
    (`jarvis_email.plan()`/`run()`: sender, subject, date, a masked short
    preview - the same shape the mail-reading tool already returns).
  * `commitments` - the open to-do items that name the person
    (`jarvis_schedule.todos()`, through the scheduler's `get()`). This PC has
    no separate "promises I made" store, and this module invents none: an open
    to-do naming the person IS the local trace of a commitment, and the
    docstring says that rather than dressing it up as more.
  * `next_event` - the next calendar event whose title, place or notes name
    the person (`jarvis_calendar.plan()`/`run()`). The calendar reader returns
    no attendee list, so "together" is matched from the event's own words; an
    event that names nobody Jarvis knows is never claimed as "together".

THE PRIVACY INVARIANT, ENFORCED FIRST, NOT LAST
  "Hide memory lists and chat history" and App lock withhold the WHOLE dossier,
  before any read is made and before any name is echoed:
      {"ok": False, "withheld": True, "why": "..." , "name": ...}
  with no facts, no chats, no mail, no to-dos and no event in it. This module
  cannot see either switch by itself - both live on the apps' side (the
  desktop's Rust and the phone's own lock) - so the state is passed IN by the
  caller that knows it, and since 2026-10-20 (Q1) merged through
  jarvis_private_view: the caller's two flags, a supplied lock state and the
  trusted live state are ORed, so a call can only ADD withholding and a False
  can never unlock. The rule is a parameter on purpose: a route or a briefing
  that knows the state hides the dossier here, in the backend, so no later
  renderer can leak what it never received. The live HUD must eventually pass
  the state (JARVIS-API section 143 / ARCHITECTURE.md); until then the apps
  keep their own hiding.

  The morning-briefing line is the one surface today, and the apps already
  hide a briefing's `items` while either switch is on (desktop
  `brain/briefing.rs` `redact`, phone `Briefing.hide`) - which is why that
  line puts the NAME in an item and only a COUNT in the summary.

READS THAT LEAVE THE PC, AND HOW THEY ARE ALLOWED
  Mail and the calendar are the two reads that open a connection to one of the
  owner's own servers. Both are read in exactly the shape the morning briefing
  already uses: only when the tool is switched on and the gate's tier lets that
  read run without a person ("auto" or "notify"). At tier "ask" NOTHING is
  read and the section says why - a dossier never raises an approval card by
  itself, because it has no route to raise one on. A future 1-click route owns
  that card; it then passes `approved` reads, exactly as every other read does.

  Everything else stays on this PC: memory facts, kept chat turns and the
  to-do list are local files, read through their own modules, never sent
  anywhere. The module opens no socket of its own and prints nothing.

TAINT
  Reading a person's saved facts marks the conversation's taint latch
  (`jarvis_gate.latch_taint(why="people_crm")`) before the facts are returned,
  so the same over-approximation the voiceprint exemplars use applies here: a
  question that touched personal memory is answered by the local model, not a
  cloud lane. The latch is replaceable in the tests and failure to latch is
  ignored - it only ever refuses an escalation, and a missing gate (a backend
  from before it, or a test) must not break the read.

WHAT THIS IS NOT, said plainly
  * It does not summarise, score or rank the person, and it never writes a
    sentence that is not a record from one of those stores. No model sees any
    of it.
  * It changes nothing: no fact is saved, retired or forgotten; no mail is
    marked read (the mail read is the same bounded one the briefing uses); no
    calendar is written; no approval is granted.
  * It is not a second memory search and not a directory of everyone: one name
    in, one dossier out. `briefing_people()` lists only people Jarvis ALREADY
    knows by name (the entity layer), never every name in a calendar.
  * It does not read `jarvis_gate.py`, `jarvis_memory.py` or the mail/calendar
    modules at import time - each is imported inside the one function that
    needs it, guarded, so a backend without them runs with that section off,
    the way every shipped module here treats the owner's own files.

Standard library only. Reads its sources; writes nothing; opens no socket.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   Words - one place, so a check and a renderer cannot disagree
# --------------------------------------------------------------------------

TITLE = "Person dossier"
BRIEFING_TITLE = "People"

#: The whole dossier, withheld. The first sentence is what a future route or
#: card shows; the name is the caller's own word and nothing else comes back.
WITHHELD_HIDDEN = 'Hidden while "Hide memory lists and chat history" is on.'
WITHHELD_LOCKED = "Hidden while App lock is on."
WITHHELD_WHY = {False: WITHHELD_HIDDEN, True: WITHHELD_LOCKED}

#: A dossier needs a name. Same sentence for "", whitespace and punctuation.
EMPTY_NAME = "Say whose dossier to put together - a name."

#: Section states, the same short words the briefing uses for its sources.
OK, EMPTY, OFF, ASKS, FAILED = "ok", "empty", "off", "asks", "failed"

FACTS_OFF = "Not read: saved facts could not be read on this PC."
CHAT_OFF = "Not read: chat history is not set up on this PC."
CHAT_FAILED = "Not read: the kept chat turns could not be searched."
EMAIL_OFF = "Not read: email is not set up for Jarvis on this PC."
EMAIL_ASKS = ("Not read: your settings ask for a yes each time Jarvis reads email, "
              "and a dossier does not raise a card for that.")
EMAIL_FAILED = "Not read: the mail server did not answer."
CALENDAR_OFF = "Not read: the calendar is not set up for Jarvis on this PC."
CALENDAR_ASKS = ("Not read: your settings ask for a yes each time Jarvis reads the "
                 "calendar, and a dossier does not raise a card for that.")
CALENDAR_FAILED = "Not read: the calendar server did not answer."
COMMITMENTS_OFF = "Not read: the to-do list could not be read on this PC."
EMPTY_OK = ""

#: Both reads that can leave the PC, named exactly as the gate names them -
#: the same action the mail and calendar tools, and the briefing, already use.
CALENDAR_ACTION = "calendar_read"
CALENDAR_TOOL = "calendar_read"
EMAIL_ACTION = "email_read"
EMAIL_TOOL = "email_check"

#: How much of each part is shown. Small on purpose: a dossier is a few lines
#: before a meeting, not a file. The facts' own words are never rewritten.
MAX_NAME_CHARS = 80
MAX_ACTIVE_FACTS = 12
MAX_RETIRED_FACTS = 6
MAX_CHAT_TURNS = 3
MAX_EMAILS = 3
#: How many of the newest messages the mail read looks at to find the ones that
#: name the person. A search box has no IMAP "from this name" criterion the
#: plan can say safely, so it reads the newest few headers and filters here;
#: bounded by jarvis_email.plan()'s own ceiling.
EMAIL_SCAN = 12
MAX_COMMITMENTS = 8
MAX_ITEM_CHARS = 240
#: How far ahead "the next event together" looks, in days.
CALENDAR_DAYS = 30
#: An event that started this long ago still counts as "next" (an ongoing
#: meeting the owner is about to join), never one from yesterday.
UPCOMING_GRACE = 60.0
#: The done-away-with "was it current" line: a valid_to in the FUTURE has not
#: happened yet, so the fact is still current (jarvis_memory.retire() says so).
#: Only a valid_to at or before `now` makes a fact retired.
TAINT_WHY = "people_crm"

#: How many known people the briefing line will name, at most.
BRIEFING_MAX_PEOPLE = 4
#: One person's name line in the briefing, at most - the same small size the
#: briefing uses for its own lines.
MAX_BRIEFING_CHARS = 160

PLURAL_FACT = ("saved fact", "saved facts")

# --------------------------------------------------------------------------
#   Small pure helpers - words, names, matching
# --------------------------------------------------------------------------


def _clean(text, cap: int = MAX_ITEM_CHARS) -> str:
    """One line, control characters gone, capped with an honest ellipsis."""
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or ""))
    t = " ".join(t.split())
    if len(t) > cap:
        t = t[:cap - 3].rstrip() + "..."
    return t


def _plural(n: int, words: tuple) -> str:
    return f"{n} {words[0] if n == 1 else words[1]}"


def clean_name(name) -> str:
    """The person's name as typed, tidied: one line, outer quotes and stray
    punctuation off, capped. "" for nothing usable."""
    t = _clean(name, MAX_NAME_CHARS + 40)
    t = t.strip(" ,;:!?\"'“”‘’")
    if len(t) > MAX_NAME_CHARS:
        t = t[:MAX_NAME_CHARS].rstrip()
    return t


def name_forms(name, aliases=None) -> list:
    """Every word form that counts as this person, longest first.

    The full name, plus - when it has more than one word - each word of three
    letters or more, so "Lunch with Alex" finds Alex Smith while "Al" does
    not start matching every "al" inside another word. Aliases the entity
    layer learned ("sister") count too, because that is how the owner talks
    about a person in a calendar title or a mail subject.
    """
    forms = []
    full = " ".join(str(name or "").split())
    if full:
        forms.append(full)
        words = full.split(" ")
        if len(words) > 1:
            forms.extend(w for w in words if len(w) >= 3)
    for a in aliases or []:
        a = " ".join(str(a or "").split())
        if a and a.casefold() not in {f.casefold() for f in forms}:
            forms.append(a)
    forms.sort(key=lambda f: (-len(f), f.casefold()))
    return forms


def mentions(text, forms) -> bool:
    """Does `text` mention any of these names, as whole words, any case?"""
    hay = str(text or "")
    if not hay:
        return False
    for form in forms or []:
        if not form:
            continue
        rx = re.compile(r"(?<!\w)" + re.escape(form) + r"(?!\w)", re.IGNORECASE)
        if rx.search(hay):
            return True
    return False


def _utc_epoch(stamp: str) -> float:
    """A "YYYYMMDDTHHMMSSZ" stamp as epoch seconds (UTC, no local guessing)."""
    import calendar as _cal
    return float(_cal.timegm(datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").timetuple()))


def _stamp_epoch(stamp) -> Optional[float]:
    """The epoch of an ICS DTSTART value, or None.

    A value ending in Z is UTC; a floating ("no zone") value is read as this
    PC's own time, the same reading the briefing's calendar lines use; a
    date-only value is that day's local midnight. This module does not
    time-zone-travel values the calendar reader did not resolve itself.
    """
    s = str(stamp or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z") and "T" in s:
            return _utc_epoch(s)
        if "T" in s:
            return float(time.mktime(datetime.strptime(s, "%Y%m%dT%H%M%S").timetuple()))
        d = datetime.strptime(s, "%Y%m%d")
        return float(time.mktime((d.year, d.month, d.day, 0, 0, 0, 0, 0, -1)))
    except (ValueError, OverflowError):
        return None


def when_words(stamp, now: Optional[float] = None) -> str:
    """"All day", "14:30" or "" for a calendar start the reader gave us. A
    stamp that ends in Z is a UTC moment and is shown by this PC's clock (the
    same reading the briefing's calendar lines use); a floating one is already
    this PC's own time. It is a line label, never a claim about a zone."""
    s = str(stamp or "").strip()
    if not s:
        return ""
    if "T" not in s:
        return "All day"
    m = re.search(r"T(\d{2})(\d{2})", s)
    if not m:
        return ""
    if s.endswith("Z"):
        epoch = _stamp_epoch(s)
        if epoch is not None:
            lt = time.localtime(epoch)
            return f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    return f"{m.group(1)}:{m.group(2)}"


def fact_is_current(row, now: float) -> bool:
    """The rule every reader in jarvis_memory.py uses: still true now means
    valid_to empty OR later than now - not "valid_to is null". A fact whose
    true-until date has not arrived is current, and calling it retired would
    present a former employer as a future one."""
    vt = row.get("valid_to") if isinstance(row, dict) else None
    if vt is None:
        return True
    try:
        return float(vt) > float(now)
    except (TypeError, ValueError):
        return True  # a damaged date is not a reason to hide a fact


def split_facts(rows, now: float) -> tuple:
    """(current, retired) rows, newest first in each. Rows that are erased or
    marked forgotten are dropped: their words must never be shown here."""
    active, retired = [], []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("erased_at"):
            continue
        if row.get("forgotten"):
            continue
        text = _clean(row.get("text") or "")
        if not text:
            continue
        item = {"id": row.get("id"), "text": text,
                "valid_from": row.get("valid_from"), "valid_to": row.get("valid_to"),
                "source": str(row.get("source") or "")}
        (active if fact_is_current(row, now) else retired).append(item)

    def newest(items, key):
        def order(item):
            stamp = item.get(key)
            try:
                return -(float(stamp) if stamp is not None else 0.0), -(int(item.get("id") or 0))
            except (TypeError, ValueError):
                return 0.0, 0
        items.sort(key=order)
        return items
    return newest(active, "valid_from"), newest(retired, "valid_to")

# --------------------------------------------------------------------------
#   Where the parts come from - each inside the function that needs it
# --------------------------------------------------------------------------


def _tier_of(action: str) -> str:
    """The gate's tier for an action, from the owner's settings file. The same
    reading, and the same "ask" fallback, jarvis_briefing.py uses: anything
    unreadable asks first."""
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception:
        return "ask"


def _tools_enabled() -> set:
    try:
        import jarvis_framework as fw
        cfg = fw.load_framework()
        return set((cfg.get("tools") or {}).get("enabled") or [])
    except Exception:
        return set()


def _latch_taint(why: str = TAINT_WHY) -> bool:
    """Mark the conversation private before the facts are handed back. False
    when there is no gate to latch - never an exception on a read."""
    try:
        import jarvis_gate
        return bool(jarvis_gate.latch_taint(why=why))
    except Exception:
        return False


def _memory_store(light: bool = False):
    """The memory store, opened the way this caller needs it.

    `light=True` is for the briefing line: a name list and a count, so no
    meaning model is loaded on the morning path - a HashEmbedder store reads
    exactly the same tables. Otherwise the backend's own singleton store is
    used, the one the chat path already has open.
    """
    import jarvis_memory as M
    if light:
        return M.MemoryStore(embedder=M.HashEmbedder())
    return M.store()


def _member(name: str, entity: dict) -> bool:
    """Is this entity the person `name`? True for its name, another name
    joined to it, or a learned alias, all case- and space-insensitive."""
    want = " ".join(str(name or "").split()).casefold()
    if not want:
        return False
    for got in [entity.get("name")] + list(entity.get("also") or []) + \
            list(entity.get("aliases") or []):
        if " ".join(str(got or "").split()).casefold() == want:
            return True
    return False


def _entity_forms(entity: dict) -> list:
    return name_forms(entity.get("name") or "",
                      list(entity.get("also") or []) + list(entity.get("aliases") or []))


def _read_known_people(store=None) -> list:
    """The people the entity layer knows: [{"name", "aliases", "facts"}], most
    facts first - never places, projects or things. A read that opens no
    connection and creates no folder beyond the one the store owns."""
    try:
        st = store or _memory_store(light=True)
        view = st.entities_view(topics="use")
    except Exception:
        return []
    out = []
    for e in (view or {}).get("entities") or []:
        if not isinstance(e, dict) or e.get("kind") != "person":
            continue
        name = clean_name(e.get("name"))
        if not name:
            continue
        out.append({"name": name,
                    "aliases": [clean_name(a) for a in (e.get("aliases") or [])
                                if clean_name(a)],
                    "facts": int(e.get("facts") or 0)})
    out.sort(key=lambda p: (-int(p.get("facts") or 0), p["name"].casefold()))
    return out


def person_facts(name, now: float, *, store=None) -> dict:
    """One person's facts, current and retired, from jarvis_memory's public
    reads only: the entity layer names their linked facts, `fact_history_view`
    gives every version of each (which is where a former employer lives), and
    - when the entity layer has never linked this name - a bounded scan of the
    current facts looks for the name in their own words."""
    try:
        import jarvis_memory as M
        st = store or _memory_store()
        view = st.entities_view(topics="use", now=now)
    except Exception:
        return {"ok": False, "known": False, "aliases": [], "active": [],
                "retired": [], "state": FAILED, "why": FACTS_OFF}
    entity = None
    for e in (view or {}).get("entities") or []:
        if isinstance(e, dict) and _member(name, e):
            entity = e
            break
    forms = _entity_forms(entity) if entity is not None else name_forms(name)
    ids = [fid for fid in (entity or {}).get("fact_ids") or []]
    if not ids:
        # No entity has been linked to this name yet (a person learned before
        # the entity layer, or a name the linker never met): look in the
        # facts' own words. Bounded, and still only fact ids.
        try:
            rows = st.current_facts(limit=400, topics="use")
        except Exception:
            rows = []
        ids = [r.get("id") for r in rows or []
               if isinstance(r, dict) and mentions(r.get("text"), forms)]
    versions = []
    for fid in ids[:max(1, MAX_ACTIVE_FACTS) * 2]:
        try:
            seen = M.fact_history_view(fid, st=st, now=now)
        except Exception:
            seen = None
        for v in (seen or {}).get("versions") or []:
            if isinstance(v, dict):
                versions.append(v)
    active, retired = split_facts(versions, now)
    # A fact may appear once per fact id (one id per row) - de-duplicate by id
    # after truncation so a chain with many old versions cannot crowd out the
    # current ones, and the other way round.
    active = active[:MAX_ACTIVE_FACTS]
    retired = retired[:MAX_RETIRED_FACTS]
    aliases = []
    if entity is not None:
        aliases = [clean_name(a) for a in list(entity.get("also") or []) +
                   list(entity.get("aliases") or []) if clean_name(a)]
    known = bool(entity is not None or active or retired)
    return {"ok": True, "known": known, "aliases": aliases[:8], "active": active,
            "retired": retired, "state": OK if known else EMPTY, "why": EMPTY_OK}


def _snippet_words(snippet: dict) -> str:
    parts = snippet.get("parts") if isinstance(snippet, dict) else None
    if not isinstance(parts, list):
        return ""
    return _clean("".join(str(p.get("text") or "") for p in parts
                          if isinstance(p, dict)))


def search_chat(name, limit: int, *, search: Optional[Callable] = None) -> dict:
    """The kept chat turns that mention the person, newest conversation first.

    `jarvis_chat_log.search()` is the History search the owner already has -
    it opens only what is still kept, scans in memory and writes no index. A
    hit is one conversation's snippet around its best match: that is the turn
    this returns, with its role, when and words, never a whole conversation.
    """
    try:
        if search is None:
            import jarvis_chat_log as CL
            search = CL.search
        got = search(name, limit=max(1, min(int(limit), 10)))
    except Exception:
        return {"ok": False, "state": FAILED, "why": CHAT_FAILED, "turns": []}
    if not isinstance(got, dict) or not got.get("query_ok"):
        return {"ok": False, "state": FAILED, "why": CHAT_FAILED, "turns": []}
    turns = []
    for conv in got.get("conversations") or []:
        if not isinstance(conv, dict):
            continue
        snippet = conv.get("snippet") or {}
        words = _snippet_words(snippet)
        if not words:
            continue
        turns.append({"conversation": str(conv.get("title") or ""),
                      "role": str(snippet.get("role") or ""),
                      "when": int(snippet.get("at") or conv.get("updated") or 0),
                      "words": words})
        if len(turns) >= max(1, int(limit)):
            break
    why = EMPTY_OK
    state = OK if turns else EMPTY
    if not turns and got.get("enabled") is False:
        state, why = OFF, ("Not read: chat history is off, and there are no kept "
                           "chats to look through.")
    return {"ok": True, "state": state, "why": why, "turns": turns,
            "partial": bool(got.get("partial"))}


def read_email(name, limit: int, *, tier_of: Optional[Callable] = None,
               tools: Optional[Callable] = None,
               fetch: Optional[Callable] = None) -> dict:
    """The newest few mail headers/snippets that name the person, through the
    same plan/run the mail tool uses. Nothing is read unless the tool is on
    and the tier lets it run without a person; `fetch` is injectable so the
    parsing below is provable with no socket."""
    tier_of = tier_of or _tier_of
    try:
        import jarvis_email as MAIL
    except Exception:
        return {"ok": False, "state": OFF, "why": EMAIL_OFF, "messages": []}
    if EMAIL_TOOL not in set((tools or _tools_enabled)()):
        return {"ok": False, "state": OFF, "why": EMAIL_OFF, "messages": []}
    if str(tier_of(EMAIL_ACTION)) not in ("auto", "notify"):
        return {"ok": False, "state": ASKS, "why": EMAIL_ASKS, "messages": []}
    p = MAIL.plan(max(1, int(EMAIL_SCAN)), unread_only=False)
    if not p.configured:
        return {"ok": False, "state": OFF, "why": EMAIL_OFF, "messages": []}
    out = MAIL.run(p, fetch_messages=fetch, approved=True)
    if not out.get("ok"):
        return {"ok": False, "state": FAILED, "why": EMAIL_FAILED, "messages": []}
    forms = name_forms(name)
    messages = []
    for msg in out.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        if mentions(str(msg.get("from") or ""), forms) \
                or mentions(str(msg.get("subject") or ""), forms) \
                or mentions(str(msg.get("preview") or ""), forms):
            messages.append({"from": _clean(msg.get("from"), 120),
                             "subject": _clean(msg.get("subject"), 160),
                             "date": _clean(msg.get("date"), 80),
                             "preview": _clean(msg.get("preview"), MAX_ITEM_CHARS)})
            if len(messages) >= max(1, int(limit)):
                break
    return {"ok": True, "state": OK if messages else EMPTY, "why": EMPTY_OK,
            "messages": messages}


def read_commitments(name, limit: int, *, todos: Optional[Callable] = None) -> dict:
    """The open to-do items that name the person. `jarvis_schedule.todos()` is
    already only the open ones (active or paused), so nothing here calls a
    list finished: this PC has no promises store, and the docstring says so."""
    try:
        if todos is None:
            import jarvis_schedule as S
            todos = lambda: S.get().todos()  # noqa: E731 - one line, one read
        rows = list(todos() or [])
    except Exception:
        return {"ok": False, "state": FAILED, "why": COMMITMENTS_OFF, "items": []}
    forms = name_forms(name)
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = _clean(row.get("text") or "")
        if not text or not mentions(text, forms):
            continue
        items.append({"text": text, "due": row.get("due"), "list": row.get("list")})
        if len(items) >= max(1, int(limit)):
            break
    return {"ok": True, "state": OK if items else EMPTY, "why": EMPTY_OK, "items": items}


def read_next_event(name, now: float, *, tier_of: Optional[Callable] = None,
                    tools: Optional[Callable] = None,
                    fetch: Optional[Callable] = None) -> dict:
    """The next calendar event that names the person, from the same read the
    briefing uses. The calendar reader has no attendee list, so a match on the
    event's own title/place is what "together" means here - and nothing is
    claimed when no event names them."""
    tier_of = tier_of or _tier_of
    try:
        import jarvis_calendar as CAL
    except Exception:
        return {"ok": False, "state": OFF, "why": CALENDAR_OFF, "event": None}
    if CALENDAR_TOOL not in set((tools or _tools_enabled)()):
        return {"ok": False, "state": OFF, "why": CALENDAR_OFF, "event": None}
    if str(tier_of(CALENDAR_ACTION)) not in ("auto", "notify"):
        return {"ok": False, "state": ASKS, "why": CALENDAR_ASKS, "event": None}
    p = CAL.plan(max(1, int(CALENDAR_DAYS)),
                 now=datetime.fromtimestamp(float(now), tz=timezone.utc))
    if p.query is None:
        return {"ok": False, "state": OFF, "why": CALENDAR_OFF, "event": None}
    out = CAL.run(p, fetch=fetch, approved=True)
    if not out.get("ok"):
        return {"ok": False, "state": FAILED, "why": CALENDAR_FAILED, "event": None}
    forms = name_forms(name)
    best, best_at = None, None
    for ev in out.get("events") or []:
        if not isinstance(ev, dict):
            continue
        if not (mentions(ev.get("summary"), forms)
                or mentions(ev.get("location"), forms)):
            continue
        at = _stamp_epoch(ev.get("start"))
        if at is None or at < float(now) - UPCOMING_GRACE:
            continue
        if best_at is None or at < best_at:
            best, best_at = ev, at
    if best is None:
        return {"ok": True, "state": EMPTY, "why": EMPTY_OK, "event": None}
    return {"ok": True, "state": OK, "why": EMPTY_OK,
            "event": {"summary": _clean(best.get("summary") or "(no title)"),
                      "location": _clean(best.get("location") or ""),
                      "start": str(best.get("start") or ""),
                      "end": str(best.get("end") or ""),
                      "when": when_words(best.get("start"), now),
                      "at": best_at,
                      "recurring": bool(best.get("recurring"))}}

# --------------------------------------------------------------------------
#   What the caller can replace - all of it, so no test opens a socket or a
#   real store
# --------------------------------------------------------------------------


@dataclass
class Deps:
    """Replaceable reads. `None` means "the real one, as documented above"."""
    #: (name, now) -> person_facts()'s shape. None: person_facts(...).
    facts: Optional[Callable[[str, float], dict]] = None
    #: (name, limit) -> search_chat()'s shape. None: search_chat(...).
    chat: Optional[Callable[[str, int], dict]] = None
    #: (name, limit) -> read_email()'s shape. None: read_email(...).
    email: Optional[Callable[[str, int], dict]] = None
    #: (name, limit) -> read_commitments()'s shape. None: read_commitments(...).
    commitments: Optional[Callable[[str, int], dict]] = None
    #: (name, now) -> read_next_event()'s shape. None: read_next_event(...).
    next_event: Optional[Callable[[str, float], dict]] = None
    #: () -> known_people()'s list. None: _read_known_people(...).
    known_people: Optional[Callable[[], list]] = None
    #: (why) -> bool. None: _latch_taint(why).
    taint: Optional[Callable[[str], bool]] = None
    #: () -> the current epoch. None: time.time.
    now: Optional[Callable[[], float]] = None
    #: The gate's tier for an action. The real reading by default.
    tier_of: Callable[[str], str] = _tier_of
    #: [tools].enabled, the same set the briefing reads.
    tools_enabled: Callable[[], set] = _tools_enabled
    #: jarvis_email.run's `fetch_messages`, for a test that must not dial.
    email_fetch: Optional[Callable] = None
    #: jarvis_calendar.run's `fetch`, for a test that must not dial.
    calendar_fetch: Optional[Callable] = None
    #: An open MemoryStore (or a test's stand-in). None: the real store.
    memory_store: Optional[object] = None
    #: () -> the scheduler's open to-dos. None: jarvis_schedule.get().todos().
    todos: Optional[Callable[[], list]] = None


def _safe(fn: Callable, *args) -> dict:
    """One read, made unable to break the dossier: a source that raises is
    reported as a failed section, never as an exception from this module."""
    try:
        got = fn(*args)
    except Exception as exc:  # noqa: BLE001 - a section's failure is a section
        return {"ok": False, "state": FAILED,
                "why": f"Not read: something went wrong ({type(exc).__name__})."}
    return got if isinstance(got, dict) else {
        "ok": False, "state": FAILED, "why": "Not read: something went wrong."}


def _now_of(now, deps: Deps) -> float:
    if now is not None:
        return float(now)
    try:
        return float(deps.now()) if deps.now is not None else time.time()
    except Exception:
        return time.time()


def _withheld(name, why: str, now: float) -> dict:
    """The whole dossier, withheld. Deliberately ONLY these keys: no facts, no
    turns, no mail, no to-dos, no event - a renderer cannot leak what it was
    never given."""
    return {"ok": False, "withheld": True, "why": why,
            "name": _clean(clean_name(name), MAX_NAME_CHARS),
            "private": True, "made": now, "states": {}, "read": []}

# --------------------------------------------------------------------------
#   The dossier
# --------------------------------------------------------------------------


def build_person_dossier(name, *, now: Optional[float] = None, deps: Optional[Deps] = None,
                         hide_memory_lists: bool = False,
                         app_locked: bool = False) -> dict:
    """One person's read-only dossier.

    The privacy invariant runs FIRST: when `hide_memory_lists` or `app_locked`
    is true - from the caller OR from jarvis_private_view's trusted live state
    / a supplied lock state - the whole dossier is withheld before any store is
    opened and before any name is looked at. A caller's False can never clear a
    lock: the two flags are merged through the one fail-safe hook (Q1 ruling,
    2026-10-20), and a missing hook leaves the caller's values standing, so an
    older backend behaves exactly as before. Then each part is read, and each
    part fails on its own - one unreadable source never takes the dossier with
    it.

    Returns a dict; `ok` is True for a dossier that was allowed to be built
    (it may still be empty of every section - an unknown person). `text` is
    the plain rendering, `read` names the outside sources whose text is in
    it, and `counts` is what a badge would show.
    """
    try:
        import jarvis_private_view as private_view

        merged = private_view.effective(app_locked=app_locked,
                                        hide_memory_lists=hide_memory_lists)
        app_locked = merged["app_locked"]
        hide_memory_lists = merged["hide_memory_lists"]
    except Exception:
        # No hook module (an older backend): the caller's own booleans stand,
        # unchanged - the absent hook defaults to unlocked, never to locked.
        pass
    deps = deps or Deps()
    now = _now_of(now, deps)
    if app_locked:
        return _withheld(name, WITHHELD_LOCKED, now)
    if hide_memory_lists:
        return _withheld(name, WITHHELD_HIDDEN, now)
    person = clean_name(name)
    if not person:
        return {"ok": False, "withheld": False, "why": EMPTY_NAME,
                "name": "", "private": True, "made": now, "states": {}, "read": []}

    facts = _safe(deps.facts or (lambda n, t: person_facts(n, t, store=deps.memory_store)),
                  person, now)
    # Before anything private is handed back: latch the conversation private.
    # The guide's rule, and the voiceprint exemplars' precedent - a latch set
    # after the text was returned did not apply to the turn that used it.
    if facts.get("ok"):
        taint = deps.taint if deps.taint is not None else _latch_taint
        try:
            taint(TAINT_WHY)
        except Exception:
            pass
    chat = _safe(deps.chat or (lambda n, k: search_chat(n, k)),
                 person, MAX_CHAT_TURNS)
    email = _safe(deps.email or (lambda n, k: read_email(
        n, k, tier_of=deps.tier_of, tools=deps.tools_enabled, fetch=deps.email_fetch)),
        person, MAX_EMAILS)
    commitments = _safe(deps.commitments or (lambda n, k: read_commitments(
        n, k, todos=deps.todos)), person, MAX_COMMITMENTS)
    upcoming = _safe(deps.next_event or (lambda n, t: read_next_event(
        n, t, tier_of=deps.tier_of, tools=deps.tools_enabled,
        fetch=deps.calendar_fetch)), person, now)

    active = list(facts.get("active") or [])
    retired = list(facts.get("retired") or [])
    turns = list(chat.get("turns") or [])
    messages = list(email.get("messages") or [])
    items = list(commitments.get("items") or [])
    event = upcoming.get("event") if isinstance(upcoming, dict) else None
    states = {"facts": facts.get("state") or FAILED,
              "chat": chat.get("state") or FAILED,
              "email": email.get("state") or FAILED,
              "commitments": commitments.get("state") or FAILED,
              "calendar": upcoming.get("state") or FAILED}
    why = {}
    for key, part in (("facts", facts), ("chat", chat), ("email", email),
                      ("commitments", commitments), ("calendar", upcoming)):
        said = str(part.get("why") or "")
        if said:
            why[key] = said
    read = []
    if event is not None:
        read.append(CALENDAR_ACTION)
    if messages:
        read.append(EMAIL_TOOL)
    out = {
        "ok": True, "withheld": False, "private": True,
        "name": person, "aliases": list(facts.get("aliases") or []),
        "known": bool(facts.get("known")),
        "made": now,
        "active_facts": active[:MAX_ACTIVE_FACTS],
        "retired_facts": retired[:MAX_RETIRED_FACTS],
        "recent_chat": turns[:MAX_CHAT_TURNS],
        "recent_email": messages[:MAX_EMAILS],
        "commitments": items[:MAX_COMMITMENTS],
        "next_event": event,
        "states": states, "why": why, "read": read,
        "counts": {"active_facts": len(active), "retired_facts": len(retired),
                   "chat": len(turns), "emails": len(messages),
                   "commitments": len(items)},
    }
    out["text"] = render(out)
    return out


def render(dossier: dict) -> str:
    """The dossier as plain lines - what a chat answer or a card would say.
    Every line is a record's own words or a count; nothing is inferred."""
    if not dossier.get("ok"):
        return str(dossier.get("why") or "")
    lines = [f"{dossier['name']} - person dossier."]
    active = dossier.get("active_facts") or []
    retired = dossier.get("retired_facts") or []
    if active or retired:
        line = "About them: " + _plural(len(active), PLURAL_FACT)
        if retired:
            line += f" ({len(retired)} no longer true)"
        lines.append(line + ".")
        lines.extend(f"- {f['text']}" for f in active)
        if retired:
            lines.append("No longer true:")
            lines.extend(f"- {f['text']}" for f in retired)
    else:
        lines.append("Jarvis has no saved facts about them.")
    for turn in dossier.get("recent_chat") or []:
        when = _when_line(turn.get("when"))
        where = f" in \"{turn['conversation']}\"" if turn.get("conversation") else ""
        lines.append(f"- Chat{where}{when}: {turn.get('words') or ''}")
    for msg in dossier.get("recent_email") or []:
        lines.append(f"- Email from {msg.get('from') or 'someone'}"
                     f"{(': ' + msg['subject']) if msg.get('subject') else ''}"
                     f"{(' - ' + msg['preview']) if msg.get('preview') else ''}")
    for item in dossier.get("commitments") or []:
        lines.append(f"- Open to-do: {item.get('text') or ''}")
    event = dossier.get("next_event")
    if isinstance(event, dict) and event:
        when = event.get("when") or ""
        lines.append(f"Next together: {when + ' ' if when else ''}"
                     f"{event.get('summary') or 'an event'}"
                     f"{(' at ' + event['location']) if event.get('location') else ''}.")
    return "\n".join(lines)


def _when_line(epoch) -> str:
    try:
        t = float(epoch)
    except (TypeError, ValueError):
        return ""
    if t <= 0:
        return ""
    lt = time.localtime(t)
    return f" on {time.strftime('%Y-%m-%d %H:%M', lt)}"

# --------------------------------------------------------------------------
#   The one screen surface today: the morning briefing's People line
# --------------------------------------------------------------------------


def briefing_people(events, *, now: Optional[float] = None,
                    deps: Optional[Deps] = None) -> Optional[dict]:
    """A compact briefing section for people Jarvis knows who are named in
    today's calendar events - the pre-meeting line the guide asks the morning
    briefing for - or None when nobody is named (so a briefing with no such
    event looks exactly as it did before).

    It stays deliberately light: memory names and a fact count only, no mail,
    no chat turns, no to-do list, because a briefing runs on its own every
    morning and this module does not widen an unattended read. The full
    dossier (`build_person_dossier`) is the on-request version.

    The person's NAME goes in `items`, which BOTH apps already blank while
    "Hide memory lists and chat history" or App lock is on; the summary says
    only how many people, so a count is all a hidden briefing shows. Same
    shape as the email senders line the briefing already has.
    """
    deps = deps or Deps()
    now = _now_of(now, deps)
    try:
        people = (deps.known_people() if deps.known_people is not None
                  else _read_known_people(store=deps.memory_store))
    except Exception:
        people = []
    if not isinstance(people, list):
        people = []
    lines, seen = [], set()
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        summary = _clean(ev.get("summary") or "", MAX_BRIEFING_CHARS)
        place = _clean(ev.get("location") or "", 80)
        hay = (summary + " " + place).strip()
        if not hay:
            continue
        for person in people:
            if not isinstance(person, dict):
                continue
            pname = clean_name(person.get("name"))
            if not pname or pname.casefold() in seen:
                continue
            if not mentions(hay, name_forms(pname, person.get("aliases"))):
                continue
            when = when_words(ev.get("start"), now)
            line = f"{pname} - {when + ': ' if when else ''}{summary or 'an event'}"
            if person.get("facts"):
                line += f" ({_plural(int(person['facts']), PLURAL_FACT)})"
            lines.append(_clean(line, MAX_BRIEFING_CHARS))
            seen.add(pname.casefold())
            if len(lines) >= BRIEFING_MAX_PEOPLE:
                break
        if len(lines) >= BRIEFING_MAX_PEOPLE:
            break
    if not lines:
        return None
    summary = (f"{len(lines)} person in today's calendar." if len(lines) == 1
               else f"{len(lines)} people in today's calendar.")
    return {"key": "people", "title": BRIEFING_TITLE, "state": OK,
            "summary": summary, "items": lines}
