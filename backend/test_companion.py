"""backend/test_companion.py - the desktop companion's own suite.

What this suite proves, and why each check can fail (review of PR #1229,
2026-11-13: the first version asserted the module's own story instead of its
behaviour):

  1. A SAVED PREFERENCE is reported as a preference, never as a working
     feature, and a save that fails says so instead of a fake success.
  2. The AGPL-3.0-derived point set and wave formula are GONE (deleted
     2026-11-13, they were line-for-line translations of the Roamies showcase),
     and the avatar helper hands back saved preferences and the design's dot
     count only - never a computed point, never a wave.
  3. The guidance and 3D-card helpers shape plain descriptions and nothing
     else.
  4. The ONE hard denylist is the screen-control module's, and a FULL PATH
     cannot get round it. The list this PR first shipped allowed
     `C:\\Windows\\System32\\cmd.exe`, `wt.exe` and every password vault.
  5. No companion answer claims UI Automation, text recognition, drawing or a
     security perimeter: every one of them says the visual half is not built.
  6. A PRIVATE chat cannot change a companion setting: the two change intents
     are off the private-read whitelist, and the file on disk does not move.
  7. The suite is hermetic (its own OPENJARVIS_HOME), the module is registered
     in `_where.SHIPPED`, and its base twin is byte-identical.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Add backend directory to sys.path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

#: The suite's own home. `OPENJARVIS_HOME` is the folder the backend treats as
#: the owner's, and the runner points it at a throwaway folder for every suite -
#: so the suite sets it itself and is hermetic either way. The first version of
#: this suite wrote `~/.jarvis/companion_settings.json` into the owner's real
#: profile (review finding H2).
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-test-companion-"))
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")

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


# --------------------------------------------------------------------------
# 1. A preference, saved honestly
# --------------------------------------------------------------------------

def t_a_preference_is_a_preference():
    print("\n--- t_a_preference_is_a_preference ----------------------")
    cfg = C.DEFAULT_CONFIG
    check("default config contains avatar_enabled", "avatar_enabled" in cfg)
    check("default config contains screen_guidance_enabled", "screen_guidance_enabled" in cfg)
    check("default config contains cursor_ask_bar_enabled", "cursor_ask_bar_enabled" in cfg)
    check("default config contains interactive_3d_cards", "interactive_3d_cards" in cfg)

    # Nothing draws these, so no switch may ship ON: a switch reading "on" while
    # no window exists is the fake presence the answers stopped claiming.
    for key in ("avatar_enabled", "screen_guidance_enabled",
                "cursor_ask_bar_enabled", "interactive_3d_cards"):
        check(f"the {key} switch ships OFF", cfg[key] is False, cfg[key])

    # ONE denylist, not a second one stored beside the switches.
    check("the settings hold no second blacklist", "hands_off_apps" not in cfg)

    ok, msg = C.toggle_feature("avatar", want_on=True)
    check("saving a switch succeeds", ok is True, msg)
    check("...and the answer says it was SAVED", "Saved" in msg, msg)
    check("...and it says nothing changes on screen", "nothing changes on screen" in msg, msg)
    check("...and it never claims the feature is enabled", "enabled" not in msg.lower(), msg)
    check("the saved value really moved", C.get_setting("avatar_enabled") is True)

    ok, msg = C.toggle_feature("screen guidance", want_on=False)
    check("turning a switch off saves too", ok is True, msg)
    check("...and says off", "as off" in msg, msg)

    # A save that fails is a failure, never a "now on" (review finding M1: the
    # old code ignored save_settings' False and reported success).
    real_save = C.save_settings
    try:
        C.save_settings = lambda cfg: False
        ok, msg = C.toggle_feature("avatar", want_on=True)
        check("a failed save of a switch is a FAILURE", ok is False, msg)
        check("...and the answer claims nothing was saved", "Saved" not in msg, msg)
        ok, msg = C.set_setting("avatar_style", "reticle")
        check("a failed save of a style is a FAILURE", ok is False, msg)
        check("...and that answer claims nothing was saved", "Saved" not in msg, msg)
    finally:
        C.save_settings = real_save

    # Validation still refuses an unknown word before anything is written.
    ok, msg = C.toggle_feature("holographic avatar", want_on=True)
    check("a known feature name saves", ok is True, msg)
    ok, msg = C.toggle_feature("teleporter", want_on=True)
    check("an unknown feature is refused", ok is False and "don't recognize" in msg, msg)
    ok, msg = C.set_setting("avatar_style", "invalid_style")
    check("invalid avatar style rejected", ok is False, msg)
    ok, msg = C.set_setting("guidance_tone", "amber")
    check("valid tone accepted", ok is True, msg)
    ok, msg = C.set_setting("guidance_tone", "rainbow")
    check("invalid tone rejected", ok is False, msg)
    ok, msg = C.set_setting("no_such_setting", "x")
    check("an unknown setting is refused", ok is False, msg)

    # The old "set style confirms change" check passed on its own failure
    # message: the refusal names the word it refused. This one is strict.
    ok, msg = C.set_setting("avatar_style", "reticle")
    check("a valid style says SAVED and names the value",
          ok is True and "Saved" in msg and "'reticle'" in msg, msg)


# --------------------------------------------------------------------------
# 2. No AGPL-derived geometry, and no claim of one
# --------------------------------------------------------------------------

def t_no_agpl_geometry_is_carried():
    print("\n--- t_no_agpl_geometry_is_carried -----------------------")
    # `generate_sphere_points()` and `calculate_wave_displacement()` were
    # line-for-line translations of AGPL-3.0 code from the Roamies showcase.
    # This MIT project may not carry them, so both are deleted and must stay
    # deleted - and nothing may hand a caller the numbers they used to compute.
    check("the AGPL-derived point set is gone",
          not hasattr(C, "generate_sphere_points"))
    check("the AGPL-derived wave formula is gone",
          not hasattr(C, "calculate_wave_displacement"))

    av_cfg = C.get_avatar_config()
    check("the avatar helper computes no points", "points" not in av_cfg)
    check("avatar config reports a known style", av_cfg.get("style") in C.AVATAR_STYLES)
    check("avatar config reports the saved preference, not a working avatar",
          av_cfg.get("enabled") is True)   # saved above by this suite, still a preference
    check("the default size still names the design's 520 dots",
          av_cfg["point_count"] == 520)

    C.set_setting("avatar_size", "small")
    small_cfg = C.get_avatar_config()
    check("small mode names the design's 260 dots", small_cfg["point_count"] == 260)
    check("...and still computes no points", "points" not in small_cfg)
    C.set_setting("avatar_size", "default")


# --------------------------------------------------------------------------
# 3. The two description shapers
# --------------------------------------------------------------------------

def t_guidance_description_shaper():
    print("\n--- t_guidance_description_shaper ----------------------")
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
    check("guidance workflow shaped successfully", wf.get("ok") is True)
    check("workflow has 2 steps", wf.get("total_steps") == 2)
    check("step 1 requires click wait", wf["steps"][0]["wait"] == "click")
    check("step 1 has ring mark", wf["steps"][0]["marks"][0]["kind"] == "ring")
    check("an unknown tone falls back to the configured one",
          wf["steps"][0]["marks"][0]["tone"] in C.VALID_TONES)

    bad_wf1 = C.create_guidance_workflow("", steps)
    check("empty title is refused", bad_wf1.get("ok") is False)
    bad_wf2 = C.create_guidance_workflow("Title", [])
    check("empty steps list is refused", bad_wf2.get("ok") is False)


def t_3d_card_shaper():
    print("\n--- t_3d_card_shaper -----------------------------------")
    card = C.create_3d_card("Rotating Black Hole", shape="sphere", motion="spin", tone="accent")
    check("card type is card_3d", card.get("type") == "card_3d")
    check("shape is sphere", card.get("shape") == "sphere")
    check("motion is spin", card.get("motion") == "spin")
    check("render mode is dithered LED", card.get("render_mode") == "dithered_led_5level")

    fallback_card = C.create_3d_card("Test", shape="invalid_shape", motion="invalid_motion")
    check("invalid shape falls back to sphere", fallback_card.get("shape") == "sphere")
    check("invalid motion falls back to spin", fallback_card.get("motion") == "spin")


# --------------------------------------------------------------------------
# 4. The ONE denylist
# --------------------------------------------------------------------------

def t_the_one_denylist_is_the_shared_one():
    print("\n--- t_the_one_denylist_is_the_shared_one ---------------")
    cases = {
        # A FULL PATH was the measured bypass in the list this PR first shipped.
        r"C:\Windows\System32\cmd.exe": "Command Prompt",
        "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe": "PowerShell",
        "1Password.exe": "1Password",
        "bitwarden.exe": "Bitwarden",
        "keepass.exe": "KeePass",
        "keepassxc": "KeePassXC",
        "wt.exe": "Windows Terminal",
        "taskmgr.exe": "Task Manager",
        "consent.exe": "the Windows UAC prompt",
    }
    for exe, label in cases.items():
        got = C.denied_app_reason(exe)
        check(f"the shared denylist refuses {exe}",
              got is not None and label in got, got)
    check("a program the shipped list allows stays allowed",
          C.denied_app_reason("notepad.exe") is None)
    check("...and a bare program name is allowed too",
          C.denied_app_reason("calc") is None)
    check("an empty name is not a refusal", C.denied_app_reason("") is None)

    # No second list anywhere: the module must not grow one back.
    check("the companion keeps NO blacklist of its own",
          not hasattr(C, "is_hands_off") and not hasattr(C, "hands_off_apps"))
    check("...and no second destructive-word list either",
          not hasattr(C, "is_risky_action") and not hasattr(C, "RISKY_WORDS"))


# --------------------------------------------------------------------------
# 5. The chat answers claim nothing that is not built
# --------------------------------------------------------------------------

#: Every phrase the first version said in Jarvis's own voice about work the
#: code does not do. Each one was reachable from chat (or, for the last one,
#: one edit away from being reachable).
FALSE_CLAIMS = (
    "ui automation",
    "winrt",
    "windows runtime ocr",
    "subtree caching",
    "security perimeter",
    "hands-off",
    "zero external downloads",
    "stark-inspired",
    "tracks your cursor",
    "ripple dynamically",
    "reticle cursor",
    "draws spotlights",
    "hand-drawn glowing loops",
    "waits for your real click",
    # The AGPL-derived geometry and wave (deleted 2026-11-13). No answer may
    # offer them as something this build computes or holds.
    "golden spiral",
    "520 points",
    "wave formula",
    "sphere point",
)


def _all_answers():
    return {
        "overview": C.format_companion_overview(),
        "avatar": C.format_avatar_explanation(),
        "guidance": C.format_guidance_explanation(),
        "askbar": C.format_askbar_explanation(),
        "settings": C.format_settings_summary(),
    }


def t_no_answer_claims_what_is_not_built():
    print("\n--- t_no_answer_claims_what_is_not_built ---------------")
    answers = _all_answers()
    for name, text in answers.items():
        low = text.lower()
        quote = [claim for claim in FALSE_CLAIMS if claim in low]
        check(f"the {name} answer claims no automation, OCR or perimeter",
              not quote, quote)
        check(f"the {name} answer says the visual half is NOT BUILT",
              "not built" in low, text[:120])

    check("the overview names no drawn avatar", "no window of jarvis draws" in answers["overview"].lower())
    check("the guidance answer says nothing is highlighted",
          "nothing is highlighted" in answers["guidance"].lower())
    check("the askbar answer says there is no box",
          "no floating input box" in answers["askbar"].lower())
    check("the settings answer calls them preferences",
          "saved preferences only" in answers["settings"].lower())

    # A damaged or hand-edited settings file must not put its own text into an
    # answer (review finding L3): the old summary printed the value straight.
    path = C._get_settings_path()
    saved = path.read_bytes() if path.is_file() else None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"avatar_style": "BOOM-do-not-echo", "guidance_tone": 7}',
                        encoding="utf-8")
        broken = C.format_settings_summary()
        check("a corrupt style is never echoed back", "BOOM-do-not-echo" not in broken, broken[:160])
        check("...and the answer says the value is not set", "not set" in broken.lower(), broken[:160])
    finally:
        if saved is None:
            try:
                path.unlink()
            except OSError:
                pass
        else:
            path.write_bytes(saved)


# --------------------------------------------------------------------------
# 6. Chat routing, and the private chat's refusal
# --------------------------------------------------------------------------

def _run(intent):
    return Q.run(intent, None, time.time())


def t_chat_routing_and_honest_answers():
    print("\n--- t_chat_routing_and_honest_answers ------------------")
    want = {
        "what are your desktop companion capabilities": "companion_overview",
        "explain your holographic avatar": "companion_avatar_info",
        "how does screen guidance work": "companion_guidance_info",
        "what is the cursor ask bar": "companion_askbar_info",
        "show companion settings": "companion_settings_show",
        "turn on holographic avatar": "companion_toggle",
        "disable screen guidance": "companion_toggle",
        "set avatar style to reticle": "companion_set_style",
    }
    for sentence, name in want.items():
        got = Q.match(sentence)
        check(f"{sentence!r} routes to {name}", got is not None and got.name == name, got)

    res = Q.match("what are your desktop companion capabilities")
    out = _run(res)
    check("the overview answer is the honest one in chat",
          "not built" in out.reply.lower(), out.reply[:120])

    res = Q.match("turn on holographic avatar")
    out = _run(res)
    check("a toggle in chat says it was SAVED, not that it works",
          "Saved" in out.reply and "nothing changes on screen" in out.reply, out.reply[:160])

    res = Q.match("set avatar style to reticle")
    out = _run(res)
    check("a style change in chat says it was SAVED",
          "Saved" in out.reply and "reticle" in out.reply, out.reply[:160])

    # The generic "set style/size/tone" form used to be swallowed by this
    # feature's own grammar. It must not be: an ordinary setting sentence is
    # not this feature's.
    got = Q.match("set style to compact")
    check("a generic 'set style to ...' is NOT the companion's",
          got is None or got.name != "companion_set_style", got)


def t_a_private_chat_cannot_change_a_companion_setting():
    print("\n--- t_a_private_chat_cannot_change_a_companion_setting -")
    check("the companion's READS are on the private-read whitelist",
          "companion_overview" in Q._PRIVATE_DETERMINISTIC_READS
          and "companion_settings_show" in Q._PRIVATE_DETERMINISTIC_READS)
    check("the TOGGLE is deliberately NOT on it",
          "companion_toggle" not in Q._PRIVATE_DETERMINISTIC_READS)
    check("the STYLE CHANGE is deliberately NOT on it",
          "companion_set_style" not in Q._PRIVATE_DETERMINISTIC_READS)
    check("neither change is marked read-only",
          "companion_toggle" not in Q.READ_ONLY_INTENTS
          and "companion_set_style" not in Q.READ_ONLY_INTENTS)

    import jarvis_private_chat

    res = Q.match("turn off avatar")
    check("'turn off avatar' really routes to the toggle",
          res is not None and res.name == "companion_toggle", res)

    C.toggle_feature("avatar", want_on=True)
    path = C._get_settings_path()
    before = path.read_bytes()
    body = {
        "messages": [{"role": "user", "content": "turn off avatar",
                      "provenance": "voice"}],
        "model": "m",
        "stream": False,
        "private": True,
    }
    out = Q.answer_turn(body)
    check("a private chat refuses the change in the one refusal sentence",
          out is not None and out.reply == jarvis_private_chat.REFUSAL,
          None if out is None else out.reply[:160])
    check("...and the settings file on disk did not move",
          path.read_bytes() == before)
    check("...so the avatar preference is still the one saved before",
          C.get_setting("avatar_enabled") is True)


# --------------------------------------------------------------------------
# 7. Governance, hermeticity, twin
# --------------------------------------------------------------------------

def t_governance_and_integrity():
    print("\n--- t_governance_and_integrity -------------------------")
    check("jarvis_companion.py is registered in _where.SHIPPED",
          "jarvis_companion.py" in _where.SHIPPED)

    check("the suite's settings file is its own temp folder",
          str(_TMP) in str(C._get_settings_path()),
          C._get_settings_path())
    check("...and OPENJARVIS_HOME is what put it there",
          str(_TMP) in str(os.environ.get("OPENJARVIS_HOME") or ""))

    backend_path = HERE / "jarvis_companion.py"
    twin_path = ROOT / "jarvis-backend" / "jarvis_companion.py"
    check("twin file exists in jarvis-backend/", twin_path.is_file())
    if backend_path.is_file() and twin_path.is_file():
        b_bytes = backend_path.read_bytes().replace(b"\r\n", b"\n")
        t_bytes = twin_path.read_bytes().replace(b"\r\n", b"\n")
        check("jarvis_companion.py matches twin byte-for-byte", b_bytes == t_bytes)


def main():
    t_a_preference_is_a_preference()
    t_no_agpl_geometry_is_carried()
    t_guidance_description_shaper()
    t_3d_card_shaper()
    t_the_one_denylist_is_the_shared_one()
    t_no_answer_claims_what_is_not_built()
    t_chat_routing_and_honest_answers()
    t_a_private_chat_cannot_change_a_companion_setting()
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
