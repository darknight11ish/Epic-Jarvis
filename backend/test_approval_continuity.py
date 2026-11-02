"""An approved card is not lost when the app's stream dies while it waits.

THE BUG (owner-reported, 2026-11-01: "approved card, then Jarvis forgets my
question"). Measured on his own run, 15:44-15:47, and written up in
`.dsh-scratch/APPROVAL-CONTINUITY-2026-11-01/EVIDENCE.md`:

    15:43:59  route turns=7          the question
    15:44:03  gate.asked             a search card
    15:44:17  gate.approved by=phone the owner's tap
    15:44:21  agent.chain web_search ran=true ok=true     the tool ran
    15:44:21  route turns=7          the app re-sent the SAME conversation, 91 ms later
    15:44:25  SPEED rounds=1 tokens=17 tools=False       one round, no tool, 17 tokens

"Approved. Carrying on." is the app's own fixed sentence for a real yes
(jarvis_card_words.VOICE), never the model's - so hearing it proves only that
the gate recorded the tap. What happened next is the bug: the turn found
`out.gone` AFTER the gate said yes, refused to run the tool (no one was there
to read it), unwound through ClientGone - and nothing on this PC remembered the
yes when the app re-sent the same conversation. `jarvis_gate.decide()` had
already consumed the tap and NULLed the card's prompt and detail, so the new
turn started from nothing: no tool, one round, a short answer. The tap was
used, the action dropped, the question forgotten.

WHAT THESE CHECKS PROVE (jarvis_agent.py, "An approved step the answer never
delivered", 2026-11-01):

  1. a card approved while the stream was dead is kept as an owed step, and is
     run at the START of the next turn for the SAME conversation, through the
     same prepare()/gate/execute() contract - so its result is in the context
     the model answers from, and the answer the owner gets is the one his tap
     was for;
  2. the gate is NOT asked a second time for that same approval (one card per
     action, and this action already has its yes), and nothing new is
     auto-approved;
  3. a denied, timed-out, expired or card-less call is never carried, and a
     request with no conversation id carries nothing (fail closed);
  4. a second re-send does not run it twice, and it never crosses into another
     conversation or outlives OWED_TTL_SECONDS;
  5. a carried step that fails says so in code's own words, and never claims it
     ran;
  6. the record and the replay are in the audit log, names and ids only - the
     card's words and the owner's question are not in it;
  7. THE YES IS RE-MADE AT REPLAY TIME, against the gate's CURRENT decision: a
     Stop everything pressed after the approval, a crisis turn in the same
     conversation after it, the tool switched off, or its action now at tier
     "never" all DROP the step (agent.owed_dropped) instead of running it -
     nothing the gate would now refuse is ever run, and no second card is
     raised to ask again;
  8. THE REPORTED SEAM IS DRIVEN END TO END (`run_local_turn`, not its pieces):
     an approved web_search whose card turn died with the app's stream really
     runs on the next turn, once, its result is in the first round of the
     answering turn, and a second re-sent turn runs nothing;
  9. a picture-lane turn and a turn whose model cannot use tools run no tool,
     so they leave the step owed rather than spending it; and a replay that
     raises after its tool-call message was appended leaves a result beside it,
     never a tool call with no answer.

The model's side of every turn is Ollama's real /v1/chat/completions stream
(_ollama_wire.py). Nothing here opens a socket, needs a phone, or touches the
owner's own state: the config folder, the audit log and HOME are throwaway
folders for this process.

    python3 test_approval_continuity.py
"""
import atexit
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# THIS SUITE'S OWN EMPTY CONFIG FOLDER AND AUDIT LOG, made before any module of
# the product is imported (so none of them can resolve ~/.openjarvis first) -
# the same shape test_agent.py and test_schedule.py use. Two reasons, and the
# second is not optional:
#   * the owner's switches (the data sandbox, the cloud preset) otherwise add
#     tools and prompt lines to the requests this suite measures;
#   * `jarvus_framework.audit_log` writes to the REAL ~/.openjarvis/logs unless
#     JARVIS_LOG_DIR moves it - the leak that put 191 synthetic gate.asked lines
#     in the owner's own log on 2026-10-20. One check below reads the audit file
#     this suite wrote, so it must be this suite's own.
_CFG = tempfile.TemporaryDirectory(prefix="jarvis-owed-cfg-")
_LOG = tempfile.TemporaryDirectory(prefix="jarvis-owed-log-")
_HOME = tempfile.TemporaryDirectory(prefix="jarvis-owed-home-")
_SAVED = {k: os.environ.get(k) for k in
          ("OPENJARVIS_CONFIG_DIR", "JARVIS_LOG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME")}
os.environ["OPENJARVIS_CONFIG_DIR"] = _CFG.name
os.environ["JARVIS_LOG_DIR"] = _LOG.name
os.environ["OPENJARVIS_HOME"] = _HOME.name
os.environ["JARVIS_HOME"] = _HOME.name


def _restore_env():
    for key, was in _SAVED.items():
        if was is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = was
    for folder in (_CFG, _LOG, _HOME):
        folder.cleanup()


atexit.register(_restore_env)

# On a real install (JARVIS_BACKEND set), the backend's own copy must be there
# and be this one - see _where.require_shipped.
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
import jarvis_agent as AG  # noqa: E402
import _ollama_wire as W  # noqa: E402

# The owner's own settings must not reach these requests: the manner line and
# the model/preset knowledge line are this PC's state, and are pinned by their
# own suites (test_manner.py, test_model_self_knowledge.py).
AG._manner_now = lambda *a, **k: None
try:
    import jarvis_model_knowledge as _model_knowledge
    _model_knowledge.prompt_line = lambda: ""
except Exception:
    pass
# Every turn would otherwise reach the default end-of-turn recorder (which
# writes the real audit log and may raise a real skill card) and the default
# step sink (the event bus). Captured here instead, for every turn in the file.
RECORDED = []
AG._record_chain = RECORDED.append
AG._publish_step = lambda step: None

FAILED, PASSED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The stand-ins: a gate with real card ids, and Ollama's own wire format
# --------------------------------------------------------------------------

class _Verdict:
    """What jarvis_gate.check() really returns for one card, as far as anything
    downstream reads it: allowed / outcome / tier / action / request_id."""

    def __init__(self, allowed, outcome, card, action):
        self.allowed = allowed
        self.outcome = outcome           # gate-outcome.patch: "approved", "denied"...
        self.tier = "ask"
        self.request_id = card           # the approval card's own id
        self.action = action
        self.reason = "" if allowed else "denied by the owner"


class Gate:
    """A gate that answers one card per call, with a real card id, and
    remembers every action it was asked about.

    `outcome` is the gate-outcome word: "approved" (a person's tap),
    "denied" (a person said no), "timed_out" (nobody answered) or "notify"
    (no person was asked at all - the tier said so)."""

    def __init__(self, outcome="approved", wait=0.0):
        self.outcome = outcome
        self.wait = wait
        self.asked = []                  # [(action, card id)] in order

    def __call__(self, action, detail, prompt):
        card = f"card{len(self.asked) + 1}-0f1e2d3c"
        self.asked.append((action, card))
        # A REAL gate waits for the person, and that wait is what lets the
        # stream die before the answer can be written - the measured timeline.
        time.sleep(self.wait)
        return _Verdict(self.outcome == "approved", self.outcome, card, action)


def calc_call(expr="2+2"):
    """One model round that asks for the calculator, in Ollama's own
    tool_calls delta shape."""
    return ("tool_calls", [{"name": "calculator", "arguments": {"expression": expr}}])


def search_call(query="what is new on the graphics card?"):
    """One model round that asks for a web search - the call the owner's own
    measured run lost."""
    return ("tool_calls", [{"name": "web_search", "arguments": {"query": query}}])


def _press_stop_all():
    """Press Stop everything for real, without touching a real task: the same
    jarvis_stop_all.stop_all() the route calls, with a stand-in task list."""
    import jarvis_stop_all as SA

    class NoTask:
        def running(self):
            return []

        def handle_post(self, *a, **k):
            return (409, {})

    SA.stop_all(by="test", task_control=NoTask())
    return SA


def opener_for(*bodies):
    """Each model request gets the next body: a list of stream events, in
    Ollama's real format (_ollama_wire.py)."""
    it = iter(bodies)
    calls = []

    def opener(url, payload):
        calls.append(payload)
        return W.FakeResponse(W.stream(next(it)))
    return opener, calls


def messages_of(calls, index=0):
    return list((calls[index] or {}).get("messages") or [])


def tool_messages(calls, index=0):
    return [m for m in messages_of(calls, index) if m.get("role") == "tool"]


def assistant_calls(calls, index=0):
    return [m for m in messages_of(calls, index)
            if m.get("role") == "assistant" and m.get("tool_calls")]


def audit_lines():
    """Every audit line this process wrote, from the folder JARVIS_LOG_DIR
    points at (never the owner's)."""
    out = []
    for path in sorted(Path(_LOG.name).glob("jarvis-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


CONV = "conv-approval-0001"      # what the phone sends; _CID_OK allows it


def _turn(events, *, answer=None, conversation_id=CONV, gate=None, stream_out=None,
          status_delay=0.02, enabled_tools=("calculator",), request=None,
          private=False, announce=None, lane=None):
    """One local turn. Its model answers with `events`; `answer` is a second
    round, for the cases where the turn goes on after a refusal. The calculator
    counts its own runs."""
    bodies = [list(events)] + ([list(answer)] if answer else [])
    opener, calls = opener_for(*bodies)
    body = {"conversation_id": conversation_id} if conversation_id else {}
    body.update(request or {})
    summary = AG.run_local_turn(
        [{"role": "user", "content": "how many is 2+2?"}], "jarvis-primary",
        ollama_url="http://127.0.0.1:11434",
        stream_out=stream_out if stream_out is not None else (lambda b: None),
        open_stream=opener,
        enabled_tools=set(enabled_tools),
        gate_check=gate if gate is not None else Gate(),
        keepalive_seconds=1000, status_delay=status_delay,
        context_length=16384, request=body, private=private,
        announce=announce, record_chain=lambda s: None,
        lane_choice=lane if lane is not None else "auto")
    return summary, calls


def _dead_stream_after_the_card():
    """A stream_out that works until the card has been announced, then fails
    every write - a socket nobody is reading any more, which is what the phone
    gave up on while the card waited (the measured 15:44 timeline).

    "Every write after the FIRST fails" would make the outcome depend on how
    fast the machine gets through the model round (the heartbeat's own
    keepalive is a write); dying at the card instead makes the named scenario
    happen on any machine. test_chat_stream.py's own test carries the same
    note, and this is the same stand-in."""
    card = []
    writes = []

    def stream_out(data):
        writes.append(data)
        if card:
            raise BrokenPipeError(32, "Broken pipe")
        if b"jarvis-status approval" in data:
            card.append(data)
    stream_out.writes = writes
    return stream_out


def _count_runs(store):
    """Replace the calculator's execute() with one that counts its runs and
    returns a marker a check can recognise in the model's context."""
    real = AG.TOOLS["calculator"].execute

    def counted(args, state, **kw):
        store.append(args)
        return {"ok": True, "value": 4}
    AG.TOOLS["calculator"].execute = counted
    return real


# --------------------------------------------------------------------------
#   1. The bug itself: an approved step lost with the stream is not lost
# --------------------------------------------------------------------------

def t_an_approved_step_lost_to_a_dead_stream_runs_at_the_start_of_the_next_turn():
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.15)
    try:
        # --- turn 1: the model asks for the calculator, the card is approved,
        # the app's stream is already dead.
        dead = _dead_stream_after_the_card()
        s1, calls1 = _turn([calc_call(), ("done", "stop")], gate=gate, stream_out=dead)
        check("the turn noticed the app had gone", s1["client_gone"] is True, repr(s1))
        check("and the approved tool did NOT run into an empty room", ran == [], repr(ran))
        check("no second model request went out", len(calls1) == 1, repr(len(calls1)))
        check("but the owner's yes is remembered for this conversation",
              AG.owed_pending(CONV) is True)

        # --- turn 2: the app re-sends the same conversation (91 ms later).
        out2 = []
        s2, calls2 = _turn([("content", "It is 4."), ("done", "stop")],
                           gate=gate, stream_out=out2.append)
        check("the owed step ran, exactly once, at the start of that turn",
              ran == [{"expression": "2+2"}], repr(ran))
        check("its result is in the context the model answered from",
              any('"value": 4' in (m.get("content") or "") for m in tool_messages(calls2)),
              repr(tool_messages(calls2)))
        check("the question is still the owner's own, and still last in the ask",
              [m.get("content") for m in messages_of(calls2)
               if m.get("role") == "user"][-1] == "how many is 2+2?",
              repr(messages_of(calls2)))
        check("the turn's own record names the tool it ran",
              "calculator" in (s2.get("tools_ran") or []), repr(s2))
        check("the answer went out", b"It is 4." in b"".join(out2),
              repr(b"".join(out2)[:200]))
        check("the record is cleared, so it cannot run again",
              AG.owed_pending(CONV) is False)

        # --- turn 3: a third re-send of the same conversation runs nothing.
        s3, calls3 = _turn([("content", "It is still 4."), ("done", "stop")], gate=gate)
        check("a re-send after that runs nothing a second time",
              len(ran) == 1 and s3["tools_ran"] == [], repr((ran, s3.get("tools_ran"))))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_the_gate_is_never_asked_for_the_same_approval_twice():
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        asked_after_turn_one = list(gate.asked)
        _turn([("content", "It is 4."), ("done", "stop")], gate=gate)
    finally:
        AG.TOOLS["calculator"].execute = real
    check("the first turn asked one card", len(asked_after_turn_one) == 1,
          repr(asked_after_turn_one))
    check("the second turn asked NO card at all - the approval is carried, not re-raised",
          gate.asked == asked_after_turn_one, repr(gate.asked))
    check("and the step still ran (a carried yes, not an auto-approve of something new)",
          ran == [{"expression": "2+2"}], repr(ran))


def t_the_carried_step_goes_through_prepare_and_execute_like_any_call():
    """The same contract an ordinary call goes through: check_call's schema
    check first (an argument that is wrong is refused, never silently run), and
    prepare() before the run. Proved through the one hook that can fail it."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    real_prepare = AG.TOOLS["calculator"].prepare
    prepared = []

    def recording_prepare(args):
        prepared.append(args)
        return real_prepare(args)
    AG.TOOLS["calculator"].prepare = recording_prepare
    try:
        gate = Gate(wait=0.12)
        _turn([calc_call("2+2"), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        _turn([("content", "4."), ("done", "stop")], gate=gate)
    finally:
        AG.TOOLS["calculator"].prepare = real_prepare
        AG.TOOLS["calculator"].execute = real
    check("prepare() ran for the carried step, exactly as for a fresh call",
          {"expression": "2+2"} in prepared, repr(prepared))
    check("and its execute() ran once", ran == [{"expression": "2+2"}], repr(ran))


def t_the_carried_web_search_runs_with_no_second_card():
    """The measured bug was a SEARCH - the owner's own log line is
    `agent.chain web_search ran=true ok=true`, then `rounds=1`, and the card
    that was approved is `search_the_web`. The generic path is proved above
    with the calculator; this drives the search's own function, with the
    search module stubbed (no key, no network), so the branch the owner
    actually hit is covered too."""
    AG.forget_owed()
    try:
        import jarvis_search as WS
    except Exception as exc:                                  # noqa: BLE001
        return skip(f"jarvis_search is not importable here ({type(exc).__name__}: {exc})")
    import types
    ran = []
    asked = []
    real = {name: getattr(WS, name) for name in
            ("settings", "plan", "describe", "run", "tool_result")}
    try:
        WS.settings = lambda: {"ask_every_time": False}
        WS.plan = lambda query, s=None: types.SimpleNamespace(
            problem="", query=query, providers=["stub"])
        WS.describe = lambda p: f"Search the web for: {p.query}"
        WS.run = lambda p, approved=False: ran.append(p.query) or {
            "ok": True, "results": [{"title": "T", "url": "https://example.invalid"}]}
        WS.tool_result = lambda r: r

        watch = AG._TurnWatch([{"role": "user", "content": "what is new?"}], {})
        convo: list = []
        steps: list = []
        out = AG._Out(lambda b: None, sse=True)
        verdict = AG._AlreadyApproved("card-search-0001", WS.ACTION_SEARCH)
        call = {"id": "call_search", "type": "function",
                "function": {"name": "web_search",
                             "arguments": {"query": "what is new?"}}}

        def must_not_be_asked(action, detail, prompt):
            asked.append(action)
            raise AssertionError("a carried search raised a second card")
        AG._web_search_call({"query": "what is new?"}, call, convo, steps,
                            must_not_be_asked, None, out, lambda *a, **k: None,
                            watch=watch, pre_approved=verdict)
    finally:
        for name, fn in real.items():
            setattr(WS, name, fn)
    check("the carried search raised NO second card", asked == [], repr(asked))
    check("and the search really ran, once", ran == ["what is new?"], repr(ran))
    check("the turn's step record says it ran and worked",
          len(steps) == 1 and steps[0].get("tool") == "web_search"
          and steps[0].get("ran") is True and steps[0].get("ok") is True
          and steps[0].get("outcome") == "approved", repr(steps))
    check("and its result is in the transcript the model reads",
          len(convo) == 1 and convo[0]["role"] == "tool"
          and "example.invalid" in convo[0]["content"], repr(convo))
    check("it counts as a read, so the outside-text note applies to it",
          "web_search" in watch.read, repr(sorted(watch.read)))


def t_the_reported_seam_end_to_end_a_lost_search_runs_once_and_answers():
    """THE OWNER'S OWN PATH, END TO END, not in pieces.

    This is the reported seam driven through `run_local_turn` itself, with
    only the wire (Ollama's stream) and the search's own module stubbed - no
    phone, no network, no socket:

        turn 1  the model asks for a web search; its card is approved while
                the app's stream is dead; the search does NOT run;
        turn 2  the app re-sends the SAME conversation: the search really
                runs, exactly once, and its result is in the transcript of
                the round that writes the answer;
        turn 3  a second re-sent turn runs nothing again.

    The search-specific checks above drive `_web_search_call` directly; this
    one proves the seam the owner actually hit - `_one_call`'s web_search
    branch, `owed_record`, the start of the next turn, `_web_search_call`
    under the carried verdict, and the ordinary answer round - in one turn
    sequence."""
    AG.forget_owed()
    try:
        import jarvis_search as WS
    except Exception as exc:                                  # noqa: BLE001
        return skip(f"jarvis_search is not importable here ({type(exc).__name__}: {exc})")
    import types
    query = "what is new on the graphics card?"
    ran = []
    gate = Gate(wait=0.15)
    real = {name: getattr(WS, name) for name in
            ("settings", "plan", "describe", "run", "tool_result")}
    result = {"ok": True, "results": [
        {"title": "A new card", "url": "https://example.invalid/news"}]}
    try:
        # "Ask before every web search": a real reason for a real card.
        WS.settings = lambda: {"ask_every_time": True}
        WS.plan = lambda q, s=None: types.SimpleNamespace(
            problem="", query=q, providers=["stub"])
        WS.describe = lambda p: f"Search the web for: {p.query}"
        WS.run = lambda p, approved=False: ran.append(p.query) or dict(result)
        WS.tool_result = lambda r: r

        # --- turn 1: the card is approved, and the app is already gone.
        dead = _dead_stream_after_the_card()
        s1, _calls1 = _turn([search_call(query), ("done", "stop")], gate=gate,
                            stream_out=dead, enabled_tools=("web_search",))
        check("the reported seam happened: the turn found the app gone",
              s1["client_gone"] is True, repr(s1))
        check("and the approved search did NOT run into an empty room",
              ran == [], repr(ran))
        check("the owner's yes is remembered for this conversation",
              AG.owed_pending(CONV) is True)
        check("only one card was raised", len(gate.asked) == 1, repr(gate.asked))

        # --- turn 2: the app re-sends the same conversation (91 ms later).
        out2 = []
        s2, calls2 = _turn([("content", "It is the new card."), ("done", "stop")],
                           gate=gate, stream_out=out2.append,
                           enabled_tools=("web_search",))
        check("the search really ran on the next turn, exactly once",
              ran == [query], repr(ran))
        check("no second card was raised for the same approval",
              len(gate.asked) == 1 and gate.asked[0][0] == WS.ACTION_SEARCH,
              repr(gate.asked))
        results = tool_messages(calls2, 0)
        check("its result is in the transcript of the FIRST round - before the "
              "answer was written",
              any("example.invalid" in (m.get("content") or "") for m in results),
              repr(results))
        check("the turn's own record names the search it ran",
              "web_search" in (s2.get("tools_ran") or []), repr(s2))
        check("the answer went out", b"It is the new card." in b"".join(out2),
              repr(b"".join(out2)[:300]))
        check("the record is cleared, so it cannot run again",
              AG.owed_pending(CONV) is False)

        # --- turn 3: a second re-send of the same conversation runs nothing.
        s3, _calls3 = _turn([("content", "Still the new card."), ("done", "stop")],
                            gate=gate, enabled_tools=("web_search",))
        check("a second re-sent turn does not run it again",
              ran == [query] and s3["tools_ran"] == [],
              repr((ran, s3.get("tools_ran"))))
    finally:
        for name, fn in real.items():
            setattr(WS, name, fn)


# --------------------------------------------------------------------------
#   2. Nothing a person did not approve is ever carried
# --------------------------------------------------------------------------

def t_a_denied_card_is_never_carried_or_run():
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(outcome="denied", wait=0.12)
    try:
        s1, _ = _turn([calc_call(), ("done", "stop")], gate=gate,
                      stream_out=_dead_stream_after_the_card(),
                      answer=[("content", "I did not do that."), ("done", "stop")],
                      request={"conversation_id": CONV})
        check("a denied card's turn ends as it did before", s1["client_gone"] is True)
        check("nothing is owed after a denial", AG.owed_pending(CONV) is False)
        s2, _ = _turn([("content", "I did not do that."), ("done", "stop")], gate=gate)
        check("and the next turn runs nothing", ran == [] and s2["tools_ran"] == [],
              repr((ran, s2.get("tools_ran"))))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_a_card_nobody_answered_is_never_carried():
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(outcome="timed_out", wait=0.12)
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card(),
              answer=[("content", "Nobody answered, so I did nothing."), ("done", "stop")])
        check("a card that timed out carries nothing (nobody said yes)",
              AG.owed_pending(CONV) is False)
        _turn([("content", "ok"), ("done", "stop")], gate=gate)
        check("and nothing runs on the next turn", ran == [], repr(ran))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_a_card_that_never_got_an_answer_is_never_carried():
    """A tier that asks nobody (the gate's own "notify" word): allowed, but no
    person was asked - so there is no yes to carry."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(outcome="notify", wait=0.12)
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card(),
              answer=[("content", "Done."), ("done", "stop")])
        check("a call nobody was asked about carries nothing",
              AG.owed_pending(CONV) is False)
        _turn([("content", "ok"), ("done", "stop")], gate=gate)
        check("and nothing runs on the next turn", ran == [], repr(ran))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_a_verdict_without_a_card_id_is_not_carried():
    """A gate from before gate-outcome.patch has no request_id. Without one the
    step could not be de-duplicated, so it is not carried at all - fail closed."""
    AG.forget_owed()

    class OldVerdict:
        allowed = True
        outcome = "approved"
        tier = "ask"

    class OldGate:
        def __init__(self):
            self.asked = []

        def __call__(self, action, detail, prompt):
            self.asked.append(action)
            time.sleep(0.12)
            return OldVerdict()

    ran = []
    real = _count_runs(ran)
    try:
        _turn([calc_call(), ("done", "stop")], gate=OldGate(),
              stream_out=_dead_stream_after_the_card())
        check("a verdict with no card id carries nothing (it could not be de-duped)",
              AG.owed_pending(CONV) is False)
    finally:
        AG.TOOLS["calculator"].execute = real


def t_a_request_without_a_conversation_id_carries_nothing():
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate, conversation_id=None,
              stream_out=_dead_stream_after_the_card())
        check("no conversation id means no conversation to carry it into",
              AG.owed_pending(CONV) is False and AG.owed_pending("") is False)
        _turn([("content", "ok"), ("done", "stop")], gate=gate, conversation_id=None)
        check("and nothing runs", ran == [], repr(ran))
    finally:
        AG.TOOLS["calculator"].execute = real


# --------------------------------------------------------------------------
#   3. Once, in one conversation, for ten minutes
# --------------------------------------------------------------------------

def t_a_different_conversation_never_inherits_it():
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        check("the step is owed to its own conversation", AG.owed_pending(CONV) is True)
        other = "conv-somebody-else"
        _turn([("content", "hello"), ("done", "stop")], gate=gate,
              conversation_id=other)
        check("another conversation runs nothing of it", ran == [], repr(ran))
        check("and it is still owed to the one it belongs to",
              AG.owed_pending(CONV) is True)
    finally:
        AG.TOOLS["calculator"].execute = real


def t_an_owed_step_ages_out_after_ten_minutes():
    AG.forget_owed()
    seen = {}
    gate = Gate(wait=0.12)

    class Clocked:
        """A gate that records the card the agent carried, so the record can be
        aged without waiting ten real minutes."""
        def __call__(self, action, detail, prompt):
            seen["card"] = f"card-clock-0001"
            time.sleep(0.12)
            return _Verdict(True, "approved", seen["card"], action)

    ran = []
    real = _count_runs(ran)
    try:
        _turn([calc_call(), ("done", "stop")], gate=Clocked(),
              stream_out=_dead_stream_after_the_card())
        check("the step is owed to begin with", AG.owed_pending(CONV) is True)
        # Age it exactly the way a ten-minute gap would, without waiting.
        AG._OWED[CONV]["at"] -= (AG.OWED_TTL_SECONDS + 1.0)
        check("ten minutes later it is no longer owed", AG.owed_pending(CONV) is False)
        _turn([("content", "ok"), ("done", "stop")], gate=gate)
        check("and it never runs", ran == [], repr(ran))
        check("the ten-minute rule is a real number, not a placeholder",
              AG.OWED_TTL_SECONDS == 600.0, repr(AG.OWED_TTL_SECONDS))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_a_private_turn_leaves_it_owed_for_an_ordinary_one():
    """A private chat runs no tool at all (the architect's H10 ruling). It must
    not consume the owner's yes either - the step stays owed until an ordinary
    turn can use it."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        _turn([("content", "private words"), ("done", "stop")], gate=gate, private=True)
        check("a private turn runs nothing and keeps the step owed",
              ran == [] and AG.owed_pending(CONV) is True, repr((ran, AG.owed_pending(CONV))))
        _turn([("content", "4."), ("done", "stop")], gate=gate)
        check("the next ordinary turn still gets it", ran == [{"expression": "2+2"}],
              repr(ran))
    finally:
        AG.TOOLS["calculator"].execute = real


# --------------------------------------------------------------------------
#   3b. The yes is a decision of the moment: the gate's CURRENT policy is
#       made again at replay time, and a withdrawn approval is dropped
# --------------------------------------------------------------------------

def _dropped_lines():
    return [l for l in audit_lines() if l.get("event") == "agent.owed_dropped"]


def t_a_stop_all_after_the_approval_drops_the_step():
    """Stop everything is a standing "do less" (jarvis_stop_all.py): a card
    approved before the press must not run after it, however long the app took
    to re-send the conversation."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    SA = None
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        check("the step is owed after the approval", AG.owed_pending(CONV) is True)
        SA = _press_stop_all()
        out = []
        s2, calls2 = _turn([("content", "I did not do that."), ("done", "stop")],
                           gate=gate, stream_out=out.append)
        said = b"".join(out).decode("utf-8", "replace")
        check("Stop everything after the approval means it does NOT run",
              ran == [] and s2["tools_ran"] == [], repr((ran, s2.get("tools_ran"))))
        check("the owner is told why, in code's own words",
              "was not run" in said and "Stop everything" in said, repr(said[:400]))
        check("nothing was invented for the model to read as its result",
              tool_messages(calls2) == [], repr(tool_messages(calls2)))
        drops = _dropped_lines()
        check("the drop is in the audit log, with its reason",
              bool(drops) and drops[-1]["detail"].get("reason") == "stop_all",
              repr(drops[-1:]))
        check("the record is spent, so it cannot run on a later question",
              AG.owed_pending(CONV) is False)
        s3, _ = _turn([("content", "ok"), ("done", "stop")], gate=gate)
        check("and a later turn does not run it either",
              ran == [] and s3["tools_ran"] == [], repr((ran, s3.get("tools_ran"))))
    finally:
        AG.TOOLS["calculator"].execute = real
        if SA is not None:
            SA._reset_for_tests()


def t_a_crisis_after_the_approval_drops_the_step():
    """A crisis message is not an ordinary question: after one, a search
    approved before it is stale, not something to run quietly. The crisis
    turn itself runs no tool and leaves the step owed; the next ordinary turn
    drops it and says why."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    try:
        import jarvis_wellbeing as WB
    except Exception as exc:                                  # noqa: BLE001
        return skip(f"jarvis_wellbeing is not importable here ({type(exc).__name__}: {exc})")
    real_crisis = WB.crisis_in_turn
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        check("the step is owed after the approval", AG.owed_pending(CONV) is True)
        # A real turn whose distress check fires, without depending on the
        # exact phrase list: the check itself is the stand-in.
        WB.crisis_in_turn = lambda *a, **k: True
        c, _ = _turn([("content", "I am here."), ("done", "stop")], gate=gate)
        check("a crisis turn runs nothing and keeps the step owed",
              ran == [] and AG.owed_pending(CONV) is True
              and c["tools_ran"] == [], repr((ran, c.get("tools_ran"))))
        WB.crisis_in_turn = real_crisis
        out = []
        s2, calls2 = _turn([("content", "ok"), ("done", "stop")],
                           gate=gate, stream_out=out.append)
        said = b"".join(out).decode("utf-8", "replace")
        check("the next ordinary turn drops it, because the crisis came after "
              "the approval",
              ran == [] and s2["tools_ran"] == [], repr((ran, s2.get("tools_ran"))))
        check("the owner is told a crisis message came after the approval",
              "was not run" in said and "crisis" in said, repr(said[:400]))
        drops = _dropped_lines()
        check("the audit log says it was the crisis, not a TTL or a denial",
              bool(drops) and drops[-1]["detail"].get("reason") == "crisis",
              repr(drops[-1:]))
        check("the record is spent", AG.owed_pending(CONV) is False)
    finally:
        WB.crisis_in_turn = real_crisis
        AG.TOOLS["calculator"].execute = real


def t_a_tier_turned_to_never_after_the_approval_drops_the_step():
    """The owner can set an action to "never" between the tap and the re-sent
    turn (Settings). The gate would refuse it with no card; the carried step
    must not run something the gate would now refuse."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    real_tier = AG._tier_of
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        check("the step is owed after the approval", AG.owed_pending(CONV) is True)
        AG._tier_of = lambda action: "never"
        out = []
        s2, _ = _turn([("content", "I did not do that."), ("done", "stop")],
                      gate=gate, stream_out=out.append)
        said = b"".join(out).decode("utf-8", "replace")
        check("an action now at tier \"never\" is not run",
              ran == [] and s2["tools_ran"] == [], repr((ran, s2.get("tools_ran"))))
        check("the owner is told the setting changed", "never run" in said,
              repr(said[:400]))
        drops = _dropped_lines()
        check("the audit log carries the tier reason",
              bool(drops) and drops[-1]["detail"].get("reason") == "tier_never",
              repr(drops[-1:]))
        check("the record is spent", AG.owed_pending(CONV) is False)
    finally:
        AG._tier_of = real_tier
        AG.TOOLS["calculator"].execute = real


def t_a_tool_switched_off_after_the_approval_drops_the_step():
    """A tool turned off in Settings after the approval is no longer offered;
    its card's yes cannot bring it back."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        check("the step is owed after the approval", AG.owed_pending(CONV) is True)
        out = []
        s2, _ = _turn([("content", "I did not do that."), ("done", "stop")],
                      gate=gate, stream_out=out.append, enabled_tools=())
        said = b"".join(out).decode("utf-8", "replace")
        check("a tool switched off after the approval is not run",
              ran == [] and s2["tools_ran"] == [], repr((ran, s2.get("tools_ran"))))
        check("the owner is told it is no longer switched on",
              "was not run" in said and "no longer switched on" in said,
              repr(said[:400]))
        drops = _dropped_lines()
        check("the audit log carries the tool-off reason",
              bool(drops) and drops[-1]["detail"].get("reason") == "tool_off",
              repr(drops[-1:]))
        check("the record is spent", AG.owed_pending(CONV) is False)
    finally:
        AG.TOOLS["calculator"].execute = real


def t_a_picture_turn_does_not_spend_or_run_it():
    """A picture turn on the vision lane offers no tool (_allowed_tools(none)),
    so it must not spend the owner's yes on a turn that could never use it."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    lane = AG.LaneChoice("http://127.0.0.1:11434", "jarvis-vision", 16384,
                         "vision", "test")
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        c, calls = _turn([("content", "I see a picture."), ("done", "stop")],
                         gate=gate, lane=lane)
        check("a picture turn runs nothing and keeps the step owed",
              ran == [] and AG.owed_pending(CONV) is True
              and c["tools_ran"] == [], repr((ran, c.get("tools_ran"))))
        check("and it offered no tools at all",
              not (calls[0] or {}).get("tools"), repr((calls[0] or {}).get("tools")))
        _turn([("content", "4."), ("done", "stop")], gate=gate)
        check("the next ordinary turn still gets it",
              ran == [{"expression": "2+2"}], repr(ran))
    finally:
        AG.TOOLS["calculator"].execute = real


def t_a_model_that_cannot_take_tools_does_not_spend_or_run_it():
    """A model that cannot use tools is offered none; the same bound applies -
    the yes waits for a turn that can use it, and the TTL ends the wait."""
    AG.forget_owed()
    ran = []
    real = _count_runs(ran)
    gate = Gate(wait=0.12)
    real_can = AG._model_can_use_tools
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        AG._model_can_use_tools = lambda url, model: False
        c, calls = _turn([("content", "I answered without tools."), ("done", "stop")],
                         gate=gate)
        check("a turn whose model cannot use tools runs nothing and keeps the "
              "step owed",
              ran == [] and AG.owed_pending(CONV) is True
              and c["tools_ran"] == [], repr((ran, c.get("tools_ran"))))
        check("and the request offered no tools at all",
              not (calls[0] or {}).get("tools"), repr((calls[0] or {}).get("tools")))
        AG._model_can_use_tools = real_can
        _turn([("content", "4."), ("done", "stop")], gate=gate)
        check("the next ordinary turn still gets it",
              ran == [{"expression": "2+2"}], repr(ran))
    finally:
        AG._model_can_use_tools = real_can
        AG.TOOLS["calculator"].execute = real


# --------------------------------------------------------------------------
#   4. Honesty: a carried step that fails says so, and is in the audit log
# --------------------------------------------------------------------------

def t_a_failed_carried_step_is_said_plainly():
    AG.forget_owed()
    gate = Gate(wait=0.12)
    real = AG.TOOLS["calculator"].execute
    # An execute() that raises is the same ceiling every tool already has (see
    # _one_call's own try/except): the result becomes an error the model reads.
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: (_ for _ in ()).throw(
        RuntimeError("the worker died"))
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        out = []
        s2, calls2 = _turn([("content", "I could not do it."), ("done", "stop")],
                           gate=gate, stream_out=out.append)
    finally:
        AG.TOOLS["calculator"].execute = real
    body = b"".join(out)
    said = body.decode("utf-8", "replace")
    check("the answer says, in code's own words, that the approved step failed",
          "you approved a moment ago" in said and "it did not work" in said, repr(said[:400]))
    check("the model was told the same thing, so it cannot claim it worked",
          any("RuntimeError" in (m.get("content") or "") for m in tool_messages(calls2)),
          repr(tool_messages(calls2)))
    check("and the answer claims no result from it", "no result from it" in said,
          repr(said[:400]))
    check("and the record is still cleared after a failed run",
          AG.owed_pending(CONV) is False)


def t_a_replay_that_raises_still_gives_the_owner_an_answer():
    """A carried step that blows up before it can even be dispatched must not
    turn the question into a 500: the turn goes on, and the answer says the
    step did not work. Nothing is run, and it is not carried a second time."""
    AG.forget_owed()
    gate = Gate(wait=0.12)
    _turn([calc_call(), ("done", "stop")], gate=gate,
          stream_out=_dead_stream_after_the_card())
    check("the step is owed", AG.owed_pending(CONV) is True)
    real = AG._one_call

    def exploding(*a, **kw):
        raise ValueError("the replay blew up")
    AG._one_call = exploding
    try:
        out = []
        s2, calls2 = _turn([("content", "I could not do it."), ("done", "stop")],
                           gate=gate, stream_out=out.append)
    finally:
        AG._one_call = real
    said = b"".join(out).decode("utf-8", "replace")
    check("the turn still finished and answered", s2.get("finish_reason") == "stop",
          repr(s2))
    check("and said, in code's own words, that the approved step did not work",
          "it did not work" in said, repr(said[:400]))
    check("the record is spent, so it cannot run on every later question",
          AG.owed_pending(CONV) is False)
    # The assistant tool-call message was appended before the raise. The
    # model must never receive a tool call with no result beside it.
    asked = assistant_calls(calls2)
    tools = tool_messages(calls2)
    check("the half-built transcript was repaired: the tool call has its result",
          len(asked) == 1 and len(tools) == 1
          and tools[0].get("tool_call_id") == asked[0]["tool_calls"][0].get("id"),
          repr((asked, tools)))
    check("and that result says plainly that nothing was run",
          "could not be run" in (tools[0].get("content") or "")
          and "no result from it" in (tools[0].get("content") or ""),
          repr(tools))
    check("and the turn does not claim the step ran",
          "calculator" not in (s2.get("tools_ran") or []),
          repr(s2.get("tools_ran")))


def t_the_record_and_the_replay_are_in_the_audit_log():
    AG.forget_owed()
    gate = Gate(wait=0.12)
    before = len(audit_lines())
    _turn([calc_call(), ("done", "stop")], gate=gate,
          stream_out=_dead_stream_after_the_card())
    _turn([("content", "4."), ("done", "stop")], gate=gate)
    lines = audit_lines()[before:]
    owed = [l for l in lines if l.get("event") == "agent.owed"]
    ran = [l for l in lines if l.get("event") == "agent.owed_ran"]
    check("the lost approval is written to the audit log, not dropped silently",
          len(owed) == 1, repr([l.get("event") for l in lines]))
    check("with who/what/why: the card, the tool, the action and the reason",
          bool(owed) and owed[0]["detail"].get("card") == "card1-0f1e2d3c"
          and owed[0]["detail"].get("tool") == "calculator"
          and owed[0]["detail"].get("action")
          and "closed" in owed[0]["detail"].get("why", ""), repr(owed))
    check("and the replay is written too, saying it ran and worked",
          len(ran) == 1 and ran[0]["detail"].get("ran") is True
          and ran[0]["detail"].get("ok") is True, repr(ran))
    check("neither line carries the card's words or the owner's question",
          bool(owed) and "2+2" not in json.dumps(owed[0])
          and "how many" not in json.dumps(owed[0]), repr(owed))


# --------------------------------------------------------------------------
#   5. The prompt shape the carried step leaves behind
# --------------------------------------------------------------------------

def t_the_carried_step_leaves_the_ordinary_multi_step_transcript():
    """The model did ask for this call - that is where the card came from - so
    what it reads must look like any turn of its own: the assistant message
    that asked for the tool, then the tool's result, in that order."""
    AG.forget_owed()
    gate = Gate(wait=0.12)
    real = AG.TOOLS["calculator"].execute
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": 4}
    try:
        _turn([calc_call(), ("done", "stop")], gate=gate,
              stream_out=_dead_stream_after_the_card())
        _, calls2 = _turn([("content", "4."), ("done", "stop")], gate=gate)
    finally:
        AG.TOOLS["calculator"].execute = real
    msgs = messages_of(calls2)
    asked = assistant_calls(calls2)
    tools = tool_messages(calls2)
    check("the assistant message that asked for the tool is in the transcript",
          len(asked) == 1 and asked[0]["tool_calls"][0]["function"]["name"] == "calculator",
          repr(asked))
    check("the tool result follows it, with that call's own id",
          len(tools) == 1 and tools[0].get("tool_call_id") == asked[0]["tool_calls"][0].get("id"),
          repr((asked, tools)))
    data = json.loads(tools[0]["content"])
    check("the result is the tool's own JSON, not a sentence about it",
          isinstance(data, dict) and data.get("ok") is True and data.get("value") == 4,
          repr(tools[0]["content"]))
    check("and the transcript holds nothing of the card's own text",
          not any("Evaluate" == (m.get("content") or "") for m in msgs))


def t_the_outside_text_note_goes_above_a_carried_reading_tool():
    """A search's result is outside text, and the note that says so must sit
    ABOVE it - the rule the round loop's own insert follows. Driven here
    through the replay itself with the one stand-in a headless machine needs:
    a reader (no network, no key) instead of a real web search."""
    AG.forget_owed()
    convo = [{"role": "user", "content": "how many is 2+2?"}]
    steps = []
    watch = AG._TurnWatch([{"role": "user", "content": "how many is 2+2?"}], {})
    out = AG._Out(lambda b: None, sse=True)
    real = AG._one_call

    # `read_web_page` is a READING tool (not in _NOT_READING), which is the
    # property this check needs: it is what makes the turn "shaped by outside
    # text" and so what OUTSIDE_NOTE has to be said about. The dispatch itself
    # is stubbed - no page is fetched, and none could be on a machine with no
    # network.
    def reading_tool(call, names, convo, steps, checker, announce, out, say_step,
                     **kw):
        convo.append({"role": "tool", "tool_call_id": call.get("id", ""),
                      "content": json.dumps({"ok": True, "url": "example.invalid"})})
        steps.append({"tool": "read_web_page", "ran": True, "ok": True})
        watch.took_in("read_web_page", {"ok": True, "text": "read from outside"})
    AG._one_call = reading_tool
    try:
        owed = {"card": "card-note-0001", "tool": "read_web_page", "action": "read_web_page",
                "call": {"id": "call_note", "type": "function",
                         "function": {"name": "read_web_page",
                                      "arguments": {"url": "https://example.invalid"}}},
                "args": {"url": "https://example.invalid"}, "at": time.monotonic()}
        AG._owed_replay(owed, convo, steps, lambda *a, **k: None, None, out, watch,
                        ["read_web_page"], {}, None, None)
    finally:
        AG._one_call = real
    kinds = [m.get("role") for m in convo]
    check("the outside-text note is in the transcript", AG.OUTSIDE_NOTE in
          [m.get("content") for m in convo], repr(kinds))
    note_at = [i for i, m in enumerate(convo) if m.get("content") == AG.OUTSIDE_NOTE]
    asked_at = [i for i, m in enumerate(convo) if m.get("tool_calls")]
    check("it sits ABOVE the call and its result, not after them",
          bool(note_at) and bool(asked_at) and note_at[0] < asked_at[0],
          repr(kinds))


# --------------------------------------------------------------------------
#   6. The shipped copy of the agent is the one the tests read
# --------------------------------------------------------------------------

def t_the_shipped_copies_are_the_same_file():
    """jarvis_agent.py is shipped WHOLE (the $SHIPPED list in
    scripts/apply-patches.ps1 copies it in; no patch targets it), so the base
    this repository publishes must be this same text - the two-file rule
    backend/test_base_matches_repo.py enforces for every shipped module. Named
    here as well because THIS change is a whole-file delivery, not a patch, and
    a reader looking for the patch should be told where the change lives."""
    base = HERE.parent / "jarvis-backend" / "jarvis_agent.py"
    if not base.is_file():
        return skip("jarvis-backend/jarvis_agent.py is not in this tree")
    mine = (HERE / "jarvis_agent.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    theirs = base.read_text(encoding="utf-8").replace("\r\n", "\n")
    check("the published base holds this same jarvis_agent.py", mine == theirs)
    check("and it is a shipped module, so the change is delivered by the whole file",
          "jarvis_agent.py" in
          (HERE.parent / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8"))


if __name__ == "__main__":
    for fn in (t_an_approved_step_lost_to_a_dead_stream_runs_at_the_start_of_the_next_turn,
               t_the_gate_is_never_asked_for_the_same_approval_twice,
               t_the_carried_step_goes_through_prepare_and_execute_like_any_call,
               t_the_carried_web_search_runs_with_no_second_card,
               t_the_reported_seam_end_to_end_a_lost_search_runs_once_and_answers,
               t_a_denied_card_is_never_carried_or_run,
               t_a_card_nobody_answered_is_never_carried,
               t_a_card_that_never_got_an_answer_is_never_carried,
               t_a_verdict_without_a_card_id_is_not_carried,
               t_a_request_without_a_conversation_id_carries_nothing,
               t_a_different_conversation_never_inherits_it,
               t_an_owed_step_ages_out_after_ten_minutes,
               t_a_private_turn_leaves_it_owed_for_an_ordinary_one,
               t_a_stop_all_after_the_approval_drops_the_step,
               t_a_crisis_after_the_approval_drops_the_step,
               t_a_tier_turned_to_never_after_the_approval_drops_the_step,
               t_a_tool_switched_off_after_the_approval_drops_the_step,
               t_a_picture_turn_does_not_spend_or_run_it,
               t_a_model_that_cannot_take_tools_does_not_spend_or_run_it,
               t_a_failed_carried_step_is_said_plainly,
               t_a_replay_that_raises_still_gives_the_owner_an_answer,
               t_the_record_and_the_replay_are_in_the_audit_log,
               t_the_carried_step_leaves_the_ordinary_multi_step_transcript,
               t_the_outside_text_note_goes_above_a_carried_reading_tool,
               t_the_shipped_copies_are_the_same_file):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
