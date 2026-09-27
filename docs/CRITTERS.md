# Animal faces ("critters")

Jarvis had twenty faces: animated pictures that show what it is doing, all
of them instruments - rings, orbits, a drum skin. Now it also has **three
animals**, small cartoon characters that sleep, listen, think, talk and
wave: a **red panda**, a **pygmy owl** and a **sea otter**.

The owner's choice, 2026-09-27: all three animals Gemini suggested, panda
first; the owl and the otter once the panda worked (go-ahead given the same
day).

## How to switch to one

- **Desktop:** open the Faces window, click the Red Panda, Pygmy Owl or Sea
  Otter card, then choose it as Jarvis's face - the same as picking any
  other face. The widget, the floating face and the HUD all show whatever
  face is chosen there.
- **Phone:** Appearance, then pick the animal from the faces.
- The choice is shared through the backend like any other face, **once
  your PC has the updated `jarvis-visual-spec.json`** (see "One thing to
  check on the PC" below).

## The three animals

In each picture, top row: idle, listening, thinking, speaking. Bottom row:
waiting on you (approval), asleep (standby), confused (error), dozing
(banked). Rendered by the desktop's own shader. The orb and rim colours are
the default colours for each state; the owner's own colour choices replace
them.

### Red panda

![The red panda in all eight states](critters/redpanda-states.png)

| Jarvis is... | The panda... |
|---|---|
| Idle | Sits holding its orb in its lap and looks slowly round the room. Blinks every few seconds, breathes, swishes its tail. |
| Listening | Perks both ears up, tilts its head about 15 degrees and leans in. Your voice makes its ears twitch and the orb glow brighter. |
| Thinking | Lifts the orb up in both paws and gazes into it. The orb glows its brightest. |
| Speaking | Its mouth opens and closes with Jarvis's voice, and it nods and gestures with one paw. |
| Waiting on you | Looks straight at you with its eyebrows up, and waves. |
| Asleep | Eyes shut, head drooped, ears down, tail wrapped round, breathing slowly. The orb dims to an ember. |
| Something went wrong | Tilts its head, one ear droops, squints and scratches its head. |
| Keeping things for later | Dozing with half-closed eyes. |

### Pygmy owl

![The pygmy owl in all eight states](critters/pygmyowl-states.png)

A round owl on a branch, with huge yellow eyes. Owls have no hands, so its
orb floats beside it.

| Jarvis is... | The owl... |
|---|---|
| Idle | Surveys the room, turning its head well round - and now and then a quick look over its shoulder. Blinks, breathes. |
| Listening | Tilts its head right over and opens its eyes wide; your voice makes its head twitch. The orb comes close. |
| Thinking | The orb circles its head, passing behind it, and the owl follows it round with its head tipped over. |
| Speaking | Its beak opens and closes with Jarvis's voice. |
| Waiting on you | Looks straight at you and waves a wing. |
| Asleep | Fluffs up round, sinks its head in, eyes shut to slits. The orb settles on the branch, dim. |
| Something went wrong | A hard head tilt, one eye squinting, wings half out, feathers ruffled. |
| Keeping things for later | Fluffed and half-lidded. |

### Sea otter

![The sea otter in all eight states](critters/seaotter-states.png)

An otter floating on its back in a small round pool, a glowing pebble - its
orb - on its chest. Rings spread across the water as it bobs.

| Jarvis is... | The otter... |
|---|---|
| Idle | Bobs and rocks on the water, looks about, and paddles its feet now and then. |
| Listening | Lifts and tilts its head, paws to its cheeks. |
| Thinking | Taps the pebble on its belly, watching it. |
| Speaking | Its mouth opens and closes with Jarvis's voice, and one paw gestures. |
| Waiting on you | Looks at you and waves a paw in the air. |
| Asleep | Covers its eyes with its paws and drifts. |
| Something went wrong | The pebble has slipped to one side; it squints and scratches its head. |
| Keeping things for later | Dozing with half-closed eyes. |

### What all three share

In the desktop's Faces window each animal also turns to follow the mouse
pointer for a few seconds after it moves over the face (the widget, HUD and
floating face have no pointer, so there it does not). Dragging turns the
camera round it, as for every 3D face.

A change of state melts from one pose to the next over about half a second.
It starts from what was actually on screen: leaving "speaking" the mouth
closes over that half second rather than at once, and a second change
arriving mid-melt carries on from the half-finished pose. Three changes
inside the same half second can still show a small jump. The approval clock,
the error shake and the dimming that every face gets still happen on top.

**Colour.** Each animal keeps its own fur or feather colours in every state.
The colour you choose for a state goes to **the orb** - which is also a real
light, so your colour shows on the animal - and the second colour is **the
rim light** round it. Repainting the whole animal per state would look like
a different animal each time, not the same one changing its mind.

## How they are made

There is **no 3D model file**. Each animal is described as maths: every body
part is a simple rounded shape (a squashed ball for a head, a tube for an
arm), and the shapes are blended together with a "smooth minimum", so the
cheeks melt into the head and the arms into the body like soft felt instead
of meeting at a seam. That is what makes them look fluid, and why they can
bend into any pose: a pose is only new numbers for where each shape sits.

The graphics card then works out, for every pixel on screen, what a ray from
your eye would hit (this is called ray-marching - the same way the Nucleus
face is drawn). It adds soft shadows, shading in the creases, a warm glow
where light passes through fur, and the orb's light.

The files, and each app gets its copy from the same place:

| File | What it does |
|---|---|
| `jarvis-desktop/critters/common_head.sksl`, `common_tail.sksl` | **What all three share**: the camera, the lighting, the orb and its glow, the soft outline, and the size-safe march. |
| `jarvis-desktop/critters/redpanda.sksl`, `pygmyowl.sksl`, `seaotter.sksl` | **Each animal's own part**: its shapes and its colours. |
| `jarvis-desktop/src/critter-pose.js` (+ `critter-owl.js`, `critter-otter.js`) | **The poses** on the desktop: where the head, ears, eyes, paws, wings, tail and orb are on each frame. |
| `jarvis-client/.../face/CritterPose.kt` (+ `OwlPose.kt`, `OtterPose.kt`) | The same pose maths on the phone, line for line. |
| `jarvis-client/.../face/CritterFaces.kt` | How the phone draws any animal (at reduced resolution - see "Cost" below). |

`tools/gen_critters.py` builds each animal's full shader (shared start +
the animal + shared end) and copies it into both apps - the desktop and the
phone use slightly different shader languages; the differences are only in
names - and records the desktop's pose answers for each animal at 44
moments. The phone's `CritterPoseTest` fails if its answers differ, so the
two apps cannot drift apart without a red build. After changing any of
these files:

```
python3 tools/gen_critters.py
```

CI runs `--check`, and fails if you forget.

### Adding a fourth animal

A new `.sksl` beside the others (it must supply `map`, `mapLite`, `partAt`,
`material`, `sparkle`, `stuckRay` and the camera constants - see `common_tail.sksl`), a
pose file on each side registering itself the way `critter-owl.js` and
`OwlPose.kt` do, a line in `tools/gen_critters.py`'s `ANIMALS`, a face entry
in the spec, and one `critterFace({...})` / one `object ... : CritterFace` in
each app. Then measure it: `python3 tools/shader_size.py`.

### On a PC without a working graphics card

If WebGL is blocked, or the graphics card turns out slower than drawing by
hand (the Faces window measures this and switches by itself, the same as for
Nucleus), the desktop draws a **flat sticker** of the same animal in the same
pose instead. It still tilts its head, blinks, holds its orb and sleeps; it
loses the lighting. The phone needs no fallback: its shader support
(Android 13) is guaranteed by the app's minimum Android version.

## What was used from Gemini's notes, and what was not

Used: the state mapping (loaf/sleep for standby, head perk and ear flick
for listening, the glowing orb for thinking, mouth synced to the voice for
speaking), a head tilt of about 15 degrees, soft "felt" materials with no
hard shine except glossy button eyes with a white sparkle, squash and
stretch for breathing, mouse tracking, and blinks.

**Not used: downloading ready-made 3D models** (Quaternius, KayKit, Kenney,
Sketchfab). Four reasons:

1. They need a full 3D engine: three.js on the desktop and something like
   Filament on the phone. That is two large new dependencies, drawn two
   different ways - the two apps would no longer show the same animal.
2. A rigged model bends at joints. The smooth-blended shapes here bend like
   felt, which is the "fluid" look asked for.
3. Every Jarvis face already runs on this system (state colours, flash
   limits, the approval clock, the reduced-motion setting, the GPU
   watchdog). A model would have needed all of that rebuilt around it.
4. Sketchfab's CC-BY models need a credit line kept with them forever;
   maths needs none.

## Things to know

- **One thing to check on the PC.** The backend refuses a face it has not
  heard of, and it learns the list from `jarvis-visual-spec.json` on the PC.
  If your backend reads that file from this repository (the usual setup),
  updating the repository is enough. If you ever copied the file into the
  Jarvis settings folder, copy the new one over too - otherwise choosing an
  animal on one device will not reach the other, and the desktop's start-up
  check will report that its copy and the backend's differ.
- **The phone's size limit - this crashed the first version.** Android
  compiles a face's shader in a strict mode that refuses any shader over a
  size of 100,000 (every operation counts 1; a loop counts its body once per
  step). The first panda was about four times over: **choosing it would have
  crashed the phone app**. The desktop, and the newer Skia used for checking
  on a PC, accepted it without complaint; GitHub's emulator test caught it
  before it reached a phone. The shader was rebuilt to fit (smaller shapes,
  32 march steps, a simplified panda for shadows) and now measures about
  55,000 by `tools/shader_size.py`, which counts the way Skia does. The owl
  (about 31,000) and the otter (about 38,000) were measured before they were
  ever pushed. CI runs that check on every push, so none of them can quietly
  grow over.
- **Cost.** Measured through Skia (the engine Android draws with), per
  pixel: the **panda about 4 to 5 times Nucleus's work**, the **owl about
  2.3 times** and the **otter about 2.8 times**. (The panda was 10 to 12
  times before its rebuild; an even earlier version of this page said "a
  little more than Nucleus", which was a guess, and wrong.) Most of it is
  finding the animal's surface for each pixel; the shadows are the rest.
  These timings wobble by a fifth or so from run to run.
  - **On the phone each animal is drawn at lower resolution and enlarged**: half the
    width and height at the High quality tier - a quarter of the pixels,
    measured at 4.3 times less work, so in total about what Nucleus costs - and less again when Auto adjust steps
    down to Medium (0.4) or Low (about 0.31). Max, chosen by hand, uses 0.75.
    Because the animals are soft and rounded, the enlarged picture differs from
    the sharp one by about 1 part in 255 on average; the shader feathers its
    outline so the enlarging does not show as steps. A software canvas (a
    bitmap snapshot) still draws it at full size.
  - **On the desktop** it is drawn at full resolution; the Faces window's own
    speed check switches to the flat version if the graphics card cannot
    keep up.
  - **Not yet measured on a real phone.** A few times Nucleus per pixel at a
    quarter of the pixels should land at or below Nucleus's own cost, but
    only the phone can confirm it. If it stutters or gets warm, say so - the next
    step would be a lower scale.
- **The phone makes about 90 small throwaway objects a frame** for an
  animal (its pose maths builds fresh number lists). Nucleus makes none. It
  is not measurable as slowness on its own, but it is more garbage than
  this app likes; worth tidying if the phone shows stutter with an animal.
- **Not yet tried on a real phone or a real graphics card.** Each has been
  rendered through the phone's own drawing library (Skia, via skia-python)
  and through the desktop's WebGL in a browser without a graphics card, and
  the pictures match. The CI emulator launches the app with every face
  chosen, which catches a shader that will not compile on Android.
