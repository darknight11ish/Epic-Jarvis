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

  5. A ONE-SIDED CLAIM CARRIES ITS REASON. An entry whose `surface` is
     `"phone"` says the DESKTOP does not have that feature - the claim that
     misinformed the owner three times (see below) - so it must carry a
     `surface_reason`: one sentence saying why, quoted from
     `docs/ARCHITECTURE.md` section 8's one-sided table where the table has it.
     The value alone is not a reason ("phone only" is refused). It covers one
     direction on purpose - see "WHY THE RULE COVERS ONLY `phone`" below.

  6. EVERY LESSON IS CLAIMED BY A FEATURE ROW, OR EXEMPT WITH A REASON
     (reverse completeness). Rule 1 asks "is every menu/route listed?", rules 2
     and 6 ask "is every row's line still true?", and rule 6's forward half
     asks "is every feature taught?". None of them could see the remaining
     hole: a feature ROW vanishes (or is renamed) while its lesson stays in
     `jarvis_tutorials.py`. The old summary printed that as "information, not a
     failure", which is exactly how a silent loss reads. Now every catalogued
     lesson id must appear in at least one row's `covers`, unless
     `LESSON_UNCOVERED` names it with the reason it is deliberately not a
     feature - and that exemption itself fails when it goes stale (a lesson
     deleted, or one that a row now claims). A tutorial the list no longer
     points at is a feature the page has stopped telling the owner about.

WHAT `surface` IS NOT CHECKED AGAINST, AND WHY NOT (2026-10-16)

`surface` is only required to be one of `("desktop", "phone", "both")` - never
to be TRUE. That gap let three entries say `"phone"` for weeks while the
desktop had the feature: PC help (`jarvis-desktop/src/pc-help.js`, Settings ->
Hardware and models), "What did I believe on this date?" (`brain.js:2501`,
`:3018`) and the rush-latch banner (`brain.js:1274-1290`). All three were
corrected by hand; nothing here could have caught them. Two cross-checks were
MEASURED before one was written, and both fail:

  * `covers` ids that are a route in `tools/check_parity.py`: **0 of 131
    entries.** The ids are menu ids (`brain.model.pc-help`) or the Brain's read
    section names (`memory`, `models`, `skills`), so a direct match finds
    nothing at all.
  * Linked indirectly - a `covers` id that is a READ_ROUTES section name, then
    its route, then the parity status: **10 of 131 entries (7.6%)**. On those it
    is wrong in both directions. It flags `memory-tab` (a false positive:
    `memory` there is the section name of the Memory TAB, not a claim about
    `/api/memory/status`), and it cannot see either drift that motivated the
    idea: `brain.model.pc-help` and `brain.trust.rush-latch` appear **0 times**
    in READ_ROUTES, because PC help reaches `/api/pc/help` through
    `hardware.rs` and the banner is drawn by `brain.js`. A check that stays
    green through the case it exists for, and lies on the one case it reaches,
    buys false confidence - which is why there is no such check here.

What is true, for anyone weighing the alternative: 101 of the 131 entries are
`"both"` and only 30 are not (19 `"desktop"`, 11 `"phone"`; #495 moves three of
the phone ones to `"both"`). Each of those 30 is a claim that ONE APP LACKS A
FEATURE - exactly the claim that misinformed the owner here.

WHY THE RULE COVERS ONLY `phone`, AND NOT `"desktop"` TOO (2026-10-16)

Rule 5 is deliberately one-directional, and this is the reason written down so
it does not read as an oversight:

  * `"phone"` has EVIDENCE OF HARM. Three entries said `"phone"` while the
    desktop had the feature - PC help, "What did I believe on this date?" and
    the rush-latch banner - and each told the owner his PC was missing
    something it had. A `surface_reason` makes that negative claim a sentence
    somebody had to write and a reader can weigh.
  * `"desktop"` has no harm this checker can see, and no sentence anybody could
    write honestly today without a fresh survey of the phone, one entry at a
    time. The tempting mechanical signal - "its cover id is a desktop menu id,
    so the phone must not have it" - is NOISE: it fires on 9 of the 11
    phone-only entries, including genuinely Android-only ones (smartwatch
    notifications, Quick Settings tiles, screen refresh rate, the floating
    face), because `menu-catalog.js` is the SHARED registry that the phone's
    `MenuCatalog.kt` is held to. A rule built on it would be switched off
    inside a week.
  * Three `"phone"` entries are exempt through `REASON_PENDING` for the same
    honesty: their claim is FALSE on this tree (the desktop has all three), so
    no sentence saying the desktop lacks them would be true. That list empties
    itself - an id that stops being a `"phone"` entry FAILS, with the line to
    delete named.

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
TUTORIALS_PY = ROOT / "backend" / "jarvis_tutorials.py"

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

#: Rule 5: how a `surface_reason` is judged. Only its SHAPE can be checked - no
#: checker can tell whether a sentence is true, which is exactly why the
#: sentence has to exist for a person to read.
REASON_MIN_WORDS = 6

#: Values that are the `surface` said again rather than a reason for it.
_VALUE_ECHO = {"phone", "phone only", "phone-only", "desktop", "desktop only",
               "desktop-only", "both", "only on the phone", "only on the desktop"}


def reason_is_a_sentence(text: str) -> bool:
    """Is this a sentence somebody wrote, rather than the value restated?"""
    words = str(text or "").split()
    return (len(words) >= REASON_MIN_WORDS
            and " ".join(words).lower().rstrip(".") not in _VALUE_ECHO)


#: Rule 5's exemptions, each with the one line saying why it is here rather
#: than carrying a sentence. Every one is a `"phone"` entry whose claim is
#: FALSE on the tree it was written against - the desktop has the feature - so
#: a `surface_reason` for it would be a lie. `pending_problems()` FAILS the
#: moment one stops being a `"phone"` entry, so this list empties itself
#: instead of rotting.
#:
#: **IT IS EMPTY, AND THAT IS THE MECHANISM WORKING (2026-10-16).** It held
#: three when this rule was written - `pc-help`, `memory-as-of` and
#: `rush-latch` - and PR #495 corrected all three to `"both"` the same day.
#: The checker then failed with, for each one, `delete its line (the entry has
#: been corrected)`, naming the desktop file that has the feature. Deleting
#: them was the whole resolution, and it took one command. **The dict stays,
#: empty, because the next false claim needs exactly this shape**: a place to
#: record "this is deliberately unhandled, and here is what un-handles it"
#: that cannot quietly become permanent.
REASON_PENDING = {}

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

#: The lessons a feature may be taught by, read from the real catalogue. A
#: `covers` list now holds two kinds of id - the menus and routes a feature is
#: reachable through (checked against the registries above) and the tutorials
#: that TEACH it (checked against this). Nothing else distinguishes them, which
#: is the design's own choice (docs/EDUCATION-TAB-DESIGN.md section 8 step 2):
#: "It gains the lessons that teach it, in the same list."
#:
#: The list is read from `backend/jarvis_tutorials.py` itself, so a lesson
#: renamed there cannot be left behind in a `covers` list, and a feature cannot
#: claim a lesson that does not exist.
LESSON_EXEMPT = {
    "typing": "the box you type in; the app's own prompt field is the lesson",
    "interrupt": "the talk button stops the answer; there is nothing to learn",
    "temporary-chat": "one switch in the chat head; its own label is the lesson",
    "history-search": "a search box over the list it is above",
    "file-history": "the drawer explains itself: it lists the copies Jarvis "
                    "took and asks before a restore",
    "people-dossier": "clicking a name in People and things opens it; the card "
                      "names the person and says it is read-only",
    "media-read": "it is one sentence in a chat - name a file and read the "
                  "answer; the module docstring and the tool description are the lesson",
    "quiz": "the deck screen explains itself; it is revision, not a Jarvis feature",
    "decks": "the deck screen explains itself; a deck is yours, not Jarvis's",
    "pc-help": "five answers on one card; the card is the lesson",
    "web-search": "a switch in Settings and a sentence saying search leaves the PC",
    "browser-engine": "a switch in Settings; the card says what it does",
    "support": "one button that starts a support session, and a log to send",
    "settings-by-asking": "saying a setting in words; the reply names the setting",
    "settings-entry": "the way into Settings; the tray row and Ctrl+K say where",
    "start-the-model-lane": "one button on the standing line, which names the lane that is down and says what pressing it does",
    "restart-the-model-lane": "automatic and nothing to press; the line says what Jarvis did, in its own words",
    "data-sandbox": "one switch in Settings whose card says what it does; the PC's own line says what the last card did",
    "focus-presets": "the preset card explains itself in the PC's own words; its one action stays disabled until the lane/apply patch, so a lesson would teach a button that does nothing yet",
    "write-like-me": "the training screen it would teach is the next UI slice; this row is the catalogue half, so a lesson now would teach a screen that is not built yet",
    "setup-questionnaire": "the card explains itself: fourteen questions in the owner's own words, a read-only plan naming each effect, and one Apply that asks twice; a lesson would repeat the card",
}
}

#: Rule 6's exemptions: lessons that are deliberately NOT a feature row, each
#: with the one line saying why nobody reaches it from this list. The reverse of
#: `LESSON_EXEMPT` above (which is keyed by FEATURE id and says "this feature
#: needs no lesson"): this one is keyed by LESSON id and says "this lesson is
#: not any feature's page". A stale line is itself an error - a lesson that no
#: longer exists, a lesson whose reason is empty, or a lesson a feature row now
#: claims all FAIL, so the list empties itself instead of becoming a hiding
#: place (the same shape REASON_PENDING already has).
#:
#: **IT IS EMPTY, AND THAT IS THE MECHANISM WORKING (2026-10-18).** The audit
#: that added the reverse check found the last two unclaimed lessons -
#: `phone-talking` (the phone's hold-to-talk button, which the "talk-button" row
#: describes) and `phone-stays-on-pc` (the "phone-limits" row's own subject) -
#: and named them from those rows instead of exempting them, because a feature
#: row genuinely teaches each. The dict stays, empty: the next lesson that is a
#: cross-cutting rule rather than a feature needs exactly this place, and its
#: entry must carry the sentence saying which rule.
LESSON_UNCOVERED = {}


def lesson_ids() -> list:
    """Every tutorial id the catalogue really defines, in file order.

    Read from the source rather than by importing the module: this checker runs
    in CI beside every other one and must not need the backend's runtime (the
    module imports `jarvis_framework` when it is there). The pattern is the same
    shape `tools/check_tutorial_places.py` reads the same file with.
    """
    text = TUTORIALS_PY.read_text(encoding="utf-8")
    start = text.index("CATALOGUE = (")
    block = text[start:text.index("\n)\n", start)]
    ids = re.findall(r'^\s{8}"id": "([a-z0-9-]+)",$', block, re.MULTILINE)
    if len(ids) < 20:
        raise AssertionError(f"read only {len(ids)} lesson ids from jarvis_tutorials.py - the parse broke")
    return ids


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
        # Rule 5: a `"phone"` entry claims the DESKTOP lacks the feature, so it
        # must say why - unless REASON_PENDING has already said why no sentence
        # is owed (see that dict, and the docstring's "WHY THE RULE COVERS ONLY
        # `phone`").
        if e.get("surface") == "phone" and where not in REASON_PENDING:
            reason = str(e.get("surface_reason") or "").strip()
            if not reason:
                bad.append(f"{where}: says `phone` with no `surface_reason` - add one "
                           f"sentence saying why the desktop does not have it")
            elif not reason_is_a_sentence(reason):
                bad.append(f"{where}: `surface_reason` is not a reason, it is the value "
                           f"said again: {reason!r}")
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
    lessons = set(lesson_ids())
    for e in got:
        for c in e.get("covers") or []:
            if c in known or c in INTERNAL:
                continue
            if c in lessons:
                continue
            bad.append(f"{e.get('id')}: covers `{c}`, which is in no registry, "
                       "in no lesson and in INTERNAL")
    return bad


def teaching_problems(got: list, known: dict) -> list:
    """Rule 6: every feature is taught by a lesson, or exempted with a reason.

    THE POINT OF THE WHOLE EXERCISE (docs/EDUCATION-TAB-DESIGN.md section 8):
    "A new feature with neither a lesson nor an exemption becomes a red check,
    not a note nobody reads." The exemption is the project's existing pattern -
    a short list, each entry with a reason, and a stale entry is itself an
    error (INTERNAL above, PHONE_LACKS in check_registry_phone.py, KNOWN_DRIFT
    in check_tutorial_places.py).

    The two kinds of id are told apart by looking the id up, and a name that
    exists in BOTH is not an error: it is a lesson. `memory` is the real case -
    a route section in `READ_ROUTES` and a tutorial id - and a `covers` list
    naming it is a claim about the tutorial, which is what this rule is for. A
    registry id is still checked where a registry id belongs, by rules 1 and 2.
    """
    bad = []
    lessons = set(lesson_ids())
    seen = {e.get("id") for e in got if isinstance(e, dict)}
    for fid, why in LESSON_EXEMPT.items():
        if not str(why).strip():
            bad.append(f"LESSON_EXEMPT `{fid}` has no reason")
        if fid not in seen:
            bad.append(f"LESSON_EXEMPT lists `{fid}`, which is not a feature any "
                       "more - delete the line")
        else:
            entry = next(e for e in got if e.get("id") == fid)
            taught = [c for c in (entry.get("covers") or []) if c in lessons]
            if taught:
                bad.append(f"{fid} is in LESSON_EXEMPT and also names the lesson(s) "
                           f"{', '.join(taught)} - one or the other")
    for e in got:
        fid = e.get("id")
        taught = [c for c in (e.get("covers") or []) if c in lessons]
        if taught or fid in LESSON_EXEMPT:
            continue
        bad.append(f"{fid}: no lesson teaches it and it is not in LESSON_EXEMPT - "
                   "name the lesson in `covers`, or add it to LESSON_EXEMPT with "
                   "the one-line reason teaching it is not useful")
    return bad


def lesson_problems(got: list, lessons=None, exempt=None) -> list:
    """Rule 6, reverse completeness: a lesson with no feature row is an orphan.

    THE HOLE THIS CLOSES (Gemini's ruling, Part II, on Session B section 11.3).
    Every direction except this one was already checked: a feature the code has
    but the list omits; a `covers` id the code no longer has; a feature row with
    no lesson. What nothing could see was a feature ROW disappearing while its
    lesson stayed in `jarvis_tutorials.py` - the checker's own summary printed
    "lessons no feature names (information, not a failure)", so the one loss
    this list exists to prevent was the one nobody would act on. Now an
    unclaimed lesson FAILS, naming the lesson and the two honest fixes: name it
    from the feature row that teaches it, or record in `LESSON_UNCOVERED` why it
    is a cross-cutting rule rather than a feature.

    `lessons` and `exempt` are injectable so the suite can prove the rule bites
    without editing the catalogue or the real list (the same way the other
    problems() helpers are called with made-up input).
    """
    lesson_list = list(lessons if lessons is not None
                       else lesson_ids())
    exempt_map = dict(LESSON_UNCOVERED if exempt is None else exempt)
    bad = []
    claimed_by = {}
    for e in got:
        if not isinstance(e, dict):
            continue
        for c in e.get("covers") or []:
            if c in lesson_list:
                claimed_by.setdefault(c, []).append(str(e.get("id")))
    for lesson in lesson_list:
        if lesson in claimed_by:
            if lesson in exempt_map:
                bad.append(f"LESSON_UNCOVERED `{lesson}` is exempt, but `{claimed_by[lesson][0]}` "
                           "names the lesson now - delete the exemption line (it is covered)")
            continue
        if lesson not in exempt_map:
            bad.append(f"lesson `{lesson}` is in jarvis_tutorials.py, but no feature row's "
                       "`covers` names it - name it in the feature row that teaches it, or add "
                       "it to LESSON_UNCOVERED with the reason it is deliberately not a feature")
    for lesson, why in exempt_map.items():
        if lesson not in lesson_list:
            bad.append(f"LESSON_UNCOVERED `{lesson}` is not a lesson in jarvis_tutorials.py any "
                       "more - delete the line")
        elif not str(why).strip():
            bad.append(f"LESSON_UNCOVERED `{lesson}` has no reason")
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


def pending_problems(got: list) -> list:
    """Rule 5's other half: an exemption that is no longer needed FAILS.

    `REASON_PENDING` names the entries that cannot carry a true one-sided
    sentence yet. The moment one of them stops being a `"phone"` entry it has
    been corrected (`#495`), so its line is stale - the same rule `INTERNAL`
    already follows for a line whose id is gone. That is what keeps the list
    from becoming a permanent hiding place."""
    phones = {e.get("id") for e in got
              if isinstance(e, dict) and e.get("surface") == "phone"}
    return [f"REASON_PENDING names `{name}`, which is no longer a `phone` entry - "
            f"delete its line (the entry has been corrected): {why}"
            for name, why in sorted(REASON_PENDING.items()) if name not in phones]


def problems() -> list:
    """Everything wrong, in one list, each line naming what to fix."""
    got = entries()
    known = known_ids()
    return (field_problems(got) + phantom_covers(got, known) + uncovered(got, known)
            + internal_problems(known) + copy_problems() + teaching_problems(got, known)
            + lesson_problems(got) + pending_problems(got))


def main() -> int:
    got = entries()
    known = known_ids()
    lessons = set(lesson_ids())
    checks = [
        (f"{len(got)} entries, each with what / where / asks / limit / surface, and a "
         f"`surface_reason` where it claims the other app lacks it",
         field_problems(got)),
        ("every `covers` id is a real registry id, a real lesson, or in INTERNAL",
         phantom_covers(got, known)),
        (f"every one of the {len(known)} route sections and menu ids is covered or in INTERNAL",
         uncovered(got, known)),
        (f"INTERNAL's {len(INTERNAL)} lines are real, with reasons", internal_problems(known)),
        ("the three copies of features.json are byte-identical", copy_problems()),
        (f"a `phone` reason is owed, never dropped: REASON_PENDING's "
         f"{len(REASON_PENDING)} line(s) are self-emptying", pending_problems(got)),
        (f"every feature is taught by one of the {len(lessons)} lessons, or exempt with a reason",
         teaching_problems(got, known)),
        (f"every one of the {len(lessons)} lessons is named by a feature row or in "
         f"LESSON_UNCOVERED ({len(LESSON_UNCOVERED)} exempt) - reverse completeness",
         lesson_problems(got)),
    ]
    failed = 0
    for name, bad in checks:
        print(("ok   " if not bad else "FAIL ") + name)
        for line in bad:
            print(f"        {line}")
        failed += bool(bad)
    covered = set()
    taught = 0
    by_lesson = {}
    for e in got:
        covered.update(e.get("covers") or [])
        named = [c for c in (e.get("covers") or []) if c in lessons]
        if named:
            taught += 1
        for lesson in named:
            by_lesson[lesson] = by_lesson.get(lesson, 0) + 1
    print(f"\n{len(got)} entries in {len(GROUPS)} groups; "
          f"{len(covered & set(known))} of {len(known)} route sections and menu ids covered, "
          f"{len(INTERNAL)} named in INTERNAL")
    print(f"{taught} of {len(got)} features are taught by a lesson; "
          f"{len(LESSON_EXEMPT)} are exempt with a reason; "
          f"{len(by_lesson)} of the {len(lessons)} lessons are named by a feature")
    unclaimed = sorted(lessons - set(by_lesson) - set(LESSON_UNCOVERED))
    if unclaimed:
        print("lessons no feature names (FAILED above, listed so the fix is one line each): "
              + ", ".join(unclaimed))
    print(f"{len(checks) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
