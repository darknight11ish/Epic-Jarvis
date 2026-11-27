# One install runbook - from nothing installed to driving the merged work

**The short answer, for this PC: the desktop installer first, then the backend deploy, then the gate
replacement.** Check the PC and the repository -> back up the backend folder and its data -> tell
Windows where the backend folder is (copying the published one only on a new PC) -> install the
desktop app built from the merged tree -> put the backend down with its **deploy** tool (this PC is
deploy-managed, so the patch stack is not its route) -> replace the one drifted approval gate from
the repository's published base -> install the phone APK that CI built -> check the whole chain by
driving it. Every step ends with the one line that undoes it. **A fresh PC, or a patcher install,
swaps the middle for the patch stack** - and then the gate replacement comes **before** it. The
section after this one gives both orders, and step 5 says how to tell which PC you are on.

**This page has been rehearsed on a copy; nothing has been installed.** It was written on 2026-11-26
by reading the files named beside each claim. On the same day the two backend steps - the deploy and
the gate replacement - were run end to end on a **byte-identical copy** of this PC's backend folder.
**The install itself has not run:** the live gate is still `c2a31981…` (236,453 bytes); the live
folder was read, never written. Three labels are used throughout:

- **VERIFIED** - the command or claim was read out of the named file in this repository on
  2026-11-26. It does **not** mean the command has been tried.
- **REHEARSED** - the command was run end to end on a byte-identical copy of this PC's backend
  folder on 2026-11-26, and this is what it printed. It was **not** run against the live folder.
- **UNVERIFIED** - it was neither read out of the repository nor run. The text says exactly what is
  missing.

Treat the first run as a test of this page, and send back the output if a line does not behave as
described here. Do not "fix" a refusal by editing a guard; the guards are the point.

**Written against** merged `main` at `4136d2d7f` (2026-11-26, the merge of PR #1521) **plus PR
#1524** (`fix/gate-base-carries-expiry`, tip `43bb5ed57`), which this page depends on and which is
merged before it: step 4 and 8.2 describe the published base **after** that change. Run `git pull`
first; if `main` has moved since, the files named here may have moved with it, so check the file
before trusting a line.

**What "driving the merged work" means here.** The backend you end up with is the repository's
published copy of the approval gate, on top of the backend files your route put down - the deploy's
files on a deploy-managed PC, the patch stack's on a fresh or patcher one; the desktop app is built
from this checkout; the phone app is the APK CI built from this project. You have driven it when you
have typed a question in the desktop app, approved a card with Windows Hello, opened the phone app,
and (only if your PC is set to it - see 8.8) said the wake phrase. Anything you could not reach is
written down as BLOCKED, PARTIAL or NOT-TESTABLE. **A screen you could not read is not a pass**, and
a feature that could not be reached is never a pass
(`docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md`, `docs/FIELD-TEST-MATRIX-2026-10-11.md`).

---

## The order, and the two backend routes

**This PC's install runs in this order: the desktop installer, then the backend deploy, then the
gate replacement.** Every part of that order is measured, not a preference.

**The desktop first, because a deploy writes `VERSION` from the desktop that is installed.** The
deploy tool plans the release marker from the installed desktop: `plan_release_files` in
`tools/reconcile_live_backend.py` says *"The VERSION value comes ONLY from the installed desktop's
FileVersion"*, and `tools/update_backend.py` will not call the update finished unless the live
`VERSION` equals that same number (`:2190-2193`, *"the two halves are not proved to match"*).
Install the desktop *after* the backend and the marker is the old desktop's number: the next launch
reads "MISMATCH" and Atlas spends a whole second backend run finishing itself. That was measured on
this PC on 2026-11-25 and is DEF-100: the log reads `installing Jarvis Desktop 0.2.502 over
0.2.495`, then `version handshake: MISMATCH: the backend 0.2.495, but this HUD expects 0.2.502`,
then a backend run from 02:29:37 to 02:33:14 for an update whose files had already carried.
**Desktop installer first, and the marker and the HUD agree.**

**Then the backend half, by the route this PC is on.** There are two routes, and they are not
interchangeable:

- **A deploy-managed PC runs the deploy tool** - `tools/reconcile_live_backend.py --apply`. **This
  PC is one.** `DEPLOY-MANIFEST` sits beside `VERSION` in
  `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program` (measured 2026-11-26), and
  that manifest is the deploy tool's own content-hash record of the release it wrote. On evidence
  like that `tools/update_backend.py` chooses the deploy route **up front and skips the patch stack
  entirely** - its own docstring: *"if the live folder is deploy-managed, run
  `tools/reconcile_live_backend.py --apply` DIRECTLY as the primary route and skip the guaranteed
  refusal"* - because a deploy-managed install has live files the patch stack rejects by
  construction. Step 5 is where you run it.
- **A fresh PC, or a patcher install, runs the patch stack** - `scripts/apply-patches.ps1`. It has
  no `DEPLOY-MANIFEST` or `SOURCE-COMMIT` beside `VERSION`, so nothing has been deployed and the
  patch stack is the install. Step 5 keeps that route, whole.

**The gate replacement is last on this PC, and it is separate from both routes.** A deploy **never
copies `jarvis_gate.py`** (the deploy tool's own words: *"the published base, which the deploy NEVER
copies"*), and on a byte-identical copy of this PC's folder the deploy left the gate byte-identical
before and after (**REHEARSED**, 2026-11-26). So the replacement can run safely after the deploy,
which is the order here. It must still run **before any patch stack**, if your PC takes one: it
refuses unless the live `jarvis_gate.py` is byte-for-byte
`c2a31981d7863c1a08e2200cc208c8f0950bead1503d40614cbcaa0ce06a2f95` (236,453 bytes), and a patch that
touched that file first would change the hash and the tool would refuse. **Nothing may touch the
live gate before the replacement.**

**What the replacement does and does not do.** It puts the repository's published base down in
place of a lineage no other tool recognises, once, keeping the old file beside it. **That base now
carries the approval model this PC has been running** - the 2026-10-28 request-bounding machinery
and the 2026-10-30 card timer included, measured in step 4. It does **not** apply patches, and the
patch stack is not a way to add to the base: the replacement tool's own docstring, measured
2026-11-26 over the 59 `jarvis_gate.py` patches left in the stack, says 58 of them do not apply to
the published base. New gate rows go into `jarvis-backend/jarvis_gate.py` and reach a live file
through `tools/repair_live_backend_gaps.py` (step 4).

---

## Two folders, and the one you must never overwrite

- **The repository** - the code from GitHub, including the scripts, the patches and the published
  backend. In this runbook it is `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main`;
  change the path if your clone is elsewhere.
- **The backend folder** - the Python program that **is** Atlas (`jarvis_hud.py` and the files
  beside it), plus `jarvis-framework.toml` (the settings file). On this PC it is
  `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`
  (`docs/ARCHITECTURE.md` section 9 says why it is not in the repository).

**Never copy `jarvis-backend\` over this PC's existing backend folder.** The published copy is a
snapshot for a *new* PC; your folder holds the data, the tokens and the history, and the patches are
written against it. Step 3 copies only on a new PC.

**This is a document, and the live folder is read-only to it.** Nothing on this page has been
executed against the live backend folder: its gate, `VERSION` and `DEPLOY-MANIFEST` were read (the
last two to tell this PC's route), and nothing in it was written. The two backend steps were run on
a byte-identical **copy** - see the labels at the top.

---

## Step 1 - Preconditions and pre-checks

What is being checked: that the PC has the programs and the model Atlas needs, that the repository
is the merged one, that there is room for the build, and that Atlas is not running while its files
are about to be edited. Nothing in this step changes anything.

**VERIFIED** for the commands' source: `docs/INSTALL.md` sections 1.1, 1.8 and 2.1 for the
programs and the models; `scripts/apply-patches.ps1`'s own help for the rule that nothing may be
running while it patches.

1. Get the merged repository and see which commit you are on. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; git pull --ff-only; git log -1 --oneline`

   Good: a commit line at or after `f9ed4cc36`. If `git pull` refuses, stop - you have local
   changes, and this runbook is not the place to merge them.

2. Check the three programs. One line:

   `git --version; py -3 --version; ollama --version`

   Good: three version numbers. If one is missing, install all three (one line), then **close
   PowerShell and open a new one** so the new programs are found:

   `winget install --id Git.Git -e; winget install --id Python.Python.3.12 -e; winget install --id Ollama.Ollama -e`

   **Do not use the word `python` on its own** - on a fresh Windows 11 that is a Microsoft Store
   shortcut, not Python. Every command on this page uses `py -3`.

3. Check the models are already downloaded. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; ollama list`

   Good: `qwen3.5:9b` (the everyday model) and `jarvis-primary` (the older fallback that typed chat
   still names by default). If they are missing, these two lines download about 11 GB; then quit
   Ollama from its tray icon and start it again:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; ollama pull qwen3.5:9b`

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; ollama pull qwen3:8b; ollama create jarvis-primary -f backend\jarvis-primary.Modelfile`

4. Check disk space, because the desktop build is the big one and the shared build cache lives on
   `D:`. One line:

   `"{0:N1} GB free on C:" -f ((Get-PSDrive C).Free/1GB); Test-Path "D:\"`

   Good: at least 15 GB free on `C:`, and `True` for `D:`. If `D:` does not exist, use
   `$env:USERPROFILE\.jarvis-cargo-target` in place of `D:\jarvis-cache\cargo-target` in step 6.

5. **Close Atlas.** If you started the backend in a PowerShell window, press **Ctrl+C** in it; if
   the desktop app started it, tray icon -> **Quit Atlas**. The patch stack refuses to run while the
   backend's own `jarvis_hud.py` is running, and for either route a running Atlas keeps the code it
   started with until it is restarted - so close it, and restart it at step 8.1. There is no command
   for this - use the window and the tray.

6. Check the backend folder is where this page says. One line:

   `Test-Path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis_hud.py"`

   Good: `True`. If `False`, that is not the backend folder; find the folder that holds
   `jarvis_hud.py` and use its path everywhere this page shows the one above.

**To undo this step:** nothing was changed. Closing Atlas is undone by starting it again (step 8).

---

## Step 2 - Back up first

What this is: a **zip file** is one file holding a copy of a folder. Two zips go on your Desktop -
the backend folder (the program and its files), and `%USERPROFILE%\.openjarvis` (the settings, the
memory database, the approval queue and the logs). Together they are the "before" picture this
whole runbook can be undone to.

**UNVERIFIED.** Both lines are ordinary PowerShell, but this exact backup was not run while writing
this page. If a zip fails, a file is open - close Atlas and try again. Do not go on with a backup
you do not have.

1. Back up the backend folder. One line (the file lands on your Desktop and ends in today's date):

   `Compress-Archive -Path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\*" -DestinationPath "$env:USERPROFILE\Desktop\jarvis-backend-before-runbook-$(Get-Date -f yyyy-MM-dd).zip" -Force`

2. Back up Atlas's own data and settings. One line:

   `Compress-Archive -Path "$env:USERPROFILE\.openjarvis\*" -DestinationPath "$env:USERPROFILE\Desktop\jarvis-openjarvis-before-runbook-$(Get-Date -f yyyy-MM-dd).zip" -Force`

   Good: two `.zip` files on the Desktop. Look at their sizes: the backend folder is roughly 10 MB;
   `.openjarvis` can be much larger. A few kilobytes means the folder was empty or the wrong one.

**To undo this step:** delete the two zips. Nothing else changed. To use them, see step 9.

---

## Step 3 - The backend install

What this is: the **backend** is the Python program that actually is Atlas - `jarvis_hud.py` and
the files beside it. On a new PC there is no such folder, so it is copied from the repository's
published copy (`jarvis-backend\`). On this PC the folder already exists and is the real one;
this step only tells Windows where it is and checks it.

**VERIFIED** from `docs/INSTALL.md` sections 1.3, 1.4 and 1.5 and from the two scripts' own help:
`scripts/install-backend.ps1` refuses a folder without `jarvis_hud.py` *before* changing anything.

1. **New PC only** - copy the published backend to a folder of your own. One line:

   `Copy-Item -Recurse -Force "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\jarvis-backend" "$env:USERPROFILE\Documents\jarvis-backend"`

   On this PC, skip this line; your folder is
   `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`.

2. Tell Windows where the backend folder is. This writes one setting for your Windows account
   (`JARVIS_BACKEND`), so the live check and the test suites find the folder by themselves. It
   opens no file in the folder and changes nothing inside it. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; powershell -ExecutionPolicy Bypass -File .\scripts\install-backend.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

   Good: it prints the one change, the way to undo it, and the next command. **Open a new
   PowerShell window afterwards**, so the new setting is picked up.

3. Check the folder is complete. This only reads. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

   Good: no `MISSING` lines. `not yet` means "this repository ships it and step 5 copies it in" -
   that is expected before step 5, whichever route your PC is on.

**If it refuses:** a folder without `jarvis_hud.py` is refused before the setting is written, so a
wrong path cannot be half-installed. Nothing changes; run it again with the right folder.

**To undo this step:** remove the setting (one line), and, if you made the copy in line 1, delete
only that copy (second line). Never run the delete against your only backend folder.

`[Environment]::SetEnvironmentVariable('JARVIS_BACKEND', $null, 'User')`

`Remove-Item -Recurse -Force "$env:USERPROFILE\Documents\jarvis-backend"`

---

## Step 4 - The gate replacement

**When: on this PC, after step 5's deploy; on a patcher PC, before step 5's patch stack; on a new
PC, never** (the copy already is the base, see below). The section at the top has the reason.

What this is: `jarvis_gate.py` is the **approval gate** - the one file that decides what needs an
approval card, what tier it asks at, and what a person is allowed to approve. The live copy here is
236,453 bytes and a **lineage** (a version history) that no other tool recognises; hand-patching
rows into it would make a second unrecognised shape. This step replaces that one file with the
repository's published copy - the **base** - once, keeping the old file beside it.

It is one-shot and it is guarded: it refuses unless the live file is the exact bytes it measured,
refuses unless the base is the exact bytes it classified, never overwrites an existing backup, and
re-imports the file it wrote to prove two rows the live file never had. It writes **only**
`jarvis_gate.py` and its backup; it touches nothing else.

**Run it once, and do not run it again to "check".** With the two shipped hashes, a second run
refuses at the live-file guard because the gate is no longer the drifted file it measured (its
`USAGE` line calls a second run "already the base"; the hash guard fires first in the code). That
refusal is not a fault - the check afterwards is the hash line in 8.2. **On a new PC there is
nothing to replace**: the copy made in step 3 already *is* the base, and this tool refuses there
because its live file is not the one it measured. Skip step 4 on a new PC; running it is how you
get a harmless refusal.

**VERIFIED** from `tools/replace_live_gate_from_base.py` (its whole docstring, its guards and its
`--backend-path` / `--apply` / `--allow-new-base` flags) and from
`backend/test_replace_live_gate_from_base.py` (every case built on temp copies).

1. Confirm the live file is the measured one. One line - it prints the hash and the size:

   `Get-FileHash -LiteralPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis_gate.py" -Algorithm SHA256 | ForEach-Object { $_.Hash.ToLower() }; (Get-Item -LiteralPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis_gate.py").Length`

   Good: `c2a31981d7863c1a08e2200cc208c8f0950bead1503d40614cbcaa0ce06a2f95` and `236453`.
   **If it is anything else, stop.** The tool will refuse, and that refusal is correct. Do not edit
   the hash inside the tool to get past it - that line exists so a human re-measures in a reviewed
   change instead.

2. Check only - rehearses the whole thing and writes nothing. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\replace_live_gate_from_base.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

   Good: it prints the live and base identity (bytes, lines, SHA-256), the line count it would
   change, then says check only and exits 0. **With today's base there is no `NOTE:` line** - the
   tool measures whether the base carries the expiry machinery and warns only when it does not, and
   it now does (see "What it carries now" below).

3. Write it. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\replace_live_gate_from_base.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" --apply`

   Good: a `backup:` line naming `jarvis_gate.py.bak.<today's date>`, a `wrote:` line, and a
   `re-import:` line that says a fresh interpreter found `cancel_scheduled` (cardless) and
   `github_mode` (its own risk and tool rows). Exit code 0.

   **REHEARSED**, 2026-11-26, on a byte-identical copy of this PC's backend folder: live 236,453 B
   / `c2a31981…` -> base 254,627 B / `be9f7469…`, `+762 / -410` lines, backup
   `jarvis_gate.py.bak.<date>` (236,453 B, `c2a31981…`), and the re-import found both rows. The
   copy's gate then read back **byte-identical to `<repo>\jarvis-backend\jarvis_gate.py`**, and a
   fresh interpreter imported `jarvis_agent, jarvis_quick, jarvis_gate`. `VERSION` in the copy was
   unchanged (0.2.507) because the installed desktop was unchanged; after step 6's installer it is
   the deploy that writes the new desktop's number, not this step.

   **A `main` that has moved needs its own word.** The tool also refuses unless the base is the
   exact file it classified; if a newer base has been published since this tool was written, the
   refusal names both hashes and `--allow-new-base` is the tool's one way to say out loud that the
   newer published base is the one to write. It is not a way past the live-file guard.

   **If it exits 2**, it refused and put the old file back (or wrote nothing). The message names
   why: wrong live hash, a moved base (that needs a reviewed `--allow-new-base`, not a guess), an
   existing backup, or a re-import check that failed. Nothing was silently changed; send the whole
   output back.

### What it carries now - measured, not taken on trust

**The base this replacement writes is the approval model this PC has been running.** Until
2026-11-26 it was not: the base's `pending()` counted a card down from `created`, swept stale rows
only at start-up, and had no `_wait_open` gate and no `expires_in` read from `waited_until`, so
replacing the live gate would have thrown the 2026-10-28 request-bounding machinery and the
2026-10-30 card timer away. **PR #1524 changed that**: it put both into
`jarvis-backend/jarvis_gate.py` and retired the three patches that used to carry them
(`no-expiry-cards.patch`, `no-deadline-cards.patch`, `show-card-timer.patch`).

Measured from the three files themselves on 2026-11-26 (occurrence counts in the text):

| file | bytes | sha256 | `waited_until` | `_wait_open` | `_expire_overdue` | `still_waiting` | `expires_in` | `cancel_scheduled` | `github_mode` |
|---|---|---|---|---|---|---|---|---|---|
| this PC's live gate | 236,453 | `c2a31981…` | 40 | 11 | 11 | 1 | 6 | 0 | 0 |
| `origin/main`'s base, before #1524 | 232,674 | `03964d30…` | 0 | 0 | 0 | 0 | 3 | 2 | 5 |
| the base after #1524 - what this step writes | 254,627 | `be9f7469…` | 43 | 11 | 11 | 1 | 6 | 2 | 5 |

So **all five behaviours are in the base, and `cancel_scheduled` and `github_mode` with them** - the
pair the re-import proves is no longer the only thing the write adds. That is the point: after this
step the live gate is the base, and the base carries what the live gate has been running.

The base is a published snapshot and it will move again, which is why 8.2 compares the live file
with the **repository's own** base instead of pinning these numbers.

What the replacement does **not** do: it does not apply patches and cannot make an older base
current. Its own docstring, measured over the 59 `jarvis_gate.py` patches left in the stack, says
58 of them do not apply to the published base, so **the patch stack is not a way to add to the
base** - new gate rows go into `jarvis-backend/jarvis_gate.py` and reach a live file through
`tools/repair_live_backend_gaps.py` (below).

What you should notice once it is replaced: cancels stop needing a card, and GitHub mode gets its
own risk and tool rows instead of the unclassified fallback that demanded Windows Hello (the PR
that shipped the replacement says the same;
`changelog.d/2026-11-26-replace-live-gate-from-base.md`).

**New gate rows after this** do not come from a new patch: they go into
`jarvis-backend/jarvis_gate.py` and reach the live file through
`tools/repair_live_backend_gaps.py` (the replacement tool's own NEXT line). That tool is the route
for a row or module a drifted install refuses - for example the note editor's `edit_vault_note`
risk row. Its check mode writes nothing; run it that way first, and send a `REFUSED` line back
rather than forcing `--apply`:

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\repair_live_backend_gaps.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

**The card timer is no longer something that tool needs to add.** Its timer repair rewrites
`pending()`'s SQL to read `waited_until`, which was for a base that did not carry the timer. The
published base now creates that column (`ALTER TABLE approvals ADD COLUMN waited_until`, after the
`CREATE TABLE`, so an older database still opens) and `pending()` runs that sweep on every read -
measured in the table above. New **rows** are still that tool's job; the timer is not.

**UNVERIFIED:** the exact output of that repair check on this PC right now. The tool's anchors are
the *live* file shapes; on a copy of the published base it refuses at `jarvis_hud.py` with "the
anchor for 'history' is not there any more" and writes nothing, which is the tool doing its job,
not a failed replacement. Its own docstring says it is a repair for drifted installs, and that once
the patch stack applies again the base files carry every piece and it reports "already".

**To undo this step** (one line; close Atlas first, then copy the backup over the gate, then
restart it). The backup is never overwritten, so this works even after a later run:

`Copy-Item -LiteralPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis_gate.py.bak.2026-11-26" -Destination "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis_gate.py" -Force`

Replace `2026-11-26` with the date in your own backup's name. If the backup is gone, restore the
whole folder from step 2's zip (step 9).

---

## Step 5 - The backend half: the deploy (this PC) or the patch stack (a fresh PC)

What this is: the backend files that sit beside `jarvis_gate.py` - the HUD, the memory store, the
models' glue. **There are two routes and the wrong one refuses**; one read-only line tells you which
this PC takes:

`Test-Path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\DEPLOY-MANIFEST"; Test-Path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\SOURCE-COMMIT"`

Good: `True` for the first is a **deploy-managed** PC - this one - and you run **5A**. `False` for
both is a fresh or patcher install, and you run **5B**. (`SOURCE-COMMIT` beside `VERSION` is the
older deploy evidence, and `_jarvis-deploy-backup-tool-*` folders corroborate either; the authority
for those three is `tools/update_backend.py`'s `deploy_managed_evidence`, whose own comment names
each one. A manifest that is there but unreadable is a refusal, not a fallback.)

### 5A - The deploy route (this PC)

What it is: `tools/reconcile_live_backend.py` copies the repository's published modules and the HUD
deltas into the live folder, then records what it wrote in `DEPLOY-MANIFEST` beside `VERSION`.
**It does not copy `jarvis_gate.py`** - step 4 is what replaces that file, and the deploy leaves it
alone.

**REHEARSED** on a byte-identical copy of this PC's backend folder on 2026-11-26: it finished
`RESULT: PASS - backend reconciled`, wrote 31 files, made a `_jarvis-deploy-backup-tool-<stamp>`
folder, and the gate was **byte-identical before and after**. The copy then imported
`jarvis_agent, jarvis_quick, jarvis_gate`.

1. Dry run first - it prints what it would add and update and writes nothing. One line, from the
   repository folder after step 1's `git pull`:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\reconcile_live_backend.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

   Good: the `to add` / `to update` / `unchanged` lines, then the refusals it found (if any), and no
   write. `--apply` is a no-op pass only once this is clean.

2. Write it. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\reconcile_live_backend.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" --apply`

   Good: `RESULT: PASS - backend reconciled; restart Jarvis and read the start-up banner.` and a
   `_jarvis-deploy-backup-tool-<stamp>` folder inside the backend folder. **Do not read the file
   count as a target** - the rehearsal's 31 is a dated measurement; the `PASS` line is the result.

   **If it refuses**, nothing was written and the message names why. One common one: `HEAD` is not
   the commit `--ref` names (run it from a checkout at `origin/main`, or name the commit with
   `--ref`). Send the whole output back rather than forcing a flag.

3. Read its `VERSION:` line. `VERSION: unchanged 0.2.507` or `VERSION: wrote <number> (was ...,
   from the installed desktop)` are both good. **`VERSION: skipped (no installed desktop)` is not**:
   the tool could not read an installed Jarvis Desktop, so it also writes no `DEPLOY-MANIFEST` (both
   need that pairing) - that is step 6 not done yet. Do step 6, then run this again.

**To undo this step**: close Atlas, then the deploy's own rollback. One line (the `<stamp>` is the
backup folder's own name, from the run above):

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\reconcile_live_backend.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" --rollback "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\_jarvis-deploy-backup-tool-<stamp>"`

It restores the files it overwrote, removes the ones it added, and keeps the backup folder.

### 5B - The patch stack (a fresh or patcher PC)

**Not this PC's route.** A deploy-managed install has live files the patch stack rejects by
construction - the repair tool's docstring records **37 refusals on this drifted install** (measured
2026-10-30) - and `tools/update_backend.py` skips it for exactly that reason. On a fresh PC, or one
with no deploy evidence, it is the install.

What this is: a **patch** is a small text edit to the backend files, and the **patch stack** is the
ordered list of them that the repository keeps in `scripts/apply-patches.ps1`. The script rehearses
the whole list on a throwaway copy first; if anything would fail it stops and changes **nothing** -
"NOTHING HAS BEEN CHANGED", in its own words. If the rehearsal passes it backs up every file it is
about to touch into a `_jarvis-backup-<date>` folder inside the backend folder, applies the list in
order, copies in the modules this repository ships whole, puts `jarvis-framework.toml` in place
**only if you have none** (yours is never overwritten), installs the Python packages from the
hash-locked `backend/requirements.lock`, and runs the test suites. It writes a log of everything to
`_jarvis-logs\apply-patches-<date>.txt` inside the backend folder.

**On a patcher PC whose live gate is the drifted one, step 4 runs before this step, never after** -
see the section at the top for the reason. Do not run `scripts\setup-jarvis.ps1` or
`scripts\update-jarvis.ps1` first either: both run the patch stack for you.

**VERIFIED** from `scripts/apply-patches.ps1`'s own help and its final summary: the order of the
list, the rehearsal, the backup folder, the `-Revert` switch, the refusal wording, exit 0 on a clean
run and exit 1 when it reports problems. The 37-patch figure is the repair tool's docstring
(measured 2026-10-30), not a count taken today.

1. Run it. One line (from the repository folder, with your own backend path):

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

2. Read the end of it. Three endings are possible:

   - **`ALL DONE - the backend is patched and proven`** (exit 0): the suites passed and nothing was
     skipped. This is the only ending that means fully done.
   - **`DONE - no problems, but NOT FULLY proven`** (exit 0): every file is in place, but one or
     more suites skipped part of their checks - usually a Python package or a machine feature they
     need. The skip list is printed; that is NOT fully proven, and it is not a pass.
   - **`DONE WITH PROBLEMS - do not trust this update yet`** (exit 1): read the numbered list, fix
     the first one, run the same line again, and send the `_jarvis-logs` file back if it is not
     clear. If it refused at the rehearsal it also says "NOTHING HAS BEEN CHANGED" - that is true:
     none of your files was touched.

   **UNVERIFIED: the patch stack's result anywhere.** It was not run while this page was written or
   rehearsed, so the log from your run is the evidence - and the 37 refusals are a dated record of
   this PC's install on 2026-10-30, not a promise about yours. **Do not expect step 4 to make the
   stack apply**: the replacement tool's own docstring, measured 2026-11-26, says 58 of the 59
   remaining `jarvis_gate.py` patches do not apply to the published base either, so the replacement
   is a lineage reset, not a way to re-apply the stack to it.

   **Do not use `-SkipMissing` to force a run through.** Its own help says it makes a PARTIAL
   install: the patches it leaves out are features you will not have. Only use it after you have
   looked for the missing files and they really are gone.

3. Keep the log. `_jarvis-logs\apply-patches-<date>.txt` in the backend folder is the whole run,
   and it is what someone else needs to diagnose a refusal.

**To undo this step:** close Atlas, then take the patches back off, newest first, with the same
script and `-Revert`. One line:

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" -Revert`

That leaves the modules it copied in and your `jarvis-framework.toml` where they are (its own
message says so), and it does **not** put back the old `jarvis_gate.py` - that is step 4's backup.
To undo the whole run in one go, restore step 2's zip instead (step 9).

---

## Step 6 - The desktop build

**When: on this PC, before step 5's deploy.** The deploy writes `VERSION` from the installed
desktop, so the desktop goes in first and the marker and the HUD agree (the section at the top has
the measurement and DEF-100). On a PC that runs the patch stack (5B) this step can come at any point
before step 8: the patch stack does not write `VERSION` at all.

What this is: the **desktop app** (Windows lists it as **Jarvis Desktop**) is the Windows app - the
bar, the tray icon, the HUD window. It is a **Tauri** app: a Rust program that shows a web page in a
window. Building it means compiling that Rust, which needs Microsoft's C++ build tools, Rust and
Node.js. The result is an installer you run; it is **not signed**, so it is not what other people
download, and Windows will warn once.

Why build it at all: the signed installer on the `desktop-latest` release is CI's build of `main`,
and it can lag the merge you just pulled. Building here is how you drive the merged tree. If you
only want the app, the release is five clicks and needs none of these tools
(`docs/INSTALL.md` section 2.1).

**VERIFIED** from `docs/INSTALL.md` Appendix A: the three programs, the build line, the output
folder, and "a local build is not a published one". The one change is the shared build cache on
`D:`, which is this repository's rule so a build cannot fill `C:` (`CLAUDE.md`, "Build caches live
in ONE place").

1. **First time only** - install the three build programs. One line (large; the build tools alone
   take a while):

   `winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"; winget install --id Rustlang.Rustup -e; winget install --id OpenJS.NodeJS.LTS -e`

   Then **close PowerShell and open a new one** - a program you just installed is only found by
   windows opened after it.

2. Build it. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\jarvis-desktop"; $env:CARGO_TARGET_DIR = "D:\jarvis-cache\cargo-target"; npm install; npm run tauri build`

   It takes 20-40 minutes cold. The installers land in
   `D:\jarvis-cache\cargo-target\release\bundle\` - `nsis\*-setup.exe` and `msi\*.msi`. **Use the
   NSIS one.** (The folder is wherever `CARGO_TARGET_DIR` points; without it, INSTALL's path is
   `jarvis-desktop\src-tauri\target\release\bundle\`.)

   **UNVERIFIED:** the exact output path with `CARGO_TARGET_DIR` set, and the build line combined
   with the cache variable. Both parts are from the repository separately; they were not run
   together while writing this page.

3. Install the build. One line, or double-click the newest `*-setup.exe` in that `nsis` folder:

   `$i = Get-ChildItem "D:\jarvis-cache\cargo-target\release\bundle\nsis\*-setup.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1; Start-Process $i.FullName`

   Windows says it "protected your PC" because the build is unsigned: **More info -> Run anyway**
   (INSTALL section 2.2). No UAC prompt; it installs for your account under `%LOCALAPPDATA%`.

   **If the installer loops instead of installing, use the fallback below.** Measured on this PC
   on 2026-11-26, driven page by page (DEF-108): the NSIS installer reaches **Already Installed**
   and `Next` returns to that same page, so the install never starts; `/UPDATE /S` exits **0** in
   0.4 s and `/UPDATE /S /D=…` exits **0** in 0.2 s, and both install nothing - a zero exit code
   from the silent switch is **not** a success here, which is exactly why this is written down.
   The same happens on a build whose version number is already the installed one.

   **The non-elevated fallback that works on this PC: extract the MSI and copy the files.** It needs
   no administrator rights and registers nothing:

   1. Extract the build's `.msi` (it sits beside the `nsis` folder in the same `bundle` directory):

      `$msi = Get-ChildItem "D:\jarvis-cache\cargo-target\release\bundle\msi\*.msi" | Sort-Object LastWriteTime -Descending | Select-Object -First 1; $out = "$env:TEMP\jarvis-msi-extract"; $null = New-Item -ItemType Directory -Force -Path $out; $p = Start-Process msiexec.exe -ArgumentList @('/a', "`"$($msi.FullName)`"", '/qn', "TARGETDIR=`"$out`"") -Wait -PassThru; "msiexec exit $($p.ExitCode)"; Get-ChildItem -Recurse "$out" -Filter 'jarvis-desktop.exe' | ForEach-Object { $_.FullName }`

      It exits **0** and the last line prints where the extracted program landed. Nothing is
      installed and no registry entry is written.
   2. Back up the installed copy first, then copy the extracted files over it:

      `$live = "$env:LOCALAPPDATA\Jarvis Desktop"; Copy-Item -Recurse -Force $live "$live.bak-$(Get-Date -f yyyyMMdd-HHmmss)"; $src = Split-Path (Get-ChildItem -Recurse "$env:TEMP\jarvis-msi-extract" -Filter 'jarvis-desktop.exe' | Select-Object -First 1).FullName; Copy-Item -Force "$src\*" $live; (Get-Item "$live\jarvis-desktop.exe").VersionInfo.FileVersion`

      The last line must print the version you built. Measured on this PC on 2026-11-26 with
      0.2.519: four files copied, every hash matching the MSI payload, and the app started.
   3. Two limits, said plainly: an extracted copy is **not** a registered install, so Settings ->
      Apps keeps showing the old version and `uninstall.exe` stays the old one; and this is a
      recovery for **this PC**, not the normal path. If the installer works on your machine, use it.

4. Point it at the backend (INSTALL section 2.5): tray icon -> **Settings and help...** ->
   **More options** -> **Starting Jarvis for you** -> **Find it for me** for the program, the full
   path of `jarvis_hud.py` for the arguments, then the switch, **Save**, **Start**. Leave its address
   at `http://127.0.0.1:4719`.

   **After building from source, do not press Update in Settings -> Updates unless you mean to
   replace your build with the published one.** A published build is numbered above a hand-built
   copy (INSTALL section 2.1 / the release workflow's version scheme), so it is offered as newer
   even when its code is the same or older. Nothing installs on its own - a person presses the
   button.

**To undo this step:** Settings -> Apps -> **Jarvis Desktop** -> Uninstall, then install the
published installer from the `desktop-latest` release if you want it back (INSTALL section 2.1).

---

## Step 7 - The phone APK

What this is: an **APK** is the Android installer file for the phone app, `jarvis-client`. **The
only APK that may be installed is CI's `client-latest` release.** It is built and signed by GitHub
Actions, and the same file is first installed on an Android emulator and started before it is
published. **Never install a local build on the phone** - that rule is in `CLAUDE.md` ("the APK
that is published and installed is still CI's") and `docs/INSTALL.md` section 3.3.

The release is rolling: its URL stays the same, but it keeps **one** APK, named
`jarvis-client-<commit>.apk`, and the previous APK is deleted when a newer one is published. Its
notes say which branch and commit it was built from.

**VERIFIED** from `docs/INSTALL.md` section 3.3 and `.github/workflows/jarvis-client.yml`: the
`client-latest` tag, the `jarvis-client-<commit>.apk` asset, `adb install -r`, the two failure
messages, and the fact that only the newest APK stays on the release.

1. Open the release page (one line; the link works in a browser too):

   `Start-Process "https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest"`

2. Download the single `.apk` on that page. On the phone, open the same page and tap it - Android
   asks once for permission to install apps from that browser. Or from the PC over USB:

   - Turn on USB debugging on the phone (Settings -> About phone -> tap **Build number** seven
     times, then Settings -> System -> Developer options -> **USB debugging**), plug it in, accept
     the prompt on the phone.
   - `adb` comes with Google's SDK Platform Tools if you do not have it, one line:
     `winget install --id Google.PlatformTools -e`
   - Install the newest APK you downloaded, one line (it picks the most recent
     `jarvis-client-*.apk` in your Downloads folder):

     `$apk = Get-ChildItem "$env:USERPROFILE\Downloads\jarvis-client-*.apk" | Sort-Object LastWriteTime -Descending | Select-Object -First 1; adb install -r $apk.FullName`

     **UNVERIFIED:** that one-liner's file-picking half. `adb install -r` and the file name are from
     INSTALL; the "newest in Downloads" wrapper is mine and was not run.

   **Do not uninstall to get past `INSTALL_FAILED_VERSION_DOWNGRADE`.** It means the APK is older
   than the copy on the phone - an uninstall wipes the app's data and the pairing token with it.
   Get the newest APK from `client-latest` instead. `INSTALL_FAILED_UPDATE_INCOMPATIBLE` means the
   installed copy was signed with an older key; `keystore/README.md` has the three steps.

3. The phone reaches the PC only through **Tailscale** or **NordVPN Meshnet**, both private
   device-to-device networks - never a public tunnel. Install and sign in to one on both devices
   first (`docs/INSTALL.md` section 3.1); with no mesh running the app says "Your PC isn't
   answering", which reads like an Atlas fault and is not one.

4. Pair. In the phone app: **Pairing**, the PC's mesh name with `:4719` (for Tailscale it ends in
   `.ts.net`; for Meshnet it ends in `.nord`), then the token. The token is on the PC - from the
   backend folder, one line:

   `cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 jarvis_token_store.py show`

   or the desktop app -> Settings -> **Connection** -> **Show the token for my phone**. Spaces do
   not matter. **Never put the token in a file, a message or a log.**

**To undo this step:** uninstall the app, which also deletes its data and the pairing token (one
line): `adb uninstall com.jarvis.client`. There is no "previous version" to go back to on the
release - it keeps only the newest APK - so a phone rollback means uninstall, install an APK you
saved yourself, and pair again.

---

## Step 8 - The after-checks, and driving it

What this is: the checks that prove the whole chain is alive, and then the only proof that counts -
using it. Nothing here changes a file; starting the backend is the only action.

**VERIFIED** from `docs/INSTALL.md` sections 1.9 and 1.11 and `backend/selftest.py`'s own docstring
(`--preflight` checks the backend that is running, is read-only, and exits 1 on any FAIL). 8.8 and
8.9 are the repository's own rules, quoted where they are used.

### 8.1 Start the backend

One line. Leave this window open - everything it prints goes here and nowhere else:

`cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $env:HF_HUB_DISABLE_TELEMETRY = "1"; $env:DO_NOT_TRACK = "1"; $env:ANONYMIZED_TELEMETRY = "False"; py -3 jarvis_hud.py`

Read the top of what it prints. A `token` line saying **in Windows Credential Manager** is good. A
line saying `NOT SAVED`, `STILL IN THE OLD PLAIN-TEXT FILE`, or `token NONE` is a real failure, and
the lines under it say why (INSTALL section 1.9).

### 8.2 The gate is the repository's base, byte for byte

Compare the live gate with the base in the repository you installed from. One line, read-only - it
prints each file's path, its size and its SHA-256:

`$g = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis_gate.py"; $b = "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\jarvis-backend\jarvis_gate.py"; foreach ($p in @($g,$b)) { $h = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower(); $n = (Get-Item -LiteralPath $p).Length; "{0}  {1}  {2}" -f $p, $n, $h }`

Good: two lines that differ only in the path - the same byte count and the same SHA-256. **The
number is deliberately not written down here.** The base moves every time the repository publishes a
new one, and a frozen hash in a page goes stale the day it does; this compares two files on your own
PC, so it stays true. (On 2026-11-26, at PR #1524, both read `be9f7469…` and `254627`.)

If they differ, name both before believing anything is broken. A `git pull` that brings a newer base
after step 4 leaves the live gate one base behind - the replacement only accepts the drifted live
file, so a second run refuses; that difference is expected, not a fault. A patch stack run after
step 4 (5B, not this PC's route) can change the gate too. Write both hashes down and send them back
rather than forcing a tool.

### 8.3 The backend folder is complete

One line (read-only):

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

Good: no `MISSING`. A `not yet` after a fully successful step 5 would mean the run did not put
everything in - read the run's own record: `_jarvis-logs\apply-patches-<date>.txt` for the patch
stack (5B), the deploy tool's own output for 5A.

### 8.4 The live check

In a **second** PowerShell window, one line. It checks the running Atlas end to end and saves the
result as `preflight.txt` on your Desktop:

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; $env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $env:PYTHONIOENCODING = "utf-8"; py -3 backend\selftest.py --preflight | Tee-Object -FilePath "$env:USERPROFILE\Desktop\preflight.txt"; Write-Host "Saved to $env:USERPROFILE\Desktop\preflight.txt"`

Good: it ends with "N pass, N fail, N warn" and no FAIL. Each FAIL says what to do. A WARN is not a
pass either; read it.

### 8.5 The desktop app

The desktop app should be running from step 6; start it from the Start menu if it is not. Press
`Alt+Space` (or tray -> **Show or hide the Atlas bar**), type `hello`, press Enter. An answer means
the desktop reached the backend and the model answered. If the HUD says "demo - not connected", it
could not reach the backend - check 8.1 and the address in Settings -> Connection (INSTALL section
2.3).

### 8.6 Approve a card

Ask for something that needs a card (for example a file or a note change), and approve it. Windows
Hello must be asked for a risky action; if this PC has no Windows Hello set up, risky approvals are
refused with a message saying so (INSTALL section 2.6). **Never approve in bulk and never clear a
card without reading it** (`CLAUDE.md`, the five rules).

### 8.7 The phone

With the mesh on and the app paired: open it, ask a question, and see the answer. If it says "Your
PC isn't answering", the causes are in `docs/INSTALL.md` section 3.4, in the order worth checking.

### 8.8 Which name does your PC answer to?

**Do not say "Hey Atlas" unless your PC's own `wake_phrase` is `hey_atlas`.** The installer puts
`jarvis-framework.toml` in place **only if you have none**, and it never overwrites yours - so a PC
that already had one **keeps whatever phrase it had**, which is usually `hey_jarvis`. A fresh PC
gets `hey_atlas`, because that is what the shipped file says (`backend/rebuilt/jarvis-framework.toml`,
`[voice] wake_phrase`). The phone listens for **"Hey Atlas"** - that is the model the APK carries -
and the PC reads every clip back and refuses one whose transcript does not start with **its own**
configured phrase, so a PC left on `hey_jarvis` will refuse a phone wake that says "Hey Atlas" until
the one line below is run (`CLAUDE.md`, "The product is Atlas").

First, see which file holds the phrase and what it says. One line, read-only (the first `->` line
that prints a phrase is your settings file):

`$p = @("$env:USERPROFILE\.openjarvis\jarvis-framework.toml", "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis-framework.toml") | Where-Object { Test-Path -LiteralPath $_ }; $p | ForEach-Object { "$_ -> " + ((Select-String -LiteralPath $_ -Pattern '^\s*wake_phrase\s*=' | Select-Object -First 1).Line) }`

If it says `wake_phrase = "hey_atlas"`, the PC answers to **"Hey Atlas"** - and so does the phone,
and the desktop's Settings -> Voice reads the phrase from the PC (`/api/voice/status`). If it says
`hey_jarvis`, the PC answers to **"Hey Jarvis"**; leave it if you want that, or move it with the one
line below.

**The one line that moves it to `hey_atlas`** (it edits only the first settings file that actually
has a `wake_phrase` line; then restart the backend so it is read). **UNVERIFIED:** this line was
written and syntax-checked on a copy of the shipped file while writing this page, but it has not
been run against a real PC's settings file.

`$c = @("$env:USERPROFILE\.openjarvis\jarvis-framework.toml", "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis-framework.toml") | Where-Object { Test-Path -LiteralPath $_ } | Where-Object { Select-String -LiteralPath $_ -Pattern '^\s*wake_phrase\s*=' -Quiet } | Select-Object -First 1; if ($c) { $t = Get-Content -LiteralPath $c -Raw; [IO.File]::WriteAllText($c, ($t -replace '(?m)^(\s*)wake_phrase\s*=\s*"[^"]*"', '${1}wake_phrase = "hey_atlas"')); (Select-String -LiteralPath $c -Pattern 'wake_phrase').Line.Trim(); "Changed: $c" } else { "No wake_phrase line found - open jarvis-framework.toml yourself and edit the line under [voice]" }`

Then restart the backend (close the step 8.1 window, run 8.1 again). If your file writes the value
with single quotes, not double, edit it by hand in Notepad - this line only matches the double-quoted
form the shipped file uses. **Nothing on this page proves the 0.1-false-accepts-per-hour bar for the
wake word** - that bar is unmeasured, and no phone microphone has been driven here (`CLAUDE.md` says
so too - do not claim it).

### 8.9 Drive it, and write down what you could not

Do the four things in "What 'driving the merged work' means here", and for anything you cannot
reach write **BLOCKED**, **PARTIAL** or **NOT-TESTABLE** - never PASS. A `BLOCKED` line is a true
record; a PASS you did not earn is a lie that later work builds on
(`docs/FIELD-TEST-MATRIX-2026-10-11.md`, `docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md`).

**To undo this step:** stop the backend (Ctrl+C in the 8.1 window, or tray -> **Quit Atlas**).
Nothing else changed; the checks are read-only.

---

## Step 9 - Rollback, step by step

Use the smallest undo that fixes the problem, and do them in reverse order if you are undoing
several steps. Stop Atlas first for anything that touches the backend folder.

| step | to undo it | what it leaves behind |
|---|---|---|
| 1 pre-checks | nothing to undo | - |
| 2 backup | delete the two zips | nothing else changed |
| 3 backend install | unset `JARVIS_BACKEND`; delete the copied folder if you made one | your only backend folder is untouched |
| 4 gate replacement | copy `jarvis_gate.py.bak.<date>` back over `jarvis_gate.py`, restart | the backup file stays |
| 5A deploy (this PC) | close Atlas, then `reconcile_live_backend.py --backend-path "<live>" --rollback "<live>\_jarvis-deploy-backup-tool-<stamp>"` | the `_jarvis-deploy-backup-tool-<stamp>` folder stays |
| 5B patch stack | `apply-patches.ps1 -Revert`, or restore step 2's zip | the modules it copied in and your settings file stay |
| 6 desktop build | Settings -> Apps -> Jarvis Desktop -> Uninstall | settings under `%LOCALAPPDATA%` may stay |
| 7 phone APK | `adb uninstall com.jarvis.client` | app data and the pairing token are gone |
| 8 after-checks | stop the backend | - |
| 8.8 wake phrase | the same one line with `hey_jarvis` in place of `hey_atlas`, then restart | - |

**The one-line full undo** - stop Atlas, then put the whole folder back from step 2's zip. It
overwrites files, so use it only when you mean to go back to the moment before this runbook began:

`Expand-Archive -LiteralPath "$env:USERPROFILE\Desktop\jarvis-backend-before-runbook-2026-11-26.zip" -DestinationPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" -Force`

Change the date in the file name to the day you took the backup. **UNVERIFIED:** this line's exact
behaviour on a folder whose files changed after the backup - it writes over them, which is the
point, but it does not delete files that were added since. Files added after the backup (for
example a `_jarvis-backup-<date>` folder or a `.bak` file) simply remain.

---

## What is still UNVERIFIED, and what to send back

**The install itself.** This page has not been run end to end on the live folder. The two backend
steps were **rehearsed** on a byte-identical copy on 2026-11-26 (deploy: `RESULT: PASS - backend
reconciled`, 31 files; gate: 236,453 B `c2a31981…` -> 254,627 B `be9f7469…`, `+762 / -410`), and
everything marked VERIFIED was read out of the repository. **Nothing was installed:** the live gate
is still `c2a31981…`, and the live folder was read, never written. A rehearsal is not an install, so
the live folder's own run is the evidence that is still missing.

The specific pieces I could not verify from the repository, with what is missing:

- **The desktop half.** Step 6's build and install were not run - the rehearsal copied the backend
  folder, not the desktop - so `VERSION` being written from the **new** desktop's FileVersion, the
  reason step 6 goes first, is proved by the code and by DEF-100's log, not by this install.
- **The patch stack's result anywhere.** The repository records 37 refusals on the 2026-10-30
  drifted install (the repair tool's docstring), and no run's log for a patcher PC exists in the
  repository. The run's own `_jarvis-logs\apply-patches-<date>.txt` is the missing evidence.
  **Do not expect step 4 to make the stack apply:** 58 of the 59 remaining `jarvis_gate.py` patches
  do not apply to the published base (the replacement tool's docstring, measured 2026-11-26).
- **The repair tool's output on this PC after the replacement.** Its anchors are the live shapes; a
  copy of the published base refuses at `jarvis_hud.py` ("the anchor for 'history' is not there any
  more") and writes nothing. What it says on the live folder is unmeasured.
- **Whether a later deploy refreshes the gate in `DEPLOY-MANIFEST`.** This PC's manifest lists
  `jarvis_gate.py` at 236,453 B / `c2a31981…` (read 2026-11-26), so step 4 leaves that record naming
  the file it replaced; the deploy plans a new manifest from the live bytes, which should refresh it
  on the next run, but that run was not made.
- **Step 2's zip lines** and **step 9's `Expand-Archive` line** - standard PowerShell, not run here.
- **8.8's two lines** (the read-only one, and the one that moves the wake phrase) were syntax-tested
  on a copy of the shipped `jarvis-framework.toml`, not on a real settings file. The single-quote
  caveat is stated in 8.8.
- **Step 6's build**, run with `CARGO_TARGET_DIR` set, and the exact output path that follows from
  it. INSTALL's build line and output path are for the default target folder; the cache variable is
  this repository's rule, and the two were not run together here.
- **Step 7's "newest APK in Downloads" one-liner** - `adb install -r` and the asset name are from
  INSTALL; the file-picking wrapper is mine.
- **Timings** (about an hour for the backend half, 20-40 minutes for a cold build) are INSTALL's
  figures, not measured for this page.

Send back, for any step that does not behave as written: the whole window (not a screenshot of one
line), the step number, and the log file it names - `_jarvis-logs\apply-patches-<date>.txt` for 5B,
the deploy tool's own output for 5A, and the replacement tool's own output (which names the refusal)
for step 4. **Never send the pairing token or a password** - no line on this page prints one.
