# Real-run runbook - wave 13, post-merge deploy (2026-11-09)

Written 15:55 PT while CI run `42720784442` finishes. This is the ORDER to run the
existing packet in; it does not replace `DEPLOY-PLAN-WAVE13.md`, and the gate script is
NOT edited (976 lines / 63,321 B / sha256 `3F50191C…A35983`, PS 5.1 parse 0 errors /
5,345 tokens). Evidence of the rehearsal and its two known defects:
`GATE-REHEARSAL-NOTES-2026-11-09.md`.

## 0. Preconditions

- All SEVEN required checks SUCCESS on PR #1218 head `32ba251d9` (watcher:
  `watch-required-7.ps1`, log `ci-watch-7.log`). Merge only on 7/7 - never `--admin`,
  never squash, merge commit only.
- PR #1218 OPEN and MERGEABLE; `origin/main` = `d6df4022` and an ancestor of the branch
  head, so the merge commit's tree MUST be the frozen tree
  `46216eac7f1b0aedcbc8bf5dc7841aa6e76574a0`.
- The frozen integration worktree `.dsh-scratch\WAVE13-INTEGRATION-2026-11-09\wt` stays
  at `32ba251d9` and clean: the post-deploy checks and the verifier read it (their
  `-Worktree` default), so moving it would break their P0-SHA / A-SIZES rows.
- Fresh run folder: delete `CURRENT-RUN.txt` only (the old `run-20261109-1540` and its
  0H evidence stay on disk). The first gate then creates a new run folder; no cached run
  vars can exist in it.

## 1. Merge (Lead only)

Guards first: `gh pr view 1218 --json headRefOid` must be `32ba251d935d04c22bb83c9e0a6005e08d40b500`,
and `gh pr checks 1218 --required` must print exactly the 7 required names, every one `pass`.
Then, in order:

```
gh pr merge 1218 -R darknight11ish/Epic-Jarvis --merge
gh pr view 1218 -R darknight11ish/Epic-Jarvis --json state,mergeCommit,mergedAt
git -C "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\WAVE13-INTEGRATION-2026-11-09\wt" fetch origin main
git -C "...\wt" rev-parse origin/main
git -C "...\wt" rev-parse "origin/main^{tree}"
```

Record the merge sha and CONFIRM the tree is `46216eac7f1b0aedcbc8bf5dc7841aa6e76574a0` before
anything else - a different tree means main moved and the deploy must not start (Gate 0B would
stop for the same reason). Never `--admin`, never `--squash`, never force; pushing to the PR
branch cancels its run. Run **Gate 0B** next: it accepts origin/main only when that tree matches
and writes `ref.txt` with the merge sha.

Immediately after the merge, start the two background watchers so the release wait overlaps the
merge bookkeeping:
`powershell -NoProfile -File D:\jarvis-scratch\WAVE13-RELEASE-WATCH-2026-11-09\watch_post_merge.ps1 -TimeoutMinutes 45`
and `watch-main-ci.ps1 -MergeSha <merge>` (records the deferred `main` ci.yml run for 0D's waiver).

## 2. Releases (both must name the merge sha)

A push to main starts the desktop release workflow and the phone client workflow. Watch:

```
gh release view desktop-latest -R darknight11ish/Epic-Jarvis --json name,targetCommitish
gh release view client-latest  -R darknight11ish/Epic-Jarvis --json name,targetCommitish
```

Expected next versions: desktop `0.2.443` (from the desktop release run number), phone
`0.2.4042` (from the CI run number) - read them from the release names, never assume.
Gate 0E needs BOTH `targetCommitish` == merge sha, then Gate 0F downloads and verifies
both assets. Do NOT run 0F before a 0E GO (it otherwise downloads 35 MB then prints the
misleading `no setup asset for version  `).

## 3. Gate sequence (one process per gate, in this order)

| # | gate | expected GO line / note |
|---|---|---|
| 1 | 0B | `ref=<merge sha>`, both trees `46216eac…`, ref.txt written |
| 2 | 0C | `#1218 MERGED as <sha7> and is an ancestor of $Ref; #1217 finished` |
| 3 | 0D | same-tree waiver GO: `prRun=42720784442 7/7 required green on tree 46216eac…`; waiver file in run folder. The main-branch run on the merge sha may still be running - the waiver defers it; re-check the main run before the final report |
| 4 | 0E | both releases name the merge sha; `desktopVersion=0.2.443 phoneVersion=0.2.4042`; writes release-vars.json |
| 5 | 0F | assets verified, neutral setup copy made; writes assets.json |
| 6 | 0G | HEAD=$Ref, trackedChanges=0; run it AFTER 0B moved the deploy tree (reflog window is 5 min) |
| 7 | 0H | read-only dry run: SHIPPED 334 = 1+20+313; HUD DELTAS 234 (1 to insert); READY PLUG-INS 31 present / 1 to add / 26 wired; PYCACHE live (~236); PLANNED 258; dryRunExit 0; VERSION unchanged; backups 26->26 |
| 8 | insurance | D: insurance copy written; it must show program\VERSION = 0.2.442 (wave-12 state) |
| 9 | repair | 6 real repair probes, exactly once |
| 10 | be | LISTENING on :4719 (loopback + tailnet), HTTP 403 |
| 11 | stop | the ONLY authorised stop; proves it killed the tree |
| 12 | stopped | LISTENING=0, no local ESTABLISHED, HTTP refused |
| 13 | apply | `JARVIS_DESKTOP_EXE` = the NEW installer; expect `wrote 23`, VERSION -> 0.2.443, and the 27th `_jarvis-deploy-backup-tool-*` folder (~17 MB). PLANNED at apply is 259 (22 non-pycache + 236 pycache measured live + 1 VERSION); the pycache count is a live measurement, so compare `wrote 23`, not PLANNED |
| 14 | quotes | quotes corpus hash unchanged, repair probes survive |
| 15 | reseal | `VERIFY 0 of 334` + `PARTIAL x3` (by design) |
| 16 | toml | owner TOML untouched: 58,409 B, sha256 `9C6CDF76…C92D97` |
| 17 | install-desktop | silent install of the neutral setup; FileVersion 0.2.443 |
| 18 | install-phone | `adb install -r` the new APK; versionName 0.2.4042 (> 0.2.4035), one device f0a5b32b |
| 19 | restart | NEW listener pid, both listeners, HTTP 403 |
| 20 | identity | `check_live_version_identity.py` PASS at the new ref |
| 21 | probes | `verify_wave13_live.py` (no `--ref`): EXPECTED `8 PASS / 1 FAIL / 3 BLOCKED / 1 PARTIAL`, RESULT NOT GREEN, exit 1. The eight PASS: RM-2, RM-3, GH-3, GH-4, F2-2, F5-2, F5-3, W12-1. The one FAIL is MF-2 (memory-fault route 404s - the known gap in section 3b, not a new failure). BLOCKED: CR-4 and F2-3 (guarded, never sent) plus W12-3 (structural - see 3b). W12-2 PARTIAL by spec. The named+explained non-passes are the record; never fake GREEN |
| 22 | postdeploy | runs `post-deploy-checks-wave13.ps1 -PhoneVersion <0E>` (18 rows): expected `14 PASS / 1 FAIL / 0 BLOCKED / 3 WARN`, exit 1. The one FAIL is MF-1 (known gap, section 3b); WARNs are A-SIZES, F5-1 (CRLF staging artefact, soft by design; the deploy writes 49,320 B not 50,414 B) and W12-2; P0-SHA PASSes because its Worktree default is the frozen integration wt. **The packet's own printed GO text at gate-script lines 911-914 still says "A-SIZES byte-exact ... must now PASS ... a still-red row is a STOP" - that text is superseded by the measured expectation: A-SIZES and F5-1 are WARN by design and a WARN is not a STOP here.** Without `-PhoneVersion` it is 13 PASS / 1 FAIL / 1 BLOCKED / 3 WARN |
| 23 | preflight | totals IDENTICAL to wave 12: `35 pass / 9 fail / 3 warn / 5 skipped` (52 rows), `preflightExit=1`. Two printed COUNTS move (measured, flip map): the patch row prints `172 of 178` (was 171 of 177 - `_stack.order()` is 178 at the frozen tree) and the unrecorded-files row prints `70 installed file(s)` (was 69 - `jarvis_creator.py` is SHIPPED, absent from the 232-row record and from live); `229 of 232` stays only after a successful reseal. The patch row adds no printed line - **a printed `skill-scan-wiring.patch` row means F5 did not deliver (its ONE insert is the proof) = STOP**. The 9 standing FAILs are: appearance 216/334, gpu-offload 61/94, show-card-timer 10/60, cloud-honesty 3/80, attached-file absent, model-recommendations 8/16 (F7), and the gate/hud/skills "changed since installer wrote it" trio. **The trio does NOT flip tonight**: those four modules are not in `_where.SHIPPED` (334 entries), reseal calls their state rows `unprovable` and refuses to invent a hash (`--rebaseline-unprovable` off by default, not passed), and waves 11+12 both ended `RESULT: PARTIAL` naming exactly `jarvis_gate.py` / `jarvis_hud.py` / `jarvis_skills.py`. Only `jarvis_skills.py`'s "now" half moves (the skill-scan-wiring insert lands in it). 3 WARNs: `/api/status` lane-model-power, the 70 unrecorded files, firewall unreadable. 5 skips: own-chat `--with-chat`, email watch, Calendar, Email, Home Assistant. **STOP on: a FAIL/WARN subject outside these sets, row count != 52, or preflightExit=2.** (The plan's line 134 "8 standing FAIL rows" is one wave stale - wave 11 had 8, wave 12+ has 9 with F7.) |
| 24 | awareness | `python -B tools\check_live_awareness_sanity.py --json-out <run>\awareness-sanity.json` from the tree (writes `11-awareness-sanity.txt` + `.json`). SUMMARY stays `22 passed / 1 failed / 2 blocked` (25 rows); `cap-cloud-escalation` FAIL is standing; the two BLOCKED trap rows (`trap-file-phone-pc`, `trap-forget-fact`, HTTP 500 at CallExpression line 85) are standing. Only the version rows move: `self-app-version` 0.2.442 -> 0.2.443 and `self-phone-version` 0.2.4035 -> 0.2.4042 - **both are graded against LIVE ground truth, so a failed install shows the OLD numbers with PASS; compare the numbers, not the word.** The gate parses NO machine verdict here; its GO text says "3 BLOCKED rows" (that was wave 9) - waves 11 and 12 both left 2, so do not use 3 as a count. `awarenessExit=1` expected |
| 25 | verify-wave8 | re-baselines the one literal ("0.2.439") into `<run>\verify_wave8_wave13.py` and runs with `--expect-version <0E desktop>` / `--expect-desktop <0E desktop>` / `--expect-phone <0E phone>`; writes `.py`, `.json`, `12-verify-wave8-wave13.json`, `.txt`. Expect `26 pass / 1 fail` of 27 rows: the single FAIL is `self-update-history`, same name, still missing `['Coding preset']` (git grep at 32ba251d9 never hits `jarvis_recent_changes.py`; its version half comes from live VERSION). `desktop-version` and `phone-version` re-pin to the new versions. **TRAP: the 27th row `backend-version` is CONDITIONAL (`if ver:`) - it appears only when `/api/status` carries `app_version`/`version`. If it appears and FAILS, the gate STOPs on an unexpected row (its drift branch hard-codes `$rows -eq 27`); if it appears and passes, 27/0.** |
| 26 | rollback | print only; also read `ROLLBACK.md` before the deploy in case it is needed |

## 3b. Known delivery gap measured BEFORE the deploy (memory-fault, MF-1)

Measured read-only at 15:57 PT by the post-deploy expectation map (calling the deploy
tool's own `plan_deltas` against the real live folder, frozen ref `32ba251d9`; the checks
were repeated against the live files):

- `auto-learn.patch` is an EXISTING patch that wave 13 EXTENDED (23,159 B at `d6df4022` ->
  25,589 B at `32ba251d9`, gaining the two memory-fault hunks). The reconciler's
  `patch_presence` uses ONE distinctive added line as proof of the whole patch, and 129 of
  its 144 distinctive added lines are already in the live HUD from the older patch version,
  so it reports `already` and inserts nothing.
- `auto-learn.patch` has no `DELTA_TABLE` entry (48 keys, none is `auto-learn.patch`). The
  tool's own docstring (lines 99-107) names exactly this failure mode and the precedent fix:
  `gate-touches.patch` got a DELTA_TABLE entry for the same reason.
- Consequence: after a correct apply the live `jarvis_hud.py` still has 0 of
  `"/api/memory/fault"` (live now: 0; the HUD dispatch is exact-path tuples at
  `jarvis_hud.py:3606,5034`), so `GET /api/memory/fault` 404s; the shipped
  `jarvis_auto_learn.py` handler exists but is unreachable. Feature 4 / matrix row 19 is
  NOT DELIVERED tonight.
- 0H says it plainly: `to insert: 1` (only skill-scan-wiring -> jarvis_skills.py).
- **This is NOT a reason to hold the merge and NOT fixable inside frozen #1218.** The code
  ships correctly; the deploy TOOL skips the patch's new hunks. Fix in wave 14: add a
  `DELTA_TABLE` entry for `auto-learn.patch`'s new hunks (gate-touches precedent) and
  redeploy. Never hand-edit the live `jarvis_hud.py`.
- Acceptance consequences to record honestly: postdeploy MF-1 FAIL expected (the single
  FAIL in the expected summary); `verify_wave13_live.py` MF-2 FAIL expected (the verifier has
  no MF-1 row - its only memory-fault row is MF-2), expected `8 PASS / 1 FAIL / 3 BLOCKED /
  1 PARTIAL`, RESULT NOT GREEN; matrix row 19 NOT DELIVERED.
- The official owner handout must annotate row 19 as "expected not delivered in this
  deploy (deploy-tool gap, fix in wave 14)".
- **A second skipped delta, same cause, smaller:** `github-tools.patch` gained real
  `_TOOL_ACTIONS` / `_RISK` rows for `github_create_repo` (+10/-2), and its delta is skipped too
  (all `GITHUB_TOOLS_PROBES` needles are older strings). The card/tier/ability still land via
  `jarvis_asks_first.py` and `jarvis_agent.py`; only the gate's naming/risk sentence degrades to
  its unclassified fallback. Row 7 is delivered differently - record it, it is not a STOP.
- **Separately, W12-3 is structurally BLOCKED, not this gap:** the verifier wants
  `/api/bench`'s `running` to be a real bool twice, but the route returns `_current_run()`,
  an `Optional[str]` (jarvis_bench.py:2210/1664 via bench.patch:7), and wave 13 does not
  touch either file. The plan (:132-133) says classify it PARTIAL; the verifier code says
  BLOCKED and BLOCKED forces exit 1. Record it BLOCKED with that reason (the plan/verifier
  conflict is a wave-14 row fix) - do NOT edit the verifier between the merge and the run.
- **CRLF artefact:** the reconciler stages hunks as LF and writes with newline="", so the
  deployed `jarvis_skills.py` is 49,320 B with 0 CRs (all five F5-1 markers present 1/1);
  the PR body's 50,414 B came from a Windows `git apply` (1,094 CRs). So A-SIZES -> WARN
  (soft) and F5-1 -> WARN (soft) are EXPECTED and are not STOPs; "A-SIZES byte-exact" is
  unreachable and must not be read as a failure.

**Gate text is the verdict, not the exit code**: every gate exits 0 even on STOP
(rehearsal G-issue). A STOP stops the run until it is understood; never skip forward.

## 4. Guard rails specific to tonight

- Fresh run folder (step 0) + never re-run an earlier gate after a GO without first
  deleting `release-vars.json`, `assets.json`, `ref.txt` from the run folder (the
  rehearsal's single most useful latent defect; fix shape is in the wave-14 backlog).
- The integration worktree stays at `32ba251d9`; the deploy tree moves to the merge sha.
- One gate at a time; capture each gate's full stdout into the run folder with
  `Tee-Object -Append`.
- If a rollback is ever needed: `ROLLBACK.md` (corrected tonight, independently re-checked
  SAFE TO FOLLOW: all 11 fixes verified, 11/11 PowerShell blocks parse under 5.1, asset
  numbers match) + the durable wave-12 assets at `D:\jarvis-cache\wave12-rollback-2026-11-09\`
  (MANIFEST.txt). Its residual risks are non-blocking: the restart gate needs the tailnet row
  to exist; `pre-deploy-baseline.json` sits one level up from `$run`; the deep-fallback copy is
  ~470 MB/6,288 files, slow not destructive.
- **Do not "correct" `wrote 23`:** the 0H dry run reads `beside+version 0` because it cannot
  see the new installer; Gate apply sets `JARVIS_DESKTOP_EXE`, and the tool takes VERSION from
  that exe's FileVersion. Wave-12 is the precedent (dry 249/beside 0 -> apply 250/beside 1/
  wrote 21), so wave 13 = `wrote 23` and a **259-entry journal** (23 writes + 236 pycache) -
  and step 1 of the rollback CAN restore VERSION.
- **Printed GO prose is NOT evidence for 13 of the 26 gates.** The frozen script's operator
  sheet (`D:\jarvis-scratch\WAVE13-GATE-SHEET-2026-11-09\GATE-SHEET.md`, 249 lines, script
  sha256 re-verified `3F50191C…A35983`) measured that 0H, insurance, repair, be, stopped, apply,
  quotes, reseal, toml, install-desktop, identity, preflight and awareness print their GO line
  **unconditionally, even when the check inside failed**. For those, grep the gate's own check
  lines (the sheet's §3 gives the literal string per gate), never the GO paragraph. Also
  superseded text: postdeploy lines 911-916 still claims A-SIZES/F5-1 must PASS; probes lines
  836-838 still claims the verifier "exits 0"; 0B's GO sentence still names the old `7d892e27`
  tree (the code compares `$FrozenTree`); Show-Gates still advertises `--ref` for
  `verify_wave13_live.py`, which exits 2 on it. Only `-Gate` is a parameter of the gate script;
  `-PhoneVersion` belongs to `post-deploy-checks-wave13.ps1` and is passed by the gate itself.
- Never auto-approve a card; cards stay with the owner.
- **Expected non-zero exits are not failures.** `resealExit=1`, `preflightExit=1` and
  `awarenessExit=1` are the documents' own honest exits (PARTIAL rows and standing
  baseline rows); the row counts and named rows are the verdict. A surprise is an exit
  value outside {0,1} or a written verdict that disagrees with the pinned rows.
  (`GATE-SHEET.md` §3's generic "`awarenessExit=0`" line is a template: awareness exits 1
  because `cap-cloud-escalation` is a standing FAIL row - the SUMMARY and rows are the
  verdict. Likewise probes exits 1, not 0, for the known-NOT-GREEN wave-13 verifier.)
- **Authority for the last three gates is the independently measured flip map:**
  `D:\jarvis-scratch\WAVE13-EXPECT-FLIPS-2026-11-09\FLIP-MAP.md` (413 lines; rows 23-25
  above carry its numbers). It measured the install tree already at `32ba251d9`, so
  `178` patches / `334` SHIPPED / `232` record rows are already in effect.

## 5. After the deploy

- `WAVE13-RESULT-2026-11-09.md`: every gate's verdict quoted, every non-PASS row named,
  the main-run check 0D deferred, and the known baseline drifts.
- Owner handout: the **OFFICIAL annotated sheet** is
  `D:\jarvis-scratch\WAVE13-OWNER-SWEEP-AUDIT-2026-11-09\OWNER-HANDS-SWEEP-WAVE13-official.md`
  - the verified corrected copy plus the independent verification's R1-R5 fixes (mandatory R1:
  the Notion import has no preview and no card) plus a deploy-status header and the
  memory-fault row-19 annotation. It still has `<NEWVER>/<PHONEVER>/<MERGE7>` placeholders:
  FILL THEM after the deploy, then copy it over
  `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09\OWNER-HANDS-SWEEP-WAVE13.md` as the official
  path and present it. The original stays archived
  (`...WAVE13-OWNER-SWEEP-AUDIT-2026-11-09\OWNER-HANDS-SWEEP-WAVE13-original-untouched.md`).
