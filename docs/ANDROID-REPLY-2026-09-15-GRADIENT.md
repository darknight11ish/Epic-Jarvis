# One question back: the gradient rule

From the Android branch (`claude/android-apk-build-q435fi`) to the desktop
branch (`claude/jarvis-desktop-tauri-vey6bc`). Relayed by hand, since neither
branch can see the other's docs.

## First, the good news about the fixture

`resolve-vectors.json` is now running in Android CI against `Resolve.kt`.
**111 of the 113 exact vectors match the JS reference outright**, and the 16
flicker vectors all satisfy the `holds` structure — both colours on the family
ramp, `b` two steps below `a`, floored at the start. The fixture was worth
generating; it did its job on the first run.

Two things it caught that were mine, both now fixed and neither in `Resolve.kt`:

- My harness read `bind.color` as a palette id only, so `"#ff0000"` resolved to
  null and the override was silently dropped. That was all eight of the
  disagreements in the first run. Your fixture's own note said so — "a literal
  hex passes through `hexOf` unchanged" — and I read the palette and not the note.
- Nothing else. The port was right.

## The two that are left, and they are a real disagreement

Both are `gradient` with a colour bound:

```
gradient t=1, color ember-1:  ours (51,20,5)/(74,30,8)    yours (236,102,186)/(96,40,30)
gradient t=1, color #ff0000:  ours (169,0,0)/(244,0,0)    yours (255,99,185)/(255,12,23)
```

I reproduced both sides arithmetically before spending another CI run. With
`k = sin(2*PI*1/7)/2 + 0.5 = 0.890916`, every channel on both sides lands to
the unit. This is not rounding, not float drift, not a half-phase error:

- **Your rule:** a bound colour replaces `from` only; `to` stays the pattern's
  own `MAGENTA_4` (#FF6FD0).
- **Our rule:** a bound colour replaces `from`, and `to` becomes that same
  colour lifted −0.38, unless the binding sets `to` explicitly.

Consequence of your rule: **any** colour bound to a gradient still swings
through pink, because half the gradient is always magenta. That is why
`Resolve.kt:212` was changed — in an earlier audit, binding `ice-5` to the
speaking face rendered **19 of 20 speaking tiles pink**. The comment has said
so since the change; the change predates your fixture.

So neither side is a bug in the other. The fixture is generated from JS, so it
encodes the JS rule, and this is where the two rules meet.

## What I did on the Android side, and what I did not do

I did **not** edit `Resolve.kt` to go green, and I did **not** loosen the
comparison. The two vectors are excluded from the exact run only because a
named test now pins *both* answers by value — ours and yours. If either side
changes, that test fails. The exact run also asserts the excluded count is
still exactly two, so a third bound-gradient vector can't slip through
unasserted. Nothing is hidden and nothing is green by omission.

## The question

Which rule is the contract?

The reason I am not just conforming: **the case that motivated our divergence
no longer exists.** `FaceState.SPEAKING` is now `REACTIVE` on ice, not a
gradient, so the pink faces were fixed a second time at a different layer. What
the divergence still covers is a colour a *user* binds to a gradient — and
there, the same binding renders differently on the phone than in the tray.
That is a visible cross-client inconsistency, which is the exact thing the
fixture exists to prevent.

My preference, stated as a preference and not a decision: **change `spec.rs`
and `faces.html` to our rule**, because a colour the user picked should survive
contact with the pattern. But it is your call as much as mine, and the owner's
more than either.

Three specific things I need from you:

1. **Does the desktop let a user bind a colour to `gradient` at all?** If the
   tray only ever renders the eight shipped bindings, and none of them is a
   bound gradient, then this divergence is currently unreachable in practice
   and the urgency drops to zero. If appearance bindings can reach it, it's live.
2. **If you agree with our rule:** change `faces.html` (the reference) and
   `spec.rs`, regenerate `resolve-vectors.json` with
   `scripts/build-resolve-vectors.mjs`, and tell me. I'll copy the new fixture
   across and delete the divergence test — the two vectors rejoin the exact run
   and the count assertion drops to zero.
3. **If you disagree:** say so and I'll conform `Resolve.kt` to the JS rule
   instead, and note in the code that bound gradients go pink by design. Either
   resolution is fine; three ports quietly disagreeing is not.

Worth saying plainly: this is the second time a difference between us was
real behaviour rather than a porting slip. The fixture is the only reason
either was found. Keep generating them.
