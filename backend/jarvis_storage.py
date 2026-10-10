"""jarvis_storage.py - what this machine can actually hold, and what to offer.

    python backend/test_storage.py      # sees it work, with no PC of its own

WHY THIS EXISTS (the owner, 2026-10-10)
    "I have a lot of space on my D drive ssd that has 4tb, i want a lot of
    model options and im flexible. this may not be the case for everyone that
    installs epic jarvis on their desktop."

    So the model chooser must look at the machine in front of it instead of
    assuming the owner's. Two things must never happen:
      * a disk getting full - C: fell to 5.7 GB free on 2026-10-10 and broke
        every build, and a stalled 12.85 GB download is what did it;
      * a download nobody agreed to.

WHAT THIS FILE DECIDES, AND WHAT IT DOES NOT
    It decides what CAN be offered, and whether there is room for a particular
    download. It does not download anything, does not talk to Ollama, and does
    not change a setting. The work setups own what is actually installed; this
    supplies the space facts they need, so there are not two choosers.

THE THREE TIERS, IN PLAIN WORDS
    Lean        a small SSD: an everyday model and a coding model, about
                10-15 GB. What a fresh install on a laptop should be offered.
    Comfortable room for picture understanding and long conversations.
    Generous    the owner's own machine: large models, per-domain specialists,
                and the opt-in choices he asked for.

    Every tier says, before anything is chosen: how big it is on disk, what it
    is for, which card it uses, and how much free space it needs.

NO SILENT FALLBACK
    If the machine cannot hold a tier, that tier says so and the next one down
    is offered - loudly, in the answer, never by quietly changing the choice.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
#  The safety margin - the number that stops the C: disaster repeating
# --------------------------------------------------------------------------

# Never start a download that would leave less free space than this. 25 GB is
# deliberately generous: Windows itself, updates and page file need room, and
# the night C: hit 5.7 GB free every build on the machine failed.
MIN_FREE_AFTER_DOWNLOAD = 25 * 1024 ** 3

# The smallest amount worth even trying: below this, say plainly that this
# machine cannot take another model rather than attempting and failing.
MIN_FREE_TO_START = 3 * 1024 ** 3


# --------------------------------------------------------------------------
#  What the machine has
# --------------------------------------------------------------------------

def free_bytes(path) -> int:
    """Free space on the drive that holds `path`, in bytes.

    0 when the path cannot be asked about - callers must treat 0 as "do not
    start", never as "there is plenty".
    """
    try:
        p = Path(path)
        while not p.exists() and p.parent != p:
            p = p.parent
        return int(shutil.disk_usage(str(p)).free)
    except Exception:
        return 0


def cards_from(hardware: Optional[dict]) -> list[dict]:
    """The graphics cards, in the shape everything else here expects.

    `jarvis_hardware.detect()` already does the hard part (nvidia-smi, and a
    fallback to the Windows registry) and has hundreds of tests of its own, so
    this reads its answer rather than calling nvidia-smi a second time.

    ITS FIELD NAMES ARE `total_gib` AND `free_gib`, NOT `memory_total` and
    `memory_free`. The first version of this function read the latter, every
    card came out as 0 GB, and the tier chooser then told this two-card 20 GB
    PC that Comfortable would not fit. Both spellings and both units are
    accepted now so that cannot happen silently again, and `test_storage.py`
    pins the shape against a real `detect()` answer.
    """
    if not isinstance(hardware, dict):
        return []
    raw = hardware.get("cards")
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        total = c.get("total_gib", c.get("memory_total", c.get("vram_total", 0)))
        free = c.get("free_gib", c.get("memory_free", c.get("vram_free", 0)))
        total_b = 0
        free_b = 0
        try:
            total_b = int(float(total) * 1024 ** 3)
        except (TypeError, ValueError):
            total_b = 0
        try:
            free_b = int(float(free) * 1024 ** 3)
        except (TypeError, ValueError):
            free_b = 0
        out.append({
            "name": str(c.get("name") or c.get("vendor") or "graphics card"),
            "vram_total": total_b,
            "vram_free": free_b,
        })
    return out


def machine_profile(models_drive: str,
                    hardware: Optional[dict] = None,
                    installed: Optional[list[str]] = None) -> dict:
    """Everything the chooser needs to know about this PC, in plain numbers.

    `models_drive` is where models live (on the owner's PC, D:\\Jarvis Models;
    after the 2026-10-10 move, that is where every store points).
    """
    cards = cards_from(hardware)
    total_vram = sum(c["vram_total"] for c in cards)
    # The biggest single card is what one model can really use: two 8 GB cards
    # do not hold a 16 GB model between them without splitting it.
    biggest = max((c["vram_total"] for c in cards), default=0)
    return {
        "models_drive": str(models_drive),
        "free_bytes": free_bytes(models_drive),
        "cards": cards,
        "card_count": len(cards),
        "total_vram": total_vram,
        "biggest_card_vram": biggest,
        "installed": sorted(set(installed or [])),
    }


# --------------------------------------------------------------------------
#  What can be offered
# --------------------------------------------------------------------------

# Each model says what it is for and which card it wants, in words the owner
# reads before choosing. `needs_vram` is the free video memory a FULL fit
# wants; going over means the model runs partly on the processor and gets
# much slower, so a tier that cannot fit says so instead of pretending.
TIERS = (
    {
        "id": "lean",
        "name": "Lean",
        "for": "a smaller PC or a laptop SSD",
        "plain": "One everyday model and one for coding. About 10 to 15 GB.",
        "needs_disk": 15 * 1024 ** 3,
        "min_cards": 0,
        "models": (
            {"id": "qwen3:8b", "plain": "The everyday model. Talks, answers, writes.",
             "gb": 4.9, "needs_vram": 6.0, "card": "the main card"},
            {"id": "qwen3:0.6b", "plain": "A tiny model for quick jobs that must always answer.",
             "gb": 0.5, "needs_vram": 1.0, "card": "the main card"},
        ),
    },
    {
        "id": "comfortable",
        "name": "Comfortable",
        "for": "one good card, and a drive with room to spare",
        "plain": ("The everyday and coding models, a bigger one for long "
                  "conversations, and room for picture understanding."),
        "needs_disk": 40 * 1024 ** 3,
        "min_cards": 1,
        "models": (
            {"id": "qwen3.5:9b", "plain": "The everyday model, with more room to think.",
             "gb": 6.1, "needs_vram": 8.0, "card": "the main card"},
            {"id": "qwen3:8b", "plain": "The coding model.",
             "gb": 4.9, "needs_vram": 6.0, "card": "the main card"},
        ),
    },
    {
        "id": "generous",
        "name": "Generous",
        "for": "a big drive and one or two large cards",
        "plain": ("Large models, a specialist for each kind of work, the "
                  "opt-in choices, and longer conversations."),
        "needs_disk": 120 * 1024 ** 3,
        "min_cards": 1,
        "models": (
            {"id": "qwen3.5:9b", "plain": "The everyday model.",
             "gb": 6.1, "needs_vram": 8.0, "card": "the main card"},
            {"id": "ornith:9b", "plain": "An agentic coding specialist.",
             "gb": 5.2, "needs_vram": 7.0, "card": "the main card"},
            {"id": "qwen3.5:4b", "plain": "A fast model for small jobs, so the big one stays free.",
             "gb": 3.2, "needs_vram": 4.0, "card": "the main card"},
        ),
        # Only offered when the owner has turned it on (Decision 5, 2026-10-10).
        "opt_in": (
            {"id": "Qwen2.5-14B-Instruct-abliterated-v2.Q4_K_M.gguf",
             "plain": ("A fiction and role-play model with the safety training "
                       "removed, for stories only. Not the everyday assistant "
                       "and never the default."),
             "gb": 8.4, "needs_vram": 9.5, "card": "a card of its own",
             "cost": ("Measured cost: it is 5.8 to 6.9 points worse on "
                      "TruthfulQA (questions whose answers people get wrong), "
                      "about the same on MMLU, and its newest build is months "
                      "older than the official model.")},
        ),
    },
)


def _worst_fit(profile: dict, tier: dict) -> list[str]:
    """Which of this tier's models would not fit, in plain words."""
    troubles: list[str] = []
    biggest = profile["biggest_card_vram"]
    for m in list(tier["models"]) + list(tier.get("opt_in", ())):
        if biggest and m["needs_vram"] > 0 and (m["needs_vram"] * 1024 ** 3) > biggest:
            troubles.append(
                "{0} wants about {1:.0f} GB of video memory and the largest card has {2:.0f} GB"
                .format(m["id"], m["needs_vram"], biggest / 1024 ** 3))
    return troubles


def offer(profile: dict) -> dict:
    """Which tiers this machine can be offered, and why not the others.

    Returns {"recommended", "tiers": [...]} where each tier carries:
      fits          true when it can be installed now
      why_not       plain words when it cannot
      free_after    what free space would be left afterwards
      size_gb       what it costs on disk
    """
    free = profile["free_bytes"]
    card_count = profile["card_count"]
    offered: list[dict] = []
    recommended: Optional[str] = None

    for tier in TIERS:
        need = tier["needs_disk"]
        need_cards = tier["min_cards"]
        why: list[str] = []

        if free < MIN_FREE_TO_START:
            why.append(
                "there is only {0:.1f} GB free on {1}, which is too little to add anything"
                .format(free / 1024 ** 3, profile["models_drive"]))
        elif free - need < MIN_FREE_AFTER_DOWNLOAD:
            why.append(
                "it needs about {0:.0f} GB on {1}, and that would leave only {2:.1f} GB free; "
                "this keeps at least {3:.0f} GB free so the PC keeps working"
                .format(need / 1024 ** 3,
                        profile["models_drive"],
                        (free - need) / 1024 ** 3,
                        MIN_FREE_AFTER_DOWNLOAD / 1024 ** 3))
        if need_cards and card_count < need_cards:
            why.append(
                "it is meant for a PC with a graphics card, and none was found")

        fits = not why
        entry = {
            "id": tier["id"],
            "name": tier["name"],
            "for": tier["for"],
            "plain": tier["plain"],
            "size_gb": round(need / 1024 ** 3, 1),
            "fits": fits,
            "why_not": " ".join(why),
            "free_after": max(0, free - need),
            "models": list(tier["models"]),
            "opt_in": list(tier.get("opt_in", ())),
        }
        if fits:
            # The BIGGEST tier that fits is the one to suggest: the owner asked
            # for as many model options as the machine can take. (The first
            # version suggested the smallest, which told a 3.5 TB, two-card PC
            # to install the laptop set.)
            recommended = tier["id"]
            entry["card_notes"] = _worst_fit(profile, tier)
        offered.append(entry)

    return {"recommended": recommended, "tiers": offered}


# --------------------------------------------------------------------------
#  The one gate every download must pass
# --------------------------------------------------------------------------

def may_download(model_id: str, gb: float, profile: dict, *,
                 agreed: bool = False) -> tuple[bool, str]:
    """May this download start? (yes/no, and the words to show the owner.)

    This is the single place that answers it, so no other part of Jarvis can
    decide for itself and get it wrong. Every "no" says what to do instead.
    """
    if not agreed:
        # Never a silent download - the owner chose this, and it is said here
        # rather than assumed anywhere.
        return (False,
                "I will not download {0} without you saying yes. It is about "
                "{1:.1f} GB. Say yes and I will ask for the card first."
                .format(model_id, gb))

    if model_id in profile.get("installed", []):
        return (True, "{0} is already here, so nothing needs downloading."
                .format(model_id))

    free = profile["free_bytes"]
    need = int(gb * 1024 ** 3)
    if free < MIN_FREE_TO_START:
        return (False,
                "There is only {0:.1f} GB free on {1}, so there is no room for "
                "{2}. Free some space first, or point Jarvis at another drive."
                .format(free / 1024 ** 3, profile["models_drive"], model_id))

    if free - need < MIN_FREE_AFTER_DOWNLOAD:
        return (False,
                "{0} is about {1:.1f} GB, and downloading it would leave only "
                "{2:.1f} GB free on {3}. Jarvis keeps at least {4:.0f} GB free "
                "so the PC keeps working - on 2026-10-10 C: fell to 5.7 GB free "
                "and every build broke. Free some space, or point Jarvis at "
                "another drive."
                .format(model_id, gb, (free - need) / 1024 ** 3,
                        profile["models_drive"],
                        MIN_FREE_AFTER_DOWNLOAD / 1024 ** 3))

    return (True, "{0} is about {1:.1f} GB, and it would leave {2:.1f} GB free."
            .format(model_id, gb, (free - need) / 1024 ** 3))


def words_for(entry: dict) -> str:
    """One tier as the owner reads it, before choosing anything.

    Every line is here because the owner asked for it: size on disk, what it
    is for, which card it uses, and what it needs free.
    """
    lines = ["{0} - {1}".format(entry["name"], entry["for"]),
             "  {0}".format(entry["plain"]),
             "  About {0:.0f} GB on disk, leaving about {1:.0f} GB free."
             .format(entry["size_gb"], entry["free_after"] / 1024 ** 3)]
    for m in entry["models"]:
        lines.append("  - {0}: {1} ({2:.1f} GB, {3})"
                     .format(m["id"], m["plain"], m["gb"], m["card"]))
    for m in entry.get("opt_in", ()):
        lines.append("  - opt-in, fiction only: {0}: {1} ({2:.1f} GB)"
                     .format(m["id"], m["plain"], m["gb"]))
        if m.get("cost"):
            lines.append("      {0}".format(m["cost"]))
    for note in entry.get("card_notes", ()):
        lines.append("  Note: {0}, so it would run slowly on the processor."
                     .format(note))
    if not entry["fits"] and entry["why_not"]:
        lines.append("  Not offered on this PC: {0}".format(entry["why_not"]))
    return "\n".join(lines)
