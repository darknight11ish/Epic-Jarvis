"""test_chatbot_api.py - the chatbot driver's API adapters
(jarvis_chatbot_api.py): ChatGPT, DeepSeek, Mistral, Grok, OpenRouter and
Groq through each company's OpenAI-style API, with a key saved on this PC.

    python3 backend/test_chatbot_api.py

The owner's decision (CLAUDE.md, "The chatbot driver becomes versatile",
2026-09-28): one adapter speaking the common OpenAI-style API; keys under
rule 3 (never logged, sent only to the one service they belong to, never in
plain text on disk); each host a named way out.

What this proves, against a FAKE OpenAI-style server on 127.0.0.1 (each
preset pointed at it), a second fake server a redirect points to, fake
Credential Manager stores, the REAL jarvis_chatbot core, jarvis_router,
jarvis_search, jarvis_mail_mask, jarvis_task_control and jarvis_stop_all:

  - six presets, each its own chatbot id, kind "api", https, its own
    Credential Manager entry; the card names the service, host and model and
    says it costs money with no money cap yet - and says nothing of captchas;
  - no key: ready=False with the one PowerShell line, refused before any
    card; a store that cannot be read says so; the command line saves and
    forgets a key without ever printing it;
  - the key goes in the Authorization header to the pinned host only; the
    address check refuses another host, another port, plain http and a user
    name; a redirect is refused and the redirect target receives nothing;
  - the key is never in a log line (logging captured at DEBUG), stdout, the
    audit, the session view, the transcript or an error's words;
  - 429: one retry after a short Retry-After, never two; a long Retry-After
    is not retried at all; 5xx, 401, 402, 404, a timeout, an unreadable or
    empty answer each end with plain words and no retry;
  - usage (tokens) is recorded from every answer and shown in the session;
  - the conversation history is resent each time (the API has no memory);
  - a whole core session through the adapter: the core's last check still
    runs before every send - a planted secret, a planted saved fact and a
    goal with a secret never reach the server;
  - close() stops a retry wait at once; the module is shipped.

No pytest. The only sockets are to the two fake servers on 127.0.0.1.
"""
from __future__ import annotations

import contextlib
import http.server
import io
import json
import logging
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

require_shipped("jarvis_chatbot.py", "jarvis_chatbot_api.py", "jarvis_token_store.py",
                "jarvis_local_http.py", "jarvis_task_control.py", "jarvis_stop_all.py",
                "jarvis_search.py", "jarvis_mail_mask.py", "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chatbot-api-"))
CFG: dict = {}
TIERS: dict = {}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {"chatbot": CFG}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

import jarvis_token_store as TS  # noqa: E402
import jarvis_task_control as TC  # noqa: E402
import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_api as API  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   Fakes. Secrets built by joining strings, as test_reach.py does.
# --------------------------------------------------------------------------

KEY = "sk-" + "proj-" + "FAKEkeyForJarvisTests" + "0123456789"
OTHER_KEY = "gsk_" + "FAKEgroqKey" + "9876543210"
FAKE_GITHUB = "gh" + "p_" + "Fak3" + "0123456789abcdefghijklmnopqrstuv"
SISTER = "Zyl" + "vana"
FACTS = [f"The owner's sister is called {SISTER}"]
GOAL = "Find out how to keep houseplants alive in a flat that gets very little light."

STORE: dict = {}


class FakeStore:
    def __init__(self, target):
        self.target = target

    def read(self):
        return STORE.get(self.target)

    def write(self, value):
        STORE[self.target] = value

    def delete(self):
        return STORE.pop(self.target, None) is not None


class BrokenStore:
    def __init__(self, target):
        pass

    def read(self):
        raise TS.StoreError("reading failed (Windows error 5)")


def use_store(factory=FakeStore):
    TS._STORE_FACTORY = factory


use_store()


class Server:
    """An OpenAI-style server on 127.0.0.1. `script` is a list of
    (status, headers, body) answers used in order (the last repeats), or
    None for the default: a plain reply with usage."""

    def __init__(self):
        self.requests: list = []
        self.script: list = []
        self.delay = 0.0
        self.n = 0
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                outer.requests.append({"path": self.path, "method": self.command,
                                       "headers": dict(self.headers.items()),
                                       "body": raw.decode("utf-8", "replace")})
                outer.n += 1
                if outer.delay:
                    time.sleep(outer.delay)
                if outer.script:
                    status, headers, body = outer.script[min(outer.n, len(outer.script)) - 1]
                else:
                    status, headers, body = 200, {}, reply_body(
                        REPLIES[(outer.n - 1) % len(REPLIES)])
                data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
                try:
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_POST = _answer
            do_GET = _answer

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path="/v1"):
        return f"http://127.0.0.1:{self.port}{path}"

    def reset(self):
        self.requests.clear()
        self.script = []
        self.delay = 0.0
        self.n = 0


REPLIES = [
    "Snake plants, ZZ plants and pothos tolerate dim corners remarkably well.",
    "Horticultural extension services publish guidance about sansevieria resilience.",
    "Grow lamps deliver consistent spectrum; windowsills vary seasonally.",
    "Chlorosis follows reduced photosynthesis when chlorophyll production drops.",
    "Reduce frequency during dormancy; check substrate moisture first.",
]


def reply_body(text, prompt=11, completion=7):
    return {"id": "x", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                      "total_tokens": prompt + completion}}


SRV = Server()
ELSEWHERE = Server()
ORIGINAL = dict(API.PRESETS)


def point_all():
    """Every preset at the fake server; each keeps its own id and key entry."""
    API._TEST_LOOPBACK_OK = True
    for pid in API.PRESETS:
        API.point_at(pid, SRV.url())


def restore():
    API._TEST_LOOPBACK_OK = False
    for pid, p in ORIGINAL.items():
        API.PRESETS[pid] = p
    API._reset_models_for_tests()


def clean():
    CB._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()
    SRV.reset()
    ELSEWHERE.reset()
    STORE.clear()
    CFG.clear()
    TIERS.clear()
    CARDS.clear()
    AUDIT.clear()
    use_store()
    restore()


def wait_reply(a, most=15.0):
    end = time.time() + most
    while time.time() < end:
        got = a.read_reply(0.2)
        if got is not None:
            return got
    return None


def expect_error(a, most=15.0):
    try:
        wait_reply(a, most)
    except API.ApiUnavailable as exc:
        return exc
    return None


# ---- the core's fakes (the same shape test_chatbot.py uses) ----------------

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
AUDIT: list = []


def approve(action, detail, prompt):
    CARDS.append((action, detail, prompt))
    return Verdict(True, "approved")


QUESTIONS = ["Which plants cope best with a north-facing window?",
             "What sources support the claim about snake plants?",
             "How does a grow lamp compare with moving plants closer to glass?",
             "Why do leaves turn yellow in low light?",
             "How often should watering happen in winter?"]


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
                  "reason": "", "notes": f"note {self.n}"}
        return {"message": {"content": json.dumps(mv)}, "done_reason": "stop"}


def deps(model=None, facts=None):
    clock = Clock()
    return CB.Deps(model=model or Model(),
                   saved_facts=lambda m: list(FACTS if facts is None else facts),
                   names_for_facts=lambda f: {}, owner_busy=lambda: False,
                   second_lane=lambda: None, full_version_on=lambda: False,
                   main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
                   tier_of=lambda a: TIERS.get(a, "ask"), gate=approve,
                   activity=lambda s, d="": None,
                   audit=lambda e, d: AUDIT.append((e, d)), clock=clock, sleep=clock.sleep)


def sent_bodies():
    out = []
    for r in SRV.requests:
        try:
            out.append(json.loads(r["body"]))
        except ValueError:
            out.append({})
    return out


# ==========================================================================
#   1. The presets
# ==========================================================================

def t_presets():
    clean()
    want = {"openai_api": "api.openai.com", "deepseek_api": "api.deepseek.com",
            "mistral_api": "api.mistral.ai", "xai_api": "api.x.ai",
            "openrouter_api": "openrouter.ai", "groq_api": "api.groq.com"}
    got = {c["id"]: c for c in CB.choices()}
    for pid, host in want.items():
        c = got.get(pid) or {}
        check(f"{pid} is its own chatbot, kind api, host {host}",
              c.get("host") == host and c.get("kind") == "api" and c.get("built"), c)
        check(f"{pid} is https", API.PRESETS[pid].base_url.startswith("https://"
                                                                        + host))
    check("each service has its own Credential Manager entry",
          len(set(API.KEY_TARGETS.values())) == len(API.PRESETS)
          and all(t.startswith("Jarvis Backend/") and t.endswith(" API key")
                  for t in API.KEY_TARGETS.values()), API.KEY_TARGETS)
    check("every preset says where its address was checked, or 'unverified'",
          all(p.verified for p in API.PRESETS.values())
          and API.PRESETS["deepseek_api"].verified == "unverified")
    check("the Gemini website and the local AI are still listed beside them",
          got.get("gemini_web", {}).get("kind") == "website"
          and got.get("local_ai", {}).get("kind") == "local")


def t_the_card():
    clean()
    point_all()
    STORE[API.KEY_TARGETS["openai_api"]] = KEY
    s = CB.plan("openai_api", GOAL, deps=deps())
    text = CB.describe(s)
    check("a preset with a key plans with no problem", not s.problem, s.problem)
    check("the card names the service, its host and its model",
          "ChatGPT (OpenAI API)" in text and "127.0.0.1" in text and "gpt-5-mini" in text,
          text[:400])
    check("the card says it costs money and that there is no money limit yet",
          "costs a little" in text and "no money limit yet" in text)
    check("the card says the key goes to that host only and a redirect is refused",
          "key is never sent anywhere else" in text and "redirect is refused" in text)
    check("the card says nothing about captchas (that is for websites)",
          "captcha" not in text.lower(), text)
    check("the card never holds the key", KEY not in text)
    STORE[API.KEY_TARGETS["openrouter_api"]] = OTHER_KEY
    or_text = CB.describe(CB.plan("openrouter_api", GOAL, deps=deps()))
    check("OpenRouter's card says it passes messages on to the model's company",
          "passes each message on" in or_text)
    CFG["openai_api_model"] = "gpt-4.1-nano"
    API._reset_models_for_tests()
    s = CB.plan("openai_api", GOAL, deps=deps())
    check("a [chatbot] openai_api_model line changes the model the card names",
          "gpt-4.1-nano" in CB.describe(s))
    CFG["openai_api_model"] = "bad model name; rm -rf"
    API._reset_models_for_tests()
    s = CB.plan("openai_api", GOAL, deps=deps())
    check("a model line that is not a model name is refused before any card",
          s.state == "refused" and "not a model name" in s.problem, s.problem)


# ==========================================================================
#   2. Keys: ready, the command line, Credential Manager
# ==========================================================================

def t_no_key_is_not_ready():
    clean()
    point_all()
    c = next(x for x in CB.choices() if x["id"] == "openai_api")
    check("no key: not ready, with the one PowerShell line",
          c["ready"] is False and "py -3 jarvis_chatbot_api.py key openai" in c["note"]
          and "platform.openai.com" in c["note"], c)
    s = CB.plan("openai_api", GOAL, deps=deps())
    code, _ = CB.start(s, deps=deps(), wait=True)
    check("no key: plan() refuses with that note, and no card, no request",
          s.state == "refused" and s.problem == c["note"] and code == 400 and not CARDS
          and not SRV.requests, (s.problem, CARDS, SRV.requests))
    use_store(BrokenStore)
    c = next(x for x in CB.choices() if x["id"] == "groq_api")
    check("a Credential Manager that cannot be read: not ready, and it says so",
          c["ready"] is False and "Credential Manager" in c["note"], c)
    use_store()
    STORE[API.KEY_TARGETS["openai_api"]] = "short"
    check("a damaged key (too short) counts as no key",
          API.key_saved("openai_api") is False)


def t_command_line():
    clean()
    lines = []
    rc = API._main(["key", "openai"], ask_secret=lambda prompt: KEY, out=lines.append)
    check("`key openai` saves into the openai entry",
          rc == 0 and STORE.get(API.KEY_TARGETS["openai_api"]) == KEY, lines)
    check("... and never prints the key", KEY not in "\n".join(lines), lines)
    rc = API._main(["key", "openai"], ask_secret=lambda prompt: "has space in it",
                   out=lines.append)
    check("a key with spaces is refused, in plain words", rc == 1
          and "no spaces" in lines[-1], lines[-1])
    rc = API._main(["key", "nope"], ask_secret=lambda p: KEY, out=lines.append)
    check("an unknown service is refused", rc == 2)
    lines.clear()
    API._main(["status"], out=lines.append)
    check("`status` says which keys are saved, never the key",
          any("ChatGPT" in ln and "key saved" in ln for ln in lines)
          and KEY not in "\n".join(lines), lines)
    rc = API._main(["forget-key", "openai"], out=lines.append)
    check("`forget-key openai` removes it", rc == 0
          and API.KEY_TARGETS["openai_api"] not in STORE)


# ==========================================================================
#   3. Pinning, redirects, the key's one destination
# ==========================================================================

def t_pinning():
    clean()
    p = API.PRESETS["openai_api"]
    check("its own https address passes",
          API.endpoint_problem("https://api.openai.com/v1/chat/completions", p) == "")
    for bad in ("https://api.openai.com.evil.example/v1/chat/completions",
                "https://evil.example/v1/chat/completions",
                "https://api.openai.com:8443/v1/chat/completions",
                "http://api.openai.com/v1/chat/completions",
                "https://user:pw@api.openai.com/v1/chat/completions"):
        check(f"refused: {bad}", API.endpoint_problem(bad, p) != "")
    # A preset pointed at plain http on this PC opens only in the tests.
    API.point_at("openai_api", SRV.url())
    STORE[API.KEY_TARGETS["openai_api"]] = KEY
    a = CB.ADAPTERS["openai_api"].factory()
    try:
        a.open()
        opened = True
    except API.ApiUnavailable as exc:
        opened = False
        words = exc.owner_words
    check("plain http is refused outside the tests, before any request",
          not opened and "https" in words and not SRV.requests)


def t_key_goes_to_the_pinned_host_only():
    clean()
    point_all()
    STORE[API.KEY_TARGETS["openai_api"]] = KEY
    STORE[API.KEY_TARGETS["groq_api"]] = OTHER_KEY
    a = CB.ADAPTERS["openai_api"].factory()
    a.open()
    a.send("Which plants like shade?")
    got = wait_reply(a)
    r = SRV.requests[0]
    check("one POST to <base>/chat/completions", r["method"] == "POST"
          and r["path"] == "/v1/chat/completions", r["path"])
    check("the key is in the Authorization header", r["headers"].get("Authorization")
          == "Bearer " + KEY)
    check("... and nowhere in the body", KEY not in r["body"])
    body = json.loads(r["body"])
    check("the body is the model and exactly the message - no system prompt, nothing else",
          body == {"model": "gpt-5-mini", "stream": False,
                   "messages": [{"role": "user", "content": "Which plants like shade?"}]},
          body)
    check("the reply comes back", got == REPLIES[0], got)
    check("another service's key is never sent with it", OTHER_KEY not in json.dumps(r))
    a.close()
    # The redirect: the server points somewhere else; nothing is followed.
    SRV.reset()
    SRV.script = [(302, {"Location": ELSEWHERE.url("/v1/chat/completions")}, b"")]
    a = CB.ADAPTERS["openai_api"].factory()
    a.open()
    a.send("Which plants like shade?")
    err = expect_error(a)
    check("a redirect is refused, with plain words",
          err is not None and err.code == "redirect" and "never follows" in err.owner_words,
          err and err.owner_words)
    check("... and the redirect target received nothing - not the key, not the message",
          not ELSEWHERE.requests, ELSEWHERE.requests)
    a.close()


def t_history_and_usage():
    clean()
    point_all()
    STORE[API.KEY_TARGETS["mistral_api"]] = KEY
    a = CB.ADAPTERS["mistral_api"].factory()
    a.open()
    a.send("First question?")
    wait_reply(a)
    a.send("Second question?")
    wait_reply(a)
    b = json.loads(SRV.requests[1]["body"])
    check("the second request resends the conversation (the API keeps none)",
          [m["role"] for m in b["messages"]] == ["user", "assistant", "user"]
          and b["messages"][1]["content"] == REPLIES[0], b["messages"])
    u = a.usage()
    check("usage adds up what each answer reported", u["prompt_tokens"] == 22
          and u["completion_tokens"] == 14 and u["total_tokens"] == 36 and u["requests"] == 2
          and u["model"] == "mistral-small-latest", u)
    a.close()
    check("close() drops the key and the history", a._key is None and a._history == []
          and a.status().state == "gone")


# ==========================================================================
#   4. Errors: 429, 5xx, 401, 402, 404, timeouts, bad answers
# ==========================================================================

def _adapter(pid="openai_api", **kw):
    STORE[API.KEY_TARGETS[pid]] = KEY
    a = API.ApiChatbot(API.PRESETS[pid], API.model_for(pid)[0], **kw)
    a.open()
    return a


def t_rate_limits():
    clean()
    point_all()
    waits = []
    SRV.script = [(429, {"Retry-After": "3"}, {"error": {"message": "slow down"}}),
                  (200, {}, reply_body("After waiting."))]
    a = _adapter(sleep=waits.append)
    a.send("Hello?")
    got = wait_reply(a)
    check("a 429 with a short Retry-After waits that long and retries ONCE",
          got == "After waiting." and waits == [3.0] and len(SRV.requests) == 2
          and a.usage()["retries"] == 1, (got, waits, len(SRV.requests)))
    SRV.reset()
    waits.clear()
    SRV.script = [(429, {"Retry-After": "1"}, {"error": {}})]
    a = _adapter(sleep=waits.append)
    a.send("Hello?")
    err = expect_error(a)
    check("a second 429 ends it - exactly two requests, never a storm",
          err is not None and err.code == "http_429" and len(SRV.requests) == 2
          and "429" in err.owner_words, (err and err.owner_words, len(SRV.requests)))
    SRV.reset()
    waits.clear()
    SRV.script = [(429, {"Retry-After": "120"}, {"error": {}})]
    a = _adapter(sleep=waits.append)
    a.send("Hello?")
    err = expect_error(a)
    check("a 429 asking for longer than Jarvis waits is not retried at all",
          err is not None and err.code == "rate_limited" and len(SRV.requests) == 1
          and not waits and "120 seconds" in err.owner_words, err and err.owner_words)
    SRV.reset()
    waits.clear()
    SRV.script = [(429, {}, {"error": {}}), (200, {}, reply_body("ok"))]
    a = _adapter(sleep=waits.append)
    a.send("Hello?")
    check("a 429 without Retry-After waits the default, once",
          wait_reply(a) == "ok" and waits == [API.RETRY_DEFAULT])
    # A close() during the wait stops it at once (the real wait, no stand-in).
    SRV.reset()
    SRV.script = [(429, {"Retry-After": "15"}, {"error": {}})]
    a = _adapter()
    a.send("Hello?")
    time.sleep(0.5)
    t0 = time.time()
    a.close()
    err = expect_error(a, 5.0)
    check("close() during a retry wait ends it at once, with no second request",
          err is not None and time.time() - t0 < 3 and len(SRV.requests) == 1,
          (err, len(SRV.requests)))


def t_other_errors():
    clean()
    point_all()
    leaky = {"error": {"message": f"Incorrect API key provided: {KEY[:8]}****{KEY[-4:]}"}}
    cases = [
        (401, leaky, "key", "http_401"),
        (403, {}, "key", "http_403"),
        (402, {}, "credit", "http_402"),
        (404, {}, "gpt-5-mini", "http_404"),
        (500, {}, "problem on its side (error 500)", "http_500"),
        (503, {}, "problem on its side (error 503)", "http_503"),
        (400, {}, "refused the message (error 400)", "http_400"),
    ]
    for status, body, words, code in cases:
        SRV.reset()
        SRV.script = [(status, {}, body)]
        a = _adapter()
        a.send("Hello?")
        err = expect_error(a)
        check(f"{status}: ends with plain words, one request, no retry",
              err is not None and err.code == code and words in err.owner_words
              and len(SRV.requests) == 1, (err and err.owner_words, len(SRV.requests)))
        check(f"{status}: the words never quote the service's own error text",
              err is not None and "Incorrect API key" not in err.owner_words
              and KEY[-4:] not in err.owner_words)
    SRV.reset()
    SRV.script = [(401, {}, leaky)]
    a = _adapter()
    a.send("Hello?")
    err = expect_error(a)
    check("401 says how to save the key again", err is not None
          and "py -3 jarvis_chatbot_api.py key openai" in err.owner_words)
    SRV.reset()
    SRV.delay = 1.5
    a = _adapter(http_timeout=0.4)
    a.send("Hello?")
    err = expect_error(a)
    check("no answer in time: plain words", err is not None and err.code == "timeout"
          and "did not answer within" in err.owner_words, err and err.owner_words)
    SRV.reset()
    for body, what in ((b"<html>not json</html>", "unreadable"),
                       ({"choices": []}, "unreadable"),
                       (reply_body("   "), "empty")):
        SRV.reset()
        SRV.script = [(200, {}, body)]
        a = _adapter()
        a.send("Hello?")
        err = expect_error(a)
        check(f"a bad answer ({what}) ends with plain words", err is not None
              and err.code == what, err and err.code)
    SRV.reset()
    SRV.script = [(200, {}, {"choices": [{"message": {"content": [
        {"type": "text", "text": "Part one. "}, {"type": "text", "text": "Part two."}]}}]})]
    a = _adapter()
    a.send("Hello?")
    check("content given as a list of text parts is joined", wait_reply(a)
          == "Part one. Part two.")
    # No server at all.
    dead = API.point_at("deepseek_api", "http://127.0.0.1:9/v1")
    a = API.ApiChatbot(dead, "deepseek-chat")
    STORE[API.KEY_TARGETS["deepseek_api"]] = KEY
    a.open()
    a.send("Hello?")
    err = expect_error(a)
    check("no connection: plain words", err is not None and err.code == "connection"
          and "could not reach" in err.owner_words, err and err.owner_words)


# ==========================================================================
#   5. A whole conversation through the core
# ==========================================================================

@contextlib.contextmanager
def captured():
    """Every log record at DEBUG, stdout and stderr."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    old = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield lambda: buf.getvalue() + out.getvalue() + err.getvalue()
    finally:
        root.removeHandler(handler)
        root.setLevel(old)


def t_a_whole_conversation():
    clean()
    point_all()
    STORE[API.KEY_TARGETS["openai_api"]] = KEY
    with captured() as logs:
        d = deps()
        s = CB.plan("openai_api", GOAL, max_turns=3, deps=d)
        code, _ = CB.start(s, deps=d, wait=True)
        view = CB.session_view(s)
    check("one card, then the conversation ran to its message limit",
          code == 202 and len(CARDS) == 1 and s.ended_code == "limit_turns"
          and s.turns_used == 3, (code, s.ended_code, s.ended_words))
    check("exactly three requests reached the service", len(SRV.requests) == 3,
          len(SRV.requests))
    first = sent_bodies()[0]
    check("the first message sent is the goal, word for word",
          first["messages"] == [{"role": "user", "content": GOAL}], first)
    check("the replies are outside text in the transcript",
          all(t["outside_text"] and t["source"] == CB.SOURCE
              for t in s.transcript if t["who"] == "chatbot"))
    check("the session view shows the token counts",
          view["usage"] and view["usage"]["prompt_tokens"] == 33
          and view["usage"]["requests"] == 3, view.get("usage"))
    blob = logs() + json.dumps(view) + json.dumps(AUDIT) + json.dumps(CARDS, default=str)
    check("the key is in no log line, output, audit, card or session view",
          KEY not in blob and KEY[-10:] not in blob)
    check("the adapter was closed at the end (key dropped)", s.adapter is None)


def t_the_last_check_still_runs():
    clean()
    point_all()
    STORE[API.KEY_TARGETS["openai_api"]] = KEY
    # A driver that keeps trying to send a planted secret, then a saved fact.
    leaks = [f"Is the token {FAKE_GITHUB} still valid?", f"Would {SISTER} like a fern?"]

    def leaky(n):
        return {"move": "deeper", "message": leaks[(n - 1) % 2], "reason": "",
                "notes": ""}
    d = deps(model=Model(moves=leaky))
    s = CB.plan("openai_api", GOAL, max_turns=4, deps=d)
    CB.start(s, deps=d, wait=True)
    bodies = json.dumps(sent_bodies())
    check("only the goal was sent; the leaking follow-ups were blocked and it paused",
          s.state == "paused" and s.paused_code == "blocked" and len(SRV.requests) == 1,
          (s.state, s.paused_code, len(SRV.requests)))
    check("the planted secret and the saved fact never reached the service",
          FAKE_GITHUB not in bodies and SISTER not in bodies)
    CB.stop(s.id, deps=d)
    clean()
    point_all()
    STORE[API.KEY_TARGETS["openai_api"]] = KEY
    s = CB.plan("openai_api", f"Check whether {FAKE_GITHUB} works", deps=deps())
    code, _ = CB.start(s, deps=deps(), wait=True)
    check("a goal holding a secret is refused before any card and any request",
          s.state == "refused" and code == 400 and not CARDS and not SRV.requests, s.problem)


def t_an_error_ends_the_conversation_plainly():
    clean()
    point_all()
    STORE[API.KEY_TARGETS["openai_api"]] = KEY
    SRV.script = [(401, {}, {"error": {"message": "nope"}})]
    d = deps()
    s = CB.plan("openai_api", GOAL, deps=d)
    CB.start(s, deps=d, wait=True)
    check("a refused key ends the conversation with the adapter's own plain words",
          s.state == "done" and s.ended_code == "adapter_failed"
          and "did not accept the key" in s.ended_words and KEY not in s.ended_words,
          s.ended_words)
    check("... after exactly one request", len(SRV.requests) == 1)


def t_shipped_and_documented():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("shipped: in _where.SHIPPED and apply-patches.ps1",
          "jarvis_chatbot_api.py" in SHIPPED and "'jarvis_chatbot_api.py'" in ps1)
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    arch = (REPO / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    check("JARVIS-API.md section 60 describes the API adapters",
          "jarvis_chatbot_api.py" in api and "openai_api" in api)
    check("ARCHITECTURE section 4 names every API host as a way out",
          all(p.host in arch for p in ORIGINAL.values()))
    src = (HERE / "jarvis_chatbot_api.py").read_text(encoding="utf-8")
    check("the module never imports logging or prints the key",
          "import logging" not in src and "print(self._key" not in src)


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
        TS._STORE_FACTORY = None
        SRV.httpd.shutdown()
        ELSEWHERE.httpd.shutdown()
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
