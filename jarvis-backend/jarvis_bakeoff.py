"""jarvis_bakeoff.py - the voice upgrades' bake-off: measure first, then
"replace" or "keep what we have".

NEW MODULE, shipped whole beside jarvis_hud.py (apply-patches.ps1 copies
it). Nothing in Jarvis calls it. The owner runs it on his PC, in the
backend's folder, with one line:

    cd "<the backend folder>"; py -3 jarvis_bakeoff.py

WHY IT EXISTS. The owner chose two voice upgrades on 2026-09-26 - "a newer
'Hey Jarvis' detector and a fast voice-copying voice, each measured before it
replaces anything". The feasibility audit's guardrails
(docs/FEASIBILITY-AUDIT-2026-09-26.md section 4) add: an invisible upgrade
gets NO switch - it is measured, then shipped or dropped; and a winner
REPLACES the old part, never sits beside it. So each upgrade is a bake-off
that can end in "keep what we have", and this is the bake-off.

TWO PARTS, each ending in ONE verdict, by rules written down BEFORE anything
was measured (WAKE_RULES and VOICE_RULES below; backend/README.md, "Voice
upgrades: the bake-off", says the same in plain words):

  1. "Hey Jarvis" - today's detector (openWakeWord's hey_jarvis_v0.1) against
     the candidate the owner trained with livekit-wakeword
     (tools/train_wakeword.py). Both run on the SAME front end and the SAME
     clips: the owner's own "hey Jarvis" recordings, an hour of the room
     (television, talking) in which nobody says it, and 110 sentences in the
     11 built-in Kokoro voices (4 of each 10 start with "hey Jarvis"). Each
     is scored alone AND with the owner's own verifier ("is it you saying
     hey Jarvis"), because a new detector changes when that is asked.
  2. The voice - ZipVoice (today) against Pocket TTS (the candidate), both on
     the processor, both copying the same recorded voice: time to first
     sound, how fast each makes speech (real-time factor), how much graphics
     memory each takes while the chat model sits on the 8 GB card, whether
     each follows the speaking-speed setting, and a blind listening sheet -
     pairs A and B, the owner picks, and only then is it said which was
     which.

NOTHING IS SWITCHED ON. This program never changes a setting, a model or a
file of Jarvis's. A "replace" verdict says what a builder then changes (one
line in jarvis_voices.py or jarvis_wakeword.py, and the phone's assets for the
wake word) - and until then Jarvis runs exactly as before.

WHAT IT KEEPS, AND WHERE. Everything goes in one folder,
<config dir>/voice/bakeoff/<date-time>/ (normally
C:\\Users\\<you>\\.openjarvis\\voice\\bakeoff\\...): results.txt (what was
printed), results.json (every number), and listening\\ (the A/B pairs).
The owner's "hey Jarvis" recordings are NOT kept: each is recorded into a
temporary file, read, and deleted at once, and scored from memory. A kept
recording of the owner saying "hey Jarvis" is exactly what someone would
need to wake Jarvis in his voice - and the voice check cannot tell a
recording from the real voice. The room is recorded a minute at a time the
same way: none of it is kept. WAV files the owner puts into
<config dir>/voice/bakeoff/hey-jarvis/ himself are used too, and left where
he put them.

NOTHING LEAVES THE PC. The only network call is to this PC's own Ollama at
127.0.0.1 (which model is loaded, and how much of it is on the card), made
through jarvis_local_http so no proxy sees it. test_voice_upgrades.py scans
this file for any other.

Standard library plus numpy, onnxruntime and sherpa-onnx - all already
installed for the voice. Recording from the microphone uses Windows' own
winmm (no package); on another system, or if it fails, WAV files dropped
into the folder above are used instead.
"""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy comes with sherpa-onnx
    np = None  # type: ignore

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

REPLACE = "replace"
KEEP = "keep what we have"

# --------------------------------------------------------------------------
#   The rules - fixed before anything was measured. Changing one after a run
#   would be choosing the answer; a change needs its own dated reason in
#   backend/README.md.
# --------------------------------------------------------------------------

WAKE_RULES = {
    # Enough of the owner's own voice and room to mean something.
    "min_owner_clips": 10,
    "min_room_minutes": 60.0,
    # The candidate's cost per 80 ms step on the PC's processor (today's is
    # about 0.04 ms; livekit's own example head took 0.29 ms in the dev
    # container). The phone is several times slower: 2 ms here is the most
    # that leaves the phone's step comfortably inside its 80 ms.
    "max_head_ms": 2.0,
    # A clear win is needed, not a tie: fewer of the owner's clips missed,
    # or at most half of today's false wake-ups in the room.
    "room_win_ratio": 0.5,
}
WAKE_RULE_WORDS = (
    "At least 10 of your own \"hey Jarvis\" recordings, and at least 60 minutes of the room.",
    "Your recordings: the new detector hears at least as many as today's - alone, and with "
    "your own \"is it you\" check.",
    "The room: the new detector wakes up by mistake no more often than today's.",
    "The 110 built-in-voice sentences: it hears at least as many \"hey Jarvis\" ones, and "
    "wakes on no more of the others.",
    "A clear win: it misses fewer of your recordings, or wakes by mistake at most half as "
    "often as today's in the room (today's must have woken at least once).",
    "Cost: at most 2 ms of processor time per 80 ms of sound, so the phone keeps up.",
)

VOICE_RULES = {
    # Pocket TTS's median time to first sound must be at most this share of
    # ZipVoice's: "fast" was the reason to try it, so it must be clearly
    # faster, not about the same.
    "first_sound_ratio": 0.8,
    # Pocket must make speech at least as fast as it is spoken (median over
    # the test sentences), or a long answer would stall mid-sentence.
    "max_rtf": 1.0,
    # It runs on the processor: the graphics card's memory may not rise by
    # more than this while it speaks (the 8 GB card has about 0.25 GB to
    # spare beside the chat model - docs/MODEL-TOPOLOGY.md).
    "max_vram_rise_mb": 100,
    # The blind listening sheet: Pocket's or "the same", in at least this
    # many of the pairs.
    "min_ear_pairs": 2,
    "ear_pairs": 3,
    # The speaking speed: at "Faster" a sentence must be at least 8% shorter
    # than at "Normal" (at "Slower", 8% longer) to count as following it.
    "speed_change": 0.08,
}
VOICE_RULE_WORDS = (
    "Both voices installed, and every test sentence made some sound.",
    "Time to first sound: Pocket TTS takes at most 80% of ZipVoice's time (the middle value "
    "of the test phrases).",
    "Speed of making speech: Pocket TTS makes each second of speech in at most one second.",
    "Graphics memory: it rises by at most 100 MB while Pocket TTS speaks, and the chat model "
    "stays on the card.",
    "Your ear: in the blind pairs, Pocket TTS's or \"the same\" in at least 2 of 3.",
    "Speaking speed: if you chose Slower or Faster, Pocket TTS follows it.",
)

# --------------------------------------------------------------------------
#   The test material
# --------------------------------------------------------------------------

#: What the owner reads when recording "hey Jarvis" (one per recording).
OWNER_LINES = (
    "Hey Jarvis, what time is it?",
    "Hey Jarvis, set a timer for ten minutes.",
    "Hey Jarvis, what's the weather tomorrow?",
    "Hey Jarvis, remind me to call Mum at six.",
    "Hey Jarvis, turn off the kitchen light.",
    "Hey Jarvis, what's on my calendar today?",
    "Hey Jarvis.",
    "Hey Jarvis, add milk to the shopping list.",
    "Hey Jarvis, how long until the timer ends?",
    "Hey Jarvis, play some music.",
    "Hey Jarvis, what did I say about the dentist?",
    "Hey Jarvis, stop.",
)
#: The built-in voices' test: 4 with the phrase, 6 without (the same design
#: as the 110-clip test in backend/README.md, "What was measured here").
KOKORO_HEY = (
    "Hey Jarvis, what time is it?",
    "Hey Jarvis, set a timer for five minutes.",
    "Hey Jarvis, what is the weather like tomorrow?",
    "Hey Jarvis.",
)
KOKORO_OTHER = (
    "Hey Jason, can you pass me the salt?",
    "Put the jar of jam back on the top shelf.",
    "In that film, the computer was called Jarvis.",
    "Harvest time is the busiest part of the year.",
    "Hey, do you know where I left my keys?",
    "The service starts at nine, so we should leave early.",
)
#: The first piece of an answer - what is spoken first, from the first
#: comma (CLAUDE.md, 2026-09-24): time to first sound is measured on these.
FIRST_PHRASES = (
    "Of course,",
    "Sure, I've set a timer for ten minutes.",
    "Good morning,",
    "Right, the dentist is on Tuesday at ten.",
    "Done,",
    "It looks like rain this afternoon,",
)
#: Whole sentences: how fast each engine makes speech, and the listening pairs.
SENTENCES = (
    "Of course. I have added the dentist to Tuesday at ten.",
    "The weather tomorrow looks mild, with light rain in the afternoon, so you may want a "
    "coat when you head out.",
    "You have two meetings this afternoon, and the first one starts in forty minutes.",
)

# --------------------------------------------------------------------------
#   Small helpers (pure, tested)
# --------------------------------------------------------------------------


def median(values) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.median(vals) if vals else None


def count_wakes(scores, threshold: float, refractory: int = 25) -> int:
    """Separate wake-ups in a stream of 80 ms scores: a score at or above the
    threshold starts one; the next may start only `refractory` steps (2 s)
    later - what a listener that waits after waking would count."""
    n, quiet_until = 0, -1
    for i, s in enumerate(scores):
        if i < quiet_until:
            continue
        if s >= threshold:
            n += 1
            quiet_until = i + refractory
    return n


def read_wav(path):
    """(float32 mono samples in -1..1, sample rate) from a 16- or 24-bit PCM
    WAV of any length. Raises ValueError, in words."""
    try:
        with wave.open(str(path), "rb") as w:
            rate, width, chans = w.getframerate(), w.getsampwidth(), w.getnchannels()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError, OSError) as exc:
        raise ValueError(f"{Path(path).name} is not a WAV file this can read "
                         f"({type(exc).__name__})") from None
    if width == 2:
        x = np.frombuffer(frames[: len(frames) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(frames[: len(frames) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        v = b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v.astype(np.float32) / 8388608.0
    else:
        raise ValueError(f"{Path(path).name} is {width * 8}-bit; save it as 16-bit")
    if chans > 1:
        x = x[: len(x) // chans * chans].reshape(-1, chans).mean(axis=1)
    return x.astype(np.float32), int(rate)


def write_wav(path, samples, rate: int) -> None:
    x = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes((x * 32767.0).astype("<i2").tobytes())


# --------------------------------------------------------------------------
#   The verdicts (pure: numbers in, a verdict and its reasons out)
# --------------------------------------------------------------------------


def wake_verdict(m: dict, rules: dict = WAKE_RULES) -> tuple:
    """(REPLACE or KEEP, [reason, ...]). `m` is wake_measure()'s dict. Any
    rule not met - or not measurable - keeps today's detector."""
    why = []
    if not m.get("candidate_ok"):
        return KEEP, [f"There is no candidate to measure: {m.get('candidate_why') or 'none'}."]
    own = m.get("owner") or {}
    room = m.get("room") or {}
    kok = m.get("kokoro") or {}
    n_own = int(own.get("clips", 0))
    if n_own < rules["min_owner_clips"]:
        why.append(f"Only {n_own} of your own recordings (at least "
                   f"{rules['min_owner_clips']} are needed).")
    minutes = float(room.get("minutes", 0.0))
    if minutes < rules["min_room_minutes"]:
        why.append(f"Only {minutes:.0f} minutes of the room (at least "
                   f"{rules['min_room_minutes']:.0f} are needed).")
    if n_own:
        if own.get("cand_heard", 0) < own.get("cur_heard", 0):
            why.append(f"It heard {own.get('cand_heard')} of your {n_own} recordings; today's "
                       f"heard {own.get('cur_heard')}.")
        if own.get("verifier"):
            if own.get("cand_heard_v", 0) < own.get("cur_heard_v", 0):
                why.append(f"With your own check it let {own.get('cand_heard_v')} of your "
                           f"recordings through; today's let {own.get('cur_heard_v')}.")
    if minutes > 0:
        if room.get("cand_per_hour", 0.0) > room.get("cur_per_hour", 0.0):
            why.append(f"In the room it woke by mistake {room.get('cand_per_hour'):.1f} times "
                       f"an hour; today's {room.get('cur_per_hour'):.1f}.")
    if kok.get("hey", 0):
        if kok.get("cand_hey", 0) < kok.get("cur_hey", 0):
            why.append(f"Of the built-in voices' {kok.get('hey')} \"hey Jarvis\" sentences it "
                       f"heard {kok.get('cand_hey')}; today's heard {kok.get('cur_hey')}.")
        if kok.get("cand_other", 0) > kok.get("cur_other", 0):
            why.append(f"It woke on {kok.get('cand_other')} of the {kok.get('other')} other "
                       f"sentences; today's on {kok.get('cur_other')}.")
    else:
        why.append("The built-in voices' sentences could not be made (Kokoro is not "
                   "installed), so that test did not run.")
    head_ms = m.get("cand_head_ms")
    if head_ms is None or head_ms > rules["max_head_ms"]:
        why.append(f"It costs {head_ms if head_ms is not None else '?'} ms per step; the most "
                   f"allowed is {rules['max_head_ms']} ms.")
    fewer_misses = n_own and own.get("cand_heard", 0) > own.get("cur_heard", 0)
    cur_room = room.get("cur_wakes", 0)
    fewer_wakes = (minutes > 0 and cur_room >= 1 and room.get("cand_wakes", 0)
                   <= cur_room * rules["room_win_ratio"])
    if not (fewer_misses or fewer_wakes):
        why.append("No clear win: it neither missed fewer of your recordings nor woke by "
                   "mistake at most half as often as today's.")
    return (KEEP, why) if why else (REPLACE, ["Every rule was met."])


def voice_verdict(m: dict, rules: dict = VOICE_RULES) -> tuple:
    """(REPLACE or KEEP, [reason, ...]) for Pocket TTS against ZipVoice."""
    if not m.get("pocket_ok"):
        return KEEP, [f"Pocket TTS could not be measured: {m.get('pocket_why') or 'unknown'}."]
    if not m.get("zipvoice_ok"):
        return KEEP, [f"ZipVoice could not be measured, so there is nothing to compare with: "
                      f"{m.get('zipvoice_why') or 'unknown'}."]
    why = []
    if m.get("silent"):
        why.append(f"Some sentences made no sound: {', '.join(m['silent'])}.")
    zf, pf = m.get("zipvoice_first"), m.get("pocket_first")
    if zf is None or pf is None or pf > zf * rules["first_sound_ratio"]:
        why.append(f"Time to first sound: Pocket TTS {_s(pf)}, ZipVoice {_s(zf)} - it needed to "
                   f"be at most {rules['first_sound_ratio']:.0%} of ZipVoice's.")
    rtf = m.get("pocket_rtf")
    if rtf is None or rtf > rules["max_rtf"]:
        why.append(f"Pocket TTS took {rtf if rtf is not None else '?'} seconds per second of "
                   f"speech; at most {rules['max_rtf']} is allowed.")
    rise = m.get("vram_rise_mb")
    if rise is None:
        why.append("The graphics card's memory could not be read (nvidia-smi), so it is not "
                   "known that Pocket TTS stays off the card.")
    elif rise > rules["max_vram_rise_mb"]:
        why.append(f"The graphics card's memory rose by {rise} MB while the two voices were "
                   f"made; at most {rules['max_vram_rise_mb']} MB is allowed.")
    if m.get("chat_pushed_off"):
        why.append("The chat model lost room on the graphics card while the two voices were "
                   "made.")
    ear = m.get("ear") or {}
    if not ear.get("answered"):
        why.append("The listening pairs were not answered, and your ear decides this one.")
    elif ear.get("pocket", 0) + ear.get("same", 0) < rules["min_ear_pairs"]:
        why.append(f"You preferred ZipVoice in {ear.get('zipvoice', 0)} of "
                   f"{ear.get('answered', 0)} pairs.")
    sp = m.get("speed") or {}
    if sp.get("choice") in ("slower", "faster") and not sp.get("pocket_follows"):
        why.append(f"You chose \"{sp.get('choice')}\", and Pocket TTS does not follow the "
                   f"speaking speed.")
    return (KEEP, why) if why else (REPLACE, ["Every rule was met."])


def _s(v) -> str:
    return "?" if v is None else f"{v:.2f} s"


# --------------------------------------------------------------------------
#   Output: everything printed also goes into results.txt
# --------------------------------------------------------------------------


class Out:
    def __init__(self):
        self.lines: list = []

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        self.lines.append(text)


def ask(prompt: str, default: str = "") -> str:
    """input(), where Enter (or no console) gives `default`."""
    try:
        got = input(prompt)
    except (EOFError, KeyboardInterrupt, OSError):
        return default
    return got.strip() or default


def results_root() -> Path:
    import jarvis_voices as V
    return V._config_dir() / "voice" / "bakeoff"


# --------------------------------------------------------------------------
#   The microphone (Windows' own winmm; nothing to install)
# --------------------------------------------------------------------------


def _mci(cmd: str) -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, 0)  # type: ignore[attr-defined]
    if err:
        msg = ctypes.create_unicode_buffer(256)
        ctypes.windll.winmm.mciGetErrorStringW(err, msg, 255)  # type: ignore[attr-defined]
        raise OSError(msg.value or f"MCI error {err}")
    return buf.value


def can_record() -> bool:
    return os.name == "nt"


def record_wav(path, seconds: float) -> None:
    """Records `seconds` from the default microphone into a 16 kHz, 16-bit,
    mono WAV at `path`. Windows only; raises OSError, in words."""
    if not can_record():
        raise OSError("recording from the microphone works on Windows only")
    alias = "jarvisbakeoff"
    try:
        _mci(f"close {alias}")
    except OSError:
        pass
    _mci(f"open new type waveaudio alias {alias}")
    try:
        _mci(f"set {alias} time format ms bitspersample 16 channels 1 samplespersec 16000 "
             f"bytespersec 32000 alignment 2")
        _mci(f"record {alias}")
        time.sleep(seconds)
        _mci(f"stop {alias}")
        _mci(f'save {alias} "{path}"')
    finally:
        try:
            _mci(f"close {alias}")
        except OSError:
            pass


# --------------------------------------------------------------------------
#   Part 1: "hey Jarvis"
# --------------------------------------------------------------------------


class Heads:
    """Today's detector and the candidate on ONE front end: each clip's
    16 x 96 windows are made once (today's models), then both last models
    score the same windows."""

    def __init__(self, W, cur, cand, cand_threshold: float, verifier=None):
        self.W, self.cur, self.cand = W, cur, cand
        self.cur_thr = float(W.threshold())
        self.cand_thr = float(cand_threshold)
        self.ver = verifier
        self.cur_s = self.cand_s = 0.0
        self.steps = 0

    def _run(self, models, windows):
        t = time.perf_counter()
        out = [float(models.wake.run(None, {models.wake_in: w[None].astype(np.float32)})[0]
                     .reshape(-1)[0]) for w in windows]
        return out, time.perf_counter() - t

    def score(self, samples, rate: int) -> dict:
        """Both detectors' scores for one clip, with and without the owner's
        verifier. {"cur": [...], "cand": [...], "cur_heard", "cand_heard",
        "cur_heard_v", "cand_heard_v"}."""
        W = self.W
        _, windows = W._clip_steps(self.cur, samples, rate)
        cur, t1 = self._run(self.cur, windows)
        cand, t2 = self._run(self.cand, windows)
        self.cur_s += t1
        self.cand_s += t2
        self.steps += len(windows)
        for s in (cur, cand):
            for i in range(min(W.WARMUP_SCORES, len(s))):
                s[i] = 0.0
        out = {"cur": cur, "cand": cand,
               "cur_heard": max(cur, default=0.0) >= self.cur_thr,
               "cand_heard": max(cand, default=0.0) >= self.cand_thr}
        for key, scores in (("cur", cur), ("cand", cand)):
            out[key + "_heard_v"] = out[key + "_heard"]
            if self.ver is not None:
                gated = [i for i, s in enumerate(scores) if s >= W.VERIFIER_GATE]
                if gated:
                    p = self.ver.probabilities(np.stack([windows[i] for i in gated]))
                    out[key + "_heard_v"] = bool(float(np.max(p)) >= self.ver.threshold)
                else:
                    out[key + "_heard_v"] = False
        return out

    def ms_per_step(self) -> tuple:
        n = max(1, self.steps)
        return round(self.cur_s / n * 1000, 3), round(self.cand_s / n * 1000, 3)


def owner_clip_dir() -> Path:
    return results_root() / "hey-jarvis"


def record_owner_clips(out: Out, n: int) -> list:
    """[(samples, rate)] of the owner saying "hey Jarvis ...", held in memory
    only: each is recorded into a temporary file that is read and deleted at
    once (see the module docstring for why none is kept)."""
    got: list = []
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-hey-"))
    try:
        for i in range(n):
            line = OWNER_LINES[i % len(OWNER_LINES)]
            if ask(f"  {i + 1}/{n}: press Enter, then say  \"{line}\"  (type s and Enter to "
                   f"stop) ", "").lower() == "s":
                break
            p = tmp / "clip.wav"
            try:
                record_wav(p, 3.5)
                got.append(read_wav(p))
                out(f"      recorded {i + 1} (held in memory only)")
            except (OSError, ValueError) as exc:
                out(f"      could not record: {exc}")
                break
            finally:
                try:
                    p.unlink()
                except OSError:
                    pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return got


def listen_room(out: Out, minutes: int, heads: Heads) -> dict:
    """Records the room one minute at a time, scores each minute with both
    detectors, deletes it. Counts wake-ups; keeps no sound."""
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-room-"))
    cur_w = cand_w = 0
    done = 0.0
    try:
        for k in range(minutes):
            p = tmp / "minute.wav"
            try:
                record_wav(p, 60.0)
            except OSError as exc:
                out(f"      could not record the room: {exc}")
                break
            try:
                x, rate = read_wav(p)
            finally:
                try:
                    p.unlink()
                except OSError:
                    pass
            sc = heads.score(x, rate)
            cur_w += count_wakes(sc["cur"], heads.cur_thr)
            cand_w += count_wakes(sc["cand"], heads.cand_thr)
            done += len(x) / float(rate) / 60.0
            if k % 10 == 9:
                out(f"      {k + 1} minutes: today's woke {cur_w} times, the new one {cand_w}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    hours = done / 60.0
    return {"minutes": round(done, 1), "cur_wakes": cur_w, "cand_wakes": cand_w,
            "cur_per_hour": round(cur_w / hours, 2) if hours else 0.0,
            "cand_per_hour": round(cand_w / hours, 2) if hours else 0.0}


def kokoro_set(out: Out, heads: Heads) -> dict:
    """The 110-sentence test in the built-in Kokoro voices, made on the fly;
    nothing kept."""
    try:
        import jarvis_speech as S
        eng = S._tts_engine()
    except Exception:
        eng = None
    res = {"voices": 0, "hey": 0, "other": 0, "cur_hey": 0, "cand_hey": 0,
           "cur_other": 0, "cand_other": 0}
    if eng is None:
        return res
    try:
        speakers = max(1, int(getattr(eng, "num_speakers", 1) or 1))
    except Exception:
        speakers = 1
    res["voices"] = speakers
    for sid in range(speakers):
        for text in KOKORO_HEY + KOKORO_OTHER:
            try:
                a = eng.generate(text, sid=sid, speed=1.0)
            except Exception:
                continue
            x = np.asarray(a.samples, dtype=np.float32)
            if not len(x):
                continue
            x = x / (float(np.abs(x).max()) or 1.0) * 0.6
            sc = heads.score(x, int(a.sample_rate))
            if text in KOKORO_HEY:
                res["hey"] += 1
                res["cur_hey"] += int(sc["cur_heard"])
                res["cand_hey"] += int(sc["cand_heard"])
            else:
                res["other"] += 1
                res["cur_other"] += int(sc["cur_heard"])
                res["cand_other"] += int(sc["cand_heard"])
        out(f"      voice {sid + 1} of {speakers} done")
    return res


def wake_files_ok(W) -> tuple:
    """(ok, why): today's three files are the pinned ones."""
    d = W.model_dir()
    for name in ("melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx"):
        p = d / name
        if not p.is_file():
            return False, f"{name} is not in {d}"
        if W.sha256_file(p) != W.KNOWN_FILES[name]["sha256"]:
            return False, f"{name} in {d} is not the expected file (its SHA-256 is different)"
    return True, ""


def wake_measure(out: Out, *, record: Optional[int], room_minutes: Optional[int]) -> dict:
    import jarvis_wakeword as W
    m: dict = {"candidate_ok": False}
    ok, why = wake_files_ok(W)
    if not ok:
        m["candidate_why"] = f"today's detector is not set up right: {why}"
        return m
    cs = W.candidate_status()
    m.update(candidate_ok=cs["ok"], candidate_why=cs["why"], candidate_sha256=cs["sha256"],
             candidate_threshold=cs["threshold"], candidate_trained=cs["trained"])
    if not cs["ok"]:
        return m
    cur = W._load()
    if cur is None:
        m.update(candidate_ok=False, candidate_why=W.status()["why"] or "today's detector "
                 "did not load")
        return m
    try:
        cand = W.load_head(cs["file"])
    except Exception as exc:
        m.update(candidate_ok=False, candidate_why=str(exc) if isinstance(exc, ValueError)
                 else f"it did not load ({type(exc).__name__})")
        return m
    ver = W.load_verifier("")
    heads = Heads(W, cur, cand, cs["threshold"], ver)
    m["thresholds"] = {"today": heads.cur_thr, "candidate": heads.cand_thr}
    m["verifier"] = ver is not None

    out("  Your own \"hey Jarvis\" recordings")
    clips = []
    if record:
        out(f"    Recording up to {record} (3.5 seconds each); none is kept")
        clips += record_owner_clips(out, record)
    own = {"clips": 0, "cur_heard": 0, "cand_heard": 0, "cur_heard_v": 0, "cand_heard_v": 0,
           "verifier": ver is not None, "unreadable": 0, "from_folder": 0}
    for p in sorted(owner_clip_dir().glob("*.wav")) if owner_clip_dir().is_dir() else []:
        try:
            clips.append(read_wav(p))
            own["from_folder"] += 1
        except ValueError:
            own["unreadable"] += 1
    for x, rate in clips:
        sc = heads.score(x, rate)
        own["clips"] += 1
        for k in ("cur_heard", "cand_heard", "cur_heard_v", "cand_heard_v"):
            own[k] += int(sc[k])
    m["owner"] = own
    out(f"    {own['clips']} recordings: today's heard {own['cur_heard']}, the new one "
        f"{own['cand_heard']}" + (f"; with your check {own['cur_heard_v']} and "
                                  f"{own['cand_heard_v']}" if ver is not None else
                                  " (no \"is it you\" check trained yet)"))

    out("  The room")
    if room_minutes:
        out(f"    Listening for {room_minutes} minutes. Do not say \"hey Jarvis\"; talking "
            f"and the television are what it should hear.")
        m["room"] = listen_room(out, room_minutes, heads)
        r = m["room"]
        out(f"    {r['minutes']:.0f} minutes: today's woke {r['cur_wakes']} times "
            f"({r['cur_per_hour']:.1f} an hour), the new one {r['cand_wakes']} "
            f"({r['cand_per_hour']:.1f} an hour)")
    else:
        m["room"] = {"minutes": 0.0}
        out("    skipped")

    out("  The built-in voices (110 sentences, nothing kept)")
    m["kokoro"] = kokoro_set(out, heads)
    k = m["kokoro"]
    if k["hey"]:
        out(f"    \"hey Jarvis\" heard: today's {k['cur_hey']} of {k['hey']}, the new one "
            f"{k['cand_hey']}; woke on the others: today's {k['cur_other']} of {k['other']}, "
            f"the new one {k['cand_other']}")
    else:
        out("    skipped: the built-in voice (Kokoro) is not installed")
    m["cur_head_ms"], m["cand_head_ms"] = heads.ms_per_step()
    out(f"  Cost per 80 ms step: today's {m['cur_head_ms']} ms, the new one "
        f"{m['cand_head_ms']} ms")
    return m


# --------------------------------------------------------------------------
#   Part 2: the voice
# --------------------------------------------------------------------------


class Vram:
    """Polls nvidia-smi for every card's used memory, in the background."""

    def __init__(self, run: Optional[Callable] = None):
        self.run = run or self._query
        self.samples: list = []
        self._stop = threading.Event()
        self._t: Optional[threading.Thread] = None
        self.available = self.run() is not None

    @staticmethod
    def _query() -> Optional[list]:
        exe = shutil.which("nvidia-smi") or (
            r"C:\Windows\System32\nvidia-smi.exe" if os.name == "nt" else None)
        if not exe:
            return None
        try:
            r = subprocess.run([exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        if r.returncode != 0:
            return None
        try:
            return [int(float(v)) for v in r.stdout.split()]
        except ValueError:
            return None

    def now(self) -> Optional[list]:
        return self.run()

    def start(self) -> None:
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                got = self.run()
                if got is not None:
                    self.samples.append(got)
                self._stop.wait(0.25)
        self._t = threading.Thread(target=loop, daemon=True, name="jarvis-bakeoff-vram")
        self._t.start()

    def stop(self) -> Optional[list]:
        self._stop.set()
        if self._t is not None:
            self._t.join(5)
        if not self.samples:
            return None
        return [max(s[i] for s in self.samples if len(s) > i) for i in range(len(self.samples[0]))]


def rise_mb(before: Optional[list], peak: Optional[list]) -> Optional[int]:
    if before is None or peak is None or len(before) != len(peak):
        return None
    return max(0, max(p - b for p, b in zip(peak, before)))


def ollama_loaded() -> Optional[list]:
    """[(name, size, size_vram)] from this PC's own Ollama, or None."""
    try:
        import urllib.request
        import jarvis_local_http as H
        req = urllib.request.Request("http://127.0.0.1:11434/api/ps")
        with H.urlopen(req, 5) as r:
            doc = json.loads(r.read().decode("utf-8"))
        return [(str(x.get("name", "")), int(x.get("size", 0)), int(x.get("size_vram", 0)))
                for x in doc.get("models", []) if isinstance(x, dict)]
    except Exception:
        return None


def reference_voice(out: Out, work: Path):
    """The voice both engines copy: the owner's chosen custom voice, else any
    custom voice, else a stand-in made by the built-in voice reading one of
    Jarvis's own sentences (a synthetic voice - no person's)."""
    import jarvis_voices as V
    st = V._read_state()
    ids = [st["active"]] if st["active"] != V.BUILTIN else []
    ids += [r["id"] for r in V.list_voices() if r.get("ready") and r["id"] not in ids]
    for vid in ids:
        v = V.load_voice(vid)
        if v is not None:
            out(f"  Copying your custom voice \"{v.name}\"")
            return v
    try:
        import jarvis_speech as S
        eng = S._tts_engine()
    except Exception:
        eng = None
    if eng is None:
        return None
    text = V.SENTENCES[0]
    a = eng.generate(text, sid=0, speed=1.0)
    x = np.asarray(a.samples, dtype=np.float32)
    if not len(x):
        return None
    folder = work / "reference-voice"
    folder.mkdir(parents=True, exist_ok=True)
    x = V.resample(x, int(a.sample_rate), V.SAMPLE_RATE)
    write_wav(folder / "clip.wav", x, V.SAMPLE_RATE)
    out("  No custom voice yet: both engines copy the built-in voice reading one sentence "
        "(a made-up voice, not a person's)")
    return V.Voice(id="bakeoff-reference", name="built-in voice sample", transcript=text,
                   seconds=len(x) / float(V.SAMPLE_RATE), created=time.time(), folder=folder)


def _timed(gen: Callable, text: str, v, speed: float, first: bool,
           seed: Optional[int] = None) -> dict:
    """One engine call: seconds to first sound, seconds in all, seconds of
    speech. `first`: the engine can say when its first piece is ready (and
    takes a `seed`, to repeat its random choices)."""
    t0 = time.perf_counter()
    mark: list = []
    try:
        if first:
            kw = {"seed": seed} if seed is not None else {}
            samples, rate, _took = gen(text, v, speed, first_audio=lambda: mark.append(
                time.perf_counter()), **kw)
        else:
            samples, rate, _took = gen(text, v, speed)
    except Exception as exc:
        return {"ok": False, "why": type(exc).__name__ + (f": {exc}" if str(exc) else "")}
    total = time.perf_counter() - t0
    audio = len(samples) / float(rate) if rate else 0.0
    return {"ok": audio > 0, "first": (mark[0] - t0) if mark else total, "total": total,
            "audio": audio, "samples": samples, "rate": rate}


def voice_measure(out: Out, work: Path, *, listen: bool, vram: Optional[Vram] = None,
                  rng: Optional[random.Random] = None) -> dict:
    import jarvis_voices as V
    m: dict = {}
    zok, zwhy = V.zipvoice_state()
    pok, pwhy = V.pocket_state(verify=True)
    m.update(zipvoice_ok=zok, zipvoice_why="" if zok else zwhy, pocket_ok=pok,
             pocket_why="" if pok else pwhy)
    if not (zok and pok):
        if not pok:
            out(f"  Pocket TTS: {pwhy}")
        if not zok:
            out(f"  ZipVoice: {zwhy}")
        return m
    v = reference_voice(out, work)
    if v is None:
        m.update(zipvoice_ok=False, zipvoice_why="there is no voice to copy: no custom voice, "
                 "and the built-in voice is not installed")
        return m
    engines = {"zipvoice": (V.zipvoice_generate, False), "pocket": (V.pocket_generate, True)}
    vram = vram or Vram()
    before = vram.now() if vram.available else None
    chat_before = ollama_loaded()
    out("  Loading both (not timed)...")
    for name, (gen, first) in engines.items():
        t = time.perf_counter()
        r = _timed(gen, "Hello.", v, 1.0, first)
        m[name + "_load_seconds"] = round(time.perf_counter() - t, 2)
        if not r["ok"]:
            m[name + "_ok"] = False
            m[name + "_why"] = f"it made no sound ({r.get('why', 'nothing came out')})"
            return m
    if vram.available:
        vram.start()
    rows: dict = {"zipvoice": [], "pocket": []}
    silent: list = []
    try:
        out("  Time to first sound, on the first piece of an answer:")
        for text in FIRST_PHRASES:
            for name, (gen, first) in engines.items():
                r = _timed(gen, text, v, 1.0, first)
                if not r["ok"]:
                    silent.append(f"{name}: \"{text}\"")
                    continue
                rows[name].append(("first", text, r))
        out("  Whole sentences:")
        for text in SENTENCES:
            for name, (gen, first) in engines.items():
                r = _timed(gen, text, v, 1.0, first)
                if not r["ok"]:
                    silent.append(f"{name}: \"{text[:30]}...\"")
                    continue
                rows[name].append(("sentence", text, r))
    finally:
        peak = vram.stop() if vram.available else None
    chat_after = ollama_loaded()
    m["silent"] = silent
    for name in engines:
        firsts = [r["first"] for kind, _t, r in rows[name] if kind == "first"]
        rtfs = [r["total"] / r["audio"] for kind, _t, r in rows[name]
                if kind == "sentence" and r["audio"] > 0]
        m[name + "_first"] = round(median(firsts), 3) if firsts else None
        m[name + "_rtf"] = round(median(rtfs), 3) if rtfs else None
        out(f"    {V.ENGINE_NAMES[name]:<11} first sound {_s(m[name + '_first'])} (middle "
            f"value), {m[name + '_rtf'] if m[name + '_rtf'] is not None else '?'} s per "
            f"second of speech")
    m["vram_before_mb"], m["vram_peak_mb"] = before, peak
    m["vram_rise_mb"] = rise_mb(before, peak)
    out(f"  Graphics memory rise while both spoke: "
        f"{'not measured (nvidia-smi was not found)' if m['vram_rise_mb'] is None else str(m['vram_rise_mb']) + ' MB'}")
    m["chat_before"], m["chat_after"] = chat_before, chat_after
    m["chat_pushed_off"] = False
    if chat_before:
        vram_b = {n: sv for n, _s2, sv in chat_before}
        for n, _s2, sv in chat_after or []:
            if n in vram_b and sv < vram_b[n]:
                m["chat_pushed_off"] = True
        out(f"  The chat model on the card: {', '.join(n for n, _a, _b in chat_before)}"
            + (" - it lost room" if m["chat_pushed_off"] else " - unchanged"))
    else:
        out("  No chat model was loaded in Ollama during this run (start a chat first to "
            "measure it beside the chat model)")

    # The speaking speed: does each follow it? Pocket TTS samples, so both of
    # its runs use one fixed seed - a length difference is then the speed's.
    choice = V._read_state().get("speed") or "normal"
    m["speed"] = {"choice": choice}
    probe = "slower" if choice == "slower" else "faster"
    factor = V.SPEED_VALUE[probe]
    for name, (gen, first) in engines.items():
        lens = []
        for text in SENTENCES:
            seed = 1234 if first else None
            a = _timed(gen, text, v, 1.0, first, seed)
            b = _timed(gen, text, v, factor, first, seed)
            if a["ok"] and b["ok"]:
                lens.append(b["audio"] / a["audio"])
        ratio = median(lens)
        need = VOICE_RULES["speed_change"]
        follows = ratio is not None and (ratio <= 1 - need if probe == "faster"
                                         else ratio >= 1 + need)
        m["speed"][name + "_ratio"] = round(ratio, 3) if ratio is not None else None
        m["speed"][name + "_follows"] = bool(follows)
    out(f"  Speaking speed (\"{probe}\" against normal, length ratio): ZipVoice "
        f"{m['speed']['zipvoice_ratio']}, Pocket TTS {m['speed']['pocket_ratio']}")

    # The blind pairs.
    m["ear"] = {"answered": 0}
    rng = rng or random.Random()
    lis = work / "listening"
    lis.mkdir(parents=True, exist_ok=True)
    key = {}
    sentence_rows = {n: [r for kind, _t, r in rows[n] if kind == "sentence"] for n in engines}
    pairs = min(len(sentence_rows["zipvoice"]), len(sentence_rows["pocket"]),
                VOICE_RULES["ear_pairs"])
    for i in range(pairs):
        a_is_pocket = rng.random() < 0.5
        a = sentence_rows["pocket" if a_is_pocket else "zipvoice"][i]
        b = sentence_rows["zipvoice" if a_is_pocket else "pocket"][i]
        write_wav(lis / f"pair-{i + 1}-A.wav", a["samples"], a["rate"])
        write_wav(lis / f"pair-{i + 1}-B.wav", b["samples"], b["rate"])
        key[str(i + 1)] = {"A": "pocket" if a_is_pocket else "zipvoice",
                           "B": "zipvoice" if a_is_pocket else "pocket"}
    (lis / "listening-sheet.txt").write_text(
        "The listening sheet\n\n"
        f"There are {pairs} pairs here, pair-1-A.wav and pair-1-B.wav and so on. In each pair "
        "the same sentence is said by the two voice engines, copying the same voice. Which one "
        "is which is hidden until you have answered.\n\n"
        "For each pair: play A, play B, and decide which sounds more like the recorded voice "
        "and is nicer to listen to. If you cannot tell, that is an answer too: \"same\".\n\n"
        "Answer in the window where the bake-off is running.\n", encoding="utf-8")
    m["ear_key"] = key
    if listen and pairs:
        out(f"  The listening pairs are in {lis}")
        if os.name == "nt":
            try:
                os.startfile(str(lis))  # type: ignore[attr-defined]
            except OSError:
                pass
        votes = {"pocket": 0, "zipvoice": 0, "same": 0}
        for i in range(1, pairs + 1):
            got = ask(f"    Pair {i}: which sounds better, A or B? (type A, B or S for the "
                      f"same, then Enter; Enter alone skips) ", "").upper()[:1]
            if got in ("A", "B"):
                votes[key[str(i)][got]] += 1
            elif got == "S":
                votes["same"] += 1
            else:
                continue
            m["ear"]["answered"] = m["ear"].get("answered", 0) + 1
        m["ear"].update(votes)
        out(f"    You picked Pocket TTS {votes['pocket']} times, ZipVoice {votes['zipvoice']} "
            f"times, and \"the same\" {votes['same']} times.")
    return m


# --------------------------------------------------------------------------
#   "Better voice" (the owner's group of 2026-09-28): three more parts, each
#   run only when asked for (--wake2, --vad, --voice-id), each measuring on
#   this PC before anything is chosen. Like the rest of this file, none of
#   them changes a setting; each ends in a verdict by rules fixed here first.
# --------------------------------------------------------------------------

#: The second "hey Jarvis" detector (microWakeWord), as a CONFIRMATION of
#: today's: is "both must agree" worth switching on?
TURN_ON = "turn on both detectors"
KEEP_ONE = "keep one detector"
WAKE2_RULES = {
    "min_owner_clips": 10,
    "min_room_minutes": 60.0,
    # "Both" may miss at most this share MORE of your own recordings than
    # today's detector alone (1 in 10).
    "max_extra_miss_share": 0.1,
    # A clear win in the room: at most half of today's false wake-ups
    # (today's must have woken at least once).
    "room_win_ratio": 0.5,
}
WAKE2_RULE_WORDS = (
    "At least 10 of your own \"hey Jarvis\" recordings, and at least 60 minutes of the room.",
    "Your recordings: with both detectors, at most 1 in 10 more of them are missed than with "
    "today's detector alone.",
    "The room: with both, at most half as many false wake-ups as today's alone (and today's "
    "must have woken by mistake at least once, or there is nothing to win).",
    "The 110 built-in-voice sentences: with both, no more wake-ups on the sentences without "
    "\"hey Jarvis\" than today's alone.",
)


def cluster_times(times, gap: float = 2.0) -> list:
    """Separate events from a list of moments (seconds): a moment more than
    `gap` after the last event starts a new one - the 2-second wait a
    listener makes after waking."""
    out: list = []
    for t in sorted(float(x) for x in times):
        if not out or t - out[-1] > gap:
            out.append(t)
    return out


def matched_events(first: list, second_times: list, window: float) -> list:
    """The events in `first` that have a moment of `second_times` within
    `window` seconds - "both heard it"."""
    return [t for t in first if any(abs(t - s) <= window for s in second_times)]


def wake2_verdict(m: dict, rules: dict = WAKE2_RULES) -> tuple:
    """(TURN_ON or KEEP_ONE, [reason, ...]) from wake2_measure()'s dict.
    Anything not met - or not measurable - keeps one detector."""
    if not m.get("second_ok"):
        return KEEP_ONE, [f"The second detector could not be measured: "
                          f"{m.get('second_why') or 'unknown'}."]
    why = []
    own = m.get("owner") or {}
    room = m.get("room") or {}
    kok = m.get("kokoro") or {}
    n = int(own.get("clips", 0))
    if n < rules["min_owner_clips"]:
        why.append(f"Only {n} of your own recordings (at least {rules['min_owner_clips']} "
                   f"are needed).")
    else:
        extra = int(own.get("first", 0)) - int(own.get("both", 0))
        allowed = math.floor(n * rules["max_extra_miss_share"])
        if extra > allowed:
            why.append(f"With both detectors, {extra} more of your {n} recordings were missed "
                       f"than with today's alone (at most {allowed} allowed).")
    minutes = float(room.get("minutes", 0.0))
    if minutes < rules["min_room_minutes"]:
        why.append(f"Only {minutes:.0f} minutes of the room (at least "
                   f"{rules['min_room_minutes']:.0f} are needed).")
    else:
        first_w, both_w = int(room.get("first_wakes", 0)), int(room.get("both_wakes", 0))
        if first_w < 1:
            why.append("Today's detector never woke by mistake in the room, so a second one "
                       "has nothing to win there.")
        elif both_w > first_w * rules["room_win_ratio"]:
            why.append(f"In the room, both together woke by mistake {both_w} times; today's "
                       f"alone {first_w} - not a clear win (at most half is needed).")
    if kok.get("other", 0):
        if int(kok.get("both_other", 0)) > int(kok.get("first_other", 0)):
            why.append(f"On the built-in voices' other sentences, both woke {kok.get('both_other')} "
                       f"times; today's alone {kok.get('first_other')}.")
    else:
        why.append("The built-in voices' sentences could not be made (Kokoro is not "
                   "installed), so that test did not run.")
    return (KEEP_ONE, why) if why else (TURN_ON, ["Every rule was met."])


def _stream_first(W, models, ver, samples, rate) -> list:
    """Moments (seconds) where today's detector would wake in a long
    recording - with the owner's own verifier deciding, as in hear(), when
    there is one."""
    scores, windows = W._clip_steps(models, samples, rate)
    scores = [float(s) for s in scores]
    for i in range(min(W.WARMUP_SCORES, len(scores))):
        scores[i] = 0.0
    thr = float(W.threshold())
    hits = []
    if ver is None:
        hits = [i for i, s in enumerate(scores) if s >= thr]
    else:
        gated = [i for i, s in enumerate(scores) if s >= W.VERIFIER_GATE]
        if gated:
            p = ver.probabilities(np.stack([windows[i] for i in gated]))
            hits = [i for i, v in zip(gated, p) if float(v) >= ver.threshold]
    step = W.CHUNK / float(W.SAMPLE_RATE)
    return [max(0.0, (i + 1) * step - W.LEAD_IN_SECONDS) for i in hits]


def wake2_measure(out: Out, *, record: Optional[int], room_minutes: Optional[int]) -> dict:
    import jarvis_microwake as M
    import jarvis_wakeword as W
    m: dict = {"second_ok": False}
    ok, why = wake_files_ok(W)
    if not ok:
        m["second_why"] = f"today's detector is not set up right: {why}"
        return m
    st = M.status()
    if not st["available"]:
        m["second_why"] = st["why"]
        return m
    cur = W._load()
    if cur is None:
        m["second_why"] = W.status()["why"] or "today's detector did not load"
        return m
    ver = W.load_verifier("")
    m.update(second_ok=True, second_version=st["version"], agree_seconds=M.AGREE_SECONDS,
             verifier=ver is not None)
    win = M.AGREE_SECONDS

    def clip(x, rate) -> dict:
        a = W.spot(x, rate)
        b = M.spot(x, rate)
        return {"first": bool(a.heard), "second": bool(b.ran and b.heard),
                "both": bool(a.heard and M.agree(a.at, b, win))}

    out("  Your own \"hey Jarvis\" recordings")
    clips = []
    if record:
        out(f"    Recording up to {record} (3.5 seconds each); none is kept")
        clips += record_owner_clips(out, record)
    own = {"clips": 0, "first": 0, "second": 0, "both": 0, "from_folder": 0, "unreadable": 0}
    for p in sorted(owner_clip_dir().glob("*.wav")) if owner_clip_dir().is_dir() else []:
        try:
            clips.append(read_wav(p))
            own["from_folder"] += 1
        except ValueError:
            own["unreadable"] += 1
    for x, rate in clips:
        r = clip(x, rate)
        own["clips"] += 1
        for k in ("first", "second", "both"):
            own[k] += int(r[k])
    m["owner"] = own
    out(f"    {own['clips']} recordings heard: today's alone {own['first']}, the second alone "
        f"{own['second']}, both together {own['both']}")

    out("  The room")
    room = {"minutes": 0.0, "first_wakes": 0, "second_wakes": 0, "both_wakes": 0}
    if room_minutes:
        out(f"    Listening for {room_minutes} minutes. Do not say \"hey Jarvis\"; talking "
            f"and the television are what it should hear.")
        tmp = Path(tempfile.mkdtemp(prefix="jarvis-room2-"))
        try:
            for k in range(room_minutes):
                p = tmp / "minute.wav"
                try:
                    record_wav(p, 60.0)
                    x, rate = read_wav(p)
                except (OSError, ValueError) as exc:
                    out(f"      could not record the room: {exc}")
                    break
                finally:
                    try:
                        p.unlink()
                    except OSError:
                        pass
                first = cluster_times(_stream_first(W, cur, ver, x, rate))
                b = M.spot(x, rate)
                second = cluster_times(b.times if b.ran else [])
                room["first_wakes"] += len(first)
                room["second_wakes"] += len(second)
                room["both_wakes"] += len(matched_events(first, b.times if b.ran else [], win))
                room["minutes"] += len(x) / float(rate) / 60.0
                if k % 10 == 9:
                    out(f"      {k + 1} minutes: today's woke {room['first_wakes']} times, the "
                        f"second {room['second_wakes']}, both {room['both_wakes']}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        room["minutes"] = round(room["minutes"], 1)
        out(f"    {room['minutes']:.0f} minutes: false wake-ups - today's alone "
            f"{room['first_wakes']}, the second alone {room['second_wakes']}, both "
            f"{room['both_wakes']}")
    else:
        out("    skipped")
    m["room"] = room

    out("  The built-in voices (110 sentences, nothing kept)")
    kok = {"voices": 0, "hey": 0, "other": 0}
    for k in ("first", "second", "both"):
        kok[k + "_hey"] = kok[k + "_other"] = 0
    for text, x, rate in kokoro_clips():
        r = clip(x, rate)
        kind = "hey" if text in KOKORO_HEY else "other"
        kok[kind] += 1
        for k in ("first", "second", "both"):
            kok[f"{k}_{kind}"] += int(r[k])
    kok["voices"] = (kok["hey"] + kok["other"]) // max(1, len(KOKORO_HEY + KOKORO_OTHER))
    m["kokoro"] = kok
    if kok["hey"]:
        out(f"    \"hey Jarvis\" heard (of {kok['hey']}): today's {kok['first_hey']}, the second "
            f"{kok['second_hey']}, both {kok['both_hey']}; woke on the others (of "
            f"{kok['other']}): today's {kok['first_other']}, the second {kok['second_other']}, "
            f"both {kok['both_other']}")
    else:
        out("    skipped: the built-in voice (Kokoro) is not installed")
    return m


def kokoro_clips():
    """(text, samples, rate) for the 110-sentence test in every built-in
    Kokoro voice, made on the fly; nothing kept. Nothing when Kokoro is not
    installed."""
    try:
        import jarvis_speech as S
        eng = S._tts_engine()
    except Exception:
        eng = None
    if eng is None:
        return
    try:
        speakers = max(1, int(getattr(eng, "num_speakers", 1) or 1))
    except Exception:
        speakers = 1
    for sid in range(speakers):
        for text in KOKORO_HEY + KOKORO_OTHER:
            try:
                a = eng.generate(text, sid=sid, speed=1.0)
            except Exception:
                continue
            x = np.asarray(a.samples, dtype=np.float32)
            if not len(x):
                continue
            yield text, x / (float(np.abs(x).max()) or 1.0) * 0.6, int(a.sample_rate)


# ---- The speech detector: Silero VAD v4 (today's) against v6 -------------

USE_V6 = "use v6"
KEEP_V4 = "keep v4"
VAD_RULES = {
    "min_owner_clips": 10,
    # A clip's speech counts as cut when the detector's span (with Jarvis's
    # own 0.3 s either side) misses more than this much of it.
    "cut_seconds": 0.15,
}
#: The built-in sentences are also tried with hiss this far below their own
#: loudness (dB) - easy, hard and very hard - and counted together.
NOISE_SNRS = (5.0, 0.0, -5.0)
VAD_RULE_WORDS = (
    "The new file is installed and is exactly the pinned one.",
    "At least 10 of your own recordings.",
    "Speech found: v6 finds speech in at least as many clips as v4 - your recordings, the "
    "built-in voices, and the built-in voices with hiss added (three levels, counted "
    "together).",
    "Noise alone (a fan, a hum, clicks, hiss, silence): v6 says \"speech\" on no more of "
    "them than v4.",
    "Speech kept whole: v6 cuts into the built-in voices' sentences no more often than v4.",
    "Your voice check (when your voice is trained): with v6 cutting your recordings, at "
    "least as many of them pass as with v4.",
)


def noise_clips(seconds: float = 3.0, seed: int = 7) -> list:
    """(name, samples at 16 kHz) - sounds with no speech in them, made the
    same way every run: hiss at three levels, a fan (low rumble), mains hum,
    knocks, and silence."""
    rng = np.random.RandomState(seed)
    n = int(16000 * seconds)
    t = np.arange(n) / 16000.0
    out = []
    for db in (-50, -35, -20):
        out.append((f"hiss {db} dB", (rng.randn(n) * 10 ** (db / 20.0)).astype(np.float32)))
    w = rng.randn(n)
    fan = np.convolve(w, np.ones(64) / 64.0, mode="same")
    out.append(("fan", (fan / (np.abs(fan).max() or 1.0) * 0.1).astype(np.float32)))
    hum = sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((50, 100, 150, 200), 1))
    out.append(("hum", (hum * 0.05).astype(np.float32)))
    knocks = np.zeros(n, dtype=np.float32)
    for at in (0.4, 1.3, 2.2):
        i = int(at * 16000)
        burst = rng.randn(400) * np.exp(-np.arange(400) / 60.0)
        knocks[i:i + 400] += (burst * 0.5).astype(np.float32)
    out.append(("knocks", knocks))
    out.append(("silence", np.zeros(n, dtype=np.float32)))
    return out


def with_noise(x, snr_db: float = 5.0, seed: int = 11):
    """`x` with hiss added at `snr_db` below its own loudness."""
    rng = np.random.RandomState(seed)
    p = float(np.mean(np.square(x))) or 1e-9
    noise = rng.randn(len(x)) * math.sqrt(p / (10 ** (snr_db / 10.0)))
    return np.clip(x + noise, -1.0, 1.0).astype(np.float32)


def speech_region(x, rate: int) -> tuple:
    """(start, end) seconds of the loud part of a clean synthetic sentence:
    20 ms frames above 2% of the loudest."""
    f = max(1, int(rate * 0.02))
    n = len(x) // f
    if n < 1:
        return 0.0, 0.0
    e = np.abs(np.asarray(x[: n * f], dtype=np.float32)).reshape(n, f).max(axis=1)
    on = np.where(e > 0.02 * (e.max() or 1.0))[0]
    if not len(on):
        return 0.0, 0.0
    return on[0] * f / float(rate), (on[-1] + 1) * f / float(rate)


def vad_verdict(m: dict, rules: dict = VAD_RULES) -> tuple:
    """(USE_V6 or KEEP_V4, [reason, ...]) from vad_measure()'s dict."""
    if not m.get("v6_ok"):
        return KEEP_V4, [f"v6 could not be measured: {m.get('v6_why') or 'unknown'}."]
    why = []
    own = m.get("owner") or {}
    n = int(own.get("clips", 0))
    if n < rules["min_owner_clips"]:
        why.append(f"Only {n} of your own recordings (at least {rules['min_owner_clips']} are "
                   f"needed).")
    for key, words in (("owner", "your recordings"), ("kokoro", "the built-in voices"),
                       ("noisy", "the built-in voices with noise")):
        d = m.get(key) or {}
        if int(d.get("v6_found", 0)) < int(d.get("v4_found", 0)):
            why.append(f"On {words}, v6 found speech in {d.get('v6_found')} of "
                       f"{d.get('clips')}; v4 in {d.get('v4_found')}.")
    noise = m.get("noise") or {}
    if int(noise.get("v6_found", 0)) > int(noise.get("v4_found", 0)):
        why.append(f"On noise alone, v6 said \"speech\" {noise.get('v6_found')} times; v4 "
                   f"{noise.get('v4_found')}.")
    kok = m.get("kokoro") or {}
    if int(kok.get("v6_cut", 0)) > int(kok.get("v4_cut", 0)):
        why.append(f"v6 cut into {kok.get('v6_cut')} of the built-in sentences; v4 into "
                   f"{kok.get('v4_cut')}.")
    if not kok.get("clips"):
        why.append("The built-in voices' sentences could not be made (Kokoro is not "
                   "installed), so that test did not run.")
    if own.get("checked"):
        if int(own.get("v6_passed", 0)) < int(own.get("v4_passed", 0)):
            why.append(f"Your voice check let {own.get('v6_passed')} of your recordings "
                       f"through with v6; {own.get('v4_passed')} with v4.")
    return (KEEP_V4, why) if why else (USE_V6, ["Every rule was met."])


def vad_measure(out: Out, *, record: Optional[int]) -> dict:
    import jarvis_speech as S
    m: dict = {"v6_ok": False}
    d = S._models_dir() / "vad"
    paths = {v: d / S.VAD_FILES[v]["file"] for v in ("v4", "v6")}
    for v, p in paths.items():
        if not p.is_file():
            m["v6_why"] = f"the {v} file is not installed (looked for {p})"
            return m
        if S._file_sha256(p) != S.VAD_FILES[v]["sha256"]:
            m["v6_why"] = f"{p.name} is not the expected file (its SHA-256 is different)"
            return m
    cfgs = {v: S.vad_config_for(str(p)) for v, p in paths.items()}
    if any(c is None for c in cfgs.values()):
        m["v6_why"] = "sherpa-onnx could not load one of the two files"
        return m
    m["v6_ok"] = True

    def span(x, rate, v):
        got = S._speech_span(x, rate, cfg=cfgs[v])
        return None if got in (None, "skip") else got

    try:
        import jarvis_voice as JV
        prof, _label = JV.find_profile("")
        emb = JV.EcapaEmbedder() if prof is not None else None
    except Exception:
        prof, emb = None, None

    out("  Your own recordings")
    clips = []
    if record:
        out(f"    Recording up to {record} (3.5 seconds each); none is kept")
        clips += record_owner_clips(out, record)
    for p in sorted(owner_clip_dir().glob("*.wav")) if owner_clip_dir().is_dir() else []:
        try:
            clips.append(read_wav(p))
        except ValueError:
            pass
    own = {"clips": len(clips), "v4_found": 0, "v6_found": 0, "checked": False,
           "v4_passed": 0, "v6_passed": 0}
    for x, rate in clips:
        for v in ("v4", "v6"):
            sp = span(x, rate, v)
            own[v + "_found"] += int(sp is not None)
            if sp is not None and prof is not None and emb is not None:
                own["checked"] = True
                try:
                    verdict = JV.verify(x[sp[0]:sp[1]], emb, sample_rate=rate)
                    own[v + "_passed"] += int(bool(verdict.is_owner))
                except Exception:
                    pass
    m["owner"] = own
    out(f"    {own['clips']} recordings: speech found by v4 in {own['v4_found']}, by v6 in "
        f"{own['v6_found']}" + (f"; your voice check passed {own['v4_passed']} with v4 and "
                                f"{own['v6_passed']} with v6" if own["checked"] else
                                " (your voice is not trained, so the voice check was not run)"))

    out("  The built-in voices, clean and with noise (nothing kept)")
    kok = {"clips": 0, "v4_found": 0, "v6_found": 0, "v4_cut": 0, "v6_cut": 0}
    noisy = {"clips": 0, "v4_found": 0, "v6_found": 0}
    cut = VAD_RULES["cut_seconds"]
    for k, (_text, x, rate) in enumerate(kokoro_clips()):
        pad = np.zeros(int(rate * 0.8), dtype=np.float32)
        x = np.concatenate([pad, x, pad])
        s0, s1 = speech_region(x, rate)
        kok["clips"] += 1
        for v in ("v4", "v6"):
            sp = span(x, rate, v)
            kok[v + "_found"] += int(sp is not None)
            if sp is None or sp[0] / rate > s0 + cut or sp[1] / rate < s1 - cut:
                kok[v + "_cut"] += 1
        for snr in NOISE_SNRS:
            xn = with_noise(x, snr, seed=100 + k)
            noisy["clips"] += 1
            for v in ("v4", "v6"):
                noisy[v + "_found"] += int(span(xn, rate, v) is not None)
    m["kokoro"], m["noisy"] = kok, noisy
    if kok["clips"]:
        out(f"    {kok['clips']} sentences: speech found by v4 in {kok['v4_found']}, v6 in "
            f"{kok['v6_found']}; cut into by v4 {kok['v4_cut']}, v6 {kok['v6_cut']}. With "
            f"noise: v4 {noisy['v4_found']}, v6 {noisy['v6_found']}")
    else:
        out("    skipped: the built-in voice (Kokoro) is not installed")

    out("  Noise alone (hiss, a fan, hum, knocks, silence)")
    noise = {"clips": 0, "v4_found": 0, "v6_found": 0, "v4_names": [], "v6_names": []}
    for name, x in noise_clips():
        noise["clips"] += 1
        for v in ("v4", "v6"):
            if span(x, 16000, v) is not None:
                noise[v + "_found"] += 1
                noise[v + "_names"].append(name)
    m["noise"] = noise
    out(f"    {noise['clips']} clips said to hold speech: v4 {noise['v4_found']}, v6 "
        f"{noise['v6_found']}")
    return m


# ---- The stronger voice-ID model: TitaNet against ResNet221 --------------

#: The owner's sentences for this part (the same kind "Train my voice" asks
#: for: a few seconds each, said normally).
VOICE_ID_LINES = (
    "What's on my calendar for tomorrow morning?",
    "Remind me to water the plants when I get home.",
    "Turn the living room lights down a little, please.",
    "How long will it take to drive to the station?",
    "Add eggs, bread and coffee to the shopping list.",
    "Read me the last message from my brother.",
    "Set a timer for twenty five minutes.",
    "What did I say I wanted to do this weekend?",
    "Play something calm while I cook dinner.",
    "Is it going to rain before the evening?",
)
VOICE_ID_RULES = {
    # Enough of the owner to split into a print and a test.
    "min_owner_clips": 20,
    # Enough real other people (WAVs the owner adds): Kokoro's synthetic
    # voices are reported but never enough on their own - measured, they
    # behave unlike real people.
    "min_other_clips": 50,
}
VOICE_ID_RULE_WORDS = (
    "At least 20 of your own sentences (half make a voice print in memory, half test it).",
    "At least 50 sentences from other real people, as WAV files in the other-voices folder "
    "(the built-in voices are shown too, but they are not real people).",
    "Then the numbers below are enough to give the newer model its own bars. Nothing is "
    "switched: you choose the model in Settings, Voice, and only after its bars are written.",
)
ROWS_READY = "enough to write its bars"
ROWS_NOT_READY = "not enough yet"


def other_voice_dir() -> Path:
    return results_root() / "other-voices"


def my_voice_dir() -> Path:
    return results_root() / "my-voice"


def sweep(owner: list, others: list, bars=None) -> list:
    """[(bar, share of the owner's clips refused, share of others let in)]
    for each raw bar - the table a MODEL_BARS row is chosen from."""
    bars = bars if bars is not None else [round(0.20 + 0.05 * i, 2) for i in range(16)]
    rows = []
    for b in bars:
        refused = sum(1 for s in owner if s < b) / len(owner) if owner else None
        let_in = sum(1 for s in others if s >= b) / len(others) if others else None
        rows.append((b, refused, let_in))
    return rows


def matching_bar(rows: list, let_in_max: float) -> Optional[tuple]:
    """The LOWEST bar at which others are let in no more often than
    `let_in_max` - the bar that keeps people out as well as the reference -
    as (bar, owner refused, others let in), or None."""
    for b, refused, let_in in rows:
        if let_in is not None and let_in <= let_in_max:
            return b, refused, let_in
    return None


def voiceid_verdict(m: dict, rules: dict = VOICE_ID_RULES) -> tuple:
    if not m.get("resnet_ok"):
        return ROWS_NOT_READY, [f"The newer model could not be measured: "
                                f"{m.get('resnet_why') or 'unknown'}."]
    why = []
    if int(m.get("owner_clips", 0)) < rules["min_owner_clips"]:
        why.append(f"Only {m.get('owner_clips', 0)} of your own sentences (at least "
                   f"{rules['min_owner_clips']} are needed).")
    if int(m.get("other_clips", 0)) < rules["min_other_clips"]:
        why.append(f"Only {m.get('other_clips', 0)} sentences from other real people (at least "
                   f"{rules['min_other_clips']} are needed).")
    return (ROWS_NOT_READY, why) if why else (ROWS_READY, ["Every rule was met."])


def voiceid_measure(out: Out, *, record: Optional[int]) -> dict:
    import jarvis_voice as JV
    m: dict = {"resnet_ok": False}
    rn = JV.resnet_state()
    if not rn["ok"]:
        m["resnet_why"] = rn["why"]
        return m
    models = {}
    for key, path in (("small", JV.speaker_model_path()), ("titanet", JV.titanet_model_path()),
                      ("resnet221", JV.resnet_model_path())):
        if not Path(path).is_file():
            continue
        try:
            models[key] = JV.StrongEmbedder(Path(path))
        except Exception as exc:
            out(f"    {key}: would not load ({type(exc).__name__})")
    if "resnet221" not in models:
        m["resnet_why"] = "the newer model's file would not load"
        return m
    m["resnet_ok"] = True
    m["models"] = sorted(models)

    out("  Your own sentences")
    mine = []
    if record and can_record():
        out(f"    Recording up to {record} (4 seconds each); none is kept")
        tmp = Path(tempfile.mkdtemp(prefix="jarvis-me-"))
        try:
            for i in range(record):
                line = VOICE_ID_LINES[i % len(VOICE_ID_LINES)]
                if ask(f"  {i + 1}/{record}: press Enter, then say  \"{line}\"  (s and Enter "
                       f"to stop) ", "").lower() == "s":
                    break
                p = tmp / "clip.wav"
                try:
                    record_wav(p, 4.0)
                    mine.append(read_wav(p))
                except (OSError, ValueError) as exc:
                    out(f"      could not record: {exc}")
                    break
                finally:
                    try:
                        p.unlink()
                    except OSError:
                        pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    for p in sorted(my_voice_dir().glob("*.wav")) if my_voice_dir().is_dir() else []:
        try:
            mine.append(read_wav(p))
        except ValueError:
            pass
    others = []
    for p in sorted(other_voice_dir().rglob("*.wav")) if other_voice_dir().is_dir() else []:
        try:
            others.append(read_wav(p))
        except ValueError:
            pass
    synthetic = [(x, r) for _t, x, r in kokoro_clips()]
    try:
        import jarvis_wakeword as W
        mine, others, synthetic = ([(W.to_16k(x, r), 16000) for x, r in group]
                                   for group in (mine, others, synthetic))
    except Exception:
        pass
    m.update(owner_clips=len(mine), other_clips=len(others), synthetic_clips=len(synthetic))
    out(f"    {len(mine)} of yours, {len(others)} from other people, {len(synthetic)} from the "
        f"built-in voices")
    half = len(mine) // 2
    train, test = mine[:half], mine[half:]
    m["results"] = {}
    for key, emb in models.items():
        t0 = time.perf_counter()
        vec = lambda xr: JV._as_vector(JV._embed(emb, xr[0], xr[1]))  # noqa: E731
        tv = [v for v in (vec(c) for c in train) if v]
        cost = (time.perf_counter() - t0) / max(1, len(train))
        if not tv:
            m["results"][key] = {"why": "no usable voice print from your sentences"}
            continue
        centroid = JV._mean_unit(tv)

        def score(xr, _vec=vec, _c=centroid) -> float:
            v = _vec(xr)
            return JV.cosine(v, _c) if v else 0.0
        own_s = [score(c) for c in test]
        oth_s = [score(c) for c in others]
        syn_s = [score(c) for c in synthetic]
        rows = sweep(own_s, oth_s)
        m["results"][key] = {"ms_per_clip": round(cost * 1000), "owner": own_s,
                             "others": oth_s, "synthetic": syn_s, "sweep": rows,
                             "measured_bars": JV.bars_for(emb.name).get("known", False),
                             "name": emb.name}
        out(f"  {key}: about {round(cost * 1000)} ms a sentence")
        out("    bar   you refused   others let in   built-in voices let in")
        syn_rows = sweep(own_s, syn_s)
        for (b, ref, let), (_b2, _r2, syn) in zip(rows, syn_rows):
            out(f"    {b:.2f}  {_pct(ref):>11}   {_pct(let):>13}   {_pct(syn):>10}")
    ti, rn_r = m["results"].get("titanet"), m["results"].get("resnet221")
    if ti and rn_r and "sweep" in ti and "sweep" in rn_r:
        vs_bar = JV.bar_for(ti["name"], "very_strict")[0]
        ref = next((r for r in ti["sweep"] if abs(r[0] - vs_bar) < 1e-6), None)
        if ref is not None and ref[2] is not None:
            got = matching_bar(rn_r["sweep"], ref[2])
            m["suggested"] = {"titanet_very_strict": ref, "resnet221_same_keep_out": got}
            if got is not None:
                out(f"  To keep other people out as well as today's very strict does "
                    f"({_pct(ref[2])} let in, you refused {_pct(ref[1])}), the newer model needs "
                    f"a bar of {got[0]:.2f} - and then refuses you {_pct(got[1])}.")
    return m


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


# --------------------------------------------------------------------------
#   The run
# --------------------------------------------------------------------------


def _clean_for_json(m):
    if isinstance(m, dict):
        return {k: _clean_for_json(v) for k, v in m.items() if k != "samples"}
    if isinstance(m, (list, tuple)):
        return [_clean_for_json(v) for v in m]
    if np is not None and isinstance(m, np.generic):
        return m.item()
    return m


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if np is None:
        print("numpy is not installed in this Python (py -3 -m pip install numpy).")
        return 1
    # "Better voice" (2026-09-28): --wake2, --vad and --voice-id run only
    # their own parts; the original two run as before when none is given.
    do_wake2, do_vad, do_voice_id = ("--wake2" in argv, "--vad" in argv,
                                     "--voice-id" in argv)
    newer = do_wake2 or do_vad or do_voice_id
    do_wake = ("--voice" not in argv or "--wake" in argv) and not (newer and "--wake" not in argv)
    do_voice = ("--wake" not in argv or "--voice" in argv) and not (newer and "--voice" not in argv)
    out = Out()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    work = results_root() / stamp
    work.mkdir(parents=True, exist_ok=True)
    out("Jarvis's voice upgrades: the bake-off")
    out("Nothing here changes Jarvis. It measures, then says \"replace\" or \"keep what we "
        "have\" by rules written down before it ran.")
    out(f"Results go in {work}")
    doc: dict = {"when": stamp, "wake_rules": WAKE_RULES, "voice_rules": VOICE_RULES}

    if do_wake:
        out("")
        out("PART 1 - \"Hey Jarvis\": today's detector against the new one")
        for r in WAKE_RULE_WORDS:
            out(f"  rule: {r}")
        record = None
        room = None
        import jarvis_wakeword as W
        if W.candidate_status()["ok"]:
            if can_record():
                n = ask("  Record some of your own \"hey Jarvis\" now? How many? (the rules need "
                        "10; none is kept; Enter for 0): ", "0")
                record = int(n) if n.isdigit() else 0
                mins = ask("  Listen to the room for how many minutes? (60 is what the rules "
                           "need; Enter for 0): ", "0")
                room = int(mins) if mins.isdigit() else 0
            else:
                out(f"  (This system cannot record; put WAV files of you saying \"hey Jarvis\" "
                    f"in {owner_clip_dir()} instead.)")
        try:
            m = wake_measure(out, record=record, room_minutes=room)
        except Exception as exc:
            m = {"candidate_ok": False,
                 "candidate_why": f"the bake-off itself failed ({type(exc).__name__}: {exc})"}
        verdict, why = wake_verdict(m)
        doc["wake"] = {"measured": _clean_for_json(m), "verdict": verdict, "why": why}
        out("")
        out(f"  VERDICT (\"hey Jarvis\"): {verdict.upper()}")
        for w in why:
            out(f"    - {w}")

    if do_voice:
        out("")
        out("PART 2 - The voice: ZipVoice (today) against Pocket TTS")
        for r in VOICE_RULE_WORDS:
            out(f"  rule: {r}")
        try:
            m = voice_measure(out, work, listen=True)
        except Exception as exc:
            m = {"pocket_ok": False,
                 "pocket_why": f"the bake-off itself failed ({type(exc).__name__}: {exc})"}
        verdict, why = voice_verdict(m)
        doc["voice"] = {"measured": _clean_for_json(m), "verdict": verdict, "why": why}
        out("")
        out(f"  VERDICT (the voice): {verdict.upper()}")
        for w in why:
            out(f"    - {w}")

    if do_wake2:
        out("")
        out("PART 3 - \"Hey Jarvis\": one detector, or two that must agree")
        for r in WAKE2_RULE_WORDS:
            out(f"  rule: {r}")
        record = room = None
        if can_record():
            n = ask("  Record some of your own \"hey Jarvis\" now? How many? (the rules need "
                    "10; none is kept; Enter for 0): ", "0")
            record = int(n) if n.isdigit() else 0
            mins = ask("  Listen to the room for how many minutes? (60 is what the rules "
                       "need; Enter for 0): ", "0")
            room = int(mins) if mins.isdigit() else 0
        else:
            out(f"  (This system cannot record; put WAV files of you saying \"hey Jarvis\" "
                f"in {owner_clip_dir()} instead.)")
        try:
            m = wake2_measure(out, record=record, room_minutes=room)
        except Exception as exc:
            m = {"second_ok": False,
                 "second_why": f"the bake-off itself failed ({type(exc).__name__}: {exc})"}
        verdict, why = wake2_verdict(m)
        doc["wake2"] = {"measured": _clean_for_json(m), "verdict": verdict, "why": why,
                        "rules": WAKE2_RULES}
        out("")
        out(f"  VERDICT (two detectors): {verdict.upper()}")
        for w in why:
            out(f"    - {w}")
        if verdict == TURN_ON:
            out("    You can turn it on in Settings, Voice, \"Second 'hey Jarvis' check\" - "
                "on the phone or the PC. That is at once; going back asks with a card.")

    if do_vad:
        out("")
        out("PART 4 - The speech detector: Silero VAD v4 (today's) against v6")
        for r in VAD_RULE_WORDS:
            out(f"  rule: {r}")
        record = None
        if can_record():
            n = ask("  Record some of your own sentences now? How many? (the rules need 10; "
                    "none is kept; Enter for 0): ", "0")
            record = int(n) if n.isdigit() else 0
        try:
            m = vad_measure(out, record=record)
        except Exception as exc:
            m = {"v6_ok": False,
                 "v6_why": f"the bake-off itself failed ({type(exc).__name__}: {exc})"}
        verdict, why = vad_verdict(m)
        doc["vad"] = {"measured": _clean_for_json(m), "verdict": verdict, "why": why,
                      "rules": VAD_RULES}
        out("")
        out(f"  VERDICT (speech detector): {verdict.upper()}")
        for w in why:
            out(f"    - {w}")
        if verdict == USE_V6:
            out("    To use it: the line \"Use the newer speech detector\" in backend/README.md, "
                "\"Better voice\", then restart Jarvis.")

    if do_voice_id:
        out("")
        out("PART 5 - The voice check: the stronger model (TitaNet) against the newer one "
            "(ResNet221)")
        for r in VOICE_ID_RULE_WORDS:
            out(f"  rule: {r}")
        out(f"  Other people's sentences: WAV files in {other_voice_dir()} (sub-folders are "
            f"fine). Yours can also go in {my_voice_dir()}.")
        record = None
        if can_record():
            n = ask("  Record some of your own sentences now? How many? (the rules need 20; "
                    "none is kept; Enter for 0): ", "0")
            record = int(n) if n.isdigit() else 0
        try:
            m = voiceid_measure(out, record=record)
        except Exception as exc:
            m = {"resnet_ok": False,
                 "resnet_why": f"the bake-off itself failed ({type(exc).__name__}: {exc})"}
        verdict, why = voiceid_verdict(m)
        doc["voice_id"] = {"measured": _clean_for_json(m), "verdict": verdict, "why": why,
                           "rules": VOICE_ID_RULES}
        out("")
        out(f"  VERDICT (newer voice-ID model's bars): {verdict.upper()}")
        for w in why:
            out(f"    - {w}")

    out("")
    out("Please send back results.txt - it is how the decision gets made. Nothing was "
        "switched on.")
    out(f"Results: {work / 'results.txt'} and {work / 'results.json'}")
    (work / "results.txt").write_text("\n".join(out.lines) + "\n", encoding="utf-8")
    (work / "results.json").write_text(json.dumps(doc, indent=1, default=str) + "\n",
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
