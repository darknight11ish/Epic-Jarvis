"""test_voice_reflex.py - the spoken-command normaliser and the speaking-speed
voice reflex (Voice Slice A, 2026-10-21; the Live/Voice audit's V4, revised by
`.dsh-scratch/FOR-GEMINI-OVERNIGHT-WAVE-2026-10-21.md` section 10.4).

    python3 backend/test_voice_reflex.py   (run it through backend/run_suites.py)

What it proves, with every socket made to fail and no model anywhere:

  * THE NORMALISER (`jarvis_quick.normalize_spoken_command`):
    - polite lead-ins `normalise` does not strip ("would you mind ...",
      "can you kindly ...", "i would like you to ...", "do you think you
      could ...", "would it be possible to ...", and the gerund form after
      them, "would you mind setting a timer") now reach the SAME grammar
      sentence the plain words already reached;
    - number words in the three grammars that demanded digits now hit them:
      "watch FIVE more minutes", "speak up THREE times a day", "the brief
      arrives at EIGHT" - and the answer carries the real number;
    - the three number forms the audit named that ALREADY worked before this
      change ("a couple of minutes", "half an hour", "an hour and a half")
      are NOT rewritten and still work - the normaliser does not invent
      wording;
    - the safe rule, tested: "one of the files", "show me the one with the
      error", "call me three times", "twenty five" on its own are left
      alone and stay chat; a rewrite never turns a non-command into one;
    - it is idempotent on every sentence the suite uses;
    - and it is fast IN THE TEST: each new-form match is measured and must
      be under 5 ms (the only speed claim this suite makes).
  * THE SPEAKING-SPEED REFLEX: "speak faster/slower/normally" calls the
    EXISTING `jarvis_voices.set_speed` (spied: exactly one call, exactly the
    body the REST route posts), really changes the setting (`speed_view()`
    and `speed()` agree), says the voice module's OWN sentence, and raises
    no card (a `jarvis_gate.check` spy is never called).
  * THE READS ARE #691's, NOT THIS FILE'S: "read this selection", "what's on
    my screen" and their siblings must NOT match this fast path, because PR
    #691 shipped them for Live turns through the same primitives
    (`jarvis_voice_ui.py`); a 0-ms copy here would intercept them before that
    path could answer. The suite holds this file to leaving them alone, and
    (when the module is present) holds #691's own matchers to still claiming
    them - so the ownership is explicit and one of the two cannot silently
    change.
  * THE COMMANDS THIS SLICE DID NOT BUILD are held to NOT being new
    intents: HUD layout switching, bar pinning, mute/unmute, "repeat that",
    scroll/back/home. No honest backend action exists for them
    (docs/JARVIS-API.md section 154 says why for each), so nothing was added
    that would look like it worked.
  * IT IS HERMETIC: its own config, home and log folders under its own temp
    dir, and it refuses to run if those names do not point inside it (the
    patcher runs suites inside the live installation - a suite must never
    write the owner's real audit log or read the owner's real settings).
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import time
import traceback
import types
import urllib.request
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-voice-reflex-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PASSED: list = []
FAILED: list = []
SKIPPED: list = []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}  (not a pass)")


def _inside_tmp(value: str) -> bool:
    try:
        Path(value).resolve().relative_to(_TMP.resolve())
        return True
    except ValueError:
        return False


def _require_own_places() -> None:
    for name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME", "JARVIS_LOG_DIR"):
        value = os.environ.get(name, "")
        if not value or not _inside_tmp(value):
            raise SystemExit(
                f"refusing to run: {name}={value!r} is not inside this suite's own temp "
                f"folder {_TMP}. A suite must never write the owner's real audit log or "
                f"read their real settings.")


_require_own_places()

import jarvis_quick as Q                                    # noqa: E402
import jarvis_voices as V                                    # noqa: E402


def _sched():
    """What `answer()` touches on a scheduler: marking the sentence a
    command (so the learner skips it) and, for "cancel that", nothing here."""
    return types.SimpleNamespace(
        mark_command=lambda *a, **k: None,
        note_set=lambda *a, **k: None,
        forget_set=lambda *a, **k: None,
    )


def _answer(text, **kwargs):
    return Q.answer(text, sched=_sched(), now=1729550000.0, **kwargs)


class NoNetwork:
    """Every way out fails: no socket, no urlopen. The fast path must not
    need one, and nothing in these tests is allowed to reach the model."""

    def __enter__(self):
        self._socket = socket.socket
        self._urlopen = urllib.request.urlopen

        def barred(*_a, **_k):
            raise AssertionError("the fast path opened a socket - it must not")
        socket.socket = barred
        urllib.request.urlopen = barred
        return self

    def __exit__(self, *exc):
        socket.socket = self._socket
        urllib.request.urlopen = self._urlopen
        return False


#: "the normaliser used to miss this" -> the intent it must hit now. Every
#: left-hand form returned None (the model answered) on the tree before this
#: change; the digit form already hit the fast path. Measured with a probe on
#: that tree (the PR body records the output).
NUMBER_GAPS = (
    ("watch five more minutes", "screen_more"),
    ("watch for ten more minutes", "screen_more"),
    ("watch twenty more minutes", "screen_more"),
    ("speak up three times a day", "settings_budget"),
    ("let jarvis speak up two times a day", "settings_budget"),
    ("the brief arrives at eight", "settings_budget"),
    ("the brief arrives at eight in the morning", "settings_budget"),
    ("the brief at eight pm", "settings_budget"),
)

#: Polite lead-ins `normalise` did not strip - each used to fall through.
POLITE_GAPS = (
    "would you mind setting a timer for five minutes",
    "can you kindly set a timer for five minutes",
    "would you be so kind as to set a timer for five minutes",
    "i would like you to set a timer for five minutes",
    "i was wondering if you could set a timer for five minutes",
    "do you think you could set a timer for five minutes",
    "any chance you could set a timer for five minutes",
    "could you possibly set a timer for five minutes",
    "would it be possible to set a timer for five minutes",
    "kindly set a timer for five minutes",
)

#: Forms that must stay exactly as they are: ordinary chat, or a duration the
#: existing parser already reads.
UNCHANGED = (
    "one of the files needs sorting",
    "show me the one with the error",
    "one of them is broken",
    "call me three times",
    "twenty five",
    "a couple of minutes",
    "half an hour",
    "an hour and a half",
    "what about tomorrow",
    "read my notes",
)

#: The reads PR #691 owns (Live turns, the same primitives). This fast path
#: must NOT match them, or it would intercept the phrase before that path can
#: answer; the suite also checks #691's own matchers still claim them.
READS_691 = (
    "read this selection",
    "read what i selected",
    "read what i've selected",
    "read my selection",
    "read the selected text",
    "read the highlighted text",
    "what did i highlight",
    "what have i highlighted",
    "summarize what i selected",
    "summarise what i selected",
    "what's on my screen",
    "what is on my screen",
    "read my screen",
    "look at my screen",
    "what am i looking at",
    "describe my screen",
)

#: What did NOT get a reflex (see docs/JARVIS-API.md section 154 for why).
NOT_BUILT = (
    "switch to cockpit mode",
    "switch to studio layout",
    "switch to ambient mode",
    "pin the bar",
    "unpin the bar",
    "mute",
    "mute for five minutes",
    "unmute",
    "repeat that",
    "scroll down",
    "scroll up",
    "go back",
    "go home",
)


def t_the_normaliser_closes_the_measured_number_gaps():
    for spoken, want_name in NUMBER_GAPS:
        got = Q.match(spoken)
        name = getattr(got, "name", None)
        check(f"number words now hit the fast path: {spoken!r} -> {want_name}",
              name == want_name, f"got {name!r}")
        if name == "screen_more":
            check(f"... and it carries the real number of minutes ({spoken!r})",
                  (got.f or {}).get("minutes") in (5.0, 10.0, 20.0), got.f)
        elif name == "settings_budget":
            body = (got.f or {}).get("body") or {}
            check(f"... and it carries the real number ({spoken!r})",
                  body.get("spoken_per_day") in (2, 3) or body.get("digest_hour") in (8, 20),
                  body)


def t_the_normaliser_strips_polite_leads_the_grammar_did_not_know():
    plain = Q.match("set a timer for five minutes")
    check("(set-up) the plain sentence already works", plain is not None
          and plain.name == "timer_set", plain)
    for phrase in POLITE_GAPS:
        got = Q.match(phrase)
        check(f"polite lead-in reaches the same action: {phrase!r}",
              got is not None and got.name == "timer_set", got)
        if got is not None:
            check(f"... with the same length the plain sentence has ({phrase!r})",
                  (got.f or {}).get("seconds") == 300.0, got.f)


def t_the_forms_the_audit_named_that_already_worked_are_not_rewritten():
    for phrase, want in (
            ("set a timer for a couple of minutes", "timer_set"),
            ("set a timer for half an hour", "timer_set"),
            ("set a timer for an hour and a half", "timer_set"),
            ("remind me in fifteen minutes to stretch", "reminder_set"),
            ("set a timer for two minutes", "timer_set")):
        got = Q.match(phrase)
        check(f"already worked before this change, still works: {phrase!r}",
              got is not None and got.name == want, got)
    check("'a couple of minutes' is NOT rewritten (parse_duration reads it)",
          Q.normalize_spoken_command("a couple of minutes") == "a couple of minutes")
    check("'half an hour' is NOT rewritten",
          Q.normalize_spoken_command("half an hour") == "half an hour")
    check("'an hour and a half' is NOT rewritten",
          Q.normalize_spoken_command("an hour and a half") == "an hour and a half")


def t_the_safe_number_rule_never_hijacks_ordinary_words():
    for phrase in UNCHANGED:
        if phrase in ("a couple of minutes", "half an hour", "an hour and a half"):
            continue        # not questions; the normaliser test above covers them
        got = Q.match(phrase)
        check(f"ordinary words stay chat: {phrase!r}", got is None, got)
    check("'one of the files' is left byte-for-byte alone",
          Q.normalize_spoken_command("one of the files needs sorting")
          == "one of the files needs sorting")
    check("'call me three times' is not '3 times'",
          Q.normalize_spoken_command("call me three times") == "call me three times")
    check("'twenty five' alone (no unit) is not '25'",
          Q.normalize_spoken_command("twenty five") == "twenty five")
    # A rewrite that matches nothing must not change what the model is asked:
    # match() returns None here, so the caller sends the ORIGINAL words.
    check("a rewritable chat sentence is still not a command",
          Q.match("give me five minutes") is None)


def t_number_words_are_read_correctly_where_they_are_rewritten():
    check("twenty nine minutes is 29, not 90",
          Q.normalize_spoken_command("set a timer for twenty nine minutes")
          == "set a timer for 29 minutes")
    check("ninety minutes is 90",
          Q.normalize_spoken_command("set a timer for ninety minutes")
          == "set a timer for 90 minutes")
    r29 = Q.match("set a timer for twenty nine minutes")
    r90 = Q.match("set a timer for ninety minutes")
    check("... and the timer lengths are 1740 s and 5400 s",
          r29 is not None and r90 is not None
          and (r29.f or {}).get("seconds") == 1740.0
          and (r90.f or {}).get("seconds") == 5400.0,
          (r29 and r29.f, r90 and r90.f))
    check("'one minute' is 1, not a word left alone",
          Q.normalize_spoken_command("set a timer for one minute")
          == "set a timer for 1 minute")
    check("twenty-five hyphenated is read as 25",
          Q.normalize_spoken_command("watch twenty-five more minutes")
          == "watch 25 more minutes")


def t_the_normaliser_is_idempotent():
    sentences = [p for p, _ in NUMBER_GAPS] + list(POLITE_GAPS) + list(UNCHANGED)
    sentences += [
        "the brief arrives at eight",
        "watch twenty-five more minutes",
        "set a timer for ninety nine minutes",
    ]
    bad = []
    for phrase in sentences:
        once = Q.normalize_spoken_command(phrase)
        twice = Q.normalize_spoken_command(once)
        if once != twice:
            bad.append((phrase, once, twice))
    check("normalize_spoken_command is idempotent on every sentence tested",
          not bad, bad[:3])


def t_the_new_forms_are_fast_in_the_test():
    phrases = [p for p, _ in NUMBER_GAPS] + list(POLITE_GAPS)
    for _ in range(3):
        Q.match("set a timer for 5 minutes")     # warm up the regex machinery
    worst = 0.0
    for phrase in phrases:
        start = time.perf_counter()
        Q.match(phrase)
        ms = (time.perf_counter() - start) * 1000.0
        worst = max(worst, ms)
    check(f"every new form matches in under 5 ms IN THE TEST "
          f"(worst {worst:.3f} ms over {len(phrases)} sentences)", worst < 5.0, worst)


def t_the_speed_reflex_calls_the_existing_action_and_it_really_changes():
    state = V._state_path()
    if state.exists():
        state.unlink()
    check("(set-up) the speed starts at the default", V.speed_view()["choice"] == "normal",
          V.speed_view())
    real_set = V.set_speed
    seen = []

    def spy(body):
        seen.append(body)
        return real_set(body)
    V.set_speed = spy
    try:
        with NoNetwork():
            res = _answer("speak faster")
    finally:
        V.set_speed = real_set
    check("'speak faster' calls the EXISTING voices action exactly once",
          seen == [{"speed": "faster"}], seen)
    check("... and the answer is the voice module's OWN sentence",
          res is not None and res.reply == V.SPEED_SAID["faster"], res)
    check("... the setting really changed (the same one the REST route writes)",
          V.speed_view()["choice"] == "faster" and abs(V.speed() - 1.15) < 1e-9,
          V.speed_view())
    res = _answer("speak at normal speed")
    check("'speak at normal speed' sets it back, with the module's words",
          res is not None and V.speed_view()["choice"] == "normal", res)
    res = _answer("would you mind speaking slower")
    check("a polite 'would you mind speaking slower' reaches the same reflex",
          res is not None and V.speed_view()["choice"] == "slower", res)
    res = _answer("speak more slowly")
    check("... and 'speak more slowly' is the same 'slower' choice",
          res is not None and V.speed_view()["choice"] == "slower", res)
    if state.exists():
        state.unlink()


def t_the_reads_belong_to_691_and_this_fast_path_leaves_them_alone():
    for phrase in READS_691:
        got = Q.match(phrase)
        check(f"the fast path does NOT intercept #691's read: {phrase!r}",
              got is None, getattr(got, "name", got))
    try:
        import jarvis_voice_ui as VU
    except Exception:
        skip("jarvis_voice_ui (#691) is not in this tree, so its matchers are not re-tested")
    else:
        matchers = tuple(VU.SELECTION_ASK) + tuple(VU.SCREEN_ASK)
        claimed = [p for p in READS_691 if any(rx.search(p) for rx in matchers)]
        unclaimed = [p for p in READS_691 if p not in claimed]
        check("#691's own matchers claim every read phrase except the known "
              "contraction gap ('read what i've selected')",
              unclaimed == ["read what i've selected"], unclaimed)
        check("... so the split is by layer, not a second implementation: #691 "
              "owns 15 of the 16, and the contraction is left to the model "
              "because NEITHER file claims it",
              len(claimed) >= 15, claimed)
        check("... and #691's reads are Live-only and PC-only",
              getattr(VU, "PC_DEVICE", "") == "desktop")


def t_a_gate_spy_is_never_consulted_by_the_speed_reflex():
    fake_gate = types.SimpleNamespace(calls=[])
    real = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = types.SimpleNamespace(
        check=lambda *a, **k: fake_gate.calls.append((a, k)),
        action_tier=lambda *a, **k: "ask",
    )
    try:
        with NoNetwork():
            res = _answer("speak faster")
    finally:
        if real is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = real
    check("no approval gate is consulted by the speed reflex (nothing to approve)",
          fake_gate.calls == [], fake_gate.calls)
    check("... and the answer is not the 'until you approve' sentence",
          res is not None and "approve the card" not in res.reply, res)


def t_the_commands_this_slice_did_not_build_are_not_new_intents():
    for phrase in NOT_BUILT:
        got = Q.match(phrase)
        name = getattr(got, "name", None)
        check(f"no new reflex for {phrase!r} (nothing honest to route it to)",
              name is None, name)
    for phrase in ("open the galaxy", "open today"):
        got = Q.match(phrase)
        name = getattr(got, "name", None)
        check(f"{phrase!r} gets no HUD reflex (the only place it can go is the "
              f"pre-existing 'open a program' path)", name in (None, "open_app"), name)
    check("a refusal is still not a card: the missing-module sentence is plain words",
          isinstance(Q.VOICES_MISSING, str) and Q.VOICES_MISSING)


def t_missing_voices_module_refuses_in_plain_words_and_does_nothing():
    real_v = sys.modules.get("jarvis_voices")
    sys.modules["jarvis_voices"] = None
    try:
        res = _answer("speak faster")
    finally:
        if real_v is None:
            sys.modules.pop("jarvis_voices", None)
        else:
            sys.modules["jarvis_voices"] = real_v
    check("without jarvis_voices the reflex says to run apply-patches.ps1",
          res is not None and res.reply == Q.VOICES_MISSING, res)


def main():
    functions = [(name, fn) for name, fn in list(globals().items())
                 if name.startswith("t_") and callable(fn)]
    for name, fn in functions:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception:
            FAILED.append(name)
            traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print("skipped (NOT passes): " + ", ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
