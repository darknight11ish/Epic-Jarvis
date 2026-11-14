# ROLLBACK-WAVE17.md — exact, ordered rollback from the 0.2.448 deploy (wave 17) to desktop 0.2.446 / phone 0.2.4059

**Why this filename.** The deploy packet addresses this document by its basename, and Lead
decision Q3 re-issues it as `ROLLBACK-WAVE17.md`, so that is the name it ships under. The **content** is wave 17:
the rollback target pair is **0.2.446 / 0.2.4059**, and the deploy being undone is the 0.2.448
build (desktop target read at 0E; see §4). `0.2.447` was the pre-merge arithmetic — PR **#1225**
consumes Desktop release run 447, so the union merge is expected to publish **0.2.448**, and gate
**0E** is the only authority for the value.

Written by the **independent verifier lane**, 2026-11-11, re-taken from the frozen wave-16 file
(18,584 B). It is not the deploy session's own note, so it is not grading itself. Every path below
was checked to exist on this PC (or is marked as created by the deploy). Every hash was recomputed
from a real file or a real tree on 2026-11-11 — the base rows from `1087d81c1`, the live values
from the live folder, the gate values from the live gate plus the union tree at provisional head
`213d35f92` — and every value that depends on the freeze is written as `<FROZEN_…>` and re-derived
from the command beside it, never guessed.

**Value-status key.**

| tag | meaning |
|---|---|
| `LIVE` | measured on the live folder, read-only, 2026-11-11 02:25 PT |
| `BASE` | measured at `1087d81c1` (the 0.2.446 merge — what a correct rollback restores) |
| `P @213d35f92` | **PROVISIONAL** — measured at the union head, re-derive at the frozen head |
| `FREEZE_PENDING` | only knowable at freeze / from this deploy's own evidence; `<FROZEN_…>` |

**Names.** The wave-17 packet renames two of the acceptance files (`verify_wave17_live.py`,
`post-deploy-checks-wave17.ps1`). This document calls them **the verifier** and **the post-deploy
sheet**, so it stays correct whichever basenames the packet ends up with.

**Read this first, in one sentence:** the wave-17 deploy changes **16 files plus VERSION** — 15
rewritten and **1 added** (`jarvis_review.py`) — and **one file that `apply` never touches**: the
live `jarvis_gate.py`, repaired by gate 4A. So a rollback has **four live-folder moves** — the tool
journal (which restores the 15 **and deletes the 1 new file**), the named 4A gate backup, the one
journaled gate `.pyc` (§3b), and `_jarvis-state.json` (§3c) — **then** the desktop and phone
reinstall. Nothing else in the live folder may be restored, and no base folder may be copied over
it.

---

## 0. When to roll back — and when NOT to

Roll back when one of these is true **after** the install and restart:

- the post-deploy sheet reports a **REQUIRED FAIL** that is about the deploy's own bytes
  (1-VERSION, 2-PAYLOAD, 2B-SHIPPED, 3-HUD, 4-GATE4A, 5-COCKPIT, 6-SWITCH, 7-GHTOOLS,
  13-BACKUPS).
- the verifier exits 1 with a **FAIL** on a required row.
- the desktop will not start, or the HUD shows no window, or `/api/version` answers
  403-then-nothing after a new process was proven.
- an approval card was raised by the deploy itself (nothing in the run-book should raise one).

**Do NOT roll back for:**

- A `BLOCKED`, `PARTIAL` or `NOT-TAKEN` row that is only missing evidence (no `--apk`, no worktree,
  no `-RunDir`). That is an **incomplete acceptance, not a broken install**: record it, do not undo
  a working deploy. **None of those three ever reads as a pass** — and none of them is a reason to
  destroy a coherent folder.
- The lanes' design-time `FAIL`s: the three by-design probe failures and the `SKIP app-control`
  that wave 15 also had.
- A cold second card (`11450` has no listener). That is `cold`, never a FAIL.
- The owner's own TOML edit (a different `jarvis-framework.toml` hash). Record it; never revert
  the owner's settings. Today's live hash is `209AC2FE…` (see §6.3), not the frozen `9C6CDF76…`.

---

## 1. STOP first — the files must not be in use

```powershell
taskkill /IM jarvis-desktop.exe /T /F; foreach($x in @(netstat -ano | findstr ":4719" | findstr LISTENING | ForEach-Object { [int](($_ -split '\s+')[-1]) } | Sort-Object -Unique)){ taskkill /PID $x /T /F }; Start-Sleep -Seconds 5; netstat -ano | findstr ":4719" | findstr LISTENING
```

**PASS** = no `LISTENING` row for `:4719`. One "process not found" is harmless.
**STOP** if a listener remains: `--rollback` refuses while the server holds the files, and a copy
over a running Python process is a half-rollback.

The tool paths this needs:

| what | path |
|---|---|
| the live backend folder | `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program` |
| the deploy worktree (a read-only checkout of the merge) | `D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\wt` — read it from the packet, never type it (0B creates it) |
| this deploy's run folder | `<run>` — the path in `<PACKET-ROOT>\CURRENT-RUN.txt` (`FREEZE_PENDING`) |
| the deploy packet | `D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11` |

> **Do not type the worktree path from this document.** The wave-16 document typed one, and a
> rollback run against a stale path would restore the wrong tree's bytes. Read `ref.txt` and
> `CURRENT-RUN.txt` in the live packet.

---

## 2. Restore the 15 payload files + VERSION — and let the journal delete the 1 new file

**Source:** the newest `_jarvis-deploy-backup-tool-<stamp>` folder inside the live folder. The
**30** that exist today are **not** this deploy's; the deploy creates the **31st**, and that one is
the source. `apply` prints its path on the `BACKUP:` line and records it in `<run>\4-apply.txt`.

```powershell
$live='C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program'; $run=(Get-Content '<PACKET-ROOT>\CURRENT-RUN.txt' -Raw).Trim(); Set-Location 'D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\wt'; py -3 -B tools\reconcile_live_backend.py --backend-path "$live" --rollback "<live>\_jarvis-deploy-backup-tool-<stamp>"
```

**PASS = two printed lines, both required** (the numbers are this run's; `247` is the example at
pycache 231 — see the relation below):

```
ROLLBACK: restored 247 overwritten path(s), removed 1 new path(s)
ROLLBACK OK - the live folder is back to its pre-deploy state; journal at <live>\_jarvis-deploy-backup-tool-<stamp>\_journal.json
```

(That is the exact text of `rollback_backup()` in `tools/reconcile_live_backend.py` at
`213d35f92`: the `ROLLBACK:` line at its line 2670, the `ROLLBACK OK -` line at 2677–2678. Note
the hyphen, not an em dash — grade the string that prints.)

**`removed M` must be 1.** Exactly one path this wave writes did not exist before the deploy —
`jarvis_review.py` — and the journal records it as `existed: false`, which `_restore_entries()`
unlinks and counts (that function, lines 2601–2643; `Backup.record_new()` writes the entry, and
`apply_shipped()` calls it for every target that is not there yet). **M = 0 means the journal has
no `existed: false` entry — with live today not holding `jarvis_review.py`, that is a wrong or
half-applied journal; M > 1 means something else was created. Both are STOPs, and §7 proves the
absence independently.**

**`restored N` is not pinned to a document.** It is the count of journalled **overwritten** paths:
the 15 payload files + `VERSION` + every `.pyc` that `apply` purged. So it equals `apply`'s own
`PLANNED CHANGES` total **minus the 1 added file** — 247 at pycache 231, 248 at 232 — and the
check that needs no arithmetic is `restored + removed == PLANNED`. (Wave 16's run read
`PLANNED 260` and would have printed `restored 260, removed 0`.)

**What the journal contains, and why it is enough.** `apply` writes only what the 0H delta
planned: the 16 payload rows, and `VERSION` when the new setup's FileVersion differs (it sets
`JARVIS_DESKTOP_EXE` to the new setup, so it writes the new version even though `install-desktop`
runs later). It journals each one before the write (`apply_shipped()` → `Backup.save()`;
`apply_release_files()` → `Backup.save()`), and it journals every `.pyc` before purging it
(`purge_pycache()` → `Backup.save()`). The **320 unchanged files were never written**, so there is
**nothing to restore** for them; a restore of those would be a no-op at best and a wave-mixing copy
at worst.

**What it does NOT contain: `jarvis_gate.py`.** It is not a `$SHIPPED` file and `apply` never
writes it — gate 4A is its only writer — so no tool journal can hold it. That is a fact about the
code path, not a measurement: the only writes `apply` journals are shipped rows, release markers,
purged bytecode and new plug-in directories. Step 3 restores the gate.

**Never point `--rollback` at the 30 older tool backups.** They are changed-file sets from earlier
waves, the newest `VERSION` inside any of them is now **0.2.445** (wave-16's journal,
`_jarvis-deploy-backup-tool-20261110-213807` — measured 2026-11-11; ten of the thirty carry a
`VERSION` file, and the newest of those ten is 0.2.445), and none of them holds the current
**0.2.446** state. Restoring one mixes waves. **Wave-16's journal is still not this deploy's**:
it restores 0.2.445's bytes, not 0.2.446's.

---

## 3. Restore `jarvis_gate.py` — from THIS deploy's gatepatch backup

**Source:** the `_jarvis-deploy-backup-gatepatch-<yyyyMMdd-HHmmss>` folder gate 4A created and
**printed**. Use that printed path; never a glob, never "newest by name".

Gate 4A's backup holds the pre-repair gate exactly:

- `jarvis_gate.py` **223,701 B** /
  `A75B15C9D53ED58AE24824E1E05EEBF8CDD4750AEC0F5D567C0754EB5398DD17` — `LIVE` (wave-16's
  after-image, which is this wave's **before**), and the value a correct rollback must land on.

```powershell
$live='C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program'; Copy-Item -LiteralPath "<live>\_jarvis-deploy-backup-gatepatch-<stamp>\jarvis_gate.py" -Destination "$live\jarvis_gate.py" -Force; (Get-Item "$live\jarvis_gate.py").Length; (Get-FileHash "$live\jarvis_gate.py" -Algorithm SHA256).Hash; Remove-Item "$live\__pycache__\jarvis_gate*.pyc" -Force -ErrorAction SilentlyContinue
```

**EXPECT** `223701` and
`A75B15C9D53ED58AE24824E1E05EEBF8CDD4750AEC0F5D567C0754EB5398DD17`.

**Never use the three older gatepatch folders.** They exist, they are older gates, and restoring
any of them destroys live-only gate rows or reverts to the wrong release:

| folder | `jarvis_gate.py` inside | verdict |
|---|---|---|
| `_jarvis-deploy-backup-gatepatch-20261102-133335` | 184,951 B | **never** (2026-11-02 wave) |
| `_jarvis-deploy-backup-gatepatch-20261102-133341` | 190,304 B | **never** (2026-11-02 wave) |
| `_jarvis-deploy-backup-gatepatch-20261110-213818` | 220,771 B / `B410327D…` | **never** — this is the **0.2.445** gate (6 rows); it is wave-16's rollback source, not wave-17's |
| `_jarvis-deploy-backup-gatepatch-<stamp from THIS deploy's gate 4A>` | **223,701 B / `A75B15C9…`** | **this one** |

The `Remove-Item` is deliberate and safe: a `.pyc` compiled from the **`230,526`**
gate (was provisional 228,590 B at the provisional head) would otherwise keep running against **0.2.446** code.
Deleting zero files is expected (apply purges them) — a zero-match purge is not an error.

---

## 3b. Restore the ONE journaled gate bytecode file (step 7.3b)

§3's purge deletes `__pycache__\jarvis_gate*.pyc` that step 2's journal restored, so the rollback
stops being byte-identical to the pre-deploy folder. Restore that one file from THIS deploy's tool
journal (the `BACKUP:` path in `<run>\4-apply.txt`). The `ADDED / REMOVED / CHANGED` counts that
prove it are **measured in this run's evidence**, not pinned here: wave 16 read
`ADDED 255 / REMOVED 1 / CHANGED 1`, and this wave's differ because the payload set and the
pycache count changed (**231** `.pyc` today).

```powershell
$live='C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program'; $bak="<live>\_jarvis-deploy-backup-tool-<stamp>"; $src="$bak\__pycache__\jarvis_gate.cpython-312.pyc"; $dst="$live\__pycache__\jarvis_gate.cpython-312.pyc"; if(Test-Path -LiteralPath $src){ if(-not(Test-Path -LiteralPath "$live\__pycache__")){ New-Item -ItemType Directory -Path "$live\__pycache__" | Out-Null }; Copy-Item -LiteralPath $src -Destination $dst -Force; 'copied'; (Get-Item $dst).Length; (Get-FileHash $dst -Algorithm SHA256).Hash; (Get-FileHash $src -Algorithm SHA256).Hash } else { 'no journaled gate .pyc in ' + $bak + ' - dstAbsent=' + (-not (Test-Path -LiteralPath $dst)) }
```

**PASS** = last two hashes equal, OR journal has no such file and dst is absent too. **STOP** if
journal lacks it while live still has a `jarvis_gate*.pyc`, or if the copied hash differs.

## 3c. Restore `_jarvis-state.json` before the identity check (step 7.3c)

Reseal leaves the record resealed to the MERGE sha, so the **0.2.446** identity check takes the
runtime-tree branch and prints `CHANGED: <N> runtime file(s) differ ...`, exit 1. The count is
measured in the run (wave 16 read 28); do not carry it as a constant. Restore the pre-reseal record
saved by `-Gate reseal`:

```powershell
$live='C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program'; $run=(Get-Content '<PACKET-ROOT>\CURRENT-RUN.txt' -Raw).Trim(); $src="$run\_jarvis-state.json.before-reseal"; if(-not(Test-Path -LiteralPath $src)){ $src=(Get-ChildItem -LiteralPath $live -Filter '_jarvis-state.json.before-reseal-*' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName }; Copy-Item -LiteralPath $src -Destination "$live\_jarvis-state.json" -Force; (Get-Item "$live\_jarvis-state.json").Length; (Get-FileHash "$live\_jarvis-state.json" -Algorithm SHA256).Hash; (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
```

**PASS** = last two hashes equal; then §4's identity check prints
`PASS (runtime tree identical to deployed ref 1087d81)`, exit 0.

---

## 4. Put desktop 0.2.446 and phone 0.2.4059 back

### 4a. Desktop

**Source:** `D:\jarvis-install-test\setup-wave16.exe` — **5,788,167 B** /
`019CF3EBB5E6FC0400D5F28FDEF693440BCB993D884FF24B8ADE160E1B83983D`, FileVersion **0.2.446**.
Measured on this PC 2026-11-11 02:25 PT, and it matches the 0.2.446 receipt's GitHub asset digest
(`sha256:019cf3eb…`, 5,788,167 B) — so it is that asset, not a hand rebuild.

**This is not a `FREEZE_PENDING` value** — the 0.2.446 installer already exists. **Verify it again
before you run it** (`(Get-Item).VersionInfo.FileVersion` must read `0.2.446`; the size and hash
must match the line above). If it is absent or different, that is **BLOCKED**: do not substitute a
0.2.448 or 0.2.445 installer.

```powershell
Copy-Item 'D:\jarvis-install-test\setup-wave16.exe' 'D:\jarvis-install-test\setup-rollback.exe' -Force; $p=Start-Process 'D:\jarvis-install-test\setup-rollback.exe' -ArgumentList '/S' -PassThru; $p.WaitForExit(180000)
```

**PASS** = exit 0 within 180 s, and then:

```powershell
(Get-Content 'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\VERSION' -Raw).Trim(); (Get-Item 'C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe').VersionInfo.FileVersion; (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis Desktop').DisplayVersion
```

all three read **0.2.446**. `VERSION` comes from step 2 (the journal restores the file `apply`
overwrote); the installer sets the exe and the uninstall entry.

**STOP** if the installer refuses to go backwards (a newer MSI ProductCode can refuse a downgrade).
Do **not** hand-edit the registry and do not delete the program folder: stop and report it.

Then start the app and prove the identity tool agrees with 0.2.446:

```powershell
Start-Process 'C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe'; Start-Sleep -Seconds 20; py -3 -B tools\check_live_version_identity.py --main-ref 1087d81c11f59f35059032c54d84da81c18b02a1
```

**Before this check, 3c must have restored `<live>\_jarvis-state.json` from
`<run>\_jarvis-state.json.before-reseal`.** PASS = `PASS (runtime tree identical to deployed ref
1087d81)` and exit 0, run from `D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\wt`; without 3c it prints
`CHANGED: <N> runtime file(s) differ ...`, exit 1 — a missing step, not a failed rollback.

### 4b. Phone

The deploy sideloads the **next** build, whose number is read from `client-latest`'s title at 0E
(`FREEZE_PENDING`; today's is **0.2.4059** / versionCode **1000004059**). To roll back, reinstall
the **0.2.4059** APK — this exact file, kept from wave 16's run:

| file | bytes | sha256 |
|---|---:|---|
| `D:\jarvis-scratch\WAVE16-DEPLOY-2026-11-10\run-20261110-211514\artifacts\jarvis-client-1087d81.apk` | 35,085,526 | `B2EA1A57B088EB4706F7EA5C1D7E54FD0209C2186D47ABD822F2ED5494F441E0` |

```powershell
& 'C:\Users\pcadmin\AppData\Local\Android\Sdk\platform-tools\adb.exe' install -r -d 'D:\jarvis-scratch\WAVE16-DEPLOY-2026-11-10\run-20261110-211514\artifacts\jarvis-client-1087d81.apk'; & 'C:\Users\pcadmin\AppData\Local\Android\Sdk\platform-tools\adb.exe' shell dumpsys package com.jarvis.client | Select-String 'versionName=|versionCode='
```

(`-d` allows the version downgrade; without it adb can refuse with
`INSTALL_FAILED_VERSION_DOWNGRADE` because the deployed build's `versionCode` is higher.)

**PASS** = `Success` and `versionName=0.2.4059` / `versionCode=1000004059`. **STOP** if the APK is
missing or its hash differs — a phone left on the new build while the PC is back on 0.2.446 is a
**BLOCKED** rollback, not a pass. Never install a locally built or older-than-0.2.4059 APK to
"make it match".

---

## 5. Only if the live folder is damaged beyond the journal

**Source:** **this deploy's** full pre-deploy snapshot, taken by the `insurance` gate as
`D:\jarvis-rehearsal\predeploy-wave17-<stamp>` (`FREEZE_PENDING`: the path is printed by the gate).
Use its `INSURANCE-MANIFEST.json`.

```powershell
robocopy 'D:\jarvis-rehearsal\predeploy-wave17-<stamp>\program' 'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program' /E /NFL /NDL /NJH /NJS /NP
```

- Copy **`program`** only. **Do not copy `data` back**: the deploy never writes `data`, and
  restoring it would delete facts learned after the snapshot.
- This is the last resort, not step 2. It restores *every* program file, including the ones the
  owner may have changed on purpose outside this deploy.
- **Never restore a wave-16 insurance copy** (`predeploy-wave16-20261110-*`). Those hold the
  **0.2.445** pre-deploy state — restoring one would undo the 0.2.446 install as well, which is
  worse than the failure you are fixing. They are wave-16 evidence, not wave-17 insurance.

---

## 6. What must NOT be restored — the list that prevents a bigger outage

1. **Never copy a whole base over the live folder.** `jarvis-backend\*` is a published snapshot,
   not the live lineage: at `213d35f92` its `jarvis_gate.py` is **203,058 B** (`P @213d35f92`)
   against live's **223,701 B** — **23,309 B smaller**, and the two files are different lineages
   (each has rows the other lacks), so a copy silently deletes live-only gate rows. Copying it
   compiles fine, which is what makes it dangerous.
2. **Never restore `data\`** (see above). The insurance copy's data half is deliberately larger
   than live because robocopy de-references symlinks; a naive restore is wrong in both directions.
3. **Never restore `jarvis-framework.toml`** from a backup. Live is now **58,610 B /
   `209AC2FE46E636F4A115173A10C61E25305C1AE548642659EC5CDEB2F140705B`** (moved 2026-11-10
   22:39:22; **one key** changed, `tools.enabled` 14 → 24 with the ten GitHub tools). It is the
   owner's file: **record, never revert** — and the ten GitHub names must survive the deploy too.
4. **Never restore `__pycache__\` as a folder — ONE measured exception.** A `.pyc` compiled from
   the **`230,526`** gate must not keep running, so purge stale bytecode; but the
   journal restores the folder's files, §3 deletes `jarvis_gate*.pyc`, and 3b copies back exactly
   that one journaled `.pyc`, making the rollback byte-identical. Nothing else from `__pycache__\`
   is restored.
5. **Never use the 30 older tool backups or the 3 older gatepatch backups** as the rollback source
   (waves 1–16 changed-file sets; the newest `VERSION` among them is **0.2.445**, and the newest
   gatepatch among them holds the **0.2.445** gate). This deploy's journal is the 31st tool folder;
   its 4A backup is the 4th gatepatch folder.
6. **Never restore `rebuilt\` as a folder.** There is no `<live>\rebuilt\` — the `rebuilt/<name>`
   entries land as `<name>` beside `jarvis_hud.py`. **No row of §7 comes from `rebuilt/` this
   wave** (`jarvis_memory.py` left the payload set), so nothing lands from it at all.
7. **Do not reinstall 0.2.448 afterwards "to be safe".** A same-version hand rebuild gets a
   different MSI ProductCode; only CI's signed installer may be installed, and a second install is
   a second change to verify.

---

## 7. Verify the rollback (all read-only)

After steps 1–4, the **15 rewritten files** must be exactly `1087d81c1`'s bytes again, **and
`jarvis_review.py` must be absent**. This table was computed from `1087d81c1` (the 0.2.446 merge)
on 2026-11-11; every row was also confirmed against the **live** file before the deploy (15/15, 0
mismatches):

| live file | bytes | sha256 (`1087d81c1`) |
|---|---:|---|
| `jarvis_accounts.py` | 58,362 | `685E9B05EC0668E91E6C975FB40843618D860BE6806366FF7AA2B1426127C18E` |
| `jarvis_agent.py` | 998,311 | `47DFA2237BBB9915B33371075B6827FFFCAEA2E60D617C54912A64B167627D9F` |
| `jarvis_asks_first.py` | 171,600 | `7160DE19F71E652B8782E89DD0B0EA6ADE04BA252D6C06BDD27E042CABCC7498` |
| `jarvis_card_words.py` | 61,429 | `CEB8BEE98B0DF02F3A826E37FA248A6CE4B9089B605291286772FEC104E9A12C` |
| `jarvis_claims.py` | 32,917 | `FD2416A11A9DC5F748B6C30A7F461F4F9482E3D9612B34D32611CC3AD0630520` |
| `jarvis_feature_catalogue.py` | 166,033 | `E41C205DF1E1A32589CDE66B4457CC4E49E3106A602610A0EA8F86E56212D04F` |
| `jarvis_feature_guide.py` | 243,514 | `AA11FCE82CDF08CC0A8D5DCE4BDA38C1712B6EFDD603BC76CC020F6B74D8EF60` |
| `jarvis_github.py` | 140,954 | `70840FAFE03A8EC86251084DDCDDAFBD19948B0110641DE60674923E205BB35E` |
| `jarvis_owner_check.py` | 102,754 | `EA30FC44EAA94BCCA59D415A27910F0CB45C52EB73A57EB3C5ED8F55E93E1357` |
| `jarvis_quick.py` | 1,471,147 | `35802D7B66BB2E094DC528F67F81B68410566C6486D222512EF98C770E3496E1` |
| `jarvis_reach.py` | 85,001 | `11652BD0CD5B64F3A53EAD10451C963895874BA281E51D30F471418F2037A0A7` |
| `jarvis_recent_changes.py` | 2,931 | `2934164097E26482F6BF4DABB562D105A42546FC1F2594A5B0821B25B86880CB` |
| `jarvis_settings_registry.py` | 281,322 | `366E84F72B38C37D641971F86F7611D838B732BD4A463DC9AB2E0E4CC21A5697` |
| `jarvis_tool_profiles.py` | 157,556 | `504A6D44307781D8B657C9DE38A898317E17B347FE5AB70DA8CAE27CA5D16130` |
| `jarvis-self-code.json` | 316,623 | `7D96AA276961699BC4F2165F0A6E08779CBED63DC62DF6D3562AD51836817966` |

One line that prints all 15 comparison rows, **and the absence test for the added file**:

```powershell
$live='C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program'; foreach($n in @('jarvis_accounts.py','jarvis_agent.py','jarvis_asks_first.py','jarvis_card_words.py','jarvis_claims.py','jarvis_feature_catalogue.py','jarvis_feature_guide.py','jarvis_github.py','jarvis_owner_check.py','jarvis_quick.py','jarvis_reach.py','jarvis_recent_changes.py','jarvis_settings_registry.py','jarvis_tool_profiles.py','jarvis-self-code.json')){ $i=Get-Item "$live\$n"; "$n $($i.Length) $((Get-FileHash $i.FullName -Algorithm SHA256).Hash)" }; if (Test-Path -LiteralPath "$live\jarvis_review.py") { 'jarvis_review.py STILL PRESENT - rollback incomplete' } else { 'jarvis_review.py absent (correct)' }
```

**PASS** = 15 rows byte-exact **and** `jarvis_review.py absent (correct)`. `STILL PRESENT` is a
**FAIL**, not a warning: the deployed folder would then hold a module the 0.2.446 install never
had, and the identity check would report it.

Also check:

- `VERSION` = **0.2.446**; exe `FileVersion` = 0.2.446; uninstall `DisplayVersion` = 0.2.446.
- `jarvis_gate.py` = **223,701 B / `A75B15C9…`** and its `"github_…"` row count is **10** again
  (the 0.2.446 shape).
- `jarvis_hud.html` = **778,164 B / `84812A4F…`** — the 0.2.446 page. **This wave does not change
  the HUD**, so a rollback must leave it exactly here; **776,898 B / `095772B9…` is the 0.2.445
  page and MUST NOT appear** — expecting it would fail a correct rollback.
- `@(Get-ChildItem $live -Directory -Filter '_jarvis-deploy-backup-tool-*').Count` is **31** (the
  31st is this deploy's journal, kept), and `_jarvis-deploy-backup-gatepatch-*` is **4** (gate
  4A's is kept).
- phone `versionName` = **0.2.4059**, `versionCode` = **1000004059**.
- No `LISTENING` row on `:4719` until the app is started again on purpose.
- The gate `.pyc` matches the tool journal's copy (3b PASS — or absent on both sides).
- `_jarvis-state.json` hash equals `<run>\_jarvis-state.json.before-reseal` (3c).

---

## 8. Stop conditions — do not "finish" a rollback that hits one

- The server is still listening after step 1.
- `--rollback` prints `REFUSED`, a traceback, or "journal not found".
- `removed M` is **not 1**, or `jarvis_review.py` is still present after `--rollback`.
- The gate backup is not exactly **223,701 B / `A75B15C9…`**.
- `VERSION` is not back to **0.2.446** after step 4, or the phone still reads the new build.
- Any of the 15 hashes in §7 does not match.
- The installer refuses the downgrade, or the uninstall entry disappears.
- You are tempted to copy `jarvis-backend\*`, `data\`, the TOML or `__pycache__`
  "because it is quicker". Each of those is in §6 for a measured reason.
- You skipped 3b or 3c, or their sources are missing — not a complete rollback.

Record the failure and stop. A half-rolled-back live folder is worse than a deployed 0.2.448 with
a failing acceptance row, because the acceptance row can still be diagnosed while the folder is
coherent.

---

## 9. Evidence to keep

The run folder (`4-apply.txt`, **`4A-gatepatch.txt`**, `5-reseal.txt`), the
**`_jarvis-deploy-backup-gatepatch-<stamp>` path printed by gate 4A**, the `BACKUP:` line, the
installer and restart consoles, the **15-row hash table before and after plus the
`jarvis_review.py` absence proof**, `VERSION` before/after, the phone version before/after, the
listener pids, and the exact failing card text or error. Never paraphrase a hash.

If the rollback itself is being verified by somebody else, they need exactly: the two backup
paths, the 15-row before table (§7) **and the absence proof for `jarvis_review.py`**, and the
gate's before/after pair — that is enough to prove both directions without trusting this document.
