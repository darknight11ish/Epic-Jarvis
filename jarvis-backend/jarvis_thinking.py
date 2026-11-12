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

# --------------------------------------------------------------------------
#   WHEN Jarvis thinks: the owner's choice, in two plain words (2026-10-11)
# --------------------------------------------------------------------------
#
# The level above says HOW HARD a model may think. It never said WHEN, and the
# everyday model is becoming one that thinks before it answers by default
# (`qwen3.5:9b`; `qwen3:8b` and `ornith:9b` behave the same way). Measured on
# this PC today: thinking left on with a normal answer allowance spent every
# token reasoning and returned an EMPTY answer on all three test questions
# (`done_reason: "length"`, `content: ""`); with thinking off the same
# questions were answered correctly in 0.29 s. So "when" is the owner's
# choice, not a default this file picked for them:
#
#   WHEN_ASKED - ordinary answers are written straight away; thinking happens
#                on the questions the owner asks for it (the "Think" key on
#                the phone, the same flag from the desktop, or a level the
#                owner set by hand being asked for).
#   ALWAYS     - every answer may think first, as a model that thinks by
#                default would. The owner is choosing the wait and the
#                conversation room it costs, and that is said in plain words
#                beside the choice.
#
# THE SAFE ONE IS THE ONE THAT IS ASSUMED. A `thinking.json` that is missing,
# empty, truncated or unreadable must never be what makes an answer come back
# blank, so every failure to read this setting falls to WHEN_ASKED: the turn
# answers directly, with thinking off. Falling back to ALWAYS would be falling
# back to the exact fault this setting exists to prevent - and the owner would
# have no way to tell a wrong answer from no answer at all. For the same
# reason WHEN_ASKED is what an ordinary turn gets when nothing was ever
# chosen: a fresh backend answers everything, and a model that would have
# thought first only does so when asked.
WHEN_ASKED = "when_asked"
ALWAYS = "always"
WHEN_MODES = (WHEN_ASKED, ALWAYS)
WHEN_DEFAULT = WHEN_ASKED
WHEN_KEY = "when"

#: Where jarvis_thinking remembers that a role's level is the OWNER'S pick
#: rather than this file's starting value - only ever needed for "off", which
#: is both. A short list of role or model names, in the same small file. Keys
#: are ALWAYS stored, so it can never be mistaken for a model's level.
_CHOSEN_KEY = "chosen"

WHEN_LABELS = {
    WHEN_ASKED: "Only when I ask",
    ALWAYS: "Always",
}

WHEN_WHY = {
    WHEN_ASKED: ("Ordinary answers are written straight away. Jarvis thinks "
                 "only on the questions you ask him to think about."),
    ALWAYS: ("Jarvis may think before every answer. Answers can take longer, "
             "and thinking uses part of your conversation room."),
}

WHEN_TITLE = "When Jarvis thinks"
WHEN_DETAIL = ("Thinking is the extra step some models take before answering. "
               "It spends part of your conversation room.")

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


def _default_settings() -> dict:
    return {"everyday": DEFAULT, "second": DEFAULT, "third": DEFAULT}


def _read_settings() -> dict:
    """The setting file as a dict, or the defaults. `when` (WHEN_KEY) is kept
    here with the model levels - one small file the owner can read, not a
    second store - and is always present in what is returned. A file that is
    missing, empty, truncated or unreadable gives the defaults, which include
    WHEN_ASKED; see the WHEN_ASKED block above for why that is the safe one."""
    try:
        p = settings_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if data.get(WHEN_KEY) not in WHEN_MODES:
                    data[WHEN_KEY] = WHEN_DEFAULT
                return data
    except Exception:
        pass
    return dict(_default_settings(), **{WHEN_KEY: WHEN_DEFAULT})


def _levels_only(data: dict) -> dict:
    """`data` without the two bookkeeping keys: the per-model levels, and
    nothing else. `get_level` walks this, so neither the owner's WHEN choice
    ("when_asked" is not a level) nor the list of levels he picked by hand can
    ever be read as a model name with a level of its own."""
    return {k: v for k, v in data.items() if k not in (WHEN_KEY, _CHOSEN_KEY)}


#: The level stored for a model nobody has chosen anything for. "off" is both
#: a real choice and this starting value, and the two are told apart in
#: _saved_levels() below - see its own note.
_UNSET = DEFAULT


def _saved_levels() -> dict:
    """Only the levels the owner really CHOSE - never the starting values.

    The difference matters in exactly one place: "off" is both a level the
    owner can pick and what a model nobody has picked anything for answers
    with, and the two must not be confused. (_read_settings fills a missing
    file with "off" for each role, so "off" being written down is not evidence
    that anybody chose it.) A level the owner actively set to "off" through
    set_level() is remembered by that function in `chosen`, and counts as a
    choice; an "off" that is only this project's starting value does not, so
    it cannot block a question the owner asks for thinking about. A missing or
    unreadable file has no choices in it at all."""
    try:
        p = settings_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                picked = data.get(_CHOSEN_KEY)
                picked = picked if isinstance(picked, list) else []
                return {k: v for k, v in _levels_only(data).items()
                        if v in LEVELS and (v != _UNSET or k in picked)}
    except Exception:
        pass
    return {}


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
    settings = _levels_only(_read_settings())
    # Check exact key, then role aliases
    if role_or_model in settings:
        val = settings[role_or_model]
        if val in LEVELS:
            return val
    # Fallback to everyday if not found
    return DEFAULT


def get_when() -> str:
    """WHEN Jarvis thinks - WHEN_ASKED or ALWAYS. Never raises, and never
    returns anything but one of the two: a missing, damaged or unreadable
    setting reads as WHEN_ASKED, the one that cannot make an answer come back
    blank. See the WHEN_ASKED block above."""
    try:
        when = _read_settings().get(WHEN_KEY)
        if when in WHEN_MODES:
            return when
    except Exception:
        pass
    return WHEN_DEFAULT


def set_when(when: str) -> Tuple[int, dict]:
    """Changes WHEN Jarvis thinks. Needs no approval card, like a level: it
    changes how much of one answer's conversation room may be spent, on a
    model already loaded on this PC, and it opens no new way out of it."""
    when = str(when or "").lower().strip()
    if when not in WHEN_MODES:
        return 400, {"error": f"'when' must be one of {', '.join(WHEN_MODES)}."}
    try:
        settings = _read_settings()
        settings[WHEN_KEY] = when
        _write_settings(settings)
    except Exception as exc:
        return 503, {"error": f"Could not save that just now ({type(exc).__name__})."}
    return 200, {"ok": True, "when": when, "label": WHEN_LABELS.get(when, when),
                 "message": f"Jarvis thinks {WHEN_LABELS.get(when, when).lower()}.",
                 "why": WHEN_WHY.get(when, "")}


def asked_for_this_turn(request: Any) -> bool:
    """Did the app ask for thinking on THIS question alone? `think: true` on
    the chat request, and nothing else turns it on: never "yes", never 1,
    never a string - the same rule the chat route's own flags follow
    (`temporary` is read the same way). Anything that is not the app's own
    request (None, a list, a string) is not a request to think."""
    if not isinstance(request, dict):
        return False
    return request.get("think") is True


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
    # A level written here is a level the OWNER picked - including "off", which
    # is otherwise indistinguishable from this file's own starting value (see
    # _saved_levels). Remembered by name, in the same small file.
    picked = settings.get(_CHOSEN_KEY)
    picked = list(picked) if isinstance(picked, list) else []
    if role_or_model not in picked:
        picked.append(role_or_model)
    settings[_CHOSEN_KEY] = picked
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
                         role: str = "everyday",
                         per_turn: bool = False) -> dict:
    """Computes the reasoning_effort parameters to pass to Ollama chat.
    Voice answers (spoken=True) are always fast (forced to 'none').
    Defaults to 'none' when off or when model does not think.

    `per_turn` is the owner asking for thinking on THIS question only
    (`think: true` on the chat request; jarvis_agent passes
    asked_for_this_turn(request)). It decides one thing and one thing only:
    whether a turn the owner did NOT ask about may think. The three rules
    above it are untouched by it - a spoken answer, a model that cannot
    think, and a level the owner set to "off" all answer directly whether or
    not this question was asked for. Asked for, a role with no level of its
    own thinks quickly rather than not at all, so "Think" on the phone does
    something on a PC where no level was ever picked.
    """
    if spoken:
        # Voice answers are always fast. First, so nothing below can undo it.
        return {"reasoning_effort": "none"}

    if not supports_thinking(model, ollama_url):
        return {"reasoning_effort": "none"}

    # The level this turn would use, and whether the owner really set one. The
    # role is what the settings screen writes; a level stored under the model's
    # own name wins when the two differ, exactly as before.
    #
    # "off" is also what a model nobody has chosen anything for answers with.
    # That is NOT a choice, so it never blocks a turn that may think: what
    # stands in its place is a brief pass, not "off" (which would make a
    # question the owner asked for - and, on "Always", every question - do
    # nothing at all) and not "deep" (which would spend far more room than was
    # asked for).
    levels = _saved_levels()

    def set_for(key: str) -> bool:
        return key in levels and levels[key] in LEVELS

    if role != model and set_for(model):
        lvl, chosen = get_level(model), True
    elif set_for(role):
        lvl, chosen = get_level(role), True
    else:
        lvl, chosen = QUICK, False

    if lvl == OFF and chosen:
        # The owner set this model to answer directly. Never overridden - not
        # even by a question that asked for thinking.
        return {"reasoning_effort": "none"}

    # WHEN. The one place the per-question flag is read.
    if not per_turn and get_when() != ALWAYS:
        return {"reasoning_effort": "none"}

    if lvl == AUTO:
        lvl = decide_auto(question)

    return REASONING_MAP.get(lvl, {"reasoning_effort": "none"})


def _why_for(level: str) -> str:
    """One row's plain words. A level the owner picked that will not be used
    yet says so, rather than promising thinking the next answer will not do:
    the two lines below are the only place this is worked out, so the row and
    the setting can never disagree."""
    why = WHY.get(level, WHY[OFF])
    if level != OFF and get_when() != ALWAYS:
        return (why + " Jarvis will think like this only on the questions you "
                       "ask him to think about.")
    return why


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
        "why": _why_for(everyday_lvl),
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
    """GET /api/thinking: returns status and running models list.

    `when` is WHEN thinking happens at all (the owner's two-choice setting,
    2026-10-11) and `when_choices` the two choices with their plain words, so
    both apps can draw the same row. A PC whose backend is older than this
    answers neither field, and the apps show the per-model rows only."""
    when = get_when()
    return {
        "title": TITLE,
        "detail": DETAIL,
        "notice": NOTICE,
        "when": when,
        "when_title": WHEN_TITLE,
        "when_detail": WHEN_DETAIL,
        "when_choices": [
            {"id": mode, "label": WHEN_LABELS[mode], "why": WHEN_WHY[mode],
             "selected": mode == when}
            for mode in WHEN_MODES
        ],
        "models": running_models(ollama_url),
    }


def handle_get(ollama_url: Optional[str] = None) -> Tuple[int, dict]:
    return 200, status(ollama_url)


def handle_set(body: Any, ollama_url: Optional[str] = None) -> Tuple[int, dict]:
    """POST /api/thinking:
      {"when": "when_asked"|"always"} - WHEN Jarvis thinks (the owner's
        two-choice setting), or
      {"role": "everyday"|"second"|"third", "level": "off"|"quick"|"deep"|"auto"}
      or {"model": "...", "level": "..."} - how hard one model may think.
    One of the two per request. A body carrying `when` never changes a level,
    and one carrying a level never changes `when`."""
    if not isinstance(body, dict):
        return 400, {"error": "Expected JSON object with 'level' and 'role' or 'model', or with 'when'."}

    if "when" in body:
        return set_when(body.get("when"))

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
