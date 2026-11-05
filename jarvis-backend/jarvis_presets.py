"""jarvis_presets.py - the focus presets the chat bar and Settings show.

Pure data plus pure helpers; reads nothing except, since 2026-10-27, WHICH
cloud key is saved on this PC (Credential Manager presence only - never a key,
never a fragment) and this month's spend against the owner's own limit, which
is what the Cloud row in the Presets menu shows. It still switches nothing and
starts nothing: every apply raises the one ask card itself, and the cloud
provider's apply changes NO model and starts NO lane.

The nine local presets: the original five (General, General Uncensored, Coding,
Agentic+Vision, Fast) and four capability rows added 2026-10-27 at the owner's
request - Reflective Coach, Pictures & Screens, Long Documents, Browser & Forms.
They replace the five "work setups" in jarvis_work.py (decision 2026-10-18).

Every measured number below is from
.dsh-scratch/android-verify/MODEL-BENCH-2026-10-10.md (and STRATEGY beside it);
`measured is None` means NOT measured for that model - never a guess.

Lanes (this PC, 2026-10-10 measurements):
  main    RTX 2060 12 GB, port 11436 - the long-context card
  coding  RTX 2080 SUPER 8 GB, port 11435 - the fast card
  pooled  both cards, port 11450 - the Coding preset's own lane (2026-11-02)
The owner's choices: Fast runs qwen3.5:4b on the coding lane at the window that
lane serves (16,384) while the 2060 keeps the general model warm; Coding starts
its own pooled both-card lane on demand.

Coding is the ONE heavy row, and since 2026-11-02 it has a lane that can really
hold it: a 14.8 GB model fits neither card alone, so its lane is ONE Ollama on
its own port with both cards visible (`jarvis_model_lanes.start_pooled_lane`),
started by the apply and stopped by the next apply that is not heavy. The cost
is stated in the preset's own words and on the card: the two lane models are
paused while it runs and come back when it is stopped.
"""
from __future__ import annotations

import os
import sys
import threading
import time
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
    # The Coding preset's own lane: ONE Ollama that sees BOTH cards, started on
    # demand by the apply (never by a logon task, which would hold both cards
    # against the two lanes the assistant runs on). `card` says "both cards"
    # because there is no single card it lives on; its port and words are
    # `jarvis_model_lanes`' own, pinned to agree by test.
    "pooled": {"key": "pooled", "card": "both cards", "port": 11450,
               "words": "one model across both cards"},
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
    heavy_mode: bool = False
    #: The plain-words COST of a heavy preset (both cards, the other models
    #: paused), which both apps show BESIDE an apply that is now allowed. It is
    #: not a refusal: the refusal was "lane support is arriving", and the lane
    #: is here (`jarvis_model_lanes.start_pooled_lane`).
    heavy_words: str = ""
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
            "heavy_mode": self.heavy_mode,
            "heavy_words": self.heavy_words,
            "apply": {"action": APPLY_ACTION, "switch_route": SWITCH_ROUTE,
                      "apply_route": "/api/work/apply",
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
        cost="Measured 2026-10-18: cold load 18.5-20.5 s, 45.6 tokens a second at 8k "
             "and 45-46 at 16k; 32k loads 7.3 GB at 100% GPU (it only splits across "
             "cards when others are resident; no CPU spill). 6.3 GB on disk, "
             "Apache-2.0, Qwen3.5 family, 8.95B parameters.",
        worse="A one-run general rubric of 6 prompts (6/6) is not independent "
              "evidence; it did beat the installed qwen2.5-14b fallback on the quality "
              "tie and 45.6 against 30.6 tokens a second. Small known nit: it suggested "
              "Homebrew on Windows.",
        model="hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M",
        lane="main", context=196608, pending=False,
        measured={"tok_s": 45.6, "tok_s_16k": 45.0, "cold_load_s": [18.5, 20.5],
                  "vram_gib_32k": 7.3, "context_max": 262144, "params_b": 8.95,
                  "disk_gib": 6.3, "licence": "Apache-2.0",
                  "source": "measurement 2026-10-18: one-run 6-prompt general rubric, "
                            "6/6; not independent; 45.6 tok/s at 8k, 45-46 at 16k"},
        prompt="balanced", diet="balanced",
        words=("uncensored", "no filter", "unfiltered", "general uncensored"),
        strong=("general uncensored", "uncensored"),
    ),
    Preset(
        id="coding", title="Coding", focus="code, files, debugging, multi-step work",
        what="For writing and fixing code, reading a project, and long tool-driven "
             "coding jobs: the 30B coding model on ONE lane that sees both cards, "
             "started on demand by this apply.",
        cost="HEAVY MODE: it fills BOTH GPUs (16.2 GB of video memory here, and "
             "another 0.3 GB in system RAM at this window) and pauses the other "
             "lanes' models while it works, for about 36 s on a cold load. "
             "Measured 2026-11-02 at 16,384 tokens: 85.3 tok/s median on three "
             "coding prompts, zero spill. Re-measured 2026-11-03 at 32,768 tokens: "
             "80.4 tok/s median on the same three prompts (79.9 at 16,384, inside "
             "this model's own run-to-run noise), with 323.5 MiB of it in system "
             "RAM instead of video memory - measured and accepted for this window "
             "alone. It is not a single-card model.",
        worse="Applying it makes it the model chat uses, so the Fast/Live and "
              "Agentic+Vision models are NOT resident while it runs - they come back "
              "when you apply another preset, and that switch costs a reload. It is "
              "not a quick helper: it takes both cards for as long as it is on, and "
              "nothing else can be loaded beside it.",
        model="qwen3-coder-30b-a3b-ud-q3-k-xl", lane="pooled", context=32768,
        prompt="coding", diet="coding", heavy_mode=True,
        heavy_words="This preset needs both cards at once as one pooled lane. While "
                    "it runs, the everyday and Fast models are paused - they come "
                    "back, proved from the model list, when you apply another preset. "
                    "Loading it takes about half a minute.",
        tools=("code", "files"),
        measured={"tok_s": 76.2, "rubric": "6/6 coding rubric", "size_gib": 14.0,
                  "gpu_use": "100% GPU across both cards", "cold_load_s": 32.1,
                  "spill_gib": 0.3, "context_zero_spill": 16384,
                  "context_measured": 32768,
                  "source": "measurement 2026-10-18 at 28,672 tokens: 76.2 tok/s "
                            "median eval, 6/6 coding rubric, no CPU spill. The "
                            "28,672-token rung was re-measured on 2026-11-02 and no "
                            "longer loads with zero spill on this PC (212 MiB went "
                            "to the CPU); 16,384 was the largest rung that loaded "
                            "with none, and is kept above as that historical fact. "
                            "From 2026-11-03 the preset asks for 32,768: the whole "
                            "ladder was measured again through the same shipped path "
                            "and every rung above 16,384 spills (20,480: 203.5 MiB, "
                            "24,576: 207.5, 28,672: 211.5, 32,768: 323.5). At 32,768 "
                            "it loaded 16,513.7 MiB with 323.5 MiB (0.3 GiB) in "
                            "system RAM, 79.88 -> 80.36 tok/s median on the three "
                            "prompts (inside noise), cold load 36.0 s against 37.0 s. "
                            "That 323.5 MiB is accepted for THIS window only, capped "
                            "at 352 MiB by jarvis_model_lanes.POOLED_SPILL_ALLOWANCE; "
                            "every other load still refuses any spill "
                            "(docs/MEASURED-2026-11-02-POOLED-LANE.md, 2026-11-03 "
                            "amendment)."},
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
        what="The quickest preset: qwen3.5:4b on the 2080 SUPER at the 16,384-token "
             "window its lane serves, while the 2060 keeps the general model warm for "
             "when you switch back.",
        cost="Measured 2026-10-10 on this same card: 77.1 tokens a second and 4.15 GB "
             "of video memory at a 65,536-token window (the file is 3.16 GB on disk). "
             "The Fast lane starts at 16,384 tokens today, so this row keeps that "
             "window; the bigger measurement is why the card has room to spare.",
        worse="The small model: fastest measured writer here, and the bench's three "
              "short prompts were only called broadly correct rather than scored. "
              "Chosen for waiting less, not for care; its first request after a cold "
              "load is slow on this card.",
        model="qwen3.5:4b", lane="coding", context=16384,
        prompt="fast", diet="fast",
        measured={"tok_s": 77.1, "size_gib": 3.16, "vram_gib": 4.15, "spill_gib": 0.0,
                  "context": 65536,
                  "source": "measured 2026-10-10 at 65,536 tokens on the RTX 2080 "
                            "SUPER (repo restatement: docs/WORK-SETUPS.md:29, "
                            "jarvis_work.py:262); the Fast lane serves 16,384"},
        words=("fast", "quick", "quickly", "short answer", "one-off", "hurry",
               "speed", "asap"),
        strong=("quick answer", "as fast as possible", "fast"),
    ),
    Preset(
        id="reflect", title="Reflective Coach",
        focus="talking a difficult thought through",
        what="For talking something through: a calm listener that reflects what you "
             "said first and asks one gentle question at a time. It is the same "
             "measured model as General, on the 12 GB card with the same full window, "
             "so a conversation is not cut off.",
        cost="Same measured setup as General: qwen3.5:9b on the 2060 at 196,608 tokens, "
             "44.9 tokens a second, 9.17 of the 12 GB, no spill. No model on this PC "
             "has been measured for empathy or reflective quality, and nothing here "
             "claims it; pair it with a matching manner in How Jarvis talks once that "
             "wording is approved.",
        worse="A model choice only - it changes no wording by itself. It is not a "
              "therapist: it gives no diagnosis, keeps no therapy record and the "
              "crisis help stays exactly where it already is.",
        model="qwen3.5:9b", lane="main", context=196608,
        prompt="balanced", diet="balanced",
        measured={"tok_s": 44.9, "size_gib": 6.10, "vram_gib": 9.17, "spill_gib": 0.0},
        words=("reflect", "talk it through", "thinking out loud", "coach",
               "difficult thought"),
        strong=("talk something through", "reflective coach"),
    ),
    Preset(
        id="pictures", title="Pictures & Screens",
        focus="reading a screenshot or a picture",
        what="For looking at a picture or a screenshot and talking about it: qwen3.5:9b, "
             "whose vision capability is documented on this PC, on the 12 GB card. "
             "Agentic + Vision is the version that also drives tools.",
        cost="Same model and card as General at a 32,768-token window. Vision is "
             "documented (the model reports completion/vision/tools/thinking and its "
             "CLIP encoder runs on the 12 GB card); this row's window and speed are not "
             "separately measured. The 2026-10-18 picture test belongs to "
             "Agentic + Vision, not this row.",
        worse="Picture quality through this row is not measured. Live phone-camera "
              "frames are explicitly unmeasured, and the old qwen3-vl fallback (which "
              "gave no answer on the desktop UI) is not used here.",
        model="qwen3.5:9b", lane="main", context=32768,
        prompt="balanced", diet="balanced",
        tools=("pictures",),
        words=("picture", "screenshot", "screen", "image", "photo", "look at"),
        strong=("read this screenshot", "look at this picture"),
    ),
    Preset(
        id="documents", title="Documents & Notes",
        focus="long reading, notes and study",
        what="For long documents, notes and study material: the same measured setup as "
             "General - qwen3.5:9b on the 2060 with the full 196,608-token window - "
             "named so long reading, note synthesis and study guides are one click "
             "instead of remembering which preset has the big window.",
        cost="Same measured setup as General: 44.9 tokens a second, 9.17 of the 12 GB, "
             "no spill. The window is the point - it is what stops a long document "
             "being cut before the model sees it.",
        worse="Not the quickest; fine for reading, not for waiting. Same model as "
              "General, so this row adds a named choice and the full window, not a "
              "different model.",
        model="qwen3.5:9b", lane="main", context=196608,
        prompt="balanced", diet="balanced",
        measured={"tok_s": 44.9, "size_gib": 6.10, "vram_gib": 9.17, "spill_gib": 0.0},
        words=("document", "documents", "long read", "summarise", "summarize", "pdf",
               "long text", "notes", "wiki", "study"),
        strong=("read this long document", "summarise this"),
    ),
    Preset(
        id="browser", title="Browser & Forms",
        focus="long pages and multi-step web work",
        what="For long web pages and multi-step form work: the long-context model on "
             "the 12 GB card with the full 196,608-token window, so a whole page plus "
             "its steps fit. Agentic + Vision stays the short tool-loop setup.",
        cost="Same measured setup as General: qwen3.5:9b on the 2060 at 196,608 tokens, "
             "44.9 tokens a second, 9.17 of the 12 GB, no spill.",
        worse="Browser and form work has not been measured through this row, and no "
              "tool-success rate is claimed; the model is the same one Agentic + "
              "Vision already uses.",
        model="qwen3.5:9b", lane="main", context=196608,
        prompt="agentic", diet="agentic",
        measured={"tok_s": 44.9, "size_gib": 6.10, "vram_gib": 9.17, "spill_gib": 0.0},
        tools=("browser", "forms"),
        words=("browser", "web page", "form", "fill in", "website"),
        strong=("use the browser", "fill in this form"),
    ),
)

PRESET_IDS = tuple(p.id for p in PRESETS)
_BY_ID = {p.id: p for p in PRESETS}
OLD_IDS = ("everyday", "coding", "admin", "long", "specialist")
FOCUS_WORDS = ("quick answers", "writing", "coding", "agentic", "pictures",
               "speed")




# --------------------------------------------------------------------------
#   Applying a preset (presets.patch, 2026-10-18)
# --------------------------------------------------------------------------

CHOICE_FILE = "presets-choice.json"
APPLY_PATH = "/api/work/apply"
PENDING_LINE = "waiting for the model; nothing was changed"



#: The contract's lane key -> jarvis_model_lanes' own lane key. The contract
#: (and both app fixtures) keep "main" for the 2060 chat lane; ma
#: jarvis_model_lanes calls that SAME lane "everyday". Translating here is the
#: difference between a working apply and a 409 "no lane called 'main'".
LANE_START_KEYS = {"main": "everyday", "coding": "coding"}

def _config_dir() -> "pathlib.Path":
    import os
    from pathlib import Path
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR", Path.home() / ".openjarvis"))


def _choice_path():
    return _config_dir() / CHOICE_FILE


def choice() -> Optional[str]:
    """The preset id the owner last applied, or None. Never raises."""
    try:
        import json
        doc = json.loads(_choice_path().read_text(encoding="utf-8"))
        return str(doc.get("preset") or "") or None
    except Exception:
        return None


def _write_choice(preset_id: str) -> bool:
    import json
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        tmp = _choice_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"preset": preset_id}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(_choice_path())
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
#   The cloud provider, and the standing escalation (2026-10-27)
# --------------------------------------------------------------------------
#
# THE OWNER'S DECISION, 2026-10-27. The Cloud row sits in the Presets menu
# beside General/Coding/Agentic+Vision/Fast (the owner's "coder, general,
# fast"), and picking one of the API services is an APPLY: ONE
# `change_own_config` card, nothing marked chosen until THIS PC's own file
# says so - the same rule every model preset already keeps
# (hud-presets.js, "a model preset is a loosening: ONE card").
#
# ONE SERVICE AT A TIME, and it is `cloud-choice.json` beside the other
# settings files. `cloud_lanes()` turns that one choice into the ONE lane name
# the whole program uses - `jarvis-escalate` - and turns "no choice" into no
# lane at all, which is `jarvis_router.choose()`'s gate "unavailable". That is
# the replacement, not a hole: before this, the lane list came from
# `litellm-proxy.yaml`, the config of a proxy that is not installed and never
# was, and it named three lanes (escalate, critic, bulk) where this program
# has one service.
#
# THE CHECKBOX UNDER IT IS A STANDING GRANT, and that is a rule the owner
# changed rather than a rule that was never there. `jarvis_router.choose()`
# says in its own words that cloud use is "per use, with permission ... and
# asks. No standing grant." (2026-09-24). On 2026-10-27 the owner asked for
# exactly that grant, and docs/DECISIONS.md records the change. What keeps it
# from being the app doing silently what the record says it never does:
#
#   * turning it ON raises ONE `change_own_config` card (`escalate_switch`'s
#     words below), and nothing is written before that yes. Turning it OFF is
#     immediate - the asymmetry every other switch in this program keeps;
#   * the FILE IS THE ONLY SOURCE of the standing yes. A client flag cannot
#     set it (`jarvis_router.choose()` reads this file, never a request body),
#     so a stale page or a phone cannot make a standing decision the PC has
#     not made;
#   * every privacy gate still runs FIRST and can still only push the turn
#     back to local: Lockdown, a tainted conversation, a picture, the screen's
#     words, a private topic, a pasted secret, the monthly money limit.
#
# WHAT THIS SECTION READS. Which keys are SAVED (Credential Manager presence -
# never a key, never a fragment, never a message) and this month's spending.
# That is the owner's own PC and it is a read; nothing here writes until a card
# has been answered.

CLOUD_CHOICE_FILE = "cloud-choice.json"
CLOUD_ESCALATE_FILE = "escalate-cloud.json"
CLOUD_ESCALATE_PATH = "/api/work/cloud-escalate"
#: The ONE cloud lane name. `jarvis_chatbot_api.CLOUD_LANES` maps it to the
#: service behind it; `jarvis_router.choose()` escalates on it and on nothing
#: else, so a stray name can never become "the cloud".
CLOUD_LANE = "jarvis-escalate"
#: The card action every loosening in this program uses.
CLOUD_ACTION = "change_own_config"
#: The Cloud row's own id - NOT one of PRESET_IDS, so both apps' nine-preset
#: list is unchanged and the phone keeps ignoring a key it does not know.
CLOUD_PRESET_ID = "cloud"


def _cloud_choice_path():
    return _config_dir() / CLOUD_CHOICE_FILE


def _escalate_path():
    return _config_dir() / CLOUD_ESCALATE_FILE


def _provider_ids() -> tuple:
    """The connected services' ids, in `jarvis_chatbot_api.PRESETS`' own order.

    Never raises: without that module (a clone, or a backend missing it) the
    answer is (). The module is imported LAZILY, inside the call, because
    this file is imported by suites that must run with no API module at all -
    the same discipline `jarvis_auto_router._money_module` uses.
    """
    try:
        import jarvis_chatbot_api as API
        return tuple(API.PRESETS)
    except Exception:
        return ()


def cloud_chosen() -> str:
    """The service id the owner last applied in the Presets menu, or "".

    "" is the honest answer for "no file", "an unreadable file", and "a name
    this PC does not know" - and it means NO cloud lane exists at all, which
    is gate "unavailable" rather than a lane nobody chose. Never raises.
    """
    try:
        import json
        doc = json.loads(_cloud_choice_path().read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(doc, dict):
        return ""
    pid = str(doc.get("provider") or "")
    if not pid:
        return ""
    known = _provider_ids()
    return pid if (not known or pid in known) else ""


def _write_cloud_choice(provider: str) -> bool:
    """Save the one provider. Atomic; False (and nothing changed) on any error."""
    import json
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        tmp = _cloud_choice_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"provider": str(provider)}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(_cloud_choice_path())
        return True
    except Exception:
        return False


def cloud_lanes() -> list:
    """The cloud lanes this PC has RIGHT NOW: one name, or none.

    None is not a hole - it is gate "unavailable", the honest answer for a PC
    where the owner has not picked a cloud service. `_lane_names()` in
    jarvis_hud.py is the only caller (through cloud-escalate.patch), and it
    used to read `litellm-proxy.yaml` for three names that no longer exist.
    """
    return [CLOUD_LANE] if cloud_chosen() else []


def escalate_on() -> bool:
    """Is the PC's own standing escalation switch ON?

    ON only when the file says so, literally: absent, unreadable, corrupt or
    holding anything but `"on": true` reads as OFF. That is the same
    fail-closed shape `jarvis_auto_router`'s own switch keeps, and it is the
    direction a privacy switch has to fail in. Never raises.
    """
    try:
        import json
        doc = json.loads(_escalate_path().read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(doc, dict) and doc.get("on") is True


def escalate_why() -> str:
    """The plain sentence for `cloud.escalate.why` - "" when it is ON."""
    if escalate_on():
        return ""
    return ("not turned on for this PC" if not _escalate_path().exists()
            else "the setting on this PC cannot be read, so it stays off")


def _write_cloud_escalate(on: bool) -> bool:
    """Save the switch. Atomic; False (and nothing changed) on any error."""
    import json
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        tmp = _escalate_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"on": bool(on), "on_since": time.time()},
                                  indent=2) + "\n", encoding="utf-8")
        tmp.replace(_escalate_path())
        return True
    except Exception:
        return False


def cloud_providers() -> list:
    """One row per connected API service, for the Cloud submenu.

    The row carries the service's NAME, host and model, whether a key is
    SAVED (`True`/`False`, or `None` when Credential Manager cannot be asked),
    the PC's own plain sentence for why it cannot be used (`ready_for`), the
    money line (`money_view`) and the one honest way to add a key from an app:
    the command line to run ON THIS PC. Keys are added on the PC only - there
    is no route for it, and the phone never sends one (rule 3).

    NO KEY, NO FRAGMENT OF ONE AND NO MESSAGE is in this answer, ever.
    `lane_status()`'s own docstring says the same for the same reason.
    """
    try:
        import jarvis_chatbot_api as API
    except Exception:
        return []
    chosen = cloud_chosen()
    rows = []
    for pid, preset in API.PRESETS.items():
        try:
            saved = API.key_saved(pid)
        except Exception:
            saved = None
        try:
            why = API.ready_for(pid)
        except Exception:
            why = "this PC could not say whether that service can be used"
        try:
            model = str(API.model_for(pid)[0] or preset.model)
        except Exception:
            model = preset.model
        try:
            money = API.money_view(pid)
        except Exception:
            money = None
        rows.append({
            "id": pid, "short": preset.short, "name": preset.name,
            "company": preset.company, "host": preset.host, "model": model,
            "key_saved": saved, "ready": not why, "why": why,
            "chosen": pid == chosen,
            "money": money,
            "key_line": API.KEY_LINE.format(short=preset.short),
            "key_where": preset.key_where,
        })
    return rows


def cloud_view() -> dict:
    """The `/api/presets` answer's new `cloud` key.

    `provider` is the service in use ("" when none is), `providers` every
    connected service (see cloud_providers), `escalate` the PC's own standing
    switch. Additive: the nine presets are untouched, `version` stays 1, and
    every reader that does not know this key ignores it.
    """
    return {"provider": cloud_chosen(),
            "providers": cloud_providers(),
            "escalate": {"on": escalate_on(), "why": escalate_why()}}


def cloud_state() -> dict:
    """The cloud facts the chat may state, read fresh and never including a key.

    This is the ONE state read for the quick answers and the model's system
    line (2026-10-31): the chosen provider, whether its key is saved (a bool,
    never a value or a fragment), whether it can be used now and why not, the
    standing escalation switch, and the DeepSeek key's presence separately
    because the owner asks about that service by name. No network, no card and
    no write; a missing module leaves the fields empty rather than guessing.
    """
    out = {"available": False, "provider": "", "provider_name": "",
           "company": "", "host": "", "model": "", "key_saved": None,
           "ready": "", "escalate": False, "escalate_why": "",
           "deepseek_key_saved": None}
    try:
        import jarvis_chatbot_api as API
    except Exception:                                       # noqa: BLE001
        return out
    out["available"] = True
    try:
        out["deepseek_key_saved"] = API.key_saved("deepseek_api")
    except Exception:                                       # noqa: BLE001
        out["deepseek_key_saved"] = None
    pid = cloud_chosen()
    out["provider"] = pid
    try:
        out["escalate"] = bool(escalate_on())
        out["escalate_why"] = escalate_why()
    except Exception:                                       # noqa: BLE001
        pass
    if pid and pid in API.PRESETS:
        preset = API.PRESETS[pid]
        out["provider_name"] = preset.name
        out["company"] = preset.company
        out["host"] = preset.host
        try:
            out["model"] = str(API.model_for(pid)[0] or preset.model)
        except Exception:                                   # noqa: BLE001
            out["model"] = preset.model
        try:
            out["key_saved"] = API.key_saved(pid)
        except Exception:                                   # noqa: BLE001
            out["key_saved"] = None
        try:
            out["ready"] = str(API.ready_for(pid) or "")
        except Exception:                                   # noqa: BLE001
            out["ready"] = "this PC could not say whether that service can be used"
    return out


def cloud_state_line() -> str:
    """ONE redacted system line saying the real cloud state, for the model.

    It names the chosen service, host and model and whether a key is saved; it
    NEVER names a key value, a fragment or a message. It exists because the
    local model was denying that any external API existed even with the Cloud
    preset chosen and a DeepSeek key saved (owner-reported, 2026-10-31). The
    line also carries the real privacy rule, so the model cannot claim either
    that everything always leaves or that nothing can ever leave.
    """
    st = cloud_state()
    if not st["available"]:
        return ("The cloud state on this PC could not be read, so do not claim either that "
                "you are connected to a cloud API or that no external connection exists. "
                "Nothing is sent to a cloud service without the owner's yes.")
    provider = st["provider"]
    if not provider:
        if st["deepseek_key_saved"]:
            return ("No cloud API service is chosen on this PC, so no question can be sent "
                    "to the cloud right now; a DeepSeek API key is saved, but choosing the "
                    "Cloud row and a provider is the step. Every answer is written by the "
                    "model on this PC unless a cloud turn is arranged and allowed.")
        return ("No cloud API service is chosen on this PC, so no question can be sent to "
                "the cloud; every answer is written by the model on this PC. A cloud turn "
                "is possible only after the owner chooses the Cloud row and saves a key.")
    who = f"{st['company']} ({st['host']}, model {st['model']})"
    key = st["key_saved"]
    if key is False:
        return (f"The Cloud preset is set to {who}, but no {st['company']} API key is saved "
                f"on this PC, so no question can be sent to it until one is added in "
                f"Windows Credential Manager; answers stay on this PC.")
    if key is None:
        return (f"The Cloud preset is set to {who}, but this PC cannot read Windows "
                f"Credential Manager, so whether that service can be used is unknown. "
                f"Nothing is sent to it without the owner's yes.")
    if st["ready"]:
        return (f"The Cloud preset is set to {who}; its key is saved on this PC, but it "
                f"cannot be used right now: {st['ready']} Nothing is sent to it.")
    escalate = (" The standing escalation switch is ON, so a hard question may go there "
                "without a per-question yes after every privacy gate; it is off at once."
                if st["escalate"] else
                " The standing escalation switch is OFF, so each cloud turn needs the "
                "owner's yes.")
    return (f"The Cloud preset is set to {who}; its key is saved on this PC and it can be "
            f"used now. A question is sent there only when the owner allows it (the Try "
            f"the cloud model button, a standing switch, or an explicit request), never "
            f"with email, files, credentials, stored memory, a picture, a screen or a "
            f"tainted conversation. Choosing the preset alone sends nothing.{escalate}")


def cloud_preset_view() -> dict:
    """The Cloud row itself, in the SAME shape as a `Preset.view()`.

    Its id is "cloud", it is deliberately absent from `PRESETS`/`PRESET_IDS`
    (both apps' nine-row list stays nine rows), and its `apply` block says the
    two things that make it different: it is a cloud row, and it needs a
    provider before it can be applied.
    """
    return {
        "id": CLOUD_PRESET_ID, "title": "Cloud",
        "focus": "a second opinion from a service you have connected",
        "what": ("Let Jarvis send a hard question to one of the cloud services whose key "
                 "is saved on this PC, instead of answering it here. Choosing this row "
                 "only chooses the service; it switches no answer and sends nothing by "
                 "itself. Each answer costs a little on that account."),
        "cost": ("Every message goes to that company's own servers, under its terms, and "
                 "is billed to your account there. Jarvis stops before a message that "
                 "could pass the monthly money limit you set."),
        "worse": ("Your words leave this PC when a cloud turn is allowed. Anything private, "
                  "tainted, a picture or your screen never goes - those gates run first and "
                  "answer here. The answer is capped, so a thinking model may return its "
                  "working-out instead of an answer."),
        "model": "",
        "lane": {"key": CLOUD_PRESET_ID, "card": "", "port": 0,
                 "words": "the cloud"},
        "context": 0,
        "helper": None,
        "policy": {"prompt": "balanced", "diet": "balanced", "tools": []},
        "measured": None,
        "pending": False,
        "heavy_mode": False,
        "heavy_words": "",
        "apply": {"action": APPLY_ACTION, "switch_route": SWITCH_ROUTE,
                  "apply_route": APPLY_PATH, "lane_start": False, "auto": False,
                  "cloud": True, "needs_provider": True},
    }


def _gate(action: str, detail: dict, prompt: str):
    """`jarvis_gate.check()`, failing CLOSED on any error.

    The same shape `jarvis_big_coder._gate` uses: a gate that cannot be
    reached is a refusal, never an allow. Tests pass their own `gate_check`.
    """
    class _Refused:
        allowed = False
        outcome = "refused"

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate
    except Exception as exc:
        return _Refused(f"the approval gate is not available here ({exc})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:
        return _Refused(f"the approval gate raised {type(exc).__name__}")


def _service_words(API, provider: str) -> tuple:
    """(company, host, model, money line) for ONE service, in plain words."""
    preset = API.PRESETS[provider]
    try:
        model = str(API.model_for(provider)[0] or preset.model)
    except Exception:
        model = preset.model
    try:
        money = API.money_view(provider) or {}
    except Exception:
        money = {}
    return preset.company, preset.host, model, str(money.get("line") or "")


def _cloud_card_text(API, provider: str) -> str:
    """What applying this provider changes, in the owner's own words."""
    company, host, model, money = _service_words(API, provider)
    said = (f"Send hard questions to {company} ({host}, model {model}) instead of "
            f"answering them on this PC. Every message then goes to {company}'s own "
            f"servers, under its terms, and is billed to your account there.")
    if money:
        said += " " + money
    said += (" Anything private, a tainted conversation, a picture or your screen still "
             "never leaves this PC, and nothing on this PC changes until you say yes.")
    return said


def _escalate_card_text(API=None) -> str:
    """The ONE card turning the standing switch ON raises.

    In the owner's own words, and naming the provider when one is chosen: he
    is being asked to let Jarvis spend money and send his words without a
    per-question yes, so the sentence has to say both, and say what still
    does NOT go.
    """
    provider = cloud_chosen()
    who = "the cloud service you chose"
    if provider:
        try:
            import jarvis_chatbot_api as _API
            who = _API.PRESETS[provider].company
        except Exception:
            who = "the cloud service you chose"
    return (f"Jarvis may send a hard question to {who} without asking you first. "
            f"Anything private, a tainted conversation, a picture or your screen still "
            f"never leaves this PC, and the monthly money limit still applies.")


def apply_cloud(*, provider="", gate_check=None) -> tuple:
    """Use ONE cloud provider after the owner's single `change_own_config` card.

    ORDER, and it is the contract: refuse a provider that was not named or
    does not exist (400) -> refuse a service this PC cannot use yet, in the
    PC's own words, BEFORE any card (409: no key, no price, no monthly limit)
    -> raise the ONE card -> only after that yes, write `cloud-choice.json`
    and `presets-choice.json`.

    IT STARTS NO LANE AND SWITCHES NO MODEL. This is the one apply branch that
    must not run `start_lane`/`switch_model`: a cloud preset changes nothing
    local, and starting a GPU lane for it would unload the model the owner is
    using. `test_presets_cloud.py` proves both spies were never called.
    """
    pid = str(provider or "").strip()
    try:
        import jarvis_chatbot_api as API
    except Exception:
        return 503, {"ok": False, "changed": False,
                     "error": ("the cloud services are not set up on this PC, so no "
                               "cloud provider can be chosen")}
    ids = tuple(API.PRESETS)
    if not pid:
        return 400, {"ok": False, "changed": False,
                     "error": f"say which cloud service; the services are {', '.join(ids)}"}
    if pid not in API.PRESETS:
        return 400, {"ok": False, "changed": False,
                     "error": (f"there is no cloud service called {pid!r}; the services "
                               f"are {', '.join(ids)}")}
    why = ""
    try:
        why = str(API.ready_for(pid) or "")
    except Exception:
        why = "this PC could not say whether that service can be used"
    if why:
        return 409, {"ok": False, "changed": False, "error": why,
                     "provider": cloud_chosen()}
    words = _cloud_card_text(API, pid)
    company = API.PRESETS[pid].company
    verdict = (gate_check or _gate)(
        CLOUD_ACTION, {"text": words},
        f"send hard questions to {company} instead of answering them on this PC")
    if not getattr(verdict, "allowed", False):
        return 200, {"ok": False, "changed": False, "provider": cloud_chosen(),
                     "preset": cloud_preset_view(),
                     "outcome": str(getattr(verdict, "outcome", "refused")),
                     "message": "Not changed - the cloud provider stays as it was."}
    previous = choice()
    if not _write_cloud_choice(pid):
        return 503, {"ok": False, "changed": False,
                     "error": ("the chosen cloud provider could not be saved on this PC; "
                               "nothing was changed")}
    if not _write_choice(CLOUD_PRESET_ID):
        return 503, {"ok": False, "changed": False,
                     "error": ("the cloud provider was saved but the chosen preset could "
                               "not be; the next read will say which provider is in use")}
    return 200, {"ok": True, "changed": True, "provider": pid,
                 "preset": cloud_preset_view(), "previous_preset": previous,
                 "cloud": cloud_view(),
                 "message": (f"{company} is the cloud service Jarvis will use. Nothing "
                             f"on this PC's models changed, and nothing is sent until a "
                             f"hard question clears every gate and you have said yes.")}


def cloud_escalate(*, on, gate_check=None) -> tuple:
    """Turn the standing escalation switch on (ONE card) or off (at once).

    ON is a LOOSENING - Jarvis may then spend money and send the owner's words
    with no per-question yes - so it raises ONE `change_own_config` card and
    writes nothing before that yes. OFF is a tightening and is instant, the
    same asymmetry every other switch in this program keeps
    (`set_web_search`: "OFF at once; ON raises the one approval card").

    It refuses ON with no provider chosen, BEFORE a card: a standing yes to a
    service that is not chosen cannot do anything, and a card for a setting
    that cannot work would be a lie.

    Returns (http status, body). `card` says whether a card was raised, so an
    app can say "waiting for your click" instead of guessing.
    """
    want = bool(on)
    now = escalate_on()
    if want == now:
        return 200, {"ok": True, "on": now, "changed": False, "card": False,
                     "message": f"Escalation is already {'on' if want else 'off'}.",
                     "escalate": {"on": now, "why": escalate_why()}}
    if want:
        if not cloud_chosen():
            return 409, {"ok": False, "on": False, "changed": False, "card": False,
                         "error": ("no cloud service has been chosen on this PC yet - "
                                   "pick one in the Presets menu first"),
                         "escalate": {"on": False, "why": escalate_why()}}
        words = _escalate_card_text()
        verdict = (gate_check or _gate)(
            CLOUD_ACTION, {"text": words},
            "let hard questions go to the cloud without asking first")
        if not getattr(verdict, "allowed", False):
            return 200, {"ok": False, "on": now, "changed": False, "card": True,
                         "outcome": str(getattr(verdict, "outcome", "refused")),
                         "message": "Not turned on - Jarvis still asks before every cloud turn.",
                         "escalate": {"on": now, "why": escalate_why()}}
    if not _write_cloud_escalate(want):
        return 503, {"ok": False, "on": now, "changed": False, "card": want,
                     "error": ("the switch could not be saved on this PC; nothing was "
                               "changed"),
                     "escalate": {"on": now, "why": escalate_why()}}
    return 200, {"ok": True, "on": want, "changed": True, "card": want,
                 "message": ("Jarvis may now send a hard question to the cloud without "
                             "asking first. Everything private still stays here."
                             if want else
                             "Jarvis asks before every cloud turn again."),
                 "escalate": {"on": want, "why": escalate_why()}}


def escalate_from_body(body) -> tuple:
    """`POST /api/work/cloud-escalate {"on": true|false}` -> cloud_escalate()."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "expected a JSON object"}
    if "on" not in body:
        return 400, {"ok": False,
                     "error": 'expected {"on": true} or {"on": false}'}
    if not isinstance(body.get("on"), bool):
        return 400, {"ok": False, "error": '"on" must be true or false'}
    return cloud_escalate(on=body["on"])


def _lane_url(key: str) -> str:
    return f"http://127.0.0.1:{LANES[key]['port']}"


def _active_url() -> str:
    import os
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11436").rstrip("/")


def _set_active_url(url: str) -> bool:
    import json
    try:
        from pathlib import Path
        d = _config_dir(); d.mkdir(parents=True, exist_ok=True)
        f = d / "presets-active-lane.json"
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"base_url": str(url).rstrip("/")}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(f)
        return True
    except Exception:
        return False



def _active_lane_key() -> Optional[str]:
    url = _active_url()
    for key, lane in LANES.items():
        if url == f"http://127.0.0.1:{lane['port']}":
            return key
    return None


def live_status() -> dict:
    """GET /api/work's and GET /api/presets' answer: the nine local presets,
    the Cloud row, the cloud provider list and the PC's own escalation switch,
    the detected cards, the questionnaire, the 1/2/3-GPU recommendations, the
    chosen preset and the active lane.

    Reads only, and never switches a model, starts a lane or writes a file -
    the two things it DOES read from the owner's PC are which cloud keys are
    saved (presence only) and this month's spend, both for `cloud`."""
    chosen = choice()
    chosen_preset = by_id(chosen) if chosen else None
    hw = hardware_block()
    lane_key = _active_lane_key()
    lane_info = LANES.get(lane_key) if lane_key else None
    lane_label = ""
    if lane_info:
        lane_label = f"{lane_info['card']} · {lane_info['words']}"
    lane = {
        "key": lane_key,
        "base_url": _active_url(),
        "card": lane_info["card"] if lane_info else "",
        "words": lane_info["words"] if lane_info else "",
        "label": lane_label,
        "ready": lane_info is not None,
        "why": "" if lane_info else "no preset has been applied on this PC yet",
    }
    return {
        "found": f"{len(PRESETS)} focus presets",
        "presets": [p.view() for p in PRESETS],
        # The Cloud row: a TENTH row in the same shape (nine presets + this
        # one), deliberately not in `presets` - both apps' nine-row list stays
        # nine rows (the owner's decision of 2026-10-27: additive keys only, so
        # the phone needs no change at all to keep working).
        "cloud_preset": cloud_preset_view(),
        # The provider in use, the services to choose from, and the PC's own
        # standing escalation switch. See cloud_view().
        "cloud": cloud_view(),
        "old_ids_replaced": list(OLD_IDS),
        # The exact shape the generated contract fixture has (and the one the
        # desktop/Android readers expect): hardware.detected + hardware.questionnaire.
        "hardware": hw,
        "recommendations": recommendations(),
        "chosen": chosen,
        "chosen_preset": chosen,
        "chosen_model": chosen_preset.model if chosen_preset else None,
        "active_lane": {"key": lane_key, "base_url": _active_url()},
        "lane": lane,
        "lane_status": lane,
        "apply_path": APPLY_PATH,
        "switch_path": SWITCH_ROUTE,
        "auto": False,
        "not_a_catalogue": ("This lists the presets that exist; it is not a download "
                            "catalogue. A pending preset waits for its model."),
    }


def apply_preset(preset_id, *, provider=None, cloud_gate=None, start_lane=None,
                 switch_model=None, active_url=None, set_active_url=None,
                 read_choice=None, write_choice=None, rollback_model=None,
                 stop_pooled=None) -> tuple:
    """Apply ONE preset after the owner's single card.

    `preset_id == "cloud"` is its own branch (`apply_cloud`): it raises ONE
    `change_own_config` card for the service, writes the choice, and starts no
    lane and switches no model - so `start_lane`, `switch_model`,
    `rollback_model` and `set_active_url` are never touched on it. Everything
    below this line is the local-preset path, unchanged.

    Order: start the named lane if it is down -> switch the model (the ask card
    lives inside switch_model) -> point chat at it -> save the chosen preset.
    The lane start is BEFORE the card on purpose: a lane that is down cannot
    answer the switch's is_installed read, so switch-first is not possible.
    That means a card the owner DENIES leaves the started lane RUNNING (it
    starts no model and switches nothing) - stated here and in JARVIS-API
    section 145 rather than claiming nothing happens before the card.

    THE CODING PRESET IS THE ONE HEAVY ROW, and since 2026-11-02 its lane
    exists. Its model is 14.8 GB against a 12 GB card and an 8 GB card, so it
    cannot run on either named lane; its lane is "pooled"
    (`jarvis_model_lanes.start_pooled_lane`), ONE Ollama on its own port with
    both cards visible. That start raises the ONE `switch_model` card ITSELF,
    before it unloads anything, because the pause has to be announced before
    the first unload - which is why the heavy path's `switch_model` is
    `_default_adopt` (record the model that is already loaded, no second card,
    no smoke test on a single-card lane) rather than `_default_switch`. See
    `_default_adopt` for the whole argument. A card the owner denies leaves
    NOTHING changed on this path: nothing has been unloaded yet.

    The other direction matters too: a preset that is NOT heavy needs the two
    lanes back, so applying one ENDS the pooled lane first (it unloads the 30B
    and puts both models back exactly as they were). If it cannot end it, the
    apply refuses in plain words rather than trying to load a model on a card
    the heavy one is still holding.

    The contract lane key is "main" (both apps' fixture says so); the model
    starter calls that same lane "everyday" - `_default_start_lane` translates
    through LANE_START_KEYS. `pending` presets refuse before anything happens.
    Once the model HAS switched, any later failure rolls the model back with
    the auto-tier jarvis_models.rollback() as well as restoring the chat lane
    and the remembered preset - and, on the heavy path, stopping the pooled
    lane it started. **Each of those restores is checked** and the answer names
    only the ones that were seen to work; the ones that were not are listed
    under `not_restored` and said in the error (silent-failure audit
    2026-10-27, row 2).
    """
    if str(preset_id or "") == CLOUD_PRESET_ID:
        return apply_cloud(provider=provider, gate_check=cloud_gate)
    p = by_id(preset_id)
    if p is None:
        return 400, {"ok": False, "changed": False,
                     "error": f"no preset called {preset_id!r}; presets are "
                              f"{', '.join(PRESET_IDS)}"}
    if p.pending:
        return 409, {"ok": False, "changed": False, "error": PENDING_LINE}
    heavy = bool(p.heavy_mode)
    start_lane = start_lane or (lambda key: _default_start_lane(key))
    switch_model = switch_model or (
        (lambda ref: _default_adopt(ref)) if heavy
        else (lambda ref: _default_switch(ref)))
    active_url = active_url or _active_url
    set_active_url = set_active_url or _set_active_url
    read_choice = read_choice or choice
    write_choice = write_choice or _write_choice
    rollback_model = rollback_model or _default_rollback_model
    stop_pooled = stop_pooled or _default_stop_pooled
    previous_preset = read_choice()
    previous_lane = active_url()
    target_lane = _lane_url(p.lane)
    if not heavy:
        # The cards must be free before another preset's model can be loaded or
        # asked anything. Ending the pooled lane is the ONLY way back, and it
        # restores both lane models itself. A failure here is said in words and
        # nothing else is changed.
        try:
            ended = stop_pooled()
        except Exception as exc:
            ended = {"ok": False, "ran": True,
                     "reason": f"{type(exc).__name__}: {exc}"}
        if isinstance(ended, dict) and ended.get("ran") and not ended.get("ok"):
            why = ended.get("reason") or "the pooled both-card lane did not stop"
            return 503, {"ok": False, "changed": False,
                         "error": ("the big coding model is still holding both "
                                   f"cards, so this preset was not applied: {why}")}
    try:
        code, start_body = start_lane(p.lane)
    except Exception as exc:
        return 503, {"ok": False, "changed": False,
                     "error": f"the {p.lane} lane could not be started "
                              f"({type(exc).__name__}); nothing was changed"}
    if code not in (200, 202) or not start_body.get("ok", True):
        why = (start_body.get("reason") or start_body.get("error")
               or start_body.get("message") or "the lane did not start")
        if code in (200, 202):
            # A card the owner DENIED (the pooled lane asks before it unloads
            # anything). Nothing was touched, and this is a refusal, not a
            # failure of the machine.
            return 409, {"ok": False, "changed": False,
                         "error": f"{why}; nothing was changed",
                         "outcome": start_body.get("outcome", "refused")}
        return 503, {"ok": False, "changed": False,
                     "error": f"the {p.lane} lane did not start: {why}; nothing was changed"}
    # True only when THIS apply started the pooled lane (not when it was
    # already running before it): a rollback must not end a mode the owner had
    # already turned on.
    started_pooled = heavy and bool(start_body.get("changed"))
    try:
        switched = switch_model(p.model)
    except Exception as exc:
        switched = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
    switched_ok = False

    def rollback(reason: str, code=409) -> tuple:
        # The lane start comes first (a down lane cannot answer the switch's
        # is_installed read), so a refused card can leave a lane RUNNING while
        # nothing was switched - said in the docstring and docs. Once the model
        # HAS switched, every later failure undoes it with the auto-tier
        # rollback, not only the lane pointer and the remembered choice.
        #
        # EVERY restore is checked, and the sentence names only what was
        # OBSERVED to happen (silent-failure audit 2026-10-27, row 2). It used
        # to be `except Exception: pass` on the lane pointer, the choice
        # write's return value never read, and then one sentence asserting all
        # three had been rolled back - so `changed: false` could stand beside a
        # model, a lane or a choice that had really moved. Now: a restore that
        # raised, returned a falsey result or reported `ok: false` is named as
        # NOT restored, and nothing is claimed that was not seen.
        restored: list = []
        failed: list = []

        def outcome(name: str, done: bool) -> None:
            (restored if done else failed).append(name)

        if started_pooled:
            # FIRST, because nothing can be loaded on a card the 30B is still
            # holding, and because the stop puts both lane models back itself.
            try:
                ended = stop_pooled()
                outcome("the pooled lane",
                        isinstance(ended, dict) and ended.get("ok") is True)
            except Exception:
                outcome("the pooled lane", False)
        if switched_ok:
            try:
                rb = rollback_model()
                outcome("the model", isinstance(rb, dict) and rb.get("ok") is True)
            except Exception:
                outcome("the model", False)
        # The chat lane pointer. `_set_active_url` answers a bool, so a falsey
        # answer is a real failure, not a "probably fine".
        try:
            outcome("the chat lane", bool(set_active_url(previous_lane)))
        except Exception:
            outcome("the chat lane", False)
        # The remembered preset: a file write, or its removal when nothing was
        # remembered before this apply (a file that is already gone is the
        # state we wanted, so that is success).
        try:
            if previous_preset is None:
                try:
                    _choice_path().unlink()
                except FileNotFoundError:
                    pass
                outcome("the chosen preset", True)
            else:
                outcome("the chosen preset", bool(write_choice(previous_preset)))
        except Exception:
            outcome("the chosen preset", False)

        def spoken(names) -> str:
            if len(names) == 1:
                return names[0]
            return ", ".join(names[:-1]) + " and " + names[-1]

        if failed:
            if restored:
                note = (f"{spoken(restored)} "
                        f"{'was' if len(restored) == 1 else 'were'} rolled back, but "
                        f"{spoken(failed)} could not be restored")
            else:
                note = f"{spoken(failed)} could not be restored"
            note += ". Check that on the PC before relying on the preset."
        else:
            note = (f"{spoken(restored)} "
                    f"{'was' if len(restored) == 1 else 'were'} rolled back")
        # `changed: false` means the preset is NOT the chosen one. It says
        # nothing about the model, the lane or the choice file - `restored` and
        # `not_restored` are the facts about those, and both are always sent.
        return code, {"ok": False, "changed": False,
                      "error": f"{reason}; {note}",
                      "restored": restored, "not_restored": failed}
    if not isinstance(switched, dict) or not switched.get("ok"):
        return rollback(f"the model switch did not happen: "
                        f"{(switched or {}).get('reason', 'refused')}")
    switched_ok = True
    # Both forward writes are checked AND held: an exception here used to
    # escape `apply_preset` (a 500 the caller could only show as an opaque
    # failure) instead of rolling back and saying what happened.
    try:
        lane_ok = bool(set_active_url(target_lane))
    except Exception:
        lane_ok = False
    if not lane_ok:
        return rollback("the chat lane could not be pointed at the new lane")
    try:
        choice_ok = bool(write_choice(p.id))
    except Exception:
        choice_ok = False
    if not choice_ok:
        return rollback("the chosen preset could not be saved")
    return 200, {"ok": True, "changed": True, "preset": p.view(),
                 "lane": dict(p.lane_info), "base_url": target_lane,
                 "model": p.model, "switched": switched,
                 "previous_preset": previous_preset}


def _default_start_lane(key: str):
    """The preset's own lane, started on demand.

    "pooled" is not one of the PC's logon tasks: it is the ONE Ollama that sees
    both cards, started here and stopped by the next apply that is not heavy
    (`_default_stop_pooled`). `jarvis_model_lanes.start_pooled_lane` raises the
    ONE card for it, before it unloads anything.
    """
    import jarvis_model_lanes
    if str(key) == jarvis_model_lanes.POOLED_KEY:
        return jarvis_model_lanes.start_pooled_lane()
    mapped = LANE_START_KEYS.get(str(key))
    if mapped is None or jarvis_model_lanes.lane_by_key(mapped) is None:
        return 409, {"ok": False, "changed": False,
                     "reason": f"the preset lane {key!r} has no model lane on this PC "
                               f"(known lanes: {', '.join(l.key for l in jarvis_model_lanes.LANES)})"}
    return jarvis_model_lanes.start_lane(mapped)


def _default_stop_pooled() -> dict:
    """End the pooled lane if it is running. Never raises.

    `{"ok", "ran", "reason"}`: `ran` says whether it was running at all, so the
    apply can tell "nothing to do" from "it would not stop". A read of
    `/api/ps` decides that, never a remembered flag - the lane's own model is
    the evidence, which is what survives a backend restart.
    """
    import jarvis_model_lanes
    try:
        running = jarvis_model_lanes.pooled_running()
    except Exception:
        running = False
    if not running:
        return {"ok": True, "ran": False, "reason": ""}
    try:
        code, body = jarvis_model_lanes.stop_pooled_lane()
    except Exception as exc:
        return {"ok": False, "ran": True, "reason": f"{type(exc).__name__}: {exc}"}
    ok = code in (200, 202) and isinstance(body, dict) and bool(body.get("ok"))
    reason = ""
    if not ok:
        reason = (body.get("error") or body.get("message")
                  or "the pooled both-card lane did not stop") if isinstance(body, dict) \
            else "the pooled both-card lane did not stop"
    return {"ok": ok, "ran": True, "reason": reason, "body": body}


def _default_rollback_model():
    import jarvis_models
    return jarvis_models.rollback()


def _default_switch(ref: str):
    import jarvis_models
    return jarvis_models.switch_to(ref, why="preset")


def _default_adopt(ref: str):
    """Record the model the POOLED lane has already loaded. No second card.

    WHY THIS EXISTS, and why it is not `_default_switch`. `jarvis_models.
    switch_to` raises the `switch_model` card - which is right for every
    single-card preset - and then runs the tripwire's smoke test AT
    `jarvis_models.OLLAMA`: the address of the owner's own lane, pinned to ONE
    card (12 GB). A 14 GB coding model cannot be loaded there. By the time this
    is called the model is already loaded on the pooled lane, so `switch_to`
    would either ask that card to hold a second copy or evict the model the
    pooled lane just loaded, and its "did the new model work" answer would be
    about the wrong lane. So the ONE card for this change is the pooled lane's
    own (`jarvis_model_lanes.start_pooled_lane`, action `switch_model`, the
    same `from`/`to`/`why` detail `switch_to` sends), and this writes the same
    record `switch_to` writes - through the model steward's own read and write,
    so the format lives in one place and cannot drift.

    NOTHING ELSE CALLS IT, it raises no card, and it is only reached from the
    heavy-mode branch of `apply_preset` - after that card was approved and
    after the model really loaded (a load that spills past this lane's one
    measured allowance is undone before this runs). If the model steward on
    this PC cannot be read or written, this says so and the apply rolls
    everything back rather than pretending.
    """
    try:
        import time as _time
        import jarvis_models as M
    except Exception as exc:
        return {"ok": False, "ref": ref,
                "reason": f"the model steward is not available ({type(exc).__name__})"}
    read = getattr(M, "_read_state", None)
    write = getattr(M, "_write_state", None)
    if not callable(read) or not callable(write):
        return {"ok": False, "ref": ref,
                "reason": ("this PC's model steward has no recordable model state, "
                           "so the coding model could not be made the one chat uses")}
    try:
        st = read()
        st = dict(st) if isinstance(st, dict) else {}
        cur = st.get("current")
        if cur == ref:
            return {"ok": True, "ref": ref, "unchanged": True,
                    "reason": "already the model in use"}
        at = _time.time()
        st["previous"] = cur
        st["current"] = ref
        st["switched_at"] = at
        st["why"] = "the Coding preset's pooled both-card lane"[:300]
        log = list(st.get("switches") or [])
        log.append({"from": cur, "to": ref, "at": at})
        st["switches"] = log[-int(getattr(M, "MAX_HISTORY", 20) or 20):]
        if not write(st):
            return {"ok": False, "ref": ref,
                    "reason": "could not write the model state file; nothing was recorded"}
    except Exception as exc:
        return {"ok": False, "ref": ref, "reason": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "ref": ref, "previous": cur, "adopted": True,
            "reason": f"the pooled both-card lane now answers as {ref}"}


def apply_from_body(body) -> tuple:
    """`POST /api/work/apply {"preset": "<id>", "provider": "<service>"}`.

    `provider` is read only for the `"cloud"` preset and ignored everywhere
    else, which is what keeps every existing call's bytes meaning exactly what
    they meant before (a body with no `provider` is the same request it was).
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "expected a JSON object"}
    provider = body.get("provider")
    if provider is not None and not isinstance(provider, str):
        return 400, {"ok": False, "error": '"provider" must be text'}
    return apply_preset(body.get("preset"), provider=provider)


def install(Handler, *, origin_ok, token_ok, read_body):
    """Wire GET /api/work and GET /api/presets (the preset contract),
    POST /api/work/apply and POST /api/work/cloud-escalate onto the HUD's
    Handler. Returns the status line the banner prints. Reads nothing from the
    owner's PC except what live_status() reports; it approves nothing: the
    local apply raises the one switch_model ask card itself, and the cloud
    apply and the escalation switch raise the one change_own_config card."""
    original_get = getattr(Handler, "do_GET", None)

    def do_GET(self):
        import json
        path = str(getattr(self, "path", "") or "").split("?", 1)[0]
        if path not in ("/api/work", "/api/presets"):
            if original_get is None:
                return self._send(404, {"error": "not found"})
            return original_get(self)
        if not origin_ok(self):
            return self._send(403, {"error": "cross-origin request refused"})
        if not token_ok(self):
            return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        try:
            out = live_status()
        except Exception as exc:
            return self._send(503, {"available": False,
                                    "error": f"{type(exc).__name__}: {exc}"})
        return self._send(200, out)

    Handler.do_GET = do_GET
    original = getattr(Handler, "do_POST", None)

    def do_POST(self):
        import json
        path = str(getattr(self, "path", "") or "").split("?", 1)[0]
        if path not in (APPLY_PATH, CLOUD_ESCALATE_PATH):
            if original is None:
                return self._send(404, {"error": "not found"})
            return original(self)
        if not origin_ok(self):
            return self._send(403, {"error": "cross-origin request refused"})
        if not token_ok(self):
            return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        try:
            body = json.loads(read_body(self) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            return self._send(400, {"error": str(exc)})
        # The standing escalation switch is its OWN route, because it is its
        # own verb: applying a preset says which model answers, and this says
        # whether Jarvis may ask the cloud with no per-question yes. Both raise
        # a card through the same gate, so neither is reachable without one.
        code, out = (escalate_from_body(body) if path == CLOUD_ESCALATE_PATH
                     else apply_from_body(body))
        return self._send(code, out)

    Handler.do_POST = do_POST
    # Warm the card detection while the HUD finishes starting, so the first
    # GET /api/work does not pay the ~10 s `nvidia-smi` + lane-probe cost. The
    # request path never does it again once a snapshot exists (see above).
    if _warm_on_startup():
        _refresh_detect_cache_async()
    return "presets    ready"

# --------------------------------------------------------------------------
#   Hardware, questionnaire and 1/2/3-GPU recommendations (contract extension)
# --------------------------------------------------------------------------

PRIORITIES = ("speed", "quality", "long_context", "vision")

#: How long a card detection is reused. `jarvis_hardware.detect()` is not cheap
#: (measured at ~10 s on the owner PC), and `GET /api/work` is read by both
#: apps through request timeouts of ~20 s; calling it twice inside one contract
#: build made the live endpoint take ~20.6 s and time the clients out. Cards do
#: not appear or disappear between requests, so a short cache is honest; tests
#: clear it when they need a fresh answer.
DETECT_CACHE_SECONDS = 60.0

#: How long a FIRST call may wait for a detection that is already in flight.
#: The startup warm-up (below) runs off the request path; if the very first
#: request arrives while it is still running, waiting for that one detection is
#: better than starting a second `nvidia-smi`. Bounded so a wedged detector
#: cannot hold a request for ever - past it the call detects for itself.
DETECT_COLD_WAIT_SECONDS = 30.0

#: The cached snapshot: "at" is the monotonic time it was stored, "value" the
#: contract dict, "in_flight" that a background refresh is running. ONE lock
#: guards all three (the detection itself runs outside it).
_DETECT_CACHE = {"at": 0.0, "value": None, "in_flight": False}
_DETECT_LOCK = threading.Lock()
#: Set once a snapshot has been stored, so a first call can wait for a
#: detection already in flight instead of starting a second one.
_DETECT_STORED = threading.Event()


def _copy_detection(value: Optional[dict]) -> dict:
    """The snapshot, copied so callers cannot mutate the cache. None reads as
    the no-cards answer, never as an exception."""
    if value is None:
        return {"count": 0, "cards": [], "source": "jarvis_hardware.detect()"}
    return {**value, "cards": [dict(card) for card in value["cards"]]}


def _clear_detect_cache() -> None:
    """Forget the cached card detection (tests and a hardware change).

    The next read detects SYNCHRONOUSLY: clearing means "I need a fresh answer
    now". Only the ordinary TTL expiry has a stale answer to serve, and only
    that path refreshes in the background.
    """
    with _DETECT_LOCK:
        _DETECT_CACHE["value"] = None
        _DETECT_CACHE["at"] = 0.0
    _DETECT_STORED.clear()


def _detect_cards() -> dict:
    """Run `jarvis_hardware.detect()` and shape the result. The slow part;
    touches no cache state. Never raises; count 0 is said plainly."""
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
            # `total_gib` LAST, not first: it is what jarvis_hardware.detect()
            # actually puts on a card row (jarvis_hardware.py's `rows.append`,
            # "total_gib": s.total_mb / 1024), and it was missing from this
            # tuple until 2026-11-04 - so every card's vram_gib came out None
            # and the hardware screen showed the count with blank sizes. The
            # other three keys are kept first so a caller that already speaks
            # this block's own vocabulary still wins.
            vram = (row.get("vram_gib") or row.get("memory_gib") or row.get("vram")
                    or row.get("total_gib"))
            uuid = row.get("uuid") or row.get("id") or ""
            # The two facts that tell two IDENTICAL cards apart (2026-11-04):
            # `nvidia-smi` reports the PCI address of every card, and whether a
            # monitor is plugged into it. Without them a plan can only say
            # "card 1" and "card 2", which is an array position, not a card.
            # Both stay None/"" when the caller does not know them, so nothing
            # here ever invents a fact.
            pci_id = str(row.get("pci_id") or "")
            monitor = row.get("monitor")
            monitor = monitor if isinstance(monitor, bool) else None
        else:
            name = str(getattr(row, "name", "") or f"card {i}")
            vram = (getattr(row, "vram_gib", None) or getattr(row, "memory_gib", None)
                    or getattr(row, "total_gib", None))
            uuid = str(getattr(row, "uuid", "") or "")
            pci_id = str(getattr(row, "pci_id", "") or "")
            monitor = getattr(row, "monitor", None)
            monitor = monitor if isinstance(monitor, bool) else None
        cards.append({"index": i, "name": str(name),
                      "vram_gib": (round(float(vram), 1) if isinstance(vram, (int, float)) else None),
                      "uuid": uuid, "pci_id": pci_id, "monitor": monitor})
    return {"count": len(cards), "cards": cards,
            "source": "jarvis_hardware.detect()"}


def _store_detection(result: dict) -> None:
    """Remember one detection - the only place the cache is written."""
    with _DETECT_LOCK:
        _DETECT_CACHE["value"] = result
        _DETECT_CACHE["at"] = time.monotonic()
    _DETECT_STORED.set()


def _refresh_detect_cache() -> None:
    """One background refresh: detect off the request thread, then store."""
    try:
        _store_detection(_detect_cards())
    finally:
        with _DETECT_LOCK:
            _DETECT_CACHE["in_flight"] = False


def _refresh_detect_cache_async() -> bool:
    """Start THE background refresh, unless one is already running.

    True when a thread was started, False when a refresh was already in flight
    (or could not start) - so a burst of expired-cache requests starts ONE
    detection, never one per request. Never raises.
    """
    with _DETECT_LOCK:
        if _DETECT_CACHE["in_flight"]:
            return False
        _DETECT_CACHE["in_flight"] = True
    thread = threading.Thread(target=_refresh_detect_cache,
                              name="jarvis-presets-detect", daemon=True)
    try:
        thread.start()
    except Exception:
        with _DETECT_LOCK:
            _DETECT_CACHE["in_flight"] = False
        return False
    return True


def _warm_on_startup() -> bool:
    """Is this the real HUD process? Only the HUD warms the cache at startup: a
    test's `install()` must not run `nvidia-smi` behind the suite that called
    it. `backend/_where.py` sets JARVIS_SUITE_RUNNING for the suites, and the
    HUD is the script named `jarvis_hud.py` (the desktop app starts that file).
    """
    if os.environ.get("JARVIS_SUITE_RUNNING"):
        return False
    main = sys.modules.get("__main__")
    name = os.path.basename(str(getattr(main, "__file__", "") or "")).lower()
    return name == "jarvis_hud.py"


def _detected_cards() -> dict:
    """Every card this PC reports, from jarvis_hardware.detect() - never a
    hardcoded two-card table. Never raises; count 0 is said plainly.

    STALE-WHILE-REVALIDATE. Once a snapshot exists it is served until the TTL
    runs out; when the TTL expires the request STILL gets the old snapshot
    immediately, and one background thread refreshes it. The request thread
    never runs the detection except on the very first call, when there is no
    snapshot to serve - because `detect()` measured ~10 s on the owner PC and
    used to block one `GET /api/work` / `GET /api/presets` every minute.
    """
    with _DETECT_LOCK:
        value = _DETECT_CACHE["value"]
        at = _DETECT_CACHE["at"]
    if value is not None:
        if time.monotonic() - at < DETECT_CACHE_SECONDS:
            return _copy_detection(value)
        _refresh_detect_cache_async()
        return _copy_detection(value)
    # Nothing cached yet, so the first answer has to be a real detection. A
    # startup warm-up may already be running it; wait for that ONE detection
    # rather than starting a second, and detect here if it never lands.
    with _DETECT_LOCK:
        in_flight = _DETECT_CACHE["in_flight"]
    if in_flight:
        _DETECT_STORED.wait(DETECT_COLD_WAIT_SECONDS)
        with _DETECT_LOCK:
            value = _DETECT_CACHE["value"]
        if value is not None:
            return _copy_detection(value)
    result = _detect_cards()
    _store_detection(result)
    return _copy_detection(result)


def hardware_block() -> dict:
    return {"detected": _detected_cards(),
            "questionnaire": {"focus_choices": list(PRESET_IDS),
                              "priority_choices": list(PRIORITIES),
                              "answers": None}}


#: The port the pooled both-cards lane listens on. It is
#: `jarvis_model_lanes.POOLED_PORT` (and `jarvis_big_coder.BIG_PORT`), and it is
#: a literal here on purpose: this module is imported by the backend's start-up
#: banner and by suites that run without the lane module beside them, so it must
#: not pull `jarvis_model_lanes` in at import time. `backend/test_presets.py`
#: pins the three to each other, so the number cannot drift in one place only.
POOLED_PLAN_PORT = 11450


def _card_roles(cards: list) -> dict:
    """Which detected card plays which role in a three-card plan, from the
    PC's own facts - never an array position.

    `main` is the card with the MOST video memory, because the long-context
    everyday model has to fit there (the 12 GB RTX 2060 on this PC). `display`
    is the card `nvidia-smi` says a monitor is plugged into; `headless` is the
    remaining card. Two identical RTX 2080 SUPERs cannot be told apart by
    number, and the plan's own words used to call them "#1" and "#2" as if the
    order in the list were a fact about the machine.

    The three indexes are always integers so every row can be placed even on a
    PC with fewer cards than the plan describes; `display_known` and
    `headless_known` say whether a card was really FOUND for the role, and
    `_role_words` uses them, so a card that is not installed is never described
    as if it were.
    """
    n = len(cards)

    def _vram(card):
        value = card.get("vram_gib")
        return float(value) if isinstance(value, (int, float)) else -1.0

    main = min(range(n), key=lambda i: (-_vram(cards[i]), i)) if n else 0
    rest = [i for i in range(n) if i != main]
    display, display_known = None, False
    for i in rest:
        if cards[i].get("monitor") is True:
            display, display_known = i, True
            break
    if display is None:
        display = rest[0] if rest else main + 1
    headless, headless_known = None, False
    for i in rest:
        if i != display:
            headless, headless_known = i, True
            break
    if headless is None:
        headless = max(main, display) + 1
    return {"main": int(main), "display": int(display),
            "headless": int(headless),
            "display_known": bool(display_known),
            "headless_known": bool(headless_known)}


def _role_words(cards: list, roles: dict, role: str) -> str:
    """One role as the owner reads it: the card's own detected name, its PCI
    address when the PC reports one (the only proof of which twin is which),
    and the fact that decided the role - or, when there is no such card, plain
    words that say it is not installed yet."""
    index = roles[role]
    card = cards[index] if 0 <= index < len(cards) else None
    if card is None:
        return {"main": "a card this PC has not detected",
                "display": "the second 2080 SUPER (not installed yet)",
                "headless": "the headless 2080 SUPER (not installed yet)"}[role]
    name = str(card.get("name") or f"card {index}")
    word = f"{name} (PCI {card['pci_id']})" if card.get("pci_id") else name
    vram = card.get("vram_gib")
    if role == "main":
        return f"{word}, {vram:g} GB" if isinstance(vram, (int, float)) else word
    if role == "display":
        # `monitor` is nvidia-smi's display_active: True when a monitor is
        # plugged in, False when it is not, None when this PC could not say.
        # A known flag needs no explanation; only the UNKNOWN case must be
        # said out loud, so the owner is never told which twin has the monitor
        # when nothing measured it.
        if card.get("monitor") is True:
            return f"{word}, the card with the monitor"
        if card.get("monitor") is False:
            return f"{word}, the card with no monitor"
        return f"{word}; monitor not reported by this PC"
    if card.get("monitor") is False:
        return f"{word}, the card with no monitor"
    return word


def _row(p: Preset, index: int, cards: list, measured: bool,
         best_effort: bool, note: str = "", card_text: str = "") -> dict:
    card = cards[index] if index < len(cards) else None
    return {"preset": p.id, "model": p.model,
            "card_index": index,
            "card": card_text or (card or {}).get("name") or f"card {index}",
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
                elif p.lane == "pooled":
                    # The Coding preset became the 30B coding model on the
                    # pooled lane on 2026-11-02. "main model on the 2060" is
                    # its 2-GPU answer no more: it pauses both lanes and takes
                    # both cards. The measured figures below are its own
                    # (`p.measured`), so only the words were stale.
                    rows[p.id] = _row(p, 0, cards, p.measured is not None,
                                      p.measured is None,
                                      "HEAVY MODE: qwen3-coder-30b-a3b-ud-q3-k-xl on "
                                      "the pooled lane (port 11450) across BOTH cards, "
                                      "started on demand; it pauses the other lanes' "
                                      "models while it runs",
                                      card_text="both cards (pooled lane, port 11450)")
                else:
                    rows[p.id] = _row(p, 0, cards, p.measured is not None,
                                      p.measured is None,
                                      "the agreed 2-GPU mapping: main model on the 2060")
            else:
                # CONFIRMED PLAN (owner, 2026-10-18): three RTX cards, no GTX 1080
                # for compute. THE RULE IS HYBRID (settled 2026-11-04): every
                # everyday preset keeps ONE lane per GPU, and only the Coding
                # preset's heavy mode pools the cards. The text here used to say
                # "lane-per-GPU, never one model split across three cards", which
                # stopped being true on 2026-11-02 when Coding became
                # qwen3-coder-30b-a3b-ud-q3-k-xl on the pooled lane - a model
                # physically too big for one card, by design.
                roles = _card_roles(cards)
                everyday = _role_words(cards, roles, "main")
                display = _role_words(cards, roles, "display")
                headless = _role_words(cards, roles, "headless")
                pooled = (f"qwen3-coder-30b-a3b-ud-q3-k-xl on ONE pooled lane (port "
                          f"{POOLED_PLAN_PORT}) across ALL the cards: it is too big for "
                          f"one card, so applying this preset pauses the other lanes' "
                          f"models, starts that lane, and stops it again when another "
                          f"preset is applied")
                idx = {"general": roles["main"], "general_uncensored": roles["main"],
                       "coding": roles["main"],
                       "fast": roles["display"], "agentic_vision": roles["main"],
                       "reflect": roles["main"], "pictures": roles["main"],
                       "documents": roles["main"], "browser": roles["main"]}[p.id]
                note = {
                    "general": f"{everyday}: main chat/everyday, 196,608 window",
                    "general_uncensored": f"{everyday}: main chat/everyday, 196,608 window",
                    "coding": pooled,
                    "fast": f"{display}: display + Fast/Live lane, qwen3.5:4b",
                    "agentic_vision": f"{everyday}: Agentic+Vision, qwen3.5:9b with images",
                    "reflect": f"{everyday}: Reflective Coach, qwen3.5:9b, 196,608 window",
                    "pictures": f"{everyday}: Pictures & Screens, qwen3.5:9b with images, "
                                f"32,768 window",
                    "documents": f"{everyday}: Documents & Notes, qwen3.5:9b, 196,608 window",
                    "browser": f"{everyday}: Browser & Forms, qwen3.5:9b, 196,608 window",
                }[p.id]
                rows[p.id] = _row(p, idx, cards, False, True, note,
                                  card_text=("all the cards (pooled lane, port "
                                             f"{POOLED_PLAN_PORT})"
                                             if p.id == "coding" else ""))
        by[str(n)] = rows
    roles = _card_roles(cards)
    return {"by_gpu_count": by,
            "basis": ("the agreed 2-GPU mapping is measured; 1 and 3 GPUs are "
                      "best effort and labelled as not tested"),
            "three_gpu_plan": {
                "confirmed": True,
                # One line, two halves, in the order the owner meets them: the
                # everyday shape first, then the on-demand heavy one that is the
                # only exception. "lane per GPU" is kept deliberately - it is
                # what the everyday half IS - so the pin in test_presets.py that
                # has always guarded it still guards something true.
                "layout": ("everyday presets keep one lane per GPU (the everyday "
                           "lane, the monitor card's lane and the headless card's "
                           f"lane); only on-demand heavy Coding pools the cards on "
                           f"port {POOLED_PLAN_PORT}. Agentic + Vision stays on the "
                           "everyday card, not the headless one: the 9B weights plus "
                           "the vision projector need about 7.00 GiB and an 8 GB card "
                           "with no monitor has 6.65 GiB free, so there is no window "
                           "at which it fits a headless card"),
                "cards": [
                    {"role": "everyday lane: main chat / everyday, 196,608 tokens",
                     "card": _role_words(cards, roles, "main"), "context": 196608},
                    {"role": "monitor card's lane: display + Fast/Live, 16,384 tokens",
                     "card": _role_words(cards, roles, "display"), "context": 16384},
                    {"role": "headless card's lane: no 9B lane fits - Agentic+Vision "
                             "needs about 7.00 GiB against 6.65 GiB free, so it stays "
                             "on the everyday card",
                     "card": _role_words(cards, roles, "headless"), "context": 16384},
                ],
                "heavy_pooled": (f"on demand, the Coding preset pauses those three lanes "
                                 f"and loads qwen3-coder-30b-a3b-ud-q3-k-xl on ONE pooled "
                                 f"lane on port {POOLED_PLAN_PORT} across all the cards. "
                                 f"It is too big for one card, so this is the ONE case "
                                 f"where a model is split across cards; every other "
                                 f"preset keeps one lane per GPU."),
                "link_note": ("the third card likely sits on the B550 chipset through an "
                              "M.2 adapter: PCIe 3.0 x4, maybe x2. A slower link costs "
                              "loading time, not a lane; each lane keeps its own model."),
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
