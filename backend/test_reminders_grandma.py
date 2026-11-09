#!/usr/bin/env python3
"""The owner's Wave-13 "Grandma" reminder bug, in his own words (2026-11-09).

THE TRANSCRIPT THIS PINS. The owner said, in chat:

    "remind me to call Grandma in 4 days from now"

and three things went wrong:

  a) RELATIVE DATE. It produced 13:00 TODAY instead of four days out. The
     cause is in `jarvis_quick.py`: `_UNIT_S` had hours, minutes and seconds
     and no day or week at all, so "4 days" was not a length of time to
     `parse_duration`; `parse_when` answered None both to "in 4 days from now"
     (the `in` branch handed "4 days from now" to the parser and gave up) and,
     for the model's `set_reminder` call, to the whole phrase. The sentence
     therefore fell through to the model, which is where a wrong time came
     from.
  b) TITLE. The whole instruction became the reminder's own words. The title
     is what both apps print and what the notification says, so it has to be
     the ACTION - "call Grandma" (the owner's own words, his capitals) - and
     never the sentence that asked for it, nor its dangling time words.
  c) FALSE RECEIPT, the half that matters most to the owner: Jarvis said
     "I've updated it" on turns whose own footer said no action ran. A receipt
     exists only when an action really ran. `jarvis_claims.CLAIMS_DONE` had no
     "updated" verb at all, so "I've updated it" was not even read as a claim;
     and a `set_reminder` that FAILED left the model free to say it had worked.
     Now the answering round's words are HELD when a scheduler write failed,
     a "done" claim is dropped before it is read, and the tool's own error is
     said instead.

Plus the phone notification flag: the key both apps read is `notify` on the
schedule event (`jarvis-client/.../net/Schedule.kt`'s `firedFrom`: `false`
means no notification). A saved reminder now says `notify: true` on its own
view and on its going-off event, so a reminder carries the flag explicitly
instead of relying on the key being absent.

EVERYTHING HERE IS DETERMINISTIC: a frozen clock, a real scheduler in a
temporary folder, no model call of any kind. The one model-shaped check uses
`test_agent`'s scripted Ollama stream - still no network.

    py -3 -B backend/test_reminders_grandma.py

"""
from __future__ import annotations

import atexit
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_schedule.py", "jarvis_claims.py",
                "jarvis_agent.py")

#: This suite's own EMPTY config folder. The fast path records "the owner was
#: here" (jarvis_briefing), the wording of a reply depends on the saved manner
#: (jarvis_manner), and the change journal is written beside them - all of them
#: read the owner's real folder unless it is moved first. Nothing here may read
#: or write the owner's settings.
_CFG = tempfile.TemporaryDirectory(prefix="jarvis-grandma-cfg-")
_SAVED_CONFIG_DIR = os.environ.get("OPENJARVIS_CONFIG_DIR")
os.environ["OPENJARVIS_CONFIG_DIR"] = _CFG.name

import jarvis_manner as _manner  # noqa: E402
_manner._config_dir = lambda: Path(_CFG.name)

import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as S  # noqa: E402
import jarvis_claims as CL  # noqa: E402


def _restore_config_dir():
    if _SAVED_CONFIG_DIR is None:
        os.environ.pop("OPENJARVIS_CONFIG_DIR", None)
    else:
        os.environ["OPENJARVIS_CONFIG_DIR"] = _SAVED_CONFIG_DIR
    _CFG.cleanup()


atexit.register(_restore_config_dir)

PASSED, FAILED, SKIPPED = [], [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-grandma-"))

#: THE FIXTURE CLOCK: Monday 9 November 2026, 10:15 local. A Monday so "next
#: Monday" is a week away, and a time that is neither a default hour nor the
#: model's invented 13:00, so a wrong answer cannot look right by accident.
NOW = S.wall_to_epoch(2026, 11, 9, 10, 15)
TRANSCRIPT = "remind me to call Grandma in 4 days from now"
#: Four days, to the SECOND: a relative "in N days" is a LENGTH of time, so the
#: clock time the owner said it at is kept (10:15), not moved to a default.
EXPECTED_DUE = NOW + 4 * 86400


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: never counted as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def wall_text(t):
    return time_text(t)


def time_text(t):
    import time as _t
    return _t.strftime("%Y-%m-%d %H:%M:%S %a", _t.localtime(t))


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


class World:
    """A REAL scheduler with a hand-moved clock, its own database file, the bus
    captured, and a gate that never asks (a one-off reminder is cardless)."""

    def __init__(self, t, *, name="w"):
        self.clock = Clock(t)
        self.events, self.cards = [], []
        path = _TMP / f"{name}-{len(os.listdir(_TMP))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate,
                             tier_of=lambda a: "ask",
                             spawn=lambda fn: fn(),
                             publish=lambda k, d: self.events.append((k, d)))

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        return Verdict(True, "ask", "approved")

    def fired(self, kind=None):
        return [d for k, d in self.events
                if k == "schedule" and d.get("state") == "fired"
                and (kind is None or d.get("kind") == kind)]


def ask(text, *, now=NOW, conversation="c-grandma", w=None):
    """One turn through the REAL fast path, the way /api/chat runs it."""
    w = w or World(now)
    r = Q.answer(text, sched=w.s, now=now, conversation=conversation,
                 peer="127.0.0.1", local=True, client_surface="hud")
    return r, w


def only_row(w):
    jobs = w.s.listed()
    return jobs[0] if len(jobs) == 1 else None


# --------------------------------------------------------------------------
#   a) the relative date, exactly
# --------------------------------------------------------------------------

def t_the_owner_transcript_is_four_days_out():
    r, w = ask(TRANSCRIPT)
    check("his exact sentence is answered by the fast path, no model",
          r is not None and r.intent == "reminder_set",
          None if r is None else (r.intent, r.reply))
    if r is None:
        return
    job = only_row(w)
    check("it really wrote ONE reminder", job is not None, w.s.listed())
    if job is None:
        return
    check("the due time is four days from when he said it, to the second",
          job["due"] == EXPECTED_DUE,
          f'{job["due"]!r} ({time_text(job["due"])}) != {EXPECTED_DUE!r} '
          f'({time_text(EXPECTED_DUE)})')
    check("it is NOT today at 13:00 (the reported wrong answer)",
          not (job["due"] < NOW + 86400), time_text(job["due"]))
    check("the reply names the day and time it will go off",
          "10:15" in r.reply and "Friday" in r.reply, r.reply)
    check("the stored source is the fast path, not a model tool",
          job.get("source") == "quick", job)


def t_every_relative_phrasing_reads_the_same():
    """The same length in the shapes the owner (and one model) use: "in N
    days", "N from now", "in N from now", weeks, and hours/minutes kept."""
    cases = [
        ("remind me in 4 days to call Grandma", 4 * 86400, "call Grandma"),
        ("remind me to call Grandma in 4 days", 4 * 86400, "call Grandma"),
        ("remind me to call Grandma 4 days from now", 4 * 86400, "call Grandma"),
        ("remind me to call Grandma in 4 days from now", 4 * 86400, "call Grandma"),
        ("remind me in 2 weeks to renew the passport", 14 * 86400, "renew the passport"),
        ("remind me in 2 hours to stretch", 2 * 3600, "stretch"),
        ("remind me in 15 minutes", 15 * 60, "your reminder"),
    ]
    for said, seconds, words in cases:
        r, w = ask(said)
        job = only_row(w)
        check(f"{said!r}: due is +{seconds}s",
              job is not None and job["due"] == NOW + seconds,
              None if job is None else (time_text(job["due"]), r and r.reply))
        check(f"{said!r}: the words are the action {words!r}",
              job is not None and job["text"] == words,
              None if job is None else job["text"])


def t_a_bare_long_length_is_a_reminder_not_a_timer():
    """"in 4 days" alone: a timer is capped at a day (jarvis_schedule.
    MAX_TIMER's own comment says "later than that, set a reminder"), so the
    bare phrase must not reach add_timer and die with a timer error."""
    r, w = ask("in 4 days")
    check("a bare 'in 4 days' is a reminder", r is not None and r.intent == "reminder_set",
          None if r is None else (r.intent, r.reply))
    check("... and no timer was started", w.s.timers() == [], w.s.timers())
    r2, w2 = ask("in 10 minutes")
    check("'in 10 minutes' is still a TIMER, as it always was",
          r2 is not None and r2.intent == "timer_set"
          and len(w2.s.timers()) == 1, None if r2 is None else (r2.intent, r2.reply))


def t_a_day_with_no_time_uses_the_product_default_on_the_right_day():
    """A date with no clock gets the default the product already uses for a
    reminder - 09:00 (`jarvis_quick.DEFAULT_HOUR`) - on THAT day. "next Monday"
    is the next Monday, not today's 09:00."""
    r, w = ask("remind me next monday to call Grandma")
    job = only_row(w)
    monday = S.wall_to_epoch(2026, 11, 16, 9, 0)
    check("'next Monday' is 09:00 on the next Monday",
          job is not None and job["due"] == monday,
          None if job is None else time_text(job["due"]))
    check("... and the words are still the action", job is not None
          and job["text"] == "call Grandma", None if job is None else job["text"])
    check("... and the reply says the time, so a default is never a surprise",
          r is not None and "09:00" in r.reply, None if r is None else r.reply)


# --------------------------------------------------------------------------
#   b) the title is the action, never the sentence
# --------------------------------------------------------------------------

def t_the_title_is_the_action_and_nothing_else():
    r, w = ask(TRANSCRIPT)
    job = only_row(w)
    check("the title is the action, in the owner's own words: 'call Grandma'",
          job is not None and job["text"] == "call Grandma",
          None if job is None else job["text"])
    check("... the owner's capital G is kept ('Grandma', never 'grandma')",
          job is not None and "Grandma" in job["text"],
          None if job is None else job["text"])
    check("... no command words ('remind me') and no time words ('in 4 days')",
          job is not None and "remind" not in job["text"].lower()
          and "days" not in job["text"].lower() and "from now" not in job["text"].lower(),
          None if job is None else job["text"])
    # The same cleanup on the model's own road into a reminder: a model that
    # copies the whole request into `text` gets the action stored, not the
    # sentence. This is the "whole instruction became the title" bug itself.
    check("the tool argument cleanup strips the sentence's own framing",
          Q.reminder_action_words("remind me to call Grandma in 4 days from now", NOW)
          == "call Grandma",
          Q.reminder_action_words("remind me to call Grandma in 4 days from now", NOW))
    check("... a time phrase alone leaves nothing to store",
          Q.reminder_action_words("tomorrow at 9", NOW) == "",
          Q.reminder_action_words("tomorrow at 9", NOW))
    check("... and a plain action is untouched",
          Q.reminder_action_words("take my pills", NOW) == "take my pills")


# --------------------------------------------------------------------------
#   c) one receipt, and only because the action ran
# --------------------------------------------------------------------------

def t_one_receipt_and_only_because_it_ran():
    r, w = ask(TRANSCRIPT)
    job = only_row(w)
    check("ONE receipt, naming exactly the row that exists",
          r is not None and len(r.made) == 1 and job is not None
          and r.made == [job["id"]],
          None if r is None else (r.made, None if job is None else job["id"]))
    check("... and it is the receipt 'cancel that' would take back",
          r is not None and bool(r.what) and bool(r.nouns),
          None if r is None else (r.what, r.nouns))
    check("the answer says what was set, never 'updated'",
          r is not None and "updated" not in r.reply.lower()
          and "Reminder set" in r.reply, None if r is None else r.reply)


def t_a_turn_that_changes_nothing_leaves_no_receipt():
    """A control turn: a question about the list. It must change nothing, so
    there is no receipt and nothing in the answer that says something was
    changed."""
    r, w = ask("what's my next reminder?")
    check("the read is answered by the fast path", r is not None
          and r.intent == "next_up", None if r is None else getattr(r, "intent", None))
    check("... with NO receipt", r is not None and r.made == [],
          None if r is None else r.made)
    check("... and no sentence claiming something was set or updated",
          r is not None and "updated" not in r.reply.lower()
          and "set for" not in r.reply.lower(), None if r is None else r.reply)
    check("... and nothing was written to the scheduler", w.s.listed() == [],
          w.s.listed())


def t_a_failed_scheduler_write_cannot_keep_a_done_claim():
    """The owner's (c), at the seam where it happens: the model calls
    set_reminder, the call FAILS, and the model answers "I've updated it".

    The answering round's words are held when a scheduler write failed, the
    claim is dropped, and the tool's own error is said instead - a receipt
    exists only when the action really ran. The model here is
    `test_agent`'s scripted Ollama stream: no network, no real model.
    """
    check("'I've updated it' is read as a claim at all (it was not, before)",
          CL.claims_done("I've updated it.") and CL.unbacked_claim("I've updated it.", []),
          CL.CLAIMS_DONE.pattern)
    check("... and an action tool that really returned ok still backs it",
          not CL.unbacked_claim("I've updated it.",
                                [{"tool": "set_reminder", "ran": True, "ok": True}]))
    try:
        import test_agent as TA
    except Exception as exc:               # pragma: no cover - harness missing
        skip(f"the scripted-model harness could not be imported ({type(exc).__name__})")
        return
    import jarvis_agent as AG
    import types

    class RefusingSched:
        """A scheduler that refuses the one write, the way a passed time does."""

        def mark_command(self, _text):
            pass

        def add_at(self, kind, at, text="", source="quick", **k):
            raise ValueError("that time has already passed")

    real_get = S.get
    S.get = lambda: RefusingSched()
    try:
        rounds = [{"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "1", "function": {"name": "set_reminder",
                                     "arguments": json.dumps({
                                         "text": "call Grandma in 4 days from now",
                                         "when": "in 4 days from now"})}}]}}]}]
        responses = rounds + [{"choices": [{"message": {
            "role": "assistant", "content": "I've updated it - you'll get a reminder in 4 days."}}]}]
        opener, _calls = TA.scripted_stream(responses)
        streamed = []
        user = {"role": "user", "content": TRANSCRIPT, "provenance": "typed"}
        with TA.NoRealIO():
            res = AG.run_local_turn([dict(user)], "qwen3:8b",
                                    ollama_url="http://127.0.0.1:11434",
                                    stream_out=streamed.append, gate_check=TA.allow,
                                    request={"messages": [user]}, stream=True,
                                    enabled_tools={"set_reminder"}, open_stream=opener)
        text = TA.answer_text([b"".join(streamed)])
    finally:
        S.get = real_get
    check("the false 'I've updated it' is NOT in what the owner reads",
          "updated" not in text.lower(), text)
    check("... the tool's own refusal is said instead",
          "not set" in text.lower() and "has already passed" in text.lower(), text)
    check("... and it ends by saying nothing was changed",
          "Nothing was changed." in text, text)
    check("... with ONE correction line, not the same thing twice",
          text.count("Nothing was") == 1, text)
    check("the turn records that the reminder tool ran and did not succeed",
          "set_reminder" in res["tools_ran"], res["tools_ran"])


def t_a_model_that_keeps_its_words_is_left_alone():
    """The other half: when the scheduler write failed and the model claims
    nothing, its words are shown exactly as written - the guard must never
    rewrite an honest answer."""
    try:
        import test_agent as TA
    except Exception as exc:               # pragma: no cover
        skip(f"the scripted-model harness could not be imported ({type(exc).__name__})")
        return
    import jarvis_agent as AG
    import types

    class RefusingSched:
        def mark_command(self, _text):
            pass

        def add_at(self, kind, at, text="", source="quick", **k):
            raise ValueError("that time has already passed")

    real_get = S.get
    S.get = lambda: RefusingSched()
    honest = "I could not read that time - which day did you mean?"
    try:
        rounds = [{"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "1", "function": {"name": "set_reminder",
                                     "arguments": json.dumps({
                                         "text": "call Grandma",
                                         "when": "in 4 days from now"})}}]}}]}]
        responses = rounds + [{"choices": [{"message": {"role": "assistant",
                                                        "content": honest}}]}]
        opener, _calls = TA.scripted_stream(responses)
        streamed = []
        user = {"role": "user", "content": TRANSCRIPT, "provenance": "typed"}
        with TA.NoRealIO():
            AG.run_local_turn([dict(user)], "qwen3:8b",
                              ollama_url="http://127.0.0.1:11434",
                              stream_out=streamed.append, gate_check=TA.allow,
                              request={"messages": [user]}, stream=True,
                              enabled_tools={"set_reminder"}, open_stream=opener)
        text = TA.answer_text([b"".join(streamed)])
    finally:
        S.get = real_get
    check("an honest answer after a failed write is shown as written",
          text.strip() == honest, text)


# --------------------------------------------------------------------------
#   the phone notification flag
# --------------------------------------------------------------------------

def t_the_saved_reminder_carries_the_phone_notification_flag():
    """The key the phone reads is `notify` on the schedule event - `Schedule.kt`
    `firedFrom` returns no notification for `false`, and `coming-up.js` tests
    the same key. A saved reminder says `true` on its own view and on its
    going-off event; a kind that tells nobody still says `false`."""
    r, w = ask(TRANSCRIPT)
    job = only_row(w)
    check("the saved reminder's own view says it notifies the phone",
          job is not None and job.get("notify") is True,
          None if job is None else job.get("notify"))
    if job is None:
        return
    w.clock.t = job["due"] + 1
    w.s.tick()
    fired = w.fired("reminder")
    check("... and its going-off event carries notify: true",
          bool(fired) and fired[-1].get("notify") is True, fired)
    check("... with the id and the kind, and never the words",
          bool(fired) and fired[-1].get("id") == job["id"]
          and "Grandma" not in json.dumps(w.events), fired)
    try:
        import jarvis_standby_schedule  # noqa: F401  (registers the kind)
        quiet = S.KINDS.get("standby")
        check("a kind that tells nobody still says notify: false, in both places",
              quiet is not None and quiet.notify is False,
              None if quiet is None else quiet.notify)
        standby = w.s.add_repeat("standby", {"every": "day", "at": "01:00",
                                             "until": "07:00"})
        view = w.s.job(standby["id"])
        check("... the quiet kind's own view says false too",
              view is not None and view.get("notify") is False,
              None if view is None else view.get("notify"))
    except Exception as exc:
        skip(f"the standby kind could not be registered ({type(exc).__name__})")


# --------------------------------------------------------------------------
#   the simple phrasings that must keep working
# --------------------------------------------------------------------------

def t_the_existing_phrasings_still_work():
    cases = [
        ("remind me at 3pm", "your reminder", S.wall_to_epoch(2026, 11, 9, 15, 0)),
        ("remind me in 15 minutes", "your reminder", NOW + 15 * 60),
        ("remind me tomorrow at 9 to take pills", "take pills",
         S.wall_to_epoch(2026, 11, 10, 9, 0)),
        ("remind me tonight to call Grandma", "call Grandma",
         S.wall_to_epoch(2026, 11, 9, 20, 0)),
        ("set a reminder for 5pm to leave", "leave",
         S.wall_to_epoch(2026, 11, 9, 17, 0)),
        ("add a reminder to take my pills at 6pm", "take my pills",
         S.wall_to_epoch(2026, 11, 9, 18, 0)),
    ]
    for said, words, due in cases:
        r, w = ask(said)
        job = only_row(w)
        check(f"{said!r}: still a reminder with the action {words!r}",
              r is not None and r.intent == "reminder_set" and job is not None
              and job["text"] == words,
              None if job is None else (job["text"], r and r.reply))
        check(f"{said!r}: still due at the same moment",
              job is not None and job["due"] == due,
              None if job is None else (time_text(job["due"]), time_text(due)))


def main():
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
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())

