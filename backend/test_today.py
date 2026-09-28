"""test_today.py - Today cards (jarvis_today.py; the owner's choice of the
research audit's idea 6, 2026-09-28).

    python3 backend/test_today.py

Runs anywhere; no model, no network. What it proves:

1. A card is kept on the ONE scheduler (kind "today", schedule.db), set up
   at once with NO approval card (like a plain repeating reminder), listed
   in Coming up with its repeat and next time, paused and deleted like any
   job - one at a time.
2. Whether it shows is worked out from the clock: on its days, from its
   time to the end of the day ("showing"), "later" before its time, and
   not at all on other days or while paused.
3. Its time coming rings NO doorbell: no "fired" event, nothing in "Just
   went off" or "What did I miss?", not "the next" thing in the briefing -
   only a "changed" event (ids and the kind, never words), so both apps
   redraw.
4. The limits and refusals, in plain words: words needed, at most 80
   characters, at most 20 cards, a time of day only ("every N hours" and a
   one-off are refused), the same card twice is one.
5. The apps' route (POST /api/schedule/add {"kind": "today"}) goes through
   the kind's own add, and never raises a card.
6. The fast path (jarvis_quick.py) sets one in the owner's own words,
   lists them (a private answer), removes ONE by its words, and "cancel
   that" takes it back; the sentence is never learned (is_command).
7. Nothing in jarvis_today.py opens a socket or talks to a model.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_today.py", "jarvis_schedule.py", "jarvis_quick.py",
                "jarvis_briefing.py")
TMP = Path(tempfile.mkdtemp(prefix="jarvis-today-"))
os.environ["JARVIS_SCHEDULE_DB"] = str(TMP / "schedule.db")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
sys.path.append(str(HERE / "rebuilt"))
import jarvis_schedule as S  # noqa: E402
import jarvis_today as T  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []
DAY = 86400.0


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


#: Monday 28 September 2026, 06:00 on this machine's clock.
MONDAY_6 = S.wall_to_epoch(2026, 9, 28, 6, 0)


class Clock:
    def __init__(self, t=MONDAY_6):
        self.t = t

    def __call__(self):
        return self.t


def fresh():
    clock = Clock()
    events = []
    path = TMP / f"s-{len(os.listdir(TMP))}.db"
    cards = []
    s = S.Scheduler(path, clock=clock, spawn=lambda fn: fn(),
                    publish=lambda k, d: events.append((k, dict(d))),
                    gate=lambda *a, **k: cards.append(a) or ("approved", ""))
    S._SCHED = s
    return s, clock, events, cards


GYM = {"every": "week", "at": "07:00", "days": [0, 2]}


# ======================================================== 1. the one scheduler

def t_kept_on_the_one_scheduler():
    check("a kind of the one scheduler, loaded before its loop runs",
          "jarvis_today" in S.KIND_MODULES and S.KINDS[T.KIND].plain_repeat
          and S.KINDS[T.KIND].silent and not S.KINDS[T.KIND].notify)
    s, clock, events, cards = fresh()
    j = T.add("Gym bag", GYM, sched=s)
    check("set up at once, no approval card", j["state"] == "active" and cards == [],
          json.dumps(j))
    check("the owner's words, as said", j["text"] == "Gym bag" and j["kind"] == "today")
    check("its repeat in words, and the next time",
          j["repeat"] == "every Monday and Wednesday at 07:00" and j["when"] == "07:00 today",
          json.dumps(j))
    check("listed in Coming up", [x["id"] for x in s.listed()] == [j["id"]])
    check("adding it rang 'changed' with the id and kind only, never the words",
          any(d == {"id": j["id"], "kind": "today", "state": "changed"} for _, d in events)
          and "Gym bag" not in json.dumps(events), json.dumps(events))
    again = T.add("  'gym BAG' ", GYM, sched=s)
    check("the same card twice is one", again.get("already") is True and again["id"] == j["id"])
    other = T.add("Gym bag", {"every": "day", "at": "07:00"}, sched=s)
    check("the same words at other times is another card", other["id"] != j["id"])
    code, out = s.act(j["id"], "pause")
    check("paused like any job", code == 200 and s.job(j["id"])["state"] == "paused")
    check("a paused card does not show", s.job(j["id"]).get("today") == "")
    s.act(j["id"], "resume")
    code, out = s.act(j["id"], "delete")
    check("deleted at once, like any job", code == 200 and s.job(j["id"]) is None)
    check("the words are the words said, never a stored note", "extra" not in (s.job(other["id"])))


# ======================================================== 2. when it shows

def t_when_it_shows():
    s, clock, events, cards = fresh()
    j = T.add("Gym bag", GYM, sched=s)
    check("before 07:00 on a Monday: later today",
          s.job(j["id"])["today"] == "later" and s.job(j["id"])["shows_at"] == "07:00")
    clock.t = MONDAY_6 + 3600
    check("at 07:00: showing", s.job(j["id"])["today"] == "showing")
    clock.t = MONDAY_6 + 17 * 3600 + 59 * 60
    check("until the end of the day", s.job(j["id"])["today"] == "showing")
    clock.t = MONDAY_6 + DAY
    check("Tuesday: not on the page", s.job(j["id"])["today"] == "")
    clock.t = MONDAY_6 + 2 * DAY + 3600
    check("Wednesday at 07:00: showing again", s.job(j["id"])["today"] == "showing")
    check("worked out from the clock alone: a PC asleep at 07:00 still shows it",
          T.state_of(GYM, MONDAY_6 + 5 * 3600) == "showing")
    check("every weekday: not on a Saturday",
          T.state_of({"every": "weekday", "at": "07:00"}, MONDAY_6 + 5 * DAY + 5 * 3600) == "")
    check("every day: every day", T.state_of({"every": "day", "at": "05:00"}, MONDAY_6 + 5 * DAY)
          == "showing")


# ======================================================== 3. no doorbell

def t_its_time_rings_no_doorbell():
    s, clock, events, cards = fresh()
    j = T.add("Bins out", {"every": "week", "at": "18:00", "days": [0]}, sched=s)
    events.clear()
    clock.t = MONDAY_6 + 12 * 3600 + 1
    went = s.tick()
    check("its time came", went == [j["id"]])
    check("no 'fired' doorbell - no notification, toast or sound",
          not any(d.get("state") == "fired" for _, d in events), json.dumps(events))
    check("... only 'changed', so both apps redraw",
          [d for _, d in events] == [{"id": j["id"], "kind": "today", "state": "changed"}],
          json.dumps(events))
    check("... still on the list, next Monday", s.job(j["id"])["state"] == "active"
          and s.job(j["id"])["today"] == "showing"
          and s.job(j["id"])["when"].startswith("18:00 on Monday"), json.dumps(s.job(j["id"])))
    check("not in 'Just went off'", s.went_off() == [])
    check("not in 'What did I miss?'", s.fired_since(0) == [])
    import jarvis_briefing as B
    nxt = B._next_section(s, clock.t)
    check("never 'the next' thing in the briefing", nxt["state"] == "empty", json.dumps(nxt))
    today = B._today_section(s, clock.t)
    check("nor in the briefing's own Today list", "Bins" not in json.dumps(today))
    clock.t += 3 * DAY
    events.clear()
    s.tick()
    check("found late (the PC slept): no burst, no 'missed', no doorbell",
          not any(d.get("state") == "fired" for _, d in events)
          and "missed" not in s.job(j["id"]), json.dumps(s.job(j["id"])))


# ======================================================== 4. limits

def t_the_limits_and_refusals():
    s, clock, events, cards = fresh()
    for words, why in (("", T.NO_WORDS), ("  ''  ", T.NO_WORDS), ("x" * 81, T.TOO_LONG)):
        try:
            T.add(words, GYM, sched=s)
            check(f"refused: {why}", False)
        except ValueError as exc:
            check(f"refused in plain words: {why[:30]}", str(exc) == why, str(exc))
    for rule in ({"every": "hours", "hours": 2}, {"every": "day", "at": "07:00",
                                                    "until": "08:00"},
                 {"every": "week", "at": "07:00", "days": []}, None, "daily",
                 {"every": "day", "at": "25:00"}):
        try:
            T.add("ok", rule, sched=s)
            check(f"refused: {rule!r}", False)
        except ValueError:
            check(f"refused: {rule!r}", True)
    for i in range(T.MAX_CARDS):
        T.add(f"card {i}", GYM, sched=s)
    try:
        T.add("one too many", GYM, sched=s)
        check("at most 20 cards", False)
    except OverflowError as exc:
        check("at most 20 cards, said plainly", str(exc) == T.TOO_MANY)


# ======================================================== 5. the apps' route

def t_the_apps_route():
    s, clock, events, cards = fresh()
    check("POST /api/schedule/add with kind 'today' is the kind's own add",
          S.KINDS[T.KIND].add is T.add_route)
    code, out = T.add_route({"kind": "today", "text": "Gym bag", "repeat": GYM})
    check("200, set up at once", code == 200 and out["ok"] and out["job"]["state"] == "active"
          and out.get("waiting") is False, json.dumps(out))
    check("said back with its next times, and how to stop it",
          out["said"].startswith("Set: “Gym bag” shows on your Today page every Monday "
                                 "and Wednesday at 07:00. Next: 07:00 today")
          and "Coming up" in out["said"], out["said"])
    code, out = T.add_route({"kind": "today", "text": "Gym bag", "repeat": GYM})
    check("again: already there", code == 200 and out.get("already") is True
          and out["said"] == T.ALREADY)
    code, out = T.add_route({"kind": "today", "text": "Gym bag", "at": clock.t + 60})
    check("a one-off is refused: a card repeats", code == 400 and out["error"] == T.NO_WHEN)
    code, out = T.add_route({"kind": "today", "text": "", "repeat": GYM})
    check("no words: 400 with the reason", code == 400 and out["error"] == T.NO_WORDS)
    code, out = T.add_route("nope")
    check("not an object: 400", code == 400)
    code, out = T.add_route({"kind": "today", "text": {"x": 1}, "repeat": GYM})
    check("words that are not text: 400", code == 400 and out["error"] == T.NO_WORDS)
    check("still no approval card after all that", cards == [])


# ======================================================== 6. the fast path

def t_the_fast_path():
    s, clock, events, cards = fresh()
    now = clock.t
    for said, text, rule in (
            ("show gym bag on Mondays and Wednesdays at 7 on my Today page", "gym bag", GYM),
            ("Show 'Gym bag' on my today page on Monday and Wednesday at 7", "'Gym bag'", GYM),
            ("put bins out on my today page on Thursday evenings", "bins out",
             {"every": "week", "at": "18:00", "days": [3]}),
            ("add a today card saying water the plants every day at 8", "water the plants",
             {"every": "day", "at": "08:00"}),
            ("show passport on my today page every weekday at 6pm", "passport",
             {"every": "weekday", "at": "18:00"})):
        i = Q.match(said, now)
        check(f"matched: {said!r}", i is not None and i.name == "today_set"
              and i.f.get("text") == text and i.f.get("rule") == rule, str(i and i.f))
        check(f"never learned as a fact: {said!r}", Q.is_command(said))
    for said in ("put the kettle on", "show me my calendar for today", "what's on today",
                 "add milk to the today list", "what's on my today list",
                 "remind me on monday at 7 to pack", "what is today"):
        i = Q.match(said, now)
        check(f"not ours: {said!r}", i is None or not i.name.startswith("today_"),
              str(i))
    res = Q.answer("show gym bag on Mondays and Wednesdays at 7 on my Today page", sched=s,
                   now=now, conversation="conv-000001")
    check("set at once, said back", res is not None and "gym bag" in res.reply
          and "every Monday and Wednesday at 07:00" in res.reply and cards == [],
          res and res.reply)
    res = Q.answer("show gym bag on my today page", sched=s, now=now)
    check("no time said: asks for one, sets nothing", res is not None
          and res.reply == T.NO_WHEN and len(T.cards(sched=s)) == 1)
    res = Q.answer("show gym bag on my today page every 2 hours", sched=s, now=now)
    check("not a time of day: says so, sets nothing", res is not None
          and res.reply == T.BAD_RULE and len(T.cards(sched=s)) == 1)
    listed = Q.answer("what's on my today page", sched=s, now=now)
    check("listed on request, as a private answer", listed is not None
          and "gym bag" in listed.reply and listed.private is True, listed and listed.reply)
    undo = Q.answer("cancel that", sched=s, now=now + 5, conversation="conv-000001")
    check("'cancel that' takes it back", undo is not None and T.cards(sched=s) == [],
          undo and undo.reply)
    Q.answer("show gym bag on Mondays at 7 on my Today page", sched=s, now=now)
    out = Q.answer("remove gym bag from my today page", sched=s, now=now)
    check("remove ONE by its words", out is not None and T.cards(sched=s) == []
          and out.reply == T.REMOVED.format(text="gym bag"), out and out.reply)
    out = Q.answer("remove gym bag from my today page", sched=s, now=now)
    check("none there: said plainly", out is not None
          and out.reply == T.NO_SUCH.format(text="gym bag"))
    T.add("tea", GYM, sched=s)
    T.add("tea", {"every": "day", "at": "07:00"}, sched=s)
    out = Q.answer("remove tea from my today page", sched=s, now=now)
    check("two with the same words: neither deleted, the owner is told where",
          out is not None and len(T.cards(sched=s)) == 2 and "Coming up" in out.reply)
    none = Q.answer("what's on my today page", sched=fresh()[0], now=now)
    check("none: said plainly", none is not None and none.reply == T.NONE_SET)


# ======================================================== 7. no way out

def t_no_socket_no_model():
    src = (HERE / "jarvis_today.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    for bad in ("socket", "urllib", "http", "requests", "ollama", "urlopen"):
        check(f"no {bad} in jarvis_today.py", bad not in code.lower())


if __name__ == "__main__":
    for fn in (t_kept_on_the_one_scheduler, t_when_it_shows, t_its_time_rings_no_doorbell,
               t_the_limits_and_refusals, t_the_apps_route, t_the_fast_path,
               t_no_socket_no_model):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    S._SCHED = None
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
