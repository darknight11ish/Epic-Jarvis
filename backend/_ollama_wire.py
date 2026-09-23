"""What Ollama's `/v1/chat/completions` actually sends, byte for byte.

WHY THIS EXISTS

The chat tests used to feed the apps invented bodies - `{"done":true}`, or a
bare "Hello there." as text/plain - that no Ollama has ever sent. A reader
that passes against an invented body proves nothing about the real one. This
builds the real one, from Ollama's own source, so the tests can put exactly
that through jarvis_agent's relay and then through each app's reader.

It is a TRANSCRIPTION of Go code, not a guess, and each shape names where it
was read (github.com/ollama/ollama, fetched 2026-09-23):

CURRENT - `main` (openai/openai.go ToStreamChunks/toChunk/FinishChunk,
middleware/openai.go ChatWriter.writeResponse):
  - every chunk is `data: <json>\\n\\n`, the JSON compact (Go's json.Marshal:
    no spaces, and `<` `>` `&` escaped as \\u003c \\u003e \\u0026);
  - chunk fields in this order: id, object "chat.completion.chunk", created,
    model, system_fingerprint "fp_ollama", choices; `usage` only when asked;
  - choice: index, delta, finish_reason (a pointer with no omitempty, so
    `"finish_reason":null` is on every chunk);
  - delta: role (only on the FIRST chunk), content (kept even when "" -
    `Content any` with omitempty keeps a non-nil ""), reasoning (omitted when
    ""), tool_calls (omitted when empty);
  - a response carrying both thinking and content is split in two chunks,
    reasoning first;
  - the metrics-only final response is NOT sent as a chunk; instead a
    separate finish chunk with an empty delta `{}` and finish_reason
    ("stop", "length", or "tool_calls" when a tool call was sent), then
    `data: [DONE]`.

LEGACY - v0.12.0 (openai/openai.go toChunk, ChatWriter.writeResponse),
which is what an Ollama from the second half of 2025 still sends:
  - delta is a full Message: role "assistant" on EVERY chunk, content always
    present (no omitempty);
  - no separate finish chunk: the final (done) response is itself a chunk,
    usually with content "" and finish_reason set ("tool_calls" if any tool
    call was sent), then `data: [DONE]`.

Errors (middleware/openai.go writeError, openai.NewError): an HTTP error
status with the body `{"error":{"message":...,"type":...}}`, Content-Type
application/json.

Not a test (no `test_` prefix). test_agent.py and
test_chat_stream_contract.py use it.
"""
import json

CONTENT_TYPE_STREAM = "text/event-stream"
CONTENT_TYPE_JSON = "application/json"


def go_json(obj) -> str:
    """json.Marshal: compact, UTF-8 as is, HTML characters escaped."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _chunk(cid, created, model, delta, finish=None):
    return {"id": cid, "object": "chat.completion.chunk", "created": created,
            "model": model, "system_fingerprint": "fp_ollama",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def _tool_calls(calls):
    out = []
    for i, c in enumerate(calls):
        out.append({"id": c.get("id") or f"call_{i:08x}", "index": i, "type": "function",
                    # json.Marshal of the arguments map, as a string - so it is
                    # escaped twice on the wire, exactly as Ollama does it.
                    "function": {"name": c["name"],
                                 "arguments": c["arguments"] if isinstance(c.get("arguments"), str)
                                 else go_json(c.get("arguments") or {})}})
    return out


def stream(events, *, model="jarvis-primary", legacy=False, cid="chatcmpl-742",
           created=1790000000) -> bytes:
    """The SSE body Ollama sends for one streamed chat.

    `events` is what the model produced, in order:
        ("reasoning", text)   a piece of thinking
        ("content", text)     a piece of the answer
        ("tool_calls", [{"name", "arguments": dict}, ...])
        ("done", reason)      "stop" | "length"  (last)
    """
    lines = []
    first = True
    tool_sent = False
    done = "stop"
    for kind, value in events:
        if kind == "done":
            done = value
            continue
        if legacy:
            delta = {"role": "assistant", "content": value if kind == "content" else ""}
            if kind == "reasoning":
                delta["reasoning"] = value
            if kind == "tool_calls":
                delta["tool_calls"] = _tool_calls(value)
                tool_sent = True
            lines.append(_chunk(cid, created, model, delta))
            continue
        # current
        if kind == "reasoning":
            delta = {}
            if first:
                delta["role"] = "assistant"
            delta["reasoning"] = value
        else:
            delta = {}
            if first:
                delta["role"] = "assistant"
            delta["content"] = value if kind == "content" else ""
            if kind == "tool_calls":
                delta["tool_calls"] = _tool_calls(value)
                tool_sent = True
        first = False
        lines.append(_chunk(cid, created, model, delta))
    reason = "tool_calls" if (tool_sent and done == "stop") else done
    if legacy:
        lines.append(_chunk(cid, created, model,
                            {"role": "assistant", "content": ""}, reason))
    else:
        lines.append(_chunk(cid, created, model, {}, reason))
    body = "".join(f"data: {go_json(c)}\n\n" for c in lines) + "data: [DONE]\n\n"
    return body.encode("utf-8")


def completion(events, *, model="jarvis-primary", cid="chatcmpl-742",
               created=1790000000) -> bytes:
    """The JSON body Ollama sends for the same chat with stream false
    (openai.ToChatCompletion)."""
    text = "".join(v for k, v in events if k == "content")
    thinking = "".join(v for k, v in events if k == "reasoning")
    calls = [c for k, v in events if k == "tool_calls" for c in v]
    done = next((v for k, v in events if k == "done"), "stop")
    msg = {"role": "assistant", "content": text}
    if thinking:
        msg["reasoning"] = thinking
    if calls:
        msg["tool_calls"] = _tool_calls(calls)
    reason = "tool_calls" if (calls and done == "stop") else done
    return (go_json({"id": cid, "object": "chat.completion", "created": created,
                     "model": model, "system_fingerprint": "fp_ollama",
                     "choices": [{"index": 0, "message": msg, "finish_reason": reason}],
                     "usage": {"prompt_tokens": 12, "completion_tokens": 7,
                               "total_tokens": 19}}) + "\n").encode("utf-8")


def error_body(status: int, message: str) -> bytes:
    kind = {400: "invalid_request_error", 404: "not_found_error"}.get(status, "api_error")
    return (go_json({"error": {"message": message, "type": kind}}) + "\n").encode("utf-8")


class FakeResponse:
    """urllib's response object, closely enough: a context manager with
    read(n) and read1(n), handing out the body in `pieces`-sized slices so a
    line is split across reads the way TCP splits it."""

    def __init__(self, body: bytes, pieces: int = 7, content_type=CONTENT_TYPE_STREAM):
        self._body = body
        self._step = max(1, pieces)
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.closed = True
        return False

    def close(self):
        self.closed = True

    def read1(self, n=1024):
        take = min(n, self._step)
        out, self._body = self._body[:take], self._body[take:]
        return out

    read = read1
