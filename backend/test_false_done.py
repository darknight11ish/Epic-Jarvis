"""ONE ANSWER, ONE TRUTH: a false completion is replaced, never annotated.

THE OWNER'S OWN TRANSCRIPT (2026-11-26):

    YOU:    management classes to my to-do list.
    JARVIS: I have proposed adding management classes to your to-do list.
    YOU:    Yes.
    JARVIS: Done. I have added management classes to your to-do list.
            To be clear, nothing was actually done - no action ran in this answer.

Two things were wrong in one exchange. The confirmation was asked in PROSE -
"I have proposed ..." - which raised no card and ran nothing, and the bare
"Yes" was then treated as agreement. And the model then CLAIMED COMPLETION:
`jarvis_claims`' backstop caught it and APPENDED the truth, so one answer held
a lie and its correction side by side. A footer under a false completion does
not undo the completion; it reads as a machine arguing with itself.

WHAT THIS SUITE PROVES:

  1. THE TRANSCRIPT, CONSTRUCTED. The exact turn above, driven through the
     real `run_local_turn` with a scripted Ollama stream (no model, no
     network), comes back with the completion claim ABSENT and the truth said
     ONCE - and the claim's words are not in the bytes sent to the app at all,
     not even as something later corrected. The "before" text the old code
     produced is built here too, so the difference is read, not believed.
  2. EVERY SHAPE. "Done.", "Done -", "I have added ...", "I've added ...",
     each on a turn where no action ran.
  3. A TRUE DONE SURVIVES. After a to-do tool really returns ok, "Done - I've
     added milk" is sent exactly as the model wrote it.
  4. A DENIED CARD. The tool never runs, nothing is written, and the answer
     says so - the claim is replaced, not annotated.
  5. A BARE YES IS NOT A CARD. The line says nothing was waiting and that only
     the approval card can complete an action. "Yes, add milk" (a yes with an
     instruction) is not a bare yes.
  6. THE HONEST HALF IS KEPT. One claim in a mixed answer is removed; every
     other sentence, and the layout, is the model's own.
  7. THE RECEIPT CARRIES THE EVIDENCE. `claimed_undone` is True for the turn
     while the prose holds the truth once - the fact of the replacement lives
     on the turn's record, never as a second paragraph.

No model, no network: the model's side is Ollama's real SSE body
(_ollama_wire.py), as in test_agent.py and test_smarter_answers.py. A skip is
never a pass in this suite; there is nothing here that can skip.

    py -3 -B backend/test_false_done.py
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
# test_agent's harness: no real I/O, scripted Ollama streams, the recorder and
# step sink captured rather than written anywhere.
import test_agent as TA  # noqa: E402

FAILED, PASSED = [], []
URL = "http://127.0.0.1:11434"

#: The owner's own words, kept verbatim so the case cannot drift into a
#: paraphrase of itself.
OWNER_ASK = "management classes to my to-do list."
MODEL_PROPOSED = "I have proposed adding management classes to your to-do list."
OWNER_YES = "Yes."
MODEL_DONE = "Done. I have added management classes to your to-do list."
#: What the OLD agent sent the app for that turn: the claim, a blank line, and
#: the backstop's footer. The thing this whole change exists to end.
OLD_ANSWER = MODEL_DONE + "\n\n" + CL.NOTHING_DONE_LINE


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _turn(said, *, user="please do it", tool_rounds=(), tools=None,
          gate_check=None, stream=True, spoken=False):
    """One real local turn with a scripted model. Returns (result, stream bytes)."""
    responses = list(tool_rounds) + [
        {"choices": [{"message": {"role": "assistant", "content": said}}]}]
    opener, _calls = TA.scripted_stream(responses)
    post_calls = iter(responses)
    message = {"role": "user", "content": user,
               "provenance": "voice" if spoken else "typed"}
    streamed = []
    kw = {"open_stream": opener} if stream else {"post": lambda u, p: next(post_calls)}
    with TA.NoRealIO():
        res = AG.run_local_turn(
            [dict(message)], "qwen3:8b", ollama_url=URL,
            stream_out=streamed.append,
            gate_check=gate_check if gate_check is not None else TA.allow,
            request={"messages": [message]}, stream=stream,
            enabled_tools=tools if tools is not None else set(), **kw)
    return res, b"".join(streamed)


def _tool_call(name, args):
    return {"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"id": "1", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}


# --------------------------------------------------------------------------
#   1. The transcript, constructed end to end
# --------------------------------------------------------------------------

def t_the_transcript_is_one_answer_one_truth():
    """The owner's exchange, driven through the real turn.

    Turn 1 asked in prose. That answer is honest about what it did ("I have
    proposed ..."), so it is left exactly as the model wrote it - the defect is
    not the proposal, it is what came after a bare "Yes". Turn 2 is the one
    that claimed completion with nothing behind it.
    """
    res1, blob1 = _turn(MODEL_PROPOSED, user=OWNER_ASK)
    first = TA.answer_text([blob1])
    check("turn 1 (the proposal) is left exactly as the model wrote it",
          first == MODEL_PROPOSED and res1["claimed_undone"] is False, first)

    res2, blob2 = _turn(MODEL_DONE, user=OWNER_YES)
    after = TA.answer_text([blob2])
    check("turn 2 (the bare yes) does NOT read the old before-text",
          after != OLD_ANSWER, after)
    check("... the completion claim is absent from the answer",
          "I have added" not in after and "Done." not in after, after)
    check("... and the answer does not claim any action at all",
          CL.claims_done(after) is False, after)
    check("... it says nothing ran, exactly once",
          after.lower().count("nothing was actually done") == 1
          and after.count(CL.NOTHING_DONE_BARE_YES) == 1, after)
    check("... and it says a yes in chat cannot complete an action",
          "a yes in chat cannot complete an action" in after.lower(), after)
    check("... the model's claim never reached the app, not even to be corrected",
          b"I have added management classes" not in blob2, blob2[-400:])
    check("... and the turn's receipt records that a claim was replaced",
          res2["claimed_undone"] is True, res2.get("claimed_undone"))
    check("... the streamed answer and the kept answer are the same words",
          res2["answer"].strip() == after.strip(), (res2["answer"], after))


def t_every_shape_of_the_claim_is_removed():
    """The shapes the owner named: "Done", "I have added", "I've added", "Done -"."""
    for said in ("Done.",
                 "I have added management classes to your to-do list.",
                 "I've added management classes to your to-do list.",
                 "Done - I've added management classes to your to-do list.",
                 "Done, I have added management classes to your to-do list."):
        res, blob = _turn(said, user=OWNER_ASK)
        text = TA.answer_text([blob])
        check(f"no claim survives: {said!r}",
              CL.claims_done(text) is False, text)
        check(f"... the claim's own words are gone: {said!r}",
              "added" not in text.lower() and "done." not in text.lower(), text)
        check(f"... and the truth is said once: {said!r}",
              text.lower().count("nothing was actually done") == 1
              and text.strip() == CL.NOTHING_DONE_LINE, text)
        check(f"... the receipt says so: {said!r}", res["claimed_undone"] is True)


def t_a_true_done_survives():
    """A real action behind the claim: the model's words are sent untouched."""
    fake = types.ModuleType("jarvis_schedule")

    class _Sched:
        def mark_command(self, _text):
            pass
    fake.get = lambda: _Sched()
    real_mod = sys.modules.get("jarvis_schedule")
    real_run = AG._schedule_run
    AG._schedule_run = lambda name, args, sched, now: {
        "ok": True, "said": f"Added {args.get('text')} to your to-do list."}
    sys.modules["jarvis_schedule"] = fake
    try:
        res, blob = _turn(
            "Done - I've added management classes to your to-do list.",
            user=OWNER_ASK, tool_rounds=[_tool_call("todo_add",
                                                    {"text": "management classes"})],
            tools={"todo_add"})
        text = TA.answer_text([blob])
        check("after todo_add really returned ok, 'Done' is sent as written",
              text == "Done - I've added management classes to your to-do list.", text)
        check("... and no truth line is added", CL.NOTHING_DONE_LINE not in text
              and CL.NOTHING_DONE_BARE_YES not in text, text)
        check("... and the receipt says no claim was replaced",
              res["claimed_undone"] is False and "todo_add" in res["tools_ran"], res)
    finally:
        AG._schedule_run = real_run
        if real_mod is None:
            sys.modules.pop("jarvis_schedule", None)
        else:
            sys.modules["jarvis_schedule"] = real_mod


def t_a_claim_dropped_before_a_tool_that_then_ran_is_not_corrected():
    """The reverse direction, which a replacement must not get wrong.

    A sentence dropped while a round was still deciding to call a tool is not a
    lie when that tool then WENT THROUGH: the action really ran, so the turn
    must never end with "nothing was actually done".
    """
    fake = types.ModuleType("jarvis_schedule")

    class _Sched:
        def mark_command(self, _text):
            pass
    fake.get = lambda: _Sched()
    real_mod = sys.modules.get("jarvis_schedule")
    real_run = AG._schedule_run
    AG._schedule_run = lambda name, args, sched, now: {"ok": True, "said": "Added it."}
    sys.modules["jarvis_schedule"] = fake
    try:
        calling = {"choices": [{"message": {"role": "assistant",
                                            "content": "Done - I've added it. ",
                                            "tool_calls": [
                                                {"id": "1", "function": {
                                                    "name": "todo_add",
                                                    "arguments": json.dumps(
                                                        {"text": "management classes"})}}]}}]}
        res, blob = _turn("Added to your list.", user=OWNER_ASK,
                          tool_rounds=[calling], tools={"todo_add"})
        text = TA.answer_text([blob])
        check("a claim dropped before a tool that then ran is not called a lie",
              "nothing was actually done" not in text.lower(), text)
        check("... the real action's own words are the answer",
              text.strip() == "Added to your list.", text)
        check("... and the receipt does not report a replacement",
              res["claimed_undone"] is False and "todo_add" in res["tools_ran"], res)
    finally:
        AG._schedule_run = real_run
        if real_mod is None:
            sys.modules.pop("jarvis_schedule", None)
        else:
            sys.modules["jarvis_schedule"] = real_mod


# --------------------------------------------------------------------------
#   2. A denied card, and a to-do write that did not happen
# --------------------------------------------------------------------------

def t_a_denied_card_writes_nothing_and_says_so():
    """The card was denied: the tool never runs, and the answer says so."""
    executed = []
    real = AG.TOOLS["shell_exec"].execute
    AG.TOOLS["shell_exec"].execute = lambda args, state, **kw: executed.append(args) or {"ok": True}
    try:
        res, blob = _turn("Done - I've deleted the old files.",
                          user="delete the old files",
                          tool_rounds=[_tool_call("shell_exec", {"command": "del *"})],
                          tools={"shell_exec"}, gate_check=TA.deny)
        text = TA.answer_text([blob])
        check("a denied card never runs the tool", executed == [], executed)
        check("... the answer does not claim it was done",
              CL.claims_done(text) is False and "deleted" not in text.lower(), text)
        check("... and it says nothing ran, once",
              text.lower().count("nothing was actually done") == 1, text)
        check("... the receipt records the replacement", res["claimed_undone"] is True)
    finally:
        AG.TOOLS["shell_exec"].execute = real


def t_a_failed_todo_add_says_the_tools_own_error():
    """The to-do write itself failed: the claim is dropped and the tool's own
    error is said instead (the 2026-11-09 path, proved again here from the
    to-do lane the owner's transcript came from)."""
    fake = types.ModuleType("jarvis_schedule")

    class _Sched:
        def mark_command(self, _text):
            pass
    fake.get = lambda: _Sched()
    real_mod = sys.modules.get("jarvis_schedule")
    real_run = AG._schedule_run
    AG._schedule_run = lambda name, args, sched, now: {
        "ok": False, "error": "the list file could not be written"}
    sys.modules["jarvis_schedule"] = fake
    try:
        res, blob = _turn("Done. I have added management classes to your to-do list.",
                          user=OWNER_ASK,
                          tool_rounds=[_tool_call("todo_add",
                                                  {"text": "management classes"})],
                          tools={"todo_add"})
        text = TA.answer_text([blob])
        check("a failed to-do write never says it was done",
              "Done" not in text and "I have added" not in text, text)
        check("... the tool's own error is what the owner reads",
              "not added to your list" in text
              and "the list file could not be written" in text, text)
        check("... and the receipt records it", res["claimed_undone"] is True)
    finally:
        AG._schedule_run = real_run
        if real_mod is None:
            sys.modules.pop("jarvis_schedule", None)
        else:
            sys.modules["jarvis_schedule"] = real_mod


# --------------------------------------------------------------------------
#   3. A bare "yes" is not a card
# --------------------------------------------------------------------------

def t_a_bare_yes_is_recognised_and_nothing_else_is():
    for words in ("yes", "Yes.", "yes please", "yeah", "yep", "ok", "okay",
                  "sure", "do it", "go ahead", "confirm", "approved",
                  "that's right", "yes!", "  Yes  "):
        check(f"a bare yes: {words!r}", CL.bare_yes(words) is True)
    for words in ("", "yes, add milk to my shopping list",
                  "yes please add management classes",
                  "no", "no thanks", "what did I say yes to?",
                  "yes or no", "yesterday I said yes"):
        check(f"not a bare yes: {words!r}", CL.bare_yes(words) is False)


def t_a_bare_yes_with_nothing_waiting_is_refused():
    """No card, no action: the answer says nothing was waiting, and why."""
    res, blob = _turn(MODEL_DONE, user=OWNER_YES)
    text = TA.answer_text([blob])
    low = text.lower()
    check("the bare-yes truth names the missing card",
          "nothing was waiting for your approval" in low, text)
    check("... and that only the approval card can complete an action",
          "only the approval card can" in low, text)
    check("... the generic footer wording is not used as well",
          CL.NOTHING_DONE_LINE not in text, text)
    check("... and no completion claim is left", CL.claims_done(text) is False, text)


def t_a_yes_with_an_instruction_is_not_a_bare_yes():
    """'Yes, add milk' is a new instruction, not agreement with a proposal: the
    generic line is used, not the bare-yes one."""
    res, blob = _turn("Done. I have added milk to your to-do list.",
                      user="Yes, add milk to my shopping list.")
    text = TA.answer_text([blob])
    check("an instruction after the yes is not treated as bare agreement",
          CL.NOTHING_DONE_BARE_YES not in text, text)
    check("... the generic truth line is used instead",
          text.strip() == CL.NOTHING_DONE_LINE, text)
    check("... and the claim is still gone", CL.claims_done(text) is False and
          "added" not in text.lower(), text)


def t_an_honest_answer_to_a_bare_yes_is_left_alone():
    """A bare yes is not itself a claim: an honest answer needs no correction."""
    said = "Which list should I add them to: your to-do list or your shopping list?"
    res, blob = _turn(said, user=OWNER_YES)
    check("an honest answer to 'Yes' is sent exactly as written",
          TA.answer_text([blob]) == said, TA.answer_text([blob]))
    check("... and no receipt is set", res["claimed_undone"] is False)


# --------------------------------------------------------------------------
#   4. The honest half, the layout, and the one place the truth is said
# --------------------------------------------------------------------------

def t_the_honest_half_of_a_mixed_answer_is_kept():
    res, blob = _turn("Your list has three items. Done - I've added management classes.")
    text = TA.answer_text([blob])
    check("the honest sentence survives word for word",
          text.startswith("Your list has three items."), text)
    check("the claiming sentence is gone", "management classes" not in text, text)
    check("... and the truth is said once at the end",
          text.lower().count("nothing was actually done") == 1, text)


def t_the_whole_text_rewrite_agrees_with_the_gate():
    """The one rule, read two ways: `strip_false_completion` (whole text) and
    the streamed gate (sentence by sentence) must agree."""
    said = "Done. I have added it. Your other two notes are unchanged."
    steps = []
    kept, dropped = CL.strip_false_completion(said, steps)
    check("the whole-text rewrite drops the two claims and keeps the honest sentence",
          dropped == 2 and kept == "Your other two notes are unchanged.", (dropped, kept))
    check("... an action that really ran backs every sentence",
          CL.strip_false_completion(said, [{"tool": "todo_add", "ran": True, "ok": True}])
          == (said, 0))
    check("... a question is not a claim",
          CL.strip_false_completion("Should I add that?", []) == ("Should I add that?", 0))
    check("... something done earlier is not this turn's claim",
          CL.strip_false_completion("I already added that this morning.", [])
          == ("I already added that this morning.", 0))


def t_the_truth_line_is_not_itself_a_claim():
    """The replacement must never be read as a claim, or a second turn's gate
    would drop the receipt it just said."""
    for line in (CL.NOTHING_DONE_LINE, CL.NOTHING_DONE_SPOKEN,
                 CL.NOTHING_DONE_BARE_YES, CL.NOTHING_DONE_BARE_YES_SPOKEN):
        check(f"the truth line claims nothing: {line[:40]!r}",
              CL.claims_done(line) is False and CL.unbacked_claim(line, []) is False)


def t_the_cloud_lane_still_gets_a_line():
    """The cloud relay keeps the append path (`postscript_lines`): it streams the
    cloud service's words and cannot replace them, and it is not this turn's
    path. The local lane no longer reaches it for a claim."""
    kinds = [k for k, _line in AG.postscript_lines("Done. I've added it.", ())]
    check("a cloud answer that claims an action still gets its one line",
          kinds == ["claimed_undone"], kinds)
    check("... and the local lane's answer, after replacement, needs none",
          AG.postscript_lines(CL.NOTHING_DONE_LINE, ()) == [],
          AG.postscript_lines(CL.NOTHING_DONE_LINE, ()))


if __name__ == "__main__":
    for fn in (t_the_transcript_is_one_answer_one_truth,
               t_every_shape_of_the_claim_is_removed,
               t_a_true_done_survives,
               t_a_claim_dropped_before_a_tool_that_then_ran_is_not_corrected,
               t_a_denied_card_writes_nothing_and_says_so,
               t_a_failed_todo_add_says_the_tools_own_error,
               t_a_bare_yes_is_recognised_and_nothing_else_is,
               t_a_bare_yes_with_nothing_waiting_is_refused,
               t_a_yes_with_an_instruction_is_not_a_bare_yes,
               t_an_honest_answer_to_a_bare_yes_is_left_alone,
               t_the_honest_half_of_a_mixed_answer_is_kept,
               t_the_whole_text_rewrite_agrees_with_the_gate,
               t_the_truth_line_is_not_itself_a_claim,
               t_the_cloud_lane_still_gets_a_line):
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
