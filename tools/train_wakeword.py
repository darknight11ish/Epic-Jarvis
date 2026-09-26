#!/usr/bin/env python3
"""Trains the CANDIDATE "hey Jarvis" detector with livekit-wakeword, on the
owner's PC, for the bake-off (backend/jarvis_bakeoff.py) to measure.

    <its own Python> tools/train_wakeword.py [--work DIR] [--check]

Run by the one PowerShell line in backend/README.md ("Voice upgrades: the
bake-off", step 2), which first makes a SEPARATE Python for it
(%USERPROFILE%\\.openjarvis\\wake-training\\venv) and installs
livekit-wakeword there, pinned to one commit. Never in the Python that runs
Jarvis: training pulls in PyTorch and a large tool chain, and nothing of it
may end up where Jarvis's backend imports from (the security review's
condition, docs/feasibility-2026-09-26/security.md, I15).

WHAT IT DOES, in order - and it stops, in plain words, before anything big
is downloaded if something is missing:

  1. Checks: Python 3.11 or newer; livekit-wakeword installed at the pinned
     commit; PyTorch can see the graphics card, with at least 5 GB of its
     memory free (Jarvis on Standby frees it - the chat model is unloaded);
     the espeak-ng program (the training's pronouncer) on the PATH; 40 GB
     free on the disk.
  2. Writes the training settings (below) into the work folder.
  3. `livekit-wakeword setup`: downloads what training needs - the Piper
     voice (about 166 MB, from livekit-wakeword's GitHub release), the
     general-speech numbers (about 16 GB, from Hugging Face), background
     noise (about 1.1 GB) and room echoes (8 MB).
  4. `livekit-wakeword run`: makes synthetic "hey Jarvis" clips and look-alike
     phrases, trains, exports the model file, and scores it on its own
     validation set. Hours, on the graphics card.
  5. Copies the model to <config>\\voice-models\\wakeword\\hey_jarvis_livekit.onnx
     and writes hey_jarvis_livekit.json beside it: its SHA-256, the
     livekit-wakeword commit, the threshold livekit-wakeword's own
     validation picked, and when. jarvis_wakeword.candidate_status() refuses
     the file if either no longer matches. NOTHING IS SWITCHED ON: only the
     bake-off reads it.

`--check` does step 1 only.

Licences: livekit-wakeword is Apache-2.0. The Piper voice it synthesises
with is trained on LibriTTS-R (CC BY 4.0). The general-speech numbers are
openWakeWord's (ACAV100M-derived; openWakeWord's own models are CC
BY-NC-SA 4.0), so the trained model is treated as non-commercial, like
today's (rule 5). THIRD-PARTY-NOTICES.txt has the lines.

NOT RUN ANYWHERE YET. The dev container that wrote this has no graphics
card and cannot reach Hugging Face; livekit-wakeword documents Linux and
macOS for training, not Windows. If a step fails on Windows, the error is
printed as it is - send it back.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

LIVEKIT_COMMIT = "95448a7559c453fcd87645bd67b247ffb45f85b0"
MODEL_NAME = "hey_jarvis"
CANDIDATE_FILE = "hey_jarvis_livekit.onnx"
CANDIDATE_MANIFEST = "hey_jarvis_livekit.json"
MIN_FREE_GB = 40
MIN_VRAM_GB = 5

#: livekit-wakeword's own production settings (configs/prod.yaml at the
#: pinned commit), with the phrase, its look-alikes and the paths changed.
#: The look-alikes are what a "hey Jarvis" detector must NOT wake for:
#: sound-alike names and phrases, and the bare name in a sentence.
CONFIG = f"""\
model_name: {MODEL_NAME}
target_phrases: ["hey jarvis"]
n_samples: 25000
n_samples_val: 5000
n_background_samples: 2000
n_background_samples_val: 500
tts_batch_size: 50
custom_negative_phrases:
  - "jarvis"
  - "hey jason"
  - "hey travis"
  - "hey marvin"
  - "hey harvest"
  - "hey service"
  - "jar of jam"
  - "hey java"
  - "hey jars"
  - "they carve this"
  - "hey there"
  - "the computer was called jarvis"
noise_scales: [0.98]
noise_scale_ws: [0.98]
length_scales: [0.75, 1.0, 1.25]
slerp_weights: [0.2, 0.35, 0.5, 0.65, 0.8]
data_dir: ./data
output_dir: ./output
augmentation:
  clip_duration: 2.0
  batch_size: 16
  rounds: 3
  background_paths: [./data/backgrounds]
  rir_paths: [./data/rirs]
model:
  model_type: conv_attention
  model_size: medium
steps: 100000
learning_rate: 0.0001
weight_decay: 0.01
label_smoothing: 0.05
max_negative_weight: 3000
target_fp_per_hour: 0.1
batch_n_per_class:
  positive: 50
  adversarial_negative: 50
  ACAV100M_sample: 1024
  background_noise: 50
"""


def config_dir() -> Path:
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".openjarvis"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def installed_commit() -> str:
    """The commit pip installed livekit-wakeword from (its direct_url.json),
    or ""."""
    try:
        from importlib import metadata
        dist = metadata.distribution("livekit-wakeword")
        raw = dist.read_text("direct_url.json") or "{}"
        return str(json.loads(raw).get("vcs_info", {}).get("commit_id", ""))
    except Exception:
        return ""


def checks(work: Path) -> list:
    """Every problem, in plain words; [] means ready."""
    bad = []
    if sys.version_info < (3, 11):
        bad.append(f"This Python is {sys.version.split()[0]}; livekit-wakeword needs 3.11 or "
                   f"newer.")
    import importlib.util
    try:
        found = importlib.util.find_spec("livekit.wakeword") is not None
    except (ImportError, ValueError):
        found = False
    if not found:
        bad.append("livekit-wakeword is not installed in this Python (the line in "
                   "backend/README.md installs it).")
    else:
        got = installed_commit()
        if got != LIVEKIT_COMMIT:
            bad.append(f"livekit-wakeword is installed from {got[:12] or 'somewhere else'}, not "
                       f"the pinned commit {LIVEKIT_COMMIT[:12]}. Run the install line again.")
    try:
        import torch
        if not torch.cuda.is_available():
            bad.append("PyTorch cannot see the graphics card (it is the processor-only "
                       "PyTorch, or the driver is too old). Training on the processor would "
                       "take days.")
        else:
            free, _total = torch.cuda.mem_get_info()
            if free < MIN_VRAM_GB * 1024 ** 3:
                bad.append(f"Only {free / 1024 ** 3:.1f} GB of the graphics card's memory is "
                           f"free; training needs about {MIN_VRAM_GB} GB. Put Jarvis on "
                           f"Standby first (it unloads the chat model), then run this again.")
    except Exception:
        bad.append("PyTorch is not installed in this Python.")
    if not shutil.which("espeak-ng"):
        bad.append("The espeak-ng program is not on the PATH. Install it from "
                   "https://github.com/espeak-ng/espeak-ng/releases (the .msi), then open a "
                   "new PowerShell window.")
    try:
        work.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(work).free
        if free < MIN_FREE_GB * 1024 ** 3:
            bad.append(f"Only {free / 1024 ** 3:.0f} GB free on the disk that holds {work}; "
                       f"training needs about {MIN_FREE_GB} GB.")
    except OSError as exc:
        bad.append(f"Could not use {work} ({type(exc).__name__}).")
    return bad


def run(cmd: list, cwd: Path) -> int:
    print("  > " + " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(cwd))


def verify_onnx(p: Path) -> str:
    """"" when the model takes (batch, 16, 96) and gives (batch, 1), else why."""
    try:
        import onnxruntime as ort
        s = ort.InferenceSession(str(p), providers=["CPUExecutionProvider"])
    except Exception as exc:
        return f"it does not load ({type(exc).__name__})"
    i, o = s.get_inputs(), s.get_outputs()
    if len(i) != 1 or list(i[0].shape)[1:] != [16, 96] or list(o[0].shape)[1:] != [1]:
        return f"it takes {[x.shape for x in i]} and gives {[x.shape for x in o]}"
    return ""


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    work = config_dir() / "wake-training"
    if "--work" in argv:
        work = Path(argv[argv.index("--work") + 1])
    print("Training the new \"hey Jarvis\" detector (livekit-wakeword) for the bake-off.")
    print(f"Work folder: {work}")
    bad = checks(work)
    if bad:
        print("Not started - fix these first:")
        for b in bad:
            print(f"  - {b}")
        return 1
    print("Ready: Python, livekit-wakeword, the graphics card, espeak-ng and the disk.")
    if "--check" in argv:
        return 0
    cfg = work / f"{MODEL_NAME}.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    cli = [sys.executable, "-m", "livekit.wakeword"]
    print("Step 1 of 2: downloading what training needs (about 18 GB; it can take hours).")
    if run(cli + ["setup", "--config", str(cfg)], work) != 0:
        print("The download step failed; the message above says why.")
        return 1
    print("Step 2 of 2: training (hours, on the graphics card; Jarvis stays on Standby).")
    t = time.time()
    if run(cli + ["run", str(cfg)], work) != 0:
        print("Training failed; the message above says why.")
        return 1
    out = work / "output" / MODEL_NAME
    onnx, evaluation = out / f"{MODEL_NAME}.onnx", out / f"{MODEL_NAME}_eval.json"
    if not onnx.is_file():
        print(f"Training ended but {onnx} is not there.")
        return 1
    why = verify_onnx(onnx)
    if why:
        print(f"The trained model cannot run on Jarvis's front end: {why}.")
        return 1
    try:
        ev = json.loads(evaluation.read_text(encoding="utf-8"))
    except Exception:
        ev = {}
    dest = config_dir() / "voice-models" / "wakeword"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(onnx, dest / CANDIDATE_FILE)
    sha = sha256_file(dest / CANDIDATE_FILE)
    manifest = {
        "version": 1, "file": CANDIDATE_FILE, "sha256": sha, "livekit_commit": LIVEKIT_COMMIT,
        # Chosen on livekit-wakeword's own validation set, never on the
        # bake-off's clips: fixed before the bake-off runs.
        "threshold": float(ev.get("optimal_threshold", 0.5) or 0.5),
        "evaluation": {k: ev.get(k) for k in ("aut", "fpph", "recall", "optimal_threshold",
                                              "optimal_recall", "optimal_fpph",
                                              "validation_hours")},
        "config_sha256": hashlib.sha256(CONFIG.encode("utf-8")).hexdigest(),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hours": round((time.time() - t) / 3600, 2),
    }
    (dest / CANDIDATE_MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n",
                                           encoding="utf-8")
    print(f"Done. The new detector is {dest / CANDIDATE_FILE}")
    print(f"  SHA-256 {sha}")
    print("Nothing was switched on. Take Jarvis off Standby, then run the bake-off line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
