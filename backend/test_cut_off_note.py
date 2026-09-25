"""The owner cut the last spoken answer off (the owner's decision of
2026-09-25; jarvis_agent.CUT_OFF_NOTE, with_cut_off_note; docs/JARVIS-API.md
section 17, 6).

When the owner interrupts Jarvis's spoken answer, the app puts the last
sentence the owner heard on its next question, as `interrupted` on the
newest user message. What is proven, on what really goes to the model:

  - the note is sent, once, just before the newest question, quoting that
    sentence - cleaned to one line and at most CUT_OFF_MAX characters;
  - never first: on a conversation's first question the Jarvis rules go
    first, word for word, then the note (keep_rules_first holds after it);
  - with the spoken-style note too, both are there, neither first;
  - no `interrupted`, an empty one, a number, or one on an EARLIER message:
    sent exactly as it came in;
  - it is never the owner's words: it is a system line added only to the
    request for this PC's model - the caller's `messages` (what the relay
    and the learner read) are unchanged, jarvis_intake.owner_turns() finds
    nothing of it, and chat-history.patch takes `interrupted` off before any
    model or the relay sees the conversation.

    python3 test_cut_off_note.py
"""
import json
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_intake.py")
import jarvis_agent as AG  # noqa: E402
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
        AG.run_local_turn(passed_in, "jarvis-primary", ollama_url=URL,
                          stream_out=lambda b: None, open_stream=opener, enabled_tools=None,
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


HISTORY = [{"role": "user", "content": "what is the weather tomorrow", "provenance": "voice"},
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
    check("just before the newest question, everything else as it came",
          msgs == passed[:-1] + [n, passed[-1]], json.dumps(msgs)[:500])
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
    check("spoken, with history: both notes just before the question, neither first",
          msgs[:len(passed) - 1] == passed[:-1] and msgs[-1] == passed[-1]
          and set(json.dumps(m) for m in msgs[len(passed) - 1:-1])
          == {json.dumps(SPOKEN), json.dumps(note(SAID))}, json.dumps(msgs)[-600:])


def t_nothing_to_say_sends_it_unchanged():
    for name, last in (("no field", {"role": "user", "content": "next"}),
                       ("empty", cut("next", said="", provenance=None)),
                       ("spaces", cut("next", said="   \n ", provenance=None)),
                       ("a number", cut("next", said=12, provenance=None)),
                       ("a list", cut("next", said=["a"], provenance=None))):
        msgs, passed = turn(HISTORY[:1] + [HISTORY[1], last])
        check(f"{name}: sent exactly as it came in", msgs == passed, json.dumps(msgs)[:300])
    earlier = [cut("first", provenance="typed"), {"role": "assistant", "content": "ok"},
               {"role": "user", "content": "second"}]
    msgs, passed = turn(earlier)
    check("on an earlier message only: nothing (it was for that turn)", msgs == passed,
          json.dumps(msgs)[:300])


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
          [m["content"] for m in learnt] == ["what is the weather tomorrow", "what about the weekend"],
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
               t_nothing_to_say_sends_it_unchanged,
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
