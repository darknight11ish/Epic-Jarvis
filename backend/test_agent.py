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

# Every turn in this file would otherwise reach the default end-of-turn
# recorder, which writes to the real audit log and may raise a real skill
# card on the owner's machine. Captured here instead, for every test.
RECORDED = []
AG._record_chain = RECORDED.append

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


def t_arguments_as_a_json_scalar_does_not_crash_the_loop():
    """A step further than the dict-shaped case above: `arguments` can be
    valid JSON and still not be an object at all - the string "123" parses
    to the int 123, not a dict. Every tool's prepare()/execute() calls
    args.get(...), which a bare int has no method by that name for."""
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": args}
    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "calculator", "arguments": "123"}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        ]
        post, calls = scripted_post(responses)
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "x"}], "qwen3:8b", ollama_url="http://x",
                stream_out=lambda b: None, post=post, gate_check=allow,
                open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
        check("a bare JSON scalar is treated as empty args, not crashed on",
              '"value": {}' in calls[1]["messages"][-1]["content"],
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


def t_file_read_rejects_reserved_windows_device_names():
    """Opening "CON" for reading, on Windows, opens the console and BLOCKS
    waiting for a keypress that will never come from a headless service -
    not a sandbox escape, just a path that resolves to a device instead of
    a file. Checked with names in a directory and with an extension too,
    since both are still the reserved device on real Windows."""
    for bad in ("CON", "con", "NUL", "COM1", "LPT9",
                "C:\\Users\\me\\CON", "C:\\Users\\me\\con.txt"):
        out = AG._run_file_read({"path": bad})
        check(f"rejected as a reserved device, not opened: {bad!r}",
              out["ok"] is False and "reserved" in out["error"], repr(out))
    check("CONTROL: a name that merely starts with a reserved word still works",
          AG._is_reserved_windows_name("CONTACT.txt") is False)


def t_tool_content_never_slices_a_json_string_mid_structure():
    """json.dumps(result)[:8000] can cut off mid-string or mid-brace,
    handing the model a hand-mangled JSON fragment instead of its actual
    tool result - and a large result is not hypothetical: file_read alone
    can return up to 200,000 characters."""
    small = {"ok": True, "value": 4}
    check("a result well under the cap is returned whole, unmodified",
          json.loads(AG._tool_content(small)) == small, AG._tool_content(small))
    big = {"ok": True, "content": "x" * 50_000}
    out = AG._tool_content(big)
    check("an oversized result is still valid JSON",
          json.loads(out) is not None, out[:200])
    check("it says it was truncated rather than silently cutting the string",
          json.loads(out).get("truncated") is True, out[:200])
    check("the safe fallback itself stays under the cap",
          len(out) <= AG._MAX_TOOL_CONTENT_CHARS, len(out))


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


def t_a_prepare_time_failure_is_a_tool_result_not_a_dead_turn():
    """`tool.prepare()` sat outside every try in run_local_turn, so a tool
    that validated its own arguments - `{"days_ahead": "seven"}` reaching an
    int() - raised straight out of the whole turn. This function's own
    docstring promises a tool failure comes back as a tool RESULT the model
    can read and retry from; that promise covered execute() and not
    prepare(). Reproduced before the fix."""
    real = AG.TOOLS["calculator"].prepare

    def explodes(args):
        raise ValueError("days_ahead must be a number, got 'seven'")

    AG.TOOLS["calculator"].prepare = explodes
    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "calculator",
                 "arguments": json.dumps({"expression": "2+2"})}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "Sorry."}}]},
        ]
        post, calls = scripted_post(responses)
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "what is 2+2"}], "qwen3:8b",
                ollama_url="http://x", stream_out=lambda b: None, post=post,
                gate_check=allow,
                open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
        check("the turn survived a prepare-time raise", len(calls) == 2, repr(len(calls)))
        tool_msg = calls[1]["messages"][-1]
        check("the failure came back as a tool message the model can read",
              tool_msg["role"] == "tool", repr(tool_msg))
        check("and it says what was wrong with the arguments",
              "days_ahead" in tool_msg["content"] and "ValueError" in tool_msg["content"],
              repr(tool_msg["content"]))
    finally:
        AG.TOOLS["calculator"].prepare = real


def t_a_prepare_time_failure_never_executes_the_tool():
    """CONTROL: the tool must not run when its own prepare refused the
    arguments - and the gate must not be asked to approve a plan that was
    never built."""
    real_prepare = AG.TOOLS["calculator"].prepare
    real_execute = AG.TOOLS["calculator"].execute
    ran, asked = [], []
    AG.TOOLS["calculator"].prepare = lambda args: (_ for _ in ()).throw(ValueError("no"))
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: ran.append(1) or {"ok": True}

    def watching_gate(action, detail, why):
        asked.append(action)
        return allow(action, detail, why)

    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "calculator",
                 "arguments": json.dumps({"expression": "2+2"})}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "Sorry."}}]},
        ]
        post, _calls = scripted_post(responses)
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "x"}], "qwen3:8b",
                ollama_url="http://x", stream_out=lambda b: None, post=post,
                gate_check=watching_gate,
                open_stream=lambda url, payload: FakeStream([b'{"done":true}\n']))
        check("CONTROL: the tool never executed", ran == [], repr(ran))
        check("CONTROL: the gate was never asked about a plan that does not exist",
              asked == [], repr(asked))
    finally:
        AG.TOOLS["calculator"].prepare = real_prepare
        AG.TOOLS["calculator"].execute = real_execute


def _two_tool_turn(gate_check, recorder=None, stream_fail=False):
    """calculator then shell_exec, in one round. Returns (steps recorded,
    payloads sent to the model)."""
    real_calc = AG.TOOLS["calculator"].execute
    real_shell = AG.TOOLS["shell_exec"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": 4}
    AG.TOOLS["shell_exec"].execute = lambda args, state, **kw: {"ok": True, "stdout": "SECRET-OUTPUT"}
    got = []
    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "calculator",
                 "arguments": json.dumps({"expression": "2+2 MY-PRIVATE-ARG"})}},
                {"id": "2", "function": {"name": "shell_exec",
                 "arguments": json.dumps({"command": "type C:\\diary.txt"})}},
                {"id": "3", "function": {"name": "made_up_tool", "arguments": "{}"}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
        ]
        post, calls = scripted_post(responses)

        def opener(url, payload):
            if stream_fail:
                raise ConnectionError("client went away")
            return FakeStream([b'{"done":true}\n'])
        with NoRealIO():
            try:
                AG.run_local_turn(
                    [{"role": "user", "content": "PLEASE-DO-NOT-LOG-ME"}], "qwen3:8b",
                    ollama_url="http://x", stream_out=lambda b: None, post=post,
                    gate_check=gate_check, open_stream=opener,
                    record_chain=recorder if recorder is not None else got.append)
            except ConnectionError:
                pass
        return got, calls
    finally:
        AG.TOOLS["calculator"].execute = real_calc
        AG.TOOLS["shell_exec"].execute = real_shell


def t_a_tool_turn_records_its_chain_by_tool_name_only():
    """Item 7's record: which tools one turn used, in order, and whether each
    ran - so repeated chains can be counted. Nothing else."""
    def calc_only(action, detail, prompt):
        class V:
            allowed = "shell" not in prompt
            outcome = "auto" if allowed else "denied"
            reason = "x"
            tier = "auto" if allowed else "ask"
        return V()
    got, _ = _two_tool_turn(calc_only)
    check("one record for the turn", len(got) == 1, repr(got))
    steps = got[0] if got else []
    check("both real tools recorded, in order; the invented one is not",
          [s["tool"] for s in steps] == ["calculator", "shell_exec"], repr(steps))
    check("the tool that ran without asking is recorded as ran, with the gate's outcome",
          steps and steps[0] == {"tool": "calculator", "ran": True, "ok": True,
                                 "outcome": "auto"}, repr(steps))
    check("the denied tool is recorded as NOT ran",
          len(steps) > 1 and steps[1]["ran"] is False and steps[1]["outcome"] == "denied",
          repr(steps))
    blob = json.dumps(got)
    for secret in ("PLEASE-DO-NOT-LOG-ME", "MY-PRIVATE-ARG", "diary", "SECRET-OUTPUT"):
        check(f"no conversation text reaches the record ({secret})", secret not in blob, blob)


def t_a_turn_with_no_tool_records_nothing():
    got = []
    responses = [{"choices": [{"message": {"role": "assistant", "content": "hi"}}]}]
    post, _ = scripted_post(responses)
    with NoRealIO():
        AG.run_local_turn([{"role": "user", "content": "hi"}], "qwen3:8b",
                          ollama_url="http://x", stream_out=lambda b: None, post=post,
                          gate_check=allow, record_chain=got.append,
                          open_stream=lambda u, p: FakeStream([b"x"]))
    check("a plain answer writes no chain record", got == [], repr(got))


def t_the_recorder_failing_never_breaks_the_turn():
    def boom(_steps):
        raise RuntimeError("disk full")
    streamed = []
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": 4}
    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "calculator",
                 "arguments": json.dumps({"expression": "2+2"})}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "4"}}]},
        ]
        post, _ = scripted_post(responses)
        with NoRealIO():
            AG.run_local_turn([{"role": "user", "content": "2+2"}], "qwen3:8b",
                              ollama_url="http://x", stream_out=streamed.append, post=post,
                              gate_check=allow, record_chain=boom,
                              open_stream=lambda u, p: FakeStream([b"four"]))
        check("the answer still streams when the recorder raises", streamed == [b"four"],
              repr(streamed))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_the_chain_is_recorded_even_if_the_answer_fails_to_stream():
    """The tools RAN. Losing the client afterwards does not undo that."""
    got, _ = _two_tool_turn(allow, stream_fail=True)
    check("recorded despite the stream failing", len(got) == 1, repr(got))
    check("a gate with no outcome field is recorded as 'unknown', not guessed",
          got and got[0][0]["outcome"] == "unknown", repr(got))


def t_the_default_recorder_is_used_when_none_is_passed():
    """No record_chain passed: the module's own _record_chain gets the turn.
    (Stubbed at the top of this file, so nothing real is written.)"""
    before = len(RECORDED)
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True}
    try:
        responses = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "1", "function": {"name": "calculator", "arguments": "{}"}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        ]
        post, _ = scripted_post(responses)
        with NoRealIO():
            AG.run_local_turn([{"role": "user", "content": "x"}], "qwen3:8b",
                              ollama_url="http://x", stream_out=lambda b: None, post=post,
                              gate_check=allow,
                              open_stream=lambda u, p: FakeStream([b"x"]))
    finally:
        AG.TOOLS["calculator"].execute = real
    check("the module-level recorder received the turn",
          len(RECORDED) == before + 1, f"{before} -> {len(RECORDED)}")


if __name__ == "__main__":
    for fn in (t_no_tool_call_streams_straight_through, t_a_denied_tool_never_executes,
               t_an_approved_tool_actually_runs_and_feeds_back_the_result,
               t_arguments_already_a_dict_does_not_crash_the_loop,
               t_arguments_as_a_json_scalar_does_not_crash_the_loop,
               t_an_unknown_tool_name_is_refused_not_guessed,
               t_file_read_caps_by_bytes_not_characters,
               t_file_read_rejects_reserved_windows_device_names,
               t_tool_content_never_slices_a_json_string_mid_structure,
               t_every_tool_resolves_to_a_real_jarvis_gate_action,
               t_calculator_cannot_reach_names_or_calls,
               t_enabled_tools_actually_restricts_what_the_model_is_offered_and_can_call,
               t_empty_enabled_tools_offers_nothing,
               t_max_rounds_stops_an_infinite_tool_loop,
               t_a_prepare_time_failure_is_a_tool_result_not_a_dead_turn,
               t_a_prepare_time_failure_never_executes_the_tool,
               t_a_tool_turn_records_its_chain_by_tool_name_only,
               t_a_turn_with_no_tool_records_nothing,
               t_the_recorder_failing_never_breaks_the_turn,
               t_the_chain_is_recorded_even_if_the_answer_fails_to_stream,
               t_the_default_recorder_is_used_when_none_is_passed):
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
