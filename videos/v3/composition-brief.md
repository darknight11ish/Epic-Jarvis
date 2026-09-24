# Hyperframes composition brief: Jarvis v3

## Output
- `composition/index.html` → `jarvis-launch-v3.mp4`: 1920×1080, 30 fps, 35 s.
- `composition/vertical.html` → `jarvis-launch-v3-vertical.mp4`: 1080×1920, 30 fps, 15 s.
  Render it with `npx hyperframes render -c vertical.html`.
- `jarvis-launch-v3.jpg`: the poster.

## Creative contract
`brag-plan.md`: what changed from v2 and why, plus the evidence table that ties every line on screen to the code and gives each one a status.

## Implementation
- **One engine for both cuts**, `assets/film.js`:
  - One paused GSAP timeline drives a clock, and `render(t)` sets every visible value as a pure function of t. A seek always equals playback.
  - Scenes and captions key off one timing table: `assets/timing.json` and `timing-vertical.json`, mirrored in the `.js` files. The score is written from the same table.
  - A film that lacks a scene's element or hit simply skips it.
- **Layout.**
  - `assets/film.css` is the landscape layout.
  - `assets/film-tall.css` re-lays the same scenes out for an upright phone. Nothing is cropped from the landscape version. Words stay clear of the top 200 px and the bottom 300 px.
- **The reactor faces** are the app's own code, from `jarvis-desktop/src/faces.html` (`tools/extract-reactor.mjs`): the big one, and the small one on the phone, whose "waiting on you" clock is real.
- **Real screens** (`assets/ui/`) are captures of the desktop app's own windows with sample data:
  - the quick-ask approval card for a browser plan (`control_browser`), its text from `jarvis_browser_control.describe()`;
  - Brain › Memory's proposal card;
  - the "What did you know on…" view;
  - the facts list with a retired fact.
- **The phone approval card** is redrawn from `ApprovalCard.kt`: countdown, title from `PendingRows.kt`, command, buttons. The fingerprint sheet follows `BiometricGate.kt`, which passes it the card's title and "why".
- **Score:** `tools/score.py` writes `assets/music/score.mp3`, `score-vertical.mp3` and the matching `audio-data*.js`. The low-band envelope drives the reactor's glow. The music stops dead on "Stop." and stays silent until the next cut.

## Look
- Dark, with the app's accent `#38f0ff` and the reactor's own state colours. Only the reactor glows.
- Chakra Petch 600 in sentence case for at most one headline per screen. IBM Plex Sans for captions.
- Four moves only:
  - the reactor crossfades between states;
  - cards slide in and settle;
  - the fingerprint ring fills;
  - the phone and the PC clear together, then the visible browser does the approved steps.
