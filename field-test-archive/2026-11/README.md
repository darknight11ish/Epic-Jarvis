# Field-test records, 2026-10-30 to 2026-11-14 — archived here on purpose

These are the **records behind field-test verdicts that already exist**, copied here from
`.dsh-scratch/` on 2026-11-14 so they stop living only on one PC.

## Why this folder exists

`.dsh-scratch/` is gitignored. The field-test records inside it were the **only** provenance for
several rows marked PASS or PARTIAL in `docs/FIELD-TEST-MATRIX-2026-10-11.md` and the later run
notes. An audit on 2026-11-14 found this, and the architect's ruling the same night was to **promote
or archive them into `docs/` before any workspace cleanup**. Without them, a PASS is an assertion
with nothing behind it — which this project does not accept.

So each file here is a verbatim copy. **Nothing was edited, reworded, trimmed or reformatted**, not
even to fix a typo. Where a record contradicts another record, both are kept: the disagreements are
reported in `FIELD-TEST-GAP-AUDIT-2026-11-14.md` (in the owner's Downloads folder) rather than
resolved here in the friendlier direction.

## What is in it

| folder | what it records |
|---|---|
| `FIELD-TEST-2026-10-30` | the earliest run in this set: `REPORT.md`, a matrix update draft, a drive plan |
| `FIELD-TEST-2026-11-01-GAPS` | the gaps found on 2026-11-01 |
| `FIELD-TEST-2026-11-02`, `-11-03`, `-11-04` | three consecutive runs, including a runbook of the features that were ready to drive |
| `FIELD-TEST-PRESETS-2026-11-03` | the presets plan from that day |
| `FIELD-TEST-WAVE6-2026-11-06`, `-WAVE7-2026-11-06` | waves 6 and 7 |
| `PIXEL-FIELD-TEST-2026-11-04` | the Pixel phone run |
| `WAVE12-INTEGRATION-2026-11-09` | wave 12 integration notes |
| `WAVE13-DEPLOY-2026-11-09` | wave 13's deploy packet and rebase notes |
| `WAVE14-DEPLOY-2026-11-09`, `WAVE15-DEPLOY-2026-11-10`, `WAVE17-DEPLOY-2026-11-11` | later deploy packets, gate diffs, rollback notes |

53 files, about 900 KB in total.

**`.dsh-scratch/wave18/` is deliberately not here.** It is the *live* working folder for the wave that
is still being deployed, and what sits in it is a mixture of drafts, pull-request bodies and work
queues that change hourly — archiving them would preserve noise and go stale the same night. When
that wave closes, anything in it that is genuinely a record gets promoted deliberately, by name,
rather than swept in by a wildcard. The folders carry their original names so a citation that says
"`.dsh-scratch/FIELD-TEST-2026-11-03/…`" can be matched to its copy here by name.

## What these are NOT

- **Not a claim that anything passes.** A record here says what was driven on a named build on a
  named day. The verdicts are in the matrix and the audit, not in this folder.
- **Not the whole of `.dsh-scratch/`.** The bulky parts of those folders were git worktrees and build
  copies — thousands of files each, and reproducible from the repository. Only the documents were
  worth keeping, and only the documents were copied.
- **Not a substitute for a new run.** A record from 2026-11-03 says nothing about the build installed
  on 2026-11-14.

## Where a new record goes

`docs/FIELD-TEST-MATRIX-2026-11-14.md` is the register for waves 14–18 and everything after. New
runs are written there. This folder is a fixed archive of what came before it.
