# Hyperframes Composition Brief: Jarvis v2

## Output
- Composition: `videos/v2/composition/` (Hyperframes project, `index.html`)
- Video: `videos/v2/jarvis-launch-v2.mp4` — 1920x1080, 30 fps, 35 s
- Poster: `videos/v2/jarvis-launch-v2.jpg` (33.5 s, baked in as frame 0)

## Creative contract
`brag-plan.md` in this folder: the storyboard, and the evidence table that
ties every on-screen claim to a doc or commit and to its status (on today /
ready / next).

## Implementation
Built on the v1 engine (`videos/v1/composition/`):
- The reactor faces are the app's own code, lifted from
  `jarvis-desktop/src/faces.html` by `tools/extract-reactor.mjs`, drawn per
  frame (Arc, Geodesic, Spiral, Fullerene in this cut).
- One paused GSAP timeline; one driver tween calls `render(t)`, which owns
  every canvas, typed/decoded text, the reactor framing and the camera hits.
- Registry: `vfx-anamorphic-flare` (outro backdrop), `grain-overlay`, and the
  rgb-glitch-text / scramble-reveal / telemetry-hud / headline-slam
  techniques.
- New scenes for v2: the proposal card (Keep / Forget), the bi-temporal
  memory timeline with an AS OF scrubber, voice training, Smart Turn, and the
  graphics-card rack (today / ready / next).
- Score: `tools/score.py`, regenerated for 35 s from `assets/timing.json`;
  the music pauses with the Smart Turn pause and stops dead on "STOP.".

## Validation
`npx hyperframes check`: 0 errors, 70/70 text contrast checks. The remaining
warnings are the advisory "split into sub-compositions" notes.
