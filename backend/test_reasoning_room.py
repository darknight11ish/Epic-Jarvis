"""Two measured defects on the path every ordinary question takes, 2026-10-09.

    python3 test_reasoning_room.py

Both were found by benchmarking this PC's own models, and both live in
jarvis_agent.run_local_turn - the one function every local turn goes through.

  1. A SHORT QUESTION COULD COME BACK EMPTY. Thinking and the answer are one
     allowance: Ollama stops the reply - reasoning included - at max_tokens.
     Measured with qwen3:8b on this PC: a one-line factual question at
     max_tokens 128 spent all 128 tokens thinking (561 characters of
     reasoning) and returned NOTHING in 3.5 s; with thinking off the same
     question answered correctly in 0.29 s. The fix
     (jarvis_agent.REASONING_MIN_ANSWER_TOKENS, chat_body): when the answer's
     own allowance is too small to share with thinking, thinking is left off
     for that turn and the model answers directly. A bigger allowance is
     untouched, so the owner's chosen thinking level still applies to every
     turn that has the room for it.

  2. THE START OF A LONG CONVERSATION WAS DELETED SILENTLY. Ollama removes
     the FRONT of an over-long prompt and answers anyway - no error, no note.
     Measured on Ollama 0.40.2 here: eight prompts of growing length, and
     every one past the limit came back reporting a prompt of EXACTLY 8,194
     tokens whatever was sent (the owner's own benchmark saw 16,382 at
     num_ctx 16384). The fix (jarvis_agent.dropped_prompt_note): what was
     sent is compared with what the model reports it read, and a shortfall
     that matters is said in the activity line both apps already show for
     link and model trouble - never a silent trim, and never an address or a
     port.

No network, no model, no socket: every reply here comes from _ollama_wire.py,
which transcribes what Ollama really sends. One stand-in response, in the
second half, is what a truncated prompt comes back as.

Run with JARVIS_BACKEND set (a real install) and the suite stops plainly
unless the backend holds this repository's jarvis_agent.py - a suite that
tested the repository's copy while reporting on the installed one would be
the same lie these two fixes are about.
"""
import json
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain, require_shipped  # noqa: E402

# The config folder jarvis_thinking writes its setting into, and jarvis_framework
# is replaced before anything imports it - so this suite can choose a thinking
# level without touching the owner's own setting file.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-reasoning-room-"))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.load_framework = lambda *a, **k: {}
_fw.audit_log = lambda *a, **k: None
sys.modules["jarvis_framework"] = _fw

require_shipped("jarvis_agent.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_thinking as JT  # noqa: E402
import _ollama_wire as W  # noqa: E402

AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

FAILED, PASSED, SKIPPED = [], [], []
MODEL = "qwen3:8b"
URL = "http://127.0.0.1:11434"


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
#   The model, as a stand-in: one request, one canned answer
# --------------------------------------------------------------------------

class FakeOllama:
    """What run_local_turn asks to send, and a real Ollama stream back.

    `usage` is the prompt count Ollama reports at the end of a stream
    (stream_options.include_usage). None: it reports none, which is what an
    older Ollama does - and what must never be read as "it dropped text".
    """

    def __init__(self, events, usage=None):
        self.events = events
        self.usage = usage
        self.requests = []

    def open(self, url, payload):
        self.requests.append(payload)
        body = W.stream(self.events)
        if self.usage is not None:
            body = body.replace(
                b"data: [DONE]",
                b"data: " + W.go_json(
                    {"id": "chatcmpl-742", "object": "chat.completion.chunk",
                     "created": 1790000000, "model": MODEL,
                     "system_fingerprint": "fp_ollama", "choices": [],
                     "usage": {"prompt_tokens": self.usage, "completion_tokens": 4,
                               "total_tokens": self.usage + 4}}).encode("utf-8")
                + b"\n\ndata: [DONE]")
        return W.FakeResponse(body)

    @property
    def body(self):
        return self.requests[-1]


def _thinking_on(level=JT.QUICK):
    """The owner's own thinking setting, ON, for the everyday model - written
    into this suite's own config folder, never the owner's, and through the
    real set_level() the settings screen calls."""
    JT.reset_for_tests()
    JT._CAP_OVERRIDE[(URL, MODEL)] = ["completion", "tools", "thinking"]
    code, out = JT.set_level("everyday", level, model_name=MODEL, ollama_url=URL)
    if code != 200:
        raise RuntimeError(f"could not set the thinking level for this suite: {out}")


def _thinking_off_again():
    JT.reset_for_tests()


def turn(ollama, **kw):
    """One ordinary turn through run_local_turn, with everything that would
    touch the network or the owner's files replaced."""
    said, out = [], []
    kw.setdefault("context_length", 16384)
    kw.setdefault("keepalive_seconds", 1000)
    summary = AG.run_local_turn([{"role": "user", "content": kw.pop("question", "hi")}],
                                MODEL, ollama_url=URL, stream_out=out.append,
                                open_stream=ollama.open, model_waking=lambda u, m: False,
                                announce=said.append, **kw)
    return b"".join(out), summary, said


# --------------------------------------------------------------------------
#   1. A short answer keeps room for the answer
# --------------------------------------------------------------------------

def t_a_short_allowance_leaves_thinking_off():
    _thinking_on()
    try:
        short = AG.chat_body(MODEL, [{"role": "user", "content": "hi"}],
                             {"max_tokens": 128}, ollama_url=URL, role="everyday")
        long = AG.chat_body(MODEL, [{"role": "user", "content": "hi"}],
                            {"max_tokens": AG.DEFAULT_MAX_TOKENS}, ollama_url=URL,
                            role="everyday")
    finally:
        _thinking_off_again()
    check("a 128-token allowance is not shared with thinking - reasoning is off",
          short.get("reasoning_effort") == "none", repr(short))
    check("the everyday allowance (1,024) still gets the level the owner chose",
          long.get("reasoning_effort") == "low", repr(long))
    check("the floor sits between the two, so neither read of it is a guess",
          128 < AG.REASONING_MIN_ANSWER_TOKENS <= AG.DEFAULT_MAX_TOKENS,
          str(AG.REASONING_MIN_ANSWER_TOKENS))


def t_the_owner_keeps_thinking_where_there_is_room():
    _thinking_on(JT.DEEP)
    try:
        body = AG.chat_body(MODEL, [{"role": "user", "content": "explain quicksort"}],
                            {"max_tokens": 1024}, ollama_url=URL, role="everyday",
                            question="explain quicksort")
    finally:
        _thinking_off_again()
    check("a deep-thinking setting is not overridden on a turn with room for it",
          body.get("reasoning_effort") == "high", repr(body))


def t_a_short_turn_reaches_ollama_with_thinking_off_and_answers():
    _thinking_on()
    try:
        ollama = FakeOllama([("reasoning", "The user asks about France. "),
                             ("content", "The capital of France is Paris."),
                             ("done", "stop")])
        body, summary, _said = turn(ollama, question="What is the capital of France?",
                                    request={"max_tokens": 128})
    finally:
        _thinking_off_again()
    check("the request really sent carries thinking off",
          ollama.body.get("reasoning_effort") == "none", repr(ollama.body))
    check("and the answer is not empty",
          summary["answer"] == "The capital of France is Paris.", repr(summary["answer"]))
    check("nothing of the model's reasoning is shown",
          b"Paris" in body and b"The user asks" not in body, repr(body))
    check("the app is told how the answer ended, as always",
          summary["finish_reason"] == "stop", repr(summary))


def t_the_floor_only_ever_touches_short_allowances():
    """The floor decides WHAT is asked, never whether the field is sent: an
    Ollama that does not know the word has to keep getting it, or the older
    Ollama's own 400-and-ask-again path (test_chat_stream) never runs."""
    check("no max_tokens at all is not treated as a short allowance",
          AG.chat_body(MODEL, [], {}, ollama_url=URL).get("reasoning_effort") == "none")
    check("a bool is not a length",
          AG.chat_body(MODEL, [], {"max_tokens": True},
                       ollama_url=URL).get("reasoning_effort") == "none")
    check("the field is still sent on every turn, as it always was",
          "reasoning_effort" in AG.chat_body(MODEL, [], {"max_tokens": 128},
                                             ollama_url=URL))


# --------------------------------------------------------------------------
#   2. A prompt the model did not read in full is said, not swallowed
# --------------------------------------------------------------------------

#: A long question. estimate_tokens is 3 characters a token, so ~30,000
#: characters is ~10,000 estimated tokens - well past the floor the note is
#: allowed to speak about, and well past what a real truncation keeps.
LONG_QUESTION = ("Tell me about the early history of the village. " * 600)


def t_a_swallowed_prompt_is_said_plainly():
    ollama = FakeOllama([("content", "It began, as far as I know, with a mill."),
                         ("done", "stop")], usage=4098)
    _body, summary, said = turn(ollama, question=LONG_QUESTION)
    check("the model's reply is still delivered - a warning never replaces an answer",
          summary["answer"].startswith("It began"), repr(summary["answer"]))
    check("the owner is told the beginning of the conversation was dropped",
          any(AG.DROPPED_PROMPT_NOTE == s for s in said), repr(said))
    note = AG.DROPPED_PROMPT_NOTE
    check("the note says plainly that earlier messages may be misremembered",
          "earliest part" in note and "earlier messages" in note, note)
    check("the note says what to do about it", "new conversation" in note, note)
    check("no address, no port, no token in it",
          not any(x in note for x in ("127.0.0.1", "11434", "http", "localhost", ":")),
          note)


def t_a_prompt_the_model_read_in_full_says_nothing():
    ollama = FakeOllama([("content", "It began with a mill."), ("done", "stop")],
                        usage=12000)
    _body, _summary, said = turn(ollama, question=LONG_QUESTION)
    check("a prompt the model read in full raises no warning",
          [s for s in said if s == AG.DROPPED_PROMPT_NOTE] == [], repr(said))


def t_an_ollama_that_reports_nothing_is_not_accused():
    ollama = FakeOllama([("content", "It began with a mill."), ("done", "stop")])
    _body, _summary, said = turn(ollama, question=LONG_QUESTION)
    check("an Ollama that reports no prompt count says nothing about what it read",
          said == [], repr(said))
    check("and with no report there is nothing to compare",
          AG.dropped_prompt_note(30000, None) is None
          and AG.dropped_prompt_note(None, 4098) is None)


def t_a_short_prompt_is_never_worth_a_warning():
    check("a short prompt the model read in full: nothing",
          AG.dropped_prompt_note(200, 150) is None)
    check("a short prompt reported short is still nothing - the gap is too small "
          "to be a passage of text",
          AG.dropped_prompt_note(300, 10) is None)
    check("the floor is above the smallest prompts and below a real conversation",
          AG.DROPPED_PROMPT_MIN_TOKENS >= 600, str(AG.DROPPED_PROMPT_MIN_TOKENS))
    check("a modest shortfall is the estimator's own margin, not a loss",
          AG.dropped_prompt_note(9000, 8100) is None)
    check("a prompt the model read in full never warns, however long",
          AG.dropped_prompt_note(30000, 30000) is None
          and AG.dropped_prompt_note(30000, 21000) is None)


def t_the_turn_that_asks_no_activity_line_still_answers():
    """A backend or a caller with no activity line must still get its answer:
    the note is a note, never a failure."""
    ollama = FakeOllama([("content", "It began with a mill."), ("done", "stop")],
                        usage=4098)
    out = []
    summary = AG.run_local_turn([{"role": "user", "content": LONG_QUESTION}], MODEL,
                                ollama_url=URL, stream_out=out.append,
                                open_stream=ollama.open,
                                model_waking=lambda u, m: False,
                                context_length=16384, keepalive_seconds=1000)
    check("the answer arrives with no announce at all",
          summary["answer"] == "It began with a mill." and summary["finish_reason"] == "stop",
          repr(summary))


def t_the_real_settings_files_are_not_touched():
    check("this suite's thinking setting lives in its own folder",
          str(JT.settings_path()).startswith(str(_TMP)), str(JT.settings_path()))
    check("and it is gone again after the checks above",
          not JT.settings_path().exists(), str(JT.settings_path()))
    check("the owner's own config folder is never read or written here",
          str(_TMP) in str(JT._config_dir()), str(JT._config_dir()))


if __name__ == "__main__":
    try:
        for fn in (t_a_short_allowance_leaves_thinking_off,
                   t_the_owner_keeps_thinking_where_there_is_room,
                   t_a_short_turn_reaches_ollama_with_thinking_off_and_answers,
                   t_the_floor_only_ever_touches_short_allowances,
                   t_a_swallowed_prompt_is_said_plainly,
                   t_a_prompt_the_model_read_in_full_says_nothing,
                   t_an_ollama_that_reports_nothing_is_not_accused,
                   t_a_short_prompt_is_never_worth_a_warning,
                   t_the_turn_that_asks_no_activity_line_still_answers,
                   t_the_real_settings_files_are_not_touched):
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(fn.__name__)
                traceback.print_exc()
    finally:
        # This suite's own config folder and thinking setting. Never the
        # owner's: _TMP is what jarvis_framework.CONFIG_DIR points at here.
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
