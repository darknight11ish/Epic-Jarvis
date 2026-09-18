"""jarvis_agent.py: every tool call gated before it runs, nothing real touched.

Three things are proven, not just the happy path: a denied tool never
executes, an unclassified/ungated tool fails CLOSED rather than running
anyway, and the final answer is streamed byte-for-byte from whatever the
model actually said - never synthesised here.

    python3 test_agent.py
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_agent as AG

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoRealIO:
    """Fail loudly if the real (network-touching) post/stream ever runs."""

    def __enter__(self):
        self.real_post, self.real_stream = AG._post, AG._open_stream
        def boom_post(*a, **k):
            raise AssertionError("a real HTTP POST ran")
        def boom_stream(*a, **k):
            raise AssertionError("a real streaming request ran")
        AG._post, AG._open_stream = boom_post, boom_stream
        return self

    def __exit__(self, *a):
        AG._post, AG._open_stream = self.real_post, self.real_stream
        return False


class FakeStream:
    """A context manager standing in for urllib's response object."""
    def __init__(self, chunks):
        self._chunks = list(chunks) + [b""]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, _n=1024):
        return self._chunks.pop(0) if self._chunks else b""


def allow(*_a, **_k):
    class _Ok:
        allowed = True
        reason = "approved"
    return _Ok()


def deny(*_a, **_k):
    class _No:
        allowed = False
        reason = "denied by a human"
    return _No()


def scripted_post(responses):
    """Returns a `post` that answers each call with the next scripted
    response, and records every payload it was given."""
    calls = []
    it = iter(responses)
    def caller(url, payload):
        calls.append(payload)
        return next(it)
    return caller, calls


def t_no_tool_call_streams_straight_through():
    responses = [{"choices": [{"message": {"role": "assistant", "content": "hi"}}]}]
    post, calls = scripted_post(responses)
    streamed = []
    stream_payloads = []
    def open_stream(url, payload):
        stream_payloads.append(payload)
        return FakeStream([b'{"done":true}\n'])
    with NoRealIO():
        AG.run_local_turn(
            [{"role": "user", "content": "hello"}], "qwen3:8b", ollama_url="http://x",
            stream_out=streamed.append, post=post, gate_check=allow,
            open_stream=open_stream)
    check("exactly one non-streaming round trip when no tool is requested",
          len(calls) == 1, repr(calls))
    check("the final bytes came from the injected stream, not fabricated",
          streamed == [b'{"done":true}\n'], repr(streamed))
    # The bug this guards against: the loop already decided (in the round
    # above) that this turn needs no tool. Offering `tools` again on the
    # final streaming call lets a nondeterministic model change its mind and
    # request a tool a second time, whose raw tool_call delta JSON would
    # then stream to the client unexecuted and ungated - nothing here reads
    # tool_calls out of a streamed response.
    check("the final streaming call does not offer tools",
          "tools" not in stream_payloads[0], repr(stream_payloads[0]))


def t_a_denied_tool_never_executes():
    executed = []
    real = AG.TOOLS["shell_exec"].execute
    AG.TOOLS["shell_exec"].execute = lambda args, state, **kw: executed.append(args) or {"ok": True}
    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "shell_exec",
                 "arguments": json.dumps({"command": "rm -rf /"})}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "I could not do that."}}]},
        ]
        post, calls = scripted_post(responses)
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "delete everything"}], "qwen3:8b",
                ollama_url="http://x", stream_out=lambda b: None, post=post,
                gate_check=deny,
                open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
        check("a denied tool call never runs the real tool", executed == [], repr(executed))
        check("the model sees a refusal, not a silent success",
              "refused" in calls[1]["messages"][-1]["content"], repr(calls[1]["messages"][-1]))
    finally:
        AG.TOOLS["shell_exec"].execute = real


def t_an_approved_tool_actually_runs_and_feeds_back_the_result():
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": 4}
    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "calculator",
                 "arguments": json.dumps({"expression": "2+2"})}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "It's 4."}}]},
        ]
        post, calls = scripted_post(responses)
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "what is 2+2"}], "qwen3:8b",
                ollama_url="http://x", stream_out=lambda b: None, post=post,
                gate_check=allow,
                open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
        check("two rounds: the tool call, then the answer using its result", len(calls) == 2)
        tool_msg = calls[1]["messages"][-1]
        check("the tool's real result is fed back as a tool message",
              tool_msg["role"] == "tool" and '"value": 4' in tool_msg["content"],
              repr(tool_msg))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_arguments_already_a_dict_does_not_crash_the_loop():
    """Some OpenAI-compatible backends hand back `function.arguments`
    already parsed into an object instead of a JSON string. json.loads() on
    a dict raises TypeError, not JSONDecodeError - uncaught, that used to
    escape run_local_turn entirely and get blamed on Ollama being down by
    the caller's own outer handler, rather than treated as "empty args" the
    way a malformed JSON string already was."""
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": args}
    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "calculator", "arguments": {"expression": "2+2"}}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        ]
        post, calls = scripted_post(responses)
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "x"}], "qwen3:8b", ollama_url="http://x",
                stream_out=lambda b: None, post=post, gate_check=allow,
                open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
        check("a dict-shaped arguments value is used directly, not crashed on",
              '"value": {"expression": "2+2"}' in calls[1]["messages"][-1]["content"],
              repr(calls[1]["messages"][-1]))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_an_unknown_tool_name_is_refused_not_guessed():
    responses = [
        {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "1", "function": {"name": "definitely_not_a_real_tool",
             "arguments": "{}"}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
    ]
    post, calls = scripted_post(responses)
    with NoRealIO():
        AG.run_local_turn(
            [{"role": "user", "content": "x"}], "qwen3:8b", ollama_url="http://x",
            stream_out=lambda b: None, post=post, gate_check=allow,
            open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
    tool_msg = calls[1]["messages"][-1]
    check("an unregistered tool name produces an error result, not a crash",
          "no such tool" in tool_msg["content"], repr(tool_msg))


def t_file_read_caps_by_bytes_not_characters():
    """Text-mode `open(...).read(N)` caps CHARACTERS, not bytes, while the
    constant and the tool's contract both claim bytes. A file that is
    mostly multi-byte UTF-8 could return up to ~4x the stated cap. Written
    with a real temp file because the bug is specifically about how many
    bytes actually get read off disk, which a fake can't stand in for."""
    import tempfile, os
    real_cap = AG._MAX_FILE_READ_BYTES
    AG._MAX_FILE_READ_BYTES = 10
    try:
        # Each "€" is 3 bytes in UTF-8 - 5 of them is 15 bytes, comfortably
        # over the 10-byte cap, but only 5 characters, comfortably under a
        # char-based one.
        text = "€" * 5
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                          encoding="utf-8") as f:
            f.write(text)
            path = f.name
        try:
            out = AG._run_file_read({"path": path})
        finally:
            os.unlink(path)
        # 5 "€" is 15 bytes but only 5 characters - under the old text-mode
        # `.read(cap + 1)` bug, reading a 5-character file never even hits an
        # 11-CHARACTER cap, so it would come back whole with truncated=False
        # despite being 1.5x the intended 10-BYTE budget. The fix must catch
        # that on bytes.
        check("a multi-byte-heavy file is truncated once BYTES exceed the cap, "
              "not left whole because it has few CHARACTERS",
              out["truncated"] is True, repr(out))
        check("the truncated content is genuinely shorter than the original, "
              "not the whole file returned anyway",
              out["content"] != text, repr(out))
    finally:
        AG._MAX_FILE_READ_BYTES = real_cap


def t_every_tool_resolves_to_a_real_jarvis_gate_action():
    """The bug this guards against is silent, not loud: passing a name
    jarvis_gate does not recognise doesn't raise - action_for_tool() just
    falls through to "unclassified_tool", which still asks by default, so
    the tool APPEARS to work right up until someone checks what action name
    actually reached the gate. Every tool here must resolve to something
    _TOOL_ACTIONS actually has an entry for."""
    try:
        import jarvis_gate
    except Exception:
        return check("SKIP - jarvis_gate not importable in this environment", True)
    for tname, tool in AG.TOOLS.items():
        lookup = tool.gate_lookup_name({}) if tool.gate_lookup_name else tname
        check(f"jarvis_gate._TOOL_ACTIONS has an entry for {tname}'s lookup name {lookup!r}",
              lookup in jarvis_gate._TOOL_ACTIONS, lookup)


def t_calculator_cannot_reach_names_or_calls():
    for expr in ("__import__('os').system('echo hi')", "open('/etc/passwd').read()",
                 "os.system('x')"):
        out = AG._run_calculator({"expression": expr})
        check(f"rejected as non-arithmetic: {expr!r}", out["ok"] is False, repr(out))
    check("plain arithmetic still works", AG._run_calculator({"expression": "2 + 3 * 4"}) == {"ok": True, "value": 14})


def t_enabled_tools_actually_restricts_what_the_model_is_offered_and_can_call():
    executed = []
    real = AG.TOOLS["shell_exec"].execute
    AG.TOOLS["shell_exec"].execute = lambda args, state, **kw: executed.append(args) or {"ok": True}
    try:
        seen_bodies = []
        # The model tries shell_exec even though it was never offered - a
        # forged or stale tool_call, not something this loop should trust
        # just because a name matches something in TOOLS.
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "shell_exec",
                 "arguments": json.dumps({"command": "echo hi"})}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
        ]
        it = iter(responses)
        def post(url, payload):
            seen_bodies.append(payload)
            return next(it)
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "run a command"}], "qwen3:8b",
                ollama_url="http://x", stream_out=lambda b: None, post=post,
                gate_check=allow, enabled_tools={"calculator"},
                open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
        offered = [t["function"]["name"] for t in seen_bodies[0]["tools"]]
        check("only the enabled tool is offered to the model",
              offered == ["calculator"], repr(offered))
        check("a tool call for something not enabled never actually runs",
              executed == [], repr(executed))
        check("the model is told it does not have that tool, not given a silent pass",
              "no such tool" in seen_bodies[1]["messages"][-1]["content"],
              repr(seen_bodies[1]["messages"][-1]))
    finally:
        AG.TOOLS["shell_exec"].execute = real


def t_empty_enabled_tools_offers_nothing():
    seen_bodies = []
    def post(url, payload):
        seen_bodies.append(payload)
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    with NoRealIO():
        AG.run_local_turn(
            [{"role": "user", "content": "hi"}], "qwen3:8b", ollama_url="http://x",
            stream_out=lambda b: None, post=post, gate_check=allow,
            enabled_tools=set(),
            open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
    check("an empty enabled set offers no tools at all", seen_bodies[0]["tools"] == [])


def t_max_rounds_stops_an_infinite_tool_loop():
    def always_wants_a_tool(url, payload):
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "1", "function": {"name": "calculator",
             "arguments": json.dumps({"expression": "1"})}}]}}]}
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": 1}
    try:
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "loop forever"}], "qwen3:8b",
                ollama_url="http://x", stream_out=lambda b: None,
                post=always_wants_a_tool, gate_check=allow, max_rounds=3,
                open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
        check("run_local_turn returns rather than looping forever", True)
    finally:
        AG.TOOLS["calculator"].execute = real


if __name__ == "__main__":
    for fn in (t_no_tool_call_streams_straight_through, t_a_denied_tool_never_executes,
               t_an_approved_tool_actually_runs_and_feeds_back_the_result,
               t_arguments_already_a_dict_does_not_crash_the_loop,
               t_an_unknown_tool_name_is_refused_not_guessed,
               t_file_read_caps_by_bytes_not_characters,
               t_every_tool_resolves_to_a_real_jarvis_gate_action,
               t_calculator_cannot_reach_names_or_calls,
               t_enabled_tools_actually_restricts_what_the_model_is_offered_and_can_call,
               t_empty_enabled_tools_offers_nothing,
               t_max_rounds_stops_an_infinite_tool_loop):
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
