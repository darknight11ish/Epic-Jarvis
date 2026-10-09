"""test_referee.py - "Referee suggestions": the propose-only "This looks done -
tick it?" card (the owner's decision of 2026-09-30; JARVIS-API section 108).

    python3 backend/test_referee.py

What it proves, with a real Goals store and scheduler (SQLite in a temporary
folder), a hand-moved clock, a stand-in gate and a stand-in for the numbers:
  - which steps are candidates: an open, unlocked step of an ACTIVE goal whose
    benchmark's newest number reaches its target (higher OR lower is better),
    and nothing else - not a ticked step, a draft or stopped goal, a step with
    no number, a number that is gone or unreadable, or one still short;
  - the card: its words, word for word, the evidence worked out by code, the
    honest label ("a suggestion from a number, not a check"), and for a health
    or money benchmark the keep-on-screen mark with nothing private in the
    gate's `what` or the audit log;
  - the tick comes ONLY from a person's yes: a card nobody answers ticks
    nothing; no, a timeout and an off switch tick nothing; a yes ticks that
    step exactly as the owner's own tick would (done_at from the PC's clock),
    and the ordinary untick undoes it; a yes for a step that changed while the
    card waited ticks nothing (stale);
  - the limits: at most three cards in 24 hours, none while one waits, none
    during a focus session or in Quiet, none mid-chat, none for a step the
    owner said no to (1 day, then 7, then 30), the same step once a day;
  - no route, no tool and no argument takes words (outside text cannot reach
    it), no model is ever called, and mark_step is called from exactly one place;
  - it is a quiet single job on the one scheduler, added and removed with the
    switch; referee.patch applies on the whole stack and is in the install lists.
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

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-referee-"))
os.environ["JARVIS_REFEREE_FILE"] = str(_TMP / "referee.json")
os.environ["JARVIS_BACKOFF_FILE"] = str(_TMP / "backoff.json")

require_shipped("jarvis_referee.py", "jarvis_goals.py", "jarvis_schedule.py",
                "jarvis_backoff.py", "jarvis_forecast.py")

import jarvis_backoff as BO  # noqa: E402
import jarvis_goals as G  # noqa: E402
import jarvis_referee as R  # noqa: E402
import jarvis_schedule as S  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None, reason=""):
        self.allowed, self.tier, self.outcome, self.reason = allowed, tier, outcome, reason


PROJ = "a" * 32


def bench(latest, target=30.0, better="lower", *, sensitive=False, name="5k time", unit="min"):
    return {"id": "b" * 32, "name": name, "unit": unit, "better": better, "target": target,
            "sensitive": sensitive, "keep_on_screen": sensitive,
            "latest": None if latest is None else {"id": "x", "value": latest, "at": 1.0},
            "forecast": None}


class World:
    """Goals + a scheduler + everything the module reaches for, replaced."""

    def __init__(self, *, answer="approved", tier="ask", on=True, focus=False, mode="active"):
        global _N
        _N += 1
        self.clock = Clock(1_000_000.0)
        self.answer, self.tier, self.on, self.focus_on = answer, tier, on, focus
        self.cards, self.audits = [], []
        self.benches = {}
        self.sched = S.Scheduler(_TMP / f"s{_N}.db", clock=self.clock,
                                 gate=lambda a, d, p: Verdict(True, "ask", "approved"),
                                 tier_of=lambda a: "ask", spawn=lambda fn: fn(),
                                 publish=lambda k, d: None)
        self.goals = G.Goals(_TMP / f"g{_N}.db", clock=self.clock, scheduler=self.sched,
                             bench_reader=self.read)
        self.bo = BO.Backoff(_TMP / f"b{_N}.json", clock=self.clock, mode=lambda: mode)
        self.mode = mode
        self.held = []           # cards whose answer has not come back yet
        os.environ["JARVIS_REFEREE_FILE"] = str(_TMP / f"r{_N}.json")
        R._reset_for_tests()
        self.before_answer = None
        S.register_kind(G.KIND, "goal check-in", "Jarvis: a goal check-in is due.",
                        on_fire=lambda jid: None, **G.KIND_OPTIONS)

    def read(self, project, b):
        return self.benches[(project, b)]         # KeyError = gone

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.before_answer:
            self.before_answer()
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)

    def goal(self, text="run a 5k", step="get under 30 minutes", accept=True, **extra):
        """A goal with one step that follows this world's benchmark (its key varies)."""
        key = (PROJ, "b" * 32)
        self.benches.setdefault(key, bench(31.0))
        g = self.goals.create(text, plan=[dict({"id": "s1", "step": step,
                                                "measure": {"project": PROJ, "bench": "b" * 32}},
                                               **extra)])
        return self.goals.accept(g["id"], plan=g["plan"]) if accept else g

    def kw(self, **over):
        d = dict(gate=self.gate, tier_of=lambda a: self.tier, spawn=lambda fn: fn(),
                 enabled=lambda: self.on, focus=lambda: self.focus_on, backoff=self.bo,
                 read_bench=self.read, goals=lambda: self.goals, clock=self.clock)
        d.update(over)
        return d

    def run(self, **over):
        return R.run_pass(**self.kw(**over))

    def step(self, goal_id, sid="s1"):
        return next(s for s in self.goals.get(goal_id)["plan"] if s["id"] == sid)


_N = 0


_REAL_AUDIT = R._audit


def _capture_audit():
    """Record what the module would write to the audit log (and put it back
    with _release_audit())."""
    seen = []
    R._audit = lambda event, detail: seen.append((event, dict(detail)))
    return seen


def _release_audit():
    R._audit = _REAL_AUDIT


# ------------------------------------------------------------ candidates --

def t_which_steps_look_done():
    w = World()
    g = w.goal()
    check("the number is short of its target: no candidate",
          R.candidates(w.goals.list(), w.read) == [])
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    c = R.candidates(w.goals.list(), w.read)
    check("lower is better, 29.5 <= 30: one candidate, with the numbers from code",
          len(c) == 1 and c[0]["goal"] == g["id"] and c[0]["step"] == "s1"
          and c[0]["latest"] == "29.5 min" and c[0]["target"] == "30 min"
          and c[0]["better"] == "lower" and c[0]["sensitive"] is False and c[0]["kind"] == "number", c)
    w.benches[(PROJ, "b" * 32)] = bench(30.0)
    check("exactly at the target counts (jarvis_forecast.better_reached)",
          len(R.candidates(w.goals.list(), w.read)) == 1)
    w.benches[(PROJ, "b" * 32)] = bench(21.1, target=21.0, better="higher", name="Long run", unit="km")
    check("higher is better, 21.1 >= 21: a candidate",
          len(R.candidates(w.goals.list(), w.read)) == 1)
    w.benches[(PROJ, "b" * 32)] = bench(20.9, target=21.0, better="higher", name="Long run", unit="km")
    check("higher is better, 20.9 < 21: none", R.candidates(w.goals.list(), w.read) == [])
    # the way "reached" is decided is the forecast module's, not a copy
    src = (HERE / "jarvis_referee.py").read_text(encoding="utf-8")
    check("'reached' is decided by jarvis_forecast.better_reached",
          "jarvis_forecast.better_reached(latest, target, better)" in src)

    w = World()
    w.benches[(PROJ, "b" * 32)] = bench(29.0)
    done = w.goal()
    w.goals.mark_step(done["id"], 0, True)
    check("a step the owner already ticked: none", R.candidates(w.goals.list(), w.read) == [])
    w = World()
    w.benches[(PROJ, "b" * 32)] = bench(29.0)
    w.goal(accept=False)
    check("a DRAFT goal: none", R.candidates(w.goals.list(), w.read) == [])
    w = World()
    w.benches[(PROJ, "b" * 32)] = bench(29.0)
    g = w.goal()
    w.goals.stop(g["id"])
    check("a STOPPED goal: none", R.candidates(w.goals.list(), w.read) == [])
    w = World()
    w.benches[(PROJ, "b" * 32)] = bench(29.0)
    g = w.goals.create("plain", plan=[{"step": "no number here"}])
    w.goals.accept(g["id"], plan=g["plan"])
    check("a step that follows no number: none", R.candidates(w.goals.list(), w.read) == [])
    w = World()
    w.benches[(PROJ, "b" * 32)] = bench(29.0)
    g = w.goals.create("race", plan=[
        {"id": "s1", "step": "sign up"},
        {"id": "s2", "step": "under 30", "needs": ["s1"],
         "measure": {"project": PROJ, "bench": "b" * 32}}])
    w.goals.accept(g["id"], plan=g["plan"])
    check("a step still locked behind another step: none (the owner ticks by hand)",
          R.candidates(w.goals.list(), w.read) == [])
    w = World()
    w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.0)
    w.benches.clear()
    check("a number that is gone: none, no crash", R.candidates(w.goals.list(), w.read) == [])

    def broken(project, b):
        raise RuntimeError("database is locked")
    w.benches[(PROJ, "b" * 32)] = bench(29.0)
    check("a reader that raises: none, no crash", R.candidates(w.goals.list(), broken) == [])
    for bad in (bench(None), bench(True), dict(bench(29.0), target=None),
                dict(bench(29.0), better=None), dict(bench(29.0), better="sideways")):
        w.benches[(PROJ, "b" * 32)] = bad
        check(f"a number that cannot be compared ({str(bad.get('latest'))[:20]}/{bad.get('better')}): none",
              R.candidates(w.goals.list(), w.read) == [])
    # a health or money benchmark carries the private mark
    w2 = World()
    w2.benches[(PROJ, "b" * 32)] = bench(150.0, target=180.0, better="lower", sensitive=True,
                                          name="Weight", unit="lb")
    w2.goal()
    c = R.candidates(w2.goals.list(), w2.read)
    check("a sensitive benchmark: the candidate is marked private", len(c) == 1 and c[0]["sensitive"] is True)


# --------------------------------------------------------------- the card --

def t_the_card_words():
    w = World()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    w.goal("run a 5k", "get under 30 minutes")
    c = R.candidates(w.goals.list(), w.read)[0]
    text = R.card_text(c)
    check("the card, word for word",
          text == ("This looks done - tick it?\n\n"
                   "Goal: \"run a 5k\"\n"
                   "Step: \"get under 30 minutes\"\n"
                   "Evidence: \"5k time\" is now 29.5 min, and your target is 30 min "
                   "(lower is better).\n\n"
                   "This is a suggestion from a number, not a check. Jarvis only compared the "
                   "latest number you logged with your target. It did not run a test, and it "
                   "cannot tell whether the work is really finished - only you can say that.\n\n"
                   "If you say yes: this step is ticked, the same as if you had ticked it "
                   "yourself. You can untick it at once in Goals.\n"
                   "If you say no: nothing changes, and Jarvis will not ask about this step "
                   "again for a day, then a week, then a month."), text)
    check("an ordinary number does not carry the private line", R.PRIVATE_LINE not in text)
    check("it never claims a model wrote it or checked anything",
          "small model" not in text.lower() and "verified" not in text.lower())
    private = dict(c, sensitive=True)
    check("a private number adds the keep-on-screen line, and only that",
          R.card_text(private) == text.replace(
              "\n\nIf you say yes", "\n\n" + R.PRIVATE_LINE + "\n\nIf you say yes"))
    check("words are cut short, never unbounded", len(R.card_text(dict(c, goal_text=R._short("g" * 300)))) < 1200)
    check("the gate's `what` holds no number and no name",
          not re.search(r"\d", R.WHAT) and R.WHAT == "tick one step of one of your goals")


def t_a_private_number_stays_on_the_screen():
    w = World()
    audits = _capture_audit()
    w.benches[(PROJ, "b" * 32)] = bench(150.0, target=180.0, better="lower", sensitive=True,
                                          name="Weight", unit="lb")
    w.goal("lose weight", "reach 180 lb")
    out = w.run()
    action, detail, prompt = w.cards[0]
    check("a card was raised for the private number", out == {"asked": 1, "why": "asked"})
    check("its detail says keep_on_screen, and carries ids, never words or numbers",
          detail["keep_on_screen"] is True and detail["what"] == R.WHAT
          and set(detail) == {"text", "what", "leaves_this_pc", "keep_on_screen", "goal", "step"}
          and detail["leaves_this_pc"] is False
          and "150" not in json.dumps({k: v for k, v in detail.items() if k != "text"}), detail)
    check("the card itself says so on the screen", R.PRIVATE_LINE in prompt and "150 lb" in prompt)
    blob = json.dumps(audits)
    check("the audit log holds counts and outcomes only - no weight, no goal, no step",
          "150" not in blob and "Weight" not in blob and "lose weight" not in blob
          and "180" not in blob, blob)
    _release_audit()
    # an ordinary benchmark is not marked
    w2 = World()
    w2.goal()
    w2.benches[(PROJ, "b" * 32)] = bench(29.0)
    w2.run()
    check("an ordinary number is not marked keep_on_screen", w2.cards[0][1]["keep_on_screen"] is False)


# ------------------------------------------- only a person's tap ticks it --

def t_only_a_yes_ticks():
    w = World()
    g = w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    held = []
    out = w.run(spawn=held.append)
    check("a card is raised and NOTHING is ticked while it waits",
          out["asked"] == 1 and len(held) == 1 and w.step(g["id"])["done"] is False
          and w.step(g["id"])["done_at"] is None)
    check("... even though the step is 'met by number' (the number alone never ticks)",
          w.step(g["id"])["state"] == "met_by_number")
    w.clock.t += 5
    held[0]()
    st = w.step(g["id"])
    check("a yes ticks that step, dated by the PC's clock, like the owner's own tick",
          st["done"] is True and st["done_at"] == w.clock.t and st["state"] == "done", st)
    check("the gate was asked exactly once, under referee_tick, with the card's words",
          len(w.cards) == 1 and w.cards[0][0] == "referee_tick"
          and w.cards[0][2].startswith("This looks done - tick it?"))
    check("and it says how it ended", R.status()["last"]["outcome"] == "ticked"
          and R.status()["last"]["message"] == R.LAST_WORDS["ticked"])
    w.goals.mark_step(g["id"], 0, False)
    st = w.step(g["id"])
    check("the ordinary untick undoes it at once", st["done"] is False and st["done_at"] is None)
    # every answer that is not a person's yes ticks nothing
    for label, ans in (("no", "denied"), ("timed out", "timed_out"), ("refused", "refused")):
        w = World(answer=ans)
        g = w.goal()
        w.benches[(PROJ, "b" * 32)] = bench(29.5)
        w.run()
        check(f"{label}: nothing is ticked", w.step(g["id"])["done"] is False)
    for label, v in (("tier notify", Verdict(True, "notify", "notify")),
                     ("tier auto", Verdict(True, "auto", "auto")),
                     ("old gate, allowed on auto", Verdict(True, "auto", None))):
        w = World()
        g = w.goal()
        w.benches[(PROJ, "b" * 32)] = bench(29.5)
        w.run(gate=lambda a, d, p, v=v: v)
        check(f"a 'yes' that is not a person ({label}): nothing is ticked",
              w.step(g["id"])["done"] is False and R.status()["last"]["outcome"] == "refused")
    w = World()
    g = w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)

    def boom(a, d, p):
        raise RuntimeError("gate down")
    w.run(gate=boom)
    check("a gate that fails: nothing is ticked, said in words",
          w.step(g["id"])["done"] is False and "gate failed" in R.status()["last"]["why"])
    src = re.sub(r'(?s)""".*?"""', "", (HERE / "jarvis_referee.py").read_text(encoding="utf-8"))
    src = "\n".join(l.split("#")[0] for l in src.splitlines())
    check("mark_step is called from exactly one place: after a person's yes",
          len(re.findall(r"\.mark_step\(", src)) == 1, re.findall(r"\.mark_step\(.*", src))
    body = src[src.index("def _decide"):src.index("def _read_bench_default")]
    check("... and that place is inside _decide, after the approval checks",
          body.index("mark_step(") > body.index('outcome == "approved"') or
          body.index("mark_step(") > body.index('"approved"'))


def t_a_yes_for_something_that_changed_ticks_nothing():
    # The number slipped back while the card waited.
    w = World()
    g = w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    w.before_answer = lambda: w.benches.__setitem__((PROJ, "b" * 32), bench(31.0))
    w.run()
    check("the number is no longer at its target when the yes comes: nothing ticked, 'stale'",
          w.step(g["id"])["done"] is False and R.status()["last"]["outcome"] == "stale")
    # The owner ticked it by hand meanwhile.
    w = World()
    g = w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    w.before_answer = lambda: w.goals.mark_step(g["id"], 0, True)
    w.clock.t += 0
    w.run()
    st = w.step(g["id"])
    check("the owner ticked it meanwhile: the card does not tick it a second time (done_at kept)",
          st["done"] is True and R.status()["last"]["outcome"] == "stale")
    # The goal was stopped meanwhile.
    w = World()
    g = w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    w.before_answer = lambda: w.goals.stop(g["id"])
    w.run()
    check("the goal was stopped meanwhile: nothing ticked", w.step(g["id"])["done"] is False
          and R.status()["last"]["outcome"] == "stale")
    # The switch was turned off while the card waited.
    w = World()
    g = w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)

    def off():
        w.on = False
    w.before_answer = off
    w.run()
    check("Referee suggestions turned off while the card waited, then a yes: nothing ticked",
          w.step(g["id"])["done"] is False and R.status()["last"]["outcome"] == "withdrawn")
    # ... and withdraw() while waiting
    w = World()
    g = w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    held = []
    w.run(spawn=held.append)
    R.withdraw()
    check("after withdraw() nothing waits", R.waiting() is False)
    held[0]()
    check("... and the late yes ticks nothing", w.step(g["id"])["done"] is False)


# ------------------------------------------------------------ the limits --

def t_the_limits():
    w = World()
    g = w.goal()
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    w.on = False
    check("switch OFF: nothing asked, nothing written",
          w.run() == {"asked": 0, "why": "off"} and not w.cards
          and not Path(os.environ["JARVIS_REFEREE_FILE"]).exists())
    w.on = True
    w.focus_on = True
    check("during a focus session: nothing asked",
          w.run() == {"asked": 0, "why": "focus"} and not w.cards)
    w.focus_on = False
    # Quiet and Standby (jarvis_backoff's own rule)
    for mode in ("quiet", "standby"):
        w2 = World(mode=mode)
        w2.goal()
        w2.benches[(PROJ, "b" * 32)] = bench(29.5)
        check(f"Jarvis in {mode}: nothing asked (kept for later)",
              w2.run() == {"asked": 0, "why": "held"} and not w2.cards)
    w3 = World()
    w3.goal()
    w3.benches[(PROJ, "b" * 32)] = bench(29.5)
    w3.bo.note_conversation()
    check("mid-chat (two minutes): nothing asked", w3.run()["why"] == "held" and not w3.cards)
    w3.clock.t += 121
    check("... and asked once the chat has gone quiet", w3.run()["asked"] == 1)
    # none while a card waits
    w = World()
    w.goal(); w.benches[(PROJ, "b" * 32)] = bench(29.5)
    w.goal("second goal", "another step")
    held = []
    check("first pass: one card", w.run(spawn=held.append)["asked"] == 1)
    check("second pass while it waits: none (waiting)",
          w.run(spawn=held.append) == {"asked": 0, "why": "waiting"} and len(held) == 1)
    held[0]()
    check("... and once it is answered the next one may be asked",
          R.waiting() is False and w.run()["asked"] == 1)
    # at most three in 24 hours
    w = World(answer="timed_out")
    for i in range(5):
        w.goal(f"goal {i}", f"step {i}")
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    asked = []
    for _ in range(5):
        asked.append(w.run()["why"])
        w.clock.t += 600
    check("five candidates, three cards then 'daily_limit'",
          asked == ["asked", "asked", "asked", "daily_limit", "daily_limit"], asked)
    check("exactly three cards reached the gate", len(w.cards) == 3)
    w.clock.t += 24 * 3600
    check("24 hours later it may ask again", w.run()["asked"] == 1)
    # the same step once a day even if nobody answered
    w = World(answer="timed_out")
    w.goal(); w.benches[(PROJ, "b" * 32)] = bench(29.5)
    check("an unanswered card is asked once", w.run()["asked"] == 1)
    w.clock.t += 3600
    check("... and not again an hour later (same step)", w.run()["why"] == "held" and len(w.cards) == 1)
    w.clock.t += 24 * 3600
    check("... but the next day, yes", w.run()["asked"] == 1)
    # a no is heard: 1 day, then 7, then 30
    w = World(answer="denied")
    w.goal(); w.benches[(PROJ, "b" * 32)] = bench(29.5)
    w.run()
    for days, label in ((1, "first no: quiet for a day"), (7, "second no: quiet for a week"),
                        (30, "third no: quiet for a month")):
        w.clock.t += days * 86400 - 3600
        check(f"{label} - still quiet just before", w.run()["why"] == "held")
        w.clock.t += 3600 + 60
        got = w.run()
        check(f"{label} - asked again after", got["asked"] == 1, got)
    check("four cards in all", len(w.cards) == 4)
    # a tier that is not ask raises nothing
    w = World(tier="auto")
    w.goal(); w.benches[(PROJ, "b" * 32)] = bench(29.5)
    check("gate line not 'ask': no card at all", w.run() == {"asked": 0, "why": "tier"} and not w.cards)
    # a ledger that cannot be read fails quiet
    w = World()
    w.goal(); w.benches[(PROJ, "b" * 32)] = bench(29.5)
    Path(os.environ["JARVIS_REFEREE_FILE"]).write_text("{not json", encoding="utf-8")
    check("an unreadable ledger: no card (fails quiet)",
          w.run() == {"asked": 0, "why": "unreadable"} and not w.cards)
    # nothing to say
    w = World()
    w.goal()
    check("no step at its target: 'nothing'", w.run() == {"asked": 0, "why": "nothing"})
    # the ledger holds times and a hash - never words
    w = World()
    w.goal("secret goal words", "secret step words")
    w.benches[(PROJ, "b" * 32)] = bench(29.5)
    w.run()
    led = Path(os.environ["JARVIS_REFEREE_FILE"]).read_text(encoding="utf-8")
    check("the ledger holds times and a fingerprint, no words",
          "secret" not in led and set(json.loads(led)) == {"offers", "asked"}, led)


# ---------------------------------------- nothing outside can reach it --

def t_no_route_no_tool_no_model():
    src = (HERE / "jarvis_referee.py").read_text(encoding="utf-8")
    code = re.sub(r'(?s)""".*?"""', "", src)
    code = "\n".join(l.split("#")[0] for l in code.splitlines())
    check("no HTTP route: no handle_get, handle_post or handler wrapping",
          not re.search(r"def (handle_get|handle_post|do_GET|do_POST)|handler_cls|read_body", code))
    check("no network at all: no socket, urllib, http or requests",
          not re.search(r"\b(socket|urllib|requests|http\.client|urlopen)\b", code))
    check("no model is ever called: no second-card lane, no generate, no /api/chat",
          not re.search(r"lane_for|generate\(|/api/chat|/api/generate|study_call|jarvis_agent|"
                        r"jarvis_router|ollama", code, re.I))
    check("it never writes a benchmark result, a VERIFIED mark, or runs a command",
          not re.search(r"log_result|add_result|verified|subprocess|os\.system|run_command|\.run\(",
                        code, re.I))
    check("its public functions take no words from outside (run_pass takes only test hooks)",
          [n for n in ("run_pass", "ensure_job", "status", "install", "withdraw")
           if not callable(getattr(R, n))] == [])
    import inspect
    check("run_pass() has no text parameter",
          set(inspect.signature(R.run_pass).parameters) == {"over"})
    try:
        import jarvis_agent as AG
        check("it is not one of the model's tools", not any("referee" in t.lower() for t in AG.TOOLS))
    except ImportError:
        skip("jarvis_agent is not importable here")
    quiz = (HERE / "jarvis_quiz.py").read_text(encoding="utf-8")
    check("the quiz and the referee do not know each other", "referee" not in quiz.lower()
          and "jarvis_quiz" not in code)


# ------------------------------------------------ the one scheduler --

def t_the_one_scheduler():
    k = S.KINDS["referee"]
    check("KIND referee is registered: quiet, single, not listed, tells nobody",
          k.owner_listed is False and k.notify is False and k.silent is True and k.single is True
          and k.plain_repeat is True)
    check("and jarvis_schedule loads this module with the other kinds",
          "jarvis_referee" in S.KIND_MODULES)
    w = World(on=False)
    real = R.enabled
    try:
        R.enabled = lambda: False
        check("switch off: no job", R.ensure_job(w.sched) == "" and w.sched.jobs_of("referee") == [])
        R.enabled = lambda: True
        check("switch on: one hourly job added", R.ensure_job(w.sched) == "added"
              and len(w.sched.jobs_of("referee")) == 1)
        check("again: kept, not doubled", R.ensure_job(w.sched) == "kept"
              and len(w.sched.jobs_of("referee")) == 1)
        listed = [j for j in w.sched.listed() if j.get("kind") == "referee"]
        check("it is not in Coming up", listed == [])
        R.enabled = lambda: False
        check("switch off again: the job is removed", R.ensure_job(w.sched) == "removed"
              and w.sched.jobs_of("referee") == [])
    finally:
        R.enabled = real
    ins = R.install()
    check("install() adds no route and says one plain line", ins.startswith("  referee") and "\n" not in ins)


def t_enabled_follows_the_second_card_switch():
    import jarvis_second_card as SC
    calls = []
    real = SC.feature_active
    try:
        SC.feature_active = lambda f: calls.append(f) or True
        check("enabled() asks the second-card switches for 'referee'",
              R.enabled() is True and calls == ["referee"])
        SC.feature_active = lambda f: (_ for _ in ()).throw(RuntimeError("x"))
        check("... and is False when in doubt", R.enabled() is False)
    finally:
        SC.feature_active = real


# ------------------------------------------------ the patch and the lists --

def t_the_patch_and_the_lists():
    import _stack
    order = _stack.order()
    # tag-suggest.patch, youtube.patch and quiz-cloud.patch (2026-09-30) go after it.
    # gate-action-name.patch (2026-10-03) goes after those: it rewrites one line
    # inside jarvis_gate.py's action_for_tool() and touches no list referee.patch's
    # hunks anchor on. readpage.patch (2026-10-05) goes after those too, for the
    # same reason as gate-action-name: its two hunks are in jarvis_gate.py,
    # anchored on quiz-cloud.patch's own added lines, and they add to the same
    # two lists rather than rewriting any line referee.patch's hunks anchor on.
    # The checks below are what really says so - the stacked jarvis_gate.py has
    # to build with referee.patch's own hunks applied to real context, and its
    # risk line has to still read as it did.
    # gate-risk-rows.patch (2026-10-06) goes after those too: it rewrites the
    # stale duplicate rows of jarvis_gate.py's _RISK table, in the part of the
    # table above the action names referee.patch's own risk line sits in, and it
    # touches no list referee.patch's hunks anchor on. The checks below are what
    # really says so.
    # chatbot-limits.patch (2026-10-06) goes after those too, and for a
    # stronger reason than the order it happened to be written in: its two
    # jarvis_gate.py hunks add the api-limit actions to the same two lists
    # readpage.patch's own hunks do, so whichever of the two runs second must
    # run against the other's finished text. readpage goes first; written the
    # other way round it stopped applying at all (test_readpage.py). It adds no
    # gate list entry referee.patch's hunks anchor on.
    #
    # accounts.patch (2026-10-06) goes after those too: its two hunks are in
    # jarvis_hud.py, anchored on web-search.patch's own added lines, and it
    # adds no gate list entry, no risk row and no _TOOL_ACTIONS line - it
    # rewrites nothing referee.patch's hunks anchor on.
    later = {"tag-suggest.patch", "youtube.patch", "quiz-cloud.patch",
             "gate-action-name.patch", "tutorials.patch", "readpage.patch",
             "chatbot-limits.patch", "chatbot-limits-hud.patch",
             "gate-risk-rows.patch", "accounts.patch",
             # screen-attach.patch (2026-10-07): one hunk in jarvis_hud.py's
             # tutorials install block. It touches jarvis_gate.py not at all, so
             # it rewrites nothing referee.patch's hunks anchor on.
             "screen-attach.patch",
             # prompt-coach.patch (2026-10-08): two hunks in jarvis_hud.py, one GET
             # route and one POST block, anchored on routes that predate it. It
             # touches jarvis_gate.py not at all, so it rewrites nothing
             # referee.patch's hunks anchor on.
             "prompt-coach.patch",
             # tasks.patch (2026-10-08): two hunks in jarvis_hud.py - one GET
             # route and one POST block - and jarvis_gate.py not at all. It
             # rewrites nothing referee.patch's hunks anchor on.
             "tasks.patch",
             # retrieve-count.patch (2026-10-08): two hunks in jarvis_hud.py -
             # `_retrieve_counts()` beside retrieve() and the handler's own
             # `count=1` branch - and jarvis_gate.py not at all. It rewrites
             # nothing referee.patch's hunks anchor on.
             "retrieve-count.patch",
             # attention-settings.patch (2026-10-08): ONE route in jarvis_hud.py
             # (POST /api/attention/settings), anchored on the attention routes
             # already there, and jarvis_gate.py not at all. It rewrites nothing
             # referee.patch's hunks anchor on.
             "attention-settings.patch"}
    check("referee.patch is the last patch in apply-patches.ps1's list, bar the ones written after it",
          [n for n in order if n not in later][-1] == "referee.patch", order[-3:])
    gate, log = _stack.stand_in("jarvis_gate.py")
    hud, hlog = _stack.stand_in("jarvis_hud.py")
    check("the stacked jarvis_gate.py builds, and referee.patch's hunks applied to real context",
          gate is not None and not any(l.startswith("referee.patch") for l in log), log[-3:])
    check("the action joins the 'acts only on tier ask' set",
          re.search(r'"referee_tick",\s+# jarvis_referee\.py acts only on tier "ask"', gate) is not None)
    m = re.search(r'"referee_tick": \("(\w+)", "(\w+)", "([^"]+)"\)', gate)
    check("its risk line is reversible, local, and says it never runs a test",
          m is not None and m.group(1) == "yes" and m.group(2) == "local"
          and "untick it at once" in m.group(3) and "never runs a test" in m.group(3), m)
    check("the startup block installs the referee and wires the study call, after the quiz block",
          hud is not None and "jarvis_referee.install()" in hud
          and "jarvis_second_card.wire_study()" in hud
          and hud.index("jarvis_quiz.install(") < hud.index("jarvis_second_card.wire_study()")
          and hud.index("jarvis_topics.install(") < hud.index("jarvis_referee.install()"))
    ps1 = (HERE.parent / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 ships jarvis_referee.py", "'jarvis_referee.py'" in ps1)
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped toml has referee_tick = \"ask\"",
          re.search(r'^referee_tick\s*=\s*"ask"', toml, re.M) is not None)
    import jarvis_asks_first as AF
    check("What asks first lists it, with plain words, and it can never be loosened",
          "referee_tick" in AF.HARD_LIMITS and "referee_tick" in AF.MUST_ASK
          and any("referee_tick" in g[1] for g in AF.GROUPS))
    import jarvis_card_words as CW
    check("the card's title words exist", CW.CARD_WORDS.get("referee_tick") if hasattr(CW, "CARD_WORDS")
          else "referee_tick" in open(HERE / "jarvis_card_words.py", encoding="utf-8").read())
    check("jarvis_backoff declares this offer, and it asks for nothing it may not",
          BO.OFFERS.get(R.OFFER) == ("tick_a_step",) and "tick_a_step" in BO.MAY_ASK
          and BO.vet(R.OFFER)[0] is True)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
