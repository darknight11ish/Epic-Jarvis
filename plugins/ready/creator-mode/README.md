# creator-mode

Creator mode: ONE waiting folder on this PC where a creator puts a skill folder
or a plug-in folder, a read-only scan when the Settings card is opened, and ONE
install card a thing. A skill lands turned off; a plug-in is refused in this
slice, in the pack manager's own words.

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy this
folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name creator-mode`) and restart Jarvis.

- Module the loader calls: `jarvis_creator.install()` (takes the core's Handler)
- Born as a folder: it replaces no patch
- The waiting folder: `creator-incoming`, beside `skills\`, `skills-off\` and
  `skills-quarantine\` in the config folder. It is made when it is first
  needed, so the installer carries no empty folder.

## What the owner does

1. Put a folder in the waiting folder. A skill is a folder with `SKILL.md` in
   it. A plug-in is a folder with `plugin.json` in it.
2. Open Settings -> Skills -> Creator mode. The card scans what is waiting and
   says what the scanner found. Nothing is copied, nothing runs, and no card is
   raised for looking.
3. Press **Install it…** on ONE item. That raises ONE card on this PC. A skill
   the scanner refuses never becomes a card, and a plug-in never becomes one at
   all in this slice: a plug-in is a program, and Creator mode installs none
   yet.
4. The skill lands **turned off**. Turn it on with the ordinary **Turn on…**
   button in the Skills list, which has its own scanner and its own card.

There is no "install all", no network source and no watcher: the folder is
scanned when the card is opened, and installed only when the owner answers a
card. Both routes refuse every device but this PC.

The module itself is one of the ones this repository already ships
(`jarvis-backend/jarvis_creator.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not change it.
