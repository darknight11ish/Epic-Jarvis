"""The chat reply, as the PC really sends it, for the three apps' readers.

WHAT THIS IS

`/api/chat` has one producer (jarvis_hud.py's two branches: a plain relay of
Ollama's bytes, and jarvis_agent.run_local_turn) and three readers: the phone
(ChatChunkParser + ChatSession), the quickbar (main.js consumeLine) and the HUD
page (jarvis_hud.html). Each reader used to be tested against bodies someone
typed in - `{"done":true}`, a bare "Hello there." as text/plain - that no
server has ever sent. The HUD's reader passed its tests and failed on the real
thing ("Unexpected token 'd'").

So this RUNS the producer on Ollama's real stream (_ollama_wire.py, transcribed
from Ollama's source) and writes what comes out - body AND Content-Type - to
one fixture file, `chat-stream-cases.json`, kept in two places:

    jarvis-client/app/src/test/resources/   read by ChatStreamContractTest.kt
    jarvis-desktop/tests/fixtures/          read by tests/chat-stream.mjs

and fails if either copy is not exactly what the producer makes today. Each
case also says what an app must show - the words (from what the MODEL said,
not from any reader), whether the answer finished, was cut short at the
length limit, failed (and the sentence), and what the PC said it was waiting
for.

    python3 test_chat_stream_contract.py            check
    python3 test_chat_stream_contract.py --write    regenerate both copies
"""
import json
import re
import sys
import time
import traceback
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
import jarvis_agent as AG  # noqa: E402
import _ollama_wire as W  # noqa: E402

AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

COPIES = [REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "chat-stream-cases.json",
          REPO / "jarvis-desktop" / "tests" / "fixtures" / "chat-stream-cases.json"]

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _normalise(body: bytes) -> str:
    """Time-based ids and timestamps fixed, and a run of keepalives (how many
    depends on timing) made one - so the fixture is the same on every run."""
    s = body.decode("utf-8")
    s = re.sub(r'"id":"chatcmpl-jarvis-\d+"', '"id":"chatcmpl-jarvis-0"', s)
    s = re.sub(r'"created":\d+', '"created":1790000000', s)
    # "thinking" and "working" appear only if this machine is slow enough
    # that a step outlasts STATUS_DELAY - timing, not behaviour. "approval"
    # is the one the cases are about, and is kept.
    s = re.sub(r": jarvis-status (thinking|working)\n\n", "", s)
    s = re.sub(r"(: keepalive\n\n)+", ": keepalive\n\n", s)
    s = re.sub(r"^\n+", "\n", s)
    return s


def _gate(wait):
    def gate(action, detail, prompt):
        time.sleep(wait)

        class V:
            allowed = True
            reason = "approved"
            outcome = "approved"
        return V()
    return gate


def _agent(bodies, *, stream=True, wait=0.0, model="jarvis-primary", legacy=False,
           keepalive=1000.0):
    it = iter(bodies)

    def opener(url, payload):
        b = next(it)
        if isinstance(b, BaseException):
            raise b
        return W.FakeResponse(W.stream(b, model=model, legacy=legacy))
    out = []
    AG.run_local_turn([{"role": "user", "content": "hi"}], model, ollama_url="http://ollama",
                      stream_out=out.append, open_stream=opener, stream=stream,
                      enabled_tools={"calculator"}, gate_check=_gate(wait),
                      context_length=16384, keepalive_seconds=keepalive,
                      status_delay=0.05 if wait else 1000.0)
    return _normalise(b"".join(out)), AG.content_type(stream)


def _http_error(code, message):
    e = urllib.error.HTTPError("http://ollama/v1/chat/completions", code, "err", {}, None)
    body = W.error_body(code, message)
    e.read = lambda *a: body
    return e


REFUSED = urllib.error.URLError(ConnectionRefusedError(10061, "No connection could be made "
                                                              "because the target machine "
                                                              "actively refused it"))


def build_cases() -> list:
    cases = []

    def add(name, producer, body_ct, expect):
        body, ct = body_ct
        cases.append({"name": name, "producer": producer, "content_type": ct,
                      "body": body, "expect": expect})

    answer = [("content", "Hello"), ("content", " there."), ("done", "stop")]
    ok = {"text": "Hello there.", "ended": True, "length": False, "error": None,
          "statuses": []}

    # -- the plain relay: Ollama's own bytes and Content-Type, untouched ------
    add("plain relay, Ollama's current format", "Ollama, relayed byte for byte",
        (W.stream(answer).decode("utf-8"), W.CONTENT_TYPE_STREAM), ok)
    add("plain relay, Ollama's 2025 format", "Ollama, relayed byte for byte",
        (W.stream(answer, legacy=True).decode("utf-8"), W.CONTENT_TYPE_STREAM), ok)
    add("plain relay, stream false", "Ollama, relayed byte for byte",
        (W.completion(answer).decode("utf-8"), W.CONTENT_TYPE_JSON), ok)

    # -- every local turn: jarvis_agent.run_local_turn ------------------------
    add("local turn", "jarvis_agent.run_local_turn", _agent([answer]), ok)
    add("local turn, Ollama's 2025 format", "jarvis_agent.run_local_turn",
        _agent([answer], legacy=True), ok)
    add("local turn with a tool and an approval card", "jarvis_agent.run_local_turn",
        _agent([[("tool_calls", [{"name": "calculator", "arguments": {"expression": "2+2"}}]),
                 ("done", "stop")],
                [("content", "It is "), ("content", "4."), ("done", "stop")]],
               wait=0.4, keepalive=0.1),
        {"text": "It is 4.", "ended": True, "length": False, "error": None,
         "statuses": ["approval"]})
    add("local turn, Qwen3 thinking", "jarvis_agent.run_local_turn",
        _agent([[("reasoning", "Let me think about the diary..."),
                 ("content", "<think>more thinking</think>\n\n"),
                 ("content", "Hello"), ("content", " there."), ("done", "stop")]]),
        ok)
    add("local turn cut short at the length limit", "jarvis_agent.run_local_turn",
        _agent([[("content", "The first half of a long"), ("done", "length")]]),
        {"text": "The first half of a long", "ended": True, "length": True, "error": None,
         "statuses": []})
    add("local turn, Ollama not running", "jarvis_agent.run_local_turn",
        _agent([REFUSED]),
        {"text": "", "ended": False, "length": False,
         "error": AG.plain_error(REFUSED, "jarvis-primary"), "statuses": []})
    add("local turn, model not installed", "jarvis_agent.run_local_turn",
        _agent([_http_error(404, 'model "qwen3:14b" not found, try pulling it first')],
               model="qwen3:14b"),
        {"text": "", "ended": False, "length": False,
         "error": AG.plain_error(_http_error(404, 'model "qwen3:14b" not found'), "qwen3:14b"),
         "statuses": []})
    add("local turn, stream false", "jarvis_agent.run_local_turn",
        _agent([answer], stream=False), ok)
    add("local turn, stream false, a tool and an approval card", "jarvis_agent.run_local_turn",
        _agent([[("tool_calls", [{"name": "calculator", "arguments": {"expression": "2+2"}}]),
                 ("done", "stop")],
                [("content", "It is 4."), ("done", "stop")]],
               stream=False, wait=0.4, keepalive=0.1),
        {"text": "It is 4.", "ended": True, "length": False, "error": None, "statuses": []})
    add("local turn, stream false, Ollama not running", "jarvis_agent.run_local_turn",
        _agent([REFUSED], stream=False),
        {"text": "", "ended": False, "length": False,
         "error": AG.plain_error(REFUSED, "jarvis-primary"), "statuses": []})
    return cases


def document(cases) -> str:
    return json.dumps({
        "about": "What /api/chat really sends, made by running the producer "
                 "(backend/test_chat_stream_contract.py --write). Do not edit by hand.",
        "status_prefix": AG.STATUS_PREFIX.strip(),
        "cases": cases,
    }, indent=2, ensure_ascii=False) + "\n"


def t_the_producer_does_what_each_case_says():
    """Before anything is written, read each body back the simplest way - so
    a wrong expectation fails HERE, not only in three apps' tests."""
    for c in build_cases():
        body, exp = c["body"], c["expect"]
        if c["content_type"] == "application/json":
            obj = json.loads(body)
            text = obj.get("choices", [{}])[0].get("message", {}).get("content", "") \
                if "choices" in obj else ""
            err = obj.get("error")
            ended = "choices" in obj
        else:
            text, err, ended = "", None, False
            for line in body.split("\n"):
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    ended = True
                    continue
                o = json.loads(data)
                if o.get("error"):
                    err = o["error"]["message"]
                    continue
                ch = o["choices"][0]
                text += (ch.get("delta") or {}).get("content") or ""
        check(f"{c['name']}: the words", text == exp["text"], repr(text))
        check(f"{c['name']}: the error", err == exp["error"], repr(err))
        check(f"{c['name']}: finished", ended == exp["ended"], repr(ended))


def t_both_copies_are_what_the_producer_makes_today():
    doc = document(build_cases())
    write = "--write" in sys.argv
    for path in COPIES:
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(doc, encoding="utf-8", newline="\n")
        have = path.read_text(encoding="utf-8") if path.exists() else ""
        rel = path.relative_to(REPO)
        check(f"{rel} matches the producer (run with --write after changing jarvis_agent)",
              have == doc, "stale or missing")


if __name__ == "__main__":
    for fn in (t_the_producer_does_what_each_case_says,
               t_both_copies_are_what_the_producer_makes_today):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
