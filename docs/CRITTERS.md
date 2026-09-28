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
| Idle | Sits holding its orb in its lap. Looks at one thing, then another - its eyes move first and its head follows - and holds each look for a few seconds. Its weight shifts now and then; its tail swishes slowly, the swing running out to the tip. About every 20 seconds it does one small thing - most often a flick of its tail or an ear turning toward a sound before its head does; now and then a stretch (leaning back, paws out) or a scratch. |
| Listening | Perks both ears up, tilts its head about 15 degrees and leans in, its eyes on you. Your voice lifts its ears a little and makes the orb glow brighter. |
| Thinking | Lifts the orb up in both paws and gazes into it, glancing up and away now and then. The orb glows its brightest. |
| Speaking | Its mouth makes the shapes of the words it is saying (see "How the mouths talk" below). It leans in and talks with its eyes and, now and then, a nod, a paw lifted off the orb, or a tilt of the head - never two alike in a row, and never just as its eyes move to look somewhere. |
| Waiting on you | Sits up, leans in and looks straight at you, ears up, holding its orb up higher - and keeps still but for its breathing, slow blinks and its eyes' tiny movements. No wave: the question may be a serious one. |
| Asleep | Eyes shut, head drooped, ears down, tail wrapped round, breathing slowly; now and then a sigh. Nothing else moves. The orb dims to an ember. |
| Something went wrong | A still, concerned look: head tipped a little and lowered, eyes down, brows drawn, ears back a touch. |
| Keeping things for later | Dozing with half-closed eyes, blinking slowly; now and then its head sinks and it catches itself. |

### Pygmy owl

![The pygmy owl in all eight states](critters/pygmyowl-states.png)

A round owl on a branch, with huge yellow eyes. Owls have no hands, so its
orb floats beside it.

| Jarvis is... | The owl... |
|---|---|
| Idle | Its head does the looking: it turns to something and holds still there, the way owls do (up to about 20 degrees either way). Its weight shifts on the branch now and then. About every 20 seconds: most often a curious tilt of the head or a long slow blink; now and then a ruffle of its feathers or a wing lifted and folded back. |
| Listening | Tilts its head right over and opens its eyes wide, looking at you, its brows level. The orb comes close. |
| Thinking | The orb comes up its right-hand side, then circles its head - riding high over its brow in front, so it never crosses its eyes - and the owl tips its head a little and turns to follow it. Leaving, the orb goes round the side (or round the back), never across the face. |
| Speaking | Its beak opens with the words it is saying, showing the dark inside. Its eyes lead each look, the head following a little; now and then a nod, a small lift of a wing, a tilt - never two alike in a row. |
| Waiting on you | Draws itself up - sleek feathers, head a little higher - leans in and looks straight at you, eyes a little wide and brows level, still. No wave. |
| Asleep | Fluffs up round, sinks its head in, eyes shut to slits; now and then a sigh. The orb settles on the branch, dim. |
| Something went wrong | A still, concerned look: head tipped a little and lowered, eyes down, the V of its brows flattened (in this owl's drawing a raised brow steepens the V into a glare, so a lowered one reads as worried). |
| Keeping things for later | Fluffed and half-lidded, blinking slowly; now and then its head sinks and it catches itself. |

### Sea otter

![The sea otter in all eight states](critters/seaotter-states.png)

An otter floating on its back in a small round pool, a glowing pebble - its
orb - on its chest. Rings spread across the water as it bobs.

| Jarvis is... | The otter... |
|---|---|
| Idle | Floats and rocks gently with the water and looks about. About every 20 seconds it does one small thing: most often rubs its pebble, kicks its feet or rolls a little to one side; now and then washes its face (its pebble resting on its chest meanwhile). |
| Listening | Lifts and tilts its head, its pebble held in its paws. |
| Thinking | Taps the pebble on its belly in little bursts, watching it, and glances up now and then. |
| Speaking | Its mouth makes the shapes of the words it is saying. It keeps its pebble low on its chest and talks with its head - a nod, both paws lifting a little, a tilt. (Waiting on you holds the pebble up instead, so the two are easy to tell apart.) |
| Waiting on you | Lifts its head and holds its pebble up a little off its chest in both paws, toward you, forearms along its chest (held higher, the arm stood up and read as a raised hand), looking at you - still, floating more quietly. No wave. |
| Asleep | Covers its eyes with its paws, its pebble resting on its chest, and drifts, rocking less than when awake; now and then a sigh. |
| Something went wrong | A still, concerned look: head tipped a little, eyes lowered, holding its pebble. |
| Keeping things for later | Dozing with half-closed eyes, blinking slowly; now and then its head sinks and it catches itself. |

### What all three share

In the desktop's Faces window each animal also turns to follow the mouse
pointer for a few seconds after it moves over the face (the widget, HUD and
floating face have no pointer, so there it does not). Dragging turns the
camera round it, as for every 3D face.

A change of state no longer moves every part together. The eyes get there
first (about a tenth of a second), then the mouth and the head, then the
paws and the body (about half a second), and the loose parts - tail, ears,
wings - last, swinging a few percent past and settling back. The new
state's own movement starts at once; what settles is only the difference
from what was on screen, and it keeps whatever speed the old pose had, so
nothing jumps or suddenly changes speed. A change arriving mid-settle
carries on from the half-finished pose - even a quick change back
(speaking, something else, speaking again), and three or four changes in a
row: each app hands the pose its list of recent changes (up to six), and
the pose works back through them. Falling asleep is slower on purpose - the
head droops over about two seconds - and waking takes about one; dozing
off and rousing from a doze take about twice the usual time.

### How they move

The owner asked for the animals to move their bodies, calmly: an assistant
on a desk, not a busy mascot. What they do, and the limits they keep to:

- **Looking.** Each animal looks at something - often you - and holds that
  look for about 1.5 to 6 seconds before its eyes jump to something else.
  The head follows the eyes a moment later and turns only part of the way.
  Between looks the eyes make the odd tiny jump of their own. A look is
  always held at least 0.6 seconds. Blinks come every few seconds (about 12
  to 15 a minute), now and then a double blink, and a blink as the head
  swings far round. Each animal has its own timing, so side by side they do
  not blink or glance together.
- **Weight and sway.** The body settles into a new lean every few seconds
  and holds it - at most about 1.5 degrees (the otter's water rocks it up
  to about 3). The panda's tail swishes and
  the swing runs out along it to the tip; its ears swing a little behind
  the head when it turns.
- **Small happenings.** When idle, about every 20 seconds (never closer
  than 10) one animal does one small thing - listed in the tables above -
  easing in and settling out. The small ones (an ear, a tail flick, a
  tilt, a blink) come up most; the big ones (a stretch, a scratch, a ruffle,
  a face wash) about one time in eight each, and never the same thing twice
  in a row. Long quiet stretches are normal.
- **Talking.** While speaking, each leans in a little; its eyes lead each
  look and its head follows only a little (a twelfth of the look; the
  owl's, an eighth). It gestures in phrase-sized pieces: at most one nod,
  paw or wing lift, or tilt every two seconds, often none, never the same
  one twice running, and never within a second and a half of its eyes
  moving to look somewhere - so a gesture and a head turn never pile up.
  Measured: about 7 gestures a minute, one gesture-or-head-turn every 4 to
  5 seconds on average, and 1 to 2 percent of them less than 1.5 seconds
  after the one before. Nods are about 3 degrees.
- **The pointer** (the desktop's Faces window) is followed mostly with the
  eyes; the head turns only a little toward it, and the pointer's position
  is smoothed over a quarter of a second, so a quick sweep no longer swings
  the head round.
- **Asleep** only the breathing moves (and a rare sigh); **dozing**, the
  head sinks slowly and catches itself now and then.
- **Serious moments stay serious** (the owner's call, 2026-09-28).
  **Waiting on you** can be a risky decision - an email about to be sent -
  so there is no wave and nothing cute: an attentive look straight at you,
  held still. **Something went wrong** is a still, concerned look, with no
  head-scratching and nothing comic. Only breathing, slow blinks and the
  eyes' tiny movements (a few hundredths of the eye's reach, always at
  you) move - enough to read as alive, not frozen.

**Moving less: calm, serious and still.** Each pose takes three more
inputs, each a weight from 0 (off) to 1 (on). The apps ease each one over
about a second when it switches, so the animal never snaps into or out of
them; the mouth is untouched by all three.

- **Calm** - the desktop's "reduce motion" (the operating system's
  setting) and the phone's calm motion. The head takes less of each look
  (about 40 percent), the idle happenings and talking gestures stop, and
  the slow rhythmic movements - the head's wander, the weight shifts, the
  tail's swish, the otter's water, the owl's orb circle and tilt while it
  thinks - are smaller. Blinks and sighs stay. On the desktop an animal
  under reduced motion is still drawn 30 times a second (other faces drop
  to 10): its movements are already calmer, and at 10 they stepped.
- **Serious** - a crisis moment (the `wellbeing` event, docs/JARVIS-API.md
  section 38.1; the owner's words: "calm and plain"). A calm, attentive
  listener: no happenings, no gestures, no tilts (listening's tilt too), no
  wide playful eyes; slower, steadier looks, mostly at you; blinking and
  breathing. The apps end it themselves 900 seconds after the last "true"
  if no "false" arrives.
- **Still** - the owner's "Still" option, **"Keep the animal still"**, off
  unless chosen: on the PC in Settings -> Appearance -> "Face on this
  computer" (saved on that computer only, `jarvis.faceTuning` in its
  storage, and read by every face on it - the widget, the floating face, the
  HUD and the Faces window), on the phone in Appearance -> More options,
  under Motion (saved on the phone, `Look.stillAnimal`). No card: it only
  takes movement away. It sits calmly and only breathes and blinks: no
  looks led by the head, no gestures, no happenings, its eyes resting on
  you with only tiny darts. The owl's thinking orb still circles, in a
  small ring above its head, so thinking still reads as thinking. The other
  faces ignore it, and both switches say so.

**When more than one is on.** They are three weights on the same pose, not
three modes, so they combine rather than fight: each takes movement away
and none adds any. Serious takes away the most (no tilts, no wide eyes);
still takes away the looking around; calm makes what is left smaller. The
mouth follows the voice under all three. The Zs (below) are not movement of
the animal: Still keeps them; calm turns them into one still z; serious does
not change them (a crisis answer and standby do not happen together).

**The sleeping "Zs"** (the owner's call, 2026-09-28). While an animal sleeps
on standby - whether the schedule or you put it there - small letter z's
rise from beside its head: a new one about every 1.4 to 1.8 seconds, each
living 3.2 to 4 seconds, so two or three at a time. Each fades in, rises up
and a little outward (away from the head), sways gently, grows a little and
fades out. Where the head is high (the panda's) they go up and out on a
slant rather than into the top edge. They are in the colour bound to
standby (the neutral grey unless you chose another), lightened toward white
so they read on the dark ground beside the dimmed animal.

- **Never while Jarvis cannot be reached.** Then the face shows standby
  with the hollow ring alone - "not connected" is not "asleep". If the link
  drops while the animal sleeps, the Zs fade out in half a second, and come
  back when it returns.
- **Calm** (the desktop's reduced motion, the phone's calm motion): one
  still z beside the head instead, nothing drifting across the screen.
- **Screen readers** hear nothing more: the face already says standby.
- **Both apps draw the same Zs.** Where each z is, how big, how see-through
  and how tilted is one function of the clock in the pose code (`zs()` in
  `critter-pose.js`, `CritterPose.zs` on the phone), with every number in
  one table (`ZS` / `CritterPose.Zs`). `tools/gen_critters.py` writes the
  desktop's answers at 144 moments, and the table itself, into
  `critter-zs-golden.json`; the phone's `CritterPoseTest` fails if its copy
  differs. The letter is three strokes, not a font's "z", so it is the same
  shape in both. Drawn flat over the picture (the shader is at its size
  limit), on every animal surface: on the desktop every face page (Faces
  window, widget, floating face, HUD), on the phone Home and the Appearance
  preview. (The phone's "Floating Jarvis" is the app's icon with a status
  dot, not the animal, so it has no Zs.)

Each animal's pose code says where the Zs rise from and how much:

- desktop: `CritterPose.species[id].overlay(P, {yaw, pitch, zoom})` returns
  `{asleep, x, y}`;
- phone: `CritterPose.overlay(p, yaw, pitch, zoom)`, `OwlPose.overlay(...)`,
  `OtterPose.overlay(...)` return `[asleep, x, y]`.

`asleep` goes from 0 to 1 as it nods off (over a couple of seconds) and back
as it wakes: fade the Zs with it. `x` and `y` are a point a little above and
to one side of the head (the otter's: above its head, toward the picture's
left), carried with the head and the breathing, in the shader's own screen
units: 0 at the middle of the picture, 1 at its edge, y UP. To pixels: on
the desktop, `px = W/2 + x * min(W, H)/2`, `py = H/2 - y * min(W, H)/2` for
a W x H canvas; on the phone, `px = cx + x * 2r`, `py = cy - y * 2r` (r is
the face radius; the animal is drawn over the 4r square round the centre).
Pass the same yaw, pitch and zoom the shader gets (uYaw, uPit, uZoom) so the
point follows the camera when the face is dragged round.

Measured (2026-09-28, the comfort review's own harness, which drives the
pose exactly as the desktop does): over half an hour of idle, the body
tips at most 1 degree (owl), 2.9 (otter, the water) and 3.4 (panda - only
during a stretch; 1.4 otherwise); the top of the body travels at most 2
percent of the animal's height (panda 2.1, owl 2.0, otter 1.8 - the otter
was 3.1); the head turns at most about 16 degrees (owl) and 11 (panda,
otter). In ten minutes of talk: speaking drops out and back in between
sentences 0 times (was 34), a look is held at least 0.15 to 0.45 seconds
even across a change of state (was 0.08), and with the pointer sweeping the
Faces window the head turns at most about 140 degrees a second (was over
1,200). Nothing big moves faster than three times a second. The tests in `CritterPoseTest` hold some of this
in place: no change of state jumps, asleep stays still, the happenings stay
rare and apart and never the same kind twice running, a look is held at
least 0.6 seconds, the otter's speaking and waiting look different, calm
turns the head less, serious has no tilt, still keeps the head still and
the eyes on you, switching an option eases, three changes inside a second
carry on smoothly, and the Zs show only asleep.

**The voice's loudness does not move the body.** It rises and falls with
every syllable, about four times a second, and a head that followed it
would bob like a toy. It still brightens the orb (and a little, the
eyebrows and the panda's listening ears). Following the real phrases of
the voice - nodding as a sentence lands - would need each app to hand the
pose a slower "phrase loudness" as well; that is written down as a later
step.

The motion is built on other people's published work, all under the MIT
licence and credited in THIRD-PARTY-NOTICES.txt: Daniel Holden's
Spring-It-On (how a change of state settles), Mika Suominen's TalkingHead
(hold-then-ease, the blinks, eyes leading the head), moeru-ai's airi (the
pauses between the eyes' small jumps) and pixiv's ChatVRM (how much of a
look the head takes). Everything is still worked out fresh each frame from
the clock - "random" means a hash of the time - so both apps draw the same
animal.

### How the mouths talk

Every spoken reply reaches the app as a whole sound clip before it plays.
The app works out from the sound, in advance, what shape a mouth would make
at each hundredth of a second (docs/LIPSYNC.md explains how), and while the
clip plays each animal is handed the shape for **what you are hearing at
that moment**. Three numbers make a shape, each 0 to 1:

| Number | Panda and otter | Owl |
|---|---|---|
| **open** | the jaw drops: the little smile under the nose stays as the upper lip, and a lower lip curves down away from it, with dark red inside and a muted pink tongue low down; the chin and the cream muzzle patch move down with it | the lower half of the beak drops (quickly at first, so half-open speech already shows a clear gap) and tucks back toward the face, showing the dark inside |
| **wide** ("ee", "s", teeth) | the corners pull out and up and the opening gets thinner, with a pale row of teeth under the upper lip | the lower half gets wider and flatter, and gapes a little less |
| **round** ("oo", "o", "w") | narrower, taller and pushed a little forward | a slightly smaller gape |

**One mouth, not two drawings.** For the panda and the otter the shut
mouth - a short stem down from the nose and a small smile - is the same
drawing as the open one: the same dark line runs round the whole opening,
so a slight opening looks like the line thickening and parting, and a wide
one like that line stretched round a big mouth. Closing on "m", "b" or "p"
is that mouth shutting, never a jump to a different picture (the first
version swapped a painted line for a separate oval, which flickered on every
closure). The drawing lives in `common_head.sksl` (`mouthPaint`), shared by
both animals; a hollow carved into the muzzle sits just inside it for depth.
The inside of a mouth (and of the owl's beak) is kept out of the rim light,
which used to light it a cold blue. The shapes blend smoothly at every
opening (checked in steps of 0.02 to 0.2, then up to 1, with wide and round)
by eye at 96 pixels and at 400.

**No sound, no mouth movement.** A typed answer, Quiet mode, and an answer
kept on screen rather than read aloud all show as "speaking" with no sound.
Then the mouth stays shut: the animals never make up mouth movements that
match nothing you can hear. (They used to open and close with the loudness,
which also meant a mouth flapping in time with no voice at all.) The nod
and the paw still follow the loudness.

For anyone changing the code: the shader reads a uniform `uMouth` (open,
wide, round). Each animal's `uniforms(pose, mouth)` (`CritterPose.uniforms(p,
mouth)` and friends on the phone) takes the shape - or nothing - and
multiplies it by how much the pose is currently speaking (the pose's
`speak`, 1 in speaking, 0 elsewhere, settling with the state), so when
speaking ends the mouth eases shut in about a quarter of a second rather
than snapping. The approval clock and
the error shake that every face gets still happen on top.

**Dimming.** In standby (0.6), banked (0.45) and error (0.9) the **whole
animal** is blended toward its background by that state's `dim`: pixel =
mix(background, pixel, dim) - the same blend every other face's colours
get, eased over the same third of a second - and the orb and rim colours
are handed to the shader undimmed, so the orb is not dimmed twice. Both
apps use this rule. (Before, only the orb and rim dimmed: a sleeping panda
was as bright as an awake one.)

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
face is drawn). It adds soft shadows, a warm glow where light passes
through fur, the rim light in the state's colour, and the orb's light.
(It used to add shading in the creases too - "ambient occlusion" - but
measured, that changed nothing on 83 to 97 percent of each animal and
cost as much as a march step; see "Drawing quality" below.)

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
names - and records the desktop's pose answers at 258 moments (about 85
per animal: every state, changes part way through, blinks, the idle
happenings, the speaking gestures, and clocks a day and three days long). The phone's `CritterPoseTest` fails if its answers differ, so the
two apps cannot drift apart without a red build. After changing any of
these files:

```
python3 tools/gen_critters.py
```

CI runs `--check`, and fails if you forget.

### Drawing quality (the 2026-09-28 pass)

Measured against a slow, exact version of the same shader (400 small
march steps) on a PC, through Skia. All of it is in the shared shader
files and the animals' `.sksl`; nothing the animals do changed.

- **More march steps where the size limit allows.** A ray that ran out of
  its 32 steps left either a see-through speck inside the animal or an
  opaque one just outside it - worst looking from well above or below
  (both apps let you tilt that far). The number of steps is now each
  animal's own (`MARCH_STEPS`): owl and otter 48. The panda has the
  biggest shape and no room to spare, so its steps were paid for by making
  the shader smaller without changing the picture: a shorter form of the
  smooth minimum (the same curve), its mouth and body sums written as
  single multiply-adds, one fewer lookup for each pixel's surface
  direction (the march has already measured the fourth), and no ambient
  occlusion (below) - 32 steps became 36 in about the same size.
  Over-relaxed marching (longer, checked steps) was tried for the panda
  and was no better than plain extra steps for its size.

  | | before | after |
  |---|---|---|
  | Panda, see-through / wrongly opaque pixels, 6 views at 384 px | 307 / 48 | 219 / 5 |
  | Panda, the same, 24 poses at 768 px | 85 / 4,523 | 96 / 1,456 |
  | Panda, specks at 128 px, looking from above / below / level (160 frames each) | 184 / 66 / 13 | 84 / 40 / 5 |
  | Owl, 6 views at 384 px | 177 / 52 | 40 / 0 |
  | Owl, 24 poses at 768 px | 0 / 239 | 0 / 0 |
  | Owl, specks at 128 px, above / below / level | 71 / 40 / 1 | 16 / 2 / 2 |
  | Otter, 6 views at 384 px | 39 / 66 | 11 / 0 |
  | Otter, 24 poses at 768 px | 0 / 451 | 0 / 0 |

  The panda is better, not fixed: seen from far above or below it still
  shows a few specks at its outline, and a big (768 px) picture still has
  about 60 wrongly opaque pixels a frame along the tail and legs. Doing
  better needs a cheaper panda - for example the pose code sending the
  mouth and tail sizes ready-made, instead of the shader working them out
  in every march step.
- **A truer outline.** The soft edge used to spread a pixel and a half
  out and made every animal about a third of a pixel fatter all round. It
  now goes from half covered, where the pixel's centre is on the edge, to
  nothing three quarters of a pixel out. Error against the true coverage
  (8 x 8 samples a pixel), panda / owl / otter at 48 px: 0.29 / 0.23 /
  0.24 before, 0.16 / 0.14 / 0.12 after; on the phone's half-resolution
  picture enlarged: 0.24 / 0.15 / 0.14 before, 0.17 / 0.09 / 0.09 after.
  At the phone's lowest tier the enlarged edge is a touch crisper than it
  was, with no more stepping.
- **No ambient occlusion.** It was shading from the simplified shadow
  shapes, and came out exactly "no shading" on 83 to 97 percent of each
  animal. Taking it out changes the default pictures by 0.01 to 0.08 of a
  level (of 255) on average, at most 23 levels in a thin crease under the
  panda's chin.
- **A bright rim colour no longer floods the animal.** The rim light adds
  light whatever the fur's colour, so a white rim made the panda's
  near-black legs 3.2 times brighter and a pure blue one tinted it blue
  all over. The rim is now held to the strength of the brightest default
  rim (no channel over 0.30, no more than 0.17 luminance, in linear light);
  every default state colour is under both, so the defaults look exactly
  as before. With a white rim the legs are now 1.1 times their default
  brightness.
- **The owl's crown spots** were laid out by angle round the head, so from
  above they squeezed into a starburst of radial dashes. They are now
  scattered on a grid in space (narrower across than tall), cut by the
  head's surface: round dots on top, upright dashes on the sides like the
  back's.

### Adding a fourth animal

A new `.sksl` beside the others (it must supply `map`, `mapLite`, `partAt`,
`material`, `sparkle`, `stuckRay`, the camera constants and `MARCH_STEPS`,
its number of march steps - see `common_tail.sksl`; give it as many as the
size limit allows), a
pose file on each side registering itself the way `critter-owl.js` and
`OwlPose.kt` do, a line in `tools/gen_critters.py`'s `ANIMALS`, a face entry
in the spec, and one `critterFace({...})` / one `object ... : CritterFace` in
each app. Then measure it: `python3 tools/shader_size.py`.

### On a PC without a working graphics card

If WebGL is blocked, or the graphics card cannot keep up, the desktop draws
a **flat sticker** of the same animal in the same pose instead. It still
tilts its head, blinks, holds its orb and sleeps; it loses the lighting.

How "cannot keep up" is decided (the GPU watchdog in `faces.html`, the same
one Nucleus, Membrane and Tokamak use): the page asks the graphics card how
long each frame of the face actually took (a WebGL timer; a "fence" where
there is none), and also notices work the card is **late** with. Three slow
frames, one frame ten times too slow, the card being reset while the face
was on it, or the page getting no frames at all for a second while the face
was already counted slow (a card far enough behind stalls the whole page),
and the face goes flat. It ignores the half second after a resize,
a quality change or a shader build (one-off costs), and after a minute it
tries the card again (then two minutes, four, up to sixteen). The Widget's
"Auto adjust" steps the quality down by the same measurement.

Until 2026-09-28 the check timed only the JavaScript that hands the work
over, which takes under a millisecond however slow the card is. Measured in a browser without a
graphics card, the panda drew about one frame a second at 1200 pixels and
the old check never noticed. Also measured then: thirty quick window
resizes flipped the otter to its flat drawing for good.

A shader that is still being built shows the flat drawing meanwhile, on
graphics drivers that can build in the background (KHR_parallel_shader_compile,
common on Windows); on others the page waits for the build, as before.

The phone needs no fallback: its shader support (Android 13) is guaranteed
by the app's minimum Android version.

If the pose script itself fails to load, the flat sticker still draws the
animal, still and neutral, rather than an empty square.

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
  32 march steps, a simplified panda for shadows) and measured about 55,000
  by `tools/shader_size.py`, which counts the way Skia does; the talking
  mouth brought it to about 58,000, inside the 60,000 each animal is held
  to. The owl and the otter were measured before they were ever pushed.
  Since the drawing-quality pass (below) each animal spends what it can
  afford on march steps: **panda 59,637 (36 steps), owl 48,520 (48
  steps), otter 55,497 (48 steps)**. The panda has about 360 to spare, so
  any change to it must save as much as it adds. CI runs that check on
  every push, so none of them can quietly grow over.
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
  - **On the desktop** it is drawn at full resolution; the GPU watchdog
    (see "On a PC without a working graphics card") switches to the flat
    version if the graphics card cannot keep up, and tries the card again
    later.
  - **Not yet measured on a real phone.** A few times Nucleus per pixel at a
    quarter of the pixels should land at or below Nucleus's own cost, but
    only the phone can confirm it. If it stutters or gets warm, say so - the next
    step would be a lower scale.
- **The phone makes about 85 small throwaway objects a frame** for an
  animal (its pose maths builds fresh number lists; the six tail names are
  no longer rebuilt every frame). Nucleus makes none. It is not measurable
  as slowness on its own, but it is more garbage than this app likes; worth
  tidying further if the phone shows stutter with an animal.
- **The phone's small offscreen picture is kept between frames.** While
  Jarvis speaks or listens the face's size wobbles a few percent with the
  voice; the picture used to be keyed by its exact size, so it was thrown
  away and a new one made almost every frame. Its size is now rounded up to
  a step of 16 pixels, so the wobble reuses one or two pictures, and the
  picker's still thumbnail keeps a picture of its own.
- **Not yet tried on a real phone or a real graphics card.** Each has been
  rendered through the phone's own drawing library (Skia, via skia-python)
  and through the desktop's WebGL in a browser without a graphics card, and
  the pictures match. The CI emulator launches the app with every face
  chosen, which catches a shader that will not compile on Android.
