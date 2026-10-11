#!/usr/bin/env python3
"""Resolve the merge's three conflicts, and move THIS branch's API section.

THE COLLISION. `main` already holds `## 124. Which card draws the pictures`
(jarvis_picture_card.py, PR #248) and `## 125. The owner's uncensored opt-ins`.
This branch's own section was also `## 124. Ask for a picture, and keep it`.
Main is merged and its files cite 124, so THIS branch moves - to **126**, the
next free number. Every reference this branch added moves with it; main's own
"section 124" references (test_picture_card.py, the picture-card patch comment)
are left exactly as they are.

Also resolves:
  * docs/JARVIS-API.md  - main's file, plus this branch's section renumbered
  * jarvis-backend twins - copied from backend/, and _where.py re-derived from
    the repository's copy + the base's own trailer
The third conflict, MenuCatalog.kt, is GENERATED and is rewritten by
tools/gen_menu_cases.py after this runs.
"""
import re
import subprocess
import sys
from pathlib import Path

#: Every one of these holds only THIS branch's "section 124" references
#: (checked by reading each line; main's picture-card references are in
#: backend/test_picture_card.py and scripts/apply-patches.ps1, neither listed).
SECTION_FILES = [
    "backend/_where.py",
    "backend/jarvis_menus.py",
    "backend/jarvis_settings_registry.py",
    "backend/test_settings_rows.py",
    "jarvis-backend/jarvis_menus.py",
    "jarvis-backend/jarvis_settings_registry.py",
    "jarvis-desktop/src/brain.html",
    "jarvis-desktop/src/pictures-panel.js",
    "jarvis-desktop/src/pictures-settings.js",
    "jarvis-desktop/src/projects-panel.js",
    "jarvis-desktop/src/settings.html",
    "jarvis-desktop/src-tauri/permissions/surfaces.toml",
    "jarvis-desktop/src-tauri/src/brain/pictures.rs",
    "jarvis-desktop/src-tauri/src/lib.rs",
    "jarvis-desktop/src-tauri/build.rs",
    "jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/net/Pictures.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/PicturesPlate.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
    "jarvis-client/app/src/test/java/com/jarvis/client/PicturesTest.kt",
    "jarvis-client/app/src/test/java/com/jarvis/client/SettingsCatalogTest.kt",
    "tools/check_parity.py",
]

#: apply-patches.ps1 holds BOTH features: this branch's pictures.patch notes AND
#: main's picture-card note ("JARVIS-API section 124): GET and POST
#: /api/picture-card"), which must NOT move. So the two pictures.patch lines are
#: replaced by their own words, and main's line is left alone.
PS1_EDITS = [
    ('# card at once)"; docs/JARVIS-API.md section 124).',
     '# card at once)"; docs/JARVIS-API.md section 126).'),
    ('# --- Ask for a picture, and keep it (2026-10-11, pictures.patch, JARVIS-API section 124) ---',
     '# --- Ask for a picture, and keep it (2026-10-11, pictures.patch, JARVIS-API section 126) ---'),
    # main's picture-card note points at this branch's route and calls it
    # "section 123", which is the limits section - stale either way. The route
    # it names is this branch's, so it moves to 126 with everything else.
    ("# jarvis_pictures.py's route, section 123), starts nothing",
     "# jarvis_pictures.py's route, section 126), starts nothing"),
]


def show(rev: str, path: str) -> str:
    out = subprocess.run(["git", "show", f"{rev}:{path}"],
                         capture_output=True, check=True)
    return out.stdout.decode("utf-8")


def renumber(text: str) -> str:
    text = re.sub(r"^(#{2,3}) 124\.", r"\1 126.", text, flags=re.M)
    return text.replace("section 124", "section 126")


def main() -> int:
    # 1. docs/JARVIS-API.md: main's file + this branch's section, renumbered.
    main_doc = show("origin/main", "docs/JARVIS-API.md").rstrip("\n")
    branch_doc = show("HEAD", "docs/JARVIS-API.md").splitlines()
    start = next(i for i, l in enumerate(branch_doc)
                 if l.startswith("## 124. Ask for a picture"))
    section = "\n".join(branch_doc[start:])
    if not section.startswith("## 124. Ask for a picture"):
        print("FAIL  the branch's section is not where it was looked for")
        return 1
    text = main_doc + "\n\n---\n\n" + renumber(section) + "\n"
    Path("docs/JARVIS-API.md").write_text(text, encoding="utf-8", newline="\n")
    print("docs/JARVIS-API.md: main's file, this branch's section as 126")

    changed = 0
    for name in SECTION_FILES:
        path = Path(name)
        if not path.is_file():
            print(f"FAIL  {name} is not here")
            return 1
        before = path.read_text(encoding="utf-8")
        after = before.replace("section 124", "section 126")
        if after != before:
            path.write_text(after, encoding="utf-8", newline="\n")
            changed += 1
    print(f"{changed} file(s) moved their section-124 reference to 126")

    # 2. test_pictures.py also asserts the document's own heading.
    tp = Path("backend/test_pictures.py")
    text = tp.read_text(encoding="utf-8")
    text = text.replace('check("docs/JARVIS-API.md has section 124", "## 124." in api,',
                        'check("docs/JARVIS-API.md has section 126", "## 126." in api,')
    text = text.replace('"no section 124 yet")', '"no section 126 yet")')
    tp.write_text(text, encoding="utf-8", newline="\n")
    print("test_pictures.py: its doc-section assertion moved to 126")

    # 3. apply-patches.ps1: this branch's two lines, and main's stale pointer.
    ps1 = Path("scripts/apply-patches.ps1")
    text = ps1.read_text(encoding="utf-8")
    for old, new in PS1_EDITS:
        if old not in text:
            print(f"FAIL  apply-patches.ps1 does not hold: {old[:60]}")
            return 1
        text = text.replace(old, new)
    ps1.write_text(text, encoding="utf-8", newline="\n")
    print("apply-patches.ps1: this branch's two notes, and main's stale pointer")

    # 4. The twins, and the base's derived copy of _where.py.
    for name in ("jarvis_menus.py", "jarvis_settings_registry.py"):
        src = Path("backend") / name
        dst = Path("jarvis-backend") / name
        dst.write_bytes(src.read_bytes())
    sys.path.insert(0, "tools")
    import gen_base_from_backend as G                      # noqa: PLC0415
    repo = Path(".").resolve()
    out = repo / "jarvis-backend" / "_where.py"
    out.write_text(G.base_where_text(repo), encoding="utf-8", newline="\n")
    print("twins copied; jarvis-backend/_where.py re-derived from the rule")
    return 0


if __name__ == "__main__":
    sys.exit(main())
