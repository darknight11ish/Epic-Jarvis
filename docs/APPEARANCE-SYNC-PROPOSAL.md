# Proposal: one route so the phone and the desktop look the same

**Status:** proposal. Nothing in `jarvis-client` implements this yet, and nothing
will until the backend does. Written because the alternative — inventing the
endpoint client-side and hoping — is exactly how `jarvis-android` ended up
speaking a protocol no server implements.

## The problem

The two ends already share a vocabulary. `jarvis-visual-spec.json` v1 defines
the faces, the 45 palette colours, the 12 patterns and the 8 states, and both
renderers were built from it. Pick `orbit` on the phone and `orbit` on the
desktop and they genuinely agree.

What is missing is any way to say so. All 20 endpoints the client knows are
about *what Jarvis is doing*; none are about *what Jarvis looks like*, and
`POST /api/config` answers 501 by design. So appearance is per-device, and
`AppearanceStore`'s own doc-comment has said this the whole time:

> Bindings are the part that *should* sync eventually, because they are a
> shared vocabulary rather than a taste: a phone whose `thinking` is violet
> while the desktop's is green has learned a private language.

That is the real argument. The face is taste. The **bindings are meaning** — if
the two ends disagree about what colour "thinking" is, the owner has to hold two
mappings in their head, and the visual language stops being a language.

## The route

```
GET  /api/appearance    -> 200 Appearance
PUT  /api/appearance    -> 200 Appearance   (the stored result, not the request)
```

Authenticated exactly like everything else: `X-Jarvis-Token`, plus
`X-Jarvis-Client`. **No new secret, no new permission, no new attack surface
beyond the one that already exists.** Appearance is not an action, so it does
not go through the approval gate — but see *Clamping*, which is the one place
this is not purely cosmetic.

### Body

```json
{
  "spec": "jarvis-visual",
  "version": 1,
  "revision": 7,
  "updated_at": "2026-09-14T21:40:00Z",
  "updated_by": "phone",
  "face": "orbit",
  "theme": "midnight",
  "bindings": {
    "idle":      { "pattern": "breathe", "color": "ice-3" },
    "listening": { "pattern": "solid",   "color": "ember-4" },
    "thinking":  { "pattern": "sweep",   "color": "azure-4" },
    "speaking":  { "pattern": "reactive","color": "ice-4" },
    "approval":  { "pattern": "pulse",   "color": "amber-4" },
    "standby":   { "pattern": "breathe", "color": "ice-2" },
    "error":     { "pattern": "pulse",   "color": "rose-4" },
    "banked":    { "pattern": "solid",   "color": "verdant-3" }
  }
}
```

Every value is an id from the shared spec: `face` from `/faces[].id`, `pattern`
from `/patterns[].id`, `color` from `/palette/colors[].id`, and the binding keys
are exactly `/states[].id`. Nothing here is free text, so both ends can validate
without agreeing on anything new.

`revision` is a monotonic integer the **server** owns. Clients never set it.

## The four things that will go wrong, and what to do about them

### 1. Two devices editing at once

`PUT` carries the `revision` the client last saw. If it does not match, the
server rejects with **409** and returns the current appearance. The client
shows what the other end chose rather than overwriting it.

This matters more than it looks. Without it, opening the appearance screen on a
phone that has been in a pocket for a week silently reverts a desktop change,
and the owner has no idea why their theme keeps coming back.

### 2. The other end cannot render it

The phone has **6 of the 20 faces**. It will be handed `tokamak` sooner or later.

The rule: **fall back, and say so.** Render the default face, and show a line
naming what was asked for and that this device cannot draw it. Never silently
substitute — a phone quietly showing `arc` while the desktop shows `tokamak` is
the same private-language problem in a new place, and it is worse than an error
because it looks like it worked.

`GET` should therefore also return what the *asking* client can use, so the
phone can grey out faces it cannot draw in the picker instead of offering them:

```json
"renderable_by": { "hud": ["...all 20..."], "phone": ["...the 8 in Faces.all..."] }
```

**This cannot be keyed on `X-Jarvis-Client`, and the first draft of this
document said it could.** Both clients send the literal string `hud` — the
desktop because it is the HUD (`commands.rs`, `JARVIS_CLIENT`), the phone
because the server's origin check runs before the token check and refuses a
request with no `Origin` unless that header marks it first-party, and a native
client has no `Origin` (`JarvisApi.CLIENT_VALUE`, which says exactly this).
The header is load-bearing for CSRF and carries no identity: changing the
phone's value to `phone` would get it 403ed before its token was read.

So this needs one of two things first, and the choice belongs to whoever
changes the backend:

- the origin check accepts a request with no `Origin` on the token alone, at
  which point `X-Jarvis-Client` is free to mean what it says; or
- the answer is keyed on the **pairing token** rather than a header — which is
  the more defensible design anyway, because the token is the only thing in the
  request the server itself issued.

Until then the phone should filter `renderable_by` client-side against
`Faces.all`, and the server should treat any face id it is handed as valid.

The face list is also written here as a count for a reason: the earlier draft
hard-coded six ids, the phone now renders eight, and a hand-maintained list of
another component's contents is the thing in this system that has rotted most
reliably.

### 3. Clamping — the one part that is not cosmetic

**The server must clamp animation parameters to `/limits/flash` and must not
trust the client to have done it.**

The spec is blunt that these are hard limits rather than advice: the face fills
well over a quarter of the visual field, so the small-area exemption does not
apply. `max_transitions_per_s: 3`, `min_luma_delta: 0.10`, `strobe_max_s: 2.0`,
`flicker_rate_hz_max: 1.3`.

Today every path to a colour on both ends goes through a governor, and the
limits hold. The moment one device can push animation parameters to another,
that stops being true unless the receiving end re-checks — and the desktop HUD
is a much larger area of visual field than a phone. A client with a bug, or an
older client, must not be able to make the desktop strobe.

So: clamp on write, return the clamped values, and let the client see that its
request was altered. This is the only reason this route needs any judgement at
all rather than being a dumb key-value store.

### 4. Live update

Both ends should change together, not on next launch. Emit an `appearance` event
on the existing `/api/events` SSE stream when the stored value changes:

```
event: appearance
data: {"revision": 8, "face": "orbit", ...}
```

Clients already hold that stream and already handle unknown event types, so this
costs one event type and no new connection. Without it, "change it on the phone
and the desktop matches" means "matches after you restart the desktop", which is
not what was asked for.

## What the client does once this exists

Small, and mostly deletion:

- `AppearanceStore` gains a remote tier: server value wins on connect, local
  edits `PUT` and adopt the response (including any clamping).
- The appearance screen loses the "per device, and the picker says so" caveat,
  and greys out faces this device cannot draw.
- A stale or unreachable desktop keeps the last known appearance and says the
  value may be out of date — the same three-state honesty the wake-word control
  already uses, because "this is what the desktop looks like" and "this is what
  it looked like when I last reached it" are not the same claim.

## What this deliberately does not do

- **No arbitrary theming.** Ids from the shared spec only. No client-supplied
  hex colours, no uploaded assets, no CSS. The palette is a fixed vocabulary and
  that is what makes both ends able to validate it.
- **No per-device overrides in v1.** If it turns out the phone genuinely wants a
  different face from the desktop while sharing bindings, that is a second
  revision — and bindings are the half that actually needs to agree.
- **No new authentication.** Same token, same header.
