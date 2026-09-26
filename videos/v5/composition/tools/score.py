"""Original score for the Jarvis v5 launch video, "A day with Jarvis": landscape (30 s) and upright (15 s).

Run from the composition folder:   python3 tools/score.py

The style: a relaxed, warm lo-fi / neo-soul groove in F major at the tables' tempo (96 BPM).
Nothing like the earlier videos (no trailer braams, risers or glitch hits, no sparse plucks).
Every sound is synthesised here:
  - a soft electric piano (FM "Rhodes": a round body, a short metal "tine" ping at the start
    of each note, a gentle stereo tremolo), playing lush chords - maj9, m9, 9sus, 6/9;
  - a warm pad underneath, a round bass (fundamentals between about 49 and 87 Hz);
  - a soft kick, a rim click and a brushed snare, a shaker; 16ths swung 57 %, every hit
    a little early or late and a little louder or softer, like a person playing.

The music follows the day. Each camera "station" in the timing table starts a section, and
chords change on the station arrivals (plus one more chord halfway through a long station):
  dawn     Fmaj9            a soft pad and two chimes as the reactor wakes; no drums
  brief    Bbmaj9 -> Am11   (7:30) the piano comes in, a shaker, a soft kick, a soft bass
  focus    Gm9 -> C9sus4    (9:00) the full groove; a playful two-note "uh-uh" on `drift`
  tell     Fmaj9 -> Dm9     (15:00) the warmest, fullest part; a rising "yes" on `approve`
                            that lands in the chord, a soft vibraphone motif on `ring`/`ring2`
  learn    Bbmaj7 -> Bbm6   (19:30) evening: the sound slowly darkens (a closing low-pass
                            filter), the drums thin out, the bass stays; a soft swish and a
                            sagging, detuned bell on `erase`
  standby  C9sus4           (23:00) a low soft thump on `press`; on `asleep` the drums and
                            bass stop cleanly, leaving a quiet pad
  end      F6/9 -> Fadd9    the chord resolves home on `end` (a reversed-piano swell leads
                            into it), one bell each on `e1`, `e2`, `e3` rising A-C-E, the
                            final F chord on `word`, then a natural decay to real silence
                            (the last 0.3 s is digital zero)
The upright cut has only dawn, focus, tell and end: its focus starts at the "morning" level and
the full groove comes in at the halfway chord, so it still climbs, then resolves on the same chord.

Nothing is hard-coded to a clock: every time comes from the tables, so the score re-renders
correctly when they change. Deterministic: numpy + ffmpeg only, fixed seeds.
Reads   assets/timing.json (landscape) and assets/timing-vertical.json (upright).
Writes  assets/music/score.mp3            assets/audio-data.js
        assets/music/score-vertical.mp3   assets/audio-data-vertical.js
audio-data.js holds per-frame envelopes for the picture: `low` (0..1, the kick and bass, smoothed,
used to pulse the reactor's glow gently) and `rms` (0..1, overall level).
Loudness: -14 LUFS integrated, true peak <= -1 dBTP (limiter ceiling -1.5 dBTP). 48 kHz stereo mp3.
"""
import json, os, subprocess
import numpy as np

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
FPS = 30
SWING = 0.57            # the first 16th of each pair gets 57 % of the 8th


# ============================================================ shared DSP (from v4's score.py)
class Engine:
    def __init__(self, dur, seed):
        self.dur = float(dur)
        self.N = int(round(self.dur * SR))
        self.rng = np.random.default_rng(seed)

    @staticmethod
    def t_axis(n):
        return np.arange(n) / SR

    def bus(self):
        return np.zeros((2, self.N))

    def place(self, bus, sig, at, gain=1.0):
        s = sig if sig.ndim == 2 else np.vstack([sig, sig])
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

    def hum(self, at, ms):
        """Human timing: gaussian jitter, clipped at 2 sigma."""
        return at + float(np.clip(self.rng.normal(0, ms / 1000), -2 * ms / 1000, 2 * ms / 1000))

    @staticmethod
    def fft_band(x, lo=None, hi=None):
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(len(x), 1 / SR) + 1e-3
        g = np.ones_like(f)
        if lo:
            g *= 1 / (1 + (lo / f) ** 4)
        if hi:
            g *= 1 / (1 + (f / hi) ** 4)
        return np.fft.irfft(X * g, len(x))

    @staticmethod
    def stft_filter(x, gfun, n=2048, hop=512):
        """Time-varying spectral filter (sqrt-Hann WOLA). gfun(t[:,None], f[None,:]) -> gain."""
        if x.ndim == 2:
            return np.vstack([Engine.stft_filter(c, gfun, n, hop) for c in x])
        L = len(x)
        xp = np.concatenate([np.zeros(n), x, np.zeros(n + hop)])
        win = np.sqrt(0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n))
        fr = np.lib.stride_tricks.sliding_window_view(xp, n)[::hop]
        X = np.fft.rfft(fr * win, axis=1)
        tc = (np.arange(X.shape[0]) * hop + n / 2 - n) / SR
        f = np.fft.rfftfreq(n, 1 / SR) + 1e-3
        X *= gfun(tc[:, None], f[None, :])
        y = np.fft.irfft(X, n, axis=1) * win
        out = np.zeros(len(xp))
        for i in range(y.shape[0]):
            out[i * hop:i * hop + n] += y[i]
        return out[n:n + L] / 2.0

    @staticmethod
    def lp(fc_fun, order=2):
        def g(tc, f):
            fc = np.maximum(fc_fun(tc), 30)
            return 1 / np.sqrt(1 + (f / fc) ** (2 * order))
        return g

    @staticmethod
    def fftconv(x, ir):
        L = len(x) + len(ir) - 1
        nfft = 1 << (L - 1).bit_length()
        return np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[:len(x)]

    def make_ir(self, rt=(1.8, 1.4, 0.7), length=2.4, predelay=0.025, taps=14, seed=0):
        """Stereo room: sparse early reflections + a diffuse tail whose highs die first."""
        r = np.random.default_rng(seed)
        n = int(length * SR); t = self.t_axis(n)
        ir = np.zeros((2, n))
        for c in range(2):
            tail = np.zeros(n)
            for (lo, hi), rt60 in zip([(None, 400), (400, 3500), (3500, None)], rt):
                tail += self.fft_band(r.standard_normal(n), lo, hi) * np.exp(-6.91 * t / rt60)
            tail *= np.clip((t - predelay) / 0.04, 0, 1)
            er = np.zeros(n)
            for _ in range(taps):
                d = predelay * 0.3 + r.uniform(0.004, 0.07)
                er[int(d * SR)] += r.choice([-1, 1]) * np.exp(-d / 0.05) * 0.6
            er = np.convolve(er, np.ones(6) / 6, mode="same")
            ir[c] = tail / np.sqrt(np.sum(tail ** 2)) + er * 0.35
        return ir

    def conv(self, x, ir):
        return np.vstack([self.fftconv(x[0], ir[0]), self.fftconv(x[1], ir[1])])

    def compress(self, x, thr_db, ratio, att=0.01, rel=0.25, block=48):
        lvl = np.abs(x).max(0)
        nb = len(lvl) // block
        blk = lvl[:nb * block].reshape(nb, block).max(1)
        env = np.zeros(nb); e = 0.0
        ca, cr = np.exp(-block / SR / att), np.exp(-block / SR / rel)
        for i, v in enumerate(blk):
            e = ca * e + (1 - ca) * v if v > e else cr * e + (1 - cr) * v
            env[i] = e
        gr = np.minimum(0, (thr_db - 20 * np.log10(env + 1e-9)) * (1 - 1 / ratio))
        g = np.repeat(10 ** (gr / 20), block)
        g = np.concatenate([g, np.full(x.shape[1] - len(g), g[-1] if len(g) else 1.0)])
        return x * g


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)

def dbg(g):
    return 10 ** (g / 20)

def curve(points):
    ts, vs = zip(*sorted(points))
    return lambda t: np.interp(t, ts, vs)

def rel_env(t, gate, rel):
    """1 until `gate`, then a raised-cosine fall to 0 over `rel` seconds (no click)."""
    u = np.clip((t - gate) / rel, 0, 1)
    return 0.5 + 0.5 * np.cos(np.pi * u)


# ============================================================ harmony: F major
# name: (root pitch class, triad intervals, electric-piano voicing without the root - the bass has it)
CH = {
    "Fmaj9":  (5,  (0, 4, 7), [57, 60, 64, 67]),         # A C E G
    "Bbmaj9": (10, (0, 4, 7), [57, 60, 62, 65]),         # A C D F
    "Am11":   (9,  (0, 3, 7), [55, 60, 62, 64]),         # G C D E
    "Gm9":    (7,  (0, 3, 7), [58, 62, 65, 69]),         # Bb D F A
    "C9sus":  (0,  (0, 5, 7), [58, 62, 65, 67]),         # Bb D F G
    "Dm9":    (2,  (0, 3, 7), [60, 64, 65, 69]),         # C E F A
    "Bbmaj7": (10, (0, 4, 7), [53, 57, 62, 65]),         # F A D F: lower, the evening
    "Bbm6":   (10, (0, 3, 7), [53, 55, 61, 65]),         # F G Db F: the borrowed minor iv, dusk
    "F69":    (5,  (0, 4, 7), [57, 62, 67, 72]),         # A D G C: the resolution
    "Fadd9":  (5,  (0, 4, 7), [53, 60, 65, 67, 69, 72]), # F C F G A C: the last chord
}
SCALE = {0, 2, 4, 5, 7, 9, 10}                           # F major pitch classes

# Chords per station: the first on arrival, the second (if any) halfway through, on the half-bar grid.
PLAN = {"dawn": ["Fmaj9"], "brief": ["Bbmaj9", "Am11"], "focus": ["Gm9", "C9sus"],
        "tell": ["Fmaj9", "Dm9"], "learn": ["Bbmaj7", "Bbm6"], "standby": ["C9sus"], "end": ["F69"]}
LEVEL_OF = {"dawn": "dawn", "brief": "morning", "focus": "groove", "tell": "full",
            "learn": "evening", "standby": "night", "end": "end"}

def bass_midi(pc):
    """The root in the octave whose fundamental sits in ~46-92 Hz (G1..F2): warm, not a sub wall."""
    m = 24 + pc
    while mtof(m) < 46:
        m += 12
    return m

def fold_bass(m):
    while mtof(m) < 44:
        m += 12
    return m

def tones_in(name, lo, hi):
    """The chord's triad tones between midi lo (incl.) and hi (excl.), ascending."""
    pc, tri, _ = CH[name]
    return [m for m in range(lo, hi) if (m - pc) % 12 in tri]


# ============================================================ instruments (all synthesised)
def rhodes(E, f, gate, vel=0.6, rel=0.14):
    """FM electric piano: body with a velocity-dependent 'bark', a short tine ping, two-stage decay."""
    n = int((gate + rel) * SR); t = E.t_axis(n)
    f = f * 2 ** (E.rng.normal(0, 1.5) / 1200)
    sc = (261.6 / f) ** 0.4                                     # low notes ring longer
    ph = 2 * np.pi * f * t
    I = (0.5 + 1.9 * vel ** 1.5) * np.exp(-t / (0.32 * sc)) + 0.18
    body = np.sin(ph + I * np.sin(ph))
    tine_f = min(f * 7.0, 4200.0)
    tine = np.sin(2 * np.pi * tine_f * t + 0.5) * np.exp(-t / 0.022) * (0.2 + 0.4 * vel)
    env = np.minimum(1, t / 0.002) * (0.6 * np.exp(-t / (1.0 * sc)) + 0.4 * np.exp(-t / (3.2 * sc)))
    y = body * env + tine * np.minimum(1, t / 0.001)
    y = (np.tanh(1.1 * y + 0.2) - np.tanh(0.2)) / 1.1           # a little pickup asymmetry: warm 2nd harmonic
    return y * rel_env(t, gate, rel) * vel

def bell(E, f, dur, vel=0.4, ratio=3.5, index=0.6, decay=1.2):
    """A soft FM chime (low index: round, not clangy)."""
    n = int(dur * SR); t = E.t_axis(n)
    mod = np.sin(2 * np.pi * f * ratio * t) * index * np.exp(-t / 0.12)
    car = np.sin(2 * np.pi * f * t + mod) * np.exp(-t / decay)
    car += 0.15 * np.sin(4 * np.pi * f * t) * np.exp(-t / (decay * 0.3))
    env = np.minimum(1, t / 0.003) * np.clip((dur - t) / 0.08, 0, 1)
    return car * env * vel * 0.5

def vibes(E, f, dur, vel=0.4, trem=5.4):
    """Vibraphone-like bar: partials 1, 4 and 10 with a motor tremolo."""
    n = int(dur * SR); t = E.t_axis(n)
    s = (np.sin(2 * np.pi * f * t) + 0.22 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / 0.12)
         + 0.05 * np.sin(2 * np.pi * min(10 * f, 9000) * t) * np.exp(-t / 0.03))
    s *= 1 - 0.28 * (0.5 - 0.5 * np.cos(2 * np.pi * trem * t))
    env = np.minimum(1, t / 0.002) * np.exp(-t / 0.9) * np.clip((dur - t) / 0.08, 0, 1)
    return s * env * vel * 0.5

def mallet(E, f, dur, vel=0.4, scoop=0.0):
    """Marimba-ish soft mallet; `scoop` starts the note that many semitones flat and slides up."""
    n = int(dur * SR); t = E.t_axis(n)
    ff = f * 2 ** (-scoop * np.exp(-t / 0.045) / 12)
    ph = 2 * np.pi * np.cumsum(ff) / SR
    s = (np.sin(ph) * np.exp(-t / 0.32) + 0.3 * np.sin(3.93 * ph) * np.exp(-t / 0.05)
         + 0.08 * np.sin(9.2 * ph) * np.exp(-t / 0.012))
    env = np.minimum(1, t / 0.0015) * np.clip((dur - t) / 0.05, 0, 1)
    return s * env * vel * 0.6

def pad(E, midis, dur, att, rel, fc=1600.0):
    """Warm additive pad: soft saw-like partials, pre-filtered, two detuned voices spread L/R."""
    n = int(dur * SR); t = E.t_axis(n)
    out = np.zeros((2, n))
    for m in midis:
        f = mtof(m)
        for side, c in ((0, -6.0), (1, 6.0)):
            ff = f * 2 ** (c / 1200)
            vib = 1 + 0.0012 * np.sin(2 * np.pi * E.rng.uniform(0.12, 0.3) * t + E.rng.uniform(0, 6.3))
            phase = 2 * np.pi * np.cumsum(ff * vib) / SR + E.rng.uniform(0, 6.3)
            K = int(max(1, min(10, 5000 // ff)))
            s = np.zeros(n)
            for k in range(1, K + 1):
                s += (1 / k) / (1 + (k * ff / fc) ** 2) * np.sin(k * phase + E.rng.uniform(0, 6.3))
            out[side] += 0.8 * s
            out[1 - side] += 0.2 * s
    env = np.minimum(1, t / att) ** 2 * rel_env(t, dur - rel, rel)
    return out * env / len(midis)

def bass_note(E, f, gate, vel=0.8, rel=0.05):
    """Round electric-bass-like note: sine with a little 2nd/3rd harmonic that fades, soft saturation."""
    n = int((gate + rel) * SR); t = E.t_axis(n)
    ph = 2 * np.pi * f * t
    s = np.sin(ph) + 0.3 * np.sin(2 * ph + 0.2) * np.exp(-t / 0.25) + 0.1 * np.sin(3 * ph) * np.exp(-t / 0.1)
    env = np.minimum(1, t / 0.006) * (0.72 + 0.28 * np.exp(-t / 0.12)) * np.exp(-t / 2.2)
    s = np.tanh(1.4 * s * env) / np.tanh(1.4)
    return s * rel_env(t, gate, rel) * vel

def kick(E, vel=0.8):
    """A soft kick: ~52 Hz body, gentle pitch drop, a felt thud instead of a click."""
    n = int(SR * 0.42); t = E.t_axis(n)
    f = 52 + 58 * np.exp(-t / 0.032)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.15)
    felt = E.fft_band(E.rng.standard_normal(n), 120, 800) * np.exp(-t / 0.008) * 0.12
    return 0.8 * np.tanh(1.3 * (body + felt)) * vel * np.minimum(1, t / 0.0015) * np.clip((t[-1] - t) / 0.06, 0, 1)

def rim(E, vel=0.6):
    """Rim click: a woody knock (two short resonances) and a tiny band-limited click."""
    n = int(SR * 0.12); t = E.t_axis(n)
    fw = E.rng.uniform(470, 530)
    wood = np.sin(2 * np.pi * fw * t) * np.exp(-t / 0.016) * 0.7 + np.sin(2 * np.pi * 1620 * t) * np.exp(-t / 0.006) * 0.35
    clk = E.fft_band(E.rng.standard_normal(n), 1500, 7000) * np.exp(-t / 0.0025) * 0.5
    return 1.3 * (wood + clk) * vel * np.minimum(1, t / 0.0008) * np.clip((t[-1] - t) / 0.02, 0, 1)

def brush(E, vel=0.5, tail=0.08):
    """Brushed snare: band-limited noise (700 Hz - 7.5 kHz) with a soft 5 ms attack."""
    n = int(SR * (tail * 4)); t = E.t_axis(n)
    x = E.fft_band(E.rng.standard_normal(n), 700, 7500)
    env = np.minimum(1, t / 0.005) ** 2 * np.exp(-t / tail)
    return x * env * vel * 0.5 * np.clip((t[-1] - t) / 0.03, 0, 1)

def shaker(E, vel=0.4):
    """Shaker: 3.8-9.5 kHz noise (rolls off above), a soft 12 ms attack, short decay."""
    n = int(SR * 0.11); t = E.t_axis(n)
    c = E.rng.uniform(0.94, 1.06)
    x = E.fft_band(E.rng.standard_normal(n), 3800 * c, 9500 * c)
    env = np.minimum(1, t / E.rng.uniform(0.009, 0.015)) ** 1.5 * np.exp(-np.maximum(t - 0.012, 0) / 0.025)
    return x * env * vel * 0.6 * np.clip((t[-1] - t) / 0.02, 0, 1)

def swish(E, dur, f_lo, f_hi, peak=0.5, width=0.6, pan_path=(0, 0)):
    """Filtered-noise air: the band moves from f_lo to f_hi, the envelope peaks at `peak` (0..1)."""
    n = int(dur * SR); t = E.t_axis(n); u = t / dur
    x = np.vstack([E.rng.standard_normal(n), E.rng.standard_normal(n)])
    ctr = lambda tc: f_lo * (f_hi / f_lo) ** np.clip(tc / dur, 0, 1)
    x = E.stft_filter(x, lambda tc, f: np.exp(-(np.log2(f / ctr(tc)) / width) ** 2) / (1 + (f / 11000) ** 4),
                      n=1024, hop=256)
    env = np.where(u < peak, np.sin(np.pi / 2 * u / peak) ** 2, np.cos(np.pi / 2 * (u - peak) / (1 - peak)) ** 2)
    p = np.interp(u, [0, 1], pan_path)
    a = (p + 1) * np.pi / 4
    return np.vstack([x[0] * np.cos(a), x[1] * np.sin(a)]) * env

def sag_bell(E, f, dur=1.0, vel=0.3):
    """Erase: two chimes 14 cents apart whose pitch sags a semitone, like the memory letting go."""
    n = int(dur * SR); t = E.t_axis(n)
    out = np.zeros((2, n))
    for side, c in ((0, -14), (1, 14)):
        ff = f * 2 ** (c / 1200) * 2 ** (-(t / dur) ** 1.3 / 12)
        ph = 2 * np.pi * np.cumsum(ff) / SR
        s = np.sin(ph + 0.5 * np.sin(2 * ph) * np.exp(-t / 0.08)) * np.exp(-t / 0.35)
        out[side] += s * 0.8; out[1 - side] += s * 0.2
    return out * np.minimum(1, t / 0.004) * np.clip((dur - t) / 0.08, 0, 1) * vel

def thump(E, vel=0.6):
    """Standby press: a low, soft felt thump (78 -> 48 Hz) with a muted knock."""
    n = int(SR * 0.4); t = E.t_axis(n)
    f = 48 + 30 * np.exp(-t / 0.025)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.1)
    knock = E.fft_band(E.rng.standard_normal(n), 150, 600) * np.exp(-t / 0.006) * 0.3
    return np.tanh(1.2 * (body + knock)) * vel * np.minimum(1, t / 0.002) * np.clip((t[-1] - t) / 0.05, 0, 1)


# ============================================================ the plan, read from the table
def build_plan(timing):
    """Chord changes and section levels, both anchored on the station arrivals."""
    st = timing["stations"]; dur = float(timing["dur"])
    BEAT = 60.0 / timing["bpm"]; HALF = 2 * BEAT
    ids = [s["id"] for s in st]
    chords, levels = [], []
    for k, s in enumerate(st):
        a = float(s["at"][0])
        b = float(st[k + 1]["at"][0]) if k + 1 < len(st) else dur
        names = PLAN.get(s["id"], ["Fmaj9"])
        split = None
        if len(names) > 1:
            mid = (a + b) / 2
            cands = [HALF * j for j in range(int(dur / HALF) + 2)
                     if a + 2 * BEAT - 1e-6 <= HALF * j <= b - 2 * BEAT + 1e-6]
            if cands:
                split = min(cands, key=lambda c: abs(c - mid))
        chords.append((a, names[0]))
        if split is not None:
            chords.append((split, names[1]))
        lvl = LEVEL_OF.get(s["id"], "groove")
        if lvl == "groove" and "brief" not in ids[:k] and split is not None:
            levels += [(a, "morning"), (split, "groove")]      # no morning station: the groove builds in-station
        else:
            levels.append((a, lvl))
    return chords, levels

def step_lookup(pairs):
    ts = [p[0] for p in pairs]
    def at(t):
        i = int(np.searchsorted(ts, t + 1e-6, side="right")) - 1
        return pairs[max(i, 0)][1]
    return at


# ---- per-level patterns, keyed by the 16th step in the bar; two variants for alternating bars
EP_PAT = {
    "morning": [{0: (8, 0.60), 10: (6, 0.44)}, {0: (8, 0.56), 8: (8, 0.42)}],
    "groove":  [{0: (6, 0.70), 6: (3, 0.48), 10: (6, 0.60)}, {0: (4, 0.66), 3: (3, 0.44), 8: (5, 0.60), 14: (2, 0.48)}],
    "full":    [{0: (6, 0.76), 6: (2, 0.50), 10: (4, 0.64), 14: (2, 0.54)}, {0: (3, 0.70), 3: (4, 0.48), 8: (6, 0.66), 14: (2, 0.56)}],
    "evening": [{0: (10, 0.55), 10: (6, 0.40)}, {0: (16, 0.50)}],
}
BASS_PAT = {   # step: (length in 16ths, velocity, degree: R root, 5 fifth, O octave, A approach to the next chord)
    "morning": [{0: (14, 0.45, "R")}, {0: (14, 0.40, "R")}],
    "groove":  [{0: (5, 0.90, "R"), 6: (2, 0.60, "R"), 8: (4, 0.80, "5"), 14: (2, 0.60, "A")},
                {0: (5, 0.90, "R"), 7: (2, 0.55, "O"), 10: (3, 0.75, "R"), 14: (2, 0.60, "A")}],
    "full":    [{0: (3, 0.92, "R"), 3: (2, 0.50, "R"), 6: (2, 0.62, "R"), 8: (4, 0.82, "5"), 14: (2, 0.62, "A")},
                {0: (5, 0.92, "R"), 7: (2, 0.58, "O"), 10: (3, 0.78, "R"), 12: (2, 0.55, "5"), 14: (2, 0.62, "A")}],
    "evening": [{0: (8, 0.80, "R"), 10: (5, 0.62, "R")}, {0: (12, 0.80, "R"), 14: (2, 0.55, "A")}],
}
KICK_PAT = {
    "morning": [{0: 0.55, 8: 0.42}, {0: 0.55, 8: 0.42}],
    "groove":  [{0: 0.85, 10: 0.70}, {0: 0.85, 7: 0.42, 10: 0.70}],
    "full":    [{0: 0.90, 10: 0.74}, {0: 0.90, 7: 0.48, 10: 0.74}],
    "evening": [{0: 0.62, 10: 0.48}, {0: 0.62, 10: 0.48}],
}
RIM_PAT = {"groove": {4: 0.70, 12: 0.74}, "full": {4: 0.72, 12: 0.76}, "evening": {12: 0.50}}
# section mix: (overall gain dB at start, at end), (pad gain dB), (tone: low-pass cutoff Hz at start, at end)
ARC = {"dawn": (-1.5, -1.0), "morning": (-1.0, -0.5), "groove": (0, 0), "full": (0.5, 0.5),
       "evening": (0, -2.0), "night": (-4.5, -7.0), "end": (-1.0, -1.0)}
PAD_DB = {"dawn": 0, "morning": -5, "groove": -7, "full": -5.5, "evening": -4, "night": -2, "end": -1}
TONE = {"dawn": (2500, 4200), "morning": (5000, 8000), "groove": (12000, 12000), "full": (14000, 14000),
        "evening": (9000, 1500), "night": (1300, 1000), "end": (4500, 3200)}


# ============================================================ one render
def render(timing, kind):
    H = timing["hits"]
    dur = float(timing["dur"])
    E = Engine(dur, seed=20260926 if kind == "land" else 20260927)
    rng, N = E.rng, E.N
    ta = E.t_axis(N)
    BEAT = 60.0 / timing["bpm"]; S16 = BEAT / 4; BAR = 4 * BEAT
    SW = (SWING - 0.5) * 2 * S16                              # delay of the off 16ths
    chords, levels = build_plan(timing)
    chord_at, level_at = step_lookup(chords), step_lookup(levels)
    seg_start = {lv: t for t, lv in reversed(levels)}         # first time each level starts
    end_at = seg_start.get("end", dur)
    word = H.get("word", min(dur - 1.5, end_at + 3.0))
    stop_at = H.get("asleep", end_at)                         # drums and bass stop here (or where the end starts)
    changes = [t for t, _ in chords]
    lv_changes = [t for t, _ in levels]

    ep, padb, bass, bass_home, drums, fx = (E.bus() for _ in range(6))
    kicks = []

    def swung(i):
        return i * S16 + (SW if i % 2 else 0.0)

    def bar_progress(t):
        """0..1 through the current level segment (the evening thins out as it goes)."""
        a = max([x for x in lv_changes if x <= t + 1e-6] or [0.0])
        b = min([x for x in lv_changes if x > t + 1e-6] or [dur])
        return float(np.clip((t - a) / max(b - a, 1e-3), 0, 1))

    # ---------------------------------------------------- electric piano: comp events, then play them
    ev = []                                                   # (time, chord, vel, max gate s, short)
    for i in range(int(dur / S16) + 1):
        at = i * S16; lvl = level_at(at)
        pat = EP_PAT.get(lvl)
        if not pat or at >= stop_at - 1e-6:
            continue
        step, bar = i % 16, i // 16
        if step in pat[bar % 2]:
            ln, v = pat[bar % 2][step]
            if lvl == "evening":
                v *= 1 - 0.3 * bar_progress(at)
            name = chord_at(at + 2 * S16 + 1e-3) if step == 14 else chord_at(at)   # the push anticipates
            ev.append((swung(i), name, v, ln * S16, ln <= 3))
    for c, name in chords:                                    # every chord change is struck, wherever it falls
        if EP_PAT.get(level_at(c)) and c < stop_at and not any(abs(e[0] - c) < 0.03 for e in ev):
            ev.append((c, name, 0.62, 2 * BEAT, False))
    if "night" in seg_start:
        ev.append((seg_start["night"], chord_at(seg_start["night"]), 0.5, end_at - seg_start["night"], False))
    if "end" in seg_start:
        ev.append((end_at, chord_at(end_at), 0.62, word - end_at, False))
        ev.append((word, "Fadd9", 0.56, dur - word, False))
    ev.sort(key=lambda e: e[0])
    bounds = sorted(set([t for t, lv in levels if not EP_PAT.get(lv) and lv not in ("night", "end")]))
    for k, (at, name, v, gate, short) in enumerate(ev):
        nxt = ev[k + 1][0] if k + 1 < len(ev) else dur
        nb = min([b_ for b_ in bounds if b_ > at + 1e-3] or [dur])
        g = max(0.08, min(gate, nxt - at, nb - at) - 0.01)
        notes = CH[name][2][1:] if short else CH[name][2]
        big = at >= end_at - 1e-3
        spread = (0.022 if big else 0.011) * rng.uniform(0.7, 1.3)
        t0 = E.hum(at, 5) if not big else at
        for j, m in enumerate(notes):
            vv = v * (0.82 + 0.18 * j / max(1, len(notes) - 1)) * rng.uniform(0.9, 1.08)
            dt = j * spread
            s = rhodes(E, mtof(m), max(0.06, g - dt), vv, rel=0.35 if big else 0.14)
            E.place(ep, E.pan(s, -0.3 + 0.6 * j / max(1, len(notes) - 1)), t0 + dt)

    # a reversed-piano swell of the notes the two chords share, rising into the end chord
    if "end" in seg_start:
        prev = chord_at(end_at - 0.01); home = chord_at(end_at)
        pcs = {m % 12 for m in CH[prev][2]} & {m % 12 for m in CH[home][2]}
        sw_notes = [m for m in CH[home][2] if m % 12 in pcs] or CH[home][2][:2]
        L = 2 * BEAT
        rev = sum(rhodes(E, mtof(m), L, 0.5, rel=0.01) for m in sw_notes)[::-1].copy()
        tt = E.t_axis(len(rev))
        rev *= np.minimum(1, tt / 0.3) ** 2 * rel_env(tt, len(rev) / SR - 0.02, 0.02)
        rev = E.fft_band(rev, None, 5000)
        E.place(fx, E.pan(rev, 0.0), end_at - len(rev) / SR, 0.55)

    # ---------------------------------------------------- pad: one segment per chord, crossfaded
    pch = chords + ([(word, "Fadd9")] if "end" in seg_start else [])
    pch.sort()
    for k, (at, name) in enumerate(pch):
        b = pch[k + 1][0] if k + 1 < len(pch) else dur
        rootm = 48 + (CH[name][0] - 48) % 12
        notes = sorted(set([rootm] + CH[name][2][:4]))
        first = k == 0
        att = min(1.6, 0.6 * (b - at)) if first else 0.28
        rel = 0.5
        seg = pad(E, notes, b - at + rel + (0.0 if first else 0.05), att, rel,
                  fc=1300 if level_at(at) in ("evening", "night") else 1800)
        E.place(padb, seg, at if first else at - 0.05)

    # ---------------------------------------------------- bass
    bev = []                                                  # (time, midi, vel, gate)
    for i in range(int(dur / S16) + 1):
        at = i * S16; lvl = level_at(at)
        pat = BASS_PAT.get(lvl)
        if not pat or at >= stop_at - 0.05:
            continue
        step, bar = i % 16, i // 16
        if step not in pat[bar % 2]:
            continue
        ln, v, deg = pat[bar % 2][step]
        name = chord_at(at); r = bass_midi(CH[name][0])
        if deg == "R":
            m = r
        elif deg == "5":
            m = r + 7
        elif deg == "O":
            m = r + 12
        else:                                                 # approach the next chord from a scale step below
            nxt = chord_at(at + 2 * S16 + 1e-3)
            if nxt == name:
                m = r + 7
            else:
                tgt = bass_midi(CH[nxt][0])
                m = fold_bass(tgt - 1 if (tgt - 1) % 12 in SCALE else tgt - 2)
        if lvl == "evening":
            v *= 1 - 0.15 * bar_progress(at)
        bev.append((swung(i), m, v, ln * S16))
    for c, name in chords:
        if (BASS_PAT.get(level_at(c)) or level_at(c) == "night") and c < stop_at - 0.05 and not any(abs(e[0] - c) < 0.03 for e in bev):
            bev.append((c, bass_midi(CH[name][0]), 0.8, 2 * BEAT))
    if "night" in seg_start and seg_start["night"] < stop_at:
        n0 = seg_start["night"]
        bev = [e for e in bev if abs(e[0] - n0) > 0.03] + [(n0, bass_midi(CH[chord_at(n0)][0]), 0.72, stop_at - n0)]
    bev.sort(key=lambda e: e[0])
    for k, (at, m, v, gate) in enumerate(bev):
        nxt = bev[k + 1][0] if k + 1 < len(bev) else dur
        g = max(0.06, min(gate, nxt - at - 0.012, stop_at - at - 0.03))
        E.place(bass, bass_note(E, mtof(m), g, v * rng.uniform(0.92, 1.05)), E.hum(at, 2.5))
    if "end" in seg_start:                                    # home: a long low F under the resolution, and again on the wordmark
        E.place(bass_home, bass_note(E, mtof(bass_midi(CH[chord_at(end_at)][0])), word - end_at - 0.05, 0.62, rel=0.3), end_at)
        E.place(bass_home, bass_note(E, mtof(bass_midi(5)), dur - word, 0.5, rel=0.5), word)

    # ---------------------------------------------------- drums on the swung, humanised 16th grid
    first_groove = min([t for t, lv in levels if lv in KICK_PAT] or [None], key=lambda x: x if x is not None else 1e9)
    for i in range(int(dur / S16) + 1):
        at = i * S16; lvl = level_at(at)
        if at >= stop_at - 0.08 or lvl in ("dawn", "end"):
            continue
        step, bar = i % 16, i // 16
        t_ = swung(i)
        thin = 1.0
        keep = 1.0
        if lvl == "evening":
            p = bar_progress(at); thin = 1 - 0.35 * p; keep = 1 - 0.7 * p
        if lvl == "night":
            if step == 0:
                kt = E.hum(t_, 2); kicks.append(kt); E.place(drums, kick(E, 0.5), kt)
            continue
        kp = KICK_PAT[lvl][bar % 2]
        if step in kp:
            kt = E.hum(t_, 2); kicks.append(kt)
            E.place(drums, kick(E, kp[step] * thin * rng.uniform(0.92, 1.03)), kt)
        elif lvl == "full" and step == 15 and bar % 2 and rng.random() < 0.5:
            kt = E.hum(t_, 2); kicks.append(kt); E.place(drums, kick(E, 0.34), kt)
        rp = RIM_PAT.get(lvl, {})
        if step in rp and (step % 8 == 4 or rng.random() < keep):
            v = rp[step] * thin * rng.uniform(0.88, 1.08)
            tr = E.hum(t_ + 0.004, 3)
            E.place(drums, E.pan(rim(E, v), 0.12), tr)
            if lvl == "full":
                E.place(drums, E.pan(brush(E, v * 0.9, 0.09), -0.1), tr - 0.004)
        if lvl == "full" and step in (7, 11) and rng.random() < 0.55:          # ghost brushes
            E.place(drums, E.pan(brush(E, 0.22 * rng.uniform(0.8, 1.2), 0.05), -0.2), E.hum(t_, 5))
        # shaker: 8ths in the morning and evening, 16ths in the groove; accents on the off-beats
        dense = lvl in ("groove", "full")
        if step % 2 == 0 or dense:
            v = (0.55 if step % 4 == 2 else 0.40 if step % 2 == 0 else 0.27) * rng.uniform(0.8, 1.15)
            v *= {"morning": 0.75, "groove": 1.0, "full": 1.1, "evening": 0.75}[lvl] * thin
            if lvl == "morning":
                v *= 0.6 + 0.4 * min(1.0, (at - seg_start["morning"]) / BAR)       # eases in over a bar
            if lvl != "evening" or step % 4 == 2 or rng.random() < keep:
                E.place(drums, E.pan(shaker(E, v), 0.35), E.hum(t_, 4))
    for c, _ in chords:                                       # a chord change off the bar line gets its own kick
        if level_at(c) in KICK_PAT and (c / BAR) % 1 > 1e-3 and not any(abs(k - c) < 0.05 for k in kicks):
            kicks.append(c); E.place(drums, kick(E, 0.62), c)
    if first_groove is not None and first_groove > BEAT:      # a brush swell into the first groove
        sw_ = swish(E, BEAT, 1500, 5000, peak=0.92, width=0.7, pan_path=(-0.3, 0.2))
        E.place(drums, sw_, first_groove - BEAT, 0.16)

    # ---------------------------------------------------- the moments
    # dawn: two chimes as the reactor wakes
    t1 = H.get("title", 0.3); t2 = H.get("sub", t1 + BEAT)
    for at, m, v, p in ((t1, 81, 0.34, -0.25), (t2, 88, 0.28, 0.25)):
        E.place(fx, E.pan(bell(E, mtof(m), 2.4, v, ratio=3.5, index=0.5, decay=1.3), p), at)
    # drift ("YouTube can wait."): a playful falling third on a soft mallet, the second note scooped
    if "drift" in H:
        hi_ = tones_in(chord_at(H["drift"]), 79, 91)
        a_, b_ = hi_[-1], hi_[-2]
        E.place(fx, E.pan(mallet(E, mtof(a_), 0.5, 0.45), 0.3), H["drift"])
        E.place(fx, E.pan(mallet(E, mtof(b_), 0.8, 0.5, scoop=0.6), 0.3), H["drift"] + 2 * S16 + SW)
    # approve: a gentle rising fourth that lands on the chord's root
    if "approve" in H:
        root = [m for m in range(84, 96) if m % 12 == CH[chord_at(H["approve"])][0]][0]
        for dt, m, v in ((0.0, root - 5, 0.3), (0.09, root, 0.38)):
            E.place(fx, E.pan(bell(E, mtof(m), 1.8, v, ratio=2.0, index=0.45, decay=0.8), 0.05), H["approve"] + dt)
    # ring / ring2: a soft vibraphone arpeggio from the chord, the answer a step higher
    for k_, r_ in enumerate(("ring", "ring2")):
        if r_ in H:
            tn = tones_in(chord_at(H[r_]), 74, 90)
            for j, m in enumerate(tn[k_:k_ + 3]):
                E.place(fx, E.pan(vibes(E, mtof(m), 1.4, 0.36 - 0.03 * j), -0.2 + 0.2 * j), H[r_] + j * 0.075)
    # erase: a soft downward swish and a sagging, detuned bell
    if "erase" in H:
        E.place(fx, swish(E, 0.5, 5500, 700, peak=0.25, width=0.6, pan_path=(0.4, -0.4)), H["erase"] - 0.12, 0.10)
        top = tones_in(chord_at(H["erase"]), 76, 88)[-1]
        E.place(fx, sag_bell(E, mtof(top), 1.0, 0.2), H["erase"])
    # standby press: a low soft thump
    if "press" in H:
        E.place(fx, E.pan(thump(E, 0.55), 0), H["press"])
        kicks.append(H["press"])
    # end card: one bell per line, rising A - C - E, then F on the wordmark
    for k_, (h, m) in enumerate((("e1", 81), ("e2", 84), ("e3", 88))):
        if h in H:
            E.place(fx, E.pan(bell(E, mtof(m), 2.2, 0.3, ratio=3.5, index=0.5, decay=1.1), -0.25 + 0.25 * k_), H[h])
    if "word" in H:
        E.place(fx, E.pan(bell(E, mtof(89), 2.5, 0.32, ratio=3.5, index=0.5, decay=1.2), 0.0), word)
        E.place(fx, E.pan(bell(E, mtof(77), 2.5, 0.2, ratio=2.0, index=0.3, decay=1.2), 0.0), word + 0.012)

    # ---------------------------------------------------- mix
    seg_list = levels + [(dur, None)]
    arc_pts, pad_pts, tone_pts = [], [], []
    for k, (a, lv) in enumerate(levels):
        b = seg_list[k + 1][0]
        e = 0.06 if k else 0.0
        arc_pts += [(a + e, ARC[lv][0]), (b - 0.06, ARC[lv][1])]
        pad_pts += [(a + e, PAD_DB[lv]), (b - 0.06, PAD_DB[lv])]
        tone_pts += [(a + e, TONE[lv][0]), (b - 0.06, TONE[lv][1])]
    if "night" in seg_start and "end" in seg_start:           # the quiet pad swells into the end chord
        pad_pts = [p for p in pad_pts if not (end_at - 1.2 < p[0] < end_at + 0.1)]
        pad_pts += [(end_at - 1.2, PAD_DB["night"]), (end_at - 0.02, PAD_DB["night"] + 4)]
    arc, padg, tone = curve(arc_pts), curve(pad_pts), curve(tone_pts)

    # gentle sidechain: the soft kick makes a little room for the bass and pad
    pump = np.zeros(N)
    for kt in kicks:
        i = int(kt * SR); m = min(N - i, int(0.3 * SR))
        if m > 0:
            tt = E.t_axis(m)
            pump[i:i + m] = np.maximum(pump[i:i + m], np.minimum(1, tt / 0.006) * np.exp(-tt / 0.12))
    padb *= (1 - 0.18 * pump) * dbg(padg(ta))
    bass *= 1 - 0.3 * pump

    # electric-piano tremolo (auto-pan at 8th-note triplets) and a little tape wow on keys and pad
    trem = 0.16 * np.sin(2 * np.pi * (3 / (2 * BEAT)) * ta)
    ep = np.vstack([ep[0] * (1 + trem), ep[1] * (1 - trem)])
    def wow(x, depth_ms):
        d = (1.5 + depth_ms * np.sin(2 * np.pi * 0.45 * ta) + 0.04 * np.sin(2 * np.pi * 5.3 * ta)) / 1000 * SR
        return np.vstack([np.interp(np.arange(N) - d, np.arange(N), c) for c in x])
    ep, padb = wow(ep, 0.25), wow(padb, 0.35)
    bass = np.vstack([E.fft_band(c, None, 420) for c in bass])

    # the stop on `asleep`: drums and bass fade out over 70 ms (no new notes start after it)
    if stop_at < dur and "night" in seg_start:
        g = rel_env(ta, stop_at - 0.03, 0.07)
        drums *= g; bass *= g
    bass = bass + bass_home
    drum_send = drums

    # the day's light: brighter through the morning, darker through the evening (keys, pad, drums)
    music = ep * 0.9 + padb * 0.55 + drums * 0.85
    music = E.stft_filter(music, E.lp(tone, 2))

    g_arc = dbg(arc(ta))
    dry = (music + bass * 0.48 + fx * 0.9) * g_arc
    send = (ep * 0.22 + padb * 0.3 + drum_send * 0.05 + fx * 0.4) * g_arc
    send = np.vstack([E.fft_band(c, 200, 7000) for c in send])
    wet = E.conv(send, E.make_ir(seed=11))
    mix = dry + 0.42 * wet

    # low end mono below 120 Hz, clean below 30 Hz, soft roll-off above ~13 kHz
    f = np.fft.rfftfreq(N, 1 / SR) + 1e-3
    M, S = (mix[0] + mix[1]) / 2, (mix[0] - mix[1]) / 2
    Mf, Sf = np.fft.rfft(M), np.fft.rfft(S)
    hi = 1 / (1 + (f / 13000) ** 4)
    Mf *= (1 / (1 + (30 / f) ** 4)) * (0.8 + 0.2 / (1 + (100 / f) ** 2)) * hi
    Sf *= (1 / (1 + (120 / f) ** 4)) * hi
    mix = np.vstack([np.fft.irfft(Mf, N) + np.fft.irfft(Sf, N), np.fft.irfft(Mf, N) - np.fft.irfft(Sf, N)])

    mix = E.compress(mix, -16, 1.8, 0.012, 0.25)             # light glue
    mix = np.tanh(1.2 * mix / np.abs(mix).max()) / np.tanh(1.2)  # a touch of tape warmth
    return mix, dict(chords=chords, levels=levels, stop=stop_at, end=end_at, word=word)


# ============================================================ master
def tp_detect(x, os_=4):
    nf = 1 << (x.shape[1] - 1).bit_length()
    up = np.fft.irfft(np.fft.rfft(x, nf, axis=1), nf * os_, axis=1)[:, :x.shape[1] * os_] * os_
    return np.abs(up).max(0).reshape(-1, os_).max(1)

def limit(x, ceiling_db=-1.5, look=0.002, rel=0.08):
    N = x.shape[1]
    greq = np.minimum(1, dbg(ceiling_db) / (tp_detect(x) + 1e-12))
    W = int(look * SR)
    g1 = np.lib.stride_tricks.sliding_window_view(np.concatenate([greq, np.ones(W)]), W + 1).min(1)[:N]
    B = 48; nb = N // B + 1
    gb = np.concatenate([g1, np.ones(nb * B - N)]).reshape(nb, B).min(1)
    out = np.empty(nb); g = 1.0; step = 1 - np.exp(-B / SR / rel)
    for i, v in enumerate(gb):
        g = v if v < g else min(v, g + (1 - g) * step)
        out[i] = g
    g2 = np.minimum(np.repeat(out, B)[:N], g1)
    g3 = np.convolve(np.concatenate([np.ones(W), g2]), np.ones(W) / W, mode="valid")[:N]   # <= required gain
    return x * g3, g3

def ebur128(x):
    raw = x.T.astype("<f4").tobytes()
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                          "-af", "ebur128=peak=true", "-f", "null", "-"], input=raw, capture_output=True).stderr.decode()
    tail = err[err.rindex("Summary:"):]
    return (float(tail.split("I:")[1].split("LUFS")[0]), float(tail.split("Peak:")[1].split("dBFS")[0]),
            float(tail.split("LRA:")[1].split("LU")[0]))

def master(mix, fade, edge=0.004):
    """Limit, fade to real silence (`fade` = (start, end) in s; digital zero after end), hit -14 LUFS."""
    x = mix / np.abs(mix).max()
    gain = 1.0
    for _ in range(8):
        y, gr = limit(x * gain)
        r = int(edge * SR)
        y[:, :r] *= np.linspace(0, 1, r)
        a = int(fade[0] * SR); b = int(fade[1] * SR)
        y[:, a:b] *= np.cos(np.linspace(0, np.pi / 2, b - a)) ** 2
        y[:, b:] = 0
        I, TP, LRA = ebur128(y)
        if abs(I + 14) < 0.05 and TP <= -1.0:
            break
        gain *= dbg(-14 - I)
    return y, (I, TP, LRA, 20 * np.log10(gr.min()))

def write(y, mp3_path):
    pcm = (np.clip(y.T, -1, 1) * 32767).round().astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-codec:a", "libmp3lame", "-b:a", "320k", "-ar", str(SR), mp3_path], input=pcm, check=True)

def audio_data(y, dur, path):
    """Per-frame envelopes, 0-1: `low` (everything under ~160 Hz: kick, bass, the press thump;
    smoothed with a 150 ms release so the glow breathes rather than flickers) and `rms`."""
    N = y.shape[1]
    m = y.mean(0)
    f = np.fft.rfftfreq(N, 1 / SR) + 1e-3
    low = np.fft.irfft(np.fft.rfft(m) / (1 + (f / 160) ** 4), N)
    frames = int(round(dur * FPS)); hop = SR // FPS
    def env(x, release=None):
        v = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) for i in range(frames)])
        if release:
            k = np.exp(-1 / (release * FPS)); s = 0.0
            for i in range(len(v)):
                s = max(v[i], s * k); v[i] = s
        return np.round(v / (np.percentile(v, 98) or 1), 3).clip(0, 1)
    lo, rm = env(low, 0.15), env(m)
    with open(path, "w") as fh:
        fh.write("window.AUDIO_DATA = " + json.dumps({"fps": FPS, "low": lo.tolist(), "rms": rm.tolist()},
                                                     separators=(",", ":")) + ";\n")


def main():
    os.makedirs(os.path.join(ASSETS, "music"), exist_ok=True)
    jobs = [("land", "timing.json", "score.mp3", "audio-data.js"),
            ("vert", "timing-vertical.json", "score-vertical.mp3", "audio-data-vertical.js")]
    for kind, tj, mp3, ad in jobs:
        with open(os.path.join(ASSETS, tj)) as fh:
            timing = json.load(fh)
        dur = float(timing["dur"])
        mix, info = render(timing, kind)
        silent = dur - 0.3                                     # the last 0.3 s is digital zero
        fade = (max(info["word"] + 0.35, silent - 1.3), silent)
        y, (I, TP, LRA, GR) = master(mix, fade)
        write(y, os.path.join(ASSETS, "music", mp3))
        audio_data(y, dur, os.path.join(ASSETS, ad))
        print(f"{mp3}: {dur:.2f} s  I={I:.1f} LUFS  TP={TP:.1f} dBTP  LRA={LRA:.1f} LU  limiter max GR={GR:.1f} dB")
        print("   chords: " + ", ".join(f"{t:.3f} {n}" for t, n in info["chords"]))
        print("   levels: " + ", ".join(f"{t:.3f} {n}" for t, n in info["levels"])
              + f"  | stop {info['stop']:.3f}  end {info['end']:.3f}  word {info['word']:.3f}  fade {fade[0]:.2f}-{fade[1]:.2f}")


if __name__ == "__main__":
    main()
