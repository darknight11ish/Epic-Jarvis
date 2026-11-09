"""jarvis_model_resources.py - WHAT IS LOADED RIGHT NOW, AND WHAT IT COSTS.

THE OWNER'S ASK, verbatim (2026-11-08, Brain -> Model screenshots):

    "the model section should tell me whats currently loaded into jarvis, how
     much memory is jarvis using of each gpu, how much other computer resources
     jarvis is uses besides vram on the gpus, what the context size is, and any
     other important info"

and, on the COMPUTE panel that said "Runs on graphics card 2" while the Coding
preset's pooled three-card lane held the coder across all three cards:

    "i have the coding preset loaded into jarvis right now, and it still says
     this"

WHAT THIS MODULE IS. The read-only truth half: ONE answer, for the chat lane and
every running Ollama lane on this PC, saying the model that is loaded, the
context size it is really running, the loaded size against the size in video
memory (the spill), and which graphics cards carry it; plus every card's
total/used/free memory and how much of that the local models are using; plus
Jarvis's OWN resident memory and processor use, read from the operating system.

WHAT IT NEVER DOES. It writes nothing, loads nothing, switches nothing, starts
no lane and raises no card. It only GETs each lane's own `/api/ps` (a read that
loads nothing) and runs `nvidia-smi`/`netstat` read-only. Unreachable lane or a
lane with nothing loaded is said in WORDS - never a 0 dressed up as a fact.

WHO SERVES IT. `jarvis_model_recommendations.install()` already wraps the live
handler for `GET /api/models/recommendations`; that wrapper serves this module's
answer at `GET /api/models/resources` (additive, same token/origin checks, and
the same DESKTOP-ONLY rule as its neighbour - the phone is deliberately not
given the graphics-card/process read; ARCHITECTURE.md section 8 says why).

WHAT ELSE IT READS (2026-11-09, the "Measured results" card). `measured()` serves
`GET /api/models/measured`, and it reads the TWO stores `jarvis_bench.py` writes -
the same stores docs/JARVIS-API.md section 205 answers "what has been measured"
from: `BenchLog` (speed runs, `bench.jsonl`) and `ScoreLog` (the five-suite
scorecards, `bench-scores.jsonl`). Every row and every number is copied from the
store; the one sentence describing a result is the store's OWN `words` field,
built by `jarvis_bench` when it measured it, so no screen can word one
measurement two different ways. An empty store is said in words WITH the reason
(no file yet, or a file with no readable row), and a missing benchmark module
answers `available: false` - it never invents a row or a score.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

#: The product's own active-chat-lane file under the config folder. The SAME
#: rule `jarvis_hud.active_ollama_url()` implements (the file, loopback only,
#: `OLLAMA_URL` as the documented fallback) - kept here so the answer follows
#: the lane chat really uses, not a module constant.
ACTIVE_LANE_FILE = "presets-active-lane.json"
CHOICE_FILE = "presets-choice.json"
#: The name this file had before 2026-11-09; read only as a fallback.
LEGACY_CHOICE_FILE = "preset-choice.json"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

#: Fallback lane table, used only when `jarvis_presets` cannot be imported
#: (a clone or a suite). It mirrors that module's own LANES; the live PC's
#: table always wins.
_FALLBACK_LANES = (
    ("main", 11436, "the everyday lane", "RTX 2060", "the long-context card"),
    ("coding", 11435, "the Fast preset's lane", "RTX 2080 SUPER", "the fast card"),
    ("pooled", 11450, "the Coding preset's lane", "all three cards",
     "one model across all three cards"),
)
_LOCAL_PREFIXES = ("http://127.0.0.1:", "http://localhost:")


# --------------------------------------------------------------------------
#   Small words helpers (pure - every one is proved in the suite)
# --------------------------------------------------------------------------
def gb_words(mb) -> str:
    """`12288` MB -> "12.0 GB". Empty string for an unknown number."""
    try:
        value = float(mb)
    except (TypeError, ValueError):
        return ""
    if value != value:  # NaN
        return ""
    return f"{value / 1024:.1f} GB"


def gib_words(byte_count) -> str:
    """`14497590799` bytes -> "13.5 GiB". Empty string for an unknown number."""
    try:
        value = float(byte_count)
    except (TypeError, ValueError):
        return ""
    if value != value:
        return ""
    return f"{value / (1024 ** 3):.1f} GiB"


def mib_words(byte_count) -> str:
    """Bytes -> whole MiB, for a spill small enough to want a plain number."""
    return f"{float(byte_count) / (1024 ** 2):,.0f} MiB"


def cards_words(indices) -> str:
    """`[0, 1, 2]` -> "all three graphics cards (0, 1, 2)"; `[2]` -> card 2."""
    idx = sorted({int(i) for i in (indices or []) if str(i).strip().isdigit()})
    if not idx:
        return "no graphics card (or the cards carrying it were not reported)"
    if idx == [0, 1, 2]:
        return "all three graphics cards (0, 1, 2)"
    if len(idx) == 1:
        return f"graphics card {idx[0]}"
    if len(idx) == 2:
        return f"graphics cards {idx[0]} and {idx[1]}"
    return "graphics cards " + ", ".join(str(i) for i in idx[:-1]) + f" and {idx[-1]}"


def context_words(tokens) -> str:
    try:
        value = int(tokens)
    except (TypeError, ValueError):
        return "the context size was not reported"
    if value <= 0:
        return "the context size was not reported"
    return f"{value:,} tokens of context"


def spill_words(spill_bytes, percent) -> str:
    try:
        spill = int(spill_bytes or 0)
    except (TypeError, ValueError):
        spill = 0
    if spill <= 0:
        return "nothing spilled into system RAM"
    on_card = f"{percent}% on the cards" if percent is not None else "partly on the cards"
    return f"{mib_words(spill)} spilled into system RAM ({on_card})"


def _active_lane(config_dir: Path, ollama_url: str = "") -> dict:
    """The chat lane, resolved the way `jarvis_hud.active_ollama_url()` does."""
    path = Path(config_dir) / ACTIVE_LANE_FILE
    doc = None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - absent/unreadable is the fallback case
        doc = None
    candidate = ""
    if isinstance(doc, dict):
        candidate = str(doc.get("base_url") or "").strip().rstrip("/")
    if candidate.startswith(_LOCAL_PREFIXES):
        return {"url": candidate, "source": "presets-active-lane.json",
                "file": str(path), "fallback": False}
    fallback = (ollama_url or os.environ.get("OLLAMA_URL") or DEFAULT_OLLAMA_URL)
    return {"url": str(fallback).strip().rstrip("/"), "source": "OLLAMA_URL",
            "file": str(path), "fallback": True}


def _chosen_preset(config_dir: Path) -> Optional[str]:
    """The preset the owner last applied, from the product's own answer."""
    try:
        import jarvis_presets as presets  # type: ignore
        chosen = presets.choice()
        if chosen:
            return str(chosen)
    except Exception:  # noqa: BLE001 - the file below is the documented fallback
        pass
    for name in (CHOICE_FILE, LEGACY_CHOICE_FILE):
        try:
            doc = json.loads((Path(config_dir) / name).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(doc, dict):
            chosen = str(doc.get("preset") or "") or None
            if chosen:
                return chosen
    return None


# --------------------------------------------------------------------------
#   The readers (each one injectable, so no test needs a live GPU)
# --------------------------------------------------------------------------
def _get_json(url: str, timeout: float = 2.5) -> tuple:
    """(status, json-or-None, error sentence). Read-only GET."""
    import urllib.request

    req = urllib.request.Request(
        url, headers={"X-Jarvis-Client": "hud", "Accept": "application/json",
                      "User-Agent": "jarvis-model-resources"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(4 * 1024 * 1024).decode("utf-8", "replace")
            try:
                return int(resp.status), json.loads(body), ""
            except Exception:  # noqa: BLE001
                return int(resp.status), None, "the lane did not answer in JSON"
    except Exception as exc:  # noqa: BLE001
        return 0, None, f"{type(exc).__name__}: {exc}"


def _lane_ps(url: str, get_json: Callable = _get_json) -> dict:
    """One lane's `/api/ps`, read-only. {} (and an `error`) when it says nothing."""
    code, doc, error = get_json(url.rstrip("/") + "/api/ps")
    models = []
    if isinstance(doc, dict):
        for row in doc.get("models") or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("model") or "")
            if not name:
                continue
            size = _number(row.get("size"))
            vram = _number(row.get("size_vram"))
            percent = None
            if size and size > 0 and vram is not None:
                percent = int(round(vram * 100 / size))
            models.append({
                "name": name,
                "context_length": _int(row.get("context_length")),
                "size_bytes": size,
                "size_vram_bytes": vram,
                "spill_bytes": (int(size - vram) if size is not None and
                                vram is not None and size >= vram else 0),
                "on_card_percent": percent,
            })
    return {"url": url, "ok": code == 200, "code": code, "models": models,
            "error": "" if code == 200 else (error or f"HTTP {code}")}


def _number(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _smi_output(run: Callable) -> dict:
    """Two read-only `nvidia-smi` queries: cards, and their compute processes."""

    def query(fields):
        try:
            done = run(["nvidia-smi", f"--query-{fields}",
                        "--format=csv,noheader,nounits"],
                       capture_output=True, text=True, timeout=10)
            if done.returncode != 0:
                return None, (done.stderr or "").strip()[:200]
            return [line.strip() for line in (done.stdout or "").splitlines()
                    if line.strip()], ""
        except Exception as exc:  # noqa: BLE001
            return None, f"{type(exc).__name__}: {exc}"

    gpu_lines, gpu_error = query("gpu=index,uuid,name,memory.total,memory.used,"
                                 "memory.free,display_active")
    app_lines, app_error = query(
        "compute-apps=gpu_uuid,pid,process_name,used_memory")
    return {"gpus": gpu_lines or [], "apps": app_lines or [],
            "error": gpu_error or app_error or ""}


def _parse_gpus(lines) -> list:
    out = []
    for line in lines or []:
        cols = [c.strip() for c in str(line).split(",")]
        if len(cols) < 6 or not cols[0].isdigit():
            continue
        out.append({
            "index": int(cols[0]),
            "uuid": cols[1],
            "name": cols[2],
            "total_mb": _number(cols[3]),
            "used_mb": _number(cols[4]),
            "free_mb": _number(cols[5]),
            "display_active": (cols[6].lower() == "enabled") if len(cols) > 6
            else None,
            "jarvis_mb": None,
            "other_mb": None,
        })
    return out


def _parse_apps(lines) -> list:
    out, seen = [], set()
    for line in lines or []:
        cols = [c.strip() for c in str(line).split(",")]
        if len(cols) < 4:
            continue
        pid = _int(cols[1])
        if pid is None:
            continue
        key = (cols[0], pid)
        if key in seen:          # one process can be listed once per card
            continue
        seen.add(key)
        # Windows' WDDM driver answers "[N/A]" for per-process video memory;
        # None means "not reported", never 0.
        out.append({"gpu_uuid": cols[0], "pid": pid, "name": cols[2],
                    "used_mb": _number(cols[3])})
    return out


def _is_model_server(app: dict) -> bool:
    """A local Ollama model host: the llama-server runner or ollama itself."""
    name = str(app.get("name") or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return "llama-server" in name or name.startswith("ollama")


def _unique_indices(apps) -> list:
    return sorted({int(a["gpu_index"]) for a in apps
                   if a.get("gpu_index") is not None})


def _listen_pids(run: Callable, ports) -> tuple:
    """Port -> listening PID from `netstat -ano`, read-only. ({}, error)."""
    wanted = {int(p) for p in ports if str(p).isdigit()}
    try:
        done = run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                   text=True, timeout=10)
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"
    if done.returncode != 0:
        return {}, (done.stderr or "").strip()[:200]
    out = {}
    for line in (done.stdout or "").splitlines():
        cols = line.split()
        if len(cols) < 5 or cols[0].upper() != "TCP":
            continue
        if cols[3].upper() != "LISTENING":
            continue
        port = _int(cols[1].rsplit(":", 1)[-1])
        pid = _int(cols[4])
        if port in wanted and pid is not None:
            out[port] = pid
    return out, ""


def _default_process_stats(pid: int) -> dict:
    """One process's real memory/CPU numbers, read-only (Windows)."""
    if os.name != "nt":
        return {"available": False, "why": "this is not a Windows PC"}
    try:
        return _windows_process_stats(int(pid))
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "why": f"{type(exc).__name__}: {exc}"}


def _windows_process_stats(pid: int) -> dict:
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD)]

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ: read-only access.
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
    if not handle:
        return {"available": False,
                "why": "the process could not be opened for a read"}
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters),
                                          counters.cb):
            return {"available": False, "why": "the memory numbers were refused"}
        created = FILETIME()
        exited = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created),
                                        ctypes.byref(exited),
                                        ctypes.byref(kernel),
                                        ctypes.byref(user)):
            return {"available": False, "why": "the processor times were refused"}
        handles = wintypes.DWORD(0)
        kernel32.GetProcessHandleCount(handle, ctypes.byref(handles))
    finally:
        kernel32.CloseHandle(handle)

    def ft_seconds(ft):
        return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 10_000_000.0

    cpu_seconds = ft_seconds(kernel) + ft_seconds(user)
    created_at = ft_seconds(created)
    uptime = max(0.0, time.time() - created_at) if created_at > 0 else None
    cpu_percent = (cpu_seconds / uptime * 100.0) if uptime else None
    return {
        "available": True,
        "pid": pid,
        "rss_mb": round(counters.WorkingSetSize / (1024 ** 2), 1),
        "private_mb": round(counters.PagefileUsage / (1024 ** 2), 1),
        "cpu_seconds": round(cpu_seconds, 1),
        "cpu_percent": round(cpu_percent, 1) if cpu_percent is not None else None,
        "handles": int(handles.value),
        "uptime_s": int(uptime) if uptime is not None else None,
    }


# --------------------------------------------------------------------------
#   The one read
# --------------------------------------------------------------------------
def collect(*, config_dir=None, preset_rows=None, lanes=None, active_lane=None,
            get_json: Callable = _get_json,
            smi: Optional[dict] = None,
            listen: Optional[Callable] = None,
            process_stats: Optional[Callable] = None,
            now: Optional[float] = None,
            jarvis_pid: Optional[int] = None) -> dict:
    """The whole answer: lanes, cards, the Jarvis process. Never raises for a
    missing lane, a missing card or a missing number - it says so in words."""
    read_at = float(now if now is not None else time.time())
    config = Path(config_dir) if config_dir is not None else _config_dir()
    rows = preset_rows if preset_rows is not None else _preset_rows()
    lane_defs = lanes if lanes is not None else _lane_definitions()
    active = active_lane if active_lane is not None else _active_lane(config)
    choose = _chosen_preset(config)
    by_lane: dict = {}
    for row in rows or []:
        key = str(row.get("lane") or "")
        if key:
            by_lane.setdefault(key, []).append(row)

    smi_data = smi if smi is not None else _smi_output(_subprocess_run())
    gpus = _parse_gpus(smi_data.get("gpus"))
    apps = _parse_apps(smi_data.get("apps"))
    uuid_to_index = {str(g.get("uuid")): int(g["index"]) for g in gpus}
    for app in apps:
        app["gpu_index"] = uuid_to_index.get(str(app.get("gpu_uuid")))
    model_apps = [a for a in apps if _is_model_server(a)]

    ports = [int(d["port"]) for d in lane_defs if d.get("port")]
    listen_pids, listen_error = ({}, "not asked")
    if listen is not None:
        listen_pids, listen_error = listen(ports)
    elif smi_data.get("apps"):
        listen_pids, listen_error = _listen_pids(_subprocess_run(), ports)
    process = process_stats or _default_process_stats

    lane_answers = []
    for definition in lane_defs:
        port = int(definition.get("port") or 0)
        if port <= 0:
            continue
        url = str(definition.get("url") or f"http://127.0.0.1:{port}")
        ps = _lane_ps(url, get_json=get_json)
        titles = [str(r.get("title") or r.get("id") or "") for r in
                  (by_lane.get(definition["key"]) or [])]
        row = {
            "key": definition["key"],
            "label": definition.get("label") or definition["key"],
            "url": url,
            "port": port,
            "card": definition.get("card") or "",
            "lane_words": definition.get("words") or "",
            "preset_ids": [str(r.get("id") or "") for r in
                           (by_lane.get(definition["key"]) or [])],
            "preset_titles": [t for t in titles if t],
            "is_chat_lane": url.rstrip("/") == str(active.get("url") or "").rstrip("/"),
            "ok": ps["ok"],
            "state": "unreachable",
            "model": None,
            "context_length": None,
            "size_bytes": None,
            "size_vram_bytes": None,
            "spill_bytes": None,
            "on_card_percent": None,
            "gpu_indices": [],
            "loaded": False,
        }
        if not ps["ok"]:
            row["words"] = (f"not running - nothing answers on port {port}")
            lane_answers.append(row)
            continue
        if not ps["models"]:
            row["state"] = "not_loaded"
            row["words"] = "nothing loaded"
            lane_answers.append(row)
            continue
        model = ps["models"][0]
        row.update({
            "state": "loaded",
            "loaded": True,
            "model": model["name"],
            "context_length": model.get("context_length"),
            "size_bytes": model.get("size_bytes"),
            "size_vram_bytes": model.get("size_vram_bytes"),
            "spill_bytes": model.get("spill_bytes") or 0,
            "on_card_percent": model.get("on_card_percent"),
            "gpu_indices": _lane_gpu_indices(apps, listen_pids.get(port)),
        })
        row["words"] = (
            f"{model['name']} loaded with "
            f"{context_words(model.get('context_length'))}, "
            f"{_on_card_words(row)}")
        lane_answers.append(row)

    # A lane's cards may be known only from the model server's own GPU rows:
    # the Ollama listener spawns the llama-server runner, so their pids differ.
    # When exactly ONE lane holds a model, all the model server's cards are
    # that lane's - a measured fact, not a guess. With two loaded lanes the
    # split cannot be told from these reads, so it is left unsaid.
    loaded_lanes = [l for l in lane_answers if l.get("loaded")]
    if len(loaded_lanes) == 1 and not loaded_lanes[0].get("gpu_indices"):
        known = _unique_indices(model_apps)
        if known:
            loaded_lanes[0]["gpu_indices"] = known
            loaded_lanes[0]["words"] = (
                f"{loaded_lanes[0]['model']} loaded with "
                f"{context_words(loaded_lanes[0].get('context_length'))}, "
                f"{_on_card_words(loaded_lanes[0])}")

    # Cards: the loaded model's video memory total is Ollama's own measured
    # figure. The PER-CARD split of Jarvis's models needs the driver to report
    # per-process memory; when it answers [N/A] (this PC's Windows driver does),
    # the share is said to be unknown rather than dressed as 0.
    share_known = bool(model_apps) and all(a.get("used_mb") is not None
                                           for a in model_apps)
    attributed = {}
    if share_known:
        for app in model_apps:
            idx = app.get("gpu_index")
            used = app.get("used_mb")
            if idx is None or used is None:
                continue
            attributed[idx] = attributed.get(idx, 0.0) + float(used)
        for gpu in gpus:
            used = gpu.get("used_mb")
            jarvis = attributed.get(int(gpu["index"]))
            if used is not None and jarvis is not None:
                gpu["jarvis_mb"] = round(jarvis, 1)
                gpu["other_mb"] = round(max(0.0, float(used) - jarvis), 1)
    loaded_vram_bytes = sum(int(l.get("size_vram_bytes") or 0)
                            for l in loaded_lanes)
    gpu_share = {
        "known": share_known,
        "why": ("" if share_known else
                "the graphics driver does not report how much video memory "
                "each program is using, so Jarvis's share of each card is not "
                "guessed"),
        "loaded_vram_gib": (round(loaded_vram_bytes / (1024 ** 3), 1)
                            if loaded_vram_bytes else None),
        "cards": _unique_indices(model_apps),
    }
    # Every model server process this PC is running for Jarvis (listener and
    # runner both), with its real resident memory - the spill lives in RAM.
    lane_servers = []
    server_pids = sorted({int(p) for p in listen_pids.values()}
                         | {int(a["pid"]) for a in model_apps})
    for pid in server_pids[:10]:
        stats = process(pid)
        lane_servers.append({"pid": pid,
                             "rss_mb": stats.get("rss_mb"),
                             "available": bool(stats.get("available"))})
    jarvis = _jarvis_block(process, jarvis_pid, lane_servers)
    preset_title = ""
    if choose:
        for row in rows or []:
            if str(row.get("id") or "") == choose:
                preset_title = str(row.get("title") or "")
                break
    active_out = {
        "url": active.get("url"),
        "source": active.get("source"),
        "file": active.get("file"),
        "fallback": bool(active.get("fallback")),
        "preset": choose,
        "preset_title": preset_title,
        "words": _active_words(active, lane_answers, preset_title),
    }
    warnings = _consistency_warnings(active_out, lane_answers, gpus)
    answer = {
        "available": True,
        "read_at": read_at,
        "read_at_words": time.strftime("%H:%M:%S", time.localtime(read_at)),
        "active_lane": active_out,
        "lanes": lane_answers,
        "gpus": gpus,
        "gpu_share": gpu_share,
        "jarvis": jarvis,
        "warnings": warnings,
        "notes": ([
            "Read-only: this answer only looked. Nothing was loaded, switched or started.",
        ] + ([] if gpu_share["known"] else [
            "The per-card amount Jarvis is using is not reported by this PC's "
            "graphics driver; the loaded model's total video memory is Ollama's "
            "own measured figure and is shown instead.",
        ])),
        "words": _headline_words(active_out, lane_answers, gpus, jarvis),
    }
    return answer


def _subprocess_run():
    import subprocess
    return subprocess.run


def _config_dir() -> Path:
    """The product's config folder: OPENJARVIS_CONFIG_DIR, else ~/.openjarvis."""
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR",
                               Path.home() / ".openjarvis"))


def _preset_rows() -> list:
    """The nine preset rows as dicts (id/title/model/lane key), or []."""
    try:
        import jarvis_presets as presets  # type: ignore
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for preset in getattr(presets, "PRESETS", []) or []:
        try:
            view = preset.view() if hasattr(preset, "view") else {}
        except Exception:  # noqa: BLE001
            view = {}
        if not isinstance(view, dict):
            continue
        lane = view.get("lane")
        lane_key = ""
        if isinstance(lane, dict):
            lane_key = str(lane.get("key") or "")
        elif isinstance(lane, str):
            lane_key = lane
        rows.append({"id": str(view.get("id") or ""),
                     "title": str(view.get("title") or ""),
                     "model": str(view.get("model") or ""),
                     "lane": lane_key})
    return rows


def _lane_definitions() -> list:
    """Every local lane the PC can run, from `jarvis_presets`' own LANES."""
    labels = {"main": "the everyday lane", "coding": "the Fast preset's lane",
              "pooled": "the Coding preset's lane (all three cards)"}
    defs = []
    try:
        import jarvis_presets as presets  # type: ignore
        table = getattr(presets, "LANES", {})
        for key, info in (table or {}).items():
            port = _int(info.get("port"))
            if not port:
                continue
            defs.append({"key": str(key), "port": port,
                         "label": labels.get(str(key), str(key)),
                         "card": str(info.get("card") or ""),
                         "words": str(info.get("words") or "")})
    except Exception:  # noqa: BLE001
        defs = []
    if not defs:
        defs = [{"key": key, "port": port, "label": labels.get(key, key),
                 "card": card, "words": words}
                for key, port, label, card, words in _FALLBACK_LANES]
    defs.sort(key=lambda d: 0 if d["key"] == "main" else
               (1 if d["key"] == "coding" else 2))
    return defs


def _lane_gpu_indices(apps, pid) -> list:
    """Which cards carry this lane's model: the cards its own server uses."""
    if pid is None:
        return []
    return sorted({int(a["gpu_index"]) for a in apps
                   if a.get("pid") == pid and a.get("gpu_index") is not None})


def _on_card_words(lane: dict) -> str:
    percent = lane.get("on_card_percent")
    spill = lane.get("spill_bytes") or 0
    memory = gib_words(lane.get("size_vram_bytes")) or "an unknown size"
    cards = cards_words(lane.get("gpu_indices"))
    if percent is None:
        return f"{memory} in video memory; the spill was not reported"
    if spill <= 0:
        return f"{memory} in video memory, 100% on {cards}"
    return (f"{memory} in video memory, {percent}% on {cards}: "
            + spill_words(spill, percent))


def _active_words(active: dict, lanes, preset_title: str) -> str:
    url = str(active.get("url") or "")
    matched = next((l for l in lanes
                    if str(l.get("url") or "").rstrip("/") == url.rstrip("/")), None)
    label = matched["label"] if matched else "the lane chat is pointed at"
    if active.get("fallback"):
        return (f"Chat is using the PC's default Ollama lane ({url}); no preset "
                "lane has been applied on this PC.")
    if preset_title:
        return f'Chat is using the "{preset_title}" preset\'s lane: {label} ({url}).'
    return f"Chat is using {label} ({url})."


def _headline_words(active: dict, lanes, gpus, jarvis: dict) -> list:
    words = [str(active.get("words") or "")]
    loaded = [l for l in lanes if l.get("loaded")]
    if loaded:
        words.append("Loaded now: " + "; ".join(
            f"{l['model']} on {l['label']} ({context_words(l.get('context_length'))})"
            for l in loaded))
    else:
        words.append("Nothing is loaded into Jarvis right now.")
    card_bits = []
    for gpu in gpus:
        free = gb_words(gpu.get("free_mb"))
        total = gb_words(gpu.get("total_mb"))
        if not total:
            continue
        bit = f"card {gpu['index']} has {free or 'an unknown amount'} free of {total}"
        if gpu.get("jarvis_mb") is not None:
            bit += f" (Jarvis's models use {gb_words(gpu['jarvis_mb'])})"
        card_bits.append(bit)
    if card_bits:
        words.append("Cards: " + "; ".join(card_bits) + ".")
    share_known = bool(any(g.get("jarvis_mb") is not None for g in gpus))
    loaded_vram = sum(float(l.get("size_vram_bytes") or 0)
                      for l in lanes if l.get("loaded"))
    if not share_known and loaded_vram > 0:
        words.append("Jarvis's loaded model holds " + gib_words(loaded_vram)
                     + " of video memory in total; this PC's graphics driver "
                     "does not report how much of each card is Jarvis's.")
    if jarvis.get("available"):
        words.append(str(jarvis.get("words") or ""))
    return [w for w in words if w]


def _jarvis_block(process: Callable, jarvis_pid, lane_servers) -> dict:
    pid = int(jarvis_pid if jarvis_pid is not None else os.getpid())
    stats = process(pid)
    if not stats.get("available"):
        return {"available": False, "pid": pid,
                "why": str(stats.get("why") or "the process numbers were not readable"),
                "words": "Jarvis's own memory and processor use could not be read."}
    rss = stats.get("rss_mb")
    cpu = stats.get("cpu_percent")
    bits = []
    if rss is not None:
        bits.append(f"{rss:.0f} MiB of RAM")
    if cpu is not None:
        bits.append(f"{cpu:.1f}% of the processor on average since it started")
    words = ("Jarvis itself is using " + " and ".join(bits) + "." if bits
             else "Jarvis's own memory use is not reported on this PC.")
    out = {"available": True, "pid": pid, "name": "jarvis",
           "rss_mb": rss, "private_mb": stats.get("private_mb"),
           "cpu_seconds": stats.get("cpu_seconds"), "cpu_percent": cpu,
           "handles": stats.get("handles"), "uptime_s": stats.get("uptime_s"),
           "model_servers": lane_servers,
           "words": words}
    model_ram = [s.get("rss_mb") for s in lane_servers if s.get("rss_mb")]
    out["model_servers_rss_mb"] = round(sum(model_ram), 1) if model_ram else None
    if model_ram:
        out["words"] = (words + " The Ollama model servers it runs are using "
                        f"{sum(model_ram):.0f} MiB more.")
    return out


def _consistency_warnings(active: dict, lanes, gpus) -> list:
    """A short, honest note when what is loaded does not match the chat lane."""
    warnings = []
    matched = next((l for l in lanes
                    if str(l.get("url") or "").rstrip("/")
                    == str(active.get("url") or "").rstrip("/")), None)
    loaded_elsewhere = [l for l in lanes
                        if l.get("loaded") and l is not matched]
    if loaded_elsewhere and matched is not None and not matched.get("loaded"):
        names = ", ".join(l["model"] or l["label"] for l in loaded_elsewhere)
        warnings.append(f"The chat lane has nothing loaded, but {names} is loaded "
                        "on another lane.")
    if not gpus:
        warnings.append("No graphics card could be asked on this read; memory "
                        "figures are absent rather than zero.")
    return warnings


# --------------------------------------------------------------------------
#   What has been measured: the two benchmark stores, read-only
# --------------------------------------------------------------------------
# THE STORES ARE `jarvis_bench`'s, NOT OURS. docs/JARVIS-API.md section 205
# answers "what has been measured" from `BenchLog` (speed runs: model, lane,
# decode rate, spill, pass/fail, date) and `ScoreLog` (one row per suite per
# model/quant/context/digest, with score, items passed, decode rate and date).
# This module only READS them through `jarvis_bench`'s own functions, so the
# card, the chat answer and the benchmark that wrote the row cannot disagree
# about the file, the shape or the sentence. The row sentence (`words`) is
# written by `jarvis_bench` at measurement time and shown verbatim: a screen
# that re-worded it could say a spilled run was fast.

#: How many rows the card shows from each store. The counts of everything
#: stored travel with them, so "3 shown" can never read as "3 measured".
MEASURED_RUNS_SHOWN = 3
MEASURED_SCORES_SHOWN = 5


def _day_words(at) -> str:
    """An epoch -> `YYYY-MM-DD` on THIS PC's own clock, or "" for no stamp."""
    try:
        stamp = float(at)
    except (TypeError, ValueError):
        return ""
    if not (stamp > 0) or stamp != stamp or stamp == float("inf"):
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(stamp))


def _stored_number(row: dict, key: str):
    """The stored number under `key`, or None. A missing number is never a 0."""
    value = (row or {}).get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _run_brief(row: dict) -> dict:
    """One stored speed run, as the card reads it - only what the row holds."""
    out = {
        "kind": "speed run",
        "model": str(row.get("model") or "")[:120],
        "lane": str(row.get("lane") or "")[:40],
        "preset": str(row.get("preset") or "")[:40],
        "spilled": bool(row.get("spilled")),
        "words": str(row.get("words") or "")[:400],
        "at": _stored_number(row, "at"),
        "day": _day_words(row.get("at")),
    }
    if isinstance(row.get("ok"), bool):
        out["ok"] = row["ok"]
    for key in ("gen_median", "prefill_median"):
        value = _stored_number(row, key)
        if value is not None:
            out[key] = value
    why = str(row.get("why") or "")[:200]
    if why:
        out["why"] = why
    return out


def _score_brief(row: dict, labels: dict) -> dict:
    """One stored suite scorecard, as the card reads it - only stored fields."""
    suite = str(row.get("suite") or "")[:40]
    out = {
        "kind": "scorecard",
        "model": str(row.get("model") or "")[:120],
        "suite": suite,
        # The label comes from `jarvis_bench.SUITES`, the same table the runner
        # uses; an unknown id is made readable, never guessed at as another suite.
        "suite_label": (labels.get(suite)
                        or suite.replace("_", " ").capitalize() or "a suite"),
        "skipped": bool(row.get("skipped")),
        "words": str(row.get("words") or "")[:400],
        "at": _stored_number(row, "at"),
        "day": _day_words(row.get("at")),
    }
    if isinstance(row.get("passed"), bool):
        out["passed"] = row["passed"]
    for key in ("score_pct", "items", "items_passed", "decode_tps", "ctx"):
        value = _stored_number(row, key)
        if value is not None:
            out[key] = value
    quant = str(row.get("quant") or "")[:40]
    if quant:
        out["quant"] = quant
    why = str(row.get("why") or "")[:200]
    if why:
        out["why"] = why
    return out


def _store_state(path, fallback: str = "the benchmark store") -> dict:
    """`{name, exists}` for one store file - the name only, never the full path."""
    name = ""
    exists = False
    try:
        if path is not None:
            name = Path(path).name
            exists = Path(path).is_file()
    except (OSError, TypeError, ValueError):
        exists = False
    return {"name": name or fallback, "exists": exists}


def _empty_reason(what: str, store: dict, rows: int, read_failed: bool,
                  start: str) -> str:
    """Why a list is empty - THE point of the card's empty state. Three
    different silences (never measured, a file with no readable row, a read
    that failed) must not read as one."""
    if read_failed:
        return (f"The {what} store could not be read this time, so nothing "
                "measured is shown - rather than a number that was not read.")
    if rows:
        return ""
    if not store.get("exists"):
        return (f"No {what} is on file yet: there is no {store['name']} beside "
                f"Jarvis's saved files. {start}")
    return (f"{store['name']} exists, but it holds no readable {what} yet, so "
            "there is nothing measured to show.")


def measured(*, limit_runs: int = MEASURED_RUNS_SHOWN,
             limit_scores: int = MEASURED_SCORES_SHOWN,
             now: Optional[float] = None,
             bench_log=None, score_log=None) -> dict:
    """The Brain's "Measured results" card: the stored speed runs and suite
    scorecards, newest first, with an honest reason when either is empty.

    READ-ONLY, and the numbers are never invented: a row is copied from the
    store's own allowlisted fields, every missing number is absent rather than
    0, and the sentence describing a result is the stored `words` field the
    benchmark itself wrote. No clock, no network and no model call reaches a
    row; `now` only dates the read.

    `bench_log`/`score_log` are injectable so a suite can drive both empty and
    populated stores without the owner's real `bench.jsonl`. Never raises.
    """
    read_at = float(now if now is not None else time.time())
    answer = {
        "available": True,
        "read_at": read_at,
        "read_at_words": time.strftime("%H:%M:%S", time.localtime(read_at)),
        "runs": [],
        "scorecards": [],
        "counts": {"runs": 0, "scorecards": 0},
        "stores": {"speed": {"name": "the speed-run store", "exists": False},
                   "scores": {"name": "the scorecard store", "exists": False}},
        "empty": {"runs": "", "scorecards": ""},
        "notes": ["Read-only: this answer only read the two benchmark stores. "
                  "Nothing was measured, loaded, switched or started."],
        "words": [],
    }
    try:
        import jarvis_bench as bench  # type: ignore
    except Exception:  # noqa: BLE001 - a clone or an older PC
        why = ("This backend has no benchmark module (jarvis_bench.py), so it "
               "cannot read measured results - and it will not invent one.")
        answer["available"] = False
        answer["why"] = why
        answer["empty"] = {"runs": why, "scorecards": why}
        answer["words"] = [why]
        return answer

    log = bench_log if bench_log is not None else bench.BenchLog()
    scores = score_log if score_log is not None else bench.ScoreLog()
    answer["stores"]["speed"] = _store_state(getattr(log, "path", None),
                                             "the speed-run store")
    answer["stores"]["scores"] = _store_state(getattr(scores, "path", None),
                                              "the scorecard store")
    labels = {str(s.get("id")): str(s.get("label") or s.get("id") or "")
              for s in (getattr(bench, "SUITES", ()) or ())
              if isinstance(s, dict) and s.get("id")}

    run_rows, runs_failed = [], False
    try:
        # `limit=0` is the store's own "all rows" (newest first), so the count
        # below is of everything stored, not of the few the card shows.
        run_rows = list(log.runs(limit=0))
    except Exception:  # noqa: BLE001 - a damaged store reads as a clear note
        runs_failed = True
    score_rows, scores_failed = [], False
    try:
        score_rows = list(bench.score_history(limit=100000, store=scores))
    except Exception:  # noqa: BLE001 - same rule for the scorecards
        scores_failed = True

    answer["counts"] = {"runs": len(run_rows), "scorecards": len(score_rows)}
    shown_runs = max(0, int(limit_runs)) if limit_runs is not None else 0
    shown_scores = max(0, int(limit_scores)) if limit_scores is not None else 0
    answer["runs"] = [_run_brief(row) for row in run_rows[:shown_runs]]
    answer["scorecards"] = [_score_brief(row, labels)
                            for row in score_rows[:shown_scores]]
    answer["empty"]["runs"] = _empty_reason(
        "speed run", answer["stores"]["speed"], len(run_rows), runs_failed,
        'A speed run is started by "Benchmark on this PC" on a model, or by '
        "asking Jarvis to start a benchmark.")
    answer["empty"]["scorecards"] = _empty_reason(
        "five-suite scorecard", answer["stores"]["scores"], len(score_rows),
        scores_failed,
        'Ask Jarvis to "start the benchmark suites" to measure all five.')

    words = []
    newest_run = answer["runs"][0] if answer["runs"] else None
    if newest_run and newest_run.get("words"):
        words.append("Newest speed run: " + str(newest_run["words"]).rstrip(".") + ".")
    newest_score = answer["scorecards"][0] if answer["scorecards"] else None
    if newest_score and newest_score.get("words"):
        words.append("Newest scorecard (" + str(newest_score.get("suite_label"))
                     + "): " + str(newest_score["words"]).rstrip(".") + ".")
    for key in ("runs", "scorecards"):
        if answer["empty"][key]:
            words.append(answer["empty"][key])
    if answer["runs"] or answer["scorecards"]:
        words.append("Every number above was measured on this PC and copied "
                     "from its benchmark store.")
    answer["words"] = [w for w in words if w]
    return answer


__all__ = ["collect", "measured", "cards_words", "context_words", "gb_words",
           "gib_words", "mib_words", "spill_words", "ACTIVE_LANE_FILE",
           "CHOICE_FILE", "MEASURED_RUNS_SHOWN", "MEASURED_SCORES_SHOWN"]
