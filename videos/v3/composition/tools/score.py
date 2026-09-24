"""Original score for the Jarvis v3 launch video: landscape (32 s) and upright (15 s).

Run from the composition folder:   python3 tools/score.py

Calm plucks and soft felt piano over a dark pad, D minor, 120 BPM. Chords change on
the picture cuts; every "yes" (Approve, Keep) resolves to F major. No risers, no
ticking, no bangs, no voices. The one "a little cinematic" moment is the deep swell
under the end line. On "Stop." every sound, reverb tails and room tone included,
stops dead until `resume`.

Everything is synthesised here (numpy + ffmpeg, fixed seeds), so a run is repeatable
and depends on nothing outside this folder. Reads:
  assets/timing.json            (landscape, 32 s)
  assets/timing-vertical.json   (upright, 15 s)
Writes:
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


# ============================================================ harmony: D minor, open voicings
# name: (bass midi, upper voicing)
CH = {
    "Dm9":  (38, [53, 57, 60, 64]),   # F A C E over D
    "Bb9":  (34, [50, 57, 62, 65]),   # D A D F over Bb (maj7 colour from the A)
    "F/A":  (33, [53, 60, 64, 67]),   # F C E G over A (Fmaj9, warm "yes")
    "Gm9":  (31, [50, 57, 58, 65]),   # D A Bb F over G
    "C9/E": (40, [55, 60, 62, 67]),   # G C D G over E (open, a question)
    "F":    (29, [53, 57, 60, 67]),   # F A C G over F (home, end line)
}

def arp_tones(name):
    b, up = CH[name]
    return sorted(set([u + 12 for u in up] + [u + 24 for u in up[1:3]]))


# ============================================================ one render
def render(timing, kind):
    H = timing["hits"]
    dur = float(timing["dur"])
    E = Engine(dur, seed=20260924 if kind == "land" else 20260915)
    rng, N = E.rng, E.N
    ta = E.t_axis(N)
    BEAT = 60.0 / timing["bpm"]; S8 = BEAT / 2
    STOP, RESUME = H["stop"], H["resume"]
    keys, pads, bass, beat, ui = E.bus(), E.bus(), E.bus(), E.bus(), E.bus()
    hall_extra = E.bus()

    YES = H["approved"] + 0.2          # the "✓ Approved" pill lands 0.2 s after `approved` (film.js p-done)
    if kind == "land":
        CHANGES = [(0.0, "Dm9"), (H["cards"], "Bb9"), (YES, "F/A"), (H["june"], "Gm9"), (H["sept"], "Bb9"),
                   (H["keep"], "F/A"), (H["drink"], "C9/E"), (H["reply"], "Dm9"), (H["outro"], "Bb9"),
                   (H["rules"], "F")]
        # arp density: 0 none, 1 quarters, 2 eighths, 3 eighths + ghosts, 4 sixteenths with rests
        DENS = [(0.0, 0), (H["cards"], 2), (H["tap"], 1), (YES, 2), (H["browser"], 1), (H["done"], 2),
                (H["june"], 2), (H["sept"], 3), (H["drink"], 4), (STOP, 0)]
        PULSE = [(H["june"], STOP)]
        pad_lvl = curve([(0, 0.32), (H["cards"], 0.5), (H["june"], 0.42), (H["sept"], 0.45), (H["drink"], 0.55),
                         (STOP, 0.55), (RESUME, 0.0), (H["outro"], 0.55), (H["rules"], 0.8), (H["logo"], 0.5), (dur, 0.3)])
        pad_fc = curve([(0, 520), (H["cards"], 900), (H["tap"], 750), (YES, 1300), (H["june"], 900),
                        (H["sept"], 1300), (H["drink"], 1700), (STOP, 2200),
                        (RESUME, 400), (H["outro"], 1500), (H["rules"], 2600), (H["logo"], 1100), (dur, 600)])
        bass_lvl = [(0.0, 0.0), (H["cards"], 0.22), (H["june"], 0.24), (H["drink"], 0.3),
                    (STOP, 0.0), (H["outro"], 0.18), (H["rules"], 0.34), (H["logo"], 0.2)]
    else:
        CHANGES = [(0.0, "Bb9"), (YES, "F/A"), (H["memory"], "Gm9"), (H["keep"], "F/A"),
                   (H["drink"], "C9/E"), (H["reply"], "Dm9"), (H["outro"], "Bb9"), (H["rules"], "Bb9")]
        DENS = [(0.0, 2), (H["tap"], 1), (YES, 2), (H["browser"], 1), (H["renewed"], 2), (H["memory"], 3),
                (H["drink"], 4), (STOP, 0),
                (H["rules"] + 0.5, 2)]                     # plucks come back so the loop runs on into frame 0
        PULSE = [(H["memory"], STOP)]
        pad_lvl = curve([(0, 0.5), (H["memory"], 0.48), (H["drink"], 0.55), (STOP, 0.55), (RESUME, 0.0),
                         (H["outro"], 0.5), (H["rules"], 0.75), (dur, 0.5)])
        pad_fc = curve([(0, 900), (H["tap"], 750), (YES, 1300), (H["memory"], 1300), (H["drink"], 1700),
                        (STOP, 2200), (RESUME, 400), (H["outro"], 1400), (H["rules"], 2400), (dur, 900)])
        bass_lvl = [(0.0, 0.22), (H["memory"], 0.26), (H["drink"], 0.3), (STOP, 0.0), (H["outro"], 0.16),
                    (H["rules"], 0.3), (H["rules"] + 0.8, 0.22)]

    def chord_at(t):
        name = CHANGES[0][1]
        for at, c in CHANGES:
            if t >= at - 1e-6:
                name = c
        return name

    def dens_at(t):
        d = DENS[0][1]
        for at, v in DENS:
            if t >= at - 1e-6:
                d = v
        return d

    # ---------------------------------------------------- pad: one segment per chord, cross-faded
    for k, (at, name) in enumerate(CHANGES):
        end = CHANGES[k + 1][0] if k + 1 < len(CHANGES) else dur
        if at == H["outro"]:
            continue                                    # the outro swell is voiced separately below
        start = at - (0.0 if at == 0 else 0.06)
        last_loop = kind == "vert" and k + 1 == len(CHANGES)      # upright cut: hold the chord into the loop
        seg = E.supersaw([mtof(m) for m in CH[name][1]], end - start + (0.0 if last_loop else 0.9),
                         att=0.02 if at == 0 else 0.08 if at == H["rules"] else 0.35, rel=0.01 if last_loop else 0.9)
        E.place(pads, seg, start)
    # the one "a little cinematic" swell: builds out of the silence after "Stop.", lands on "Your rules."
    sw_at = RESUME + 0.05
    sw_len = H["rules"] - sw_at + 0.6
    sw = E.supersaw([mtof(m) for m in CH["Bb9"][1]] + [mtof(CH["Bb9"][1][0] - 12)], sw_len,
                    att=H["rules"] - sw_at, rel=0.6)
    E.place(pads, sw, sw_at, 1.25)
    lfo = lambda tc: 1 + 0.15 * np.sin(2 * np.pi * tc / 4.0)          # two-bar breathing on the filter
    pads = E.stft_filter(pads, E.lp(lambda tc: pad_fc(tc) * lfo(tc), 2, 0.45))
    pads *= pad_lvl(ta)

    # ---------------------------------------------------- bass: soft sine in the D2 register, played in 8ths
    pts = []
    for at, name in CHANGES:
        r = CH[name][0]
        pts.append((at, r if r >= 31 else r + 12))          # never below G1 (49 Hz): no sub rumble
    f_step = np.zeros(N)
    for k, (at, m) in enumerate(pts):
        f_step[int(at * SR):] = mtof(m)
    kk = int(0.03 * SR)
    f_line = np.convolve(np.pad(f_step, kk, mode="edge"), np.ones(kk) / kk, mode="same")[kk:-kk]
    g_line = np.zeros(N)
    for at, g in sorted(bass_lvl):
        g_line[int(at * SR):] = g
    g_line = np.convolve(np.pad(g_line, 2400, mode="edge"), np.ones(2400) / 2400, mode="same")[2400:-2400]
    art = np.zeros(N)
    for i in range(int(dur / S8) + 1):
        a0 = max(0.0, E.hum(i * S8, 3)); i0 = int(a0 * SR); m = min(N - i0, int(S8 * SR))
        if m > 0:
            art[i0:i0 + m] = np.maximum(art[i0:i0 + m], rng.uniform(0.75, 1.0) * np.exp(-E.t_axis(m) / 0.16))
    art = np.convolve(art, np.ones(192) / 192, mode="same")
    s = np.sin(2 * np.pi * np.cumsum(f_line) / SR)
    b = np.tanh(1.6 * s) / np.tanh(1.6) * g_line * (0.45 + 0.55 * art)
    E.place(bass, b, 0.0)

    # ---------------------------------------------------- the arp: swung, played, evolving
    motif = [0, 2, 1, 3, 2, 4, 3, 1]
    S16 = BEAT / 4
    for i in range(int(dur / S16)):
        at = i * S16
        d = dens_at(at)
        if d == 0 or (STOP - 0.02 <= at < RESUME):
            continue
        step = i % 16
        play = {1: step % 4 == 0, 2: step % 2 == 0, 3: step % 2 == 0 or rng.random() < 0.3,
                4: rng.random() > 0.15}[d]
        if not play:
            continue
        tones = arp_tones(chord_at(at + 0.01))
        bar = int(at // 2)
        idx = (motif[(step // 2 + bar) % 8] + (bar % 3 if d >= 3 else 0)) % len(tones)
        m = tones[idx]
        vel = (0.38 + 0.08 * d) * (1.0 if step % 4 == 0 else 0.8 if step % 2 == 0 else 0.6) * rng.uniform(0.85, 1.1)
        when = E.hum(at + (0.07 * 2 * S16 if step % 2 else 0.0) + 0.004, 5)       # 57 % swing, a hair behind
        if when >= STOP - 0.01 and when < RESUME:
            continue
        E.place(keys, E.pan(E.ks_pluck(mtof(m), 0.9, vel, 0.35 + 0.1 * d), 0.5 * np.sin(2 * np.pi * at / 3.7)),
                when, 0.5)

    # ---------------------------------------------------- heartbeat pulse (memory story), half time
    kicks = []
    for a, b_ in PULSE:
        at = np.ceil(a / (2 * BEAT)) * 2 * BEAT if kind == "land" else a
        while at < b_ - 0.05:
            kt = E.hum(at, 2); kicks.append(kt)
            E.place(beat, E.heartbeat(0.42 * rng.uniform(0.9, 1.0)), kt)
            at += 2 * BEAT

    # ---------------------------------------------------- felt piano: the human hand
    def piano(m, at, vel, p=0.0, d=3.0, extra=0.0):
        n = E.pan(E.felt_piano(mtof(m), d, vel), p)
        E.place(keys, n, E.hum(at, 3))
        if extra:
            E.place(hall_extra, n, at, extra)

    def rolled(ms, at, vel, spread=0.014):
        for j, m in enumerate(ms):
            piano(m, at + j * spread, vel * (1 - 0.05 * j), -0.45 + 0.9 * j / max(1, len(ms) - 1), 3.2, 0.3)

    # ---------------------------------------------------- sound design + scene notes
    def card_land(at, note, gain=1.0):
        E.place(ui, E.swish(0.32, 700, 5200, peak=0.9, width=0.55, pan_path=(-0.3, 0.2)), at - 0.29, 0.22 * gain)
        n = E.pan(E.bell(mtof(note), 1.4, 0.32 * gain), 0.1)
        E.place(ui, n, at); E.place(hall_extra, n, at, 0.45)

    def fingerprint(touch, ok, approved, sheet):
        E.place(ui, E.swish(0.28, 500, 3000, peak=0.9, width=0.5), sheet - 0.25, 0.08)     # sheet rises, barely
        E.place(ui, E.thud(0.55), touch)
        for at, m in ((ok, 72), (approved, 77)):                                            # C5 -> F5: settles on "yes"
            n = E.pan(E.bell(mtof(m), 1.6, 0.34, ratio=2.0, index=0.5, decay=0.8), 0.0)
            E.place(ui, n, at); E.place(hall_extra, n, at, 0.5)

    def browser(land, click_at, renewed):
        E.place(ui, E.swish(0.34, 600, 4200, peak=0.9, width=0.6, pan_path=(0.4, 0.0)), land - 0.31, 0.2)   # peaks at `land`
        E.place(ui, E.click(0.4), click_at)
        piano(69, renewed, 0.4, 0.1, 3.0, 0.5)                                                               # one warm A4

    def deep(f_hi, f_lo, at, d):
        """The deep weight under the landing: two soft sines an octave apart, slow decay."""
        tt = E.t_axis(int(d * SR))
        s = (0.6 * np.sin(2 * np.pi * f_hi * tt) + 0.4 * np.sin(2 * np.pi * f_lo * tt)) * np.exp(-tt / (d / 2.5))
        E.place(bass, s * np.minimum(1, tt / 0.012) * np.clip((d - tt) / 0.2, 0, 1), at, 0.4)

    if kind == "land":
        piano(62, H["hey"], 0.27, 0.2, 3.5, 0.5)              # D4, alone: it's listening
        card_land(H["cards"], 81)                             # A5 over Bb: both cards land
        piano(50, H["every"], 0.3, 0.0, 2.5)                  # "Every time." gets a low D, not a hit
        E.place(ui, E.click(0.45), H["tap"])
        fingerprint(H["touch"], H["ok"], YES, H["sheet"])
        E.place(ui, E.swish(0.25, 3000, 900, peak=0.3, width=0.5, pan_path=(0.3, -0.2)), H["clear"], 0.05)
        browser(H["browser"] + 0.2, H["click"], H["renewed"])   # the window is fully in ~0.2 s after `browser`
        piano(70, H["juneCard"], 0.26, 0.2, 2.2)              # June card: one note, no swish
        card_land(H["askCard"], 81, 0.8)                      # the "keep this?" card
        E.place(ui, E.click(0.4), H["keep"])
        piano(65, H["keep"], 0.42, 0.0, 3.0, 0.5)             # Keep: one warm F4
        E.place(ui, E.swish(0.3, 600, 4000, peak=0.85, width=0.6, pan_path=(0.4, -0.1)), H["list"] - 0.25, 0.1)
        n = E.pan(E.sag(mtof(74), 0.9, 0.2), -0.3)            # the old fact is set aside: a note that sags
        E.place(ui, n, H["retired"]); E.place(hall_extra, n, H["retired"], 0.4)
        # outro: a light Bb9 on the cut, the swell lands on "Your rules." as F (a plagal "amen"), one bell for the logo
        rolled([50, 57, 62, 65], H["outro"], 0.3, 0.02)
        piano(74, H["pc"], 0.25, 0.3, 2.5, 0.4)
        rolled([29, 41, 53, 57, 60, 64, 69], H["rules"], 0.5, 0.018)
        deep(mtof(41), mtof(29), H["rules"], 3.2)
        for j, m in enumerate([77, 84]):
            n = E.pan(E.bell(mtof(m), 3.0, 0.28, ratio=3.5, index=0.9, decay=1.4), -0.15 + 0.3 * j)
            E.place(ui, n, H["logo"] + 0.03 * j); E.place(hall_extra, n, H["logo"] + 0.03 * j, 0.6)
        piano(53, H["logo"], 0.25, 0.0, 3.0)
    else:
        card_land(0.0, 81, 0.6)                               # cards are already there: the note only rings
        E.place(ui, E.click(0.45), H["tap"])
        fingerprint(H["touch"], H["ok"], YES, H["sheet"])
        browser(H["browser"] + 0.2, H["click"], H["renewed"])
        card_land(H["askCard"], 81, 0.8)
        E.place(ui, E.click(0.4), H["keep"])
        piano(65, H["keep"], 0.42, 0.0, 3.0, 0.5)
        rolled([50, 57, 62, 65], H["outro"], 0.3, 0.02)
        piano(74, H["pc"], 0.25, 0.3, 2.0, 0.4)
        rolled([34, 46, 50, 57, 62, 69], H["rules"], 0.48, 0.018)   # the swell lands on Bb: the loop's first chord
        deep(mtof(46), mtof(34), H["rules"], 1.4)

    # ---------------------------------------------------- mix
    pump = np.zeros(N)
    for kt in kicks:
        i = int(kt * SR); m = min(N - i, int(0.4 * SR))
        if m > 0:
            tt = E.t_axis(m)
            pump[i:i + m] = np.maximum(pump[i:i + m], np.minimum(1, tt / 0.006) * np.exp(-tt / 0.2))
    pads *= 1 - 0.25 * pump
    bass *= 1 - 0.3 * pump

    # a little analogue drift on keys and pads (slow wow + flutter via a variable delay)
    def wow(x, depth_ms):
        d = (1.5 + depth_ms * np.sin(2 * np.pi * 0.55 * ta) + 0.07 * np.sin(2 * np.pi * 6.3 * ta)) / 1000 * SR
        return np.vstack([np.interp(np.arange(N) - d, np.arange(N), c) for c in x])
    keys, pads = wow(keys, 0.3), wow(pads, 0.45)

    beat = beat + 0.15 * E.conv(beat, E.make_ir((0.5, 0.4, 0.25), 0.6, 0.006, 20, seed=3))
    dry = keys * 0.9 + pads * 0.6 + bass * 0.75 + beat * 0.7 + ui * 0.9
    send = keys * 0.3 + pads * 0.3 + ui * 0.2 + hall_extra * 0.6
    send = np.vstack([E.fft_band(c, 250, 8000) for c in send])     # EQ the send: no low mud in the hall
    HALL = E.make_ir(seed=11)
    s0 = int(round(STOP * SR)); s1 = int(round(RESUME * SR))
    pre, post = send.copy(), send.copy()
    pre[:, s0:] = 0; post[:, :s1] = 0
    wet = E.conv(pre, HALL); wet[:, s0:] = 0                        # the hall dies with everything else
    wet += E.conv(post, HALL)
    mix = dry + 0.5 * wet

    # low end: mono below 120 Hz; a gentle shelf keeps the bottom from dominating
    f = np.fft.rfftfreq(N, 1 / SR) + 1e-3
    M, S = (mix[0] + mix[1]) / 2, (mix[0] - mix[1]) / 2
    Mf, Sf = np.fft.rfft(M), np.fft.rfft(S)
    Mf *= (1 / (1 + (28 / f) ** 4)) * (0.7 + 0.3 / (1 + (90 / f) ** 2))      # HPF 28 Hz + ~-3 dB shelf under 90 Hz
    Mf *= 1 + 0.5 / (1 + (7000 / f) ** 2)                                    # a little air on top (+3.5 dB shelf)
    Sf *= (1 / (1 + (120 / f) ** 4)) * (1 + 0.2 / (1 + (2000 / f) ** 2)) * (1 + 0.5 / (1 + (7000 / f) ** 2))
    M, S = np.fft.irfft(Mf, N), np.fft.irfft(Sf, N)
    mix = np.vstack([M + S, M - S])

    # glue + tape
    mix = E.compress(mix, -20, 1.8, 0.012, 0.3)
    bias = 0.06
    mix = (np.tanh(1.25 * mix + bias) - np.tanh(bias)) / 1.25
    F = np.fft.rfft(mix, axis=1); F *= 1 / (1 + (18 / f) ** 4); mix = np.fft.irfft(F, N, axis=1)   # DC blocker

    # room tone (quiet, moving) so the calm stretches sound recorded, not rendered
    pink = np.fft.irfft(np.fft.rfft(rng.standard_normal((2, N)), axis=1) / np.sqrt(np.maximum(f, 20))
                        / (1 + (f / 7000) ** 2) / (1 + (40 / f) ** 4), N, axis=1)
    mix += pink / np.abs(pink).max() * dbg(-60) * (1 + 0.3 * np.sin(2 * np.pi * 0.13 * ta))
    if kind == "vert":
        # loop seam: ease the last 1.5 s to the level of the first 250 ms, so the replay does not jump
        w = int(0.25 * SR)
        r = np.sqrt(np.mean(mix[:, :w] ** 2)) / (np.sqrt(np.mean(mix[:, -w:] ** 2)) + 1e-12)
        g = np.ones(N)
        a0, a1 = int((dur - 1.5) * SR), int((dur - 0.35) * SR)
        g[a0:a1] = 10 ** (np.linspace(0, np.log10(r), a1 - a0)); g[a1:] = r
        mix *= g
    return E, mix, s0, s1, dict(bass=bass, beat=beat)


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

STOP_LEAD = 0.020    # seconds of silence before the stop frame (less than one 30 fps frame)


def master(mix, s0, s1, fade_out=None, edge=0.004):
    N = mix.shape[1]
    x = mix / np.abs(mix).max()
    gain = 1.0
    for _ in range(5):
        y = limit(x * gain)
        # the dead stop: an 8 ms raised-cosine ramp that ends STOP_LEAD before the stop frame, then digital
        # zero until resume. The video's AAC encoder smears a hard cut forward by up to ~16 ms; a 12 ms lead
        # still left the upright cut at -51 dBFS just after its stop frame, 20 ms clears both (tested).
        r = int(edge * SR); rs = int(0.008 * SR); e0 = s0 - int(STOP_LEAD * SR)
        y[:, e0 - rs:e0] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, rs))
        y[:, e0:s1] = 0
        y[:, s1:s1 + r] *= np.linspace(0, 1, r)
        y[:, :r] *= np.linspace(0, 1, r)
        if fade_out:
            a = int(fade_out[0] * SR); b = int(fade_out[1] * SR)
            y[:, a:b] *= np.linspace(1, 0, b - a) ** 2
            y[:, b:] = 0
        else:
            y[:, -r:] *= np.linspace(1, 0, r)
        I, TP, LRA = ebur128(y)
        if abs(I + 14) < 0.05 and TP <= -1.0:
            break
        gain *= dbg(-14 - I)
    return y, (I, TP, LRA)

def write(y, mp3_path):
    pcm = (np.clip(y.T, -1, 1) * 32767).round().astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-codec:a", "libmp3lame", "-b:a", "256k", "-ar", str(SR), mp3_path], input=pcm, check=True)

def audio_data(y, dur, path, s0, s1):
    """Per-frame envelopes, 0-1: `low` (< 160 Hz of the mix, drives the reactor glow) and `rms`."""
    N = y.shape[1]
    m = y.mean(0)
    f = np.fft.rfftfreq(N, 1 / SR) + 1e-3
    low = np.fft.irfft(np.fft.rfft(m) / (1 + (f / 160) ** 4), N)
    frames = int(round(dur * FPS)); hop = SR // FPS
    def env(x):
        v = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) for i in range(frames)])
        return np.round(v / (np.percentile(v, 98) or 1), 3).clip(0, 1)
    lo, rm = env(low), env(m)
    k0, k1 = int(np.ceil(s0 / hop)), int(s1 // hop)                 # the glow goes dark on "Stop." too
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
        E, mix, s0, s1, _ = render(timing, kind)
        fade = (E.dur - 0.7, E.dur) if kind == "land" else None      # fade to black with the picture
        y, (I, TP, LRA) = master(mix, s0, s1, fade)
        write(y, os.path.join(ASSETS, "music", mp3))
        audio_data(y, E.dur, os.path.join(ASSETS, ad), s0, s1)
        print(f"{mp3}: {E.dur:.1f} s  I={I:.1f} LUFS  TP={TP:.1f} dBTP  LRA={LRA:.1f} LU")


if __name__ == "__main__":
    main()
