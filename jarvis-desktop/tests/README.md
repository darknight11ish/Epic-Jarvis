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
| `npm run test:ui` | the HUD window served exactly as the packaged app serves it (Tauri's header CSP with its script hashes) and actually sending a message; then the audited ship blockers, each one a bug that shipped, and the IA findings — things that were unreachable and things that were not true; and `continuity.mjs`, which holds the desktop to the phone: the same three themes and names, Ember mapped to Reactor, one set of words for the link, and the face settings slow-down only; and `learning.mjs`, the right/wrong mark on an answer and the review cards that say what their buttons do; and `task-controls.mjs` and `notes.mjs`, Pause/Resume/Stop and Logseq/Joplin/Obsidian notes believing only what the PC reports, including which note apps it is set up for; and `provenance.mjs` and `history.mjs`, chat history on the PC: every turn says where its words came from (typed, pasted, clipboard, voice) and keeps saying it, and the Brain's History tab lists, opens and deletes one conversation at a time, with the switch that waits for its approval card; and `auto-learn.mjs`, automatic learning on the Memory tab: its two switches that wait for their approval cards (one raised on the phone too), the "Saved automatically" list with Forget and Load older, and the quiet "Jarvis remembered 2 things" line |
| `npm run test:a11y` | live regions, headings, the roving tablist, hue-only state, text scaling, and whether a disabled control is still readable in all three themes |
| `npm run test:themes` | every theme's contrast over a black **and** a white backdrop, every window's theme reach, and colour distinctness under three kinds of colour-blindness |
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
