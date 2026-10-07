# The 2026-10-07 bug audit — the eight per-stream reports

These are the working reports the audit produced, kept because
[`../BUG-AUDIT-2026-10-07.md`](../BUG-AUDIT-2026-10-07.md) - the summary meant
to be read - is built from them. That summary carries every finding that led to
a change; these carry the full reasoning, the exact `path:line` behind each one,
and the commands and measurements that were used to reach it.

| Report | What it covers |
|---|---|
| [`A-backend-python.md`](A-backend-python.md) | The Python backend (344k lines) and the patch stack's integrity |
| [`B-desktop-js-rust.md`](B-desktop-js-rust.md) | The desktop app: JavaScript in `src/`, Rust in `src-tauri/` |
| [`C-android-kotlin.md`](C-android-kotlin.md) | The Android app (488 Kotlin files) and the phone/desktop contracts |
| [`D-infra-ci-space.md`](D-infra-ci-space.md) | CI, the scripts, the dependencies, and the space measurements |
| [`E-open-pull-requests.md`](E-open-pull-requests.md) | The pull requests that were open during the audit |
| [`F-upstream-drift.md`](F-upstream-drift.md) | Every dependency, checked against its upstream |
| [`G-performance.md`](G-performance.md) | Where Jarvis is slow, with two re-runnable measurement scripts |
| [`H-gap-audit.md`](H-gap-audit.md) | Whether the comments and the claimed work match the code |

## Two things to know before reading them

**The paths are from a throwaway worktree.** The audit ran against a separate
checkout of `main` at `.dsh-scratch/audit-main`, so a `path:line` in these
reports is the real file at that commit - but the line numbers are pinned to
`main` as it stood at `fa2b379f`, and the fix pull request moves several of them.
`docs/BUG-AUDIT-2026-10-07.md` is the one to read for what changed.

**Three of the reports were produced under a sandbox that could not run
everything**, and they say so where it matters rather than guessing:

- 116 of the desktop's 151 test suites need a headless browser, which that
  sandbox refuses. The 33 that need none were run: 31 passed, and the 2
  failures were both the sandbox.
- The sandbox also refuses piped child output, which `backend/_stack.py` needs
  to run `git apply` - so the synthetic backend it builds came out empty and
  every patch test downstream failed. That was proven environmental by
  reproducing the identical failures on a **pristine `main`** worktree.
- Nothing was fixed from these reports alone. Every finding that became a change
  was re-verified by compiling the file, running its own suite, or reproducing
  the behaviour first and after.
