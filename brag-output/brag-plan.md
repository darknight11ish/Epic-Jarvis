# Brag Plan: Jarvis

## What is this app?
A private, local-first personal assistant — a Windows desktop app and an Android
phone app — that runs its AI model on the owner's own PC and graphics card, and
asks before it does anything with outside effects.

## The angle
Play it straight, like a product film for something serious: a dark reactor
face glowing on a black screen, a wake word, and a system that always asks
before it acts. The claim ("nothing leaves the room") is the whole hook — no
jokes needed, just confident, precise delivery. Every visual comes from the
real product: the actual reactor-face states and colours from
`jarvis-visual-spec.json`, the real approval-card countdown copy
("Expires in Xm Ys"), and the real closing line the owner chose.

## Hook (first 2-3 seconds)
Near-black frame. A single glowing face — cold cyan, idle — sits alone in the
dark. Text slams in: **"Hey Jarvis."** A beat. Then: **"Nothing leaves the
room."**

## Key moments (the middle)
Three highlights, chosen because they are the most visual features in the
brief and the ones with real, screenshot-able UI already in the repo:

- **Voice** — the wake word, the face shifting into its warm "listening"
  state, and the line "Speech is understood on the PC, not the cloud."
- **Animated faces** — the reactor face changing state/colour (idle →
  listening → thinking → speaking), gesturing at the "several styles and
  colour themes" the desktop and phone share.
- **Approval cards** — a card sliding in with a live countdown ("Expires in
  45s"), swiped to a decision, landing the "asks first, every time" claim.

## Outro / punchline
Phone and desktop side by side, faces in sync, then: **"Your assistant. Your
PC. Your rules."**

## User flow worth showing
1. **Entry** — the owner says "Hey Jarvis"; the reactor face wakes from idle
   (cool cyan) into its listening state (warm amber), reacting to voice the
   way `--state-listening` / `--state-thinking` / `--state-speaking` are
   defined in `jarvis-desktop/src/theme.css`.
2. **Key action** — Jarvis proposes something with an outside effect. An
   approval card appears with a live countdown, matching the real copy in
   `ApprovalCard.kt`'s `ExpiryCountdown` ("Expires in Xm Ys").
3. **Result** — the card is swiped to a decision (approve), the card's gone,
   the face settles back — nothing happened until that swipe.

## Tone
- Preset: cinematic
- Creative direction: dark, precise, a little cinematic — the reactor face
  as hero image, calm confidence rather than hype
- Interpretation: wide, deliberate shots; big type that lands and holds;
  dramatic reveals rather than rapid cuts; 4-5 scenes, each given room to
  breathe before the next begins.

## Format: landscape — 1920x1080
## Duration: 20s target (range 18-21s)

## Visual identity (from the project)
- Background: `--bg-window: rgba(8, 9, 12, 0.86)` over near-black —
  effectively `#08090c`, per `jarvis-desktop/src/theme.css`
- Accent: `--accent: #38f0ff` (cyan), with real face-state colours layered in:
  `--state-idle: #2ea8cc`, `--state-listening: #ff9b52`,
  `--state-thinking: #ae7bff`, `--state-speaking: #6fe3ff`,
  `--state-approval: #ffb648`
- Text: `--text: #f2f5f8`, muted `--text-muted: #a8b2c1`
- Display font: "Chakra Petch" (real bundled font, `jarvis-desktop/src/fonts/`)
- Body font: "Segoe UI Variable Display" / system-ui fallback
- Strongest visual element: the reactor face itself — a glowing, animated
  disc that changes colour and geometry with state, real to the product (20
  named designs — Arc, Orbit, Geodesic, Spectrum, Tokamak, Swarm, Coreplate,
  Workbench, Membrane, Nucleus, Comb, Iris, Shoal, Accretion, Cascade, Rime,
  Orbital, Fullerene, Spiral, Kirkwood — in `jarvis-desktop/src/faces-spec.js`)

## Share copy (draft)
Built my own Jarvis: a voice assistant that lives on my PC, answers to "Hey
Jarvis," and never sends my private life to anyone else's cloud. It asks
before it acts — every time.

## Audio direction
- Role: cinematic support — a low, steady bed with restrained swells under
  the two or three biggest visual beats
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady and
  clean, tempo ~110 BPM, the tones.md-recommended pick for `cinematic`)
- Music treatment: start near-silent under the hook, hold low (~0.3) through
  the middle, a small perceived lift into the approval-card beat, gentle
  fade on the outro line. Never above 0.4.
- Music cue guidance: preset read from
  `happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.md`. Target
  strong cues near 8.74s (Voice scene entrance) and 17.47s/18.56s (approval
  swipe / outro line landing) — within ±0.15s, and only if it doesn't cost
  readability. Beat grid available for any smaller staggered reveals.
- Audio-reactive treatment: subtle — let the reactor face's glow breathe
  gently with RMS/bass under the middle scenes; no waveform or equalizer
  visuals.
- SFX posture: sparse, 2-3 cues total, cinematic weight
  (`impact/impactBell_heavy_*`, `impact/impactSoft_medium_*`) — one on the
  face's first wake, one on the approval-card swipe, one on the final line.
- Audio-coupled moments: the wake-word text landing, the face state
  crossfade into listening, the approval card's swipe-to-decide gesture.
- Restraint rule: no dense SFX stacking, no aggressive stingers — this is
  "calm confidence," not a hype reel.

## Storyboard

### Scene 1 — Hook — 3.5s
Near-black frame (`#08090c`). A single reactor face (Arc/Coreplate-style
disc), idle state, cool cyan (`--state-idle #2ea8cc`), sits centered and
barely breathing. "Hey Jarvis." slams in bold Chakra Petch, holds ~1.3s, then
"Nothing leaves the room." settles below it, holds ~1.4s.
Sequential/interaction: none
Audio intent: quiet, tense anticipation — almost silent until the line lands
Audio-coupled idea: a single soft impact/bell cue under "Nothing leaves the
room" landing
Music: near-silent bed fading up from 0
Transition mood: dramatic wipe → Scene 2

### Scene 2 — Reveal: private by design — 4s
The face's glow reframes to suggest a graphics card silhouette in the
background (dark, precise, no literal hardware photo — an abstracted glow
shape). Text arrives: "Runs on your own graphics card." then "Email, files,
credentials, memory — never leave this PC."
Sequential/interaction: two lines arrive in sequence, second after first
settles
Audio intent: steady, grounding — the bed becomes audible and even
Audio-coupled idea: none, let the reveal carry
Music: bed rises to ~0.3
Transition mood: crossfade with scale (0.95→1.0) → Scene 3

### Scene 3 — Voice — 4.5s
The reactor face shifts from idle cyan to listening amber
(`--state-listening #ff9b52`), a visible state crossfade (per the product's
real ~300ms colour crossfade). Text: "Hey Jarvis." appears again, smaller,
as if spoken, then "Speech is understood on the PC. Not the cloud." A beat
where the face shifts to a violet "thinking" tint (`--state-thinking
#ae7bff`) suggesting it's working.
Sequential/interaction: face state crossfades idle → listening → thinking,
matched to the two lines of text
Audio intent: alert, attentive — the moment the product "hears" you
Audio-coupled idea: a soft interface tone on the state crossfade into
listening
Music: hold at ~0.3, nudge toward the 8.74s strong cue for the face's
listening-state entrance
Transition mood: clean dramatic wipe → Scene 4

### Scene 4 — Approval cards — 5.5s
Split composition: phone and desktop side by side, dark background. A card
slides in from the bottom on the phone side with a live countdown label
("Expires in 0m 45s", matching the real `ExpiryCountdown` copy) and the face
tints amber (`--state-approval #ffb648`) on the desktop side in sync. A
simulated right-swipe carries the card off-screen to a green approve edge.
Text: "It asks first. Every time." then "One card. One decision. Nothing is
ever auto-approved."
Sequential/interaction: yes — countdown ticks down briefly, then the swipe
gesture resolves the card; the two devices react together
Audio intent: the tension of a decision, then the small relief of it being
made
Audio-coupled idea: card-slide sound as it enters; a distinct swipe/impact
sound on the resolve
Music: aim the swipe-resolve near the 17.47s/18.56s strong-cue pair (±0.15s)
Transition mood: dramatic wipe → Scene 5

### Scene 5 — Outro — 3s
Phone and desktop rest side by side, faces settled back to idle cyan, in
sync. Final line lands large, centered: **"Your assistant. Your PC. Your
rules."** Long hold on the line before cut to black.
Sequential/interaction: none
Audio intent: a quiet landing — confidence, not triumph
Audio-coupled idea: one restrained final impact/bell cue under the line
Music: gentle fade down through the hold, out by the cut to black
Transition mood: soft hold → cut to black

**Music mood for this video:** cinematic, steady, restrained
**Audio summary:** A near-silent open that rises into a steady, even bed
through the middle, with two gentle lifts timed to the voice and approval
beats, fading to near-silence under the closing line — three sparse,
cinematic-weight SFX cues carry the rest.
