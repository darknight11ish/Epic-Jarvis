# Report 40 (audit), agent a97e232f, 2026-09-30T07:07Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first; beginner owner, plain words; verify every claim with file:line + quote; say 'not checked' honestly; change no files). AREA: the UPDATE PATH: scripts/apply-patches.ps1 (2256 lines), backend/rebuilt-patches/, backend/patch-history/, tools/build_patch_history.py, backend/_stack.py, docs/UPDATE-AND-CHECK-2026-09-28.md, docs/INSTALL.md. Context: it just failed on the owner's real Windows PC: their backend files were CRLF, patches are LF, the -FixLineEndings switch was added (PR #37), and my own screen.patch hunk skipped a middle line 

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

UPDATE-PATH AUDIT (read-only; one experiment run under the scratchpad). Findings, worst first.

1. "NOTHING HAS BEEN CHANGED" is FALSE after -FixLineEndings. RAN IT. On a fake backend with CRLF files I ran -FixLineEndings and got 3 missing files. The script printed "NOTHING HAS BEEN CHANGED." and exited 1. jarvis_hud.py had changed anyway (md5 db7f... became 980c...), and a `_jarvis-backup-...-endings` folder had appeared. Cause: the CRLF-to-LF rewrite of the real files (apply-patches.ps1:1490-1503) runs before the missing-file check (1619) and before the rehearsal (1848, which repeats the claim).
   - The rewrite is meant to be safe, and a backup is made. But the message lies, and a failed run leaves the owner's files rewritten.
   - Smallest fix: move the FixLineEndings block to after the rehearsal succeeds. Rehearse on a copy that has been converted with Copy-AsLf. Only then convert the real files. If that is too big a change, reword the failure lines to say "line endings were changed; originals are in <endings backup>".
   - Related: the loop (1497-1503) runs under `$ErrorActionPreference='Stop'`. If one file is locked, `Move-Item` throws. That leaves earlier files converted, later ones not, and an orphan `.lf-tmp`. Not tested.

2. The tests can pass "proven" while proving nothing. Read, not run.
   - 2216-2223: a suite passes if its exit code is 0. The output is never read.
   - Suites report a skip as a pass: `test_loopback_too.py:112,123,159` calls `check("SKIP - ...", True)`.
   - `_where.missing()` skips a suite when a backend file is absent (`_where.py:85`). This is the one that hides a broken backend folder.
   - The final line (2236) is "N suites passed. The backend is patched and proven."
   - If `$tests` is empty, it prints "0 suites passed ... proven".
   - Smallest fix: capture stdout, count lines matching `SKIP`, and print "N passed, M of them skipped (names)". Refuse the word "proven" if any suite skipped or zero ran. `run_suites.py` already has skip logic that could be reused.

3. Failure paths that still end "success". Read, not run.
   - Step 3 (1985-1991) and 3b (2040-2043) print FAIL for missing shipped modules, then continue.
   - A pip failure (2149) is the same.
   - With -SkipTests the script says "Done. Tests skipped." and exit 0 (2160) whatever happened above.
   - With tests run and passing, the last lines are still the green "backend is patched and proven" plus the start command. Earlier red FAIL lines scroll away.
   - The script never calls `exit 0` at the end. It just falls off, so the exit code is implicit.
   - Smallest fix: keep a `$problems` list. Print a final "DONE WITH PROBLEMS: ..." in red and `exit 1` if it is non-empty. End success with an explicit `exit 0`.

4. Half-patched real backend after a mid-way failure (1907-1940). Read, not run.
   - Each patch is applied in place. On failure the script prints "Copy them back, or run with -Revert" and exits 1.
   - Beginner problems: no copy-back command is given, and it does not say to restart Jarvis or that the backend may not start.
   - `-Revert` has to reverse a partly-applied stack. It only works per patch, with the older-text fallback.
   - Rehearsal and real run differ in one way that could cause this: the real folder is where `git apply` runs. If the backend sits inside another git repo (OneDrive, or an OpenJarvis clone), repo config and `.gitignore` apply, and `git apply` skips paths outside the current subfolder. The rehearsal in %TEMP% is in no repo.
   - Smallest fix: on failure, print a ready one-line restore, `Copy-Item "<backup>\*" "<backend>" -Force`. Add `--unsafe-paths`-free `git rev-parse` warning if the backend is inside a repo (not checked).
   - Also: a Jarvis that is running keeps old code in memory. There is no check for a running Jarvis (grep for `Get-Process` found nothing).

5. Rehearsal versus real apply. Mostly the same, with a caveat. Read, not run.
   - `Reset-Rehearsal` copies only `*.py` from the top level (1718). Patches touching any other file or a subfolder fail closed in the rehearsal, so that is safe.
   - The step 3 modules are copied after the patches in both, so the order matches.
   - The rehearsal does not model file locks, `.gitattributes`, `core.autocrlf` or `apply.whitespace`. It uses the global git config only, while the real run inside a repo also uses repo config.
   - CRLF is handled only for `+++ b/` targets of the current list (1471-1478). A target reachable only through an older-text undo is not converted.

6. The test stand-in CAN hide a bad hunk, and this is what bit the owner.
   - `backend/_stack.py:118-136`: it starts from an EMPTY file. When a hunk does not apply, it writes the hunk's own pre-image after a `# gap` line and applies it to that. So a hunk that skips a real middle line always "passes".
   - Its own docstring admits it: "scripts/apply-patches.ps1, on a copy of the real files, is the only proof."
   - No real original exists in the repo. `backend/jarvis_hud.py`, `jarvis_gate.py` and `jarvis_extract.py` are not there. `backend/fixtures` holds only hardware cases, LoCoMo and mouth data. There are no snapshots.
   - Only 7 files are patched: jarvis_hud.py, jarvis_gate.py, jarvis_extract.py, jarvis_memory.py, jarvis_events.py, jarvis_models.py, jarvis_skills.py.
   - Proposed strict check: `backend/test_real_originals.py`. Point it at `backend/originals/` (LF-normalised copies of those 7 files). For each patch in `_stack.order()`, apply it with `git apply --check` in a temp folder, in order, for real. Any failure is a hard FAIL. If the folder is absent, the check must print FAIL, not SKIP, on the owner's PC.
   - Even better, add a `_stack.py` mode with `strict=True` that raises instead of materialising, once real originals exist.
   - Blind spot: the originals must be the pre-patch versions. Copies from the owner's PC are already patched, so the check needs `-Revert` output or the `_jarvis-backup-*` folders. The oldest `_jarvis-backup-<date>` folder, or a run of the script with `-Revert` first, gives the originals.
   - Owner one-liner (from the backend folder; lands in the Desktop folder `jarvis-originals`). Run it after `-Revert`, or use the oldest backup folder as the source: `$b="C:\Users\<your-windows-name>\Documents\Claude\Open jarvis files\Desktop program"; $d="$env:USERPROFILE\Desktop\jarvis-originals"; New-Item -ItemType Directory -Force $d | Out-Null; 'jarvis_hud.py','jarvis_gate.py','jarvis_extract.py','jarvis_memory.py','jarvis_events.py','jarvis_models.py','jarvis_skills.py' | ForEach-Object { Copy-Item -LiteralPath (Join-Path $b $_) $d }; Write-Host "Copied to $d"`
   - Privacy: these files hold the owner's own code, not secrets, but they should be checked before being committed.

7. Encodings. Read, not run.
   - The script reads the CRLF and patch bytes with `ReadAllBytes` and `WriteAllBytes` (1346, 1358). No BOM is added and no re-encoding happens. That part is safe on 5.1.
   - `Get-Content` without `-Encoding` (1570, 1883) reads ANSI in 5.1. It only searches for `+++ b/<ascii>`, so that is harmless unless a target path is non-ASCII.
   - `Start-Transcript` writes UTF-8 with a BOM in 5.1, which is fine.
   - `??` was not found in the grep; the only `??` hits were in comments.
   - A BOM on line 1 of a backend file would break any hunk starting at line 1 (not seen).
   - A file with mixed line endings gets fully converted to LF (1497-1503). That is fine but unannounced.

8. Smaller items. Read, not run.
   - Paths with spaces: git and patch arguments go in arrays (1540-1550), so they are safe. The default path (`param`, line 89) contains "Desktop program", and the owner lost the space when copying it, which gives the clear "No folder at" error (1256). Good.
   - Backup folders are named per second (`$Stamp`, 1149), so there is no name clash. But nothing prunes them, and the space use is unreported: 7 files times each run, plus an endings backup.
   - `git` not on PATH is handled (1272). Execution policy is handled by the docs' `-ExecutionPolicy Bypass`.
   - Running twice on an already-patched backend is handled by rehearsal step (a). It skips the backup and goes on to step 3.
   - Long paths, OneDrive and NordLocker: not checked. Sync clients can hold file locks while `Move-Item` and `git apply` write.

OWNER DECISIONS

A. Fix 1: how? (recommended) Move the line-ending rewrite to after the rehearsal succeeds. Or just reword the message and leave the order.

B. Fix 2 and 3: is a final "DONE WITH PROBLEMS" and a nonzero exit code, or a "N skipped" note, wanted? (recommended) Both.

C. Check 6: is the owner willing to copy the seven original files into `backend/originals/`? (recommended: yes, one line, once). Otherwise the stand-in stays and can hide the same kind of bug again.

Not checked: any real Windows PowerShell 5.1 run, OneDrive behaviour, `git config apply.whitespace`, and the desktop/Android parts.
