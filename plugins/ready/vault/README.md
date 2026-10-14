# vault

A secret is kept in Windows Credential Manager and everything else carries its
NAME - a handle, `{{vault:github}}` - never the value.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder and restart Jarvis.

    Copy-Item plugins\ready\vault "$env:JARVIS_BACKEND\jarvis_plugins\" -Recurse

- Module the loader calls: `jarvis_vault.install()` (takes the core's Handler)
- Routes: `GET /api/vault/handles`, `POST /api/vault/put`
- Position in the loader's order: 144, after `receipts` at 143, so its two paths
  are checked in the order they were added rather than in the middle of
  somebody else's
- The patch this replaces: none - this is not a feature that used to be a patch

## Why `scripts\add-plugin.ps1 -Name vault` says "not a drop-in module"

Every other folder here replaces a patch: `tools/gen_plugin_catalogue.py` reads
`$PATCHES` in `scripts/apply-patches.ps1` and writes a folder for each patch
whose only wiring was one `install()` call. The vault never was a patch - it is
built for the drop-in loader from the start - so there is no patch for the
generator to find and **this folder is not in `plugins/registry.json`**, which
is where `add-plugin.ps1` reads its names from. That script therefore refuses
the name, and copying the folder by hand, as above, is what to do.

Three consequences, all real, all measured on 2026-10-14:

1. `scripts\add-plugin.ps1 -Name vault` will not work. Copy the folder by hand.
2. Running `python tools/gen_plugin_catalogue.py` (the *writer*, not `--check`)
   prunes any `ready/<name>` folder that is not in the catalogue, so it would
   delete this one.
3. `tools/check_plugins.py` and `tools/gen_plugin_catalogue.py --check` both
   PASS with this folder here, because both iterate the catalogue's own entries
   and never the folder list - so their being green says nothing about whether
   this folder survives a regeneration.

`plugins\ready\receipts\` is the same shape, from the same week, and its README
does not say this; its own line tells the reader to run `add-plugin.ps1 -Name
receipts`, which fails for the same reason. This is written down here rather
than assumed, because it is the kind of thing that is only ever discovered by
the person following the instruction.

The module itself is one this repository ships
(`backend/jarvis_vault.py`), copied into the backend by `scripts/apply-patches.ps1`
exactly as before. This folder does not change it.

## What it does

- `GET /api/vault/handles` - the names, the host each is bound to and when each
  was last used. **Never a value, never a mask or a prefix of one.**
- `POST /api/vault/put` - `{"name": ..., "value": ..., "for_host": ...}`. This
  is a mutating action, so it goes through the one permission model: ONE
  approval card at tier `ask`. A denied, timed-out or refused card stores
  nothing, and nothing is stored before the answer.

The values are in Windows Credential Manager, under `Jarvis Backend/vault/<name>`.
`vault.json` in the config folder holds the names, their host binding and their
times - and no value, ever.
