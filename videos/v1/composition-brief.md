# Hyperframes Composition Brief: Jarvis (v2)

## Objective
A 25-second, beat-cut, sci-fi-trailer launch video for Jarvis that shows the
real reactor face and the real approval flow, and lands on "Your assistant.
Your PC. Your rules."

## Output
- Composition directory: `videos/v1/composition/`
- Rendered video: `videos/v1/jarvis-launch-v1.mp4`
- Format: landscape — 1920x1080, 30 fps
- Duration: 25 s

## Source Material
- Project root: `/home/user/Epic-Jarvis`
- Primary files read: `jarvis-desktop/src/faces.html` (the reactor renderer),
  `jarvis-desktop/src/jarvis-visual-spec.json` (palette, patterns, states,
  approval clock), `jarvis-desktop/src/widget.html` (desktop widget bar:
  status dot, LOCAL route pill, quick-capture chips),
  `jarvis-client/.../ui/approval/ApprovalCard.kt` (card anatomy, "Swipe right
  to approve, left to deny — …", "Expires in 0m 47s", Approve / Deny),
  `jarvis-client/.../ui/screens/HomeScreen.kt` (link labels "Waiting on you",
  "Linked"), the owner's video brief, and the owner's Reactor Kit screenshot.
- Product name: Jarvis
- Tagline / strongest claim: "Your assistant. Your PC. Your rules."
- Key visual to recreate: the Arc reactor face in its thinking state — not
  recreated: lifted verbatim (see `tools/` and `assets/reactor.js`).
- Copy that must appear verbatim: "Hey Jarvis." / "Nothing leaves the room." /
  "Your assistant. Your PC. Your rules."

## Creative Direction
- Tone preset: cinematic; creative direction: "sci-fi trailer, cut to the beat"
- Interpretation: cinematic type, trailer pacing; every cut on a beat of a
  120 BPM grid; slams fast-in, then hold for reading.
- Hook: ignition from black → braam on 2.0 s → "Hey Jarvis."
- Outro: three braams, three lines, JARVIS, fade.
- Avoid: generic SaaS language, abstract filler, any claim outside the brief.

## Visual Identity
- Background `#04070c`; ink `#dbe7f2`; dim `#8fa3b8`
- State colours from the spec (ice idle, ember listening, azure→violet
  thinking sweep, amber approval, ice speaking)
- Display: Chakra Petch 700; HUD/body: IBM Plex Mono 500 (the app's own
  bundled font files)

## Storyboard
Contract: `brag-plan.md`. Scene summary:
1. Ignite — 0-2 — Arc spins up from a point, HUD draws on
2. Hey Jarvis — 2-3.5 — listening-ember, RGB-split slam
3. Nothing leaves the room — 3.5-5.5 — data tags bounce off the room wall
4. A face that's alive — 5.5-7.5 — Geodesic / Rime / Fullerene / Spiral, one per beat
5. It listens / thinks / speaks — 7.5-10.5 — Arc changes state on the beat
6. Interrupt — 10.5-13 — reply streams, "STOP." cuts picture and music together
7. It asks first — 13-18 — spoken request, phone approval card, swipe, approved
8. Your GPU, not their cloud — 18-21 — chromatic wipe; desktop + phone on a private mesh; cloud path breaks
9. Your rules — 21-25 — violet Arc over the anamorphic-flare block; three lines; JARVIS

## Audio
- Role: dense rhythmic layer (original trailer score, `tools/score.py`)
- Music: `assets/music/score.mp3`, 120 BPM, A minor, -14 LUFS (linear)
- Cue source: by construction — the score and the picture read the same
  `assets/timing.json`. Strong cues: 2.0 (braam), 11.5 (hard silence), 21.0 (braam).
- Audio-reactive: the score's low-band envelope (`assets/audio-data.js`, 30 fps)
  drives the reactor's glow and its core bloom (`HUD.beat`).
- SFX (from the /brag library, mixed into the score at the animation's times):
  glitch ticks on montage cuts, key ticks while the reply streams, card slide
  when the phone arrives and on the swipe, confirmation chime, bell on JARVIS.

## Hyperframes implementation notes
- Registry items used: `vfx-anamorphic-flare` (mounted block, tinted to the
  violet family), `grain-overlay` (pasted), and the techniques of
  `rgb-glitch-text` (three stacked copies driven by CSS variables),
  `scramble-reveal` (left-to-right glyph lock), `telemetry-hud`
  (attribute-drawn brackets, text-at-time readouts), `headline-slam`
  (three-frame landing shake) and `chromatic-aberration-wipe` (clip-edge wipe
  with RGB-split sheen).
- One paused GSAP timeline. One driver tween calls `render(t)`, which owns
  every canvas, every per-frame text value, the reactor framing and the
  camera hits, all as pure functions of `t`.
- Determinism: faces re-seed `Math.random` from their id before every draw;
  scrambles and grain use integer hashes of the frame number.
- `hyperframes check`: 0 errors; the remaining warnings are the advisory
  "split into sub-compositions" notes and four data tags that overlap only
  while invisible at the start of scene 3.
