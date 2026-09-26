"""Spoken questions get spoken-style answers (the owner's decision of
2026-09-24; jarvis_agent.SPOKEN_NOTE and with_spoken_note).

What is proven, on what really goes to the model:

  - a turn whose NEWEST user message was spoken (`provenance: "voice"` on
    the request as it arrived) gets the note, once, on every round;
  - a typed turn - or one where only an earlier message was spoken - is
    sent exactly as it came in;
  - the note is never the first message, so Ollama still puts the
    Modelfile's SYSTEM block in front; on a conversation's first question
    that block goes first itself, word for word;
  - on the second card, the Jarvis block is not doubled;
  - the note never reaches the caller's `messages` (the relay's copy, the
    only road to a cloud model), and the relay's cut when a turn leaves this
    PC (degrade-filter.patch: user messages only) leaves nothing of it.

    python3 test_spoken_style.py
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
import jarvis_agent as AG  # noqa: E402
# The owner's manner line (jarvis_manner.py) has its own suite, test_manner.py;
# this one checks the rest of the request word for word, so it is left out here.
AG._manner_now = lambda: None
import _ollama_wire as W  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


NOTE = {"role": "system", "content": getattr(AG, "SPOKEN_NOTE", "(no SPOKEN_NOTE)")}
BLOCK = {"role": "system", "content": AG.LANE_SYSTEM}
URL = "http://127.0.0.1:11434"


def turn(request_messages, *, rounds=None, lane_choice=None):
    """Runs one turn the way jarvis_hud does since chat-history.patch: the
    loop gets `messages` WITHOUT provenance, and `request` as it arrived.
    Returns (bodies sent to the model, urls, the messages list passed in)."""
    passed_in = [{k: v for k, v in m.items() if k != "provenance"} for m in request_messages]
    before = json.dumps(passed_in)
    script = iter(rounds or [[("content", "Sure."), ("done", "stop")]])
    sent, urls = [], []

    def opener(url, body):
        urls.append(url)
        sent.append(json.loads(json.dumps(body)))
        return W.FakeResponse(W.stream(next(script)))

    real_get, real_calc = AG._get_json, AG.TOOLS["calculator"].execute
    AG._get_json = lambda *a, **k: (_ for _ in ()).throw(OSError("no network in this test"))
    AG.TOOLS["calculator"].execute = lambda args, state, **kw: {"ok": True, "value": 4}
    try:
        AG.run_local_turn(passed_in, "jarvis-primary", ollama_url=URL,
                          stream_out=lambda b: None, open_stream=opener,
                          enabled_tools={"calculator"}, context_length=16384,
                          request={"model": "jarvis-primary", "stream": True,
                                   "messages": request_messages},
                          gate_check=lambda *a, **k: type("V", (), {"allowed": True,
                                                                    "outcome": "auto",
                                                                    "reason": "x"})(),
                          on_step=lambda s: None, record_chain=lambda s: None,
                          keepalive_seconds=60, status_delay=60, lane_choice=lane_choice)
    finally:
        AG._get_json, AG.TOOLS["calculator"].execute = real_get, real_calc
    check("the caller's messages are not changed by the turn",
          json.dumps(passed_in) == before, json.dumps(passed_in)[:300])
    return sent, urls, passed_in


def voice(text):
    return {"role": "user", "content": text, "provenance": "voice"}


def typed(text):
    return {"role": "user", "content": text, "provenance": "typed"}


HISTORY = [typed("hello"), {"role": "assistant", "content": "Hi. What can I do?"}]


def t_a_spoken_question_gets_the_note_just_before_it():
    sent, _, passed = turn(HISTORY + [voice("what is the weather tomorrow")])
    msgs = sent[0]["messages"]
    check("the note is sent", NOTE in msgs, json.dumps(msgs)[:400])
    check("exactly once", msgs.count(NOTE) == 1)
    check("just before the newest user message, everything else as it came",
          msgs == passed[:-1] + [NOTE, passed[-1]], json.dumps(msgs)[:400])
    check("not first", msgs[0] != NOTE)


def t_a_typed_question_is_sent_unchanged():
    for name, last in (("typed", typed("what is the weather tomorrow")),
                       ("no provenance", {"role": "user", "content": "what is the weather"}),
                       ("pasted", {"role": "user", "content": "x", "provenance": "pasted"}),
                       ("unknown value", {"role": "user", "content": "x", "provenance": "Voice"})):
        sent, _, passed = turn(HISTORY + [last])
        check(f"{name}: sent exactly as it came in", sent[0]["messages"] == passed,
              json.dumps(sent[0]["messages"])[:300])


def t_only_the_newest_message_counts():
    sent, _, passed = turn([voice("hello"), {"role": "assistant", "content": "Hi."},
                            typed("now a typed one")])
    check("an earlier spoken message does not make a typed turn spoken",
          sent[0]["messages"] == passed, json.dumps(sent[0]["messages"])[:300])


def t_the_first_question_keeps_the_jarvis_rules_first():
    # [note, question] would make the note message 0, and Ollama would then
    # leave the Modelfile's SYSTEM block out (memory-prefix.patch).
    sent, _, passed = turn([voice("what time is it")])
    msgs = sent[0]["messages"]
    check("the Modelfile's SYSTEM block, word for word, then the note, then the question",
          msgs == [BLOCK, NOTE] + passed, json.dumps(msgs)[:400])


def t_the_second_card_does_not_get_the_block_twice():
    lane = AG.LaneChoice("http://127.0.0.1:11435", "qwen3:8b", 32768, "long_context", "test")
    sent, urls, passed = turn([voice("summarise this for me")], lane_choice=lane)
    msgs = sent[0]["messages"]
    check("second card: its block first, the note, the question - the block once",
          msgs == [BLOCK, NOTE] + passed, json.dumps(msgs)[:400])
    check("second card: loopback only", all(u.startswith("http://127.0.0.1:") for u in urls), urls)


def t_every_round_of_a_tool_turn_carries_it_once():
    rounds = [
        [("tool_calls", [{"id": "1", "name": "calculator",
                          "arguments": json.dumps({"expression": "2+2"})}]), ("done", "stop")],
        [("content", "Four."), ("done", "stop")],
    ]
    sent, urls, _ = turn(HISTORY + [voice("what is two plus two")], rounds=rounds)
    check("two rounds were asked", len(sent) == 2, len(sent))
    for n, body in enumerate(sent, 1):
        msgs = body["messages"]
        check(f"round {n}: the note once, and not first",
              msgs.count(NOTE) == 1 and msgs[0] != NOTE, json.dumps(msgs)[:400])
    last_user = max(i for i, m in enumerate(sent[1]["messages"]) if m.get("role") == "user")
    check("round 2: still just before the question, with the tool result after it",
          sent[1]["messages"][last_user - 1] == NOTE
          and sent[1]["messages"][-1].get("role") == "tool", json.dumps(sent[1]["messages"])[:500])
    check("every request went to this PC's model", all(u.startswith(URL) for u in urls), urls)


def t_trimming_cannot_leave_the_note_first():
    # A long history that has to be cut down to the question: the note is
    # placed after trimming, so it can never end up at position 0.
    long_history = []
    for n in range(40):
        long_history += [typed(f"question {n} " + "x" * 600),
                         {"role": "assistant", "content": "answer " + "y" * 600}]
    sent, _, passed = turn(long_history + [voice("and the last one")])
    msgs = sent[0]["messages"]
    check("the history really was trimmed", len(msgs) < len(passed), len(msgs))
    check("after trimming: not first, and just before the question",
          msgs[0] != NOTE and msgs[-2] == NOTE and msgs[-1] == passed[-1],
          json.dumps(msgs[:2])[:300])
    # A question so long that every earlier turn has to go.
    sent, _, passed = turn(long_history + [voice("read this back to me " + "z" * 45000)])
    msgs = sent[0]["messages"]
    check("everything earlier trimmed away: the Jarvis block first, then the note",
          msgs == [BLOCK, NOTE, passed[-1]], json.dumps(msgs)[:300])


def t_leaving_this_pc_takes_nothing_of_it():
    # The relay (the only road to a cloud model) works on the caller's
    # `messages`, which the turn above proved unchanged. And when a turn
    # does leave, degrade-filter.patch keeps user messages only.
    sent, _, passed = turn(HISTORY + [voice("what is on my calendar")])
    check("the relay's copy never had it", NOTE not in passed)
    cut = [m for m in sent[0]["messages"] if isinstance(m, dict) and m.get("role") == "user"]
    check("the leaving-local cut keeps no system line", all(m.get("role") == "user" for m in cut)
          and NOTE not in cut)


def t_the_note_says_what_the_owner_decided():
    text = NOTE["content"].lower()
    for words in ("read aloud", "one short sentence", "three sentences", "more detail",
                  "no lists", "markdown", "emojis", "numbers"):
        check(f"the note says {words!r}", words in text, NOTE["content"])


if __name__ == "__main__":
    for fn in (t_a_spoken_question_gets_the_note_just_before_it,
               t_a_typed_question_is_sent_unchanged,
               t_only_the_newest_message_counts,
               t_the_first_question_keeps_the_jarvis_rules_first,
               t_the_second_card_does_not_get_the_block_twice,
               t_every_round_of_a_tool_turn_carries_it_once,
               t_trimming_cannot_leave_the_note_first,
               t_leaving_this_pc_takes_nothing_of_it,
               t_the_note_says_what_the_owner_decided):
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
