"""jarvis_big_model.py - an optional "big model (slow)" lane for background jobs.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).
The owner's guide is docs/BIG-MODEL.md.

WHAT IT IS FOR. colibri (https://github.com/JustVugg/colibri, Apache-2.0) is
an inference engine that runs very large "mixture of experts" models on an
ordinary PC by keeping most of the model on the SSD and reading only the
parts each word needs. That makes models far bigger than the graphics card
possible - and slow. So this lane is for work nobody is waiting on:

    wiki             the wiki builder (jarvis_wiki.py) uses the big model
                     instead of the second card's lane
    deep_questions   "think about this properly": one question, answered in
                     the background, the answer kept for the owner to read

and NEVER for chat, voice or approvals. Only those two job ids may call
lane_for(); any other id gets None.

NOTHING FROM COLIBRI IS IN HERE. Jarvis starts `coli serve` and talks to its
OpenAI-compatible HTTP API on 127.0.0.1, the same way it talks to Ollama.
No colibri code was copied.

WHAT COLIBRI'S DOCS SAY, and where (a clone read on 2026-09-24, v1.12.0):

  - Memory. README.md, "What each one needs": Qwen3.6-35B-A3B ~20 GB on disk,
    "24 GB (needs full RAM residency)"; DeepSeek V4 Flash ~167 GB (REAP 150B
    ~85 GB), "16 GB min, 32 GB comfortable". docs/qwen36.md: "~30 GB RAM for
    comfortable expert caching". Those are the numbers used below.
  - The serve command and the key. docs/api.md: `coli serve --host 127.0.0.1
    --port 8000 --model-id <id>`, key from COLI_API_KEY, sent as
    `Authorization: Bearer <key>`; docs/SETTINGS.md lists `--api-key` as
    defaulting to $COLI_API_KEY. `coli serve` runs the gateway in-process
    (c/coli, cmd serve), so the key never appears on a command line.
  - Structured output. docs/grammar-draft.md, "Server usage: response_format":
    a schema is "a draft source, never a sampling constraint", and
    c/openai_server.py refuses `response_format` with HTTP 400 on every
    engine whose family lacks `grammar_payload` - which is every engine but
    GLM (c/family_registry.py). So Jarvis never sends it: the schema goes in
    the instructions and jarvis_wiki's own strict validation decides.
  - Readiness. c/openai_server.py serve(): the port is bound BEFORE the model
    loads and requests are answered only after. So "connects but does not
    answer" means "still loading", and the check below waits with a short
    timeout rather than treating that as a failure.
  - GPU. docs/deepseek-v4.md says the Windows release "also contains the CUDA
    backend", but the release workflow in the same clone
    (.github/workflows/release.yml) packages no CUDA DLL, and the CUDA DLL
    CI does build (.github/workflows/ci.yml, windows-cuda-build) is a 30-day
    artifact for sm_80 and newer (c/Makefile, CUDA_ARCH=portable). The
    owner's cards are Turing (sm_75). So `cuda = "on"` needs a source build;
    docs/BIG-MODEL.md says how heavy that is. Off by default.

THE PERMISSION MODEL (docs/ARCHITECTURE.md section 3). Three switches, all
off, kept in <config dir>/big-model.json: `master`, `wiki`, `deep_questions`.
Turning one ON is one approval card through jarvis_gate, action
`big_model_enable`, tier "ask" (checked before the card and again on the
answer - the same shape as jarvis_second_card). A second ON while a card
waits is refused (409). OFF is immediate. Nothing here auto-approves.

A switch can only be turned on once colibri is found, Python 3 is found
(colibri's launcher is a Python script - its docs/windows.md), a configured
model folder with a config.json exists, and the PC has enough RAM in total
and free disk on that drive.

THE ENGINE PROCESS. Started ON DEMAND by lane_for() for a job, never kept
resident (the medium model alone takes about 24 of the PC's 32 GB), and
stopped after `[big_model] idle_minutes` (default 10) with no job, when the
switches go off, and when Jarvis exits. Refused, with the numbers, when the
PC does not have the model's memory free right now.

    <python> <colibri folder>/coli serve --model <dir> --host 127.0.0.1
        --port <[big_model] port, 8765> --model-id <id> --ctx <ctx>
        --gpu none | 0                    (+ --ram <GB> for a giant model)

`coli.cmd` itself is what docs/windows.md says to run; it only finds Python
and runs `coli` beside it. Jarvis does that step itself, because a .cmd file
is read by cmd.exe, which re-reads its arguments - a model folder with a & or
% in its name could then run something else. coli.cmd is used only when the
`coli` script is not beside it, and then no argument may hold such a
character.

    COLI_API_KEY=<key>       the ONLY way the key reaches colibri
    CUDA_VISIBLE_DEVICES     "-1" (no card) by default; the SECOND card's id
                             only with cuda = "on" - never the main card,
                             which is everyday chat
    COLI_CUDA / DSV4_CUDA    "0" by default (DSV4_CUDA is DeepSeek V4's own
                             switch - docs/ENVIRONMENT.md)

THE KEY. Made here, kept in Windows Credential Manager under
"Jarvis Big Model/api key" (jarvis_token_store.WindowsStore), handed to
colibri only through COLI_API_KEY, and sent only as a Bearer header to
http://127.0.0.1:<port> - through an opener with no proxy, so it cannot
leave by way of one. Never logged, never in status(), an error or a card
(CLAUDE.md rule 3). Where Credential Manager is not available it lives in
memory for this run only.

DEEP QUESTIONS. POST /api/deep/ask queues one background job; it asks the
big model the question with no tools, no memory and no web, and keeps the
answer in <config dir>/deep-questions.jsonl, capped. There is NO approval
card per question, on purpose: the owner approved the switch, a question
acts on nothing and nothing leaves this PC. Every job's speed is measured
and kept (tokens and words per second), because none of colibri's speed
claims have been checked on this PC.

Standard library only.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


# --------------------------------------------------------------------------
#   Constants
# --------------------------------------------------------------------------

ACTION = "big_model_enable"
HOST = "127.0.0.1"
DEFAULT_PORT = 8765
#: Ports that are someone else's: the everyday Ollama and the second card's.
RESERVED_PORTS = (11434, 11435)
DEFAULT_IDLE_MINUTES = 10
DEFAULT_CTX = 16384
DEFAULT_LOAD_MINUTES = 20
DEFAULT_ANSWER_MINUTES = 60
DEFAULT_DEEP_MAX_TOKENS = 2048
CRED_TARGET = "Jarvis Big Model/api key"

#: What each kind of model needs, from colibri's README.md table ("What each
#: one needs") - see the module docstring.
KIND_NEEDS = {
    # total RAM the PC must have / free RAM needed to start / what colibri says
    "medium": {"total_gb": 24.0, "start_gb": 24.0,
               "says": "24 GB, because the whole model is held in memory "
                       "(colibri's README.md; docs/qwen36.md: ~30 GB is comfortable)"},
    "giant": {"total_gb": 16.0, "start_gb": 16.0,
              "says": "16 GB at least, 32 GB comfortable (colibri's README.md)"},
}
#: colibri writes small files into the model's folder (.coli_usage, .coli_kv,
#: and for DeepSeek V4 prefix checkpoints of ~140 MB each in .coli_ckpt -
#: docs/deepseek-v4.md), so the drive must not be full.
MIN_FREE_DISK_GB = 2.0

JOBS = ("wiki", "deep_questions")
SWITCHES = ("master",) + JOBS
JOB_NAMES = {"wiki": "Wiki builder", "deep_questions": "Deep questions"}
JOB_WHAT = {
    "wiki": ("The wiki builder uses the big model, on this PC's processor and SSD, instead "
             "of the second graphics card. Much slower; for when you want a bigger model "
             "to write the pages, or have no second card."),
    "deep_questions": ("Ask a question that deserves a careful answer. It is answered in "
                       "the background by the big model and kept for you to read later."),
}

UNVERIFIED = ("None of colibri's speed figures have been checked on this PC. The numbers "
              "Jarvis records here, from your own jobs, are the first real ones.")

_ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
#: Characters cmd.exe gives a meaning to. Only matters on the coli.cmd route.
_CMD_META = set('&|<>^%!"\r\n')


@dataclass(frozen=True)
class Lane:
    """Where a job's model calls go: always http://127.0.0.1:<port>. The
    same four fields as jarvis_second_card.Lane. The key is NOT in it: a
    Lane may be printed; the key is added by chat() at the socket."""
    url: str
    model: str
    num_ctx: int
    why: str

    #: Not a field. Tells jarvis_wiki this lane speaks colibri's
    #: OpenAI-compatible API, not Ollama's /api/chat.
    protocol = "openai"


# --------------------------------------------------------------------------
#   Things the tests replace
# --------------------------------------------------------------------------

_popen = subprocess.Popen
_which = shutil.which
_ON_WINDOWS = os.name == "nt"


def _now() -> float:
    return time.time()


def _mono() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-big-model", daemon=True).start()


def _new_id() -> str:
    return "deep_" + secrets.token_hex(6)


def _make_key() -> str:
    return secrets.token_urlsafe(32)


def _run(cmd: list, timeout: float) -> tuple:
    """(return code, stdout) of a short command; (None, "") on any failure."""
    try:
        kw: dict = {"capture_output": True, "text": True, "timeout": timeout}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000        # no console window
        r = subprocess.run(cmd, **kw)
        return r.returncode, r.stdout or ""
    except Exception:
        return None, ""


def _isfile(p) -> bool:
    try:
        return Path(p).is_file()
    except Exception:
        return False


def _isdir(p) -> bool:
    try:
        return Path(p).is_dir()
    except Exception:
        return False


def _memory() -> tuple:
    """(total bytes, available bytes) of RAM, or (None, None)."""
    try:
        if os.name == "nt":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return None, None
            return int(st.ullTotalPhys), int(st.ullAvailPhys)
        vals = {}
        with open("/proc/meminfo", encoding="ascii", errors="replace") as f:
            for line in f:
                k, _, rest = line.partition(":")
                parts = rest.split()
                if parts and parts[0].isdigit():
                    vals[k.strip()] = int(parts[0]) * 1024
        total, avail = vals.get("MemTotal"), vals.get("MemAvailable")
        return total, avail
    except Exception:
        return None, None


def _disk_free(path) -> Optional[int]:
    try:
        return int(shutil.disk_usage(str(path)).free)
    except Exception:
        return None


_DRIVE_TYPES: dict = {}          # drive -> (type, when)
_DRIVE_SECONDS = 600.0


def _drive_type(drive: str) -> str:
    """"NVMe", "SATA SSD", "SATA HDD", "USB", "SSD", "HDD" or "unknown".
    Windows only (Get-Partition, then Get-PhysicalDisk), never longer than
    a few seconds, cached ten minutes; anything else is "unknown"."""
    if os.name != "nt" or not re.fullmatch(r"[A-Za-z]:", drive or ""):
        return "unknown"
    hit = _DRIVE_TYPES.get(drive.upper())
    if hit and _mono() - hit[1] < _DRIVE_SECONDS:
        return hit[0]
    letter = drive[0].upper()
    script = ("$ErrorActionPreference='Stop'; "
              f"$n=(Get-Partition -DriveLetter {letter}).DiskNumber; "
              "$p=Get-PhysicalDisk | Where-Object { $_.DeviceId -eq [string]$n } | "
              "Select-Object -First 1; "
              "if ($p) { [string]$p.BusType + '|' + [string]$p.MediaType }")
    rc, out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], 4.0)
    kind = parse_drive_type(out) if rc == 0 else "unknown"
    _DRIVE_TYPES[drive.upper()] = (kind, _mono())
    return kind


def parse_drive_type(text: str) -> str:
    """Get-PhysicalDisk's "BusType|MediaType", in words."""
    bus, _, media = (text or "").strip().partition("|")
    bus, media = bus.strip().lower(), media.strip().lower()
    if bus == "nvme":
        return "NVMe"
    if bus in ("sata", "ata", "sas", "raid"):
        return "SATA HDD" if media == "hdd" else ("SATA SSD" if media == "ssd" else "SATA")
    if bus == "usb":
        return "USB"
    if media in ("ssd", "hdd"):
        return media.upper()
    return "unknown"


def _port_taken(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((HOST, int(port))) == 0
    except Exception:
        return False
    finally:
        s.close()


#: No proxy, ever: the key goes to 127.0.0.1 and nowhere else.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http(method: str, url: str, payload: Optional[dict] = None, *,
          key: Optional[str] = None, timeout: float = 5.0) -> dict:
    """One request to colibri on 127.0.0.1. Raises on anything else."""
    if not _is_ours(url):
        raise ValueError("the big model is only ever asked on 127.0.0.1")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with _OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _second_card() -> dict:
    """What jarvis_second_card sees: {capable, uuid, name, lane, why}."""
    try:
        import jarvis_second_card as sc
        det = sc.detect()
        second = det.get("second") or {}
        lane = sc.lane_state() if hasattr(sc, "lane_state") else "unknown"
        return {"capable": bool(det.get("capable")), "uuid": second.get("uuid"),
                "name": second.get("name"), "lane": lane, "why": str(det.get("why") or "")}
    except Exception as exc:
        return {"capable": False, "uuid": None, "name": None, "lane": "unknown",
                "why": f"the second-card check is not available here ({type(exc).__name__})"}


def _key_store():
    """Credential Manager under CRED_TARGET, or None where there is none."""
    if os.name != "nt":
        return None
    import jarvis_token_store
    return jarvis_token_store.WindowsStore(target=CRED_TARGET)


def _publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _tier(action: str) -> str:
    return str(fw.action_tier(action)) if fw is not None else "unknown"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _start_reaper() -> None:
    """The thread that stops an idle engine. Replaced in tests."""
    def loop():
        while True:
            _sleep(30)
            try:
                _ENGINE.check_idle()
            except Exception:
                pass
    threading.Thread(target=loop, name="jarvis-big-model-idle", daemon=True).start()


# --------------------------------------------------------------------------
#   Settings: the toml for how, a small file for the owner's switches
# --------------------------------------------------------------------------

def _section() -> dict:
    if fw is None:
        return {}
    try:
        s = fw.load_framework().get("big_model") or {}
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def _cfg(key: str, default=None):
    return _section().get(key, default)


def _int_cfg(key: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(_cfg(key, default))
    except (TypeError, ValueError):
        return default
    return v if lo <= v <= hi else default


def _config_dir() -> Path:
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def _state_path() -> Path:
    """The switches. Never the owner's toml: no route may write that."""
    return _config_dir() / "big-model.json"


def _log_path() -> Path:
    return _config_dir() / "big-model-engine.log"


def _deep_path() -> Path:
    return _config_dir() / "deep-questions.jsonl"


def _port() -> int:
    p = _int_cfg("port", DEFAULT_PORT, 1024, 65535)
    return DEFAULT_PORT if p in RESERVED_PORTS else p


def _idle_minutes() -> int:
    return _int_cfg("idle_minutes", DEFAULT_IDLE_MINUTES, 1, 24 * 60)


def _ctx() -> int:
    return _int_cfg("ctx", DEFAULT_CTX, 2048, 262144)


def _load_minutes() -> int:
    return _int_cfg("load_minutes", DEFAULT_LOAD_MINUTES, 1, 240)


def _answer_minutes() -> int:
    return _int_cfg("answer_minutes", DEFAULT_ANSWER_MINUTES, 1, 24 * 60)


def _deep_max_tokens() -> int:
    return _int_cfg("deep_max_tokens", DEFAULT_DEEP_MAX_TOKENS, 64, 32768)


def _cuda_setting() -> str:
    v = str(_cfg("cuda", "off") or "off").strip().lower()
    return v if v in ("off", "on") else "off"


def _is_loopback_url(url: str) -> bool:
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return u.scheme == "http" and (u.hostname or "") == HOST


def _is_ours(url: str) -> bool:
    """Only colibri's own address, http://127.0.0.1:<port>, is ever sent
    the key."""
    try:
        u = urllib.parse.urlsplit(url)
        return (u.scheme == "http" and (u.hostname or "") == HOST
                and u.port == _port())
    except ValueError:
        return False


_STATE_LOCK = threading.RLock()


def _read_switches() -> dict:
    """{switch: bool}. A missing or broken file is everything off."""
    out = {s: False for s in SWITCHES}
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return out
    if isinstance(raw, dict):
        for s in SWITCHES:
            out[s] = raw.get(s) is True
    return out


def _write_switch(switch: str, enabled: bool) -> Optional[str]:
    with _STATE_LOCK:
        cur = _read_switches()
        cur[switch] = bool(enabled)
        p = _state_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(dict(cur, set_at=int(_now())), indent=1),
                           encoding="utf-8")
            tmp.replace(p)
        except OSError as exc:
            return f"could not save the switch ({type(exc).__name__})"
    return None


# --------------------------------------------------------------------------
#   Detection
# --------------------------------------------------------------------------

def _gib(n: Optional[int]) -> Optional[float]:
    return None if n is None else round(n / 1024 ** 3, 1)


def _gb(x: Optional[float]) -> str:
    if x is None:
        return "an unknown amount"
    return f"{x:.0f} GB" if abs(x - round(x)) < 0.05 else f"{x:.1f} GB"


def _find_colibri() -> dict:
    """{found, dir, launcher, script, why}. `script` is the `coli` Python
    file coli.cmd runs, when it is beside it."""
    p = str(_cfg("coli_path", "") or "").strip()
    places = []
    if p:
        places.append((Path(p), f"{p} ([big_model] coli_path)"))
    else:
        for name in ("coli.cmd", "coli"):
            w = _which(name)
            if w:
                places.append((Path(w).parent, f"{Path(w).parent} (on PATH)"))
                break
    for d, where in places:
        launcher = next((d / n for n in ("coli.cmd", "coli") if _isfile(d / n)), None)
        if launcher is not None:
            script = d / "coli"
            return {"found": True, "dir": str(d), "launcher": str(launcher),
                    "script": str(script) if _isfile(script) else None,
                    "why": f"colibri found in {where}"}
    if p:
        return {"found": False, "dir": p, "launcher": None, "script": None,
                "why": (f"[big_model] coli_path is {p}, but there is no coli.cmd in that "
                        f"folder. It must be the folder you unpacked colibri's release into")}
    return {"found": False, "dir": None, "launcher": None, "script": None,
            "why": ("colibri was not found. Unpack its Windows release and put that "
                    "folder in [big_model] coli_path (docs/BIG-MODEL.md, step 1)")}


_PY_CACHE: dict = {"at": -1e9, "value": None}
_PY_SECONDS = 300.0


def _find_python() -> dict:
    """{found, cmd, why}: the Python 3 colibri's launcher needs. The same
    order coli.cmd uses: the `py` launcher, then python, then python3. The
    Microsoft Store's stand-in python.exe (in WindowsApps) is not Python -
    colibri's docs/windows.md calls it the most common trap."""
    if _mono() - _PY_CACHE["at"] < _PY_SECONDS and _PY_CACHE["value"] is not None:
        return _PY_CACHE["value"]
    order = [("py", ["-3"]), ("python", []), ("python3", [])] if _ON_WINDOWS \
        else [("python3", []), ("python", [])]
    stub = False
    found = None
    for exe, extra in order:
        w = _which(exe)
        if not w:
            continue
        if "windowsapps" in w.lower() and exe != "py":
            stub = True
            continue
        rc, out = _run([w, *extra, "-c", "import sys; print(sys.version_info[0])"], 5.0)
        if rc == 0 and out.strip() == "3":
            found = {"found": True, "cmd": [w, *extra], "why": f"Python 3 found ({exe})"}
            break
    if found is None:
        why = ("Python 3 was not found. colibri's launcher is a Python script: install "
               "Python 3 from python.org and tick \"Add python.exe to PATH\"")
        if stub:
            why += (" (the python.exe that is there is the Microsoft Store's stand-in, "
                    "not Python)")
        found = {"found": False, "cmd": None, "why": why}
    _PY_CACHE.update(at=_mono(), value=found)
    return found


def _model_entries() -> list:
    raw = _cfg("models", [])
    return [m for m in raw if isinstance(m, dict)] if isinstance(raw, list) else []


def _drive_of(d: str) -> str:
    drive = os.path.splitdrive(d)[0] if d else ""
    if not drive and re.match(r"^[A-Za-z]:", d or ""):
        drive = d[:2]
    return drive.upper() if drive else (d[:1] if d.startswith("/") else "")


def _model_row(m: dict, total_gb: Optional[float], avail_gb: Optional[float]) -> dict:
    mid = str(m.get("id") or "").strip()
    name = str(m.get("name") or mid).strip()[:80] or mid
    d = str(m.get("dir") or "").strip()
    kind = str(m.get("kind") or "").strip().lower()
    row = {"id": mid or None, "name": name or None, "kind": kind or None, "dir": d or None,
           "drive": None, "drive_type": "unknown", "free_gb": None, "need_gb": None,
           "found": False, "usable": False, "can_start_now": False, "why": "", "note": None}
    if not _ID_OK.match(mid):
        row["why"] = ("its id is missing or has characters other than letters, digits "
                      "and . _ : -")
        return row
    if kind not in KIND_NEEDS:
        row["why"] = 'its kind must be "medium" or "giant"'
        return row
    need = KIND_NEEDS[kind]
    start_gb = need["start_gb"]
    if kind == "giant":
        start_gb = max(start_gb, float(_giant_ram_gb(m)))
    try:
        start_gb = max(start_gb, float(m.get("ram_gb") or 0))
    except (TypeError, ValueError):
        pass
    row["need_gb"] = start_gb
    if not d:
        row["why"] = "no dir is set for it"
        return row
    row["drive"] = _drive_of(d) or None
    if not _isdir(d):
        row["why"] = f"the folder {d} does not exist"
        return row
    if not _isfile(Path(d) / "config.json"):
        row["why"] = (f"{d} has no config.json, so it is not a finished model download "
                      f"(colibri reads config.json to pick its engine)")
        return row
    row["found"] = True
    free = _disk_free(d)
    row["free_gb"] = _gib(free)
    row["drive_type"] = _drive_type(row["drive"] or "")
    if kind == "giant":
        where = row["drive"] or "its drive"
        if row["drive_type"] in ("SATA SSD", "SATA HDD", "SATA", "HDD", "USB"):
            row["note"] = (f"{where} is a {row['drive_type']} drive. colibri reads most of a "
                           f"giant model from the disk for every word (its README: \"speed is "
                           f"set by your disk\"), and your own plan says giant models on the "
                           f"SATA drive are too slow: keep it on the NVMe drive.")
        elif row["drive_type"] == "unknown":
            row["note"] = (f"Jarvis could not tell what kind of drive {where} is. Your plan: "
                           f"giant models on the NVMe drive only - on the SATA drive they are "
                           f"too slow.")
    if total_gb is not None and total_gb + 0.5 < need["total_gb"]:
        row["why"] = (f"this PC has {_gb(total_gb)} of memory, and a {kind} model needs "
                      f"{need['says']}")
        return row
    if total_gb is not None and total_gb + 0.5 < start_gb:
        row["why"] = (f"it is set to use {_gb(start_gb)} of memory ([big_model] ram_gb), "
                      f"more than this PC's {_gb(total_gb)}")
        return row
    if free is not None and row["free_gb"] < MIN_FREE_DISK_GB:
        row["why"] = (f"{row['drive'] or 'its drive'} has only {_gb(row['free_gb'])} free; "
                      f"colibri writes a few small files into the model's folder, so keep "
                      f"at least {_gb(MIN_FREE_DISK_GB)} free")
        return row
    row["usable"] = True
    if avail_gb is None:
        row["can_start_now"] = True
        row["why"] = ("Ready to use. Jarvis could not read how much memory is free, so it "
                      "will not check before starting.")
    elif avail_gb + 0.05 < start_gb:
        row["why"] = (f"Usable, but not right now: it needs {_gb(start_gb)} of free memory to "
                      f"start and {_gb(avail_gb)} is free. Close something big, or wait.")
    else:
        row["can_start_now"] = True
        row["why"] = f"Ready to use: {_gb(avail_gb)} of memory free, {_gb(start_gb)} needed."
    return row


def _giant_ram_gb(m: dict) -> int:
    """The `--ram` budget a giant model is started with (GB). Per model
    `ram_gb`, else [big_model] giant_ram_gb, else colibri's minimum (16).
    colibri's own default is ~88% of free memory (docs/SETTINGS.md), which
    would leave the rest of Jarvis almost nothing."""
    for v in (m.get("ram_gb"), _cfg("giant_ram_gb", None)):
        try:
            n = int(v)
            if 16 <= n <= 1024:
                return n
        except (TypeError, ValueError):
            continue
    return 16


_DET: dict = {"at": -1e9, "value": None}
_DET_SECONDS = 30.0


def detect(fresh: bool = False) -> dict:
    """`detected` in status(). Cached about 30 s. Never raises."""
    try:
        if not fresh and _DET["value"] is not None and _mono() - _DET["at"] < _DET_SECONDS:
            return _DET["value"]
        v = _detect()
    except Exception as exc:
        v = {"capable": False, "why": f"the check failed ({type(exc).__name__})",
             "colibri": {"found": False, "dir": None, "why": "not checked"},
             "python": {"found": False, "why": "not checked"},
             "ram": {"total_gb": None, "available_gb": None}, "models": [],
             "_colibri": None, "_python": None}
    _DET.update(at=_mono(), value=v)
    return v


def _detect() -> dict:
    col = _find_colibri()
    py = _find_python() if col["found"] else {"found": False, "cmd": None,
                                              "why": "not checked (colibri first)"}
    total, avail = _memory()
    total_gb, avail_gb = _gib(total), _gib(avail)
    rows = [_model_row(m, total_gb, avail_gb) for m in _model_entries()]
    usable = [r for r in rows if r["usable"]]
    if not col["found"]:
        why = col["why"]
    elif not py["found"]:
        why = py["why"]
    elif not rows:
        why = ("no model is set up yet: add one under [big_model] in jarvis-framework.toml "
               "(docs/BIG-MODEL.md, step 3)")
    elif not usable:
        why = "; ".join(f"{r['name'] or r['id'] or 'a model'}: {r['why']}" for r in rows)
    else:
        why = ("colibri and Python 3 found; usable: "
               + ", ".join(f"{r['name']} ({r['kind']})" for r in usable))
    return {"capable": bool(col["found"] and py["found"] and usable), "why": why,
            "colibri": {k: col[k] for k in ("found", "dir", "why")},
            "python": {"found": py["found"], "why": py["why"]},
            "ram": {"total_gb": total_gb, "available_gb": avail_gb},
            "models": rows, "_colibri": col, "_python": py}


def _public_det(det: dict) -> dict:
    return {k: v for k, v in det.items() if not k.startswith("_")}


def _model_for(job: str, det: dict) -> Optional[dict]:
    """The model row a job uses: [big_model] wiki_model / deep_model by id,
    else the first medium model for the wiki and the first giant one for
    deep questions, else the first model listed."""
    rows = [r for r in det.get("models") or [] if r.get("id")]
    if not rows:
        return None
    key = "wiki_model" if job == "wiki" else "deep_model"
    want = str(_cfg(key, "") or "").strip()
    if want:
        return next((r for r in rows if r["id"] == want), None)
    prefer = "medium" if job == "wiki" else "giant"
    return next((r for r in rows if r["kind"] == prefer), rows[0])


def _model_missing_why(job: str) -> str:
    key = "wiki_model" if job == "wiki" else "deep_model"
    want = str(_cfg(key, "") or "").strip()
    if want:
        return f"[big_model] {key} is {want!r}, and no model has that id"
    return "no model is set up under [big_model]"


# --------------------------------------------------------------------------
#   The key
# --------------------------------------------------------------------------

_KEY_LOCK = threading.Lock()
_KEY: dict = {"value": None, "kept": "not-made-yet"}


def _api_key() -> Optional[str]:
    """The key colibri is started with. Credential Manager when it can be
    used; in memory for this run otherwise. Never logged or returned by any
    route."""
    with _KEY_LOCK:
        if _KEY["value"]:
            return _KEY["value"]
        try:
            store = _key_store()
        except Exception:
            store = None
        if store is not None:
            try:
                v = store.read()
                if not v:
                    v = _make_key()
                    store.write(v)
                    if store.read() != v:
                        raise RuntimeError("read-back did not match")
                _KEY.update(value=v, kept="credential-manager")
                return v
            except Exception:
                pass
        v = _make_key()
        _KEY.update(value=v, kept="this-run-only")
        return v


def _key_where() -> str:
    kept = _KEY["kept"]
    if kept == "credential-manager":
        return f'Windows Credential Manager, "{CRED_TARGET}"'
    if kept == "this-run-only":
        return "in memory, for this run only (Credential Manager could not be used)"
    return (f'made when colibri first starts, then kept in Windows Credential Manager as '
            f'"{CRED_TARGET}"' if _ON_WINDOWS else
            "made when colibri first starts, and kept in memory for that run")


# --------------------------------------------------------------------------
#   The command line and the environment
# --------------------------------------------------------------------------

_ENV_DROP = ("COLI_API_KEY", "COLI_ALLOWED_HOSTS", "COLI_ALLOW_INSECURE_BIND", "COLI_MODEL",
             "COLI_MODEL_ID", "COLI_MODEL_MIRROR", "COLI_GPU", "COLI_GPUS", "COLI_CUDA",
             "DSV4_CUDA", "DSV4_CUDA_DEVICE", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER",
             "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "COLI_HIP_RUNTIME_DIR",
             "CLUSTER_WORKERS", "CLUSTER_COORDINATOR", "COLI_DEBUG", "COLI_KV_SLOTS")


def engine_command(model: dict, *, colibri: dict, python: Optional[list], port: int,
                   ctx: int, gpu: str, host: str = HOST) -> list:
    """The argv for `coli serve`. Raises ValueError for any host but
    127.0.0.1 (rule 2), a bad port, or an argument cmd.exe would re-read."""
    if host != HOST:
        raise ValueError(f"colibri only ever listens on {HOST}, not {host!r}")
    port = int(port)
    if not (1024 <= port <= 65535) or port in RESERVED_PORTS:
        raise ValueError(f"port {port} cannot be used for the big model")
    if not _ID_OK.match(str(model.get("id") or "")):
        raise ValueError("the model id has characters Jarvis does not pass on")
    args = ["serve", "--model", str(model["dir"]), "--host", HOST, "--port", str(port),
            "--model-id", str(model["id"]), "--ctx", str(int(ctx)), "--gpu", gpu]
    if model.get("kind") == "giant":
        args += ["--ram", str(int(model.get("_ram_gb") or 16))]
    script = colibri.get("script")
    if script and python:
        return [*python, script, *args]
    launcher = colibri.get("launcher")
    if not launcher:
        raise ValueError("colibri's launcher was not found")
    if str(launcher).lower().endswith(".cmd"):
        bad = [a for a in [launcher, *args] if _CMD_META & set(str(a))]
        if bad:
            raise ValueError("a folder name has a character (& | < > ^ % ! or a quote) that "
                             "the Windows command line would read as a command; rename it")
    return [launcher, *args]


def engine_env(key: str, *, cuda_uuid: Optional[str] = None,
               base: Optional[dict] = None) -> dict:
    """The environment for `coli serve`. The key goes in COLI_API_KEY and
    nowhere else. No card unless `cuda_uuid` (the SECOND card's id)."""
    if not key:
        raise ValueError("no key")
    env = dict(os.environ if base is None else base)
    for k in _ENV_DROP:
        env.pop(k, None)
    env["COLI_API_KEY"] = key
    if cuda_uuid:
        if not re.fullmatch(r"GPU-[0-9A-Fa-f-]{8,64}", cuda_uuid):
            raise ValueError("a card is only ever chosen by its id (GPU-...)")
        env["CUDA_VISIBLE_DEVICES"] = cuda_uuid
        env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        env["COLI_CUDA"] = "1"
    else:
        # "-1" is not a card, and CUDA shows only the cards listed before
        # the first one that is not: so none.
        env["CUDA_VISIBLE_DEVICES"] = "-1"
        env["COLI_CUDA"] = "0"
        env["DSV4_CUDA"] = "0"
    return env


def _cuda_plan() -> tuple:
    """(card uuid or None, why, usable). cuda "off": (None, ..., True)."""
    if _cuda_setting() != "on":
        return None, ("not used: [big_model] cuda is \"off\", so colibri runs on the "
                      "processor and never touches a graphics card"), True
    sc = _second_card()
    if not sc["capable"] or not sc["uuid"]:
        return None, (f"[big_model] cuda is \"on\", but there is no capable second card "
                      f"({sc['why']}). colibri is never put on the main card: that one is "
                      f"everyday chat"), False
    if sc["lane"] in ("starting", "running") or _card_holder(sc["uuid"]) == "second_card":
        return None, (f"[big_model] cuda is \"on\", but the second card's own features are "
                      f"running on the {sc['name']} right now, so colibri will not share "
                      f"it"), False
    return sc["uuid"], (f"the {sc['name']} (the second card), and only that card"), True


def _compute():
    try:
        import jarvis_compute
        return jarvis_compute
    except Exception:
        return None


def _card_holder(uuid: Optional[str]) -> Optional[str]:
    cp = _compute()
    if cp is None or not uuid or not hasattr(cp, "card_holder"):
        return None
    try:
        return cp.card_holder(uuid)
    except Exception:
        return None


def _claim_card(uuid: str) -> Optional[str]:
    """jarvis_compute.claim_card for colibri: None when the card is ours,
    else who holds it. Without jarvis_compute there is nothing to share."""
    cp = _compute()
    if cp is None or not hasattr(cp, "claim_card"):
        return None
    try:
        return cp.claim_card(uuid, "big_model")
    except Exception:
        return None


def _release_card(uuid: Optional[str]) -> None:
    cp = _compute()
    if cp is None or not uuid or not hasattr(cp, "release_card"):
        return
    try:
        cp.release_card(uuid, "big_model")
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The engine
# --------------------------------------------------------------------------

class _Engine:
    """The one `coli serve` this module started, or none."""

    RETRY_SECONDS = 60.0
    PROBE_EVERY = 2.0

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.state = "off"
        self.why = "not running - it starts only when a background job needs it"
        self.proc = None
        self.model_id: Optional[str] = None
        self.model_name: Optional[str] = None
        self.port = DEFAULT_PORT
        self.since: Optional[float] = None
        self.last_used = 0.0
        self.busy = 0
        self.gen = 0
        self.failed_at = -1e9
        self.card: Optional[str] = None
        self.reaper = False

    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def alive(self) -> bool:
        p = self.proc
        try:
            return p is not None and p.poll() is None
        except Exception:
            return False

    def touch(self) -> None:
        self.last_used = _mono()

    def begin(self) -> None:
        with self.lock:
            self.busy += 1
            self.touch()

    def end(self) -> None:
        with self.lock:
            self.busy = max(0, self.busy - 1)
            self.touch()

    def _fail(self, why: str) -> None:
        self.state, self.why, self.failed_at = "failed", why, _mono()

    def ensure(self, row: dict, det: dict) -> None:
        """Start colibri with `row`'s model if it is not running it."""
        with self.lock:
            if self.model_id == row["id"] and self.state in ("loading", "ready") and self.alive():
                return
            if self.state == "ready" and self.model_id == row["id"] and not self.alive():
                code = self._exit_code()
                self.proc = None
                self._drop_card()
                self._fail(f"colibri stopped by itself (exit code {code}). Its log: "
                           f"{_log_path()}")
                return
            if self.state in ("loading", "ready") and self.alive() and self.busy:
                return          # busy with the other model's job; it waits
            if self.state == "failed" and self.model_id == row["id"] \
                    and _mono() - self.failed_at < self.RETRY_SECONDS:
                return
            if self.proc is not None:
                self._stop_proc()
            self._start(row, det)

    def _exit_code(self):
        try:
            return self.proc.poll()
        except Exception:
            return "unknown"

    def _start(self, row: dict, det: dict) -> None:
        self.model_id, self.model_name, self.port = row["id"], row["name"], _port()
        self.card = None
        col, py = det.get("_colibri") or {}, det.get("_python") or {}
        if not col.get("found"):
            return self._fail(col.get("why") or "colibri was not found")
        if not py.get("found"):
            return self._fail(py.get("why") or "Python 3 was not found")
        _, avail = _memory()
        avail_gb = _gib(avail)
        if avail_gb is not None and avail_gb + 0.05 < float(row["need_gb"] or 0):
            return self._fail(f"not started: {row['name']} needs {_gb(row['need_gb'])} of free "
                              f"memory and {_gb(avail_gb)} is free right now. Close something "
                              f"big (a game, a browser with many tabs) and it tries again")
        if _port_taken(self.port):
            return self._fail(f"another program is already using {HOST}:{self.port}; Jarvis "
                              f"neither uses it nor stops it. Set another port under "
                              f"[big_model] in jarvis-framework.toml")
        uuid, cuda_why, ok = _cuda_plan()
        if not ok:
            return self._fail(cuda_why)
        key = _api_key()
        try:
            m = dict(row)
            m["_ram_gb"] = _giant_ram_gb(next((e for e in _model_entries()
                                               if str(e.get("id")) == row["id"]), {}))
            argv = engine_command(m, colibri=col, python=py.get("cmd"), port=self.port,
                                  ctx=_ctx(), gpu="0" if uuid else "none")
            env = engine_env(key, cuda_uuid=uuid)
        except ValueError as exc:
            return self._fail(str(exc))
        if uuid:
            # Taken BEFORE the process starts. jarvis_second_card takes the
            # same claim before its own start, so only one of the two can
            # start on the card, whatever the timing.
            holder = _claim_card(uuid)
            if holder is not None:
                return self._fail(f"[big_model] cuda is \"on\", but the second card's own "
                                  f"features are starting on it right now, so colibri will "
                                  f"not share it")
        kwargs: dict = {"env": env, "stdin": subprocess.DEVNULL, "cwd": col.get("dir") or None}
        log = None
        try:
            _log_path().parent.mkdir(parents=True, exist_ok=True)
            log = open(_log_path(), "wb")
            kwargs["stdout"] = log
            kwargs["stderr"] = subprocess.STDOUT
        except OSError:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        try:
            self.proc = _popen(argv, **kwargs)
        except Exception as exc:
            self.proc = None
            _release_card(uuid)
            return self._fail(f"colibri could not be started ({type(exc).__name__})")
        finally:
            if log is not None:
                try:
                    log.close()
                except Exception:
                    pass
        self.card = uuid
        self.gen += 1
        gen = self.gen
        self.state, self.since = "loading", _now()
        self.touch()
        self.why = (f"loading {row['name']} from {row['drive'] or 'its drive'} - this can "
                    f"take several minutes. colibri listens on {HOST}:{self.port} (this PC "
                    f"only)")
        if not self.reaper:
            self.reaper = True
            try:
                _start_reaper()
            except Exception:
                pass
        _spawn(lambda: self._wait_ready(gen))

    def _probe(self) -> bool:
        """Is colibri answering, with our key, for our model?"""
        try:
            out = _http("GET", f"{self.url()}/v1/models", key=_api_key(), timeout=3.0)
        except Exception:
            return False
        ids = [m.get("id") for m in (out.get("data") or []) if isinstance(m, dict)]
        return self.model_id in ids

    def _wait_ready(self, gen: int) -> None:
        deadline = _mono() + _load_minutes() * 60
        while _mono() < deadline:
            with self.lock:
                if gen != self.gen or self.state != "loading":
                    return
                if not self.alive():
                    code = self._exit_code()
                    self.proc = None
                    self._drop_card()
                    return self._fail(f"colibri stopped while loading (exit code {code}). "
                                      f"Its log: {_log_path()}")
            if self._probe():
                with self.lock:
                    if gen == self.gen and self.state == "loading":
                        self.state, self.since = "ready", _now()
                        self.touch()
                        self.why = (f"running {self.model_name} on {HOST}:{self.port} (this PC "
                                    f"only); it stops after {_idle_minutes()} minutes with "
                                    f"nothing to do")
                return
            _sleep(self.PROBE_EVERY)
        with self.lock:
            if gen == self.gen and self.state == "loading":
                self._stop_proc()
                self._fail(f"colibri did not finish loading within {_load_minutes()} minutes "
                           f"([big_model] load_minutes). Its log: {_log_path()}")

    def _drop_card(self) -> None:
        """Gives back the card's claim (jarvis_compute) once no process of
        ours is on it."""
        card, self.card = self.card, None
        _release_card(card)

    def _stop_proc(self) -> None:
        p, self.proc = self.proc, None
        self.gen += 1
        self._drop_card()
        if p is None:
            return
        try:
            if p.poll() is not None:
                return
        except Exception:
            return
        _kill_tree(p)

    def stop(self, why: str) -> None:
        with self.lock:
            self._stop_proc()
            self.state, self.why = "off", why
            self.since = None

    def check_idle(self, now: Optional[float] = None) -> bool:
        """Stops a ready engine nobody has used for idle_minutes. True if
        it stopped it."""
        now = _mono() if now is None else now
        with self.lock:
            if self.state != "ready" or self.busy:
                return False
            if now - self.last_used < _idle_minutes() * 60:
                return False
            self.stop(f"stopped after {_idle_minutes()} minutes with nothing to do; it starts "
                      f"again when a job needs it")
            return True


def _kill_tree(p) -> None:
    """Stops a process THIS module started, and what it started (the
    launcher starts Python, which starts the engine). Replaced in tests."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        else:
            import signal
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                p.terminate()
        p.wait(timeout=10)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


_ENGINE = _Engine()


def _reconcile(sw: dict) -> None:
    """Stop colibri when nothing may use it; stop it when idle."""
    try:
        if not sw["master"] or not any(sw[j] for j in JOBS):
            if _ENGINE.proc is not None or _ENGINE.state in ("loading", "ready", "failed"):
                _ENGINE.stop("the big-model switch is off" if not sw["master"]
                             else "no job that uses the big model is switched on")
            elif _ENGINE.state == "off":
                _ENGINE.why = "not running - it starts only when a background job needs it"
        else:
            _ENGINE.check_idle()
            if _ENGINE.state == "ready" and not _ENGINE.alive():
                code = _ENGINE._exit_code()
                _ENGINE.proc = None
                _ENGINE._drop_card()
                _ENGINE._fail(f"colibri stopped by itself (exit code {code}). Its log: "
                              f"{_log_path()}")
    except Exception as exc:
        _ENGINE.state, _ENGINE.why = "failed", f"unexpected error ({type(exc).__name__})"


def shutdown() -> None:
    """Stops colibri if this module started it. At process exit."""
    try:
        _ENGINE.stop("Jarvis is shutting down")
    except Exception:
        pass


atexit.register(shutdown)


def engine_card() -> Optional[dict]:
    """The graphics card colibri is on right now, or None: {"uuid",
    "state", "idle_minutes"}. There is only ever one with [big_model] cuda =
    "on", and it is only ever the SECOND card. Reads only; starts and stops
    nothing. jarvis_second_card asks this before it starts its own Ollama on
    that card (it does not while colibri is loading or running there).
    Never raises."""
    try:
        state, card = _ENGINE.state, _ENGINE.card
        if card and state in ("loading", "ready"):
            return {"uuid": card, "state": state, "idle_minutes": _idle_minutes()}
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
#   lane_for - the call the wiki and deep questions make
# --------------------------------------------------------------------------

def selected(job: str) -> bool:
    """Has the owner chosen the big model for this job (master and the
    job's switch on)? Reads one small file; starts nothing."""
    try:
        sw = _read_switches()
        return bool(job in JOBS and sw["master"] and sw[job])
    except Exception:
        return False


def lane_for(job: str) -> Optional[Lane]:
    """The big model's lane for `job`, or None - "not now". Starts colibri
    if the job's switch is on and it is not running; None until it has
    loaded. Only "wiki" and "deep_questions" may ask. Never raises."""
    try:
        if job not in JOBS:
            return None
        sw = _read_switches()
        if not (sw["master"] and sw[job]):
            return None
        det = detect()
        row = _model_for(job, det)
        if not det.get("capable") or row is None or not row["usable"]:
            return None
        _ENGINE.check_idle()
        _ENGINE.ensure(row, det)
        if _ENGINE.state == "ready" and _ENGINE.model_id == row["id"] and _ENGINE.alive():
            _ENGINE.touch()
            url = _ENGINE.url()
            if not _is_ours(url):
                return None
            return Lane(url=url, model=row["id"], num_ctx=_ctx(),
                        why=f"{JOB_NAMES[job]}: {row['name']} with colibri, on this PC")
        return None
    except Exception:
        return None


def job_state(job: str) -> tuple:
    """(state, why) for a caller holding a job: "ready", "loading" (wait),
    "busy" (the engine is on another model's job; wait), or "off",
    "unavailable", "not_now" (not enough free memory right now), "failed"
    (do not wait; show why). Starts nothing."""
    try:
        if job not in JOBS:
            return "unavailable", "only the wiki builder and deep questions use the big model"
        sw = _read_switches()
        if not sw["master"]:
            return "off", "the big-model switch is off"
        if not sw[job]:
            return "off", f"\"{JOB_NAMES[job]}\" is not switched on for the big model"
        det = detect()
        row = _model_for(job, det)
        if row is None:
            return "unavailable", _model_missing_why(job)
        if not det.get("capable") or not row["usable"]:
            return "unavailable", (row["why"] if not row["usable"] else det["why"])
        with _ENGINE.lock:
            st, why, mid = _ENGINE.state, _ENGINE.why, _ENGINE.model_id
            alive = _ENGINE.alive()
        if mid == row["id"] and st == "ready" and alive:
            return "ready", why
        if mid == row["id"] and st == "loading":
            return "loading", why
        if st == "failed" and mid == row["id"]:
            return "failed", why
        if st in ("loading", "ready") and alive and _ENGINE.busy:
            return "busy", (f"the big model is busy with another job ({_ENGINE.model_name}); "
                            f"this one waits for it")
        if not row["can_start_now"]:
            return "not_now", row["why"]
        return "loading", f"starting {row['name']} with colibri"
    except Exception as exc:
        return "failed", f"unexpected error ({type(exc).__name__})"


def peek(job: str) -> dict:
    """For a status line: {selected, available, why, model, num_ctx}.
    Reads only; starts nothing."""
    st, why = job_state(job)
    det = detect()
    row = _model_for(job, det) if det else None
    return {"selected": selected(job), "state": st,
            "available": st in ("ready", "loading", "busy"),
            "why": why, "model": row["id"] if row else None,
            "name": row["name"] if row else None, "num_ctx": _ctx()}


# --------------------------------------------------------------------------
#   Asking it
# --------------------------------------------------------------------------

def chat(lane: Lane, body: dict, *, timeout: float) -> dict:
    """One /v1/chat/completions call to colibri, non-streamed. The key is
    added here, at the socket, and only for colibri's own 127.0.0.1 URL."""
    if not isinstance(lane, Lane) or not _is_ours(lane.url):
        raise ValueError("the big model is only ever asked on 127.0.0.1")
    key = _api_key()
    _ENGINE.begin()
    try:
        return _http("POST", f"{lane.url}/v1/chat/completions", body, key=key,
                     timeout=timeout)
    finally:
        _ENGINE.end()


_FENCE = re.compile(r"\A```[A-Za-z]*\s*\n(.*)\n```\s*\Z", re.S)
_MEASURED: dict = {}          # job -> {words_per_s, tokens_per_s, tokens, seconds, model, at}


def _answer_of(out: dict) -> tuple:
    """(text, finish_reason, usage) of an OpenAI-shaped answer."""
    if not isinstance(out, dict):
        raise ValueError("not an answer")
    choices = out.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("no choices")
    msg = choices[0].get("message") or {}
    text = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(text, str):
        raise ValueError("no text")
    usage = out.get("usage") if isinstance(out.get("usage"), dict) else {}
    return text, str(choices[0].get("finish_reason") or ""), usage


def _measure(job: str, model: str, tokens, seconds: float, words: int) -> dict:
    m = {"model": model, "seconds": round(seconds, 1), "at": int(_now()),
         "tokens": tokens if isinstance(tokens, int) and tokens >= 0 else None,
         "tokens_per_s": (round(tokens / seconds, 2) if isinstance(tokens, int)
                          and tokens > 0 and seconds > 0 else None),
         "words": words,
         "words_per_s": round(words / seconds, 2) if seconds > 0 else None}
    _MEASURED[job] = m
    return m


def wiki_call(lane: Lane, body: dict) -> dict:
    """jarvis_wiki's model call, for the big model's lane.

    jarvis_wiki builds Ollama /api/chat bodies with a JSON-schema `format`.
    colibri speaks OpenAI's API and does not constrain output to a schema
    (see the module docstring), so the schema goes into the instructions,
    and the answer comes back in the Ollama shape jarvis_wiki already
    validates strictly: {"message": {"content"}, "done_reason",
    "prompt_eval_count"}."""
    messages = [dict(m) for m in body.get("messages") or []]
    schema = body.get("format")
    if isinstance(schema, dict) and messages and messages[0].get("role") == "system":
        messages[0]["content"] = (
            str(messages[0].get("content") or "")
            + "\n\nAnswer with ONE JSON object and nothing else: no code fences, no words "
              "before or after it. It must match this JSON schema exactly:\n"
            + json.dumps(schema, ensure_ascii=False))
    opts = body.get("options") or {}
    req = {"model": lane.model, "messages": messages, "stream": False, "temperature": 0,
           "max_tokens": int(opts.get("num_predict") or 2048)}
    t0 = _mono()
    out = chat(lane, req, timeout=_answer_minutes() * 60)
    secs = _mono() - t0
    text, finish, usage = _answer_of(out)
    m = _FENCE.match(text.strip())
    if m:
        text = m.group(1)
    _measure("wiki", lane.model, usage.get("completion_tokens"), secs, len(text.split()))
    return {"model": lane.model, "done": True,
            "done_reason": "length" if finish == "length" else "stop",
            "prompt_eval_count": usage.get("prompt_tokens"),
            "eval_count": usage.get("completion_tokens"),
            "message": {"role": "assistant", "content": text}}


# --------------------------------------------------------------------------
#   status()
# --------------------------------------------------------------------------

def _switch_row(job: str, sw: dict, det: dict, pending: list) -> dict:
    enabled = bool(sw[job])
    row = _model_for(job, det)
    st, why = job_state(job)

    def full(s: str) -> str:
        # A reason that already ends a sentence keeps its own stop; "wait.."
        # was the result of adding one regardless.
        s = str(s).rstrip()
        return s if s.endswith((".", "!", "?")) else s + "."

    if not det.get("capable"):
        if enabled:
            why = (f"On, but it cannot run: {full(det['why'])} Your choice is kept; it works again "
                   f"once that is fixed.")
        else:
            why = f"Needs the big model set up: {full(det['why'])}"
    elif row is None:
        why = f"Cannot run: {full(_model_missing_why(job))}"
    elif not enabled:
        why = "Off."
        if job in pending:
            why = "Off. A card to turn it on is waiting for your answer."
        elif not sw["master"]:
            why = "Off. Turn on the big model itself first."
    elif not sw["master"]:
        why = "On, but the big-model switch is off."
    elif not row["usable"]:
        why = f"On, but {row['name']} cannot be used: {full(row['why'])}"
    elif st == "ready":
        why = f"Working: {row['name']} is loaded."
    elif st == "loading":
        why = (f"On. {row['name']} is loading." if _ENGINE.state == "loading"
               and _ENGINE.model_id == row["id"] else
               f"On. {row['name']} starts when this job next has work, and stops "
               f"{_idle_minutes()} minutes after.")
    else:
        why = f"On. {full(why[:1].upper() + why[1:])}" if why else "On."
    return {"id": job, "name": JOB_NAMES[job], "what": JOB_WHAT[job], "enabled": enabled,
            "available": bool(det.get("capable") and sw["master"] and enabled and row
                              and row["usable"] and st in ("ready", "loading", "busy")),
            "model": row["id"] if row else None, "model_name": row["name"] if row else None,
            "why": why}


def status() -> dict:
    """GET /api/big-model. Starts nothing (it may stop an idle or
    switched-off colibri). No key in it, ever. Never raises."""
    sw = _read_switches()
    det = detect()
    _reconcile(sw)
    with _PENDING_LOCK:
        pending = [s for s in SWITCHES if s in _PENDING and not _PENDING[s].get("withdrawn")]
    with _ENGINE.lock:
        eng = {"state": _ENGINE.state, "why": _ENGINE.why, "model": _ENGINE.model_id
               if _ENGINE.state != "off" else None,
               "listens_on": f"{HOST}:{_port()}", "idle_minutes": _idle_minutes(),
               "since": _ENGINE.since, "busy": _ENGINE.busy > 0}
    card, cuda_why, cuda_ok = _cuda_plan()
    return {
        "detected": _public_det(det),
        "enabled": sw["master"],
        "active": bool(sw["master"] and det.get("capable")),
        "pending": pending,
        "engine": eng,
        "cuda": {"setting": _cuda_setting(), "usable": cuda_ok, "why": cuda_why},
        "key_kept": _KEY["kept"],
        "key_where": _key_where(),
        "switches": [_switch_row(j, sw, det, pending) for j in JOBS],
        "measured": {j: _last_measured(j) for j in JOBS},
        "verified": False,
        "unverified": UNVERIFIED,
    }


def _last_measured(job: str) -> Optional[dict]:
    if job in _MEASURED:
        return dict(_MEASURED[job])
    if job == "deep_questions":
        for r in reversed(_load_deep()):
            if r.get("state") == "done" and r.get("seconds") is not None:
                return {k: r.get(k) for k in ("model", "seconds", "tokens", "tokens_per_s",
                                              "words", "words_per_s")} | {"at": r.get("finished")}
    return None


# --------------------------------------------------------------------------
#   Changing a switch
# --------------------------------------------------------------------------

_PENDING_LOCK = threading.Lock()
_PENDING: dict = {}
_LAST: dict = {}


def describe_on(switch: str, det: dict) -> str:
    """The approval card. Every word from here; what refusing costs is on it."""
    ram = det.get("ram") or {}
    lines = []
    if switch == "master":
        rows = [r for r in det.get("models") or [] if r["usable"]]
        lines.append("Let Jarvis use a big model (slow) for background jobs?")
        lines.append("")
        lines.append("Which models: " + "; ".join(
            f"{r['name']} ({r['kind']}), in {r['dir']}" for r in rows) + ".")
    else:
        r = _model_for(switch, det)
        lines.append(f"Use the big model for \"{JOB_NAMES[switch]}\"?")
        lines.append("")
        lines.append(f"What it does: {JOB_WHAT[switch]}")
        lines.append("")
        rows = [r]
        lines.append(f"Which model: {r['name']} ({r['kind']}), in {r['dir']}.")
    for r in rows:
        dt = r["drive_type"] if r["drive_type"] != "unknown" else "drive type unknown"
        lines.append(f"{r['name']}: needs about {_gb(r['need_gb'])} of memory while it runs "
                     f"(this PC has {_gb(ram.get('total_gb'))}; {_gb(ram.get('available_gb'))} "
                     f"is free now). Disk: {_gb(r['free_gb'])} free on "
                     f"{r['drive'] or 'its drive'} ({dt}).")
        if r.get("note"):
            lines.append(r["note"])
    _, cuda_why, _ = _cuda_plan()
    lines += [
        "",
        f"What runs: colibri, started only when a background job needs it, and stopped "
        f"{_idle_minutes()} minutes after the last one. It listens on {HOST}:{_port()} - this "
        f"PC only, not your network or the internet - and answers only Jarvis, which holds "
        f"its key ({_key_where()}).",
        f"Graphics card: {cuda_why}.",
        "It is used only for the wiki builder and deep questions - never for chat, voice or "
        "approvals. Nothing leaves this PC.",
        "",
        f"Speed: {UNVERIFIED} Expect minutes, not seconds, per answer.",
        "",
        "If you did not just ask for this, say no.",
        "",
        "If you say no: nothing changes. The wiki builder keeps using the second graphics "
        "card (if that is on), and deep questions stay off.",
    ]
    return "\n".join(lines)


def _finish(switch: str, pid: str, outcome: str, reason: str = "", request_id=None) -> None:
    with _PENDING_LOCK:
        if switch in _PENDING and _PENDING[switch]["id"] == pid:
            del _PENDING[switch]
        _LAST[switch] = {"outcome": outcome, "reason": reason[:200]}
    _audit("big_model.decided", {"switch": switch, "outcome": outcome,
                                 **({"request_id": request_id} if request_id else {})})


def _can_turn_on(switch: str, det: dict) -> Optional[str]:
    """Why `switch` cannot be turned on, or None."""
    if not det.get("capable"):
        return det.get("why") or "the big model is not set up"
    if switch == "master":
        return None
    row = _model_for(switch, det)
    if row is None:
        return _model_missing_why(switch)
    if not row["usable"]:
        return f"{row['name']}: {row['why']}"
    return None


def _decide(switch: str, pid: str, gate: Callable) -> None:
    det = detect(fresh=True)
    why = _can_turn_on(switch, det)
    if why:
        return _finish(switch, pid, "refused", why)
    text = describe_on(switch, det)
    row = _model_for(switch, det) if switch != "master" else None
    detail = {"text": text, "what": f"turn on the big model: {switch}", "switch": switch,
              "model": row["id"] if row else None,
              "memory_gb": row["need_gb"] if row else None,
              "listens_on": f"{HOST}:{_port()}", "leaves_this_pc": False}
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        return _finish(switch, pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return _finish(switch, pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes",
                       rid)
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(switch, pid, outcome, "", rid)
        return _finish(switch, pid, "refused", str(getattr(v, "reason", "refused")), rid)
    with _PENDING_LOCK:
        withdrawn = bool(_PENDING.get(switch, {}).get("id") == pid
                         and _PENDING[switch].get("withdrawn"))
    if withdrawn:
        return _finish(switch, pid, "withdrawn", "you turned it off while the card was waiting",
                       rid)
    why = _can_turn_on(switch, detect(fresh=True))
    if why:
        return _finish(switch, pid, "refused", f"no longer possible: {why}", rid)
    err = _write_switch(switch, True)
    if err:
        return _finish(switch, pid, "failed", err, rid)
    _finish(switch, pid, "enabled", "", rid)


def request_change(switch: str, enabled, *, gate: Optional[Callable] = None,
                   tier_of: Optional[Callable[[str], str]] = None,
                   spawn: Optional[Callable] = None) -> tuple:
    """POST /api/big-model. (http code, body). OFF at once, no card. ON:
    one approval card, and this returns straight away - `pending: true`
    means a card is up, NOT that it is on."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if switch not in SWITCHES:
        return 400, {"error": f"there is no big-model switch called {str(switch)[:40]!r}"}
    if not isinstance(enabled, bool):
        return 400, {"error": "\"enabled\" must be true or false"}
    label = "The big model" if switch == "master" else f"\"{JOB_NAMES[switch]}\""
    lc = "the big model" if switch == "master" else label
    if not enabled:
        with _PENDING_LOCK:
            if switch in _PENDING:
                _PENDING[switch]["withdrawn"] = True
        err = _write_switch(switch, False)
        if err:
            return 500, {"error": err}
        _audit("big_model.off", {"switch": switch})
        _reconcile(_read_switches())
        return 200, {"ok": True, "enabled": False, "pending": False,
                     "message": f"{label} is off."}
    sw = _read_switches()
    if sw[switch]:
        return 200, {"ok": True, "enabled": True, "pending": False,
                     "message": f"{label} is already on."}
    with _PENDING_LOCK:
        p = _PENDING.get(switch)
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": f"a card to turn on {lc} is already waiting - approve or "
                                  f"deny that one"}
    if switch != "master" and not sw["master"]:
        return 400, {"error": "Turn on the big model itself first (the main switch), then "
                              "this one."}
    why = _can_turn_on(switch, detect(fresh=True))
    if why:
        return 503, {"error": f"{label} cannot be turned on: {why}."}
    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 503, {"error": (f"{ACTION} is tier {tier!r} in jarvis-framework.toml; turning "
                               f"this on needs a person to say yes, so it must be 'ask'")}
    pid = secrets.token_hex(8)
    with _PENDING_LOCK:
        p = _PENDING.get(switch)
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": f"a card to turn on {lc} is already waiting"}
        _PENDING[switch] = {"id": pid, "since": _now(), "withdrawn": False}
    _audit("big_model.asked", {"switch": switch})

    def work() -> None:
        try:
            _decide(switch, pid, gate)
        except Exception:
            _finish(switch, pid, "failed", "unexpected error")
    try:
        spawn(work)
    except Exception:
        _finish(switch, pid, "failed", "could not start")
        return 503, {"error": "could not raise the approval card"}
    return 200, {"ok": True, "enabled": False, "pending": True,
                 "message": ("Approve the card on your PC or phone to turn it on. Nothing "
                             "changes until you do.")}


def handle_post(body) -> tuple:
    """POST /api/big-model: {"switch": "master"|"wiki"|"deep_questions",
    "enabled": true|false}."""
    if not isinstance(body, dict):
        return 400, {"error": "send {\"switch\": \"...\", \"enabled\": true or false}"}
    return request_change(str(body.get("switch") or ""), body.get("enabled"))


# --------------------------------------------------------------------------
#   Deep questions
# --------------------------------------------------------------------------

MAX_QUESTION_CHARS = 4000
MAX_ANSWER_CHARS = 60000
MAX_QUEUED = 3
KEEP_JOBS = 100
MAX_FILE_BYTES = 2 * 1024 * 1024
LIST_JOBS = 20

DEEP_SYSTEM = ("You are answering one question from the owner of this PC, carefully and in "
               "depth. You have no tools, no internet and no memory of earlier "
               "conversations: answer from what you know. Say plainly where you are not "
               "sure. Answer in plain text.")

_DEEP_LOCK = threading.Lock()
_DEEP: "OrderedDict[str, dict]" = OrderedDict()     # jobs of this run, oldest first
_DEEP_WORKER = {"running": False}
_FILE_LOCK = threading.Lock()


def _public_job(j: dict) -> dict:
    out = {k: j.get(k) for k in ("id", "question", "state", "queued", "started", "finished",
                                 "seconds", "tokens", "words_per_s", "tokens_per_s", "model",
                                 "why")}
    if j.get("state") == "done":
        out["answer"] = j.get("answer")
    return out


def _load_deep() -> list:
    """The kept jobs, oldest first. A broken line is skipped."""
    out = []
    try:
        with open(_deep_path(), encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("id"), str):
                    out.append(r)
    except OSError:
        pass
    return out


def _keep(job: dict) -> None:
    """Append one finished job; trim the file to KEEP_JOBS and
    MAX_FILE_BYTES, oldest first, by rewriting it whole."""
    row = {"v": 1, **{k: job.get(k) for k in ("id", "question", "state", "answer", "queued",
                                              "started", "finished", "seconds", "tokens",
                                              "prompt_tokens", "words", "words_per_s",
                                              "tokens_per_s", "model", "why")}}
    with _FILE_LOCK:
        p = _deep_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if p.stat().st_size <= MAX_FILE_BYTES and len(_load_deep()) <= KEEP_JOBS:
                return
            rows = _load_deep()[-KEEP_JOBS:]
            lines = [json.dumps(r, ensure_ascii=False) + "\n" for r in rows]
            while lines and sum(len(l.encode("utf-8")) for l in lines) > MAX_FILE_BYTES:
                lines.pop(0)
            tmp = p.with_suffix(".jsonl.tmp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(lines)
            tmp.replace(p)
        except OSError:
            job["why"] = (job.get("why") or "") + " (It could not be saved to disk, so it is " \
                                                  "gone after a restart.)"


def deep_available() -> tuple:
    """(available, why) for deep questions. Starts nothing."""
    st, why = job_state("deep_questions")
    if st in ("off", "unavailable", "not_now"):
        return False, why[:1].upper() + why[1:].rstrip(".") + "."
    if st == "failed":
        return True, ("Available, but the last start failed: " + why + ". A new question "
                      "tries again.")
    return True, ("Ready. Questions are answered one at a time, in the background, by "
                  f"{peek('deep_questions')['name']}.")


def deep_status() -> dict:
    """GET /api/deep. Recent jobs, newest first; the answer only when done.
    Reads only; starts nothing."""
    avail, why = deep_available()
    with _DEEP_LOCK:
        live = [dict(j) for j in _DEEP.values()]
    kept = _load_deep()
    ids = {j["id"] for j in live}
    jobs = live + [r for r in kept if r["id"] not in ids]
    jobs.sort(key=lambda j: (j.get("queued") or 0, j.get("id")), reverse=True)
    return {"available": avail, "why": why, "enabled": selected("deep_questions"),
            "model": peek("deep_questions")["model"],
            "jobs": [_public_job(j) for j in jobs[:LIST_JOBS]],
            "limits": {"question_chars": MAX_QUESTION_CHARS, "queue": MAX_QUEUED,
                       "answer_tokens": _deep_max_tokens()}}


def _set_job(jid: str, **fields) -> None:
    with _DEEP_LOCK:
        if jid in _DEEP:
            _DEEP[jid].update(fields)


def ask(question, *, spawn: Optional[Callable] = None) -> tuple:
    """POST /api/deep/ask {"question": "..."}. (http code, body).

    Queues ONE background job and returns at once (202). There is no
    approval card per question, on purpose: the owner approved the
    "deep_questions" switch with a card, a question acts on nothing (no
    tools, no memory writes, no web), and nothing leaves this PC - the
    answer is kept in <config dir>/deep-questions.jsonl, on this PC."""
    if not isinstance(question, str) or not question.strip():
        return 400, {"ok": False, "state": "refused",
                     "error": "say what to ask: {\"question\": \"...\"}"}
    q = question.strip().replace("\r\n", "\n")
    if len(q) > MAX_QUESTION_CHARS:
        return 400, {"ok": False, "state": "refused",
                     "error": f"the question is {len(q):,} characters; at most "
                              f"{MAX_QUESTION_CHARS:,}"}
    avail, why = deep_available()
    if not avail:
        return 503, {"ok": False, "state": "refused", "error": why}
    with _DEEP_LOCK:
        waiting = [j for j in _DEEP.values() if j["state"] in ("queued", "loading", "thinking")]
        if len(waiting) >= MAX_QUEUED:
            return 409, {"ok": False, "state": "refused",
                         "error": f"{len(waiting)} questions are already waiting; ask again when "
                                  f"one has finished"}
        jid = _new_id()
        _DEEP[jid] = {"id": jid, "question": q, "state": "queued", "queued": int(_now()),
                      "started": None, "finished": None, "seconds": None, "tokens": None,
                      "words_per_s": None, "tokens_per_s": None, "model": None,
                      "why": ("Waiting its turn." if waiting else "Queued.")}
        while len(_DEEP) > LIST_JOBS * 2:
            old = next(iter(_DEEP))
            if _DEEP[old]["state"] in ("queued", "loading", "thinking"):
                break
            _DEEP.pop(old)
        start = not _DEEP_WORKER["running"]
        if start:
            _DEEP_WORKER["running"] = True
    _audit("deep.asked", {"job": jid})
    if start:
        try:
            (spawn or _spawn)(_deep_worker)
        except Exception:
            with _DEEP_LOCK:
                _DEEP_WORKER["running"] = False
            _set_job(jid, state="failed", why="the background job could not be started")
            return 503, {"ok": False, "state": "refused",
                         "error": "the background job could not be started"}
    return 202, {"ok": True, "id": jid, "pending": True, "state": "queued",
                 "message": ("Queued. The big model answers in the background - expect "
                             "minutes. The answer appears in the list when it is done.")}


def _deep_worker() -> None:
    """Runs queued questions one at a time until none are left."""
    while True:
        with _DEEP_LOCK:
            nxt = next((j["id"] for j in _DEEP.values() if j["state"] == "queued"), None)
            if nxt is None:
                _DEEP_WORKER["running"] = False
                return
        try:
            _run_deep(nxt)
        except Exception as exc:
            _fail_deep(nxt, f"an unexpected {type(exc).__name__}")


def _fail_deep(jid: str, why: str) -> None:
    _set_job(jid, state="failed", finished=int(_now()), why=f"Not answered: {why}.")
    with _DEEP_LOCK:
        job = dict(_DEEP.get(jid) or {})
    if job:
        _keep(job)
    _publish("deep", {"id": jid, "state": "failed"})
    _audit("deep.failed", {"job": jid})


def _run_deep(jid: str) -> None:
    _set_job(jid, state="loading", why="Starting the big model (this can take minutes).")
    deadline = _mono() + _load_minutes() * 60 + 60
    while True:
        lane = lane_for("deep_questions")
        if lane is not None:
            break
        st, why = job_state("deep_questions")
        if st not in ("loading", "busy"):
            return _fail_deep(jid, why)
        if _mono() > deadline:
            return _fail_deep(jid, f"the big model did not finish loading within "
                                   f"{_load_minutes()} minutes")
        _set_job(jid, why=why[:1].upper() + why[1:] + ".")
        _sleep(3)
    with _DEEP_LOCK:
        q = _DEEP[jid]["question"]
    name = peek("deep_questions").get("name") or lane.model
    _set_job(jid, state="thinking", started=int(_now()), model=lane.model,
             why=(f"{name} is thinking. On this PC that can take many minutes; nothing "
                  f"else waits for it."))
    body = {"model": lane.model, "stream": False, "max_tokens": _deep_max_tokens(),
            "messages": [{"role": "system", "content": DEEP_SYSTEM},
                         {"role": "user", "content": q}]}
    t0 = _mono()
    try:
        out = chat(lane, body, timeout=_answer_minutes() * 60)
        text, finish, usage = _answer_of(out)
    except urllib.error.HTTPError as exc:
        return _fail_deep(jid, f"the big model answered HTTP {exc.code}")
    except (socket.timeout, TimeoutError):
        return _fail_deep(jid, f"no answer within {_answer_minutes()} minutes "
                               f"([big_model] answer_minutes)")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return _fail_deep(jid, f"no answer within {_answer_minutes()} minutes "
                                   f"([big_model] answer_minutes)")
        return _fail_deep(jid, "the big model could not be reached (it may have been "
                               "stopped)")
    except ValueError:
        return _fail_deep(jid, "the big model's answer was not in the shape expected")
    except Exception as exc:
        return _fail_deep(jid, f"the big model could not be asked ({type(exc).__name__})")
    secs = max(_mono() - t0, 0.001)
    text = re.sub(r"(?s)<think>.*?</think>", "", text).strip()
    if not text:
        return _fail_deep(jid, "the big model gave an empty answer")
    cut = finish == "length"
    text = text[:MAX_ANSWER_CHARS]
    tokens = usage.get("completion_tokens")
    m = _measure("deep_questions", lane.model, tokens, secs, len(text.split()))
    why = (f"Answered in {m['seconds']:.0f} s by {name}"
           + (f", {m['tokens_per_s']} tokens a second" if m["tokens_per_s"] else "")
           + (f" ({m['words_per_s']} words a second)" if m["words_per_s"] else "")
           + ". The time includes reading the question.")
    if cut:
        why += (f" The answer stopped at the {_deep_max_tokens():,}-token limit "
                f"([big_model] deep_max_tokens), so it may end mid-sentence.")
    _set_job(jid, state="done", finished=int(_now()), answer=text, seconds=m["seconds"],
             tokens=m["tokens"], prompt_tokens=usage.get("prompt_tokens"), words=m["words"],
             words_per_s=m["words_per_s"], tokens_per_s=m["tokens_per_s"], why=why)
    with _DEEP_LOCK:
        job = dict(_DEEP[jid])
    _keep(job)
    _publish("deep", {"id": jid, "state": "done"})
    _audit("deep.done", {"job": jid})


def handle_deep_post(body) -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "state": "refused",
                     "error": "send {\"question\": \"...\"}"}
    return ask(body.get("question"))


def _reset_for_tests() -> None:
    global _ENGINE
    with _PENDING_LOCK:
        _PENDING.clear()
        _LAST.clear()
    try:
        _ENGINE.stop("reset")
    except Exception:
        pass
    _ENGINE = _Engine()
    _DET.update(at=-1e9, value=None)
    _PY_CACHE.update(at=-1e9, value=None)
    _DRIVE_TYPES.clear()
    _MEASURED.clear()
    with _KEY_LOCK:
        _KEY.update(value=None, kept="not-made-yet")
    with _DEEP_LOCK:
        _DEEP.clear()
        _DEEP_WORKER["running"] = False


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
