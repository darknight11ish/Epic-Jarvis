"""Original score for the Jarvis v4 launch video: landscape (30 s) and upright (15 s).

Run from the composition folder:   python3 tools/score.py

v2's energy, with v2's faults fixed. Driving 120 BPM trailer electronica in D minor:
four-on-the-floor kick, sidechained bass and pad, a Karplus-Strong 16th arp, punchy
hits on the cuts, risers into the big moments, braams on "YOUR RULES.". Unlike v2:
  - balance: the kick and bass sit at 50-75 Hz, not a 44 Hz sub wall;
  - hats are band-limited noise that rolls off above ~12 kHz, with played velocities;
  - timing jitter, swing, accents and a moving filter, so nothing is machine-flat;
  - every sound is synthesised here and peaks ON its hit (no late card-slide sample);
  - chords change on the picture cuts, not on a fixed bar clock.
The STOP ("ALT+SHIFT+X") works like v2's "STOP.": the music cuts 20 ms before the
stop frame, one dry key slam lands on the frame, then digital silence until stopEnd.

Deterministic: numpy + ffmpeg, fixed seeds. Reads assets/timing.json (landscape)
and assets/timing-vertical.json (upright). Writes:
  assets/music/score.mp3            assets/audio-data.js
  assets/music/score-vertical.mp3   assets/audio-data-vertical.js
Loudness: -14 LUFS integrated, true peak <= -1 dBTP (limiter ceiling -1.5 dBTP).
"""
import json, os, subprocess
import numpy as np

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
FPS = 30


# ============================================================ shared DSP
class Engine:
    def __init__(self, dur, seed):
        self.dur = float(dur)
        self.N = int(round(self.dur * SR))
        self.rng = np.random.default_rng(seed)

    # ---- basics
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
    def lp(fc_fun, order=2, res=0.0):
        def g(tc, f):
            fc = np.maximum(fc_fun(tc), 30)
            G = 1 / np.sqrt(1 + (f / fc) ** (2 * order))
            if res:
                G = G * (1 + res * np.exp(-(np.log2(f / fc) / 0.22) ** 2))
            return G
        return g

    @staticmethod
    def fftconv(x, ir):
        L = len(x) + len(ir) - 1
        nfft = 1 << (L - 1).bit_length()
        return np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[:len(x)]

    # ---- instruments
    def ks_pluck(self, f, dur, vel=0.6, bright=0.5):
        """Karplus-Strong string, vectorised per period, retuned by resampling (exact pitch)."""
        rng = self.rng
        a = 0.5 + 0.35 * bright
        P = max(8, int(np.floor(SR / f - (1 - a))))
        f0 = SR / (P + (1 - a))
        n_out = int(dur * SR)
        n = int(n_out * f / f0) + 2 * P + 4
        exc = rng.standard_normal(P)
        k = max(1, int(1 + 7 * (1 - vel * bright)))
        exc = np.convolve(exc, np.ones(k) / k, mode="same")
        exc -= np.roll(exc, int(P * rng.uniform(0.12, 0.22)))
        exc -= exc.mean()
        y = np.zeros(n)
        y[:P] = exc
        damp = 0.9985 - 0.002 * (f / 1000)
        for s in range(P, n, P):
            e = min(n, s + P)
            prev = y[s - P:e - P]
            prev1 = y[s - P - 1:e - P - 1] if s - P - 1 >= 0 else np.concatenate([[0.0], y[0:e - P - 1]])
            y[s:e] = damp * (a * prev + (1 - a) * prev1)
        out = np.interp(np.arange(n_out) * f / f0, np.arange(n), y)
        t = self.t_axis(n_out)
        body = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.05) * 0.4
        out = (out / (np.abs(out).max() + 1e-9) + body) * vel
        return out * np.clip((dur - t) / 0.04, 0, 1)

    def felt_piano(self, f, dur, vel=0.5, felt=0.75):
        """Stiff-string additive piano with a felt hammer: inharmonic partials, per-partial
        two-stage decay, two detuned strings per note, soft hammer noise, damper release."""
        rng = self.rng
        n = int(dur * SR); t = self.t_axis(n)
        m = 69 + 12 * np.log2(f / 440)
        B = 0.00025 * (1 + max(0, (m - 60)) / 24)
        out = np.zeros(n)
        K = int(min(16, 8000 // f))
        tone = 0.35 + 0.65 * vel * (1 - 0.6 * felt)
        for k in range(1, K + 1):
            fk = k * f * np.sqrt(1 + B * k * k)
            amp = (1 / k ** 1.2) * np.exp(-(k - 1) * (1.1 - tone))
            tau = (3.2 if f < 200 else 2.2) / (1 + 0.35 * k) * (1.2 - 0.4 * m / 100)
            for cents in (-0.9, 0.9):
                ph = rng.uniform(0, 2 * np.pi)
                out += amp * np.sin(2 * np.pi * fk * 2 ** (cents / 1200) * t + ph) * (
                    0.7 * np.exp(-t / tau) + 0.3 * np.exp(-t / (tau * 3.5)))
        hammer = np.convolve(rng.standard_normal(n), np.ones(24) / 24, mode="same") * np.exp(-t / 0.006) * 0.5
        out = out / (np.abs(out).max() + 1e-9) + hammer * vel
        env = np.minimum(1, t / 0.002) * np.clip((dur - t) / 0.15, 0, 1)
        return out * env * vel

    def bell(self, f, dur, vel=0.4, ratio=2.0, index=0.7, decay=0.9):
        """A soft FM glass note (low index: round, not clangy)."""
        n = int(dur * SR); t = self.t_axis(n)
        mod = np.sin(2 * np.pi * f * ratio * t) * index * np.exp(-t / 0.15)
        car = np.sin(2 * np.pi * f * t + mod) * np.exp(-t / decay)
        env = np.minimum(1, t / 0.003) * np.clip((dur - t) / 0.05, 0, 1)
        return car * env * vel * 0.5

    def blep_saw(self, freq):
        dt = freq / SR
        ph = (np.cumsum(dt) + self.rng.uniform()) % 1.0
        y = 2 * ph - 1
        m1 = ph < dt
        t1 = ph[m1] / dt[m1]; y[m1] -= t1 + t1 - t1 * t1 - 1
        m2 = ph > 1 - dt
        t2 = (ph[m2] - 1) / dt[m2]; y[m2] -= t2 * t2 + t2 + t2 + 1
        return y

    def supersaw(self, freqs, dur, att=0.4, rel=0.8, voices=(-15, -8, -3, 0, 4, 9, 14)):
        """Detuned PolyBLEP saws; each voice drifts on its own slow LFO; voices spread L/R."""
        rng = self.rng
        n = int(dur * SR); t = self.t_axis(n)
        out = np.zeros((2, n))
        for f in freqs:
            for vi, c in enumerate(voices):
                drift = 1 + 0.0012 * np.sin(2 * np.pi * rng.uniform(0.07, 0.23) * t + rng.uniform(0, 6.3))
                s = self.blep_saw(f * 2 ** (c / 1200) * drift) * rng.uniform(0.7, 1.0)
                out += self.pan(s, (vi / (len(voices) - 1)) * 1.6 - 0.8)
        env = np.minimum(1, t / att) * np.clip((dur - t) / rel, 0, 1)
        return out * env / (len(freqs) * len(voices)) * 2.5

    def heartbeat(self, vel=0.4):
        """A soft felt kick: low-mid body (~65 Hz), no click, short - a pulse, not a bang."""
        n = int(SR * 0.5); t = self.t_axis(n)
        f = 62 + 45 * np.exp(-t / 0.03)
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)
        felt = self.fft_band(self.rng.standard_normal(n), 150, 900) * np.exp(-t / 0.01) * 0.15
        return np.tanh(1.2 * (body + felt)) * vel * np.clip((t[-1] - t) / 0.05, 0, 1)

    def swish(self, dur, f_lo, f_hi, peak=0.85, width=0.55, pan_path=(0, 0)):
        """Filtered-noise air swish; the moving band and the envelope peak at `peak` (0..1)."""
        rng = self.rng
        n = int(dur * SR); t = self.t_axis(n); u = t / dur
        x = np.vstack([rng.standard_normal(n), rng.standard_normal(n)])
        ctr = lambda tc: f_lo * (f_hi / f_lo) ** np.clip(tc / dur / peak, 0, 1)
        x = self.stft_filter(x, lambda tc, f: np.exp(-(np.log2(f / ctr(tc)) / width) ** 2), n=1024, hop=256)
        env = np.where(u < peak, (u / peak) ** 2, np.exp(-(u - peak) * dur / 0.07))
        p = np.interp(u, [0, 1], pan_path)
        a = (p + 1) * np.pi / 4
        return np.vstack([x[0] * np.cos(a), x[1] * np.sin(a)]) * env

    def click(self, vel=0.5):
        """A tiny touch click: 3 ms of band-passed noise plus a 2.2 kHz blip."""
        n = int(SR * 0.03); t = self.t_axis(n)
        nz = self.fft_band(self.rng.standard_normal(n), 1800, 7000) * np.exp(-t / 0.0012)
        blip = np.sin(2 * np.pi * 2200 * t) * np.exp(-t / 0.004) * 0.5
        return (nz * 0.6 + blip) * vel * np.clip((t[-1] - t) / 0.005, 0, 1)

    def thud(self, vel=0.6):
        """Fingerprint touch: a soft low thud like a phone's haptic buzz (95 -> 70 Hz, 90 ms)."""
        n = int(SR * 0.25); t = self.t_axis(n)
        f = 70 + 25 * np.exp(-t / 0.02)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.045)
        s += 0.25 * np.sin(4 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.02)    # a little 2nd harmonic: audible on phones
        return s * np.minimum(1, t / 0.002) * vel

    def sag(self, f, dur=0.9, vel=0.3):
        """A note set aside: pitch sags two semitones like tape slowing, and fades."""
        n = int(dur * SR); t = self.t_axis(n)
        ff = f * 2 ** (-2 * (t / dur) ** 1.5 / 12)
        ph = 2 * np.pi * np.cumsum(ff) / SR
        s = (np.sin(ph) + 0.25 * np.sin(2 * ph)) * np.exp(-t / 0.35) * np.minimum(1, t / 0.004)
        return s * vel

    # ---- rooms and dynamics
    def make_ir(self, rt=(2.4, 1.8, 0.8), length=3.0, predelay=0.02, taps=14, seed=0):
        """Stereo hall: sparse early reflections + a diffuse tail whose highs die first."""
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




# ============================================================ harmony: D minor, trailer voicings
# name: (bass midi, upper voicing)
CH = {
    "Dm": (38, [57, 62, 65, 69]),     # A D F A over D
    "Bb": (34, [58, 62, 65, 70]),     # Bb D F Bb over Bb
    "F":  (41, [57, 60, 65, 69]),     # A C F A over F: the "yes" chord
    "C":  (36, [55, 60, 64, 67]),     # G C E G over C
    "Gm": (31, [55, 58, 62, 67]),     # G Bb D G over G
    "A":  (33, [57, 61, 64, 69]),     # A C# E A over A: harmonic-minor tension before the outro
}

def arp_tones(name):
    b, up = CH[name]
    return sorted(set([u + 12 for u in up] + [u + 24 for u in up[:2]]))


# ============================================================ trailer instruments (all synthesised)
def kick(E, vel=0.9):
    """Punchy kick: 56 Hz body (not a 44 Hz sub), pitch sweep, band-limited click, soft clip."""
    n = int(SR * 0.45); t = E.t_axis(n)
    f = 56 + (95 + 40 * vel) * np.exp(-t / 0.028)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.2)
    click = E.fft_band(E.rng.standard_normal(n), 1500, 7000) * np.exp(-t / 0.0022) * 0.55 * vel
    return np.tanh(1.8 * (body + click)) * vel * np.clip((t[-1] - t) / 0.06, 0, 1)

def hat(E, vel=0.5, open_=False):
    """Band-limited noise hat (4.8-10 kHz, rolls off above), varied colour, decay tied to velocity."""
    n = int(SR * (0.2 if open_ else 0.07)); t = E.t_axis(n)
    c = E.rng.uniform(0.92, 1.08)
    x = E.fft_band(E.rng.standard_normal(n), 4800 * c, 10000 * c)
    x *= np.minimum(1, t / E.rng.uniform(0.001, 0.003)) * np.exp(-t / ((0.07 if open_ else 0.013) * (0.7 + 0.6 * vel)))
    return x * vel * 0.42 * np.clip((t[-1] - t) / 0.01, 0, 1)

def clap(E, vel=0.7):
    n = int(SR * 0.35); t = E.t_axis(n)
    x = np.zeros(n); at = 0.0
    for k in range(4):                                    # four hands, never evenly spaced
        i = int(at * SR)
        x[i:] += E.rng.standard_normal(n - i) * np.exp(-t[:n - i] / (0.006 if k < 3 else 0.08)) * (0.8 if k < 3 else 1)
        at += E.rng.uniform(0.007, 0.013)
    return E.fft_band(x, 900, 5500) * vel * 0.5 * np.clip((t[-1] - t) / 0.05, 0, 1)

def impact(E, vel=0.8, size=1.0):
    """A trailer hit: pitched-down thump (115 -> 55 Hz, never a sub rumble), a knock, a noise burst."""
    n = int(SR * (0.9 + 0.5 * size)); t = E.t_axis(n)
    f = 55 + 60 * E.rng.uniform(0.85, 1.15) * np.exp(-t / (0.09 * size))
    drop = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.26 * size))
    knock = np.sin(2 * np.pi * 170 * E.rng.uniform(0.9, 1.1) * t) * np.exp(-t / 0.03) * 0.5
    burst = E.fft_band(E.rng.standard_normal(n), 150, 3200) * np.exp(-t / (0.05 + 0.03 * size)) * 1.2
    s = np.tanh(1.5 * (drop + knock + burst)) * np.minimum(1, t / 0.0015)
    return s * vel * np.clip((t[-1] - t) / 0.1, 0, 1)

def braam(E, root_m, dur, vel=1.0):
    """Root-fifth-octave supersaw stack with a filter that bites open then closes, plus the root sine."""
    st = E.supersaw([mtof(root_m), mtof(root_m + 7), mtof(root_m + 12), mtof(root_m + 19)], dur, att=0.012, rel=0.5)
    st = E.stft_filter(st, E.lp(lambda tc: 180 + 2600 * np.clip(tc / 0.06, 0, 1) * np.exp(-np.maximum(tc, 0) / 0.6), 3, 1.2),
                       n=1024, hop=256)
    t = E.t_axis(st.shape[1])
    sub = np.sin(2 * np.pi * mtof(root_m) * t) * np.exp(-t / 1.0) * np.minimum(1, t / 0.01) * 0.6
    return np.tanh(1.7 * (st * 1.6 + sub)) * np.clip((dur - t) / 0.4, 0, 1) * vel

def riser(E, dur, vel=0.5):
    """Noise band rising ~5 octaves plus a quiet gliding tone; ends exactly at `dur`."""
    x = E.swish(dur, 300, 9000, peak=0.995, width=0.75, pan_path=(-0.6, 0.6))
    t = E.t_axis(x.shape[1]); u = t / dur
    tone = np.sin(2 * np.pi * np.cumsum(220 * 8 ** u) / SR) * u ** 3 * 0.25
    return (x + tone) * vel

def ring(E, lo=81, hi=84, dur=0.38, vel=0.35):
    """A phone-alarm pulse in key: a fast two-note trill (A5 / C6) with a 20 Hz buzz."""
    n = int(dur * SR); t = E.t_axis(n)
    sel = (np.sin(2 * np.pi * 16 * t) > 0).astype(float)
    sel = np.convolve(sel, np.ones(96) / 96, mode="same")
    f = mtof(lo) * (1 - sel) + mtof(hi) * sel
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph + 0.8 * np.sin(2 * ph)) * (0.75 + 0.25 * np.sin(2 * np.pi * 20 * t))
    return s * np.minimum(1, t / 0.004) * np.clip((dur - t) / 0.03, 0, 1) * vel

def key_slam(E, vel=1.0, length=0.055):
    """ALT+SHIFT+X hit together: three plastic key clacks 5-8 ms apart and one desk thock, dry, short."""
    n = int(length * SR); t = E.t_axis(n)
    s = np.zeros(n); at = 0.0
    for k in range(3):
        i = int(at * SR); m = n - i; tt = t[:m]
        clack = E.fft_band(E.rng.standard_normal(m), 1200, 7500) * np.exp(-tt / 0.003)
        body = np.sin(2 * np.pi * E.rng.uniform(380, 520) * tt) * np.exp(-tt / 0.012) * 0.6
        s[i:] += (clack + body) * E.rng.uniform(0.8, 1.0)
        at += E.rng.uniform(0.005, 0.008)
    thock = np.sin(2 * np.pi * np.cumsum(90 + 60 * np.exp(-t / 0.01)) / SR) * np.exp(-t / 0.03) * 1.2
    s = np.tanh(1.4 * (s + thock)) * np.minimum(1, t / 0.0008)
    s *= 0.5 + 0.5 * np.cos(np.pi * np.clip((t - (length - 0.012)) / 0.012, 0, 1))      # cosine tail to 0 at `length`
    return s * vel

def blip(E, vel=0.35):
    """The answer pops: two quick glassy notes, D6 then A6."""
    out = np.zeros(int(0.35 * SR))
    for j, m in enumerate((86, 93)):
        b = E.bell(mtof(m), 0.3, vel, ratio=2.0, index=0.6, decay=0.09)
        i = int(j * 0.045 * SR); out[i:i + len(b)] += b[:len(out) - i]
    return out

def erase(E, vel=0.3):
    """Erase: a band of noise sweeping DOWN and away, with a note that sags."""
    x = E.swish(0.4, 7000, 500, peak=0.12, width=0.6, pan_path=(0.5, -0.5))
    s = E.sag(mtof(81), 0.4, 0.5)
    return (x + np.vstack([s, s]) * 0.5) * vel

def lock(E, vel=0.5):
    """A latch closing: two small clicks 35 ms apart over a low thud."""
    out = np.zeros(int(0.3 * SR))
    for at, v in ((0.0, 0.6), (0.035, 1.0)):
        c = E.click(v); i = int(at * SR); out[i:i + len(c)] += c
    th = E.thud(0.7); out[:len(th)] += th[:len(out)]
    return out * vel


# ============================================================ one render
def render(timing, kind):
    H = timing["hits"]
    dur = float(timing["dur"])
    EXT = 2.0 if kind == "vert" else 0.0              # upright: render past the end and wrap it (seamless loop)
    E = Engine(dur + EXT, seed=20260926 if kind == "land" else 20260927)
    rng, N = E.rng, E.N
    NO = int(round(dur * SR))
    ta = E.t_axis(N)
    BEAT = 60.0 / timing["bpm"]; S16 = BEAT / 4; S8 = BEAT / 2
    STOP, STOP_END = H["stop"], H["stopEnd"]
    drums, bass, keys, pads, fx, ui, slam, hall_extra = (E.bus() for _ in range(8))
    kicks = []

    if kind == "land":
        CHANGES = [(0.0, "Dm"), (H["local"], "Bb"), (H["focus"], "F"), (H["distract"], "C"), (H["report"], "Dm"),
                   (H["tell"], "Bb"), (H["tellOk"], "F"), (STOP_END, "Dm"), (H["asks"], "Bb"), (H["hello"], "Gm"),
                   (H["ok"], "F"), (H["instant"], "C"), (H["learn"], "Dm"), (H["erase"], "Bb"), (H["sensitive"], "A"),
                   (H["outro"], "Bb"), (H["pc"], "C"), (H["rules"], "Dm")]
        # groove level: 0 none, 1 bass + hats, 2 + kick + arp 8ths, 3 + clap + arp 16ths, 4 the drop
        LEVEL = [(0.0, 0), (H["edge"], 1), (H["local"], 2), (H["focus"], 3), (H["distract"], 1), (H["report"], 3),
                 (STOP_END, 4), (H["asks"], 3), (H["hello"], 2), (H["ok"], 3), (H["instant"], 1), (H["answer"], 3),
                 (H["sensitive"], 2), (H["outro"], 0)]
        HITS = [("edge", 1.0, 1.2), ("local", 0.55, 0.8), ("focus", 0.6, 0.8), ("report", 0.85, 1.0),
                ("tell", 0.55, 0.8), ("stopEnd", 1.0, 1.3), ("asks", 0.5, 0.8), ("asksLine", 0.85, 1.0),
                ("ok", 0.55, 0.8), ("learn", 0.55, 0.8), ("outro", 0.75, 1.0), ("o1", 0.7, 0.9),
                ("pc", 0.8, 1.0), ("rules", 1.0, 1.4), ("logo", 0.7, 1.1)]
        RISERS = [(0.0, H["edge"], 0.5), (H["asks"] - 0.7, H["asks"], 0.25), (H["outro"] - 1.0, H["outro"], 0.45)]
        pad_fc = curve([(0, 400), (H["edge"], 900), (H["local"], 1200), (H["focus"], 2000), (H["distract"], 700),
                        (H["report"], 2200), (STOP, 2800), (STOP_END, 3500), (H["hello"], 1400), (H["ok"], 2600),
                        (H["instant"], 450), (H["answer"], 2400), (H["sensitive"], 1600), (H["outro"], 2600),
                        (H["rules"], 3500), (H["logo"], 1500), (dur, 700)])
        arc = curve([(0, -7), (H["edge"] - 0.01, -4), (H["edge"], 0), (H["local"], -2.5), (H["focus"] - 0.01, -1.5),
                     (H["focus"], 0), (H["distract"], -3), (H["report"] - 0.01, -3), (H["report"], 0), (H["tell"], -0.5),
                     (STOP, 0), (STOP_END, 2), (H["asks"] - 0.01, 1), (H["asks"], 0), (H["hello"], -1.5),
                     (H["ok"] - 0.01, -1.5), (H["ok"], 0), (H["instant"], -4.5), (H["answer"] - 0.01, -4.5),
                     (H["answer"], -0.5), (H["learn"], 0), (H["sensitive"], -1.5), (H["outro"], 0.5), (H["rules"] - 0.01, 1),
                     (H["rules"], 3), (H["logo"], 0), (dur, -4)])
    else:
        CHANGES = [(0.0, "Dm"), (H["focus"], "F"), (H["distract"], "C"), (H["report"], "Dm"), (H["tell"], "Bb"),
                   (H["tellOk"], "F"), (STOP_END, "Dm"), (H["asks"], "Bb"), (H["ok"], "F"), (H["outro"], "Bb"),
                   (H["pc"], "C"), (H["rules"], "Dm")]
        LEVEL = [(0.0, 0), (H["edge"], 2), (H["focus"], 3), (H["distract"], 1), (H["report"], 3), (STOP_END, 4),
                 (H["asks"], 3), (H["finger"], 2), (H["ok"], 3), (H["outro"], 0)]
        HITS = [("edge", 1.0, 1.2), ("focus", 0.55, 0.8), ("report", 0.85, 1.0), ("tell", 0.55, 0.8),
                ("stopEnd", 1.0, 1.3), ("asksLine", 0.85, 1.0), ("ok", 0.55, 0.8), ("outro", 0.7, 0.9),
                ("o1", 0.65, 0.9), ("pc", 0.8, 1.0), ("rules", 1.0, 1.4), ("logo", 0.6, 1.0)]
        # the loop: a riser across the end, wrapping into the next play's "edge" slam at 0.2 s
        RISERS = [(dur - 0.7, dur + H["edge"], 0.45), (H["asks"] - 0.6, H["asks"], 0.25)]
        pad_fc = curve([(0, 1200), (H["edge"], 1500), (H["focus"], 2000), (H["distract"], 700), (H["report"], 2200),
                        (STOP, 2800), (STOP_END, 3500), (H["finger"], 1500), (H["ok"], 2600), (H["outro"], 2600),
                        (H["rules"], 3500), (H["logo"], 1800), (dur, 1200), (dur + EXT, 1500)])
        arc = curve([(0, -2), (H["edge"] - 0.01, -2), (H["edge"], 0), (H["distract"], -3), (H["report"] - 0.01, -3),
                     (H["report"], 0), (STOP, 0), (STOP_END, 2), (H["asks"] - 0.01, 1), (H["asks"], 0),
                     (H["finger"], -1.5), (H["ok"] - 0.01, -1.5), (H["ok"], 0), (H["outro"], 0.5), (H["rules"] - 0.01, 1),
                     (H["rules"], 3), (H["logo"], 0.5), (dur, -2), (dur + EXT, -2)])

    def chord_at(t):
        name = CHANGES[0][1]
        for at, c in CHANGES:
            if t >= at - 1e-6:
                name = c
        return name

    def level_at(t):
        v = LEVEL[0][1]
        for at, l in LEVEL:
            if t >= at - 1e-6:
                v = l
        if kind == "vert" and t >= dur:
            return 0                                            # past the end only tails ring on (they wrap to the start)
        return v

    in_stop = lambda t: STOP - 0.03 <= t < STOP_END

    # ---------------------------------------------------- pad: one supersaw segment per chord, moving filter
    for k, (at, name) in enumerate(CHANGES):
        end = CHANGES[k + 1][0] if k + 1 < len(CHANGES) else dur
        # upright loop: the first chord fades in over exactly the 0.5 s the last one fades out (wrapped on top)
        att = (0.5 if kind == "vert" else 0.03) if at == 0 else 0.12
        seg = E.supersaw([mtof(m) for m in CH[name][1]], end - at + 0.5, att=att, rel=0.5)
        E.place(pads, seg, max(0.0, at - 0.02))
    lfo = lambda tc: 1 + 0.2 * np.sin(2 * np.pi * tc / 2.0)             # one-bar wah on the cutoff
    pads = E.stft_filter(pads, E.lp(lambda tc: pad_fc(tc) * lfo(tc), 2, 0.7))

    # ---------------------------------------------------- bass: D2-register 8ths, re-articulated, a little saw grit
    f_step = np.zeros(N)
    for at, name in CHANGES:
        r = CH[name][0]
        f_step[int(at * SR):] = mtof(r if r >= 36 else r + 12)       # C2..G2: 65-117 Hz fundamentals, no sub wall
    kk = int(0.02 * SR)
    f_line = np.convolve(np.pad(f_step, kk, mode="edge"), np.ones(kk) / kk, mode="same")[kk:-kk]
    lv = np.array([level_at(t) for t in np.arange(0, N) [::480] / SR])
    g_line = np.repeat(np.where(lv >= 1, np.where(lv >= 3, 0.5, 0.4), 0.0), 480)[:N]
    g_line = np.convolve(np.pad(g_line, 480, mode="edge"), np.ones(480) / 480, mode="same")[480:-480]
    art = np.zeros(N)
    for i in range(int((dur + EXT) / S8) + 1):
        a0 = max(0.0, E.hum(i * S8, 2.5)); i0 = int(a0 * SR); m = min(N - i0, int(S8 * SR))
        if m > 0:
            acc = 1.0 if i % 2 == 0 else rng.uniform(0.7, 0.9)
            art[i0:i0 + m] = np.maximum(art[i0:i0 + m], acc * np.exp(-E.t_axis(m) / 0.11))
    art = np.convolve(art, np.ones(144) / 144, mode="same")
    ph = 2 * np.pi * np.cumsum(f_line) / SR
    grit = E.fft_band(E.blep_saw(f_line * 2), None, 900) * 0.25
    b = np.tanh(1.8 * (np.sin(ph) + grit)) * g_line * (0.3 + 0.7 * art)
    E.place(bass, b, 0.0)

    # ---------------------------------------------------- drums and arp on a swung, humanised 16th grid
    motif = [0, 2, 1, 3, 2, 4, 3, 1, 0, 3, 2, 4, 1, 3, 2, 5]
    for i in range(int((dur + EXT) / S16)):
        at = i * S16
        lvl = level_at(at)
        if lvl == 0 or in_stop(at):
            continue
        step = i % 16
        sw = 0.06 * 2 * S16 if step % 2 else 0.0                       # 53 % swing on the off 16ths
        # hats: 8ths at level 1, 16ths from 2, with an accent shape and random spread
        if step % 2 == 0 or lvl >= 2:
            v = (0.62 if step % 4 == 2 else 0.4 if step % 2 == 0 else 0.3) * rng.uniform(0.8, 1.15) * (0.8 + 0.1 * lvl)
            op = lvl >= 3 and step % 4 == 2
            E.place(drums, E.pan(hat(E, v, op), 0.3 if step % 2 else -0.2), E.hum(at + sw, 3))
        if lvl >= 2 and step % 4 == 0:
            kt = E.hum(at, 1.5); kicks.append(kt)
            E.place(drums, kick(E, 0.9 * rng.uniform(0.92, 1.0)), kt)
        if lvl >= 4 and step == 14 and rng.random() < 0.7:           # the drop gets a pickup kick
            kt = E.hum(at, 1.5); kicks.append(kt)
            E.place(drums, kick(E, 0.55), kt)
        if lvl >= 3 and step in (4, 12):
            E.place(drums, clap(E, rng.uniform(0.65, 0.8)), E.hum(at + 0.004, 2.5))
        # arp: 8ths at level 2, 16ths with a few rests from 3
        if lvl >= 2 and (step % 2 == 0 or (lvl >= 3 and rng.random() > 0.12)):
            tones = arp_tones(chord_at(at + 0.01))
            m = tones[(motif[step] + int(at // 2)) % len(tones)]
            vel = (0.5 if step % 4 == 0 else 0.4 if step % 2 == 0 else 0.3) * rng.uniform(0.85, 1.12) * (0.8 + 0.1 * lvl)
            E.place(keys, E.pan(E.ks_pluck(mtof(m), 0.5, vel, 0.45 + 0.1 * lvl), 0.45 * np.sin(2 * np.pi * at / 3.1)),
                    E.hum(at + sw, 4), 0.5)

    # ---------------------------------------------------- hits on the cuts, risers into the big ones
    for name, vel, size in HITS:
        at = H[name] + (0.020 if name == "stopEnd" else 0.0)     # the re-entry hit rides with the 20 ms resume lag
        E.place(fx, E.pan(impact(E, vel, size), 0), at)
        E.place(hall_extra, E.pan(impact(E, vel * 0.5, size), 0), at, 0.5)
    for a, b_, v in RISERS:
        E.place(fx, riser(E, b_ - a, v), a)
    # braams: one short one on "CUTTING-EDGE.", the big one (with the swell) on "YOUR RULES."
    E.place(fx, braam(E, 38, 1.6, 0.6), H["edge"])
    E.place(fx, braam(E, 38, 3.0 if kind == "land" else 2.4, 1.0), H["rules"])
    E.place(hall_extra, braam(E, 38, 2.4, 0.5), H["rules"])
    sw_at = H["o1"] if "o1" in H else H["outro"]
    E.place(pads, E.supersaw([mtof(m) for m in CH["Dm"][1]] + [mtof(50)], H["rules"] - sw_at + 0.4,
                             att=H["rules"] - sw_at, rel=0.4), sw_at, 0.9)       # the swell INTO the braam

    # ---------------------------------------------------- UI sounds, each peaking on its own hit
    def card_land(at, note, gain=1.0):
        E.place(ui, E.swish(0.3, 800, 6000, peak=0.9, width=0.55, pan_path=(-0.3, 0.2)), at - 0.27, 0.35 * gain)
        n_ = E.pan(E.bell(mtof(note), 1.0, 0.35 * gain), 0.1)
        E.place(ui, n_, at); E.place(hall_extra, n_, at, 0.4)

    def yes(at):                                            # two rising notes that land on the F chord
        for dt, m in ((0.0, 84), (0.07, 89)):
            n_ = E.pan(E.bell(mtof(m), 1.2, 0.35, ratio=2.0, index=0.6, decay=0.6), 0.0)
            E.place(ui, n_, at + dt); E.place(hall_extra, n_, at + dt, 0.4)

    if "focusCard" in H: card_land(H["focusCard"], 81)
    if "tellCard" in H: card_land(H["tellCard"], 82 if kind == "land" else 81)
    if "mailCard" in H: card_land(H["mailCard"], 81, 0.8)
    yes(H["tellOk"]); yes(H["ok"])
    for r_ in ("ring", "ring2"):
        E.place(ui, E.pan(ring(E), 0.15), H[r_])
    if "hello" in H:                                       # Windows Hello: a short rising scan shimmer
        E.place(ui, E.swish(0.45, 2000, 9000, peak=0.8, width=0.4, pan_path=(-0.4, 0.4)), H["hello"], 0.12)
    E.place(ui, E.thud(0.6), H["finger"])
    if "answer" in H: E.place(ui, E.pan(blip(E), 0.2), H["answer"])
    if "erase" in H: E.place(ui, erase(E), H["erase"])
    if "sensitive" in H: E.place(ui, lock(E), H["sensitive"])
    if "ready" in H:
        n_ = E.pan(E.ks_pluck(mtof(74), 1.2, 0.6, 0.7), 0.0); E.place(ui, n_, H["ready"])
    for j, m in enumerate((74, 81)):
        n_ = E.pan(E.bell(mtof(m), 2.2, 0.3, ratio=3.5, index=0.9, decay=1.2), -0.15 + 0.3 * j)
        E.place(ui, n_, H["logo"] + 0.03 * j); E.place(hall_extra, n_, H["logo"] + 0.03 * j, 0.6)

    # ---------------------------------------------------- STOP: the slam, alone and dry
    E.place(slam, E.pan(key_slam(E, 1.0), 0), STOP)
    slam_end = STOP + 0.055

    # ---------------------------------------------------- mix
    pump = np.zeros(N)
    for kt in kicks:
        i = int(kt * SR); m = min(N - i, int(0.4 * SR))
        if m > 0:
            tt = E.t_axis(m)
            pump[i:i + m] = np.maximum(pump[i:i + m], np.minimum(1, tt / 0.005) * np.exp(-tt / 0.16))
    pads *= 1 - 0.5 * pump; bass *= 1 - 0.55 * pump; keys *= 1 - 0.3 * pump

    # "instant": the model is asleep - the music is heard muffled until the answer pops
    if "instant" in H:
        wake = curve([(0, 60000), (H["instant"] - 0.01, 60000), (H["instant"] + 0.05, 500), (H["answer"] - 0.05, 700),
                      (H["answer"], 60000), (dur, 60000)])
        keys = E.stft_filter(keys, E.lp(wake, 3)); pads = E.stft_filter(pads, E.lp(wake, 3))

    def wow(x, depth_ms):
        d = (1.2 + depth_ms * np.sin(2 * np.pi * 0.5 * ta) + 0.05 * np.sin(2 * np.pi * 6.1 * ta)) / 1000 * SR
        return np.vstack([np.interp(np.arange(N) - d, np.arange(N), c) for c in x])
    keys, pads = wow(keys, 0.2), wow(pads, 0.35)

    drums = drums + 0.12 * E.conv(drums, E.make_ir((0.5, 0.4, 0.25), 0.6, 0.006, 20, seed=3))
    drums = drums + 0.3 * np.tanh(2.0 * E.compress(drums, -28, 6, 0.001, 0.08))       # parallel squash
    g_arc = dbg(arc(ta))
    dry = (drums * 0.75 + bass * 0.65 + keys * 0.95 + pads * 0.62 + fx * 0.85 + ui * 0.9) * g_arc
    send = (keys * 0.25 + pads * 0.25 + drums * 0.05 + fx * 0.15 + ui * 0.2) * g_arc + hall_extra * 0.5
    send = np.vstack([E.fft_band(c, 250, 8000) for c in send])

    # the music (and its reverb) stops 20 ms before the stop frame; only the dry slam plays on the frame
    STOP_LEAD, RAMP = 0.020, 0.008
    RESUME_LAG = 0.020     # the re-entry lands 20 ms after stopEnd (under a frame), so AAC pre-echo stays out of the gap
    e0 = int((STOP - STOP_LEAD) * SR); r = int(RAMP * SR); s1 = int((STOP_END + RESUME_LAG) * SR)
    gate = np.ones(N)
    gate[e0 - r:e0] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r))
    gate[e0:s1] = 0
    gate[s1:s1 + int(0.003 * SR)] = np.linspace(0, 1, int(0.003 * SR))
    # (s1 is already RESUME_LAG after stopEnd - see below)
    HALL = E.make_ir((2.2, 1.7, 0.8), 2.6, seed=11)
    pre, post = send * gate, send.copy()
    pre[:, e0:] = 0; post[:, :s1] = 0
    wet = E.conv(pre, HALL); wet[:, e0:] = 0
    wet += E.conv(post, HALL)
    mix = (dry + 0.45 * wet) * gate + slam * 0.9

    # low end mono below 120 Hz, a gentle shelf under 90 Hz, a little air
    f = np.fft.rfftfreq(N, 1 / SR) + 1e-3
    M, S = (mix[0] + mix[1]) / 2, (mix[0] - mix[1]) / 2
    Mf, Sf = np.fft.rfft(M), np.fft.rfft(S)
    Mf *= (1 / (1 + (30 / f) ** 4)) * (0.72 + 0.28 / (1 + (90 / f) ** 2)) * (1 + 0.4 / (1 + (8000 / f) ** 2))
    Sf *= (1 / (1 + (120 / f) ** 4)) * (1 + 0.25 / (1 + (2000 / f) ** 2))
    mix = np.vstack([np.fft.irfft(Mf, N) + np.fft.irfft(Sf, N), np.fft.irfft(Mf, N) - np.fft.irfft(Sf, N)])

    mix = E.compress(mix, -12, 1.5, 0.008, 0.2)            # light glue
    bias = 0.07
    mix = (np.tanh(1.35 * mix + bias) - np.tanh(bias)) / 1.35
    F = np.fft.rfft(mix, axis=1); F *= 1 / (1 + (18 / f) ** 4); mix = np.fft.irfft(F, N, axis=1)

    if kind == "vert":                                     # wrap the tail onto the start: a seamless loop
        tail = mix[:, NO:]
        mix = mix[:, :NO].copy(); mix[:, :tail.shape[1]] += tail
    gap0 = int(round((slam_end + 0.002) * SR))            # digital zero from just after the slam to stopEnd
    return E, mix, gap0, s1, dict(drums=drums[:, :NO], bass=bass[:, :NO])


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
    return x * g3

def ebur128(x):
    raw = x.T.astype("<f4").tobytes()
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                          "-af", "ebur128=peak=true", "-f", "null", "-"], input=raw, capture_output=True).stderr.decode()
    tail = err[err.rindex("Summary:"):]
    return (float(tail.split("I:")[1].split("LUFS")[0]), float(tail.split("Peak:")[1].split("dBFS")[0]),
            float(tail.split("LRA:")[1].split("LU")[0]))



def master(mix, g0, g1, fade_out=None, loop=False, edge=0.004):
    x = mix / np.abs(mix).max()
    gain = 1.0
    for _ in range(6):
        y = limit(x * gain)
        y[:, g0:g1] = 0                                     # the STOP gap is digital zero, after the limiter too
        r = int(edge * SR)
        if not loop:
            y[:, :r] *= np.linspace(0, 1, r)
        if fade_out:
            a = int(fade_out[0] * SR); b = int(fade_out[1] * SR)
            y[:, a:b] *= np.linspace(1, 0, b - a) ** 2
            y[:, b:] = 0
        I, TP, LRA = ebur128(y)
        if abs(I + 14) < 0.05 and TP <= -1.0:
            break
        gain *= dbg(-14 - I)
    return y, (I, TP, LRA)

def write(y, mp3_path):
    pcm = (np.clip(y.T, -1, 1) * 32767).round().astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-codec:a", "libmp3lame", "-b:a", "256k", "-ar", str(SR), mp3_path], input=pcm, check=True)

def audio_data(y, parts, dur, path, g0, g1):
    """Per-frame envelopes, 0-1: `low` (kick + bass + everything under 160 Hz; drives the glow) and `rms`."""
    N = y.shape[1]
    m = y.mean(0)
    f = np.fft.rfftfreq(N, 1 / SR) + 1e-3
    low = np.fft.irfft(np.fft.rfft(m) / (1 + (f / 160) ** 4), N)
    frames = int(round(dur * FPS)); hop = SR // FPS
    def env(x):
        v = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) for i in range(frames)])
        return np.round(v / (np.percentile(v, 98) or 1), 3).clip(0, 1)
    lo, rm = env(low), env(m)
    k0, k1 = int(np.ceil(g0 / hop)), int(g1 // hop)
    lo[k0:k1] = 0; rm[k0:k1] = 0
    with open(path, "w") as fh:
        fh.write("window.AUDIO_DATA = " + json.dumps({"fps": FPS, "low": lo.tolist(), "rms": rm.tolist()},
                                                     separators=(",", ":")) + ";\n")


def main():
    os.makedirs(os.path.join(ASSETS, "music"), exist_ok=True)
    jobs = [("land", "timing.json", "score.mp3", "audio-data.js"),
            ("vert", "timing-vertical.json", "score-vertical.mp3", "audio-data-vertical.js")]
    for kind, tj, mp3, ad in jobs:
        timing = json.load(open(os.path.join(ASSETS, tj)))
        dur = float(timing["dur"])
        E, mix, g0, g1, parts = render(timing, kind)
        fade = (dur - 0.7, dur) if kind == "land" else None      # landscape fades to black with the picture
        y, (I, TP, LRA) = master(mix, g0, g1, fade, loop=(kind == "vert"))
        write(y, os.path.join(ASSETS, "music", mp3))
        audio_data(y, parts, dur, os.path.join(ASSETS, ad), g0, g1)
        print(f"{mp3}: {dur:.1f} s  I={I:.1f} LUFS  TP={TP:.1f} dBTP  LRA={LRA:.1f} LU  "
              f"(silence {g0 / SR:.3f}-{g1 / SR:.3f} s)")


if __name__ == "__main__":
    main()
