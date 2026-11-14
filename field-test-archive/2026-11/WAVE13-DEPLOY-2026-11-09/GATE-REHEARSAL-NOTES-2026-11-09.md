# Gate rehearsal notes - 2026-11-09 (read-only, before the wave-13 merge)

Lead's record of the read-only rehearsal of the wave-13 gate packet, run BEFORE the merge,
at the frozen head `32ba251d935d04c22bb83c9e0a6005e08d40b500` (tree
`46216eac7f1b0aedcbc8bf5dc7841aa6e76574a0`). The rehearsal ran a sandbox copy of
`deploy-gates-wave13.ps1` whose source is this packet's script (976 lines / 63,321 B,
sha256 `3F50191C565CE5117666AB0434497C0FC0773BB19C26590BAE65081DFEA35983`). Nothing here
was written by a gate: every gate below is read-only, and no live PC state changed.

Evidence: `D:\jarvis-scratch\WAVE13-GATE-REHEARSAL-2026-11-09\` - `logs\0C.log` to
`logs\0G.log`, `logs\parse-check.log`, `logs\baseline-readonly.txt`,
`logs\post-readonly.txt`, plus the sandbox scratch folder
`scratch\run-20261109-153147\`. The rehearsal agent did not write the promised
`GATE-REHEARSAL.md` before it finished; its logs are the verbatim evidence and this note is
the summarized record.

## Results (pre-merge)

| gate | result | reason quoted | meaning |
|---|---|---|---|
| 0C | STOP | "PR #1218 is OPEN" | correct: 0C requires #1218 CLOSED or MERGED. GO is only possible after the merge. #1217 is MERGED (`d6df4022`), but 0C checks #1218 first. |
| 0D | STOP | "no completed successful ci.yml run on the PR head either" | CI run `42720784442` on `32ba251d9` was still in progress. Once that run completes successfully, 0D GOes via the documented same-tree waiver (defers the main-run check). A post-merge GO is expected. |
| 0E | STOP | desktop target `d6df4022` != `32ba251d9` | correct and expected: only the wave-12 releases exist pre-merge. GO after the wave-13 desktop release names the merge sha. |
| 0F | STOP | "no setup asset for version  " (two spaces) | misleading message, not a missing asset: it ran with `$NewDesktopVersion` empty because 0E had STOPped. It also downloaded the 35 MB APK before stopping. Never run 0F before a 0E GO. |
| 0G | GO | HEAD=`32ba`; trackedChanges=0; gateRecordCall=True; toolBytes 182141=182141 | the tree and gate-record half of the packet is consistent at the frozen head. |

## Decisions taken from it (no gate-script edit tonight)

The gate script is the one artifact every derived number and every rehearsal log hashes to,
so it is NOT edited hours before the deploy. The two defects found are handled procedurally
and recorded for wave 14:

1. **Fresh run folder for the real deploy.** `CURRENT-RUN.txt` currently points at
   `run-20261109-1540` (the 0H dry-run evidence). Before Gate 0B of the real run, delete
   `CURRENT-RUN.txt` only - the old folder and its evidence stay - so the script creates a
   new run folder with no cached run vars of any kind.
2. **No out-of-order re-runs.** If a STOP after a GO forces a re-run from an earlier gate,
   delete `release-vars.json`, `assets.json` and `ref.txt` from the run folder first.
   `Load-RunVars` reads them only when the in-memory value is empty, so a stale file would
   otherwise feed an old version or asset to a later gate.
3. **Order 0E then 0F.** `0F` needs `0E`'s GO (both versions named) or it stops on an empty
   version after downloading the APK.
4. **Wave-14 backlog:** `WAVE14-BACKLOG-2026-11-09.md` section G records the fix shapes
   (STOP paths clear or ref-bind the run-vars; 0F empty-version guard; 0D names the run it
   waived; the script header's 14:05 fix-commit label should say `b3b300034`).

## Expected post-merge shape

- 0C GO once #1218 is MERGED.
- 0D GO once the required checks on the PR head have a completed successful `ci.yml` run
  (the same-tree waiver; the merge commit's tree must equal the frozen tree, which it does
  because `origin/main` `d6df4022` is an ancestor of the branch head).
- 0E GO only after `desktop-latest` names the merge sha; 0F GO only after `client-latest`
  names it and the assets verify.
