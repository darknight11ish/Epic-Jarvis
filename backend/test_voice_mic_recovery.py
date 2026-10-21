"""test_voice_mic_recovery.py - Slice D (2026-10-21): a microphone returning
EXACT digital silence is told apart from a quiet room and SAID, not
misreported as "no speech in that recording".

    python3 backend/test_voice_mic_recovery.py

What this suite proves, with real code and no microphone (the desktop's own
re-open is `voice.rs`, proved by `cargo test`):

  * the exact-zero detector: all-zero yes; a quiet ROOM with even a one-count
    (-90 dBFS) noise floor, no - and zeros after the probe window do not
    count either, because the window is the START of the clip;
  * hearing a silence clip with the VAD's "no speech" answer gives the SAME
    sentence the desktop shows (`voice.rs` MIC_SILENT_WORDS), with
    `silent: true`, no words, `ok: false` and no transcription ever started -
    so a deaf microphone is never worded as "that didn't sound like you";
  * a quiet-but-real room keeps the ordinary "no speech in that recording"
    wording and `silent: false`: the detector cannot call a room deaf;
  * Pillar 28's own counters (`voice_attempts_status`, read by PC help) are
    unchanged in SHAPE and still flip only at three exact-zero attempts, and a
    silent clip COUNTS as an attempt - the doctor keeps reporting a microphone
    that has not recovered.
"""
import array
import io
import sys
import tempfile
import wave
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
require_shipped("jarvis_speech.py")
import jarvis_speech as S  # noqa: E402

FAILED, PASSED = [], []


def check(what, ok, detail=""):
    if ok:
        PASSED.append(what)
        print(f"  ok    {what}")
    else:
        FAILED.append(what)
        print(f"  FAIL  {what}" + (f" - {detail}" if detail else ""))


def skip(what, why):
    print(f"  SKIPPED  {what} - {why} (did NOT run, did NOT pass)")


def _wav(samples, sample_rate=16000):
    """Real 16-bit mono PCM bytes, like a client sends."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(array.array("h", [int(v) for v in samples]).tobytes())
    return buf.getvalue()


def _quiet_room(n=8000):
    """A REAL quiet room: one-count dither, never exact zeros."""
    return [1 if i % 2 else -1 for i in range(n)]


def _silent(n=8000):
    return [0] * n


class hear_world:
    """The smallest fake world hear() needs to reach the VAD's answer: no
    engines, a temp config folder, and the VAD saying "no speech" (which is
    what the real Silero VAD says about silence)."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(S, "_config_dir", return_value=Path(self.tmp.name)),
            mock.patch.object(S, "_speech_span", lambda *a, **k: None),
        ]

    def __enter__(self):
        S._reset_mic_levels()
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()
        S._reset_mic_levels()


def t_the_sentence_is_the_one_the_desktop_shows():
    desktop = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "voice.rs").read_text(
        encoding="utf-8")
    joined = " ".join(desktop.split())
    check("the desktop's voice.rs declares the same silence sentence (voice.rs MIC_SILENT_WORDS)",
          "MIC_SILENT_WORDS" in desktop and S.MIC_SILENT_WORDS in joined,
          f"backend: {S.MIC_SILENT_WORDS!r}")
    check("the sentence names both things the owner should check",
          "mute switch" in S.MIC_SILENT_WORDS.lower()
          and "input device" in S.MIC_SILENT_WORDS.lower(), S.MIC_SILENT_WORDS)
    check("one sentence, no trailing change from the tested wording",
          S.MIC_SILENT_WORDS == ("Microphone is returning silence - check the mute "
                                 "switch or Windows input device."), S.MIC_SILENT_WORDS)


def t_exact_zeros_only_are_the_deaf_state():
    check("all-zero samples are exact digital silence",
          S.digital_zero_prefix([0] * 6400, 16000) is True)
    check("a clip shorter than the window, all zeros, is still silence",
          S.digital_zero_prefix([0] * 500, 16000) is True)
    check("one nonzero sample in the window is a real (if quiet) device",
          S.digital_zero_prefix([0] * 3000 + [1] + [0] * 3400, 16000) is False)
    check("a -90 dBFS one-count room is never called deaf",
          S.digital_zero_prefix(_quiet_room(), 16000) is False)
    check("zeros AFTER the 400 ms window are not the deaf state (the window is the start)",
          S.digital_zero_prefix([1] * 6400 + [0] * 8000, 16000) is False)
    check("an empty clip proves nothing",
          S.digital_zero_prefix([], 16000) is False)
    check("a missing sample rate proves nothing",
          S.digital_zero_prefix([0] * 6400, 0) is False)


def t_a_silence_clip_is_said_plainly_and_never_transcribed():
    transcribed = []

    def never(samples, rate):
        transcribed.append(True)
        raise AssertionError("a deaf microphone's clip must never reach STT")

    with hear_world():
        with mock.patch.object(S, "_transcribe", never), \
             mock.patch.object(S, "_live_refusal", lambda *a, **k: (None, False)):
            h = S.hear(_wav(_silent()), source="push_to_talk", mic="desktop")
    check("the reply carries silent: true", h.silent is True, repr(h))
    check("it says the sentence, not 'no speech in that recording'",
          h.reason == S.MIC_SILENT_WORDS, h.reason)
    check("nothing was heard: no owner, no words",
          h.is_owner is False and h.text == "", f"{h.is_owner} {h.text!r}")
    check("no transcription was ever started", not transcribed, transcribed)
    d = h.as_dict()
    check("the wire reply says silent (additive field, both clients ignore it safely)",
          d.get("silent") is True and d.get("ok") is False and d.get("owner") is False,
          {k: d.get(k) for k in ("silent", "ok", "owner")})


def t_a_quiet_room_keeps_the_ordinary_wording():
    with hear_world():
        h = S.hear(_wav(_quiet_room()), source="push_to_talk", mic="desktop")
    check("a real quiet room is NOT called a deaf microphone",
          h.silent is False and h.reason == "no speech in that recording",
          f"silent={h.silent} reason={h.reason!r}")


def t_pillar_28_counters_are_unchanged_and_still_see_the_attempt():
    S._reset_mic_levels()
    S._note_voice_attempt([0.0] * 160, "desktop")
    S._note_voice_attempt([0.0] * 160, "desktop")
    st = S.voice_attempts_status()
    check("two silent attempts are not yet the doctor's finding",
          st["digital_zero"] is False and st["zeros_in_a_row"] == 2, st)
    check("the status fields are exactly the ones Pillar 28 and PC help read",
          set(st) == {"attempts", "zeros_in_a_row", "digital_zero", "device",
                      "last_peak_rms", "last_at"}, sorted(st))
    S._note_voice_attempt([0.0] * 160, "desktop")
    st = S.voice_attempts_status()
    check("three exact-zero attempts in a row: digital_zero flips",
          st["digital_zero"] is True and st["zeros_in_a_row"] == 3, st)
    # A silent CLIP counts too: the doctor must keep reporting a microphone
    # that has not recovered, and hear() records the attempt before it speaks.
    S._reset_mic_levels()
    with hear_world():
        S.hear(_wav(_silent()), source="push_to_talk", mic="desktop")
        # Read inside the world: its exit clears the counters for the next test.
        st = S.voice_attempts_status()
    check("a silence clip is counted as an attempt, with peak RMS exactly 0.0",
          st["attempts"] == 1 and st["last_peak_rms"] == 0.0
          and st["zeros_in_a_row"] == 1, st)
    S._reset_mic_levels()


def t_a_relieved_microphone_stops_tripping_the_counters():
    S._reset_mic_levels()
    S._note_voice_attempt([0.0] * 160, "desktop")
    S._note_voice_attempt([0.0] * 160, "desktop")
    S._note_voice_attempt([0.0] * 160, "desktop")
    check("three zeros trip it", S.voice_attempts_status()["digital_zero"] is True)
    S._note_voice_attempt([0.3] * 160, "desktop")
    st = S.voice_attempts_status()
    check("one real level clears it (a re-opened device works again)",
          st["digital_zero"] is False and st["zeros_in_a_row"] == 0, st)
    S._reset_mic_levels()


if __name__ == "__main__":
    for fn in (t_the_sentence_is_the_one_the_desktop_shows,
               t_exact_zeros_only_are_the_deaf_state,
               t_a_silence_clip_is_said_plainly_and_never_transcribed,
               t_a_quiet_room_keeps_the_ordinary_wording,
               t_pillar_28_counters_are_unchanged_and_still_see_the_attempt,
               t_a_relieved_microphone_stops_tripping_the_counters):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            import traceback
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
