#!/usr/bin/env python3
"""Trains the "stop" word and writes backend/jarvis_stopword.py and the
phone's jarvis-client/app/src/main/assets/wakeword/stop_head.bin (the same
numbers, byte for byte), and the phone test's golden file
jarvis-client/app/src/test/resources/stop-golden.json.

    python3 tools/train_stopword.py data <split> <piper-dir> <kokoro-dir> <wakeword-dir> <work-dir>
    python3 tools/train_stopword.py train <work-dir>

`data` once for each split - train, test_piper, test_kokoro, stream - then
`train`. The data step takes about ten minutes a split on a laptop CPU.

WHAT IT IS. openWakeWord turns every 80 ms of sound into 96 numbers (an
"embedding"); its "hey jarvis" model looks at the last 16 of them. The stop
word is a second tiny model on the very same 16 x 96 numbers, the same
shape as openWakeWord's own heads: 1,536 -> 32 -> LayerNorm -> ReLU -> 32 ->
LayerNorm -> ReLU -> 1 -> sigmoid. It hears one word, "stop" (also "Jarvis,
stop", "okay, stop", "stop it"). It turns sound into one number and knows no
words: it is not speech-to-text, which a client must never do.

WHERE THE VOICES COME FROM. Synthetic voices only; no recording of any
person is used or shipped.
  - Piper's LibriTTS-R voice (904 speakers), `vits-piper-en_US-libritts_r-
    medium` from https://github.com/k2-fsa/sherpa-onnx/releases/download/
    tts-models/vits-piper-en_US-libritts_r-medium.tar.bz2. Training uses
    speakers 200..519; the tests use 600..679 and 700..759, never trained on.
  - Kokoro v0.19 (`kokoro-en-v0_19` from the same release page) - Jarvis's
    own voice family, so its sentences are the negatives that matter most.
    Voices 1..4 in training; 0 and 5..10 in the tests.
Positives are the stop phrases; negatives are sound-alikes ("top", "shop",
"stuff", "step", "spot", "stock"...) and ordinary sentences - several
of them with "stop"'s sounds inside ("the stock market", "a spot of
paint"). The label for a positive clip is 1 only for windows ending just
after the word - in training, only once the quiet after it shows
(AFTER_WORD); the middle of a longer phrase is left out, not called 0.

WHAT IT MEASURES (all synthetic): per clip, the best score over the clip
against the threshold - held-out Piper speakers, held-out Kokoro voices, and
a long stream of ordinary sentences for false alarms per hour of talk.

Needs sherpa-onnx, onnxruntime and numpy. Deterministic for given model
files: each split has a fixed seed, training a fixed one.
"""
import base64
import json
import os
import random
import struct
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "backend"))

POS = ["Stop.", "Stop!", "Stop.", "Stop!", "Jarvis, stop.", "Okay, stop.", "Stop it.", "Stop, stop."]
# Words and phrases that sound close to "stop" or contain its sounds.
CONFUSE = ["Top.", "Shop.", "Stuff.", "Step.", "Spot.", "Stock.", "Stomp.", "Stoop.", "Store.",
           "Stuck.", "Star.", "Stone.", "Scott.", "Hot pot.", "Drop it.", "Stay.", "Stuffed.",
           "Stopper", "Top it off.", "Swap.", "Chop.", "Pop.", "Mop.", "Crop.", "Sop."]
SENT = [
    "The weather tomorrow will be sunny with a light breeze.",
    "Your next meeting is at three o'clock in the afternoon.",
    "I have added milk and eggs to your shopping list.",
    "The timer for ten minutes has been set.",
    "Here is a short summary of the article you asked about.",
    "Traffic on the way into town looks light right now.",
    "You have two new messages and one missed call.",
    "The lights in the kitchen are now turned off.",
    "Playing some quiet music in the living room.",
    "It is currently eighteen degrees outside.",
    "Let me check your calendar for Thursday.",
    "The report is due at the end of the week.",
    "Can you pass me the salt, please?",
    "We should leave for the station in twenty minutes.",
    "I think the train is running a little late today.",
    "Please remember to water the plants on the balcony.",
    "The children are playing football in the garden.",
    "Could you turn the volume down a little bit?",
    "That was the best pizza I have had in a long time.",
    "Let's go for a walk after dinner tonight.",
    "The shop on the corner closes at six.",
    "He kept talking about the top of the mountain.",
    "She stepped onto the platform and waited.",
    "The stock market went up again this morning.",
    "Put the stuff back on the shelf when you're done.",
    "There is a spot of paint on the carpet.",
    "Thank you, that is all for now.",
    "What time does the pharmacy open on Sunday?",
    "I'll be home in about half an hour.",
    "Set an alarm for seven thirty tomorrow morning.",
]
SEEDS = {"test_piper": 11, "test_kokoro": 12, "stream": 13, "train": 14}
HIDDEN = 32
EPOCHS = 30
AFTER_WORD = 0.15
MAGIC = b"JSTOP1\x00\x00"


# --------------------------------------------------------------------------
#   data
# --------------------------------------------------------------------------

def data(split: str, piper_dir: Path, kokoro_dir: Path, wake_dir: Path, work: Path) -> int:
    import sherpa_onnx
    import jarvis_wakeword as W
    W.model_dir = lambda: wake_dir
    models = W._load()
    if models is None:
        print("the wake-word models did not load from", wake_dir)
        return 1
    piper = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(
            model=str(piper_dir / "en_US-libritts_r-medium.onnx"), tokens=str(piper_dir / "tokens.txt"),
            data_dir=str(piper_dir / "espeak-ng-data")),
        num_threads=4)))
    kokoro = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
            model=str(kokoro_dir / "model.onnx"), voices=str(kokoro_dir / "voices.bin"),
            tokens=str(kokoro_dir / "tokens.txt"), data_dir=str(kokoro_dir / "espeak-ng-data")),
        num_threads=4)))
    rng = random.Random(SEEDS[split])

    def synth(engine, text, sid, speed):
        a = engine.generate(text, sid=sid, speed=speed)
        x = np.asarray(a.samples, np.float32)
        if not len(x):
            return None
        x = W.to_16k(x, a.sample_rate)
        return x / (float(np.abs(x).max()) or 1.0) * rng.uniform(0.25, 0.9)

    def embeddings(x):
        """Batch openWakeWord embeddings, 2 s of silence first; and each
        window's end time in seconds from the start of the speech clip.
        Two seconds, not one: a window is 16 embeddings of 0.76 s each, 80 ms
        apart, so with one second the first window ended almost a second
        into the clip - after a bare "Stop." had finished - and every
        one-word positive was silently dropped (found on the first run)."""
        lead = 32000
        pcm = np.concatenate([np.zeros(lead, np.float32), x, np.zeros(8000, np.float32)])
        pcm = pcm + rng.gauss(0, 1) * 0.0 + np.random.default_rng(rng.randint(0, 1 << 30)).normal(
            0, rng.uniform(0.0005, 0.004), len(pcm)).astype(np.float32)
        mel = models.melspec(np.clip(pcm, -1, 1) * 32767.0)
        idx = list(range(0, mel.shape[0] - 76 + 1, 8))
        wins = np.stack([mel[i:i + 76] for i in idx])[..., None].astype(np.float32)
        emb = models.emb.run(None, {models.emb_in: wins})[0].reshape(-1, 96)
        end = np.array([(i + 76) * 160 / 16000.0 - lead / 16000.0 for i in idx])
        return emb, end

    def speech_bounds(x):
        e = np.sqrt(np.convolve(x ** 2, np.ones(160) / 160, "same"))
        idx = np.where(e > 0.02 * float(np.abs(x).max()))[0]
        return (idx[0] / 16000, idx[-1] / 16000) if len(idx) else (0, len(x) / 16000)

    def pos_label(x):
        s, e = speech_bounds(x)

        def f(t):
            if e - 0.02 <= t <= e + 0.35:   # the window ends just after the word
                return 1
            if t < s + 0.15:                 # before the speech really starts
                return 0
            return None                      # the middle of "Jarvis, stop" - not used
        return f

    jobs = []
    if split == "train":
        for sid in range(200, 520):
            jobs += [("piper", sid, rng.choice(POS), 1) for _ in range(2)]
            jobs += [("piper", sid, rng.choice(CONFUSE), 0) for _ in range(2)]
            jobs += [("piper", sid, rng.choice(SENT), 0) for _ in range(2)]
        for sid in (1, 2, 3, 4):
            jobs += [("kokoro", sid, s, 0) for s in SENT[:15]]
    elif split == "test_piper":
        for sid in range(600, 680):
            jobs += [("piper", sid, rng.choice(POS), 1), ("piper", sid, rng.choice(CONFUSE), 0),
                     ("piper", sid, rng.choice(SENT), 0)]
    elif split == "test_kokoro":
        for sid in (0, 5, 6, 7, 8, 9, 10):
            jobs += [("kokoro", sid, p, 1) for p in POS[:6]]
            jobs += [("kokoro", sid, c, 0) for c in CONFUSE[:8]]
            jobs += [("kokoro", sid, s, 0) for s in SENT[15:]]
    elif split == "stream":
        for sid in range(11):
            jobs += [("kokoro", sid, s, 0) for s in SENT]
        for sid in range(700, 760):
            jobs += [("piper", sid, s, 0) for s in rng.sample(SENT, 4)]
    else:
        print("unknown split", split)
        return 2

    X, Y, T, C, meta = [], [], [], [], []
    for n, (eng, sid, text, lab) in enumerate(jobs):
        x = synth(piper if eng == "piper" else kokoro, text, sid, rng.choice((0.85, 0.95, 1.0, 1.05, 1.15)))
        if x is None:
            continue
        label = pos_label(x) if lab == 1 else (lambda t: 0)
        emb, end = embeddings(x)
        for j in range(15, len(emb)):
            v = label(end[j])
            if v is None:
                continue
            X.append(emb[j - 15:j + 1]); Y.append(v); T.append(end[j]); C.append(n)
        meta.append({"id": n, "engine": eng, "sid": sid, "text": text, "label": lab,
                     "seconds": round(len(x) / 16000, 2)})
        if n % 200 == 0:
            print(split, n, len(jobs), flush=True)
    work.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(work / f"{split}.npz", X=np.array(X, np.float16), y=np.array(Y, np.int8),
                        t=np.array(T, np.float32), clip=np.array(C, np.int32))
    (work / f"{split}.json").write_text(json.dumps(meta))
    print("done", split, len(X), "windows,", sum(Y), "positive")
    return 0


# --------------------------------------------------------------------------
#   train
# --------------------------------------------------------------------------

class Net:
    """The head, with Adam. Weights as [in][out], like the file."""

    def __init__(self, d, h, rng):
        self.p = {"W1": rng.normal(0, 1 / np.sqrt(d), (d, h)).astype(np.float32), "b1": np.zeros(h, np.float32),
                  "g1": np.ones(h, np.float32), "c1": np.zeros(h, np.float32),
                  "W2": rng.normal(0, 1 / np.sqrt(h), (h, h)).astype(np.float32), "b2": np.zeros(h, np.float32),
                  "g2": np.ones(h, np.float32), "c2": np.zeros(h, np.float32),
                  "W3": rng.normal(0, 1 / np.sqrt(h), (h, 1)).astype(np.float32), "b3": np.zeros(1, np.float32)}
        self.m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.t = 0

    @staticmethod
    def ln(x, g, c):
        mu = x.mean(1, keepdims=True)
        var = x.var(1, keepdims=True)
        xh = (x - mu) / np.sqrt(var + 1e-5)
        return xh * g + c, (xh, var)

    def forward(self, x, keep=False):
        p = self.p
        a1 = x @ p["W1"] + p["b1"]; n1, c1 = self.ln(a1, p["g1"], p["c1"]); r1 = np.maximum(n1, 0)
        a2 = r1 @ p["W2"] + p["b2"]; n2, c2 = self.ln(a2, p["g2"], p["c2"]); r2 = np.maximum(n2, 0)
        z = (r2 @ p["W3"] + p["b3"]).reshape(-1)
        out = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        if keep:
            self.cache = (x, a1, n1, c1, r1, a2, n2, c2, r2)
        return out

    @staticmethod
    def ln_back(dy, g, cache):
        xh, var = cache
        dxh = dy * g
        dx = (1 / np.sqrt(var + 1e-5)) * (dxh - dxh.mean(1, keepdims=True) - xh * (dxh * xh).mean(1, keepdims=True))
        return dx, (dy * xh).sum(0), dy.sum(0)

    def step(self, x, y, w, lr=1e-3, wd=1e-4):
        p = self.p
        out = self.forward(x, keep=True)
        x, a1, n1, c1, r1, a2, n2, c2, r2 = self.cache
        dz = ((out - y) * w / w.sum())[:, None]
        g = {"W3": r2.T @ dz, "b3": dz.sum(0)}
        dn2 = (dz @ p["W3"].T) * (n2 > 0)
        da2, g["g2"], g["c2"] = self.ln_back(dn2, p["g2"], c2)
        g["W2"] = r1.T @ da2; g["b2"] = da2.sum(0)
        dn1 = (da2 @ p["W2"].T) * (n1 > 0)
        da1, g["g1"], g["c1"] = self.ln_back(dn1, p["g1"], c1)
        g["W1"] = x.T @ da1; g["b1"] = da1.sum(0)
        self.t += 1
        for k in p:
            gk = g[k] + (wd * p[k] if k.startswith("W") else 0)
            self.m[k] = 0.9 * self.m[k] + 0.1 * gk
            self.v[k] = 0.999 * self.v[k] + 0.001 * gk * gk
            mh = self.m[k] / (1 - 0.9 ** self.t)
            vh = self.v[k] / (1 - 0.999 ** self.t)
            p[k] -= (lr * mh / (np.sqrt(vh) + 1e-8)).astype(np.float32)


def head_bytes(p) -> bytes:
    h = p["b1"].shape[0]
    d = p["W1"].shape[0]
    out = MAGIC + struct.pack("<ii", h, d)
    for k in ("W1", "b1", "g1", "c1", "W2", "b2", "g2", "c2", "W3", "b3"):
        out += np.ascontiguousarray(p[k], dtype="<f4").tobytes()
    return out


def train(work: Path) -> int:
    rng = np.random.default_rng(0)

    def load(split):
        z = np.load(work / f"{split}.npz")
        meta = {m["id"]: m for m in json.loads((work / f"{split}.json").read_text())}
        return z["X"].astype(np.float32).reshape(len(z["y"]), -1), z["y"].astype(np.float32), z["clip"], meta

    X, y, _, _ = load("train")
    # A "stop" window only once the quiet AFTER the word is in it: from
    # AFTER_WORD seconds past the first window at the word's end. The start
    # of any longer sentence also looks like "quiet, then a short sound";
    # what it never has is the quiet after. (Without this, the first run
    # fired on 47 of 570 ordinary sentences.)
    z = np.load(work / "train.npz")
    t, clip = z["t"], z["clip"]
    first: dict = {}
    for i in np.where(y > 0)[0]:
        first[clip[i]] = min(first.get(clip[i], 9e9), float(t[i]))
    keep = np.ones(len(y), bool)
    for i in np.where(y > 0)[0]:
        keep[i] = t[i] >= first[clip[i]] + 0.02 + AFTER_WORD
    X, y = X[keep], y[keep]
    print("train", X.shape, int(y.sum()), "positive windows", flush=True)
    net = Net(X.shape[1], HIDDEN, rng)
    w = np.ones(len(y), np.float32)
    # Positives are rare: weighted up to a seventh of the total.
    w[y > 0] *= (w[y == 0].sum() / max(1, (y > 0).sum())) / 6
    for ep in range(EPOCHS):
        lr = 1e-3 * 0.5 * (1 + np.cos(np.pi * ep / EPOCHS))   # cosine: settles, no late swings
        order = rng.permutation(len(y))
        for i in range(0, len(y), 256):
            b = order[i:i + 256]
            net.step(X[b], y[b], w[b], lr=lr)
        if ep % 5 == 4 or ep == EPOCHS - 1:
            p = net.forward(X)
            print(f"epoch {ep + 1}: stop windows mean {p[y > 0].mean():.3f}, "
                  f"others' 99th percentile {np.percentile(p[y == 0], 99):.3f}", flush=True)

    def per_clip(split):
        Xs, _, cs, meta = load(split)
        p = net.forward(Xs)
        best = {}
        for pi, ci in zip(p, cs):
            best[int(ci)] = max(best.get(int(ci), 0.0), float(pi))
        return best, meta

    results = {}
    for thr in (0.5, 0.7, 0.8, 0.9):
        row = {}
        for split in ("test_piper", "test_kokoro"):
            best, meta = per_clip(split)
            pos = [best[c] for c in best if meta[c]["label"] == 1]
            neg = [best[c] for c in best if meta[c]["label"] == 0]
            alike = [best[c] for c in best if meta[c]["label"] == 0 and " " not in meta[c]["text"].strip()]
            row[split] = {"stop_heard": [sum(v >= thr for v in pos), len(pos)],
                          "others_fired": [sum(v >= thr for v in neg), len(neg)],
                          "sound_alikes_fired": [sum(v >= thr for v in alike), len(alike)]}
        best, meta = per_clip("stream")
        neg = [best[c] for c in best]
        hours = sum(m["seconds"] for m in meta.values()) / 3600
        fired = sum(v >= thr for v in neg)
        row["stream"] = {"sentences_fired": [fired, len(neg)], "minutes": round(hours * 60, 1),
                         "per_hour": round(fired / hours, 1)}
        results[thr] = row
        print(f"threshold {thr}: {json.dumps(row)}", flush=True)

    thr = float(os.environ.get("STOP_THRESHOLD", "0.5"))
    if thr not in results:
        print("STOP_THRESHOLD must be one of", list(results))
        return 2
    raw = head_bytes(net.p)
    # The golden file: what these numbers say for three made-up windows (a
    # formula the phone's test repeats) and one real "stop" from a held-out
    # voice - so StopWordTest checks the phone's arithmetic against the PC's.
    import jarvis_wakeword as W
    head = W.parse_stop_head(raw)
    cases = []
    for k in range(3):
        x = np.array([2.5 * np.sin(0.0137 * (i + 1) * (k + 1) + 0.5 * k) for i in range(1536)], np.float32)
        cases.append({"k": k, "p": float(W.stop_probabilities(head, x[None])[0])})
    Xs, ys, _, _ = load("test_piper")
    pos = np.where(ys > 0)[0]
    best = pos[int(np.argmax(net.forward(Xs[pos])))]
    real = Xs[best].astype(np.float32)
    golden = {"threshold": thr, "hidden": HIDDEN, "bytes": len(raw), "cases": cases,
              "stop_window": [float(v) for v in real],
              "stop_p": float(W.stop_probabilities(head, real[None])[0])}
    write(raw, thr, results[thr], golden)
    return 0


def write(raw: bytes, thr: float, measured: dict, golden: dict) -> None:
    b64 = base64.b64encode(raw).decode("ascii")
    lines = [b64[i:i + 100] for i in range(0, len(b64), 100)]
    tp, tk, st = measured["test_piper"], measured["test_kokoro"], measured["stream"]
    doc = f'''"""jarvis_stopword.py - the "stop" word's numbers.

GENERATED by tools/train_stopword.py - do not edit by hand; run that
script to remake it. Shipped whole beside jarvis_hud.py
(apply-patches.ps1 copies it); read only by jarvis_wakeword.spot_stop. The
phone ships the same bytes as assets/wakeword/stop_head.bin.

A {HIDDEN}-unit head on openWakeWord's embeddings (1,536 -> {HIDDEN} -> {HIDDEN} -> 1),
trained on SYNTHETIC voices only - Piper LibriTTS-R and Kokoro v0.19 -
saying "stop", sound-alikes and ordinary sentences. No real person's voice.
Measured on held-out synthetic voices at THRESHOLD {thr}, per clip:
  Piper speakers:  "stop" heard {tp["stop_heard"][0]}/{tp["stop_heard"][1]}; other clips fired {tp["others_fired"][0]}/{tp["others_fired"][1]}
                   (sound-alike single words {tp["sound_alikes_fired"][0]}/{tp["sound_alikes_fired"][1]})
  Kokoro voices:   "stop" heard {tk["stop_heard"][0]}/{tk["stop_heard"][1]}; other clips fired {tk["others_fired"][0]}/{tk["others_fired"][1]}
                   (sound-alike single words {tk["sound_alikes_fired"][0]}/{tk["sound_alikes_fired"][1]})
  Ordinary talk:   {st["sentences_fired"][0]} of {st["sentences_fired"][1]} sentences fired ({st["minutes"]} min of speech)
Not measured on a real voice or a real room. Licences:
THIRD-PARTY-NOTICES.txt (LibriTTS-R CC BY 4.0, Kokoro Apache-2.0; the
embedding model it sits on is openWakeWord's, CC BY-NC-SA 4.0).
"""
import base64

#: A clip's best 80 ms step at or above this is "stop". The phone's
#: StopHead.THRESHOLD (StopWord.kt) is the same number (StopWordTest).
THRESHOLD = {thr}
HIDDEN = {HIDDEN}
_HEAD = (
'''
    body = "".join(f'    "{ln}"\n' for ln in lines)
    tail = ''')


def head_bytes() -> bytes:
    """The head in jarvis_wakeword.parse_stop_head's format."""
    return base64.b64decode(_HEAD)
'''
    (REPO / "backend" / "jarvis_stopword.py").write_text(doc + body + tail)
    asset = REPO / "jarvis-client" / "app" / "src" / "main" / "assets" / "wakeword" / "stop_head.bin"
    asset.write_bytes(raw)
    (REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "stop-golden.json").write_text(
        json.dumps(golden) + "\n")
    print("wrote backend/jarvis_stopword.py and", asset.relative_to(REPO), len(raw), "bytes")


def main() -> int:
    if len(sys.argv) >= 7 and sys.argv[1] == "data":
        return data(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]), Path(sys.argv[6]))
    if len(sys.argv) >= 3 and sys.argv[1] == "train":
        return train(Path(sys.argv[2]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
