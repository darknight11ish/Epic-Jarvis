"""jarvis_f5_worker.py - the better voice (F5-TTS), as its own program, on the second card.

NEW FILE, shipped whole beside jarvis_hud.py. Nothing imports it: only
jarvis_voices.py STARTS it, as a separate process, when the owner has
switched the better voice on (an approval card) and Jarvis is about to speak
in a custom voice. It is stopped after idle minutes, in standby and when the
switch goes off, so it does not hold graphics memory all the time.

WHY A SEPARATE PROCESS. F5-TTS runs on PyTorch with CUDA: a large import, a
model on the graphics card, and memory that is only really given back when
the process ends. Keeping it out of the server means stopping it frees the
card completely, and a crash in it cannot take Jarvis down.

HOW IT IS TALKED TO: its standard input and output, one JSON line each way.
No port, no socket - nothing on the network can reach it, and it reaches
nothing (test_voices.py scans this file for network calls).

    out  {"ready": true, "device": "cuda", "load_seconds": 41.2}
         or {"ready": false, "error": "<what went wrong>"}   then it exits
    in   {"id": 1, "text": "...", "ref_audio": "<clip.wav>", "ref_text": "...", "speed": 1.0}
    out  {"id": 1, "ok": true, "sample_rate": 24000, "audio": "<base64 16-bit PCM>", "seconds": 0.8}
         or {"id": 1, "ok": false, "error": "<the error's NAME only>"}
    in   {"cmd": "quit"}

WHAT IS NEVER WRITTEN ANYWHERE. F5-TTS prints the reference transcript and
progress bars. Everything this process prints - Python's and the native
libraries' - goes to the null device; only the protocol lines above reach the
real standard output (a copy of it taken before anything could print), and
jarvis_voices.py discards standard error. An error on a sentence sends the
error's type name only, never its message, which could quote the text.

THE MODEL FILES are local (jarvis_voices.py passes their paths) and the
Hugging Face libraries are told they are offline (HF_HUB_OFFLINE and friends
in the environment jarvis_voices.worker_env() builds), so nothing is
downloaded when it starts. F5-TTS's weights are CC-BY-NC (non-commercial),
which this build is (CLAUDE.md rule 5); its code is MIT.

NOT RUN ON A GRAPHICS CARD by anyone working on this project: there was none
where it was written. test_voices.py runs this file for real with stand-ins
for PyTorch and F5-TTS; the real ones are the owner's first run.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

#: The three F5-TTS files, by SHA-256, taken from the Hugging Face file
#: metadata the install line in backend/README.md downloads (2026-10-18, the
#: security audit's supply-chain finding M8). The owner's copy is verified
#: before PyTorch or F5-TTS is imported: a changed or truncated file refuses
#: with a plain sentence instead of being loaded. The README's install line
#: prints these hashes so a fresh download can be compared too.
F5_PINNED = {
    "checkpoint": "670900fd14e6c458b95da6e9ed317cdb20dbaf7a1c02ac6a05475a9d32b6a38",
    "vocoder model": "97ec976ad1fd67a33ab2682d29c0ac7df85234fae875aefcc5fb215681a91b2a",
    "vocoder config": "da9033922f969a47f0c160010226919e59f27761fd5066f3828d46de6650b0fc",
}


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_model_files(checkpoint, vocoder_dir) -> None:
    """Refuse the F5-TTS files unless their bytes match the pinned SHA-256.

    `checkpoint` is the .safetensors file; `vocoder_dir` holds
    `pytorch_model.bin` and `config.yaml` - exactly what the install line in
    backend/README.md downloads. Called before any import of torch/f5_tts, so a
    changed file is never handed to the model loader.
    """
    root = Path(str(vocoder_dir))
    files = (
        ("checkpoint", Path(str(checkpoint)), F5_PINNED["checkpoint"]),
        ("vocoder model", root / "pytorch_model.bin", F5_PINNED["vocoder model"]),
        ("vocoder config", root / "config.yaml", F5_PINNED["vocoder config"]),
    )
    for label, path, expected in files:
        if not path.is_file():
            raise RuntimeError(
                f"the F5-TTS {label} is missing at {path}; nothing was loaded. "
                "backend/README.md, \"The better voice\", has the install line.")
        got = _file_sha256(path)
        if got.lower() != expected:
            raise RuntimeError(
                f"the F5-TTS {label} at {path} does not match its pinned SHA-256, "
                "so nothing was loaded. Download the model files again with the "
                "line in backend/README.md, \"The better voice\", and check the "
                "hashes it prints.")


def _args(argv):
    ap = argparse.ArgumentParser(description="Jarvis's better voice (F5-TTS). Started by "
                                             "jarvis_voices.py; not meant to be run by hand.")
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--vocoder", required=True)
    ap.add_argument("--model", default="F5TTS_v1_Base")
    ap.add_argument("--nfe", type=int, default=32)
    ap.add_argument("--device", default="cuda")
    return ap.parse_args(argv)


def load(args):
    """The F5-TTS model, on the card. Raises with a plain reason."""
    verify_model_files(args.checkpoint, args.vocoder)   # before torch/F5-TTS load
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE",
              "HF_HUB_DISABLE_TELEMETRY"):
        os.environ.setdefault(k, "1")
    import torch
    if str(args.device).startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("PyTorch cannot see the graphics card - is the CUDA build of "
                           "PyTorch installed? (backend/README.md, \"The better voice\")")
    from f5_tts.api import F5TTS
    return F5TTS(model=args.model, ckpt_file=args.checkpoint,
                 vocoder_local_path=args.vocoder, device=args.device)


def _quiet(*_a, **_k):
    return None


def _pcm16(wav) -> bytes:
    import numpy as np
    x = np.clip(np.asarray(wav, dtype=np.float32).reshape(-1), -1.0, 1.0)
    return (x * 32767.0).astype("<i2").tobytes()


def serve(engine, lines, send, nfe: int = 32) -> int:
    """Answer requests until "quit" or the end of input."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            send({"ok": False, "error": "bad request"})
            continue
        if not isinstance(req, dict):
            send({"ok": False, "error": "bad request"})
            continue
        if req.get("cmd") == "quit":
            return 0
        rid = req.get("id")
        try:
            t = time.monotonic()
            wav, sr, _spec = engine.infer(
                ref_file=str(req["ref_audio"]), ref_text=str(req["ref_text"]),
                gen_text=str(req["text"]), show_info=_quiet, nfe_step=int(nfe),
                speed=float(req.get("speed", 1.0)), remove_silence=False)
            send({"id": rid, "ok": True, "sample_rate": int(sr),
                  "audio": base64.b64encode(_pcm16(wav)).decode("ascii"),
                  "seconds": round(time.monotonic() - t, 3)})
        except Exception as exc:
            # The NAME only: a message could quote the sentence.
            send({"id": rid, "ok": False, "error": type(exc).__name__})
    return 0


def _protocol_out():
    """A private copy of the real standard output for the protocol, and the
    null device everywhere anything else might print."""
    fd = os.dup(1)
    out = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.dup2(null, 2)
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
    sys.stderr = sys.stdout
    return out


def main(argv=None) -> int:
    out = _protocol_out()

    def send(msg: dict) -> None:
        out.write(json.dumps(msg) + "\n")
        out.flush()

    try:
        args = _args(argv)
    except SystemExit:
        send({"ready": False, "error": "bad arguments"})
        return 2
    t = time.monotonic()
    try:
        engine = load(args)
    except Exception as exc:
        # Loading has been given no text or recording yet, so the message is
        # safe to pass on - and "No module named 'f5_tts'" is the useful part.
        msg = str(exc).strip()
        send({"ready": False, "error": (f"{type(exc).__name__}: {msg}" if msg
                                        else type(exc).__name__)[:300]})
        return 1
    send({"ready": True, "device": str(args.device),
          "load_seconds": round(time.monotonic() - t, 1)})
    return serve(engine, sys.stdin, send, args.nfe)


if __name__ == "__main__":
    raise SystemExit(main())
