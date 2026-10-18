"""test_people_crm.py - the personal CRM: one read-only person dossier, built
from this PC's own records (Pillar 16, 2026-10-17).

    python3 backend/test_people_crm.py

No pytest, no network, no model. Every read that would leave the PC is an
injected fixture here (the same technique jarvis_briefing.py's own suite uses),
and the two real stores this suite does open are a temporary SQLite memory
file and a temporary config folder - never the owner's.

What it proves:
  * THE PRIVACY INVARIANT FIRST: with `hide_memory_lists` or `app_locked` on,
    the dossier is withheld before ANY reader is called - {"ok": False,
    "withheld": True, ...} with no facts, chats, mail, to-dos or event in it -
    and the refused reason names the switch that did it.
  * the dossier is assembled from its five sources (memory facts split
    current/retired, kept chat turns, mail headers/snippets, open to-dos, the
    next event that names the person), each source failing on its own;
  * a fact whose valid_to is still in the FUTURE is current, and only a
    valid_to at or before `now` is retired - the rule every reader in
    jarvis_memory.py uses;
  * reading the facts latches the conversation taint (jarvis_gate.latch_taint)
    and a missing or broken gate never breaks the dossier;
  * the memory reader works against a REAL temporary MemoryStore: a person's
    current facts, a replaced fact kept as history (former employer/city), and
    the entity layer's own kind filter (a place is not a person);
  * every bounded list has its cap, and the mail/calendar readers make no
    connection at tier "ask" or when the tool is off;
  * the briefing's People line names only people Jarvis already knows, only
    today's events, at most four, with a COUNT-only summary - the apps blank
    its items while the private lists are hidden, so no name survives there.

Every check fails on the code before this change: jarvis_people_crm.py did not
exist, and jarvis_briefing.py had no People line.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-people-crm-"))
# Before anything imports jarvis_framework/jarvis_memory: their folders are
# read once. A HashEmbedder store and a temp memory file - no model, no owner.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "config" / "memory.db")
os.environ["JARVIS_NO_EMBED"] = "1"
os.environ["JARVIS_CALDAV_URL"] = "https://cal.example.com/dav/"
os.environ["JARVIS_IMAP_HOST"] = "imap.example.com"
os.environ.pop("JARVIS_CALENDAR_ICS_SECRET_URL", None)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_rebuilt, require_shipped  # noqa: E402

require_shipped("jarvis_people_crm.py", "jarvis_briefing.py")
require_rebuilt("jarvis_memory")

import jarvis_memory as M  # noqa: E402
import jarvis_people_crm as P  # noqa: E402
import jarvis_briefing as B  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class NoSockets:
    """Every way out of this process made to fail, and counted."""

    def __enter__(self):
        self.tried = []
        self.saved = (socket.socket.connect, urllib.request.urlopen,
                      socket.create_connection)

        def refuse(*a, **k):
            self.tried.append(a[:1])
            raise AssertionError("a socket was opened")
        socket.socket.connect = refuse
        urllib.request.urlopen = refuse
        socket.create_connection = refuse
        return self

    def __exit__(self, *exc):
        socket.socket.connect, urllib.request.urlopen, socket.create_connection = self.saved


# --------------------------------------------------------------------------
#   Fixtures - every source as its own record, so a check names one thing
# --------------------------------------------------------------------------


def fact(fid, text, *, valid_to=None, valid_from=1000.0, erased_at=None, forgotten=False):
    return {"id": fid, "text": text, "valid_from": valid_from, "valid_to": valid_to,
            "erased_at": erased_at, "forgotten": forgotten, "source": "typed"}


DEFAULT_FACTS = {
    "ok": True, "known": True, "aliases": ["Al"], "state": P.OK, "why": "",
    "active": [fact(2, "Works at Acme Ltd"), fact(1, "Lives in Leeds")],
    "retired": [fact(3, "Used to work at Beta Corp", valid_to=900.0)],
}
DEFAULT_CHAT = {"ok": True, "state": P.OK, "why": "", "partial": False,
                "turns": [{"conversation": "Weekend plans", "role": "user",
                           "when": 1700000000,
                           "words": "Lunch with Alex on Friday?"}]}
DEFAULT_EMAIL = {"ok": True, "state": P.OK, "why": "", "messages": [
    {"from": "Alex Smith <alex@example.com>", "subject": "Friday lunch",
     "date": "Fri, 17 Oct 2026", "preview": "See you at one."}]}
DEFAULT_COMMITMENTS = {"ok": True, "state": P.OK, "why": "",
                       "items": [{"text": "Send Alex the photos", "due": None, "list": None}]}
DEFAULT_EVENT = {"ok": True, "state": P.OK, "why": "", "event": {
    "summary": "Lunch with Alex", "location": "Cafe", "start": "20261018T140000Z",
    "end": "20261018T150000Z", "when": "14:00", "at": 1792322400.0, "recurring": False}}


class Recorder:
    """A Deps whose five reads answer fixtures and count their calls. An
    Exception value is raised by that read instead of returned."""

    def __init__(self, *, facts=None, chat=None, email=None, commitments=None,
                 next_event=None, known_people=None, taint=None, now=None,
                 tier_of=None, tools_enabled=None, store=None, todos=None,
                 email_fetch=None, calendar_fetch=None):
        self.calls = {}
        self.taints = []
        self.tiers = []

        def make(key, value, default):
            def fn(*a):
                self.calls[key] = self.calls.get(key, 0) + 1
                if isinstance(value, BaseException):
                    raise value
                return default if value is None else value
            return fn
        taint_fn = taint if taint is not None else (lambda why: self.taints.append(why) or True)
        if isinstance(taint_fn, BaseException):
            def taint_fn(why, _exc=taint_fn):
                self.taints.append(why)
                raise _exc
        self.taint_calls = taint_fn
        self.tier_calls = []

        def tier(action):
            self.tier_calls.append(action)
            if tier_of is not None:
                return tier_of(action)
            return "auto"
        tools = tools_enabled if tools_enabled is not None else (lambda: {"calendar_read",
                                                                           "email_check"})
        self.deps = P.Deps(
            facts=make("facts", facts, DEFAULT_FACTS),
            chat=make("chat", chat, DEFAULT_CHAT),
            email=make("email", email, DEFAULT_EMAIL),
            commitments=make("commitments", commitments, DEFAULT_COMMITMENTS),
            next_event=make("next_event", next_event, DEFAULT_EVENT),
            known_people=(None if known_people is None else make("known", known_people, [])),
            taint=self.taint_calls, tier_of=tier, tools_enabled=tools,
            email_fetch=email_fetch, calendar_fetch=calendar_fetch)

    def build(self, name="Alex Smith", **kw):
        return P.build_person_dossier(name, deps=self.deps, **kw)


def recorder(**kw) -> Recorder:
    return Recorder(**kw)


def mail(from_addr, subject, body=""):
    """One raw RFC 822 message, as jarvis_email's fetch would hand it back."""
    return (f"From: {from_addr}\r\nSubject: {subject}\r\n"
            f"Date: Fri, 17 Oct 2026 10:00:00 +0000\r\n\r\n{body}\r\n").encode("utf-8")


def utc(y, mo, d, hh, mm=0):
    import calendar as _cal
    from datetime import datetime
    return float(_cal.timegm(datetime(y, mo, d, hh, mm).timetuple()))


ICS = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
{blocks}
</D:multistatus>"""
BLOCK = """  <D:response><D:propstat><D:prop><C:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:{uid}
SUMMARY:{summary}
DTSTART{param}:{start}
{extra}END:VEVENT
END:VCALENDAR</C:calendar-data></D:prop></D:propstat></D:response>"""


def calendar_xml(*events):
    return ICS.format(blocks="\n".join(
        BLOCK.format(uid=f"e{i}", summary=e[0], param=e[1], start=e[2],
                     extra=e[3] if len(e) > 3 else "")
        for i, e in enumerate(events)))

# --------------------------------------------------------------------------
#   The privacy invariant, before anything else
# --------------------------------------------------------------------------


def t_hide_memory_lists_withholds_the_whole_dossier():
    r = recorder()
    out = r.build(hide_memory_lists=True)
    check("hide memory lists: the dossier is withheld",
          out["ok"] is False and out["withheld"] is True, repr(out)[:400])
    check("hide memory lists: the reason is the switch, in words",
          out["why"] == P.WITHHELD_HIDDEN and "Hide memory lists" in out["why"], out.get("why"))
    check("hide memory lists: NO reader was called at all",
          r.calls == {}, repr(r.calls))
    check("hide memory lists: no data key is in the answer",
          not any(k in out for k in ("active_facts", "retired_facts", "recent_chat",
                                     "recent_email", "commitments", "next_event")),
          sorted(out))
    check("hide memory lists: nothing is marked as read",
          out["read"] == [] and out["private"] is True, repr(out)[:200])


def t_app_lock_withholds_and_wins_over_hide():
    r = recorder()
    locked = r.build(app_locked=True)
    both = r.build(app_locked=True, hide_memory_lists=True)
    check("App lock: the dossier is withheld", locked["ok"] is False
          and locked["withheld"] is True, repr(locked)[:200])
    check("App lock: the reason is App lock", locked["why"] == P.WITHHELD_LOCKED,
          locked.get("why"))
    check("App lock and hide both on: App lock is the reason it says",
          both["why"] == P.WITHHELD_LOCKED, both.get("why"))
    check("App lock: no reader was called", r.calls == {}, repr(r.calls))


def t_privacy_is_enforced_before_the_name_is_even_read():
    out = P.build_person_dossier("", hide_memory_lists=True)
    check("an empty name with the lists hidden: withheld, not 'say a name'",
          out["withheld"] is True and out["why"] == P.WITHHELD_HIDDEN, repr(out)[:200])
    plain = P.build_person_dossier("", deps=recorder().deps)
    check("an empty name with the lists shown: plain refusal, not withheld",
          plain["ok"] is False and plain["withheld"] is False
          and plain["why"] == P.EMPTY_NAME, repr(plain)[:200])


def t_a_name_is_tidied_and_capped():
    r = recorder()
    out = r.build("  'Alex Smith'  ")
    check("the name is tidied: quotes and stray spacing off", out["name"] == "Alex Smith",
          repr(out.get("name")))
    out = r.build("A" * (P.MAX_NAME_CHARS + 20))
    check(f"the name is capped at {P.MAX_NAME_CHARS} characters",
          len(out["name"]) == P.MAX_NAME_CHARS, len(out.get("name") or ""))
    nothing = P.build_person_dossier(" ,;: ", deps=recorder().deps)
    check("punctuation alone is not a name", nothing["ok"] is False
          and nothing["why"] == P.EMPTY_NAME, repr(nothing)[:200])

# --------------------------------------------------------------------------
#   Assembly - the five sources, and each one failing on its own
# --------------------------------------------------------------------------


def t_the_dossier_holds_all_five_parts():
    out = recorder().build()
    check("a dossier for a known person is ok", out["ok"] is True
          and out["known"] is True and out["withheld"] is False, repr(out)[:200])
    check("the current facts are there", [f["text"] for f in out["active_facts"]]
          == ["Works at Acme Ltd", "Lives in Leeds"], out["active_facts"])
    check("the retired facts are separate", [f["text"] for f in out["retired_facts"]]
          == ["Used to work at Beta Corp"], out["retired_facts"])
    check("the kept chat turn is there", out["recent_chat"][0]["words"]
          == "Lunch with Alex on Friday?", out["recent_chat"])
    check("the mail header/snippet is there", out["recent_email"][0]["from"]
          == "Alex Smith <alex@example.com>" and "Friday lunch" in out["recent_email"][0]["subject"],
          out["recent_email"])
    check("the open to-do naming the person is there",
          out["commitments"][0]["text"] == "Send Alex the photos", out["commitments"])
    check("the next event together is there", out["next_event"]["summary"]
          == "Lunch with Alex" and out["next_event"]["when"] == "14:00", out["next_event"])
    check("the counts say how many of each",
          out["counts"] == {"active_facts": 2, "retired_facts": 1, "chat": 1,
                            "emails": 1, "commitments": 1}, out["counts"])
    check("the plain text holds the facts and the next event",
          "Works at Acme Ltd" in out["text"] and "No longer true" in out["text"]
          and "Next together: 14:00 Lunch with Alex" in out["text"], out["text"])


def t_each_source_fails_alone():
    r = recorder(chat=RuntimeError("the chat log is locked"))
    out = r.build()
    check("a source that raises does not break the dossier", out["ok"] is True)
    check("... its section is reported failed, and says so",
          out["states"]["chat"] == P.FAILED and "went wrong" in out["why"].get("chat", ""),
          (out["states"], out["why"]))
    check("... and the other sections are still there",
          out["active_facts"] and out["recent_email"] and out["next_event"], repr(out)[:200])


def t_a_source_state_is_passed_through_with_its_why():
    said = "Not read: the mail server did not answer."
    r = recorder(email={"ok": False, "state": P.FAILED, "why": said, "messages": []})
    out = r.build()
    check("a source's state and why reach the dossier",
          out["states"]["email"] == P.FAILED and out["why"]["email"] == said,
          (out["states"], out["why"]))
    check("... with no mail lines in it", out["recent_email"] == []
          and "email_check" not in out["read"], out["read"])


def t_the_read_list_names_only_sources_whose_text_is_shown():
    out = recorder().build()
    check("calendar and mail are named when their lines are in the dossier",
          out["read"] == [P.CALENDAR_ACTION, P.EMAIL_TOOL], out["read"])
    empty = recorder(email={"ok": True, "state": P.EMPTY, "why": "", "messages": []},
                     next_event={"ok": True, "state": P.EMPTY, "why": "", "event": None}).build()
    check("no outside line, no read claimed", empty["read"] == [], empty["read"])


def t_an_unknown_person_is_an_empty_dossier_not_an_error():
    r = recorder(facts={"ok": True, "known": False, "aliases": [], "state": P.EMPTY,
                        "why": "", "active": [], "retired": []},
                 chat={"ok": True, "state": P.EMPTY, "why": "", "turns": []},
                 email={"ok": True, "state": P.EMPTY, "why": "", "messages": []},
                 commitments={"ok": True, "state": P.EMPTY, "why": "", "items": []},
                 next_event={"ok": True, "state": P.EMPTY, "why": "", "event": None})
    out = r.build("Nobody At All")
    check("a person Jarvis knows nothing about: ok, not known",
          out["ok"] is True and out["known"] is False, repr(out)[:200])
    check("... and the dossier says plainly it has no facts",
          "no saved facts" in out["text"], out["text"])


def t_every_bounded_list_has_its_cap():
    many = {"ok": True, "known": True, "aliases": [], "state": P.OK, "why": "",
            "active": [fact(100 + i, f"active {i}") for i in range(20)],
            "retired": [fact(200 + i, f"retired {i}", valid_to=900.0) for i in range(20)]}
    out = recorder(facts=many,
                   chat={"ok": True, "state": P.OK, "why": "",
                         "turns": [{"conversation": "c", "role": "user", "when": 1,
                                    "words": f"turn {i}"} for i in range(10)]},
                   email={"ok": True, "state": P.OK, "why": "",
                          "messages": [{"from": "Alex", "subject": f"s{i}", "date": "",
                                        "preview": ""} for i in range(10)]},
                   commitments={"ok": True, "state": P.OK, "why": "",
                                "items": [{"text": f"todo {i}", "due": None, "list": None}
                                          for i in range(20)]}).build()
    check(f"at most {P.MAX_ACTIVE_FACTS} current facts are shown",
          len(out["active_facts"]) == P.MAX_ACTIVE_FACTS, len(out["active_facts"]))
    check(f"at most {P.MAX_RETIRED_FACTS} retired facts are shown",
          len(out["retired_facts"]) == P.MAX_RETIRED_FACTS, len(out["retired_facts"]))
    check(f"at most {P.MAX_CHAT_TURNS} chat turns are shown",
          len(out["recent_chat"]) == P.MAX_CHAT_TURNS, len(out["recent_chat"]))
    check(f"at most {P.MAX_EMAILS} mail lines are shown",
          len(out["recent_email"]) == P.MAX_EMAILS, len(out["recent_email"]))
    check(f"at most {P.MAX_COMMITMENTS} open to-dos are shown",
          len(out["commitments"]) == P.MAX_COMMITMENTS, len(out["commitments"]))
    check("the counts still say how many there were in all",
          out["counts"]["active_facts"] == 20 and out["counts"]["retired_facts"] == 20
          and out["counts"]["commitments"] == 20, out["counts"])

# --------------------------------------------------------------------------
#   The privacy latch (taint)
# --------------------------------------------------------------------------


def t_reading_the_facts_latches_the_conversation_private():
    r = recorder()
    out = r.build()
    check("reading a person's facts latches the taint, once, as people_crm",
          r.taints == [P.TAINT_WHY] and P.TAINT_WHY == "people_crm", r.taints)
    check("... and the dossier says it is private", out["private"] is True)
    hidden = recorder()
    hidden.build(hide_memory_lists=True)
    check("a withheld dossier reads nothing, so it latches nothing",
          hidden.taints == [], hidden.taints)
    broken = recorder(facts=RuntimeError("memory is unreadable"))
    check("a facts read that failed latches nothing",
          broken.build()["ok"] is True and broken.taints == [], broken.taints)


def t_a_broken_or_missing_gate_never_breaks_the_dossier():
    def explode(why):
        raise RuntimeError("no gate here")
    out = P.build_person_dossier("Alex Smith", deps=recorder(taint=explode).deps)
    check("a taint latch that raises is ignored", out["ok"] is True
          and out["active_facts"], repr(out)[:200])

# --------------------------------------------------------------------------
#   The pure rules: current vs retired, names, matching
# --------------------------------------------------------------------------


def t_current_vs_retired_follows_the_memory_modules_own_rule():
    now = 1000.0
    check("no valid_to: current", P.fact_is_current({"valid_to": None}, now) is True)
    check("a valid_to at `now`: retired", P.fact_is_current({"valid_to": now}, now) is False)
    check("a valid_to before `now`: retired",
          P.fact_is_current({"valid_to": now - 1}, now) is False)
    check("a valid_to in the FUTURE: still current (it has not happened yet)",
          P.fact_is_current({"valid_to": now + 1}, now) is True)
    check("a damaged valid_to does not hide the fact",
          P.fact_is_current({"valid_to": "not a date"}, now) is True)
    active, retired = P.split_facts([
        fact(1, "current one"),
        fact(2, "future-dated one", valid_to=now + 50),
        fact(3, "old one", valid_to=now - 50),
        fact(4, "erased one", erased_at=now),
        fact(5, "forgotten one", forgotten=True),
        fact(6, ""),
        "not a row",
    ], now)
    check("split: erased facts never come back",
          all(f["id"] != 4 for f in active + retired), active + retired)
    check("split: forgotten facts never come back",
          all(f["id"] != 5 for f in active + retired), active + retired)
    check("split: a fact with no words is not shown",
          all(f["text"] for f in active + retired), active + retired)
    check("split: current, future-dated and old land in the right lists",
          {f["id"] for f in active} == {1, 2} and {f["id"] for f in retired} == {3},
          (active, retired))
    check("split: each list is newest first",
          [f["id"] for f in retired] == [3], retired)


def t_name_forms_and_matching():
    forms = P.name_forms("Alex Smith")
    check("the full name is a form", "Alex Smith" in forms, forms)
    check("the longer words of a name are forms",
          "Smith" in forms and "Alex" in forms, forms)
    short = P.name_forms("Al Smith")
    check("a two-letter word is not a form on its own (it would match inside words)",
          "Al" not in short and "Smith" in short, short)
    with_alias = P.name_forms("Alex Smith", ["friend", "Alex Smith"])
    check("an alias is a form, once (case-insensitive)", with_alias.count("Alex Smith") == 1
          and "friend" in with_alias, with_alias)
    check("a name matches as a whole word, any case",
          P.mentions("Lunch with alex", ["Alex"]) is True
          and P.mentions("Alex's birthday", ["Alex"]) is True)
    check("a name does not match inside a longer word",
          P.mentions("Alexandra called", ["Alex"]) is False)
    check("no name form in text: no match", P.mentions("Dentist", ["Alex"]) is False)


def t_calendar_stamps_are_read_without_guessing_zones():
    stamp = "20261018T140000Z"
    check("a Z stamp is the UTC moment", P._stamp_epoch(stamp) == utc(2026, 10, 18, 14),
          P._stamp_epoch(stamp))
    check("a date-only stamp is that day", P._stamp_epoch("20261018")
          == P._stamp_epoch("20261018T000000"))
    check("a floating stamp is this PC's own time",
          P._stamp_epoch("20261018T140000")
          == float(time.mktime((2026, 10, 18, 14, 0, 0, 0, 0, -1))))
    check("an unreadable stamp is None", P._stamp_epoch("soon") is None)
    lt = time.localtime(utc(2026, 10, 18, 14))
    check("a Z stamp's label is this PC's clock time",
          P.when_words(stamp) == f"{lt.tm_hour:02d}:{lt.tm_min:02d}", P.when_words(stamp))
    check("an all-day event says 'All day'", P.when_words("20261018") == "All day")
    check("a stamp with no time says nothing", P.when_words("") == "")

# --------------------------------------------------------------------------
#   The real memory reader, against a real temporary MemoryStore
# --------------------------------------------------------------------------


def temp_store():
    d = Path(tempfile.mkdtemp(prefix="jarvis-people-crm-db-", dir=str(_TMP)))
    return M.MemoryStore(path=d / "memory.db", embedder=M.HashEmbedder())


def t_the_real_memory_reader_finds_current_and_former_facts():
    st = temp_store()
    first = st.add("My friend Alex Smith works at Acme Ltd")
    leeds = st.add("Alex Smith lives in Leeds")
    york = st.add("Alex Smith lives in York", supersedes=leeds)
    now = time.time() + 10
    got = P.person_facts("Alex Smith", now, store=st)
    texts = [f["text"] for f in got["active"]]
    check("the real store: a known person is found through the entity layer",
          got["ok"] is True and got["known"] is True, repr(got)[:300])
    check("the real store: the current facts are current",
          any("Acme Ltd" in t for t in texts) and any("York" in t for t in texts), texts)
    check("the real store: the replaced fact is RETIRED, never shown as current",
          any("Leeds" in f["text"] for f in got["retired"])
          and not any("Leeds" in t for t in texts),
          (got["active"], got["retired"]))
    check("the real store: the entity layer's own alias comes along",
          "friend" in got["aliases"], got["aliases"])
    none = P.person_facts("Nobody At All", now, store=st)
    check("the real store: a name it has never seen is not known, and does not fail",
          none["ok"] is True and none["known"] is False, repr(none)[:300])
    check("the real store: only the person counts as a person, not the places",
          [p["name"] for p in P._read_known_people(store=st)] == ["Alex Smith"],
          P._read_known_people(store=st))


class FakeStore:
    """The smallest store jarvis_people_crm's fallback path reads: no entity
    has linked the name yet, but a fact's own words mention them."""

    def entities_view(self, **kw):
        return {"entities": []}

    def current_facts(self, limit=400, topics="use"):
        return [{"id": 7, "text": "my friend Alex Smith called about the roof",
                 "created": 500.0, "valid_from": 500.0, "valid_to": None,
                 "source": "typed", "meta": None, "erased_at": None, "retired_at": None,
                 "retired_by": None}]

    def fact_history(self, fact_id, limit=None):
        return [dict(self.current_facts()[0])]


def t_the_real_memory_reader_falls_back_to_the_facts_own_words():
    got = P.person_facts("alex smith", 1000.0, store=FakeStore())
    check("with no entity linked, a fact that names the person is found",
          got["known"] is True and got["active"] and "roof" in got["active"][0]["text"],
          repr(got)[:300])

# --------------------------------------------------------------------------
#   The other readers, with the network made an injected fixture
# --------------------------------------------------------------------------


def t_the_chat_reader_uses_the_history_search():
    def search(query, limit=20, kind=None):
        assert query == "Alex Smith"
        return {"query_ok": True, "enabled": True, "partial": False,
                "conversations": [
                    {"title": "Tickets", "updated": 11, "snippet": {
                        "role": "user", "at": 10,
                        "parts": [{"text": "Alex said ", "hit": False},
                                  {"text": "Alex Smith", "hit": True},
                                  {"text": " will call", "hit": False}]}}]}
    with NoSockets():
        got = P.search_chat("Alex Smith", 3, search=search)
    check("the chat reader asks the History search and keeps the turn",
          got["ok"] is True and got["turns"][0]["words"] == "Alex said Alex Smith will call",
          repr(got)[:300])
    check("the chat reader carries the conversation, role and when",
          got["turns"][0]["conversation"] == "Tickets" and got["turns"][0]["role"] == "user"
          and got["turns"][0]["when"] == 10, got["turns"][0])
    empty = P.search_chat("Alex Smith", 3, search=lambda q, limit=20: {
        "query_ok": True, "enabled": True, "conversations": []})
    check("no kept chat mentions them: empty, not a failure",
          empty["ok"] is True and empty["state"] == P.EMPTY and empty["turns"] == [], empty)
    off = P.search_chat("Alex Smith", 3, search=lambda q, limit=20: {
        "query_ok": True, "enabled": False, "conversations": []})
    check("chat history off and nothing kept: the state says off",
          off["state"] == P.OFF and "chat history is off" in off["why"], off)
    failed = P.search_chat("Alex Smith", 3, search=lambda *a, **k: 1 / 0)
    check("a search that breaks is reported failed, and said",
          failed["ok"] is False and failed["state"] == P.FAILED, failed)
    could_not = P.search_chat("Alex Smith", 3,
                              search=lambda *a, **k: {"query_ok": False, "why": "too short"})
    check("a search that says it could not search is reported failed",
          could_not["ok"] is False and could_not["state"] == P.FAILED, could_not)


def t_the_mail_reader_reads_nothing_unless_it_may():
    with NoSockets():
        asks = P.read_email("Alex Smith", 3, tier_of=lambda a: "ask", tools=lambda: {"email_check"},
                            fetch=lambda p: (_ for _ in ()).throw(AssertionError("dialled")))
        off = P.read_email("Alex Smith", 3, tier_of=lambda a: "auto", tools=lambda: set(),
                           fetch=lambda p: (_ for _ in ()).throw(AssertionError("dialled")))
    check("mail at tier ask: nothing read, and it says why",
          asks["ok"] is False and asks["state"] == P.ASKS and "ask for a yes" in asks["why"], asks)
    check("the mail tool switched off: nothing read", off["state"] == P.OFF, off)
    raw = [mail("Alex Smith <alex@example.com>", "Friday lunch", "See you at one"),
           mail('"Your Bank" <alerts@bank.example>', "Statement", "Your statement is ready"),
           mail("Alex Smith <alex@example.com>", "Photos", "Here they are")]
    with NoSockets():
        got = P.read_email("Alex Smith", 3, tier_of=lambda a: "auto",
                           tools=lambda: {"email_check"}, fetch=lambda p: raw)
    check("mail: only the messages that name the person are kept",
          [m["subject"] for m in got["messages"]] == ["Friday lunch", "Photos"],
          got["messages"])
    check("mail: the header and the bounded snippet come through, and it is ok",
          got["ok"] is True and got["messages"][0]["from"].startswith("Alex Smith")
          and "See you at one" in got["messages"][0]["preview"], got["messages"][0])
    none = P.read_email("Alex Smith", 3, tier_of=lambda a: "auto", tools=lambda: {"email_check"},
                        fetch=lambda p: [raw[1]])
    check("mail that names nobody: empty, not a failure",
          none["ok"] is True and none["state"] == P.EMPTY, none)
    broken = P.read_email("Alex Smith", 3, tier_of=lambda a: "auto",
                          tools=lambda: {"email_check"}, fetch=lambda p: 1 / 0)
    check("a mail server that breaks is reported failed, never quoted",
          broken["ok"] is False and broken["state"] == P.FAILED
          and "ZeroDivisionError" not in json.dumps(broken), broken)


def t_the_calendar_reader_finds_the_next_event_together():
    now = utc(2026, 10, 17, 19)
    xml = calendar_xml(
        ("Lunch with Alex", "", "20261018T140000Z"),      # tomorrow: the next
        ("Dinner with Alex", "", "20261017T200000Z"),     # later today: sooner
        ("Breakfast with Alex", "", "20261017T080000Z"),  # past: not "next"
        ("Dentist", "", "20261017T170000Z"),             # not the person
    )
    with NoSockets():
        got = P.read_next_event("Alex Smith", now, tier_of=lambda a: "auto",
                                tools=lambda: {"calendar_read"}, fetch=lambda q: xml)
    check("the next event together is the soonest one that names the person, "
          "skipping the past", got["ok"] is True and got["event"]["summary"]
          == "Dinner with Alex", got)
    check("... carrying its time label by this PC's clock",
          got["event"]["when"] == P.when_words("20261017T200000Z")
          and got["event"]["when"] == time.strftime("%H:%M", time.localtime(utc(2026, 10, 17, 20))),
          got["event"]["when"])
    asks = P.read_next_event("Alex Smith", now, tier_of=lambda a: "ask",
                             tools=lambda: {"calendar_read"},
                             fetch=lambda q: (_ for _ in ()).throw(AssertionError("dialled")))
    check("calendar at tier ask: nothing read, and it says why",
          asks["ok"] is False and asks["state"] == P.ASKS, asks)
    off = P.read_next_event("Alex Smith", now, tier_of=lambda a: "auto", tools=lambda: set(),
                            fetch=lambda q: (_ for _ in ()).throw(AssertionError("dialled")))
    check("the calendar tool switched off: nothing read", off["state"] == P.OFF, off)
    empty = P.read_next_event("Alex Smith", now, tier_of=lambda a: "auto",
                              tools=lambda: {"calendar_read"},
                              fetch=lambda q: calendar_xml(("Dentist", "", "20261018T140000Z")))
    check("no event names them: no event together, not a failure",
          empty["ok"] is True and empty["state"] == P.EMPTY and empty["event"] is None, empty)
    broken = P.read_next_event("Alex Smith", now, tier_of=lambda a: "auto",
                               tools=lambda: {"calendar_read"}, fetch=lambda q: 1 / 0)
    check("a calendar that breaks is reported failed", broken["ok"] is False
          and broken["state"] == P.FAILED, broken)


def t_the_commitments_reader_lists_open_todos_that_name_the_person():
    todos = [{"text": "Send Alex the photos", "due": None, "list": None},
             {"text": "Buy milk", "due": None, "list": None},
             {"text": "Call Alex Smith about the roof", "due": 500.0, "list": None}]
    got = P.read_commitments("Alex Smith", 8, todos=lambda: todos)
    check("only the open to-dos that name the person are commitments",
          [i["text"] for i in got["items"]] == ["Send Alex the photos",
                                                "Call Alex Smith about the roof"],
          got["items"])
    check("a to-do keeps its due time", got["items"][1]["due"] == 500.0, got["items"])
    none = P.read_commitments("Alex Smith", 8, todos=lambda: [])
    check("no open to-do names them: empty", none["ok"] is True
          and none["state"] == P.EMPTY, none)
    broken = P.read_commitments("Alex Smith", 8, todos=lambda: 1 / 0)
    check("a scheduler that breaks is reported failed", broken["ok"] is False
          and broken["state"] == P.FAILED, broken)

# --------------------------------------------------------------------------
#   The briefing's People line (Pillar 16's one screen surface today)
# --------------------------------------------------------------------------


def known(*names):
    return [{"name": n, "aliases": [], "facts": 3} for n in names]


def t_the_briefing_line_names_known_people_in_todays_events():
    events = [{"summary": "Lunch with Alex Smith", "start": "20261018T140000Z",
               "location": ""},
              {"summary": "Dentist", "start": "20261018T090000Z", "location": ""}]
    now = utc(2026, 10, 18, 7)
    sec = P.briefing_people(events, now=now,
                            deps=P.Deps(known_people=lambda: known("Alex Smith")))
    check("a known person named in an event gets a briefing line",
          sec is not None and sec["key"] == "people" and sec["title"] == P.BRIEFING_TITLE,
          repr(sec)[:300])
    check("the line carries the name, the time and the fact count",
          "Alex Smith" in sec["items"][0] and "Lunch with Alex Smith" in sec["items"][0]
          and "3 saved facts" in sec["items"][0], sec["items"])
    check("the summary is a count only - no name reaches it",
          sec["summary"] == "1 person in today's calendar." and "Alex" not in sec["summary"],
          sec["summary"])
    none = P.briefing_people([{"summary": "Dentist", "start": "20261018T090000Z"}],
                             now=now, deps=P.Deps(known_people=lambda: known("Alex Smith")))
    check("no event names a known person: no section at all", none is None, none)
    unknown = P.briefing_people([{"summary": "Lunch with Someone New",
                                  "start": "20261018T140000Z"}], now=now,
                                deps=P.Deps(known_people=lambda: known("Alex Smith")))
    check("a name Jarvis does not know is never claimed", unknown is None, unknown)


def t_the_briefing_line_is_bounded_and_counts_people():
    events = [{"summary": f"Meeting with Person{i}", "start": "20261018T090000Z"}
              for i in range(8)]
    people = known(*[f"Person{i}" for i in range(8)])
    sec = P.briefing_people(events, now=utc(2026, 10, 18, 7),
                            deps=P.Deps(known_people=lambda: people))
    check(f"at most {P.BRIEFING_MAX_PEOPLE} people are named",
          len(sec["items"]) == P.BRIEFING_MAX_PEOPLE, sec["items"])
    check("the summary counts the people it named, in the plural",
          sec["summary"] == f"{P.BRIEFING_MAX_PEOPLE} people in today's calendar.", sec["summary"])
    one = P.briefing_people(events[:1], now=utc(2026, 10, 18, 7),
                            deps=P.Deps(known_people=lambda: people[:1]))
    check("one person reads as one, not '1 people'", "1 person in" in one["summary"], one["summary"])
    broken = P.briefing_people(events, now=utc(2026, 10, 18, 7),
                               deps=P.Deps(known_people=lambda: 1 / 0))
    check("a memory read that breaks leaves the briefing line out",
          broken is None, broken)


def t_the_briefing_line_matches_an_alias_and_a_place():
    people = [{"name": "Sarah Jones", "aliases": ["sister"], "facts": 2}]
    event = {"summary": "Dinner with my sister", "start": "20261018T190000Z",
             "location": ""}
    sec = P.briefing_people([event], now=utc(2026, 10, 18, 7),
                            deps=P.Deps(known_people=lambda: people))
    check("an alias the owner uses about the person matches an event",
          sec is not None and "Sarah Jones" in sec["items"][0], repr(sec)[:300])
    placed = [{"name": "Alex Smith", "aliases": [], "facts": 1}]
    event = {"summary": "Workshop", "start": "20261018T090000Z",
             "location": "Alex Smith's office"}
    sec = P.briefing_people([event], now=utc(2026, 10, 18, 7),
                            deps=P.Deps(known_people=lambda: placed))
    check("a name in the event's place counts too",
          sec is not None and "Alex Smith" in sec["items"][0], repr(sec)[:300])


def t_the_briefings_people_line_is_todays_only():
    events = [{"summary": "Lunch with Alex Smith", "start": "20261019T140000Z"},
              {"summary": "Dinner with Alex Smith", "start": "20261018T190000Z"}]
    now = utc(2026, 10, 18, 7)
    kept = B._people_events(events, now)
    check("the People line only sees today's events, not tomorrow's",
          [e["summary"] for e in kept] == ["Dinner with Alex Smith"], kept)
    unreadable = B._people_events([{"summary": "Lunch with Alex", "start": "soon"}], now)
    check("an event whose time cannot be read is never given a name", unreadable == [], unreadable)

# --------------------------------------------------------------------------


def main() -> int:
    for fn in (
            t_hide_memory_lists_withholds_the_whole_dossier,
            t_app_lock_withholds_and_wins_over_hide,
            t_privacy_is_enforced_before_the_name_is_even_read,
            t_a_name_is_tidied_and_capped,
            t_the_dossier_holds_all_five_parts,
            t_each_source_fails_alone,
            t_a_source_state_is_passed_through_with_its_why,
            t_the_read_list_names_only_sources_whose_text_is_shown,
            t_an_unknown_person_is_an_empty_dossier_not_an_error,
            t_every_bounded_list_has_its_cap,
            t_reading_the_facts_latches_the_conversation_private,
            t_a_broken_or_missing_gate_never_breaks_the_dossier,
            t_current_vs_retired_follows_the_memory_modules_own_rule,
            t_name_forms_and_matching,
            t_calendar_stamps_are_read_without_guessing_zones,
            t_the_real_memory_reader_finds_current_and_former_facts,
            t_the_real_memory_reader_falls_back_to_the_facts_own_words,
            t_the_chat_reader_uses_the_history_search,
            t_the_mail_reader_reads_nothing_unless_it_may,
            t_the_calendar_reader_finds_the_next_event_together,
            t_the_commitments_reader_lists_open_todos_that_name_the_person,
            t_the_briefing_line_names_known_people_in_todays_events,
            t_the_briefing_line_is_bounded_and_counts_people,
            t_the_briefing_line_matches_an_alias_and_a_place,
            t_the_briefings_people_line_is_todays_only,
    ):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            traceback.print_exc()
            FAILED.append(fn.__name__)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed"
          + (f", {len(SKIPPED)} skipped" if SKIPPED else ""))
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
