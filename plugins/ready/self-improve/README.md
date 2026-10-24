# self-improve

Two **read-only** diagnostic routes, so the owner can ask Jarvis about its own
source and about the local model's capabilities without opening a keyboard in
the backend.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: like
`receipts`, this feature is born as a folder. Copy this folder into the
backend's `jarvis_plugins\` folder (or run `scripts\add-plugin.ps1 -Name
self-improve`) and restart Jarvis.

- Module the loader calls: `jarvis_self_improve.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Position in the loader's order: 151, after every folder the old patch stack had
  and after the other no-patch folders added before it (`notion-obsidian` at 149
  is the one immediately before it, and `setup` at 150 is the patch that made
  room for this one), so its two paths are checked in the order they were added
  rather than in the middle of somebody else's

The module itself is one of the ones this repository already ships
(`backend/jarvis_self_improve.py`), copied into the backend by
`scripts/apply-patches.ps1` exactly as before. This folder does not change it.

Its two routes (both `GET`, both behind the same origin and token checks as
every other route):

    GET /api/self-improve/diagnose?q=<question>
        Read the program's own source, ask the LOCAL model which of those lines
        answers the question, and hand back the answer with `file:line`
        citations whose quotes are re-read from disk.

    GET /api/self-improve/contract?model=<name>
        Ask the local Ollama for `POST /api/show` and say which of the three
        outcomes it is: understood, a capability Jarvis has never heard of, or a
        capability the model plainly has that Ollama's list does not name.

A missing `q` is refused (400: "question is empty"), and so is one longer than
500 characters (400: "question is too long") - nothing is read for either. A
missing `model` uses the model a diagnosis would ask (`JARVIS_MODEL`, else
`qwen3.5:9b`). An internal failure is a 503 in plain words, never a traceback.

## What it deliberately does NOT do

- **No `POST` route, and no route for drafting a change.** Applying a change is
  Phase 5 of the self-improvement design and is not here. Nothing in this
  folder approves, writes, applies or reverts anything.
- **It does not write a file, start a program, or stop/start Ollama.** The
  diagnosis reads this program's own text and talks to the local model; the
  contract route makes ONE read-only `POST /api/show`, which reads the model's
  metadata and loads nothing.
- **It does not leave this PC.** The model address is the loopback guard
  `jarvis_self_improve._loopback_url()` already has: an `OLLAMA_HOST` pointing
  at another machine is not used.
- **No app calls these routes yet.** There is no desktop or Android button for
  them in this slice; they are a PC-side diagnostic for the owner (curl, or any
  client that already sends the token).
- **It does not show raw evidence lines.** A "could not establish it" answer
  carries no `file:line` at all, and citation quotes are scrubbed before they
  are returned.

The two routes and their JSON shapes are written down in `docs/JARVIS-API.md`
section 139.
