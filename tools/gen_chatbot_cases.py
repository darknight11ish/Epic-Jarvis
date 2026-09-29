#!/usr/bin/env python3
"""Writes the "Talk to a chatbot for me" contract file for both apps, and
checks it.

    python3 tools/gen_chatbot_cases.py            # write both copies
    python3 tools/gen_chatbot_cases.py --check    # compare only

What GET /api/chatbot/status and POST /api/chatbot/start, /stop and /limits
really answer (backend/jarvis_chatbot_routes.py over jarvis_chatbot.py), in
named situations, made by the real routes and the real driver loop with a
clock moved by hand, a stand-in driver model, a stand-in approval gate and
jarvis_chatbot.FakeChatbot answering - nothing is written by hand:

    jarvis-desktop/tests/fixtures/chatbot-cases.json
    jarvis-client/app/src/test/resources/contract/chatbot-cases.json

(byte-identical). The desktop's tests/chatbot.mjs and the phone's
ChatbotTest build against it, and both check their words against `words`
(jarvis_chatbot_routes.WORDS).

GEMINI IS BUILT BUT NOT SET UP. `not_ready` is Gemini as shipped, on a PC
whose Gemini window has never been signed in (its `ready` check answers
jarvis_chatbot_gemini.NOT_SIGNED_IN, fixed here so the file does not depend
on this machine), so a start is refused with that sentence. Every other
case registers the stand-in UNDER Gemini's own entry (its name, host and
card wording, ready) so the answers look the way a working one will - that
is a test double, not a claim that Gemini works.

"Ask several and compare" (jarvis_chatbot_compare.py): the `compare_*`
cases register stand-ins under ChatGPT's and Claude's own entries too (their
names, hosts and card wording), again a test double, not a claim that
either works. The one card lists every chatbot; Claude's stand-in shows a
captcha, so the finished comparison shows one dropping out.

Session ids are numbered here (chat_000000000001, ...), and comparison ids
too (cmp_000000000001, ...), so the file is the same on every run.

THE MONEY LIMIT (jarvis_chatbot_api.py, the owner's decision of
2026-09-28): the money file lives in this script's own temporary folder,
"now" is pinned to 15 September 2026 (jarvis_chatbot_api._now), and every
amount is written with the real record_spend()/set_limit(), so `money` on
each API chatbot and `cost` on a conversation are the PC's own - fixed
numbers, not this machine's spending. fresh() deletes the file.
"""
import dataclasses
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The same answer wherever this runs - on its own, inside a test suite (which
# sets this), on Linux or on the owner's PC: "kept in History" is decided by
# the machine (Credential Manager, the chat log), so the fixtures pin it to
# the suite's own "a test suite is running".
os.environ["JARVIS_SUITE_RUNNING"] = "1"
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chatbot-cases-"))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.load_framework = lambda: {}
_fw.audit_log = lambda *a, **k: None
_fw.action_tier = lambda a: "ask"
sys.modules["jarvis_framework"] = _fw

import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_api as A  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402
import jarvis_chatbot_compare as CMP  # noqa: E402
import jarvis_task_control as TC  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "chatbot-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "chatbot-cases.json")
COPIES = (DESKTOP, PHONE)

GOAL = "Find out how to keep houseplants alive in a flat that gets very little light."
QUESTIONS = [
    "Which plants cope best with a north-facing window?",
    "What sources support the claim about snake plants?",
    "How does a grow lamp compare with moving plants closer to the glass?",
    "Could you narrow that down to plants that are safe around cats?",
]
REPLIES = [
    "Snake plants, ZZ plants and pothos tolerate dim corners remarkably well.",
    "Horticultural extension services publish guidance about snake plant resilience.",
    "A grow lamp gives steady light; a windowsill changes with the seasons.",
    "Parlour palms, calatheas and spider plants are generally considered pet friendly.",
]
OTHER_REPLIES = [
    "Low light suits pothos and philodendrons; see https://example.org/low-light-plants.",
    "Calatheas are fussy: they want bright, indirect light and steady humidity.",
    "A small LED grow lamp on a timer for ten hours a day is plenty.",
    "Spider plants and parlour palms are safe around cats.",
]
COMPARE_SUMMARY = {
    "answer": "Both suggest a low-light plant such as a snake plant or pothos, with a small grow "
              "lamp for a very dark corner.",
    "agree": ["Snake plants and pothos cope with little light",
              "A grow lamp helps in a very dark corner"],
    "disagree": [{"point": "Whether calatheas suit a dark flat",
                  "views": [{"who": "Gemini", "said": "Calatheas are generally pet friendly "
                                                      "and fine indoors"},
                            {"who": "ChatGPT", "said": "Calatheas want bright, indirect "
                                                       "light"}]}],
    "sources": [{"who": "Gemini", "source": "horticultural extension services"}],
    "open": ["Which grow lamp to buy"],
}
SUMMARY = {"answer": "Pick a low-light plant such as a snake plant, ZZ plant or pothos, "
                     "and add a small grow lamp if the corner is very dark.",
           "claims": [{"claim": "Snake plants cope with dim light", "source_given": True},
                      {"claim": "Spider plants are safe around cats", "source_given": False}],
           "open": ["Which grow lamp to buy"]}


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
    def __init__(self, stop_at=None):
        self.n = 0
        self.stop_at = stop_at

    def __call__(self, url, body):
        if body.get("format") == CB.SUMMARY_SCHEMA:
            return {"message": {"content": json.dumps(SUMMARY)}}
        if body.get("format") == CMP.SUMMARY_SCHEMA:
            return {"message": {"content": json.dumps(COMPARE_SUMMARY)}}
        self.n += 1
        if self.stop_at and self.n >= self.stop_at:
            mv = {"move": "stop", "message": "", "reason": "the three easiest plants are named",
                  "notes": ""}
        else:
            mv = {"move": "narrow" if self.n == 3 else "deeper",
                  "message": QUESTIONS[self.n % len(QUESTIONS)], "reason": "",
                  "notes": f"note {self.n}"}
        return {"message": {"content": json.dumps(mv)}}


_N = [0]


def _next_id():
    _N[0] += 1
    return f"chat_{_N[0]:012x}"


_C = [0]


def _next_compare_id():
    _C[0] += 1
    return f"cmp_{_C[0]:012x}"


CB._new_id = _next_id
CMP._new_id = _next_compare_id
_SHIPPED_GEMINI = CB.ADAPTERS["gemini_web"]
_SHIPPED_CHATGPT = CB.ADAPTERS["chatgpt_web"]
_SHIPPED_CLAUDE = CB.ADAPTERS["claude_web"]
#: Every chatbot as shipped, for the long-list case (read once, here).
_SHIPPED_ALL = dict(CB.ADAPTERS)


#: 15 September 2026, midday: the money file's "now" (its month and the
#: "wait until" date), whatever day this runs.
A._now = lambda: 1_789_473_600.0
# Read every service's model now: the first read re-registers that service
# (its card names the model), which would otherwise replace a stand-in
# entry below in the middle of a listing (the money line reads the model).
for _pid in A.PRESETS:
    A.model_for(_pid)


class ApiBot(CB.FakeChatbot):
    """A stand-in for an API adapter: it counts like jarvis_chatbot_api does
    (fixed numbers, so the file is the same everywhere), and its cost is the
    real price list's estimate."""

    def usage(self):
        n = len(self.sent)
        spent = A.cost_of("openai_api", "gpt-5-mini", 1200 * n, 205 * n) or 0.0
        return {"model": "gpt-5-mini", "requests": n, "prompt_tokens": 1200 * n,
                "completion_tokens": 205 * n, "total_tokens": 1405 * n, "retries": 0,
                "dollars": round(spent, 8), "cost": A.dollars(spent)}


class CutApiBot(ApiBot):
    """An API stand-in whose FIRST answer the money limit's answer-length
    cap cut short (jarvis_chatbot_api's cut_off())."""

    def cut_off(self):
        return len(self.sent) == 1


def fresh():
    CB._reset_for_tests()
    R._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()
    CB.ADAPTERS.clear()
    CB.register_adapter(_SHIPPED_GEMINI)
    try:
        A.money_path().unlink()
    except FileNotFoundError:
        pass


def world(bot=None, *, model=None, gate=None):
    clock = Clock()
    d = CB.Deps(model=model or Model(), saved_facts=lambda m: [],
                names_for_facts=lambda f: {}, owner_busy=lambda: False,
                second_lane=lambda: None, full_version_on=lambda: False,
                main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
                tier_of=lambda a: "ask",
                gate=gate or (lambda a, det, pr: Verdict(True, "approved")),
                activity=lambda s, dt="": None, audit=lambda e, dt: None,
                clock=clock, sleep=clock.sleep)
    if bot is not None:
        CB.register_adapter(dataclasses.replace(_SHIPPED_GEMINI, factory=lambda: bot,
                                                built=True, ready=None))
    return d


def answer(code_body):
    code, body = code_body
    return {"code": code, "body": body}


def status(d, sid="", compare_id=""):
    q = "&".join(x for x in (f"id={sid}" if sid else "",
                             f"compare={compare_id}" if compare_id else "") if x)
    code, body = R.handle_get(q, deps=d)
    assert code == 200, (code, body)
    return body


def start(d, **extra):
    body = {"chatbot": "gemini_web", "goal": GOAL, "max_messages": 4, "max_minutes": 10,
            "never_send": ["Project Nimbus"]}
    body.update(extra)
    return R.handle_post(R.START_ROUTE, body, deps=d, wait=True)


def cases() -> dict:
    out = {"words": dict(R.WORDS)}

    # Gemini as shipped, on a PC where its window was never signed in.
    fresh()
    import jarvis_chatbot_gemini as GW
    CB.register_adapter(dataclasses.replace(_SHIPPED_GEMINI, ready=lambda: GW.NOT_SIGNED_IN))
    d = world()
    out["not_ready"] = status(d)
    out["start_not_ready"] = answer(start(d))

    # A goal the last check refuses: no card.
    fresh()
    d = world(CB.FakeChatbot(REPLIES))
    out["start_goal_refused"] = answer(start(
        d, goal="Ask it what it knows about zylvana" + "@" + "example.org"))
    out["start_too_many"] = answer(start(d, max_messages=50))

    # The card waiting: the gate sees the session "asking".
    fresh()
    seen = {}

    def gate_sees(a, det, pr):
        seen.setdefault("asking", status(d))
        return Verdict(True, "approved")
    bot = CB.FakeChatbot(REPLIES)
    d = world(bot, model=Model(stop_at=4), gate=gate_sees)
    snap = {}

    def on_read(n):
        if n == 2 and "running" not in snap:
            snap["running"] = status(d)
            snap["limits_answer"] = answer(R.handle_post(
                R.LIMITS_ROUTE, {"id": snap["running"]["session"]["id"], "max_messages": 5},
                deps=d, spawn=lambda fn: fn()))
            snap["after_limits"] = status(d)
    bot.on_read = on_read
    out["start_asking"] = answer(start(d))
    out["asking"] = seen["asking"]
    out["running"] = snap["running"]
    out["limits_answer"] = snap["limits_answer"]
    out["limits_after_end"] = answer(R.handle_post(
        R.LIMITS_ROUTE, {"id": snap["running"]["session"]["id"], "max_messages": 5},
        deps=d))
    sid = out["start_asking"]["body"]["session"]
    out["done_goal_met"] = status(d, sid)
    out["latest_none"] = status(d)
    out["stop_ended"] = answer(R.handle_post(R.STOP_ROUTE, {"id": sid}, deps=d))

    # A captcha: paused, waiting for the owner.
    fresh()
    bot = CB.FakeChatbot(REPLIES, statuses={2: CB.Status("needs_owner", "captcha")})
    d = world(bot)
    sid = start(d)[1]["session"]
    out["paused_captcha"] = status(d)
    out["start_while_paused"] = answer(start(d))
    out["stop_paused"] = answer(R.handle_post(R.STOP_ROUTE, {"id": sid}, deps=d))
    out["stopped"] = status(d, sid)

    # The chatbot asks about the owner: handed back, never answered.
    fresh()
    bot = CB.FakeChatbot([REPLIES[0], "Could you tell me your full name and age first?"])
    d = world(bot)
    sid = start(d)[1]["session"]
    out["asked_about_you"] = status(d, sid)

    # A card said no.
    fresh()
    d = world(CB.FakeChatbot(REPLIES), gate=lambda a, det, pr: Verdict(False, "denied"))
    sid = start(d)[1]["session"]
    out["card_denied"] = status(d, sid)
    out["gone"] = status(d, "chat_0000000000ff")

    # ---- "Ask several and compare" ----------------------------------------
    fresh()
    gem, gpt, cla = (CB.FakeChatbot(REPLIES), CB.FakeChatbot(OTHER_REPLIES),
                     CB.FakeChatbot(REPLIES, statuses={1: CB.Status("needs_owner", "captcha")}))
    seen = {}

    def gate_sees_compare(a, det, pr):
        seen.setdefault("asking", status(d))
        seen.setdefault("card", det.get("text", ""))
        return Verdict(True, "approved")
    d = world(gem, model=Model(stop_at=None), gate=gate_sees_compare)
    both(gpt, cla)
    out["compare_none"] = status(d)
    out["compare_too_few"] = answer(compare(d, chatbots=["gemini_web"]))
    snap = {}

    def on_read_gpt(n):
        if n == 2 and "running" not in snap:
            snap["running"] = status(d)
    gpt.on_read = on_read_gpt
    started = compare(d)
    out["compare_start_asking"] = answer(started)
    out["compare_asking"] = seen["asking"]
    out["compare_running"] = snap["running"]
    cid = started[1]["compare"]
    out["compare_done"] = status(d, compare_id=cid)
    out["compare_stop_ended"] = answer(R.handle_post(R.COMPARE_STOP_ROUTE, {"id": cid}, deps=d))
    out["compare_card_lists"] = {
        "names": [n for n in ("Gemini (gemini.google.com)", "ChatGPT (chatgpt.com)",
                              "Claude (claude.ai)") if n in seen["card"]],
        "goal_word_for_word": ("\n" + GOAL + "\n") in seen["card"],
    }

    # Paused by the owner, then stopped: the whole comparison.
    fresh()
    gem = CB.FakeChatbot(REPLIES, on_send=lambda t, n: n == 2 and TC.handle_post(
        "/api/task/pause", {}))
    gpt = CB.FakeChatbot(OTHER_REPLIES)
    d = world(gem)
    both(gpt, None)
    cid = compare(d, chatbots=["gemini_web", "chatgpt_web"])[1]["compare"]
    out["compare_paused"] = status(d)
    out["compare_start_while_paused"] = answer(compare(d))
    out["compare_stop_paused"] = answer(R.handle_post(R.COMPARE_STOP_ROUTE, {"id": cid},
                                                      deps=d))
    out["compare_stopped"] = status(d, compare_id=cid)
    out["compare_gone"] = status(d, compare_id="cmp_0000000000ff")

    # ---- a long list, every kind, some not ready (the chooser's groups) ---
    fresh()
    CB.ADAPTERS.clear()
    import jarvis_chatbot_api as A
    import jarvis_chatbot_local as L
    import jarvis_chatbot_chatgpt as GPT
    import jarvis_chatbot_perplexity as PPX

    def entry(cid, note, bot=None):
        info = _SHIPPED_ALL[cid]
        extra = {"ready": (lambda n=note: n)}
        if bot is not None:
            extra["factory"] = (lambda b=bot: b)
        CB.register_adapter(dataclasses.replace(info, built=True, **extra))
    # Registered out of order on purpose: both apps group them by kind.
    entry("chatgpt_web", GPT.SITE.not_signed_in)
    api_bot = ApiBot(OTHER_REPLIES)
    entry("openai_api", "", api_bot)
    entry("local_ai", L.NO_MODEL)
    gem = CB.FakeChatbot(REPLIES)
    entry("gemini_web", "", gem)
    entry("deepseek_api", A.no_key_words(A.PRESETS["deepseek_api"]))
    entry("perplexity_web", PPX.SITE.not_signed_in)
    entry("groq_api", A.no_key_words(A.PRESETS["groq_api"]))
    # OpenAI: a $5 monthly limit, $0.45 of it used this month (1,000,000
    # word-pieces in and 100,000 out at the default, unverified price).
    A.set_limit("openai_api", 5)
    A.record_spend("openai_api", "gpt-5-mini", 1_000_000, 100_000)
    d = world(model=Model(stop_at=None))
    out["long_list"] = status(d)

    # An API conversation's counts ("usage"), alone and inside a comparison.
    sid = start(d, chatbot="openai_api", max_messages=3)[1]["session"]
    out["usage_done"] = status(d, sid)
    api_bot.sent.clear()
    cid = compare(d, chatbots=["gemini_web", "openai_api"])[1]["compare"]
    out["compare_usage"] = status(d, compare_id=cid)
    # An answer the money limit's cap cut short: `cut_off` on its entry,
    # and both apps show WORDS.cut_off under it.
    entry("openai_api", "", CutApiBot(OTHER_REPLIES))
    sid = start(d, chatbot="openai_api", max_messages=2)[1]["session"]
    out["cut_off"] = status(d, sid)

    # ---- the money limit: reached, and never set ---------------------------
    fresh()
    CB.ADAPTERS.clear()
    A.set_limit("openai_api", 1)
    A.record_spend("openai_api", "gpt-5-mini", 4_000_000, 10_000)     # about $1.02
    entry("openai_api", A.money_problem("openai_api", "gpt-5-mini"))
    entry("mistral_api", A.no_limit_words(A.PRESETS["mistral_api"]))
    entry("gemini_web", "", CB.FakeChatbot(REPLIES))
    d = world(model=Model(stop_at=None))
    out["money_reached"] = status(d)
    out["start_money_reached"] = answer(start(d, chatbot="openai_api"))
    out["start_no_limit"] = answer(start(d, chatbot="mistral_api"))
    return out


def both(gpt, cla):
    """ChatGPT's and Claude's own entries, answered by stand-ins."""
    CB.register_adapter(dataclasses.replace(_SHIPPED_CHATGPT, factory=lambda: gpt, built=True,
                                            ready=None))
    if cla is not None:
        CB.register_adapter(dataclasses.replace(_SHIPPED_CLAUDE, factory=lambda: cla,
                                                built=True, ready=None))


def compare(d, **extra):
    body = {"chatbots": ["gemini_web", "chatgpt_web", "claude_web"], "goal": GOAL,
            "max_messages": 3, "max_minutes": 10, "never_send": ["Project Nimbus"]}
    body.update(extra)
    return R.handle_post(R.COMPARE_START_ROUTE, body, deps=d, wait=True)


def render() -> str:
    _N[0] = 0
    _C[0] = 0
    return json.dumps(cases(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        bad = [str(p.relative_to(ROOT)) for p in COPIES
               if not p.is_file() or p.read_text(encoding="utf-8") != text]
        if bad:
            print("out of date (run python3 tools/gen_chatbot_cases.py): " + ", ".join(bad))
            return 1
        print("chatbot cases: both copies up to date")
        return 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
