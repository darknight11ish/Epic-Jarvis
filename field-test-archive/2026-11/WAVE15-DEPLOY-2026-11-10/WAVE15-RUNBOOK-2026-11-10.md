# Wave-15 real-run runbook (2026-11-10)

STATUS: PREPARED AFTER THE MERGE. The authority is `frozen-ref.txt` in this folder, then the gate
script's own printed lines. This is the wave-14 runbook re-derived for wave 15: same 26 gates, same
order, same shape. Where a number depends on the live PC it says **TO MEASURE** instead of guessing.

**FROZEN REF (read from `frozen-ref.txt`, re-verified in git at 10:20 PT):**

- `frozenHead = fd9cb5762c021a4b16508a7c0c75c7073db17fa4` — the merge commit of PR #1221,
  merged 2026-11-10 10:08:15 PT. `origin/main` is this commit; `git rev-parse origin/main^{tree}`
  prints `be33366702d062459e0df2d97b11a837e4ee215f`.
- `frozenTree = be33366702d062459e0df2d97b11a837e4ee215f`, and the PR head
  `d66a0a4cf818966a127721049d8698cc628da401` has the **same** tree. That equality is what gate 0D
  now codifies (see §1).
- Base before the merge: `455765eb5d406d5c5d531c23b75bd952c30b5b35` (the #1220 merge).
- PR #1221, previous wave PR #1220. Floors: desktop **0.2.444**, phone **4047**.
- The deploy worktree `wt` was checked at 10:20 PT: HEAD `fd9cb576`, tree `be333667`, clean.

**0H was measured at 10:20 PT** by a read-only dry run at the frozen merge commit, and the receipt is
in this folder: `0H-preview-wave15.txt` (copy in the run folder as `0H-dryrun.txt`). It printed
`SHIPPED (335 files)`: **add 0 + update 7 + unchanged 328**; `HUD DELTAS (234 checked)`:
**234 already present + 0 to insert**; `READY PLUG-INS: 32 present, 0 to add, 26 already wired`;
`PYCACHE: 236`; `PLANNED CHANGES: 243 = add 0 + update 7 + insert 0 + beside+version 0 + pycache 236`;
`VERSION: unchanged 0.2.444`; 28 backup folders before and after the dry run.

The seven updates it named: `jarvis_recent_changes.py`, `jarvis_hud.html`, `hud-edit.js`,
`hud-presets.js`, `hud-layout.js`, `jarvis_vault_organizer.py`, `jarvis-self-code.json`.
`jarvis_vault_organizer.py` is the DEF-062 wording that arrived in #1220 and never reached the live
folder (live 118,536 B, tree 119,353 B). `jarvis_big_coder.py` is **already byte-identical** to the
tree (53,831 B, sha256 `96F52607…`), so it is `unchanged` and the apply will not rewrite it. Why the
count is live-driven: `plan_shipped()` in `tools/reconcile_live_backend.py` compares each shipped
file's **live bytes** with the ref's blob (`git show fd9cb576:tools/reconcile_live_backend.py`,
`def plan_shipped`). **PYCACHE is a live counter** — read whatever number 0H printed, never type 236.

## 0. Preconditions

- **PR #1221 is MERGED** (not open, not pending) as `fd9cb576`, and its merge tree equals the PR
  head's tree. This session does not merge, does not push, does not move the PR.
- Origin/main and its tree were re-read from git (commands in §1) and equal the values above.
  **STOP if either differs** — re-read `frozen-ref.txt` and stop; do not "fix" the packet.
- **Live state before the deploy (measured 10:20–10:30 PT, read-only):** backend + desktop
  **0.2.444**; phone **0.2.4047** (`versionCode 1000004047`, adb device `f0a5b32b`); **28**
  `_jarvis-deploy-backup-tool-*` folders (newest `_jarvis-deploy-backup-tool-20261109-213922`);
  two listeners on :4719 (127.0.0.1 and 100.75.21.228, pid 36612) and `/api/status` answers
  **HTTP 403** as required; owner TOML `58,409 B` / sha256
  `9C6CDF7644D67D8CBAF19B71DA574A3ED5DF95DDC09C6C2C2B565AC134C92D97`.
- **The run folder already exists.** `CURRENT-RUN.txt` points at
  `run-20261110-102051` (created 10:21 PT) and `gate-logs\` already held `0B`, `0C`, `0G`, `0H`,
  `insurance`, `repair` and `be` at 10:35 PT. **Read `CURRENT-RUN.txt`, never type a `<stamp>`, and
  never reuse the wave-14 run folder** `run-20261109-212243`.
- **The packet's scripts are owned by other lanes.** `deploy-gates-wave15.ps1` is the Lead's file;
  `post-deploy-checks-wave15.ps1` and `verify_wave15_live.py` are built by separate agents. This
  runbook **references** them and never creates or edits them. Their sizes, hashes and row counts
  are **TO MEASURE** and must never be quoted from this document.

## 1. Merge and releases — gate 0D is SAME-TREE-VERIFIED

The merge is already done (PR #1221 merged 2026-11-10 10:08:15 PT). Re-read the ref, then walk the
gate train:

```
git -C "...\Epic-Jarvis-main\.dsh-scratch\WAVE15-DEPLOY-2026-11-10\wt" fetch origin main
git -C "...\wt" rev-parse origin/main
git -C "...\wt" rev-parse "origin/main^{tree}"
```

Expected, from today: `fd9cb5762c021a4b16508a7c0c75c7073db17fa4` and
`be33366702d062459e0df2d97b11a837e4ee215f`. A different tree is a STOP.

**OWNER RULING Q4 (2026-11-10 00:05 PT): deploy first, then ONE combined owner-hands sweep on
0.2.445.** The duplicate main `CI` run on the merge sha is **logged, not awaited**. Gate 0D is
codified as **SAME-TREE-VERIFIED**, which means all four of these, and nothing else:

1. The merge commit's **tree** equals the PR head's **tree**. Verified today:
   `fd9cb576^{tree}` = `d66a0a4cf^{tree}` = `be33366702d062459e0df2d97b11a837e4ee215f`.
2. The PR head's **seven required checks were 7/7 green** on the PR run: `rust`, `frontend`,
   `backend`, `backend-windows`, `credential-manager`, `powershell-5`, `phone-unit-tests`
   (run `42796552404`; that run holds 14 CI jobs and the head has **17 check-runs**, all success).
3. The **post-merge `Desktop release` and `Jarvis client` workflows must succeed before 0E** —
   0E still requires BOTH releases to name the merge sha `fd9cb576`.
4. The background duplicate main `CI` run `42872103198` (run #4986, in progress at 10:16 PT) is
   **recorded once it finishes** in the run folder. It is **not awaited** and does not gate 0E.

**Releases, read from GitHub at 10:16–10:20 PT:**

- `Desktop release` run **#445** (`42872103330`, sha `fd9cb576`) **succeeded**, and `desktop-latest`
  now publishes **Jarvis Desktop - latest (0.2.445)**. Expected desktop after install: **0.2.445**.
- `Jarvis client` run **#4054** (`42872103259`, sha `fd9cb576`) was **still in progress**. The phone
  version is whatever the new `client-latest` says — **TO MEASURE at 0E, never hard-code it**. The
  floor is **0.2.4047** (what is installed); for context the previous `client-latest` was
  `0.2.4052 (main @ 455765e)`, so the new tag will be higher than 0.2.4052 in practice, but the
  gate's rule is the floor.
- The background main `CI` run is #4986 and was still running; log it, do not wait for it.

## 2. Gate train (wave-15 script)

One process per gate, in this order:

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".dsh-scratch\WAVE15-DEPLOY-2026-11-10\deploy-gates-wave15.ps1" -Gate <gate>
```

Console captured to `gate-logs\<gate>.log`. **The gate text is the verdict, not the exit code.**

| # | gate | expected (fill from 0H before the run) |
|---|---|---|
| 1 | 0B | GO: ref = merge sha `fd9cb576`; `origin/main` tree == frozen tree `be333667`; deploy tree checked out at the merge sha |
| 2 | 0C | GO: #1221 MERGED as `fd9cb576` and an ancestor of the ref; #1220 finished (MERGED as `455765eb5`) |
| 3 | 0D | **GO: SAME-TREE-VERIFIED** — merge tree == PR head tree (verified); PR head required checks 7/7 (run 42796552404); post-merge `Desktop release` **and** `Jarvis client` succeeded; duplicate main `CI` 42872103198 logged, **not awaited** |
| 4 | 0E | GO: BOTH releases name `fd9cb576`; desktop 0.2.445; phone new (> 0.2.4047 floor); writes `release-vars.json` |
| 5 | 0F | GO: setup FileVersion 0.2.445 + APK names the merge sha first 7 (`fd9cb57`); both sha256 match the API; neutral copy written |
| 6 | 0G | GO: HEAD = expect, trackedChanges = 0, gateRecordCall = True, toolBytes equal |
| 7 | 0H | GO: measured at 10:20 PT — SHIPPED 335 = 0 + 7 + 328; HUD 234 = 234 + 0; PLUG-INS 32/0/26; PYCACHE 236 (live); PLANNED 243; `dryRunExit=0`; VERSION unchanged 0.2.444; **backups 28 -> 28**. Re-run it after the merge and read the printed lines |
| 8 | insurance | GO: `D:\jarvis-rehearsal\predeploy-wave15-<stamp>` written, TOML hash equal, copy `program\VERSION` = 0.2.444 |
| 9 | repair | GO: six probes count=1, `probesBad=0` (pre-apply size/hash lineage) |
| 10 | be | GO: 2 listeners (loopback + tailnet), HTTP 403 |
| 11 | stop | the ONLY authorised stop; kills the tree |
| 12 | stopped | GO: LISTENING=0, no local ESTABLISHED, no HTTP |
| 13 | apply | GO: `wrote 8` (the gate predicts 8 = 7 updates + VERSION 1 — read the printed line), VERSION -> **0.2.445**, `PLANNED CHANGES: 244` if pycache is still 236, backup folder **29**, `RESULT: FAIL (3 expected)` probe failures, no rollback |
| 14 | quotes | GO: quotes hashes equal, `probesBad=0` |
| 15 | reseal | GO: `VERIFY: 0 of 335`, `RESULT: PARTIAL` naming only the unprovable base files — **names TO MEASURE** (wave 14 named a subset of `jarvis_gate.py`, `jarvis_hud.py`, `jarvis_skills.py`, `jarvis_extract.py`, `jarvis_project_read.py`) |
| 16 | toml | GO: owner TOML untouched `58,409 B` / `9C6CDF76...C92D97` |
| 17 | install-desktop | GO: after = **0.2.445**, `exitedIn180s=True`, HKCU DisplayVersion **0.2.445** |
| 18 | install-phone | GO: one device, `Success`, versionName = the release's, versionCode = 1000000000 + run digits (**TO MEASURE**) |
| 19 | restart | GO: NEW listener pid, both listeners, HTTP 403 |
| 20 | identity | GO: PASS, `identityExit=0` |
| 21 | probes | wave-11 regression 24/24 PASS; **wave-14 verifier read row by row as regression** (its own SUMMARY is TO MEASURE); **wave-15 verifier is acceptance** (TO MEASURE; pass mark is 0 FAIL, BLOCKED is never a pass) |
| 22 | preflight | record rows: compare **ROW NAMES**, never a total; the wave-14 measured set is in its run folder — TO MEASURE this wave |
| 23 | awareness | record rows: TO MEASURE; version rows must read the new versions (0.2.445 / the new phone) |
| 24 | postdeploy | wave-15 post-deploy checks: **TO MEASURE from the script's own SUMMARY**; expected **0 FAIL**; WARN by design A-SIZES (and F5-1 if the template keeps it). DEF-062/063/064 and the HUD rows should flip to PASS |
| 25 | verify-wave8 | 26/1 with only `self-update-history` (TO MEASURE); version rows read the new versions |
| 26 | rollback | print only; anchor = the **new** `_jarvis-deploy-backup-tool-*` folder (the 29th) that the apply printed |

### 2.1 Expected printed values

**Values that are already known (measured off the live PC, the frozen tree and the 0H receipt):**

- 0H: `SHIPPED (335 files)`: add 0 + update 7 + unchanged 328; `HUD DELTAS (234 checked)`:
  234 already + 0 to insert; `READY PLUG-INS: 32 present, 0 to add, 26 already wired`;
  `PYCACHE: 236`; `PLANNED CHANGES: 243`; `VERSION: unchanged 0.2.444`; backups 28 -> 28.
- `VERSION: wrote 0.2.445 (was 0.2.444, from the installed desktop)` at apply.
- `backupFolders=28->28` at 0H; the apply's `BACKUP:` line creates the **29th** folder.
- Desktop after install: **0.2.445** (`desktop-latest` already says so; `Desktop release` #445).
- Phone: the new `client-latest` tag, **> 0.2.4047** floor — read it at 0E.
- Owner TOML unchanged: `58,409 B` / `9C6CDF76...C92D97`.
- **Q3 cap already live and already in the tree** — `jarvis_big_coder.py` 53,831 B / sha256
  `96F52607…`, and the two lane engines printed `prompt cache is enabled, size limit: 3072 MiB`
  (`main.log` for 11436, `coding.log` for 11435). See §4: this wave does **not** edit or restart
  anything for Q3.

**TO MEASURE (read the gate's own line, never type these):**

- apply: `wrote N` (the gate predicts 8; read the printed line), `PLANNED CHANGES: N`, the backup
  folder name, the three expected probe failures + `SKIP app-control`.
- reseal: `VERIFY : 0 of N`, `RESULT: PARTIAL`, and the PARTIAL names (allowed set of unprovable
  base files: `jarvis_gate.py, jarvis_hud.py, jarvis_skills.py, jarvis_extract.py,
  jarvis_project_read.py` — but read what it prints).
- postdeploy: the printed SUMMARY and row count (the script in this folder lists 29 row ids in its
  own header; the run's SUMMARY is the authority).
- probes: the wave-14 verifier's and the wave-15 verifier's SUMMARYs (the gate carries the wave-14
  measured shape as the regression expectation: 12 PASS / 0 FAIL / 3 BLOCKED / 1 PARTIAL, exit 1).
- preflight / awareness / verify-wave8: totals and row sets.
- install-phone: versionName and `versionCode` (the wave-14 shape was 1000000000 + run digits).
- The verifier's path and size — **TO MEASURE**, because another lane owns that file.

## 3. Owner rows — ONE combined sweep on 0.2.445 (owner ruling Q4)

Run the sweep **after** the gate train, once, on the deployed 0.2.445. The gates already ran the
scripted checks (postdeploy + both verifiers); the sweep is only what needs a person at the screen.
Record every row as **PASS / FAIL / NOT-RUN / BLOCKED with evidence** — a row not reached is not a
pass.

What the sweep is for this wave (the user-visible content of the 46-file diff; all of it needs eyes
on the real window, because no script can prove what the installed window draws):

1. **HUD return pill and the one navigation** — open Face Only / Mini View in the real HUD and come
   back with the pill; confirm there is exactly one way back. (The stage got taller: the HUD test's
   own stage window moved 24,000 -> 40,000 characters in
   `jarvis-desktop/tests/hud-live-read-aloud.mjs` — a test-window fix, not behaviour.)
2. **Presets note (DEF-063)** — the note now names BOTH heavy rows and reads "Coding and Medical
   (they pause both other models first) and Cloud (it changes where your words go) still ask for
   the PC's ONE approval card."; the click's announce says "It pauses both other models first".
3. **Memory door line (DEF-064)** — the fixed line reads "Keep a plain new fact here; anything else
   is decided in the Memory tab in the Brain window." and the Keep button on the same plate still
   works for a plain new fact.
4. **Vault switch wording (DEF-062, delivered by this deploy from #1220)** — switching the
   organizer on raises exactly ONE card and the Settings line says "Waiting for your approval. The
   vault organizer is still OFF; …", never that it is ON.
5. **Desktop brain / settings styles** — the Brain window and Settings look and behave as before
   the CSS/JS change (`brain.css`, `brain.js`, `settings.css`, `settings.js`).

**The exact owner-row list is the Lead's call** and is written in the result receipt; this section
names what the wave changed, not a scripted list. Anything the gates already prove (versions,
hashes, listeners, HTTP 403) does not need the owner to re-do it.

## 4. Owner ruling Q3 — the 3 GB prompt-cache cap is ALREADY live; check it STAYS

This wave is different from wave 14: the cap is no longer a live-only edit. It is in the repo and
in the live files, and the apply will not touch it.

- `…\Desktop program\jarvis_big_coder.py`: **53,831 B**, sha256
  `96F526077BF42A2C0EBA64C00A0F36B4A577106FB110E5FA112276DEEA80B547`, and `git hash-object
  --no-filters` on the live file prints the frozen tree's blob `39159f6bc1a3e6cbae8b1ed135d16a41a6aad4fe`
  — **byte-identical to `fd9cb576:backend/jarvis_big_coder.py`**. The line is
  `env["LLAMA_ARG_CACHE_RAM"] = "3072"` in `_child_env()`.
- `C:\Users\pcadmin\AppData\Local\JarvisOllama\start-lane.ps1` (live-only, not in git): 4,854 B,
  sha256 `2D3C761CD6490895052F83D20A41B0793AF38241746C6C4DFF38C86BF9A22E94`, cap line at line 89.
- Proof the engines actually accepted it: `srv load_model: prompt cache is enabled, size limit:
  3072 MiB` appears in `…\JarvisOllama\logs\main.log` (11436) and `coding.log` (11435).

**So the Q3 check this wave is a read, not an edit:**

```
"big_coder bytes=" + (Get-Item $live\jarvis_big_coder.py).Length
"big_coder sha256=" + (Get-FileHash $live\jarvis_big_coder.py -Algorithm SHA256).Hash
"start-lane sha256=" + (Get-FileHash "$env:LOCALAPPDATA\JarvisOllama\start-lane.ps1" -Algorithm SHA256).Hash
```

GO: `big_coder bytes=53831`, `big_coder sha256=96F52607…`, `start-lane sha256=2D3C761C…`. The
post-deploy checks' `Q3-CAP` row is expected **PASS both before and after** the deploy (it is the
one new row that does not flip). **No edit, no lane restart, no second app restart is needed for
Q3.** If `Q3-CAP` reads FAIL after the deploy, that is a STOP to diagnose — do not quietly re-apply
the two edits.

Honest limit: the 11450 lane's own engine line (the app's child env) appears only when that lane
next loads a model, so it is not in today's logs; 11450's file-level proof is the byte-identical
module above. Do not claim the 11450 engine line until a load prints it.

## 5. Records

- Result/receipt: the Lead names it (the wave-14 shape was
  `D:\jarvis-scratch\OFFPEAK-CONTINUATION-2026-11-09\WAVE14-DEPLOY-RESULT-2026-11-10.md`). It must
  carry the gate table, the measured values, the owner-sweep rows and the Q3 read-back.
- Packet: this folder (`frozen-ref.txt`, `deploy-gates-wave15.ps1`, `post-deploy-checks-wave15.ps1`,
  the two verifier paths the gate records, `GATE-DIFF-NOTES.md`, `POSTDEPLOY-EXPECT-WAVE15.md`,
  `WAVE15-RUNBOOK-2026-11-10.md`, `ROLLBACK-WAVE15.md`, `PACKET-INTEGRATION-2026-11-10.md`,
  `FACT-SOURCES-WAVE15.md`, `gate-logs\`, the run folder named by `CURRENT-RUN.txt`).
- Verifier: `verify_wave15_live.py` — path chosen by its owning lane (**TO MEASURE**); the probes
  gate stops if its `EXPECTED_SHA` is not this run's frozen head.
- Rollback: `ROLLBACK-WAVE15.md` in this folder. Anchor = the 29th
  `_jarvis-deploy-backup-tool-*` folder that the apply prints. Do not touch the owner's TOML; never
  hand-edit a live file.

## 6. What this runbook is not

It is not the gate script and it does not replace its text. If the gate prints a number this file
does not predict, **the gate is right and this file is incomplete** — record the printed value and
say so in the receipt. Every "TO MEASURE" above exists for that reason: those numbers belong to the
live PC at run time, not to this document.
