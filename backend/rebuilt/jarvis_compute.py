"""jarvis_compute.py - what runs on which card.

REBUILT. Three call sites, and between them they name every field:

    jarvis_hud.py:1425   jarvis_compute.plan().as_dict()
    jarvis_hud.py:2233   cp = jarvis_compute.plan()
    jarvis_hud.py:2234   cp.text_model, cp.text_on, cp.vision_resident,
                         cp.tts_resident, cp.simulated

`[compute] prefer` in the config is the only setting, and its own comment is
the specification:

    "speed":      the current-size model on the fastest card at full speed,
                  the second card carries vision + voice resident so nothing
                  swaps.
    "capability": the biggest model the pair can hold, generation bounded by
                  the slower card (a P100 is Pascal: ~2-3x slower per token).

`simulated` is the honest field. When no GPU can be interrogated this returns
a plan anyway - the HUD prints one at startup and must not crash on a machine
with no card - but it says so, rather than reporting a confident layout for
hardware nobody looked at.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


@dataclass
class Device:
    index: int
    name: str
    total_mb: int
    free_mb: int


@dataclass
class Plan:
    text_model: str = "unknown"
    text_on: str = "cpu"
    vision_resident: bool = False
    tts_resident: bool = False
    simulated: bool = True
    prefer: str = "speed"
    devices: list = field(default_factory=list)
    why: str = ""

    @property
    def total_mb(self) -> int:
        """Total VRAM across the cards, in MB. 0 when nothing was measured.

        jarvis_models.py:489 reads this to size its model budget:

            pl = C.plan()
            if pl.total_mb: return pl.total_mb
            ...
            return int(os.environ.get("JARVIS_VRAM_MB", "8192"))

        wrapped in `except Exception: pass`. Without the attribute the
        AttributeError was SWALLOWED and every machine silently scored its
        models against a fabricated 8192 MB. 0 here falls through to that same
        default honestly, because 0 means "no card was measured".
        """
        total = 0
        for d in self.devices:
            v = d.get("total_mb") if isinstance(d, dict) else getattr(d, "total_mb", 0)
            try:
                total += int(v or 0)
            except (TypeError, ValueError):
                continue
        return total

    def as_dict(self) -> dict:
        d = asdict(self)
        d["devices"] = [asdict(x) if not isinstance(x, dict) else x
                        for x in self.devices]
        d["total_mb"] = self.total_mb      # a property, so asdict misses it
        return d


def _cfg(key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get("compute", {}).get(key, default)
    except Exception:
        return default


def devices() -> list:
    """The GPUs, via nvidia-smi. Empty list if there are none or it is absent.

    Parsed from --query-gpu CSV rather than any library, because the backend
    is standard-library-only and a dependency here would make the startup
    banner the one thing that needs pip.
    """
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=index,name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
    except Exception:
        return []
    if out.returncode != 0:
        return []
    found = []
    for line in out.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            found.append(Device(int(parts[0]), parts[1], int(parts[2]), int(parts[3])))
        except ValueError:
            continue
    return found


def plan(model: Optional[str] = None) -> Plan:
    """Where things should run. Never raises; says `simulated` when guessing."""
    prefer = str(_cfg("prefer", "speed")).strip().lower()
    if prefer not in ("speed", "capability"):
        prefer = "speed"

    name = model or os.environ.get("JARVIS_TEXT_MODEL") or "local"
    devs = devices()

    if not devs:
        return Plan(text_model=name, text_on="cpu", vision_resident=False,
                    tts_resident=False, simulated=True, prefer=prefer,
                    devices=[],
                    why="no GPU could be interrogated; this layout is a guess")

    # Fastest card = most free memory. A crude proxy, and named as one: the
    # real answer is memory bandwidth, which nvidia-smi does not report.
    ranked = sorted(devs, key=lambda d: -d.free_mb)
    first = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None

    if prefer == "speed":
        text_on = f"cuda:{first.index}"
        # The config's own words: "the second card carries vision + voice
        # resident so nothing swaps". With one card, keeping them resident
        # would evict the text model mid-answer, so they go on demand.
        vision = tts = bool(second)
        why = ("speed: text on the freest card; "
               + ("vision and voice resident on the second"
                  if second else "one card only, so vision and voice load on demand"))
    else:
        text_on = "+".join(f"cuda:{d.index}" for d in ranked)
        vision = tts = False
        why = ("capability: the model is spread across every card, so nothing "
               "else stays resident; generation is bounded by the slowest card")

    return Plan(text_model=name, text_on=text_on, vision_resident=vision,
                tts_resident=tts, simulated=False, prefer=prefer,
                devices=[asdict(d) for d in ranked], why=why)


if __name__ == "__main__":
    for k, v in plan().as_dict().items():
        print(f"  {k:<18} {v}")
