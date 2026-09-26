# UI audit, 2026-09-26: making Jarvis feel "alive" without making it busy

Scope: motion only. That means the face and its states, the switches between
voice states, small reactions to touch and clicks ("micro-interactions"),
sounds and vibrations paired with them, how text appears while it streams in,
and moving between screens. Read-only audit. Every claim below cites the file
and line I read. Anything I did not check says so.

**Two words used throughout:**
- **Envelope**: a smoothed loudness number (0 to 1) that follows a voice. It
  rises fast when a syllable starts and falls slowly after it. The face uses
  one for your microphone and one for Jarvis's own voice.
- **Reduced motion**: the Windows and Android setting that asks apps to move
  less ("Show animations" off on Windows, "Remove animations" on Android).

---

## The short answer

The face is already very good work. The shared spec
(`jarvis-desktop/src/jarvis-visual-spec.json`) sets out a real motion language:
approval "knocks", error stops and runs backwards, banked stands still with
notches, colours fade over 300 ms, and flashing is capped for seizure safety.
The phone follows it closely. The phone's face hears you and speaks with
Jarvis's real voice.

The gaps are all at the edges, and they are cheap to fix:

1. **The desktop face never hears you, and it does not move with Jarvis's
   real voice.** Its "speaking" motion is a made-up rhythm, and its
   "listening" motion is a flat level that ignores your voice.
2. **The small reactor in the desktop's ask bar speaks a different language.**
   When something is waiting for approval, or something has gone wrong, it
   only changes colour. The spec says those two states must be readable
   without colour. And while an answer streams in, seven separate animations
   run at once on that bar.
3. **Reduced motion means three different things** on the desktop face, the
   desktop windows and the phone.
4. **The phone has no entrance or exit motion for list items.** Approval cards
   pop in, and the list jumps when one leaves. New paragraphs of an answer
   also snap in, where the desktop fades them in.
5. **The moment you let go of the talk button** gets no vibration and no
   visible "caught it" from the face, although pressing and cancelling both
   vibrate.

None of the fixes needs a new always-running animation. Almost all of them
are one-off animations that play once, triggered by an event, and they fit
inside the budget the face already has.

---

## What is already right (keep it)

| Thing | Where | Why it matters |
|---|---|---|
| State colours fade over 300 ms, and the spin speed eases over 220 ms | spec `state_transforms.color_ease_s` / `rate_ease_s`; phone `face/FaceView.kt:870-884`, `:986-1002`; desktop `faces.html:3700-3706` | A state change reads as the same creature changing its mind, not as a cut. |
| Approval's colour follows 100 ms *after* its ring ("the knock comes before the door opens") | spec `tint_delay_s`; `FaceView.kt:992-997` | Order of events feels intentional. |
| Error stops dead, holds, shakes, then crawls backwards | spec `state_transforms.states.error`; `faces.html:4297-4302`; `FaceView.kt:1060-1068` | Direction survives colour-blindness and still frames. |
| Resting states draw at fewer frames per second (idle 30, standby 15, banked 2). Any change or tap gets 600 ms at full speed | `face/Spec.kt:77-85`; `faces.html:4091-4096` | This is where the battery saving comes from. Every proposal below reuses that 600 ms window rather than adding a new loop. |
| The phone's face gets the real mic and speaker levels | `HomeScreen.kt:1530-1538`; `audio/Speaker.kt:276`, `:406` | The face talks with the actual voice. |
| Tapping the face makes it flinch and sends out a ring | spec `interaction.tap`; `FaceView.kt:886-890`, `:1030-1039` | An "I felt that" within one frame. |
| Deciding an approval vibrates (Confirm/Reject) | `approval/ApprovalCard.kt:160-167` | The decision is felt, not just seen. |
| Talk-button press and slide-to-cancel vibrate | `parts/VoiceButton.kt:113`, `:147` | Good. |
| "One moving thing at a time" on the phone | `docs/UI-AUDIT-2026-09-23.md:59`; `ui/Nav.kt:223-226` | This is the rule that keeps things from getting busy. Every proposal below respects it. |
| The desktop answer paints at most every 100 ms, and each new block fades in once | `main.js:555-584`; `style.css:917-929` | Text arrives instead of snapping in. |

---

## Findings (checked against the source)

### F1. The desktop face does not hear you, and it speaks to a made-up rhythm (high)

- The face windows (the Widget and the HUD) embed `faces.html` in display
  mode. That page's message handler accepts only `state` and `appearance`
  (`faces.html:5182-5201`). No level is ever passed in.
- `voice.js` has `attachSpeechSource` and `attachMicSource`, written for
  exactly this job (`voice.js:278-293`). A search of every `.js` and `.html`
  file in `jarvis-desktop/src` finds **no caller** of either one.
- The voice.js comment says "Nothing in this build plays TTS yet" (TTS means
  text-to-speech, the spoken voice). **That comment is out of date.**
  `main.js:3212-3221` plays each spoken clip with `new Audio(dataUri)` in the
  ask-bar window.
- So `voiceLevel()` always goes stale and falls back to the made-up syllable
  generator (`faces.html:3303-3306`). "Listening" sits at the flat 0.28
  floor, because `HUD.raw` is never set (`faces.html:3251`, `:3295-3297`).
- The loudness is already computed. Rust works out the microphone's RMS level
  (RMS is a standard way of measuring loudness) for every audio chunk in its
  voice-detection loop (`src-tauri/src/voice.rs:1475`). It is used for
  detecting speech and then thrown away.
- The phone does all of this properly. So the two apps disagree on the single
  most "alive" thing the product does.

### F2. The ask-bar reactor ignores the spec's state language, and it gets busy while streaming (medium)

- It is a 48-unit SVG with its own CSS animations (`index.html:50-73`;
  `style.css:327-418`). For approval it turns amber
  (`style.css:1676-1693`), and for error it turns red (`style.css:411-418`).
  It keeps spinning forwards at the same speed in both states. The spec says
  approval must be "legible with no colour at all" (spec
  `approval_overlay`), and that error is the one thing that runs backwards.
  For someone with red-green colour-blindness, amber and red on a 48 px
  reactor are hard to tell apart (spec `colour_science`).
- While an answer streams in, all of these run at the same time, each on its
  own timing:
  - halo breathing, every 3.4 s (`style.css:327-331`)
  - core pulse, every 2.6 s (`:359-364`)
  - outer ring, every 2.2 s while streaming (`:397-400`)
  - middle ring, every 1.5 s, backwards (`:346-350`, `:402-405`)
  - status dot pulse, every 1.1 s (`:724-728`)
  - hairline scan, every 1.6 s (`:186-210`)
  - blinking cursor, every 1 s (`:896-911`, shown at `main.js:2586`)

  That is seven loops with seven different timings, all drifting against each
  other. This is exactly the "busy" the owner asked us to avoid. Even when
  idle, four of them keep going (halo, core, and both rings).

### F3. Reduced motion means three different things (medium)

- **Phone face:** "calm" runs at 2/3 speed, and it drops the error shake, the
  tap flinch and the speech push (`FaceView.kt:106-118`, `:800`, `:1030`,
  `:1063`). The colour patterns and the flash limits still run in real time.
  This is the best of the three.
- **Desktop face:** it keeps its full speed but draws only 10 frames a second
  (`faces.html:3990-4012`, `:5159-5165`). **It still shakes on error and
  flinches on click**, because nothing checks `CALM` there
  (`faces.html:3687-3698`, `:3722-3746`). At 10 frames a second the shake
  becomes a few large jumps, which is worse for someone who gets motion-sick,
  not better.
- **Desktop windows:** `style.css:1755-1788` keeps short 120 ms fades on
  purpose ("a cross-fade is not motion", so a state change still has a
  channel). `widget.css:877-884` and `jarvis_hud.html:449-451` squash every
  transition to about 0 ms, which gives hard cuts. The very reason
  `style.css` gives against doing that applies to them too.

### F4. The phone's list pops, and its streaming text snaps (low-medium)

- Approval cards are keyed items (`HomeScreen.kt:1008`
  `items(state.pending, key = { it.id })`), but nothing in the phone app uses
  `animateItem` (a search of `ui/` found none). So a new card appears in one
  frame, and when the desktop removes a decided card the whole list jumps up
  by that card's height.
- New answer paragraphs are plain `Text`s added in one frame
  (`HomeScreen.kt:1983-1990`). The desktop fades each new block in
  (`style.css:917-929`).

### F5. Letting go of the talk button is the one voice moment with no response (low)

- Press vibrates (`VoiceButton.kt:113`) and cancel vibrates (`:147`). Release
  only calls `onRelease()` (`:167`). The "I heard you" sound is off by
  default (CLAUDE.md, 2026-09-25; `voice-flow.js:262-290`). So with default
  settings, the moment your turn is caught gives you nothing to feel or hear.
  The face goes from listening to thinking with a 300 ms colour fade, and
  that is all.

### F6. Possible: the phone's face may run slightly ahead of Jarvis's voice (not measured)

- The level is published when the samples are *queued* into the AudioTrack
  (Android's audio player), not when they are *heard*
  (`Speaker.kt:274-276`; the code's own comment at `:279-280` says write()
  returns when queued). The on-device voice engine's path publishes the level
  when the audio is made (`:401-407`), and that can also run ahead of
  playback. How big the lead is depends on the audio buffer size. I have
  **not** measured it. If it is over about 80 ms, the face's pulses will
  visibly come before the syllables.

### F7. Possible: a brief "idle" blink between listening and thinking on the phone (not measured)

- When your voice is being checked, the phone shows THINKING from its own
  knowledge. But for its local THINKING and SPEAKING phases it deliberately
  lets the server's `activity` decide (`JarvisRuntime.kt:3794-3800`). If the
  server's event arrives after the phone's phase changes, the face falls
  through to IDLE for that gap (`:3822-3829`). The 300 ms colour fade would
  soften it, but the motion table would switch twice. Worth a log line to
  confirm before fixing.

### F8. The approval knock never relaxes (owner's call, not a bug)

- The knock ring leaves the core every 1.6 s for as long as a card waits
  (`FaceView.kt:1254-1256`). The 20 s clock arc then stays full
  (`FaceView.kt:1048-1054`). That is right for the first minute. A card the
  owner has chosen to leave until later keeps knocking at the same pace
  forever, and that is the one part of the face that can start to feel like
  nagging.

---

## Proposals

Each proposal lists what it costs in speed and battery, and what it does under
reduced motion. "Both apps" says where it belongs. Suggested order at the end.

### P1. Make the desktop face hear and speak for real (fixes F1)

- **What:** feed three levels into the display-mode face.
  1. **Jarvis's voice.** In `main.js`, attach `voice.js`'s existing
     `attachSpeechSource` to each clip's `Audio` element in `playClip`
     (`main.js:3212`). Share the level with the other windows through a
     `BroadcastChannel` (a same-origin browser message channel that every
     Jarvis window can listen to), about 30 times a second, only while a
     clip plays.
  2. **Your voice.** Have Rust emit the RMS it already computes at
     `voice.rs:1475` as a small event, about 20 times a second, **only while
     listening**.
  3. `faces.html`'s display mode listens and calls `setLevel` and
     `setSpeechLevel`. They already exist and already do all the smoothing
     (`faces.html:3251`, `:3282`).
- **Why:** this is the biggest single "alive" gain available. The face stops
  pretending.
- **Cost:** an AnalyserNode (the browser's built-in audio level meter) reading
  512 samples per frame is a fraction of a millisecond. The messages are tiny.
  There is no new drawing, because the face already draws every frame while
  speaking and listening. Battery: nothing worth measuring on a desktop.
- **Reduced motion:** `voice.js` already writes 0 under reduced motion
  (`voice.js:254`). In the face, follow the phone's rule: drop the scale push
  and keep the brightness lift. The lift is light, not movement, and the
  flash limits still police it.
- **Both apps:** the phone already does this. After this change they match.
- **Also:** fix the out-of-date "Nothing in this build plays TTS yet" comment
  (`voice.js:280-282`).

### P2. Teach the ask-bar reactor the face's language, and give it one clock (fixes F2)

- **What:**
  - **Approval:** one ring that leaves the core every 1.6 s, drawn as a CSS
    `transform: scale` + `opacity` keyframe on one extra `<circle>`. It is
    the same "knock" as the big face. Add a static partial arc to the outer
    ring, so the state reads with no colour.
  - **Error:** the rings stop, then turn slowly backwards
    (`animation-direction: reverse`, 3 to 4 times slower). Add a visible gap
    in the outer ring (a static `stroke-dasharray` change), so a still frame
    also reads as "broken".
  - **Streaming:** keep **one** moving signal on the bar. Either the reactor
    spins up or the hairline scan runs, not both. Stop the status-dot pulse
    and the cursor blink while text is arriving, because the text growing is
    already the motion. Put the loops that remain on one shared timing (for
    example 1.6 s and 3.2 s), so they move together instead of drifting.
  - **Idle:** breathing only (halo and core). The rings stop spinning. This
    matches the spec's idle "breathe" pattern (spec `states[idle]`).
- **Cost:** it goes down. There are fewer running animations, and everything
  is `transform` and `opacity`, which the graphics card handles without
  redrawing the page (`style.css:163-175` explains why that matters).
- **Reduced motion:** approval shows the static arc, error shows the static
  gap, and both have their colour. Nothing loops. This already fits the
  `style.css:1763` block.
- **Both apps:** the phone has no ask-bar reactor, so this is desktop only,
  and it matches the phone's face.

### P3. One reduced-motion rule everywhere (fixes F3)

- **What:**
  - **Desktop face:** adopt the phone's "calm". That means 2/3 speed at the
    normal state frame rates (30 for idle), no shake, no flinch, and no
    speech scale push. Keep the tap ring and the error's stop-then-crawl.
    Drop the 10-frames-a-second stepping.
  - **Widget and HUD CSS:** use `style.css`'s policy (loops stop, nothing
    moves or scales, 120 ms colour and opacity fades stay) instead of
    squashing everything to 0 ms.
- **Cost:** at worst the desktop face draws 30 frames a second in calm
  instead of 10. That is small next to the Brain window's own drawing, and it
  only applies to people who have reduced motion turned on.
- **Reduced motion:** this *is* the reduced-motion fix. It also removes the
  shake and flinch that currently ignore the setting.
- **Both apps:** afterwards both follow one rule, and it can be written once
  in the spec (a new `calm` block) so it stays in sync.

### P4. Entrances and exits for phone list items, and fading paragraphs (fixes F4)

- **What:**
  - Add `Modifier.animateItem()` to the keyed items in `HomeScreen.kt`'s list
    (approvals, the reply, the notices). It is in Compose Foundation, and the
    app is on BOM 2026.06.00 (`app/build.gradle.kts:284`). A card fades and
    slides in. When the desktop removes it, it fades out and the cards below
    glide up instead of jumping.
  - This does **not** change the rule that a card leaves only when the
    desktop says so (`ApprovalCard.kt:206-217`). The exit plays *after* the
    item is gone from `pending`.
  - Fade each new answer paragraph in once, over the theme's `enter`
    duration (200 ms), keyed by its position. That is the same idea as the
    desktop's `.fresh` class.
- **Cost:** it runs only when an item is added or removed. It is a
  graphics-layer fade, with no recomposition while it runs. Nothing loops.
- **Reduced motion:** `LocalMotion.current.enter()` is already 0 ms under
  reduced motion (`JarvisTheme.kt:202-206`), so this turns into an instant
  change automatically.
- **Approval cards stay plain:** the entrance is 200 ms, once. The card has
  no glow, no pulse and no loop. The face's knock remains the thing that
  pulls the eye.

### P5. "Caught it": pair a vibration, a face beat and the optional sound on release (fixes F5)

- **What:** on a real release (not a cancel), the phone does one light haptic
  tick (a haptic is a small vibration, here Compose's
  `HapticFeedbackType.GestureEnd` or `SegmentTick`, whichever feels lighter
  on the device). The face does one short "inhale": the listening scale push
  contracts toward the core over about 150 ms before thinking starts. The
  existing "I heard you" sound, if the owner has switched it on, lands on the
  same beat.
  - Desktop: the same inhale on the face when the turn is cut (the Rust
    `VOICE_HEARD` event already exists, `voice.rs:1690`). There is no
    vibration on a PC.
- **Cost:** the inhale sits inside the 600 ms full-speed window that every
  state change already gets (`Spec.kt:85`). There is no extra loop. The
  vibration costs nothing measurable.
- **Reduced motion:** no inhale. The vibration stays (it is not motion), and
  it follows the phone's own "touch feedback" setting through
  `LocalHapticFeedback`. The sound follows its own switch.
- **Both apps:** yes, as described.

### P6. A small beat for each tool step while Jarvis works (new)

- **What:** each tool `step` event (the same events the phone's "What Jarvis
  is doing" list shows, `StepsPlate.kt`) sends one faint ring *inwards* from
  the rim, the reverse of the tap ring. Long thinking then shows progress
  instead of one endless identical sweep. It is limited to at most one ring
  per 700 ms, which stays well under the 3-changes-per-second flash limit
  (`Spec.kt:90`).
  - It must not use notches. Notches already mean "things waiting" in banked
    (spec `state_transforms.states.banked`).
- **Cost:** a one-off overlay inside the thinking state, which already draws
  at full speed. Nothing extra.
- **Reduced motion:** off. The text line ("Checking your calendar…") already
  carries the same information.
- **Both apps:** yes. It is one shell-level overlay each (FaceHost on the
  phone, `drawStateOverlay` on the desktop), so the twenty faces need no
  changes.

### P7. Lip-sync and state-hold checks on the phone (F6, F7; measure first)

- **F6:** log the gap between `_level` updates and
  `AudioTrack.getTimestamp()` (the player's report of what has actually
  played) on the owner's phone. If the lead is over about 80 ms, delay the
  level by that much, or read the level at the play position instead.
  Cost: nothing.
- **F7:** log the face state once every 50 ms around a voice turn. If an IDLE
  frame shows up between listening and thinking, hold the local phase's face
  for up to 1.5 s until the server confirms. Cost: nothing.
- **Reduced motion:** not affected.

### P8. A patient knock (owner's call; F8)

- **What:** after about 60 s of waiting, the knock slows from every 1.6 s to
  every 4 s. The full amber arc, the colour and the card itself stay exactly
  as they are. A new card arriving restarts the fast knock.
- **Why it is the owner's call:** it touches how unmissable approvals are.
  The argument for it is that a knock nobody answers teaches the eye to tune
  it out. The argument against is "never make approval quieter".
- **Cost:** it goes down.
- **Reduced motion:** today the knock keeps running under calm, only slowed
  to 2/3 speed, because it runs on the face's motion clock (`FaceView.kt:1256`
  reads `f.t`, which is `motionT`). A ring that keeps leaving the core is
  motion. Under calm it could be shown as a still second ring instead, with
  the arc and the colour unchanged. That is also the owner's call.

### P9. The GL faces do not fade when you leave Home (small, known)

- `Nav.kt:240-243` already records that Tokamak and Membrane stay solid for
  the 200 ms fade and then vanish. That happens because they draw on their
  own separate surface (a GLSurfaceView), which ignores the fade.
- **Fix:** a Box painted in the well colour, placed over the face, whose
  alpha goes from 0 to 1 during the exit. Compose draws over a SurfaceView
  normally.
- **Cost:** one fill, for 200 ms. **Not tested on a phone.**
- **Reduced motion:** transitions are already off under reduced motion, so
  this never runs then.

---

## Ideas considered and turned down

| Idea | Why not |
|---|---|
| A typing spinner or animated "…" while waiting for the first word | The face is already thinking. A second moving thing breaks "one moving thing at a time" (`UI-AUDIT-2026-09-23.md:59`). |
| A glow or pulse on approval cards | Cards must stay plain and unmissable, never decoration. The face's knock is the attention signal. |
| The spec's planned "transcript orbiting the rim while speaking" (spec `interaction.planned`) | Moving text is hard to read, and it turns the face into a second place to read. It is busy by definition. |
| The spec's planned "banked items as particles in the outer ring" | Banked is still on purpose ("Still - not slow, STOPPED", spec `states.banked.why`), and the phone draws it at 2 frames a second. Particles would undo both. |
| Gyro parallax on the phone (spec `interaction.planned`) | It keeps the motion sensor running while the face is visible, which costs a constant bit of battery for a 2-3 px effect. Maybe later, only in active states and never in calm. Not a priority. |
| Blur, glass, full-screen shaders | Already refused on cost (`UI-AUDIT-2026-09-14.md`, "Refused, with reasons"). Nothing has changed since. |
| Speeding anything up past 1x | Standing rule: motion settings only slow things down (`face-tuning.js:36-44`; `AppearanceStore.kt:569-584`). |

---

## Suggested order

| # | Change | Apps | Effort | Cost |
|---|---|---|---|---|
| 1 | P1 real voice levels on the desktop face | Desktop (JS + a small Rust event) | M | ~0 |
| 2 | P2 ask-bar reactor: state language and one clock | Desktop CSS/SVG | S | goes down |
| 3 | P3 one reduced-motion rule | Both (desktop mainly) | S | ~0 |
| 4 | P4 phone list entrances and paragraph fades | Phone | S | only when things change |
| 5 | P5 "caught it" on release | Both | S | ~0 |
| 6 | P7 measure lip-sync and state-hold | Phone | S (logs) | 0 |
| 7 | P6 step beats | Both | M | ~0 |
| 8 | P8 patient knock | Both | S | goes down (owner's call) |
| 9 | P9 GL fade cover | Phone | S | 200 ms fill |

Each phone change needs a CI round trip (about 15 minutes), so items 4, 5 and
6's phone halves are best shipped together. Items 1-3 can be checked locally
with the Windows-target `cargo check` / `clippy` for the Rust event and the
existing `jarvis-desktop/tests` (contrast, a11y and themes) for the CSS.

## Not checked

- Whether the server reports `activity = speaking` while the desktop's own
  `main.js` plays a clip. P1 assumes the face is already in "speaking" then.
- Whether an in-app vibration when an approval arrives would double up with
  the approval notification's own vibration (`JarvisApp.kt:53-66`). That is
  why I did not propose one.
- Anything on real hardware. All costs here are reasoned from the code, not
  measured.
