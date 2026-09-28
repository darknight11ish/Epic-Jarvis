"""test_chatbot_routes.py - the routes both apps use for "Talk to a chatbot
for me" (jarvis_chatbot_routes.py, chatbot-routes.patch; docs/JARVIS-API.md
section 60).

    python3 backend/test_chatbot_routes.py

Runs anywhere; no model, no website, no socket. The REAL jarvis_chatbot,
jarvis_task_control and jarvis_stop_all, with a stand-in driver model, a
stand-in approval gate, a clock moved by hand and jarvis_chatbot.FakeChatbot
registered under Gemini's own entry. What it proves:

1. GET /api/chatbot/status: the chatbots (Gemini listed, "Not built yet."),
   which version runs, the conversation and its transcript - every chatbot
   turn and the summary marked outside text, never read aloud; a bad id is
   refused; `routed` is true.
2. POST /api/chatbot/start: nothing is sent before a person's yes (a no, or
   a gate that fails, sends nothing); a goal or limit plan() refuses is a 400
   in a plain sentence and raises no card; one conversation at a time (409);
   the feature switched off ("never") is a 409 with no card.
3. POST /api/chatbot/stop: never a card; a bad or unknown id says so.
4. POST /api/chatbot/limits: answers 202 at once, asks a NEW card on its own
   thread, and changes nothing unless a person says yes; the outcome rides
   on the next GET; a bad number is a 400 now; a second change while a card
   waits is a 409.
5. install(): the four routes are answered after the server's own origin and
   token checks; everything else passes through; installing twice does not
   wrap twice.
6. chatbot-routes.patch applies after the rest of the stack and reverses; both
   shipped lists hold the module; the contract file both apps read is up to
   date (tools/gen_chatbot_cases.py --check).
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_chatbot.py", "jarvis_chatbot_routes.py", "jarvis_task_control.py",
                "jarvis_stop_all.py", "jarvis_search.py", "jarvis_mail_mask.py",
                "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chatbot-routes-"))
TIERS: dict = {}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

import _stack  # noqa: E402
import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402
import jarvis_task_control as TC  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


GOAL = "Find out how to keep houseplants alive in a flat that gets very little light."
REPLIES = ["Snake plants and ZZ plants tolerate dim corners remarkably well.",
           "A grow lamp gives steady light; a windowsill changes with the seasons.",
           "Pothos, snake plants and ZZ plants are the easiest three."]
QUESTIONS = ["Which plants cope best with a north-facing window?",
             "How does a grow lamp compare with moving plants closer to the glass?",
             "Could you narrow that down to plants that are safe around cats?"]
SHIPPED_GEMINI = CB.ADAPTERS["gemini_web"]


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, float(s))


class Verdict:
    def __init__(self, allowed, outcome):
        self.allowed, self.outcome, self.tier = allowed, outcome, "ask"


CARDS: list = []


def approve(action, detail, prompt):
    CARDS.append((action, detail))
    return Verdict(True, "approved")


def deny(action, detail, prompt):
    CARDS.append((action, detail))
    return Verdict(False, "denied")


def model(url, body):
    if body.get("format") == CB.SUMMARY_SCHEMA:
        return {"message": {"content": json.dumps(
            {"answer": "Use a low-light plant.", "claims": [], "open": []})}}
    n = sum(1 for m in body.get("messages", []) if m.get("role") == "user")
    return {"message": {"content": json.dumps(
        {"move": "deeper", "message": QUESTIONS[n % len(QUESTIONS)], "reason": "",
         "notes": "n"})}}


def fresh():
    CB._reset_for_tests()
    R._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()
    CB.register_adapter(SHIPPED_GEMINI)
    CARDS.clear()
    TIERS.clear()


def world(bot=None, gate=approve):
    clock = Clock()
    d = CB.Deps(model=model, saved_facts=lambda m: [], names_for_facts=lambda f: {},
                owner_busy=lambda: False, second_lane=lambda: None,
                full_version_on=lambda: False,
                main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
                tier_of=lambda a: TIERS.get(a, "ask"), gate=gate,
                activity=lambda s, dt="": None, audit=lambda e, dt: None,
                clock=clock, sleep=clock.sleep)
    if bot is not None:
        # The stand-in replaces Gemini's window, so Gemini's own "is the
        # window signed in?" check does not apply to it.
        CB.register_adapter(dataclasses.replace(SHIPPED_GEMINI, factory=lambda: bot,
                                                built=True, ready=None))
    return d


def start(d, *, wait=True, **extra):
    body = {"chatbot": "gemini_web", "goal": GOAL, "max_messages": 3}
    body.update(extra)
    return R.handle_post(R.START_ROUTE, body, deps=d, wait=wait)


# ==========================================================================
#   1. GET /api/chatbot/status
# ==========================================================================

def t_status():
    fresh()
    d = world()
    code, out = R.handle_get("", deps=d)
    gem = [c for c in out["chatbots"] if c["id"] == "gemini_web"]
    check("status: 200, routed, no conversation", code == 200 and out["routed"] is True
          and out["session"] is None)
    check("Gemini is listed, built, and here not ready, with the one-line fix",
          gem and gem[0]["built"] is True and gem[0]["ready"] is False
          and bool(gem[0]["note"]), gem)
    check("the test stand-in is never offered to the owner",
          not any(c["id"] == "fake" for c in out["chatbots"]))
    check("which version runs, in words, with its caps",
          out["tier"]["id"] == CB.ONE_CARD and "one graphics card" in out["tier"]["name"]
          and out["tier"]["turns_max"] == 8)
    code, out = R.handle_get("id=../../etc", deps=d)
    check("a bad id is refused", code == 400)
    code, out = R.handle_get("id=chat_0123456789ab", deps=d)
    check("an unknown id: no conversation (a restart loses them)",
          code == 200 and out["session"] is None)

    fresh()
    bot = CB.FakeChatbot(REPLIES)
    d = world(bot)
    code, out = start(d)
    sid = out["session"]
    code, out = R.handle_get(f"id={sid}", deps=d)
    s = out["session"]
    bot_turns = [t for t in s["transcript"] if t["who"] == "chatbot"]
    own = [t for t in s["transcript"] if t["who"] == "jarvis"]
    check("the transcript is there, both sides", len(bot_turns) == 3 and len(own) == 3,
          s["transcript"])
    check("every chatbot turn is outside text, from the chatbot transcript",
          all(t["outside_text"] is True and t["source"] == CB.SOURCE for t in bot_turns))
    check("Jarvis's own messages are not outside text, and the first one is the goal",
          all(t["outside_text"] is False for t in own) and own[0]["text"] == GOAL)
    check("the summary is outside text and never read aloud",
          s["summary"]["outside_text"] is True and s["summary"]["read_aloud"] is False
          and s["read_aloud"] is False)
    check("an ended conversation is not the 'latest live' one",
          R.handle_get("", deps=d)[1]["session"] is None)


# ==========================================================================
#   2. POST /api/chatbot/start
# ==========================================================================

def t_start_needs_a_yes():
    fresh()
    bot = CB.FakeChatbot(REPLIES)
    d = world(bot, gate=deny)
    code, out = start(d)
    check("start: 202, nothing sent yet, a card asked", code == 202 and out["asking"] is True
          and "Nothing has been sent yet" in out["message"])
    check("a no sends nothing and opens no window", not bot.sent and bot.opened == 0
          and len(CARDS) == 1 and CARDS[0][0] == CB.ACTION)
    s = R.handle_get(f"id={out['session']}", deps=d)[1]["session"]
    check("... and the conversation says why", s["state"] == "refused"
          and "not approved" in s["ended"])

    fresh()
    bot = CB.FakeChatbot(REPLIES)

    def broken(a, det, pr):
        raise RuntimeError("gate down")
    d = world(bot, gate=broken)
    start(d)
    check("a gate that fails is a no: nothing sent", not bot.sent)

    fresh()
    bot = CB.FakeChatbot(REPLIES)
    d = world(bot)
    code, out = start(d)
    check("a yes: the goal goes first, word for word", bot.sent and bot.sent[0] == GOAL)
    check("the card carried the goal word for word", GOAL in CARDS[0][1]["text"])

    fresh()
    d = world(CB.FakeChatbot(REPLIES))
    gate_ran = threading.Event()
    release = threading.Event()

    def waits(a, det, pr):
        gate_ran.set()
        release.wait(5)
        return Verdict(False, "denied")
    d.gate = waits
    code, out = start(d, wait=False)
    gate_ran.wait(5)
    got = R.handle_get("", deps=d)[1]["session"]
    check("the route answers at once while the card waits (state asking)",
          code == 202 and got and got["state"] == "asking")
    code2, out2 = start(d, wait=False)
    check("one conversation at a time: a second start is a 409, no second card",
          code2 == 409 and out2["session"] == out["session"] and "Another" in out2["error"])
    release.set()


def t_start_refusals_are_plain():
    fresh()
    d = world()
    code, out = start(d)
    check("Gemini not ready on this PC: 400, in a sentence", code == 400
          and isinstance(out.get("error"), str) and out["error"].endswith("."), out)
    check("... and no card", not CARDS)

    fresh()
    d = world(CB.FakeChatbot(REPLIES))
    code, out = start(d, goal="Ask about zylvana" + "@" + "example.org please")
    check("a goal the last check refuses: 400, why, no card", code == 400
          and "email address" in out["error"] and out["error"][0].isupper() and not CARDS,
          out)
    code, out = start(d, goal="")
    check("no goal: 400", code == 400 and "goal" in out["error"])
    code, out = start(d, max_messages=99)
    check("more messages than this version allows: 400", code == 400
          and "At most 8 messages" in out["error"], out)
    code, out = start(d, max_messages="five")
    check("a limit that is not a number: 400", code == 400)
    code, out = start(d, never_send="Project Nimbus")
    check("a single never-send word as text is accepted as one word", code == 202, out)

    fresh()
    TIERS[CB.ACTION] = "never"
    d = world(CB.FakeChatbot(REPLIES))
    code, out = start(d)
    check("switched off (never): 409, the reason, no card", code == 409
          and "switched off" in out["error"] and not CARDS, out)
    TIERS[CB.ACTION] = "auto"
    code, out = start(d)
    check("a tier that would not ask anyone: 409, no card", code == 409 and not CARDS)
    code, out = R.handle_post(R.START_ROUTE, ["not", "an", "object"], deps=d)
    check("a body that is not an object: 400", code == 400)


# ==========================================================================
#   3. Stop, 4. Limits
# ==========================================================================

def t_stop():
    fresh()
    d = world(CB.FakeChatbot(REPLIES, statuses={1: CB.Status("needs_owner", "captcha")}))
    code, out = start(d)
    sid = out["session"]
    live = R.handle_get("", deps=d)[1]["session"]
    check("a captcha pauses it and asks", live and live["state"] == "paused"
          and "captcha" in live["paused"])
    n = len(CARDS)
    code, out = R.handle_post(R.STOP_ROUTE, {"id": sid}, deps=d)
    check("stop: 200, never a card", code == 200 and len(CARDS) == n)
    s = R.handle_get(f"id={sid}", deps=d)[1]["session"]
    check("... and it is stopped", s["state"] == "stopped")
    code, out = R.handle_post(R.STOP_ROUTE, {"id": sid}, deps=d)
    check("stopping it again: 409 in a sentence", code == 409
          and out["error"].endswith("."))
    code, out = R.handle_post(R.STOP_ROUTE, {"id": "nope"}, deps=d)
    check("a bad id: 400", code == 400)
    code, out = R.handle_post(R.STOP_ROUTE, {"id": "chat_0123456789ab"}, deps=d)
    check("an unknown id: 404", code == 404)


def t_limits():
    fresh()
    d = world(CB.FakeChatbot(REPLIES, statuses={1: CB.Status("needs_owner", "captcha")}))
    sid = start(d)[1]["session"]
    queued = []
    d.gate = deny
    code, out = R.handle_post(R.LIMITS_ROUTE, {"id": sid, "max_messages": 6}, deps=d,
                              spawn=queued.append)
    check("limits: 202 at once, nothing changed yet", code == 202 and out["asking"] is True
          and CB.get(sid).limits.max_turns == 3)
    st = R.handle_get(f"id={sid}", deps=d)[1]
    check("... the next read says a card is waiting", st["limits"]["waiting"] is True)
    code2, out2 = R.handle_post(R.LIMITS_ROUTE, {"id": sid, "max_messages": 7}, deps=d,
                                spawn=queued.append)
    check("a second change while the card waits: 409", code2 == 409)
    n = len(CARDS)
    queued[0]()
    st = R.handle_get(f"id={sid}", deps=d)[1]
    check("a no: the limits stay, and the read says so", len(CARDS) == n + 1
          and CB.get(sid).limits.max_turns == 3 and st["limits"]["waiting"] is False
          and "not changed" in st["limits"]["said"], st["limits"])
    d.gate = approve
    R.handle_post(R.LIMITS_ROUTE, {"id": sid, "max_messages": 6, "never_send": ["Nimbus"]},
                  deps=d, spawn=lambda fn: fn())
    st = R.handle_get(f"id={sid}", deps=d)[1]
    check("a yes: the new limits, from the next message", CB.get(sid).limits.max_turns == 6
          and st["session"]["never_send"] == ["Nimbus"] and "apply" in st["limits"]["said"])
    code, out = R.handle_post(R.LIMITS_ROUTE, {"id": sid, "max_messages": 6,
                                               "never_send": ["Nimbus"]}, deps=d)
    check("the same limits again: 200, nothing asked", code == 200
          and out["changed"] is False)
    code, out = R.handle_post(R.LIMITS_ROUTE, {"id": sid, "max_messages": 60}, deps=d,
                              spawn=queued.append)
    check("a number past this version's most: 400 now, no card", code == 400
          and "At most 8" in out["error"], out)
    code, out = R.handle_post(R.LIMITS_ROUTE, {"id": "chat_0123456789ab"}, deps=d)
    check("an unknown conversation: 404", code == 404)
    R.handle_post(R.STOP_ROUTE, {"id": sid}, deps=d)
    code, out = R.handle_post(R.LIMITS_ROUTE, {"id": sid, "max_messages": 7}, deps=d)
    check("an ended conversation's limits cannot change: 409", code == 409)


def t_a_paused_conversation_nobody_can_resume_is_ended():
    fresh()
    bot = CB.FakeChatbot(REPLIES, statuses={1: CB.Status("needs_owner", "captcha")})
    d = world(bot)
    sid = start(d)[1]["session"]
    clock = [1000.0]
    R._now = lambda: clock[0]
    try:
        s = R.handle_get(f"id={sid}", deps=d)[1]["session"]
        check("paused and held by task control: left alone", s["state"] == "paused")
        TC.handle_post("/api/task/stop", {})      # forgets the paused task
        s = R.handle_get(f"id={sid}", deps=d)[1]["session"]
        check("just let go of: not ended at once (it may be mid-pause)", s["state"] == "paused")
        clock[0] += R.UNHELD_GRACE + 1
        s = R.handle_get(f"id={sid}", deps=d)[1]["session"]
        check("still let go of after the grace: ended, its window closed",
              s["state"] == "stopped" and bot.closed == 1 and "could no longer be resumed"
              in s["ended"], (s["state"], s["ended"]))
        check("... and a new conversation may start", R.handle_get("", deps=d)[1]["session"]
              is None)
    finally:
        R._now = __import__("time").monotonic


# ==========================================================================
#   5. install()
# ==========================================================================

def t_install():
    hits = []

    class H:
        def __init__(self, path, body=b"{}", origin=True, token=True):
            self.path, self._body, self.sent = path, body, None
            self.origin, self.token = origin, token

        def do_GET(self):
            hits.append(("get0", self.path))

        def do_POST(self):
            hits.append(("post0", self.path))

        def _send(self, code, obj):
            self.sent = (code, obj)

    fresh()
    CB.ROUTED = False
    line = R.install(H, origin_ok=lambda h: h.origin, token_ok=lambda h: h.token,
                     read_body=lambda h: h._body)
    import jarvis_reach
    check("install marks the chatbot driver routed, so 'What Jarvis can reach' can say On",
          CB.ROUTED is True and jarvis_reach._chatbot_status()["routed"] is True)
    check("install says what it turned on, naming the chatbots built", "Talk to a chatbot for me" in line
          and "Gemini" in line, line)
    check("installing twice does not wrap twice", "already on" in R.install(
        H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: b"{}"))
    h = H("/api/chatbot/status?id=")
    h.do_GET()
    check("GET /api/chatbot/status is answered here", h.sent and h.sent[0] == 200
          and h.sent[1]["routed"] is True)
    h = H("/api/chatbot/status", token=False)
    h.do_GET()
    check("... behind the token", h.sent and h.sent[0] == 401)
    h = H("/api/chatbot/start", origin=False)
    h.do_POST()
    check("... and the origin check", h.sent and h.sent[0] == 403)
    h = H("/api/chatbot/start", body=b"not json")
    h.do_POST()
    check("a body that is not JSON: 400", h.sent and h.sent[0] == 400)
    h = H("/api/chatbot/start", body=json.dumps({"chatbot": "gemini_web", "goal": GOAL})
          .encode())
    h.do_POST()
    check("POST /api/chatbot/start is answered here (Gemini not built: 400)",
          h.sent and h.sent[0] == 400)
    for path in ("/api/chat", "/api/chatbot/other"):
        H(path).do_POST()
        H(path).do_GET()
    check("everything else passes through to the original",
          ("post0", "/api/chatbot/other") in hits and ("get0", "/api/chat") in hits)


# ==========================================================================
#   6. The patch, the shipped lists, the contract file
# ==========================================================================

def t_the_patch():
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    order = _stack.order()
    check("chatbot-routes.patch is in apply-patches.ps1's list, last",
          order and order[-1] == "chatbot-routes.patch", order[-3:])
    if "chatbot-routes.patch" not in order:
        return
    text, log = _stack.stand_in("jarvis_hud.py", order[:order.index("chatbot-routes.patch")])
    check("the stand-in built", text is not None, "; ".join(log or []))
    if text is None:
        return
    patch = (HERE / "chatbot-routes.patch").read_text(encoding="utf-8")
    d = Path(tempfile.mkdtemp(prefix="jarvis-chatbot-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "--include", "jarvis_hud.py", "p.patch"], cwd=d,
                           capture_output=True, text=True)
        check("chatbot-routes.patch applies to what the earlier patches wrote", r.returncode == 0,
              r.stderr)
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        blk = after[after.index("# chatbot-routes.patch"):after.index("# Before the main socket",
                                                              after.index("# chatbot-routes.patch"))]
        check("the block hands origin_ok/token_ok/read_body to install()",
              "import jarvis_chatbot_routes" in blk and "origin_ok=_origin_ok" in blk
              and "token_ok=_token_ok" in blk and "read_body=_read_body" in blk)
        compile("def f(self, bind, Handler):\n" + blk, "<patched block>", "exec")
        check("the patched block compiles", True)
        r = subprocess.run([git, "apply", "-R", "--include", "jarvis_hud.py", "p.patch"],
                           cwd=d, capture_output=True, text=True)
        check("... and reverses cleanly", r.returncode == 0
              and (d / "jarvis_hud.py").read_text(encoding="utf-8") == text, r.stderr)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_shipped_and_contract():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("shipped: in _where.SHIPPED and apply-patches.ps1",
          "jarvis_chatbot_routes.py" in SHIPPED and "'jarvis_chatbot_routes.py'" in ps1)
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_chatbot_cases.py"),
                        "--check"], capture_output=True, text=True)
    check("both apps' contract file is up to date (tools/gen_chatbot_cases.py --check)",
          r.returncode == 0, r.stdout + r.stderr)
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    sec = api[api.index("## 60."):]
    check("JARVIS-API section 60 lists every route", all(
        p in sec for p in (R.STATUS_ROUTE, R.START_ROUTE, R.STOP_ROUTE, R.LIMITS_ROUTE)))


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
        fresh()
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
