# UI tests

Three checks that run the real frontend rather than a copy of it, plus a
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
| `npm run test:tokens` | no colour is welded into a component where a theme cannot reach it. Needs Python, not Playwright. |
| `npm run test:ui` | the audited ship blockers, each one a bug that shipped |
| `npm run test:themes` | every theme's contrast, over a black **and** a white backdrop |
| `npm run shots` | renders every surface in every state into `tests/shots/` |

`npm test` remains the Rust suite and needs none of this.

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
