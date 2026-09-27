# Animal faces ("critters")

Jarvis has had twenty faces: animated pictures that show what it is doing.
They are all instruments - rings, orbits, a drum skin. The **red panda** is
the first animal: a small cartoon character that sleeps, listens, thinks,
talks and waves.

The owner's choice, 2026-09-27: all three animals Gemini suggested (red
panda, pygmy owl, sea otter), **panda first**. The owl and the otter are
built only after the owner has seen a working panda and says go.

![The red panda in all eight states](critters/redpanda-states.png)

*Top row: idle, listening, thinking, speaking. Bottom row: waiting on you
(approval), asleep (standby), confused (error), dozing (banked). Rendered
by the desktop's own shader. The orb and rim colours are the default
colours for each state; the owner's own colour choices replace them.*

## How to switch to it

- **Desktop:** open the Faces window, click the Red Panda card, then choose
  it as Jarvis's face - the same as picking any other face. The widget, the
  floating face and the HUD all show whatever face is chosen there.
- **Phone:** Appearance, then pick Red Panda from the faces.
- The choice is shared through the backend like any other face, **once
  your PC has the updated `jarvis-visual-spec.json`** (see "One thing to
  check on the PC" below).

## What each state looks like

| Jarvis is... | The panda... |
|---|---|
| Idle | Sits holding its orb in its lap and looks slowly round the room. Blinks every few seconds, breathes, swishes its tail. In the desktop's Faces window it also turns to follow the mouse pointer for a few seconds after it moves over the face (the widget, HUD and floating face have no pointer, so there it does not). |
| Listening | Perks both ears up, tilts its head about 15 degrees and leans in. Your voice makes its ears twitch and the orb glow brighter. |
| Thinking | Lifts the orb up in both paws and gazes into it. The orb glows its brightest. |
| Speaking | Its mouth opens and closes with Jarvis's voice, and it nods and gestures with one paw. |
| Waiting on you (approval) | Looks straight at you with its eyebrows up, and waves. |
| Asleep (standby) | Eyes shut, head drooped, ears down, tail wrapped round, breathing slowly. The orb dims to an ember. |
| Something went wrong (error) | Tilts its head, one ear droops, squints and scratches its head. |
| Keeping things for later (banked) | Dozing with half-closed eyes. |

A change of state melts from one pose to the next over about half a second.
It starts from what was actually on screen: leaving "speaking" the mouth
closes over that half second rather than at once, and a second change
arriving mid-melt carries on from the half-finished pose. Three changes
inside the same half second can still show a small jump. The approval clock, the error shake and the dimming that
every face gets still happen on top.

**Colour.** The panda keeps its own fur colours in every state. The colour
you choose for a state goes to **the orb it holds** - which is also a real
light, so your colour shows on its paws and chin - and the second colour is
**the rim light** round its fur. Repainting the whole animal per state would
look like a different animal each time, not the same one changing its mind.

## How it is made

There is **no 3D model file**. The panda is described as maths: every body
part is a simple rounded shape (the head is a squashed ball, the tail is five
tapered tubes), and the shapes are blended together with a "smooth minimum",
so the cheeks melt into the head and the arms into the body like soft felt
instead of meeting at a seam. That is what makes it look fluid, and why it
can bend into any pose: a pose is only new numbers for where each shape sits.

The graphics card then works out, for every pixel on screen, what a ray from
your eye would hit (this is called ray-marching - the same way the Nucleus
face is drawn). It adds soft shadows, shading in the creases, a warm glow
where light passes through fur, and the orb's light.

Three files make it, and each app gets its copy from the same place:

| File | What it does |
|---|---|
| `jarvis-desktop/critters/redpanda.sksl` | **The shader** - the shapes, fur colours and lighting. One file for both apps. |
| `jarvis-desktop/src/critter-pose.js` | **The pose** on the desktop: where the head, ears, eyes, paws, tail and orb are on each frame. |
| `jarvis-client/.../face/CritterPose.kt` | The same pose maths on the phone, line for line. |

`tools/gen_critters.py` copies the shader into both apps (the desktop and the
phone use slightly different shader languages; the differences are only in
names) and records the desktop's pose answers at 44 moments. The phone's
`CritterPoseTest` fails if its answers differ - so the two apps cannot drift
apart without a red build. After changing any of the three files:

```
python3 tools/gen_critters.py
```

The desktop test `tests/faces.mjs` fails if you forget.

### On a PC without a working graphics card

If WebGL is blocked, or the graphics card turns out slower than drawing by
hand (the Faces window measures this and switches by itself, the same as for
Nucleus), the desktop draws a **flat sticker** of the same panda in the same
pose instead. It still tilts, blinks, perks its ears, holds its orb and
sleeps; it loses the lighting. The phone needs no fallback: its shader
support (Android 13) is guaranteed by the app's minimum Android version.

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
  Jarvis settings folder, copy the new one over too - otherwise choosing the
  panda on one device will not reach the other, and the desktop's start-up
  check will report that its copy and the backend's differ.
- **Cost.** The panda is by far the most expensive face to draw: measured
  through Skia (the engine Android draws with), **10 to 12 times Nucleus's
  work per pixel**. (An earlier version of this page said "a little more
  than Nucleus" - that was a guess, and wrong.) Most of it (about 80%) is
  finding the panda's surface for each pixel; the shadows are the rest.
  - **On the phone it is drawn at lower resolution and enlarged**: half the
    width and height at the High quality tier - a quarter of the pixels,
    measured at 3.9 times less work - and less again when Auto adjust steps
    down to Medium (0.4) or Low (about 0.31). Max, chosen by hand, uses 0.75.
    Because the panda is soft and rounded, the enlarged picture differs from
    the sharp one by about 1 part in 255 on average; the shader feathers its
    outline so the enlarging does not show as steps. A software canvas (a
    bitmap snapshot) still draws it at full size.
  - **On the desktop** it is drawn at full resolution; the Faces window's own
    speed check switches to the flat version if the graphics card cannot
    keep up.
  - **Not yet measured on a real phone.** Rough arithmetic for a Pixel 9 at
    the Large size said full resolution would have been choppy while
    listening, thinking and speaking; a quarter of the work should bring it
    within reach, but only the phone itself can confirm that. If it still
    stutters or gets warm, say so - the next steps are a lower scale or a
    simpler shadow.
- **The phone makes about 90 small throwaway objects a frame** for the
  panda (its pose maths builds fresh number lists). Nucleus makes none. It
  is not measurable as slowness on its own, but it is more garbage than
  this app likes; worth tidying if the phone shows stutter with the panda.
- **Not yet tried on a real phone or a real graphics card.** It has been
  rendered through the phone's own drawing library (Skia, via skia-python)
  and through the desktop's WebGL in a browser without a graphics card, and
  the pictures match. The CI emulator launches the app with every face
  chosen, which catches a shader that will not compile on Android.

## Adding the owl and the otter (not started)

Each would be a new `.sksl` file beside `redpanda.sksl`, a new set of poses
in the two pose files, a face entry in the spec and one small face object in
each app - the generator and the tests already work per animal. Designs from
Gemini's notes:

- **Pygmy owl:** a round bean body, head that turns to follow the pointer,
  fluffs up and shuts its eyes to slits when asleep, tilts upside down when
  thinking.
- **Sea otter:** floats on its back, bobbing on an invisible water line;
  taps a glowing pebble on its belly when thinking; floats upright with its
  paws on its cheeks when listening.
