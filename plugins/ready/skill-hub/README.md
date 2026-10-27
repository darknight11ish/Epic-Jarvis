# skill-hub

The skill library's other doors: a reference manual read only when it is asked
for, leading `/skill` and `/bundle` chains, a project's own skills, and
`/learn`.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name skill-hub`) and restart Jarvis.

- Module the loader calls: `jarvis_skill_hub.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Position in the loader's order: **145**, the first free slot after every
  folder the old patch stack had (`model-lanes` is the highest of those, at
  144), so its four routes are checked after that stack rather than in the
  middle of somebody else's. 146 is `voiceprint` and 147 is `receipts`, so 145
  is the free slot that collides with neither. `backend/test_receipts.py` asks
  only that a no-patch folder sorts AFTER every catalogued one, which 145 does.

The module itself is one of the ones this repository ships
(`backend/jarvis_skill_hub.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not change it.

## What it adds, and what it does not

`jarvis_skills.py` already owns the skill itself - the frontmatter parser, the
scanner, the quarantine, the ~100-token card, the full body, installing,
removing and writing one. **This module calls all of those and re-implements
none of them.** It adds the four things that were missing:

| door | what it does |
|---|---|
| `references()` / `level2_reference()` | the reference manuals. `parse_skill` collects `references/<file>.md` but nothing ever read one. Listing a manual costs nothing; reading one costs one file, scanned before it is handed over |
| `parse_chain()` / `expand_chain()` | up to five LEADING `/skill-name` or `/bundle-name` tokens, stopping at the first name that is not known, so `/path/to/file` is never swallowed |
| `project_roots()` / `project_skills()` | `<project folder>/.jarvis/skills` for projects the owner explicitly trusted, with anything that fails the scan quarantined rather than loaded |
| `learn()` | `/learn`: a four-section distillation (When to Use / Procedure / Pitfalls / Verification), scrubbed through `jarvis_scrub`, writing NOTHING when the scrubber is absent, saved only through the existing `jarvis_skills.write_skill()` so its scanner and its approval card run where they always have |

## Its four routes

    GET  /api/skills/hub/references?skill=<name>[&file=<ref>.md]
    GET  /api/skills/hub/projects
    POST /api/skills/chain          {"text": "/skill-a /bundle rest of the message"}
    POST /api/skills/learn          {"topic": ..., "steps": [...], "when": ..., "pitfalls": ..., "verification": ...}

It adds no route that already exists. **`GET /api/skills` (the list) and
`POST /api/skills/decide` (removing one, and the "are you sure?" that goes with
it) are `jarvis_hud.py`'s already, on both apps, and this module leaves them
exactly where they are.**

Nothing here approves anything. `/learn` is not a way around the scanner or the
card: it reaches the write only through `jarvis_skills.write_skill()`, which
scans first and raises the `modify_own_code` card first - and it re-checks that
`modify_own_code` is tier `ask` itself, so a settings file that listed it as
`notify` cannot turn the card into a rubber stamp.
