# Wave 14 - expected post-deploy checks (PR #1219)

STATUS: EXPECTATIONS READY. The script exists, parses and has been dry-run against a
FAKE live root built in scratch. It has NOT been run against the live folder, and
nothing here was deployed.

| item | value |
|---|---|
| script | `post-deploy-checks-wave14.ps1` in this folder - 45,022 B / 837 lines / sha256 `A4629C2DD64836BF0294C57B680868E89C998A8590EF5EB9D9048414F2A70918` (re-hash after any edit; the copy checked here is this one) |
| model | `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09\post-deploy-checks-wave13.ps1` (611 lines / 30,238 B / `F19DFE0D...`), kept row for row; every change carries a `# W14:` comment |
| frozen head | `2dc899fdbd23cffce498449858b1eb7d3c153c0b` (PR #1219) |
| frozen tree | `d98c6519eef3b33e27551cdfeb17496200e87030` - re-read with `git rev-parse 2dc899fd^{tree}` in `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main`, equal to the tree named in the brief |
| PowerShell 5.1 parse | **PARSE OK (0 errors)** under `powershell.exe` 5.1.26100.9711, checked with `[Parser]::ParseFile`; the same checker on a deliberately broken file reports 2 errors, so the check is live, not vacuous |
| PowerShell 5.1 execution | it also RAN under 5.1 in the dry run below (not only parsed) |
| ASCII-only | 0 non-ASCII bytes (the wave-13 rule: a BOM-less .ps1 is read as ANSI by 5.1) |

Which tree every expectation was read from: **`2dc899fd`** in the main clone
(`git cat-file -s` / `git show`), plus `git diff 32ba251d..2dc899fd` (129 files, matching
the brief). Which live state was measured: **`C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`**, read-only, no POST, no restart, no card.

---

## 1. Expected totals after the wave-14 deploy

| invocation | PASS | FAIL | BLOCKED | WARN | exit |
|---|---|---|---|---|---|
| **with `-PhoneVersion 0.2.4043`** (the expected new build) | **20** | **0** | **0** | **2** | **0** |
| without `-PhoneVersion` (gate 0E not run) | 19 | 0 | 1 | 2 | 0 |
| with the OLD `-PhoneVersion 0.2.4042` | 19 | 1 | 0 | 2 | 1 |

- 22 rows (18 from wave 13 + 4 new).
- The two WARNs are **A-SIZES** and **F5-1**, both by design (the reasons are on rows 4 and
  14 in §2), both unchanged from wave 13's measured 14/1/0/3.
- This would be the first wave whose post-deploy checks exit **0**: wave 13's single FAIL
  (MF-1) is the row wave 14 fixes, and W12-2 flips too.

## 2. Row by row

| # | row | expected | why (grounded) |
|---|---|---|---|
| 1 | P0-SHA | **PASS** | `HEAD == 2dc899fd`, or (the merge commit) `HEAD^{tree} == d98c6519`. Only WARN when neither - read this row first if so. |
| 2 | P0-MIXED | **PASS** | `VERSION == EXE > 0.2.443`. Expected reading 0.2.444 for both (the deploy bumps the patch number and the release stamps the EXE). FAIL is correct if the desktop install did not land. |
| 3 | P0-PHONE | **PASS** | needs `-PhoneVersion` of the NEW build (> 0.2.4042). **TO MEASURE**: the number is CI's `client-latest` run number, only known after the merge; 0.2.4043 is the expected next value. Passing 0.2.4042 is a FAIL; omitting it is BLOCKED, never a pass. |
| 4 | A-SIZES | **WARN** | `exact 13/14`: every other file byte-exact against `2dc899fd`, `jarvis_skills.py` 49,320 live vs the baked 50,414 (WARN-only). By design, unchanged from wave 13. |
| 5 | RM-1 | **PASS** | `jarvis_quick.py` unchanged (1,464,997 B); 4/4 markers. |
| 6 | GH-1 | **PASS** | `jarvis_github.py` unchanged (42,711 B); 4/4 markers + shipped toml `github_create_repo="ask"` 1/1. |
| 7 | GH-2 | **PASS** | agent 2/2 at its new 982,447 B; guide 3/3 (239,980 B); quick 2/2 (1,464,997 B). |
| 8 | CR-1 | **PASS** | `jarvis_creator.py` unchanged (29,935 B); 5/5. |
| 9 | CR-2 | **PASS** | creator-mode `plugin.json` unchanged (401 B); 2/2, size not asserted. |
| 10 | CR-3 | **PASS** | `jarvis_packs.py` (123,872 B) 1/1; creator 1/1. |
| 11 | **MF-1** | **PASS - THE FLIP** | auto_learn 4/4 (160,558 B, `memory-fault.json` 3 raw / 2 code); HUD 4/4 (`"/api/memory/fault"):` 1, `"/api/memory/fault/retry"):` 1, the widened `handle_post` call 1, the `_extract_model()`/`OLLAMA` line 1); **extract 2/2** (`def _intake_fault_visible(rows: list) -> list:` 1, `return _intake_fault_visible(_rows)` 1). Grounded in the D-1 fix: the wave-14 tree adds an `"auto-learn.patch"` `DELTA_TABLE` entry with five explicit regions (three HUD, two extract) from `tools/hud-deltas/`, and on 2026-11-09 all **five region pre-images were measured exactly once in the live files**, while all six post-image markers are 0 there today. |
| 12 | MF-3 | **PASS** | none of `brain.js`, `brain/auto_learn.rs`, `lib.rs` or the `brain_memory_fault_retry` permission is in the 129-file change list, so the wave-13 expectation stands (tree-only check; it never proves the installed window draws the banner). |
| 13 | F2-1 | **PASS** | agent 3/3 at 982,447 B; the F2 seam itself is untouched. |
| 14 | F5-1 | **WARN** | 5/5 markers present, size 49,320 vs the baked 50,414 - the LF-staged artefact vs the PR's CRLF figure. **The file is not in the 129-file change list** (`git diff 32ba251d..2dc899fd -- jarvis-backend/jarvis_skills.py` prints nothing), so the wave-13 expectation is kept exactly: WARN-only, never FAIL. |
| 15 | HUD-1 | **PASS** | `hud-presets.js` unchanged (124,613 B); 2/2 calls, 6/6 `markChosen(`, 1/1 def. |
| 16 | HUD-2 | **PASS** | chip marker 1, still inside `loadPresets` before its `}catch(e){` (re-measured at `2dc899fd`: offsets 252,874 < 253,460 < 253,504), size **727,922** (was 721,863). |
| 17 | W12-0 | **PASS** | `jarvis_model_resources.py` 48,996 B (-1 byte, comment-only); 4/4 markers. |
| 18 | **W12-2** | **PASS - THE FLIP** | `install(` 1/1, and **16/16 of the tree's patch added lines are in the live `jarvis_hud.py`**, stale `Seven PC-only` 0. Measured on 2026-11-09. |
| 19 | W14-PROJ | **PASS** | **NEW.** agent 3/3 (`"project_read": Tool(`, `_prepare_project_read`, `_run_project_read`) at 982,447 B; the new module 8/8 at 37,112 B (`MAX_LINES = 2000`, `MAX_SLICE_BYTES = 96 * 1024`, `DEFAULT_LINES = 400`, `read_folder`, `read_project`, `run_tool`, `jarvis_documents.allowed_path`, `jarvis_repomap._walk`). Delivery only - it does not fire the tool. |
| 20 | W14-HUDK | **PASS** | **NEW.** HUD Memory Keep at 727,922 B: `function memoryDoorKeepable(row){` 1, `memoryDoorKeep(` 2, `memory-door-keep` 1, `/api/memory/decide` 1 in code (the second raw mention is a comment and is stripped). |
| 21 | W14-EDIT | **PASS** | **NEW.** `hud-edit.js` 96,571 B (live is 93,653 today and holds none of these): `const EDITOR_OWN_CLICK = [` 1, `if (selectedCard) editTab = "cards";` 1, `onMainScreenClick` 2. This is the capture-phase fix itself. |
| 22 | W14-VAULT | **PASS** | **NEW.** DEF-061 at 118,536 B (live is 118,119 with the old truthy placeholder): `_PENDING: dict = {}` 1, `if _PENDING.get("id"):` 1, `dict(_PENDING) if _PENDING.get("id") else {}` 1. |

Not a row here, on purpose: **the tenth preset (Medical Expert)**. A static count proves
delivery only, and A-SIZES already proves `jarvis_presets.py` lands byte-exact (138,775 B);
whether the preset behaves is the separate read-only preset probe, not this script.

## 3. The exact command the deploy gate should run

Modelled on the wave-13 gate's postdeploy invocation
(`deploy-gates-wave13.ps1:904-907`: `@('-NoProfile','-ExecutionPolicy','Bypass','-File',$pd,'-Transcript',"$run\10b2-post-checks.txt")`,
plus `-PhoneVersion $NewPhoneVersion`):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\WAVE14-DEPLOY-2026-11-09\post-deploy-checks-wave14.ps1" -Transcript "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\WAVE14-DEPLOY-2026-11-09\run-<stamp>\10b2-post-checks.txt" -PhoneVersion <NewPhoneVersion>
```

- `<NewPhoneVersion>` is gate 0E's `$NewPhoneVersion` (the `client-latest` run number,
  expected 0.2.4043). **Do not hard-code it before the release exists.**
- `<stamp>` is the wave-14 run folder the gate creates; the wave-13 one was
  `run-20261109-164537` and its transcript was `10b2-post-checks.txt`.
- Append `-Worktree "<path>"` if the deploy tree is NOT at the default
  `.dsh-scratch\WAVE14-DEPLOY-2026-11-09\wt`. Without a readable worktree the script says
  so: P0-SHA/A-SIZES/MF-3 BLOCKED and W12-2 loses its record half - it never guesses.
  The default was checked at 20:30 on 2026-11-09: `wt` is a git repo at
  `2dc899fd` / tree `d98c6519`, and dry run 3 below (which used the default, not a
  passed path) reads P0-SHA PASS. **Do not point it at `wt-frozen`**: that worktree is
  at `24a3fc9b` / tree `ad1de9e1`, which is NOT the frozen tree.
- The gate's own GO text must be corrected for wave 14: it should expect **A-SIZES and
  F5-1 to be WARN by design** (the wave-13 GO text still said they must PASS, which its
  own result doc §5 item 10 records as superseded), and it should now expect **MF-1 PASS**.
- Exit code is 0 unless a row is FAIL: BLOCKED and WARN alone do not exit 1, and are
  never read as passes.

## 4. What changed from wave 13 (the whole diff, compact)

| item | wave 13 | wave 14 | why |
|---|---|---|---|
| `-Worktree` default | `WAVE13-INTEGRATION-2026-11-09\wt` | `WAVE14-DEPLOY-2026-11-09\wt` | the new deploy tree |
| `-FrozenSha` | `32ba251d...` | `2dc899fd...` | PR #1219 head |
| `-FrozenTree` | (did not exist) | `d98c6519...` | NEW: lets the merge commit pass (same tree, different sha), which is what wave 13 measured |
| `-VersionFloor` | 0.2.442 | 0.2.443 | live is already 0.2.443 |
| `-PhoneFloor` | 0.2.4035 | 0.2.4042 | installed phone is already 0.2.4042 |
| P0-SHA | `HEAD == frozen` only | + `HEAD^{tree} == frozen tree` PASS case | the merge commit's sha differs |
| A-SIZES | 13 rows | 14 rows | `jarvis_project_read.py` 37,112 added (`backend/_where.py:1785` lists it in SHIPPED) |
| A-SIZES sizes | - | agent 982,447; asks_first 170,242; model_resources 48,996; presets 138,775; hud.html 727,922 | re-read from `2dc899fd` |
| A-SIZES `jarvis_skills.py` | 50,414 warn-only | **identical** | file not in the change list |
| MF-1 | 2 items, expected FAIL | 3 items (+extract 2 markers; HUD +postcall/+handle), expected **PASS** | the D-1 `DELTA_TABLE` entry |
| W12-2 | drift string counted, 0 expected | every `+` line of the tree's patch must be in live, stale seven-route claim must be 0 | the tree now carries the live file's own block |
| HUD-2 | size 721,863 | 727,922 | the new HUD |
| new rows | - | W14-PROJ, W14-HUDK, W14-EDIT, W14-VAULT | the four wave-14 deliverables a file read can prove |

Everything else (row ids, order, functions, comment stripping, transcript, exit code) is
the wave-13 code unchanged.

## 5. Evidence for the two flips, and what remains uncertain

**W12-2 (grounded, not assumed).** At `2dc899fd` the patch's added block is the live
file's own eight comment lines ("Five PC-only routes" - the two routes the patch does not
install are gone) and the hunk header is `@@ -6871,3 +6871,19 @@`. Measured in the live
`jarvis_hud.py`: all 16 added lines present, `Seven PC-only` 0, `Five PC-only` 1,
`install(` 1. The wave-13 patch revision claimed **seven** PC-only routes, which is the
drift; that text no longer exists in the tree.

**MF-1 (grounded, not assumed).** At `2dc899fd`, `tools/reconcile_live_backend.py` carries
the `"auto-learn.patch"` entry with five regions and two probe sets. In the live files,
read-only: the three HUD pre-images and the two extract pre-images are each present
**exactly once**, and the six post-image markers are each **0**. The wave-13 result doc
§5 item 1 names the same gap (`GET /api/memory/fault` was 404, postdeploy MF-1 FAIL).

**Dry run (never against live).** The script was run three times under 5.1 with `-LiveRoot`
pointed at a FAKE root in `_work\fake-live`, built by copying the `2dc899fd` blobs and
applying the five D-1 regions to **copies** of the live `jarvis_hud.py` / `jarvis_extract.py`
(the pre-images matched exactly once in each, which is itself evidence the fix will land):

- `_work\dryrun-fake.txt` - the fake root with VERSION 0.2.444 but the real, still-0.2.443
  desktop EXE: that correctly reads FAIL on P0-MIXED (a mixed install - the pre-deploy truth).
- `_work\dryrun-fully-landed.txt` - the same root with matching versions and a tree-equal
  HEAD: **`SUMMARY: 20 PASS / 0 FAIL / 0 BLOCKED / 2 WARN`, exit 0**, every row's detail
  exactly as §2 predicts.
- `_work\dryrun-default-worktree.txt` - the same, but with the script's OWN default
  `-Worktree` (no path passed): P0-SHA reads `HEAD=2dc899fd... == frozen; tree=d98c6519...`,
  and the summary is the same **20 / 0 / 0 / 2**, exit 0.

**UNCERTAIN / TO MEASURE** (never presented as measured):
1. **The new phone version** (P0-PHONE) - CI's run number after the merge. Expected
   0.2.4043; only the release can say.
2. **The deployed `jarvis_skills.py` size** - expected to stay 49,320 (the file is
   unchanged and its delta is already live). If the deploy rewrites it from the tree blob
   (51,305 B) the row still reads WARN, never FAIL; only the printed number moves.
3. **MF-1's live HUD/extract sizes** are deliberately not asserted (patch artefacts). If
   the deploy tool refuses an anchor (it refuses rather than guessing), MF-1 stays FAIL -
   that would be a real finding, not an expectation.
4. **A-SIZES' other 13 files** assume the deploy writes them byte-exact from the tree, as
   wave 13 measured (`live == w13 blob` verified for agent, asks_first, presets,
   model_resources, vault, hud-edit before this packet was written).
5. The **tenth preset's behaviour** is out of scope here (A-SIZES proves delivery only);
   the separate read-only preset probe owns it.

## 6. Scratch evidence kept in this folder

`_w14tree\` - the 20 wave-14 blobs the expectations were counted against (byte-exact,
written with `git show > file`), plus `_work\` - the marker probe, the parse checker, the
fake-live builder, the fake root and the three dry-run transcripts. None of it is a live
write; all of it can be deleted. Live was only ever read: `VERSION` = 0.2.443 and
`jarvis_skills.py` 49,320 B (mtime 17:06:34, the wave-13 deploy), `jarvis_hud.py` 442,086 B
(mtime 2026-11-07), and the newest backup folder is still
`_jarvis-deploy-backup-tool-20261109-170634` (17:06:35, the wave-13 deploy). The 29 folders
matching `_jarvis-deploy-backup-*` are 27 tool backups plus 2 of another name - the brief's
"27" counts the tool ones.
