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
    heavy_mode: bool = False
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
             "coding jobs: the 30B coding model across both cards (heavy mode), with "
             "the coding lane arriving as part of the lane patch.",
        cost="HEAVY MODE: it holds BOTH GPUs (14 GB, 100% GPU across both cards) and "
             "evicts the other lanes' models while it works; cold load is about 32.1 s. "
             "Measured 76.2 tok/s median eval and 6/6 on the coding rubric. It is not a "
             "single-card model.",
        worse="Heavy mode means the Fast/Live and Agentic+Vision lanes lose their models "
              "while it runs, and its apply path needs a pooled both-GPU lane - the "
              "pinned 2060/2080S lanes cannot host it. Until that lane patch lands: "
              "\"heavy mode: both cards; lane support arriving\". No single-card use "
              "is claimed.",
        model="qwen3-coder-30b-a3b-ud-q3-k-xl", lane="main", context=28672,
        prompt="coding", diet="coding", heavy_mode=True,
        tools=("code", "files"),
        measured={"tok_s": 76.2, "rubric": "6/6 coding rubric", "size_gib": 14.0,
                  "gpu_use": "100% GPU across both cards", "cold_load_s": 32.1,
                  "spill_gib": 0.0,
                  "source": "measurement 2026-10-18: 76.2 tok/s median eval, 6/6 "
                            "coding rubric, 14 GB, 100% GPU across both cards, cold "
                            "load ~32.1 s, no CPU spill"},
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
#   Applying a preset (presets.patch, 2026-10-18)
# --------------------------------------------------------------------------

CHOICE_FILE = "presets-choice.json"
APPLY_PATH = "/api/work/apply"
HEAVY_MODE_LINE = ("heavy mode needs the both-card lane, arriving later; nothing was "
                   "changed")
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
    """GET /api/work's new answer: the five presets (the one contract both app
    UIs render), the detected cards, the questionnaire, the 1/2/3-GPU
    recommendations, the chosen preset and the active lane. Reads only - it
    starts nothing, switches nothing and writes nothing."""
    chosen = choice()
    chosen_preset = by_id(chosen) if chosen else None
    hw = hardware_block()
    return {
        "found": f"{len(PRESETS)} focus presets",
        "presets": [p.view() for p in PRESETS],
        "old_ids_replaced": list(OLD_IDS),
        "hardware": hw["detected"],
        "questionnaire": hw["questionnaire"],
        "recommendations": recommendations(),
        "chosen": chosen,
        "chosen_preset": chosen,
        "chosen_model": chosen_preset.model if chosen_preset else None,
        "active_lane": {"key": _active_lane_key(), "base_url": _active_url()},
        "apply_path": APPLY_PATH,
        "switch_path": SWITCH_ROUTE,
        "auto": False,
        "not_a_catalogue": ("This lists the presets that exist; it is not a download "
                            "catalogue. A pending preset waits for its model."),
    }

def apply_preset(preset_id, *, start_lane=None, switch_model=None,
                 active_url=None, set_active_url=None, read_choice=None,
                 write_choice=None, rollback_model=None) -> tuple:
    """Apply ONE preset after the owner's single switch_model card.

    Order: start the named lane if it is down -> switch the model (the ask card
    lives inside switch_model) -> point chat at it -> save the chosen preset.
    The lane start is BEFORE the card on purpose: a lane that is down cannot
    answer the switch's is_installed read, so switch-first is not possible.
    That means a card the owner DENIES leaves the started lane RUNNING (it
    starts no model and switches nothing) - stated here and in JARVIS-API
    section 145 rather than claiming nothing happens before the card.

    The contract lane key is "main" (both apps' fixture says so); the model
    starter calls that same lane "everyday" - `_default_start_lane` translates
    through LANE_START_KEYS. `pending` presets and heavy mode refuse before
    anything happens. Once the model HAS switched, any later failure rolls the
    model back with the auto-tier jarvis_models.rollback() as well as restoring
    the chat lane and the remembered preset.
    """
    p = by_id(preset_id)
    if p is None:
        return 400, {"ok": False, "changed": False,
                     "error": f"no preset called {preset_id!r}; presets are "
                              f"{', '.join(PRESET_IDS)}"}
    if p.pending:
        return 409, {"ok": False, "changed": False, "error": PENDING_LINE}
    if p.heavy_mode:
        return 409, {"ok": False, "changed": False, "error": HEAVY_MODE_LINE}
    start_lane = start_lane or (lambda key: _default_start_lane(key))
    switch_model = switch_model or (lambda ref: _default_switch(ref))
    active_url = active_url or _active_url
    set_active_url = set_active_url or _set_active_url
    read_choice = read_choice or choice
    write_choice = write_choice or _write_choice
    rollback_model = rollback_model or _default_rollback_model
    previous_preset = read_choice()
    previous_lane = active_url()
    target_lane = _lane_url(p.lane)
    try:
        code, start_body = start_lane(p.lane)
    except Exception as exc:
        return 503, {"ok": False, "changed": False,
                     "error": f"the {p.lane} lane could not be started "
                              f"({type(exc).__name__}); nothing was changed"}
    if code not in (200, 202) or not start_body.get("ok", True):
        why = start_body.get("reason") or start_body.get("error") or "the lane did not start"
        return 503, {"ok": False, "changed": False,
                     "error": f"the {p.lane} lane did not start: {why}; nothing was changed"}
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
        model_note = ""
        if switched_ok:
            try:
                rb = rollback_model()
                if not (isinstance(rb, dict) and rb.get("ok")):
                    model_note = " (the model rollback did not report ok)"
            except Exception as exc:
                model_note = f" (the model rollback failed: {type(exc).__name__})"
        try:
            set_active_url(previous_lane)
        except Exception:
            pass
        try:
            if previous_preset is None:
                try:
                    _choice_path().unlink()
                except Exception:
                    pass
            else:
                write_choice(previous_preset)
        except Exception:
            pass
        return code, {"ok": False, "changed": False,
                      "error": f"{reason}; chat lane, chosen preset and model were "
                               f"rolled back{model_note}"}
    if not isinstance(switched, dict) or not switched.get("ok"):
        return rollback(f"the model switch did not happen: "
                        f"{(switched or {}).get('reason', 'refused')}")
    switched_ok = True
    if not set_active_url(target_lane):
        return rollback("the chat lane could not be pointed at the new lane")
    if not write_choice(p.id):
        return rollback("the chosen preset could not be saved")
    return 200, {"ok": True, "changed": True, "preset": p.view(),
                 "lane": dict(p.lane_info), "base_url": target_lane,
                 "model": p.model, "switched": switched,
                 "previous_preset": previous_preset}


def _default_start_lane(key: str):
    import jarvis_model_lanes
    mapped = LANE_START_KEYS.get(str(key))
    if mapped is None or jarvis_model_lanes.lane_by_key(mapped) is None:
        return 409, {"ok": False, "changed": False,
                     "reason": f"the preset lane {key!r} has no model lane on this PC "
                               f"(known lanes: {', '.join(l.key for l in jarvis_model_lanes.LANES)})"}
    return jarvis_model_lanes.start_lane(mapped)


def _default_rollback_model():
    import jarvis_models
    return jarvis_models.rollback()


def _default_switch(ref: str):
    import jarvis_models
    return jarvis_models.switch_to(ref, why="preset")


def apply_from_body(body) -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "expected a JSON object"}
    return apply_preset(body.get("preset"))


def install(Handler, *, origin_ok, token_ok, read_body):
    """Wire GET /api/work (the new preset contract) and POST /api/work/apply
    onto the HUD's Handler. Returns the status line the banner prints. Reads
    nothing from the owner's PC except what live_status() reports; it approves
    nothing: switch_to raises the one switch_model ask card itself."""
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
        if path != APPLY_PATH:
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
        code, out = apply_from_body(body)
        return self._send(code, out)

    Handler.do_POST = do_POST
    return "presets    ready"

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
                    "general_uncensored": "2060 12 GB: main chat/everyday, 196k",
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
