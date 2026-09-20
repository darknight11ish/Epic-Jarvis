# The shared look — what the phone and the desktop must agree on

For the desktop thread. This is what the Android client now implements, written
as the contract rather than as a description of one client, so the two can be
built against the same thing rather than compared afterwards.

**The test for whether something belongs here:** if changing it in one client
without the other produces a **wrong statement** rather than a worse-looking
one, it is shared. "Approval is amber" is a statement. "The card corner is 14
rather than 12" is not.

---

## 0. The state of things

Before any of this: **there are four colour systems in play, not two.** The
desktop alone ships three token vocabularies across four surfaces —
`--accent`/`--cyan`/`--ice`, `--warn`/`--gold`, `--bad`/`--crit` — and the
phone's tokens were transcribed by eye from `jarvis_hud.html`, three of them a
digit off.

So "make them match" currently has no target to match *to*. The desktop needs
to consolidate internally first, and the spec's palette is the only defensible
target, for one concrete reason:

```css
html[data-state="approval"] .reactor-ring { stroke: var(--warn); }
html[data-state="error"]    .reactor-core { fill:   var(--bad);  }
```

The spotlight's miniature reactor takes its **state** colours from **chrome**
tokens. With `--warn: #ffc860` against the spec's `amber-4 #ffb648`, the two
faces already disagree about what Jarvis is doing — slightly, and by
construction rather than by accident. The moment anyone presses Randomise they
disagree completely, because Randomise moves the phone's amber and `--warn`
stays put.

**A state colour must never come from a chrome token, on either client.**

---

## 1. Three classes of colour

Every colour in either app is exactly one of these. The class decides who owns
it and is not negotiable per-theme.

### Class A — the theme's, freely

Surfaces, text tiers, hairlines, scrim, shadow. Nothing here is read by the
face or compared across devices.

### Class B — the theme's, constrained

`ok`, `warn`, `bad`. A theme picks the **step**; the **family** is fixed:
verdant, amber, rose. Forced, because `randomise.state_rules` pins approval and
error to those families and refuses to move them — *"a green alarm is a design
you have to explain."* A theme must not be able to break a rule the randomiser
cannot.

Two tiers, because a light theme needs them and a dark one can alias them:

- `*Ink` — for **text**, target 4.5:1.
- `*Mark` — for **icons and fills**, target 3:1.

On white, step 2 has the better hue separation (ok/bad 9.8 ΔE to a deuteranope
against step 1's 7.5) but `amber-2` reaches only 4.39:1, failing AA for text;
step 1 clears text contrast easily and its separation collapses to 7.9. So hue
carries the mark tier, where 3:1 is the bar, and words carry the ink tier,
where a label is present and hue was never doing the distinguishing. On dark
themes both are step 4.

### Class C — nobody's but `resolve()`'s

Every state colour, and the chrome accent.

---

## 2. The accent is derived, not chosen

```
accent(theme) = legibility_floor(theme, resolve(IDLE).a)
```

The chrome accent is the **idle state's bound colour**, walked along its own
family's steps until it clears the theme's contrast floor against `surface-1`.

This is the load-bearing idea. It means the chrome is a *function of the
bindings*, so re-roll idle to violet and the caret, the focus ring, the
streaming hairline and the selected tab become violet on **both** clients —
because both compute the same function from the same data. The chrome can never
disagree with the face, because the chrome has no opinion of its own.

**There is no accent picker, on either client.** The settings surface shows the
derived accent read-only with the words "follows your Idle colour", and tapping
it goes to the bindings editor. That is how you stop someone adding a free
accent picker in six months.

The walk stays **inside the family**. Walking toward white desaturates the hue,
and the hue is the thing the user bound; a step keeps it recognisably the same
colour and lands on a value the spec already sanctions.

Android's implementation is `accentFor()` in
`jarvis-client/.../ui/theme/Chrome.kt` — about thirty lines.

---

## 3. The well

The reactor's ground is the **one** theme token the face may read, and it
applies identically to all faces. `renderer.background_why` pins a single
ground because each face used to paint its own and showed as a differently
tinted rectangle in every gallery; the *intent* is cross-face consistency, not
that one hex.

**It must stay essentially black — Y ≤ 0.01.** Not a style rule. Faces
composite additively (`globalCompositeOperation 'lighter'`, and the bloom
sprite too), so on a light ground the glow saturates and the reactor is not
dim, it is **absent**. And `dim_rule` blends *toward* the background rather
than multiplying toward zero, so a white well makes standby and banked dim
toward white, where they read as "disabled" — the opposite of "something is
waiting".

This is why a fully light theme is not buildable and why the phone's Daylight
theme is light **chrome with a dark inset well**: a dark gauge face in a light
dashboard, which is what real instruments do. The desktop should do the same
rather than shipping a light theme that erases the reactor.

---

## 4. Precedence — currently inverted between the two

The desktop tray has this right and the phone did not. It should be in the spec
rather than a comment in `tray.rs` and a different `when` block in Kotlin.

```
error > approval > activity(listening|thinking|speaking) > banked > standby > idle
```

Plus two rules that were only ever in prose:

- **`power: quiet` maps to `standby`**, not to idle. Leaving it on idle says
  "ready to talk" about a machine that will not.
- **A transport failure is NOT `error`.** The spec's error face is a reversed
  motion with a hitch and a shake; showing it because the phone left Wi-Fi says
  Jarvis is broken when the network is. Hold the previous state for a grace
  window keyed on *time since the link dropped* — not on which enum a retry
  loop is in — and let the link bar carry the news in words.

Approval sits above banked because they are **separate queues**, so
`banked == true` with something pending is reachable, and when it happened the
phone rendered a stopped grey disc: the state that exists to pull the eye
suppressed by the state that exists to be ignored.

---

## 5. Rule 1, which Android was skipping

```js
const q = Object.assign({}, P.params, bind.params || {});
```

The pattern's own params are the base; the binding overrides key by key. The
desktop ports this literally. Android carried a *kind* and one generic default
set shared by all twelve patterns, so `sweep` and `rainbow` — the same kind,
different params — were the same pattern, and a bound sweep rendered as a full
rainbow.

**A binding must carry the pattern, not just the kind.** Both clients now do.
Measured divergence before the fix reached 209/255 on a channel.

Note `strobe` names its two colours `a` and `b`, not `color`/`to`, and its
`period_s` floor of 0.4 is a safety limit rather than a preference.

---

## 6. The sentences that are not paraphrasable

Six strings where a rewording is a behaviour change. They should live in the
spec, keyed, and be rendered verbatim by both:

| key | text |
|---|---|
| `attention.count` | "N things waiting to be told" — **not** "N banked". `pending` counts the digest; `banked` is a separate boolean that is usually false. |
| `attention.mark_read_caveat` | "Marking read approves nothing." — in the same eyeline as the button. |
| `approval.reassurance` | "Nothing runs until you decide." |
| `mute.bound` | "There is no mute without an end." |
| `hold.too_late` | "Too late — that message has already gone. There is no unsend." |
| `rush.not_here` | "Nothing is approved from here. A latch is cleared where the scanner runs." |

---

## 7. Photosensitivity, once themes exist

`limits.flash` says `resolve()` is the only path to a colour, so a hand-written
binding cannot get past the governor. **A theme change is not a colour and does
not go through `resolve()`** — the governor measures the state colour and a
theme changes the surface underneath it. Theming is therefore the one new
photosensitivity hazard the feature introduces, on both clients.

Measured: every dark-to-dark swap is below threshold (all five dark grounds sit
in Y ∈ [0.0000, 0.0064]); anything to or from a light theme is ΔY ≈ 0.87 and
counts.

Five rules:

1. **Crossfade 500 ms at full display rate.** Not at `state_fps` — at 15 fps
   the peak per-frame step is 0.175 and at 2 fps it is a hard cut. A monotone
   ramp is one transition, not N; the budget is spent by *toggling*.
2. **500 ms dwell, enforced in the store and not the UI**, so a double-tap or a
   system light/dark flap cannot get past it. With the crossfade that is 1.0
   opposing transitions a second against a budget of three.
3. **Freeze `resolve()` during the crossfade**, or a pulse running underneath a
   ramping ground produces a composite luminance that oscillates while the
   ground rises — which *is* a reversal.
4. **Reset the governor after**, on every surface: its baseline is now measured
   against a different ground.
5. **Theme chips are static swatches.** `limits.flash.scope_why` records what a
   grid of live reactors did — twenty clocks fed one window, spent the budget
   on cross-surface transitions, then held one face's colour on another. One
   live preview at most, with its own governor.

And an automatic "follow the system" change must **defer** while the face is
listening, thinking, speaking, approving or erroring: the state crossfade and
the theme crossfade would compound, and a ground that changes mid-approval is
exactly the "is it telling me something?" ambiguity the waiting clock exists to
remove.

---

## 8. Scales, shared as scales rather than as numbers

18px on a 640px floating pane and 18dp on a 400dp phone are different
proportions of their container, and 14px at 60cm is not 14sp at 30cm. So share
the **names and relationships**, resolve the numbers per platform.

- **Radius:** `shell / card / chip / control`. `chip` is fully round — the
  "this is a label, not a control" signal, which the phone had nowhere and the
  desktop uses for route badges, note chips, approval targets and digest kinds.
- **Motion:** one easing token, `cubic-bezier(0.22, 1, 0.36, 1)` — Compose's
  `CubicBezierEasing(0.22f, 1f, 0.36f, 1f)` — and three durations
  (`micro / enter / state`) with a documented per-platform multiplier. Touch
  wants faster acknowledgement than a pointer.
- **Type:** roles (`display / title / body / label / mono`) with weight and
  tracking per role. The kicker is uppercase and **tracked out**; at 11sp
  untracked uppercase reads as shouting rather than as a label. Mono is for
  machine-authored strings only — ids, hashes, paths, model names — never prose.
- **Reduced motion** is honoured on every surface. The desktop already does
  this on all three of its; the phone did it on none, which was the worse gap
  because the phone is where the most motion-heavy thing in the product lives.

---

## 9. ok and bad are never distinguished by colour alone

`verdant-4` and `rose-4` are 67.7 ΔE apart normally and **8.2** apart to a
deuteranope. Simulated they are nearly the same beige — `#cbc4ac` against
`#b9ae83`, differing by 1.2 on the red-green axis, where the original
difference was 99.7.

So every affirmative/destructive pair needs a second channel. Android uses
**shape**: the affirmative is filled, the destructive is outlined, and the two
remain distinguishable with the colour removed entirely. A check glyph against
a cross glyph would do as well. Luminance alone is too weak at a glance.

This is the same conclusion the spec already reached about listening versus
approval, applied one layer up into the chrome.

---

## 10. What each client keeps

| Desktop | Phone |
|---|---|
| Window management, transparency, always-on-top | Foreground service, notification channels, boot receiver |
| Tray icon rasterisation, quickbar, widget geometry | Swipe-to-approve and its `swipe_ok` gate |
| Keyboard shortcuts and `kbd` rendering | Biometric gate, Keystore token handling |
| Markdown renderer, diff colouring | Compose draw implementations of its six faces |
| The 14 canvas + 3 shader faces the phone skips | Density conversion, 48dp touch minimums |
| Backend supervision UI, the memory graph | Pairing, tailnet discovery |

Two things stay per-device on purpose: **chrome theming** (a phone is used
outdoors in daylight; an overlay bar floats on a screen in a room) and the
**face selection**, which should sync only as a *suggestion* — the phone
renders six of twenty and a desktop selecting `tokamak` must not blank it.

**The bindings should sync**, when there is a route for it. They are not a
preference, they are a shared vocabulary: the argument in `spec.rs` that a tray
with a hardcoded colour *"disagrees with the face about what Jarvis is doing,
which is worse than no tray colour at all"* does not stop at the machine
boundary. There is no endpoint today — `POST /api/config` is 501 by design and
none of the 38 routes reads or writes a preference — so both clients should
**store locally and say in the UI that it is per-device**. Do not fake sync,
and do not block the picker on the endpoint.

What syncing would need, when it exists: `GET`/`PUT /api/ui/bindings` shaped
exactly like `states[].default` plus a `face_id`, last-writer-wins on a
monotonic version, a `ui_prefs` event kind, and a `capabilities.ui_prefs` flag
so both clients hide the picker on a backend that lacks it.

---

## 11. Corrections the desktop owes

- `style.css`: `--ok: #3ddc97`, `--warn: #ffc860`, `--bad: #ff6b7a` are not
  `verdant-4` / `amber-4` / `rose-4`. The spotlight is the most-used surface
  and its approval amber and error rose are both off-palette.
- `jarvis_hud.html`: `--crit: #ff6b5e` is a fourth error red.
- `--accent: #38f0ff` is 7.1 ΔE from `ice-4`.
- The `html[data-state=…]` rules in §0 must read a state colour, not a chrome
  token.

## 12. Corrections Android already made

Listed so the desktop does not port the old values: `Void #05070B` was neither
`neutral-1` nor `renderer.background`; `Ink #DBE7F2` was two off `neutral-5`;
`Line #17293A` was 1.65 ΔE from the HUD's. All three now come from the
generated palette. Standby breathed at 11 s against the desktop's 4.5.
