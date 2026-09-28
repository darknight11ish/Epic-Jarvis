# Animal faces ("critters")

Jarvis had twenty faces: animated pictures that show what it is doing, all
of them instruments - rings, orbits, a drum skin. Now it also has **four
animals**, small cartoon characters that sleep, listen, think and talk: a
**red panda**, a **pygmy owl**, a **sea otter** and a **monkey**.

The owner's choice, 2026-09-27: all three animals Gemini suggested, panda
first; the owl and the otter once the panda worked (go-ahead given the same
day). The monkey followed on 2026-09-28, from the owner's own picture.

## How to switch to one

- **Desktop:** open the Faces window, click the Red Panda, Pygmy Owl, Sea
  Otter or Monkey card, then choose it as Jarvis's face - the same as picking any
  other face. The widget, the floating face and the HUD all show whatever
  face is chosen there.
- **Phone:** Appearance, then pick the animal from the faces.
- The choice is shared through the backend like any other face, **once
  your PC has the updated `jarvis-visual-spec.json`** (see "One thing to
  check on the PC" below).

## The four animals

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

**More detail (the owner, 2026-09-28: "the otter looks too plain ... the
water around the otter is too plain as well").** All of it is painted on
in its colours, once a pixel, not built into its shape - so it cost almost
nothing of the phone's size limit (below):

- *Fur.* Soft wavy strands in short tufts along the body and arms, with
  finer hairs inside each tuft when the picture is big enough to hold them;
  on the face the fur fans out from the nose. The strands show more at the
  outline, so its edge reads soft and furry rather than smooth. A dark
  back, a lighter belly and a pale chest under the chin; darker paws and
  feet, with faint toe creases. Three staggered rows of whisker dots on
  each side of the muzzle (the mouth is drawn over them).
- *Water.* Small wavelets crossing each other, shading the water and
  catching the light in soft broken glints; rings spreading out from the
  otter, stronger while its feet paddle; a thin, broken line of foam where
  it meets the water; lighter water close in, deepening to near-dark at the
  pool's edge, so the edge melts into the background instead of looking
  like a plastic ring. Everything moves slowly - a wavelet travels about
  its own length in two to three seconds - and asleep it is half as strong.
  It all runs off the water's own clock from the pose (`uWater.y`, one
  turn every 2.6 seconds), in whole turns, so nothing jumps when that
  clock wraps round; the shared `uTime` was not used, because it speeds
  up, slows and even reverses with the state, and wraps differently on
  the two apps.
- *Never sparkling when small.* Each pattern fades out as the picture gets
  too small to hold it (it uses `uPx`, the size of a pixel): at 96 px the
  otter looks almost as it did before, smooth; the tufts come in from
  about 85 px (full by about 235), the whisker dots from about 160 (full
  by about 450) and the fine hairs from about 210 (full by about 580).
- *Calm, serious and still quieten it too.* The pose scales the ripple
  strength it sends (`uWater.z`) by the same option weights as the
  otter's rocking: calm halves the waves and rings, serious takes 60
  percent off, and "Keep the animal still" stops them altogether (a still,
  flat pool). Only the options - each state already sets its own strength
  (asleep is half).

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

### Monkey

![The monkey in all eight states](critters/monkey-states.png)

The owner's fourth animal (2026-09-28), from their own picture of a cartoon
monkey, in the same style as the other three: warm brown fur, a big peach
face shaped like a heart - a round patch round each eye over a wide one
across the cheeks and muzzle - big round ears with peach insides, a small
tuft on top, a peach belly, long arms and legs with peach hands and feet,
and a long thin tail ending in a curl. It hangs by one arm from a green vine
across the top of the picture - the arm rises from its shoulder beside its
head, bent a little at the elbow, and passes behind the edge of its ear, as
in the picture - and swings gently round its hand, like a slow pendulum. **Its banana is its orb**: the banana's ends stay banana-yellow,
its middle glows in the state's colour with the same halo the other orbs
have, and it lights the monkey the same way. The owner asked for it to be
"more energetic than the other animal models to a degree", so it is a
little livelier - see "How they move" for the numbers - but smooth, and
the serious moments are as still as the others'. The owner then set how
much: **about 1.5 times the panda's resting movement** (2026-09-28).
Measured with the comfort review's harness over half an hour of idle, the
middle of its head travels at most 6.6 percent of the animal's height
(the panda's, 4.5: 1.47 times); the swing itself is about 1 degree each
way, 1.4 at its widest.

| Jarvis is... | The monkey... |
|---|---|
| Idle | Hangs and swings gently (one swing every 3.5 seconds, about 1 degree each way), its legs and tail trailing the swing a moment behind. Looks at one thing, then another, a little more often than the others, with a curious tilt of its head. About every 19 seconds it does one small thing - most often kicks its legs, turns to something with one ear first, or curls its tail tip; now and then looks at its banana (lifts it, tips its head, turns it) or swings a little wider for a few swings; once in a while scratches the top of its head. |
| Listening | Leans in, its head tilted about 15 degrees, its ears turned forward to you, its eyes on you; its swing settles to about half. |
| Thinking | Brings its banana up in front of its chest and looks into it - it glows its brightest - tapping it in little bursts, glancing up and away now and then. |
| Speaking | Its mouth makes the shapes of the words it is saying. It talks with its eyes and, now and then, a nod, its banana lifted a little, or a tilt of the head - never two alike in a row, and never just as its eyes move. |
| Waiting on you | Hangs still, leans in and looks straight at you, ears forward, its banana held out a little toward you. No wave. |
| Asleep | Has climbed up and sits on the vine, its legs hanging in front, its tail curled round the vine, hugging its banana, head drooped, eyes shut, breathing slowly; now and then a sigh. |
| Something went wrong | A still, concerned look: head tipped a little and lowered, eyes down, brows drawn, ears back a touch; it hangs almost still. |
| Keeping things for later | Dozes where it hangs, half-lidded, swinging a little; now and then its head sinks and it catches itself. |

Because it sleeps sitting ON the vine and hangs from it awake, going to
sleep it climbs up, and waking it slides back down. The picture follows the
monkey, so on screen it is the vine that moves - down past the monkey as it
climbs, and **always behind it**, so it never cuts through the monkey. That
move is not an extra: it is the difference between its two poses, so it
happens under calm, still and serious too (plainly, without the extras
below).

### What all four share

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
the pose works back through them. Falling asleep and waking are not a plain
settle: each animal plays a short piece of its own (see "Waking up and
nodding off" below); dozing off and rousing from a doze take about twice
the usual time.

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
- **Waking up and nodding off** (the owner, 2026-09-28). When Jarvis
  leaves standby - by the schedule, by hand, or when the link comes back
  after "not connected", which shows standby too - the animal wakes up in
  about two seconds; when it goes to standby it nods off in about three.
  Calm, never busy, and **the mouth never moves** (it follows Jarvis's real
  voice and nothing else, so no yawn):

  | | Waking up (about 2 s) | Nodding off (about 3 s) |
  |---|---|---|
  | Red panda | Its eyes open with a slow double blink; its head lifts a little past and settles; a small stretch (leans back, paws up and out, chin up, a deeper breath); its ears perk with a flick. | Heavy eyes and a slow blink; its head nods as it drifts, it catches itself (eyes open a little, ears up), another heavy blink - then its head goes down and its tail curls round. |
  | Pygmy owl | One eye opens, then the other; a quick ruffle of its feathers with a small shiver; its head draws up a little and settles with a small shake. | Its eyes half close, one last slow blink, then it fluffs up round (a touch past, and settles) and tucks its head in. |
  | Sea otter | Its paws stay over its eyes a moment and rub them; then they come away into a small stretch in the water (paws up and apart, chin up, toes out) and go back to the pebble, picking it up. | A slow stretch in the water, then its paws come up over its eyes, leaving the pebble on its chest, and it settles. |
  | Monkey | It takes hold of the vine and slides down off it to hang by one hand again (the vine going back up, behind it); as it hangs, its eyes open, it has a small stretch (legs out, a deeper breath) and its ears flick. | It looks up at the vine and climbs up it, the vine passing down behind it; its hand keeps hold until the vine is down at its middle, then it lifts its legs over, curls its tail round the vine, hugs its banana, and its head droops. |

  - **Waking straight into "waiting on you", "something went wrong" or a
    doze**, only the eyes open, gently - no stretch, rub or ruffle - so
    those looks stay attentive and still.
  - **Calm, serious and still:** only the eyes open, or close, slowly.
    (Each is a weight, so part way on gives part of the piece.)
  - **Nothing doubles up.** While it wakes, its idle happenings, talking
    gestures and ordinary blinks wait, then come back over the last
    moments. Woken by a question and answering straight away, it plays the
    whole wake-up while it speaks: the mouth follows the voice as always,
    only the gestures wait.
  - **A quick flip never snaps.** Asleep for a moment and awake again (or
    the other way round): each piece is scaled by how far the one before it
    had got, and carries on from what was on screen. Woken into listening
    and then thinking, the wake-up carries on across both changes rather
    than starting again.
  - **The Zs** fade out in the first 0.3 to 0.7 seconds of waking, and
    only rise once it is asleep - from about two seconds into nodding off,
    all of them by three - not the moment standby starts.
  - Both apps play the same piece: it is part of the pose code
    (`wakeSleep` in each animal's `critter-*.js`, the same in
    `CritterPose.kt`, `OwlPose.kt` and `OtterPose.kt`), a pure function of
    the state, the list of past changes and the clock, held equal by the
    fixture like everything else. Measured at 240 frames a second: no
    sudden change of speed where either piece starts or ends; the head
    turns at most about 35 to 50 degrees a second (as it did before); the
    otter's paws are the fastest thing, about half the picture's width a
    second as they leave its face.
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
  back when it returns - but only if it returns to standby. A link that
  comes back straight into an awake state leaves them off while the animal
  wakes (before, they flashed back for about 0.7 s during the wake-up).
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

`asleep` stays 0 for the first two seconds of nodding off and reaches 1 by
three (the Zs only rise once it is asleep), and falls back to 0 within
about 0.7 seconds of waking: fade the Zs with it. `x` and `y` are a point a little above and
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
carry on smoothly, the Zs show only asleep, and the wake-up and the nodding
off play, end on time, keep to the eyes when they should (waiting on you,
something wrong, a doze; calm, serious, still), leave the mouth alone, and
never change speed suddenly (stepped at 240 frames a second).

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

**Mouth drawing (fixed 2026-09-28, after a close visual check).**
- *The line stays one line at small sizes.* Its width used to be fixed, so
  below about 200 pixels it could fall between pixel centres: at 96 px a
  shut mouth broke into pieces in about 690 of 2,541 panda shapes and 460
  otter ones. It is now never thinner than about a pixel and a half of
  whatever it is drawn at (0 broken at 96 and 64 px); big pictures are
  unchanged. On the phone's lower-resolution picture this is what keeps the
  line: at the Low tier the worst mouth line keeps 60 percent of its
  contrast (it was down to 17 percent, and the otter's could vanish), so
  the phone's trace sizes did not need changing.
- *Teeth are ivory, whatever the orb's colour.* Inside a mouth the light
  arrives without its colour (`common_tail.sksl`, `lit`): the key light is
  mostly shadowed in there, so the blue sky and the orb had turned the
  panda's teeth grey-blue (79 percent of teeth pixels bluer than red) and a
  red or green orb would tint them. Now 0 percent, sRGB about 164, 155, 142
  with the default orb, and ivory under red, green, purple, white and amber
  orbs.
- *No stripes on the roof of the mouth.* Seen from below, the roof of an
  open mouth showed dotted dark stripes: the hit point sat a hair off the
  surface by a different amount per pixel, and the teeth and line are
  painted by position. Each hit is now moved onto the surface before it is
  coloured (it changes nothing else visibly), and the roof takes no line.
- *The otter's lower lip is no longer cut off.* Wide open, it reaches
  round under the otter's chin, where it used to be clipped (up to 71
  pixels at 400 px). It is now painted on the whole front of the head. The
  price: seen from low down and to the side, a wide-open otter mouth wraps
  a little way under the chin and looks longer.
- These cost nothing in size: the smooth minimum was rewritten with one
  division instead of two, which made every animal smaller (panda 59,637
  to 58,730) with pictures the same to within one level of 255.

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
get - and the orb and rim colours are handed to the shader undimmed, so
the orb is not dimmed twice. Both apps use this rule. (Before, only the
orb and rim dimmed: a sleeping panda was as bright as an awake one.)
Banked and error dim at once (the desktop eases it over about a third of a
second; the phone steps). **Standby's dim follows the animal's own sleep**:
it is laid over the dim of the state before, as far as the pose is asleep
(its `asleep` weight, the one the Zs fade with - `sleepDim` on the desktop,
`DimRule.sleep` on the phone). So the animal darkens as its eyes close and
the Zs appear, at the end of nodding off, and brightens as its eyes open,
in the first ~0.7 s of waking - not the moment standby starts or ends.

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
| `jarvis-desktop/critters/common_head.sksl`, `common_tail.sksl` | **What all four share**: the camera, the lighting, the orb and its glow, the soft outline, and the size-safe march. |
| `jarvis-desktop/critters/redpanda.sksl`, `pygmyowl.sksl`, `seaotter.sksl`, `monkey.sksl` | **Each animal's own part**: its shapes and its colours. |
| `jarvis-desktop/src/critter-pose.js` (+ `critter-owl.js`, `critter-otter.js`, `critter-monkey.js`) | **The poses** on the desktop: where the head, ears, eyes, paws, wings, tail and orb are on each frame. |
| `jarvis-client/.../face/CritterPose.kt` (+ `OwlPose.kt`, `OtterPose.kt`, `MonkeyPose.kt`) | The same pose maths on the phone, line for line. |
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
- **Edges between two parts are not smoothed.** The soft outline smooths
  an animal's edge against the background only. Where one part passes in
  front of another - an arm or a leg over the body, the banana over the
  belly, the panda's paw over its leg - the edge is a plain one-pixel
  step, the same on all four animals (checked on the monkey and the panda
  at 540 px against a picture made with 16 rays a pixel: they differ from
  it about equally, 0.51 and 0.47 of a level on average). The owner saw the
  monkey as "a bit pixelated" in 320-pixel preview videos, enlarged; most
  of that was the video's small size and its compression - the 540-pixel
  renders are cleaner - and the rest is these inside edges, which the
  monkey has more of than the others (thin arms, legs and tail in front of
  its body). Smoothing them would mean several rays a pixel, two to four
  times the work; not done. One real fault was found and fixed on the way:
  the belly right beside the banana's tip was coloured as banana, a few
  yellow slivers.
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

### Resolution and frame rate (owner, 2026-09-28)

The owner's ask: "if Jarvis detects capable hardware (and the user opts for
better quality and not battery save mode) the resolutions will all be high",
and higher resolution and frame-rate choices for the animals on both apps.
The numbers live once, in `jarvis-visual-spec.json` (`frame_rate.animals`
and `frame_rate.pick_rule`); the desktop reads them through `face-pace.js`,
the phone keeps the same numbers in `FaceBudget.kt` (`QualityTier`,
`AnimalPace`) and its SpecDriftTest fails if they drift.

**Quality levels** - the same words in both apps (Settings, "Face on this
computer" on the PC; Appearance, Face editor on the phone). The stored ids
are still `low`, `medium`, `high`, `max`, so a saved setting keeps working.
The lowest is "Lower", not "Battery saver": the phone already has a Battery
saver switch, and it still overrides everything here.

| Level | Desktop animal | Phone animal | Its one line in both apps |
|---|---|---|---|
| Lower | 62% of the screen's pixels | 0.4 of full resolution | Softest picture and the least work for the graphics chip. Easiest on battery and heat. |
| Balanced | 80% | 0.5 | A little softer than High, with less work for the graphics chip. |
| High | 100% | 0.75 | Sharp. A fair amount of work for the graphics chip. |
| Maximum | 2x2 per pixel, averaged down (at most 2,400 pixels a side) | 1.0 | The sharpest edges. The most work for the graphics chip, and the most battery and heat. |

Measured the audit's way (a red panda against an 8x - 240 px - or 6x - 600
px - supersampled reference, through Skia; mean error on its edges, out of
255; lower is sharper):

| | 240 px | 600 px |
|---|---|---|
| desktop High (before and after) | 9.4 | 9.4 |
| desktop Maximum (new) | **3.2** | **3.1** |
| phone High before (0.5) | 23.1 | 19.9 |
| phone High now (0.75) | 13.0 | 11.9 |
| phone Maximum now (1.0) | 9.4 | 9.4 |

Cost: Maximum on the desktop traces four times the pixels of High. On the
phone, High now traces 2.25 times the pixels it did (0.75 against 0.5 each
way), and Maximum four times.

**Auto adjust** starts an animal at High. It steps down in this order when
frames run late: Maximum to High, then the frame rate to 60, then Balanced,
then 30, then Lower (frame-rate steps are whole shares of the screen's rate,
never under 30). It climbs back the same way, held off for a while after
each step down - and it may climb to **Maximum**, for an animal only, when
its frames take under a quarter of their time. On the phone never in
Battery saver (the switch or the phone's own) and never while the phone is
warm; on a software renderer (the emulator) it stays at Lower. A level or
frame rate picked by hand stays picked.

**Frame rate** choices: Auto, 30, 60, 90, 120, Max (30 and 90 are new). A
picked rate is drawn on whole shares of the screen's rate, the nearest one
but never more than a fifth faster than the pick: 90 becomes 72 on a 144 Hz
screen and 60 on a 120 Hz one.

**Resting.** An animal at rest (idle, or waiting on an approval) with Frame
rate on Auto is drawn 60 times a second while frames are cheap (they cost
under half of a 60 fps frame's time; it drops back to 30 above 0.8 of it),
else 30 - and at the screen's full rate while one of its idle happenings (a
stretch, a scratch, an ear turning) is playing, which each pose file reports
as `busy(state, t)` (`critter-busy-golden.json` holds the phone's copy to
the desktop's). A picked 30, 60, 90, 120 or Max sets its resting rate to
that. Standby stays 15 and banked 2 whatever is picked. The other faces
keep the spec's resting rates. The desktop's widget, HUD and floating face
used to draw every frame in every state; they now rest by the same rules as
the Faces window. On the phone, resting at 30 or more strides on the
display's own frames (it used to sleep on a timer, which landed 30 frames a
second unevenly on a 120 Hz screen); standby and banked still sleep on a
timer.

**No shadow on a small face.** Under 200 device pixels (the animal's square)
or at Lower, the soft shadow is skipped (`uNoShadow` in
`common_tail.sksl`): at that size it is a few pixels of shading. Measured
through Skia at 256 px it is about 10 to 20% of an animal's cost (panda 406
-> 331 ms; the monkey showed no difference), and it changes the picture by
about 1.5 of 255 on average for the panda. Shader sizes after: panda 58,740,
monkey 58,273, otter 54,134, owl 48,168 (the limit here is 60,000).

**What it shows.** Under the full-size face in the desktop's Faces window,
and at the bottom of the phone's Frame rate setting: "60 fps · 4.2 ms per
frame · animal resolution 1200 px (200%)" - frames a second, the time each
takes, and the size the animal is traced at against the size it is shown.

**Not yet measured on real hardware.** Whether Auto reaches Maximum depends
on the owner's graphics card and phone; the rules and pacing are tested,
the speed is not.

### Adding another animal

The monkey (2026-09-28) was the fourth, added by this list:

- **Shader:** a new `.sksl` beside the others. It must supply `map`,
  `mapLite`, `partAt`, `material`, `sparkle`, `stuckRay`, the camera
  constants and `MARCH_STEPS` (see `common_tail.sksl`; give it as many as
  the size limit allows). The orb's glow and light come from `uOrb`; the
  orb can be another shape (the monkey's banana is its own part, glowing
  through `sparkle`).
- **Pose:** a file on each side registering itself the way
  `critter-owl.js` / `OwlPose.kt` do, with its own `wakeSleep` and its own
  salts (the numbers its dice use - no two animals may share one), slots
  that divide `PERIOD` (16 or 32 seconds), and the Zs' `overlay`.
- **Generator:** a line in `tools/gen_critters.py`'s `ANIMALS`, the pose
  file in `POSE_JS`, and its moments in `MOMENTS` (a blink, a double blink,
  each happening, each speaking gesture - found by scanning its pose code).
- **Tests:** the animal in every list in `CritterPoseTest`,
  `FaceShellRulesTest` and the desktop's `faces.mjs` / `face-watchdog.mjs`.
- **Both apps:** a face entry in `jarvis-visual-spec.json` (both copies,
  then `python3 jarvis-desktop/scripts/build-faces-spec.py`), one
  `critterFace({...})` with its flat drawing and a `<script>` tag in
  `faces.html`, one `object ... : CritterFace` in `CritterFaces.kt`, listed
  in `Faces.all` and `warmCritterShaders()`.
- **Voice:** a row in `backend/jarvis_voices.py` `FACE_VOICES` and
  `voice_training.rs` `ANIMALS`, then `gen_voice_training_cases.py` and
  `gen_phone_voice_cases.py`.
- **Measure:** `python3 tools/shader_size.py`, and render it.

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

## The sky behind the animals (sun, moon and weather)

Two options, both **off** until the owner switches them on (the owner's
decisions of 2026-09-28). In plain words:

- **"Show the sun and moon behind the animal"** draws the real sun and moon
  for the owner's town behind whichever animal is showing: the sun comes up
  on the east side of the picture at sunrise, arcs over the animal and goes
  down at sunset, with a warm glow near the ground at dawn and dusk; at night
  the moon does the same at its own times, drawn in its real shape (a thin
  crescent, a half, a full moon) with its lit side turned the right way.
- **"Weather in the animal's scene"** adds soft rain, slow snow, or a few
  faint lines of wind and drifting clouds.

Where to switch them on: the desktop's Settings, Appearance, "Sun, moon and
weather" (the town is typed there, once); the phone's Appearance, "Sun, moon
and weather" (it shows the town the PC has, and can switch the sky on or
off, forget the town, or choose the weather source). docs/JARVIS-API.md
section 59 has the route; ARCHITECTURE section 4 the one part that goes
online (Open-Meteo, only if chosen, after an approval card).

**How the sky is worked out.** On each device, from the town's rough
position (0.1 degree, about 11 km) and the clock - `jarvis-desktop/src/sky.js`
and its line-for-line phone copy `face/Sky.kt`, held equal by
`tools/gen_sky.py` (`sky-golden.json`, checked by the phone's `SkyTest`). The
formulas, implemented from their published form (no code copied): the sun
from NOAA's Solar Calculator (Meeus, "Astronomical Algorithms", 1998, ch. 22
and 25); the moon from the low-precision formulas of "The Astronomical
Almanac"; its lit fraction and the angle of its bright edge from Meeus ch.
48, turned to the screen by the parallactic angle (ch. 14); rising and
setting by the standard altitudes of Meeus ch. 15. Checked in
`jarvis-desktop/tests/sky.mjs` against NASA's published moon phases, the
published London solstice sunrise and sunset, and an independent program
(PyEphem) for New York, Denver, Sydney and Singapore: the sun within 2
minutes, the moon within 6.

**How it looks, and why.**

- The picture looks toward the equator (south in the northern half of the
  world, north in the southern), so the sun rises on the left in New York
  and on the right in Sydney, as it does to someone standing outside.
- Each body follows one fixed arc round the animal, timed by its real hour
  angle: rising at the side, at the top at noon (the sun) or at its own
  highest point (the moon), setting at the other side. The arc is a picture
  of the day, not a camera view: at its top the sun or moon sits ABOVE every
  animal's head and above the monkey's vine, so a noon sun or a midnight
  moon is seen rather than hidden; the vine passes in front of it twice a
  day, like a real branch. The season shows in when it rises and sets.
- The sky tint is dark by design - at most about a fifth over the app's own
  ground (tested) - so the animal and the dark themes stay readable: a
  quiet blue by day, a warm low band at dawn and dusk, deep blue at twilight,
  nearly nothing at night. Cloud dims the sun and moon.
- Rain is soft, slanting streaks at low opacity; snow drifts slowly (over ten
  seconds to cross the picture) with a gentle sway; wind is a few faint lines
  and a sideways drift of everything else. Thunder is drawn as heavy rain:
  nothing in the sky ever flashes. The weather is a pure function of the
  clock, the weather and a hash - never of the frame before - so both apps
  draw the same rain at the same moment. **The animals themselves move no
  more in wind than in calm** - the owner asked for calm, so the weather
  never reaches the pose.
- It is drawn BEHIND the animal, as a flat 2D picture on the face's own
  canvas - not in the animal's shader, which is at its size budget. On the
  desktop the shader leaves its uncovered part see-through while the sky is
  on (`uSeeThrough`); the phone's shader always did.
- Calm (reduced) motion: the weather holds still; the sun and moon move only
  with the real clock anyway (a day to cross the picture). "Keep the animal
  still": unchanged - it is the sky, not the animal. Not connected, and
  serious moments: the sky stays (it is calm). Standby: it dims with the
  animal. Stale weather (over 90 minutes old) is not drawn.

**Known limits.** At a polar day's midnight the sun's arc wraps from one side
to the other; it fades out for about three quarters of an hour either side
of that moment rather than jump. Positions are to about 0.3 degree for the
moon (a few minutes in its rising time) - far finer than the picture shows.
Not yet seen on a real phone: the phone's drawing (`SkyDraw.kt`) is checked
by CI's compiler and the emulator only.

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
  steps), otter 55,497 (48 steps)**. The mouth-drawing fixes (see "Mouth
  drawing" under "How the mouths talk") paid for themselves with a one-division smooth minimum:
  now **panda 58,730, owl 48,113, otter 54,594** (the owl is 48,158 since its sine-free spots). The otter's added detail (fur, wavelets, rings, foam) is all
  painted once a pixel, and its water's surface became flat in the march
  (the old rings there were barely visible): it went down, to **54,124**. The panda has about
  1,270 to spare, so any change to it must still save as much as it adds.
  The **monkey** is at **58,263 with 36 steps**: it has the most parts (a
  vine, two arms with elbows, two legs, a four-piece tail, a banana), so
  its legs are worked out one side at a time (the panda's eyes' trick), its
  tail's pieces join with a plain minimum, and its tail's thicknesses come
  ready-made from the pose code. Rendered against 400 small steps it shows
  no more wrongly drawn pixels than the panda (at 256 px, 8 states by 6
  views: 55 see-through, 1,767 wrongly opaque - the opaque ones along its
  outline, mostly seen side-on). CI runs that check on every push, so none
  of them can quietly grow over.
- **Cost.** Measured through Skia (the engine Android draws with), per
  pixel: the **panda about 4 to 5 times Nucleus's work**, the **owl about
  2.3 times**, the **otter about 2.8 times** and the **monkey about 4
  times** (measured against the panda: about nine tenths of its work). (The panda was 10 to 12
  times before its rebuild; an even earlier version of this page said "a
  little more than Nucleus", which was a guess, and wrong.) Most of it is
  finding the animal's surface for each pixel; the shadows are the rest.
  These timings wobble by a fifth or so from run to run.
  - **How sharp each animal is drawn depends on the Quality level** (see
    "Resolution and frame rate" below): on the phone it is traced at part of
    the screen's resolution and enlarged - 0.4, 0.5, 0.75 or all of it for
    Lower, Balanced, High and Maximum; on the desktop at 62%, 80% or 100% of
    the screen's pixels, and at Maximum at 2x2 samples per pixel, averaged
    down. A software canvas (a bitmap snapshot) on the phone still draws it
    at full size.
  - **On the desktop** the GPU watchdog (see "On a PC without a working
    graphics card") switches to the flat version if the graphics card cannot
    keep up, and tries the card again later.
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
