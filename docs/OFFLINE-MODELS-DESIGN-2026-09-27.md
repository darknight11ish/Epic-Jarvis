# Seeing the model list when Jarvis isn't running

Design research only. No code changed. Answers the owner's request: "make it
so I can view the models on the Android app and desktop program without
having Jarvis up and running."

## The short answer

**Recommended: a small cache file, written by each app the last time it
successfully read the model list, shown read-only and clearly marked
"as of &lt;time&gt;" whenever the live read fails.** That is the only option
that works on the phone at all, so it is worth building it once and reusing
it on the desktop too, rather than building two different things.

The desktop *could* also read Ollama's own files off the disk directly, with
Jarvis not running at all - but that only gets the installed-models list
(name, size, digest), not quantization or "what's loaded right now" without
extra work, and it means new code that talks to Ollama's files instead of
going through the backend, which nothing else in this app does today. I
recommend **not** building that for a first version - the cache alone
already answers the owner's request for both apps, with much less new code
and no new place for a bug to hide. It is written up below in case the
owner wants it later, e.g. if the cache ever drifts from what's really
installed.

## 1. What "the model list" actually is today, and a correction

The task description names "Settings -> Hardware and models" on desktop and
"Brain -> Hardware" on the phone as today's model list. Having read the
code, that is not quite where the list with sizes lives, and it is worth
saying so plainly rather than routing around it:

- **Settings -> "Hardware and models"** (`jarvis-desktop/src/hardware-panel.js`,
  `src-tauri/src/hardware.rs`; phone equivalent `HardwareSection.kt` /
  `net/Hardware.kt`, reached from Brain) is about the **graphics cards** -
  which GPU(s) are found, what preset (Fastest/Smartest/Most features) is
  chosen, and the steps to get there. It shows the *name* of the model
  running now, but not a list of every installed model with its size.
  Route: `GET /api/hardware`.
- **Brain -> "Model"** (`jarvis-desktop/src/brain.js` `renderModels()`;
  phone's `BrainScreen.kt` `ModelsPlate` at line 863, fed by
  `net/ApiModels.kt`'s `ModelsInfo`) is the screen with the actual **list
  of installed models**, each with its size and family, which one is
  current, which was previous, and recent speed. Route: `GET /api/models`.

Both screens read live and have no cache today (see below). The owner's
request - "view the models" with sizes - is mostly about the second screen,
Brain -> Model, even though the GPU/hardware screen is the one most likely
to get asked about too since it's the other place a model's name shows up.
The design below covers both, since the same small piece of work serves
both.

## 2. Confirming today's mechanism really has no cache

Read `hardware-panel.js`, `hardware.rs`, `brain.js`'s `renderModels()` and
`load()`, and the phone's `Hardware.kt` and `ApiModels.kt`. All four:

- Call the backend fresh every time the screen opens or polls
  (`GET /api/hardware`, `GET /api/models`, and - for what's actually running
  in Ollama's memory - the backend's own read of Ollama's `/api/ps`).
- Keep **no file on disk**. `grep -rn localStorage jarvis-desktop/src/*.js`
  shows `localStorage` used only for UI preferences (theme, zoom, whether a
  toggle is on, which settings row to scroll to) - never for the content of
  a backend read. The phone's `DataStore`/`SharedPreferences` uses
  (`ClientSettings.kt`, `AppearanceStore.kt`, `TokenStore.kt`) are the same:
  settings and the pairing key, not cached reads.
- Fail two different ways today, worth knowing about because one of them is
  most of the pattern this feature needs, already built:
  - **`brain.js`'s `load()`** (lines 596-662) keeps the *last good answer for
    each section in memory* (`state.data[section]`) and, if the next read
    fails, keeps showing the old one and says so: `"Could not read models:
    <why>. What is shown is from the last read that worked."` This is exactly
    the shape the owner is asking for - but it lives only in the page's
    in-memory `state` object. Close the window, or restart the app, and it
    is gone; the very next launch has nothing to show until a live read
    succeeds.
  - **`hardware-panel.js`'s `loadHardware()`** does the opposite: on any
    failure it calls `showProblem()`, which sets `last = null` and **hides
    the whole panel**, showing only an error sentence. Nothing carries
    over, not even within the same session.

So there is a nearby, in-spirit pattern (`brain.js`'s "last read that
worked") but it does not survive an app restart, which is the exact case
the owner is asking about - Jarvis not running when the app opens. Nothing
in this codebase persists a backend read to disk today. This is genuinely
new, not a gap in an existing feature.

## 3. Where the data could come from

### Option A - a cached copy of the last successful read (recommended)

Each app keeps a small file with the last good answer from `GET
/api/models` (and, for the desktop's hardware screen, `GET /api/hardware`'s
`cards` and `now` sections too), written every time that read succeeds, and
shown read-only, clearly marked as old, whenever the live read fails or the
backend cannot be reached at all (`plain-errors.js`'s `pc_unreachable` /
`jarvis_not_running` cases - see below).

This fits the project's existing "say what's wrong, plainly" pattern
(`plain-errors.js` / `PlainErrors.kt`, `tests/plain-error-cases.json`): when
the backend can't be reached, both apps already show one plain sentence and
a fix ("Jarvis isn't running on your PC... press Start under 'Starting
Jarvis for you'"). This feature adds a **second** thing to show alongside
that sentence, not a replacement for it: the sentence saying why live data
isn't available right now, and, under it, the cached list with its "as of"
time.

### Option B - reading Ollama's own files off the disk (desktop only, and only partly)

Possible, but only from the desktop, and only for part of the answer.
Labelled as external research (Ollama's own documented behaviour, not
anything found in this repository):

Ollama stores what it has downloaded under `%USERPROFILE%\.ollama\models`
on Windows by default (overridable with the `OLLAMA_MODELS` environment
variable, which a careful reader would check via `Get-ChildItem Env:
OLLAMA_MODELS` before assuming the default path). Inside that folder:

- **`manifests\registry.ollama.ai\library\<model>\<tag>`** - one JSON file
  per model:tag, e.g. `manifests\registry.ollama.ai\library\qwen3\8b`. It
  lists a `config` digest and an array of `layers`, each with a `digest`
  (`sha256:...`) and a `size` in bytes. Summing the layer sizes gives the
  model's on-disk size - this is what `ollama list`'s SIZE column comes
  from.
- **`blobs\sha256-<digest>`** - the actual model weights and metadata,
  named by content hash, shared between models/tags that happen to include
  the same layer.

These are **plain files**. Reading them needs nothing from Ollama's own
service - it does not need Ollama running, and it does not go through
Jarvis's Python backend either. A name and a size are cheap to get this
way.

The catch is **quantization** (e.g. "Q4_K_M"). Ollama's own `/api/show` and
`ollama list` get that by reading the GGUF file's own header out of the
blob - the manifest JSON does not carry it as a field. Getting quantization
straight from disk means writing a small GGUF-header reader, not just JSON
parsing. That is real, buildable work, but it is a second, separate piece
from reading the manifests, and it duplicates logic Ollama's own code
already has, only to have it break the day Ollama changes its GGUF layout.

**Recommendation: skip Option B for now.** It only ever covers the desktop
half, it needs new code to read a foreign program's on-disk format instead
of going through the one channel (the backend, `jarvis_base`) every other
Rust command in `hardware.rs`/`commands.rs` already uses, and everything it
would show (name, size, maybe quantization) Option A already shows more
simply, cached from the last time Jarvis itself asked Ollama. It is worth
keeping in mind only if the owner later wants the desktop to double-check
the cache is not stale in a way that matters (e.g. a model was deleted
outside of Jarvis) - a possible "also verify against disk" follow-up, not
a replacement for the cache.

## 4. The phone specifically

The phone has no access to the PC's disk, full stop - Option B does not
exist for it under any design. And it must not become a model catalogue or
browsing UI, which is a standing rule (`CLAUDE.md`: "do not build the model
catalogue... on the phone"). Both of those point at the same answer:

**The phone's offline view is a cached copy of its own last successful
read of `GET /api/models`, and nothing else.** It is not a live disk read
(impossible), and it is not a browsable catalogue (against the rule) - it
is a plain read-only replay of what the phone itself already saw and
already had permission to see, from the last time it was actually talking
to the PC. This is not new ground the standing rule needs revisiting for:
today's live view is already "the installed models, as words the PC sent,
with Use/Install buttons" (no catalogue); the offline view is the exact
same data, just held a little longer and marked as old. Nothing about it
lets the phone browse, search, or discover a model it hasn't already been
told about.

One thing to avoid, called out because it is an easy mistake to make: **do
not have the phone try to "sync" or "refresh" the cache on demand as part
of showing the offline view.** That would need exactly the live PC
connection that "offline" is supposed to work without - a contradiction.
The cache is written *only* as a side effect of an ordinary, already-
happening live read (opening Brain -> Model, or the app's normal background
refresh), never fetched specially for the offline case.

## 5. What "offline" can honestly show, field by field

| Field | Offline-safe? | Why |
|---|---|---|
| Which models are installed, and their names | Yes, cached | Ollama already told the backend this at the last live read; it doesn't change from moment to moment. |
| Each model's size | Yes, cached | Same as above. |
| Each model's family (e.g. "qwen3") | Yes, cached | Same as above. |
| Which model was "current" and "previous" at the last live read | Yes, cached, but labelled as of the cache's time, not "now" | This can have changed since - a switch approved from another device, for instance. |
| Which model is loaded in Ollama's memory *right now*, and its speed numbers | **No - hide it, don't show it stale** | This needs `GET /api/ps` on a running Ollama by definition. Showing yesterday's "currently running: qwen3:8b" while Jarvis is off would read as live and be wrong - the model in memory list is very likely empty if Ollama unloaded it, or a completely different backend/model may be running by the time the owner is next connected. |
| Whether the model is on the graphics card or spilled to the CPU (`offload`) | **No - hide it** | Same reason: this is a live measurement of what's happening right now, not a fact about the file on disk. |
| "Use"/"Install" buttons | **No - hide or disable them** | They ask the PC to do something; asking a PC that isn't there just times out. Showing them invites a tap that goes nowhere. |
| The GPU cards found, and the chosen hardware preset (the other screen) | Yes, cached, same "as of" treatment | These are also just facts read from the PC last time, not live measurements - except the preset's "on card %" and health line (temperature/watts/fan), which are live and should hide the same way as "currently running" above. |

The rule in one sentence, to reuse in code review later: **cache and show
anything that is a fact about a file Ollama already has; hide, don't
guess, anything that is a fact about what Ollama's process is doing right
now.**

## 6. The concrete design

### The cache file

One small JSON file per app, holding just enough to redraw the two screens
above, nothing more (never chat text, never a token):

```json
{
  "as_of": 1758960000,
  "models": {
    "current": "qwen3:8b",
    "previous": "qwen3:4b",
    "installed": [
      { "ref": "qwen3:8b", "size": 5100000000, "family": "qwen3" },
      { "ref": "qwen3:4b", "size": 2600000000, "family": "qwen3" }
    ]
  },
  "hardware": {
    "cards": [
      { "name": "NVIDIA GeForce RTX 2080 SUPER", "total_gb": 8, "used": true }
    ],
    "now_label": "Fastest answers",
    "chosen": "fast"
  }
}
```

`as_of` is a Unix timestamp, set at the moment the read that filled this
cache succeeded - the same clock `brain.js`'s `state.readAt[section]` and
`Hardware.kt`'s `now: Long` already use elsewhere, so no new time-handling
code is needed. The shape deliberately drops everything from `/api/models`
and `/api/hardware` that is either live-only (per the table above, so it's
never shown by mistake) or is already elsewhere (approval-card details,
speed history) - keeping this file small and single-purpose.

**Where it lives:**
- Desktop: a JSON file beside the other settings the desktop already keeps
  locally (the same folder pattern as `SETTINGS_PLACE_KEY` and the barge-in/
  face-tuning preference files, i.e. plain per-user app data on this PC -
  never inside the repo, never synced anywhere). Written by the Rust side
  (`hardware.rs`'s `get_hardware`, and the equivalent for `/api/models`)
  right after a successful read, so it survives even if the window that
  triggered the read is later closed uncleanly.
- Phone: one row in the same local `DataStore` `ClientSettings.kt` already
  uses (or a tiny sibling store next to it) - not a database table, since
  there's only ever one "last models read" to keep, not a history of them.

**When it's written:** every time `GET /api/models` (and, for the desktop's
hardware panel, `GET /api/hardware`) succeeds - the exact same moment
`brain.js`'s `load()` already updates `state.data.models` and
`state.readAt.models` in memory. This is genuinely "for free": the write is
one extra step tacked onto a success path that already runs constantly
while the app is open and Jarvis is up, so the cache is fresh as of the
last time either app was actually used while connected - never fetched
specially, per point 4 above.

**When it's read:** once, when the screen opens, before or alongside the
live attempt - so a cold start with Jarvis off has something to paint at
once instead of a blank screen while the request times out.

### What the offline view shows

Using the exact wording style already in `plain-errors.js` (short sentence,
what happened, then what it means) and matching `brain.js`'s existing "What
is shown is from the last read that worked":

> **Jarvis isn't running on your PC**, so this list is from the last time
> it was: **27 Sep, 6:14pm**. Sizes and names are probably still right.
> What's actually loaded right now isn't shown, since only a running
> Jarvis knows that.

Below that sentence, the screen shows the cached installed-models list
(name + size + family) and the cached GPU-card names/sizes, with:
- **No "current model" highlight drawn as if it were live** - instead, a
  quieter note: "As of the last connection, qwen3:8b was the one in use."
- **No "Use"/"Install" buttons**, or shown disabled with "Needs Jarvis
  running" under them, matching how the rest of the app already dims
  controls while the link is stale (rule 4, `canAct` on the phone,
  `busy`/disabled buttons on desktop) - reusing that exact greying pattern
  rather than inventing a new "offline" visual state.
- **No live GPU health line** (temperature/watts/fan) and **no "on card %"
  bar** - both hidden outright, not shown stale, per the table in section 5.
- A single **Retry** (desktop already has this button pattern in
  `plain-errors.js`'s `retry` action; the phone's `Quiet("Refresh", ...)`
  already on the Hardware screen does the same job) that attempts the live
  read again and, on success, replaces the whole view with the live one and
  refreshes the cache.

If there has **never** been a successful read at all (a fresh install, or
Jarvis has genuinely never run) - say that plainly instead of showing an
empty list: "There's nothing to show yet - open this once while Jarvis is
running on your PC."

## 7. Fit with what's already there

- Reuses `plain-errors.js` / `PlainErrors.kt`'s existing sentence-plus-fix
  shape and its `pc_unreachable` / `jarvis_not_running` wording rather than
  inventing new error text.
- Reuses `brain.js`'s existing "last read that worked, marked as old"
  pattern (section 2 above) rather than a different mechanism for this one
  screen - and, as a side benefit, this work is a natural moment to make
  `hardware-panel.js`'s `loadHardware()` stop wiping the panel to a blank
  problem screen on every failure (its `showProblem()`/`last = null`) and
  instead fall back to the same cached-and-marked view, so the two screens
  finally behave the same way on a dead backend. Worth flagging to the
  owner as a small related fix, not required to ship the main feature.
- Reuses the existing dimmed/disabled-control pattern (rule 4: "the app
  blocks acting when the event stream is stale") for Use/Install while
  offline, rather than a new visual treatment.
- No new approval card, no new setting, no egress: this is a read of data
  the app already had permission to see, held a little longer. Nothing
  about rules 1-5 in `CLAUDE.md` is touched.
- No change to what may be built on the phone: still no catalogue, no
  search, no picker - only a delayed replay of the same non-browsable list
  the phone already shows live today.
- Needs a line each in `docs/JARVIS-API.md` (nothing - no route changes)
  and `docs/ARCHITECTURE.md` §8's parity table only if the cache ships on
  one app before the other; if both ship together, no §8 entry is needed
  since it isn't one-sided.

## 8. Size estimate

- **Desktop: S.** One small Rust-side write-through-cache (a JSON file, a
  save-on-success, a load-at-startup, both already-shaped read paths just
  need one line each after they succeed), plus JS-side changes to
  `hardware-panel.js` and `brain.js`'s `renderModels()` to paint the "as of"
  banner and grey the live-only fields and buttons. The Windows-target
  `cargo check`/`clippy` workflow in `CLAUDE.md` covers checking the Rust
  half without a live backend.
- **Phone: S/M.** A `DataStore` (or small Room row) write-through cache next
  to `ClientSettings.kt`, a `Hardware.Read`/`ModelsInfo` "offline, cached"
  state added to the existing sealed-interface pattern already used for
  `Read.OlderBackend`/`Read.NotInstalled`, and the same greying in
  `HardwareSection.kt`/`ModelsPlate`. Slightly bigger than the desktop half
  only because every change needs the ~15-minute CI round trip
  (`CLAUDE.md`: no local Android build) to confirm it compiles and the
  contract tests (`HardwareContractTest`, the models equivalent) still pass
  against the shared fixtures - not because the change itself is larger.
