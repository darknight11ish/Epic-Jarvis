# media-index

The searchable recordings and videos index (F5 slice S2, owner decision of
2026-10-19: keep readable transcript text, switch ON by default). One route,
so the desktop's Settings can show the switch, the plain-language disclosure
and the one Delete:

    GET  /api/media-index
         the switch (on/off, a card waiting), the stored counts, how many
         recordings are still waiting to be indexed, and the disclosure words

    POST /api/media-index {"enabled": bool}
         ON  -> ONE normal approval card on the PC (`change_own_config`, tier
                `ask`), 202 while it waits; nothing is written before a person
                says yes
         OFF -> at once, 200, and it takes back a waiting ON card

    POST /api/media-index {"action": "delete", "path": "..."}
         removes that ONE recording's stored words. The recording itself is
         never opened or touched.

    POST /api/media-index {"action": "delete"}
         removes every stored word AND the index file. This is what the
         backup exclusion makes real: `media-index.db` is in
         `jarvis_backup.py`'s exclusion table (day one), so no older backup
         holds a copy that a Delete could leave behind.

**Drop-in, and this one replaces NO patch.** The module itself
(`backend/jarvis_media_index.py`) is shipped by `scripts\apply-patches.ps1`
exactly as before; its route existed as no patch because it needs none. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name media-index`) and restart Jarvis - the same
mechanism `plugins/ready/sandbox` uses.

- Module the loader calls: `jarvis_media_index.install()` (takes the core's Handler)
- The patch this replaces: none - it is born as a folder
- Position in the loader's order: 152, the first free slot after `sandbox` (151)

The chat path needs none of this: `my_files`'s `search_media` action works as
soon as the module is installed, with no plugin folder and no route.

An older backend that has the module but not this folder answers 404 on the
route; the desktop Settings card then says so in words instead of showing a
switch that does nothing.
