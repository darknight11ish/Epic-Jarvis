# Wave-14 packet integration record (Lead, 2026-11-09 20:35 PT)

Every number here was measured on this PC tonight. This file is the packet's own audit trail: it
says what each lane delivered, what the Lead re-based after the PR head moved, and which checks were
re-run. The authority for the frozen ref remains `frozen-ref.txt`.

## 1. The frozen ref (authority)

- `frozenHead = 24a3fc9b1da913556b7ee1585d46538830cb0b80`
- `frozenTree = ad1de9e15f5ad14b35a1d7c9cda31d2eaa54e9c8`
- base `origin/main` before the merge: `85e9e85005d175a9a5217ff1a3650cc51947cb20` (wave-13 merge),
  tree `46216eac7f1b0aedcbc8bf5dc7841aa6e76574a0`.
- The head moved during preparation from `2dc899fdbd23cffce498449858b1eb7d3c153c0b` (tree
  `d98c6519…`) to the frozen head by ONE commit: `fix(ci): the served hud-edit copy and its base
  copy follow the editor comment` (`backend/static/hud-edit.js` + `jarvis-backend/hud-edit.js`,
  +10/-8; both blobs now `96595` bytes). Nothing else changed: 129 files changed vs base on both
  heads, `tools/reconcile_live_backend.py` byte-identical, every gate/0H count identical.
- Deploy worktree moved (Lead, 20:33 PT): `.dsh-scratch\WAVE14-DEPLOY-2026-11-09\wt` checked out
  detached at the frozen head, clean, `HEAD^{tree} = ad1de9e1…` (was at the previous head for the
  preparation measurements). `wt-frozen` is also at the frozen head. **Gate 0B moves the deploy
  tree `C:\Users\pcadmin\Documents\jarvis-install-tree`, never `wt`.**
- Merge-commit prediction: `git merge-tree --write-tree 85e9e850 <head>` = `ad1de9e1…`; main is an
  ancestor of the head, so after the merge `origin/main^{tree}` MUST equal `ad1de9e1…`. Gate 0B
  STOPS on any other tree.

## 2. Artifact hashes (re-read at 20:34 PT)

| file | bytes | sha256 |
|---|---|---|
| `frozen-ref.txt` | 1,178 | `CE09C6F5B8350C90B82BD1728194266A990ED85DD20F48A7AE819DFEDD75871F` |
| `deploy-gates-wave14.ps1` (lane repinned by its owner) | 74,012 | `C98BA1BA69BAB67FE31189835DB1AC400C98AF3FBF93D508E2AEEFF562C19D9C` |
| `post-deploy-checks-wave14.ps1` (Lead re-based sha/tree) | 45,022 | `66881FD11AAA595EE0E05DD95F015B959BB38C3182F0A2591C293790329CF23F` |
| `GATE-DIFF-NOTES.md` (lane) | 26,839 | `E3580878AA1D350A3E2889A2655D94B531E87900AF392F1DCBAA42469A9C9767` |
| `EXPECTATIONS-0H.md` (lane) | 13,062 | `1716CC4CF0A72331682DCE4DCD11ECEB92AD5FE5EFA145BA6FD5D12FF90410F0` |
| `POSTDEPLOY-EXPECT-WAVE14.md` (lane) | 14,490 | `46D67CA4CCECD341A2C9E7B63673F5463A28335C2682ADD7916D0B62BF67A7A3` |
| `WAVE14-RUNBOOK-2026-11-10.md` (Lead, updated) | 13,530 | `826DDA51F04FC6091141E2B4E7E9B83ABAB033ECE0892CA17E928535E59AE92B` |
| `run-gate.ps1` (Lead) | 1,456 | `31AE98BC89C74231D0A4AFADDD37D15C70009DA71F65A4E80E86517F8A54B484` |
| `check-parse-all.ps1` (Lead) | 767 | `E4767221BCC4DFE4D9613F40CADDA1F61ED8C3148D546E636132639366DDAE56` |
| `q3-apply-cap.ps1` (Lead, NOT run before the deploy) | 4,851 | `15B577021ECCC6F0831D613E9D287C205B5FE891FECA4CEEA0CB4C73E75023EA` |
| `q3_child_env_probe.py` (Lead, read-only proof) | 1,877 | `E575975D7A65648D8F0070F26475315E58DB88ADAECAB5541F364AE91D4376E5` |
| `D:\…\WAVE14-VERIFIER-2026-11-09\verify_wave14_live.py` (Lead re-based expected sha) | 84,080 | `0414E2DB1C4495AA326F3ED318AAE7E7EAF3C4F1A5BA07CE72C29F38D81C9C85` |
| `…\VERIFIER-EXPECT-WAVE14.md` (Lead re-based text) | 37,742 | `4356C2743683803EE072BE9364B0A934C73ABF16D476EA056F2A3EDBB92610A3` |

The wave-13 packet and evidence stay untouched in `.dsh-scratch\WAVE13-DEPLOY-2026-11-09\`.

## 3. What each lane delivered (all read-only; no live write, no POST, no restart, no merge)

- **0H measurement** (`EXPECTATIONS-0H.md`, `0H-PREVIEW-wave14-frozen.txt`, `0H-inventory-frozen.json`):
  measured at the frozen head. SHIPPED **335 = 1 add + 21 update + 313 unchanged** (new
  `jarvis_project_read.py`); HUD DELTAS **234 = 232 already + 2 inserts ONLY**
  `auto-learn.patch -> jarvis_hud.py (3 region(s))` and `-> jarvis_extract.py (2 region(s))`
  (skill-scan-wiring is now already present); PLUG-INS **32 present / 0 to add / 26 wired**;
  PYCACHE live only (231 then 232); PLANNED **24 + pycache**; VERSION unchanged 0.2.443;
  backups **27 -> 27**; dryRunExit 0, no REFUSED/Traceback; D-1 proof: DELTA_TABLE entry exists at
  the frozen head only (0 auto-learn mentions at 85e9e850), new test
  `t_the_auto_learn_fault_routes_are_carried_not_false_greened` ran 37/37 ok.
- **Gate packet** (`deploy-gates-wave14.ps1`, `GATE-DIFF-NOTES.md`): the wave-13 packet re-based
  for wave 14 (36 `# W14:` markers), repinned to the final head, PS 5.1 PARSE OK. It adds
  `-FrozenTree` (merge commit passes by tree), the 3-script probes gate (wave-11 regression +
  wave-13 regression + wave-14 acceptance, STOP on a stale verifier pin), RUNS the post-deploy
  checks script with this run's `-FrozenSha/-FrozenTree/-Worktree/-PhoneVersion`, and prints
  wave-13's measured numbers as reference with TO MEASURE for the live-only totals.
- **Post-deploy static checks** (`post-deploy-checks-wave14.ps1`, `POSTDEPLOY-EXPECT-WAVE14.md`):
  22 rows (wave-13's 19 + 3 new W14 rows: W14-PROJ, W14-HUDK, W14-EDIT, W14-VAULT), MF-1 flipped
  FAIL -> PASS, W12-2 WARN -> PASS, A-SIZES 14 rows. Expected on the real deploy: **20 PASS /
  0 FAIL / 0 BLOCKED / 2 WARN (A-SIZES, F5-1 by design), exit 0** - the first wave whose post-deploy
  checks exit 0. It is read-only; the only file it writes is `-Transcript`.
- **Wave-14 verifier** (`verify_wave14_live.py`, `VERIFIER-EXPECT-WAVE14.md`): wave-13's verifier
  with `EXPECTED_SHA` re-based and 3 new implemented rows (MEM-3, PRJ-1, PRE-1). 16 rows, all
  dispatched. Expected: **12 PASS / 0 FAIL / 3 BLOCKED (CR-4, F2-3 guarded; W12-3 structural) /
  1 PARTIAL (W12-2), exit 1** (W12-3's structural BLOCKED makes exit 0 unreachable; the pass mark
  is 0 FAIL - BLOCKED is never a pass).
- **Probes runner** (`run_wave14_probes.py`, `PROBE-PLAN.md`, baseline before the deploy):
  owner-row runner - check 1 memory-fault GET (baseline 404, the D-1 bug), check 2 live
  `jarvis_skills.py` `_extra_findings(` (already PASS at 49,320 B), check 3 the ONE cold 11450
  turn behind `--cold-turn` (loads ~13.8 GB, reads `/api/ps` `context_length == 49152`, chats once,
  unloads), check 4 tenth preset (baseline 9 presets, no Medical), check 5 vault ON-switch card
  count with a temp `OPENJARVIS_CONFIG_DIR` (baseline reproduces DEF-061: first ON => 202 "one card
  is already waiting", 0 cards; live config untouched). Checks 1,2,4,5 are GET-only.
- **Q3 cache-cap plan** (`D:\jarvis-scratch\WAVE14-CACHE-CAP-2026-11-09\`): mechanism verified,
  before baseline captured, restart one-liners, measurement protocol, honest limits. The Lead's
  `q3-apply-cap.ps1` is the single live-write helper; it backs both files up first and refuses if
  the anchor is not exactly once or the cap line already exists.

## 4. Validations run by the Lead after integration

1. `check-parse-all.ps1` under Windows PowerShell 5.1.26100.9711: **PARSE OK for both**
   `deploy-gates-wave14.ps1` and `post-deploy-checks-wave14.ps1` (0 errors, exit 0).
2. `deploy-gates-wave14.ps1` constants read back: `$FrozenHead`/`$Ref`/`$FrozenTree` = the frozen
   refs, `$Pr` 1219, `$PrevPr` 1218, floors 0.2.443 / 4042, `$expectedShipped` 335; the remaining
   `2dc899f` strings are comments that record the move only.
3. `verify_wave14_live.py`: `EXPECTED_SHA` = frozen head, `py_compile` exit 0, `--help` prints the
   same 6 flags, no `2dc899f`/`d98c6519` left.
4. `post-deploy-checks-wave14.ps1` dry run against the lane's fake live root, with the real frozen
   worktree: **19 PASS / 1 FAIL / 0 BLOCKED / 2 WARN**; the 1 FAIL is `P0-MIXED` only because the
   dry run reads the REAL installed EXE (0.2.443) while the fake VERSION is 0.2.444 - a dry-run
   artefact; the first run also failed W14-EDIT on the old 96,571-byte hud-edit copy, and updating
   that fake copy to the frozen head's 96,595-byte blob made it PASS. On the real deploy the EXE is
   installed first (0.2.444), so the expected shape is 20/0/0/2 exit 0.
5. No `CURRENT-RUN.txt` in this folder: every gate run tonight creates a fresh `run-<stamp>`.

## 5. Order of operations after the merge (authority: `WAVE14-RUNBOOK-2026-11-10.md`)

0B -> 0C -> 0D -> 0G -> 0H -> insurance -> repair -> be -> [wait releases] -> 0E -> 0F -> stop ->
stopped -> apply -> quotes -> reseal -> toml -> install-desktop -> install-phone -> restart ->
identity -> probes -> postdeploy -> preflight -> awareness -> verify-wave8 -> rollback.

Then, on the deployed 0.2.444 and in this order: probes rows 1/2/4/5 -> the ONE cold F2 turn ->
Q3 (backups, two one-line live edits, lane restarts, `measure.ps1` receipts, startup env-map proof,
one documented second app restart to load the edited 11450 module) -> receipts -> relay.

## 6. Standing rules kept

No merge by this session (the paired session merges), no push, no branch/worktree move of the PR,
no live write before the gates, no hand edit of a live file except the owner-approved Q3 change
(backed up first), no token printed, owner TOML never touched, bulk evidence on D:.
