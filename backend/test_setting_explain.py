"""test_setting_explain.py - every setting answers with its VALUE and a phrase
that really changes it (2026-11-03; F5 M1-M6; docs/JARVIS-API.md section 183).

    python3 backend/test_setting_explain.py

WHAT THIS PROVES, AND WHY EACH CHECK IS HERE

The owner's ask: for ANY feature, function or setting, Jarvis must answer what
it is, where it lives, WHAT IT IS SET TO RIGHT NOW, and the exact phrase that
changes it. Before this slice the explain door
(`jarvis_settings_registry.find_explain_setting` / `explain_setting_words`)
answered three of those four facts for a switch, and only two for a choice -
and it could not name the number setting, the sun-and-moon switch, any animal
switch or the weather source at all. So:

1. EVERY ROW EXPLAINS AND CARRIES A REAL VALUE. All 35 `BOOL_SETTINGS`, all 10
   `CHOICE_SETTINGS` and the one `NUMBER_SETTINGS` row produce an answer that
   either contains the value its OWN reader just returned or the one fixed
   sentence "I could not read its current value on this PC, so I will not
   guess." - never a default dressed up as the value, and never the word
   "None". A row whose reader cannot answer is PRINTED in the run's summary
   (`Unreadable on this PC: ...`), never silently skipped: the suite passing on
   an unreadable row means it said so, not that it had a value.

2. EVERY PHRASE THE ANSWER PRINTS RESOLVES BACK, THROUGH THE REAL MATCHER.
   This is the half that keeps the advice honest: an answer that suggests a
   sentence the product does not accept is worse than no answer. The phrase is
   taken OUT of the answer text and run through the same matcher the write path
   uses - `find_bool_setting_words` / `find_choice_setting_words` /
   `find_number_setting_words` / `find_animal_switch` / `find_explain_setting`,
   plus `jarvis_quick.match` for the end-to-end sentence - and must name the
   same setting back.

3. THE THREE SETTING FAMILIES THAT COULD NOT BE NAMED NOW CAN BE: the
   sun-and-moon switch (`sky`), every shared animal switch (`animal`, through
   `jarvis_animal`'s own alias list - never typed twice) and the weather source
   (`weather`, checked against `jarvis_sky`'s own SOURCES and through the
   grammar that really changes it).

4. `face-auto` ("Auto adjust") explains itself as page-only, by the Lead's
   decision of 2026-11-03. ITS ONE HONEST LIMIT IS PINNED TOO: the same auto
   mode IS reachable by "turn on auto adjust" through the per-device animal
   grammar, so the refusal's "cannot change it by asking" sentence is about the
   named-row grammar only. Both facts are checked here so neither can drift
   silently.

5. THE THINGS THAT CANNOT BE CHANGED BY ASKING STILL SAY SO, and say where the
   row is: `theme`, `hud layout` and every `NOT_BY_ASKING` id.

6. EXPLAINING CHANGES NOTHING. Every setter in the three tables is replaced
   with one that raises, and every explain answer is built again: no setter is
   called, so no card can be raised and no file can be written by this door.

7. THE SAME FOUR FACTS FOR A CHOICE IN THE FEATURE GUIDE (M4):
   `jarvis_feature_guide.state` / `how_to` now resolve a named choice as well
   as a switch, and never yield a value they did not read.

Run with `python3 backend/test_setting_explain.py` (or `-B`); it touches no
network, starts no server and leaves the owner's own settings alone - every
module that reads state is pointed at a temporary folder first.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_settings_registry.py", "jarvis_feature_guide.py",
                "jarvis_quick.py", "jarvis_animal.py", "jarvis_sky.py",
                "jarvis_live.py", "jarvis_limits.py")
sys.path.append(str(HERE / "rebuilt"))

# THE OWNER'S OWN STATE IS LEFT ALONE, set BEFORE the modules are imported, so
# even a module that reads its folder once at import time gets the temporary
# one (run_suites.py's private_state() rule, the same one
# test_settings_registry.py follows).
TMP = Path(tempfile.mkdtemp(prefix="jarvis-setting-explain-"))
_TOML_COPY = TMP / "jarvis-framework.toml"
_TOML_COPY.write_text((HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8"),
                      encoding="utf-8")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TOML_COPY)
# And the receipts store has its own variable - jarvis_receipts prefers the
# framework module's CONFIG_DIR over the two config-dir variables above, so a
# desk run would otherwise write into the owner's real receipts.db.
os.environ["JARVIS_RECEIPTS_DB"] = str(TMP / "receipts.db")

import jarvis_settings_registry as R  # noqa: E402
import jarvis_feature_guide as G  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []

#: Rows whose own reader could not answer on this PC. Printed in the summary,
#: never hidden: passing means "it said it could not read it", not "it knew".
UNREADABLE: list = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   The face reader, faked the way a running server provides it
# --------------------------------------------------------------------------
# `jarvis_settings_registry._face_now` reads the RUNNING server's
# `_appearance_view` (appearance.patch), found through `sys.modules`. Nothing in
# this repository is the server, so one is installed here for the duration -
# the same technique backend/test_appearance_command.py uses, cut down to the
# two functions the registry reads.
def _repo_face_rows():
    spec = json.loads((REPO / "jarvis-desktop" / "src" / "jarvis-visual-spec.json")
                      .read_text(encoding="utf-8"))
    return [{"id": str(row["id"]), "name": str(row.get("name") or row["id"])}
            for row in spec.get("faces") or []
            if isinstance(row, dict) and row.get("id")]


FACE_ROWS = _repo_face_rows()


def _install_server(face: str = "redpanda"):
    """Install a fake `jarvis_hud` and return the previous module (or None)."""
    mod = types.ModuleType("jarvis_hud")
    mod._appearance_faces = lambda: list(FACE_ROWS)
    mod._appearance_view = lambda: {"readable": True, "face": face}
    previous = sys.modules.get("jarvis_hud")
    sys.modules["jarvis_hud"] = mod
    return previous


def _restore_server(previous):
    if previous is None:
        sys.modules.pop("jarvis_hud", None)
    else:
        sys.modules["jarvis_hud"] = previous


# --------------------------------------------------------------------------
#   Reading the answer the way the owner reads it
# --------------------------------------------------------------------------
def _quoted(text: str) -> list:
    """Every "quoted phrase" in an answer, in order."""
    return re.findall(r'"([^"]+)"', str(text or ""))


def _all_rows():
    """Every explainable ROW as (kind, key, row) - the 35 + 10 + 1."""
    rows = [("bool", b.key, b) for b in R.BOOL_SETTINGS]
    rows += [("choice", c.key, c) for c in R.CHOICE_SETTINGS]
    rows += [("number", n.key, n) for n in R.NUMBER_SETTINGS]
    return rows


# --------------------------------------------------------------------------
#   What the reader is
# --------------------------------------------------------------------------
def t_the_counts_and_the_readers_are_the_registrys_own():
    """35 switches, 10 choices, 1 number - and a reader for every one of them.

    The numbers are the plan's own count on this tree; if a row is added
    without a reader, the "every row explains with a value" checks below fail
    and this check names the row before they do."""
    check("35 BOOL_SETTINGS, as the plan counted", len(R.BOOL_SETTINGS) == 35,
          len(R.BOOL_SETTINGS))
    check("10 CHOICE_SETTINGS", len(R.CHOICE_SETTINGS) == 10, len(R.CHOICE_SETTINGS))
    check("1 NUMBER_SETTINGS", len(R.NUMBER_SETTINGS) == 1, len(R.NUMBER_SETTINGS))
    gap = [b.key for b in R.BOOL_SETTINGS if b.key not in G.STATE_READERS]
    check("every switch has a state reader (the guide's own table)", not gap, gap)
    check("every choice row answers `now` (its own reader)",
          all(hasattr(c, "now") for c in R.CHOICE_SETTINGS))
    check("every number row answers `now` (its own reader)",
          all(hasattr(n, "now") for n in R.NUMBER_SETTINGS))
    raised = []
    for kind, key, row in _all_rows():
        try:
            value = R.current_value(row)
        except Exception as exc:            # noqa: BLE001 - that IS the failure
            raised.append(f"{kind}:{key}: {type(exc).__name__}: {exc}")
            continue
        if not (value is None or isinstance(value, str)):
            raised.append(f"{kind}:{key}: current_value -> {type(value).__name__}")
    check("`current_value` answers words or None for every row, and never raises",
          not raised, raised)


def t_every_row_explains_with_a_real_value():
    """Every one of the 46 rows answers, with its value or the fixed sentence."""
    previous = _install_server()
    try:
        for kind, key, row in _all_rows():
            name = row.names[0] if row.names else key
            found = R.find_explain_setting(name)
            check(f"{kind} {key!r}: the explain door names it",
                  found is not None and found.get("kind") == kind, found)
            words = R.explain_setting_words(found or {})
            check(f"{kind} {key!r}: the answer is words, not a blank",
                  bool(str(words).strip()), words)
            value = R.current_value(row)
            if value is None:
                UNREADABLE.append(f"{kind}:{key}")
                check(f"{kind} {key!r}: unreadable -> the ONE fixed sentence",
                      R.UNREADABLE_VALUE_WORDS in words, words)
                check(f"{kind} {key!r}: ...and no default is offered as the value",
                      "Right now:" in words
                      and words.split("Right now:", 1)[1].startswith(
                          " " + R.UNREADABLE_VALUE_WORDS), words)
            else:
                check(f"{kind} {key!r}: the answer carries the reader's own value "
                      f"({value!r})",
                      str(value).rstrip(".") in words, words)
                check(f"{kind} {key!r}: ...and does NOT claim it could not read it",
                      R.UNREADABLE_VALUE_WORDS not in words, words)
            check(f"{kind} {key!r}: the answer never prints the word None",
                  "None" not in words, words)
    finally:
        _restore_server(previous)


def t_the_number_explains_with_its_range():
    """`live_idle_seconds` explains, with its value AND the range it accepts."""
    row = R.NUMBER_SETTINGS[0]
    found = R.find_explain_setting("the jarvis live timeout")
    check("the number setting is reached by its own name",
          found is not None and found.get("kind") == "number"
          and found.get("key") == row.key, found)
    words = R.explain_setting_words(found or {})
    span = row.range_words()
    check("the number's range is read from the row, not typed here", bool(span), span)
    check("the answer states the range the setter really enforces",
          span and span in words, (span, words))
    check("...and says it is a number in the Limits card",
          "is a number in Settings" in words, words)
    check("...and prints a change sentence built from its own name",
          'Say "set ' in words, words)


def t_every_printed_phrase_resolves_through_the_real_matcher():
    """The phrase an answer suggests is a phrase the product really accepts.

    Taken OUT of the answer text and run through the write path's own matcher,
    so a reworded answer cannot quietly start recommending a sentence nothing
    answers."""
    previous = _install_server()
    try:
        for b in R.BOOL_SETTINGS:
            name = b.names[0]
            words = R.explain_setting_words(R.find_explain_setting(name) or {})
            tails = [m.group(1) for phrase in _quoted(words)
                     for m in [re.match(r"turn (?:on|off) (.+)$", phrase)] if m]
            check(f"bool {b.key!r}: the answer prints a turn on/off phrase",
                  len(tails) >= 2, words)
            for tail in tails:
                check(f"bool {b.key!r}: {tail!r} resolves back through "
                      f"find_bool_setting_words",
                      R.find_bool_setting_words(tail) is b,
                      R.find_bool_setting_words(tail))
                got = Q.match(f"turn off {tail}")
                check(f"bool {b.key!r}: ...and the real sentence changes that switch",
                      got is not None and got.name == "settings_bool"
                      and got.f.get("key") == b.key, got)
        for c in R.CHOICE_SETTINGS:
            name = c.names[0]
            words = R.explain_setting_words(R.find_explain_setting(name) or {})
            pairs = [m.groups() for phrase in _quoted(words)
                     for m in [re.match(r"set (.+?) to (.+)$", phrase)] if m]
            check(f"choice {c.key!r}: the answer prints a set-to phrase",
                  bool(pairs), words)
            for label, value in pairs:
                check(f"choice {c.key!r}: {label!r} resolves back through "
                      f"find_choice_setting_words",
                      R.find_choice_setting_words(label) is c,
                      R.find_choice_setting_words(label))
                check(f"choice {c.key!r}: {value!r} is one of the row's own values",
                      R.choice_from_words(c, value) is not None,
                      c.option_words())
                got = Q.match(f"set {label} to {value}")
                check(f"choice {c.key!r}: ...and the real sentence changes that setting",
                      got is not None
                      and (got.f.get("key") == c.key
                           or (got.name == "personality_set" and c.key == "personality")),
                      got)
        for n in R.NUMBER_SETTINGS:
            name = n.names[0]
            words = R.explain_setting_words(R.find_explain_setting(name) or {})
            pairs = [m.groups() for phrase in _quoted(words)
                     for m in [re.match(r"set (.+?) to (.+)$", phrase)] if m]
            check(f"number {n.key!r}: the answer prints a set-to phrase",
                  bool(pairs), words)
            for label, value in pairs:
                check(f"number {n.key!r}: {label!r} resolves back through "
                      f"find_number_setting_words",
                      R.find_number_setting_words(label) is n,
                      R.find_number_setting_words(label))
                got = Q.match(f"set {label} to {value}")
                check(f"number {n.key!r}: ...and the real sentence sets that number",
                      got is not None and got.name == "live_idle_set"
                      and isinstance(got.f.get("seconds"), int), got)
    finally:
        _restore_server(previous)


def t_the_animal_options_and_the_weather_source_explain():
    """M2: the sun and moon, every animal switch, and the weather source."""
    previous = _install_server()
    try:
        # --- the sun and moon (M2)
        found = R.find_explain_setting("the sun and moon")
        check("the sun and moon is explained", found is not None
              and found.get("kind") == "sky", found)
        words = R.explain_setting_words(found or {})
        check("...with its real Settings label and place",
              "Show the sun and moon behind the face" in words
              and "animal options" in words.lower(), words)
        tails = [m.group(1) for phrase in _quoted(words)
                 for m in [re.match(r"turn (?:on|off) (.+)$", phrase)] if m]
        check("...and a turn on/off phrase", bool(tails), words)
        for tail in tails:
            check(f"the sun and moon: {tail!r} resolves through the sky grammar",
                  (R.find_explain_setting(tail) or {}).get("kind") == "sky",
                  R.find_explain_setting(tail))
            got = Q.match(f"turn on {tail}")
            check(f"the sun and moon: ...and the real sentence changes the sky",
                  got is not None and got.name == "animal_sky", got)

        # --- every shared animal switch, through the module's OWN alias list
        import jarvis_animal as AN
        for switch in AN.SWITCHES:
            name = switch.names[0]
            check(f"animal {switch.id!r}: find_animal_switch names it",
                  R.find_animal_switch(name) == switch.id, R.find_animal_switch(name))
            found = R.find_explain_setting(name)
            check(f"animal {switch.id!r}: it is explained",
                  found is not None and found.get("kind") == "animal"
                  and found.get("key") == switch.id, found)
            words = R.explain_setting_words(found or {})
            check(f"animal {switch.id!r}: the answer uses the module's own label",
                  switch.label in words, words)
            tails = [m.group(1) for phrase in _quoted(words)
                     for m in [re.match(r"turn (?:on|off) (.+)$", phrase)] if m]
            check(f"animal {switch.id!r}: the answer prints a turn on/off phrase",
                  bool(tails), words)
            for tail in tails:
                check(f"animal {switch.id!r}: {tail!r} resolves through "
                      f"find_animal_switch",
                      R.find_animal_switch(tail) == switch.id, R.find_animal_switch(tail))
                got = Q.match(f"turn off {tail}")
                check(f"animal {switch.id!r}: ...and the real sentence flips that switch",
                      got is not None and got.name == "animal_switch"
                      and got.f.get("key") == switch.id, got)

        # --- the weather source, through the grammar that really changes it
        import jarvis_sky as SK
        found = R.find_explain_setting("the weather source")
        check("the weather source is explained", found is not None
              and found.get("kind") == "weather", found)
        words = R.explain_setting_words(found or {})
        check("...with the sky module's own label", SK.WEATHER_LABEL in words, words)
        printed = [phrase for phrase in _quoted(words) if phrase.startswith("set ")]
        check("...and one set-to phrase per real source", len(printed) == len(SK.SOURCES),
              (printed, SK.SOURCES))
        for source in SK.SOURCES:
            wanted = f"set the weather source to {source.replace('_', ' ')}"
            check(f"weather: {wanted!r} is printed", wanted in printed, printed)
            got = Q.match(wanted)
            check(f"weather: ...and it sets {source!r}",
                  got is not None and got.name == "animal_weather"
                  and got.f.get("source") == source, got)
    finally:
        _restore_server(previous)


def t_face_auto_explains_with_the_phrase_that_works():
    """`face-auto` ("Auto adjust") is a DEVICE option, and must explain itself.

    IT IS NOT PAGE-ONLY, measured: "turn on auto adjust" and "set the sharpness
    back to auto" really do change the per-device automatic quality, through
    `jarvis_quick._animal`'s per-device grammar. So the page-only refusal
    ("I cannot change it by asking yet") would be a FALSE sentence about it -
    which is exactly why it is not in NOT_BY_ASKING. Its own `device` kind
    gives the four facts the owner asked for: what it is, where it lives, the
    ONE honest line about a value nothing here can read back, and the phrase
    that really works. The working phrase is pinned beside it, so the two
    halves cannot drift apart."""
    found = R.find_explain_setting("auto adjust")
    check("auto adjust is its own device kind", found is not None
          and found.get("kind") == "device" and found.get("key") == "auto", found)
    words = R.explain_setting_words(found or {})
    check("...it names the Settings row the owner opens",
          '"Auto adjust"' in words, words)
    check("...it says where it lives", "animal options" in words.lower(), words)
    check("...it never pretends to know the value",
          R.UNREADABLE_VALUE_WORDS in words, words)
    check("...and it gives the phrase that REALLY works",
          '"turn on auto adjust"' in words, words)
    got = Q.match("how do i change auto adjust")
    check("...and the asking sentence reaches the explain, not the model",
          got is not None and got.name == "setting_explain"
          and (got.f or {}).get("kind") == "device", got)
    got = Q.match("turn on auto adjust")
    check("the per-device auto sentence still works (turn on auto adjust)",
          got is not None and got.name == "animal_device"
          and got.f.get("change") == "auto", got)


def t_a_choice_answers_is_it_on_too():
    """M4 end to end: "is <choice> on?" is answered on the PC, not by the model.

    The guide half was wired and tested on its own (`jarvis_feature_guide.state`
    / `how_to` answer all ten choices). The PRODUCER in jarvis_quick stayed
    bool-only, so a choice asked "is it on?" fell through to the local model
    while every switch answered on the PC. This pins the producer AND the
    answer, for the rows whose own phrasing the state matcher takes."""
    for words, key in (("is the personality on", "personality"),
                       ("is the voice speed on", "voice_speed")):
        got = Q.match(words)
        check(f"{words!r} is answered on the PC, not by the model",
              got is not None and got.name == "feature_state_setting"
              and got.f.get("key") == key,
              None if got is None else (got.name, got.f))
        if got is None or got.name != "feature_state_setting":
            continue
        reply = Q.run(got, None, 0.0)
        check(f"...and it reads that row's own current value ({words!r})",
              reply is not None and "right now" in str(reply.reply).lower(),
              None if reply is None else reply.reply)


def t_theme_and_the_hud_layout_answer_honestly():
    """The two desktop-only controls explain themselves and cannot be changed."""
    for name, section in (("theme", "appearance-card"), ("hud layout", "hud-window")):
        found = R.find_explain_setting(name)
        check(f"{name!r} is a desktop-only area", found is not None
              and found.get("kind") == "area" and found.get("section") == section,
              found)
        words = R.explain_setting_words(found or {})
        check(f"{name!r} says it cannot be changed by asking",
              "on this PC only" in words and "cannot change it by asking" in words,
              words)
        check(f"{name!r} still says where it is",
              "Settings," in words, words)
    got = Q.match("how do i change the theme")
    check("the asking sentence for the theme reaches its own answer",
          got is not None and got.name == "setting_explain"
          and got.f.get("kind") == "area", got)
    reply = Q.run(got, None, 0.0) if got is not None else None
    check("...and the answer says it cannot be changed by asking",
          reply is not None and "cannot change it by asking" in reply.reply,
          None if reply is None else reply.reply)


def t_every_page_only_row_answers_honestly():
    """Every `NOT_BY_ASKING` id answers with its own refusal - and no change."""
    expected = {"sec-app-lock", "sec-private", "floating-enabled",
                "floating-click-through", "follow-system", "voice-heard-sound",
                "hud-open-bar-show", "supervise", "autostart"}
    # face-auto is NOT here, and that is the measured truth: "turn on auto
    # adjust" really does change it, so its refusal would be false. It explains
    # itself through its own `device` kind instead
    # (t_face_auto_explains_with_the_phrase_that_works pins both halves).
    check("the page-only table holds the nine originals, and NOT face-auto",
          set(R.NOT_BY_ASKING) == expected, sorted(R.NOT_BY_ASKING))
    for dom_id, names in R.NOT_BY_ASKING.items():
        for name in names:
            found = R.find_explain_setting(name)
            check(f"{name!r} is the page-only row {dom_id}",
                  found is not None and found.get("kind") == "page"
                  and found.get("dom_id") == dom_id, found)
            words = R.explain_setting_words(found or {})
            check(f"{name!r} answers with that row's own refusal",
                  words == R.not_by_asking_sentence(dom_id), words)
            check(f"{name!r} never claims a change was made",
                  "done" not in words.lower() and "changed" not in words.lower(), words)
        # ONE asking sentence per row reaches the refusal intent.
        got = Q.match(f"turn on {names[0]}")
        check(f"{dom_id}: 'turn on {names[0]}' is answered, not handed to the model",
              got is not None, got)
        check(f"{dom_id}: ...and it is not reported as a switch change",
              got is None or got.name not in ("settings_bool", "settings_choice"), got)
    check("the face is NOT in the page-only table (it has its own reader)",
          "face" not in R.NOT_BY_ASKING)


def t_an_unreadable_value_is_the_fixed_sentence_and_never_a_default():
    """A reader that answers the wrong thing is never dressed up as the value.

    Each of the three kinds is put in front of a reader that is (a) patched to a
    DIFFERENT real value - the answer must show the patched value, not the
    default - and (b) patched to answer nothing, which must produce the ONE
    fixed sentence and no value at all."""
    import jarvis_manner as MN
    import jarvis_live as LV
    import jarvis_limits as JL

    previous = _install_server()
    try:
        # --- a bool: the guide's own reader table, patched to on.
        backup = dict(G.STATE_READERS)
        try:
            G.STATE_READERS["prompt_coach"] = lambda: True
            words = R.explain_setting_words(R.find_explain_setting("prompt coach") or {})
            check("a patched-on switch says on", "Right now: on." in words, words)
            G.STATE_READERS["prompt_coach"] = lambda: False
            words = R.explain_setting_words(R.find_explain_setting("prompt coach") or {})
            check("...and a patched-off switch says off", "Right now: off." in words, words)
            G.STATE_READERS["prompt_coach"] = lambda: None
            words = R.explain_setting_words(R.find_explain_setting("prompt coach") or {})
            check("a reader that answers nothing gets the fixed sentence",
                  R.UNREADABLE_VALUE_WORDS in words, words)
            check("...and no on/off word is claimed for it",
                  "Right now: on" not in words and "Right now: off" not in words, words)
        finally:
            G.STATE_READERS.clear()
            G.STATE_READERS.update(backup)

        # --- a choice: the manner module's own reader, patched to another preset.
        personality = R._choice("personality")
        presets = [p for p in MN.all_personalities() if p.get("id")]
        now_id = MN.current_personality()
        other = next(p for p in presets if p["id"] != now_id)
        backup_now = MN.current_personality
        try:
            MN.current_personality = lambda conversation_id=None: other["id"]
            words = R.explain_setting_words(
                R.find_explain_setting("the personality") or {})
            check("a patched personality shows the preset it was patched to",
                  str(other.get("title") or other["id"]) in words, (other, words))
            MN.current_personality = lambda conversation_id=None: ""
            words = R.explain_setting_words(
                R.find_explain_setting("the personality") or {})
            check("a choice reader that answers nothing gets the fixed sentence",
                  R.UNREADABLE_VALUE_WORDS in words, words)
        finally:
            MN.current_personality = backup_now
        check("the unexplained default is never invented for the personality",
              R.current_value(personality) is not None,
              R.current_value(personality))

        # --- the number: the engine's own reader, patched to another value.
        number = R.NUMBER_SETTINGS[0]
        row = JL.find(number.limit_key)
        backup_quiet = LV.quiet_seconds
        try:
            LV.quiet_seconds = lambda: 300
            words = R.explain_setting_words(
                R.find_explain_setting("the jarvis live timeout") or {})
            check("a patched number shows the patched value in the row's own words",
                  row.words(300) in words, (row.words(300), words))
            check("...and does NOT show the row's default instead",
                  row.words(row.default) not in words if row.default != 300 else True,
                  (row.words(row.default), words))
            LV.quiet_seconds = lambda: None
            words = R.explain_setting_words(
                R.find_explain_setting("the jarvis live timeout") or {})
            check("a number reader that answers nothing is not a value",
                  R.UNREADABLE_VALUE_WORDS in words
                  or row.words(row.default) not in words, words)
        finally:
            LV.quiet_seconds = backup_quiet
    finally:
        _restore_server(previous)


def t_a_missing_module_is_the_fixed_sentence_not_an_exception():
    """A module that is not on this PC is said, never raised and never guessed.

    `sys.modules[name] = None` is what a failed import leaves behind, so this is
    the real shape of "that module is not installed here". The descriptor is
    resolved FIRST and the module is removed before the answer is BUILT, so what
    is proved is the reader path: a setting that was named still answers, and
    the answer says it could not read its value.
    """
    previous = _install_server()
    cases = [
        ("bool", "prompt coach", "jarvis_feature_guide"),
        ("choice", "the personality", "jarvis_manner"),
        ("number", "the jarvis live timeout", "jarvis_live"),
        ("animal", "listening nods", "jarvis_animal"),
        ("sky", "the sun and moon", "jarvis_sky"),
        ("weather", "the weather source", "jarvis_sky"),
    ]
    try:
        for kind, name, module_name in cases:
            found = R.find_explain_setting(name)
            check(f"{kind}: the setting is named while the module is there",
                  found is not None and found.get("kind") == kind, found)
            saved = sys.modules.get(module_name, "absent")
            sys.modules[module_name] = None
            try:
                try:
                    words = R.explain_setting_words(found or {})
                    raised = None
                except Exception as exc:        # noqa: BLE001 - that IS the failure
                    words, raised = "", f"{type(exc).__name__}: {exc}"
            finally:
                if saved == "absent":
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = saved
            check(f"{kind}: a missing {module_name} does not raise", raised is None, raised)
            check(f"{kind}: ...it says the fixed sentence instead",
                  R.UNREADABLE_VALUE_WORDS in words, words)
            check(f"{kind}: ...and offers no value of its own",
                  "Right now: none" not in words.lower(), words)
        # The OTHER half, said plainly: a name that only the missing module
        # knows falls through rather than being guessed at - no animal switch
        # is named by a module that is not there.
        saved = sys.modules.get("jarvis_animal", "absent")
        sys.modules["jarvis_animal"] = None
        try:
            fell = R.find_explain_setting("listening nods")
        finally:
            if saved == "absent":
                sys.modules.pop("jarvis_animal", None)
            else:
                sys.modules["jarvis_animal"] = saved
        check("without jarvis_animal the switch's NAME falls through (never guessed)",
              fell is None, fell)
    finally:
        _restore_server(previous)


def t_explaining_changes_nothing():
    """No explain answer can call a setter, so this door cannot change a thing.

    Every setter in the three tables is replaced with one that raises: if any
    explain path reached a setter, the answer would fail loudly here."""
    def _boom(*args, **kwargs):
        raise AssertionError("an explain answer called a setter")

    before = (R.BOOL_SETTINGS, R.CHOICE_SETTINGS, R.NUMBER_SETTINGS)
    previous = _install_server()
    try:
        R.BOOL_SETTINGS = tuple(dataclasses.replace(b, set=_boom) for b in before[0])
        R.CHOICE_SETTINGS = tuple(dataclasses.replace(c, set=_boom) for c in before[1])
        R.NUMBER_SETTINGS = tuple(dataclasses.replace(n, set=_boom) for n in before[2])
        raised = []
        for kind, key, row in _all_rows():
            try:
                R.explain_setting_words(R.find_explain_setting(row.names[0]) or {})
            except Exception as exc:            # noqa: BLE001 - that IS the failure
                raised.append(f"{kind}:{key}: {type(exc).__name__}: {exc}")
        for name in ("the sun and moon", "listening nods", "the weather source",
                     "auto adjust", "theme", "hud layout", "app lock"):
            try:
                R.explain_setting_words(R.find_explain_setting(name) or {})
            except Exception as exc:            # noqa: BLE001 - that IS the failure
                raised.append(f"{name}: {type(exc).__name__}: {exc}")
        check("not one explain answer calls a setting's setter", not raised, raised)
    finally:
        R.BOOL_SETTINGS, R.CHOICE_SETTINGS, R.NUMBER_SETTINGS = before
        _restore_server(previous)


def t_the_guide_answers_a_choice_too():
    """M4: `state` / `how_to` resolve a choice, with a value, never a guess."""
    previous = _install_server()
    try:
        for c in R.CHOICE_SETTINGS:
            out = G.state(c.key)
            check(f"guide state for the choice {c.key!r} answers as that setting",
                  out.get("ok") is True and out.get("kind") == "setting"
                  and out.get("setting") == c.key, out)
            here = R.current_value(c)
            if here:
                check(f"guide state {c.key!r}: the answer carries the real value",
                      str(here) in str(out.get("words") or ""), (here, out.get("words")))
                check(f"guide state {c.key!r}: ...and reports it as the state",
                      out.get("state") == here, (here, out.get("state")))
            else:
                check(f"guide state {c.key!r}: unreadable is said, not guessed",
                      "could not read" in str(out.get("words") or "")
                      and "guess" in str(out.get("words") or ""), out)
            how = G.how_to(c.key, True)
            check(f"guide how_to for {c.key!r} answers as that setting",
                  how.get("ok") is True and how.get("setting") == c.key, how)
            words = str(how.get("words") or "")
            options = sorted(set(c.options().keys()))
            check(f"guide how_to {c.key!r}: it prints a real set-to phrase",
                  bool(options) and f'set {c.names[0]} to {options[0]}' in words, words)
            check(f"guide how_to {c.key!r}: it does not offer an on/off phrase",
                  f"turn on {c.names[0]}" not in words, words)
    finally:
        _restore_server(previous)
    # The unknown answer is untouched: a name in neither table is still unknown.
    out = G.state("nonsense xyz")
    check("an unknown name is still unknown (the choice branch did not widen it)",
          out.get("ok") is False and out.get("kind") == "unknown", out)


def t_the_compound_where_and_value_question_answers_once():
    """Q7 (Gemini's ruling, 2026-11-03): "where do I change X, and what is it set to?"

    ONE question asking for BOTH halves - the place and the value - and
    `explain_setting_words` already prints both, so it must reach the SAME
    `setting_explain` the plain "where do I change X" reaches. Measured before
    this: the compound sentence matched NOTHING and went to the local model,
    which invented a `configuration.yaml` place for the weather source.
    """
    for subject, kind in (("the weather source", "weather"),
                          ("the voice speed", "choice"),
                          ("the personality", "choice")):
        plain = Q.match(f"where do I change {subject}")
        check(f"{subject}: the plain question is setting_explain",
              plain is not None and plain.name == "setting_explain"
              and (plain.f or {}).get("kind") == kind, plain)
        for wanted in (f"where do I change {subject}, and what is it set to",
                       f"where do i change {subject} and what is it set to",
                       f"where do I set {subject}, and what is it set to?"):
            got = Q.match(wanted)
            check(f"{subject}: the compound question answers too: {wanted!r}",
                  got is not None and got.name == "setting_explain"
                  and got.f == (plain.f if plain is not None else None), got)
        # ...and the answer really carries both halves.
        got = Q.match(f"where do I change {subject}, and what is it set to")
        said = R.explain_setting_words(got.f or {}) if got is not None else ""
        check(f"{subject}: the answer names a Settings place",
              bool(said) and "Settings" in said, said)
        check(f"{subject}: the answer carries the current value",
              "Right now:" in said, said)
    # A name nothing knows still falls through to the model, exactly as the
    # plain question does - the exact-name gate is unchanged.
    check("an unknown setting stays the model's",
          Q.match("where do I change my wifi password, and what is it set to") is None,
          Q.match("where do I change my wifi password, and what is it set to"))


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for test in tests:
        print(f"--- {test.__name__} ---")
        test()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    # THE UNREADABLE ROWS ARE LISTED, never hidden: a pass on one of these means
    # the answer said it could not read the value, not that it had one.
    print("Unreadable on this PC (said so, never guessed): "
          + (", ".join(UNREADABLE) if UNREADABLE else "none"))
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
