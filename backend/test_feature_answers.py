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

import importlib.util
import os
import re
import subprocess
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
    check("'what can you do?' is the feature OVERVIEW, not only sayable examples",
          got is not None and got.intent == "feature_overview",
          got.intent if got else "the model")
    check("... naming the list's groups and pointing at Everything Jarvis can do",
          got is not None and "features in" in (got.reply or "")
          and "groups" in (got.reply or "")
          and "Everything Jarvis can do" in (got.reply or ""),
          (got.reply or "")[:220])


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


def t_ruling_c_the_protection_row_covers_both_its_settings_ids():
    """Ruling (c), 2026-10-31: both ids in `covers`, without a wrong label.

    The section id `protection` is a fourth, real kind of cover id (the checker
    reads the registry's own SECTIONS with `ast`); the menu id
    `settings.protection` is the place it opens. The row must not become
    Settings-Only, because the owner's 2026-10-22 decision reserves that label
    for accounts and restore-backup exactly.
    """
    row = next(r for r in SOURCE if r["id"] == "protected-items")
    check("the protection feature row covers both its section and menu id",
          {"protection", "settings.protection"} <= set(row.get("covers") or []),
          row.get("covers"))
    check("... and still names the lesson that teaches it",
          "protected-items" in (row.get("covers") or []), row.get("covers"))
    spec = importlib.util.spec_from_file_location(
        "check_feature_list_for_answers", REPO / "tools" / "check_feature_list.py")
    CL = importlib.util.module_from_spec(spec)
    sys.modules["check_feature_list_for_answers"] = CL
    spec.loader.exec_module(CL)
    check("check_feature_list knows settings-registry sections as a cover kind",
          "protection" in CL.settings_section_ids())
    check("... and the list passes it", CL.problems() == [], CL.problems()[:3])
    for tool in ("check_feature_list.py", "check_feature_controls.py"):
        run = subprocess.run([sys.executable, "-B", str(REPO / "tools" / tool)],
                             cwd=str(REPO), capture_output=True, text=True,
                             timeout=180)
        check(f"tools/{tool} exits 0 with both ids in covers",
              run.returncode == 0, (run.stdout + run.stderr)[-700:])
    contract = __import__("json").loads(
        (REPO / "contract" / "feature-controls.json").read_text(encoding="utf-8"))
    check("Settings-Only is still exactly accounts + backup",
          {x["feature"] for x in contract.get("settings_only") or []}
          == {"accounts", "backup"},
          contract.get("settings_only"))
    prow = next(f for f in contract["features"] if f["id"] == "protected-items")
    check("... and the protection row is still Command-Only",
          prow["label"] == FG.LABEL_COMMAND_ONLY, prow["label"])
    check("... never Settings-Only", prow["label"] != FG.LABEL_SETTINGS_ONLY)
    matrix = next(r for r in FG.control_matrix() if r["id"] == "protected-items")
    check("the guide still derives Command-Only for the protection row",
          matrix["label"] == FG.LABEL_COMMAND_ONLY
          and matrix["status"] == "not-a-setting",
          (matrix["label"], matrix["status"]))
    feat = next(r for r in FG.features() if r["id"] == "protected-items")
    check("... with the owned section not folded into its Settings sections",
          FG._sections_in(feat) == [], FG._sections_in(feat))


def t_ruling_d_owner_words_map_to_catalogue_rows():
    """Ruling (d), 2026-10-31: synonyms map; a capability is never denied by
    the list using a different word."""
    cases = {
        "obsidian": {"notes-write", "notes-editor"},
        "vault": {"notes-write", "notes-editor"},
        "schedule": {"calendar", "jarvis-calendar"},
        "events": {"calendar", "jarvis-calendar"},
        "appointments": {"calendar", "jarvis-calendar"},
        "block": {"protected-items"},
        "exclude": {"protected-items"},
        "permissions": {"protected-items"},
        "send file": {"documents"},
        "download file": {"documents"},
    }
    for words, expected in cases.items():
        out = FG.capabilities(words)
        named = {f["id"] for f in out.get("features", [])}
        check(f"ruling (d): {words!r} maps to the rows it means",
              out.get("kind") != "unknown" and bool(named & expected),
              (out.get("kind"), sorted(named)))
        check(f"... and {words!r} is not falsely denied",
              FG.CAPABILITY_NOT_A_FEATURE not in out.get("words", ""),
              out.get("words", "")[:220])
        check(f"... and points at the whole feature list",
              "Everything Jarvis can do" in out.get("words", ""))
    # Through the real fast path: the same mapping must hold, with no model.
    got = ask("what can you do with obsidian?")
    check("the fast path maps 'obsidian' to the notes rows",
          got is not None and got.intent == "feature_capabilities"
          and "Browse and edit your notes" in (got.reply or ""),
          got.reply[:200] if got else "the model")
    got = ask("what can you do with appointments?")
    check("the fast path maps 'appointments' to the calendar rows",
          got is not None and got.intent == "feature_capabilities"
          and "Read your own calendar" in (got.reply or ""),
          got.reply[:200] if got else "the model")
    got = ask("what can you do with permissions?")
    check("the fast path maps 'permissions' to Protected from Jarvis",
          got is not None and got.intent == "feature_capabilities"
          and "Protected from Jarvis" in (got.reply or ""),
          got.reply[:200] if got else "the model")


def t_ruling_d_hard_sentence_only_on_zero_overlap_or_unsupported():
    """Ruling (d): the hard denial is for no overlap or a known unsupported
    topic only; any real catalogue overlap gets words and the list pointer."""
    zero = FG.capabilities("chainsaw")
    check("zero catalogue overlap keeps the honest denial",
          zero.get("kind") == "unknown"
          and FG.CAPABILITY_NOT_A_FEATURE in zero.get("words", ""),
          zero.get("words", "")[:200])
    check("... and it still points at the whole list",
          "Everything Jarvis can do" in zero.get("words", ""))
    for phrase in ("system permissions", "notification history",
                   "calendar invitations"):
        out = FG.capabilities(phrase)
        check(f"the known unsupported topic {phrase!r} is denied plainly",
              out.get("kind") == "unknown"
              and FG.CAPABILITY_NOT_A_FEATURE in out.get("words", ""),
              out.get("words", "")[:220])
        got = ask(f"what can you do with {phrase}?")
        check(f"... the fast path says it too: {phrase!r}",
              got is not None and got.intent == "feature_capabilities"
              and FG.CAPABILITY_NOT_A_FEATURE in (got.reply or ""),
              got.reply[:200] if got else "the model")
    partial = FG.capabilities("password")
    check("a partial catalogue overlap is answered, not denied",
          partial.get("kind") != "unknown"
          and FG.CAPABILITY_NOT_A_FEATURE not in partial.get("words", ""),
          (partial.get("kind"), partial.get("words", "")[:220]))
    check("... with the whole-list pointer",
          "Everything Jarvis can do" in partial.get("words", ""))
    check("'permissions' maps to protection while 'system permissions' stays "
          "unsupported",
          any(f["id"] == "protected-items"
              for f in FG.capabilities("permissions").get("features", []))
          and FG.capabilities("system permissions").get("kind") == "unknown")


def t_settings_help_keeps_its_precedence_over_the_catalogue_path():
    """Regression: the settings-help family must not be captured by the list.

    CI on the pushed head (2026-10-31) failed `test_settings_help.py` on exactly
    "what can I change in settings": the new catalogue capability path claimed
    it because `settings` was one of the area nouns. The settings-help answer
    owns that phrase (and the rest of its family), so the catalogue matcher no
    longer names `settings` as an area; a real capability question is still
    answered from the list.
    """
    got = ask("what can I change in settings")
    check("'what can I change in settings' is still the settings-help answer",
          got is not None and got.intent == "settings_help",
          got.intent if got else "the model")
    check("... and it says something, from the real switches",
          got is not None and bool((got.reply or "").strip())
          and "undo" in (got.reply or "").lower(), (got.reply or "")[:200])
    for phrase in ("what settings can I change", "which settings can I change"):
        got = ask(phrase)
        check(f"the settings-help phrase {phrase!r} is still settings_help",
              got is not None and got.intent == "settings_help",
              got.intent if got else "the model")
    # A nearby settings ITEM keeps its own answer (the feature guide's), not a
    # capability one and not the model.
    got = ask("how do I change the appearance?")
    check("a nearby settings-item phrasing keeps its own answer",
          got is not None and got.intent == "feature_explain",
          got.intent if got else "the model")
    # The catalogue path is untouched for non-settings questions.
    got = ask("what can you do with the calendar?")
    check("... while a real capability question is still answered from the list",
          got is not None and got.intent == "feature_capabilities",
          got.intent if got else "the model")


def t_discussion_shapes_quote_the_rows_own_fields():
    """The pass-11 audit's exact limits failures, plus asks/app/why/state."""
    def reply_of(phrase):
        got = ask(phrase)
        return got, (got.reply if got is not None else "")

    cases = {
        "what are the limits of Galaxy": ("feature_limits", "Galaxy",
                                          "Drawn from the same memory lists"),
        "what are the limits of Protected from Jarvis":
            ("feature_limits", "Protected from Jarvis", "executable name"),
        "what are the limits of lights, plugs and fans":
            ("feature_limits", "Lights, plugs and fans", "Locks, doors"),
        "what are the limits of Jarvis Calendar":
            ("feature_limits", "Jarvis Calendar", "Local only: no Google sync"),
    }
    for phrase, (want_intent, title, own_words) in cases.items():
        got, reply = reply_of(phrase)
        check(f"{phrase!r} is answered from the list", got is not None
              and got.intent == want_intent, got.intent if got else "the model")
        check(f"... quoting {title!r}'s own title", title in reply, reply[:260])
        check(f"... and its own limit words {own_words!r}", own_words in reply,
              reply[:300])
        check("... and not a model's invented limit",
              got is not None, reply[:200])
    # The audit's specific wrong answer about Jarvis Calendar (the OTHER
    # calendar row): the local calendar's own Where must be the one quoted.
    _got, reply = reply_of("what are the limits of Jarvis Calendar")
    check("... and the local calendar is not called the read-only iCal row",
          "Settings, Accounts" not in reply, reply[:260])
    got, reply = reply_of("does protected from jarvis ask first?")
    check("'does X ask first?' quotes the row's own asks field",
          got is not None and got.intent == "feature_asks"
          and "raises one card" in reply, reply[:260])
    got, reply = reply_of("which app can use picture-in-picture?")
    check("'which app can use X?' quotes the row's own surface",
          got is not None and got.intent == "feature_app"
          and "phone only" in reply, reply[:260])
    got, reply = reply_of("why would I use galaxy?")
    check("'why would I use X?' quotes the row's own what/where/limit",
          got is not None and got.intent == "feature_why"
          and "A map of what Jarvis knows" in reply
          and "Drawn from the same memory lists" in reply, reply[:320])
    got, reply = reply_of("is quiet hours on or off?")
    check("'is quiet hours on or off?' answers from the Notifications row",
          got is not None and got.intent == "feature_state"
          and "Notifications" in reply, reply[:260])


def t_every_row_can_be_discussed_by_two_shapes():
    """Every catalogue row resolves through tell-me and what-does-it-do."""
    rows = __import__("json").loads(
        (REPO / "features" / "features.json").read_text(encoding="utf-8"))
    bad_match, bad_fields = [], []
    for row in rows:
        fid, title = row["id"], row["title"]
        for phrase in (f"tell me about {title}", f"what does {title} do"):
            got = Q.match(phrase, NOW)
            if (got is None or got.name != "feature_explain"
                    or got.f.get("id") != fid):
                bad_match.append((fid, phrase, got.name if got else "the model",
                                  got.f.get("id") if got else ""))
        out = FG.explain(title)
        words = str(out.get("words") or "")
        fields = [str(row.get(k) or "").strip() for k in
                  ("what", "where", "asks", "limit")]
        quoted = [f for f in fields if f and f in words]
        if row["title"] not in words or len(quoted) < 2:
            bad_fields.append((fid, len(quoted)))
    check(f"all {len(rows)} rows resolve through BOTH tell-me and what-does-it-do",
          not bad_match, bad_match[:8])
    check(f"all {len(rows)} rows quote at least two of their own fields",
          not bad_fields, bad_fields[:8])


def t_group_overview_answers_by_group_and_points_at_the_list():
    got = ask("what can you do?")
    reply = got.reply if got is not None else ""
    check("'what can you do?' is the group overview",
          got is not None and got.intent == "feature_overview",
          got.intent if got else "the model")
    check("... naming the group counts", "features in" in reply
          and "groups" in reply and "Talking" in reply, reply[:260])
    check("... and pointing at Everything Jarvis can do",
          "Everything Jarvis can do" in reply, reply[:260])
    got = ask("list what you can do")
    check("'list what you can do' is the same overview",
          got is not None and got.intent == "feature_overview"
          and "groups" in (got.reply or ""), got.intent if got else "the model")
    got = ask("what can you do about safety")
    reply = got.reply if got is not None else ""
    check("a group word answers BY GROUP ('safety')",
          got is not None and got.intent == "feature_overview"
          and "The Safety group has" in reply, reply[:260])
    check("... capped, with a count and the whole-list pointer",
          "and 6 more" in reply or "and " in reply
          and "Everything Jarvis can do" in reply, reply[:300])


def t_comparison_quotes_both_rows_side_by_side():
    got = ask("what's the difference between reminders and alarms?")
    reply = got.reply if got is not None else ""
    check("'reminders vs alarms' is the fixed comparison",
          got is not None and got.intent == "feature_difference",
          got.intent if got else "the model")
    check("... saying they are the SAME feature row, never inventing a difference",
          "same feature row" in reply
          and "Timers, alarms, reminders and lists" in reply, reply[:320])
    got = ask("what's the difference between Galaxy and the wiki Jarvis builds?")
    reply = got.reply if got is not None else ""
    check("two real rows are quoted side by side",
          got is not None and got.intent == "feature_difference"
          and "Galaxy" in reply and "The wiki Jarvis builds" in reply,
          reply[:360])
    check("... each with its own limit",
          "Drawn from the same memory lists" in reply, reply[:500])
    got = ask("what's the difference between Galaxy and a bicycle?")
    reply = got.reply if got is not None else ""
    check("one real row + one non-row is honest about the other",
          got is not None and got.intent == "feature_difference"
          and "has no" in reply and "bicycle" in reply, reply[:300])


def t_discussion_ordering_does_not_steal_working_quick_answers():
    """The two measured ordering bugs: scheduler status must keep its lane."""
    cases = {
        "what's coming up": "next_up",
        "what's my next reminder?": "next_up",
        "what timers are running?": "timer_status",
    }
    for phrase, want in cases.items():
        got = Q.match(phrase, NOW)
        check(f"{phrase!r} keeps its own quick answer ({want})",
              got is not None and got.name == want,
              got.name if got else "the model")
    got = Q.match("what jobs are running?", NOW)
    check("the feature matcher does not claim 'what jobs are running'",
          got is None or not got.name.startswith("feature_"),
          got.name if got else "the model")
    got = Q.match("how do timers work", NOW)
    check("'how do timers work' explains the timers row, not a model denial",
          got is not None and got.name == "feature_explain"
          and got.f.get("id") == "coming-up",
          (got.name, got.f) if got else "the model")
    got = Q.match("what can I change in settings", NOW)
    check("the settings-help phrase still keeps its own lane",
          got is not None and got.name == "settings_help",
          got.name if got else "the model")


def t_discussion_shapes_do_not_over_capture():
    """Ordinary conversation about non-features still reaches the model."""
    for phrase in ("what's the difference between a car and a bike?",
                   "what are the limits of a car?",
                   "does my oven ask first?",
                   "which app can use my printer?",
                   "why would I use a bicycle?"):
        got = ask(phrase)
        check(f"{phrase!r} is still the model's", got is None,
              (got.intent if got else "")[:120])


def t_settings_shaped_features_answer_from_their_own_rows():
    """The audit's settings-ish names resolve and quote the catalogue row."""
    cases = {
        "tell me about quiet hours": ("notifications", "Notifications"),
        "tell me about thinking level": ("attention-budget",
                                         "How much Jarvis may interrupt you"),
        "tell me about memories": ("memory-saved", "Facts Jarvis saved by itself"),
        "tell me about personality presets": ("manner", "How Jarvis talks"),
    }
    for phrase, (fid, title) in cases.items():
        got = ask(phrase)
        target = phrase.replace("tell me about ", "")
        resolved = FG.explain(target).get("feature", {}).get("id")
        check(f"{phrase!r} discusses the catalogue row",
              got is not None and got.intent == "feature_explain"
              and resolved == fid,
              (got.intent if got else "the model", resolved))
        check(f"... in the row's own words ({title!r})",
              got is not None and title in (got.reply or ""),
              (got.reply or "")[:240])
    # The surface field is stated when it is asked about (the audit's
    # PC-only/phone-only confusion).
    got = ask("which app can use picture-in-picture?")
    check("a phone-only row says it is on the phone only",
          got is not None and got.intent == "feature_app"
          and "phone only" in (got.reply or ""), (got.reply or "")[:200])
    got = ask("which app can use what jarvis knows about you?")
    check("a desktop-only row says it is on the PC only",
          got is not None and got.intent == "feature_app"
          and "PC only" in (got.reply or ""), (got.reply or "")[:200])


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
