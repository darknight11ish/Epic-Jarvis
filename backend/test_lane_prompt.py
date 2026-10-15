"""test_lane_prompt.py - the Jarvis rules reach the MAIN lane too (2026-10-14).

    python3 backend/test_lane_prompt.py

THE FAULT THIS HOLDS SHUT. `jarvis_agent.run_local_turn` sent LANE_SYSTEM
(Jarvis's own rules, the Modelfile's SYSTEM block word for word) only on a
second-card lane, on the belief - written at the constant - that "the everyday
model has them built in". The owner's everyday model since 2026-10-10 is
`qwen3.5:9b`, a plain library pull with NO SYSTEM of its own (`ollama show
qwen3.5:9b --system` prints nothing on his PC), and Ollama adds a Modelfile
SYSTEM block only when the request does not already start with a system
message. So a fresh main-lane turn was the owner's question and nothing else:
the honesty rule ("Never claim an action was taken that was not") was not in
front of the model on the lane he actually uses.

No Ollama, no network. Two halves:

  1. `with_rules_first(msgs)` - the one rule, on its own. Every shape of list a
     turn can really start from, plus the shapes where BOTH the rules and
     something else would apply (a recalled-facts block, an app's own system
     message), because the fault this fix could introduce is a SECOND
     competing system turn, not a missing one.
  2. The whole turn, through the real `run_local_turn` and a fake Ollama, so
     this fails if the main lane ever stops sending the rules again - and so
     the second-card lane and the recalled-facts turn are both measured
     alongside it, on the same request, rather than assumed.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# ...and the ten modules this repository ships WHOLE, from backend/rebuilt/ -
# the same two lines test_agent.py carries, for the same reason.
sys.path.insert(0, str(HERE / "rebuilt"))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
import jarvis_agent as AG  # noqa: E402
import _ollama_wire as W  # noqa: E402

FAILED, PASSED = [], []
AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


RULES = {"role": "system", "content": AG.LANE_SYSTEM}
RECALLED = {"role": "system", "content": "Things you know about the user: recalled facts"}
APP_MSG = {"role": "system", "content": "Context:\nsome copied text"}
QUESTION = {"role": "user", "content": "hello"}


def rules_in(msgs):
    """How many messages in `msgs` ARE the rules block, word for word."""
    return sum(1 for m in msgs
               if isinstance(m, dict) and m.get("role") == "system"
               and m.get("content") == AG.LANE_SYSTEM)


# --------------------------------------------------------------------------
#   1. The one rule, on its own
# --------------------------------------------------------------------------

def t_with_rules_first_gives_every_shape_of_turn_the_rules_once():
    cases = [
        ("a first question and nothing else", [dict(QUESTION)], [RULES, QUESTION]),
        ("a recalled-facts block first (a first question)", [dict(RECALLED), dict(QUESTION)],
         [RULES, RECALLED, QUESTION]),
        ("an app's own leading system message", [dict(APP_MSG), dict(QUESTION)],
         [RULES, APP_MSG, QUESTION]),
        ("a conversation already under way", [{"role": "assistant", "content": "hi"},
                                              dict(QUESTION)],
         [RULES, {"role": "assistant", "content": "hi"}, QUESTION]),
        ("the rules already first (the second card's own call)", [dict(RULES), dict(QUESTION)],
         [RULES, QUESTION]),
        ("a system message inside a chat, not first",
         [dict(QUESTION), dict(RECALLED), {"role": "assistant", "content": "x"}],
         [RULES, QUESTION, RECALLED, {"role": "assistant", "content": "x"}]),
        ("nothing at all", [], [RULES]),
    ]
    for label, given, want in cases:
        frozen = json.dumps(given, sort_keys=True)
        got = AG.with_rules_first(given)
        check(f"with_rules_first: {label} - the rules first, once",
              got == want, got)
        check(f"  ... and {label}: exactly one rules block, never two",
              rules_in(got) == 1, rules_in(got))
        check(f"  ... and {label}: the list it was given is not changed",
              json.dumps(given, sort_keys=True) == frozen, given)


def t_with_rules_first_does_not_change_the_list_it_is_given():
    given = [dict(QUESTION)]
    copy = [dict(QUESTION)]
    AG.with_rules_first(given)
    check("with_rules_first returns a new list - the caller's own list is untouched",
          given == copy, given)
    same = [dict(RULES), dict(QUESTION)]
    AG.with_rules_first(same)
    check("... and it does not re-copy or reorder a list that already starts with them",
          same == [RULES, QUESTION], same)


def t_both_lanes_and_the_facts_turn_agree_on_one_rules_block():
    """The fault this fix could introduce: two competing system turns."""
    both = AG.with_rules_first([dict(RECALLED), dict(APP_MSG), dict(QUESTION)])
    check("recalled facts AND an app's own message AND the rules: still ONE rules block",
          rules_in(both) == 1 and both[0] == RULES, both)
    twice = AG.with_rules_first(AG.with_rules_first([dict(QUESTION)]))
    check("... applying it twice does not stack a second one", rules_in(twice) == 1, twice)
    after_repair = AG.keep_rules_first(AG.with_rules_first([dict(QUESTION)]))
    check("... and keep_rules_first (which runs last in dress_messages) leaves it alone",
          after_repair == [RULES, QUESTION] and rules_in(after_repair) == 1, after_repair)


# --------------------------------------------------------------------------
#   2. The whole turn, through the real run_local_turn
# --------------------------------------------------------------------------

def first_request(msgs, *, ctx=16384, lane=None, request=None):
    """The first request one local turn really sends, as (url, body)."""
    sent = []

    def opener(url, body):
        sent.append((url, body))
        return W.FakeResponse(W.stream([("content", "ok"), ("done", "stop")]))

    AG.run_local_turn(msgs, "jarvis-primary", ollama_url="http://127.0.0.1:11434",
                      stream_out=lambda b: None, open_stream=opener,
                      enabled_tools=set(), context_length=ctx, on_step=lambda s: None,
                      record_chain=lambda s: None, keepalive_seconds=60,
                      status_delay=60, lane_choice=lane, request=request,
                      manner=None)
    return sent[0]


def t_the_main_lane_request_starts_with_the_rules():
    """THE test that fails if the main lane loses its prompt again."""
    url, body = first_request([dict(QUESTION)])
    got = body["messages"]
    check("a fresh main-lane turn is sent with the Jarvis rules as message 0",
          got[:1] == [RULES], got[:2])
    check("... and the owner's own question still follows it, unchanged",
          got[1:] == [QUESTION], got[1:])
    check("... and the rules are in the REQUEST, not left to the model's own Modelfile "
          "(the owner's everyday model has none)",
          json.dumps(body["messages"]).count(json.dumps(AG.LANE_SYSTEM)[1:-1]) == 1,
          json.dumps(body["messages"])[:200])
    check("CONTROL: the conversation itself was not modified - the rules are added to "
          "the request only, so the app's own history is untouched",
          AG.keep_rules_first([dict(QUESTION)]) == [QUESTION])


def t_a_recalled_facts_turn_does_not_get_two_competing_system_turns():
    url, body = first_request([dict(RECALLED), dict(QUESTION)])
    got = body["messages"]
    check("a recalled-facts first question: the rules first, then the facts, then the "
          "question", got == [RULES, RECALLED, QUESTION], got)
    check("... and exactly one rules block reached the model", rules_in(got) == 1,
          rules_in(got))
    check("... and the recalled facts were not swallowed or reordered",
          [m.get("role") for m in got] == ["system", "system", "user"],
          [m.get("role") for m in got])


def t_the_second_card_lane_still_carries_the_rules_once():
    lane = AG.LaneChoice("http://127.0.0.1:11435", "qwen3:8b", 32768,
                         "long_context", "test")
    url, body = first_request([dict(QUESTION)], lane=lane)
    got = body["messages"]
    check("a second-card turn starts with the Jarvis rules", got[:1] == [RULES], got[:2])
    check("... and carries exactly ONE rules block (the fix must not double it there)",
          rules_in(got) == 1, rules_in(got))
    check("... and the question still follows it", got[1:] == [QUESTION], got[1:])
    url2, body2 = first_request([dict(RECALLED), dict(QUESTION)], lane=lane)
    check("... even with recalled facts: rules, facts, question - one rules block",
          body2["messages"] == [RULES, RECALLED, QUESTION]
          and rules_in(body2["messages"]) == 1, body2["messages"])


def t_the_warm_up_sends_the_same_start_as_a_real_turn():
    """The warm-up exists to have the rules+tools already read. If a real turn
    starts with the rules and the warm-up does not, the warm-up warms nothing."""
    real = first_request([dict(QUESTION)])[1]["messages"]
    head, tools = AG.chat_prefix(set(), ollama_url="http://127.0.0.1:11434",
                                 model="jarvis-primary", manner=None)
    check("chat_prefix (what the warm-up sends before its one word) starts with the rules",
          head[:1] == [RULES], head[:2])
    check("... and is exactly what a real first question sends before its question",
          head == real[:-1], (head, real[:-1]))
    warm_body = AG.chat_body("jarvis-primary",
                             head + [{"role": "user", "content": AG.WARM_WORD}],
                             {"max_tokens": 1}, tools, spoken=True,
                             ollama_url="http://127.0.0.1:11434")
    check("... and the warm-up's only words from anyone are its one word, after the rules",
          warm_body["messages"][-1] == {"role": "user", "content": AG.WARM_WORD}
          and rules_in(warm_body["messages"]) == 1, warm_body["messages"][:2])


def t_a_short_context_still_keeps_the_rules_after_trimming():
    """fit_messages never drops a system message, and the rules go in BEFORE
    trimming - so a long conversation that must be trimmed keeps them."""
    long = [{"role": "user", "content": "earlier question " + "x" * 6000},
            {"role": "assistant", "content": "earlier answer " + "y" * 6000},
            dict(RECALLED), {"role": "user", "content": "the new question"}]
    url, body = first_request(long, ctx=2048)
    got = body["messages"]
    check("a conversation trimmed to fit still starts with the rules",
          got[:1] == [RULES], [str(m.get("content"))[:24] for m in got])
    check("... exactly once", rules_in(got) == 1, rules_in(got))
    check("CONTROL: trimming really happened, so this measured something",
          not any("earlier question" in str(m.get("content")) for m in got),
          [str(m.get("content"))[:24] for m in got])


if __name__ == "__main__":
    import traceback
    for fn in (t_with_rules_first_gives_every_shape_of_turn_the_rules_once,
               t_with_rules_first_does_not_change_the_list_it_is_given,
               t_both_lanes_and_the_facts_turn_agree_on_one_rules_block,
               t_the_main_lane_request_starts_with_the_rules,
               t_a_recalled_facts_turn_does_not_get_two_competing_system_turns,
               t_the_second_card_lane_still_carries_the_rules_once,
               t_the_warm_up_sends_the_same_start_as_a_real_turn,
               t_a_short_context_still_keeps_the_rules_after_trimming):
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
