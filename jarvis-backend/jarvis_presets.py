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
        cost="NOT MEASURED for this model on this PC. Its context is planned at "
             "16,384, and pictures take longer than text; no speed figure is claimed "
             "until it is measured.",
        worse="Unmeasured: nothing here says it is faster or better than the general "
              "preset, and it is not the everyday choice.",
        model="qwen3-vl:8b-thinking", lane="main", context=16384,
        prompt="agentic", diet="agentic",
        tools=("browser", "phone", "forms", "notes"),
        measured=None,
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


def by_id(preset_id) -> Optional[Preset]:
    return _BY_ID.get(str(preset_id or ""))


def view() -> dict:
    """{"presets": [...], "old_ids_replaced": [...]} - what both apps render."""
    return {"presets": [p.view() for p in PRESETS],
            "old_ids_replaced": list(OLD_IDS)}


def status_view() -> dict:
    """The GET answer without the PC's readiness fields (the HUD adds those)."""
    return {"found": f"{len(PRESETS)} focus presets", "presets": view()["presets"],
            "old_ids_replaced": list(OLD_IDS),
            "switch_path": SWITCH_ROUTE, "auto": False}
