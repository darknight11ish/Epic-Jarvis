# Browser suites on the audit pass (PR #48)

Revision `d404063e`, the head of pull request #48 (`audit-pass-only`).
Run on the owner's Windows 11 PC, 2026-10-05, in a worktree of its own
(`jarvis-browser-pr48`, branch `browser-pr48`). The parallel run of the same
141 suites against `01425b52` (the pre-change baseline) is the other half of
the comparison; this page is the candidate side only.

**Headline: 141 suites ran, 137 passed, 4 exited non-zero (5 failing checks) -
and every one is the machine, not this pass.** No failure names a surface this
pass touched.

## How Playwright was installed

Exactly what `.github/workflows/ci.yml`'s "Install Playwright's Chromium" step
does, in `jarvis-desktop`:

```
npm install --no-save --no-audit --no-fund playwright
npx playwright install --with-deps chromium
```

Both succeeded. `playwright` is still not a dependency of `package.json`, as
`tests/README.md` intends — `--no-save` leaves the manifest alone. Chromium
v1243 (Chrome for Testing 153.0.8010.12) landed in
`%LOCALAPPDATA%\ms-playwright\chromium-1243`. `--with-deps` is a no-op on
Windows (it installs Linux system libraries) and did nothing harmful; the
browser download is what matters and it completed.

## The failures: 5 failing checks across 4 suites

Two of the four died on an uncaught exception rather than reporting a check,
so "failing check" is empty for those — the detail column is the exception.

| suite | failing check | what it reported |
|---|---|---|
| `account-secrets.mjs` | `CONTROL: there is no such page for the phone` | `Command failed: grep -rl 'account_secret\|Jarvis Backend/IMAP\|…' jarvis-client jarvis-android` — `'grep' is not recognized as an internal or external command` |
| `faces.mjs` | `the generated spec script matches the JSON it came from` | `spawnSync python3 ENOENT` |
| `faces.mjs` | `the animals' generated shaders, phone copies and pose fixture are up to date` | `spawnSync python3 ENOENT` (and, on the next check, `glslangValidator is not installed`) |
| `memory.mjs` | *(none — the process died)* | uncaught `Error: spawnSync python3 ENOENT` at `tests/memory.mjs:31` (`realPython`), thrown from line 275. Checks 1–14 had passed; the suite stopped there |
| `voice-training.mjs` | *(none — the process died)* | uncaught `Error: spawnSync python3 ENOENT` at `tests/voice-training.mjs:1058` (`realCalibrate`), thrown from line 1061. Checks 1–33 had passed; the suite stopped there |

All three missing tools, named by `Get-Command` on this PC:

```
python3         : NOT FOUND   (python 3.12 IS installed, as `python`)
grep            : NOT FOUND   (it is a Unix tool; CI is ubuntu-latest)
glslangValidator: NOT FOUND   (shader_size.py's own precondition)
```

## What each failure is, in my judgement

**(c) environmental — all four, and I am not unsure about any of them.**

- `account-secrets.mjs` calls the Unix `grep` through `execSync` (line 214).
  There is no such program on Windows. The check itself is a CONTROL — it
  greps the two phone apps for backend-only strings. `git grep` is in the box
  and would answer the same question; the suite was written for CI, which has
  `grep`. **Not this pass**: the file is untouched by `01425b52..d404063e`.

- `faces.mjs`, `memory.mjs`, `voice-training.mjs` all invoke `python3`. This
  PC has Python 3.12 named `python`. The three suites are written for
  `ubuntu-latest`, where `python3` is the name.

  I did not take that on trust. I ran the two checks `faces.mjs` was trying to
  make, with this machine's `python`, and both passed:

  ```
  python jarvis-desktop\scripts\build-faces-spec.py   -> exit 0
      "faces-spec.js: 25 faces, 12 patterns, 8 states"
  python tools\gen_critters.py --check                -> exit 0
  ```

  So the generated files really are up to date on this revision; only the
  interpreter's name stopped the suite from asking.

  `memory.mjs` and `voice-training.mjs` are worse than a failure: they are an
  **uncaught exception**, so each stops at its first Python call and the
  remaining checks in that file never run. `memory.mjs` got through 14 checks
  and `voice-training.mjs` through 33 before dying. Their true state on those
  remaining checks is **unverified** — I am not claiming they pass.

  `brain-producers.mjs` already handles this properly: its `python()` catches
  `ENOENT` and returns null, and the suite prints `SKIP - python3 is not
  installed` three times and exits 0. `lipsync.mjs` tries `python3` then
  `python`. So the repo already knows both idioms; these four files predate or
  missed them. **Not this pass**: none of the four is in
  `01425b52..d404063e`.

## A fifth thing, which is not a failure but is worse than one

`contrast.mjs` **printed nothing at all and exited 0.** It is the WCAG
contrast self-test, and its body is behind

```js
if (import.meta.url === `file://${process.argv[1]}`) {
```

`import.meta.url` is always a URL with forward slashes and a drive letter
(`file:///C:/…`); `process.argv[1]` on Windows keeps its backslashes
(`C:\…`). The two can never be equal, so the whole self-test — the WCAG
arithmetic, the translucent-surface pair, the backdrop control — is bypassed
silently. On Linux the comparison happens to hold, which is why CI has never
noticed.

```
node tests/contrast.mjs                              -> (no output) exit 0
node C:\…\tests\contrast.mjs                         -> (no output) exit 0
```

The fix is one line — compare against `pathToFileURL(process.argv[1]).href` —
and I deliberately did **not** make it. It would be a change to
`jarvis-desktop/tests/`, which holds no product code, on a branch whose
deliverable is a report of what the revision does. It is also pre-existing
(the file is unchanged by this pass, last touched by `465b5d0b`). Flagging it
is the useful act; patching it belongs with whoever owns the suites.

## What this pass changed, and what the suites said about it

For the record, since a failure would have been attributed to one of these.
`01425b52..d404063e` touches `jarvis-desktop/src/` in ten files:

| change | suite that covers it | result |
|---|---|---|
| CSP: `media-src` gains `data:` (`tauri.conf.json`) | `csp-inline.mjs`, `html-sinks.mjs` | pass |
| `settings.css`: `forced-colors` block | `focus-outline.mjs`, `themecheck.mjs`, `themes-all.mjs`, `distinct.mjs` | pass |
| `settings.css`: `46em` measure on notes | `notes.mjs` | pass |
| notification settings push to Rust (`notifications-prefs.js`, `notifications-settings.js`) | `notifications-settings.mjs` | pass |
| widget wrong-card fix (`approval-target.js`, `widget.js`) | `approval-target.mjs`, `blockers.mjs`, `ia.mjs` | pass |
| "Expired" → "Timed out" (`jarvis-link.js`, `jarvis_hud.html`) | `approvals-contract.mjs`, `card-words.mjs` | pass |
| `first_pair_only` device row (`devices.js`, `devices-words.js`) | `devices.mjs` | pass |
| Brain rail button (`brain.js`) | `menu-visibility.mjs` | pass |

The Brain rail and its Tutorials tab are not on this revision, as stated, so
nothing here speaks to them.

Worth knowing for the comparison: **`notifications-settings.mjs` is not a
browser suite.** It has two checks (localStorage round-trip, markup grep) and
finished in 0.1s. The new `pushNotificationPrefs` path — the part of this pass
that decides whether a toast actually honours a switch — is **not** exercised
by any suite on this revision. The widget fix is the same shape:
`approval-target.mjs` asserts the rule and the wiring against `widget.js`'s
source, deliberately without a browser, so no suite on this revision clicks a
real swapped card.

## What I fixed

**Nothing.** Every non-zero exit is a missing Unix tool or a missing
interpreter name, and each is proven so above; the one silent skip is a
pre-existing test-harness bug in a file this pass does not touch.

I had a fix ready for the Python-name and `pathToFileURL` cases and chose not
to apply it, for the reason stated: the deliverable is a measurement of this
revision, and changing the measuring instrument mid-measurement is exactly the
kind of thing that makes the baseline comparison lie. No assertion was
weakened, no check deleted, no comparison loosened — nothing was touched at
all.

## The full table

141 suites, CI's selection (`tests/*.mjs` minus `uikit.mjs` and `shots.mjs`),
each run as CI runs it — `node tests/<name>.mjs` from `jarvis-desktop`, one at
a time, every suite run even after one failed. "checks passed" counts the
suite's own `ok` lines; a suite that dies part-way reports only what it got to.

| suite | verdict | checks passed | failing checks |
|---|---|---|---|
| `a11y.mjs` | pass | 16 | 0 |
| `about.mjs` | pass | 9 | 0 |
| `account-secrets.mjs` | FAIL | 9 | 1 |
| `activity.mjs` | pass | 9 | 0 |
| `animal-behaviours.mjs` | pass | 23 | 0 |
| `animal-lids.mjs` | pass | 37 | 0 |
| `animal-motion.mjs` | pass | 14 | 0 |
| `animal-options.mjs` | pass | 13 | 0 |
| `animal-settings.mjs` | pass | 11 | 0 |
| `approval-target.mjs` | pass | 12 | 0 |
| `approvals-contract.mjs` | pass | 15 | 0 |
| `asks-first.mjs` | pass | 17 | 0 |
| `auto-learn.mjs` | pass | 34 | 0 |
| `autonomy.mjs` | pass | 12 | 0 |
| `backend-supports.mjs` | pass | 5 | 0 |
| `barge-in.mjs` | pass | 9 | 0 |
| `big-model.mjs` | pass | 30 | 0 |
| `blockers.mjs` | pass | 12 | 0 |
| `brain-producers.mjs` | pass | 15 | 0 |
| `briefing.mjs` | pass | 20 | 0 |
| `browser-engine.mjs` | pass | 9 | 0 |
| `card-words.mjs` | pass | 9 | 0 |
| `chat-history.mjs` | pass | 18 | 0 |
| `chat-stream.mjs` | pass | 23 | 0 |
| `chat-thread.mjs` | pass | 14 | 0 |
| `chatbot.mjs` | pass | 32 | 0 |
| `cloud-offer.mjs` | pass | 7 | 0 |
| `coming-up.mjs` | pass | 26 | 0 |
| `composer.mjs` | pass | 11 | 0 |
| `continuity.mjs` | pass | 18 | 0 |
| `contrast.mjs` | pass | 0 | 0 |
| `conversation.mjs` | pass | 9 | 0 |
| `csp-inline.mjs` | pass | 1 | 0 |
| `css-vars.mjs` | pass | 10 | 0 |
| `custom-voices.mjs` | pass | 37 | 0 |
| `decide.mjs` | pass | 9 | 0 |
| `decks.mjs` | pass | 54 | 0 |
| `deep.mjs` | pass | 23 | 0 |
| `devices.mjs` | pass | 21 | 0 |
| `disabled.mjs` | pass | 16 | 0 |
| `distinct.mjs` | pass | 0 | 0 |
| `email-send.mjs` | pass | 10 | 0 |
| `erase.mjs` | pass | 10 | 0 |
| `face-bounds.mjs` | pass | 8 | 0 |
| `face-pace.mjs` | pass | 16 | 0 |
| `face-watchdog.mjs` | pass | 27 | 0 |
| `faces.mjs` | FAIL | 38 | 2 |
| `fact-history.mjs` | pass | 7 | 0 |
| `faq.mjs` | pass | 9 | 0 |
| `flashgov.mjs` | pass | 19 | 0 |
| `focus-outline.mjs` | pass | 1 | 0 |
| `focus.mjs` | pass | 13 | 0 |
| `folders.mjs` | pass | 12 | 0 |
| `forecast.mjs` | pass | 9 | 0 |
| `forget-date.mjs` | pass | 9 | 0 |
| `forget-range.mjs` | pass | 12 | 0 |
| `fork.mjs` | pass | 19 | 0 |
| `form-review.mjs` | pass | 10 | 0 |
| `galaxy-panel.mjs` | pass | 14 | 0 |
| `galaxy.mjs` | pass | 8 | 0 |
| `goal-locks.mjs` | pass | 7 | 0 |
| `goals.mjs` | pass | 35 | 0 |
| `handoff.mjs` | pass | 7 | 0 |
| `hardware.mjs` | pass | 14 | 0 |
| `heavy-approve.mjs` | pass | 11 | 0 |
| `history-import.mjs` | pass | 12 | 0 |
| `history.mjs` | pass | 55 | 0 |
| `hotkeys.mjs` | pass | 22 | 0 |
| `html-sinks.mjs` | pass | 1 | 0 |
| `hud.mjs` | pass | 59 | 0 |
| `ia.mjs` | pass | 21 | 0 |
| `inbox-tidy.mjs` | pass | 17 | 0 |
| `jarvis-live.mjs` | pass | 39 | 0 |
| `learning.mjs` | pass | 9 | 0 |
| `lipsync.mjs` | pass | 27 | 0 |
| `live.mjs` | pass | 4 | 0 |
| `look-rules.mjs` | pass | 21 | 0 |
| `look.mjs` | pass | 15 | 0 |
| `memory-entities.mjs` | pass | 10 | 0 |
| `memory-profile.mjs` | pass | 11 | 0 |
| `memory-used.mjs` | pass | 16 | 0 |
| `memory-words.mjs` | pass | 8 | 0 |
| `memory.mjs` | FAIL | 14 | 1 |
| `menu-visibility.mjs` | pass | 10 | 0 |
| `model-chat.mjs` | pass | 27 | 0 |
| `models-cache.mjs` | pass | 12 | 0 |
| `notes.mjs` | pass | 22 | 0 |
| `notifications-settings.mjs` | pass | 2 | 0 |
| `own-network.mjs` | pass | 11 | 0 |
| `pairing.mjs` | pass | 17 | 0 |
| `pc-help.mjs` | pass | 7 | 0 |
| `photo-reminder.mjs` | pass | 14 | 0 |
| `picture.mjs` | pass | 7 | 0 |
| `plain-errors.mjs` | pass | 18 | 0 |
| `private-speech.mjs` | pass | 28 | 0 |
| `progress.mjs` | pass | 37 | 0 |
| `projects.mjs` | pass | 43 | 0 |
| `provenance.mjs` | pass | 11 | 0 |
| `quickbar-autonomy.mjs` | pass | 17 | 0 |
| `quiz-cloud.mjs` | pass | 7 | 0 |
| `quiz.mjs` | pass | 24 | 0 |
| `reach.mjs` | pass | 7 | 0 |
| `retirement.mjs` | pass | 25 | 0 |
| `sayable.mjs` | pass | 10 | 0 |
| `screen-work.mjs` | pass | 11 | 0 |
| `season.mjs` | pass | 23 | 0 |
| `second-card.mjs` | pass | 43 | 0 |
| `security.mjs` | pass | 28 | 0 |
| `shared.mjs` | pass | 11 | 0 |
| `sheet.mjs` | pass | 0 | 0 |
| `sky.mjs` | pass | 22 | 0 |
| `sources.mjs` | pass | 11 | 0 |
| `speech-pieces.mjs` | pass | 40 | 0 |
| `spending.mjs` | pass | 47 | 0 |
| `support.mjs` | pass | 15 | 0 |
| `tag-suggest.mjs` | pass | 31 | 0 |
| `tags.mjs` | pass | 40 | 0 |
| `tailscale.mjs` | pass | 14 | 0 |
| `task-controls.mjs` | pass | 12 | 0 |
| `themecheck.mjs` | pass | 0 | 0 |
| `themes-all.mjs` | pass | 6 | 0 |
| `thinking.mjs` | pass | 3 | 0 |
| `today.mjs` | pass | 12 | 0 |
| `tokens.mjs` | pass | 6 | 0 |
| `topics.mjs` | pass | 43 | 0 |
| `updater-manifest.mjs` | pass | 3 | 0 |
| `updates.mjs` | pass | 24 | 0 |
| `voice-auto.mjs` | pass | 15 | 0 |
| `voice-capture.mjs` | pass | 8 | 0 |
| `voice-flow.mjs` | pass | 24 | 0 |
| `voice-mouth.mjs` | pass | 12 | 0 |
| `voice-settings.mjs` | pass | 16 | 0 |
| `voice-speech.mjs` | pass | 17 | 0 |
| `voice-speed.mjs` | pass | 4 | 0 |
| `voice-training.mjs` | FAIL | 33 | 1 |
| `voicecheck.mjs` | pass | 21 | 0 |
| `wake-switch.mjs` | pass | 8 | 0 |
| `web-search.mjs` | pass | 11 | 0 |
| `widget-board.mjs` | pass | 17 | 0 |
| `wiki.mjs` | pass | 16 | 0 |
| `youtube.mjs` | pass | 27 | 0 |


## What is still unverified

- The **remaining checks** in memory.mjs (from the Python call at line 275
  onwards) and oice-training.mjs (from line 1061). Neither suite reached
  them on this machine. The baseline run has the same wall and will not reach
  them either, so the comparison will not settle them.
- shader_size.py --check (the Android 100,000-unit shader budget). It is
  gated on glslangValidator, which is not installed here; CI's backend job
  runs it. aces.mjs says so out loud and carries on, which is correct.
- contrast.mjs's WCAG arithmetic. It is in the repository and it exits 0,
  but it did not execute on this machine (see above). Its assertions are
  therefore neither passed nor failed here - they were skipped in silence.
- sheet.mjs and shots.mjs write screenshots rather than assert; sheet.mjs
  ran and rewrote 	ests/shots/sheet-default.png, which was restored. The
  pixel content of that file is not a check either way.
- Whether the same four failures appear on 1425b52. That is the baseline
  agent's half of the comparison. My reading of git diff 01425b52 d404063e
  is that none of the four files changed, so they should fail identically -
  but I have not run the baseline and am not asserting it.

The raw output of every suite is verbatim in un-results/<suite>.log, and
the exit codes in un-results/summary.json.
