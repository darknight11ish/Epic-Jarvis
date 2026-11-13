## Why this is urgent — `main` is red

`origin/main` at `a6f8496fe` has both required backend jobs failing on its push run (CI run `43384823744`): `backend` and `backend-windows` fail one suite, `test_patch_history.py`, on one check:

> FAIL  every earlier version of every patch in `git log` is in backend/patch-history

Cause: the GitHub-union pull request edited `backend/github-tools.patch` and `backend/approval-notice.patch` in four commits (`a922fb4`, `1ad8ae0`, `2b3b275` — that one touched both patches — and `264484a`) without rebuilding `backend/patch-history`, the step `CLAUDE.md` requires before committing a patch change. The consequence is wider than `main`: **every open pull request based on that `main` inherits the red required check**, which is why #1227/#1228/#1229/#1230/#1233 could not merge tonight despite their own code passing.

## Fix

`python3 tools/build_patch_history.py` on `main` writes the earlier versions the history was missing and refreshes `index.tsv`:

- `backend/patch-history/github-tools/{a922fb4,1ad8ae0,2b3b275}.patch`
- `backend/patch-history/approval-notice/2b3b275.patch`
- `backend/patch-history/index.tsv`

No product code, no patch text, and nothing in the live install changes. The tool deliberately leaves out four versions whose hunk headers do not match their own lines (`decks` 2e70954, `handoff-mode` 6982058, `thinking` e8ba023, `wellbeing` 31ad726) — no such text could ever have applied to a backend, so they are not real versions and stay out.

## Evidence (local, rebuilt tree)

- rebuild exit 0; the working tree gains exactly the four patch files and the `index.tsv` update
- `backend/test_patch_history.py` → **32 passed, 0 failed** (same tree before the rebuild: **31 passed, 1 failed**)
- `backend/test_patch_wellformed.py` → **16 passed, 0 failed**
- `tools/roll_changelog.py --check` and `tools/roll_decisions.py --check` → OK, one new fragment each
- Reproduced at the desk on a clean worktree of `origin/main` at `a6f8496fe` before the fix, so this is not a branch-only artefact

## Records

One `changelog.d` bullet and one `decisions.d` bullet: a patch edit is a two-part change (the patch **and** the history it came from), rebuilt last in the same PR — the same order the generated self-code map and recent-changes module already follow.

## After this merges

Main goes green again. The open PRs above need their branches updated onto the new `main` (or a re-merge) so their required `backend` run happens again; none of them needs a code change for this failure.
