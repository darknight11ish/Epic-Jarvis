"""The animals' mouths from Kokoro's own timing (jarvis_mouth.py).

    python3 test_mouth.py

Runs anywhere; no voice model needed. The committed fixtures in
fixtures/mouth/ are two real Kokoro sentences (made on the dev machine with
the real model: the WAV say() returned, and each speech sound's time) - so
the mouth shapes are checked on Jarvis's real voice without the model.

With JARVIS_KOKORO_DIR pointing at a kokoro-en-v0_19 folder (model.onnx,
voices.bin, tokens.txt, espeak-ng-data), it also runs the real thing: the
one-time step, the timing of real sentences in all four voices checked to
the sample against sherpa-onnx, and espeak-ng's sounds checked against
piper-phonemize when that is installed. `--make-fixtures` rebuilds the
fixtures from that model.

What it proves:

  - sherpa-onnx's pause shortening, copied exactly (against a line-for-line
    reference of the C++ loop, edges included), and where every sample went;
  - how a clause ended, read from the text, as piper-phonemize has it;
  - Kokoro's token pieces (pads, the space after ".", the split at 510);
  - the mouth on real speech: m, b, p shut for their whole sound; f, v a
    lip-bite; "oo", "w" rounded, starting before the vowel; "ee" spread;
    "ah" opens more than "eh", "eh" more than "ee"; pauses shut; no jumps;
  - the "jmth" chunk: after `data`, even length, RIFF size right, and every
    backend reader (Python wave, _read_wav, jarvis_voice_flow) still reads
    the same sound; lipsync.js reads the same track (with node);
  - say(): the chunk when the timing is right, and exactly the old sound and
    no chunk on every failure; status() says how to set it up;
  - the one-time step (with onnx installed): makes the copy, leaves the
    model alone, is idempotent, refuses a model without the node.
"""
import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import traceback
import types
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, require_shipped  # noqa: E402

require_shipped("jarvis_mouth.py", "jarvis_speech.py")

import numpy as np  # noqa: E402
import jarvis_mouth as J  # noqa: E402
import jarvis_speech as S  # noqa: E402

FIX = HERE / "fixtures" / "mouth"
LIPSYNC_JS = REPO / "jarvis-desktop" / "src" / "lipsync.js"
FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="mouth-test-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


# ---------------------------------------------------------------------------
#   sherpa-onnx's ScaleSilence, transliterated line for line (the reference)
# ---------------------------------------------------------------------------

def sherpa_scale_silence(samples, sample_rate, scale):
    x = [float(v) for v in np.asarray(samples, dtype=np.float32)]
    if scale == 1:
        return np.asarray(x, np.float32)
    s32 = np.float32(scale)
    if not (np.float32(0.01) <= s32 <= np.float32(10.0)):
        return np.asarray(x, np.float32)
    threshold = int(sample_rate * 0.2)
    intervals, last, n = [], -1, len(x)
    for i in range(n):
        if abs(x[i]) <= 0.01:
            if last == -1:
                last = i
            continue
        if last != -1 and i - last < threshold:
            last = -1
            continue
        if last != -1:
            intervals.append((last, i))
            last = -1
    if last != -1 and n - last > threshold:
        intervals.append((last, n))
    if not intervals:
        return np.asarray(x, np.float32)
    out, i = [], 0
    for a, b in intervals:
        out += x[i:a]
        i = b
        length = b - a
        keep = int(np.float32(length) * s32)
        if keep <= length:
            out += x[a:a + keep]
        else:
            out += x[a:b] + [0.0] * (keep - length)
    if i < n:
        out += x[i:]
    return np.asarray(out, np.float32)


def _signal(rng, pieces):
    """[(kind, length)] -> float32: "s" speech (|x| > 0.02), "q" quiet
    (|x| <= 0.01, with values right at the 0.01 edge)."""
    parts = []
    for kind, n in pieces:
        if kind == "s":
            v = rng.uniform(0.02, 0.9, n) * rng.choice([-1, 1], n)
        else:
            v = rng.uniform(-0.01, 0.01, n)
            if n > 2:
                v[n // 2] = 0.01
                v[n // 3] = np.float32(-0.01)
        parts.append(v.astype(np.float32))
    return np.concatenate(parts) if parts else np.zeros(0, np.float32)


def t_scale_silence_is_sherpas():
    rng = np.random.default_rng(7)
    th = 4800
    shapes = [
        [("s", 500), ("q", th), ("s", 300)],                      # exactly the threshold: cut
        [("s", 500), ("q", th - 1), ("s", 300)],                  # one short: kept whole
        [("s", 500), ("q", 9000), ("s", 10), ("q", 12000)],       # a pause ending the clip
        [("s", 500), ("q", th)],                                  # final pause == threshold: kept
        [("s", 500), ("q", th + 1)],                              # final pause just over: cut
        [("q", 7000), ("s", 700), ("q", 30000), ("s", 5)],        # leading pause
        [("s", 2000)],                                            # nothing quiet
        [("q", 20000)],                                           # nothing but quiet
    ]
    for k in range(20):
        shapes.append([(("s", "q")[j % 2], int(rng.integers(1, 15000))) for j in range(9)])
    worst = 0
    for scale in (0.2, 0.5, 1.0, 1.7, 0.001):
        for shape in shapes:
            x = _signal(rng, shape)
            want = sherpa_scale_silence(x, 24000, scale)
            got, rm = J.scale_silence(x, 24000, scale)
            same = len(want) == len(got) and np.array_equal(want, got)
            if not same:
                worst += 1
            # every sample that survives lands where the remap says
            if same and len(x):
                idx = np.arange(len(x))
                mapped = np.array([rm(float(i)) for i in idx])
                dropped = np.zeros(len(x), bool)
                for a, b, delta in rm.cuts:
                    if delta > 0:
                        dropped[a:b] = True
                inside = (mapped < len(got)) & ~dropped
                ok = np.all(got[mapped[inside].astype(int)] == x[idx[inside]]) if inside.any() else True
                # and every dropped sample lands where the pause now ends
                ok = ok and all(rm(float(i)) == rm(float(b)) for a, b, d in rm.cuts if d > 0
                                for i in (a, (a + b) // 2, b - 1))
                if not ok:
                    worst += 1
    check("scale_silence() is sherpa-onnx's ScaleSilence exactly (148 signals, 5 scales, "
          "edges at the 0.2 s threshold, pauses at the start/end, scale > 1, out of range), "
          "and the remap puts every kept sample where it went", worst == 0, f"{worst} differ")
    got, rm = J.scale_silence(_signal(rng, [("s", 100), ("q", 10000), ("s", 100)]), 24000, 0.2)
    check("a 10000-sample pause keeps its first 2000 (float32 arithmetic, as sherpa-onnx)",
          len(got) == 2200 and rm(100.0) == 100.0 and rm(10100.0) == 2100.0
          and rm(5000.0) == 2100.0)


# ---------------------------------------------------------------------------
#   Words -> sounds -> tokens
# ---------------------------------------------------------------------------

def t_clause_end():
    # (text espeak consumed for one clause, more text follows, piper-phonemize's
    #  answer) - every row measured against piper-phonemize (docs/LIPSYNC.md).
    cases = [
        ("Hello, m", True, ","), ("y name is Jarvis. I", True, "."),
        ("t's 7:45 a.m. now!", False, "!"), ("hi... t", True, ""),
        ("Wait—what? (", True, "?"), ("Really.)", True, "."), (' "Yes."', True, "."),
        ("a) one; b", True, ";"), ("What?! N", True, "?"), ("Yes!? N", True, "!"),
        ("o way!!", False, "!"), ("Done.\n\nN", True, "P"), ("Done.\nN", True, "."),
        ("directions — s", True, ";"), ("ok – f", True, ";"), ("Hi… t", True, ""),
        ("well,, t", True, ","), ("thread, `", True, ","), ("claude/x`, 2", True, ","),
        ("ok \"x\".", False, "."), ("Ok…", False, ""), ("then left", False, ""),
    ]
    bad = [(c, m, w, J._clause_end(c, m)) for c, m, w in cases if J._clause_end(c, m) != w]
    check("how a clause ended, read from the text, matches piper-phonemize (22 cases)",
          not bad, str(bad))


def t_token_pieces():
    toks = {" ": 16, ".": 4, ",": 3, "h": 50, "ə": 83, "l": 54, "ˈ": 156, "o": 57, "ʊ": 135}
    got = J.token_pieces(["həlˈoʊ.", "h̃ə, ə"], toks)
    check("pieces: 0 at both ends, a space token after every '.', unknown sounds dropped",
          got[0][0] == [0, 50, 83, 54, 156, 57, 135, 4, 16, 0]
          and got[1][0] == [0, 50, 83, 3, 16, 83, 0]
          and got[0][1] == ["", "h", "ə", "l", "ˈ", "o", "ʊ", ".", " ", ""], str(got))
    long = J.token_pieces(["əəəəəəəəə"], toks, max_len=6)
    check("a sentence longer than the model takes is split as sherpa-onnx splits it "
          "(check before each sound: more than max_len - 1 already)",
          [p[0] for p in long] == [[0, 83, 83, 83, 83, 83, 0], [0, 83, 83, 83, 83, 0]],
          str([p[0] for p in long]))
    p = TMP / "tokens.txt"
    p.write_text("$ 0\n  16\n. 4\nh 50\n", encoding="utf-8")
    check("tokens.txt: a line with only a number is the space (as sherpa-onnx reads it)",
          J.read_tokens(str(p)) == {"$": 0, " ": 16, ".": 4, "h": 50})


def t_segments_fold_marks():
    segs = J.segments([("", 0.0, 0.1), ("h", 0.1, 0.15), ("ˈ", 0.15, 0.175), ("a", 0.175, 0.3),
                       ("ː", 0.3, 0.325), ("m", 0.325, 0.4), ("ˌ", 0.4, 0.425), ("t", 0.425, 0.45),
                       ("ə", 0.45, 0.5), (",", 0.5, 0.6)])
    labs = [(s[0], s[1], round(s[2], 3), round(s[3], 3), s[4]) for s in segs]
    check("stress goes to the next vowel (its time to the next sound), length marks to "
          "the sound before, h has no pull of its own, pads and commas are pauses",
          labs == [("", "REST", 0.0, 0.1, 0), ("h", "T", 0.1, 0.15, 0),
                   ("a", "V", 0.15, 0.325, 2), ("m", "BIL", 0.325, 0.4, 0),
                   ("t", "ALV", 0.4, 0.45, 0), ("ə", "V", 0.45, 0.5, 1),
                   (",", "REST", 0.5, 0.6, 0)], str(labs))


# ---------------------------------------------------------------------------
#   The mouth on Jarvis's real voice (committed fixtures)
# ---------------------------------------------------------------------------

def _fixtures():
    out = []
    for meta in sorted(FIX.glob("*.json")):
        info = json.loads(meta.read_text(encoding="utf-8"))
        wav = (FIX / info["wav"]).read_bytes()
        samples, rate = S._read_wav(wav)
        out.append((meta.stem, info, wav, samples, rate))
    return out


def _frames_in(t0, t1, n):
    a = max(0, int(math.ceil(t0 * J.FPS)))
    b = min(n - 1, int(math.floor(t1 * J.FPS)))
    return range(a, b + 1)


def t_mouth_on_real_speech():
    fx = _fixtures()
    check("the fixtures are there (two real Kokoro sentences)", len(fx) >= 2, str(len(fx)))
    for name, info, wav, samples, rate in fx:
        segs = [tuple(s) for s in info["segments"]]
        tr = J.build_track(segs, samples, rate)
        n = tr["n"]
        want = J.unpack(info["track"])
        diff = max(float(np.max(np.abs(np.asarray(tr[k]) - want[k]))) for k in
                   ("open", "wide", "round")) if want and want["n"] == n else 9
        check(f"{name}: the track is the committed one (within 2/255)", diff <= 2 / 255 + 1e-9,
              f"{diff:.4f}")
        check(f"{name}: one frame per 10 ms of the clip, like lipsync.js",
              n == J.frame_count(len(samples), rate) and n == math.ceil(len(samples) * 100 / rate))
        sl = J.segments(segs)
        o, w, r = np.asarray(tr["open"]), np.asarray(tr["wide"]), np.asarray(tr["round"])
        bil = [s for s in sl if s[1] == "BIL"]
        shut = all(o[i] <= 1e-6 for s in bil for i in _frames_in(s[2], s[3], n))
        check(f"{name}: m, b, p shut for their whole sound ({len(bil)} of them)",
              bil and shut, str([(s[0], s[2]) for s in bil]))
        lab = [s for s in sl if s[1] == "LAB"]
        bite = all(o[i] <= J.K["lab_open"] + 1e-6 for s in lab for i in _frames_in(s[2], s[3], n))
        check(f"{name}: f, v a lip-bite - barely open for their sound ({len(lab)})",
              bool(lab) == bool(info.get("has_fv")) and bite)
        # rounding: every clear "oo"/"w"/"oh" is round, and it starts early
        rounders = [s for s in sl if (s[1] == "W" or (s[1] == "V" and J._V[s[0]][2] >= 0.75))
                    and s[3] - s[2] >= 0.04]
        ok_peak = all(max(r[i] for i in _frames_in(s[2], s[3], n)) >= 0.45 for s in rounders)
        ant = []
        for s in rounders:
            prev = [q for q in sl if q[3] <= s[2] + 1e-9 and q[1] == "V"]
            if prev and s[2] - prev[-1][3] < 0.1:
                continue  # right after another vowel: nothing to anticipate across
            i = int(round((s[2] - 0.08) * J.FPS))
            if 0 <= i < n:
                ant.append((s[0], float(r[i])))
        check(f"{name}: rounded sounds round ({len(rounders)}), and the lips are already "
              f"rounding 80 ms before them", rounders and ok_peak and all(v >= 0.15 for _, v in ant),
              str(ant))
        spread = [s for s in sl if s[1] == "V" and s[0] == "i" and s[3] - s[2] >= 0.04]
        check(f"{name}: 'ee' spreads the lips ({len(spread)})",
              all(max(w[i] for i in _frames_in(s[2], s[3], n)) >= 0.4 for s in spread))
        quiet = [s for s in sl if s[1] == "REST" and s[3] - s[2] >= 0.15 and s[2] > 0.05]
        check(f"{name}: pauses shut ({len(quiet)})",
              all(o[int((s[2] + s[3]) / 2 * J.FPS)] < 0.05 for s in quiet))
        check(f"{name}: silence at the very start and end is shut", o[0] < 0.05 and o[-1] < 0.05)
        jumps = max(float(np.max(np.abs(np.diff(x)))) for x in (o, w, r))
        check(f"{name}: no jumps - at most 0.3 between two frames", jumps <= 0.3, f"{jumps:.3f}")
        check(f"{name}: wide and round are never both over 0.5",
              not np.any((w > 0.5) & (r > 0.5)))

    # Openness: "ah" > "eh" > "ee", on everything in the fixtures together.
    peaks = {"open": [], "mid": [], "close": []}
    for name, info, wav, samples, rate in fx:
        tr = J.build_track([tuple(s) for s in info["segments"]], samples, rate)
        o = np.asarray(tr["open"])
        for s in J.segments([tuple(q) for q in info["segments"]]):
            if s[1] != "V" or s[3] - s[2] < 0.05:
                continue
            group = ("open" if s[0] in "ɑaæ" else "mid" if s[0] in "ɛe" else
                     "close" if s[0] in "iɪ" else None)
            if group:
                peaks[group].append(max(o[i] for i in _frames_in(s[2], s[3], tr["n"])))
    med = {k: float(np.median(v)) if v else None for k, v in peaks.items()}
    check("vowels open by how open they are: ah > eh > ee (median peak opening)",
          None not in med.values() and med["open"] > med["mid"] > med["close"], str(med))


def _node():
    return shutil.which("node")


def t_pack_is_lipsync_js():
    fx = _fixtures()
    name, info, wav, samples, rate = fx[0]
    tr = J.build_track([tuple(s) for s in info["segments"]], samples, rate)
    s = J.pack(tr)
    back = J.unpack(s)
    check("pack() then unpack() gives the track back to the byte",
          back["n"] == tr["n"] and all(np.array_equal(J._byte(tr[k]), J._byte(back[k]))
                                       for k in ("level", "open", "wide", "round")))
    edge = {"fps": 100, "n": 3, "level": [0.5 / 255, 1.5 / 255, 2], "open": [0, 1, -1],
            "wide": [0.2, 0.4, 0.6], "round": [1, 0, 0.5]}
    node = _node()
    if not node:
        print("skip pack-vs-lipsync.js: node is not installed here")
        return
    js = ("const L=require(%s);const fs=require('fs');const a=JSON.parse(fs.readFileSync(0,'utf8'));"
          "const out={pack:L.pack(a.edge),fromWav:null};"
          "const r=L.fromWav(fs.readFileSync(a.wav));"
          "out.fromWav=r.mouth?{n:r.mouth.n,fps:r.mouth.fps,open:Array.from(r.mouth.open)}:null;"
          "out.mouthFrom=L.mouthFrom(a.payload)?L.mouthFrom(a.payload).n:null;"
          "console.log(JSON.stringify(out));") % json.dumps(str(LIPSYNC_JS))
    payload = J.read_chunk(wav)
    got = subprocess.run([node, "-e", js], input=json.dumps(
        {"edge": edge, "wav": str(FIX / info["wav"]), "payload": payload}),
        capture_output=True, text=True, timeout=60)
    try:
        out = json.loads(got.stdout)
    except Exception:
        check("lipsync.js ran", False, got.stderr[-300:])
        return
    check("pack() is byte for byte lipsync.js pack() (halves round up, clamped)",
          out["pack"] == J.pack(edge), f"{out['pack']} vs {J.pack(edge)}")
    fw = out["fromWav"]
    check("lipsync.js fromWav() finds the mouth in a WAV say() returned, the same track",
          fw is not None and fw["fps"] == 100 and fw["n"] == J.unpack(payload.split(";")[-1])["n"]
          and np.allclose(fw["open"], J.unpack(payload.split(";")[-1])["open"], atol=1e-6))
    check("lipsync.js mouthFrom() takes the payload as it is",
          out["mouthFrom"] == J.unpack(payload.split(";")[-1])["n"])


# ---------------------------------------------------------------------------
#   The chunk in the WAV, and every backend reader of it
# ---------------------------------------------------------------------------

def t_chunk_and_readers():
    rng = np.random.default_rng(3)
    x = (rng.uniform(-0.5, 0.5, 2401)).astype(np.float32)
    plain = S._write_wav(x, 24000)
    for payload in ("v1;src=kokoro;100:AAAA", "v1;src=kokoro;100:AAAAAAAA="):
        wav = J.add_chunk(plain, payload)
        size = struct.unpack("<I", wav[4:8])[0]
        check(f"chunk ({len(payload)} bytes): after data, RIFF size = file - 8, even length",
              wav.startswith(plain[:4]) and size == len(wav) - 8 and len(wav) % 2 == 0
              and wav[len(plain):len(plain) + 4] == b"jmth")
        check(f"chunk ({len(payload)} bytes) reads back", J.read_chunk(wav) == payload)
        with wave.open(io.BytesIO(wav), "rb") as w:
            frames = w.readframes(w.getnframes())
        check("Python's wave reads exactly the same sound",
              frames == plain[44:] and w.getnframes() == 2401)
        a, _ = S._read_wav(wav)
        b, _ = S._read_wav(plain)
        check("jarvis_speech._read_wav reads the same samples", np.array_equal(a, b))
        try:
            import jarvis_voice_flow as F
            c, rate = F._wav_samples(wav)
            check("jarvis_voice_flow._wav_samples (barge-in, the moment clip) reads the same",
                  np.array_equal(c, b) and rate == 24000)
        except ImportError:
            print("skip jarvis_voice_flow: not importable here")
    check("add_chunk leaves anything unexpected alone (not a WAV; no payload; bytes after the "
          "last chunk; a data chunk of size 0)",
          J.add_chunk(b"junk", "v1;x") == b"junk" and J.add_chunk(plain, None) == plain
          and J.add_chunk(plain + b"\0\0\0", "v1;x") == plain + b"\0\0\0"
          and J.add_chunk(plain[:40] + b"\0\0\0\0" + plain[44:], "v1;x")
          == plain[:40] + b"\0\0\0\0" + plain[44:])
    check("read_chunk: none in a plain WAV, none before data", J.read_chunk(plain) is None)


# ---------------------------------------------------------------------------
#   finish(): the proof that the timing is sherpa-onnx's
# ---------------------------------------------------------------------------

def _fake_job(pieces, done=True):
    job = J.Job.__new__(J.Job)
    job.pieces, job.why, job.ms = pieces, "", 1.0
    job.done = threading.Event()
    if done:
        job.done.set()
    return job


def _synthetic(frames_list, rng):
    raw = []
    for frames in frames_list:
        parts = []
        for k, f in enumerate(frames):
            n = int(f) * J.KOKORO_FRAME
            parts.append(np.zeros(n, np.float32) if k in (0, len(frames) - 1) or f >= 12
                         else (rng.uniform(0.05, 0.4, n) * np.sin(np.arange(n) * 0.3)).astype(np.float32))
        raw.append(np.concatenate(parts))
    return raw


def t_finish():
    rng = np.random.default_rng(5)
    labels = ["", "m", "ˈ", "u", "n", ",", " ", "b", "i", "."]
    frames = np.array([4, 3, 1, 6, 3, 14, 0, 2, 5, 12])
    raw = _synthetic([frames], rng)
    # 2026-09-28: the owner may pick a DEEPER animal voice too (-3..+4): f
    # below 1, the sound longer, every time divided by the same f.
    for semis in (0.0, 2.0, 4.0, -1.5, -3.0):
        f = 2.0 ** (semis / 12)
        y, rm = J.scale_silence(raw[0], 24000, 0.2)
        final = S.pitch_up(y, semis)
        got = J.finish(_fake_job([(labels, frames)]), raw, [rm], final, 24000, f)
        tr = J.unpack(got.split(";")[-1]) if got else None
        check(f"finish() makes the payload when every piece is exactly as long as the timing "
              f"says (pitch {semis:+g})", got is not None and got.startswith("v1;src=kokoro;100:")
              and tr["n"] == J.frame_count(len(final), 24000))
    before = J.status()["skipped"]
    bad = frames.copy()
    bad[3] += 1
    check("one frame out -> no payload", J.finish(_fake_job([(labels, bad)]), raw, [rm], raw[0],
                                                  24000, 1.0) is None)
    check("... and status() counts it, with why",
          J.status()["skipped"] == before + 1 and "samples" in J.status()["last_skip_why"])
    check("a different number of sentences -> no payload",
          J.finish(_fake_job([(labels, frames), (labels, frames)]), raw, [rm], raw[0], 24000,
                   1.0) is None)
    check("the timing not ready within the wait -> no payload (and no waiting past it)",
          J.finish(_fake_job([(labels, frames)], done=False), raw, [rm], raw[0], 24000, 1.0,
                   wait=0.01) is None)
    check("a piece sherpa-onnx had already shortened (no remap) -> no payload",
          J.finish(_fake_job([(labels, frames)]), raw, [None], raw[0], 24000, 1.0) is None)


# ---------------------------------------------------------------------------
#   say() and status()
# ---------------------------------------------------------------------------

class FakeAudio:
    def __init__(self, samples, rate=24000):
        self.samples, self.sample_rate = list(samples), rate


class FakeEngine:
    """generate(text, sid=, speed=) as before, and generate(text, config,
    callback) as jarvis_mouth asks: raw pieces, one per sentence."""

    def __init__(self, pieces):
        self.pieces, self.calls = pieces, []

    def generate(self, text, *args, **kw):
        if args and hasattr(args[0], "silence_scale"):
            cfg, cb = args[0], args[1]
            self.calls.append(("config", cfg.silence_scale, cfg.sid, round(cfg.speed, 4)))
            for p in self.pieces:
                if not cb(np.asarray(p, np.float32), 1.0):
                    break
            return FakeAudio(np.concatenate(self.pieces))
        self.calls.append(("old", kw.get("sid"), kw.get("speed")))
        return FakeAudio(J.scale_silence(np.concatenate(self.pieces), 24000, 0.2)[0])


def t_say():
    rng = np.random.default_rng(11)
    labels = ["", "m", "ˈ", "u", "n", ",", " ", "b", "i", "."]
    frames = np.array([4, 3, 1, 6, 3, 14, 0, 2, 5, 12])
    raw = _synthetic([frames], rng)
    orig = {n: getattr(J, n) for n in ("begin",)}
    s_orig = {n: getattr(S, n) for n in ("_tts_engine", "tts_voice")}
    real_sherpa = sys.modules.get("sherpa_onnx")
    fake_sherpa = types.SimpleNamespace(GenerationConfig=lambda: types.SimpleNamespace(
        sid=0, speed=1.0, silence_scale=0.2))
    try:
        sys.modules["sherpa_onnx"] = fake_sherpa
        eng = FakeEngine(raw)
        S._tts_engine = lambda: eng
        S.tts_voice = lambda *a: (1, 1.0, 2.0)
        J.begin = lambda *a, **k: _fake_job([(labels, frames)])
        wav = S.say("Moon, bee.")
        check("say(): a Kokoro WAV carries the mouth chunk when the timing is right",
              wav is not None and J.read_chunk(wav) is not None
              and J.read_chunk(wav).startswith("v1;src=kokoro;100:"))
        check("... sherpa-onnx was asked once, with its pause shortening off, at speed / f",
              eng.calls == [("config", 1.0, 1, round(1.0 / 2 ** (2 / 12), 4))], str(eng.calls))
        y = S.pitch_up(J.scale_silence(raw[0], 24000, 0.2)[0], 2.0)
        with wave.open(io.BytesIO(wav), "rb") as w:
            got = np.frombuffer(w.readframes(w.getnframes()), "<i2")
        check("... and the sound is the pause-shortened, pitched sound, as before",
              np.array_equal(got, np.frombuffer(S._write_wav(y, 24000)[44:], "<i2")))
        # the timing wrong: same sound, no chunk
        bad = frames.copy()
        bad[1] += 1
        J.begin = lambda *a, **k: _fake_job([(labels, bad)])
        wav2 = S.say("Moon, bee.")
        check("say(): the timing one frame out -> the same sound and no chunk",
              wav2 is not None and J.read_chunk(wav2) is None and wav2 == S._write_wav(y, 24000))
        # no durations model: exactly the old way
        J.begin = orig["begin"]
        eng.calls.clear()
        wav3 = S.say("Moon, bee.")
        check("say(): mouths not set up here -> sherpa-onnx is called exactly as before, no chunk",
              wav3 is not None and J.read_chunk(wav3) is None and eng.calls
              and eng.calls[0][0] == "old", str(eng.calls))

        # anything raising inside jarvis_mouth.speak: speak as before
        def boom(*a, **k):
            raise RuntimeError("x")
        real_speak = J.speak
        J.speak = boom
        eng.calls.clear()
        wav4 = S.say("Moon, bee.")
        J.speak = real_speak
        check("say(): jarvis_mouth failing in any way -> spoken exactly as before",
              wav4 is not None and J.read_chunk(wav4) is None and eng.calls[0][0] == "old")
    finally:
        J.begin = orig["begin"]
        for n, v in s_orig.items():
            setattr(S, n, v)
        if real_sherpa is not None:
            sys.modules["sherpa_onnx"] = real_sherpa
        else:
            sys.modules.pop("sherpa_onnx", None)
    st = S.status()["tts"]["mouth"]
    check("status(): tts.mouth is there, says whether mouths are ready and why not",
          set(st) >= {"available", "status", "made", "skipped", "last_skip_why"}
          and isinstance(st["available"], bool))


def t_ready_words():
    d = TMP / "tts"
    (d / "espeak-ng-data").mkdir(parents=True)
    for f in ("model.onnx", "voices.bin", "tokens.txt"):
        (d / f).write_bytes(b"x")
    paths = {"model": str(d / "model.onnx"), "voices": str(d / "voices.bin"),
             "tokens": str(d / "tokens.txt"), "data_dir": str(d / "espeak-ng-data")}
    ok, why = J.ready(paths)
    check("ready(): without model.durations.onnx, plain words: a one-time step, where it is "
          "written down, that the voice is not changed, and what happens meanwhile",
          not ok and "One-time step" in why and "README" in why and "not changed" in why
          and "from the sound" in why, why)
    check("begin() then gives None - nothing changes about the sound",
          J.begin("hi", 0, 1.0, paths=paths) is None)
    out = J.prepare({"model": str(TMP / "nowhere.onnx"), "voices": "", "tokens": "",
                     "data_dir": ""}, say=lambda s: None)
    check("prepare() with no voice model says so and does nothing",
          not out["ok"] and "no Kokoro voice model" in out["why"])


def _toy_model(onnx):
    """A tiny model shaped like Kokoro's inputs, with a Round -> Clip ->
    Cast(int64) duration node and an `audio` output."""
    h, T = onnx.helper, onnx.TensorProto
    nodes = [
        h.make_node("Cast", ["tokens"], ["tf"], to=T.FLOAT),
        h.make_node("ReduceMean", ["style"], ["sm"], keepdims=0),
        h.make_node("Mul", ["tf", "speed"], ["t2"]),
        h.make_node("Add", ["t2", "sm"], ["t3"]),
        h.make_node("Mul", ["t3", "k"], ["/Squeeze_output_0"]),
        h.make_node("Round", ["/Squeeze_output_0"], ["/Round_output_0"]),
        h.make_node("Clip", ["/Round_output_0", "lo"], ["/Clip_output_0"]),
        h.make_node("Cast", ["/Clip_output_0"], ["/Cast_output_0"], to=T.INT64),
        h.make_node("Cast", ["/Cast_output_0"], ["df"], to=T.FLOAT),
        h.make_node("ReduceSum", ["df"], ["audio"], keepdims=0),
    ]
    g = h.make_graph(nodes, "toy", [
        h.make_tensor_value_info("tokens", T.INT64, [1, None]),
        h.make_tensor_value_info("style", T.FLOAT, [1, 256]),
        h.make_tensor_value_info("speed", T.FLOAT, [1])],
        [h.make_tensor_value_info("audio", T.FLOAT, None)],
        initializer=[h.make_tensor("k", T.FLOAT, [], [0.1]), h.make_tensor("lo", T.FLOAT, [], [1.0])])
    m = h.make_model(g, opset_imports=[h.make_opsetid("", 17)])
    m.ir_version = 8
    m.metadata_props.add(key="style_dim", value="511,1,256")
    m.metadata_props.add(key="sample_rate", value="24000")
    return m


def t_prepare_toy_model():
    try:
        import onnx
        import onnxruntime  # noqa: F401
    except Exception:
        print("skip prepare(): onnx / onnxruntime not installed here (only the one-time step needs onnx)")
        return
    d = TMP / "toy"
    d.mkdir()
    onnx.save(_toy_model(onnx), str(d / "model.onnx"))
    np.zeros((1, 511, 256), np.float32).tofile(d / "voices.bin")
    before = (d / "model.onnx").read_bytes()
    paths = {"model": str(d / "model.onnx"), "voices": str(d / "voices.bin"),
             "tokens": str(d / "tokens.txt"), "data_dir": str(d)}
    said = []
    out = J.prepare(paths, say=said.append)
    check("prepare(): makes model.durations.onnx beside the model, says so",
          out["ok"] and out["did"] == "made" and (d / J.DURATIONS_FILE).is_file()
          and "was not changed" in said[-1], str(out))
    check("... and the voice model itself is untouched", (d / "model.onnx").read_bytes() == before)
    sub = onnx.load(str(d / J.DURATIONS_FILE))
    meta = {p.key: p.value for p in sub.metadata_props}
    check("... the copy is the slice: three inputs, the duration node as its only output, "
          "the model's notes kept, and which model it came from",
          [o.name for o in sub.graph.output] == [J.DURATION_NODE]
          and sorted(i.name for i in sub.graph.input) == ["speed", "style", "tokens"]
          and "audio" not in {o for n in sub.graph.node for o in n.output}
          and meta.get("style_dim") == "511,1,256"
          and meta.get("jarvis_source_size") == str(len(before)))
    out2 = J.prepare(paths, say=said.append)
    check("prepare() again: already done, nothing changed", out2["ok"] and out2["did"] == "already done")
    m = _toy_model(onnx)
    for n in m.graph.node:
        if n.output[0] == "/Cast_output_0":
            n.output[0] = "/Other"
        n.input[:] = ["/Other" if x == "/Cast_output_0" else x for x in n.input]
    d2 = TMP / "toy2"
    d2.mkdir()
    onnx.save(m, str(d2 / "model.onnx"))
    out3 = J.prepare({**paths, "model": str(d2 / "model.onnx")}, say=lambda s: None)
    check("prepare() refuses a model without the duration node, writes nothing, says why",
          not out3["ok"] and not (d2 / J.DURATIONS_FILE).exists() and "Kokoro v0.19" in out3["why"],
          out3["why"])


# ---------------------------------------------------------------------------
#   The real model (only with JARVIS_KOKORO_DIR)
# ---------------------------------------------------------------------------

REAL_SENTENCES = [
    "Hello, my name is Jarvis.",
    "It's 7:45 a.m. on Tuesday, September 28th.",
    "You have 2 new emails: one from Dr. Patel, and one from the U.S. Postal Service.",
    "Wait... let me check that again.",
    "Who's there? Oh, it's you!",
]
VOICES = {"default": (0, 1.0, 0.0), "panda": (1, 1.0, 2.0), "owl": (2, 0.85, 1.0),
          "otter": (4, 1.15, 3.0),
          # The deepest an owner may make an animal (2026-09-28), at a quick pace.
          "deep": (9, 1.15, -3.0)}


def _real_paths():
    d = os.environ.get("JARVIS_KOKORO_DIR")
    if not d:
        return None
    d = Path(d)
    p = {"model": str(d / "model.onnx"), "voices": str(d / "voices.bin"),
         "tokens": str(d / "tokens.txt"), "data_dir": str(d / "espeak-ng-data"),
         "lexicon": "", "dict_dir": ""}
    return p if all(Path(p[k]).exists() for k in ("model", "voices", "tokens", "data_dir")) else None


def _real_engine(p):
    import sherpa_onnx
    k = sherpa_onnx.OfflineTtsKokoroModelConfig(model=p["model"], voices=p["voices"],
                                                tokens=p["tokens"], data_dir=p["data_dir"],
                                                lang="en-us")
    cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(kokoro=k, num_threads=2))
    return sherpa_onnx.OfflineTts(cfg), cfg.silence_scale


def t_real_model():
    p = _real_paths()
    if p is None:
        print("skip the real model: set JARVIS_KOKORO_DIR to a kokoro-en-v0_19 folder to run it")
        return
    out = J.prepare(p, say=lambda s: None)
    check("real model: the one-time step works (or was already done)", out["ok"], out["why"])
    try:
        import piper_phonemize as pp
        same = all(J.phonemize(t, p["data_dir"]) == ["".join(s) for s in pp.phonemize_espeak(t, "en-us")]
                   for t in REAL_SENTENCES)
        check("real model: espeak-ng through espeakng-loader gives piper-phonemize's sounds", same)
    except ImportError:
        print("skip the piper-phonemize comparison: not installed")
    eng, scale = _real_engine(p)
    made = 0
    for name, (sid, speed, semis) in VOICES.items():
        for t in REAL_SENTENCES:
            got = J.speak(eng, t, sid, speed, semis, pitch_up=S.pitch_up, silence_scale=scale,
                          paths=p, wait=5.0)
            made += got is not None and got[2] is not None
    check(f"real model: every sentence in every voice (a deeper one too) got its mouth - the timing "
          f"matched sherpa-onnx to the sample ({made}/{len(VOICES) * len(REAL_SENTENCES)})",
          made == len(VOICES) * len(REAL_SENTENCES), J.status()["last_skip_why"])


FIXTURE_CASES = [
    # (name, voice, text, has f/v)
    ("default-lips", "default", "Please, maybe Bob moved five blue boots; we see it.", True),
    ("otter-round", "otter", "Who knew? Father's cheese fell off the boat.", True),
]


def make_fixtures():
    p = _real_paths()
    if p is None:
        print("set JARVIS_KOKORO_DIR first")
        return 1
    J.prepare(p)
    eng, scale = _real_engine(p)
    FIX.mkdir(parents=True, exist_ok=True)
    for name, voice, text, has_fv in FIXTURE_CASES:
        sid, speed, semis = VOICES[voice]
        f = 2.0 ** (semis / 12)
        job = J.begin(text, sid, speed / f, paths=p)
        job.done.wait(30)
        import sherpa_onnx
        cfg = sherpa_onnx.GenerationConfig()
        cfg.sid, cfg.speed, cfg.silence_scale = sid, speed / f, 1.0
        pieces = []
        eng.generate(text, cfg, lambda c, _p: pieces.append(np.array(c, np.float32)) or 1)
        remaps, parts = [], []
        for c in pieces:
            y, rm = J.scale_silence(c, 24000, scale)
            parts.append(y)
            remaps.append(rm)
        final = S.pitch_up(np.concatenate(parts), semis)
        segs, off = [], 0.0
        for (labels, frames), raw, rm in zip(job.pieces, pieces, remaps):
            assert int(np.sum(frames)) * 600 == len(raw)
            edges = np.concatenate(([0], np.cumsum(frames))) * 600
            for lab, a, b in zip(labels, edges[:-1], edges[1:]):
                segs.append([lab, round((off + rm(float(a))) / f / 24000, 6),
                             round((off + rm(float(b))) / f / 24000, 6)])
            off += rm(float(len(raw)))
        plain = S._write_wav(final, 24000)
        samples, rate = S._read_wav(plain)
        tr = J.build_track([tuple(s) for s in segs], samples, rate)
        payload = J.PAYLOAD_HEAD + J.pack(tr)
        (FIX / f"{name}.wav").write_bytes(J.add_chunk(plain, payload))
        (FIX / f"{name}.json").write_text(json.dumps({
            "text": text, "voice": voice, "sid": sid, "speed": speed, "semitones": semis,
            "made_with": "kokoro-en-v0_19 + sherpa-onnx 1.13.8, test_mouth.py --make-fixtures",
            "wav": f"{name}.wav", "has_fv": has_fv, "segments": segs, "track": J.pack(tr)},
            ensure_ascii=False, indent=0), encoding="utf-8")
        print("wrote", name, len(segs), "sounds", tr["n"], "frames")
    return 0


def t_shipped():
    ps = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    import _where
    check("apply-patches.ps1 and _where.SHIPPED copy jarvis_mouth.py in",
          "'jarvis_mouth.py'" in ps and "jarvis_mouth.py" in _where.SHIPPED)
    req = (HERE / "requirements.txt").read_text(encoding="utf-8")
    check("requirements.txt lists espeakng-loader and onnx",
          "\nespeakng-loader" in req and "\nonnx " in req)
    notices = (REPO / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    check("THIRD-PARTY-NOTICES.txt names espeak-ng (GPL-3), espeakng-loader and HeadTTS's table",
          "espeak-ng" in notices and "espeakng-loader" in notices and "HeadTTS" in notices)


if __name__ == "__main__":
    if "--make-fixtures" in sys.argv:
        sys.exit(make_fixtures())
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
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
