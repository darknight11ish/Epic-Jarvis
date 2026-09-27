"""test_focus_brief.py - "briefer during focus" (feasibility I144,
2026-09-27: "Saved setting untouched.").

    python3 backend/test_focus_brief.py

What it proves, on jarvis_agent.py's real message-building (run_local_turn),
never a guess about what "should" happen:
  - a running, unpaused focus session adds FOCUS_NOTE just before the
    newest question - additive: the owner's manner line (if any) is still
    there too, in its usual place, untouched;
  - a paused session, or no session, adds nothing - jarvis_focus.is_active()
    is read fresh every turn, so this needs no signal to "turn off";
  - it is never first: the rules block still leads (keep_rules_first);
  - it costs its own line in the token budget (_TEMPLATE_TOKENS does not
    have to cover it - it is added after trimming, like manner and the
    spoken note - but budget() itself must leave room, or trimming would
    fight the very note meant to shorten the answer);
  - a backend without jarvis_focus.py adds nothing, ever (no guess);
  - jarvis_focus.is_active(): on+unpaused only; off or paused is False.
No network, no model - the model's own request is scripted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_focus.py")
import jarvis_agent as AG  # noqa: E402
import _ollama_wire as W  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


BLOCK = {"role": "system", "content": AG.LANE_SYSTEM}
FOCUS = {"role": "system", "content": AG.FOCUS_NOTE}
URL = "http://127.0.0.1:11434"


def turn(messages, *, manner=None, focus_active=False):
    """One turn with jarvis_focus.is_active() faked; returns the messages
    really sent to the model."""
    sent = []

    def opener(url, body):
        sent.append(json.loads(json.dumps(body)))
        return W.FakeResponse(W.stream([("content", "ok"), ("done", "stop")]))
    real_focus_active = AG._focus_active_now
    real_get_json = AG._get_json
    AG._focus_active_now = lambda: focus_active
    AG._get_json = lambda *a, **k: (_ for _ in ()).throw(OSError("no network in this test"))
    try:
        AG.run_local_turn(messages, "jarvis-primary", ollama_url=URL,
                          stream_out=lambda b: None, open_stream=opener, enabled_tools=None,
                          context_length=16384,
                          request={"model": "jarvis-primary", "stream": True,
                                   "messages": messages},
                          on_step=lambda s: None, record_chain=lambda s: None,
                          keepalive_seconds=60, status_delay=60, lane_choice=None,
                          manner=manner, model_waking=lambda u, m: False)
    finally:
        AG._focus_active_now = real_focus_active
        AG._get_json = real_get_json
    return sent[0]["messages"] if sent else None


def t_a_running_unpaused_session_adds_the_note():
    q = {"role": "user", "content": "what's the capital of France"}
    got = turn([q], manner=None, focus_active=True)
    check("the note is there, just before the question",
          got == [BLOCK, FOCUS, q], json.dumps(got))


def t_no_session_or_paused_adds_nothing():
    # A bare first question with no note at all is sent exactly as it came
    # (test_agent.py: "a first question with nothing recalled is sent as it
    # is") - Ollama's own stored SYSTEM block covers it. Focus off adds
    # nothing here either, so this proves the note is really the only
    # difference the other cases show.
    q = {"role": "user", "content": "what's the capital of France"}
    got = turn([q], manner=None, focus_active=False)
    check("nothing added: sent exactly as it came", got == [q], json.dumps(got))


def t_additive_the_manner_line_still_shows_up():
    q = {"role": "user", "content": "what's the capital of France"}
    manner_line = {"role": "system", "content": AG.manner_message("plain")["content"]}
    got = turn([q], manner="plain", focus_active=True)
    check("both lines are there: manner AND focus, focus nearer the question",
          got == [BLOCK, manner_line, FOCUS, q], json.dumps(got))
    check("manner's own words are completely untouched by the focus note",
          manner_line["content"] == AG.manner_message("plain")["content"])


def t_a_follow_up_gets_the_note_just_before_the_question():
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello."}]
    q = {"role": "user", "content": "and now?"}
    got = turn(history + [q], manner=None, focus_active=True)
    check("the note lands right before the question, the rest untouched",
          got == history + [FOCUS, q], json.dumps(got))


def t_still_never_first_when_a_system_message_would_be():
    # Recalled facts (or any app's own system text) at position 0: the
    # rules go first (keep_rules_first), same as without a focus session -
    # the note never displaces that rule.
    facts = {"role": "system", "content": "Things you remember about the owner: ..."}
    q = {"role": "user", "content": "and now?"}
    got = turn([facts, q], manner=None, focus_active=True)
    check("the rules lead, then the recalled facts, then the note, then the question",
          got == [BLOCK, facts, FOCUS, q], json.dumps(got))


def t_with_focus_note_directly():
    check("on its own, never first",
          AG.with_focus_note([{"role": "user", "content": "x"}])[0] == BLOCK)
    check("no user message: a plain copy, nothing added",
          AG.with_focus_note([{"role": "system", "content": "x"}])
          == [{"role": "system", "content": "x"}])


def t_reads_no_network_and_no_state_by_itself():
    src = (BACKEND / "jarvis_agent.py").read_text(encoding="utf-8")
    i = src.index("def _focus_active_now")
    j = src.index("\n\n\n", i)
    body = src[i:j]
    check("_focus_active_now only reads jarvis_focus.is_active() - no gate, no card",
          "import jarvis_focus" in body and "jarvis_focus.is_active()" in body
          and "jarvis_gate" not in body and "request_id" not in body, body)


def t_is_active_reads_on_and_not_paused():
    saved_shipped = sys.modules.pop("jarvis_focus", None)
    try:
        import jarvis_focus as F

        class _Fake:
            on = False
            paused = False
        real_engine = F.ENGINE
        F.ENGINE = _Fake()
        try:
            check("off: not active", F.is_active() is False)
            F.ENGINE.on = True
            check("on, not paused: active", F.is_active() is True)
            F.ENGINE.paused = True
            check("on AND paused: not active - paused counts as off", F.is_active() is False)
            F.ENGINE.on = False
            check("off and paused: still not active", F.is_active() is False)
        finally:
            F.ENGINE = real_engine
    finally:
        if saved_shipped is not None:
            sys.modules["jarvis_focus"] = saved_shipped


def t_without_jarvis_focus_adds_nothing():
    saved = sys.modules.get("jarvis_focus")
    sys.modules["jarvis_focus"] = None
    try:
        check("no module: _focus_active_now says False, never a guess",
              AG._focus_active_now() is False)
    finally:
        if saved is None:
            sys.modules.pop("jarvis_focus", None)
        else:
            sys.modules["jarvis_focus"] = saved


if __name__ == "__main__":
    for fn in (t_a_running_unpaused_session_adds_the_note, t_no_session_or_paused_adds_nothing,
               t_additive_the_manner_line_still_shows_up,
               t_a_follow_up_gets_the_note_just_before_the_question,
               t_still_never_first_when_a_system_message_would_be,
               t_with_focus_note_directly, t_reads_no_network_and_no_state_by_itself,
               t_is_active_reads_on_and_not_paused, t_without_jarvis_focus_adds_nothing):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            import traceback
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
