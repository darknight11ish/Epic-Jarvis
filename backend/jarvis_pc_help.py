"""jarvis_pc_help.py - "PC help": plain answers about this PC, read-only.

NEW MODULE, shipped whole, no patch of its own. The owner chose it on
2026-09-28 (docs/RESEARCH-AUDIT-2026-09-28.md section 3, idea 12, after a
phone maker's "Device help"). docs/JARVIS-API.md section 84 is the contract.

    "why is my PC slow?"              how busy the processor is, how full the
                                      memory is, and the top three programs
                                      using each - with Jarvis's own AI model
                                      named as such when it is one of them; and,
                                      when the processor and memory look calm,
                                      the graphics card that is hot or nearly
                                      full and what to do about it
    "how full is my disk?"            every fixed drive: free GB and %
    "what's using my graphics card?"  every NVIDIA card, by a name a person
                                      can tell apart: its memory in use, how
                                      busy it is, whether it is resting, hot,
                                      at its power limit or nearly full, the
                                      programs nvidia-smi names on it (no
                                      amounts - this PC's driver reports none),
                                      and the AI models Ollama has loaded
    "how hot is my graphics card?"    every NVIDIA card's temperature, what it
                                      means, and what to do when it is hot
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

THE SILENT-FAILURE DOCTOR (Pillar 28, 2026-10-17). Alongside the five
answers, `diagnose_silent_failures()` runs four checks for things that fail
quietly, and read() appends ONE warning section per finding: a microphone
whose last three voice attempts were 100% digital zeros (peak RMS exactly 0.0
- the state some PCs leave it in after sleep), a SQLite write-ahead log past
64 MiB in Jarvis's home folder (the database is named; a passive checkpoint
is offered with its exact safe statement and never run), a paired phone that
has stopped checking in, and the model service not running vs running with its
TCP port open but `/api/ps` timed out. It only reads: it stats files, reads the
pairing registry, asks Ollama one loopback question, and reads the peak RMS
jarvis_speech already remembered for its last three attempts - it never opens
the microphone itself, never checkpoints a database and never restarts
anything.


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
  * graphics cards: jarvis_compute.query_cards (nvidia-smi), jarvis_hardware's
    health reading (heat, power, fan, load, pstate, clocks, and the driver's
    reason flags - the same readings the Hardware and models screen shows) and
    jarvis_compute.query_apps (--query-compute-apps: WHICH programs hold a
    card; this PC's driver reports no per-program amount, and that is kept as
    "not told", never a guess); Ollama's own /api/ps on loopback for which
    models are loaded and how much card memory each uses. Two cards with the
    same name and size are told apart by jarvis_profiles.card_label (the
    monitor first, the card's own id tail last) - the Hardware page's rule.

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
from pathlib import Path
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

# --------------------------------------------------------------------------
#   Pillar 28 (2026-10-17): the silent-failure doctor
# --------------------------------------------------------------------------
# Four checks that run inside "Check now" and add their own warning section
# only when something has failed quietly (the healthy answer is still exactly
# the five the apps know). None of them changes anything: the WAL check only
# reads file sizes (a passive checkpoint is OFFERED in words through
# `safe_passive_checkpoint_statement()` and never run here), the phone check
# only reads the pairing registry (it cannot test the network), the Ollama
# check asks one loopback question, and the microphone check reads the peak
# RMS jarvis_speech already remembered for the last three voice attempts - PC
# help itself never opens the microphone.
#:
#: The four check ids, in the order `silent.checked` lists them. Stable - the
#: apps may rely on these names, never on a section existing.
SILENT_CHECKS = ("digital_zero_mic", "wal_bloat", "phone_unreachable",
                 "ollama_wedged")
#: N_placeholder (Law 9): 64 MiB, three attempts and seven days are the
#: blueprint's thresholds, not measured on this PC; recalibrate when the
#: owner's own logs and phone habits have been observed.
WAL_LIMIT_BYTES = 64 * 1024 * 1024
MIC_ZERO_ATTEMPTS = 3
PHONE_STALE_SECONDS = 7 * 24 * 3600
OLLAMA_TIMEOUT = 2.0                   # the phone's whole read budget is 20 s

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
    cards()    -> [{"name", "uuid", "pci_id", "display_active", "index",
                    "used_mib", "total_mib", "free_mib", "temp_c", "hot_slowdown",
                    "load_percent", "power_w", "power_limit_w", "fan_percent",
                    "pstate", "clock_mhz", "max_clock_mhz", "idle", "power_capped",
                    "state"}]
        Only the keys a reading could fill are present; `state` is
        jarvis_hardware.card_state's one of "hot"/"idle"/"power_limited"/
        "working"/"unknown". `display_active` is True/False/None.
    models()   -> [{"name", "vram_bytes"}]   Ollama's loaded models
    apps()     -> [{"pid", "name", "uuid", "used_mib"}]  nvidia-smi's own
        process list. `used_mib` is None when the driver does not report it
        (measured on this PC 2026-10-17: it is [N/A] for every process), and
        must stay None - never a made-up 0.
    mic()      -> jarvis_speech.voice_attempts_status(): {"attempts",
                   "zeros_in_a_row", "digital_zero", "device", "last_peak_rms",
                   "last_at"} (Pillar 28: the last 3 voice attempts' peak RMS)
    databases()-> [{"name", "path", "wal_bytes"}] for the .db-wal files in
                   Jarvis's home folder (Pillar 28)
    devices()  -> jarvis_devices.paired_status(): {"devices": [{"id", "name",
                   "kind", "created", "last_seen", "reach"}], "readable",
                   "why"} (Pillar 28)
    ollama()   -> {"state": "ok" | "not_running" | "wedged" | "error",
                   "why": <name>} - one loopback /api/ps question (Pillar 28)
    """
    programs: Callable[[], Optional[dict]]
    memory: Callable[[], Optional[dict]]
    disks: Callable[[], Optional[list]]
    uptime: Callable[[], Optional[float]]
    cards: Callable[[], Optional[list]]
    models: Callable[[], Optional[list]]
    apps: Optional[Callable[[], Optional[list]]] = None
    mic: Optional[Callable[[], Optional[dict]]] = None
    databases: Optional[Callable[[], Optional[list]]] = None
    devices: Optional[Callable[[], Optional[dict]]] = None
    ollama: Optional[Callable[[], Optional[dict]]] = None
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
        import jarvis_child_env
        out = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                             capture_output=True, text=True, timeout=PS_TIMEOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             env=jarvis_child_env.inherited())
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
    """Each NVIDIA card's own facts, from the same two readings the Hardware
    and models screen uses (nvidia-smi's card list and its health query).
    Identity (`uuid`, `pci_id`, `display_active`) is kept so two identical
    cards can be told apart in words, and `used_mib` is measured memory in
    use, never a guess. A card whose health could not be read still gets its
    memory line, with the state honestly None."""
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
    state_of = getattr(HW, "card_state", None)
    out = []
    for c in cards:
        h = HW.health_for({"uuid": getattr(c, "uuid", ""), "index": getattr(c, "index", None)},
                          health) or {}
        total = getattr(c, "total_mb", None)
        free = getattr(c, "free_mb", None)
        used = (total - free) if isinstance(total, (int, float)) and isinstance(
            free, (int, float)) and total > 0 else None
        out.append({"name": str(getattr(c, "name", "") or "Graphics card"),
                    "uuid": str(getattr(c, "uuid", "") or ""),
                    "pci_id": str(getattr(c, "pci_id", "") or ""),
                    "display_active": getattr(c, "display_active", None),
                    "index": getattr(c, "index", None),
                    "used_mib": used, "total_mib": total,
                    "free_mib": free if isinstance(free, (int, float)) else None,
                    "temp_c": h.get("temp_c"), "hot_slowdown": h.get("hot_slowdown"),
                    "load_percent": h.get("load_percent"),
                    "power_w": h.get("power_w"), "power_limit_w": h.get("power_limit_w"),
                    "fan_percent": h.get("fan_percent"),
                    "pstate": h.get("pstate"), "clock_mhz": h.get("clock_mhz"),
                    "max_clock_mhz": h.get("max_clock_mhz"),
                    "idle": h.get("idle"), "power_capped": h.get("power_capped"),
                    "state": (state_of(h) if callable(state_of) and h else None)})
    return out


def _read_apps() -> Optional[list]:
    """nvidia-smi's own list of the programs using a card, or None when it
    cannot be read. On this PC the list is real and the per-program amounts
    are not (the driver answers [N/A]); jarvis_compute keeps that distinction
    as None, and so does this reader."""
    try:
        import jarvis_compute as CP
        reader = getattr(CP, "query_apps", None)
        return reader() if callable(reader) else None
    except Exception:
        return None


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


# ---- Pillar 28: the four silent-failure readings (all read-only) ----------

def _home_dir() -> Path:
    """Jarvis's own settings/data folder. OPENJARVIS_HOME (the name the
    Pillar 28 blueprint uses) is honoured first, then this codebase's
    OPENJARVIS_CONFIG_DIR / JARVIS_CONFIG_DIR, else ~/.openjarvis."""
    env = (os.environ.get("OPENJARVIS_HOME") or os.environ.get("OPENJARVIS_CONFIG_DIR")
           or os.environ.get("JARVIS_CONFIG_DIR"))
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def _read_mic() -> Optional[dict]:
    """The peak RMS of the last few voice attempts, from jarvis_speech's
    in-memory meter. PC help never opens the microphone."""
    try:
        import jarvis_speech as S
        reader = getattr(S, "voice_attempts_status", None)
        return reader() if callable(reader) else None
    except Exception:
        return None


def _read_databases() -> Optional[list]:
    """The .db-wal files in Jarvis's home folder ($OPENJARVIS_HOME/*.db-wal),
    with their size. A stat() per file, nothing else - a passive checkpoint is
    never run here. None when the folder cannot be listed at all."""
    root = _home_dir()
    try:
        paths = sorted(root.glob("*.db-wal"))
    except Exception:
        return None
    rows = []
    for p in paths:
        try:
            rows.append({"name": p.name[:-len("-wal")], "path": str(p),
                         "wal_bytes": p.stat().st_size})
        except OSError:
            continue
    return rows


def _read_devices() -> Optional[dict]:
    """The paired devices, when each was last heard from, and whether it has
    remote reach, from jarvis_devices. Read-only; never a token or key."""
    try:
        import jarvis_devices as D
        reader = getattr(D, "paired_status", None)
        return reader() if callable(reader) else None
    except Exception:
        return None


def _read_ollama() -> Optional[dict]:
    """One loopback question to this PC's Ollama's /api/ps, and - the point -
    WHY it failed when it did: the TCP port refused (the process is not
    running) or it accepted and /api/ps did not answer in time (running, but
    wedged). Those need different words and different fixes. Never raises; a
    missing Ollama answers "not_running"."""
    try:
        import jarvis_hardware as HW
        base = HW._main_url()
    except Exception:
        return None
    url = f"{base}/api/ps"
    try:
        import jarvis_local_http
        with jarvis_local_http.opener().open(url, timeout=OLLAMA_TIMEOUT) as reply:
            reply.read(1024)
        return {"state": "ok"}
    except Exception as exc:
        # Deliberately NO urllib import (test_pc_help checks this module never
        # imports it): the exception already carries what is needed. urllib
        # wraps a refused connect as URLError(reason=ConnectionRefusedError)
        # and a timeout as URLError(reason=TimeoutError) or TimeoutError.
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ConnectionRefusedError):
            return {"state": "not_running"}
        if isinstance(reason, TimeoutError) or isinstance(exc, TimeoutError):
            return {"state": "wedged"}
        if "timed out" in str(reason).lower() or "timed out" in str(exc).lower():
            return {"state": "wedged"}
        return {"state": "error", "why": type(reason).__name__}


def real_readers() -> Readers:
    return Readers(programs=_cached_programs, memory=_read_memory, disks=_read_disks,
                   uptime=_read_uptime, cards=_read_cards, models=_read_models,
                   apps=_read_apps, mic=_read_mic, databases=_read_databases,
                   devices=_read_devices, ollama=_read_ollama)


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


def _program_label(name: str) -> str:
    """A program's own file name, without its folder: the nvidia-smi process
    list names a full path, and the owner reads the short name."""
    base = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    return _clean_name(base) or "a program"


def _profile_card(c, key: str):
    """The jarvis_profiles.Card a reader's plain dict describes, for the
    shared twin-naming rule (jarvis_profiles.card_label). None when profiles
    cannot be imported, so the doctor falls back to the plain name."""
    import jarvis_profiles as P
    total = c.get("total_mib")
    try:
        gib = float(total) / 1024.0 if total is not None else 0.0
    except (TypeError, ValueError):
        gib = 0.0
    return P.Card(key=key, name=str(c.get("name") or "A graphics card"),
                  total_gib=gib, monitor=c.get("display_active"),
                  uuid=str(c.get("uuid") or ""))


def _labels(cards: list) -> list:
    """Each card's name, told apart from a twin the same way the Hardware and
    models page tells them apart (jarvis_profiles.card_label: the monitor
    first, the card's own id tail when that cannot say). One card keeps its
    plain name, so today's PC reads exactly as it always did. Never raises."""
    plain = [str(c.get("name") or "A graphics card") for c in cards]
    try:
        pcs = [_profile_card(c, str(c.get("uuid") or c.get("pci_id") or c.get("index") or i))
               for i, c in enumerate(cards)]
        import jarvis_profiles as P
        return [P.card_label(pc, pcs) for pc in pcs]
    except Exception:
        return plain


def _apps_by_card(cards: list, apps: Optional[list]) -> dict:
    """{card index: [{"pid", "name", "used_mib"}]} from nvidia-smi's own
    process list. A process whose card id matches nothing here is left out
    (it is not the doctor's to guess which card it is on)."""
    by_uuid: dict = {}
    for a in apps or []:
        if not isinstance(a, dict):
            continue
        uuid = str(a.get("uuid") or "").lower()
        if uuid:
            by_uuid.setdefault(uuid, []).append(a)
    out: dict = {}
    for i, c in enumerate(cards or []):
        uuid = str(c.get("uuid") or "").lower()
        out[i] = by_uuid.get(uuid, []) if uuid else []
    return out


def _held_words(held: list) -> tuple:
    """(one card's "Programs holding it: ..." sentence or "", names_programs).
    At most `TOP_N` names are shown - the same limit the processor and memory
    answers use - because a desktop card can easily have twenty programs on it
    (measured: 23 on this PC's 2080 SUPER), and a wall of names helps nobody;
    "and N more" says the rest. Amounts are printed only when the driver
    reports one for EVERY program there; on this PC it reports none, and the
    words say so instead of inventing a number."""
    merged: dict = {}
    for a in held:
        label = _program_label(a.get("name"))
        key = "model" if _is_model(label) else label.lower()
        row = merged.setdefault(key, {"name": MODEL_WORDS if key == "model" else label,
                                      "used_mib": 0, "amounts": True})
        used = a.get("used_mib")
        if isinstance(used, int) and not isinstance(used, bool):
            row["used_mib"] += used
        else:
            row["amounts"] = False
    rows = sorted(merged.values(),
                  key=lambda r: (0 if r["name"] == MODEL_WORDS else 1, r["name"].lower()))
    shown = rows[:TOP_N]
    parts = []
    for row in shown:
        part = MODEL_WORDS if row["name"] == MODEL_WORDS else row["name"]
        if row["amounts"]:
            part += f" ({_gb(row['used_mib'] * 1024 ** 2)})"
        parts.append(part)
    extra = len(rows) - len(shown)
    if extra > 0:
        parts.append(f"{extra} more")
    return _join(parts), any(r["name"] != MODEL_WORDS for r in rows)


def _card_used_fraction(c):
    used, total = c.get("used_mib"), c.get("total_mib")
    if isinstance(used, (int, float)) and isinstance(total, (int, float)) and total > 0:
        return max(0.0, min(1.0, float(used) / float(total)))
    return None


def _card_worry(cards: list) -> tuple:
    """(card label, why) for the first card worth mentioning on its own -
    "hot" (the driver's own thermal slow-down reason) or "nearly_full" (90 %
    or more measured memory in use) - else ("", ""). Used by "why is my PC
    slow" when the processor and memory look calm."""
    for i, c in enumerate(cards):
        if c.get("hot_slowdown") is True:
            return i, "hot"
        frac = _card_used_fraction(c)
        if frac is not None and frac >= 0.9:
            return i, "nearly_full"
    return -1, ""


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
    # If the processor and memory look calm and a card is hot or nearly full,
    # say so: that is the measured reason answers can still be slow, and the
    # action that helps. No program is named here, so this stays not-private.
    calm = cpu is not None and mem_pct is not None and cpu < 50 and mem_pct < 75
    if calm:
        try:
            cards = r.cards() or []
        except Exception:
            cards = []
        if cards:
            i, why = _card_worry(cards)
            if i >= 0:
                label = _labels(cards)[i]
                if why == "hot":
                    bits.append(f"If Jarvis feels slow, its AI model is on the {label}, which "
                                f"is running hot - stop the model that is running, or check the "
                                f"PC's fans and vents, then try again.")
                else:
                    bits.append(f"If Jarvis feels slow, its AI model is on the {label}, which "
                                f"is nearly full - use a smaller model in Brain > Model, or turn "
                                f"off a feature you are not using.")
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
    """(words, names_programs). Every card, in plain words: memory in use and
    how busy it is, what state it is in, whether it is nearly full, the
    programs holding it, and Jarvis's own loaded model. True when it names a
    program other than Jarvis's own (that answer then stays private).

    MEASURED ON THIS PC (2026-10-17): nvidia-smi names the programs holding a
    card but reports no amount for any of them (`used_memory` is [N/A]), so
    the amount is shown only when the driver reports it, and the words say
    plainly when it does not. Windows' own counter gives a program's total
    graphics memory across every card, so it is labelled as a total and never
    presented as one card's number."""
    cards = r.cards()
    models = r.models()
    reading = r.programs()
    apps = None
    try:
        if callable(getattr(r, "apps", None)):
            apps = r.apps()
    except Exception:
        apps = None
    bits = []
    names = False
    if cards:
        labels = _labels(cards)
        by_card = _apps_by_card(cards, apps)
        no_amounts = False
        for i, c in enumerate(cards):
            line = labels[i]
            if c.get("used_mib") is not None and c.get("total_mib"):
                line += (f": {_gb(c['used_mib'] * 1024 ** 2)} of "
                         f"{_gb(c['total_mib'] * 1024 ** 2)} of its memory in use")
            if c.get("load_percent") is not None:
                line += f", {c['load_percent']}% busy"
            line += "."
            if c.get("hot_slowdown") is True:
                line += (" It is slowing itself down to cool off, which makes answers slower. "
                         "Stop the model that is running, or check the PC's fans and vents, then "
                         "try again in a minute.")
            elif c.get("state") == "idle":
                line += " It is not doing any work right now - that is normal."
            elif c.get("state") == "power_limited":
                line += " It is at its power limit, which is normal while it is working hard."
            frac = _card_used_fraction(c)
            if frac is not None and frac >= 0.9:
                free = max(0.0, (c["total_mib"] - c["used_mib"]) * 1024 ** 2)
                line += (f" It is nearly full: only {_gb(free)} free, so a bigger model will "
                         f"not fit. Use a smaller model in Brain > Model, or turn off a feature "
                         f"you are not using.")
            held = by_card.get(i) or []
            if held:
                said, held_names = _held_words(held)
                if said:
                    line += f" Programs holding it: {said}."
                    names = names or held_names
                    measured = all(isinstance(a.get("used_mib"), int)
                                   and not isinstance(a.get("used_mib"), bool) for a in held)
                    if not measured:
                        no_amounts = True
            bits.append(line)
        if no_amounts:
            bits.append("This PC's driver does not report how much graphics memory each "
                        "program uses, so Jarvis can only list the programs holding a card.")
        loaded = [m for m in (models or []) if m.get("name")]
        on_card = [m for m in loaded if (m.get("vram_bytes") or 0) > 0]
        if on_card:
            bits.append("Jarvis's AI " + ("model " if len(on_card) == 1 else "models ")
                        + _join([f"{m['name']} ({_gb(m['vram_bytes'])})" for m in on_card])
                        + (" is" if len(on_card) == 1 else " are") + " loaded.")
        elif models is not None:
            bits.append("Jarvis's AI model is not loaded on a card right now.")
    others = []
    if reading:
        rows = [p for p in _programs(reading, r.own_pid)
                if not p["model"] and p["gpu_bytes"] >= 50 * 1024 ** 2]
        others = sorted(rows, key=lambda p: -p["gpu_bytes"])[:TOP_N]
    if others:
        bits.append("Other programs using graphics memory on this PC (their total, not one "
                    "card): " + _join([f"{p['name']} ({_gb(p['gpu_bytes'])})" for p in others]) + ".")
        names = True
    if not bits:
        return (NO_NVIDIA if cards == [] else COULD_NOT), False
    return " ".join(bits), names


def heat_words(r: Readers) -> str:
    """Every card's temperature in plain words, with what it means and what to
    do. The driver's own thermal slow-down reason is the only thing called
    "slowing itself down"; a card that is merely resting says so, because an
    idle card is not a hot card (measured 2026-10-17: both cards sit at
    P8/300 MHz and 29-35 °C on this PC)."""
    cards = r.cards()
    if cards is None:
        return COULD_NOT
    temps = [c for c in cards if c.get("temp_c") is not None]
    if not temps:
        return NO_TEMP
    labels = _labels(cards)
    parts = []
    for i, c in enumerate(cards):
        if c.get("temp_c") is None:
            continue
        t = c["temp_c"]
        state = c.get("state")
        if c.get("hot_slowdown") is True:
            say = ("hot - it is slowing itself down to cool off, which makes answers slower. "
                   "Stop the model that is running, or check the PC's fans and vents, then try "
                   "again in a minute")
        elif t >= 85:
            say = "hot, near where cards like it start slowing down"
        elif state == "idle" and t < 75:
            say = "fine - and not doing any work right now, which is normal"
        elif t >= 75:
            say = "warm, which is normal while it is working hard"
        else:
            say = "fine"
        parts.append(f"{labels[i]} is at {t} °C: {say}.")
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
#   Pillar 28: the silent-failure checks
# --------------------------------------------------------------------------
#
# `diagnose_silent_failures()` is the one public entry: a list of findings
# (0..4), each {"id", "title", "words"} using the four ids in SILENT_CHECKS
# and in that order. A check that cannot read - or has too little to tell -
# returns nothing: it must not claim a failure it did not see. All four are
# read-only; the WAL finding OFFERS a passive checkpoint through
# `safe_passive_checkpoint_statement()` and never runs one.

def _mb(n: float) -> str:
    return f"{n / (1024 ** 2):.0f} MB"


def _is_time(value) -> bool:
    """A reading that means seconds: a real number, but never a bool (True is
    1 in Python and would read as a 1970 timestamp)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _now(r: Readers) -> float:
    try:
        return float(r.now())
    except Exception:
        return time.time()


def _reading(r: Readers, name: str):
    """One of the silent-failure readings, or None. Never raises."""
    fn = getattr(r, name, None)
    if not callable(fn):
        return None
    try:
        return fn()
    except Exception:
        return None


def safe_passive_checkpoint_statement() -> str:
    """The one safe repair for a bloated write-ahead log, OFFERED as a
    diagnostic and never run by PC help (it only reads). SQLite's PASSIVE
    checkpoint waits for no one, removes no data and leaves the database
    usable throughout: the log is folded back into the database."""
    return "PRAGMA wal_checkpoint(PASSIVE);"


def _digital_zero_mic(r: Readers) -> Optional[dict]:
    """Three voice attempts in a row whose peak RMS was exactly 0.0: a
    microphone that has gone deaf (the state some PCs leave it in after
    sleep), not a quiet room. Names the input device Jarvis heard it from."""
    status = _reading(r, "mic")
    if not isinstance(status, dict) or status.get("digital_zero") is not True:
        return None
    tries = status.get("zeros_in_a_row")
    tries = tries if isinstance(tries, int) and tries >= MIC_ZERO_ATTEMPTS else MIC_ZERO_ATTEMPTS
    device = str(status.get("device") or "the microphone")
    return {"id": "digital_zero_mic",
            "title": "The microphone is giving Jarvis silence",
            "words": (f"Every one of the last {tries} voice attempts from {device} was pure "
                      "digital silence - every sample exactly 0.000 - so a quiet room does "
                      "not explain it. A microphone can go deaf like this after the PC wakes "
                      "from sleep. Unplug the microphone and plug it back in, or restart the "
                      "PC (or the phone, if that is where the sound came from), then press "
                      "Check now again.")}


def _wal_bloat(r: Readers) -> Optional[dict]:
    """A SQLite write-ahead log past 64 MiB in Jarvis's home folder: the
    database is healthy but its writes have not been folded back. Names each
    database; a passive checkpoint is the safe repair, offered here and NOT
    run."""
    rows = _reading(r, "databases")
    if not isinstance(rows, list):
        return None
    big = []
    for d in rows:
        if not isinstance(d, dict):
            continue
        size = d.get("wal_bytes")
        if _is_time(size) and size > WAL_LIMIT_BYTES:
            big.append((str(d.get("name") or "a database"), size))
    if not big:
        return None
    big.sort(key=lambda item: -item[1])
    shown = _join([f"{_mb(size)} for {name}" for name, size in big[:TOP_N]])
    more = f", and {len(big) - TOP_N} more" if len(big) > TOP_N else ""
    return {"id": "wal_bloat",
            "title": "Jarvis's database log is very large",
            "words": ("Jarvis's database write-ahead logs have grown very large: "
                      f"{shown}{more}. They are the .db-wal files in Jarvis's own folder "
                      f"({_home_dir()}). The databases are healthy, but recent writes have not "
                      "been folded back into them for a while. A passive checkpoint would fold "
                      f"a log back - that is SQLite's {safe_passive_checkpoint_statement()!r}, a "
                      "safe diagnostic that deletes nothing - and PC help does not run it "
                      "because it only reads. Restart Jarvis on the PC: a clean shutdown "
                      "checkpoints these logs, and nothing is deleted.")}


def _phone_unreachable(r: Readers) -> Optional[dict]:
    """A paired phone with remote reach that has not checked in past the
    staleness threshold: its changes have silently stopped syncing. This PC
    can only read the last-check-in time - it cannot test Tailscale or Meshnet
    reachability - so the words say so."""
    status = _reading(r, "devices")
    if not isinstance(status, dict) or status.get("readable") is False:
        return None
    now = _now(r)
    stale = []
    for d in status.get("devices") or []:
        if not isinstance(d, dict) or d.get("kind") != "phone":
            continue
        if d.get("reach") is False:
            continue
        seen = d.get("last_seen")
        created = d.get("created")
        if _is_time(seen):
            if now - seen > PHONE_STALE_SECONDS:
                stale.append((d, seen))
        elif _is_time(created) and now - created > PHONE_STALE_SECONDS:
            stale.append((d, None))
    if not stale:
        return None
    row, seen = sorted(stale, key=lambda item: -item[0].get("last_seen")
                       if _is_time(item[0].get("last_seen")) else 0)[0]
    name = str(row.get("name") or "your phone")
    if seen is None:
        since = f"it has not checked in since it was paired {_ago(now - row['created'])}"
    else:
        since = f"it was last heard from {_ago(now - seen)} ({_when(seen, now)})"
    return {"id": "phone_unreachable",
            "title": "Your phone has not checked in",
            "words": (f"The phone {name} has not checked in: {since}, so nothing from it has "
                      "synced since then. Jarvis cannot tell from this PC whether the phone is "
                      "on your own network. Open Jarvis on the phone, check it is on the same "
                      "Tailscale or NordVPN Meshnet network as this PC, and use it once; then "
                      "press Check now again.")}


def _ollama_wedged(r: Readers) -> Optional[dict]:
    """The model service's two silent failures, said differently because the
    fixes differ: the process is not running (its TCP port refused) vs running
    but wedged (the port opened and /api/ps timed out)."""
    status = _reading(r, "ollama")
    if not isinstance(status, dict):
        return None
    state = str(status.get("state") or "")
    if state == "not_running":
        return {"id": "ollama_wedged",
                "title": "Jarvis's model service is not running",
                "words": ("The program that writes Jarvis's answers on this PC (Ollama) is not "
                          "running - its port refused the connection - so no answer can be "
                          "written until it is. Open Ollama from the Start menu (or let Jarvis "
                          "start it), then press Check now again.")}
    if state == "wedged":
        return {"id": "ollama_wedged",
                "title": "Jarvis's model service is not answering",
                "words": ("The program that writes Jarvis's answers on this PC (Ollama) is "
                          "running: its TCP port is open, but /api/ps did not answer within "
                          f"{OLLAMA_TIMEOUT:.0f} seconds. That is why answers seem to never "
                          "arrive. Quit Ollama from its icon by the clock, then open it again "
                          "from the Start menu, and press Check now again.")}
    return None


def diagnose_silent_failures(readers: Optional[Readers] = None) -> list:
    """The Pillar 28 silent-failure doctor: a list of findings, 0 to 4, in
    SILENT_CHECKS' order. Each finding is {"id", "title", "words"} - the id is
    one of SILENT_CHECKS, and `words` is the one plain paragraph the apps show
    for it. A check that cannot read returns nothing rather than a guess, and
    no check changes anything. Never raises."""
    r = readers or real_readers()
    found = []
    for check in (_digital_zero_mic, _wal_bloat, _phone_unreachable,
                  _ollama_wedged):
        try:
            got = check(r)
        except Exception:
            got = None
        if got:
            found.append(got)
    return found


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
    """GET /api/pc/help: the five answers, in the order of TOPICS, plus one
    warning section per Pillar 28 silent failure found (so a healthy answer
    still has exactly five). `silent` says what was checked and what failed,
    for anything that wants the facts rather than the words."""
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
    findings = diagnose_silent_failures(r)
    for finding in findings:
        sections.append({"id": finding["id"], "title": finding["title"],
                         "words": finding["words"], "programs": False})
    return {"ok": True, "at": at, "sections": sections, "changes": CHANGES_LATER,
            "private": PRIVATE_NOTE,
            "silent": {"checked": list(SILENT_CHECKS),
                       "failed": [f["id"] for f in findings], "at": at}}




def handle_get(query: str = "", readers: Optional[Readers] = None) -> tuple:
    """(status, body) for GET /api/pc/help. Takes no parameters."""
    try:
        return 200, read(readers)
    except Exception as exc:
        return 500, {"error": type(exc).__name__}
