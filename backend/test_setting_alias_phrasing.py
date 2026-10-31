"""test_setting_alias_phrasing.py - a settings NAME answers "how do I change it".

    python3 backend/test_setting_alias_phrasing.py

THE GAP (Gemini principal-architect ruling Q6 Step A, 2026-10-26). The
feature-talk fast path answers "how/where do I change <X>?" and "tell me about
<X>" from the 140-row feature catalogue. Five names the owner really uses are
not catalogue titles: `personality`, `voice speed` and `focus preset` are
CHOICE_SETTINGS rows, and `theme` / `hud layout` are desktop-only controls
inside a Settings card. "how do i change the personality?" matched nothing and
went to the local model (~2 s), which has no settings tool to answer it.

WHAT THIS PROVES
  1. THE FIVE RULED NAMES ANSWER ON THE FAST PATH, in all three question
     shapes - "how do i change", "where do i change", "tell me about" - with
     the real Settings place, a real example phrase, no model turn and no card.
  2. THE EXAMPLE PHRASE IT OFFERS REALLY ROUTES. Every "say ..." sentence in
     an answer is fed back through the same matcher and must reach a real
     change/open intent - never another dead end.
  3. AN UNKNOWN "X" STILL FALLS TO THE MODEL. "how do i change turbo?", "tell
     me about the kitchen light" and "how do i change my password" return
     None, exactly as before; the fallback is a registry-name lookup, not a
     land grab.
  4. THE PAGE-ONLY REFUSAL STILL WINS OVER EVERYTHING - including hyphens,
     slashes and filler ("windows hello for memory-lists and chat history"),
     and including a sentence that names TWO page-only rows (which used to
     fall through to the tolerant switch matcher and turn chat-history
     retention off with no card).
  5. Q5 (the same review's cleanup items). `find_not_by_asking` - the exact
     spoken helper the tolerant lookup replaced - is gone; the page-only and
     switch matchers that run in the same breath share ONE normaliser
     (`_setting_words`), proven by hyphen and slash forms; and a MIXED refusal
     gets the "ask for it separately" sentence while the plain refusal is
     byte-for-byte unchanged.
  6. NOTHING HERE CHANGES ANYTHING. Every routed answer is in
     READ_ONLY_INTENTS, carries no `made` receipt, and its runner touches the
     schedule only for the ordinary `mark_command` bookkeeping - a stand-in
     schedule raises on any other attribute, so a hidden write would fail this
     suite.

No model, no network, no settings file: the suite stops at `jarvis_quick`'s
own fast path.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))

import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class RecordingSched:
    """A schedule stand-in: `mark_command` is the fast path's bookkeeping;
    anything else is a write this read-only answer must never make."""

    def __init__(self):
        self.marked = []

    def mark_command(self, text):
        self.marked.append(text)

    def __getattr__(self, name):
        def _no(*a, **k):
            raise AssertionError(f"a read-only answer called schedule.{name}")
        return _no


def ask(text):
    """Run the fast path exactly as /api/chat does, with the stand-in schedule.

    None means the caller would ask the model - the thing this fix removes for
    the five ruled names. A Result means zero model turns."""
    sched = RecordingSched()
    got = Q.answer(text, sched=sched, now=time.time())
    return got, sched


#: The five names the ruling names, the intent/kind each must reach, and the
#: Settings card the answer must point at.
RULED = (
    ("the personality", "choice", "personality", "how jarvis talks"),
    ("the voice speed", "choice", "voice_speed", "voice"),
    ("the focus preset", "choice", "focus_preset", "focus presets"),
    ("the hud layout", "area", "hud-window", "the big hud window"),
    ("the theme", "area", "appearance-card", "appearance"),
)

SHAPES = ("how do i change {name}?",
          "where do i change {name}?",
          "tell me about {name}")


def t_the_five_ruled_names_answer_every_question_shape():
    """Ruling Q6 Step A: <X> from the settings registry answers on the fast path."""
    for name, kind, thing, place in RULED:
        for shape in SHAPES:
            phrase = shape.format(name=name)
            got, sched = ask(phrase)
            check(f'"{phrase}" answers without the model',
                  got is not None, got)
            if got is None:
                continue
            check(f'...as the settings fallback, not a feature answer',
                  got.intent == "setting_explain", got)
            check(f'...pointing at Settings, {place}',
                  f"Settings, {place}" in got.reply, got.reply)
            check(f'...and it is a read-only answer with no card',
                  got.intent in Q.READ_ONLY_INTENTS and not got.made
                  and Q.match(phrase) is not None, got)
            if kind == "choice":
                check(f'...for the {thing} setting',
                      Q.match(phrase).f.get("kind") == "choice"
                      and Q.match(phrase).f.get("key") == thing,
                      Q.match(phrase))
            else:
                check(f'...for the {thing} area',
                      Q.match(phrase).f.get("kind") == "area"
                      and Q.match(phrase).f.get("section") == thing,
                      Q.match(phrase))
            check("...and the schedule was touched only for mark_command",
                  sched.marked == [phrase], sched.marked)


def t_the_example_phrase_it_offers_really_routes():
    """An answer that names a phrase must name one the same matcher accepts."""
    for name, kind, thing, place in RULED:
        got, _ = ask(f"how do i change {name}?")
        if got is None:
            check(f"an answer exists for {name}", False, got)
            continue
        if kind == "choice":
            m = re.search(r'Say "set .+ to (.+)" and I will do it', got.reply)
            check(f"{name}: the answer offers a real set phrase", m is not None,
                  got.reply)
            if m is None:
                continue
            phrase = m.group(0)
            phrase = phrase[len('Say "'):-len('" and I will do it')]
            routed = Q.match(phrase)
            check(f'{name}: "{phrase}" routes to a real setter',
                  routed is not None
                  and routed.name in ("personality_set", "settings_choice",
                                      "control_set"),
                  routed)
        else:
            m = re.search(r'Say "(open .+ settings)" to go there', got.reply)
            check(f"{name}: the answer offers a real open phrase", m is not None,
                  got.reply)
            if m is None:
                continue
            routed = Q.match(m.group(1))
            check(f'{name}: "{m.group(1)}" opens the right card',
                  routed is not None and routed.name == "settings_open"
                  and routed.f.get("id") == thing, routed)


def t_an_unknown_x_still_falls_to_the_model():
    """No registry name: the old fall-through is untouched."""
    for phrase in ("how do i change turbo?",
                   "where do i change turbo?",
                   "tell me about turbo",
                   "how do i change my password?",
                   "how do i change my wifi password?",
                   "how do i change the kitchen light?",
                   "how do i change the layout presets?"):
        got = Q.answer(phrase, sched=RecordingSched(), now=time.time())
        check(f'"{phrase}" still falls through to the model', got is None, got)
    # And an explicitly-unknown FEATURE keeps its honest sentence, rather than
    # being given a setting's facts.
    got, _ = ask("jarvis how do i change the turbo feature?")
    check("an unknown feature keeps the honest feature_unknown answer",
          got is not None and got.intent == "feature_unknown", got)


def t_the_page_only_refusal_wins_over_everything():
    """Hyphen, slash and filler forms are all the page-only refusal."""
    base = R.not_by_asking_sentence("sec-private")
    for phrase in ("turn off windows hello for memory-lists and chat history",
                   "turn off windows hello for memory/lists and chat history",
                   "turn off the windows hello for memory lists and chat history setting",
                   "please turn off windows hello for memory lists and chat history now"):
        got, _ = ask(phrase)
        intent = Q.match(phrase)
        check(f'"{phrase}" is the page-only refusal',
              got is not None and got.intent == "settings_not_by_asking"
              and intent is not None and intent.f.get("dom_id") == "sec-private",
              got)
        check("...with the pinned refusal wording and no extra sentence",
              got is not None and got.reply == base, got.reply if got else None)
        check("...and never the switch whose words it contains",
              intent is None or intent.f.get("key") != "chat_history", intent)
    # TWO page-only rows in one sentence: it used to return no page-only row,
    # fall to the tolerant switch matcher and turn chat-history off at once.
    got, _ = ask("turn off the app lock and windows hello for memory lists "
                 "and chat history")
    check("a sentence naming TWO page-only rows is still a page-only refusal",
          got is not None and got.intent == "settings_not_by_asking", got)
    check("...and never a switch change",
          got is not None and got.intent != "settings_bool", got)


def t_a_mixed_refusal_offers_the_one_next_step():
    """Q5(c): the hint appears only when a second changeable setting is named."""
    hint = "(If you also want to change another setting, ask for it separately.)"
    base = R.not_by_asking_sentence("sec-app-lock")
    got, _ = ask("turn off the app lock and the prompt coach")
    intent = Q.match("turn off the app lock and the prompt coach")
    check("a page-only name beside a real switch still refuses",
          got is not None and got.intent == "settings_not_by_asking"
          and intent is not None and intent.f.get("dom_id") == "sec-app-lock",
          got)
    check("...and says to ask for the other setting separately",
          got is not None and got.reply == base + " " + hint, got.reply if got else None)
    got, _ = ask("turn off the app lock")
    check("the plain refusal is unchanged (no hint)",
          got is not None and got.reply == base, got.reply if got else None)
    # The model's own refusal (cannot_change_setting_words) is a different
    # surface and does not get the spoken sentence.
    said = R.cannot_change_setting_words("the app lock")
    check("the model-tool refusal keeps its own shape",
          said.startswith('I cannot change "the app lock" by asking.')
          and "ask for it separately" not in said, said)


def t_q5a_one_normaliser_for_the_two_tolerant_matchers():
    """Q5(a): the page-only guard and the switch matcher it guards see the
    same words. Hyphens, slashes, case and filler are ONE normaliser."""
    hyphen = "windows hello for memory-lists and chat history"
    slash = "windows hello for memory/lists and chat history"
    check("the page-only matcher folds a hyphen to a space",
          R.find_not_by_asking_words(hyphen) == "sec-private",
          R.find_not_by_asking_words(hyphen))
    check("...and a slash to a space",
          R.find_not_by_asking_words(slash) == "sec-private",
          R.find_not_by_asking_words(slash))
    check("the tolerant switch matcher also folds a hyphen",
          getattr(R.find_bool_setting_words("chat-history"), "key", None)
          == "chat_history",
          R.find_bool_setting_words("chat-history"))
    check("...so the page-only refusal must be decided first",
          R.page_only_asked(hyphen)[0] == "sec-private"
          and Q.match("turn off " + hyphen) is not None
          and Q.match("turn off " + hyphen).name == "settings_not_by_asking",
          Q.match("turn off " + hyphen))
    # The EXACT spoken switch lookup stays exact on purpose - it is not the
    # matcher this guard is paired with, and loosening it would let a half-heard
    # sentence change a switch the owner did not name (see its own docstring).
    check("the exact spoken switch lookup is deliberately NOT folded",
          R.find_bool_setting("chat-history") is None,
          R.find_bool_setting("chat-history"))


def t_q5b_the_dead_exact_helper_is_gone():
    """Q5(b): the exact `find_not_by_asking` has no caller left in the stack."""
    check("find_not_by_asking is gone from the registry",
          not hasattr(R, "find_not_by_asking"))
    check("its tolerant replacement is still the one the guard uses",
          R.find_not_by_asking_words("the app lock please") == "sec-app-lock",
          R.find_not_by_asking_words("the app lock please"))


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        t()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
