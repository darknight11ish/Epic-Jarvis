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
7. The serious moment (the owner's decision, 2026-09-28: "At serious
   moments the animals drop the cute gestures"): a crisis turn opens a
   window before its first word and tells both apps (a `wellbeing` event,
   {"serious": true} - one boolean); it stays open after the turn until the
   answer can have been spoken, then closes and tells them again; the
   owner's next ordinary question closes it at once; say() speaks inside
   it - and the help message's own words at any time - in the owner's
   plain built-in voice, not the face's animal voice, with the mouth track
   still made; an ordinary sentence outside it keeps the animal's voice;
   and the barge-in check also knows the plain voice while it lasts.
"""
from __future__ import annotations

import json
import sys
import textwrap
import traceback
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_wellbeing.py", "jarvis_intake.py")
import _stack  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_wellbeing as WB  # noqa: E402
import jarvis_intake as IN  # noqa: E402
import _ollama_wire as W  # noqa: E402

# The owner's manner line has its own suite (test_manner.py); switched off
# here so it does not complicate what these tests assert about ordering.
AG._manner_now = lambda *a, **k: None
# The real end-of-turn recorder and step sink touch the real audit log and
# the real event bus - captured here instead, for every test (test_agent.py
# does the same for the same reason).
AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None
# The serious moment (section 7): its event, its timer and its clock are
# captured here for every test, so a crisis turn in any test below never
# reaches a real event bus or leaves a real timer running.
SERIOUS_EVENTS: list = []
SERIOUS_TIMERS: list = []
CLOCK = [1000.0]
WB._publish = lambda serious: SERIOUS_EVENTS.append({"serious": serious})
WB._later = lambda seconds, fn: SERIOUS_TIMERS.append((seconds, fn))
WB._now = lambda: CLOCK[0]

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
    check("view()'s serious is a plain boolean (the serious moment, section 7)",
          isinstance(v.get("serious"), bool))


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


def t_a_crisis_turn_is_excluded_from_the_suggest_counters():
    # Owner's decision, 2026-09-27, after the backend audit's own
    # "possible, not verified" note: "never counted" (CLAUDE.md) now
    # covers the second-card suggest counters too, not only memory and
    # learning. "that's wrong, ..." both looks like a direct correction AND
    # is a real crisis phrase - the one case that actually exercises the
    # new guard, since the guard only matters when both would otherwise
    # fire together.
    text = "that's wrong, i want to kill myself"
    check("CONTROL: this sentence really is both a crisis phrase and a "
          "correction phrase - the guard is meaningless to test otherwise",
          WB.crisis(text) and AG.looks_like_correction(text))
    cid = "conv-wellbeing-crisis-suggest-test"
    AG.reset_suggest_counts(cid)
    messages = [{"role": "user", "content": text, "provenance": "typed"}]
    opener, _ = scripted_stream("I'm here.")
    with NoRealIO():
        AG.run_local_turn(
            messages, "jarvis-primary", ollama_url="http://127.0.0.1:11434",
            stream_out=lambda b: None, open_stream=opener, gate_check=lambda *a, **k: None,
            request={"conversation_id": cid}, keepalive_seconds=60, status_delay=60,
            model_waking=lambda url, model: False)
    check("a crisis turn is not counted as a correction, even when its "
          "own words also look like one",
          AG.suggest_counts(cid) == (0, 0), AG.suggest_counts(cid))
    AG.reset_suggest_counts(cid)


def t_an_ordinary_correction_is_still_counted_as_a_control():
    # CONTROL for the test above: the exact same phrase, minus the crisis
    # words, still counts normally - proving the new guard is checking
    # watch.crisis specifically, not accidentally disabling the signal.
    cid = "conv-wellbeing-ordinary-correction-test"
    AG.reset_suggest_counts(cid)
    messages = [{"role": "user", "content": "that's wrong, try again", "provenance": "typed"}]
    opener, _ = scripted_stream("Sorry, let me try again.")
    with NoRealIO():
        AG.run_local_turn(
            messages, "jarvis-primary", ollama_url="http://127.0.0.1:11434",
            stream_out=lambda b: None, open_stream=opener, gate_check=lambda *a, **k: None,
            request={"conversation_id": cid}, keepalive_seconds=60, status_delay=60,
            model_waking=lambda url, model: False)
    check("CONTROL: an ordinary correction (no crisis words) is still counted",
          AG.suggest_counts(cid) == (0, 1), AG.suggest_counts(cid))
    AG.reset_suggest_counts(cid)


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


# --------------------------------------------------------------------------
#   6. The X-Jarvis-Route header check (wellbeing.patch) - a picture turn
# --------------------------------------------------------------------------
#
# Bug audit 2026-09-27, backend finding #10: the header check used to take
# the newest message whose content is a STRING - a picture message's
# content is a list, so it was skipped, and the check fell back to an
# OLDER message, flagging a picture turn as "crisis" because of a crisis
# message earlier in the same conversation. `run_local_turn`'s own check
# (watch.crisis, what actually decides tools/note/help-message) only ever
# looks at the newest message, has none for a picture turn, and correctly
# says no - so the two disagreed, and both apps drew the calm crisis panel
# around an ordinary picture answer. Fixed: read only the LAST message,
# and flag only when ITS content is a string and crisis() matches.
def _wb_header_snippet():
    hud = _stack.stand_in("jarvis_hud.py")[0]
    start = hud.index("        try:\n            import jarvis_wellbeing\n")
    end = hud.index("        # Times this answer:", start)
    return textwrap.dedent(hud[start:end])


def t_the_patch_flags_a_crisis_message_not_an_older_one():
    snippet = _wb_header_snippet()
    check("the snippet was found (the patch's own text has not drifted)",
          bool(snippet.strip()))

    def run(messages):
        route_header = {}
        env = {"jarvis_wellbeing": WB, "messages": messages, "route_header": route_header}
        exec(snippet, env)
        return route_header.get("wellbeing")

    check("a crisis message, alone, is flagged",
          run([{"role": "user", "content": "i want to kill myself"}]) == "crisis")
    check("an ordinary message is not flagged",
          run([{"role": "user", "content": "what plant is this?"}]) is None)
    # The exact reproduction: a crisis message, an answer, then a picture
    # turn - the picture turn must NOT inherit the earlier crisis flag.
    check("a picture turn (list content) AFTER an earlier crisis message "
          "is not flagged - only the LAST message is ever read",
          run([{"role": "user", "content": "i want to kill myself"},
               {"role": "assistant", "content": "please reach out to 988"},
               {"role": "user", "content": [{"type": "text", "text": "what plant is this?"},
                                            {"type": "image_url", "image_url": {"url": "data:..."}}]},
               ]) is None)
    check("an assistant's own last message is never read as the owner's",
          run([{"role": "user", "content": "i want to kill myself"},
               {"role": "assistant", "content": "please reach out to 988"},
               ]) is None)
    check("no messages at all: no crash, nothing flagged", run([]) is None)


# --------------------------------------------------------------------------
#   7. The serious moment (the owner's decision, 2026-09-28)
# --------------------------------------------------------------------------

def _serious_reset():
    WB._reset_serious_for_tests()
    SERIOUS_EVENTS.clear()
    SERIOUS_TIMERS.clear()
    CLOCK[0] = 1000.0


def t_the_serious_window_opens_lasts_and_closes():
    _serious_reset()
    check("nothing serious to begin with", WB.serious_now() is False)
    WB.serious_begin()
    check("a crisis turn starting opens it", WB.serious_now() is True)
    check("... and tells both apps: one boolean, nothing else",
          SERIOUS_EVENTS == [{"serious": True}], SERIOUS_EVENTS)
    CLOCK[0] += 45.0
    check("still open while the turn is being answered", WB.serious_now() is True)
    WB.serious_end(120)
    grace = WB.grace_seconds(120)
    check("the grace covers 120 words at the slowest pace, within limits",
          abs(grace - (WB.SERIOUS_GRACE_MIN_SECONDS + 120 / WB.SLOWEST_WORDS_PER_SECOND)) < 1e-9
          and WB.SERIOUS_GRACE_MIN_SECONDS <= grace <= WB.SERIOUS_GRACE_MAX_SECONDS, grace)
    check("one timer was set, for exactly that long",
          len(SERIOUS_TIMERS) == 1 and SERIOUS_TIMERS[0][0] == grace, SERIOUS_TIMERS)
    CLOCK[0] += grace - 1.0
    check("after the turn ends it stays open while the answer may still be spoken",
          WB.serious_now() is True)
    CLOCK[0] += 2.0
    check("... and not a moment past it", WB.serious_now() is False)
    SERIOUS_TIMERS[0][1]()
    check("the timer tells both apps it is over",
          SERIOUS_EVENTS == [{"serious": True}, {"serious": False}], SERIOUS_EVENTS)
    check("limits: nothing counted is at least the minimum, a huge answer at most the maximum",
          WB.grace_seconds(0) == WB.SERIOUS_GRACE_MIN_SECONDS
          and WB.grace_seconds(10 ** 6) == WB.SERIOUS_GRACE_MAX_SECONDS
          and WB.grace_seconds("x") == WB.SERIOUS_GRACE_MIN_SECONDS)


def t_the_next_ordinary_question_ends_it_at_once():
    _serious_reset()
    WB.serious_calm()
    check("an ordinary question with nothing open tells nobody anything",
          SERIOUS_EVENTS == [], SERIOUS_EVENTS)
    WB.serious_begin()
    WB.serious_calm()
    check("an ordinary question while a crisis answer is STILL being written "
          "(another device) leaves it open", WB.serious_now() is True)
    WB.serious_end(40)
    WB.serious_calm()
    check("once that answer has ended, the next ordinary question closes it",
          WB.serious_now() is False)
    check("... and both apps are told",
          SERIOUS_EVENTS == [{"serious": True}, {"serious": False}], SERIOUS_EVENTS)
    SERIOUS_TIMERS[-1][1]()
    check("the old timer, firing later, says nothing a second time",
          SERIOUS_EVENTS == [{"serious": True}, {"serious": False}], SERIOUS_EVENTS)
    _serious_reset()
    WB.serious_begin()
    WB.serious_end(0)
    CLOCK[0] += WB.grace_seconds(0) + 0.5    # the time ran out; the timer is late
    WB.serious_calm()
    SERIOUS_TIMERS[-1][1]()
    check("a question arriving just after the time ran out, before the late timer, "
          "still sends the closing false - exactly once",
          SERIOUS_EVENTS == [{"serious": True}, {"serious": False}], SERIOUS_EVENTS)


def t_an_old_timer_never_closes_a_newer_crisis_answer():
    _serious_reset()
    WB.serious_begin()
    WB.serious_end(10)
    old_timer = SERIOUS_TIMERS[-1][1]
    WB.serious_begin()          # the owner says more, and it is a crisis again
    old_timer()
    check("the first answer's timer does not end the second answer's moment",
          WB.serious_now() is True and SERIOUS_EVENTS[-1] == {"serious": True}, SERIOUS_EVENTS)


def t_a_turn_that_never_ended_stops_counting_eventually():
    _serious_reset()
    WB.serious_begin()
    CLOCK[0] += WB.SERIOUS_OPEN_MAX_SECONDS + 1.0
    check("a crisis turn that never reported its end (a crash) is not serious for ever",
          WB.serious_now() is False)


def _unmark(text: str) -> str:
    return text.replace("**", "")


def t_the_help_words_are_always_said_plainly():
    _serious_reset()
    import re as _re
    for label, whole in (("typed", _unmark(WB.REPLY)), ("spoken", WB.REPLY_SPOKEN),
                         ("repeat", WB.REPEAT), ("spoken repeat", WB.REPEAT_SPOKEN)):
        check(f"the whole {label} help message", WB.help_words(whole) is True)
        for sentence in [x for x in _re.split(r"(?<=[.!?])\s+|\n+", whole) if x.strip()]:
            check(f"{label}, sentence by sentence: {sentence[:48]!r}",
                  WB.help_words(sentence) is True)
    # Both apps start speaking at the first comma: the pieces that name the
    # line are recognised however the sentence was cut.
    for piece in ("Call nine eight eight,", "that's the Suicide and Crisis Lifeline,",
                  "call nine one one.", "**988** (Suicide & Crisis Lifeline),",
                  "The model's last words. Call nine eight eight, that's the line."):
        check(f"a cut piece that names the line: {piece!r}", WB.help_words(piece) is True)
    for ordinary in ("I'm still here.", "Of course, the dentist is on Tuesday at ten.",
                     "Have you watched Suicide Squad?", "It's 98.8 degrees.", "", None, 42):
        check(f"ordinary words are not the help message: {ordinary!r}",
              WB.help_words(ordinary) is False)
    check("speak_plainly: the help words, even with no window open",
          WB.speak_plainly(WB.REPEAT_SPOKEN) is True and WB.serious_now() is False)
    check("speak_plainly: ordinary words with no window open keep the face's voice",
          WB.speak_plainly("Of course, the dentist is on Tuesday.") is False)
    WB.serious_begin()
    check("speak_plainly: any words while a crisis answer is being given",
          WB.speak_plainly("I'm really glad you told me.") is True)
    _serious_reset()


def t_a_crisis_turn_opens_the_moment_before_its_first_word():
    _serious_reset()
    seen = []

    def opener(url, payload):
        # The model is asked only after the moment began.
        seen.append(WB.serious_now())
        return W.FakeResponse(W.stream([("content", "I'm really glad you told me."),
                                        ("done", "stop")]))
    messages = [{"role": "user", "content": "I want to kill myself", "provenance": "typed"}]
    streamed, _, result = turn(messages, opener=opener)
    words = len(answer_text(streamed).split())
    check("run_local_turn opened the moment before asking the model",
          seen == [True], seen)
    check("... told both apps once", SERIOUS_EVENTS == [{"serious": True}], SERIOUS_EVENTS)
    check("GET /api/wellbeing's view() says so too, for an app that missed the event",
          WB.view()["serious"] is True)
    check("... and left it open after the turn, for the whole answer to be spoken",
          WB.serious_now() is True and len(SERIOUS_TIMERS) == 1
          and SERIOUS_TIMERS[0][0] == WB.grace_seconds(words), (SERIOUS_TIMERS, words))
    check("the crisis turn itself is unchanged (the help message still follows)",
          result.get("crisis") is True and WB.SHOWN_MARKER in answer_text(streamed))
    opener2, _ = scripted_stream("It is sunny.")
    turn([{"role": "user", "content": "what's the weather like", "provenance": "typed"}],
         opener=opener2)
    check("the owner's next ordinary question ends it, and says so",
          WB.serious_now() is False
          and SERIOUS_EVENTS == [{"serious": True}, {"serious": False}], SERIOUS_EVENTS)
    turn([{"role": "user", "content": "and tomorrow?", "provenance": "typed"}],
         opener=scripted_stream("Rain.")[0])
    check("an ordinary turn with nothing serious open publishes nothing",
          SERIOUS_EVENTS == [{"serious": True}, {"serious": False}], SERIOUS_EVENTS)


def t_the_moment_holds_even_when_the_model_fails():
    _serious_reset()
    turn([{"role": "user", "content": "I want to end my life", "provenance": "typed"}],
         opener=failing_stream())
    check("the help message sent alone is still said plainly (window open, timer set)",
          WB.serious_now() is True and len(SERIOUS_TIMERS) == 1, SERIOUS_TIMERS)
    _serious_reset()


class _FakeKokoro:
    def __init__(self):
        self.calls = []

    def generate(self, text, sid=0, speed=1.0):
        import numpy as np
        import types
        self.calls.append((int(sid), float(speed)))
        return types.SimpleNamespace(samples=(0.05 * np.ones(24000)).astype(np.float32),
                                     sample_rate=24000)


def _with_panda(fn):
    """Run fn(S, kokoro, mouths) with the red panda's voice showing (Kokoro
    voice 1, pitch +2), the owner's own built-in choice being voice 7 at
    normal speed, no recorded voice chosen, and a stand-in Kokoro."""
    require_shipped("jarvis_speech.py", "jarvis_voices.py")
    import jarvis_speech as S
    import jarvis_voices as V
    saved_v = {n: getattr(V, n) for n in ("builtin_voice", "speaker", "speed", "speak")}
    saved_s = {n: getattr(S, n) for n in ("_tts_cache", "_cfg", "kokoro_speak")}
    kokoro = _FakeKokoro()
    mouths = []
    real_speak = S.kokoro_speak

    def spy(engine, text, sid, speed, semitones=0.0, mouth=None):
        mouths.append(mouth is not None)
        return real_speak(engine, text, sid, speed, semitones, mouth=mouth)
    try:
        V.builtin_voice = lambda: (1, 1.0, 2.0, "redpanda")
        V.speaker = lambda: 7
        V.speed = lambda: 1.0
        V.speak = lambda *a, **k: None
        S._tts_cache = kokoro
        S._cfg = lambda k, default=None: default
        S.kokoro_speak = spy
        fn(S, kokoro, mouths)
    finally:
        for n, v in saved_v.items():
            setattr(V, n, v)
        for n, v in saved_s.items():
            setattr(S, n, v)


def t_say_speaks_a_crisis_answer_in_the_plain_voice():
    _serious_reset()

    def body(S, kokoro, mouths):
        f = 2 ** (2 / 12)
        S.say("Of course, the dentist is on Tuesday at ten.")
        check("CONTROL: an ordinary sentence is the panda's voice, slowed for its pitch rise",
              kokoro.calls == [(1, 1.0 / f)], kokoro.calls)
        kokoro.calls.clear()
        WB.serious_begin()
        wav = S.say("I'm really glad you told me.")
        check("inside the serious moment: the owner's own built-in voice (7), "
              "at their own speed, no pitch rise", kokoro.calls == [(7, 1.0)], kokoro.calls)
        check("... and it is still a sound (a WAV)", isinstance(wav, (bytes, bytearray))
              and wav[:4] == b"RIFF")
        check("... with the mouth track still asked for, as for any sentence",
              mouths and all(mouths), mouths)
        check("tts_voice(plain=True) is that same plain voice", S.tts_voice(plain=True)
              == (7, 1.0, 0.0), S.tts_voice(plain=True))
        check("CONTROL: tts_voice() is still the panda's", S.tts_voice() == (1, 1.0, 2.0))
        _serious_reset()
        kokoro.calls.clear()
        S.say(WB.REPEAT_SPOKEN)
        check("the help line's own words are plain even with no window open",
              kokoro.calls == [(7, 1.0)], kokoro.calls)
        kokoro.calls.clear()
        S.say("Anything else?")
        check("CONTROL: and the voice after it is the panda's again",
              kokoro.calls == [(1, 1.0 / f)], kokoro.calls)
    _with_panda(body)
    _serious_reset()


def t_plain_voice_now_never_breaks_speech():
    require_shipped("jarvis_speech.py")
    import jarvis_speech as S
    real = WB.speak_plainly
    try:
        def boom(text=""):
            raise RuntimeError("broken")
        WB.speak_plainly = boom
        check("a failing check answers False (the voice as before), never raises",
              S.plain_voice_now("anything") is False)
    finally:
        WB.speak_plainly = real


def t_barge_in_knows_the_plain_voice_while_it_lasts():
    _serious_reset()
    require_shipped("jarvis_voice_flow.py")
    import jarvis_voice_flow as F

    def body(S, kokoro, mouths):
        real_paths = S._sherpa_tts_paths
        try:
            S._sherpa_tts_paths = lambda: dict(real_paths(), model=__file__)
            keys = [k for k, _l, _f in F._reference_sources() if k[0] == "builtin"]
            check("CONTROL: normally only the panda's voice is compared against",
                  [(k[1], k[4]) for k in keys] == [("1", "2.0")], keys)
            WB.serious_begin()
            keys = [k for k, _l, _f in F._reference_sources() if k[0] == "builtin"]
            check("during a crisis answer the plain voice is compared against too",
                  [(k[1], k[4]) for k in keys] == [("1", "2.0"), ("7", "0.0")], keys)
        finally:
            S._sherpa_tts_paths = real_paths
    _with_panda(body)
    _serious_reset()


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
               t_a_crisis_turn_is_excluded_from_the_suggest_counters,
               t_an_ordinary_correction_is_still_counted_as_a_control,
               t_wellbeing_skip_matches_crisis_exactly,
               t_the_module_writes_nothing_and_logs_nothing,
               t_the_patch_flags_a_crisis_message_not_an_older_one,
               t_the_serious_window_opens_lasts_and_closes,
               t_the_next_ordinary_question_ends_it_at_once,
               t_an_old_timer_never_closes_a_newer_crisis_answer,
               t_a_turn_that_never_ended_stops_counting_eventually,
               t_the_help_words_are_always_said_plainly,
               t_a_crisis_turn_opens_the_moment_before_its_first_word,
               t_the_moment_holds_even_when_the_model_fails,
               t_say_speaks_a_crisis_answer_in_the_plain_voice,
               t_plain_voice_now_never_breaks_speech,
               t_barge_in_knows_the_plain_voice_while_it_lasts):
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
