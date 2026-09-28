#!/usr/bin/env python3
"""Writes the "Chat with customer support for me" contract file for both
apps, and checks it.

    python3 tools/gen_support_cases.py            # write both copies
    python3 tools/gen_support_cases.py --check    # compare only

What GET /api/chatbot/status (its `support`, `companies` and `support_tier`)
and POST /api/chatbot/support/start, /stop, /takeover, /answer and GET
/api/chatbot/support/export really answer (backend/jarvis_chatbot_routes.py
over jarvis_support.py), in named situations, made by the real routes and
the real support loop with a clock moved by hand, a stand-in driver model, a
stand-in approval gate and jarvis_support.FakeWidget as the company's chat -
nothing is written by hand:

    jarvis-desktop/tests/fixtures/support-cases.json
    jarvis-client/app/src/test/resources/contract/support-cases.json

(byte-identical). The desktop's tests/support.mjs and the phone's SupportTest
build against it, and both check their words against `words`
(jarvis_support.WORDS). The stand-in chat is registered under Groupon's own
preset (its name, help page and terms words) - a test double, not a claim
that Groupon's chat works: nothing has been tried against the real site.

Support chat ids are numbered here (sup_000000000001, ...), the clock starts
at a fixed moment and the time zone is UTC, so the file is the same on every
run and every machine.
"""
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-support-cases-"))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.load_framework = lambda: {}
_fw.audit_log = lambda *a, **k: None
_fw.action_tier = lambda a: "ask"
sys.modules["jarvis_framework"] = _fw

import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402
import jarvis_support as S  # noqa: E402
import jarvis_task_control as TC  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "support-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "support-cases.json")
COPIES = (DESKTOP, PHONE)

ORDER = "4481" + "902217"
EMAIL = "alex.q" + "@" + "example.net"
DETAILS = [{"name": "Order number", "value": ORDER}, {"name": "Email", "value": EMAIL}]
GOAL = "Get a refund for my spa voucher: the spa closed before I could use it."
OPENING = "Hi, I bought a spa voucher and the spa has closed. Could I get a refund?"
ORDER_Q = "Hi, I'm Priya from Groupon. Could I have your order number please?"
OFFER = ("Thank you. I can offer you a full refund of $45 to your original payment method. "
         "Would you like me to go ahead?")
SUMMARY = {"answer": "Groupon agreed to refund $45 to the original payment method.",
           "agreed": ["A full refund of $45"], "open": []}


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, float(s))


class Verdict:
    def __init__(self, allowed, outcome):
        self.allowed, self.outcome, self.tier = allowed, outcome, "ask"


class Model:
    def __init__(self, moves):
        self.moves = list(moves)

    def __call__(self, url, body):
        if body.get("format") == S.SUMMARY_SCHEMA:
            return {"message": {"content": json.dumps(SUMMARY)}}
        mv = {"move": "wait", "message": "", "option": "", "reason": "", "notes": ""}
        if self.moves:
            mv.update(self.moves.pop(0))
        return {"message": {"content": json.dumps(mv)}}


def reply(text):
    return {"move": "reply", "message": text}


_N = [0]


def _next_id():
    _N[0] += 1
    return f"sup_{_N[0]:012x}"


S._new_id = _next_id


def fresh():
    S._reset_for_tests()
    CB._reset_for_tests()
    R._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()


def world(widget, *, moves=(), gate=None, spawn=None):
    clock = Clock()
    d = S.Deps(model=Model(moves), saved_facts=lambda m: [], names_for_facts=lambda f: {},
               owner_busy=lambda: False, second_lane=lambda: None,
               full_version_on=lambda: False,
               main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
               tier_of=lambda a: "ask",
               gate=gate or (lambda a, det, pr: Verdict(True, "approved")),
               activity=lambda s, dt="": None, audit=lambda e, dt: None, clock=clock,
               sleep=clock.sleep, make_widget=lambda c: widget,
               spawn=spawn or (lambda fn: fn()), history=lambda rec: "")
    S.DEPS = d
    return d


def answer(code_body):
    code, body = code_body
    return {"code": code, "body": body}


def status(d, sid=""):
    code, body = R.handle_get(f"support={sid}" if sid else "", deps=d)
    assert code == 200, (code, body)
    return {k: body[k] for k in ("support", "companies", "support_tier", "routed")}


def start(d, **extra):
    body = {"company": "groupon", "goal": GOAL, "details": DETAILS}
    body.update(extra)
    return R.handle_post(R.SUPPORT_START_ROUTE, body, deps=d, wait=True)


def cases() -> dict:
    out = {"words": dict(S.WORDS), "offer_accept_line": S.ACCEPT_LINE,
           "decline_line": S.DECLINE_LINE, "hold_line": S.HOLD_LINE}

    # Refused before any card: a password row.
    fresh()
    d = world(S.FakeWidget())
    out["nothing"] = status(d)
    out["start_refused_detail"] = answer(start(d, details=[{"name": "Password",
                                                            "value": "x"}]))
    out["start_bad_address"] = answer(start(d, company="other",
                                            address="http://help.example.com"))

    # A whole chat: the card waiting, the queue, the offer waiting on its
    # card, then finished with a reference and the summary.
    fresh()
    snap = {}

    def gate_sees(a, det, pr):
        if a == S.ACTION:
            snap.setdefault("asking", status(d))
        return Verdict(True, "approved")
    held = []

    def on_read(n):
        c = next(iter(S._CHATS.values()), None)
        if c is None:
            return
        if c.in_queue and "queue" not in snap:
            snap["queue"] = status(d)
        if c.offer is not None and "offer" not in snap:
            snap["offer"] = status(d)
            held.pop()()
    w = S.FakeWidget({
        1: ["You are number 2 in the queue.", "Priya joined the chat.", ORDER_Q],
        2: [OFFER],
        3: ["Done, the refund is on its way. Is there anything else I can help you with?"],
        4: ["Your reference number is GRP48213.", "This chat has ended."],
    }, on_read=on_read)
    d = world(w, moves=[reply(OPENING), reply(f"It's {ORDER}.")], gate=gate_sees,
              spawn=held.append)
    started = start(d)
    out["start_asking"] = answer(started)
    sid = started[1]["support"]
    out["asking"] = snap["asking"]
    out["in_queue"] = snap["queue"]
    out["offer_waiting"] = snap["offer"]
    out["done"] = status(d, sid)
    out["export"] = answer(R.handle_export(f"id={sid}"))
    out["stop_ended"] = answer(R.handle_post(R.SUPPORT_STOP_ROUTE, {"id": sid}, deps=d))

    # An offer card that says no: the offer waits for Decline / Say / Take
    # over; "accept" is refused.
    fresh()
    snap = {}

    def on_read_no(n):
        c = next(iter(S._CHATS.values()), None)
        if c is None or c.offer is None or "no" in snap:
            return
        if c.offer.get("verdict"):
            snap["no"] = status(d)
            snap["accept"] = answer(R.handle_post(R.SUPPORT_ANSWER_ROUTE, {
                "id": c.id, "offer": c.offer["id"], "choice": "accept"}, deps=d))
            snap["say_yes"] = answer(R.handle_post(R.SUPPORT_ANSWER_ROUTE, {
                "id": c.id, "offer": c.offer["id"], "choice": "say",
                "text": "Yes please."}, deps=d))
            snap["decline"] = answer(R.handle_post(R.SUPPORT_ANSWER_ROUTE, {
                "id": c.id, "offer": c.offer["id"], "choice": "decline"}, deps=d))
    w = S.FakeWidget({1: [OFFER], 2: ["No problem. This chat has ended."]},
                     on_read=on_read_no)
    d = world(w, moves=[reply(OPENING)],
              gate=lambda a, det, pr: Verdict(a == S.ACTION,
                                              "approved" if a == S.ACTION else "denied"))
    sid = start(d)[1]["support"]
    out["offer_card_no"] = snap["no"]
    out["answer_accept_refused"] = snap["accept"]
    out["answer_say_yes_refused"] = snap["say_yes"]
    out["answer_decline"] = snap["decline"]
    out["declined_done"] = status(d, sid)

    # "Are you a bot?": paused and handed to the owner.
    fresh()
    w = S.FakeWidget({1: ["Quick check - am I talking to a bot or a real person?"]})
    d = world(w, moves=[reply(OPENING)])
    sid = start(d)[1]["support"]
    out["paused_bot_question"] = status(d)
    out["takeover_while_paused"] = answer(R.handle_post(R.SUPPORT_TAKEOVER_ROUTE,
                                                        {"id": sid}, deps=d))

    # An identity check: handed over.
    fresh()
    w = S.FakeWidget({1: ["For security, please confirm the last 4 digits of the card."]})
    d = world(w, moves=[reply(OPENING)])
    start(d)
    out["paused_identity"] = status(d)

    # Take over: paused by the owner's own tap.
    fresh()
    took = {}

    def on_read_take(n):
        c = next(iter(S._CHATS.values()), None)
        if c is not None and n == 1 and not took:
            took["a"] = answer(R.handle_post(R.SUPPORT_TAKEOVER_ROUTE, {"id": c.id}, deps=d))
    w = S.FakeWidget({1: ["Hi, how can I help?"]}, on_read=on_read_take)
    d = world(w, moves=[reply(OPENING)])
    start(d)
    out["takeover_answer"] = took["a"]
    out["paused_takeover"] = status(d)

    # A chat the window never opened.
    fresh()
    w = S.FakeWidget(statuses={0: CB.Status("needs_owner", S.NO_CHAT)})
    d = world(w)
    sid = start(d)[1]["support"]
    out["no_chat"] = status(d, sid)
    out["gone"] = status(d, "sup_0000000000ff")
    return out


def render() -> str:
    _N[0] = 0
    return json.dumps(cases(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        bad = [str(p.relative_to(ROOT)) for p in COPIES
               if not p.is_file() or p.read_text(encoding="utf-8") != text]
        if bad:
            print("out of date (run python3 tools/gen_support_cases.py): " + ", ".join(bad))
            return 1
        print("support cases: both copies up to date")
        return 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
