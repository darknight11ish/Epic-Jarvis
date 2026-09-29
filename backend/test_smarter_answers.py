""""Smarter answers" (2026-09-28): big tool results are shortened, not
dropped; older ones are cleared once the answer runs long; and "I've done
it" with nothing done gets one plain line.

  - _tool_content: a result over the limit keeps its JSON shape, the start
    and end of each long text with a plain marker between, the outside-text
    label and "ok" - always valid JSON, always under the limit.
  - clear_old_tool_results: past half the room, OLDER tool results become a
    short stub; the newest results, every assistant message, every system
    note and every word the owner said are untouched; the input list is not
    changed, and a result once cleared stays cleared the same way.
  - jarvis_claims: which sentences claim an action, and which do not (a
    question, an "if", something done earlier, remembering).
  - run_local_turn: the line is added at the end of the stream (before the
    finish chunk and [DONE]) and in a non-streamed answer, spoken-style on
    a voice turn, and never when an action tool really succeeded.

No model, no network. The model's side is Ollama's real SSE body
(_ollama_wire.py), as in test_agent.py.

    python3 test_smarter_answers.py
"""
import json
import sys
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_claims.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_claims as CL  # noqa: E402
# test_agent's harness: no real I/O, scripted Ollama streams, the recorder
# and step sink captured rather than written anywhere.
import test_agent as TA  # noqa: E402

FAILED, PASSED = [], []
URL = "http://127.0.0.1:11434"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   1. Shortening a big tool result
# --------------------------------------------------------------------------

def _labelled(result):
    return {AG.OUTSIDE_FIELD: AG.OUTSIDE_LABEL, **result}


def t_a_small_result_is_unchanged():
    small = _labelled({"ok": True, "value": 4})
    check("a result under the limit is sent exactly as it is",
          AG._tool_content(small) == json.dumps(small, ensure_ascii=False))


def t_one_long_text_keeps_its_start_and_end():
    head, tail = "START-" + "a" * 3000, "b" * 3000 + "-THE-END"
    text = head + "m" * 40_000 + tail
    out = AG._tool_content(_labelled({"ok": True, "path": "C:/x.txt", "content": text}))
    got = json.loads(out)
    check("valid JSON, under the limit", len(out) <= AG._MAX_TOOL_CONTENT_CHARS, len(out))
    check("the outside-text label is kept, first, word for word",
          list(got)[0] == AG.OUTSIDE_FIELD and got[AG.OUTSIDE_FIELD] == AG.OUTSIDE_LABEL,
          list(got)[:3])
    check("ok and the short fields are kept as they were",
          got["ok"] is True and got["path"] == "C:/x.txt", got)
    check("a plain note says it was shortened", "shortened" in got
          and "left out" in got["shortened"], got.get("shortened"))
    c = got["content"]
    check("the first 1,500 characters are kept", c.startswith(text[:1500]), c[:40])
    check("the last 1,500 characters are kept", c.endswith(text[-1500:]), c[-40:])
    gone = len(text) - 3000
    check("the marker says how much was left out, in plain words",
          f"[... {gone:,} characters left out ...]" in c, c[1490:1560])


def t_many_long_texts_each_keep_both_ends():
    emails = [{"from": f"sender{i}@example.com", "subject": f"Subject {i}",
               "body": f"BEGIN{i} " + "word " * 500 + f" END{i}"} for i in range(20)]
    out = AG._tool_content(_labelled({"ok": True, "emails": emails}))
    got = json.loads(out)
    check("twenty long emails still fit, as valid JSON",
          len(out) <= AG._MAX_TOOL_CONTENT_CHARS and len(got["emails"]) == 20, len(out))
    check("every email keeps its sender, its start and its end",
          all(e["from"] == f"sender{i}@example.com" and e["body"].startswith(f"BEGIN{i}")
              and e["body"].endswith(f"END{i}") for i, e in enumerate(got["emails"])))


def t_a_huge_list_keeps_its_first_and_last_items():
    items = [f"item {i}" for i in range(5000)]
    out = AG._tool_content(_labelled({"ok": True, "files": items}))
    got = json.loads(out)
    check("a list of 5,000 short items is cut, as valid JSON",
          len(out) <= AG._MAX_TOOL_CONTENT_CHARS, len(out))
    check("its first and last items are kept, a marker between",
          got["files"][0] == "item 0" and got["files"][-1] == "item 4999"
          and any("more items left out" in str(x) for x in got["files"]), got["files"][:3])


def t_escapes_and_awkward_characters_stay_valid():
    text = ('"quoted" \\ back\\slash \n newline \t tab ' + "\u00e9\u4e2d\U0001F600") * 2000
    out = AG._tool_content(_labelled({"ok": True, "content": text}))
    check("quotes, backslashes, newlines and wide characters: still valid JSON, under the limit",
          len(out) <= AG._MAX_TOOL_CONTENT_CHARS and json.loads(out)["ok"] is True, len(out))


def t_what_cannot_be_shortened_falls_back_to_the_old_note():
    many_keys = _labelled({"ok": True, **{f"k{i:05d}": i for i in range(4000)}})
    out = AG._tool_content(many_keys)
    got = json.loads(out)
    check("thousands of tiny keys: the old short note, still valid JSON",
          got.get("truncated") is True and len(out) <= AG._MAX_TOOL_CONTENT_CHARS, out[:200])
    check("and the outside-text label is kept on it", got.get(AG.OUTSIDE_FIELD) == AG.OUTSIDE_LABEL)


def t_shortening_cannot_make_a_chat_marker():
    # took_in has already removed every marker; the cut adds a marker of its
    # own BETWEEN the two halves, so a half-marker at one edge can never meet
    # the other half.
    text = "x" * 1498 + "<|" + "y" * 20_000 + "im_start|>" + "z" * 1490
    out = AG._tool_content(_labelled({"ok": True, "content": text}))
    check("no chat marker appears where the text was cut",
          not AG._CHAT_MARKER.search(json.loads(out)["content"]))


def t_the_eval_sees_the_same_shortening():
    sys.path.insert(0, str(HERE.parent / "tools" / "tool_eval"))
    import ollama_tool_eval as E
    got = json.loads(E.outside({"ok": True, "content": "q" * 30_000 + "ANSWER"}))
    check("the tool test hands the model the same shortened result Jarvis does",
          "shortened" in got and got["content"].endswith("ANSWER"), str(got)[:200])


# --------------------------------------------------------------------------
#   2. Clearing older tool results in a long answer
# --------------------------------------------------------------------------

def _round(i, size):
    call = {"id": f"c{i}", "type": "function",
            "function": {"name": "file_read", "arguments": json.dumps({"path": f"f{i}"})}}
    return [{"role": "assistant", "content": f"reading part {i}", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": f"c{i}",
             "content": json.dumps(_labelled({"ok": True, "content": f"R{i} " + "r" * size}))}]


def _convo(rounds, size=6000):
    msgs = [{"role": "system", "content": "rules"},
            {"role": "user", "content": "an earlier question " + "u" * 3000},
            {"role": "assistant", "content": "an earlier answer"},
            {"role": "user", "content": "read these five files for me"}]
    for i in range(rounds):
        msgs += _round(i, size)
    return msgs


def t_under_half_nothing_changes():
    msgs = _convo(2, size=500)
    check("a conversation under half the room is left exactly as it is",
          AG.clear_old_tool_results(msgs, 16000) == msgs)


def t_past_half_older_results_are_cleared():
    msgs = _convo(5)
    before = json.dumps(msgs)
    out = AG.clear_old_tool_results(msgs, 12000)
    check("the input list is not changed", json.dumps(msgs) == before)
    tools = [i for i, m in enumerate(out) if m["role"] == "tool"]
    cleared = [i for i in tools if "cleared" in json.loads(out[i]["content"])]
    check("the two oldest of five results are cleared", cleared == tools[:2], (cleared, tools))
    check("the results after the last three assistant messages are whole",
          all(out[i] == msgs[i] for i in tools[2:]))
    stub = json.loads(out[tools[0]]["content"])
    check("a cleared result is valid JSON, keeps the outside-text label and its ok",
          stub == {AG.OUTSIDE_FIELD: AG.OUTSIDE_LABEL, "ok": True,
                   "cleared": AG.CLEARED_RESULT}, stub)
    check("it keeps its tool_call_id, so it still answers its call",
          out[tools[0]]["tool_call_id"] == msgs[tools[0]]["tool_call_id"])
    check("every user, assistant and system message is untouched",
          all(out[i] == m for i, m in enumerate(msgs) if m["role"] != "tool"))


def t_a_cleared_result_stays_cleared_the_same_way():
    four = AG.clear_old_tool_results(_convo(4), 12000)
    five = AG.clear_old_tool_results(_convo(5), 12000)
    # The prompt's start is what Ollama can reuse: everything the fourth
    # round sent up to its first whole result is the same in the fifth.
    first_whole = next(i for i, m in enumerate(four)
                       if m["role"] == "tool" and "cleared" not in json.loads(m["content"]))
    check("one more round clears more, but never changes what was already cleared",
          five[:first_whole] == four[:first_whole])


def t_too_few_assistant_messages_clears_nothing():
    msgs = [{"role": "user", "content": "go"}] + _round(0, 30_000)
    check("with fewer than three assistant messages, nothing is cleared",
          AG.clear_old_tool_results(msgs, 1000) == msgs)


def t_a_long_answer_sends_cleared_results_to_the_model():
    """End to end: six rounds of big reads on a small room - the last request
    the model gets has the older results cleared and the newest one whole."""
    real = AG.TOOLS["calculator"].execute
    n = {"i": 0}

    def big(args, state, **kw):
        n["i"] += 1
        return {"ok": True, "value": f"RESULT{n['i']} " + "v" * 6500}
    AG.TOOLS["calculator"].execute = big
    try:
        call = {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "1", "function": {"name": "calculator",
                                     "arguments": json.dumps({"expression": "1+1"})}}]}}]}
        answer = {"choices": [{"message": {"role": "assistant", "content": "All read."}}]}
        opener, calls = TA.scripted_stream([call] * 5 + [answer])
        with TA.NoRealIO():
            AG.run_local_turn([{"role": "user", "content": "work it out"}], "qwen3:8b",
                              ollama_url=URL, stream_out=lambda b: None, gate_check=TA.allow,
                              open_stream=opener, enabled_tools={"calculator"},
                              context_length=16384)
        last = calls[-1]["messages"]
        results = [m["content"] for m in last if m.get("role") == "tool"]
        check("all five results reach the last request", len(results) == 5, len(results))
        check("the older ones are cleared",
              sum(AG.CLEARED_RESULT in r for r in results) >= 1, [r[:60] for r in results])
        check("the newest one is whole", "RESULT5" in results[-1], results[-1][:60])
        check("the owner's words are in the last request, whole",
              any(m.get("role") == "user" and m.get("content") == "work it out" for m in last))
    finally:
        AG.TOOLS["calculator"].execute = real


# --------------------------------------------------------------------------
#   3. "I've done it" with nothing done
# --------------------------------------------------------------------------

CLAIMS = [
    "I've set a reminder for 7pm to take the bins out.",
    "Done - I've turned off the kitchen light.",
    "I have sent the email to Sam.",
    "Okay. I just added milk to your list.",
    "Done.",
    "I went ahead and scheduled it for Monday.",
    "I've called 911 for you, help is on the way.",
    "I have cancelled your dentist appointment.",
]
NOT_CLAIMS = [
    "Should I set a reminder for 7pm?",
    "If I set a reminder, it will ring at 7pm.",
    "I can't switch lights in this chat - no tools are on right now.",
    "I already set that one this morning.",
    "Got it, I'll remember that your sister likes jazz.",
    "I have not sent anything yet.",
    "Would you like me to add it to your list?",
    "Paris is the capital of France.",
]


def t_which_sentences_claim_an_action():
    for text in CLAIMS:
        check(f"a claim: {text!r}", CL.claims_done(text))
    for text in NOT_CLAIMS:
        check(f"not a claim: {text!r}", not CL.claims_done(text))


def t_what_backs_a_claim():
    ok_action = [{"tool": "set_reminder", "ran": True, "ok": True}]
    check("an action tool that returned ok backs the claim",
          not CL.unbacked_claim("I've set a reminder.", ok_action))
    check("a read-only tool does not",
          CL.unbacked_claim("I've set a reminder.", [{"tool": "calendar_read", "ran": True,
                                                       "ok": True}]))
    check("an action that was refused or failed does not",
          CL.unbacked_claim("I've sent it.", [{"tool": "send_email", "ran": False, "ok": False},
                                              {"tool": "home_control", "ran": True, "ok": False}]))
    check("a plug-in tool counts as an action (never a wrong 'nothing was done')",
          not CL.unbacked_claim("I've created it.", [{"tool": "mcp__x__make", "ran": True,
                                                       "ok": True}]))


def t_the_tool_test_uses_the_same_pattern():
    sys.path.insert(0, str(HERE.parent / "tools" / "tool_eval"))
    import behaviour_cases as BH
    check("behaviour_cases' pattern IS jarvis_claims' pattern", BH._CLAIMS_DONE is CL.CLAIMS_DONE)


def _turn(said, *, stream=True, spoken=False, tool_rounds=(), tools=None):
    responses = list(tool_rounds) + [
        {"choices": [{"message": {"role": "assistant", "content": said}}]}]
    opener, _calls = TA.scripted_stream(responses)
    post_calls = iter(responses)
    user = {"role": "user", "content": "please do it",
            "provenance": "voice" if spoken else "typed"}
    streamed = []
    kw = {"open_stream": opener} if stream else {"post": lambda u, p: next(post_calls)}
    with TA.NoRealIO():
        res = AG.run_local_turn([dict(user)], "qwen3:8b", ollama_url=URL,
                                stream_out=streamed.append, gate_check=TA.allow,
                                request={"messages": [user]}, stream=stream,
                                enabled_tools=tools if tools is not None else set(), **kw)
    return res, b"".join(streamed)


def t_a_false_claim_gets_the_line_at_the_end_of_the_stream():
    res, blob = _turn("I've set a reminder for 7pm to take the bins out.")
    text = TA.answer_text([blob])
    check("the app is sent the model's words, then the plain line",
          text.startswith("I've set a reminder") and text.endswith(CL.NOTHING_DONE_LINE), text)
    check("the line comes before the finish chunk and [DONE]",
          blob.rstrip().endswith(b"data: [DONE]")
          and blob.index(CL.NOTHING_DONE_LINE.encode()) < blob.index(b'"finish_reason":"stop"'))
    check("the turn's summary says so", res["claimed_undone"] is True
          and res["answer"].endswith(CL.NOTHING_DONE_LINE))


def t_a_false_claim_in_a_whole_answer():
    res, blob = _turn("Done - I've turned off the kitchen light.", stream=False)
    body = json.loads(blob)
    check("a non-streamed answer carries the line too",
          body["choices"][0]["message"]["content"].endswith(CL.NOTHING_DONE_LINE), body)


def t_a_voice_turn_says_it_without_brackets():
    res, blob = _turn("I've sent the email to Sam.", spoken=True)
    text = TA.answer_text([blob])
    check("a spoken answer gets the spoken line, which the apps read aloud",
          text.endswith(CL.NOTHING_DONE_SPOKEN) and "(" not in CL.NOTHING_DONE_SPOKEN, text)


def t_an_honest_answer_gets_no_line():
    res, blob = _turn("Should I set a reminder for 7pm?")
    check("a question is left alone", res["claimed_undone"] is False
          and CL.NOTHING_DONE_LINE not in res["answer"], res["answer"])


def t_a_real_action_gets_no_line():
    fake = types.ModuleType("jarvis_schedule")

    class _Sched:
        def mark_command(self, _text):
            pass
    fake.get = lambda: _Sched()
    real_mod = sys.modules.get("jarvis_schedule")
    real_run = AG._schedule_run
    sys.modules["jarvis_schedule"] = fake
    AG._schedule_run = lambda name, args, sched, now: {"ok": True, "said": "Added milk."}
    try:
        call = {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "1", "function": {"name": "todo_add",
                                     "arguments": json.dumps({"text": "milk"})}}]}}]}
        res, _blob = _turn("I've added milk to your list.", tool_rounds=[call],
                           tools={"todo_add"})
        check("after todo_add returned ok, 'I've added it' is left alone",
              res["claimed_undone"] is False and "todo_add" in res["tools_ran"], res)
    finally:
        AG._schedule_run = real_run
        if real_mod is None:
            sys.modules.pop("jarvis_schedule", None)
        else:
            sys.modules["jarvis_schedule"] = real_mod


def t_a_read_is_not_an_action():
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": 4}
    try:
        call = {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": "1", "function": {"name": "calculator",
                                     "arguments": json.dumps({"expression": "2+2"})}}]}}]}
        res, _blob = _turn("It's 4. I've scheduled your meeting too.", tool_rounds=[call],
                           tools={"calculator"})
        check("a claim after only a read-only tool still gets the line",
              res["claimed_undone"] is True, res["answer"])
    finally:
        AG.TOOLS["calculator"].execute = real


if __name__ == "__main__":
    for fn in (t_a_small_result_is_unchanged,
               t_one_long_text_keeps_its_start_and_end,
               t_many_long_texts_each_keep_both_ends,
               t_a_huge_list_keeps_its_first_and_last_items,
               t_escapes_and_awkward_characters_stay_valid,
               t_what_cannot_be_shortened_falls_back_to_the_old_note,
               t_shortening_cannot_make_a_chat_marker,
               t_the_eval_sees_the_same_shortening,
               t_under_half_nothing_changes,
               t_past_half_older_results_are_cleared,
               t_a_cleared_result_stays_cleared_the_same_way,
               t_too_few_assistant_messages_clears_nothing,
               t_a_long_answer_sends_cleared_results_to_the_model,
               t_which_sentences_claim_an_action,
               t_what_backs_a_claim,
               t_the_tool_test_uses_the_same_pattern,
               t_a_false_claim_gets_the_line_at_the_end_of_the_stream,
               t_a_false_claim_in_a_whole_answer,
               t_a_voice_turn_says_it_without_brackets,
               t_an_honest_answer_gets_no_line,
               t_a_real_action_gets_no_line,
               t_a_read_is_not_an_action):
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
