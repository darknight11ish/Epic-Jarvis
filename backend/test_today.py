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
8. The Today board (GTD-2, 2026-10-18) is ADDITIVE: on a quiet day its
   answer is exactly {"available": True}, the scheduler's own replies are
   byte-identical before and after it is read, and a job's full view does
   not change.
9. Due reminders come from the one scheduler (never jarvis_tasks.py, which
   is the job list): due, overdue and just-went-off jobs are listed, future
   ones and to-do items are not, and a GTD-1 field rides along only when the
   row really has it.
10. Next steps come from the real stores: the first open step of each active
   goal, and the first open item on each project's work list.
11. Owner-words-only proposals: assistant and tool words, temporary chats
   and crisis chats are never scanned; a commitment an open reminder or
   Today card already covers is not proposed again; the private-lists/App
   lock hiding withholds the whole list; nothing is created by the scan.
12. The route GET /api/today/cockpit (served by the module the server
   already wraps, jarvis_brain_reads.py) answers the board, withholds
   everything for ?hidden=1, and is a read.
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


# ======================================================== 8. the board (GTD-2)

def _tomorrow(now):
    import datetime
    return (datetime.date.fromtimestamp(now) + datetime.timedelta(days=1)).isoformat()


class _QuietStore:
    """An empty goals/projects store for tests that must not import the real
    modules (reading a board must not start the scheduler loop in a test)."""

    def list(self):
        return []

    def next_open_step(self, goal_id):
        return None


def t_the_board_is_additive():
    """The additive contract: a quiet day answers exactly what existed
    before, and reading the board edits no scheduler reply."""
    s, clock, events, cards = fresh()
    j = T.add("Gym bag", GYM, sched=s)
    before = json.dumps(s.status(), sort_keys=True, default=str)
    view_before = json.dumps(s.job(j["id"]), sort_keys=True, default=str)
    quiet = _QuietStore()
    board = T.cockpit_sections(s, now=clock.t, turns=(), goals=quiet, projects=quiet)
    check("a quiet day: no section keys at all, and the switch's own state",
          board == {"available": True, "unspoken_commitments_enabled": False,
                    "rollover_cards": []}, json.dumps(board, sort_keys=True))
    after = json.dumps(s.status(), sort_keys=True, default=str)
    check("the scheduler's own reply is unchanged by reading the board",
          before == after)
    check("... and one job's whole view is unchanged too",
          view_before == json.dumps(s.job(j["id"]), sort_keys=True, default=str))
    out = T.read_cockpit(sched=s, now=clock.t, turns=(), goals=quiet, projects=quiet)
    check("read_cockpit on a quiet day is the same additive answer",
          out == {"available": True, "unspoken_commitments_enabled": False,
                  "rollover_cards": []}, json.dumps(out, sort_keys=True))
    check("the old card list still answers exactly as before",
          [c["text"] for c in T.cards(sched=s)] == ["Gym bag"])


def t_due_reminders():
    s, clock, events, cards = fresh()
    started = clock.t
    code, out = S.handle_add({"kind": "reminder", "at": started + 60,
                              "text": "Call the dentist"})
    check("a reminder is set on the one scheduler", code == 200, str(out))
    due_id = out["job"]["id"]
    S.handle_add({"kind": "reminder", "at": started + 7200, "text": "Later thing"})
    s.add_todo("Buy milk")
    clock.t = started + 3600          # an hour later; the PC did not tick
    board = T.cockpit_sections(s, now=clock.t, turns=())
    due = board.get("due_reminders") or []
    texts = [r["text"] for r in due]
    check("a due reminder is on the board", "Call the dentist" in texts, json.dumps(due))
    check("... a later one and a to-do item are not",
          "Later thing" not in texts and "Buy milk" not in texts, json.dumps(due))
    row = next(r for r in due if r["text"] == "Call the dentist")
    check("... marked overdue, with its time and kind",
          row["overdue"] is True and row["kind"] == "reminder" and row["due"] is not None
          and row["id"] == due_id, json.dumps(row))
    check("no invented GTD-1 fields while the scheduler carries none",
          not any(k in row for k in T.CONTEXT_KEYS), json.dumps(row))
    # A GTD-1 row, once session A's work merges: copied only when present.
    rich = T._due_row({"id": "s0000000aaa", "kind": "reminder", "due": clock.t - 30,
                       "text": "Reply to Sam", "context_bundle": {"source_summary": "the Q4 email"},
                       "suggested_prompt": "Draft the reply to Sam", "snooze_count": 3,
                       "stuck_hint": True}, clock.t, went_off=False)
    check("a GTD-1 field rides along when the row really has it",
          rich.get("suggested_prompt") == "Draft the reply to Sam"
          and rich.get("stuck_hint") is True and rich.get("snooze_count") == 3
          and rich.get("context_bundle", {}).get("source_summary") == "the Q4 email",
          json.dumps(rich))
    neutral = T._due_row({"id": "s0000000aab", "kind": "reminder", "due": clock.t - 30,
                          "text": "Call the vet"}, clock.t, went_off=False)
    spicy = T._due_row({"id": "s0000000aac", "kind": "reminder", "due": clock.t - 30,
                        "text": "My chemotherapy appointment"}, clock.t, went_off=False)
    check("a sensitive reminder is marked, so break-into-steps is never offered",
          spicy.get("sensitive") is True and "sensitive" not in neutral,
          json.dumps([neutral, spicy]))
    # Fired: it shows as just went off, with no words changed.
    s.tick()
    board = T.cockpit_sections(s, now=clock.t + 1, turns=())
    fired = [r for r in (board.get("due_reminders") or [])
             if r["id"] == due_id and r["went_off"]]
    check("a reminder that just went off is on the board too",
          len(fired) == 1 and fired[0]["text"] == "Call the dentist"
          and fired[0].get("fired_at") is not None, json.dumps(board.get("due_reminders")))


def t_active_next_steps():
    import jarvis_goals as G
    import jarvis_projects as P
    s, clock, events, cards = fresh()
    S.register_kind(G.KIND, "goal check-in", "Jarvis: a goal check-in is due.",
                    **G.KIND_OPTIONS)
    goals = G.Goals(path=TMP / "goals.db", clock=clock, scheduler=s)
    draft = goals.create("Learn to sail")
    goal = goals.create("Insulate the garage",
                        plan=[{"step": "Call two installers", "by": "Friday"},
                              {"step": "Book the first one", "by": ""}])
    goals.accept(goal["id"], plan=[{"step": "Call two installers", "by": "Friday"},
                                   {"step": "Book the first one", "by": ""}])
    projects = P.Projects(path=TMP / "projects.db", clock=clock)
    project = projects.create({"name": "Garage tidy", "kind": "life"}, here=False)
    work_name = project["work_list"]["name"]
    s.add_todo("Sort the shelves", list_name=work_name)
    s.add_todo("Sweep the floor", list_name=work_name)
    board = T.cockpit_sections(s, now=clock.t, turns=(), goals=goals, projects=projects)
    steps = board.get("active_next_steps") or []
    check("the first open step of an active goal, and the goal's words",
          any(x["kind"] == "goal" and x["step"] == "Call two installers"
              and x["name"] == "Insulate the garage" for x in steps), json.dumps(steps))
    check("... the draft goal is not one of them",
          all(x["name"] != "Learn to sail" for x in steps), json.dumps(steps))
    check("the first open item on the project's work list",
          any(x["kind"] == "project" and x["step"] == "Sort the shelves"
              and x["name"] == "Garage tidy" for x in steps), json.dumps(steps))
    check("... only the FIRST open item, not every one",
          all(x["step"] != "Sweep the floor" for x in steps), json.dumps(steps))
    goals.mark_step(goal["id"], 0, True)
    board = T.cockpit_sections(s, now=clock.t, turns=(), goals=goals, projects=projects)
    step = next(x for x in board["active_next_steps"] if x["kind"] == "goal")
    check("ticking a step moves the board to the next one",
          step["step"] == "Book the first one", json.dumps(step))
    goals.stop(goal["id"])
    board = T.cockpit_sections(s, now=clock.t, turns=(), goals=goals, projects=projects)
    check("a stopped goal is not on the board",
          all(x["kind"] != "goal" for x in board.get("active_next_steps") or []),
          json.dumps(board.get("active_next_steps")))


def t_owner_words_only_proposals():
    now = MONDAY_6
    turns = [
        {"role": "user", "text": "I'll send the report to Sam tomorrow.",
         "conversation": "conv-aa000001"},
        {"role": "assistant", "text": "I'll send the report myself, Sam.",
         "conversation": "conv-aa000001"},
        {"role": "tool", "text": "I need to call the petrol station.",
         "conversation": "conv-aa000001"},
        {"role": "user", "text": "Let me get back to you tomorrow.",
         "conversation": "conv-aa000002"},
        {"role": "user", "text": "I need to call the bank.",
         "conversation": "conv-aa000002"},
        {"role": "user", "text": "remind me to call the dentist",
         "conversation": "conv-aa000003"},
        {"role": "user", "text": "I finished the report.",
         "conversation": "conv-aa000003"},
        {"role": "user", "text": "Can I'll do what now?",
         "conversation": "conv-aa000003"},
        {"role": "user", "text": "I'll book the car service tomorrow.",
         "conversation": "conv-aa000004", "temporary": True},
        {"role": "user", "text": "I'll call my sister tomorrow.",
         "conversation": "conv-aa000005", "crisis": True},
    ]
    out = T.scan_unspoken_commitments(turns, now=now, enabled=True)
    texts = [p["text"] for p in out]
    check("the owner's future commitments are proposed, in their own words",
          "send the report to Sam tomorrow" in texts and "get back to you tomorrow" in texts
          and "call the bank" in texts and "call the dentist" in texts, json.dumps(out))
    check("a proposal is only {text, suggested_due, source_conv_id}",
          all(set(p) == {"text", "suggested_due", "source_conv_id"} for p in out),
          json.dumps(out))
    check("the chat it came from is named, not guessed",
          next(p for p in out if p["text"] == "send the report to Sam tomorrow")
          ["source_conv_id"] == "conv-aa000001", json.dumps(out))
    check("a day the words name is suggested",
          next(p for p in out if p["text"] == "send the report to Sam tomorrow")
          ["suggested_due"] == _tomorrow(now)
          and next(p for p in out if p["text"] == "call the bank")["suggested_due"] == "",
          json.dumps(out))
    check("assistant and tool words are NEVER scanned",
          not any("myself" in t for t in texts) and "call the petrol station" not in texts,
          json.dumps(texts))
    check("a temporary chat and a crisis chat are never scanned",
          "book the car service tomorrow" not in texts
          and "call my sister tomorrow" not in texts, json.dumps(texts))
    check("a question is not a commitment", all("do what now" not in t for t in texts))
    check("nothing to propose: an empty list, not an error",
          T.scan_unspoken_commitments([], enabled=True) == []
          and T.scan_unspoken_commitments([{"role": "user", "text": "Hello."}],
                                          enabled=True) == [])
    deduped = T.scan_unspoken_commitments(turns, now=now, enabled=True,
                                          existing=["call the bank"])
    check("already an open reminder, not re-proposed",
          "call the bank" not in [p["text"] for p in deduped], json.dumps(deduped))
    shielded = T.scan_unspoken_commitments(turns, now=now, enabled=True,
                                           existing=["Send report to Sam"])
    check("... the same for a longer owner phrasing",
          "send the report to Sam tomorrow" not in [p["text"] for p in shielded],
          json.dumps(shielded))
    check("hidden stores no proposals at all",
          T.scan_unspoken_commitments(turns, now=now, hidden=True, enabled=True) == [])
    many = [{"role": "user", "text": f"I'll do thing number {i} tomorrow.",
             "conversation": "conv-aa00000x"} for i in range(8)]
    capped = T.scan_unspoken_commitments(many, now=now, enabled=True)
    check("at most a handful, not a wall of chips",
          len(capped) == T.MAX_PROPOSALS, json.dumps(capped))
    s, clock, events, cards = fresh()
    before = json.dumps(s.status(), sort_keys=True, default=str)
    T.scan_unspoken_commitments(turns, now=now, enabled=True)
    check("the scan creates nothing: the scheduler is untouched",
          json.dumps(s.status(), sort_keys=True, default=str) == before)


def t_board_proposals_from_kept_chats():
    import jarvis_chat_log as L
    s, clock, events, cards = fresh()
    folder = TMP / "history"
    folder.mkdir()
    log = L.ChatLog(folder / "chat-history.db", folder / "chat-history.json",
                    lambda: bytes(range(32)), clock=clock)
    L.use(log)
    try:
        log.record_turn({"messages": [{"role": "user", "content":
                                       "I need to call the dentist tomorrow about the crown."}],
                         "conversation_id": "conv-brd00001", "device": "phone"},
                        lane="local", turn={"finish_reason": "stop", "client_gone": False,
                                            "rounds": 1, "answer": "Noted.",
                                            "tools_ran": []})
        log.record_turn({"messages": [{"role": "user",
                                       "content": "I'll book the car service tomorrow."}],
                         "conversation_id": "conv-brd00002", "device": "phone",
                         "temporary": True})
        log.record_turn({"messages": [{"role": "user",
                                       "content": "I'll call my sister tomorrow."}],
                         "conversation_id": "conv-brd00003", "device": "phone"},
                        lane="local", turn={"crisis": True, "finish_reason": "stop",
                                            "answer": "I'm here.", "tools_ran": []})
        turns = T.recent_owner_turns()
        owner = [t["text"] for t in turns]
        check("the kept chats are read through jarvis_chat_log's own API",
              any("dentist tomorrow" in x for x in owner), json.dumps(owner))
        check("a temporary chat was never kept, so it is never read",
              all("car service" not in x for x in owner), json.dumps(owner))
        check("a crisis chat is flagged and left alone",
              any(t.get("crisis") is True for t in turns)
              and all("call my sister" not in p["text"] for p in
                      T.scan_unspoken_commitments(turns, now=clock.t, enabled=True)),
              json.dumps(turns))
        board = T.cockpit_sections(s, now=clock.t, turns=turns, unspoken=True)
        proposals = board.get("proposals") or []
        check("a kept chat's commitment reaches the board as a proposal",
              any("dentist tomorrow about the crown" in p["text"] for p in proposals),
              json.dumps(proposals))
        S.handle_add({"kind": "reminder", "at": clock.t + 86400,
                      "text": "Call the dentist"})
        board = T.cockpit_sections(s, now=clock.t, turns=turns, unspoken=True)
        check("a reminder the owner already set covers it: not proposed again",
              all("dentist" not in p["text"] for p in board.get("proposals") or []),
              json.dumps(board.get("proposals")))
    finally:
        L.use(None)


def t_the_cockpit_route():
    import jarvis_brain_reads as B
    check("the board rides on the module the server already wraps",
          B.COCKPIT_PATH == T.COCKPIT_PATH and B.COCKPIT_PATH in B.PATHS)
    s, clock, events, cards = fresh()
    code, out = B.handle_get(B.COCKPIT_PATH, "")
    check("GET /api/today/cockpit answers the board", code == 200
          and isinstance(out, dict) and out.get("available") is True, json.dumps(out))
    check("... a quiet day carries no sections", "due_reminders" not in out
          and "active_next_steps" not in out and "proposals" not in out, json.dumps(out))
    code, out = B.handle_get(B.COCKPIT_PATH, "hidden=1")
    check("?hidden=1 withholds every word", code == 200
          and out == {"available": True, "hidden": True}, json.dumps(out))
    S.handle_add({"kind": "reminder", "at": clock.t + 60, "text": "Call the vet"})
    clock.t += 3600
    code, out = B.handle_get(B.COCKPIT_PATH, "")
    check("... and with something due it lists it, words included",
          any(r["text"] == "Call the vet" for r in out.get("due_reminders") or []),
          json.dumps(out))
    code, hidden = B.handle_get(B.COCKPIT_PATH, "hidden=1")
    check("while hidden, no reminder's words come back at all",
          "Call the vet" not in json.dumps(hidden), json.dumps(hidden))
    check("the route is listed once, as a read", B.PATHS.count(B.COCKPIT_PATH) == 1)
    check("no new file is registered for it: jarvis_today.py is already shipped",
          '"jarvis_today.py"' in (HERE / "_where.py").read_text(encoding="utf-8"))


class _Verdict:
    def __init__(self, tier="ask", allowed=True, outcome="approved", reason=""):
        self.tier, self.allowed, self.outcome, self.reason = tier, allowed, outcome, reason


def t_the_switch_is_off_by_default_and_asks():
    T.set_unspoken(False)
    check("the said-I'd-do switch is OFF by default (no file, no reading)",
          T.unspoken_enabled() is False)
    calls = []

    def denied(action, detail, prompt):
        calls.append((action, detail, prompt))
        return _Verdict(allowed=False, outcome="denied")

    code, out = T.request_unspoken(True, gate=denied, tier_of=lambda a: "ask",
                                   spawn=lambda fn: fn())
    check("ON is ONE card that waits, and changes nothing yet",
          code == 202 and out.get("waiting") is True and out.get("enabled") is False
          and T.unspoken_enabled() is False, json.dumps(out))
    check("the card uses the existing change_own_config action (no new gate row)",
          bool(calls) and calls[0][0] == "change_own_config"
          and "suggestions" in calls[0][2].casefold(), str(calls[:1]))
    check("... and says nothing leaves this PC", calls[0][1].get("leaves_this_pc") is False)
    code, out = T.request_unspoken(False, gate=denied, tier_of=lambda a: "ask",
                                   spawn=lambda fn: fn())
    check("OFF is immediate and raises no card", code == 200
          and out.get("enabled") is False and len(calls) == 1, json.dumps(out))

    def approve(action, detail, prompt):
        calls.append((action, detail, prompt))
        return _Verdict()

    code, out = T.request_unspoken(True, gate=approve, tier_of=lambda a: "ask",
                                   spawn=lambda fn: fn())
    check("with the owner's yes, ON is written and read back",
          code == 202 and T.unspoken_enabled() is True
          and json.loads(T.settings_path().read_text(encoding="utf-8"))
          ["unspoken_commitments_enabled"] is True, json.dumps(out))
    code, out = T.request_unspoken(True, gate=approve, tier_of=lambda a: "ask",
                                   spawn=lambda fn: fn())
    check("turning on something already on asks nothing",
          code == 200 and out.get("waiting") is False, json.dumps(out))
    T.set_unspoken(False)
    code, out = T.request_unspoken(True, gate=approve, tier_of=lambda a: "auto",
                                   spawn=lambda fn: fn())
    check("an action that is not tier 'ask' is refused in words", code == 503
          and "ask" in out.get("error", ""), json.dumps(out))
    T.set_unspoken(False)


def t_turning_it_off_while_the_card_waits_wins():
    T.set_unspoken(False)
    held = []
    T.request_unspoken(True, gate=lambda *a: _Verdict(), tier_of=lambda a: "ask",
                       spawn=lambda fn: held.append(fn))
    code, out = T.request_unspoken(False, gate=lambda *a: _Verdict(),
                                   tier_of=lambda a: "ask", spawn=lambda fn: held.append(fn))
    check("turned off while its card was waiting", code == 200 and held,
          json.dumps(out))
    held[0]()                         # the card now comes back "approved"
    check("... a yes that arrives afterwards changes nothing",
          T.unspoken_enabled() is False)
    T.set_unspoken(False)


def t_proposals_fade_and_are_gated_by_the_switch():
    now = MONDAY_6
    day = 86400.0
    day3 = [{"role": "user", "text": "I'll call the plumber tomorrow.",
             "conversation": "conv-aa000010", "at": now - 3 * day}]
    day4 = [{"role": "user", "text": "I'll call the plumber tomorrow.",
             "conversation": "conv-aa000010", "at": now - 4 * day}]
    check("said 3 days ago: still offered", len(T.scan_unspoken_commitments(
        day3, now=now, enabled=True)) == 1,
        json.dumps(T.scan_unspoken_commitments(day3, now=now, enabled=True)))
    check("said 4 days ago: faded, gone", T.scan_unspoken_commitments(
        day4, now=now, enabled=True) == [])
    check("no time on a turn: still offered (an older PC's history)",
          len(T.scan_unspoken_commitments(
              [{"role": "user", "text": "I'll call the plumber tomorrow."}],
              now=now, enabled=True)) == 1)
    check("the switch off: no proposals at all", T.scan_unspoken_commitments(
        day3, now=now, enabled=False) == [])
    T.set_unspoken(False)
    check("the real switch off is what a bare call reads",
          T.scan_unspoken_commitments(day3, now=now) == [])
    T.set_unspoken(True)
    try:
        check("the real switch on is what a bare call reads",
              len(T.scan_unspoken_commitments(day3, now=now)) == 1)
    finally:
        T.set_unspoken(False)


def t_rollover_is_honestly_empty():
    check("rollover_cards is [] - no per-day done state exists to roll over",
          T.rollover_cards(now=MONDAY_6) == []
          and T.rollover_cards() == [])
    s, clock, events, cards = fresh()
    board = T.cockpit_sections(s, now=clock.t, turns=(), unspoken=False,
                               goals=_QuietStore(), projects=_QuietStore())
    check("... and the board says so out loud, as an empty list",
          board.get("rollover_cards") == [], json.dumps(board))


class _PostHandler:
    def __init__(self, path, raw=b"{}"):
        self.path = path
        self.raw = raw
        self.sent = None

    def do_GET(self):
        self.sent = ("original-get", self.path)

    def do_POST(self):
        self.sent = ("original-post", self.path)

    def _send(self, code, body):
        self.sent = (code, body)


def t_the_switch_has_one_post_route():
    import jarvis_brain_reads as B
    check("the switch's POST rides the same already-wrapped path",
          B.COCKPIT_PATH in B.POST_PATHS and B.POST_PATHS == (B.COCKPIT_PATH,))
    T.set_unspoken(False)

    class Hd(_PostHandler):
        pass

    line = B.install(Hd, origin_ok=lambda s: True, token_ok=lambda s: True,
                     read_body=lambda s: s.raw)
    check("install still says what it answers", "Search old chats" in line, line)
    h = Hd(B.COCKPIT_PATH, raw=json.dumps({"enabled": False}).encode())
    h.do_POST()
    check("POST off is answered here, at once", h.sent[0] == 200
          and h.sent[1].get("enabled") is False, str(h.sent))
    h = Hd("/api/schedule/add", raw=b"{}")
    h.do_POST()
    check("every other POST goes to the original handler, untouched",
          h.sent == ("original-post", "/api/schedule/add"), str(h.sent))

    class Locked(_PostHandler):
        pass

    B.install(Locked, origin_ok=lambda s: True, token_ok=lambda s: False,
              read_body=lambda s: s.raw)
    h = Locked(B.COCKPIT_PATH, raw=b'{"enabled": false}')
    h.do_POST()
    check("no token: the switch is not reachable", h.sent[0] == 401, str(h.sent))

    class Bad(_PostHandler):
        pass

    B.install(Bad, origin_ok=lambda s: True, token_ok=lambda s: True,
              read_body=lambda s: s.raw)
    h = Bad(B.COCKPIT_PATH, raw=b"not json")
    h.do_POST()
    check("a bad body is 400, in words", h.sent[0] == 400, str(h.sent))
    h = Bad(B.COCKPIT_PATH, raw=b'{"enabled": "yes"}')
    h.do_POST()
    check("a body that is not a yes/no is refused", h.sent[0] == 400
          and "true|false" in h.sent[1].get("error", ""), str(h.sent))


if __name__ == "__main__":
    for fn in (t_kept_on_the_one_scheduler, t_when_it_shows, t_its_time_rings_no_doorbell,
               t_the_limits_and_refusals, t_the_apps_route, t_the_fast_path,
               t_no_socket_no_model, t_the_board_is_additive, t_due_reminders,
               t_active_next_steps, t_owner_words_only_proposals,
               t_board_proposals_from_kept_chats, t_the_cockpit_route,
               t_the_switch_is_off_by_default_and_asks,
               t_turning_it_off_while_the_card_waits_wins,
               t_proposals_fade_and_are_gated_by_the_switch,
               t_rollover_is_honestly_empty, t_the_switch_has_one_post_route):
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
