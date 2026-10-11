"""WHEN Jarvis thinks is the owner's choice, and asking for it works, 2026-10-11.

    python3 test_thinking_when.py

THE PROBLEM, MEASURED. The everyday model is becoming `qwen3.5:9b`, a model
that thinks before it answers. Measured on this PC with `qwen3:8b` (the same
behaviour as `ornith:9b`): thinking left on with a normal answer allowance
spent EVERY token reasoning and came back with an EMPTY answer on all three
test questions - `done_reason: "length"`, `content: ""`; with thinking off the
correct answer came back in 0.29 s. Whether an ordinary answer thinks first is
therefore not a default this repository may pick for the owner, and it is not
one any app may pick for him either.

WHAT WAS BUILT

  1. A setting with two plain choices (jarvis_thinking.py, stored in the same
     `thinking.json` the thinking levels already live in):

        "Only when I ask"  ordinary answers are written straight away; Jarvis
                           thinks on the questions the owner asks him to
                           think about
        "Always"           every answer may think first

     A missing, empty, truncated or unreadable file reads as "Only when I ask".
     That is the safe one, and the check below is why: falling back to
     "Always" would fall back to the exact fault this setting exists to
     prevent - a blank answer - and the owner would have no way to tell a
     wrong answer from no answer at all.

  2. ONE QUESTION can ask for thinking without changing that setting: the
     phone's "Think" key sends `"think": true` with that turn only. This suite
     proves the flag reaches the REQUEST OLLAMA IS SENT - not merely that a
     variable somewhere changed - by reading the JSON body the turn really
     put on the wire.

  3. It can never be the reason an answer comes back blank or a message fails
     to send. Three rules outrank it, all of them checked here: a spoken turn
     (a voice answer cannot wait for a long think), a model that cannot think
     at all, and the answer's own room - thinking and the answer share one
     allowance (jarvis_agent.REASONING_MIN_ANSWER_TOKENS), so a question asked
     for thinking about on a turn with too little room is still answered
     directly.

No network, no model, no socket: every reply here comes from _ollama_wire.py,
which transcribes what Ollama really sends.

Run with JARVIS_BACKEND set (a real install) and the suite stops plainly
unless the backend holds this repository's jarvis_thinking.py and
jarvis_agent.py - a suite that tested the repository's copy while reporting on
the installed one would be exactly the kind of claim this fix is about.
"""
import json
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

#: The config folder jarvis_thinking writes its setting into. jarvis_framework
#: is replaced BEFORE anything imports it, so this suite chooses its own
#: thinking setting and never reads or writes the owner's own file. It is
#: removed again at the end of the run.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-thinking-when-"))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.load_framework = lambda *a, **k: {}
_fw.audit_log = lambda *a, **k: None
sys.modules["jarvis_framework"] = _fw

require_shipped("jarvis_thinking.py", "jarvis_agent.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_thinking as JT  # noqa: E402
import _ollama_wire as W  # noqa: E402

AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

FAILED, PASSED, SKIPPED = [], [], []
MODEL = "qwen3.5:9b"
URL = "http://127.0.0.1:11434"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   The model, as a stand-in: one request, one canned answer
# --------------------------------------------------------------------------

class FakeOllama:
    """What the turn asks to send, and a real Ollama stream back.

    `payloads` keeps every request body the turn really put on the wire, as
    the JSON text it sent - which is what "the flag reaches the model" has to
    mean. `last` is the most recent one, parsed.
    """

    def __init__(self, events):
        self.events = events
        self.payloads = []

    def open(self, url, payload):
        self.payloads.append(payload)
        return W.FakeResponse(W.stream(self.events))

    @property
    def last(self) -> dict:
        return self.payloads[-1] if self.payloads else {}


ANSWER = [("content", "The capital of France is Paris."), ("done", "stop")]
REASONING_FIRST = [("reasoning", "The user asks about France. "),
                   ("content", "The capital of France is Paris."),
                   ("done", "stop")]


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


def _model_can_think(url=URL, model=MODEL):
    """This PC's Ollama, stood in for: /api/show says this model can think.
    Written through the same override jarvis_thinking's own suite uses, so
    nothing here goes near a socket."""
    JT._CAP_OVERRIDE[(url, model)] = ["completion", "tools", "thinking"]


def _fresh():
    """No thinking setting of any kind - the state the owner's PC is in before
    anything is chosen."""
    JT.reset_for_tests()
    _model_can_think()


# --------------------------------------------------------------------------
#   1. The setting, and the fallback that is safe
# --------------------------------------------------------------------------

def t_the_two_choices_are_plain_and_the_default_is_the_safe_one():
    _fresh()
    check("nothing chosen reads as 'only when I ask'",
          JT.get_when() == JT.WHEN_ASKED, JT.get_when())
    check("and there are exactly two choices",
          list(JT.WHEN_MODES) == [JT.WHEN_ASKED, JT.ALWAYS], list(JT.WHEN_MODES))
    for mode in JT.WHEN_MODES:
        label = JT.WHEN_LABELS.get(mode, "")
        why = JT.WHEN_WHY.get(mode, "")
        check(f"'{mode}' has a short label a beginner can read",
              bool(label) and len(label) <= 24 and label[0].isupper(), label)
        check(f"'{mode}' says what it does in plain words", len(why) > 40, why)
        check(f"'{mode}' says nothing about tokens or reasoning_effort",
              not any(w in why.lower() for w in ("token", "reasoning", "json", "api")), why)
    check("the everyday choice names the extra step as thinking, as the rest of "
          "this feature does", "think" in JT.WHEN_DETAIL.lower(), JT.WHEN_DETAIL)


def t_a_missing_or_unreadable_setting_never_turns_thinking_on():
    """The one fallback this repository may not get wrong: a file that is
    missing, empty, truncated or unreadable must answer directly, because
    thinking on is what returns an empty answer."""
    for damaged in (None, "", "{not json", "[]", '"a string"',
                    '{"when": "sometimes"}', '{"when": null}', '{"when": true}'):
        _fresh()
        if damaged is not None:
            JT.settings_path().write_text(damaged, encoding="utf-8")
        check(f"a setting file of {damaged!r} reads as 'only when I ask'",
              JT.get_when() == JT.WHEN_ASKED, JT.get_when())
        check(f"...and a plain question thinks nothing ({damaged!r})",
              AG.chat_body(MODEL, [], {"max_tokens": AG.DEFAULT_MAX_TOKENS},
                           ollama_url=URL, role="everyday").get("reasoning_effort") == "none")
    _fresh()


def t_always_is_a_choice_the_owner_makes_and_it_sticks():
    _fresh()
    JT._CAP_OVERRIDE[(URL, "second")] = ["thinking"]
    code, out = JT.set_when(JT.ALWAYS)
    check("choosing Always is accepted", code == 200 and out.get("ok") is True, repr(out))
    check("and it says what it costs, in plain words",
          "conversation room" in out.get("why", ""), repr(out))
    check("it is remembered", JT.get_when() == JT.ALWAYS)
    check("and the next ordinary question really does think",
          AG.chat_body(MODEL, [], {"max_tokens": AG.DEFAULT_MAX_TOKENS},
                       ollama_url=URL, role="everyday").get("reasoning_effort") == "low",
          repr(AG.chat_body(MODEL, [], {"max_tokens": AG.DEFAULT_MAX_TOKENS},
                            ollama_url=URL, role="everyday")))
    code, out = JT.set_when("sometimes")
    check("a third choice is refused in plain words",
          code == 400 and "must be one of" in out.get("error", ""), repr(out))
    check("...and changes nothing", JT.get_when() == JT.ALWAYS)
    _fresh()


def t_the_two_halves_of_the_setting_never_clobber_each_other():
    """A level and WHEN live in one small file. Picking one must not drop the
    other - the owner would set "Always" and lose the level he chose."""
    _fresh()
    JT.set_level("everyday", JT.DEEP, model_name=MODEL, ollama_url=URL)
    JT.set_when(JT.ALWAYS)
    check("choosing WHEN keeps the level", JT.get_level("everyday") == JT.DEEP,
          JT.get_level("everyday"))
    JT.set_level("everyday", JT.QUICK, model_name=MODEL, ollama_url=URL)
    check("choosing a level keeps WHEN", JT.get_when() == JT.ALWAYS, JT.get_when())
    check("the file is one small object the owner could read",
          set(json.loads(JT.settings_path().read_text(encoding="utf-8")))
          == {"everyday", "second", "third", "when", "chosen"},
          JT.settings_path().read_text(encoding="utf-8"))
    check("and neither bookkeeping key can be read as a model's level",
          JT.get_level(JT.WHEN_KEY) == JT.OFF
          and JT.get_level("chosen") == JT.OFF,
          f"{JT.get_level(JT.WHEN_KEY)} / {JT.get_level('chosen')}")
    _fresh()


def t_the_status_view_carries_the_choice_for_both_apps():
    _fresh()
    view = JT.status()
    check("GET /api/thinking says when thinking happens", view.get("when") == JT.WHEN_ASKED,
          repr(view.get("when")))
    ids = [c.get("id") for c in view.get("when_choices", [])]
    check("it offers exactly the two choices, in order",
          ids == [JT.WHEN_ASKED, JT.ALWAYS], repr(ids))
    check("the one in force is marked", [c.get("selected") for c in view["when_choices"]]
          == [True, False], repr(view["when_choices"]))
    check("a POST carrying 'when' goes to the WHEN setting, not to a level",
          JT.handle_set({"when": JT.ALWAYS})[0] == 200
          and JT.get_when() == JT.ALWAYS and JT.get_level("everyday") == JT.OFF)
    check("a POST carrying a level still goes to the level",
          JT.handle_set({"role": "everyday", "level": JT.QUICK})[0] == 200
          and JT.get_level("everyday") == JT.QUICK and JT.get_when() == JT.ALWAYS)
    _fresh()


# --------------------------------------------------------------------------
#   2. One question can ask for thinking - and it reaches the model
# --------------------------------------------------------------------------

def t_the_flag_reaches_the_request_ollama_is_sent():
    """The whole point. Not "a variable changed": the JSON body the turn put
    on the wire carries the reasoning level the level setting asks for."""
    _fresh()
    JT.set_level("everyday", JT.DEEP, model_name=MODEL, ollama_url=URL)
    ollama = FakeOllama(REASONING_FIRST)
    turn(ollama, question="What is the capital of France?",
         request={"max_tokens": AG.DEFAULT_MAX_TOKENS, "think": True})
    sent = ollama.last
    check("exactly one request was sent", len(ollama.payloads) == 1, str(len(ollama.payloads)))
    check("the request the model is sent carries thinking ON",
          sent.get("reasoning_effort") == "high", repr(sent.get("reasoning_effort")))
    check("the question really is the one asked",
          any(m.get("content") == "What is the capital of France?"
              for m in sent.get("messages", []) if isinstance(m, dict)), repr(sent.get("messages")))
    check("the answer still arrives",
          ollama.events[-1][1] == "stop", repr(ollama.events))
    _fresh()


def t_the_same_question_without_the_flag_thinks_nothing():
    """The control for the check above: same model, same level, same words -
    only the flag differs. Without it, the request carries thinking off."""
    _fresh()
    JT.set_level("everyday", JT.DEEP, model_name=MODEL, ollama_url=URL)
    ollama = FakeOllama(ANSWER)
    turn(ollama, question="What is the capital of France?",
         request={"max_tokens": AG.DEFAULT_MAX_TOKENS})
    check("an ordinary question's request leaves thinking off",
          ollama.last.get("reasoning_effort") == "none", repr(ollama.last))
    _fresh()


def t_asking_for_one_question_does_not_change_the_setting():
    _fresh()
    JT.set_level("everyday", JT.DEEP, model_name=MODEL, ollama_url=URL)
    ollama = FakeOllama(ANSWER)
    turn(ollama, question="What is the capital of France?",
         request={"max_tokens": AG.DEFAULT_MAX_TOKENS, "think": True})
    check("the WHEN setting is untouched by the flag",
          JT.get_when() == JT.WHEN_ASKED, JT.get_when())
    check("so is the level", JT.get_level("everyday") == JT.DEEP, JT.get_level("everyday"))
    after = FakeOllama(ANSWER)
    turn(after, question="And the capital of Spain?",
         request={"max_tokens": AG.DEFAULT_MAX_TOKENS})
    check("and the NEXT question is an ordinary one again",
          after.last.get("reasoning_effort") == "none", repr(after.last))
    _fresh()


def t_only_the_apps_own_true_asks_for_thinking():
    """"think": "yes" is not a request to think - the same rule the chat
    route's own `temporary` flag follows."""
    check("the app's own true asks for it", JT.asked_for_this_turn({"think": True}) is True)
    for other in ({}, {"think": False}, {"think": "true"}, {"think": "yes"},
                  {"think": 1}, {"think": 0}, {"think": None}, None, [], "", True):
        check(f"{other!r} is not a request to think",
              JT.asked_for_this_turn(other) is False)
    check("jarvis_agent reads the request the same way",
          AG.think_asked_for({"think": True}) is True
          and AG.think_asked_for({"think": "yes"}) is False
          and AG.think_asked_for(None) is False)


# --------------------------------------------------------------------------
#   3. The three things that outrank it
# --------------------------------------------------------------------------

def t_a_spoken_answer_never_waits_for_a_long_think():
    _fresh()
    JT.set_level("everyday", JT.DEEP, model_name=MODEL, ollama_url=URL)
    check("a spoken turn thinks nothing, even asked for",
          AG.chat_body(MODEL, [], {"max_tokens": AG.DEFAULT_MAX_TOKENS}, spoken=True,
                       ollama_url=URL, role="everyday",
                       per_turn=True).get("reasoning_effort") == "none")


def t_a_model_that_cannot_think_is_never_offered_it():
    JT.reset_for_tests()
    JT._CAP_OVERRIDE[(URL, "plain:8b")] = ["completion", "tools"]
    check("a model with no thinking capability is asked for none, even asked for",
          AG.chat_body("plain:8b", [], {"max_tokens": AG.DEFAULT_MAX_TOKENS},
                       ollama_url=URL, role="everyday",
                       per_turn=True).get("reasoning_effort") == "none")
    _fresh()


def t_too_little_room_outranks_the_owners_question():
    """Thinking and the answer share ONE allowance (the measured defect this
    repository already fixed). A question asked for thinking about whose
    answer has too little room is answered directly rather than blank."""
    _fresh()
    JT.set_level("everyday", JT.DEEP, model_name=MODEL, ollama_url=URL)
    check("the floor is still where the measurement put it",
          AG.REASONING_MIN_ANSWER_TOKENS == 192, str(AG.REASONING_MIN_ANSWER_TOKENS))
    short = AG.chat_body(MODEL, [], {"max_tokens": AG.REASONING_MIN_ANSWER_TOKENS - 1},
                         ollama_url=URL, role="everyday", per_turn=True)
    check("a short allowance is not shared with thinking, asked for or not",
          short.get("reasoning_effort") == "none", repr(short))
    roomy = AG.chat_body(MODEL, [], {"max_tokens": AG.REASONING_MIN_ANSWER_TOKENS},
                         ollama_url=URL, role="everyday", per_turn=True)
    check("an allowance exactly at the floor is enough, asked for",
          roomy.get("reasoning_effort") == "high", repr(roomy))


def t_a_question_asked_for_on_a_short_turn_still_answers():
    """The end of the same point, through a whole turn: the answer is not
    empty, and nothing of the model's reasoning is shown."""
    _fresh()
    JT.set_level("everyday", JT.DEEP, model_name=MODEL, ollama_url=URL)
    ollama = FakeOllama(REASONING_FIRST)
    body, summary, _said = turn(ollama, question="What is the capital of France?",
                                request={"max_tokens": 128, "think": True})
    check("the request really sent carries thinking off",
          ollama.last.get("reasoning_effort") == "none", repr(ollama.last))
    check("and the answer is not empty",
          summary.get("answer") == "The capital of France is Paris.", repr(summary.get("answer")))
    check("the app is told how the answer ended, as always",
          summary.get("finish_reason") == "stop", repr(summary))
    check("nothing of the model's reasoning is shown",
          b"Paris" in body and b"The user asks" not in body, repr(body))


def t_the_flag_never_reaches_a_model_as_a_word():
    """A request field is not a message. None of the apps' bookkeeping fields
    (think, conversation_id, device, provenance) may ride along as an option
    of the request the model is sent, or as a word in a message.

    Notes on what is safe to assert here: the Jarvis rules block in the system
    message is the repository's own prose, so a bare word like "device" may
    appear inside it. What must never appear is the FIELD - and that is what
    is checked, both as a top-level key of the request and as the exact JSON a
    message would carry it in."""
    _fresh()
    ollama = FakeOllama(ANSWER)
    turn(ollama, question="What is the capital of France?",
         request={"max_tokens": AG.DEFAULT_MAX_TOKENS, "think": True,
                  "conversation_id": "conv-thinking1", "device": "phone"})
    sent = ollama.last
    for field in ("think", "conversation_id", "device", "provenance", "provenance_note"):
        check(f"'{field}' is not an option of the request the model is sent",
              field not in sent, repr(sorted(sent)))
    after = json.dumps(sent)
    for carried in ('"think": true', '"device": "phone"',
                    '"conversation_id": "conv-thinking1"'):
        check(f"{carried} appears nowhere in what the model is sent",
              carried not in after, after[:400])
    check("no message carries an app field either",
          not any(k in m for m in sent.get("messages", []) if isinstance(m, dict)
                  for k in ("think", "conversation_id", "device", "provenance")),
          repr(sent.get("messages")))
    check("the request's own options are still sent, exactly as before",
          sent.get("stream") is True and sent.get("max_tokens") == AG.DEFAULT_MAX_TOKENS,
          repr({k: v for k, v in sent.items() if k != "messages"}))
    check("and thinking is on for this turn, which is the whole point",
          sent.get("reasoning_effort") == "low", repr(sent.get("reasoning_effort")))


def t_the_owners_own_config_folder_is_never_touched():
    check("this suite's thinking setting lives in its own folder",
          str(JT.settings_path()).startswith(str(_TMP)), str(JT.settings_path()))
    check("and this suite never read or wrote the owner's own folder",
          str(_TMP) in str(JT._config_dir()), str(JT._config_dir()))


if __name__ == "__main__":
    try:
        for fn in (t_the_two_choices_are_plain_and_the_default_is_the_safe_one,
                   t_a_missing_or_unreadable_setting_never_turns_thinking_on,
                   t_always_is_a_choice_the_owner_makes_and_it_sticks,
                   t_the_two_halves_of_the_setting_never_clobber_each_other,
                   t_the_status_view_carries_the_choice_for_both_apps,
                   t_the_flag_reaches_the_request_ollama_is_sent,
                   t_the_same_question_without_the_flag_thinks_nothing,
                   t_asking_for_one_question_does_not_change_the_setting,
                   t_only_the_apps_own_true_asks_for_thinking,
                   t_a_spoken_answer_never_waits_for_a_long_think,
                   t_a_model_that_cannot_think_is_never_offered_it,
                   t_too_little_room_outranks_the_owners_question,
                   t_a_question_asked_for_on_a_short_turn_still_answers,
                   t_the_flag_never_reaches_a_model_as_a_word,
                   t_the_owners_own_config_folder_is_never_touched):
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
