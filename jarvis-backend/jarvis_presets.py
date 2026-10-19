"""jarvis_presets.py - the four focus presets the chat bar and Settings show.

Pure data plus pure helpers; reads nothing, switches nothing. The four replace
the five "work setups" in jarvis_work.py (owner decision 2026-10-18):
General (absorbs Admin + Long), Coding, Agentic+Vision, Fast.

Every measured number below is from
.dsh-scratch/android-verify/MODEL-BENCH-2026-10-10.md (and STRATEGY beside it);
`measured is None` means NOT measured for that model - never a guess.

Lanes (this PC, 2026-10-10 measurements):
  main    RTX 2060 12 GB, port 11436 - the long-context card
  coding  RTX 2080 SUPER 8 GB, port 11435 - the fast card
The owner's choices: Fast runs qwen3:8b on the coding lane at 16k while the
2060 keeps the general model warm; Coding starts the coding lane on demand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

#: Evidence every measured figure is quoted from.
EVIDENCE = (".dsh-scratch/android-verify/MODEL-BENCH-2026-10-10.md",
            ".dsh-scratch/android-verify/MODEL-STRATEGY-2026-10-10.md")

LANES = {
    "main": {"key": "main", "card": "RTX 2060", "port": 11436,
             "words": "the long-context card"},
    "coding": {"key": "coding", "card": "RTX 2080 SUPER", "port": 11435,
               "words": "the fast card"},
}

#: What the one owner-approved action is. It is a preset application, never a
#: route that runs by itself: every apply raises the existing switch_model card
#: (tier "ask"), and a lane start is only ever part of that same asked action.
APPLY_ACTION = "Use this preset"
SWITCH_ROUTE = "/api/models/switch"
LANE_START_ROUTE = "/api/model-lanes/start"


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    focus: str              # a few words under the title
    what: str               # one sentence, what it is for
    cost: str               # honest cost
    worse: str              # honest weakness
    model: str
    lane: str               # a key of LANES
    context: int
    helper_model: Optional[str] = None
    helper_lane: Optional[str] = None
    helper_context: int = 0
    prompt: str = "balanced"
    diet: str = "balanced"  # the top-K tool diet's grouping word
    tools: tuple = ()       # extra tool groups that matter for this preset
    measured: Optional[dict] = None
    pending: bool = False
    words: tuple = ()       # trigger words for /api/work/recommend
    strong: tuple = ()

    @property
    def lane_info(self) -> dict:
        return dict(LANES[self.lane])

    def view(self) -> dict:
        """The one JSON both apps render; also the fixture's shape."""
        return {
            "id": self.id, "title": self.title, "focus": self.focus,
            "what": self.what, "cost": self.cost, "worse": self.worse,
            "model": self.model,
            "lane": dict(self.lane_info),
            "context": self.context,
            "helper": ({"model": self.helper_model,
                        "lane": dict(LANES[self.helper_lane]),
                        "context": self.helper_context}
                       if self.helper_model else None),
            "policy": {"prompt": self.prompt, "diet": self.diet,
                       "tools": list(self.tools)},
            "measured": self.measured,
            "pending": self.pending,
            "apply": {"action": APPLY_ACTION, "switch_route": SWITCH_ROUTE,
                      "lane_start": self.lane != "main",
                      "auto": False},
        }


PRESETS = (
    Preset(
        id="general", title="General", focus="everyday questions, writing, life admin",
        what="The everyday preset: questions, writing, checking things, your own "
             "paperwork - one balanced setup instead of a separate admin preset.",
        cost="qwen3.5:9b sits on the 2060 and holds 196,608 tokens there, taking "
             "9.17 of its 12 GB; nothing else fits beside it. Writing is 44.9 "
             "tokens a second, not the fastest.",
        worse="Not the quickest and not the picture specialist; its thinking has to "
              "stay off for ordinary turns, or it answered nothing in the measured "
              "run.",
        model="qwen3.5:9b", lane="main", context=196608,
        prompt="balanced", diet="balanced",
        measured={"tok_s": 44.9, "size_gib": 6.10, "vram_gib": 9.17, "spill_gib": 0.0},
        words=("everyday", "general", "quick question", "writing", "admin",
               "paperwork", "letter", "statement", "form", "tax", "email", "inbox"),
        strong=("everyday use", "quick questions", "life admin", "my admin"),
    ),
    Preset(
        id="general_uncensored", title="General Uncensored",
        focus="general work with the uncensored model",
        what="General everyday work with the uncensored model, for answers the "
             "ordinary model's safety tuning would refuse or water down.",
        cost="PENDING: the owner chose a newer Qwen3.5-based uncensored model and a "
             "separate stream is finding and installing it. No model tag, speed or "
             "memory figure is claimed until that ref is confirmed on this PC.",
        worse="Uncensored means fewer refusals, not better answers; it is not the "
              "everyday default and its quality has not been measured here.",
        model="pending", lane="main", context=196608, pending=True,
        prompt="balanced", diet="balanced",
        words=("uncensored", "no filter", "unfiltered", "general uncensored"),
        strong=("general uncensored", "uncensored"),
    ),
    Preset(
        id="coding", title="Coding", focus="code, files, debugging, multi-step work",
        what="For writing and fixing code, reading a project, and long tool-driven "
             "coding jobs: the 2060 keeps the best measured model at 196k, and the "
             "coding lane starts on demand when the job needs a second worker.",
        cost="The 2060's 44.9 tokens a second is slower than the fast card, and it "
             "spends 9.17 of 12 GB, so the second model lives on the other card.",
        worse="The coding lane is on the smaller display card (8 GB); it is started "
              "for a coding job and is not the everyday lane.",
        model="qwen3.5:9b", lane="main", context=196608,
        helper_model="qwen3.5:4b", helper_lane="coding", helper_context=65536,
        prompt="coding", diet="coding",
        tools=("code", "files"),
        measured={"tok_s": 44.9, "size_gib": 6.10, "vram_gib": 9.17, "spill_gib": 0.0},
        words=("code", "coding", "program", "android", "app", "debug", "bug",
               "kotlin", "python", "script", "compile", "repository", "git"),
        strong=("writing code", "fix a bug", "build an app", "app development",
                "coding"),
    ),
    Preset(
        id="agentic_vision", title="Agentic + Vision",
        focus="tools, steps, forms, browser, phone, pictures",
        what="For work that takes several steps with tools - browser, phone, forms, "
             "notes - and pictures: the vision model reads the image, and a "
             "picture-capable model stays off the display card.",
        cost="Measured 2026-10-18: it accepts pictures and answered correctly (minor "
             "mislabels of status indicators). Browser: 4.45 s to first token, 25.6 s "
             "total. Desktop: 0.89 s first token / 46.9 s total warm, 27.6 s / 70.2 s "
             "cold - these are LATENCY, not tokens a second.",
        worse="Slow on the desktop UI (about 47 s warm, 70 s cold for a full answer), "
              "and the faster first-token fallback qwen3-vl:8b-thinking produced NO "
              "answer on the desktop UI (all thinking, done_reason=length), so it is "
              "only a simple-page option.",
        model="qwen3.5:9b", lane="main", context=16384,
        prompt="agentic", diet="agentic",
        tools=("browser", "phone", "forms", "notes"),
        measured={"vision_latency_s": {"browser_first_token": 4.45,
                                       "browser_total": 25.6,
                                       "desktop_warm_first_token": 0.89,
                                       "desktop_warm_total": 46.9,
                                       "desktop_cold_first_token": 27.6,
                                       "desktop_cold_total": 70.2},
                  "source": "vision test 2026-10-18: pictures accepted, answers correct "
                            "(minor status-indicator mislabels); speeds are LATENCY, not tok/s",
                  "fallback": {"model": "qwen3-vl:8b-thinking",
                               "note": "browser 0.39 s first token / 25.9 s total and exact, "
                                       "but on the desktop UI no answer at 3,000 or 700 tokens "
                                       "(all thinking, done_reason=length) - a first-token "
                                       "option for simple pages only, not the default"}},
        words=("agent", "agentic", "multi-step", "browser", "phone", "form",
               "screenshot", "picture", "image", "vision", "steps", "automate"),
        strong=("multi-step work", "use the browser", "read this screenshot",
                "look at this picture", "agentic"),
    ),
    Preset(
        id="fast", title="Fast", focus="the quickest short answers",
        what="The quickest preset: qwen3:8b on the fast card at 16k, while the 2060 "
             "keeps the general model warm for when you switch back.",
        cost="16,384 tokens is its ceiling and it is the weakest measured explainer; "
             "the 2060's model stays loaded beside it, for the same measured -1.9% "
             "off the main model's speed.",
        worse="Weakest answer quality of the measured models and the shortest "
              "conversation; chosen for waiting less, not for care.",
        model="qwen3:8b", lane="coding", context=16384,
        prompt="fast", diet="fast",
        measured={"tok_s": 64.0, "size_gib": 4.87, "vram_gib": 5.84, "spill_gib": 0.0},
        words=("fast", "quick", "quickly", "short answer", "one-off", "hurry",
               "speed", "asap"),
        strong=("quick answer", "as fast as possible", "fast"),
    ),
)

PRESET_IDS = tuple(p.id for p in PRESETS)
_BY_ID = {p.id: p for p in PRESETS}
OLD_IDS = ("everyday", "coding", "admin", "long", "specialist")
FOCUS_WORDS = ("quick answers", "writing", "coding", "agentic", "pictures",
               "speed")



# --------------------------------------------------------------------------
#   Hardware, questionnaire and 1/2/3-GPU recommendations (contract extension)
# --------------------------------------------------------------------------

PRIORITIES = ("speed", "quality", "long_context", "vision")


def _detected_cards() -> dict:
    """Every card this PC reports, from jarvis_hardware.detect() - never a
    hardcoded two-card table. Never raises; count 0 is said plainly."""
    try:
        import jarvis_hardware
        got = jarvis_hardware.detect() or {}
        rows = got.get("cards") or []
    except Exception:
        rows = []
    cards = []
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        if isinstance(row, dict):
            name = row.get("name") or row.get("model") or f"card {i}"
            vram = row.get("vram_gib") or row.get("memory_gib") or row.get("vram")
            uuid = row.get("uuid") or row.get("id") or ""
        else:
            name = str(getattr(row, "name", "") or f"card {i}")
            vram = getattr(row, "vram_gib", None) or getattr(row, "memory_gib", None)
            uuid = str(getattr(row, "uuid", "") or "")
        cards.append({"index": i, "name": str(name),
                      "vram_gib": (round(float(vram), 1) if isinstance(vram, (int, float)) else None),
                      "uuid": uuid})
    return {"count": len(cards), "cards": cards,
            "source": "jarvis_hardware.detect()"}


def hardware_block() -> dict:
    return {"detected": _detected_cards(),
            "questionnaire": {"focus_choices": list(PRESET_IDS),
                              "priority_choices": list(PRIORITIES),
                              "answers": None}}


def _row(p: Preset, index: int, cards: list, measured: bool,
         best_effort: bool, note: str = "") -> dict:
    card = cards[index] if index < len(cards) else None
    return {"preset": p.id, "model": p.model,
            "card_index": index,
            "card": (card or {}).get("name") or f"card {index}",
            "context": p.context,
            "tok_s": (p.measured or {}).get("tok_s") if measured else None,
            "measured": bool(measured),
            "best_effort_not_tested": bool(best_effort),
            "note": note}


def recommendations() -> dict:
    """The 1-, 2- and 3-GPU rows for every preset.

    The measured 2-GPU mapping is the agreed one (General/Coding/Agentic+Vision
    on the 2060, Fast on the 2080 SUPER). 1- and 3-GPU layouts are reasoned,
    not measured: every row there says best_effort_not_tested. A pending preset
    is never recommended (pending=True comes through and no figure is given).
    """
    cards = _detected_cards()["cards"]
    by = {}
    for n in (1, 2, 3):
        rows = {}
        for p in PRESETS:
            if p.pending:
                rows[p.id] = _row(p, 0, cards, False, True,
                                  "waiting for the model; nothing can be placed yet")
                continue
            if n == 1:
                rows[p.id] = _row(p, 0, cards, False, True,
                                  "one card: reasoned, not measured on this PC")
            elif n == 2:
                if p.id == "fast":
                    rows[p.id] = _row(p, 1, cards, p.measured is not None,
                                      p.measured is None,
                                      "the agreed 2-GPU mapping: Fast on the fast card")
                else:
                    rows[p.id] = _row(p, 0, cards, p.measured is not None,
                                      p.measured is None,
                                      "the agreed 2-GPU mapping: main model on the 2060")
            else:
                # CONFIRMED PLAN (owner, 2026-10-18): three RTX cards, no GTX 1080
                # for compute; lane-per-GPU, never one model split across three.
                idx = {"general": 0, "general_uncensored": 0, "coding": 0,
                       "fast": 1, "agentic_vision": 2}[p.id]
                note = {
                    "general": "2060 12 GB: main chat/everyday, 196k",
                    "general_uncensored": "2060 12 GB: main chat/everyday, 196k; waiting for the model",
                    "coding": "main model on the 2060; the Coding lane (qwen3.5:4b helper) "
                              "starts on demand on 2080 SUPER #2 (card 2, PCIe 3.0 x4 M.2 adapter)",
                    "fast": "2080 SUPER #1 (card 1): display + Fast/Live lane, qwen3:8b",
                    "agentic_vision": "2080 SUPER #2 (card 2): Agentic+Vision, qwen3.5:9b with images",
                }[p.id]
                rows[p.id] = _row(p, idx, cards, False, True, note)
        by[str(n)] = rows
    return {"by_gpu_count": by,
            "basis": ("the agreed 2-GPU mapping is measured; 1 and 3 GPUs are "
                      "best effort and labelled as not tested"),
            "three_gpu_plan": {
                "confirmed": True,
                "layout": "lane per GPU, never one model split across three cards",
                "cards": [
                    {"role": "main chat / everyday", "card": "RTX 2060 12 GB", "context": 196608},
                    {"role": "display + Fast/Live lane", "card": "RTX 2080 SUPER #1", "context": 16384},
                    {"role": "Agentic+Vision and Coding lane (on demand)",
                     "card": "RTX 2080 SUPER #2", "context": 16384},
                ],
                "link_note": ("2080 SUPER #2 likely sits on the B550 chipset through an M.2 "
                              "adapter: PCIe 3.0 x4, maybe x2. A slower link costs loading "
                              "time, not a lane; each lane keeps its own model."),
                "future_not_a_preset": ("Qwen3.8-27B pooled to 28 GB across cards is a future "
                                        "'max quality' experiment only; it is not a preset and "
                                        "no figure is claimed until it is measured."),
            }}

def by_id(preset_id) -> Optional[Preset]:
    return _BY_ID.get(str(preset_id or ""))


def view() -> dict:
    """{"presets": [...], "old_ids_replaced": [...]} - what both apps render."""
    return {"presets": [p.view() for p in PRESETS],
            "old_ids_replaced": list(OLD_IDS),
            "hardware": hardware_block(),
            "recommendations": recommendations()}


def status_view() -> dict:
    """The GET answer without the PC's readiness fields (the HUD adds those)."""
    return {"found": f"{len(PRESETS)} focus presets", "presets": view()["presets"],
            "old_ids_replaced": list(OLD_IDS),
            "switch_path": SWITCH_ROUTE, "auto": False}
