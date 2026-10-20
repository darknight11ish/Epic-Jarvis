"""jarvis_setup.py - the setup questionnaire: a guided path through settings
that already exist.

NEW MODULE, shipped whole (no patch of its own). `setup.patch` adds ONE route
install block to `jarvis_hud.py`, the same shape as `tutorials.patch`:

    GET  /api/setup          the questions, the current values and last answers
    POST /api/setup/plan     {"answers": {...}}          -> what WOULD change
    POST /api/setup/apply    {"answers": {...}, "confirm": true} -> what changed

WHAT THIS IS, AND THE ONE THING IT MUST NEVER BECOME. The owner asked for a
first-run questionnaire (their words, 2026-10-20): "there should be a setup
questionnaire when someone first starts jarvis (or can be filled out again) if
they want jarvis to act a different way overall ... a series of questions with
multiple choices and jarvis sets the settings with a summary for the user at
the end ... that the user can choose to accept afterwards". The design is
`.dsh-scratch/DESIGN-SETUP-QUESTIONNAIRE-2026-10-20.md`.

This module is a GUIDE, not a second settings system. Every option maps to a
function in `jarvis_settings_registry.py` (or, for the "how careful" bundle,
`jarvis_asks_first.py`), and those functions call the EXACT function the
matching Settings control calls - the same tier check, the same approval card,
the same PC-only refusal, the same words. Nothing here writes a settings file
directly, invents a gate action or tier, approves anything, clears a latch,
switches a model, or applies a preset. The preset answer is a RECOMMENDATION
only: applying a preset is the existing `POST /api/work/apply` route and its
own ONE `switch_model` card, and this module never calls it.

THE RULES, kept by construction:

* `plan()` is READ-ONLY. It reads current values and returns what would
  change; it writes nothing and raises no card.
* `apply()` refuses unless `confirm is True`. It then calls the existing
  setters in a fixed, safest-first order, ONE AT A TIME. A loosening setting
  still raises its OWN existing card; a carded change is awaited so a second
  card is never on screen at the same time (no combined/bulk card, ever).
  A denied or missing setting never aborts the rest, and the per-setting
  outcome says exactly what happened in plain words.
* `effect` is "card" exactly where the existing setter would ask. It is read
  from the same machinery the setters use: the action's tier in
  `jarvis-framework.toml` (`jarvis_framework.action_tier`, read-only) and the
  module's own direction rule (e.g. web search ON is one card, OFF is
  instant). If the tier is not "ask" the setter itself refuses (503); plan
  reports that as skipped, never as a change that will happen.

STORAGE. Only the owner's own answers and a completed timestamp, in
`<CONFIG_DIR>/setup.json` (the folder `jarvis_framework.CONFIG_DIR` names -
never the owner's toml, which no route may write). No chat, no facts, no
voice, no files. `jarvis_data_health.py` already parses every `*.json` in that
folder, so a damaged file is reported there; this repository has no
"delete my data" path that removes CONFIG_DIR files to add it to (searched
2026-10-19 - the closest, `jarvis_forget_range.py`, deletes facts/chats and
never settings files).

WHAT IS NOT HERE, on purpose: the desktop Settings page and the phone screens
(S2/S3), the first-run offer, and any UI. `state()` is what they will read.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

try:  # the framework module, when it is there (the real backend, not a suite)
    import jarvis_framework as fw
except Exception:  # pragma: no cover - a suite sets the environment instead
    fw = None

#: The routes `install()` answers. Everything else goes to the server's own
#: handler untouched, so this module stands in front of nothing else.
PATH = "/api/setup"
PLAN_PATH = "/api/setup/plan"
APPLY_PATH = "/api/setup/apply"

ANSWERS_NAME = "setup.json"
ROUTES_GET = (PATH,)
ROUTES_POST = (PLAN_PATH, APPLY_PATH)

#: How long `apply()` waits for ONE raised card before it moves on. The gate's
#: own card timeout is 900 s; this is the questionnaire's patience, not a
#: refusal - a card still waiting when it runs out is left on screen and the
#: outcome says so. Tests inject their own waiter; the environment variable is
#: for a local rehearsal, never set on the owner's PC by anything here.
CARD_WAIT_S = 300.0
CARD_WAIT_ENV = "JARVIS_SETUP_CARD_WAIT_S"
CARD_POLL_S = 0.25

_WRITE_LOCK = threading.Lock()


class Unavailable(Exception):
    """A module this PC does not have - answered in words, never a traceback."""


# ---------------------------------------------------------------------------
#   The questions, in order. Pure data: no import is run at module load.
#
#   Each option carries the changes it means. A change is one of:
#     {"kind": "bool", "setting": <BoolSetting key>, "to": True|False}
#     {"kind": "manner", "to": "warm"|"plain"}
#     {"kind": "card_mode", "to": "start_short"|"always_full"}
#     {"kind": "provider", "to": <search provider id>}
#     {"kind": "asks_first", "action": <jarvis_asks_first action>, "ask": bool}
#     {"kind": "reading_tool", "tool": <reading tool action>, "to": bool}
#     {"kind": "animal", "key": <jarvis_animal switch id>, "to": bool}
#     {"kind": "sky_show", "to": True|False}
#     {"kind": "preset", "to": <jarvis_presets preset id>}   RECOMMENDATION only
#
#   A multi question also accepts the two data-level answers "all" and "none";
#   `plan()` expands them here, so both apps get the same behaviour without
#   special-casing them.
# ---------------------------------------------------------------------------


def _b(setting: str, to: bool) -> dict:
    return {"kind": "bool", "setting": setting, "to": bool(to)}


def _asks(action: str, ask: bool) -> dict:
    return {"kind": "asks_first", "action": action, "ask": bool(ask)}


def _tool(tool: str, to: bool = True) -> dict:
    return {"kind": "reading_tool", "tool": tool, "to": bool(to)}


def _animal(key: str, to: bool = True) -> dict:
    return {"kind": "animal", "key": key, "to": bool(to)}


#: The seven "what asks first" actions the carefulness answer covers. They are
#: jarvis_asks_first.LOOSE's own action names (`_ASKS_FIRST_TARGETS` in the
#: registry has the same seven), kept here as data so this module imports
#: nothing at load time.
ASKS_FIRST_ACTIONS = ("calendar_read", "email_read", "notes_search", "home_read",
                      "append_obsidian_daily", "append_logseq_journal",
                      "create_joplin_note")

#: The four reading tools an app may offer the AI model
#: (jarvis_asks_first.TOOLS_SWITCHABLE's actions).
READING_TOOLS = ("calendar_read", "email_read", "notes_search", "home_read")

#: The seven shared animal switches (jarvis_animal.SWITCHES).
ANIMAL_SWITCHES = ("still", "nods", "focus_buddy", "acks", "petting",
                   "cute_moments", "seasonal")

#: The five work presets, by the ids `jarvis_presets.PRESETS` uses. The answer
#: to "what will you mostly use it for" only RECOMMENDS one; test_setup.py
#: fails if an id here leaves the preset table.
PRESET_IDS = {"general": "General", "general_uncensored": "General Uncensored",
              "coding": "Coding", "agentic_vision": "Agentic + Vision", "fast": "Fast"}

QUESTIONS: tuple = (
    {
        "id": "talk_style",
        "title": "How should Jarvis talk?",
        "help": ("This changes only how answers are worded. It never changes what "
                 "Jarvis does or what it asks you first."),
        "multi": False,
        "options": (
            {"id": "warm", "label": "Warm and brief (default)",
             "detail": "Friendly and short, like a helpful person.",
             "changes": ({"kind": "manner", "to": "warm"},)},
            {"id": "plain", "label": "Plain",
             "detail": "Neutral and businesslike - just the answer.",
             "changes": ({"kind": "manner", "to": "plain"},)},
        ),
    },
    {
        "id": "humour",
        "title": "Should Jarvis use a little humour?",
        "help": ("Occasional light humour when it fits. Never on cards, errors, or "
                 "serious topics."),
        "multi": False,
        "options": (
            {"id": "on", "label": "Yes, a little humour",
             "changes": (_b("humor", True),)},
            {"id": "off", "label": "No, keep it plain (default)",
             "changes": (_b("humor", False),)},
        ),
    },
    {
        "id": "carefulness",
        "title": "How careful should Jarvis be before it acts?",
        "help": ("Which of your things Jarvis may read, and whether it asks first. "
                 "Making it MORE careful happens at once; making it LESS careful asks "
                 "you on its own card, one for each thing."),
        "multi": False,
        "options": (
            {"id": "strict",
             "label": "Strict - ask me first for all seven",
             "detail": "Calendar, email, notes, home status, and writing to Obsidian, "
                       "Logseq and Joplin: always ask first.",
             "changes": tuple(_asks(a, True) for a in ASKS_FIRST_ACTIONS)},
            {"id": "balanced",
             "label": "Balanced - leave my current first-time choices alone",
             "detail": "The setup changes none of the \"what asks first\" rows; you "
                       "can see and change them in Settings, What asks first.",
             "changes": ()},
            {"id": "trusting",
             "label": "Trusting - go ahead without a card",
             "detail": "Jarvis may read and write those seven without asking. Each one "
                       "still asks you on its own card before it changes, and it can "
                       "only be changed from the PC.",
             "changes": tuple(_asks(a, False) for a in ASKS_FIRST_ACTIONS)},
        ),
    },
    {
        "id": "learning",
        "title": "How should Jarvis learn?",
        "help": ("Facts about you and your projects are learned from YOUR own words "
                 "only. Turning learning on, or letting sensitive topics be learned "
                 "automatically, asks you on a card. Turning things off is instant."),
        "multi": False,
        "options": (
            {"id": "learn",
             "label": "Learn automatically (recommended)",
             "detail": "Facts are saved without a per-fact yes; sensitive topics still "
                       "wait for your yes.",
             "changes": (_b("background_learning", True),
                         _b("learn_sensitive_topics", False))},
            {"id": "learn_all",
             "label": "Learn automatically, including sensitive topics",
             "detail": "Health, money and private details about other people are also "
                       "saved without asking. Turning this on raises its own card.",
             "changes": (_b("background_learning", True),
                         _b("learn_sensitive_topics", True))},
            {"id": "learn_off",
             "label": "Don't learn automatically; ask me for each fact",
             "changes": (_b("background_learning", False),
                         _b("learn_sensitive_topics", False))},
        ),
    },
    {
        "id": "reading_tools",
        "title": "Which of your things may the AI model read when you ask?",
        "help": ("These are the tools Jarvis may be offered at all. Turning one on "
                 "shows its own approval card and asks for Windows Hello, on the PC; "
                 "turning one off is instant. All / None applies to the whole list."),
        "multi": True,
        "options": (
            {"id": "calendar", "label": "My calendar",
             "changes": (_tool("calendar_read"),)},
            {"id": "email", "label": "My email",
             "changes": (_tool("email_read"),)},
            {"id": "notes", "label": "My notes",
             "changes": (_tool("notes_search"),)},
            {"id": "home", "label": "Home status",
             "changes": (_tool("home_read"),)},
        ),
    },
    {
        "id": "web_search",
        "title": "Should Jarvis be able to search the web?",
        "help": ("A search still shows its exact words on a card first when private "
                 "things could slip in. Turning web search on raises its one card; "
                 "turning it off is instant."),
        "multi": False,
        "options": (
            {"id": "on", "label": "Yes, search the web when it helps",
             "changes": (_b("web_search", True),)},
            {"id": "off", "label": "No web search",
             "changes": (_b("web_search", False),)},
        ),
    },
    {
        "id": "search_asking",
        "title": "How often should Jarvis ask before a web search?",
        "help": ("By default a search asks only when it could include something "
                 "private. Asking before EVERY search is stricter and instant; turning "
                 "that back off raises a card."),
        "multi": False,
        "options": (
            {"id": "ask_every", "label": "Ask before every search (strictest)",
             "changes": (_b("ask_before_every_search", True),)},
            {"id": "ask_private", "label": "Ask only when private things could slip in (default)",
             "changes": (_b("ask_before_every_search", False),)},
        ),
    },
    {
        "id": "search_provider",
        "title": "Which search service should Jarvis use?",
        "help": ("The service only sees the words of a search Jarvis decides to make. "
                 "Some need a key you add later in Settings; changing this is instant."),
        "multi": False,
        "options": (
            {"id": "searxng", "label": "SearXNG on this PC (default, no key)",
             "changes": ({"kind": "provider", "to": "searxng"},)},
            {"id": "duckduckgo", "label": "DuckDuckGo (no key)",
             "changes": ({"kind": "provider", "to": "duckduckgo"},)},
            {"id": "exa", "label": "Exa (needs a key)",
             "changes": ({"kind": "provider", "to": "exa"},)},
            {"id": "tavily", "label": "Tavily (needs a key)",
             "changes": ({"kind": "provider", "to": "tavily"},)},
            {"id": "brave", "label": "Brave Search (needs a key and a card)",
             "changes": ({"kind": "provider", "to": "brave"},)},
        ),
    },
    {
        "id": "screen_pictures",
        "title": "What may Jarvis look at or draw on this PC?",
        "help": ("Each of these has its own existing card or switch. Picture mode and "
                 "the headless browser each raise their own card when turned on. All / "
                 "None applies to the whole list."),
        "multi": True,
        "options": (
            {"id": "screen_picture", "label": "Picture mode - read the words on my screen",
             "changes": (_b("screen_picture", True),)},
            {"id": "headless_browser", "label": "The headless browser (Obscura)",
             "changes": (_b("headless_browser", True),)},
            {"id": "pictures", "label": "Let me ask Jarvis to make pictures",
             "changes": (_b("pictures", True),)},
            {"id": "sandbox", "label": "Data and maths sandbox (small Python runs)",
             "changes": (_b("sandbox_exec", True),)},
        ),
    },
    {
        "id": "notifications",
        "title": "Which notifications do you want?",
        "help": ("Each switch only changes when this PC or your phone speaks up; none "
                 "of them raises a card, and none of them is ever a way out of your "
                 "own devices. All / None applies to the whole list."),
        "multi": True,
        "options": (
            {"id": "phone", "label": "Read notifications on my phone",
             "changes": (_b("phone_notifications", True),)},
            {"id": "watch", "label": "Show notifications on my smartwatch",
             "changes": (_b("smartwatch_notifications", True),)},
            {"id": "senders", "label": "Show who new emails are from in the morning briefing",
             "changes": (_b("briefing_senders", True),)},
            {"id": "alarm", "label": "Alarm sounds",
             "changes": (_b("pc_alarm_sounds", True),)},
            {"id": "reminder", "label": "Reminder sounds",
             "changes": (_b("pc_reminder_sounds", True),)},
            {"id": "briefing", "label": "A notification when the briefing is ready",
             "changes": (_b("pc_briefing_notification", True),)},
            {"id": "handoff", "label": "\"A website needs you\" notifications",
             "changes": (_b("pc_handoff_notification", True),)},
            {"id": "quiet", "label": "Quiet hours on the PC",
             "changes": (_b("pc_quiet_hours", True),)},
        ),
    },
    {
        "id": "card_size",
        "title": "How much of an approval card should be shown at first?",
        "help": ("This only changes how much of the card is open when it appears: the "
                 "same card, the same words underneath, the same buttons. Instant "
                 "either way."),
        "multi": False,
        "options": (
            {"id": "short", "label": "Start short, with \"Explain more\" (default)",
             "changes": ({"kind": "card_mode", "to": "start_short"},)},
            {"id": "full", "label": "Always show the whole card",
             "changes": ({"kind": "card_mode", "to": "always_full"},)},
        ),
    },
    {
        "id": "voice",
        "title": "Which voice options should be on?",
        "help": ("These only change how Jarvis sounds. This questionnaire never starts "
                 "voice training - that stays your own step, in Settings. All / None "
                 "applies to the whole list."),
        "multi": True,
        "options": (
            {"id": "prompt_coach", "label": "Prompt coach",
             "changes": (_b("prompt_coach", True),)},
            {"id": "face_voice", "label": "Voice follows the face",
             "changes": (_b("voice_follows_face", True),)},
            {"id": "better_voice", "label": "Better voice on the second card",
             "detail": "Turning this on raises its own card, and needs a second card.",
             "changes": (_b("better_voice", True),)},
        ),
    },
    {
        "id": "animal_faces",
        "title": "How should the animal faces behave?",
        "help": ("Small cosmetic switches, shared by the PC and the phone. None of "
                 "them raises a card. All / None applies to the whole list."),
        "multi": True,
        "options": (
            {"id": "still", "label": "Keep the animal still",
             "changes": (_animal("still"),)},
            {"id": "nods", "label": "Listening nods",
             "changes": (_animal("nods"),)},
            {"id": "focus_buddy", "label": "Focus buddy",
             "changes": (_animal("focus_buddy"),)},
            {"id": "acks", "label": "Small acknowledgements",
             "changes": (_animal("acks"),)},
            {"id": "petting", "label": "Petting",
             "changes": (_animal("petting"),)},
            {"id": "cute_moments", "label": "Cute idle moments",
             "changes": (_animal("cute_moments"),)},
            {"id": "seasonal", "label": "Seasonal touches",
             "changes": (_animal("seasonal"),)},
            {"id": "sky", "label": "Show the sun and moon behind the face",
             "changes": ({"kind": "sky_show", "to": True},)},
        ),
    },
    {
        "id": "main_use",
        "title": "What will you mostly use Jarvis for?",
        "help": ("This recommends one of the existing work presets. It changes NO "
                 "model by itself: a preset is only applied by choosing it in the "
                 "preset selector, where its own ONE card asks you."),
        "multi": False,
        "options": (
            {"id": "general", "label": "Everyday questions, writing and life admin",
             "changes": ({"kind": "preset", "to": "general"},)},
            {"id": "agentic", "label": "Browser-and-forms, multi-step work",
             "changes": ({"kind": "preset", "to": "agentic_vision"},)},
            {"id": "coding", "label": "Coding and long jobs with tools",
             "changes": ({"kind": "preset", "to": "coding"},)},
            {"id": "uncensored", "label": "Uncensored answers",
             "changes": ({"kind": "preset", "to": "general_uncensored"},)},
            {"id": "quick", "label": "Quick, short answers",
             "changes": ({"kind": "preset", "to": "fast"},)},
        ),
    },
)

#: question id -> question, for the plan/apply code.
_QUESTIONS_BY_ID = {q["id"]: q for q in QUESTIONS}


# ---------------------------------------------------------------------------
#   Where the answers live, and the one file they write
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def answers_path() -> Path:
    return _config_dir() / ANSWERS_NAME


def _read_saved() -> dict:
    """{"answers": {...}, "completed_at": float|None, "outcomes": [...]} - an
    empty one when nothing was saved or the file is damaged (never raises)."""
    out = {"answers": {}, "completed_at": None, "outcomes": []}
    try:
        doc = json.loads(answers_path().read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(doc, dict):
        return out
    answers = doc.get("answers")
    if isinstance(answers, dict):
        out["answers"] = {str(k): v for k, v in answers.items()
                          if isinstance(v, (str, list, tuple))}
    at = doc.get("completed_at")
    if isinstance(at, (int, float)) and not isinstance(at, bool):
        out["completed_at"] = float(at)
    rows = doc.get("outcomes")
    if isinstance(rows, list):
        out["outcomes"] = [r for r in rows if isinstance(r, dict)][:40]
    return out


def _save_saved(doc: dict) -> bool:
    """Atomic write beside the other settings. False (and nothing changed) on
    any error - the questionnaire must never take a setting down with it."""
    p = answers_path()
    try:
        with _WRITE_LOCK:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n",
                           encoding="utf-8")
            os.replace(tmp, p)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
#   The existing setters, imported lazily (same style as the registry)
# ---------------------------------------------------------------------------


def _registry():
    try:
        import jarvis_settings_registry as R
        return R
    except Exception as exc:
        raise Unavailable(f"the settings registry is not installed ({type(exc).__name__})")


def _module(name: str):
    try:
        return __import__(name)
    except Exception as exc:
        raise Unavailable(f"{name} is not installed ({type(exc).__name__})")


def _tier(action: str) -> str:
    """The action's tier, read-only, exactly as the setters read it."""
    try:
        if fw is not None:
            t = str(fw.action_tier(action))
            return t if t in ("auto", "notify", "ask", "never") else "ask"
    except Exception:
        pass
    return "ask"


def _bool_action(key: str) -> Optional[str]:
    """The gate action a BoolSetting's carded direction uses, from the module
    that owns it - never a second copy of the tier. None for one that never
    asks. Raises Unavailable only for a module this PC does not have, which is
    what the plan reports as "not available on this PC"."""
    try:
        if key in ("background_learning", "learn_sensitive_topics"):
            AL = _module("jarvis_auto_learn")
            return AL.action_for("auto" if key == "background_learning" else "sensitive")
        if key == "web_search":
            return _module("jarvis_search").ACTION_ENABLE
        if key == "ask_before_every_search":
            return _module("jarvis_search").ACTION_ASK_LESS
        if key == "smartwatch_notifications":
            return _module("jarvis_watch_notify").ACTION
        if key == "phone_notifications":
            return _module("jarvis_phone_notifications").ACTION
        if key == "screen_picture":
            return _module("jarvis_screen_picture").ACTION
        if key == "headless_browser":
            return _module("jarvis_browser_engine").ACTION
        if key == "sandbox_exec":
            return _module("jarvis_sandbox_exec").SWITCH_ACTION
        if key == "briefing_senders":
            return _module("jarvis_briefing").SENDERS_ACTION
        if key == "big_coder":
            return _module("jarvis_big_coder").ACTION_ON
        if key == "better_voice":
            return _module("jarvis_voices").BETTER_ACTION
    except Unavailable:
        raise
    except Exception:
        return None
    return None


def _asks_first_action() -> str:
    try:
        return _module("jarvis_asks_first").LOOSEN_ACTION
    except Exception:
        raise Unavailable("jarvis_asks_first.py is not installed")


def _tool_action() -> str:
    try:
        return _module("jarvis_asks_first").ENABLE_TOOL_ACTION
    except Exception:
        raise Unavailable("jarvis_asks_first.py is not installed")


#: Which DIRECTION of each BoolSetting raises its own existing card. Read from
#: the setters' own docstrings/request functions in
#: jarvis_settings_registry.py (e.g. set_web_search: "OFF at once; ON raises
#: the one approval card"; set_ask_every_search: ON instant, OFF one card).
#: Anything absent never asks.
BOOL_CARDED = {
    "background_learning": "on",
    "learn_sensitive_topics": "on",
    "web_search": "on",
    "ask_before_every_search": "off",
    "smartwatch_notifications": "on",
    "phone_notifications": "on",
    "screen_picture": "on",
    "headless_browser": "on",
    "sandbox_exec": "on",
    "briefing_senders": "on",
    "big_coder": "on",
    "better_voice": "on",
}

#: Plain labels for every change, so the summary reads like a person talking.
BOOL_LABELS = {
    "background_learning": "Learn facts automatically",
    "learn_sensitive_topics": "Also remember sensitive topics automatically",
    "prompt_coach": "Prompt coach",
    "web_search": "Web search",
    "ask_before_every_search": "Ask before every web search",
    "smartwatch_notifications": "Smartwatch notifications",
    "phone_notifications": "Phone notifications",
    "screen_picture": "Picture mode",
    "headless_browser": "Headless browser",
    "sandbox_exec": "Data and maths sandbox",
    "pictures": "Making pictures",
    "briefing_senders": "Senders in the morning briefing",
    "big_coder": "Big coding model",
    "pc_alarm_sounds": "Alarm sounds on the PC",
    "pc_reminder_sounds": "Reminder sounds on the PC",
    "pc_briefing_notification": "Briefing notification",
    "pc_handoff_notification": "\"A website needs you\" notification",
    "pc_quiet_hours": "Quiet hours on the PC",
    "humor": "Light humour",
    "voice_follows_face": "Voice follows the face",
    "better_voice": "Better voice on the second card",
}
ASKS_LABELS = {
    "calendar_read": "Reading my calendar",
    "email_read": "Reading my email",
    "notes_search": "Searching my notes",
    "home_read": "Reading home status",
    "append_obsidian_daily": "Writing my Obsidian daily note",
    "append_logseq_journal": "Writing my Logseq journal",
    "create_joplin_note": "Creating a Joplin note",
}
TOOL_LABELS = dict(ASKS_LABELS)
ANIMAL_LABELS = {
    "still": "Keep the animal still",
    "nods": "Listening nods",
    "focus_buddy": "Focus buddy",
    "acks": "Small acknowledgements",
    "petting": "Petting",
    "cute_moments": "Cute idle moments",
    "seasonal": "Seasonal touches",
}
PROVIDER_LABELS = {
    "searxng": "SearXNG on this PC",
    "duckduckgo": "DuckDuckGo",
    "exa": "Exa",
    "tavily": "Tavily",
    "brave": "Brave Search",
}
CARD_MODE_LABELS = {"start_short": "Start short, with \"Explain more\"",
                    "always_full": "Always show the whole card"}
MANNER_LABELS = {"warm": "Warm and brief", "plain": "Plain"}


def change_key(ch: dict) -> str:
    """A stable key for one change, so two questions cannot silently fight."""
    kind = str(ch.get("kind") or "")
    if kind == "bool":
        return f"bool:{ch.get('setting')}"
    if kind == "asks_first":
        return f"asks:{ch.get('action')}"
    if kind == "reading_tool":
        return f"tool:{ch.get('tool')}"
    if kind == "animal":
        return f"animal:{ch.get('key')}"
    if kind == "preset":
        return f"preset:{ch.get('to')}"
    return kind


def change_label(ch: dict) -> str:
    kind = str(ch.get("kind") or "")
    if kind == "bool":
        return BOOL_LABELS.get(str(ch.get("setting")), str(ch.get("setting")))
    if kind == "asks_first":
        return ASKS_LABELS.get(str(ch.get("action")), str(ch.get("action")))
    if kind == "reading_tool":
        return "Offer the AI model: " + ASKS_LABELS.get(str(ch.get("tool")),
                                                       str(ch.get("tool")))
    if kind == "animal":
        return ANIMAL_LABELS.get(str(ch.get("key")), str(ch.get("key")))
    if kind == "sky_show":
        return "Sun and moon behind the face"
    if kind == "manner":
        return MANNER_LABELS.get(str(ch.get("to")), str(ch.get("to")))
    if kind == "card_mode":
        return CARD_MODE_LABELS.get(str(ch.get("to")), str(ch.get("to")))
    if kind == "provider":
        return PROVIDER_LABELS.get(str(ch.get("to")), str(ch.get("to")))
    if kind == "preset":
        return "Work preset (recommendation only)"
    return kind


# ---------------------------------------------------------------------------
#   Reading the CURRENT value of a change. Used by plan() and by apply()'s
#   waiter. A module this PC does not have raises Unavailable; any other read
#   failure is None ("could not read"), never a guessed value.
# ---------------------------------------------------------------------------


def _read_bool(key: str):
    if key in ("background_learning", "learn_sensitive_topics"):
        s = _module("jarvis_auto_learn").settings()
        return bool(s["auto"] if key == "background_learning" else s["auto_sensitive"])
    if key == "prompt_coach":
        s = _module("jarvis_prompt_coach").status()
        return bool(s.get("on", s.get("enabled")))
    if key in ("web_search", "ask_before_every_search"):
        s = _module("jarvis_search").settings()
        return bool(s["enabled"] if key == "web_search" else s["ask_every_time"])
    if key == "smartwatch_notifications":
        return bool(_module("jarvis_watch_notify").settings()["enabled"])
    if key == "phone_notifications":
        return bool(_module("jarvis_phone_notifications").settings()["enabled"])
    if key == "screen_picture":
        return bool(_module("jarvis_screen_picture").settings()["enabled"])
    if key == "headless_browser":
        return bool(_module("jarvis_browser_engine").settings()["obscura"])
    if key == "sandbox_exec":
        return bool(_module("jarvis_sandbox_exec").settings()["enabled"])
    if key == "pictures":
        v = _module("jarvis_settings_registry").pictures_on()
        return v
    if key == "briefing_senders":
        return bool(_module("jarvis_briefing").senders_setting()["on"])
    if key == "big_coder":
        # enabled() opens the switch file; status() would run nvidia-smi and
        # ask the model lanes - far too much for a settings read.
        return bool(_module("jarvis_big_coder").enabled())
    if key == "better_voice":
        return bool(_module("jarvis_voices").status()["better_voice"]["enabled"])
    if key == "humor":
        return bool(_module("jarvis_manner").humor_enabled())
    if key == "voice_follows_face":
        fv = _module("jarvis_voices").face_voice_view()
        return fv.get("enabled") is True
    if key in ("pc_alarm_sounds", "pc_reminder_sounds", "pc_briefing_notification",
               "pc_handoff_notification", "pc_quiet_hours"):
        LIM = _module("jarvis_limits")
        return bool(LIM.value_of(LIM.find(_NOTIFY_LIMIT[key])))
    raise Unavailable(f"no reader for {key}")


_NOTIFY_LIMIT = {
    "pc_alarm_sounds": "notif_alarms",
    "pc_reminder_sounds": "notif_reminders",
    "pc_briefing_notification": "notif_briefing",
    "pc_handoff_notification": "notif_handoff",
    "pc_quiet_hours": "notif_quiet_enabled",
}


def _current(ch: dict):
    """The current value of one change, in the same form `to` uses - or None
    when it cannot be read (not the same as "off")."""
    kind = str(ch.get("kind") or "")
    try:
        if kind == "bool":
            return _read_bool(str(ch.get("setting")))
        if kind == "manner":
            return _module("jarvis_manner").current()
        if kind == "card_mode":
            return _module("jarvis_card_summary").card_mode()
        if kind == "provider":
            return _module("jarvis_search").settings()["provider"]
        if kind == "asks_first":
            tier = _tier(str(ch.get("action")))
            return {"tier": tier, "asks": tier == "ask"}
        if kind == "reading_tool":
            AF = _module("jarvis_asks_first")
            tool = str(ch.get("tool"))
            return AF.real_tool(tool) in AF.tools_enabled_set()
        if kind == "animal":
            return bool(_module("jarvis_animal").values()[str(ch.get("key"))])
        if kind == "sky_show":
            return bool(_module("jarvis_sky").view()["show"])
        if kind == "preset":
            return None
    except Unavailable:
        raise
    except Exception:
        return None
    return None


def _same(ch: dict, current) -> bool:
    """Is `current` already the change's target? False when unreadable."""
    if current is None:
        return False
    kind = str(ch.get("kind") or "")
    if kind == "asks_first":
        cur = bool(current.get("asks")) if isinstance(current, dict) else bool(current)
        return cur == bool(ch.get("ask"))
    if kind in ("bool", "reading_tool", "animal", "sky_show"):
        return bool(current) == bool(ch.get("to"))
    return current == ch.get("to")


def _from_words(ch: dict, current) -> str:
    if current is None:
        return "could not read it now"
    kind = str(ch.get("kind") or "")
    if kind == "bool" or kind == "reading_tool" or kind == "animal" or kind == "sky_show":
        return "on" if current is True else "off" if current is False else str(current)
    if kind == "asks_first":
        cur = bool(current.get("asks")) if isinstance(current, dict) else bool(current)
        return "asks me first" if cur else "goes ahead without asking"
    return str(current)


def _to_words(ch: dict) -> str:
    kind = str(ch.get("kind") or "")
    if kind == "asks_first":
        return "asks me first" if ch.get("ask") else "goes ahead without asking"
    if kind in ("bool", "reading_tool", "animal", "sky_show"):
        return "on" if ch.get("to") is True else "off"
    if kind == "preset":
        return PRESET_IDS.get(str(ch.get("to")), str(ch.get("to")))
    return str(ch.get("to"))


# ---------------------------------------------------------------------------
#   Would the existing rule ask? The same tier machinery the setters use,
#   read-only. "blocked" means the setter itself would refuse (it checks the
#   tier before raising a card), so the app must not promise the change.
# ---------------------------------------------------------------------------


def effect_of(ch: dict, *, tier_of: Optional[Callable[[str], str]] = None) -> str:
    """'instant' | 'card' | 'blocked' | 'recommendation'."""
    tier_of = tier_of or _tier
    kind = str(ch.get("kind") or "")
    if kind == "preset":
        return "recommendation"
    if kind == "asks_first":
        if ch.get("ask"):
            return "instant"                      # stricter: never a card
        try:
            action = _asks_first_action()
        except Unavailable:
            return "blocked"
        return "card" if str(tier_of(action)) == "ask" else "blocked"
    if kind == "reading_tool":
        if not ch.get("to"):
            return "instant"                      # narrowing: never a card
        try:
            action = _tool_action()
        except Unavailable:
            return "blocked"
        return "card" if str(tier_of(action)) == "ask" else "blocked"
    if kind != "bool":
        return "instant"
    direction = "on" if ch.get("to") else "off"
    if BOOL_CARDED.get(str(ch.get("setting"))) != direction:
        return "instant"
    try:
        action = _bool_action(str(ch.get("setting")))
    except Unavailable:
        return "blocked"
    if not action:
        return "instant"
    return "card" if str(tier_of(action)) == "ask" else "blocked"


# ---------------------------------------------------------------------------
#   Answers -> the changes they mean
# ---------------------------------------------------------------------------


def _expand_question(q: dict, selected) -> tuple:
    """(picked option ids, changes, warnings). Handles "all"/"none" here, so
    both apps get the same behaviour from the same data."""
    choices = {str(o["id"]): o for o in q["options"]}
    if isinstance(selected, str):
        selected = [selected]
    if not isinstance(selected, (list, tuple)):
        return [], [], [f"{q['title']}: the answer was not a list of choices"]
    picked, changes, warnings = [], [], []
    for raw in selected:
        sid = str(raw or "").strip()
        if not sid:
            continue
        if sid in ("all", "none"):
            want_on = sid == "all"
            if not q["multi"]:
                warnings.append(f"{q['title']}: \"All\" is only for a choose-any "
                                "question")
                continue
            for o in q["options"]:
                if str(o["id"]) not in picked:
                    picked.append(str(o["id"]))
                for ch in o["changes"]:
                    changes.append(_flip(ch, want_on))
            continue
        if sid not in choices:
            warnings.append(f"{q['title']}: {sid!r} is not one of its choices")
            continue
        if sid in picked:
            continue
        picked.append(sid)
        changes.extend(dict(ch) for ch in choices[sid]["changes"])
    if not q["multi"] and len(picked) > 1:
        warnings.append(f"{q['title']}: one answer only; used the first")
        picked = picked[:1]
        changes = []
        for ch in choices[picked[0]]["changes"]:
            changes.append(dict(ch))
    return picked, changes, warnings


def _flip(ch: dict, want_on: bool) -> dict:
    """The same change for the 'none' side of a multi question: the switch is
    turned OFF. Only the on/off kinds appear in multi questions."""
    out = dict(ch)
    kind = str(out.get("kind") or "")
    if kind in ("bool", "reading_tool", "animal", "sky_show"):
        out["to"] = bool(want_on)
    elif kind == "asks_first":
        out["ask"] = bool(want_on)
    return out


def _read_for(readers, ch: dict, key: str):
    """One current value, through the caller's readers when given (the suite's
    own), otherwise through this module's real readers."""
    if readers is None:
        return _current(ch)
    if callable(readers):
        return readers(ch)
    fn = readers.get(key) if isinstance(readers, dict) else None
    if fn is None:
        return _current(ch)
    return fn(ch)


def _planned(answers, *, tier_of=None, readers=None):
    """[(question, option_id, change, current)] and skipped rows - shared by
    plan() and apply() so a summary and an apply can never disagree."""
    tier_of = tier_of or _tier
    if not isinstance(answers, dict):
        raise ValueError('the answers must be one object, like {"talk_style": "warm"}')
    rows = []
    by_key = {}
    skipped = []
    for q in QUESTIONS:
        if q["id"] not in answers:
            continue
        picked, changes, warnings = _expand_question(q, answers[q["id"]])
        for w in warnings:
            skipped.append({"setting": q["id"], "reason": w})
        for ch in changes:
            key = change_key(ch)
            if key in by_key:
                # A later answer for the same setting wins, in the first
                # position - never silently planned twice.
                i = by_key[key]
                rows[i] = (rows[i][0], rows[i][1], ch, rows[i][3])
                continue
            try:
                cur = _read_for(readers, ch, key)
            except Unavailable:
                skipped.append({"setting": key, "reason":
                                f"{change_label(ch)}: not available on this PC"})
                continue
            except Exception:
                cur = None
            by_key[key] = len(rows)
            rows.append((q, picked[0] if picked else "", ch, cur))
    return rows, skipped


def plan(answers, *, tier_of: Optional[Callable[[str], str]] = None,
         readers=None) -> dict:
    """READ-ONLY: what the answers would change, in plain words. Writes
    nothing, raises nothing, and never claims a carded change is instant."""
    changes, summary, skipped = [], [], []
    recommendation = None
    try:
        rows, skipped = _planned(answers, tier_of=tier_of, readers=readers)
    except ValueError as exc:
        return {"ok": False, "error": str(exc),
                "changes": [], "summary": [], "skipped": [], "recommendation": None}
    for q, _pick, ch, cur in rows:
        kind = str(ch.get("kind") or "")
        if kind == "preset":
            pid = str(ch.get("to"))
            title = PRESET_IDS.get(pid, pid)
            recommendation = {"id": pid, "title": title,
                              "why": "A preset changes models, so it is only a "
                                     "recommendation here - apply it from the preset "
                                     "selector if you want it."}
            summary.append(f"Recommended setup: {title} (this changes no models).")
            continue
        try:
            effect = effect_of(ch, tier_of=tier_of)
        except Unavailable as exc:
            skipped.append({"setting": change_key(ch),
                            "reason": f"{change_label(ch)}: {exc}"})
            continue
        if effect == "blocked":
            skipped.append({"setting": change_key(ch), "reason":
                            f"{change_label(ch)}: this PC's settings file does not ask "
                            "for this change, so it cannot be made from here"})
            continue
        if _same(ch, cur):
            skipped.append({"setting": change_key(ch), "reason":
                            f"{change_label(ch)}: already {_to_words(ch)}"})
            continue
        sentence = (f"{change_label(ch)}: {_from_words(ch, cur)} -> {_to_words(ch)}")
        changes.append({
            "setting": change_key(ch),
            "label": change_label(ch),
            "question": q["id"],
            "from": cur,
            "to": ch.get("to", ch.get("ask")),
            "effect": effect,
            "sentence": sentence,
            "change": ch,
        })
        summary.append(("Will ask you on a card: " if effect == "card"
                        else "Takes effect immediately: ") + sentence)
    return {"ok": True, "changes": changes, "summary": summary,
            "skipped": skipped, "recommendation": recommendation}


# ---------------------------------------------------------------------------
#   Applying one change through the EXISTING setter. Returns
#   {"ok", "waiting", "message", "unavailable"?} - never raises.
# ---------------------------------------------------------------------------


def _apply_change(ch: dict, *, peer=None, local=None) -> dict:
    kind = str(ch.get("kind") or "")
    try:
        R = _registry()
    except Unavailable as exc:
        return {"ok": False, "waiting": False, "unavailable": True,
                "message": f"{change_label(ch)}: {exc}"}
    try:
        if kind == "bool":
            key = str(ch.get("setting"))
            setting = next((b for b in R.BOOL_SETTINGS if b.key == key), None)
            if setting is None:
                return {"ok": False, "waiting": False,
                        "message": f"{change_label(ch)}: this PC does not know that "
                                   "setting"}
            out = setting.set(bool(ch.get("to")), peer=peer, local=local)
        elif kind == "manner":
            out = R.set_manner(str(ch.get("to")), peer=peer, local=local)
        elif kind == "card_mode":
            out = R.set_card_mode(str(ch.get("to")), peer=peer, local=local)
        elif kind == "provider":
            out = R.set_web_search_provider(str(ch.get("to")), peer=peer, local=local)
        elif kind == "asks_first":
            out = R.set_asks_first(str(ch.get("action")), bool(ch.get("ask")),
                                   peer=peer, local=local)
        elif kind == "reading_tool":
            out = R.set_reading_tool(str(ch.get("tool")), bool(ch.get("to")),
                                     peer=peer, local=local)
        elif kind == "animal":
            out = R.set_animal_switch(str(ch.get("key")), bool(ch.get("to")),
                                      peer=peer, local=local)
        elif kind == "sky_show":
            out = R.set_sky_show(bool(ch.get("to")), peer=peer, local=local)
        else:
            return {"ok": False, "waiting": False,
                    "message": f"{change_label(ch)}: nothing to apply"}
    except Exception as exc:
        return {"ok": False, "waiting": False, "failed": True,
                "message": f"{change_label(ch)}: the change could not be made "
                           f"({type(exc).__name__})"}
    ok = bool(getattr(out, "ok", False))
    waiting = bool(getattr(out, "waiting", False))
    message = str(getattr(out, "said", "") or "")
    if getattr(out, "refused_pc_only", False):
        return {"ok": False, "waiting": False, "pc_only": True,
                "message": message or f"{change_label(ch)}: that can only be changed "
                                      "on the PC."}
    return {"ok": ok, "waiting": waiting, "message": message}


# ---------------------------------------------------------------------------
#   Waiting for ONE card, so a second card is never raised on top of it.
#   Each state reader below is the module's own reported state - the same
#   thing its settings screen shows - never a second gate path.
# ---------------------------------------------------------------------------


def _card_state(ch: dict) -> Optional[dict]:
    """{'waiting': bool, 'outcome': str, 'message': str} from the module that
    owns this card, or None when it does not report one."""
    kind = str(ch.get("kind") or "")
    try:
        if kind == "bool":
            key = str(ch.get("setting"))
            if key in ("background_learning", "learn_sensitive_topics"):
                AL = _module("jarvis_auto_learn")
                st = AL.state("auto" if key == "background_learning" else "sensitive")
                return _state_row(st)
            if key == "web_search":
                st = _module("jarvis_search").enable_card_state()
                return {"waiting": bool(st.get("enable_waiting")),
                        "outcome": (st.get("enable_last") or {}).get("outcome", ""),
                        "message": (st.get("enable_last") or {}).get("message", "")}
            if key == "ask_before_every_search":
                return _state_row(_module("jarvis_search").card_state())
            if key == "smartwatch_notifications":
                return _state_row(_module("jarvis_watch_notify").state())
            if key == "phone_notifications":
                return _state_row(_module("jarvis_phone_notifications").state())
            if key == "screen_picture":
                return _state_row(_module("jarvis_screen_picture").view())
            if key == "headless_browser":
                return _state_row(_module("jarvis_browser_engine").view())
            if key == "sandbox_exec":
                return _state_row(_module("jarvis_sandbox_exec").view())
            if key == "briefing_senders":
                return _state_row(_module("jarvis_briefing").senders_status())
            if key == "better_voice":
                row = _module("jarvis_voices").status().get("better_voice") or {}
                return {"waiting": bool(row.get("pending")),
                        "outcome": str((row.get("last") or {}).get("outcome", "")),
                        "message": str((row.get("last") or {}).get("why", ""))}
            # big_coder's setter answers synchronously; no waiting card.
            return None
        if kind == "asks_first":
            AF = _module("jarvis_asks_first")
            st = AF.view(here=True)
            wait = st.get("waiting") or {}
            last = st.get("last") or {}
            return {"waiting": bool(wait),
                    "outcome": str(last.get("outcome", "")),
                    "message": str(last.get("why") or last.get("message") or "")}
        if kind == "reading_tool":
            AF = _module("jarvis_asks_first")
            rows = (AF.tools_status(here=True).get("items") or [])
            row = next((r for r in rows if r.get("id") == str(ch.get("tool"))), None)
            if row is None:
                return None
            return {"waiting": bool(row.get("waiting")),
                    "outcome": str((row.get("last") or {}).get("outcome", "")),
                    "message": str((row.get("last") or {}).get("why", ""))}
    except Exception:
        return None
    return None


def _state_row(st) -> Optional[dict]:
    if not isinstance(st, dict):
        return None
    last = st.get("last") or {}
    if not isinstance(last, dict):
        last = {}
    return {"waiting": bool(st.get("waiting")),
            "outcome": str(last.get("outcome", "")),
            "message": str(last.get("message") or last.get("why") or "")}


_APPROVED = ("approved", "enabled", "changed", "created", "switched", "loosened",
             "added")
_DENIED = ("denied", "timed_out", "withdrawn", "refused", "failed", "error")


def _await_card(ch: dict, deadline: float) -> dict:
    """Wait for the card this change raised. The change itself is already
    raised by the existing setter; this only reads what the module reports and
    the setting's own new value. Never raises and never approves anything."""
    while time.monotonic() < deadline:
        try:
            if _same(ch, _current(ch)):
                return {"state": "asked-and-approved", "message": ""}
        except Exception:
            pass
        st = _card_state(ch)
        if st is not None and not st["waiting"]:
            outcome = str(st.get("outcome") or "").lower()
            if outcome in _APPROVED:
                return {"state": "asked-and-approved", "message": st.get("message", "")}
            if outcome in _DENIED:
                return {"state": "asked-and-denied",
                        "message": st.get("message") or
                        "The card was not approved, so it stays as it was."}
        time.sleep(CARD_POLL_S)
    return {"state": "asked-no-answer",
            "message": "The card is still waiting - answer it and the change is made."}


def _card_wait_s() -> float:
    try:
        want = float(os.environ.get(CARD_WAIT_ENV, "") or CARD_WAIT_S)
    except Exception:
        want = CARD_WAIT_S
    return max(5.0, min(900.0, want))


#: Safest first: tightening and cosmetic changes at once, then the carded ones;
#: within the carded group a single ON-card setting goes before the bundles.
_KIND_ORDER = {"asks_first": 1, "reading_tool": 2, "manner": 3, "card_mode": 4,
               "provider": 5, "animal": 6, "sky_show": 7, "bool": 8, "preset": 9}


def _order(ch: dict, effect: str) -> tuple:
    kind = str(ch.get("kind") or "")
    tightening = (kind == "asks_first" and ch.get("ask")) or \
                 (kind == "reading_tool" and not ch.get("to"))
    return (1 if effect == "card" else 0,
            0 if tightening else 1,
            _KIND_ORDER.get(kind, 8),
            change_key(ch))


def apply(answers, confirm: bool = False, *, peer=None, local=None,
          tier_of: Optional[Callable[[str], str]] = None,
          readers=None, appliers=None,
          wait: Optional[Callable[[dict, float], dict]] = None,
          timeout_s: Optional[float] = None) -> dict:
    """Apply the questionnaire's answers through the existing setters.

    Refuses unless `confirm is True`; the summary must have been accepted by a
    person first. Carded changes are handled ONE AT A TIME: the card that
    change raises is awaited before the next carded change is attempted, so
    there is never a combined approval. A denied, unavailable or failed change
    never aborts the rest, and every outcome is recorded in the same plain
    words the owner reads.

    `wait`, `readers`, `appliers` and `tier_of` exist so the suite can drive
    every branch without a card, a module or the owner's PC; the shipped route
    passes none of them.
    """
    if confirm is not True:
        return {"ok": False, "confirmed": False,
                "error": "Nothing was changed. Send confirm: true to apply these "
                         "settings.",
                "outcomes": [], "completed_at": None}
    try:
        planned = plan(answers, tier_of=tier_of, readers=readers)
    except Exception as exc:
        return {"ok": False, "confirmed": False,
                "error": f"The answers could not be read ({type(exc).__name__}).",
                "outcomes": [], "completed_at": None}
    if not planned.get("ok"):
        return {"ok": False, "confirmed": False,
                "error": planned.get("error") or "The answers could not be read.",
                "outcomes": [], "completed_at": None}
    changes = list(planned["changes"])
    changes.sort(key=lambda row: _order(row["change"], row["effect"]))
    deadline_s = float(timeout_s if timeout_s is not None else _card_wait_s())
    outcomes = []
    applied_ok = 0
    for row in changes:
        ch = row["change"]
        effect = row["effect"]
        if appliers is not None:
            fn = appliers.get(change_key(ch))
            if fn is None:
                out = {"ok": False, "waiting": False,
                       "message": f"{change_label(ch)}: not available on this PC"}
            else:
                try:
                    out = fn(ch) or {}
                except Exception as exc:
                    out = {"ok": False, "waiting": False, "failed": True,
                           "message": f"{change_label(ch)}: failed "
                                      f"({type(exc).__name__})"}
        else:
            out = _apply_change(ch, peer=peer, local=local)
        state = "failed"
        message = str(out.get("message") or "")
        if out.get("unavailable") or out.get("pc_only"):
            state = "not-available"
            message = message or f"{change_label(ch)}: not available on this PC"
        elif out.get("failed"):
            state = "failed"
            message = message or f"{change_label(ch)}: did not change."
        elif out.get("waiting"):
            waiter = wait or _await_card
            try:
                got = waiter(ch, time.monotonic() + deadline_s) or {}
            except Exception:
                got = {"state": "asked-no-answer", "message": ""}
            state = str(got.get("state") or "asked-no-answer")
            message = str(got.get("message") or "")
        elif out.get("ok"):
            state = "changed"
            applied_ok += 1
        else:
            state = "not-changed"
        outcomes.append({"setting": change_key(ch), "label": change_label(ch),
                         "question": row.get("question", ""), "effect": effect,
                         "state": state,
                         "message": message or _outcome_words(state),
                         "waited": bool(out.get("waiting"))})
    saved = _read_saved()
    at = time.time()
    if not _save_saved({"answers": _clean_answers(answers),
                        "completed_at": at,
                        "outcomes": outcomes}):
        return {"ok": False, "confirmed": True,
                "error": "The settings were attempted, but the answers could not be "
                         "saved. Nothing else changed.",
                "outcomes": outcomes, "completed_at": None}
    return {"ok": True, "confirmed": True, "completed_at": at,
            "outcomes": outcomes, "recommendation": planned.get("recommendation"),
            "changed_count": applied_ok,
            "summary": [f"{o['label']}: {o['message']}" for o in outcomes]}


def _outcome_words(state: str) -> str:
    return {
        "changed": "changed.",
        "asked-and-approved": "you approved the card, so it changed.",
        "asked-and-denied": "the card was not approved, so it stays as it was.",
        "asked-no-answer": "the card is still waiting; answer it and it changes.",
        "not-available": "not available on this PC.",
        "not-changed": "not changed.",
        "failed": "did not change.",
    }.get(state, "")


def _clean_answers(answers) -> dict:
    out = {}
    if not isinstance(answers, dict):
        return out
    for q in QUESTIONS:
        if q["id"] in answers:
            v = answers[q["id"]]
            if isinstance(v, str):
                out[q["id"]] = v
            elif isinstance(v, (list, tuple)):
                out[q["id"]] = [str(x) for x in v if isinstance(x, (str, int))]
    return out


# ---------------------------------------------------------------------------
#   What the apps read: the questions, current values and the last answers
# ---------------------------------------------------------------------------


def current_values(*, readers=None) -> dict:
    """Every change's current value, by change_key. Unreadable entries are
    left OUT rather than guessed - an app shows it could not be read."""
    out = {}
    seen = set()
    for q in QUESTIONS:
        for o in q["options"]:
            for ch in o["changes"]:
                key = change_key(ch)
                if key in seen:
                    continue
                seen.add(key)
                if str(ch.get("kind")) == "preset":
                    continue
                try:
                    cur = _read_for(readers, ch, key)
                except Exception:
                    continue
                if cur is None:
                    continue
                if str(ch.get("kind")) == "asks_first" and isinstance(cur, dict):
                    cur = bool(cur.get("asks"))
                out[key] = cur
    return out


def state(*, readers=None) -> dict:
    """GET /api/setup: the questions (in order), the current values, the last
    answers and when they were accepted. Never raises."""
    saved = _read_saved()
    try:
        available = True
        _registry()
    except Unavailable:
        available = False
    return {
        "available": available,
        "questions": [{
            "id": q["id"], "title": q["title"], "help": q["help"],
            "multi": bool(q["multi"]),
            "options": [{"id": o["id"], "label": o["label"],
                         "detail": o.get("detail", "")} for o in q["options"]],
            "all_none": bool(q["multi"]),
        } for q in QUESTIONS],
        "current": current_values(readers=readers),
        "answers": saved["answers"],
        "completed_at": saved["completed_at"],
        "last_outcomes": saved["outcomes"],
        "storage": "setup.json in the Jarvis settings folder",
        "card_wait_s": _card_wait_s(),
        "about": ("A guided path through settings that already exist. Applying is "
                  "one change at a time; anything that loosens a rule still shows "
                  "its own approval card."),
    }


# ---------------------------------------------------------------------------
#   The routes: GET /api/setup, POST /api/setup/plan, POST /api/setup/apply
#   (setup.patch wraps the HUD's Handler with install(); same origin/token
#   checks as every other write).
# ---------------------------------------------------------------------------


def handle_get() -> tuple:
    return 200, state()


def handle_post_plan(body) -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    answers = body.get("answers")
    if not isinstance(answers, dict):
        return 400, {"ok": False,
                     "error": 'send {"answers": {...}} - one answer per question you '
                              "want to change"}
    out = plan(answers)
    return (200 if out.get("ok") else 400), out


def handle_post_apply(body, *, peer=None, local=None) -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    answers = body.get("answers")
    if not isinstance(answers, dict):
        return 400, {"ok": False,
                     "error": 'send {"answers": {...}, "confirm": true}'}
    # `peer`/`local` are the request's own addresses, read by install() the same
    # way owner-check.patch's wrappers read them and passed all the way down to
    # the existing setters. Loosening a rule and offering a reading tool are
    # PC-only: jarvis_asks_first.request_tier/request_tool_enable refuse from
    # another device and fail closed when they cannot tell. `peer is None` is
    # the project's documented IN-PROCESS convention (a direct call, no network
    # request) - never what a routed request should look like.
    out = apply(answers, confirm=body.get("confirm") is True,
                peer=peer, local=local)
    if not out.get("confirmed"):
        return 400, out
    return (200 if out.get("ok") else 500), out


def install(Handler, *, origin_ok, token_ok, read_body):
    """Wire the three /api/setup routes onto the HUD's Handler. Every other
    request goes untouched. Origin and token are checked FIRST, exactly like
    every other route, and nothing is read before both pass."""
    get0 = getattr(Handler, "do_GET", None)
    post0 = getattr(Handler, "do_POST", None)
    if getattr(post0, "_jarvis_setup", False):
        return "  setup      Setup questionnaire (already on)"

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
        split = str(getattr(self, "path", "") or "").split("?", 1)[0].rstrip("/")
        if split != PATH:
            if get0 is None:
                return self._send(404, {"error": "not found"})
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get()
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        split = str(getattr(self, "path", "") or "").split("?", 1)[0].rstrip("/")
        if split not in ROUTES_POST:
            if post0 is None:
                return self._send(404, {"error": "not found"})
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            if split == PLAN_PATH:
                code, out = handle_post_plan(body)
            else:
                # The request's own addresses, read exactly as the asks-first
                # and owner-check routes read them: the existing PC-only rules
                # must see where this request really came from, not the
                # in-process `None` convention (which says "this PC").
                peer = (getattr(self, "client_address", None) or ("",))[0]
                try:
                    local = self.connection.getsockname()[0]
                except Exception:
                    local = None
                code, out = handle_post_apply(body, peer=peer, local=local)
        except Exception as exc:
            code, out = 503, {"ok": False, "available": False,
                              "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_setup = True
    do_POST._jarvis_setup = True
    Handler.do_GET = do_GET
    Handler.do_POST = do_POST
    return ("  setup      Setup questionnaire "
            "(GET /api/setup, POST /api/setup/plan, POST /api/setup/apply)")
