# Docs review, 2026-10-11: what is accurate, what is stale, and what is not written down

**Written 2026-10-11 evening, off `origin/main` `9c91e1fb`.** Every claim about main below was read with
`git show origin/main:<path>` or `git ls-tree -r origin/main`, never from a working tree. Nothing was
written outside this worktree; `ci.yml` was not touched; no suite runner was used.

The point of this page is the second column. **A document that has quietly stopped being true is worse
than one that is late**, so the two audits that have drifted now carry a *Settlement* block beside the
original lines, in the pattern #312 settled: **keep the limit as written, put what is true now next to
it.**

## THE HEADLINE, FIRST: his machine is nearly current, and that is the good news

**He re-ran the patcher at 21:01 and it closed the machine-versus-repo audit's central gap.** That
audit said three features were absent and eight module checks failed; measured again with the same
rule, **the preflight reads 190 identical, 0 missing, 0 different - every one of those FAILs is gone**,
142 of 144 patches applied, and all three modules present. Two patch names are still missing from his
record and **they touch files that are byte-identical to main's**, so nothing observable is missing.
`AUDIT-2026-10-11-MACHINE-VS-REPO.md` now carries that as a **Settlement** block beside its original
lines - and with it a correction to one of its own tests, because `work.patch` wires `jarvis_work` as
route handlers rather than a startup call.

**What did not close is the desktop and the phone**, because both need an *install* rather than a patch
run: the desktop is now **five published builds behind** (0.2.140 against 0.2.145) and the phone is
**62 commits** behind. That is the gap that still costs him something.

---

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
  its count still holds, though `tools/check_*.py` is 22 now rather than 24). **Two independent audits
  reached the same seven**, and **#316 wires five of them** (`check_stale_twins`, `check_feature_list`,
  `check_lanes`, `check_registry_phone`, `check_screen_safety`); the other two cannot run anywhere but
  the owner's PC.
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
| `AUDIT-2026-10-11-CHECKS-THAT-PROVE-NOTHING.md` | **not on main, because it is on #310's branch `docs/checks-that-prove-nothing`** - which is also why a search of the scratch worktrees found nothing, and why the brief's file name differs from the real one. **Reviewed there**: its §2.1 MEDIUM finding - `backend/test_agent.py`'s `check("run_local_turn returns rather than looping forever", True)` - is **already settled on main** by `50b65550` ("a hanging check becomes a failing check"), which bounds the fake model so a runaway loop now **fails** instead of hanging, and adds a real assertion beside it (`len(calls) <= 3 + 1`, with the reason it is four calls). Its **line number is stale: 786 on that branch, 801 on main** | that branch carries its own page fix; the finding itself needs no action |

## 4. Today's work that was not written down anywhere durable

* **BLOCKED and NOT-TESTABLE are never counted as passes.** It was a rule inside one document; it is now
  a bullet in `CLAUDE.md` as well, so a reader who never opens the matrix still meets it.
* **Editing any file under `backend/` is a two-file change** - `backend/<file>` and
  `jarvis-backend/<file>` are kept equal, checked by `backend/test_base_matches_repo.py` (and
  `tools/check_stale_twins.py`), **neither of which any workflow runs**. It was documented in
  `jarvis-backend/README.md:211`; it is now also in `CLAUDE.md`, with the "not on CI" warning attached.
* **The phone may raise a spending limit with its own fingerprint** (#314, merged 2026-10-12) - already
  written down at `CLAUDE.md:666`; deliberately not duplicated.
* **`audit` and `python-advisories` are informational; six required checks gate a merge** - now in
  `CLAUDE.md`, with **both** pieces of evidence: the ruleset refused a direct push to `main` with
  *"6 of 6 required status checks are expected"*, and five PRs (#312, #314, #315, #317, #318) merged with
  those six green **while `audit` was red**. A red `audit` is therefore a signal to fix main's own state,
  never a reason to hold a PR.
* **The three dead ids in the field-test record** - `crash-notes`, `first-run` and `notifications` are
  named by its rows and are not on the current feature list. **Reconciliation is another agent's work,
  so this page only notes it** rather than duplicating it; until then the record's row list should not be
  read as exactly matching `features/features.json`.

## 5. What I could not run or verify

* **The one claim I could not verify from here has since been settled, and is now written down.** I could
  not confirm that six required checks gate a merge: the branch-protection API answers
  `404 Branch not protected`, which is a token-permission answer rather than a fact about the branch.
  **Two independent measurements settle it** - the ruleset refused a direct push to `main` with
  ***"6 of 6 required status checks are expected"***, and five PRs (#312, #314, #315, #317, #318) merged
  with those six green while `audit` was red. It is in `CLAUDE.md` now, with both, **because the cost of
  not knowing it was hours of holding mergeable work.**
* **Checks that need the owner's PC or a build**: `check_apk_16kb.py`, `check_obscura.py`,
  `check_work_claims.py`, and any suite that wants `JARVIS_BACKEND` pointed at his install. Not run; the
  reasons are in §1.
* **No surface stamps the commit it was built from** (the backend manifest has hashes, the desktop's two
  version fields both say `0.2.0`, the phone's `versionName` is a local counter), so "what is he running"
  is still inferred rather than read - the gap the machine-vs-repo audit's §"honest part" describes.
