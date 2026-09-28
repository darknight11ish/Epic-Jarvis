"""test_chatbot_compare.py - "Ask several and compare" (jarvis_chatbot_compare.py;
the owner's decision of 2026-09-28; docs/JARVIS-API.md section 60.7).

    python3 backend/test_chatbot_compare.py

Jarvis asks two or more chatbots the same goal, one card listing every one,
each in its own conversation under the same limits and the same safety as a
single conversation, and writes ONE summary: where they agree, where they
disagree (naming who said what), the sources each gave (not checked by
Jarvis), what is still open, and who dropped out and why.

With the REAL jarvis_chatbot, jarvis_chatbot_routes, jarvis_router,
jarvis_search, jarvis_mail_mask, jarvis_task_control and jarvis_stop_all;
stand-in chatbots (jarvis_chatbot.FakeChatbot, one per test entry), a
stand-in driver model, a stand-in gate and a clock moved by hand. What it
proves:

  - how many chatbots one comparison may ask, per version (2 to 3 on one
    card, 2 to 4 on two cards); each chatbot checked by name before a card;
  - ONE card, action chatbot_session, listing every chatbot by name and
    address, the goal word for word, the limits per chatbot and in all, and
    what saying no costs; a no (or a failing gate) sends nothing anywhere;
  - each chatbot gets its own conversation, one after another, the goal
    first; the driver for one never sees another chatbot's words (clean
    context);
  - the last check and the never-send words apply to every chatbot; a goal
    that fails the check raises no card;
  - one chatbot failing (an error, a captcha) does not stop the others, and
    the summary says which one dropped out and why;
  - Stop (the comparison's own, a conversation's id, the task Stop) and Stop
    everything stop all of them; the ones not asked yet are never opened;
  - Pause pauses the whole comparison; Resume is jarvis_task_control's own
    card and carries on where it stopped;
  - the summary names who disagrees, drops names that are not the chatbots
    asked, lists each one's sources as not checked, and is outside text;
  - one comparison OR one conversation at a time;
  - the routes: status carries the comparison and the per-version numbers,
    start/stop answer in plain sentences, bad ids are refused.

No pytest, no network, no model.
"""
from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_chatbot.py", "jarvis_chatbot_compare.py", "jarvis_chatbot_routes.py",
                "jarvis_task_control.py", "jarvis_stop_all.py", "jarvis_search.py",
                "jarvis_mail_mask.py", "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chatbot-compare-"))
TIERS: dict = {}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

import jarvis_stop_all as SA  # noqa: E402
import jarvis_task_control as TC  # noqa: E402
import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_compare as CMP  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


GOAL = "Find out how to keep houseplants alive in a flat that gets very little light."
NEVER = "Project " + "Nimbus"
FAKE_EMAIL = "zyl" + "vana" + "@" + "example.org"

#: The stand-ins, registered as test-only chatbots of their own.
BOTS = {
    "fake_a": ("Test chatbot A", "a.example"),
    "fake_b": ("Test chatbot B", "b.example"),
    "fake_c": ("Test chatbot C", "c.example"),
    "fake_d": ("Test chatbot D", "d.example"),
    "fake_e": ("Test chatbot E", "e.example"),
}
SAYS = {
    "fake_a": ["Alpha thinks snake plants tolerate dim corners remarkably well, see "
               "https://example.org/snake-plants.",
               "Alpha adds that grow lamps deliver consistent spectrum all year.",
               "Alpha concludes pothos, snake plants and ZZ plants are easiest."],
    "fake_b": ["Bravo believes calatheas need bright indirect light instead.",
               "Bravo mentions extension services publish guidance: https://example.net/guide.",
               "Bravo recommends parlour palms for pet owners."],
    "fake_c": ["Charlie suggests cast iron plants survive neglect beautifully.",
               "Charlie warns overwatering kills more houseplants than darkness.",
               "Charlie prefers fluorescent tubes over LED strips."],
    "fake_d": ["Delta lists ferns, peace lilies and philodendrons.",
               "Delta cites horticultural research about humidity levels.",
               "Delta says rotating pots weekly helps symmetrical growth."],
}
QUESTIONS = [
    "Which plants cope best with a north-facing window?",
    "What sources support that claim?",
    "How does a grow lamp compare with moving plants closer to the glass?",
    "Could you narrow that down to plants that are safe around cats?",
    "Why do leaves turn yellow in low light?",
    "How often should watering happen in winter?",
]
SUMMARY = {
    "answer": "Choose a low-light plant and add a grow lamp if the corner is very dark.",
    "agree": ["Snake plants cope with dim light"],
    "disagree": [{"point": "Whether calatheas suit a dark flat",
                  "views": [{"who": "Test chatbot A", "said": "Low-light plants are fine"},
                            {"who": "test chatbot b", "said": "Calatheas need bright light"},
                            {"who": "Bard", "said": "An AI that was never asked"}]},
                 {"point": "Only a stranger's view", "views": [{"who": "Nobody", "said": "x"}]}],
    "sources": [{"who": "Test chatbot B", "source": "university extension services"},
                {"who": "Bard", "source": "made up"}],
    "open": ["Which grow lamp to buy"],
}


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, float(s))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


CARDS: list = []


def approve(action, detail, prompt):
    CARDS.append((action, detail, prompt))
    return Verdict(True, "approved")


def deny(action, detail, prompt):
    CARDS.append((action, detail, prompt))
    return Verdict(False, "denied")


class Model:
    """The driver model's stand-in. `moves(body, n)` may return a move dict;
    None is the next plain question. Every request is kept."""

    def __init__(self, moves=None, summary=None):
        self.moves = moves
        self.summary = summary if summary is not None else SUMMARY
        self.bodies: list = []
        self.n = 0

    def __call__(self, url, body):
        self.bodies.append(json.loads(json.dumps(body)))
        if body.get("format") == CMP.SUMMARY_SCHEMA:
            return {"message": {"content": json.dumps(self.summary)}, "done_reason": "stop"}
        if body.get("format") == CB.SUMMARY_SCHEMA:
            raise AssertionError("a conversation in a comparison wrote its own summary")
        self.n += 1
        mv = self.moves(body, self.n) if callable(self.moves) else None
        if mv is None:
            mv = {"move": "deeper", "message": QUESTIONS[(self.n - 1) % len(QUESTIONS)],
                  "reason": "", "notes": f"note {self.n}"}
        return {"message": {"content": json.dumps(mv)}, "done_reason": "stop"}

    def moves_for(self):
        return [b for b in self.bodies if b.get("format") == CB.MOVE_SCHEMA]

    def summaries(self):
        return [b for b in self.bodies if b.get("format") == CMP.SUMMARY_SCHEMA]


def bot(cid, **kw):
    says = SAYS[cid]
    kw.setdefault("replies", lambda text, n: says[(n - 1) % len(says)])
    b = CB.FakeChatbot(**kw)
    b.cid = cid
    return b


def register():
    for cid, (name, host) in BOTS.items():
        CB.register_adapter(CB.AdapterInfo(cid, name, host, CB.FakeChatbot, test_only=True,
                                           how="a stand-in on this PC that talks to nobody"))


def clean():
    CB._reset_for_tests()
    CMP._reset_for_tests()
    R._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()
    CARDS.clear()
    TIERS.clear()
    register()


def deps(bots, model=None, *, gate=approve, full=False, lane=None, facts=None, busy=None):
    clock = Clock()
    return CB.Deps(model=model or Model(), saved_facts=lambda m: list(facts or []),
                   names_for_facts=lambda f: {}, owner_busy=busy or (lambda: False),
                   second_lane=lambda: lane, full_version_on=lambda: full,
                   main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
                   tier_of=lambda a: TIERS.get(a, "ask"), gate=gate,
                   activity=lambda s, d="": None, audit=lambda e, d: None,
                   clock=clock, sleep=clock.sleep,
                   make_adapter=lambda cid: bots[cid], allow_test_adapters=True)


def go(bots, d=None, ids=None, **kw):
    d = d or deps(bots)
    c = CMP.plan(ids or list(bots), kw.pop("goal", GOAL), deps=d, **kw)
    code, out = CMP.start(c, deps=d, wait=True)
    return c, d, code, out


class Lane:
    url = "http://127.0.0.1:11435"
    model = "jarvis-long"
    num_ctx = 32768


# ==========================================================================

def t_how_many_per_version():
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b", "fake_c", "fake_d")}
    d = deps(bots)
    one = CMP.plan(["fake_a"], GOAL, deps=d)
    check("one chatbot is not a comparison", one.problem == "pick at least 2 chatbots to compare",
          one.problem)
    same = CMP.plan(["fake_a", "fake_a"], GOAL, deps=d)
    check("the same chatbot twice counts once", "at least 2" in same.problem, same.problem)
    four = CMP.plan(["fake_a", "fake_b", "fake_c", "fake_d"], GOAL, deps=d)
    check("one card: at most 3", four.tier.id == CB.ONE_CARD
          and four.problem == "pick at most 3 chatbots in this version", four.problem)
    three = CMP.plan(["fake_a", "fake_b", "fake_c"], GOAL, deps=d)
    check("one card: 3 is fine", not three.problem and len(three.members) == 3, three.problem)
    d2 = deps(bots, full=True, lane=Lane())
    four2 = CMP.plan(["fake_a", "fake_b", "fake_c", "fake_d"], GOAL, deps=d2)
    check("two cards: 4 is fine", four2.tier.id == CB.TWO_CARDS and not four2.problem,
          four2.problem)
    five = CMP.plan(list(BOTS), GOAL, deps=d2)
    check("two cards: at most 4", five.problem == "pick at most 4 chatbots in this version",
          five.problem)
    check("the numbers are the proposed ones", CMP.MIN_AIS == 2
          and CMP.MAX_AIS == {CB.ONE_CARD: 3, CB.TWO_CARDS: 4})
    unknown = CMP.plan(["fake_a", "nope"], GOAL, deps=d)
    check("an unknown chatbot is named", "no chatbot called 'nope'" in unknown.problem,
          unknown.problem)
    d3 = deps(bots)
    d3.allow_test_adapters = False
    t = CMP.plan(["fake_a", "fake_b"], GOAL, deps=d3)
    check("a test-only chatbot is refused outside the tests",
          "only for Jarvis's own tests" in t.problem, t.problem)
    CB.register_adapter(CB.AdapterInfo("fake_x", "Unbuilt bot", "x.example", CB.FakeChatbot,
                                       built=False))
    u = CMP.plan(["fake_a", "fake_x"], GOAL, deps=d)
    check("an unbuilt chatbot is named", u.problem == "Unbuilt bot is not built yet", u.problem)
    CB.ADAPTERS.pop("fake_x", None)
    CB.register_adapter(CB.AdapterInfo("fake_y", "Unready bot", "y.example", CB.FakeChatbot,
                                       ready=lambda: "Unready bot has never been signed in."))
    d4 = deps(bots)
    d4.make_adapter = None
    u = CMP.plan(["fake_a", "fake_y"], GOAL, deps=d4)
    check("a chatbot that is not set up says why", "never been signed in" in u.problem,
          u.problem)
    CB.ADAPTERS.pop("fake_y", None)
    bad = CMP.plan(["fake_a", "fake_b"], GOAL, max_turns=50, deps=d)
    check("the per-chatbot limits are the version's", "at most 8 messages" in bad.problem,
          bad.problem)


def t_one_card_lists_every_ai():
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b", "fake_c")}
    c, d, code, out = go(bots, max_turns=2, max_minutes=5, never_send=[NEVER])
    check("the start answers 202 and asked", code == 202 and out["asking"] is True, out)
    check("exactly ONE card, under chatbot_session", len(CARDS) == 1
          and CARDS[0][0] == "chatbot_session", [x[0] for x in CARDS])
    text = CARDS[0][1]["text"]
    for cid, (name, host) in list(BOTS.items())[:3]:
        check(f"the card names {name} and its address", f"{name} ({host})" in text)
    check("... every one numbered, in order",
          text.index("1. Test chatbot A") < text.index("2. Test chatbot B")
          < text.index("3. Test chatbot C"))
    check("... the goal word for word, marked as sent to each",
          "These words will be sent first to each of them, exactly as written:" in text
          and f"\n{GOAL}\n" in text)
    check("... the limits per chatbot and in all",
          "at most 2 messages to each chatbot, the goal included (6 in all)" in text
          and "at most 5 minutes with each chatbot (15 in all" in text, text)
    check("... the never-send words and the built-in list", f'"{NEVER}"' in text
          and CB.BUILT_IN_NEVER in text)
    check("... they never see each other's answers, one after another",
          "never see each other's answers" in text and "one after another" in text)
    check("... what happens when one drops out, and no always-allow",
          "leaves that one out and carries on with the others" in text
          and 'There is no "always allow"' in text)
    check("... and what saying no costs", text.endswith(
        "If you say no: nothing is sent, and no chatbot window is opened."))
    check("the card's detail names the comparison and every chatbot",
          CARDS[0][1]["compare"] == c.id and CARDS[0][1]["chatbot"] == "fake_a,fake_b,fake_c"
          and CARDS[0][1]["digest"] == c.digest)
    check("every chatbot was asked, one after another, the goal first to each",
          all(b.sent and b.sent[0] == GOAL and b.opened == 1 and b.closed == 1
              for b in bots.values()) and c.state == "done", c.state)
    check("... each within its own limit", all(len(b.sent) == 2 for b in bots.values()),
          {k: len(b.sent) for k, b in bots.items()})


def t_no_yes_no_comparison():
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    c, d, code, out = go(bots, d=deps(bots, gate=deny))
    check("a no sends nothing to any chatbot and opens nothing",
          all(not b.sent and not b.opened for b in bots.values()) and c.state == "refused")
    check("... and every conversation in it is refused",
          all(m.state == "refused" for m in c.members))
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}

    def broken(a, det, pr):
        raise RuntimeError("gate down")
    c, *_ = go(bots, d=deps(bots, gate=broken))
    check("a gate that fails is a no", all(not b.sent for b in bots.values())
          and c.state == "refused")
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    c, *_ = go(bots, d=deps(bots, gate=lambda a, det, pr: Verdict(True, "auto", "auto")))
    check("a yes nobody gave is a no", all(not b.sent for b in bots.values()))
    clean()
    TIERS[CB.ACTION] = "auto"
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    c, d, code, out = go(bots)
    check("the action at tier auto raises no card and sends nothing",
          not CARDS and all(not b.sent for b in bots.values()) and c.state == "refused")
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    c = CMP.plan(list(bots), GOAL, deps=deps(bots))
    check("run() without the card's yes sends nothing",
          CMP.run(c, approved=True)["ok"] is False and all(not b.sent for b in bots.values()))


def t_clean_context_per_chatbot():
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b", "fake_c")}
    m = Model()
    c, *_ = go(bots, d=deps(bots, m), max_turns=3)
    names = [n for n, _ in list(BOTS.values())[:3]]
    ok = True
    for body in m.moves_for():
        text = json.dumps(body)
        seen = [n for n in names if n in text]
        others = [w for cid, says in SAYS.items() for w in says if w.split()[0] not in text]
        if len(seen) != 1 or not others:
            ok = False
        if body.get("tools") or "tools" in body:
            ok = False
        if body["messages"][0]["content"] != CB.FIXED_INSTRUCTION:
            ok = False
    check("each driver request is about ONE chatbot, and holds none of the others' words",
          ok and len(m.moves_for()) == 6, len(m.moves_for()))
    for body in m.moves_for():
        user = body["messages"][1]["content"]
        who = next(n for n in names if n in user)
        foreign = [s for cid, says in SAYS.items() if BOTS[cid][0] != who for s in says
                   if s in user]
        if foreign:
            check("no chatbot's words reach another's driver", False, foreign)
            break
    else:
        check("no chatbot's words reach another's driver", True)
    check("the conversations never wrote summaries of their own (the model would have raised)",
          all(not m2.summary.get("by_model") for m2 in c.members))


def t_last_check_on_every_chatbot():
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    c = CMP.plan(list(bots), "Ask it what it knows about " + FAKE_EMAIL, deps=deps(bots))
    check("a goal the last check refuses raises no card",
          "the goal cannot be sent" in c.problem and "email address" in c.problem
          and not CARDS, c.problem)

    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b", "fake_c")}

    def leaky(body, n):
        user = body["messages"][1]["content"]
        if "Test chatbot B" in user:
            return {"move": "deeper", "message": f"And what about {NEVER}?", "reason": "",
                    "notes": ""}
        return None
    c, *_ = go(bots, d=deps(bots, Model(moves=leaky)), max_turns=3, never_send=[NEVER])
    sent_all = [t for b in bots.values() for t in b.sent]
    check("a never-send word reaches no chatbot", not any(NEVER in t for t in sent_all),
          sent_all)
    b_member = c.members[1]
    check("... the chatbot whose next message was blocked twice was left out",
          b_member.ended_code == "needs_owner" and "blocked twice" in b_member.ended_words
          and bots["fake_b"].closed == 1, (b_member.ended_code, b_member.ended_words))
    check("... and the others carried on", len(bots["fake_c"].sent) == 3
          and c.state == "done", (len(bots["fake_c"].sent), c.state))
    check("... and the summary says it dropped out",
          any(x["who"] == "Test chatbot B" and "blocked twice" in x["why"]
              for x in c.summary["dropped"]), c.summary["dropped"])

    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    FACT = "The owner's sister is called Zyl" + "vana"

    def repeat_fact(body, n):
        if "Test chatbot A" in body["messages"][1]["content"] and n == 1:
            return {"move": "deeper", "message": "Does Zyl" + "vana like ferns?", "reason": "",
                    "notes": ""}
        return None
    c, *_ = go(bots, d=deps(bots, Model(moves=repeat_fact), facts=[FACT]), max_turns=2)
    check("a saved fact is caught by the same last check for every chatbot",
          not any("Zyl" + "vana" in t for b in bots.values() for t in b.sent)
          and len(bots["fake_a"].sent) == 2, bots["fake_a"].sent)


def t_one_failing_does_not_stop_the_others():
    clean()

    class Broken(CB.FakeChatbot):
        def open(self):
            raise RuntimeError("the window would not open")
    bots = {"fake_a": bot("fake_a"), "fake_b": Broken(), "fake_c": bot("fake_c")}
    c, *_ = go(bots, max_turns=2)
    check("a chatbot whose window fails is left out; the others are all asked",
          len(bots["fake_a"].sent) == 2 and len(bots["fake_c"].sent) == 2
          and not bots["fake_b"].sent and c.state == "done")
    check("... and the summary says which one and why",
          [x["who"] for x in c.summary["dropped"]] == ["Test chatbot B"]
          and "could not be worked" in c.summary["dropped"][0]["why"], c.summary["dropped"])
    check("... and it was written by the model from the ones that answered",
          c.summary["by_model"] is True
          and c.summary["answered"] == ["Test chatbot A", "Test chatbot C"])

    clean()
    bots = {"fake_a": bot("fake_a", statuses={1: CB.Status("needs_owner", "captcha")}),
            "fake_b": bot("fake_b")}
    c, *_ = go(bots, max_turns=3)
    a = c.members[0]
    check("a captcha leaves that chatbot out (never solved), its window closed",
          a.state == "done" and a.ended_code == "needs_owner" and "captcha" in a.ended_words
          and "never solves or skips" in a.ended_words and bots["fake_a"].closed == 1,
          (a.state, a.ended_words))
    check("... the other carried on, and the comparison did not pause",
          len(bots["fake_b"].sent) == 3 and c.state == "done" and TC.paused() is None)

    clean()
    bots = {"fake_a": bot("fake_a", replies=["Could you tell me your full name and age?"]),
            "fake_b": bot("fake_b")}
    c, *_ = go(bots, max_turns=3)
    check("a chatbot that asks about the owner is left out; its question kept, never answered",
          c.members[0].ended_code == "asked_personal" and c.members[0].question
          and len(bots["fake_a"].sent) == 1 and len(bots["fake_b"].sent) == 3)


def t_stop_stops_all():
    clean()
    holder = {}
    bots = {"fake_a": bot("fake_a"),
            "fake_b": bot("fake_b", on_send=lambda t, n: n == 1 and holder.update(
                out=CMP.stop(holder["id"]))),
            "fake_c": bot("fake_c")}
    d = deps(bots)
    c = CMP.plan(list(bots), GOAL, deps=d, max_turns=3)
    holder["id"] = c.id
    CMP.start(c, deps=d, wait=True)
    check("Stop: the chatbot being asked stops before its next message",
          len(bots["fake_b"].sent) == 1 and bots["fake_b"].closed == 1, bots["fake_b"].sent)
    check("... the ones not asked yet are never opened", not bots["fake_c"].opened
          and c.members[2].state == "stopped" and "Not asked" in c.members[2].ended_words)
    check("... the whole comparison is stopped, with no model summary",
          c.state == "stopped" and c.summary["by_model"] is False
          and "you stopped it" in c.summary["answer"], c.summary.get("answer"))
    check("... and the stop answered plainly", holder["out"][0] == 200
          and "Nothing more is sent to any of the chatbots" in holder["out"][1]["message"])

    clean()
    bots = {"fake_a": bot("fake_a", on_send=lambda t, n: n == 2 and SA.stop_all("test")),
            "fake_b": bot("fake_b")}
    c, *_ = go(bots, max_turns=3)
    check("Stop everything stops the whole comparison", c.state == "stopped"
          and len(bots["fake_a"].sent) == 2 and not bots["fake_b"].opened, c.state)
    check("the comparison's stopper is registered", CMP.STOPPER in SA.registered())

    clean()
    bots = {"fake_a": bot("fake_a", on_send=lambda t, n: n == 1 and TC.handle_post(
        "/api/task/stop", {})), "fake_b": bot("fake_b")}
    c, *_ = go(bots, max_turns=3)
    check("the task Stop stops the whole comparison", c.state == "stopped"
          and not bots["fake_b"].opened)

    clean()
    holder = {}
    bots = {"fake_a": bot("fake_a", on_send=lambda t, n: n == 1 and holder.update(
        out=R.handle_post(R.STOP_ROUTE, {"id": holder["member"]}))), "fake_b": bot("fake_b")}
    d = deps(bots)
    c = CMP.plan(list(bots), GOAL, deps=d, max_turns=3)
    holder["member"] = c.members[0].id
    CMP.start(c, deps=d, wait=True)
    check("/api/chatbot/stop with one conversation's id stops the whole comparison",
          c.state == "stopped" and not bots["fake_b"].opened
          and holder["out"][0] == 200, holder.get("out"))

    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    d = deps(bots)
    c = CMP.plan(list(bots), GOAL, deps=d)

    def stop_while_card_waits(a, det, pr):
        SA.stop_all("test")
        return Verdict(True, "approved")
    d.gate = stop_while_card_waits
    CMP.start(c, deps=d, wait=True)
    check("a stop pressed while the card waited wins over its approval",
          c.state == "stopped" and all(not b.sent for b in bots.values()), c.state)


def t_pause_and_resume_the_whole():
    clean()
    bots = {"fake_a": bot("fake_a"),
            "fake_b": bot("fake_b", on_send=lambda t, n: n == 1 and TC.handle_post(
                "/api/task/pause", {})),
            "fake_c": bot("fake_c")}
    c, d, *_ = go(bots, max_turns=3)
    p = TC.paused()
    check("Pause pauses the whole comparison, as one task",
          c.state == "paused" and p is not None and p["tool"] == "chatbot_compare"
          and p["steps_done"] == 4 and p["steps_left"] == 5, (c.state, p))
    check("... the reply on its way was kept, and the next chatbot was not opened",
          c.members[1].transcript[-1]["who"] == "chatbot" and not bots["fake_c"].opened)
    rv = R.handle_get("", deps=d)[1]
    check("... and the status shows the comparison paused, not a single conversation",
          rv["session"] is None and rv["compare"]["state"] == "paused"
          and rv["compare"]["paused"] == CMP.PAUSED_WORDS)
    keep = CB.DEPS
    CB.DEPS = d
    cards = []
    try:
        TC.resume("test", wait=True, gate_check=lambda a, det, pr: cards.append((a, det))
                  or Verdict(True, "approved"))
    finally:
        CB.DEPS = keep
    text = cards[0][1]["text"] if cards else ""
    check("Resume is one card under chatbot_session, naming every chatbot",
          len(cards) == 1 and cards[0][0] == "chatbot_session"
          and "Carry on the comparison of Test chatbot A, Test chatbot B, Test chatbot C"
          in text and "4 messages already went" in text, text[:300])
    check("... showing what each one has done so far",
          "Test chatbot A: finished, 3 messages sent." in text
          and "Test chatbot B: 1 of 3 messages sent so far." in text
          and "Test chatbot C: not asked yet." in text, text)
    live = CMP.get(c.id)
    check("... and on yes it carried on to the end",
          live.state == "done" and len(bots["fake_b"].sent) == 3
          and len(bots["fake_c"].sent) == 3 and bots["fake_b"].opened == 1, live.state)

    clean()
    bots = {"fake_a": bot("fake_a", on_send=lambda t, n: n == 1 and TC.handle_post(
        "/api/task/pause", {})), "fake_b": bot("fake_b")}
    c, d, *_ = go(bots)
    code, out = CMP.stop(c.id, deps=d)
    check("stopping a paused comparison ends it at once and closes the window",
          code == 200 and c.state == "stopped" and bots["fake_a"].closed == 1
          and not bots["fake_b"].opened)


def t_the_summary():
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    m = Model()
    c, *_ = go(bots, d=deps(bots, m), max_turns=3)
    s = c.summary
    check("ONE summary, written once by the local model", len(m.summaries()) == 1
          and s["by_model"] is True)
    body = m.summaries()[0]
    user = body["messages"][1]["content"]
    check("... from the goal and each conversation, headed by name, no tools",
          GOAL in user and "=== Test chatbot A ===" in user and "=== Test chatbot B ===" in user
          and "tools" not in body, user[:200])
    check("the disagreement names who said what (names matched as asked)",
          s["disagree"] == [{"point": "Whether calatheas suit a dark flat",
                             "views": [{"who": "Test chatbot A",
                                        "said": "Low-light plants are fine"},
                                       {"who": "Test chatbot B",
                                        "said": "Calatheas need bright light"}]}],
          s["disagree"])
    check("... a view from an AI that was never asked is dropped", "Bard" not in json.dumps(s)
          and "Nobody" not in json.dumps(s))
    check("where they agree, and what is still open", s["agree"] == [SUMMARY["agree"][0]]
          and s["open"] == ["Which grow lamp to buy"])
    srcs = {x["who"]: x["items"] for x in s["sources"]}
    check("the sources each gave: the addresses found in its own replies, plus the model's",
          srcs.get("Test chatbot A") == ["https://example.org/snake-plants"]
          and srcs.get("Test chatbot B") == ["https://example.net/guide",
                                             "university extension services"], srcs)
    check("... every source marked not checked by Jarvis",
          s["sources_checked"] is False and all(x["checked"] is False for x in s["sources"]))
    check("the summary is outside text, never read aloud",
          s["outside_text"] is True and s["read_aloud"] is False and s["source"] == CB.SOURCE)
    check("nobody dropped out", s["dropped"] == [])

    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    m = Model(summary={"answer": "x"})
    c, *_ = go(bots, d=deps(bots, m), max_turns=1)
    check("a summary with missing parts keeps the rest empty",
          c.summary["answer"] == "x" and c.summary["agree"] == [] and c.summary["disagree"] == [])

    clean()

    class Broken(CB.FakeChatbot):
        def open(self):
            raise RuntimeError("no")
    bots = {"fake_a": Broken(), "fake_b": Broken()}
    m = Model()
    c, *_ = go(bots, d=deps(bots, m))
    check("nobody answered: no model call, and the summary says so plainly",
          not m.summaries() and "None of the chatbots answered" in c.summary["answer"]
          and len(c.summary["dropped"]) == 2)

    clean()
    busy = {"on": True}
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    m = Model()
    c, *_ = go(bots, d=deps(bots, m, busy=lambda: busy["on"]), max_turns=1)
    check("on one card the summary waits for the owner's chat, then goes without the model",
          not m.summaries() and c.summary["by_model"] is False and c.state == "done")


def t_one_at_a_time():
    clean()
    bots = {"fake_a": bot("fake_a", on_send=lambda t, n: n == 1 and TC.handle_post(
        "/api/task/pause", {})), "fake_b": bot("fake_b")}
    c, d, *_ = go(bots)
    single = CB.plan("fake_c", GOAL, deps=d)
    check("a single conversation cannot start while a comparison is paused",
          "still running or paused" in single.problem, single.problem)
    code, out = R.handle_post(R.START_ROUTE, {"chatbot": "fake_c", "goal": GOAL}, deps=d)
    check("... the route says so (409)", code == 409 and "comparison" in out["error"], out)
    again = CMP.plan(["fake_c", "fake_d"], GOAL, deps=d)
    check("a second comparison cannot start either", "another comparison" in again.problem)
    CMP.stop(c.id, deps=d)

    clean()
    bots = {"fake_a": bot("fake_a", statuses={1: CB.Status("needs_owner", "captcha")})}
    d = deps(bots)
    s = CB.plan("fake_a", GOAL, deps=d)
    CB.start(s, deps=d, wait=True)
    c = CMP.plan(["fake_b", "fake_c"], GOAL, deps=d)
    check("a comparison cannot start while a single conversation is paused",
          "another chatbot conversation" in c.problem, c.problem)
    code, out = R.handle_post(R.COMPARE_START_ROUTE, {"chatbots": ["fake_b", "fake_c"],
                                                      "goal": GOAL}, deps=d)
    check("... the route says so (409)", code == 409 and out["error"].startswith("Another"),
          out)


def t_routes():
    clean()
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    d = deps(bots)
    code, out = R.handle_get("", deps=d)
    check("status carries no comparison when none is going, and the per-version numbers",
          code == 200 and out["compare"] is None and out["tier"]["compare_min"] == 2
          and out["tier"]["compare_max"] == 3, out.get("tier"))
    code, out = R.handle_post(R.COMPARE_START_ROUTE, {"chatbots": ["fake_a"], "goal": GOAL},
                              deps=d, wait=True)
    check("too few is a 400 in the apps' own sentence, and no card",
          code == 400 and out["error"] == R.WORDS["compare_too_few"].format(min=2)
          and not CARDS, out)
    code, out = R.handle_post(R.COMPARE_START_ROUTE,
                              {"chatbots": ["fake_a", "fake_b", "fake_c", "fake_d"],
                               "goal": GOAL}, deps=d, wait=True)
    check("too many is a 400 in the apps' own sentence",
          code == 400 and out["error"] == R.WORDS["compare_too_many"].format(max=3), out)
    code, out = R.handle_post(R.COMPARE_START_ROUTE, {"chatbots": "fake_a", "goal": GOAL},
                              deps=d, wait=True)
    check("a single id as text is not a list of two", code == 400)
    code, out = R.handle_post(R.COMPARE_START_ROUTE, {"chatbots": ["fake_a", "../x"],
                                                      "goal": GOAL}, deps=d, wait=True)
    check("a bad id is refused", code == 400 and "named by its id" in out["error"], out)
    code, out = R.handle_post(R.COMPARE_START_ROUTE,
                              {"chatbots": ["fake_a", "fake_b"], "goal": GOAL,
                               "max_messages": 2, "never_send": [NEVER]}, deps=d, wait=True)
    check("a good start answers 202 with the comparison's id",
          code == 202 and out["compare"].startswith("cmp_") and len(CARDS) == 1, out)
    cid = out["compare"]
    code, got = R.handle_get(f"compare={cid}", deps=d)
    cv = got["compare"]
    check("status by id shows the comparison, every conversation and the summary",
          cv["id"] == cid and cv["state"] == "done" and cv["count"] == 2
          and [m["name"] for m in cv["members"]] == ["Test chatbot A", "Test chatbot B"]
          and all(m["compare"] == cid for m in cv["members"])
          and cv["summary"]["by_model"] is True and cv["read_aloud"] is False
          and cv["never_send"] == [NEVER] and cv["messages_used"] == 4, cv)
    check("... every chatbot turn in it is outside text",
          all(t["outside_text"] is True for m in cv["members"] for t in m["transcript"]
              if t["who"] == "chatbot"))
    check("... and 'the latest conversation' is never one of a comparison's",
          got["session"] is None)
    check("a bad comparison id is a 400", R.handle_get("compare=cmp_../x", deps=d)[0] == 400)
    check("an unknown comparison reads as none", R.handle_get(
        "compare=cmp_0000000000ff", deps=d)[1]["compare"] is None)
    code, out = R.handle_post(R.COMPARE_STOP_ROUTE, {"id": cid}, deps=d)
    check("stopping an ended comparison says so", code == 409
          and out["error"] == "That comparison has already ended.", out)
    code, out = R.handle_post(R.COMPARE_STOP_ROUTE, {"id": "nope"}, deps=d)
    check("a stop needs a comparison id", code == 400
          and out["error"] == "Say which comparison to stop.")
    code, out = R.handle_post(R.COMPARE_STOP_ROUTE, {"id": "cmp_0000000000ff"}, deps=d)
    check("an unknown comparison is a 404", code == 404
          and out["error"] == "No such comparison.")
    check("both new routes are POST routes the install() wrapper answers",
          R.COMPARE_START_ROUTE in R.POST_ROUTES and R.COMPARE_STOP_ROUTE in R.POST_ROUTES)

    clean()
    TIERS[CB.ACTION] = "never"
    bots = {k: bot(k) for k in ("fake_a", "fake_b")}
    code, out = R.handle_post(R.COMPARE_START_ROUTE, {"chatbots": list(bots), "goal": GOAL},
                              deps=deps(bots), wait=True)
    check("switched off (never): a 409, no card", code == 409 and not CARDS
          and "switched off" in out["error"], out)


def t_hardening():
    clean()
    bots = {"fake_a": bot("fake_a", on_send=lambda t, n: n == 1 and TC.handle_post(
        "/api/task/pause", {})), "fake_b": bot("fake_b")}
    c, d, *_ = go(bots, max_turns=3)
    mid = c.members[0].id
    code, out = R.handle_post(R.LIMITS_ROUTE, {"id": mid, "max_messages": 5}, deps=d,
                              spawn=lambda fn: fn())
    check("a comparison's conversation cannot have its limits changed on its own (route)",
          code == 409 and "stop it and start a new one" in out["error"] and len(CARDS) == 1,
          out)
    code, out = CB.change_limits(mid, max_turns=5, deps=d)
    check("... nor through the core", code == 409 and c.members[0].limits.max_turns == 3, out)
    keep = CB.DEPS
    CB.DEPS = d
    try:
        TC.resume("test", wait=True, gate_check=lambda a, det, pr: Verdict(True, "approved"))
    finally:
        CB.DEPS = keep
    check("... so its Resume still runs it to the end", c.state == "done"
          or CMP.get(c.id).state == "done", CMP.get(c.id).state)

    clean()
    CB.register_adapter(CB.AdapterInfo("fake_twin", "Test chatbot A", "twin.example",
                                       CB.FakeChatbot, test_only=True))
    bots = {"fake_a": bot("fake_a"), "fake_twin": bot("fake_b")}
    c = CMP.plan(["fake_a", "fake_twin"], GOAL, deps=deps(bots))
    check("two chatbots with the same name are refused (who said what must be clear)",
          "same name" in c.problem and not CARDS, c.problem)
    CB.ADAPTERS.pop("fake_twin", None)

    clean()
    bots = {"fake_a": bot("fake_a", statuses={1: CB.Status("needs_owner", "captcha")})}
    d = deps(bots)
    s = CB.plan("fake_a", GOAL, deps=d)
    CB.start(s, deps=d, wait=True)
    TC.handle_post("/api/task/stop", {})         # forgets the paused conversation
    c = CMP.plan(["fake_b", "fake_c"], GOAL, deps=d)
    check("a paused conversation nobody can resume no longer blocks a comparison",
          not c.problem and s.state == "stopped", (c.problem, s.state))


def t_a_paused_comparison_nobody_can_resume_is_ended():
    clean()
    bots = {"fake_a": bot("fake_a", on_send=lambda t, n: n == 1 and TC.handle_post(
        "/api/task/pause", {})), "fake_b": bot("fake_b")}
    c, d, *_ = go(bots)
    TC.handle_post("/api/task/stop", {})         # forgets the paused task
    t = {"now": 100.0}
    keep = R._now
    R._now = lambda: t["now"]
    try:
        R.handle_get("", deps=d)
        check("just after: not yet ended (it may be being handed over)", c.state == "paused")
        t["now"] += R.UNHELD_GRACE + 1
        R.handle_get("", deps=d)
    finally:
        R._now = keep
    check("after the grace: ended, its window closed", c.state == "stopped"
          and bots["fake_a"].closed == 1 and "could no longer be resumed" in c.ended_words)


def t_shipped_and_documented():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("shipped: in _where.SHIPPED and apply-patches.ps1",
          "jarvis_chatbot_compare.py" in SHIPPED and "'jarvis_chatbot_compare.py'" in ps1)
    check("apply-patches.ps1 stays ASCII", all(ord(ch) < 128 for ch in ps1))
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("JARVIS-API.md documents both routes",
          "/api/chatbot/compare/start" in api and "/api/chatbot/compare/stop" in api)
    design = (REPO / "docs" / "CHATBOT-DRIVER-DESIGN.md").read_text(encoding="utf-8")
    check("the design doc has the numbers the owner confirmed (2026-09-28)",
          "Ask several and compare" in design
          and "The limits (confirmed by the owner, 2026-09-28)" in design)


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
        clean()
        for cid in BOTS:
            CB.ADAPTERS.pop(cid, None)
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
