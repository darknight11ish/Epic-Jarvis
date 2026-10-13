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
2. **The backend.** `scripts/apply-patches.ps1 -BackendPath <the backend
   folder>` is run, with `powershell -NoProfile -ExecutionPolicy Bypass -File`.
   This reuses the patcher; **nothing about patching is reimplemented in Rust
   or in JavaScript**, so the script's own rehearsal rule — a run that would
   fail changes nothing, because the whole list is tried on a copy first — is
   inherited rather than restated.
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
3. **Whether the tests should run as part of the button's run.** They are how
   the patcher proves itself, and they are the slow part (minutes). Passing
   `-SkipTests` would make the button much faster and would make "patched" mean
   less, which is why it is not passed today.

## 7. Where the code is

| piece | file |
|---|---|
| the backend half: both folders, the refusals, running the script, reading its verdict | `jarvis-desktop/src-tauri/src/backend_update.rs` |
| the sequence, the step report and `updatedBoth` | `jarvis-desktop/src-tauri/src/update.rs` |
| the card, the question, and the three endings | `jarvis-desktop/src/settings.html`, `jarvis-desktop/src/settings.js` |
| the suites | `jarvis-desktop/tests/update-both.mjs` (page + Rust source), and the unit tests in both Rust modules |
| the stub bridge the suites drive | `jarvis-desktop/tests/uikit.mjs` (`UPDATE_BOTH`) |
