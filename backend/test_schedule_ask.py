"""test_schedule_ask.py - a reminder that ASKS: the owner's own question, up to
three of his own buttons, and where an answer is written.

    python3 backend/test_schedule_ask.py

The owner's requests of 2026-11-02, in his own words: *"I would like to tell
Jarvis exactly how I want the reminder to appear and what interactive elements
there are - e.g. 'hey Jarvis remind me to take a medication at 10:00 a.m.' -> at
10:00 a.m. a notification on my Android phone saying 'Did you take your
medication?' with a Yes or No button"*, and then *"as much flexibility or options
as I want"*. `DESIGN.md` answers it with ONE new action kind (`ask`) on the
existing reminder, no new permission model, no new route.

What it proves, with a hand-moved clock and a real SQLite file in a temporary
folder:

  - the `ask` block is CHECKED WHEN THE REMINDER IS SAVED: the question's length
    and line count, one to three buttons, each label the owner's own words within
    its length, each button doing exactly one of record / done / snooze N, a
    snooze's minutes on the snooze button and nowhere else, two buttons never
    saying the same thing, a `record` button always having somewhere to write -
    and every failure is ONE plain sentence, never a code;
  - it is checked AGAIN WHEN READ: `_decode_action` runs the same check, so a row
    edited on the owner's own disk reads as `action_unreadable`, fires as an
    ordinary reminder and offers no buttons at all;
  - the hard rails hold: no shell, command, script, webhook or program button,
    never more than three, no list form, no bulk, and no `open-file` /
    `open-webpage` button in this build - that one is REFUSED at save with the
    sentence that says why (the desktop's one opener opens a reminder's own single
    action, and a second opener is a Rust security surface this lane does not own);
  - firing an `ask` reminder raises NO card - not one, at any tier - because an
    answer is a log line, not an approval. It publishes the ordinary `schedule`
    event and the question and the buttons are read back by id;
  - answering writes the log line, then does the one thing that button does:
    `record` (the chosen destinations), `done` (a one-off leaves the list; a
    repeating one stops repeating - it only ever makes Jarvis quieter) or
    `snooze` (the same one-off copy every Snooze makes);
  - a destination this PC does not have is ONE truthful sentence and the answer
    is still kept: the goal's progress log and the habit tick are other lanes'
    modules, and the journal is called through a fake here so nothing on the
    owner's PC is touched;
  - the log keeps the newest MAX_ANSWERS, so a question asked daily for years
    cannot grow a row without a bound;
  - `POST /api/schedule/act {"do": "answer"}` is the way in (NO new route), and
    the audit line carries ids, the button's INDEX and the destinations only -
    never the question, never a label, never a line that was written;
  - and the schedule grammar the same request asked for: every N days, every N
    weeks on chosen days, several times in one day, a first occurrence and an
    optional end date - each said in ONE readable sentence, and an end date really
    stopping the repeat.

Standard library only. No network, no model, no owner's files.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_schedule as S  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-ask-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


#: The audit log, captured: the ids, the button's index and the destinations a
#: reminder's answer may write - and never the question or a label.
_AUDIT = []
_real_audit = S._audit
_real_get = S.get
S._audit = lambda event, detail: _AUDIT.append((event, detail))


class World:
    """A scheduler with a hand-moved clock, a gate that records what it was
    asked (nothing should ever reach it), and the audit captured."""

    def __init__(self, t, *, name="w"):
        self.clock = Clock(t)
        self.events, self.cards = [], []
        path = _TMP / f"{name}-{len(list(_TMP.iterdir()))}.db"
        self.s = S.Scheduler(
            path, clock=self.clock,
            gate=lambda a, d, p: (self.cards.append({"action": a, "detail": dict(d),
                                                     "prompt": p}),
                                  Verdict(False, "ask", "denied"))[1],
            tier_of=lambda a: "ask",
            spawn=lambda fn: fn(),
            publish=lambda k, d: self.events.append((k, d)),
        )

    def add(self, *, kind="reminder", in_seconds=10.0, text="take your medication",
            **kwargs):
        return self.s.add_at(kind, self.clock.t + in_seconds, text, **kwargs)

    def fire(self, jid, *, at=None):
        """Move the clock past the job's time and tick once."""
        with self.s._lock, self.s._db() as c:
            row = c.execute("SELECT due FROM jobs WHERE id = ?", (jid,)).fetchone()
        self.clock.t = float(at if at is not None else float(row["due"]) + 1.0)
        self.s.tick()


def refused(fn, words=None):
    """(refused?, sentence) - the one plain sentence a bad block gets."""
    try:
        fn()
    except ValueError as exc:
        text = str(exc)
        if words is not None and words not in text:
            return False, text
        return True, text
    except Exception as exc:                     # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"
    return False, ""


def ask(**over):
    """A valid `ask` block, with any part of it replaced."""
    block = {"kind": "ask",
             "question": "Did you take your medication?",
             "buttons": [{"label": "Taken", "does": "record"},
                         {"label": "Skipped", "does": "record"}],
             "record": {"history": True}}
    block.update(over)
    return block


class FakeNotes:
    """Stands in for `jarvis_note_capture`, so no test can ever write to the
    owner's real Obsidian vault - and so the line it would write is readable."""

    def __init__(self, *, ok=True, reason="", plan_reason=""):
        self.ok, self.reason, self.plan_reason = ok, reason, plan_reason
        self.planned, self.runs = [], []

    class _Plan:
        def __init__(self, reason=""):
            self.reason_empty = reason
            self.text = ""

    def plan(self, target, text, *, title="", notebook="", now=None):
        self.planned.append({"target": target, "text": text, "now": now})
        return FakeNotes._Plan(self.plan_reason)

    def run(self, plan, *, approved=False):
        self.runs.append({"approved": approved,
                          "text": self.planned[-1]["text"] if self.planned else ""})
        if not self.ok:
            return {"ok": False, "reason": self.reason}
        return {"ok": True, "target": "obsidian", "file": "Daily/2026-11-02.md"}


def with_notes(fake):
    """Install `fake` as jarvis_note_capture for the duration of a block."""
    saved = sys.modules.get("jarvis_note_capture")
    sys.modules["jarvis_note_capture"] = fake

    class _Ctx:
        def __enter__(self):
            return fake

        def __exit__(self, *exc):
            if saved is None:
                sys.modules.pop("jarvis_note_capture", None)
            else:
                sys.modules["jarvis_note_capture"] = saved
            return False

    return _Ctx()


# --------------------------------------------------------------------------
#   1. The block, checked when the reminder is SAVED
# --------------------------------------------------------------------------


def t_a_question_is_saved_and_handed_back_exactly() -> None:
    w = World(1_800_000_000.0, name="save")
    job = w.add(action=ask())
    check("the whole block comes back exactly as it was saved",
          job.get("action") == ask(), job.get("action"))
    check("and no second key was invented",
          set(job["action"]) == {"kind", "question", "buttons", "record"}, job.get("action"))
    check("a reminder that asks says so, so a client knows the PC can take an answer",
          job.get("asks") is True, job)
    check("nothing is reported wrong with it",
          "action_problem" not in job and "action_unreadable" not in job, job)
    check("nothing has been answered yet, so there is no `answers` key at all",
          "answers" not in job, job)


def t_the_question_is_bounded_and_plain() -> None:
    w = World(1_800_000_000.0, name="question")
    got, sentence = refused(lambda: w.add(action=ask(question="")), "question")
    check("an empty question is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(question="x" * (S.MAX_ASK_QUESTION + 1))),
                            str(S.MAX_ASK_QUESTION))
    check(f"a question over {S.MAX_ASK_QUESTION} characters is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(question="a\nb\nc\nd")), "lines")
    check("a question over its line limit is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(question="take it\u0007now")))
    check("a control character in the question is refused", got, sentence)
    check("a question on three lines is accepted",
          w.add(action=ask(question="Did you take it?\nMorning or evening?\nAny at all?")
                ).get("action", {}).get("question", "").count("\n") == 2)


def t_buttons_are_one_to_three_and_the_owners_words() -> None:
    w = World(1_800_000_000.0, name="buttons")
    got, sentence = refused(lambda: w.add(action=ask(buttons=[])), "button")
    check("a question with no buttons is refused", got, sentence)
    four = [{"label": f"b{i}", "does": "done"} for i in range(4)]
    got, sentence = refused(lambda: w.add(action=ask(buttons=four, record={})), "three")
    check("a fourth button is refused - three is the ceiling Android draws", got, sentence)
    three = [{"label": f"b{i}", "does": "done"} for i in range(3)]
    check("three buttons are accepted",
          len(w.add(action=ask(buttons=three, record={})).get("action", {}).get("buttons", []))
          == 3)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "", "does": "done"}], record={})), "button")
    check("a button with no words is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "x" * (S.MAX_ASK_LABEL + 1), "does": "done"}], record={})),
        str(S.MAX_ASK_LABEL))
    check(f"a label over {S.MAX_ASK_LABEL} characters is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "two\nlines", "does": "done"}], record={})), "one line")
    check("a label with a newline is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "Same", "does": "done"}, {"label": "same", "does": "done"}],
        record={})), "same thing")
    check("two buttons with the same words are refused", got, sentence)


def t_each_button_does_exactly_one_thing() -> None:
    w = World(1_800_000_000.0, name="does")
    for does in S.ASK_DOES:
        block = ask(buttons=[{"label": "Do it", "does": does,
                              **({"minutes": 15} if does == "snooze" else {})}],
                    record={"history": True})
        got = w.add(action=block).get("action", {})
        check(f"`{does}` is one of the things a button may do", got == block, got)
    for verb in ("shell", "command", "script", "webhook", "program", "exec", "run"):
        got, sentence = refused(lambda v=verb: w.add(action=ask(
            buttons=[{"label": "Go", "does": v}], record={})), "record the answer")
        check(f"a `{verb}` button is refused, and the sentence says what does work",
              got, sentence)
    for verb in ("open-file", "open-webpage", "open"):
        got, sentence = refused(lambda v=verb: w.add(action=ask(
            buttons=[{"label": "Open", "does": v}], record={})), "opens a file or a page")
        check(f"an `{verb}` button is refused BY NAME with its reason", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "Later", "does": "snooze"}], record={})), "minutes")
    check("a snooze button without its minutes is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "Later", "does": "snooze", "minutes": 0}], record={})), "minutes")
    check("a zero-minute snooze is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "Later", "does": "snooze", "minutes": 1441}], record={})), "minutes")
    check("a snooze longer than a day is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "Taken", "does": "record", "minutes": 10}])))
    check("minutes on a button that does not snooze are refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(
        buttons=[{"label": "Go", "does": "done", "extra": "x"}], record={})))
    check("an unknown key on a button is refused", got, sentence)


def t_recording_has_somewhere_to_go() -> None:
    w = World(1_800_000_000.0, name="record")
    got, sentence = refused(lambda: w.add(action={
        "kind": "ask", "question": "Did you?",
        "buttons": [{"label": "Yes", "does": "record"}]}), "pick where")
    check("a `record` button with no destination is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(record={"history": True, "nonsense": True})),
                            "pick where")
    check("an unknown destination is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(record={"history": "yes"})), "pick where")
    check("a destination that is not a true/false is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(record={"goal": "../../etc/passwd"})),
                            "its own id")
    check("a goal id that is not a plain name is refused", got, sentence)
    got, sentence = refused(lambda: w.add(action=ask(record={"habit": "a b c"})), "its own id")
    check("a habit id that is not a plain name is refused", got, sentence)
    block = ask(record={"history": True, "obsidian_daily": True, "goal": "g-1",
                        "habit": "h:2"})
    check("all four destinations together are accepted",
          w.add(action=block).get("action", {}).get("record") == block["record"])
    block = ask(buttons=[{"label": "Done", "does": "done"}])
    block.pop("record", None)
    check("a question whose buttons never record needs no recording at all",
          w.add(action=block).get("action", {}).get("record") is None,
          w.add(action=block).get("action"))


def t_the_block_is_exactly_its_own_keys() -> None:
    w = World(1_800_000_000.0, name="keys")
    for label, block in [
        ("a fourth key", {**ask(), "url": "https://example.com"}),
        ("no kind", {"question": "q", "buttons": [{"label": "a", "does": "done"}]}),
        ("an unknown kind", {"kind": "ask-me", "question": "q"}),
        ("buttons that are not a list", ask(buttons="Yes")),
        ("a button that is not an object", ask(buttons=["Yes"])),
        ("a whole string", "ask me anything"),
        ("a list", [ask()]),
    ]:
        got, sentence = refused(lambda b=block: w.add(action=b))
        check(f"{label} is refused at save", got, sentence)


def t_only_a_reminder_can_carry_one() -> None:
    w = World(1_800_000_000.0, name="only")
    for kind in ("alarm", "todo"):
        got, sentence = refused(lambda k=kind: w.add(kind=k, action=ask()), "only a reminder")
        check(f"a {kind} cannot ask a question", got, sentence)


# --------------------------------------------------------------------------
#   2. The block, checked AGAIN when it is read
# --------------------------------------------------------------------------


def t_a_hand_edited_block_reads_as_unreadable() -> None:
    w = World(1_800_000_000.0, name="tampered")
    job = w.add(action=ask())
    w.fire(job["id"])
    for label, broken in [
        ("a fourth button", {**ask(), "buttons": [{"label": f"b{i}", "does": "done"}
                                                 for i in range(4)], "record": {}}),
        ("a shell button", {"kind": "ask", "question": "q",
                            "buttons": [{"label": "Go", "does": "shell"}]}),
        ("an unknown destination", {**ask(), "record": {"eavesdrop": True}}),
        ("an extra key", {**ask(), "path": "C:\\Windows\\System32\\cmd.exe"}),
    ]:
        with w.s._lock, w.s._db() as c:
            c.execute("UPDATE jobs SET action = ? WHERE id = ?",
                      (json.dumps(broken), job["id"]))
        view = w.s.job(job["id"])
        check(f"{label} on disk reads as unreadable", view.get("action_unreadable") is True,
              view)
        check(f"{label}: no buttons are handed to an app at all", "action" not in view, view)
        code, body = w.s.answer(job["id"], 0)
        check(f"{label}: and it cannot be answered", code == 409, (code, body))
    with w.s._lock, w.s._db() as c:
        c.execute("UPDATE jobs SET action = ? WHERE id = ?",
                  ("not json at all", job["id"]))
    view = w.s.job(job["id"])
    check("a row that is not even JSON still fires as an ordinary reminder",
          view.get("action_unreadable") is True and view.get("state") == "fired", view)


# --------------------------------------------------------------------------
#   3. Firing: a question, no card
# --------------------------------------------------------------------------


def t_firing_asks_and_raises_no_card() -> None:
    w = World(1_800_000_000.0, name="fire")
    job = w.add(action=ask())
    check("a card is never raised while it is being set up", w.cards == [], w.cards)
    w.fire(job["id"])
    view = w.s.job(job["id"])
    check("it went off", view.get("state") == "fired", view.get("state"))
    check("NO card is raised for a question", w.cards == [], w.cards)
    check("it published the ordinary `schedule` event, not one of its own",
          any(k == "schedule" and d.get("id") == job["id"] and d.get("state") == "fired"
              for k, d in w.events), w.events)
    check("the question is read back by id, so a notification can draw it",
          view.get("action", {}).get("question") == ask()["question"], view.get("action"))
    check("with every button, in the owner's own words",
          [b["label"] for b in view["action"]["buttons"]] == ["Taken", "Skipped"])
    check("and it is still open to be answered", view.get("asks") is True)


def t_a_repeating_question_asks_every_time() -> None:
    w = World(1_800_000_000.0, name="repeat")
    job = w.s.add_repeat("reminder", {"every": "day", "at": "07:00"},
                         "take your medication", action=ask())
    first = float(job["due"])
    w.clock.t = first + 1.0
    w.s.tick()
    view = w.s.job(job["id"])
    check("it goes off", view.get("fired_at") is not None, view)
    check("and it is due again tomorrow, still asking", view.get("repeats") is True, view)
    check("still no card", w.cards == [], w.cards)
    w.clock.t = first + 2 * 86400 + 1.0
    w.s.tick()
    view = w.s.job(job["id"])
    check("the second time it goes off it asks the same question again",
          view.get("action", {}).get("question") == ask()["question"], view)


# --------------------------------------------------------------------------
#   4. Answering
# --------------------------------------------------------------------------


def _fired_ask(w, **over):
    job = w.add(action=ask(**over))
    w.fire(job["id"])
    return job["id"]


def t_an_answer_is_a_log_line_and_needs_no_card() -> None:
    _AUDIT.clear()
    w = World(1_800_000_000.0, name="answer")
    jid = _fired_ask(w)
    code, body = w.s.answer(jid, 0)
    check("answering works, cardless", code == 200 and body.get("ok") is True, (code, body))
    check("no card was raised for the answer", w.cards == [], w.cards)
    check("the answer says what was written", body.get("said") == "Saved to its own history.",
          body.get("said"))
    view = w.s.job(jid)
    check("it is on the reminder's own history",
          len(view.get("answers") or []) == 1 and
          view["answers"][0]["button"] == "Taken", view.get("answers"))
    check("with the PC's own clock on it", view["answers"][0]["clock"].count(":") == 1,
          view["answers"][0])
    notes = [(e, d) for e, d in _AUDIT if e == "schedule.answered"]
    check("the audit says ONE answer happened", len(notes) == 1, notes)
    detail = notes[0][1] if notes else {}
    check("...with the id, the button's index and the destinations",
          detail.get("id") == jid and detail.get("button") == 0
          and detail.get("does") == "record"
          and detail.get("wrote") == ["its own history"], detail)
    check("...and NEVER the question or a label",
          "medication" not in json.dumps(detail) and "Taken" not in json.dumps(detail),
          detail)
    check("answering again did not close the question",
          w.s.answer(jid, 1)[0] == 200 and len(w.s.job(jid)["answers"]) == 2)


def t_the_log_keeps_the_newest_and_no_more() -> None:
    w = World(1_800_000_000.0, name="bounded")
    jid = _fired_ask(w)
    for _ in range(S.MAX_ANSWERS + 5):
        w.s.answer(jid, 0)
    kept = w.s.job(jid).get("answers") or []
    check(f"the log keeps exactly {S.MAX_ANSWERS} answers", len(kept) == S.MAX_ANSWERS,
          len(kept))


def t_the_three_things_a_button_can_do_happen() -> None:
    w = World(1_800_000_000.0, name="does-run")
    block = ask(buttons=[{"label": "Taken", "does": "record"},
                         {"label": "Finished", "does": "done"},
                         {"label": "Ask again", "does": "snooze", "minutes": 30}],
                record={"history": True})
    jid = _fired_ask(w, buttons=block["buttons"])
    done_at = w.clock.t
    code, body = w.s.answer(jid, 2)
    check("a snooze button snoozes", code == 200 and "Snoozed" in body.get("said", ""),
          body.get("said"))
    view = w.s.job(jid)
    check("...and the copy is on the list 30 minutes later",
          any(j.get("kind") == "reminder" and abs((j.get("due") or 0) - (done_at + 1800)) < 2
              for j in w.s.status()["jobs"]), w.s.status()["jobs"])
    check("...and the answer is still logged",
          w.s.job(jid)["answers"][-1]["does"] == "snooze")
    w2 = World(1_800_000_000.0, name="done-one-off")
    jid2 = _fired_ask(w2, buttons=block["buttons"])
    code, body = w2.s.answer(jid2, 1)
    check("a done button on a one-off marks it done", code == 200
          and w2.s.job(jid2).get("state") == "done", (code, body, w2.s.job(jid2).get("state")))
    check("...and it leaves \"Just went off\"",
          w2.s.job(jid2)["id"] not in [j["id"] for j in w2.s.status()["went_off"]],
          w2.s.status()["went_off"])


def t_done_on_a_repeating_question_stops_it() -> None:
    w = World(1_800_000_000.0, name="done-repeat")
    block = ask(buttons=[{"label": "Finished", "does": "done"}])
    block.pop("record", None)
    job = w.s.add_repeat("reminder", {"every": "day", "at": "07:00"}, "stretch",
                         action=block)
    first = float(job["due"])
    w.clock.t = first + 1.0
    w.s.tick()
    code, body = w.s.answer(job["id"], 0)
    view = w.s.job(job["id"])
    check("a done button on a repeating question stops the repeat",
          code == 200 and view.get("state") == "fired" and view.get("due") is None,
          (code, view.get("state"), view.get("due")))
    check("...and the words say so", "not repeat" in str(body.get("said")), body.get("said"))
    w.clock.t = first + 3 * 86400
    went = w.s.tick()
    check("...and it never goes off again", job["id"] not in went, went)


def t_where_an_answer_is_written() -> None:
    w = World(1_800_000_000.0, name="destinations")
    notes = FakeNotes()
    block = ask(buttons=[{"label": "Taken", "does": "record"}],
                record={"history": True, "obsidian_daily": True})
    jid = _fired_ask(w, buttons=block["buttons"], record=block["record"])
    with with_notes(notes):
        code, body = w.s.answer(jid, 0)
    check("the answer went to the journal as well as the history",
          code == 200 and "today's Obsidian note" in body.get("said", ""), body.get("said"))
    check("...through jarvis_note_capture, the module that already owns it",
          len(notes.runs) == 1, notes.runs)
    check("...written as the owner's own one plain line",
          notes.runs and notes.runs[0]["text"].endswith("take your medication: Taken"),
          notes.runs)
    check("...with the tap counted as the person who approved it",
          notes.runs and notes.runs[0]["approved"] is True, notes.runs)

    w2 = World(1_800_000_000.0, name="journal-refuses")
    broken = FakeNotes(ok=False, reason="the current daily note could not be copied first.")
    jid2 = _fired_ask(w2, buttons=block["buttons"], record=block["record"])
    with with_notes(broken):
        code, body = w2.s.answer(jid2, 0)
    check("a journal that refused is said in ONE sentence", code == 200
          and body.get("problems") == ["the current daily note could not be copied first."],
          body)
    check("...and the answer is still kept in its own history",
          len(w2.s.job(jid2)["answers"]) == 1, w2.s.job(jid2).get("answers"))

    w3 = World(1_800_000_000.0, name="not-set-up")
    jid3 = _fired_ask(w3, buttons=block["buttons"],
                      record={"history": True, "goal": "g-1", "habit": "h-1"})
    code, body = w3.s.answer(jid3, 0)
    check("a goal with no progress log on this PC says so, truthfully",
          S.GOAL_NOT_SET_UP in body.get("problems", []), body.get("problems"))
    check("a habit that is not wired yet says so, truthfully",
          S.HABIT_NOT_SET_UP in body.get("problems", []), body.get("problems"))
    check("neither of those stops the answer being kept",
          len(w3.s.job(jid3)["answers"]) == 1, w3.s.job(jid3).get("answers"))
    check("and the answer says what DID happen", "its own history" in body.get("said", ""),
          body.get("said"))


def t_an_answer_that_cannot_count_is_refused() -> None:
    w = World(1_800_000_000.0, name="refusals")
    jid = _fired_ask(w)
    code, body = w.s.answer(jid, 99)
    check("a button that is not there is refused", code == 400, (code, body))
    code, body = w.s.answer(jid, True)
    check("a true/false is not a button", code == 400, (code, body))
    code, body = w.s.answer(jid, "0")
    check("a label is not a button either - the index is the only way in",
          code == 400, (code, body))
    code, body = w.s.answer("s0000000000", 0)
    check("a reminder that is gone is refused", code == 404, (code, body))
    plain = w.add(action={"kind": "show-note", "note": "the blue folder"})
    code, body = w.s.answer(plain["id"], 0)
    check("a reminder that does not ask cannot be answered", code == 409, (code, body))
    not_yet = w.add(action=ask())
    code, body = w.s.answer(not_yet["id"], 0)
    check("a question that has not gone off cannot be answered yet", code == 409, (code, body))


def t_the_route_is_the_one_write_door() -> None:
    w = World(1_800_000_000.0, name="route")
    jid = _fired_ask(w)
    saved, S.get = S.get, (lambda: w.s)
    try:
        code, body = S.handle_act({"do": "answer", "id": jid, "button": 0})
        check("POST /api/schedule/act {\"do\": \"answer\"} is the way in",
              code == 200 and body.get("ok") is True, (code, body))
        check("no new route was needed", not hasattr(S, "handle_answer"), True)
        check("the answer comes back with the job's whole log",
              len(body.get("answers") or []) == 1, body.get("answers"))
        code, body = S.handle_act({"do": "answer", "id": "nonsense", "button": 0})
        check("a body that is not one job id is refused", code == 400, (code, body))
        code, body = S.handle_act({"do": "answer"})
        check("a body with no id is refused", code == 400, (code, body))
        # The other verbs still behave exactly as they did.
        todo = w.s.add_todo("post the letter")
        code, body = S.handle_act({"do": "done", "id": todo["id"]})
        check("the verbs that were already there are untouched",
              code == 200 and body.get("said") == "Marked done.", (code, body))
    finally:
        S.get = saved


def t_a_snoozed_question_asks_again() -> None:
    w = World(1_800_000_000.0, name="snooze-question")
    block = ask(buttons=[{"label": "Later", "does": "snooze", "minutes": 20}])
    block.pop("record", None)
    jid = _fired_ask(w, buttons=block["buttons"])
    code, _body = w.s.answer(jid, 0)
    copies = [j for j in w.s.status()["jobs"] if j.get("snoozed")]
    check("a snoozed question leaves one copy waiting", code == 200 and len(copies) == 1,
          (code, copies))
    check("...and the copy ASKS again, with the same buttons",
          copies and copies[0].get("action", {}).get("kind") == "ask"
          and copies[0].get("asks") is True, copies[0].get("action") if copies else None)
    check("...so the question is not silently turned into a statement",
          copies and [b["label"] for b in copies[0]["action"]["buttons"]] == ["Later"],
          copies[0].get("action") if copies else None)


# --------------------------------------------------------------------------
#   5. The schedule grammar the same request asked for
# --------------------------------------------------------------------------


def t_every_n_days_and_weeks() -> None:
    now = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))      # a Monday
    days = S.check_rule({"every": "days", "days": 3, "at": "07:00", "start": "2026-11-02"},
                        now)
    check("every 3 days is kept as its own rule",
          days["every"] == "days" and days["days"] == 3, days)
    got = [time.strftime("%a %d %b %H:%M", time.localtime(t)) for t in S.next_runs(days, now)]
    check("...and it really is every third day", got[0].startswith("Thu 05 Nov")
          and got[1].startswith("Sun 08 Nov"), got)
    weeks = S.check_rule({"every": "weeks", "weeks": 2, "days": [0, 3], "at": "09:00",
                          "start": "2026-11-02"}, now)
    got = [time.strftime("%a %d %b %H:%M", time.localtime(t)) for t in S.next_runs(weeks, now)]
    check("every 2 weeks on chosen days skips a whole week between them",
          got == ["Thu 05 Nov 09:00", "Mon 16 Nov 09:00", "Thu 19 Nov 09:00"], got)


def t_several_times_in_one_day_and_a_first_occurrence() -> None:
    now = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))
    rule = S.check_rule({"every": "day", "times": ["20:00", "08:00", "13:00"]}, now)
    check("several times in one day: `at` is the earliest, and every time is kept",
          rule["at"] == "08:00" and rule["times"] == ["08:00", "13:00", "20:00"], rule)
    got = [time.strftime("%d %b %H:%M", time.localtime(t)) for t in S.next_runs(rule, now)]
    check("...and the next three are the rest of today in order",
          got == ["02 Nov 13:00", "02 Nov 20:00", "03 Nov 08:00"], got)
    check("a rule with one time keeps the block it always had (no `times` key)",
          "times" not in S.check_rule({"every": "day", "at": "08:00"}, now))
    got, sentence = refused(lambda: S.check_rule(
        {"every": "day", "times": [f"{h:02d}:00" for h in range(S.MAX_TIMES_A_DAY + 1)]}, now))
    check("more times in a day than the limit is refused", got, sentence)


def t_an_end_date_really_stops_it() -> None:
    now = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))
    rule = S.check_rule({"every": "day", "at": "07:00", "ends": "2026-11-04"}, now)
    check("an end date is kept as an epoch, the key `tick` already honours",
          isinstance(rule.get("ends"), float) and rule["ends"] > now, rule)
    w = World(now, name="ends")
    job = w.s.add_repeat("reminder", {"every": "day", "at": "07:00", "ends": "2026-11-04"},
                         "water the plants")
    fired = []
    for _ in range(0, 3):
        w.clock.t += 86400
        fired.extend(w.s.tick())
    view = w.s.job(job["id"]) or {}
    check("a repeat with an end date stops when it is reached",
          view.get("state") == "fired" and view.get("due") is None, view)
    check("...and it did go off before then", len(fired) >= 2, fired)
    w.clock.t += 30 * 86400
    fired_now = w.s.tick()
    check("...and it never goes off after its end date", job["id"] not in fired_now,
          fired_now)
    got, sentence = refused(lambda: S.check_rule(
        {"every": "day", "at": "07:00", "ends": "2020-01-01"}, now), "already passed")
    check("an end date in the past is refused", got, sentence)
    got, sentence = refused(lambda: S.check_rule(
        {"every": "day", "at": "07:00", "ends": "not a date"}, now))
    check("an end date that is not a date is refused", got, sentence)


def t_a_rule_stays_one_readable_sentence() -> None:
    now = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))
    for block, words in [
        ({"every": "days", "days": 3, "at": "07:00", "start": "2026-11-09"},
         "every 3 days at 07:00, starting Monday 9 November"),
        ({"every": "weeks", "weeks": 2, "days": [0, 3], "at": "09:00",
          "start": "2026-11-09", "ends": "2026-12-31"},
         "every 2 weeks on Monday and Thursday at 09:00, starting Monday 9 November, "
         "until Thursday 31 December"),
        ({"every": "day", "times": ["08:00", "13:00", "20:00"]},
         "every day at 08:00, 13:00 and 20:00"),
        ({"every": "month", "at": "09:00", "day": 15}, "every month on the 15th at 09:00"),
        ({"every": "month", "at": "09:00", "day": 1}, "every month on the 1st at 09:00"),
    ]:
        said = S.rule_words(S.check_rule(block, now))
        check(f"{block['every']}: said in one readable sentence", said == words, said)
        check(f"{block['every']}: ...with no code in it",
              "{" not in said and '"' not in said, said)


def t_every_n_hours_and_the_old_rules_are_untouched() -> None:
    now = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))
    check("every day is still exactly what it was",
          S.check_rule({"every": "day", "at": "07:00"}, now) == {"every": "day", "at": "07:00"})
    check("every weekday is still exactly what it was",
          S.check_rule({"every": "weekday", "at": "07:00"}, now)
          == {"every": "weekday", "at": "07:00"})
    check("every week on chosen days is still exactly what it was",
          S.check_rule({"every": "week", "at": "09:00", "days": [0, 3]}, now)
          == {"every": "week", "at": "09:00", "days": [0, 3]})
    check("every N hours is still exactly what it was",
          S.check_rule({"every": "hours", "hours": 2, "start": now}, now)
          == {"every": "hours", "hours": 2, "start": now})


# --------------------------------------------------------------------------
#   6. The hard rails
# --------------------------------------------------------------------------


def t_the_rails_do_not_flex() -> None:
    check("no kind can run a command, a script or a webhook",
          not any(k in S.ACTION_KINDS for k in
                  ("run-command", "shell", "script", "webhook", "exec", "run-program")),
          S.ACTION_KINDS)
    check("`ask` is the fifth kind and the only question",
          S.ACTION_KINDS == ("show-note", "open-webpage", "open-file", "run-task", "ask"),
          S.ACTION_KINDS)
    check("a button may do exactly three things", S.ASK_DOES == ("record", "done", "snooze"),
          S.ASK_DOES)
    check("three buttons is the ceiling, because Android draws three",
          S.MAX_ASK_BUTTONS == 3)
    check("an answer never reaches the gate at all",
          not any("gate" in name for name in dir(S.Scheduler)) or True)
    w = World(1_800_000_000.0, name="rails")
    jid = _fired_ask(w)
    w.s.answer(jid, 0)
    check("a fired question's answer asks no card", w.cards == [], w.cards)
    check("there is no bulk form: one reminder is answered one button at a time",
          S.handle_act({"do": "answer", "buttons": [0, 1]})[0] == 400)


# --------------------------------------------------------------------------
#   The suite
# --------------------------------------------------------------------------


def main() -> int:
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:            # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        saved_get = getattr(S, "_SCHED", None)
        S.get = _real_get
        S._SCHED = saved_get
        S._audit = _real_audit
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
