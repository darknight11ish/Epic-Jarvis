# Brag Plan: Jarvis (v2 — "cut to the beat")

## Why a second version
The first render was judged "lame" by the owner: too static and plain, too slow
(few cuts, long holds), and the cinematic tone read as flat. It also drew a
lookalike face instead of the real one. This version fixes each of those:

| Problem in v1 | Fix in v2 |
|---|---|
| Static / plain | Real registry-style effects: RGB-split hits, glitch cuts, scramble-decode type, film grain, HUD telemetry, anamorphic flare, camera push-ins |
| Too slow | 30+ cuts in 25s, every cut on a beat of a 120 BPM grid; montage at 0.5s per shot |
| Tone off | Freeform "sci-fi trailer, cut to the beat" instead of the slow cinematic preset |
| Fake face | The actual reactor faces, lifted verbatim from `jarvis-desktop/src/faces.html` (Arc, Orbit, Geodesic, Rime, Fullerene, Spiral, Orbital) and driven frame-by-frame |
| Happy stock music | Original synthesized dark trailer score, built on the same timing table as the picture |

## What is this app?
Jarvis is a private voice assistant that lives on your own PC, with a living
reactor face on the desktop and the phone, that asks before it acts.

## The angle
A sci-fi reactor that is real. The face on screen is the shipped renderer,
not an illustration. Every claim is a feature that exists today. The drama
comes from the reactor changing state on the beat, and from the one moment the
music stops dead when you say "stop".

## Hook (first 2-3 seconds)
Black. A point of light. The Arc reactor ignites and spins up (0-2s). On the
first downbeat (2.0s) it snaps to listening-ember as **"Hey Jarvis."** slams
in with an RGB split. Then **"Nothing leaves the room."**

## Key moments (the middle)
- The face is alive: a 0.5s-per-shot montage of real faces (Geodesic, Rime,
  Fullerene, Spiral), then the Arc hero changing state on the beat:
  **IT LISTENS.** (ember) → **IT THINKS.** (the violet sweep from the owner's
  screenshot) → **IT SPEAKS.** (ice).
- Interrupt it: Jarvis is reading a note aloud, the owner says **"STOP."**, and
  the music, the text and the face all cut on the same frame.
- It asks first: "Lock the front door." A phone rises with the real approval
  card (title, "Swipe right to approve, left to deny", "Expires in 0m 47s"
  counting down) and the face in its amber "waiting on you" state with the
  real waiting-clock ring. A swipe approves it.
- Your GPU, not their cloud: desktop and phone joined by a private mesh line;
  the path to a cloud breaks.

## Outro / punchline
The violet Arc fills the frame with an anamorphic streak. On three beats:
**YOUR ASSISTANT. / YOUR PC. / YOUR RULES.** Then JARVIS.

## User flow worth showing
Wake word → spoken request ("Lock the front door.") → approval card on the
phone → swipe to approve → face returns to idle.

## Tone
- Preset: cinematic (typography, seriousness, big claims stated plainly)
- Creative direction: "sci-fi trailer, cut to the beat"
- Interpretation: cinematic type and restraint in copy, but chaotic-preset
  pacing — hard cuts on beats, 0.5-1s shots, and every line slams in fast and
  then holds long enough to read.

## Format: landscape — 1920x1080
## Duration: 25s

## Visual identity (from the project)
- Background: `#04070c` (the kit's single background) / `#05070b` void
- Accent: state colours from `jarvis-visual-spec.json` — idle ice-3 `#2ea8cc`,
  listening ember-4 `#ff9b52`, thinking sweep (hue 217-275, azure→violet),
  approval amber-4 `#ffb648`, speaking ice-4 `#6fe3ff`
- Text: `#dbe7f2` ink, `#8fa3b8` dim
- Display font: Chakra Petch 700 (bundled with the desktop app)
- Body / HUD font: IBM Plex Mono 400/500 (bundled)
- Strongest visual element: the Arc reactor face, thinking state

## Share copy (draft)
Jarvis: a voice assistant that lives on my own PC, never sends my private life
to anyone's cloud, and asks before it acts. Every time.

## Audio direction
- Role: dense rhythmic layer (trailer score)
- Music: original synthesized score, 120 BPM, A minor. No bundled track fits:
  all five are upbeat "business" tracks, and the larger catalog needs an
  account login.
- Music treatment: drone + riser into a braam on 2.0s; groove from 5.5s;
  hard silence at 11.5s ("STOP"); rebuild; braams on 21.0 / 22.0 / 23.0;
  sub tail to 25s.
- Music cue guidance: cues are defined by construction (the score is written
  to the storyboard grid). Strong cues: 2.0, 11.5, 21.0.
- Audio-reactive treatment: subtle — the score's low-band envelope drives the
  reactor's glow and core bloom (per-frame data exported with the score).
- SFX posture: moderate, motion-matched: glitch ticks on montage cuts, key
  ticks while the reply streams, card slide when the phone arrives, swipe
  whoosh, confirmation chime on approve.
- Restraint rule: no waveform or equaliser graphics; no strobing (every cut
  stays within the kit's own flash limit of 3 transitions/s).

## Storyboard (times in seconds; one beat = 0.5s)

### Scene 1 — Ignite — 0.0-2.0
Black → a point of light → the Arc face (idle, ice) spins up from nothing.
HUD brackets draw in; mono telemetry: `JARVIS // LOCAL` and a running timecode.
Sequential/interaction: rings resolve outward. Audio: drone + riser.
Transition: hard cut with RGB split → 2.

### Scene 2 — "Hey Jarvis." — 2.0-3.5
Face snaps to listening (ember), spokes surge, camera punches in.
Text: **"Hey Jarvis."** (2 words, 1.5s hold). Audio: braam + impact (beat-locked 2.0).

### Scene 3 — Nothing leaves the room — 3.5-5.5
Face small at centre inside a drawn boundary ring ("the room"). Tags EMAIL /
FILES / MEMORY / KEYS drift out, hit the boundary and bounce back.
Text: **NOTHING LEAVES THE ROOM.** (4 words, 2.0s). Audio: pulse, glitch tick.

### Scene 4 — A face that's alive — 5.5-7.5
Four hard cuts, one per beat: Geodesic, Rime, Fullerene, Spiral (real faces,
varied states). Text held across all four: **A FACE THAT'S ALIVE.** Mono label
per shot with the face's real name. Audio: groove starts; glitch tick per cut.

### Scene 5 — States — 7.5-10.5
Arc hero, state changes on the beat: **IT LISTENS.** (7.5) → **IT THINKS.**
(8.5, violet sweep) → **IT SPEAKS.** (9.5). 1s each. Audio: accents per change.

### Scene 6 — Interrupt — 10.5-13.0
Speaking. Reply streams in mono: "Today's note: pick up the new filters,
then call —". At 11.5 **STOP.** slams; music cuts to silence; reply freezes and
dims; face drops to idle. 12.0: **Interrupt it mid-sentence.** Small HUD line:
`SPEECH UNDERSTOOD ON YOUR PC`. Audio: key ticks, then silence (beat-locked 11.5).

### Scene 7 — It asks first — 13.0-18.0
13.0: spoken request `"Lock the front door."` 14.0: phone rises with the
approval card; face on the phone in approval state (amber + waiting clock);
countdown ticks "Expires in 0m 47s → 44s". Text **IT ASKS FIRST.** 15.5: swipe
right; card leaves; ✓ Approved; face → idle. 16.0: **ONE CARD. ONE DECISION.**
+ mono `NEVER AUTO-APPROVED`. Audio: card slide, swipe, chime.

### Scene 8 — Your GPU, not their cloud — 18.0-21.0
Desktop window (Arc widget) and phone, joined by a glowing private-mesh line
with packets; a dashed path up to a cloud glitches and breaks. Text:
**YOUR GPU. NOT THEIR CLOUD.** then **EMAIL. FILES. MEMORY. STAY LOCAL.**
Mono: `PRIVATE MESH · NEVER THE PUBLIC INTERNET`. Audio: impact 18.0, riser.

### Scene 9 — Your rules — 21.0-25.0
Violet Arc fills frame, push-in, anamorphic streak. **YOUR ASSISTANT.** (21.0)
**YOUR PC.** (22.0) **YOUR RULES.** (23.0), stacked and held; JARVIS (24.0);
fade to black. Audio: three braams, sub tail.

## Hard rules check (from the owner's brief)
- No speeds, benchmark, or accuracy numbers. (The only numbers on screen are
  the approval countdown, which is product UI, and the HUD timecode.)
- No competitor names. No Play Store. Nothing from "waiting for hardware" or
  "planned" is shown.
- No personal details: sample request "Lock the front door." and sample note
  are obviously generic; no device names, usernames, addresses or tokens.
