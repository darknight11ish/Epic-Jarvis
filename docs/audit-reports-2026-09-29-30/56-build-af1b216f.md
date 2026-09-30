# Report 56 (build), agent af1b216f, 2026-09-30T07:30Z

> **What it was asked** (first 600 characters of the task): You are in a git worktree of Epic-Jarvis. Read CLAUDE.md fully first (PowerShell rules: owner has Windows PowerShell 5.1, run under /opt/pwsh/pwsh 7 for testing but read for 5.1-only pitfalls; plain words for a beginner owner; verify before claiming; patch-history rule). Do NOT push or open a PR; commit on your worktree branch and report branch+sha. Edit ONLY scripts/apply-patches.ps1, backend/test_apply_line_endings.py (and a new sibling test file if you prefer), and docs/UPDATE-AND-CHECK-2026-09-28.md. A read-only audit of the update path (scripts/apply-patches.ps1, 2256 lines) found these; 

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Branch `worktree-agent-af1b216ff3bb3b71b`, commit `286207b9`. Not pushed, no PR. Edited only scripts/apply-patches.ps1, backend/test_apply_line_endings.py, new backend/test_apply_outcomes.py, docs/UPDATE-AND-CHECK-2026-09-28.md. The patch list is untouched.

WHAT CHANGED (all in the script)
1. -FixLineEndings only finds CRLF files early. The rehearsal now runs on a copy converted with Copy-AsLf. The real files are converted only after the rehearsal and every check pass. Each file is converted via temp+replace. If one is locked, files already converted are restored from the endings backup, orphan .lf-tmp files are removed, and the message names the file and says close Jarvis. Every failure message is now true about what changed.
2. Each suite's output is read. SKIP lines and "N skipped" summaries are counted and the suite is named. It never prints "proven" with any skip, zero suites, a failure, or a partial install (-SkipMissing).
3. A problems list and one `Finish-Run` end: green ALL DONE, yellow DONE but NOT fully proven, or red DONE WITH PROBLEMS. Exit codes are explicit (0/1), and a `trap` catches unplanned errors. Step 3/3b missing modules, pip failure, missing settings file, no Python and -SkipTests now show up in the ending.
4. Half-patched failure: prints a one-line restore command and says do not start Jarvis. A running-Jarvis check (Get-CimInstance, ps fallback on Linux) stops the run unless `-Force`. After applying, the real files are checked a second time.
5. The last screen names the backup folder and says old `_jarvis-backup-*` folders can be deleted. The doc covers all of this.

CORRECTION TO THE AUDIT BRIEF
I could NOT reproduce "git apply skips paths outside the subfolder". Patch paths resolve relative to the current folder. What I did reproduce: inside an outer repo with `*.py text eol=crlf`, the real run diverges from the rehearsal (the rehearsal runs in %TEMP%, outside any repo). The fix is `GIT_CEILING_DIRECTORIES` set to the parent folder around every git call, plus the second check. No `--directory` is used.

TESTS
- New test_apply_outcomes.py: 59 pass, 0 fail.
- Run against the OLD script: 35 fail, 17 pass. The 17 that pass are ones the old script already satisfied, e.g. "-SkipTests never says proven".
- test_apply_line_endings.py: 11 pass. Its three old -FixLineEndings assertions only passed because of the bug. On the full patch list a stand-in backend cannot take the stack forward, so the rehearsal fails and nothing is converted. Those assertions now check that.
- Also passing: test_patch_history (24), test_gate_stack_clean, and run_suites for test_shipped_modules, test_installed_stand_in, test_tool_updates.
- test_suite_state and test_rebuilt fail here because this container's `cryptography` is broken (`_cffi_backend` missing). They do not touch the script, but I did not compare against a baseline run.
- Most tests use a copy of the real script with the patch list cut to two patches, since no stand-in can take all 103 forward. Only the CRLF-with-missing-files and failed-rehearsal checks run the unmodified script. Override the script with env `JARVIS_TEST_APPLY_PS1`.

COULD NOT VERIFY
- Real Windows PowerShell 5.1. I only read for 5.1 pitfalls: ASCII only, no `??` or ternary, no -AsHashtable.
- GIT_CEILING_DIRECTORIES with a Windows path, and Get-CimInstance on a real Windows PC.
- A real locked file. I simulated it on Linux with a directory at the .lf-tmp path.

PASTE-READY FOR CLAUDE.md
Fixed 2026-09-30, after a read-only audit of the update script (`scripts/apply-patches.ps1`; commit 286207b9): (1) `-FixLineEndings` used to rewrite the owner's real files before the missing-file check and the rehearsal, so "NOTHING HAS BEEN CHANGED" could be false. It now rehearses on a converted copy and converts the real files only afterwards. A locked file rolls back and names the file. (2) Test suites are read for SKIP and never called "proven" with a skip, zero suites, or a partial install. (3) Failures end as a red "DONE WITH PROBLEMS" list with exit 1, and success as green or yellow with exit 0. (4) A half-patched backend gets a one-line restore command. A running Jarvis stops the run (`-Force` overrides). The real files are checked again after patching, and git is told to ignore an outer repository (GIT_CEILING_DIRECTORIES). The audit's "git skips paths outside the subfolder" claim was not reproduced. What was reproduced is a repo-attributes (`eol=crlf`) divergence between the rehearsal and the real run. Tests: `backend/test_apply_outcomes.py`. Not run on real Windows PowerShell 5.1.
