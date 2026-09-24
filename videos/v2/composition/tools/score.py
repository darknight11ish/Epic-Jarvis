"""Original trailer score for the Jarvis brag video, written to the storyboard.

120 BPM, A minor, 25 s. Every hit sits on the same timing table the
composition uses (T below mirrors assets/timing.js), so picture and sound
cannot drift. Output:
  assets/music/score.mp3      the mixed track
  assets/audio-data.js        per-frame low-band + RMS envelope (30 fps)
"""
import json, os, subprocess, sys
import numpy as np

SR = 48000
DUR = 35.0
N = int(SR * DUR)
BEAT = 0.5
rng = np.random.default_rng(7)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SFX_DIR = sys.argv[1] if len(sys.argv) > 1 else ""

T = json.load(open(os.path.join(ROOT, "assets", "timing.json")))

def t_axis(n):
    return np.arange(n) / SR

def place(bus, sig, at, gain=1.0):
    i = int(round(at * SR))
    if i >= bus.shape[1] or i + sig.shape[-1] <= 0:
        return
    s = sig if sig.ndim == 2 else np.vstack([sig, sig])
    j = min(bus.shape[1], i + s.shape[1])
    bus[:, i:j] += s[:, : j - i] * gain

def pan(sig, p):
    # p in -1..1, constant power
    a = (p + 1) * np.pi / 4
    return np.vstack([sig * np.cos(a), sig * np.sin(a)])

def additive_saw(f, dur, fc_curve, detune_cents=(0,), max_h=None):
    """Band-limited saw; fc_curve(t) is a time-varying lowpass cutoff in Hz."""
    n = int(SR * dur)
    t = t_axis(n)
    fc = fc_curve(t)
    out = np.zeros(n)
    for c in detune_cents:
        ff = f * 2 ** (c / 1200)
        kmax = int(min(max_h or 999, (SR * 0.45) // ff))
        ph0 = rng.uniform(0, 2 * np.pi)
        for k in range(1, kmax + 1):
            g = 1.0 / (1.0 + (k * ff / fc) ** 4)
            if np.max(g) < 1e-3:
                break
            out += g * np.sin(2 * np.pi * k * ff * t + ph0 * k) / k
    return out / len(detune_cents)

def kick(gain=1.0):
    n = int(SR * 0.6); t = t_axis(n)
    f = 44 + 90 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / 0.30)
    click = rng.standard_normal(n) * np.exp(-t / 0.0025) * 0.35
    return np.tanh(1.6 * (body + click)) * gain

def hat(open_=False):
    n = int(SR * (0.18 if open_ else 0.05)); t = t_axis(n)
    x = rng.standard_normal(n)
    x = np.diff(np.diff(x, prepend=0), prepend=0)  # crude high-pass
    return x * np.exp(-t / (0.06 if open_ else 0.012)) * 0.055

def clap():
    n = int(SR * 0.35); t = t_axis(n)
    x = rng.standard_normal(n)
    x = np.diff(x, prepend=0)
    x = np.convolve(x, np.ones(6) / 6, mode="same")
    env = np.exp(-t / 0.09) * (1 + 0.6 * np.exp(-((t - 0.012) / 0.004) ** 2))
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05) * 0.4
    return (x * 0.9 + tone) * env * 0.5

def sub_note(f, dur=0.24, gain=1.0):
    n = int(SR * dur); t = t_axis(n)
    env = np.minimum(1, t / 0.006) * np.exp(-t / 0.16)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t)
    grit = additive_saw(f * 2, dur, lambda tt: 900 * np.exp(-tt / 0.08) + 180, max_h=40) * 0.35
    return np.tanh(1.3 * (s + grit)) * env * gain

def pluck(f, dur=0.22, bright=2600):
    n = int(SR * dur); t = t_axis(n)
    s = additive_saw(f, dur, lambda tt: bright * np.exp(-tt / 0.07) + 300, detune_cents=(-6, 6), max_h=30)
    return s * np.minimum(1, t / 0.003) * np.exp(-t / 0.09)

def braam(root=55.0, dur=2.6, gain=1.0):
    n = int(SR * dur); t = t_axis(n)
    fc = lambda tt: 160 + 1900 * np.minimum(1, tt / 0.12) * np.exp(-tt / 0.55) + 220
    s = (additive_saw(root, dur, fc, detune_cents=(-9, 0, 9))
         + 0.8 * additive_saw(root * 1.5, dur, fc, detune_cents=(-7, 7))
         + 0.7 * additive_saw(root * 2, dur, fc, detune_cents=(-5, 5)))
    sub = np.sin(2 * np.pi * root * t) * 0.9
    env = np.minimum(1, t / 0.015) * np.exp(-t / 1.1)
    return np.tanh(1.8 * (s * 0.8 + sub)) * env * gain

def impact(gain=1.0):
    n = int(SR * 1.2); t = t_axis(n)
    f = 28 + 70 * np.exp(-t / 0.18)
    drop = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.45)
    x = rng.standard_normal(n)
    x = np.convolve(x, np.ones(24) / 24, mode="same") * np.exp(-t / 0.08) * 2.2
    return np.tanh(1.4 * (drop + x)) * gain

def riser(dur, gain=1.0):
    n = int(SR * dur); t = t_axis(n); u = t / dur
    f = 180 * (12 ** u)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    x = rng.standard_normal(n)
    x = np.diff(x, prepend=0) * 0.5
    env = u ** 2.4
    return (tone + x) * env * gain

def chime():
    n = int(SR * 1.4); t = t_axis(n)
    a = np.sin(2 * np.pi * 659.25 * t) * np.exp(-t / 0.35)
    b = np.zeros(n); k = int(0.09 * SR)
    b[k:] = np.sin(2 * np.pi * 880 * t[: n - k]) * np.exp(-t[: n - k] / 0.6)
    return (a + b) * 0.28

def whoosh(dur=0.45):
    n = int(SR * dur); t = t_axis(n); u = t / dur
    x = rng.standard_normal(n)
    w = int(40 - 34 * np.sin(np.pi * u).mean())
    x = np.convolve(x, np.ones(8) / 8, mode="same")
    return x * np.sin(np.pi * u) ** 2 * 0.35

def pad(chord, dur, gain=1.0):
    n = int(SR * dur); t = t_axis(n)
    s = sum(additive_saw(f, dur, lambda tt: 520 + 0 * tt, detune_cents=(-8, 0, 8), max_h=24) for f in chord)
    env = np.minimum(1, t / 0.6) * np.minimum(1, (dur - t) / 0.4)
    return s * env * gain

def reverb(stereo, seconds=2.2, decay=0.75, wet=0.25):
    n = int(SR * seconds); t = t_axis(n)
    irs = []
    for _ in range(2):
        ir = rng.standard_normal(n) * np.exp(-t / decay)
        ir = np.convolve(ir, np.ones(10) / 10, mode="same")
        ir[: int(0.012 * SR)] = 0
        irs.append(ir / np.sqrt(np.sum(ir ** 2)))
    out = np.zeros_like(stereo)
    L = stereo.shape[1] + n
    nfft = 1 << (L - 1).bit_length()
    for c in range(2):
        y = np.fft.irfft(np.fft.rfft(stereo[c], nfft) * np.fft.rfft(irs[c], nfft), nfft)[: stereo.shape[1]]
        out[c] = y
    return out * wet

def load_sfx(rel):
    path = os.path.join(SFX_DIR, rel)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.astype(np.float64)

# ---------------------------------------------------------------- arrange (v2, 35 s)
H = T["hits"]
drums = np.zeros((2, N)); bass = np.zeros((2, N)); music = np.zeros((2, N))
fx = np.zeros((2, N)); send = np.zeros((2, N)); ui = np.zeros((2, N))

# Am - F - Dm - E, one chord per bar (2 s)
ROOTS = [55.0, 43.65, 73.42, 41.2]
CHORDS = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [146.83, 174.61, 220.0], [164.81, 207.65, 246.94]]
ARP = [[440, 523.25, 659.25, 880], [349.23, 440, 523.25, 698.46], [293.66, 349.23, 440, 587.33], [329.63, 415.3, 493.88, 659.25]]

def bar_of(t):
    return int(t // 2) % 4

pause0, pause1 = H["paused"], H["resume"]
stop, stop_end = H["stop"], H["interrupt"]

def groove_on(t):
    # The music waits while Jarvis waits on a pause (Smart Turn), and dies on STOP.
    if pause0 <= t < pause1:
        return False
    return (H["learns"] <= t < stop) or (H["ready"] <= t < H["outro"])

def half_time(t):
    return H["today"] <= t < H["ready"]

# Opening: drone + riser into the braam at 2.0
place(music, pan(pad([55.0, 82.41, 110.0], 2.4, 0.18), 0), 0.0)
place(fx, pan(riser(2.0, 0.7), 0), 0.0)
place(bass, pan(braam(55.0, 2.8, 1.0), 0), H["hey"])
place(fx, pan(impact(0.9), 0), H["hey"])
place(send, pan(braam(55.0, 2.8, 0.5), 0), H["hey"])

# 2.0 - 5.5: tension pulse (sub 8ths + closed hats)
for i in range(int((H["learns"] - H["hey"]) / 0.25)):
    at = H["hey"] + i * 0.25
    if i % 2 == 0:
        place(bass, pan(sub_note(ROOTS[0], gain=0.55), 0), at)
    place(drums, pan(hat(), 0.3 if i % 2 else -0.3), at, 0.7)
place(fx, pan(impact(0.6), 0), H["nothing"])
place(ui, load_sfx("interface/glitch_002.ogg"), H["nothing"], 0.9)
place(music, pan(pad(CHORDS[0], 2.2, 0.35), 0), 3.4)
place(fx, pan(riser(1.0, 0.5), 0), 4.5)

# Groove sections (16ths grid)
for i in range(int(DUR / 0.125)):
    at = i * 0.125
    if groove_on(at):
        b = bar_of(at); step = i % 16
        if step % 4 == 0:
            place(drums, pan(kick(0.95), 0), at)
        place(drums, pan(hat(open_=(step % 4 == 2)), 0.35 if step % 2 else -0.35), at, 1.0 if step % 2 == 0 else 0.6)
        if step % 2 == 0:
            place(bass, pan(sub_note(ROOTS[b], gain=0.7 if step % 4 == 0 else 0.5), 0), at)
        arp = ARP[b][[0, 1, 2, 3, 2, 1, 3, 0][(step // 2) % 8]]
        if step % 2 == 1 or at >= H["propose"]:
            place(music, pan(pluck(arp, bright=1800 + 1400 * (at > 8.0)), 0.5 if step % 4 < 2 else -0.5), at, 0.22)
            place(send, pan(pluck(arp), 0), at, 0.12)
    elif half_time(at) and (i % 4 == 0):
        step = i % 16
        if step == 0:
            place(drums, pan(kick(0.9), 0), at)
            place(bass, pan(sub_note(ROOTS[3], 0.45, 0.85), 0), at)
        if step == 8:
            place(drums, pan(clap(), 0), at, 0.7)
        place(drums, pan(hat(True), 0.2), at + 0.25, 0.5)

# Scene accents
for key in ("learns", "propose", "timeline", "voice", "turn", "phone", "next"):
    place(drums, pan(clap(), 0), H[key], 0.9)
    place(send, pan(clap(), 0), H[key], 0.5)
place(music, pan(pad(CHORDS[1], 4.0, 0.22), 0), H["propose"])
place(music, pan(pad(CHORDS[2], 3.0, 0.22), 0), H["timeline"])

# Learning act
for k in range(10):   # "I've started running on Tuesdays." types in
    place(ui, load_sfx(f"keyboard/keypress-{(k * 7) % 30 + 1:03d}.wav"), H["learns"] + 0.15 + k * 0.075, 0.35)
place(ui, load_sfx("casino/card-slide-1.ogg"), H["propose"] + 0.05, 0.8)
place(ui, load_sfx("interface/click_003.ogg"), H["keep"], 1.0)
place(ui, pan(whoosh(0.4), 0.5), H["stash"], 0.9)
place(ui, load_sfx("interface/glitch_004.ogg"), H["retire"], 0.9)
place(ui, pan(whoosh(0.6), -0.4), H["asof"], 0.8)
place(ui, pan(chime(), 0), H["match"], 0.9)
place(ui, load_sfx("interface/error_005.ogg"), H["reject"], 0.7)

# Smart Turn: the groove holds its breath on the pause, a soft pad under it
place(music, pan(pad(CHORDS[3], 0.9, 0.3), 0), pause0 - 0.1)
place(fx, pan(impact(0.5), 0), pause1)

# Phone + card, swipe, approved
place(fx, pan(impact(0.7), 0), H["phone"])
place(ui, load_sfx("casino/card-slide-1.ogg"), H["phone"] + 0.05, 0.8)
place(ui, pan(whoosh(0.45), 0.6), H["swipe"], 1.0)
place(ui, load_sfx("casino/card-slide-1.ogg"), H["swipe"] + 0.05, 0.6)
place(ui, pan(chime(), 0), H["approved"], 1.0)
place(send, pan(chime(), 0), H["approved"], 0.8)

# Reply streams, then STOP
for k in range(12):
    place(ui, load_sfx(f"keyboard/keypress-{(k * 11) % 30 + 1:03d}.wav"), H["reply"] + 0.08 + k * 0.075, 0.35)
place(fx, pan(riser(1.0, 0.45), 0), H["reply"])
place(fx, pan(impact(1.1), 0), stop)
place(ui, load_sfx("impact/impactSoft_heavy_003.ogg"), stop, 0.9)

# 20.5 - 22.0: low drone, then a kick build into TODAY
place(music, pan(pad([55.0, 82.41], 1.6, 0.45), 0), stop_end)
for k in range(4):
    place(drums, pan(kick(0.55 + 0.12 * k), 0), H["today"] - 1.0 + k * 0.25)
place(fx, pan(riser(1.0, 0.55), 0), H["today"] - 1.0)

# Scaling act
place(fx, pan(impact(0.9), 0), H["today"])
place(bass, pan(braam(41.2, 2.0, 0.5), 0), H["today"])
place(music, pan(pad(CHORDS[3], 2.0, 0.3), 0), H["today"])
place(fx, pan(impact(1.0), 0), H["ready"])
place(ui, load_sfx("impact/impactMetal_heavy_000.ogg"), H["ready"] + 0.05, 0.7)   # the card seats
for at in H["tiles"] + H["choices"]:
    place(ui, load_sfx("interface/click_003.ogg"), at, 0.9)
place(fx, pan(impact(0.8), 0), H["next"])
place(music, pan(pad(CHORDS[0], 3.0, 0.25), 0), H["next"])
place(fx, pan(riser(2.0, 1.0), 0), H["outro"] - 2.0)
for k in range(8):
    place(drums, pan(clap(), 0), H["outro"] - 1.0 + k * 0.125, 0.25 + 0.08 * k)

# Outro: three braams, then the sub tail
for key, root, g in (("outro", 55.0, 1.0), ("pc", 43.65, 0.85), ("rules", 55.0, 1.0)):
    place(bass, pan(braam(root, 2.8, g), 0), H[key])
    place(fx, pan(impact(0.85 * g), 0), H[key])
    place(send, pan(braam(root, 2.8, 0.45 * g), 0), H[key])
place(music, pan(pad([220.0, 261.63, 329.63, 440.0], 4.5, 0.35), 0), H["outro"])
place(fx, pan(impact(0.7), 0), H["logo"])
place(ui, load_sfx("impact/impactBell_heavy_000.ogg"), H["logo"], 0.45)

# ------------------------------------------------------------------ mix
kick_env = np.zeros(N)
for i in range(int(DUR / 0.5)):
    at = i * 0.5
    if groove_on(at) or half_time(at):
        s_ = int(at * SR); e = min(N, s_ + int(0.25 * SR))
        kick_env[s_:e] = np.maximum(kick_env[s_:e], np.exp(-t_axis(e - s_) / 0.09))
duck = 1 - 0.55 * kick_env

mix = drums * 0.8 + bass * 0.8 * duck + music * 0.5 * duck + fx * 0.75 + ui * 0.8
mix += reverb(send + music * 0.4 + fx * 0.2, wet=0.35)

# STOP: everything cuts dead 60 ms after the hit, until the downbeat
s0, s1 = int((stop + 0.06) * SR), int(stop_end * SR)
fade = int(0.012 * SR)
mix[:, s0:s0 + fade] *= np.linspace(1, 0, fade)
mix[:, s0 + fade:s1] = 0

# Master: gentle tape-style saturation, fade in, tail fade
mix = np.tanh(mix * 1.1) / np.tanh(1.1)
fi = int(0.02 * SR); mix[:, :fi] *= np.linspace(0, 1, fi)
fo = int(0.9 * SR); mix[:, -fo:] *= np.linspace(1, 0, fo) ** 1.5
mix /= np.max(np.abs(mix)) / 0.95

out_dir = os.path.join(ROOT, "assets", "music")
os.makedirs(out_dir, exist_ok=True)
wav = os.path.join(out_dir, "score.wav")
raw = (np.clip(mix.T, -1, 1) * 32767).astype("<i2").tobytes()
# Two-pass LINEAR loudness normalisation: one gain for the whole track, so the
# quiet ignite and the braams keep their distance (single-pass loudnorm is
# dynamic and flattened them to 3.7 LU).
pcm = ["-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-"]
meas = subprocess.run(["ffmpeg", "-hide_banner", "-y", *pcm, "-af", "loudnorm=I=-14:TP=-1.0:LRA=20:print_format=json",
                       "-f", "null", "-"], input=raw, capture_output=True, check=True).stderr.decode()
m = json.loads(meas[meas.rindex("{"):meas.rindex("}") + 1])
ln = (f"loudnorm=I=-14:TP=-1.0:LRA=20:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
      f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
subprocess.run(["ffmpeg", "-v", "error", "-y", *pcm, "-af", ln, "-ar", str(SR), wav], input=raw, check=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-codec:a", "libmp3lame", "-b:a", "256k",
                os.path.join(out_dir, "score.mp3")], check=True)
os.remove(wav)

# Per-frame envelopes for audio-reactive visuals (30 fps)
FPS = 30
low = (drums + bass).mean(axis=0)
full = mix.mean(axis=0)
def env(x):
    hop = SR // FPS
    frames = int(DUR * FPS)
    v = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) for i in range(frames)])
    return np.round(v / (np.percentile(v, 98) or 1), 3).clip(0, 1)
data = {"fps": FPS, "low": env(low).tolist(), "rms": env(full).tolist()}
with open(os.path.join(ROOT, "assets", "audio-data.js"), "w") as f:
    f.write("window.AUDIO_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
print("score ok")
