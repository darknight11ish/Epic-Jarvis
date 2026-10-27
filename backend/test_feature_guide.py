"""test_feature_guide.py - "what is this feature?", "is it on?", "turn it on".

    python backend/test_feature_guide.py

THE FIELD-TEST GAP (2026-10-19/20). The owner asked whether Jarvis could
explain the program's features and switch them by chat. Asking "how do I turn
on the prompt coach?" got a thin model answer that never said what the coach
does or where it lives; asking "is it on right now?" got "I don't know its
current state directly". The feature list existed all along -
`features/features.json`, the exact rows both apps' Features pages draw - but
no chat path read it.

WHAT THIS PROVES
  1. THE FACTS ARE THE LIST'S OWN. Every one of the 140 rows is found by its id,
     and the answer's facts equal the JSON word for word (groups, what, where,
     asks, limit, surface, covers) - nothing is reworded into the facts, and
     the generated copy the PC carries is current (`tools/
     gen_feature_guide_catalogue.py --check`).
  2. A FEATURE'S SWITCH IS READ, NOT GUESSED. Every BoolSetting in
     jarvis_settings_registry has a state reader here (a switch added later
     fails this suite until it gets one); the reader's True/False is what the
     answer says; a reader that raises, or a module that cannot answer, makes
     the answer SAY it could not read it - it never says "on"/"off" from a
     nothing. A feature with no switch says exactly that.
  3. AN UNKNOWN FEATURE IS SAID PLAINLY. "Jarvis, what is the turbo feature"
     answers "I do not have a feature called ..." and offers the real groups.
     It never matches some other feature by a loose word.
  4. THE FIXED PHRASES DO NOT HIJACK OTHER QUESTIONS. "what is the weather",
     "is the oven on", "how do I turn on the oven", "what is my name" and the
     like still fall through to the model (or keep the intent they had), proven
     phrase by phrase. Since the 2026-10-20 hardening (Gemini §11.8.3) a
     feature phrase also needs an EXACT catalogue name, or explicit Jarvis
     context ("Jarvis", "here", "my settings"): "what is a focus session in
     psychology?" and "how do I turn on dark mode in Chrome?" stay the
     model's, and "is my oven on?" finds no feature.
  5. SWITCHING BY CHAT STILL USES THE REAL SETTER. A fixed phrase that changes
     a feature's switch goes through the SAME BoolSetting.set the settings
     phrases and the model's change_setting tool use, so the setting's own card
     rule is unchanged; the reply is the setter's own outcome - never a "Done"
     when it did not do it - and a feature naming SEVERAL switches changes
     nothing and says which ones.
  6. THE MODEL TOOL IS READ-ONLY AND NO CARD. `feature_guide` exists, is under
     the gate's own read-only `skill_list` action (tier auto, no card), is in
     the short-list group rules, within the 300-token tool-text budget, and a
     scripted model turn gets the exact facts back with NO approval card.
  7. "WHAT CAN I CHANGE?" IS UNCHANGED. The existing exact answer still comes
     from jarvis_settings_registry.changeable_words.
  8. EVERY FEATURE ANSWERS EVERY OWNER QUESTION (2026-10-26). The owner asked
     for Jarvis to talk about ANY feature of the project, in detail. All 140
     rows are asked the nine questions a person actually uses - "tell me
     about", "what does it do", "explain", "how do I use", "where is", "how do
     I turn on", "can I change", "is it on", "what is it" - through the row's
     title, its id AND its aliases, and every answer must carry the name, what
     it does, where it lives, whether it asks first, which apps have it, and
     how to use or change it. "Can I change it?" never runs a setter. Every
     one-sided answer carries the row's own reason, and the two names that
     carry "Jarvis" for real (not as an address) still resolve. Before this
     section existed, three of those nine questions reached no feature intent
     at all (0/140), five rows could not be named, and 127 answers never said
     how to use or change the feature.
  9. THE OWNER'S TWO UNANSWERED QUESTIONS, AND ONE FALSE ANSWER (2026-10-26
     review). "What are you capable of?" - the screenshot question - matched
     nothing in the fast grammar ("capable" appeared nowhere in
     `jarvis_quick.py`), so it went to the model; it now answers from the fixed
     "things you can say" list, with no model. "Where do I change the jarvis
     presets?" matched no phrase at all; "where do I change <x>" is a
     where-question now, and the two kinds of preset carry the owner's own
     names as exact aliases on the rows that own them. And the five phone-only
     controls stopped saying they are changed "on this PC" - the row's
     `surface` wins over the PC-Only label's wording, with the owner-approved
     label counts untouched.

No model runs, no network, no real settings file is touched: every read/write
here is a temp folder or a recording stand-in.
"""
from __future__ import annotations

import dataclasses
import json
import re
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_feature_guide.py", "jarvis_feature_catalogue.py",
                "jarvis_agent.py", "jarvis_quick.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_feature_catalogue as CAT  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402
from test_agent import FakeStream, NoRealIO, answer_text, scripted_stream  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import gen_feature_guide_catalogue as GEN  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-feature-guide-"))
_SOURCE = json.loads((REPO / "features" / "features.json").read_text(encoding="utf-8"))
SOURCE = _SOURCE
#: The contract's own record of the approved label mix. `tools/
#: check_feature_controls.py` pins those numbers to the owner's approval; this
#: suite derives them from the contract instead of typing them, so a new
#: feature row never needs a count literal edited here.
_CONTRACT = json.loads(
    (REPO / "contract" / "feature-controls.json").read_text(encoding="utf-8"))
CONTRACT_LABEL_COUNTS = _CONTRACT["label_counts"]
_SETTINGS_BACKUP = R.BOOL_SETTINGS

# The real config folders of the two switches this suite reads for real are
# redirected into the temp folder, so a read never touches the owner's files.
import jarvis_auto_learn as AL  # noqa: E402
import jarvis_prompt_coach as PC  # noqa: E402

_AL_DIR, _PC_DIR = AL._config_dir, PC._config_dir
AL._config_dir = lambda: TMP
PC._config_dir = lambda: TMP

FEATURE_INTENTS = ("feature_explain", "feature_unknown", "feature_state",
                   "feature_state_setting", "feature_howto",
                   "feature_howto_setting", "feature_switch",
                   "feature_switch_refused", "feature_change", "features_list",
                   "features_group")

#: The owner's own questions (2026-10-26) and the intent each must reach. Every
#: row is asked every one of them through its title, id and aliases below.
OWNER_QUESTIONS = (
    ("tell me about {}", "feature_explain"),
    ("what does {} do", "feature_explain"),
    ("explain {}", "feature_explain"),
    ("how do I use {}", "feature_explain"),
    ("where is {}", "feature_explain"),
    ("how do I turn on {}", "feature_howto"),
    ("can I change {}", "feature_change"),
    ("is {} on", "feature_state"),
    ("what is {}", "feature_explain"),
)

#: The two questions an OLDER intent deliberately owns for one row. "What is
#: the morning briefing?" reads the briefing (it has read it since 2026-09-28),
#: and "is the morning briefing on?" asks the briefing module whether one is
#: set up - both are real answers to the question, in the briefing's own words,
#: not a fall-through. The feature itself is still explained by the other seven
#: questions, so this is a named exception rather than a hole.
OWNER_QUESTION_EXCEPTIONS = {
    ("briefing", "is {} on"): {"briefing_list"},
    ("briefing", "what is {}"): {"briefing_now"},
}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def say(intent, peer=None, local=None):
    """Run one fixed-phrase intent through the real dispatcher."""
    return Q.run(intent, None, 0.0, peer=peer, local=local)


def replace_setting(key: str, **changes):
    """(old, new): swap ONE BoolSetting in the table for the length of a test.

    BoolSetting is a frozen dataclass (deliberately: the table is the rule), so
    a test records a setter by replacing the whole entry - never by mutating
    the shipped one - and puts the original tuple back afterwards.
    """
    global _SETTINGS_BACKUP
    _SETTINGS_BACKUP = R.BOOL_SETTINGS
    old = next(b for b in R.BOOL_SETTINGS if b.key == key)
    new = dataclasses.replace(old, **changes)
    R.BOOL_SETTINGS = tuple(new if b.key == key else b for b in R.BOOL_SETTINGS)
    return old, new


def restore_settings():
    global _SETTINGS_BACKUP
    R.BOOL_SETTINGS = _SETTINGS_BACKUP


def match(phrase):
    return Q.match(phrase)


# ------------------------------------------------ 1. the facts are the list's

def t_every_row_is_looked_up_and_its_facts_equal_the_json():
    check("the generated catalogue names every row", len(CAT.FEATURES) == len(SOURCE),
          f"{len(CAT.FEATURES)} vs {len(SOURCE)}")
    check("the generated copy is current (tools/gen_feature_guide_catalogue.py --check)",
          GEN.main(["--check"]) == 0)
    source_by_id = {row["id"]: row for row in SOURCE}
    check("the rows and ids are the same list, in order",
          [r["id"] for r in CAT.FEATURES] == [r["id"] for r in SOURCE])
    bad = []
    for row in SOURCE:
        out = FG.explain(row["id"])
        if not out.get("ok") or out.get("kind") != "feature":
            bad.append((row["id"], out.get("kind"), "not found"))
            continue
        facts = out["feature"]
        for key in ("group", "title", "what", "where", "asks", "limit", "surface"):
            if facts.get(key) != row[key]:
                bad.append((row["id"], key, facts.get(key), row[key]))
        if facts.get("covers") != list(row.get("covers") or []):
            bad.append((row["id"], "covers", facts.get("covers"),
                        row.get("covers")))
        for text in (row["what"], row["where"], row["asks"]):
            if text not in out["words"]:
                bad.append((row["id"], "words lost a field", text[:40]))
        if row.get("limit") and row["limit"] not in out["words"]:
            bad.append((row["id"], "words lost limit", row["limit"][:40]))
        if not row.get("limit") and "gives no limit" not in out["words"]:
            bad.append((row["id"], "empty limit not said", ""))
    check("every one of the 140 rows is found by id, with facts equal to the JSON",
          not bad, bad[:6])
    # A row whose words are not the list's is a reworded fact. Each answer is
    # assembled from the row the module's own `features()` returns; prove the
    # sweep above would have caught a changed word, on one row, without
    # changing the shipped data.
    row = dict(CAT.FEATURES[0])
    row["what"] = row["what"] + " (reworded)"
    original = FG.features
    try:
        FG.features = lambda: [row] + [dict(r) for r in CAT.FEATURES[1:]]
        out = FG.explain(row["id"])
        check("...and the comparison is real: an answer uses the row it is given",
              "(reworded)" in out["words"]
              and "(reworded)" not in SOURCE[0]["what"])
    finally:
        FG.features = original


def t_unknown_and_ambiguous_never_guess():
    out = FG.explain("turbo mode")
    check("an unknown feature says it is not in the list", out["ok"] is False
          and out["kind"] == "unknown"
          and "do not have a feature" in out["words"], out)
    check("...and offers the real groups", "groups" in out["words"]
          and str(len(FG.groups())) in out["words"], out["words"][:200])
    out = FG.explain("what is the thing that does the turbo")
    check("a feature question with no matching row is still unknown, not a guess",
          out["ok"] is False and out["kind"] == "unknown", out)
    check("a two-feature name is reported as ambiguous, with candidates",
          FG.find("the memory and safety")["kind"] in ("unknown", "ambiguous"))
    rows = FG.groups()
    check("every group is named with its real count",
          sum(g["count"] for g in rows) == len(SOURCE)
          and [g["group"] for g in rows] == CAT.GROUPS, rows)


def t_cloud_sync_is_answered_not_padded():
    """Gemini's post-review (2026-10-20, HIGH-4): the live model padded "I do not
    have that" with generic OneDrive/Google Drive advice, which nudges the owner
    toward pointing a third-party sync folder at Jarvis's private folders. The
    guide now answers the topic directly, deterministically, and names the real
    path (Tailscale/Meshnet + encrypted .jbak backups)."""
    for asked in ("cloud sync", "how do I turn on cloud sync",
                  "sync across devices", "can I sync my files to OneDrive"):
        out = FG.explain(asked)
        check(f'"{asked}" is answered, not invented', out["ok"] is True
              and out["kind"] == "note", out)
        check("...and the answer names the private link and the encrypted backup",
              "does not use cloud sync" in out["words"]
              and "Tailscale" in out["words"] and "Meshnet" in out["words"]
              and ".jbak" in out["words"], out.get("words"))
    out = FG.state("is cloud sync on")
    check("the on/off question about cloud sync gets the same honest note",
          out["ok"] is True and out["kind"] == "note" and out.get("state") is None
          and "does not use cloud sync" in out["words"], out)
    check("the tool result path (feature_guide) carries it too",
          FG.tool_result("cloud sync")["kind"] == "note")
    ambient = FG.explain("the prompt coach")
    check("...and an ordinary feature question is unaffected",
          ambient["kind"] == "feature", ambient.get("kind"))


# -------------------------------- 2. state: read, or said that it could not be

def t_every_switch_has_a_state_reader():
    missing = [b.key for b in R.BOOL_SETTINGS if b.key not in FG.STATE_READERS]
    check("every on/off switch in jarvis_settings_registry has a state reader here",
          not missing, missing)
    before = set(FG.STATE_READERS)
    fake = R.BoolSetting("test_only_switch", ("a setting added by the test",), None,
                         R.set_prompt_coach)
    R.BOOL_SETTINGS = R.BOOL_SETTINGS + (fake,)
    try:
        check("a switch added to the table has no reader until one is written",
              "test_only_switch" not in FG.STATE_READERS, sorted(FG.STATE_READERS)[:4])
    finally:
        R.BOOL_SETTINGS = R.BOOL_SETTINGS[:-1]
    check("...and the reader table was not changed by the test", set(FG.STATE_READERS) == before)


def t_current_on_off_is_read_from_the_owners_module():
    PC.set_enabled(False)
    off = FG.read_state("prompt_coach")
    PC.set_enabled(True)
    on = FG.read_state("prompt_coach")
    check("the prompt coach's real switch reads off then on, from the module's own reader",
          off is False and on is True, (off, on))
    check("...and the temp config folder is the only place it wrote",
          PC.settings_path().parent == TMP, PC.settings_path())
    backup = dict(FG.STATE_READERS)
    try:
        FG.STATE_READERS["prompt_coach"] = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        check("a reader that raises reads as UNKNOWN, never as off",
              FG.read_state("prompt_coach") is None)
        FG.STATE_READERS["prompt_coach"] = lambda: "yes"
        check("a reader that returns something other than True/False is UNKNOWN too",
              FG.read_state("prompt_coach") is None)
    finally:
        FG.STATE_READERS = backup
    PG = FG.explain("prompt coach")
    check("the prompt coach's answer carries its real switch, from that reader",
          any(s["key"] == "prompt_coach" and s["state"] is True for s in PG["switches"]),
          PG["switches"])


def t_state_never_claims_what_it_did_not_read():
    backup = dict(FG.STATE_READERS)
    try:
        FG.STATE_READERS["prompt_coach"] = lambda: None
        out = FG.state("prompt coach")
        check("an unreadable switch gives state None and says it could not read it",
              out.get("state") is None and "could not read" in out["words"]
              and "guess" in out["words"], out)
        check("...and the answer does not contain an on/off claim",
              not re.search(r"\b(?:is|are) (?:on|off) right now\b", out["words"]), out["words"])
        FG.STATE_READERS["prompt_coach"] = lambda: False
        out = FG.state("prompt coach")
        check("a readable switch gives its real value in words", out.get("state") is False
              and "off right now" in out["words"], out)
        FG.STATE_READERS["prompt_coach"] = lambda: True
        out = FG.state("prompt coach")
        check("...both ways", out.get("state") is True and "on right now" in out["words"], out)
    finally:
        FG.STATE_READERS = backup
    out = FG.state("typing")
    check("a feature with no on/off switch says so instead of inventing a state",
          out.get("ok") is True and out.get("state") is None
          and "no on/off switch" in out["words"], out)
    out = FG.state("nonsense xyz")
    check("an unknown feature says it is not in the list", out["ok"] is False
          and out["kind"] == "unknown", out)


# ------------------------------------- 3. the fixed phrases (no model at all)

def t_the_fixed_phrases_answer_the_right_intent():
    wanted = {
        "what is the prompt coach": "feature_explain",
        "what's the prompt coach": "feature_explain",
        "explain the prompt coach": "feature_explain",
        "tell me about the prompt coach": "feature_explain",
        "what does the prompt coach do": "feature_explain",
        "what is the clipboard time machine": "feature_explain",
        "what is a focus session": "feature_explain",
        # "Write like me" (2026-10-20): the row's exact name, and the way the
        # owner actually asks to be trained.
        "what is write like me": "feature_explain",
        "what is the write like me feature": "feature_explain",
        "how do I train you to write like me?": "feature_explain",
        "how do I train you to write like me": "feature_explain",
        "how do I teach you to write like me": "feature_explain",
        "is write like me on": "feature_state",
        "Jarvis, what is the turbo feature": "feature_unknown",
        "is the prompt coach on": "feature_state",
        "is the prompt coach on right now": "feature_state",
        "is the prompt coach enabled": "feature_state",
        "is background learning on": "feature_state_setting",
        "how do I turn on the prompt coach": "feature_howto",
        "how do I turn off the prompt coach": "feature_howto",
        "how can I enable the prompt coach": "feature_howto",
        "how to turn on phone notifications": "feature_howto",
        "what features do you have": "features_list",
        "list the features": "features_list",
        "what are your features": "features_list",
        "what's in the memory group": "features_group",
        "list the memory features": "features_group",
        "turn on browser engine": "feature_switch",
        "turn on custom voices": "feature_switch_refused",
    }
    for phrase, want in wanted.items():
        got = match(phrase)
        check(f"'{phrase}' -> {want}", got is not None and got.name == want,
              f"got {got.name if got else 'the model'}")


def t_the_fixed_phrases_do_not_swallow_other_questions():
    # Each of these is a different question. None may be answered with a
    # feature's facts, and where an older intent already owned the sentence it
    # must keep owning it.
    other = ("what is the weather", "is the weather on", "is the oven on",
             "how do I turn on the oven", "how do I turn on my phone bluetooth",
             "turn on the kitchen light", "what is my name",
             "what's a good pasta recipe", "what is quantum physics",
             "tell me about your day", "is it going to rain tomorrow",
             "turn off the weather", "what can you do", "what did I miss",
             # Gemini's §11.8.3 examples: a general question that merely
             # CONTAINS a feature's word is not that feature's question.
             "what is a focus session in psychology",
             "how do I turn on dark mode in Chrome",
             "where is my file manager", "is my oven on",
             # "how do I train/teach you to ..." is a feature question, but
             # training something else is not (2026-10-20).
             "how do I train my dog to sit")
    for phrase in other:
        got = match(phrase)
        check(f"'{phrase}' is not answered as a feature",
              got is None or got.name not in FEATURE_INTENTS,
              f"got {got.name if got else 'the model'}")
    got = match("what is the weather")
    check("'what is the weather' keeps the older weather intent (or the model)",
          got is None or got.name == "weather_now", got.name if got else "the model")
    got = match("turn off the weather")
    check("'turn off the weather' keeps the animal/weather path",
          got is not None and got.name.startswith("animal_"),
          got.name if got else "the model")


def t_the_phrase_gate_requires_an_exact_name_or_jarvis_context():
    """Gemini's §11.8.3 gate, stated as its own check.

    The fixed phrases fire only when the sentence is explicitly about Jarvis
    ("Jarvis", "here", "my settings") OR the subject after "what is [the] ..."
    / "is [the] ... on" EXACTLY matches a catalogue name. A general question
    that merely CONTAINS a feature's word is not answered with that feature's
    facts - it falls through to the model."""
    # The matcher itself: exact names in, loose substrings out.
    check("find_exact answers an exact title and id, articles ignored",
          (FG.find_exact("the prompt coach") or {}).get("id") == "prompt-coach"
          and (FG.find_exact("Focus session") or {}).get("id") == "focus")
    check("find_exact refuses a sentence that CONTAINS a feature name",
          FG.find_exact("a focus session in psychology") is None
          and FG.find_exact("dark mode in chrome") is None
          and FG.find_exact("focus sessions") is None)
    check("...while the looser matcher is still there for the model's own tool",
          FG.find_feature("prompt coach feature", strong=False) is not None
          and FG.find_feature("a focus session in psychology", strong=False) is None)
    # The whole grammar: the four questions from the review fall through.
    for phrase in ("what is a focus session in psychology",
                   "how do I turn on dark mode in chrome",
                   "where is my file manager", "is my oven on"):
        got = match(phrase)
        check(f"'{phrase}' is the model's, not a feature's",
              got is None or got.name not in FEATURE_INTENTS,
              f"got {got.name if got else 'the model'}")
    # Positive controls: an exact catalogue name answers with no Jarvis word...
    for phrase, intent in (("what is the prompt coach", "feature_explain"),
                           ("what is the clipboard time machine", "feature_explain"),
                           ("what is a focus session", "feature_explain"),
                           ("is the prompt coach on", "feature_state"),
                           ("how do I turn on web search", "feature_howto")):
        got = match(phrase)
        check(f"...and an exact name still answers: '{phrase}'",
              got is not None and got.name == intent,
              f"got {got.name if got else 'the model'}")
    # ...and explicit Jarvis context still allows the honest unknown answer,
    # while a general question addressed to Jarvis does NOT get one.
    got = match("Jarvis, what is the turbo feature")
    check("...and explicit context still says an unknown feature is unknown",
          got is not None and got.name == "feature_unknown",
          got.name if got else "the model")
    got = match("Jarvis, what is quantum physics")
    check("...but a general question addressed to Jarvis stays the model's",
          got is None or got.name not in FEATURE_INTENTS,
          got.name if got else "the model")


def t_answering_works_without_a_model_and_says_the_facts():
    got = match("what is the prompt coach")
    out = say(got)
    row = next(r for r in SOURCE if r["id"] == "prompt-coach")
    check("the explanation is answered here, with the list's own where/asks/limit",
          out is not None and row["where"] in out.reply and row["asks"] in out.reply
          and row["limit"] in out.reply, out.reply if out else None)
    got = match("what features do you have")
    out = say(got)
    check("the groups answer names all 9 groups and the real count",
          out is not None and f"{len(SOURCE)} features" in out.reply
          and all(g["group"] in out.reply for g in FG.groups()), out.reply[:200] if out else None)
    got = match("Jarvis, what is the turbo feature")
    out = say(got)
    check("an unknown feature is said plainly, with the groups to pick from",
          out is not None and "turbo" in out.reply
          and "do not have a feature" in out.reply, out.reply[:200] if out else None)


def t_cloud_sync_is_answered_without_a_model():
    """Gemini post-review HIGH-4: the model used to pad "I do not have that" with
    generic OneDrive/Google Drive advice. The fixed phrase now answers it from
    the guide's own note, before any model can add a sync suggestion."""
    for phrase in ("how do I turn on cloud sync for my files",
                   "what is cloud sync",
                   "can I sync across devices"):
        got = match(phrase)
        check(f'"{phrase}" is routed to the guide, not the model',
              got is not None and got.name == "feature_explain", got)
        if got is None:
            continue
        out = say(got)
        check("...and the fixed answer names the private link and the .jbak backup",
              out is not None and "does not use cloud sync" in out.reply
              and "Tailscale" in out.reply and "Meshnet" in out.reply
              and ".jbak" in out.reply, out.reply[:300] if out else None)


# --------------------------- 4. switching by chat goes through the real setter

def t_switching_uses_the_real_setter_and_reports_its_outcome():
    calls = []

    class Out:
        def __init__(self, ok, said, waiting=False):
            self.ok, self.said, self.waiting = ok, said, waiting

    old, new = replace_setting("headless_browser")
    try:
        R.BOOL_SETTINGS = tuple(
            dataclasses.replace(b, set=lambda on, **kw: calls.append(on) or Out(
                True, "Done - the windowless browser is on."))
            if b.key == "headless_browser" else b for b in R.BOOL_SETTINGS)
        got = match("turn on browser engine")
        out = say(got)
        check("a feature's switch phrase calls the SAME BoolSetting.set (with the card rule)",
              got is not None and got.name == "feature_switch"
              and calls and calls[0] is True, (got.name if got else None, calls))
        check("...and the answer is the setter's own words, not a canned 'Done'",
              out is not None and out.reply == "Done - the windowless browser is on.",
              out.reply if out else None)
        calls.clear()
        R.BOOL_SETTINGS = tuple(
            dataclasses.replace(b, set=lambda on, **kw: calls.append(on) or Out(
                False, "That did not work - the browser setting could not be saved."))
            if b.key == "headless_browser" else b for b in R.BOOL_SETTINGS)
        out = say(match("turn off browser engine"))
        check("a setter that did not work is repeated as it said it, never as success",
              out is not None and out.reply == ("That did not work - the browser setting "
                                                "could not be saved.")
              and "Done." not in out.reply, out.reply if out else None)
        calls.clear()
        R.BOOL_SETTINGS = tuple(
            dataclasses.replace(b, set=lambda on, **kw: calls.append(on) or Out(
                True, "An approval card is up - approve it to switch the browser on.",
                waiting=True))
            if b.key == "headless_browser" else b for b in R.BOOL_SETTINGS)
        out = say(match("turn on browser engine"))
        check("a setter that raised a card says so - nothing is claimed as changed",
              out is not None and "approval card" in out.reply, out.reply if out else None)
    finally:
        restore_settings()
    check("...and the real setter table is put back", R.BOOL_SETTINGS is _SETTINGS_BACKUP)


def t_a_feature_with_several_switches_changes_nothing():
    touched = []
    replace_setting("voice_follows_face")
    R.BOOL_SETTINGS = tuple(
        dataclasses.replace(b, set=lambda on, _key=b.key, **_kw: touched.append(_key))
        if b.key in ("voice_follows_face", "better_voice") else b
        for b in R.BOOL_SETTINGS)
    try:
        got = match("turn on custom voices")
        out = say(got)
        check("a feature naming several switches is refused in words, changing nothing",
              got is not None and got.name == "feature_switch_refused"
              and out is not None and "more than one switch" in out.reply
              and "voice follows the face" in out.reply
              and "the better voice" in out.reply, out.reply if out else None)
        check("...and neither of its setters ran", not touched, touched)
    finally:
        restore_settings()


# ------------------------------------------- 5. the model tool: read-only, no card

def t_the_tool_is_listed_short_and_read_only():
    check("jarvis_agent.TOOLS has feature_guide", "feature_guide" in AG.TOOLS)
    tool = AG.TOOLS["feature_guide"]
    check("its argument is the one feature name", list(tool.parameters["properties"]) == ["feature"],
          tool.parameters)
    # D1a, the live campaign of 2026-10-25: `feature` used to be REQUIRED, so
    # the one listing call the tool documents (`{"feature": ""}`) was refused by
    # check_call before the tool ran - four times in one turn on the owner's PC.
    # The schema now says what the tool does: the field may be left out.
    check("its one argument is NOT required, because \"\" lists the groups",
          "feature" not in (tool.parameters.get("required") or []), tool.parameters)
    tokens = AG.estimate_tokens(tool.schema())
    check(f"its text is within the per-tool budget (300 tokens; it is {tokens})",
          tokens <= 300, tokens)
    check("says what not to do: never invent a feature",
          "never invent" in tool.description)
    check("says when to use it, in the ruling's own words",
          "Use when" in tool.description and "Do NOT use" in tool.description,
          tool.description[:120])
    check("is decided under the gate's read-only skill_list action (tier auto, no card)",
          tool.gate_lookup_name({}) == "skill_list")
    action, known = None, False
    try:
        import jarvis_gate
        action, known = jarvis_gate.action_for_tool(tool.gate_lookup_name({}), {})
    except Exception:
        pass
    if action is not None:
        check("...and the gate resolves it to the auto tier", action == "skill_list")
    check("its result is not marked as outside text", "feature_guide" in AG._NOT_READING)
    homes = [g for g, _w, members in AG.TOOL_GROUPS if "feature_guide" in members]
    check("it is in exactly one short-list group", homes == ["settings"], homes)
    check("offered when enabled, not offered when not",
          "feature_guide" in AG.offered_tools({"feature_guide"})
          and "feature_guide" not in AG.offered_tools({"calculator"}))


def t_the_documented_listing_call_is_never_refused():
    """D1a: the listing call the tool's own schema documents must reach the tool.

    Before this fix `check_call` answered "'feature' is required" for
    `{"feature": ""}` - the exact call `_feature_guide_tool_text()` and the
    property's own description tell the model to make - so the model retried it
    four times in one turn and then invented the features instead
    (calls/200145-probe-feature-guide-2.json in the 2026-10-25 campaign).
    """
    for raw, why in ((json.dumps({"feature": ""}), "an empty string"),
                     ("{}", "no arguments at all"),
                     (json.dumps({"feature": None}), "a null feature")):
        args, problem = AG.check_call("feature_guide", raw, ["feature_guide"])
        check(f"{why} is accepted, not refused", problem is None and isinstance(args, dict),
              problem or args)
    groups = AG._run_feature_guide(AG.check_call(
        "feature_guide", json.dumps({"feature": ""}), ["feature_guide"])[0])
    check("...and it really answers with the groups",
          groups.get("ok") is True and groups.get("kind") == "groups"
          and len(groups["groups"]) == len(CAT.GROUPS), groups.get("kind"))


def t_a_model_turn_can_list_the_groups_with_no_refusal():
    """The same, through a real turn: the model asks for the groups and gets
    them, in one round, with no refusal sentence in the conversation."""
    tool_call = {"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"id": "g1", "function": {"name": "feature_guide",
                                  "arguments": json.dumps({"feature": ""})}}]}}]}
    final = {"choices": [{"message": {"role": "assistant",
                                      "content": "The groups are the ones the guide lists."}}]}
    opener, calls = scripted_stream([tool_call, final])
    streamed, refusals = [], []

    def gate(action, detail, prompt):
        class V:
            allowed, outcome, tier, request_id, reason = True, "auto", "auto", None, ""
        V.action = action
        return V

    real_manner = AG._manner_now
    real_can = AG._model_can_use_tools
    AG._manner_now = lambda *a, **k: None
    AG._model_can_use_tools = lambda url, model: True
    try:
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "what features do you have",
                  "provenance": "typed"}], "qwen3:8b",
                ollama_url="http://127.0.0.1:11434", stream_out=streamed.append,
                gate_check=gate, open_stream=opener,
                enabled_tools={"feature_guide"},
                on_step=refusals.append,
                request={"conversation_id": "fg-list",
                         "messages": [{"role": "user", "content": "what features do you have",
                                       "provenance": "typed"}]})
    finally:
        AG._manner_now = real_manner
        AG._model_can_use_tools = real_can
    tool_msg = calls[1]["messages"][-1] if len(calls) > 1 else {}
    refused = [s for s in refusals if s.get("kind") == "tool_refused"]
    check("the blank listing call is not refused in a real turn", not refused, refused)
    check("the model is fed the guide's own groups",
          tool_msg.get("role") == "tool"
          and any(g in tool_msg.get("content", "") for g in CAT.GROUPS),
          tool_msg.get("content", "")[:120])
    check("the turn answers with the model's words", bool(answer_text(streamed)),
          answer_text(streamed))


def t_the_tool_returns_the_exact_facts():
    out = AG._run_feature_guide({"feature": "prompt coach"})
    row = next(r for r in SOURCE if r["id"] == "prompt-coach")
    check("the tool's result carries the row's exact where/asks/limit",
          out.get("ok") is True and out["feature"]["where"] == row["where"]
          and out["feature"]["asks"] == row["asks"]
          and row["limit"] in out["words"], out.get("kind"))
    groups = AG._run_feature_guide({"feature": ""})
    check("an empty feature lists the groups, read-only",
          groups.get("ok") is True and groups.get("kind") == "groups"
          and len(groups["groups"]) == len(CAT.GROUPS), groups.get("kind"))


def t_a_model_turn_gets_the_facts_with_no_card():
    tool_call = {"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"id": "c1", "function": {"name": "feature_guide",
                                  "arguments": json.dumps({"feature": "prompt coach"})}}]}}]}
    final = {"choices": [{"message": {"role": "assistant",
                                      "content": "The prompt coach checks a prompt before you send it."}}]}
    opener, calls = scripted_stream([tool_call, final])
    cards, verdicts = [], []

    def gate(action, detail, prompt):
        cards.append((action, detail.get("text", "") if isinstance(detail, dict) else ""))

        class V:
            allowed, outcome, tier, request_id, reason = True, "auto", "auto", None, ""
        V.action = action
        verdicts.append(V)
        return V

    streamed = []
    real_manner = AG._manner_now
    real_can = AG._model_can_use_tools
    AG._manner_now = lambda *a, **k: None
    AG._model_can_use_tools = lambda url, model: True
    try:
        with NoRealIO():
            AG.run_local_turn(
                [{"role": "user", "content": "what is the prompt coach",
                  "provenance": "typed"}], "qwen3:8b",
                ollama_url="http://127.0.0.1:11434", stream_out=streamed.append,
                gate_check=gate, open_stream=opener,
                enabled_tools={"feature_guide"},
                request={"conversation_id": "fg-1",
                         "messages": [{"role": "user", "content": "what is the prompt coach",
                                       "provenance": "typed"}]})
    finally:
        AG._manner_now = real_manner
        AG._model_can_use_tools = real_can
    row = next(r for r in SOURCE if r["id"] == "prompt-coach")
    tool_msg = calls[1]["messages"][-1] if len(calls) > 1 else {}
    check("the model is fed the guide's exact facts", tool_msg.get("role") == "tool"
          and row["where"] in tool_msg.get("content", ""), tool_msg.get("role"))
    check("the turn raised NO approval card: one gate call, action skill_list (auto)",
          len(cards) == 1 and cards[0][0] == "skill_list", cards)
    check("the answer is completed and the model's own words reach the app",
          answer_text(streamed).startswith("The prompt coach"), answer_text(streamed))


# -------------------------------------------- 6. what can I change? unchanged

def t_what_can_i_change_is_still_the_exact_answer():
    got = match("what can I change")
    check("'what can I change' is still the settings help", got is not None
          and got.name == "settings_help", got.name if got else "the model")
    out = say(got)
    want = R.changeable_words()
    check("...and its answer is still changeable_words, exactly", out is not None
          and out.reply == want)
    count = R.changeable_settings()["count"]
    check("...which still names the real count and the card/undo rule",
          out is not None and str(count) in out.reply and "undo" in out.reply.lower(),
          out.reply[:120] if out else None)


def t_every_feature_has_a_matrix_row_and_a_reason():
    """The owner's requirement is a matrix, not an anecdote: every catalogue
    feature is either command-controllable (proved by a working
    phrase through the real matcher) or carries a stable reason code and an
    owner. A feature missing from both is a silent gap - this test forbids it."""
    rows = FG.control_matrix()
    check("the matrix has one row per catalogue feature",
          len(rows) == FG.feature_count() and
          [r["id"] for r in rows] == [r["id"] for r in FG.features()],
          (len(rows), FG.feature_count()))
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        check(f"{r['id']} has a known status",
              r["status"] in ("switch", "adjust", "open-only", "not-a-setting", "planned"),
              r["status"])
        if r["status"] not in ("switch", "adjust"):
            check(f"{r['id']} carries a stable reason code",
                  bool(r["reason_code"]) and r["reason_code"] in FG.REASON_CODES,
                  r["reason_code"])
            check(f"{r['id']} names an owner for its gap",
                  bool(r["owner"]) and r["owner"] in
                  ("voiceprint-wiring", "setup-ui", "Session B", "none-needed"),
                  r["owner"])
    check("no feature is silently missing a reason",
          not FG.matrix_rows_without_reason(), FG.matrix_rows_without_reason())
    # The other direction: an allowlist row may not excuse a feature that now
    # HAS a working control (that would be a stale excuse nobody re-checked).
    controllable = {r["id"] for r in rows if r["status"] in ("switch", "adjust")}
    stale = sorted(set(FG.NO_COMMAND_REASON) & controllable)
    check("no allowlist row excuses a feature that is now controllable",
          not stale, stale)
    # The typed phrases the matrix carries must be exactly the phrases that work
    # - an intent of None is a promise nobody checked.
    for r in rows:
        for entry in r["adjust"]:
            check(f"{r['id']}: {entry['phrase']!r} works", bool(entry["intent"]), entry)
        # Every switch the row names has its OWN working phrase (the
        # exhaustive BOOL loop lives in test_settings_registry.py); a feature
        # title that is not a switch alias may legitimately not resolve, so the
        # generic sentence is reported, not required.
        for key in r["switch_keys"]:
            b = next((x for x in R.BOOL_SETTINGS if x.key == key), None)
            check(f"{r['id']}: {key} is a real switch", b is not None, key)
            if b is None or not b.names:
                continue
            got = match(f"turn on {b.names[0]}")
            check(f"{r['id']}: 'turn on {b.names[0]}' reaches {key}",
                  got is not None and got.name == "settings_bool"
                  and got.f.get("key") == key, got)


def t_the_matrix_tables_link_to_real_controls():
    """Every key and place the matrix's helper tables name is real: a switch
    key from the registry, a Settings card that exists, or a phrase that
    resolves through the real matcher. Never a string typed only here."""
    bool_keys = {b.key for b in R.BOOL_SETTINGS}
    places = set()
    for row in FG.features():
        for cover in row.get("covers") or ():
            if str(cover).startswith("settings."):
                sid = str(cover).split("settings.", 1)[1]
                if R.section_by_id(sid) is not None:
                    places.add(sid)
    for fid, keys in FG.EXTRA_CONTROLS.items():
        for key in keys:
            check(f"EXTRA_CONTROLS[{fid!r}] names the real switch {key}",
                  key in bool_keys, key)
    for fid, extra in FG.EXTRA_ADJUST.items():
        for place in extra:
            check(f"EXTRA_ADJUST[{fid!r}] names a real Settings card {place}",
                  place == "topics" or R.section_by_id(place) is not None, place)
    for place, proofs in FG.ADJUST_SECTIONS.items():
        for phrase, _kind in proofs:
            got = match(phrase)
            check(f"ADJUST_SECTIONS[{place!r}]: {phrase!r} resolves",
                  got is not None and not str(getattr(got, "name", "")).endswith("_bad"),
                  got.name if got else None)
    for row in FG.control_matrix():
        for key in row["switch_keys"]:
            check(f"{row['id']} names a real switch ({key})", key in bool_keys, key)


def t_the_five_owner_labels_are_exact_and_every_feature_has_one():
    """Ruling Q8 (2026-10-22): exactly these five plain labels, one per feature,
    used by the report AND the Settings "All features & abilities" directory.
    A feature with no label, or a label outside the five, is a silent omission."""
    check("the five labels are the approved words, in order",
          FG.CONTROL_LABELS == (
              "Switchable / Adjustable (Typed & Settings)",
              "Settings-Only (By Design \u2014 Security Boundary)",
              "PC-Only Setting (Honest Refusal on Phone)",
              "Command-Only (Runs When You Ask \u2014 No Switch Needed)",
              "Always On (Core Safety Rule \u2014 Cannot Be Turned Off)"),
          FG.CONTROL_LABELS)
    directory = FG.abilities_directory()
    check("the directory has every feature exactly once",
          len(directory) == FG.feature_count()
          and len({r["id"] for r in directory}) == FG.feature_count(),
          (len(directory), FG.feature_count()))
    allowed = set(FG.CONTROL_LABELS)
    for row in directory:
        check(f"{row['id']} has one of the five labels",
              row["label"] in allowed, row["label"])
        check(f"{row['id']} says whether it is a toggle in plain words",
              bool(row["example_words"]) and bool(row["settings_path"]),
              row)
        check(f"{row['id']} names a Settings place",
              "Settings" in row["settings_path"], row["settings_path"])
        if not row["switch_keys"] and "Settings, " + "" in row["settings_path"] and "(planned)" in row["settings_path"]:
            check(f"{row['id']}'s planned directory is marked planned", True)
        mine = next(r for r in FG.control_matrix() if r["id"] == row["id"])
        check(f"{row['id']}'s label matches its matrix row",
              row["label"] == mine["control_class"], (row["label"], mine["control_class"]))
        if mine["status"] == "switch":
            check(f"{row['id']} is marked a toggle", mine["is_toggle"] is True, mine["is_toggle"])
        else:
            check(f"{row['id']} is marked not a toggle", mine["is_toggle"] is False, mine["is_toggle"])
            check(f"{row['id']} says plainly it is not a toggle",
                  "not a toggle" in mine["not_a_toggle_words"].lower(),
                  mine["not_a_toggle_words"])
    counts = {label: sum(1 for r in directory if r["label"] == label) for label in FG.CONTROL_LABELS}
    # Lead's 2026-10-22 classification rules, pinned exactly. The expected
    # numbers are the contract's own approved `label_counts`, not typed here:
    # tools/check_feature_controls.py holds the contract to the owner's mix.
    check("Settings-Only is exactly the Accounts + Restore-backup pair",
          counts[FG.LABEL_SETTINGS_ONLY] == CONTRACT_LABEL_COUNTS[FG.LABEL_SETTINGS_ONLY]
          and {r["id"] for r in directory if r["label"] == FG.LABEL_SETTINGS_ONLY}
          == {"accounts", "backup"}, counts)
    check("Always On is the canonical 12-row safety list",
          counts[FG.LABEL_ALWAYS_ON] == len(FG.ALWAYS_ON_IDS)
          and {r["id"] for r in directory if r["label"] == FG.LABEL_ALWAYS_ON}
          == FG.ALWAYS_ON_IDS, counts)
    check("the canonical 12 always-on ids are the approved union",
          FG.ALWAYS_ON_IDS == {
              "approvals", "app-lock", "trust", "rush-latch", "outside-text",
              "stale-link", "stop-everything", "crisis-help", "sensitive-facts",
              "memory-waiting", "settings-entry", "devices"}, sorted(FG.ALWAYS_ON_IDS))
    check("PC-Only is the pc-only, app-local and non-account key rows",
          counts[FG.LABEL_PC_ONLY] == CONTRACT_LABEL_COUNTS[FG.LABEL_PC_ONLY], counts)
    check("Command-Only is the remaining abilities + read-only pages",
          counts[FG.LABEL_COMMAND_ONLY] == CONTRACT_LABEL_COUNTS[FG.LABEL_COMMAND_ONLY], counts)
    check("Switchable/Adjustable is the real switch, choice and multi-field rows",
          counts[FG.LABEL_SWITCH_ADJUST] == CONTRACT_LABEL_COUNTS[FG.LABEL_SWITCH_ADJUST], counts)
    # Lead review: the six Switchable rows without a typed proof carry a
    # visible planned marker (backup is Settings-Only, so not counted here).
    planned = [r for r in FG.control_matrix() if r.get("planned")]
    check("exactly the six multi-field rows are marked planned",
          len(planned) == 6
          and {r["id"] for r in planned} == {
              "folders", "spending", "email-send", "hardware", "models", "compute"},
          [r["id"] for r in planned])
    check("every planned row carries the visible note",
          all(r.get("planned_words") for r in planned), planned)
    check("the five counts sum to the catalogue", sum(counts.values()) == len(SOURCE), counts)
    # The rules themselves, so a future reclassification cannot quietly drift:
    # an always-on rule may still have a typed control (approvals has a card
    # display choice) but its owner-facing label must say Always On.
    wrong = [r["id"] for r in directory
             if r["id"] in FG.ALWAYS_ON_IDS and r["label"] != FG.LABEL_ALWAYS_ON]
    check("every always-on rule is labelled Always On", not wrong, wrong)


def t_turning_on_an_ability_gets_a_deterministic_honest_answer():
    """Ruling Q2(a): typing turn on/off an ability that has no switch gets the
    honest kind (Always On vs Command-Only), a real example where one exists,
    and the exact Settings place - no fake switch and no model guess."""
    stop = FG.row_by_id("stop-everything")
    words = FG.ability_explanation(stop)
    check("an always-on safety rule says so", "Always On" in words, words)
    check("...names its Settings inspection place", "Settings" in words, words)
    ret = FG.row_by_id("retirement")
    words = FG.ability_explanation(ret)
    check("a command-only ability says it runs when asked", "Command-Only" in words, words)
    check("...gives a real example phrase or says there is none",
          "for example" in words.lower() or "no fixed" in words.lower(), words)
    check("...names its Settings place", "Settings" in words, words)
    # Through the real matcher: "turn off stop everything" answers, changes
    # nothing, and never reaches the model as a silent success.
    import jarvis_quick as Q
    got = Q.match("turn off stop everything")
    check("the fixed phrase reaches the feature refusal, not a model turn",
          got is not None and got.name == "feature_switch_refused", got)
    if got is not None and got.name == "feature_switch_refused":
        check("...and its words are the honest Always-On explanation",
              "Always On" in str(got.f.get("words") or ""), got.f)


def t_abilities_directory_labels_are_consistent_with_reason_codes():
    """The label is DERIVED, never typed twice: credentials -> Settings-Only,
    PC-only/app-local/multi-field -> PC-Only, safety rules -> Always On, the
    rest of the non-toggle rows -> Command-Only."""
    for row in FG.control_matrix():
        expected = FG._label_from(row["status"], row["reason_code"], row["id"])
        check(f"{row['id']}'s label is derived from its status/reason",
              row["control_class"] == expected, (row["control_class"], expected))
    for row in FG.abilities_directory():
        if row["reason_code"] != "credentials":
            continue
        if row["id"] in FG.SETTINGS_ONLY_IDS:
            check(f"{row['id']} (credentials) is Settings-Only",
                  row["label"] == FG.LABEL_SETTINGS_ONLY, row["label"])
        elif row["id"] in FG.ALWAYS_ON_IDS:
            check(f"{row['id']} is on the always-on canonical list",
                  row["label"] == FG.LABEL_ALWAYS_ON, row["label"])
        else:
            check(f"{row['id']} (pairing/key) is PC-Only, not a security boundary claim",
                  row["label"] == FG.LABEL_PC_ONLY, row["label"])


def t_always_on_rules_own_no_switch_and_point_to_their_exception():
    """Lead's 2026-10-22 sensitive-facts ruling: an Always-On SAFETY RULE must
    have no switch of its own; its exception (e.g. learn_sensitive_topics) is a
    separate setting, where typed on/off and card gating still work."""
    rows = {r["id"]: r for r in FG.control_matrix()}
    for aid in FG.ALWAYS_ON_IDS:
        row = rows.get(aid)
        check(f"{aid} is a real feature row", row is not None, aid)
        if row is None:
            continue
        check(f"{aid} (Always On) owns no switch", row["switch_keys"] == [], row["switch_keys"])
        check(f"{aid} (Always On) is not a switch/adjust row",
              row["status"] not in ("switch", "adjust"), row["status"])
        check(f"{aid} (Always On) carries a reason", bool(row["reason"]), row)
        check(f"{aid} (Always On) names a screen path",
              "Settings" in row["screen_path"], row["screen_path"])
    # The exception is not hidden: it is reachable through its own setting.
    import jarvis_quick as Q
    got = Q.match("turn on also remember sensitive topics automatically")
    check("learn_sensitive_topics still resolves through its own switch",
          got is not None and got.name == "settings_bool"
          and got.f.get("key") == "learn_sensitive_topics", got)
    learning = {r["id"]: r for r in FG.control_matrix()}["memory-learning"]
    check("the memory-learning row still names both learning switches",
          set(learning["switch_keys"]) == {"background_learning",
                                           "learn_sensitive_topics"},
          learning["switch_keys"])
    words = FG.ability_explanation(FG.row_by_id("sensitive-facts"))
    check("sensitive-facts explains the rule and points to the exception",
          "Always On" in words
          and "also remember sensitive topics automatically" in words,
          words)


def t_settings_gaps_are_real_named_and_owned():
    """A command-controllable feature whose control is NOT on the Settings page
    must say so, with an owner - setup-ui's audit of 2026-10-22 (chat history
    switch + retention, and the two learning switches, live only in Brain).
    A page-less typed path that looked "covered" would be the exact lie this
    project keeps fixing."""
    bool_keys = {b.key for b in R.BOOL_SETTINGS}
    choice_keys = {c.key for c in R.CHOICE_SETTINGS}
    by_id = {r["id"]: r for r in FG.control_matrix()}
    check("both known Settings gaps are recorded", set(FG.SETTINGS_GAPS) ==
          {"history", "memory-learning"}, sorted(FG.SETTINGS_GAPS))
    for fid, gap in FG.SETTINGS_GAPS.items():
        row = by_id.get(fid)
        check(f"{fid} is a real feature", row is not None, fid)
        check(f"{fid}'s typed controls are named", bool(gap.get("controls")), gap)
        for key in gap.get("controls", ()):
            check(f"{fid}: {key} is a real typed setting",
                  key in bool_keys or key in choice_keys, key)
        check(f"{fid}'s gap names the desktop owner",
              gap.get("desktop") in ("setup-ui", "Session B"), gap)
        check(f"{fid}'s gap names the phone owner",
              gap.get("phone") in ("setup-ui", "Session B"), gap)
        check(f"{fid}'s gap says why in plain words", len(str(gap.get("reason") or "")) > 40, gap)
        check(f"{fid}'s matrix row carries the gap",
              row is not None and row.get("settings_gap") == gap, row and row.get("settings_gap"))
    for row in by_id.values():
        if row.get("settings_gap") is None:
            continue
        check(f"{row['id']} is command-controllable despite its Settings gap",
              row["status"] in ("switch", "adjust"), row["status"])


def t_the_matrix_reports_the_switch_and_adjust_counts_honestly():
    """The headline numbers, stated out loud so a change is noticed."""
    rows = FG.control_matrix()
    status = {}
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
    check("the switches are the registry's own count (16 features cover them)",
          status.get("switch", 0) >= 16, status)
    check("the adjust rows are at least the nine known settings places",
          status.get("adjust", 0) >= 9, status)
    check("every feature is classified, none invented",
          sum(status.values()) == len(rows), status)
    check("the open-only rows carry a Settings card",
          all(r["sections"] for r in rows if r["status"] == "open-only"),
          [r["id"] for r in rows if r["status"] == "open-only" and not r["sections"]])
    # The two multi-field gaps named with an owner in this slice's report.
    multi = [r["id"] for r in rows if r["reason_code"] == "multi-field"]
    check("the multi-field gaps are named, not hidden", bool(multi), multi)


# ------------------- 8. every feature, every owner question (2026-10-26) ----
#
# The field test this section exists for: the owner asked for Jarvis to be able
# to talk about ANY feature of the project, in detail. The gap was not one
# feature's row - it was that the fixed-phrase grammar only knew three of the
# nine questions a person asks, and that a handful of names could not be said
# at all. These checks compare against the DATA (features/features.json) and
# the real matcher, never against typed prose, so a new row is covered the day
# it is added.

def _flat(text) -> str:
    """A phrase's own text: quotes flattened, whitespace collapsed, lower-case."""
    return " ".join(str(text).replace('"', "").split()).lower()


#: The ways an answer says how to use or change a row. A PHONE-ONLY control is
#: "changed in the phone's own Settings" rather than "changed at ... on this PC"
#: (F3, 2026-10-26 review): the row's surface wins over the PC-Only label's own
#: words, so both spellings are legitimate answers here.
HOW_WORDS = ("To turn it on or off", "To change it", "more than one switch",
             "no switch of its own", "no on/off switch", "Always On",
             "changed only at", "changed at", "changed in the phone's own Settings",
             "not wired yet")


def _names(row: dict) -> list:
    """Every name a person may use for this row: title, id, aliases."""
    out, seen = [], set()
    for name in [row["title"], row["id"].replace("-", " ")] + list(row.get("aliases") or []):
        key = _flat(name)
        if key and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def t_every_feature_answers_every_owner_question():
    """All 140 rows, all nine questions - by title, by id and by alias.

    This is the completeness check the owner's request needs: it fails for a
    row whose name no phrasing reaches, and for an answer that lost one of the
    facts (name, what, where, asks, apps, how to change it)."""
    misses, thin = [], []
    for row in SOURCE:
        for template, want in OWNER_QUESTIONS:
            allowed = OWNER_QUESTION_EXCEPTIONS.get((row["id"], template), set())
            asked = []
            for name in _names(row):
                phrase = template.format(_flat(name))
                got = match(phrase)
                asked.append((got.name if got is not None else None, phrase))
            hit = next((a for a in asked if a[0] == want), None)
            if hit is None:
                hit = next((a for a in asked if a[0] in allowed), None)
            if hit is None:
                misses.append((row["id"], template.format("<name>"),
                               [a[0] for a in asked[:3]]))
                continue
            if hit[0] != want:
                # An older intent owns this one question for this row; the
                # feature itself is still explained by the other eight (each of
                # which is checked with the same row, above and below).
                continue
            if want == "feature_explain" and template != "tell me about {}":
                # Every explain phrasing routes to ONE renderer, so its answer
                # is checked once per row (below, on the "tell me about" case)
                # rather than six times for the same text.
                continue
            out = say(match(hit[1]))
            text = out.reply if out is not None else ""
            # Each question gets the answer THAT question needs: the explain
            # questions carry every fact, the switch/state/change questions
            # carry their own (where + card + phrase, or the real state), never
            # less than a beginner needs to act.
            if want == "feature_explain":
                required = (
                    ("name", row["title"] in text),
                    ("what", row["what"] in text),
                    ("where", row["where"] in text),
                    ("asks", row["asks"] in text),
                    ("apps", FG.surface_words(row) in text),
                    ("how", any(m in text for m in HOW_WORDS)),
                )
            elif want == "feature_howto":
                required = (
                    ("name", row["title"] in text),
                    ("where", row["where"] in text),
                    ("asks", row["asks"] in text),
                    ("how", any(m in text for m in HOW_WORDS)),
                )
            elif want == "feature_change":
                required = (
                    ("name", row["title"] in text),
                    ("status", "Status:" in text),
                    ("how", any(m in text for m in HOW_WORDS)),
                )
            else:                            # feature_state
                required = (
                    ("name", row["title"] in text),
                    ("state", any(m in text for m in (
                        "right now", "Right now", "no on/off switch",
                        "could not read"))),
                )
            missing = [label for label, present in required if not present]
            if missing:
                thin.append((row["id"], hit[1], missing))
    check("every one of the 140 rows answers all nine owner questions", not misses,
          misses[:8])
    check("...and every answer names the feature, what it does, where it lives, "
          "whether it asks first, and which apps have it", not thin, thin[:8])

    # The same facts for the one answer the model is given, so a model turn and
    # a fixed phrase cannot disagree.
    bad = []
    for row in SOURCE:
        out = FG.explain(row["id"])
        words = str(out.get("words") or "")
        if not out.get("ok") or out.get("kind") != "feature":
            bad.append((row["id"], "not found"))
            continue
        if not any(marker in words for marker in HOW_WORDS):
            bad.append((row["id"], "no way to use or change it"))
        if row["surface"] == "both" and "both apps" not in words:
            bad.append((row["id"], "does not name both apps"))
    check("...and the single answer always says how to use or change it",
          not bad, bad[:8])


def t_can_i_change_answers_and_changes_nothing():
    """'Can I change <feature>?' - the five kinds, and not one setter runs."""
    calls = []
    backup = R.BOOL_SETTINGS
    try:
        R.BOOL_SETTINGS = tuple(
            dataclasses.replace(b, set=lambda on, _k=b.key, **_kw: calls.append(_k))
            for b in R.BOOL_SETTINGS)
        problems = []
        for row in SOURCE:
            got = match(f"can I change {_flat(row['title'])}")
            if got is None or got.name != "feature_change":
                problems.append((row["id"], "intent", got.name if got else None))
                continue
            out = say(got)
            text = out.reply if out is not None else ""
            if "Status:" not in text:
                problems.append((row["id"], "no status", text[:60]))
                continue
            if not any(marker in text for marker in HOW_WORDS):
                problems.append((row["id"], "no how", text[:80]))
        check("every feature says whether and how it can be changed", not problems,
              problems[:8])
        check("...and no answer changed a setting: no setter ran", not calls, calls[:8])
    finally:
        R.BOOL_SETTINGS = backup
    check("...and the real setter table is put back", R.BOOL_SETTINGS is backup)
    # The phrase the answer SUGGESTS must be a phrase that really works: every
    # switch label the read answers can name, said as "turn on/off <label>",
    # must reach that switch (through the registry's own exact name, the
    # feature's own switch phrase, or the honest refusal for several).
    dead = []
    seen = set()
    for row in SOURCE:
        for switch in FG.feature_switches(row):
            key, label = switch["key"], switch["label"]
            if (key, label) in seen:
                continue
            seen.add((key, label))
            for on, word in ((True, "on"), (False, "off")):
                got = match(f"turn {word} {label}")
                name = got.name if got else None
                works = ((name in ("settings_bool", "feature_switch")
                          and got.f.get("key") == key)
                         or name in ("feature_switch_refused", "settings_choice"))
                if not works:
                    dead.append((row["id"], key, label, word, name))
    check("every 'turn on/off <switch>' sentence the answer suggests really resolves",
          not dead, dead[:8])
    expected_keys = {key for mrow in FG.control_matrix()
                     for key in (mrow.get("switch_keys") or [])}
    check("...and every switch the matrix names was covered by that sweep",
          len(seen) == len(expected_keys), (len(seen), len(expected_keys)))
    out = say(match("can I change background learning"))
    check("a plain switch (not a feature row) gets its own honest change answer",
          out is not None and "on/off setting" in out.reply
          and "turn on background learning" in out.reply, out.reply if out else None)


def t_aliases_are_the_rows_own_names():
    """Every alias names ONE row, exactly, and the catalogue carries it."""
    seen = {}
    problems = []
    for row in SOURCE:
        for name in [row["title"], row["id"].replace("-", " ")]:
            seen.setdefault(FG._norm(name), set()).add(row["id"])
        cat = next((r for r in CAT.FEATURES if r["id"] == row["id"]), None)
        if cat is None:
            problems.append((row["id"], "not in the catalogue"))
            continue
        if list(cat.get("aliases") or []) != list(row.get("aliases") or []):
            problems.append((row["id"], "catalogue aliases differ", cat.get("aliases")))
        for alias in row.get("aliases") or []:
            if alias != alias.lower():
                problems.append((row["id"], "alias is not lower case", alias))
            words = FG._norm(alias).split()
            if len(words) == 1 and words[0] in (FG._GENERIC | FG._STOP):
                problems.append((row["id"], "alias is a generic word", alias))
            found = FG.find_exact(alias)
            if found is None or found["id"] != row["id"]:
                problems.append((row["id"], "alias does not find its row", alias,
                                 found and found["id"]))
            key = FG._norm(alias)
            if key in seen and row["id"] not in seen[key]:
                problems.append((row["id"], "alias is another row's name", alias,
                                 sorted(seen[key])))
            seen.setdefault(key, set()).add(row["id"])
    check("every alias names its own row exactly, and only that row", not problems,
          problems[:8])
    # A row's alias is as usable as its title: the same four questions answer.
    bad = []
    for row in SOURCE:
        for alias in row.get("aliases") or []:
            for template in ("tell me about {}", "where is {}", "how do I use {}",
                             "can I change {}"):
                got = match(template.format(_flat(alias)))
                if got is None or got.name not in ("feature_explain", "feature_change"):
                    bad.append((row["id"], alias, template, got.name if got else None))
    check("...and every alias answers the explain, where, use and change questions",
          not bad, bad[:8])


def t_every_one_sided_answer_says_why():
    """No feature is called one-app-only without the row's own reason."""
    problems = []
    for row in SOURCE:
        out = FG.explain(row["id"])
        words = str(out.get("words") or "")
        if row["surface"] == "both":
            if "both apps" not in words or FG.PHONE_FEATURES_PAGE not in words:
                problems.append((row["id"], "a both-apps answer does not name both"))
            continue
        reason = str(row.get("surface_reason") or "")
        if len(reason.split()) < 6:
            problems.append((row["id"], "no surface_reason"))
        line = "PC only" if row["surface"] == "desktop" else "phone only"
        if line not in words or (reason and reason not in words):
            problems.append((row["id"], "the answer does not say why", line))
        if out.get("feature", {}).get("surface_reason") != reason:
            problems.append((row["id"], "the facts lost the reason"))
    check("every one-sided row carries a reason and its answer says it", not problems,
          problems[:8])
    # The rule this enforces was checked by hand when the 19 desktop reasons
    # were written; a row that claims BOTH is never asked for one.
    check("...and a both-apps row is never asked for a reason",
          all(r.get("surface") != "both" for r in SOURCE if r.get("surface_reason")))


def t_the_new_questions_do_not_swallow_other_questions():
    """The nine questions did not turn general questions into feature answers."""
    other = ("how do I use a chainsaw", "how do I use python",
             "where is my file manager", "where did I put my passport",
             "where are my keys", "can I change my password in chrome",
             "where do I change my wifi password",
             "how do I change my wifi password", "how does the weather work",
             "is my oven on", "what is a focus session in psychology",
             "how do I turn on dark mode in chrome",
             "Jarvis, how do I use a chainsaw", "Jarvis, where is my passport",
             "Jarvis, can I change my password")
    for phrase in other:
        got = match(phrase)
        check(f"'{phrase}' is not answered as a feature",
              got is None or got.name not in FEATURE_INTENTS,
              f"got {got.name if got else 'the model'}")
    got = match("where did I put my passport")
    check("'where did I put my passport' keeps the lost-object path",
          got is not None and got.name == "where_put",
          got.name if got else None)
    got = match("where is the prompt coach")
    check("...while 'where is the prompt coach' IS the feature's own answer",
          got is not None and got.name == "feature_explain",
          got.name if got else None)
    for phrase in ("Jarvis, where is the turbo feature",
                   "Jarvis, how do I use the turbo feature",
                   "Jarvis, can I change the turbo feature"):
        got = match(phrase)
        check(f"'{phrase}' says the feature is unknown, never a guess",
              got is not None and got.name == "feature_unknown",
              got.name if got else "the model")


def t_what_can_you_do_still_answers():
    """"What can you do?" is the neighbour these questions must not eat."""
    got = match("what can you do")
    check("'what can you do' is still the sayable answer",
          got is not None and got.name == "sayable_help",
          got.name if got else None)
    out = say(got)
    check("...and it still lists the real sentences",
          out is not None and "Set a timer for 10 minutes." in out.reply,
          out.reply[:120] if out else None)
    # THE OWNER'S OWN SCREENSHOT QUESTION (2026-10-26). "what are you capable
    # of?" matched NOTHING in jarvis_quick.py's fast grammar - the word
    # "capable" appeared nowhere in the module and nowhere in this branch - so
    # it went to the model and could be answered differently every time. It is
    # the same question as "what can you do?", so it is the same fixed list.
    for phrase in ("what are you capable of", "what are you capable of?",
                   "what are you able to do", "what are my capabilities",
                   "what is jarvis capable of", "what can jarvis do"):
        got = match(phrase)
        check(f"the owner's own wording answers with no model: {phrase!r}",
              got is not None and got.name == "sayable_help",
              got.name if got else "the model")
    for phrase in ("what are you capable of", "what are you able to do"):
        out = say(match(phrase))
        check(f"...and {phrase!r} lists the real sentences, not a model's prose",
              out is not None and "Set a timer for 10 minutes." in out.reply,
              out.reply[:120] if out else None)


def t_the_presets_question_reaches_the_guide():
    """The owner's other live question: "where do i change the jarvis presets?"

    It matched no phrase at all, so it went to the model, which told them to
    look in the PC's system settings - a place Jarvis's presets are not.
    "where do I change <x>" is now a where question (the same exact-name gate as
    every other fixed phrase), and the two kinds of preset carry the owner's own
    names as exact aliases on the rows that really own them.
    """
    for phrase, want in (
            ("where do i change the jarvis presets", "focus-presets"),
            ("where do i change presets", "focus-presets"),
            ("tell me about presets", "focus-presets"),
            ("where do i change personality presets", "manner"),
            ("where do i change my personalities", "manner"),
            ("tell me about personalities", "manner")):
        got = match(phrase)
        check(f"{phrase!r} reaches the row that owns it",
              got is not None and got.name == "feature_explain"
              and got.f.get("id") == want,
              (got.name if got else None, got.f if got else None))
    out = say(match("where do i change the jarvis presets"))
    check("...and the answer names the real place, never 'system settings'",
          out is not None and "Settings, Focus presets" in out.reply
          and "system settings" not in out.reply.lower(),
          out.reply[:160] if out else None)
    out = say(match("where do i change personality presets"))
    check("...and the personality presets answer is Settings, How Jarvis talks",
          out is not None and "Settings, How Jarvis talks" in out.reply,
          out.reply[:160] if out else None)
    # The aliases are the row's own words: the catalogue carries them, exactly
    # as it carries every other row's, and the generator refuses a short one.
    by_id = {row["id"]: row for row in SOURCE}
    check("the two preset rows really carry those names",
          by_id["focus-presets"].get("aliases") == ["presets", "jarvis presets"]
          and by_id["manner"].get("aliases") == ["personalities", "personality presets",
                                                 "my personalities"],
          (by_id["focus-presets"].get("aliases"), by_id["manner"].get("aliases")))


def t_a_phone_only_row_is_never_changed_on_this_pc():
    """F3 (2026-10-26 review): five phone-only rows were changed "on this PC".

    `change_words` branched on the five-label mix only, and `_label_from` maps a
    row's reason (pc-only / app-local) to PC-Only without looking at `surface` -
    so phone-notifications, phone-watch, phone-floating, phone-tiles and
    phone-screen-rate answered "It is changed at ... on this PC" for controls
    the PC does not have. The surface now wins in the WORDS, and the
    owner-approved label counts are untouched.
    """
    phone = [row for row in SOURCE if row["surface"] == "phone"]
    check("there are phone-only rows to check", len(phone) >= 5, len(phone))
    bad = []
    for row in phone:
        words = FG.change_words(row)
        if "on this PC" in words:
            bad.append((row["id"], "change_words", words))
        ability = FG.ability_explanation(row)
        if "on this PC" in ability:
            bad.append((row["id"], "ability_explanation", ability))
    check("no phone-only row is ever said to change 'on this PC'", not bad, bad[:8])
    settings_rows = [row for row in phone if FG.label_for(row) in
                     (FG.LABEL_PC_ONLY, FG.LABEL_SETTINGS_ONLY)]
    check("...the five phone controls are the PC-Only-labelled ones",
          len(settings_rows) == 5, [r["id"] for r in settings_rows])
    # Each names its OWN path and says what is true of the PC, in both the change
    # sentence and the whole answer. The PC's side is read from the row's own
    # `surface_reason`: three of the five really have no PC control, and the other
    # two (`phone-floating`, `phone-screen-rate`) name the desktop's own, different
    # control - so denying a PC control would contradict the surface line printed
    # in the same answer (2026-10-26, part B).
    missing = []
    for row in settings_rows:
        where = str(row["where"])
        head, sep, rest = where.partition(",")
        tail = rest.strip() if head.strip().lower() == "settings" and sep else where
        pc_has_its_own = row["id"] in FG.PHONE_PC_COUNTERPART
        for label, words in (("change_words", FG.change_words(row)),
                             ("explain", str(FG.explain(row["id"]).get("words") or ""))):
            if "phone's own Settings" not in words:
                missing.append((row["id"], label, "no phone Settings path", words[:120]))
            if tail.rstrip(".") not in words:
                missing.append((row["id"], label, "does not name its own path", tail))
            if "on this PC" in words:
                missing.append((row["id"], label, "still says on this PC"))
            if pc_has_its_own:
                if "The PC does not have that control" in words:
                    missing.append((row["id"], label,
                                    "denies the PC's own control", words[:120]))
                if "different control" not in words:
                    missing.append((row["id"], label,
                                    "does not name the PC's different control", words[:120]))
            elif "The PC does not have that control" not in words:
                missing.append((row["id"], label,
                                "does not say the PC has no control", words[:120]))
    check("...and each says the phone's own Settings, names its own path, and "
          "says the truth about the PC's own control", not missing, missing[:8])
    # The two rows whose PC has its own, different control are pinned exactly, and
    # the row's own surface_reason must be what says so - the map in the module
    # cannot drift away from the data it was written from.
    for fid, want in FLAT_ROW_SENTENCES.items():
        row = next(r for r in SOURCE if r["id"] == fid)
        check(f"{fid} names the phone's path and the PC's DIFFERENT control",
              FG.change_words(row) == want, FG.change_words(row))
        check(f"...and its own surface reason is what says the PC has one",
              "the desktop's" in FG.surface_words(row), FG.surface_words(row)[:160])
    for row in settings_rows:
        if row["id"] in FG.PHONE_PC_COUNTERPART:
            continue
        check(f"{row['id']}'s surface reason really says the PC has none",
              "the desktop's" not in FG.surface_words(row),
              FG.surface_words(row)[:160])
    # The other three phone rows are abilities, not settings: their sentence must
    # stay the Command-Only one instead of pretending the PC has a control.
    for fid in ("memory-people", "live-camera", "phone-limits"):
        row = next(r for r in SOURCE if r["id"] == fid)
        check(f"{fid} keeps its Command-Only sentence",
              "no switch of its own" in FG.change_words(row),
              FG.change_words(row))


#: The four rows BOTH apps have whose SETTING CONTROL is the PC's, and the exact
#: sentence each now answers "how do I change it?" with (2026-10-26, part B).
#: Pinned word for word so a reword cannot drift what a reviewer checked; the
#: comma-fragment garble they replace read "It is changed at Settings, a new
#: conversation starts after on this PC; the phone says so rather than pretending
#: it changed".
BOTH_PC_ONLY_SENTENCES = {
    "chat-thread": ("Its setting is in Settings, a new conversation starts after. "
                    "It is changed on the PC; the phone has the feature but cannot "
                    "change the PC's setting."),
    "connection": ("Its setting is in Settings, connection. It is changed on the PC; "
                   "the phone has the feature but cannot change the PC's setting."),
    "appearance": ("Its setting is in Settings, appearance. It is changed on the PC; "
                   "the phone has the feature but cannot change the PC's setting."),
    "faces": ("Its setting is in Settings, Appearance. It is changed on the PC; "
              "the phone has the feature but cannot change the PC's setting."),
}
#: The garble shape itself: a Settings path swallowed by " on this PC" in the same
#: clause. It is what `settings_path_words()` produced when a prose `where` was
#: split at its first comma and glued together.
_GARBLED_PATH = re.compile(r"Settings,[^.;]*\s+on this PC")

#: The two phone-only rows whose PC has its own, DIFFERENT control (2026-10-26,
#: part B). Pinned word for word: the row's own surface_reason says the PC has one,
#: so "The PC does not have that control" contradicted the same answer.
FLAT_ROW_SENTENCES = {
    "phone-floating": ("It is changed in the phone's own Settings, Floating Jarvis. "
                       "The PC's floating face is a different control."),
    "phone-screen-rate": ('It is changed in the phone\'s own Settings, Screen refresh '
                          'rate. "Check again" re-reads what the screen settled on. '
                          "The PC's frame-rate setting is the animal's, a different "
                          "control."),
}


def t_the_galaxy_is_both_apps_and_its_answer_says_so():
    """Part B (2026-10-26): the Galaxy row the phone now draws, and its old lie.

    The phone draws a read-only Galaxy picture since PR #869, so the row is
    `surface: "both"` and carries no desktop-only reason. The branch that met
    here had added one - "the memory graph stays off the phone, so the phone has
    no Galaxy view" - which the merged row finally made owner-facing. The answer
    must never carry it again.
    """
    row = FG.row_by_id("galaxy")
    check("the Galaxy row is both apps'", row["surface"] == "both", row["surface"])
    check("...and carries no one-sided reason to contradict it",
          not row.get("surface_reason"), row.get("surface_reason"))
    words = FG.explain_words(row)
    check("...so its answer says both apps and never 'the phone has no Galaxy view'",
          "It is in both apps" in words
          and "the phone has no Galaxy view" not in words, words[:200])
    check("...and describes the phone's picture as read-only",
          "read-only picture" in words and "at most 48 names" in words, words[:200])
    # The row the phone's list draws from is the same row in all three copies of
    # the list; tools/check_feature_list.py is the gate, and this pins the one
    # fact this suite can read: the catalogue the answers use.
    check("...and the catalogue the answers read is the generator's",
          CAT.SOURCE_SHA256 == GEN.load_rows()[1], CAT.SOURCE_SHA256)


def t_the_four_both_rows_name_the_pcs_setting_without_losing_the_phone():
    """Part B (2026-10-26): four rows BOTH apps have read as PC-only settings.

    `_label_from` maps the row's `reason` (app-local / credentials) to PC-Only
    without looking at `surface`, and `change_words` believed the label's own
    words - so chat-thread, connection, appearance and faces said "It is changed
    at Settings, <a comma-split fragment> on this PC; the phone says so rather
    than pretending it changed" for features both apps have. The sentence is now
    built from `surface`: the PC's Settings is named as a place, and the phone is
    not said to lack the feature. The four are pinned exactly.
    """
    both_pc = [row for row in SOURCE if row["surface"] == "both"
               and FG.label_for(row) == FG.LABEL_PC_ONLY]
    check("exactly the four pinned rows are both-apps PC-Only settings",
          [r["id"] for r in both_pc] == list(BOTH_PC_ONLY_SENTENCES),
          [r["id"] for r in both_pc])
    for fid, want in BOTH_PC_ONLY_SENTENCES.items():
        row = FG.row_by_id(fid)
        check(f"{fid} says where its setting is, and does not take the phone's copy away",
              FG.change_words(row) == want, FG.change_words(row))
        ability = FG.ability_explanation(row)
        check(f"{fid} says the same when asked how to turn it on",
              want in ability and "on this PC" not in ability, ability)
        words = FG.explain_words(row)
        check(f"{fid}'s whole answer carries that sentence and both apps",
              want in words and "It is in both apps" in words, words[:200])
    # No BOTH-APPS row may carry the garble shape, in either the change sentence
    # or the whole explain answer. (A desktop-only row may still say "on this PC" -
    # that is true for it - but its place is never swallowed by that phrase.)
    bad = []
    for row in SOURCE:
        if row["surface"] != "both":
            continue
        for label, words in (("change_words", FG.change_words(row)),
                             ("explain", FG.explain_words(row))):
            if _GARBLED_PATH.search(words):
                bad.append((row["id"], label, words[:160]))
    check("no both-apps answer glues a Settings place to ' on this PC' any more",
          not bad, bad[:8])
    # A both-apps row must never claim the phone has no control at all.
    denied = [(row["id"], FG.change_words(row)) for row in SOURCE
              if row["surface"] == "both"
              and re.search(r"phone (does not|has no|cannot)\b", FG.change_words(row))
              and "phone has the feature" not in FG.change_words(row)]
    check("...and no both-apps row tells the owner the phone lacks the feature",
          not denied, denied[:8])


def t_a_phone_only_status_line_agrees_with_its_surface():
    """Part B (2026-10-26): the Status line of a phone-only row said "PC-Only".

    The five phone controls carry the PC-Only label because the phone is the only
    app with the control; `label_for()` reads that from the row's reason and
    never looks at `surface`, so the Status line contradicted the "It is on the
    phone only" line in the same answer. `status_label()` derives the Status line
    from `surface` for DISPLAY only. `label_for()`, the contracts' counts and
    both apps' directories are untouched - the phone-side UI label is a separate
    change, recorded in the PR body.
    """
    phone = [row for row in SOURCE if row["surface"] == "phone"]
    check("there are phone-only rows to check", len(phone) >= 5, len(phone))
    bad = []
    for row in SOURCE:
        status = FG.status_label(row)
        words = FG.explain_words(row)
        if f"Status: {status}." not in words:
            bad.append((row["id"], "the Status line is not the derived label", status))
        if row["surface"] == "phone":
            if FG.LABEL_PC_ONLY in words or FG.LABEL_SETTINGS_ONLY in words:
                bad.append((row["id"], "a PC label inside a phone-only answer", words[:160]))
            if status == FG.PHONE_ONLY_DISPLAY_LABEL:
                if "phone's own Settings" not in words or "It is on the phone only" not in words:
                    bad.append((row["id"], "the Status disagrees with the change sentence",
                                words[:160]))
            elif status != FG.label_for(row):
                bad.append((row["id"], "a phone row's label was reworded for no reason",
                            status))
        elif status != FG.label_for(row):
            bad.append((row["id"], "a non-phone row was reworded", status))
    check("every row's Status line agrees with its surface", not bad, bad[:8])
    five = [row for row in phone
            if FG.label_for(row) in (FG.LABEL_PC_ONLY, FG.LABEL_SETTINGS_ONLY)]
    check("...the five phone controls are the ones this rewording covers",
          len(five) == 5, [r["id"] for r in five])
    check("...and each says Phone-Only, with the phone's Settings named",
          all(FG.status_label(r) == FG.PHONE_ONLY_DISPLAY_LABEL for r in five),
          [FG.status_label(r) for r in five])
    # The reword is display-only: the contract label, the directory data both
    # apps render and the counts tools/check_feature_controls.py pins are all
    # exactly as approved.
    directory = {r["id"]: r for r in FG.abilities_directory()}
    check("...and the directory's own label and counts are untouched",
          all(directory[r["id"]]["label"] == FG.LABEL_PC_ONLY for r in five)
          and all(FG.label_for(r) == FG.LABEL_PC_ONLY for r in five),
          [(r["id"], directory[r["id"]]["label"]) for r in five])
    # "can I change it?" says the same thing as "tell me about it".
    out = FG.change("phone notifications")
    check("...and 'can I change it?' carries the same Status line",
          out.get("ok") and f"Status: {FG.PHONE_ONLY_DISPLAY_LABEL}." in str(out.get("words")),
          str(out.get("words"))[:160])


def t_a_settings_path_is_a_place_not_a_sentence():
    """Part B (2026-10-26): `where` is written for a person, not to be split.

    `settings_path_words()` answered "Settings, <fragment>" for rows whose
    `where` is prose: the place was taken from a comma-split of the sentence and
    then glued into "on this PC". A place is now READ, never split blindly: the
    opening "Settings, <Place>" is taken only up to its own stop, and only when
    it is path-shaped; anything else falls back to the directory, which every
    feature really is listed at.
    """
    check("a plain place is a path", FG._path_shaped("Connection"),
          FG._path_shaped("Connection"))
    check("a place that opens like a clause is not",
          not FG._path_shaped("the first card on the page"),
          FG._path_shaped("the first card on the page"))
    check("...and neither is a clause with a comma in it",
          not FG._path_shaped("Appearance, then Open Faces on the PC"),
          FG._path_shaped("Appearance, then Open Faces on the PC"))
    check("the row's own prose gives up its first place only",
          FG._where_place({"where": 'Settings, Appearance, then Open Faces on the PC. '
                                    'On the phone, Appearance.'}) == "Appearance",
          FG._where_place({"where": 'Settings, Appearance, then Open Faces on the PC. '
                                    'On the phone, Appearance.'}))
    check("...and a row that opens with prose yields nothing",
          FG._where_place({"where": "Scroll the Jarvis bar. Settings has it."}) == "",
          FG._where_place({"where": "Scroll the Jarvis bar. Settings has it."}))
    for fid, want in (("chat-thread", "Settings, a new conversation starts after"),
                      ("connection", "Settings, connection"),
                      ("appearance", "Settings, appearance"),
                      ("faces", "Settings, Appearance")):
        got = FG.settings_path_words(FG.row_by_id(fid))
        check(f"{fid}'s Settings place is a real path", got == want, got)
    bad = []
    for row in SOURCE:
        path = FG.settings_path_words(row)
        if not path.startswith("Settings, "):
            bad.append((row["id"], path, "not a Settings path"))
        if path.rstrip().endswith(".") or any(ch in path for ch in ";:!?"):
            bad.append((row["id"], path, "prose punctuation in a path"))
        if " on this PC" in path:
            bad.append((row["id"], path, "the old garble is back"))
    check("every row's Settings place is a path, not a sentence", not bad, bad[:8])


def t_how_do_i_change_asks_the_same_question_as_where_do_i_change():
    """Part B (2026-10-26): "how do i change <x>" is an alternative, gated the same.

    The owner's live question was "where do i change the presets?"; the same
    question the other way round must reach the same ROW, through the row's own
    aliases ("presets" is focus-presets' alias, "personality presets" is
    manner's), and get the full answer - which ends with the way to change it.
    The gate is unchanged, so a general "how do i change my password" still falls
    through to the model instead of being hijacked.
    """
    pairs = (("how do i change the presets", "where do i change presets",
              "focus-presets"),
             ("how do i change the jarvis presets",
              "where do i change the jarvis presets", "focus-presets"),
             ("how do i change the personality presets",
              "where do i change the personality presets", "manner"),
             ("how do i change my personalities",
              "where do i change my personalities", "manner"))
    for how, where, fid in pairs:
        got_how, got_where = match(how), match(where)
        check(f'"{how}" reaches {fid}, exactly as "{where}" does',
              got_how is not None and got_where is not None
              and got_how.name == got_where.name == "feature_explain"
              and got_how.f.get("id") == got_where.f.get("id") == fid,
              (got_how, got_where))
    out = say(match("how do i change the presets"))
    check("...and the answer still says how to change it",
          out is not None and any(marker in out.reply for marker in HOW_WORDS),
          out.reply[:200] if out else None)
    for phrase in ("how do i change my password",
                   "how do i change my wifi password",
                   "Jarvis, how do i change my password",
                   "how do i change my password in chrome",
                   "how do i change the layout presets"):
        got = match(phrase)
        check(f'"{phrase}" is not hijacked by the feature list', got is None, got)
    # THE ONE THE RULING MOVED (Q6 Step A, 2026-10-26). "voice speed" is a
    # registry CHOICE_SETTING, not a feature row; the settings-name fallback
    # now answers it with the real Settings place and a real phrase instead of
    # handing it to the model. It is still NOT a feature answer, which is what
    # this test is about.
    got = match("how do i change the voice speed")
    check('"how do i change the voice speed" reaches the settings registry, '
          "not the feature list",
          got is not None and got.name == "setting_explain"
          and got.f.get("kind") == "choice"
          and got.f.get("key") == "voice_speed", got)
    for phrase, fid in (("can i change the presets", "focus-presets"),
                        ("how can i adjust the presets", "focus-presets"),
                        ("is the prompt coach adjustable", "prompt-coach")):
        got = match(phrase)
        check(f'"{phrase}" still reaches the change lane',
              got is not None and got.name == "feature_change"
              and got.f.get("id") == fid, got)


def t_the_matrix_keeps_every_typed_phrase():
    """The build's own re-entrancy: a phrase asked mid-build is not lost.

    `control_matrix()` calls the real matcher ~500 times, and a "turn on
    <ability>" phrase reaches back into `label_for` -> `_matrix()`. Without the
    guard that rebuilt the table from inside its own build, the nested ask died
    on the recursion limit and `_quick_intent` swallowed it - four rows (How
    Jarvis talks, Floating Jarvis, Starting Jarvis for you, What Jarvis can
    reach) lost their typed phrases. Measured on this branch before the fix:
    4 of 140 rows had an empty on/off phrase; after: 0.
    """
    FG._MATRIX_CACHE = None
    rows = FG.control_matrix()
    missing = [(r["id"], key) for r in rows
               for key in ("on_phrase", "off_phrase", "how_to_phrase")
               if not r[key]["intent"]]
    check("every feature keeps its on, off and how-to phrases", not missing,
          missing[:8])
    check("...and the build left no half-built state",
          FG._MATRIX_BUILDING is False and FG._MATRIX_CACHE is not None)
    FG._MATRIX_CACHE = None
    FG._MATRIX_BUILDING = True
    try:
        check("a nested ask during the build gets an empty table, not a recursion",
              FG._matrix() == [])
    finally:
        FG._MATRIX_BUILDING = False
        FG._MATRIX_CACHE = None
    check("...and the next build is complete again",
          len(FG.control_matrix()) == len(SOURCE))
    # The four names that carry "Jarvis" in the feature's OWN name, not as an
    # address: each must reach a real change path for "turn on". A title that is
    # also one of the registry's exact switch names legitimately takes the older
    # settings_bool path - the SAME switch, so it is accepted only when the key
    # is one this row names.
    for row in SOURCE:
        if "jarvis" not in row["title"].lower():
            continue
        got = match(f"turn on {_flat(row['title'])}")
        mine = {s.key for s in FG.switches_for(row)}
        ok = got is not None and (
            got.name in ("feature_switch", "feature_switch_refused")
            or (got.name == "settings_bool" and got.f.get("key") in mine))
        check(f"'{row['title']}' can be turned on by its own name",
              ok, (got.name if got else None, got.f if got else None))


if __name__ == "__main__":
    for fn in (t_every_row_is_looked_up_and_its_facts_equal_the_json,
               t_unknown_and_ambiguous_never_guess,
               t_every_switch_has_a_state_reader,
               t_current_on_off_is_read_from_the_owners_module,
               t_state_never_claims_what_it_did_not_read,
               t_the_fixed_phrases_answer_the_right_intent,
               t_the_fixed_phrases_do_not_swallow_other_questions,
               t_the_phrase_gate_requires_an_exact_name_or_jarvis_context,
               t_answering_works_without_a_model_and_says_the_facts,
               t_cloud_sync_is_answered_without_a_model,
               t_switching_uses_the_real_setter_and_reports_its_outcome,
               t_a_feature_with_several_switches_changes_nothing,
               t_the_tool_is_listed_short_and_read_only,
               t_the_tool_returns_the_exact_facts,
               t_the_documented_listing_call_is_never_refused,
               t_a_model_turn_can_list_the_groups_with_no_refusal,
               t_a_model_turn_gets_the_facts_with_no_card,
               t_what_can_i_change_is_still_the_exact_answer,
               t_every_feature_has_a_matrix_row_and_a_reason,
               t_the_matrix_tables_link_to_real_controls,
               t_the_matrix_reports_the_switch_and_adjust_counts_honestly,
               t_settings_gaps_are_real_named_and_owned,
               t_the_five_owner_labels_are_exact_and_every_feature_has_one,
               t_turning_on_an_ability_gets_a_deterministic_honest_answer,
               t_abilities_directory_labels_are_consistent_with_reason_codes,
               t_every_feature_answers_every_owner_question,
               t_can_i_change_answers_and_changes_nothing,
               t_aliases_are_the_rows_own_names,
               t_every_one_sided_answer_says_why,
               t_the_new_questions_do_not_swallow_other_questions,
               t_what_can_you_do_still_answers,
               t_the_presets_question_reaches_the_guide,
               t_a_phone_only_row_is_never_changed_on_this_pc,
               t_the_galaxy_is_both_apps_and_its_answer_says_so,
               t_the_four_both_rows_name_the_pcs_setting_without_losing_the_phone,
               t_a_phone_only_status_line_agrees_with_its_surface,
               t_a_settings_path_is_a_place_not_a_sentence,
               t_how_do_i_change_asks_the_same_question_as_where_do_i_change,
               t_the_matrix_keeps_every_typed_phrase):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)


# -------------------------------------------- 7. the command-side matrix (2026-10-22)
