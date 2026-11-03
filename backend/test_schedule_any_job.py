"""test_schedule_any_job.py - a scheduled task may run ANY job in the owner's words.

    python backend/test_schedule_any_job.py

THE OWNER'S DECISION (2026-11-02): a scheduled task may record the owner's own
words for the job, not only the closed two-name list. At fire time Jarvis
resolves the words through the SAME intent/action path chat uses, raises exactly
ONE approval card naming exactly what it will do, and runs nothing without a
person's yes. A shell, command or script is refused outright - the decision
excludes those - and so is any phrase the resolver cannot turn into a real
action.

What this proves, with a real SQLite file in a temporary folder, a hand-moved
clock, a gate that records what it was asked and a fake resolver where the real
one would touch modules:

  - an arbitrary phrase is SAVED and handed back exactly, and the two existing
    names (`briefing`, and `backup`'s refusal) work exactly as before;
  - an unresolvable phrase is refused when it is saved, in one plain sentence;
  - a shell / command / script phrase is refused when it is saved, in the
    owner's own decision's words - every one of the sample forms;
  - at fire time the phrase is resolved AGAIN: a phrase that no longer
    resolves raises NO card and runs nothing;
  - a job that resolves raises exactly ONE `schedule_action` card, its body says
    the action in plain words and says nothing happens before a yes, and its
    `detail` carries no owner words;
  - approved runs it ONCE through `jarvis_quick.run` - the same chat path;
  - denied, timed out, a tier that is not "ask" and a gate that raises all run
    nothing;
  - the owner's words never reach the audit log (ids and intent names only).

No model, no network, no real live backend, no real `~/.openjarvis` store: the
config dir is pointed at a temporary folder before the module is imported.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

#: Point every config default at a temporary folder BEFORE the module is
#: imported, so nothing in this file can read or write the owner's stores.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-any-job-"))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_TMP / "config"))
os.environ.setdefault("JARVIS_CONFIG_DIR", str(_TMP / "config"))
(_TMP / "config").mkdir(parents=True, exist_ok=True)

import jarvis_schedule as S  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


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


class Intent:
    def __init__(self, name, f=None):
        self.name = name
        self.f = dict(f or {})


_AUDIT = []
_real_audit = S._audit
S._audit = lambda event, detail: _AUDIT.append((event, detail))


class World:
    """A scheduler with a moved clock, a recording gate and no thread."""

    def __init__(self, t, *, answer="approved", tier="ask", name="w"):
        self.clock = Clock(t)
        self.events, self.cards = [], []
        self.answer, self.tier = answer, tier
        path = _TMP / f"{name}-{len(list(_TMP.iterdir()))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate,
                             tier_of=lambda a: self.tier,
                             spawn=lambda fn: fn(),
                             publish=lambda k, d: self.events.append((k, d)))

    def gate(self, action, detail, prompt):
        self.cards.append({"action": action, "detail": dict(detail), "prompt": prompt})
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)

    def card(self):
        return self.cards[-1] if self.cards else {}


def add(w, action, text="a reminder", **kwargs):
    kwargs.setdefault("kind", "reminder")
    return w.s.add_at(kwargs.pop("kind"), w.clock.t + kwargs.pop("in_seconds", 10.0),
                      text, action=action, **kwargs)


def refused(fn, words=None):
    try:
        fn()
    except ValueError as exc:
        text = str(exc)
        if words is not None and words not in text:
            return False, text
        return True, text
    except Exception as exc:                    # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"
    return False, ""


def with_resolver(fn):
    """Run `fn` with the resolver/runner replaced, then restore them."""
    def fake_resolve(words):
        return Intent("todo_add", {"text": "x"}), ""
    real_resolve = S.resolve_job
    S.resolve_job = fake_resolve
    try:
        return fn()
    finally:
        S.resolve_job = real_resolve


def fake_runner(hits):
    def runner(intent, words, jid):
        hits.append({"intent": getattr(intent, "name", ""), "words": words, "jid": jid})
    return runner


def fire_job(w, hits, phrase="add milk to my shopping list"):
    """Save a job, fire it, and record what `_run_job` would have run."""
    def go():
        add(w, {"kind": "run-task", "job": phrase})
        setattr(w.s, "_run_job", fake_runner(hits))
        w.clock.t += 20.0
        w.s.tick()
    with_resolver(go)


# ---------------------------------------------------------------------------
#   Saving: the owner's words, the two old names, and the refusals
# ---------------------------------------------------------------------------

def t_a_phrase_is_saved_and_handed_back():
    w = World(1_800_000_000.0, name="save-phrase")
    phrase = "add milk to my shopping list"
    intent, why = S.resolve_job(phrase)
    check("the REAL chat resolver resolves an everyday job phrase",
          intent is not None and getattr(intent, "name", ""), why)
    job = add(w, {"kind": "run-task", "job": phrase})
    check("the phrase is saved and handed back exactly",
          job.get("action") == {"kind": "run-task", "job": phrase}, job.get("action"))
    check("the saved row reports nothing wrong with it",
          "action_problem" not in job and "action_unreadable" not in job, job)
    check("a read-only-sounding job still resolves (the card is the gate)",
          S.resolve_job("brief me now")[0] is not None,
          S.resolve_job("brief me now")[1])
    check("a job with two keys (task AND job) is refused at save",
          refused(lambda: add(w, {"kind": "run-task", "task": "briefing",
                                  "job": "add milk"}))[0])


def t_an_unresolvable_phrase_is_refused_at_save():
    w = World(1_800_000_000.0, name="save-unknown")
    got, sentence = refused(
        lambda: add(w, {"kind": "run-task", "job": "flibbertigibbet the moon"}),
        "does not know how to do that")
    check("a phrase the resolver cannot turn into an action is refused at save",
          got, sentence)
    check("... and the reminder was not saved", w.s.listed() == [], w.s.listed())
    got, sentence = refused(lambda: add(w, {"kind": "run-task", "job": "   "}))
    check("an empty job phrase is refused at save", got, sentence)


def t_a_shell_command_or_script_is_refused_at_save():
    w = World(1_800_000_000.0, name="save-shell")
    for phrase in ("run a shell command dir",
                   "powershell -Command Get-ChildItem",
                   "run the script backup.bat",
                   "start a terminal and type dir",
                   "execute C:\\Temp\\setup.exe",
                   "bash -c whoami",
                   "run a command prompt"):
        got, sentence = refused(
            lambda p=phrase: add(w, {"kind": "run-task", "job": p}),
            "program, a command or a script")
        check(f"the shell phrase {phrase!r} is refused at save", got, sentence)
    check("... and no reminder was saved for any of them",
          w.s.listed() == [], w.s.listed())


def t_the_two_existing_names_still_work():
    w = World(1_800_000_000.0, name="save-names")
    check("briefing is still saved exactly as before",
          add(w, {"kind": "run-task", "task": "briefing"}).get("action")
          == {"kind": "run-task", "task": "briefing"})
    got, sentence = refused(lambda: add(w, {"kind": "run-task", "task": "backup"}),
                            "recovery code")
    check("backup is still refused with its own reason", got, sentence)
    for name in ("shell", "sleep", "rm -rf /", "open-app", ""):
        got, sentence = refused(lambda n=name: add(w, {"kind": "run-task", "task": n}))
        check(f"the closed name {name!r} is still refused", got, sentence)


# ---------------------------------------------------------------------------
#   Fire time: one card, re-resolved, nothing without a yes
# ---------------------------------------------------------------------------

def t_fire_raises_exactly_one_card_naming_the_action():
    hits = []
    w = World(1_800_000_000.0, name="fire-card")
    fire_job(w, hits)
    check("going off raises exactly ONE card", len(w.cards) == 1, w.cards)
    card = w.card()
    check("... and it is the scheduler's own `schedule_action`",
          card.get("action") == "schedule_action", card.get("action"))
    prompt = card.get("prompt") or ""
    check("the card body names the action in plain words",
          "What it will do:" in prompt and "add it to your to-do list" in prompt, prompt)
    check("... and says it happens only if the owner says yes",
          "only if you say yes" in prompt and "Nothing happens before that" in prompt,
          prompt)
    detail = card.get("detail") or {}
    check("the detail carries ids, the resolved intent and due - and no words",
          set(detail) == {"job", "due", "what", "intent", "leaves_this_pc"}
          and detail.get("intent") == "todo_add"
          and "add milk" not in json.dumps(detail), detail)
    check("an approved card runs the job ONCE through the chat path",
          len(hits) == 1 and hits[0]["intent"] == "todo_add", hits)
    ran = [d for e, d in _AUDIT if e == "schedule.action_ran"]
    check("the audit says it ran, with the intent name only",
          ran and ran[-1].get("what") == "todo_add" and "add milk" not in json.dumps(ran),
          ran[-1:])


def t_a_denied_or_unanswered_card_runs_nothing():
    for answer in ("denied", "timed_out"):
        hits = []
        w = World(1_800_000_000.0, name=f"fire-{answer}", answer=answer)
        fire_job(w, hits)
        check(f"{answer}: the card was raised once", len(w.cards) == 1, w.cards)
        check(f"{answer}: nothing ran", hits == [], hits)
        lines = [d for e, d in _AUDIT if e == "schedule.action_refused"]
        check(f"{answer}: the audit names the outcome, and only the id",
              lines and lines[-1].get("outcome") == answer
              and set(lines[-1]) == {"id", "outcome"}, lines[-1:])


def t_a_non_ask_tier_raises_no_card_and_runs_nothing():
    hits = []
    w = World(1_800_000_000.0, name="fire-auto", tier="auto")
    fire_job(w, hits)
    check("a tier of auto raises no card", w.cards == [], w.cards)
    check("... and runs nothing", hits == [], hits)


def t_a_phrase_that_stopped_resolving_refuses_at_fire():
    hits = []
    w = World(1_800_000_000.0, name="fire-gone")

    def save():
        add(w, {"kind": "run-task", "job": "add milk to my shopping list"})
        setattr(w.s, "_run_job", fake_runner(hits))

    with_resolver(save)
    real = S.resolve_job
    S.resolve_job = lambda words: (None, S.JOB_UNKNOWN)
    try:
        w.clock.t += 20.0
        w.s.tick()
    finally:
        S.resolve_job = real
    check("a phrase that no longer resolves raises NO card", w.cards == [], w.cards)
    check("... and runs nothing", hits == [], hits)
    lines = [d for e, d in _AUDIT if e == "schedule.action_refused"]
    check("... and the audit says it was not runnable",
          lines and lines[-1].get("outcome") == "unknown", lines[-1:])


def t_the_closed_name_path_is_unchanged():
    """`briefing` still raises the same ONE card with the same detail keys."""
    calls = []

    class FakeBriefing:
        @staticmethod
        def make(**kwargs):
            calls.append(kwargs)
            return {"ok": True}

    keep = sys.modules.get("jarvis_briefing")
    sys.modules["jarvis_briefing"] = FakeBriefing
    try:
        w = World(1_800_000_000.0, name="fire-briefing")
        job = add(w, {"kind": "run-task", "task": "briefing"},
                  text="taxes and the blue folder")
        w.clock.t += 20.0
        w.s.tick()
        check("the closed name still raises exactly ONE card", len(w.cards) == 1, w.cards)
        detail = w.card().get("detail") or {}
        check("... with exactly the old detail keys, and the closed name as `task`",
              set(detail) == {"job", "due", "what", "task", "leaves_this_pc"}
              and detail.get("task") == "briefing", detail)
        check("... and it ran the briefing once, with this reminder's id",
              len(calls) == 1 and calls[0].get("job") == job["id"], calls)
        check("... and the owner's words stayed out of the detail too",
              "taxes" not in json.dumps(detail), detail)
    finally:
        if keep is None:
            sys.modules.pop("jarvis_briefing", None)
        else:
            sys.modules["jarvis_briefing"] = keep


def t_run_job_is_the_chat_path():
    """`_run_job` calls `jarvis_quick.run(intent, sched, now)` - no new executor."""
    calls = []
    fake = types.ModuleType("jarvis_quick")

    def run(intent, sched, now, *a, **k):
        calls.append({"intent": intent, "sched": sched, "now": now})
        return object()

    fake.run = run
    keep = sys.modules.get("jarvis_quick")
    sys.modules["jarvis_quick"] = fake
    try:
        w = World(1_800_000_000.0, name="run-job")
        intent = Intent("todo_add", {"text": "milk"})
        S.Scheduler._run_job(w.s, intent, "add milk", "jid-1")
        check("the job runs through jarvis_quick.run - the same chat path",
              len(calls) == 1 and calls[0]["intent"] is intent
              and calls[0]["sched"] is w.s, calls)
        check("... and it rings the schedule event with this reminder's id",
              any(e[0] == "schedule" and e[1].get("id") == "jid-1" for e in w.events),
              w.events)

        def unhandled(intent, sched, now, *a, **k):
            return None

        fake.run = unhandled
        got = False
        try:
            S.Scheduler._run_job(w.s, intent, "add milk", "jid-2")
        except ValueError:
            got = True
        check("a job the chat path no longer handles is a failure, not a silent success",
              got)
    finally:
        if keep is None:
            sys.modules.pop("jarvis_quick", None)
        else:
            sys.modules["jarvis_quick"] = keep


# ---------------------------------------------------------------------------

def main():
    for fn in (t_a_phrase_is_saved_and_handed_back,
               t_an_unresolvable_phrase_is_refused_at_save,
               t_a_shell_command_or_script_is_refused_at_save,
               t_the_two_existing_names_still_work,
               t_fire_raises_exactly_one_card_naming_the_action,
               t_a_denied_or_unanswered_card_runs_nothing,
               t_a_non_ask_tier_raises_no_card_and_runs_nothing,
               t_a_phrase_that_stopped_resolving_refuses_at_fire,
               t_the_closed_name_path_is_unchanged,
               t_run_job_is_the_chat_path):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\nPASS {len(PASSED)}   FAIL {len(FAILED)}")
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
    S._audit = _real_audit
    shutil.rmtree(_TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
