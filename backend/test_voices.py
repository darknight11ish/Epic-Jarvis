"""Custom voices: jarvis_voices.py, jarvis_f5_worker.py, say()'s use of them,
and voices.patch.

    python3 test_voices.py

Runs anywhere. No graphics card, no PyTorch, no F5-TTS: the better voice's
process is the REAL jarvis_f5_worker.py, started for real, with small
stand-ins for PyTorch and F5-TTS put in front of it. ZipVoice and Kokoro are
stand-ins too - except in t_real_zipvoice, which runs the real ZipVoice when
its model files are found under JARVIS_TEST_VOICE_MODELS (the voice-models
folder, as in the other voice suites), and skips cleanly when they are not.

What it proves:

  - the owner's voice is refused: a clip scoring at or above a voice print's
    threshold minus the margin is refused, through the real jarvis_voice
    (its profile files, cosine and thresholds); every print is checked;
    no print means nothing to compare; a missing voice check refuses; and a
    voice made before a print was trained is refused at say() once one is.
  - the cards: creating and switching each raise ONE card (custom_voice), a
    tier other than "ask" raises none, and nothing is saved or switched on
    deny, timeout, a gate that says "notify", or a gate that fails; the clip
    is held in memory until then and dropped after; one card at a time;
    switching back to the built-in voice and deleting are immediate, and
    withdraw a waiting switch card.
  - fallback: a missing voice, missing or failing ZipVoice, and "too slow"
    each make say() use Kokoro and say why (status and the timing row).
  - the better voice: its switch (card ON, OFF at once, refused without a
    capable second card); its process on demand, ZipVoice in the same voice
    while it loads, idle stop, standby stop and staying stopped, a sentence
    that fails, a process that hangs; the environment it gets.
  - nothing leaves: no network call in either file, and none made at run
    time; no name, words or text in an audit line, an event or a timing row.
  - timing: every say() records engine, characters, seconds and audio seconds.
  - voices.patch applies after big-model.patch to what the earlier patches
    wrote, and reverses; the install lists, the toml.
"""
import base64
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import types
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, require_shipped  # noqa: E402

for p in (HERE / "rebuilt",):
    if str(p) not in sys.path:
        sys.path.append(str(p))

require_shipped("jarvis_voices.py", "jarvis_f5_worker.py", "jarvis_speech.py",
                "rebuilt/jarvis_voice.py")

import numpy as np  # noqa: E402
import jarvis_voices as V  # noqa: E402
import jarvis_speech as S  # noqa: E402
import jarvis_voice as JV  # noqa: E402
import jarvis_f5_worker as W  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------------------------ helpers --

def tone(seconds=5.0, rate=24000, f0=150.0, amp=0.3):
    t = np.arange(int(seconds * rate)) / float(rate)
    x = amp * (np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2.3 * f0 * t))
    # a little silence at both ends, which is trimmed
    pad = np.zeros(int(0.5 * rate))
    return np.concatenate([pad, x / 1.5, pad]).astype(np.float32)


def make_wav(samples, rate=24000, width=2, channels=1) -> bytes:
    x = np.clip(np.asarray(samples, dtype=np.float64), -1, 1)
    if channels == 2:
        x = np.repeat(x[:, None], 2, axis=1).reshape(-1)
    if width == 2:
        data = (x * 32767).astype("<i2").tobytes()
    else:
        v = (x * 8388607).astype(np.int32)
        data = b"".join(int(i & 0xFFFFFF).to_bytes(3, "little") for i in v)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(data)
    return buf.getvalue()


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


WORDS = "The quick brown fox jumps over the lazy dog then runs back home"


def body(name="Grandpa", seconds=5.0, words=WORDS, **kw):
    return {"name": name, "clip": b64(make_wav(tone(seconds, **kw))), "transcript": words}


def verdict(outcome="approved", tier="ask"):
    return types.SimpleNamespace(tier=tier, allowed=outcome in ("approved", "auto", "notify"),
                                 outcome=outcome, request_id="rq1", reason=outcome)


class Gate:
    """A stand-in for jarvis_gate.check that records every card."""

    def __init__(self, outcome="approved", tier="ask", boom=False, wait=None):
        self.outcome, self.tier, self.boom, self.wait = outcome, tier, boom, wait
        self.cards = []

    def __call__(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.wait is not None:
            self.wait.wait(10)
        if self.boom:
            raise RuntimeError("gate down")
        return verdict(self.outcome, self.tier)


def inline(fn):
    fn()


ASK = lambda a: "ask"  # noqa: E731
NOT_OWNER = lambda s: {"ok": True, "why": "it does not sound like your voice", "checked": 1,  # noqa: E731
                       "fingerprint": V.prints_fingerprint()}


class FakeZip:
    """ZipVoice's generate(): a quiet tone as long as the text wants."""

    def __init__(self, boom=False):
        self.calls, self.boom = [], boom

    def generate(self, text, prompt_text, prompt_samples, sample_rate, speed, steps):
        self.calls.append((text, prompt_text, len(prompt_samples), sample_rate, steps))
        if self.boom:
            raise RuntimeError("onnxruntime: out of memory")
        n = int(24000 * max(0.5, len(text) / 15.0))
        return types.SimpleNamespace(samples=(0.1 * np.ones(n)).astype(np.float32),
                                     sample_rate=24000)


class FakeKokoro:
    def __init__(self):
        self.calls = []

    def generate(self, text, sid=0, speed=1.0):
        self.calls.append(text)
        return types.SimpleNamespace(samples=(0.05 * np.ones(24000)).astype(np.float32),
                                     sample_rate=24000)


CFG = {}
AUDIT, EVENTS = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-voices-test-"))
_ORIG = {n: getattr(V, n) for n in ("_config_dir", "_cfg", "_audit", "_publish", "_second_card",
                                    "_worker_command", "_start_reaper", "_mono", "_voice_mod",
                                    "_embedder")}


def reset(zipvoice=True, kokoro=True):
    V._reset_for_tests()
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=TMP))
    CFG.clear()
    AUDIT.clear()
    EVENTS.clear()
    V._config_dir = lambda: d
    V._cfg = lambda k, default=None: CFG.get(k, default)
    V._audit = lambda e, det: AUDIT.append((e, dict(det)))
    V._publish = lambda data: EVENTS.append(dict(data))
    V._second_card = lambda: {"capable": False, "why": "only one graphics card found",
                              "uuid": None, "name": None, "free_mb": None, "big_model": None}
    V._start_reaper = lambda: None
    V._mono = _ORIG["_mono"]
    V._voice_mod = _ORIG["_voice_mod"]
    V._embedder = _ORIG["_embedder"]
    JV.PROFILE_PATH = d / "voice" / "owner.json"
    if zipvoice:
        V._ZIP.update(engine=FakeZip(), why="ready", built=True)
    S._tts_cache = FakeKokoro() if kokoro else None
    with S._TIMINGS_LOCK:
        S._TIMINGS.clear()
    return d


def make_voice(name="Grandpa", **kw):
    code, out = V.create(body(name, **kw), gate=Gate(), tier_of=ASK, spawn=inline,
                         check=NOT_OWNER)
    assert code == 202 and V._LAST.get("outcome") == "created", (code, out, V._LAST)
    return out["voice"]


def use(vid):
    code, out = V.switch({"voice": vid}, gate=Gate(), tier_of=ASK, spawn=inline, check=NOT_OWNER)
    assert V._read_state()["active"] == vid, (code, out, V._LAST)


# --------------------------------------------------------- reading the clip --

def t_the_clip_is_read_and_normalised():
    reset()
    x = tone(5.0, rate=48000)
    for label, raw in (("16-bit mono 24 kHz", make_wav(tone(5.0))),
                       ("16-bit stereo 48 kHz", make_wav(x, rate=48000, channels=2)),
                       ("24-bit mono 16 kHz", make_wav(tone(5.0, rate=16000), rate=16000, width=3))):
        y, secs = V.normalise(raw)
        check(f"{label} becomes mono 24 kHz, silence trimmed ({secs} s)",
              y.ndim == 1 and abs(len(y) / 24000.0 - secs) < 0.01 and 5.0 <= secs <= 5.4, secs)
    bad = {
        "not base64": dict(body(), clip="@@@"),
        "not a WAV": dict(body(), clip=b64(b"RIFF....nope")),
        "too short": body(seconds=1.5, words="Hello there my friend"),
        "too long": body(seconds=11.0, words=" ".join([WORDS] * 3)),
        "silent": dict(body(), clip=b64(make_wav(np.zeros(24000 * 5)))),
        "8-bit": dict(body(), clip=b64(_eight_bit())),
        "words that do not fit": body(words="Hi"),
        "no name": body(name="  "),
        "a name with a slash": body(name="a/b"),
        "no words": body(words="  ...  "),
    }
    for label, b in bad.items():
        code, out = V.create(b, gate=Gate(), tier_of=ASK, spawn=inline, check=NOT_OWNER)
        check(f"{label}: 400 with a sentence, no card, nothing saved",
              code == 400 and out.get("error") and not V._ids_on_disk(), (code, out))


def _eight_bit():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(24000)
        w.writeframes(bytes([128]) * 24000 * 5)
    return buf.getvalue()


def t_resample_keeps_pitch():
    x = tone(2.0, rate=16000, f0=440.0)
    y = V.resample(x, 16000, 24000)
    spec = np.abs(np.fft.rfft(y))
    peak = np.argmax(spec) * 24000.0 / len(y)
    check("resampling 16 -> 24 kHz keeps a 440 Hz tone at 440 Hz", abs(peak - 440) < 3, peak)


def t_words_and_chunks():
    check("Chinese characters count one each", V.count_words("各位村民, 大家新年好") == 9)
    check("English words count one each", V.count_words("Hello there, Jarvis.") == 3)
    long = " ".join(["This is sentence number %d, and it goes on a while." % i for i in range(20)])
    parts = V.chunks(long)
    check("a long answer is cut into pieces of at most about 200 characters, at sentence ends",
          len(parts) > 3 and all(len(p) <= 200 for p in parts)
          and " ".join(parts) == long and all(p.endswith(".") for p in parts), parts[:2])
    one = "word " * 120
    check("one enormous sentence is cut at spaces", all(len(p) <= 200 for p in V.chunks(one)))


# --------------------------------------------------------- the owner check --

class FakeEmb:
    name = "fake-emb"

    def __init__(self, vec):
        self.vec = vec

    def embed(self, audio):
        return list(self.vec)


def _print(label, centroid, threshold=0.5, embedder="fake-emb"):
    p = JV.PROFILE_PATH if label == "general" else JV.profile_path(label)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"centroid": centroid, "threshold": threshold, "samples": 3,
                             "embedder": embedder}), encoding="utf-8")


def _vec_at(cos):
    return [cos, (1 - cos * cos) ** 0.5, 0.0]


def t_the_owners_voice_is_refused():
    reset()
    samples = tone(5.0)
    V._embedder = lambda mod: FakeEmb(_vec_at(0.2))
    out = V.owner_check(samples)
    check("no voice print trained: nothing to compare with, allowed, and it says so",
          out["ok"] and out["checked"] == 0 and "not been trained" in out["why"], out)
    _print("phone", [1.0, 0.0, 0.0], threshold=0.5)
    for cos, ok, label in ((1.0, False, "the owner's own voice (score 1.0)"),
                           (0.45, False, "within the margin (0.45 >= 0.50 - 0.10)"),
                           (0.40, False, "exactly at the bar (0.40)"),
                           (0.35, True, "clearly below the bar (0.35)")):
        V._embedder = lambda mod, c=cos: FakeEmb(_vec_at(c))
        out = V.owner_check(samples)
        check(f"{label}: {'allowed' if ok else 'refused'}", out["ok"] is ok, out)
        if not ok:
            check("  ... refused as owner_voice, with the reason in plain words",
                  out.get("refused") == "owner_voice" and "YOUR voice" in out["why"]
                  and "pass the check" in out["why"], out["why"])
    # Every print counts, not only the first.
    _print("desktop", [0.0, 1.0, 0.0], threshold=0.6)
    V._embedder = lambda mod: FakeEmb([0.0, 1.0, 0.0])
    out = V.owner_check(samples)
    check("a clip matching the SECOND print (the PC's) is refused too",
          not out["ok"] and out.get("refused") == "owner_voice" and "PC voice print" in out["why"],
          out)
    # A print from a different voice check cannot be compared: skipped, said.
    reset()
    _print("phone", [1.0, 0.0, 0.0], embedder="another-model")
    V._embedder = lambda mod: FakeEmb([1.0, 0.0, 0.0])
    out = V.owner_check(samples)
    check("a print made with another voice check is not compared, and it says so",
          out["ok"] and out["checked"] == 0 and "different voice check" in out["why"], out)
    V._voice_mod = lambda: (_ for _ in ()).throw(ImportError("gone"))
    out = V.owner_check(samples)
    check("no voice check installed: refused", not out["ok"] and "not installed" in out["why"])
    V._voice_mod = _ORIG["_voice_mod"]
    V._embedder = lambda mod: FakeEmb([])
    _print("phone", [1.0, 0.0, 0.0])
    check("an embedder that returns nothing: refused", not V.owner_check(samples)["ok"])


def t_the_owners_voice_is_refused_through_the_real_voice_check():
    """No stand-in embedder: jarvis_voice's own (the spectral fallback here,
    as there is no speaker model in this container), its enroll(), its
    profile file. The owner's print is made from a clip; the same voice
    offered as a custom voice is refused, with no card."""
    reset()
    owner = tone(8.0, rate=16000, f0=130.0)
    clips = [owner[(i + 1) * 16000:(i + 4) * 16000] for i in range(3)]   # 3 s each
    emb = V._embedder(JV)
    JV.enroll([(c * 32767).astype("<i2").tobytes() for c in clips], embedder=emb,
              sample_rate=16000, mic="phone")
    gate = Gate()
    b = {"name": "Me", "clip": b64(make_wav(tone(5.0, rate=24000, f0=130.0))),
         "transcript": WORDS}
    code, out = V.create(b, gate=gate, tier_of=ASK, spawn=inline)
    check("the owner's own voice is refused as a custom voice (409, owner_voice), no card",
          code == 409 and out.get("refused") == "owner_voice" and not gate.cards
          and not V._ids_on_disk(), (code, out))


def t_a_print_trained_later_stops_the_voice_at_say():
    reset()
    vid = make_voice()
    use(vid)
    V._embedder = lambda mod: FakeEmb([1.0, 0.0, 0.0])
    S.say("Hello from the custom voice.")
    check("before any print exists the custom voice speaks",
          S.say_timings()[-1]["engine"] == "zipvoice", S.say_timings()[-1])
    time.sleep(0.01)
    _print("phone", [1.0, 0.0, 0.0])
    wav = S.say("Hello again.")
    row = S.say_timings()[-1]
    check("once the owner trains a print that matches it, say() uses the built-in voice and "
          "says why", wav and row["engine"] == "kokoro" and "YOUR voice" in row["fallback"], row)
    st = V.status()
    check("... and status says why too", st["speaking_with"] == "kokoro"
          and "YOUR voice" in st["fallback"], st["fallback"])
    code, out = V.switch({"voice": vid}, gate=Gate(), tier_of=ASK, spawn=inline)
    check("switching to it again is refused", code in (200, 409))


# ------------------------------------------------------------------ cards --

def t_create_needs_a_card():
    d = reset()
    gate = Gate()
    code, out = V.create(body(), gate=gate, tier_of=ASK, spawn=inline, check=NOT_OWNER)
    check("create answers 202 pending and raises ONE card, custom_voice",
          code == 202 and out["pending"] and len(gate.cards) == 1
          and gate.cards[0][0] == "custom_voice", (code, out))
    text = gate.cards[0][2]
    check("the card quotes the words in full, says where it is kept and that nothing is sent",
          WORDS in text and str(d / "voices" / "grandpa") in text and "Nothing is sent" in text
          and "If you say no" in text and "agreed" in text, text)
    folder = d / "voices" / "grandpa"
    check("approved: clip.wav, transcript.txt and voice.json are written",
          (folder / "clip.wav").is_file() and (folder / "transcript.txt").read_text().strip() == WORDS
          and json.loads((folder / "voice.json").read_text())["name"] == "Grandpa")
    with wave.open(str(folder / "clip.wav")) as w:
        fmt = (w.getnchannels(), w.getframerate(), w.getsampwidth())
    check("the stored clip is mono, 24 kHz, 16-bit", fmt == (1, 24000, 2), fmt)
    check("the voice is listed, and Jarvis does NOT start speaking in it yet",
          any(v["id"] == "grandpa" for v in V.status()["voices"])
          and V._read_state()["active"] == "builtin")
    check("the held clip is gone from memory", not V._PENDING)
    code, out = V.create(body(), gate=Gate(), tier_of=ASK, spawn=inline, check=NOT_OWNER)
    check("a second voice with the same name is refused", code == 409 and "already" in out["error"])


def t_create_never_saves_without_a_yes():
    for label, gate in (("denied", Gate("denied")), ("timed out", Gate("timed_out")),
                        ("the gate said notify (no person)", Gate("notify", tier="notify")),
                        ("the gate said auto (no person)", Gate("auto", tier="auto")),
                        ("the gate failed", Gate(boom=True))):
        reset()
        code, out = V.create(body(), gate=gate, tier_of=ASK, spawn=inline, check=NOT_OWNER)
        check(f"{label}: nothing saved, the clip dropped, the outcome said",
              code == 202 and not V._ids_on_disk() and not V._PENDING
              and V._LAST["outcome"] in ("denied", "timed_out", "refused")
              and V._LAST["why"], (code, V._LAST))
    reset()
    gate = Gate()
    code, out = V.create(body(), gate=gate, tier_of=lambda a: "auto", spawn=inline,
                         check=NOT_OWNER)
    check("tier 'auto' in the toml: 409, no card, nothing saved",
          code == 409 and not gate.cards and not V._ids_on_disk() and "'ask'" in out["error"])


def t_one_card_at_a_time_and_nothing_while_it_waits():
    reset()
    release = threading.Event()
    gate = Gate("denied", wait=release)
    th = []
    code, out = V.create(body(), gate=gate, tier_of=ASK,
                         spawn=lambda fn: th.append(threading.Thread(target=fn)) or th[-1].start(),
                         check=NOT_OWNER)
    for _ in range(100):
        if gate.cards:
            break
        time.sleep(0.01)
    st = V.status()
    check("while the card waits: nothing on disk, status shows it pending with seconds left",
          not V._ids_on_disk() and st["pending"] and st["pending"]["kind"] == "create"
          and st["pending"]["expires_in"] > 0, st["pending"])
    code2, out2 = V.create(body("Other"), gate=Gate(), tier_of=ASK, spawn=inline, check=NOT_OWNER)
    code3, _ = V.switch({"voice": "grandpa"}, gate=Gate(), tier_of=ASK, spawn=inline)
    check("a second create while it waits: 409", code2 == 409 and out2.get("pending"), out2)
    release.set()
    th[0].join(5)
    check("denied: nothing saved, clip dropped", not V._ids_on_disk() and not V._PENDING
          and V._LAST["outcome"] == "denied")


def t_switch_needs_a_card_and_builtin_does_not():
    reset()
    vid = make_voice()
    gate = Gate("denied")
    code, out = V.switch({"voice": vid}, gate=gate, tier_of=ASK, spawn=inline, check=NOT_OWNER)
    check("switch: 202, ONE custom_voice card, and on a no nothing changes",
          code == 202 and len(gate.cards) == 1 and gate.cards[0][0] == "custom_voice"
          and V._read_state()["active"] == "builtin", (code, out))
    check("the switch card says what changes, and what no costs",
          "everything Jarvis says aloud" in gate.cards[0][2]
          and "keeps speaking in its built-in voice" in gate.cards[0][2])
    for outcome in ("timed_out", "refused"):
        V.switch({"voice": vid}, gate=Gate(outcome), tier_of=ASK, spawn=inline, check=NOT_OWNER)
        check(f"{outcome}: not switched", V._read_state()["active"] == "builtin")
    V.switch({"voice": vid}, gate=Gate(), tier_of=ASK, spawn=inline, check=NOT_OWNER)
    check("approved: switched", V._read_state()["active"] == vid)
    gate = Gate()
    code, out = V.switch({"voice": "builtin"}, gate=gate)
    check("back to the built-in voice: immediate, no card",
          code == 200 and out["active"] == "builtin" and not gate.cards
          and V._read_state()["active"] == "builtin")
    code, out = V.switch({"voice": "nobody"}, gate=Gate(), tier_of=ASK, spawn=inline)
    check("an unknown voice: 404", code == 404)
    gate = Gate()
    code, out = V.switch({"voice": vid}, gate=gate, tier_of=lambda a: "notify", spawn=inline,
                         check=NOT_OWNER)
    check("tier not 'ask': 409, no card", code == 409 and not gate.cards)


def t_going_back_while_a_switch_card_waits_withdraws_it():
    reset()
    vid = make_voice()
    release = threading.Event()
    gate = Gate("approved", wait=release)
    th = []
    V.switch({"voice": vid}, gate=gate, tier_of=ASK,
             spawn=lambda fn: th.append(threading.Thread(target=fn)) or th[-1].start(),
             check=NOT_OWNER)
    for _ in range(100):
        if gate.cards:
            break
        time.sleep(0.01)
    V.switch({"voice": "builtin"})
    release.set()
    th[0].join(5)
    check("approving a card after going back to the built-in voice changes nothing",
          V._read_state()["active"] == "builtin" and V._LAST["outcome"] == "withdrawn", V._LAST)


def t_delete_is_immediate():
    reset()
    vid = make_voice()
    use(vid)
    code, out = V.delete({"voice": vid})
    check("delete: 200 at once, the folder is gone, the built-in voice is back",
          code == 200 and not V._ids_on_disk() and V._read_state()["active"] == "builtin", out)
    check("deleting the built-in voice: 400", V.delete({"voice": "builtin"})[0] == 400)
    check("deleting an unknown or malformed id: 404",
          V.delete({"voice": "nobody"})[0] == 404 and V.delete({"voice": "../x"})[0] == 404)
    check("a path outside voices/ is never reachable", V._voice_path("..") is None
          and V._voice_path("a/b") is None and V._voice_path("builtin") is None)


# --------------------------------------------------------------- fallback --

def t_say_speaks_in_the_custom_voice():
    reset()
    vid = make_voice()
    use(vid)
    zip_ = V._ZIP["engine"]
    wav = S.say("Of course. I have added the dentist to Tuesday at ten.")
    row = S.say_timings()[-1]
    check("say() speaks with ZipVoice, in the chosen voice",
          wav and row["engine"] == "zipvoice" and row["voice"] == vid and not row["fallback"], row)
    call = zip_.calls[-1]
    check("ZipVoice is given the voice's own words and its 24 kHz recording",
          call[1] == WORDS and call[3] == 24000 and 5.0 * 24000 <= call[2] <= 5.4 * 24000, call[1:])
    check("the timing row: engine, characters, seconds, audio seconds - never the text",
          row["chars"] == 54 and row["seconds"] >= 0 and row["audio_seconds"] > 0
          and "dentist" not in json.dumps(row), row)
    check("Kokoro was not asked", not S._tts_cache.calls)
    st = S.status()["tts"]
    check("/api/voice/status's tts block names the voice and has the timings",
          st["voice"]["active"] == vid and st["voice"]["engine"] == "zipvoice"
          and st["timings"][-1]["engine"] == "zipvoice", st["voice"])


def t_fallback_to_the_built_in_voice():
    cases = []
    reset()
    vid = make_voice()
    use(vid)
    shutil.rmtree(V.voices_dir() / vid)
    cases.append(("the voice's folder is gone", "missing"))
    _fb(*cases[-1])
    reset(zipvoice=False)
    V._ZIP.update(engine=None, why="ZipVoice could not be loaded (RuntimeError)", built=True)
    vid = make_voice()
    use(vid)
    _fb("ZipVoice will not load", "could not be loaded")
    reset(zipvoice=False)
    V._ZIP.update(built=False)
    CFG["zipvoice_dir"] = str(TMP / "no-such-folder")
    vid = make_voice()
    use(vid)
    _fb("ZipVoice's files are not installed", "not on this PC yet")
    reset()
    V._ZIP.update(engine=FakeZip(boom=True))
    vid = make_voice()
    use(vid)
    _fb("ZipVoice raises", "failed (RuntimeError)")
    check("... and the engine's own message is not repeated",
          "out of memory" not in S.say_timings()[-1]["fallback"])


def _fb(label, words):
    wav = S.say("Hello there, this is a test.")
    row = S.say_timings()[-1]
    check(f"{label}: Kokoro speaks, and the timing row says why",
          wav and row["engine"] == "kokoro" and words in row["fallback"], row)


def t_too_slow_falls_back_and_says_so():
    reset()
    vid = make_voice()
    use(vid)
    clock = [1000.0]
    real_gen = V._ZIP["engine"].generate

    def slow(text, *a):
        out = real_gen(text, *a)
        clock[0] += 2.0 * len(out.samples) / 24000.0       # RTF 2.0
        return out
    V._ZIP["engine"].generate = slow
    V._mono = lambda: clock[0]
    engines = []
    for _ in range(4):
        S.say("A sentence to make, slowly.")
        engines.append(S.say_timings()[-1]["engine"])
    row = S.say_timings()[-1]
    check("three slow sentences in a row, then the built-in voice",
          engines == ["zipvoice"] * 3 + ["kokoro"] and "too slow" in row["fallback"], engines)
    check("status says why", "too slow" in V.status()["fallback"])
    clock[0] += V.SLOW_PAUSE_SECONDS + 1
    S.say("And later it is tried again.")
    check("after the pause it is tried again", S.say_timings()[-1]["engine"] == "zipvoice")


def t_builtin_is_untouched():
    reset()
    wav = S.say("Nothing custom here.")
    row = S.say_timings()[-1]
    check("with the built-in voice chosen, say() is Kokoro as before, no fallback reason",
          wav and row["engine"] == "kokoro" and row["voice"] == "builtin" and not row["fallback"])
    reset(kokoro=False)
    check("and with no Kokoro, None as before (the route's 503)",
          S.say("hello") is None and S.say_timings()[-1]["failed"])


# ------------------------------------------------------ the better voice --

GPU = "GPU-8932f937-d72c-4106-c12f-20bd9faed9f6"
CAPABLE = {"capable": True, "why": "", "uuid": GPU, "name": "NVIDIA GeForce RTX 2060",
           "free_mb": 11000, "big_model": None}

FAKE_TORCH = "import types\ncuda = types.SimpleNamespace(is_available=lambda: True)\n"
FAKE_F5 = textwrap.dedent('''
    import os, time
    import numpy as np
    HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def mode():
        try:
            return open(os.path.join(HERE, "MODE")).read().strip()
        except OSError:
            return "ok"

    class F5TTS:
        def __init__(self, model="", ckpt_file="", vocoder_local_path=None, device=None, **kw):
            m = mode()
            if m == "fail_load":
                raise RuntimeError("the fake card is missing")
            if m.startswith("slow_load"):
                time.sleep(float(m.split(":")[1]))
            print("F5TTS noise that must not reach the protocol")

        def infer(self, ref_file, ref_text, gen_text, show_info=print, nfe_step=32, speed=1.0, **kw):
            print("ref_text", ref_text)        # the real one prints this; it must go nowhere
            if "BOOM" in gen_text:
                raise ValueError("secret words " + gen_text)
            if "HANG" in gen_text:
                time.sleep(30)
            assert os.path.isfile(ref_file), ref_file
            return 0.2 * np.ones(int(24000 * 0.8), dtype=np.float32), 24000, None
''')


def better_setup(mode="ok"):
    d = reset()
    fake = d / "fakelibs"
    (fake / "torch").mkdir(parents=True)
    (fake / "torch" / "__init__.py").write_text(FAKE_TORCH)
    (fake / "f5_tts").mkdir()
    (fake / "f5_tts" / "__init__.py").write_text("")
    (fake / "f5_tts" / "api.py").write_text(FAKE_F5)
    (fake / "MODE").write_text(mode)
    f5 = d / "f5"
    (f5 / "vocos").mkdir(parents=True)
    (f5 / V.F5_CHECKPOINT).write_bytes(b"x")
    (f5 / "vocos" / "config.yaml").write_text("x")
    (f5 / "vocos" / "pytorch_model.bin").write_bytes(b"x")
    CFG["f5_dir"] = str(f5)
    V._second_card = lambda: dict(CAPABLE)
    worker = str(HERE / "jarvis_f5_worker.py")
    code = (f"import sys, runpy; sys.path.insert(0, {str(fake)!r}); "
            f"sys.argv = ['jarvis_f5_worker.py', '--checkpoint', 'c', '--vocoder', 'v']; "
            f"runpy.run_path({worker!r}, run_name='__main__')")
    V._worker_command = lambda: [sys.executable, "-c", code]
    return d, fake


def wait_for(cond, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def t_better_voice_switch():
    reset()
    gate = Gate()
    code, out = V.set_better({"enabled": True}, gate=gate, tier_of=ASK, spawn=inline)
    check("without a capable second card: 503 with the reason, no card",
          code == 503 and "second graphics card" in out["error"] and not gate.cards, out)
    V._second_card = lambda: dict(CAPABLE)
    for outcome in ("denied", "timed_out"):
        gate = Gate(outcome)
        V.set_better({"enabled": True}, gate=gate, tier_of=ASK, spawn=inline)
        check(f"{outcome}: stays off", not V._read_state()["better_voice"]
              and gate.cards[0][0] == "better_voice_enable")
    gate = Gate()
    code, out = V.set_better({"enabled": True}, gate=gate, tier_of=ASK, spawn=inline)
    check("ON: 202 pending, one better_voice_enable card, then on when approved",
          code == 202 and out["pending"] and V._read_state()["better_voice"], (code, out))
    check("the card names the card, the memory estimate, idle stop, standby and non-commercial",
          "RTX 2060" in gate.cards[0][2] and "not measured" in gate.cards[0][2]
          and "standby" in gate.cards[0][2] and "non-commercial" in gate.cards[0][2])
    gate = Gate()
    code, out = V.set_better({"enabled": False}, gate=gate)
    check("OFF: immediate, no card", code == 200 and not gate.cards
          and not V._read_state()["better_voice"])
    code, out = V.set_better({"enabled": True}, gate=Gate(), tier_of=lambda a: "auto", spawn=inline)
    check("tier not 'ask': refused, no card", code == 503 and "'ask'" in out["error"])
    check("a non-boolean: 400", V.set_better({"enabled": "yes"})[0] == 400)


def t_better_voice_loads_on_demand_with_zipvoice_meanwhile():
    d, fake = better_setup("slow_load:1.5")
    vid = make_voice()
    use(vid)
    V._write_state(better_voice=True)
    check("nothing is started before Jarvis speaks", V._F5.proc is None and V._F5.state == "off")
    wav = S.say("First sentence while it loads.")
    row = S.say_timings()[-1]
    check("the first sentence is spoken by ZipVoice in the same voice while F5 loads - never "
          "silence", wav and row["engine"] == "zipvoice" and row["voice"] == vid
          and "loading" in row["note"], row)
    check("the F5 process was started", V._F5.proc is not None and V._F5.state == "loading")
    check("it becomes ready", wait_for(lambda: V._F5.state == "ready"), V._F5.why)
    wav = S.say("Second sentence, on the second card.")
    row = S.say_timings()[-1]
    check("then F5 speaks", wav and row["engine"] == "f5" and row["voice"] == vid, row)
    x, sr = S._read_wav(wav)
    check("its audio came back through the pipe intact (0.8 s at 24 kHz)",
          sr == 24000 and abs(len(x) / sr - 0.8) < 0.01, (sr, len(x)))
    st = V.status()
    check("status: better voice ready, speaking with f5",
          st["better_voice"]["state"] == "ready" and st["speaking_with"] == "f5", st["better_voice"])
    # A sentence that fails in F5 falls back to ZipVoice for that sentence.
    wav = S.say("BOOM goes this one.")
    row = S.say_timings()[-1]
    check("a sentence F5 fails on is spoken by ZipVoice, and only the error's NAME is kept",
          wav and row["engine"] == "zipvoice" and "ValueError" in row["note"]
          and "secret" not in json.dumps(row), row)
    check("... and F5 stays ready for the next", V._F5.state == "ready")
    proc = V._F5.proc
    V._F5.check_idle(now=V._mono() + 60 * V.F5_IDLE_MINUTES + 1)
    check("idle for the idle minutes: stopped, and the process is really gone",
          V._F5.state == "off" and V._F5.proc is None and wait_for(lambda: proc.poll() is not None),
          V._F5.why)
    check("... and it says why, and when it starts again", "starts again" in V._F5.why)


def t_standby_stops_it_and_keeps_it_stopped():
    d, fake = better_setup("ok")
    vid = make_voice()
    use(vid)
    V._write_state(better_voice=True)
    S.say("Start it.")
    check("ready", wait_for(lambda: V._F5.state == "ready"), V._F5.why)
    proc = V._F5.proc
    power = types.SimpleNamespace(current=lambda: "standby")
    sys.modules["jarvis_power"] = power
    try:
        out = V.sleep("Jarvis is on standby")
        check("standby: the F5 process is stopped and it says so",
              out["stopped"] and "better voice" in out["sentence"]
              and wait_for(lambda: proc.poll() is not None))
        wav = S.say("Speaking in standby.")
        row = S.say_timings()[-1]
        check("in standby custom voices still speak, from the processor, and F5 is not started",
              wav and row["engine"] == "zipvoice" and V._F5.proc is None
              and "standby" in row["note"], row)
        power.current = lambda: "active"
        S.say("Awake again.")
        check("once Jarvis leaves standby it may start again", V._F5.proc is not None)
    finally:
        sys.modules.pop("jarvis_power", None)
        V._F5.stop("test")


def t_switch_off_and_failures():
    d, fake = better_setup("ok")
    vid = make_voice()
    use(vid)
    V._write_state(better_voice=True)
    S.say("Start it.")
    wait_for(lambda: V._F5.state == "ready")
    proc = V._F5.proc
    V.set_better({"enabled": False})
    check("turning the switch off stops the process at once",
          V._F5.proc is None and wait_for(lambda: proc.poll() is not None))
    # A process that cannot load.
    d, fake = better_setup("fail_load")
    vid = make_voice()
    use(vid)
    V._write_state(better_voice=True)
    S.say("Try.")
    check("a failed load is 'failed', with its reason, and ZipVoice keeps speaking",
          wait_for(lambda: V._F5.state == "failed") and "fake card is missing" in V._F5.why
          and S.say_timings()[-1]["engine"] == "zipvoice", V._F5.why)
    S.say("Again.")
    check("it is not restarted at once (it waits before trying again)",
          V._F5.proc is None and V._F5.state == "failed")
    # A process that hangs on a sentence.
    d, fake = better_setup("ok")
    vid = make_voice()
    use(vid)
    V._write_state(better_voice=True)
    S.say("Start it.")
    wait_for(lambda: V._F5.state == "ready")
    old = V.F5_CALL_SECONDS
    V.F5_CALL_SECONDS = 1.0
    try:
        wav = S.say("HANG on this one.")
    finally:
        V.F5_CALL_SECONDS = old
    row = S.say_timings()[-1]
    check("a sentence F5 never answers: ZipVoice speaks it, and F5 is stopped as broken",
          wav and row["engine"] == "zipvoice" and V._F5.state == "failed"
          and "did not answer" in V._F5.why, (row, V._F5.why))
    # Not enough free memory on the card.
    d, fake = better_setup("ok")
    V._second_card = lambda: dict(CAPABLE, free_mb=1000)
    V._write_state(better_voice=True)
    check("too little free memory on the card: not started, and it says the numbers",
          "1,000 MB free" in V.f5_blocked())
    V._second_card = lambda: dict(CAPABLE, big_model="the big model is using the RTX 2060")
    check("the big model on the card: not started", "big model" in V.f5_blocked())


def t_the_worker_environment():
    env = V.worker_env(GPU, base={"PATH": "/bin", "JARVIS_HUD_TOKEN": "tok", "OPENAI_API_KEY": "k",
                                  "CUDA_PATH": "/cuda", "HOME": "/h"})
    check("the F5 process sees only the second card, by its id",
          env["CUDA_VISIBLE_DEVICES"] == GPU and env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID")
    check("no token or key goes with it", "JARVIS_HUD_TOKEN" not in env and "OPENAI_API_KEY" not in env)
    check("the Hugging Face libraries are told they are offline",
          env["HF_HUB_OFFLINE"] == "1" and env["TRANSFORMERS_OFFLINE"] == "1")
    try:
        V.worker_env("1")
        check("a card number instead of an id is refused", False)
    except ValueError:
        check("a card number instead of an id is refused", True)


def t_the_worker_says_only_the_error_name():
    sent = []

    class Eng:
        def infer(self, **kw):
            raise ValueError("the owner's private sentence")
    W.serve(Eng(), [json.dumps({"id": 7, "text": "private", "ref_audio": "a", "ref_text": "b"}),
                    "not json", json.dumps({"cmd": "quit"}),
                    json.dumps({"id": 8, "text": "never reached", "ref_audio": "a",
                                "ref_text": "b"})], sent.append)
    check("a failing sentence answers with the error's name only",
          sent[0] == {"id": 7, "ok": False, "error": "ValueError"}, sent)
    check("a bad line is answered, and quit stops it", len(sent) == 2 and not sent[1]["ok"])


# ------------------------------------------------------ nothing leaves --

NET = re.compile(r"\b(urlopen|urllib|requests|socket|http\.client|httpx|aiohttp|websocket|"
                 r"smtplib|ftplib)\b")


def t_no_network_in_either_file():
    for name in ("jarvis_voices.py", "jarvis_f5_worker.py"):
        src = (HERE / name).read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        code = re.sub(r'"""[\s\S]*?"""', "", code)
        hits = sorted(set(NET.findall(code)))
        check(f"{name} makes no network call (no {', '.join(['urlopen', 'socket', 'requests'])}...)",
              not hits, hits)


def t_nothing_leaves_at_run_time():
    reset()
    calls = []
    real = (socket.socket.connect, socket.create_connection)

    def refuse(*a, **k):
        calls.append(a[1:] if len(a) > 1 else a)
        raise OSError("no network in this test")
    socket.socket.connect = refuse
    socket.create_connection = refuse
    try:
        vid = make_voice("Secret Name", words="Private words spoken into the recording for Jarvis")
        use(vid)
        S.say("A private sentence about the owner's email.")
        V.status()
        V.delete({"voice": vid})
    finally:
        socket.socket.connect, socket.create_connection = real
    check("creating, switching, speaking, status and deleting open no connection", not calls, calls)
    blob = json.dumps(AUDIT) + json.dumps(EVENTS) + json.dumps(S.say_timings())
    check("no name, words or text in an audit line, an event or a timing row",
          "Secret" not in blob and "Private" not in blob and "private" not in blob
          and "email" not in blob, blob[:300])
    check("the module never prints or logs anything itself",
          not re.search(r"^\s*print\(", re.sub(r'def _time_cli[\s\S]*', "",
                                              (HERE / "jarvis_voices.py").read_text()), re.M)
          and "logging." not in (HERE / "jarvis_voices.py").read_text())


# ------------------------------------------------------ the real ZipVoice --

def t_real_zipvoice():
    base = os.environ.get("JARVIS_TEST_VOICE_MODELS")
    zdir = Path(base) / "zipvoice" if base else None
    if not zdir or not (zdir / "tokens.txt").is_file():
        return check("SKIP - set JARVIS_TEST_VOICE_MODELS to a voice-models folder holding "
                     "zipvoice\\ to run the real ZipVoice", True)
    prompt = zdir / "test_wavs" / "news-female.wav"
    ptxt = zdir / "test_wavs" / "prompt.txt"
    if not prompt.is_file() or not ptxt.is_file():
        return check("SKIP - the model folder has no test_wavs/news-female.wav to use as a "
                     "recording", True)
    words = next(l.split(" ", 1)[1].strip() for l in ptxt.read_text(encoding="utf-8").splitlines()
                 if l.startswith("news-female.wav"))
    reset(zipvoice=False)
    V._ZIP.update(built=False)
    CFG["zipvoice_dir"] = str(zdir)
    code, out = V.create({"name": "News reader", "clip": b64(prompt.read_bytes()),
                          "transcript": words}, gate=Gate(), tier_of=ASK, spawn=inline,
                         check=NOT_OWNER)
    use(out["voice"])
    for text in ("Of course. I have added the dentist to Tuesday at ten.",
                 "The weather tomorrow looks mild, with light rain in the afternoon."):
        wav = S.say(text)
        row = S.say_timings()[-1]
        print(f"        real ZipVoice: {row['chars']} characters, {row['seconds']:.2f} s to make, "
              f"{row['audio_seconds']:.2f} s of speech (RTF {row['rtf']})")
    x, sr = S._read_wav(wav)
    check("the real ZipVoice speaks in the recorded voice (24 kHz, a few seconds of sound)",
          row["engine"] == "zipvoice" and sr == 24000 and 1.0 < len(x) / sr < 20
          and float(np.max(np.abs(x))) > 0.05, row)


# --------------------------------------------------------------- the patch --

def _rehearse():
    import _skeleton
    import test_second_card as TS
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-voices-"))
    try:
        with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(TS._stand_in())
        (d / "jarvis_gate.py").write_text(
            _skeleton.build("ui-control-wiring.patch", target="jarvis_gate.py"), encoding="utf-8")
        for name, inc in (("note-capture.patch", ["--include=jarvis_gate.py"]),
                          ("second-card.patch", []), ("wiki.patch", []), ("big-model.patch", [])):
            lf = d / name
            lf.write_bytes((HERE / name).read_bytes().replace(b"\r\n", b"\n"))
            r = subprocess.run([git, "apply", *inc, str(lf)], cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{name}: {r.stderr}", "", "", "", ""
        before = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        gate_before = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        lf = d / "voices.patch"
        lf.write_bytes((HERE / "voices.patch").read_bytes().replace(b"\r\n", b"\n"))
        after = gate_after = ""
        for args in (["apply", "--check"], ["apply"], ["apply", "--check", "--reverse"]):
            r = subprocess.run([git, *args, str(lf)], cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"git {' '.join(args)}: {r.stderr}", before, "", gate_before, ""
            if args == ["apply"]:
                after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
                gate_after = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        for name in ("voices.patch", "big-model.patch", "wiki.patch", "second-card.patch"):
            r = subprocess.run([git, "apply", "--reverse", str(d / name)], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"reverse {name}: {r.stderr}", before, after, gate_before, gate_after
        return True, "", before, after, gate_before, gate_after
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, err, before, after, gb, ga = _rehearse()
    check("voices.patch applies after big-model.patch to what the earlier patches wrote, "
          "reverses, and big-model, wiki and second-card still reverse after it", ok, err)
    if not ok:
        return
    i = after.index('if path == "/api/voice/voices":')
    blk = after[i:i + 1400]
    check("GET /api/voice/voices checks origin and token and answers status()",
          "_origin_ok(self)" in blk and "_token_ok(self)" in blk
          and "jarvis_voices.status()" in blk)
    check("... and a missing module is a 503, like the other voice routes",
          "except ImportError:" in blk and "self._send(503" in blk)
    i = after.index('if route in ("/api/voice/voices/create"')
    blk = after[i:i + 3000]
    check("POST create/active/delete/better check origin and token and hand the body over",
          "_origin_ok(self)" in blk and "_token_ok(self)" in blk
          and "jarvis_voices.handle_post(route, body)" in blk
          and all(r in blk for r in ("/api/voice/voices/active", "/api/voice/voices/delete",
                                     "/api/voice/voices/better")))
    check("... a missing module is a 503, and an error names the exception only",
          "self._send(503" in blk and '{"error": type(exc).__name__}' in blk
          and "str(exc)" not in blk)
    check("the routes sit after the big model's",
          after.index('"/api/big-model", "/api/deep")') < after.index('"/api/voice/voices"')
          and after.index('if route in ("/api/big-model"')
          < after.index('if route in ("/api/voice/voices/create"'))
    check("the big model's blocks are untouched",
          before[before.index('if route in ("/api/big-model"'):].split("\n\n")[0]
          == after[after.index('if route in ("/api/big-model"'):].split("\n\n")[0])
    check("the approval notice knows custom_voice and better_voice_enable stay on this PC",
          '"custom_voice": ("yes", "local",' in ga and '"better_voice_enable": ("yes", "local",' in ga
          and '"big_model_enable"' in ga)
    for start, end in (('        if path == "/api/voice/voices"', '        if path in ("/api/memory/pending"'),
                       ('        if route in ("/api/voice/voices/create"', '        if route in ("/api/memory/forget"')):
        block = after[after.index(start):after.index(end)]
        try:
            compile("def f(self, path, route):\n" + block, "<patched block>", "exec")
            check(f"the patched block {start.strip()[:34]}... compiles", True)
        except SyntaxError as exc:
            check(f"the patched block {start.strip()[:34]}... compiles", False, str(exc))
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies voices.patch last, right after big-model.patch",
          names and names[-1] == "voices.patch" and names[-2] == "big-model.patch")
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    import _where
    check("apply-patches.ps1 and _where.SHIPPED copy jarvis_voices.py and jarvis_f5_worker.py in",
          "'jarvis_voices.py'" in shipped and "'jarvis_f5_worker.py'" in shipped
          and "jarvis_voices.py" in _where.SHIPPED and "jarvis_f5_worker.py" in _where.SHIPPED)
    ps = (HERE / "jarvis_power_switch.py").read_text(encoding="utf-8")
    check("standby asks jarvis_voices to sleep too", '"jarvis_voices"' in ps)


def t_the_toml():
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    for action in ("custom_voice", "better_voice_enable"):
        check(f'the shipped toml has {action} = "ask"',
              re.search(rf'^{action}\s*=\s*"ask"', toml, re.M) is not None)
    try:
        import jarvis_framework as fw
        got = (fw.action_tier("custom_voice"), fw.action_tier("better_voice_enable"))
        check("jarvis_framework reads both as 'ask'", got == ("ask", "ask"), got)
    except Exception as exc:
        check("jarvis_framework reads them", False, repr(exc))
    go = (HERE / "gate-outcome.patch").read_text(encoding="utf-8")
    check("a 'no' on either card proposes no standing rule (gate-outcome's list)",
          '+    "custom_voice",' in go and '+    "better_voice_enable",' in go)


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has /api/voice/voices (voices.patch applied)",
          '"/api/voice/voices"' in s)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    try:
        for fn in tests:
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc(file=sys.stdout)
    finally:
        try:
            V._F5.stop("tests done")
        except Exception:
            pass
        S._tts_cache = S._UNSET
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
