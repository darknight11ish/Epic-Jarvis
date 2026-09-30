"""jarvis_agent.py's wiring of jarvis_retirement.py into the `TOOLS` table as
`retirement_whatif` (the owner's decisions of 2026-09-30; docs/JARVIS-API.md
section 103.6): the chat door for the retirement what-if.

Every check drives the real `jarvis_agent.run_local_turn()` loop with a scripted
model, the way test_spending.py and test_agent_plan_wiring.py do.

What is proven here:
  - the answer is CODE-WRITTEN text only: the disclaimer is in it, and a
    sentence the model writes that round is dropped, never shown, never kept;
  - refused BEFORE anything is worked out after each kind of outside text
    (a reading tool ran, the conversation is tainted, a pasted or shared
    message, text the app added);
  - a missing number is asked for, never guessed; an unknown field is refused;
  - a spoken question gets one true line and the same written text, never
    read aloud (the tool is not on the read-aloud list);
  - the tool is invisible in the short list until its own group opens, and
    fits its token budget;
  - no card: decided under the calculator's action, not in NEEDS_A_PERSON;
  - the typed figures are in no step, no gate prompt or card, no log line and
    no chat record, and never reach the model as an answer;
  - a chat run and a form run cannot go at the same time (the shared lock).

    python3 test_agent_retirement_wiring.py
"""
import contextlib
import io
import json
import logging
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_retirement.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_agent as AG  # noqa: E402
import jarvis_retirement as R  # noqa: E402
from test_agent import NoRealIO, scripted_stream, answer_text, allow  # noqa: E402

AG._manner_now = lambda *a, **k: None
AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

FAILED, PASSED = [], []
MARK = 4567891          # a saving that must appear nowhere it should not


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def numbers(**kw):
    d = dict(current_age="40", retirement_age="65", savings=str(MARK), yearly_saving="12000",
             yearly_spending="30000")
    d.update(kw)
    return d


def call(name=AG.RETIREMENT_TOOL, **args):
    return {"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"id": "c1", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}


def say(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


TYPED = [{"role": "user", "content": "what if I retire at 65?", "provenance": "typed"}]
VOICE = [{"role": "user", "content": "what if I retire at 65", "provenance": "voice"}]


class Gate:
    """Records every decision it is asked for: (action, detail text, prompt)."""

    def __init__(self):
        self.asked = []

    def __call__(self, action, detail, prompt):
        self.asked.append((action, (detail or {}).get("text", ""), prompt))
        return allow(action, detail, prompt)


def turn(messages, responses, *, enabled=(AG.RETIREMENT_TOOL,), gate=None, short=False,
         cid="conv-ret", steps_out=None, stream=True):
    real_short = AG.short_list_on
    AG.short_list_on = lambda: short
    opener, calls = scripted_stream(responses)
    streamed = []
    try:
        with NoRealIO():
            out = AG.run_local_turn(
                messages, "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                stream_out=streamed.append, gate_check=gate or Gate(), open_stream=opener,
                enabled_tools=set(enabled), stream=stream,
                request={"conversation_id": cid, "messages": messages},
                record_chain=lambda s: None,
                on_step=(steps_out.append if steps_out is not None else (lambda s: None)),
                lane_choice=None)
    finally:
        AG.short_list_on = real_short
    return b"".join(streamed), out, calls


def words(stream: bytes) -> str:
    return answer_text([stream])


def tool_messages(calls):
    """What the model was handed back for its tool call, from the last request."""
    return [m["content"] for m in calls[-1]["messages"] if m.get("role") == "tool"]


def expected_text(**kw):
    return R.run(numbers(**kw))["text"]


# ------------------------------------------------------------------ 1. code-written text only

def t_the_answer_is_code_written_text():
    gate = Gate()
    steps = []
    invented = "About 99 of 100 futures are fine, so you can relax about money."
    stream, out, calls = turn(TYPED, [call(**numbers()), say(invented)], gate=gate, steps_out=steps)
    want = expected_text()
    check("the answer is exactly the what-if's own text", words(stream) == want, words(stream)[:200])
    check("... which ends with the disclaimer", words(stream).endswith(R.DISCLAIMER))
    check("the model's own sentence is nowhere in the stream or the kept answer",
          "relax" not in words(stream) and "relax" not in out["answer"] and out["answer"] == want)
    check("the kept answer for chat history is the code's text only", out["answer"] == want)
    seen = json.dumps(tool_messages(calls))
    check("the model was handed no figure and no summary, only 'shown on screen'",
          "shown_on_screen" in seen and "simulated futures" not in seen and "lasts to age" not in seen
          and R.DISCLAIMER not in seen and str(MARK) not in seen, seen[:300])
    check("... and told to write nothing more", "NOTHING more" in seen)
    check("the tool ran once, and was seen as a step", any(
        e.get("tool") == AG.RETIREMENT_TOOL and e.get("phase") == "tool_finished" and e.get("ok") is True
        for e in steps), steps)
    check("its run is NOT recorded as outside text in the chat record", out["tools_ran"] == [], out["tools_ran"])
    # the model says nothing at all: the text still comes
    stream, out, _c = turn(TYPED, [call(**numbers()), say("")])
    check("the model says nothing: the what-if's text still comes", words(stream) == want, words(stream)[:100])
    # a model that writes "done, I've set it up" is not shamed with the 'nothing done' line
    stream, out, _c = turn(TYPED, [call(**numbers()), say("Done. I've saved and set it all up for you.")])
    check("held model words do not trigger the 'nothing was done' line",
          words(stream) == want and "Nothing was actually done" not in words(stream), words(stream)[-120:])
    # stream:false shape
    stream, out, _c = turn(TYPED, [call(**numbers()), say(invented)], stream=False)
    obj = json.loads(stream)
    check("stream:false: the message content is the code's text",
          obj["choices"][0]["message"]["content"] == want, str(obj)[:200])
    # second run in one answer: the answer holds one text
    stream, out, _c = turn(TYPED, [call(**numbers()), call(**numbers(yearly_spending="20000")),
                                   say("ok")])
    check("two what-ifs in one answer: the first is kept, and nothing repeats",
          words(stream).count(R.DISCLAIMER) == 1, words(stream)[:80])


def t_no_card_and_a_calculator_gate():
    gate = Gate()
    stream, out, _c = turn(TYPED, [call(**numbers()), say("x")], gate=gate)
    check("the gate is asked once, under the calculator's action (tier auto, no card)",
          [a[0] for a in gate.asked] == ["calculator"], gate.asked)
    tool = AG.TOOLS[AG.RETIREMENT_TOOL]
    check("gate_lookup_name is the calculator's", tool.gate_lookup_name({}) == "calculator")
    check("it changes nothing and sends nothing: not in NEEDS_A_PERSON", AG.RETIREMENT_TOOL not in AG.NEEDS_A_PERSON)
    check("a plan step may not name it (its text would be lost)", AG._plan_step_excluded(AG.RETIREMENT_TOOL))
    check("its result is not outside text", AG.RETIREMENT_TOOL in AG._NOT_READING)
    import jarvis_claims
    import jarvis_reach
    check("a reading tool for the 'I have done it' check", AG.RETIREMENT_TOOL in jarvis_claims.READ_ONLY_TOOLS)
    check("a plain-English row on 'What asks first'", AG.RETIREMENT_TOOL in jarvis_reach.TOOL_NAMES)
    check("the tool's text comes from the module", tool.description == R.TOOL_DESCRIPTION
          and tool.parameters == R.tool_schema())


# ------------------------------------------------------------------ 2. refused after outside text

def t_refused_after_outside_text():
    conv = TYPED
    check("a clean typed turn: allowed", AG._retirement_refusal(AG._TurnWatch(conv, tainted=False)) == "")
    w = AG._TurnWatch(conv, tainted=False)
    w.took_in("email_check", {"ok": True, "text": "a mail"})
    check("a reading tool ran this turn: refused", AG._retirement_refusal(w) == AG.RETIREMENT_OUTSIDE)
    check("a conversation that read outside text before: refused",
          AG._retirement_refusal(AG._TurnWatch(conv, tainted=True)) == AG.RETIREMENT_OUTSIDE)
    for prov in ("pasted", "shared", "clipboard"):
        w = AG._TurnWatch([{"role": "user", "content": "x", "provenance": prov}], tainted=False)
        check(f"a {prov} message: refused", AG._retirement_refusal(w) == AG.RETIREMENT_OUTSIDE, w.provenance)
    with_app = conv + [{"role": "system", "content": "app text"}]
    w = AG._TurnWatch(with_app, request={"messages": with_app}, tainted=False)
    check("text the app added: refused", AG._retirement_refusal(w) == AG.RETIREMENT_OUTSIDE)
    w = AG._TurnWatch(conv, tainted=False)
    w.took_in("calculator", {"ok": True, "value": 4})
    check("the calculator (not outside text) does not block it", AG._retirement_refusal(w) == "")
    w.took_in(AG.RETIREMENT_TOOL, {"ok": True})
    check("its own earlier run does not block a second one", AG._retirement_refusal(w) == "")
    # through the whole loop: an email read first, then the what-if
    ran = []
    real_exec = AG.TOOLS["email_check"].execute
    real_run = R.run
    AG.TOOLS["email_check"].execute = lambda a, s, **k: {"ok": True, "emails": [{"subject": "hi"}]}
    R.run = lambda *a, **k: (ran.append(a), real_run(*a, **k))[1]
    try:
        stream, out, calls = turn(TYPED, [call("email_check"), call(**numbers()), say("I could not.")],
                                  enabled=(AG.RETIREMENT_TOOL, "email_check"))
    finally:
        AG.TOOLS["email_check"].execute = real_exec
        R.run = real_run
    check("after an email was read the what-if never ran; the model was told why; no text",
          ran == [] and R.DISCLAIMER not in words(stream)
          and "outside text shaped this answer" in json.dumps(calls[-1]["messages"]))
    ran.clear()
    R.run = lambda *a, **k: (ran.append(a), real_run(*a, **k))[1]
    try:
        pasted = [{"role": "user", "content": "retire at 65?", "provenance": "pasted"}]
        stream, out, calls = turn(pasted, [call(**numbers()), say("no")])
        check("a pasted message: never ran", ran == [] and R.DISCLAIMER not in words(stream))
    finally:
        R.run = real_run
    ran.clear()
    R.run = lambda *a, **k: (ran.append(a), real_run(*a, **k))[1]
    try:
        stream, out, calls = turn(TYPED + [{"role": "system", "content": "app text"}],
                                  [call(**numbers()), say("no")])
        check("text the app added: never ran", ran == [] and R.DISCLAIMER not in words(stream))
    finally:
        R.run = real_run


# ------------------------------------------------------------------ 3. missing and unknown

def t_missing_and_unknown_numbers():
    ran = []
    real_run = R.run
    R.run = lambda *a, **k: (ran.append(a), real_run(*a, **k))[1]
    try:
        args = numbers()
        del args["savings"]
        stream, out, calls = turn(TYPED, [call(**args), say("How much have you saved so far?")])
        msg = json.dumps(tool_messages(calls))
        check("a missing number is not run, and the model is told which one to ask for",
              ran == [] and "savings" in msg and "required" in msg, msg[:300])
        check("... so the owner is asked, and no what-if text appears",
              words(stream) == "How much have you saved so far?" and R.DISCLAIMER not in words(stream), words(stream))
        stream, out, calls = turn(TYPED, [call(**numbers(savings="   ")), say("How much have you saved?")])
        check("a blank number counts as missing", ran == [] and "required" in json.dumps(tool_messages(calls)))
        stream, out, calls = turn(TYPED, [call(**numbers(favourite_colour="blue")), say("sorry")])
        msg = json.dumps(tool_messages(calls))
        check("an unknown field is refused, not ignored", ran == [] and "favourite_colour" in msg
              and "not one of the arguments" in msg, msg[:300])
        # numbers written as bare JSON numbers are accepted (models often do that)
        bare = {"current_age": 40, "retirement_age": 65.0, "savings": 100000, "yearly_saving": 12000,
                "yearly_spending": 30000}
        stream, out, calls = turn(TYPED, [call(**bare), say("x")])
        check("bare JSON numbers (40, 65.0, 100000) are read as typed", ran and R.DISCLAIMER in words(stream), words(stream)[:80])
    finally:
        R.run = real_run
    # R's own 'missing' is what the tool says when the check above is passed by
    r = AG._run_retirement({"current_age": "40"}, None)
    check("the tool itself answers 'missing' (the model then asks; nothing guessed)",
          r["ok"] is False and r["error"] == "missing" and r["field"] in R.REQUIRED and "will not guess" in r["message"], r)
    r = AG._run_retirement(numbers(savings="lots"), None)
    check("a number that cannot be read: a plain error naming the field, with no figure",
          r["ok"] is False and r["error"] == "bad_number" and r["field"] == "savings" and "lots" not in json.dumps(r), r)
    r = AG._run_retirement(numbers(plan_to_age="60"), None)
    check("an age plan that makes no sense is refused in plain words", r["error"] == "plan_not_after", r)
    ok = AG._run_retirement(numbers(), None)
    check("a good run hands back the result under a private key, and no figure beside it",
          ok["ok"] and "_retirement_result" in ok and ok["shown_on_screen"] is True
          and "text" not in ok and "summary" not in ok, list(ok))


# ------------------------------------------------------------------ 4. a spoken question

def t_a_spoken_question():
    want = expected_text()
    invented = "It looks about 70 percent safe."
    stream, out, calls = turn(VOICE, [call(**numbers()), say(invented)])
    text = words(stream)
    check("a spoken question: one true line first, then the same written text",
          text == R.SPOKEN_LINE + "\n\n" + want, text[:200])
    check("... the model's own words are dropped", "70 percent" not in text and "70 percent" not in out["answer"])
    check("the spoken line says nothing about numbers and does not claim a form",
          not any(ch.isdigit() for ch in R.SPOKEN_LINE) and "Brain" not in R.SPOKEN_LINE
          and "written in this chat" in R.SPOKEN_LINE)
    import gen_private_aloud_cases as G
    check("read aloud: not on the read-aloud list, so a spoken answer stays on screen",
          AG.RETIREMENT_TOOL not in G.READ_ALOUD_TOOLS
          and G.is_private_tool_run({"phase": "tool_finished", "tool": AG.RETIREMENT_TOOL}))


# ------------------------------------------------------------------ 5. the short list

def t_the_short_list():
    enabled = {"calculator", AG.RETIREMENT_TOOL}
    check("not in the core", AG.RETIREMENT_TOOL not in AG.CORE_TOOLS)
    groups = [(g, m) for g, _w, m in AG.TOOL_GROUPS if AG.RETIREMENT_TOOL in m]
    check("in exactly one group, and that group has it alone", len(groups) == 1 and groups[0][1] == (AG.RETIREMENT_TOOL,),
          groups)
    check("its group is not the spending tool's (that group is dropped when no folder is listed)",
          groups[0][0] not in ([g for g, _w, m in AG.TOOL_GROUPS if "my_spending" in m]))
    check("with the short list on it is not offered until its group opens",
          AG.RETIREMENT_TOOL not in AG.tool_offer(enabled, (), short=True)
          and AG.RETIREMENT_TOOL in AG.tool_offer(enabled, (groups[0][0],), short=True)
          and AG.RETIREMENT_TOOL in AG.tool_offer(enabled, (), short=False))
    check("more_tools lists the group when the tool is on",
          groups[0][0] in AG.more_tools_groups(enabled, short=True))
    check("... and not when the tool is off", groups[0][0] not in AG.more_tools_groups({"calculator"}, short=True))
    # through the loop: the first round has no retirement tool; opening the group adds it
    real_short_list = AG.short_list_on
    AG.short_list_on = lambda: True
    try:
        opener, bodies = scripted_stream([
            {"choices": [{"message": {"role": "assistant", "tool_calls": [
                {"id": "m", "function": {"name": AG.MORE_TOOLS, "arguments": json.dumps({"group": groups[0][0]})}}]}}]},
            say("ok")])
        with NoRealIO():
            AG.run_local_turn(TYPED, "qwen3:8b", ollama_url="http://127.0.0.1:11434", stream_out=lambda b: None,
                              open_stream=opener, gate_check=Gate(), enabled_tools=enabled,
                              request={"conversation_id": "conv-short", "messages": TYPED},
                              record_chain=lambda s: None, on_step=lambda s: None, lane_choice=None)
    finally:
        AG.short_list_on = real_short_list
    names = [[t["function"]["name"] for t in b.get("tools") or []] for b in bodies]
    check("round 1 does not show it; round 2 (after more_tools) does",
          AG.RETIREMENT_TOOL not in names[0] and AG.RETIREMENT_TOOL in names[1], names)
    tokens = AG.estimate_tokens(AG.TOOLS[AG.RETIREMENT_TOOL].schema())
    check(f"the tool fits the per-tool token budget of 300 ({tokens})", tokens <= 300)
    every = set(AG.TOOLS) - {"browser_control"}
    check("more_tools itself still fits 300 tokens with its group in",
          AG.estimate_tokens(AG.more_tools_schema(AG.more_tools_groups(every, short=True))) <= 300)
    check("the tool is offered only when [tools].enabled names it",
          AG.RETIREMENT_TOOL not in AG.offered_tools({"calculator"}) and AG.RETIREMENT_TOOL in AG.offered_tools(enabled))


# ------------------------------------------------------------------ 6. no figures written down

def t_no_figures_are_written_down():
    gate = Gate()
    steps, events = [], []
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    announced = []
    buf, err_buf = io.StringIO(), io.StringIO()
    opener, calls = scripted_stream([call(**numbers()), say("ok")])
    streamed = []
    real_short = AG.short_list_on
    AG.short_list_on = lambda: False
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err_buf), NoRealIO():
            out = AG.run_local_turn(TYPED, "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                                    stream_out=streamed.append, gate_check=gate, open_stream=opener,
                                    enabled_tools={AG.RETIREMENT_TOOL}, announce=announced.append,
                                    request={"conversation_id": "conv-mark", "messages": TYPED},
                                    record_chain=steps.append, on_step=events.append, lane_choice=None)
    finally:
        AG.short_list_on = real_short
        root.removeHandler(handler)
        root.setLevel(old_level)
    marker = str(MARK)
    seen_gate = json.dumps(gate.asked)
    check("the gate (its card text and its audit prompt) holds none of the typed figures",
          marker not in seen_gate and "12000" not in seen_gate and "30000" not in seen_gate, seen_gate[:300])
    check("... its prompt is only the tool's name", gate.asked and gate.asked[0][2] == f"tool {AG.RETIREMENT_TOOL}",
          gate.asked)
    rec = json.dumps({"steps": steps, "events": events, "announced": announced,
                      "summary": {k: v for k, v in out.items() if k != "answer"}})
    check("no step, event, announcement or turn record holds a typed figure",
          marker not in rec and "12000" not in rec and "30000" not in rec, rec[:300])
    check("nothing printed and nothing logged",
          (buf.getvalue() + err_buf.getvalue() + log_stream.getvalue()) == "",
          (buf.getvalue() + err_buf.getvalue() + log_stream.getvalue())[:200])
    check("the kept answer has ranges only, never the saving that was typed",
          marker not in out["answer"] and out["answer"] == expected_text())
    check("the events name the tool but carry no arguments", events and all(
        set(e) <= {"phase", "tool", "ok", "round"} for e in events), events[:3])


# ------------------------------------------------------------------ 7. one run at a time

def t_chat_and_form_share_one_lock():
    R._RUN_LOCK.acquire()
    try:
        stream, out, calls = turn(TYPED, [call(**numbers()), say("Please try again in a moment.")])
        msg = json.dumps(tool_messages(calls))
    finally:
        R._RUN_LOCK.release()
    check("while the form's run is going the chat is told 'busy' and shows no what-if text",
          "busy" in msg and R.BUSY in msg and R.DISCLAIMER not in words(stream), msg[:300])
    check("... and its own words come through (nothing was held)", words(stream) == "Please try again in a moment.",
          words(stream))
    # a slow chat run: a form run started meanwhile is told to wait (429), the chat still finishes
    gate, results = threading.Event(), {}
    real_run = R.run

    def slow(*a, **k):
        gate.wait(5)
        return real_run(*a, **k)
    R.run = slow
    try:
        def chat():
            results["chat"] = turn(TYPED, [call(**numbers()), say("x")])
        t = threading.Thread(target=chat)
        t.start()
        time.sleep(0.4)
        code, body = R.handle_post(R.PATH_RUN, numbers())
        gate.set()
        t.join(10)
    finally:
        R.run = real_run
        gate.set()
    check("a form run during a chat run is told to wait (429 busy)", code == 429 and body["error"] == "busy", (code, body))
    check("... and the chat run still finished with its text",
          "chat" in results and R.DISCLAIMER in words(results["chat"][0]))
    check("the lock is free afterwards", R._RUN_LOCK.acquire(blocking=False))
    R._RUN_LOCK.release()


if __name__ == "__main__":
    for fn in (t_the_answer_is_code_written_text, t_no_card_and_a_calculator_gate,
               t_refused_after_outside_text, t_missing_and_unknown_numbers, t_a_spoken_question,
               t_the_short_list, t_no_figures_are_written_down, t_chat_and_form_share_one_lock):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", *FAILED, sep="\n  ")
        sys.exit(1)
