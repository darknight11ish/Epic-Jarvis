"""jarvis_companion.py - the desktop companion's settings and its honest answers.

WHAT IS HERE. The settings store behind the desktop-companion chat answers, plus
the pure data helpers a renderer would need if the companion's visual half were
ever built: the golden-spiral point set for the avatar sphere, the wave formula
for a sound-reactive surface, a shaper for a step-by-step guidance description,
and a shaper for a 3D card.

WHAT IS NOT HERE, AND IS NOT CLAIMED (corrected 2026-11-12, the PR #1229 review).
This module does not draw anything, does not open a window, does not read another
program's controls, does not recognise text in a picture, and does not click,
type or take a screenshot. No window of the desktop app and no screen of either
app draws an avatar, a guidance overlay, a cursor ask bar or a 3D card. So the
chat answers below say plainly that the visual half is NOT BUILT in this copy of
Jarvis, and that the switches only record a preference - never a success, never
a maybe.

THE ONE SAFETY LIST. This module keeps no list of programs of its own.
`denied_app_reason()` asks the screen-control module, which owns the ONE enforced
hard denylist (password vaults, terminals, the sign-in and UAC prompts, the
security-settings windows) and the ONE approval-card path. A second, shorter list
here is exactly the shape that lets a program through the moment the two
disagree, so there is not one (review finding H1, 2026-11-13).

Provenance: the design was inspired by the open-source Roamies system. The
numbers and the words are ours; the drawing is not built.

Standard library only. All state changes are non-destructive.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

#: The one sentence a companion answer says when it describes a thing that does
#: not exist in this build. Nothing here reports a success for it.
NOT_BUILT = ("The desktop companion's drawing and screen half is not built in "
             "this copy of Jarvis.")

#: Default companion settings. Every switch ships OFF: nothing draws any of
#: these, so a switch that read ON would be the fake presence the answers below
#: stopped claiming (2026-11-12).
DEFAULT_CONFIG: Dict[str, Any] = {
    "avatar_enabled": False,
    "avatar_style": "sphere",  # "sphere", "reticle", "classic", "off"
    "avatar_size": "default",  # "default", "small", "cursor"
    "avatar_voice_reactive": False,
    "screen_guidance_enabled": False,
    "guidance_tone": "accent",  # "accent", "teal", "amber", "coral", "lilac", "sky", "lime"
    "guidance_auto_advance": False,  # wait for user click before advancing step
    "cursor_ask_bar_enabled": False,
    "cursor_ask_bar_hotkey": "ctrl+shift",
    "interactive_3d_cards": False,
}

#: Valid avatar styles
AVATAR_STYLES = ("sphere", "reticle", "classic", "off")

#: Valid avatar sizes
AVATAR_SIZES = ("default", "small", "cursor")

#: Valid visual tones
VALID_TONES = ("accent", "teal", "amber", "coral", "lilac", "sky", "lime", "red", "white")

#: Valid 3D card shapes
SHAPES_3D = ("sphere", "box", "cylinder", "cone", "torus")

#: Valid 3D animations
MOTIONS_3D = ("spin", "orbit", "slide", "pulse")

#: The plain name of each setting, for a saved-preference sentence.
_SETTING_WORDS = {
    "avatar_style": "the avatar style",
    "avatar_size": "the avatar size",
    "guidance_tone": "the guidance highlight colour",
}

#: What a saved switch is called in the answer.
_FEATURE_WORDS = {
    "avatar_enabled": "holographic avatar",
    "screen_guidance_enabled": "screen guidance",
    "cursor_ask_bar_enabled": "cursor ask bar",
    "interactive_3d_cards": "3D cards",
    "avatar_voice_reactive": "voice-reactive avatar",
}


# -----------------------------------------------------------------------------
# Settings - a preference file, and nothing more
# -----------------------------------------------------------------------------

def _settings_dir() -> Path:
    """The folder Jarvis keeps its own settings in.

    The same rule the rest of the backend follows (`jarvis_receipts.py` and
    `jarvis_file_guardian.py`): `OPENJARVIS_HOME` first - which is what the test
    runner points at a throwaway folder, so a suite can never write the owner's
    real profile - then the two config-folder names, then `~/.openjarvis`.
    Read on every call, never cached.
    """
    env = os.environ.get("OPENJARVIS_HOME")
    if env and str(env).strip():
        return Path(os.path.expanduser(str(env).strip()))
    env = (os.environ.get("OPENJARVIS_CONFIG_DIR")
           or os.environ.get("JARVIS_CONFIG_DIR"))
    if env and str(env).strip():
        return Path(os.path.expanduser(str(env).strip()))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def _get_settings_path() -> Path:
    """Return the path to the companion settings file."""
    return _settings_dir() / "companion_settings.json"


def load_settings() -> Dict[str, Any]:
    """Load companion settings from disk or return default settings."""
    cfg = dict(DEFAULT_CONFIG)
    p = _get_settings_path()
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_settings(cfg: Dict[str, Any]) -> bool:
    """Save companion settings to disk safely. False means nothing changed."""
    p = _get_settings_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        tmp.replace(p)
        return True
    except Exception:
        return False


def get_setting(key: str) -> Any:
    """Get a specific companion setting value."""
    cfg = load_settings()
    return cfg.get(key, DEFAULT_CONFIG.get(key))


def _known(value: Any, allowed: Tuple[str, ...]) -> str:
    """A saved value if it is one of the allowed words, else "not set".

    A hand-edited or damaged settings file must never put its own text into a
    chat answer (review finding L3, 2026-11-13).
    """
    return value if value in allowed else "not set"


def _saved_word(value: Any) -> str:
    """How a saved on/off preference is described - never "enabled"."""
    return "on" if value else "off"


def set_setting(key: str, value: Any) -> Tuple[bool, str]:
    """Save one companion preference, and say honestly what that did."""
    if key not in DEFAULT_CONFIG:
        return False, f"Unknown companion setting: '{key}'."

    # Validate specific keys
    if key == "avatar_style" and value not in AVATAR_STYLES:
        return False, f"Invalid avatar style '{value}'. Allowed: {', '.join(AVATAR_STYLES)}."
    if key == "avatar_size" and value not in AVATAR_SIZES:
        return False, f"Invalid avatar size '{value}'. Allowed: {', '.join(AVATAR_SIZES)}."
    if key == "guidance_tone" and value not in VALID_TONES:
        return False, f"Invalid tone '{value}'. Allowed: {', '.join(VALID_TONES)}."

    cfg = load_settings()
    cfg[key] = value
    if not save_settings(cfg):
        return False, "Jarvis could not save that preference, so nothing changed."
    name = _SETTING_WORDS.get(key, key.replace("_", " "))
    return True, (f"Saved {name} as '{value}' for the desktop companion. This build "
                  f"does not draw the companion yet, so nothing changes on screen.")


def toggle_feature(feature: str, want_on: Optional[bool] = None) -> Tuple[bool, str]:
    """Save a companion switch, and say honestly what that did."""
    feature_map = {
        "avatar": "avatar_enabled",
        "holographic avatar": "avatar_enabled",
        "wave sphere": "avatar_enabled",
        "guidance": "screen_guidance_enabled",
        "screen guidance": "screen_guidance_enabled",
        "screen pointing": "screen_guidance_enabled",
        "ask bar": "cursor_ask_bar_enabled",
        "cursor ask bar": "cursor_ask_bar_enabled",
        "askbar": "cursor_ask_bar_enabled",
        "3d cards": "interactive_3d_cards",
        "interactive 3d": "interactive_3d_cards",
        "voice reactive": "avatar_voice_reactive",
    }

    norm = feature.lower().strip()
    key = feature_map.get(norm)
    if not key:
        for k, v in feature_map.items():
            if k in norm:
                key = v
                break

    if not key:
        return False, f"I don't recognize companion feature '{feature}'. Choose from avatar, screen guidance, cursor ask bar, or 3D cards."

    cfg = load_settings()
    current = bool(cfg.get(key, DEFAULT_CONFIG[key]))
    new_val = (not current) if want_on is None else bool(want_on)
    cfg[key] = new_val
    if not save_settings(cfg):
        # A failed save is a failure, never a "now on" (review finding M1).
        return False, "Jarvis could not save that switch, so it is still where it was."
    readable = _FEATURE_WORDS.get(key, key.replace("_", " "))
    return True, (f"Saved the {readable} switch as {_saved_word(new_val)}. This build "
                  f"does not draw the companion yet, so nothing changes on screen.")


# -----------------------------------------------------------------------------
# 1. The avatar's numbers - not a drawn avatar
# -----------------------------------------------------------------------------

def generate_sphere_points(count: int = 520) -> List[Tuple[float, float, float]]:
    """Evenly distributed 3D points on a unit sphere (the golden spiral).

    The numbers a renderer would draw. Nothing draws them in this build.
    """
    n = max(32, min(count, 2000))
    points: List[Tuple[float, float, float]] = []
    for i in range(n):
        y = 1.0 - (2.0 * (i + 0.5)) / n
        r = math.sqrt(max(0.0, 1.0 - y * y))
        a = i * 2.399963229728653  # golden angle in radians
        x = math.cos(a) * r
        z = math.sin(a) * r
        points.append((round(x, 4), round(y, 4), round(z, 4)))
    return points


def calculate_wave_displacement(
    point: Tuple[float, float, float],
    time_sec: float,
    audio_level: float,
    is_talking: bool = False
) -> float:
    """The outward ripple a renderer would apply at one point, from sound.

    A pure number between -0.16 and 0.16: louder sound moves a point further,
    and nothing plays, draws or hears it here.
    """
    x, y, z = point
    azimuth = math.atan2(z, x)
    freq_y = 7.0
    speed = 9.0 if is_talking else 3.0
    band = math.sin(y * freq_y - time_sec * speed) * 0.5 + math.sin(azimuth * 5.0 + time_sec * 4.0) * 0.5
    wavy = max(0.12, min(1.0, audio_level))
    displacement = wavy * 0.16 * band
    return displacement


def get_avatar_config() -> Dict[str, Any]:
    """The numbers a renderer would need, plus the saved preferences.

    `enabled` is the owner's saved preference, not a statement that anything is
    drawn: nothing is (see NOT_BUILT).
    """
    cfg = load_settings()
    style = _known(cfg.get("avatar_style"), AVATAR_STYLES)
    size = _known(cfg.get("avatar_size"), AVATAR_SIZES)
    dot_count = 260 if size == "small" else 520
    return {
        "enabled": bool(cfg.get("avatar_enabled")),
        "style": style,
        "size": size,
        "voice_reactive": bool(cfg.get("avatar_voice_reactive")),
        "point_count": dot_count,
        "points": generate_sphere_points(dot_count),
    }


# -----------------------------------------------------------------------------
# 2. Screen guidance - a description, not a drawn overlay
# -----------------------------------------------------------------------------

def create_guidance_workflow(title: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Shape the plain description of a multi-step screen guidance workflow.

    A title, numbered steps, marks with a colour and a wait mode - and no more.
    Nothing shows it, highlights anything or waits for a click: the overlay does
    not exist in this build (see NOT_BUILT).
    """
    if not title or not title.strip():
        return {"ok": False, "problem": "Guidance workflow requires a descriptive title."}
    if not steps or not isinstance(steps, list):
        return {"ok": False, "problem": "Guidance workflow requires at least one instructional step."}

    cleaned_steps: List[Dict[str, Any]] = []
    cfg = load_settings()
    default_tone = _known(cfg.get("guidance_tone"), VALID_TONES)
    if default_tone == "not set":
        default_tone = "accent"
    auto_advance = cfg.get("guidance_auto_advance", False)

    for i, s in enumerate(steps):
        say = str(s.get("say") or "").strip()
        if not say:
            say = f"Step {i + 1}"

        marks = s.get("marks") or []
        cleaned_marks: List[Dict[str, Any]] = []
        for m in marks:
            kind = str(m.get("kind") or "ring").lower()
            target = m.get("at") or m.get("target") or {}
            tone = m.get("tone") or default_tone
            if tone not in VALID_TONES:
                tone = default_tone

            cleaned_marks.append({
                "kind": kind,
                "target": target,
                "tone": tone,
                "label": m.get("label"),
            })

        wait_mode = s.get("wait") or ("none" if auto_advance else "click")
        cleaned_steps.append({
            "step_number": i + 1,
            "say": say,
            "marks": cleaned_marks,
            "wait": wait_mode,
        })

    return {
        "ok": True,
        "title": title.strip(),
        "total_steps": len(cleaned_steps),
        "steps": cleaned_steps,
        "active_tone": default_tone,
    }


# -----------------------------------------------------------------------------
# 3. The ONE safety list - asked, never copied
# -----------------------------------------------------------------------------

def denied_app_reason(app_or_exe: str) -> Optional[str]:
    """The shared hard denylist's refusal for a program, or None when allowed.

    ONE list, never a second one. The screen-control code already refuses to
    click or type in a password vault, a terminal, a sign-in or UAC prompt, or a
    security-settings window, and it refuses by EXECUTABLE NAME. A companion
    answer that kept its own shorter list would let a program through the moment
    the two lists disagreed, so this asks that module and nothing else (review
    finding H1, 2026-11-13 - the list this replaced allowed
    `C:\\Windows\\System32\\cmd.exe` and nine vault/terminal names).

    A full path is reduced to the program's own file name first, and both
    separators are split, so the answer is the same on this PC and on a runner
    that is not Windows. When the list cannot be read the answer is a refusal,
    never None: a guard that fails open is not a guard.
    """
    name = str(app_or_exe or "").strip()
    if not name:
        return None
    leaf = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not leaf:
        return None
    try:
        import jarvis_ui_control as _screen
        return _screen.denied_process_refusal(process=leaf) or None
    except Exception:
        return ("Jarvis cannot read its own list of programs it never drives, so "
                "it will not touch any window at all.")


# -----------------------------------------------------------------------------
# 4. Interactive 3D cards - a description, not a rendered card
# -----------------------------------------------------------------------------

def create_3d_card(
    title: str,
    shape: str = "sphere",
    motion: str = "spin",
    tone: str = "accent",
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Shape the plain description of a 3D concept card.

    A shape, a motion and a colour. Nothing renders it: there is no card
    renderer in either app in this build (see NOT_BUILT).
    """
    if shape not in SHAPES_3D:
        shape = "sphere"
    if motion not in MOTIONS_3D:
        motion = "spin"
    if tone not in VALID_TONES:
        tone = "accent"

    return {
        "type": "card_3d",
        "title": title.strip(),
        "shape": shape,
        "motion": motion,
        "tone": tone,
        "description": description or f"Interactive 3D {shape} demonstrating {title}.",
        "render_mode": "dithered_led_5level",
    }


# -----------------------------------------------------------------------------
# 5. The chat answers - honest first, every time
# -----------------------------------------------------------------------------

def format_companion_overview() -> str:
    """Return the overview of what a desktop companion has, and has not, here."""
    cfg = load_settings()
    av_state = _saved_word(cfg.get("avatar_enabled"))
    sg_state = _saved_word(cfg.get("screen_guidance_enabled"))
    ab_state = _saved_word(cfg.get("cursor_ask_bar_enabled"))
    cards_state = _saved_word(cfg.get("interactive_3d_cards"))

    return (
        "### Desktop Companion\n\n"
        f"**{NOT_BUILT}** No window of Jarvis draws an avatar, a guidance "
        "overlay, a cursor bar or a 3D card, and nothing here clicks, types, "
        "reads your screen or recognises text in a picture.\n\n"
        "What is here today:\n\n"
        f"1. **Four saved preferences** (avatar {av_state}, screen guidance "
        f"{sg_state}, cursor ask bar {ab_state}, 3D cards {cards_state}). Saying "
        "*'turn on avatar'* saves the preference; it does not turn anything on "
        "on screen, because there is nothing to turn on yet.\n"
        "2. **The avatar's numbers** (the Holographic 3D LED Wave Sphere): 520 "
        "points on a golden spiral around a sphere, 260 in small mode, plus the "
        "wave formula a renderer would use for sound-reactive ripples. Nothing "
        "draws them.\n"
        "3. **A guidance description:** a title, numbered steps, marks with a "
        "colour and a wait mode. It is plain words only - nothing is "
        "highlighted and nothing waits for your click.\n"
        "4. **A 3D card description:** a shape, a motion and a colour. Nothing "
        "renders it.\n\n"
        "What is not here, and is not claimed: the avatar itself, the screen "
        "pointing and highlighting, the cursor ask bar, the 3D card renderer, "
        "reading another program's controls, reading text off the screen, and "
        "any control of your mouse or keyboard.\n\n"
        "You can say *'turn on avatar'*, *'disable screen guidance'*, or "
        "*'show companion settings'* at any time - each one saves a preference "
        "and tells you so."
    )


def format_avatar_explanation() -> str:
    """Return the design of the wave sphere, and say it is not drawn."""
    return (
        "### Holographic 3D LED Wave Sphere Avatar\n\n"
        f"**{NOT_BUILT}** What follows is the design and its geometry, not a "
        "working avatar.\n\n"
        "- **The geometry:** 520 points (260 in small mode) evenly spaced on a "
        "golden spiral around a 3D sphere. The points are computed here; "
        "nothing draws them.\n"
        "- **The wave:** a formula gives each point a small outward ripple, and "
        "a louder sound moves it further. It is never played or drawn.\n"
        "- **Gaze, the glowing core and reticle mode:** described in the design "
        "and not built. No window follows your cursor, and no reticle appears.\n\n"
        "The two preferences that exist are the style (sphere, reticle, classic, "
        "off) and the size (default, small, cursor). Say *'set avatar style to "
        "sphere'* or *'set avatar size to small'* to save one."
    )


def format_guidance_explanation() -> str:
    """Return the design of screen guidance, and say nothing is drawn."""
    return (
        "### Step-by-Step Screen Guidance ('Jarvis Shows You How')\n\n"
        f"**{NOT_BUILT}** Jarvis cannot point at your screen in this build, so "
        "this is a description of a workflow, not something you can watch.\n\n"
        "- **What the description holds:** a title, numbered steps, marks (a "
        "ring, a target, a label) with a colour, and a wait mode.\n"
        "- **What does not happen:** no rings, spotlights or lines are drawn, "
        "nothing is highlighted, and Jarvis never waits for a click because it "
        "never shows you the step.\n"
        "- **Control:** Jarvis does not take your mouse or keyboard, here or "
        "anywhere else.\n\n"
        "The preference that exists is the highlight colour (tone). Say *'set "
        "guidance tone to amber'* to save it."
    )


def format_askbar_explanation() -> str:
    """Return the design of the cursor ask bar, and say it does not exist."""
    return (
        "### Transient Cursor Micro-Ask Bar\n\n"
        f"**{NOT_BUILT}** There is no floating input box beside your cursor in "
        "this build, and no shortcut opens one.\n\n"
        "- **What is here:** the saved preference that says whether you would "
        "want it, and the shortcut written beside it.\n"
        "- **What is not here:** the bar itself, its window, and dismissing it "
        "by clicking away.\n\n"
        "To ask Jarvis something now, use the chat window or the Jarvis bar - "
        "both already work."
    )


def format_settings_summary() -> str:
    """Return the saved preferences, each labelled as a preference."""
    cfg = load_settings()
    return (
        "### Desktop Companion Settings\n\n"
        f"**{NOT_BUILT}** These are saved preferences only: none of them "
        "changes what you see on screen.\n\n"
        f"- **Holographic Avatar:** saved as {_saved_word(cfg.get('avatar_enabled'))}\n"
        f"  - Style: `{_known(cfg.get('avatar_style'), AVATAR_STYLES)}`\n"
        f"  - Size: `{_known(cfg.get('avatar_size'), AVATAR_SIZES)}`\n"
        f"  - Voice Reactive: {_saved_word(cfg.get('avatar_voice_reactive'))}\n"
        f"- **Screen Guidance:** saved as {_saved_word(cfg.get('screen_guidance_enabled'))}\n"
        f"  - Highlight Tone: `{_known(cfg.get('guidance_tone'), VALID_TONES)}`\n"
        f"  - Auto Advance: {'yes' if cfg.get('guidance_auto_advance') else 'wait for click'}\n"
        f"- **Cursor Micro-Ask Bar:** saved as {_saved_word(cfg.get('cursor_ask_bar_enabled'))}\n"
        f"  - Shortcut: `{_known(cfg.get('cursor_ask_bar_hotkey'), ('ctrl+shift',))}`\n"
        f"- **Interactive 3D Cards:** saved as {_saved_word(cfg.get('interactive_3d_cards'))}\n\n"
        "No companion window, overlay or card is drawn in this build, so these "
        "preferences wait for one."
    )
