"""The reflex confirmation cache in jarvis_speech.py (2026-10-21).

    python -B backend/run_suites.py test_reflex_speech.py

THE PREMISE THIS SLICE STARTED FROM, CHECKED HERE. The audit said "Kokoro
waits for a full sentence, so the first audio is blocked until then". That is
not true of this backend, and the first check below proves it: _synthesise()
hands the WHOLE text it is given to the engine in one call - there is no
sentence buffer anywhere on the speak path (the first-piece rule lives in the
clients: jarvis-desktop/src/speech-pieces.js cuts the first piece at the first
comma; the phone has SpeechText.kt). So no first-fragment splitter is added;
what IS added is the second half of the audit's idea - the fixed quick
confirmations are made once per voice and handed back without running ONNX
again.

WHAT IS PROVEN HERE, with a fake engine that counts every call:

  - the whole text goes to the engine in ONE call (no backend sentence wait);
  - a fixed confirmation (REFLEX_TEXTS, the literals jarvis_quick.py writes
    for its own commands) is synthesised once, then a repeat returns the SAME
    PCM without touching the engine - and say()'s own bookkeeping still runs
    on the hit;
  - nothing else is ever kept: arbitrary text, and text of the shape a private
    answer could have, is synthesised every single time;
  - another voice, another speed/pitch, the plain crisis voice or a replaced
    model/voice pack is a different sound, never a stale hit; reload_engines()
    empties the cache; the cache is bounded and the least recently used goes;
  - the background warm-up makes the whole list once per voice, skips a custom
    voice, and with no Kokoro voice nothing crashes and nothing is cached.

No ONNX model, no microphone, no network: the engine is a stand-in, exactly
like the rest of the voice suites' missing-asset paths.
"""
from __future__ import annotations

import sys
import tempfile
import traceback
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "rebuilt"))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_speech.py")

import numpy as np  # noqa: E402
import jarvis_speech as S  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class FakeVoices(types.ModuleType):
    """The bits of jarvis_voices the speak path and the cache key read."""

    def __init__(self, active="builtin", engine="kokoro"):
        super().__init__("jarvis_voices")
        self.active = active
        self.engine = engine

    def brief(self):
        return {"active": self.active, "engine": self.engine}

    def speak(self, *_a, **_k):
        # "no custom voice is chosen": _synthesise then uses Kokoro.
        return None


class Rig:
    """A fake Kokoro engine: counts ONNX calls and returns deterministic PCM.

    `calls` is every text that reached the engine, in order - the unit of
    'bypassing ONNX' the whole suite measures."""

    def __init__(self, sid=0, speed=1.0, semis=0.0, active="builtin", engine="kokoro"):
        self.calls = []
        self.mouth = []
        self.sid, self.speed, self.semis = sid, speed, semis
        self.voices = FakeVoices(active=active, engine=engine)
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.paths = {}
        for name, payload in (("model", b"m" * 100), ("voices", b"v" * 50),
                              ("tokens", b"t" * 25)):
            p = base / name
            p.write_bytes(payload)
            self.paths[name] = str(p)

    # -- the patched pieces --------------------------------------------------
    def engine(self):
        return object()

    def kokoro_speak(self, engine, text, sid, speed, semis=0.0, mouth=None):
        self.calls.append(text)
        samples = np.full(64, 0.01 * (int(sid) + 1), dtype="float32")
        if mouth is not None:
            payload = {"src": "fake", "sid": int(sid), "text": text}
            self.mouth.append(payload)
            mouth.append(payload)
        return samples, 24000

    def tts_voice(self, voices_module=None, *, plain=False):
        return (self.sid, self.speed, self.semis)

    def paths_fn(self):
        return dict(self.paths)

    def voices_mod(self):
        return self.voices

    def patch(self):
        stack = mock.ExitStack() if hasattr(mock, "ExitStack") else None
        self._stack = stack
        self._patches = [
            mock.patch.object(S, "_tts_engine", self.engine),
            mock.patch.object(S, "kokoro_speak", self.kokoro_speak),
            mock.patch.object(S, "tts_voice", self.tts_voice),
            mock.patch.object(S, "_sherpa_tts_paths", self.paths_fn),
            mock.patch.object(S, "_voices_mod", self.voices_mod),
            mock.patch.object(S, "_reflex_warm_soon", lambda *a, **k: None),
            mock.patch.dict(sys.modules, {"jarvis_voices": self.voices}),
        ]
        for p in self._patches:
            p.start()
        return self

    def close(self):
        for p in reversed(self._patches):
            p.stop()
        self.tmp.cleanup()


def fresh(rig):
    """A clean cache and a clean engine cache for one test."""
    S.reflex_clear()
    return rig


def synth(text, *, plain=False, mouth=None):
    """The speak path's own synthesis step, without say()'s bookkeeping."""
    return S._synthesise(text, mouth=mouth, plain=plain)


# --------------------------------------------------------------------------
#   The premise: no backend sentence wait
# --------------------------------------------------------------------------

def t_the_backend_does_not_wait_for_a_sentence():
    rig = Rig().patch()
    try:
        fresh(rig)
        text = ("A long first sentence, with a comma; and a second clause - "
                "then more. And a question?")
        got = synth(text)
        check("the speak path hands the WHOLE text to the engine in one call",
              rig.calls == [text], rig.calls)
        check("... and it returns one WAV's samples, as before",
              got[0] is not None and got[2] == "kokoro", got[2])
        check("... so there is no backend sentence/first-fragment buffer to fix "
              "(the first piece is cut in the clients, which already do it)",
              len(rig.calls) == 1, rig.calls)
    finally:
        rig.close()


# --------------------------------------------------------------------------
#   The cache: fixed confirmations only
# --------------------------------------------------------------------------

def t_a_fixed_confirmation_is_made_once_then_handed_back():
    rig = Rig().patch()
    try:
        fresh(rig)
        check("the fixed list is the real quick-path confirmations (11 of them)",
              len(S.REFLEX_TEXTS) == 11 and "Added to your to-do list." in S.REFLEX_TEXTS
              and "Marked done." in S.REFLEX_TEXTS and "Done." in S.REFLEX_TEXTS,
              list(S.REFLEX_TEXTS))
        for text in S.REFLEX_TEXTS:
            S.reflex_clear()
            before = len(rig.calls)
            first = synth(text)
            after_first = len(rig.calls)
            second = synth(text)
            after_second = len(rig.calls)
            check(f"{text!r}: made once, then a hit with no engine call",
                  after_first == before + 1 and after_second == after_first,
                  (before, after_first, after_second))
            check(f"{text!r}: the hit is the SAME PCM, sample for sample",
                  first[0] is not None and second[0] is not None
                  and np.array_equal(first[0], second[0]) and first[1] == second[1],
                  (first[1], second[1]))
    finally:
        rig.close()


def t_say_still_does_its_bookkeeping_on_a_hit():
    rig = Rig().patch()
    seen = {"remember": 0, "said": 0, "speaking": 0, "close": 0, "timing": 0}
    real = {name: getattr(S, name) for name in
            ("_remember_said", "_note_said", "_mark_speaking", "_close_question",
             "_note_timing")}
    try:
        fresh(rig)
        text = "Marked done."

        def wrap(name, fn):
            def inner(*a, **k):
                seen[name] += 1
                return fn(*a, **k)
            return inner

        S._remember_said = wrap("remember", real["_remember_said"])
        S._note_said = wrap("said", real["_note_said"])
        S._mark_speaking = wrap("speaking", real["_mark_speaking"])
        S._close_question = wrap("close", real["_close_question"])
        S._note_timing = wrap("timing", real["_note_timing"])
        wav1 = S.say(text)
        engine_calls_after_first = len(rig.calls)
        wav2 = S.say(text)
        check("say() on the kept confirmation made no second engine call",
              len(rig.calls) == engine_calls_after_first, rig.calls)
        check("... and the PCM is byte-for-byte the same WAV",
              bool(wav1) and wav1 == wav2, (len(wav1 or b""), len(wav2 or b"")))
        check("... while every one of say()'s own rules still ran twice",
              all(v == 2 for v in seen.values()), seen)
    finally:
        S._remember_said = real["_remember_said"]
        S._note_said = real["_note_said"]
        S._mark_speaking = real["_mark_speaking"]
        S._close_question = real["_close_question"]
        S._note_timing = real["_note_timing"]
        rig.close()


def t_nothing_else_is_ever_kept():
    rig = Rig().patch()
    try:
        fresh(rig)
        secret = "Your sister's birthday is Tuesday."   # private-shaped answer
        for text in ("Sure thing, I can do that for you now.", secret,
                     "Timer set for 10 minutes.",  # a confirmation with a number
                     "Added 3 items to your shopping list."):
            before = len(rig.calls)
            synth(text)
            synth(text)
            check(f"arbitrary/private text {text[:34]!r}: never cached",
                  len(rig.calls) == before + 2
                  and S.reflex_status()["entries"] == 0,
                  (len(rig.calls) - before, S.reflex_status()))
    finally:
        rig.close()


# --------------------------------------------------------------------------
#   The key: one sound per voice, speed and pack
# --------------------------------------------------------------------------

def t_another_voice_or_speed_is_a_different_sound():
    rig = Rig(sid=0, speed=1.0).patch()
    try:
        fresh(rig)
        text = "Resumed."
        synth(text)
        check("(first voice: made)", len(rig.calls) == 1, rig.calls)
        synth(text)
        check("(same voice: hit)", len(rig.calls) == 1, rig.calls)
        rig.sid = 3
        synth(text)
        check("another speaker is synthesised, not reused", len(rig.calls) == 2, rig.calls)
        rig.sid = 0
        synth(text)
        check("switching back to the first voice hits ITS kept sound",
              len(rig.calls) == 2, rig.calls)
        rig.speed = 0.8
        synth(text)
        check("another speaking speed is synthesised, not reused",
              len(rig.calls) == 3, rig.calls)
        rig.speed = 1.0
        rig.semis = 2.0
        synth(text)
        check("another pitch is synthesised, not reused", len(rig.calls) == 4, rig.calls)
        rig.semis = 0.0
        synth(text)
        check("back to the first recipe: hit again", len(rig.calls) == 4, rig.calls)
        plain = synth(text, plain=True)
        check("the plain crisis voice is a separate sound, made once then kept",
              len(rig.calls) == 5 and plain[0] is not None, rig.calls)
        synth(text, plain=True)
        check("... and then hit without the engine", len(rig.calls) == 5, rig.calls)
    finally:
        rig.close()


def t_a_replaced_voice_pack_invalidates_everything():
    rig = Rig().patch()
    try:
        fresh(rig)
        synth("Here you go.")
        Path(rig.paths["model"]).write_bytes(b"m" * 5000)   # a new model file
        synth("Here you go.")
        check("a replaced model file is synthesised again, not reused",
              len(rig.calls) == 2, rig.calls)
        S.reload_engines()
        check("reload_engines() empties the kept confirmations",
              S.reflex_status()["entries"] == 0, S.reflex_status())
        synth("Here you go.")
        check("... and the next one is made again", len(rig.calls) == 3, rig.calls)
    finally:
        rig.close()


def t_the_cache_is_bounded_and_lru():
    rig = Rig().patch()
    try:
        fresh(rig)
        for sid in range(6):
            rig.sid = sid
            for text in S.REFLEX_TEXTS:
                synth(text)
        st = S.reflex_status()
        check(f"the cache never grows past REFLEX_MAX ({S.REFLEX_MAX})",
              st["entries"] <= S.REFLEX_MAX and st["entries"] == S.REFLEX_MAX, st)
        rig.sid = 0                  # the oldest voice's entries went first
        before = len(rig.calls)
        synth(S.REFLEX_TEXTS[0])
        check("the least recently used voice's sound was evicted",
              len(rig.calls) == before + 1, (before, len(rig.calls)))
    finally:
        rig.close()


# --------------------------------------------------------------------------
#   The warm-up
# --------------------------------------------------------------------------

def t_the_warm_up_makes_the_list_once_per_voice():
    rig = Rig().patch()
    try:
        fresh(rig)
        out = S.reflex_warm(wait=True)
        check("the warm-up made every confirmation once, on its own",
              out.get("ok") is True and len(rig.calls) == len(S.REFLEX_TEXTS),
              (out, rig.calls))
        before = len(rig.calls)
        for text in S.REFLEX_TEXTS:
            synth(text)
        check("... so every one of them is a hit afterwards",
              len(rig.calls) == before, rig.calls)
        again = S.reflex_warm(wait=True)
        check("... and a second warm-up makes nothing",
              len(rig.calls) == before and again.get("made") == 0, (again, rig.calls))
    finally:
        rig.close()


def t_the_warm_up_skips_a_custom_voice_and_no_kokoro():
    rig = Rig(active="my-voice", engine="f5").patch()
    try:
        fresh(rig)
        out = S.reflex_warm(wait=True)
        check("a custom voice is skipped - it makes its own sound every time",
              out.get("skipped") and not rig.calls, (out, rig.calls))
    finally:
        rig.close()
    rig2 = Rig().patch()
    try:
        S.reflex_clear()
        with mock.patch.object(S, "_tts_engine", lambda: None):
            got = synth("Done.")
            out = S.reflex_warm(wait=True)
        check("with no Kokoro voice: no crash, no sound, nothing kept",
              got[0] is None and out.get("ok") is False
              and S.reflex_status()["entries"] == 0, (got[0], out))
    finally:
        rig2.close()


def t_a_synthesised_sound_starts_the_warm_up_once():
    rig = Rig().patch()
    calls = []
    try:
        fresh(rig)
        S._reflex_warm_soon = lambda *a, **k: calls.append(1)
        synth("Not a fixed confirmation at all, just a sentence.")
        check("after a sound in a voice, the warm-up is asked once",
              len(calls) == 1, calls)
        synth("Done.")                       # first time: made, so still asked
        check("... a sound that is made also asks (the real one is guarded inside)",
              len(calls) == 2, calls)
        synth("Done.")                       # a cache hit: synthesis skipped
        check("... but a kept confirmation does not ask at all",
              len(calls) == 2, calls)
    finally:
        rig.close()


def t_the_mouth_payload_is_kept_with_the_sound():
    rig = Rig().patch()
    try:
        fresh(rig)
        first_mouth = []
        first = synth("Done.", mouth=first_mouth)
        check("(first call: made with a mouth payload)",
              len(rig.calls) == 1 and bool(first_mouth), (rig.calls, first_mouth))
        second_mouth = []
        second = synth("Done.", mouth=second_mouth)
        check("the kept sound carries its mouth shapes too, and no engine call",
              len(rig.calls) == 1 and second_mouth == first_mouth,
              (rig.calls, second_mouth, first_mouth))
        check("... and it is the same PCM",
              np.array_equal(first[0], second[0]), (first[1], second[1]))
    finally:
        rig.close()


# --------------------------------------------------------------------------

def main():
    tests = (t_the_backend_does_not_wait_for_a_sentence,
             t_a_fixed_confirmation_is_made_once_then_handed_back,
             t_say_still_does_its_bookkeeping_on_a_hit,
             t_nothing_else_is_ever_kept,
             t_another_voice_or_speed_is_a_different_sound,
             t_a_replaced_voice_pack_invalidates_everything,
             t_the_cache_is_bounded_and_lru,
             t_the_warm_up_makes_the_list_once_per_voice,
             t_the_warm_up_skips_a_custom_voice_and_no_kokoro,
             t_a_synthesised_sound_starts_the_warm_up_once,
             t_the_mouth_payload_is_kept_with_the_sound)
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
