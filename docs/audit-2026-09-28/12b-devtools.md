# Audit #12b - Developer tools, scripts and CI (2026-09-28)

Everything below was run or read on a **copy** of the combined tree
(`git -C integ archive HEAD` into `scratchpad/p12/tree`), except
`build_patch_history.py --check` and `gen_gemini_bundles.py` (they need git
history; both only read the tree, and `git status` in `integ` stayed clean).
origin/main was read with `git show`. Nothing in the repository was edited.

## Will CI pass on the combined tree?

**No - but only for reasons already known.** Job by job (`.github/workflows/ci.yml`):

| CI job / step | Run here | Result on combined |
|---|---|---|
| rust: `cargo fmt --check` | yes | pass |
| rust: `cargo clippy --all-targets -D warnings` | yes, `--target x86_64-pc-windows-msvc` | pass (only the expected "GNU compiler" warning) |
| rust: `cargo test` | no (needs Windows) | not known |
| frontend: `node --check`, markdown-test, check-tokens | from the earlier helper's logs | pass |
| frontend: every `tests/*.mjs` | earlier helper's `ui3.txt` | **fails: faces.mjs** (already known: the https:// credit in faces.html) |
| backend: `run_suites.py` | yes | **172 passed, 4 failed, 19 skipped**: test_brain_reads, test_forget_range, test_history_import, test_photo_remind (already known: the "is last in the list" checks). test_patch_history is skipped in my copy (no git); `build_patch_history.py --check` in `integ` says "up to date", so it should pass in CI. |
| backend: check_parity.py | yes | pass ("No undecided drift"; desktop 173 routes, phone 149) |
| backend: gen_critters --check, shader_size --check | yes | gen_critters pass; shader_size needs `glslangValidator` (CI installs it; not tested here) |
| backend: gen_lipsync, gen_sky, gen_sky_cases --check, sky.mjs | yes | pass |
| backend: check_command_acl.py | yes | pass (249 commands) |
| powershell-5: parse every .ps1 | pwsh 7 parser, 5.1 operators searched | pass: no `??`, `?.`, ternary, `&&`, `||`, `-Parallel`, non-ASCII code, or parse error in any of the 5 `.ps1` files |
| powershell-5: run apply-patches with an empty list | yes, pwsh 7 | pass (exit 0; second run left the settings file alone; `-Revert` exit 0) - see T2 |
| audit: gen_notices --check | yes | pass |
| python-advisories | yes | pass (78 pinned releases, 0 advisories) |
| credential-manager | no (Windows) | not known |

So the combined tree needs exactly the two known fixes (the four
"last in the list" tests and faces.mjs) to go green on everything this
container can run.

## Findings

| # | Severity | Where | One line |
|---|---|---|---|
| T1 | medium | main + combined | `desktop-release.yml` and `jarvis-client.yml` publish only from `main` or `claude/admiring-ritchie-5urg5h` - the old working branch (PR #17, merged). Today's work branches never publish. Owner's call (Q1). |
| T2 | low | main + combined | CI's PowerShell 5.1 run copies only `scripts/` and `backend/`, so apply-patches prints "FAIL 1 file(s) 'Check for tool updates' reads are missing ... Cargo.lock" on every run - and still exits 0. A FAIL line in a green log. |
| T3 | low | main + combined | `tools/gen_palette.py` is stale: re-running it throws away a hand-made fix in `Palette.kt` (the cached `ramps` map that stops per-frame allocation). |
| T4 | low | combined | `tools/gen_gemini_bundles.py` is stale: its default `--since 093caee` now covers 1,086 commits, and every one of its six files is 455k-1,231k tokens - all over the 400k the tool itself says it keeps each file under. |
| T5 | low | main + combined | `tools/tool_eval` says "62 requests"; the code runs 65 (also report 11, D11). |
| T6 | info | main + combined | Not in CI, by design or need: `gen_sky_places.py` (needs `pip install geonamescache`, documented), `server/test_jarvis_mobile_ws.py` (legacy module), the trainers/bank builders (need big external downloads), and real `tool_eval` runs (need Ollama). `tool_eval` IS covered offline by `backend/test_tool_eval.py` in run_suites. |
| T7 | info | main + combined | `docs/SOURCE-BUNDLE.md` (from `gen_source_bundle.py`) is from 2026-09-14, 478 phone commits old - already marked stale in docs/README.md. |

### T1 - the publish branch (medium, owner's call)

`.github/workflows/desktop-release.yml` line 44: `branches: [main, "claude/admiring-ritchie-5urg5h"]`,
line 100: `IS_WORK_BRANCH: ${{ github.ref == 'refs/heads/claude/admiring-ritchie-5urg5h' }}`.
`.github/workflows/jarvis-client.yml` line 975:
`if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/claude/admiring-ritchie-5urg5h'`.
That branch still exists on GitHub but is no longer where work happens (work is
on the five `claude/jarvis-*` branches). README.md and jarvis-client/README.md
say builds publish "from main or the working branch". Result: until the
branches reach `main`, no phone APK or desktop installer from this week's work
is published. Proposed: main only (simplest, recommended) - delete the second
branch name in all three places and change the READMEs' "or the working branch".

### T2 - a FAIL line in every green CI run (low, code change)

Ran here exactly as CI does (patch list emptied, `scripts` and `backend` copied):
```
  ok    requirements.lock - copied in (Check for tool updates was off until now)
  FAIL  1 file(s) 'Check for tool updates' reads are missing from this repository:
          .../repo/jarvis-desktop/src-tauri/Cargo.lock
```
exit code 0. The script reads `jarvis-desktop\src-tauri\Cargo.lock`
(`apply-patches.ps1` line 1830); CI's copy step (`ci.yml`, "Run
apply-patches.ps1 in 5.1 against a stand-in backend") has
`Copy-Item -Recurse scripts, backend -Destination $repo` only. On the owner's
PC the file is there, so this is CI-only. Fix in ci.yml, after that Copy-Item:
```
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'jarvis-desktop\src-tauri') | Out-Null; Copy-Item jarvis-desktop\src-tauri\Cargo.lock (Join-Path $repo 'jarvis-desktop\src-tauri')
```
and assert the log has no `FAIL` line, so a real one would turn CI red.

### T3 - gen_palette.py would undo a fix (low, code change)

Running `python3 tools/gen_palette.py` on the copy changed
`jarvis-client/.../face/Palette.kt`: the committed file has
```
fun steps(family: String): List<Color> = ramps[family] ?: emptyList()
...
private val ramps: Map<String, List<Color>> =
    families.associateWith { f -> (1..5).mapNotNull { byId["$f-$it"] } }
```
(with a comment: "steps() used to rebuild its list on every call ... per frame");
the generator writes back the old `(1..5).mapNotNull { byId["$family-$it"] }`.
Same file on main. Fix: put the `ramps` version into gen_palette.py's template
(and ideally give it a `--check`, run in CI like the other generators).
`gen_golden.py` and `scripts/build-resolve-vectors.mjs` were also re-run: both
produce byte-identical output (no drift).

### T4 - gen_gemini_bundles.py (low)

`tools/gen_gemini_bundles.py` line 37 `LAST_AUDIT = "093caee"`; run with
`--out` into the scratchpad:
```
Since 093caeec (1086 commits), at deaca649 on audit-integration:
  jarvis-audit-1a-backend-safety.md    - 179 files, 4810 KB (about 1231k tokens)
  jarvis-audit-1b-backend-abilities.md -  32 files, 1836 KB (about 470k tokens)
  jarvis-audit-2-desktop-rust.md       -  77 files, 1777 KB (about 455k tokens)
  jarvis-audit-3-desktop-web.md        - 105 files, 2793 KB (about 715k tokens)
  jarvis-audit-4a-phone-core.md        - 127 files, 2023 KB (about 517k tokens)
  jarvis-audit-4b-phone-screens.md     - 100 files, 2154 KB (about 551k tokens)
```
Its docstring: "one past about 400k tokens reads shallowly. So each session is
one part of Jarvis, kept under that". It works, but the default is unusable
now. Fix: move `LAST_AUDIT` to the commit of the last real Gemini audit, or
make the tool split further / warn when a file passes 400k.

## Tool by tool

| Tool | Status | How checked |
|---|---|---|
| tools/check_parity.py | works | run: clean, in CI |
| tools/check_command_acl.py | works | run: 249 commands agree, in CI |
| tools/check_python_advisories.py | works | run (needs PyPI access), in CI |
| tools/build_patch_history.py | works | `--check` in integ: "up to date"; CI via test_patch_history |
| tools/gen_*_cases.py (29 of them) | all work | every `--check` exit 0; each is exercised by its backend test (in CI) and most by a desktop/phone test |
| tools/gen_critters.py, gen_lipsync.py, gen_sky.py, gen_sky_cases.py, gen_notices.py | work | `--check` exit 0; in CI |
| tools/shader_size.py | works in CI only | needs glslangValidator (CI installs it) |
| tools/gen_sky_places.py | works with `geonamescache` installed | `--check` fails here with ModuleNotFoundError; documented in its docstring; not in CI |
| tools/gen_golden.py | works | re-run, identical output |
| tools/gen_palette.py | **stale** | T3 |
| tools/gen_gemini_bundles.py | **stale default** | T4 |
| tools/gen_source_bundle.py | stale output | T7; not re-run |
| tools/gen_launcher_icon.py, gen_voicebank.py, gen_wakebank.py, build_locomo_fixture.py, train_stopword.py, train_wakeword.py | not runnable here | need source art, speech datasets, voice models, espeak-ng or several GB; `train_wakeword --check` stops at "espeak-ng not on PATH" |
| tools/tool_eval | works offline | `--help` fine; `backend/test_tool_eval.py` (in CI) covers it without Ollama; count wrong (T5) |
| tools/model_tryout | works offline | `backend/test_model_tryout.py` passes |
| scripts/apply-patches.ps1 | works (what can be run here) | parses; no 5.1-only syntax; every native call (`git`, python, pip, run_suites) runs with `$ErrorActionPreference = 'Continue'` (lines 1073, 1342, 1914, 1951, 2006), so the stderr trap in CLAUDE.md is handled; `$PATCHES` (97) = the 97 .patch files and it refuses an unlisted one (line 1045); `$SHIPPED` (116) + the 10 rebuilt = `_where.SHIPPED` (126) = every module on disk. The real patch rehearsal needs the owner's jarvis_hud.py etc.; on the earlier helper's stand-in it stops at memory-safety with "NOTHING HAS BEEN CHANGED", as designed. |
| scripts/check-backend.ps1 | works | run on the stand-in: lists the 4 owner-only modules (jarvis_gate, _extract, _models, _skills) as missing, exit 1, as designed |
| scripts/fetch-repo-stats.ps1, get-export.ps1, jarvis-desktop/scripts/verify-windows.ps1 | parse clean | not run (need GitHub API / a Claude export / Windows) |
| scripts/build-resolve-vectors.mjs | works | re-run: 130 vectors, fixture unchanged; not in CI |
| scripts/recover_from_claude_export.py | not run | needs an export |

## Workflows

- **ci.yml** picks up new work automatically: backend suites by
  `glob("test_*.py")`, desktop suites by `tests/*.mjs`. All 195 backend tests
  and 104 desktop suites are therefore in CI. Paths all exist.
- **jarvis-client.yml**'s path filter includes `backend/**`,
  `jarvis-desktop/src/**`, `src-tauri/src/**`, `tests/fixtures/**` and
  `VERSION`. I checked what the phone's tests read from outside
  `jarvis-client/`: backend files, desktop src/tests and Rust - all covered.
  No phone test reads `tools/` or `docs/`.
- **android-apk.yml** (legacy app) and **verify-toolchain.yml** (manual) point
  at real paths; unchanged by the new work.
- ci.yml's `paths-ignore` (CLAUDE.md, README.md) is still right: no test reads
  the top-level README.md or CLAUDE.md (the tests that read "README.md" read
  `backend/README.md` or `server/README.md`).

## Questions for the owner

- **Q1 (T1).** Which branch should build and publish the phone APK and the
  desktop installer? **Only `main`** (recommended - you press Merge, then it
  publishes), or also a named working branch (which then has to be kept up
  to date in three places)?
