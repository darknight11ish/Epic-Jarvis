# Wave-14 real-run runbook (2026-11-09 night -> 2026-11-10)

STATUS: PREPARED BEFORE THE MERGE, then re-based after the head move. The authority is the live
value in `frozen-ref.txt` in this folder, and the post-merge tree check below. This runbook is the
wave-13 one re-derived for wave 14; it does not replace the gate script's own text.

**FROZEN REF (re-based 20:37 PT after the head moved):**
`frozenHead=24a3fc9b1da913556b7ee1585d46538830cb0b80`, `frozenTree=ad1de9e15f5ad14b35a1d7c9cda31d2eaa54e9c8`
(PR #1219's final head, run `42754820367`; the move was one `fix(ci)` commit on the two hud-edit.js
copies). Packet artifacts re-based to it: `deploy-gates-wave14.ps1`, `post-deploy-checks-wave14.ps1`,
`verify_wave14_live.py`, `VERIFIER-EXPECT-WAVE14.md`; the deploy worktree `wt` must be moved from
`2dc899fdb` to this head (Gate 0B does not move it; the `probes` gate STOPS on a mismatch).
0H measured at the frozen head (read-only, `EXPECTATIONS-0H.md`): SHIPPED **335** (1 add + 21
update + 313 unchanged), HUD DELTAS **234 = 232 + 2** (auto-learn.patch -> hud.py 3 regions and
-> extract.py 2 regions), PLUG-INS **32 present / 0 to add / 26 wired**, PLANNED **24 + pycache**,
apply **wrote 25**, VERSION unchanged 0.2.443 -> apply writes 0.2.444, backups **27 -> 27** (28 after
apply), dryRunExit=0, no REFUSED/Traceback.

## 0. Preconditions

- PR #1219 OPEN, MERGEABLE, all SEVEN required checks SUCCESS (`rust`, `frontend`, `backend`,
  `backend-windows`, `credential-manager`, `powershell-5`, `phone-unit-tests`; ruleset 24677804).
  The paired session (off-peak continuation) owns the merge - this session does not merge.
- Merge commit tree MUST equal the frozen tree in `frozen-ref.txt`. Pre-merge prediction:
  `git merge-tree --write-tree origin/main <head>` printed the head tree, because origin/main
  `85e9e850` is an ancestor of the PR head. Verify after the merge with
  `git rev-parse origin/main^{tree}` and STOP if it differs.
- Live state before: backend+desktop **0.2.443**, phone **0.2.4042**, 27
  `_jarvis-deploy-backup-tool-*` folders, app running on :4719.
- Fresh run folder: this packet has no `CURRENT-RUN.txt` yet; the first gate creates
  `run-<stamp>`. Never reuse a wave-13 run folder.

## 1. Merge and releases

The paired session merges #1219 and relays the merge sha. Then:

```
git -C "...\Epic-Jarvis-main\.dsh-scratch\WAVE14-DEPLOY-2026-11-09\wt" fetch origin main
git -C "...\wt" rev-parse origin/main
git -C "...\wt" rev-parse "origin/main^{tree}"
```

Tree must equal `frozen-ref.txt` frozenTree. Then start the release watcher (below) and run the
gate train; gate 0E needs BOTH releases naming the merge sha, so the train runs through 0D/0G/0H,
insurance, repair, be, stop, stopped, then waits for 0E -> 0F -> apply.

Expected releases: desktop **0.2.444** (desktop-release run 444); phone **0.2.4044** expected
(jarvis-client run_number on the main push; wave 13's was 4042, so this is the next-but-one at most -
read the release names, never assume). Floors: 0.2.443 / 4042.

## 2. Gate train (wave-14 script)

One process per gate, in this order, `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
"<this folder>\deploy-gates-wave14.ps1" -Gate <gate>`, console captured to
`gate-logs\<gate>.log`. Gate text is the verdict, not the exit code.

| # | gate | expected (fill from 0H measurement before the run) |
|---|---|---|
| 1 | 0B | GO: ref = merge sha, origin/main tree == frozen tree, deploy tree checked out at the merge sha |
| 2 | 0C | GO: #1219 MERGED and ancestor of ref; #1218 finished |
| 3 | 0D | GO: main ci.yml run on the merge ref 7/7, or same-tree waiver with the PR run |
| 4 | 0E | GO: BOTH releases name the ref; desktop 0.2.444; phone new; writes release-vars.json |
| 5 | 0F | GO: setup FileVersion 0.2.444 + APK names the merge sha first 7; both sha256 match the API; neutral copy |
| 6 | 0G | GO: HEAD=expect, trackedChanges=0, gateRecordCall=True, toolBytes equal |
| 7 | 0H | TO MEASURE: SHIPPED count/add/update, HUD DELTAS + the inserts (the D-1 fix should insert auto-learn.patch hunks), PLUG-INS, PYCACHE, PLANNED; dryRunExit=0; VERSIONsame=True; backups 27->27 |
| 8 | insurance | GO: D: copy written, TOML hash equal, copy VERSION 0.2.443 |
| 9 | repair | GO: six probes count=1, probesBad=0 (pre-apply size/hash lineage) |
| 10 | be | GO: 2 listeners (loopback + tailnet), HTTP 403 |
| 11 | stop | the ONLY authorised stop; kills the tree |
| 12 | stopped | GO: LISTENING=0, no local ESTABLISHED, no HTTP |
| 13 | apply | GO: `wrote N` = add + update + inserts + VERSION 1 (N measured at 0H), VERSION -> 0.2.444, backup folder 28, `RESULT: FAIL (3 expected)` probe failures, no rollback |
| 14 | quotes | GO: quotes hashes equal, probesBad=0 |
| 15 | reseal | GO: `VERIFY: 0 of <SHIPPED count>`, RESULT PARTIAL naming only the unprovable base files (wave 13 named gate/hud/skills; wave 14 may add jarvis_project_read.py if it is SHIPPED and unprovable - read the printed names) |
| 16 | toml | GO: owner TOML untouched 58,409 B / 9C6CDF76...C92D97 |
| 17 | install-desktop | GO: after = 0.2.444, exitedIn180s=True, HKCU DisplayVersion 0.2.444 |
| 18 | install-phone | GO: one device, Success, versionName = release, versionCode = 1000000000 + run digits |
| 19 | restart | GO: NEW listener pid, both listeners, HTTP 403 |
| 20 | identity | GO: PASS, identityExit=0 |
| 21 | probes | wave-11 regression 24/24 PASS exit 0; wave-14 verifier read row by row (MF-2 should now PASS if D-1 delivered; W12-3 may stay BLOCKED; guarded rows stay BLOCKED) |
| 22 | preflight | record rows: the wave-13 standing set is 9 FAILs + the auto-learn patch row (which should disappear once D-1 delivers); compare ROW NAMES, never a total |
| 23 | awareness | record rows: 24/1/0 expected (cap-cloud-escalation standing FAIL); version rows read the new versions |
| 24 | postdeploy | wave-14 post-deploy checks: MF-1 should now PASS; WARNs A-SIZES/F5-1 by design unless the tree changed them; read the printed SUMMARY |
| 25 | verify-wave8 | 26/1 with only self-update-history, version rows read the new versions |
| 26 | rollback | print only; anchor = the new `_jarvis-deploy-backup-tool-*` folder |

### 2.1 Expected printed values (measured, frozen head)

- 0H: `SHIPPED (335 = 1 + 21 + 313)`; `HUD DELTAS (234 checked = 232 already + 2 to insert)`; the
  two insert lines are exactly `auto-learn.patch -> jarvis_hud.py (3 region(s))` and
  `auto-learn.patch -> jarvis_extract.py (2 region(s))`; `READY PLUG-INS (32 present, 0 to add,
  26 already wired)`; `PYCACHE: <N>` live only; `PLANNED CHANGES: 24 + N`; `VERSION: unchanged
  0.2.443`, `VERSIONsame=True`; `backupFolders=27->27`; `dryRunExit=0`.
- apply: `wrote 25` (22 shipped + 2 delta files + VERSION 1); `VERSION: wrote 0.2.444`;
  `PLANNED CHANGES: 25 + N`; backup folder #28 `_jarvis-deploy-backup-tool-<stamp>`; the three
  expected probe failures and SKIP app-control are expected (read the probe list).
- reseal: `VERIFY : 0 of 335`, `RESULT: PARTIAL`; allowed PARTIAL names only
  `jarvis_gate.py, jarvis_hud.py, jarvis_skills.py, jarvis_extract.py, jarvis_project_read.py`.
- postdeploy (wave-14 script, patched to the frozen head): expected **20 PASS / 0 FAIL / 0 BLOCKED /
  2 WARN** (A-SIZES, F5-1), exit 0; MF-1 flips FAIL -> PASS; W12-2 expected PASS. Read the SUMMARY.
- probes gate: wave-11 regression 24/24 PASS; wave-13 verifier regression is expected to have its
  wave-13 FAIL (MF-2 404) - it grades wave 13's tree, so read it as regression only; wave-14
  verifier expected **12 PASS / 0 FAIL / 3 BLOCKED / 1 PARTIAL** (`W12-3` structural BLOCKED makes
  exit 1; pass mark is 0 FAIL).
- preflight/awareness/verify-wave8: compare row NAMES to wave 13 (§3 lists them); wave-13 measured
  35/10/3/5, 24/1/0 (`cap-cloud-escalation` the standing FAIL), 26/1 (`self-update-history`).

## 3. Owner-required post-deploy checks (record PASS/FAIL/NOT-RUN with evidence)

Run AFTER the gate train (the gates already ran postdeploy + both verifiers; these are the owner
rows, one runner). Receipts land in `D:\jarvis-scratch\WAVE14-PROBES-2026-11-09\`.

0. **Read-only rows 1, 2, 4, 5** (GET-only, ~15 s):
   `py -3 -B D:\jarvis-scratch\WAVE14-PROBES-2026-11-09\run_wave14_probes.py`
1. `GET /api/memory/fault` answers HTTP 200 valid JSON, NOT 404 (D-1 delivery proof).
2. Live backend `jarvis_skills.py` carries `_extra_findings(`.
3. F2: `/api/ps` on port 11450 reports `context_length == 49152` on a COLD chat turn (owner ruling
   Q7), ONE lane-direct cold turn:
   `py -3 -B D:\jarvis-scratch\WAVE14-PROBES-2026-11-09\run_wave14_probes.py --only 3 --cold-turn`
   — it loads ~13.8 GB on 11450, does one chat turn, records `context_length` (and spill), then
   unloads. If it does not, record NOT-RUN/FAIL with what was seen; never call it PASS.
   The stronger product path (POST /api/work/apply preset=coding -> ONE card the owner approves)
   needs the owner at the screen and is NOT run tonight; the lane-direct turn is the authorised
   substitute and its spill must be recorded.
4. Medical Expert is the tenth preset and is selectable.
5. Vault organizer ON-switch raises exactly ONE approval card on a fresh backend (DEF-061) using
   `OPENJARVIS_CONFIG_DIR` pointed at a temp dir, with the live config hash unchanged.
   Probe receipts: `D:\jarvis-scratch\WAVE14-PROBES-2026-11-09\`.

## 4. Owner ruling Q3 — 3 GB prompt-cache cap

Apply `LLAMA_ARG_CACHE_RAM=3072` where each lane server reads it, restart the lane ONCE, and
measure RAM + first-word/tokens-per-second before and after on throw-away calls. Before numbers
were captured pre-deploy (`D:\jarvis-scratch\WAVE14-CACHE-CAP-2026-11-09\BASELINE-BEFORE.md`:
11436 one warm call 1,619.7 ms first content / 34.27 tok/s / 11 tokens; RAM 13,166 MB private,
10,400 MB GPU; 11435 7,163 MB private / 6,126 MB GPU, no before call; 11450 cold 64 MB).
If a clean pair is impossible, record exactly which half is missing and why.

**Mechanism (live-only files; back up first to `...\WAVE14-CACHE-CAP-2026-11-09\pre-q3\`):**
1. `C:\Users\pcadmin\AppData\Local\JarvisOllama\start-lane.ps1` — insert after the
   `$env:OLLAMA_NO_CLOUD = '1'` line:
   `$env:LLAMA_ARG_CACHE_RAM   = '3072'   # Q3 2026-11-09: cap the prompt cache in system RAM at 3 GB`
   (covers 11436 and 11435 on their next start; proven by the lane log's startup env map).
2. Live `...\Desktop program\jarvis_big_coder.py` — in `_child_env()`, insert before `return env`:
   `    env["LLAMA_ARG_CACHE_RAM"] = "3072"   # Q3 2026-11-09: 3 GB host-RAM prompt cache`
   (11450; the running backend keeps the OLD module until the app is restarted, so the cap is
   activated by ONE documented second app restart at the end of Q3).
   Repo twin + PR: the two-file rule means this line belongs in `backend/jarvis_big_coder.py` AND
   `jarvis-backend/jarvis_big_coder.py`; this session does NOT push - the exact hunk goes to the
   paired session for the wave-15 record.

**Order (the owner rows above are run BEFORE any edit, on the deployed 0.2.444):**
1. Probe rows 1,2,4,5; then F2 cold turn (row 3) — pristine deploy evidence.
2. Back up both live files, record sha256; apply the two one-line edits, record new sha256.
3. Prove the edited 11450 path without starting anything:
   `py -3 -B -c "import sys; sys.path.insert(0, r'...\Desktop program'); import jarvis_big_coder as B; print(B._child_env(11450).get('LLAMA_ARG_CACHE_RAM'))"`
   must print `3072` (only that key is printed; env contains no secrets).
4. Restart 11436 ONCE (one-liner in `PLAN.md` §3), then `measure.ps1 -Label after-fresh` and
   `measure.ps1 -Label after-11436 -Chat -ChatPort 11436 -AllowLoad -ModelName qwen3.5:9b -Calls 3`.
5. Restart 11435 ONCE, then `measure.ps1 -Label after-11435 -Chat -ChatPort 11435 -AllowLoad
   -ModelName qwen3:8b -Calls 3`.
6. Prove the cap reached the engines: `Select-String` the startup env-map line for
   `LLAMA_ARG_CACHE_RAM` in `...\JarvisOllama\logs\main.log` and `coding.log` (files are truncated
   on every start, so the line is this run's).
7. Stop the cold 11450 server so its next start uses the edited env; cold snapshot after.
8. ONE documented second backend app restart (same restart mechanics as the gate) to load the
   edited `jarvis_big_coder.py`; re-verify new pid, 2 listeners, HTTP 403, VERSION 0.2.444.
   This is ACTIVATION, named as such in the result; gates/verifier ran before it.
9. Honest limits: 11436 before = ONE warm call (calls 2-3 missing); 11435 before = MISSING (no
   pre-deploy POST was authorised there); 11450 loaded-RAM before/after = PARTIAL (the only
   loaded run is the F2 cold turn, taken before the cap; a second 13.8 GB load was NOT run).
   The `after-fresh` snapshot plus the startup env-map line separate "cap applied" from "cache
   was emptied"; a RAM pair alone is an upper bound, not proof of the 3 GB ceiling.

## 5. Records

- Result/receipt: `D:\jarvis-scratch\OFFPEAK-CONTINUATION-2026-11-09\WAVE14-DEPLOY-RESULT-2026-11-10.md`
  (this session writes it; the paired session gets a compact table).
- Packet: this folder (`deploy-gates-wave14.ps1`, `post-deploy-checks-wave14.ps1`,
  `EXPECTATIONS-0H.md`, `GATE-DIFF-NOTES.md`, `POSTDEPLOY-EXPECT-WAVE14.md`, `frozen-ref.txt`,
  `gate-logs\`, the run folder).
- Verifier: `D:\jarvis-scratch\WAVE14-VERIFIER-2026-11-09\verify_wave14_live.py`.
- Rollback: wave-13's `ROLLBACK.md` is the procedure template; tonight's anchor is the new backup
  folder printed by the apply gate. Do not touch the owner's TOML; never hand-edit live files.
