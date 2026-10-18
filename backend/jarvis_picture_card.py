"""jarvis_picture_card.py - "which card draws the pictures, and what the chat
does about it".

THE OWNER'S THREE WAYS TO TRY IT (2026-10-10). Both cards are Turing and the
everyday conversation already fills the 12 GB card, so the picture-maker has
to share. The owner named three arrangements and wants to try each one and
compare them, so all three live here as switches, each OFF until he turns
*that* one on (CLAUDE.md: a feature that uses the second card keeps its own
switch, off until that feature is measured):

  A  "Pictures on the 12 GB card - the chat steps aside while one is drawn"
     The picture-maker gets the 12 GB card (the RTX 2060). The everyday chat
     is UNLOADED first and warmed back afterwards, so only one of them is on
     the card at a time - which is what keeps the owner's 196,608-token
     everyday conversation. This is the owner's recorded preference.

  B  "Pictures on the 12 GB card - the chat moves to the 8 GB card"
     The picture-maker gets the 12 GB card and the everyday chat MOVES to the
     8 GB card (the RTX 2080 Super) and stays resident, so both are up at
     once. The price is the conversation: the chat can then only hold what the
     8 GB card holds with no spill. `largest_context_with_no_spill` measures
     that number instead of guessing it.

  C  "Small pictures on the 8 GB card - the chat is left alone"
     The small picture model gets the 8 GB card and the everyday chat is not
     touched at all: same port, same card, same long conversation.

WHAT THIS MODULE DOES NOT DO, AND WHY THAT IS NOT A GAP

It does not draw anything and it owns no route under /api/pictures. Asking for
a picture, saving it and listing it are jarvis_pictures.py's job (JARVIS-API
section 123). This module answers the one question that module deliberately
leaves alone: WHICH CARD, launched how, and whether the chat has to move. Its
own routes live under /api/picture-card so the two can never fight over a
prefix, and a test fails if this module ever grows a route under /api/pictures.

HOW THE CARD IS ACTUALLY PINNED (the mistake this project already made)

  * ``CUDA_VISIBLE_DEVICES`` alone does NOT pin a card for Ollama - it silently
    falls back to its Vulkan engine and lands on the other card. This module
    never pins Ollama; the lanes are started by jarvis_second_card.py, which
    sets OLLAMA_VULKAN=0 as well. Where this module does start something, it
    passes the card the way THAT program takes it.
  * For ComfyUI the card is pinned twice over: ``CUDA_VISIBLE_DEVICES`` set to
    the card's UUID, AND ``--cuda-device 0`` (its own flag, whose argument is
    the index among the *visible* devices, so 0 is the one card we exposed).
  * The card is always found by asking nvidia-smi and ranking by real memory,
    never by assuming an index - the two cards' order is not guaranteed.

WHAT IT REFUSES TO PRETEND

  * With no option on, every route says so in one plain sentence and names all
    three. Nothing is started, nothing is unloaded.
  * If the picture-maker's files or its runtime are not on this PC, the answer
    says exactly what is missing rather than half-working.
  * ``nothing_measured`` is in every status answer until a real run has been
    recorded, and the words say "not measured yet" - this project has already
    been bitten once by numbers that came from two models on one card.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore


# --------------------------------------------------------------------------
#   The three ways, in the owner's own words
# --------------------------------------------------------------------------

#: 12 GB and 8 GB, in MiB, are what the two cards report. A card is called
#: "big" or "small" by its own reported memory, never by its index.
BIG_CARD_MB = 11776
SMALL_CARD_MB = 7680

OPTIONS: tuple = (
    {
        "id": "A",
        "key": "pictures_on_big_card_chat_steps_aside",
        "name": "Pictures on the 12 GB card, the chat steps aside while one is drawn",
        "detail": ("The picture-maker and the everyday chat take turns on the 12 GB card. "
                   "Your long everyday conversation is kept. Drawing waits a few seconds while "
                   "the chat steps aside, and the chat reloads after."),
        "card": "big",
        "chat": "steps_aside",
        "model": "big",
        "recommended": True,
    },
    {
        "id": "B",
        "key": "pictures_on_big_card_chat_moves_to_small",
        "name": "Pictures on the 12 GB card, the chat moves to the 8 GB card",
        "detail": ("The picture-maker takes the 12 GB card and the everyday chat moves to the "
                   "8 GB card and stays there, so neither has to wait. The price is the "
                   "conversation: it can only hold as much as the 8 GB card holds with nothing "
                   "spilled into system memory."),
        "card": "big",
        "chat": "moves_to_small",
        "model": "big",
        "recommended": False,
    },
    {
        "id": "C",
        "key": "small_pictures_on_small_card_chat_untouched",
        "name": "Small pictures on the 8 GB card, the chat is left alone",
        "detail": ("The smaller picture model goes on the 8 GB card. The everyday chat is not "
                   "moved, unloaded or touched at all - same card, same long conversation. "
                   "The pictures come from the smaller model."),
        "card": "small",
        "chat": "untouched",
        "model": "small",
        "recommended": False,
    },
)

OPTION_IDS = tuple(o["id"] for o in OPTIONS)
_BY_ID = {o["id"]: o for o in OPTIONS}

#: One sentence naming all three, so a plain "no" is never the whole answer.
OFF_WORDS = (
    "No way of making pictures is switched on yet. There are three to try: "
    "A - pictures on the 12 GB card with the chat stepping aside while one is drawn (the "
    "recommended one); B - pictures on the 12 GB card with the chat moved to the 8 GB card; "
    "C - small pictures on the 8 GB card with the chat left alone. "
    "Turning one on turns the other two off, because they are three answers to one question."
)

#: The two models the owner already has, and what each needs beside it. Sizes
#: are the real files on disk, in bytes, used to say whether one is missing.
#:
#: `loader`, `clip_type` and `graph` are what a ComfyUI graph must use for THIS
#: file, and they live here rather than in the drawing module so there is ONE
#: record of the machine's picture models. `jarvis_pictures.py` builds its
#: graph from them, and `test_pictures_graph.py` checks them against the file
#: itself: NEITHER model is a fused checkpoint (Chroma1-HD is a diffusion
#: model with its own text encoder and VAE beside it; the Qwen one is an
#: sd.cpp GGUF), so `CheckpointLoaderSimple` - which takes CLIP and VAE out of
#: the same file - cannot load either of them. Both recipes are the ones
#: `scripts/measure-image-options.ps1:487-528` drew real pictures with.
IMAGE_MODELS = (
    {
        "id": "big",
        "file": r"D:\Jarvis Models\AI-Models\Chroma1-HD-int8-convrot-simple.safetensors",
        "bytes": 9201358564,
        "plain": "Chroma1-HD (the bigger picture model)",
        "needs": ("a T5-XXL text encoder and the FLUX VAE beside it",),
        "companions": (
            ("t5xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders", 5157348688),
            ("ae.safetensors", "vae", 335304388),
        ),
        "runtime": "comfyui",
        "loader": "UNETLoader",
        "clip_type": "chroma",
        "graph": "chroma",
    },
    {
        "id": "small",
        "file": r"D:\Jarvis Models\AI-Models\qwen-image-2.1-UC-Q4_K_M.gguf",
        "bytes": 4604558112,
        "plain": "Qwen-Image 2.1 (the smaller picture model)",
        "needs": ("a Qwen3-VL-8B text encoder and the Qwen-Image VAE beside it",),
        "companions": (
            ("qwen3vl_8b_int8_convrot.safetensors", "text_encoders", 9350798360),
            ("qwen_image_2.1_vae_bf16.safetensors", "vae", 675509688),
        ),
        "runtime": "comfyui",
        "loader": "UnetLoaderGGUF",
        "clip_type": "qwen_image",
        "graph": "qwen_image",
    },
)

#: Where the picture-making program was installed on this PC (2026-10-10).
COMFY_DIR = r"D:\Jarvis\ImageGen\ComfyUI"
SDCPP_DIR = r"D:\Jarvis\ImageGen\stable-diffusion.cpp"

#: The everyday chat lane and the coding lane, as they are started at boot.
#: Only the everyday one is ever moved or unloaded by this module.
DEFAULT_LANES = {
    "everyday": {"port": 11436, "model": "qwen3.5:9b", "card": "big"},
    "coding": {"port": 11435, "model": "qwen3:8b", "card": "small"},
}

#: The contexts tried when asking "how much conversation does the 8 GB card
#: hold with nothing spilled". Tried largest first; the first that fits wins.
CONTEXT_STEPS = (196608, 163840, 131072, 114688, 98304, 81920, 65536, 49152,
                 40960, 32768, 24576, 16384, 12288, 8192, 4096)


# --------------------------------------------------------------------------
#   The settings file
# --------------------------------------------------------------------------

CONFIG_NAME = "picture-card.json"

DEFAULTS = {
    #: None, or "A"/"B"/"C". Off until the owner turns one on.
    "option": None,
    #: "comfyui" or "sd_cpp", or None while the owner has not picked one.
    "runtime": None,
    #: The address the runtime answers on. None -> that runtime's own default.
    "address": None,
    #: The two lanes as they really are on this PC (ports and model names).
    "lanes": None,
    #: What a real run recorded, so the words can never claim more than was
    #: measured. Empty means "not measured yet" and the sentences say so.
    "measured": None,
}


def _config_dir() -> Path:
    base = getattr(fw, "CONFIG_DIR", None) or os.environ.get("JARVIS_CONFIG_DIR") or Path.cwd()
    return Path(base)


def settings_path(path=None) -> Path:
    return Path(path) if path else _config_dir() / CONFIG_NAME


def load_settings(path=None) -> dict:
    """The settings file, with the switches OFF when anything is wrong with it
    (a missing file, a half-written one) - never an exception, never a switch
    that reads on because a file could not be parsed."""
    values = dict(DEFAULTS)
    try:
        raw = json.loads(settings_path(path).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            values.update({k: v for k, v in raw.items() if k in DEFAULTS})
    except Exception:
        pass
    if values.get("option") not in OPTION_IDS:
        values["option"] = None
    return values


def save_settings(values: dict, path=None) -> dict:
    merged = dict(DEFAULTS)
    merged.update(values or {})
    if merged.get("option") not in OPTION_IDS:
        merged["option"] = None
    target = settings_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
    return merged


def switches(values: dict) -> dict:
    """Each option as its own on/off switch, which is how the owner asked for
    it. At most one can be on: they are three answers to one question."""
    on = values.get("option")
    return {o["id"]: (on == o["id"]) for o in OPTIONS}


def set_option(option, values: dict, path=None) -> tuple:
    """Turn one option on, or all of them off with ``option=None``.

    Returns ``(values, sentence)``. Turning one on turns the other two off and
    the sentence SAYS so, rather than leaving the owner to notice.
    """
    if option is None or option == "" or option is False:
        values = dict(values)
        values["option"] = None
        save_settings(values, path)
        return values, "Pictures are switched off again. Nothing is drawn until you turn one on."
    key = str(option).strip().upper()
    if key not in _BY_ID:
        return values, ("That is not one of the three ways. Say A, B or C: "
                        "A - pictures on the 12 GB card with the chat stepping aside; "
                        "B - pictures on the 12 GB card with the chat moved to the 8 GB card; "
                        "C - small pictures on the 8 GB card with the chat left alone.")
    values = dict(values)
    values["option"] = key
    save_settings(values, path)
    chosen = _BY_ID[key]
    return values, "{0} is on: {1}. The other two ways are off.".format(key, chosen["name"])


# --------------------------------------------------------------------------
#   The cards, found rather than assumed
# --------------------------------------------------------------------------

_CARD_CACHE = {"at": 0.0, "cards": []}


def _run(cmd, timeout=20):
    try:
        import jarvis_child_env
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             env=jarvis_child_env.inherited())
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


def read_cards(fresh: bool = False) -> list:
    """Both cards, from nvidia-smi: index, name, its UUID and its real memory.

    The UUID is the only safe handle - the index ordering is not guaranteed, so
    nothing here ever assumes card 0 is the 12 GB one. Cached for 30 seconds so
    a page can ask often without shelling out every time.
    """
    now = time.time()
    if not fresh and _CARD_CACHE["cards"] and (now - _CARD_CACHE["at"]) < 30:
        return list(_CARD_CACHE["cards"])

    cards = []
    listing = _run(["nvidia-smi", "-L"])
    uuid_by_index = {}
    for line in listing.splitlines():
        m = re.match(r"GPU\s+(\d+):\s+(.*?)\s+\(UUID:\s*(GPU-[0-9a-fA-F-]+)\)", line.strip())
        if m:
            uuid_by_index[int(m.group(1))] = (m.group(2), m.group(3))
    query = _run(["nvidia-smi",
                  "--query-gpu=index,memory.total,memory.used",
                  "--format=csv,noheader,nounits"])
    for line in query.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            index, total, used = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        name, uuid = uuid_by_index.get(index, ("", ""))
        cards.append({"index": index, "name": name, "uuid": uuid,
                      "total_mb": total, "used_mb": used})
    cards.sort(key=lambda c: c["total_mb"])
    _CARD_CACHE["cards"] = cards
    _CARD_CACHE["at"] = now
    return list(cards)


def pick_card(cards: list, want: str) -> Optional[dict]:
    """The card a role means: "big" is the one with the MOST memory, "small" the
    one with the least. Nothing here uses an index."""
    if not cards:
        return None
    if want == "big":
        return cards[-1]
    if want == "small":
        return cards[0] if len(cards) > 1 else cards[0]
    return None


def card_for(option_id: str, cards=None) -> Optional[dict]:
    opt = _BY_ID.get(str(option_id).strip().upper())
    if not opt:
        return None
    cards = read_cards() if cards is None else cards
    return pick_card(cards, opt["card"])


def fits(card: Optional[dict], model_id: str) -> Optional[bool]:
    """Whether a model's weights alone fit the card's OWN reported memory.

    This is the honest half of the question: it compares the real file size
    against the real memory, and it says nothing about the working memory a
    draw needs on top. The measured answer comes from ``measured``."""
    if not card:
        return None
    model = next((m for m in IMAGE_MODELS if m["id"] == model_id), None)
    if not model:
        return None
    return model["bytes"] <= card["total_mb"] * 1024 * 1024


# --------------------------------------------------------------------------
#   The picture-maker: what is on disk, and how it is started on one card
# --------------------------------------------------------------------------

def model_files(model_id: str, comfy_dir: str = COMFY_DIR) -> dict:
    """What of a model's own files is on this PC right now.

    ``main`` is the model the owner already has. ``companions`` are the files it
    cannot run without - a text encoder and a VAE - each looked for in the
    ComfyUI folders. A model is only ``ready`` when all of them are here AND
    each one is the full published size: a part-downloaded file is a file on
    disk, and calling that ready would be exactly the kind of claim this
    project has already been burned by. A file that is here but short is
    reported as ``partial``, with how much is still coming.
    """
    model = next((m for m in IMAGE_MODELS if m["id"] == model_id), None)
    if not model:
        return {"id": model_id, "main": False, "companions": {}, "ready": False}
    main_path = Path(model["file"])
    main = main_path.is_file() and main_path.stat().st_size >= model["bytes"]
    companions = {}
    for name, kind, want in model["companions"]:
        path = Path(comfy_dir) / "models" / kind / name
        here = path.is_file()
        size = path.stat().st_size if here else 0
        full = here and size >= want
        companions[name] = {"path": str(path), "present": full, "partial": here and not full,
                            "bytes": size, "want_bytes": want,
                            "still_missing_bytes": max(0, want - size)}
    return {"id": model_id, "main": main, "main_path": str(main_path),
            "companions": companions, "ready": main and all(c["present"] for c in companions.values())}


def missing_words(model_id: str, comfy_dir: str = COMFY_DIR) -> str:
    """One plain sentence naming exactly what is not here yet."""
    files = model_files(model_id, comfy_dir)
    model = next(m for m in IMAGE_MODELS if m["id"] == model_id)
    if files["ready"]:
        return "{0} and everything it needs are on this PC.".format(model["plain"])
    missing = [name for name, info in files["companions"].items() if not info["present"]]
    if not files["main"]:
        return "{0} itself is not at {1} any more.".format(model["plain"], files["main_path"])
    #: What each companion file weighs on the publisher's own page, in MB, so
    #: the sentence can say how big the wait is instead of just "missing".
    sizes = {"t5xxl_fp8_e4m3fn_scaled.safetensors": 4665,
             "ae.safetensors": 320,
             "qwen3vl_8b_int8_convrot.safetensors": 8918,
             "qwen_image_2.1_vae_bf16.safetensors": 645}
    wanted = ", ".join("{0} (about {1} MB)".format(n, sizes.get(n, 0)) for n in missing)
    return ("{0} is here, but it cannot draw yet: {1} is still missing. "
            "Run D:\\Jarvis\\ImageGen\\fetch-all.ps1 to fetch it."
            .format(model["plain"], wanted))


def image_env(option_id: str, cards=None) -> dict:
    """The environment the picture-maker must be started with for this option.

    ``CUDA_VISIBLE_DEVICES`` is set to the card's UUID - never its index - so
    the program can only see the one card. This is the same shape
    jarvis_second_card.py uses for its lanes.
    """
    card = card_for(option_id, cards)
    if not card or not card.get("uuid"):
        return {}
    return {"CUDA_VISIBLE_DEVICES": card["uuid"]}


def image_argv(option_id: str, cards=None, python_exe=None, comfy_dir: str = COMFY_DIR,
               port: int = 8188) -> list:
    """The exact command line that starts ComfyUI on the right card.

    ``--cuda-device 0``: with CUDA_VISIBLE_DEVICES already narrowed to one
    card, index 0 IS that card. Passing the flag as well means the card is
    pinned by two independent mechanisms, which is the lesson this project
    already paid for once.
    """
    card = card_for(option_id, cards)
    if not card:
        return []
    exe = python_exe or os.path.join(COMFY_DIR, "..", "venv", "Scripts", "python.exe")
    argv = [str(exe), "main.py", "--port", str(port), "--cuda-device", "0",
            "--listen", "127.0.0.1"]
    return argv


def runtime_address(values: dict, runtime: Optional[str] = None) -> str:
    chosen = runtime or values.get("runtime") or "comfyui"
    if values.get("address"):
        return values["address"]
    return "http://127.0.0.1:8188" if chosen == "comfyui" else "http://127.0.0.1:1234"


# --------------------------------------------------------------------------
#   The lanes: what the chat is doing, and stepping it aside
# --------------------------------------------------------------------------

def lanes(values: dict) -> dict:
    saved = values.get("lanes")
    if isinstance(saved, dict):
        merged = {k: dict(v) for k, v in DEFAULT_LANES.items()}
        for name, lane in saved.items():
            if name in merged and isinstance(lane, dict):
                merged[name].update({k: v for k, v in lane.items() if k in ("port", "model", "card")})
        return merged
    return {k: dict(v) for k, v in DEFAULT_LANES.items()}


def _json(url: str, payload: Optional[dict] = None, timeout: float = 120.0, method: str = "GET"):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = "POST"
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        body = answer.read().decode("utf-8", "replace")
    return json.loads(body) if body.strip() else {}


def lane_status(port: int, timeout: float = 5.0) -> list:
    """What a lane is holding right now, from its own /api/ps.

    ``size`` is everything the model needs and ``size_vram`` is how much of it
    is really on the card; the difference is what spilled into system memory,
    which is the number that says whether a context really fits.
    """
    try:
        answer = _json("http://127.0.0.1:{0}/api/ps".format(int(port)), timeout=timeout)
    except Exception:
        return []
    models = answer.get("models") or []
    out = []
    for m in models:
        size = int(m.get("size") or 0)
        vram = int(m.get("size_vram") or 0)
        out.append({"name": m.get("name"), "size": size, "size_vram": vram,
                    "spill": max(0, size - vram),
                    "expires_at": m.get("expires_at")})
    return out


def spill(models: list) -> int:
    """The total that is NOT on the card. Zero means the whole thing is on it."""
    return sum(m.get("spill") or 0 for m in models)


def unload_lane(port: int, model: str, timeout: float = 120.0) -> dict:
    """Take one model off the card at once, and say how long that took.

    ``keep_alive: 0`` is Ollama's own "unload this now". Nothing here stops the
    server or changes its configuration - the lane is untouched and reloads on
    the next question.
    """
    started = time.time()
    try:
        _json("http://127.0.0.1:{0}/api/generate".format(int(port)),
              {"model": model, "prompt": "", "keep_alive": 0}, timeout=timeout)
    except Exception as exc:
        return {"ok": False, "seconds": round(time.time() - started, 2),
                "words": "The chat could not be stepped aside: {0}".format(exc)}
    seconds = round(time.time() - started, 2)
    still = [m for m in lane_status(port) if m.get("size_vram")]
    if still:
        words = "The chat was asked to step aside but is still on the card."
    else:
        words = "The chat stepped aside in {0:.1f} seconds.".format(seconds)
    return {"ok": not still, "seconds": seconds, "still_resident": still, "words": words}


def warm_lane(port: int, model: str, context: Optional[int] = None,
              keep_alive: str = "30m", timeout: float = 600.0) -> dict:
    """Bring one model back onto its card, and say how long that cost.

    It waits until /api/ps shows the model really ON the card (``size_vram``
    above zero), so the seconds returned are the real reload, not the moment
    the request was accepted.
    """
    started = time.time()
    payload = {"model": model, "prompt": "", "keep_alive": keep_alive,
               "options": {"num_predict": 1}}
    if context:
        payload["options"]["num_ctx"] = int(context)
    try:
        _json("http://127.0.0.1:{0}/api/generate".format(int(port)), payload, timeout=timeout)
    except Exception as exc:
        return {"ok": False, "seconds": round(time.time() - started, 2),
                "words": "The chat could not be loaded again: {0}".format(exc)}
    deadline = started + timeout
    while time.time() < deadline:
        here = [m for m in lane_status(port) if m.get("name") == model and m.get("size_vram")]
        if here:
            return {"ok": True, "seconds": round(time.time() - started, 2), "loaded": here[0],
                    "words": "The chat was back on the card after {0:.1f} seconds."
                             .format(time.time() - started)}
        time.sleep(1.0)
    return {"ok": False, "seconds": round(time.time() - started, 2),
            "words": "The chat was asked to come back but never appeared on the card."}


def largest_context_with_no_spill(port: int, model: str, steps=None,
                                  keep_alive: str = "5m") -> dict:
    """The biggest conversation a card holds with NOTHING spilled.

    This is the one number that is the price of option B. It loads the model at
    each size, biggest first, and reads ``/api/ps``: the first context whose
    ``size_vram`` equals ``size`` is the answer. Every attempt is written down,
    including the ones that spilled, so the number cannot be quietly rounded up.
    """
    tried = []
    for ctx in (steps or CONTEXT_STEPS):
        payload = {"model": model, "prompt": "", "keep_alive": keep_alive,
                   "options": {"num_ctx": int(ctx), "num_predict": 1}}
        try:
            _json("http://127.0.0.1:{0}/api/generate".format(int(port)), payload, timeout=900.0)
        except Exception as exc:
            tried.append({"context": ctx, "error": str(exc)})
            continue
        here = [m for m in lane_status(port) if m.get("name") == model]
        if not here:
            tried.append({"context": ctx, "error": "the model did not appear in /api/ps"})
            continue
        row = {"context": ctx, "size": here[0]["size"], "size_vram": here[0]["size_vram"],
               "spill": here[0]["spill"]}
        tried.append(row)
        if here[0]["spill"] == 0:
            return {"context": ctx, "row": row, "tried": tried, "found": True}
    return {"context": None, "tried": tried, "found": False}


# --------------------------------------------------------------------------
#   Putting it together for a draw
# --------------------------------------------------------------------------

def prepare(values: dict, cards=None) -> dict:
    """Everything that must happen BEFORE the picture-maker draws.

    A: the everyday chat is unloaded so the 12 GB card is free.
    B: the everyday chat is loaded on the 8 GB card (its own lane, started by
       jarvis_second_card.py), so both can be up at once.
    C: nothing at all is done to the chat.
    """
    option_id = values.get("option")
    if option_id not in OPTION_IDS:
        return {"ok": False, "option": None, "words": OFF_WORDS, "steps": []}
    opt = _BY_ID[option_id]
    where = lanes(values)["everyday"]
    card = card_for(option_id, cards)
    steps = []
    if opt["chat"] == "steps_aside":
        steps.append({"did": "unload the chat", **unload_lane(where["port"], where["model"])})
    elif opt["chat"] == "moves_to_small":
        steps.append({"did": "load the chat on the 8 GB card",
                      **warm_lane(where["port"], where["model"])})
    return {"ok": True, "option": option_id, "card": card, "env": image_env(option_id, cards),
            "argv": image_argv(option_id, cards), "steps": steps,
            "words": "Ready for {0}: {1}".format(option_id, opt["name"])}


def restore(values: dict, cards=None) -> dict:
    """Everything that puts the chat back the way the owner left it.

    A: the everyday chat is loaded again on the 12 GB card and the seconds are
       reported (that cost is part of A's price).
    B and C: the chat is where it belongs already, so nothing is done.
    """
    option_id = values.get("option")
    if option_id not in OPTION_IDS:
        return {"ok": True, "steps": [], "words": "Nothing to put back."}
    opt = _BY_ID[option_id]
    where = lanes(values)["everyday"]
    if opt["chat"] != "steps_aside":
        return {"ok": True, "steps": [],
                "words": "The chat was left where it belongs; nothing to put back."}
    step = warm_lane(where["port"], where["model"])
    return {"ok": step.get("ok"), "steps": [step],
            "words": step.get("words")}


# --------------------------------------------------------------------------
#   What a page reads
# --------------------------------------------------------------------------

def status_answer(values: dict, *, cards=None, comfy_dir: str = COMFY_DIR) -> dict:
    cards = read_cards() if cards is None else cards
    on = values.get("option")
    big, small = pick_card(cards, "big"), pick_card(cards, "small")
    rows = []
    for opt in OPTIONS:
        card = card_for(opt["id"], cards)
        model = next(m for m in IMAGE_MODELS if m["id"] == opt["model"])
        files = model_files(model["id"], comfy_dir)
        rows.append({
            "id": opt["id"], "key": opt["key"], "name": opt["name"], "detail": opt["detail"],
            "recommended": opt["recommended"], "on": (on == opt["id"]),
            "card": card, "card_role": opt["card"], "chat": opt["chat"],
            "model": model["plain"], "model_ready": files["ready"],
            "fits_weights": fits(card, model["id"]),
            "missing": None if files["ready"] else missing_words(model["id"], comfy_dir),
        })
    return {
        "switches": switches(values),
        "option": on,
        "recommended": "A",
        "off_words": OFF_WORDS,
        "cards": cards,
        "words": (OFF_WORDS if on is None else
                  next(r["name"] for r in rows if r["id"] == on) + " is on."),
        "options": rows,
        "chat_lanes": lanes(values),
        "everyday_now": lane_status(lanes(values)["everyday"]["port"]),
        "measured": values.get("measured"),
        "measured_words": ("Not measured yet - these three have not been run on this PC, "
                           "so nothing here claims a speed or a size.")
                          if not values.get("measured") else "Measured on this PC.",
        "big_card": big, "small_card": small,
        "conflict": None,
    }


BASE = "/api/picture-card"


def handle_get(route: str, query: str = "", *, settings=None) -> tuple:
    values = settings if settings is not None else load_settings()
    path = urlsplit(route).path.rstrip("/") or BASE
    if path == BASE:
        return 200, status_answer(values)
    if path == BASE + "/options":
        return 200, {"options": status_answer(values)["options"], "off_words": OFF_WORDS}
    if path == BASE + "/ready":
        on = values.get("option")
        if on is None:
            return 200, {"ready": False, "words": OFF_WORDS}
        opt = _BY_ID[on]
        model = next(m for m in IMAGE_MODELS if m["id"] == opt["model"])
        files = model_files(model["id"])
        return 200, {"ready": files["ready"], "option": on, "model": model["plain"],
                     "files": files,
                     "words": ("{0} is ready to draw on {1}."
                               if files["ready"] else missing_words(model["id"])).format(
                                   model["plain"], (card_for(on) or {}).get("name", "its card"))}
    return 404, {"error": "no such picture-card route", "route": path}


def handle_post(route: str, body, *, settings=None, path=None) -> tuple:
    """Turn one of the three ways on, or all of them off.

    Three shapes are accepted, so the apps and a person at a terminal can both
    be plain about it:
      {"option": "B"}                  - turn B on (A and C go off)
      {"switch": "B", "on": true}      - the same, said as a switch
      {"option": null} / {"on": false} - all three off
    """
    values = settings if settings is not None else load_settings(path)
    key = urlsplit(route).path.rstrip("/") or BASE
    body = body if isinstance(body, dict) else {}
    if key == BASE:
        option = body.get("option")
        if option is None and isinstance(body.get("switch"), str):
            option = body["switch"] if body.get("on", True) else None
        if option is None and body.get("on") is False:
            option = None
        values, sentence = set_option(option, values, path)
        return 200, {"switches": switches(values), "option": values.get("option"),
                     "words": sentence}
    if key == BASE + "/measured":
        values = dict(values)
        values["measured"] = body.get("measured")
        save_settings(values, path)
        return 200, {"measured": values["measured"], "words": "The measurement was written down."}
    return 404, {"error": "no such picture-card route", "route": key}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the PC's Handler so the three switches answer over the API.

    The same shape the progress module's own `install()` uses, with the POST
    side added because a switch has to be turned ON as well as read: GET
    /api/picture-card and POST /api/picture-card. Nothing here draws, downloads
    or starts anything by itself - starting the picture-maker on the right card
    is D:\\Jarvis\\ImageGen\\Start-Pictures.ps1's job, which reads these
    settings. (That module is named nowhere here on purpose: test_progress.py
    fails if any module in backend/ but its own three names it, which is how
    "not reachable from a model" is kept honest.)
    """
    previous_get = handler_cls.do_GET
    previous_post = getattr(handler_cls, "do_POST", None)

    def _ours(path: str) -> bool:
        route = urlsplit(path).path.rstrip("/")
        return route == BASE or route.startswith(BASE + "/")

    def do_GET(self):  # noqa: N802 - the Handler's own name
        if _ours(self.path):
            if not origin_ok(self) or not token_ok(self):
                self.send_response(403)
                self.end_headers()
                return
            code, answer = handle_get(self.path)
            return _send_json(self, code, answer)
        return previous_get(self)

    handler_cls.do_GET = do_GET

    if previous_post is not None:
        def do_POST(self):  # noqa: N802 - the Handler's own name
            if _ours(self.path):
                if not origin_ok(self) or not token_ok(self):
                    self.send_response(403)
                    self.end_headers()
                    return
                try:
                    body = read_body(self)
                except Exception:
                    body = {}
                code, answer = handle_post(self.path, body)
                return _send_json(self, code, answer)
            return previous_post(self)

        handler_cls.do_POST = do_POST

    return "picture-card  ON  - GET and POST /api/picture-card (the three ways of making pictures)"


def _send_json(handler, code: int, answer: dict) -> None:
    payload = json.dumps(answer).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)
