"""test_chatbot_local.py - "a second AI on this PC" (jarvis_chatbot_local.py):
the chatbot driver talks to another Ollama model on this PC.

    python3 backend/test_chatbot_local.py

The owner's decision (CLAUDE.md, "The chatbot driver becomes versatile",
2026-09-28): "a second AI on the owner's own PC (another local model, best
on the 12 GB card; nothing leaves the PC)".

What this proves, against a FAKE Ollama on 127.0.0.1 (/api/tags and
/api/chat), the REAL jarvis_chatbot core, jarvis_router, jarvis_search,
jarvis_mail_mask, jarvis_task_control and jarvis_stop_all:

  - Ollama's cloud models ("-cloud", ":cloud") are refused before any card
    and before any request, by the core's own check and a second pattern;
  - loopback only: a model address that is not this PC is refused, and no
    request is ever made to one;
  - the two versions, decided by the core's own choose_tier(): one card
    allows only the everyday model already loaded (at chat's context size;
    anything else says "needs your second graphics card"); two cards run the
    chosen model on the second card's lane, keeping the lane's size for its
    own model and saying so when the card has to swap;
  - a model the PC does not have, or one too big for the 12 GB card, is
    refused - nothing is ever downloaded;
  - no model chosen: not ready, with the one line that fixes it;
  - a whole core session: one card saying nothing leaves the PC, the
    replies are outside text, usage is recorded, thinking is stripped, the
    one-card version waits while the owner chats, and the core's last check
    still blocks a planted secret before it reaches the other model;
  - no row in "What Jarvis can reach"; the module is shipped.

No pytest. The only socket is to the fake Ollama on 127.0.0.1.
"""
from __future__ import annotations

import http.server
import json
import select
import socket
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_chatbot.py", "jarvis_chatbot_local.py", "jarvis_local_http.py",
                "jarvis_task_control.py", "jarvis_stop_all.py", "jarvis_search.py",
                "jarvis_mail_mask.py", "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chatbot-local-"))
CFG: dict = {}
TIERS: dict = {}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {"chatbot": CFG}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

import jarvis_task_control as TC  # noqa: E402
import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_local as L  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


FAKE_GITHUB = "gh" + "p_" + "Fak3" + "0123456789abcdefghijklmnopqrstuv"
GOAL = "Find out how to keep houseplants alive in a flat that gets very little light."
GIB = 1024 ** 3

REPLIES = [
    "Snake plants, ZZ plants and pothos tolerate dim corners remarkably well.",
    "Horticultural extension services publish guidance about sansevieria resilience.",
    "Grow lamps deliver consistent spectrum; windowsills vary seasonally.",
    "Chlorosis follows reduced photosynthesis when chlorophyll production drops.",
]


class Ollama:
    """A fake Ollama: /api/tags lists `models`; /api/chat answers."""

    def __init__(self):
        self.requests: list = []
        self.models = {"jarvis-primary:latest": 5 * GIB, "qwen3:8b": 5 * GIB,
                       "gemma3:12b": 8 * GIB, "llama3.1:70b": 40 * GIB}
        self.think = False
        self.n = 0
        self.delay = 0.0
        self.dropped = 0
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj):
                data = json.dumps(obj).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.requests.append({"path": self.path, "body": ""})
                self._send({"models": [{"name": n, "size": s}
                                       for n, s in outer.models.items()]})

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.requests.append({"path": self.path, "body": raw.decode("utf-8")})
                if outer.delay:
                    # A slow answer. Like Ollama, notice when Jarvis closes
                    # the connection, and stop working on it then.
                    end = time.time() + outer.delay
                    while time.time() < end:
                        ready, _, _ = select.select([self.connection], [], [], 0.05)
                        if ready:
                            try:
                                peek = self.connection.recv(1, socket.MSG_PEEK)
                            except OSError:
                                peek = b""
                            if not peek:
                                outer.dropped += 1
                                return
                outer.n += 1
                text = REPLIES[(outer.n - 1) % len(REPLIES)]
                if outer.think:
                    text = "<think>private musing</think>\n" + text
                self._send({"model": "x", "message": {"role": "assistant", "content": text},
                            "done": True, "prompt_eval_count": 20, "eval_count": 9})

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def chats(self):
        return [json.loads(r["body"]) for r in self.requests if r["path"] == "/api/chat"]


OLL = Ollama()


def one_card(model="jarvis-primary"):
    return CB.Tier(CB.ONE_CARD, OLL.url, model, CB.ONE_CARD_NUM_CTX)


def two_cards(model="qwen3:8b", num_ctx=32768):
    return CB.Tier(CB.TWO_CARDS, OLL.url, model, num_ctx)


def setup(model, tier=None):
    CFG.clear()
    if model is not None:
        CFG["local_model"] = model
    L._TIER = (lambda: tier) if tier is not None else (lambda: one_card())
    L._reset_for_tests()


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = float(t)

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


QUESTIONS = ["Which plants cope best with a north-facing window?",
             "What sources support the claim about snake plants?",
             "How does a grow lamp compare with moving plants closer to glass?",
             "Why do leaves turn yellow in low light?"]


class Model:
    def __init__(self, moves=None):
        self.moves, self.n = moves, 0

    def __call__(self, url, body):
        if body.get("format") == CB.SUMMARY_SCHEMA:
            return {"message": {"content": json.dumps(
                {"answer": "Use low-light plants.", "claims": [], "open": []})}}
        self.n += 1
        mv = self.moves(self.n) if callable(self.moves) else None
        if mv is None:
            mv = {"move": "deeper", "message": QUESTIONS[(self.n - 1) % len(QUESTIONS)],
                  "reason": "", "notes": ""}
        return {"message": {"content": json.dumps(mv)}, "done_reason": "stop"}


def deps(model=None):
    clock = Clock()
    return CB.Deps(model=model or Model(), saved_facts=lambda m: [],
                   names_for_facts=lambda f: {}, owner_busy=lambda: False,
                   second_lane=lambda: None, full_version_on=lambda: False,
                   main_lane=lambda: (OLL.url, "jarvis-primary"),
                   tier_of=lambda a: TIERS.get(a, "ask"), gate=approve,
                   activity=lambda s, d="": None, audit=lambda e, d: None,
                   clock=clock, sleep=clock.sleep)


def clean():
    CB._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()
    OLL.requests.clear()
    OLL.n = 0
    OLL.think = False
    OLL.delay = 0.0
    OLL.dropped = 0
    CARDS.clear()
    TIERS.clear()
    L._OWNER_BUSY = None
    L._HTTP = None


def wait_reply(a, most=15.0):
    end = time.time() + most
    while time.time() < end:
        got = a.read_reply(0.2)
        if got is not None:
            return got
    return None


# ==========================================================================

def t_cloud_models_refused():
    clean()
    for name in ("gpt-oss:120b-cloud", "qwen3-coder:480b-cloud", "deepseek-v3.1:671B-CLOUD",
                 "kimi-k2:cloud", "glm-4.6:cloud-large"):
        check(f"a cloud model is recognised: {name}", L.is_cloud_model(name))
    for name in ("qwen3:8b", "llama3.2:3b", "jarvis-primary", "cloudberry:7b"):
        check(f"a model on this PC is not: {name}", not L.is_cloud_model(name))
    setup("gpt-oss:120b-cloud")
    note = L.ready()
    check("a cloud model is not ready, in plain words", "cloud models" in note
          and "ollama.com" in note, note)
    s = CB.plan(L.ID, GOAL, deps=deps())
    check("... refused before any card", s.state == "refused" and not CARDS, s.problem)
    a = L.LocalChatbot("gpt-oss:120b-cloud", L.Place(OLL.url, 8192, CB.TWO_CARDS, ""))
    try:
        a.open()
        opened = True
    except L.LocalUnavailable as exc:
        opened = exc.code != "cloud"
    check("... and the adapter refuses it before any request", not opened
          and not OLL.requests)


def t_loopback_only():
    clean()
    setup("jarvis-primary", CB.Tier(CB.ONE_CARD, "http://10.0.0.5:11434", "jarvis-primary",
                                    16384))
    note = L.ready()
    check("a model address that is not this PC is not ready", "not on this PC" in note, note)
    for url in ("http://10.0.0.5:11434/api/chat", "http://ollama.example.com/api/chat",
                "https://ollama.com/api/chat"):
        called = []
        L._HTTP = lambda req, t: called.append(req.full_url) or (200, b"{}")
        try:
            L._http(__import__("urllib.request").request.Request(url), 1.0)
            refused = False
        except L.LocalUnavailable:
            refused = True
        check(f"no request to {url}", refused and not called)
    L._HTTP = None


def t_no_model_chosen():
    clean()
    setup(None)
    c = next(x for x in CB.choices() if x["id"] == L.ID)
    check("no model chosen: not ready, with the line to add",
          c["ready"] is False and "local_model" in c["note"] and "ollama list" in c["note"]
          and c["kind"] == "local" and c["host"] == "this PC", c)
    setup("bad name; rm")
    check("a model line that is not a model name is not ready", "not a model name"
          in L.ready())


def t_one_card():
    clean()
    setup("jarvis-primary", one_card())
    check("one card: the everyday model already loaded is ready", L.ready() == "")
    place, _ = L.placement("jarvis-primary:latest")
    check("... ':latest' counts as the same model, at chat's own context size",
          place is not None and place.num_ctx == CB.ONE_CARD_NUM_CTX
          and place.tier == CB.ONE_CARD and "same model Jarvis itself uses" in place.words)
    setup("qwen3:4b", one_card())
    note = L.ready()
    check("one card: any other model needs the second graphics card",
          "needs your second graphics card" in note and "jarvis-primary" in note, note)


def t_two_cards():
    clean()
    setup("gemma3:12b", two_cards())
    check("two cards: another model is ready", L.ready() == "")
    place, _ = L.placement("gemma3:12b")
    check("... on the second card's lane, at its own size, and the card says it swaps",
          place.url == OLL.url and place.num_ctx == L.LOCAL_NUM_CTX and place.swaps
          and "swaps" in place.words, place.words)
    place, _ = L.placement("qwen3:8b")
    check("the lane's own model keeps the lane's size and never swaps",
          place.num_ctx == 32768 and not place.swaps)
    a = L.LocalChatbot("llama3.1:70b", L.placement("llama3.1:70b")[0])
    try:
        a.open()
        why = ""
    except L.LocalUnavailable as exc:
        why = exc.code
    check("a model too big for the 12 GB card is refused", why == "too_big", why)
    a = L.LocalChatbot("mistral:7b", L.placement("mistral:7b")[0])
    try:
        a.open()
        why = ""
    except L.LocalUnavailable as exc:
        why = exc.code
    check("a model the PC does not have is refused (nothing is downloaded)",
          why == "not_installed"
          and not any(r["path"] == "/api/pull" for r in OLL.requests), why)


def t_ready_never_probes_the_second_card():
    clean()
    CFG.clear()
    CFG["local_model"] = "gemma3:12b"
    CFG["full_version"] = True
    L._TIER = None
    L._reset_for_tests()
    real, probed = CB.choose_tier, []
    CB.choose_tier = lambda *a, **k: probed.append(1) or one_card()
    try:
        note = L.ready()
    finally:
        CB.choose_tier = real
    check("with the full version on, ready() says yes without asking the second card's "
          "lane (What Jarvis can reach wakes nothing)", note == "" and not probed
          and not OLL.requests, (note, probed))
    check("... and the card words say it runs there only while the lane is running",
          "while its lane is running" in CB.ADAPTERS[L.ID].how)
    L._TIER = lambda: one_card()
    try:
        L._factory()
        refused = ""
    except L.LocalUnavailable as exc:
        refused = exc.owner_words
    check("... and when the conversation opens on one card, another model is refused in "
          "plain words, before anything is sent", "second graphics card" in refused
          and not OLL.chats(), refused)
    CFG.clear()


def t_the_card():
    clean()
    setup("jarvis-primary", one_card())
    s = CB.plan(L.ID, GOAL, deps=deps())
    text = CB.describe(s)
    check("the card says nothing leaves this PC and names where it runs",
          not s.problem and "Nothing leaves this PC" in text
          and "same model Jarvis itself uses" in text, text[:600])
    check("the card says its words are still outside text", "outside text" in text)
    check("the card does not claim a message leaves the PC, nor mention captchas",
          "just before it is sent" in text and "leaves this PC." not in text
          and "captcha" not in text.lower(), text)
    check("the card names it once - not \"A second AI on this PC (this PC)\"",
          f"Chatbot: {L.NAME}, another AI model" in text and "(this PC)" not in text,
          [x for x in text.splitlines() if x.startswith("Chatbot:")])
    head = CB.RESUME_HEADER(s, 1)
    check("the resume card does not say a message 'leaves this PC' either",
          "just before it is sent" in head and "leaves this PC" not in head, head)
    web = CB.Session(id="x", chatbot="gemini_web", goal=GOAL, limits=s.limits, tier=s.tier)
    check("... while a website's resume card still does",
          "just before it leaves this PC" in CB.RESUME_HEADER(web, 1))


def t_a_whole_conversation():
    clean()
    setup("jarvis-primary", one_card())
    OLL.think = True
    d = deps()
    s = CB.plan(L.ID, GOAL, max_turns=3, deps=d)
    CB.start(s, deps=d, wait=True)
    chats = OLL.chats()
    check("the conversation ran to its limit", s.ended_code == "limit_turns"
          and len(chats) == 3, (s.ended_code, s.ended_words, len(chats)))
    check("every request went to this PC's Ollama, with the chosen model at chat's size",
          all(c["model"] == "jarvis-primary" and c["options"]["num_ctx"]
              == CB.ONE_CARD_NUM_CTX and c["stream"] is False for c in chats), chats[:1])
    check("the history is resent each time", [m["role"] for m in chats[2]["messages"]]
          == ["user", "assistant", "user", "assistant", "user"])
    check("the other model's replies are outside text, with its thinking stripped",
          all(t["outside_text"] and "musing" not in t["text"]
              for t in s.transcript if t["who"] == "chatbot"))
    u = CB.session_view(s)["usage"]
    check("usage is recorded", u and u["prompt_tokens"] == 60 and u["completion_tokens"] == 27
          and u["requests"] == 3, u)


def t_the_last_check_still_runs():
    clean()
    setup("jarvis-primary", one_card())

    def leaky(n):
        return {"move": "deeper", "message": f"Is {FAKE_GITHUB} valid?", "reason": "",
                "notes": ""}
    d = deps(model=Model(moves=leaky))
    s = CB.plan(L.ID, GOAL, max_turns=3, deps=d)
    CB.start(s, deps=d, wait=True)
    check("a planted secret never reaches the other model, even on this PC",
          s.paused_code == "blocked" and FAKE_GITHUB not in json.dumps(OLL.chats())
          and len(OLL.chats()) == 1, (s.state, s.paused_code))
    CB.stop(s.id, deps=d)


def t_one_card_waits_while_the_owner_chats():
    clean()
    setup("jarvis-primary", one_card())
    L.BUSY_POLL, old = 0.05, L.BUSY_POLL
    calls = []

    def busy():
        calls.append(1)
        return len(calls) < 4
    L._OWNER_BUSY = busy
    try:
        a = L._factory()
        a.open()
        a.send("Which plants like shade?")
        got = wait_reply(a)
        check("one card: the other AI waits while the owner chats, then answers",
              got == REPLIES[0] and len(calls) >= 4, (got, len(calls)))
        L._OWNER_BUSY = lambda: True
        a.send("And ferns?")
        time.sleep(0.2)
        n = len(OLL.chats())
        a.close()
        check("close() while waiting sends nothing more", len(OLL.chats()) == n == 1)
    finally:
        L.BUSY_POLL = old


def t_waiting_for_the_owner_is_not_a_timeout():
    """Audit, 2026-09-28: on one card the other AI waits while the owner's
    own chat is answered. That wait used to count against the driver's
    reply limit, so a long owner answer plus a slow reply ended with a
    wrong "did not answer within 180 seconds"."""
    clean()
    setup("jarvis-primary", one_card())
    old = (L.BUSY_POLL, CB.REPLY_TIMEOUT, CB.REPLY_SLICE)
    L.BUSY_POLL, CB.REPLY_TIMEOUT, CB.REPLY_SLICE = 0.05, 1.0, 0.2
    said = []
    try:
        until = time.time() + 2.5      # the owner's chat takes longer than the reply limit
        L._OWNER_BUSY = lambda: time.time() < until
        d = deps()
        d = CB.Deps(**dict(d.__dict__, activity=lambda st, words="": said.append(words)))
        s = CB.plan(L.ID, GOAL, max_turns=1, deps=d)
        CB.start(s, deps=d, wait=True)
        check("a wait for the owner's own chat longer than the reply limit does not end the "
              "conversation as 'did not answer'",
              s.ended_code == "limit_turns" and len(OLL.chats()) == 1
              and s.transcript[-1]["who"] == "chatbot", (s.ended_code, s.ended_words))
        check("... and Jarvis says it is waiting for the owner's chat",
              any("Waiting while you chat before asking" in w for w in said), said)
        # The reply limit still holds once the other AI HAS been asked.
        clean()
        setup("jarvis-primary", one_card())
        L._OWNER_BUSY = lambda: False
        OLL.delay = 3.0
        d = deps()
        s = CB.plan(L.ID, GOAL, max_turns=1, deps=d)
        CB.start(s, deps=d, wait=True)
        check("a reply that is genuinely slow still ends 'did not answer' at the reply limit",
              s.ended_code == "no_reply", (s.ended_code, s.ended_words))
        time.sleep(0.5)
        check("... and ending it closed the connection, so Ollama stopped that answer",
              OLL.dropped == 1 and OLL.n == 0, (OLL.dropped, OLL.n))
    finally:
        L.BUSY_POLL, CB.REPLY_TIMEOUT, CB.REPLY_SLICE = old


def t_close_abandons_the_request():
    clean()
    setup("jarvis-primary", one_card())
    L._OWNER_BUSY = lambda: False
    OLL.delay = 5.0
    a = L._factory()
    a.open()
    a.send("Which plants like shade?")
    end = time.time() + 3
    while not OLL.requests[-1:] or OLL.requests[-1]["path"] != "/api/chat":
        if time.time() > end:
            break
        time.sleep(0.02)
    time.sleep(0.2)
    t0 = time.time()
    a.close()
    raised = None
    try:
        a.read_reply(2.0)
    except L.LocalUnavailable as exc:
        raised = exc.code
    took = time.time() - t0
    check("close() during a request abandons it at once (not after the 5-second answer)",
          raised == "closed" and took < 1.5, (raised, round(took, 2)))
    time.sleep(0.3)
    check("... Ollama sees the connection closed, so the graphics card is freed",
          OLL.dropped == 1 and OLL.n == 0, (OLL.dropped, OLL.n))
    clean()
    setup("jarvis-primary", one_card())
    L.BUSY_POLL, old = 0.05, L.BUSY_POLL
    try:
        L._OWNER_BUSY = lambda: True
        a = L._factory()
        a.open()
        a.send("And ferns?")
        time.sleep(0.2)
        check("while the owner chats it says it is waiting for the owner",
              a.waiting_for_owner() is True)
        a.close()
        raised = None
        try:
            a.read_reply(1.0)
        except L.LocalUnavailable as exc:
            raised = exc.code
        check("close() while waiting for the owner ends the wait at once, and asks nothing",
              raised == "closed" and not a.waiting_for_owner() and not OLL.chats(), raised)
    finally:
        L.BUSY_POLL = old


def t_no_reach_row_and_shipped():
    import jarvis_reach as R
    ids = [k for k, _ in R.KINDS]
    check("'a second AI on this PC' has no row in What Jarvis can reach",
          not any("local" in i for i in ids), ids)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("shipped: in _where.SHIPPED and apply-patches.ps1",
          "jarvis_chatbot_local.py" in SHIPPED and "'jarvis_chatbot_local.py'" in ps1)
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("JARVIS-API.md section 60 describes it", "jarvis_chatbot_local.py" in api
          and "local_ai" in api)


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
        L._TIER = None
        OLL.httpd.shutdown()
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
