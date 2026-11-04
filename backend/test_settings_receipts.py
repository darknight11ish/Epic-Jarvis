"""test_settings_receipts.py - receipts for the nine cardless change families.

    python3 backend/test_settings_receipts.py

WHY THIS SUITE EXISTS (2026-11-03, DEF-031). `changeable_words()` has told the
owner 'say "undo" in the same chat if you change your mind' since the settings
registry was written. Most settings changes write that receipt now - but NINE
families reach their module's setter directly and wrote none, so for a wake-word
change, which browser Jarvis uses, an anti-slop scope, the voice speed, the two
captcha hand-off choices, "ask me first" for one action, the approval-card
style, or offering a reading tool to the model, "undo" had nothing to take back.

THE WHOLE CLAIM, MEASURED HERE: for each of those nine families

  1. the real typed sentence, through the real `jarvis_quick.match()` and the
     real `run()`, reaches the real runner;
  2. the setter really ran (the value really changed);
  3. exactly ONE receipt appeared, whose `before` is the value that was there
     and whose `after` is the value it became;
  4. the receipt's own undo puts the value BACK through the setter's own path
     - or, where that path raises its own approval card or keeps a PC-only
     refusal, says so honestly and changes nothing.

It also proves the two negative halves:

  * a change that only WAITS on a card writes NO receipt (nothing happened, so
    there is nothing to take back);
  * a reader that genuinely cannot read returns None, and then no receipt is
    written - the runner never guesses a "before".

WHAT THIS SUITE STUBS, SAID PLAINLY. No model and no network run. The two
modules that raise an approval card on a live PC (`jarvis_speech`'s wake-word
card, `jarvis_asks_first`'s loosening card) have their card THREAD replaced by a
no-op, so a suite never opens a real card; the refusal paths and their words are
the modules' own and are asserted. The receipts database is a throwaway file
under the temporary folder (JARVIS_RECEIPTS_DB), and every settings file the
setters touch is a COPY of the shipped `jarvis-framework.toml` - the
repository's own file and the owner's desk are never written.
"""
from __future__ import annotations

import dataclasses
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

#: A plain run must not write bytecode into the tree it tests (the rule
#: test_settings_tool.py states at its own top: a staged run's pycache would
#: make backend/test_base_matches_repo.py fail on the NEXT run).
sys.dont_write_bytecode = True

#: BEFORE ANY BACKEND IMPORT: a throwaway settings folder and a COPY of the
#: shipped framework file. `jarvis_framework` reads CONFIG_DIR at import, and
#: the asks-first / tools seeds below write jarvis-framework.toml - so the
#: copy is what they write, never the repository's own file.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-settings-receipts-"))
_CFG = _TMP / "config"
_CFG.mkdir(parents=True, exist_ok=True)
_TOML = _TMP / "jarvis-framework.toml"
shutil.copyfile(REPO / "backend" / "rebuilt" / "jarvis-framework.toml", _TOML)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_CFG)
os.environ["JARVIS_CONFIG_DIR"] = str(_CFG)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TOML)
#: The receipts store needs its OWN variable: a run at the owner's desk must
#: never write real rows into his receipts.db (test_settings_tool.py's own
#: measured note, 2026-11-03: 20 rows in four minutes). Since R5 the module
#: also honours OPENJARVIS_CONFIG_DIR / JARVIS_CONFIG_DIR first, but the
#: explicit file is still the pin this suite wants.
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")

sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_settings_registry.py",
                "jarvis_asks_first.py", "jarvis_antislop.py",
                "jarvis_browser_engine.py", "jarvis_card_summary.py",
                "jarvis_speech.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_antislop as AS  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_browser_engine as BE  # noqa: E402
import jarvis_card_summary as CS  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_receipts as RC  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402
import jarvis_speech as SP  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class _SchedStub:
    """`run()`'s scheduler calls: nothing is written anywhere."""

    def mark_command(self, text):
        return None

    def forget_set(self, cid):
        return None

    def last_set(self, cid, now):
        return None


def _drive(text, conv, *, peer=None, local=None):
    """The real matcher, then the real runner - what a chat turn does."""
    intent = Q.match(text)
    if intent is None:
        return None, None
    return intent, Q.run(intent, _SchedStub(), time.time(),
                         conversation=conv, peer=peer, local=local)


def _receipt_count():
    return len(RC.recent(200))


def _one_new_receipt(count_before):
    """The single new receipt, or None when the count did not move by one."""
    rows = RC.recent(200)
    if len(rows) != count_before + 1:
        return None
    return rows[0] if rows else None


def _choice_value(key: str):
    """One ChoiceSetting's current value in the VALUE its setter takes."""
    setting = next((c for c in R.CHOICE_SETTINGS if c.key == key), None)
    if setting is None:
        return None
    words = R.current_value(setting)
    return R.choice_from_words(setting, words) if words else None


def _undo(conv, *, peer=None, local=None):
    """The owner's own "undo" in that chat, through the real undo path."""
    return Q._run_undo({"noun": None, "soft": False}, _SchedStub(), time.time(),
                       conv, peer=peer, local=local)


def _before_value(row):
    return (row or {}).get("before") or {}


def _after_value(row):
    return (row or {}).get("after") or {}


# ---------------------------------------------------------------------------
#   1. The PC's "hey Jarvis" wake-word switch (jarvis_speech.py)
# ---------------------------------------------------------------------------

def t_wake_word_change_leaves_one_receipt_and_its_card_guards_the_way_back():
    """One REAL change on a two-state switch: OFF is instant, ON raises the
    module's own card.

    The before value is READ through the module's own reader
    (`_wake_word_now`), never assumed from `not on`, so a sentence that changes
    nothing writes no receipt at all - that case is the no-op test below.

    Both halves are proved here: ON while the card waits writes NO receipt
    (nothing happened), and the instant OFF writes exactly one whose undo asks
    for that same card instead of silently turning the microphone back on.
    """
    real_spawn = SP._spawn
    SP._spawn = lambda fn: None            # no card thread in a suite
    conv = "receipts-wake-word-01"
    try:
        SP._reset_wake_for_tests()
        SP.set_wake_enabled(False)
        count = _receipt_count()
        intent, res = _drive("turn on the wake word", conv)
        check("'turn on the wake word' reaches the wake-word runner",
              intent is not None and intent.name == "settings_wake_word"
              and intent.f.get("on") is True, intent)
        check("...a carded change says the card is waiting, in the module's own words",
              res is not None and "Approve the card" in res.reply,
              None if res is None else res.reply)
        check("...and writes NO receipt, because nothing has changed yet",
              _receipt_count() == count, (count, _receipt_count()))

        SP._reset_wake_for_tests()
        check("seed: the switch is ON for the change under test",
              SP._write_wake(True) is None and SP._wake_enabled() is True,
              SP._wake_enabled())
        count = _receipt_count()
        intent, res = _drive("turn off the wake word", conv)
        check("'turn off the wake word' reaches the same runner",
              intent is not None and intent.name == "settings_wake_word"
              and intent.f.get("on") is False, intent)
        check("...the change really happened",
              SP._wake_enabled() is False, SP._wake_enabled())
        row = _one_new_receipt(count)
        check("...and it left exactly ONE receipt",
              row is not None, (count, _receipt_count()))
        check("...under the settings tool's own name",
              (row or {}).get("tool_name") == Q.SETTINGS_RECEIPT_TOOL,
              (row or {}).get("tool_name"))
        check("...whose before is ON and whose after is OFF",
              _before_value(row).get("kind") == "wake_word"
              and _before_value(row).get("value") is True
              and _after_value(row).get("value") is False,
              ((row or {}).get("before"), (row or {}).get("after")))
        undo = _undo(conv)
        check("undo raises the wake word's own card instead of turning it back on",
              undo is not None and "raised its own card" in undo.reply
              and "nothing was changed" in undo.reply,
              None if undo is None else undo.reply)
        check("...and the microphone is still off", SP._wake_enabled() is False,
              SP._wake_enabled())
    finally:
        SP._spawn = real_spawn
        SP._reset_wake_for_tests()
        SP.set_wake_enabled(False)


def t_wake_word_no_op_change_writes_no_receipt_and_undo_leaves_the_mic_alone():
    """R4's no-op guard (2026-11-03 review, BUG 3).

    `jarvis_speech.set_wake_enabled(True)` while the switch is ALREADY on
    answers "The wake word is already on." and changes nothing, so NO receipt
    may be written for it. Before the guard a receipt claiming `before: true`
    was written, and its undo calls `set_wake_enabled(False)`, which is instant
    and cardless - so "turn on the wake word" (already on) then "undo"
    silently switched the microphone OFF. The same guard covers OFF while
    already off, which is the same code path.
    """
    real_spawn = SP._spawn
    SP._spawn = lambda fn: None            # no card thread in a suite
    conv = "receipts-wake-word-noop-01"
    try:
        SP._reset_wake_for_tests()
        check("seed: the wake word is ON",
              SP._write_wake(True) is None and SP._wake_enabled() is True,
              SP._wake_enabled())
        count = _receipt_count()
        intent, res = _drive("turn on the wake word", conv)
        check("'turn on the wake word' while it is already on says so, in the "
              "module's own words",
              intent is not None and intent.name == "settings_wake_word"
              and res is not None and "already on" in res.reply,
              None if res is None else res.reply)
        check("...and writes NO receipt, because nothing changed",
              _receipt_count() == count, (count, _receipt_count()))
        check("...and this chat has nothing to take back",
              not Q._SETTINGS_UNDO.get(conv), Q._SETTINGS_UNDO.get(conv))
        undone = _undo(conv)
        check("...so 'undo' changes nothing and says there is nothing to take back",
              undone is not None and undone.reply == Q.UNDO_NOTHING_SAID
              and SP._wake_enabled() is True,
              (None if undone is None else undone.reply, SP._wake_enabled()))

        # The other direction is the same code path: OFF while already off.
        SP._reset_wake_for_tests()
        SP.set_wake_enabled(False)
        count = _receipt_count()
        intent, res = _drive("turn off the wake word", conv)
        check("'turn off the wake word' while it is already off writes NO receipt either",
              intent is not None and intent.name == "settings_wake_word"
              and _receipt_count() == count,
              (None if res is None else res.reply, count, _receipt_count()))
        check("...and 'undo' still leaves the microphone off",
              _undo(conv) is not None and SP._wake_enabled() is False,
              SP._wake_enabled())
    finally:
        SP._spawn = real_spawn
        SP._reset_wake_for_tests()
        SP.set_wake_enabled(False)


# ---------------------------------------------------------------------------
#   2. Which browser Jarvis uses (jarvis_browser_engine.py)
# ---------------------------------------------------------------------------

def t_browser_mode_change_leaves_one_receipt_and_undo_puts_it_back():
    """The mode is a module setting, not a row: before comes from
    `browser_mode_now()`, the module's own current mode."""
    check("seed: the browser starts visible",
          BE.set_mode("visible").get("ok") is True
          and R.browser_mode_now() == "visible", R.browser_mode_now())
    conv = "receipts-browser-01"
    count = _receipt_count()
    intent, res = _drive("set the browser to headless", conv)
    check("'set the browser to headless' reaches the browser runner",
          intent is not None and intent.name == "settings_browser_mode"
          and intent.f.get("mode") == "headless", intent)
    check("...the change really happened",
          BE.settings().get("mode") == "headless", BE.settings())
    row = _one_new_receipt(count)
    check("...and it left exactly ONE receipt with the module's own before",
          row is not None
          and _before_value(row).get("kind") == "browser_mode"
          and _before_value(row).get("value") == "visible"
          and _after_value(row).get("value") == "headless",
          ((row or {}).get("before"), (row or {}).get("after")))
    undo = _undo(conv)
    check("undo puts the previous mode back through the same setter",
          undo is not None and "which browser Jarvis uses" in undo.reply
          and BE.settings().get("mode") == "visible",
          (None if undo is None else undo.reply, BE.settings()))
    BE.set_mode("auto")


# ---------------------------------------------------------------------------
#   3. One Anti-Slop scope (jarvis_antislop.py)
# ---------------------------------------------------------------------------

def t_antislop_scope_leaves_exactly_one_receipt_and_undo_puts_it_back():
    """The module records its OWN receipt for every write, so the runner's
    receipt call must be suppressed by the `since` guard: ONE receipt, never
    two (DEF-031 sub-cause 3's two instruments, measured). R4 (2026-11-03):
    that one receipt must also be reachable by the chat's own "undo"."""
    AS.set_scope("code", True)
    conv = "receipts-antislop-01"
    count = _receipt_count()
    intent, res = _drive("turn off anti-slop for code", conv)
    check("'turn off anti-slop for code' reaches the scope runner",
          intent is not None and intent.name == "settings_antislop_scope"
          and intent.f.get("scope") == "code" and intent.f.get("on") is False,
          intent)
    check("...the scope really changed",
          R.antislop_scope_now("code") is False, R.antislop_scope_now("code"))
    row = _one_new_receipt(count)
    check("...and it left exactly ONE receipt, not two",
          row is not None, (count, _receipt_count()))
    check("...the module's own, under the module's own name",
          (row or {}).get("tool_name") == "antislop",
          (row or {}).get("tool_name"))
    check("...holding the whole filter state, with code off in the after",
          (_after_value(row).get("scopes") or {}).get("code") is False,
          (row or {}).get("after"))
    undone = _undo(conv)
    check("'undo' in this chat takes the module's own receipt back (R4: it "
          "used to answer there was nothing to take back)",
          undone is not None and R.antislop_scope_now("code") is True,
          None if undone is None else undone.reply)
    # The registry's own `antislop_scope` restore kind is there too: it is the
    # path a snapshot uses if this module's own recording ever stops. Drive it
    # directly, through the real setter.
    AS.set_scope("copy", False)
    restored = Q._restore_settings_change(
        {"kind": "antislop_scope", "key": "antislop_scope:copy", "value": True})
    check("the antislop_scope restore kind puts one scope back through its setter",
          restored.ok is True and R.antislop_scope_now("copy") is True,
          (getattr(restored, "ok", None), R.antislop_scope_now("copy")))


def t_antislop_filter_toggle_is_undoable_by_chat():
    """R4 (2026-11-03): "turn on the anti-slop filter" is a plain switch
    sentence, but its module records its own receipt - the chat's "undo" has
    to find that receipt, or the promise "say undo" is broken for it."""
    AS.set_enabled(False)
    conv = "receipts-antislop-filter-01"
    count = _receipt_count()
    intent, res = _drive("turn on the anti-slop filter", conv)
    check("'turn on the anti-slop filter' reaches a switch runner for antislop",
          intent is not None
          and intent.name in ("settings_bool", "feature_switch")
          and intent.f.get("key") == "antislop" and intent.f.get("on") is True,
          intent)
    check("...the filter really turned on",
          (AS.get_state() or {}).get("enabled") is True,
          (AS.get_state() or {}).get("enabled"))
    row = _one_new_receipt(count)
    check("...and it left exactly ONE receipt, the module's own",
          row is not None and (row or {}).get("tool_name") == AS.TOOL_NAME,
          (count, _receipt_count(), (row or {}).get("tool_name")))
    # BUG 2 (2026-11-03 review): the chat's pointer must name the row the
    # module RETURNED for this change, never "whatever row is newest" - another
    # chat or either Settings screen can write one in the same clock tick, and
    # its undo would then put back someone else's change.
    entry = Q._SETTINGS_UNDO.get(conv) or {}
    check("...and this chat's undo points at THAT row, not at the newest one",
          bool(entry) and entry.get("receipt_id") == (row or {}).get("receipt_id"),
          (entry, (row or {}).get("receipt_id")))
    check("...and the pointer carries no empty before-snapshot to be read as "
          "'that setting is not on this PC any more'",
          bool(entry) and "before" not in entry, entry)
    undone = _undo(conv)
    check("'undo' in this chat turns the filter back off",
          undone is not None and (AS.get_state() or {}).get("enabled") is False,
          None if undone is None else undone.reply)
    check("...and says what it did, instead of claiming nothing happened",
          undone is not None and "back the way it was" in undone.reply,
          None if undone is None else undone.reply)
    again = _undo(conv)
    check("a SECOND 'undo' is honest: it says the filter is already back, and "
          "leaves it off",
          again is not None and "already put" in again.reply
          and "nothing left to undo" in again.reply
          and (AS.get_state() or {}).get("enabled") is False,
          (None if again is None else again.reply,
           (AS.get_state() or {}).get("enabled")))


def t_antislop_mode_change_leaves_one_receipt_and_undo_puts_it_back():
    """R4 (2026-11-03): the Anti-Slop mode is a named CHOICE
    (`_run_settings_choice`), and its module records its own receipt too - so
    the same exact-id bridge has to work for the second of the three Anti-Slop
    settings, not just the master switch."""
    AS.set_mode("during")
    check("seed: the filter works as it writes",
          _choice_value("antislop_mode") == "during", _choice_value("antislop_mode"))
    conv = "receipts-antislop-mode-01"
    count = _receipt_count()
    intent, res = _drive("set the anti-slop mode to after", conv)
    check("'set the anti-slop mode to after' reaches the choice runner",
          intent is not None and intent.name == "settings_choice"
          and intent.f.get("key") == "antislop_mode"
          and intent.f.get("value") == "after", intent)
    check("...the mode really changed",
          _choice_value("antislop_mode") == "after", _choice_value("antislop_mode"))
    row = _one_new_receipt(count)
    check("...and it left exactly ONE receipt, the module's own",
          row is not None and (row or {}).get("tool_name") == AS.TOOL_NAME,
          (count, _receipt_count(), (row or {}).get("tool_name")))
    entry = Q._SETTINGS_UNDO.get(conv) or {}
    check("...and this chat's undo points at that exact row",
          bool(entry) and entry.get("receipt_id") == (row or {}).get("receipt_id"),
          (entry, (row or {}).get("receipt_id")))
    undone = _undo(conv)
    check("'undo' in this chat puts the mode back",
          undone is not None and _choice_value("antislop_mode") == "during",
          (None if undone is None else undone.reply, _choice_value("antislop_mode")))


def t_antislop_pointer_ignores_a_receipt_written_in_between():
    """BUG 2 (2026-11-03 review): identity comes from the id the module
    RETURNED, never from "the newest row in the database".

    Reproduced exactly as the review describes it: a receipt is written by
    another surface between the setter's own write and this file's decision, so
    the newest row is no longer the Anti-Slop row. Before the fix the pointer
    was set from that newest row (or from nothing at all), so "undo" in this
    chat could put back someone else's change - or answer that there was
    nothing to take back right after telling the owner to say undo.
    """
    setting = next((b for b in R.BOOL_SETTINGS if b.key == "antislop"), None)
    if setting is None:                     # a tree without the filter: nothing to prove
        return
    real_set, real_record = setting.set, RC.record
    real_settings = R.BOOL_SETTINGS
    other_ids = []

    def noisy_set(on, *, peer=None, local=None):
        out = real_set(on, peer=peer, local=local)
        # Another chat, or either Settings screen, writes its own receipt
        # inside THIS change - the race the review measured.
        other_ids.append(real_record("other_tool", "a change from somewhere else"))
        return out

    # `BoolSetting` is a frozen dataclass, so the row is swapped for a copy of
    # itself with the same names and the noisy setter - everything else about
    # the row is the real one.
    R.BOOL_SETTINGS = tuple(dataclasses.replace(b, set=noisy_set)
                            if b.key == "antislop" else b for b in real_settings)
    conv = "receipts-antislop-race-01"
    try:
        AS.set_enabled(False)
        intent, res = _drive("turn on the anti-slop filter", conv)
        check("the race test really reached the switch runner",
              intent is not None and intent.name in ("settings_bool", "feature_switch")
              and intent.f.get("key") == "antislop", intent)
        rows = RC.recent(4)
        check("the newest row in the database is NOT this change's (the race is real)",
              bool(rows) and rows[0].get("tool_name") == "other_tool",
              [(r.get("tool_name"), r.get("receipt_id")) for r in rows])
        mine = next((r for r in rows if r.get("tool_name") == AS.TOOL_NAME), None)
        pointer = (Q._SETTINGS_UNDO.get(conv) or {}).get("receipt_id")
        check("...and this chat's undo still points at the anti-slop row, not at it",
              bool(pointer) and mine is not None
              and pointer == mine.get("receipt_id"),
              (pointer, None if mine is None else mine.get("receipt_id")))
        undone = _undo(conv)
        other = RC.get(str(other_ids[0])) if other_ids and other_ids[0] else None
        check("...so 'undo' takes back the filter, not the other surface's change",
              undone is not None
              and (AS.get_state() or {}).get("enabled") is False
              and bool(other) and other.get("undone") is False,
              (None if undone is None else undone.reply,
               [(r.get("tool_name"), r.get("undone")) for r in RC.recent(4)]))
    finally:
        R.BOOL_SETTINGS = real_settings
        AS.set_enabled(False)


# ---------------------------------------------------------------------------
#   4-6. The three named-choice families that arrive through _run_control_set
# ---------------------------------------------------------------------------

def _choice_family_check(family, sentence_for, key):
    """One shared check for a named choice: change, receipt, undo."""
    conv = f"receipts-{family}-01"
    before = _choice_value(key)
    target = sentence_for(before)
    count = _receipt_count()
    intent, res = _drive(target["sentence"], conv)
    check(f"{target['sentence']!r} reaches the control setter for {key}",
          intent is not None and intent.name == "control_set"
          and intent.f.get("key") == key == target["key"]
          and intent.f.get("value") == target["value"], intent)
    check(f"...{key} really changed",
          _choice_value(key) == target["value"],
          (_choice_value(key), target["value"]))
    row = _one_new_receipt(count)
    check(f"...and it left exactly ONE receipt for {key}",
          row is not None, (count, _receipt_count()))
    check(f"...whose before is the value that was there and after is the new one",
          _before_value(row).get("key") == key
          and _before_value(row).get("value") == before
          and _after_value(row).get("value") == target["value"],
          (before, (row or {}).get("before"), (row or {}).get("after")))
    undo = _undo(conv)
    check(f"undo puts {key} back through the same setter",
          undo is not None and _choice_value(key) == before,
          (None if undo is None else undo.reply, _choice_value(key), before))


def t_voice_speed_change_leaves_one_receipt_and_undo_puts_it_back():
    """`set the voice speed to faster` - a CHOICE_SETTINGS row reached by the
    generic control grammar, which had no receipt before."""
    def sentence_for(before):
        value = "faster" if before != "faster" else "normal"
        return {"sentence": f"set the voice speed to {value}", "key": "voice_speed",
                "value": value}
    _choice_family_check("voice-speed", sentence_for, "voice_speed")


def t_voice_speed_natural_verb_door_leaves_one_receipt_too():
    """"speak faster" / "make the voice faster" is the SECOND door to the SAME
    `voice_speed` row (the dedicated `voice_speed` reflex, not the generic
    control grammar). Q1b originally receipted only the generic door, so the
    family was still cardless through this one - both must leave the same ONE
    receipt, with the same before/after and the same undo."""
    before = _choice_value("voice_speed")
    target = "faster" if before != "faster" else "normal"
    sentence = "speak faster" if target == "faster" else "speak at the normal speed"
    conv = "receipts-voice-speed-natural-01"
    count = _receipt_count()
    intent, res = _drive(sentence, conv)
    check(f"{sentence!r} is the natural-verb speaking-speed door",
          intent is not None and intent.name == "voice_speed"
          and intent.f.get("speed") == target, intent)
    check("...and its sibling wording reaches the same door",
          Q.match("make the voice faster") is not None
          and Q.match("make the voice faster").name == "voice_speed",
          Q.match("make the voice faster"))
    check("...the speaking speed really changed",
          _choice_value("voice_speed") == target,
          (_choice_value("voice_speed"), target))
    row = _one_new_receipt(count)
    check("...and it left exactly ONE receipt",
          row is not None, (count, _receipt_count()))
    check("...whose before is the old speed and after is the new one",
          _before_value(row).get("key") == "voice_speed"
          and _before_value(row).get("value") == before
          and _after_value(row).get("value") == target,
          (before, (row or {}).get("before"), (row or {}).get("after")))
    undo = _undo(conv)
    check("undo puts the speaking speed back through the row's own setter",
          undo is not None and _choice_value("voice_speed") == before,
          (None if undo is None else undo.reply, _choice_value("voice_speed"), before))


def t_handoff_mode_change_leaves_one_receipt_and_undo_respects_its_card():
    """The captcha hand-off's two choices. "Stop early" is instant; "Keep
    offering it" is the loosening, so it raises ONE card.

    The receipted change is therefore the instant direction (seeded to the
    risky value through the module's own writer, as the owner's approved choice
    would have left it); the rollback goes back to the carded value, and must
    report that card instead of silently keeping the hand-off longer."""
    import jarvis_handoff_mode as HM
    real_spawn = HM._spawn
    HM._spawn = lambda fn: None
    conv = "receipts-handoff-mode-01"
    try:
        HM.set_mode(HM.KEEP_OFFERING)
        check("seed: the hand-off keeps offering for the full 15 minutes",
              HM.settings()["mode"] == HM.KEEP_OFFERING
              and _choice_value("handoff_mode") == "keep_offering",
              HM.settings())
        count = _receipt_count()
        intent, res = _drive("set the handoff mode to stop early", conv)
        check("'set the handoff mode to stop early' reaches the control setter",
              intent is not None and intent.name == "control_set"
              and intent.f.get("key") == "handoff_mode"
              and intent.f.get("value") == "stop_early", intent)
        check("...the instant direction really changed",
              _choice_value("handoff_mode") == "stop_early",
              _choice_value("handoff_mode"))
        row = _one_new_receipt(count)
        check("...and it left exactly ONE receipt",
              row is not None, (count, _receipt_count()))
        check("...whose before is keep-offering and after is stop-early",
              _before_value(row).get("key") == "handoff_mode"
              and _before_value(row).get("value") == "keep_offering"
              and _after_value(row).get("value") == "stop_early",
              ((row or {}).get("before"), (row or {}).get("after")))
        undo = _undo(conv)
        check("undo of the loosening raises its own card, and nothing changes",
              undo is not None and "nothing was changed" in undo.reply,
              None if undo is None else undo.reply)
        check("...so the hand-off still stops early",
              _choice_value("handoff_mode") == "stop_early",
              _choice_value("handoff_mode"))

        # The other direction is the carded one: it must write NO receipt.
        with HM._LOCK:
            HM._PENDING.clear()
        count = _receipt_count()
        intent, res = _drive("set the handoff mode to patient", conv)
        check("the CARDED direction says the card is waiting",
              res is not None and "Waiting for your approval" in res.reply,
              None if res is None else res.reply)
        check("...and writes NO receipt, because nothing has changed yet",
              _receipt_count() == count, (count, _receipt_count()))
    finally:
        HM._spawn = real_spawn
        with HM._LOCK:
            HM._PENDING.clear()
        HM.set_mode(HM.STOP_EARLY)


def t_handoff_front_change_leaves_one_receipt_and_undo_respects_its_card():
    """Whether the captcha window comes to the front. "Leave it where it is" is
    instant; "Bring it to the front" takes the owner's screen, so it is carded."""
    import jarvis_handoff_front as HF
    real_spawn = HF._spawn
    HF._spawn = lambda fn: None
    conv = "receipts-handoff-front-01"
    try:
        HF.set_mode(HF.BRING_TO_FRONT)
        check("seed: the captcha window comes to the front",
              HF.settings()["mode"] == HF.BRING_TO_FRONT
              and _choice_value("handoff_front") == "bring_to_front",
              HF.settings())
        count = _receipt_count()
        intent, res = _drive("set the handoff window to leave it in place", conv)
        check("'set the handoff window to leave it in place' reaches the control setter",
              intent is not None and intent.name == "control_set"
              and intent.f.get("key") == "handoff_front"
              and intent.f.get("value") == "leave_in_place", intent)
        check("...the instant direction really changed",
              _choice_value("handoff_front") == "leave_in_place",
              _choice_value("handoff_front"))
        row = _one_new_receipt(count)
        check("...and it left exactly ONE receipt",
              row is not None, (count, _receipt_count()))
        check("...whose before is bring-to-front and after is leave-in-place",
              _before_value(row).get("key") == "handoff_front"
              and _before_value(row).get("value") == "bring_to_front"
              and _after_value(row).get("value") == "leave_in_place",
              ((row or {}).get("before"), (row or {}).get("after")))
        undo = _undo(conv)
        check("undo of bringing it forward raises its own card, and nothing changes",
              undo is not None and "nothing was changed" in undo.reply,
              None if undo is None else undo.reply)
        check("...so the window still stays where it is",
              _choice_value("handoff_front") == "leave_in_place",
              _choice_value("handoff_front"))
    finally:
        HF._spawn = real_spawn
        with HF._LOCK:
            HF._PENDING.clear()
        HF.set_mode(HF.LEAVE_IN_PLACE)


# ---------------------------------------------------------------------------
#   7. "What asks first" for one action (jarvis_asks_first.py)
# ---------------------------------------------------------------------------

def t_asks_first_change_leaves_one_receipt_and_undo_respects_its_card():
    """Stricter is instant; the rollback (going looser) is the PC only, one
    card plus Windows Hello. The receipt must make that refusal, not skip it."""
    real_spawn = AF._spawn
    AF._spawn = lambda fn: None            # no card thread in a suite
    conv = "receipts-asks-first-01"
    try:
        AF.set_tier("calendar_read", "auto")
        check("seed: calendar reads do not ask first",
              R.asks_first_now("calendar_read") is False,
              R.asks_first_now("calendar_read"))
        count = _receipt_count()
        intent, res = _drive("ask me first before jarvis reads my calendar", conv)
        check("the stricter sentence reaches the asks-first runner",
              intent is not None and intent.name == "settings_asks_first"
              and intent.f.get("action") == "calendar_read"
              and intent.f.get("ask") is True, intent)
        check("...the switch really changed",
              R.asks_first_now("calendar_read") is True,
              R.asks_first_now("calendar_read"))
        row = _one_new_receipt(count)
        check("...and it left exactly ONE receipt",
              row is not None, (count, _receipt_count()))
        check("...whose before is not-asking and after is asking",
              _before_value(row).get("kind") == "asks_first"
              and _before_value(row).get("value") is False
              and _after_value(row).get("value") is True,
              ((row or {}).get("before"), (row or {}).get("after")))
        undo = _undo(conv)
        check("undo of a loosening is refused, and says nothing was changed",
              undo is not None and "nothing was changed" in undo.reply,
              None if undo is None else undo.reply)
        check("...so it still asks first", R.asks_first_now("calendar_read") is True,
              R.asks_first_now("calendar_read"))
    finally:
        AF._spawn = real_spawn
        AF._L_STATE["pending"].clear()
        AF.set_tier("calendar_read", "auto")


# ---------------------------------------------------------------------------
#   8. How much of an approval card is shown (jarvis_card_summary.py)
# ---------------------------------------------------------------------------

def t_card_mode_change_leaves_one_receipt_and_undo_puts_it_back():
    CS.set_mode(CS.START_SHORT)
    check("seed: cards start short", R.card_mode_now() == CS.START_SHORT,
          R.card_mode_now())
    conv = "receipts-card-mode-01"
    count = _receipt_count()
    intent, res = _drive("always show the whole approval card", conv)
    check("'always show the whole approval card' reaches the card-mode runner",
          intent is not None and intent.name == "settings_card_mode"
          and intent.f.get("mode") == CS.ALWAYS_FULL, intent)
    check("...the mode really changed", CS.card_mode() == CS.ALWAYS_FULL,
          CS.card_mode())
    row = _one_new_receipt(count)
    check("...and it left exactly ONE receipt with the old mode as before",
          row is not None
          and _before_value(row).get("kind") == "card_mode"
          and _before_value(row).get("value") == CS.START_SHORT
          and _after_value(row).get("value") == CS.ALWAYS_FULL,
          ((row or {}).get("before"), (row or {}).get("after")))
    undo = _undo(conv)
    check("undo puts the card style back through the same setter",
          undo is not None and CS.card_mode() == CS.START_SHORT,
          (None if undo is None else undo.reply, CS.card_mode()))


# ---------------------------------------------------------------------------
#   9. Offering a reading tool to the AI model (jarvis_asks_first.py)
# ---------------------------------------------------------------------------

def t_reading_tool_change_leaves_one_receipt_and_undo_respects_its_card():
    """OFF is instant and receipted; the rollback (ON) is the PC only, one card
    plus Windows Hello, so undo must report that and change nothing."""
    real_spawn = AF._spawn
    AF._spawn = lambda fn: None
    conv = "receipts-reading-tool-01"
    try:
        AF.set_tools_enabled("email_read", True)
        check("seed: the email tool is offered to the model",
              R.reading_tool_now("email_read") is True,
              R.reading_tool_now("email_read"))
        count = _receipt_count()
        intent, res = _drive("don't let the ai model read my email", conv)
        check("the OFF sentence reaches the reading-tool runner",
              intent is not None and intent.name == "settings_tool"
              and intent.f.get("tool") == "email_read"
              and intent.f.get("on") is False, intent)
        check("...the tool really stopped being offered",
              R.reading_tool_now("email_read") is False,
              R.reading_tool_now("email_read"))
        row = _one_new_receipt(count)
        check("...and it left exactly ONE receipt",
              row is not None, (count, _receipt_count()))
        check("...whose before is offered and after is not",
              _before_value(row).get("kind") == "reading_tool"
              and _before_value(row).get("value") is True
              and _after_value(row).get("value") is False,
              ((row or {}).get("before"), (row or {}).get("after")))
        undo = _undo(conv)
        check("undo of offering it back is refused, and says nothing was changed",
              undo is not None and "nothing was changed" in undo.reply,
              None if undo is None else undo.reply)
        check("...so it is still not offered",
              R.reading_tool_now("email_read") is False,
              R.reading_tool_now("email_read"))
    finally:
        AF._spawn = real_spawn
        AF._T_STATE["pending"].clear()


# ---------------------------------------------------------------------------
#   10. A reader that cannot read means NO receipt, never a guessed before
# ---------------------------------------------------------------------------

def t_no_reader_means_no_receipt_and_the_answer_still_tells_the_truth():
    """The "no reader, no receipt" half. A before snapshot that would be a
    guess is worse than none: it would let "undo" put back a value the owner
    never had. The change itself still happens and is still answered in the
    setter's own words."""
    real_reader = R.browser_mode_now
    R.browser_mode_now = lambda: None
    conv = "receipts-no-reader-01"
    try:
        BE.set_mode("auto")
        count = _receipt_count()
        intent, res = _drive("set the browser to visible", conv)
        check("the change still runs when the reader cannot read",
              intent is not None and intent.name == "settings_browser_mode"
              and BE.settings().get("mode") == "visible", BE.settings())
        check("...and NO receipt is written for it",
              _receipt_count() == count, (count, _receipt_count()))
        check("...and the answer is the setter's own true sentence",
              res is not None and "which browser Jarvis uses" in res.reply,
              None if res is None else res.reply)
        check("...so 'undo' has nothing to guess at",
              _undo(conv) is not None and _undo(conv).reply == Q.UNDO_NOTHING_SAID,
              _undo(conv).reply if _undo(conv) else None)
    finally:
        R.browser_mode_now = real_reader
        BE.set_mode("auto")


if __name__ == "__main__":
    for fn in (t_wake_word_change_leaves_one_receipt_and_its_card_guards_the_way_back,
               t_wake_word_no_op_change_writes_no_receipt_and_undo_leaves_the_mic_alone,
               t_browser_mode_change_leaves_one_receipt_and_undo_puts_it_back,
               t_antislop_scope_leaves_exactly_one_receipt_and_undo_puts_it_back,
               t_antislop_filter_toggle_is_undoable_by_chat,
               t_antislop_mode_change_leaves_one_receipt_and_undo_puts_it_back,
               t_antislop_pointer_ignores_a_receipt_written_in_between,
               t_voice_speed_change_leaves_one_receipt_and_undo_puts_it_back,
               t_voice_speed_natural_verb_door_leaves_one_receipt_too,
               t_handoff_mode_change_leaves_one_receipt_and_undo_respects_its_card,
               t_handoff_front_change_leaves_one_receipt_and_undo_respects_its_card,
               t_asks_first_change_leaves_one_receipt_and_undo_respects_its_card,
               t_card_mode_change_leaves_one_receipt_and_undo_puts_it_back,
               t_reading_tool_change_leaves_one_receipt_and_undo_respects_its_card,
               t_no_reader_means_no_receipt_and_the_answer_still_tells_the_truth):
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
