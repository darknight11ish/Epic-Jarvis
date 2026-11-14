# WAVE-14 GATE DIFF NOTES — wave-13 packet -> wave-14 packet

Packet: `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\WAVE14-DEPLOY-2026-11-09\deploy-gates-wave14.ps1`
Base: wave-13 packet, 976 lines, 63,321 bytes, SHA256 `3F50191C565CE5117666AB0434497C0FC0773BB19C26590BAE65081DFEA35983`
New: **1,116 lines, 74,012 bytes, SHA256 `C98BA1BA69BAB67FE31189835DB1AC400C98AF3FBF93D508E2AEEFF562C19D9C`**, 36 `# W14:` markers
PS 5.1 parse: **PARSE OK, 0 errors, exit 0** (`check-parse.ps1`, log `parse-check-5.1.txt`, `powershell.exe 5.1.26100.9711`)

## 0. THE PIN MOVED — read this first

`frozen-ref.txt` in this folder is the authority and it says the PR #1219 head moved during preparation:

| | head | tree |
|---|---|---|
| **frozen (this packet)** | **`24a3fc9b1da913556b7ee1585d46538830cb0b80`** | **`ad1de9e15f5ad14b35a1d7c9cda31d2eaa54e9c8`** |
| previous (the brief's value) | `2dc899fdbd23cffce498449858b1eb7d3c153c0b` | `d98c6519eef3b33e27551cdfeb17496200e87030` |
| base origin/main (wave-13 merge) | `85e9e85005d175a9a5217ff1a3650cc51947cb20` | `46216eac…` |

The move is one commit, `fix(ci): the served hud-edit copy and its base copy follow the editor comment` (+10/-8 in `backend/static/hud-edit.js` and `jarvis-backend/hud-edit.js`; 129 files changed either way). **`tools/reconcile_live_backend.py` is byte-identical at both heads**, so every 0H number is unchanged — and that was measured, not assumed: another session ran the read-only dry run at both heads and the two receipts are identical line for line (`0H-PREVIEW-wave14.txt`, `0H-PREVIEW-wave14-frozen.txt`, summarised in `EXPECTATIONS-0H.md`).

**Re-read `frozen-ref.txt` at the start of the run.** If it names a newer head again, edit the two constants (`$FrozenHead`, `$FrozenTree`) and `$Ref` in the packet — they are the only pin in the file. The derived numbers below do not change for a comment-only commit; re-run 0H after the merge regardless.

I executed nothing against the live PC: no gate, no branch/worktree move, no merge. The 0H figures below are confirmed by the other session's read-only receipts in this folder.

---

## 1. Every changed line / constant (old -> new -> why)

| # | Where | Old (wave 13) | New (wave 14) | Why |
|---|---|---|---|---|
| 1 | header block (lines 1-47) | wave-13 title, origin, run commands, `DEPLOY-PLAN-WAVE13.md` | wave-14 title, origin sha of the wave-13 packet, wave-14 run commands, `GATE-DIFF-NOTES.md`, the predicted-numbers block, the head-move note | the packet must name itself and its authority; the wave-13 ledger is kept verbatim below it as history (line ~49) |
| 2 | `$scratch` | `…\WAVE13-DEPLOY-2026-11-09` | `…\WAVE14-DEPLOY-2026-11-09` | run folder, `CURRENT-RUN.txt`, artifacts and evidence all live in the new wave folder |
| 3 | `$Pr` | `1218` | `1219` | wave-14 PR |
| 4 | `$PrevPr` | `1217` | `1218` | previous wave PR; must be CLOSED/MERGED, not OPEN |
| 5 | `$PhoneFloor` | `4035` | `4042` | live phone is 0.2.4042; new APK must be newer |
| 6 | `$DesktopFloor` | `'0.2.442'` | `'0.2.443'` | live desktop/backend is 0.2.443; new build must be newer |
| 7 | `$FrozenHead` | `32ba251d935d04c22bb83c9e0a6005e08d40b500` | `24a3fc9b1da913556b7ee1585d46538830cb0b80` | PR #1219 head (moved once from 2dc899fdb; `frozen-ref.txt`) |
| 8 | `$FrozenTree` | `46216eac7f1b0aedcbc8bf5dc7841aa6e76574a0` | `ad1de9e15f5ad14b35a1d7c9cda31d2eaa54e9c8` | `git rev-parse 24a3fc9b1^{tree}`, verified |
| 9 | `$Ref` default | `32ba251d9…` | `24a3fc9…` | 0B may re-pin only to a main whose tree equals the frozen tree |
| 10 | `$PreflightDir` | `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09` | `…\WAVE14-PREFLIGHT-2026-11-09` | deliverable candidates for wave 14 |
| 11 | `$PostDeployScript` / `$PostDeployCandidates` | `post-deploy-checks-wave13.ps1` | `post-deploy-checks-wave14.ps1` | the wave-13 script pins wave-13 sha/floors; it must not grade wave 14 |
| 12 | `$AcceptanceScripts` | `verify_wave13_live.py` paths | `verify_wave14_live.py` paths (4 candidates, incl. `D:\jarvis-scratch\WAVE14-VERIFIER-2026-11-09\`) | the wave-14 verifier exists there |
| 13 | `$RegressionScripts` | — (did not exist) | wave-13 verifier paths | wave 13's acceptance is now a regression half |
| 14 | `$expectedShipped` | `334` | `335` | + `jarvis_project_read.py` |
| 15 | 0B comment + GO text | `#1218`, `frozen 7d892e27 tree`, `Wave-13 merge (PR #1218)` | `#1219`, `frozen 24a3fc9b1 tree`, `Wave-14 merge (PR #1219)` | the wave-13 text was already stale (`7d892e27` was a retired head); code compares `$FrozenTree`, only the text moves |
| 16 | 0C comment | `#1217 is MERGED as d6df4022` | `#1218 is MERGED as 85e9e850` | previous PR state |
| 17 | 0D waiver title string | `(Wave-13 run, …)` | `(Wave-14 run, …)` | evidence file must name this run |
| 18 | 0E GO text | `Wave 9/11/12/13` | `Wave 9/11/12/13/14` | no runtime-tree waiver in this wave either |
| 19 | 0F neutral copy | `jarvis-desktop-wave13-setup.exe` | `jarvis-desktop-wave14-setup.exe` | run-scoped name |
| 20 | 0H expectation block | 334 = 1+20+313; 234 = 233+1; insert MUST be skill-scan-wiring; 31/1/26; pycache 229 note; `wrote 23`; backups unspecified | 335 = 1+21+313; 234 = 232+2; inserts ONLY auto-learn->hud (3 regions) and ->extract (2 regions); 32/0/26; PLANNED = 24 + pycache; VERSION unchanged 0.2.443; backups 27->27; `wrote 25` | measured at the frozen head, see §2 |
| 21 | 0H STOP text | "any 'to insert' row that is NOT the skill-scan-wiring one" | "any 'to insert' row that is NOT one of the two auto-learn rows" | skill-scan is now already present |
| 22 | `insurance` backup folder | `D:\jarvis-rehearsal\predeploy-wave13-<stamp>` | `…predeploy-wave14-<stamp>` | separate insurance copy per wave |
| 23 | `apply` GO/STOP text | `wrote 23` = 1+20+ONE insert+1; creator-mode added as its own step | `wrote 25` = 1+21+TWO staged files+1; 0 plug-ins to add; BACKUP creates the 28th folder | see §2; the wave-13 apply measured 23 with this exact formula |
| 24 | `reseal` GO text | `VERIFY 0 of 334`, PARTIAL names ONLY gate/hud/skills | `VERIFY 0 of 335`, names TO MEASURE from the 5-name allowed set | wave 14 adds a SHIPPED module and inserts into `jarvis_extract.py` |
| 25 | `toml` GO text | "repository copy changed in wave 13" | same history + "did not change in wave 14 either" | `backend/jarvis-framework.toml` is not in the wave-14 diff |
| 26 | `install-desktop` launch copy | `setup-wave13.exe` | `setup-wave14.exe` | D: launch copy name |
| 27 | `preflight` output file | `preflight-after-wave13.txt` | `preflight-after-wave14.txt` (both write and grep) | run-scoped evidence |
| 28 | `preflight` GO text | wave-12 35/9/3/5, 9 FAILs | TO MEASURE; wave-13 measured 35/10/3/5 and its 10 FAILs named, incl. the auto-learn row | wave 13's own numbers, and wave 14 may flip two rows |
| 29 | `awareness` GO text | Wave-9 3 BLOCKED rows | TO MEASURE; wave-13 measured 24/1/0, FAIL = `cap-cloud-escalation` | measured baseline, not remembered |
| 30 | `postdeploy` comment, args, GO text | wave-13 script; 0.2.442/0.2.4035 floors; only `-Transcript`/`-PhoneVersion`; wave-13 14/1/0/3 prose | wave-14 script (45,022 B, 22 rows); passes `-FrozenSha $FrozenHead -FrozenTree $FrozenTree` and `-Worktree` (a local tree whose HEAD tree is the frozen tree); expects 0 FAIL / 2 WARN by design (A-SIZES, F5-1) / exit 0; MF-1 and W12-2 flip to PASS | the checks script landed after the draft and its own defaults pin the PREVIOUS head |
| 31 | `verify-wave8` dst + json/txt names | `verify_wave8_wave13.py`, `12-verify-wave8-wave13.*` | `verify_wave8_wave14.py`, `12-verify-wave8-wave14.*` | run-scoped evidence |
| 32 | `verify-wave8` comment | grep at `43b925f6` | grep re-run at the frozen head (still exit 1, nothing) | expectation re-derived, still 26/1 |
| 33 | `verify-wave8` GO text | `DEPLOY-PLAN-WAVE13.md`, wave-13 result doc | `GATE-DIFF-NOTES.md`, wave-14 result doc | authority |
| 34 | `probes` gate | 2 scripts (wave-11 + wave-13), STOP if wave-13 verifier absent | 3 scripts (wave-11 + wave-13 regression + wave-14 acceptance); STOP if the wave-14 verifier is absent, if its `EXPECTED_SHA` is not this run's frozen head, or if its worktree cannot resolve that commit | a green regression is not wave-14 acceptance; see §3 |
| 35 | `Show-Gates` | wave-13 title; reseal `PARTIAL x3`; phone floor 0.2.4035; probes `verify_wave13_live.py --ref`; postdeploy "print path" | wave-14 title; PARTIAL names TO MEASURE; 0.2.4042; three scripts, NO `--ref`; postdeploy RUNS it | the wave-13 `--ref` hint was already wrong (argparse exit 2) and "print path" was already superseded |
| 36 | `$NewDesktopVersion` / `$NewPhoneVersion` examples | `0.2.443` / `0.2.4036` | `0.2.444` / `0.2.4044` | both are still read from the releases at 0E, never hard-coded |

`repair`, `be`, `stop`, `stopped`, `quotes`, `identity` are byte-identical to wave 13. `jarvis_gate.py` is not touched by wave 14, so `repair`'s remembered `~220771 B / B410327D…` still describes the live file (wave-13 preflight measured `b410327d now`).

---

## 2. The numbers, and how each was derived (then measured)

The calibration: applying the same method to the wave-13 tree reproduces wave 13's **measured** 0H output exactly (`add 1 + update 20 + unchanged 313`). Then a read-only dry run at **24a3fc9** confirmed every wave-14 number (`0H-PREVIEW-wave14-frozen.txt`, produced by the delegated 0H session; the live folder was not written to: VERSION 0.2.443 and 27 backup folders before and after).

### SHIPPED 335 = add 1 + update 21 + unchanged 313  — MEASURED
- `$SHIPPED` at 24a3fc9 parses to **335** entries; at 85e9e85 to **334**; the only difference is `jarvis_project_read.py` (`backend/_where.py` and `scripts/apply-patches.ps1` both add it, same position above `jarvis_bench.py`).
- Changed shipped modules between the two trees: **22** — `jarvis-self-code.json, jarvis_agent.py, jarvis_asks_first.py, jarvis_bench.py, jarvis_big_coder.py, jarvis_claims.py, jarvis_feature_catalogue.py, jarvis_hud.html, jarvis_menus.py, jarvis_model_knowledge.py, jarvis_model_lanes.py, jarvis_model_recommender.py, jarvis_model_resources.py, jarvis_presets.py, jarvis_project_read.py, jarvis_reach.py, jarvis_recent_changes.py, jarvis_settings_registry.py, jarvis_setup.py, jarvis_tool_profiles.py, jarvis_vault_organizer.py, static/hud-edit.js`.
- One of the 22 is the new file -> **add 1, update 21, unchanged 313**. `hud-edit.js` is still a SHIPPED *update* at the moved head (the +10/-8 comment does not change its class).
- Live is the wave-13 repo byte-for-byte for shipped files: the wave-13 reseal printed `VERIFY : 0 of 334 shipped file(s) still differ from the repository` (`run-20261109-164537\5-reseal.txt`). `jarvis_hud.py`, `jarvis_extract.py`, `jarvis_gate.py`, `jarvis_skills.py` are **not** in `$SHIPPED` (checked), so they are delta/gate files, not update rows.

### HUD DELTAS 234 checked = 232 already present + 2 to insert  — MEASURED
- The count is **patch x patched-file pairs** (`plan_deltas` appends one `DeltaAction` per patch/file with added lines), so it does not change when a DELTA_TABLE entry is added: the wave-14 stack is unchanged except `model-recommendations.patch` (a comment rewrite), and **no patch was added**. Wave 13 measured 234. -> **234**.
- Wave 13 measured `233 already + 1 insert`, and the 1 insert was `skill-scan-wiring.patch -> jarvis_skills.py (5 hunk(s))` (`run-20261109-164537\4-apply.txt`), which the wave-13 apply **wrote** (`wrote 23`). So at wave 14 that row is **already present**: 233 - 1 = 232, and an insert row for `jarvis_skills.py` now means the live file lost the wave-13 insert -> STOP.
- `auto-learn.patch` was one of wave 13's 233 "already" rows via the loose fallback (the D-1 comment records `129 of its 144` distinctive HUD lines present -> ALREADY_PRESENT, and wave 13 never carried the missing hunks). The wave-14 tree adds a DELTA_TABLE entry with **2 patch/file rows** (3 HUD regions + 2 extract regions); both were counted in the 234 already, so they leave "already" and become **insert**. -> **232 + 2**.
- Expected insert lines (the tool's own `_summ` shape):
  `auto-learn.patch -> jarvis_hud.py (3 region(s))`
  `auto-learn.patch -> jarvis_extract.py (2 region(s))`

### READY PLUG-INS 32 present / 0 to add / 26 already wired  — MEASURED
- Wave 13 measured `31 present, 1 to add (creator-mode), 26 wired` = 58 ready plugins.
- The wave-13 apply printed `PASS  plugin creator-mode`, so creator-mode exists in the live folder now: **32 present, 0 to add, 26 wired** (the `hud_wired` bucket is "ready plugin whose `install(` the live HUD calls", independent of the live folder; wave 14 changed no `plugins/ready` files).
- A non-zero "to add" here is a STOP: it means the wave-13 plugin step did not stick.

### 0H PLANNED = 24 + pycache  — MEASURED (255 at pycache 231)
`changes = add + update + insert + beside/version + pycache` = 1 + 21 + 2 + 0 + pycache. In the dry run the release markers are 0 because VERSION is read from the **installed desktop** (0.2.443) and equals the live VERSION -> `VERSION: unchanged 0.2.443`; `requirements.lock` and `quiz_grader_cases.json` are unchanged in wave 14. pycache is a live measurement (wave 13 measured 236/237; the 24a3fc9 dry run measured **231**, because the running app wrote a `.pyc` mid-session) and is **never predicted** — the gate prints 24 + N.

### apply: wrote 25  — DERIVED, confirmed by the sibling's arithmetic
`wrote = apply_shipped(add+update) + apply_deltas(distinct staged files) + released` = (1 + 21) + 2 + 1 = **25**. Wave 13 is the same formula: (1 + 20) + 1 + 1 = 23, measured. Apply's own PLANNED = 1 + 21 + 2 + 1 + pycache = **25 + pycache**. `creator-mode` is no longer an extra plugin step (0 to add).

### backup folders 27 -> 27, then 28
The live folder holds **27** `_jarvis-deploy-backup-tool-*` folders now (wave-13 apply created the 27th, `_jarvis-deploy-backup-tool-20261109-170634`; the 0H session re-checked 27 before and after its dry runs). 0H must read `backupFolders=27->27`; the apply's `BACKUP:` line creates the 28th. 0H only prints this (wave-13 behaviour: print, operator judges), so the printed expectation is the check.

### reseal VERIFY 0 of 335
`FILES (334 entries in $SHIPPED…)` becomes 335. Wave 13 printed `VERIFY : 0 of 334` with `RESULT: PARTIAL` naming exactly `jarvis_gate.py, jarvis_hud.py, jarvis_skills.py`.

### verify-wave8: 26/1 again, or 27/0
`git grep -i 'coding preset' 24a3fc9 -- backend/jarvis_recent_changes.py` -> **exit 1, no match** (same at 2dc899f), same as wave 13's check at `43b925f6`. The `self-update-history` row still cannot name "Coding preset", so the SUMMARY is 26/1 with that single FAIL (or a clean 27/0 if the row's other needle now satisfies it). Nothing else is re-baselined.

### The auto-learn needles/regions the deploy will insert (task item 4)
`tools/reconcile_live_backend.py` at the frozen head **does** carry the auto-learn DELTA_TABLE entry (commit `a69d55426`, +63 lines, the D-1 fix; the tool is byte-identical at 2dc899f and 24a3fc9). Exact entry:

- patch key `auto-learn.patch`; HUD entry-level probes (all 4 present => "already", and live holds 0 `/api/memory/fault`):
  1. `                    "/api/memory/fault"):`
  2. `                     "/api/memory/learning/paraphrase", "/api/memory/fault/retry"):`
  3. `                code, out = jarvis_auto_learn.handle_post(`
  4. `                    model=_extract_model(), ollama=getattr(jarvis_extract, "OLLAMA", None))`
- HUD regions (OLD block replaced by NEW block; each old block must appear exactly once, each region skipped if its probe is present):
  | region new file | replaces | probe | size old -> new |
  |---|---|---|---|
  | `auto-learn-hud-get-new.txt` | `auto-learn-hud-get-old.txt` | `                    "/api/memory/fault"):` | 7 lines/503 B -> 11/744 |
  | `auto-learn-hud-post-new.txt` | `auto-learn-hud-post-old.txt` | `                     "/api/memory/learning/paraphrase", "/api/memory/fault/retry"):` | 2/141 -> 2/168 |
  | `auto-learn-hud-postcall-new.txt` | `auto-learn-hud-postcall-old.txt` | `                    model=_extract_model(), ollama=getattr(jarvis_extract, "OLLAMA", None))` | 1/71 -> 8/560 |
- extract entry-level probes: `        return _intake_fault_visible(_rows)` and `def _intake_fault_visible(rows: list) -> list:`
- extract regions:
  | `auto-learn-extract-intake-new.txt` | `…-intake-old.txt` | `        return _intake_fault_visible(_rows)` | 3/223 -> 8/566 |
  | `auto-learn-extract-eof-new.txt` | `…-eof-old.txt` | `def _intake_fault_visible(rows: list) -> list:` | 2/91 -> 15/719 |

`hunks: True` is deliberately **not** used (hunk 8's pre-image still appears once after the live dispatch block, so replaying hunks would insert a second copy - the tool's own comment records this). The sibling's D-1 test (`0H-d1-test.txt`, `PASSED=37 FAILED=0`) measured every region pre-image exactly once in a reconstructed live shape and proved a second plan sees both files ALREADY_PRESENT. If a region's old block appears 0 or >1 times in the REAL live file, the tool **refuses** (exit 2): that is a STOP to diagnose, not a retry.

---

## 3. Gates whose wave-13 assumption no longer holds

1. **0H insert rows and apply arithmetic.** Wave 13's single insert (skill-scan -> `jarvis_skills.py`) is now already present; the new inserts are the two auto-learn regions. Wave 13's "wrote 23" is now "wrote 25". The plugin step is gone (0 to add). Read the tool's own `SHIPPED (` / `HUD DELTAS (` / `PLANNED CHANGES:` / `wrote N` lines and compare with §2; the 24a3fc9 receipt is the reference.
2. **`reseal` PARTIAL names.** The three names are no longer guaranteed. Allowed set: `jarvis_gate.py, jarvis_hud.py, jarvis_skills.py, jarvis_extract.py, jarvis_project_read.py`. Any other name, or a VERIFY count that is not 335, is a STOP to diagnose. This is the one place the packet deliberately prints "TO MEASURE" rather than a number.
3. **`probes` - three scripts.** Wave 13's acceptance script grades wave-13 rows only; using it as wave 14's acceptance would be the same false pass wave 13 refused when it refused to grade with the wave-11 script. So the gate runs wave-11 (regression), the wave-13 verifier (regression), and `verify_wave14_live.py` (acceptance).
   - The wave-14 verifier was first inspected as a 67,597 B draft that declared **16 rows** but dispatched only wave 13's 13 (`MEM-3`, `PRJ-1`, `PRE-1` had no check and would have come out BLOCKED, exit 1). The checks owner **completed it** while this packet was being written: the current file is **84,080 B**, `EXPECTED_SHA = 24a3fc9…`, and all 16 rows dispatch. Expected SUMMARY: **12 PASS / 0 FAIL / 3 BLOCKED / 1 PARTIAL, exit 0**, where BLOCKED = CR-4 and F2-3 (guarded, not run) and W12-3 (structural), PARTIAL = W12-2 by the spec, and MF-2 should now PASS (the D-1 deploy stages the fault routes). **Re-read the file's size and `EXPECTED_SHA` at run time** - the gate reads the SHA itself and stops if it is not this run's frozen head, or if the verifier's worktree cannot resolve that commit. The worktree's checked-out HEAD (`wt`, at 2dc899f) is not judged: the verifier reads sizes by `git cat-file -s <sha>:path` and reports its HEAD without grading it.
   - The wave-13 verifier stays a regression, with wave 13's measured 8 PASS / 1 FAIL (MF-2) / 3 BLOCKED / 1 PARTIAL; MF-2 should flip to PASS after this deploy.
4. **`postdeploy`.** `post-deploy-checks-wave14.ps1` landed in this folder (45,022 B, 22 rows) after the packet draft. Its own defaults pin the PREVIOUS head (`-FrozenSha 2dc899f`, `-FrozenTree d98c6519`) and its default worktree is `wt` (2dc899f), so this gate now passes `-FrozenSha $FrozenHead -FrozenTree $FrozenTree` and `-Worktree <a local tree whose HEAD tree is the frozen tree>` (the merge-deploy tree, else `wt-frozen`, else `wt`). Expected, from `POSTDEPLOY-EXPECT-WAVE14.md`: **22 rows, 0 FAIL, 2 WARN by design (A-SIZES and F5-1), exit 0** - the first wave whose post-deploy checks exit 0; MF-1 and W12-2 both flip to PASS. TO MEASURE: the printed SUMMARY, the P0-SHA row (PASS at this ref), and P0-PHONE. A FAIL, or a 3rd WARN, is a STOP to diagnose. If no local worktree matches the frozen tree, the script falls back to its own default and P0-SHA may WARN - record it; a WARN is never a pass.
5. **`preflight`.** Wave 13 measured 35 pass / 10 fail / 3 warn / 5 skipped, and one of the 10 FAILs was `only part of auto-learn.patch is in jarvis_extract.py (52 of 67 lines)` - exactly the D-1 gap wave 14 fixes. After the apply that row should flip or change shape, and `model-recommendations.patch` changed in wave 14 too, so the totals will differ. The gate prints the wave-13 row names and says TO MEASURE the totals; compare row names, never a total.
6. **`awareness`.** Wave 13 measured 24 passed / 1 failed / 0 blocked, exit 1, the one FAIL being the standing `cap-cloud-escalation` row. Wave 14 did not fix that capability: same shape expected, but TO MEASURE; a new FAIL or any BLOCKED row is a STOP.
7. **`verify-wave8`.** Still 26/1 on `self-update-history` (grep re-run at the frozen head still finds nothing) - but the row reads the **new** desktop version (the packet re-baselines the `0.2.439` literal to `$NewDesktopVersion`, expected 0.2.444) and the new phone version, so a 27/0 is also a GO; anything else is a STOP.
8. **Backup folder count.** 27 before the apply, 28 after - not 26. 0H must print `27->27`; the apply's BACKUP line names the 28th folder, which the rollback gate then prints.
9. **Release floors only.** The actual new versions are never hard-coded: 0E reads `desktop-latest` / `client-latest`. Expected (not enforced): desktop `0.2.444` (desktop-release run 444) and phone `0.2.<jarvis-client main-push run_number>`; wave 13's main run 4042 -> 0.2.4042, so a wave-14 main run 4043/4044 gives 0.2.4043/0.2.4044. The gate's floors are 0.2.443 and 4042.

---

## 4. What could not be computed (and how the operator measures it)

| Item | Why it cannot be computed without the live PC | How to measure |
|---|---|---|
| `reseal` PARTIAL names | depends on the live `_jarvis-state.json` manifest and the bytes the apply writes | read `5-reseal.txt`: `VERIFY : 0 of 335`, `RESULT: PARTIAL`, and the names after it; allowed set in §3.2 |
| `pycache` count, and every PLANNED total | a live directory scan | read `0H-dryrun.txt`: `PYCACHE: N stale .pyc file(s)` and `PLANNED CHANGES: 24+N …`; at apply `PLANNED CHANGES: 25+N` and `wrote 25` |
| `preflight` totals and row set | a live comparison of ~178 patches and the live folder | read `preflight-after-wave14.txt`; compare row NAMES with the wave-13 set in §3.5 |
| `awareness` totals | live runtime state | read `11-awareness-sanity.txt` SUMMARY and BLOCKED rows |
| `postdeploy` SUMMARY | live bytes/versions; the script pins the previous head by default | read `10b2-post-checks.txt`; expected 0 FAIL / 2 WARN / exit 0 per §3.4 |
| wave-14 verifier SUMMARY | depends on live server state | read `10-probes-wave14.txt`; expected 12/0/3/1, exit 0 per §3.3 |
| actual new versions | releases do not exist until CI cuts them | Gate 0E reads them from the release names; floors 0.2.443 / 4042 |

Everything else in the packet is either unchanged from wave 13 or one of the derived/measured numbers in §2.

---

## 5. Evidence trail (read-only)

- `frozen-ref.txt` — the authority for the pin (frozenHead 24a3fc9 / frozenTree ad1de9e1; prevHead 2dc899f; baseOriginMain 85e9e85; floors; backupFoldersBefore 27).
- `git cat-file -t 24a3fc9` -> commit; `git rev-parse 24a3fc9^{tree}` -> `ad1de9e15f5ad14b35a1d7c9cda31d2eaa54e9c8`; `git merge-base --is-ancestor 2dc899f 24a3fc9` -> exit 0; the delta is `backend/static/hud-edit.js` + `jarvis-backend/hud-edit.js` (+10/-8).
- `git diff --name-status 85e9e85 24a3fc9` -> **129 changed files**; `git diff --numstat` -> **6,722 insertions / 657 deletions** (at 2dc899f it was 6,720 / 657; the move adds the +10/-8 hud-edit comment).
- `git diff 85e9e85 24a3fc9 -- tools/reconcile_live_backend.py` -> +63 lines: the ten `AUTOLEARN_*_FILE` constants and the `"auto-learn.patch"` DELTA_TABLE entry, nothing else. Byte-identical at 2dc899f (empty diff).
- `git show 24a3fc9:backend/_where.py` parsed with `ast` -> 335 entries (`shipped-w14.txt`); at 85e9e85 -> 334 (`shipped-w13.txt`).
- `git grep -in 'coding preset' 24a3fc9 -- backend/jarvis_recent_changes.py` -> exit 1.
- **Read-only 0H measurement at the frozen head** (by the delegated 0H session, cited, not run by me): `0H-PREVIEW-wave14-frozen.txt` -> 335 = 1+21+313; 234 = 232+2 with the exact two insert rows; VERSION unchanged 0.2.443; PYCACHE 231; PLANNED 255 = 24+231; READY PLUG-INS 32/0/26. `EXPECTATIONS-0H.md` tabulates it and records that the live folder was not written (VERSION still 0.2.443, 27 backup folders before and after). `0H-PREVIEW-wave14.txt` (at prevHead 2dc899f) is identical after stripping the `repo:`/`ref :` lines.
- `0H-d1-test.txt` -> `PASSED=37 FAILED=0`: the D-1 entry's five region pre-images each appear exactly once in a reconstructed live shape, both files are staged with no refusal, the staged files compile, and a second plan sees both ALREADY_PRESENT.
- Wave-13 measured evidence (read-only): `run-20261109-164537\0H-dryrun.txt` (334 = 1+20+313; 234 = 233+1; 31/1/26; PYCACHE 236), `4-apply.txt` (`to insert: 1  skill-scan-wiring.patch -> jarvis_skills.py (5 hunk(s))`; `VERSION: wrote 0.2.443`; `wrote 23`; `PASS plugin creator-mode`), `5-reseal.txt` (`VERIFY : 0 of 334`, PARTIAL 3 names), `preflight-after-wave13.txt` (the 10 FAIL rows incl. the auto-learn 52/67 row), `WAVE13-RESULT-2026-11-09.md` (preflight 35/10/3/5, awareness 24/1/0, postdeploy 14/1/0/3, verify-wave8 26/1, backups 26->27).
- Wave-14 verifier: `D:\jarvis-scratch\WAVE14-VERIFIER-2026-11-09\verify_wave14_live.py` — current file 84,080 B, `EXPECTED_SHA` 24a3fc9, 16 `ROW_SPECS` rows and 16 dispatch branches (`check_mem3`/`check_prj1`/`check_pre1` present); the earlier 67,597 B draft had 3 undispatched rows. Read-only inspection.
- Post-deploy checks: `post-deploy-checks-wave14.ps1` in this folder, 45,022 B, 22 rows, `param()` carries `-Worktree`, `-FrozenSha` (default 2dc899f), `-FrozenTree` (default d98c6519), `-VersionFloor 0.2.443`, `-PhoneFloor 0.2.4042`, `-PhoneVersion`, `-Transcript`; `POSTDEPLOY-EXPECT-WAVE14.md` lists the 22 expected rows (0 FAIL, A-SIZES/F5-1 WARN, MF-1/W12-2 PASS flips).
- Worktrees, checked read-only: `wt` HEAD = 2dc899f (clean); `wt-frozen` HEAD = 24a3fc9 (clean). `git -C wt rev-parse --verify --quiet 24a3fc9^{commit}` resolves (same object DB), which is what the verifier needs.

No live file was read or written by me, no gate was executed, no branch or worktree was created or moved, nothing was merged or pushed.
