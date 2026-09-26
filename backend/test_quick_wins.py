"""test_quick_wins.py - snooze, "cancel that", named lists and "what did I
miss?" (the creativity audit's everyday quick wins, 2026-09-25;
docs/CREATIVITY-AUDIT-2026-09-25.md items 6 and 7; JARVIS-API sections 21.9
and 22.9).

    python3 backend/test_quick_wins.py

What it proves, with a clock the test moves by hand and real SQLite files in
a temporary folder, and every socket made to fail:
  - SNOOZE: only a timer, alarm or reminder that WENT OFF can be snoozed; it
    makes a one-off copy (no card); a repeating job's own next time does not
    move; snoozing twice while the copy waits changes nothing; the copy goes
    off; "Just went off" lists the last hour and leaves out one already
    snoozed; the events carry ids and kinds only; the limits say why;
  - the fast path: "snooze", "snooze 5 minutes", "snooze the alarm",
    "remind me again in 5 minutes" - and near-misses go to the model;
  - "CANCEL THAT": takes back only the last thing the fast path set, in this
    conversation, within two minutes, once; never another conversation's,
    never after the model answered in between, never one it found already
    there; a repeat withdrawn while its card waits; a snooze taken back frees
    its original; "never mind" with nothing to take back goes to the model;
  - NAMED LISTS: add (several items with commas), read, tick off, remove,
    which lists; the same words twice on one list are one item; a list's
    name is one to three plain words; clearing a named list only with the
    count the app showed, never the to-do list, and never by voice; a
    schedule.db from before the change opens and gains the columns;
  - "WHAT DID I MISS?": since the owner's previous message (touch), what went
    off, cards waiting (and how many came up since), unread email under the
    same gate and settings as the briefing (and says email was read when it
    names senders), what is next; never further back than a day; after a
    restart "the last 12 hours", said so; answered without the model and
    marked private; POST /api/briefing/now {"missed": true} answers it and
    keeps nothing as the latest briefing.

Every check fails on the code before this change: none of it existed. No
pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-quick-wins-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_schedule.py", "jarvis_quick.py", "jarvis_briefing.py", "jarvis_email.py")

if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_schedule as S  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_briefing as B  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


class World:
    def __init__(self, t, *, name="w", answer="approved", spawn_now=True):
        self.clock = Clock(t)
        self.events, self.cards = [], []
        self.answer = answer
        path = _TMP / f"{name}-{len(os.listdir(_TMP))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate, tier_of=lambda a: "ask",
                             spawn=(lambda fn: fn()) if spawn_now else (lambda fn: None),
                             publish=lambda k, d: self.events.append((k, d)))

    def gate(self, action, detail, prompt):
        self.cards.append(action)
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)


_AUDIT = []
_real_audit = S._audit
S._audit = lambda event, detail: _AUDIT.append((event, detail))


def use_tz(name):
    if not hasattr(time, "tzset"):
        return False
    os.environ["TZ"] = name
    time.tzset()
    return True


def local(y, mo, d, hh, mm):
    return S.wall_to_epoch(y, mo, d, hh, mm)


def wall(t):
    lt = time.localtime(t)
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min)


class NoSockets:
    def __enter__(self):
        self.tried = []
        self.saved = (socket.socket.connect, urllib.request.urlopen, socket.create_connection)

        def refuse(*a, **k):
            self.tried.append(a[:1])
            raise AssertionError("a socket was opened")
        socket.socket.connect = refuse
        urllib.request.urlopen = refuse
        socket.create_connection = refuse
        return self

    def __exit__(self, *exc):
        socket.socket.connect, urllib.request.urlopen, socket.create_connection = self.saved


NOON = None


def say(w, text, conversation="conversation-1", seen=None):
    return Q.answer(text, sched=w.s, now=w.clock.t, conversation=conversation, seen=seen)

# --------------------------------------------------------------------------
#   Snooze
# --------------------------------------------------------------------------


def t_snooze_is_a_one_off_copy_of_what_went_off():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="snooze")
    a = w.s.add_at("alarm", now + 600, "get up")
    code, out = w.s.act(a["id"], "snooze")
    check("something that has not gone off cannot be snoozed (409, said)",
          code == 409 and "not gone off" in out["error"], out)
    w.clock.t = now + 600
    w.s.tick()
    went = w.s.went_off()
    check("it is listed under 'just went off', with when", [j["id"] for j in went] == [a["id"]]
          and went[0]["went_off_at"] == "12:10", went)
    code, out = w.s.act(a["id"], "snooze")
    copy = out.get("job") or {}
    check("snooze: 200, ten minutes when not said, in plain words",
          code == 200 and out["said"] == "Snoozed for 10 minutes - until 12:20.", out)
    check("... a NEW one-off job with the same words, marked snoozed",
          copy.get("id") != a["id"] and copy.get("kind") == "alarm" and copy.get("text") == "get up"
          and copy.get("snoozed") is True and copy.get("repeats") is False
          and abs(copy["due"] - (now + 1200)) < 1, copy)
    check("... and no card", w.cards == [])
    check("... and it leaves 'just went off' (its copy is on the list)", w.s.went_off() == [])
    code, out2 = w.s.act(a["id"], "snooze", 300)
    check("snoozing it again while the copy waits changes nothing, and says until when",
          code == 200 and out2.get("already") is True and out2["said"] == "Already snoozed until 12:20."
          and len([j for j in w.s.listed() if j["kind"] == "alarm"]) == 1, out2)
    w.clock.t = now + 1200
    check("the copy goes off at 12:20", w.s.tick() == [copy["id"]])
    code, out3 = w.s.act(copy["id"], "snooze", 300)
    check("... and can be snoozed in turn", code == 200 and "12:25" in out3["said"], out3)
    blob = json.dumps(w.events) + json.dumps(_AUDIT)
    check("no event and no audit line carries the words", "get up" not in blob)
    check("the events are ids, kinds and states only",
          all(set(d) <= {"id", "kind", "state", "late"} for _, d in w.events), w.events[-3:])
    for secs, why in ((0, "no length"), (59, "under a minute"), (86401, "over a day")):
        code, out = w.s.act(copy["id"], "snooze", secs)
        check(f"a snooze of {why} is refused with a sentence", code == 400 and out.get("error"))
    d = w.s.add_todo("buy milk")
    check("a to-do cannot be snoozed", w.s.act(d["id"], "snooze")[0] == 409)


def t_snoozing_a_repeat_moves_only_that_one_time():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 6, 0)       # Friday
    w = World(now, name="repeat")
    j = w.s.add_repeat("reminder", {"every": "weekday", "at": "07:00"}, "take my pills")
    w.clock.t = local(2026, 9, 25, 7, 0)
    w.s.tick()
    before = w.s.job(j["id"])
    code, out = w.s.act(j["id"], "snooze", 900)
    after = w.s.job(j["id"])
    check("a repeating reminder that went off can be snoozed", code == 200, out)
    check("... its own next time is still Monday 07:00 (the rule untouched)",
          wall(after["due"]) == (2026, 9, 28, 7, 0) and after["rule"] == before["rule"]
          and after["state"] == "active", after)
    check("... the copy is a one-off at 07:15", out["job"]["repeats"] is False
          and wall(out["job"]["due"]) == (2026, 9, 25, 7, 15))
    check("... and no card at all: a plain repeat needs none (2026-09-26)", w.cards == [])
    w.clock.t = local(2026, 9, 28, 7, 0)
    w.s.tick()
    check("when the repeat goes off again, it can be snoozed afresh",
          w.s.act(j["id"], "snooze")[0] == 200 and w.s.act(j["id"], "snooze")[1].get("already"))


def t_snooze_by_voice_or_typing():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    for text, secs, kind in (("snooze", None, None), ("Snooze 5 minutes", 300, None),
                             ("snooze for 20 minutes", 1200, None), ("snooze the alarm", None, "alarm"),
                             ("snooze it for another 5 minutes", 300, None),
                             ("remind me again in 10 minutes", 600, None),
                             ("Jarvis, snooze please", None, None)):
        got = Q.match(text, now)
        check(f"ours: {text!r}", got is not None and got.name == "snooze"
              and got.f.get("seconds") == secs and got.f.get("kind") == kind, got and got.f)
    for text in ("snooze button", "what is snooze", "how do i snooze my alarm", "snooze 10"):
        check(f"to the model: {text!r}", Q.match(text, now) is None)
    w = World(now, name="saysnooze")
    r = say(w, "snooze")
    check("nothing went off: said, nothing made",
          r.reply == "Nothing went off in the last hour, so there is nothing to snooze."
          and w.s.listed() == [], r.reply)
    say(w, "set a pasta timer for 1 minute")
    w.clock.t = now + 60
    w.s.tick()
    r = say(w, "snooze 5 minutes")
    check("snooze: the timer that just went off, for 5 minutes",
          r.reply == "Snoozed the pasta timer for 5 minutes - until 12:06.", r.reply)
    r = say(w, "snooze")
    check("again: says it is already snoozed, changes nothing",
          "already snoozed until 12:06" in r.reply and len(w.s.timers()) == 1, r.reply)
    w.clock.t = now + 60 + 4000
    check("more than an hour later, 'snooze' finds nothing to snooze",
          "nothing to snooze" in say(w, "snooze").reply)

# --------------------------------------------------------------------------
#   "Cancel that"
# --------------------------------------------------------------------------


def t_cancel_that_takes_back_only_the_last_thing_set_here():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="undo")
    say(w, "set a timer for 10 minutes")
    r = say(w, "cancel that")
    check("'cancel that' right after: the timer is gone, and it says which",
          r.reply == "Cancelled: the 10 minute timer." and w.s.timers() == [], r and r.reply)
    check("... once: a second 'cancel that' is not ours (the model answers)",
          say(w, "cancel that") is None)
    r = say(w, "remind me at 6pm to call Mum")
    r = say(w, "cancel that", conversation="conversation-2")
    check("another conversation cannot take it back", r is None
          and len([j for j in w.s.listed() if j["kind"] == "reminder"]) == 1)
    w.clock.t = now + S.UNDO_WINDOW + 1
    r = say(w, "cancel that")
    check("more than two minutes later: said, nothing cancelled",
          r.reply.startswith("That was more than 2 minutes ago, so nothing was cancelled")
          and len(w.s.listed()) == 1, r.reply)
    check("... and 'never mind' then is not ours", say(w, "never mind") is None)
    w.clock.t = now + 600
    say(w, "set an alarm for 7am")
    r = say(w, "delete that reminder")
    check("'delete that reminder' after setting an alarm: said, nothing cancelled",
          r.reply == "The last thing set here was an alarm, not a reminder, so nothing was cancelled."
          and any(j["kind"] == "alarm" for j in w.s.listed()), r.reply)
    r = say(w, "no, cancel that alarm")
    check("'no, cancel that alarm' takes it back",
          r.reply == "Cancelled: the alarm for 07:00 tomorrow."
          and not any(j["kind"] == "alarm" for j in w.s.listed()), r.reply)
    say(w, "add stamps to my to-do list")
    say(w, "what's on my to-do list")
    check("anything else said in between: 'cancel that' no longer means the item",
          say(w, "cancel that") is None and len(w.s.todos()) == 1)
    r = say(w, "add stamps to my to-do list")
    check("an item that was already there is not 'set' now: nothing to take back",
          r.reply == "That is already on your to-do list." and say(w, "undo") is None
          and len(w.s.todos()) == 1)


def t_cancel_that_through_the_chat_request():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="undoturn")

    def turn(text, cid="abcdefgh-1", prov="typed"):
        body = {"messages": [{"role": "user", "content": text, "provenance": prov}],
                "conversation_id": cid}
        return Q.answer_turn(body, sched=w.s, now=w.clock.t)
    turn("set a timer for 5 minutes")
    check("the model answering in between: 'cancel that' is about ITS answer, not the timer",
          turn("what's the capital of Peru") is None and turn("cancel that") is None
          and len(w.s.timers()) == 1)
    turn("set a timer for 6 minutes")
    check("a pasted message in between counts the same", turn("x", prov="pasted") is None
          and turn("cancel that") is None and len(w.s.timers()) == 2)
    turn("set a timer for 7 minutes", cid="bad id!")
    check("no valid conversation id: nothing to take back", turn("cancel that", cid="bad id!") is None
          and len(w.s.timers()) == 3)
    turn("set a timer for 8 minutes")
    r = turn("never mind")
    check("'never mind' right after, same conversation: the timer is gone",
          r is not None and r.reply == "Cancelled: the 8 minute timer." and len(w.s.timers()) == 3,
          r and r.reply)


def t_cancel_that_for_a_repeat_a_list_and_a_snooze():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="undokinds", spawn_now=False)      # the card stays up
    say(w, "remind me every weekday at 7 to take my pills")
    r = say(w, "cancel that")
    check("a repeat (set up at once, no card since 2026-09-26): cancelled, off the list",
          r.reply == "Cancelled: the repeating reminder (every weekday (Monday to Friday) at 07:00)."
          and w.s.listed() == [], r.reply)
    say(w, "add milk, eggs and bread to the shopping list")
    r = say(w, "cancel that")
    check("three items added in one go: all three taken back",
          r.reply == "Removed the 3 items just added to your shopping list." and w.s.todos() == [],
          r.reply)
    say(w, "set an alarm for 12:05")
    w.clock.t = now + 300
    w.s.tick()
    say(w, "snooze")
    r = say(w, "cancel that")
    check("a snooze taken back: the copy is gone and the alarm is back under 'just went off'",
          r.reply == "Cancelled: the snooze." and [j["kind"] for j in w.s.went_off()] == ["alarm"]
          and w.s.listed() == [], r.reply)

# --------------------------------------------------------------------------
#   Named lists
# --------------------------------------------------------------------------


def t_list_names():
    check("'Shopping list' is kept as 'shopping'", S.list_key("Shopping list") == "shopping")
    check("the to-do list has no name", all(S.list_key(n) is None for n in
                                            (None, "", "to-do", "todo", "To do", "todo list")))
    for bad in ("all", "my list", "a b c d", "shop;ping", "x" * 31, "the"):
        try:
            S.list_key(bad)
            ok = False
        except ValueError as exc:
            ok = bool(str(exc))
        check(f"not a list's name, said why: {bad!r}", ok)
    check("titles", S.list_title("shopping") == "Shopping list" and S.list_title(None) == "To-do list")


def t_named_lists_by_voice_or_typing():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    OURS = {
        "add milk to the shopping list": ("todo_add", {"list": "shopping", "items": ["milk"]}),
        "Add Milk, eggs and bread to my shopping list": ("todo_add", {"list": "shopping",
                                                                      "items": ["Milk", "eggs", "bread"]}),
        "add mac and cheese to our shopping list": ("todo_add", {"items": ["mac and cheese"]}),
        "put Dune on my reading list": ("todo_add", {"list": "reading", "items": ["Dune"]}),
        "what's on my shopping list": ("todo_list", {"list": "shopping"}),
        "read me the shopping list": ("todo_list", {"list": "shopping"}),
        "my shopping list": ("todo_list", {"list": "shopping"}),
        "cross milk off the shopping list": ("todo_done", {"text": "milk", "list": "shopping"}),
        "tick off milk on my shopping list": ("todo_done", {"text": "milk", "list": "shopping"}),
        "remove eggs from the shopping list": ("todo_remove", {"text": "eggs", "list": "shopping"}),
        "clear the shopping list": ("list_clear", {"list": "shopping"}),
        "delete everything from the shopping list": ("list_clear", {"list": "shopping"}),
        "clear my to-do list": ("bulk", {}),
        "what lists do I have": ("lists_which", {}),
    }
    for text, (name, fields) in OURS.items():
        got = Q.match(text, now)
        ok = got is not None and got.name == name and all(got.f.get(k) == v for k, v in fields.items())
        check(f"ours: {text!r} -> {name}", ok, got and (got.name, got.f))
    for text in ("add salt to the pasta recipe", "what's on the list", "add it to my shopping list",
                 "add this to the list", "what should I add to my shopping list",
                 "add 5 minutes to the timer list please do", "make a shopping list for a party",
                 "put the kettle on"):
        got = Q.match(text, now)
        check(f"to the model: {text!r}", got is None or got.name not in (
            "todo_add", "todo_list", "list_clear"), got and (got.name, got.f))


def t_named_lists_act_and_answer():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="lists")
    r = say(w, "add milk, eggs and bread to the shopping list")
    check("three items, one answer", r.reply == "Added 3 items to your shopping list.", r.reply)
    r = say(w, "add Milk to the shopping list")
    check("the same words twice on one list are one item",
          r.reply == "That is already on your shopping list.", r.reply)
    say(w, "add milk to my to-do list")
    check("... but the same words on another list are another item",
          len([t for t in w.s.todos() if t["text"].lower() == "milk"]) == 2)
    r = say(w, "what's on my shopping list")
    check("read out, private", r.reply == "Your shopping list: milk, eggs and bread." and r.private,
          r.reply)
    r = say(w, "what's on my to-do list")
    check("the to-do list reads its own items, and names the other lists",
          r.reply == "One thing on your to-do list: milk. Other lists: shopping list." and r.private,
          r.reply)
    r = say(w, "cross milk off the shopping list")
    check("ticked off on the list named", r.reply == "Marked done."
          and [t["text"] for t in w.s.todos() if t["list"] == "shopping"] == ["eggs", "bread"]
          and any(t["text"] == "milk" and t["list"] == "" for t in w.s.todos()))
    r = say(w, "remove eggs from the shopping list")
    check("removed from the list named", r.reply == "Removed from your shopping list.", r.reply)
    r = say(w, "what lists do I have")
    check("which lists", r.reply == "Your lists, besides the to-do list: shopping list (1 item)."
          and r.private, r.reply)
    r = say(w, "clear the shopping list")
    check("'clear the shopping list' changes nothing and points to the app's Clear list",
          "Clear list" in r.reply and "are you sure?" in r.reply
          and "Nothing was changed" in r.reply and len(w.s.todos()) == 2, r.reply)
    check("'clear the packing list' (there is none) says so",
          say(w, "clear the packing list").reply == "There is nothing on your packing list.")
    lists = w.s.lists()
    check("lists() names the shopping list with its count",
          lists == [{"name": "shopping", "title": "Shopping list", "open": 1}], lists)
    st = w.s.status()
    check("GET /api/schedule carries the lists and each item's list",
          st["lists"] == lists and {t["list"] for t in st["todo"]} == {"", "shopping"})


def t_clearing_a_named_list_only_as_the_app_saw_it():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 12, 0), name="clear")
    for t in ("milk", "eggs"):
        w.s.add_todo(t, list_name="shopping")
    w.s.add_todo("post the letter")
    code, out = w.s.clear_list("shopping", 3)
    check("the wrong count (something added since the app looked): 409, nothing cleared",
          code == 409 and "changed since you looked" in out["error"] and len(w.s.todos()) == 3, out)
    code, out = w.s.clear_list(None, 1)
    check("the to-do list is never cleared at once", code == 409 and len(w.s.todos()) == 3, out)
    code, out = w.s.clear_list("all", 1)
    check("'all' is not a list", code == 400)
    S._SCHED = w.s
    try:
        code, out = S.handle_act({"do": "clear_list", "list": "shopping", "count": True})
        check("a count that is not a whole number is refused", code == 400)
        code, out = S.handle_act({"do": "clear_list", "list": "shopping", "count": 2})
        check("the right count: cleared, said", code == 200 and out["said"] ==
              "Cleared your shopping list (2 items)." and [t["text"] for t in w.s.todos()] ==
              ["post the letter"], out)
        code, out = S.handle_add({"kind": "todo", "text": "tent", "list": "Camping list"})
        check("POST /api/schedule/add with a list", code == 200 and out["job"]["list"] == "camping")
        code, out = S.handle_add({"kind": "todo", "text": "tent", "list": "a b c d"})
        check("... and a bad list name is 400 with a sentence", code == 400 and out.get("error"))
    finally:
        S._SCHED = None
    src = (HERE / "jarvis_schedule.py").read_text(encoding="utf-8")
    code_only = re.sub(r'"""[\s\S]*?"""|#[^\n]*', "", src)
    check("still no DELETE that is not by id or by state in the scheduler's code",
          not re.search(r"DELETE FROM jobs(?! WHERE (?:id|state))", code_only))


def t_too_many_lists_is_said():
    w = World(time.time(), name="many")
    for i in range(S.MAX_LISTS):
        w.s.add_todo("x", list_name="box" + "abcdefghijklmnopqrstuvwxyz"[i])
    try:
        w.s.add_todo("x", list_name="one more")
        ok = False
    except OverflowError as exc:
        ok = "lists" in str(exc)
    check(f"a {S.MAX_LISTS + 1}th list is refused with a sentence", ok)


def t_an_older_file_gains_the_new_columns():
    path = _TMP / "old.db"
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL,
        text TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, due REAL, rule TEXT, duration REAL,
        left_s REAL, created REAL NOT NULL, changed REAL NOT NULL, fired_at REAL, fired_due REAL,
        late INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'app');
        INSERT INTO jobs (id, kind, text, state, created, changed) VALUES
        ('s0123456789', 'todo', 'buy milk', 'active', 1, 1);""")
    c.commit()
    c.close()
    s = S.Scheduler(path, clock=Clock(1000.0), publish=lambda k, d: None, spawn=lambda fn: None)
    todo = s.todos()
    check("a schedule.db from before opens: the old item is on the to-do list",
          [(t["text"], t["list"]) for t in todo] == [("buy milk", "")], todo)
    check("... and a named list works on it", s.add_todo("eggs", list_name="shopping")["list"]
          == "shopping")

# --------------------------------------------------------------------------
#   "What did I miss?"
# --------------------------------------------------------------------------


def _deps(pending=0, created=None, senders=None, tools=(), asked=None):
    def gate(action, detail, prompt):
        if asked is not None:
            asked.append((action, detail.get("for")))
        return Verdict(True, "auto", "auto")
    return B.Deps(tier_of=lambda a: "auto", gate=gate, tools_enabled=lambda: set(tools),
                  pending_count=lambda: pending,
                  pending_created=(lambda: created) if created is not None else (lambda: None),
                  email_senders=senders, email_search=lambda *a: (_ for _ in ()).throw(
                      ConnectionRefusedError("no network")),
                  senders_on=lambda: senders is not None, publish=lambda k, d: None, deadline=5.0)


def t_what_did_i_miss_since_you_last_talked():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 9, 0)
    w = World(now, name="missed")
    w.s.add_at("reminder", local(2026, 9, 25, 10, 0), "call the bank")
    w.s.add_at("alarm", local(2026, 9, 25, 11, 0))
    w.s.add_at("reminder", local(2026, 9, 25, 18, 0), "water the plants")
    w.s.add_todo("post the letter")
    w.clock.t = local(2026, 9, 25, 10, 0)
    w.s.tick()
    w.clock.t = local(2026, 9, 25, 11, 0)
    w.s.tick()
    w.clock.t = local(2026, 9, 25, 14, 30)
    with NoSockets() as ns:
        b = B.build_missed(sched=w.s, now=w.clock.t, since=local(2026, 9, 25, 9, 30),
                           deps=_deps(pending=2, created=[local(2026, 9, 25, 8, 0),
                                                          local(2026, 9, 25, 12, 0)]))
    check("no socket, no model", not ns.tried)
    check("the heading says since when, and what that time is",
          b["heading"] == "What you missed since 09:30 today, when you last talked to Jarvis.",
          b["heading"])
    sec = {s["key"]: s for s in b["sections"]}
    check("what went off, in order, with the words as lines",
          sec["went_off"]["summary"] == "2 things went off: 1 reminder and 1 alarm."
          and sec["went_off"]["items"] == ["10:00 call the bank", "11:00 alarm"], sec["went_off"])
    check("cards waiting, and how many came up since",
          sec["approvals"]["summary"] == "2 cards are waiting for your yes or no. 1 of them came up "
          "since then. Open Jarvis to answer.", sec["approvals"]["summary"])
    check("what is next", sec["next"]["summary"] == "The next is at 18:00 today."
          and sec["next"]["items"] == ["18:00 today: water the plants"], sec["next"])
    check("email not set up: not mentioned", "email" not in sec)
    check("no weather line, private, never kept as the latest briefing",
          B.OUTSIDE_LINE not in b["text"] and b["private"] is True and b["source"] == "missed")
    b2 = B.build_missed(sched=w.s, now=w.clock.t, since=local(2026, 9, 25, 10, 30), deps=_deps())
    check("since later: only what went off after it",
          next(s for s in b2["sections"] if s["key"] == "went_off")["items"] == ["11:00 alarm"])
    b3 = B.build_missed(sched=w.s, now=w.clock.t, since=w.clock.t - 3 * 86400, deps=_deps())
    check("never further back than a day, and said so",
          b3["heading"].startswith("What you missed in the last 24 hours.") and not b3["since_known"])
    b4 = B.build_missed(sched=w.s, now=w.clock.t, since=None, deps=_deps())
    check("after a restart: the last 12 hours, said so",
          b4["heading"].startswith("What you missed in the last 12 hours.")
          and "restarted" in b4["heading"] and abs(b4["since"] - (w.clock.t - 12 * 3600)) < 1)
    b5 = B.build_missed(sched=w.s, now=w.clock.t, since=local(2026, 9, 25, 14, 0), deps=_deps())
    check("nothing since: said plainly",
          next(s for s in b5["sections"] if s["key"] == "went_off")["summary"] == "Nothing went off.")


def t_what_did_i_miss_reads_email_like_the_briefing():
    use_tz("Europe/London")
    os.environ["JARVIS_IMAP_HOST"] = "imap.example.com"
    try:
        w = World(local(2026, 9, 25, 12, 0), name="missedmail")

        def two(p, newest):
            return 2, [b"From: Alex <alex@example.com>\r\n\r\n", b"From: noreply@github.com\r\n\r\n"]
        asked = []
        with NoSockets() as ns:
            b = B.build_missed(sched=w.s, now=w.clock.t, since=w.clock.t - 3600,
                               deps=_deps(senders=two, tools=("email_check",), asked=asked))
        check("the read goes through the gate as email_read, saying what asked",
              asked == [("email_read", '"What did I miss?"')], asked)
        sec = next((s for s in b["sections"] if s["key"] == "email"), None)
        check("email set up: the count and who from, as the briefing reads them, no socket",
              sec is not None and sec["summary"] == "2 unread emails."
              and sec["items"] == ["From Alex and noreply@github.com"] and not ns.tried, sec)
        check("... and it says email was read (the names are outside text)",
              b["read"] == [B.EMAIL_TOOL])
    finally:
        os.environ.pop("JARVIS_IMAP_HOST", None)


def t_what_did_i_miss_by_voice_the_route_and_touch():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    for text in ("what did I miss", "What have I missed?", "did I miss anything", "catch me up",
                 "what's new", "what happened while I was away", "Jarvis, what did I miss?"):
        got = Q.match(text, now)
        check(f"ours: {text!r}", got is not None and got.name == "missed", got and got.name)
    for text in ("what did I miss in the meeting", "I miss my cat", "what's new in python 3.13"):
        check(f"to the model: {text!r}", Q.match(text, now) is None)
    w = World(now, name="missedturn")
    B._forget_seen()
    body = {"messages": [{"role": "user", "content": "hello", "provenance": "typed"}],
            "conversation_id": "abcdefgh-2"}
    Q.answer_turn(body, sched=w.s, now=local(2026, 9, 25, 11, 0))
    r = Q.answer_turn({"messages": [{"role": "user", "content": "what did I miss",
                                     "provenance": "voice"}], "conversation_id": "abcdefgh-2"},
                      sched=w.s, now=now)
    check("by voice: since the previous message (11:00), answered without the model",
          r is not None and r.reply.startswith("What you missed since 11:00 today")
          and Q.route_fields(r).get("gate") == "private" and r.intent == "missed", r and r.reply)
    check("touch: every chat message counts, whoever's words", B.touch(now + 5) == now)
    B._forget_seen()
    S._SCHED = w.s
    B.forget()
    try:
        code, out = B.handle_now({"missed": True}, sched=w.s, deps=_deps())
        check("POST /api/briefing/now {\"missed\": true}: the answer, source 'missed'",
              code == 200 and out["briefing"]["source"] == "missed"
              and "12 hours" in out["briefing"]["heading"], out)
        check("... not kept as the latest briefing", B.latest() is None)
        code, out = B.handle_now({"missed": True}, sched=w.s, deps=_deps())
        check("... and asking counts as looking: the next one is since then",
              code == 200 and "when you last talked to Jarvis" in out["briefing"]["heading"])
    finally:
        S._SCHED = None
        B._forget_seen()


def t_the_briefing_counts_named_lists_apart():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 7, 0), name="brieflists")
    w.s.add_todo("post the letter")
    w.s.add_todo("milk", list_name="shopping")
    w.s.add_todo("eggs", list_name="shopping")
    b = B.build(sched=w.s, now=w.clock.t, deps=_deps())
    sec = next(s for s in b["sections"] if s["key"] == "todo")
    check("the briefing's to-do part: the to-do list, and each named list as one counted line",
          sec["summary"] == "1 open item. 1 other list has items."
          and sec["items"] == ["post the letter", "Shopping list: 2 items"], sec)


def t_the_words_match_both_apps():
    js = (REPO / "jarvis-desktop" / "src" / "coming-up.js").read_text(encoding="utf-8")
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "net" / "Schedule.kt").read_text(encoding="utf-8")
    check("the fast path's 'Clear list' is the apps' button", 'CLEAR_LIST_LABEL = "Clear list"' in js
          and 'CLEAR_LIST = "Clear list"' in kt and "Clear list" in Q.LIST_CLEAR_IN_APP)
    check("ten minutes everywhere", "SNOOZE_SECONDS = 600" in js and "SNOOZE_SECONDS = 600" in kt
          and S.SNOOZE_DEFAULT == 600.0)
    bj = (REPO / "jarvis-desktop" / "src" / "briefing.js").read_text(encoding="utf-8")
    bk = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "net" / "Briefing.kt").read_text(encoding="utf-8")
    check("'What did I miss?' in both apps and on the PC",
          B.MISSED_LABEL in bj and B.MISSED_LABEL in bk)


def main():
    orig_tz = os.environ.get("TZ")
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        if orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig_tz
        if hasattr(time, "tzset"):
            time.tzset()
        S._audit = _real_audit
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
