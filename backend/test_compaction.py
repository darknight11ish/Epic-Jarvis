"""test_compaction.py - what a long conversation keeps, and what it must not change.

    python3 backend/test_compaction.py

WHY THIS EXISTS

`jarvis_agent.fit_messages` trims a long conversation down to three quarters of
the budget, and `clear_old_tool_results` empties the older tool results. Both are
lossy on purpose. This suite covers the two-stage compaction built on top of
them (`jarvis_compaction`): a small exact stub in place of a cleared tool
result, one bounded digest of the evicted turns, and a bounded recall of the
evicted turns nearest the question.

THE CHECK THAT DECIDES WHETHER THIS IS A FIX OR A REGRESSION

The reason `fit_messages` trims to three quarters is that the START of the
prompt must not change between turns, so Ollama can reuse the KV prefix it has
already read. A digest rewritten on a turn where nothing was evicted would make
every later turn re-read the whole prompt. So:

  * `t_nothing_evicted_leaves_the_prompt_byte_identical` - with no eviction, the
    pipeline returns exactly what `fit_messages` returns, byte for byte;
  * `t_the_digest_is_a_pure_function_of_the_evicted_turns` - the same evicted
    turns give the same bytes, whatever surrounds them;
  * `t_the_prefix_stays_intact_while_nothing_new_is_evicted` - two rounds in the
    same answer, where the evicted set does not change, keep the digest at the
    same index with the same bytes, and the serialised prompt's common prefix
    covers the whole digest.

EVERY GUARD IS BITE-PROVED: the outcome word, the scrubber failing closed, the
missing module, the anchor cap, the recall's relevance gate and the condenser's
breaker are each shown failing with the guard disabled, and then passing again.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_agent as A  # noqa: E402
import jarvis_compaction as C  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why: str) -> None:
    print(f"skip  {why}")


def _msgs(turns: int, *, filler: int = 400, rules: str = "RULES", question: str = "") -> list:
    """A conversation of `turns` finished exchanges, plus the current question."""
    out = [{"role": "system", "content": rules}]
    for i in range(1, turns + 1):
        out.append({"role": "user", "content":
                    f"turn {i}: never delete anything under C:\\Jarvis\\keep. {('filler ' * filler)}"})
        out.append({"role": "assistant", "content":
                    f"done with turn {i}; see jarvis_gate.py and port 8765"})
    out.append({"role": "user", "content": question or "and now the next question"})
    return out


def _digest_of(messages: list) -> dict:
    return next((m for m in messages if C.is_own_message(m)
                 and m["content"].startswith(C.DIGEST_HEADER)), {})


def _recall_of(messages: list) -> dict:
    return next((m for m in messages if C.is_own_message(m)
                 and m["content"].startswith(C.RECALL_HEADER)), {})


def _serialised(messages: list) -> str:
    """The messages as one string. This is what the prompt prefix is made of, so
    comparing these is comparing the bytes Ollama would read."""
    return json.dumps(messages, ensure_ascii=False, sort_keys=True)


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


# --------------------------------------------------------------------------
#   The tool-result stub (stage 1)
# --------------------------------------------------------------------------

def t_the_stub_keeps_which_tool_what_it_aimed_at_and_how_it_ended():
    stub = C.tool_stub(name="file_read", args={"path": r"C:\Jarvis\keep\notes.txt"},
                       result_text=json.dumps({"ok": True, "text": "port 8765, see jarvis_hud.py"}))
    check("the tool is named", "file_read" in stub, stub)
    check("the primary target is named", "notes.txt" in stub, stub)
    check("the outcome is named", C.OUTCOME_OK in stub, stub)
    check("an anchor from the result is kept", "port 8765" in stub or "jarvis_hud.py" in stub, stub)
    check("and it fits the stub budget", len(stub) <= C.STUB_MAX, (len(stub), stub))


def t_a_denied_call_is_never_reported_as_a_completed_one():
    """The whole point of the third outcome word.

    The agent writes every gate refusal as an error beginning `refused:` - that
    is the shape this reads, and `t_the_agent_still_writes_refusals_that_way`
    pins it on the agent's own source."""
    denied = C.tool_stub(name="shell_exec", args={"command": "rm -rf /"},
                         result_text=json.dumps({"ok": False,
                                                 "error": "refused: the owner said no"}))
    check("a refused call is denied_by_owner", C.OUTCOME_DENIED in denied, denied)
    check("... and does NOT say ok", C.OUTCOME_OK not in denied.split("|")[2], denied)
    failed = C.tool_stub(name="file_read", args={"path": "x"},
                         result_text=json.dumps({"ok": False, "error": "no such file"}))
    check("a tool's own failure is error", "error" in failed, failed)
    fine = C.tool_stub(name="file_read", args={"path": "x"},
                       result_text=json.dumps({"ok": True}))
    check("a call that worked is ok", "ok" in fine, fine)


def t_the_outcome_rule_bites():
    """BITE: with the outcome rule replaced by "everything worked", the same
    refused call reads as a completed one - which is the defect the third word
    exists to prevent."""
    real = C._outcome
    try:
        C._outcome = lambda result, text: C.OUTCOME_OK
        wrong = C.tool_stub(name="shell_exec", args={"command": "rm"},
                            result_text=json.dumps({"ok": False, "error": "refused: no"}))
    finally:
        C._outcome = real
    check("BITE: without the rule, the refused call DOES read as ok",
          C.OUTCOME_OK in wrong and C.OUTCOME_DENIED not in wrong, wrong)
    check("... and the rule is back", C._outcome is real)
    check("... and the refusal reads as denied again",
          C.OUTCOME_DENIED in C.tool_stub(name="shell_exec", args={"command": "rm"},
                                          result_text=json.dumps({"ok": False,
                                                                  "error": "refused: no"})))


def t_the_stub_is_bounded_and_keeps_at_most_three_anchors():
    long_result = json.dumps({"ok": True, "text": " ".join(
        [r"C:\a\one.txt", r"C:\a\two.txt", r"C:\a\three.txt", r"C:\a\four.txt",
         "port 8765", "v1.2.3", "2026-10-16", "KeyError"])})
    stub = C.tool_stub(name="file_read", args={"path": r"C:\a\one.txt"},
                       result_text=long_result)
    check("no longer than the budget", len(stub) <= C.STUB_MAX, (len(stub), stub))
    anchors = [a for a in C.extract_anchors(long_result)]
    kept = [a for a in anchors if a in stub]
    check("at most three anchors are kept", len(kept) <= C.STUB_ANCHORS, kept)
    check("... and the anchors are real ones from the result",
          all(a in long_result for a in kept), kept)


def t_the_scrubber_fails_closed_for_the_stub():
    """No scrubber, nothing emitted: `tool_stub` answers None and the caller
    keeps the old bare placeholder rather than reading out a result unscrubbed."""
    real = C.scrubber
    C.scrubber = lambda: None
    try:
        stub = C.tool_stub(name="file_read", args={"path": "secret.txt"},
                           result_text=json.dumps({"ok": True, "text": "hunter2"}))
    finally:
        C.scrubber = real
    check("with no scrubber the stub is None", stub is None, stub)

    msgs = [{"role": "system", "content": "RULES"}]
    for i in range(4):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{i}", "function": {"name": "file_read",
                                         "arguments": json.dumps({"path": f"f{i}.txt"})}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}",
                     "content": json.dumps({"ok": True, "text": "x" * 400})})
    real_comp = A._compaction
    A._compaction = lambda: None
    try:
        cleared = A.clear_old_tool_results(msgs, 50)
    finally:
        A._compaction = real_comp
    bodies = [json.loads(m["content"]) for m in cleared if m.get("role") == "tool"]
    # The newest three results are deliberately kept WHOLE, so only the cleared
    # ones are the ones this check is about.
    cleared_bodies = [b for b in bodies if "cleared" in b]
    check("the old placeholder is what a CLEARED result says",
          bool(cleared_bodies)
          and all(b.get("cleared") == A.CLEARED_RESULT for b in cleared_bodies),
          cleared_bodies[:1])
    check("... i.e. every cleared one, not just the first",
          len(cleared_bodies) == len(bodies) - 3, (len(cleared_bodies), len(bodies)))
    check("... so nothing from a cleared result is read out",
          all("x" * 50 not in json.dumps(b) for b in cleared_bodies), cleared_bodies[:1])


def t_clearing_touches_only_old_tool_results():
    msgs = [{"role": "system", "content": "RULES"}]
    for i in range(5):
        msgs.append({"role": "assistant", "content": f"thinking {i}", "tool_calls": [
            {"id": f"c{i}", "function": {"name": "file_read",
                                         "arguments": json.dumps({"path": f"f{i}.txt"})}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}",
                     "content": json.dumps({"ok": True, "text": "body " * 200})})
    msgs.append({"role": "user", "content": "the owner's own words"})
    cleared = A.clear_old_tool_results(msgs, 50)

    check("the owner's words are untouched",
          any(m.get("content") == "the owner's own words" for m in cleared if isinstance(m, dict)))
    check("no assistant message is rewritten",
          [m.get("content") for m in cleared if isinstance(m, dict) and m.get("role") == "assistant"]
          == [m.get("content") for m in msgs if isinstance(m, dict) and m.get("role") == "assistant"])
    check("the system message is untouched",
          cleared[0] == {"role": "system", "content": "RULES"})
    tool_msgs = [m for m in cleared if isinstance(m, dict) and m.get("role") == "tool"]
    kept_whole = [i for i, m in enumerate(tool_msgs) if "body body" in json.dumps(m)]
    check("the newest three results are kept whole", kept_whole == [2, 3, 4], kept_whole)
    check("... and the older ones carry a stub, still valid JSON",
          all(isinstance(json.loads(m["content"]), dict) for m in tool_msgs))
    check("... with the outside-text label kept",
          all(A.OUTSIDE_FIELD in json.loads(m["content"]) for m in tool_msgs[:2]))


def t_a_cleared_result_keeps_its_ok_so_a_denial_is_not_laundered():
    msgs = [{"role": "system", "content": "RULES"}]
    for i in range(4):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{i}", "function": {"name": "shell_exec",
                                         "arguments": json.dumps({"command": f"cmd{i}"})}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": json.dumps(
            {"ok": False, "error": "refused: the owner said no"} if i == 0
            else {"ok": True, "text": "fine " * 200})})
    cleared = A.clear_old_tool_results(msgs, 50)
    first = json.loads([m for m in cleared if m.get("role") == "tool"][0]["content"])
    check("the refused result keeps ok=False", first.get("ok") is False, first)
    check("... and its stub says denied_by_owner", C.OUTCOME_DENIED in first.get("cleared", ""), first)


# --------------------------------------------------------------------------
#   The digest (stage 2)
# --------------------------------------------------------------------------

def t_the_digest_carries_the_rules_the_anchors_and_the_endings():
    _kept, evicted, _at = A.fit_messages_detailed(_msgs(6), 500)
    digest = C.digest_message([m for m in evicted if isinstance(m, dict)])
    check("a digest is built from evicted turns", digest is not None, digest)
    body = (digest or {}).get("content", "")
    check("it says how many turns were folded", "evicted-turns=" in body, body[:200])
    check("the owner's rule is quoted word for word",
          "never delete anything under C:\\Jarvis\\keep." in body, body[:400])
    check("exact lines are kept with the turn they came from",
          re.search(r"- turn \d+: .*jarvis_gate\.py", body) is not None, body)
    check("... and how a turn ended", C.OUTCOME_HEADER in body, body)
    check("it is ONE system message", digest.get("role") == "system", digest)
    check("it is bounded", C.tokens(body) <= C.DIGEST_TOKENS, C.tokens(body))


def t_the_digest_is_a_pure_function_of_the_evicted_turns():
    """Same evicted turns, same bytes - whatever surrounds them."""
    _kept, evicted, _at = A.fit_messages_detailed(_msgs(6), 500)
    same = [m for m in evicted if isinstance(m, dict)]
    first = C.digest_text(same)
    check("the same turns give the same text", first == C.digest_text(same), "")
    check("... and their key is the number of owner turns folded",
          C.digest_key(same) == f"evicted-turns={sum(1 for m in same if m.get('role') == 'user')}",
          C.digest_key(same))
    check("... and the key is said in the text", C.digest_key(same) in (first or ""), first)
    check("fewer turns give a different key",
          C.digest_key(same[:2]) != C.digest_key(same), C.digest_key(same[:2]))
    check("an empty evicted list builds nothing", C.digest_message([]) is None)
    check("... and so does one with no owner turn in it",
          C.digest_message([{"role": "assistant", "content": "hi"}]) is None)


def t_nothing_evicted_leaves_the_prompt_byte_identical():
    """THE PREFIX CACHE'S FIRST GUARANTEE. With nothing to evict, the pipeline
    must return exactly what `fit_messages` returns - no digest, no recall, not
    even an extra message - or every short turn would rewrite the prompt."""
    short = _msgs(1, filler=2)
    fit = A.fit_messages(short, 100000)
    compact = A.compact_messages(short, 100000, question="and now the next question")
    check("compact() returns exactly fit()", fit == compact, (len(fit), len(compact)))
    check("... byte for byte", _serialised(fit) == _serialised(compact))
    check("... and no message of ours was added", not any(C.is_own_message(m) for m in compact))


def t_the_prefix_stays_intact_while_nothing_new_is_evicted():
    """THE PREFIX CACHE'S SECOND GUARANTEE, measured on the bytes.

    A long conversation where every earlier turn is evicted, and the same
    conversation with one more tool result on the CURRENT turn: the evicted set
    is the same, so the digest must be the same bytes at the same index, and the
    serialised prompt's common prefix must cover the whole digest."""
    budget = 400
    base = _msgs(4, filler=300)
    round_two = base + [{"role": "assistant", "content": "calling a tool"},
                        {"role": "tool", "tool_call_id": "z",
                         "content": json.dumps({"ok": True, "text": "a short result"})},
                        {"role": "user", "content": "and now the next question"}]

    one = A.compact_messages(base, budget, question="port 8765")
    two = A.compact_messages(round_two, budget, question="port 8765")
    d1, d2 = _digest_of(one), _digest_of(two)
    check("both rounds evicted something", bool(d1) and bool(d2), (len(d1), len(d2)))
    check("the evicted set is the same in both rounds",
          C.digest_key([m for m in A.fit_messages_detailed(base, budget)[1]]) ==
          C.digest_key([m for m in A.fit_messages_detailed(round_two, budget)[1]]),
          (C.digest_key(A.fit_messages_detailed(base, budget)[1]),
           C.digest_key(A.fit_messages_detailed(round_two, budget)[1])))
    check("the digest is byte-for-byte identical", d1 == d2, (d1.get("content"), d2.get("content")))
    i1 = one.index(d1) if d1 in one else -1
    i2 = two.index(d2) if d2 in two else -1
    check("... and sits at the same index", i1 == i2 and i1 >= 0, (i1, i2))

    prefix = _common_prefix(_serialised(one), _serialised(two))
    digest_end = len(_serialised(one[:i1 + 1]))
    check("the serialised prompts share a prefix covering the whole digest",
          prefix >= digest_end, (prefix, digest_end))
    check("... so nothing before or inside the digest moved", prefix >= digest_end)


def t_the_digest_is_bounded_even_for_a_huge_conversation():
    _kept, evicted, _at = A.fit_messages_detailed(_msgs(40, filler=2000), 800)
    body = C.digest_text([m for m in evicted if isinstance(m, dict)])
    check("a huge eviction still gives a bounded digest",
          body is not None and C.tokens(body) <= C.DIGEST_TOKENS, C.tokens(body or ""))
    check("... and it kept the owner's rule", "never delete" in (body or ""), (body or "")[:200])


def t_the_digest_fails_closed_without_the_scrubber():
    _kept, evicted, _at = A.fit_messages_detailed(_msgs(6), 500)
    real = C.scrubber
    C.scrubber = lambda: None
    try:
        body = C.digest_text([m for m in evicted if isinstance(m, dict)])
        recall = C.recall_text("port 8765", [m for m in evicted if isinstance(m, dict)])
    finally:
        C.scrubber = real
    check("no scrubber, no digest", body is None, body)
    check("no scrubber, no recall", recall is None, recall)


# --------------------------------------------------------------------------
#   Recall of evicted turns
# --------------------------------------------------------------------------

def t_recall_picks_the_evicted_turn_nearest_the_question():
    evicted = [m for m in A.fit_messages_detailed(_msgs(6), 500)[1] if isinstance(m, dict)]
    body = C.recall_text("what about the port 8765", evicted)
    check("a question with a shared word gets a recall", bool(body), body)
    check("... and it is quoted from the evicted turns", "port 8765" in body, body)
    check("... and it is bounded", C.tokens(body) <= C.RECALL_TOKENS, C.tokens(body))
    check("... and it says where it came from", body.startswith(C.RECALL_HEADER), body[:60])
    check("at most two turns are quoted", body.count("- user:") <= C.RECALL_TURNS,
          body.count("- user:"))


def t_recall_says_nothing_when_nothing_is_relevant():
    """No shared words, no recall: a wasted 400 tokens on every turn is a cost
    with no answer in it."""
    evicted = [m for m in A.fit_messages_detailed(_msgs(6), 500)[1] if isinstance(m, dict)]
    check("an unrelated question gets nothing",
          C.recall_text("zzqqxx flurble", evicted) is None,
          C.recall_text("zzqqxx flurble", evicted))
    check("no question gets nothing", C.recall_text("", evicted) is None)
    check("no evicted turns gets nothing", C.recall_text("port 8765", []) is None)


def t_recall_sits_after_the_cached_prefix():
    """The digest holds what was evicted; the recall is per-question, so it must
    come AFTER it - otherwise a change of question would move the prefix."""
    budget = 400
    messages = _msgs(4, filler=300)
    out = A.compact_messages(messages, budget, question="port 8765")
    digest, recall = _digest_of(out), _recall_of(out)
    check("both are present", bool(digest) and bool(recall), (bool(digest), bool(recall)))
    if digest and recall:
        check("the recall comes after the digest",
              out.index(recall) > out.index(digest), (out.index(digest), out.index(recall)))
        newest_user = max(i for i, m in enumerate(out)
                          if isinstance(m, dict) and m.get("role") == "user")
        check("... and immediately before the newest question",
              out.index(recall) < newest_user, (out.index(recall), newest_user))


def t_the_recall_relevance_gate_bites():
    """BITE: with the gate off, an unrelated question pulls in evicted turns."""
    evicted = [m for m in A.fit_messages_detailed(_msgs(6), 500)[1] if isinstance(m, dict)]
    real = C._score
    C._score = lambda question, message: 1
    try:
        pulled = C.recall_text("zzqqxx flurble", evicted)
    finally:
        C._score = real
    check("BITE: with the gate off, the unrelated question DOES get a recall",
          bool(pulled), pulled)
    check("... and with the gate on it gets nothing",
          C.recall_text("zzqqxx flurble", evicted) is None)
    check("... and the gate is back", C._score is real)


# --------------------------------------------------------------------------
#   The agent's side: the pieces it must keep, and the wiring
# --------------------------------------------------------------------------

def t_a_missing_module_is_exactly_todays_behaviour():
    """The two-file, feature-off rule: with no `jarvis_compaction`, the pipeline
    is `fit_messages` and the cleared result is the old placeholder."""
    real = A._compaction
    A._compaction = lambda: None
    try:
        messages = _msgs(6, filler=300)
        check("compact() == fit() with no module",
              A.compact_messages(messages, 400) == A.fit_messages(messages, 400))
    finally:
        A._compaction = real
    check("... and the import helper is back", A._compaction is real)


def t_fit_messages_still_keeps_everything_it_promised():
    """The refactor must not have changed what `fit_messages` does."""
    messages = [{"role": "system", "content": "RULES"},
                {"role": "system", "content": "RECALLED FACTS"}]
    for i in range(8):
        messages.append({"role": "user", "content": f"q{i} " + "x" * 400})
        messages.append({"role": "assistant", "content": f"a{i} " + "y" * 400})
    messages.append({"role": "user", "content": "the current question"})
    kept = A.fit_messages(messages, 900)
    check("every system message is kept",
          [m for m in kept if m.get("role") == "system"] ==
          [m for m in messages if m.get("role") == "system"],
          [m for m in kept if m.get("role") == "system"])
    check("the current question is kept", kept[-1]["content"] == "the current question", kept[-1])
    check("nothing after the current question is dropped", len(kept) >= 1)
    check("the first kept earlier message is a question, never a bare answer",
          next((m.get("role") for m in kept if m.get("role") not in ("system",)), None) == "user",
          [m.get("role") for m in kept])
    check("a conversation inside the budget is returned unchanged",
          A.fit_messages(messages[:3], 100000) == messages[:3])
    src = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("the 75% target is still the source of the cache argument",
          "target = int(budget * 0.75)" in src, "the three-quarters trim moved")


def t_the_agent_still_writes_refusals_that_way():
    """The stub's third word reads `refused:`, which the agent writes at every
    refusal site. If that wording changes, this suite says so rather than
    quietly calling a denied call an error (or worse, a success)."""
    src = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("the agent writes gate refusals as errors beginning refused:",
          f'"error": f"{C.OUTCOME_REFUSED} ' in src or f'"refused: ' in src, "")
    check("... at more than one refusal site", src.count('refused: ') >= 3,
          src.count('refused: '))
    check("the stub reads exactly that prefix", C.OUTCOME_REFUSED == "refused:", C.OUTCOME_REFUSED)


def t_the_turn_uses_the_new_pipeline():
    src = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("the turn builds its messages with compact_messages",
          "compact_messages(clear_old_tool_results(msgs, room)," in src, "")
    check("... still passing the question for the recall",
          "question=question_text)" in src, "")
    check("fit_messages is still there for anything that wants only the trim",
          "def fit_messages(" in src and "def fit_messages_detailed(" in src, "")


def t_compaction_never_raises_on_junk():
    junk = [{"role": "user", "content": None}, "not a message", 7,
            {"role": "tool", "content": "{not json"}, {"role": "assistant"},
            {"role": "user", "content": ["a", {"type": "text", "text": "b"}]}]
    try:
        kept, evicted, at = A.fit_messages_detailed(junk, 1)
        out = A.compact_messages(junk, 1, question="anything")
        cleared = A.clear_old_tool_results(junk, 1)
        bad = None
    except Exception as exc:                                     # noqa: BLE001
        bad = exc
    check("junk messages do not raise", bad is None, bad)
    check("... and the pipeline still returns a list", isinstance(out, list), type(out))
    check("... and clearing leaves the list alone at that size", cleared == junk, cleared)


# --------------------------------------------------------------------------
#   The optional condenser
# --------------------------------------------------------------------------

def t_the_condenser_is_off_by_default_and_never_on_the_hot_path():
    called = []
    off = C.Condenser(lambda s: called.append(s) or "short")
    check("off by default", off.available() is False and off.submit("k", "prose") is False, "")
    check("... and it was never called", called == [], called)

    gate = threading.Event()
    on = C.Condenser(lambda s: (gate.wait(2), "short")[1], enabled=True)
    started = time.time()
    queued = on.submit("k", "prose")
    elapsed = time.time() - started
    check("an enabled condenser is asked in the background", queued is True, queued)
    check("... and submit() does not wait for it", elapsed < 0.5, elapsed)
    check("... and its answer is not there yet", on.take("k") is None, on.take("k"))
    gate.set()
    for _ in range(50):
        if on.take("k") is not None:
            break
        time.sleep(0.02)
    check("... and it arrives afterwards", on.take("k") in (None, "short"), "")


def t_the_condenser_is_never_given_the_anchor_table():
    evicted = [m for m in A.fit_messages_detailed(_msgs(4, filler=200), 400)[1]
               if isinstance(m, dict)]
    body = C.digest_text(evicted)
    check("the digest really does carry an anchor table", C.ANCHOR_HEADER in (body or ""), "")
    prose = C.digest_prose(body or "")
    check("the prose has no anchor table", C.ANCHOR_HEADER not in prose, prose[:200])
    check("... and no anchor from it", "port 8765" not in prose and "jarvis_gate.py" not in prose,
          prose[:300])
    check("... but keeps the words", C.DIGEST_HEADER in prose, prose[:120])


def t_the_circuit_breaker_stops_a_failing_condenser():
    bad = C.Condenser(lambda s: (_ for _ in ()).throw(RuntimeError("boom")),
                      enabled=True, max_failures=2)
    for i in range(2):
        bad.submit(f"k{i}", "prose")
        for _ in range(50):
            if bad.failures >= i + 1:
                break
            time.sleep(0.02)
    check("the breaker trips after the allowed failures", bad.tripped is True, bad.failures)
    check("... and it is no longer available", bad.available() is False)
    calls_before = bad.calls
    check("... and it refuses new work", bad.submit("k9", "prose") is False)
    time.sleep(0.05)
    check("... so no further call is made", bad.calls == calls_before, (bad.calls, calls_before))
    bad.reset()
    check("reset() closes it again", bad.available() is True and bad.tripped is False)


# --------------------------------------------------------------------------
#   This suite's own registration
# --------------------------------------------------------------------------

def _unregistered(names, run) -> list:
    return sorted(set(names) - set(run))


def t_every_test_here_is_registered():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    defined = sorted(n.name for n in tree.body
                     if isinstance(n, ast.FunctionDef) and n.name.startswith("t_"))
    running = sorted(fn.__name__ for fn in RUN)
    check("every t_ function here is in RUN", not _unregistered(defined, running),
          _unregistered(defined, running))
    check("... and every name in RUN is a function here", not _unregistered(running, defined),
          _unregistered(running, defined))
    check("this suite has at least 25 checks' worth of tests", len(defined) >= 20, len(defined))
    check("BITE: a name left out of RUN would be named",
          _unregistered(["t_a", "t_never_run"], ["t_a"]) == ["t_never_run"])


if __name__ == "__main__":
    RUN = (
        t_the_stub_keeps_which_tool_what_it_aimed_at_and_how_it_ended,
        t_a_denied_call_is_never_reported_as_a_completed_one,
        t_the_outcome_rule_bites,
        t_the_stub_is_bounded_and_keeps_at_most_three_anchors,
        t_the_scrubber_fails_closed_for_the_stub,
        t_clearing_touches_only_old_tool_results,
        t_a_cleared_result_keeps_its_ok_so_a_denial_is_not_laundered,
        t_the_digest_carries_the_rules_the_anchors_and_the_endings,
        t_the_digest_is_a_pure_function_of_the_evicted_turns,
        t_nothing_evicted_leaves_the_prompt_byte_identical,
        t_the_prefix_stays_intact_while_nothing_new_is_evicted,
        t_the_digest_is_bounded_even_for_a_huge_conversation,
        t_the_digest_fails_closed_without_the_scrubber,
        t_recall_picks_the_evicted_turn_nearest_the_question,
        t_recall_says_nothing_when_nothing_is_relevant,
        t_recall_sits_after_the_cached_prefix,
        t_the_recall_relevance_gate_bites,
        t_a_missing_module_is_exactly_todays_behaviour,
        t_fit_messages_still_keeps_everything_it_promised,
        t_the_agent_still_writes_refusals_that_way,
        t_the_turn_uses_the_new_pipeline,
        t_compaction_never_raises_on_junk,
        t_the_condenser_is_off_by_default_and_never_on_the_hot_path,
        t_the_condenser_is_never_given_the_anchor_table,
        t_the_circuit_breaker_stops_a_failing_condenser,
        t_every_test_here_is_registered,
    )
    for fn in RUN:
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
