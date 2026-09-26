"""test_wellbeing.py - the crisis help line (jarvis_wellbeing.py; CLAUDE.md,
"Decided 2026-09-27, the owner's answers": "Crisis help line: United States
- 988 (Suicide & Crisis Lifeline) and 911." and "Crisis messages are never
learned from and never counted."). docs/JARVIS-API.md section 38.

    python3 backend/test_wellbeing.py

Runs anywhere; no model and no network are needed. What it proves:

1. crisis() matches the plain-English crisis phrases and does not match the
   false-alarm list ("this bug is killing me", "kill the process", "Suicide
   Squad", "I'm dying to see it", "dead tired", and more of the same shape).
2. The fixed texts (REPLY, REPLY_SPOKEN, REPEAT, REPEAT_SPOKEN, NOTE) carry
   the owner's US numbers (988, 911) and nothing else - no UK/Ireland
   numbers, no invented claim of feelings ("I feel", "I love", "I miss",
   "I care"), no phone number written anywhere but in code, not by a model.
3. In a real run_local_turn turn: the crisis note (NOTE) is never the first
   message (the Jarvis rules block stays first); no tools are offered; the
   caller's own `messages` list is never mutated; the help message is
   appended after the model's own words, and sent ALONE - no error object -
   when the model fails or times out; a second mention in the same
   conversation gets the short repeat line, not the whole message again.
4. A crisis turn is excluded from jarvis_intake.owner_turns() - the same way
   a scheduler command already is - so it can never be learned or counted.
5. Nothing here writes to disk or logs anything: read straight off the
   module's own source, which has no `open(`, `write(`, `print(` or
   `logging` at all.
"""
from __future__ import annotations

import json
import sys
import traceback
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_wellbeing.py", "jarvis_intake.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_wellbeing as WB  # noqa: E402
import jarvis_intake as IN  # noqa: E402
import _ollama_wire as W  # noqa: E402

# The owner's manner line has its own suite (test_manner.py); switched off
# here so it does not complicate what these tests assert about ordering.
AG._manner_now = lambda: None
# The real end-of-turn recorder and step sink touch the real audit log and
# the real event bus - captured here instead, for every test (test_agent.py
# does the same for the same reason).
AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoRealIO:
    """Fail loudly if the real (network-touching) post/stream ever runs -
    the context-length and tool-capability lookups (/api/ps, /api/show)
    answer "cannot tell" instead, which is the conservative default."""

    def __enter__(self):
        self.real_post, self.real_stream = AG._post, AG._open_stream
        self.real_get = AG._get_json

        def boom(*a, **k):
            raise AssertionError("a real HTTP call ran")

        def no_lookup(*a, **k):
            raise OSError("no network in this test")
        AG._post, AG._open_stream, AG._get_json = boom, boom, no_lookup
        AG._CTX_CACHE.clear()
        AG._TOOLS_CACHE.clear()
        return self

    def __exit__(self, *a):
        AG._post, AG._open_stream = self.real_post, self.real_stream
        AG._get_json = self.real_get
        return False


def scripted_stream(text: str):
    """An open_stream that answers one round with `text`, and records the
    request body it was sent."""
    calls = []

    def opener(url, payload):
        calls.append(payload)
        return W.FakeResponse(W.stream([("content", text), ("done", "stop")]))
    return opener, calls


def failing_stream():
    """An open_stream standing in for Ollama being down or timing out."""
    def opener(url, payload):
        raise OSError("Ollama is not answering")
    return opener


def answer_text(streamed) -> str:
    """The words an app would show, read out of the streamed SSE bytes."""
    text = []
    for line in b"".join(streamed).split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:") or line[5:].strip() == b"[DONE]":
            continue
        obj = json.loads(line[5:])
        delta = obj["choices"][0].get("delta") or {}
        text.append(delta.get("content") or "")
    return "".join(text)


def has_error(streamed) -> bool:
    for line in b"".join(streamed).split(b"\n"):
        line = line.strip()
        if line.startswith(b"data:") and line[5:].strip() != b"[DONE]":
            obj = json.loads(line[5:])
            if "error" in obj:
                return True
    return False


def turn(messages, *, opener, enabled_tools=None):
    """One run_local_turn call; returns (streamed bytes list, the request
    body sent to the model, or None if the model was never reached)."""
    calls = []

    def wrapped(url, payload):
        calls.append(payload)
        return opener(url, payload)
    streamed = []
    with NoRealIO():
        result = AG.run_local_turn(
            messages, "jarvis-primary", ollama_url="http://127.0.0.1:11434",
            stream_out=streamed.append, open_stream=wrapped, gate_check=lambda *a, **k: None,
            enabled_tools=enabled_tools, keepalive_seconds=60, status_delay=60,
            model_waking=lambda url, model: False)
    return streamed, (calls[0] if calls else None), result


# --------------------------------------------------------------------------
#   1. The word check
# --------------------------------------------------------------------------

CRISIS_CASES = (
    "I want to kill myself",
    "I want to end my life",
    "I just want to die",
    "I've been thinking about self-harm",
    "I hurt myself last night",
    "sometimes I try to hurt myself",
    "there is no reason to live anymore",
    "everyone would be better off without me",
    "I don't want to be here anymore",
    "I feel suicidal",
    "I feel hopeless",
    "I'm thinking about suicide",
    "she took her own life",  # third person still catches it (the wording, not the subject)
)

FALSE_ALARM_CASES = (
    "this bug is killing me",
    "kill the process",
    "have you watched Suicide Squad",
    "I'm dying to see the new movie",
    "dead tired after that run",
    "can you kill the lights before bed",
    "let's kill two birds with one stone",
    "that new track is killing it on the charts",
    "sudden death overtime in the game last night",
    "my whole team is on suicide watch about this deadline",
    "he loves a suicide king in poker",
    "the old car had suicide doors",
)


def t_crisis_phrases_match():
    for text in CRISIS_CASES:
        check(f"crisis() is True for {text!r}", WB.crisis(text) is True)


def t_false_alarms_do_not_fire():
    for text in FALSE_ALARM_CASES:
        check(f"crisis() is False for {text!r}", WB.crisis(text) is False)


def t_crisis_is_a_pure_check():
    check("not a string: False, never raises", WB.crisis(None) is False)
    check("empty string: False", WB.crisis("") is False)
    check("whitespace only: False", WB.crisis("   \n\t") is False)
    check("an ordinary question: False", WB.crisis("what time is it in Tokyo?") is False)


# --------------------------------------------------------------------------
#   2. The fixed texts
# --------------------------------------------------------------------------

_NO_FEELINGS = ("i feel", "i love", "i miss", "i care")
# Numbers this module must never give out - the report's own UK/Ireland
# draft, which the owner did not choose (CLAUDE.md, 2026-09-27: "United
# States - 988 ... and 911", not the report's guess).
_WRONG_NUMBERS = ("116 123", "999", "112")


def t_fixed_texts_have_only_the_us_numbers():
    # The typed texts write digits; the spoken ones say them as words
    # (jarvis_agent.SPOKEN_NOTE's own rule: "write numbers the way they are
    # said"), so each is checked in its own shape, not against "988".
    check("REPLY carries 988", "988" in WB.REPLY, WB.REPLY)
    check("REPLY carries 911", "911" in WB.REPLY, WB.REPLY)
    check("REPEAT carries 988", "988" in WB.REPEAT, WB.REPEAT)
    check("REPLY_SPOKEN says the help number as digits (nine eight eight)",
          "nine eight eight" in WB.REPLY_SPOKEN, WB.REPLY_SPOKEN)
    check("REPLY_SPOKEN says the emergency number as digits (nine one one)",
          "nine one one" in WB.REPLY_SPOKEN, WB.REPLY_SPOKEN)
    check("REPLY_SPOKEN never writes the numbers as digits",
          "988" not in WB.REPLY_SPOKEN and "911" not in WB.REPLY_SPOKEN, WB.REPLY_SPOKEN)
    check("REPEAT_SPOKEN says the help number as digits (nine eight eight)",
          "nine eight eight" in WB.REPEAT_SPOKEN, WB.REPEAT_SPOKEN)
    check("REPEAT_SPOKEN never writes the number as digits",
          "988" not in WB.REPEAT_SPOKEN, WB.REPEAT_SPOKEN)
    for name, text in (("REPLY", WB.REPLY), ("REPLY_SPOKEN", WB.REPLY_SPOKEN),
                       ("REPEAT", WB.REPEAT), ("REPEAT_SPOKEN", WB.REPEAT_SPOKEN),
                       ("NOTE", WB.NOTE)):
        low = text.lower()
        for wrong in _WRONG_NUMBERS:
            check(f"{name} does not carry the wrong number {wrong!r}", wrong not in text, text)
        for phrase in _NO_FEELINGS:
            check(f"{name} claims no feeling ({phrase!r})", phrase not in low, text)


def t_note_never_writes_a_number_itself():
    check("NOTE tells the model not to write phone numbers itself",
          "do not write phone numbers" in WB.NOTE.lower(), WB.NOTE)
    check("NOTE never mentions 988 or 911 itself - only Jarvis's own code does",
          "988" not in WB.NOTE and "911" not in WB.NOTE, WB.NOTE)


def t_reply_gives_the_short_line_once_shown():
    check("first mention: the full message", WB.reply() == WB.REPLY)
    check("repeat: the short line", WB.reply(repeat=True) == WB.REPEAT)
    check("first mention, spoken: the full spoken message",
          WB.reply(spoken=True) == WB.REPLY_SPOKEN)
    check("repeat, spoken: the short spoken line",
          WB.reply(repeat=True, spoken=True) == WB.REPEAT_SPOKEN)
    check("the repeat line does not itself look like a first mention",
          not WB.shown_before([{"role": "assistant", "content": WB.REPEAT}]))
    check("the full message DOES mark a conversation as having shown it",
          WB.shown_before([{"role": "assistant", "content": WB.REPLY}]))


def t_view_matches_the_fixed_texts():
    v = WB.view()
    check("view() is available with no settings to change (no off switch)", v.get("available") is True)
    check("view()'s reply is REPLY word for word", v.get("reply") == WB.REPLY)
    check("view()'s repeat is REPEAT word for word", v.get("repeat") == WB.REPEAT)
    check("view()'s help_number is 988", v.get("help_number") == "988")
    check("view()'s emergency_number is 911", v.get("emergency_number") == "911")


# --------------------------------------------------------------------------
#   3. Wired into run_local_turn
# --------------------------------------------------------------------------

def t_rules_stay_first_and_the_crisis_note_is_nearest_the_question():
    messages = [{"role": "user", "content": "I want to kill myself", "provenance": "typed"}]
    before = json.dumps(messages)
    opener, _ = scripted_stream("I'm here.")
    _, sent, _ = turn(messages, opener=opener)
    check("the caller's own messages list is never mutated", json.dumps(messages) == before)
    check("a request was actually sent", sent is not None, sent)
    got = sent["messages"]
    check("the Jarvis rules block is first",
          got[0] == {"role": "system", "content": AG.LANE_SYSTEM}, [m.get("role") for m in got])
    check("the crisis note is in the request",
          any(m.get("content") == WB.NOTE for m in got), got)
    check("the crisis note sits directly before the newest user message - "
          "nearest the question of every note here",
          got[-2] == {"role": "system", "content": WB.NOTE} and got[-1] == messages[0], got)


def t_no_tools_offered_on_a_crisis_turn():
    messages = [{"role": "user", "content": "I want to end my life", "provenance": "typed"}]
    opener, _ = scripted_stream("I'm here.")
    # enabled_tools=None means "every tool this module has" on an ordinary
    # turn (offered_tools' own contract) - so if this is empty, it is the
    # crisis check turning them off, not the caller asking for none.
    _, sent, _ = turn(messages, opener=opener, enabled_tools=None)
    check("no tools are offered on a crisis turn", not sent.get("tools"), sent.get("tools"))


def t_tools_are_offered_as_normal_on_an_ordinary_turn():
    # The control for the test above: without a crisis phrase, tools are
    # offered as they always were.
    messages = [{"role": "user", "content": "what's a good calculator tool for this?", "provenance": "typed"}]
    opener, _ = scripted_stream("Sure.")
    _, sent, _ = turn(messages, opener=opener, enabled_tools={"calculator"})
    check("CONTROL: an ordinary turn still offers its enabled tools",
          bool(sent.get("tools")), sent)


def t_the_help_message_follows_the_models_own_words():
    messages = [{"role": "user", "content": "I want to kill myself", "provenance": "typed"}]
    opener, _ = scripted_stream("I'm really glad you told me.")
    streamed, _, result = turn(messages, opener=opener)
    text = answer_text(streamed)
    check("the model's own words are still said",
          text.startswith("I'm really glad you told me."), text)
    check("the help message follows it, with the real US number",
          WB.SHOWN_MARKER in text, text)
    check("911 is in the answer the app receives", "911" in text, text)
    check("run_local_turn's own result says this was a crisis turn",
          result.get("crisis") is True, result)
    check("the turn still ends normally (finish_reason stop)",
          result.get("finish_reason") == "stop", result)


def t_the_help_message_is_sent_alone_when_the_model_fails():
    messages = [{"role": "user", "content": "I want to end my life", "provenance": "typed"}]
    streamed, sent, result = turn(messages, opener=failing_stream())
    text = answer_text(streamed)
    check("a request was attempted", sent is not None, sent)
    check("no error object reaches the app - the help message replaces it",
          not has_error(streamed), streamed)
    check("the help message, and only the help message, is what is sent",
          text == WB.REPLY, text)
    check("the turn still reports finish_reason stop, not a dead turn",
          result.get("finish_reason") == "stop", result)
    check("run_local_turn's own result says this was a crisis turn",
          result.get("crisis") is True, result)


def t_an_ordinary_failure_still_gets_the_plain_error():
    # The control: without a crisis phrase, a model failure is still
    # reported as an error, exactly as before this module existed.
    messages = [{"role": "user", "content": "what's the weather like", "provenance": "typed"}]
    streamed, _, result = turn(messages, opener=failing_stream())
    check("CONTROL: an ordinary failure still sends an error object",
          has_error(streamed), streamed)
    check("CONTROL: run_local_turn's result says this was not a crisis turn",
          result.get("crisis") is False, result)


def t_a_repeat_mention_gets_the_short_line_not_the_whole_message_again():
    messages = [
        {"role": "user", "content": "I want to kill myself", "provenance": "typed"},
        {"role": "assistant", "content": "I'm here. " + WB.REPLY},
        {"role": "user", "content": "I still want to kill myself", "provenance": "typed"},
    ]
    opener, _ = scripted_stream("I hear you.")
    streamed, _, result = turn(messages, opener=opener)
    text = answer_text(streamed)
    check("a repeat mention still counts as a crisis turn", result.get("crisis") is True, result)
    check("the short repeat line is said this time", WB.REPEAT in text, text)
    check("the FULL help message is not said a second time this turn",
          text.count(WB.SHOWN_MARKER) == 0, text)


def t_a_first_mention_is_told_apart_from_a_conversation_with_no_history():
    check("shown_before() is False for a first message with nothing before it",
          WB.shown_before([{"role": "user", "content": "I want to kill myself"}]) is False)
    check("shown_before() ignores a USER message that happens to contain the marker "
          "(only an assistant turn counts - the app cannot forge Jarvis having said it)",
          WB.shown_before([{"role": "user", "content": WB.SHOWN_MARKER}]) is False)


# --------------------------------------------------------------------------
#   4. Never learned, never counted
# --------------------------------------------------------------------------

def t_a_crisis_turn_is_excluded_from_owner_turns():
    convo = [
        {"role": "user", "content": "I want to kill myself"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "my sister likes jazz"},
    ]
    got = [m["content"] for m in IN.owner_turns(convo, "owner")]
    check("the crisis turn is not handed to the learner", "I want to kill myself" not in got, got)
    check("CONTROL: an ordinary turn in the same conversation still is",
          "my sister likes jazz" in got, got)


def t_wellbeing_skip_matches_crisis_exactly():
    check("wellbeing_skip agrees with crisis() on a real phrase",
          IN.wellbeing_skip("I want to end my life") is True)
    check("wellbeing_skip agrees with crisis() on a false alarm",
          IN.wellbeing_skip("kill the process") is False)
    check("wellbeing_skip is False for anything that is not a string",
          IN.wellbeing_skip(None) is False)


# --------------------------------------------------------------------------
#   5. Nothing written to disk or logged
# --------------------------------------------------------------------------

def t_the_module_writes_nothing_and_logs_nothing():
    src = (HERE / "jarvis_wellbeing.py").read_text(encoding="utf-8")
    for bad in ("open(", ".write(", "logging.", "print(", "requests.", "urllib.request",
                "socket.", "subprocess."):
        check(f"jarvis_wellbeing.py never uses {bad!r}", bad not in src)


if __name__ == "__main__":
    for fn in (t_crisis_phrases_match,
               t_false_alarms_do_not_fire,
               t_crisis_is_a_pure_check,
               t_fixed_texts_have_only_the_us_numbers,
               t_note_never_writes_a_number_itself,
               t_reply_gives_the_short_line_once_shown,
               t_view_matches_the_fixed_texts,
               t_rules_stay_first_and_the_crisis_note_is_nearest_the_question,
               t_no_tools_offered_on_a_crisis_turn,
               t_tools_are_offered_as_normal_on_an_ordinary_turn,
               t_the_help_message_follows_the_models_own_words,
               t_the_help_message_is_sent_alone_when_the_model_fails,
               t_an_ordinary_failure_still_gets_the_plain_error,
               t_a_repeat_mention_gets_the_short_line_not_the_whole_message_again,
               t_a_first_mention_is_told_apart_from_a_conversation_with_no_history,
               t_a_crisis_turn_is_excluded_from_owner_turns,
               t_wellbeing_skip_matches_crisis_exactly,
               t_the_module_writes_nothing_and_logs_nothing):
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
