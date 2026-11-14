# Wave-13 ROLLBACK — restore the previous, verified Wave-12 state

Only when a deploy gate says STOP, or the owner asks. Do the steps **in this order**.
The measured baseline this restores to is the **Wave-12 deploy of 2026-11-09 09:20 PT**:
backend `0.2.442` sealed from merge `d6df40225de7c7400b302744f10043f284496cd5`, desktop
`0.2.442`, phone `0.2.4035` / `versionCode 1000004035`, owner TOML `58,409 B` /
`9C6CDF7644D67D8CBAF19B71DA574A3ED5DF95DDC09C6C2C2B565AC134C92D97`, both listeners,
HTTP 403. Those values are measured (Wave-12 result doc + its run folder), not remembered
from an older wave.

Paths used below — run these first, in the same PowerShell window:

```powershell
$root = 'C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main'
$run  = (Get-Content 'C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\WAVE13-DEPLOY-2026-11-09\CURRENT-RUN.txt' -Raw).Trim()
"run=$run files=$(@(Get-ChildItem $run -File).Count)"
$tree = 'C:\Users\pcadmin\Documents\jarvis-install-tree'
$live = 'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program'
$w12run = "$root\.dsh-scratch\WAVE9-DEPLOY-2026-11-08\run-20261109-092148"
$w12    = "$w12run\artifacts"
```

`$run` is the folder `CURRENT-RUN.txt` pins — **read it, never type a `<stamp>`**. It has
already moved twice today (it now points at `run-20261109-1540`), and every file this procedure
needs is written into the pinned folder by the gates.

`$w12` is the Wave-12 run folder's `artifacts`. The sibling
`.dsh-scratch\WAVE9-DEPLOY-2026-11-08\artifacts\` (one folder up from `$w12run`) is the
**wrong** folder: it holds the older wave-11 APK (`jarvis-client-2644d57.apk`, `0.2.4028`) and
the `0.2.440` / `0.2.441` setups. The sha256 STOP in steps 4 and 5 is what catches one of those
being installed by mistake.

## 0. First: prove the stack is stopped

Never restore files under a listener. Repeat the stop proof:

```powershell
netstat -ano | findstr ":4719" | findstr "LISTENING"          # must print nothing
try { Invoke-WebRequest 'http://127.0.0.1:4719/api/status' -UseBasicParsing -TimeoutSec 10 } catch { "refused as required" }
```

**STOP DOING THE RESTORE** if a listener survives — kill it with
`taskkill /IM jarvis-desktop.exe /T /F` and the PIDs from `netstat`, then re-prove.

## 1. Preferred backend restore: the reconcile tool's own journal

The apply wrote its backup journal and printed a `BACKUP:` line; the run folder holds it in
`backup-folder-tool.txt`. This restores exactly the files the tool touched, including the
ones it added and the `.pyc` it purged.

The journal folder is **inside the live backend folder**:
`...\Open jarvis files\Desktop program\_jarvis-deploy-backup-tool-<stamp>\`. It already holds
**26** such folders (**442.9 MB**); this apply adds the **27th** (~17 MB). Address it **only**
through `$run\backup-folder-tool.txt` — the names are timestamps and 26 siblings look alike.
**Keep the folder after the rollback**: it is the only per-file copy of the pre-deploy bytes.
The deep fallback's `robocopy /E` does not purge it, and Gate 0H's `backupFolders 26->26` line
reads **27** after this apply — that is correct, not a failure.

```powershell
$toolBak = (Get-Content "$run\backup-folder-tool.txt").Trim()
"restoring=$toolBak files=$(@(Get-ChildItem $toolBak -Recurse -File).Count)"
py -3 -B "$tree\tools\reconcile_live_backend.py" --backend-path $live --rollback $toolBak 2>&1 |
  Tee-Object -FilePath "$run\rollback.txt"
"exit=$LASTEXITCODE"
"VERSION=$((Get-Content (Join-Path $live 'VERSION') -Raw).Trim())"
```

**GO:** the tool reports `ROLLBACK: restored N overwritten path(s), removed M new path(s)` and
`ROLLBACK OK`, and `VERSION` reads `0.2.442` again. The paths it touches are exactly the ones the
apply journalled: the 23 its own `wrote 23` counts (`add 1 + update 20 + insert 1 + VERSION 1`)
plus the stale `.pyc` it purged. Check the three patched base files against the Wave-12 folder
prefixes in `$w12run\5-reseal.txt` (12 hex characters, not a full sha256): `jarvis_gate.py`
starts `B410327DAF9D`, `jarvis_hud.py` starts `B89ED744A7FB`, `jarvis_skills.py` starts
`6C518CE49FEA`. `requirements.lock` and `quiz_grader_cases.json` are **not** journalled and need
no check: the apply reports `BESIDE: unchanged` for both, so they never moved this wave. Do not
compare anything from memory.

**If `backup-folder-tool.txt` or the journal folder is missing, do NOT hand-copy files out
of the insurance copy — stop and report: the live folder's state is then unknown.** A
`REFUSED` line or **exit 2** means the journal belongs to a different folder — stop. **Exit 1**
with `ROLLBACK INCOMPLETE` is the other case: N paths need attention and the backup is still at
that folder — record the N names, and do not start step 3 as though it were the same thing.
Step 1 restores the journalled paths only; step 3 restores the whole folder.

## 2. Restore the installer's record if the reseal wrote it

The reseal tool writes its own copy **inside the live folder**
(`_jarvis-state.json.before-reseal-<stamp>`), and Gate `reseal` also copies it into the run
folder:

```powershell
Copy-Item "$run\_jarvis-state.json.before-reseal" (Join-Path $live '_jarvis-state.json') -Force
"manifestBack=" + (Test-Path (Join-Path $live '_jarvis-state.json'))
```

(`$run\_jarvis-state.json.before-reseal` exists only after the `reseal` gate ran.)

## 3. Deep fallback: restore the whole insurance copy

Use this only if the tool journal path above is unusable (e.g. a file outside the tool's
journal was changed). Gate `insurance` makes `D:\jarvis-rehearsal\predeploy-wave13-<stamp>` —
take the exact path from the `backup=` line of `$run\1-insurance.txt`, never a typed stamp.

**There is no whole-folder Wave-12 insurance copy on this PC.** The newest copies in
`D:\jarvis-rehearsal` read `program\VERSION` **0.2.441**, **0.2.440** and **0.2.439**, and the
newest of the three is named `predeploy-wave11-20261109-092219` — Wave 12 reused the wave-11
name for its own insurance copy. The owner TOML sha256 `9C6CDF76…C92D97` is **identical from
Wave 9 through the live folder**, so it cannot identify a wave. **`program\VERSION = 0.2.442` is
the only proof that a copy is the Wave-12 one** — check it before restoring anything.

```powershell
$bak  = 'D:\jarvis-rehearsal\predeploy-wave13-<stamp>'   # exact path: backup= in $run\1-insurance.txt
$ver  = (Get-Content (Join-Path $bak 'program\VERSION') -Raw).Trim()
"bakVERSION=$ver"                        # MUST be 0.2.442 - STOP on anything else
if ($ver -ne '0.2.442') { "STOP: this is not the Wave-12 pre-deploy copy - do not robocopy" } else {
  # 3a. the backend folder back (overwrite in place, restore deleted files)
  robocopy "$bak\program" $live /E /NFL /NDL /NJH /NJS /NP | Out-Null
  "programCopyExit=$LASTEXITCODE"        # robocopy 0-7 = success; >=8 is a STOP
}

# 3b. remove the two files wave 13 ADDS (the copy predates them); both are also in the
# wave-13 journal as created paths, so step 1 already removes them
Remove-Item (Join-Path $live 'jarvis_creator.py') -ErrorAction SilentlyContinue
Remove-Item (Join-Path $live 'jarvis_plugins\creator-mode') -Recurse -Force -ErrorAction SilentlyContinue
# clear stale bytecode on purpose (it is NOT a wave-13 addition - it exists before and
# inside the copy); this forces a clean recompile after the restore
Remove-Item (Join-Path $live '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
```

Then re-check the files and the marker:

```powershell
"VERSION=$((Get-Content (Join-Path $live 'VERSION') -Raw).Trim())"
foreach ($f in 'jarvis_gate.py','jarvis_hud.py','jarvis_skills.py','jarvis-framework.toml','requirements.lock','quiz_grader_cases.json') {
  $p = Join-Path $live $f
  "$f bytes=$((Get-Item $p).Length) sha256=$((Get-FileHash $p -Algorithm SHA256).Hash)"
}
```

**GO:** `VERSION=0.2.442` — **that, not the TOML hash, is the proof this is the Wave-12 copy**.
The owner TOML also reads `58,409 B / 9C6CDF76…C92D97`, but that value is identical in the
Wave-9, Wave-11 and Wave-12 copies, so it says nothing about which wave you restored. **The
owner's TOML is never overwritten blindly** — if the restore changed it, put the owner's bytes
back from the copy you just proved is Wave-12. A changed hash after that means the owner edited
his own TOML: record it, never revert it.

**The data folder is NOT restored.** `C:\Users\pcadmin\.openjarvis` is snapshotted by Gate
`insurance` into `<bak>\data` only as insurance against a catastrophic mistake, never as a
rollback step. **17 files there have changed since the 09:22 snapshot** — `chat-history.db`,
`memory.db`, `receipts.db`, `approvals.db` and `schedule.db` among them — so restoring that copy
would throw away everything the owner said and did after it. Only the backend files are
restored. After a rollback the wave-13 code's only new data file, `memory-fault.json`, is
ignored by the wave-12 code: leave it or delete that one file.

## 4. Put the previous desktop back (only if Gate `install-desktop` ran)

Previous, verified build — the **Wave-12** `0.2.442` installer, measured in this repo:

- path: `$w12\jarvis-desktop_0.2.442_x64-setup.exe`
- bytes **5,753,269**; sha256 **`EEB2A5B8FA409D74EDEC4CE570470EE8A95A348066023095C07E372112AA3393`**;
  `FileVersion 0.2.442`.

If `$w12` has been cleaned away, the byte-identical copy made tonight is
`D:\jarvis-cache\wave12-rollback-2026-11-09\jarvis-desktop_0.2.442_x64-setup.exe` — same bytes,
same sha256 (see **Durable copies** at the end).

```powershell
$old = "$w12\jarvis-desktop_0.2.442_x64-setup.exe"
"bytes=$((Get-Item $old).Length) sha=$((Get-FileHash $old -Algorithm SHA256).Hash) ver=$((Get-Item $old).VersionInfo.FileVersion)"
# run the verified bytes from D: (the Wave-11 lesson: launching the setup from the
# repository path can hang), exactly as the packet's install-desktop gate does
$launch = 'D:\jarvis-install-test\rollback-setup-0.2.442.exe'
New-Item -ItemType Directory -Force -Path 'D:\jarvis-install-test' | Out-Null
Copy-Item $old $launch -Force
$p = Start-Process -FilePath $launch -ArgumentList '/S' -PassThru
"exitedIn180s=$($p.WaitForExit(180000)) exitCode=$($p.ExitCode)"
Start-Sleep -Seconds 5
"after=$((Get-Item 'C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe').VersionInfo.FileVersion)"
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis Desktop' | Select-Object DisplayVersion
```

**GO:** sha256 and bytes match the two values above, `after=0.2.442`, HKCU
`DisplayVersion=0.2.442`. **STOP if the hash differs** — do not install an unverified file.

## 5. Put the previous phone APK back (only if Gate `install-phone` ran)

Previous verified APK — the **Wave-12** build (`d6df402`):

- path: `$w12\jarvis-client-d6df402.apk`
- bytes **35,077,350**; sha256 **`96B02E8500E5337C5BE240AD9ED38E8CC22E12062AE8C5AB75FE20B5A8CD6465`**;
  `versionName 0.2.4035`, `versionCode 1000004035`.

If `$w12` has been cleaned away, the byte-identical copy made tonight is
`D:\jarvis-cache\wave12-rollback-2026-11-09\jarvis-client-d6df402.apk` — same bytes, same
sha256.

```powershell
$old = "$w12\jarvis-client-d6df402.apk"
"bytes=$((Get-Item $old).Length) sha=$((Get-FileHash $old -Algorithm SHA256).Hash)"
$adb = 'C:\Users\pcadmin\AppData\Local\Android\Sdk\platform-tools\adb.exe'
& $adb install -r $old
& $adb shell dumpsys package com.jarvis.client | Select-String -Pattern 'versionName|versionCode'
```

**GO:** `Success`, `versionName=0.2.4035`, `versionCode=1000004035`. **STOP if the hash
differs** — do not install an unverified file. Do not uninstall or re-pair the phone.

## 5b. Bring Jarvis back up — after step 4, never between steps 1 and 4

Steps 0–5 leave Jarvis stopped. Bring it back with the packet's own restart gate, which
**proves** a new listener pid and an `HTTP 403` instead of claiming them:

```powershell
pwsh -NoProfile -File 'C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\WAVE13-DEPLOY-2026-11-09\deploy-gates-wave13.ps1' -Gate restart
```

**GO:** `GO: NEW pid(s) ... listening on 127.0.0.1:4719 AND the tailnet address; HTTP 403.` — a
pid that was not listening before the restart, both listeners, and **HTTP 403** on `:4719`. Any
`STOP:` line is a STOP.

Run this **after step 4** (and after step 5 if it ran) and **never between steps 1 and 4**:
starting the backend while the new desktop is still installed would run the restored `0.2.442`
backend behind the Wave-13 desktop build.

## 6. Record it

Write what was restored, the VERSION/hash checks, and every command output into
`WAVE13-RESULT-2026-11-09.md` in the run folder — a rollback that is not recorded is an
unexplained live change.

**Re-read the live state before touching any lane or preset.** The baseline in
`pre-deploy-baseline.json` was captured at 12:25 and is already out of date: the owner changed
`presets-choice.json` from `general_uncensored` to `general` at 14:39:51, and lane 11436 now
holds `qwen3.5:9b` (context 196,608) instead of the Huihui GGUF tag in the snapshot. Lane 11435
(`qwen3:8b`, context 16,384) and 11450 (empty) still match. So read first:

```powershell
$data = 'C:\Users\pcadmin\.openjarvis'
foreach ($lane in 11436,11435,11450) {
  "== lane $lane"
  Invoke-RestMethod "http://127.0.0.1:$lane/api/ps" | ConvertTo-Json -Depth 6
}
foreach ($f in 'presets-choice.json','presets-active-lane.json') {
  $p = Join-Path $data $f
  "$f bytes=$((Get-Item $p).Length) sha256=$((Get-FileHash $p -Algorithm SHA256).Hash)"
}
```

**Ask the owner before restoring any preset or lane state.** The move to `general` was his own
edit, and 11436 may be a model he loaded himself: record it, never revert it silently. Restore
only what the deploy itself moved, and only after he says so.

## Durable copies (2026-11-09)

`.dsh-scratch` is gitignored, so `git clean -fdx` or a scratch tidy can delete the two rollback
assets steps 4 and 5 use. Tonight they were copied out of the repository, byte for byte, into
`D:\jarvis-cache\wave12-rollback-2026-11-09\`:

- `jarvis-desktop_0.2.442_x64-setup.exe` — **5,753,269 B**, sha256
  **`EEB2A5B8FA409D74EDEC4CE570470EE8A95A348066023095C07E372112AA3393`**
- `jarvis-client-d6df402.apk` — **35,077,350 B**, sha256
  **`96B02E8500E5337C5BE240AD9ED38E8CC22E12062AE8C5AB75FE20B5A8CD6465`**
- `jarvis-desktop_0.2.442_x64-setup.exe.sig` — 452 B
- `latest.json` — 4,159 B
- `MANIFEST.txt` — 406 B, the four files above with their bytes and sha256

Desktop **0.2.442**, phone **0.2.4035** (`versionCode 1000004035`) — the same Wave-12 build the
steps above restore. Check either asset against its sha256 above before using it:

```powershell
Get-ChildItem 'D:\jarvis-cache\wave12-rollback-2026-11-09' -File |
  ForEach-Object { "$($_.Name) $($_.Length) $((Get-FileHash $_.FullName -Algorithm SHA256).Hash)" }
```
