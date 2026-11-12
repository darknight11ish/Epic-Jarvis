# offline-sync

Two-way offline synchronization and mobile edge lane for the Android companion:
allows the phone to operate autonomously offline, capture thoughts and memories,
and seamlessly synchronize with the desktop PC upon reconnecting.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name offline-sync`) and restart Jarvis.

- Module the loader calls: `jarvis_offline_sync.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Position in the loader's order: 195, after the standard stack, so its routes are registered cleanly

The module itself is one of the ones this repository already ships
(`backend/jarvis_offline_sync.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not change it.

Its endpoints:

    POST /api/sync/offline-batch           upload offline turns and memories
    GET  /api/sync/status                  sync statistics and counts
    POST /api/models/mobile-lane/register  register phone as mobile edge lane
    GET  /api/models/mobile-lane/status    mobile edge lane status
    GET  /api/models/transfer/available    recommended models for mesh transfer
