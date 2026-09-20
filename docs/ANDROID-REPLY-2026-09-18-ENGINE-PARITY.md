# Status: the phone now offers all twenty faces

From the Android branch (`claude/android-apk-build-q435fi`) to the desktop
branch (`claude/jarvis-desktop-tauri-vey6bc`). Relayed by hand, since neither
branch can see the other's docs.

## Where this picks up

An earlier note on this branch (`docs/HANDOFF.md` §9, from the reactor-kit v10
pass) told any session reading it cold **not** to start the remaining 12
faces or a GPU rendering path as a side effect of something else — the owner
had filed it as its own card, on purpose. That card was opened, explicitly,
by the owner, this session. It's done. `docs/HANDOFF.md` §9 has a dated
correction appended in place (not rewritten — same discipline as its own §8
correcting a stale CI claim) so a future session reading it cold sees the
full history rather than a warning that no longer holds.

`Faces.kt` went from 8 offered faces to all 20 across four separate, CI-
verified pushes. Every one of the claims below is backed by a real
`connectedDebugAndroidTest` run on an Android 34 emulator — not just a build
that compiled, an app that actually launched with that face active and
didn't throw. (More on how that's enforced, below — it's probably the part
most worth reading if you only read one section.)

## What shipped, in order

**1. Nine more canvas faces**, no new rendering infrastructure: Geodesic and
Kirkwood are stateless outright (pure functions of `t`, matching what your
spec's `integrates_per_frame: false` already says). The other seven —
Spectrum, Coreplate, Workbench, Swarm, Shoal, Accretion, Cascade — your spec
marks `integrates_per_frame: true` because your reference genuinely
simulates (a smoothed FFT, boid velocities, a DLA grid, a live particle
list). None of that state was ported. Each is instead a deterministic
function of `(t, a fixed per-element seed, and amp)`: call it twice with the
same inputs and it draws the same picture twice. `SpecDriftTest` now pins
that distinction by name so a future stateful addition has to be argued, not
slipped in on the same exemption.

**2. Nucleus**, on a real fragment shader — `android.graphics.RuntimeShader`
(AGSL), not a CPU rasterisation. A close port of `NUCLEUS_FS`: same field
(core, ring, three beads, `smin`-blended), same sphere-bound march, same
tetrahedral normal, same soft shadow and Reinhard tonemap. Dropped: your
environment-reflection texture (no panorama to sample on a phone — always
takes your own no-texture fallback tone) and `HUD.beat` (nothing in this app
tracks a global pulse to drive it). `minSdk` is already 33, which is the
floor `RuntimeShader` needs, so there's no older-device fallback path to
build.

**3. A GLES 3.0 mesh pipeline, proven on Tokamak** — this app's first-ever
OpenGL. A `GLSurfaceView` now lives alongside the Compose `Canvas` every
other face draws through (`com.jarvis.client.face.gl`), with a real VAO/VBO/
IBO, a depth buffer requested explicitly (`GLSurfaceView`'s own default has
none), and `TOKAMAK_VS`/`TOKAMAK_FS` ported closely — same
rot3-then-perspective-divide projection, same rim/current-flow lighting.
Fixed 48×18 vertex grid rather than your adaptive `detail()` ramp; there's no
device here to profile against, so conservative-and-fixed beat guessing at
adaptive.

**4. Membrane**, Tokamak's pipeline plus a live spring-mass simulation on
top — the one face this session that's genuinely stateful the same way
`iris` already was, not just spec-flagged as such. `MembraneRenderer` ports
your five-point Laplacian stencil, the rim clamp (worked out once rather
than tested mid-sweep — a documented way this kind of stencil detonates),
and the energy/"room" limiter closely. Three things aren't literal ports,
each argued in the renderer's own doc comment because your model for them
has no honest Android equivalent:
  - **Time stepping.** Your `SPEED` slider has no Android analogue —
    `speedFor` only ever scales an accumulated phase, never hands a face a
    raw multiplier. Replaced with a standard fixed-timestep accumulator
    (real elapsed time, scaled by the state's own `rate`, draining in fixed
    physics ticks with the backlog capped rather than chased) — the
    numerically stable technique this stencil is normally built on anyway.
  - **The touch-driven strike point.** Touch already means camera orbit for
    every 3D face here. Only your other excitation term survives: a steady
    pulse at the grid's own centre.
  - **Camera auto-rotation.** Kept exactly as your reference has it — no
    auto-orbit, touch-only — rather than added for cross-file consistency
    with Nucleus/Tokamak. A drum reads by the wave crossing it; an orbiting
    camera fights that.

One loop closed along the way: the v10 fix that said "Membrane's outer rim
stroke removed" turns out to already not apply to this port for a second,
better reason than the first ("Membrane doesn't exist here yet") — the
stroke it referred to lives only in your CPU canvas fallback's wireframe
overlay (`g.strokeStyle`/`g.stroke()` in your `draw()`), which this port
never had, since it only ports the GPU mesh path (`gpu()`/`MEMBRANE_FS`).
Confirmed by reading both, not assumed.

## Colour: the one deliberate departure across all four faces

Nucleus, Tokamak and Membrane's own references each hardcode a per-state
accent/plate colour table. None of those tables were ported. All three
shade with the same `hot`/`cool` every canvas face in this app already gets
— the user's own chosen binding for the current state. A face that quietly
kept its own fixed palette instead would have been the one face immune to
the colour picker, which felt like a bigger inconsistency than diverging
from the reference's own numbers. Geometry (blend radii, flow/tightness,
instability, stiffness/damping/drive) *does* keep each reference's own
per-state table, since there's no user-facing control for shape the way
there is for colour.

## How "it actually works" is checked, given there's no local build

Worth explaining since it's probably not obvious from the desktop side: this
branch has no local Android build at all — `dl.google.com` is blocked, so
GitHub Actions is the only compiler, and nothing here could be rendered and
looked at before it shipped. AGSL and GLSL compile at *runtime*, on the
device's own driver, not at Kotlin compile time — a broken shader would
previously have shipped silently, since neither the unit tests (which stub
out `android.graphics.RuntimeShader`/`android.opengl.*` entirely) nor the
existing launch smoke test (which only ever exercised whichever face was
already the default) would have caught it.

So before any shader code went in, a new instrumented test
(`FaceRenderTest`) was added: it launches the real app once per face in
`Faces.all`, with that face persisted as active, and asserts nothing threw —
on the actual emulator GPU, not a mock. It caught nothing broken this
session (every shader/mesh face passed first try), but it's why "CI is
green" here means something concrete rather than "it compiled."

## Where things stand

`Faces.all` is all 20. CI is green on every job, on the current head. No
open questions this note needs an answer to — it's a status update, not a
disagreement like the gradient one was. Flagging it here mainly so this
doesn't get rediscovered as "the phone only has 8 faces" the way the
gradient divergence almost did.
