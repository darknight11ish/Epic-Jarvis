"""Which microphone a clip came from reaches the voice check.

    python3 test_voice_mic.py

The phone and the desktop each have their own voice print since 2026-09-24
(jarvis_voice.py, "ONE VOICE PRINT PER MICROPHONE"). The phone sends
`/api/voice/utterance?...&mic=phone`, the desktop `&mic=desktop`;
voice-mic.patch hands that to jarvis_speech.hear(), which hands it to the
voice check and the "hey Jarvis" verifier. What it proves:

  1. hear(mic=...) passes the microphone on - and still works with a
     jarvis_voice.py / jarvis_wakeword.py from before it existed.
  2. Anything but "phone" or "desktop" counts as no microphone named.
  3. voice-mic.patch applies to what voice-503.patch wrote, and reverses;
     it passes `mic` only to a jarvis_speech.py that says TAKES_MIC, reads
     no header, logs nothing.
  4. The clients send it: the phone's JarvisApi.utterance and the desktop's
     voice.rs post_utterance.
"""
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_speech.py")
import jarvis_speech as S  # noqa: E402
import jarvis_voice as V  # noqa: E402
import jarvis_wakeword as W  # noqa: E402
import _skeleton  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def tone(seconds=1.0):
    import array, io, math, wave
    s = array.array("h", [int(0.4 * 32767 * math.sin(2 * math.pi * 220 * i / 16000))
                          for i in range(int(seconds * 16000))])
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(s.tobytes())
    return b.getvalue()


def t_hear_passes_the_microphone():
    seen = {}

    def verify(audio, embedder=None, sample_rate=None, mic=""):
        seen["verify"] = mic
        return V.Verdict(False, score=0.1, threshold=0.4, reason="no", voice_print=mic or "general")

    with mock.patch.object(S, "_speech_span", return_value="skip"), \
            mock.patch.object(V, "verify", verify):
        for sent, want in (("phone", "phone"), ("desktop", "desktop"), ("tablet", ""),
                           ("", ""), ("PHONE", "phone")):
            seen.clear()
            h = S.hear(tone(), mic=sent)
            check(f"mic={sent!r} reaches the voice check as {want!r}",
                  seen.get("verify") == want and h.voice_print == (want or "general"),
                  (seen, h.voice_print))

    def old_verify(audio, embedder=None, sample_rate=None):     # before mic existed
        return V.Verdict(False, score=0.1, threshold=0.4, reason="no")
    with mock.patch.object(S, "_speech_span", return_value="skip"), \
            mock.patch.object(V, "verify", old_verify):
        try:
            h = S.hear(tone(), mic="phone")
            ok = h.is_owner is False and h.voice_print == ""
        except TypeError as exc:
            ok, h = False, exc
    check("an older jarvis_voice.verify (no mic) is still called, without it", ok, h)

    spotted = {}

    def spot(samples, sample_rate=16000, mic=""):
        spotted["mic"] = mic
        return W.Spot(True, heard=False, score=0.0)
    with mock.patch.object(S, "_speech_span", return_value="skip"), \
            mock.patch.object(S, "_wake_enabled", return_value=True), \
            mock.patch.object(S, "_take_awake", return_value=False), \
            mock.patch.object(W, "spot", spot):
        S.hear(tone(), source="wake_word", mic="desktop")
    check("a wake-word clip's microphone reaches the verifier too",
          spotted.get("mic") == "desktop", spotted)
    check("jarvis_speech says it takes mic (voice-mic.patch checks this)", S.TAKES_MIC is True)


def _added(patch):
    return "\n".join(l[1:] for l in (HERE / patch).read_text(encoding="utf-8").splitlines()
                     if l.startswith("+") and not l.startswith("+++"))


def t_the_patch():
    added = _added("voice-mic.patch")
    check("mic is passed only to a jarvis_speech.py that says TAKES_MIC",
          'getattr(jarvis_speech, "TAKES_MIC", False)' in added
          and "jarvis_speech.hear(raw, source=src)" in added, added)
    check("no header read, nothing logged", "self.headers" not in added and "print(" not in added)
    ok, out = _skeleton.rehearse("voice-mic.patch", "voice-503.patch")
    if ok is None:
        return check("SKIP - " + out, True)
    check("voice-mic.patch applies to what voice-503.patch wrote, and reverses", ok is True, out)
    if ok:
        check("the old call is gone and both new ones are there",
              out.count("jarvis_speech.hear(raw, source=src)") == 1
              and "jarvis_speech.hear(raw, source=src, mic=voice_mic)" in out, out[-1500:])


def t_the_clients_send_it():
    api = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
           / "net" / "JarvisApi.kt").read_text(encoding="utf-8")
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "voice.rs").read_text(encoding="utf-8")
    check("the phone sends mic=phone on every utterance",
          "/api/voice/utterance?source=$source&mic=$MIC_PHONE" in api
          and 'const val MIC_PHONE = "phone"' in api)
    check("the desktop sends mic=desktop on every utterance",
          "/api/voice/utterance?source={source}&mic={MIC_DESKTOP}" in rs
          and 'const MIC_DESKTOP: &str = "desktop";' in rs)


if __name__ == "__main__":
    for fn in (t_hear_passes_the_microphone, t_the_patch, t_the_clients_send_it):
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
