# UI tests

Ten checks that run the real frontend rather than a copy of it, plus a
screenshot harness.

They exist because this app has surfaces where being wrong is silent: a
contrast ratio nobody computed, a button pushed below a window clamp, a key
bound to the wrong decision. All three shipped at least once.

## Running them

Playwright is **not** a dependency of this package — it downloads several
hundred megabytes of browsers, and the first thing anyone does here is build
the app on Windows. Install it only when you want these:

```
npm i -D playwright
npx playwright install chromium
```

Then:

| command | what it checks |
|---|---|
| `npm run test:all` | everything below, in order |
| `npm run test:tokens` | no colour is welded into a component where a theme cannot reach it, and the `rgb(var(--hue-rgb) / a)` form actually resolves. The Python half needs no Playwright. |
| `npm run test:ui` | (among them `face-watchdog.mjs`: the faces' GPU watchdog, the animals' dimming and fallback pose, and the "Jarvis isn't connected" ring; and `face-pace.mjs`: the animals' resolution and frame-rate choices - Lower, Balanced, High and Maximum in the spec's, Settings' and the phone's words, Maximum traced at 2x2, the pick rule (90 is 72 on a 144 Hz screen), an animal resting at 60 or 30 and at the full rate while an idle happening plays, Auto's ladder down and its climb to Maximum, and the widget's face resting at all; and `animal-options.mjs`: the animals' sleeping Zs - on standby, never while not connected, following the head, one still z under reduced motion - "Keep the animal still" from Settings' Animal options (shared with the phone) to every face page, an old per-computer "on" kept until it has reached the PC, and an older PC's local-only switch, and the serious moment reaching the floating face) the HUD window served exactly as the packaged app serves it (Tauri's header CSP with its script hashes) and actually sending a message; then the audited ship blockers, each one a bug that shipped, and the IA findings — things that were unreachable and things that were not true; and `continuity.mjs`, which holds the desktop to the phone: the same three themes and names, Ember mapped to Reactor, one set of words for the link, and the face settings slow-down only; and `learning.mjs`, the right/wrong mark on an answer and the review cards that say what their buttons do; and `task-controls.mjs` and `notes.mjs`, Pause/Resume/Stop and Logseq/Joplin/Obsidian notes believing only what the PC reports, including which note apps it is set up for; and `provenance.mjs` and `history.mjs`, chat history on the PC: every turn says where its words came from (typed, pasted, clipboard, voice) and keeps saying it, and the Brain's History tab lists, opens and deletes one conversation at a time, with the switch that waits for its approval card; and `auto-learn.mjs`, automatic learning on the Memory tab: its two switches that wait for their approval cards (one raised on the phone too), the "Saved automatically" list with Forget and Load older, and the quiet "Jarvis remembered 2 things" line; and `erase.mjs`, "Erase the words" beside every Forget (on a forgotten fact too): it asks first, sends one id, is held on a stale link, and an erased fact shows only the date it was erased; and `memory-profile.mjs`, "Always keep in mind": its section with "N of 1,200 characters used" and Unpin, Pin beside every Forget, one fact per tap with no question, the PC's refusal in its own words, held on a stale link and hidden under Windows Hello; and `memory-used.mjs`, temporary chat and "Used in this answer": the mode only on a PC that has it, its marker and its one line, every question sent temporary and a new conversation each way, a PC that did not confirm it said plainly, "Remember: is off", and "Used 2 memories" opening those facts with Forget and Erase - asked first, one fact per tap, held on a stale link, hidden under Windows Hello - and the Brain's "Jarvis remembered 2 things" opening the facts themselves |
| `npm run test:a11y` | live regions, headings, the roving tablist, hue-only state, text scaling, and whether a disabled control is still readable in all three themes |
| `npm run test:themes` | every theme's contrast over a black **and** a white backdrop, every window's theme reach, and colour distinctness under three kinds of colour-blindness |
| `node tests/animal-settings.mjs` | "Animal options" (2026-09-28): the fallback switches and words are the PC's (`fixtures/animal-cases.json`, written by `jarvis_animal.py`), "make the animal sharper" steps the same way as the PC's rule from every start, and - with Playwright - Settings' one section: every switch the PC lists (the "coming in the next update" line on the ones not built yet), ONE change per tap, turning one on held on a stale link and off never, a phone change shown at once, the sky and the per-computer sharpness and frame rate inside it, the way to the face's voice, and the Jarvis bar applying `face_tuning` to this computer only. The first part needs no browser; CI runs it. |
| `node tests/sky.mjs` | the sun, the moon and the weather behind the animals (sky.js): the astronomy against published times (NASA's moon phases, London's solstice sunrise and sunset, an independent program for four more cities), the scene's promises (dark, behind the animal, above the monkey's vine at its top, still under reduced motion, a pure function of the clock), and - with Playwright - the face pages drawing it from this computer's store, dimming with the animal, and Settings' "Sun, moon and weather". The first part needs no browser; CI runs it. |
| `node tests/season.mjs` | the seasonal touches behind the character faces (season.js): the calendar (every season in both halves of the world, each holiday's first and last hour, time zones), what shows when (Still and serious moments hide it, an approval or an error holds it still, calm makes it fewer and still), no autumn leaves or winter snow in the tropics, no snowman for the owl (its branch covers that corner), the promises about how it looks (behind the face, slow, never flashing, never a state colour), and - with Playwright - the face pages drawing it from this computer's store, off by default, and Still hiding it. The first part needs no browser; CI runs it. |
| `node tests/animal-behaviours.mjs` | the new animal behaviours as the desktop feeds them (2026-09-28): a fact's nod, a long answer's glow and the focus buddy relayed into every face frame (face-moments.js) - never a nod while App lock or "Hide memory lists" is on, or before that is known, and never twice for a replayed event - and, with Playwright, the real face page handing the pose the switches, the owner's pauses, Jarvis's phrase ends (switched on when a real voice is first heard while speaking, never over one of the animal's own gestures, off when speaking ends), the moments, a focus session and its stretch once idle, a stroke across the Widget's face, the frame pacer's full rate for a cute moment, a stroke, a fact's nod and the focus stretch (and not for a happening a focus session took away), a face that has just opened not counted as rested, a face switched back to taking today's options at once, the seasonal touches never shown under Still while the options load, and switching faces: the goodbye, then the hello; a cross-fade under calm motion and while waiting on you; a fade for a face that is not a character; two instruments at once. The first part needs no browser; CI's backend job runs it too. |
| `node tests/face-bounds.mjs` | the animals' bounding volumes (2026-09-29, docs/CRITTERS.md "The bounding volumes"): about a hundred poses per animal drawn from four sides with the real shader and with the single outer sphere it replaced, pixel for pixel - no more than 8 pixels differ in one picture and under 0.7 a picture on average, so no hand, ear, tail or vine is cut off; CONTROL: with every sphere at half size the check does see the cut. Needs Playwright with WebGL (software is fine); part of `test:ui`. |
| `node tests/voice-speed.mjs` | the faces at every speed of Jarvis's voice (2026-09-28, docs/LIPSYNC.md "At every pace"): the phrase-end finder the talking gestures land on finds the end of sentences spoken back to back at the slowest and fastest pace, and never one inside a sentence; the robot's eyes pulse with the words at every pace, never busier than the syllables and never with a jump. Pure node, no browser; CI runs it. |
| `npm run test:voice` | the speech envelope against `jarvis-visual-spec.json`. Needs no browser. |
| `npm run test:release` | the updater's `latest.json`, as `.github/workflows/desktop-release.yml` writes it: the three Windows keys, the URLs, the signatures, and that it names the same release the app reads. Needs no browser; CI runs it. |
| `npm run shots` | renders every surface in every state into `tests/shots/` |

`npm test` remains the Rust suite and needs none of this.

Two of these need no browser at all — `check-tokens.py` and `voicecheck.mjs`
parse and compute rather than render — so they run on a machine with nothing
installed.

## Why both backdrops

These windows are frameless and transparent. A translucent surface composites
against whatever the user's wallpaper happens to be, so a pair can measure
9.8:1 over black and 2.21:1 over white — that exact case was live in the CSS
and is why sunken surfaces are opaque now. A checker that assumes a dark
desktop would have passed it.

## What the harness is not

`tests/uikit.mjs` stubs the Tauri bridge with payloads copied from what the
backend actually returns — `jarvis_arbiter.digest()`, `jarvis_gate.pending()`,
`jarvis_jobs`, `jarvis_undo`, `build_graph()` and the rest. That makes the
markup, the CSS and the JavaScript real, and the data plausible. It does not
test the Rust, the IPC or the backend, and a green run here is not evidence the
app launches on Windows.
