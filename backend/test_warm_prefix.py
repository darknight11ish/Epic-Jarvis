"""The warm-up with words (speed fix, 2026-09-28): jarvis_agent.warm_prefix,
warm_after_waking, warm_after_learning, and warm-prefix.patch.

    python3 test_warm_prefix.py

After Jarvis loads or wakes the model, and after a learning pass on a
one-card PC, the first question used to read Jarvis's rules and tool list
from nothing (3,000-4,000 tokens). The warm-up sends exactly the start a real
question sends, with one word as the question and one word of answer, and
throws the answer away. What this proves, against a fake Ollama listening on
127.0.0.1 (real sockets, real JSON), with nothing from the owner's PC:

  - the warm-up's request is, byte for byte, the request run_local_turn sends
    for the question "hi" - except max_tokens - with the owner's manner line,
    a focus session, the short tool list, no tools, and a model that cannot
    use tools; and for a real question the start (every message before it,
    and the tools) is the same;
  - neither sends num_ctx, options or keep_alive (nothing that could make
    Ollama reload the model);
  - it writes no chat history, no speed row, no step event, learns nothing,
    and holds no words from any conversation;
  - it is never sent to a cloud model or another machine, never loads a
    model, never runs on standby, during a task or while a question is being
    answered, never after a temporary chat (or a game), and never when the
    learner has its own lane (the second card);
  - a question arriving while it runs cuts it off, and does not wait for it;
  - `[power] warm_prefix = false` switches it off, and only a real false;
  - the wake-up path calls it once the model is loaded, and not when Jarvis
    went back on standby;
  - warm-prefix.patch is last in apply-patches.ps1's list, its context is
    text extraction-wiring.patch writes, it applies to the stand-in of
    jarvis_hud.py the whole stack before it leaves and comes off again, and
    its lines, run as they are, call the warm-up only after a pass that
    asked a model - and never raise.
"""
from __future__ import annotations

import json
import os
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_CFG = tempfile.mkdtemp(prefix="jarvis-warm-prefix-cfg-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _CFG
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
import _ollama_wire as W  # noqa: E402
import _stack  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_power_switch as S  # noqa: E402

PATCH = "warm-prefix.patch"
TARGET = "jarvis_hud.py"
MODEL = "jarvis-primary"
FAILED, PASSED = [], []
STEPS: list = []
AG._publish_step = STEPS.append          # a real turn publishes; recorded here
AG._record_chain = lambda steps: None
REAL_MANNER, REAL_FOCUS, REAL_SHORT = AG._manner_now, AG._focus_active_now, AG.short_list_on
REAL_ON = AG.warm_prefix_on


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   A fake Ollama on 127.0.0.1
# --------------------------------------------------------------------------

class Fake:
    def __init__(self, tools_ok=True):
        self.posts: list = []            # (path, raw body bytes)
        self.lock = threading.Lock()
        self.tools_ok = tools_ok
        self.hold = False                 # hold a warm-up until its caller goes
        self.warm_in = threading.Event()
        self.warm_gone = threading.Event()
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj):
                data = json.dumps(obj).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/ps":
                    return self._json({"models": [{"name": MODEL + ":latest",
                                                   "model": MODEL + ":latest",
                                                   "context_length": 16384}]})
                self.send_error(404)

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path == "/api/show":
                    caps = ["completion", "tools"] if fake.tools_ok else ["completion"]
                    return self._json({"capabilities": caps,
                                       "parameters": "num_ctx                        16384"})
                with fake.lock:
                    fake.posts.append((self.path, raw))
                body = json.loads(raw or b"{}")
                if fake.hold and body.get("max_tokens") == 1:
                    fake.warm_in.set()
                    sock = self.connection
                    end = time.monotonic() + 10
                    while time.monotonic() < end:
                        r, _, _ = select.select([sock], [], [], 0.05)
                        if r:
                            try:
                                if sock.recv(1, socket.MSG_PEEK) == b"":
                                    fake.warm_gone.set()
                                    return
                            except OSError:
                                fake.warm_gone.set()
                                return
                    return
                data = W.stream([("content", "Hel"), ("content", "lo"), ("done", "stop")],
                                model=MODEL)
                self.send_response(200)
                self.send_header("Content-Type", W.CONTENT_TYPE_STREAM)
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def chats(self):
        with self.lock:
            return [raw for path, raw in self.posts if path == "/v1/chat/completions"]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def fresh():
    AG._CTX_CACHE.clear()
    AG._TOOLS_CACHE.clear()


def real_turn(fake, question="hi", *, enabled, request_extra=None, history=()):
    fresh()
    msgs = list(history) + [{"role": "user", "content": question}]
    req = {"conversation_id": "conv-warm-1", "stream": True,
           "messages": [dict(m, provenance="typed") if m["role"] == "user" else m
                        for m in msgs]}
    req.update(request_extra or {})
    before = len(fake.chats())
    AG.run_local_turn(msgs, MODEL, ollama_url=fake.url, stream_out=lambda b: None,
                      enabled_tools=enabled, request=req, lane_choice=None)
    return fake.chats()[before]


def warm(fake, *, enabled, **kw):
    fresh()
    before = len(fake.chats())
    out = AG.warm_prefix(MODEL, ollama_url=fake.url, enabled_tools=enabled, **kw)
    sent = fake.chats()[before:]
    return out, (sent[0] if sent else None)


EVERY = set(AG.TOOLS) - {"browser_control"}


def settings(*, manner=None, focus=False, short=False):
    AG._manner_now = lambda *a, **k: manner
    AG._focus_active_now = lambda: focus
    AG.short_list_on = lambda: short


def restore():
    AG._manner_now, AG._focus_active_now, AG.short_list_on = REAL_MANNER, REAL_FOCUS, REAL_SHORT
    AG.warm_prefix_on = REAL_ON


# --------------------------------------------------------------------------
#   1. The same bytes
# --------------------------------------------------------------------------

def t_the_same_bytes_as_a_real_turn():
    cases = [
        ("every tool, the warm manner", dict(manner="warm"), EVERY, True),
        ("every tool, plain manner, a focus session", dict(manner="plain", focus=True), EVERY,
         True),
        ("the short tool list", dict(manner="warm", short=True), EVERY, True),
        ("the shipped default: web search only", dict(manner="warm"), {"web_search"}, True),
        ("no tools enabled", dict(manner="warm"), set(), True),
        ("no manner module (None)", dict(manner=None), EVERY, True),
        ("a model that cannot use tools", dict(manner="warm"), EVERY, False),
    ]
    for label, st, enabled, tools_ok in cases:
        fake = Fake(tools_ok=tools_ok)
        try:
            settings(**st)
            real = real_turn(fake, enabled=enabled)
            out, sent = warm(fake, enabled=enabled)
            check(f"{label}: the warm-up was sent", out["state"] == "warmed" and sent, out)
            if not sent:
                continue
            same = real.replace(b'"max_tokens": 1024', b'"max_tokens": 1') == sent
            check(f"{label}: byte for byte the real request for \"hi\", but max_tokens 1",
                  same and b'"max_tokens": 1024' in real,
                  (real[:300], sent[:300]))
            body = json.loads(sent)
            check(f"{label}: tools {'sent' if (enabled and tools_ok) else 'not sent'}",
                  ("tools" in body) == bool(enabled and tools_ok), list(body))
        finally:
            restore()
            fake.close()


def t_a_real_question_starts_the_same_way():
    fake = Fake()
    try:
        settings(manner="warm")
        real = json.loads(real_turn(fake, "what is on my calendar tomorrow", enabled=EVERY))
        _out, sent = warm(fake, enabled=EVERY)
        w = json.loads(sent)
        check("a real first question: every message before the question is the same",
              real["messages"][:-1] == w["messages"][:-1] and len(w["messages"]) >= 2,
              (real["messages"][:-1], w["messages"][:-1]))
        check("... the tools are the same, in the same order",
              json.dumps(real["tools"]) == json.dumps(w["tools"]))
        check("... and every other field but max_tokens is the same",
              {k: v for k, v in real.items() if k not in ("messages", "max_tokens")}
              == {k: v for k, v in w.items() if k not in ("messages", "max_tokens")})
        check("the warm-up's only words from anyone are the one word",
              w["messages"][-1] == {"role": "user", "content": AG.WARM_WORD}
              and [m["role"] for m in w["messages"][:-1]] == ["system"] * (len(w["messages"]) - 1))
        head, tools = AG.chat_prefix(EVERY, ollama_url=fake.url, model=MODEL)
        check("chat_prefix() is what was sent: (messages before the question, tools)",
              head == w["messages"][:-1] and tools == w["tools"])
        for key in ("options", "num_ctx", "keep_alive"):
            check(f"neither request carries {key!r} (nothing to make Ollama reload)",
                  key not in real and key not in w and f'"{key}"'.encode() not in sent)
        check("both go to /v1/chat/completions on the same Ollama",
              [p for p, _ in fake.posts] == ["/v1/chat/completions"] * 2, fake.posts)
    finally:
        restore()
        fake.close()


# --------------------------------------------------------------------------
#   2. What it never does
# --------------------------------------------------------------------------

class Spy(types.ModuleType):
    """A module that records any use of it."""
    def __init__(self, name, used):
        super().__init__(name)
        self._used = used

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        self._used.append(f"{self.__name__}.{attr}")
        raise AttributeError(attr)


def t_it_records_nothing_and_learns_nothing():
    fake = Fake()
    used: list = []
    names = ("jarvis_chat_log", "jarvis_speed", "jarvis_events", "jarvis_feedback",
             "jarvis_extract", "jarvis_auto_learn", "jarvis_skill_discovery", "jarvis_sources",
             "jarvis_voice_flow", "jarvis_intake")
    saved = {n: sys.modules.get(n) for n in names}
    try:
        settings(manner="warm")
        real_turn(fake, enabled=EVERY)          # so a turn is on record, like on the PC
        STEPS.clear()
        for n in names:
            sys.modules[n] = Spy(n, used)
        before = sorted(os.listdir(_CFG))
        out, sent = warm(fake, enabled=EVERY)
        check("the warm-up ran", out["state"] == "warmed" and sent is not None, out)
        check("it touched no chat history, speed record, event, feedback, learner or "
              "sources module", used == [], used)
        check("it published no step event (a real turn does - see the control below)",
              STEPS == [])
        check("it wrote no file in the settings folder (no speed.jsonl)",
              sorted(os.listdir(_CFG)) == before, (before, os.listdir(_CFG)))
    finally:
        for n, m in saved.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m
        restore()
        fake.close()
    fake = Fake()
    try:
        STEPS.clear()
        real_turn(fake, enabled=EVERY)
        check("CONTROL: a real turn does publish step events", len(STEPS) > 0)
        last = AG._last_turn()
        check("what is remembered of the last turn holds no words",
              set(last) == {"url", "model", "tools", "temporary", "combined"}
              and "hi" not in json.dumps(sorted(map(str, last.values()))), last)
    finally:
        fake.close()


def t_where_it_is_never_sent():
    fake = Fake()
    try:
        settings(manner="warm")
        out = AG.warm_prefix("gpt-oss:120b-cloud", ollama_url=fake.url, enabled_tools=EVERY)
        check("a cloud model: skipped, nothing sent", out["state"] == "skipped"
              and fake.chats() == [], out)
        out = AG.warm_prefix(MODEL, ollama_url="http://192.168.1.50:11434", enabled_tools=EVERY,
                             send=lambda *a: check("another machine: never sent", False))
        check("Ollama on another machine: skipped", out["state"] == "skipped", out)
        for waking, label in ((True, "not loaded"), (None, "cannot tell whether it is loaded")):
            out = AG.warm_prefix(MODEL, ollama_url=fake.url, enabled_tools=EVERY,
                                 model_waking=lambda u, m, w=waking: w)
            check(f"the model is {label}: skipped - a warm-up never loads a model",
                  out["state"] == "skipped" and fake.chats() == [], out)
        real_power = sys.modules.get("jarvis_power")
        sys.modules["jarvis_power"] = types.SimpleNamespace(current=lambda: "standby")
        try:
            out = AG.warm_prefix(MODEL, ollama_url=fake.url, enabled_tools=EVERY)
            check("on standby: skipped", out["state"] == "skipped" and fake.chats() == [], out)
        finally:
            if real_power is None:
                sys.modules.pop("jarvis_power", None)
            else:
                sys.modules["jarvis_power"] = real_power
        real_tc = sys.modules.get("jarvis_task_control")
        sys.modules["jarvis_task_control"] = types.SimpleNamespace(running=lambda: ["t1"])
        try:
            out = AG.warm_prefix(MODEL, ollama_url=fake.url, enabled_tools=EVERY)
            check("a task running: skipped", out["state"] == "skipped" and fake.chats() == [],
                  out)
        finally:
            if real_tc is None:
                sys.modules.pop("jarvis_task_control", None)
            else:
                sys.modules["jarvis_task_control"] = real_tc
        AG.warm_prefix_on = lambda: False
        out = AG.warm_prefix(MODEL, ollama_url=fake.url, enabled_tools=EVERY)
        check("switched off: nothing sent", out["state"] == "off" and fake.chats() == [], out)
    finally:
        restore()
        fake.close()


def t_the_off_switch_reads_only_a_real_false():
    saved = sys.modules.get("jarvis_framework")
    try:
        for cfg, want in (({"power": {"warm_prefix": False}}, False),
                          ({"power": {"warm_prefix": True}}, True),
                          ({"power": {"warm_prefix": "false"}}, True),
                          ({"power": {}}, True), ({}, True)):
            sys.modules["jarvis_framework"] = types.SimpleNamespace(
                load_framework=lambda *a, c=cfg, **k: c)
            check(f"[power] {cfg.get('power')} -> {'on' if want else 'off'}",
                  REAL_ON() is want)
        sys.modules["jarvis_framework"] = types.SimpleNamespace(
            load_framework=lambda *a, **k: (_ for _ in ()).throw(OSError("unreadable")))
        check("an unreadable settings file -> the default (on)",
              REAL_ON() is AG.WARM_PREFIX_DEFAULT is True)
    finally:
        if saved is None:
            sys.modules.pop("jarvis_framework", None)
        else:
            sys.modules["jarvis_framework"] = saved


# --------------------------------------------------------------------------
#   3. After learning: only on one card, never after a temporary chat
# --------------------------------------------------------------------------

def _inline(fn):
    fn()


def t_after_learning():
    fake = Fake()
    try:
        settings(manner="warm")
        real_turn(fake, enabled=EVERY)
        n = len(fake.chats())
        out = AG.warm_after_learning(learner=lambda: (fake.url, MODEL + ":latest"), spawn=_inline)
        check("one card (the learner used the chat's model and address): warmed",
              out["state"] == "started" and len(fake.chats()) == n + 1
              and AG.WARM_LAST.get("state") == "warmed", (out, AG.WARM_LAST))
        n = len(fake.chats())
        out = AG.warm_after_learning(learner=lambda: ("http://127.0.0.1:11435", "qwen3:8b"),
                                     spawn=_inline)
        check("the learner on the second card: nothing sent",
              out["state"] == "skipped" and len(fake.chats()) == n, out)
        out = AG.warm_after_learning(learner=lambda: (fake.url, "another-model"), spawn=_inline)
        check("the learner on another model: nothing sent",
              out["state"] == "skipped" and len(fake.chats()) == n, out)
        real_turn(fake, enabled=EVERY, request_extra={"temporary": True})
        n = len(fake.chats())
        out = AG.warm_after_learning(learner=lambda: (fake.url, MODEL), spawn=_inline)
        check("the last question was in a temporary chat: nothing sent",
              out["state"] == "skipped" and len(fake.chats()) == n, out)
        real_turn(fake, "let's roleplay: you are a pirate captain", enabled=EVERY)
        n = len(fake.chats())
        out = AG.warm_after_learning(learner=lambda: (fake.url, MODEL), spawn=_inline)
        check("the last question was a game (a temporary chat by itself): nothing sent",
              out["state"] == "skipped" and len(fake.chats()) == n, out)
        AG._turn_begins(fake.url, MODEL, EVERY, {},
                        AG.LaneChoice("http://127.0.0.1:11436", "big", 32768, "combined", "x"))
        AG._turn_ends()
        out = AG.warm_after_learning(learner=lambda: (fake.url, MODEL), spawn=_inline)
        check("the last question went to the bigger model on both cards: nothing sent",
              out["state"] == "skipped" and len(fake.chats()) == n, out)
        real_turn(fake, enabled=EVERY)
        out = AG.warm_after_learning(learner=lambda: (_ for _ in ()).throw(RuntimeError()),
                                     spawn=_inline)
        check("a learner lookup that raises: no error, nothing sent",
              out["state"] == "failed" and len(fake.chats()) == n + 1, out)
    finally:
        restore()
        fake.close()


def t_after_waking():
    fake = Fake()
    try:
        settings(manner="warm")
        with AG._LIVE_LOCK:
            AG._LAST_TURN.clear()
        out = AG.warm_after_waking(MODEL, fake.url)
        check("no question since Jarvis started: nothing sent (it would have to guess the "
              "tools)", out["state"] == "skipped" and fake.chats() == [], out)
        real_turn(fake, enabled={"web_search"})
        n = len(fake.chats())
        out = AG.warm_after_waking("another-model", fake.url)
        check("the model loaded is not the one chat used: nothing sent",
              out["state"] == "skipped" and len(fake.chats()) == n, out)
        out = AG.warm_after_waking(MODEL + ":latest", fake.url + "/")
        body = json.loads(fake.chats()[-1]) if len(fake.chats()) == n + 1 else {}
        check("the model chat used: warmed with the tools that turn had",
              out["state"] == "warmed"
              and [t["function"]["name"] for t in body.get("tools") or []] == ["web_search"],
              (out, list(body)))

        class FakeOllama:
            url = fake.url

            def __init__(self):
                self.loads = []

            def load(self, name):
                self.loads.append(name)

            def unload(self, name):
                pass

        class Power:
            mode = "active"

            def current(self):
                return self.mode

        seen = []
        st = S.warm_up(Power(), FakeOllama(), MODEL,
                       warmer=lambda name, url: seen.append((name, url)) or {"state": "warmed"})
        check("waking: loaded, then the words, with the loaded model and address",
              st["state"] == "ready" and seen == [(MODEL, fake.url)]
              and "rules and tool list" in st["why"], (st, seen))
        seen.clear()
        p = Power()
        p.mode = "standby"
        st = S.warm_up(p, FakeOllama(), MODEL,
                       warmer=lambda name, url: seen.append((name, url)) or {})
        check("back on standby while it loaded: no words", seen == [] and
              st["state"] == "skipped", (st, seen))
        st = S.warm_up(Power(), FakeOllama(), MODEL,
                       warmer=lambda name, url: {"state": "skipped", "why": "a task is running"})
        check("words skipped: still ready (the model is loaded), and it says why",
              st["state"] == "ready" and "a task is running" in st["why"], st)
    finally:
        restore()
        fake.close()


# --------------------------------------------------------------------------
#   4. A question arriving meanwhile does not wait for it
# --------------------------------------------------------------------------

def t_a_question_is_never_kept_waiting():
    fake = Fake()
    try:
        settings(manner="warm")
        real_turn(fake, enabled=EVERY)
        fake.hold = True
        box = {}
        t = threading.Thread(target=lambda: box.update(out=warm(fake, enabled=EVERY)[0]),
                             daemon=True)
        t.start()
        check("the warm-up reached Ollama", fake.warm_in.wait(5))
        with AG._LIVE_LOCK:
            live = AG._LIVE["warm"] is not None
        check("... and is on record as on the wire", live)
        t0 = time.monotonic()
        sent = real_turn(fake, "what time is it", enabled=EVERY)
        took = time.monotonic() - t0
        t.join(5)
        check("a question arriving cut the warm-up's connection (Ollama sees its caller go)",
              fake.warm_gone.wait(3))
        check("the warm-up says it was cancelled", (box.get("out") or {}).get("state")
              == "cancelled", box)
        check("the question was answered at once, not after the warm-up",
              json.loads(sent)["messages"][-1]["content"] == "what time is it" and took < 3,
              took)
        with AG._LIVE_LOCK:
            check("nothing left on record afterwards", AG._LIVE["warm"] is None
                  and AG._LIVE["turns"] == 0, dict(AG._LIVE))
        fake.hold = False
        # A warm-up asked for WHILE a question is being answered is not sent.
        gate = threading.Event()
        release = threading.Event()
        real_open = AG._open_stream

        def slow_open(url, payload):
            gate.set()
            release.wait(5)
            return real_open(url, payload)
        AG._open_stream = slow_open
        try:
            th = threading.Thread(target=lambda: real_turn(fake, "slow one", enabled=EVERY),
                                  daemon=True)
            th.start()
            check("(a question is being answered)", gate.wait(5))
            n = len(fake.chats())
            out = AG.warm_prefix(MODEL, ollama_url=fake.url, enabled_tools=EVERY)
            check("a warm-up while a question is being answered: skipped, nothing sent",
                  out["state"] == "skipped" and len(fake.chats()) == n, out)
            release.set()
            th.join(5)
        finally:
            AG._open_stream = real_open
        check("the count is back to none after a turn that ran", AG.turns_running() == 0)
    finally:
        fake.hold = False
        restore()
        fake.close()


def t_a_turn_that_raises_is_still_uncounted():
    real = AG._TurnWatch
    AG._TurnWatch = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        try:
            AG.run_local_turn([{"role": "user", "content": "x"}], MODEL,
                              ollama_url="http://127.0.0.1:9", stream_out=lambda b: None)
        except RuntimeError:
            pass
        check("a turn that raised is no longer counted as running", AG.turns_running() == 0)
        try:
            AG.run_local_turn([{"role": "user", "content": "x"}], MODEL,
                              ollama_url="http://127.0.0.1:9", stream_out=lambda b: None,
                              enabled_tools=5, request="not a dict")
        except RuntimeError:
            pass
        check("odd arguments: still counted exactly once, and uncounted after",
              AG.turns_running() == 0 and AG._last_turn().get("temporary") is False)
    finally:
        AG._TurnWatch = real


# --------------------------------------------------------------------------
#   5. warm-prefix.patch
# --------------------------------------------------------------------------

def t_its_place_in_the_stack():
    order = _stack.order()
    # Last when it was written; photo-reminder.patch (an install block beside
    # brain-reads') now follows it. What matters is that nothing after it
    # touches the learner-thread lines it rewrites.
    check(f"{PATCH} is in apply-patches.ps1's list", PATCH in order, order[-3:])
    for later in order[order.index(PATCH) + 1:] if PATCH in order else []:
        body = (HERE / later).read_text(encoding="utf-8")
        check(f"{later}, after it, leaves the learner thread's lines alone",
              "self._pass()" not in body and "EXTRACT_MIN_GAP" not in body)
    patch = (HERE / PATCH).read_text(encoding="utf-8")
    check("it patches jarvis_hud.py and nothing else",
          sorted(l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/"))
          == [TARGET])
    context = [l[1:] for l in patch.splitlines()
               if (l.startswith(" ") or (l.startswith("-") and not l.startswith("---")))
               and l.strip()]
    written = {l[1:] for name in ("rebuilt-patches/extraction-wiring.patch",
                                  "extraction-wiring.patch")
               for l in (HERE / name).read_text(encoding="utf-8").splitlines()
               if l.startswith("+")}
    check("every line it keeps or replaces is one extraction-wiring.patch adds",
          context and all(c in written for c in context),
          [c for c in context if c not in written])
    later = order[order.index("rebuilt-patches/extraction-wiring.patch")
                  if "rebuilt-patches/extraction-wiring.patch" in order
                  else order.index("extraction-wiring.patch"):order.index(PATCH) + 1]
    touched = [n for n in later[1:-1]
               if "if self._pass() and self._stop.wait(EXTRACT_MIN_GAP):"
               in (HERE / n).read_text(encoding="utf-8")]
    check("no patch between extraction-wiring and this one touches those lines", not touched,
          touched)


def _patched():
    order = _stack.order()
    order = order[:order.index(PATCH)]
    text, log = _stack.stand_in(TARGET, order)
    if text is None:
        check(f"a stand-in of {TARGET} could be built", False, log)
        return None, None
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return None, None
    patch = (HERE / PATCH).read_text(encoding="utf-8")
    d = Path(tempfile.mkdtemp(prefix="jarvis-warm-prefix-"))
    try:
        (d / TARGET).write_text(text, encoding="utf-8", newline="\n")
        one = "".join(h for h, _ in _stack.hunks(patch, TARGET))
        (d / "p.patch").write_text(f"--- a/{TARGET}\n+++ b/{TARGET}\n{one}",
                                   encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        after = (d / TARGET).read_text(encoding="utf-8") if r.returncode == 0 else None
        r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                            text=True)
        back = (d / TARGET).read_text(encoding="utf-8") == text
        check(f"{TARGET}: applies to what the earlier patches wrote, and reverses",
              after is not None and r2.returncode == 0 and back, (r.stderr, r2.stderr))
        return text, after
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _loop_tail(after: str):
    """The patched lines from `_asked = self._pass()` to the `return` after
    the wait, as a function: loop_once(self, EXTRACT_MIN_GAP) -> "stopped" |
    "carried on"."""
    lines = after.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "_asked = self._pass()")
    end = next(i for i in range(start, len(lines))
               if lines[i].strip() == "if _asked and self._stop.wait(EXTRACT_MIN_GAP):")
    body = [l if l.strip() != "return" else l.replace("return", 'return "stopped"')
            for l in textwrap.dedent("\n".join(lines[start:end + 2])).splitlines()]
    src = ("def loop_once(self, EXTRACT_MIN_GAP):\n"
           + textwrap.indent("\n".join(body), "    ") + '\n    return "carried on"\n')
    env: dict = {}
    exec(compile(src, PATCH, "exec"), env)
    return env["loop_once"], src


def t_what_the_patch_does():
    before, after = _patched()
    if after is None:
        return
    check("CONTROL: before this patch, the learner never warms anything",
          "warm_after_learning" not in before)
    loop_once, src = _loop_tail(after)

    class Learner:
        def __init__(self, asked, stop=False):
            self.asked, self.waits = asked, []
            outer = self

            class Stop:
                def wait(self, s):
                    outer.waits.append(s)
                    return stop
            self._stop = Stop()

        def _pass(self):
            return self.asked

    calls = []
    saved = sys.modules.get("jarvis_agent")
    sys.modules["jarvis_agent"] = types.SimpleNamespace(
        warm_after_learning=lambda: calls.append(1))
    try:
        L = Learner(True)
        got = loop_once(L, 300)
        check("a pass that asked a model: the warm-up is asked for, then the usual wait",
              calls == [1] and L.waits == [300] and got == "carried on", (calls, L.waits, got))
        calls.clear()
        L = Learner(False)
        loop_once(L, 300)
        check("a pass that asked nothing: no warm-up and no wait, as before",
              calls == [] and L.waits == [])
        L = Learner(True, stop=True)
        check("stopped during the wait: the loop ends, as before",
              loop_once(L, 300) == "stopped")
        sys.modules["jarvis_agent"] = types.SimpleNamespace(
            warm_after_learning=lambda: (_ for _ in ()).throw(RuntimeError("x")))
        L = Learner(True)
        check("a warm-up that raises: no error, the usual wait",
              loop_once(L, 300) == "carried on" and L.waits == [300])
        sys.modules["jarvis_agent"] = None       # `import jarvis_agent` now raises
        L = Learner(True)
        check("jarvis_agent cannot be loaded: no error, the usual wait",
              loop_once(L, 300) == "carried on" and L.waits == [300])
    except Exception as exc:
        check("the patched lines run", False, f"{exc!r}\n{src}")
    finally:
        if saved is None:
            sys.modules.pop("jarvis_agent", None)
        else:
            sys.modules["jarvis_agent"] = saved


if __name__ == "__main__":
    try:
        for fn in (t_the_same_bytes_as_a_real_turn, t_a_real_question_starts_the_same_way,
                   t_it_records_nothing_and_learns_nothing, t_where_it_is_never_sent,
                   t_the_off_switch_reads_only_a_real_false, t_after_learning, t_after_waking,
                   t_a_question_is_never_kept_waiting, t_a_turn_that_raises_is_still_uncounted,
                   t_its_place_in_the_stack, t_what_the_patch_does):
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    finally:
        shutil.rmtree(_CFG, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
