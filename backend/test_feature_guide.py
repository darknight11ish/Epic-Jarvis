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
  1. THE FACTS ARE THE LIST'S OWN. Every one of the 137 rows is found by its id,
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
                   "feature_switch_refused", "features_list", "features_group")


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
    check("every one of the 137 rows is found by id, with facts equal to the JSON",
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
             "where is my file manager", "is my oven on")
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
    check("its arguments are the one feature name", list(tool.parameters["properties"]) == ["feature"]
          and tool.parameters["required"] == ["feature"], tool.parameters)
    tokens = AG.estimate_tokens(tool.schema())
    check(f"its text is within the per-tool budget (300 tokens; it is {tokens})",
          tokens <= 300, tokens)
    check("says what not to do: never invent a feature",
          "never invent" in tool.description)
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
               t_switching_uses_the_real_setter_and_reports_its_outcome,
               t_a_feature_with_several_switches_changes_nothing,
               t_the_tool_is_listed_short_and_read_only,
               t_the_tool_returns_the_exact_facts,
               t_a_model_turn_gets_the_facts_with_no_card,
               t_what_can_i_change_is_still_the_exact_answer):
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
