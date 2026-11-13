"""jarvis_companion.py - the desktop companion's settings and its honest answers.

WHAT IS HERE. The settings store behind the desktop-companion chat answers, plus
two pure data helpers that shape a plain description: one for a step-by-step
guidance workflow, one for a 3D card. The avatar's point set and its
sound-reactive wave formula are deliberately NOT here: both were line-for-line
translations of AGPL-3.0-licensed code in the Roamies showcase, and this
MIT-licensed project may not carry them (removed 2026-11-13).

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

Provenance: the design was inspired by the open-source Roamies system
(AGPL-3.0). No line of its code is carried here - neither the geometry nor the
wave formula, both deleted on 2026-11-13 - so only the preference names and the
plain-word answers are ours, and the drawing is not built.

Standard library only. All state changes are non-destructive.
"""

from __future__ import annotations

import json
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
# 1. The avatar's saved preferences - not a drawn avatar
# -----------------------------------------------------------------------------

#: The dot count the design names for each avatar size. A number from the
#: design, not a point set: nothing computes the points in this build.
_AVATAR_DOT_COUNTS = {"default": 520, "small": 260}


def get_avatar_config() -> Dict[str, Any]:
    """The saved avatar preferences, plus the design's dot count.

    `enabled` is the owner's saved preference, not a statement that anything is
    drawn: nothing is (see NOT_BUILT). The point set itself is NOT here and is
    not computed - it was AGPL-3.0-derived code this project may not carry.
    """
    cfg = load_settings()
    style = _known(cfg.get("avatar_style"), AVATAR_STYLES)
    size = _known(cfg.get("avatar_size"), AVATAR_SIZES)
    return {
        "enabled": bool(cfg.get("avatar_enabled")),
        "style": style,
        "size": size,
        "voice_reactive": bool(cfg.get("avatar_voice_reactive")),
        "point_count": _AVATAR_DOT_COUNTS.get(size, 520),
    }


# -----------------------------------------------------------------------------
# 1. Screen guidance - a description, not a drawn overlay
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
# 2. The ONE safety list - asked, never copied
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
# 3. Interactive 3D cards - a description, not a rendered card
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
# 4. The chat answers - honest first, every time
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
        "2. **The avatar's saved preferences:** a style (sphere, reticle, "
        "classic, off) and a size (default, small, cursor). The avatar itself "
        "- its geometry and its sound-reactive formula - is not built and is "
        "not computed here.\n"
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
    """Return the avatar's saved preferences, and say the avatar is not built."""
    return (
        "### Holographic Avatar (design only)\n\n"
        f"**{NOT_BUILT}** What follows is the name of a design and the "
        "preferences that save it, not a working avatar.\n\n"
        "- **What is saved:** a style (sphere, reticle, classic, off) and a "
        "size (default, small, cursor). Each is a preference, not a drawn "
        "thing.\n"
        "- **The geometry and the sound-reactive formula:** deliberately not "
        "in this build at all. Nothing computes a point set, nothing applies a "
        "wave, and nothing is played or drawn.\n"
        "- **Gaze, the glowing core and reticle mode:** described in the design "
        "and not built. No window follows your cursor, and no reticle appears.\n\n"
        "The two preferences that exist are the style and the size. Say *'set "
        "avatar style to sphere'* or *'set avatar size to small'* to save one."
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
