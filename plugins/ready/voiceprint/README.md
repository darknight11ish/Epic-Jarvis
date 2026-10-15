# voiceprint

**Write Like Me:** Jarvis drafts in the owner's own voice, measured from his
own words, on his own PC.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name voiceprint`) and restart Jarvis.

- Module the loader calls: `jarvis_voiceprint.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Position in the loader's order: **146**. It was 142 until 2026-10-15, when
  `skill-hub` was found to claim 142 as well - so the loader was ordering the two
  by folder NAME, which nobody chose. `skill-hub` kept 142 and this moved to the
  first free number after it: 143 (`receipts`), 144 (`auto-router`) and 145
  (`vault`, on `fix/vault-fail-closed`) are all taken, so 146 is the next one
  free. Its four paths are therefore checked after those rather than in the
  middle of somebody else's.

The module itself is one of the ones this repository ships
(`backend/jarvis_voiceprint.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not change it.

Its four routes:

    GET  /api/voiceprint                the learned samples, the voiceprint
                                        numbers, and what the engine is doing
    POST /api/voiceprint/sample         one piece of the owner's own writing
    POST /api/voiceprint/learn_edit     his final version of a draft, as a gold sample
    POST /api/voiceprint/forget         delete one sample; needs "confirm": true

What it does, in plain words: it finds how the owner has written about
something similar before, takes the names and numbers out of that example, and
shows his own model the shape of his sentences. Nothing is sent anywhere. No
weights are changed. It is a memory read, so the turn stays on the local model.

**Every write is guarded, and fails closed.** With no `jarvis_scrub` nothing is
written at all - the store is not even created. A sample that looks like it
holds a password, a key or a one-time code is refused, not stored.

**Forget asks first.** The owner's decision of 2026-09-24: forgetting cannot be
undone, so it asks "are you sure?" first. That question is enforced on the
server, not only in the app: a forget without `"confirm": true` changes
nothing.

**This is not `jarvis_style.py`.** An earlier version of the same idea lives in
`jarvis-backend/jarvis_style.py`. The installer never writes that file - it is
in no patch and in no `$SHIPPED` entry - so editing it would reach nobody. It is
left exactly as it is, and this module carries the engine instead. The reasons,
and the limitation that comes with them, are recorded in `docs/ARCHITECTURE.md`
section 8 ("Write Like Me `voiceprint`").
