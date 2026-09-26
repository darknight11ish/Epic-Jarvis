# Hyperframes composition brief: Jarvis v5

## Output

- `composition/index.html` → `jarvis-launch-v5.mp4`: 1920×1080, 30 fps, 30 s.
- `composition/vertical.html` → `jarvis-launch-v5-vertical.mp4`: 1080×1920, 30 fps, 15 s. Render it with `npx hyperframes render -c vertical.html`.
- `jarvis-launch-v5.jpg`: the poster.

## Creative contract

`brag-plan.md` holds the storyboard and the evidence table. That table ties
every claim on screen to the code on the feature branch.

## How to make it again

1. `python3 tools/build_html.py` writes both HTML files from one template.
2. `python3 tools/score.py` writes the music and the glow data from the
   timing tables.
3. Render both cuts. Then remux the score into each file (see the README in
   `videos/`: the renderer once lowered the music), and keep each file under
   100 MB.

## Implementation

- **One engine for both cuts** (`assets/day.js`), with the same contract as
  v3 and v4: one paused GSAP timeline drives a clock, and `render(t)` sets
  every visible value as a pure function of t. Scenes key off
  `assets/timing.json` and `timing-vertical.json`, which the score is written
  from too.
- **One continuous shot.** Each moment of the day is a "station" on one long
  strip. The camera dwells on a station with a slow drift, then glides to the
  next with an ease; it never cuts. The upright cut runs the same strip top to
  bottom.
- **The ribbon of hours** is placed along the strip so that the hour under the
  playhead is the station's hour. The sky's two colours, the glow behind the
  reactor, and the ink (dark by day, cream at night) are all read from that
  hour, so the light follows the camera.
- **The reactor** is the app's own code: `jarvis-desktop/src/faces.html`,
  extracted by `tools/extract-reactor.mjs` from the feature branch
  (unchanged since v3). It is the playhead, and at the end it leaves the
  ribbon and settles in the middle, asleep.
- **Real screens** (`assets/ui/`): the desktop app's own windows, rendered
  headless from the feature branch's `jarvis-desktop/src` with the repo's own
  Tauri stand-in, in the app's light "paper" theme by day and its dark theme
  at night. Their text was produced by running the backend's own functions
  (`jarvis_briefing`, `jarvis_focus.Engine`, `jarvis_tellme`) with made-up data.
- **Drawn, not captured**, because they are Android's: the phone's
  notification and the phone app's Mind › Doing plate. Their words come from
  the code cited in `brag-plan.md`.
- **Type:** Fraunces and Inter, both under the SIL Open Font License
  (`assets/fonts/`).
- **Score** (`tools/score.py`): an original, fully synthesised warm groove at
  96 BPM that follows the day (see its docstring).
