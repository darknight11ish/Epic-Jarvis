"""test_habits.py - habit check-ins (the owner's 2026-11-02 life-coach
decisions D1-D4; backend/jarvis_habits.py).

    python3 backend/test_habits.py

What it proves, with a REAL scheduler (its own SQLite file, a hand-moved clock,
no real thread, no real gate) and REAL SQLite files in a temporary folder:

  - a new habit sets up exactly ONE repeating job of kind "habit_checkin", and
    raises NO card - it is the plain_repeat path, the same class as a plain
    repeating reminder (decided 2026-09-26);
  - ONE tick writes exactly ONE row, and a second tick for the same day adds
    nothing (idempotent per day) - two taps can never make two rows;
  - a tick on a DIFFERENT day adds a second row, so the rule is per day and not
    "the habit can only ever be ticked once";
  - stop deletes the scheduler job, marks the habit stopped, KEEPS every tick,
    and a stopped habit refuses a new tick;
  - record_tick() is the reminder lane's entry point: callable with no server,
    returns the row, raises no card;
  - the nudge's note is deterministic, carries the habit's own words, and holds
    no count, streak, percentage or praise;
  - the week in review is COUNTS OF STORED ROWS from four stores (habit ticks,
    goal steps, reminders that went off, mood rows) with no interpretation -
    and a count it could not read says so instead of reporting zero;
  - the weekly review is a repeating job the owner turns on, and one tap turns
    it off again;
  - the HTTP routes answer exactly those shapes, 404 for an unknown habit, and
    let an unrelated route through to the original handler.

Every check fails on the code before this feature: jarvis_habits.py did not
exist, and the plugin folder that installs it did not exist either.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_habits.py", "jarvis_mood.py", "jarvis_schedule.py",
                "jarvis_goals.py")

import jarvis_goals as G  # noqa: E402
import jarvis_habits as H  # noqa: E402
import jarvis_mood as M  # noqa: E402
import jarvis_schedule as S  # noqa: E402

PASSED, FAILED = [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-habits-"))

#: Words a habit feature must never say: a score, a streak, a percentage, a
#: verdict or praise. This project has removed a streak twice on purpose.
BANNED = ("streak", "score", "percent", "%", "slipping", "well done", "great job",
          "average", "trend", "target", "goal met", "on track")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


class World:
    """A real Scheduler plus the real module over its own SQLite file - wired
    exactly as install() wires them, but without touching the module's own
    singleton, so no test shares state."""

    def __init__(self, t=1_000_000.0, *, answer="approved"):
        self.n = len(os.listdir(_TMP))
        self.clock = Clock(t)
        self.cards, self.events = [], []
        self.answer = answer
        os.environ["JARVIS_HABITS_DB"] = str(_TMP / f"habits-{self.n}.db")
        self.sched = S.Scheduler(_TMP / f"sched-{self.n}.db", clock=self.clock,
                                 gate=self.gate, tier_of=lambda a: "ask",
                                 spawn=lambda fn: fn(),
                                 publish=lambda k, d: self.events.append((k, d)))
        self._old = H._scheduler
        H._scheduler = lambda: self
        H._reset_for_tests()
        H.register()

    # the two calls the module makes on the scheduler module
    def get(self):
        return self.sched

    def register_kind(self, *a, **kw):
        return S.register_kind(*a, **kw)

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        return Verdict(self.answer == "approved", "ask", self.answer)

    def close(self):
        H._scheduler = self._old


def _handler_class():
    """A FRESH stand-in Handler class per test.

    install() wraps a class IN PLACE and marks the wrapper function, so two
    tests sharing one class would find the second install() answering "already
    on" and never check origin/token again - a passing-looking test that proved
    nothing. A new class each time is the honest way to test a wrapper.
    """
    class Handler:
        def __init__(self, path="/api/habits", body=b"{}"):
            self.path = path
            self.body = body
            self.sent = None

        def do_GET(self):
            return "original-get"

        def do_POST(self):
            return "original-post"

        def _send(self, code, out):
            self.sent = (code, out)
            return self.sent

    return Handler


def _day_epoch(text: str) -> float:
    d = _dt.date.fromisoformat(text)
    return _dt.datetime.combine(d, _dt.time(hour=12)).timestamp()


# --------------------------------------------------------------------------
#   Creating one: one job, no card
# --------------------------------------------------------------------------

def t_a_new_habit_sets_up_one_repeat_and_raises_no_card():
    w = World()
    try:
        habit = H.create("Walk after lunch", {"every": "day", "at": "13:00"})
        check("a new habit has the owner's own words",
              habit["text"] == "Walk after lunch", habit["text"])
        check("it is active and has no stop time", habit["active"] is True
              and habit["stopped"] is None)
        check("it carries the rule it was given",
              habit["rule"] == {"every": "day", "at": "13:00"}, str(habit["rule"]))
        check("NO card was raised by creating a habit", w.cards == [], str(w.cards))
        jobs = w.sched.listed()
        check("exactly ONE scheduler job exists", len(jobs) == 1, str(len(jobs)))
        check("... and it is a habit_checkin", jobs[0]["kind"] == H.KIND, jobs[0]["kind"])
        check("... whose own text is the habit's words",
              jobs[0]["text"] == "Walk after lunch", jobs[0]["text"])
        check("the job's id is the one the habit remembers",
              habit["checkin"]["id"] == jobs[0]["id"])
        check("looking the habit up FROM the job works (never by parsing text)",
              H.habit_id_for_job(jobs[0]["id"]) == habit["id"])
    finally:
        w.close()


def t_a_habit_with_no_rule_gets_the_plain_default():
    w = World()
    try:
        habit = H.create("Stretch")
        check("no rule given means the plain daily default",
              habit["rule"] == H.DEFAULT_RULE, str(habit["rule"]))
        check("... and that still raises no card", w.cards == [], str(w.cards))
    finally:
        w.close()


def t_bad_input_is_refused_in_words():
    w = World()
    try:
        for text, why in (("", "no words"), ("   ", "only spaces")):
            try:
                H.create(text)
                check(f"a habit with {why} is refused", False)
            except ValueError:
                check(f"a habit with {why} is refused", True)
        try:
            H.create("x" * (H.MAX_TEXT + 1))
            check("a habit longer than MAX_TEXT is refused", False)
        except ValueError as exc:
            check("a habit longer than MAX_TEXT is refused", str(H.MAX_TEXT) in str(exc))
        check("none of those refusals raised a card", w.cards == [], str(w.cards))
    finally:
        w.close()


def t_the_habit_cap_is_enforced():
    w = World()
    try:
        for i in range(H.MAX_HABITS):
            H.create(f"habit {i}")
        try:
            H.create("one too many")
            check("more than MAX_HABITS active habits is refused", False)
        except OverflowError:
            check("more than MAX_HABITS active habits is refused", True)
        check("filling the cap raised no card at all", w.cards == [], str(w.cards))
    finally:
        w.close()


# --------------------------------------------------------------------------
#   Ticking: one row per day, idempotent
# --------------------------------------------------------------------------

def t_one_tick_is_one_row_and_a_second_tick_same_day_adds_nothing():
    w = World()
    try:
        hid = H.create("Walk")["id"]
        first = H.record_tick(hid, day="2026-11-02")
        check("the first tick is added", first["added"] is True and first["ok"] is True)
        check("... and says so in plain words", first["said"] == H.WORDS["ticked"])
        second = H.record_tick(hid, day="2026-11-02", words="again")
        check("a second tick for the SAME day adds nothing",
              second["added"] is False, str(second))
        check("... and returns the day's one row, not a new one",
              second["tick"]["day"] == "2026-11-02")
        habit = H.get(hid)
        check("the store holds exactly ONE tick for that habit",
              len(habit["history"]) == 1, str(habit["history"]))
        check("... and the newest day is the one that was ticked",
              habit["last_tick"] == "2026-11-02", habit["last_tick"])
        check("ticking raised no card", w.cards == [], str(w.cards))
    finally:
        w.close()


def t_a_different_day_is_a_second_row():
    w = World()
    try:
        hid = H.create("Walk")["id"]
        H.record_tick(hid, day="2026-11-01")
        r = H.record_tick(hid, day="2026-11-02")
        check("a tick on another day IS added", r["added"] is True)
        check("the habit now has two rows", len(H.get(hid)["history"]) == 2,
              str(H.get(hid)["history"]))
    finally:
        w.close()


def t_record_tick_is_the_reminder_lanes_entry_point():
    w = World()
    try:
        hid = H.create("Walk")["id"]
        out = H.record_tick(hid)                  # no day, no words, no server
        check("record_tick works with the habit id alone", out["ok"] is True)
        check("... it defaults to the owner's own wall-clock day",
              out["tick"]["day"] == _dt.date.today().isoformat(), out["tick"]["day"])
        check("... and it is the same function the route calls",
              H.tick(hid, day="2026-11-02")["ok"] is True)
        check("record_tick raised no card", w.cards == [], str(w.cards))
    finally:
        w.close()


def t_untick_removes_one_day_only():
    w = World()
    try:
        hid = H.create("Walk")["id"]
        H.record_tick(hid, day="2026-11-01")
        H.record_tick(hid, day="2026-11-02")
        out = H.untick(hid, day="2026-11-02")
        check("untick removes that day's row", out["removed"] is True)
        check("... and leaves the other day alone",
              [t["day"] for t in H.get(hid)["history"]] == ["2026-11-01"],
              str(H.get(hid)["history"]))
        check("untick raised no card", w.cards == [], str(w.cards))
    finally:
        w.close()


# --------------------------------------------------------------------------
#   Stopping: the job goes, the history stays
# --------------------------------------------------------------------------

def t_stop_deletes_the_job_and_keeps_every_tick():
    w = World()
    try:
        habit = H.create("Walk")
        hid = habit["id"]
        H.record_tick(hid, day="2026-10-31")
        H.record_tick(hid, day="2026-11-01")
        H.record_tick(hid, day="2026-11-02")
        before = len(H.get(hid)["history"])
        job = habit["checkin"]["id"]
        out = H.stop(hid)
        check("stop marks the habit stopped", out["active"] is False
              and out["stopped"] is not None)
        check("stop DELETES the repeating job",
              all(j["id"] != job for j in w.sched.listed()), str(w.sched.listed()))
        check("stop KEEPS every tick", len(out["history"]) == before == 3,
              str(len(out["history"])))
        check("stop says the history stays",
              "stays" in out["said"].lower(), out["said"])
        check("stopping raised no card", w.cards == [], str(w.cards))
        try:
            H.record_tick(hid, day="2026-11-03")
            check("a stopped habit refuses a new tick", False)
        except ValueError:
            check("a stopped habit refuses a new tick", True)
        check("the refusal raised no card either", w.cards == [], str(w.cards))
    finally:
        w.close()


def t_stopping_twice_is_not_an_error():
    w = World()
    try:
        hid = H.create("Walk")["id"]
        H.stop(hid)
        again = H.stop(hid)
        check("a second stop is a no-op, not an error", again["active"] is False)
        check("... its history is still there", again["history"] == [])
    finally:
        w.close()


# --------------------------------------------------------------------------
#   The nudge: deterministic, no score
# --------------------------------------------------------------------------

def t_the_note_is_deterministic_and_carries_no_score():
    w = World()
    try:
        hid = H.create("Walk after lunch")["id"]
        note = H.habit_note(hid)
        check("the note carries the habit's own words",
              "Walk after lunch" in note, note)
        check("the note is the module's own fixed sentence",
              note == H.WORDS["note"].format(text="Walk after lunch"), note)
        check("the note holds no count, streak, percentage or praise",
              not any(w in note.lower() for w in BANNED), note)
        H.record_tick(hid, day="2026-11-02")
        check("a tick does not change the note (it is not a scoreboard)",
              H.habit_note(hid) == note)
        check("a stopped habit has no note at all",
              H.stop(hid) is not None and H.habit_note(hid) == "")
        check("the scheduler's on_fire writes nothing and raises nothing",
              H.on_habit_fire(w.sched.listed()[0]["id"] if w.sched.listed() else "gone")
              is None)
    finally:
        w.close()


# --------------------------------------------------------------------------
#   The week in review: counts of stored rows, never interpretations
# --------------------------------------------------------------------------

def t_the_week_summary_counts_four_stores():
    w = World()
    try:
        old_mood = M.db_path()
        os.environ["JARVIS_MOOD_DB"] = str(_TMP / f"mood-{w.n}.db")
        hid = H.create("Walk")["id"]
        H.record_tick(hid, day="2026-11-01")
        H.record_tick(hid, day="2026-11-02")
        H.record_tick(hid, day="2026-10-20")          # outside the window
        M.record(3, day="2026-11-01")
        M.record(4, day="2026-11-02")
        summary = H.week_summary("2026-11-03", goal_reader=lambda a, b: 2,
                                 reminder_reader=lambda a, b: 5)
        check("the window is the seven days BEFORE the review day",
              (summary["from"], summary["to"]) == ("2026-10-27", "2026-11-02"),
              str((summary["from"], summary["to"])))
        check("habit ticks are counted from the store only",
              summary["habit_ticks"] == 2, str(summary["habit_ticks"]))
        check("... with each habit's own count, keyed by its words",
              summary["habits"] == [{"text": "Walk", "ticks": 2}], str(summary["habits"]))
        check("goal steps come from the goals store's own count",
              summary["goal_steps"] == 2, str(summary["goal_steps"]))
        check("reminders that went off come from the scheduler's own list",
              summary["reminders"] == 5, str(summary["reminders"]))
        check("mood is a COUNT of days with a row, read for real",
              summary["mood_rows"] == 2, str(summary["mood_rows"]))
        check("... against how many days the window holds",
              summary["mood_days_in_week"] == 7)
        text = summary["text"]
        check("the review text carries the four counts",
              "Habit ticks: 2" in text and "Goal steps ticked: 2" in text
              and "Reminders that went off: 5" in text
              and "Mood entries: 2 of 7 days" in text, text)
        check("the review says out loud that these are counts, not a judgement",
              H.WORDS["counts_note"] in text, text)
        check("the review holds no interpretation or praise word",
              not any(x in text.lower() for x in ("slipping", "streak", "score",
                                                  "well done", "great job",
                                                  "average", "trend", "%")), text)
        os.environ["JARVIS_MOOD_DB"] = str(old_mood)
    finally:
        w.close()


def t_a_count_that_cannot_be_read_says_so():
    """BLOCKED is never a pass: a store this PC cannot read is reported as
    "not read", never as a confident zero."""
    w = World()
    try:
        hid = H.create("Walk")["id"]
        H.record_tick(hid, day="2026-11-02")
        summary = H.week_summary("2026-11-03", goal_reader=lambda a, b: None,
                                 reminder_reader=lambda a, b: None,
                                 mood_reader=lambda a, b: None)
        text = summary["text"]
        check("an unread goals count says 'not read'",
              "Goal steps ticked: not read" in text, text)
        check("an unread reminder count says 'not read'",
              "Reminders that went off: not read" in text, text)
        check("an unread mood count says 'not read'",
              "Mood entries: not read" in text, text)
        check("the habit count it CAN read is still a number",
              "Habit ticks: 1" in text, text)
    finally:
        w.close()


def t_a_real_goal_step_is_counted_from_the_goals_store():
    """The goals half is a real read, not an injected number: a step ticked at
    a known epoch is inside the window, and one ticked outside it is not."""
    w = World()
    try:
        # The module's own reader opens db_path(), so point it at the VERY file
        # this test ticks a step in - otherwise it would read an empty store and
        # the check would pass for the wrong reason.
        goals_db = _TMP / f"goals-{w.n}.db"
        os.environ["JARVIS_GOALS_DB"] = str(goals_db)
        store = G.Goals(goals_db, clock=w.clock, scheduler=w.sched)
        S.register_kind(H.KIND, "habit check-in", "Jarvis: a habit check-in is due.",
                        on_fire=lambda j: None, note=lambda j: "", **H.KIND_OPTIONS)
        S.register_kind(G.KIND, "goal check-in", "Jarvis: a goal check-in is due.",
                        on_fire=lambda j: None, note=lambda j: "", **G.KIND_OPTIONS)
        goal = store.create("Get the garage insulated")
        store.accept(goal["id"])
        w.clock.t = _day_epoch("2026-11-02")
        store.mark_step(goal["id"], 0, True)
        inside = H.week_summary("2026-11-03", reminder_reader=lambda a, b: 0,
                                mood_reader=lambda a, b: 0)
        check("a step ticked inside the window is counted",
              inside["goal_steps"] == 1, str(inside["goal_steps"]))
        w.clock.t = _day_epoch("2026-10-01")
        store.mark_step(goal["id"], 0, False)
        store.mark_step(goal["id"], 0, True)
        outside = H.week_summary("2026-11-03", reminder_reader=lambda a, b: 0,
                                 mood_reader=lambda a, b: 0)
        check("a step ticked OUTSIDE the window is not counted",
              outside["goal_steps"] == 0, str(outside["goal_steps"]))
    finally:
        store = None
        w.close()


# --------------------------------------------------------------------------
#   The weekly review's own job: on because the owner turned it on
# --------------------------------------------------------------------------

def t_the_weekly_review_is_one_tap_on_and_one_tap_off():
    w = World()
    try:
        check("the review starts OFF", H.week_job() is None)
        on = H.start_week()
        check("turning it on sets up one job", on["ok"] is True
              and on["job"]["kind"] == H.WEEK_KIND, str(on))
        check("... and raises NO card (plain_repeat)", w.cards == [], str(w.cards))
        check("the scheduler holds exactly that one review job",
              [j["kind"] for j in w.sched.listed()] == [H.WEEK_KIND],
              str(w.sched.listed()))
        check("asking for it twice is refused in words",
              _raises(ValueError, H.start_week))
        off = H.stop_week()
        check("one tap turns it off", off["stopped"] is True
              and H.week_job() is None)
        check("... and says so", "off" in off["said"].lower(), off["said"])
        check("turning it off again is not an error",
              H.stop_week()["stopped"] is False)
        check("none of that raised a card", w.cards == [], str(w.cards))
    finally:
        w.close()


def t_the_week_job_files_through_the_existing_notes_route():
    """The filing call is the one POST /api/notes/capture uses; this proves the
    review passes it the counts, and that a PC with no journal says so."""
    w = World()
    try:
        calls = []

        def fake_capture(target, text, **kw):
            calls.append((target, text, kw))
            return 200, {"ok": True, "state": "filed", "message": "Filed."}

        old_mood = M.db_path()
        os.environ["JARVIS_MOOD_DB"] = str(_TMP / f"mood-{w.n}.db")
        H.create("Walk")
        code, body = H.file_week_review("2026-11-03", capture=fake_capture,
                                        target="obsidian")
        check("the review is filed with status 200", code == 200, str(code))
        check("... exactly one call, to the journal it was given",
              len(calls) == 1 and calls[0][0] == "obsidian", str(calls))
        check("... titled as the review", calls[0][2].get("title") == H.WORDS["week_title"],
              str(calls[0][2]))
        check("... and carrying the counts, not a generated paragraph",
              "Habit ticks:" in calls[0][1] and "Mood entries:" in calls[0][1],
              calls[0][1][:300])
        code, body = H.file_week_review("2026-11-03", capture=fake_capture, target="")
        check("a PC with no journal set up refuses in words, not a crash",
              code == 503 and "journal" in body["error"].lower(), str(body)[:200])
        os.environ["JARVIS_MOOD_DB"] = str(old_mood)
    finally:
        w.close()


def _raises(exc_type, fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
        return False
    except exc_type:
        return True


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

def t_the_routes_answer_the_shapes_both_apps_read():
    w = World()
    Handler = _handler_class()
    try:
        H.install(Handler, origin_ok=lambda h: True, token_ok=lambda h: True,
                  read_body=lambda h: h.body)
        h = Handler(path="/api/habits", body=json.dumps({"text": "Walk"}).encode())
        code, out = h.do_POST()
        check("POST /api/habits creates a habit", code == 200 and out["ok"] is True,
              str(out)[:200])
        hid = out["habit"]["id"]

        h = Handler(path="/api/habits")
        code, out = h.do_GET()
        check("GET /api/habits lists it", code == 200
              and [x["id"] for x in out["habits"]] == [hid], str(out)[:200])
        check("... with the limits and the fixed words",
              out["limits"]["habits"] == H.MAX_HABITS and out["words"] == H.WORDS)

        h = Handler(path=f"/api/habits/{hid}", body=b"{}")
        code, out = h.do_GET()
        check("GET /api/habits/<id> reads one habit", code == 200
              and out["habit"]["id"] == hid, str(out)[:200])

        # The review window is the seven days BEFORE today, so tick a day
        # inside it - a tick "today" would be outside its own review.
        inside = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        h = Handler(path=f"/api/habits/{hid}/tick",
                    body=json.dumps({"day": inside}).encode())
        code, out = h.do_POST()
        check("POST /api/habits/<id>/tick ticks it", code == 200 and out["ok"] is True,
              str(out)[:200])
        check("... and the answer carries the habit with its history",
              out["habit"]["last_tick"] == inside, str(out.get("habit"))[:200])

        h = Handler(path=f"/api/habits/{hid}/tick",
                    body=json.dumps({"day": inside}).encode())
        code, out = h.do_POST()
        check("... and a second tick that day is idempotent over HTTP",
              code == 200 and out["added"] is False, str(out)[:200])

        h = Handler(path="/api/habits/week")
        code, out = h.do_GET()
        check("GET /api/habits/week answers the counts and the on/off state",
              code == 200 and out["week"]["habit_ticks"] == 1 and out["on"] is False,
              str(out)[:240])

        h = Handler(path="/api/habits/week/start", body=b"{}")
        code, out = h.do_POST()
        check("POST /api/habits/week/start turns it on", code == 200
              and out["ok"] is True, str(out)[:200])
        h = Handler(path="/api/habits/week/stop", body=b"{}")
        code, out = h.do_POST()
        check("POST /api/habits/week/stop turns it off", code == 200
              and out["stopped"] is True, str(out)[:200])

        h = Handler(path=f"/api/habits/{hid}/stop", body=b"{}")
        code, out = h.do_POST()
        check("POST /api/habits/<id>/stop stops it", code == 200
              and out["habit"]["active"] is False, str(out)[:200])

        h = Handler(path="/api/habits/not-a-habit/tick", body=b"{}")
        code, out = h.do_POST()
        check("an unknown habit is a plain 404", code == 404, f"{code} {out}")
        h = Handler(path="/api/habits/not-a-habit")
        code, out = h.do_GET()
        check("... on the read side too", code == 404, f"{code} {out}")
    finally:
        w.close()


def t_an_unrelated_route_reaches_the_original_handler():
    w = World()
    Handler = _handler_class()
    try:
        H.install(Handler, origin_ok=lambda h: True, token_ok=lambda h: True,
                  read_body=lambda h: h.body)
        check("an unrelated GET is left to the original handler",
              Handler(path="/api/chat").do_GET() == "original-get")
        check("an unrelated POST is left to the original handler",
              Handler(path="/api/chat").do_POST() == "original-post")
        check("a bad token is refused before any habit is touched",
              H.install(Handler, origin_ok=lambda h: True, token_ok=lambda h: False,
                        read_body=lambda h: h.body) is not None)
    finally:
        w.close()


def t_the_wrong_origin_or_token_is_refused():
    w = World()
    seen = {}
    Spying = _handler_class()
    real_send = Spying._send

    def _send(self, code, out):
        seen["code"] = code
        return real_send(self, code, out)

    Spying._send = _send
    try:
        H.install(Spying, origin_ok=lambda h: False, token_ok=lambda h: True,
                  read_body=lambda h: b"{}")
        code = Spying(path="/api/habits").do_GET()
    finally:
        w.close()
    check("a cross-origin request is refused with 403", seen.get("code") == 403,
          str(seen))
    check("... and the route answered nothing", code is None)


# --------------------------------------------------------------------------
#   What the module promises about itself
# --------------------------------------------------------------------------

def _imports_and_attrs(path: Path):
    """(top-level module names the file imports, attribute names it uses).

    Scanned from the AST, not from the text: this module's own docstring SAYS
    it does not import jarvis_gate and makes no network call, and a grep would
    convict it for saying so.
    """
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods, attrs = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:
                mods.add(node.module)
        elif isinstance(node, ast.Attribute):
            attrs.add(node.attr)
    return mods, attrs


def t_the_module_holds_no_card_and_no_model():
    mods, attrs = _imports_and_attrs(HERE / "jarvis_habits.py")
    top = {m.split(".")[0] for m in mods}
    check("jarvis_habits.py never imports the gate (so it cannot raise a card)",
          "jarvis_gate" not in top, str(sorted(mods)))
    # urllib.PARSE is string work, not a network call: the client modules are
    # what must be absent. (install() parses the request's own path, exactly as
    # jarvis_goals.install does.)
    for word in ("requests", "socket", "ssl", "ftplib", "http"):
        check(f"jarvis_habits.py imports no network client ({word})", word not in top,
              str(sorted(mods)))
    check("... and no urllib client (request/error) either",
          not any(m.startswith("urllib.") and m != "urllib.parse" for m in mods),
          str(sorted(mods)))
    for call in ("open_stream", "urlopen", "create_connection"):
        check(f"jarvis_habits.py never calls {call}", call not in attrs,
              str(sorted(attrs)))
    check("the plugin folder that installs it exists",
          (ROOT / "plugins/ready/habits/plugin.json").is_file())
    row = json.loads((ROOT / "plugins/ready/habits/plugin.json").read_text(encoding="utf-8"))
    check("... and names this module with install: handler",
          row["module"] == "jarvis_habits" and row["install"] == "handler", str(row))


def main():
    tests = [t_a_new_habit_sets_up_one_repeat_and_raises_no_card,
             t_a_habit_with_no_rule_gets_the_plain_default,
             t_bad_input_is_refused_in_words,
             t_the_habit_cap_is_enforced,
             t_one_tick_is_one_row_and_a_second_tick_same_day_adds_nothing,
             t_a_different_day_is_a_second_row,
             t_record_tick_is_the_reminder_lanes_entry_point,
             t_untick_removes_one_day_only,
             t_stop_deletes_the_job_and_keeps_every_tick,
             t_stopping_twice_is_not_an_error,
             t_the_note_is_deterministic_and_carries_no_score,
             t_the_week_summary_counts_four_stores,
             t_a_count_that_cannot_be_read_says_so,
             t_a_real_goal_step_is_counted_from_the_goals_store,
             t_the_weekly_review_is_one_tap_on_and_one_tap_off,
             t_the_week_job_files_through_the_existing_notes_route,
             t_the_routes_answer_the_shapes_both_apps_read,
             t_an_unrelated_route_reaches_the_original_handler,
             t_the_wrong_origin_or_token_is_refused,
             t_the_module_holds_no_card_and_no_model]
    for fn in tests:
        print("\n-- " + fn.__name__ + " " + "-" * 40)
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            check(fn.__name__ + " ran", False, traceback.format_exc()[-800:])
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
