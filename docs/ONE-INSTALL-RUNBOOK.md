# One install runbook - from nothing installed to driving the merged work

**The short answer: eight steps, in this order.** Check the PC and the repository -> back up the
backend folder and its data -> tell Windows where the backend folder is (copying the published one
only on a new PC) -> replace the one drifted approval-gate file from the repository's published
copy -> run the patch stack **after** that replacement -> build the desktop app from the merged tree
-> install the phone APK that CI built -> check the whole chain by driving it. Every step ends with
the one line that undoes it.

**This document has NOT been executed.** It was written on 2026-11-26 by reading the files named
beside each claim, and no step has been run end to end. Two labels are used throughout:

- **VERIFIED** - the command or claim was read out of the named file in this repository on
  2026-11-26. It does **not** mean the command has been tried.
- **UNVERIFIED** - I could not read it out of the repository at all. The text says exactly what is
  missing.

Treat the first run as a test of this page, and send back the output if a line does not behave as
described here. Do not "fix" a refusal by editing a guard; the guards are the point.

**Written against** merged `main` at `f9ed4cc36` (2026-11-26 10:58 -0800, the merge of PR #1519).
Run `git pull` first; if `main` has moved since, the files named here may have moved with it, so
check the file before trusting a line.

**What "driving the merged work" means here.** The backend you end up with is the repository's
published copy of the approval gate plus whatever the patch stack can still put on this PC; the
desktop app is built from this checkout; the phone app is the APK CI built from this project. You
have driven it when you have typed a question in the desktop app, approved a card with Windows
Hello, opened the phone app, and (only if your PC is set to it - see 8.8) said the wake phrase.
Anything you could not reach is written down as BLOCKED, PARTIAL or NOT-TESTABLE. **A screen you
could not read is not a pass**, and a feature that could not be reached is never a pass
(`docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md`, `docs/FIELD-TEST-MATRIX-2026-10-11.md`).

---

## The one order that is not negotiable: the gate replacement runs before the patch stack

This runbook deliberately puts **the gate replacement (step 4) before the patch stack (step 5)**.
That is not a preference; it is what the two tools require:

- The replacement tool (`tools/replace_live_gate_from_base.py`) **refuses unless the live
  `jarvis_gate.py` is byte-for-byte the file it was measured against** - SHA-256
  `c2a31981d7863c1a08e2200cc208c8f0950bead1503d40614cbcaa0ce06a2f95`, 236,453 bytes. Any patch
  that touched that file first would change the hash, and the tool would refuse forever (until a
  reviewed change re-measures it). **Nothing may touch the live gate before step 4.**
- `backend/test_replace_live_gate_from_base.py`'s own docstring says what the replacement is for:
  the tool replaces the unrecognised file "with the published base - once, with the old file kept -
  and then the patch stack can be applied to a recognised file again."
- It is the patch stack that refuses on this PC today: the repair tool's docstring records that
  `scripts/apply-patches.ps1` **refuses 37 patches on this drifted install** (measured 2026-10-30).
  Running it before the replacement proves nothing and risks the gate's identity.

And one thing that must be said plainly rather than discovered later: **the gate replacement does
not carry the patch-stack behaviour, and the patch stack cannot put it back on the base.** The
2026-10-28 request-bounding and the 2026-10-30 card timer are patch-carried, the base does not have
them, and 58 of the 62 `jarvis_gate.py` patches do not apply to the base either (the replacement
tool's own docstring, measured 2026-11-26). Step 4 spells out exactly what is lost. If it must
survive, it has to be taken into `jarvis-backend/jarvis_gate.py` first - a separate reviewed change
that this page cannot do.

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

**This is a document.** Nothing on this page was executed by the session that wrote it, and this
PC's live backend folder was not read or touched while it was written.

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
   backend's own `jarvis_hud.py` is running, because a running backend has the files open and would
   go on running the old code. There is no command for this - use the window and the tray.

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

**UNVERIFIED.** Both lines are ordinary PowerShell and are the shape `docs/INSTALL.md` uses for
copies, but this exact backup was not run while writing this page. If a zip fails, a file is open -
close Atlas and try again. Do not go on with a backup you do not have.

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
   that is expected before the patch stack.

**If it refuses:** a folder without `jarvis_hud.py` is refused before the setting is written, so a
wrong path cannot be half-installed. Nothing changes; run it again with the right folder.

**To undo this step:** remove the setting (one line), and, if you made the copy in line 1, delete
only that copy (second line). Never run the delete against your only backend folder.

`[Environment]::SetEnvironmentVariable('JARVIS_BACKEND', $null, 'User')`

`Remove-Item -Recurse -Force "$env:USERPROFILE\Documents\jarvis-backend"`

---

## Step 4 - The gate replacement (must run before the patch stack)

What this is: `jarvis_gate.py` is the **approval gate** - the one file that decides what needs an
approval card, what tier it asks at, and what a person is allowed to approve. The live copy here is
236,453 bytes and a **lineage** (a version history) that no other tool recognises; hand-patching
rows into it would make a second unrecognised shape. This step replaces that one file with the
repository's published copy - the **base** - once, keeping the old file beside it.

It is one-shot and it is guarded: it refuses unless the live file is the exact bytes it measured,
refuses unless the base is the exact bytes it classified, never overwrites an existing backup, and
re-imports the file it wrote to prove two rows the live file never had. It writes **only**
`jarvis_gate.py` and its backup; it touches nothing else.

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

   Good: it prints the live and base identity, the line count it would change, and the
   **approval-model note** (read it - see "What it does NOT carry" below), then says check only and
   exits 0.

3. Write it. One line:

   `cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\replace_live_gate_from_base.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" --apply`

   Good: a `backup:` line naming `jarvis_gate.py.bak.<today's date>`, a `wrote:` line, and a
   `re-import:` line that says a fresh interpreter found `cancel_scheduled` (cardless) and
   `github_mode` (its own risk and tool rows). Exit code 0.

   **If it exits 2**, it refused and put the old file back (or wrote nothing). The message names
   why: wrong live hash, a moved base (that needs a reviewed `--allow-new-base`, not a guess), an
   existing backup, or a re-import check that failed. Nothing was silently changed; send the whole
   output back.

### What it does NOT carry - say this out loud before you run it

The base is a published snapshot, **not** a superset of the live file. Measured for this
replacement (2026-11-26), the base does **not** carry:

- the **2026-10-28 request-bounding machinery** - `waited_until`, `_wait_open`, `_expire_overdue`,
  `still_waiting`, the read-time sweep and the no-deadline ceremonies;
- the **2026-10-30 card timer** from `show-card-timer.patch` - an `expires_in` counted from
  `waited_until` while the request is still waiting, with the 60-second grace not shown;
- and it does not merge, apply patches, or invent any of that. `58 of the 62` `jarvis_gate.py`
  patches do not apply to the base either, so **the patch stack in step 5 is not a way to get the
  two behaviours back**.

What the base carries instead is its own older approval model: `pending()` counts a card down from
`created` plus `APPROVAL_TIMEOUT`, and stale rows are swept only at start-up. The tool prints that
note before it writes, so it is not a surprise afterwards. If the patch-carried behaviour has to
survive, it must be taken into `jarvis-backend/jarvis_gate.py` first, as a separate reviewed
change.

What you should notice once it is replaced: cancels stop needing a card, and GitHub mode gets its
own risk and tool rows instead of the unclassified fallback that demanded Windows Hello (the PR
that shipped the replacement says the same; `changelog.d/2026-11-26-replace-live-gate-from-base.md`).

**New gate rows after this** do not come from a new patch: they go into
`jarvis-backend/jarvis_gate.py` and reach the live file through
`tools/repair_live_backend_gaps.py` (the replacement tool's own NEXT line). That tool is the route
for a row or module a drifted install refuses - for example the note editor's `edit_vault_note`
risk row. Its check mode writes nothing; run it that way first, and send a `REFUSED` line back
rather than forcing `--apply`:

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\repair_live_backend_gaps.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

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

## Step 5 - The patch stack

What this is: a **patch** is a small text edit to the backend files, and the **patch stack** is the
ordered list of them that the repository keeps in `scripts/apply-patches.ps1`. The script rehearses
the whole list on a throwaway copy first; if anything would fail it stops and changes **nothing** -
"NOTHING HAS BEEN CHANGED", in its own words. If the rehearsal passes it backs up every file it is
about to touch into a `_jarvis-backup-<date>` folder inside the backend folder, applies the list in
order, copies in the modules this repository ships whole, puts `jarvis-framework.toml` in place
**only if you have none** (yours is never overwritten), installs the Python packages from the
hash-locked `backend/requirements.lock`, and runs the test suites. It writes a log of everything to
`_jarvis-logs\apply-patches-<date>.txt` inside the backend folder.

**This step runs after step 4, never before it** - see the section at the top for the reason. Also,
**do not run `scripts\setup-jarvis.ps1` or `scripts\update-jarvis.ps1` before step 4**: both run the
patch stack for you.

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

   **UNVERIFIED: what this run prints on this PC after step 4.** The replacement gives the
   patch stack a recognised `jarvis_gate.py` to work against (the test's docstring says it "can be
   applied to a recognised file again"), and the patcher treats the published base as the state
   *after* the patches, so expect some patches to be reported as already on. What is not measured
   is whether every one of the 37 refusals is gone; the log from your run is the answer, and it is
   the file to send back.

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

### 8.2 The gate is the base it was replaced with

One line (check only; writes nothing):

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; py -3 tools\replace_live_gate_from_base.py --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

Good: `ok: the live gate is already the published base byte for byte; nothing to do.` If the patch
stack changed the gate after step 4, this refuses instead - that is the guard telling you the file
is no longer the classified one, and worth sending back rather than forcing.

### 8.3 The backend folder is complete

One line (read-only):

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; powershell -ExecutionPolicy Bypass -File .\scripts\check-backend.ps1 -BackendPath "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`

Good: no `MISSING`. A `not yet` after a fully successful step 5 would mean the run did not put
everything in - read the patch log.

### 8.4 The live check

In a **second** PowerShell window, one line. It checks the running Atlas end to end and saves the
result as `preflight.txt` on your Desktop:

`cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"; $env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $env:PYTHONIOENCODING = "utf-8"; py -3 backend\selftest.py --preflight | Tee-Object -FilePath "$env:USERPROFILE\Desktop\preflight.txt"; Write-Host "Saved to $env:USERPROFILE\Desktop\preflight.txt"`

Good: it ends with "N pass, N fail, N warn" and no FAIL. Each FAIL says what to do. A WARN is not a
pass either; read it.

### 8.5 The desktop app

The desktop app should be running from step 6. Press `Alt+Space` (or tray -> **Show or hide the
Atlas bar**), type `hello`, press Enter. An answer means the desktop reached the backend and the
model answered. If the HUD says "demo - not connected", it could not reach the backend - check
8.1 and the address in Settings -> Connection (INSTALL section 2.3).

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
form the shipped file uses. The phrase this creates is **not** the same as the 0.1-false-accepts-per-
hour bar; that bar is unmeasured, and no phone microphone has been driven here (`CLAUDE.md` says so
too - do not claim it).

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
| 5 patch stack | `apply-patches.ps1 -Revert`, or restore step 2's zip | the modules it copied in and your settings file stay |
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

**The whole page.** It has not been run end to end. Everything marked VERIFIED was read out of the
repository; nothing marked VERIFIED was executed.

The specific pieces I could not verify from the repository, with what is missing:

- **The patch stack's result on this PC after the gate replacement.** The repository records
  37 refusals on the 2026-10-30 drifted install (the repair tool's docstring), and the replacement's
  test says the patch stack can be applied to a recognised file again, but no run's log for the
  post-replacement state exists in the repository. The run's own
  `_jarvis-logs\apply-patches-<date>.txt` is the missing evidence.
- **The repair tool's output on this PC after the replacement.** Its anchors are the live shapes; a
  copy of the published base refuses at `jarvis_hud.py` ("the anchor for 'history' is not there any
  more") and writes nothing. What it says on the live folder is unmeasured.
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
line), the step number, and the log file it names. For step 5 that is
`_jarvis-logs\apply-patches-<date>.txt`; for step 4 it is the tool's own output, which names the
refusal. **Never send the pairing token or a password** - no line on this page prints one.
