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

WHICH CARD IS "FIRST" (fixed 2026-09-24). This used to rank "fastest card =
most free memory". With the second card the owner is adding - an RTX 2060
12 GB beside the 2080 Super 8 GB - that put everyday chat on the 2060: more
free memory, about two thirds the memory speed (docs/MODEL-TOPOLOGY.md, "The
planned second card"). The everyday card is now chosen by one rule, which
jarvis_second_card.py uses too (it imports it from here):

    1. `[compute] primary_gpu` in the toml - a UUID ("GPU-...") or an
       nvidia-smi index - when it names a card that is there;
    2. otherwise the card a monitor is plugged into (nvidia-smi's
       `display_active`), because the owner plugs the monitors into the
       fast card (MODEL-TOPOLOGY's install checklist, step 2);
    3. otherwise nvidia-smi index 0.

`primary()` returns the card AND the sentence saying which rule chose it, so
a screen can say why rather than just what.

`simulated` is the honest field. When no GPU can be interrogated this returns
a plan anyway - the HUD prints one at startup and must not crash on a machine
with no card - but it says so, rather than reporting a confident layout for
hardware nobody looked at.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
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
    # Added 2026-09-24 for the primary-card rule and jarvis_second_card.py.
    # Defaults, so a Device built with the original four fields still works.
    uuid: str = ""
    compute_cap: Optional[float] = None     # None: nvidia-smi did not say
    display_active: Optional[bool] = None   # None: nvidia-smi did not say


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
                v = int(v or 0)
            except (TypeError, ValueError):
                continue
            # Negative is not zero. `if pl.total_mb: return pl.total_mb`
            # above only falls through to the honest default on exactly 0 -
            # a negative reading (corrupt or injected device data; real
            # nvidia-smi cannot emit one, but nothing here enforced that)
            # is truthy and was trusted as a genuine measurement, reported
            # with simulated=False as if it were real VRAM.
            if v > 0:
                total += v
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


# --------------------------------------------------------------------------
#   Reading the cards
# --------------------------------------------------------------------------

#: What is asked for. `compute_cap` only exists in newer drivers' nvidia-smi
#: (an older one refuses the WHOLE query, saying the field is not a valid
#: field to query), so a refusal is retried without it, and the generation
#: is then looked up by name (COMPUTE_BY_NAME) or left unknown.
FIELDS_FULL = "index,uuid,name,memory.total,memory.free,compute_cap,display_active"
FIELDS_OLD = "index,uuid,name,memory.total,memory.free,display_active"
FIELDS_OLDEST = "index,name,memory.total,memory.free"

#: Compute capability by marketing name, for a driver too old to report it.
#: Checked in order; the first substring found wins. Only families whose
#: every member shares one capability are listed; anything else is None,
#: which jarvis_second_card treats as "unknown, so not capable".
COMPUTE_BY_NAME = (
    ("RTX 50", 12.0), ("RTX 40", 8.9), ("RTX 30", 8.6), ("A100", 8.0),
    ("RTX 20", 7.5), ("GTX 16", 7.5), ("TITAN RTX", 7.5), ("QUADRO RTX", 7.5),
    ("TESLA T4", 7.5), ("TITAN V", 7.0), ("V100", 7.0),
    ("P100", 6.0), ("P40", 6.1), ("GTX 10", 6.1), ("TITAN X", 6.1),
    ("GTX 9", 5.2),
)

_CACHE_SECONDS = 30.0
_cache: dict = {"at": -1e9, "cards": None, "fields": ""}


def _run_smi(args: list) -> Optional[str]:
    """nvidia-smi's stdout, or None if it is absent or refused. Never raises.
    Replaced in tests with recorded output."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe] + list(args), capture_output=True, text=True,
                             timeout=10)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def _num(text) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None           # "[N/A]", "[Not Supported]", "", garbage


def compute_from_name(name: str) -> Optional[float]:
    up = " ".join(str(name or "").upper().split())
    for key, cc in COMPUTE_BY_NAME:
        if key in up:
            return cc
    return None


def parse_smi(text: str, fields: str = FIELDS_FULL) -> list:
    """Rows of `nvidia-smi --query-gpu=<fields> --format=csv,noheader,nounits`
    as Devices. A line that does not parse is skipped, never guessed at."""
    names = fields.split(",")
    found = []
    for line in str(text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != len(names):
            continue
        row = dict(zip(names, parts))
        try:
            index = int(row["index"])
            total = int(float(row["memory.total"]))
        except (KeyError, TypeError, ValueError):
            continue
        if index < 0 or total <= 0:
            continue
        free = _num(row.get("memory.free", ""))
        name = row.get("name", "") or f"GPU {index}"
        cc = _num(row.get("compute_cap", "")) if "compute_cap" in row else None
        if cc is None:
            cc = compute_from_name(name)
        da = row.get("display_active", "").strip().lower()
        display = True if da == "enabled" else False if da == "disabled" else None
        uuid = row.get("uuid", "")
        if not uuid.startswith("GPU-"):
            uuid = ""
        found.append(Device(index, name, total,
                            int(free) if free is not None and free >= 0 else 0,
                            uuid=uuid, compute_cap=cc, display_active=display))
    return found


def query_cards(fresh: bool = False) -> list:
    """Every NVIDIA card, via nvidia-smi, cached for 30 seconds. Empty when
    there is none or nvidia-smi is missing. Never raises."""
    now = time.monotonic()
    if not fresh and _cache["cards"] is not None and now - _cache["at"] < _CACHE_SECONDS:
        return list(_cache["cards"])
    cards: list = []
    used = ""
    for fields in (FIELDS_FULL, FIELDS_OLD, FIELDS_OLDEST):
        try:
            out = _run_smi([f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
        except Exception:
            out = None
        if out is None:
            continue
        try:
            cards = parse_smi(out, fields)
        except Exception:
            cards = []
        if cards:
            used = fields
            break
    _cache.update(at=now, cards=list(cards), fields=used)
    return list(cards)


def devices() -> list:
    """The GPUs, via nvidia-smi. Empty list if there are none or it is absent.

    Parsed from --query-gpu CSV rather than any library, because the backend
    is standard-library-only and a dependency here would make the startup
    banner the one thing that needs pip.
    """
    return query_cards()


def primary(devs: list, configured=None) -> tuple:
    """(the everyday card, the sentence saying which rule chose it), or
    (None, why) with no cards. The rule is in this module's docstring.
    `configured` is `[compute] primary_gpu`; None reads it from the toml."""
    devs = [d for d in devs or [] if d is not None]
    if not devs:
        return None, "no graphics card was found"
    if configured is None:
        configured = _cfg("primary_gpu", "")
    want = str(configured if configured is not None else "").strip()
    note = ""
    if want:
        for d in devs:
            if getattr(d, "uuid", "") and d.uuid.lower() == want.lower():
                return d, f"[compute] primary_gpu names this card by its id ({want})"
        if want.isdigit():
            for d in devs:
                if d.index == int(want):
                    return d, (f"[compute] primary_gpu names nvidia-smi number {want} "
                               f"(an id starting GPU- is safer: numbers can change)")
        note = (f"[compute] primary_gpu is {want!r}, which is not a card in this PC, "
                f"so it was ignored and ")
    shown = sorted((d for d in devs if getattr(d, "display_active", None) is True),
                   key=lambda d: d.index)
    if shown:
        return shown[0], note + "a monitor is plugged into it"
    first = min(devs, key=lambda d: d.index)
    return first, note + "it is nvidia-smi's first card (no monitor was seen on any card)"


# --------------------------------------------------------------------------
#   Who is starting a process on which card (added 2026-09-24)
#
#   jarvis_second_card.py (the second Ollama) and jarvis_big_model.py
#   (colibri with [big_model] cuda = "on") can both want the second card.
#   Each checks the other before starting, but a check and a start are two
#   steps, so both could pass the check at the same moment. The claim below
#   closes that gap: a module takes the card's claim BEFORE it starts a
#   process on it and gives it back when that process is stopped. Only one
#   owner holds a card at a time. In this process only (both modules live
#   in the one backend); nothing is written anywhere.
# --------------------------------------------------------------------------

_CLAIMS_LOCK = threading.Lock()
_CLAIMS: dict = {}            # card id, lower case -> owner


def claim_card(uuid: str, owner: str) -> Optional[str]:
    """Take the card for `owner`. None when it is now `owner`'s (taken, or
    already held); otherwise the owner that holds it, and nothing changes."""
    key = str(uuid or "").strip().lower()
    if not key:
        return None
    with _CLAIMS_LOCK:
        holder = _CLAIMS.get(key)
        if holder is not None and holder != owner:
            return holder
        _CLAIMS[key] = owner
    return None


def release_card(uuid: str, owner: str) -> None:
    """Give the card back, only if `owner` holds it."""
    key = str(uuid or "").strip().lower()
    with _CLAIMS_LOCK:
        if _CLAIMS.get(key) == owner:
            del _CLAIMS[key]


def card_holder(uuid: str) -> Optional[str]:
    """Who holds the card's claim, or None. Reads only."""
    with _CLAIMS_LOCK:
        return _CLAIMS.get(str(uuid or "").strip().lower())


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

    # The everyday card by the primary rule (module docstring), never "the
    # one with the most free memory": that picked a 12 GB RTX 2060 over the
    # faster 8 GB 2080 Super. The others follow in nvidia-smi order.
    first, rule = primary(devs)
    ranked = [first] + sorted((d for d in devs if d is not first), key=lambda d: d.index)
    second = ranked[1] if len(ranked) > 1 else None

    if prefer == "speed":
        text_on = f"cuda:{first.index}"
        # Voice runs on the processor (docs/ARCHITECTURE.md section 11: 0 GB
        # of graphics memory), so it is never resident on a card. Pictures
        # are on the second card only while its "Pictures" switch is on and
        # working (jarvis_second_card.py) - not merely because a second card
        # exists, which is what this used to claim, for voice as well.
        tts = False
        vision = False
        if second is not None:
            try:
                import jarvis_second_card
                vision = jarvis_second_card.lane_for("vision") is not None
            except Exception:
                vision = False
        why = (f"speed: everyday chat on the {first.name} (because {rule}); "
               + ("the second card runs only the second-card features that are "
                  "switched on (GET /api/second-card)"
                  if second else "one card only"))
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
