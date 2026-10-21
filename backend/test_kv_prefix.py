"""The start of every prompt, made reusable: conversation-sticky canonical
tool order (Gemini work order Layer 2 Opt 2.1, 2026-10-20).

    python3 test_kv_prefix.py

WHY THIS EXISTS. Ollama (llama.cpp) reuses what it has already read of the
last prompt only while the next prompt starts the same way, and the tool list
is part of that start - the short-list section of jarvis_agent.py says so in
its own words ("the tool list sits at the start of the prompt... A list that
changed from turn to turn would be re-read every turn"). The top-K diet
(F1, 2026-10-18) picked tools per QUESTION, so two questions in one
conversation used to send two different `tools` arrays: the whole earlier
conversation after that block was read again. This change carries a
conversation's tools forward in one canonical order.

Opt 2.2 (`keep_alive: -1` on the everyday lane) is NOT part of this change:
the owner's live lanes already answer `expires_at` far in the future
(`OLLAMA_KEEP_ALIVE=-1` is set by the lane launcher), so there is no state for
code to enforce. This suite therefore does not touch keep_alive at all.

WHAT IS PROVEN HERE, and every one of these fails on the code before this
change:

  1. two turns of ONE conversation serialize the SAME `tools` bytes, even
     when the second question names fewer tools than the first - the
     conversation carries them forward in one canonical order;
  2. a DIFFERENT conversation id gets the plain top-K diet for the same
     question (nothing carries over);
  3. a new conversation still gets the diet (a few tools, not the whole
     catalogue), and a full-list fallback turn is not carried forward;
  4. the carried list stops at MAX_STICKY_TOOLS (9), and this turn's own
     diet is never cut to reach that;
  5. a message prefix that has to be COMPACTED starts the tool list over;
  6. a turn that offers no tools at all (a crisis turn, a model that cannot
     use tools) does not wipe the conversation's carried list, and a request
     with no conversation id never clears another conversation's;
  7. the system prefix (the rules block) is byte-identical across turns: the
     work order's "volatile timestamps in token 0" claim is checked, not
     assumed - the agent's system prefix is static (no timestamp or status
     is put there; the per-turn notes go just before the newest question),
     and this test holds the first system message to that byte for byte.

HOW. The model's side of every turn is a scripted stream (`_ollama_wire`,
built from Ollama's own wire format) recorded at the same seam run_local_turn
really posts through, so the JSON body is what would have gone on the wire.
No real Ollama, no card, no network.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# The ten modules this repository ships WHOLE (see test_agent.py's header):
# flattened beside the rest by apply-patches.ps1 and by run_suites.py's
# staging, and here so a direct `python test_kv_prefix.py` measures the same.
sys.path.insert(0, str(HERE / "rebuilt"))
_CFG = tempfile.mkdtemp(prefix="jarvis-kv-prefix-cfg-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _CFG
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py")
import _ollama_wire as W  # noqa: E402
import jarvis_agent as AG  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   The fake model and the fake network
# --------------------------------------------------------------------------

class NoRealIO:
    """Fail loudly if the real (network-touching) post/stream ever runs."""

    def __enter__(self):
        self.real_post, self.real_stream = AG._post, AG._open_stream
        self.real_get = AG._get_json

        def boom_post(*a, **k):
            raise AssertionError("a real HTTP POST ran")

        def boom_stream(*a, **k):
            raise AssertionError("a real streaming request ran")

        def no_lookup(*a, **k):
            raise OSError("no network in this test")
        AG._post, AG._open_stream, AG._get_json = boom_post, boom_stream, no_lookup
        AG._CTX_CACHE.clear()
        AG._TOOLS_CACHE.clear()
        return self

    def __exit__(self, *a):
        AG._post, AG._open_stream = self.real_post, self.real_stream
        AG._get_json = self.real_get
        return False


def _events(resp):
    """A scripted whole response, as the events Ollama streams for it."""
    msg = ((resp.get("choices") or [{}])[0].get("message")) or {}
    ev = []
    text = msg.get("content") or ""
    if text:
        ev.append(("content", text))
    ev.append(("done", "stop"))
    return ev


def scripted_stream(responses):
    """Like test_agent.py's helper: the opener hands back Ollama's real SSE
    body for the next scripted response, and records the JSON body it was
    given - the fake HTTP layer every check below reads."""
    calls = []
    it = iter(responses)

    def opener(url, payload):
        calls.append(payload)
        return W.FakeResponse(W.stream(_events(next(it))))

    return opener, calls


def turn(question, *, cid=None, history=(), enabled=None, messages=None):
    """One real run_local_turn through the scripted opener. Returns
    (captured JSON bodies, summary). The sticky tool state is shared by every
    turn in this process on purpose - these are real conversations.

    `enabled` is left None by default: offered_tools(None) is the documented
    "every tool, for callers and tests that do not read the config" path, so
    the checks below measure the shipped catalogue rather than whatever the
    owner's own [tools].enabled happens to say today.
    """
    AG._CTX_CACHE.clear()
    AG._TOOLS_CACHE.clear()
    msgs = list(history) + [{"role": "user", "content": question}]
    req = {"conversation_id": cid, "stream": True, "messages": list(msgs)}
    opener, calls = scripted_stream(
        [{"choices": [{"message": {"role": "assistant", "content": "done"}}]}])
    with NoRealIO():
        summary = AG.run_local_turn(
            messages if messages is not None else msgs, "qwen3.5:9b",
            ollama_url="http://127.0.0.1:11436", stream_out=lambda b: None,
            enabled_tools=enabled, request=req, gate_check=lambda *a, **k: None,
            open_stream=opener)
    return calls, summary


def tool_names(body):
    return [t["function"]["name"] for t in body.get("tools") or []]


def tool_bytes(body) -> bytes:
    """The serialized `tools` array - the bytes at the start of the prompt."""
    return json.dumps(body.get("tools") or [], separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def reset():
    AG.reset_sticky_tools()


# The two questions used for the carry-forward checks. A names a calendar read
# and a reminder (a chain, so it shows the chain core); B names only the
# calendar, and its own diet is ONE tool. The same conversation's second turn
# must still show A's list, byte for byte; another conversation's B must show
# B's own diet.
Q_A = "what is on my calendar tomorrow, and remind me"
Q_B = "what is on my calendar tomorrow"
CID = "conv-kv-0001"

#: Ten single-subject questions whose matches together name more than
#: MAX_STICKY_TOOLS tools (measured, not assumed: see the measured section).
GROWING = (
    "what is 20% of 420",
    "check my inbox for unread messages",
    "what is the latest news online",
    "set a timer for five minutes",
    "is the living room lamp on",
    "search github for a library",
    "find the invoice pdf in my documents",
    "how much did I spend on bills",
    "search my notes for the birthday",
    "draft an email to my sister")


# --------------------------------------------------------------------------
#   1. Two turns of one conversation: the same tools bytes
# --------------------------------------------------------------------------

def t_two_turns_of_one_conversation_serialize_the_same_tools():
    reset()
    allowed = AG.offered_tools(None)
    first = turn(Q_A, cid=CID)[0][0]
    second = turn(Q_B, cid=CID)[0][0]
    first_names, second_names = tool_names(first), tool_names(second)
    check("turn 1 shows the diet for its own question (the chain core, so a real list)",
          1 < len(first_names) <= AG.TOOL_DIET_MULTI_LIMIT, first_names)
    check("turn 2's OWN diet is one tool - this is not two identical questions",
          AG.tool_diet(Q_B, allowed) == ["calendar_read"],
          AG.tool_diet(Q_B, allowed))
    check("turn 2 still shows turn 1's tools: the conversation carries them forward",
          len(second_names) == len(first_names)
          and all(n in second_names for n in first_names),
          (first_names, second_names))
    check("... in the SAME canonical order, so the array is byte for byte identical",
          tool_bytes(first) == tool_bytes(second),
          (tool_bytes(first)[:200], tool_bytes(second)[:200]))
    check("... and the same holds for the whole request's tools list object",
          first["tools"] == second["tools"], (first["tools"], second["tools"]))
    # A third turn that names yet another tool still keeps the once-canonical
    # order and previous tools: the list only ever GROWS within a conversation.
    third = turn("what is on my calendar tomorrow, then set a timer for ten minutes",
                 cid=CID)[0][0]
    third_names = tool_names(third)
    check("a later turn that names a new tool adds it without losing any old one",
          set(second_names) <= set(third_names), (second_names, third_names))
    check("... and the order stays canonical (TOOLS order), not first-seen order",
          third_names == AG._canonical_tool_order(third_names), third_names)


def t_a_different_conversation_gets_the_original_diet():
    reset()
    allowed = AG.offered_tools(None)
    sticky_conv = turn(Q_A, cid=CID)[0][0]
    body = turn(Q_B, cid="conv-kv-9999")[0][0]
    names = tool_names(body)
    check("a different conversation_id is NOT carrying the first conversation's tools",
          names == ["calendar_read"], names)
    check("... its tools array is exactly the plain top-K diet for the question",
          body["tools"] == AG._schemas_for(AG.tool_diet(Q_B, allowed), [], {}),
          names)
    check("... and the two conversations really serialize different bytes",
          tool_bytes(body) != tool_bytes(sticky_conv),
          (tool_names(sticky_conv), names))


def t_a_new_conversation_still_gets_the_top_k_diet():
    reset()
    allowed = AG.offered_tools(None)
    body = turn(Q_B, cid="conv-kv-new")[0][0]
    names = tool_names(body)
    check("a new conversation's first turn shows the diet, not the whole catalogue",
          0 < len(names) <= AG.TOOL_DIET_LIMIT and len(names) < len(allowed),
          (names, len(allowed)))
    check("... and it is exactly what the selector picks for those words",
          names == AG.tool_diet(Q_B, allowed), names)


def t_a_full_list_fallback_is_not_carried():
    reset()
    allowed = AG.offered_tools(None)
    fallback = turn("hi", cid="conv-kv-fallback")[0][0]
    check("an unrecognised question still falls back to the WHOLE allowed list",
          tool_names(fallback) == AG._canonical_tool_order(allowed),
          len(tool_names(fallback)))
    check("... and nothing is carried from that fallback",
          AG.sticky_tool_names("conv-kv-fallback") == [],
          AG.sticky_tool_names("conv-kv-fallback"))
    after = turn(Q_B, cid="conv-kv-fallback")[0][0]
    check("... so the next recognised question gets its own diet, not a union",
          tool_names(after) == ["calendar_read"], tool_names(after))


# --------------------------------------------------------------------------
#   2. The cap
# --------------------------------------------------------------------------

def t_the_carried_list_stops_at_nine():
    reset()
    allowed = AG.offered_tools(None)
    check("MAX_STICKY_TOOLS is 9", AG.MAX_STICKY_TOOLS == 9, AG.MAX_STICKY_TOOLS)
    sizes = []
    for question in GROWING:
        body = turn(question, cid="conv-kv-cap")[0][0]
        sizes.append(len(tool_names(body)))
        check(f"within the cap after {question[:28]!r}",
              len(tool_names(body)) <= AG.MAX_STICKY_TOOLS, tool_names(body))
    check("the conversation really did outgrow the cap while growing",
          9 in sizes and sizes[-1] == AG.MAX_STICKY_TOOLS, sizes)
    carried = AG.sticky_tool_names("conv-kv-cap")
    check("exactly MAX_STICKY_TOOLS names are carried",
          len(carried) == AG.MAX_STICKY_TOOLS, carried)
    check("a carried list is always in canonical order",
          carried == AG._canonical_tool_order(carried), carried)


def t_this_turns_own_diet_is_never_cut_to_reach_the_cap():
    reset()
    allowed = AG.offered_tools(None)
    for question in GROWING[:6]:
        turn(question, cid="conv-kv-full")
    # A chain question picks up to TOOL_DIET_MULTI_LIMIT tools even though this
    # conversation already carries the full 9: its own pick must not be cut.
    # This one names enough subjects to fill the multi-step cap (measured: 15
    # tools, more than MAX_STICKY_TOOLS).
    chain = ("check my email inbox, search my notes for the invoice pdf, add it "
             "to my to-do list, turn the living room lamp off, calculate 20% of "
             "my spending, and remind me")
    own = AG.tool_diet(chain, allowed)
    body = turn(chain, cid="conv-kv-full")[0][0]
    names = tool_names(body)
    check("the chain's own diet really is bigger than the carried-tools cap",
          len(own) > AG.MAX_STICKY_TOOLS, (len(own), own))
    check("a multi-step chain still shows every tool its own diet picked",
          all(n in names for n in own), (own, names))
    check("... and exactly its own pick - the carry is not added on top of it",
          names == AG._canonical_tool_order(own), (names, own))


# --------------------------------------------------------------------------
#   3. Compaction starts it over
# --------------------------------------------------------------------------

def t_a_compacted_prefix_starts_the_tool_list_over():
    reset()
    allowed = AG.offered_tools(None)
    cid = "conv-kv-compact"
    turn(Q_B, cid=cid)
    check("(a normal turn carries its tools for this conversation)",
          AG.sticky_tool_names(cid) == [n for n in AG.tool_diet(Q_B, allowed)],
          AG.sticky_tool_names(cid))
    check("a small history is NOT compacted",
          not AG.prefix_compacted([{"role": "user", "content": "hi"}], 8000))
    # A history far past the window: fit_messages must drop earlier turns.
    huge = []
    for i in range(30):
        huge.append({"role": "user", "content": f"old question {i} " + "x" * 2000})
        huge.append({"role": "assistant", "content": f"old answer {i} " + "y" * 2000})
    check("a huge history WILL be compacted (the control this test needs)",
          AG.prefix_compacted(huge + [{"role": "user", "content": "q"}], 8000))
    turn(Q_B, cid=cid, history=huge)
    check("after a compacted turn the conversation carries no tools forward",
          AG.sticky_tool_names(cid) == [], AG.sticky_tool_names(cid))
    # ... and a request WITHOUT a conversation id can never clear another
    # conversation's carried list (reset_sticky_tools(None) means "all of
    # them"; a compacted turn with no id must not reach that).
    turn(Q_B, cid="conv-kv-other")
    before = AG.sticky_tool_names("conv-kv-other")
    turn(Q_B, cid=None, history=huge)
    check("a compacted turn with no conversation id leaves other conversations alone",
          AG.sticky_tool_names("conv-kv-other") == before, before)


def t_a_turn_with_no_tools_keeps_the_conversation_carried_list():
    reset()
    cid = "conv-kv-notools"
    turn(Q_B, cid=cid)
    before = AG.sticky_tool_names(cid)
    check("(the conversation carries its tool)", before == ["calendar_read"], before)
    body = turn(Q_A, cid=cid, enabled=set())[0][0]
    check("a turn that offers no tools at all sends none", "tools" not in body,
          list(body))
    check("... and that empty list is not a selection, so nothing is wiped",
          AG.sticky_tool_names(cid) == before, AG.sticky_tool_names(cid))
    after = turn(Q_A, cid=cid)[0][0]
    check("... and the next ordinary turn still carries it",
          "calendar_read" in tool_names(after), tool_names(after))


# --------------------------------------------------------------------------
#   4. The system prefix itself is static
# --------------------------------------------------------------------------

def t_the_system_prefix_is_byte_identical_across_turns():
    reset()
    allowed = AG.offered_tools(None)
    first = turn(Q_A, cid="conv-kv-prefix")[0][0]
    second = turn(Q_B, cid="conv-kv-prefix")[0][0]
    first_system = [m for m in first["messages"] if m.get("role") == "system"]
    second_system = [m for m in second["messages"] if m.get("role") == "system"]
    check("the rules block is the first message of the request",
          first["messages"][0] == {"role": "system", "content": AG.LANE_SYSTEM},
          first["messages"][:1])
    check("every system message before the question is byte-identical on both turns",
          first_system == second_system,
          ([m.get("content", "")[:60] for m in first_system],
           [m.get("content", "")[:60] for m in second_system]))
    # Nothing in the prefix carries a clock or a status string: the work
    # order's "volatile text in token 0" is checked here, not assumed.
    blob = json.dumps(first_system, ensure_ascii=False)
    import datetime
    now = datetime.datetime.now()
    for stamp in (now.strftime("%Y-%m-%d"), now.strftime("%H:%M"),
                  str(now.year) + "-"):
        check(f"no per-turn stamp {stamp!r} in the system prefix",
              stamp not in blob, blob[:200])


# --------------------------------------------------------------------------
#   The measured before/after (printed for the PR, not only asserted)
# --------------------------------------------------------------------------

def measure():
    """The numbers the PR body quotes: what the tool block costs, before and
    after Opt 2.1, by estimate_tokens - the count budget() itself takes off
    the room (3 characters a token, deliberately pessimistic)."""
    allowed = AG.offered_tools(None)
    full = AG._schemas_for(AG._canonical_tool_order(allowed), [], {})
    reset()
    first_body = turn(Q_A, cid="conv-kv-measure")[0][0]
    second_body = turn(Q_B, cid="conv-kv-measure")[0][0]
    old_second = AG._schemas_for(AG.tool_diet(Q_B, allowed), [], {})
    new_second = second_body["tools"]
    print("\n----- measured (estimate_tokens; json separators=(',',':')) -----")
    print(f"whole catalogue          : {len(allowed):2d} tools, "
          f"{AG.estimate_tokens(full):5d} est. prompt tokens, "
          f"{len(json.dumps(full, separators=(',', ':')).encode()):5d} bytes")
    print(f"turn 1 diet (question A) : {len(tool_names(first_body)):2d} tools, "
          f"{AG.estimate_tokens(first_body['tools']):5d} est. tokens, "
          f"{len(tool_bytes(first_body)):5d} bytes")
    print(f"turn 2 BEFORE Opt 2.1    : {len(AG.tool_diet(Q_B, allowed)):2d} tools, "
          f"{AG.estimate_tokens(old_second):5d} est. tokens, "
          f"{len(json.dumps(old_second, separators=(',', ':')).encode()):5d} bytes"
          "   <- the array CHANGED from turn 1")
    print(f"turn 2 AFTER Opt 2.1     : {len(tool_names(second_body)):2d} tools, "
          f"{AG.estimate_tokens(new_second):5d} est. tokens, "
          f"{len(tool_bytes(second_body)):5d} bytes"
          "   <- SAME bytes as turn 1, prefix cache holds")
    # A realistic second turn: the app sends the conversation so far, so its
    # prompt is rules + tools + turn 1's question + its answer + turn 2's
    # question. Only the tail of that is new work when the prefix is reused.
    history = [{"role": "user", "content": Q_A},
               {"role": "assistant", "content": "done"}]
    reset()
    turn(Q_A, cid="conv-kv-measure2")
    with_history = turn(Q_B, cid="conv-kv-measure2", history=history)[0][0]
    turn2_prompt = (AG.estimate_tokens(with_history["messages"])
                    + AG.estimate_tokens(with_history["tools"]))
    # AFTER the fix, the whole of turn 1's prompt is a prefix of turn 2's
    # (same tools bytes, same rules, same earlier messages).
    turn1_prompt = (AG.estimate_tokens(first_body["messages"])
                    + AG.estimate_tokens(first_body["tools"]))
    reused_after = min(turn1_prompt, turn2_prompt)
    # BEFORE the fix the tools array changed. Under this repository's own
    # assumption that the tool list is rendered ahead of the messages ("the
    # tool list sits at the start of the prompt"), the re-read starts at the
    # tool block, so only what the template renders BEFORE it can be reused:
    # the rules block alone. (Where exactly the tool block renders is decided
    # by the model's chat template; the 2026-10-07 audit's G3 row flags that
    # position as unverified in this repo, so this is the pessimistic end.)
    reused_before = AG.estimate_tokens([{"role": "system", "content": AG.LANE_SYSTEM}])
    print(f"turn 2 prompt (with the conversation so far): {turn2_prompt:5d} est. tokens")
    print(f"... re-read BEFORE Opt 2.1: ~{turn2_prompt - reused_before:5d} est. tokens "
          f"(tools changed; only the {reused_before} rules tokens before them are reused)")
    print(f"... re-read AFTER Opt 2.1:  ~{turn2_prompt - reused_after:5d} est. tokens "
          "(only what follows turn 1's prompt: its answer and the new question)")
    print("not measured here: real first-token latency on the owner's PC "
          "(NOT-TESTABLE at this desk - no card is driven by a test)")
    print("----- end measured -----\n")


# --------------------------------------------------------------------------

def main():
    AG._publish_step = lambda *a, **k: None
    AG._record_chain = lambda steps: None
    tests = (t_two_turns_of_one_conversation_serialize_the_same_tools,
             t_a_different_conversation_gets_the_original_diet,
             t_a_new_conversation_still_gets_the_top_k_diet,
             t_a_full_list_fallback_is_not_carried,
             t_the_carried_list_stops_at_nine,
             t_this_turns_own_diet_is_never_cut_to_reach_the_cap,
             t_a_compacted_prefix_starts_the_tool_list_over,
             t_a_turn_with_no_tools_keeps_the_conversation_carried_list,
             t_the_system_prefix_is_byte_identical_across_turns)
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
        finally:
            reset()
    measure()
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
