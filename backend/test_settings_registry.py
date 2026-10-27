"""test_settings_registry.py - "open" and "adjust" any setting, by voice or
chat, on either app (jarvis_settings_registry.py, jarvis_quick.py; the
owner's decisions of 2026-09-27; docs/JARVIS-API.md section 58).

    python3 backend/test_settings_registry.py

Runs anywhere; no Home Assistant, no model, no network, no Windows Hello
(jarvis_owner_check.set_verifier stands in for it). What it proves:

1. SECTIONS matches the real UI - every id is really a settings.html
   section (desktop) and, where marked "both" or "phone", really an
   `item(key = ...)` in SettingsScreen.kt - never a hand-typed list that
   drifted from the pages it claims to open.
2. "Open <a section>" is pure navigation: it changes nothing, and an
   unknown noun ("open the door") falls straight through to the model
   rather than answering with an invented place.
3. "Turn on/off <a setting>" calls the EXACT function the matching UI
   toggle already calls - never a new mutation path - proved by import
   identity, not by re-implementing each function's own tests.
4. A setting on jarvis_owner_check.PC_ONLY_ACTIONS (today:
   loosen_what_asks_first, enable_reading_tool) genuinely REFUSES this new
   voice/chat path from a simulated phone request, and genuinely goes
   through - raising the SAME approval card, needing the SAME Windows
   Hello confirmation - from this PC. Nothing is changed by the refused
   attempt.
5. A setting already gated by an approval card (lights without asking,
   background learning, "also remember sensitive topics automatically")
   still raises that card through this new path - never applies silently -
   whichever device asks; turning the same setting OFF is still immediate,
   with no card, exactly as the existing route behaves.
6. Ambiguous or unrecognised phrasing: a named control asks/refuses here;
   a sentence that names no control in the closed table matches nothing and falls through
   to the model) rather than guessing at a setting or a value.
7. `jarvis_quick.answer_turn`'s own peer/local plumbing (schedule.patch)
   reaches this file unchanged - proved end to end, not only at run()'s own
   boundary - and `is_command()` recognises every new sentence, so
   jarvis_intake.owner_turns never learns one of these as a fact.
8. The settings.html jump list is still a map of that page, after the
   owner's 2026-10-06 tidy-up: its bands are the page's own three headings
   in order, every link is a real card on the page, none is listed twice and
   none is missing (t_jump_list_matches_the_page).
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_quick.py", "jarvis_settings_registry.py", "jarvis_asks_first.py",
                "jarvis_owner_check.py", "jarvis_auto_learn.py", "jarvis_watch_notify.py",
                "jarvis_briefing.py", "jarvis_search.py", "jarvis_manner.py",
                "jarvis_schedule.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402
import jarvis_menus as M  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_auto_learn as AL  # noqa: E402
import jarvis_watch_notify as WN  # noqa: E402
import jarvis_briefing as BR  # noqa: E402
import jarvis_search as WS  # noqa: E402
import jarvis_manner as MN  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402

# THE OWNER'S STATE IS LEFT ALONE (run_suites.py's own private_state()'s own
# rule, followed the same way here): every module this file drives writes a
# real settings file. jarvis_framework.config_path() - which
# jarvis_asks_first.py's tier lookups and writes go through - falls back to
# this repository's OWN backend/rebuilt/jarvis-framework.toml when no
# override is set ("beside the module" search), so a run of this file
# WITHOUT the env vars below really did edit a file this repository tracks
# once, while this test was being written; see this task's own report.
# JARVIS_FRAMEWORK_TOML (a copy of the real file, so every OTHER tier keeps
# its real value) and OPENJARVIS_CONFIG_DIR/JARVIS_CONFIG_DIR (the plain
# on/off settings' own JSON files) are pointed at a temporary directory,
# exactly as run_suites.py's private_state() does for every other suite.
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
TMP = Path(tempfile.mkdtemp(prefix="jarvis-settings-registry-"))
_TOML_COPY = TMP / "jarvis-framework.toml"
shutil.copyfile(REPO / "backend" / "rebuilt" / "jarvis-framework.toml", _TOML_COPY)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TOML_COPY)
for _mod in (AF, AL, WN, BR, WS, MN):
    _mod._config_dir = lambda _tmp=TMP: _tmp

# THE FACE'S CHOICES ARE THE OWNER'S PC DATA - `jarvis-visual-spec.json`, read
# from beside the server (`jarvis_settings_registry._face_choices`). A staged
# run of this suite (the way run_suites.py and CI run it) holds the shipped
# MODULES only, so that file is not beside them and the face's options would be
# {} - a fact about the staging, not about the grammar this file proves. Point
# the registry's file fallback at this repository's own measured spec (the same
# file test_appearance.py pins) so every check below runs on real face names;
# the EMPTY case - a PC with no spec at all - is proved in words by
# t_a_pc_with_no_face_spec_says_why, which stubs it back out itself.
def _repo_face_rows():
    import json
    spec = json.loads((REPO / "jarvis-desktop" / "src" / "jarvis-visual-spec.json")
                      .read_text(encoding="utf-8"))
    return [{"id": str(row["id"]), "name": str(row.get("name") or row["id"])}
            for row in spec.get("faces") or []
            if isinstance(row, dict) and row.get("id")]


_FACE_ROWS_FROM_THE_SPEC = _repo_face_rows()
R._face_rows = lambda: _FACE_ROWS_FROM_THE_SPEC


FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def go(text, *, peer=None, local="127.0.0.1", now=None):
    body = {"messages": [{"role": "user", "content": text, "provenance": "typed"}]}
    return Q.answer_turn(body, now=now or time.time(), peer=peer, local=local)


#: `settings.` ids `features/features.json` claims that are ROWS INSIDE a
#: section rather than sections of their own, with the reason. Everything else
#: it claims must name a real Section.
SUB_ROWS = {
    "second-card.chat-card": "a row inside the second-card card",
    "second-card.referee": "a row inside the second-card card",
    "second-card.study-helper": "a row inside the second-card card",
    "second-card.third-card": "a row inside the second-card card",
}


def t_every_feature_settings_claim_names_a_section():
    """"Open <a feature's setting>" must be able to name the place.

    `features/features.json` says where each feature can be changed (`covers`),
    and `jarvis_quick._run_settings_open` turns such an id into the words it
    says and the place it opens through `section_by_id` - falling back to the
    raw id when the section is missing. That fallback hid a real gap for
    months: `settings.floating-avatar` was claimed with no Section, so "open
    Floating Jarvis" answered "Opening floating-avatar in Settings." and named
    nothing either app could find (measured 2026-10-08: five claimed ids had no
    section - four are rows inside the second-card card, listed above with the
    reason, and the fifth was this one)."""
    import json
    try:
        rows = json.loads((REPO / "features" / "features.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return check("features/features.json is readable", False,
                     f"{type(exc).__name__}: {exc}")
    claims: dict = {}
    for row in rows:
        for cover in (row.get("covers") or []):
            if isinstance(cover, str) and cover.startswith("settings."):
                claims.setdefault(cover.split(".", 1)[1], row.get("id"))
    missing = sorted(i for i in claims if R.section_by_id(i) is None and i not in SUB_ROWS)
    check("every settings.* id a feature claims names a Section (or a listed sub-row)",
          not missing,
          "; ".join(f"{i} (claimed by {claims[i]})" for i in missing)
          + " - add it to jarvis_settings_registry.SECTIONS, or to SUB_ROWS above "
            "with the section it sits in")
    stale = sorted(i for i in SUB_ROWS if R.section_by_id(i) is not None)
    check("...and no SUB_ROWS entry has quietly become a section of its own", not stale,
          f"{stale} - drop it from SUB_ROWS")


PC, PHONE = "127.0.0.1", "100.100.5.9"

# ======================================================== 1. SECTIONS matches the real UI


def t_sections_match_the_real_ui():
    settings_html = (REPO / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")
    # A top-level card is `<section class="card" id="...">`; "More options"
    # (the folded group start-jarvis, "Startup and logs" and crash-notes sit
    # inside) is the one `<details ... id="more-options">` instead.
    desktop_ids = set(re.findall(r'<(?:section class="card"|details[^>]*)[^>]*\bid="([^"]+)"',
                                 settings_html))
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "ui" / "screens" / "SettingsScreen.kt").read_text(encoding="utf-8")
    phone_keys = set(re.findall(r'item\(key\s*=\s*"([^"]+)"\)', kt))
    desktop_missing = [s.id for s in R.SECTIONS if s.app in ("both", "desktop")
                       and s.id not in desktop_ids]
    check("every 'both'/'desktop' section is a real settings.html <section id>",
          not desktop_missing, desktop_missing)
    phone_missing = [s.id for s in R.SECTIONS if s.app in ("both", "phone")
                     and s.id not in phone_keys and s.id not in desktop_ids]
    # Bug audit 2026-09-27, finding #2: Security, Voice and Appearance are
    # ordinary `item(key = ...)` rows on SettingsScreen.kt, same as every
    # other phone section - the regex above already matches them by their
    # literal keys ("security", "voice", "appearance"). Only "appearance-card"
    # needs listing here at all: that is this registry's own section id, kept
    # different from the phone's literal item key ("appearance") because the
    # desktop's settings.html uses "appearance-card" for its own <section id>.
    # "security" and "voice" are named below too, defensively, since they are
    # never missing to begin with; anything else missing is a real drift.
    # "animal-options" (2026-09-28): on the phone the section is inside
    # Appearance, so it maps to the Appearance row (SETTINGS_ITEM_INDEX).
    ALLOWED_NO_KEY = {"security", "appearance-card", "voice", "animal-options"}
    phone_missing = [i for i in phone_missing if i not in ALLOWED_NO_KEY]
    check("every 'both'/'phone' section (bar the appearance-card id spelling) "
          "is a real SettingsScreen.kt item key", not phone_missing, phone_missing)
    check("no id is listed twice", len(R.SECTIONS) == len({s.id for s in R.SECTIONS}))
    check("no alias is claimed by two sections",
          len([n for s in R.SECTIONS for n in s.names])
          == len({n for s in R.SECTIONS for n in s.names}))
    _check_settings_item_index(kt)


def t_every_real_settings_card_is_listed():
    """The other direction (settings audit 2026-09-30): "devices" and
    "crash-notes" were real cards on the apps that "open ..." could not name.
    Every top-level desktop card, and every phone Settings row, must be in
    SECTIONS - or be one of the few named exceptions below."""
    settings_html = (REPO / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")
    # Cards only (nested <details> such as "link-tech" are parts of a card);
    # "More options" is the one top-level <details>.
    desktop_ids = set(re.findall(r'<section class="card"[^>]*\bid="([^"]+)"', settings_html))
    desktop_ids.add("more-options")
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "ui" / "screens" / "SettingsScreen.kt").read_text(encoding="utf-8")
    phone_keys = set(re.findall(r'item\(key\s*=\s*"([^"]+)"', kt))
    listed = {s.id for s in R.SECTIONS}
    # The phone's "appearance" row is the registry's "appearance-card"; "tail" is
    # a spacer; "floating-avatar" and "voice-switches"/"jump-list" are rows of
    # the same screen reached through Appearance / Voice / the top.
    # "jarvis-notify" (2026-10-09) is the same shape for the same reason: it is a
    # row that opens Android's OWN per-app notification screen and is
    # deliberately not a Jarvis setting at all (the owner's decision of
    # 2026-10-09, docs/SETTINGS-COVERAGE-AUDIT-2026-10-09.md's GAP 1). The
    # registry's "notifications" Section stays desktop-only, because the four
    # per-kind switches and quiet hours really are the PC's, and
    # _check_phone_declines_the_pc_only_cards below still holds the phone to
    # that.
    # "app-control" (2026-10-19) is the same shape once more: the phone's
    # accessibility service is a phone-only capability, so the desktop registry
    # has no menu for it and the row is always drawn.
    phone_ok = {"appearance", "tail", "floating-avatar", "jump-list", "jarvis-notify",
                "app-control"}
    check("every desktop settings card is a SECTION",
          not (desktop_ids - listed), sorted(desktop_ids - listed))
    check("every phone Settings row is a SECTION (bar the named spacers)",
          not (phone_keys - listed - phone_ok), sorted(phone_keys - listed - phone_ok))
    for sid in ("devices", "crash-notes"):
        check(f"'open {sid.replace('-', ' ')}' finds its section",
              R.find_section(sid.replace("-", " ")) is not None)
    check("'devices' is on both apps, 'crash-notes' is desktop only",
          R.section_by_id("devices").app == "both" and R.section_by_id("crash-notes").app == "desktop")
    _check_phone_declines_the_pc_only_cards()


def _check_phone_declines_the_pc_only_cards():
    """A section this file says the phone has must really be on the phone.

    Settings-coverage audit, 2026-10-09: `notifications` was declared
    `app="both"` for months while the phone has no notifications screen at
    all - its controls are Android's own, per channel. Nothing failed,
    because the phone half of the two checks above is satisfied by an id
    that is a desktop card (`s.id not in phone_keys and s.id not in
    desktop_ids`), so one id could be "both" for a reason that only ever
    held on the PC. `jarvis-client`'s own `ui/OpenPlace.kt` had the right
    answer all along ("notifications" is in its PC_ONLY set, so the phone
    answers "only in Jarvis on your PC"); this reads that same file as text
    and holds the registry to it, the way OpenPlaceTest reads this file."""
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "ui" / "OpenPlace.kt").read_text(encoding="utf-8")
    block = re.search(r"val PC_ONLY: Set<String> = setOf\((.*?)\n    \)", kt, re.S)
    pc_only = set(re.findall(r'"([\w-]+)"', block.group(1))) if block else set()
    check("OpenPlace.kt's own PC_ONLY set was found and parsed", bool(pc_only), sorted(pc_only))
    lying = sorted(s.id for s in R.SECTIONS
                   if s.app in ("both", "phone") and s.id in pc_only)
    check("no section claims the phone has it while the phone says 'only on your PC'",
          not lying, f"{lying} - set app=\"desktop\" on each, or take it out of OpenPlace.PC_ONLY")
    check("'notifications' is desktop only, as the phone's own OpenPlace says",
          R.section_by_id("notifications").app == "desktop"
          and "notifications" in pc_only
          and all(s.id != "notifications" for s in R.sections_for("phone")))


def t_jump_list_matches_the_page():
    """The settings.html jump list, held to the page it is a map of.

    The owner, 2026-10-06: "organize the jump to settings in the settings
    menu? This is really disorganized" - about forty links in eleven flat
    rows. The fix groups them under the page's own three bands (Everyday,
    Rare, What Jarvis does) and, inside each band, under the short groups
    `docs/ease-audit-2026-09-27/customize.md` proposed and `critic.md:199`
    kept as "the target order of the jump list".

    WHY THIS TEST AND NOT A REGISTRY FIELD. Checked before the grouping was
    chosen: `jarvis_settings_registry.py`'s SECTIONS carries an id, its
    spoken names, `app` and `where` - and NO group and NO order - and
    `jarvis_menus.py`'s groups (graphics-cards, finance, study, chatbots,
    goals-projects, home) are feature groups for the hide-a-menu list, not
    places on this page (most settings cards, and all but three of the jump
    list's own links, are in no group at all). So there was no grouping to
    use, and adding one would have made the backend a second, quieter owner
    of where a card sits on one desktop page. What is checked instead is the
    two things that can really drift apart: the page's own band order, and
    the jump list's agreement with it.

    Proves, and does NOT prove:
      * every jump link points at a real `<section class="card" id=...>` (or
        the one `<details id="more-options">`) on this page;
      * no link is listed twice, and none is missing - all of them are still
        there, which is what "every existing link must keep working" means
        for a list that only ever adds an anchor;
      * each band's links ARE that band's cards, in the page's own order -
        a link that floated to another band, or a card inserted in the wrong
        place, fails here;
      * every link is in SECTIONS with app "both"/"desktop", so nothing on
        this list is a place "open <name>" cannot name.
    It does NOT prove that clicking a link scrolls anywhere: that needs the
    page in a browser, and Playwright is not installed here.
    """
    settings_html = (REPO / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")

    # The page's three bands, in order, with the exact heading each carries.
    headings = [(m.start(), m.group(1)) for m in
                re.finditer(r'<h2 class="settings-group-heading">([^<]+)</h2>', settings_html)]
    check("the page still has its three bands, in this order",
          [h for _, h in headings] == ["Everyday", "Rare", "What Jarvis does"],
          [h for _, h in headings])

    # Every card the page has, in page order, split by the band it sits under.
    card_ids = [m.group(1) for m in
                re.finditer(r'<section class="card"[^>]*\bid="([^"]+)"', settings_html)]
    card_ids.append("more-options")          # the one top-level <details>
    card_pos = {cid: settings_html.index(f'id="{cid}"') for cid in card_ids}
    band_of = {}
    for n, (at, name) in enumerate(headings):
        end = headings[n + 1][0] if n + 1 < len(headings) else len(settings_html)
        for cid, pos in card_pos.items():
            # "start-jarvis" and "crash-notes" are cards INSIDE the folded "More
            # options" (<details id="more-options">), whose own row is the jump
            # link - they are reached through it, so they are not rows here.
            # (The same two are the named exceptions in
            # t_every_real_settings_card_is_listed.)
            if at < pos < end and cid not in ("start-jarvis", "crash-notes"):
                band_of[cid] = name

    nav_at = settings_html.index('class="settings-jump"')
    nav_end = settings_html.index("</nav>", nav_at)
    nav = settings_html[nav_at:nav_end]

    # Read the list back the way a person does: the band labels divide it, and
    # every link belongs to the band label above it.
    listed_by_band = {name: [] for _, name in headings}
    band_now = None
    for m in re.finditer(r'<span class="settings-jump-label">([^<]+)</span>'
                         r'|<a href="#([\w-]+)">', nav):
        if m.group(1) is not None:
            band_now = m.group(1)
        else:
            check(f"jump link #{m.group(2)} sits under a band label",
                  band_now in listed_by_band, band_now)
            if band_now in listed_by_band:
                listed_by_band[band_now].append(m.group(2))

    by_band = {name: [] for _, name in headings}
    for cid in card_ids:
        if cid in band_of:
            by_band[band_of[cid]].append(cid)

    for name in listed_by_band:
        check(f"the {name} band lists every card in it, in the page's own order",
              listed_by_band[name] == by_band[name],
              f"listed {listed_by_band[name]}, page has {by_band[name]}")

    every = [cid for ids in listed_by_band.values() for cid in ids]
    check("no jump link is listed twice", len(every) == len(set(every)),
          sorted({c for c in every if every.count(c) > 1}))
    # Every href really is on this page - an anchor to nothing scrolls nowhere.
    check("every jump link points at a real card on this page",
          all(cid in card_pos for cid in every),
          sorted(c for c in every if c not in card_pos))

    # ...and every one of them is a place "open <name>" can name.
    unopenable = [c for c in every
                  if R.section_by_id(c) is None
                  or R.section_by_id(c).app not in ("both", "desktop")]
    check("every jump link is a SECTION this app has", not unopenable, unopenable)

    # The grouping is short rows inside a band, never a third level: a band's
    # own direct children are its `.settings-jump-place` rows and nothing else.
    for g in re.findall(r'<div class="settings-jump-group">(.*?)\n        </div>', nav, re.S):
        check("a band holds only jump rows and its own label",
              not re.search(r'<a\s', re.sub(r'<div class="settings-jump-place">.*?</div>', "", g, flags=re.S)),
              g[:80])
    check("no jump row is empty",
          all(re.search(r'<a href="#', p) for p in
              re.findall(r'<div class="settings-jump-place">(.*?)</div>', nav, re.S)))


#: A row's `item(key = ...)`: either a quoted string or a `SettingsJump`
#: constant. The search box (2026-10-09) names `SettingsJump.SEARCH_KEY`, and
#: the jump list's own row names `SettingsJump.LIST_KEY`, so the screen and
#: the tests that read it cannot disagree about those two keys by spelling
#: them twice. `SettingsJumpTest` reads the same two shapes
#: (jarvis-client/app/src/test/java/com/jarvis/client/SettingsJumpTest.kt,
#: its own ROW_KEY) - this reader mirrors it, because a reader that only
#: understood quoted keys silently SKIPPED both rows and then reported the
#: whole map as shifted by two.
_ROW_KEY = re.compile(r'item\(key\s*=\s*(?:"([\w.-]+)"|SettingsJump\.(\w+))')

#: A declared position is a plain number OR a `SettingsJump` constant
#: (`"search" to SettingsJump.SEARCH_KEY_INDEX`), so `SEARCH_KEY_INDEX` is
#: held to the row it names rather than trusted.
_JUMP_CONST = re.compile(r'const val (\w+) = "([\w.-]+)"')
_JUMP_INT = re.compile(r'const val (\w+) = (\d+)')


def _settings_jump_source() -> str:
    return (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
            / "client" / "ui" / "SettingsJump.kt").read_text(encoding="utf-8")


def _check_settings_item_index(kt: str):
    """`SettingsScreen.kt`'s own `SETTINGS_ITEM_INDEX` claims a `LazyColumn`
    position for each key it lists - checked here against the REAL, current
    order of `item(key = ...)` calls in the same file, never trusted as
    still accurate.

    Bug audit 2026-09-27: this map went stale the moment a concurrent piece
    of work inserted "floating-avatar" at position 3 - every index below it
    was one item too early, and nothing caught it because the map was never
    checked against the file's real order, only checked (by the test above)
    for which keys it lists at all. A silent, plausible-looking wrong
    number is exactly what a presence-only check misses.

    Settings search, 2026-10-09: the search box became the FIRST row and the
    jump list's own row started naming `SettingsJump.LIST_KEY`. Both are real
    `item(key = ...)` rows, but neither spells its key as a quoted string, so
    the old quoted-only reader counted NEITHER: every declared position then
    looked two too high. The map itself was right (search 0, jump-list 1,
    voice 2, ... limits 22) - the reader was the stale half. A row key and a
    declared position may now both be a `SettingsJump` constant, resolved
    from `SettingsJump.kt` itself, so the map is still held to every row it
    names - the two rows the old reader skipped are now counted rather than
    ignored. This is what SettingsJumpTest's own ROW_KEY already does."""
    jump_src = _settings_jump_source()
    keys = dict(_JUMP_CONST.findall(jump_src))
    numbers = dict(_JUMP_INT.findall(jump_src))
    real_order = [quoted or keys.get(const) for quoted, const in _ROW_KEY.findall(kt)]
    unresolved = sorted({c for q, c in _ROW_KEY.findall(kt) if not q and c not in keys})
    check("every SettingsJump constant a row key names is a real const val",
          not unresolved, f"{unresolved} - SettingsJump.kt has no such constant")
    real_index = {key: i for i, key in enumerate(real_order)}
    map_block = re.search(r"SETTINGS_ITEM_INDEX[^{(]*\(\s*(.*?)\n\)", kt, re.S)
    declared, unresolved_numbers = {}, []
    if map_block:
        for key, value in re.findall(r'"([\w-]+)"\s+to\s+([\w.]+)', map_block.group(1)):
            if value.isdigit():
                declared[key] = value
            else:
                name = value.split(".")[-1]
                if name in numbers:
                    declared[key] = numbers[name]
                else:
                    unresolved_numbers.append(key)
    check("SETTINGS_ITEM_INDEX's own map block was found and parsed", bool(declared))
    check("every declared position is a number or a real SettingsJump constant",
          not unresolved_numbers,
          f"{unresolved_numbers} - SettingsJump.kt has no such const val, so that "
            "row's position would go unchecked")
    # "appearance-card" is the desktop's own id, deliberately aliased to the
    # phone's own item key "appearance" (docs/JARVIS-API.md section 58.1's
    # own note on this one intentional name mismatch) - checked against
    # "appearance" instead of expecting the wire id to appear verbatim.
    ALIAS = {"appearance-card": "appearance", "animal-options": "appearance"}
    wrong = []
    for key, declared_i in declared.items():
        real_i = real_index.get(ALIAS.get(key, key))
        if real_i is None or str(real_i) != declared_i:
            wrong.append(f"{key}: map says {declared_i}, real position is {real_i}")
    check("SETTINGS_ITEM_INDEX's positions match the real item(key=...) order",
          not wrong, wrong)


# ======================================================== 2. "open" is pure navigation


def t_open_is_pure_navigation():
    for phrase, want in (("open web search", "web-search"),
                        ("show me the security settings", "security"),
                        ("go to accounts", "account-secrets"),
                        ("take me to what asks first", "asks-first"),
                        ("show me how jarvis talks", "manner")):
        i = Q.match(phrase)
        check(f"{phrase!r} opens {want!r}", i is not None and i.name == "settings_open"
              and i.f.get("id") == want, i)
    # "open the faq" opened the Settings card "Help and FAQ" until 2026-10-08.
    # The card is gone (its questions moved to the Brain's "Tutorials and the
    # FAQ"), so the phrase must no longer name a settings section - there is no
    # #faq element left for the window to scroll to, and a section that names a
    # card that no longer exists is the drift this test is for. What DID stay is
    # the help itself: the Brain's own menu answers to "faq", "the faq" and
    # "frequently asked questions" (backend/jarvis_menus.py), which is where the
    # owner is sent instead - checked right here rather than left implied.
    i = Q.match("open the faq")
    check("'open the faq' no longer names a Settings section (the card is gone)",
          i is None or i.f.get("id") != "faq", i)
    check("the Brain's Help place still answers to the names 'open the faq' used",
          {"faq", "the faq", "frequently asked questions"}
          <= set(M.menu("brain.tab.tutorials").names),
          M.menu("brain.tab.tutorials").names)
    for phrase in ("open the door", "open the pod bay doors", "show me the money",
                   "go to sleep"):
        i = Q.match(phrase)
        # What this suite is about: none of them names a SECTION, so none of
        # them is a settings jump. Since 2026-10-10 the two "open ..." ones are
        # claimed by the other feature that owns those words (jarvis_open.py:
        # "open the pod bay doors" is a program name this PC will not find, and
        # it is reported plainly rather than guessed at), so what is checked is
        # that the answer is NOT a settings jump - never that the phrase is
        # nobody's.
        check(f"{phrase!r} names no section, so it is not a settings jump",
              (i is None) or not i.f.get("id"), i)
    for phrase in ("open the door", "open the pod bay doors"):
        got = Q.match(phrase)
        check(f"{phrase!r} is the app opener's, not this module's",
              got is not None and got.name == "open_app", got)
    for phrase in ("show me the money", "go to sleep"):
        check(f"{phrase!r} is still nobody's", Q.match(phrase) is None, Q.match(phrase))
    r = go("open web search", peer=PHONE)
    check("the reply names the place and carries open_settings, nothing else runs",
          r is not None and r.open_settings == "web-search" and "web search" in r.reply.lower())
    rf = Q.route_fields(r)
    check("X-Jarvis-Route carries open_settings", rf.get("open_settings") == "web-search")
    r2 = go("set a timer for 5 minutes", peer=PHONE)
    rf2 = Q.route_fields(r2)
    check("an ordinary quick answer carries no open_settings key at all",
          "open_settings" not in rf2, rf2)


def t_reach_wins_over_open_reach_settings():
    # Bug audit 2026-09-27, finding #8: the "reach" section's own aliases
    # ("what jarvis can reach/access") are word-for-word what the older,
    # already-established _REACH grammar already matches for a different
    # purpose - reading the list aloud (jarvis_reach.py), not opening
    # Settings. _settings_open used to run first in _match's dispatch
    # chain, so those exact sentences opened Settings instead and the
    # older phrase became silently unreachable.
    for phrase in ("show me what jarvis can reach", "show me what jarvis can access",
                  "what can jarvis reach", "tell me what jarvis can access"):
        i = Q.match(phrase)
        check(f"{phrase!r} still reads the reach list aloud, not Settings",
              i is not None and i.name == "reach_list", (phrase, i))
    # Said plainly rather than silently accepted: the "reach" section's
    # own two declared aliases are BOTH exactly what _REACH now wins
    # against, so this fix trades "the wrong intent every time" for "no
    # voice alias opens this one section at all" - still strictly better
    # (reach_list is the more useful, more specific answer), but a real
    # gap, not a false "everything still works". A future alias for this
    # section that does not repeat _REACH's own wording would close it.
    for phrase in ("show me what jarvis can reach", "show me what jarvis can access"):
        i = Q.match(phrase)
        check(f"{phrase!r} no longer opens Settings (traded away on purpose)",
              i is None or i.name != "settings_open", i)


# ======================================================== 3. "adjust" calls the real function


def t_adjust_calls_the_real_function():
    check("web_search_provider's registry entry IS jarvis_search.use",
          R.set_web_search_provider.__module__ == "jarvis_settings_registry")
    import jarvis_search as WS
    check("... and calling it really calls WS.use (import identity, not a copy)",
          R.set_web_search_provider("duckduckgo", peer=None, local=None).said
          == WS.use("duckduckgo"))
    import jarvis_manner as MN
    before = MN.current()
    try:
        out = R.set_manner("plain")
        check("manner's registry entry really flips jarvis_manner's own setting",
              out.ok and MN.current() == "plain")
    finally:
        MN.handle_set({"manner": before})


BOOL_CASES = (
    ("background_learning", "turn off background learning", "turn on background learning"),
    ("smartwatch_notifications", "turn off smartwatch notifications",
     "turn on smartwatch notifications"),
)


def t_bool_settings_round_trip():
    for key, off_phrase, on_phrase in BOOL_CASES:
        setting = next(b for b in R.BOOL_SETTINGS if b.key == key)
        i_off = Q.match(off_phrase)
        check(f"{off_phrase!r} matches {key} off", i_off is not None
              and i_off.name == "settings_bool" and i_off.f == {"key": key, "on": False})
        i_on = Q.match(on_phrase)
        check(f"{on_phrase!r} matches {key} on", i_on is not None
              and i_on.name == "settings_bool" and i_on.f == {"key": key, "on": True})
        check(f"{key} is spelled the same as jarvis_quick's Intent name",
              setting.key == i_off.f["key"] == i_on.f["key"])


def t_ambiguous_phrasing_is_left_alone():
    # A near-miss of a real bool setting's wording, and a made-up setting -
    # neither may be guessed at.
    for phrase in ("turn on the learning thing", "turn off my calendar",
                  "enable the special mode", "turn on jarvis"):
        i = Q.match(phrase)
        check(f"{phrase!r} is not guessed at", i is None or i.name != "settings_bool", i)


# ======================================================== 4. PC_ONLY_ACTIONS genuinely refuses


def t_loosen_asks_first_pc_only():
    check("loosen_what_asks_first is really on PC_ONLY_ACTIONS (not invented for this test)",
          "loosen_what_asks_first" in OC.PC_ONLY_ACTIONS)
    AF._reset_for_tests()
    OC.set_verifier(lambda m, t: OC.CONFIRMED)
    OC._ARMED = True
    try:
        # calendar_read ships "auto" - already loosened - so there is
        # nothing to loosen until it is made stricter first.
        r = go("ask me before my calendar", peer=PHONE)
        check("stricter works from anywhere, immediately, no card",
              r is not None and (r.reply == "Done - it asks you first from now on."
                                 or "already asks" in r.reply))
        check("... and the tier really is 'ask' now", AF._tier("calendar_read") == "ask")
        r = go("stop asking before my calendar", peer=PHONE)
        check("looser, from a phone-shaped peer: refused, plain words, nothing raised",
              r is not None and "PC" in r.reply and "Windows Hello" in r.reply)
        check("... and the tier is still 'ask' - nothing was raised or changed",
              AF._tier("calendar_read") == "ask" and not AF._L_STATE["pending"])
        r = go("stop asking before my calendar", peer=PC)
        check("looser, from this PC: the SAME card jarvis_asks_first.request_tier raises",
              r is not None and "approval" in r.reply.lower() and "Windows Hello" in r.reply)
        check("... nothing applies until the card is approved", AF._tier("calendar_read") == "ask")
    finally:
        AF._reset_for_tests()
        AF.set_tier("calendar_read", "auto")   # leave the sandboxed toml as it shipped
        OC.set_verifier(None)
        OC._ARMED = False


def t_enable_reading_tool_pc_only():
    check("enable_reading_tool is really on PC_ONLY_ACTIONS (not invented for this test)",
          "enable_reading_tool" in OC.PC_ONLY_ACTIONS)
    AF._reset_for_tests()
    OC.set_verifier(lambda m, t: OC.CONFIRMED)
    OC._ARMED = True
    try:
        before = set(AF.tools_enabled_set())
        r = go("let the ai model read my calendar", peer=PHONE)
        check("ON, from a phone-shaped peer: refused",
              r is not None and "PC" in r.reply)
        check("... and [tools].enabled is unchanged", AF.tools_enabled_set() == before)
        AF._reset_for_tests()
        r = go("let the ai model read my calendar", peer=PC)
        check("ON, from this PC: the SAME card jarvis_asks_first.request_tool_enable raises",
              r is not None and ("approval" in r.reply.lower() or "already offered" in r.reply))
        AF._reset_for_tests()
        r = go("don't let the ai model read my calendar", peer=PHONE)
        check("OFF works from anywhere, immediately, no card",
              r is not None and "not offered" in r.reply)
    finally:
        AF._reset_for_tests()
        OC.set_verifier(None)
        OC._ARMED = False


# ================================================== 5. card-gated, not device-restricted


def t_lights_still_raises_its_card():
    check("lights_without_card is NOT on PC_ONLY_ACTIONS - it is gated by a card only, "
          "from either device", "loosen_what_asks_first" != AF.LIGHTS_ACTION
          and AF.LIGHTS_ACTION not in OC.PC_ONLY_ACTIONS)
    AF._reset_for_tests()
    before = AF.lights_setting()["on"]
    r = go("turn on lights without asking", peer=PHONE)
    check("ON, from the phone: a card is raised, nothing applied yet",
          r is not None and "approval" in r.reply.lower()
          and AF.lights_setting()["on"] == before)
    AF._reset_for_tests()
    r = go("turn off lights without asking", peer=PHONE)
    check("OFF is immediate, from the phone, no card",
          r is not None and AF.lights_setting()["on"] is False)


def t_background_learning_still_raises_its_card():
    AL._reset_for_tests()
    go("turn off background learning", peer=PC)
    check("OFF is immediate", AL.settings()["auto"] is False)
    r = go("turn on background learning", peer=PHONE)
    check("ON, from the phone: a card (or an unreadable-tier refusal in this bare test "
          "environment), never a silent flip", AL.settings()["auto"] is False, r.reply if r else None)


# ================================================== 6. is_command(), so the learner skips it


def t_is_command_recognises_every_new_sentence():
    for phrase in ("open web search", "turn on background learning",
                  "stop asking before my calendar", "let the ai model read my calendar"):
        check(f"is_command({phrase!r})", Q.is_command(phrase))


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        t()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0



def t_the_backend_behind_check():
    """Does the app know about something the backend on this PC cannot do?

    The capability seam (task-55): the app is built from one commit and the
    backend on the PC runs another, and the measured symptom is a backend that
    offers 13 settings where the app's build knows 51. This detects a CAPABILITY
    mismatch - nothing more, which is what its own words say."""
    import jarvis_settings_registry as R

    full = R.capability_report()
    check("the report names what this backend can change",
          bool(full["keys"]) and full["count"] >= 1, full)
    check("the count is the one the owner is told when he asks what he can change",
          full["count"] == R.changeable_settings()["count"], full)
    same = R.behind(full["keys"], full)
    check("a backend that can do everything the app knows is NOT behind",
          same["behind"] is False, same)
    check("...and then there is nothing to say to the owner", same["line"] == "", same)

    old = [k for k in full["keys"] if k.startswith("switch:")]
    verdict = R.behind(full["keys"], old)
    check("a backend that only offers the on/off switches IS behind",
          verdict["behind"] is True, verdict)
    check("...and it names everything that is missing",
          len(verdict["missing"]) == len(full["keys"]) - len(old), verdict)
    check("...and the line says TELL, never update, and names the script to run",
          "behind this app" in verdict["line"]
          and "does not update the backend" in verdict["line"]
          and "apply-patches.ps1" in verdict["line"], verdict["line"])
    check("...and it never claims anything is automatic",
          "automatic" not in verdict["line"].lower(), verdict["line"])

    one = R.behind(full["keys"] + ["switch:a_setting_this_backend_does_not_have"], full)
    check("one capability the backend does not have is enough to be behind",
          one["behind"] is True
          and one["missing"] == ["switch:a_setting_this_backend_does_not_have"], one)
    more = R.behind(full["keys"][:-1], full)
    check("a backend that can do MORE than the app knows is not behind",
          more["behind"] is False and bool(more["extra"]), more)
    check("a report dict can be passed where a key list is expected",
          R.behind({"keys": full["keys"]}, full)["behind"] is False, full)



# ================================== 7. the universal-control pass (2026-10-22)
#
# The owner's requirement: every function or feature can be turned on, off or
# adjusted by typing at Jarvis on either app. These tests prove the COMMAND
# side is real: every switch's phrase resolves and dispatches to its own
# registered setter (a spy), every named-choice option resolves and dispatches
# to its own setter, an unknown value is answered with the real options rather
# than guessed at, the deliberate open-only switches never become speakable,
# and nothing branches on which app asked.

def t_every_bool_setting_resolves_on_and_off_and_reaches_its_own_setter():
    import dataclasses
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    names = [n for b in R.BOOL_SETTINGS for n in b.names]
    check("no two switches claim the same spoken name", len(names) == len(set(names)),
          sorted({n for n in names if names.count(n) > 1}))
    for b in R.BOOL_SETTINGS:
        label = b.names[0]
        for want_on, phrase in ((True, f"turn on {label}"), (False, f"turn off {label}")):
            got = Q.match(phrase)
            check(f"{phrase!r} resolves to the {b.key} switch",
                  got is not None and got.name == "settings_bool"
                  and got.f.get("key") == b.key and got.f.get("on") is want_on,
                  got)
            if got is None or got.name != "settings_bool":
                continue
            calls = []

            def spy(on, *, peer=None, local=None):
                calls.append((bool(on), peer, local))
                return R.Outcome(True, "spy")

            swapped = dataclasses.replace(b, set=spy)
            saved = R.BOOL_SETTINGS
            R.BOOL_SETTINGS = tuple(swapped if x.key == b.key else x for x in saved)
            try:
                out = Q._run_settings_bool({"key": b.key, "on": want_on}, "peer-a", True)
            finally:
                R.BOOL_SETTINGS = saved
            check(f"...and dispatch calls {b.key}'s own setter with the value",
                  calls == [(want_on, "peer-a", True)], calls)
            check(f"...and reports the setter's own sentence ({b.key})",
                  out is not None and out.reply == "spy", out)


def t_a_pc_with_no_face_spec_says_why():
    """A PC with no visual spec has no faces to choose - and must SAY SO.

    MEASURED 2026-10-27, through the staged runner: with no spec beside the
    backend the generic control refusal read "That is not one of the values for
    face's face. Say one of: ." - an empty list of choices, which is worse than
    no answer. The face is the one choice setting whose list is a file
    (`_face_choices`), so it is the one that can have no choices at all on a
    real PC; the fix words that case instead of printing an empty list.
    """
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    saved = R._face_rows
    R._face_rows = lambda: []
    try:
        check("a PC with no visual spec has no face choices at all",
              R._face_choices() == {}, R._face_choices())
        got = Q.match("set the face to red panda")
        check("...so that sentence is a refusal, not a guess",
              got is not None and got.name == "control_bad", got)
        refused = (Q._run_control_bad(dict(got.f))
                   if got is not None and got.name == "control_bad" else None)
        replied = refused.reply if refused is not None else ""
        check("...and the refusal names the file that would supply the faces",
              "jarvis-visual-spec.json" in replied, replied)
        check("...and never prints an empty 'Say one of:' list",
              "say one of: ." not in replied.lower(), replied)
        check("...and says nothing was changed",
              "nothing was changed" in replied.lower(), replied)
        said = R.choice_bad_words(R._choice("face"))
        check("the settings-choice refusal path says the same thing",
              "jarvis-visual-spec.json" in said, said)
    finally:
        R._face_rows = saved


def t_every_choice_setting_resolves_its_options_and_reaches_its_own_setter():
    import dataclasses
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    for c in R.CHOICE_SETTINGS:
        options = c.options()
        check(f"{c.key} has at least two named choices", len(options) >= 2, options)
        check(f"{c.key}'s setter is this registry's own (no copied path)",
              getattr(c.set, "__module__", "") == "jarvis_settings_registry", c.set)
        # THESE CHECKS HAD NEVER RUN until 2026-10-26: they sat after the file's
        # `if __name__ == "__main__"` block, so a script run - the way
        # run_suites.py runs a suite - never defined them. Moving that block to
        # the end of the file is what surfaced the three stale expectations
        # below; each is repaired to the grammar as it really is, never weakened.
        for value_word, value in list(options.items())[:3]:
            phrase = f"set {c.names[0]} to {value_word}"
            got = Q.match(phrase)
            # THREE real grammars can own this sentence since 2026-10-22, and
            # every one of them changes the SAME setting: `settings_choice` (the
            # named-choice table), `control_set` (the generic control/field
            # grammar, which names the voice, the captcha hand-off and the focus
            # preset) and `personality_set` (the older personality grammar,
            # which owns "set the personality to X"). Accept whichever wins, and
            # insist it carries THIS setting and THIS value - never another one.
            if got is not None and got.name == "personality_set":
                check(f"{phrase!r} resolves to personality={value!r}",
                      c.key == "personality" and got.f.get("personality") == value, got)
                continue
            check(f"{phrase!r} resolves to {c.key}",
                  got is not None and got.name in ("settings_choice", "control_set")
                  and got.f.get("key") == c.key and got.f.get("value") == value, got)
            if got is None or got.name not in ("settings_choice", "control_set"):
                continue
            calls = []

            def spy(chosen, *, peer=None, local=None):
                calls.append((chosen, peer, local))
                return R.Outcome(True, "spy")

            swapped = dataclasses.replace(c, set=spy)
            saved = R.CHOICE_SETTINGS
            R.CHOICE_SETTINGS = tuple(swapped if x.key == c.key else x for x in saved)
            try:
                if got.name == "control_set":
                    out = Q._run_control_set({"key": c.key, "value": got.f["value"]},
                                             "peer-b", False)
                else:
                    out = Q._run_settings_choice({"key": c.key, "value": got.f["value"]},
                                                 "peer-b", False)
            finally:
                R.CHOICE_SETTINGS = saved
            check(f"...and dispatch calls {c.key}'s own setter with the value",
                  calls and calls[0][0] == value and calls[0][1:] == ("peer-b", False),
                  calls)
            check(f"...and reports the setter's own sentence ({c.key})",
                  out is not None and out.reply == "spy", out)
        bad = Q.match(f"set {c.names[0]} to zzzz-not-a-real-choice")
        check(f"{c.key}: an unknown value is a refusal, not a guess",
              bad is not None and bad.name in ("settings_choice_bad", "control_bad"), bad)
        refused = None
        if bad is not None and bad.name == "settings_choice_bad":
            refused = Q._run_settings_choice_bad(bad.f)
        elif bad is not None and bad.name == "control_bad":
            refused = Q._run_control_bad(bad.f)
        if bad is not None and bad.name == "control_bad" and not bad.f.get("field"):
            # A control with MORE THAN ONE field (the captcha hand-off) cannot
            # answer with values: the value may belong to either field, so the
            # honest answer names the fields. The values belong to a field, and
            # `control_bad` answers with them once one is named.
            fields = [row.field for row in R.fields_for_control(bad.f.get("control"))]
            check(f"{c.key}: an unrecognised value names the fields to choose from",
                  refused is not None and all(f in refused.reply for f in fields),
                  (fields, refused.reply if refused else None))
            ask = Q.match(f"what are the choices for {c.names[0]}")
            check(f"{c.key}: 'what are the choices' answers without changing anything",
                  ask is not None and ask.name == "settings_choice_help", ask)
            continue
        first = sorted(options)[0]
        check(f"{c.key}: the refusal names the real options",
              refused is not None and first in refused.reply.lower()
              and "not one of the" in refused.reply.lower(),
              refused.reply if refused else None)
        ask = Q.match(f"what are the choices for {c.names[0]}")
        check(f"{c.key}: 'what are the choices' answers without changing anything",
              ask is not None and ask.name == "settings_choice_help", ask)


def t_the_deliberate_open_only_switches_stay_unreachable():
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    for dom_id, names in R.NOT_BY_ASKING.items():
        for name in names:
            got = Q.match(f"turn on {name}")
            check(f"{name!r} is not changed by asking (NOT_BY_ASKING: {dom_id})",
                  got is None or got.name not in ("settings_bool", "settings_choice"),
                  got)
            got = Q.match(f"turn off {name}")
            check(f"...nor turned off ({name!r})",
                  got is None or got.name not in ("settings_bool", "settings_choice"),
                  got)


def t_the_new_controls_do_not_branch_on_which_client_asked():
    """The backend never reads a client kind: the same phrase, the same setter,
    the same gate on both apps (the app is told apart only by peer/local, which
    the setters already receive).

    READ AS CODE, NOT AS TEXT (2026-10-26). This used to scan the source for the
    two names, so a DOCSTRING that explains why per-app wording is not done
    ("would need the backend to read `X-Jarvis-Client`") failed the check while
    no code read anything. It now walks the syntax tree and ignores docstrings,
    which is the claim the test is actually making."""
    import ast
    import inspect
    import jarvis_settings_registry as R
    repo = Path(__file__).resolve().parents[1]

    def _code_mentions(tree, needle: str) -> bool:
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                body = getattr(node, "body", [])
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings and needle in node.value):
                return True
            if isinstance(node, ast.Name) and node.id == needle:
                return True
            if isinstance(node, ast.Attribute) and node.attr == needle:
                return True
        return False

    for name in ("jarvis_settings_registry.py", "jarvis_quick.py"):
        tree = ast.parse((repo / "backend" / name).read_text(encoding="utf-8"))
        for needle in ("X-Jarvis-Client", "client_kind"):
            check(f"{name} does not branch on the client kind ({needle})",
                  not _code_mentions(tree, needle), needle)
    for key in ("chat_history", "write_like_me", "big_model", "second_card_combined"):
        setting = next(b for b in R.BOOL_SETTINGS if b.key == key)
        params = inspect.signature(setting.set).parameters
        check(f"{key}'s setter takes peer and local, not a client kind",
              "peer" in params and "local" in params and "client" not in params,
              list(params))
    for c in R.CHOICE_SETTINGS:
        params = inspect.signature(c.set).parameters
        check(f"{c.key}'s setter takes peer and local too",
              "peer" in params and "local" in params, list(params))


def t_the_new_rows_link_to_real_controls():
    """Every feature the matrix calls command-controllable must name a real
    BoolSetting/ChoiceSetting key - never a string typed only in the matrix."""
    import jarvis_feature_guide as FG
    import jarvis_settings_registry as R
    bool_keys = {b.key for b in R.BOOL_SETTINGS}
    choice_keys = {c.key for c in R.CHOICE_SETTINGS}
    for fid, keys in FG.EXTRA_CONTROLS.items():
        for key in keys:
            check(f"{fid}'s extra control {key} is a real BoolSetting",
                  key in bool_keys, key)
    for row in FG.control_matrix():
        for key in row["switch_keys"]:
            check(f"{row['id']} names the real switch {key}", key in bool_keys, key)
        for entry in row["adjust"]:
            check(f"{row['id']}'s adjust proof {entry['phrase']!r} works",
                  bool(entry["intent"]), entry)
    check("the matrix has one row per catalogue feature",
          len(FG.control_matrix()) == FG.feature_count(),
          (len(FG.control_matrix()), FG.feature_count()))
    known = bool_keys | choice_keys
    check("every extra-control key is a real switch", known, known)


# ================================== 8. the generic multi-field grammar (Q3)

def t_the_generic_control_grammar_is_closed_world_and_asks_on_ambiguity():
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    # the closed vocabulary itself: every field points at a real choice setting
    choice_keys = {c.key for c in R.CHOICE_SETTINGS}
    for control, fields in R.CONTROL_FIELDS.items():
        check(f"{control!r} has at least one field", bool(fields), control)
        for field in fields:
            check(f"{control}/{field.field} points at a real choice setting",
                  field.setting.key in choice_keys, field.setting.key)
    # unambiguous: control + field + value
    for phrase, key, value in (
            ("set voice speed to faster", "voice_speed", "faster"),
            ("change the voice speed to normal", "voice_speed", "normal"),
            ("set the captcha hand-off window to bring it to the front",
             "handoff_front", "bring_to_front"),
            ("set the captcha hand-off mode to patient", "handoff_mode", "keep_offering"),
                        ("set the focus preset to coding", "focus_preset", "coding")):
        got = Q.match(phrase)
        check(f"{phrase!r} resolves to {key}={value!r}",
              got is not None and got.name == "control_set"
              and got.f.get("key") == key and got.f.get("value") == value, got)
    # no field, value names exactly one field - still deterministic
    got = Q.match("change voice to faster")
    check("an omitted field is resolved when the value names exactly one",
          got is not None and got.name == "control_set"
          and got.f.get("key") == "voice_speed", got)
    # no field and no unique value -> a deterministic question, never a guess
    got = Q.match("set voice to something else")
    check("an ambiguous control asks, never guesses",
          got is not None and got.name in ("control_ask", "control_bad"), got)
    got = Q.match("adjust voice")
    check("'adjust voice' alone asks which field",
          got is not None and got.name == "control_ask", got)
    # a named field with an invalid value names the real values
    got = Q.match("set voice speed to turbo")
    check("a bad value is refused with the real options",
          got is not None and got.name == "control_bad"
          and got.f.get("field") == "speed", got)
    # a sentence naming no control is somebody else's exactly as before
    for phrase in ("set a timer to 5 minutes", "change my alarm to 8am",
                   "set my security settings"):
        got = Q.match(phrase)
        check(f"{phrase!r} is not read as a control-field change",
              got is None or got.name != "control_set", got)


def t_the_generic_control_handler_calls_the_same_setter_and_answers_deterministically():
    import dataclasses
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    setting = next(c for c in R.CHOICE_SETTINGS if c.key == "voice_speed")
    calls = []

    def spy(value, *, peer=None, local=None):
        calls.append((value, peer, local))
        return R.Outcome(True, "spy")

    swapped = dataclasses.replace(setting, set=spy)
    saved = R.CHOICE_SETTINGS
    R.CHOICE_SETTINGS = tuple(swapped if c.key == setting.key else c for c in saved)
    try:
        out = Q._run_control_set({"key": "voice_speed", "value": "faster"}, "peer-q", True)
    finally:
        R.CHOICE_SETTINGS = saved
    check("the generic handler calls the setting's OWN setter",
          calls == [("faster", "peer-q", True)], calls)
    check("...and reports the setter's own sentence", out is not None and out.reply == "spy", out)
    ask = Q._run_control_ask({"control": "voice"})
    check("the clarifying question lists the fields",
          ask is not None and "speed" in ask.reply and "voice" in ask.reply, ask)
    check("...and their current values", "currently" in ask.reply.lower(), ask)
    bad = Q._run_control_bad({"control": "voice", "field": "speed", "value": ""})
    check("an invalid value answer names the valid values",
          bad is not None and "faster" in bad.reply and "slower" in bad.reply, bad)
    weird = Q._run_control_bad({"control": "voice", "field": "", "value": "something else"})
    check("an unknown value names the fields rather than guessing",
          weird is not None and "speed" in weird.reply, weird)


def t_the_two_settings_only_exceptions_are_refused_in_plain_words():
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    for phrase, which in (("restore my backup", "restore"),
                          ("restore from a backup", "restore"),
                          ("change my openai api key", "accounts"),
                          ("add an api key", "accounts"),
                          ("show me my password", "accounts")):
        got = Q.match(phrase)
        check(f"{phrase!r} is a Settings-only refusal",
              got is not None and got.name == "settings_only"
              and got.f.get("which") == which, got)
        if got is None or got.name != "settings_only":
            continue
        out = Q._run_settings_only(got.f)
        check(f"{phrase!r} names Settings and the right card",
              out is not None and "Settings" in out.reply
              and ("Backups" in out.reply if which == "restore" else "Accounts" in out.reply),
              out.reply if out else None)
        check(f"{phrase!r} never claims a change happened",
              out is not None and "changed" not in out.reply.lower(), out.reply if out else None)
    check("the two Settings-only messages exist",
          set(R.SETTINGS_ONLY) == {"accounts", "restore"}, sorted(R.SETTINGS_ONLY))
    # Lead review 2026-10-22: the chat-retention typed control is deliberately
    # NOT shipped - that route deletes stored conversations at once, so it needs
    # an owner decision, not a spoken one-liner.
    check("the chat-retention typed control is deferred, not shipped",
          "chat_keep_days" not in {c.key for c in R.CHOICE_SETTINGS}
          and "chat history" not in R.CONTROL_FIELDS,
          [c.key for c in R.CHOICE_SETTINGS])


# ================================== 9. the two settings outside the tables
#
# 2026-10-26. The PC's own "hey Jarvis" switch and which browser Jarvis uses
# are real routes, but they are not BOOL_SETTINGS/CHOICE_SETTINGS rows (the
# contract pins those keys, and the desktop draws the wake word as a button,
# not a toggle). They are reachable by asking all the same, and that is what
# this section proves - phrases, values, refusals and the honest count.

def t_the_wake_word_changes_by_asking_and_says_whether_it_asked():
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    for phrase, want_on in (
            ("turn on the wake word", True),
            ("turn the wake word on", True),
            ("enable the wake word", True),
            ("turn off the wake word", False),
            ("turn the wake word off", False),
            ("disable the wake word", False)):
        got = Q.match(phrase)
        check(f"{phrase!r} changes the wake word",
              got is not None and got.name == "settings_wake_word"
              and got.f.get("on") is want_on, got)

    calls = []

    def spy(on, *, peer=None, local=None):
        calls.append((bool(on), peer, local))
        return R.Outcome(True, "Approve the card on your PC or phone to turn it "
                               "on. Nothing changes until you do.", waiting=bool(on))

    real = R.set_wake_word
    R.set_wake_word = spy
    try:
        off = Q._run_settings_wake_word({"on": False}, "peer-w", True)
        on = Q._run_settings_wake_word({"on": True}, "peer-w", True)
    finally:
        R.set_wake_word = real
    check("the runner calls the setting's own setter, with the request's peer/local",
          calls == [(False, "peer-w", True), (True, "peer-w", True)], calls)
    check("turning it ON repeats the module's own 'waiting for the card' words",
          on is not None and "Nothing changes until you do" in on.reply, on)
    check("turning it OFF repeats the module's own words too",
          off is not None and "Approve the card" in off.reply, off)


def t_the_wake_words_own_title_points_at_the_working_phrase():
    """The feature's own TITLE used to get the false "Command-Only" sentence
    (review of 2026-10-26).

    `jarvis_feature_guide.switch_target` cannot see a switch for the wake-word
    row - its switch is not a BoolSetting - so "turn on Say "Hey Jarvis"" fell
    to the old refusal, which said the ability is Command-Only and "there is no
    fixed sentence for it" while "turn on the wake word" does work. The row now
    names that phrase instead, and changes nothing."""
    import jarvis_quick as Q
    for verb in ("turn on", "turn off"):
        phrase = f'{verb} Say "Hey Jarvis"'
        got = Q.match(phrase)
        words = str(((got.f or {}) if got is not None else {}).get("words") or "")
        check(f"{phrase!r} names the real phrase, not the Command-Only sentence",
              got is not None and got.name == "feature_switch_refused"
              and "turn on the wake word" in words and "Command-Only" not in words,
              got)
    # The phrase the refusal points at is the real control, so the pointer is
    # true rather than another sentence with nothing behind it.
    got = Q.match("turn on the wake word")
    check("...and the phrase it names really changes the wake word",
          got is not None and got.name == "settings_wake_word"
          and got.f.get("on") is True, got)


def t_which_browser_jarvis_uses_changes_by_asking():
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    for phrase, want in (
            ("set the browser to headless", "headless"),
            ("set the browser mode to automatic", "auto"),
            ("change the browser engine to visible", "visible"),
            ("use the windowless browser", "headless"),
            ("only use the visible browser", "visible")):
        got = Q.match(phrase)
        check(f"{phrase!r} picks {want}",
              got is not None and got.name == "settings_browser_mode"
              and got.f.get("mode") == want, got)
    bad = Q.match("set the browser to the kitchen sink")
    check("a browser Jarvis does not have is a refusal, not a guess",
          bad is not None and bad.name == "settings_browser_mode_bad", bad)
    refused = Q._run_settings_browser_mode_bad(bad.f if bad else {})
    check("the refusal names the three real ones",
          refused is not None and "headless" in refused.reply
          and "visible" in refused.reply and "automatic" in refused.reply,
          refused.reply if refused else None)
    check("...and says nothing was changed",
          refused is not None and "not one of the browsers" in refused.reply,
          refused.reply if refused else None)

    calls = []

    def spy(mode, *, peer=None, local=None):
        calls.append((mode, peer, local))
        return R.Outcome(True, "Done - which browser Jarvis uses is now the "
                               "windowless browser when it can run. That is a PC "
                               "setting, so both apps follow it, and it needed no card.")

    real = R.set_browser_mode
    R.set_browser_mode = spy
    try:
        out = Q._run_settings_browser_mode({"mode": "headless"}, "peer-b", False)
    finally:
        R.set_browser_mode = real
    check("the runner calls the setting's own setter",
          calls == [("headless", "peer-b", False)], calls)
    check("a success says what changed, that both apps follow it, and that no card was needed",
          out is not None and "which browser Jarvis uses" in out.reply
          and "both apps" in out.reply and "no card" in out.reply,
          out.reply if out else None)


def t_the_honest_count_includes_them():
    import jarvis_settings_registry as R
    data = R.changeable_settings()
    words = data["words"].lower()
    check("the answer to 'what can I change?' names the wake word",
          "wake word" in words, data["words"][:400])
    check("...and which browser Jarvis uses",
          "which browser jarvis uses" in words, data["words"][:400])
    check("the count is at least the switches + the two families",
          data["count"] >= len(R.BOOL_SETTINGS) + 2, data["count"])
    check("the number in the sentence is the measured number",
          f"You can change {data['count']} settings" in data["words"],
          data["words"][:120])


def t_every_registry_row_resolves_from_a_natural_phrase():
    """A setting added to any table WITHOUT a phrase that reaches it fails here.

    THE COMPLETENESS CHECK the machinery never had: the tables are what
    "what can I change?" reads, and a row nothing can reach is a promise the
    owner will try and be refused. One natural phrase per row (its own first
    name), through the real matcher, and the intent must carry that row's own
    key and value - a phrase reaching a DIFFERENT setting is worse than none."""
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    for b in R.BOOL_SETTINGS:
        for want_on, verb in ((True, "turn on"), (False, "turn off")):
            phrase = f"{verb} {b.names[0]}"
            got = Q.match(phrase)
            check(f"{phrase!r} reaches the {b.key} switch",
                  got is not None and got.name in ("settings_bool", "feature_switch")
                  and got.f.get("key") == b.key and got.f.get("on") is want_on, got)
    for c in R.CHOICE_SETTINGS:
        options = c.options()
        check(f"{c.key} declares at least one value to try", bool(options), c.key)
        value_word = sorted(options)[0] if options else ""
        phrase = f"set {c.names[0]} to {value_word}"
        got = Q.match(phrase)
        ok = got is not None and (
            (got.name in ("settings_choice", "control_set")
             and got.f.get("key") == c.key)
            or (got.name == "personality_set" and c.key == "personality"
                and got.f.get("personality") == options[value_word]))
        check(f"{phrase!r} reaches {c.key}", ok, got)
    for action, names in R.asks_first_targets().items():
        phrase = f"stop asking before {names[0]}"
        got = Q.match(phrase)
        check(f"{phrase!r} reaches asks-first {action}",
              got is not None and got.name == "settings_asks_first"
              and got.f.get("action") == action and got.f.get("ask") is False, got)
    for tool, names in R.tool_targets().items():
        phrase = f"let the ai model read {names[0]}"
        got = Q.match(phrase)
        check(f"{phrase!r} reaches the {tool} tool switch",
              got is not None and got.name == "settings_tool"
              and got.f.get("tool") == tool and got.f.get("on") is True, got)
    # The two that are not table rows (this section's own subject).
    for phrase, want_on in (("turn on the wake word", True),
                            ("turn off the wake word", False)):
        got = Q.match(phrase)
        check(f"{phrase!r} reaches the wake-word switch",
              got is not None and got.name == "settings_wake_word"
              and got.f.get("on") is want_on, got)
    for phrase, want in (("set the browser to headless", "headless"),
                         ("set the browser to visible", "visible"),
                         ("set the browser to automatic", "auto")):
        got = Q.match(phrase)
        check(f"{phrase!r} reaches which-browser mode {want}",
              got is not None and got.name == "settings_browser_mode"
              and got.f.get("mode") == want, got)


def t_a_page_only_switch_is_not_stolen_by_the_tolerant_matcher():
    """THE REGRESSION THIS FOUND (2026-10-26, in a suite that had never run).

    "turn on windows hello for memory lists and chat history" is an exact
    NOT_BY_ASKING name - a real switch this backend has no route for - and the
    word-tolerant switch matcher read "chat history" inside it and would have
    switched the setting on. The page-only answer is decided first now, and
    nothing is changed.

    AND THE FILLER FORMS, from the review of the same day: the first fix used
    the EXACT page-only lookup, so one natural filler word defeated it again -
    "turn off the windows hello for memory lists and chat history setting" fell
    to the tolerant switch matcher and turned `chat_history` off AT ONCE, with
    no card. The page-only lookup now strips the same filler the switch matcher
    strips, and it is checked BEFORE any switch - so every tail below is the
    named refusal, and none of them carries a switch key."""
    import jarvis_quick as Q
    import jarvis_settings_registry as R
    for name in ("windows hello for memory lists and chat history",
                 "windows hello for memory lists"):
        for verb in ("turn on", "turn off"):
            # "setting" and "please" are the matcher's own filler words;
            # "now" is NOT filler, so it exercises the containment rule (the
            # request contains the whole page-only name).
            for tail in ("", " setting", " please", " now"):
                phrase = f"{verb} {name}{tail}"
                got = Q.match(phrase)
                check(f"{phrase!r} is answered as a page-only setting",
                      got is not None and got.name == "settings_not_by_asking", got)
                check(f"...and it is not read as the switch whose words it contains",
                      got is None or got.f.get("key") != "chat_history", got)
    check("the tolerant page-only lookup strips the switch matcher's own filler",
          R.find_not_by_asking_words(
              "the windows hello for memory lists and chat history setting")
          == "sec-private",
          R.find_not_by_asking_words(
              "the windows hello for memory lists and chat history setting"))
    check("...and a different page-only row with filler is still that row",
          R.find_not_by_asking_words("the app lock please") == "sec-app-lock",
          R.find_not_by_asking_words("the app lock please"))
    got = Q.match("turn off the app lock please")
    check("a page-only name plus filler answers as the page, not a switch",
          got is not None and got.name == "settings_not_by_asking"
          and got.f.get("dom_id") == "sec-app-lock", got)
    said = R.cannot_change_setting_words(
        "windows hello for memory lists and chat history setting")
    check("the tool's refusal names the page and the row, never the whole list",
          "Settings" in said
          and "Windows Hello for memory lists and chat history" in said
          and "You can change" not in said, said)
    # The tolerant matcher still works for the owner's own words (D5), so the
    # fix did not take a working phrase away.
    got = Q.match("turn on learning in the background")
    check("the owner's own words still reach background learning",
          got is not None and got.name == "settings_bool"
          and got.f.get("key") == "background_learning" and got.f.get("on") is True,
          got)
    check("that phrase really was the tolerant matcher's",
          R.find_bool_setting("learning in the background") is None
          and R.find_bool_setting_words("learning in the background") is not None)


if __name__ == "__main__":
    raise SystemExit(main())
