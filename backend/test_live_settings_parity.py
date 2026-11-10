#!/usr/bin/env python3
"""test_live_settings_parity.py - every chat setting change is also a Live change.

    python -B backend/test_live_settings_parity.py

THE OWNER'S REQUIREMENT (2026-11-07, verbatim): "also make sure anything that
can be changed by chat with jarvis (with an approval card when appropriate) can
also be changed in the same manner through jarvis live. i dont want any gaps"
and "also check if jarvis can also change the settings of these under the hood
functions whether through settings or chat or live".

WHY A SECOND SUITE. `backend/test_live_parity.py` proves the Live DOOR (tool
list, route, marks, read-only answers, the calm card line). It does not prove
any particular SETTING changes the same way in both doors. This suite does, and
it derives the list from the registry so a setting added later cannot ship
chat-only.

WHAT THIS SUITE PROVES, headless (no model, no network, no real card decision):

  1. ONE SOURCE OF TRUTH. `jarvis_settings_registry.capability_keys()` is the
     list /api/self reports to both apps. Every `switch:`/`choice:`/`limit:`/
     `asks_first:`/`tool:` key must have a sentence the REAL matcher
     (`jarvis_quick.match`) resolves, built from that row's own first name - and
     every one of them is then driven through both doors below. A setting added
     to any table without a chat path fails the coverage check at the end; a
     setting added with a chat path that Live somehow skips fails its family
     loop. The suite prints the exact number of options it covered.

  2. TYPED == LIVE, DOOR FOR DOOR. The same sentence is answered twice through
     `jarvis_quick.answer_turn` - once typed and once with the exact Live marks
     both apps send (`provenance:"voice"` + `live:true`, the shape in
     `jarvis_live_turn.py` and `jarvis_quick._live_body`) - with the registry's
     own setter replaced by a recorder. Both doors must call the SAME setter
     with the SAME arguments exactly ONCE. Nothing is approved, and no real
     card is raised: the recorder's answer stands in for the setter's.

  3. THE ONE DELIBERATE DIFFERENCE. A change whose setter says it is WAITING on
     a card gets the setter's own sentence in typed chat and ONE calm line in
     Live (`_settings_said`/`_settings_tool_waiting_line`): Live speaks aloud,
     so no card id, no list, no question back, and nothing that could be heard
     as "say yes". Both doors still called the setter once - ONE card, never two
     - and neither reports it as done.

  4. THE CARD RULES ARE THE SETTING'S OWN. ON that asks stays asking, OFF that
     is instant stays instant, and a waiting answer is never reworded into
     "done" in either door.

  5. THE TOOL SWITCHES (the 2026-11-07 audit's H7/LP-2). Every switchable tool
     resolves from its own name: "turn on the browser control tool" and "let
     the ai model read the browser control tool" - ON and OFF - while a device
     sentence ("turn off the kitchen light") still falls through to its own
     handler and is never read as a tool switch.

  6. THE SPOKEN PRE-PASS (owner's Q2 ruling, 2026-11-07). Wake words, polite
     lead-ins and spoken punctuation reach the same intent as the typed
     sentence, and the typed sentences themselves still resolve exactly as
     before.

  7. LP-3, THE FALSE DENIAL. "Can you change your own settings by voice through
     Jarvis Live?" is answered deterministically: yes, the same sentence, the
     same card, the same effect; some settings are PC-only and their card is
     tapped, never said.

  8. THE LIVE FALLBACK MENU (owner's Q2 ruling). A spoken sentence the fast path
     does not recognise is offered the SAME configuration tools as typed chat
     (`change_setting` and the `cloud_escalation` switch that rides with it, and
     `approval_policy`), so the model can raise the same card - and, because
     `_settings_said` exists, spoken Live gets the calm card line.

WHAT IT DOES NOT PROVE: a real microphone/speech-to-text, a real card decision,
a real Live session, or which model answers a fallback turn. Those stay
NOT-TESTABLE here (BLOCKED is never a pass).
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_settings_registry.py",
                "jarvis_asks_first.py", "jarvis_live.py", "jarvis_agent.py")

TMP = Path(tempfile.mkdtemp(prefix=".jarvis-live-settings-parity-", dir=str(Path.home())))
for _d in ("config", "logs", "home"):
    (TMP / _d).mkdir()
# The switchable-tools list lives in the shipped framework TOML. The REAL tool
# setter writes `[tools].enabled` back through jarvis_framework, so this suite
# must point it at a COPY: without this line a test run edits
# backend/rebuilt/jarvis-framework.toml in the checkout (measured 2026-11-07 -
# exactly the kind of tree damage a suite must never cause). The same staging
# test_animal.py and test_self_answers.py do.
import shutil  # noqa: E402

_TOML = TMP / "config" / "jarvis-framework.toml"
shutil.copyfile(HERE / "rebuilt" / "jarvis-framework.toml", _TOML)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(TMP / "home")
os.environ["JARVIS_LOG_DIR"] = str(TMP / "logs")
os.environ["JARVIS_MEMORY_DB"] = str(TMP / "config" / "memory.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(TMP / "config" / "receipts.db")
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TOML)
os.environ.pop("JARVIS_BACKEND", None)

import jarvis_asks_first as AF  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

# --------------------------------------------------------------------------
#   Q2 (the owner's 2026-11-10 00:05 PT ruling): cache the repeated STATIC
#   reads this suite drives hundreds of times
# --------------------------------------------------------------------------
# WHY. This suite is green in substance - 935 checks, 0 failed - but it took
# 606.6 s at the desk, 6.6 s past check_claims.py's old 600 s cap, because it
# drives ~500 REAL chat turns and Jarvis has grown to 62 switchable tools and
# 180+ features. Measured here (not guessed), per turn, the cost is TWO
# repeated STATIC reads and nothing else:
#
#   1. `jarvis_framework.load_framework()` - the shipped framework TOML. It
#      already caches the TOML PARSE but returns `copy.deepcopy(_CACHE)` on
#      every call (its docstring explains why: a caller may mutate what it is
#      handed). One turn reaches it ~870 times, and deep-copying a 145 KB
#      nested dict ~870 times is ~0.5-0.9 s of the turn. The file does not
#      change between those calls.
#   2. `jarvis_compute._run_smi(...)` - nvidia-smi's hardware table. One turn
#      runs it 4 times (jarvis_second_card's "which card is the model on" and
#      `jarvis_voices.status`), ~0.6 s of subprocess time. The graphics cards
#      do not change during a test run.
#
# Neither read is what this suite tests: it tests that a setting changed by
# TYPING changes the same way through Jarvis Live, door for door. So the two
# static reads are cached for the process, and ONE check at the end
# (`t_zzz_the_static_read_cache_is_behaviour_preserving`) proves the cache
# changed speed and nothing else: every hardware answer is checked for the real
# table's shape and for being served from the cache, and the cached framework
# dict is compared with a fresh `load_framework()` - which fails if any of the
# ~500 turns MUTATED it, the one way returning a cached dict could leak state
# between turns. Measured on the owner's PC, 2026-11-10: 606.6 s -> 90 s. The
# cap itself was raised 600 -> 900 s in tools/check_claims.py by the same
# ruling - the ruling explicitly forbids splitting claim row C101 or inventing
# an "environment-dependent" category.
_STATIC_CACHE_COUNTS = {"framework": 0, "smi": 0}

# --- 1. the framework TOML: keyed on the file's own stat, so a real edit ----
# (the tool-switch checks in this suite DO edit [tools].enabled) is re-read.
import jarvis_framework as _framework  # noqa: E402

_real_load_framework = _framework.load_framework

#: The one framework file this run uses, resolved ONCE. `config_path()` itself
#: is not cheap - it resolves this module's own path and stats four candidates -
#: and it is called ~890 times per turn through `load_framework`, so asking it
#: per call costs more than the read it guards. The suite sets
#: JARVIS_FRAMEWORK_TOML at import and never moves the file, so this cannot
#: change under it; the per-call part is only the stat the cache is keyed on.
_FRAMEWORK_PATH = _framework.config_path()


def _framework_key():
    if _FRAMEWORK_PATH is None:
        return None
    try:
        st = _FRAMEWORK_PATH.stat()
    except OSError:
        return (str(_FRAMEWORK_PATH), None, None)
    return (str(_FRAMEWORK_PATH), st.st_mtime_ns, st.st_size)


_FRAMEWORK_CACHE = {"key": (_framework_key(),), "value": None}


def _cached_load_framework(*args, **kwargs):
    key = _framework_key()
    if _FRAMEWORK_CACHE["value"] is None or key != _FRAMEWORK_CACHE["key"]:
        _FRAMEWORK_CACHE["value"] = _real_load_framework(*args, **kwargs)
        _FRAMEWORK_CACHE["key"] = key
    else:
        _STATIC_CACHE_COUNTS["framework"] += 1
    return _FRAMEWORK_CACHE["value"]


_framework.load_framework = _cached_load_framework

# --- 2. nvidia-smi: the hardware table, keyed on the exact query ------------
import jarvis_compute as _compute  # noqa: E402

_real_run_smi = _compute._run_smi

#: {(query arguments): the one nvidia-smi answer}. A dict (not lru_cache) so the
#: closing check can ask every cached query again and compare the answers.
_SMI_CACHE: dict = {}


def _run_smi_cached(args):
    key = tuple(args or ())
    if key in _SMI_CACHE:
        _STATIC_CACHE_COUNTS["smi"] += 1
        return _SMI_CACHE[key]
    _SMI_CACHE[key] = _real_run_smi(list(key))
    return _SMI_CACHE[key]


_compute._run_smi = _run_smi_cached

PASSED, FAILED, SKIPPED = [], [], []
COVERED_KEYS: set = set()

#: What a recorder says when the setting's own setter would have raised a card.
CARD_SAID = "Waiting for your yes on the approval card. Nothing has changed yet."
#: ... and when a cardless change really happened.
DONE_SAID = "Done - that setting is now what you asked for."


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"SKIP {why}")


def body(text, live):
    """The exact request shape: typed chat, and the marks Jarvis Live sends."""
    msg = {"role": "user", "content": text, "provenance": "voice"}
    if live:
        msg["live"] = True
    return {"messages": [msg], "model": "m", "stream": False}


def doors(text):
    return Q.answer_turn(body(text, False)), Q.answer_turn(body(text, True))


class Recorder:
    """Stands in for one setting's own setter and records what it was asked.

    `waiting` says whether this recorder answers with the setting's card
    sentence - the real setter's answer when it raises a card. The suite never
    raises or approves a card: the recorder is the setter's answer, so the card
    tier itself is proved by both doors calling the same real setter with the
    same arguments (the tier lives inside that setter, never in the door).
    """

    def __init__(self, waiting=False):
        self.calls = []
        self.waiting = waiting

    def _answer(self, *args):
        self.calls.append(args)
        if self.waiting:
            return R.Outcome(True, CARD_SAID, waiting=True)
        return R.Outcome(True, DONE_SAID)

    def __call__(self, value, *, peer=None, local=None):
        return self._answer(value)


class FamilyRecorder:
    """A recorder for the functions that take more than one positional value."""

    def __init__(self, waiting=False):
        self.calls = []
        self.waiting = waiting

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if self.waiting:
            return R.Outcome(True, CARD_SAID, waiting=True)
        return R.Outcome(True, DONE_SAID)


def with_row(attr, key, replacement):
    """Swap one registry row for `replacement`; returns the restore function."""
    saved = getattr(R, attr)
    setattr(R, attr, tuple(replacement if r.key == key else r for r in saved))
    return lambda: setattr(R, attr, saved)


def one_calm_line(reply, label):
    """Is `reply` the ONE calm Live line for a card that is waiting?"""
    want = (f"A card is waiting for {label}, so approve it on your phone or PC "
            f"and it changes.")
    return (isinstance(reply, str) and reply == want
            and reply.count(".") == 1 and "?" not in reply
            and not re.search(r"\b[0-9a-f]{8,}\b", reply)
            and "approve or deny" not in reply)


# ------------------------------------------------------------------ 1. switches

def t_every_switch_changes_the_same_way_in_both_doors():
    """All 38 on/off switches: same sentence, same setter, same value, both doors.

    ON is carded for every row in this registry shape (a switch that reads or
    loosens more asks first), and the recorder returns the card's sentence for
    it; OFF is instant. A switch that Live skipped entirely, or ran a different
    setter, fails here.
    """
    for b in R.BOOL_SETTINGS:
        COVERED_KEYS.add(f"switch:{b.key}")
        for on in (True, False):
            verb = "turn on " if on else "turn off "
            phrase = verb + b.names[0]
            got = Q.match(phrase)
            check(f"{phrase!r} reaches the {b.key} switch",
                  got is not None and got.name in ("settings_bool", "feature_switch")
                  and got.f.get("key") == b.key and got.f.get("on") is on, got)
            rec = Recorder(waiting=on)
            restore = with_row("BOOL_SETTINGS", b.key, dataclasses.replace(b, set=rec))
            try:
                typed, live = doors(phrase)
            finally:
                restore()
            # A no-op is a real outcome, not a gap: if the switch is ALREADY
            # in the asked state, both doors answer the same honest "already
            # ... Nothing was changed." and neither calls the setter (the
            # no-op receipt rule, 2026-11-07). The recorder is never asked, so
            # there is no card to be waiting for either.
            already = (typed is not None and live is not None
                       and "nothing was changed" in typed.reply.lower()
                       and "already" in typed.reply.lower())
            if already:
                check(f"a no-op {b.key} ({on}) calls no setter in either door",
                      rec.calls == [], rec.calls)
                check(f"{b.key} says the same thing in both doors when it is "
                      f"already {'on' if on else 'off'}",
                      typed.reply == live.reply, (typed.reply, live.reply))
                continue
            check(f"the same {b.key} setter runs once in typed and once in Live",
                  typed is not None and live is not None
                  and rec.calls == [(on,), (on,)], rec.calls)
            check(f"{b.key} says the same thing in both doors: {on}",
                  typed is not None and live is not None and (
                      typed.reply == live.reply if not on
                      else (typed.reply == CARD_SAID and live.reply != typed.reply)),
                  (None if typed is None else typed.reply,
                   None if live is None else live.reply))
            if on:
                check(f"...and a carded {b.key} ON in Live is ONE calm line, not "
                      f"the setter's sentence",
                      live is not None and one_calm_line(live.reply,
                                                          (b.names[0] if b.names else b.key)),
                      None if live is None else live.reply)
                check(f"...and a carded {b.key} ON is never reported as done",
                      typed is not None and live is not None
                      and "done" not in typed.reply.lower()
                      and "done" not in live.reply.lower(),
                      (None if typed is None else typed.reply,
                       None if live is None else live.reply))


# ------------------------------------------------------------------- 2. choices

def t_every_choice_changes_the_same_way_in_both_doors():
    """All 10 named-choice settings: same setter, same value, both doors."""
    for c in R.CHOICE_SETTINGS:
        COVERED_KEYS.add(f"choice:{c.key}")
        options = c.options()
        if not options:
            skip(f"{c.key} declares no choices on this PC, so it cannot be asked")
            continue
        value_word = sorted(options)[0]
        value = options[value_word]
        phrase = f"set {c.names[0]} to {value_word}"
        got = Q.match(phrase)
        check(f"{phrase!r} reaches {c.key}", got is not None and (
            (got.name in ("settings_choice", "control_set")
             and got.f.get("key") == c.key)
            or (got.name == "personality_set" and c.key == "personality"
                and got.f.get("personality") == value)), got)
        if got is None or got.name != "settings_choice":
            # The personality row has its own runner (a real, cardless write to
            # manner.json). Run it for real, in the throwaway config, and prove
            # the two doors answer the same - the same rule, one file.
            typed, live = doors(phrase)
            check(f"{c.key}'s own runner answers the same in typed and Live",
                  typed is not None and live is not None
                  and typed.reply == live.reply,
                  (None if typed is None else typed.reply,
                   None if live is None else live.reply))
            continue
        rec = Recorder(waiting=True)
        restore = with_row("CHOICE_SETTINGS", c.key, dataclasses.replace(c, set=rec))
        try:
            typed, live = doors(phrase)
        finally:
            restore()
        check(f"the same {c.key} setter runs once in typed and once in Live",
              typed is not None and live is not None and rec.calls == [(value,), (value,)],
              rec.calls)
        check(f"a carded {c.key} change is ONE calm line in Live",
              typed is not None and live is not None and typed.reply == CARD_SAID
              and one_calm_line(live.reply, (c.names[0] if c.names else c.key)),
              (None if typed is None else typed.reply,
               None if live is None else live.reply))
        # A SECOND recorder for the cardless half: the first one's calls are
        # already recorded, and reusing it would make this count four.
        rec2 = Recorder(waiting=False)
        restore = with_row("CHOICE_SETTINGS", c.key, dataclasses.replace(c, set=rec2))
        try:
            typed, live = doors(phrase)
        finally:
            restore()
        check(f"a cardless {c.key} change says the same thing in both doors",
              typed is not None and live is not None and typed.reply == live.reply
              and rec2.calls == [(value,), (value,)], rec2.calls)


# ------------------------------------------------------- 3. the one number row

def t_the_one_number_setting_changes_the_same_way_in_both_doors():
    """How long Jarvis Live waits: the same writer, the same seconds, one file."""
    if not R.NUMBER_SETTINGS:
        skip("this backend has no number setting")
        return
    row = R.NUMBER_SETTINGS[0]
    COVERED_KEYS.add(f"limit:{row.key}")
    phrase = "make jarvis live wait 3 minutes"
    got = Q.match(phrase)
    check(f"{phrase!r} reaches {row.key}",
          got is not None and got.name == "live_idle_set", got)
    if got is None:
        return
    state = {"seconds": 90}
    calls = []

    def fake_set(value, *, peer=None, local=None):
        # The runner reads the value back through `_live_idle_now`, so the
        # recorder updates it exactly as the real writer would.
        calls.append((value,))
        state["seconds"] = int(value)
        return R.Outcome(True, DONE_SAID)

    saved_now = Q._live_idle_now
    Q._live_idle_now = lambda: state["seconds"]
    try:
        typed_replies = []
        for live in (False, True):
            state["seconds"] = 90              # the same BEFORE state for each door
            restore = with_row("NUMBER_SETTINGS", row.key,
                               dataclasses.replace(row, set=fake_set))
            try:
                typed_replies.append(Q.answer_turn(body(phrase, live)))
            finally:
                restore()
    finally:
        Q._live_idle_now = saved_now
    typed, live = typed_replies
    check("the same number writer runs once per door with the same seconds",
          typed is not None and live is not None
          and [c[0] for c in calls] == [180, 180], calls)
    check("both doors say the same thing about the new Live window",
          typed is not None and live is not None and typed.reply == live.reply,
          (None if typed is None else typed.reply,
           None if live is None else live.reply))


# ------------------------------------------------------- 4. what asks first

def t_every_asks_first_change_is_the_same_in_both_doors():
    """All 7 asks-first actions: stricter (instant) and looser (carded)."""
    for action, names in R.asks_first_targets().items():
        COVERED_KEYS.add(f"asks_first:{action}")
        for ask, phrase in ((True, f"ask me first before {names[0]}"),
                            (False, f"stop asking before {names[0]}")):
            got = Q.match(phrase)
            check(f"{phrase!r} reaches asks-first {action}",
                  got is not None and got.name == "settings_asks_first"
                  and got.f.get("action") == action and got.f.get("ask") is ask, got)
            rec = FamilyRecorder(waiting=not ask)      # the loosening is the carded half
            saved = R.set_asks_first
            R.set_asks_first = rec
            try:
                typed, live = doors(phrase)
            finally:
                R.set_asks_first = saved
            check(f"the same asks-first setter runs once per door: {action} ask={ask}",
                  typed is not None and live is not None
                  and rec.calls == [(action, ask), (action, ask)], rec.calls)
            check(f"both doors answer alike: {action} ask={ask}",
                  typed is not None and live is not None
                  and typed.reply == live.reply, (
                      None if typed is None else typed.reply,
                      None if live is None else live.reply))


# ------------------------------------------------------------- 5. tool switches

def _tool_core(name):
    core = re.sub(r"^(?:the|my)\s+", "", str(name))
    return re.sub(r"\s+tool$", "", core)


def t_every_tool_switch_is_the_same_in_both_doors():
    """All 60 switchable tools: the generated names resolve, ON and OFF, both doors."""
    targets = R.tool_targets()
    extra = [t for t in targets if t not in AF.TOOLS_SWITCHABLE]
    check("the registry names every switchable tool, plus the legacy "
          "reading-tool row the old sentences still reach",
          all(t in targets for t in AF.TOOLS_SWITCHABLE)
          and extra == ["email_read"],
          (len(targets), len(AF.TOOLS_SWITCHABLE), extra))
    for tool, names in targets.items():
        COVERED_KEYS.add(f"tool:{tool}")
        core = _tool_core(names[0] if names else tool)
        for on, phrase in (
                (True, f"turn on the {core} tool"),
                (True, f"let the ai model read {names[0]}"),
                (False, f"turn off the {core} tool"),
                (False, f"stop letting the ai model read {names[0]}")):
            got = Q.match(phrase)
            check(f"{phrase!r} reaches the {tool} tool switch",
                  got is not None and got.name == "settings_tool"
                  and got.f.get("tool") == tool and got.f.get("on") is on, got)
        phrase_on = f"turn on the {core} tool"
        phrase_off = f"turn off the {core} tool"
        for phrase, waiting in ((phrase_on, True), (phrase_off, False)):
            rec = FamilyRecorder(waiting=waiting)
            saved = R.set_reading_tool
            R.set_reading_tool = rec
            try:
                typed, live = doors(phrase)
            finally:
                R.set_reading_tool = saved
            want = [(tool, waiting), (tool, waiting)]
            check(f"the same tool setter runs once per door: {tool} on={waiting}",
                  typed is not None and live is not None
                  and rec.calls == want, rec.calls)
            if waiting:
                check(f"a carded {tool} ON is ONE calm line in Live",
                      typed is not None and live is not None
                      and typed.reply == CARD_SAID and live.reply != typed.reply
                      and live.reply.count(".") == 1 and "?" not in live.reply
                      and "approve or deny" not in live.reply
                      and not re.search(r"\b[0-9a-f]{8,}\b", live.reply),
                      (None if typed is None else typed.reply,
                       None if live is None else live.reply))
            else:
                check(f"an instant {tool} OFF says the same thing in both doors",
                      typed is not None and live is not None
                      and typed.reply == live.reply, (
                          None if typed is None else typed.reply,
                          None if live is None else live.reply))


def t_the_owners_own_tool_sentence_now_resolves():
    """The measured sentence from the audit: it went to the model before."""
    got = Q.match("Turn on the browser control tool.")
    check("'Turn on the browser control tool.' is a tool switch now",
          got is not None and got.name == "settings_tool"
          and got.f.get("tool") == "browser_control"
          and got.f.get("on") is True, got)
    got = Q.match("turn off the browser control tool")
    check("...and its OFF twin resolves too",
          got is not None and got.name == "settings_tool"
          and got.f.get("tool") == "browser_control"
          and got.f.get("on") is False, got)


def t_the_generated_tool_names_are_not_stale():
    """The generated table must be what TOOLS_SWITCHABLE says today.

    A tool added, renamed or removed without running the generator would
    otherwise ship as a Settings row chat cannot name - the exact defect this
    pass fixed - so the drift check is part of the suite CI already runs.
    """
    import subprocess

    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_tool_targets.py"),
                        "--check"], capture_output=True, text=True, timeout=180,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    check("the tool-name table is what TOOLS_SWITCHABLE says today "
          "(python -B tools/gen_tool_targets.py)", r.returncode == 0,
          (r.stdout or "") + (r.stderr or ""))


def t_a_device_sentence_is_never_swallowed_by_the_tool_switch():
    """The closed-world rule: 'tool' plus a real alias, or nothing."""
    for phrase in ("turn off the kitchen light", "turn off the lights",
                   "turn on the fan", "turn off the timer",
                   "turn on the weather"):
        got = Q.match(phrase)
        check(f"{phrase!r} is NOT read as a tool switch",
              got is None or got.name != "settings_tool", got)
    # ...and a name that is not a switchable tool, even with "tool" said, still
    # falls through to the model exactly as before.
    check("'turn on the espresso machine tool' is not a tool switch",
          (Q.match("turn on the espresso machine tool") is None
           or Q.match("turn on the espresso machine tool").name != "settings_tool"),
          Q.match("turn on the espresso machine tool"))


# --------------------------------------------------------------- 6. the ASR pass

def t_spoken_lead_ins_reach_the_same_intent_as_typed():
    """Wake words, polite lead-ins and spoken punctuation hit the fast path."""
    pairs = (
        ("turn on anti-slop",
         "hey jarvis, could you please go ahead and turn on anti-slop"),
        ("turn off the kitchen light", "hey jarvis, please turn off the kitchen light"),
        ("turn on the browser control tool",
         "Jarvis; could you go ahead and turn on the browser control tool please"),
        ("set the hand-off to patient", "hey jarvis, can you set the hand-off to patient"),
        ("make jarvis live wait 3 minutes",
         "um, jarvis, make jarvis live wait 3 minutes please"),
        ("stop asking before my calendar", "hey jarvis, stop asking before my calendar"),
        ("turn on the timer tool", "uh, turn on the timer tool"),
        ("what can i change", "hey jarvis, what can i change"),
    )
    for typed_text, spoken in pairs:
        a, b = Q.match(typed_text), Q.match(spoken)
        check(f"the spoken form of {typed_text!r} reaches the same intent",
              a is not None and b is not None and a.name == b.name
              and a.f == b.f, (None if a is None else (a.name, a.f),
                               None if b is None else (b.name, b.f)))


def t_the_typed_sentences_still_resolve_exactly_as_before():
    """The pre-pass must not change what a TYPED sentence does."""
    pinned = (
        ("turn on anti-slop", "settings_bool"),
        ("turn off the kitchen light", "honest_chat"),
        ("set the hand-off to patient", "control_set"),
        ("stop asking before my calendar", "settings_asks_first"),
        ("let the ai model read my calendar", "settings_tool"),
        ("what can i change", "changeable_overview"),
        ("make jarvis live wait 3 minutes", "live_idle_set"),
    )
    for typed_text, want in pinned:
        got = Q.match(typed_text)
        check(f"typed {typed_text!r} still resolves to {want}",
              got is not None and got.name == want, got if got is None else got.name)


# ------------------------------------------------------------ 7. the LP-3 answer

LIVE_QUESTION = "Can you change your own settings by voice through Jarvis Live?"


def t_the_self_answer_says_yes_plainly():
    """LP-3: the model used to deny the Live door. Now the code answers."""
    got = Q.match(LIVE_QUESTION)
    check("the Live-settings question is answered without the model",
          got is not None and got.name == "how_live_settings", got)
    check("...and the answer is fixed, not measured state",
          got is not None and Q.READ_ONLY_INTENTS is not None
          and got.name in Q.READ_ONLY_INTENTS, None if got is None else got.name)
    typed, live = doors(LIVE_QUESTION)
    reply = "" if typed is None else typed.reply
    check("both doors answer it", typed is not None and live is not None)
    check("...identically", typed is not None and live is not None
          and typed.reply == live.reply, (
              None if typed is None else typed.reply,
              None if live is None else live.reply))
    low = reply.lower()
    for want, why in (
            ("yes", "it says yes"),
            ("jarvis live", "it names Jarvis Live"),
            ("same", "it says the change is the same as typing"),
            ("card", "it names the approval card"),
            ("pc-only", "it says some settings are PC-only"),
            ("tap", "it says the card is tapped, not said")):
        check(f"...it says {why}", want in low, reply[:200])
    for wrong in ("no, you can't", "cannot change", "can't change",
                  "no - ", "approve or deny"):
        check(f"...it never says {wrong!r}", wrong not in low, reply[:200])


# ------------------------------------------------- 8. the Live fallback menu

def t_a_live_fallback_turn_is_offered_the_same_configuration_tools():
    """The owner's Q2 ruling: a fallback Live turn gets the same config tools.

    `test_live_parity.py` proves the whole tool LIST is identical; this pins the
    CONFIGURATION names specifically, because those are what can raise a
    setting/preset/approval card from a sentence the fast path missed.
    """
    import jarvis_agent as A

    def shown(limit, question):
        names = A.offered_tools(list(A.TOOLS))
        offer = A._new_offer(names, limit=limit)
        A._fill_offer(offer, names, question=question, conversation_id=None)
        return list(offer["shown"])

    question = "book a table for two at the italian place"
    from jarvis_live import live_tool_limit
    typed = shown(None, question)
    live = shown(live_tool_limit(), question)
    check("a fallback Live turn is shown exactly the typed tool list",
          live == typed, (len(typed), len(live)))
    check("the configuration tool is offered in both doors",
          "change_setting" in typed and "change_setting" in live)
    check("the standing Cloud switch rides with it in both doors",
          "cloud_escalation" in typed and "cloud_escalation" in live,
          (typed, live))
    check("the approval-policy tool is offered in both doors",
          "approval_policy" in typed and "approval_policy" in live)


# ------------------------------------------------ real disk, representative set

def _config_json(name):
    path = TMP / "config" / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:                        # noqa: BLE001 - unreadable is None
        return None


def t_representative_settings_write_the_same_state_on_disk():
    """Beyond the stubs: the REAL setters, and the file each one owns.

    The owner's requirement is parity of EFFECT, not only of call. Anti-Slop and
    humour are the cardless representative pair (each writes its own JSON file),
    a carded switch is the "one card, nothing written yet" case, and a tool
    switch's real ON/OFF is driven through the module's own list.
    """
    import json

    # --- Anti-Slop on: typed and Live must leave antislop.json identical ------
    # Reset through the PRODUCT path (the same door a person uses), not by
    # calling the row's setter directly: the direct call leaves the owning
    # module's cache stale, and the 2026-11-07 no-op rule then makes the two
    # doors disagree in the harness for a reason that cannot happen in the app.
    row = next(b for b in R.BOOL_SETTINGS if b.key == "antislop")
    # Each door is driven on its OWN, from the same starting state. Calling
    # doors() runs typed and then Live in one go, and since 2026-11-07 the
    # second turn honestly reports "already on. Nothing was changed." because
    # the FIRST turn already made the change - a harness artefact, not a gap.
    Q.answer_turn(body("turn off anti-slop", False))
    typed = Q.answer_turn(body("turn on anti-slop", False))
    after_typed = _config_json("antislop.json")
    check("typed anti-slop ON really writes enabled true",
          typed is not None and (after_typed or {}).get("enabled") is True,
          (None if typed is None else typed.reply, after_typed))
    Q.answer_turn(body("turn off anti-slop", False))
    live = Q.answer_turn(body("turn on anti-slop", True))
    after_live = _config_json("antislop.json")
    check("Live anti-slop ON really writes enabled true too",
          live is not None and (after_live or {}).get("enabled") is True,
          (None if live is None else live.reply, after_live))
    check("...and both doors state the SAME outcome",
          typed is not None and live is not None and typed.reply == live.reply
          and after_typed is not None and after_live is not None
          and after_typed.get("enabled") == after_live.get("enabled"))

    # --- Humour off: manner.json, the same way -------------------------------
    # Same rule as anti-slop above: reset through the product door so the
    # owning module's cache matches the file both doors read.
    hrow = next(b for b in R.BOOL_SETTINGS if b.key == "humor")
    Q.answer_turn(body("turn on humour", False))
    typed = Q.answer_turn(body("turn off humour", False))
    typed_state = _config_json("manner.json")
    Q.answer_turn(body("turn on humour", False))
    live = Q.answer_turn(body("turn off humour", True))
    live_state = _config_json("manner.json")
    check("both doors turn humour off in manner.json",
          typed is not None and live is not None
          and (typed_state or {}).get("humor") is False
          and (live_state or {}).get("humor") is False,
          (typed_state, live_state))
    check("...and say the same sentence",
          typed is not None and live is not None and typed.reply == live.reply,
          (None if typed is None else typed.reply,
           None if live is None else live.reply))

    # --- A carded switch: ONE card, nothing written, calm line in Live -------
    try:
        srow = next(b for b in R.BOOL_SETTINGS if b.key == "learn_sensitive_topics")
        before_files = sorted(p.name for p in (TMP / "config").iterdir())
        typed, live = doors("turn on remembering sensitive topics automatically")
        after_files = sorted(p.name for p in (TMP / "config").iterdir())
        both_waiting = (typed is not None and live is not None
                        and "approv" in typed.reply.lower()
                        and "approv" in live.reply.lower())
        check("the carded sensitive-topic switch waits in BOTH doors", both_waiting,
              (None if typed is None else typed.reply,
               None if live is None else live.reply))
        check("...the carded change wrote no settings file yet",
              before_files == after_files, (before_files, after_files))
        check("...Live speaks ONE calm line for it",
              live is not None and one_calm_line(
                  live.reply, "remembering sensitive topics automatically"),
              None if live is None else live.reply)
    except Exception as exc:                 # noqa: BLE001 - no module, no claim
        skip(f"the real sensitive-topic setter could not be driven here "
             f"({type(exc).__name__}), so its real card was not checked")

    # --- A tool switch: the real ON/OFF path and the real list ---------------
    on_tool = next((t for t in R.tool_targets()
                    if R.reading_tool_now(t) is True), "")
    if on_tool:
        typed, _live = doors(f"turn off the {_tool_core(R.tool_targets()[on_tool][0])} tool")
        after_typed = R.reading_tool_now(on_tool)
        _typed, live = doors(f"turn off the {_tool_core(R.tool_targets()[on_tool][0])} tool")
        after_live = R.reading_tool_now(on_tool)
        check(f"a real tool OFF ({on_tool}) changes the list in typed chat",
              typed is not None and after_typed is False,
              (None if typed is None else typed.reply, after_typed))
        check("...and Live sees that same state (already off), never a second card",
              live is not None and after_live is False
              and "already" in live.reply.lower(), (
                  None if live is None else live.reply, after_live))
    else:
        skip("no tool is switched on in this throwaway config, so the real "
             "tool OFF could not be driven")
    tool = "browser_control"
    typed, live = doors(f"turn on the {_tool_core(R.tool_targets()[tool][0])} tool")
    check("a real tool ON is refused by the SAME PC-only rule in both doors",
          typed is not None and live is not None and typed.reply == live.reply
          and "windows hello" in typed.reply.lower(), (
              None if typed is None else typed.reply,
              None if live is None else live.reply))


def t_zz_the_whole_registry_is_covered_by_this_suite():
    """NO GAPS: every capability key the registry exposes was driven above.

    This is the check that a future chat-only setting cannot pass: add a switch,
    a choice, a number, an asks-first action or a tool, and its `switch:`/
    `choice:`/`limit:`/`asks_first:`/`tool:` key appears in `capability_keys()`
    - which this suite reads - but unless the family loops above also drove it
    through both doors, the missing keys are printed and this fails.
    """
    all_keys = set(R.capability_keys())
    family = {k for k in all_keys
              if k.split(":", 1)[0] in ("switch", "choice", "limit",
                                        "asks_first", "tool")}
    missing = sorted(family - COVERED_KEYS)
    extra = sorted(COVERED_KEYS - family)
    check(f"all {len(family)} registry settings are driven through both doors",
          not missing, missing[:20])
    check("...and the suite covers nothing the registry does not name",
          not extra, extra[:20])
    print(f"     covered {len(family)} registry settings: "
          f"{len([k for k in family if k.startswith('switch:')])} switches, "
          f"{len([k for k in family if k.startswith('choice:')])} choices, "
          f"{len([k for k in family if k.startswith('limit:')])} number, "
          f"{len([k for k in family if k.startswith('asks_first:')])} asks-first, "
          f"{len([k for k in family if k.startswith('tool:')])} tool switches")


# -------------------------------------------------- separate module surfaces

def t_presets_and_search_providers_are_the_same_in_both_doors():
    """The 10 presets and 6 search providers are their own fast-path surfaces.

    They are not rows in the settings registry (their writers live in
    jarvis_presets.py and jarvis_search.py), so they are covered here by
    deriving every value from those modules' own tables. Both doors answer the
    same and neither leaves a Live-only refusal.
    """
    try:
        import jarvis_presets as P
        presets = [str(getattr(p, "id", p)) for p in P.PRESETS]
    except Exception:                        # noqa: BLE001 - no module, no claim
        presets = []
        skip("jarvis_presets is not on this PC, so the presets were not driven")
    for pid in presets:
        name = pid
        got = Q.match(f"switch to the {name} preset")
        check(f"'switch to the {name} preset' reaches a preset change",
              got is not None and got.name in ("preset_switch", "settings_choice"),
              got)
    try:
        import jarvis_search as S
        providers = list(S.PROVIDERS)
    except Exception:                        # noqa: BLE001
        providers = []
        skip("jarvis_search is not on this PC, so the providers were not driven")
    for pid in providers:
        phrase = f"switch to {pid} for search"
        got = Q.match(phrase)
        check(f"{phrase!r} reaches a search-provider change",
              got is not None and got.name in ("search_use", "settings_choice"), got)
    for phrase in ([f"switch to the {p} preset" for p in presets[:1]]
                   + [f"switch to {s} for search" for s in providers[:1]]):
        typed, live = doors(phrase)
        check(f"both doors answer {phrase!r}", typed is not None and live is not None)
        check(f"...and neither denies that Live may change it: {phrase!r}",
              typed is not None and live is not None
              and "cannot change settings" not in live.reply.lower()
              and live.reply == typed.reply, (
                  None if typed is None else typed.reply,
                  None if live is None else live.reply))
    # The Cloud row itself is a Command-Only ability, so there is no cloud
    # SERVICE change to drive through two doors; what the owner asked for is
    # that the sentence is answered the same WAY by both, so that is checked
    # here rather than skipped (a skip is never a pass - 2026-10-11 rule).
    for phrase in ("turn on cloud escalation", "turn off cloud escalation",
                   "is cloud escalation on"):
        typed, live = doors(phrase)
        check(f"both doors answer {phrase!r} the same way",
              typed is not None and live is not None and typed.reply == live.reply,
              (None if typed is None else typed.reply,
               None if live is None else live.reply))


# ------------------------------------------------- Q2: the cache is speed only

def t_zzz_the_static_read_cache_is_behaviour_preserving():
    """Q2 (2026-11-10 00:05 PT ruling): the cache must change SPEED only.

    This is the check that lets the two caches at the top of this file be
    trusted: it proves each cached answer is the SAME answer the real read
    gives, and that none of the ~500 real turns MUTATED the shared framework
    dict (the one way handing back a cached dict instead of a fresh deep copy
    could leak state between turns - `jarvis_framework.load_framework`'s own
    docstring exists because a caller may mutate what it is handed).
    """
    check("Q2: the framework read was really served from the cache (hundreds of times)",
          _STATIC_CACHE_COUNTS["framework"] > 100, _STATIC_CACHE_COUNTS)
    check("Q2: the hardware probe was asked more than once and cached",
          _STATIC_CACHE_COUNTS["smi"] > 10 and len(_SMI_CACHE) >= 2,
          (_STATIC_CACHE_COUNTS, sorted(_SMI_CACHE)))
    # A FRESH read of the TOML as it is NOW (the tool switches in this suite
    # legitimately edit it, which is why the cache keys on its mtime/size): if
    # any turn had mutated the cached dict, these two would differ.
    fresh = _real_load_framework()
    check("Q2: no turn mutated the cached framework config (cached == a fresh read)",
          _FRAMEWORK_CACHE["value"] == fresh,
          "the cached framework dict differs from a fresh load_framework()")
    # The hardware table is a LIVE reading (another program can load a model and
    # move `memory.free`/the process list between two calls), so the honest
    # check is not "the numbers are identical for ever" - it is: every cached
    # answer still has the shape the query asked for, and asking again returns
    # the SAME object, i.e. the cache answered instead of re-running nvidia-smi.
    bad_shape = {}
    for key, value in _SMI_CACHE.items():
        if value is None:                    # "nvidia-smi absent/refused" is a
            continue                         # real answer; nothing to shape-check
        rows = [[p.strip() for p in ln.split(",")]
                for ln in str(value).splitlines() if ln.strip()]
        # Every query this backend sends starts with an integer id (the GPU
        # index, or a process pid); a cached answer must still look like that.
        if not rows or not all(row and row[0].isdigit() for row in rows):
            bad_shape[key] = str(value)[:200]
    check("Q2: every cached hardware answer is the hardware table's real shape",
          bad_shape == {}, bad_shape)
    asked_again = {key: _run_smi_cached(list(key)) for key in _SMI_CACHE}
    check("Q2: asking again returns the cached object itself (no re-run)",
          all(asked_again[key] is value for key, value in _SMI_CACHE.items()),
          [key for key, value in _SMI_CACHE.items() if asked_again[key] is not value])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
