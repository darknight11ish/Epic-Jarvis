# Post-deploy static checks — expectations for wave 15 (live 0.2.445)

Script: `.dsh-scratch\WAVE15-DEPLOY-2026-11-10\post-deploy-checks-wave15.ps1`
(Windows PowerShell 5.1, read-only, exit 1 only when a row is FAIL).
Built for this deploy by a separate lane and RUN by Gate `postdeploy` with
`-Worktree`/`-FrozenSha`/`-FrozenTree`/`-PhoneVersion` passed by the gate; transcript in the run
folder as `10b2-post-checks.txt`.

## Expected AFTER the deploy (measured 2026-11-10 10:50 PT)

`SUMMARY: 27 PASS / 0 FAIL / 0 BLOCKED / 2 WARN` — exit 0.

- P0-SHA PASS (`HEAD=fd9cb5762 == frozen`, tree `be333667`); P0-MIXED PASS (VERSION 0.2.445 ==
  EXE 0.2.445, both past 0.2.444); P0-PHONE PASS (phone 0.2.4054 > 0.2.4047).
- The new wave-15 rows all PASS: `HUD-MODS` (all four HUD files exact size + sha256 vs the frozen
  tree), `DEF-062` (119,353 B, waiting words on both 202 branches, ON path retained), `DEF-063`
  (both sentences in the live presets note, `its coding lane` gone), `DEF-064` (new memory-door
  sentence, old phrase gone), `HUD-NAV` (return pill + one navigation ids, legacy strip gone),
  `HUD-TOKENS` (0 literal-colour fallbacks), `Q3-CAP` (one cap line; `size limit: 3072 MiB` in
  main.log and coding.log).
- The carried wave-14 rows all PASS (RM-1, GH-1/2, CR-1/2/3, MF-1/3, F2-1, HUD-1/2, W12-0/2,
  W14-PROJ/HUDK/EDIT/VAULT).
- **2 WARN by design** (not passes, read them): `A-SIZES` — 15/16 exact, `jarvis_skills.py`
  reads 49,320 B live vs 50,414 B in the repository's `backend/` copy, because that file is one of
  the patched base files whose live bytes are the base+patch result, not the repo copy; and `F5-1`
  the same size note. Both were WARN on wave 14 for the same reason. No other WARN is expected.

## What a PRE-DEPLOY run looks like (proof the rows bite)

Measured 10:22 PT on the old 0.2.444: `15 PASS / 12 FAIL / 1 BLOCKED / 1 WARN` — the version rows,
the four HUD files, DEF-062/063/064, HUD-NAV and the carried wave-14 HUD/vault rows were red.
Evidence: `predeploy-run-wave15.txt` in this folder.

A FAIL row after the deploy, or a WARN outside A-SIZES/F5-1, is a STOP to diagnose; BLOCKED and WARN
are never counted as passes. The row count and the exact SUMMARY are read from the script's own
output, never typed in from this document.
