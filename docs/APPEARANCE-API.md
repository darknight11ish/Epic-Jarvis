# `/api/appearance` — the one route the face picker needs

> **Written, tested and ready to apply:** `backend/appearance.patch`. This page
> is the contract; that patch is the implementation of it for `jarvis_hud.py`,
> with nineteen checks in `backend/test_appearance.py` (the merge is in there)
> and fifteen in `backend/test_appearance_command.py` (asking for a face).

The desktop's Faces window edits which face Jarvis wears and how each of the
eight states looks. That choice is **data, not drawing code**, which is the
visual spec's own framing:

> Android (Compose) and the Tauri desktop cannot share drawing code — one is
> Kotlin, one is JavaScript — so what they share is this DATA.

A choice stored only on the desktop is therefore half a feature: the owner
picks `orbit` on the laptop and the phone carries on wearing `arc`. For the
picker to work **from either client**, the document has to live somewhere both
can read and write, and the only such place is the backend.

`/api/config` was the obvious existing home and is not one — it is a read on
the desktop side and a **501 on the server**, so there is no write path to
borrow. Hence a route.

The desktop already speaks this contract. Until the backend answers, every read
falls back to the local store and every write says so on screen:

> Saved on this machine. This backend has no `/api/appearance`, so the phone
> will not see it.

## The document

```json
{
  "face": "orbit",
  "bindings": {
    "idle":      { "pattern": "breathe", "color": "ice-3" },
    "listening": { "pattern": "solid",   "color": "ember-4" },
    "thinking":  { "pattern": "sweep",   "params": { "offset_deg": 246, "span_deg": 58 } },
    "speaking":  { "pattern": "reactive","color": "ice-4", "params": { "loud": "ice-5" } },
    "approval":  { "pattern": "pulse",   "color": "amber-4" },
    "standby":   { "pattern": "solid",   "color": "neutral-3" },
    "error":     { "pattern": "solid",   "color": "rose-4" },
    "banked":    { "pattern": "solid",   "color": "neutral-2" }
  },
  "updated": 1758067200.0
}
```

* `face` — a face id from `jarvis-visual-spec.json`. Absent or `null` leaves
  each client on its own default.
* `bindings` — state id to binding. **A state that is absent keeps the spec's
  default.** A client that has never been edited is not a client with no face,
  so a partial document is valid and normal.
* `color` — **absent** for the two patterns whose `kind` is `hue_sweep`
  (`rainbow`, `sweep`). They generate their own hues, so storing a colour
  there would imply it does something.
* `params` — the pattern's own knobs, absent when empty.
* `updated` — unix seconds at the write. The tie-break between two clients.

## The routes

### `GET /api/appearance`

Returns the document, or `{"available": false}` if the capability is not
installed — which the desktop reads as "hide the feature", per the API spec's
rule for a false capability.

### `POST /api/appearance`

Body is the part of the document the caller owns. **A key that is present
replaces its stored value; a key that is absent keeps it** (the merge rule
below). The server owns `updated` and stamps it.

```json
{ "ok": true, "updated": 1758067200.0 }
```

## Asking for a face, from either app (2026-10-26)

The owner asked to be able to *say* what face to wear, from the desktop or the
phone. The storage and the live event were already here; what was missing was a
way to ask. It is one named choice in `jarvis_settings_registry.py`
(`ChoiceSetting("face")`), reached by the grammar `jarvis_quick.py` already
has for settings, and its setter calls `_appearance_set_face` in
`appearance.patch` — the same one write this page describes. There is **no new
route**.

Sentences it answers, typed or spoken, from either app:

| Say | What happens |
|---|---|
| "change your face to Spiral" | the face becomes `spiral` |
| "use the Orbit face" | `orbit` |
| "switch the face to the red panda" | `redpanda` (the spec's display name) |
| "make your face the accretion face" | `accretion` |
| "put the spiral face on" | `spiral` |
| "what face are you using?" | a read: "The face is Red Panda. The voice is separate and unchanged." |

* **No approval card.** This document is cosmetic (see the rules below), so a
  face changes at once, exactly as the Faces window's own pick does.
* **One key, one event.** `_appearance_set_face` sends `{"face": id}` and
  nothing else. The merge keeps the state colours, so a face asked for in
  chat cannot erase what the phone or the Faces window owns — and the
  `appearance` event carries the merged document, so the other app repaints
  without asking.
* **The voice does not change.** A face never changes the voice by itself; the
  answer says so out loud. The question "does this animal use its own voice?"
  is the Faces window's own offer, not something a chat turn answers for the
  owner.
* **A name this PC does not have is refused with the real list**, never
  guessed at. A PC with no `jarvis-visual-spec.json` refuses too ("the face
  cannot be checked and nothing was changed") rather than storing an id its
  renderer does not know.
* That list is the spec's own (`_appearance_faces()`), so a face added to
  `jarvis-visual-spec.json` can be asked for without editing any Python.

## Rules worth keeping

**Last write wins, key by key.** There is one owner and two of their devices; a
merge strategy would be machinery for a conflict that does not happen. The
desktop stamps `updated` locally too, so a server that ignores the field still
behaves. Two devices setting the SAME key within the same second still end
with one of them — that is the rule, not an accident.

**A partial write MERGES; it does not replace.** This is a correctness rule,
not a convenience, and it was a real defect before 2026-10-26: the write used
to replace the whole document, and three writers send three different shapes.
The phone sends `bindings` on every push and a `face` only once its owner has
picked one (`AppearanceStore.toSyncDocument` leaves a blank face out), so the
first colour change from a fresh phone wrote `face: null` and erased the face
the desktop was wearing. The desktop's own document has the same shape when no
face is chosen. Now an absent key keeps its stored value, and only the request
is validated, so a document already on disk that a newer spec would refuse
cannot make a colour change fail.

**Clearing is explicit.** Because an absent key now means "leave it alone",
forgetting something has to be said: `"face": null` (or `""`) clears the face,
and `"bindings": {}` clears every state binding so each client falls back to
the spec's defaults.

**Validate against the spec, and reject rather than clamp.** An unknown
`pattern` or `color` should be a 400 naming the offender. A server that
silently dropped a bad binding would leave the picker showing a choice that
is not in effect anywhere — the worst of the three outcomes.

**Nothing here is privileged.** This document changes how Jarvis *looks*. It
approves nothing, starts nothing and reveals nothing, so it needs no gate and
should never grow one. If a future field would change behaviour rather than
appearance, it belongs on a different route.

**Tolerate unknown fields in both directions.** The phone may write a key this
desktop build has never heard of, and vice versa. Refusing the whole document
over one field makes the older client unusable; the desktop's parser already
ignores what it does not recognise.

## Notify the other client

Optional, and worth it: publish an `appearance` event on `/api/events` when the
document changes, so a client that is already open repaints instead of waiting
for the next read. The desktop's stream already fans out unknown event kinds
harmlessly, so adding it breaks nothing that exists.
