# Hyperframes composition brief: Jarvis v6

## Output

- `composition/index.html` → `jarvis-launch-v6.mp4`: 1920×1080, 30 fps, 25.6 s.
- `composition/vertical.html` → `jarvis-launch-v6-vertical.mp4`: 1080×1920, 30 fps, 13.6 s. Render it with `npx hyperframes render -c vertical.html`.
- `jarvis-launch-v6.jpg`: the poster.

## Creative contract

`brag-plan.md` holds the storyboard and the evidence table. It was planned by
a six-member review of v1 to v5 (an AI engineer, a motion director, a launch
strategist, an everyday-viewer panel, a sound designer and an honesty
skeptic) and a moderator who settled their disagreements.

## How to make it again

1. `python3 tools/build_html.py` writes both HTML files from one template.
2. `python3 tools/score.py` writes the music and the glow data from the
   timing tables. It stops with an error if the limiter works more than 3 dB.
3. Render both cuts. Then remux the score into each file (see the README in
   `videos/`), and keep each file under 100 MB.

## Implementation

- **One engine for both cuts** (`assets/glass.js`), with the same contract as
  v3 to v5: one paused GSAP timeline drives a clock, and `render(t)` sets every
  visible value as a pure function of t. Scenes key off `assets/timing.json`
  and `timing-vertical.json`, which the score is written from too.
- **"Glass & Light":**
  - The reactor (the app's own `faces.html`, extracted by
    `tools/extract-reactor.mjs` from main; it changed since v5) is the only
    light, and its state colour tints the backlight and the glass rims.
  - Real screens sit on glass slabs that arrive with a short turn in depth,
    then stay flat and still.
- **Effects, all written here and deterministic:**
  - the iris from the reactor's core, with a thin colour fringe on its edge;
  - seeded canvas particles for the ignition and the settle;
  - an SVG tracing beam;
  - a touch ring;
  - a freeze and a dip on "Stop".

  The registry items the plan named (`sdf-iris`, `particle-text-dissolve`,
  `tracing-beam`, `touch-indicator`, `focus-blur-resolve`) were replaced by
  these fallbacks, so that every frame is a pure function of t in one engine.
- **Real screens** (`assets/ui/`): the desktop app's Jarvis bar, rendered
  headless from main's `jarvis-desktop/src` with the repo's own Tauri
  stand-in. The step line is the app's own `step-words.js`. "Where this came
  from" and the quote warning come from the backend's own `jarvis_sources.py`,
  run on a made-up web-search result. Text size is the app's own 150 % setting.
- **Drawn, not captured:** the Android phone (its Brain › Model list and the
  approval card), with jarvis-client's own strings only (cited in
  `tools/build_html.py`).
- **Type:** Inter, and IBM Plex Mono (the app's own font), both under the SIL
  Open Font License (`assets/fonts/`).
- **Score** (`tools/score.py`):
  - "clean machine": F♯ Lydian, 150 BPM played half-time;
  - FM bass, a wavetable pad, UI ticks, pings and a chime;
  - a tape-stop and real silence after "Stop";
  - −14 LUFS, a loudness range of about 6 LU.
