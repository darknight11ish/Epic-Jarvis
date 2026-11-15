"""test_chat_window.py - the window the preset names is the window the turn gets.

    py -3 backend/test_chat_window.py

WHAT THIS PINS. Measured on the live install, 2026-11-15 ~08:30 PT, backend
0.2.456, the Coding preset applied, qwen3-coder-30b-a3b-ud-q3-k-xl:latest on
127.0.0.1:11450:

  * GET /api/ps BEFORE the turn: `context_length` 49,152.
  * ONE turn through the app, even the single word "hi": HTTP 400, "request
    (9794 tokens) exceeds the available context size (8192 tokens)". A real
    question measured 9,835 tokens. Zero tool calls, no answer.
  * GET /api/ps AFTER that turn: `context_length` 8,192 - the turn itself
    re-created the runner at Ollama's own small default.

It is not a long question. The 28-tool stack the app offers is 9,110 tokens by
itself (`estimate_tokens`, the same estimator the prompt trimmer uses), so the
stack alone is bigger than the 8,192 the lane came back at.

THE WIRE THAT CAUSED IT. `chat_body()` named the window in a top-level `options`
field on `/v1/chat/completions` (Q5, 2026-11-08). Ollama's OpenAI-compatible
endpoint does not use that field when it chooses a runner: the measured 49,152
runner was unloaded and replaced with an 8,192 one by the very request that
named 49,152, and the prompt it then could not fit was refused.
`pooled_preload()`'s own docstring records the same thing from 2026-11-09 - a
COLD `/v1` turn loaded at 8,192 though the body named 49,152.

THE FIX THIS PINS. On the ONE lane its preset gives a window to - and only that
one - the turn is sent to Ollama's NATIVE `/api/chat`, which honours
`options.num_ctx` when it loads or reuses a runner (the same field
`/api/generate` honours, measured at 49,152 tokens and zero spill on this PC).
Every other lane still sends its `/v1` request, byte for byte. Nothing in this
suite opens a socket: the lane, the stream and every lookup are fakes.

WHY IT CANNOT BE SILENT ANY MORE. Ollama drops the FRONT of a prompt that does
not fit and answers anyway (see "When the model was not given the whole
conversation" in jarvis_agent.py). Three things now say so instead:

  * a turn whose own prompt is over the window it is about to name is told so,
    in the app's words, before the request (WINDOW_OVERFLOW_LINE);
  * a lane that cannot say which window it is set to is TOLD so
    (POOLED_WINDOW_UNKNOWN_LINE) instead of guessed at; and
  * the existing after-the-fact guard still works - DROPPED_PROMPT_NOTE - which
    is why the native wire's `prompt_eval_count` is carried into the same
    `usage.prompt_tokens` the `/v1` wire filled.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="chat-window-"))
CONFIG = _TMP / "config"
CONFIG.mkdir(parents=True, exist_ok=True)
# The Coding preset the owner had applied on the measured PC. Its own `mode` is
# "", so the applied-preset read falls through to what the lane holds; the line
# below makes that fall-through answer "coding" WITHOUT /api/ps (see Fakes).
(CONFIG / "presets-choice.json").write_text(json.dumps({"preset": "coding"}),
                                           encoding="utf-8")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["OLLAMA_URL"] = "http://127.0.0.1:11436"

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_agent.py")
require_shipped("jarvis_presets.py")

import _ollama_wire as W  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_model_lanes as LANES  # noqa: E402
import jarvis_presets as P  # noqa: E402

POOLED = "http://127.0.0.1:11450"
EVERYDAY = "http://127.0.0.1:11436"
MODEL = "qwen3-coder-30b-a3b-ud-q3-k-xl"
EVERYDAY_MODEL = "qwen3.5:9b"        # what may run on the one-card lane
WINDOW = 49152                       # the Coding preset's measured window
SMALL = 8192                         # what the failed turn left the lane at
NOW = "2026-11-15T08:30:00.000000-08:00"

#: The 28 tools the live install offered on the measured turn (real names from
#: jarvis_agent.TOOLS, the first 28 a Coding preset reaches). Their schemas are
#: what makes the prompt stack bigger than 8,192 tokens on their own.
STACK = ("calculator", "memory_search", "file_read", "web_search",
         "read_web_page", "control_computer", "control_phone", "phone_apps",
         "plugin_list", "plugin_switch", "pack_list", "pack_inspect",
         "pack_install", "pack_remove", "shell_exec", "github_search",
         "github_list", "github_read_file", "github_ci_status", "github_comment",
         "github_open_issue", "github_rerun_workflow", "github_create_repo",
         "github_pr_scan", "github_merge_pr", "github_fix_and_push",
         "review_changes", "check_records")

PASSED, FAILED = [], []

#: The coding preset resolves its window through the lane module's own default
#: only after an /api/ps read (its `mode` is ""). That read would be a socket,
#: so it is faked to the answer the live lane gives - "coding" - and the check
#: below pins that this is the window the preset names.
LANES.pooled_mode_now = lambda **k: "coding"


def check(name: str, ok, detail=None) -> None:
    (PASSED if ok else FAILED).append(name)
    print(f"ok    {name}" if ok else
          f"FAIL  {name}" + (f" | {detail!r}" if detail is not None else ""))


# ---------------------------------------------------------------------------
#   Fakes: no socket anywhere
# ---------------------------------------------------------------------------

class NoNet:
    """The real HTTP helpers refuse to run; the two lookups answer from fakes.

    `/api/ps` reports the model at `ps_ctx` (None: nothing loaded), which is
    what the lane's own preload and the prompt trimmer read. `/api/show` is
    never answered, exactly as a model with no Modelfile num_ctx."""

    def __init__(self, *, ps_ctx=None):
        self.ps_ctx = ps_ctx

    def __enter__(self):
        self.real = (AG._post, AG._open_stream, AG._get_json)

        def boom(*_a, **_k):
            raise AssertionError("a real HTTP request ran")

        def get(url, payload=None, timeout=4.0):
            if str(url).endswith("/api/ps"):
                models = [] if not self.ps_ctx else [
                    {"name": MODEL + ":latest", "model": MODEL + ":latest",
                     "context_length": int(self.ps_ctx)}]
                return {"models": models}
            if str(url).endswith("/api/generate"):
                return {"done": True}
            raise OSError("no network in this test")

        AG._post, AG._open_stream, AG._get_json = boom, boom, get
        return self

    def __exit__(self, *_a):
        AG._post, AG._open_stream, AG._get_json = self.real
        return False


class FakeStream:
    """A context manager standing in for urllib's response object."""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self, n=1024):
        out, self._body = self._body[:n], self._body[n:]
        return out

    def read1(self, n=1024):
        return self.read(n)

    def close(self):
        pass


def native_stream(*, text: str = "ok", prompt_tokens=None, done_reason: str = "stop") -> bytes:
    """Ollama's NATIVE /api/chat stream, one JSON object per line.

    The shapes are Ollama's own: a content object with `done: false`, then one
    final object with `done: true`, `done_reason`, and the usage counts
    (`prompt_eval_count` = what the model REALLY read)."""
    lines = []
    if text:
        lines.append({"model": MODEL, "created_at": NOW,
                      "message": {"role": "assistant", "content": text},
                      "done": False})
    final = {"model": MODEL, "created_at": NOW,
             "message": {"role": "assistant", "content": ""},
             "done": True, "done_reason": done_reason}
    if prompt_tokens is not None:
        final["prompt_eval_count"] = int(prompt_tokens)
        final["eval_count"] = 3
    lines.append(final)
    return b"".join((json.dumps(obj) + "\n").encode("utf-8") for obj in lines)


def answer_text(streamed) -> str:
    """The words an app would show, read out of what the turn wrote."""
    text = []
    for line in b"".join(streamed).split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:") or line[5:].strip() == b"[DONE]":
            continue
        obj = json.loads(line[5:])
        delta = (obj.get("choices") or [{}])[0].get("delta") or {}
        text.append(delta.get("content") or "")
    return "".join(text)


def a_turn(*, url: str = POOLED, tools=STACK, prompt_tokens=None, messages=None,
           announce=None, context_length=None, model: str = MODEL):
    """One REAL `run_local_turn`, every request faked. (out, [(url, payload)], what the app got)."""
    calls: list = []
    streamed: list = []
    msgs = list(messages or [{"role": "user", "content": "hi"}])

    def opener(u, payload):
        calls.append((u, payload))
        if "/v1/" in u:
            return FakeStream(W.stream([("content", "ok"), ("done", "stop")],
                                       model=str((payload or {}).get("model") or model)))
        return FakeStream(native_stream(prompt_tokens=prompt_tokens))

    AG._CTX_CACHE.clear()
    AG._TOOLS_CACHE.clear()
    AG._reasoning_field_refused = False
    with NoNet(ps_ctx=WINDOW):
        out = AG.run_local_turn(
            msgs, model, ollama_url=url, stream_out=streamed.append,
            enabled_tools=set(tools), announce=announce, open_stream=opener,
            lane_choice=None, record_chain=lambda s: None,
            on_step=lambda s: None, context_length=context_length,
            request={"conversation_id": "conv-window", "stream": True,
                     "messages": msgs})
    return out, calls, streamed


# ---------------------------------------------------------------------------
#   W0/W1 - the measured defect, and the window the preset names
# ---------------------------------------------------------------------------

def the_window_the_preset_names_is_the_window_the_turn_gets() -> None:
    stack = AG._schemas_for(list(STACK), [], {})
    check("W0: the 28-tool stack alone is bigger than the 8,192 the lane came back at",
          AG.estimate_tokens(stack) > SMALL, AG.estimate_tokens(stack))
    check("W0: the preset's lane names 49,152 - read from the lane config, not typed here",
          P.lane_num_ctx(POOLED) == WINDOW, P.lane_num_ctx(POOLED))

    out, calls, streamed = a_turn()
    urls = [u for u, _ in calls]
    payload = calls[0][1] if calls else {}
    check("W1: the pooled turn goes to Ollama's NATIVE /api/chat",
          urls[:1] == [POOLED + "/api/chat"], urls)
    check("W1: ... naming options.num_ctx = 49,152, the window the preset names",
          (payload.get("options") or {}).get("num_ctx") == WINDOW,
          payload.get("options"))
    check("W1: ... with the full 28-tool stack, whose schemas alone are bigger "
          "than the 8,192 the lane came back at",
          len(payload.get("tools") or []) >= len(STACK)
          and AG.estimate_tokens(payload.get("tools") or []) > SMALL,
          (len(payload.get("tools") or []),
           AG.estimate_tokens(payload.get("tools") or [])))
    check("W1: ... still streaming, as the apps read it",
          payload.get("stream") is True, payload.get("stream"))
    check("W1: ... and the answer arrives",
          out.get("answer") == "ok" and out.get("finish_reason") == "stop", out)
    check("W1: the words the app got are the model's own",
          answer_text(streamed) == "ok", repr(b"".join(streamed)[-300:]))
    check("W1: no /v1 request was sent on this lane at all",
          not any("/v1/" in u for u in urls), urls)


# ---------------------------------------------------------------------------
#   W2 - a lane whose window genuinely is small keeps that window, and says
#        when the prompt does not fit it
# ---------------------------------------------------------------------------

def a_prompt_over_the_named_window_is_said_before_it_is_sent() -> None:
    noted: list = []
    real = P.lane_num_ctx
    # A pooled preset whose own window really is 8,192. The number the request
    # must name is the PRESET's, so this is the case that proves a small lane is
    # not made big by this change.
    P.lane_num_ctx = lambda url: SMALL
    try:
        out, calls, _ = a_turn(announce=noted.append, context_length=SMALL)
    finally:
        P.lane_num_ctx = real
    payload = calls[0][1] if calls else {}
    check("W2: a lane whose window really is 8,192 names 8,192",
          (payload.get("options") or {}).get("num_ctx") == SMALL,
          payload.get("options"))
    said = [str(line) for line in noted]
    check("W2: ... and the app says the prompt does not fit that window",
          any("does not fit" in line for line in said), said)
    check("W2: ... and the answer still comes", out.get("answer") == "ok", out)


# ---------------------------------------------------------------------------
#   W3 - a truncated prompt is never silent (before OR after the answer)
# ---------------------------------------------------------------------------

def a_truncated_prompt_is_never_silent() -> None:
    # 60,000 characters: ~20,000 tokens by the trimmer's own estimator, so the
    # 8,194 the fake lane reports reading can only be a prompt cut to fit.
    long = {"role": "user", "content": "word " * 12000}
    noted: list = []
    out, _calls, _streamed = a_turn(messages=[long], prompt_tokens=8194,
                                    announce=noted.append,
                                    context_length=WINDOW)
    check("W3: the native wire's prompt_eval_count reaches the turn's own record",
          out.get("prompt_tokens") == 8194, out.get("prompt_tokens"))
    said = [str(line) for line in noted]
    check("W3: ... and a prompt the model was not given whole is said, not silent",
          any("not given the whole conversation" in line for line in said), said)


# ---------------------------------------------------------------------------
#   W4 - a window nobody can name is SAID, not guessed
# ---------------------------------------------------------------------------

def a_window_nobody_can_name_is_said_not_guessed() -> None:
    real = P.lane_num_ctx
    P.lane_num_ctx = lambda url: None          # the config cannot say
    noted: list = []
    try:
        out, calls, _ = a_turn(announce=noted.append)
    finally:
        P.lane_num_ctx = real
    said = [str(line) for line in noted]
    check("W4: with no window to name, today's /v1 request is still sent",
          bool(calls) and "/v1/" in calls[0][0], [c[0] for c in calls])
    check("W4: ... and the app says the window could not be established",
          any("could not be read" in line or "could not" in line and "window" in line
              for line in said), said)
    check("W4: ... and the answer still comes", out.get("answer") == "ok", out)


# ---------------------------------------------------------------------------
#   W5 - every other lane is untouched
# ---------------------------------------------------------------------------

def every_other_lane_keeps_its_request() -> None:
    out, calls, streamed = a_turn(url=EVERYDAY, model=EVERYDAY_MODEL)
    check("W5: an everyday-lane turn still goes to /v1/chat/completions",
          bool(calls) and calls[0][0] == EVERYDAY + "/v1/chat/completions",
          [c[0] for c in calls])
    check("W5: ... with no options field, exactly as before",
          bool(calls) and "options" not in calls[0][1],
          sorted(calls[0][1]) if calls else None)
    check("W5: ... and it still answers", out.get("answer") == "ok"
          and answer_text(streamed) == "ok", out)


def main() -> int:
    print("-- W0/W1: the window the preset names --")
    the_window_the_preset_names_is_the_window_the_turn_gets()
    print("\n-- W2: a genuinely small window --")
    a_prompt_over_the_named_window_is_said_before_it_is_sent()
    print("\n-- W3: a truncated prompt is never silent --")
    a_truncated_prompt_is_never_silent()
    print("\n-- W4: a window nobody can name --")
    a_window_nobody_can_name_is_said_not_guessed()
    print("\n-- W5: every other lane --")
    every_other_lane_keeps_its_request()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
