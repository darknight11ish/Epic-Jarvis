# Docs review, 2026-10-11: what is accurate, what is stale, and what is not written down

**Written 2026-10-11 evening, off `origin/main` `9c91e1fb`.** Every claim about main below was read with
`git show origin/main:<path>` or `git ls-tree -r origin/main`, never from a working tree. Nothing was
written outside this worktree; `ci.yml` was not touched; no suite runner was used.

The point of this page is the second column. **A document that has quietly stopped being true is worse
than one that is late**, so the two audits that have drifted now carry a *Settlement* block beside the
original lines, in the pattern #312 settled: **keep the limit as written, put what is true now next to
it.**

## 1. What I ran, and what it said

The `audit` job has **13 steps** (the brief said 17; `ci.yml` at `9c91e1fb` has 13 in that job). All
thirteen were run here, on this branch, which is main merged in plus the page fix:

| step | tool | result |
|---|---|---|
| 1 | `tools/gen_notices.py --check` | exit 0 - notices up to date |
| 2 | `tools/check_media_csp.py` | exit 0 |
| 3 | `tools/check_plugins.py` | exit 0 - 20 passed, 0 failed |
| 4 | `tools/gen_plugin_catalogue.py --check` | exit 0 - 50 files compared |
| 5 | `tools/check_event_names.py` | exit 0 - 5 known breaks, each recorded |
| 6 | `tools/check_literal_keys.py` | exit 0 |
| 7 | `tools/check_invoke_grants.py` | exit 0 - 40 modules judged where the window allows |
| 8 | `tools/check_same_tick_paths.py` | exit 0 |
| 9 | `tools/check_tutorial_places.py` | exit 0 |
| 10 | `tools/check_vacuous_checks.py` | exit 0 |
| 11 | `tools/check_claims.py` | exit 0 |
| 12 | `tools/check_defect_register.py` | exit 0 - 5 open, 3 closed |
| 13 | `tools/check_docs_map.py` | **fails on main; passes here** - see §2 |

So the brief's summary is right: **step 13 (the documents count) is the one that fails on main**, and
this branch carries the fix. Two things worth adding to it:

* **Seven checkers are named by no workflow** and therefore no job runs them, whichever branch you are
  on: `check_feature_list.py`, `check_lanes.py`, `check_obscura.py`, `check_registry_phone.py`,
  `check_screen_safety.py`, `check_stale_twins.py`, `check_work_claims.py` (the coherence audit's §1;
  its count still holds, though `tools/check_*.py` is 22 now rather than 24).
* **Three of those cannot pass anywhere but the owner's PC** and were red when run here for those
  reasons alone: `check_apk_16kb.py` (no APK built), `check_obscura.py` (Obscura not installed),
  `check_work_claims.py` (its evidence is untracked - `exit=2` by design). `check_claims.py`, which the
  coherence audit listed as red, **exits 0 in a plain checkout**: its red was the owner's installed
  backend being compared, which is the drift the machine-vs-repo audit measures, not a fault in main.

## 2. Accurate as of `9c91e1fb`

These hold, and something checks them:

* **the claims register** - `check_claims.py` exit 0 (8 rows still name no definite check and say so);
* **the defect register** - `check_defect_register.py`: 5 open, 3 closed, every named file real;
* **the plug-in catalogue** and the patch stack - `check_plugins.py` 20/0, the generated catalogue is
  current;
* **twins, patch order, encoding, generated files** - re-checked by the audit job's steps and the
  coherence audit's §§2, 5 and 6, unchanged;
* **`docs/FIELD-TEST-MATRIX-2026-10-11.md`** - its rule ("a feature that could not be reached is never a
  pass") is at line 51 and its 45 rows were cross-checked against the record in #303;
* **`docs/FIELD-TEST-HOW-TO-READ-THE-APPS.md`** - every document and script it names exists;
* **`CLAUDE.md`'s phone-limit amendment** - the owner's 2026-10-11 decision is recorded at line 666.

## 3. Stale, and what it now says

| document | what had drifted | where it is now settled |
|---|---|---|
| `AUDIT-2026-10-11-MACHINE-VS-REPO.md` | **he re-ran the patcher at 21:01**, so its central gap closed: `run: partial` with **142 of 144** patches (was 139), **two** patches unapplied (was five), **all three modules present**, and the preflight's rule reads **190 identical, 0 missing, 0 different** (was 182/3/5). It also had **one wrong test**: `work.patch` wires `jarvis_work` as route handlers, not a startup call. The desktop moved on too (0.2.142 -> **0.2.145**) and the phone (45 -> **62** commits). | its own **Settlement** block, added by this PR |
| `AUDIT-2026-10-11-IS-MAIN-COHERENT.md` | `tools/check_*.py` is **22**, not 24 (the seven unnamed checkers are unchanged); its §4 "red today" row for `check_claims.py` is environmental rather than main's | its own **Settlement** block, added by this PR |
| `docs/README.md` (**the page itself**) | main's tree held **352** documents while the page said **351**; that one-number lag is what has had **seven open PRs red on the `audit` job** | the page now carries the tool's own count for the tree it ships |
| `docs/CHECKS-THAT-PROVE-NOTHING.md` | **it is not on main** - `git ls-tree -r origin/main` has no such file, and a search of the scratch worktrees found none. It may be on an unfetched branch | **cannot be reviewed here**; tell me the branch and I will review it |

## 4. Today's work that was not written down anywhere durable

* **BLOCKED and NOT-TESTABLE are never counted as passes.** It was a rule inside one document; it is now
  a bullet in `CLAUDE.md` as well, so a reader who never opens the matrix still meets it.
* **Editing any file under `backend/` is a two-file change** - `backend/<file>` and
  `jarvis-backend/<file>` are kept equal, checked by `backend/test_base_matches_repo.py` (and
  `tools/check_stale_twins.py`), **neither of which any workflow runs**. It was documented in
  `jarvis-backend/README.md:211`; it is now also in `CLAUDE.md`, with the "not on CI" warning attached.
* **The phone may raise a spending limit with its own fingerprint** (#314, merged 2026-10-12) - already
  written down at `CLAUDE.md:666`; deliberately not duplicated.
* **The three dead ids in the field-test record** - `crash-notes`, `first-run` and `notifications` are
  named by its rows and are not on the current feature list. **Reconciliation is another agent's work,
  so this page only notes it** rather than duplicating it; until then the record's row list should not be
  read as exactly matching `features/features.json`.

## 5. What I could not run or verify

* **The `audit` job is informational in this repository as far as I can see.** The brief says six
  required checks gate a merge; **I could not confirm that**: the branch-protection API answers
  `404 Branch not protected` for `main` (which can also mean the token cannot read it), and no document
  in the tree lists those six. **This is the one claim above I am not recording as a decision**, because
  I cannot check it - if it is true it belongs in `CLAUDE.md` too, and I will add it on your word.
* **Checks that need the owner's PC or a build**: `check_apk_16kb.py`, `check_obscura.py`,
  `check_work_claims.py`, and any suite that wants `JARVIS_BACKEND` pointed at his install. Not run; the
  reasons are in §1.
* **No surface stamps the commit it was built from** (the backend manifest has hashes, the desktop's two
  version fields both say `0.2.0`, the phone's `versionName` is a local counter), so "what is he running"
  is still inferred rather than read - the gap the machine-vs-repo audit's §"honest part" describes.
