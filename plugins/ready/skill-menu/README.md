# skill-menu

The skills menu's PC doors: install a skill from a folder or a `.zip`, import
one from Hermes, turn an installed skill off and back on, and edit its
SKILL.md. The owner chose this scope on 2026-11-02 (the Hermes-skills research
document's option **B**).

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name skill-menu`) and restart Jarvis.

- Module the loader calls: `jarvis_skill_menu.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Position in the loader's order: **173**, the first free slot after every
  catalogued folder (`send-file` is the highest, at 172), so its five routes are
  checked after that stack rather than in the middle of somebody else's.

The module itself is one of the ones this repository ships
(`backend/jarvis_skill_menu.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not change it.

## What it adds, and what it does not

`jarvis_skills.py` already owns the skill itself - the frontmatter parser, the
scanner, the quarantine, the ~100-token card, the full body, installing,
removing and writing one. **This module calls all of those and re-implements
none of them.** Every install, every turn-on and every edit goes through
`jarvis_skills.install()`, which vets first and then raises exactly ONE
`modify_own_code` card.

| door | what it does |
|---|---|
| `menu()` | one read for the Settings screen: every installed skill, every one turned off, the verdict each was installed with, and how many files it ships in `scripts/` |
| `install_source()` | a folder or a `.zip` the owner picked on this PC, or a folder the Hermes scan named. The scanner runs first; a **refuse** verdict is quarantined and never becomes a card; a **review** verdict waits for `accept_warnings` from a person who read the warnings |
| `import_scan()` | a READ-ONLY scan of `%USERPROFILE%\.hermes\skills`. It lists what is there and what the scanner says about each one; it copies, moves and installs nothing, and raises no card |
| `set_state()` | off MOVES the folder to `<config>\skills-off\<name>` and takes its row out of the index, so the model is no longer offered it and `load()` cannot find it - no card, and nothing deleted. On is the same scanner and the same ONE card as installing it |
| `edit()` | the edited SKILL.md is written into a copy of the skill folder and installed through `install()` - the same scanner, the same ONE card, a block finding refused before any card |

## Its five routes

    GET  /api/skills/menu[?name=<skill>]
    POST /api/skills/install        {"path": "<folder or .zip>", "dry_run": true|false, "accept_warnings": true|false}
    POST /api/skills/install        {"hermes": "<folder from the scan>", "accept_warnings": true|false}
    POST /api/skills/import/scan    {}
    POST /api/skills/state          {"name": "<skill>", "on": true|false}
    POST /api/skills/edit           {"name": "<skill>", "text": "<whole SKILL.md>"}

It adds no route that already exists. **`GET /api/skills` (the list) and
`POST /api/skills/decide` (removing one, and the "are you sure?" that goes with
it) are `jarvis_hud.py`'s already, on both apps, and this module leaves them
exactly where they are** - the Settings menu's Remove button calls that same
route.

## No marketplace, no network, no auto-install

There is no catalogue to browse, nothing is downloaded, and nothing installs
itself. The only sources are a folder on this PC, a `.zip` on this PC, and
`~/.hermes/skills` if it already exists. The module imports no network library
and starts no process, and its `.zip` unpacking refuses a member that is
absolute, carries a drive letter, climbs with `..`, or is a symlink - with the
same file-count and total-size caps a skill folder already has.

One request raises at most ONE card. Three skills are three cards: there is no
"install all", no "yes to all" and no batch approval anywhere in it.

## What a Hermes skill really gets, said on the card and on the row

Hermes skills and Jarvis skills are the same format (agentskills.io), so a
Hermes folder usually installs as it is. Hermes-only metadata (`platforms`,
`metadata.hermes.*`, `required_environment_variables`) is kept and does
nothing here, and **a skill's `scripts/` folder is never run** - Jarvis skills
are instructions, full stop. Every card and every row for a skill that ships
one says it in the owner's words:

    Imported SKILL.md instructions (N file(s) in scripts/ are kept inert and
    never run automatically).

That sentence reaches the card through `jarvis_skills.install(..., note=...)`,
the one additive change `backend/skill-install-note.patch` makes. The same
patch makes the card a real card: `jarvis_gate.check` returns allowed=True on
tiers `notify` and `auto`, where nobody was asked, so `install()` now re-checks
the tier the way `jarvis_skills.refine()` already did.
