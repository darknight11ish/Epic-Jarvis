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
   `scripts/apply-patches.ps1 -SkipTests` is run first in a shell the tool
   **chooses**: PowerShell 7 (`pwsh`) when this PC has it, else Windows
   PowerShell 5.1 (`-NoProfile -ExecutionPolicy Bypass -File`), else a clear
   refusal before anything runs. A 5.1 child gets the WindowsPowerShell module
   directories appended to its own `PSModulePath` (the caller's environment is
   kept, not wiped), because a child launched from a pwsh-hosted process can
   otherwise start unable to find its own cmdlets — the 30-second failure the
   2026-10-18 field test hit. Then the SAME suites
   from `backend/run_suites.py --jobs <workers>`, then the recorded times are
   kept for the next estimate. Before any of that the tool takes the exclusive
   `update-in-progress.lock` (2026-10-18): a second update is refused, a test
   sweep beside it is refused, and the desktop's watchdog does not restart the
   backend until the update finishes - section 8 below. **Nothing about patching
   is reimplemented in Rust or in JavaScript**, so the script's own rehearsal
   rule — a run that would fail changes nothing, because the whole list is
   tried on a copy first — is inherited rather than restated; `-SkipTests` only
   hands the suites to step 3 of the tool, it does not drop them. The three
   paces, the ETAs and the bar are section 8 below.
3. **This app.** Only if step 2 finished: the newest signed release is
   downloaded, checked against the public key compiled into this build, and
   installed. Nothing about that check changed.
4. **Restart.** The new executable is on disk and the old process is still
   running, and Jarvis was stopped for step 2, so the card offers the same
   Restart button the desktop-only install already offered.

**Both or neither (the owner's standing rule, stated 2026-11-20 21:12 PT).**
*"when I update Jarvis the HUD and backend should always update at the same
time."* The in-app action therefore installs nothing when the backend half
cannot run: it says in one plain line which folder or program is missing, and it
never claims Jarvis was updated. The Windows installer path cannot be hooked
(the updater runs it and exits the process), so a desktop-only update can still
happen - and **section 9** is what finishes its backend half automatically on
the next start.

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
4. **It does not act on its own; only a desktop-only update is finished.** No
   timer, no page and no setting can start `update_both`: it is reachable only
   from its own button, behind a question (a test asserts the page invokes it
   exactly once and only after `window.confirm`). The ONE automatic path is the
   owner's own update action continuing: when the Windows installer has already
   moved the desktop alone, the next start finishes the backend half by itself
   (section 9) - once per mismatch, never when the halves are equal or the
   backend is newer. It raises no card and approves nothing.
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
| the tool: the patcher wrapper, the deploy-route choice, the parallel suites, the ETAs, the fallback | `tools/update_backend.py`, `backend/run_suites.py` (`--jobs`) |
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

- **First run at a pace: a RANGE, labelled "not measured for this pace yet".**
  The tool has no times for THAT pace on this PC yet, so it shows
  `etaLowSeconds`–`etaHighSeconds` and says so. It never shows a single invented
  number. Timings are recorded PER PACE in `update-timings.json` (a `safe` run
  at one worker is not evidence for `max_speed` at 22), so a pace the owner has
  not run yet keeps the honest wide range even after another pace has measured.
- **After a run of that pace: measured.** Each suite's own seconds are saved
  under that pace in `<backend>/_jarvis-logs/update-timings.json` and the next
  card says "from this PC's own times". The range narrows with the recorded
  data.
- **While it runs: refined live.** Every finished suite updates the remaining
  estimate; the card shows the new range, still labelled with its source.

One implementation of the maths lives in Python (`estimate`, `live_eta`,
`mode_plan`); Rust only reads the tool's `--modes-json` answer, and the card
draws it. There is no second copy in Rust to drift.

### The exclusive update lock (2026-10-18)

An update patches the backend and then runs several hundred suites against it;
tonight's real run measured 2h8m, and part of that was a second thing happening
beside it. So an update is now exclusive on this PC:

- **The file.** `update-in-progress.lock` in the folder Jarvis keeps its own
  data in (`OPENJARVIS_CONFIG_DIR`, then `JARVIS_CONFIG_DIR`, then
  `~/.openjarvis`), holding `{pid, started_at, updated_at, pace}`. It is taken
  before a file is patched and removed on every way out; a crash leaves it, and
  the rule below makes it stale at once. The take is ATOMIC (an existing file is
  never overwritten and two updates starting at the same instant have exactly one
  winner); the loser is refused in plain words.
- **When it is valid.** The pid must be a running process and the heartbeat
  (`updated_at`) under **30 minutes** old. The heartbeat is refreshed as each
  suite finishes, *and* through the patch phase's own progress lines at most once
  every five minutes - a long patch can no longer make a live update look
  abandoned. The **3-hour** window is a PID-REUSE guard only: a live run renews
  its own `started_at` while it keeps heartbeating, so the measured 2h8m run, and
  a quick pass plus its safe fallback, do not expire themselves. A dead pid is
  stale immediately; non-finite or future timestamps are a clock problem and are
  read as stale (Python and Rust agree).
- **Who obeys it.** `backend/run_suites.py` refuses to start (exit 3) and names
  the lock's pid, pace and start time - and asks again immediately before the
  first suite, so a lock published while it was staging the backend still stops
  it. The update's own suite phase passes `--ignore-update-lock` (or
  `JARVIS_INSIDE_PATCHER=1`), which is the only bypass. The desktop's backend
  watchdog does not auto-restart the backend while a valid lock is held
  (`sidecar.rs`), `update_both` refuses a second press before touching the
  backend, and every backend start path - tray, Settings "Start backend", app
  startup and the watchdog - shares one `ensure_backend` gate that says an update
  is running instead of starting one. **The gap, stated plainly:** a by-hand
  `scripts/apply-patches.ps1` run does not read the lock (that script is the
  owner's own tool and was deliberately not edited), and the desktop stops the
  backend a moment before the tool has written the lock, so a sweep begun in that
  instant can still overlap. The tool's lock is written before it patches; the
  rest of the path is covered.
- **One implementation.** The rules and the reader live in
  `tools/update_backend.py` (Python); `backend_update.rs` mirrors them for the
  desktop. The lock is advisory: an unreadable lock file or a checkout without
  the update tool means nothing is enforced, and nothing claims it was.

### The progress bar

Painted ONLY from the tool's own `JARVIS-EVENT` lines (`update_progress.rs` ->
the `backend-update-progress` event):

- **Fraction = completed work**, not time: items applied in the patch phase,
  then finished suites weighted by their recorded seconds (the same weights the
  ETA uses). Before a pace has timed anything, the weights are the first-run
  placeholders; the label says "not measured for this pace yet", exactly as the
  ETA does.
- **Monotonic within a pass, never over 100%, never 100% before the final
  verdict.** A missing or out-of-order event holds the last real value; the
  page never guesses forward and has no timer that moves the bar.
- **A fallback is the only reset**, and it is labelled in the same words as the
  tool's note: "quick check hit a problem - re-running the safe way, new ETA",
  then "second pass (safe mode)" beside the bar while the safe pass runs.

### The safe fallback

Any failed or ambiguous suite, a worker that crashes, or a live-file
verification mismatch in `max_speed`/`responsive` is not trusted: every file is
put back from the newest `_jarvis-backup-*` (copying, never deleting it; the
**bytes** are what is restored, and a read-only LIVE file is made writable for
the copy so the safe pass can rewrite it - the read-only backup itself is never
altered), then the patcher and ALL the same suites run again with one worker.
**That safe pass is what the update is judged by.** A `safe`-mode failure is
reported and not re-run, because re-running the same checks the same way is not
a second opinion. The final honesty lines are unchanged: `ALL DONE - the
backend is patched and proven`, `DONE - no problems, but NOT fully proven`, or
`DONE WITH
PROBLEMS - do not trust this update yet`, and `updatedBoth` still needs both
halves `ok`.

## 9. One update, both halves - and everything the halves need (2026-11-20/21)

The owner's standing rule, stated 2026-11-20 21:12 PT after two half-updates
left the HUD saying MISMATCH: **"when I update Jarvis the HUD and backend should
always update at the same time."** Three places had to change, and one of them
is not about code at all:

1. **Both or neither, for the in-app action.** The desktop half is not installed
   unless `locate()` says the backend half can run. When it cannot, the press
   says in one plain line which folder or program is missing and installs
   nothing - never "updated". The old desktop-only fallback is gone. The Rust
   `install_update` command refuses the same case before downloading a byte, and
   the tray's blocked press says the same line instead of installing.
2. **A desktop-only update finishes its backend half automatically.** The Windows
   installer path cannot be hooked, so the next start's version handshake does
   it: when the desktop is ahead and the backend is the OLDER one, the app runs
   the SAME backend half an "Update everything" press runs - the same
   `tools/update_backend.py`, patcher and suites, at the `responsive` pace - then
   starts the backend again and reads the two versions back. It says one line
   before and one line after in the HUD's chat (`version` channel), claims
   "both halves now match" only when the read-back really says in-sync, and tries
   ONCE for one `(desktop, backend)` mismatch, never in a loop and never when the
   versions are equal or the backend is newer. A blocked attempt - folders not
   set, a lock held, the tool missing, a program folder that cannot be proved to
   hold this build's commit or later (a stale clone), or a patch/checks failure -
   says exactly why in one line and claims nothing. A stale program folder is
   refused rather than patched: patching from an older folder would make the
   backend older than the desktop, and moving the HUD's marker would hide the
   very difference this rule exists to show.
3. **The release's own identity and files move with the backend half.** "Both
   halves updated" is not code alone; three things were measured broken on the
   live PC the day after the rule was stated:
   - the backend's `VERSION` marker (the number `GET /api/self` reports, which the
     HUD compares character for character) was only ever written by the deploy
     tool, so a successful in-app backend patch still left MISMATCH. After the
     patcher proves itself, and only when `git merge-base` proves the program
     folder holds this build's commit or later, the app writes
     `<backend>/VERSION` with the version it is running - the deploy tool's own
     rule (the installed desktop's version, never this repository's root
     `VERSION`), one file, atomic;
   - **the release's look spec** (`jarvis-desktop/src/jarvis-visual-spec.json`)
     never reached the live backend folder, so every start warned that the
     desktop's bundled spec DISAGREED with the server's copy (measured: the
     release's 73,121-byte copy against the live folder's 61,301-byte one).
     `tools/update_backend.py` now compares the release's copy with the live one
     structurally - the same comparison `spec_drift.rs` makes, so formatting
     alone is not a difference - and writes it atomically with a timestamped
     backup of the old file and a read-back, reported as one `BESIDE:` line.
     **Since 2026-11-21 it is delivered as soon as the FILE half is proved and
     before the proof suites start** (section 9's last subsection): the spec is
     content the release owns, not part of the proof, and a suite phase that
     runs long must not decide whether the owner keeps the old look;
   - **the release's new tool defaults** never reached the owner's own
     `jarvis-framework.toml`: PM2 shipped eight project tools ON in the published
     config, and the live file listed 29 and none of the eight (measured all
     eight `enabled=False offered=False`). After the proof, the tool hands the
     tools this release NEWLY ships ON to `tools/enable_new_tools.py`'s explicit
     additive write (`--add`, `--apply`, backup, read-back), reported verbatim as
     `TOOL DEFAULTS:` lines. "New" is shipped ON now and not shipped ON at the
     desktop build the owner had BEFORE this update (the pending-install record
     for the automatic finish, this binary's own build commit for a press). A tool
     the owner turned off was shipped at that baseline, so it is never named; a
     tool merely absent from the live list is never added on that evidence alone.
     If the baseline commit is not in the clone, either config cannot be read, or
     the release has no `tools/enable_new_tools.py`, the step says exactly which
     and adds nothing. **Honest first-run limit:** the automatic rule only knows
     tools shipped AFTER the previous desktop build; the tools that shipped
     before it (PM2's eight are exactly that) were a one-time explicit `--add`
     migration by hand. Nobody may "fix" the baseline later by re-adding every
     shipped tool that is absent from the live list - that is how an owner's
     deliberate OFF gets flipped back on.

All three report lines (the version marker, `BESIDE:`, `TOOL DEFAULTS:`) are
shown verbatim in the backend half's own sentence on the card, and the automatic
finish puts them on its ending line too. None of them can fail the backend
update: if a step cannot run, its line says so and the proven patch stands.

### The backend half chooses its route with evidence (measured 2026-11-21 00:25-00:28 PT)

The automatic finish ran on the owner's PC after his installer had put 0.2.487 on
the desktop, and the backend half **failed after about three minutes**. Its own
transcript (`…\Desktop program\_jarvis-logs\apply-patches-2026-11-21-002546.txt`)
ended with **"51 patch(es) will not apply to your files as they are"** and
**"None of your backend files were changed by this run."** That install is
**deploy-managed**: its live files come from `tools/reconcile_live_backend.py`
(the published base plus the HUD deltas), not from a full `apply-patches.ps1`
run, so the 160-patch stack cannot apply to them. Run by hand, the deploy tool
finished the same update (VERSION 0.2.487 written from the installed desktop,
0 refusals) and the app then said IN SYNC.

So `tools/update_backend.py` now chooses the backend half's route **with
evidence, never a guess**. `apply-patches.ps1` stays the default for a patched
install. Only when its transcript is that refusal shape - the stack says the
patches will not apply AND that no backend file was changed, and carries no
half-updated warning - does the same run continue with
`tools/reconcile_live_backend.py --apply` on the same backend folder. The deploy
route does the whole job the patch route did: it runs inside the same update
lock, the deploy tool writes the `$SHIPPED` bytes and both release markers
(`VERSION` from the installed desktop, `SOURCE-COMMIT` from the deployed
commit) with its own backups and rehearsal, and the SAME proof suites then run
against the live folder at the chosen pace. Success still needs the same proof:
the live files are this repository's bytes, `VERSION` equals the installed
desktop's FileVersion, and only then are the two halves claimed to match. A
refusal from the deploy tool itself is printed **verbatim** and claims nothing;
a refusal for any other reason (Jarvis still running, a missing file, a
half-applied stack) keeps the old behaviour and never switches route. One
`ROUTE:` line on the card says what happened, in the measured words: "the patch
stack refused 51 hunks on a deployed install; the deploy route carried the
update".

**The automatic finish's failure line, corrected the same night.** When the
desktop half is already installed, a failed backend half must not say the
opposite. The line reads that Jarvis Desktop 0.2.487 **is installed**, names the
backend half as the one that did not finish, says what the two versions RE-READ
after the attempt really say (since 2026-11-21 - see the subsection below; it
never restates the pre-run version as if it were still true), says the one press
that retries it ("Update everything"), and names the run's own log. It never
claims a match. `backend_update::backend_failure_words` owns the backend-only
half of that sentence (the caller owns whether the desktop half was installed),
and both automatic-finish endings are pure functions held by tests.

### The bound measures progress, and every ending re-reads the versions (measured 2026-11-21)

**What was measured, to the minute.** At **11:08:54Z** the automatic finish
started, because Desktop 0.2.488 was ahead of backend 0.2.487. The patcher
refused, and the deploy route carried the backend half - it wrote
**`VERSION 0.2.488`** and **`SOURCE-COMMIT d7003442e`**, so the two halves were
genuinely equal by then. The run then started its proof stage
(`backend/run_suites.py` against the live folder, Balanced / 14 workers), which
on that PC legitimately takes **~57+ minutes**. At **12:08:54Z, exactly 60
minutes after the start**, the app's single one-hour wall clock killed it and
said: *"automatic backend finish: … The patch run did not finish within an hour
… The backend half is the one that did not finish. The backend is still
0.2.487"* - **both claims were false by then**; the backend read 0.2.488. A
restart logged *"Jarvis Desktop 0.2.488 and the backend 0.2.488 – IN SYNC."*
The release's look spec was never delivered either (the delivery step ran only
after the proof, and the bound had already ended the run), so the desktop kept
warning that the spec DISAGREED until it was copied by hand. The same run left
the owner's **everyday model lane** switched, too (lane 11436 held
`jarvis-primary:latest` at 16,384 instead of the preset table's `qwen3.5:9b`
at 196,608, and the field battery's PRESETS row failed afterwards); the owner
warmed it back by hand.

Four rules came out of that, and each is held by tests with injected clocks and
injected output - no real hour is ever waited for:

1. **The bound measures progress, not just the wall clock.** A run that keeps
   producing output is alive, and new output resets the silence clock. The only
   two bounds are a **silence stretch of 15 minutes** with no new output at all,
   and an absolute **hard ceiling of three hours** - well above the measured
   57-minute proof stage and the 2h8m full run of 2026-10-18. Whichever one ends
   the run is named in the words, with how long the run had been going (for
   example "ended by the silence bound after 1h 23m: no new output arrived for
   15m 0s"). The same bound and the same runner are used by an "Update
   everything" press and by the automatic finish, so a click cannot be killed at
   one hour while the run is healthy. For this to work the run's own log must
   really grow line by line, so `tools/update_backend.py` line-buffers its
   stdout and gives a Python child `PYTHONUNBUFFERED=1` - and, because one
   proof suite can print nothing for longer than the silence stretch, the tool
   heartbeats the proof stage itself (rule 6).
2. **On any ending, the two versions are re-read and what is true is reported.**
   `Run::ending` reads `<backend>/VERSION` before and after the attempt and
   compares it with the installed desktop's own version. A run a bound ended
   whose marker read back as the installed desktop's version is reported as
   `partial` and says: **the backend's files and version are updated; the full
   check did not finish within the bound; restart Jarvis and it will read IN
   SYNC.** That "will read IN SYNC" is a promise about the next start, not a
   claim about now - only a restart's own handshake may say IN SYNC, and the
   proven path still reaches `both halves now match` only from that handshake.
   A run that wrote nothing says its marker still reads the old version and the
   halves still differ. "The backend is still 0.2.487" can never be said when
   the marker reads 0.2.488; an unreadable marker is reported as unreadable
   rather than guessed.
3. **The release's look spec goes with the file half, before the proof suites.**
   Once the deploy's own bytes+markers proof (and the live-file verification)
   has passed, `tools/update_backend.py` delivers the spec (step 2b) and only
   then starts the suites. It is content the release owns, not proof, and its
   `BESIDE:` line is part of the run report - read from the WHOLE output, not
   the last 60 lines, so a run a bound ends still says the spec reached the PC.
   The release's new tool defaults still wait for the whole proof, because they
   change the owner's own config; the delivery step can never fail the update.
4. **"Both or neither" is unchanged.** A genuine failure of the deploy (bytes or
   markers not proved) still claims nothing, delivers no spec, and installs no
   desktop half; a bound ending is `partial`/`failed`, never `ok`, so a
   half-finished check cannot paint an update green. No card or approval path
   changed.
5. **The owner's everyday model lane is put back.** Measured the same day,
   after the same auto-finish: the proof suites run against the live backend
   folder and at least one of them loads a different model on the **everyday
   lane** without putting the owner's back. Lane 11436 - whose preset table row
   is `qwen3.5:9b` at 196,608 tokens - was left resident on
   `jarvis-primary:latest` at 16,384, and the field battery's PRESETS row then
   failed (*"the everyday lane is on a model its own preset table declares for
   it"* / *"on its one-card model at 196,608"*). So the suites are bracketed:
   before they start, `tools/update_backend.py` reads the lane's resident
   model+context from `GET /api/ps` on `OLLAMA_URL` (loopback only - it never
   reaches another machine) and writes that record into the backend's own
   `_jarvis-logs` folder; after them it warms the recorded model at the
   recorded context when the suites left a different one. Warming always names
   the context the lane itself reported - a preload without one would reload
   the model at Ollama's own small default (the measured 2026-10-10 2,048-token
   bug). One `LANE:` line in the run report says which happened (restored / left
   alone) or that the lane could not be read, in which case **nothing is
   restored and no model is invented**. The record is what makes the timeout
   ending safe: the desktop owns the run's bound and can kill the tool
   mid-suite, so after **any** ending the app runs the tool's own
   `--restore-lane` mode from that record (the tool's normal endings remove the
   record once the lane is back; a failed restore leaves it for that one
   retry, and the app always removes it afterwards so a stale record can never
   override a model the owner picks later).
6. **The proof stage says it is alive, so only true silence is a stall.**
   Measured on the same PC the same day, an hour after the run above: the
   automatic finish for desktop **0.2.491** started at **07:07 PT**. The deploy
   route carried the file half (`VERSION 0.2.491` at 07:11), delivered the look
   spec, recorded the everyday lane's model, and then the proof suites ran. At
   **07:55:57Z = 07:55 PT - 48m 10s in - the silence bound ended that healthy
   run**: *"The patch run was ended by the silence bound after 48m 10s (no new
   output arrived for 15m) ... The full check did not finish within the bound ...
   Restart Jarvis and it will read IN SYNC."* The backend half had genuinely
   succeeded (the restart logged *"Jarvis Desktop 0.2.491 and the backend
   0.2.491 - IN SYNC"*), and the lane restore line worked (`LANE: ... warmed
   the recorded qwen3.5:9b at 196608`). The only fault was that **one proof
   suite can print nothing for more than fifteen minutes between suite
   boundaries** (`test_live_settings_parity.py` was one; the previous full run
   took ~48-57 minutes), so "no output" was read as a stall. The ruling: **the
   heartbeat is the fix, not a weaker bound.** While the suites child is quiet,
   `tools/update_backend.py` prints its own line at least every five minutes -
   *"PROOF: still running - 24m 05s elapsed, checking the backend against the
   live folder"* - and every real child line still flows through unchanged and
   restarts that clock. The 15-minute silence bound and the 3-hour ceiling are
   unchanged; the silence stretch now means the **heartbeat AND the child's
   output** both stopped, which is a real hang, so a healthy proof stage can
   never be pre-empted by it. The heartbeat interval is pinned against the
   Rust silence bound by tests on both sides (the tool tests drive the injected
   clock and scripted child output; a Rust test reads the tool's own
   `PROOF_HEARTBEAT_SECONDS` and checks it is at least three times inside the
   bound). The honest ending is unchanged: marker == installed desktop -> files
   and version are updated, restart will read IN SYNC; unchanged or unreadable
   -> exactly what the marker says. No card or gate changed, and "both or
   neither" is untouched.

**What this deliberately does not do:** it raises no card, approves nothing,
changes no other setting, touches no network beyond the one local `/api/self`
read, and never fetches anything from GitHub. It is the owner's own update
action continuing, not a new one.

### The card says which half is missing, and the HUD's warning clears in place (2026-11-21)

Four owner reports the same morning, ~10:12 PT, while a real update was running.
They are one rule each, and all of them are words and lifetimes - no new update
path, no card, no gate:

1. **The card's state is the release check AND the two halves, never either
   alone.** *"when i go to updates in settings it says none available when i
   click check for updates"* is true about a NEWER release and was misleading
   mid-update, when the backend was still behind and the card implied there was
   nothing to do. `settings.js` now composes the card's one state line from
   both answers it reads (`updateStateWords`):

   - the two halves equal and a finished check that found nothing newer ->
     **"Up to date."** followed by the check's own line ("Version X — the newest
     published. Last checked …"), so the Check button still has its answer on
     screen;
   - the backend older (the measured case: Desktop 0.2.492 installed, backend
     0.2.491) -> **"Jarvis Desktop 0.2.492 is installed; the backend is 0.2.491
     - press Update everything to finish the backend half."** The check's own
     line is APPENDED, never substituted, so a no-newer-release answer can never
     hide a half that still needs finishing;
   - a backend half running right now -> **"Finishing the backend half now.
     Jarvis Desktop 0.2.492 is installed; the backend is 0.2.491 - the card
     updates when it ends."** The "running" fact is the shell's, not the page's
     guess: `update.rs` marks a live backend half (the press and the automatic
     finish both take the mark), and `backend_self.rs` carries it out as
     `VersionSync.running`. Equal halves are never made to say "finishing", and
     a NEWER backend is not something this app is writing.
   - "Up to date." is reachable only with a finished check behind it: an equal
     pair with no check yet still says "Not checked yet".

2. **The HUD's version line is ONE line, rewritten in place.** *"MISMATCH: the
   backend 0.2.491, but this HUD expects 0.2.492 ... this usually clears on its
   own" stayed visible after the backend half had finished* - `VERSION` already
   read 0.2.492 while the banner still said 0.2.491. The handshake line used to
   be a chat message APPENDED once and only for state `older`, so the run's own
   later states landed nowhere. `hud_bootstrap.js`'s `handleVersion` now owns one
   note and:
   - a mismatch, a run starting, and every ending REWRITE its words - the
     automatic finish's opening line says **"Finishing the backend half now"**
     (`auto_finish_opening`), and every ending carries the two versions RE-READ
     after the attempt, so a bound's honest partial ending replaces the stale
     0.2.491 rather than living beside it;
   - an `ok`/`in-sync` read-back REMOVES the note. A warning about a mismatch is
     not left standing after the mismatch is gone, and no manual restart is
     needed for that - nor is a second line appended to retell the same story.

Both rules are held by tests: the card's three states are browser checks in
`jarvis-desktop/tests/updates.mjs` (with the release check and handshake fixtures
driving the real page), the "a no-newer check does not hide a behind backend"
case among them; the HUD line's rewrite-then-clear is a check in
`tests/hud-window.mjs` that feeds the REAL injected bootstrap through its own
`version` channel; and the Rust words (`backend_self::finishing_words` /
`words_for`, `update::auto_finish_opening`) plus the running flag are unit tests.
"Both or neither" is untouched: nothing here installs, approves or starts
anything.
