#!/usr/bin/env python3
"""Is "Everything Jarvis can do" complete, and is every line on it still true?

    python3 tools/check_feature_list.py

The owner asked, 2026-10-08: *"is there a button where I can find the entire
feature set of Jarvis on my desktop or android phone? It's important I can know
all the features, with an extend button on each feature where I can get
additional info."*  `features/features.json` is that list, and this is the
check that keeps it honest (docs/FEATURES-LIST-DESIGN.md).

BOTH DIRECTIONS, which is the whole point:

  1. NOBODY ADDED A FEATURE AND FORGOT THE LIST. Every route section the
     desktop's Brain may read (`jarvis-desktop/src-tauri/src/brain/routes.rs`,
     READ_ROUTES) and every menu id either app draws
     (`jarvis-desktop/src/menu-catalog.js`, the registry
     `menu-visibility-settings.js` renders; and
     `jarvis-client/.../ui/MenuPlaces.kt`, where each phone menu lives) is
     either named in some entry's `covers` list or named in `INTERNAL` below
     with a one-line reason. A new pane, command or menu that nobody listed
     FAILS here.

  2. NOBODY REMOVED A FEATURE AND LEFT THE LINE BEHIND. Every id in a `covers`
     list must still exist in the code, and every `INTERNAL` id must too. A
     page that promises a button which is gone is worse than no page.

  3. EVERY ENTRY IS READABLE. Each one has a non-empty `what`, `where` and
     `asks` - the three questions a beginner actually has - and a `group` from
     the fixed list, in the fixed order.

  4. THE THREE COPIES ARE ONE FILE. `features/features.json` is the source;
     `jarvis-desktop/src/features.json` and
     `jarvis-client/app/src/main/assets/features.json` are byte-identical
     copies of it, read at run time by each app with no bundler and no build
     step. The same rule `backend/test_base_matches_repo.py` already applies to
     the backend copies, so this is one precedent rather than a new idea.

WHY `INTERNAL` AND NOT "one entry per route": 249 backend routes are not 249
features to a person - most are plumbing behind a button that IS listed. The
allow-list below is what keeps "curated for reading" from meaning
"incomplete": every id in it says, in one line, what it is and why the owner
never presses it directly. It is deliberately as small as the truth allows.

Run through `backend/run_suites.py test_feature_list.py`, which is how CI runs
it with the other Python suites.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE = ROOT / "features" / "features.json"
COPIES = (
    ROOT / "jarvis-desktop" / "src" / "features.json",
    ROOT / "jarvis-client" / "app" / "src" / "main" / "assets" / "features.json",
)
ROUTES_RS = ROOT / "jarvis-desktop" / "src-tauri" / "src" / "brain" / "routes.rs"
MENU_CATALOG = ROOT / "jarvis-desktop" / "src" / "menu-catalog.js"
MENU_PLACES = (
    ROOT / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
    / "client" / "ui" / "MenuPlaces.kt"
)

#: The groups, in the order both apps draw them (docs/FEATURES-LIST-DESIGN.md).
GROUPS = [
    "Talking",
    "Memory",
    "Screen and pictures",
    "Notes and files",
    "Money and health",
    "Home",
    "Phone",
    "The PC itself",
    "Safety",
]

SURFACES = ("desktop", "phone", "both")

#: Ids that are real but are never a row of their own, each with the one-line
#: reason the owner never presses it. Keyed by the id exactly as the code
#: spells it. An entry here that no longer exists in the code fails too.
INTERNAL = {
    "attention": "the interruption-budget read; the card 'attention-budget' names it",
    "compute": "the graphics-card plan is drawn inside the Models/Compute card the 'Compute' entry names",
    "config": "the settings file's own read; the card that shows and changes it is 'settings-file'",
    "digest": "the daily brief is drawn in the Jarvis bar's own waiting line, not a screen of its own; 'attention-budget' names it",
    "gate_history": "read-only past approvals; the card is 'past-approvals'",
    "initiative": "what Jarvis noticed by itself, drawn in the Now pane 'now' names",
    "jobs": "the background-job list is one pane of the Work tab; the 'jobs' entry names it",
    "ledger": "the audit chain, read and drawn inside the Trust tab 'trust' names",
    "memory": "the memory counts read behind the Learning card; 'memory-learning' names it",
    "memory_entities": "the people-and-things read behind the list; 'memory-people' names it",
    "memory_facts": "the whole fact store read behind the list; 'memory-known' names it",
    "memory_pending": "the cards waiting for a yes; 'memory-waiting' names it",
    "content_risk": "the scanner's own read; its results are drawn in the Trust tab 'trust' names",
    "status": "the connection and model status read; the 'connection' entry names the line it feeds",
    "undo": "the undo shelf's own read; the 'undo' entry names the pane",
    "watch": "the GitHub watchlist's own read; 'github-watchlist' names the feature",
    "watch_report": "the GitHub watchlist's read-only peek; 'github-watchlist' names the feature",
}


def source_bytes() -> bytes:
    return SOURCE.read_bytes()


def entries() -> list:
    """The list, as checked in."""
    got = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(got, list):
        raise AssertionError("features/features.json must be an array of entries")
    return got


def route_sections() -> list:
    """Every route section the Brain window may read, by name, in file order.

    READ_ROUTES is the allow-list itself (`("status", "/api/status")`); this
    reads the names only, and refuses to guess if the shape changed - a parse
    that quietly found nothing would make every "is it covered" answer yes.
    """
    text = ROUTES_RS.read_text(encoding="utf-8")
    start = text.index("const READ_ROUTES")
    block = text[start:text.index("];", start)]
    names = []
    for line in block.splitlines():
        # `    ("status", "/api/status"),` and the one wrapped entry, which puts
        # only the name on its own line. Comments start with `//`, never `"`.
        m = re.match(r'\s*\(?\s*"([a-z_]+)",', line)
        if m:
            names.append(m.group(1))
    if len(names) < 10:
        raise AssertionError(f"read only {len(names)} route sections from READ_ROUTES - the parse broke")
    return names


def desktop_menu_ids() -> list:
    """Every menu id the desktop's registry holds, in file order.

    `menu-visibility-settings.js` - the file the design note names - holds no
    ids at all: it renders the registry `menu-catalog.js` exports, which is
    generated from `backend/jarvis_menus.py` by `tools/gen_menu_cases.py`. The
    registry is read here for that reason, and `menu-catalog.js` is the same
    list the phone's MenuCatalog.kt is held to.
    """
    text = MENU_CATALOG.read_text(encoding="utf-8")
    start = text.index("export const MENUS")
    block = text[start:text.index("export const NEVER_HIDE", start)]
    ids = re.findall(r'\n    "id": "([^"]+)"', block)
    if len(ids) < 50:
        raise AssertionError(f"read only {len(ids)} menu ids from menu-catalog.js - the parse broke")
    return ids


def phone_menu_ids() -> list:
    """Every menu id the phone's own places name (`ui/MenuPlaces.kt`).

    SETTINGS and BRAIN map an `item(key = ...)` to a menu id, so the id is on
    the right of `to`; INSIDE is keyed BY the id, so it is on the left. Both
    halves are read, in that order.

    SETTINGS_ALIAS is deliberately NOT read: it maps a *settings-registry*
    section id ("appearance-card") to the item key that draws it, and neither
    side of it is a menu id. MenuVisibilityTest holds the places - SETTINGS,
    BRAIN and INSIDE - to the same registry this does.
    """
    text = MENU_PLACES.read_text(encoding="utf-8")
    ids = []
    for name, side in (("SETTINGS", "right"), ("BRAIN", "right"),
                       ("INSIDE", "left")):
        at = text.index(f"val {name}: Map<String, String> = mapOf(")
        block = text[at:text.index("\n    )", at)]
        for m in re.finditer(r'"([^"]+)"\s+to\s+"([^"]*)"', block):
            ids.append(m.group(2) if side == "right" else m.group(1))
    if len(ids) < 50:
        raise AssertionError(f"read only {len(ids)} menu ids from MenuPlaces.kt - the parse broke")
    return ids


def known_ids() -> dict:
    """id -> where it came from, for everything that must be covered."""
    out = {}
    for name in route_sections():
        out[name] = "jarvis-desktop/src-tauri/src/brain/routes.rs (READ_ROUTES)"
    for name in desktop_menu_ids():
        out.setdefault(name, "jarvis-desktop/src/menu-catalog.js (MENUS)")
    for name in phone_menu_ids():
        out.setdefault(name, "jarvis-client .../ui/MenuPlaces.kt")
    return out


def field_problems(got: list) -> list:
    """Rule 3: every entry is a readable row with an id, a group and a surface."""
    bad = []
    seen = set()
    for i, e in enumerate(got):
        if not isinstance(e, dict):
            bad.append(f"entry {i} is not an object")
            continue
        where = e.get("id") or f"entry {i}"
        for key in ("id", "group", "title", "what", "where", "asks", "limit", "surface", "covers"):
            if key not in e:
                bad.append(f"{where}: no `{key}`")
        if where in seen:
            bad.append(f"{where}: listed twice")
        seen.add(where)
        for key in ("what", "where", "asks"):
            if not str(e.get(key) or "").strip():
                bad.append(f"{where}: `{key}` is empty")
        if e.get("group") not in GROUPS:
            bad.append(f"{where}: group `{e.get('group')}` is not one of the nine")
        if e.get("surface") not in SURFACES:
            bad.append(f"{where}: surface `{e.get('surface')}` is not one of {SURFACES}")
        if not isinstance(e.get("limit"), str):
            bad.append(f"{where}: `limit` must be a string (empty when there is none)")
        if not isinstance(e.get("covers"), list) or any(not isinstance(c, str) for c in e.get("covers") or []):
            bad.append(f"{where}: `covers` must be a list of ids")
    # The group order is the design note's, and the file is written in it.
    order = [e.get("group") for e in got if isinstance(e, dict)]
    firsts = [g for i, g in enumerate(order) if i == 0 or order[i - 1] != g]
    if firsts != [g for g in GROUPS if g in set(firsts)]:
        bad.append(f"the groups are not in the fixed order: {firsts}")
    return bad


def phantom_covers(got: list, known: dict) -> list:
    """Rule 2: a `covers` id that is no longer in the code (or in INTERNAL)."""
    bad = []
    for e in got:
        for c in e.get("covers") or []:
            if c not in known and c not in INTERNAL:
                bad.append(f"{e.get('id')}: covers `{c}`, which is in no registry and in INTERNAL")
    return bad


def uncovered(got: list, known: dict) -> list:
    """Rule 1: an id nobody listed - a feature added without being written down."""
    covered = set()
    for e in got:
        covered.update(e.get("covers") or [])
    return sorted(i for i in known if i not in covered and i not in INTERNAL)


def internal_problems(known: dict) -> list:
    """The allow-list itself: every id in it real, every reason non-empty."""
    bad = []
    for i, why in INTERNAL.items():
        if i not in known:
            bad.append(f"INTERNAL lists `{i}`, which is in no registry any more")
        if not str(why).strip():
            bad.append(f"INTERNAL `{i}` has no reason")
    return bad


def copy_problems() -> list:
    """Rule 4: the source and its two copies are one file."""
    bad = []
    want = source_bytes()
    for path in COPIES:
        if not path.is_file():
            bad.append(f"{path.relative_to(ROOT)} is missing")
        elif path.read_bytes() != want:
            bad.append(f"{path.relative_to(ROOT)} differs from features/features.json "
                       "(copy it again - the two apps read their own copy)")
    return bad


def problems() -> list:
    """Everything wrong, in one list, each line naming what to fix."""
    got = entries()
    known = known_ids()
    return (field_problems(got) + phantom_covers(got, known) + uncovered(got, known)
            + internal_problems(known) + copy_problems())


def main() -> int:
    got = entries()
    known = known_ids()
    checks = [
        (f"{len(got)} entries, each with what / where / asks / limit / surface",
         field_problems(got)),
        ("every `covers` id is still in the code", phantom_covers(got, known)),
        (f"every one of the {len(known)} route sections and menu ids is covered or in INTERNAL",
         uncovered(got, known)),
        (f"INTERNAL's {len(INTERNAL)} lines are real, with reasons", internal_problems(known)),
        ("the three copies of features.json are byte-identical", copy_problems()),
    ]
    failed = 0
    for name, bad in checks:
        print(("ok   " if not bad else "FAIL ") + name)
        for line in bad:
            print(f"        {line}")
        failed += bool(bad)
    covered = set()
    for e in got:
        covered.update(e.get("covers") or [])
    print(f"\n{len(got)} entries in {len(GROUPS)} groups; "
          f"{len(covered & set(known))} of {len(known)} route sections and menu ids covered, "
          f"{len(INTERNAL)} named in INTERNAL")
    print(f"{len(checks) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
