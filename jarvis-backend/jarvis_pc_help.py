"""jarvis_pc_help.py - "PC help": plain answers about this PC, read-only.

NEW MODULE, shipped whole, no patch of its own. The owner chose it on
2026-09-28 (docs/RESEARCH-AUDIT-2026-09-28.md section 3, idea 12, after a
phone maker's "Device help"). docs/JARVIS-API.md section 84 is the contract.

    "why is my PC slow?"              how busy the processor is, how full the
                                      memory is, and the top three programs
                                      using each - with Jarvis's own AI model
                                      named as such when it is one of them
    "how full is my disk?"            every fixed drive: free GB and %
    "what's using my graphics card?"  each NVIDIA card's memory in use, the AI
                                      models Ollama has loaded on it, and the
                                      other programs using its memory
    "how hot is my graphics card?"    each NVIDIA card's temperature
    "when did my PC last restart?"    when Windows last started

WHO ASKS. jarvis_quick.py answers the five questions WITHOUT the AI model
(answer() below): a PC that is slow is the worst time to wait for a model,
and the model itself is often what is using the card, so asking it to
explain would make the answer slower and change the thing being measured.
There is NO model tool for this. GET /api/pc/help (read()) gives both apps
the same five answers for their "PC help" section; jarvis_brain_reads.py
routes it, behind the pairing token and the origin check like every other
Brain read, so no new patch is needed.

READ-ONLY. Nothing here changes a Windows setting, ends a program, frees
memory or deletes a file. Night light, dark mode and Do not disturb were
asked about: nothing in this codebase changes a Windows setting safely today
(jarvis_ui_control.py clicks inside other apps' windows, which is a different
thing), so those are written down as a later step (CHANGES_LATER) rather
than built here. Nothing is gated because nothing acts; Lockdown has nothing
to stop, since nothing leaves this PC.

PRIVATE. Program names say what the owner is doing, so:
  * never logged, printed, audited or written to any file here;
  * the program reading is held in memory for at most CACHE_SECONDS (so a
    question asked in both apps at once runs PowerShell once), then dropped;
  * an answer that names programs is marked private (it stays on screen
    under the apps' private rule rather than being read aloud) and as having
    read outside text (READ_MARK): a program chooses its own name, so it is
    not the owner's words and is never learned from - the same treatment
    jarvis_media.py gives a song title.
  * nothing is sent anywhere: every reading is a Windows call on this PC,
    or Ollama and nvidia-smi on this PC.

HOW IT READS WINDOWS (standard means only; no new dependency - psutil is
not in requirements.lock, so it is not used):
  * programs: ONE PowerShell call (Windows PowerShell 5.1, which every
    Windows 10/11 PC has) reading Windows' own performance counters through
    CIM - Win32_PerfFormattedData_PerfProc_Process (processor and private
    memory per program), ..._GPUPerformanceCounters_GPUProcessMemory
    (graphics-card memory per program) and ..._PerfOS_Processor (the whole
    processor). Sent as -EncodedCommand, so no quoting can go wrong.
  * memory, drives and the last start: ctypes calls into kernel32
    (GlobalMemoryStatusEx, GetLogicalDrives/GetDriveTypeW with
    shutil.disk_usage, GetTickCount64).
  * graphics cards: jarvis_compute.query_cards (nvidia-smi) and
    jarvis_hardware's health reading (temperature), the same readings the
    Hardware and models screen shows; Ollama's own /api/ps on loopback for
    which models are loaded and how much card memory each uses.

TESTED WITHOUT WINDOWS: every reading is one field of Readers; the tests
pass fakes. A reading that fails is None, and its answer says plainly that
it could not be read. Never raises from the public calls.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

PATH = "/api/pc/help"

#: What an answer that names programs marks the turn with - outside text
#: (a program picks its own name), exactly as jarvis_media.READ_MARK.
READ_MARK = "pc_help_programs"

TOPICS = ("slow", "disk", "gpu", "heat", "restart")

#: Each topic's heading in both apps - the question in the owner's words.
TITLES = {
    "slow": "Why is my PC slow?",
    "disk": "How full are my drives?",
    "gpu": "What is using my graphics card?",
    "heat": "How hot is my graphics card?",
    "restart": "When did my PC last restart?",
}

#: Said under the five answers in both apps.
CHANGES_LATER = ("PC help only reads. Changing Windows settings from Jarvis (Night light, dark "
                 "mode, Do not disturb) is not built yet.")
PRIVATE_NOTE = ("Program names stay on your PC: Jarvis does not save, log or learn from them.")

COULD_NOT = "Jarvis could not read this on your PC just now."
NO_NVIDIA = ("Jarvis can only read an NVIDIA graphics card (through its nvidia-smi tool), and "
             "none answered.")
NO_TEMP = ("Jarvis could not read the graphics card's temperature - it needs an NVIDIA card "
           "and its nvidia-smi tool.")
FAST_STARTUP = ("With Windows' Fast Startup on, \"Shut down\" does not count as a restart - only "
                "\"Restart\" does.")

#: Jarvis's own AI model, when it is a program in the list.
MODEL_WORDS = "Jarvis's AI model"
#: This backend itself.
SELF_WORDS = "Jarvis itself"

TOP_N = 3
CACHE_SECONDS = 5.0
PS_TIMEOUT = 12   # under the phone's 20-second limit for a read
GIB = 1024 ** 3

#: Counter rows that are not programs.
_NOT_PROGRAMS = frozenset({"_total", "idle", "system idle process"})


# --------------------------------------------------------------------------
#   The readings, replaceable for the tests
# --------------------------------------------------------------------------

@dataclass
class Readers:
    """Each returns None when it could not read.

    programs() -> {"cores": int, "cpu_percent": float | None,
                   "procs": [{"name", "pid", "cpu", "mem_bytes"}],
                   "gpu": [{"pid", "bytes"}]}
        `cpu` is Windows' per-program figure, where 100 is one whole core.
    memory()   -> {"total_bytes", "available_bytes"}
    disks()    -> [{"drive": "C:", "total_bytes", "free_bytes"}]
    uptime()   -> seconds since Windows started
    cards()    -> [{"name", "used_mib", "total_mib", "temp_c", "hot_slowdown",
                   "load_percent"}]
    models()   -> [{"name", "vram_bytes"}]   Ollama's loaded models
    """
    programs: Callable[[], Optional[dict]]
    memory: Callable[[], Optional[dict]]
    disks: Callable[[], Optional[list]]
    uptime: Callable[[], Optional[float]]
    cards: Callable[[], Optional[list]]
    models: Callable[[], Optional[list]]
    now: Callable[[], float] = field(default=time.time)
    own_pid: int = field(default_factory=os.getpid)


# ---- programs: one PowerShell call ----------------------------------------

#: Two samples a second apart: the first query of a "formatted" counter can
#: read 0 for a rate. No double quotes anywhere, and sent encoded.
PS_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$null=Get-CimInstance Win32_PerfFormattedData_PerfProc_Process;"
    "$null=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor;"
    "Start-Sleep -Milliseconds 1000;"
    "$p=@(Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | ForEach-Object {"
    "[pscustomobject]@{n=[string]$_.Name;i=[int]$_.IDProcess;c=[double]$_.PercentProcessorTime;"
    "m=[double]$_.WorkingSetPrivate}});"
    "$g=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory |"
    " ForEach-Object {[pscustomobject]@{n=[string]$_.Name;b=[double]$_.DedicatedUsage}});"
    "$t=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter 'Name=''_Total''';"
    "[pscustomobject]@{procs=$p;gpu=$g;cpu=$(if($t){[double]$t.PercentProcessorTime}else{$null});"
    "cores=[Environment]::ProcessorCount} | ConvertTo-Json -Depth 3 -Compress"
)

_PID_IN_GPU_NAME = re.compile(r"^pid_(\d+)_", re.I)


def parse_programs(text: str) -> Optional[dict]:
    """PS_SCRIPT's JSON as programs()'s shape. None when it is not that."""
    try:
        raw = json.loads(str(text or "").strip() or "null")
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None

    def rows(v):
        if isinstance(v, dict):
            return [v]           # ConvertTo-Json writes a one-item array as an object
        return [r for r in v if isinstance(r, dict)] if isinstance(v, list) else []

    procs = []
    for r in rows(raw.get("procs")):
        try:
            procs.append({"name": str(r.get("n") or ""), "pid": int(r.get("i") or 0),
                          "cpu": float(r.get("c") or 0), "mem_bytes": float(r.get("m") or 0)})
        except (TypeError, ValueError):
            continue
    gpu = []
    for r in rows(raw.get("gpu")):
        m = _PID_IN_GPU_NAME.match(str(r.get("n") or ""))
        try:
            b = float(r.get("b") or 0)
        except (TypeError, ValueError):
            continue
        if m:
            gpu.append({"pid": int(m.group(1)), "bytes": b})
    try:
        cores = max(1, int(raw.get("cores") or 1))
    except (TypeError, ValueError):
        cores = 1
    cpu = raw.get("cpu")
    try:
        cpu = None if cpu is None else float(cpu)
    except (TypeError, ValueError):
        cpu = None
    return {"cores": cores, "cpu_percent": cpu, "procs": procs, "gpu": gpu}


def _powershell() -> Optional[str]:
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    exe = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return exe if os.path.isfile(exe) else shutil.which("powershell")


def _read_programs() -> Optional[dict]:
    if os.name != "nt":
        return None
    exe = _powershell()
    if not exe:
        return None
    encoded = base64.b64encode(PS_SCRIPT.encode("utf-16-le")).decode("ascii")
    try:
        out = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                             capture_output=True, text=True, timeout=PS_TIMEOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return None
    # stderr is never read or kept: it could quote a program's name.
    return parse_programs(out.stdout) if out.returncode == 0 else None


# ---- memory, drives, the last start: kernel32 -----------------------------

def _read_memory() -> Optional[dict]:
    if os.name != "nt":
        return None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return None
        return {"total_bytes": int(st.ullTotalPhys), "available_bytes": int(st.ullAvailPhys)}
    except Exception:
        return None


def _read_disks() -> Optional[list]:
    if os.name != "nt":
        return None
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        mask = int(k32.GetLogicalDrives())
        out = []
        for i in range(26):
            if not mask & (1 << i):
                continue
            root = f"{chr(65 + i)}:\\"
            if int(k32.GetDriveTypeW(ctypes.c_wchar_p(root))) != 3:   # DRIVE_FIXED
                continue
            try:
                u = shutil.disk_usage(root)
            except OSError:
                continue
            out.append({"drive": root[:2], "total_bytes": int(u.total),
                        "free_bytes": int(u.free)})
        return out
    except Exception:
        return None


def _read_uptime() -> Optional[float]:
    if os.name != "nt":
        return None
    try:
        import ctypes
        f = ctypes.windll.kernel32.GetTickCount64
        f.restype = ctypes.c_ulonglong
        return float(f()) / 1000.0
    except Exception:
        return None


# ---- graphics cards and Ollama: what the Hardware screen already reads -----

def _read_cards() -> Optional[list]:
    try:
        import jarvis_hardware as HW
    except Exception:
        return None
    try:
        cards = HW._smi_cards()
        health = HW._read_health()
    except Exception:
        return None
    if not cards:
        return []
    out = []
    for c in cards:
        h = HW.health_for({"uuid": getattr(c, "uuid", ""), "index": getattr(c, "index", None)},
                          health) or {}
        total = getattr(c, "total_mb", None)
        free = getattr(c, "free_mb", None)
        used = (total - free) if isinstance(total, (int, float)) and isinstance(
            free, (int, float)) and total > 0 else None
        out.append({"name": str(getattr(c, "name", "") or "Graphics card"),
                    "used_mib": used, "total_mib": total, "temp_c": h.get("temp_c"),
                    "hot_slowdown": h.get("hot_slowdown"), "load_percent": h.get("load_percent")})
    return out


def _read_models() -> Optional[list]:
    try:
        import jarvis_hardware as HW
    except Exception:
        return None
    urls = [HW._main_url()]
    try:
        second = HW._second_url()
    except Exception:
        second = None
    if second:
        urls.append(second)
    out, any_ok = [], False
    for url in urls:
        rows = HW._ps(url)
        if rows is None:
            continue
        any_ok = True
        for m in rows:
            try:
                out.append({"name": str(m.get("name") or m.get("model") or ""),
                            "vram_bytes": float(m.get("size_vram") or 0)})
            except (TypeError, ValueError):
                continue
    return out if any_ok else None


def real_readers() -> Readers:
    return Readers(programs=_cached_programs, memory=_read_memory, disks=_read_disks,
                   uptime=_read_uptime, cards=_read_cards, models=_read_models)


_CACHE: dict = {"at": -1e9, "value": None}
_LOCK = threading.Lock()


def _cached_programs() -> Optional[dict]:
    """The program reading, held in memory only, for CACHE_SECONDS."""
    with _LOCK:
        now = time.monotonic()
        if _CACHE["value"] is not None and now - _CACHE["at"] < CACHE_SECONDS:
            return _CACHE["value"]
        value = _read_programs()
        _CACHE.update(at=now, value=value)
        return value


def _forget_cache() -> None:
    with _LOCK:
        _CACHE.update(at=-1e9, value=None)


# --------------------------------------------------------------------------
#   Words
# --------------------------------------------------------------------------

def _clean_name(name: str) -> str:
    """A program's name as shown: "chrome#3" -> "chrome", ".exe" dropped,
    control characters out, at most 40 characters."""
    n = re.sub(r"#\d+$", "", str(name or "").strip())
    n = re.sub(r"\.exe$", "", n, flags=re.I)
    n = "".join(ch for ch in n if ch.isprintable())
    return n[:40].strip()


def _is_model(name: str) -> bool:
    low = name.lower()
    return low.startswith("ollama") or low.startswith("llama-server") or \
        low.startswith("llama_server")


def _gb(n: float) -> str:
    v = n / GIB
    return f"{v:.1f} GB" if v < 100 else f"{v:,.0f} GB"


def _pct(n: float) -> str:
    return f"{int(round(n))}%"


def _join(items: list) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _programs(reading: dict, own_pid: int) -> list:
    """One row per program name: {"name", "cpu" (% of the whole processor),
    "mem_bytes", "gpu_bytes", "model", "self"}, merged across its processes."""
    cores = max(1, int(reading.get("cores") or 1))
    gpu_by_pid: dict = {}
    for g in reading.get("gpu") or []:
        gpu_by_pid[g["pid"]] = gpu_by_pid.get(g["pid"], 0.0) + max(0.0, float(g["bytes"]))
    merged: dict = {}
    for p in reading.get("procs") or []:
        raw = _clean_name(p.get("name", ""))
        if not raw or raw.lower() in _NOT_PROGRAMS:
            continue
        me = p.get("pid") == own_pid and own_pid > 0
        model = _is_model(raw)
        key = SELF_WORDS if me else MODEL_WORDS if model else raw.lower()
        row = merged.setdefault(key, {"name": SELF_WORDS if me else MODEL_WORDS if model else raw,
                                      "cpu": 0.0, "mem_bytes": 0.0, "gpu_bytes": 0.0,
                                      "model": model, "self": me})
        row["cpu"] += max(0.0, float(p.get("cpu") or 0)) / cores
        row["mem_bytes"] += max(0.0, float(p.get("mem_bytes") or 0))
        row["gpu_bytes"] += gpu_by_pid.get(p.get("pid"), 0.0)
    for row in merged.values():
        row["cpu"] = min(100.0, row["cpu"])
    return list(merged.values())


def slow_words(r: Readers) -> tuple:
    """(words, names_programs)."""
    reading = r.programs()
    mem = r.memory()
    bits, verdict = [], ""
    cpu = reading.get("cpu_percent") if reading else None
    mem_pct = None
    if mem and mem.get("total_bytes"):
        used = mem["total_bytes"] - mem.get("available_bytes", 0)
        mem_pct = 100.0 * used / mem["total_bytes"]
    if cpu is not None and mem_pct is not None:
        bits.append(f"Your processor is {_pct(cpu)} busy and your memory (RAM) is "
                    f"{_pct(mem_pct)} full ({_gb(used)} of {_gb(mem['total_bytes'])}).")
    elif cpu is not None:
        bits.append(f"Your processor is {_pct(cpu)} busy.")
    elif mem_pct is not None:
        bits.append(f"Your memory (RAM) is {_pct(mem_pct)} full ({_gb(used)} of "
                    f"{_gb(mem['total_bytes'])}).")
    rows = _programs(reading, r.own_pid) if reading else []
    by_cpu = [p for p in sorted(rows, key=lambda p: -p["cpu"]) if p["cpu"] >= 1][:TOP_N]
    by_mem = [p for p in sorted(rows, key=lambda p: -p["mem_bytes"])
              if p["mem_bytes"] >= 50 * 1024 ** 2][:TOP_N]
    if by_cpu:
        bits.append("Using the processor most: "
                    + _join([f"{p['name']} ({_pct(p['cpu'])})" for p in by_cpu]) + ".")
    if by_mem:
        bits.append("Using memory (RAM) most: "
                    + _join([f"{p['name']} ({_gb(p['mem_bytes'])})" for p in by_mem]) + ".")
    if not bits:
        return COULD_NOT, False
    model_top = any(p["model"] for p in by_cpu[:1] + by_mem[:1])
    if cpu is not None and cpu >= 85:
        verdict = "The processor is nearly flat out - that is the likely reason."
    elif mem_pct is not None and mem_pct >= 90:
        verdict = ("Memory is nearly full - that is the likely reason. Closing a program you "
                   "are not using frees some.")
    elif cpu is not None and mem_pct is not None and cpu < 50 and mem_pct < 75:
        verdict = ("Nothing looks very busy right now. If it still feels slow, it may be the "
                   "disk or the internet, which PC help does not measure.")
    if model_top:
        verdict = (verdict + " " if verdict else "") + (
            "Jarvis's own AI model is one of them - it works hardest while it is answering.")
    if verdict:
        bits.append(verdict)
    return " ".join(bits), bool(by_cpu or by_mem)


def disk_words(r: Readers) -> str:
    disks = r.disks()
    if disks is None:
        return COULD_NOT
    if not disks:
        return "Jarvis found no fixed drives on your PC."
    parts, full = [], []
    for d in disks:
        total, free = d.get("total_bytes") or 0, d.get("free_bytes") or 0
        if total <= 0:
            continue
        pct = 100.0 * free / total
        parts.append(f"{d['drive']} has {_gb(free)} free of {_gb(total)} ({_pct(pct)} free).")
        if pct < 10:
            full.append(d["drive"])
    if not parts:
        return COULD_NOT
    if full:
        parts.append(f"{_join(full)} {'is' if len(full) == 1 else 'are'} nearly full - "
                     "Windows' Storage settings can show what is taking the space.")
    return " ".join(parts)


def gpu_words(r: Readers) -> tuple:
    """(words, names_programs)."""
    cards = r.cards()
    models = r.models()
    reading = r.programs()
    bits = []
    if cards:
        for c in cards:
            line = c["name"]
            if c.get("used_mib") is not None and c.get("total_mib"):
                line += (f": {_gb(c['used_mib'] * 1024 ** 2)} of "
                         f"{_gb(c['total_mib'] * 1024 ** 2)} of its memory in use")
            if c.get("load_percent") is not None:
                line += f", {c['load_percent']}% busy"
            bits.append(line + ".")
    loaded = [m for m in (models or []) if m.get("name")]
    on_card = [m for m in loaded if (m.get("vram_bytes") or 0) > 0]
    if on_card:
        bits.append("Jarvis's AI " + ("model " if len(on_card) == 1 else "models ")
                    + _join([f"{m['name']} ({_gb(m['vram_bytes'])})" for m in on_card])
                    + (" is" if len(on_card) == 1 else " are") + " loaded on it.")
    elif models is not None:
        bits.append("Jarvis's AI model is not loaded on the card right now.")
    others = []
    if reading:
        rows = [p for p in _programs(reading, r.own_pid)
                if not p["model"] and p["gpu_bytes"] >= 50 * 1024 ** 2]
        others = sorted(rows, key=lambda p: -p["gpu_bytes"])[:TOP_N]
    if others:
        bits.append("Other programs using its memory: "
                    + _join([f"{p['name']} ({_gb(p['gpu_bytes'])})" for p in others]) + ".")
    if not bits:
        return (NO_NVIDIA if cards == [] else COULD_NOT), False
    return " ".join(bits), bool(others)


def heat_words(r: Readers) -> str:
    cards = r.cards()
    if cards is None:
        return COULD_NOT
    temps = [c for c in cards if c.get("temp_c") is not None]
    if not temps:
        return NO_TEMP
    parts = []
    for c in temps:
        t = c["temp_c"]
        if c.get("hot_slowdown") is True:
            say = "hot - it is slowing itself down to cool off"
        elif t >= 85:
            say = "hot, near where cards like it start slowing down"
        elif t >= 75:
            say = "warm, which is normal while it is working hard"
        else:
            say = "fine"
        parts.append(f"{c['name']} is at {t} °C: {say}.")
    return " ".join(parts)


def _when(ts: float, now: float) -> str:
    then, today = time.localtime(ts), time.localtime(now)
    clock = time.strftime("%H:%M", then)
    days = (time.mktime((today.tm_year, today.tm_mon, today.tm_mday, 0, 0, 0, 0, 0, -1))
            - time.mktime((then.tm_year, then.tm_mon, then.tm_mday, 0, 0, 0, 0, 0, -1)))
    days = int(round(days / 86400))
    if days <= 0:
        return f"today at {clock}"
    if days == 1:
        return f"yesterday at {clock}"
    if days < 7:
        return f"on {time.strftime('%A', then)} at {clock}"
    return f"on {time.strftime('%A', then)} {then.tm_mday} {time.strftime('%B', then)} at {clock}"


def _ago(seconds: float) -> str:
    m = int(seconds // 60)
    if m < 60:
        return "under an hour ago" if m < 2 else f"{m} minutes ago"
    h = m // 60
    if h < 48:
        return "1 hour ago" if h == 1 else f"{h} hours ago"
    return f"{h // 24} days ago"


def restart_words(r: Readers) -> str:
    up = r.uptime()
    if up is None or up < 0:
        return COULD_NOT
    now = r.now()
    said = f"Your PC last started {_when(now - up, now)} ({_ago(up)})."
    if up >= 2 * 86400:
        said += " " + FAST_STARTUP
    return said


# --------------------------------------------------------------------------
#   The two ways in
# --------------------------------------------------------------------------

def answer(topic: str, readers: Optional[Readers] = None) -> dict:
    """One topic's answer for jarvis_quick.py: {"said", "private", "read"}.
    Never raises."""
    r = readers or real_readers()
    names = False
    try:
        if topic == "slow":
            said, names = slow_words(r)
        elif topic == "disk":
            said = disk_words(r)
        elif topic == "gpu":
            said, names = gpu_words(r)
        elif topic == "heat":
            said = heat_words(r)
        elif topic == "restart":
            said = restart_words(r)
        else:
            said = COULD_NOT
    except Exception:
        said, names = COULD_NOT, False
    return {"said": said, "private": names, "read": [READ_MARK] if names else []}


def read(readers: Optional[Readers] = None) -> dict:
    """GET /api/pc/help: the five answers, in the order of TOPICS."""
    r = readers or real_readers()
    sections = []
    for topic in TOPICS:
        a = answer(topic, r)
        sections.append({"id": topic, "title": TITLES[topic], "words": a["said"],
                         "programs": bool(a["private"])})
    try:
        at = int(r.now())
    except Exception:
        at = int(time.time())
    return {"ok": True, "at": at, "sections": sections, "changes": CHANGES_LATER,
            "private": PRIVATE_NOTE}


def handle_get(query: str = "", readers: Optional[Readers] = None) -> tuple:
    """(status, body) for GET /api/pc/help. Takes no parameters."""
    try:
        return 200, read(readers)
    except Exception as exc:
        return 500, {"error": type(exc).__name__}
