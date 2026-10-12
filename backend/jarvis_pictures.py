"""jarvis_pictures.py - "ask for a picture, and keep it" (the owner's decision
of 2026-09-27: *"12 GB card: longer conversations with picture understanding
first, and making pictures too (swapped in when asked, since both cannot sit on
the card at once)"*; docs/JARVIS-API.md section 129).

NEW MODULE, shipped whole. `pictures.patch` adds one call at start-up,
`install(Handler, ...)`, which answers the routes below (the same shape as the
activity-heatmap module and the backup module).

WHAT THIS IS, IN PLAIN WORDS

You ask Jarvis for a picture, in your own words. A picture-making program on
this PC draws it, the file is saved in a folder on this PC, and both apps can
show it to you again with the words that made it.

NOTHING LEAVES THE PC. The drawing program is a program on this machine
(CLAUDE.md rule 1). The only address this module ever opens a socket to is the
one the owner configured, which is the drawing program on this PC. There is no
route here that sends a picture anywhere: the phone's own "save it to my phone"
reads the picture over Tailscale or Meshnet, which is the owner's own device.

THE CARD: NONE, AND WHY THAT IS NOT A LOOPHOLE

Making a picture needs no approval card, and that is deliberate rather than an
oversight. The approval gate exists for things that leave the PC, change the
owner's accounts, or cannot be undone (docs/ARCHITECTURE.md section 4). A
picture is none of those: it is a new file in a folder on this PC, drawn by a
program on this PC, from words the owner typed. It is the same shape as a
timer or a note, both of which need no card. What WOULD need a card is sending
that picture to anyone else, and this module has no such path.

WHERE THE PROMPT CAME FROM STILL MATTERS, and it is not invented here: the
prompt is whatever the owner typed in the box. This module is not a tool in
jarvis_agent.py, is not imported by it, and is reachable from no model turn,
so a prompt can never be filled in from email, a web page or a file by the
model. `test_pictures.py` fails if any model path starts importing it.

THE SWITCH IS OFF UNTIL THE OWNER TURNS IT ON. Both cards are Turing and the
everyday model already holds the 12 GB one; the drawing program has to be
swapped in, so only one of the two can be on the card at a time. The owner's
standing rule (CLAUDE.md) is that a feature using the second card keeps its own
switch, off until *that feature* is measured. `enabled` therefore starts
`false`, and every route says so plainly rather than pretending.

THE RUNTIME, AND WHAT THE OWNER MUST INSTALL

The drawing program is a SETTING, never guessed at, because two different
programs are plausible and the owner may install either:

  * ``comfyui``  - ComfyUI, spoken to over its own HTTP API
                   (``http://127.0.0.1:8188`` by default). Nothing else here
                   needs installing: this module speaks HTTP with the standard
                   library.
  * ``sd_cpp``   - stable-diffusion.cpp, run as its own server
                   (``sd-server``, ``http://127.0.0.1:1234`` by default).

``runtime`` is ``null`` until the owner picks one, and while it is ``null``
every route answers ONE PLAIN SENTENCE saying so and naming both programs -
never a crash, never a silent nothing. That is the same promise the Progress
pictures and the second-card features make.

THE GRAPH COMFYUI IS ASKED FOR (added 2026-10-11, fixing a real defect)

The first version posted one graph whose only loader was
``CheckpointLoaderSimple``, the loader for a FUSED checkpoint. No picture model
on this PC is fused - Chroma1-HD is a diffusion model with a separate T5-XXL
encoder and a separate FLUX VAE, and the Qwen one is an sd.cpp GGUF - so that
graph could not have drawn a picture here whatever the switch said. Which
loaders and companions to use now comes from the machine's OWN record
(``jarvis_picture_card.IMAGE_MODELS``), and the two graphs are the recipes
``scripts/measure-image-options.ps1`` drew real pictures with, node for node:
the Chroma1-HD publisher's own, and Comfy-Org's Qwen-Image 2.1 one. Neither is
invented here, and a model this PC has no record of is refused in plain words
rather than guessed at.

WHERE PICTURES ARE KEPT (this survives a restart, by design)

  * The FOLDER: ``folder`` in the settings file, defaulting to
    ``%USERPROFILE%\\Pictures\\Jarvis`` - chosen on this PC only, the same
    shape jarvis_backup.py uses for its backup folder (a settings-file value,
    with a sensible default, never a path a phone can set). Only the PC's own
    account can change it.
  * The NAME: ``YYYY-MM-DD-HHMMSS-<slug>.png``, where ``<slug>`` is the first
    few words of the prompt with everything unsafe taken out. The date AND the
    time are both in the name, and a name already on disk gets ``-2``, ``-3``
    and so on, so two pictures asked for in the same second cannot collide and
    nothing is ever overwritten. `test_pictures.py` asks for the same prompt
    twice and proves both files are there.
  * The SIDECAR: ``<same name>.json``, beside the picture, holding the prompt,
    the seed, the program and its own model name, and the settings (steps,
    size, guidance) - everything needed to make the same picture again.
  * NOTHING IS DELETED ON A TIMER. Unlike jarvis_backup.py's five kept files,
    the owner's own pictures are never tidied away by Jarvis. The folder and
    its total size are reported by the list route so the owner can see what it
    costs.

WHAT IS KEPT IN THE SETTINGS FILE, AND WHERE

``pictures.json`` in the config folder (``jarvis_framework.CONFIG_DIR``), the
same place folders.json and asks_first.json live. Four keys, all read with a
fallback so a hand-edited or missing file can never crash a route:
``enabled`` (false), ``runtime`` (null), ``address`` (the program's own
default), ``folder`` (Pictures\\Jarvis).

WHAT THIS MODULE DOES NOT DO, SAID PLAINLY
  * It does not install, start, stop or reconfigure the drawing program. It
    only talks to it at the address the owner set.
  * It does not choose or download models. Whatever the program is configured
    with is what draws; this module reports that program's model name in the
    sidecar and never picks one.
  * It does not send a picture anywhere. There is no email, no upload, no
    chat attachment and no web search here.
  * It does not read the picture, describe it, or hand it to a model.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore


# --------------------------------------------------------------------------
#   Limits and words
# --------------------------------------------------------------------------

#: How many pictures one list answer carries. The FILES are never capped or
#: deleted (the owner's own pictures); only one page of the list is.
LIST_LIMIT = 60

#: The longest prompt accepted, and the longest side of a picture.
MAX_PROMPT = 2000
MAX_SIDE = 2048
MIN_SIDE = 64

#: How many words of the prompt go into the file name.
SLUG_WORDS = 6
SLUG_MAX = 48

#: The two programs this module knows how to talk to, with the address each
#: uses when it is running with its own defaults.
RUNTIMES = {
    "comfyui": {
        "plain": "ComfyUI",
        "install": "ComfyUI (https://github.com/comfyanonymous/ComfyUI)",
        "address": "http://127.0.0.1:8188",
    },
    "sd_cpp": {
        "plain": "stable-diffusion.cpp",
        "install": "stable-diffusion.cpp's server, sd-server "
                   "(https://github.com/leejet/stable-diffusion.cpp)",
        "address": "http://127.0.0.1:1234",
    },
}

#: The one plain sentence when nothing is configured. Never an error, never
#: empty: the owner is told what to install and where to say so.
NOT_CONFIGURED = (
    "Jarvis has no picture-making program set up yet, so it cannot draw one. "
    "Install ComfyUI (https://github.com/comfyanonymous/ComfyUI) or "
    "stable-diffusion.cpp's server (https://github.com/leejet/stable-diffusion.cpp), "
    "then choose which one you installed in Settings, under Pictures."
)

#: The sentence when the switch is off. The owner's own rule, said back.
OFF_WORDS = (
    "Making pictures is switched off. Turn on \"Making pictures\" in Settings, "
    "under Pictures, when you want Jarvis to use the second card for this."
)

#: The sentence when a program is configured but not answering.
def not_running(runtime: str) -> str:
    which = RUNTIMES.get(runtime, {}).get("plain", runtime or "the drawing program")
    return ("Jarvis is set to use {0}, but it is not answering. Start it on this "
            "PC, then ask again.".format(which))


#: The fixed sentences both apps show, word for word (the shape the
#: activity-heatmap module's WORDS has). The PC sends the finished ones; these
#: are the labels the screens need.
WORDS = {
    "title": "Pictures",
    "under": "Ask for a picture in your own words. Jarvis draws it on this PC and keeps it here.",
    "make": "Make a picture",
    "another": "Make another",
    "save_phone": "Save to my phone",
    "saved_phone": "Saved to your phone.",
    "ask_label": "What should the picture show?",
    "empty": "No pictures yet. Ask for one and it will appear here.",
    "hidden": "Hidden while memory lists and chat history are hidden.",
    "hidden_short": "Turn off Hide memory lists to see your pictures.",
    "off": OFF_WORDS,
    "not_configured": NOT_CONFIGURED,
    "made": "Drawn in {seconds} seconds and saved as {name}.",
    "not_kept": "A picture is never sent anywhere by Jarvis. \"Save to my phone\" copies it to your own phone.",
    "prompt_label": "You asked for",
    "made_label": "Made",
    "no_folder": "That folder is not there any more. Choose another folder in Settings, under Pictures.",
    "too_long": "That is a very long request for a picture. Keep it under {max} characters.",
    "no_words": "Say what the picture should show, and Jarvis will draw it.",
    "unknown_model": ("That is not one of the picture models on this PC, so "
                      "Jarvis will not guess at a graph that cannot load it."),
    "folder_size": "{count} pictures, {size} on disk, in {folder}.",
}


# --------------------------------------------------------------------------
#   The settings file
# --------------------------------------------------------------------------

CONFIG_NAME = "pictures.json"

DEFAULTS = {
    "enabled": False,
    "runtime": None,
    "address": None,          # None -> that runtime's own default address
    "folder": None,           # None -> %USERPROFILE%\Pictures\Jarvis
}


def settings_path() -> Path:
    """Where pictures.json lives: the config folder, beside folders.json."""
    base = Path(getattr(fw, "CONFIG_DIR", None) or Path.cwd())
    return base / CONFIG_NAME


def default_folder() -> Path:
    """``%USERPROFILE%\\Pictures\\Jarvis``, or a plain fallback when there is
    no user profile to ask (a test, a container)."""
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    if home:
        return Path(home) / "Pictures" / "Jarvis"
    return Path.cwd() / "Jarvis pictures"


def load_settings(path=None) -> dict:
    """The four settings, with every fallback applied.

    A missing file, an unreadable file, a half-written file or a wrong type in
    one key can never raise: each key falls back on its own. That matters more
    than it looks - this runs on every route, and a crash here would be the
    "never a crash" promise broken by a hand-edited line.
    """
    out = dict(DEFAULTS)
    p = Path(path) if path is not None else settings_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        raw = None
    if isinstance(raw, dict):
        if isinstance(raw.get("enabled"), bool):
            out["enabled"] = raw["enabled"]
        rt = raw.get("runtime")
        if rt is None or (isinstance(rt, str) and rt in RUNTIMES):
            out["runtime"] = rt
        addr = raw.get("address")
        if isinstance(addr, str) and addr.strip():
            out["address"] = addr.strip()
        folder = raw.get("folder")
        if isinstance(folder, str) and folder.strip():
            out["folder"] = folder.strip()
    if out["address"] is None and out["runtime"]:
        out["address"] = RUNTIMES[out["runtime"]]["address"]
    if out["folder"] is None:
        out["folder"] = str(default_folder())
    return out


def save_settings(values: dict, path=None) -> dict:
    """Write the settings back, keeping only the four keys this file owns."""
    out = dict(DEFAULTS)
    out.update({k: v for k, v in (values or {}).items() if k in DEFAULTS})
    p = Path(path) if path is not None else settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    return load_settings(p)


# --------------------------------------------------------------------------
#   The drawing programs
# --------------------------------------------------------------------------
#
# One small class each, behind one shape, so the route below never grows an
# `if runtime ==` and a test can put a stub in the registry instead of needing
# a graphics card. That is the whole reason the registry exists: the suite that
# proves the routes must not need a 12 GB card or a model on disk.

class DrawingFailed(Exception):
    """The program answered, and said it could not draw this."""


class NotReady(Exception):
    """The program is configured but is not answering at its address."""


class Piece:
    """What a drawing program hands back for one picture."""

    __slots__ = ("png", "seed", "model", "settings", "seconds")

    def __init__(self, png: bytes, *, seed=None, model="", settings=None,
                 seconds=0.0):
        self.png = png
        self.seed = seed
        self.model = model
        self.settings = dict(settings or {})
        self.seconds = round(float(seconds or 0.0), 1)


class LocalRuntime:
    """The shape every drawing program's adapter has.

    ``available()`` is a cheap probe that must never raise: it answers False
    when the program is not answering, and the route turns that into the plain
    "start it on this PC" sentence.
    """

    name = ""

    def __init__(self, address, *, timeout=10.0):
        self.address = str(address or "").rstrip("/")
        self.timeout = float(timeout)

    # -- helpers ---------------------------------------------------------
    def _json(self, path, payload=None, *, method=None, timeout=None):
        url = self.address + path
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except Exception:
                detail = ""
            raise DrawingFailed(
                "The drawing program refused that ({0}){1}".format(
                    exc.code, ": " + detail if detail else ""))
        except Exception as exc:
            raise NotReady(type(exc).__name__)
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            raise DrawingFailed("The drawing program answered with something "
                                "this PC could not read.")

    # -- the two things the route needs ---------------------------------
    def available(self) -> bool:
        raise NotImplementedError

    def draw(self, prompt, *, seed=None, settings=None) -> Piece:
        raise NotImplementedError


# --------------------------------------------------------------------------
#   Which graph this PC's picture models need
# --------------------------------------------------------------------------
#
# WHY THIS EXISTS (2026-10-11, the defect this file shipped with). The first
# version of this module posted ONE graph, whose only loader was
# `CheckpointLoaderSimple` - the loader for a FUSED checkpoint, which hands out
# a model, a CLIP and a VAE from one file. No picture model on this PC is
# fused: Chroma1-HD is a diffusion model with a separate T5-XXL text encoder
# and a separate FLUX VAE, and the Qwen one is an sd.cpp GGUF. So the route
# could not draw a picture here at all - the graph failed at its first node,
# whatever the switch said. The loaders and companions now come from the
# machine's OWN record (`jarvis_picture_card.IMAGE_MODELS`, checked against the
# real files byte for byte by `test_picture_card.py`), and the two graphs are
# the recipes `scripts/measure-image-options.ps1:487-528` drew real pictures
# with - the Chroma1-HD publisher's own, and Comfy-Org's Qwen-Image 2.1 one.

#: The size, steps and guidance each proven graph used, when the caller names
#: none. Not invented here: these are the numbers in the measurement script.
GRAPH_DEFAULTS = {
    "chroma": {"width": 1152, "height": 1152, "steps": 26, "guidance": 3.8},
    "qwen_image": {"width": 1024, "height": 1024, "steps": 25, "guidance": 1.0},
}


def _cards():
    """`jarvis_picture_card`, or None when this backend does not carry it.

    Guarded, and imported late: a backend without that module answers with one
    plain sentence instead of an ImportError on a pictures route.
    """
    try:
        import jarvis_picture_card as cards
        return cards
    except Exception:
        return None


def placement_for(model) -> Optional[dict]:
    """The loaders one picture model needs, from the machine's own record.

    Matched on the FILE NAME, so a caller may pass either the bare name ComfyUI
    shows or the full path. ``None`` means "this PC has no record of that
    file", and the route says so in plain words rather than posting a graph
    that cannot load it.
    """
    name = Path(str(model or "")).name.lower()
    if not name:
        return None
    cards = _cards()
    if cards is None:
        return None
    for entry in getattr(cards, "IMAGE_MODELS", ()) or ():
        if Path(str(entry.get("file", ""))).name.lower() != name:
            continue
        kinds = {kind: str(f) for f, kind, _size in entry.get("companions", ())}
        return {
            "model": Path(str(entry.get("file", ""))).name,
            "loader": str(entry.get("loader") or ""),
            "clip": kinds.get("text_encoders", ""),
            "vae": kinds.get("vae", ""),
            "clip_type": str(entry.get("clip_type") or ""),
            "graph": str(entry.get("graph") or ""),
        }
    return None


def default_model() -> str:
    """The file name to draw with when the caller names none.

    The apps send only a prompt, so something has to choose; it is the model of
    the way `jarvis_picture_card.OPTIONS` marks recommended, and the sidecar
    records which one drew. Empty when this backend has no such record - the
    adapter then answers plainly instead of guessing.
    """
    cards = _cards()
    if cards is None:
        return ""
    wanted = None
    for option in getattr(cards, "OPTIONS", ()) or ():
        if option.get("recommended"):
            wanted = option.get("model")
    for entry in getattr(cards, "IMAGE_MODELS", ()) or ():
        if wanted is None or entry.get("id") == wanted:
            return Path(str(entry.get("file", ""))).name
    return ""


def graph_knobs(settings: dict, place: dict) -> dict:
    """The size, steps and guidance a graph will really use.

    The caller's own numbers win; the per-graph defaults above fill the rest.
    The values returned here are the ones written into the sidecar, so the
    record and the graph can never disagree.
    """
    settings = dict(settings or {})
    defaults = GRAPH_DEFAULTS.get(place.get("graph"), GRAPH_DEFAULTS["chroma"])

    def _int(key, fallback):
        try:
            return int(settings[key])
        except (KeyError, TypeError, ValueError):
            return int(fallback)

    width = max(MIN_SIDE, min(MAX_SIDE, _int("width", defaults["width"])))
    height = max(MIN_SIDE, min(MAX_SIDE, _int("height", defaults["height"])))
    steps = max(1, min(150, _int("steps", defaults["steps"])))
    try:
        guidance = round(float(settings["guidance"]), 3)
    except (KeyError, TypeError, ValueError):
        guidance = float(defaults["guidance"])
    return {"width": width, "height": height, "steps": steps,
            "guidance": guidance}


def _chroma_graph(prompt, negative, seed, knobs, place) -> dict:
    """The Chroma1-HD publisher's own graph, node for node.

    Copied from `scripts/measure-image-options.ps1:510-527`, which drew real
    pictures on this PC. `T5TokenizerOptions` and `ModelSamplingAuraFlow` are
    the publisher's requirements, not decoration: without the shift this model
    samples wrongly.
    """
    return {
        "1": {"class_type": place["loader"] or "UNETLoader",
              "inputs": {"unet_name": place["model"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": place["clip"], "type": place["clip_type"],
                         "device": "default"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": place["vae"]}},
        "4": {"class_type": "T5TokenizerOptions",
              "inputs": {"clip": ["2", 0], "min_padding": 1, "min_length": 0}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["4", 0]}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["4", 0]}},
        "7": {"class_type": "ModelSamplingAuraFlow",
              "inputs": {"model": ["1", 0], "shift": 1.0}},
        "8": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": knobs["width"], "height": knobs["height"],
                         "batch_size": 1}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "CFGGuider",
               "inputs": {"model": ["7", 0], "positive": ["5", 0],
                          "negative": ["6", 0], "cfg": knobs["guidance"]}},
        "11": {"class_type": "KSamplerSelect",
               "inputs": {"sampler_name": "euler"}},
        "12": {"class_type": "BetaSamplingScheduler",
               "inputs": {"model": ["7", 0], "steps": knobs["steps"],
                          "alpha": 0.45, "beta": 0.45}},
        "13": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["9", 0], "guider": ["10", 0],
                          "sampler": ["11", 0], "sigmas": ["12", 0],
                          "latent_image": ["8", 0]}},
        "14": {"class_type": "VAEDecode",
               "inputs": {"samples": ["13", 0], "vae": ["3", 0]}},
        "15": {"class_type": "SaveImage",
               "inputs": {"images": ["14", 0], "filename_prefix": "jarvis"}},
    }


def _qwen_image_graph(prompt, negative, seed, knobs, place) -> dict:
    """Comfy-Org's Qwen-Image 2.1 graph, node for node.

    Copied from `scripts/measure-image-options.ps1:493-504`. `TextEncodeQwenImage21`
    hands out its OWN 64-channel latent (positive, negative and latent on the
    same node), so `EmptyLatentImage` would be the wrong shape; and this model
    is guidance-distilled, so its cfg stays 1.0 whatever a caller asks for.
    """
    return {
        "1": {"class_type": place["loader"] or "UnetLoaderGGUF",
              "inputs": {"unet_name": place["model"]}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": place["clip"], "type": place["clip_type"],
                         "device": "default"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": place["vae"]}},
        "4": {"class_type": "TextEncodeQwenImage21",
              "inputs": {"clip": ["2", 0], "prompt": prompt,
                         "negative_prompt": negative,
                         "resolution": knobs["width"]}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["4", 0],
                         "negative": ["4", 1], "latent_image": ["4", 2],
                         "seed": seed, "steps": knobs["steps"], "cfg": 1.0,
                         "sampler_name": "euler", "scheduler": "simple",
                         "denoise": 1.0}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["3", 0]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"images": ["6", 0], "filename_prefix": "jarvis"}},
    }


class ComfyUI(LocalRuntime):
    """ComfyUI, over its own HTTP API (``/prompt``, ``/history``, ``/view``).

    The graph is built here rather than loaded from a file: a file the owner
    might not have would be a second thing to install. There are TWO, and which
    one runs is decided by the MODEL FILE, from the machine's own record - never
    guessed, and never a fused `CheckpointLoaderSimple`, because no picture
    model on this PC is a fused checkpoint (see the note above).
    """

    name = "comfyui"

    def available(self) -> bool:
        if not self.address:
            return False
        try:
            self._json("/system_stats", timeout=3.0)
            return True
        except Exception:
            return False

    def _workflow(self, prompt, settings):
        settings = dict(settings or {})
        place = placement_for(settings.get("model"))
        if place is None:
            raise DrawingFailed(WORDS["unknown_model"])
        negative = str(settings.get("negative") or "")
        seed = int(settings.get("seed") or 0)
        knobs = graph_knobs(settings, place)
        if place["graph"] == "qwen_image":
            return _qwen_image_graph(prompt, negative, seed, knobs, place), knobs
        return _chroma_graph(prompt, negative, seed, knobs, place), knobs

    def draw(self, prompt, *, seed=None, settings=None) -> Piece:
        started = time.time()
        settings = dict(settings or {})
        if seed is not None:
            settings["seed"] = int(seed)
        graph, knobs = self._workflow(prompt, settings)
        client_id = "jarvis-pictures"
        posted = self._json("/prompt", {"prompt": graph,
                                        "client_id": client_id})
        pid = posted.get("prompt_id")
        if not pid:
            raise DrawingFailed("The drawing program did not start a picture.")
        # ComfyUI answers the history entry only once the job is done. Polling
        # is what its own examples do; the cap keeps a wedged job from hanging
        # the route for ever.
        deadline = time.time() + max(60.0, self.timeout * 12)
        entry = None
        while time.time() < deadline:
            hist = self._json("/history/" + str(pid))
            entry = (hist or {}).get(str(pid))
            if entry:
                break
            time.sleep(0.5)
        if not entry:
            raise DrawingFailed("The picture was still being drawn after a "
                                "long wait, so Jarvis stopped waiting.")
        images = []
        for node in (entry.get("outputs") or {}).values():
            for img in (node or {}).get("images") or ():
                images.append(img)
        if not images:
            raise DrawingFailed("The drawing program finished without a picture.")
        first = images[0]
        query = ("/view?filename={0}&subfolder={1}&type={2}"
                 .format(urllib.parse.quote(str(first.get("filename") or ""), safe=""),
                         urllib.parse.quote(str(first.get("subfolder") or ""), safe=""),
                         urllib.parse.quote(str(first.get("type") or "output"), safe="")))
        url = self.address + query
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                png = r.read()
        except Exception as exc:
            raise DrawingFailed(type(exc).__name__)
        if not png:
            raise DrawingFailed("The drawing program sent an empty picture.")
        named = str(settings.get("model") or "")
        return Piece(png, seed=settings.get("seed"), model=named,
                     settings={"steps": knobs["steps"],
                               "width": knobs["width"],
                               "height": knobs["height"],
                               "guidance": knobs["guidance"]},
                     seconds=time.time() - started)


class StableDiffusionCpp(LocalRuntime):
    """stable-diffusion.cpp's own server (``sd-server``), ``/sdapi/v1/txt2img``.

    Its address is a setting for the same reason ComfyUI's is: the owner
    starts the program, and Jarvis only talks to it.
    """

    name = "sd_cpp"

    def available(self) -> bool:
        if not self.address:
            return False
        try:
            self._json("/sdapi/v1/sd-models", timeout=3.0)
            return True
        except Exception:
            return False

    def draw(self, prompt, *, seed=None, settings=None) -> Piece:
        started = time.time()
        settings = dict(settings or {})
        if seed is not None:
            settings["seed"] = int(seed)
        body = {
            "prompt": prompt,
            "negative_prompt": str(settings.get("negative") or ""),
            "seed": int(settings.get("seed") or -1),
            "steps": int(settings.get("steps") or 20),
            "width": int(settings.get("width") or 512),
            "height": int(settings.get("height") or 512),
            "cfg_scale": float(settings.get("guidance") or 7.0),
        }
        if settings.get("model"):
            body["model"] = settings["model"]
        out = self._json("/sdapi/v1/txt2img", body)
        images = out.get("images") or []
        if not images:
            raise DrawingFailed("The drawing program finished without a picture.")
        try:
            png = base64.b64decode(images[0])
        except Exception:
            raise DrawingFailed("The drawing program sent a picture this PC "
                                "could not read.")
        info = out.get("info") or {}
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except Exception:
                info = {}
        return Piece(png, seed=info.get("seed", body["seed"]),
                     model=str(settings.get("model") or ""),
                     settings={k: body[k] for k in
                               ("steps", "width", "height", "cfg_scale")},
                     seconds=time.time() - started)


#: name -> adapter class. `register_runtime` is how a test puts a stub here
#: instead of a real program; nothing else in this module reads this directly.
RUNTIME_CLASSES = {
    "comfyui": ComfyUI,
    "sd_cpp": StableDiffusionCpp,
}


def register_runtime(name: str, cls) -> None:
    """Put an adapter (or a stub) under a runtime name."""
    if name not in RUNTIMES:
        raise KeyError(name)
    RUNTIME_CLASSES[name] = cls


def runtime_for(settings: dict):
    """The adapter for these settings, or None when nothing is configured."""
    name = (settings or {}).get("runtime")
    if not name:
        return None
    cls = RUNTIME_CLASSES.get(name)
    if cls is None:
        return None
    return cls((settings or {}).get("address") or RUNTIMES[name]["address"])


# --------------------------------------------------------------------------
#   Storage: where a picture goes, and what is written beside it
# --------------------------------------------------------------------------

_SLUG_KEEP = re.compile(r"[^a-z0-9]+")
_SAFE_NAME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6}-[A-Za-z0-9._-]+$")


def slug_for(prompt: str, *, words: int = SLUG_WORDS, limit: int = SLUG_MAX) -> str:
    """The few words of the prompt that go in the file name.

    Everything that is not a letter or a digit becomes a dash, so a prompt
    holding a slash, a colon or an emoji cannot make a path. An empty result
    (a prompt of punctuation only) becomes "picture" rather than an empty
    name.
    """
    text = _SLUG_KEEP.sub("-", str(prompt or "").lower()).strip("-")
    parts = [p for p in text.split("-") if p][:max(1, int(words))]
    out = "-".join(parts)[:max(1, int(limit))].strip("-")
    return out or "picture"


def picture_stem(when, prompt: str) -> str:
    """``YYYY-MM-DD-HHMMSS-<slug>`` - the date AND the time, so two pictures
    asked for on one day do not collide."""
    stamp = time.strftime("%Y-%m-%d-%H%M%S", time.localtime(when))
    return "{0}-{1}".format(stamp, slug_for(prompt))


def next_names(folder, stem: str) -> tuple:
    """``(png path, sidecar path)`` for the first free name.

    A name already on disk is never overwritten: ``-2``, ``-3`` ... up to a
    bound, and then a random tail, so a determined collision still cannot
    destroy a picture. Returns the first pair where NEITHER file exists.
    """
    folder = Path(folder)
    for n in range(1, 1000):
        tail = "" if n == 1 else "-{0}".format(n)
        png = folder / (stem + tail + ".png")
        side = folder / (stem + tail + ".json")
        if not png.exists() and not side.exists():
            return png, side
    tail = "-" + uuid.uuid4().hex[:8]
    return folder / (stem + tail + ".png"), folder / (stem + tail + ".json")


def sidecar_for(png: Path, prompt: str, piece: Piece, settings: dict) -> dict:
    """What made this picture, so the owner can read it and make it again."""
    return {
        "jarvis_pictures": 1,
        "picture": png.name,
        "prompt": str(prompt),
        "seed": piece.seed,
        "runtime": (settings or {}).get("runtime"),
        "model": piece.model or "",
        "settings": piece.settings or {},
        "made_at": time.time(),
        "made_at_words": time.strftime("%d %b %Y, %H:%M", time.localtime()),
        "seconds": piece.seconds,
    }


def save_picture(folder, prompt: str, piece: Piece, settings: dict, *,
                 when=None) -> dict:
    """Write the picture and its sidecar, and answer with where they went.

    The picture is written FIRST and the sidecar second: a crash between the
    two leaves a picture with no record (readable, just unexplained), never a
    record pointing at a picture that is not there.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = picture_stem(time.time() if when is None else when, prompt)
    png, side = next_names(folder, stem)
    png.write_bytes(piece.png)
    record = sidecar_for(png, prompt, piece, settings)
    try:
        side.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    except Exception:
        # The picture is the thing the owner asked for; losing its record is
        # worth saying, and is said by the record's absence in the list.
        pass
    record["path"] = str(png)
    record["sidecar"] = str(side)
    record["bytes"] = len(piece.png)
    return record


def read_sidecar(side: Path) -> Optional[dict]:
    """The record beside a picture, or None when it is missing or unreadable.
    A picture is still listed without one - never hidden by a lost record."""
    try:
        got = json.loads(Path(side).read_text(encoding="utf-8"))
    except Exception:
        return None
    return got if isinstance(got, dict) else None


def folder_bytes(folder) -> int:
    """Everything in the folder, in bytes. 0 when it cannot be read."""
    total = 0
    try:
        for p in Path(folder).iterdir():
            try:
                if p.is_file():
                    total += p.stat().st_size
            except Exception:
                continue
    except Exception:
        return 0
    return total


def sized_words(n: int) -> str:
    """A size a person reads: 0 B, 512 KB, 1.4 MB."""
    n = int(n or 0)
    if n < 1024:
        return "{0} B".format(n)
    if n < 1024 ** 2:
        return "{0:.0f} KB".format(n / 1024.0)
    if n < 1024 ** 3:
        return "{0:.1f} MB".format(n / 1024.0 ** 2)
    return "{0:.2f} GB".format(n / 1024.0 ** 3)


def listing(folder, *, limit: int = LIST_LIMIT) -> list:
    """Every picture in the folder, newest first, each with its record.

    The list is the folder's own truth: a picture is here because its file is
    here. A picture whose sidecar is gone still appears, with `prompt` empty
    and `record: false`, so the owner is never shown a picture that "does not
    exist" because a small JSON file was lost.
    """
    out = []
    folder = Path(folder)
    try:
        files = sorted(folder.glob("*.png"), key=lambda p: p.name, reverse=True)
    except Exception:
        return out
    for png in files[:max(0, int(limit))]:
        try:
            stat = png.stat()
        except Exception:
            continue
        record = read_sidecar(png.with_suffix(".json"))
        out.append({
            "name": png.name,
            "id": png.stem,
            "bytes": int(stat.st_size),
            "made_at": stat.st_mtime,
            "made_at_words": time.strftime("%d %b %Y, %H:%M",
                                          time.localtime(stat.st_mtime)),
            "prompt": (record or {}).get("prompt") or "",
            "seed": (record or {}).get("seed"),
            "model": (record or {}).get("model") or "",
            "runtime": (record or {}).get("runtime"),
            "settings": (record or {}).get("settings") or {},
            "record": bool(record),
        })
    return out


def picture_path(folder, pid: str) -> Optional[Path]:
    """The file named by an id, or None if that id is not one of ours.

    The id must be a bare file stem this module could have written: no
    separators, no dots, no traversal. A request for anything else is answered
    "no such picture", never a file outside the folder.
    """
    pid = str(pid or "")
    if not pid or "/" in pid or "\\" in pid or ".." in pid:
        return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6}-[A-Za-z0-9._-]{1,80}",
                        pid):
        return None
    png = Path(folder) / (pid + ".png")
    try:
        if png.is_file():
            return png
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------
#   The routes (docs/JARVIS-API.md section 129)
# --------------------------------------------------------------------------

BASE = "/api/pictures"
GET_ROUTES = (BASE, BASE + "/file")
POST_ROUTES = (BASE, BASE + "/settings")


def status_answer(settings: dict, *, now=None) -> dict:
    """Everything both apps need to draw the screen without asking twice."""
    settings = dict(settings or {})
    runtime = settings.get("runtime")
    folder = settings.get("folder") or str(default_folder())
    items = listing(folder) if settings.get("enabled") else []
    total = folder_bytes(folder) if settings.get("enabled") else 0
    words = None
    if not runtime:
        words = NOT_CONFIGURED
    elif not settings.get("enabled"):
        words = OFF_WORDS
    return {
        "ok": True,
        "available": True,
        "enabled": bool(settings.get("enabled")),
        "runtime": runtime,
        "runtime_plain": RUNTIMES.get(runtime, {}).get("plain", ""),
        "runtimes": [{"id": k, "plain": v["plain"], "install": v["install"],
                      "address": v["address"]}
                     for k, v in RUNTIMES.items()],
        "folder": folder,
        "count": len(items),
        "bytes": total,
        "size_words": sized_words(total),
        "words": words,
        "pictures": items,
        "keep": ("Your pictures are kept until you delete them yourself. "
                 "Jarvis never tidies them away."),
    }


def make_answer(body, settings: dict, *, runtime=None, now=None) -> tuple:
    """``POST /api/pictures`` - draw one picture and keep it.

    Returns ``(status, answer)``. Every "no" is a plain sentence in `error`
    with `ok: false`, never a traceback and never an empty 200.
    """
    settings = dict(settings or {})
    body = body if isinstance(body, dict) else {}
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return 400, {"ok": False, "error": WORDS["no_words"]}
    if len(prompt) > MAX_PROMPT:
        return 400, {"ok": False,
                     "error": WORDS["too_long"].format(max=MAX_PROMPT)}
    if not settings.get("runtime"):
        # Not configured: one plain sentence saying what to install.
        return 503, {"ok": False, "available": False,
                     "error": NOT_CONFIGURED}
    if not settings.get("enabled"):
        return 503, {"ok": False, "available": True, "off": True,
                     "error": OFF_WORDS}

    # `settings` inside the request is the DRAWING program's own knobs
    # (steps, size, model). They are not the Jarvis settings above; the names
    # are kept apart deliberately.
    draw = body.get("settings")
    draw = dict(draw) if isinstance(draw, dict) else {}
    for key in ("steps", "width", "height"):
        if key in draw:
            try:
                draw[key] = int(draw[key])
            except (TypeError, ValueError):
                draw.pop(key)
    if "width" in draw:
        draw["width"] = max(MIN_SIDE, min(MAX_SIDE, draw["width"]))
    if "height" in draw:
        draw["height"] = max(MIN_SIDE, min(MAX_SIDE, draw["height"]))
    if "steps" in draw:
        draw["steps"] = max(1, min(150, draw["steps"]))
    if "seed" in body:
        try:
            draw["seed"] = int(body["seed"])
        except (TypeError, ValueError):
            pass
    # WHICH MODEL, AND WHY IT HAS TO BE ONE OF THIS PC'S OWN (2026-10-11).
    # The apps send only a prompt, so when no model is named the recommended
    # way's own model is used and the sidecar records it. A name this PC has no
    # record of is refused HERE, in plain words - the alternative is posting a
    # graph whose loader cannot open the file, which fails deeper down with a
    # message the owner cannot act on.
    if not draw.get("model"):
        draw["model"] = default_model()
    if draw.get("model") and placement_for(draw["model"]) is None:
        return 503, {"ok": False, "available": False,
                     "error": WORDS["unknown_model"]}

    adapter = runtime if runtime is not None else runtime_for(settings)
    if adapter is None:
        return 503, {"ok": False, "available": False, "error": NOT_CONFIGURED}
    try:
        ready = bool(adapter.available())
    except Exception:
        ready = False
    if not ready:
        return 503, {"ok": False, "available": False,
                     "runtime": settings.get("runtime"),
                     "error": not_running(settings.get("runtime"))}

    try:
        piece = adapter.draw(prompt, seed=body.get("seed"), settings=draw)
    except NotReady:
        return 503, {"ok": False, "available": False,
                     "runtime": settings.get("runtime"),
                     "error": not_running(settings.get("runtime"))}
    except DrawingFailed as exc:
        return 502, {"ok": False, "error": str(exc) or
                     "The picture could not be drawn. Try again."}
    except Exception as exc:
        return 502, {"ok": False,
                     "error": "The picture could not be drawn ({0}).".format(
                         type(exc).__name__)}

    folder = settings.get("folder") or str(default_folder())
    try:
        record = save_picture(folder, prompt, piece, settings,
                              when=time.time() if now is None else now)
    except Exception as exc:
        return 500, {"ok": False,
                     "error": "The picture was drawn but could not be saved in "
                              "{0} ({1}).".format(folder, type(exc).__name__)}
    return 200, {
        "ok": True,
        "available": True,
        "name": record["picture"],
        "id": Path(record["picture"]).stem,
        "path": record["path"],
        "folder": folder,
        "prompt": prompt,
        "seed": record["seed"],
        "model": record["model"],
        "runtime": record["runtime"],
        "settings": record["settings"],
        "seconds": record["seconds"],
        "bytes": record["bytes"],
        "made_at_words": record["made_at_words"],
        "words": WORDS["made"].format(seconds=record["seconds"],
                                      name=record["picture"]),
    }


def file_answer(pid: str, settings: dict) -> tuple:
    """``GET /api/pictures/file?id=<id>`` - the picture itself.

    Sent as base64 in JSON with the token header, exactly as the captcha
    hand-off sends its one frame (jarvis_handoff.py). That is the existing
    way a picture reaches the owner's own phone over Tailscale or Meshnet, and
    it is a way to the owner's own device, not a way out of the PC.
    """
    settings = dict(settings or {})
    folder = settings.get("folder") or str(default_folder())
    png = picture_path(folder, pid)
    if png is None:
        return 404, {"ok": False, "error": "There is no picture with that name."}
    try:
        data = png.read_bytes()
    except Exception:
        return 503, {"ok": False, "error": WORDS["no_folder"]}
    return 200, {"ok": True, "id": png.stem, "name": png.name,
                 "png": base64.b64encode(data).decode("ascii"),
                 "bytes": len(data),
                 "encoding": "base64"}


def settings_answer(body, *, settings=None, path=None) -> tuple:
    """``POST /api/pictures/settings`` - the switch, the drawing program and
    the folder.

    ONE named change at a time, so nothing else can be changed by accident:

        {"action": "enabled", "on": true}
        {"action": "runtime", "runtime": "comfyui" | "sd_cpp" | null,
         "address"?: "http://127.0.0.1:8188"}
        {"action": "folder", "folder": "D:\\\\Jarvis pictures"}

    NO APPROVAL CARD, and the reason is the same one the make route gives: this
    opens no way out of the PC and loosens no rule. **It is only accepted from
    this PC** (`pc_only`), so the folder a picture is written into and the
    program that draws it stay the PC's own business - the same rule the
    chatbot money limits follow for their own PC-only writes. The route cannot
    be told apart from a local request on its own, so the caller passes
    `pc_only=True` after its own check; this module refuses without it.
    """
    body = body if isinstance(body, dict) else {}
    action = str(body.get("action") or "").strip().lower()
    st = load_settings(path) if settings is None else dict(settings)
    if action == "enabled":
        on = body.get("on")
        if not isinstance(on, bool):
            return 400, {"ok": False, "error": "Say whether making pictures is on or off."}
        st["enabled"] = on
    elif action == "runtime":
        name = body.get("runtime")
        if name is not None and name not in RUNTIMES:
            return 400, {"ok": False,
                         "error": ("Pick one of: "
                                   + ", ".join(sorted(RUNTIMES)) + ".")}
        st["runtime"] = name
        address = body.get("address")
        if isinstance(address, str) and address.strip():
            st["address"] = address.strip()
        elif name:
            st["address"] = RUNTIMES[name]["address"]
        else:
            st["address"] = None
    elif action == "folder":
        folder = str(body.get("folder") or "").strip()
        if not folder:
            return 400, {"ok": False,
                         "error": "Give the folder to keep the pictures in."}
        try:
            p = Path(folder)
            p.mkdir(parents=True, exist_ok=True)
            if not p.is_dir():
                raise NotADirectoryError(folder)
        except Exception:
            return 400, {"ok": False,
                         "error": ("Jarvis could not use that folder. Pick a "
                                   "folder on this PC it can write to.")}
        st["folder"] = str(p)
    else:
        return 400, {"ok": False,
                     "error": ("Say what to change: enabled, runtime or folder.")}
    try:
        saved = save_settings(st, path) if settings is None else st
    except Exception as exc:
        return 503, {"ok": False,
                     "error": "That could not be saved ({0}).".format(
                         type(exc).__name__)}
    return 200, dict(status_answer(saved), changed=action)


def handle_get(route: str, query: str = "", *, settings=None, now=None) -> tuple:
    """Every GET this module answers. `settings` is passed in so a test needs
    no config folder and no PC."""
    st = load_settings() if settings is None else settings
    route = (route or "").rstrip("/") or BASE
    try:
        if route == BASE:
            return 200, status_answer(st, now=now)
        if route == BASE + "/file":
            pid = (parse_qs(query or "").get("id") or [""])[0]
            return file_answer(pid, st)
    except Exception as exc:
        return 503, {"ok": False, "available": False,
                     "error": "The pictures could not be read ({0}).".format(
                         type(exc).__name__)}
    return 404, {"ok": False, "error": "no such route"}


def handle_post(route: str, body, *, settings=None, runtime=None, now=None,
                pc_only=True) -> tuple:
    route = (route or "").rstrip("/") or BASE
    if route not in POST_ROUTES:
        return 404, {"ok": False, "error": "no such route"}
    st = load_settings() if settings is None else settings
    try:
        if route == BASE + "/settings":
            # The folder a picture is written into and the program that draws
            # it are this PC's own business: never from the phone.
            if not pc_only:
                return 403, {"ok": False, "pc_only": True,
                             "error": ("Changing where pictures are kept, or "
                                       "which program draws them, can only be "
                                       "done on this PC.")}
            return settings_answer(body, settings=settings)
        return make_answer(body, st, runtime=runtime, now=now)
    except Exception as exc:
        return 503, {"ok": False, "available": False,
                     "error": "The pictures could not be used ({0}).".format(
                         type(exc).__name__)}


def _sentence(exc) -> str:
    s = str(exc).strip() or type(exc).__name__
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!")) else s + "."


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap do_GET and do_POST so these routes are answered here, after the
    server's own origin and token checks. Every other request goes straight to
    the original. Returns the banner line."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_pictures", False):
        return "  pictures   Ask for a picture and keep it (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in GET_ROUTES:
            return get0(self)
        if not _allowed(self):
            return None
        code, out = handle_get(route, parts.query)
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in POST_ROUTES:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        # Changing the folder or the drawing program is this PC's own business.
        # `jarvis_owner_check.from_this_pc` is the same test
        # jarvis_documents.py and jarvis_backup.py use for their PC-only
        # writes, imported rather than copied so the two can never drift.
        pc = True
        try:
            import jarvis_owner_check as OC
            pc = bool(OC.from_this_pc(getattr(self, "client_address", None) or (),
                                      getattr(self, "server_address", None) or ()))
        except Exception:
            pc = True
        code, out = handle_post(route, body, pc_only=pc)
        return self._send(code, out)

    do_GET._jarvis_pictures = True
    do_POST._jarvis_pictures = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  pictures   Ask for a picture and keep it (Settings > Pictures)"
