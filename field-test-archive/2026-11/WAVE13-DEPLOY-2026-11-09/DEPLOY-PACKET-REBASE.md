# Wave-13 deploy packet re-base — every changed run value, with its evidence

Prepared 2026-11-09 12:20–12:30 PT, read-only, by a deploy-engineer subagent. This
document is the audit trail for `deploy-gates-wave13.ps1` in this same folder: it
records **the exact command and the observed output** behind every number the packet
now prints, and says plainly which numbers could **not** be derived offline.

**POST-AUDIT RE-PIN, 13:00 PT:** the deploy target is now
`7d892e277a42efe9a7b6d86a5b9623d65eff45fd` (tree
`ae49d2b8e0d38801046f9f4db2a606738409c857`), two commits on top of the original
`43b925f6…` freeze — see §9. Every `43b925f6` reference below is the derivation tree and
stays valid as history; §9 records what was re-measured and what did not move.

- **Source copied:** `.dsh-scratch\WAVE9-DEPLOY-2026-11-08\deploy-gates.ps1`
  — 759 lines, 46,839 B, sha256 `CD8964ADA8E483DD92F326C48577DB9F1851603B7ECED0FFFABAB8E83BB2BB1A`
  (re-hashed after the copy: **unchanged**; the wave-12 original was not edited).
- **Frozen tree every number comes from:**
  `.dsh-scratch\WAVE13-INTEGRATION-2026-11-09\wt` at
  `43b925f6239b8625982920abbf0eb57ade6394c5` (branch `integration/wave13-2026-11-09`,
  subject `fix(wave13): the COMPUTE panel names the card each loaded lane is on (F6)`),
  tree `905ab4497165a0dc48308be2d499f8b9cbb13379`, working tree clean (`git status
  --porcelain` printed nothing). Parent: `03034f43214503849899be56357565bc22d91daf`.
- **Build produced:** `deploy-gates-wave13.ps1` — see §7 for its hash and parse result.
- **Nothing was run against the live PC.** No gate, no apply, no install, no service
  restart, no `gh` mutation, no push, no release. The install tree
  (`...\jarvis-install-tree`) and the live backend (`...\Claude\Open jarvis files\
  Desktop program`) were never opened for writing and never touched. The two files
  this task was told to reference and never create
  (`post-deploy-checks-wave13.ps1`, `verify_wave13_live.py`) **were not created**.

---

## 1. How the numbers were derived (and why the method can be trusted)

Two independent routes, both from git objects only:

1. **The deploy tool's own parser.** `$SHIPPED` and `$PATCHES` are read from
   `scripts/apply-patches.ps1` at a ref with
   `tools/reconcile_live_backend.py`'s own `parse_powershell_list()` and
   `flatten_shipped()` — the same functions `plan_shipped` uses, so the list cannot
   drift from the tool's reading of it.
2. **Blob comparison, not file names.** For each `$SHIPPED` entry the blob sha at the
   old ref is compared with the blob sha at the new ref (`git ls-tree -r <ref> --
   backend/`). `add` = present in the new list only, `update` = same name, different
   bytes, `unchanged` = same bytes.

**Calibration (this is the important part).** The same computation was run on the
**wave-12 pair** `2644d57a2 → d6df4022`, where the recorded dry run in
`run-20261109-092148\0H-dryrun.txt` says:

```
SHIPPED (333 files in $SHIPPED, flattened):
  to add: 2          (jarvis_model_resources.py, jarvis_reversible_ui.py)
  to update: 18
  unchanged: 313
```

The method reproduced **exactly 2 / 18 / 313** and the same two added names
(E2 output below). A method that reproduces a recorded measurement on the previous
wave is the reason the wave-13 numbers below are marked HIGH confidence rather than
"probably".

### 1.1 Concurrent edit by the Lead (recorded, not hidden)

This file lives in a folder other agents were working in at the same time. While I was
re-basing, the **Lead edited `deploy-gates-wave13.ps1` at 12:35 PT** (their own comment
at the `postdeploy` gate says so): the gate no longer only prints the checks command, it
**runs** `post-deploy-checks-wave13.ps1` with `-Transcript` into the run folder and prints
the `SUMMARY:`/`VERDICT:` lines. That is a deliberate improvement and it is kept. Their
edit also left an 8-line duplicate of the packet's closing header block; I removed the
duplicate and re-verified the whole file (parse, 26 gates + `default`, one `param(`).
Everything else in the delivered file is the re-base described here. Because the file can
be edited after this document, §7 records the hash **as of 12:32:34 PT** — re-hash before
trusting it.

---

## 2. Evidence blocks (exact commands and the output they printed)

All commands are read-only. `<wt>` = `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\WAVE13-INTEGRATION-2026-11-09\wt`;
`43b925f6` = the frozen head, `d6df4022` = the wave-12 merge.
The helper scripts were written under `%TEMP%\wave13-rebase\` (throwaway, not in the
repo) and their bodies are reproduced here so they can be re-run.

### E1 — SHIPPED and PATCHES counts at both refs

```
py -3 -c "import subprocess,sys; sys.path.insert(0,r'<wt>\tools'); import reconcile_live_backend as R; t=subprocess.run(['git','-C',r'<wt>','show','43b925f6:scripts/apply-patches.ps1'],capture_output=True).stdout.decode(); print(len(R.parse_powershell_list(t,'SHIPPED')), len(R.parse_powershell_list(t,'PATCHES')))"
```
Output (same shape for `d6df4022: 333 179`):

```
334 180
```

### E2 — add / update / unchanged, by blob sha (this is the calibrated one)

```python
# derive.py  (run as: py -3 -B derive.py)
import subprocess, sys
from pathlib import Path
WT = Path(r"<wt>"); sys.path.insert(0, str(WT / "tools"))
import reconcile_live_backend as R

def git(*a, b=False):
    p = subprocess.run(["git", "-C", str(WT), *a], capture_output=True)
    assert p.returncode == 0, p.stderr
    return p.stdout if b else p.stdout.decode()

def ls(ref):
    d = {}
    for line in git("ls-tree", "-r", "-z", "--full-tree", ref, "--", "backend/", b=True).split(b"\0"):
        if line:
            meta, path = line.split(b"\t", 1)
            d[path.decode()] = meta.split(b" ")[2].decode()
    return d

def measure(a, b):
    sa = R.parse_powershell_list(git("show", f"{a}:scripts/apply-patches.ps1"), "SHIPPED")
    sb = R.parse_powershell_list(git("show", f"{b}:scripts/apply-patches.ps1"), "SHIPPED")
    ta, tb = ls(a), ls(b)
    add, upd = [], []
    for repo_path, live_name in R.flatten_shipped(sb):
        k = "backend/" + repo_path
        if ta.get(k) is None: add.append(live_name)
        elif ta[k] != tb[k]:  upd.append(live_name)
    return len(sb), sorted(add), sorted(upd), len(sb) - len(add) - len(upd)

for label, a, b in (("wave-12 calibration", "2644d57a2", "d6df4022"),
                    ("wave-13",             "d6df4022",  "43b925f6")):
    print(label, measure(a, b))
```

Output:

```
wave-12 calibration (333, ['jarvis_model_resources.py', 'jarvis_reversible_ui.py'], 18 names, 313)
wave-13             (334, ['jarvis_creator.py'], 20 names, 313)
```

The 20 update names at wave 13 (verbatim from the run):

```
hud-presets.js, jarvis-self-code.json, jarvis_accounts.py, jarvis_agent.py,
jarvis_asks_first.py, jarvis_auto_learn.py, jarvis_card_words.py, jarvis_claims.py,
jarvis_connect_account.py, jarvis_feature_catalogue.py, jarvis_feature_guide.py,
jarvis_github.py, jarvis_hud.html, jarvis_model_resources.py, jarvis_quick.py,
jarvis_reach.py, jarvis_recent_changes.py, jarvis_schedule.py,
jarvis_settings_registry.py, jarvis_tool_profiles.py
```

### E3 — HUD-delta rows (the tool's own `HUD DELTAS (N ... checked)` number)

`len(deltas)` in `plan_deltas()` is one entry per `(patch, patched base file)` whose
hunks ADD lines to one of the five `PATCHED_FILES`, plus the DELTA_TABLE's literal
rows (entries with no `.patch` of their own). Reproduced from the patch texts at each
ref:

```python
# derive2.py (excerpt)
for patch in R.parse_powershell_list(git("show", f"{ref}:scripts/apply-patches.ps1"), "PATCHES"):
    files = R.parse_patch_files(git("show", f"{ref}:backend/{patch}"))
    for target in R.PATCHED_FILES:
        if (files.get(target) or {}).get("added"):
            rows.append((patch, target))
lit = [(k, t) for k, targets in R.DELTA_TABLE.items()
       for t in targets if t in R.PATCHED_FILES and k not in set(patches)]
```

Output:

```
wave12  patches=179  deltaRows=211 {jarvis_hud.py:138, jarvis_gate.py:60, jarvis_extract.py:8, jarvis_models.py:2, jarvis_skills.py:3}  literalRows=23
frozen  patches=180  deltaRows=212 {jarvis_hud.py:138, jarvis_gate.py:60, jarvis_extract.py:8, jarvis_models.py:2, jarvis_skills.py:4}  literalRows=22
addedRows: [('skill-scan-wiring.patch', 'jarvis_skills.py')]      removedRows: []
```

`211 patch rows + 22 literal rows = 233` reproduces the wave-12 recorded
`HUD DELTAS (233 patch/file delta(s) checked)` — the 23rd literal in wave 12 was
`skill-scan-wiring.patch`, which was not yet in `$PATCHES` and is skipped as a literal
(its table entry is `hunks: True`, which the literal branch does not carry). At the
frozen ref that entry is a **patch row**, so the wave-13 total is `212 + 22 = 234`,
with `already present 233 + to insert 1`.

`skill-scan-wiring.patch` targets `jarvis_skills.py` only (`diff --git a/jarvis_skills.py`
in its own header) and its DELTA_TABLE entry is
`{"jarvis_skills.py": {"probes": SKILL_SCAN_WIRING_PROBES, "hunks": True}}` — a
five-hunk, four-region carrier, so the insert is supported and will not refuse.

### E4 — ready plug-ins

```
git -C <wt> ls-tree -r --name-only d6df4022  -- plugins/ready/   → 57 plugin.json
git -C <wt> ls-tree -r --name-only 43b925f6  -- plugins/ready/   → 58 plugin.json
```
`Compare-Object` on the two name lists printed one line: `creator-mode =>`.
`git show 43b925f6:plugins/ready/creator-mode/plugin.json` → `"module": "jarvis_creator"`,
`"install": "handler"`. `git show 43b925f6:jarvis-desktop/src/jarvis_hud.html` grepped
for `jarvis_creator` printed **nothing**, so the plugin is not `hud_wired` and lands in
`to add`.

### E5 — the TOML files (two different files, deliberately)

```
git -C <wt> cat-file -s d6df4022:backend/rebuilt/jarvis-framework.toml   → 144489
git -C <wt> cat-file -s 43b925f6:backend/rebuilt/jarvis-framework.toml   → 144925
git -C <wt> diff --unified=0 d6df4022 43b925f6 -- backend/rebuilt/jarvis-framework.toml
   → 13 added lines, 6 removed lines
   → sections 60 → 60,  key rows 339 → 340
   → the one new key row:  github_create_repo        = "ask"
```

The live owner TOML the `toml` gate reads is **not** either of these files: the deploy
tool's own `BESIDE` set (printed in `0H-dryrun.txt`) is `requirements.lock` and
`quiz_grader_cases.json` only, and the wave-12 run recorded the live file at
58,409 B / `9C6CDF76…C92D97`, which is far smaller than the repo's 144 KB copy. The
deploy does not write it, so that value is unchanged.

### E6 — the verify-wave8 "known drift"

```
git -C <wt> grep -i "coding preset" 43b925f6 -- backend/jarvis_recent_changes.py
```
Output: **nothing** (the file has no such string; the 2026-11-09 grep of the whole
`backend/` tree lists `jarvis_big_coder.py`, `jarvis_feature_catalogue.py`,
`jarvis_model_lanes.py`, `backend/README.md` — never `jarvis_recent_changes.py`).
`verify_wave8.py`'s row `self-update-history` demands `("Coding preset", "names a real
recent change")` and the answer is built from that module, so the row cannot pass.

### E7 — the 0E rule, exercised read-only against the real releases

The gate was run **only** from a throwaway copy under `%TEMP%` whose `$root` was
redirected to a fake folder, so its run folder was created there and not in this
scratch folder:

```
desktop=Jarvis Desktop - latest (0.2.442) target=d6df40225de7c7400b302744f10043f284496cd5 prerelease=False
phone=Jarvis for Android 0.2.4035 (main @ d6df402) target=d6df40225de7c7400b302744f10043f284496cd5 prerelease=True
desktopTarget=d6df40225de7c7400b302744f10043f284496cd5 phoneTarget=d6df4022… ref=43b925f6…
STOP: desktop release targetCommitish (d6df4022…) is not $Ref
```

Two things this proves: (a) `targetCommitish` is a **sha** today, not a branch name,
so the strict comparison is the right one; (b) both releases still name the wave-12
merge, so wave 13 must re-cut them — the gate stops, as designed.

### E8 — PowerShell 5.1 parse (the owner's shell)

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File parse51.ps1 -Path <the wave-13 script>
```

```
PSVersion=5.1.26100.9711
tokens=5259
PARSE_ERRORS=0
```

### E9 — no-argument invocation creates nothing

A copy under `%TEMP%\wave13-rebase\noargs\` with `$root` redirected to a fresh empty
folder was run with **no arguments**:

```
filesBefore=0
<26 gate entries + 1 header line printed (27 lines)>
filesAfter=0
created=0
```

A second run with `-Gate bogus` created only
`fake-root\.dsh-scratch\WAVE13-DEPLOY-2026-11-09\{CURRENT-RUN.txt,run-…\RUN.txt,artifacts\}`
— i.e. everything stays under the redirected root. The real
`.dsh-scratch\WAVE13-DEPLOY-2026-11-09` folder received **no** `CURRENT-RUN.txt` and
**no** run folder from these tests.

### E10 — the wave-13 static checks, run read-only (they confirm the "before" state)

After the Lead's 12:35 PT edit, `-Gate postdeploy` (still from the throwaway copy under
`%TEMP%`) ran the real `post-deploy-checks-wave13.ps1` against the live folder. Its
decisive lines:

```
IDENTITY sha=43b925f6239b8625982920abbf0eb57ade6394c5 VERSION=0.2.442 EXE=0.2.442 phone=(not passed)
PASS    P0-SHA    HEAD=43b925f6… == frozen
FAIL    P0-MIXED  EXE=0.2.442 is not past the 0.2.442 floor; VERSION=0.2.442
BLOCKED P0-PHONE  phone version is only readable from client-latest … Pass -PhoneVersion <x>
FAIL    A-SIZES   exact 2/13; differ: … jarvis_skills.py 42416/50414 … absent: jarvis_creator.py (want 29935)
FAIL    CR-2      ABSENT jarvis_plugins\creator-mode\plugin.json (want 401 B, 2 markers)
SUMMARY: 2 PASS / 14 FAIL / 1 BLOCKED / 1 WARN
VERDICT: FAIL
```

This reproduces `DEPLOY-PLAN-WAVE13.md:172-173`'s recorded pre-deploy pattern **exactly**
(`2 PASS / 14 FAIL / 1 BLOCKED / 1 WARN`), so it is an independent confirmation that the
live PC is still the wave-12 "before" state at 12:32 PT: live `VERSION` and the installed
EXE are both **0.2.442**, the live `jarvis_skills.py` is 42,416 B against the frozen
50,414 B (the F5 body is absent), and `jarvis_creator.py` plus
`jarvis_plugins\creator-mode\plugin.json` are **absent** — exactly the two "new" items
the packet's `add 1` and `to add 1` describe. It wrote only
`10b2-post-checks.txt` / `10b2-post-checks-stdout.txt` into the throwaway run folder under
`%TEMP%`; nothing under the live folder (the script's own header: the ONE file it can
write is `-Transcript`).

---

## 3. The changed run values (the table)

Confidence: **HIGH** = derived from git objects and (where the same shape exists)
calibrated against a recorded wave-12 measurement; **MEDIUM** = derived, but depends on
one live assumption that the run itself must confirm; **LIVE** = cannot be derived
offline, the packet reads it at run time instead of asserting it.

| run value | wave-12 value | wave-13 value | evidence (command → output) | confidence |
|---|---|---|---|---|
| `$scratch` | `$root\.dsh-scratch\WAVE9-DEPLOY-2026-11-08` | `$root\.dsh-scratch\WAVE13-DEPLOY-2026-11-09` | this folder exists and holds `DEPLOY-PLAN-WAVE13.md`; the wave-12 folder's `CURRENT-RUN.txt` still points at `run-20261109-092148`, so the two runs cannot share a folder | HIGH |
| `$Pr` | 1217 | **1218** | `DEPLOY-PLAN-WAVE13.md:1` "Wave-13 deploy plan (PR #1218)" | HIGH |
| `$PrevPr` | 1216 | **1217** | 0C live read: `gh pr view 1217` returns MERGED; `#1217`'s merge commit `d6df40225de7c7400b302744f10043f284496cd5` is an ancestor of the frozen head (`git merge-base --is-ancestor` → exit 0) | HIGH |
| `$PhoneFloor` | 4028 | **4035** | `run-20261109-092148\WAVE12-RESULT-2026-11-09.md:23` "phone released + installed: 0.2.4035" and `release-vars.json` `"phone": "0.2.4035"`; `_where.py`/plan agree | HIGH |
| `$DesktopFloor` | `'0.2.441'` | **`'0.2.442'`** | same record line 20 "desktop released + installed: 0.2.442"; `4-apply.txt:53` "VERSION: wrote 0.2.442 (was 0.2.441, from the installed desktop)" | HIGH |
| `$Ref` | `''` (filled by 0B) | **`'43b925f6239b8625982920abbf0eb57ade6394c5'`** (pre-filled) | `git rev-parse HEAD` in the frozen worktree → that sha; branch `integration/wave13-2026-11-09`; subject names F6 | HIGH |
| `$FrozenHead` (new) | — | `43b925f6…` | same as above | HIGH |
| `$FrozenTree` (new) | — | `905ab4497165a0dc48308be2d499f8b9cbb13379` | `git rev-parse '43b925f6^{tree}'` → that sha; Gate 0B compares the live value with it and STOPs on a mismatch | HIGH |
| `$expectedShipped` | 333 | **334** | E1 → `334` | HIGH |
| dry-run SHIPPED breakdown | `333 = add 2 + update 18 + unchanged 313` | **`334 = add 1 + update 20 + unchanged 313`** | E2 → `(334, ['jarvis_creator.py'], 20 names, 313)`; the wave-12 half of the same script reproduced 2/18/313 exactly | HIGH |
| the one added module | `jarvis_model_resources.py`, `jarvis_reversible_ui.py` | **`jarvis_creator.py`** | E2; `backend/_where.py` comment at the frozen ref names it "Creator mode (jarvis_creator.py, 2026-11-09, Wave 13)" | HIGH |
| the 20 updated modules | 18 names | list in §2 E2 | E2 | HIGH for the count (calibrated); MEDIUM for the names (assumes live == the wave-12 merge tree, which `5-reseal.txt` "VERIFY: 0 of 333 shipped file(s) still differ" supports) |
| HUD DELTAS rows | `233` checked, `0` to insert | **`234` checked: 233 already present + 1 to insert** | E3 → 212 patch rows + 22 literal rows = 234, and the same arithmetic gives 233 for wave 12 | HIGH |
| the one insert | none | **`skill-scan-wiring.patch → jarvis_skills.py`** | E3 `addedRows`; the patch touches only that file; its DELTA_TABLE entry is `hunks: True` (5 hunks) so the insert is supported | HIGH |
| PYCACHE | 229 | **not predicted — read the tool's line** (wave-12 measured 229) | `0H-dryrun.txt:35` `PYCACHE: 229 stale .pyc file(s)` — a count of stale `.pyc` in the live `__pycache__` folders, which no git object can answer | LIVE |
| READY PLUG-INS | `31 present, 0 to add, 26 already wired` | **`31 present, 1 to add, 26 already wired`** | E4: 57 → 58 ready folders, the diff is `creator-mode`, its module is `jarvis_creator`, and the served HUD does not call `jarvis_creator.install(` | HIGH for "1 to add" and for the 58 total; MEDIUM for 31/26 (live counts, unchanged by wave 13) |
| PLANNED (dry run) | `249 = 2 + 18 + 0 + 0 + 229` | **`22 + pycache`** (`251` if pycache is still 229) | arithmetic from the rows above; the tool prints its own total, the packet tells the operator to check `1 + 20 + 1 + 0 + pycache` | HIGH for the arithmetic, LIVE for the total |
| PLANNED (apply) | `250 = 2 + 18 + 0 + 1 + 229` | **`23 + pycache`** (`252` if 229) | same, plus the VERSION marker (1) — see next row | HIGH |
| `wrote N` at apply | `21` (`= 2 + 18 + 0 + 1`) | **`23` (`= 1 + 20 + 1 + 1`)** | `4-apply.txt:66` "wrote 21 file(s)" = add 2 + update 18 + insert 0 + version 1; the same formula on the wave-13 rows | HIGH |
| VERSION marker | `wrote 0.2.442 (was 0.2.441)` | **`wrote $NewDesktopVersion (was 0.2.442)`** | `4-apply.txt:53`; the tool reads the marker from `JARVIS_DESKTOP_EXE` (the new setup) — `apply` sets it, `0H` does not | HIGH |
| reseal count | `VERIFY: 0 of 333` | **`VERIFY: 0 of 334`** | E1; `5-reseal.txt` quotes the tool's own `$SHIPPED` count | HIGH |
| patch stack (`$PATCHES`) | 179 | **180** | E1 `334 180`; the diff is `skill-scan-wiring.patch` (E3) | HIGH |
| TOML gate (live owner file) | `58409` B / `9C6CDF76…C92D97` | **unchanged** (same bytes and hash) | E5: the deploy never writes it; repo copy differs but is a different file | HIGH that it is unwritten; LIVE for the value |
| repo TOML (for the record) | 144,489 B, 60 sections, 339 key rows | **144,925 B, 60 sections, 340 key rows** (`+github_create_repo = "ask"`) | E5 | HIGH |
| repair-gate live numbers | `~220771 B`, `B410327D…` | **unchanged** | the wave-12 `repair`/`quotes` output shows the same live `jarvis_gate.py` before and after the apply; no wave-13 patch or delta targets `jarvis_gate.py` (E3: 60 rows before, 60 after) | HIGH |
| preflight rows | GO text said "exactly the 7 standing FAIL rows" (the run MEASURED 35 pass / 9 fail / 3 warn / 5 skipped) | **the same 35/9/3/5 baseline, named by row, with a possible new row for `skill-scan-wiring.patch`** | `run-20261109-092148\preflight-after-wave9.txt` (9 FAIL rows listed in §5) | MEDIUM — see §5 item 7 |
| verify-wave8 expectation | 27 rows; accept `27/0` or `26/1` on `self-update-history` | **27 rows; expect `26/1` on `self-update-history`** (the packet still accepts `27/0`) | E6 → the string "Coding preset" is absent from `backend/jarvis_recent_changes.py` at the frozen ref | MEDIUM (the answer text is produced by a read route, not by the file) |
| acceptance script (`probes`) | `.dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py` | **`verify_wave13_live.py`** — candidates: this folder, the wave-13 integration folder, then `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09`; **STOP if absent**; run with `--json-out` only | the file EXISTS at `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09\verify_wave13_live.py` — 63,333 B, sha256 `F41B4B71…A4AC337`, 13 rows (matches `DEPLOY-PLAN-WAVE13.md:176-179`); its argparse has `--json-out --timeout --chat-timeout --restore-timeout --allow-guarded --dry` and **no `--ref`/`--repo`**, so the gate passes none of those | HIGH |
| post-deploy checks | (not referenced by the packet) | **new gate `postdeploy` finds `post-deploy-checks-wave13.ps1` (this folder, then `D:`), RUNS it read-only with `-Transcript` in the run folder, and prints its `SUMMARY:`/`VERDICT:` lines; it never creates the file** | the file EXISTS at `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09\post-deploy-checks-wave13.ps1` — 29,890 B, sha256 `DCD7A37F…B2B4E`, 607 lines, PS 5.1 parse clean (plan, and re-hashed here); its own defaults are `-FrozenSha 43b925f6…`, `-VersionFloor 0.2.442`, `-PhoneFloor 0.2.4035`, `-PhoneVersion` empty → the gate passes `-PhoneVersion $NewPhoneVersion` when 0E has recorded it. **LEAD EDIT 12:35 PT** turned the pointer into a runner; see §1.1 | HIGH |
| `release-vars.json` write point | written BEFORE 0E's checks (a STOPped 0E left the old versions for later gates) | **written only after every 0E check passes** | E7/sandbox: on a fresh redirected root a STOPped 0E wrote `0E-client-latest.json`, `0E-desktop-latest.json`, `0E-release-identity.txt` and **no** `release-vars.json` | HIGH |
| insurance folder prefix | `D:\jarvis-rehearsal\predeploy-wave11-$stamp` | **`predeploy-wave13-$stamp`** | the wave-12 run recorded `predeploy-wave11-20261109-092219` (`1-insurance.txt`), a stale prefix | HIGH |
| install-desktop launch copy | `...\jarvis-install-test\setup-wave11.exe` | **`setup-wave13.exe`** | wave-12 used `setup-wave11.exe` for a 0.2.442 installer; the name is a run label only | HIGH |
| 0F neutral copy | `jarvis-desktop-wave11-setup.exe` | **`jarvis-desktop-wave13-setup.exe`** | same | HIGH |
| evidence file names | `10-probes-wave11.txt`, `preflight-after-wave9.txt`, `12-verify-wave8-wave9.*`, `verify_wave8_wave9.py` | **`…-wave13.txt` / `preflight-after-wave13.txt` / `12-verify-wave8-wave13.*` / `verify_wave8_wave13.py`** | the wave-12 names were already stale by one wave; re-basing removes the ambiguity | HIGH |
| 0C previous-PR state | #1216, expect CLOSED or MERGED | **#1217, expect MERGED as `d6df4022`; CLOSED still accepted; only OPEN stops** | `WAVE12-RESULT-2026-11-09.md:10` merge commit; task instruction; live `gh pr view 1217` → MERGED | HIGH |
| 0E release targeting | both compared, guard `-and $Ref` | **explicit empty-ref STOP + both compared trimmed/case-folded** | E7 shows the gate reading both targets and stopping correctly | HIGH |
| run folder / CURRENT-RUN | `$scratch\run-yyyyMMdd-HHmmss`, path cached in `$scratch\CURRENT-RUN.txt` | **same pattern, new `$scratch`** | E9: `run-20261109-122537` created under the redirected root only | HIGH |
| 0D required checks | 7 (`rust frontend backend backend-windows credential-manager powershell-5 phone-unit-tests`) | **unchanged 7** | the list is in the packet and matches the ruleset recorded in `CLAUDE.md` | HIGH |

---

## 4. Values I could NOT recompute confidently, and why

1. **PYCACHE (wave-12: 229).** It counts stale `.pyc` files inside the *live*
   `__pycache__` folders. No git object contains that. The packet now says "read the
   tool's own line; wave-12 measured 229" and folds it into the PLANNED arithmetic
   instead of asserting a total.
2. **READY PLUG-INS `31 present` / `26 already wired`.** `present` is
   `<live>\jarvis_plugins\<name>` and `wired` greps the *live* `jarvis_hud.py`; both
   are live reads. What is derived: the total (58, E4), the new name (`creator-mode`),
   and that it is **not** wired, hence `to add: 1`. The 31/26 halves are copied from
   the wave-12 measurement on the assumption that wave 13 adds no plug-in other than
   `creator-mode` (E4 confirms) and removes none.
3. **The exact 20 update NAMES.** The blobs are compared between the wave-12 merge and
   the frozen head, which is equivalent to comparing against live only while live still
   equals the wave-12 tree. `5-reseal.txt` records `VERIFY: 0 of 333 shipped file(s)
   still differ`, and the wave-12 calibration reproduced the tool byte-for-byte, so
   this is strong — but a hand edit in the live folder would change the tool's list.
4. **The two new release versions.** `0.2.443`-class / `0.2.4042`-class are the next
   cuts; the packet deliberately reads them from `desktop-latest` / `client-latest` and
   never presumes them (E7 shows the current ones are still 0.2.442 / 0.2.4035).
5. **The live TOML bytes/hash and the repair-gate size/hash.** Both are properties of
   the live folder. Unchanged by this deploy (E5, and the gate/hud delta counts are
   identical before and after), but only the run can read them.
6. **The preflight row count.** The 9 FAIL rows are a live measurement against the
   live backend, and wave 13 adds a patch to the stack, so a row may appear or flip.
   The packet therefore names the baseline rows and forbids comparing totals.
7. **Whether `verify_wave8` is 26/1 or 27/0.** E6 proves the demanded string is absent
   from the module that builds the answer, but the answer itself comes through a read
   route; the packet accepts either shape and requires the drift to be recorded.
8. **Whether `origin/main`'s tree will be the frozen tree.** That depends on the merge
   (it will be, if #1218 is merged with a merge commit and nothing else lands on top).
   Gate 0B compares the trees and STOPs otherwise — the value is not assumed offline.
9. **The two parallel deliverables — later than the first cut of this packet.** At 12:20 PT
   both landed at `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09\`, **not** in this folder:
   `post-deploy-checks-wave13.ps1` (29,890 B, 607 lines) and `verify_wave13_live.py`
   (63,333 B, 13 rows). I read both read-only to get their **real** interfaces, and the
   packet was corrected to match: the `probes` gate no longer passes `--ref`/`--repo`
   (that script has no such arguments — argparse would have exited 2), and the
   `postdeploy` gate tries both paths and passes `-PhoneVersion` when 0E has recorded it.
   What remains unverified is what happens when they actually run against the live PC —
   they were not executed here.

---

## 5. Wave-12 semantics that do NOT transfer to wave 13

1. **`$Ref` is no longer blank.** Wave 12 expected the operator to run 0B and paste the
   merge sha into `$Ref`. Wave 13 pins the frozen head at the top, so the precedence in
   `Load-RunVars` had to change: a `ref.txt` written by 0B **wins over the pinned
   default** (otherwise 0E would demand that the releases name a pre-merge commit), and
   a ref the operator typed by hand still wins over `ref.txt`.
2. **Gate 0B's job changed from "discover" to "prove".** It now fetches, compares
   `origin/main^{tree}` with the frozen tree, STOPs on a mismatch, and only then moves
   the deploy worktree. A main that moved elsewhere can no longer silently re-target
   the run.
3. **0E's old guard was vacuous.** `if ($Ref -and $d.targetCommitish -ne $Ref)` skipped
   the comparison whenever `$Ref` was empty — which is now never, but the shape was
   wrong: a blank ref used to mean "no check", and it must mean STOP. The gate now
   STOPs on an empty ref and compares both targets trimmed and case-folded (E7).
   Note: because `targetCommitish` is currently a sha, a release cut from a **branch
   name** would STOP rather than pass — that strictness is deliberate.
4. **0H's "STOP on any `to insert`" is now wrong.** Wave 12 had `0` inserts. Wave 13
   expects **exactly one** (`skill-scan-wiring.patch`), which is the F5 delivery. The
   STOP condition was narrowed to "any insert that is NOT that one"; a blanket "no
   inserts" would have made a successful F5 deploy look like a failure.
5. **The apply arithmetic moved.** `wrote 21` (`2+18+0+1`) became `wrote 23`
   (`1+20+1+1`). Anyone checking against the wave-12 number would call a correct run
   wrong.
6. **`apply-patches.ps1`'s own stack grew to 180 patches.** Any step quoting "179
   patches" is now stale; the new one is `skill-scan-wiring.patch`.
7. **The preflight expectation in the packet was already wrong in wave 12.** Its GO
   text said "exactly the 7 standing FAIL rows" while the run measured **9**:
   `appearance.patch` (216/334), `gpu-offload.patch` (61/94), `show-card-timer.patch`
   (10/60), `model-recommendations.patch` (8/16 = F7, new that wave),
   `cloud-honesty.patch` (3/80), `attached-file.patch` (not present), and the three
   "`jarvis_gate.py` / `jarvis_hud.py` / `jarvis_skills.py` has changed since the
   installer wrote it" rows. Wave 13 now names that measured set, adds that
   `skill-scan-wiring.patch` may add a row, and keeps "compare row NAMES, never a
   total". (The plan's own line "8 standing FAIL rows" is the 8 without F7; the packet
   states the measured 9 instead of either remembered number.)
8. **0E used to hand its values to later gates before proving them.** The wave-12 gate
   wrote `release-vars.json` *above* its target/version checks, so the wave-12 run's
   stopped 0E (09:22 PT, stale releases) left `desktop=0.2.441 / phone=0.2.4028` in the
   run folder, and `Load-RunVars` would have fed those to `install-phone`, `apply`,
   `awareness` and `verify-wave8` had the operator not re-run 0E. Wave 13 writes that
   file **only after every check passes**; a stopped gate now leaves no consumable
   values. Its evidence files (`0E-desktop-latest.json`, `0E-client-latest.json`,
   `0E-release-identity.txt`) are still written before the checks, because they record
   what the gate *saw*, including a stale state.
9. **The wave-11 acceptance script is no longer a substitute.** It grades the 24
   baseline rows and knows nothing about F2/F5/reminders/GitHub truth/creator
   mode/memory-fault. Running it and printing a green 24/24 would be a false pass, so
   the gate STOPs if `verify_wave13_live.py` is absent.
10. **A new ready plug-in now rides along.** Wave 12 added `0` plug-ins; wave 13 adds
    `creator-mode` via the tool's plug-in step. That is a live write that is **not** in
    `wrote N` and **not** in PLANNED — a reader checking only those numbers would miss it.
11. **The owner's TOML is not updated, and wave 13 adds a tier row to the repo copy.**
    `github_create_repo = "ask"` exists in `backend/rebuilt/jarvis-framework.toml`
    (and the base), not in the owner's 58 KB live file; the deploy never writes that
    file. `DEPLOY-PLAN-WAVE13.md:185-188` states the same and names the fallback: an
    unknown action still asks through `jarvis_gate.UNKNOWN_TIER` (`"ask"`), so the live
    behaviour is still a card. If the owner wants the row in his own TOML, he edits it.
    This is the same shape as wave 12, but it matters more now because the new row is a
    write action on GitHub.
12. **The rollback/rehearsal documents were still being written while this packet was.**
    At 12:31:57 PT, after the first cut of this file, a parallel agent landed
    `$scratch\ROLLBACK.md` (7,642 B) — so the `rollback` gate's path is now valid. Its
    stated baseline is an independent confirmation of three numbers above: backend
    `0.2.442` sealed from `d6df4022`, desktop `0.2.442`, phone `0.2.4035` /
    `versionCode 1000004035`, and the owner TOML at `58,409 B` /
    `9C6CDF76…C92D97`. `REHEARSAL.md`, `CHECKLIST.md` and `deploy-notes.md` (all of which
    the wave-12 folder carried) are still absent; those are **not** this packet's to
    create (this task was exactly two files).
13. **The 0H dry run must still run BEFORE `install-desktop`.** The VERSION marker comes
    from the *installed* desktop at 0H time (0.2.442, unchanged → `0` in the formula)
    and from the new setup at apply time (the installer named by
    `JARVIS_DESKTOP_EXE`). If someone installs the new build first, the dry run flips
    `beside+version` from 0 to 1 and every total above shifts by one.

---

## 6. What I did NOT verify (honest list)

- I did **not** run `reconcile_live_backend.py` in any mode against the live folder.
  Every dry-run number above is a derivation, not a measurement; the calibration on the
  wave-12 pair is the evidence that the derivation matches the tool.
- I did **not** run `run_preflight_live.py`, `check_live_version_identity.py`,
  `verify_wave8.py`, `check_live_awareness_sanity.py` or any acceptance script — they
  need the live backend, which was off limits.
- I did **not** run `post-deploy-checks-wave13.ps1` or `verify_wave13_live.py` at all — I
  only read their `param`/`argparse` blocks read-only, to get the real interfaces right.
  Both files are later than my first pass: they landed at
  `D:\jarvis-scratch\WAVE13-PREFLIGHT-2026-11-09\` at 12:20 PT, not in this folder.
- I did **not** confirm the wave-13 merge commit (it does not exist; #1218 is still OPEN
  with head `43b925f6`); `$Ref` is pinned to the frozen head and 0B proves the tree.
- I did **not** read the live `VERSION`, TOML, `jarvis_gate.py` or `__pycache__`
  folders; the numbers quoted for them are the wave-12 records, explicitly labelled. A
  parallel agent's `PRE-DEPLOY-BASELINE.txt` (12:22 PT) independently records the live
  VERSION at **0.2.442**, `jarvis_skills.py` 42,416 B with `_extra_findings` **0 hits**,
  and `jarvis_model_resources.py` 44,202 B with `lane_port` **0 hits** — the "before"
  state this packet's F5 insert and F6 update are meant to change.
- PowerShell 5.1 was used only to **parse** the script and to run it with no arguments,
  `-Gate bogus`, `-Gate postdeploy` and `-Gate 0E` from throwaway copies under `%TEMP%`
  whose `$root` was redirected to an empty folder. `-Gate postdeploy` (after the Lead's
  edit) executed the **read-only** static checks against the live folder and wrote its
  transcript only into the throwaway run folder (E10). No gate that writes to the live PC
  was executed, and nothing in the live folder was written or restarted.
- The TOML row counts (339 → 340 keys) are line-shape counts of the repo copy, not a
  parser's idea of a TOML key; they are quoted as "rows" only as a size-comparison aid.

---

## 7. Deliverables

| file | bytes | lines | sha256 |
|---|---|---|---|
| `deploy-gates-wave13.ps1` | 60,023 | 933 | `1CDFF30AF6F17B69ACE0CDF36B853D6D74BD77EB241D183A762D18158222237D` |
| `DEPLOY-PACKET-REBASE.md` (this file) | — | — | — |

- **PowerShell 5.1 parse:** `PSVersion=5.1.26100.9711`, `tokens=5259`,
  `PARSE_ERRORS=0` (E8, re-run against this final file after the last edit).
- **Structure check:** 26 gates + `default`, one `param(`, one `$root`, one `$scratch`,
  six functions, no duplicated block (a duplicated 8-line comment block from an edit
  race was found and removed; a scan for duplicate markers now reports 1 each).
- **No-argument run:** prints the 26 gate entries and the header (27 lines), creates
  nothing, exit 0 (E9).
- **Gates added:** `postdeploy` (10b-2). Gates changed in behaviour: `0B`, `0C` (message
  only), `0E`, `0H`/`apply`/`reseal` (numbers and GO text), `probes`, `preflight`,
  `verify-wave8` (file names and expectations), `insurance`, `install-desktop`.
- **Wave-12 original:** untouched —
  `CD8964ADA8E483DD92F326C48577DB9F1851603B7ECED0FFFABAB8E83BB2BB1A`, 46,839 B,
  759 lines, re-hashed after the copy.

---

## 8. Lead edits after delivery (2026-11-09 12:34-12:40 PT)

The Lead reviewed `deploy-gates-wave13.ps1` against this document and made two changes in
the same file (nothing else was touched):

1. **The `probes` gate runs BOTH acceptance scripts.** The delivered version replaced the
   wave-11 24-row script with `verify_wave13_live.py`; that loses the regression baseline
   wave 12 measured at 24/24. The gate now runs the wave-11 script first
   (`--ref $Ref --repo $root`, output `10-probes-wave11.txt`) and then the wave-13 verifier
   (`--json-out`, output `10-probes-wave13.json` / `.txt`), and its GO text names both halves.
2. **The `postdeploy` gate RUNS the static checks** instead of only printing a command:
   `powershell.exe -File post-deploy-checks-wave13.ps1 -Transcript <run>\10b2-post-checks.txt`
   (plus `-PhoneVersion` once Gate 0E has recorded it), capturing stdout to
   `10b2-post-checks-stdout.txt` and printing the SUMMARY / VERDICT lines and the exit code.
   The script is still only referenced, never created.

**Re-validated after the edits:** PowerShell 5.1 parse clean (`PSVersion=5.1.26100.9711`,
tokens 5259, `PARSE_ERRORS=0`); the no-argument run still prints the gate list and creates
nothing. The packet author then removed an 8-line duplicated closing-header block in the
same file (a comment block that already exists earlier in the header) and the Lead fixed
the header's `probes` / `postdeploy` one-line descriptions to match the new behaviour.
FINAL file: **933 lines / 60,074 B**, sha256
**`F95B884D3057C9C1ECB2F1FDBC5E189AB8D1C742B4CBBE31FF939A1B081ADF6C`** (the §7 hash is the
as-delivered one; 62A95F8F… was the intermediate one, both superseded by this line).
- **Not created (referenced only):** `post-deploy-checks-wave13.ps1`,
  `verify_wave13_live.py`, `REHEARSAL.md`, `CHECKLIST.md`.
- **Landed in parallel while this packet was written (not mine):** `ROLLBACK.md` (12:31:57),
  `PRE-DEPLOY-BASELINE.txt`, `pre-deploy-baseline.json`, the CI watcher log, and the
  Lead's `postdeploy` runner edit at 12:35 PT. See §1.1 and §5 items 9 and 12.

## 9. POST-AUDIT RE-PIN (13:00 PT) — the deploy target moved two commits

**Why.** The independent Wave-13 feature audit (read-only, finished 12:36 PT) found one
MEDIUM in the frozen tree: the owner's exact sentence "can you create a repository?" did not
reach the deterministic GitHub answer. The Lead fixed it and carried the audit's record
corrections as two commits on top of `43b925f62`:

- `6f00bd58d324f11a07059c4139d0d84499e23d8a` — fix(wave13): the owner's own "can you create
  a repository?" reaches the carded answer (`backend/jarvis_quick.py` + its
  `jarvis-backend/` twin, `backend/test_web_access_truth.py`).
- `7d892e277a42efe9a7b6d86a5b9623d65eff45fd` — docs(wave13): the audit's record corrections
  (JARVIS-API Creator numbering 211.x, ARCHITECTURE §8 reference, README 182/36 counts and
  the split Reminders bullet, the F2 design page's row status, `gen_self_code_map.py`'s
  "four small actions", DEF-049 reopened in the tsv + md, and both self-code maps
  regenerated LAST in one run).

**New pin.** Frozen head **`7d892e277a42efe9a7b6d86a5b9623d65eff45fd`**, frozen tree
**`ae49d2b8e0d38801046f9f4db2a606738409c857`** (`git rev-parse 7d892e277^{tree}`); PR
#1218's head was confirmed as that sha after the push. The deploy tree
(`C:\Users\pcadmin\Documents\jarvis-install-tree`) now sits detached at it; Gate 0B checks it
out to the merge ref as before.

**What did NOT move (re-measured, not assumed).** Gate 0H re-ran from the deploy tree at the
new head (13:02 PT, `0H-preview-wave13-postaudit.txt`): SHIPPED **334** = add 1 + update 20 +
unchanged 313; HUD DELTAS **234** = 233 + 1 insert (still only
`skill-scan-wiring.patch -> jarvis_skills.py`); READY PLUG-INS **31** present / 1 to add
(creator-mode) / 26 already wired; PYCACHE **230**; PLANNED CHANGES **252**; `dryRunExit=0`;
VERSION unchanged 0.2.442; `VERSIONsame=True backupFolders=26->26`. The static post-deploy
script was re-pinned in only two values: `jarvis_quick.py` expected **1,464,997 B** (its
committed blob grew by 956 B) and its `-FrozenSha` default; its dry run kept the same
2 PASS / 14 FAIL / 1 BLOCKED / 1 WARN "before" shape. The live verifier was re-pinned
(`EXPECTED_SHA`, and GH-4 now probes the owner's own phrase as well as "are you able to …");
its read-only baseline kept 2 PASS / 6 FAIL / 3 BLOCKED / 2 PARTIAL. Both scripts parse
clean under Windows PowerShell 5.1.

**Every `43b925f6` reference earlier in this document** is the tree the values were first
derived from and stays valid as the derivation record; the run's target is the new tree
above. Only two deployed-byte files changed: `backend/jarvis_quick.py` (SHIPPED update;
`jarvis-backend/jarvis_quick.py` kept byte-equal) and the `jarvis-self-code.json` twins (both
SHIPPED updates) — the 0H totals above prove neither became an add. Every other changed file
is docs/records the deploy does not install.

## 10. SECOND RE-PIN (14:10 PT) - the CI-fix commit b3b300034

The first COMPLETED required run on 7d892e277 (run 42697153344) came back red on
`backend-windows`: three stale tool pins in suites wave 13 never touched, one measured
cause - `set_reminder`'s new `text` parameter description (268 -> 309 tokens; it is a
CORE tool, so the short list grew by exactly the same 41). The fix commit is
`b3b3000349e1b779b08981b6b517e4d421aa28ec`, 6 files, +54/-25: the three pins, the
tool_eval saved fallback copy and the self-code map twins. No shipped behaviour changed.

WHAT MOVED: $FrozenHead = b3b300034, $FrozenTree = 6ecffcadb7d8cea63307e272a320d9ac86e7cc93,
$Ref = b3b300034, the post-deploy script's default -FrozenSha, the verifier's
EXPECTED_SHA, the spec pins and Appendix A heading, the deploy tree (detached at the new
head, clean), and the deploy run folder (run-20261109-1405; the earlier
run-20261109-125132 is kept as the first re-pin's evidence).

WHAT DID NOT MOVE (re-measured, not assumed):
  * Gate 0H at b3b300034: SHIPPED 334 = add 1 + update 20 + unchanged 313; HUD DELTAS
    234 = 233 + 1 insert; READY PLUG-INS 31 / 1 to add / 26 wired; PYCACHE 230;
    PLANNED 252; dryRunExit 0; VERSIONsame True; backups 26->26.
  * the static checks: 2 PASS / 14 FAIL / 1 BLOCKED / 1 WARN, exit 1 (before-shape).
  * the live verifier baseline: 2 PASS / 6 FAIL / 3 BLOCKED / 2 PARTIAL, exit 1.
  * the apply write count: still `wrote 23` (add 1 + update 20 + insert 1 + VERSION 1).
  * jarvis_quick.py's expected live size: still 1,464,997 B; every other Appendix A size
    is re-read from the tree at run time (`git cat-file -s <sha>:<path>`).
  * the owner TOML: untouched, 58,409 B / 9C6CDF76...C92D97, not asserted by the deploy.

WHY THIS WAS NOT CAUGHT BEFORE THE FREEZE: the branch had no COMPLETED CI run on its
final heads - every earlier run was cancelled by the next push, by design. The first run
that reached the long jobs is the one that found these. The lesson is recorded with the
fix (the three suites are cheap to run at the desk; they now have been).

## 11. THIRD RE-PIN (15:35 PT) - the second CI-fix commit 32ba251d9

The first COMPLETED required run on `b3b300034` was 6/7: `backend-windows` went green (the first CI
fix worked) but the required Ubuntu `backend` job failed at 15:26:50 PT - its own summary 73059
passed / 198 skipped / 4 failed, and all four were stale catalogue/patch pins in the same class:
test_capability_answers (181 -> 182 rows), test_tool_profiles (the model-facing feature-guide
sentence still said 181 rows; jarvis_tool_profiles.py + its twin are the fix), test_notes_edit
(generated-registry pin 28/57 -> 29/58) and test_phone_app_allowlist (stack order gains
skill-scan-wiring.patch before activity-turn-guard). The local full-sweep triage and the paired
session's independent clean-clone reproduction agreed on all four numbers.

WHAT MOVED: $FrozenHead = 32ba251d9, $FrozenTree = 46216eac7f1b0aedcbc8bf5dc7841aa6e76574a0,
$Ref = 32ba251d9, the post-deploy script's default -FrozenSha, the verifier's EXPECTED_SHA, the spec
pins and Appendix A heading, the deploy tree (detached at 32ba251d9, clean), the deploy run folder
(run-20261109-1540) and the plan STATUS.

WHAT DID NOT MOVE (re-measured at 32ba251d9, not assumed):
  * Gate 0H: SHIPPED 334 = add 1 + update 20 + unchanged 313; HUD DELTAS 234 = 233 + 1 insert;
    READY PLUG-INS 31 / 1 to add / 26 wired; dryRunExit 0; VERSIONsame True; backups 26->26.
  * PYCACHE 236 and PLANNED 258: PYCACHE is a LIVE measurement (it was 230 at the last re-pin;
    the local python bytecode cache changed because suites were run between the re-pins). It
    changes the PLANNED total only - the apply write count stays 23 (add 1 + update 20 + insert 1
    + VERSION 1), because pycache entries are cleaned, not written.
  * every Appendix A expected size (the only shipped module whose text changed is
    jarvis_tool_profiles.py, and no size of it is pinned); every marker row count.
  * the apply write count: `wrote 23`; the owner TOML: untouched, 58,409 B / 9C6CDF76...C92D97.

WHY THIS RE-PIN IS SAFE TO WEIGHT LIGHTLY: both fix commits are test pins plus one owner-facing
sentence; the shipped feature code is identical to 7d892e277, whose independent feature audit passed
with no merge blocker.
