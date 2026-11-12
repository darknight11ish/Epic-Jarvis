"""jarvis_companion.py - Desktop companion and screen guidance capabilities for Jarvis.

Multi-modal desktop companion features inspired by the open-source Roamies system:
1. Holographic 3D LED Wave Sphere Avatar: Stark-style glowing sphere of 520 golden-spiral
   LED points with voice-reactive ripples, yaw/pitch gaze tracking, and reticle cursor mode.
2. Step-by-Step Screen Guidance: Visual pointing, glowing loops, spotlights, and step-by-step
   walkthroughs on screen ("Jarvis shows you how"), with click confirmation.
3. Windows Native Automation Guards: Non-blocking UI Automation with subtree caching,
   hardware-accelerated Windows Runtime OCR (WinRT), and hands-off security boundaries.
4. Transient Cursor Micro-Ask Bar: Minimal floating HUD input field beside the cursor.
5. Interactive 3D Explanatory Cards: Lightweight zero-dependency WebGL 3D concept diagrams
   with animated motions (spin, orbit, slide, pulse) dithered to 5 LED levels.
6. Chat Settings Management & Self-Awareness: Discuss capabilities in depth, query settings,
   and toggle companion features directly via voice or chat.

Standard library only. All state changes are non-destructive.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

#: Default companion settings configuration
DEFAULT_CONFIG: Dict[str, Any] = {
    "avatar_enabled": True,
    "avatar_style": "sphere",  # "sphere", "reticle", "classic", "off"
    "avatar_size": "default",  # "default", "small", "cursor"
    "avatar_voice_reactive": True,
    "screen_guidance_enabled": True,
    "guidance_tone": "accent",  # "accent", "teal", "amber", "coral", "lilac", "sky", "lime"
    "guidance_auto_advance": False,  # wait for user click before advancing step
    "cursor_ask_bar_enabled": True,
    "cursor_ask_bar_hotkey": "ctrl+shift",
    "windows_native_ocr": "auto",  # "auto", "winrt", "off"
    "hands_off_apps": [
        "cmd", "powershell", "powershell_ise", "pwsh",
        "windowsterminal", "openconsole", "conhost", "keepassxc"
    ],
    "interactive_3d_cards": True,
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

#: Dangerous action keywords that cannot run automatically
RISKY_WORDS = ("delete", "remove", "erase", "format", "wipe", "drop", "purge", "destroy", "shutdown", "reboot")


def _get_settings_path() -> Path:
    """Return the path to the companion settings file."""
    custom = os.environ.get("JARVIS_SETTINGS_DIR")
    if custom:
        base = Path(custom)
    else:
        base = Path.home() / ".jarvis"
    return base / "companion_settings.json"


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
    """Save companion settings to disk safely."""
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


def set_setting(key: str, value: Any) -> Tuple[bool, str]:
    """Set a specific companion setting value with validation."""
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
    ok = save_settings(cfg)
    if ok:
        return True, f"Updated {key} to {value}."
    return False, "Failed to save settings file."


def toggle_feature(feature: str, want_on: Optional[bool] = None) -> Tuple[bool, str]:
    """Toggle a companion feature on or off."""
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
    save_settings(cfg)
    state_str = "enabled" if new_val else "disabled"
    readable = key.replace("_enabled", "").replace("_", " ")
    return True, f"Desktop companion {readable} is now {state_str}."


# -----------------------------------------------------------------------------
# 1. Holographic 3D LED Wave Sphere Avatar
# -----------------------------------------------------------------------------

def generate_sphere_points(count: int = 520) -> List[Tuple[float, float, float]]:
    """Generate evenly distributed 3D points on a unit sphere using the golden spiral algorithm."""
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
    """Calculate outward surface wave ripple at a given 3D coordinate based on speech audio."""
    x, y, z = point
    azimuth = math.atan2(z, x)
    freq_y = 7.0
    speed = 9.0 if is_talking else 3.0
    band = math.sin(y * freq_y - time_sec * speed) * 0.5 + math.sin(azimuth * 5.0 + time_sec * 4.0) * 0.5
    wavy = max(0.12, min(1.0, audio_level))
    displacement = wavy * 0.16 * band
    return displacement


def get_avatar_config() -> Dict[str, Any]:
    """Return the active configuration for the desktop avatar."""
    cfg = load_settings()
    style = cfg.get("avatar_style", "sphere")
    size = cfg.get("avatar_size", "default")
    dot_count = 260 if size == "small" else 520
    return {
        "enabled": cfg.get("avatar_enabled", True),
        "style": style,
        "size": size,
        "voice_reactive": cfg.get("avatar_voice_reactive", True),
        "point_count": dot_count,
        "points": generate_sphere_points(dot_count),
    }


# -----------------------------------------------------------------------------
# 2. Screen Guidance & Visual Ringing Engine ("JARVIS Shows You How")
# -----------------------------------------------------------------------------

def create_guidance_workflow(title: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create a structured multi-step visual screen guidance workflow."""
    if not title or not title.strip():
        return {"ok": False, "problem": "Guidance workflow requires a descriptive title."}
    if not steps or not isinstance(steps, list):
        return {"ok": False, "problem": "Guidance workflow requires at least one instructional step."}

    cleaned_steps: List[Dict[str, Any]] = []
    cfg = load_settings()
    default_tone = cfg.get("guidance_tone", "accent")
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
# 3. Windows Native Automation & Security Boundaries
# -----------------------------------------------------------------------------

def is_hands_off(app_or_exe: str) -> Optional[str]:
    """Check if an executable or application is on the hands-off security blacklist."""
    raw = app_or_exe.lower().strip()
    name = raw[:-4] if raw.endswith(".exe") else raw

    cfg = load_settings()
    blacklist = set(cfg.get("hands_off_apps", DEFAULT_CONFIG["hands_off_apps"]))

    if name in blacklist:
        names = {
            "cmd": "Command Prompt",
            "powershell": "PowerShell",
            "powershell_ise": "PowerShell ISE",
            "pwsh": "PowerShell 7",
            "windowsterminal": "Windows Terminal",
            "openconsole": "Windows Console",
            "conhost": "Console Host",
            "keepassxc": "KeePassXC Password Vault",
        }
        return names.get(name, name)
    return None


def is_risky_action(instruction_or_label: str) -> bool:
    """Check if a label or instruction suggests destructive or sensitive operations."""
    text = instruction_or_label.lower()
    for w in RISKY_WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", text):
            return True
    return False


# -----------------------------------------------------------------------------
# 4. Interactive 3D Explanatory Cards
# -----------------------------------------------------------------------------

def create_3d_card(
    title: str,
    shape: str = "sphere",
    motion: str = "spin",
    tone: str = "accent",
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Create a structured specification for a WebGL 3D concept visualization card."""
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
# 5. Self-Awareness Knowledge Base & Chat Guidance
# -----------------------------------------------------------------------------

def format_companion_overview() -> str:
    """Return a comprehensive overview of desktop companion capabilities."""
    cfg = load_settings()
    av_state = "ON" if cfg.get("avatar_enabled") else "OFF"
    sg_state = "ON" if cfg.get("screen_guidance_enabled") else "OFF"
    ab_state = "ON" if cfg.get("cursor_ask_bar_enabled") else "OFF"
    cards_state = "ON" if cfg.get("interactive_3d_cards") else "OFF"

    return (
        "### Jarvis Desktop Companion Capabilities\n\n"
        "Here are the desktop presence, guidance, and automation capabilities integrated into Jarvis:\n\n"
        f"1. **Holographic 3D LED Wave Sphere Avatar** [{av_state}]\n"
        "   - Stark-inspired glowing globe of 520 golden-spiral LED points that tracks your cursor gaze.\n"
        "   - Sound-reactive surface waves ripple dynamically as Jarvis listens or speaks.\n"
        "   - Smoothly transforms into a HUD precision reticle cursor when pointing at screen items.\n"
        "   - *Settings:* `avatar_style` (sphere, reticle, classic, off), `avatar_size` (default, small, cursor).\n\n"
        f"2. **Step-by-Step Screen Guidance & Pointing** [{sg_state}]\n"
        "   - Jarvis shows you how to use any desktop app by highlighting and ringing real controls.\n"
        "   - Draws spotlights, callout lines, and hand-drawn glowing loops around buttons.\n"
        "   - Paces instructions step-by-step and waits for your real click before continuing.\n\n"
        f"3. **Transient Cursor Micro-Ask Bar** [{ab_state}]\n"
        "   - Tap **Ctrl+Shift** to open a minimal floating input bar right beside your mouse cursor.\n"
        "   - Ask a question or trigger a task without opening the main window, and it vanishes when done.\n\n"
        f"4. **Interactive 3D Explanatory Cards** [{cards_state}]\n"
        "   - Zero-dependency WebGL 3D visualizations rendered in Jarvis's retro-futuristic 5-level LED style.\n"
        "   - Explains physical, astronomical, and structural concepts with interactive rotating or pulsing models.\n\n"
        "5. **Windows Native Automation & Security Boundaries**\n"
        "   - Non-blocking UI Automation with batch subtree caching and timeout protection.\n"
        "   - Native Windows Runtime OCR (WinRT) with zero external downloads.\n"
        "   - Strict hands-off security perimeter blocking terminals, password vaults, and destructive actions.\n\n"
        "You can say *'turn on avatar'*, *'disable screen guidance'*, or *'show companion settings'* at any time."
    )


def format_avatar_explanation() -> str:
    """Return a detailed explanation of the holographic 3D wave sphere avatar."""
    return (
        "### Holographic 3D LED Wave Sphere Avatar\n\n"
        "The Jarvis holographic avatar is a Stark-inspired visual presence for your desktop:\n"
        "- **Mathematical Structure:** 520 points (260 in small mode) mapped along a golden spiral around a 3D unit sphere.\n"
        "- **Cursor Tracking:** Rotates in 3D pitch and yaw, following the direction of your mouse cursor.\n"
        "- **Audio Reactivity:** Surface waves ripple outward dynamically based on microphone input and spoken speech.\n"
        "- **Luminescent Core:** An inner glowing heart pulses gently during idle states and expands with vocal energy.\n"
        "- **Reticle Mode:** In screen-pointing tasks, the sphere collapses into a precision HUD targeting reticle.\n\n"
        "To adjust: say *'set avatar style to sphere'*, *'set avatar size to small'*, or *'turn off avatar'*."
    )


def format_guidance_explanation() -> str:
    """Return an explanation of the screen guidance engine."""
    return (
        "### Step-by-Step Screen Guidance ('Jarvis Shows You How')\n\n"
        "Jarvis can visually guide you through complex software workflows across any application:\n"
        "- **Visual Rings:** Draws glowing hand-drawn loops around the exact button or menu item on your real screen.\n"
        "- **Spotlights & Underlines:** Dims distraction and focuses attention on the exact relevant text or element.\n"
        "- **Click-Wait Progression:** Vocalizes the current step and pauses until you actually click the highlighted control.\n"
        "- **Ask-First Protection:** Jarvis guides you visually without taking control of your mouse without permission.\n\n"
        "To adjust: say *'turn on screen guidance'*, *'turn off screen guidance'*, or *'set guidance tone to amber'*."
    )


def format_native_automation_explanation() -> str:
    """Return an explanation of native Windows automation and OCR."""
    return (
        "### Windows Native Automation & Security Guardrails\n\n"
        "Jarvis interacts with desktop applications safely using specialized native helpers:\n"
        "- **Non-Blocking UI Automation:** Queries Windows accessibility trees via COM cache requests with 4s/8s timeouts, preventing application freezes.\n"
        "- **Zero-Download WinRT OCR:** Uses Windows 10/11 built-in optical character recognition (`Windows.Media.Ocr`) for fast local text extraction.\n"
        "- **Hands-Off Security Perimeter:** Automatically refuses to type into or click inside command terminals (cmd, PowerShell, Windows Terminal) and password vaults (KeePassXC).\n"
        "- **Destructive Action Filter:** Prompts for explicit Ask-First approval cards before any critical system changes."
    )


def format_askbar_explanation() -> str:
    """Return an explanation of the transient cursor micro-ask bar."""
    return (
        "### Transient Cursor Micro-Ask Bar\n\n"
        "The cursor ask bar is a lightweight, floating text prompt directly beside your cursor:\n"
        "- **Instant Access:** Tap **Ctrl+Shift** anywhere to open the prompt immediately.\n"
        "- **Frictionless Interaction:** Type a command, read the answer, and press Escape or click away to dismiss.\n"
        "- **Non-Intrusive:** Keeps your screen clear without shifting focus away from your active work."
    )


def format_settings_summary() -> str:
    """Return a plain-English summary of all companion settings."""
    cfg = load_settings()
    return (
        "### Jarvis Desktop Companion Settings\n\n"
        f"- **Holographic Avatar:** {'Enabled' if cfg.get('avatar_enabled') else 'Disabled'}\n"
        f"  - Style: `{cfg.get('avatar_style')}`\n"
        f"  - Size: `{cfg.get('avatar_size')}`\n"
        f"  - Voice Reactive: {'Yes' if cfg.get('avatar_voice_reactive') else 'No'}\n"
        f"- **Screen Guidance:** {'Enabled' if cfg.get('screen_guidance_enabled') else 'Disabled'}\n"
        f"  - Highlight Tone: `{cfg.get('guidance_tone')}`\n"
        f"  - Auto Advance: {'Yes' if cfg.get('guidance_auto_advance') else 'Wait for click'}\n"
        f"- **Cursor Micro-Ask Bar:** {'Enabled' if cfg.get('cursor_ask_bar_enabled') else 'Disabled'} (`{cfg.get('cursor_ask_bar_hotkey')}`)\n"
        f"- **Interactive 3D Cards:** {'Enabled' if cfg.get('interactive_3d_cards') else 'Disabled'}\n"
        f"- **Windows Native OCR:** `{cfg.get('windows_native_ocr')}`\n"
        f"- **Hands-Off Apps Protected:** {len(cfg.get('hands_off_apps', []))} apps (cmd, powershell, pwsh, keepassxc, ...)"
    )
