#!/usr/bin/env python3
"""Writes backend/jarvis_voicebank.py: other people's voices, as numbers, for
the voice check's comparison ("cohort") step.

    curl -sS https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz \\
        | python3 tools/gen_voicebank.py - <small model.onnx> <strong model.onnx> [speakers]

WHY. The voice check (backend/rebuilt/jarvis_voice.py, "Other voices")
lets a clip in only when it is clearly closer to the owner's print than to
other people's. "Other people" is this bank: one averaged voice print per
speaker, for each model file the check uses.

WHERE THE VOICES COME FROM. Google's Speech Commands v0.02 (Pete Warden,
2018), CC BY 4.0: about 2,600 real people, each recording short words on
their own computer or phone - so the bank has real voices through real,
varied microphones. Speakers whose anonymous id starts with 6-9 or a-f
(backend/README.md's measurements used 0-5, so the bank and the
measurements never share a voice), in id order, each with at least
16 words: two "sentences" of 8 words each, embedded, averaged. Real
voices rather than the synthetic Piper voices jarvis_wakebank.py uses:
the bank stands for the people who might be in the room, and synthetic
voices were measured to behave unlike real ones here (backend/README.md,
"The stricter voice check": the small model scored different Piper voices
as nearly the same person).

WHAT IS SHIPPED. Not audio: per model, one unit vector per speaker, 8 bits
per number with one scale per dimension (jarvis_voice.encode_bank), base64
in a Python file so apply-patches.ps1 ships it like any other module.

Needs sherpa-onnx and numpy. Deterministic for a given archive and models.
"""
import io
import json
import sys
import tarfile
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend" / "rebuilt"))
import jarvis_voice as V  # noqa: E402

KEEP = tuple("6789abcdef")
WORDS = 8
MIN_WORDS = 16
OUT = HERE.parent / "backend" / "jarvis_voicebank.py"


def trim(x: np.ndarray) -> np.ndarray:
    """The loud part of a one-second word clip (20 ms frames above 10% of
    the loudest), with 40 ms either side."""
    f = 320
    n = len(x) // f
    if n < 3:
        return x
    e = (x[: n * f].astype(np.float32).reshape(n, f) ** 2).mean(1)
    on = np.where(e > 0.1 * e.max())[0]
    if not len(on):
        return x[:0]
    return x[max(0, on[0] - 2) * f: min(n, on[-1] + 3) * f]


def read_words(src):
    """{speaker: [int16 arrays]} for the speakers this bank uses."""
    tar = tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") if src == "-" \
        else tarfile.open(src, mode="r:gz")
    words = {}
    for m in tar:
        if not m.isfile() or not m.name.endswith(".wav") or "_background_noise_" in m.name:
            continue
        spk = m.name.rsplit("/", 1)[-1].split("_nohash")[0]
        if not spk.startswith(KEEP):
            continue
        got = words.setdefault(spk, [])
        if len(got) >= MIN_WORDS:
            continue
        try:
            with wave.open(io.BytesIO(tar.extractfile(m).read())) as w:
                if w.getsampwidth() != 2 or w.getframerate() != 16000:
                    continue
                x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        except Exception:
            continue
        x = trim(x)
        if len(x) >= 3200 and np.abs(x).max() >= 800:
            got.append(x.copy())
    return words


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    src, models = sys.argv[1], sys.argv[2:4]
    speakers = int(sys.argv[4]) if len(sys.argv) > 4 else 300
    import sherpa_onnx
    words = read_words(src)
    chosen = sorted(s for s, w in words.items() if len(w) >= MIN_WORDS)[:speakers]
    if len(chosen) < 100:
        print(f"only {len(chosen)} speakers with {MIN_WORDS} words; need at least 100")
        return 1
    gap = np.zeros(800, np.float32)
    banks = {}
    for path in models:
        ext, name = V._sherpa_extractor(Path(path))
        vecs = []
        for s in chosen:
            parts = []
            for half in (0, 1):
                seq = []
                for w in words[s][half * WORDS:(half + 1) * WORDS]:
                    seq += [w.astype(np.float32) / 32768.0, gap]
                st = ext.create_stream()
                st.accept_waveform(16000, np.concatenate(seq))
                st.input_finished()
                parts.append(V._norm([float(v) for v in ext.compute(st)]))
            vecs.append(V._mean_unit(parts))
        banks[name] = V.encode_bank(
            name, vecs, f"{len(vecs)} real speakers from Google's Speech Commands v0.02 "
                        f"(CC BY 4.0), two 8-word sentences each")
        print(f"{name}: {len(vecs)} speakers, {ext.dim} numbers each")
    body = "{\n"
    for name in sorted(banks):
        doc = banks[name]
        v = doc["vectors"]
        chunks = "\n".join(f"        {v[i:i + 100]!r}" for i in range(0, len(v), 100))
        body += (f"    {name!r}: {{\n        \"model\": {name!r}, \"dim\": {doc['dim']}, "
                 f"\"speakers\": {doc['speakers']},\n        \"source\": {doc['source']!r},\n"
                 f"        \"scale\": {json.dumps(doc['scale'])},\n"
                 f"        \"vectors\": (\n{chunks}\n        ),\n    }},\n")
    body += "}"
    OUT.write_text(
        '"""jarvis_voicebank.py - other people\'s voices, as numbers.\n\n'
        "GENERATED by tools/gen_voicebank.py - do not edit by hand; run that\n"
        "script to remake it. Shipped whole beside jarvis_hud.py\n"
        "(apply-patches.ps1 copies it); read only by jarvis_voice.cohort_for.\n\n"
        f"For each voice-ID model file (by the start of its SHA-256), one averaged\n"
        f"voice print per speaker for {len(chosen)} real speakers of Google's Speech\n"
        "Commands v0.02 (Pete Warden, 2018; CC BY 4.0 - THIRD-PARTY-NOTICES.txt),\n"
        "each from two 8-word sentences. Numbers only: no audio, no words, no\n"
        "speaker ids. A clip must be clearly closer to the owner than to these.\n"
        '"""\n\n'
        f"BANKS = {body}\n", encoding="utf-8")
    print("wrote", OUT, OUT.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
