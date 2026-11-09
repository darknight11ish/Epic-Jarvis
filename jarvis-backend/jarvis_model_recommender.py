"""jarvis_model_recommender.py - "what model should THIS PC run?"

WHAT THIS IS, AND THE OWNER'S RULING IT IMPLEMENTS (Q6, 2026-11-07 17:40 PT)

    "Combine both tiers with strict provenance labels: 'MEASURED ON THIS PC'
    (when a local /api/bench record matches the hardware) + 'ESTIMATED FROM
    HARDWARE SPECS' (for any unmeasured model or other PC)."

So this module answers ONE question - which local models suit the PC it is
running on, and why - with every row labelled by how it knows:

  * `MEASURED ON THIS PC` - this PC's own scorecard store
    (`jarvis_bench.ScoreLog`, written by the five suites) holds a result for
    that model at a context it needs, and it names the cards this PC has. The
    row then carries the real decode speed, the spill and the date.
  * `ESTIMATED FIT (run benchmark to verify)` - nothing has been measured here.
    The fit is arithmetic from the model's own size and this PC's video memory,
    and the row says so in those words.

NOTHING IN THIS MODULE IS A MEASUREMENT IT DID NOT READ. It loads no model,
starts no server, writes no file, raises no card and changes no preset. A
recommendation is a sentence and a table. There is no "use this model" button
here, on purpose: applying a change is the existing preset card's job.

THE TIERS (Q6's list, plus one honest fallback). A PC is placed by what the
hardware probe and nvidia-smi really report:

    processor only          no usable graphics card reported
    one 8 GB card           the everyday small-model PC
    one 12-16 GB card       the roomy everyday PC
    multi-GPU 20-28 GB pool the two/three-card PC (this one is 28 GiB)
    workstation 32 GB+      the big-card PC
    other / unclear         e.g. one 24 GB card, which is none of the five -
                            said plainly rather than forced into a tier

THE BRAIN PANEL'S JSON SHAPE (Lane 2 leaves the seam; the Lead wires it):

    {
      "hardware": {
        "cards": [{"name", "total_gib", "monitor", "uuid", "index"}],
        "card_count": int, "vram_total_gib": float, "largest_card_gib": float,
        "ram_gib": float|null, "cpu": str, "detected": bool,
        "words": "the one sentence a screen shows"},
      "tier": {"id", "label", "words"},
      "rows": [{
        "model", "label", "params", "quant", "capabilities": [str],
        "fit": "fits_1_card"|"pooled"|"processor"|"too_big",
        "vram_needed_gib": float, "context_gib": float|null,
        "provenance": "measured_this_pc"|"estimated_fit"|
                      "measured_other_hardware",
        "provenance_label": "MEASURED ON THIS PC (...)" etc,
        "measured": {decode_tps, spill_bytes, on_card_percent, at, suite,
                     digest, quant, ctx} | null,
        "downgrade_warning": str,
        "why": "one plain sentence"}],
      "not_shown": int, "notes": [str], "generated_at": int
    }

THE CHAT HOOK THE LEAD WIRES (exact signature - this module adds no route):

    jarvis_model_recommender.chat_hook(question, *, hardware=None,
                                       scores=None) -> Optional[str]

    * returns None when the question is not this module's (so the existing
      deterministic matchers keep every question they match today);
    * returns a short, deterministic plain sentence for
      "what model should this PC run?" and its phrasings, built from the same
      rows the panel shows - no model call, no network, no random seed, no
      clock in the wording (so the same PC answers the same way every time);
    * `hardware` / `scores` are for tests and for a caller that already has
      them; both default to this PC and its own store.

WHY IT DOES NOT IMPORT THE MODEL MANAGER. `jarvis_models` is OWNER_ONLY and
never shipped; `jarvis_hardware`, `jarvis_bench` and `jarvis_child_env` are
shipped whole. This module reads only the latter (and wraps even those), so it
installs beside the owner's backend like every other shipped module and works
on a backend that has never had the model manager patched.

Standard library only, no network, no file writes, no card, no approval.
"""
from __future__ import annotations

import os
import platform
import time
from typing import Callable, Optional

# ==========================================================================
#   The tiers
# ==========================================================================
#
# The boundaries are about VIDEO MEMORY and how the models are arranged, not
# about card names: a 12 GB card and a 16 GB card are the same tier because the
# models this project runs fit either and the difference is headroom, while a
# 20-28 GiB POOL is a different arrangement because only the pooled Coding lane
# uses it.

TIER_CPU_ONLY = "cpu_only"
TIER_SINGLE_8 = "single_8gb"
TIER_SINGLE_12_16 = "single_12_16gb"
TIER_MULTI_20_28 = "multi_gpu_20_28gb"
TIER_WORKSTATION = "workstation_32gb_plus"
TIER_OTHER = "other"

TIERS = (
    {"id": TIER_CPU_ONLY, "label": "Processor only",
     "words": ("no graphics card was reported, so only the small models can "
               "run, on the processor, and slowly")},
    {"id": TIER_SINGLE_8, "label": "One 8 GB card",
     "words": ("one 8 GB card: the small Fast model and an 8B model fit; the "
               "everyday 9B fits only at a reduced window")},
    {"id": TIER_SINGLE_12_16, "label": "One 12-16 GB card",
     "words": ("one 12-16 GB card: the everyday 9B fits with room for a long "
               "context, and the small models fit beside nothing else")},
    {"id": TIER_MULTI_20_28, "label": "Two to three cards, 20-28 GB in total",
     "words": ("a 20-28 GB pool: the everyday model on one card plus the pooled "
               "coding lane across all of them is the arrangement this pool "
               "was measured for")},
    {"id": TIER_WORKSTATION, "label": "Workstation, 32 GB or more",
     "words": ("32 GB or more of video memory: the big 30B-and-up models fit "
               "without pausing everything, and the everyday model keeps a "
               "card to itself")},
    {"id": TIER_OTHER, "label": "This PC's own arrangement",
     "words": ("this PC does not sit inside the five named profiles (its cards "
               "are not one 8 GB, one 12-16 GB, a 20-28 GB pool, or 32 GB+), so "
               "it is described as it is rather than forced into one")},
)

#: What a model needs, measured on THIS PC where a scorecard exists and
#: calculated from the file size otherwise. `min_vram_gib` is the smallest
#: window this project would run the model at, with the KV cache and the
#: compute buffers included; `context_gib` is the window that number is for.
#: EVERY number here is either a measured row from `docs/MEASURED-2026-11-07-
#: THREE-GPU.md` (this PC's own three-card sweep) or said to be an estimate.
CATALOGUE = (
    {"model": "qwen3.5:4b", "label": "Qwen3.5 4B", "params": "4B",
     "quant": "Q4_K_M", "min_vram_gib": 3.2, "context_gib": 16384,
     "capabilities": ("completion",),
     "measured_note": "3.20 GiB at 16,384 on one card (2026-11-07 sweep)"},
    {"model": "minicpm-v4.6", "label": "MiniCPM-V 4.6", "params": "1.3B",
     "quant": "Q4_K_M", "min_vram_gib": 1.4, "context_gib": 16384,
     "capabilities": ("completion", "vision"),
     "measured_note": "1.33 GiB at 16,384 across three cards (2026-11-07 sweep)"},
    {"model": "qwen3:8b", "label": "Qwen3 8B", "params": "8B",
     "quant": "Q4_K_M", "min_vram_gib": 6.0, "context_gib": 16384,
     "capabilities": ("completion",),
     "measured_note": "5.85-5.97 GiB at 16,384 on one card (2026-11-07, this PC)"},
    {"model": "qwen3.5:9b", "label": "Qwen3.5 9B (everyday)", "params": "9B",
     "quant": "Q4_K_M", "min_vram_gib": 9.3, "context_gib": 196608,
     "capabilities": ("completion",),
     "measured_note": "9.18 GiB at 196,608 on the RTX 2060 alone "
                      "(2026-11-07 sweep: 42.01 tok/s)"},
    {"model": "qwen3-vl:8b-thinking", "label": "Qwen3-VL 8B (vision)",
     "params": "8B", "quant": "Q4_K_M", "min_vram_gib": 6.2,
     "context_gib": 16384, "capabilities": ("completion", "vision"),
     "measured_note": "6.14 GiB at 16,384 on the headless 2080 SUPER "
                      "(2026-11-07 sweep: 63.35 tok/s)"},
    {"model": "gemma4:12b-it-qat", "label": "Gemma 4 12B (QAT)",
     "params": "12B", "quant": "QAT Q4", "min_vram_gib": 7.2,
     "context_gib": 16384, "capabilities": ("completion",),
     "measured_note": "7.15 GiB at 16,384 on the RTX 2060 (2026-11-07 sweep)"},
    {"model": "qwen3-coder-30b-a3b-ud-q3-k-xl",
     "label": "Qwen3 Coder 30B-A3B (coding)", "params": "30B MoE",
     "quant": "UD-Q3_K_XL", "min_vram_gib": 16.2, "context_gib": 49152,
     "capabilities": ("completion", "coding"),
     "measured_note": "16.17 GiB at 49,152 across three cards "
                      "(2026-11-07 sweep: 83.82 tok/s)"},
    {"model": "qwen3-coder:30b-a3b-q4_K_M",
     "label": "Qwen3 Coder 30B-A3B (Q4 candidate)", "params": "30B MoE",
     "quant": "Q4_K_M", "min_vram_gib": 20.6, "context_gib": 49152,
     "capabilities": ("completion", "coding"),
     "measured_note": "20.60 GiB at 49,152 across three cards "
                      "(2026-11-07 sweep: 93.08 tok/s, not shipped)"},
    {"model": "gemma4:31b-it-qat", "label": "Gemma 4 31B (QAT)",
     "params": "31B", "quant": "QAT Q4", "min_vram_gib": 18.3,
     "context_gib": 16384, "capabilities": ("completion", "reasoning"),
     "measured_note": "18.25 GiB at 16,384 across three cards "
                      "(2026-11-07 sweep: 15.57 tok/s)"},
    {"model": "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M",
     "label": "Qwen3.8 27B Uncensored", "params": "27B", "quant": "Q4_K_M",
     "min_vram_gib": 16.9, "context_gib": 24576,
     "capabilities": ("completion", "uncensored"),
     "measured_note": "16.93 GiB at 24,576 across three cards "
                      "(2026-11-07 sweep: 17.68 tok/s)"},
    {"model": "hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M",
     "label": "Huihui Qwen3.5 9B (uncensored)", "params": "9B",
     "quant": "Q4_K_M", "min_vram_gib": 7.3, "context_gib": 32768,
     "capabilities": ("completion", "uncensored"),
     "measured_note": "7.30 GiB at 32,768 across three cards "
                      "(2026-11-07 sweep: 52.76 tok/s)"},
)

#: On a PC that reports NO usable card, a model still runs - on the processor,
#: in system RAM, slowly. This is the one tier where "fits" means memory rather
#: than video memory, so a model whose measured footprint is within this many
#: GiB is offered as a \processor\ row instead of being called too big. 8 GiB
#: is where this PC's CPU-only measurements put a usable answer; the row's own
#: words say it will be slow.
CPU_FIT_GIB = 8.0

#: The order the tiers are placed in, and the words for the question this
#: module answers. One constant, so the chat hook and a screen cannot disagree.
PROVENANCE_MEASURED = "measured_this_pc"
PROVENANCE_ESTIMATED = "estimated_fit"
PROVENANCE_OTHER_PC = "measured_other_hardware"
PROVENANCE_LABELS = {
    PROVENANCE_MEASURED: "MEASURED ON THIS PC",
    PROVENANCE_ESTIMATED: "ESTIMATED FIT (run benchmark to verify)",
    PROVENANCE_OTHER_PC: "MEASURED ON DIFFERENT CARDS (run benchmark to verify)",
}

#: The question phrasings the chat hook answers. Lower-cased substrings; the
#: Lead wires `chat_hook` before the model, and a question that is not one of
#: these returns None so no existing matcher loses its question.
CHAT_TRIGGERS = (
    "what model should this pc run",
    "what model should this computer run",
    "which model should this pc run",
    "which model should this computer run",
    "what model should i run",
    "which model should i run",
    "what models fit this pc",
    "which models fit this pc",
    "recommend a model for this pc",
    "what model suits this pc",
)


# ==========================================================================
#   The hardware, as this PC reports it
# ==========================================================================

def _card_rows(cards) -> list:
    """Normalise a hardware probe's card rows. Never raises."""
    out = []
    for c in cards or ():
        if not isinstance(c, dict):
            continue
        try:
            total = float(c.get("total_gib") or 0)
        except (TypeError, ValueError):
            total = 0.0
        if total <= 0:
            continue
        out.append({"name": str(c.get("name") or "a graphics card"),
                    "total_gib": round(total, 1),
                    "monitor": c.get("monitor"),
                    "uuid": str(c.get("uuid") or ""),
                    "index": c.get("index")})
    return out


def detect_cards(*, detect: Optional[Callable] = None) -> list:
    """The CUDA cards this PC reports, through `jarvis_hardware.detect()`.

    A separate function so a test (and another PC's probe) can hand cards in;
    `[]` when the probe cannot answer, which is the honest "no card reported"
    rather than a guess. Never raises.
    """
    try:
        if detect is not None:
            got = detect()
        else:
            import jarvis_hardware  # type: ignore
            got = jarvis_hardware.detect()
    except Exception:
        return []
    rows = (got or {}).get("cards") if isinstance(got, dict) else None
    usable = [c for c in (rows or ())
              if str(c.get("route") or "CUDA").upper() in ("CUDA", "")
              and c.get("used") is not False]
    return _card_rows(usable)


def ram_gib() -> Optional[float]:
    """This PC's physical RAM in GiB, or None - absent is never zero.

    `os.sysconf` on POSIX; `GlobalMemoryStatusEx` through the standard
    library's `ctypes` on Windows. Neither is a dependency, and an unreadable
    value stays None so the row says "not reported" instead of inventing 0 GB.
    """
    try:
        if os.name == "nt":
            import ctypes

            class _Memory(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong),
                            ("load", ctypes.c_ulong),
                            ("total_phys", ctypes.c_ulonglong),
                            ("avail_phys", ctypes.c_ulonglong),
                            ("total_page", ctypes.c_ulonglong),
                            ("avail_page", ctypes.c_ulonglong),
                            ("total_virtual", ctypes.c_ulonglong),
                            ("avail_virtual", ctypes.c_ulonglong),
                            ("avail_extended", ctypes.c_ulonglong)]
            mem = _Memory()
            mem.length = ctypes.sizeof(_Memory)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(
                    ctypes.byref(mem)):
                return None
            return round(mem.total_phys / 1024 ** 3, 1)
        page = int(os.sysconf("SC_PAGE_SIZE"))
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        return round(page * pages / 1024 ** 3, 1)
    except Exception:
        return None


def _cpu_words() -> str:
    try:
        name = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "")
    except Exception:
        name = ""
    cores = os.cpu_count()
    name = " ".join(str(name or "").split())[:60]
    if name and cores:
        return f"{name} ({cores} logical processors)"
    if cores:
        return f"{cores} logical processors"
    return "processor not reported"


def tier_for(cards: list) -> dict:
    """Which of the five named profiles this PC is, and its plain words.

    Boundaries by total video memory for the single-card tiers and the pool;
    anything that does not sit inside one of them is `other` and SAYS so -
    forcing a 24 GB single card into "12-16 GB" would be a lie a screen would
    then repeat.
    """
    rows = _card_rows(cards)
    if not rows:
        tier = next(t for t in TIERS if t["id"] == TIER_CPU_ONLY)
        return dict(tier, vram_total_gib=0.0, largest_card_gib=0.0,
                    card_count=0)
    total = round(sum(c["total_gib"] for c in rows), 1)
    largest = round(max(c["total_gib"] for c in rows), 1)
    n = len(rows)
    if n == 1 and largest <= 9.5:
        tier_id = TIER_SINGLE_8
    elif n == 1 and largest <= 16.5:
        tier_id = TIER_SINGLE_12_16
    elif n >= 2 and 18.0 <= total <= 30.0:
        tier_id = TIER_MULTI_20_28
    elif total >= 32.0:
        tier_id = TIER_WORKSTATION
    else:
        tier_id = TIER_OTHER
    tier = next(t for t in TIERS if t["id"] == tier_id)
    return dict(tier, vram_total_gib=total, largest_card_gib=largest,
                card_count=n)


def hardware_profile(*, cards=None, ram_gb: Optional[float] = None,
                     cpu: Optional[str] = None,
                     detect: Optional[Callable] = None) -> dict:
    """One dict a screen and the chat hook both read. Never raises.

    `cards=None` means "detect on this PC"; an explicit `[]` means "this PC
    reported no card" (the processor-only tier). `detected` is False when the
    probe could not be read at all, so a row can say "not reported" rather
    than "none".
    """
    detected = cards is not None
    rows = _card_rows(cards) if cards is not None else detect_cards(detect=detect)
    tier = tier_for(rows)
    ram = ram_gb if ram_gb is not None else ram_gib()
    return {"cards": rows, "card_count": len(rows),
            "vram_total_gib": tier.get("vram_total_gib", 0.0),
            "largest_card_gib": tier.get("largest_card_gib", 0.0),
            "ram_gib": ram, "cpu": str(cpu or _cpu_words()),
            "detected": detected or bool(rows),
            "tier": {"id": tier["id"], "label": tier["label"],
                     "words": tier["words"]},
            "words": hardware_words(rows, tier, ram)}


def hardware_words(cards: list, tier: dict, ram_gb: Optional[float]) -> str:
    """The one sentence a screen shows about the hardware."""
    rows = _card_rows(cards)
    if not rows:
        return ("This PC reported no usable graphics card, so only the small "
                "models can run, on the processor.")
    cards_bit = " + ".join(f"{c['total_gib']:g} GB" for c in rows)
    ram_bit = f" and {ram_gb:g} GiB of RAM" if ram_gb else ""
    count = len(rows)
    return (f"This PC has {count} NVIDIA card{'s' if count != 1 else ''} with "
            f"{tier.get('vram_total_gib', 0):g} GiB of video memory in total "
            f"({cards_bit}){ram_bit}. It is the {tier['label']} tier: "
            f"{tier['words']}.")


# ==========================================================================
#   The rows: every catalogue model, labelled by how it is known
# ==========================================================================

def _measured_for(model: str, scores: Optional[dict]) -> Optional[dict]:
    """The newest speed scorecard for one model out of a scorecards dict."""
    if not scores:
        return None
    bare = str(model or "").strip()
    bare = bare[:-7] if bare.endswith(":latest") else bare
    for (name, suite), row in scores.items():
        if name == bare and suite == "speed":
            return row
    return None


def _hardware_matches(row: dict, profile: dict) -> bool:
    """Does a scorecard's card set match the cards this PC reports NOW?

    The row carries the card INDICES the run measured on (`cards_used`,
    "0,1,2"), so the check is the count. It is deliberately conservative: a
    scorecard from a different card arrangement is not offered as "measured on
    this PC", because the number would belong to a different PC. The limitation
    is stated in the row and in this docstring: the record names the indices,
    not the card models.
    """
    used = str(row.get("cards_used") or "").strip()
    if not used:
        return True            # written before the field existed; same store
    count = len([x for x in used.split(",") if x.strip()])
    return count == int(profile.get("card_count") or 0)


def _fits(card: dict, profile: dict) -> str:
    """Where one catalogue model can live on this PC."""
    need = float(card.get("min_vram_gib") or 0)
    tier = (profile.get("tier") or {}).get("id")
    if tier == TIER_CPU_ONLY:
        return "processor" if need <= CPU_FIT_GIB else "too_big"
    if need <= float(profile.get("largest_card_gib") or 0):
        return "fits_1_card"
    if need <= float(profile.get("vram_total_gib") or 0):
        return "pooled"
    return "too_big"


def _measured_label(row: dict, provenance: str) -> str:
    decode = row.get("decode_tps")
    spill = row.get("spill_bytes")
    at = row.get("at")
    bits = [PROVENANCE_LABELS[provenance]]
    if isinstance(decode, (int, float)) and not isinstance(decode, bool):
        bits.append(f"{float(decode):.1f} tok/s")
    if isinstance(spill, (int, float)) and not isinstance(spill, bool):
        bits.append("0% spill" if spill == 0 else
                    f"{float(spill) / 1024 ** 2:.0f} MiB spilled")
    if isinstance(at, int) and at > 0:
        bits.append(time.strftime("%Y-%m-%d", time.localtime(at)))
    return " (".join([bits[0], ", ".join(bits[1:])]) + ")" if len(bits) > 1 \
        else bits[0]


def recommend(*, hardware: Optional[dict] = None,
              scores: Optional[dict] = None,
              limit: int = 0) -> dict:
    """The panel's whole JSON, from this PC's hardware and scorecards.

    A model that does not fit is NOT offered as a recommendation (Q4's rule
    that the Brain must never suggest a model this PC cannot run); the count
    of those is returned in `not_shown` with one note, so the table is honest
    about what it left out rather than pretending it does not exist.
    """
    profile = hardware if isinstance(hardware, dict) else hardware_profile()
    rows, not_shown = [], 0
    for card in CATALOGUE:
        fit = _fits(card, profile)
        if fit == "too_big":
            not_shown += 1
            continue
        measured = _measured_for(card["model"], scores)
        provenance, warning, measured_bits = PROVENANCE_ESTIMATED, "", None
        if measured is not None:
            if _hardware_matches(measured, profile):
                provenance = PROVENANCE_MEASURED
            else:
                provenance = PROVENANCE_OTHER_PC
                warning = ("measured on a different card set than the one this "
                           "PC reports now - run the benchmark here to verify")
            measured_bits = {
                "decode_tps": measured.get("decode_tps"),
                "spill_bytes": measured.get("spill_bytes"),
                "on_card_percent": measured.get("on_card_percent"),
                "at": measured.get("at"), "suite": measured.get("suite"),
                "digest": measured.get("digest"), "quant": measured.get("quant"),
                "ctx": measured.get("ctx"),
            }
            spill = measured.get("spill_bytes")
            if isinstance(spill, (int, float)) and not isinstance(spill, bool) \
                    and spill > 0:
                warning = ((warning + "; " if warning else "")
                           + f"the last run spilled {spill / 1024 ** 2:.0f} MiB "
                             "of this model out of video memory - the estimate "
                             "is too optimistic at that window")
        where = ("fits on one card" if fit == "fits_1_card" else
                 "runs on the processor, slowly" if fit == "processor" else
                 "fits across the pooled cards")
        why = (f"{card['label']} needs about {card['min_vram_gib']:g} GiB at "
               f"{int(card['context_gib']):,} tokens, and it {where} on this "
               f"PC.")
        if warning:
            why = why + " Warning: " + warning + "."
        rows.append({
            "model": card["model"], "label": card["label"],
            "params": card["params"], "quant": card["quant"],
            "capabilities": list(card.get("capabilities") or ()),
            "fit": fit, "vram_needed_gib": float(card["min_vram_gib"]),
            "context_gib": int(card["context_gib"]),
            "provenance": provenance,
            "provenance_label": _measured_label(measured, provenance)
                                if measured is not None else
                                PROVENANCE_LABELS[PROVENANCE_ESTIMATED],
            "measured": measured_bits,
            "downgrade_warning": warning,
            "why": why,
            "measured_note": card.get("measured_note", ""),
        })
    # Measured rows first (they are the ones a reader can trust most), then
    # the fastest measured, then the smallest estimated - a stable order.
    def _order(row):
        rank = {PROVENANCE_MEASURED: 0, PROVENANCE_OTHER_PC: 1,
                PROVENANCE_ESTIMATED: 2}[row["provenance"]]
        speed = row.get("measured", {}) or {}
        tps = speed.get("decode_tps")
        return (rank, -(tps if isinstance(tps, (int, float))
                        and not isinstance(tps, bool) else 0.0),
                row["vram_needed_gib"])
    rows.sort(key=_order)
    if limit and int(limit) > 0:
        rows = rows[:int(limit)]
    notes = []
    if not_shown:
        notes.append(f"{not_shown} more model(s) need more video memory than "
                     "this PC has, so they are not offered here; the Brain's "
                     "own filter can show them as not-fitting and view-only.")
    if not profile.get("detected"):
        notes.append("the hardware probe could not be read, so this table may "
                     "not match the PC.")
    if not scores:
        notes.append("nothing has been benchmarked on this PC yet, so every "
                     "row is an ESTIMATED FIT; run the benchmark to verify one.")
    return {"hardware": profile, "tier": profile.get("tier") or {},
            "rows": rows, "not_shown": not_shown, "notes": notes,
            "generated_at": int(time.time()),
            "words": panel_words(profile, rows)}


def panel_words(profile: dict, rows: list, limit: int = 3) -> str:
    """The one sentence a chat answer and a screen can share."""
    if not rows:
        return (f"{profile.get('words', '')} There is no model this PC can run "
                "from the known list.")
    measured = [r for r in rows if r["provenance"] == PROVENANCE_MEASURED]
    estimated = [r for r in rows if r["provenance"] != PROVENANCE_MEASURED]
    parts = []
    if measured:
        parts.append("already measured on this PC: " + ", ".join(
            f"{r['label']} ({r['measured']['decode_tps']:.1f} tok/s)"
            if isinstance(r["measured"].get("decode_tps"), (int, float))
            else r["label"]
            for r in measured[:limit]))
    if estimated:
        parts.append("estimated fits to verify: " + ", ".join(
            r["label"] for r in estimated[:max(1, limit - len(measured))]))
    return (f"{profile.get('words', '')} " + "; ".join(parts) + ".").strip()


# ==========================================================================
#   The deterministic chat hook the Lead wires into jarvis_quick
# ==========================================================================

#: EXACT SIGNATURE (kept beside the code so the wiring cannot drift):
#:   jarvis_model_recommender.chat_hook(question, *, hardware=None,
#:                                      scores=None) -> Optional[str]
CHAT_HOOK_SIGNATURE = ("jarvis_model_recommender.chat_hook(question, *, "
                       "hardware=None, scores=None) -> Optional[str]")


def _is_this_question(question: str) -> bool:
    text = " ".join(str(question or "").lower().split())
    return any(trigger in text for trigger in CHAT_TRIGGERS)


def chat_hook(question: str, *, hardware: Optional[dict] = None,
              scores: Optional[dict] = None,
              limit: int = 3) -> Optional[str]:
    """Answer "what model should this PC run?" - or None if it is not that.

    Deterministic: the same hardware, the same stored scorecards and the same
    question always produce the same sentence. No model is called, no network
    is used, no clock or random value reaches the wording. Returning None is
    the contract that lets the Lead wire this BEFORE the existing matchers
    without stealing any question they answer today.
    """
    if not _is_this_question(question):
        return None
    panel = recommend(hardware=hardware, scores=scores, limit=0)
    return panel_words(panel["hardware"], panel["rows"], limit=limit)


def panel(*, hardware: Optional[dict] = None,
          scores: Optional[dict] = None, now: Optional[int] = None) -> dict:
    """The JSON shape documented in this module's docstring - one entry point
    for the Brain panel and any route the Lead adds. Read-only."""
    out = recommend(hardware=hardware, scores=scores)
    if now is not None:
        out["generated_at"] = int(now)
    return out


def latest_scores(*, store=None) -> dict:
    """This PC's newest scorecards in `{(bare model, suite): row}` shape.

    Borrowed from `jarvis_bench` (the module that writes them) rather than
    re-read here, so the two can never disagree about the file or the shape.
    An absent bench module is an empty store, not an error: every row is then
    an ESTIMATED FIT, which is exactly what a backend without the bench is.
    """
    try:
        import jarvis_bench  # type: ignore
        return jarvis_bench.latest_scorecards(store=store)
    except Exception:
        return {}
