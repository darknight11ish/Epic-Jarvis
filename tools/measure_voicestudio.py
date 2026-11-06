#!/usr/bin/env python3
"""Re-report the VoiceStudio measurements, and never repeat the heavy work.

    py -3 -B tools/measure_voicestudio.py
    py -3 -B tools/measure_voicestudio.py --json
    py -3 -B tools/measure_voicestudio.py --measure-warm   # one live call, opt-in

WHY THIS EXISTS

The heavy measurement is DONE and its evidence is authoritative:
`VOICESTUDIO-EVAL/MEASURE/RESULTS.md` (2026-11-04, 390 lines, raw logs and
`nvidia-smi` samples under `MEASURE/evidence/`). It installed a 11.61 GB
environment, downloaded 3.043 GB of model weights and took 268 s of first
call. Repeating any of that would be a live model change on the owner's PC and
a large download for no new fact. So this harness does not reinstall, does not
re-download, does not start or stop VoiceStudio, and does not unload anything:
it RE-REPORTS.

Three kinds of line, always labelled, never mixed:

    MEASURED   a fact from the 2026-11-04 record, quoted from the client's own
               constants (`backend/jarvis_voicestudio.py`), with its source.
    LIVE       a fact read right now, read-only: the cards, the lanes on
               11435/11436, and VoiceStudio's own /health, /startup/progress
               and /model/loaded if it is running.
    BLOCKED    something that could not be read, or that this harness refuses
               to do. A BLOCKED line is NEVER a pass, and it says why.

WHAT IT REFUSES, ON PURPOSE

* It never calls `jarvis_voicestudio.stop()`, `/model/unload/*`, or anything
  else that would free a model. Freeing a model is the launcher's `-Stop` (the
  process this script did not start) or the owner's own unload line for the
  11435 lane - a person's decision, not a measurement's.
* `--unload` exists only to be REFUSED, so the refusal is testable and clear.
* `--measure-warm` is the one live call, opt-in, and only when VoiceStudio
  already has a model loaded: a call that would LOAD one is refused, because
  loading is a live model change and the load path is what the record already
  measured (267.97 s first, 27.41 s after a restart).
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

import jarvis_voicestudio as VS  # noqa: E402

SECOND_CARD_LANE = 11435
EVERYDAY_LANE = 11436
LANES = ((SECOND_CARD_LANE, "the second card (RTX 2080 SUPER)"),
         (EVERYDAY_LANE, "the everyday card (RTX 2060)"))
WARM_SENTENCE = "This sentence is the warm-latency probe the measurement used."
STATUS_WIDTH = 9


def label(kind: str, name: str, value: str, note: str = "") -> None:
    """One report line, always starting with its kind so nothing is ambiguous."""
    line = f"{kind:<{STATUS_WIDTH}} {name:<46} {value}"
    if note:
        line += f"  ({note})"
    print(line)


def head(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


# ---------------------------------------------------------------------------
#   MEASURED: the record, straight from the client's constants
# ---------------------------------------------------------------------------

def report_the_record() -> dict:
    facts = VS.measured()
    head("MEASURED - the 2026-11-04 record this feature is built around")
    label("MEASURED", "first start -> /health 200", f"{facts['startup_first_seconds']} s")
    label("MEASURED", "later start -> /health 200", f"{facts['startup_later_seconds']} s")
    label("MEASURED", "model preload after health", f"{facts['preload_seconds']} s")
    label("MEASURED", "first ever speech call", f"{facts['first_call_seconds']} s",
          "download 3.043 GB + load + generate")
    label("MEASURED", "warm speech call",
          f"{facts['warm_call_seconds'][0]}-{facts['warm_call_seconds'][1]} s",
          "for ~2.5 s of audio")
    label("MEASURED", "real-time factor (warm)",
          f"{facts['warm_call_rtf'][0]}-{facts['warm_call_rtf'][1]}")
    label("MEASURED", "resident VRAM", f"{facts['resident_vram_mb']} MB",
          "app-reported; nvidia-smi delta ~1,750-1,900 MiB")
    label("MEASURED", "idle RAM (no model)", f"{facts['idle_ram_mb']} MB")
    label("MEASURED", "weights on disk", f"{facts['weights_bytes'] / 1e9:.3f} GB",
          "never shipped, never downloaded by this harness")
    label("MEASURED", "free VRAM at the measured peak",
          f"{facts['peak_free_vram_mib']} MiB", "the CONTENTION verdict")
    label("MEASURED", "coexistence verdict", facts["coexistence"],
          "demand-only, serialised, never resident beside Jarvis")
    label("MEASURED", "source", facts["source"])
    label("MEASURED", "bind", f"{VS.HOST}:{VS.PORT}", "loopback only, no LAN socket")
    return facts


# ---------------------------------------------------------------------------
#   LIVE: the cards, read with nvidia-smi
# ---------------------------------------------------------------------------

def report_gpus() -> list:
    head("LIVE - the cards, read now with nvidia-smi (nothing is changed)")
    exe = shutil.which("nvidia-smi")
    if not exe:
        label("BLOCKED", "nvidia-smi", "not found", "the cards cannot be read on this PC")
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=index,uuid,name,memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30)
    except Exception as exc:                              # noqa: BLE001
        label("BLOCKED", "nvidia-smi", type(exc).__name__, str(exc)[:120])
        return []
    if out.returncode != 0:
        label("BLOCKED", "nvidia-smi", f"exit {out.returncode}", (out.stderr or "")[:120])
        return []
    rows = []
    for line in out.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        row = {"index": int(parts[0]), "uuid": parts[1], "name": parts[2],
               "total": int(parts[3]), "used": int(parts[4]), "free": int(parts[5])}
        rows.append(row)
        marker = ""
        if "2080" in row["name"].upper():
            marker = "VoiceStudio is pinned here"
        elif "2060" in row["name"].upper():
            marker = "the everyday lane; must never be touched"
        label("LIVE", f"GPU {row['index']} {row['name']}",
              f"used {row['used']} / {row['total']} MiB, free {row['free']} MiB", marker)
    if not rows:
        label("BLOCKED", "the cards", "nvidia-smi returned nothing usable", "")
    return rows


# ---------------------------------------------------------------------------
#   LIVE: what is resident on the two Ollama lanes
# ---------------------------------------------------------------------------

def report_lanes() -> dict:
    head("LIVE - what is resident on Jarvis's own lanes (read-only GET /api/ps)")
    out = {}
    for port, what in LANES:
        url = f"http://127.0.0.1:{port}/api/ps"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=3) as reply:
                body = json.loads(reply.read().decode("utf-8", "replace") or "{}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            label("BLOCKED", f"lane {port} ({what})", "did not answer", type(exc).__name__)
            out[port] = None
            continue
        models = [m for m in (body.get("models") or []) if isinstance(m, dict)]
        if not models:
            label("LIVE", f"lane {port} ({what})", "no model resident")
            out[port] = []
            continue
        out[port] = models
        for model in models:
            size_gb = float(model.get("size") or 0) / 1e9
            expires = str(model.get("expires_at") or "")
            # Ollama writes a far-future placeholder for keep_alive = -1, which
            # is the owner's OLLAMA_KEEP_ALIVE setting. Say "never" rather than
            # print a year that is not a real date.
            if expires[:4].isdigit() and int(expires[:4]) > 2100:
                expires = "never (the owner keeps it loaded)"
            elif not expires:
                expires = "at its own time"
            label("LIVE", f"lane {port} ({what})", f"{model.get('name')}",
                  f"{size_gb:.2f} GB VRAM, unloads {expires}")
    return out


# ---------------------------------------------------------------------------
#   LIVE: the sidecar itself. Read-only, and never started here.
# ---------------------------------------------------------------------------

def report_sidecar() -> dict:
    head("LIVE - VoiceStudio on 127.0.0.1:11439 (read-only; this harness never starts it)")
    state = {"running": False, "loaded": 0}
    listener = _listening()
    label("LIVE", f"port {VS.PORT}", "listening" if listener else "nobody listening")
    health = VS.health()
    state["running"] = bool(health.get("running"))
    if health.get("running") is False:
        label("BLOCKED", "VoiceStudio health", "not running",
              f"start it with: {VS.START_COMMAND}")
        label("BLOCKED", "startup, health and model checks", "no process to ask", "NOT a pass")
        label("MEASURED", "when it does start", f"{VS.STARTUP_FIRST_SECONDS} s first, "
              f"{VS.STARTUP_WARM_SECONDS} s later", "so a wait is normal, not a failure")
        return state
    if health.get("ready"):
        label("LIVE", "VoiceStudio health", "ready",
              f"{health.get('device') or 'device unknown'}, version "
              f"{health.get('version') or 'unknown'}")
    else:
        label("LIVE", "VoiceStudio health", "starting",
              f"{health.get('label') or health.get('step') or 'no step reported'}")
        progress = VS.startup_progress()
        if progress.get("elapsed_s") is not None:
            label("LIVE", "startup progress", f"{progress['elapsed_s']} s",
                  "this is the measured 16.66-32.06 s window, so it is expected")
    loaded = VS.model_loaded()
    count = int(loaded.get("count") or 0)
    state["loaded"] = count
    if count:
        for model in loaded.get("models") or []:
            label("LIVE", "model loaded", f"{model.get('id')} {model.get('name')}",
                  f"{model.get('vram_mb')} MB, unloadable={model.get('unloadable')}")
    else:
        label("LIVE", "model loaded", "none", "not holding the card right now")
    return state


def _listening() -> bool:
    sock = socket.socket()
    sock.settimeout(0.5)
    try:
        return sock.connect_ex((VS.HOST, VS.PORT)) == 0
    finally:
        sock.close()


# ---------------------------------------------------------------------------
#   The one live call, opt-in, and only when a model is ALREADY loaded
# ---------------------------------------------------------------------------

def report_warm(loaded: int, measure: bool) -> None:
    head("WARM LATENCY")
    label("MEASURED", "warm speech call",
          f"{VS.WARM_CALL_SECONDS[0]}-{VS.WARM_CALL_SECONDS[1]} s",
          "the record; this is not re-timed by default")
    if not measure:
        label("BLOCKED", "re-timing it now", "not asked for",
              "pass --measure-warm; this harness does not touch a live model by default")
        return
    if not loaded:
        label("BLOCKED", "re-timing it now", "no model loaded",
              "a call now would LOAD one, which is a live model change - refused")
        return
    started = time.monotonic()
    try:
        audio = VS.synthesize(WARM_SENTENCE)
    except VS.VoiceStudioError as exc:
        label("BLOCKED", "re-timing it now", type(exc).__name__, exc.words[:150])
        return
    seconds = time.monotonic() - started
    duration = _wav_seconds(audio)
    if duration:
        label("LIVE", "warm speech call now", f"{seconds:.2f} s",
              f"{duration:.2f} s of audio, RTF {seconds / duration:.2f}")
    else:
        label("LIVE", "warm speech call now", f"{seconds:.2f} s",
              f"{len(audio)} bytes, format {VS.sniff_format(audio) or 'unknown'}")


def _wav_seconds(audio: bytes) -> float:
    """Duration of a WAV body, read from its own header. 0.0 if not a WAV."""
    try:
        if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            return 0.0
        pos = 12
        rate = channels = bits = 0
        while pos + 8 <= len(audio):
            chunk = audio[pos:pos + 4]
            size = struct.unpack("<I", audio[pos + 4:pos + 8])[0]
            body = audio[pos + 8:pos + 8 + size]
            if chunk == b"fmt " and len(body) >= 16:
                channels, rate = struct.unpack("<H", body[2:4])[0], struct.unpack("<I", body[4:8])[0]
                bits = struct.unpack("<H", body[14:16])[0]
            elif chunk == b"data" and rate and channels and bits:
                return len(body) / float(rate * channels * (bits // 8))
            pos += 8 + size + (size % 2)
        return 0.0
    except Exception:                                     # noqa: BLE001
        return 0.0


# ---------------------------------------------------------------------------
#   What this harness refuses, said out loud
# ---------------------------------------------------------------------------

def report_refusals() -> None:
    head("WHAT THIS HARNESS WILL NOT DO")
    label("BLOCKED", "unload a model", "refused",
          "freeing a model is the launcher's -Stop or the owner's own 11435 line")
    label("BLOCKED", "start or stop VoiceStudio", "refused", "that is tools/voicestudio_sidecar.ps1")
    label("BLOCKED", "download weights (3.043 GB)", "refused", "the record already has that fact")
    label("BLOCKED", "install or reinstall anything", "refused", "the measurement is done")
    label("BLOCKED", "accept a model licence", "refused", "the owner's yes, in VoiceStudio's terms")
    label("BLOCKED", "touch the 2060 lane (11436)", "refused", "every read only; nothing is unloaded")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-report the VoiceStudio measurement. Read-only unless --measure-warm.")
    parser.add_argument("--json", action="store_true", help="also print one JSON object")
    parser.add_argument("--measure-warm", action="store_true",
                        help="time ONE speech call, only if a model is already loaded")
    parser.add_argument("--unload", action="store_true",
                        help="refused on purpose: this harness never frees a model")
    args = parser.parse_args(argv)

    if args.unload:
        print("REFUSED - this harness never unloads a model.")
        print("Freeing a model is a person's decision: run "
              "tools\\voicestudio_sidecar.ps1 -Stop (VoiceStudio's own process), or the owner's "
              "line for the 11435 lane that -Start prints when the card is full.")
        return 2

    print("VoiceStudio measurement, re-reported. Nothing here starts, stops, downloads, installs")
    print("or unloads anything. A BLOCKED line is never a pass.")
    facts = report_the_record()
    gpus = report_gpus()
    lanes = report_lanes()
    sidecar = report_sidecar()
    report_warm(sidecar.get("loaded", 0), args.measure_warm)
    report_refusals()

    if args.json:
        print()
        print(json.dumps({"measured": facts, "gpus": gpus,
                          "lanes": {str(k): v for k, v in lanes.items()},
                          "sidecar": sidecar}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
