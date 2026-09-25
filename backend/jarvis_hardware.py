"""jarvis_hardware.py - which graphics cards this PC has, and the three setups.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).
docs/HARDWARE-PROFILES.md is the design; jarvis_profiles.py does the
arithmetic. This module does everything that touches the PC:

    status()            GET  /api/hardware          the cards, what runs now,
                                                    three presets, the one line
    choose(preset)      POST /api/hardware/apply    remembers the owner's
                                                    choice; the steps appear
    request_create(n)   POST /api/hardware/create   ONE approval card
                                                    (models_create, tier "ask"),
                                                    then Ollama makes the model
    request_measure()   POST /api/hardware/measure  times each model and checks
                                                    it is all on the card

DETECTION, in the design's trust order (section 4.1):

    1. Ollama's own log, %LOCALAPPDATA%\\Ollama\\server.log: the cards Ollama
       will use ("inference compute" lines, most recent start-up only), and
       the reason for each card it dropped.
    2. nvidia-smi (jarvis_compute.query_cards): the GPU-... id, the monitor,
       live free memory.
    3. The registry (HardwareInformation.qwMemorySize under the display-
       adapter class key): name and real total memory of every card, any
       maker. Win32_VideoController is not used at all: its memory field
       stops at 4 GB, and the registry gives the same names.

The log lines' shape was read from Ollama's source (the design, section 2.1);
no real log from the owner's PC has been seen yet. Every test value is made
up and labelled so.

NOTHING CHANGES UNTIL THE OWNER CHOOSES (section 4.8). Choosing a preset only
records the choice in hardware-choice.json beside the other settings. Every
step after it - downloading a model, making a tuned model, switching chat,
each second-card switch - is its own approval card, raised when the owner
presses that step's button, in order; a step waits for the one before it.
There is no "approve all" (CLAUDE.md). What Ollama reads at start-up is one
PowerShell line the owner runs.

Never raises from the public calls. Never returns a token or key: card ids
(GPU-...) are hardware ids. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid as _uuid
from pathlib import Path
from typing import Callable, Optional

import jarvis_local_http
import jarvis_profiles as P

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    import jarvis_compute as compute
except Exception:
    compute = None  # type: ignore

HOST = "127.0.0.1"
MAIN_PORT = 11434
ACTION_CREATE = "models_create"
CHOICE_FILE = "hardware-choice.json"
MEASURED_FILE = "hardware-measured.json"
#: The routes a step may name. The apps post a step's body to its route and
#: to nothing else (commands.rs `hardware_step`, JarvisRuntime.hardwareStep).
STEP_ROUTES = ("/api/models/install", "/api/models/switch", "/api/hardware/create",
               "/api/second-card")
_CACHE_SECONDS = 10.0


# --------------------------------------------------------------------------
#   Reading Ollama's log (source 1)
# --------------------------------------------------------------------------

_KV = re.compile(r'([A-Za-z_][A-Za-z0-9_.]*)=("(?:[^"\\]|\\.)*"|\S*)')
#: Ollama's start-up markers: its "server config" line first, then
#: "Listening on". The most recent one starts the block that counts.
_START = re.compile(r'msg="server config"|msg="Listening on')
_DROPPED = (
    ("skipping CUDA device", "Ollama skipped it: its CUDA build does not include this card's "
                             "generation"),
    ("dropping ROCm device", "Ollama dropped it: its AMD (ROCm) build has no support for this "
                             "card's chip"),
    ("AMD driver is too old", "Ollama dropped it: the AMD driver is too old"),
    ("NVIDIA driver too old", "Ollama dropped it: the NVIDIA driver is too old"),
    ("driver too old", "Ollama dropped it: the driver is too old"),
    ("dropping integrated GPU", "Ollama does not use built-in (integrated) graphics unless told "
                                "to (OLLAMA_IGPU_ENABLE=1)"),
)


def parse_kv(line: str) -> dict:
    """key=value pairs of one Go slog text line; quoted values unquoted."""
    out = {}
    for k, v in _KV.findall(str(line or "")):
        if v.startswith('"') and v.endswith('"') and len(v) >= 2:
            v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        out[k] = v
    return out


def _gib(text) -> Optional[float]:
    """"8.0 GiB", "7936 MiB", "512 B" -> GiB. None when it is not that."""
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]i?B|B)\s*", str(text or ""))
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2).upper().replace("I", "")
    scale = {"B": 1 / 1024 ** 3, "KB": 1 / 1024 ** 2, "MB": 1 / 1024, "GB": 1.0, "TB": 1024.0}
    return n * scale[unit]


def _env_map(text: str) -> dict:
    """Ollama's `env="map[NAME:value NAME:value]"` as a dict."""
    m = re.search(r"map\[(.*)\]", str(text or ""), re.S)
    if not m:
        return {}
    out = {}
    for tok in m.group(1).split():
        if ":" in tok:
            k, v = tok.split(":", 1)
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
                out[k] = v
    return out


def parse_ollama_log(text: str) -> dict:
    """The most recent start-up block of Ollama's server.log, and the model
    loads after it. Every field is None or empty when the log does not say.

    {"devices": [{id, uuid, library, compute, name, description, pci_id, type,
                  total_gib, available_gib}],
     "dropped": [{"why", "name", "pci_id", "raw"}],
     "overrode": {name: value} | None, "default_ctx": int | None,
     "env": {name: value} | None, "version": str | None,
     "offloaded": [n, m] | None, "flash_forced": bool, "cache_type_k": str | None}
    """
    lines = str(text or "").splitlines()
    # The last "server config" line starts the most recent start-up; a log
    # without one (cut short) falls back to the last "Listening on".
    marks = [i for i, ln in enumerate(lines) if 'msg="server config"' in ln]
    if not marks:
        marks = [i for i, ln in enumerate(lines) if _START.search(ln)]
    start = marks[-1] if marks else 0
    out = {"devices": [], "dropped": [], "overrode": None, "default_ctx": None, "env": None,
           "version": None, "offloaded": None, "flash_forced": False, "cache_type_k": None}
    for ln in lines[start:]:
        kv = parse_kv(ln)
        msg = kv.get("msg", "")
        if msg == "server config":
            out["env"] = _env_map(kv.get("env", ln))
            continue
        if msg.startswith("Listening on"):
            m = re.search(r"version ([0-9][^)\s]*)", msg)
            if m:
                out["version"] = m.group(1)
            continue
        if msg == "inference compute":
            uuid = next((kv[k] for k in ("filter_id", "id", "uuid")
                         if str(kv.get(k, "")).startswith("GPU-")), "")
            out["devices"].append({
                "id": kv.get("id", ""), "uuid": uuid,
                "library": _route(kv.get("library", "")),
                "compute": kv.get("compute", ""), "name": kv.get("name", ""),
                "description": kv.get("description", "") or kv.get("name", ""),
                "pci_id": kv.get("pci_id", ""), "type": kv.get("type", ""),
                "total_gib": _gib(kv.get("total")), "available_gib": _gib(kv.get("available")),
            })
            continue
        if msg == "user overrode visible devices":
            out["overrode"] = {k: v for k, v in kv.items()
                               if k not in ("time", "level", "source", "msg")}
            continue
        if msg == "vram-based default context":
            try:
                out["default_ctx"] = int(kv.get("default_num_ctx", ""))
            except ValueError:
                pass
            continue
        for needle, why in _DROPPED:
            if needle in msg or needle in ln:
                out["dropped"].append({
                    "why": why,
                    "name": kv.get("description") or kv.get("name") or "",
                    "pci_id": kv.get("pci_id", ""),
                    "gfx": kv.get("gfx_target") or kv.get("gpu_type") or "",
                    "raw": msg or ln.strip()[:200]})
                break
        m = re.search(r"offloaded (\d+)/(\d+) layers to GPU", ln)
        if m:
            out["offloaded"] = [int(m.group(1)), int(m.group(2))]
        if "enabling flash_attn since it is required for quantized V cache" in ln:
            out["flash_forced"] = True
        if "starting llama-server" in ln or "starting llama server" in ln:
            m = re.search(r"--cache-type-k[ =]+(\S+)", ln)
            if m:
                out["cache_type_k"] = m.group(1).strip('"')
    return out


def _route(library: str) -> str:
    low = str(library or "").strip().lower()
    return {"cuda": "CUDA", "rocm": "ROCm", "hip": "ROCm", "vulkan": "Vulkan"}.get(low, "")


# --------------------------------------------------------------------------
#   Reading the registry (source 3)
# --------------------------------------------------------------------------

CLASS_KEY = r"HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def parse_reg(text: str) -> list:
    """`reg query <CLASS_KEY> /s` output: one entry per adapter subkey
    (\\0000, \\0001, ...) that has a name. total_gib is None when the size is
    not in the 64-bit value (HardwareInformation.qwMemorySize); the older
    32-bit value is never used for sizing (it stops at 4 GB)."""
    out, cur = [], None
    for raw in str(text or "").splitlines():
        line = raw.rstrip()
        if line.upper().startswith("HKEY_"):
            m = re.search(r"\\(\d{4})$", line)
            cur = {"key": m.group(1), "name": "", "total_gib": None, "device_id": ""} if m else None
            if cur is not None:
                out.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"\s+(\S+)\s+(REG_\w+)\s*(.*)$", line)
        if not m:
            continue
        name, typ, val = m.group(1), m.group(2), m.group(3).strip()
        if name == "DriverDesc" and typ == "REG_SZ":
            cur["name"] = val
        elif name == "MatchingDeviceId" and typ == "REG_SZ":
            cur["device_id"] = val.lower()
        elif name == "HardwareInformation.qwMemorySize":
            try:
                if typ == "REG_QWORD":
                    cur["total_gib"] = int(val, 16) / 1024 ** 3
                elif typ == "REG_BINARY" and len(val) == 16:
                    cur["total_gib"] = int.from_bytes(bytes.fromhex(val), "little") / 1024 ** 3
            except ValueError:
                pass
    return [c for c in out if c["name"]]


def _vendor(name: str, device_id: str = "") -> str:
    up = f"{name} {device_id}".upper()
    if "NVIDIA" in up or "VEN_10DE" in up or "GEFORCE" in up or "QUADRO" in up or "TESLA" in up:
        return "nvidia"
    if "AMD" in up or "RADEON" in up or "VEN_1002" in up:
        return "amd"
    if "INTEL" in up or "VEN_8086" in up or " ARC" in up:
        return "intel"
    return "other"


# --------------------------------------------------------------------------
#   Things the tests replace
# --------------------------------------------------------------------------

def _ollama_log_path() -> Optional[Path]:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Ollama" / "server.log" if base else None


def _read_tail(path: Optional[Path], max_bytes: int = 2 * 1024 * 1024) -> Optional[str]:
    if path is None:
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return None


def _read_log() -> Optional[str]:
    return _read_tail(_ollama_log_path())


def _read_lane_log() -> Optional[str]:
    """The second Ollama's own log, which Jarvis writes (jarvis_second_card)."""
    return _read_tail(_config_dir() / "second-card-ollama.log")


_REG = {"at": -1e9, "text": None}
_REG_SECONDS = 300.0


def _reg_text() -> Optional[str]:
    """`reg query` of the display-adapter class key, kept 5 minutes: the
    cards in a PC do not change while it runs, and the apps re-read often."""
    if os.name != "nt":
        return None
    now = time.monotonic()
    if _REG["text"] is not None and now - _REG["at"] < _REG_SECONDS:
        return _REG["text"]
    text = _reg_query()
    _REG.update(at=now, text=text)
    return text


def _reg_query() -> Optional[str]:
    if os.name != "nt":
        return None
    exe = shutil.which("reg")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "query", CLASS_KEY, "/s"], capture_output=True, text=True,
                             timeout=10)
    except Exception:
        return None
    return out.stdout if out.returncode == 0 else None


def _smi_cards(fresh: bool = False) -> list:
    if compute is None:
        return []
    try:
        return compute.query_cards(fresh=fresh)
    except Exception:
        return []


def _user_env(name: str) -> Optional[str]:
    """A Windows user setting (HKCU\\Environment). None elsewhere."""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            val, _ = winreg.QueryValueEx(k, name)
            return str(val) if val else None
    except Exception:
        return None


def _on_windows() -> bool:
    return os.name == "nt"


def _http_json(url: str, payload: Optional[dict] = None, timeout: float = 2.0):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("not a loopback address")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    with jarvis_local_http.urlopen(req, timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _main_url() -> str:
    return (os.environ.get("OLLAMA_URL") or f"http://{HOST}:{MAIN_PORT}").rstrip("/")


def _second_url() -> Optional[str]:
    try:
        import jarvis_second_card as SC
        return SC._LANE.url()
    except Exception:
        return None


def _current_model() -> Optional[str]:
    """The model everyday chat uses, from jarvis_models (the owner's file).
    None when it cannot say."""
    try:
        import jarvis_models
        name = jarvis_models.current_model()
        return str(name) if name else None
    except Exception:
        return None


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-hardware", daemon=True).start()


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    return str(fw.action_tier(action)) if fw is not None else "unknown"


def _primary_setting() -> str:
    if fw is None:
        return ""
    try:
        return str(fw.load_framework().get("compute", {}).get("primary_gpu", "") or "")
    except Exception:
        return ""


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _config_dir() -> Path:
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


# --------------------------------------------------------------------------
#   Ollama on this PC
# --------------------------------------------------------------------------

def _tags(url: str) -> Optional[set]:
    try:
        body = _http_json(f"{url}/api/tags", timeout=2.0)
    except Exception:
        return None
    names = set()
    for m in body.get("models") or []:
        for k in ("name", "model"):
            if isinstance(m.get(k), str):
                names.add(m[k])
    return names


def _has(names: Optional[set], model: str) -> Optional[bool]:
    if names is None:
        return None
    want = {model, model + ":latest"} if ":" not in model else {model}
    return bool(want & names)


def _ps(url: str) -> Optional[list]:
    try:
        body = _http_json(f"{url}/api/ps", timeout=2.0)
    except Exception:
        return None
    return [m for m in body.get("models") or [] if isinstance(m, dict)]


def _version(url: str) -> Optional[str]:
    try:
        v = _http_json(f"{url}/api/version", timeout=1.0)
    except Exception:
        return None
    return str(v.get("version")) if isinstance(v, dict) and v.get("version") else None


def _show(url: str, name: str) -> Optional[dict]:
    try:
        body = _http_json(f"{url}/api/show", {"model": name}, timeout=3.0)
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _num_ctx(show: Optional[dict]) -> Optional[int]:
    m = re.search(r"(?m)^\s*num_ctx\s+(\d+)", str((show or {}).get("parameters") or ""))
    return int(m.group(1)) if m else None


def _same(a: str, b: str) -> bool:
    strip = lambda s: s[:-7] if s.endswith(":latest") else s
    return bool(a and b) and strip(a.strip()) == strip(b.strip())


# --------------------------------------------------------------------------
#   Detection: the cards, joined
# --------------------------------------------------------------------------

def _norm(name: str) -> str:
    up = re.sub(r"[^A-Z0-9 ]", " ", str(name or "").upper())
    up = re.sub(r"\b(NVIDIA|GEFORCE|AMD|RADEON|INTEL|R|TM)\b", " ", up)
    return " ".join(up.split())


def _close(a: Optional[float], b: Optional[float]) -> bool:
    return a is not None and b is not None and abs(a - b) <= max(0.35, 0.06 * max(a, b))


_DET_LOCK = threading.Lock()
_DET: dict = {"at": -1e9, "value": None}


def detect(fresh: bool = False) -> dict:
    """The cards, every one, with where each fact came from. Never raises.

    {"cards": [row], "planned": [jarvis_profiles.Card], "sources": {...},
     "found": sentence, "log": parse_ollama_log(...) | None}"""
    now = time.monotonic()
    with _DET_LOCK:
        if not fresh and _DET["value"] is not None and now - _DET["at"] < _CACHE_SECONDS:
            return _DET["value"]
    try:
        value = _detect(fresh)
    except Exception as exc:
        value = {"cards": [], "planned": [], "log": None,
                 "sources": {"ollama_log": "unreadable", "nvidia_smi": "unreadable",
                             "registry": "unreadable"},
                 "found": f"The graphics cards could not be read ({type(exc).__name__})."}
    with _DET_LOCK:
        _DET.update(at=now, value=value)
    return value


def _nothing_loaded() -> bool:
    """Is no model loaded in either Ollama right now? Then nvidia-smi's free
    memory is the desktop's share, measured (section 4.1)."""
    for url in (_main_url(), _second_url()):
        if not url:
            continue
        ps = _ps(url)
        if ps is None:
            if url == _main_url():
                return False       # cannot tell: do not call it measured
            continue
        if ps:
            return False
    return True


def _detect(fresh: bool) -> dict:
    text = _read_log()
    log = parse_ollama_log(text) if text else None
    smi = list(_smi_cards(fresh))
    reg = parse_reg(_reg_text() or "")
    idle = _nothing_loaded() if smi else False
    rows = []
    used_smi, used_reg = set(), set()

    def smi_for(dev) -> Optional[object]:
        for i, s in enumerate(smi):
            if i in used_smi:
                continue
            if dev.get("uuid") and getattr(s, "uuid", "") and s.uuid.lower() == dev["uuid"].lower():
                return i
        for i, s in enumerate(smi):
            if i in used_smi:
                continue
            if _norm(s.name) == _norm(dev.get("description", "")) and \
                    _close(s.total_mb / 1024, dev.get("total_gib")):
                return i
        return None

    def reg_for(name: str, total: Optional[float]) -> Optional[int]:
        for i, r in enumerate(reg):
            if i in used_reg:
                continue
            if _norm(r["name"]) == _norm(name) and (total is None or r["total_gib"] is None
                                                    or _close(r["total_gib"], total)):
                return i
        return None

    if log is not None and log["devices"]:
        for dev in log["devices"]:
            si = smi_for(dev)
            s = smi[si] if si is not None else None
            if si is not None:
                used_smi.add(si)
            name = (s.name if s is not None else "") or dev["description"] or dev["name"] \
                or "a graphics card"
            total = (s.total_mb / 1024) if s is not None else dev["total_gib"]
            ri = reg_for(name, total)
            if ri is not None:
                used_reg.add(ri)
                if total is None:
                    total = reg[ri]["total_gib"]
            sources = ["Ollama's log"] + (["nvidia-smi"] if s is not None else []) + \
                (["the registry"] if ri is not None else [])
            share, how = None, ""
            if s is not None and idle and s.free_mb > 0:
                share, how = max(0.0, (s.total_mb - s.free_mb) / 1024), \
                    "measured now, with no model loaded"
            elif dev["available_gib"] is not None and total:
                share, how = max(0.0, total - dev["available_gib"]), \
                    "measured when Ollama started"
            vendor = "nvidia" if dev["library"] == "CUDA" else _vendor(
                name, reg[ri]["device_id"] if ri is not None else "")
            rows.append({
                "name": name, "total_gib": total, "vendor": vendor,
                "route": dev["library"] or "", "compute": dev["compute"] or (
                    str(s.compute_cap) if s is not None and s.compute_cap else ""),
                "uuid": (s.uuid if s is not None and s.uuid else dev["uuid"]) or "",
                "pci_id": dev["pci_id"],
                "monitor": s.display_active if s is not None else None,
                "free_gib": (s.free_mb / 1024) if s is not None else dev["available_gib"],
                "share_gib": share, "share_how": how, "used": True, "why_unused": "",
                "sources": sources, "index": s.index if s is not None else None})
    elif smi:
        for i, s in enumerate(smi):
            used_smi.add(i)
            ri = reg_for(s.name, s.total_mb / 1024)
            if ri is not None:
                used_reg.add(ri)
            share, how = None, ""
            if idle and s.free_mb > 0:
                share, how = max(0.0, (s.total_mb - s.free_mb) / 1024), \
                    "measured now, with no model loaded"
            rows.append({
                "name": s.name, "total_gib": s.total_mb / 1024, "vendor": "nvidia",
                "route": "CUDA", "compute": str(s.compute_cap) if s.compute_cap else "",
                "uuid": s.uuid or "", "pci_id": "", "monitor": s.display_active,
                "free_gib": s.free_mb / 1024, "share_gib": share, "share_how": how,
                # No log: assumed usable, and said so.
                "used": True, "why_unused": "",
                "sources": ["nvidia-smi"] + (["the registry"] if ri is not None else []),
                "index": s.index})
    # Cards Ollama does not list (or nvidia-smi only saw when there is a log).
    for i, s in enumerate(smi):
        if i in used_smi:
            continue
        ri = reg_for(s.name, s.total_mb / 1024)
        if ri is not None:
            used_reg.add(ri)
        rows.append(_unused_row(s.name, s.total_mb / 1024, "nvidia", log,
                                ["nvidia-smi"] + (["the registry"] if ri is not None else []),
                                uuid=s.uuid or "", monitor=s.display_active, index=s.index))
    for i, r in enumerate(reg):
        if i in used_reg:
            continue
        rows.append(_unused_row(r["name"], r["total_gib"], _vendor(r["name"], r["device_id"]),
                                log, ["the registry"]))
    planned = []
    for n, row in enumerate(rows):
        row["key"] = row["uuid"] or row["pci_id"] or f"card{n}"
        if not row["used"] or not row["total_gib"]:
            continue
        planned.append(P.Card(
            key=row["key"], name=row["name"], total_gib=float(row["total_gib"]),
            monitor=row["monitor"], share_gib=row["share_gib"], share_source=row["share_how"],
            route=row["route"] or "CUDA", compute=row["compute"], vendor=row["vendor"],
            uuid=row["uuid"]))
    sources = {
        "ollama_log": ("used" if log is not None and log["devices"] else
                       "no cards in it" if log is not None else "not found"),
        "nvidia_smi": "used" if smi else "not found",
        "registry": "used" if reg else ("not on Windows" if os.name != "nt" else "not read"),
    }
    return {"cards": rows, "planned": planned, "sources": sources, "log": log,
            "found": _found_sentence(rows, planned, log)}


def _unused_row(name, total, vendor, log, sources, *, uuid="", monitor=None, index=None) -> dict:
    why = ""
    if log is not None:
        for d in log["dropped"]:
            if d["name"] and _norm(d["name"]) == _norm(name):
                why = d["why"]
                break
        if not why:
            integrated = [d for d in log["dropped"] if "integrated" in d["why"]]
            if integrated and vendor == "intel" and (total or 0) < 4.5:
                why = integrated[0]["why"]
        why = why or "Ollama's log does not list it, so Ollama does not use it"
    elif vendor == "nvidia":
        why = "nvidia-smi sees it, but it could not be matched to anything else"
    else:
        why = ("Ollama's log was not found, so Jarvis cannot tell whether Ollama can use it. "
               "Start Ollama once, then look again")
    return {"name": name, "total_gib": total, "vendor": vendor, "route": "", "compute": "",
            "uuid": uuid, "pci_id": "", "monitor": monitor, "free_gib": None,
            "share_gib": None, "share_how": "", "used": False, "why_unused": why,
            "sources": sources, "index": index}


def _found_sentence(rows, planned, log) -> str:
    if not rows:
        return ("No graphics card was found: Ollama's log, nvidia-smi and the registry said "
                "nothing, so everything would run on the processor.")
    n = len(planned)
    names = " and ".join(f"the {c.name}" for c in planned) or "none"
    head = (f"Found {len(rows)} graphics card{'s' if len(rows) != 1 else ''}; "
            f"Ollama can use {n}: {names}.")
    if log is None:
        head += (" Ollama's log was not found, so this is from nvidia-smi alone: which cards "
                 "Ollama really uses is assumed, not read.")
    return head


# --------------------------------------------------------------------------
#   The owner's choice, and what Jarvis made for it
# --------------------------------------------------------------------------

_STATE_LOCK = threading.RLock()


def _choice_path() -> Path:
    return _config_dir() / CHOICE_FILE


def _measured_path() -> Path:
    return _config_dir() / MEASURED_FILE


def _read_json(p: Path) -> dict:
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _write_json(p: Path, data: dict) -> Optional[str]:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:
        return f"could not save it ({type(exc).__name__})"
    return None


def cards_fingerprint(planned: list) -> str:
    """Which cards these are: names and memory, sorted. A different set
    means a choice made for other hardware no longer counts."""
    return " + ".join(sorted(f"{c.name} {c.total_gib:.1f}" for c in planned))


def _choice() -> dict:
    """{"preset", "fingerprint", "at", "before", "created": {name: {...}}}."""
    raw = _read_json(_choice_path())
    if raw.get("preset") not in P.PRESET_IDS:
        raw["preset"] = None
    if not isinstance(raw.get("created"), dict):
        raw["created"] = {}
    if not isinstance(raw.get("before"), dict):
        raw["before"] = {}
    return raw


def _measured_rows() -> list:
    rows = _read_json(_measured_path()).get("rows")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _limits(fp: str, preset: str) -> dict:
    """Caps from the last measurement of this preset on these cards: a role
    that was partly on the processor drops to the next context size (the
    owner's decision 1: drop, rather than spill)."""
    out: dict = {}
    for r in _measured_rows():
        # By the cards alone, so a new Ollama version does not forget that a
        # size did not fit. Every spill counts, not only the last one: once
        # the smaller size measures clean, the bigger one still did not fit.
        if r.get("cards") != fp or r.get("preset") != preset:
            continue
        for role in r.get("roles") or []:
            if role.get("spilled") and isinstance(role.get("ctx"), int):
                lower = [c for c in P.CONTEXTS if c < role["ctx"]]
                if lower:
                    name = role.get("role")
                    out[name] = min(out.get(name, max(lower)), max(lower))
    return out


def _layouts(planned: list, *, gap: float = P.GAP_GIB, fp: str = "") -> dict:
    prim = _primary_setting()
    return {pid: P.plan(planned, pid, gap=gap, primary=prim, limits=_limits(fp, pid))
            for pid in P.PRESET_IDS}


def lane_plan() -> Optional[dict]:
    """For jarvis_second_card: where the lanes go under the chosen preset,
    or None - no preset chosen, or chosen for other cards - which means
    "exactly as before presets existed" (section 4.8). Never raises.

    {"preset", "chat_card": Card, "lane_card": Card | None (None: the lanes
     run in the everyday Ollama), "long": (model, ctx, gib) | None,
     "pictures": (model, ctx, gib) | None, "fit_target": str | None,
     "why_none": {feature: sentence}}"""
    try:
        ch = _choice()
        if not ch.get("preset"):
            return None
        det = detect()
        planned = det["planned"]
        fp = cards_fingerprint(planned)
        if not planned or ch.get("fingerprint") != fp:
            return None
        lay = _layouts(planned, fp=fp)[ch["preset"]]
        if lay.chat is None:
            return None
        lane_card = lay.lane_card
        same = lane_card is None or lane_card is lay.chat.card
        long = (lay.long.tuned, lay.long.ctx, round(lay.long.need, 2)) if lay.long else None
        pics = (lay.pictures.tuned, lay.pictures.ctx, round(lay.pictures.need, 2)) \
            if lay.pictures else None
        why = {}
        if long is None:
            why["long_context"] = (
                f"this preset ({_preset_name(lay.preset)}) has no separate long-conversation "
                f"model: " + (f"chat itself has room for {lay.chat.ctx:,} tokens"
                              if lay.long_is_chat else "there is no room for one"))
        if pics is None:
            why["vision"] = (f"this preset ({_preset_name(lay.preset)}) has no picture model: "
                             + next((o for o in lay.off if o.startswith("Pictures")),
                                    "there is no room for one").rstrip("."))
        fit = dict(P.settings_for(lay)).get("LLAMA_ARG_FIT_TARGET")
        return {"preset": lay.preset, "chat_card": lay.chat.card,
                "lane_card": None if same else lane_card, "long": long, "pictures": pics,
                "pictures_mode": lay.pictures.mode if lay.pictures else None,
                "fit_target": fit, "why_none": why}
    except Exception:
        return None


def _preset_name(pid: Optional[str]) -> str:
    return next((p["name"] for p in P.PRESETS if p["id"] == pid), "Custom")


# --------------------------------------------------------------------------
#   The steps (section 4.5)
# --------------------------------------------------------------------------

def _gate_waiting() -> list:
    """[(action, detail as text)] for every approval card waiting now, from
    jarvis_gate.pending() (the owner's file). Empty when it cannot be read -
    a step then shows as "next", never as done."""
    try:
        import jarvis_gate
        rows = jarvis_gate.pending() or []
    except Exception:
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = r.get("detail")
        text = d if isinstance(d, str) else json.dumps(d, default=str)
        out.append((str(r.get("action") or ""), text or ""))
    return out


def _card_up(waiting: list, action: str, ref: str) -> bool:
    """Is a card for `action` about `ref` waiting? The model's name has to
    be in the card's detail: the gate's detail for a download or switch is
    the owner's file's to shape, so this only says yes when it can see it."""
    pat = re.compile(r"(?<![\w.:-])" + re.escape(ref) + r"(?:[\s\"'},]|:latest|$)")
    return any(a == action and pat.search(t) for a, t in waiting)


def _switches() -> Optional[dict]:
    try:
        import jarvis_second_card as SC
        sw = SC._read_switches()
        with SC._PENDING_LOCK:
            pend = [f for f in SC._PENDING if not SC._PENDING[f].get("withdrawn")]
        return {"master": sw["master"], "features": dict(sw["features"]), "pending": pend}
    except Exception:
        return None


def _steps(lay: P.Layout, ch: dict, *, names: Optional[set], current: Optional[str],
           sw: Optional[dict], settings: list, user: dict, pending_create: set,
           gate_waiting: Optional[list] = None) -> list:
    steps = []
    gate_waiting = gate_waiting or []
    if lay.chat is None:
        return steps
    for base in dict.fromkeys(r.model.ref for r in lay.roles):
        have = _has(names, base)
        m = P.MODELS[base]
        steps.append({"id": f"install:{base}", "kind": "install",
                      "title": f"Download {base} (about {m.download_gb:.1f} GB)",
                      "detail": ("Raises the usual download card. Nothing downloads until you "
                                 "approve it."),
                      "route": "/api/models/install", "body": {"ref": base},
                      "done": have is True, "known": have is not None,
                      "waiting": _card_up(gate_waiting, "download_model", base)})
    for r in lay.roles:
        made = ch["created"].get(r.tuned) or {}
        exists = _has(names, r.tuned)
        ok = bool(exists and made.get("from") == r.model.ref and made.get("num_ctx") == r.ctx)
        steps.append({"id": f"create:{r.tuned}", "kind": "create",
                      "title": (f"Make {r.tuned}: {r.model.ref} with room for {r.ctx:,} tokens"),
                      "detail": ("Raises a card showing exactly what is made. It is made on "
                                 "this PC from the model you downloaded; nothing downloads."
                                 + (" It replaces the jarvis model of the same name." if exists
                                    and not ok else "")),
                      "route": "/api/hardware/create", "body": {"name": r.tuned},
                      "done": ok, "known": names is not None,
                      "waiting": r.tuned in pending_create,
                      "modelfile": P.modelfile(r)})
    steps.append({"id": "switch:" + P.TUNED["chat"], "kind": "switch",
                  "title": f"Switch everyday chat to {P.TUNED['chat']}",
                  "detail": ("Raises the usual model-switch card. jarvis-primary stays "
                             "installed, so switching back is one more switch."),
                  "route": "/api/models/switch", "body": {"ref": P.TUNED["chat"]},
                  "done": bool(current and _same(current, P.TUNED["chat"])),
                  "known": current is not None,
                  "waiting": _card_up(gate_waiting, "switch_model", P.TUNED["chat"])})
    lanes = []
    if lay.long is not None:
        lanes.append("long_context")
    if lay.pictures is not None:
        lanes.append("vision")
    if lanes:
        names_sc = {"master": "the second-card switch (\"Use the second graphics card\")",
                    "long_context": "\"Longer conversations\"", "vision": "\"Pictures\""}
        for f in ["master"] + lanes:
            on = None
            waiting = False
            if sw is not None:
                on = sw["master"] if f == "master" else bool(sw["features"].get(f))
                waiting = f in sw["pending"]
            steps.append({"id": f"lane:{f}", "kind": "lane",
                          "title": f"Turn on {names_sc[f]}",
                          "detail": "Raises the usual second-card card.",
                          "route": "/api/second-card", "body": {"feature": f, "enabled": True},
                          "done": on is True, "known": on is not None, "waiting": waiting})
    if settings:
        if _on_windows():
            done = all(_same_setting(user.get(n), v) for n, v in settings)
            known = True
        else:
            done, known = False, False
        steps.append({"id": "command", "kind": "command",
                      "title": "Run the one-line command, then restart Ollama",
                      "detail": ("Ollama reads these settings only when it starts. The line is "
                                 "under \"The one command\"; nothing is written to a file."),
                      "route": None, "body": None, "done": done, "known": known})
    seen_next = False
    for s in steps:
        s.setdefault("waiting", False)
        if s["done"]:
            s["state"] = "done"
        elif not seen_next:
            s["state"] = "waiting" if s["waiting"] else "next"
            seen_next = True
        else:
            s["state"] = "later"
    return steps


def _same_setting(have: Optional[str], want: str) -> bool:
    if have is None:
        return False
    a, b = str(have).strip().lower(), str(want).strip().lower()
    alias = {"false": "0", "true": "1"}
    return alias.get(a, a) == alias.get(b, b)


def _restart_pending(settings: list, user: dict, log: Optional[dict]) -> Optional[bool]:
    """True when the user settings hold a value Ollama did not start with
    (its "server config" line); None when that cannot be told."""
    if not settings or log is None or not log.get("env") or not _on_windows():
        return None
    env = log["env"]
    seen = False
    for n, _ in settings:
        if n == "OLLAMA_KEEP_ALIVE" or n not in env:
            continue
        have = user.get(n)
        if have is None:
            continue
        seen = True
        if not _same_setting(env.get(n), have):
            return True
    return False if seen else None


# --------------------------------------------------------------------------
#   status() - GET /api/hardware
# --------------------------------------------------------------------------

def _card_row(row: dict, planned: list, ranked_first: Optional[P.Card]) -> dict:
    card = next((c for c in planned if c.key == row["key"]), None)
    share, how = (P.desktop_share(card) if card else (None, ""))
    if card is not None and card.share_gib is not None:
        how = f"measured ({card.share_source})"
    elif card is not None:
        how = "a placeholder until measured"
    kv = P.kv_type(card)[0] if card else None
    gen = row["compute"]
    return {
        "key": row["key"], "name": row["name"],
        "total_gb": round(row["total_gib"], 1) if row["total_gib"] else None,
        "free_gb": round(row["free_gib"], 1) if row["free_gib"] is not None else None,
        "vendor": row["vendor"], "route": row["route"] or None,
        "generation": gen or None, "monitor": row["monitor"], "uuid": row["uuid"] or None,
        "used": row["used"], "why_unused": row["why_unused"] or None,
        "sources": row["sources"],
        "desktop_share_gb": round(share, 2) if share is not None else None,
        "desktop_share_how": how or None,
        "conversation_format": kv,
        "best_effort": P.best_effort(card) if card else None,
        "chat_first": ranked_first is not None and card is ranked_first,
        "words": _card_words(row, card),
    }


def _card_words(row: dict, card: Optional[P.Card]) -> str:
    size = f"{row['total_gib']:.0f} GB" if row["total_gib"] else "memory unknown"
    bits = [f"{row['name']}, {size}"]
    if row["route"]:
        bits.append(f"used by Ollama through {row['route']}")
    if row["monitor"] is True:
        bits.append("a monitor is plugged into it")
    elif row["monitor"] is False:
        bits.append("no monitor")
    line = "; ".join(bits) + "."
    if not row["used"]:
        line += f" Not used: {row['why_unused']}."
    elif card is not None and P.best_effort(card):
        line += " Best effort, not tested."
    return line


def _now(det: dict, planned: list, ch: dict, current: Optional[str], user: dict,
         layouts: dict, all_done: bool) -> dict:
    """What runs today (section 4.6, "Now running"). Custom unless a preset
    was chosen and every step is done."""
    preset = ch.get("preset") if all_done else None
    out = {"preset": preset, "label": _preset_name(preset) if preset else
           "Custom (your own setup)", "model": current, "context": None, "on_card_percent": None,
           "bar": None, "words": ""}
    fit = user.get("LLAMA_ARG_FIT_TARGET")
    gap = (int(fit) / 1024) if (fit and fit.isdigit()) else P.LLAMA_DEFAULT_GAP_GIB
    loaded = None
    for m in _ps(_main_url()) or []:
        if current and _same(str(m.get("name") or m.get("model") or ""), current):
            loaded = m
    if loaded is not None:
        size, vram = loaded.get("size"), loaded.get("size_vram")
        if isinstance(size, (int, float)) and size > 0 and isinstance(vram, (int, float)):
            out["on_card_percent"] = int(min(100, round(vram * 100 / size)))
        if isinstance(loaded.get("context_length"), int):
            out["context"] = loaded["context_length"]
    show = _show(_main_url(), current) if current else None
    if out["context"] is None:
        out["context"] = _num_ctx(show)
    base = _match_model(show)
    if base and out["context"] and planned:
        first = P.rank(planned, _primary_setting())[0][0]
        # The format Ollama started with (its "server config" line), else
        # the user setting, else the flag it gave llama-server, else its
        # own default, f16.
        log = det.get("log") or {}
        kv = ((log.get("env") or {}).get("OLLAMA_KV_CACHE_TYPE")
              or user.get("OLLAMA_KV_CACHE_TYPE") or log.get("cache_type_k"))
        known = kv in P.KV_BYTES
        kv = kv if known else "f16"
        out["format"] = kv if known else None
        need = base.need(out["context"], kv)
        bar = P.Bar(first, need, 1, gap)
        over = bar.used_gib - first.total_gib
        out["bar"] = {"card": first.name, "used_gib": round(bar.used_gib, 2),
                      "total_gib": round(first.total_gib, 2), "blocks": bar.blocks,
                      "words": f"{need:.2f} + {bar.fixed_gib:.2f} = {bar.used_gib:.2f} of "
                               f"{first.total_gib:.0f} GB"}
        out["words"] = (f"{current} is {base.ref} with room for {out['context']:,} tokens"
                        + (f"; calculated about {over:.2f} GB over the card, so part of it is "
                           f"probably on the processor. Press Measure to check."
                           if over > 0.005 else "."))
        if not known:
            out["words"] += (" (Worked out for the larger conversation format, Ollama's own "
                             "default: Jarvis could not see which one Ollama uses here.)")
    elif current:
        out["words"] = f"Everyday chat uses {current}."
    else:
        out["words"] = "Jarvis could not tell which model everyday chat uses."
    if out["on_card_percent"] is not None and out["on_card_percent"] < 100:
        out["words"] += (f" Measured now: only {out['on_card_percent']}% of it is on the card; "
                         f"the rest runs on the processor, much more slowly.")
    return out


def _match_model(show: Optional[dict]) -> Optional[P.Model]:
    """The known model an installed one is made from, by Ollama's own
    details (family and size); None when it is not one of the table's."""
    d = (show or {}).get("details") or {}
    fam = str(d.get("family") or "").lower()
    size = str(d.get("parameter_size") or "").upper().rstrip("B")
    try:
        n = float(size)
    except ValueError:
        return None
    if fam == "qwen3":
        for ref, lo, hi in (("qwen3:4b", 3.5, 4.6), ("qwen3:8b", 7.5, 8.9),
                            ("qwen3:14b", 13.5, 15.5)):
            if lo <= n <= hi:
                return P.MODELS[ref]
    return None


def _measured_for(fp: str, preset: str) -> Optional[dict]:
    for r in reversed(_measured_rows()):
        if r.get("fingerprint") == fp and r.get("preset") == preset:
            return r
    return None


def status() -> dict:
    """GET /api/hardware. Never raises; no token, no key."""
    try:
        return _status()
    except Exception as exc:
        return {"available": True, "cards": [], "presets": [], "found":
                f"Jarvis could not work out the presets ({type(exc).__name__}).",
                "error": type(exc).__name__}


def _status() -> dict:
    det = detect()
    planned = det["planned"]
    fp = cards_fingerprint(planned)
    ch = _choice()
    stale = bool(ch.get("preset") and ch.get("fingerprint") != fp)
    layouts = _layouts(planned, fp=fp)
    rec, rec_why = P.recommended(layouts) if planned else (None, None)
    main = _main_url()
    names = _tags(main)
    current = _current_model()
    user = {n: _user_env(n) for n in P.ORDER}
    ver = _version(main)
    ranked = P.rank(planned, _primary_setting())
    first = ranked[0][0] if ranked[0] else None
    presets = []
    for pid in P.PRESET_IDS:
        lay = layouts[pid]
        d = P.describe(lay)
        m = _measured_for(fp + f" | Ollama {ver or '?'}", pid)
        d["measured"] = bool(m and m.get("ok"))
        d["measured_words"] = ("measured on this PC" if d["measured"]
                               else "calculated, not measured")
        d["recommended"] = pid == rec
        d["recommended_why"] = rec_why if pid == rec else None
        settings = P.settings_for(lay)
        d["command"] = {"line": P.one_line(settings), "undo": P.undo_line(settings, user),
                        "settings": [{"name": n, "value": v} for n, v in settings]}
        presets.append(d)
    applying = None
    all_done = False
    pend_create = _pending_creates()
    if ch.get("preset") and not stale:
        lay = layouts[ch["preset"]]
        settings = P.settings_for(lay)
        steps = _steps(lay, ch, names=names, current=current, sw=_switches(),
                       settings=settings, user=user, pending_create=pend_create,
                       gate_waiting=_gate_waiting())
        all_done = bool(steps) and all(s["done"] for s in steps)
        nxt = next((s["id"] for s in steps if s["state"] in ("next", "waiting")), None)
        applying = {"preset": ch["preset"], "name": _preset_name(ch["preset"]),
                    "chosen_at": ch.get("at"), "steps": steps, "next": nxt,
                    "done": all_done,
                    "restart_pending": _restart_pending(settings, user, det["log"]),
                    "undo": P.undo_line(settings, ch.get("before") or {})}
    cmd_lay = layouts[ch["preset"]] if applying else (layouts.get(rec) if rec else None)
    settings = P.settings_for(cmd_lay) if cmd_lay is not None else []
    return {
        "available": True,
        "found": det["found"],
        "sources": det["sources"],
        "cards": [_card_row(r, planned, first) for r in det["cards"]],
        "chat_card_why": ranked[1] if len(planned) > 1 else None,
        "gap_gb": P.GAP_GIB,
        "ollama_version": ver,
        "now": _now(det, planned, ch, current, user, layouts, all_done),
        "presets": presets,
        "recommended": rec,
        "chosen": ch.get("preset") if not stale else None,
        "chosen_stale": ("Your cards have changed since you chose a preset, so it is no "
                         "longer used. Choose again." if stale else None),
        "applying": applying,
        "command": {"for": (applying or {}).get("preset") or rec,
                    "line": P.one_line(settings), "undo": P.undo_line(
                        settings, (ch.get("before") if applying else user) or {}),
                    "check": P.CHECK_LINE,
                    "restart_pending": _restart_pending(settings, user, det["log"])},
        "measure": _measure_view(),
        # How the last "make a model" card ended: {name, outcome, why, at}.
        "last": dict(_LAST_ANY) or None,
        # Tuned models with a card waiting.
        "pending": sorted(pend_create),
        "test_later": [{"model": m, "why": w} for m, w in P.TEST_LATER],
    }


# --------------------------------------------------------------------------
#   POST /api/hardware/apply - the owner's choice
# --------------------------------------------------------------------------

def choose(preset) -> tuple:
    """Remember the owner's choice, or forget it (preset null). Changes no
    model and no setting by itself; returns the steps. (http code, body)"""
    if preset is not None and preset not in P.PRESET_IDS:
        return 400, {"error": f"there is no preset called {str(preset)[:40]!r}; the presets "
                              f"are {', '.join(P.PRESET_IDS)}"}
    with _STATE_LOCK:
        ch = _choice()
        if preset is None:
            old_lane = _lanes_now()
            ch.update(preset=None, fingerprint=None, at=int(time.time()))
            err = _write_json(_choice_path(), ch)
            if err:
                return 500, {"error": err}
            _audit("hardware.cleared", {})
            _drop_cache()
            note = _master_off_if_moved(old_lane, _lanes_now())
            return 200, {"ok": True, "chosen": None,
                         "message": ("No setup is used now. Your models and settings are as "
                                     "they are; to go back to jarvis-primary, switch to it "
                                     "(Brain, Models)." + note)}
        det = detect(fresh=True)
        planned = det["planned"]
        if not planned:
            return 503, {"error": "no graphics card Ollama can use was found, so there is "
                                  "nothing to set up"}
        fp = cards_fingerprint(planned)
        lay = _layouts(planned, fp=fp)[preset]
        if lay.chat is None:
            return 409, {"error": " ".join(lay.off) or "this preset does not fit these cards"}
        old_lane = _lanes_now()
        user = {n: _user_env(n) for n in P.ORDER}
        prev = ch.get("before") if ch.get("preset") else None
        ch.update(preset=preset, fingerprint=fp, at=int(time.time()),
                  before=prev or {k: v for k, v in user.items() if v is not None})
        err = _write_json(_choice_path(), ch)
        if err:
            return 500, {"error": err}
    _audit("hardware.chosen", {"preset": preset})
    _drop_cache()
    note = _master_off_if_moved(old_lane, _lanes_now())
    st = status()
    return 200, {"ok": True, "chosen": preset,
                 "message": (f"\"{_preset_name(preset)}\" chosen. Nothing has changed yet: each "
                             f"step below is its own approval card, in order.{note}"),
                 "applying": st.get("applying")}


def _master_off_if_moved(old: Optional[str], new: Optional[str]) -> str:
    """When the extra features would now run somewhere else - another card,
    the everyday Ollama, or back where they ran before any setup - the main
    second-card switch goes OFF: the safe direction, and the owner's yes was
    for the old place. Its card, asked again, names the new one. Returns the
    sentence to add, or ""."""
    if new is None or old == new:
        return ""
    sw = _switches()
    if sw is None or not sw["master"]:
        return ""
    try:
        import jarvis_second_card as SC
        SC.request_change("master", False)
    except Exception:
        return ""
    return (" The second-card switch was turned off, because the extra features would now "
            "run somewhere else; turning it on again asks you with a card that says where.")


def _lane_key(lay: P.Layout) -> Optional[str]:
    """Where a layout's extra features run: a card id, "main" (inside the
    everyday Ollama), or None (it has none)."""
    card = lay.lane_card
    if card is None or lay.chat is None:
        return None
    return "main" if card is lay.chat.card else (card.uuid or card.key)


def _lanes_now() -> Optional[str]:
    """Where the extra features run before this choice: the chosen preset's
    place, else the second card jarvis_second_card finds by itself."""
    plan = lane_plan()
    if plan is not None:
        lc = plan.get("lane_card")
        if plan.get("long") is None and plan.get("pictures") is None:
            return None
        return "main" if lc is None else (lc.uuid or lc.key)
    try:
        import jarvis_second_card as SC
        second = SC.detect().get("_second")
        return (second.uuid or None) if second is not None else None
    except Exception:
        return None


def _drop_cache() -> None:
    with _DET_LOCK:
        _DET.update(at=-1e9, value=None)


def handle_apply(body) -> tuple:
    if not isinstance(body, dict) or "preset" not in body:
        return 400, {"error": "send {\"preset\": \"fast\" | \"smart\" | \"features\" | null}"}
    return choose(body.get("preset"))


# --------------------------------------------------------------------------
#   POST /api/hardware/create - one tuned model, one approval card
# --------------------------------------------------------------------------

_PENDING_LOCK = threading.Lock()
_PENDING: dict = {}          # tuned name -> card id
_LAST_ANY: dict = {}


def _pending_creates() -> set:
    with _PENDING_LOCK:
        return set(_PENDING)


def _chosen_role(name: str) -> tuple:
    """(Role, Layout, sentence) for a tuned model of the chosen preset."""
    ch = _choice()
    if not ch.get("preset"):
        return None, None, "choose a preset first; this makes only that preset's models"
    det = detect(fresh=True)
    planned = det["planned"]
    fp = cards_fingerprint(planned)
    if ch.get("fingerprint") != fp:
        return None, None, "your cards have changed since the preset was chosen; choose again"
    lay = _layouts(planned, fp=fp)[ch["preset"]]
    for r in lay.roles:
        if r.tuned == name:
            return r, lay, ""
    return None, lay, f"the chosen preset does not use {name}"


def describe_create(r: P.Role, replacing: bool) -> str:
    """The approval card. Every word from here."""
    job = {"chat": "everyday chat", "long": "long conversations",
           "pictures": "pictures"}[r.role]
    return (
        f"Make the model {r.tuned} for {job}?\n\n"
        f"What it is: {r.model.ref} (already downloaded) with room for {r.ctx:,} tokens of "
        f"conversation, about {r.need:.1f} GB of the {r.card.name}'s memory (calculated, not "
        f"measured).\n\n"
        + (f"It replaces the {r.tuned} that is on this PC now.\n\n" if replacing else "")
        + "It is made by Ollama on this PC from files you already have. Nothing is downloaded "
          "and nothing leaves this PC. jarvis-primary is not changed.\n\n"
          f"Exactly what is made (a Modelfile):\n\n{P.modelfile(r)}\n"
          "If you did not just ask for this, say no.\n\n"
          "If you say no: nothing is made, and the steps after this one wait.")


def request_create(name, *, gate: Optional[Callable] = None,
                   tier_of: Optional[Callable[[str], str]] = None,
                   spawn: Optional[Callable] = None,
                   create: Optional[Callable[[dict], None]] = None) -> tuple:
    """POST /api/hardware/create {"name"}. One card; nothing is made until it
    is approved. Returns at once: `pending: true` means a card is up."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    create = create or _ollama_create
    if name not in P.TUNED.values():
        return 400, {"error": f"Jarvis only makes {', '.join(P.TUNED.values())}"}
    r, lay, why = _chosen_role(name)
    if r is None:
        return 409, {"error": why}
    names = _tags(_main_url())
    if names is None:
        return 503, {"error": "Ollama on this PC did not answer, so nothing can be made now"}
    if not _has(names, r.model.ref):
        return 409, {"error": (f"download {r.model.ref} first (the step before this one); "
                               f"making {name} never downloads anything")}
    with _PENDING_LOCK:
        if name in _PENDING:
            return 409, {"error": f"a card to make {name} is already waiting - approve or deny "
                                  f"that one"}
    try:
        tier = tier_of(ACTION_CREATE)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 503, {"error": (f"{ACTION_CREATE} is tier {tier!r} in jarvis-framework.toml; "
                               f"making a model needs a person to say yes, so it must be 'ask'")}
    pid = _uuid.uuid4().hex
    with _PENDING_LOCK:
        if name in _PENDING:
            return 409, {"error": f"a card to make {name} is already waiting"}
        _PENDING[name] = pid
    replacing = bool(_has(names, name))
    text = describe_create(r, replacing)
    detail = {"text": text, "what": f"make the model {name} on this PC", "name": name,
              "from": r.model.ref, "num_ctx": r.ctx, "card": r.card.name,
              "memory_gib": round(r.need, 2), "modelfile": P.modelfile(r),
              "leaves_this_pc": False}
    _audit("hardware.create_asked", {"name": name})

    def work() -> None:
        try:
            _decide_create(name, pid, r, gate, detail, text, create)
        except Exception as exc:
            _finish(name, pid, "failed", f"unexpected error ({type(exc).__name__})")

    try:
        spawn(work)
    except Exception:
        _finish(name, pid, "failed", "could not start")
        return 503, {"error": "could not raise the approval card"}
    return 200, {"ok": True, "pending": True,
                 "message": ("Approve the card on your PC or phone to make it. Nothing is made "
                             "until you do.")}


def _decide_create(name, pid, r, gate, detail, text, create) -> None:
    v = gate(ACTION_CREATE, detail, text)
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask":
        return _finish(name, pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(name, pid, outcome, "")
        return _finish(name, pid, "refused", str(getattr(v, "reason", "refused")))
    # Checked again now: the choice may have changed while the card waited.
    again, _, why = _chosen_role(name)
    if again is None or again.model.ref != r.model.ref or again.ctx != r.ctx:
        return _finish(name, pid, "refused",
                       why or "the chosen preset changed while the card waited")
    try:
        create(P.create_request(r))
    except Exception as exc:
        return _finish(name, pid, "failed", f"Ollama could not make it ({type(exc).__name__})")
    with _STATE_LOCK:
        ch = _choice()
        ch["created"][name] = {"from": r.model.ref, "num_ctx": r.ctx, "at": int(time.time())}
        _write_json(_choice_path(), ch)
    _finish(name, pid, "made", "")


def _ollama_create(body: dict) -> None:
    out = _http_json(f"{_main_url()}/api/create", body, timeout=300.0)
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(str(out["error"])[:200])


def _finish(name: str, pid: str, outcome: str, reason: str) -> None:
    words = {
        "made": f"{name} was made.",
        "denied": f"You said no, so {name} was not made.",
        "timed_out": f"Nobody answered the card in time, so {name} was not made.",
        "failed": f"{name} could not be made: {reason or 'an unexpected error'}.",
    }.get(outcome, f"{name} was not made: {reason or 'refused'}.")
    with _PENDING_LOCK:
        if _PENDING.get(name) == pid:
            del _PENDING[name]
        _LAST_ANY.clear()
        _LAST_ANY.update(name=name, outcome=outcome, why=words, at=int(time.time()))
    _drop_cache()
    _audit("hardware.create_decided", {"name": name, "outcome": outcome})


def handle_create(body) -> tuple:
    if not isinstance(body, dict):
        return 400, {"error": "send {\"name\": \"jarvis-chat\" | \"jarvis-long\" | "
                              "\"jarvis-vision\"}"}
    return request_create(str(body.get("name") or ""))


# --------------------------------------------------------------------------
#   POST /api/hardware/measure (section 4.7)
# --------------------------------------------------------------------------

_MEASURE = {"state": "idle", "why": "", "at": None}
_MEASURE_LOCK = threading.Lock()


def _measure_view() -> dict:
    with _MEASURE_LOCK:
        view = dict(_MEASURE)
    rows = _measured_rows()
    view["last"] = rows[-1] if rows else None
    return view


def _standby() -> bool:
    try:
        import jarvis_power
        return str(jarvis_power.current()) == "standby"
    except Exception:
        return False


def _speed_measure(model: str, base: str) -> dict:
    import jarvis_speed
    return jarvis_speed.measure(model, base=base)


def request_measure(*, spawn: Optional[Callable] = None,
                    measure: Optional[Callable[[str, str], dict]] = None) -> tuple:
    """Start measuring, in the background. No card: it runs one short
    prompt per model on this PC and changes no setting. It does LOAD each
    model, and on one card a picture model pushes chat off the card until
    the next message - the apps say so on the button."""
    spawn = spawn or _spawn
    measure = measure or _speed_measure
    if _standby():
        return 409, {"error": ("Jarvis is on standby, which keeps the graphics card free; "
                               "measuring would load models onto it. Wake Jarvis first")}
    with _MEASURE_LOCK:
        if _MEASURE["state"] == "running":
            return 409, {"error": "a measurement is already running; it takes about a minute"}
        _MEASURE.update(state="running", why="measuring…", at=int(time.time()))

    def work() -> None:
        try:
            row = _run_measure(measure)
            with _MEASURE_LOCK:
                _MEASURE.update(state="done", why=row["words"], at=int(time.time()))
        except Exception as exc:
            with _MEASURE_LOCK:
                _MEASURE.update(state="failed", why=f"The measurement stopped "
                                                    f"({type(exc).__name__}).",
                                at=int(time.time()))

    try:
        spawn(work)
    except Exception:
        with _MEASURE_LOCK:
            _MEASURE.update(state="failed", why="could not start")
        return 503, {"error": "could not start measuring"}
    return 200, {"ok": True, "running": True,
                 "message": "Measuring. It loads each model once and takes about a minute."}


def _run_measure(measure: Callable[[str, str], dict]) -> dict:
    det = detect(fresh=True)
    planned = det["planned"]
    fp = cards_fingerprint(planned)
    ch = _choice()
    preset = ch.get("preset") if ch.get("fingerprint") == fp else None
    main = _main_url()
    ver = _version(main)
    targets = []
    if preset:
        lay = _layouts(planned, fp=fp)[preset]
        for r in lay.roles:
            url = main if r.card is lay.chat.card else _second_url()
            targets.append((r.role, r.tuned, r.ctx, url))
    else:
        cur = _current_model()
        if cur:
            targets.append(("chat", cur, None, main))
    roles = []
    for role, model, ctx, url in targets:
        entry = {"role": role, "model": model, "ctx": ctx}
        if not url or _tags(url) is None:
            entry["note"] = "not measured: its copy of Ollama is not running"
            roles.append(entry)
            continue
        if not _has(_tags(url), model):
            entry["note"] = "not measured: it is not made yet"
            roles.append(entry)
            continue
        res = measure(model, url) or {}
        entry["tokens_per_s"] = res.get("tokens_per_s")
        entry["first_word_ms"] = res.get("first_word_ms")
        if not res.get("ok"):
            entry["note"] = str(res.get("note") or "not measured")[:200]
        for m in _ps(url) or []:
            if _same(str(m.get("name") or m.get("model") or ""), model):
                size, vram = m.get("size"), m.get("size_vram")
                if isinstance(size, (int, float)) and size > 0 and isinstance(vram, (int, float)):
                    entry["on_card_percent"] = int(min(100, round(vram * 100 / size)))
        text = _read_log() if url == main else _read_lane_log()
        lg = parse_ollama_log(text) if text else None
        if lg is not None:
            entry["offloaded"] = lg["offloaded"]
            entry["flash_forced"] = lg["flash_forced"]
        pct = entry.get("on_card_percent")
        off = entry.get("offloaded")
        entry["spilled"] = bool((pct is not None and pct < 100) or
                                (off and off[0] < off[1]))
        roles.append(entry)
    free = [{"card": c.name, "free_gb": round(c.free_mb / 1024, 2)}
            for c in _smi_cards(fresh=True)]
    ok = bool(roles) and all("tokens_per_s" in r and not r.get("spilled") for r in roles)
    spilled = [r for r in roles if r.get("spilled")]
    if not roles:
        words = "Nothing to measure: Jarvis could not tell which model chat uses."
    elif spilled:
        words = ("Part of " + " and ".join(r["model"] for r in spilled) +
                 " is on the processor, which is much slower. "
                 + ("The preset now uses the next smaller size for it: make that model again "
                    "(its step is open again)." if preset else
                    "A preset with less conversation would fit fully."))
    elif ok:
        words = "Everything measured is fully on the card."
    else:
        words = "Some of it could not be measured; the reasons are listed."
    row = {"fingerprint": fp + f" | Ollama {ver or '?'}", "cards": fp, "preset": preset,
           "at": int(time.time()), "roles": roles, "free": free, "ok": ok, "words": words}
    with _STATE_LOCK:
        rows = _measured_rows()[-19:] + [row]
        _write_json(_measured_path(), {"rows": rows})
    _drop_cache()
    return row


def _reset_for_tests() -> None:
    with _PENDING_LOCK:
        _PENDING.clear()
        _LAST_ANY.clear()
    with _MEASURE_LOCK:
        _MEASURE.update(state="idle", why="", at=None)
    _drop_cache()


if __name__ == "__main__":
    print(json.dumps(status(), indent=2, default=str))
