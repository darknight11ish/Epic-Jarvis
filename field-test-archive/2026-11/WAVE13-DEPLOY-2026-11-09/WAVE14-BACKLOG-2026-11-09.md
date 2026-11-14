# Wave-14 backlog - everything carried out of the Wave-13 freeze and audit

Started 2026-11-09 12:58 PT, while Wave-13 CI runs on head `7d892e277`. (Head note:
that run came back red on backend-windows - three stale tool pins, fixed as `b3b300034`;
the backlog items below are unaffected.) NOTHING in this
file starts before Wave-13 is deployed, its automated acceptance + post-deploy checks are
recorded, and the owner's hands-on sweep is handed over.

Baseline for wave 14: the Wave-13 merge on `main` (merge commit of PR #1218), verified by
Gate 0B's tree equality. New branch: `integration/wave14-2026-11-09` (or as the owner rules
after the sweep).

## A. Carried out of the Wave-13 feature audit (see D:\jarvis-scratch\WAVE13-AUDIT-2026-11-09\AUDIT-DISPOSITION-W13.md)

| id | what | where | why not in wave 13 |
|---|---|---|---|
| W13-01 | The new reminder-title trimmer can eat a bare trailing number: "remind me to take 2 at 8pm" stores title "take" (parse_when("2") reads it as a clock). | `backend/jarvis_quick.py` (`reminder_action_words`, the time-tail loop) + `backend/test_reminders_grandma.py` | Real regression, LOW frequency; fixing the time-tail rule wants its own tested change, not a last-minute deploy edit. |
| W13-03 | Creator's install answer writes `where: "turned off"` unconditionally, while the pack manager can answer ok:True/state "installed" and say the skill is ON. | `backend/jarvis_creator.py` (~line 524) + `backend/test_creator_mode.py`; page currently does not draw `where` | No test covers that branch; needs a small test + wording decision. |
| W13-04 | The new 30-second chip repaint (S.lane == "auto") can overwrite a cloud/second-card turn's chip text and clear `.hot`. | `jarvis-desktop/src/jarvis_hud.html` (repaint near `paintModelInUse`, poll) + `jarvis-desktop/tests/hud-current-models.mjs` | Reasoned, not driven; the repaint is wanted in the normal case. Needs a driven repro before scoping it. |
| W13-09 remainder | "three small actions" survives in `backend/github-tools.patch`'s header comment (the self-code map half was fixed). | `backend/github-tools.patch` | Editing a `.patch` requires the patch-history record step (`tools/build_patch_history.py`), which does not belong in a deploy freeze. |

## B. Carried out of the Wave-13 F6 audit (`F6-AUDIT.md`, LOW)

- **Multi-model lane union:** a lane running more than one model reports the union of the
  models' cards rather than per-model attribution; document it or split the read.
- **No test executes `_windows_parent_pid`:** the ctypes parent-chain walk is exercised only
  through helpers; a test that really calls it would pin the handle-typing risk. The live
  two-lane read worked (11436 -> card 0, 11435 -> card 2), so this is a test gap, not a bug.

## C. Recorded follow-ups already named before wave 13

- **F7** - comment-only patch-record drift in `backend/model-recommendations.patch`
  (a `2026-10-28` comment); the route answers and the drift is cosmetic.
- **`repin_after_install` gap** - the published base's `install()` calls
  `_packs.repin_after_install()`, no `.patch` carries it, and the live file lacks it, so a
  pack edited through the approved path can still read as tampered. Same delivery class as
  F5: needs its own patch + test + deploy.
- **memory.db encryption** - DEF-055, owner told plainly on 2026-11-09: `memory.db` has no
  cipher at rest (chat history and encrypted backups already use AES-256-GCM). Ruling was:
  research shape first (same key material/unlock path), then a design + migration plan
  before touching live data. Queued as its own task after Wave-13 (team board task-10).

## D. Lanes already planned elsewhere (do not duplicate)

- **Preset cut-back (9 presets + Medical tenth + two measured pooled candidates):**
  `D:\jarvis-scratch\OFFPEAK-CONTINUATION-2026-11-09\WAVE14-PRESET-CUTBACK-PLAN-2026-11-09.md`
  (paired session's lane; prepare only until Wave-13 deploy is complete, code changes off
  merged main).
- **P1a takeover work:** `.dsh-scratch\TAKEOVER-P1A-2026-11-09\` (another active lane).
- **Owner-hands sweep after deploy:** `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09\OWNER-HANDS-SWEEP-WAVE13.md`
  (31 rows; BLOCKED/NOT RUN rows stay non-passes until driven).

## E. Deferred housekeeping (owner's call, not during a deploy)

- **C: cleanup:** `C:\Users\pcadmin\.lmstudio` holds about 232.7 GB of models untouched since
  10 Oct. The owner was offered move-to-D: (recommended) vs leave; decision deferred until
  after the deploy. C: free space is monitored in the deploy gates.
- **Old worktree pruning** beyond the ones already removed by earlier cleanup passes.

## F. Wave-13 deploy findings

- Anything the post-deploy checks, the two acceptance scripts, or the owner's sweep record
  that is NOT a pass goes here after the deploy - do not start wave 14 with an unread red row.
- Wave-14 nit from the third re-pin: the new comment in `backend/test_notes_edit.py`
  (added in 32ba251d9) says "skill-scan-wiring.patch adds a 29th patch-backed drop-in
  and creator-mode is the 58th ready folder". The measured figures (29 / 58) are right,
  but the attribution should be re-checked against `plugins/registry.json` semantics
  before anyone repeats it - the paired session attributes BOTH rises to the creator-mode
  folder. Comment-only; no check depends on the wording.

## G. Deploy-gate hardening (found by the read-only 2026-11-09 gate rehearsal)

- **Stale run-vars across a STOP.** `release-vars.json`, `assets.json` and `ref.txt` are
  written only on a GO and read back by `Load-RunVars`; the STOP paths do not clear them.
  After an earlier GO, a later STOP leaves those files for a following invocation, so
  `0F` / `apply` / `install-desktop` could consume a previous attempt's versions or assets.
  Tonight's mitigation is procedural (fresh run folder for the real deploy; if a STOP
  after a GO forces a re-run from an earlier gate, delete the three files first - see
  `GATE-REHEARSAL-NOTES-2026-11-09.md`). Fix shape for wave 14: STOP paths delete the
  three files, or write a `ref` field and have `Load-RunVars` STOP on mismatch.
- **`0F` misleading STOP when it runs without `0E`'s GO.** It downloads the 35 MB APK,
  then prints `no setup asset for version  ` (empty version) because `$NewDesktopVersion`
  is empty. Fix shape: guard on an empty version before any download.
- **`0D` same-tree waiver message.** When it defers the main-run check, name the run id
  and head it is trusting so the log proves what was waived.
- Cosmetic: the script header still labels the 14:05 PT CI fix commit `32ba251d9`; that
  fix was `b3b300034` (the 15:35 re-pin block above it is correct). Comment-only.

## H. Wave-13 delivery gap found before the deploy: memory-fault (MF-1) never reaches live

- **What:** wave 13 extends the EXISTING `backend/auto-learn.patch` (23,159 -> 25,589 B) with
  two memory-fault hunks for `jarvis_hud.py`. The reconciler reports that patch `already`
  because `patch_presence` takes ONE distinctive added line as proof of the whole patch and
  129/144 of its distinctive lines are already live from the old version. `auto-learn.patch`
  has no `DELTA_TABLE` entry, so nothing is inserted; 0H says `to insert: 1` (only
  skill-scan-wiring). Live `jarvis_hud.py` keeps 0 `"/api/memory/fault"` dispatch markers
  (its dispatch is exact-path tuples, lines ~3606/5034), so the route 404s even though the
  shipped `jarvis_auto_learn.py` has the handler. Feature 4 / matrix row 19 NOT DELIVERED.
- **Fix shape (wave 14):** add a `DELTA_TABLE` entry for `auto-learn.patch`'s new hunks - the
  tool docstring (lines 99-107) names `gate-touches.patch` as the precedent - then redeploy.
  Never hand-edit the live `jarvis_hud.py`.
- **Acceptance:** postdeploy expected `14 PASS / 1 FAIL / 0 BLOCKED / 3 WARN` exit 1, the
  FAIL being MF-1; `verify_wave13_live.py` expected `8 PASS / 1 FAIL / 3 BLOCKED / 1 PARTIAL`
  NOT GREEN, the FAIL being MF-2 (its only memory-fault row; the verifier has no MF-1 row);
  owner handout row 19 annotated. Separately, W12-3 is structurally BLOCKED - `/api/bench`'s
  `running` is `_current_run()`, an `Optional[str]`, never a bool (jarvis_bench.py:2210/1664
  via bench.patch:7); the plan says PARTIAL, the verifier code says BLOCKED - fix the row in
  wave 14 and do not edit the verifier during a deploy.
- **CRLF note:** staging writes LF, so the deployed `jarvis_skills.py` is 49,320 B (0 CRs,
  all five F5-1 markers 1/1) while the PR body's 50,414 B came from a Windows `git apply`
  (1,094 CRs) - A-SIZES and F5-1 WARN are soft/expected, not failures.


