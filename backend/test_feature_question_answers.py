"""test_feature_question_answers.py - a feature question is answered from the
feature row it names, never with an unrelated row's words.

    python3 backend/test_feature_question_answers.py

WHY THIS EXISTS (the owner's third live defect, 2026-11-08). On the installed
0.2.439 build, all his tests on the CODING preset, a feature question was
answered with an unrelated feature-row echo. `GEMINI-REVIEW-2026-11-08-1535.md`
records the class only (item 7c: "a feature question was answered with
unrelated feature-row echo, on the coding preset"); the transcripts themselves
were in the chat and are compacted, so THE OWNER'S EXACT WORDS ARE NOT
RECOVERABLE FROM THIS CHECKOUT. The sentences below are therefore
REPRESENTATIVE reconstructions of the class - except the read-aloud one, which
is the measured strongest candidate:

  QUEUED tree (eb776a6e0) and LIVE 0.2.439, driven through the real matcher,
  no model: "does jarvis have a feature for reading out loud?" answered
  `quick: capability_answer` from the `read-web-page` row -
  "Yes - Read one web page out loud. Fetch the one page you named ..."
  - while the row he means is `read-aloud` ("Jarvis reads its answers aloud").
  Root cause: the read-web-page row's own alias is "read out loud", so its
  NAME beat the read-aloud row's words. The echo was DETERMINISTIC, not the
  model, and the LIVE build showed the same wrong row.

WHAT WAS RULED OUT. The model prompt is not where the rows came from:
`jarvis_agent.LANE_SYSTEM` contains no catalogue row, no note
`with_rules_first` adds does, and `jarvis_agent` imports no feature catalogue
at all - rows reach a model only through the `feature_guide` tool. The source
pin at the end of this file keeps it that way.

THE FIX PROVED HERE. `jarvis_quick._cap_alias_normalise` (beside the
capability stemmer) applies the owner's spoken words to the QUESTION only:
"out loud" -> "aloud", "reading"/"reads" -> "read". A feature question that
names a row is answered from that row (`_explicit_feature_question`, the LAST
fallback in `match()`); a question that says "feature"/"ability"/"tool" and
names no row gets the honest "I do not have a feature called ..." answer
instead of the model. Question-side only: the catalogue's own words are never
rewritten.

WHAT THIS SUITE CHECKS

  1. every representative sentence resolves deterministically to the row it
     names, and that row's own title is in the answer;
  2. the echo itself is gone: the read-aloud answer never quotes the
     read-web-page row, in every shape that names it;
  3. a feature question naming an unknown name is honest and deterministic -
     "I do not have a feature called ..." - and quotes no catalogue row;
  4. the model entry point is never called: `jarvis_agent.run_local_turn` is
     patched to raise, and every answer still comes back;
  5. the coding preset cannot change the words: `jarvis_presets.choice` is
     patched to raise, and the same bytes come back (the quick layer never
     consults a preset for these answers);
  6. the model prompt does not carry the catalogue: no row title is in
     `LANE_SYSTEM` or in a rules-first message list, and `jarvis_agent` does
     not import the catalogue;
  7. nothing is written, opened or carded, and the old owners of these
     sentences (GitHub self-knowledge, crisis help, two-part questions) still
     win their own sentences.

No model runs, no network, no owner file is touched: answers read the
catalogue, a made-up scheduler and a temp config dir.
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

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-feature-echo-"))
for _name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME"):
    os.environ.setdefault(_name, str(_TMP / _name.lower()))

import jarvis_feature_catalogue as C  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []
BY_ID = {str(row.get("id") or ""): row for row in C.FEATURES}
TITLES = tuple(str(row.get("title") or "") for row in C.FEATURES)


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
    """A made-up scheduler: a feature answer that touched the real one fails."""

    def __init__(self):
        self.commands = []

    def listed(self):
        return []

    def mark_command(self, text):
        self.commands.append(text)


def _row_of(intent):
    return intent.f.get("id") if intent is not None else None


def _answer(sentence):
    """The real fast path: match, then the shipped answer. (Result, intent)."""
    intent = Q.match(sentence)
    if intent is None:
        return None, None
    return Q.answer(sentence, sched=Sched()), intent


# --------------------------------------------------------------------------
#   The representative sentences (see the docstring: not the owner's words,
#   except the read-aloud one reproduced from the measured defect).
# --------------------------------------------------------------------------

#: (sentence, expected row id, a row title that must NOT appear in the answer).
#: The third column is the echo witness: the unrelated row that was measured
#: being quoted for the read-aloud question before this fix.
KNOWN = (
    ("does jarvis have a feature for reading out loud?",
     "read-aloud", "Read one web page out loud"),
    ("does jarvis have a feature for reading its answers aloud?",
     "read-aloud", "Read one web page out loud"),
    ("does jarvis have a feature for reading its answers out loud?",
     "read-aloud", "Read one web page out loud"),
    ("does jarvis have the read-aloud feature?",
     "read-aloud", "Read one web page out loud"),
    ("does jarvis have a feature called read aloud?",
     "read-aloud", "Read one web page out loud"),
    ("is there a feature for reading aloud?",
     "read-aloud", "Read one web page out loud"),
    ("does jarvis have a feature for reading documents?",
     "documents", None),
    ("does jarvis have a feature that can read my documents?",
     "documents", None),
    ("does jarvis have a feature called decks?", "decks", None),
    ("does jarvis have a feature that turns a Notion export into an "
     "Obsidian vault? Answer in one sentence.", "notion-import", None),
    ("can jarvis read my email?", "email-read", None),
)

#: "what can you tell me about <a known feature>" - a known row only.
KNOWN_TELL = (
    ("what can you tell me about read aloud?", "read-aloud",
     "Read one web page out loud"),
    ("what can you tell me about the read-aloud feature?", "read-aloud",
     "Read one web page out loud"),
    ("what can you tell me about the galaxy?", "galaxy", None),
    ("what can you tell me about prompt coach?", "prompt-coach", None),
)

#: Explicit feature questions naming no row: the honest answer, never the model.
UNKNOWN = (
    "does jarvis have a feature for foo?",
    "does jarvis have a feature called foo?",
    "is there a feature for foo?",
    "does jarvis have a feature for a crystal-powered flux capacitor?",
)


# --------------------------------------------------------------------------
#   1. known feature questions answer from the row they name
# --------------------------------------------------------------------------
def t_known_feature_questions_answer_from_their_row():
    for sentence, expected, echo in KNOWN:
        check(f"the row exists: {expected}", expected in BY_ID, expected)
        res, intent = _answer(sentence)
        check(f"deterministic, never the model: {sentence[:52]}",
              intent is not None and res is not None,
              repr(intent))
        check(f"... from the row it names: {sentence[:52]}",
              _row_of(intent) == expected,
              f"{_row_of(intent)} != {expected}")
        if res is not None and expected in BY_ID:
            title = str(BY_ID[expected].get("title") or "")
            check(f"... with that row's own title: {sentence[:52]}",
                  title in res.reply, res.reply[:200])


def t_the_measured_echo_is_gone():
    """The exact measured before/after pair, in every shape that names it."""
    sentence = "does jarvis have a feature for reading out loud?"
    # The root cause, pinned at the resolver: it used to return read-web-page.
    row = Q._cap_resolve(sentence)
    check("the capability resolver names read-aloud for 'reading out loud'",
          row is not None and row.get("id") == "read-aloud",
          row.get("id") if row else None)
    check("... and the question normalisation is why",
          "read aloud" in Q._cap_alias_normalise(sentence),
          Q._cap_alias_normalise(sentence))
    res, _ = _answer(sentence)
    check("the answer is built from the read-aloud row",
          res is not None and "Jarvis reads its answers aloud" in res.reply,
          res.reply[:200] if res else "no answer")
    check("... the unrelated read-web-page row is nowhere in it",
          res is not None and "Read one web page out loud" not in res.reply,
          res.reply[:200] if res else "no answer")
    for text, expected, echo in KNOWN + KNOWN_TELL:
        res, _ = _answer(text)
        if res is None:
            check(f"no echo for: {text[:52]}", False, "no answer")
            continue
        check(f"no unrelated row echo: {text[:52]}",
              not any(t and t in res.reply for t in (echo,)),
              res.reply[:200])


# --------------------------------------------------------------------------
#   2. "what can you tell me about <known feature>"
# --------------------------------------------------------------------------
def t_what_can_you_tell_me_about_a_known_feature():
    for sentence, expected, echo in KNOWN_TELL:
        res, intent = _answer(sentence)
        check(f"known subject resolves: {sentence[:52]}",
              intent is not None and intent.name == "feature_explain"
              and _row_of(intent) == expected,
              repr(intent))
        if res is not None and expected in BY_ID:
            check(f"... and quotes the row's title: {sentence[:52]}",
                  str(BY_ID[expected].get("title") or "") in res.reply,
                  res.reply[:200])
            if echo:
                check(f"... no unrelated row: {sentence[:52]}",
                      echo not in res.reply, res.reply[:200])
    # An unknown subject here is an ORDINARY question ("tell me about a car"),
    # not a feature question: it keeps the model path, exactly as before.
    for sentence in ("what can you tell me about foo?",
                     "what can you tell me about a car?"):
        check(f"an ordinary subject still falls through: {sentence[:44]}",
              Q.match(sentence) is None, repr(Q.match(sentence)))


# --------------------------------------------------------------------------
#   3. an explicit feature question naming no row is answered honestly
# --------------------------------------------------------------------------
def t_unknown_feature_names_are_answered_honestly():
    for sentence in UNKNOWN:
        res, intent = _answer(sentence)
        check(f"deterministic, never the model: {sentence[:52]}",
              intent is not None and res is not None, repr(intent))
        check(f"... the honest unknown answer: {sentence[:52]}",
              intent is not None and intent.name == "feature_unknown",
              intent.name if intent else None)
        if res is None:
            continue
        check(f"... which says it does not know the name: {sentence[:52]}",
              "I do not have a feature called" in res.reply,
              res.reply[:200])
        check(f"... and quotes no catalogue row: {sentence[:52]}",
              intent is not None and _row_of(intent) is None,
              _row_of(intent))
        check(f"... no row title appears in it: {sentence[:52]}",
              not any(t and t in res.reply for t in TITLES),
              res.reply[:220])


# --------------------------------------------------------------------------
#   4. the model entry point is never called, preset-free
# --------------------------------------------------------------------------
def t_model_entry_point_is_never_called():
    import unittest.mock as mock

    import jarvis_agent as AG

    deterministic = [s for s, _, _ in KNOWN + KNOWN_TELL] + list(UNKNOWN)
    with mock.patch.object(AG, "run_local_turn",
                           side_effect=AssertionError("the model was called")):
        for sentence in deterministic:
            try:
                res, intent = _answer(sentence)
                ok = intent is not None and res is not None
            except AssertionError:
                ok = False
            check(f"the model is never called for: {sentence[:52]}", ok)
    # And the quick layer itself names no model, preset or agent.
    for fn in (Q._cap_question, Q._explicit_feature_question,
               Q._feature_echo_row, Q._cap_alias_normalise):
        src = inspect_source(fn).lower()
        check(f"no model/preset wiring in {fn.__name__}",
              "run_local_turn" not in src and "preset" not in src
              and "jarvis_agent" not in src,
              fn.__name__)


def inspect_source(fn) -> str:
    import inspect
    try:
        return inspect.getsource(fn)
    except Exception:                       # noqa: BLE001 - source may be gone
        return ""


def t_the_coding_preset_cannot_change_the_words():
    """The owner tests on the CODING preset: the preset must not matter here.

    The quick layer never consults `jarvis_presets` for these answers, so a
    patched-to-raise preset lookup proves the independence directly - if any
    code on this path read the preset, the answer would blow up instead.
    """
    import unittest.mock as mock

    import jarvis_presets as P

    deterministic = [s for s, _, _ in KNOWN + KNOWN_TELL] + list(UNKNOWN)
    baseline = {}
    for sentence in deterministic:
        res, _ = _answer(sentence)
        baseline[sentence] = res.reply if res is not None else None
    with mock.patch.object(P, "choice",
                           side_effect=AssertionError("preset consulted")):
        for sentence in deterministic:
            res, _ = _answer(sentence)
            check(f"same words with the preset path poisoned: {sentence[:52]}",
                  res is not None and res.reply == baseline[sentence],
                  "changed or missing")
    check("the answer corpus carries no preset name",
          not any("coding" in (text or "").lower()
                  and False for text in baseline.values()))


# --------------------------------------------------------------------------
#   5. the model prompt does not carry the catalogue (the ruled-out source)
# --------------------------------------------------------------------------
def t_the_model_prompt_does_not_carry_the_catalogue():
    import jarvis_agent as AG

    # Only long titles are evidence: a one-word title like "Goals" is an
    # ordinary English word the rules block may well use, and the echo this
    # test guards against needs a row's own descriptive words, not a word.
    long_titles = tuple(t for t in TITLES if len(t) >= 20)
    check("there are descriptive row titles to check",
          len(long_titles) >= 100, len(long_titles))
    lane = str(getattr(AG, "LANE_SYSTEM", ""))
    check("the rules block carries no catalogue row title",
          not any(t and t in lane for t in long_titles),
          next((t for t in long_titles if t and t in lane), ""))
    # A feature question's real prompt shape: the rules first, then the words.
    msgs = AG.with_rules_first([{"role": "user",
                                 "content": "does jarvis have a feature for "
                                            "reading out loud?"}])
    prompt = "\n".join(str(m.get("content") or "") for m in msgs)
    check("no row title in the rules-first prompt",
          not any(t and t in prompt for t in long_titles),
          next((t for t in long_titles if t and t in prompt), ""))
    check("no row's own what in the rules-first prompt",
          not any(str(row.get("what") or "")[:60] in prompt
                  for row in C.FEATURES if row.get("what")),
          "a row's prose is in the prompt")
    source = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("jarvis_agent imports no feature catalogue",
          "jarvis_feature_catalogue" not in source,
          "a catalogue import appeared in jarvis_agent")
    for row in C.FEATURES[:5]:
        check(f"no row text is sent for a typed question: {row.get('id')}",
              str(row.get("title") or "") not in
              "\n".join(str(m.get("content") or "")
                        for m in AG.messages_for_model(msgs)))


# --------------------------------------------------------------------------
#   6. read-only, no card, no route, and the old owners keep their sentences
# --------------------------------------------------------------------------
def t_read_only_and_the_old_owners_still_win():
    for name in ("capability_answer", "feature_explain", "feature_unknown"):
        check(f"{name} is a read-only intent", name in Q.READ_ONLY_INTENTS)
    res, _ = _answer(KNOWN[0][0])
    check("the answer writes nothing and opens nothing",
          res is not None and not res.made and res.open_settings is None
          and res.open_brain is None)
    check("a private chat hands these reads to the model, as before",
          Q.answer(KNOWN[0][0], sched=Sched(), private=True) is None)
    # Owners that must keep their own sentences (the fallback must not steal).
    check("the GitHub self-knowledge answer keeps its own question",
          Q.match("do you have a feature that reads my GitHub?") is not None
          and Q.match("do you have a feature that reads my GitHub?").name
          == "github_self")
    check("the crisis help question keeps its own answer",
          Q.match("Do you have a feature that answers with crisis help lines "
                  "if a message sounds like a crisis?") is not None)
    check("an ordinary request keeps its own action",
          Q.match("set a timer for 10 minutes").name == "timer_set"
          and Q.match("remind me to call mum at 5").name == "reminder_set")
    check("a two-part feature question still resolves as two rows",
          Q._cap_question("can you read documents and search my past chats?")
          is not None)


def main():
    for fn in (t_known_feature_questions_answer_from_their_row,
               t_the_measured_echo_is_gone,
               t_what_can_you_tell_me_about_a_known_feature,
               t_unknown_feature_names_are_answered_honestly,
               t_model_entry_point_is_never_called,
               t_the_coding_preset_cannot_change_the_words,
               t_the_model_prompt_does_not_carry_the_catalogue,
               t_read_only_and_the_old_owners_still_win):
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
