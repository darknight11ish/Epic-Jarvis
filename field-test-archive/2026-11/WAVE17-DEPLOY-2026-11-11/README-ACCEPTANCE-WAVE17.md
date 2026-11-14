# README-ACCEPTANCE-WAVE17.md - how the wave-17 deploy session runs the independent half

Written by the wave-17 acceptance re-take lane, 2026-11-11. This lane is not the
deploy session and does not perform the deploy. Lead decision Q3 re-issued the four
wave-16 working basenames under wave-17 names at the freeze, so this file is the
frozen `README-ACCEPTANCE-WAVE17.md`, and the frozen packet addresses that name.

All five files live in **`D:\jarvis-scratch\WAVE17-VERIFIER-2026-11-11\`**. The
table maps every role to the frozen name and to the working basename it was built
under before the freeze.

| role | frozen name (the packet uses this) | working basename before the freeze | what it proves | bytes | sha256 |
|---|---|---|---|---|---|
| verify | `verify_wave17_live.py` | `verify_wave16_live.py` | 15 rows (9 REQUIRED), read-only: the installed facts at file/hash level, the 336 `$SHIPPED` names, the 320 unchanged files, and a before/after snapshot that nothing moved while it ran | `94,391` | `25A3C3284FC7850B9381CEED0BFF6954A1792164CF7BF81113C62391BF5AF3BC` |
| expectations | `EXPECTATIONS-0H.md` | unchanged | the numbers the 0H dry run must print before `apply`: 1 added + 15 updated + 320 unchanged, `PLANNED = 16 + pycache` (247 at pycache 231), `VERSION: unchanged 0.2.446` | `24,680` | `88C1ABAFDFC8A25652A4F9650500C49A190623F8E8574C239E6791DFC92A5B95` |
| rollback | `ROLLBACK-WAVE17.md` | `ROLLBACK-WAVE16.md` | the exact way back to desktop 0.2.446 and phone 0.2.4059: the tool journal, the 4A gate backup, the one journalled `.pyc`, the pre-reseal state record, then the two installs | `26,789` | `2B1436DC6D780A3C5B0B0F31CFE74FC5674D02E3AE0A565AAB084510CB111071` |
| postdeploy | `post-deploy-checks-wave17.ps1` | `post-deploy-checks-wave16.ps1` | 19 ordered gates (12 REQUIRED), PowerShell 5.1, no token, no HTTP: the installed facts, the gate 4A/4A2 after-image, 31 tool + 4 plain gatepatch backups (plus 1 extra if 4A2 ran), and the new REQUIRED `16-LISTENERS` | `69,705` | `032B870B3FADD115FC151B66625165FD648D8F39298373C8C9A09442F8483543` |
| this README | `README-ACCEPTANCE-WAVE17.md` | `README-ACCEPTANCE-WAVE16.md` | how to run the other four, and how to read them | not self-hashed | the packet preflight records `$ReadmeBytes` / `$ReadmeSha256` |

**Deploy target: 0.2.448.** The desktop release is read at gate **0E** and never
typed into a pin; the union merge consumes Desktop release run 448, so 0.2.448 is
the expectation and 0E is the authority. Floors: desktop **0.2.446** (the release
live runs today, and the 0.2.446 merge `1087d81c1` is the base every "unchanged"
comparison uses), phone **0.2.4059**.

**Neither script makes an HTTP request.** The pairing token is never read, never
printed and never written. The only live code either one runs is a `py -3 -B`
import of the live registry, with bytecode writing off; `--no-import` /
`-SkipImport` turns it off and BLOCKS the rows that need it.

---

## 1. What this set proves - and what it deliberately does not

### 1.1 The claims a green run has measured

| claim | graded by |
|---|---|
| live `VERSION` is the release read at 0E (0.2.448 expected), past the 0.2.446 floor; the 0H log read `unchanged 0.2.446` before it | `1-VERSION`, `W17-VERSION`, 15-LEDGER |
| the 16 payload rows are byte-identical to the frozen tree: 15 rewritten + 1 added (`jarvis_review.py`), and the added file has no blob at the 0.2.446 base `1087d81c1` | `2-PAYLOAD`, `W17-PAYLOAD`, `W17-TREE` |
| all 336 `$SHIPPED` names exist live, and the 320 names this wave does not write still equal the 0.2.446 base | `2B-SHIPPED`, `W17-TREE`, 14-UNCHANGED (delegated to `W17-TREE`) |
| the live HUD is 778,164 B / `84812A4F...E6F2`, and the three tree copies are one identical blob | `3-HUD`, `W17-HUD` |
| the live `jarvis_gate.py` is the frozen after-image: 18 `"github_..."` rows, the seventeen-tool wording present, the wave-16 wording gone | `4-GATE4A`, `W17-GATE` |
| the owner's `jarvis-framework.toml` is byte-unchanged at 58,610 B / `209AC2FE...` and still lists the ten GitHub tools he enabled on 2026-11-10 | `7-GHTOOLS`, `W17-GH-TOOLS` |
| the live registry reads 74 switchable / 75 targets / 79 registered, and the live `TOOLS` carries the 17 GitHub tools (18 `github_*` names, counting `github_search`) | `6-SWITCH`, `7-GHTOOLS`, `W17-SWITCH`, `W17-GH-TOOLS` |
| the two-column cockpit CSS and the Edit-HUD exemption are in the live page | `5-COCKPIT`, `W17-COCKPIT` |
| the merge card and the fix-and-push card words are in the live source at their exact measured counts | `8-CARDS`, `W17-CARDS` |
| the claims gate's per-test cap is 900 s, and the shared credential denylist is wired as reviewed | `9-CLAIMS`, `10-DENYLIST`, `W17-CLAIMS-CAP`, `W17-DENYLIST` |
| the phone APK, when given, is newer than 0.2.4059, its versionCode matches its versionName, and its features file carries the two carried markers | `12-APK`, `W17-APK` |
| the restart left two LISTEN sockets on 4719: 127.0.0.1 and the tailnet address | `16-LISTENERS` |
| the backups a rollback needs exist: 31 tool + 4 plain gatepatch, and the newest plain gatepatch holds the 223,701 B / `A75B15C9...` before-image | `13-BACKUPS` |
| no live file changed while the verifier ran | `W17-READONLY` |

**The backup count, stated carefully.** After a train that ran 4A2 there are
31 tool + 4 plain gatepatch + 1 `-gatepatch-extra-` = **36** directories matching
`_jarvis-deploy-backup-*`. `EXPECTATIONS-0H.md` row 19 says 35, and that is the
4A2-absent arithmetic (31 + 4). The sheet's 13-BACKUPS grades the 31 and the 4
separately and never asserts a total, and the 4A2 check grades the extra folder
itself - so both documents are right about their own count.

The numbers that moved since wave 16, so a reader can tell a correct wave-17 run
from a correct wave-16 one: payload rows 19 -> 16 (15 rewritten + 1 added, and
the added file has no base blob at all), `$SHIPPED` 335 -> 336, unchanged
316 -> 320, registry 65/66/70 -> 74/75/79, GitHub tools 10 -> 17 (18 `github_*`
names), gate rows 10 -> 18, gate before-image 220,771 / `B410327D...` -> 223,701
/ `A75B15C9...`, gates 18 -> 19 (the new REQUIRED `16-LISTENERS`), and `apply`
writes 17 files instead of 20. These are structural facts of the frozen files,
not measurements taken by this README lane.

Two structural traps are worth knowing, because both would fail a CORRECT deploy
if a future edit got them wrong:

- **The added file has no base.** `jarvis_review.py` has no 0.2.446 blob, so it
  must sit in the payload table and be excluded from the 320 "unchanged"
  comparison. The verifier proves the exclusion instead of trusting it: if the
  filter ever widened, the correct deploy would print a BAD line and `W17-TREE`
  could not pass.
- **A `4A2` STOP is not a verdict.** The 4A2 carrier's own STOP is a bare
  `return` (exit 0). That is why the packet re-reads the live gate and the reseal
  belt refuses to record anything unless the file is the 4A2 image.

### 1.2 The independence caveat - write this into the receipt

These files are re-taken by a lane that is not the deploy session, and neither
script performs the deploy. That is what "independent" means here: an independent
**instrument**, not an independent **opinion**.

The expected numbers in `EXPECTATIONS-0H.md`, the pins in both graders and the
payload table inside them were derived from the same frozen tree the deploy
installs, by lanes reading the same packet documents. So:

- a row that compares live bytes to a table derived from the frozen head proves
  **the deploy installed that head**; it does not prove the head is right.
- a wrong expectation in the packet would be reproduced by both the deploy and
  its grader. Two confirmations of the same wrong thing are not evidence.
- the genuinely independent comparisons are the ones against a tree the deploy
  does **not** write: the 0.2.446 base `1087d81c1` for the 320 unchanged files,
  and the live **before**-image of the gate (223,701 B / `A75B15C9...`).

Do not describe a green run as "independently confirmed" without this caveat.

### 1.3 Deliberately not proven - say it out loud

1. **The cockpit PIXELS.** The CSS is proven present in the live page (248 px
   rail, 1081 px breakpoint, one column below it, `#left-toggle`, `#left-close`,
   Edit HUD exempt). Whether the installed WebView2 **draws** two columns is a
   screen and a pair of eyes - the owner's. BLOCKED by design.
2. **The desktop's bundled HUD copy.** The exe serves the page from inside
   itself; the live `jarvis_hud.html` is the file the backend serves. Only the
   installer's version and CI's own build tie the two together; this folder does
   not read inside the exe.
3. **A real GitHub action.** The 17 tools are proven present and switchable, the
   owner's TOML is proven byte-unchanged with the ten he enabled, and the card
   words are proven by exact counts. Driving a real read or a real merge needs
   the owner's token and the owner's yes - outside this folder by design.
   **The wave-16 assertion "none of the ten is on" is FALSE in wave 17**: the
   owner switched ten on in his TOML on 2026-11-10 (14 -> 24 `[tools].enabled`
   entries), so the check now proves the file is byte-unchanged and still lists
   them. It must never be "fixed" back to the wave-16 assertion.
4. **The owner's approval card on screen.** No card is raised here (no HTTP, no
   POST). Whether the live card reads right is the owner's sweep.
5. **The phone install itself.** `12-APK` / `W17-APK` prove the APK's version,
   its versionCode arithmetic and its feature text. Installing it and seeing the
   new text is the owner's hands. The phone **rollback** source is the measured
   0.2.4059 APK, 35,085,526 B, installed with `adb install -r -d` (a downgrade).
6. **The 0.2.448 installer's bytes.** CI publishes them; read them at 0F, never
   from this folder. The 0.2.446 **rollback** installer is known and measured:
   `D:\jarvis-install-test\setup-wave16.exe`, 5,788,167 B, FileVersion 0.2.446.
7. **The rollback itself.** `ROLLBACK-WAVE17.md` is a written, checked plan, not a
   measured receipt until it is run. `removed M = 1` is new in this wave (the one
   added payload path) and has not been exercised in a live rollback; the
   mechanism is code-read, not rehearsed.
8. **The 0H numbers were not executed by the re-take lanes.** They are derived
   from the tree; the 0H log must reproduce them. A 0H log that cannot be
   produced leaves the ledger BLOCKED and the acceptance incomplete.
9. **The 4A2 carrier's own file** (`gatepatch-extra-wave17.ps1`) is not one of the
   five pinned acceptance files. Its effect is proven by the live gate bytes+sha
   the packet re-reads before reseal and the post-deploy sheet re-reads after -
   not by a pin on the carrier script itself.

---

## 2. The order at the deploy moment

Run these from the deploy session, in this order. Each command is **one line**,
PowerShell 5.1 style (no `??`, no ternaries).

### Step 0 - the two previews, on the exact frozen bytes

Nothing is measured and nothing is written. Both must exit 0 **before** the set is
hashed (the freeze) and again from the frozen bytes (the deploy):

```powershell
py -3 -B "D:\jarvis-scratch\WAVE17-VERIFIER-2026-11-11\verify_wave17_live.py" --dry
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\jarvis-scratch\WAVE17-VERIFIER-2026-11-11\post-deploy-checks-wave17.ps1" -DryRun
```

`--dry` / `-DryRun` are the **only** non-measuring modes. The packet's
`artefacts` gate then re-proves all five pinned files; a stale file is a STOP
before any live write.

### Step 1 - before `apply`: the 0H expectation check

The packet's gate **0H** is the read-only dry run of `tools/reconcile_live_backend.py`,
taken after the app/backend stop and before `apply`. It writes nothing. Compare
every printed number with `EXPECTATIONS-0H.md`:

- `SHIPPED (336 files in $SHIPPED, flattened)`
- `to add: 1` and the one name is `jarvis_review.py`
- `to update: 15` and `unchanged: 320`
- `HUD DELTAS` (expected 234) / `already present` (expected 234), `to insert: none`
- `VERSION: unchanged 0.2.446`
- `PYCACHE: <N> stale .pyc file(s)` - a live counter, **never a pin**
- `PLANNED CHANGES: 16 + N` (247 at pycache 231)

If any **exact** value differs, STOP here: nothing has been written yet, which is
the cheapest possible moment to stop. Do not edit the gate to make a number pass.

### Step 2 - the deploy itself (the deploy session's run-book drives this)

`apply` -> `gatepatch` (4A) -> `quotes` (4B/4C) -> `gatepatch-extra` (4A2) ->
`reseal` -> `toml` -> `install-desktop` -> `install-phone` -> `restart` ->
`identity`.

| gate | what must be true, and what prints it |
|---|---|
| `apply` | `PLANNED 247` = 16 payload + pycache 231 (pycache is read at 0H, never pinned); `wrote 17` = 16 payload + `VERSION`; `VERSION: wrote <the version read at 0E>` (0.2.448 expected); it prints its own `BACKUP:` folder - the rollback journal |
| `gatepatch` (4A) | in: 223,701 B / `A75B15C9...`; the old 7,171 B / `6D76FE93...` block occurs **exactly once** and the new 12,060 B / `D781063F...` block **zero** times; out: 228,590 B / `564B1D87...` (PROVISIONAL, filled at freeze); prints `after: bytes=228590 sha=...` and every probe ok; its backup folder is the **only** valid `rollback-gate` source |
| `quotes` (4B/4C) | the live gate IS the 4A post-image (228,590 / `564B1D87...`). Its STOP is a bare `return` (exit 0), so grade the printed line, not the exit |
| `gatepatch-extra` (4A2) | runs **between `quotes` and `reseal`**; leaves the live gate at 231,256 B / `8EBFAEF4...` (PROVISIONAL); prints the carrier's `GO: extra gate patch ...; 5 fragments x1, old x0`; its own STOP is a bare `return` (exit 0), so the packet re-reads the live gate and the reseal belt must refuse anything but the 4A2 image |
| `reseal` | expected exit 1 with `RESULT: PARTIAL` and `VERIFY 0 of 336`; the gate stays `unprovable`; never rebaseline it |
| `toml` | 58,610 B / `209AC2FE...`; the ten owner-enabled GitHub tools still listed; record, never revert |
| `install-desktop` / `install-phone` / `restart` / `identity` | installer exit 0 and HKCU DisplayVersion matches the 0E version; adb install succeeds at the client-latest version; two listeners on 4719; identity PASS |

### Step 3 - after the restart: the PowerShell gate sheet

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\jarvis-scratch\WAVE17-VERIFIER-2026-11-11\post-deploy-checks-wave17.ps1" -MergeSha <MERGE-SHA> -Pr <PR-N> -Worktree "D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\wt" -RunDir "D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\run-<stamp>" -Log "D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\run-<stamp>\post-deploy-checks.txt"
```

Add the phone half when the CI-signed APK exists:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\jarvis-scratch\WAVE17-VERIFIER-2026-11-11\post-deploy-checks-wave17.ps1" -MergeSha <MERGE-SHA> -Pr <PR-N> -Worktree "D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\wt" -RunDir "D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\run-<stamp>" -Apk "<path to the CI-signed client APK>" -Log "D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\run-<stamp>\post-deploy-checks.txt"
```

### Step 4 - after the gate sheet: the independent receipt

```powershell
py -3 -B "D:\jarvis-scratch\WAVE17-VERIFIER-2026-11-11\verify_wave17_live.py" --merge-sha <MERGE-SHA> --pr <PR-N> --worktree "D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\wt" --json-out "D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\run-<stamp>\verify-wave17-live-result.json"
```

With the phone half, add `--apk "<APK path>"` (and `--apk-version` only if the
packet pins an exact version). Without `--json-out` the JSON lands **next to the
script**, named `verify-wave17-live-result.json`; the deploy must pass
`--json-out` so the receipt sits in the run folder.

The packet's `probes` gate runs this verifier **and** the standing wave-11
24-row regression script in front of it. That baseline is version-independent:
expect `24/24 PASS, 0 FAIL, 0 BLOCKED`, exit 0. A non-zero exit from either half
is a STOP. The gate also refuses a verifier whose sha256 is not the frozen
`verify` pin - never re-run with edited bytes.

### Step 5 - only if something failed: `ROLLBACK-WAVE17.md`

Read it before touching anything. The live-folder moves, in order: the tool
journal (`--rollback` restores the 15 rewritten payload files + `VERSION` and
deletes the 1 added path), the gatepatch backup (4A's `jarvis_gate.py`), the one
journalled gate `.pyc`, the pre-reseal `_jarvis-state.json` - then reinstall
desktop 0.2.446 and phone 0.2.4059.

`rollback-gate` restores the gate to 223,701 B / `A75B15C9...` and **refuses the
4A2 backup folder**: its bytes test wants 223,701, and the 4A2 backup holds
228,590. After 4A2 has run, one `rollback-gate` therefore undoes **both** gate
writes. To undo 4A2 alone, restore from the 4A2 backup first (it lands 228,590);
only then does `rollback-gate` accept the 4A backup.

---

## 3. Which verdicts must print

Grade the printed lines. These are the ones a good deploy shows:

| moment | must print | why it matters |
|---|---|---|
| previews | verifier: `rows: 15 (9 required)` then `--dry: listed the rows and measured nothing. No file was read, no import ran, nothing was written.`; sheet: `DRY RUN: nothing was read, imported or written. RESULT=DRYRUN` | proves the frozen bytes parse and list the right shape |
| 0H | the six EXACT lines: `SHIPPED (336 files...)`, `to add: 1`, `to update: 15`, `unchanged: 320`, `VERSION: unchanged 0.2.446`, `PLANNED CHANGES: 247` (at pycache 231) | the cheapest STOP: nothing is written yet |
| apply | `PLANNED CHANGES: 247 ...`, `wrote 17`, `VERSION: wrote <0E version>` (0.2.448 expected) | the payload set and the version the deploy actually wrote |
| 4A | `after: bytes=228590 sha=<...>` (PROVISIONAL) and every probe ok | the one block substitution that carries the new gate rows |
| 4A2 | the carrier's `GO: extra gate patch 231256 B / 8EBFAEF4...; 5 fragments x1, old x0` (PROVISIONAL), then the packet's re-read of the live gate before reseal | the non-block gate delta really landed |
| reseal | `RESULT: PARTIAL` and `VERIFY 0 of 336` with exit 1 | the expected standing outcome; never rebaseline |
| postdeploy | `WAVE17-POSTDEPLOY: RESULT=PASS REQUIRED=12 PASS=12 FAIL=0 BLOCKED=0 OPTIONAL=7 OPTIONAL_PASS=<n> MEASUREMENTS=<n> MERGE_SHA=<sha> PR=<n> AT=<time>` and `16-LISTENERS ... 2 LISTEN sockets on 4719: 127.0.0.1 and 100.75.21.228` | all 12 REQUIRED gates passed, including the restart proof |
| probes | wave-11 half: 24/24 PASS, 0 FAIL, 0 BLOCKED, exit 0 (the packet's standing expectation); verifier: `SUMMARY: ...`, `REQUIRED: 9 rows, 9 PASS, 0 not-pass (none)`, `RESULT: PASS - every REQUIRED row met its rule. This is a measured receipt for merge <sha> / PR #<n>.` | this wave's acceptance, plus the standing regression |
| verifier JSON | `"schema": "jarvis-wave17-live-verify/1"`, `"exit": 0`, `"required": {"rows": 9, "not_pass": []}`, `"read_only": {"http_requests": 0, "token_read": false, ...}` | the machine-readable receipt; no token anywhere in it |
| rollback (only if used) | `ROLLBACK: restored 247 overwritten path(s), removed 1 new path(s)` (247 at pycache 231) **and** `ROLLBACK OK - the live folder is back to its pre-deploy state; journal at <path>` | both lines are required; `removed` must be 1 |

`ROLLBACK OK - ...` is printed with a **hyphen**, not an em dash. Grade the string
that prints.

---

## 4. How to read a verdict - the non-pass rules

- **PASS is the only pass.** `BLOCKED`, `PARTIAL`, `NOT-TAKEN`, `SKIPPED` (and
  the verifier's `WARN`) are **never** passes. The project's 2026-10-11 rule.
- **A failed REQUIRED row is a STOP.** The sheet has 12 REQUIRED gates; the
  verifier has 9 REQUIRED rows. Any FAIL, BLOCKED, PARTIAL or NOT-TAKEN among
  them is not a green deploy - write down the row and its measured value.
- **Grade printed lines, never exit codes.** The project has shipped gates whose
  STOP is a bare `return` with **exit 0** (`quotes`, and the 4A2 step). A zero
  exit proves the process ended, not that the step passed. Conversely, `reseal`
  is expected to exit 1 with `RESULT: PARTIAL`; that is not a failure. Read the
  `GO` / `STOP` / `PASS` / `FAIL` / `NOT-TAKEN` lines and the row table.
- **A failed drift check is a finding, not an edit.** If the frozen bytes and a
  printed value disagree, the deploy is wrong or the freeze is stale. Never edit
  these files to make a run pass, and never grade a changed grader.
- **Advisory rows never set the gate, but an advisory FAIL is still a finding.**
  `12-APK` BLOCKED (no APK given) is an honest gap; `14-UNCHANGED` is BLOCKED by
  design because the 320-file comparison (640 git calls) is delegated to
  `W17-TREE`;
  `11-SHA-RECORD` is usually PARTIAL because nothing live records the merge sha.
  Say each one out loud in the receipt; none is a pass.
- **The 4A2 sub-check is never a pass by silence.** If the packet ships 4A2 and
  its pin is unfilled, the sheet prints `4A2 post-check: NOT-TAKEN` and the
  REQUIRED `4-GATE4A` row FAILS. If the packet ships no 4A2, both pins stay
  unset and the same NOT-TAKEN line FAILS - do not fill the pin with the 4A
  image to make it green.
- **The desktop pixels and the phone install are not script-gradable.** If the
  receipt claims them, it is claiming the owner's observation, not this folder's.

---

## 5. Where the evidence lands - and what must not be overwritten

Every printed verdict goes into the wave-17 run folder,
`D:\jarvis-scratch\WAVE17-DEPLOY-2026-11-11\run-<stamp>`:

| file | what it is |
|---|---|
| `0A-merge-proof.txt` | `verify-merge-commit.ps1` printing `RESULT=PASS` for the merge sha (two parents, parent1 = base tip, parent2 = frozen head, merge tree = frozen tree, PR MERGED, 7/7 required contexts). Gates 0C/0D would both pass a **squash** merge, which is why this proof is recorded separately |
| `0H-dryrun.txt` / `0H.txt` | the 0H dry run and its byte copy - the numbers `EXPECTATIONS-0H.md` grades |
| `4-apply.txt`, `4A-gatepatch.txt`, `4A2-gatepatch-extra-backup.txt`, `5-reseal.txt`, `6-toml.txt`, `6-identity.txt` | the live-write gates' printed logs, including the `BACKUP:` journal path and the 4A2 backup folder name |
| `post-deploy-checks.txt` | the sheet's printout (the `-Log` path): all 19 gates and the `WAVE17-POSTDEPLOY:` machine line |
| `verify-wave17-live-result.json` | the verifier JSON (`--json-out`): schema, every row's verdict + measurement, `counts`, `required`, `read_only`, `exit` |
| `10-probes-wave11.txt`, `10-probes-wave17.txt` | the packet's `probes` gate: the wave-11 24-row baseline and this wave's verifier |
| byte copies of `EXPECTATIONS-0H.md` and `ROLLBACK-WAVE17.md` | so the receipt names the exact documents this run graded against. Copy them in if the packet has not; never edit them |

**Do not overwrite the wave-16 folders.** They are this deploy's evidence
lineage and, for the phone, its rollback source:

- `D:\jarvis-scratch\WAVE16-VERIFIER-2026-11-10\` - the frozen wave-16 set and
  its struct notes;
- `D:\jarvis-scratch\WAVE16-DEPLOY-2026-11-10\` - the wave-16 run folders and
  artifacts, including the 0.2.4059 rollback APK at
  `run-20261110-211514\artifacts\jarvis-client-1087d81.apk` (35,085,526 B).

Wave 17 writes only under `WAVE17-*` folders and its own
`D:\jarvis-rehearsal\predeploy-wave17-<stamp>` insurance copy.

---

## 6. The freeze fill - eight values, the payload rows, five pins

This table is deliberately token-only: the bytes and hashes are filled at the
**freeze**, from the derive's JSON produced immediately before this set is
hashed. Do not hardcode a working size or hash here; they change when the values
are filled, and any edit to a pinned file invalidates its pin.

The order, and it is not reorderable:

1. Last edit to any of the five files.
2. Both previews (step 0) exit 0 **on those exact bytes**.
3. The derive run emits the JSON: the 16 payload rows and the eight
   bytes+sha256 values for the four graded files. Fill those rows in the grader
   tables and fill the eight values above.
4. Rename the three files (and this README) to their frozen names.
5. Hash the five files and fill the packet preflight pins:
   `$AcceptBytes`/`$AcceptSha256` (verify), `$PostDeployBytes`/`$PostDeploySha256`,
   `$RollbackDocBytes`/`$RollbackDocSha256`, `$ExpectDocBytes`/`$ExpectDocSha256`,
   and `$ReadmeBytes`/`$ReadmeSha256` for this README (which is why it does not
   hash itself).
6. The packet's `artefacts` gate re-proves all five. A stale file is a STOP
   **before any live write**. Never edit a file to match its pin; never grade a
   changed grader.

The payload rows are re-derived at the frozen head, not carried from the
provisional `213d35f92` table: three rows already moved once (the union head
moved), and `jarvis_recent_changes.py` shrank while `jarvis_owner_check.py` had
no wave-16 row. Re-derive every row; a stale row fails loudly.

The verifier's own freeze-pending register is five values + one path:
`GATE_BYTES`, `GATE_SHA`, `GATE_4A2_BYTES`, `GATE_4A2_SHA`, `PHONE_BEFORE`, and
`WORKTREE`. The sheet's is eight values: `$VersionWant`, `$GateBytes`,
`$GateSha`, `$Gate2Bytes`, `$Gate2Sha`, `$SwitchableWant`, `$TargetsWant`,
`$RegisteredWant`. `EXPECTATIONS-0H.md` and `ROLLBACK-WAVE17.md` anchor their
rows at the union tree and say every row is re-derived at freeze. Fill the
constants and the two payload tables only; no prose should need touching.

If the packet ships **no** 4A2, the two 4A2 pins stay unset and the REQUIRED
`4-GATE4A` row prints `4A2 post-check: NOT-TAKEN` and FAILS. That is deliberate:
an absent check is never a pass. The honest resolution is a recorded acceptance
gap, not a filled pin.

---

## 7. Rules for using this folder (so it stays independent)

- **Do not edit these files to make a run pass.** A failing row is the finding.
- **Do not add a `--force`, a skip flag or a "known good" override.** The only
  switches are `--dry` / `-DryRun` (measure nothing), `--no-import` /
  `-SkipImport` (skip the live import, which BLOCKS two rows), and optional
  paths. There is no way to make a row PASS without the bytes being right.
- **Do not run them before the install** and call the result acceptance: before
  the deploy, `1-VERSION` and `2-PAYLOAD` are **supposed** to fail.
- **Do not grade the deploy yourself.** Hand the two receipts (the sheet log and
  the verifier JSON) plus the 0H log to whoever is accepting, and let them read
  the rows.
- **Record the independence caveat** of section 1.2 in the receipt, next to the
  PASS line. The rows were authored from the same tree the deploy installs; they
  are an independent instrument, not an independent opinion.
