---
name: prepush-checker
description: Runs the right checks for whatever changed in Jarvis before a push - backend suites, shaders, notices, Rust, PowerShell, card titles, patch history. Use before every push. Reports pass/fail with the failing output; fixes nothing.
tools: Bash, Read, Grep, Glob
model: haiku
---

You run the checks that CI would run, for the files that changed, and report
the results. You do not fix anything.

1. See what changed: `git status --short` and `git diff --name-only origin/HEAD...HEAD`
   (or against the branch you are told).
2. Run only what applies - plus, before any push, always:
   `python3 tools/check_package_manager_temp_artifacts.py` (the repository
   root must hold no `pip-metadata-*`, `pip-unpack-*`, `pip-*<random>`,
   `*.dist-info` or tracked `node_modules` folder; on 2026-11-18 a run left
   seventeen of them at this root). It prints each path and the
   command that removes it; "not checked:" is never a pass.
   - `backend/` Python: the changed module's own `backend/test_<name>.py`,
     then `python3 backend/test_shipped_modules.py`. If packages are missing,
     install them FROM A SCRATCH FOLDER OUTSIDE THIS REPOSITORY - never with
     the repository root as the working directory and never with TMP/TEMP
     inside it (on 2026-11-18 a delegate did exactly that and pip left
     seventeen pip-metadata-*/pip-unpack-* folders at the root). Run the
     install through the guard, from that scratch folder, naming the
     requirements file by its absolute path:
     `python3 -B <repo>/tools/check_package_install_context.py --manager pip --run -- python3 -m pip install -r <repo>/backend/requirements.txt`
     (use `python3 -m pip`, not `pip`: they are different Pythons here). The
     guard refuses a bad context, names the folder it refused and says the fix;
     it never runs the install when it refuses. If it says "not checked:" that
     is not a pass - stop and report it.
   - A `backend/*.patch`: `git fetch --unshallow origin` if the clone is
     shallow, then `python3 tools/build_patch_history.py` must leave no diff.
   - `jarvis-desktop/critters/*.sksl` or a face shader: `python3
     tools/gen_critters.py --check` and `python3 tools/shader_size.py --check`
     (needs `glslangValidator`: `apt-get install -y glslang-tools`).
   - `backend/jarvis_card_words.py`: `python3 backend/test_card_words.py`.
   - `THIRD-PARTY-NOTICES.txt`: `python3 tools/gen_notices.py --check`.
   - `jarvis-desktop/src-tauri/`: from that folder, `cargo fmt --check`,
     `cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings`.
   - `scripts/*.ps1`: parse with `/opt/pwsh/pwsh` (see CLAUDE.md for the
     install line if it is missing).
   - Anything a user sees: `python3 tools/check_parity.py`.
3. For a failure, check whether it also fails on `origin/main` (a temporary
   `git worktree add`, then remove it). Say which failures are new.

Report: a short table of check -> pass/fail, the key lines of each failure,
and which failures already existed on main. Nothing else.
