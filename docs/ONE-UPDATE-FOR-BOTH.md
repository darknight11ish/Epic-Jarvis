# One Update control for both halves (2026-10-13)

The owner asked for this directly, on 2026-10-13: **one Update control that
updates BOTH the desktop program and the Python backend.**

Before this, only one half could be updated from inside the app. Jarvis Desktop
had checked a signed release and installed it on a press since the signing key
landed (`jarvis-desktop/src-tauri/src/update.rs`). The Python backend had never
been touched by the app at all: it moved only when somebody ran
`scripts/apply-patches.ps1` by hand, in a PowerShell window, from the
repository. Everything the owner saw when the two drifted apart was a sentence
telling him to go and do that — "run apply-patches.ps1 on the PC" — in about
eighty places across both apps.

---

## 1. What the button does, in order

The sequence lives in **one Rust command**, `update_both`
(`jarvis-desktop/src-tauri/src/update.rs`), and not in the page. A page that
called three commands could get the order wrong in a later edit; a page that
calls one cannot.

1. **It asks first.** One press opens a question that names the backend folder
   by path, says that the backend step writes into the folder Jarvis runs from
   and copies every file it touches into a `_jarvis-backup-<date>` folder
   first, says that Jarvis is stopped while it works, says which half goes
   first, and says what happens if the first half fails. Cancel changes
   nothing.
2. **The backend.** Since 2026-10-17 a press also chooses a PACE, and the
   backend half runs through `tools/update_backend.py --mode <pace>`:
   `scripts/apply-patches.ps1 -SkipTests` is run first (with
   `powershell -NoProfile -ExecutionPolicy Bypass -File`), then the SAME suites
   from `backend/run_suites.py --jobs <workers>`, then the recorded times are
   kept for the next estimate. **Nothing about patching is reimplemented in Rust
   or in JavaScript**, so the script's own rehearsal rule — a run that would
   fail changes nothing, because the whole list is tried on a copy first — is
   inherited rather than restated; `-SkipTests` only hands the suites to step 3
   of the tool, it does not drop them. The three paces, the ETAs and the bar are
   section 8 below.
3. **This app.** Only if step 2 finished: the newest signed release is
   downloaded, checked against the public key compiled into this build, and
   installed. Nothing about that check changed.
4. **Restart.** The new executable is on disk and the old process is still
   running, and Jarvis was stopped for step 2, so the card offers the same
   Restart button the desktop-only install already offered.

### Why that order, and not the other one

- **The backend half needs a process stopped, and this half is the one that can
  stop it.** `apply-patches.ps1` refuses to touch a backend whose own
  `jarvis_hud.py` is still running, and it is right to: a running Python has
  already imported the modules being rewritten. This app is what started that
  process, so the stop belongs here — and it has to happen before the patches,
  not after.
- **A failure after the first half lands in the state the project already lives
  in.** New backend plus old desktop is what this repository is in most of the
  time: the app is released far more often than the patcher is run, and every
  screen already renders it honestly (a route the older app does not know is
  simply not called). So the failure direction degrades into the ordinary.
- **The step that can leave a machine half-changed goes first.** The script says
  so itself, in its own words, when it has already started writing ("Some of
  your backend files WERE changed before this went wrong, and the patched files
  may be HALF updated"). Putting the backend first means the run that reports
  "not updated" is the run that has *not* already replaced the executable.
- **The executable goes last because it is the half that can leave the app
  unable to start**, and by then it is the only step left — the smaller, signed,
  signature-checked one.

### What a failure looks like

The second step is **not attempted** when the first did not finish. It is
reported as `skipped`, present in the list with the reason, never left out — so
the card cannot show one row where two things were promised. And
`update_both` returns one boolean, `updatedBoth`, which is **true only when
every step is `ok`** (`update::both_updated`, held by a unit test). The page
paints its green line from that boolean and from nothing else.

Three endings, and only the first is a pass:

| state | what it means |
|---|---|
| `ok` | the half finished. The backend half only says `ok` when the script printed "ALL DONE - the backend is patched and proven". |
| `partial` | the backend IS patched, and the script could not prove every check (it says which were skipped). This project's rule is that a check which could not run is never a pass, so this is not `ok` and `updatedBoth` is false. |
| `failed` / `skipped` | nothing was put on top of it. |

If the backend half reports that files WERE changed before it went wrong, the
card says so in those words, names the log folder, and does not offer anything
as updated.

## 2. How the app finds the repo and the backend folder

**It never guesses.** There is no search of the disk, no walk up from the
working directory, no "it is probably under Documents". A feature that guessed
at a security-relevant path and got it wrong would run the patcher against
somebody else's folder, so both paths are read only from somewhere the owner
already put them, and a missing one is a refusal rather than an attempt.

The **backend folder** (the one holding `jarvis_hud.py`), in this order:

1. the box on the card — `updates.backend_folder` in the app's own settings
   store;
2. the folder this app already starts Jarvis from — the `jarvis_hud.py` argument
   in Settings → More options → "Starting Jarvis for you", which is the owner's
   own typing;
3. that setting's working folder, if it names one;
4. `JARVIS_BACKEND` — the environment variable
   `scripts/install-backend.ps1` exists to set, and the same one
   `backend/_where.py` reads for the test suites.

The card **says which of those it used**, rather than implying it.

The **repository** (the folder holding `scripts\apply-patches.ps1`) is only ever
the box on the card — `updates.repo_folder`. It is **empty until the owner fills
it in once**, because nothing in the app knows where a git clone lives and
nothing should pretend to. `docs/INSTALL.md` step 1.2 puts it at
`C:\Users\<you>\Epic-Jarvis`.

Both paths are checked before anything runs: the repository must actually
contain `scripts\apply-patches.ps1`, and the backend folder must actually
contain `jarvis_hud.py`. A path that fails either check is refused with the
sentence that says what to do, the same shape `scripts/install-backend.ps1`
already uses. `backend_update::refuse` is a pure function of its five inputs, so
the rule is a test rather than a comment.

## 3. What the owner must configure once

One thing: **the Jarvis program folder**, in Settings → Updates → "Update both
halves" → "The Jarvis program folder on this PC", then "Save these two
folders". The backend folder box can be left blank — it then resolves to the
folder this app already starts Jarvis from.

## 4. The five rules, checked

1. **Nothing about this leaves the PC.** The only network request in the whole
   feature is the same signed-release check the app already made. No telemetry,
   no new endpoint, and no route was added to the backend at all — held by a
   test that reads `backend_update.rs` for an `"/api/"` string.
2. **No tunnel.** Nothing here opens one.
3. **No key is involved.** The paths are not secrets, and no token is read,
   logged or written by this feature.
4. **Never automatic.** No timer, no startup path and no setting can start it:
   `update_both` is reachable only from its own button, behind a question. A
   test asserts the page invokes it exactly once and only after
   `window.confirm`.
5. **Non-commercial.** Untouched.

## 5. Why the phone has nothing

A phone cannot patch a PC's backend. The patch program, the repository it lives
in and the Python folder it writes into are all on the PC, and the work is
`git apply`, then `pip`, then the test suites. There is deliberately **no
route**, so the phone is not offered a control that cannot work, and
`tools/check_parity.py` has nothing to classify because nothing was added to the
API. The reason is written down in `docs/ARCHITECTURE.md` §8 ("One-sided on
purpose"), where the audit requires it, and a desktop test reads that section so
the promise cannot be dropped quietly.

## 6. What is still the owner's call

Written here as well as in the pull request, because these are decisions this
work deliberately did not take:

1. **The program folder is typed in by hand.** It is a text box, and typing a
   path is exactly the kind of thing this project tries to avoid asking for.
   The alternative is a Windows folder picker, the same one Backups and
   "Folders Jarvis may look in" use — it would need a new Rust command, since
   the existing pickers add the folder to Jarvis's own read list, which is not
   what this is.
2. **Whether the app may write into the backend folder at all.** This control
   does what `scripts/apply-patches.ps1` does — backups first, and the patcher's
   own refusals — but it does it from a window rather than from a terminal the
   owner typed in. If that is not wanted, the button can be made to print the
   one PowerShell line instead of running it, and nothing else here changes.
3. **Whether the tests should run as part of the button's run.** Settled
   2026-10-17: they always run, and the owner chooses only how many run at
   once. `apply-patches.ps1` is passed `-SkipTests` so the suites are not run
   twice, and `tools/update_backend.py` runs the same suite list itself, at the
   chosen pace, with the safe fallback. "Patched" can never mean less than it
   did before: the suites are still the proof, and a run that could not prove
   them is still not a pass.

## 7. Where the code is

| piece | file |
|---|---|
| the backend half: both folders, the refusals, running the tool, reading its verdict | `jarvis-desktop/src-tauri/src/backend_update.rs` |
| the sequence, the pace and the step report (`updatedBoth`) | `jarvis-desktop/src-tauri/src/update.rs` |
| the tool: the patcher wrapper, the parallel suites, the ETAs, the fallback | `tools/update_backend.py`, `backend/run_suites.py` (`--jobs`) |
| the card, the pace choice, the question, the bar and the three endings | `jarvis-desktop/src/settings.html`, `jarvis-desktop/src/settings.js`, `jarvis-desktop/src/settings.css` |
| the tool's own suite | `backend/test_update_backend.py` |
| the card's suites | `jarvis-desktop/tests/update-both.mjs` (page + Rust source), and the unit tests in all three Rust modules |
| the stub bridge the suites drive | `jarvis-desktop/tests/uikit.mjs` (`UPDATE_BOTH`) |

## 8. Three paces, honest ETAs, and a bar that is not decoration (2026-10-17)

The owner asked for the update to be quicker without giving up the checks, and
for a progress bar that corresponds to what is really happening. Both are one
change, because the number the bar shows and the number the ETA shows come
from the same completed work.

### The three paces

Chosen when "Update everything" is pressed, before anything runs:

| pace | suites at once (24 threads) | what it means |
|---|---|---|
| `max_speed` | 22 (clamped 20–22) | nearly the whole PC while it checks: fastest |
| `responsive` | 14 (clamped 12–16) | **the default and the recommended one**: about half the PC |
| `safe` | 1 (always) | one check at a time: slowest, safest on a busy PC |

**All three run the same suites.** `tools/update_backend.py` calls the patcher
with `-SkipTests`, then runs `backend/run_suites.py --jobs N`; N is the only
difference, and `run_suites.py`'s default is still 1, so CI is untouched. An
unknown pace is refused before a process starts, in the Python tool AND in Rust
(`update_both`), naming the three that exist; a program folder too old to have
the tool may still update at `responsive` only (the older one-at-a-time path).

### The ETAs

- **First run: a RANGE, labelled "first run - not measured yet".** The tool has
  no times for this PC yet, so it shows `etaLowSeconds`–`etaHighSeconds` and
  says so. It never shows a single invented number.
- **After a run: measured.** Each suite's own seconds are saved in
  `<backend>/_jarvis-logs/update-timings.json` and the next card says "from
  this PC's own times". The range narrows with the recorded data.
- **While it runs: refined live.** Every finished suite updates the remaining
  estimate; the card shows the new range, still labelled with its source.

One implementation of the maths lives in Python (`estimate`, `live_eta`,
`mode_plan`); Rust only reads the tool's `--modes-json` answer, and the card
draws it. There is no second copy in Rust to drift.

### The progress bar

Painted ONLY from the tool's own `JARVIS-EVENT` lines (`update_progress.rs` ->
the `backend-update-progress` event):

- **Fraction = completed work**, not time: items applied in the patch phase,
  then finished suites weighted by their recorded seconds (the same weights the
  ETA uses). Before any timing exists, the weights are the first-run
  placeholders; the label says "not measured yet", exactly as the ETA does.
- **Monotonic within a pass, never over 100%, never 100% before the final
  verdict.** A missing or out-of-order event holds the last real value; the
  page never guesses forward and has no timer that moves the bar.
- **A fallback is the only reset**, and it is labelled in the same words as the
  tool's note: "quick check hit a problem - re-running the safe way, new ETA",
  then "second pass (safe mode)" beside the bar while the safe pass runs.

### The safe fallback

Any failed or ambiguous suite, a worker that crashes, or a live-file
verification mismatch in `max_speed`/`responsive` is not trusted: every file is
put back from the newest `_jarvis-backup-*` (copying, never deleting it), then
the patcher and ALL the same suites run again with one worker. **That safe pass
is what the update is judged by.** A `safe`-mode failure is reported and not
re-run, because re-running the same checks the same way is not a second
opinion. The final honesty lines are unchanged: `ALL DONE - the backend is
patched and proven`, `DONE - no problems, but NOT fully proven`, or `DONE WITH
PROBLEMS - do not trust this update yet`, and `updatedBoth` still needs both
halves `ok`.
