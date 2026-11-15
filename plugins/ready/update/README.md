# update

**Update Jarvis on the PC, asked for and approved from the phone.**

The owner's ask: the phone should be able to *request and authorize* a desktop
update - their fingerprint approving ONE card - without going to the PC. The
Windows Hello step is deliberately not part of this: the approval is the
phone's own fingerprint on its own approval card, and the update action is NOT
in `jarvis_owner_check.PC_ONLY_ACTIONS`.

**Drop-in.** Copy this folder into the backend's `jarvis_plugins\` folder (or
run `scripts\add-plugin.ps1 -Name update`) and restart Jarvis. The module it
names ships with this repository (`backend/jarvis_update.py`), copied into the
backend by `scripts/apply-patches.ps1`; this folder adds no patch to
`jarvis_hud.py`. Nothing new is installed and no gate file is touched: the card
is the gate's own `ask` tier for the action `update_jarvis`.

## The two routes

`GET /api/update/status` - read-only, no card. `installed` is the version of
Jarvis Desktop on this PC (the highest Windows uninstall entry, the same row
`Get-InstalledDesktop` reads), `published` is the newest release from the
public manifest the desktop app's own updater reads ("cannot tell: ..." in
words when either cannot be read), `newer` is `true`, `false` or `null`, and
`phase` is one of `closing`, `patching`, `installing`, `restarting`,
`checking`, `done`, `failed` or `idle` - each with a plain sentence in `what`.
`can_request` and `why_not` are the same answers the POST would give.

`POST /api/update/request` - `{}` is the whole body. It refuses, in words, when
there is nothing newer (or the two versions cannot be compared), when an update
is already running (in this backend, in the helper, or by the desktop's own
"update both halves"), when the backend folder cannot be found, when this
repository's folder cannot be found, or when the tier is not `ask`. Otherwise it
raises exactly ONE card and starts nothing. The card says which version it moves
to, that Jarvis on the PC closes for about a minute, that this phone's link
drops and comes back, that the installer's signature is checked, and that
nothing else on the PC changes.

On approval a detached helper runs `scripts/update-jarvis.ps1` - the one
program that already does the whole update safely - with arguments the module
builds itself (`-BackendPath <the folder it found> -Force`). No part of the
request can add an argument. The helper writes progress to
`<config dir>/update-state.json`, which the status route reads even after the
restart the update caused.

## Nothing approves itself

The card is raised through `jarvis_gate.check` at tier `ask`, and the update
starts only on a verdict that is a person saying yes (`allowed` AND
`outcome == "approved"` AND tier `ask`). A loosened tier line is refused in
words BEFORE a card exists. `update_jarvis` is in
`jarvis_asks_first.MUST_ASK` and `jarvis_agent.NEEDS_A_PERSON`, so a later
settings edit still cannot run it with nobody asked.

## One at a time

A second request refuses cleanly: one card may be waiting at a time, a state
file whose phase is in flight with a live pid blocks a new one, the helper takes
an exclusive `update-helper.lock`, and the helper holds the same
`update-in-progress.lock` the desktop's own updater writes - so neither update
path can run beside the other.

## What this half does not have yet

No phone UI. The backend half is this module and its two routes; the phone
screen comes next (`docs/ARCHITECTURE.md` section 8 records the one-sidedness).
