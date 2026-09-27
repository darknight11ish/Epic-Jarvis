"""Original score for the Jarvis v6 launch video, "Your AI": landscape (25.6 s) and upright (12.8 s).

Run from anywhere:   python3 videos/v6/composition/tools/score.py

THE STYLE - "clean machine"
  Bright, clean and a little futuristic, but not a movie trailer. 150 BPM played half-time, so it
  feels like 75 and never gets frantic, while a 16th note is exactly 0.1 s = 3 video frames: every
  tick lands on a frame. The key is F-sharp Lydian (a major scale with a raised 4th, the classic
  "sci-fi wonder" colour), and the chords are stacked fourths instead of ordinary triads.
  Every sound is synthesised here; no audio file is ever read:
    - bass: two-operator FM (one sine bending another) with a snapping "dwip" attack, over a plain
      sine sub (46-78 Hz) that stays in mono;
    - pad: a wavetable that slowly morphs from a pure sine to a vowel-like "formant" tone;
    - drums: a short tight kick (55 Hz, ~0.13 s), a snare made of a noise snap plus a 1.8 kHz
      ping, and metallic hats made by multiplying sines together (ring modulation), kept to
      6-13 kHz so they sparkle without fizzing;
    - a glassy FM arpeggio in the loudest two sections;
    - interface sounds, which own the 2-6 kHz band (the music dips 3 dB under each one):
      a tool "tick" (3 ms click + a 45 ms FM blip, one scale step higher per step), a soft glass
      "ping", the approval chime (two glassy notes rising a fifth, F#5 then C#6), a grainy
      "thinking" cloud that stops dead when the answer appears, and the reactor's listening hum,
      a vowel-coloured drone on F#2 that slides from "ah" to "oo" (it never moves like speech);
    - transition effects, each used 1-3 times, only on cuts: a reversed-reverb swell into an
      iris cut, a buffer stutter (1/32-note repeats) into a cut, and one tape-stop dive at "Stop".
  FM sounds and the ring-modulated hats are rendered at twice the sample rate and filtered back
  down, so their high harmonics cannot fold back as harsh noise.

THE STRUCTURE - each section starts on a hit from the timing table
  ignite   (ignite)      a full-strength hit on the very first sample: kick, FM "dwip", a glass
                         chord (F#maj7#11 in fourths), a particle sparkle; then it settles
  look     (b2)          reversed swell into the iris cut; quiet groove (kick, hats), the pad,
                         a tick on step1..step4 each one note higher, the thinking cloud from b2
                         that stops dead on `answer`
  sources  (b3)          bass joins, the snare on beat 3; a soft glass ping on `warn`;
                         a buffer stutter into the next cut
  listen   (b4)          one bar with no drums: the reactor's hum ("ah" -> "oo"), pad, sub;
                         the drums come back for the second bar
  speak    (b5)          the full groove; at `stop` a full-strength hit that dives like a tape
                         machine stopping (0.15 s), then true digital silence until `silenceEnd`
  resume   (silenceEnd)  the pad comes back alone
  swap     (b6)          reversed swell into the iris cut, the groove again; a tick on `tapUse`;
                         a buffer stutter into the cut at b7
  approve  (b7)          the fullest part (arpeggio in 16ths); the approval chime on `approve`,
                         on the home chord, with the music ducked 3 dB around it
  end      (end)         an open fifth on F# at full strength, a soft glass accent on `name`, a
                         natural decay to real silence (the last 0.3 s is digital zero)
  Chords (stacked fourths, one per bar, changing only on bar lines and cuts):
    ignite F#maj7#11 | look F#6/9, G#6/9 | sources D#m11, C#sus | listen F#maj7#11, D#m11 |
    speak C#sus | resume G#6/9 | swap F#6/9, G#6/9 | approve D#m11, F#6/9 | end F#5 (open fifth)
  The arc builds from `look` to `approve`; only ignite, stop and end are full strength.
  The upright table has a subset of the same hits (ignite, b6, b7, b5, end, ...); the same rules
  build its score, so it follows its own order (swap -> approve -> speak/stop -> end).

WHAT IT READS AND WRITES
  Reads   assets/timing.json and assets/timing-vertical.json. Every time comes from these
          tables; nothing is hard-coded to a clock.
  Writes  assets/music/score.mp3            assets/audio-data.js
          assets/music/score-vertical.mp3   assets/audio-data-vertical.js
  The mp3s are 48 kHz stereo, 320 kbit/s, mastered to -14.0 LUFS with true peak <= -1 dBTP
  (limiter ceiling -1.5 dBTP; one linear gain, no dynamic loudness processing).
  audio-data*.js set  window.AUDIO_DATA = {fps, low, rms, hi, think, events}:
    low    0..1 per frame, everything below 160 Hz (kick, bass), 150 ms release - for the glow;
    rms    0..1 per frame, overall level;
    hi     0..1 per frame, the interface sounds only (2-6 kHz band), held for 0.1 s (so the two
           chime notes read as one flash), then a fast 120 ms release;
    think  0..1 per frame, the level of the thinking cloud (no release: it drops to 0 on `answer`);
    events [{t, kind}] - exact times of hits, ticks, ping, stop, chime, ... for flashes.
  All envelopes are 0 during the silences. The hats never drive any of them.

CHECKS IT PRINTS (on the decoded mp3, i.e. the file that ships)
  loudness, true peak, LRA and the limiter's largest gain reduction (it stops with an error if
  that is over 3 dB); the energy share per band; stereo width (Side/Mid) and the loss when
  folded to mono; that the silences are digital zero; and a timing self-check that names any
  cue whose sound starts more than 5 ms away from the table.
Deterministic: numpy + ffmpeg only; one seed per render and a sub-seed per instrument from
zlib.crc32(name) (never Python's hash(), which changes on every run).
"""
import json
import os
import subprocess
import sys
import zlib

import numpy as np

SR = 48000
FPS = 30
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")

LYDIAN = {6, 8, 10, 0, 1, 3, 5}          # F# G# A# B# C# D# E#
TAPE_STOP = 0.15                         # the dive at `stop`, seconds
TAIL_ZERO = 0.3                          # the last 0.3 s is digital zero


# ============================================================ small helpers
def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def dbg(d):
    return 10 ** (d / 20)


def rel_env(t, gate, rel):
    """1 until `gate`, then a raised-cosine fall to 0 over `rel` seconds (no click)."""
    u = np.clip((t - gate) / max(rel, 1e-4), 0, 1)
    return 0.5 + 0.5 * np.cos(np.pi * u)


def curve(points):
    ts, vs = zip(*sorted(points))
    return lambda t: np.interp(t, ts, vs)


def band(x, lo=None, hi=None, order=4):
    """Zero-phase Butterworth-shaped band filter (FFT). Works on 1-D or (channels, n)."""
    n = x.shape[-1]
    f = np.fft.rfftfreq(n, 1 / SR) + 1e-3
    g = np.ones_like(f)
    if lo:
        g /= np.sqrt(1 + (lo / f) ** (2 * order))
    if hi:
        g /= np.sqrt(1 + (f / hi) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x, axis=-1) * g, n, axis=-1)


def t2x(n):
    """Time axis at twice the sample rate, for FM and ring modulation (2n samples)."""
    return np.arange(2 * n) / (2 * SR)


def dec2(x2):
    """Back from 2x to 1x: remove everything above ~20 kHz, then keep every other sample."""
    n = len(x2) // 2
    X = np.fft.rfft(x2[:2 * n])[:n // 2 + 1]
    f = np.arange(n // 2 + 1) * SR / n
    u = np.clip((23000 - f) / 3000, 0, 1)
    return np.fft.irfft(X * (0.5 - 0.5 * np.cos(np.pi * u)), n) * 0.5


def fade_edges(y, a=0.0005, b=0.004):
    n = y.shape[-1]
    t = np.arange(n) / SR
    return y * np.minimum(1, t / a) * np.clip((t[-1] - t) / b, 0, 1)


# ============================================================ engine
class Engine:
    """One render. `win` = (from, to): only events anchored inside it are placed, so a score can be
    rendered in pieces around a silence and nothing started before a stop rings on after it."""

    def __init__(self, dur, seed, win=(-1e9, 1e9)):
        self.dur = float(dur)
        self.N = int(round(self.dur * SR))
        self.seed = seed
        self.win = win
        self._rng = {}

    def rng(self, name):
        """Each instrument has its own random stream, seeded from zlib.crc32 of its name."""
        if name not in self._rng:
            self._rng[name] = np.random.default_rng([self.seed, zlib.crc32(name.encode())])
        return self._rng[name]

    def live(self, at):
        return self.win[0] <= at < self.win[1]

    def bus(self):
        return np.zeros((2, self.N))

    def place(self, bus, sig, at, gain=1.0, anchor=None):
        if not self.live(at if anchor is None else anchor):
            return
        s = sig if sig.ndim == 2 else np.vstack([sig, sig]) * np.sqrt(0.5)
        i = int(round(at * SR))
        a = max(0, -i)
        j = min(bus.shape[1], i + s.shape[1])
        if j <= max(i, 0):
            return
        bus[:, max(i, 0):j] += s[:, a:a + j - max(i, 0)] * gain

    @staticmethod
    def pan(sig, p):
        a = (np.clip(p, -1, 1) + 1) * np.pi / 4
        return np.vstack([sig * np.cos(a), sig * np.sin(a)])

    @staticmethod
    def fftconv(x, ir):
        L = len(x) + len(ir) - 1
        nfft = 1 << (L - 1).bit_length()
        return np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[:len(x)]

    def make_ir(self, rt=(1.1, 1.0, 0.55), length=1.8, predelay=0.018, taps=12):
        """Stereo room: sparse early reflections and a diffuse tail whose highs die first."""
        r = self.rng("room")
        n = int(length * SR)
        t = np.arange(n) / SR
        ir = np.zeros((2, n))
        for c in range(2):
            tail = np.zeros(n)
            for (lo, hi), rt60 in zip([(None, 400), (400, 4000), (4000, None)], rt):
                tail += band(r.standard_normal(n), lo, hi, 2) * np.exp(-6.91 * t / rt60)
            tail *= np.clip((t - predelay) / 0.03, 0, 1)
            er = np.zeros(n)
            for _ in range(taps):
                d = predelay * 0.3 + r.uniform(0.004, 0.06)
                er[int(d * SR)] += r.choice([-1, 1]) * np.exp(-d / 0.05) * 0.6
            ir[c] = tail / np.sqrt(np.sum(tail ** 2)) + er * 0.3
        return ir

    def conv(self, x, ir):
        return np.vstack([self.fftconv(x[0], ir[0]), self.fftconv(x[1], ir[1])])


# ============================================================ harmony: F# Lydian in stacked fourths
# name: (bass pitch class, voicing in midi). Every voicing is built from fourths.
CH = {
    "Fs_lyd": (6, [61, 66, 72, 77]),     # C# F# B# E#   F#maj7#11: the Lydian colour
    "Fs69":   (6, [58, 63, 68, 73]),     # A# D# G# C#   F#6/9, the home chord
    "Gs69":   (8, [60, 65, 70, 75]),     # B# E# A# D#   G#6/9, the bright II of Lydian
    "Ds11":   (3, [56, 61, 66, 70]),     # G# C# F# A#   D#m11
    "Cs_sus": (1, [56, 61, 66, 75]),     # G# C# F# D#   C#sus4 add9
    "Fs5":    (6, [54, 61, 66, 73]),     # F# C# F# C#   the open fifth at the end
}
CHORDS = {"ignite": ["Fs_lyd"], "look": ["Fs69", "Gs69"], "sources": ["Ds11", "Cs_sus"],
          "listen": ["Fs_lyd", "Ds11"], "speak": ["Cs_sus"], "resume": ["Gs69"],
          "swap": ["Fs69", "Gs69"], "approve": ["Ds11", "Fs69"], "end": ["Fs5"]}
# groove level per bar of each section: -1 pad only, 0 no drums, 1..4 build up
LEVELS = {"look": [1, 1], "sources": [2, 2], "listen": [0, 2], "speak": [3], "resume": [-1],
          "swap": [3, 3], "approve": [4, 4]}
LEVELS_VERT = {"swap": [2, 3]}          # the upright cut starts its groove one step lower
# music-bus level (dB) at the start and end of each section: the arc
SEC_DB = {"ignite": (0.0, -5.0), "look": (-10.0, -8.5), "sources": (-7.0, -6.0),
          "listen": (-8.0, -5.5), "speak": (-3.0, -2.0), "resume": (-10.0, -8.0),
          "swap": (-3.0, -1.5), "approve": (-0.5, 0.0), "end": (0.0, 0.0)}
SEC_DB_VERT = {"swap": (-11.0, -3.0)}
SECTION_HITS = [("ignite", "ignite"), ("b2", "look"), ("b3", "sources"), ("b4", "listen"),
                ("b5", "speak"), ("b6", "swap"), ("b7", "approve"), ("end", "end")]


def bass_midi(pc):
    return 36 + pc % 12                  # C2..B2: 65-123 Hz, the FM bass register


def sub_freq(m):
    f = mtof(m)
    return f / 2 if f / 2 >= 45 else f  # the sine sub stays within ~46-78 Hz


class Plan:
    """Sections, chords and levels, all read from the timing table."""

    def __init__(self, timing, kind):
        H = timing["hits"]
        self.H, self.dur = H, float(timing["dur"])
        self.BEAT = 60.0 / timing["bpm"]
        self.S16, self.BAR = self.BEAT / 4, self.BEAT * 4
        starts = [(float(H[h]), name) for h, name in SECTION_HITS if h in H]
        if "stop" in H and "silenceEnd" in H:
            starts += [(float(H["stop"]), "gap"), (float(H["silenceEnd"]), "resume")]
        starts.sort()
        self.secs = [(a, starts[k + 1][0] if k + 1 < len(starts) else self.dur, n)
                     for k, (a, n) in enumerate(starts)]
        self.levels = dict(LEVELS, **(LEVELS_VERT if kind == "vert" else {}))
        self.sec_db = dict(SEC_DB, **(SEC_DB_VERT if kind == "vert" else {}))
        # chord segments: one per bar of each section's chord list
        self.segs = []
        for a, b, name in self.secs:
            names = CHORDS.get(name)
            if not names:
                continue
            for k, ch in enumerate(names):
                s = a + k * self.BAR
                if s >= b - 1e-6:
                    break
                e = b if k == len(names) - 1 else min(b, a + (k + 1) * self.BAR)
                self.segs.append((s, e, ch, name))

    def sec_at(self, t):
        for a, b, n in self.secs:
            if a - 1e-6 <= t < b - 1e-6:
                return a, b, n
        return self.secs[-1]

    def level_at(self, t):
        a, _, n = self.sec_at(t)
        lv = self.levels.get(n)
        if lv is None:
            return None
        return lv[min(int((t - a + 1e-6) // self.BAR), len(lv) - 1)]

    def chord_at(self, t):
        for s, e, ch, _ in self.segs:
            if s - 1e-6 <= t < e - 1e-6:
                return ch
        return self.segs[-1][2]

    def arc(self):
        pts = []
        for a, b, n in self.secs:
            if n == "gap":
                continue
            d0, d1 = self.sec_db[n]
            pts += [(a + (0.002 if a > 0 else 0), d0), (b - 0.002, d1)]
        return curve(pts)


# ============================================================ instruments (all synthesised)
def fm_bass(f, gate, vel, rel=0.03, snap=0.022, idx=2.6, lp=2200, att=0.0012):
    """2-operator FM: the index snaps from bright to round in ~20 ms - a tight 'dwip'."""
    n = int((gate + rel) * SR)
    t = t2x(n)
    ph = 2 * np.pi * f * t
    I = idx * np.exp(-t / snap) + 0.55
    y = np.sin(ph + I * np.sin(ph) + 0.35 * np.exp(-t / 0.05) * np.sin(2 * ph))
    env = np.minimum(1, t / att) * (0.6 + 0.4 * np.exp(-t / 0.1)) * rel_env(t, gate, rel)
    return band(dec2(y * env), None, lp, 2) * vel


def sub_note(f, gate, vel, att=0.004, rel=0.04, decay=None):
    n = int((gate + rel) * SR)
    t = np.arange(n) / SR
    env = np.minimum(1, t / att) * rel_env(t, gate, rel)
    if decay:
        env *= np.exp(-t / decay)
    return np.sin(2 * np.pi * f * t) * env * vel


def kick(rng, vel):
    """Tight kick: 55 Hz body with a fast pitch drop, a knock an octave up and a tiny click, so a
    phone speaker (which cannot play 55 Hz) still hears it."""
    n = int(0.15 * SR)
    t = np.arange(n) / SR
    f = 55 + 110 * np.exp(-t / 0.016)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = 0.8 * np.sin(ph) * np.exp(-t / 0.065) + 0.42 * np.sin(2 * ph + 0.6) * np.exp(-t / 0.022)
    click = band(rng.standard_normal(n), 1200, 6000) * np.exp(-t / 0.0012) * 0.3
    y = np.tanh(1.3 * body) / np.tanh(1.3) + click
    return fade_edges(y, 0.0006, 0.025) * vel


def snare(rng, vel):
    """Noise snap plus a resonant 1.8 kHz ping and a short 190 Hz body."""
    n = int(0.24 * SR)
    t = np.arange(n) / SR
    noise = band(rng.standard_normal(n), 1500, 11000) * np.exp(-t / 0.05) * 0.45
    snap = band(rng.standard_normal(n), 3000, 13000) * np.exp(-t / 0.004) * 0.35
    ping = np.sin(2 * np.pi * 1800 * t * (1 - 0.01 * np.exp(-t / 0.01))) * np.exp(-t / 0.035) * 0.4
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.045) * 0.55
    return fade_edges(noise + snap + ping + body, 0.0006, 0.03) * vel


def hat_voice(rng, decay, length):
    """Metallic hat: pairs of sines multiplied together (ring modulation), band-limited to
    6-13 kHz, plus a breath of noise. Rendered at 2x."""
    n = int(length * SR)
    t = t2x(n)
    y = np.zeros(2 * n)
    for a, b in ((3310, 2870), (4130, 3470), (4710, 2390), (5230, 3910), (3770, 4990), (2910, 5570),
                 (6130, 4870), (6620, 5410)):
        a *= rng.uniform(0.985, 1.015)
        b *= rng.uniform(0.985, 1.015)
        y += np.sin(2 * np.pi * a * t + rng.uniform(0, 6.3)) * np.sin(2 * np.pi * b * t + rng.uniform(0, 6.3))
    y += 0.9 * rng.standard_normal(2 * n)
    y *= np.exp(-t / decay) * np.minimum(1, t / 0.0004)
    y = band(dec2(y), 6000, 13000, 4)
    y = fade_edges(y, 0.0003, 0.01)
    return y / np.abs(y).max()


def pad_seg(E, rng, midis, dur, att, rel, t_abs, morph):
    """Wavetable pad: two tables per note - A near-sine, B shaped by vowel-like formants - blended
    by a slow morph curve of absolute time; each note has a voice left and right, 7 cents apart."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    m = morph(t_abs + t)
    out = np.zeros((2, n))
    res = lambda f, F, B: 1 / (1 + ((f - F) / (B / 2)) ** 2)
    for mi in midis:
        f = mtof(mi)
        K = int(max(1, min(20, 6000 // f)))
        A = np.array([{1: 1.0, 2: 0.14, 3: 0.05}.get(k, 0.0) for k in range(1, K + 1)])
        Bt = np.array([k ** -0.6 * (res(k * f, 700, 520) + 0.9 * res(k * f, 1350, 640)
                                    + 0.3 * res(k * f, 2600, 900)) for k in range(1, K + 1)])
        Bt *= np.sqrt(np.sum(A ** 2) / np.sum(Bt ** 2))
        for side, cents in ((0, -7.0), (1, 7.0)):
            ff = f * 2 ** (cents / 1200) * (1 + 0.0015 * np.sin(2 * np.pi * rng.uniform(0.1, 0.25) * t
                                                                + rng.uniform(0, 6.3)))
            ph = 2 * np.pi * np.cumsum(ff) / SR + rng.uniform(0, 6.3)
            sa, sb = np.zeros(n), np.zeros(n)
            for k in range(1, K + 1):
                if A[k - 1] < 1e-3 and Bt[k - 1] < 1e-3:
                    continue
                s = np.sin(k * ph + rng.uniform(0, 6.3))
                sa += A[k - 1] * s
                sb += Bt[k - 1] * s
            v = (1 - m) * sa + m * sb
            out[side] += 0.88 * v
            out[1 - side] += 0.12 * v
    env = np.minimum(1, t / att) ** 2 * rel_env(t, dur - rel, rel)
    return out * env / len(midis)


def fm_pluck(f, dur, vel, ratio=2.0, idx=1.4, decay=0.12):
    """Glassy FM pluck for the arpeggio."""
    n = int(dur * SR)
    t = t2x(n)
    y = np.sin(2 * np.pi * f * t + idx * np.exp(-t / 0.02) * np.sin(2 * np.pi * f * ratio * t))
    y *= np.minimum(1, t / 0.001) * np.exp(-t / decay)
    return fade_edges(band(dec2(y), None, 3200, 2), 0.001, 0.01) * vel


def chime_note(f, vel, dur=0.9, idx=0.9, decay=0.32):
    """Glassy FM bell: carrier + a 3:1 modulator whose index falls fast, plus a 2.76 'glass' partial."""
    n = int(dur * SR)
    t = t2x(n)
    mod = (idx * np.exp(-t / 0.05) + 0.15) * np.sin(2 * np.pi * 3.0 * f * t)
    y = np.sin(2 * np.pi * f * t + mod) * np.exp(-t / decay)
    y += 0.22 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t / 0.1)
    y *= np.minimum(1, t / 0.0008)
    return fade_edges(dec2(y), 0.0008, 0.05) * vel


def glass_ping(f, vel, dur=0.9):
    """Soft glass: partials 1, 2.76 and 5.4 with fast-dying highs and a 1.2 ms attack."""
    n = int(dur * SR)
    t = t2x(n)
    y = (np.sin(2 * np.pi * f * t) * np.exp(-t / 0.4)
         + 0.35 * np.sin(2 * np.pi * 2.76 * f * t + 0.7) * np.exp(-t / 0.12)
         + 0.12 * np.sin(2 * np.pi * 5.4 * f * t + 1.3) * np.exp(-t / 0.04))
    y *= np.minimum(1, t / 0.0012)
    return fade_edges(dec2(y), 0.0012, 0.05) * vel


def tick(rng, f, vel):
    """Tool-call tick: a 3 ms click and a 45 ms FM blip at ~2.5-3.3 kHz."""
    n = int(0.045 * SR)
    t = t2x(n)
    y = np.sin(2 * np.pi * f * t + 1.2 * np.exp(-t / 0.008) * np.sin(2 * np.pi * 2 * f * t))
    y *= np.minimum(1, t / 0.0005) * np.exp(-t / 0.011)
    y = dec2(y)
    tt = np.arange(n) / SR
    click = band(rng.standard_normal(n), 2500, 7000) * np.exp(-tt / 0.0007) * (tt < 0.003)
    return fade_edges(0.8 * y + 0.45 * click, 0.0003, 0.004) * vel


def dwip(f0, vel, up=2.0, dur=0.4):
    """The ignition 'dwip': an FM tone whose pitch jumps up `up` octaves in ~60 ms while its index
    snaps from bright to round."""
    n = int(dur * SR)
    t = t2x(n)
    f = f0 * 2 ** (up * (1 - np.exp(-t / 0.028)))
    ph = 2 * np.pi * np.cumsum(f) / (2 * SR)
    y = np.sin(ph + (4.5 * np.exp(-t / 0.025) + 0.4) * np.sin(ph))
    y *= np.minimum(1, t / 0.0008) * np.exp(-t / 0.1)
    return fade_edges(band(dec2(y), None, 5000, 2), 0.0008, 0.04) * vel


def sparkle(rng, dur, count, lo=110, hi=128, decay=0.35, settle=False):
    """Particles: tiny sine grains on Lydian pitches between ~5 and ~13 kHz, scattered in time and
    across the stereo field. `settle` gathers them towards the start instead of spraying out."""
    n = int(dur * SR)
    out = np.zeros((2, n))
    pitches = [m for m in range(lo, hi + 1) if m % 12 in LYDIAN]
    for _ in range(count):
        at = min(rng.exponential(decay), dur - 0.03)
        if settle:
            at = min(rng.uniform(0, 1) ** 2 * dur * 0.6, dur - 0.03)
        L = rng.uniform(0.004, 0.014)
        m = int(L * SR)
        tt = np.arange(m) / SR
        g = np.sin(2 * np.pi * mtof(rng.choice(pitches)) * tt + rng.uniform(0, 6.3)) * np.sin(np.pi * tt / L) ** 2
        g *= rng.uniform(0.3, 1.0) * np.exp(-at / (decay * 2))
        i = int(at * SR)
        out[:, i:i + m] += Engine.pan(g, rng.uniform(-0.9, 0.9))[:, :n - i]
    return out


def cloud(rng, dur):
    """The 'thinking' cloud: grains of 20-60 ms, sine grains on Lydian pitches and band-passed
    noise grains, 1.5-6 kHz, spread wide, getting denser; it is cut dead at `dur`."""
    n = int(dur * SR)
    out = np.zeros((2, n + int(0.07 * SR)))
    pitches = [m for m in range(90, 115) if m % 12 in LYDIAN]
    at = 0.0
    while at < dur:
        u = at / dur
        at += rng.exponential(1 / (14 + 46 * u ** 1.3))
        if at >= dur:
            break
        L = rng.uniform(0.02, 0.06)
        m = int(L * SR)
        tt = np.arange(m) / SR
        w = np.sin(np.pi * tt / L) ** 2
        if rng.random() < 0.7:
            g = np.sin(2 * np.pi * mtof(rng.choice(pitches)) * tt + rng.uniform(0, 6.3))
        else:
            c = rng.uniform(1800, 5000)
            g = band(rng.standard_normal(m), c / 1.3, c * 1.3, 2) * 2.5
        g = g * w * rng.uniform(0.3, 1.0) * (0.6 + 0.4 * u)
        i = int(at * SR)
        out[:, i:i + m] += Engine.pan(g, rng.uniform(-0.95, 0.95))
    out = out[:, :n]
    t = np.arange(n) / SR
    out *= np.minimum(1, t / 0.15) * np.clip((dur - t) / 0.0015, 0, 1)    # stops dead
    return out


def hum(rng, dur, f0, morph_at=(0.3, 0.95)):
    """The reactor listening: a harmonic drone on f0 through three vowel formants that glide from
    'ah' to 'oo'. Steady pitch, slow glide, no syllables - tonal, never speech-like."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    tc = np.arange(0, dur + 0.01, 0.005)
    u = np.clip((tc / dur - morph_at[0]) / (morph_at[1] - morph_at[0]), 0, 1)
    s = u * u * (3 - 2 * u)
    ah = np.array([[730, 1090, 2440], [1.0, 0.5, 0.22], [150, 180, 260]])
    oo = np.array([[320, 870, 2240], [1.0, 0.28, 0.08], [150, 180, 260]])
    V = ah[:, :, None] * (1 - s) + oo[:, :, None] * s                     # (3 rows, 3 formants, ctrl)
    f = f0 * (1 + 0.002 * np.sin(2 * np.pi * 0.33 * t) + 0.0008 * np.sin(2 * np.pi * 1.1 * t + 1.0))
    ph = 2 * np.pi * np.cumsum(f) / SR
    out = np.zeros((2, n))
    for k in range(1, int(4200 // f0) + 1):
        fk = k * f0
        a = sum(V[1, i] / (1 + ((fk - V[0, i]) / (V[2, i] / 2)) ** 2) for i in range(3)) * k ** -0.7
        s_ = np.interp(t, tc, a) * np.sin(k * ph + rng.uniform(0, 6.3))
        p = 0.35 * (1 if k % 2 else -1) * min(1, k / 6)
        out += Engine.pan(s_, p)
    env = np.sin(np.pi / 2 * np.clip(t / 0.35, 0, 1)) ** 2 * rel_env(t, dur - 0.25, 0.25)
    return out * env


def reverse_swell(E, ir, midis, L):
    """A chord's reverb tail played backwards, swelling into a cut and ending exactly on it."""
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for m in midis:
        x += np.sin(2 * np.pi * mtof(m) * t) * np.exp(-t / 0.3) + 0.3 * np.sin(4 * np.pi * mtof(m) * t) * np.exp(-t / 0.1)
    x *= np.minimum(1, t / 0.002)
    wet = np.vstack([E.fftconv(x, ir[0]), E.fftconv(x, ir[1])])[:, ::-1]
    m = int(L * SR)
    wet = band(wet[:, -m:], 200, 7000, 2)
    tt = np.arange(m) / SR
    wet *= (tt / L) ** 2.2 * np.clip((L - tt) / 0.006, 0, 1)
    return wet / (np.abs(wet).max() + 1e-12)


# ============================================================ the arrangement
KICK = {1: [{0: 0.75}, {0: 0.75, 10: 0.45}],
        2: [{0: 0.85, 10: 0.6}, {0: 0.85, 7: 0.4, 10: 0.6}],
        3: [{0: 0.9, 6: 0.5, 10: 0.75}, {0: 0.9, 10: 0.7, 13: 0.45}],
        4: [{0: 1.0, 6: 0.55, 10: 0.8}, {0: 1.0, 3: 0.4, 10: 0.75, 13: 0.5}]}
SNARE = {2: [{8: 0.75}, {8: 0.75}], 3: [{8: 0.9}, {8: 0.9, 15: 0.25}],
         4: [{8: 1.0, 14: 0.22}, {8: 1.0, 11: 0.2, 15: 0.3}]}
BASS = {   # step: (length in 16ths, velocity, degree: R root, O octave, 5 fifth, A approach)
    0: [{0: (15, 0.8, "R")}, {0: (15, 0.8, "R")}],
    2: [{0: (5, 0.85, "R"), 10: (4, 0.7, "R")}, {0: (5, 0.85, "R"), 10: (3, 0.7, "R"), 14: (2, 0.55, "A")}],
    3: [{0: (3, 0.9, "R"), 3: (2, 0.55, "O"), 6: (2, 0.7, "R"), 10: (3, 0.8, "5"), 13: (2, 0.6, "O")},
        {0: (3, 0.9, "R"), 6: (2, 0.6, "R"), 8: (2, 0.55, "O"), 10: (4, 0.8, "R"), 14: (2, 0.6, "A")}],
    4: [{0: (3, 0.95, "R"), 3: (2, 0.6, "O"), 6: (2, 0.75, "R"), 8: (1, 0.5, "O"), 10: (3, 0.85, "5"), 13: (2, 0.65, "O")},
        {0: (3, 0.95, "R"), 3: (1, 0.5, "O"), 6: (2, 0.65, "R"), 8: (2, 0.6, "O"), 10: (4, 0.85, "R"), 14: (2, 0.65, "A")}],
}
TICK_NOTES = [99, 101, 102, 104]         # D#7 E#7 F#7 G#7: one Lydian step higher per tool step
GAIN = dict(kick=0.56, snare=0.38, hat=0.13, bass=0.36, sub=0.2, pad=0.5, arp=0.12,
            tick=0.30, ping=0.2, chime=0.30, hum=0.42, think=0.14, swell=0.16, sparkle=0.16, hit=0.55)


def render(timing, kind, win):
    """Render the score (or the piece of it whose events fall inside `win`). Returns the stereo mix
    and stems for the picture's envelopes."""
    H = timing["hits"]
    dur = float(timing["dur"])
    E = Engine(dur, seed=zlib.crc32(("jarvis-v6-" + kind).encode()), win=win)
    P = Plan(timing, kind)
    S16, BAR, BEAT = P.S16, P.BAR, P.BEAT
    N = E.N
    ta = np.arange(N) / SR
    ir = E.make_ir()
    bus = {k: E.bus() for k in ("kick", "snare", "hat", "bass", "sub", "pad", "arp", "hit", "hitkick", "ui", "hum", "think", "swell")}
    kicks, ducks = [], []                                     # kick times; (time, length) of UI ducks
    gap = (float(H["stop"]), float(H["silenceEnd"])) if "stop" in H and "silenceEnd" in H else None
    hit_times = [float(H[h]) for h in ("ignite", "stop", "end") if h in H]

    hats = {k: hat_voice(E.rng("hat-voice"), d, L) for k, d, L in (("a", 0.022, 0.08), ("b", 0.03, 0.09), ("open", 0.14, 0.3))}
    morph = lambda t: 0.5 - 0.42 * np.cos(2 * np.pi * t / (4 * BAR))

    # ---------------------------------------------------- drums and bass on the 16th grid
    r_dr, r_b = E.rng("drums"), E.rng("bass")
    for i in range(int(round(dur / S16))):
        at = i * S16
        lvl = P.level_at(at)
        if lvl is None or any(abs(at - h) < 1e-6 for h in hit_times):
            continue
        clear = any(0 < h - at <= 0.3 + 1e-6 for h in hit_times)      # room for the hit that follows
        step, var = i % 16, (i // 16) % 2
        if lvl >= 1:
            v = KICK[lvl][var].get(step)
            if v and not clear:
                kicks.append(at)
                E.place(bus["kick"], kick(r_dr, v * r_dr.uniform(0.95, 1.02)), at)
            v = SNARE.get(lvl, [{}, {}])[var].get(step)
            if v:
                E.place(bus["snare"], E.pan(snare(r_dr, v * r_dr.uniform(0.92, 1.05)), 0.08), at)
            # hats: 8ths at level 1-2 (with 16th ghosts at 2), 16ths at 3-4, an open hat at 4
            hv = 0.0
            if step % 2 == 0:
                hv = 0.6 if step % 4 == 2 else 0.38
            elif lvl >= 3:
                hv = 0.26
            elif lvl == 2 and step in (7, 15):
                hv = 0.2
            hv *= {1: 0.7, 2: 0.85, 3: 1.0, 4: 1.1}[lvl]
            if hv:
                vo = "open" if (lvl == 4 and step == 14 and var) else ("a" if step % 4 else "b")
                E.place(bus["hat"], E.pan(hats[vo] * hv * r_dr.uniform(0.85, 1.1), 0.35 if step % 2 else -0.3), at)
        pat = BASS.get(lvl)
        if pat and step in pat[var] and not clear:
            ln, v, deg = pat[var][step]
            ch = P.chord_at(at)
            r = bass_midi(CH[ch][0])
            if deg == "O":
                m = r + 12
            elif deg == "5":
                m = r + 7
            elif deg == "A":
                nxt = P.chord_at(at + 2 * S16 + 1e-3)
                tgt = bass_midi(CH[nxt][0])
                m = r + 7 if nxt == ch else next(tgt - d for d in (1, 2) if (tgt - d) % 12 in LYDIAN)
            else:
                m = r
            g = ln * S16 - 0.012
            _, b_end, _ = P.sec_at(at)
            g = min(g, b_end - at - 0.02, min([h - at - 0.3 for h in hit_times if h > at] or [9.0]))
            E.place(bus["bass"], fm_bass(mtof(m), g, v * r_b.uniform(0.95, 1.03), idx=2.2 + 0.4 * (lvl >= 3)), at)

    # ---------------------------------------------------- pad and sub: one segment per chord
    r_p = E.rng("pad")
    for k, (a, b, ch, sec) in enumerate(P.segs):
        fresh = k == 0 or P.segs[k - 1][1] < a - 1e-6 or sec in ("end",) or a in hit_times
        att = 0.03 if (a in hit_times) else (0.06 if fresh else 0.12)     # at a hit the kick owns the transient
        start = a if fresh else a - 0.06
        rel = 0.35 if sec != "end" else 0.5
        length = (b - start) + (rel if b < dur - 1e-6 else 0.0)
        root = 48 + (CH[ch][0] - 48) % 12
        notes = sorted(set([root] + CH[ch][1]))
        if sec == "end":
            length = dur - a
            seg = pad_seg(E, r_p, notes, length, att, 2.5, start, morph)
            seg *= 0.3 + 0.7 * np.exp(-np.arange(seg.shape[1]) / SR / 0.7)     # a hit that settles
        else:
            seg = pad_seg(E, r_p, notes, length, att, rel, start, morph)
        lv = P.level_at(a)
        pg = {None: 1.0, -1: 1.0, 0: 0.9, 1: 0.9, 2: 0.8, 3: 0.72, 4: 0.72}.get(lv, 0.8)
        if sec == "ignite":
            pg = 0.7
        if sec == "end":
            pg = 0.6
        E.place(bus["pad"], seg * pg, start, anchor=a)
        # the sub holds the chord's root under everything except the pad-only moments
        if lv is None or lv >= 0:
            f = sub_freq(bass_midi(CH[ch][0]))
            if sec in ("ignite", "end"):
                continue                                     # the hits play their own sub
            gate = b - a - (0.3 if any(abs(b - h) < 1e-6 for h in hit_times) else 0.02)
            E.place(bus["sub"], sub_note(f, gate, 0.9 if lv and lv >= 1 else 0.75), a)

    # ---------------------------------------------------- glass arpeggio at levels 3 (8ths) and 4 (16ths)
    r_a = E.rng("arp")
    order = [0, 2, 1, 3, 2, 0, 3, 1]
    for i in range(int(round(dur / S16))):
        at = i * S16
        lvl = P.level_at(at)
        if lvl not in (3, 4) or (lvl == 3 and i % 2):
            continue
        notes = [m + 12 for m in CH[P.chord_at(at)][1]]
        m = notes[order[i % 8] % len(notes)]
        v = (0.9 if i % 4 == 0 else 0.6) * r_a.uniform(0.85, 1.05) * (0.8 if lvl == 3 else 1.0)
        E.place(bus["arp"], E.pan(fm_pluck(mtof(m), 0.35, v), 0.55 if i % 2 else -0.55), at)

    # ---------------------------------------------------- the three full-strength hits
    r_h = E.rng("hits")
    if "ignite" in H:
        t0 = float(H["ignite"])
        kicks.append(t0)
        E.place(bus["hitkick"], kick(r_h, 0.9), t0)
        E.place(bus["hit"], E.pan(dwip(mtof(42), 0.45), 0.0), t0)
        E.place(bus["hit"], sub_note(mtof(30), 1.5, 0.35, att=0.03, rel=0.1, decay=0.9), t0)
        for j, m in enumerate(CH["Fs_lyd"][1]):
            E.place(bus["hit"], E.pan(chime_note(mtof(m + 12), 0.11, dur=1.5, idx=0.6, decay=0.5), -0.45 + 0.3 * j), t0 + 0.003)
        E.place(bus["hit"], sparkle(r_h, 1.4, 90, decay=0.35), t0, GAIN["sparkle"])
    if "stop" in H:
        t0 = float(H["stop"])
        ch = P.chord_at(t0 - 0.01)
        kicks.append(t0)
        E.place(bus["hitkick"], kick(r_h, 0.85), t0)
        E.place(bus["hit"], E.pan(snare(r_h, 0.8), 0.08), t0, GAIN["snare"])
        E.place(bus["hit"], fm_bass(mtof(bass_midi(CH[ch][0])), 0.3, 0.5, idx=3.2, att=0.01), t0)
        E.place(bus["hit"], sub_note(sub_freq(bass_midi(CH[ch][0])), 0.3, 0.35, att=0.03), t0)
        for j, m in enumerate(CH[ch][1]):
            E.place(bus["hit"], E.pan(chime_note(mtof(m + 12), 0.14, dur=0.4, idx=0.8), -0.45 + 0.3 * j), t0 + 0.003)
    if "end" in H:
        t0 = float(H["end"])
        kicks.append(t0)
        L = dur - t0
        # The upright cut's end lands right after the reversed swell and the pad's return, so its
        # kick is a little softer to keep the limiter under 3 dB.
        E.place(bus["hitkick"], kick(r_h, 0.9 if kind == "landscape" else 0.75), t0)
        E.place(bus["hit"], sub_note(mtof(30), L - 0.3, 0.32, att=0.04, rel=0.3, decay=0.9), t0)
        E.place(bus["hit"], fm_bass(mtof(42), L - 0.3, 0.4, rel=0.3, idx=2.4, snap=0.03, att=0.04) * np.exp(-np.arange(int(L * SR)) / SR / 1.2), t0)
        for j, m in enumerate([66, 73, 78, 85]):                  # F#4 C#5 F#5 C#6: the open fifth, in glass
            E.place(bus["hit"], E.pan(chime_note(mtof(m), 0.14 - 0.015 * j, dur=min(3.0, L), idx=0.5, decay=0.9), -0.4 + 0.27 * j), t0 + 0.003)
        E.place(bus["hit"], sparkle(r_h, min(2.0, L), 70, decay=0.5, settle=True), t0, GAIN["sparkle"])
    if "name" in H:                                              # the soft accent under the name
        t0 = float(H["name"])
        for m, v, p in ((90, 0.26, -0.15), (97, 0.16, 0.15)):   # F#6, C#7
            E.place(bus["hit"], E.pan(chime_note(mtof(m), v, dur=2.0, idx=0.35, decay=0.7), p), t0)
        E.place(bus["hit"], sub_note(mtof(42), 0.5, 0.18, att=0.003, rel=0.3, decay=0.4), t0)

    # ---------------------------------------------------- transitions: reversed swells into iris cuts
    for h in ("b2", "b6", "end"):
        if h in H:
            t0 = float(H[h])
            L = 2 * BEAT
            if gap and gap[1] < t0:
                L = min(L, t0 - gap[1])
            L = min(L, t0)
            if L > 0.1:
                E.place(bus["swell"], reverse_swell(E, ir, CH[P.chord_at(t0)][1], L), t0 - L, anchor=t0 - 1e-3)

    # ---------------------------------------------------- interface sounds (own the 2-6 kHz band)
    r_u = E.rng("ui")
    for k, h in enumerate(("step1", "step2", "step3", "step4")):
        if h in H:
            t0 = float(H[h])
            E.place(bus["ui"], E.pan(tick(r_u, mtof(TICK_NOTES[k]), 1.0), -0.3 + 0.2 * k), t0)
            ducks.append((t0, 0.15))
    if "tapUse" in H:
        t0 = float(H["tapUse"])
        E.place(bus["ui"], E.pan(tick(r_u, mtof(102), 1.0), 0.3), t0)
        ducks.append((t0, 0.15))
    if "warn" in H:
        t0 = float(H["warn"])
        E.place(bus["ui"], E.pan(glass_ping(mtof(92), GAIN["ping"] / GAIN["tick"]), 0.1), t0)       # G#6
        ducks.append((t0, 0.15))
    if "approve" in H:
        t0 = float(H["approve"])
        E.place(bus["ui"], E.pan(chime_note(mtof(78), GAIN["chime"] / GAIN["tick"] * 0.9, dur=0.9), -0.12), t0)          # F#5
        E.place(bus["ui"], E.pan(chime_note(mtof(85), GAIN["chime"] / GAIN["tick"], dur=1.1), 0.12), t0 + S16)     # C#6
        ducks.append((t0, 0.45))
    if "b2" in H and "answer" in H:
        t0, t1 = float(H["b2"]), float(H["answer"])
        E.place(bus["think"], cloud(E.rng("cloud"), t1 - t0), t0)
    if "b4" in H:
        t0 = float(H["b4"])
        t1 = P.sec_at(t0)[1]
        E.place(bus["hum"], hum(E.rng("hum"), t1 - t0, mtof(42)), t0)

    # ---------------------------------------------------- mix
    arc = dbg(P.arc()(ta))

    def env_from(times, att, rel, hold=0.0):
        e = np.zeros(N)
        for t0, *rest in times:
            h = rest[0] if rest else hold
            i = int(round((t0 - att) * SR))
            tt = np.arange(int((att + h + 5 * rel) * SR)) / SR
            seg = np.minimum(1, tt / att) * np.where(tt < att + h, 1.0, np.exp(-(tt - att - h) / rel))
            a, b = max(i, 0), min(N, i + len(seg))
            if b > a:
                e[a:b] = np.maximum(e[a:b], seg[a - i:b - i])
        return e

    pump = env_from([(t,) for t in kicks], 0.005, 0.1 / 3)        # sidechain: 5 ms attack, ~100 ms release
    duck = 1 - (1 - dbg(-3)) * env_from(ducks, 0.005, 0.05)       # UI sounds: -3 dB on the music
    ticks = [(t0 - 0.03, 0.12) for t0, _ in ducks]
    think = bus["think"] * GAIN["think"] * (1 - (1 - dbg(-10)) * env_from(ticks, 0.02, 0.04))  # the cloud clears for each tick
    lows = (bus["bass"] * GAIN["bass"] + bus["sub"] * GAIN["sub"]) * (1 - (1 - dbg(-8)) * pump)
    pad = bus["pad"] * GAIN["pad"] * (1 - (1 - dbg(-5)) * pump)
    pad = band(pad, 150, None, 2)
    music = (bus["kick"] * GAIN["kick"] + bus["snare"] * GAIN["snare"] + bus["hat"] * GAIN["hat"]
             + lows + pad + bus["arp"] * GAIN["arp"]) * arc * duck
    ui = bus["ui"]
    fx = bus["hit"] * GAIN["hit"] + bus["swell"] * GAIN["swell"]
    hitkick = bus["hitkick"] * GAIN["kick"]
    voice = bus["hum"] * GAIN["hum"] * arc + think
    uig = ui * GAIN["tick"]                                       # the tick gain is the UI bus gain
    send = (pad * 0.35 + bus["snare"] * GAIN["snare"] * arc * 0.12 + bus["arp"] * GAIN["arp"] * arc * 0.5
            + uig * 0.3 + fx * 0.25 + bus["hum"] * GAIN["hum"] * arc * 0.3)
    wet = E.conv(band(send, 250, 8000, 2), ir)
    mix = music + hitkick + fx + uig + voice + 0.3 * wet

    # clean below 30 Hz, mono below 120 Hz, a gentle roll-off above 17 kHz
    f = np.fft.rfftfreq(N, 1 / SR) + 1e-3
    M, S = np.fft.rfft((mix[0] + mix[1]) / 2), np.fft.rfft((mix[0] - mix[1]) / 2)
    top = 1 / np.sqrt(1 + (f / 17000) ** 8)
    M *= top / np.sqrt(1 + (30 / f) ** 8)
    S *= top / np.sqrt(1 + (120 / f) ** 8)
    m_, s_ = np.fft.irfft(M, N), np.fft.irfft(S, N)
    mix = np.vstack([m_ + s_, m_ - s_])
    stems = {"ui": uig, "think": think}
    return mix, stems


# ============================================================ effects on the rendered mix
def tape_stop(x, t0, D):
    """From t0 the 'tape' slows to a halt over D seconds (pitch and speed dive together); after
    that the piece is silent."""
    y = x.copy()
    i0, n = int(round(t0 * SR)), int(round(D * SR))
    u = np.arange(n) / n
    pos = i0 + np.concatenate([[0.0], np.cumsum((1 - u) ** 2)[:-1]])
    g = np.clip((1 - u) / 0.25, 0, 1)
    for c in range(x.shape[0]):
        y[c, i0:i0 + n] = np.interp(pos, np.arange(x.shape[1]), x[c]) * g
    y[:, i0 + n:] = 0
    return y


def stutter(x, t_cut, S32, reps=4):
    """Buffer stutter: the 1/32 note that starts `reps` slices before the cut is repeated into it,
    with the low end taken out, so the downbeat after it lands on a clear floor."""
    l = int(round(S32 * SR))
    a = int(round(t_cut * SR)) - reps * l
    if a < 0:
        return x
    t = np.arange(l) / SR
    sl = band(x[:, a:a + l], 200, None, 2) * np.minimum(1, t / 0.001) * np.clip((t[-1] - t) / 0.002, 0, 1)
    for k in range(reps):
        x[:, a + k * l:a + (k + 1) * l] = sl * (0.85 + 0.15 * k / max(1, reps - 1))
    return x


# ============================================================ master (from v4/v5's score.py)
def tp_detect(x, os_=4):
    nf = 1 << (x.shape[1] - 1).bit_length()
    up = np.fft.irfft(np.fft.rfft(x, nf, axis=1), nf * os_, axis=1)[:, :x.shape[1] * os_] * os_
    return np.abs(up).max(0).reshape(-1, os_).max(1)


def limit(x, ceiling_db=-1.5, look=0.002, rel=0.08):
    N = x.shape[1]
    greq = np.minimum(1, dbg(ceiling_db) / (tp_detect(x) + 1e-12))
    W = int(look * SR)
    g1 = np.lib.stride_tricks.sliding_window_view(np.concatenate([greq, np.ones(W)]), W + 1).min(1)[:N]
    B = 48
    nb = N // B + 1
    gb = np.concatenate([g1, np.ones(nb * B - N)]).reshape(nb, B).min(1)
    out = np.empty(nb)
    g = 1.0
    step = 1 - np.exp(-B / SR / rel)
    for i, v in enumerate(gb):
        g = v if v < g else min(v, g + (1 - g) * step)
        out[i] = g
    g2 = np.minimum(np.repeat(out, B)[:N], g1)
    g3 = np.convolve(np.concatenate([np.ones(W), g2]), np.ones(W) / W, mode="valid")[:N]
    return x * g3, g3


def ebur128(x):
    raw = np.ascontiguousarray(x.T).astype("<f4").tobytes()
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                          "-af", "ebur128=peak=true", "-f", "null", "-"], input=raw, capture_output=True).stderr.decode()
    tail = err[err.rindex("Summary:"):]
    return (float(tail.split("I:")[1].split("LUFS")[0]), float(tail.split("Peak:")[1].split("dBFS")[0]),
            float(tail.split("LRA:")[1].split("LU")[0]))


def master(mix, zero, fade):
    """Limit, zero the silences AFTER the limiter, fade the tail, and find the one linear gain that
    lands on -14 LUFS. `zero` = [(from, to)] in seconds; `fade` = (start, end) of the last fade."""
    x = mix / np.abs(mix).max()
    gain = 1.0
    for _ in range(10):
        y, gr = limit(x * gain)
        a, b = int(fade[0] * SR), int(fade[1] * SR)
        y[:, a:b] *= np.cos(np.linspace(0, np.pi / 2, b - a)) ** 2
        for z0, z1 in zero:
            y[:, int(round(z0 * SR)):int(round(z1 * SR))] = 0.0
        I, TP, LRA = ebur128(y)
        if abs(I + 14) < 0.05 and TP <= -1.0:
            break
        gain *= dbg(-14 - I)
    print(f"   limiter works hardest at {int(np.argmin(gr)) / SR:.3f} s")
    return y, (I, TP, LRA, 20 * np.log10(gr.min()))


def write(y, mp3_path):
    pcm = (np.clip(y.T, -1, 1) * 32767).round().astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-codec:a", "libmp3lame", "-b:a", "320k", "-ar", str(SR), mp3_path], input=pcm, check=True)


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<f4").reshape(-1, 2).T.astype(np.float64)


# ============================================================ picture data
EVENT_KIND = {"ignite": "hit", "step1": "tick", "step2": "tick", "step3": "tick", "step4": "tick",
              "answer": "answer", "warn": "ping", "b4": "listen", "stop": "stop", "silenceEnd": "resume",
              "tapUse": "tick", "approve": "chime", "end": "hit", "name": "accent"}


def audio_data(y, stems, dur, zero, path, H):
    """Per-frame envelopes 0..1 and an event list for the picture (see the module docstring)."""
    N = y.shape[1]
    frames = int(round(dur * FPS))
    hop = SR // FPS
    m = y.mean(0)

    def env(x, release=None, norm="p98", hold=0):
        v = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(x) else 0.0
                      for i in range(frames)])
        if hold:                                               # peak-hold for `hold` frames
            v = np.array([v[max(0, i - hold):i + 1].max() for i in range(len(v))])
        if release:
            k = np.exp(-1 / (release * FPS))
            s = 0.0
            for i in range(len(v)):
                s = max(v[i], s * k)
                v[i] = s
        ref = np.percentile(v, 98) if norm == "p98" else v.max()
        v = (v / (ref or 1)).clip(0, 1)
        for z0, z1 in zero:                                    # dark in the silences
            v[int(np.floor(z0 * FPS + 1e-6)):int(np.ceil(z1 * FPS - 1e-6))] = 0
        return np.round(v, 3)

    low = band(m, None, 160, 4)
    hi = band(stems["ui"].mean(0), 2000, 6000, 4)
    data = {"fps": FPS, "low": env(low, 0.15).tolist(), "rms": env(m).tolist(),
            "hi": env(hi, 0.12, "max", hold=3).tolist(), "think": env(stems["think"].mean(0), None, "max").tolist(),
            "events": [{"t": round(float(H[h]), 3), "kind": k} for h, k in
                       sorted(EVENT_KIND.items(), key=lambda kv: H.get(kv[0], 1e9)) if h in H]}
    with open(path, "w") as fh:
        fh.write("window.AUDIO_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")


# ============================================================ checks on the shipped file
CUES = [  # hit, band (Hz) to look in, what should start there
    ("ignite", 30, 20000, "kick + dwip"), ("b2", 30, 200, "kick"), ("step1", 2000, 6000, "tick"),
    ("step2", 2000, 6000, "tick"), ("step3", 2000, 6000, "tick"), ("step4", 2000, 6000, "tick"),
    ("b3", 30, 200, "kick"), ("warn", 1200, 6000, "glass ping"), ("b4", 60, 400, "FM bass"),
    ("b5", 30, 200, "kick"), ("stop", 30, 20000, "stop hit"), ("b6", 30, 200, "kick"),
    ("tapUse", 2000, 6000, "tick"), ("b7", 30, 200, "kick"), ("approve", 600, 6000, "chime"),
    ("end", 30, 200, "kick"), ("name", 1000, 8000, "glass accent")]


def onset(x, t, lo, hi):
    """Where the sound in [lo, hi] Hz starts near t: the first 0.5 ms step (within +-30 ms) whose
    level is halfway (in dB) between the level before and the peak just after. Returns
    (onset time, rise in dB)."""
    a = int(round((t - 0.3) * SR))
    pad = max(0, -a)
    seg = np.concatenate([np.zeros(pad), x[max(a, 0):int(round((t + 0.3) * SR))]])
    seg = band(seg, lo, hi, 4)
    h = SR // 2000
    e = seg[:len(seg) // h * h].reshape(-1, h)
    db = 10 * np.log10(np.convolve(np.mean(e ** 2, 1), np.ones(4) / 4, mode="same") + 1e-14)
    c = int(0.3 * 2000)                                         # the index of t
    peak = db[c - 10:c + 60].max()
    pre = max(np.median(db[c - 120:c - 30]), peak - 40)
    thr = pre + 0.5 * (peak - pre)
    idx = np.nonzero(db[c - 60:c + 60] >= thr)[0]
    if not len(idx):
        return None, peak - pre
    k = c - 60 + idx[0]
    return t - 0.3 + k * h / SR, peak - pre                  # seg[0] is always t - 0.3 (zero-padded)


def checks(path, H, dur, zero, gr):
    x = decode(path)
    M, S = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2
    I, TP, LRA = ebur128(x)
    Im, _, _ = ebur128(np.vstack([M, M]))
    P = np.abs(np.fft.rfft(x, axis=1)) ** 2
    P = P.sum(0)
    f = np.fft.rfftfreq(x.shape[1], 1 / SR)
    tot = P.sum()
    share = lambda lo, hi: 10 * np.log10(P[(f >= lo) & (f < hi)].sum() / tot)
    sm = 10 * np.log10(np.sum(S ** 2) / np.sum(M ** 2))
    print(f"   file {os.path.basename(path)}: {x.shape[1] / SR:.3f} s  I={I:.1f} LUFS  TP={TP:.1f} dBTP  "
          f"LRA={LRA:.1f} LU  limiter max GR={gr:.1f} dB  mono fold-down {Im - I:+.1f} LU")
    print(f"   bands (share of total): <60 {share(0, 60):.1f} | 60-120 {share(60, 120):.1f} | "
          f"120-2k {share(120, 2000):.1f} | 2-5k {share(2000, 5000):.1f} | 5-10k {share(5000, 10000):.1f} | "
          f"10-20k {share(10000, 20000):.1f} dB   Side/Mid {sm:.1f} dB")
    for z0, z1 in zero:
        a, b = int(round(z0 * SR)), int(round(z1 * SR))
        inner = np.abs(x[:, a + int(0.03 * SR):b - int(0.005 * SR)]).max() if b - a > int(0.04 * SR) else 0.0
        pk = np.abs(x[:, a:b]).max()
        print(f"   silence {z0:.2f}-{z1:.2f} s: peak {20 * np.log10(pk + 1e-12):.1f} dBFS over the whole gap, "
              f"{20 * np.log10(inner + 1e-12):.1f} dBFS from 30 ms in (mp3 smears a few ms)")
    bad = []
    for h, lo, hi, what in sorted(CUES, key=lambda c: H.get(c[0], 1e9)):
        if h not in H:
            continue
        t = float(H[h])
        o, rise = onset(M, t, lo, hi)
        if o is None or rise < 6 or abs(o - t) > 0.005:
            bad.append(f"{h} ({what}) at {t:.3f}: " + ("no clear onset" if o is None or rise < 6
                                                       else f"starts at {o:.4f} ({(o - t) * 1000:+.1f} ms)")
                       + f", rise {rise:.0f} dB")
        else:
            print(f"      ok  {h:<10} {t:6.3f}  onset {(o - t) * 1000:+5.1f} ms  rise {rise:4.0f} dB  ({what})")
    if "answer" in H:                                             # the cloud must stop dead
        t = float(H["answer"])
        band_ = band(M[int((t - 0.2) * SR):int((t + 0.2) * SR)], 1500, 6000, 4)
        before = np.sqrt(np.mean(band_[int(0.12 * SR):int(0.195 * SR)] ** 2))
        after = np.sqrt(np.mean(band_[int(0.205 * SR):int(0.28 * SR)] ** 2))
        print(f"      cloud at answer {t:.3f}: 1.5-6 kHz level drops {20 * np.log10(after / before):.1f} dB across the cut")
    print("   timing self-check: " + ("every cue within 5 ms" if not bad else "PROBLEMS:\n      " + "\n      ".join(bad)))
    return dict(I=I, TP=TP, LRA=LRA, bad=bad)


# ============================================================ main
def main():
    os.makedirs(os.path.join(ASSETS, "music"), exist_ok=True)
    jobs = [("land", "timing.json", "score.mp3", "audio-data.js"),
            ("vert", "timing-vertical.json", "score-vertical.mp3", "audio-data-vertical.js")]
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for kind, tj, mp3, ad in jobs:
        if only and only != kind:
            continue
        with open(os.path.join(ASSETS, tj)) as fh:
            timing = json.load(fh)
        H = timing["hits"]
        dur = float(timing["dur"])
        S16 = 60.0 / timing["bpm"] / 4
        zero = []
        if "stop" in H and "silenceEnd" in H:
            stop, back = float(H["stop"]), float(H["silenceEnd"])
            a, sa = render(timing, kind, (-1e9, stop + 1e-6))
            b, sb = render(timing, kind, (back - 1e-6, 1e9))
            a = tape_stop(a, stop, TAPE_STOP)
            ib = int(round(back * SR))
            b[:, :ib] = 0
            mix = a + b
            stems = {k: tape_stop(sa[k], stop, TAPE_STOP) + np.hstack([np.zeros((2, ib)), sb[k][:, ib:]]) for k in sa}
            zero.append((stop + TAPE_STOP, back))
        else:
            mix, stems = render(timing, kind, (-1e9, 1e9))
        for h in ("b4", "b7"):                                   # buffer stutters into these cuts
            if h in H:
                mix = stutter(mix, float(H[h]), S16 / 2)
        tail0 = dur - TAIL_ZERO
        zero.append((tail0, dur))
        fade = (max(float(H.get("name", tail0 - 1.5)) + 0.9, tail0 - 1.6), tail0)
        y, (I, TP, LRA, GR) = master(mix, zero, fade)
        print(f"{mp3}: {dur:.2f} s  PCM I={I:.2f} LUFS  TP={TP:.1f} dBTP  LRA={LRA:.1f} LU  limiter max GR={GR:.1f} dB")
        if GR < -3.0:
            raise SystemExit(f"limiter gain reduction {GR:.1f} dB is over 3 dB: turn the hits down")
        path = os.path.join(ASSETS, "music", mp3)
        write(y, path)
        audio_data(y, stems, dur, zero, os.path.join(ASSETS, ad), H)
        checks(path, H, dur, zero, GR)


if __name__ == "__main__":
    main()
