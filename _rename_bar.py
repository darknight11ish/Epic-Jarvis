"""Rename the HUD's bar button from "Open the Jarvis bar" to "Open the Atlas bar".

The 2026-11-12 visible rename made the product say Atlas everywhere it can be
seen, and missed this one label: it is the tooltip AND the accessible name of
the button beside the big window's chat box, so a screen reader still said
"Open the Jarvis bar" on an app called Atlas.

Only the button's own name is replaced, in code and in the tests that pin it.
Prose that merely mentions the bar ("the Jarvis bar's gear", "Jarvis is locked")
is left alone: the change's own changelog says the assistant still introduces
itself as Jarvis until the backend wording pass, and that pass owns sentences.
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
OLD = "Open the Jarvis bar"
NEW = "Open the Atlas bar"
MIC_OLD = "Talk to Jarvis: opens the quickbar"
MIC_NEW = "Talk to Atlas: opens the quickbar"

# Every file that carries the button's own name. Generated files are NOT here:
# they are re-made from the registry afterwards.
SOURCES = [
    "backend/jarvis_menus.py",
    "backend/jarvis_settings_registry.py",
    "backend/jarvis_tutorials.py",
    "backend/static/hud-layout.js",
    "backend/static/hud-web-bridge.js",
    "contract/feature-controls.json",
    "jarvis-desktop/src-tauri/src/hud_bootstrap.js",
    "jarvis-desktop/src-tauri/src/clipboard_time_machine.rs",
    "jarvis-desktop/src-tauri/src/hotkeys.rs",
    "jarvis-desktop/src-tauri/src/live.rs",
    "jarvis-desktop/src-tauri/src/look.rs",
    "jarvis-desktop/src-tauri/src/talk_type/rules.rs",
    "jarvis-desktop/src-tauri/src/voice.rs",
    "jarvis-desktop/src-tauri/src/windows.rs",
    "jarvis-desktop/src/hud-window-settings.js",
    "jarvis-desktop/src/hud-window.js",
    "jarvis-desktop/src/live-badge.html",
    "backend/jarvis_hud.html",
    "jarvis-desktop/tests/hud-layout.mjs",
    "jarvis-desktop/tests/hud-live-read-aloud.mjs",
    "jarvis-desktop/tests/hud-web-bridge.mjs",
    "jarvis-desktop/tests/hud-window.mjs",
    "jarvis-desktop/tests/hud.mjs",
    "jarvis-desktop/tests/uikit.mjs",
]

changed = 0
total = 0
for rel in SOURCES:
    path = ROOT / rel
    if not path.is_file():
        print(f"MISSING: {rel}")
        sys.exit(1)
    text = path.read_text(encoding="utf-8")
    hits = text.count(OLD)
    new = text.replace(OLD, NEW)
    if "hud_bootstrap.js" in rel:
        mic = new.count(MIC_OLD)
        new = new.replace(MIC_OLD, MIC_NEW)
        if mic:
            print(f"  {rel}: mic hint x{mic}")
    if new != text:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
        changed += 1
        total += hits
        print(f"  {rel}: x{hits}")

print(f"\n{changed} files, {total} occurrences of the button's name")

# The twins the rule requires to be byte-identical, and the two desktop copies
# of the vendored HUD scripts.
COPIES = [
    ("backend/jarvis_menus.py", "jarvis-backend/jarvis_menus.py"),
    ("backend/jarvis_settings_registry.py", "jarvis-backend/jarvis_settings_registry.py"),
    ("backend/jarvis_tutorials.py", "jarvis-backend/jarvis_tutorials.py"),
    ("backend/static/hud-layout.js", "jarvis-backend/hud-layout.js"),
    ("backend/static/hud-layout.js", "jarvis-desktop/src/hud-layout.js"),
    ("backend/static/hud-web-bridge.js", "jarvis-backend/hud-web-bridge.js"),
    ("backend/static/hud-web-bridge.js", "jarvis-desktop/src/hud-web-bridge.js"),
    ("backend/jarvis_hud.html", "jarvis-backend/jarvis_hud.html"),
    ("backend/jarvis_hud.html", "jarvis-desktop/src/jarvis_hud.html"),
]
for src, dst in COPIES:
    data = (ROOT / src).read_bytes()
    with open(ROOT / dst, "wb") as fh:
        fh.write(data)
    print(f"  copied {src} -> {dst}")

left = subprocess.run(["git", "grep", "-c", OLD, "--",
                       "backend/*.py", "backend/static/*", "jarvis-backend/*",
                       "jarvis-desktop/src/*", "jarvis-desktop/src-tauri/src/*",
                       "jarvis-desktop/tests/*", "contract/*.json",
                       "jarvis-client/app/src/main/**"],
                      cwd=ROOT, capture_output=True, text=True)
print("\nremaining in code (generated files not yet re-made show up here too):")
print(left.stdout.strip() or "  none")
