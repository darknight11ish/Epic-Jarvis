# WAVE-15 GATE DIFF NOTES — wave-14 packet -> wave-15 packet

Packet: `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\WAVE15-DEPLOY-2026-11-10\deploy-gates-wave15.ps1`

- New: **71,978 bytes, 1,103 lines, sha256 `8280412734FDFB4B50BB7AB7FCFC7270C3A7A79C299179000711054AA7BB4A1D`**, 34 `# W15:` markers.
- Base: the wave-14 packet, 74,012 bytes, 1,116 lines, sha256 `C98BA1BA69BAB67FE31189835DB1AC400C98AF3FBF93D508E2AEEFF562C19D9C`. The wave-14 ledger is kept verbatim below the wave-15 block as history (that is why the file is long; the W15 markers are the diff).
- PowerShell 5.1 parse: **PARSE OK, 0 errors, exit 0** for **both** wave-15 scripts, checked with `check-parse-wave15.ps1` under `powershell.exe 5.1.26100.9711` (it parses, executes nothing, writes nothing). Log: the checker's own output, `PARSE-CHECK-DONE bad=0`.
- Companions in the same folder (different owners): `post-deploy-checks-wave15.ps1` **67,246 B / 1,281 lines / sha256 `6611F50A803362A8AFB9F5EC8EC43E90B9CFA382CFEE0CDFBBEFAF3D3B70A9E6`**, 21 `# W15:` markers, **29 rows declared in its own header**; and `verify_wave15_live.py`, owned by a third lane (path/size **TO MEASURE** — it was not in the folder at 10:35 PT).

## 0. THE PIN — read this first

`frozen-ref.txt` in this folder is the authority. Re-read it at the start of the run and at the end.

| | value | how it was verified |
|---|---|---|
| PR / previous PR | **#1221** / **#1220** | `gh pr view 1221`, `gh pr view 1220` → both MERGED |
| frozen head | **`fd9cb5762c021a4b16508a7c0c75c7073db17fa4`** | `git rev-parse origin/main`; that commit is `Merge pull request #1221 …` |
| frozen tree | **`be33366702d062459e0df2d97b11a837e4ee215f`** | `git rev-parse origin/main^{tree}` |
| PR head | `d66a0a4cf818966a127721049d8698cc628da401`, tree **`be333667…`** | `git rev-parse d66a0a4cf^{tree}` — the **same tree**, which is what makes 0D's SAME-TREE-VERIFIED legal |
| base before the merge | `455765eb5d406d5c5d531c23b75bd952c30b5b35` | the #1220 merge |

For the first time in this family of packets **the frozen head is the merge commit itself** (wave 14
froze a PR head and the merge commit followed). There is no second head to chase: if
`origin/main` moves past `fd9cb576`, that is a STOP, not a re-pin.

## 1. Every changed constant / expectation (old -> new -> why)

| # | Where | Old (wave 14) | New (wave 15) | Why |
|---|---|---|---|---|
| 1 | header block | wave-14 title, PR #1219, head 24a3fc9 | wave-15 title, PR #1221, **merge commit** fd9cb576, the Q4 0D paragraph, the 0H numbers actually measured | the packet must name itself, its authority and its ruling |
| 2 | `$scratch` | `…\WAVE14-DEPLOY-2026-11-09` | `…\WAVE15-DEPLOY-2026-11-10` | run folder, `CURRENT-RUN.txt`, artifacts, gate logs |
| 3 | `$Pr` | 1219 | **1221** | wave-15 PR |
| 4 | `$PrevPr` | 1218 | **1220** | previous wave PR (MERGED as `455765eb5`; only an OPEN one stops 0C) |
| 5 | `$DesktopFloor` | `'0.2.443'` | **`'0.2.444'`** | the live desktop/backend is 0.2.444; the new build must be newer |
| 6 | `$PhoneFloor` | 4042 | **4047** | the installed phone is 0.2.4047 (`versionCode 1000004047`) |
| 7 | `$FrozenHead` | `24a3fc9b1…` | **`fd9cb5762c021a4b16508a7c0c75c7073db17fa4`** | the merge commit |
| 8 | `$FrozenTree` | `ad1de9e1…` | **`be33366702d062459e0df2d97b11a837e4ee215f`** | `git rev-parse fd9cb576^{tree}` |
| 9 | `$Ref` default | `24a3fc9…` | **`fd9cb576…`** | 0B may re-pin only to a main whose tree equals the frozen tree |
| 10 | `$PreflightDir` | `D:\jarvis-scratch\WAVE14-PREFLIGHT-2026-11-09` | **`D:\jarvis-scratch\WAVE15-VERIFIER-2026-11-10`** | the deliverable-candidate folder for this wave (the name is the Lead's choice; it is also where the wave-15 verifier is expected) |
| 11 | `$PostDeployScript` / `$PostDeployCandidates` | `post-deploy-checks-wave14.ps1` | **`post-deploy-checks-wave15.ps1`** (script folder, then `$PreflightDir`) | the wave-14 script pins the wave-14 tree and must not grade wave 15; **a missing script is BLOCKED, never a pass**, and the packet never creates it |
| 12 | `$AcceptanceScripts` | `verify_wave14_live.py` (4 candidates) | **`verify_wave15_live.py`** (script folder, `WAVE15-INTEGRATION-2026-11-10`, `$PreflightDir`, `D:\jarvis-scratch\WAVE15-VERIFIER-2026-11-10`) | this wave's acceptance half |
| 13 | `$RegressionScripts` | wave-13 verifier paths | **the wave-14 verifier's three paths** (`WAVE14-DEPLOY-2026-11-09`, `D:\jarvis-scratch\WAVE14-VERIFIER-2026-11-09`, `D:\jarvis-scratch\WAVE14-REVERIFY-2026-11-09`) | wave-14's acceptance is now a regression; it pins `24a3fc9b1` and grades the wave-14 tree |
| 14 | `$expectedShipped` | 335 | **335 — unchanged, informational only** | the `$SHIPPED` list parses to 335 entries at both `455765eb5` and `fd9cb576`; **no new module this wave** (add 0) |
| 15 | 0B comment + GO text | #1219, `frozen 24a3fc9b1 tree` | **#1221, `frozen fd9cb576 tree`, merge commit** | the code compares `$FrozenTree`; only the text moves |
| 16 | 0C comment | `#1218 is MERGED as 85e9e850` | **`#1220 is MERGED as 455765eb5`** | previous PR state |
| 17 | **0D — the big change** | "seven required checks green on `$ref`, or a same-tree waiver with the PR run" | **SAME-TREE-VERIFIED (Q4)**: (a) merge tree == PR head tree, (b) the PR head's ci.yml run was **7/7 required green**, (c) the post-merge **`Desktop release` AND `Jarvis client`** runs succeeded on the merge sha; the duplicate **main `CI` run is LOGGED, NOT AWAITED** | owner ruling Q4, 2026-11-10 00:05 PT: deploy first, then ONE combined owner-hands sweep on 0.2.445 |
| 18 | 0D evidence files | `0D-waiver.txt` | **`0D-same-tree-verified.txt` + `0D-main-ci.txt`** (the second one records the logged run) | the mode and the logged run each leave their own evidence |
| 19 | 0E GO text | wave 9/11/12/13/14 | **+ wave 15**; both releases must name `$Ref`; desktop 0.2.445, phone new (> 4047) | 0E still hard-requires both published releases, so the deploy never starts from a stale release |
| 20 | 0F neutral copy | `jarvis-desktop-wave14-setup.exe` | **`jarvis-desktop-wave15-setup.exe`** | run-scoped name |
| 21 | 0H expectation block | 335 = 1+21+313; 234 = 232+2; two auto-learn inserts; 32/0/26; PLANNED 24+N; backups 27->27; VERSION 0.2.443 | **335 = 0+7+328**; **234 = 234+0**; **0 to insert — an insert row is a STOP now**; 32/0/26; **PLANNED 7+N**; backupFolders **28->28**; VERSION unchanged **0.2.444** | measured at 10:20 PT, see §2 |
| 22 | 0H STOP text | "any insert row that is NOT one of the two auto-learn rows" | **any insert row at all** | both wave-14 inserts are live; an insert row means the live file lost them |
| 23 | `insurance` backup folder | `D:\jarvis-rehearsal\predeploy-wave14-<stamp>` | **`D:\jarvis-rehearsal\predeploy-wave15-<stamp>`** | separate insurance copy per wave |
| 24 | `apply` GO/STOP text | `wrote 25` = 1+21+2 staged delta files+VERSION 1; 28th folder | **`wrote 8` = update 7 + VERSION 1**; 0 delta files; **29th** folder; PLANNED 244 if pycache is still 236 | the tool's own arithmetic; see §2 |
| 25 | `reseal` GO text | `VERIFY 0 of 335`, PARTIAL names TO MEASURE | **`VERIFY 0 of 335`, `RESULT: PARTIAL`, names TO MEASURE** | wave 15 changes none of the unprovable base files, so a name outside the known set is a STOP |
| 26 | `toml` GO text | history + "did not change in wave 14 either" | **+ "did not change in wave 15 either"** | `backend/jarvis-framework.toml` is not in the 46-file diff |
| 27 | `install-desktop` launch copy | `setup-wave14.exe` | **`setup-wave15.exe`** | the launch copy on D: |
| 28 | `preflight` output file | `preflight-after-wave14.txt` | **`preflight-after-wave15.txt`** (write and grep) | run-scoped evidence |
| 29 | `preflight` GO text | wave-13 35/10/3/5 + the 10 named FAILs | **TO MEASURE**; compare ROW NAMES with the wave-14 set | the live patch stack moves every wave |
| 30 | `awareness` GO text | TO MEASURE; wave-13 24/1/0, FAIL `cap-cloud-escalation` | **TO MEASURE**; same standing FAIL expected | live runtime state |
| 31 | `postdeploy` comment, args, GO text | wave-14 script, 22 rows, wave-13 floors, expected 20/0/0/2 | **wave-15 script (29 rows)**, passes `-PhoneVersion` from 0E, `-Worktree` (a local tree whose HEAD tree is the frozen tree), `-FrozenSha $FrozenHead -FrozenTree $FrozenTree`; expected **0 FAIL + only the script's own by-design WARNs**; a **pre-deploy run of the same script is expected to FAIL the version and new-content rows** | the checks script's own defaults now pin `fd9cb576` / `be333667` / 0.2.444 / 4047, so the gate's explicit args are belt-and-braces |
| 32 | `verify-wave8` dst + json/txt names | `verify_wave8_wave14.py`, `12-verify-wave8-wave14.*` | **`verify_wave8_wave15.py`, `12-verify-wave8-wave15.*`** | run-scoped evidence |
| 33 | `verify-wave8` comment | grep at the wave-14 frozen head | **grep re-run at `fd9cb576`** — still exit 1, no `coding preset` in `backend/jarvis_recent_changes.py` | expectation re-derived, still 26/1 |
| 34 | `probes` gate | wave-11 + wave-13 regression + wave-14 acceptance; STOP on a stale verifier pin | **wave-11 regression (24/24) + the WAVE-14 verifier as REGRESSION (12/0/3/1, exit 1 by design) + `verify_wave15_live.py` as ACCEPTANCE**; STOP if the acceptance verifier's `EXPECTED_SHA` is not `fd9cb576` or its worktree cannot resolve that commit | a green regression is not this wave's acceptance |
| 35 | `Show-Gates` | wave-14 title; 27->28 folders; `verify_wave14_live.py` | **wave-15 title; 28->29 folders; `verify_wave15_live.py`; SAME-TREE-VERIFIED named** | the one-liner list must describe this run |

The unchanged gates are `repair`, `be`, `stop`, `stopped`, `quotes`, `identity` — byte-identical to
wave 14. `jarvis_gate.py` is not touched by wave 15, so `repair`'s remembered size/hash lineage still
describes the live file.

## 2. The numbers, and how each was derived (then measured at 0H)

The 0H dry run was taken read-only at the frozen merge commit, in the packet's own `wt`, and wrote
nothing (28 backup folders before and after). Receipts: `0H-preview-wave15.txt` and the run folder's
`0H-dryrun.txt`. What it printed:

### SHIPPED 335 = add 0 + update 7 + unchanged 328 — MEASURED
- `$SHIPPED` parses to **335** entries at both `455765eb5` and `fd9cb576` (parsed with `ast` from
  `git show <ref>:backend/_where.py`). No module was added this wave, so add = 0.
- The seven updates are decided by **live bytes vs the ref's blob** (`plan_shipped()`:
  `status = "unchanged" if current == blob else "update"`), and they are exactly:
  `jarvis_recent_changes.py`, `jarvis_hud.html`, `hud-edit.js`, `hud-presets.js`, `hud-layout.js`,
  `jarvis_vault_organizer.py`, `jarvis-self-code.json`.
- Note the two different sets, and why they are both right:
  - **46 files** changed between the base `455765eb5` and the merge `fd9cb576` (7,981 insertions,
    1,353 deletions) — this is the wave-15 PR's own content.
  - **56 files** changed between the wave-14 *deploy* tree `24a3fc9b1` and `fd9cb576` (8,629 / 1,483)
    — this adds the #1220 follow-ups that were merged after the wave-14 deploy (`jarvis_vault_organizer.py`
    and its suite, `jarvis-self-code.json`, `jarvis_recent_changes.py`, the record files).
  - The live folder sits on the wave-14 deploy, so the **live-vs-tree** comparison picks up
    `jarvis_vault_organizer.py` (DEF-062) from the second list and skips `jarvis_big_coder.py` (already
    byte-identical). That is why 0H's seven and the PR diff's seven backend files are not the same
    seven — see §4 item 5.

### HUD DELTAS 234 checked = 234 already + 0 to insert — MEASURED
- The count is **patch x patched-file pairs with added lines**; no `.patch` file changed in wave 15
  (checked against both bases), so it stays 234.
- Wave 14 inserted the two `auto-learn.patch` rows (`jarvis_hud.py` 3 regions, `jarvis_extract.py`
  2 regions) and its apply wrote them. They are live, so they are now in "already present".
  **An insert row in this wave means the live file lost a wave-14 insert: STOP.**

### READY PLUG-INS 32 present / 0 to add / 26 already wired — MEASURED
No `plugins/ready/` file is in either change list; the wave-14 state stands. A non-zero "to add" is a
STOP (it would mean a plugin step did not stick).

### 0H PLANNED = 7 + pycache
`PLANNED = add 0 + update 7 + insert 0 + beside/version 0 + pycache`. The receipt measured
**pycache 236** → `PLANNED CHANGES: 243`. **pycache is a live counter**: wave 14 watched it move
231 → 232 during one session. Read the tool's own number; never type 236.

### apply: wrote 8 — DERIVED, then confirmed by the 0H receipt
`wrote = apply_shipped(add + update) + apply_deltas(distinct staged files) + released`
= (0 + 7) + 0 + 1 = **8**. Wave 14 is the same formula: (1 + 21) + 2 + 1 = 25, and the tool printed
`wrote 25`. Apply's own `PLANNED CHANGES` = 7 + 1 + pycache = **244** if pycache is still 236.
The apply gate makes the VERSION write happen by exporting `JARVIS_DESKTOP_EXE` = the neutral
0.2.445 setup copy from 0F; without that line the tool would print `VERSION: unchanged` and
`wrote 7` — that is the first thing to check if 8 does not appear.

### backup folders 28 -> 28, then 29
The live folder held **28** `_jarvis-deploy-backup-tool-*` folders when this packet was written
(newest `_jarvis-deploy-backup-tool-20261109-213922`, the wave-14 apply). 0H printed 28 -> 28; the
apply's `BACKUP:` line creates the **29th**, which the rollback gate prints.

### reseal VERIFY 0 of 335
`FILES (335 entries in $SHIPPED…)`; the count is unchanged because no module was added. Wave 14
printed `VERIFY : 0 of 335` with `RESULT: PARTIAL` and named a subset of
`jarvis_gate.py, jarvis_hud.py, jarvis_skills.py, jarvis_extract.py, jarvis_project_read.py`.
Wave 15 changes none of those files' identities, so the same allowed set applies — **read the names
it prints**, and a name outside that set is a STOP.

### verify-wave8: 26/1 again
`git grep -i 'coding preset' fd9cb576 -- backend/jarvis_recent_changes.py` → **exit 1, no match**
(re-run for this packet). `jarvis_recent_changes.py` was regenerated this wave (2,966 → 2,972 B) and
still cannot name "Coding preset", so `self-update-history` stays the single FAIL (or 27/0 if its
other needle now satisfies it). The version rows read the **new** versions.

## 3. What is measured at 0H and never predicted

These belong to the live PC at run time. The packet prints them and the operator reads them; **no
document may state them as a fixed value**:

| item | where it is read |
|---|---|
| `SHIPPED` split and the seven names | `0H-dryrun.txt` — the tool prints them every run |
| `HUD DELTAS` already/insert split | same |
| `READY PLUG-INS` present/to-add/wired | same |
| **`PYCACHE: N`** and therefore `PLANNED CHANGES` | same (live directory scan) |
| `VERSIONsame` / `VERSION:` line | same |
| `backupFolders=` line | same |
| `wrote N` and apply's `PLANNED CHANGES:` | `4-apply.txt` |
| `reseal` PARTIAL count and names | `5-reseal.txt` |
| `preflight` FAIL/WARN rows and totals | `preflight-after-wave15.txt` |
| `awareness` SUMMARY and BLOCKED rows | `11-awareness-sanity.txt` |
| **postdeploy SUMMARY and row count** | `10b2-post-checks.txt` / `-stdout.txt` |
| wave-14 (regression) and wave-15 (acceptance) verifier SUMMARYs | `10-probes-wave14.txt`, `10-probes-wave15.txt` |
| the actual new phone version | gate 0E, from `client-latest` |
| the wave-15 verifier's path/size | the probes gate's `wrote` line |

## 4. Gates whose old assumption no longer holds

1. **0D is a different mode, not a different message.** Wave 14 accepted "the main ci.yml run on the
   merge ref, or a same-tree waiver with the PR run". Wave 15 accepts **SAME-TREE-VERIFIED** only:
   merge tree == PR head tree, the PR head's 7/7 required checks, and **both** post-merge release
   workflows green on the merge sha. The duplicate main `CI` run is **written to the run folder and
   recorded when it finishes — it is never awaited**. Do not sit on 0D waiting for it.
2. **`wrote 25` is wave-14's number.** Wave 15's arithmetic gives **8** (7 updates + VERSION 1) with
   **no** delta-file writes, because wave 14's two inserts are already live. A `wrote 25` here would
   mean the tool planned wave-14 work again — a STOP to diagnose, not a pass.
3. **0H's "to insert" must be empty.** Wave 14's allowed inserts (the two `auto-learn.patch` rows) are
   now the thing whose *absence from the live file* is the failure. Any insert row is a STOP.
4. **The probes gate's roles swapped.** It now runs three scripts: the wave-11 probes as regression
   (24/24), the **wave-14 verifier as regression** (its measured shape, 12 PASS / 0 FAIL / 3 BLOCKED
   / 1 PARTIAL, exit 1 by design — BLOCKED is never a pass), and **`verify_wave15_live.py` as this
   wave's acceptance**. The gate STOPS if the acceptance verifier's `EXPECTED_SHA` is not
   `fd9cb576`, or if its worktree cannot resolve that commit. A green regression proves nothing
   about wave 15.
5. **Two files change the plan in opposite directions.**
   - `jarvis_vault_organizer.py` is **not** in the 46-file PR diff, yet the apply **will write it**
     (live 118,536 B, sha256 `34B11EB3…`; tree 119,353 B, sha256 `630687BA…`) because the plan
     compares live bytes with the tree. That is DEF-062's wording delivery — a wave-14 follow-up
     that never reached the live folder. Expect it in `wrote 8`; its post-deploy row is `DEF-062`.
   - `jarvis_big_coder.py` **is** in the 46-file PR diff, yet the apply will **not** write it: the
     live file is already byte-identical to the tree (53,831 B, sha256 `96F52607…`, git blob
     `39159f6b`). So it counts as `unchanged`, not in `wrote N`, and **Q3's cap is not re-applied
     by this deploy** (it is already both live and in the repo — see the runbook §4).
6. **`postdeploy`'s old tally is gone.** Wave 14's script had 22 rows and its measured shape was
   20 PASS / 0 FAIL / 0 BLOCKED / 2 WARN. The wave-15 script declares **29 rows** (22 carried + the
   seven new HUD-MODS / DEF-062 / DEF-063 / DEF-064 / HUD-NAV / HUD-TOKENS / Q3-CAP). Read its
   SUMMARY; a pre-deploy run of the same script is *expected* to FAIL the version and new-content
   rows, which proves the rows bite.
7. **The phone expectation is not floor+1.** The installed phone is 0.2.4047, but `client-latest` was
   already at `0.2.4052 (main @ 455765e)` before this merge, so the new tag jumps past 4052. The
   gate's rule is the floor (4047) and the real value comes from the release at 0E.
8. **Backup folders are 28 before, 29 after** — not 27/28. 0H prints `28->28`; the apply's BACKUP
   line names the 29th, and the rollback gate prints it.
9. **`verify-wave8` reads the new versions.** Its literal version strings are re-baselined to
   `$NewDesktopVersion` / `$NewPhoneVersion`, so 26/1 today can become 27/0 once the versions move;
   both are a GO, anything else is a STOP.

## 5. Evidence trail (read-only)

- `frozen-ref.txt` — the pin (frozenHead/frozenTree/prevHead/prevTree/baseOriginMain/pr/prevPr/floors/live values/backupFoldersBefore 28).
- `git rev-parse origin/main` → `fd9cb576…`; `git rev-parse origin/main^{tree}` and
  `git rev-parse d66a0a4cf^{tree}` → both `be333667…`.
- `gh pr view 1221` → MERGED, `mergeCommit.oid` `fd9cb576…`, `headRefOid` `d66a0a4cf…`;
  `gh pr view 1220` → MERGED as `455765eb5…`.
- `git diff --name-status 455765eb5 fd9cb576` → **46 files**; `--numstat` totals **7,981 / 1,353**.
  `git diff --stat 24a3fc9b1 fd9cb576` → **56 files, 8,629 / 1,483**.
- `git cat-file -s fd9cb576:<path>` → `jarvis_hud.html` 776,898; `static/hud-edit.js` 105,726;
  `static/hud-layout.js` 38,305; `static/hud-presets.js` 133,281; `jarvis_big_coder.py` 53,831;
  `jarvis_recent_changes.py` 2,972; `backend/jarvis_vault_organizer.py` 119,353.
- `git rev-parse fd9cb576:backend/jarvis_vault_organizer.py` → blob `5dde9998…`; the same blob at
  `455765eb5` (so #1220 landed it before this PR).
- `git hash-object --no-filters "<live>\jarvis_big_coder.py"` → `39159f6b…` = the tree blob; live
  sha256 `96F52607…`; bytes 53,831.
- `git show fd9cb576:tools/reconcile_live_backend.py` → `def plan_shipped(...)` docstring
  "Compare every shipped file's bytes with the ref; copy only changed/missing" and
  `status = "unchanged" if current == blob else "update"`.
- `ast` parse of `backend/_where.py` at both refs → `SHIPPED` 335 / 335.
- `git grep -i 'coding preset' fd9cb576 -- backend/jarvis_recent_changes.py` → exit 1.
- 0H receipt: `0H-preview-wave15.txt` (335 = 0+7+328; 234 = 234+0; 32/0/26; PYCACHE 236;
  PLANNED 243; VERSION unchanged 0.2.444) and `run-20261110-102051\0H-dryrun.txt`.
- Live pre-state, read-only: `VERSION` 0.2.444; desktop `HKCU … DisplayVersion` 0.2.444; phone
  `versionName 0.2.4047` / `versionCode 1000004047`; 28 `_jarvis-deploy-backup-tool-*`; TOML
  58,409 B / `9C6CDF76…C92D97`; two listeners on :4719 and HTTP 403.
- Parse: `check-parse-wave15.ps1` under Windows PowerShell 5.1.26100.9711 → `PARSE OK` for both
  scripts, `PARSE-CHECK-DONE bad=0`, exit 0.
- `gh run view 42796552404` → CI on the PR head, success; 17 check-runs on `d66a0a4cf`, all success
  (14 of them the CI run's own jobs). `gh run view 42872103330` → Desktop release, success, #445.
  `gh run view 42872103259` → Jarvis client #4054, in progress at 10:16 PT.
  `gh run view 42872103198` → main CI #4986, in progress (logged, not awaited).

No live file was written by this lane, no gate was executed by this lane, nothing was merged or
pushed, and no token was read or printed.
