"""jarvis_second_card.py - what Jarvis may do with a second graphics card.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).

WHAT IT IS FOR. The owner is adding a second card - an RTX 2060 12 GB, or
possibly an RTX 2080 Ti 11 GB - beside the RTX 2080 Super 8 GB that runs the
everyday model. docs/MODEL-TOPOLOGY.md ("The planned second card") works out
what that second card could hold. This module is every feature built for it,
ALL OFF, each behind a switch that can only be turned on once a capable
second card is actually detected. That is how CLAUDE.md's "do not switch
anything on that depends on it until it is installed and measured" is kept:
nothing here does anything on a PC with one card, and nothing does anything
on a PC with two until the owner says yes on an approval card.

THE FEATURES (the ids are the API contract - both apps build against them):

    long_context     "Longer conversations": when a chat would be trimmed to
                     fit the main card, that answer is written on the second
                     card instead, with the whole history.
    vision           "Pictures": a turn that carries a picture goes to a
                     picture-reading model on the second card.
    learning         "Learning in the background": the memory learner's
                     model calls run on the second card.
    browser_control  "Browser control": the browser tool is offered only
                     while this lane is running, and its turns continue on
                     it. Needs long_context (it uses that lane's model).
    wiki             "Wiki builder": the lane jarvis_wiki.py's builder
                     runs on (lane_for("wiki")); it runs nowhere else.

THE INTERFACE other modules use - kept exactly:

    lane_for(feature) -> Optional[Lane]      Lane(url, model, num_ctx, why)
    status() -> dict                         GET /api/second-card
    request_change(feature, enabled, *, gate=...) -> (http code, dict)
                                             POST /api/second-card

lane_for() returns None unless the main switch and that feature are on, a
capable second card is detected, the second Ollama is running and the model
is installed. It never raises. Every caller treats None as "do exactly what
you did before this module existed".

THE PERMISSION MODEL (docs/ARCHITECTURE.md section 3). Turning a switch ON
is one approval card through jarvis_gate, action `second_card_enable`, tier
"ask" (the tier is checked before the card and again on the answer; only
tier "ask" with outcome "approved" turns it on - the same shape as the
wake-word card in jarvis_speech.set_wake_enabled). Turning OFF is immediate:
it only narrows what runs. Nothing here auto-approves (rule 4).

THE SECOND OLLAMA. While the main switch and at least one feature are on,
this starts `ollama serve` with:

    OLLAMA_HOST=127.0.0.1:11435      loopback only (rule 2); refused otherwise
    CUDA_VISIBLE_DEVICES=<uuid>      pinned by the card's id, never its number
    OLLAMA_KV_CACHE_TYPE=q8_0        the cache format MODEL-TOPOLOGY budgets
    OLLAMA_MAX_LOADED_MODELS=1       one model there at a time
    OLLAMA_NUM_PARALLEL=1            one conversation's cache, not four
    OLLAMA_CONTEXT_LENGTH=<num_ctx>  the only way to set context for the
                                     /v1 chat endpoint (no field for it)
    OLLAMA_KEEP_ALIVE=30m            (configurable)
    OLLAMA_VULKAN=0                  no Vulkan route (see below)

and NOT OLLAMA_FLASH_ATTENTION, unless `[second_card] flash_attention` says
"on". "off" is refused with a plain reason (_flash_refusal): with the q8_0
cache, llama.cpp will not load a model with flash attention off. I checked Ollama's source (llm/llama_server.go,
LlamaServerFlashAttention, main branch, 2026-09-24): unset means llama.cpp's
"auto", which falls back per model; set to 1 it passes `--flash-attn on`,
which removes that fallback. MODEL-TOPOLOGY.md already says not to set it, for
that reason.

WHY OLLAMA_VULKAN=0 (bug audit 3; the owner's decision 3 in
docs/HARDWARE-PROFILES.md section 5). Ollama reaches cards through a second
route, Vulkan, which is ON by default (ollama envconfig/config.go:234,
EnableVulkan, default true) and ignores CUDA_VISIBLE_DEVICES. Removing
GGML_VK_VISIBLE_DEVICES, which this module used to do alone, does not turn
that route off, so the second Ollama could still see the main card through
it. OLLAMA_VULKAN=0 does. The second card is always an NVIDIA card (it is
found through nvidia-smi), so CUDA is the route it uses. The owner's
`pin_command` sets the same thing for the everyday Ollama.

WHY THE CARD'S ID, NOT ITS NUMBER. CUDA numbers cards "fastest first" by
default (CUDA_DEVICE_ORDER=FASTEST_FIRST) while nvidia-smi numbers them in
PCI bus order, so "1" can mean different cards to the two - NVIDIA's CUDA
programming guide, "CUDA Environment Variables" (read through a search
result on 2026-09-24; docs.nvidia.com itself is blocked from where this was
written). CUDA_VISIBLE_DEVICES also accepts the id nvidia-smi prints
("GPU-8932f937-..."), and Ollama's own docs/gpu.mdx says "Numeric IDs may be
used, however ordering may vary, so UUIDs are more reliable" (read
2026-09-24). CUDA_DEVICE_ORDER=PCI_BUS_ID is set as well, belt and braces.

WHY TURING IS THE FLOOR (compute capability 7.5). MODEL-TOPOLOGY.md: llama.cpp
reaches the q8_0 cache only through its fused-attention path, and its fast
kernels need the Turing MMA path (GGML_CUDA_CC_TURING is 750). Everything this
module budgets assumes that cache. A Pascal card such as the Tesla P100
(6.0) passes Ollama's own gate and then takes the slow kernel, and has no
DP4A for quantised maths - see "If you are thinking about a second card".

THE EVERYDAY OLLAMA IS PINNED BY THE OWNER, NOT BY THIS MODULE. It must only
see the main card, or it may put the everyday model on the second one. This
module cannot and does not change another program's settings; it detects
(best effort) and hands the owner one PowerShell line (`pin_command`).

Standard library only. Never logs or returns a token or key.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

#: Every request here goes straight to the address, never through a proxy
#: (bug audit 3, CONN-1): see jarvis_local_http.py.
import jarvis_local_http

#: What a program Jarvis starts may inherit (bug audit 3, CONN-2).
import jarvis_child_env

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    import jarvis_compute as compute
except Exception:
    compute = None  # type: ignore


# --------------------------------------------------------------------------
#   Constants
# --------------------------------------------------------------------------

ACTION = "second_card_enable"
#: "Browser control" has its own action (AP-9). Every other switch only
#: starts a model on this PC; this one also lets Jarvis offer its browser
#: tool, which works real web pages on the internet. Its own action gives
#: it its own tier line in the toml and its own words on the lock-screen
#: notice (second-card.patch's _RISK line: "outbound"), instead of
#: borrowing second_card_enable's "nothing leaves this PC".
BROWSER_ACTION = "second_card_browser_enable"
HOST = "127.0.0.1"
DEFAULT_PORT = 11435
MAIN_OLLAMA_PORT = 11434

#: Turing. See the module docstring and MODEL-TOPOLOGY.md.
MIN_COMPUTE = 7.5
#: 10 GiB, as nvidia-smi reports memory.total (MiB).
MIN_TOTAL_MB = 10240
#: A card sold as "12 GB". 11.5 GiB rather than exactly 12,288 MiB, because
#: a card can report a little under its label; an 11 GB 2080 Ti (11,264 MiB)
#: stays below it. Since 2026-09-24 both sizes get the same lane (below);
#: the line is kept so a bigger plan for 12 GB can be put back in one place.
BIG_TOTAL_MB = 11776

# What the long-context lane holds, by the second card's memory.
#
# CHANGED 2026-09-24 (bug audit T3). This used to be Qwen 3 14B at 16K on a
# 12 GB card. The everyday model, jarvis-primary, also has 16,384 tokens of
# room (backend/jarvis-primary.Modelfile, num_ctx 16384), so a conversation
# too long for the main card was moved to a lane with NO more room, and was
# trimmed there exactly as it would have been at home. The lane is only
# worth having if it holds more than the main card, so 12 GB now gets what
# docs/HARDWARE-PROFILES.md section 4.4 gives a 12 GB long-context lane
# ("8 + 12 GB, monitor on the 12" and "12 + 12 GB": qwen3:8b, 32K), with
# the owner's 0.75 GB gap (section 5, decision 1):
#
#   KV per token, q8_0 = 2 (K and V) x layers x kv_heads x 128 x 1.0625 bytes
#     Qwen 3 8B : 2 x 36 x 8 x 128 x 1.0625 = 78,336 B   (section 2.8)
#
#   Qwen 3 8B Q4_K_M @ 32K: 4.67 + 2.39 + 0.30 = 7.36 GiB   (section 8.2's "need")
#                           (weights) (cache) (compute)
#   + 0.33 GiB CUDA start-up, which section 4.2 counts on the card's side
#   = 7.69 GiB, the figure the approval card shows.
#
#   room on the card, no monitor: total - 0.60 desktop - 0.33 - 0.75 gap
#     12 GB card (2060 12 GB)  10.32 GiB  -> 8B @ 32K (7.36), 2.96 spare
#     11 GB card (2080 Ti)      9.32 GiB  -> 8B @ 32K, 1.96 spare
#     10 GB card                8.32 GiB  -> 8B @ 32K, 0.96 spare
#
# Qwen 3 14B at 16K (10.10 needed) would fit a 12 GB card, but gives no more
# room than the main card; 14B at 32K (11.43) does not fit. Measure on the
# PC before changing this (HARDWARE-PROFILES section 4.7).
LONG_BIG = ("qwen3:8b", 32768, 7.69)
LONG_SMALL = ("qwen3:8b", 32768, 7.69)

# Pictures. NOT CHECKED against ollama.com: the library page could not be
# reached from where this was written (ollama.com and huggingface.co are
# blocked there). From the published Qwen2.5-VL-7B geometry as remembered -
# 28 layers, 4 KV heads, head size 128 - its cache is
#   2 x 28 x 4 x 128 x 1.0625 = 30,464 B a token (0.46 GiB at 16K, 0.93 at 32K),
# and the download is about 6 GB with the picture reader included (~5.59 GiB
# of weights, assumed). Plus 0.63 runtime, plus an unmeasured amount for
# reading an image. Treat VISION_WEIGHTS_GIB as a guess until
# `ollama show qwen2.5vl:7b` has been read on the PC.
VISION_MODEL = "qwen2.5vl:7b"
VISION_WEIGHTS_GIB = 5.59
VISION_KV_BYTES_PER_TOKEN = 30464
RUNTIME_GIB = 0.63

#: The five features, in the order both apps show them.
FEATURES = (
    {"id": "long_context", "name": "Longer conversations", "needs": [],
     "what": ("When a conversation grows past what the main card has room for, "
              "that answer is written on the second card, which has room for more of it.")},
    {"id": "vision", "name": "Pictures", "needs": [],
     "what": ("A message with a picture goes to a picture-reading model on the "
              "second card, on this PC, so Jarvis can see what you attached.")},
    {"id": "learning", "name": "Learning in the background", "needs": [],
     "what": ("Jarvis learns from your conversations on the second card, so it "
              "never slows the main card down and does not wait long for a pause.")},
    {"id": "browser_control", "name": "Browser control", "needs": ["long_context"],
     "what": ("Jarvis can work a web page for you in your browser, one approved step at a "
              "time, using the second card's extra room for long pages. The pages are on "
              "the internet: what it types or clicks there reaches that website.")},
    {"id": "wiki", "name": "Wiki builder", "needs": [],
     "what": ("Lets the wiki builder use the second card: documents you put in "
              "your vault's Jarvis Wiki/Sources folder become linked pages, each one "
              "after its own approval card.")},
)
FEATURE_IDS = tuple(f["id"] for f in FEATURES)
_BY_ID = {f["id"]: f for f in FEATURES}


@dataclass(frozen=True)
class Lane:
    """Where a feature's model calls go. `url` is always loopback."""
    url: str
    model: str
    num_ctx: int
    why: str


# --------------------------------------------------------------------------
#   Things the tests replace
# --------------------------------------------------------------------------

def _cards(fresh: bool = False) -> list:
    """jarvis_compute's reading of nvidia-smi (cached 30 s there)."""
    if compute is None:
        return []
    try:
        return compute.query_cards(fresh=fresh)
    except Exception:
        return []


def _primary(cards: list) -> tuple:
    if compute is None:
        return (cards[0], "it is the first card") if cards else (None, "no card")
    return compute.primary(cards)


def _smi_apps() -> Optional[str]:
    """nvidia-smi's list of processes using a card, or None."""
    if compute is None:
        return None
    try:
        return compute._run_smi(["--query-compute-apps=pid,process_name,gpu_uuid,used_memory",
                                 "--format=csv,noheader,nounits"])
    except Exception:
        return None


def _user_env(name: str) -> Optional[str]:
    """A variable from the Windows user environment (HKCU\\Environment),
    where `[Environment]::SetEnvironmentVariable(..., 'User')` puts it.
    None when not set or not Windows."""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            val, _ = winreg.QueryValueEx(k, name)
            return str(val) if val else None
    except Exception:
        return None


def _http_json(url: str, payload: Optional[dict] = None, timeout: float = 2.0):
    """GET (or POST `payload`) a loopback URL and return the JSON body.
    Raises on anything else - callers catch."""
    if not _is_loopback_url(url):
        raise ValueError("not a loopback address")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    # Never through a proxy: jarvis_local_http.py (bug audit 3, CONN-1).
    with jarvis_local_http.urlopen(req, timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _port_taken(port: int) -> bool:
    """Is anything listening on 127.0.0.1:<port>?"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((HOST, int(port))) == 0
    except Exception:
        return False
    finally:
        s.close()


_popen = subprocess.Popen
_which = shutil.which
_ON_WINDOWS = os.name == "nt"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-second-card", daemon=True).start()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _big_model():
    """jarvis_big_model, or None. Imported when asked, never at load."""
    try:
        import jarvis_big_model
        return jarvis_big_model
    except Exception:
        return None


def _claim_card(uuid: str) -> Optional[str]:
    """jarvis_compute.claim_card for this lane: None when the card is ours,
    else who holds it."""
    if compute is None or not hasattr(compute, "claim_card"):
        return None
    try:
        return compute.claim_card(uuid, "second_card")
    except Exception:
        return None


def _release_card(uuid: str) -> None:
    if compute is None or not uuid or not hasattr(compute, "release_card"):
        return
    try:
        compute.release_card(uuid, "second_card")
    except Exception:
        pass


def big_model_holds(uuid: str, name: str) -> Optional[str]:
    """Why the second Ollama must not start on this card because the big
    model (colibri, with [big_model] cuda = "on") is using it, in plain
    words; None when it is not. Reads only."""
    if not uuid:
        return None
    bm = _big_model()
    ec = None
    if bm is not None and hasattr(bm, "engine_card"):
        try:
            ec = bm.engine_card()
        except Exception:
            ec = None
    held = bool(ec and str(ec.get("uuid") or "").lower() == str(uuid).lower())
    if not held and compute is not None and hasattr(compute, "card_holder"):
        try:
            held = compute.card_holder(uuid) == "big_model"
        except Exception:
            held = False
    if not held:
        return None
    mins = (ec or {}).get("idle_minutes")
    after = (f"it stops after {mins} idle minutes" if mins
             else "it stops when it has been idle for a while")
    return f"the big model is using the {name}; {after}"


# --------------------------------------------------------------------------
#   Settings: the toml for how, a small file for the owner's switches
# --------------------------------------------------------------------------

def _cfg(key: str, default=None):
    if fw is None:
        return default
    try:
        return (fw.load_framework().get("second_card") or {}).get(key, default)
    except Exception:
        return default


def _config_dir() -> Path:
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def _state_path() -> Path:
    """The switches. Never the owner's toml: no route may write that."""
    return _config_dir() / "second-card.json"


def _log_path() -> Path:
    return _config_dir() / "second-card-ollama.log"


def _port() -> int:
    try:
        p = int(_cfg("port", DEFAULT_PORT))
    except (TypeError, ValueError):
        return DEFAULT_PORT
    return p if 1024 <= p <= 65535 and p != MAIN_OLLAMA_PORT else DEFAULT_PORT


def _keep_alive() -> str:
    v = str(_cfg("keep_alive", "30m") or "30m").strip()
    return v if re.fullmatch(r"-1|\d+[smh]?", v) else "30m"


def _flash_setting() -> str:
    v = str(_cfg("flash_attention", "auto") or "auto").strip().lower()
    return v if v in ("auto", "on", "off") else "auto"


def _flash_refusal() -> Optional[str]:
    """Why the lane must not start with this [second_card] flash_attention,
    or None. "off" cannot work with the lane's q8_0 cache: llama.cpp
    refuses to create the model's context ("quantized V cache requires
    flash_attn to be enabled", src/llama-context.cpp ~3737-3741, b11081 -
    docs/HARDWARE-PROFILES.md 2.2), so every model on the lane would fail
    to load. Refused here, in words, instead."""
    if _flash_setting() != "off":
        return None
    return ("[second_card] flash_attention is \"off\" in jarvis-framework.toml, which cannot "
            "work: the second copy of Ollama keeps the conversation in the compact q8_0 "
            "format, and llama.cpp refuses to load a model that way with flash attention "
            "off. Delete that line (or set it to \"auto\"), and the second card starts")


def _main_ollama_url() -> str:
    return (os.environ.get("OLLAMA_URL") or f"http://{HOST}:{MAIN_OLLAMA_PORT}").rstrip("/")


def _is_loopback_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in ("127.0.0.1", "localhost", "::1")


_STATE_LOCK = threading.RLock()


def _read_switches() -> dict:
    """{"master": bool, "features": {id: bool}}. A missing or broken file is
    everything off - the safe reading."""
    out = {"master": False, "features": {f: False for f in FEATURE_IDS}}
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    out["master"] = raw.get("master") is True
    feats = raw.get("features")
    if isinstance(feats, dict):
        for f in FEATURE_IDS:
            out["features"][f] = feats.get(f) is True
    return out


def _write_switch(feature: str, enabled: bool) -> Optional[str]:
    """Sets one switch. None on success, else the error in words."""
    with _STATE_LOCK:
        cur = _read_switches()
        if feature == "master":
            cur["master"] = bool(enabled)
        else:
            cur["features"][feature] = bool(enabled)
        p = _state_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"master": cur["master"], "features": cur["features"],
                                       "set_at": int(time.time())}, indent=1),
                           encoding="utf-8")
            tmp.replace(p)
        except OSError as exc:
            return f"could not save the switch ({type(exc).__name__})"
    return None


# --------------------------------------------------------------------------
#   Detection
# --------------------------------------------------------------------------

def _gb(total_mb: int) -> str:
    g = total_mb / 1024.0
    return f"{g:.0f} GB" if abs(g - round(g)) < 0.05 else f"{g:.1f} GB"


def _not_capable(card) -> Optional[str]:
    """Why this card cannot be the second card, in plain words, or None."""
    name = card.name
    cc = card.compute_cap
    if cc is None:
        return (f"Jarvis could not tell which generation the {name} is (this driver "
                f"does not report it), so it is treated as not capable")
    if cc < MIN_COMPUTE:
        extra = ""
        if "P100" in name.upper():
            extra = (" - the P100 in particular cannot run the compressed models Jarvis "
                     "uses at speed (docs/MODEL-TOPOLOGY.md, 'If you are thinking about "
                     "a second card')")
        return (f"the {name} is older than Turing (the RTX 20 generation, compute "
                f"capability 7.5), which the second-card features need{extra}")
    if card.total_mb < MIN_TOTAL_MB:
        return (f"the {name} has {_gb(card.total_mb)}, which is not enough: the "
                f"second-card features need at least 10 GB")
    if not card.uuid:
        return (f"nvidia-smi did not give the {name}'s id, and Jarvis only points work "
                f"at a card by its id")
    return None


def detect(fresh: bool = False) -> dict:
    """`detected` in status(). Never raises."""
    try:
        return _detect(fresh)
    except Exception as exc:
        return {"capable": False, "why": f"the graphics cards could not be read "
                                         f"({type(exc).__name__})",
                "primary": None, "second": None, "cards": [], "_second": None}


def _detect(fresh: bool) -> dict:
    cards = list(_cards(fresh))
    if not cards:
        return {"capable": False,
                "why": ("no NVIDIA graphics card could be read (nvidia-smi is missing "
                        "or did not answer)"),
                "primary": None, "second": None, "cards": [], "_second": None}
    prim, rule = _primary(cards)
    rows, candidates, reasons = [], [], []
    for c in sorted(cards, key=lambda d: d.index):
        if c is prim:
            continue
        r = _not_capable(c)
        if r is None:
            candidates.append(c)
        else:
            reasons.append((c, r))
    second = None
    if candidates:
        second = sorted(candidates, key=lambda d: (-d.total_mb, d.index))[0]
    for c in sorted(cards, key=lambda d: d.index):
        if c is prim:
            role, why = "primary", f"everyday chat runs here: {rule}"
        elif c is second:
            role, why = "second", "the second-card features would run here"
            if c.display_active:
                why += (" (a monitor is plugged into it, which uses some of its memory; "
                        "plug the monitors into the main card)")
        elif c in candidates:
            role, why = "unused", f"capable, but the {second.name} has more memory"
        else:
            role, why = "unused", next(r for (x, r) in reasons if x is c)
        rows.append({"index": c.index, "uuid": c.uuid or None, "name": c.name,
                     "total_mb": c.total_mb, "free_mb": c.free_mb,
                     "compute_cap": c.compute_cap, "display_active": c.display_active,
                     "role": role, "why": why})
    p = {"uuid": prim.uuid or None, "index": prim.index, "name": prim.name}
    if second is not None:
        s = {"uuid": second.uuid, "index": second.index, "name": second.name,
             "total_mb": second.total_mb, "compute_cap": second.compute_cap}
        why = (f"the {second.name} ({_gb(second.total_mb)}) can take the second-card "
               f"features; everyday chat stays on the {prim.name}")
        return {"capable": True, "why": why, "primary": p, "second": s, "cards": rows,
                "_second": second}
    if len(cards) == 1:
        why = f"only one graphics card found (the {prim.name})"
    else:
        why = "; ".join(r for (_, r) in reasons)
    return {"capable": False, "why": why, "primary": p, "second": None, "cards": rows,
            "_second": None}


def _long_context_plan(total_mb: int) -> tuple:
    """(model, num_ctx, memory_gib) for a second card with this much memory."""
    return LONG_BIG if total_mb >= BIG_TOTAL_MB else LONG_SMALL


def _vision_gib(num_ctx: int) -> float:
    kv = VISION_KV_BYTES_PER_TOKEN * num_ctx / 1024 ** 3
    return round(VISION_WEIGHTS_GIB + kv + RUNTIME_GIB, 2)


def _feature_model(feature: str, det: dict) -> tuple:
    """(model, num_ctx, memory_gib) - all None without a capable card."""
    second = det.get("_second")
    if second is None:
        return None, None, None
    model, ctx, gib = _long_context_plan(second.total_mb)
    if feature == "vision":
        return VISION_MODEL, ctx, _vision_gib(ctx)
    return model, ctx, gib


# --------------------------------------------------------------------------
#   Is the model there?
# --------------------------------------------------------------------------

_TAGS: dict = {}          # url -> (names, when)
_TAGS_SECONDS = 30.0


def _installed_names(url: str) -> Optional[set]:
    hit = _TAGS.get(url)
    now = time.monotonic()
    if hit and now - hit[1] < _TAGS_SECONDS:
        return hit[0]
    try:
        body = _http_json(f"{url}/api/tags", timeout=2.0)
        names = set()
        for m in body.get("models") or []:
            for k in ("name", "model"):
                if isinstance(m.get(k), str):
                    names.add(m[k])
    except Exception:
        return None
    _TAGS[url] = (names, now)
    return names


def _model_installed(model: Optional[str]) -> Optional[bool]:
    """Asks the second Ollama when it runs, else the everyday one (both read
    the same model folder). None: neither answered, or the everyday one is
    not on this PC (it is not asked then)."""
    if not model:
        return None
    url = _LANE.url() if _LANE.state == "running" else _main_ollama_url()
    if not _is_loopback_url(url):
        return None
    names = _installed_names(url)
    if names is None:
        return None
    want = {model, model + ":latest"} if ":" not in model else {model}
    return bool(want & names)


# --------------------------------------------------------------------------
#   The second Ollama
# --------------------------------------------------------------------------

def lane_env(uuid: str, *, port: int, num_ctx: int, host: str = HOST,
             base: Optional[dict] = None, flash: str = "auto",
             keep_alive: str = "30m") -> dict:
    """The environment for the second `ollama serve`. Raises ValueError for
    a host that is not 127.0.0.1 (rule 2) or an id that is not a card id.

    Built from an allowlist (jarvis_child_env.py, bug audit 3 CONN-2): what
    Windows needs to start a program, plus OLLAMA_MODELS if the owner set it
    (so the second Ollama finds the models already downloaded). Nothing else
    of Jarvis's environment - not the pairing token, not any other *_TOKEN,
    *_KEY, *_PASSWORD or *_SECRET - reaches the second Ollama."""
    if host != HOST:
        raise ValueError(f"the second Ollama only ever listens on {HOST}, not {host!r}")
    if not re.fullmatch(r"GPU-[0-9A-Fa-f-]{8,64}", str(uuid or "")):
        raise ValueError("the second Ollama is only pinned by a card id (GPU-...)")
    port = int(port)
    if not (1024 <= port <= 65535) or port == MAIN_OLLAMA_PORT:
        raise ValueError(f"port {port} cannot be used for the second Ollama")
    env = jarvis_child_env.inherited(base, names=("OLLAMA_MODELS",))
    # Inherited settings that would widen or reshape it are removed first.
    # (The allowlist above already leaves them out; kept, so a name added to
    # it later cannot quietly bring one back.)
    for k in ("OLLAMA_HOST", "OLLAMA_ORIGINS", "OLLAMA_SCHED_SPREAD",
              "OLLAMA_FLASH_ATTENTION", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES",
              "GPU_DEVICE_ORDINAL", "GGML_VK_VISIBLE_DEVICES"):
        env.pop(k, None)
    env.update({
        "OLLAMA_HOST": f"{HOST}:{port}",
        "CUDA_VISIBLE_DEVICES": uuid,
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "OLLAMA_KV_CACHE_TYPE": "q8_0",
        "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_CONTEXT_LENGTH": str(int(num_ctx)),
        "OLLAMA_KEEP_ALIVE": keep_alive,
        # Vulkan is on by default and ignores CUDA_VISIBLE_DEVICES: off, so
        # this Ollama sees the second card only (see the module docstring).
        "OLLAMA_VULKAN": "0",
    })
    if flash == "on":
        env["OLLAMA_FLASH_ATTENTION"] = "1"
    elif flash == "off":
        env["OLLAMA_FLASH_ATTENTION"] = "0"
    return env


def _version_at(port: int) -> Optional[dict]:
    try:
        v = _http_json(f"http://{HOST}:{port}/api/version", timeout=1.0)
        return v if isinstance(v, dict) and "version" in v else None
    except Exception:
        return None


class _LaneProcess:
    """One `ollama serve` that this module started, or none."""

    START_SECONDS = 30.0
    RETRY_SECONDS = 60.0

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.state = "off"
        self.why = "nothing on the second card is switched on"
        self.proc = None
        self.port = DEFAULT_PORT
        self.uuid = ""
        self.card = ""
        self.num_ctx = 0
        self.failed_at = -1e9
        self.gen = 0
        self.claimed = ""          # the card id whose claim this lane holds

    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def alive(self) -> bool:
        p = self.proc
        try:
            return p is not None and p.poll() is None
        except Exception:
            return False

    def ensure(self, uuid: str, card: str, num_ctx: int) -> None:
        with self.lock:
            port = _port()
            same = (self.uuid == uuid and self.num_ctx == num_ctx and self.port == port)
            if self.state in ("running", "starting") and same and self.alive():
                return
            if self.state == "running" and same and not self.alive():
                code = self._exit_code()
                self._clear()
                self._drop_card()
                self._fail(f"the second Ollama stopped by itself (exit code {code}); "
                           f"Jarvis will try again in a minute. Its log: {_log_path()}")
                return
            if self.state == "failed" and same and \
                    time.monotonic() - self.failed_at < self.RETRY_SECONDS:
                return
            if self.proc is not None:
                self._stop_proc()
            self._start(uuid, card, num_ctx, port)

    def _exit_code(self):
        try:
            return self.proc.poll()
        except Exception:
            return "unknown"

    def _clear(self) -> None:
        self.proc = None

    def _fail(self, why: str) -> None:
        self.state, self.why, self.failed_at = "failed", why, time.monotonic()

    def _drop_card(self) -> None:
        """Gives back the card's claim once no process of ours is on it."""
        card, self.claimed = self.claimed, ""
        _release_card(card)

    def hold(self, why: str) -> None:
        """Not started, and not a failure: something else (the big model)
        is using the card. Tried again on the next look."""
        with self.lock:
            if self.proc is not None:
                self._stop_proc()
            self.state, self.why = "off", why

    def _start(self, uuid: str, card: str, num_ctx: int, port: int) -> None:
        self.uuid, self.card, self.num_ctx, self.port = uuid, card, num_ctx, port
        exe = _which("ollama")
        if not exe:
            return self._fail("Ollama was not found on this PC's PATH, so the second "
                              "copy could not be started")
        if _port_taken(port) or _version_at(port) is not None:
            if _version_at(port) is not None:
                return self._fail(
                    f"something that answers like Ollama is already using {HOST}:{port}, "
                    f"and Jarvis did not start it, so Jarvis will neither use it nor stop "
                    f"it. Close it, or set another port under [second_card] in "
                    f"jarvis-framework.toml")
            return self._fail(f"another program is already using {HOST}:{port}; set "
                              f"another port under [second_card] in jarvis-framework.toml")
        refused = _flash_refusal()
        if refused:
            return self._fail(refused)
        try:
            env = lane_env(uuid, port=port, num_ctx=num_ctx, flash=_flash_setting(),
                           keep_alive=_keep_alive())
        except ValueError as exc:
            return self._fail(str(exc))
        # The card's claim, taken BEFORE the process starts. jarvis_big_model
        # takes the same claim before it starts colibri on this card, so the
        # two can never both be starting here, whatever the timing.
        if _claim_card(uuid) is not None:
            self.state = "off"
            self.why = (big_model_holds(uuid, card)
                        or f"the big model is starting on the {card}")
            return None
        self.claimed = uuid
        kwargs: dict = {"env": env, "stdin": subprocess.DEVNULL}
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
            # No console window, and its own group so stopping it is clean.
            kwargs["creationflags"] = 0x08000000 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        try:
            self.proc = _popen([exe, "serve"], **kwargs)
        except Exception as exc:
            self.proc = None
            self._drop_card()
            return self._fail(f"the second Ollama could not be started ({type(exc).__name__})")
        finally:
            if log is not None:
                try:
                    log.close()      # the child has its own handle
                except Exception:
                    pass
        self.gen += 1
        gen = self.gen
        self.state = "starting"
        self.why = (f"starting a second copy of Ollama on {HOST}:{port}, using only "
                    f"the {card}")
        _spawn(lambda: self._wait_healthy(gen))

    def _wait_healthy(self, gen: int) -> None:
        deadline = time.monotonic() + self.START_SECONDS
        while time.monotonic() < deadline:
            with self.lock:
                if gen != self.gen or self.state != "starting":
                    return
                if not self.alive():
                    code = self._exit_code()
                    self._clear()
                    self._drop_card()
                    return self._fail(f"the second Ollama stopped straight away (exit code "
                                      f"{code}). Its log: {_log_path()}")
            if _version_at(self.port) is not None:
                with self.lock:
                    if gen == self.gen and self.state == "starting":
                        self.state = "running"
                        self.why = (f"running on {HOST}:{self.port} (this PC only), using "
                                    f"only the {self.card}")
                return
            _sleep(0.5)
        with self.lock:
            if gen == self.gen and self.state == "starting":
                self._stop_proc()
                self._fail(f"the second Ollama did not answer within "
                           f"{self.START_SECONDS:.0f} seconds. Its log: {_log_path()}")

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

    def pids(self) -> set:
        """Our process and everything it started (for the pin check)."""
        p = self.proc
        if p is None or not self.alive():
            return set()
        return _tree(p.pid)


def _kill_tree(p) -> None:
    """Stops a process THIS module started, and what it started. Never
    called with any other process. Replaced in tests."""
    try:
        if os.name == "nt":
            # The whole tree of this one process: `ollama serve` starts a
            # runner per model, and stopping the parent alone would leave the
            # runner holding the card's memory.
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        else:
            import signal
            try:
                # Its own session (start_new_session=True), so this group
                # is exactly it and its children.
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                p.terminate()
        p.wait(timeout=10)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _tree(root: int) -> set:
    """`root` and its descendants. Best effort; {root} when unreadable."""
    parents: dict = {}
    try:
        if os.name == "nt":
            parents = _win_parents()
        else:
            for d in Path("/proc").iterdir():
                if d.name.isdigit():
                    try:
                        stat = (d / "stat").read_text()
                        ppid = int(stat[stat.rindex(")") + 2:].split()[1])
                        parents[int(d.name)] = ppid
                    except Exception:
                        continue
    except Exception:
        return {root}
    out, frontier = {root}, [root]
    while frontier:
        cur = frontier.pop()
        for pid, ppid in parents.items():
            if ppid == cur and pid not in out:
                out.add(pid)
                frontier.append(pid)
    return out


def _win_parents() -> dict:
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return {}
    out = {}
    try:
        e = PROCESSENTRY32()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = k32.Process32First(snap, ctypes.byref(e))
        while ok:
            out[int(e.th32ProcessID)] = int(e.th32ParentProcessID)
            ok = k32.Process32Next(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return out


_LANE = _LaneProcess()


def _wanted(sw: dict, det: dict) -> bool:
    return bool(sw["master"] and det.get("capable")
                and any(_feature_active(f, sw, det) for f in FEATURE_IDS))


def _feature_active(feature: str, sw: dict, det: dict) -> bool:
    return bool(det.get("capable") and sw["master"] and sw["features"].get(feature)
                and all(sw["features"].get(d) for d in _BY_ID[feature]["needs"]))


def _reconcile(sw: dict, det: dict) -> None:
    """Start the second Ollama if something needs it, stop it if nothing does.
    While Jarvis is on standby (sleep()), it starts nothing."""
    try:
        if _still_asleep():
            if _LANE.state != "off" or _LANE.proc is not None:
                _LANE.stop(_ASLEEP["why"])
            else:
                _LANE.why = _ASLEEP["why"]
            return
        if _wanted(sw, det):
            second = det["_second"]
            _, ctx, _ = _long_context_plan(second.total_mb)
            ours = (_LANE.state in ("starting", "running") and _LANE.uuid == second.uuid
                    and _LANE.alive())
            if not ours:
                # The big model (colibri with [big_model] cuda = "on") may be
                # on this very card. It will not start while this lane runs
                # (jarvis_big_model._cuda_plan); this is the other direction.
                held = big_model_holds(second.uuid, second.name)
                if held:
                    _LANE.hold(held)
                    return
            _LANE.ensure(second.uuid, second.name, ctx)
        elif _LANE.state != "off" or _LANE.proc is not None:
            if not det.get("capable"):
                why = f"no capable second card: {det.get('why')}"
            elif not sw["master"]:
                why = "the second-card switch is off"
            else:
                why = "nothing on the second card is switched on"
            _LANE.stop(why)
        else:
            _LANE.why = ("nothing on the second card is switched on"
                         if det.get("capable") else f"no capable second card: {det.get('why')}")
    except Exception as exc:
        _LANE.state, _LANE.why = "failed", f"unexpected error ({type(exc).__name__})"


# --------------------------------------------------------------------------
#   Standby: the second card is freed too
# --------------------------------------------------------------------------
#
# Standby (jarvis_power_switch.py) promises to free the graphics card. With
# two cards that has to mean both: sleep() stops the second Ollama, which
# frees everything it held on that card, CUDA's own share included.
#
# It then has to STAY stopped. Both apps read GET /api/second-card every few
# seconds, and status() reconciles - so without this flag the next poll
# started the lane again, and standby freed the card for a few seconds.
# It wakes the way the main model does, "on demand": the next time the owner
# actually uses a second-card feature (lane_for), or when Jarvis leaves
# standby. Background learning is not the owner using it, so it does not
# wake the card; it waits, like the rest of Jarvis's own background work.

_ASLEEP = {"on": False, "why": ""}
_ASLEEP_LOCK = threading.Lock()
#: Features that run in the background on Jarvis's own schedule. They never
#: wake the card from standby.
_BACKGROUND = frozenset({"learning"})


def sleep(why: str = "Jarvis is on standby") -> dict:
    """Stop the second Ollama and keep it stopped until it is really needed
    or Jarvis leaves standby. {"stopped": bool, "sentence": str}. Never raises."""
    try:
        with _ASLEEP_LOCK:
            _ASLEEP.update(on=True, why=f"asleep: {why}")
        running = _LANE.state != "off" or _LANE.proc is not None
        if running:
            _LANE.stop(_ASLEEP["why"])
        _audit("second_card.sleep", {"stopped": running})
        return {"stopped": running,
                "sentence": "The second graphics card was freed too." if running else ""}
    except Exception as exc:
        return {"stopped": False,
                "sentence": f"Could not stop the second graphics card ({type(exc).__name__})."}


def wake() -> None:
    """Allow the second Ollama to start again. It starts only when something
    needs it. Never raises."""
    with _ASLEEP_LOCK:
        _ASLEEP.update(on=False, why="")


def asleep() -> bool:
    return bool(_ASLEEP["on"])


def _still_asleep() -> bool:
    """Asleep, unless Jarvis has left standby since - then wake by itself.
    A power module that cannot be read leaves it asleep: the safe direction
    for a promise to keep the card free."""
    if not _ASLEEP["on"]:
        return False
    try:
        import jarvis_power
        if str(jarvis_power.current()) != "standby":
            wake()
            return False
    except Exception:
        pass
    return True


def lane_state() -> str:
    """"off", "starting", "running" or "failed": the second Ollama's state as
    last seen. Reads only; starts and stops nothing. jarvis_big_model.py asks
    this before it would put colibri on the second card (it will not while
    this lane is starting or running)."""
    try:
        return str(_LANE.state)
    except Exception:
        return "unknown"


def shutdown() -> None:
    """Stops the second Ollama if this module started it. At process exit."""
    try:
        _LANE.stop("Jarvis is shutting down")
    except Exception:
        pass


atexit.register(shutdown)


# --------------------------------------------------------------------------
#   lane_for - the one call the rest of the backend makes
# --------------------------------------------------------------------------

def lane_for(feature: str) -> Optional[Lane]:
    """Where `feature`'s model calls go, or None to carry on exactly as
    before. Never raises."""
    try:
        if feature not in _BY_ID:
            return None
        sw = _read_switches()
        # The cheap checks first: with the switches off (the default) this
        # reads one small file and returns, on every chat turn.
        if not sw["master"] or not sw["features"].get(feature):
            return None
        if not all(sw["features"].get(d) for d in _BY_ID[feature]["needs"]):
            return None
        if _ASLEEP["on"]:
            if feature in _BACKGROUND:
                return None     # Jarvis's own background work does not wake the card
            wake()              # the owner is using it: wake on demand
        det = detect()
        _reconcile(sw, det)
        if not det.get("capable") or _LANE.state != "running":
            return None
        model, ctx, _ = _feature_model(feature, det)
        if not model or _model_installed(model) is not True:
            return None
        url = _LANE.url()
        if not _is_loopback_url(url):
            return None
        return Lane(url=url, model=model, num_ctx=int(ctx),
                    why=f"{_BY_ID[feature]['name']}: {model} on the {det['_second'].name}")
    except Exception:
        return None


#: After the learning lane fails to answer, how long the learner goes back
#: to exactly what it did before this module: the main card, after the full
#: quiet wait (K13).
LEARN_RETRY_SECONDS = 600.0
_LEARN: dict = {"failed_at": -1e9, "short": False}


def _learning_lane() -> Optional[Lane]:
    """lane_for("learning"), unless it failed to answer in the last
    LEARN_RETRY_SECONDS."""
    if time.monotonic() - _LEARN["failed_at"] < LEARN_RETRY_SECONDS:
        return None
    return lane_for("learning")


def learning_idle_seconds(default: float) -> float:
    """How long the learner waits for a quiet spell. With the learner on the
    second card it no longer competes with chat, so a short pause is enough
    (10 s, never longer than it already was). Not while the lane has lately
    failed to answer: then the pass will run on the main card, which needs
    the full wait."""
    try:
        if _learning_lane() is not None:
            _LEARN["short"] = float(default) > 10.0
            return min(float(default), 10.0)
    except Exception:
        pass
    _LEARN["short"] = False
    return default


def generate(lane: Lane, prompt: str, *, timeout: float = 120.0) -> Optional[str]:
    """One non-streamed answer from the lane's model, or None. Loopback only.
    num_ctx matches the lane's OLLAMA_CONTEXT_LENGTH, so asking never makes
    Ollama reload the model at a different size."""
    if lane is None or not _is_loopback_url(lane.url):
        return None
    body = {"model": lane.model, "prompt": prompt, "stream": False, "think": False,
            "options": {"num_ctx": int(lane.num_ctx), "temperature": 0}}
    for attempt in (1, 2):
        try:
            out = _http_json(f"{lane.url}/api/generate", body, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if attempt == 1 and exc.code == 400 and "think" in body:
                body.pop("think", None)     # an Ollama or model without the field
                continue
            return None
        except Exception:
            return None
        text = out.get("response") if isinstance(out, dict) else None
        if not isinstance(text, str):
            return None
        return re.sub(r"(?s)<think>.*?</think>", "", text).strip()
    return None


def _skip_pass(prompt: str) -> Optional[str]:
    return None


def _say_skipped() -> None:
    print("  ! learning: the second card did not answer, so this pass was skipped rather "
          "than run on the main card after only a short pause. The next passes use the "
          "main card after the full wait; the second card is tried again in "
          f"{LEARN_RETRY_SECONDS / 60:.0f} minutes. What was said is looked at again on the "
          "pass after your next message.", file=sys.stderr)


def learning_llm(llm: Callable[[str], Optional[str]]) -> Callable[[str], Optional[str]]:
    """The learner's model call, moved to the second card when the
    "learning" feature is working there; `llm` itself otherwise.

    If the second card does not answer, and this pass waited only the short
    pause (learning_idle_seconds), the pass is SKIPPED - `llm` is not called
    - because the main card was never given the full quiet it needs (K13:
    it used to fall back to the main card after 10 seconds). For the next
    LEARN_RETRY_SECONDS the learner then does exactly what it did before
    this module existed: the full wait, then `llm`."""
    short, _LEARN["short"] = _LEARN["short"], False
    try:
        lane = _learning_lane()
    except Exception:
        lane = None
    if lane is None:
        if short:
            # The pause was shortened for a lane that is gone now.
            _say_skipped()
            return _skip_pass
        return llm

    def ask(prompt: str) -> Optional[str]:
        out = generate(lane, prompt)
        if out is not None:
            return out
        first = time.monotonic() - _LEARN["failed_at"] >= LEARN_RETRY_SECONDS
        _LEARN["failed_at"] = time.monotonic()
        if short:
            if first:
                _say_skipped()
            return None
        return llm(prompt)
    return ask


# --------------------------------------------------------------------------
#   Is the everyday Ollama kept off the second card?
# --------------------------------------------------------------------------

_UUID_RE = re.compile(r"GPU-[0-9A-Fa-f-]{8,64}")


def pin_command(primary_uuid: Optional[str]) -> Optional[str]:
    """One PowerShell line (5.1-safe) that pins the owner's everyday Ollama
    to the main card. None without a real card id.

    Two settings: CUDA_VISIBLE_DEVICES (only the main card, by its id) and
    OLLAMA_VULKAN=0, because Ollama's Vulkan route is on by default and does
    not read CUDA_VISIBLE_DEVICES - without it the everyday Ollama could still
    reach the second card (docs/HARDWARE-PROFILES.md, decision 3)."""
    if not primary_uuid or not _UUID_RE.fullmatch(primary_uuid):
        return None
    return ("[Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', "
            f"'{primary_uuid}', 'User'); "
            "[Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', '0', 'User'); "
            "Write-Host 'Done. Now quit Ollama (right-click "
            "its icon by the clock, then Quit Ollama) and start it again from the Start "
            "menu. Nothing was written to any file.'")


def main_pin(det: dict) -> tuple:
    """(true | false | None, one sentence). Best effort, never raises."""
    try:
        return _main_pin(det)
    except Exception as exc:
        return None, f"Could not check ({type(exc).__name__})."


def _main_pin(det: dict) -> tuple:
    prim = det.get("primary")
    cards = det.get("cards") or []
    if not prim or not cards:
        return None, "No graphics card could be read, so there is nothing to check."
    if len(cards) < 2:
        return None, "Only one graphics card, so there is nothing to keep apart yet."
    prim_uuid = (prim.get("uuid") or "").lower()
    others = {(c.get("uuid") or "").lower(): c.get("name") for c in cards
              if c.get("role") != "primary" and c.get("uuid")}
    ours = _LANE.pids()
    text = _smi_apps()
    if text:
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            pname = parts[1].lower()
            gpu = parts[2].lower()
            if ("ollama" in pname or "llama" in pname) and gpu in others and pid not in ours:
                return False, (f"The everyday Ollama is using the {others[gpu]} right now, so "
                               f"it can take memory the second-card features need. Run the "
                               f"command below, then restart Ollama.")
    val = _user_env("CUDA_VISIBLE_DEVICES")
    if val is not None:
        if val.strip().lower() == prim_uuid and prim_uuid:
            vulkan = (_user_env("OLLAMA_VULKAN") or "").strip()
            if vulkan != "0":
                # CUDA_VISIBLE_DEVICES hides the second card from Ollama's
                # CUDA route only. Its Vulkan route (on by default, see
                # lane_env) can still put a model there - which is why the
                # command below now sets OLLAMA_VULKAN=0 as well. An owner who
                # ran the older one-setting command must not be told "pinned".
                return False, (f"Ollama's CUDA route is pinned to the {prim.get('name')}, "
                               f"but its Vulkan route is still on and can still use the "
                               f"second card. Run the command below (it now switches "
                               f"Vulkan off too), then restart Ollama.")
            return True, (f"Ollama is set to use only the {prim.get('name')} "
                          f"(CUDA_VISIBLE_DEVICES in your user settings). If you set it "
                          f"just now, quit Ollama and start it again.")
        return False, (f"CUDA_VISIBLE_DEVICES in your user settings is {val.strip()!r}, "
                       f"which is not the {prim.get('name')}'s id. Run the command below.")
    if _ON_WINDOWS:
        return False, ("The everyday Ollama is not pinned: it can see both cards and may put "
                       "models on the second one. Run the command below once, then restart "
                       "Ollama.")
    return None, "Could not tell from here (this check reads Windows' user settings)."


# --------------------------------------------------------------------------
#   status()
# --------------------------------------------------------------------------

def _feature_row(f: dict, sw: dict, det: dict, lane_state: str, lane_why: str,
                 pending: list) -> dict:
    fid = f["id"]
    enabled = bool(sw["features"].get(fid))
    active = _feature_active(fid, sw, det)
    model, ctx, gib = _feature_model(fid, det)
    installed = _model_installed(model) if model else None
    available = bool(active and lane_state == "running" and installed is True)
    missing = [d for d in f["needs"] if not sw["features"].get(d)]
    names = ", ".join(_BY_ID[d]["name"] for d in missing)
    if not det.get("capable"):
        if enabled:
            why = (f"On, but it cannot run: {det['why']}. Your choice is kept; it works "
                   f"again once a capable second card is back.")
        else:
            why = f"Needs a capable second graphics card: {det['why']}."
    elif not enabled:
        why = "Off."
        if fid in pending:
            why = "Off. A card to turn it on is waiting for your answer."
        elif missing:
            why += f" Needs {names} on first."
    elif not sw["master"]:
        why = "On, but the main second-card switch is off."
    elif missing:
        why = f"On, but it needs {names} to be on as well."
    elif lane_state != "running":
        why = f"On. The second copy of Ollama is {lane_state}: {lane_why}."
    elif installed is None:
        why = f"On, but Jarvis could not ask Ollama whether {model} is installed."
    elif installed is False:
        why = (f"On, but {model} is not installed yet. Install it (Brain, Models, or "
               f"'ollama pull {model}' in a terminal) and it starts working.")
    else:
        why = (f"Working: {model} on the {det['second']['name']}, with room for "
               f"{ctx:,} tokens of conversation.")
    return {"id": fid, "name": f["name"], "what": f["what"], "enabled": enabled,
            "active": active, "available": available, "needs": list(f["needs"]),
            "model": model, "model_installed": installed,
            "memory_gib": gib, "why": why}


def status() -> dict:
    """GET /api/second-card. No token, no key, no secret in it: card ids are
    hardware ids. Never raises."""
    sw = _read_switches()
    det = detect()
    _reconcile(sw, det)
    lane_state, lane_why = _LANE.state, _LANE.why
    with _PENDING_LOCK:
        pending = [f for f in ("master",) + FEATURE_IDS
                   if f in _PENDING and not _PENDING[f].get("withdrawn")]
        last = dict(_LAST_ANY) or None
    feats = [_feature_row(f, sw, det, lane_state, lane_why, pending) for f in FEATURES]
    pinned, note = main_pin(det)
    prim = det.get("primary") or {}
    cmd = pin_command(prim.get("uuid")) if len(det.get("cards") or []) >= 2 else None
    detected = {k: det[k] for k in ("capable", "why", "primary", "second", "cards")}
    return {
        "detected": detected,
        "enabled": sw["master"],
        "active": bool(sw["master"] and det.get("capable")),
        "pending": pending,
        "lane": {"state": lane_state, "why": lane_why},
        "main_ollama_pinned": pinned,
        "pin_note": note,
        "pin_command": cmd,
        "features": feats,
        # How the last approval card ended (AP-6): {feature, outcome, why,
        # at}, or null when none has ended since Jarvis started.
        "last": last,
    }


# --------------------------------------------------------------------------
#   Changing a switch
# --------------------------------------------------------------------------

_PENDING_LOCK = threading.Lock()
_PENDING: dict = {}        # feature -> {"id", "since", "withdrawn"}
_LAST: dict = {}           # feature -> how its last card ended
#: Every card switched off while it waited and not yet answered, by its id.
#: A SET, not a flag on _PENDING: a new ON replaces _PENDING[feature], and
#: the flag went with it - after two ON/OFF rounds, approving the FIRST
#: card turned the switch on although the owner's last word was OFF.
_WITHDRAWN: set = set()
#: The last card to end, whichever switch it was for: status()["last"].
_LAST_ANY: dict = {}


def _last_words(label: str, outcome: str, reason: str) -> str:
    """How the last card ended, in words the apps can show as they are.
    `outcome` is one of: enabled, denied, timed_out, refused, failed,
    withdrawn (timed_out is jarvis_gate's own word for a card nobody
    answered in time)."""
    reason = str(reason or "").strip().rstrip(".")
    if outcome == "enabled":
        return f"{label} was turned on."
    if outcome == "denied":
        return f"You said no, so {label} stays off."
    if outcome == "timed_out":
        return f"Nobody answered the card in time, so {label} stays off."
    if outcome == "withdrawn":
        return (f"You turned {label} off while its card was waiting, so approving that "
                f"card changed nothing.")
    if outcome == "failed":
        return f"{label} could not be turned on: {reason or 'an unexpected error'}."
    return f"{label} was not turned on: {reason or 'refused'}."


def _tier(action: str) -> str:
    return str(fw.action_tier(action)) if fw is not None else "unknown"


def action_for(feature: str) -> str:
    """The gate action a switch's ON card is raised under."""
    return BROWSER_ACTION if feature == "browser_control" else ACTION


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _shares_with_big_model() -> str:
    """One line for the card when the big model may use this card too, or
    ""."""
    bm = _big_model()
    try:
        on = bm is not None and bm._cuda_setting() == "on"
    except Exception:
        on = False
    if not on:
        return ""
    return ("\n\nThe big model is set to use this card too ([big_model] cuda = \"on\"). "
            "They never share it: while the big model is using the card, this waits "
            "until it stops.")


def _would_work(feature: str, sw: dict) -> list:
    """The features that are working once `feature` is turned on, given the
    owner's other switches as they are - every choice is kept while the
    main switch or a feature it needs is off, so approving one card can
    bring back others. In the apps' order."""
    after = {"master": sw["master"], "features": dict(sw["features"])}
    if feature == "master":
        after["master"] = True
    else:
        after["features"][feature] = True
    ok = {"capable": True}
    return [f for f in FEATURE_IDS if _feature_active(f, after, ok)]


def _brings_browser(feature: str, sw: dict) -> bool:
    """Does saying yes to `feature`'s card start "Browser control" working
    (it was not before)? Then the card must not say nothing leaves."""
    return ("browser_control" in _would_work(feature, sw)
            and not _feature_active("browser_control", sw, {"capable": True}))


def _names(ids: list) -> str:
    names = [f"\"{_BY_ID[i]['name']}\"" for i in ids]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def describe_on(feature: str, det: dict, sw: Optional[dict] = None) -> str:
    """The approval card. Every word from here; what refusing costs is on it.
    It says exactly what starts if the owner says yes (AP-4)."""
    sw = sw if sw is not None else _read_switches()
    s = det["second"]
    p = det.get("primary") or {}
    card = f"the {s['name']} ({_gb(s['total_mb'])}, id {s['uuid']})"
    lane = (f"Jarvis starts a second copy of Ollama that uses only that card and "
            f"listens on {HOST}:{_port()} - this PC only, not your network or the "
            f"internet.")
    if _brings_browser(feature, sw):
        # AP-9: not "Nothing leaves this PC". The model stays here; the
        # browser tool it offers works real web pages.
        lane += (" \"Browser control\" also lets Jarvis offer to work web pages in your "
                 "browser: those pages are on the internet, so what it types or clicks "
                 "there reaches that website. Each thing it would do there is shown to you "
                 "on its own card first.")
    else:
        lane += " Nothing leaves this PC."
    lane += _shares_with_big_model()
    if feature == "master":
        back = _would_work("master", sw)
        if back:
            yes = (f"If you say yes: {_names(back)} start{'s' if len(back) == 1 else ''} "
                   f"working again at once - you left "
                   f"{'it' if len(back) == 1 else 'them'} switched on. {lane} Every other "
                   "feature stays off; each has its own switch and its own card.")
        else:
            yes = ("If you say yes: nothing starts yet. Each feature (Longer conversations, "
                   "Pictures, Learning in the background, Browser control, Wiki builder) has "
                   f"its own switch and its own card. Once one of them is on, {lane}")
        return (
            "Let Jarvis use the second graphics card?\n\n"
            f"Which card: {card}.\n\n"
            f"{yes}\n\n"
            "If you did not just ask for this, say no.\n\n"
            f"If you say no: nothing changes. Everything keeps running on the "
            f"{p.get('name', 'main card')}.")
    f = _BY_ID[feature]
    model, ctx, gib = _feature_model(feature, det)
    mem = (f"about {gib:.1f} GB of the card's {_gb(s['total_mb'])}"
           + (" (an estimate: the picture model's size was not checked)"
              if feature == "vision" else ""))
    installed = _model_installed(model)
    inst = ""
    if installed is False:
        inst = (f"\n\n{model} is not installed yet. The switch will be on, but the "
                f"feature waits until it is installed.")
    ok = {"capable": True}
    also = [x for x in _would_work(feature, sw)
            if x != feature and not _feature_active(x, sw, ok)]
    if also:
        one = len(also) == 1
        inst += (f"\n\nAlso: {_names(also)} {'is' if one else 'are'} still switched on from "
                 f"before, so {'it starts' if one else 'they start'} working again too, "
                 f"at once.")
    return (
        f"Turn on \"{f['name']}\" on the second graphics card?\n\n"
        f"What it does: {f['what']}\n\n"
        f"Which card: {card}.\n"
        f"Which model: {model}, with room for {ctx:,} tokens - {mem}.\n\n"
        f"{lane}{inst}\n\n"
        "If you did not just ask for this, say no.\n\n"
        "If you say no: nothing changes. This keeps working the way it does today, on "
        f"the {p.get('name', 'main card')}.")


def _finish(feature: str, pid: str, outcome: str, reason: str = "",
            request_id=None) -> None:
    with _PENDING_LOCK:
        if feature in _PENDING and _PENDING[feature]["id"] == pid:
            del _PENDING[feature]
        _WITHDRAWN.discard(pid)
        _LAST[feature] = {"outcome": outcome, "reason": reason[:200]}
        label = ("The second graphics card" if feature == "master"
                 else f"\"{_BY_ID[feature]['name']}\"" if feature in _BY_ID else feature)
        _LAST_ANY.clear()
        _LAST_ANY.update(feature=feature, outcome=outcome,
                         why=_last_words(label, outcome, reason[:200]), at=int(time.time()))
    _audit("second_card.decided", {"feature": feature, "outcome": outcome,
                                   **({"request_id": request_id} if request_id else {})})


def _decide(feature: str, pid: str, gate: Callable, tier_of: Callable) -> None:
    """Raise the card, wait for the answer, act on it. Runs on its own thread."""
    det = detect()
    if not det.get("capable"):
        return _finish(feature, pid, "refused", det.get("why", ""))
    text = describe_on(feature, det)
    model, ctx, gib = _feature_model(feature, det) if feature != "master" else (None, None, None)
    web = _brings_browser(feature, _read_switches())
    detail = {"text": text, "what": f"turn on the second graphics card: {feature}",
              "feature": feature, "card": det["second"]["name"],
              "card_id": det["second"]["uuid"], "model": model, "memory_gib": gib,
              "listens_on": f"{HOST}:{_port()}", "leaves_this_pc": web}
    try:
        v = gate(action_for(feature), detail, text)
    except Exception as exc:
        return _finish(feature, pid, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return _finish(feature, pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes",
                       rid)
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(feature, pid, outcome, "", rid)
        return _finish(feature, pid, "refused", str(getattr(v, "reason", "refused")), rid)
    with _PENDING_LOCK:
        withdrawn = pid in _WITHDRAWN
    if withdrawn:
        return _finish(feature, pid, "withdrawn",
                       "you turned it off while the card was waiting", rid)
    if feature != "master":
        # Checked again now, not only when the card went up: the main switch
        # (or a feature this one needs) may have been turned off meanwhile.
        cur = _read_switches()
        if not cur["master"]:
            return _finish(feature, pid, "refused",
                           "the main second-card switch was turned off while the card "
                           "waited", rid)
        gone = [d for d in _BY_ID[feature]["needs"] if not cur["features"].get(d)]
        if gone:
            return _finish(feature, pid, "refused",
                           f"it needs {_names(gone)}, which was turned off while the card "
                           f"waited", rid)
    if not detect(fresh=True).get("capable"):
        return _finish(feature, pid, "refused", "the second card is not there any more", rid)
    err = _write_switch(feature, True)
    if err:
        return _finish(feature, pid, "failed", err, rid)
    _finish(feature, pid, "enabled", "", rid)
    _reconcile(_read_switches(), detect())


def request_change(feature: str, enabled: bool, *, gate: Optional[Callable] = None,
                   tier_of: Optional[Callable[[str], str]] = None,
                   spawn: Optional[Callable] = None) -> tuple:
    """POST /api/second-card. Returns (http code, body).

    OFF: at once, no card. ON: one approval card, and this returns straight
    away - `pending: true` means a card is up, NOT that it is on."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if feature != "master" and feature not in _BY_ID:
        return 400, {"error": f"there is no second-card feature called {str(feature)[:40]!r}"}
    if not isinstance(enabled, bool):
        return 400, {"error": "\"enabled\" must be true or false"}
    label = "The second graphics card" if feature == "master" else f"\"{_BY_ID[feature]['name']}\""

    if not enabled:
        with _PENDING_LOCK:
            if feature in _PENDING:
                _PENDING[feature]["withdrawn"] = True
                _WITHDRAWN.add(_PENDING[feature]["id"])
        err = _write_switch(feature, False)
        if err:
            return 500, {"error": err}
        _audit("second_card.off", {"feature": feature})
        _reconcile(_read_switches(), detect())
        return 200, {"ok": True, "enabled": False, "pending": False,
                     "message": f"{label} is off."}

    sw = _read_switches()
    already = sw["master"] if feature == "master" else sw["features"].get(feature)
    if already:
        return 200, {"ok": True, "enabled": True, "pending": False,
                     "message": f"{label} is already on."}
    with _PENDING_LOCK:
        p = _PENDING.get(feature)
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": (f"a card to turn on {label} is already waiting - "
                                   f"approve or deny that one")}
    det = detect(fresh=True)
    if not det.get("capable"):
        return 503, {"error": f"{label} cannot be turned on: {det.get('why')}."}
    if feature != "master":
        if not sw["master"]:
            return 400, {"error": "Turn on the second graphics card itself first "
                                  "(the main switch), then this one."}
        missing = [d for d in _BY_ID[feature]["needs"] if not sw["features"].get(d)]
        if missing:
            names = ", ".join(f"\"{_BY_ID[d]['name']}\"" for d in missing)
            return 400, {"error": f"{label} needs {names} on first."}
    if feature != "master" or any(sw["features"].values()):
        # This ON would start the second Ollama. Not while the big model is
        # on the card: the approval would turn on something that cannot run.
        held = big_model_holds(det["second"]["uuid"], det["second"]["name"])
        if held:
            return 409, {"error": f"Not now: {held}."}
    action = action_for(feature)
    try:
        tier = tier_of(action)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        # Checked BEFORE a card is raised: a card that could not end in a
        # person deciding should not be raised at all.
        return 503, {"error": (f"{action} is tier {tier!r} in jarvis-framework.toml; "
                               f"turning this on needs a person to say yes, so it must "
                               f"be 'ask'")}
    pid = _uuid.uuid4().hex
    with _PENDING_LOCK:
        p = _PENDING.get(feature)
        if p is not None and not p.get("withdrawn"):
            return 409, {"error": f"a card to turn on {label} is already waiting"}
        _PENDING[feature] = {"id": pid, "since": time.time(), "withdrawn": False}
    _audit("second_card.asked", {"feature": feature})

    def work() -> None:
        try:
            _decide(feature, pid, gate, tier_of)
        except Exception:
            _finish(feature, pid, "failed", "unexpected error")

    try:
        spawn(work)
    except Exception:
        _finish(feature, pid, "failed", "could not start")
        return 503, {"error": "could not raise the approval card"}
    return 200, {"ok": True, "enabled": False, "pending": True,
                 "message": ("Approve the card on your PC or phone to turn it on. "
                             "Nothing changes until you do.")}


def handle_post(body) -> tuple:
    """The route's body: {"feature": "...", "enabled": true|false}."""
    if not isinstance(body, dict):
        return 400, {"error": "send {\"feature\": \"...\", \"enabled\": true or false}"}
    return request_change(str(body.get("feature") or ""), body.get("enabled"))


def _reset_for_tests() -> None:
    global _LANE
    with _PENDING_LOCK:
        _PENDING.clear()
        _LAST.clear()
        _WITHDRAWN.clear()
        _LAST_ANY.clear()
    _TAGS.clear()
    _LEARN.update(failed_at=-1e9, short=False)
    wake()
    try:
        _LANE.stop("reset")
    except Exception:
        pass
    _LANE = _LaneProcess()


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
