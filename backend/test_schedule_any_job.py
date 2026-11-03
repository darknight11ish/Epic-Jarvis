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
  - a phrase that resolves to an intent raising its OWN approval card (the
    batch audit's C2: `forget_range`, `update_start`, a carded setting change, a
    repeating briefing) is refused when it is SAVED, in one plain sentence that
    says it needs the owner's approval each time, that it cannot be scheduled as
    one card, and what the phrase matched - and no reminder is written;
  - a phrase that raises no card of its own still saves, and at fire time raises
    exactly ONE `schedule_action` card;
  - at fire time the phrase is resolved AGAIN: a phrase that no longer
    resolves raises NO card and runs nothing;
  - the fire path checks the resolved intent itself: a stored row that now
    resolves to a carded intent (saved by an older build, or a resolver that
    said yes) raises NO second card, runs nothing, says `needs_approval` in the
    audit, and its own row view says it did not run and why;
  - every intent `jarvis_quick.py` can construct is classified as carded or
    cardless, so a new one cannot arrive unclassified and slip a second card
    through;
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
import re
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


def fire_real(w, hits, phrase="add milk to my shopping list"):
    """The same, but the REAL resolver decides at save AND at fire time."""
    job = add(w, {"kind": "run-task", "job": phrase})
    setattr(w.s, "_run_job", fake_runner(hits))
    w.clock.t += 20.0
    w.s.tick()
    return job


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
#   The ONE-card promise: a job that would raise its OWN card is refused
# ---------------------------------------------------------------------------

def t_a_carded_phrase_is_refused_at_save():
    """The batch audit's C2: `forget_range`, `update_start` and a carded
    settings change each raise their own card, so scheduling one would put a
    SECOND card on screen. Refused at save, in one honest sentence."""
    w = World(1_800_000_000.0, name="save-carded")
    cases = (
        # phrase, the words the refusal must use, what the phrase matched
        ("forget everything from last week", "needs your approval each time",
         "forget a time frame"),
        ("update jarvis", "needs your approval each time", "install an update"),
        ("turn on background learning", "can need your approval each time",
         "change a setting"),
        ("brief me every weekday at 7", "needs your approval each time",
         "set up a repeating briefing"),
    )
    for phrase, need, matched in cases:
        got, sentence = refused(lambda p=phrase: add(w, {"kind": "run-task", "job": p}))
        check(f"the carded phrase {phrase!r} is refused at save", got, sentence)
        check(f"... {phrase!r}: it cannot be scheduled as one card",
              "cannot be scheduled as one card" in sentence, sentence)
        check(f"... {phrase!r}: the sentence says {need!r}", need in sentence, sentence)
        check(f"... {phrase!r}: it names what the phrase matched ({matched!r})",
              matched in sentence, sentence)
        check(f"... {phrase!r}: it says the reminder was not saved",
              "It was not saved." in sentence, sentence)
    check("... and no reminder was saved for any of them",
          w.s.listed() == [], w.s.listed())
    # The check is on the FORM that would ask, not on a name: a once-only
    # briefing raises no card of its own, so it still saves.
    once = add(w, {"kind": "run-task", "job": "brief me tomorrow at 7"})
    check("a once-only briefing still saves (only its repeating form is carded)",
          once.get("action") == {"kind": "run-task", "job": "brief me tomorrow at 7"},
          once.get("action"))
    # A new intent this build has never classified is refused too, in its own
    # honest sentence - never treated as "no card" by default.
    unknown = S._job_card_refusal(Intent("brand_new_job"))
    check("an unclassified intent is refused conservatively, in its own sentence",
          unknown.startswith("Jarvis cannot tell whether that job")
          and S._job_own_card(Intent("brand_new_job")) is S._JOB_UNSURE, unknown)


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


def t_a_cardless_phrase_still_saves_and_fires_one_card():
    """(b) of the fix: the refusal is not a fence around the whole feature."""
    hits = []
    w = World(1_800_000_000.0, name="fire-real-cardless")
    job = fire_real(w, hits)
    check("a cardless phrase still saves through the REAL resolver",
          job.get("action") == {"kind": "run-task", "job": "add milk to my shopping list"},
          job.get("action"))
    check("... and going off raises exactly ONE card", len(w.cards) == 1, w.cards)
    check("... the scheduler's own `schedule_action` card",
          w.card().get("action") == "schedule_action", w.card().get("action"))
    check("... and it runs the job once", len(hits) == 1
          and hits[0]["intent"] == "todo_add", hits)


def t_a_stored_carded_job_is_refused_at_fire():
    """(c) of the fix: a row an OLDER build let in (the permissive stub stands
    in for that save-time resolver) must not raise a second card now. It is
    refused at fire time, the audit says why, and the row's own view says it did
    not run."""
    hits = []
    w = World(1_800_000_000.0, name="fire-stored-carded")
    phrase = "forget everything from last week"

    def save_like_an_older_build():
        # `with_resolver` makes the save path say "todo_add" for everything, so
        # the row is written with the owner's words and no card check - exactly
        # what a build without this fix would have stored.
        return add(w, {"kind": "run-task", "job": phrase})

    job = with_resolver(save_like_an_older_build)
    setattr(w.s, "_run_job", fake_runner(hits))
    w.clock.t += 20.0
    w.s.tick()
    check("a stored carded job raises NO card at fire time", w.cards == [], w.cards)
    check("... and it runs nothing", hits == [], hits)
    lines = [d for e, d in _AUDIT if e == "schedule.action_refused"]
    check("... the audit says it needs approval, with the id and outcome only",
          lines and lines[-1].get("outcome") == "needs_approval"
          and set(lines[-1]) == {"id", "outcome"}, lines[-1:])
    view = w.s.job(job["id"]) or {}
    problem = str(view.get("action_problem") or "")
    check("... and the row says it did not run and why",
          "needs your approval each time" in problem
          and "forget a time frame" in problem, view.get("action_problem"))


def t_fire_rechecks_the_intent_even_when_resolution_says_yes():
    """The fire path's OWN check, not only the resolver's: even if a resolver
    handed back a carded intent as allowed, `_fire_action` refuses it."""
    hits = []
    w = World(1_800_000_000.0, name="fire-recheck")
    add(w, {"kind": "run-task", "job": "add milk to my shopping list"})
    setattr(w.s, "_run_job", fake_runner(hits))
    real = S.resolve_job
    S.resolve_job = lambda words: (Intent("forget_range"), "")
    try:
        w.clock.t += 20.0
        w.s.tick()
    finally:
        S.resolve_job = real
    check("a carded intent that resolution let through raises NO card",
          w.cards == [], w.cards)
    check("... and runs nothing", hits == [], hits)
    lines = [d for e, d in _AUDIT if e == "schedule.action_refused"]
    check("... and the audit says it needs approval",
          lines and lines[-1].get("outcome") == "needs_approval", lines[-1:])


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


def t_every_intent_the_resolver_can_return_is_classified():
    """Every `Intent("...")` name in `jarvis_quick.py` is in exactly one of the
    carded / cardless sets, so a future intent cannot arrive unclassified and
    slip a second card through. Also pins that each carded name has plain words
    for the refusal, and that the sets do not overlap."""
    source = (HERE / "jarvis_quick.py").read_text(encoding="utf-8")
    names = set(re.findall(r'Intent\("([a-z0-9_]+)"', source))
    import jarvis_quick as Q
    groups = {
        "read_only": set(Q.READ_ONLY_INTENTS),
        "cardless": set(S._JOB_CARDLESS),
        "carded": set(S._JOB_CARDED),
        "can_need": set(S._JOB_CAN_NEED),
        "repeat_carded": set(S._JOB_REPEAT_CARDED),
    }
    known = set().union(*groups.values())
    missing = sorted(names - known)
    check("every intent jarvis_quick.py constructs is classified carded/cardless",
          not missing, missing)
    overlaps = sorted((a & b) for a, b in
                      ((groups["cardless"], groups["carded"]),
                       (groups["cardless"], groups["can_need"]),
                       (groups["cardless"], groups["repeat_carded"]),
                       (groups["carded"], groups["can_need"]),
                       (groups["carded"], groups["repeat_carded"]),
                       (groups["can_need"], groups["repeat_carded"]))
                      if a & b)
    check("... and none are in two of the carded/cardless sets at once",
          not overlaps, overlaps)
    carded = groups["carded"] | groups["can_need"] | groups["repeat_carded"]
    read_collision = sorted(groups["read_only"] & carded)
    check("... and no READ_ONLY intent is also classified as carded",
          not read_collision, read_collision)
    no_words = sorted(n for n in carded if n not in S._JOB_CARD_WORDS)
    check("... and every carded intent has plain words for its refusal",
          not no_words, no_words)
    check("the read-only set is used as-is (a read-only intent is never refused)",
          all(S._job_own_card(Intent(n)) == "" for n in sorted(Q.READ_ONLY_INTENTS)
              if n in names), "a READ_ONLY intent was classified as carded")


# ---------------------------------------------------------------------------

def main():
    for fn in (t_a_phrase_is_saved_and_handed_back,
               t_an_unresolvable_phrase_is_refused_at_save,
               t_a_shell_command_or_script_is_refused_at_save,
               t_the_two_existing_names_still_work,
               t_a_carded_phrase_is_refused_at_save,
               t_fire_raises_exactly_one_card_naming_the_action,
               t_a_denied_or_unanswered_card_runs_nothing,
               t_a_non_ask_tier_raises_no_card_and_runs_nothing,
               t_a_phrase_that_stopped_resolving_refuses_at_fire,
               t_a_cardless_phrase_still_saves_and_fires_one_card,
               t_a_stored_carded_job_is_refused_at_fire,
               t_fire_rechecks_the_intent_even_when_resolution_says_yes,
               t_the_closed_name_path_is_unchanged,
               t_run_job_is_the_chat_path,
               t_every_intent_the_resolver_can_return_is_classified):
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
