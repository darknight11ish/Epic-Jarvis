# receipts

Action receipts and one-click undo: every action that CHANGES something
leaves a receipt saying what changed, with one button to put it back.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name receipts`) and restart Jarvis.

- Module the loader calls: `jarvis_receipts.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Position in the loader's order: 146, after every folder the old patch stack had
  (the highest is `model-lanes` at 143), so its two paths are checked in the order
  they were added rather than in the middle of somebody else's

The module itself is one of the ones this repository already ships
(`backend/jarvis_receipts.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not change it.

Its two routes:

    GET  /api/receipts                     the recent list. A read.
    POST /api/receipts/<receipt_id>/undo    put one change back.

Undo is a mutating action, so it goes through the one permission model like
everything else: ONE card, action `undo_action`, tier `ask`, and the reversal
runs only after a person's approved. A denied card changes nothing.
