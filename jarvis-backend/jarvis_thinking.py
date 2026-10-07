"""jarvis_thinking.py - Per-model thinking levels (Section 5.5).

Builds: a setting per model (everyday model, second-card lane's model,
third-card lane's model) - Off / Quick / Deep / Auto; only levels the loaded
model supports (read from Ollama /api/show capabilities); default Off;
voice answers always fast; change needs no card; both apps show one row per
running model; changeable by voice/chat ("think harder"); Auto decides per
question and must be tested first (tool-eval style, tools/tool_eval/).
Plain words explain that thinking uses conversation room. Thinking text
is never shown, saved or learned from.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

OFF = "off"
QUICK = "quick"
DEEP = "deep"
AUTO = "auto"
LEVELS = (OFF, QUICK, DEEP, AUTO)
DEFAULT = OFF

TITLE = "Thinking levels"
DETAIL = ("Lets Jarvis think through complex questions before answering. "
          "Thinking spends some of your conversation room.")
NOTICE = ("Thinking uses conversation room: when Jarvis thinks before answering, "
          "the thinking tokens take up part of the conversation room.")

WHY = {
    OFF: "Off. Answers directly without an extra thinking step.",
    QUICK: "Quick thinking. Takes a brief thinking pass before answering.",
    DEEP: "Deep thinking. Takes more time and room to think through complex problems.",
    AUTO: "Automatic. Decides whether to think based on the question (simple questions stay fast, complex questions think deeply).",
}

# Mapping to OpenAI-compatible reasoning_effort supported by Ollama
REASONING_MAP = {
    OFF: {"reasoning_effort": "none"},
    QUICK: {"reasoning_effort": "low"},
    DEEP: {"reasoning_effort": "high"},
}

_CONFIG_LOCK = threading.Lock()
_CAP_CACHE: Dict[Tuple[str, str], Tuple[List[str], float]] = {}
_CAP_TTL = 300.0  # 5 minutes
_CAP_OVERRIDE: Dict[Tuple[str, str], List[str]] = {}


def _config_dir() -> Path:
    fw = sys.modules.get("jarvis_framework")
    if fw is None:
        try:
            import jarvis_framework as fw
        except Exception:
            fw = None
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "thinking.json"


def _read_settings() -> dict:
    try:
        p = settings_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"everyday": DEFAULT, "second": DEFAULT, "third": DEFAULT}


def _write_settings(data: dict) -> None:
    with _CONFIG_LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _ollama_url() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def model_capabilities(model: str, ollama_url: Optional[str] = None) -> List[str]:
    """Reads the capabilities list from Ollama's /api/show for the given model.
    Returns e.g. ['tools', 'thinking', 'vision'] or []. Cached for 5 minutes.
    """
    url = (ollama_url or _ollama_url()).rstrip("/")
    if (url, model) in _CAP_OVERRIDE:
        return list(_CAP_OVERRIDE[(url, model)])
    now = time.monotonic()
    hit = _CAP_CACHE.get((url, model))
    if hit and (now - hit[1] < _CAP_TTL):
        return list(hit[0])

    caps = []
    try:
        req = urllib.request.Request(
            f"{url}/api/show",
            data=json.dumps({"model": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "capabilities" in data:
                c = data.get("capabilities")
                if isinstance(c, list):
                    caps = [str(x).lower().strip() for x in c]
    except Exception:
        pass

    _CAP_CACHE[(url, model)] = (caps, now)
    return caps


def supports_thinking(model: str, ollama_url: Optional[str] = None) -> bool:
    """True if Ollama reports the 'thinking' capability for this model."""
    caps = model_capabilities(model, ollama_url)
    return "thinking" in caps


def supported_levels(model: str, ollama_url: Optional[str] = None) -> Tuple[str, ...]:
    """Tuple of levels this model supports: ('off', 'quick', 'deep', 'auto') if capable,
    or ('off',) if not.
    """
    if supports_thinking(model, ollama_url):
        return LEVELS
    return (OFF,)


def get_level(role_or_model: str) -> str:
    """Returns the configured thinking level for a role ('everyday', 'second', 'third')
    or specific model name. Defaults to 'off'.
    """
    settings = _read_settings()
    # Check exact key, then role aliases
    if role_or_model in settings:
        val = settings[role_or_model]
        if val in LEVELS:
            return val
    # Fallback to everyday if not found
    return DEFAULT


def set_level(role_or_model: str, level: str, model_name: Optional[str] = None,
              ollama_url: Optional[str] = None) -> Tuple[int, dict]:
    """Updates the thinking level for a role or model without requiring an approval card.
    Rejects levels the model does not support in plain words.
    """
    level = str(level).lower().strip()
    if level not in LEVELS:
        return 400, {"error": f"Thinking level must be one of {', '.join(LEVELS)}."}

    # If model_name is known, verify capabilities
    check_model = model_name or (role_or_model if ":" in role_or_model else None)
    if check_model:
        supp = supported_levels(check_model, ollama_url)
        if level not in supp:
            return 400, {
                "error": f"The model \"{check_model}\" does not support thinking controls; only \"off\" is available."
            }

    settings = _read_settings()
    settings[role_or_model] = level
    _write_settings(settings)
    return 200, {
        "ok": True,
        "target": role_or_model,
        "level": level,
        "message": f"Thinking set to {level}."
    }


# Auto question decision heuristic
_MATH_LOGIC_PATTERN = re.compile(
    r"\b(solve|calculate|equation|derivative|integral|proof|prove|theorem|"
    r"algorithm|complexity|puzzle|riddle|step[-\s]by[-\s]step|deduce|infer|"
    r"debug|refactor|trace\s+this|why\s+is\s+this\s+(?:bug|error|failing))\b",
    re.I
)
_ANALYTICAL_PATTERN = re.compile(
    r"\b(compare\s+and\s+contrast|pros\s+and\s+cons|trade[-\s]offs?|"
    r"analyze|architectural|root\s+cause|critique|evaluate)\b",
    re.I
)
_SIMPLE_PATTERN = re.compile(
    r"^(hi|hello|hey|good\s+morning|good\s+evening|how\s+are\s+you|"
    r"what\s+time|what\s+is\s+the\s+capital|who\s+(?:is|was)|thanks|thank\s+you|"
    r"ok|okay|yes|no)\b",
    re.I
)


def decide_auto(question: str) -> str:
    """Decides thinking level for a question when set to 'auto'.
    Simple conversational/lookup questions -> 'off'.
    Analytical/comparisons -> 'quick'.
    Deep logic/math/code/puzzles -> 'deep'.
    """
    q = (question or "").strip()
    if not q or len(q) < 15 or _SIMPLE_PATTERN.search(q):
        return OFF
    if _MATH_LOGIC_PATTERN.search(q):
        return DEEP
    if _ANALYTICAL_PATTERN.search(q):
        return QUICK
    # Long or multi-sentence questions benefit from quick thinking pass
    if len(q) > 200 or q.count("?") > 1:
        return QUICK
    return OFF


def reasoning_parameters(model: str, question: str = "", *,
                         spoken: bool = False,
                         ollama_url: Optional[str] = None,
                         role: str = "everyday") -> dict:
    """Computes the reasoning_effort parameters to pass to Ollama chat.
    Voice answers (spoken=True) are always fast (forced to 'none').
    Defaults to 'none' when off or when model does not think.
    """
    if spoken:
        # Voice answers are always fast
        return {"reasoning_effort": "none"}

    if not supports_thinking(model, ollama_url):
        return {"reasoning_effort": "none"}

    lvl = get_level(role)
    if role != model and model in _read_settings():
        lvl = get_level(model)

    if lvl == AUTO:
        lvl = decide_auto(question)

    return REASONING_MAP.get(lvl, {"reasoning_effort": "none"})


def running_models(ollama_url: Optional[str] = None) -> List[dict]:
    """Lists currently running models across everyday Ollama and second/third card lanes."""
    url = ollama_url or _ollama_url()
    rows = []

    # 1. Everyday model
    everyday_model = "jarvis-primary"
    try:
        import jarvis_agent
        if hasattr(jarvis_agent, "chat_model"):
            everyday_model = jarvis_agent.chat_model() or everyday_model
    except Exception:
        pass

    everyday_supp = supported_levels(everyday_model, url)
    everyday_lvl = get_level("everyday")
    rows.append({
        "role": "everyday",
        "name": "Everyday chat",
        "model": everyday_model,
        "level": everyday_lvl,
        "supported": list(everyday_supp),
        "why": WHY.get(everyday_lvl, WHY[OFF]),
    })

    # 2. Second card lane
    try:
        import jarvis_second_card as SC
        st = SC.status()
        lane = st.get("lane", {})
        if lane.get("state") == "running" and lane.get("model"):
            m = lane["model"]
            s_supp = supported_levels(m, lane.get("url"))
            s_lvl = get_level("second")
            rows.append({
                "role": "second",
                "name": "Second card lane",
                "model": m,
                "level": s_lvl,
                "supported": list(s_supp),
                "why": WHY.get(s_lvl, WHY[OFF]),
            })
        # 3. Third card lane
        third = st.get("third", {})
        t_lane = third.get("lane", {})
        if t_lane.get("state") == "running" and t_lane.get("model"):
            tm = t_lane["model"]
            t_supp = supported_levels(tm, t_lane.get("url"))
            t_lvl = get_level("third")
            rows.append({
                "role": "third",
                "name": "Third card lane",
                "model": tm,
                "level": t_lvl,
                "supported": list(t_supp),
                "why": WHY.get(t_lvl, WHY[OFF]),
            })
    except Exception:
        pass

    return rows


def status(ollama_url: Optional[str] = None) -> dict:
    """GET /api/thinking: returns status and running models list."""
    return {
        "title": TITLE,
        "detail": DETAIL,
        "notice": NOTICE,
        "models": running_models(ollama_url),
    }


def handle_get(ollama_url: Optional[str] = None) -> Tuple[int, dict]:
    return 200, status(ollama_url)


def handle_set(body: Any, ollama_url: Optional[str] = None) -> Tuple[int, dict]:
    """POST /api/thinking: {"role": "everyday"|"second"|"third", "level": "off"|"quick"|"deep"|"auto"}
    or {"model": "...", "level": "..."}.
    """
    if not isinstance(body, dict):
        return 400, {"error": "Expected JSON object with 'level' and 'role' or 'model'."}

    level = body.get("level")
    if not level:
        return 400, {"error": "'level' field is required."}

    target = body.get("role") or body.get("model") or "everyday"
    model_name = body.get("model")
    return set_level(target, level, model_name=model_name, ollama_url=ollama_url)


def reset_for_tests() -> None:
    with _CONFIG_LOCK:
        _CAP_CACHE.clear()
        _CAP_OVERRIDE.clear()
        p = settings_path()
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
