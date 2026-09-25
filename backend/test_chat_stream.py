"""chat-stream.patch and jarvis_agent's streaming turn: what the apps receive.

The findings this answers (docs/ audit, 2026-09-23):

  1. A tool turn was sent as `Content-Type: application/json` with an SSE body,
     so the HUD page - which picks its reader from that header - failed with
     "Unexpected token 'd'". And `stream: false` was ignored.
  2. With any tool listed in the config, EVERY local turn was generated twice:
     once whole and unseen, then again as a stream. Silence, then a different
     answer.
  3. Nothing was written while an approval card waited (up to three minutes),
     so the phone gave up after two minutes of silence; and the server never
     noticed the app had gone, so an approved tool still ran for nobody.
  5. Qwen3's thinking was never switched off, and a cut-off answer ("length")
     looked like a finished one.
  8. The history was sized for 16,384 tokens whatever the loaded model has.
  9. Error messages were Python exceptions and instructions for programs this
     setup does not have.

The model's side of every turn here is Ollama's real /v1/chat/completions
stream (_ollama_wire.py, transcribed from Ollama's source), in both the current
and the 2025 format. Nothing here opens a socket.

    python3 test_chat_stream.py
"""
import ast
import json
import sys
import threading
import time
import traceback
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, explain, require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
import jarvis_agent as AG  # noqa: E402
import _ollama_wire as W  # noqa: E402
import _skeleton  # noqa: E402

AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Gate:
    """A gate that answers after `wait` seconds, and remembers what it saw."""

    def __init__(self, allowed=True, wait=0.0):
        self.allowed, self.wait, self.asked = allowed, wait, []

    def __call__(self, action, detail, prompt):
        self.asked.append(action)
        time.sleep(self.wait)
        allowed = self.allowed

        class V:
            reason = "approved" if allowed else "denied by a human"
            outcome = "approved" if allowed else "denied"
        V.allowed = allowed
        return V()


def opener_for(*bodies, legacy=False, calls=None):
    """Each request gets the next body: a list of events (streamed the way
    Ollama streams them) or an exception to raise."""
    it = iter(bodies)
    calls = calls if calls is not None else []

    def opener(url, payload):
        calls.append(payload)
        b = next(it)
        if isinstance(b, BaseException):
            raise b
        return W.FakeResponse(W.stream(b, legacy=legacy))
    return opener, calls


def turn(opener, **kw):
    out = []
    kw.setdefault("context_length", 16384)
    kw.setdefault("gate_check", Gate())
    kw.setdefault("keepalive_seconds", 1000)
    summary = AG.run_local_turn([{"role": "user", "content": "hi"}], "jarvis-primary",
                                ollama_url="http://127.0.0.1:11434", stream_out=out.append,
                                open_stream=opener, **kw)
    return b"".join(out), summary


def sse_objects(body: bytes):
    objs = []
    for line in body.split(b"\n"):
        line = line.strip()
        if line.startswith(b"data:") and line[5:].strip() != b"[DONE]":
            objs.append(json.loads(line[5:]))
    return objs


def text_of(body: bytes) -> str:
    return "".join((o.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
                   for o in sse_objects(body))


def calc_call(expr="2+2"):
    return ("tool_calls", [{"name": "calculator", "arguments": {"expression": expr}}])


# --------------------------------------------------------------------------
#   1. Content-Type and stream:false
# --------------------------------------------------------------------------

def t_content_type_matches_the_body():
    check("a streamed reply is text/event-stream", AG.content_type(True) == "text/event-stream")
    check("a stream:false reply is application/json", AG.content_type(False) == "application/json")
    hud = (REPO / "jarvis-desktop" / "src" / "jarvis_hud.html").read_text(encoding="utf-8")
    check("the HUD page really picks its SSE reader on exactly that header value",
          'ctype.includes("text/event-stream")' in hud)


def t_stream_false_is_one_json_body():
    opener, calls = opener_for([("content", "Four"), ("content", "."), ("done", "stop")])
    body, _ = turn(opener, stream=False)
    obj = json.loads(body.decode("utf-8"))
    check("stream:false gets ONE JSON body, Ollama's chat.completion shape",
          obj.get("object") == "chat.completion", body[:200])
    check("its answer is the model's words",
          obj["choices"][0]["message"]["content"] == "Four.", repr(obj))
    check("and it says how it ended", obj["choices"][0]["finish_reason"] == "stop")
    check("no SSE line anywhere in it", b"data:" not in body)


def t_stream_false_keepalives_are_blank_lines_json_still_parses():
    opener, _ = opener_for([calc_call(), ("done", "stop")],
                           [("content", "It is 4."), ("done", "stop")])
    body, _ = turn(opener, stream=False, gate_check=Gate(wait=0.3), keepalive_seconds=0.05)
    check("keepalives were sent while the gate waited", body.startswith(b"\n"), repr(body[:20]))
    check("and the body is still one valid JSON document",
          json.loads(body.decode("utf-8"))["choices"][0]["message"]["content"] == "It is 4.")


# --------------------------------------------------------------------------
#   2. One request per answer, not two
# --------------------------------------------------------------------------

def t_a_plain_turn_is_one_streamed_request():
    for legacy in (False, True):
        opener, calls = opener_for([("content", "Hel"), ("content", "lo."), ("done", "stop")],
                                   legacy=legacy)
        body, s = turn(opener, enabled_tools={"calculator"})
        fmt = "2025 format" if legacy else "current format"
        check(f"{fmt}: one request, not two", len(calls) == 1, repr(len(calls)))
        check(f"{fmt}: the words arrive as the model writes them", text_of(body) == "Hello.",
              repr(body))
        check(f"{fmt}: exactly one finish and one [DONE], at the end",
              body.count(b"[DONE]") == 1 and body.rstrip().endswith(b"data: [DONE]")
              and sum(1 for o in sse_objects(body)
                      if o["choices"][0].get("finish_reason")) == 1, repr(body))


def t_a_tool_round_never_reaches_the_app():
    opener, calls = opener_for([calc_call(), ("done", "stop")],
                               [("content", "It is 4."), ("done", "stop")])
    body, s = turn(opener, enabled_tools={"calculator"})
    check("two requests: the tool round, then the answer", len(calls) == 2)
    check("the tool call itself is never sent to the app", b"tool_calls" not in body, repr(body))
    check("the round's own finish_reason tool_calls is not relayed (apps stop on any finish)",
          b'"tool_calls"' not in body and body.count(b"finish_reason\":\"stop") == 1, repr(body))
    check("only one [DONE], after the answer", body.count(b"[DONE]") == 1)
    check("the answer is the second round's words", text_of(body) == "It is 4.")
    check("the tool result went back to the model",
          any(m.get("role") == "tool" for m in calls[1]["messages"]))


def t_words_before_a_tool_call_are_kept_and_the_answer_follows_on():
    opener, calls = opener_for([("content", "Let me check."), calc_call(), ("done", "stop")],
                               [("content", "It is 4."), ("done", "stop")])
    body, _ = turn(opener, enabled_tools={"calculator"})
    asked = [m for m in calls[1]["messages"] if m.get("role") == "assistant"]
    check("the model is shown the words it wrote before asking for the tool",
          asked and asked[-1]["content"] == "Let me check." and asked[-1].get("tool_calls"),
          repr(asked))
    check("the app gets both, with a paragraph break between",
          text_of(body) == "Let me check.\n\nIt is 4.", repr(text_of(body)))


class _DiesHalfWay(W.FakeResponse):
    def read1(self, n=1024):
        if not self._body:
            raise ConnectionResetError(104, "Connection reset by peer")
        return super().read1(n)
    read = read1


def t_ollama_dying_mid_answer_is_said_plainly():
    whole = W.stream([("content", "The first"), ("content", " part"), ("done", "stop")])
    cut = whole[:whole.index(b'"finish_reason":"stop"') - 120]

    def opener(url, payload):
        return _DiesHalfWay(cut)
    out = []
    AG.run_local_turn([{"role": "user", "content": "x"}], "m", ollama_url="http://127.0.0.1:11434",
                      stream_out=out.append, open_stream=opener, context_length=4096,
                      keepalive_seconds=1000)
    objs = sse_objects(b"".join(out))
    msg = (objs[-1].get("error") or {}).get("message", "") if objs else ""
    check("the words so far arrive, then a plain sentence, not a Python error",
          "stopped in the middle" in msg and "ConnectionReset" not in msg, repr(objs))


def t_only_real_tools_are_offered():
    check("names the agent does not have are not offered",
          AG.offered_tools({"image_gen", "ha_mcp", "calculator"}) == ["calculator"])
    opener, calls = opener_for([("content", "ok"), ("done", "stop")])
    turn(opener, enabled_tools={"image_gen", "something_else"})
    check("a config listing only unknown tools sends no `tools` at all",
          "tools" not in calls[0], repr(calls[0].keys()))


# --------------------------------------------------------------------------
#   3. Waiting for an approval, and an app that went away
# --------------------------------------------------------------------------

def t_the_app_hears_from_the_pc_while_a_card_waits():
    opener, _ = opener_for([calc_call(), ("done", "stop")],
                           [("content", "It is 4."), ("done", "stop")])
    body, _ = turn(opener, enabled_tools={"calculator"}, gate_check=Gate(wait=0.4),
                   keepalive_seconds=0.1, status_delay=0.05)
    check("the app is told a card is waiting", b": jarvis-status approval\n\n" in body, repr(body))
    check("and keeps getting keepalives while it waits", body.count(b": keepalive\n\n") >= 2,
          repr(body))
    check("both are SSE comments, which every SSE reader skips",
          all(l.startswith(b":") for l in body.split(b"\n")
              if l and not l.startswith(b"data:")), repr(body))
    check("the answer still arrives whole", text_of(body) == "It is 4.")


def t_a_gate_that_answers_at_once_never_says_waiting():
    opener, _ = opener_for([calc_call(), ("done", "stop")],
                           [("content", "4"), ("done", "stop")])
    body, _ = turn(opener, enabled_tools={"calculator"}, status_delay=0.5)
    check("no 'approval' status for a tool the gate let straight through",
          b"jarvis-status approval" not in body, repr(body))


def t_an_approved_tool_does_not_run_for_an_app_that_left():
    ran = []
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: ran.append(1) or {"ok": True}
    announced = []
    try:
        opener, calls = opener_for([calc_call(), ("done", "stop")],
                                   [("content", "It is 4."), ("done", "stop")])
        wrote = []

        def closed_app(data):
            # The phone gave up: every write after the first fails, the way
            # a socket with nobody reading it does.
            if wrote:
                raise BrokenPipeError(32, "Broken pipe")
            wrote.append(data)
        s = AG.run_local_turn([{"role": "user", "content": "2+2?"}], "jarvis-primary",
                              ollama_url="http://127.0.0.1:11434", stream_out=closed_app,
                              open_stream=opener, enabled_tools={"calculator"},
                              gate_check=Gate(wait=0.4), keepalive_seconds=0.05,
                              status_delay=0.02, context_length=16384,
                              announce=announced.append, record_chain=lambda s: None)
    finally:
        AG.TOOLS["calculator"].execute = real
    check("the server noticed the app was gone", s["client_gone"] is True, repr(s))
    check("the approved tool did NOT run for nobody", ran == [], repr(ran))
    check("and no further request went to the model", len(calls) == 1, repr(len(calls)))
    check("the owner is told why, on the doorbell", any("closed" in a for a in announced),
          repr(announced))


def t_an_app_leaving_mid_answer_stops_ollama():
    aborted = []
    opener, _ = opener_for([("content", "one "), ("content", "two "), ("content", "three"),
                            ("done", "stop")])

    def gone(data):
        raise ConnectionResetError(104, "reset")
    s = AG.run_local_turn([{"role": "user", "content": "count"}], "jarvis-primary",
                          ollama_url="http://127.0.0.1:11434", stream_out=gone, open_stream=opener,
                          context_length=16384, abort=aborted.append,
                          keepalive_seconds=1000)
    check("the request to Ollama is aborted, so the GPU stops", len(aborted) == 1, repr(aborted))
    check("and the turn reports the app gone", s["client_gone"] is True)


# --------------------------------------------------------------------------
#   5. Thinking off, and an answer cut short says so
# --------------------------------------------------------------------------

def t_thinking_is_switched_off_and_never_shown():
    opener, calls = opener_for([("reasoning", "The user's bank PIN is 1234, so"),
                                ("content", "<thi"), ("content", "nk>still thinking</th"),
                                ("content", "ink>\n\nHello"), ("content", " <b> there"),
                                ("done", "stop")])
    body, _ = turn(opener)
    check("the request switches thinking off the supported way",
          calls[0].get("reasoning_effort") == "none", repr(calls[0]))
    check("the reasoning field is never relayed", b"reasoning" not in body and b"PIN" not in body,
          repr(body))
    check("a <think> block inside the text is cut out, even split across chunks",
          text_of(body) == "Hello <b> there", repr(text_of(body)))
    check("strip_thinking does the same on whole text",
          AG.strip_thinking("<think>x</think>\n\nAnswer") == "Answer"
          and AG.strip_thinking("a < b") == "a < b")


def t_an_old_ollama_that_refuses_none_is_asked_again_without_it():
    AG._reasoning_field_refused = False
    refusal = urllib.error.HTTPError(
        "http://ollama/v1/chat/completions", 400, "Bad Request", {},
        None)
    body400 = W.error_body(400, "invalid reasoning value: 'none'")
    refusal.read = lambda *a: body400
    opener, calls = opener_for(refusal, [("content", "ok"), ("done", "stop")])
    body, _ = turn(opener)
    check("asked twice, the second time without reasoning_effort",
          len(calls) == 2 and "reasoning_effort" not in calls[1], repr(calls))
    check("and the answer came through", text_of(body) == "ok")
    AG._reasoning_field_refused = False


def t_a_cut_off_answer_says_length():
    opener, _ = opener_for([("content", "The first half"), ("done", "length")])
    body, s = turn(opener)
    check("finish_reason length reaches the app, so it can say the answer was cut short",
          b'"finish_reason":"length"' in body and s["finish_reason"] == "length", repr(body))


def t_every_window_gets_the_same_answer_length():
    opener, calls = opener_for([("content", "ok"), ("done", "stop")])
    turn(opener, request={"temperature": 0.7})
    check("no max_tokens from the app -> the Modelfile's 1,024",
          calls[0]["max_tokens"] == 1024 and calls[0]["temperature"] == 0.7, repr(calls[0]))
    opener, calls = opener_for([("content", "ok"), ("done", "stop")])
    turn(opener, request={"max_tokens": 300})
    check("an app's own max_tokens is kept", calls[0]["max_tokens"] == 300)


# --------------------------------------------------------------------------
#   8. The history fits the model it is going to
# --------------------------------------------------------------------------

def t_history_is_trimmed_to_the_real_context():
    old = [{"role": "user", "content": "q" * 3000}, {"role": "assistant", "content": "a" * 3000}]
    msgs = old * 4 + [{"role": "system", "content": "Recalled: the owner likes tea."},
                      {"role": "user", "content": "and now?"}]
    fitted = AG.fit_messages(msgs, budget=2000)
    check("the recalled-facts system message is kept",
          any(m["role"] == "system" for m in fitted))
    check("the new question is kept, last", fitted[-1]["content"] == "and now?")
    check("it fits", AG.estimate_tokens(fitted) <= 2000, AG.estimate_tokens(fitted))
    check("a question and its answer go together (no answer left without its question)",
          fitted[0]["role"] in ("user", "system"), repr([m["role"] for m in fitted]))
    check("a conversation that already fits is untouched",
          AG.fit_messages(msgs[-2:], budget=2000) == msgs[-2:])

    opener, calls = opener_for([("content", "ok"), ("done", "stop")])
    out = []
    AG.run_local_turn(msgs, "qwen3:8b", ollama_url="http://127.0.0.1:11434", stream_out=out.append,
                      open_stream=opener, context_length=4096, keepalive_seconds=1000)
    check("a 4,096-token model gets a trimmed conversation, with room for the answer",
          AG.estimate_tokens(calls[0]["messages"]) <= 4096 - 1024, AG.estimate_tokens(calls[0]["messages"]))


def t_the_context_length_comes_from_ollama():
    real = AG._get_json
    AG._CTX_CACHE.clear()
    try:
        AG._get_json = lambda url, payload=None, timeout=4.0: (
            {"models": [{"name": "jarvis-primary:latest", "model": "jarvis-primary:latest",
                         "context_length": 16384}]} if url.endswith("/api/ps") else {})
        check("/api/ps's context_length for the loaded model is used",
              AG._context_length("http://o", "jarvis-primary") == 16384)
        AG._CTX_CACHE.clear()
        AG._get_json = lambda url, payload=None, timeout=4.0: (
            {"models": []} if url.endswith("/api/ps")
            else {"parameters": "num_batch                      512\nnum_ctx                        8192"})
        check("not loaded yet: the Modelfile's num_ctx from /api/show",
              AG._context_length("http://o", "jarvis-primary") == 8192)
        AG._CTX_CACHE.clear()

        def down(*a, **k):
            raise OSError("refused")
        AG._get_json = down
        check("Ollama cannot say: the smallest it could be, 4,096",
              AG._context_length("http://o", "x") == 4096)
    finally:
        AG._get_json = real
        AG._CTX_CACHE.clear()


# --------------------------------------------------------------------------
#   9. Plain words when something is wrong
# --------------------------------------------------------------------------

def t_errors_are_plain_sentences_in_the_same_framing():
    refused = urllib.error.URLError(ConnectionRefusedError(10061, "No connection could be made"))
    opener, _ = opener_for(refused)
    body, s = turn(opener)
    objs = sse_objects(body)
    msg = objs[-1]["error"]["message"] if objs and "error" in objs[-1] else ""
    check("Ollama down -> an SSE error line the apps already read", bool(msg), repr(body))
    check("which says what to do, in plain words",
          "not running" in msg and "Open Ollama" in msg and "WinError" not in msg
          and "urlopen" not in msg, msg)

    missing_model = urllib.error.HTTPError("http://ollama", 404, "Not Found", {}, None)
    b404 = W.error_body(404, 'model "qwen3:14b" not found, try pulling it first')
    missing_model.read = lambda *a: b404
    opener, _ = opener_for(missing_model)
    out = []
    AG.run_local_turn([{"role": "user", "content": "x"}], "qwen3:14b", ollama_url="http://127.0.0.1:11434",
                      stream_out=out.append, open_stream=opener, context_length=4096,
                      keepalive_seconds=1000)
    msg = sse_objects(b"".join(out))[-1]["error"]["message"]
    check("a model that is not installed is named, with how to get it",
          "qwen3:14b" in msg and "not installed" in msg and "Models" in msg, msg)

    opener, _ = opener_for(refused)
    body, _ = turn(opener, stream=False)
    check("stream:false gets the same sentence as {\"error\": ...}",
          "not running" in json.loads(body.decode("utf-8"))["error"])


# --------------------------------------------------------------------------
#   The patch itself
# --------------------------------------------------------------------------

EARLIER = ("gpu-offload.patch", "ollama-direct.patch", "tool-calling-wiring.patch")


def t_the_patch_applies_after_speed_record():
    ok, out = _skeleton.rehearse("chat-stream.patch", *EARLIER, on_top=("speed-record.patch",))
    if ok is None:
        return check("SKIP - " + out, True)
    check("chat-stream.patch applies to what tool-calling-wiring, ollama-direct and "
          "speed-record wrote", ok is True, out)
    if not ok:
        return
    check("the agent branch sends the Content-Type the agent's body has",
          'self.send_header("Content-Type", jarvis_agent.content_type(_streaming))' in out)
    check("stream comes from what the app asked",
          '_streaming = bool((payload or {}).get("stream"))' in out)
    check("run_local_turn is told stream, the request and how to abort",
          "stream=_streaming, request=payload, abort=_abort," in out)
    check("both branches say where the answer was made",
          out.count('route_header["where"]') == 2)
    check("the fixed-JSON Content-Type is gone from the agent branch",
          'self.send_header("Content-Type", "application/json")' not in out)
    check("no message tells the owner to run a program this setup never installs",
          'f"Start it with `uv run jarvis serve`' not in out)
    check("a turn that did not finish is not recorded as a speed sample",
          'and not _turn.get("client_gone")' in out)
    check("the old unconditional tools=True is gone", "_speed.finish(lane, tools=True)" not in out)


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    if "jarvis_agent.content_type" not in src:
        return check("chat-stream.patch is applied to jarvis_hud.py", False,
                     "run scripts/apply-patches.ps1 first")
    tree = ast.parse(src)
    do_post = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "do_POST"]
    body = ast.unparse(do_post[0]) if do_post else ""
    check("do_POST sends jarvis_agent.content_type(...)", "jarvis_agent.content_type(" in body)
    check("the agent is used for every local turn",
          "use_tools = lane == local_model and _agent_ok" in body.replace("\n", " "))


if __name__ == "__main__":
    for fn in (t_content_type_matches_the_body, t_stream_false_is_one_json_body,
               t_stream_false_keepalives_are_blank_lines_json_still_parses,
               t_a_plain_turn_is_one_streamed_request, t_a_tool_round_never_reaches_the_app,
               t_words_before_a_tool_call_are_kept_and_the_answer_follows_on,
               t_ollama_dying_mid_answer_is_said_plainly,
               t_only_real_tools_are_offered,
               t_the_app_hears_from_the_pc_while_a_card_waits,
               t_a_gate_that_answers_at_once_never_says_waiting,
               t_an_approved_tool_does_not_run_for_an_app_that_left,
               t_an_app_leaving_mid_answer_stops_ollama,
               t_thinking_is_switched_off_and_never_shown,
               t_an_old_ollama_that_refuses_none_is_asked_again_without_it,
               t_a_cut_off_answer_says_length, t_every_window_gets_the_same_answer_length,
               t_history_is_trimmed_to_the_real_context, t_the_context_length_comes_from_ollama,
               t_errors_are_plain_sentences_in_the_same_framing,
               t_the_patch_applies_after_speed_record, t_the_real_file):
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
