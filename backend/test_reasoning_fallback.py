"""An empty cloud answer falls back to the model's working-out, marked.

    python3 test_reasoning_fallback.py

WHY THIS EXISTS. Measured on the owner's PC on 2026-10-14, on four escalated
turns driven through the live `/api/chat`: every one came back
`finish_reason: "length"`, `len(content) == 0`, and all 2048 completion tokens
spent on `reasoning_tokens` - DeepSeek's thinking mode is on by default, the
cap defaults to 2048, and the thinking is billed INSIDE it. `content` was empty
and nothing in the program read `reasoning_content`, so the owner pressed "Try
the cloud model" on the hardest question he had and was shown a blank card.
The full record is `docs/FIELD-TEST-CLOUD-ESCALATION-2026-10-14.md`.

THE OWNER'S DECISION (2026-10-14): when the visible answer is empty and the
reply carries the reasoning, show the reasoning - rather than turn his thinking
off or change what he is billed for. So it is a FALLBACK: `jarvis_chatbot_api.
CloudAnswer` passes a reply with any visible text through byte for byte, and
`reasoning_answer()` is the same law for a whole reply.

WHAT IS CHECKED, and each half can fail on its own:

  1. the reader, driven with the SHAPES THE FIELD TEST RECORDED - a
     reasoning-only stream, a normal stream, a whole JSON reply each way - and
     with the bytes split at arbitrary places, because a naive reader that
     split on a chunk boundary would lose an event;
  2. that a reply WITH an answer is untouched, byte for byte, so nothing
     ordinary changes;
  3. that the added text lands BEFORE the finish_reason / `[DONE]`, because
     every reader in this program (the HUD page, main.js, the phone's
     ChatChunkParser) finalizes on that event and would drop anything after
     it;
  4. that a turn with neither an answer nor working-out says so plainly
     instead of rendering an empty card;
  5. that the relay in `jarvis-backend/jarvis_hud.py` actually uses it, and
     still hands `jarvis_speed`'s meter the SERVICE's own bytes in the same
     order - the whole point of "the spend must not change";
  6. that the money in `ApiChatbot._parse` is counted from the ORIGINAL text,
     so a reasoning fallback cannot inflate a guessed token count;
  7. the twin rule: `backend/jarvis_chatbot_api.py` and
     `jarvis-backend/jarvis_chatbot_api.py` are byte-identical.

No network, no socket, no file outside a temporary folder. The owner's money
file is never read or written here.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
# THE PUBLISHED BASE MUST CARRY NO BYTECODE. `jarvis-backend/` is the tracked
# copy of the whole program - the folder a stranger clones - and importing a
# module from it writes `jarvis-backend/__pycache__/`, which
# backend/test_base_matches_repo.py then fails on ("bytecode; it embeds absolute
# paths, and git ignores it"). This suite is run by scripts/apply-patches.ps1's
# own test loop WITHOUT -B, so it turns bytecode writing off itself before the
# first import from the base. (CI's run_suites.py passes -B, which is why this
# only ever bit the patcher's run.)
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "jarvis-backend"))

import jarvis_chatbot_api as API  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


# ---------------------------------------------------------------------------
#   The shapes the field test recorded, verbatim in structure
# ---------------------------------------------------------------------------

def chunk(payload: dict) -> bytes:
    return b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n"


def delta(text: str) -> dict:
    return {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}


def hidden(text: str) -> dict:
    return {"choices": [{"index": 0, "delta": {"reasoning_content": text},
                         "finish_reason": None}]}


REASONING = "We need answer. User asks: compare three approaches. Limited. Let me plan:"
FINISH_LENGTH = {"choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
                 "usage": {"prompt_tokens": 279, "completion_tokens": 2048,
                           "total_tokens": 2327,
                           "completion_tokens_details": {"reasoning_tokens": 2048}}}

#: What the owner's four escalated calls actually streamed: no visible content
#: at all, 2048 working-out chunks, and the cap reached.
REASONING_ONLY = (chunk(delta("")) + chunk(hidden(REASONING[:20]))
                  + chunk(hidden(REASONING[20:])) + chunk(FINISH_LENGTH)
                  + b"data: [DONE]\n\n")

#: The same question when the model does write an answer.
WITH_ANSWER = (chunk(delta("Exact hashing ")) + chunk(delta("wins below a million."))
               + chunk({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
               + b"data: [DONE]\n\n")

#: A reply that ended without an answer and without any working-out.
NOTHING = (chunk({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
           + b"data: [DONE]\n\n")


def run(stream: bytes, *, streamed=True, size=7) -> bytes:
    """Drive one reply through the reader in fixed-size reads.

    `size=7` on purpose: seven bytes cuts events, JSON and `data:` lines in
    places no hand-written example would, so a reader that assumed one chunk
    per event fails here rather than on the owner's PC."""
    reader = API.CloudAnswer(streamed)
    out = []
    for i in range(0, len(stream), size):
        out.append(reader.feed(stream[i:i + size]))
    out.append(reader.close())
    return b"".join(out)


def body(**message) -> bytes:
    return json.dumps({"id": "x", "model": "deepseek-flash",
                       "choices": [{"index": 0, "message": dict(message),
                                    "finish_reason": "length"}],
                       "usage": {"prompt_tokens": 279, "completion_tokens": 2048,
                                 "total_tokens": 2327,
                                 "completion_tokens_details": {"reasoning_tokens": 2048}}},
                      ensure_ascii=False).encode("utf-8")


def streamed_text(raw: bytes) -> str:
    """Every `delta.content` in a stream, joined - what a client would show."""
    said = []
    for line in raw.split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:") or line[5:].strip() == b"[DONE]":
            continue
        try:
            got = json.loads(line[5:].strip().decode("utf-8"))
        except ValueError:
            continue
        said.append((got.get("choices") or [{}])[0].get("delta", {}).get("content") or "")
    return "".join(said)


# ---------------------------------------------------------------------------
#   1. The reasoning-only stream - the defect this exists for
# ---------------------------------------------------------------------------

def t_reasoning_only_stream():
    if not hasattr(API, "CloudAnswer"):
        return check("jarvis_chatbot_api has a reader for a cloud reply (CloudAnswer)",
                     False, "the class is absent - this is the pre-fix module")
    reader = API.CloudAnswer(True)
    out = b"".join([reader.feed(REASONING_ONLY), reader.close()])
    check("a reasoning-only stream is not left blank",
          streamed_text(out).strip() != "", repr(streamed_text(out))[:200])
    check("... it is shown under the line that says what it is",
          API.REASONING_NOT_ANSWER in streamed_text(out),
          f"the marker is {API.REASONING_NOT_ANSWER!r}")
    check("... the marker says the model wrote no answer and this is its working-out",
          "ran out of room" in API.REASONING_NOT_ANSWER
          and "working-out" in API.REASONING_NOT_ANSWER,
          API.REASONING_NOT_ANSWER)
    check("... and the working-out itself is there, in order, whole",
          REASONING in streamed_text(out).replace("\n", ""),
          repr(streamed_text(out))[:300])
    check("... the reader says the working-out is what was shown",
          reader.used_reasoning is True)

    # Nothing the service sent may be dropped: take the added event out and the
    # stream must be exactly the bytes that came in, event for event.
    events = [e + b"\n\n" for e in out.split(b"\n\n") if e]
    original = [e + b"\n\n" for e in REASONING_ONLY.split(b"\n\n") if e]
    added_events = [e for e in events if API.REASONING_NOT_ANSWER.encode() in e]
    check("exactly one event is added to the stream", len(added_events) == 1,
          [e[:80] for e in events])
    check("... and every event the service sent is still there, in order, byte for byte",
          [e for e in events if e not in added_events] == original,
          [e[:60] for e in events])

    # The order is the part a client depends on.
    added = events.index(added_events[0])
    finish = [i for i, e in enumerate(events) if b'"finish_reason": "length"' in e]
    done = [i for i, e in enumerate(events) if e.strip() == b"data: [DONE]"]
    check("the added text lands BEFORE the finish_reason and before [DONE]",
          finish and done and added < finish[0] < done[0],
          f"added={added} finish={finish} done={done} - every reader here stops "
          "at the finish event and would drop text written after it")
    check("... and the service's own usage still rides the finish event untouched",
          b'"completion_tokens": 2048' in events[finish[0]],
          events[finish[0]][:200])

    # Splitting the bytes anywhere must not change the answer.
    sizes = {run(REASONING_ONLY, size=n) for n in (1, 3, 7, 64, 4096)}
    check("the answer does not depend on where the bytes were split",
          len(sizes) == 1,
          [streamed_text(s)[:60] for s in sizes])

    # SSE allows either ending for an event, and a reader that knew only one
    # would hold the whole stream and quietly add nothing to it.
    crlf = REASONING_ONLY.replace(b"\n\n", b"\r\n\r\n")
    check("a stream that ends its events with CRLF is read as well",
          API.REASONING_NOT_ANSWER in streamed_text(run(crlf))
          and REASONING in streamed_text(run(crlf)),
          repr(run(crlf))[:200])
    crlf_answer = WITH_ANSWER.replace(b"\n\n", b"\r\n\r\n")
    check("... and a CRLF stream with an answer still comes out byte for byte",
          run(crlf_answer) == crlf_answer)


# ---------------------------------------------------------------------------
#   2. A real answer is never touched
# ---------------------------------------------------------------------------

def t_a_real_answer_is_untouched():
    check("a streamed reply with an answer comes out byte for byte",
          run(WITH_ANSWER) == WITH_ANSWER, repr(run(WITH_ANSWER))[:200])
    check("... and nothing is added to it",
          API.REASONING_NOT_ANSWER.encode() not in run(WITH_ANSWER)
          and API.NO_ANSWER_AT_ALL.encode() not in run(WITH_ANSWER))
    check("... even when the working-out came FIRST and the answer after it",
          run(chunk(hidden("thinking...")) + WITH_ANSWER)
          == chunk(hidden("thinking...")) + WITH_ANSWER)
    reader = API.CloudAnswer(True)
    reader.feed(WITH_ANSWER)
    reader.close()
    check("... and the reader does not claim the working-out was shown",
          reader.used_reasoning is False)

    whole = body(content="Exact hashing wins below a million.",
                 reasoning_content="thinking...")
    check("a whole reply with an answer comes out byte for byte",
          run(whole, streamed=False) == whole)

    # A tool call is an answer of its own kind, with `content` empty by design.
    called = json.loads(whole.decode("utf-8"))
    called["choices"][0]["message"]["content"] = ""
    called["choices"][0]["message"]["tool_calls"] = [
        {"id": "call_1", "type": "function",
         "function": {"name": "web_search", "arguments": "{}"}}]
    called_bytes = json.dumps(called).encode("utf-8")
    check("a whole reply that asked for a tool is left alone, working-out and all",
          run(called_bytes, streamed=False) == called_bytes,
          repr(run(called_bytes, streamed=False))[:200])
    tool_stream = (chunk({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "call_1", "function": {"name": "web_search"}}]},
        "finish_reason": None}]})
        + chunk({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
        + b"data: [DONE]\n\n")
    check("... and a streamed tool call is left alone too",
          run(tool_stream) == tool_stream, repr(run(tool_stream))[:200])


# ---------------------------------------------------------------------------
#   3. Neither an answer nor any working-out: said plainly, never blank
# ---------------------------------------------------------------------------

def t_nothing_at_all():
    out = run(NOTHING)
    check("a reply with no answer and no working-out says so instead of nothing",
          API.NO_ANSWER_AT_ALL in streamed_text(out),
          repr(streamed_text(out))[:200])
    check("... before the stream's own end, like the fallback",
          out.index(API.NO_ANSWER_AT_ALL.encode()) < out.index(b"data: [DONE]"))
    whole = body(content="", reasoning_content="")
    after = json.loads(run(whole, streamed=False).decode("utf-8"))
    check("... and a whole reply with neither says so in its message",
          after["choices"][0]["message"]["content"] == API.NO_ANSWER_AT_ALL,
          after["choices"][0]["message"])


# ---------------------------------------------------------------------------
#   4. What must NOT be touched: errors, unfamiliar shapes, fragments
# ---------------------------------------------------------------------------

def t_awkward_shapes():
    err = json.dumps({"error": {"message": "rate limited", "type": "server_error"}}).encode()
    check("an error body is passed through untouched",
          run(err, streamed=False) == err, repr(run(err, streamed=False))[:200])

    weird = json.dumps({"ok": True, "note": "not a chat reply"}).encode()
    check("a body in an unfamiliar shape is passed through untouched",
          run(weird, streamed=False) == weird)

    broken = b"data: {not json\n\n"
    check("a stream whose only data is unreadable is passed through untouched",
          run(broken) == broken, repr(run(broken))[:200])

    # A stream that stops in the middle of an event is a fragment: the client's
    # own "interrupted" handling is the honest answer, and nothing is added.
    fragment = REASONING_ONLY[:-8]
    check("a stream cut off mid-event is passed through and nothing is added",
          run(fragment) == fragment, repr(run(fragment))[:200])

    plain = b'data: {"choices":[{"delta":{"content":"one word"}}]}\n\n' \
            b"data: [DONE]\n\n"
    check("a normal stream is byte-identical (the control)",
          run(plain) == plain, repr(run(plain))[:200])


# ---------------------------------------------------------------------------
#   5. The law for a whole reply, where jarvis_chatbot_api parses one
# ---------------------------------------------------------------------------

def t_reasoning_answer():
    if not hasattr(API, "reasoning_answer"):
        return check("jarvis_chatbot_api.reasoning_answer exists", False)
    shown, used = API.reasoning_answer(
        {"choices": [{"message": {"role": "assistant", "content": "",
                                  "reasoning_content": REASONING}}]})
    check("a whole reply with an empty answer but a working-out uses it, marked",
          used is True and shown.startswith(API.REASONING_NOT_ANSWER)
          and REASONING in shown, repr(shown)[:200])
    shown, used = API.reasoning_answer(
        {"choices": [{"message": {"content": "a real answer",
                                  "reasoning_content": REASONING}}]})
    check("... a reply with an answer is returned as it is",
          (shown, used) == ("a real answer", False), repr((shown, used)))
    shown, used = API.reasoning_answer({"choices": [{"message": {"content": ""}}]})
    check("... and a reply with neither is left to the caller's own words",
          (shown, used) == ("", False), repr((shown, used)))
    check("... a whitespace-only answer counts as empty, as it does everywhere else",
          API.reasoning_answer({"choices": [{"message": {"content": "   \n",
                                                         "reasoning_content": "x"}}]})[1] is True)


# ---------------------------------------------------------------------------
#   6. The relay uses it - and the meter still gets the service's own bytes
# ---------------------------------------------------------------------------

def t_the_relay_uses_it():
    src = (REPO / "jarvis-backend" / "jarvis_hud.py").read_text(encoding="utf-8")
    try:
        start = src.index('_read = getattr(upstream, "read1", None) or upstream.read')
        end = src.index("_speed.finish(lane)", start)
    except ValueError as exc:
        return check("the cloud relay's read-back loop is still where it was", False, exc)
    block = src[start:end]
    check("the relay runs the cloud reply through the reader",
          "_says.feed(chunk)" in block, block[-600:])
    check("... and writes what the reader withholds, when the service is done",
          "_says.close()" in block, block[-600:])
    check("... and the reader is made from jarvis_chatbot_api's own rule",
          "jarvis_chatbot_api" in src[:start] and "CloudAnswer(" in src[:start][-2000:],
          src[:start][-800:])
    check("... only for a lane that is not the local model",
          "lane != local_model" in src[:start][-2000:], src[:start][-800:])
    check("... told whether the body is a stream, from the service's own header",
          'event-stream' in src[:start][-2000:] and "Content-Type" in src[:start][-2000:])
    check("the meter is still fed the SERVICE's bytes, not what was added",
          "_speed.feed(chunk)" in block and "_speed.feed(_out)" not in block,
          block[-600:])
    check("... so nothing about the spend can move because of this fallback",
          "_speed.feed(chunk)" in block)
    # The bug this replaces: the raw chunk written straight to the client, so
    # the reader could not withhold the end of the stream.
    check("the old unconditional write of the upstream chunk is gone",
          "self.wfile.write(chunk)" not in block, block[-600:])


# ---------------------------------------------------------------------------
#   7. The money is counted from the original text
# ---------------------------------------------------------------------------

def t_the_money_cannot_move():
    src = (HERE / "jarvis_chatbot_api.py").read_text(encoding="utf-8")
    parse = src[src.index("    def _parse(self, body: bytes"):]
    parse = parse[:parse.index("\n    def ", 10)]
    counted = parse.index("self._count_money(use, counts, messages or [], text)")
    fallback = parse.index("reasoning_answer(got)")
    check("the money is counted BEFORE any reasoning fallback replaces the text",
          counted < fallback,
          "the fallback must not reach the token guess: a guessed completion "
          "count would then be the working-out's length, which is not what the "
          "service charged for")

    # And behaviourally, each in its own month's file so the two cannot mix.
    def recorded(raw: bytes) -> dict:
        real_path = API.money_path
        with tempfile.TemporaryDirectory(prefix="reasoning-fallback-") as tmp:
            API.money_path = lambda: Path(tmp) / "api-money.json"
            try:
                bot = API.ApiChatbot(API.PRESETS["deepseek_api"], "deepseek-flash")
                bot._parse(raw, [{"role": "user", "content": "a question"}])
                data = json.loads((Path(tmp) / "api-money.json").read_text(encoding="utf-8"))
            finally:
                API.money_path = real_path
        return data["months"][sorted(data["months"])[-1]]["deepseek_api"]

    no_usage = json.dumps(
        {"choices": [{"index": 0, "message": {"role": "assistant", "content": "",
                                              "reasoning_content": REASONING},
                      "finish_reason": "length"}]}).encode("utf-8")
    row = recorded(no_usage)
    check("a reasoning-only reply with no usage records the ORIGINAL text's tokens, "
          "not the working-out's",
          row["completion_tokens"] == 0,
          f"recorded={row['completion_tokens']} - {len(REASONING)} characters "
          "of working-out must not become billed tokens")
    check("... and it is still counted as an estimate, exactly as before this",
          row["guessed_from_length"] == 1, row)

    row = recorded(body(content="", reasoning_content=REASONING))
    check("a reply carrying the service's own usage records exactly that",
          row["completion_tokens"] == 2048 and not row.get("guessed_from_length"), row)
    check("... and the prompt tokens are the service's own figure too",
          row["prompt_tokens"] == 279, row)


# ---------------------------------------------------------------------------
#   8. The twin rule
# ---------------------------------------------------------------------------

def t_the_twins_match():
    a = (HERE / "jarvis_chatbot_api.py").read_bytes()
    b = (REPO / "jarvis-backend" / "jarvis_chatbot_api.py").read_bytes()
    check("backend/ and jarvis-backend/ jarvis_chatbot_api.py are byte-identical",
          a == b, "the two-file rule: the base is what an installer ships")


def main() -> int:
    checks = [t_reasoning_only_stream, t_a_real_answer_is_untouched, t_nothing_at_all,
              t_awkward_shapes, t_reasoning_answer, t_the_relay_uses_it,
              t_the_money_cannot_move, t_the_twins_match]
    for fn in checks:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception as exc:                      # a crash is a failure here
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} ran to the end", False, f"{type(exc).__name__}: {exc}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
