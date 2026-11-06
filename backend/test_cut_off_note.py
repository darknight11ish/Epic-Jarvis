"""The owner cut the last spoken answer off (the owner's decision of
2026-09-25; jarvis_agent.CUT_OFF_NOTE, with_cut_off_note; docs/JARVIS-API.md
section 17, 6).

When the owner interrupts Jarvis's spoken answer, the app puts the last
sentence the owner heard on its next question, as `interrupted` on the
newest user message. What is proven, on what really goes to the model:

  - the note is sent, once, just before the newest question, quoting that
    sentence - cleaned to one line and at most CUT_OFF_MAX characters;
  - never first: the Jarvis rules lead EVERY local turn, in the request itself
    (jarvis_agent.with_rules_first, 2026-10-14 - not left to a Modelfile, which
    the owner's everyday model qwen3.5:9b does not have), then the note;
  - with the spoken-style note too, both are there, neither first;
  - no `interrupted`, an empty one, a number, or one on an EARLIER message:
    the rules and then the conversation as it came, with no note added;
  - it is never the owner's words: it is a system line added only to the
    request for this PC's model - the caller's `messages` (what the relay
    and the learner read) are unchanged, jarvis_intake.owner_turns() finds
    nothing of it, and chat-history.patch takes `interrupted` off before any
    model or the relay sees the conversation.

    python3 test_cut_off_note.py
"""
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

# THE QUIZ IS FINISHED HERE (2026-11-04). Wave B's `dress_messages` adds one
# "Personalize Jarvis: the setup quiz is unfinished" system line while the quiz
# is unfinished, and an ABSENT setup.json reads as unfinished (0 of 25 answered)
# - so in a fresh config folder, as in CI, one more system line lands in every
# prompt this file pins word for word. This suite is about the CUT-OFF note and
# nothing else, so it gives itself a finished quiz in its own throwaway config
# folder (never the owner's real one): every check below stays the exact byte
# comparison it was, and the line's own behaviour is proved in
# test_setup_quiz.py. The folder is created BEFORE jarvis_framework is imported,
# because CONFIG_DIR is read once, at import.
_QUIZ_CFG = tempfile.mkdtemp(prefix="jarvis-cut-off-note-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _QUIZ_CFG
os.environ["JARVIS_CONFIG_DIR"] = _QUIZ_CFG
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_intake.py")
import jarvis_setup as _setup  # noqa: E402
Path(_QUIZ_CFG, "setup.json").write_text(json.dumps({
    "version": 2, "completed_version": _setup.QUIZ_VERSION, "runs": 1,
    "dismissed_at": None, "in_progress": {}, "answers": {},
    "completed_at": 1.0, "outcomes": []}), encoding="utf-8")
import jarvis_agent as AG  # noqa: E402
# The owner's manner line (jarvis_manner.py) has its own suite, test_manner.py;
# this one checks the rest of the request word for word, so it is left out here.
AG._manner_now = lambda *a, **k: None
# The Personalize Jarvis line (jarvis_agent.with_setup_state_note, Wave B
# 2026-11-03) is ONE system line added to every local turn while the quiz is
# unfinished - correct to send, but not inside a test that pins the request
# word for word. test_setup_quiz.py proves that line and its placing.
AG.setup_state_note = lambda: None
import jarvis_intake as IN  # noqa: E402
import _ollama_wire as W  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


BLOCK = {"role": "system", "content": AG.LANE_SYSTEM}
SPOKEN = {"role": "system", "content": AG.SPOKEN_NOTE}
URL = "http://127.0.0.1:11434"
CLIENT_FIELDS = ("provenance", "interrupted")


def note(said):
    return {"role": "system", "content": AG.CUT_OFF_NOTE.format(said=said)}


def turn(request_messages):
    """One turn the way jarvis_hud does it: the loop gets `messages` without
    the apps' fields, and `request` as it arrived. Returns (the messages sent
    to the model, the messages passed in)."""
    passed_in = [{k: v for k, v in m.items() if k not in CLIENT_FIELDS} for m in request_messages]
    before = json.dumps(passed_in)
    sent = []

    def opener(url, body):
        sent.append(json.loads(json.dumps(body)))
        return W.FakeResponse(W.stream([("content", "Sure."), ("done", "stop")]))

    real_get = AG._get_json
    AG._get_json = lambda *a, **k: (_ for _ in ()).throw(OSError("no network in this test"))
    try:
        # NO TOOLS ARE OFFERED, and that is deliberate (2026-11-04).
        # `enabled_tools=None` means "every tool this module has"
        # (`offered_tools`' own docstring) and it is the wrong stand-in for a
        # real turn here: jarvis_hud passes the owner's `[tools].enabled`
        # list, which the shipped file makes 14 tools and 2,924 tokens. This
        # suite is about the cut-off note and where it sits, and the tool
        # catalogue now costs 11,806 of a 16,384-token turn - leaving about
        # 1,600 tokens for the conversation, which this fixture's own three
        # messages (1,697 with the spoken note) do not fit in. Compaction then
        # does exactly its job: it folds the history into an "[EARLIER IN
        # THIS CONVERSATION]" digest, so the checks that pin "the history ...
        # as they came" can never pass. CI run 41866121515, job
        # `backend`/`backend-windows`, failed exactly that way on 2026-11-04
        # once the six GitHub tool schemas (1,269 tokens together, each well
        # inside the 300-token rule test_tool_text.py enforces) were added.
        # With no tools the same window leaves 13,619 tokens, and every
        # check keeps its assertion. `test_compaction.py` and `test_agent.py`
        # are the suites that prove what a too-long prompt does. This is the
        # same shape as the quiz line's own fix at the top of this file
        # (2026-11-04): keep this suite free of unrelated prompt growth rather
        # than loosen a check that pins the request.
        AG.run_local_turn(passed_in, "jarvis-primary", ollama_url=URL,
                          stream_out=lambda b: None, open_stream=opener,
                          enabled_tools=set(),
                          context_length=16384,
                          request={"model": "jarvis-primary", "stream": True,
                                   "messages": request_messages},
                          on_step=lambda s: None, record_chain=lambda s: None,
                          keepalive_seconds=60, status_delay=60, lane_choice=None)
    finally:
        AG._get_json = real_get
    check("the caller's messages are not changed by the turn",
          json.dumps(passed_in) == before, json.dumps(passed_in)[:300])
    return sent[0]["messages"], passed_in


# Not "what is the weather tomorrow": since 2026-09-26 that plain question
# is answered without the model (jarvis_quick, the weather from Home
# Assistant), and a command is never read by the learner.
HISTORY = [{"role": "user", "content": "what will the weather be like tomorrow",
            "provenance": "voice"},
           {"role": "assistant", "content": "Tomorrow looks mild, with light rain in the "
                                            "morning. It clears by noon. Take a coat."}]
SAID = "Tomorrow looks mild, with light rain in the morning."


def cut(text, said=SAID, provenance="voice"):
    m = {"role": "user", "content": text, "interrupted": said}
    if provenance:
        m["provenance"] = provenance
    return m


def t_the_note_goes_just_before_the_newest_question():
    msgs, passed = turn(HISTORY + [cut("what about the weekend", provenance="typed")])
    n = note(SAID)
    check("sent, once", msgs.count(n) == 1, json.dumps(msgs)[:500])
    check("just before the newest question, everything else as it came after "
          "the rules",
          msgs == [BLOCK] + passed[:-1] + [n, passed[-1]], json.dumps(msgs)[:500])
    check("it quotes the sentence the owner heard", SAID in n["content"])


def t_never_first():
    msgs, passed = turn([cut("no, the other one", provenance="typed")])
    check("first question: the Jarvis rules first, word for word, then the note",
          msgs == [BLOCK, note(SAID)] + passed, json.dumps(msgs)[:400])
    msgs, passed = turn([cut("no, the other one")])
    check("spoken too: the rules, the spoken note, the cut-off note, the question",
          msgs[0] == BLOCK and msgs[-1] == passed[-1]
          and SPOKEN in msgs and note(SAID) in msgs and msgs[0] not in (SPOKEN, note(SAID)),
          json.dumps(msgs)[:500])
    msgs, passed = turn(HISTORY + [cut("the weekend")])
    check("spoken, with history: the rules, then the history and the question as "
          "they came, both notes between them and neither first",
          msgs[0] == BLOCK and msgs[1:len(passed)] == passed[:-1]
          and msgs[-1] == passed[-1]
          and set(json.dumps(m) for m in msgs[len(passed):-1])
          == {json.dumps(SPOKEN), json.dumps(note(SAID))}, json.dumps(msgs)[-600:])


def t_a_folded_history_keeps_both_notes_between_it_and_the_question():
    """The same thing on a conversation that really does not fit.

    On a 16,384-token turn the prompt can be too long, and then
    `run_local_turn` does not merely drop the oldest turns: it folds them into
    ONE "[EARLIER IN THIS CONVERSATION]" digest, in their place
    (jarvis_compaction, `compact_messages`). The two notes must survive that -
    between the digest and the newest question, neither of them first - or a
    spoken question in a long chat would lose exactly the sentence the owner
    had just heard cut off.

    This is the case the fixture above used to reach by ACCIDENT on
    2026-11-04, when offering every tool left about 1,600 tokens for the
    conversation and folded a THREE-message history (CI run 41866121515,
    `backend` and `backend-windows`). Here it is reached on purpose, so the
    behaviour is pinned instead of the accident.
    """
    long_history = []
    for i in range(20):
        long_history.append({"role": "user", "provenance": "typed",
                             "content": f"question {i}: " + "word " * 400})
        long_history.append({"role": "assistant", "content": f"answer {i}: " + "word " * 400})
    msgs, passed = turn(long_history + [cut("the weekend")])
    digest = [m for m in msgs
              if str(m.get("content") or "").startswith("[EARLIER IN THIS CONVERSATION]")]
    check("a long history is really folded: one digest, and turns are gone",
          len(digest) == 1 and len(msgs) < len(long_history) + 2,
          f"{len(msgs)} sent of {len(long_history) + 2}")
    if not digest:
        return
    at = msgs.index(digest[0])
    check("the rules are still first, before the digest", msgs[0] == BLOCK and at > 0)
    check("the newest question is still last", msgs[-1] == passed[-1])
    check("both notes are still there, between the digest and the question",
          SPOKEN in msgs[at + 1:] and note(SAID) in msgs[at + 1:],
          json.dumps(msgs)[-600:])
    check("neither note is first", msgs[0] not in (SPOKEN, note(SAID)))
    check("the cut-off note still quotes the sentence the owner heard",
          note(SAID) in msgs[at + 1:] and SAID in str(note(SAID)["content"]))


def t_nothing_to_say_adds_no_note():
    for name, last in (("no field", {"role": "user", "content": "next"}),
                       ("empty", cut("next", said="", provenance=None)),
                       ("spaces", cut("next", said="   \n ", provenance=None)),
                       ("a number", cut("next", said=12, provenance=None)),
                       ("a list", cut("next", said=["a"], provenance=None))):
        msgs, passed = turn(HISTORY[:1] + [HISTORY[1], last])
        check(f"{name}: no cut-off note - the rules, then the turn as it came",
              msgs == [BLOCK] + passed, json.dumps(msgs)[:300])
    earlier = [cut("first", provenance="typed"), {"role": "assistant", "content": "ok"},
               {"role": "user", "content": "second"}]
    msgs, passed = turn(earlier)
    check("on an earlier message only: nothing (it was for that turn)",
          msgs == [BLOCK] + passed, json.dumps(msgs)[:300])


def t_the_sentence_is_cleaned():
    long = "word " * 200
    words = AG.cut_off_words(long)
    check("at most CUT_OFF_MAX characters", len(words) <= AG.CUT_OFF_MAX, len(words))
    check("one line", "\n" not in AG.cut_off_words("one\ntwo\r\nthree"))
    check("its double quotes cannot close the quote", '"' not in AG.cut_off_words('say "hi" now'))
    check("not text: nothing", AG.cut_off_words(None) == "" and AG.cut_off_words(3) == "")


def t_it_is_never_the_owners_words():
    request = HISTORY + [cut("what about the weekend")]
    msgs, passed = turn(request)
    learnt = IN.owner_turns(request, IN.ORIGIN_OWNER)
    check("the learner reads the owner's questions only, and nothing of the note",
          [m["content"] for m in learnt] == ["what will the weather be like tomorrow",
                                             "what about the weekend"],
          learnt)
    check("the note is a system line, not a user one",
          all(m.get("role") == "system" for m in msgs if "interrupted your last" in str(m.get("content"))))
    check("the relay's copy (the messages passed in) never had it",
          not any("interrupted your last" in str(m.get("content")) for m in passed))
    # chat-history.patch takes the field off before any model or the relay.
    patch = (HERE / "chat-history.patch").read_text(encoding="utf-8")
    line = next((l for l in patch.splitlines() if l.startswith("+_CHAT_CLIENT_FIELDS = ")), "")
    check("chat-history.patch strips `interrupted` with the apps' other fields",
          re.search(r'"interrupted"', line) is not None, line)


def t_the_note_says_what_happened():
    text = AG.CUT_OFF_NOTE.lower()
    for words in ("interrupted", "heard", "nothing after", "do not go on", "only if they ask"):
        check(f"the note says {words!r}", words in text, AG.CUT_OFF_NOTE)


if __name__ == "__main__":
    for fn in (t_the_note_goes_just_before_the_newest_question,
               t_never_first,
               t_a_folded_history_keeps_both_notes_between_it_and_the_question,
               t_nothing_to_say_adds_no_note,
               t_the_sentence_is_cleaned,
               t_it_is_never_the_owners_words,
               t_the_note_says_what_happened):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
