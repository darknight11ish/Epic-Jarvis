"""test_feature_control_phrases.py - the audit brief's own sentences, driven.

    python3 backend/test_feature_control_phrases.py

WHY THIS SUITE EXISTS (2026-11-13)

`D:\\jarvis-scratch\\awareness-audit-2026-11-13\\CONTROL-MATRIX.md` scored ten
control rows by reading the grammar and the setters. It marked one cell NOT
VERIFIED and one PASS-by-title-only, and both for the same reason: nobody had
run the owner's own sentences through `jarvis_quick.match()`. This suite runs
them, so the next matrix can cite a test instead of an inference.

Measured on `origin/main` before this suite existed (`a6f8496f`):

    "turn on GitHub reads"                    -> None  (went to the model)
    "stop asking before you read my github"   -> None  (went to the model)

and `github_inspect` - the READ-ONLY switch that puts the GitHub reads card
back - had no spoken name in `jarvis_settings_registry._ASKS_FIRST_TARGETS` at
all. So the owner's own words for the one control that spends his GitHub token
reached nothing.

WHAT IT PINS

  1. Every sentence in the brief resolves to the intent CONTROL-MATRIX names,
     with the row and the direction it names - not merely "something".
  2. The two companion writes and the VoiceStudio switch are REFUSED in a
     private chat, and the VoiceStudio STATE answer is allowed there (it writes
     nothing) - the same split the module's own allowlist documents.
  3. VoiceStudio: ON needs an approval card, OFF is instant and cardless, and
     ON never claims it turned the switch on when no card could be shown.

No model runs, no network, no owner file is touched: `match()` and `answer()`
read the shipped modules and a made-up scheduler, and the config folder is a
temp one.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-control-phrases-"))
for _name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME",
              "JARVIS_LOG_DIR"):
    os.environ.setdefault(_name, str(_TMP / _name.lower()))

import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []


def check(label: str, ok: bool, detail="") -> None:
    if ok:
        PASSED.append(label)
        print("  ok    " + label)
    else:
        FAILED.append(label)
        print("  FAIL  " + label)
        if detail:
            print("          " + str(detail)[:300])


class Sched:
    """A made-up scheduler: a control answer that touched the real one fails."""

    def __init__(self):
        self.commands = []

    def listed(self):
        return []

    def mark_command(self, text):
        self.commands.append(text)


def _answer(sentence, private=False):
    intent = Q.match(sentence)
    if intent is None:
        return None, None
    return Q.answer(sentence, sched=Sched(), private=private), intent


#: (sentence, intent name, the fields that must say which row and direction).
#: The third column is CONTROL-MATRIX's own claim, turned into data.
BRIEF = (
    ("turn on GitHub reads", "settings_asks_first",
     {"action": "github_inspect", "ask": True}),
    ("turn off GitHub reads", "settings_asks_first",
     {"action": "github_inspect", "ask": False}),
    ("stop asking before you read my github", "settings_asks_first",
     {"action": "github_inspect", "ask": False}),
    ("ask me first before you read my github", "settings_asks_first",
     {"action": "github_inspect", "ask": True}),
    ("turn on the github merge pr tool", "settings_tool",
     {"tool": "github_merge_pr", "on": True}),
    ("turn on avatar", "companion_toggle",
     {"action": "turn on", "feature": "avatar"}),
    ("set avatar style to reticle", "companion_set_style",
     {"setting": "avatar style", "value": "reticle"}),
    ("turn on voicestudio", "voicestudio_set", {"on": True}),
    ("turn off voicestudio", "voicestudio_set", {"on": False}),
    ("is voicestudio on", "voicestudio_state", {}),
    ("what is the voicestudio switch set to", "voicestudio_state", {}),
)


# --------------------------------------------------------------------------
#   1. the brief's sentences reach the row and direction it names
# --------------------------------------------------------------------------
def t_the_briefs_sentences_resolve_to_their_rows():
    for sentence, name, want in BRIEF:
        got = Q.match(sentence)
        check(f"resolves, never the model: {sentence!r}", got is not None, repr(got))
        if got is None:
            continue
        check(f"... to {name}: {sentence!r}", got.name == name, got.name)
        for key, value in want.items():
            check(f"... {key}={value!r}: {sentence!r}",
                  got.f.get(key) == value, got.f.get(key))


def t_every_brief_sentence_has_a_real_answer():
    """A resolved intent that then answers nothing is not a control."""
    for sentence, _name, _want in BRIEF:
        res, intent = _answer(sentence)
        check(f"the answer is a sentence: {sentence!r}",
              res is not None and len(str(res.reply)) > 20,
              "" if res is None else str(res.reply)[:160])
        check(f"... and it wrote nothing: {sentence!r}",
              res is not None and not res.made and res.open_settings is None
              and res.open_brain is None)


# --------------------------------------------------------------------------
#   2. a private chat refuses every write, and still answers the state
# --------------------------------------------------------------------------
def t_a_private_chat_refuses_the_writes_and_answers_the_state():
    writes = ("turn on voicestudio", "turn off voicestudio", "turn on avatar",
              "set avatar style to reticle", "turn on GitHub reads")
    for sentence in writes:
        res, intent = _answer(sentence, private=True)
        check(f"a private chat refuses the change: {sentence!r}",
              intent is not None and res is not None, repr(intent))
        if res is None:
            continue
        check(f"... in the documented words: {sentence!r}",
              "private chat can read, search, and answer" in res.reply,
              res.reply[:160])
        check(f"... and says it changes nothing: {sentence!r}",
              "doesn't change settings" in res.reply, res.reply[:160])
    res, intent = _answer("is voicestudio on", private=True)
    check("a private chat still answers the VoiceStudio state",
          intent is not None and res is not None
          and "VoiceStudio is" in res.reply, "" if res is None else res.reply[:120])


# --------------------------------------------------------------------------
#   3. VoiceStudio: ON is one card, OFF is instant, neither starts anything
# --------------------------------------------------------------------------
def t_voicestudio_on_needs_a_card_and_off_needs_none():
    off, _ = _answer("turn off voicestudio")
    check("OFF is instant: no card is mentioned",
          off is not None and "approval card" not in off.reply, off.reply[:200])
    check("... and it says nothing changed",
          off is not None and "Nothing was changed" in off.reply, off.reply[:200])
    on, _ = _answer("turn on voicestudio")
    check("ON names the approval card", on is not None and "approval card" in on.reply,
          on.reply[:200])
    check("... and never claims the switch went on",
          on is not None and "is on now" not in on.reply, on.reply[:200])
    check("... and never claims anything was started",
          on is not None and "started" not in on.reply.replace("Nothing was started", ""),
          on.reply[:200])
    state, _ = _answer("is voicestudio on")
    check("the state answer names the switch and both doors",
          state is not None and "[voicestudio] enabled" in state.reply
          and "voicestudio_sidecar.ps1 -Start" in state.reply
          and "Settings" in state.reply, state.reply[:260])


def t_the_voice_sentences_do_not_steal_other_switch_questions():
    """The new names are narrow: an ordinary setting question keeps its own row."""
    for sentence in ("turn on the timer tool", "turn on web search",
                     "turn off chat history", "turn on the github merge pr tool"):
        got = Q.match(sentence)
        check(f"an ordinary switch keeps its own owner: {sentence!r}",
              got is not None and got.name != "voicestudio_set", repr(got))
    # And a sentence naming a row that does not exist is still not this one:
    # the older honesty answer keeps it (the new names are closed-world).
    got = Q.match("turn on the flux capacitor setting")
    check("a made-up control is not read as the VoiceStudio switch",
          got is None or got.name != "voicestudio_set", repr(got))


def main():
    for fn in (t_the_briefs_sentences_resolve_to_their_rows,
               t_every_brief_sentence_has_a_real_answer,
               t_a_private_chat_refuses_the_writes_and_answers_the_state,
               t_voicestudio_on_needs_a_card_and_off_needs_none,
               t_the_voice_sentences_do_not_steal_other_switch_questions):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
