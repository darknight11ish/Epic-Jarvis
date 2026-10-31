"""test_feature_answers.py - Jarvis answers "what can you do with X?" itself.

    python backend/test_feature_answers.py

THE FIELD-TEST GAP (2026-10-31, pass 9, PART B). The owner asked Jarvis about
its own features through the live HUD's own chat box, and only two of eight
answers were accurate. The rest were the model's prose: it claimed calendar
invitations and availability that do not exist, said it was unaware of its own
smart features, invented "add new entries" for notes, invented a filesystem
"system permissions" workaround for protecting a folder, and offered to read a
phone's "notification history" for the next reminder.

THE FIX PROVED HERE. `jarvis_quick` now answers those questions from
`jarvis_feature_guide`'s own rows, with no model, and the answers always say
plainly when something is not one of Jarvis's features. This suite drives the
REAL fast path (`jarvis_quick.answer`) for the eight questions, and checks:

  a. each answer comes from the feature list - the matching rows' own title,
     where, asks and limit words are in it, and every feature it names is a
     row in `features/features.json`;
  b. no answer CLAIMS a capability that is not in the list (the field test's
     five forbidden claims, negation-aware: "no invitations" is honest, a bare
     "invitations" is not);
  c. a question that is not about Jarvis's features still reaches the model
     (None from the fast path) - or keeps the older intent it already had;
  d. the two new intents are registered where `jarvis_quick` looks answers up.

No model runs, no network, no owner file is touched: the answers read the
catalogue and a made-up schedule only.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-feature-answers-"))
for _name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME"):
    os.environ.setdefault(_name, str(_TMP / _name.lower()))

import jarvis_feature_guide as FG  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []
NOW = time.mktime(time.strptime("2026-10-31 09:05:00", "%Y-%m-%d %H:%M:%S"))

SOURCE = __import__("json").loads(
    (REPO / "features" / "features.json").read_text(encoding="utf-8"))
SOURCE_BY_ID = {row["id"]: row for row in SOURCE}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Sched:
    """A made-up scheduler: the answers read this list, never the owner's."""

    def __init__(self, jobs=None):
        self.jobs = list(jobs or [])

    def listed(self):
        return list(self.jobs)

    def add_todo(self, text, source="quick", list_name=None):
        return {"id": "made-up-item", "text": text, "already": False}

    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def forget_set(self, conversation):
        pass


def ask(text, jobs=None):
    """The fast path's answer, through the same function /api/chat calls."""
    return Q.answer(text, sched=Sched(jobs), now=NOW,
                    messages=[{"role": "user", "content": text}])


def row_of(feature_id: str) -> dict:
    """The catalogue row, from the same JSON the Features pages are drawn from."""
    return SOURCE_BY_ID[feature_id]


def says_row(answer: str, feature_id: str, fields=("title", "where", "limit")) -> bool:
    """Do the row's own words appear in the answer, unedited?"""
    row = row_of(feature_id)
    for key in fields:
        value = str(row.get(key) or "").strip()
        if value and value not in answer:
            return False
    return True


#: The field test's own five invented claims (PART B). A bare mention is an
#: over-claim; a NEGATED one ("no invitations") is the list's honest limit and
#: is allowed. See `claims`.
FORBIDDEN = ("invitations", "availability", "add new entries",
             "notification history", "system permissions")
_NEGATIONS = ("no ", "not ", "never ", "cannot ", "can't ", "none ", "without ",
              "isn't ", "doesn't ", "don't ", "has no ", "have no ")


def claims(text: str, word: str) -> bool:
    """True when `word` appears WITHOUT a negation just before it."""
    low = text.lower()
    start = 0
    while True:
        at = low.find(word, start)
        if at < 0:
            return False
        window = low[max(0, at - 30):at]
        if not any(neg in window for neg in _NEGATIONS):
            return True
        start = at + len(word)


def t_the_eight_field_test_questions_are_answered_without_the_model():
    """All eight answers are the fast path's own - none reaches the model."""
    jobs = [{"kind": "reminder", "id": "r1", "text": "dentist",
             "when": "at 15:00 today", "due": NOW + 3600},
            {"kind": "timer", "id": "t1", "text": "tea",
             "when": "in 5 minutes", "due": NOW + 300}]
    questions = [
        ("Q8", "what is the time?", "time_now"),
        ("Q1", "what can you do with the calendar?", "feature_capabilities"),
        ("Q2", "can you add something to my calendar?", "feature_capabilities"),
        ("Q3", "what are the smart features of the calendar?", "feature_capabilities"),
        ("Q4", "what can you edit in my notes?", "feature_capabilities"),
        ("Q5", "can I protect a folder from you?", "feature_capabilities"),
        ("Q6", "what is picture-in-picture?", "feature_explain"),
        ("Q7", "what's my next reminder?", "next_up"),
    ]
    answers = {}
    for tag, text, want in questions:
        got = ask(text, jobs)
        check(f"{tag} '{text}' is answered with no model", got is not None,
              "the fast path returned None (the model would answer)")
        if got is None:
            continue
        answers[tag] = (text, got)
        check(f"{tag} ... by the expected fixed path", got.intent == want,
              f"got {got.intent}")
        check(f"{tag} ... with words, not an empty answer", bool((got.reply or "").strip()))
    return answers


def t_the_calendar_answers_are_the_lists_own_rows():
    """"what can you do/smart features/add something to the calendar" - rows."""
    for tag in ("Q1", "Q3"):
        got = ask({"Q1": "what can you do with the calendar?",
                   "Q3": "what are the smart features of the calendar?"}[tag])
        check(f"{tag} answers from the fixed path", got is not None
              and got.intent == "feature_capabilities",
              got.intent if got else "the model")
        if got is None:
            continue
        reply = got.reply or ""
        for feature_id in ("calendar", "jarvis-calendar"):
            check(f"{tag} names the list's own '{feature_id}' row",
                  says_row(reply, feature_id, ("title", "where", "asks", "limit")),
                  reply[:400])
        check(f"{tag} names the HUD card and the three views",
              "Calendar card in the HUD (month, week and day views)" in reply, reply[:400])
        check(f"{tag} names the Add form's own rule",
              "Adding, changing or deleting an event is that card" in reply, reply[:400])
    # The ADDING question is the adding row only: the read-only iCal row has
    # nothing to do with adding, and the old answer listed it because "address"
    # contained "add".
    got = ask("can you add something to my calendar?")
    check("Q2 answers from the fixed path", got is not None
          and got.intent == "feature_capabilities", got.intent if got else "the model")
    if got is not None:
        reply = got.reply or ""
        check("Q2 names Jarvis Calendar's own adding rule",
              says_row(reply, "jarvis-calendar") and
              "Adding, changing or deleting an event is that card" in reply, reply[:500])
        check("... and not the read-only iCal row, which cannot add anything",
              "Read your own calendar" not in reply, reply[:300])


def t_the_notes_answer_is_the_notes_editor_row():
    """"what can you edit in my notes?" - the notes editor row, not a refusal."""
    got = ask("what can you edit in my notes?")
    check("the notes question is the fixed answer", got is not None
          and got.intent == "feature_capabilities", got.intent if got else "the model")
    if got is None:
        return
    reply = got.reply or ""
    check("... it is NOT the old 'not one of my features' answer",
          "That is not one of my features on this PC." not in reply, reply[:400])
    check("... and it is the list's own notes-editor row",
          says_row(reply, "notes-editor", ("title", "where", "asks", "limit")),
          reply[:500])
    check("... with its own limits named, not invented",
          "does not create, delete or rename" in reply, reply[:500])
    check("... and nothing from a different note feature",
          "Write a note for you" not in reply, reply[:300])


def t_the_protection_answer_is_the_protected_row_and_invents_nothing():
    """"can I protect a folder from you?" - the Protected from Jarvis row."""
    got = ask("can I protect a folder from you?")
    check("the protection question is the fixed answer", got is not None
          and got.intent == "feature_capabilities", got.intent if got else "the model")
    if got is None:
        return
    reply = got.reply or ""
    check("... it is NOT the old 'not one of my features' answer",
          "That is not one of my features on this PC." not in reply, reply[:400])
    check("... and it is the list's own protected-items row",
          says_row(reply, "protected-items", ("title", "where", "asks", "limit")),
          reply[:500])
    check("... naming both modes and the executable-name match",
          "blocked" in reply.lower() and "read-only" in reply.lower()
          and "executable name" in reply, reply[:500])
    for invented in ("system permissions", "permission", "filesystem", "move that folder"):
        check(f"... and never offers the invented {invented!r}",
              invented not in reply.lower(), reply[:400])


def t_no_answer_claims_a_capability_the_list_does_not_have():
    """The field test's five over-claims, checked word for word (negation-aware)."""
    probes = [
        ("what can you do with the calendar?", None),
        ("can you add something to my calendar?", None),
        ("what are the smart features of the calendar?", None),
        ("what can you edit in my notes?", None),
        ("can I protect a folder from you?", None),
        ("what's my next reminder?", [{"kind": "reminder", "id": "r1",
                                       "text": "dentist", "when": "at 15:00 today"}]),
        ("what's my next reminder?", []),
    ]
    for text, jobs in probes:
        got = ask(text, jobs)
        check(f"'{text}' answers without the model", got is not None)
        if got is None:
            continue
        reply = got.reply or ""
        for word in FORBIDDEN:
            check(f"... it does not claim {word!r}", not claims(reply, word),
                  f"claimed {word!r} in: {reply[:500]}")
        check("... it never says it is unaware of its own features",
              "currently unaware" not in reply.lower(), reply[:300])


def t_the_next_reminder_answer_comes_from_the_schedule():
    """"what's my next reminder?" - the scheduler's list, never a phone feature."""
    jobs = [{"kind": "reminder", "id": "r1", "text": "dentist",
             "when": "at 15:00 today", "due": NOW + 3600},
            {"kind": "timer", "id": "t1", "text": "tea",
             "when": "in 5 minutes", "due": NOW + 300}]
    got = ask("what's my next reminder?", jobs)
    check("the next reminder is answered from the schedule", got is not None
          and got.intent == "next_up", got.intent if got else "the model")
    if got is not None:
        reply = got.reply or ""
        check("... naming the reminder and its time", "dentist" in reply
              and "15:00" in reply, reply[:300])
        check("... and never a 'notification history'", "notification history"
              not in reply.lower(), reply[:300])
    empty = ask("what's my next reminder?", [])
    check("with no reminder set it says so plainly", empty is not None
          and empty.intent == "next_up"
          and "No reminder is set on this PC." in (empty.reply or ""),
          empty.reply if empty else "the model")
    check("... and still names no phone feature", empty is not None
          and "notification history" not in (empty.reply or "").lower())
    # The generic shape reads the same list.
    generic = ask("what's next on my schedule?", jobs)
    check("'what's next on my schedule?' reads the same list", generic is not None
          and generic.intent == "next_up", generic.intent if generic else "the model")
    check("... and names the next item", generic is not None
          and ("tea" in (generic.reply or "") or "dentist" in (generic.reply or "")),
          generic.reply if generic else None)


def t_one_feature_names_are_answered_from_that_row():
    """"what can you do with the prompt coach?" - one row's own facts."""
    got = ask("what can you do with the prompt coach?")
    check("a single named feature is the fixed answer", got is not None
          and got.intent == "feature_capabilities", got.intent if got else "the model")
    if got is None:
        return
    reply = got.reply or ""
    check("... with that row's own title, where, asks and limit",
          says_row(reply, "prompt-coach", ("title", "where", "asks", "limit")),
          reply[:400])
    check("... and never another feature's facts",
          "calendar" not in reply.lower(), reply[:300])


def t_an_ambiguous_area_asks_which_one_never_guesses():
    """"what can you do with memory?" - many rows: name them, ask which."""
    got = ask("what can you do with memory?")
    check("an ambiguous area is the fixed answer", got is not None
          and got.intent == "feature_capabilities", got.intent if got else "the model")
    if got is None:
        return
    reply = got.reply or ""
    check("... it says there is more than one feature",
          "more than one feature" in reply, reply[:400])
    check("... it names the matching feature names in one list",
          all(name in reply for name in ("The Memory tab", "Facts Jarvis saved by itself")),
          reply[:400])
    check("... and asks which one, never inventing one",
          "Say which one" in reply, reply[:400])


def t_every_feature_row_in_the_list_is_answerable():
    """No row can silently be non-answerable: each answers to its own name.

    The 2026-10-31 rows made this worth pinning: a row that exists in
    `features/features.json` but that `capabilities()` cannot reach would be a
    feature the chat still cannot talk about. Titles must resolve to that one
    row (its own words in the answer); ids must at least be named - either as
    the row itself or in an honest "more than one feature" candidate list.
    """
    rows = __import__("json").loads(
        (REPO / "features" / "features.json").read_text(encoding="utf-8"))
    catalogue = {r["id"]: r for r in FG.features()}
    check("the generated catalogue has every row the JSON has",
          set(catalogue) == {r["id"] for r in rows}, len(catalogue))
    bad_title, bad_id = [], []
    for row in rows:
        fid = row["id"]
        if fid not in catalogue:
            continue
        by_title = FG.capabilities(row["title"])
        named = [f["id"] for f in by_title.get("features", [])]
        if (by_title.get("kind") not in ("rows", "feature") or fid not in named
                or row["title"] not in by_title.get("words", "")):
            bad_title.append((fid, by_title.get("kind"), named[:3]))
        by_id = FG.capabilities(fid)
        named = ([f["id"] for f in by_id.get("features", [])]
                 + [c["id"] for c in by_id.get("candidates", [])])
        if by_id.get("kind") == "unknown" or fid not in named:
            bad_id.append((fid, by_id.get("kind"), named[:3]))
    check(f"all {len(rows)} rows answer to their own TITLE with their own words",
          not bad_title, bad_title[:10])
    check(f"all {len(rows)} rows are reachable by their ID (or listed as a candidate)",
          not bad_id, bad_id[:10])
    for fid in ("notes-editor", "protected-items"):
        got = FG.capabilities(fid)
        check(f"the new 2026-10-31 row {fid!r} is answerable",
              got.get("kind") != "unknown"
              and fid in [f["id"] for f in got.get("features", [])], got.get("kind"))


def t_a_non_feature_question_still_reaches_the_model():
    """No over-capture: the answers are for feature questions only."""
    for text in ("what's the capital of France?",
                 "how do I change a tyre?",
                 "can I protect a folder with a password?"):
        got = ask(text)
        check(f"'{text}' is still the model's", got is None,
              got.reply[:120] if got is not None else "")
    # The older, REAL paths keep their own sentences too.
    got = ask("can you connect my calendar?")
    check("'can you connect my calendar?' keeps the connect path",
          got is not None and got.intent == "connect_account",
          got.intent if got else "the model")
    got = ask("can you add milk to my shopping list?")
    check("'add milk to my shopping list' keeps the to-do path",
          got is not None and got.intent == "todo_add",
          got.intent if got else "the model")
    got = ask("what can you do?")
    check("'what can you do?' keeps the things-you-can-say answer",
          got is not None and got.intent == "sayable_help",
          got.intent if got else "the model")


def t_the_quick_paths_are_registered_where_answers_are_looked_up():
    """The two intents are in the fast path's own read-only registry."""
    check("feature_capabilities is a registered read-only answer",
          "feature_capabilities" in Q.READ_ONLY_INTENTS)
    check("next_up is a registered read-only answer",
          "next_up" in Q.READ_ONLY_INTENTS)
    got = Q.match("what can you do with the calendar?", NOW)
    check("the matcher returns the registered intent",
          got is not None and got.name == "feature_capabilities",
          got.name if got else "the model")
    got = Q.match("what's my next reminder?", NOW)
    check("the reminder matcher returns the registered intent",
          got is not None and got.name == "next_up",
          got.name if got else "the model")
    # A private chat hands read-only intents to the model by design; being in
    # READ_ONLY_INTENTS is what keeps that behaviour.
    check("... so a private chat does not change state with it",
          all(name in Q.READ_ONLY_INTENTS
              for name in ("feature_capabilities", "next_up")))


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL  {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
