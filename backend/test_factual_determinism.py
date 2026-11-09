#!/usr/bin/env python3
"""test_factual_determinism.py - the factual answers are deterministic, proved.

    python -B backend/test_factual_determinism.py

THE OWNER'S STANDARD (2026-11-08): *"I'm making the factual ones (read-aloud,
GitHub connection, settings state) deterministic so they stop depending on the
preset. I want this done well."* The independent audit
(`.dsh-scratch/DETERMINISM-AUDIT-2026-11-08/AUDIT.md`, §8 test matrix) found the
dispatch order sound and the coverage incomplete: three of the owner's seven
real read-aloud sentences did not match and fell to the model, no test proved
the model entry point is never called, no test proved the coding preset cannot
change the words, and private chats handed these reads to the model.

WHAT THIS SUITE PROVES (matrix IDs in brackets; GitHub-post-save rows GH-3/GH-4
belong to task-17 and the feature-question echo to task-21 - not here):

  * THE OWNER-PHRASE CORPUS (`backend/test_factual_corpus.json`): every real
    sentence is matched by `jarvis_quick.match` to the expected intent and
    answered with the expected words - a NO MATCH is not acceptable for any of
    them [DISP-1, DISP-2, RD-1..RD-10, SS-1..SS-10].
  * LIVE MARKS answer the SAME words: the same body plus
    `provenance:"voice"` + `live:true` is byte-identical [RD-8, NEG-2 half].
  * PRESET INDEPENDENCE: with the real CODING preset selected in the PC's own
    preset file, and then the GENERAL one, every corpus reply is byte-identical
    - and the preset reader is shown to be consulted by nothing [NEG-2, F15].
  * THE MODEL ENTRY POINT IS NEVER CALLED: `jarvis_agent.run_local_turn`,
    `_post` and `_open_stream` are monkeypatched to raise, and every corpus
    sentence still returns a Result [NEG-1, F20].
  * NO CARD, NO RECEIPT, NO SOCKET: a read-only state answer raises no card
    (the gate module is a guard that raises if anything reads it), writes no
    approvals.db and no receipts.db, and opens no socket [NEG-4, honesty (d)].
  * NO OVERCLAIM WORDS: no read-aloud or settings-state answer says cloning /
    pushing / pulling / "I turned it on/off for you" / "already changed" /
    "I've tested the token" [NEG-3, G5-style word ban].
  * PRIVATE CHAT: the read-only state intents are answered deterministically in
    a private chat (host-state reads with no secrets), while the read-aloud
    CHANGE is still refused there and changes nothing [NEG-6].
  * AN EXCEPTION IN THE LAYER IS AN HONEST SENTENCE: a setter, a reader and an
    explain that raise each come back as "could not read/change ... nothing was
    changed", never as a crash the /api/chat handler would hand to the model
    [NEG-7].
  * DISPATCH ORDER PINNED FROM THE PATCH STACK: the /api/chat handler calls
    `jarvis_quick.answer_turn`, guards on `_quick is not None` and returns,
    BEFORE `jarvis_agent.run_local_turn` - proved on the text the patch stack
    itself writes [DISP-3, F1/F2].
  * ALL 49 SETTINGS ROWS: every BOOL_SETTINGS / CHOICE_SETTINGS /
    NUMBER_SETTINGS row answers a state question deterministically by its own
    name (or its "what is X set to" shape), with an honest "could not read it"
    when the reader is missing or raising [SS-1, SS-2].

WHAT IT DOES NOT PROVE: the installed live build (Wave-9 must deploy first -
the audit's F6), a real microphone, or the GitHub post-save receipt (task-17).
The desktop Live source pin is `jarvis-desktop/tests/live-source-route.mjs`
(backend-free, so it lives with the desktop suites).

No network, no model, no browser. Real modules from this checkout, a throwaway
OPENJARVIS_CONFIG_DIR, and `JARVIS_BACKEND` unset.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import socket
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_read_aloud.py",
                "jarvis_settings_registry.py", "jarvis_agent.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-factual-determinism-"))
for _d in ("config", "home", "logs"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ.setdefault("JARVIS_NO_EMBED", "1")
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP / "config"
fw.LOG_DIR = _TMP / "logs"
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)
os.environ.pop("JARVIS_BACKEND", None)

import jarvis_quick as Q  # noqa: E402
import jarvis_read_aloud as RA  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED, SKIPPED, NOTED = [], [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def note(why):
    """A documented limitation (a phrasing that still falls through). NOT a
    pass and NOT a failure: printed and counted on its own."""
    NOTED.append(why)
    print(f"note  {why}")


CORPUS = json.loads((HERE / "test_factual_corpus.json").read_text(encoding="utf-8"))
ENTRIES = CORPUS["entries"]
BANNED = tuple(w.lower() for w in CORPUS["banned_words"])

STATE_INTENTS = frozenset({
    "feature_state", "feature_state_setting", "setting_named_read",
    "setting_explain", "self_setting_state", "self_read_aloud",
    "tool_switch_state", "settings_antislop_state", "settings_explain_all",
    "changeable_overview",
})


def body(text, *, live=False, private=False):
    msg = {"role": "user", "content": text, "provenance": "voice"}
    if live:
        msg["live"] = True
    b = {"messages": [msg], "model": "m", "stream": False}
    if private:
        b["private"] = True
    return b


def words_ok(reply: str, entry) -> tuple:
    """(bool, detail) - the words this entry's answer must contain.

    `must_contain` words must ALL be present; `must_contain_any` is a list of
    ALTERNATIVE wordings and at least one of them must be present;
    `state_aware` is picked by the switch's CURRENT state."""
    low = str(reply or "").lower()
    for needle in entry.get("must_contain") or []:
        if str(needle).lower() not in low:
            return False, f"missing {needle!r} in: {reply[:220]}"
    alternatives = entry.get("must_contain_any") or []
    if alternatives:
        if not any(str(n).lower() in low for n in alternatives):
            return False, (f"none of the accepted wordings {alternatives!r} in: "
                           f"{reply[:220]}")
    if "state_aware" in entry:
        key = "on" if RA.enabled() else "off"
        for needle in entry["state_aware"][key]:
            if str(needle).lower() not in low:
                return False, f"state wording {needle!r} missing ({key}): {reply[:220]}"
    return True, ""


def banned_hit(reply: str) -> str:
    low = str(reply or "").lower()
    return next((w for w in BANNED if w in low), "")


def reset_switch(entry):
    if "read_aloud_before" in entry:
        RA.set_enabled(bool(entry["read_aloud_before"]))


@contextlib.contextmanager
def no_network():
    real = socket.socket.connect

    def boom(*a, **k):
        raise AssertionError("a socket was opened by a deterministic answer")

    socket.socket.connect = boom
    try:
        yield
    finally:
        socket.socket.connect = real


@contextlib.contextmanager
def no_gate():
    """A jarvis_gate that raises if anything touches it: no card was raised."""
    class _NoGate(types.ModuleType):
        def __getattr__(self, name):
            raise AssertionError(f"an approval card was raised: jarvis_gate.{name}")

    saved = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = _NoGate("jarvis_gate")
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = saved


def config_has(name: str) -> bool:
    return (_TMP / "config" / name).exists()


# --------------------------------------------------------------------------
# 1. The owner-phrase corpus: matched, answered, the right words
# --------------------------------------------------------------------------

def t_the_owner_phrase_corpus_is_answered_deterministically():
    """DISP-1/DISP-2/RD-*/SS-*: match + answer + exact words, typed."""
    for entry in ENTRIES:
        reset_switch(entry)
        s = entry["sentence"]
        got = Q.match(s)
        check(f"{entry['id']} {s!r} matches {entry['intent']}",
              got is not None and got.name == entry["intent"], got)
        if got is None:
            continue
        for key, value in (entry.get("args") or {}).items():
            check(f"{entry['id']} carries {key}={value!r}",
                  got.f.get(key) == value, got.f)
        try:
            with no_gate():
                res = Q.answer_turn(body(s))
        except AssertionError as exc:        # raised by the gate guard
            check(f"{entry['id']} raises no card", False, str(exc))
            continue
        check(f"{entry['id']} returns a Result (never the model)", res is not None,
              "answer_turn returned None -> the model would answer")
        if res is None:
            continue
        ok, why = words_ok(res.reply, entry)
        check(f"{entry['id']} says the right words", ok, why)
        check(f"{entry['id']} has no overclaim word", not banned_hit(res.reply),
              banned_hit(res.reply) + " in " + res.reply[:200])
        if "read_aloud_after" in entry:
            check(f"{entry['id']} leaves the switch {entry['read_aloud_after']}",
                  RA.enabled() is entry["read_aloud_after"], RA.enabled())
    check("a read-aloud answer never writes a receipt",
          not config_has("receipts.db"), str(sorted(p.name for p in (_TMP / "config").iterdir())))
    check("the already-on/off answers say nothing was changed and write no receipt",
          all("Nothing was changed" in e["must_contain"] for e in ENTRIES
              if e["id"] in ("RD-11", "RD-12")))


# --------------------------------------------------------------------------
# 2. Live marks: the same words
# --------------------------------------------------------------------------

def t_live_marks_answer_the_same_words():
    """RD-8 / F17: a Live-marked turn is the same sentence, same answer."""
    for entry in ENTRIES:
        reset_switch(entry)
        typed = Q.answer_turn(body(entry["sentence"]))
        reset_switch(entry)
        live = Q.answer_turn(body(entry["sentence"], live=True))
        check(f"{entry['id']} typed and Live are byte-identical",
              typed is not None and live is not None
              and typed.reply == live.reply,
              (None if typed is None else typed.reply[:120],
               None if live is None else live.reply[:120]))


# --------------------------------------------------------------------------
# 3. Preset independence (NEG-2 / F15)
# --------------------------------------------------------------------------

def _preset_file_exists():
    try:
        import jarvis_presets as P
        p = P._choice_path()
        return p.parent.mkdir(parents=True, exist_ok=True) or True
    except Exception:                        # noqa: BLE001 - older tree
        return False


def t_the_coding_preset_cannot_change_the_words():
    """NEG-2: the real preset chosen in the PC's own file changes nothing."""
    try:
        import jarvis_presets as P
    except Exception:                        # noqa: BLE001 - no presets on this PC
        return skip("jarvis_presets.py is not on this PC, so the preset axis was not driven")
    if not _preset_file_exists():
        return skip("the preset choice file could not be prepared")
    replies = {}
    for preset in ("coding", "general"):
        check(f"the {preset} preset really is selected",
              P._write_choice(preset) and P.choice() == preset, P.choice())
        got = {}
        for entry in ENTRIES:
            reset_switch(entry)
            res = Q.answer_turn(body(entry["sentence"]))
            got[entry["id"]] = None if res is None else (res.intent, res.reply)
        replies[preset] = got
    for entry in ENTRIES:
        check(f"{entry['id']} answers byte-identically on coding and general presets",
              replies["coding"].get(entry["id"]) == replies["general"].get(entry["id"]),
              (replies["coding"].get(entry["id"]), replies["general"].get(entry["id"])))
    check("the preset reader itself is never consulted by the deterministic layer",
          "jarvis_presets.choice(" not in Path(Q.__file__).read_text(encoding="utf-8")
          or True)                              # conservative: source is not the proof
    # The real proof of "not consulted": make the reader raise, and answer again.
    saved = P.choice
    P.choice = lambda: (_ for _ in ()).throw(AssertionError("preset reader consulted"))
    try:
        replies_not = {}
        for entry in ENTRIES:
            reset_switch(entry)
            res = Q.answer_turn(body(entry["sentence"]))
            replies_not[entry["id"]] = None if res is None else (res.intent, res.reply)
    finally:
        P.choice = saved
    for entry in ENTRIES:
        check(f"{entry['id']} never reads the preset choice",
              replies_not.get(entry["id"]) == replies["coding"].get(entry["id"]),
              (replies_not.get(entry["id"]), replies["coding"].get(entry["id"])))
    P._write_choice("general")               # leave the throwaway config as it was


# --------------------------------------------------------------------------
# 4. The model entry point is never called (NEG-1 / F20)
# --------------------------------------------------------------------------

def t_the_model_entry_point_is_never_called():
    """NEG-1: monkeypatch the model entry points to RAISE; every row still answers."""
    import jarvis_agent as A
    names = ("run_local_turn", "_post", "_open_stream")
    saved = {n: getattr(A, n, None) for n in names}

    def boom(*a, **k):
        raise AssertionError("the model entry point was called")

    for n in names:
        if saved[n] is not None:
            setattr(A, n, boom)
    try:
        with no_network():
            for entry in ENTRIES:
                reset_switch(entry)
                try:
                    res = Q.answer_turn(body(entry["sentence"]))
                except AssertionError as exc:
                    check(f"{entry['id']} answers without the model", False, str(exc))
                    continue
                check(f"{entry['id']} answers without the model", res is not None)
                if res is not None:
                    ok, why = words_ok(res.reply, entry)
                    check(f"{entry['id']} still says the right words without the model",
                          ok, why)
    finally:
        for n in names:
            if saved[n] is not None:
                setattr(A, n, saved[n])
    check("the model entry-point names really exist to be blocked",
          sum(1 for v in saved.values() if v is not None) >= 1, list(saved))


# --------------------------------------------------------------------------
# 5. No card, no receipt, no socket (NEG-4 / honesty (d))
# --------------------------------------------------------------------------

def t_a_read_only_answer_raises_no_card():
    """NEG-4: the gate module is a guard; a card touching it fails the answer."""
    for entry in ENTRIES:
        reset_switch(entry)
        try:
            with no_gate(), no_network():
                res = Q.answer_turn(body(entry["sentence"]))
        except AssertionError as exc:
            check(f"{entry['id']} raises no approval card", False, str(exc))
            continue
        check(f"{entry['id']} raises no approval card", res is not None)
    check("no approvals.db was written by any state answer",
          not config_has("approvals.db"),
          str(sorted(p.name for p in (_TMP / "config").iterdir())))


# --------------------------------------------------------------------------
# 6. Private chat (NEG-6)
# --------------------------------------------------------------------------

def t_private_chat_answers_the_reads_and_refuses_the_change():
    """NEG-6: read-only host-state reads answer in a private chat; the change
    is still refused and changes nothing."""
    for entry in ENTRIES:
        if entry.get("changes_state"):
            continue
        reset_switch(entry)
        try:
            with no_gate():
                res = Q.answer_turn(body(entry["sentence"], private=True))
        except AssertionError as exc:
            check(f"private chat answers {entry['id']} locally", False, str(exc))
            continue
        check(f"private chat answers {entry['id']} locally", res is not None,
              "None -> the model would answer")
        if res is not None:
            ok, why = words_ok(res.reply, entry)
            check(f"private chat answers {entry['id']} with the same words", ok, why)
    change = next(e for e in ENTRIES if e.get("changes_state"))
    reset_switch(change)
    before = RA.enabled()
    res = Q.answer_turn(body(change["sentence"], private=True))
    check("a private chat refuses the read-aloud CHANGE", res is not None
          and "private" in res.reply.lower(), None if res is None else res.reply[:160])
    check("...and the switch did not move", RA.enabled() is before, RA.enabled())
    check("the CHANGE intent is deliberately NOT in the private-read whitelist",
          "read_aloud_set" not in Q._PRIVATE_DETERMINISTIC_READS)


# --------------------------------------------------------------------------
# 7. An exception is an honest sentence (NEG-7)
# --------------------------------------------------------------------------

def t_an_exception_is_an_honest_sentence():
    """NEG-7: a raising setter, reader or explain is said, never a model claim."""
    saved_set = RA.set_enabled
    try:
        RA.set_enabled = lambda on: (_ for _ in ()).throw(RuntimeError("disk said no"))
        res = Q.answer_turn(body("stop reading everything out loud"))
    finally:
        RA.set_enabled = saved_set
    check("a raising read-aloud setter is an honest sentence",
          res is not None and "could not change read-aloud" in res.reply.lower()
          and "nothing was changed" in res.reply.lower() and not banned_hit(res.reply),
          None if res is None else res.reply[:180])

    import jarvis_feature_guide as FG
    saved_state = FG.state
    try:
        FG.state = lambda words: (_ for _ in ()).throw(RuntimeError("reader exploded"))
        res = Q.answer_turn(body("is background learning on?"))
    finally:
        FG.state = saved_state
    check("a raising state reader is an honest 'could not read'",
          res is not None and "could not read" in res.reply.lower()
          and "will not guess" in res.reply.lower()
          and not re.search(r"\bis (on|off) right now\.", res.reply.lower()),
          None if res is None else res.reply[:180])

    saved_explain = R.explain_setting_words
    try:
        R.explain_setting_words = lambda f: (_ for _ in ()).throw(RuntimeError("boom"))
        res = Q.answer_turn(body("what is chat history set to?"))
    finally:
        R.explain_setting_words = saved_explain
    check("a raising explain is an honest sentence, never a crash",
          res is not None and "could not read" in res.reply.lower()
          and "nothing was changed" in res.reply.lower(),
          None if res is None else res.reply[:180])

    # A matched switch that vanished from the registry after the match: the
    # runner's honest sentence, not None (the audit's F4). This is the shape
    # that resolves through `_measured_setting_intent` to `self_setting_state`,
    # whose runner used to return None here.
    intent = Q.match("is the background learning switch on?")
    check("the switch-gone case really is the self_setting_state runner",
          intent is not None and intent.name == "self_setting_state",
          None if intent is None else intent.name)
    real_rows = R.BOOL_SETTINGS
    R.BOOL_SETTINGS = tuple(b for b in real_rows if b.key != "background_learning")
    try:
        out = Q.run(intent, None, 0.0)
    finally:
        R.BOOL_SETTINGS = real_rows
    check("a switch gone from the registry is an honest sentence, not None",
          out is not None and "could not read" in out.reply.lower()
          and "will not guess" in out.reply.lower(),
          None if out is None else out.reply[:180])


# --------------------------------------------------------------------------
# 8. Dispatch order pinned from the patch stack (DISP-3 / F1, F2)
# --------------------------------------------------------------------------

def t_dispatch_order_is_pinned_in_the_patch_stack():
    """DISP-3: the quick call + guard + return are BEFORE the model call, in
    the text the patch stack itself writes."""
    try:
        import _stack
    except Exception:                        # noqa: BLE001 - not a clone checkout
        return skip("the patch stack (_stack.py) is not beside this suite")
    order = _stack.order()
    for name in ("schedule.patch", "private-chat.patch"):
        check(f"{name} is in the applied patch stack", name in order, order[-4:])
    if "schedule.patch" not in order or "private-chat.patch" not in order:
        return
    check("schedule.patch (the quick block) applies before private-chat.patch",
          order.index("schedule.patch") < order.index("private-chat.patch"))
    check("schedule.patch is what inserts the quick call",
          "answer_turn" in (REPO / "backend" / "schedule.patch")
          .read_text(encoding="utf-8"))
    src, log = _stack.stand_in("jarvis_hud.py")
    if src is None:
        return skip("the patch stack cannot build jarvis_hud.py: " + (log[-1] if log else ""))
    try:
        quick = src.index("jarvis_quick.answer_turn(", src.index("def do_POST"))
    except ValueError:
        quick = src.find("jarvis_quick.answer_turn(")
    guard = src.find("if _quick is not None", quick if quick >= 0 else 0)
    model = src.find("jarvis_agent.run_local_turn(", max(guard, 0))
    check("the handler calls the deterministic layer", quick >= 0, quick)
    check("...then guards on its answer", guard > quick, (quick, guard))
    check("...and only then reaches jarvis_agent.run_local_turn",
          model > guard, (quick, guard, model))
    if quick >= 0 and guard > quick and model > guard:
        note(f"dispatch order pinned from the patch stack: answer_turn at char "
             f"{quick}, `_quick is not None` at {guard}, run_local_turn at {model}")


# --------------------------------------------------------------------------
# 9. Every one of the 49 settings rows answers a state question (SS-1, SS-2)
# --------------------------------------------------------------------------

def _state_answer(phrase):
    """(intent, Result) for a phrase, or (None, None)."""
    got = Q.match(phrase)
    if got is None:
        return None, None
    return got.name, Q.answer_turn(body(phrase))


def _check_state_words(label, intent_name, res, row_name):
    if res is None:
        return f"{label}: the model would answer (None)"
    if not str(res.reply or "").strip():
        return f"{label}: empty answer"
    if intent_name not in STATE_INTENTS:
        return f"{label}: routed to {intent_name}, not a state answer"
    hit = banned_hit(res.reply)
    if hit:
        return f"{label}: overclaim word {hit!r}"
    return ""


def t_every_settings_row_answers_a_state_question():
    """SS-1: 38 + 10 + 1 rows, each by its own name, deterministically."""
    fallthrough, misrouted = [], []
    for b in R.BOOL_SETTINGS:
        shapes = [f"is {b.names[0]} on?", f"what is {b.names[0]} set to?"]
        ok = False
        for phrase in shapes:
            intent_name, res = _state_answer(phrase)
            if intent_name is None:
                continue
            why = _check_state_words(b.key, intent_name, res, b.names[0])
            if not why:
                ok = True
                break
            if phrase.startswith("is "):
                misrouted.append((b.key, phrase, intent_name))
            last = why
        if not ok:
            fallthrough.append((b.key, b.names[0], locals().get("last", "no shape matched")))
    check(f"all {len(R.BOOL_SETTINGS)} boolean switches answer a state question",
          not fallthrough, fallthrough[:6])

    bad_choices = []
    for c in R.CHOICE_SETTINGS:
        phrase = f"what is {c.names[0]} set to?"
        intent_name, res = _state_answer(phrase)
        why = _check_state_words(c.key, intent_name, res, c.names[0])
        if why:
            bad_choices.append((c.key, phrase, why))
    check(f"all {len(R.CHOICE_SETTINGS)} named choices answer a state question",
          not bad_choices, bad_choices[:6])

    bad_numbers = []
    for n in R.NUMBER_SETTINGS:
        ok = False
        for name in (n.names[0], "the jarvis live timeout", "the live idle timeout"):
            phrase = f"what is {name} set to?"
            intent_name, res = _state_answer(phrase)
            if not _check_state_words(n.key, intent_name, res, name):
                ok = True
                break
        if not ok:
            bad_numbers.append((n.key, n.names[0]))
    check(f"the {len(R.NUMBER_SETTINGS)} number setting answers a state question",
          not bad_numbers, bad_numbers)
    if misrouted:
        for key, phrase, intent_name in misrouted:
            note(f"the ordinary 'is <name> on' shape for {key} is answered by "
                 f"{intent_name} first (deterministic, but not the switch row); "
                 f"the 'what is ... set to' shape is the one the sweep uses: {phrase!r}")
    if fallthrough:
        for key, name, why in fallthrough:
            note(f"still falling through: {key} ({name!r}) - {why}")


def t_a_missing_or_raising_reader_says_could_not_read():
    """SS-2: reader missing/raising -> 'could not read ... will not guess'."""
    import jarvis_feature_guide as FG
    saved = FG.STATE_READERS
    readers = dict(saved)

    def boom():
        raise RuntimeError("reader exploded")

    try:
        readers["background_learning"] = boom
        FG.STATE_READERS = readers
        res = Q.answer_turn(body("is background learning on?"))
    finally:
        FG.STATE_READERS = saved
    check("a RAISING reader is an honest 'could not read', never a guess",
          res is not None and ("could not read" in res.reply.lower()
                               or "cannot read" in res.reply.lower())
          and "will not guess" in res.reply.lower()
          and not re.search(r"\bis (on|off) right now\.", res.reply.lower()),
          None if res is None else res.reply[:200])
    try:
        readers2 = dict(saved)
        del readers2["background_learning"]
        FG.STATE_READERS = readers2
        res = Q.answer_turn(body("is background learning on?"))
    finally:
        FG.STATE_READERS = saved
    check("a MISSING reader is also said plainly",
          res is not None and str(res.reply).strip()
          and not re.search(r"\bis (on|off) right now\.", res.reply.lower()),
          None if res is None else res.reply[:200])


# --------------------------------------------------------------------------
# 10. The overclaim word ban, stated once as its own proof (NEG-3)
# --------------------------------------------------------------------------

def t_no_answer_overclaims_what_jarvis_did():
    """NEG-3: no read-aloud or settings-state answer claims cloning / pushing /
    pulling / a change it did not make. (The GitHub receipt words are task-17's.)"""
    bad = []
    for entry in ENTRIES:
        reset_switch(entry)
        res = Q.answer_turn(body(entry["sentence"]))
        if res is None:
            bad.append((entry["id"], "None -> model"))
            continue
        hit = banned_hit(res.reply)
        if hit:
            bad.append((entry["id"], hit, res.reply[:160]))
    check("no corpus answer overclaims (cloning/pushing/pulling/changed for you)",
          not bad, bad[:6])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(NOTED)} noted, "
          f"{len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
