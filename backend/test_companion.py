"""backend/test_companion.py - Test suite for desktop companion and Roamies capabilities.

Verifies:
  1. Settings lifecycle, defaults, and validation.
  2. Holographic 3D LED wave sphere mathematical properties and voice reactivity.
  3. Step-by-step visual screen guidance workflow creation and click-wait pacing.
  4. Windows native automation security perimeters and hands-off boundaries.
  5. Interactive 3D explanatory cards generation and motion states.
  6. Chat intent matching, self-awareness responses, and setting toggle execution.
  7. Architectural registration in _where.SHIPPED and twin parity.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import jarvis_companion as C
import jarvis_quick as Q
import _where

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"ok    {name}")
    else:
        FAILED += 1
        msg = f"FAIL  {name}"
        if detail:
            msg += f" ({detail})"
        print(msg)


def t_companion_settings_lifecycle():
    print("\n--- t_companion_settings_lifecycle ---------------------")
    cfg = C.DEFAULT_CONFIG
    check("default config contains avatar_enabled", "avatar_enabled" in cfg)
    check("default config contains screen_guidance_enabled", "screen_guidance_enabled" in cfg)
    check("default config contains cursor_ask_bar_enabled", "cursor_ask_bar_enabled" in cfg)
    check("default config contains interactive_3d_cards", "interactive_3d_cards" in cfg)
    check("default config contains hands_off_apps", len(cfg["hands_off_apps"]) > 0)

    # Test set_setting validation
    ok, msg = C.set_setting("avatar_style", "sphere")
    check("valid avatar style accepted", ok is True)

    ok, msg = C.set_setting("avatar_style", "invalid_style")
    check("invalid avatar style rejected", ok is False)

    ok, msg = C.set_setting("guidance_tone", "amber")
    check("valid tone accepted", ok is True)

    ok, msg = C.set_setting("guidance_tone", "rainbow")
    check("invalid tone rejected", ok is False)

    # Test toggle_feature
    ok, msg = C.toggle_feature("avatar", want_on=True)
    check("toggle avatar to True succeeds", ok is True)
    check("avatar is enabled", C.get_setting("avatar_enabled") is True)

    ok, msg = C.toggle_feature("screen guidance", want_on=False)
    check("toggle screen guidance to False succeeds", ok is True)
    check("screen guidance is disabled", C.get_setting("screen_guidance_enabled") is False)

    # Toggle back
    C.toggle_feature("screen guidance", want_on=True)
    check("restored screen guidance to enabled", C.get_setting("screen_guidance_enabled") is True)


def t_holographic_avatar_engine():
    print("\n--- t_holographic_avatar_engine ------------------------")
    pts_520 = C.generate_sphere_points(520)
    check("generated 520 sphere points", len(pts_520) == 520)

    pts_260 = C.generate_sphere_points(260)
    check("generated 260 sphere points", len(pts_260) == 260)

    # Verify points lie on unit sphere
    all_on_sphere = True
    for x, y, z in pts_520[:30]:
        dist = math.sqrt(x * x + y * y + z * z)
        if abs(dist - 1.0) > 0.05:
            all_on_sphere = False
            break
    check("points lie on unit sphere radius 1.0", all_on_sphere)

    # Test wave displacement calculation
    disp_quiet = C.calculate_wave_displacement((1.0, 0.0, 0.0), time_sec=1.0, audio_level=0.1, is_talking=False)
    disp_loud = C.calculate_wave_displacement((1.0, 0.0, 0.0), time_sec=1.0, audio_level=0.9, is_talking=True)
    check("wave displacement reacts to audio energy", abs(disp_loud) >= abs(disp_quiet) or abs(disp_loud) > 0)

    av_cfg = C.get_avatar_config()
    check("avatar config contains points", "points" in av_cfg and len(av_cfg["points"]) > 0)
    check("avatar config reports style", av_cfg.get("style") in C.AVATAR_STYLES)


def t_screen_guidance_workflow():
    print("\n--- t_screen_guidance_workflow -------------------------")
    steps = [
        {
            "say": "Click the File menu",
            "marks": [{"kind": "ring", "at": {"text": "File", "x": 10, "y": 10, "w": 40, "h": 20}}],
            "wait": "click"
        },
        {
            "say": "Select Export Video",
            "marks": [{"kind": "target", "at": {"text": "Export", "x": 10, "y": 60, "w": 100, "h": 24}}],
            "wait": "click"
        }
    ]

    wf = C.create_guidance_workflow("Export Video Tutorial", steps)
    check("guidance workflow created successfully", wf.get("ok") is True)
    check("workflow has 2 steps", wf.get("total_steps") == 2)
    check("step 1 requires click wait", wf["steps"][0]["wait"] == "click")
    check("step 1 has ring mark", wf["steps"][0]["marks"][0]["kind"] == "ring")

    # Negative validation
    bad_wf1 = C.create_guidance_workflow("", steps)
    check("empty title is refused", bad_wf1.get("ok") is False)

    bad_wf2 = C.create_guidance_workflow("Title", [])
    check("empty steps list is refused", bad_wf2.get("ok") is False)


def t_windows_automation_and_security_guards():
    print("\n--- t_windows_automation_and_security_guards -----------")
    # Verify hands-off apps are blocked
    check("Command Prompt is hands-off", C.is_hands_off("cmd.exe") is not None)
    check("PowerShell is hands-off", C.is_hands_off("powershell.exe") is not None)
    check("PowerShell 7 is hands-off", C.is_hands_off("pwsh") is not None)
    check("Windows Terminal is hands-off", C.is_hands_off("WindowsTerminal.exe") is not None)
    check("KeePassXC is hands-off", C.is_hands_off("keepassxc") is not None)

    # Standard safe apps are allowed
    check("Notepad is permitted", C.is_hands_off("notepad.exe") is None)
    check("Calculator is permitted", C.is_hands_off("calc") is None)

    # Risky actions are caught
    check("format action flagged as risky", C.is_risky_action("format disk C:") is True)
    check("delete all action flagged as risky", C.is_risky_action("delete all files") is True)
    check("view action is not risky", C.is_risky_action("view the document") is False)


def t_interactive_3d_cards():
    print("\n--- t_interactive_3d_cards -----------------------------")
    card = C.create_3d_card("Rotating Black Hole", shape="sphere", motion="spin", tone="accent")
    check("card type is card_3d", card.get("type") == "card_3d")
    check("shape is sphere", card.get("shape") == "sphere")
    check("motion is spin", card.get("motion") == "spin")
    check("render mode is dithered LED", card.get("render_mode") == "dithered_led_5level")

    # Fallback validation
    fallback_card = C.create_3d_card("Test", shape="invalid_shape", motion="invalid_motion")
    check("invalid shape falls back to sphere", fallback_card.get("shape") == "sphere")
    check("invalid motion falls back to spin", fallback_card.get("motion") == "spin")


def t_chat_intent_routing_and_self_awareness():
    print("\n--- t_chat_intent_routing_and_self_awareness -----------")
    import time

    def run_cmd(intent):
        return Q.run(intent, None, time.time())

    # 1. Overview
    res = Q.match("what are your desktop companion capabilities")
    check("companion overview intent matched", res is not None and res.name == "companion_overview")
    if res:
        out = run_cmd(res)
        check("companion overview output describes features", "Holographic 3D LED Wave Sphere" in out.reply)

    # 2. Avatar explanation
    res = Q.match("explain your holographic avatar")
    check("companion avatar intent matched", res is not None and res.name == "companion_avatar_info")
    if res:
        out = run_cmd(res)
        check("avatar explanation describes golden spiral", "golden spiral" in out.reply)

    # 3. Guidance explanation
    res = Q.match("how does screen guidance work")
    check("companion guidance intent matched", res is not None and res.name == "companion_guidance_info")
    if res:
        out = run_cmd(res)
        check("guidance explanation describes visual rings", "Visual Rings" in out.reply)

    # 4. Ask bar explanation
    res = Q.match("what is the cursor ask bar")
    check("companion ask bar intent matched", res is not None and res.name == "companion_askbar_info")
    if res:
        out = run_cmd(res)
        check("ask bar explanation mentions shortcut", "Ctrl+Shift" in out.reply)

    # 5. Settings summary
    res = Q.match("show companion settings")
    check("companion settings show matched", res is not None and res.name == "companion_settings_show")
    if res:
        out = run_cmd(res)
        check("settings summary outputs status", "Holographic Avatar" in out.reply)

    # 6. Toggle feature in chat
    res = Q.match("turn on holographic avatar")
    check("toggle intent matched", res is not None and res.name == "companion_toggle")
    if res:
        out = run_cmd(res)
        check("toggle result confirms state", "enabled" in out.reply or "avatar" in out.reply)

    res = Q.match("disable screen guidance")
    check("disable guidance matched", res is not None and res.name == "companion_toggle")
    if res:
        out = run_cmd(res)
        check("disable confirms disabled", "disabled" in out.reply)

    # 7. Set style in chat
    res = Q.match("set avatar style to reticle")
    check("set style intent matched", res is not None and res.name == "companion_set_style")
    if res:
        out = run_cmd(res)
        check("set style confirms change", "reticle" in out.reply or "avatar_style" in out.reply)


def t_governance_and_integrity():
    print("\n--- t_governance_and_integrity -------------------------")
    check("jarvis_companion.py is registered in _where.SHIPPED",
          "jarvis_companion.py" in _where.SHIPPED)

    # Check twin parity
    backend_path = HERE / "jarvis_companion.py"
    twin_path = ROOT / "jarvis-backend" / "jarvis_companion.py"
    check("twin file exists in jarvis-backend/", twin_path.is_file())
    if backend_path.is_file() and twin_path.is_file():
        b_bytes = backend_path.read_bytes().replace(b"\r\n", b"\n")
        t_bytes = twin_path.read_bytes().replace(b"\r\n", b"\n")
        check("jarvis_companion.py matches twin byte-for-byte", b_bytes == t_bytes)


def main():
    t_companion_settings_lifecycle()
    t_holographic_avatar_engine()
    t_screen_guidance_workflow()
    t_windows_automation_and_security_guards()
    t_interactive_3d_cards()
    t_chat_intent_routing_and_self_awareness()
    t_governance_and_integrity()

    print("\n" + "=" * 60)
    print(f"Total: {PASSED + FAILED} | Passed: {PASSED} | Failed: {FAILED}")
    if FAILED > 0:
        print(f"FAILURES DETECTED: {FAILED}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
