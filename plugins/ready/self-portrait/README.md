# self-portrait - what Jarvis is made of, on this PC

The owner's ask (2026-11-03): *"be aware of every setting, function and ability
it has"* - and open any place, find any old conversation, and clear one on
request.

This folder is the whole wiring. `plugin.json` names
`jarvis_self_portrait` and its `install()` wraps the server's handler, so
there is **no patch to `jarvis_hud.py`** - the plugin loader makes the call.

## What it answers

- `GET /api/self` - the portrait. Places (every `SECTIONS` row and every
  `MENUS` row, imported from the two registries, never typed here), settings
  with their live values, what asks first, abilities, drop-in plugins, store
  counts, and the installer's recorded identity.
- `GET /api/self/version` - the cheap identity block alone. The version
  **string** is `app_version`; the live modules' identity is
  `deploy.identity` (sha256) and `deploy.resealed.commit`, read from
  `_jarvis-state.json` beside `jarvis_hud.py`.
- `GET /api/conversations` and `GET /api/conversations/<id>` - thin aliases
  onto `jarvis_chat_log`'s own History routes, so there is still ONE list and
  ONE reader.
- `POST /api/conversations/clear {"id": "..."}` - ONE conversation, ONE
  approval card (action `conversation_clear`, tier `ask`). The card names the
  chat by title and message count, says it cannot be undone, that the facts
  Jarvis learned from it are KEPT, and that copies in older backups stay until
  they age out. There is no bulk form and no cardless form.

Nothing here reads the pairing token, an API key, an account secret, a word
of memory or chat, an email, a web page, a model-written sentence or an owner
folder path. A value that cannot be read says "unknown", never "off".

## What is deliberately not here

- No new source of truth: the place ids come from
  `jarvis_settings_registry.SECTIONS` and `jarvis_menus.MENUS`, and their own
  generators plus `backend/test_self_portrait.py` hold this module to them.
- No new event kind: navigation stays on the existing `X-Jarvis-Route`
  response field.
- No memory-clear route: forgetting keeps its existing `/api/memory/forget`,
  `/api/memory/erase` and "Forget a time frame" flows.

## Turning it on and off

Copy this folder into `jarvis_plugins\` beside `jarvis_hud.py` (or run
`scripts\add-plugin.ps1 self-portrait`) and restart Jarvis. Take it out and
restart and the routes are gone; nothing else changes.
