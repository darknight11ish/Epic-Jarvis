"""test_cloud_answer_bound.py - the cloud answer is BOUNDED, not truncated.

    python3 backend/test_cloud_answer_bound.py

THE RULING THIS PROVES (external review, 2026-11-19, 6.5). A concise-by-default
instruction and a generous safety ceiling - `max_tokens` 4,096 for a standard
escalation and 8,192 for a coding/deep-analysis one - and NOT an aggressive
truncation of hard answers.

WHY, MEASURED. One escalated turn on the owner's PC cost $0.002747-$0.0039 and
was almost entirely OUTPUT: 2,152 completion tokens against 84 prompt tokens,
about 99% of the bill (the field battery's EFFICIENCY row,
`.dsh-scratch/wave21/field-battery/`). A cost per turn is therefore a length
control, and the review's point is that a TRUNCATED hard answer costs more than
the tokens it saves - the answer is unusable, so the owner asks again and pays
twice.

WHAT THIS SUITE RUNS, AND WHY IT IS NOT A SOURCE READ. Every check calls the
real composer and reads the request BODY it returns: the dict the relay would
serialise and POST. The composer lives in `jarvis_chatbot_api.py` and is called
by the HUD relay on every hop of the degrade loop (`ollama-direct.patch`), so
this is the same code the owner's PC runs, with a lane state this suite owns.
No socket, no key, no model, no live settings file: a scratch config folder is
made before anything imports, and the "key" below is a made-up string that is
never sent anywhere.

No network, no model, no live file: standard library only.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REBUILT = HERE / "rebuilt"

#: A scratch home BEFORE anything reads a settings file.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-cloud-bound-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")

sys.dont_write_bytecode = True
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import jarvis_chatbot_api as API  # noqa: E402
import jarvis_router as RT  # noqa: E402

FAILED, PASSED = [], []

#: A hard, plainly non-private question: the shape the router escalates.
STANDARD = ("Explain in detail how a car's gearbox works, why the gears change "
            "the turning force, and what happens when one gear engages another.")
#: Long, clause-heavy and explicitly asking for reasoning: the router's own
#: score puts it in the deep band (measured 0.733 with jarvis_router.complexity).
DEEP = ("Prove by induction that the sum of the first n odd numbers equals n "
        "squared. Then explain carefully, for a beginner, why the induction step "
        "is legitimate rather than circular, and give one counterexample-shaped "
        "argument that would fail if the claim were changed to even numbers.")
#: A coding request. Its own words are the Coding preset's trigger words, so it
#: is the coding tier even with a STANDARD complexity score.
CODING = ("Write a complete Python script that reads a CSV of temperatures, "
          "computes daily averages, handles missing rows, writes a summary file, "
          "and explain each step.")

#: A lane state exactly the shape `lane_state()` returns for the shipped default
#: (DeepSeek bills hidden reasoning INSIDE max_tokens, so its priced answer is
#: cap + REASONING_ROOM). The key is a made-up string, never used.
DEEPSEEK = {"lane": RT.CLOUD_LANE, "pid": "deepseek_api", "model": "deepseek-flash",
            "host": "api.deepseek.com",
            "url": "https://api.deepseek.com/chat/completions",
            "key": "not-a-real-key-0123456789", "cap": 8000, "problem": ""}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def body_for(question, *, complexity=0.0, state=None, asked=2048):
    """The composed request body for one escalation of `question`."""
    return API.cloud_request_body(
        {"model": RT.CLOUD_LANE,
         "messages": [{"role": "user", "content": question}],
         "stream": True, "max_tokens": asked},
        dict(DEEPSEEK if state is None else state), complexity=complexity)


# ==========================================================================
#  1. the two ceilings, on the composed body
# ==========================================================================

def t_a_standard_escalation_carries_4096_and_the_instruction():
    state = dict(DEEPSEEK)
    body = {"model": RT.CLOUD_LANE,
            "messages": [{"role": "user", "content": STANDARD}],
            "stream": True, "max_tokens": 2048}
    out = API.cloud_request_body(body, state, complexity=0.45)
    check("a standard escalation's composed body carries max_tokens 4096",
          out.get("max_tokens") == 4096, out.get("max_tokens"))
    check("... its ONE system message is the concise-by-default instruction",
          out.get("messages", [])[:1] == [{"role": "system",
                                           "content": API.CLOUD_CONCISE_INSTRUCTION}],
          out.get("messages", [])[:1])
    check("... and the owner's own question follows it, word for word",
          out.get("messages", [])[1:] == [{"role": "user", "content": STANDARD}],
          out.get("messages", [])[1:])
    check("... the lane state now records the same ceiling, so the relay's own "
          "cap call a moment later can only LOWER it",
          state.get("max_tokens_ceiling") == 4096, state)
    check("... and the caller's original body was not mutated",
          body["max_tokens"] == 2048 and len(body["messages"]) == 1, body)


def t_a_coding_or_deep_escalation_carries_8192():
    check("the ceilings themselves are 4096 and 8192",
          API.cloud_answer_ceiling() == 4096
          and API.cloud_answer_ceiling(deep=True) == 8192,
          (API.cloud_answer_ceiling(), API.cloud_answer_ceiling(deep=True)))
    deep = body_for(DEEP, complexity=0.73)
    check("a deep-analysis escalation (complexity 0.73) carries max_tokens 8192",
          deep.get("max_tokens") == 8192, deep.get("max_tokens"))
    check("... and it still carries the concise instruction",
          deep.get("messages", [])[:1] == [{"role": "system",
                                            "content": API.CLOUD_CONCISE_INSTRUCTION}],
          deep.get("messages", [])[:1])
    # A coding turn whose router score is only STANDARD is still the coding
    # tier: the existing Coding-preset words recognise it.
    check("the existing coding signal sees a coding request",
          API.cloud_deep_turn(CODING) is True, API.cloud_deep_turn(CODING))
    coding = body_for(CODING, complexity=0.45)
    check("... so a coding escalation carries max_tokens 8192 even at complexity 0.45",
          coding.get("max_tokens") == 8192, coding.get("max_tokens"))
    check("... and an ordinary question is NOT made deep by the word match",
          API.cloud_deep_turn("What is a semicolon?") is False,
          API.cloud_deep_turn("What is a semicolon?"))
    check("... a whole-word match: the preset's 'app' does not read 'happens'",
          API.cloud_deep_turn("What happens when a gear engages another?") is False,
          API.cloud_deep_turn("What happens when a gear engages another?"))


# ==========================================================================
#  2. the bound can only lower what the money check priced - never raise it
# ==========================================================================

def t_the_bound_can_only_lower_the_money_checked_request():
    # The 2026-11-03 rule is untouched: a reasoning-inside lane is priced with
    # its cap plus the reasoning room.
    priced = API.cloud_request_cap({"pid": "deepseek_api", "cap": 8000}, 2048)
    check("the existing money rule still prices a reasoning-inside lane at "
          "cap + reasoning room", priced == 8000 + API.REASONING_ROOM, priced)
    lowered = API.cloud_request_cap({"pid": "deepseek_api", "cap": 8000,
                                     "max_tokens_ceiling": 4096}, 2048)
    check("... and a recorded ceiling can only LOWER it",
          lowered == 4096, lowered)
    # A service whose reasoning is not measured inside its cap keeps the
    # caller's own number; the ceiling must not RAISE it.
    other = {"pid": "mistral_api", "model": "mistral-small-latest",
             "host": "api.mistral.ai", "url": "https://api.mistral.ai/v1/chat/completions",
             "key": "not-a-real-key-0123456789", "cap": 8000, "problem": ""}
    out = body_for(STANDARD, complexity=0.45, state=other, asked=2048)
    check("a lane priced with the caller's own cap is never RAISED above it",
          out.get("max_tokens") == min(4096, API.cloud_request_cap(other, 2048)),
          out.get("max_tokens"))
    # A nearly-spent month prices a smaller cap; the answer bound stays inside
    # the money-priced worst case.
    small = dict(DEEPSEEK, cap=256)
    out2 = body_for(STANDARD, complexity=0.45, state=small)
    check("a nearly-spent month still gets a bounded answer, inside what "
          "money_check priced",
          out2.get("max_tokens") == 4096
          and out2["max_tokens"] <= API.cloud_request_cap(dict(small), 2048),
          (out2.get("max_tokens"), API.cloud_request_cap(dict(small), 2048)))


# ==========================================================================
#  3. the instruction goes with EVERY cloud request, and only those
# ==========================================================================

def t_every_escalation_gets_the_instruction():
    cases = (
        ("standard", body_for(STANDARD, complexity=0.45)),
        ("deep", body_for(DEEP, complexity=0.73)),
        ("coding", body_for(CODING, complexity=0.45)),
        ("another service", body_for(
            STANDARD, complexity=0.45,
            state={"pid": "mistral_api", "model": "mistral-small-latest",
                   "host": "api.mistral.ai",
                   "url": "https://api.mistral.ai/v1/chat/completions",
                   "key": "not-a-real-key-0123456789", "cap": 8000,
                   "problem": ""})),
        ("a small cap", body_for(STANDARD, complexity=0.45,
                                 state=dict(DEEPSEEK, cap=256))),
    )
    for label, out in cases:
        check(f"{label}: the composed cloud request carries the concise instruction",
              out.get("messages", [])[:1] == [{"role": "system",
                                               "content": API.CLOUD_CONCISE_INSTRUCTION}],
              out.get("messages", [])[:1])
    # The cloud lane's privacy cut is unchanged: only the owner's own turns are
    # carried, and only the NEWEST one - earlier turns do not ride along.
    body = {"model": RT.CLOUD_LANE,
            "messages": [{"role": "user", "content": "my salary is 90000"},
                         {"role": "assistant", "content": "ok"},
                         {"role": "user", "content": STANDARD}],
            "stream": True}
    out = API.cloud_request_body(body, dict(DEEPSEEK), complexity=0.45)
    check("... and only the NEWEST user turn is carried, so no earlier turn can "
          "ride along",
          out.get("messages", [])[1:] == [{"role": "user", "content": STANDARD}],
          out.get("messages"))


def t_a_local_or_unusable_lane_is_untouched():
    body = {"model": "qwen3.5:9b",
            "messages": [{"role": "user", "content": STANDARD}],
            "stream": True, "max_tokens": 2048}
    out = API.cloud_request_body(body, dict(API.NO_LANE_STATE), complexity=0.45)
    check("a local lane's body is returned unchanged - no instruction, no bound",
          out == body and "max_tokens_ceiling" not in API.NO_LANE_STATE,
          (out, body))
    out2 = API.cloud_request_body(dict(body), {}, complexity=0.45)
    check("... and an empty lane state is the same",
          out2 == body, out2)


# ==========================================================================
#  4. the instruction itself: concise, and still complete for a hard question
# ==========================================================================

def t_the_instruction_asks_for_short_without_cutting_a_hard_answer():
    text = API.CLOUD_CONCISE_INSTRUCTION
    check("it is one short paragraph (under 600 characters)",
          isinstance(text, str) and 0 < len(text) < 600, len(text or ""))
    check("... it asks for a DIRECT and CONCISE answer",
          "concise" in text.lower() and "directly" in text.lower(), text)
    check("... it says not to pad or restate the question",
          "pad" in text.lower() and "restate" in text.lower(), text)
    check("... and it protects a hard answer: a COMPLETE answer is still required",
          "complete answer" in text.lower() and "hard question" in text.lower(), text)


# ==========================================================================
#  5. the relay really calls it: every hop of the degrade loop composes the
#     request through this one seam
# ==========================================================================

def t_the_relay_composes_every_cloud_request_here():
    """Run the REAL `_completions_url` from the patch stack, where it lives.

    The composer is only worth anything if the HUD relay calls it on the way to
    the socket. `ollama-direct.patch` puts the call in `_completions_url`, and
    `_open` builds EVERY hop of the degrade loop through that one function. This
    lifts the function out of `_stack.stand_in("jarvis_hud.py")` - the text the
    patch stack really produces, the same slice `test_ollama_direct.py` lifts -
    and runs it with a stand-in `jarvis_chatbot_api` whose lane resolves to the
    DeepSeek state above, then reads the caller's own request body. No socket:
    `_completions_url` returns an address and applies the composition to the
    body it is given; nothing is sent.
    """
    import sys as _sys
    import types
    import urllib
    import _stack
    src, log = _stack.stand_in("jarvis_hud.py")
    if not src:
        check("the HUD stand-in could be built from the patch stack", False,
              "; ".join((log or [])[-2:]))
        return
    start = "def _completions_url(lane: str, body: dict) -> str:"
    end = "\n\n        # A rate-limited lane"
    try:
        block = src[src.index(start):src.index(end)]
        code = compile(block, "<hud _completions_url>", "exec")
    except (ValueError, SyntaxError) as exc:
        check("the patch stack carries the cloud request composer", False, str(exc))
        return

    class FakeApi:
        def lane_state(self, lane):
            return dict(DEEPSEEK)

    api = FakeApi()
    api.cloud_request_body = API.cloud_request_body
    api.cloud_request_cap = API.cloud_request_cap
    body = {"model": RT.CLOUD_LANE,
            "messages": [{"role": "user", "content": STANDARD}],
            "stream": True, "max_tokens": 2048}
    ns = {"OLLAMA_URL": "http://127.0.0.1:11434",
          "JARVIS_URL": "http://127.0.0.1:8000",
          "active_ollama_url": lambda: "http://127.0.0.1:11434",
          "local_model": "qwen3.5:9b", "urllib": urllib,
          "decision": types.SimpleNamespace(inject_memory=False, complexity=0.45)}
    saved = _sys.modules.get("jarvis_chatbot_api")
    _sys.modules["jarvis_chatbot_api"] = api
    try:
        exec(code, ns)
        url = ns["_completions_url"](RT.CLOUD_LANE, body)
    finally:
        if saved is not None:
            _sys.modules["jarvis_chatbot_api"] = saved
        else:
            _sys.modules.pop("jarvis_chatbot_api", None)
    check("the relay's cloud request function sends to the lane's own service",
          url == DEEPSEEK["url"], url)
    check("... and through it the request body is bounded at the standard 4096",
          body.get("max_tokens") == 4096, body.get("max_tokens"))
    check("... with the concise instruction in front of the owner's question",
          body.get("messages", [])[:1] == [{"role": "system",
                                            "content": API.CLOUD_CONCISE_INSTRUCTION}]
          and body.get("messages", [])[1:] == [{"role": "user", "content": STANDARD}],
          body.get("messages"))


# ==========================================================================
#  6. the shipped module and its published-base twin are one file
# ==========================================================================

def t_the_twins_match():
    here = (HERE / "jarvis_chatbot_api.py").read_bytes()
    base = (REPO / "jarvis-backend" / "jarvis_chatbot_api.py").read_bytes()
    check("backend/jarvis_chatbot_api.py and jarvis-backend/ are byte identical",
          here == base, (len(here), len(base)))


# ==========================================================================

TESTS = [
    t_a_standard_escalation_carries_4096_and_the_instruction,
    t_a_coding_or_deep_escalation_carries_8192,
    t_the_bound_can_only_lower_the_money_checked_request,
    t_every_escalation_gets_the_instruction,
    t_a_local_or_unusable_lane_is_untouched,
    t_the_instruction_asks_for_short_without_cutting_a_hard_answer,
    t_the_relay_composes_every_cloud_request_here,
    t_the_twins_match,
]


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(f"{fn.__name__} raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
