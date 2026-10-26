# sandbox

The data and maths sandbox's own switch: whether the AI model is offered the
small read-only Python tool at all. OFF by default; turning it ON is ONE
normal approval card on the PC (`change_own_config`, tier `ask`), and turning it
OFF is instant, from either app. Every one of the sandbox's own refusals (the
AST allow-list, the time limit, the output cap, the memory cap, files only)
stays exactly as it is - this switch only decides whether the model is TOLD the
tool exists.

**Drop-in, and this one replaces NO patch.** The module itself is one this
repository already ships (`backend/jarvis_sandbox_exec.py`, copied into the
backend by `scripts\apply-patches.ps1` exactly as before); its route existed as
no patch because it needs none. Copy this folder into the backend's
`jarvis_plugins\` folder (or run `scripts\add-plugin.ps1 -Name sandbox`) and
restart Jarvis.

- Module the loader calls: `jarvis_sandbox_exec.install()` (takes the core's Handler)
- The patch this replaces: none - the feature was born as a folder
- Position in the loader's order: 155, the first free slot after every folder
  the old patch stack had (`self-improve` is 151, `setup` is 150,
  `notion-obsidian` is 149)

Its two paths:

    GET  /api/sandbox                     what both Settings rows show: the
                                          state and the PC's own words
    POST /api/sandbox {"enabled": bool}   ON -> one approval card (202 waiting,
                                          nothing written yet); OFF -> 200 at once

The POST handler never writes the setting itself: it calls the module's
`request_enabled()`, which is the same function the chat/voice phrase uses, so
a direct POST cannot bypass the approval card. A request from another device is
refused (403) before its body is read, and a wrong token is 401 - the same shape
as every other route.

An older backend that has the module but not this folder answers 404 on the
route; both apps then disable the row and say the PC's Jarvis does not have the
switch yet, rather than showing a switch that does nothing.
