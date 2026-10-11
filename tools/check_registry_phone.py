#!/usr/bin/env python3
"""The other direction: is anything still on the phone that the registries
call desktop-only?

    python3 tools/check_registry_phone.py

WHY THIS EXISTS (the parity audit of 2026-10-10,
`.dsh-scratch/android-verify/PARITY-AUDIT-2026-10-10.md`)

`backend/jarvis_menus.py` and `backend/jarvis_settings_registry.py` are the two
files that say which app has what. Both were read by hand for that audit, and
both under-reported the PHONE: eight menu entries said "desktop only" while the
phone really drew the feature (`settings.animal-options`,
`settings.briefing-settings`, `settings.voices`, `settings.updates`,
`settings.about`, `brain.history.tags`, `brain.work.undo`,
`brain.work.activity`), and `features.json` had six of its desktop rows wrong.

The cost is not cosmetic. "desktop-only" in these files is read by people and
by tools as "the phone does not have this", so the audit had to open phone code
in eight places to avoid reporting eight false gaps - and a real gap can hide
behind a wrong row just as easily.

WHAT WAS ALREADY CHECKED, AND WHAT WAS NOT

Two checks existed, and both point the same way:

  * the phone's `MenuVisibilityTest` (and the desktop's `menu-visibility.mjs`)
    fail when a menu the registry says BOTH apps have has no place in the
    phone's screens - a menu MISSING from the phone;
  * `tools/check_feature_list.py` fails when a menu id nobody listed is added,
    and when a `covers` id that no longer exists is left behind.

Neither can see the reverse: a feature the registry calls ABSENT that the phone
actually has. That is the direction this tool checks.

HOW IT CHECKS IT - declarations, held to the code

For every menu id the registry marks DESKTOP-ONLY, one of two things must be
true, and both are recorded in this file so a reader can see the evidence
rather than a verdict:

  1. the phone HAS the feature, and the registry is wrong - then the id must
     not be desktop-only at all, and the row here says which phone file draws
     it (`PHONE_HAS`). This is the audit's finding, written down as a claim the
     tool re-checks on every run: the named file must still be there and must
     still contain the named thing.
  2. the phone does NOT have the feature, and the absence is a DECISION - then
     the id is in `PHONE_LACKS` with the reason, and the id must really be
     desktop-only.

The tool also holds the two registries to each other: every `app="desktop"`
section in `jarvis_settings_registry.py` must have a desktop-only menu in
`jarvis_menus.py` (or be a row inside one), and the phone's own
`OpenPlace.PC_ONLY` list - which is what actually answers "only on your PC"
when the owner says "open notifications" - must name it. Two files that
disagree about the same section are exactly the drift the audit's section 6.3
found nine times.

WHAT IT DELIBERATELY DOES NOT DO

It does not try to guess, by itself, whether a phone screen "is" a feature: a
share of the desktop-only rows are about a layout (the desktop's Brain rail
tabs), and a text search for a word like "shortcuts" or "updates" in the phone
tree finds launcher shortcuts and update checks that are different things.
Guessing there would make this check noisy, and a noisy check is ignored. What
it does instead is cheap, exact and one-directional:

  * no phone source file may READ a menu id the registry calls desktop-only -
    `menus.shows("<id>")` or `item(key = "<id>")` for such an id is a
    contradiction, in the phone's own words, and it fails here;
  * every declaration in `PHONE_HAS`/`PHONE_LACKS` must still point at code
    that is really there, so the table cannot rot into a comment;
  * the counts are asserted, so a parse that quietly found nothing fails
    loudly instead of passing.

A comment is NOT a contradiction: `OpenPlace.kt` and `MenuPlaces.kt` name
desktop-only ids in their comments on purpose (that is how the phone explains
itself). Comments are stripped before the scan, the same way
`tools/check_parity.py` strips them.

CHEAP ENOUGH FOR CI: one file read per declaration, one pass over the phone's
`.kt` files, no network, no model, no Android build. Run through
`backend/test_registry_phone.py`, which CI picks up like every other suite.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
PHONE_MAIN = ROOT / "jarvis-client" / "app" / "src" / "main" / "java"
OPEN_PLACE = PHONE_MAIN / "com" / "jarvis" / "client" / "ui" / "OpenPlace.kt"
SETTINGS_SCREEN = (PHONE_MAIN / "com" / "jarvis" / "client" / "ui" / "screens"
                   / "SettingsScreen.kt")

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: Every desktop-only menu id, and WHY the phone does not have it, with the
#: phone file that shows the absence is real. Each entry is checked: the file
#: must exist and must contain `must contain`, so a stale reason fails here
#: rather than being repeated for years.
#:
#: `name` is what the owner calls it; `why` is the one-line decision; `where`
#: is the phone file (relative to the repository root) and `must_contain` is
#: the exact line that proves the phone made a decision about it (almost
#: always the phone's own `OpenPlace.PC_ONLY` entry, which is what answers
#: "only on your PC" at run time).
PHONE_LACKS = {
    "settings.shortcuts": {
        "name": "Shortcuts",
        "why": "Keyboard shortcuts are a PC's; the phone has no keys (ARCHITECTURE section 8).",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"shortcuts",',
    },
    "settings.account-secrets": {
        "name": "Accounts",
        "why": "The phone is never asked for an account secret (rule 3).",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"account-secrets",',
    },
    "settings.chatbot-api-keys": {
        "name": "Chatbot API keys",
        "why": "Keys go straight into Windows Credential Manager from the PC's own Rust.",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"chatbot-api-keys",',
    },
    "settings.tool-updates": {
        "name": "Check for tool updates",
        "why": "Outdated packages and tools are developer/maintenance work on the PC.",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"tool-updates",',
    },
    "settings.more-options": {
        "name": "More options",
        "why": "Startup, logs and crash notes are about the PC's own process.",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"more-options",',
    },
    "settings.notifications": {
        "name": "Notifications",
        "why": ("The phone's notification controls are Android's own, per channel; the phone's "
                "\"Notifications from Jarvis\" row opens Android's screen instead."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"notifications",',
    },
    "settings.hud-window": {
        "name": "The big HUD window",
        "why": "The big \"Jarvis\" window is the PC's; a phone has no such window.",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"hud-window",',
    },
    "settings.first-run": {
        "name": "Set up Jarvis",
        "why": ("The first-run card is the page a new owner meets on the PC; the phone's first "
                "screen IS pairing instead (ARCHITECTURE section 8)."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"first-run",',
    },
    "settings.start-jarvis": {
        "name": "Starting Jarvis for you",
        "why": ("The backend runs on the PC, next to the desktop app; a phone cannot start or "
                "stop it (ARCHITECTURE section 8)."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"start-jarvis",',
    },
    "settings.crash-notes": {
        "name": "Hang and crash notes",
        "why": ("The PC process's own notes. The phone keeps its own crash screen "
                "(CrashScreen.kt, platform/CrashLog.kt)."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": '"crash-notes",',
    },
    "brain.tab.memory": {
        "name": "Memory (rail tab)",
        "why": ("A layout difference, not a missing feature: the phone draws the Memory "
                "contents as plates with no rail. Kept desktop-only on purpose, and the "
                "contents themselves are ids of their own (see PHONE_HAS)."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"memory-counts" to "brain.memory.learning",',
    },
    "brain.tab.history": {
        "name": "History (rail tab)",
        "why": "A layout difference: the phone reaches History from the Brain's own entry row.",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"history" to "entry.history",',
    },
    "brain.tab.faculties": {
        "name": "Model (rail tab)",
        "why": "A layout difference: the phone draws the model plates under \"Model and PC\".",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"models" to "brain.model.models",',
    },
    "brain.tab.work": {
        "name": "Work (rail tab)",
        "why": "A layout difference: the phone draws the Work plates directly on the Brain.",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"today" to "brain.work.today",',
    },
    "brain.tab.tutorials": {
        "name": "Tutorials and the FAQ (rail tab)",
        "why": ("A layout difference: the phone draws the same catalogue as its own "
                "`brain.model.tutorials` plate."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"tutorials" to "brain.model.tutorials",',
    },
    "brain.tab.galaxy": {
        "name": "Galaxy (rail tab)",
        "why": "The memory graph stays off the phone (CLAUDE.md; ARCHITECTURE section 8).",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": "val PC_ONLY: Set<String> = setOf(",
    },
    "brain.tab.now": {
        "name": "Now (rail tab)",
        "why": "A layout difference: the phone draws \"Right now\" and the budget on the Brain.",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"doing" to "brain.now.right-now",',
    },
    "brain.tab.trust": {
        "name": "Trust (rail tab)",
        "why": ("A layout difference: the phone draws the audit chain and the rush banner, "
                "with no Trust rail to hold them (both are ids of their own)."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"ledger" to "brain.trust.ledger",',
    },
    "brain.tab.watch": {
        "name": "Watch (rail tab)",
        "why": "A layout difference: the phone draws the watchlist itself, with no Watch rail.",
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"watch" to "brain.watch.watchlist",',
    },
    "brain.memory.history-import": {
        "name": "Bring in old chats",
        "why": ("The export is a file on the PC and is usually hundreds of megabytes; "
                "uploading it from a phone would be a new way out (ARCHITECTURE section 8)."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt",
        "must_contain": "val PC_ONLY: Set<String> = setOf(",
    },
    "brain.memory.known": {
        "name": "What Jarvis knows about you",
        "why": ("The list of every fact, forgotten ones included, is deep memory editing, "
                "which stays on the desktop (ARCHITECTURE section 8). The phone's own "
                "\"Saved automatically\" list is `brain.memory.auto`."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"memory-auto" to "brain.memory.auto",',
    },
    "brain.history.conversations": {
        "name": "Chat history and conversations",
        "why": ("The phone HAS the conversations themselves (HistoryScreen.kt, under the "
                "Brain's History entry) - what this id is, is the desktop's own History "
                "card, which holds the list AND how long chats are kept. The keeping is "
                "the PC's (`net/ChatLog.kt` reads it), and the phone has no such card."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"history" to "entry.history",',
    },
    "brain.model.memory": {
        "name": "Memory (model view)",
        "why": ("The memory summary on the desktop's Model page. The phone draws the same "
                "summary once, under its Memory group (`brain.memory.learning`), and has "
                "no second Model-page copy."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt",
        "must_contain": '"memory-counts" to "brain.memory.learning",',
    },
    "brain.trust.content-risk": {
        "name": "Content risk",
        "why": ("The phone reads `/api/content-risk` but draws only the rush banner, never "
                "the list of flagged outside text - the audit's GAP 7. Recorded here as a "
                "real absence rather than left to look like parity."),
        "where": "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
        "must_contain": "contentRisk",
    },
}

#: The menu ids the audit found on the phone while the registry called them
#: desktop-only. Each is checked in the tool itself (they must NOT be
#: desktop-only any more) and each names the phone file that draws it, so the
#: correction this file is built on stays true.
PHONE_HAS = {
    "settings.animal-options": ("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
                                "AnimalOptionsPlate.kt", "fun AnimalOptionsSection("),
    "settings.briefing-settings": ("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
                                   "BriefingPlate.kt",
                                   'menus.shows("settings.briefing-settings")'),
    "settings.voices": ("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
                        "VoicesScreen.kt", "fun VoicesScreen("),
    "settings.updates": ("jarvis-client/app/src/main/java/com/jarvis/client/net/UpdateCheck.kt",
                         "object UpdateCheck"),
    "settings.about": ("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FaqScreen.kt",
                       "private fun AboutCard()"),
    "brain.history.tags": ("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
                           "HistoryTags.kt", "fun TagsEditor("),
    "brain.work.undo": ("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
                        "InboxScreen.kt", '"UNDO SHELF"'),
    "brain.work.activity": ("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
                            "ApprovalsScreen.kt", "fun ApprovalsScreen("),
}

#: The settings-registry sections that really are the desktop's. Each must be
#: a desktop-only menu above (or a row inside one), so the two registries
#: cannot disagree about the same section - the audit's section 6.3.
#: Ids here that are NOT menus (`crash-notes`, `start-jarvis`, `first-run`) are
#: rows inside "More options" or the first-run card, which is why the tool
#: accepts either a desktop-only menu or a mention in `settings.html`.
SETTINGS_DESKTOP_ONLY = (
    "first-run", "shortcuts", "account-secrets", "chatbot-api-keys", "tool-updates",
    "more-options", "start-jarvis", "crash-notes", "hud-window", "notifications",
)

#: Below this many ids the parse has broken and the check would pass by
#: finding nothing. The registry has 113 menus today; the floors are set well
#: under that so ordinary growth never trips them.
MIN_MENUS = 100
MIN_DESKTOP_ONLY = 15
MIN_PHONE_FILES = 100


def _comment_free(text: str, suffix: str) -> str:
    """A file with its comments taken out.

    A desktop-only id named in a KDoc block is how the phone explains itself
    (OpenPlace.kt does it deliberately); only real code counts.
    """
    if suffix == ".kt":
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"(?m)//.*$", "", text)
        return text
    if suffix in (".js", ".mjs"):
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"(?m)//.*$", "", text)
        return text
    return text


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def desktop_only_ids() -> list:
    """Every menu id `jarvis_menus.py` marks desktop-only, in file order."""
    import jarvis_menus as M  # noqa: E402  (deliberate: only this function needs it)

    ids = [m.id for m in M.MENUS if m.apps == (M.DESKTOP,)]
    if len(M.MENUS) < MIN_MENUS:
        raise AssertionError(f"read only {len(M.MENUS)} menus from jarvis_menus.py - the parse broke")
    if len(ids) < MIN_DESKTOP_ONLY:
        raise AssertionError(f"read only {len(ids)} desktop-only menus - the parse broke")
    return ids


def phone_files() -> list:
    """Every Kotlin file of the phone app, main sources only."""
    got = sorted(p for p in PHONE_MAIN.rglob("*.kt") if p.is_file())
    if len(got) < MIN_PHONE_FILES:
        raise AssertionError(f"read only {len(got)} phone .kt files under {PHONE_MAIN} - the scan broke")
    return got


def phone_menu_reads() -> dict:
    """menu id -> "file:line", for every id the phone's CODE reads.

    The two ways a Kotlin screen reads a menu id, and nowhere else: the
    `menus.shows("<id>")` / `menus.folded("<id>")` guards and the
    `item(key = "<id>")` list keys. Comments are stripped first, so a KDoc
    mention is not a read. Keyed by the first place it is read.
    """
    found: dict = {}
    for path in phone_files():
        text = _comment_free(read(path), ".kt")
        rel = path.relative_to(ROOT).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            for m in re.finditer(r'(?:shows|folded)\(\s*"([\w.-]+)"\s*\)|item\(key\s*=\s*"([\w.-]+)"', line):
                mid = m.group(1) or m.group(2)
                found.setdefault(mid, f"{rel}:{i}")
    if len(found) < 40:
        raise AssertionError(f"read only {len(found)} menu ids out of the phone's code - the scan broke")
    return found


def open_place_pc_only() -> set:
    """The ids the phone itself answers "only on your PC" for."""
    text = read(OPEN_PLACE)
    at = text.index("val PC_ONLY: Set<String> = setOf(")
    block = text[at:text.index("\n    )", at)]
    return set(re.findall(r'"([\w.-]+)"', block))


def settings_desktop_sections() -> list:
    """Every `app="desktop"` section of jarvis_settings_registry.py."""
    import jarvis_settings_registry as R  # noqa: E402

    return [s.id for s in R.SECTIONS if s.app == "desktop"]


def desktop_settings_card_ids() -> set:
    """Every top-level Settings card id in the desktop's own settings.html."""
    html = read(ROOT / "jarvis-desktop" / "src" / "settings.html")
    ids = set(re.findall(r'<section class="card"[^>]*\bid="([^"]+)"', html))
    ids.update(re.findall(r'<details[^>]*\bid="([^"]+)"', html))
    if len(ids) < 20:
        raise AssertionError(f"read only {len(ids)} Settings cards from settings.html - the parse broke")
    return ids


def problems() -> list:
    """Everything wrong, one `(group, line)` per finding, so the report can
    print the findings under the heading they belong to."""
    bad = []
    names = desktop_only_ids()

    # 1. The declarations and the registry are one story, both directions.
    for mid in names:
        if mid not in PHONE_LACKS:
            bad.append(("absences", f"{mid} is desktop-only but has no PHONE_LACKS entry - say why "
                                    "the phone does not have it, or move it to PHONE_HAS if it does"))
    for mid in PHONE_LACKS:
        if mid not in names:
            bad.append(("absences", f"PHONE_LACKS lists {mid}, which is not a desktop-only menu any "
                                    "more - if the phone has it now, delete the entry (PHONE_HAS is "
                                    "for the ids that were corrected)"))

    # 2. Every "the phone has it" claim is still true in the phone's own code.
    for mid, (rel, needle) in PHONE_HAS.items():
        path = ROOT / rel
        if not path.is_file():
            bad.append(("corrections", f"PHONE_HAS[{mid}] points at {rel}, which is not there"))
            continue
        if needle not in read(path):
            bad.append(("corrections", f"PHONE_HAS[{mid}] says {rel} holds `{needle}`, and it does "
                                       "not - the phone's side of this feature moved or went"))
        if mid in names:
            bad.append(("corrections", f"{mid} is on the phone ({rel}) and is still marked "
                                       "desktop-only in jarvis_menus.py - the registries "
                                       "under-report the phone again"))

    # 3. Every "the phone has not got it" reason still points at real code.
    for mid, entry in PHONE_LACKS.items():
        path = ROOT / entry["where"]
        if not path.is_file():
            bad.append(("absences", f"PHONE_LACKS[{mid}] points at {entry['where']}, which is not there"))
            continue
        if entry["must_contain"] not in read(path):
            bad.append(("absences", f"PHONE_LACKS[{mid}] says {entry['where']} holds "
                                    f"`{entry['must_contain']}`, and it does not - check the "
                                    "absence is still real before trusting this line"))

    # 4. No phone source file may READ an id the registry calls desktop-only.
    reads = phone_menu_reads()
    for mid in names:
        if mid in reads:
            bad.append(("phone reads", f"the phone reads the menu id {mid} at {reads[mid]}, and "
                                       "jarvis_menus.py calls it desktop-only - the phone has this "
                                       "feature, so correct `apps` rather than the phone"))

    # 5. The two registries tell one story about the same section.
    pc_only = open_place_pc_only()
    cards = desktop_settings_card_ids()
    for sid in settings_desktop_sections():
        if f"settings.{sid}" not in names and sid not in cards:
            bad.append(("agreement", f"jarvis_settings_registry.py calls the section `{sid}` "
                                     f"desktop-only and there is no desktop-only menu "
                                     f"`settings.{sid}` - the two registries disagree"))
    for sid in SETTINGS_DESKTOP_ONLY:
        if sid in cards and f"settings.{sid}" not in names:
            bad.append(("agreement", f"`{sid}` is a real desktop Settings card and "
                                     "jarvis_settings_registry.py calls it desktop-only, but "
                                     f"jarvis_menus.py has no desktop-only `settings.{sid}` menu"))
    # ...and the phone's own "only on your PC" list is what answers at run time.
    for sid in SETTINGS_DESKTOP_ONLY:
        if sid not in pc_only:
            bad.append(("agreement", f"the phone's OpenPlace.PC_ONLY does not name `{sid}` - "
                                     "`settings.notifications` is exactly the section that went "
                                     "unnoticed for months, so every desktop-only section is held "
                                     "to it"))
    return bad


def main() -> int:
    names = desktop_only_ids()
    reads = phone_menu_reads()
    found = problems()
    checks = [
        ("absences", f"{len(names)} desktop-only menus, each with a reason that still points at "
                     "real phone code"),
        ("corrections", f"the {len(PHONE_HAS)} phone-has-it corrections still hold in the phone's "
                        "own code"),
        ("phone reads", f"no phone file reads an id the registry calls desktop-only "
                        f"({len(reads)} ids are read in all)"),
        ("agreement", "the two registries and the phone's own PC_ONLY list agree"),
    ]
    failed = 0
    for group, label in checks:
        bad = [line for g, line in found if g == group]
        print(("ok   " if not bad else "FAIL ") + label)
        for line in bad:
            print(f"        {line}")
        failed += bool(bad)

    print(f"\n{len(names)} menus are desktop-only; {len(PHONE_HAS)} of them are recorded as "
          f"features the phone really has, {len(PHONE_LACKS)} as real absences.")
    print(f"{len(checks) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
