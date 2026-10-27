# `/api/appearance` — the one route the face picker needs

> **Written, tested and ready to apply:** `backend/appearance.patch`. This page
> is the contract; that patch is the implementation of it for `jarvis_hud.py`,
> with nineteen checks in `backend/test_appearance.py` (the merge is in there).

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
below). `face` and `bindings` are the only fields a client sends that matter;
the server owns `updated` and stamps it.

```json
{ "ok": true, "updated": 1758067200.0 }
```

## Rules worth keeping

**Last write wins, key by key.** There is one owner and two of their devices; a
merge strategy would be machinery for a conflict that does not happen. The
desktop stamps `updated` locally too, so a server that ignores the field still
behaves. Two devices setting the SAME key within the same second still end with
one of them — that is the rule, not an accident.

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

**Two narrow ways a save can still lose a half, recorded rather than claimed
away.** The merge covers the ordinary partial document, not two rarer cases.
The server is a `ThreadingHTTPServer` and the read-modify-write has no lock, so
two saves that overlap inside the server can both read the same old document
and the second write can carry the first one's stale other half. And
`_appearance_view` cannot tell a corrupt file from one that is unreadable just
now, so a save made in that moment merges onto an empty document and can lose
the rest. Both were found by the independent review of 2026-10-26; closing
them means a `threading.Lock` and a "could not read just now" refusal, and is
the obvious next change if either is ever seen. The windows are small: one
owner, two devices.

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
