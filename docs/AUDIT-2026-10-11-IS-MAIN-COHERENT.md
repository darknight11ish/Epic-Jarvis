# Is main actually what we think it is? (audit, 2026-10-11)

**Answer, in one line: main's *content* is coherent on every check I could run;
main's *coverage* is not - seven checkers exist that no workflow ever runs, and
three of those cannot run anywhere but the owner's PC.**

Audited tip: `origin/main` = **`64381c0d`** ("Merge pull request #300 from
darknight11ish/fix/preflight-runs-on-his-pc"). Worktree:
`.dsh-scratch/main-audit`, branch `audit/is-main-coherent`, created with
`git worktree add .dsh-scratch/main-audit -b audit/is-main-coherent origin/main`.

Method note, because it matters more than usual here: **every claim below was
read from `origin/main` with `git show origin/main:<path>` or
`git ls-tree -r origin/main`, never from the working tree and never with
`git grep`.** The working tree in this worktree is a clean checkout of that
same tip, but the discipline is the point: today's lesson was a clean merge
that nobody could catch by reading a diff. A second agent's report supplies the
sharpest example: in the main clone, whose working tree sat on another branch
with 22 changed files, **`git grep` would have found no
`tools/check_plugins.py` at all** - the file that asserts the rule - and would
have reported the rule as unasserted.

---

## Findings, in order of consequence

### 1. Seven checkers exist that no workflow runs - and the twins checker is one of them

`git ls-tree -r --name-only origin/main | Where-Object { $_ -match
"^(tools|jarvis-desktop/scripts|backend)/.*(check|verify|audit)[^/]*\.(py|ps1|mjs)$" }`
lists 24 `tools/check_*.py` plus `jarvis-desktop/scripts/check-tokens.py`,
`jarvis-desktop/scripts/verify-windows.ps1` and `tools/offdevice/SelfCheck.ps1`.
Extracting every checker *named* in every workflow
(`git show origin/main:.github/workflows/<wf>.yml` for each of them) and taking
the set difference gives:

| checker | named by any workflow? | runs today on main |
|---|---|---|
| `tools/check_stale_twins.py` | **no** | yes: `exit=0` |
| `tools/check_screen_safety.py` | **no** | yes: `exit=0` |
| `tools/check_registry_phone.py` | **no** | yes: `exit=0`, `4 passed, 0 failed` |
| `tools/check_feature_list.py` | **no** | yes: `exit=0`, `5 passed, 0 failed` |
| `tools/check_lanes.py` | **no** | yes: `exit=0` |
| `tools/check_obscura.py` | **no** | no: needs Obscura installed on the owner's PC |
| `tools/check_work_claims.py` | **no** | no: its evidence is untracked (below) |
| `tools/check_apk_16kb.py` | yes (`../tools/check_apk_16kb.py`) | no: needs a built APK |
| `jarvis-desktop/scripts/verify-windows.ps1` | **no** | a manual Windows verification script |
| `tools/offdevice/SelfCheck.ps1` | **no** | runs on a device, by hand |

**No workflow enumerates the checkers with a glob**, which is the one thing
that would have made this table wrong: a scan of every `.github/workflows/*.yml`
and every `scripts/`, `tools/` and `jarvis-desktop/scripts/` file for a
`check_*` enumeration found only `tools/check_apk_16kb.py` itself (its own
message names `check_*`). So the named list in the workflow is the whole story,
and the checkers in the first five rows are **green today and unguarded
tomorrow**.

Why this is the top finding rather than a nitpick: **four of them pass today and
would cost nothing to add to the `audit` job, and one of them is the twins
checker the repository's own discipline depends on.**

### 2. The twins check passes: `backend/` and `jarvis-backend/` agree

`py -3 tools/check_stale_twins.py` (never run by CI):

```
jarvis-backend/ is this repository's copy: all 191 modules this repository
ships whole match, line endings ignored (190 SHIPPED entries plus
backend/rebuilt/).
This is the shipped-twin half of backend/test_base_matches_repo.py only; that
suite also checks the base's imports, the files beside its code and that
nothing private was swept in.
exit=0
```

So the twin files are byte-identical modulo line endings - but note the
checker's own second line: **it is half of a suite.** The other half
(`backend/test_base_matches_repo.py`) is a backend suite and is not part of the
twin checker. A "twins are fine" reading that stops at the exit code is exactly
the vacuous-check shape this repository already worries about.

### 3. A silent-mis-merge scan over seven days: 328 merges, 89 flagged lines, two worth a human read

This is the day's specific failure - a three-way merge that keeps one side's
context and drops the other's trailing line with **no conflict marker**. I
built a mechanical detector for that shape:

```
for every merge commit since 2026-10-04 (git log --merges):
  base = git merge-base P1 P2
  for each file BOTH sides changed (text files only):
    for each side: lines that side ADDED vs base (git diff -U0 base P)
    flag any added line (>= 12 chars, containing a word-like token >= 8 chars)
    that appears NOWHERE in the merge result (git show M:file)
```

Commands and result:

```
merge commits since 2026-10-04: 328
merge x both-sides file pairs compared: 510
pairs with a line added on one side and absent from the merge result: 89
```

**89 is not 89 defects, and it must not be read as one.** The detector cannot
tell a *dropped* line from a legitimately *rewritten* one, so it flags both. The
sample output shows the flag firing on lines that were reworded by the other
side (`"pictures.patch"}` becoming a longer list, a comment re-flowed) - those
are the majority. **The value of the scan is the shortlist, not the count.**

Two items in the shortlist deserve a human read, and neither is claimed as a
defect:

```
2026-10-11 b23673dff  P1  backend/plugin-loader.patch  (that side added 3 lines)
   merge: Merge remote-tracking branch 'origin/main' into feat/work-se...
   absent from result: httpd = ThreadingHTTPServer((bind, HUD_PORT), Handler)
```

This is the exact line DEF-007 is about (the loader's anchor), so it may be the
known, deliberate re-anchoring that closed DEF-007 - or it may be a second one.
It needs the merge read beside DEF-007's resolution, not guessed at.

```
2026-10-11 81f69b89e  P1  docs/defect-register.tsv and docs/DEFECT-REGISTER.md
   merge: Merge remote-tracking branch 'origin/main' into docs/readme-map-count
   absent from result: DEF-007  fix-266 ... backend/plugin-loader.patch;plugins/registry.json;tools/check_plugins.py
```

This is my own #287 branch's merge, and the "missing" line is DEF-007's **older
wording** - the row was deliberately rewritten when DEF-007 closed. Flagged
correctly by shape, harmless in fact.

**Limits of this scan, stated rather than implied:** (a) it compares whole-line
text, so any line the other side reworded is flagged; (b) it covers only files
**both** sides touched - a merge that drops a line from a file only one side
touched is invisible to it; (c) **some files could not be read at all** -
roughly twenty `git show` calls died with `UnicodeDecodeError: 'charmap' codec`
on non-UTF-8 bytes (the patch files), so coverage is partial and those files
were skipped rather than reported; (d) `git grep` was not used, per the brief.

### 4. Three checkers are red today, and none of the three is main's fault

| checker | exit | its own last line | why |
|---|---|---|---|
| `tools/check_claims.py` | **1** | `says: backend/test_api_doc.py exited 1: FAIL jarvis_quick.py in C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program is not the copy in t...` | compares against **this machine's** backend copy, which lives outside the repo; the claim is about a deployment, not about main |
| `tools/check_apk_16kb.py` | **1** | `error: no APK found. Build one first ...` | needs a built APK; cannot run from a source checkout |
| `tools/check_obscura.py` | **1** | `Stopped: Obscura (the windowless browser) is not installed on this PC yet.` | needs a program on the owner's PC |
| `tools/check_work_claims.py` | **2** | `missing: .dsh-scratch/android-verify/MODEL-BENCH-2026-10-10.md` / `They live in .dsh-scratch/, which is not in git.` | **its evidence is untracked, so it cannot pass on any clone, including CI** |

`check_work_claims.py` is the interesting one: it is written to *refuse to make
a claim without the numbers*, and the numbers live in a directory that is not in
git. That is a deliberate design ("nothing is claimed about the numbers without
them"), but it also means the checker can never run in CI, so it is unguarded
in both directions - it cannot pass there, and it cannot fail there.

### 5. Patch order and encoding: coherent

```
apply-patches.ps1: bytes >127: 0   length: 318145
offset of plugin-loader.patch: 89134
cd backend; py -3 test_patch_history.py
  ok    every one of this repository's 17 *.ps1 files is ASCII, not only apply-patches.ps1
  25 passed, 0 failed        exit=0
```

So `apply-patches.ps1` is pure ASCII (0 bytes above 127 in 318,145), and the
patch-history suite passes on its own terms - **including widening the ASCII
rule to all 17 `.ps1` files**, not just the one the brief named.

**What I did not verify here, honestly:** that `plugin-loader.patch` is **LAST**
in the apply order. I read its byte offset (89,134 of 318,145, so about 28% in)
and I found the files that mention it, but the order is defined by an allow-list
inside the patch machinery and I did not isolate the list and compare it. **SETTLED, and not by this audit:** the apply order is **written, not computed**.
`scripts/apply-patches.ps1`'s `$PATCHES` is a literal ordered array of **144
entries, 0 duplicates, `plugin-loader.patch` at index 143 of 143, exactly
once**, and the patcher's loop (`:4058`, `:4169`) filters it and never reorders;
`backend/_stack.py:285 order()` - the list the suites read - ends
`big-coder.patch`, `pictures.patch`, `plugin-loader.patch`; and
`plugins/registry.json` (`patch_count: 142`), `plugins/loader/README.md:68` and
the patcher's own comments (`:1337-1340`, `:1436`, `:1459`) agree. `backend/patch-history/index.tsv` is **not an order list** - it is per-patch
version history, newest first per patch, so it carries no position and can
neither agree nor disagree. A name to be careful with: the *suite* is
`backend/test_patch_history.py` (the 25/0 above); the tool that writes that
history is `tools/build_patch_history.py`; **there is no
`tools/check_patch_history.py`.** **The rule is
asserted, not only written down:** `tools/check_plugins.py:243-244`
(`listed[-1] == "plugin-loader.patch"`), `backend/test_gate_touches.py:608-609`,
`test_big_coder.py:610-612`, `test_work.py:697-698`, and four more singles (`test_picture_card.py:426`, `test_devices.py:689`, `test_gate_risk_rows.py:126`, `test_referee.py:725`); and
the five allow-lists (`test_devices`, `test_gate_risk_rows`, `test_gate_touches`,
`test_referee`, `test_screen_attach`) each report "patches after the guard NOT
named: NONE". A second agent checked it read-only at `origin/main` `c66d494d`,
18 of 18 files read with `git show origin/main:<path>` and hash-verified. **The four extra singles, the `index.tsv` point and the name
correction above are that agent's findings, not re-run by me**; my own
run of the suites agrees - `test_gate_touches.py` 80/0 ("still last of all"),
`test_big_coder.py` 94/0, `test_devices.py` 329/0, **all 0 skipped**, so this is
a rule CI can enforce rather than one that holds only on the owner's PC.

### 6. Generated files against their sources: coherent where a checker exists

```
py -3 jarvis-desktop/scripts/check-tokens.py   -> TOTAL 0 (0 unreachable, 1 defining block)
py -3 tools/check_parity.py                    -> No undecided drift.
py -3 tools/check_command_acl.py               -> 366 commands, generate_handler! and build.rs agree.
py -3 tools/check_plugins.py                   -> 20 passed, 0 failed
py -3 tools/check_registry_phone.py            -> 4 passed, 0 failed   (never run by CI)
py -3 tools/check_feature_list.py              -> 5 passed, 0 failed   (never run by CI)
py -3 tools/check_docs_map.py                  -> docs map OK: 348 documents, 8,309,055 bytes
```

`check_parity.py` is the one that answers "the generated files and their sources
disagree" for the paired catalogues, and it reports no undecided drift.
`check_plugins.py` covers `plugins/registry.json`, and `check_registry_phone.py`
covers the phone's own registry view - **the second of those is in the never-run
list**, so the phone half of that pairing is checked only by hand.

### 7. What I could not run, and why

- **The Playwright page suites** (`jarvis-desktop/tests/*.mjs`, including
  `security.mjs`): `node tests/security.mjs` exits 2 with *"These UI tests need
  Playwright, which is not installed by default"*. CI installs it for its
  desktop job; this environment cannot.
- **`cargo test`**: excluded by the brief (it OOMs here).
- **The backend suites that need a file from the owner's PC**: excluded by
  design; `backend/run_suites.py` skips them by name.
- **`tools/check_obscura.py`, `tools/check_work_claims.py`,
  `tools/check_apk_16kb.py`**: cannot pass in a source checkout, as above.
- ~~The patch apply-order question~~ **settled independently - see finding 5**.

---

## What I checked and found coherent, with the evidence

- **`origin/main` at `64381c0d`**; this worktree is a clean checkout of it, and
  every file claim above was read with `git show origin/main:<path>`.
- **The shipped twins**: 191 modules match, line endings ignored
  (`tools/check_stale_twins.py`, exit 0).
- **Patch machinery**: `scripts/apply-patches.ps1` is pure ASCII (0 of 318,145
  bytes above 127); `backend/test_patch_history.py` passes 25/0 and holds all
  17 `.ps1` files to ASCII.
- **Generated artefacts vs sources**: tokens 0 unreachable; parity "No undecided
  drift"; command ACL "366 commands ... agree"; plugin registry 20/0; phone
  registry 4/0.
- **The defect register**: `py -3 tools/check_defect_register.py` ->
  `defect register OK: 4 open, 3 closed`.
- **The docs map**: `docs map OK: 348 documents, 8,309,055 bytes, and README.md
  agrees`.
- **The merge-history scan**: 328 merges and 510 both-sides file pairs since
  2026-10-04, with 89 whole-line flags of which the sampled majority are
  legitimate rewrites; **no silent mis-merge was proved**, and the two items
  that need reading are named in finding 3.

## The one-line answer, restated

**Main is coherent where it is checked, and less checked than it looks:** four
checkers that pass today are run by nothing, the twins checker among them, and
three more cannot run outside the owner's PC. The patch apply-order question -
the one item this audit could not answer - has since been settled independently
(finding 5), and the "no `git grep`" rule earned its keep in the process.

*(Written 2026-10-11 against `origin/main` `64381c0d`. This audit fixes nothing:
findings only, per the brief.)*
