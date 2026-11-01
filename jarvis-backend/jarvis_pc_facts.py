"""jarvis_pc_facts.py - read-only facts about THIS PC, in plain words.

WHY THIS EXISTS (owner-reported, 2026-10-31): the owner asked "how much storage
does my computer have available?" and the chat model answered "I don't have
direct access to your system's storage stats right now". The facts were already
read on this PC by `jarvis_pc_help.py` (kernel32 memory, GetLogicalDrives +
shutil.disk_usage, GetTickCount64, nvidia-smi through jarvis_hardware) and by
`jarvis_big_model.py` (`_memory`, `_disk_free`), but no small layer put them
together for a deterministic answer and the model had no current-state line.

WHAT THIS IS. ONE read-only collector, `collect()`, and `answer(shape)` for the
chat fast path. It calls the EXISTING readers in `jarvis_pc_help.real_readers()`
- no second nvidia-smi, no PowerShell, no psutil (not vendored), no new
dependency - and adds the current chat model and focus preset. Nothing is
written, logged, gated or sent; a fact that cannot be read is None and the
answer says "not readable" rather than guessing.

WHAT IS AVAILABLE TODAY (measured from the tree):
  * each fixed drive's own total/free bytes: jarvis_pc_help._read_disks;
  * RAM total/available: jarvis_pc_help._read_memory (GlobalMemoryStatusEx);
  * CPU logical cores: os.cpu_count(); the CPU's NAME is NOT read anywhere in
    this backend, so it is reported "not recorded", never invented;
  * GPU name and VRAM: jarvis_pc_help._read_cards (nvidia-smi + registry),
    with temperature/load when the same reader has them;
  * uptime: jarvis_pc_help._read_uptime (GetTickCount64);
  * the current chat model: jarvis_power_switch.chat_model; the chosen preset:
    jarvis_presets.choice()/view();
  * the storage safety margin: jarvis_storage.MIN_FREE_AFTER_DOWNLOAD (25 GB)
    and MIN_FREE_TO_START (3 GB), the numbers the model chooser already uses.

WHAT IS NOT AVAILABLE: a CPU model name, a non-NVIDIA GPU, temperatures/loads
for a card nvidia-smi cannot see, and any fact from a source this PC does not
have. Those say so plainly.
"""
from __future__ import annotations

import os
import shutil
from typing import Optional

GIB = 1024 ** 3
#: The drive the model chooser watches. C: on Windows; the first fixed drive
#: on a machine without one.
WATCH_DRIVE = "C:"


def _gb(n) -> str:
    try:
        v = float(n) / GIB
    except (TypeError, ValueError):
        return "not readable"
    return f"{v:.1f} GB" if v < 100 else f"{v:,.0f} GB"


def _pct(n: float) -> str:
    return f"{int(round(float(n)))}%"


def _call(fn):
    try:
        return fn() if callable(fn) else None
    except Exception:                                       # noqa: BLE001
        return None


def _drive(disks, wanted: str = "") -> Optional[dict]:
    if not isinstance(disks, list):
        return None
    want = str(wanted or "").strip().rstrip("\\").upper().rstrip(":")
    for d in disks:
        if not isinstance(d, dict):
            continue
        name = str(d.get("drive") or "").rstrip("\\").upper().rstrip(":")
        if want and name == want:
            return d
    if want:
        return None
    for d in disks:
        if isinstance(d, dict) and str(d.get("drive") or "").rstrip("\\").upper().rstrip(":") == WATCH_DRIVE:
            return d
    return disks[0] if disks else None


def _margin() -> tuple:
    try:
        import jarvis_storage as S
        return int(S.MIN_FREE_AFTER_DOWNLOAD), int(S.MIN_FREE_TO_START)
    except Exception:                                       # noqa: BLE001
        return 25 * GIB, 3 * GIB


def _model_and_preset() -> tuple:
    model, preset = "", ""
    try:
        import jarvis_power_switch
        model = str(jarvis_power_switch.chat_model() or "")
    except Exception:                                       # noqa: BLE001
        pass
    try:
        import jarvis_presets
        chosen = str(jarvis_presets.choice() or "")
        view = jarvis_presets.view() or {}
        preset = str(view.get("chosen_preset") or chosen)
        if not model:
            model = str(view.get("chosen_model") or "")
    except Exception:                                       # noqa: BLE001
        pass
    return model, preset


def collect(readers=None) -> dict:
    """Every PC fact this backend really reads, or None for an unread fact."""
    try:
        import jarvis_pc_help as PCH
    except Exception:                                       # noqa: BLE001
        return {"ok": False, "why": "the PC-help reader is not on this backend"}
    r = readers or PCH.real_readers()
    disks = _call(getattr(r, "disks", None))
    memory = _call(getattr(r, "memory", None))
    cards = _call(getattr(r, "cards", None))
    uptime = _call(getattr(r, "uptime", None))
    cores = None
    try:
        cores = int(os.cpu_count() or 0) or None
    except Exception:                                       # noqa: BLE001
        cores = None
    model, preset = _model_and_preset()
    watch = _drive(disks, WATCH_DRIVE)
    free = int(watch.get("free_bytes") or 0) if watch else None
    margin, start_margin = _margin()
    state = ""
    if free is not None:
        if free < start_margin:
            state = "full"
        elif free < margin:
            state = "low"
        else:
            state = "ok"
    return {
        "ok": True,
        "disks": disks if isinstance(disks, list) else None,
        "memory": memory if isinstance(memory, dict) else None,
        "cards": cards if isinstance(cards, list) else None,
        "uptime": float(uptime) if isinstance(uptime, (int, float)) and not isinstance(uptime, bool) else None,
        "cpu": {"cores": cores, "name": ""},        # name is not read anywhere
        "model": model, "preset": preset,
        "watch_drive": (watch or {}).get("drive") if watch else "",
        "watch_free": free,
        "watch_total": int(watch.get("total_bytes") or 0) if watch else None,
        "margin_bytes": margin, "start_margin_bytes": start_margin,
        "storage_state": state,
    }


def _missing(what: str) -> str:
    return f"I could not read {what} on this PC just now."


def _drive_line(d: dict) -> str:
    total = int(d.get("total_bytes") or 0)
    free = int(d.get("free_bytes") or 0)
    if total <= 0:
        return ""
    return f"{str(d.get('drive') or '?').rstrip(chr(92))} has {_gb(free)} free of {_gb(total)} ({_pct(100.0 * free / total)} free)."


def _duration(seconds: float) -> str:
    s = max(0, int(seconds))
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''}"
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''}"
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def answer(shape: str, *, drive: str = "", facts: Optional[dict] = None) -> str:
    """One deterministic answer for the chat fast path. Never raises."""
    f = facts if isinstance(facts, dict) and facts.get("ok") else collect()
    if not f.get("ok"):
        return _missing("the PC's facts")
    disks = f.get("disks")
    if shape in ("storage", "space_all"):
        if disks is None:
            return _missing("your drives")
        if not disks:
            return "Jarvis found no fixed drive it could read on this PC."
        parts = [_drive_line(d) for d in disks if isinstance(d, dict)]
        parts = [p for p in parts if p]
        if not parts:
            return _missing("your drives")
        return " ".join(parts)
    if shape in ("drive", "storage_drive"):
        if disks is None:
            return _missing("your drives")
        d = _drive(disks, drive or WATCH_DRIVE)
        if d is None:
            want = str(drive or WATCH_DRIVE).rstrip("\\").rstrip(":")
            return f"I could not find a fixed drive called {want}: on this PC, so I cannot say how much space it has."
        line = _drive_line(d)
        return line or _missing(f"{drive or WATCH_DRIVE}")
    if shape == "ram":
        mem = f.get("memory")
        if not isinstance(mem, dict):
            return _missing("your memory (RAM)")
        total = int(mem.get("total_bytes") or 0)
        free = int(mem.get("available_bytes") or 0)
        if total <= 0:
            return _missing("your memory (RAM)")
        return (f"This PC has {_gb(total)} of RAM, with {_gb(free)} free "
                f"({_pct(100.0 * free / total)} free).")
    if shape == "cpu":
        cores = (f.get("cpu") or {}).get("cores")
        if not cores:
            return _missing("the processor")
        return (f"The processor reports {cores} logical cores. Its exact model name is not "
                f"recorded by any reader on this PC, so I will not guess it.")
    if shape == "gpu":
        cards = f.get("cards")
        if cards is None:
            return _missing("the graphics cards")
        if not cards:
            return ("No NVIDIA graphics card answered this PC's nvidia-smi tool, so I have no "
                    "graphics-card name or memory to report.")
        parts = []
        for c in cards:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "a graphics card")
            total = c.get("total_mib")
            free = c.get("free_mib")
            if isinstance(total, (int, float)) and total > 0:
                line = f"{name} has {_gb(float(total) * 1024 * 1024)} of graphics memory"
                if isinstance(free, (int, float)):
                    line += f", with {_gb(float(free) * 1024 * 1024)} free"
                parts.append(line + ".")
            else:
                parts.append(f"{name} answered, but its memory size was not readable.")
        return " ".join(parts) if parts else _missing("the graphics cards")
    if shape in ("uptime", "on"):
        up = f.get("uptime")
        if up is None:
            return _missing("how long this PC has been on")
        return f"This PC has been on for {_duration(up)}."
    if shape in ("full", "disk_full"):
        state = str(f.get("storage_state") or "")
        free = f.get("watch_free")
        total = f.get("watch_total")
        drive_name = str(f.get("watch_drive") or WATCH_DRIVE).rstrip("\\")
        if free is None or total is None:
            return _missing(f"{drive_name}'s free space")
        margin = int(f.get("margin_bytes") or 0)
        start = int(f.get("start_margin_bytes") or 0)
        line = f"{drive_name} has {_gb(free)} free of {_gb(total)}."
        if state == "full":
            return (line + f" That is under the {_gb(start)} emergency floor this PC uses "
                    f"before it may start anything; the model chooser will not download "
                    f"or start a model until space is freed.")
        if state == "low":
            return (line + f" That is under the {_gb(margin)} safety margin the model "
                    f"chooser uses: it will not start a download that would leave less "
                    f"than that, so a bigger model may be refused until space is freed.")
        return (line + f" That is above the {_gb(margin)} safety margin the model chooser "
                f"uses, so it may start a download that fits while keeping that margin.")
    return "I can read the PC's disk, memory, processor, graphics card and uptime facts if you ask about them."


def prompt_line(facts: Optional[dict] = None) -> str:
    """ONE redacted line for the model: current model/preset + the capability."""
    f = facts if isinstance(facts, dict) and facts.get("ok") else collect()
    model = str(f.get("model") or "") or "not recorded"
    preset = str(f.get("preset") or "") or "not recorded"
    return (f"The model now is {model} and the chosen focus preset is {preset}. "
            f"You can read this PC's disk, RAM, CPU and GPU facts and its uptime on "
            f"request - use the fixed PC facts answer, and never invent a number; a fact "
            f"that is not readable is told as not readable.")


#: The shapes the quick path may ask for.
SHAPES = ("storage", "drive", "ram", "cpu", "gpu", "uptime", "full")
