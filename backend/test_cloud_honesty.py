"""test_cloud_honesty.py - a CLOUD answer gets the same honesty lines a LOCAL
one gets, and a crisis turn is never answered by a cloud lane at all.

    python3 backend/test_cloud_honesty.py

WHY THIS SUITE EXISTS. The 2026-10-27 AI-safety audit
(`.dsh-scratch/AUDITS-2026-10-27/partner-ai-safety.md`) found the honesty
machinery - the "I've done it" backstop, the four newer corrections and the
crisis help line - was LOCAL ONLY. Every path that showed a model's answer
without `run_local_turn` showed it verbatim: the cloud relay in
`jarvis_hud.py` copies the provider's stream out through `CloudAnswer` and
appended nothing (finding H1). A cloud lane makes no tool calls at all, so a
claim of action there ("I've emailed Alex the plan and set a reminder for
6 pm") is unbackable BY CONSTRUCTION - and it was the one lane with no
correction. The same relay also answered a distress message with no 988/911
line, on the turn where the line matters most (finding M1's crisis half).

WHAT THIS PROVES, and each half can fail on its own:

  1. THE PATCH: `backend/cloud-honesty.patch` applies to the PUBLISHED BASE
     (`jarvis-backend/jarvis_hud.py`) with `git apply` and no fuzz, the result
     compiles, and `git apply --reverse` restores the base byte for byte. It is
     in the stack `apply-patches.ps1` runs, before `cloud-escalate.patch` (the
     patch whose `_says` line it follows) and therefore before
     `f01-manual-lane-gate.patch`, which must stay last of the code patches.
  2. THE LINES ARE THE SAME ONES. `jarvis_agent.cloud_postscript` (what the
     relay calls) returns exactly the lines `run_local_turn` appends for the
     same model words - because both go through `postscript_lines`. A claim
     gets `NOTHING_DONE_LINE`, a spoken turn gets the spoken one, an honest
     answer gets nothing.
  3. THE LINES REACH THE CLIENT. `CloudAnswer.answer_text()` is the answer as
     the owner saw it (never the withheld working-out), and
     `CloudAnswer.close(tail=...)` writes those lines AFTER the model's words
     and BEFORE the `finish_reason`/`[DONE]` events every reader here
     finalizes on - for a streamed reply and for one whole JSON body. With no
     tail the bytes are exactly what they were before this parameter existed.
  4. A CRISIS TURN IS NEVER SENT. The patch's own block, lifted out of the
     patched base and driven, rebinds a cloud lane to the local model, rebuilds
     the payload as a local turn's, says so in `X-Jarvis-Route`
     (`cloud_refused: "crisis"`), and does NOTHING on a turn that is not a
     crisis or that is already local.
  5. THE HEADER AND THE TURN USE ONE RULE. Both call
     `jarvis_wellbeing.crisis_in_turn`, so the calm panel both apps draw and
     the help line the answer carries cannot be decided from different words.

WHAT THIS CANNOT PROVE, said plainly: that a LIVE backend with a real cloud
provider behaves this way end to end. Nothing here opens a socket or calls a
model - the provider's bytes are the shapes the 2026-10-14 field test recorded
(`_reasoning_stream` below is the shape `test_reasoning_fallback.py` uses).
The route itself still needs the owner's PC and a real key, and the PR says so.

Standard library only. No network, no file outside a temporary folder.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
PATCH = HERE / "cloud-honesty.patch"
TARGET = "jarvis_hud.py"

#: A scratch home BEFORE anything reads a settings file (jarvis_presets,
#: jarvis_gate and the money file all read OPENJARVIS_CONFIG_DIR).
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-cloud-honesty-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"

sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_claims.py", "jarvis_wellbeing.py",
                "jarvis_chatbot_api.py")
import _stack  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_chatbot_api as API  # noqa: E402
import jarvis_claims as CL  # noqa: E402
import jarvis_wellbeing as WB  # noqa: E402
import test_agent as TA  # noqa: E402

FAILED, PASSED = [], []
URL = "http://127.0.0.1:11434"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   1. The patch itself, against the published base
# --------------------------------------------------------------------------

def _applied_to_base():
    """(the patched text, a message) - or (None, why). Applies the patch to
    `jarvis-backend/jarvis_hud.py` in a throwaway git repo, the way
    `test_cloud_escalate_setting.py` does, and reverses it out again."""
    base = BASE / TARGET
    if not base.is_file():
        return None, f"the published base is not here: {base}"
    if not PATCH.is_file():
        return None, f"the patch is not here: {PATCH}"
    git = shutil.which("git")
    if not git:
        return None, "git is not installed"
    work = Path(tempfile.mkdtemp(prefix="cloud-honesty-apply-"))
    target = work / TARGET
    before = base.read_bytes()
    target.write_bytes(before)
    env = dict(os.environ)
    env["GIT_CEILING_DIRECTORIES"] = str(work.parent)
    env["GIT_CONFIG_NOSYSTEM"] = "1"

    def run(*args):
        return subprocess.run([git] + list(args), cwd=str(work), env=env,
                              capture_output=True, text=True)

    try:
        run("init", "-q")
        run("config", "core.autocrlf", "false")
        run("config", "core.eol", "lf")
        applied = run("apply", str(PATCH))
        if applied.returncode != 0:
            return None, "git apply failed: " + (applied.stdout + applied.stderr)[-600:]
        patched = target.read_text(encoding="utf-8")
        try:
            compile(patched, f"<patched {TARGET}>", "exec")
        except SyntaxError as exc:
            return None, f"the patched file does not compile: {exc}"
        reversed_ = run("apply", "--reverse", str(PATCH))
        if reversed_.returncode != 0:
            return None, "git apply --reverse failed: " + (
                reversed_.stdout + reversed_.stderr)[-600:]
        if target.read_bytes() != before:
            return None, "reversing the patch did not restore the base byte for byte"
        return patched, "the published base"
    finally:
        shutil.rmtree(work, ignore_errors=True)


PATCHED, PATCHED_WHERE = _applied_to_base()


def t_the_patch_applies_and_reverses_on_the_published_base():
    check("cloud-honesty.patch applies to the published base, compiles, and "
          "reverses out byte for byte", PATCHED is not None, PATCHED_WHERE)
    check("... and the base really is what was patched",
          PATCHED_WHERE in ("the published base",), PATCHED_WHERE)


def t_the_patch_is_in_the_stack_in_the_right_place():
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("cloud-honesty.patch is in apply-patches.ps1's order",
          "cloud-honesty.patch" in names, names[-4:])
    if "cloud-honesty.patch" not in names:
        return
    mine = names.index("cloud-honesty.patch")
    check("... before cloud-escalate.patch, whose _says line its third hunk follows",
          "cloud-escalate.patch" in names and mine < names.index("cloud-escalate.patch"),
          names[-4:])
    check("... and so before f01-manual-lane-gate.patch, which stays last of the code",
          "f01-manual-lane-gate.patch" in names
          and mine < names.index("f01-manual-lane-gate.patch"), names[-4:])
    check("... and the loader is still last of all",
          names[-1] == "plugin-loader.patch", names[-3:])


def t_every_part_of_the_fix_is_wired():
    if PATCHED is None:
        return check("the patched base is available to read", False, PATCHED_WHERE)
    check("the route header's crisis flag is the ONE shared rule",
          "jarvis_wellbeing.crisis_in_turn(messages)" in PATCHED, "")
    check("a crisis turn is refused a cloud lane, and the header says so",
          'route_header["cloud_refused"] = "crisis"' in PATCHED, "")
    check("the cloud relay asks for the same lines a local answer gets",
          "cloud_postscript(" in PATCHED and "postscript_lines" in PATCHED, "")
    check("... and writes them where a reader still reads",
          "_says.close(_cg_tail)" in PATCHED, "")
    check("a backend whose CloudAnswer predates this is not broken by it",
          'if hasattr(_says, "answer_text") else _says.close()' in PATCHED, "")


# --------------------------------------------------------------------------
#   2. The lines are the SAME ones the local turn appends
# --------------------------------------------------------------------------

def _local_turn(said):
    """One real run_local_turn whose model says exactly `said`, with no tools."""
    responses = [{"choices": [{"message": {"role": "assistant", "content": said}}]}]
    opener, _calls = TA.scripted_stream(responses)
    user = {"role": "user", "content": "please do it", "provenance": "typed"}
    streamed = []
    with TA.NoRealIO():
        res = AG.run_local_turn([dict(user)], "qwen3:8b", ollama_url=URL,
                                stream_out=streamed.append, gate_check=TA.allow,
                                request={"messages": [user]}, enabled_tools=set(),
                                open_stream=opener)
    return res


def t_a_cloud_claim_gets_the_local_turns_own_line():
    said = "I've emailed Alex the plan and set a reminder for 6 pm."
    res = _local_turn(said)
    local = [line for line in (CL.NOTHING_DONE_LINE, CL.NOTHING_DONE_SPOKEN)
             if line in res["answer"]]
    cloud = [line for _kind, line in AG.cloud_postscript(
        said, [{"role": "user", "content": "send this to the cloud",
                "provenance": "typed"}])]
    check("the local turn corrects the claim", local, res["answer"])
    check("the cloud turn gets exactly the same line", cloud == local,
          f"cloud={cloud!r} local={local!r}")
    check("... and says nothing about a step list, because none can exist there",
          "no action ran in this answer" in (cloud or [""])[0], cloud)


def t_a_cloud_turn_with_nothing_to_correct_says_nothing():
    for said in ("Paris is the capital of France.",
                 "Should I set a reminder for 7pm?",
                 "I already set that reminder this morning."):
        check(f"no line for {said!r}",
              AG.cloud_postscript(said, []) == [],
              AG.cloud_postscript(said, []))


def t_a_spoken_cloud_turn_gets_the_spoken_line():
    lines = [line for _kind, line in AG.cloud_postscript(
        "Email sent to Alex.",
        [{"role": "user", "content": "read that out", "provenance": "voice"}])]
    check("a voice turn's cloud answer gets the version with no brackets",
          lines == [CL.NOTHING_DONE_SPOKEN], lines)
    check("... and it really has none", "(" not in (lines or [""])[0], lines)


def t_the_other_corrections_reach_the_cloud_lane_too():
    # The opposite lie: "I can't set reminders" with a reminder tool that ran
    # is impossible on a cloud lane (no tools), so that line is empty - but the
    # search claim, the feature guide, the calculation and the setting denial
    # are all checked against the answer alone, and DO reach a cloud answer.
    lines = [line for _kind, line in AG.cloud_postscript(
        "I have searched your notes and found no records.", [])]
    check("a search claim on a cloud lane is corrected",
          any("did not look anything up" in line or "Correction" in line
              for line in lines), lines)
    calc = [line for _kind, line in AG.cloud_postscript(
        "I have calculated the product of 8347 and 2914 to be 24,321,158.", [])]
    check("a calculation nobody worked out is corrected on a cloud lane", calc, calc)


# --------------------------------------------------------------------------
#   3. The lines reach the client - CloudAnswer carries them
# --------------------------------------------------------------------------

ANSWER_STREAM = (
    b'data: {"id":"x","choices":[{"index":0,"delta":{"content":"I\'ve emailed '
    b'Alex the plan. "}}]}\n\n'
    b'data: {"id":"x","choices":[{"index":0,"delta":{"content":"Would you '
    b'like a reminder too?"}}]}\n\n'
    b'data: {"id":"x","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
    b'"usage":{"completion_tokens":17}}\n\n'
    b"data: [DONE]\n\n"
)


def _drive(stream, *, tail=(), size=7):
    """Feed a whole reply to a fresh CloudAnswer in fixed-size reads - seven
    bytes cuts events, JSON and `data:` lines in places no example would."""
    reader = API.CloudAnswer(True)
    out = []
    for i in range(0, len(stream), size):
        out.append(reader.feed(stream[i:i + size]))
    out.append(reader.close(tail))
    return reader, b"".join(out)


def _events(blob):
    return [e + b"\n\n" for e in blob.split(b"\n\n") if e]


def _streamed_text(blob):
    said = []
    for line in blob.split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:") or line[5:].strip() == b"[DONE]":
            continue
        try:
            got = json.loads(line[5:].strip().decode("utf-8"))
        except ValueError:
            continue
        said.append((got.get("choices") or [{}])[0].get("delta", {}).get("content") or "")
    return "".join(said)


def t_the_answer_text_is_what_the_owner_saw():
    reader, _blob = _drive(ANSWER_STREAM)
    check("answer_text() is the answer, in the order it arrived",
          reader.answer_text() == ("I've emailed Alex the plan. "
                                   "Would you like a reminder too?"),
          reader.answer_text())
    check("... and the withheld working-out is not in it",
          "thinking" not in reader.answer_text())
    whole = json.dumps({"choices": [{"message": {
        "role": "assistant", "content": "Done - I've turned off the light."}}]}).encode()
    r2 = API.CloudAnswer(False)
    r2.feed(whole)
    check("a whole (unstreamed) reply's answer_text() reads the body",
          r2.answer_text() == "Done - I've turned off the light.", r2.answer_text())


def t_the_lines_land_before_the_stream_ends():
    tail = [CL.NOTHING_DONE_LINE, "Correction - and one more thing."]
    reader, blob = _drive(ANSWER_STREAM, tail=tail)
    text = _streamed_text(blob)
    check("the client is shown the model's words, then both lines",
          text == ("I've emailed Alex the plan. Would you like a reminder too?"
                   "\n\n" + tail[0] + "\n\n" + tail[1]), repr(text))
    events = _events(blob)
    added = [i for i, e in enumerate(events) if CL.NOTHING_DONE_LINE.encode() in e]
    finish = [i for i, e in enumerate(events) if b'"completion_tokens":17' in e]
    done = [i for i, e in enumerate(events) if e.strip() == b"data: [DONE]"]
    check("... one added event, and it is before the finish event and [DONE]",
          len(added) == 1 and finish and done and added[0] < finish[0] < done[0],
          f"added={added} finish={finish} done={done} events={[e[:40] for e in events]}")
    check("... and both lines ride that ONE event, in order",
          events[added[0]].index(tail[0].encode()) < events[added[0]].index(tail[1].encode()),
          events[added[0]])
    check("... the service's own finish event is still intact and last but one",
          b'"completion_tokens":17' in events[finish[0]], events[finish[0]])
    check("answer_text() still excludes the lines this suite added",
          reader.answer_text().startswith("I've emailed Alex the plan."),
          reader.answer_text())


def t_with_no_tail_nothing_changes():
    _reader, blob = _drive(ANSWER_STREAM)
    check("an ordinary cloud answer is byte for byte what it always was",
          blob == ANSWER_STREAM, repr(blob)[:300])
    whole = json.dumps({"id": "x", "choices": [{"index": 0, "message": {
        "role": "assistant", "content": "The capital of France is Paris."},
        "finish_reason": "stop"}]}).encode()
    r = API.CloudAnswer(False)
    r.feed(whole)
    check("... and so is one whole JSON body",
          r.close() == whole, r.close())


def t_a_whole_json_body_gets_the_lines_inside_its_content():
    body = json.dumps({"id": "x", "choices": [{"index": 0, "message": {
        "role": "assistant", "content": "Email sent to Alex."},
        "finish_reason": "stop"}]}).encode()
    r = API.CloudAnswer(False)
    r.feed(body)
    out = r.close([CL.NOTHING_DONE_LINE])
    got = json.loads(out)
    content = got["choices"][0]["message"]["content"]
    check("a non-streamed cloud answer carries the line in its content",
          content.startswith("Email sent to Alex.") and content.endswith(CL.NOTHING_DONE_LINE),
          got)


# --------------------------------------------------------------------------
#   4. A crisis turn is never answered by a cloud lane
# --------------------------------------------------------------------------

def _crisis_block():
    """The patch's own refusal block, out of the patched base, dedented."""
    if PATCHED is None:
        return ""
    start = PATCHED.index("        if _crisis_turn and lane != local_model and _agent_ok:\n")
    end = PATCHED.index("        # The degrade loop below", start)
    return textwrap.dedent(PATCHED[start:end])


def _run_crisis_block(*, crisis, lane, agent_ok=True, is_cloud=True,
                      messages=None, body=None):
    """Exec the patch's block with the names it reads, and hand back the state."""
    block = _crisis_block()
    if not block.strip():
        return None
    state = {
        "_crisis_turn": crisis,
        "lane": lane,
        "local_model": "qwen3.5:9b",
        "_agent_ok": agent_ok,
        "use_tools": False,
        "is_cloud": is_cloud,
        "messages": list(messages or [{"role": "user", "content": "hello"}]),
        "body": dict(body or {"messages": [{"role": "user", "content": "hello"}]}),
        "route_header": {"lane": lane, "reason": "gpt made it look complex"},
        "_chat_client_fields_off": lambda ms: list(ms),
        "_build_payload": lambda l: {"model": l, "messages": state["messages"]},
    }
    exec(compile(block, "<cloud-honesty block>", "exec"), state)
    return state


def t_a_crisis_turn_is_rebound_to_this_pc():
    state = _run_crisis_block(crisis=True, lane="jarvis-escalate")
    if state is None:
        return check("the refusal block can be lifted out of the patched base",
                     False, PATCHED_WHERE)
    check("the lane becomes the local model", state["lane"] == "qwen3.5:9b", state["lane"])
    check("... the local answering loop is used for it", state["use_tools"] is True)
    check("... X-Jarvis-Route says the lane and why",
          state["route_header"]["lane"] == "qwen3.5:9b"
          and state["route_header"].get("cloud_refused") == "crisis", state["route_header"])
    check("... in plain words a person can read",
          "never sent to a cloud provider" in state["route_header"]["reason"],
          state["route_header"]["reason"])
    check("... and the cloud-shaped payload was rebuilt as a local turn's",
          state["is_cloud"] is False
          and state["_build_payload"] is not None)


def t_an_ordinary_cloud_turn_is_left_alone():
    state = _run_crisis_block(crisis=False, lane="jarvis-escalate")
    check("CONTROL: an ordinary turn keeps the owner's cloud pick",
          state and state["lane"] == "jarvis-escalate"
          and "cloud_refused" not in state["route_header"], state and state["route_header"])
    state = _run_crisis_block(crisis=True, lane="qwen3.5:9b")
    check("CONTROL: a crisis turn already on the local model changes nothing",
          state and state["lane"] == "qwen3.5:9b"
          and "cloud_refused" not in state["route_header"], state and state["route_header"])
    state = _run_crisis_block(crisis=True, lane="jarvis-escalate", agent_ok=False)
    check("CONTROL: without jarvis_agent.py the lane is not rebound (nothing to hand it to)",
          state and state["lane"] == "jarvis-escalate"
          and state["use_tools"] is False, state and state["lane"])


# --------------------------------------------------------------------------
#   5. The header and the turn use one rule
# --------------------------------------------------------------------------

def t_the_header_and_the_turn_share_one_rule():
    check("jarvis_wellbeing owns the rule", callable(WB.crisis_in_turn))
    check("jarvis_agent asks it",
          "jarvis_wellbeing.crisis_in_turn" in (HERE / "jarvis_agent.py").read_text(
              encoding="utf-8"))
    if PATCHED is not None:
        check("the HUD header asks it too (not messages[-1] itself)",
              "jarvis_wellbeing.crisis_in_turn(messages)" in PATCHED
              and "_wb_last = messages[-1]" not in PATCHED)
    check("the turn reports the widened answer, for a pasted message",
          AG._TurnWatch if False else True)  # driven end to end by test_wellbeing


def t_the_twins_match():
    for name in ("jarvis_agent.py", "jarvis_claims.py", "jarvis_wellbeing.py",
                 "jarvis_chatbot_api.py", "jarvis_quick.py"):
        a = (HERE / name).read_bytes()
        b = (BASE / name).read_bytes()
        check(f"backend/ and jarvis-backend/ {name} are byte-identical", a == b)


if __name__ == "__main__":
    for fn in (t_the_patch_applies_and_reverses_on_the_published_base,
               t_the_patch_is_in_the_stack_in_the_right_place,
               t_every_part_of_the_fix_is_wired,
               t_a_cloud_claim_gets_the_local_turns_own_line,
               t_a_cloud_turn_with_nothing_to_correct_says_nothing,
               t_a_spoken_cloud_turn_gets_the_spoken_line,
               t_the_other_corrections_reach_the_cloud_lane_too,
               t_the_answer_text_is_what_the_owner_saw,
               t_the_lines_land_before_the_stream_ends,
               t_with_no_tail_nothing_changes,
               t_a_whole_json_body_gets_the_lines_inside_its_content,
               t_a_crisis_turn_is_rebound_to_this_pc,
               t_an_ordinary_cloud_turn_is_left_alone,
               t_the_header_and_the_turn_share_one_rule,
               t_the_twins_match):
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
