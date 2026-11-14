# Packet integration — wave 15 (2026-11-10)

The wave-15 deploy packet lives in `.dsh-scratch\WAVE15-DEPLOY-2026-11-10\` in the repository
root. It is a PACKET, not an auto-pilot: every gate is run as its own Windows PowerShell 5.1 process,
one at a time, and the gate's own printed text is the verdict (the exit code is not).

## Run it

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".dsh-scratch\WAVE15-DEPLOY-2026-11-10\deploy-gates-wave15.ps1" -Gate <name>
```

or, for one gate with the console teed into `gate-logs\<gate>.log` and only the verdict lines printed:

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".dsh-scratch\WAVE15-DEPLOY-2026-11-10\run-gate-wave15.ps1" -Gate <name>
```

`CURRENT-RUN.txt` names the ONE run folder this wave uses (`run-20261110-102051` for the real run);
never type a new stamp and never reuse a wave-14 folder. All gate evidence lands in that folder.

## Gate order actually used (26 gates, all run)

`0B, 0C, 0G, 0H, insurance, repair, be, 0D, 0E, 0F, stop, stopped, apply, quotes, reseal, toml,
install-desktop, install-phone, restart, identity, probes, postdeploy, preflight, awareness,
verify-wave8, rollback`

The three gates between the read-only block and the stop (`0D`, `0E`, `0F`) were run once BOTH
post-merge release workflows had succeeded, because gate 0F needs the published assets and gate
`apply` needs the neutral setup copy; that is the Q4 order (wait on the RELEASES, never on the
duplicate main CI). Everything before `stop` is read-only except the D: insurance copy.

## Who owns what

| file | owner | notes |
|---|---|---|
| `deploy-gates-wave15.ps1` | Lead (this session) | built from the wave-14 packet by `mk-gates-wave15.py`; every change carries a `# W15:` marker |
| `post-deploy-checks-wave15.ps1` | separate build lane, RUN by gate `postdeploy` | static rows; the packet references it and never creates it |
| `verify_wave15_live.py` (`D:\jarvis-scratch\WAVE15-VERIFIER-2026-11-10\`) | separate build lane, RUN by gate `probes` | 14 read-only rows; pins `EXPECTED_SHA=fd9cb5762` |
| `verify_wave14_live.py` (`D:\jarvis-scratch\WAVE14-VERIFIER-2026-11-09\`) | wave-14 lane | now the REGRESSION half; grades the wave-14 deploy |
| `frozen-ref.txt` | Lead | AUTHORITY for ref/tree; re-read at start and end |
| `WAVE15-RUNBOOK-2026-11-10.md` | docs lane | the human walk-through |
| `EXPECTATIONS-0H.md`, `GATE-DIFF-NOTES.md`, `POSTDEPLOY-EXPECT-WAVE15.md` | Lead/docs lane | derivation and expected values |
| `ROLLBACK-WAVE15.md` | Lead | anchor + procedure |
| `FACT-SOURCES-WAVE15.md` | Lead | every claim and where it was measured |
| `baseline-before-wave15.txt`, `q7-restoration.txt`, `final-state-wave15.txt` | Lead | before / Q7 / after snapshots |
| `gate-logs\`, `run-20261110-102051\` | the gates | raw evidence (the authority over any summary) |

## Reading rules

- GO/STOP/BLOCKED/PARTIAL/WARN: BLOCKED, PARTIAL and WARN are never counted as passes.
- The web-15 verifier's and the post-deploy checks' SUMMARYs are read exactly as printed; this packet
  never types a row count in place of the tool's own output.
- `0D` is SAME-TREE-VERIFIED (owner ruling Q4): the merge tree equals the PR head tree, the PR head's
  seven required checks are green, and BOTH post-merge release workflows succeeded; the duplicate
  main CI run is recorded once it finishes and never awaited.
- A missing `post-deploy-checks-wave15.ps1` or `verify_wave15_live.py` at its gate is BLOCKED, never a
  pass, and the packet never creates either file itself.
