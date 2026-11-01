"""jarvis_model_knowledge.py - what Jarvis is running, and what it could run.

THE OWNER'S REQUEST (2026-10-31). Asked "what ai model do you have?", Jarvis
answered *"I don't know what specific AI model I'm running on - my capabilities
come from the tools..."*, while the HUD telemetry right beside it said
"ANSWERED BY qwen3.5:9b". It must know the model it is running, the presets and
their effects, the local models, their measured speed and honest limits, and it
must switch a preset or load a model when asked - through the EXISTING one-card
routes, never by approving anything itself.

WHERE EVERY FACT COMES FROM (nothing here is invented):
  * the presets, their model, lane, context, `what`/`cost`/`worse` sentences and
    their measured figures come from `jarvis_presets.py` - the same rows both
    apps render;
  * the model everyday chat uses comes from `jarvis_models.current_model()`
    (the owner's own file on this PC), with `jarvis_hardware._current_model()`
    and the chosen preset's model as fallbacks;
  * the installed-model list comes from the owner's `jarvis_models` when it can
    list models, else from the local Ollama `/api/tags` read the hardware
    module already makes;
  * a measured benchmark comes from `jarvis_model_recommendations`'s store
    (`model-recommendations.json`), written by this PC's own benchmark route;
    the presets' `measured` fields are the fallback with their stated context;
  * release dates are NOT recorded in this tree. These are local Ollama tags
    (e.g. `qwen3.5:9b`) and no official release page for that exact tag is
    recorded anywhere here, so every answer says "not recorded" instead of
    inventing a date. Pros and cons are the preset rows' own measured words.
  * a model switch is `jarvis_models.switch_to(ref, why="chat")` - the same
    function the preset card and the Models page use, which raises the same ONE
    `change_own_config` card. A preset applies through
    `jarvis_presets.apply_from_body({"preset": id})`, the existing route body.
    This module approves nothing and writes nothing itself.

Pure standard library. No network of its own; every live read is delegated to a
module that already owns it, guarded so an older PC answers honestly instead of
raising.
"""
from __future__ import annotations

from typing import Optional

#: WHERE THE FACTS COME FROM, quoted beside the answers that use them.
SOURCES = {
    "presets": "jarvis_presets.py (the shared preset contract both apps render)",
    "current_model": "jarvis_models.current_model() on this PC, else "
                     "jarvis_hardware._current_model(), else the chosen preset",
    "installed": "jarvis_models's own list, else the local Ollama /api/tags",
    "benchmarks": "model-recommendations.json (this PC's own benchmark route), "
                  "else the preset row's measured fields",
    "release_dates": "not recorded",
}

#: The one honest sentence about release dates, when a date is asked for.
RELEASE_NOTE = ("The release date is not recorded on this PC. These are local "
                "Ollama tags, and no official release page for the exact tag is "
                "recorded in this tree - so this is 'not recorded', not a guess.")

#: The sentence when no benchmark exists for a model.
NO_BENCHMARK = ("No benchmark is recorded on this PC for {model}. Brain, Models "
                "can measure an installed model - one short request, one "
                "measurement at a time.")

#: What the model page/route is, for a question about where the controls live.
WHERE_MODELS = ("Brain, Models (and Settings, Hardware and models) on this PC; "
                "the phone's Brain has the same model list read-only, and a "
                "switch or install there is the same one card.")

#: The one card a switch or preset apply raises, said plainly.
CARD_WORDS = ("Nothing switches until you answer the ONE approval card on your "
              "PC (Windows Hello for a risky one).")


def _presets():
    try:
        import jarvis_presets as P
        return list(P.PRESETS)
    except Exception:
        return []


def presets() -> list:
    """The nine shared preset rows, as the two apps render them."""
    return [p.view() for p in _presets()]


def preset_by_name(name) -> Optional[dict]:
    """A preset by id, title or one of its own trigger words; None if no match."""
    want = " ".join(str(name or "").lower().replace("-", " ").split())
    if not want:
        return None
    for p in _presets():
        words = {p.id.replace("_", " ").lower(), p.title.lower(), p.focus.lower()}
        words.update(str(w).lower() for w in (p.words or ()))
        words.update(str(w).lower() for w in (p.strong or ()))
        if want == p.id.replace("_", " ").lower() or want == p.title.lower():
            return p.view()
        for word in words:
            if word and (want == word or want in word.split()):
                return p.view()
    if want in ("cloud", "the cloud"):
        return {"id": "cloud", "title": "Cloud", "model": "", "what":
                "One cloud service answers a question you allow, inside the monthly cap.",
                "worse": "", "cost": "", "measured": None, "pending": False}
    return None


def chosen_preset_id() -> str:
    try:
        import jarvis_presets as P
        return str(P.choice() or "")
    except Exception:
        return ""


def current_preset() -> Optional[dict]:
    pid = chosen_preset_id()
    if not pid:
        return None
    for row in presets():
        if row.get("id") == pid:
            return row
    return None


def current_model() -> str:
    """The model everyday chat uses, tried in the same order as the PC itself."""
    try:
        import jarvis_models as M
        name = M.current_model()
        if name:
            return str(name)
    except Exception:
        pass
    try:
        import jarvis_hardware as H
        name = H._current_model()
        if name:
            return str(name)
    except Exception:
        pass
    chosen = current_preset()
    if chosen and chosen.get("model"):
        return str(chosen["model"])
    return ""


def installed_models() -> list:
    """Installed model tags, from the owner's model manager or the local Ollama."""
    try:
        import jarvis_models as M
        for fn in ("installed_models", "installed", "list_models"):
            read = getattr(M, fn, None)
            if callable(read):
                got = read()
                if isinstance(got, (list, tuple, set)):
                    names = [str(x) for x in got if str(x or "").strip()]
                    if names:
                        return sorted(dict.fromkeys(names))
    except Exception:
        pass
    try:
        import jarvis_hardware as H
        url = H._main_url()
        tags = H._tags(url) if url else None
        if tags:
            return sorted(str(t) for t in tags if str(t or "").strip())
    except Exception:
        pass
    return []


def benchmarks() -> dict:
    """The PC's measured benchmark rows, keyed by model ref."""
    try:
        import jarvis_model_recommendations as R
        return dict(R.load_store().get("benchmarked") or {})
    except Exception:
        return {}


def bench_for(model) -> Optional[dict]:
    """One measured row for `model`: the PC's own benchmark first, then the preset
    row's measured fields. Always says WHICH source and WHICH context it is."""
    ref = str(model or "")
    rows = benchmarks()
    row = rows.get(ref)
    if row:
        out = dict(row)
        out["source"] = "benchmark route on this PC"
        out["measured_here"] = True
        return out
    for preset in presets():
        if str(preset.get("model") or "") == ref and preset.get("measured"):
            out = dict(preset["measured"])
            out["source"] = "the preset row's measured figures"
            out["measured_here"] = True
            out["context_tokens"] = preset.get("context")
            return out
    return None


def _tokens_words(row: dict) -> str:
    rate = row.get("tokens_per_s") or row.get("tok_s")
    if rate is None:
        return ""
    text = f"{float(rate):g} tokens a second"
    if row.get("tok_s_16k"):
        text += f" ({float(row['tok_s_16k']):g} at 16k tokens)"
    return text


def speed_words(model) -> str:
    """The measured speed sentence for one model, with units and provenance."""
    row = bench_for(model)
    if not row:
        return NO_BENCHMARK.format(model=model)
    words = _tokens_words(row)
    if not words:
        return NO_BENCHMARK.format(model=model)
    text = words
    context = row.get("context_tokens")
    if context:
        text += f" at {int(context):,} tokens"
    vram = row.get("vram_gb", row.get("vram_gib"))
    if vram:
        text += f", holding {float(vram):g} GB of the card"
    measured_at = row.get("measured_at")
    if measured_at:
        try:
            import datetime
            stamp = datetime.datetime.fromtimestamp(float(measured_at))
            text += f", measured on this PC on {stamp.date().isoformat()}"
        except Exception:
            pass
    source = row.get("source") or SOURCES["benchmarks"]
    return text + f" ({source})."


def model_facts(model) -> dict:
    """Everything the tree honestly holds about one model ref, no invention."""
    ref = str(model or "")
    preset = next((p for p in presets() if str(p.get("model") or "") == ref), None)
    measured = dict(preset.get("measured") or {}) if preset else {}
    return {
        "model": ref,
        "preset": preset.get("title") if preset else "",
        "preset_id": preset.get("id") if preset else "",
        "speed": bench_for(ref),
        "size_gib": measured.get("size_gib") or measured.get("disk_gib"),
        "licence": measured.get("licence"),
        "params_b": measured.get("params_b"),
        "release": "",
        "release_note": RELEASE_NOTE,
        "pros": preset.get("what") if preset else "",
        "cons": preset.get("worse") if preset else "",
        "cost": preset.get("cost") if preset else "",
        "source": SOURCES["presets"] if preset else "",
    }


def recommendation(task) -> Optional[dict]:
    """The preset whose own trigger words fit the task words; None if no fit."""
    words = " ".join(str(task or "").lower().split())
    if not words:
        return None
    best = None
    for preset in presets():
        score = 0
        for word in list(preset.get("words") or []) + list(preset.get("strong") or []):
            word = str(word or "").lower()
            if word and word in words:
                score = max(score, len(word))
        if score and (best is None or score > best[0]):
            best = (score, preset)
    return best[1] if best else None


def preset_model_words(preset) -> str:
    """What one preset changes: its model, lane, context, and the honest cost."""
    row = preset if isinstance(preset, dict) else {}
    lane = row.get("lane") or {}
    card = lane.get("card") or ""
    model = row.get("model") or "no model (cloud)"
    context = row.get("context")
    parts = [f"{row.get('title') or row.get('id')}: {row.get('what') or ''}".strip()]
    if model:
        text = f"It runs {model}"
        if card:
            text += f" on {card}"
        if context:
            text += f" at {int(context):,} tokens"
        parts.append(text + ".")
    if row.get("cost"):
        parts.append(str(row["cost"]))
    if row.get("worse"):
        parts.append("What it is worse at: " + str(row["worse"]))
    helper = row.get("helper") or {}
    if helper.get("model"):
        parts.append(f"It uses {helper['model']} as a helper.")
    return " ".join(p for p in parts if p)


def apply_preset(preset_id) -> tuple:
    """The EXISTING preset-apply route body; the one card decides. Returns (code, body)."""
    try:
        import jarvis_presets as P
        return P.apply_from_body({"preset": preset_id})
    except Exception as exc:
        return 503, {"ok": False, "changed": False,
                     "error": f"this PC's Jarvis cannot apply presets ({type(exc).__name__})."}


def switch_model(model) -> tuple:
    """The EXISTING model switch, the same function the preset card calls.

    `jarvis_models.switch_to(ref, why=...)` raises the ONE `change_own_config`
    card; this module never approves it. An older PC without that function
    answers honestly instead of pretending anything switched.
    """
    ref = str(model or "").strip()
    if not ref:
        return 400, {"ok": False, "error": "which model should I switch to?"}
    try:
        import jarvis_models as M
    except Exception:
        return 503, {"ok": False, "error":
                     "This PC's Jarvis cannot switch models from chat. " + WHERE_MODELS}
    fn = getattr(M, "switch_to", None)
    if not callable(fn):
        return 503, {"ok": False, "error":
                     "This PC's Jarvis cannot switch models from chat. " + WHERE_MODELS}
    try:
        got = fn(ref, why="chat")
    except Exception as exc:
        return 503, {"ok": False, "error": f"the model switch failed ({type(exc).__name__}); "
                     "nothing was changed."}
    if isinstance(got, tuple) and len(got) == 2 and isinstance(got[1], dict):
        return int(got[0]), dict(got[1])
    if isinstance(got, dict):
        return 200, got
    return 200, {"ok": True, "model": ref, "waiting": True}


def prompt_line() -> str:
    """The one honest line for the model's system prompt: model, and preset."""
    model = current_model()
    preset = current_preset()
    if not model and not preset:
        return ""
    if model and preset:
        return (f"You are running as {model} on this PC, under the "
                f"\"{preset.get('title')}\" preset.")
    if model:
        return f"You are running as {model} on this PC."
    return (f"The active preset on this PC is \"{preset.get('title')}\"; the exact "
            "model it runs is not recorded here.")
