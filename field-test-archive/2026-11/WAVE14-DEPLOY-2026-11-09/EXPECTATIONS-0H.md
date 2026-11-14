# Wave-14 0H expectations — measured read-only on the live install

Measured 2026-11-09 20:22–20:26 PT by a delegated session. **Nothing was applied, merged,
branched, committed or pushed. The live folder was not written to**: the live `VERSION` still
read `0.2.443` and the count of `_jarvis-deploy-backup-tool-*` folders was still 27 before and
after every run.

## 0. Which commit this is measured at — the brief's SHA moved

The brief names `2dc899fdbd23cffce498449858b1eb7d3c153c0b` (tree `d98c6519…`). The packet's
own `frozen-ref.txt` and `git ls-remote origin refs/pull/1219/head` both now name:

- **frozenHead = `24a3fc9b1da913556b7ee1585d46538830cb0b80`**
- **frozenTree = `ad1de9e15f5ad14b35a1d7c9cda31d2eaa54e9c8`**

I measured **both** heads in two clean detached worktrees:

| worktree | HEAD | tree | receipt |
|---|---|---|---|
| `wt` | `2dc899fdb…` (prevHead) | `d98c6519…` | `0H-PREVIEW-wave14.txt` |
| `wt-frozen` | `24a3fc9b1…` (frozenHead) | `ad1de9e1…` | `0H-PREVIEW-wave14-frozen.txt` |

The two receipts are **identical line for line** after stripping the `repo:` and `ref :`
lines (`Compare-Object` → no differences). That is expected and checked, not assumed: the
only delta between the heads is `backend/static/hud-edit.js` and `jarvis-backend/hud-edit.js`
(+10/−8, comment fix), hud-edit.js is a SHIPPED *update* at both heads, and
`tools/reconcile_live_backend.py` is byte-identical at both heads (empty `git diff --stat`).
**Use the frozen-head receipt as the 0H authority; re-run 0H against the merge tree after
the merge, as the runbook requires.**

Command actually used (frozen head; the brief's line omitted `--ref`, which would REFUSE —
see §8):

```
py -3 -B "...\wt-frozen\tools\reconcile_live_backend.py" `
  --backend-path "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" `
  --repo "...\wt-frozen" --ref 24a3fc9b1da913556b7ee1585d46538830cb0b80 --dry-run
```

Exit 0. Receipts and their SHA-256 are in §12.

## 1. Expected 0H rows (the frozen-head receipt)

| row | expected at 0H |
|---|---|
| SHIPPED | **335** files = **add 1 + update 21 + unchanged 313** |
| HUD DELTAS | **234** checked = **already present 232 + to insert 2** |
| to insert | `auto-learn.patch -> jarvis_hud.py (3 region(s))` and `auto-learn.patch -> jarvis_extract.py (2 region(s))` |
| READY PLUG-INS | **32 present / 0 to add / 26 already wired** (broken: none) |
| PYCACHE | **231** stale `.pyc` (live counter — see §5) |
| PLANNED CHANGES | **255** = add 1 + update 21 + insert 2 + beside/version 0 + pycache 231 |
| VERSION | **unchanged 0.2.443**; RELEASE MARKERS **0** in the formula |
| backups | **27 → 27** (dry run writes nothing) |
| REFUSED / Traceback / diff lines | **none** |
| dryRunExit | **0** |

## 2. SHIPPED detail (335)

Add (1): `jarvis_project_read.py` — the wave-14 new module.

Update (21), in the tool's own order; the receipt prints the first 12 and `... and 9 more`,
the full list is in `0H-inventory-frozen.json`:

`jarvis_agent.py`, `jarvis_recent_changes.py`, `jarvis_settings_registry.py`,
`jarvis_setup.py`, `jarvis_reach.py`, `jarvis_asks_first.py`, `jarvis_claims.py`,
`jarvis_menus.py`, `jarvis_hud.html`, `hud-edit.js`, `jarvis_big_coder.py`,
`jarvis_model_lanes.py`, `jarvis_presets.py`, `jarvis_vault_organizer.py`,
`jarvis_feature_catalogue.py`, `jarvis_model_resources.py`, `jarvis_model_knowledge.py`,
`jarvis_tool_profiles.py`, `jarvis-self-code.json`, `jarvis_model_recommender.py`,
`jarvis_bench.py`.

Unchanged 313. Arithmetic: 1 + 21 + 313 = 335.

**New beside-file: none.** `requirements.lock` and `quiz_grader_cases.json` are both
`BESIDE: unchanged`; no other beside file is in the formula. (The root `VERSION` says
`0.2.0` and is not the release marker — the tool reads the installed desktop's FileVersion.)

## 3. HUD DELTAS (234 checked)

| patch | live target | tool text | what it carries |
|---|---|---|---|
| `auto-learn.patch` | `jarvis_hud.py` | **3 region(s)** | the `/api/memory/fault` GET branch, the POST dispatch 2-tuple, and the `_extract_model()` call site |
| `auto-learn.patch` | `jarvis_extract.py` | **2 region(s)** | the intake return and the appended `_intake_fault_visible` body |

Five region pairs in total (3 + 2), deliberately **not** `hunks: True` — this is the D-1
DELTA_TABLE entry. The tool's own suffix is `region(s)` for a region-shaped entry, so the
row is `(3 region(s))` / `(2 region(s))`, not `(N hunk(s))`.

`skill-scan-wiring.patch` is **not** in the to-insert list any more: wave 13's apply landed
it and it now counts in `already present` (+1), while the two auto-learn rows are no longer
counted there (−2) — net already-present 233 → 232, as the D-1 fix intends. Staged files are
exactly `jarvis_extract.py` and `jarvis_hud.py`; `rehearsal: py_compile OK for
jarvis_extract.py, jarvis_hud.py`.

## 4. READY PLUG-INS

**32 present, 0 to add, 26 already wired by the HUD, broken manifests: none.**
Wave 13 measured 31 / 1 (creator-mode) / 26; creator-mode is now present, so the to-add list
is `none` and no plugin step is expected at apply.

## 5. PYCACHE — a live counter, not a constant

The receipt says **231** stale `.pyc`. It is live: a re-read a minute later said **232**,
because the running app wrote `jarvis_learning_switch.cpython-312.pyc` at 20:23:38. Wave 13
measured 237. The 0H gate must read the tool's own `PYCACHE: N` line and check the PLANNED
arithmetic against that N; do not hard-code 231. (`PLANNED` = 24 + N with the other terms
fixed: 1 add + 21 update + 2 insert + 0 beside/version.)

## 6. PLANNED CHANGES and `wrote N`

0H, exactly as printed:

```
PLANNED CHANGES: 255 file-level change(s) = add 1 + update 21 + insert 2
                 + beside+version 0 + pycache 231
```

**Expected `wrote N` at apply = 25**, derived from the tool's code and the gate's own env:

- `apply_shipped` writes add + update = **1 + 21 = 22** files;
- `apply_deltas` writes **one file per staged target**, not one per region — the 5 region
  pairs collapse to 2 files (`jarvis_hud.py`, `jarvis_extract.py`) = **2**;
- `apply_release_files` writes **VERSION 1** — because the apply gate sets
  `$env:JARVIS_DESKTOP_EXE = $SetupNeutral` (the neutral copy of the **0.2.444** setup made
  by 0F), so the tool reads 0.2.444 against the live 0.2.443 and plans one write;
- `wrote N` excludes the pycache purge (it has its own `PYCACHE: purged N` line).

**25 = 1 add + 21 update + 2 delta-insert file writes + 1 VERSION.** Wave 13 is the proof of
the pattern: its 0H said `unchanged 0.2.442` / `PLANNED 259`, its apply printed
`wrote 23 = 1 + 20 + 1 + 1` after the same env line made VERSION write 0.2.443.

Caveat, stated rather than hidden: **without** that `JARVIS_DESKTOP_EXE` line (i.e. applying
against today's pre-state), VERSION stays `unchanged 0.2.443`, release markers are 0,
`wrote N` is **24**, and PLANNED stays 255. If the wave-14 gate prints `wrote 24` and
`VERSION: unchanged`, the missing or wrong `$SetupNeutral` is the first thing to check.

If pycache is still 231 at apply, PLANNED at apply is **256** (255 + the VERSION write).
`wrote N` is unaffected by pycache.

## 7. VERSION and backups

- Dry run: `VERSION: unchanged 0.2.443`; `BESIDE: unchanged requirements.lock`;
  `BESIDE: unchanged quiz_grader_cases.json`; `RELEASE MARKERS (0 in the formula…)`.
- Apply (with the gate env): `VERSION: wrote 0.2.444 (was 0.2.443, from the installed
  desktop)` — 0.2.444 is the runbook's expected desktop build; read the release name, never
  assume it.
- Backup folders: **27 before → 27 after** the dry run (re-counted). Apply creates exactly
  **one** new `_jarvis-deploy-backup-tool-*` folder → **28**.

## 8. REFUSED / Traceback / diff lines

**None.** Both 0H receipts scan clean for `REFUSED`, `Traceback`, `^--- `, `^\+\+\+ `, `^@@ `
and `^diff `.

One deliberate extra run is kept as `0H-refguard-default-ref.txt`: the brief's command
**without `--ref`** refuses, because the worktree HEAD is 24a3fc9b1 and the default
`origin/main` is still 85e9e850:

> REFUSED: the working tree is at HEAD 24a3fc9b1… but --ref origin/main is 85e9e850…

Exit 2, nothing written. So the wave-14 gate must pass `--ref <merge sha>` (wave 13's 0H
already did pass `--ref $Ref`; the brief's prose line is what omitted it). Do **not** use
`--allow-worktree-mismatch`.

## 9. Live pre-state (read-only, git-free reads)

| item | value |
|---|---|
| `VERSION` | `0.2.443` |
| `_jarvis-deploy-backup-tool-*` folders | **27** |
| `jarvis_hud.py` | **442,086 bytes**, mtime 2026-11-07T02:20:36; contains `/api/memory/fault`: **False** |
| `jarvis_extract.py` | 42,548 bytes; contains `_intake_fault_visible`: **False** |
| `__pycache__/*.pyc` | 231 at receipt, 232 at 20:24 |
| live folder items | 461 |

The HUD/extract pre-state is exactly the wave-13 shape the D-1 test describes (442,086 B and
42,548 B measured in its own comment), and the fault routes are still **absent** — the
wave-14 delivery is still owed.

## 10. D-1 proof — what the dry run proves, and what only the apply can prove

At 85e9e850 the tool has **zero** `auto-learn` mentions; at 24a3fc9b1 it has the
DELTA_TABLE entry (two files, five region pairs), the ten block-file constants, and the
probes (`"/api/memory/fault"`, the POST 2-tuple, the `_extract_model()` call, and the
extract's `_intake_fault_visible` pair). The suite gained
`t_the_auto_learn_fault_routes_are_carried_not_false_greened` (line 4154, wired into
`main()` at line 5573; absent at 85e9e850). I ran that test alone from the frozen worktree:
**37 checks `ok`, 0 FAIL, exit 0**, including the reproduction of the old false-green
("with NO entry … wrongly ALREADY_PRESENT"), the idempotent second plan, and byte-for-byte
staging.

So the dry run proves the plan on today's live bytes: the presence rule now answers ABSENT
(where wave 13's fallback answered ALREADY_PRESENT), the two files are staged with no
refusal, the staged bytes compile, and a second plan stages nothing. It does **not** prove the
live write or the feature: only the apply (staged bytes actually written), a restart, and a
live `GET /api/memory/fault` answering JSON instead of 404 — plus the live `jarvis_hud.py`
containing `/api/memory/fault` — prove D-1 delivered. The test itself says the same: "all on
strings; the real live folder is never read."

## 11. What the wave-14 gate must print differently from wave 13

1. **`--ref` must be the merge sha** (frozen tree ad1de9e1) and the tree must be at that sha;
   without `--ref` the tool refuses (exit 2) — §8.
2. **0H expected rows:** SHIPPED 335 / add 1 `jarvis_project_read.py` / update 21 /
   unchanged 313; HUD 234 = 232 already + the **two auto-learn** inserts (3 + 2 regions);
   PLUG-INS 32 / 0 / 26; PLANNED 255 with pycache 231; VERSION same; backups 27→27;
   dryRunExit 0.
   Wave 13's line "any 'to insert' row that is NOT the skill-scan-wiring one" must be
   replaced: the **only** allowed inserts are the two `auto-learn.patch` rows, and
   `skill-scan-wiring.patch` must now be in `already present`.
3. **Apply:** expect `wrote 25` (1 + 21 + 2 + VERSION 1), `VERSION: wrote 0.2.444`, PLANNED
   256 if pycache is 231, backup folder **28**, `RESULT: FAIL (3 expected)` probe failures
   (setup / media-index / voice) + `SKIP app-control`, no rollback. `wrote 24` with
   `VERSION: unchanged` means the `$env:JARVIS_DESKTOP_EXE = $SetupNeutral` line is missing.
4. **Pycache is live:** read the tool's N and check PLANNED = 24 + N; it moved 231 → 232
   during this measurement (so `0H-inventory-frozen.json`, captured seconds after the
   receipt, records 232 / PLANNED 256 — that is the drift, not a contradiction).
5. **Do not reuse the wave-13 run folder**; this packet had no `CURRENT-RUN.txt` when the
   measurement started.

## 12. Receipts (all in this packet)

| file | bytes | SHA-256 |
|---|---|---|
| `0H-PREVIEW-wave14-frozen.txt` | 1818 | `A27614E68513D9A66F3E135B0F5CAAA2EA92F24E4F8F619015639F8E8DDF5864` |
| `0H-PREVIEW-wave14.txt` | 1811 | `CB4FB32A2DFF1D855C85E785191A2D8A5A1C394A7C238A1ECE02FFEB7F96995C` |
| `0H-inventory-frozen.json` | 2995 | `4C0364CCE138DCC118C75D30FBA41E742C42E4DC7573EA58FE27213991CCC518` |
| `0H-inventory.json` | 2988 | `7CA32490FC87110A54DBFD385D2629A41682A090D20C7C77372FB76758F34C5A` |
| `0H-d1-test.txt` | 2806 | `103C8DB54C26703E6F8FAB83206A324C1735AB0F83ECC370522163DB90CC1AF2` |
| `0H-refguard-default-ref.txt` | 1121 | `D99B3CD9604947A8C5BAABEC805E8B22D3DC656B5C8DA9FCB5A85F358524DE1F` |

`0H-inventory*.json` is the read-only script inventory (`inventory-wave14.py`) that names the
9 update rows the receipt truncates; it re-plans, it does not write. `run-d1-test.py` is the
single-test driver for the D-1 regression.

Re-read at 20:26 PT, as `frozen-ref.txt` asks: the file and `refs/pull/1219/head` still name
`24a3fc9b1`, the live `VERSION` still reads `0.2.443`, and there are still 27 backup folders.
If the PR head moves again before the merge, re-run 0H at the new tree before trusting any
number above.
