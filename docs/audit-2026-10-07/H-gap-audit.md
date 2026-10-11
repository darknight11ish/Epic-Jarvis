# Stream H — gap audit: do the comments and claimed work actually exist?

**Target:** clean `main` worktree at `.dsh-scratch/audit-main`, commit `fa2b379f`
("Merge pull request #89 from darknight11ish/next-one-command", 2026-10-06).
**Method:** read `docs/CLAIMS.tsv` and `tools/check_claims.py` in full, ran the
register and the four wiring checkers, classified every claim check against the
line it actually matches, and hand-verified the suspicious ones with
`git log -S`, `git ls-files` and targeted reads. No product code was changed.

## Verdict

**The documentation is substantially honest, and the register is real.** I
examined **118 claim rows** (the file is 151 lines: 118 rows, 33 comment lines)
and independently re-derived the evidence for **every one of the 111 rows that
carries a definite check** (55 `grep`, 33 `absent`, 18 `file`, 2 `test`,
2 `number`, 1 `no-file`; the other 7 are `unverifiable` and say so) — plus the
four wiring checkers and the doc index. **109 of 111 rows held exactly as
written.** The two that did not are all one thing:
the register judges the **working tree**, so the two `test:` rows (B17, D06)
report failures caused by *this audit's own scratch and another stream's
uncommitted edit*, not by a regression. I found **9 new gaps**, none of them a
false safety claim: 4 stale comments and 5 counts of documentation drift. I
found **no new unreachable feature, no new unwired route or command, and no
missing work that the repo does not already record as open.**

`python tools/check_claims.py` → **exit code 1**, two errors, both disproved by
hand (H1). With a clean tree it would be **exit 0, 118 rows, 86 built, 25 open,
7 unverifiable**, and every one of those 116 definite rows is correct today.

**Counts by gap kind**

| Gap kind | New findings | Where |
|---|---|---|
| `stale-comment` | 4 | H3 (CLAUDE.md backups button), H4 (checker docstring), H7 (`jarvis_projects` goals link), H8 (a test name that never existed) |
| `drift` | 5 | H1 (working tree vs git), H2 (source column), H5 (prose-matched checks), H6 (patch table), H9 (docs index) |
| `unreachable` | 0 new | the real ones are found and printed by the repo's own checkers (see "Checked and holds") |
| `unwired` | 0 new | every route/command/event the checkers cover is accounted for |
| `missing-work` | 0 new | every gap I found that is already `open` in the register is still genuinely open |
| `undocumented` | 0 new beyond H6/H9 | — |

Already found by stream D, **not re-reported**: D2 (the checker judges the
working directory) and D4 (40 `CLAUDE.md:<line>` sources, nothing validates the
column). H1 and H2 add what D did not have: the exact mechanism of today's two
false failures, and the size of the drift.

---

## Findings

### H1. `check_claims.py`'s only red run today is caused by audit scratch and an uncommitted edit, not by a claim — so the register cannot be run to green while anyone is working

**Where:** `tools/check_claims.py:92` (`REPO = Path(__file__).resolve().parent.parent` — every check resolves paths on disk); `backend/test_shipped_modules.py:279` (`HERE.glob("*.py")`)
**The claim:** `tools/check_claims.py`'s own docstring, line 79: *"Exit code is non-zero only for a real violation: a broken direction above, or a register this check cannot read"*, and line 35: *"a `built` row whose check now FAILS - the thing regressed, or the claim was wrong when it was written"*.
**The reality:** I ran it. **Exit code 1**, headlined *"a claim written down as BUILT no longer holds"*, naming two rows:

* **B17** (`the shipped-module suite passes`) → `backend/test_shipped_modules.py exited 1: 549 passed, 2 failed | failed: backend/run_suites_audit.py is shipped, t_the_settings_diff_reports_what_differs`. The first failure is **audit scratch**: `backend/run_suites_audit.py` is untracked (`git status` → `?? backend/run_suites_audit.py`; `git ls-files backend/run_suites_audit.py` → empty), and `t_every_module_here_is_shipped` enumerates the directory with `HERE.glob("*.py")` and then demands every `*.py` here be in `$SHIPPED`. Nothing in git carries that file.
* **D06** (`the published base still matches this repository's own copies`) → `backend/test_base_matches_repo.py exited 1`, on *"jarvis_scrub.py (base 28264 B, repository 28868 B)"* and on 180-odd `__pycache__/*.pyc` paths. Both are working-tree artifacts: `git diff --stat backend/jarvis_scrub.py` → **13 insertions, 3 deletions** (another stream's in-flight edit), and the base copy is byte-identical to `HEAD:backend/jarvis_scrub.py` (file hashes compared); the `.pyc` files are untracked (`git ls-files "jarvis-backend/__pycache__"` → **0**) and ignored by `jarvis-backend/.gitignore:43` (`__pycache__/`).

**Confidence:** Confirmed
**Severity:** High (this is the register's headline signal; a red run that means "someone has a file open" trains the reader to ignore it — the exact failure mode the register was built to end)
**Gap kind:** `drift`
**Fix shape:** resolve every check against `git ls-files`/`git show` rather than the directory, or refuse to run on a dirty tree with a plain message.

### H2. The `source` column is unvalidated and 36 of its 40 `CLAUDE.md:<line>` citations land on unrelated text

**Where:** `docs/CLAIMS.tsv` rows A01–A38, B18, C23; read by `tools/check_claims.py:357-376` (the loop only checks the column is non-empty — `run_row` never receives it)
**The claim:** `docs/CLAIMS.tsv:16-17`: *"source is where the claim came from - file and line - so the original can be read. Every line number was right when its row was written"*.
**The reality:** three verified exactly, then swept:

* **B18** cites `CLAUDE.md:998` for the 60,000 shader budget. That sentence — *"60,000 shader budget still holds."* — is at **`:1004`**.
* **A01** cites `:1816` for the notifications settings screen. The queue item *"(1) a notification settings screen in both apps"* is at **`:1820`**.
* **A37** cites `:1803`, which is the *"Desktop hardening"* bullet. The sentence A37 is about is at **`:1809`**.
* **Sweep:** of the 40 rows citing `CLAUDE.md`, **36 cite a line that shares no word of five characters or more with their own claim text**. The four that do share a word are A10, A26, A30 and C23 — and A10's short claim *"tap-to-talk on the phone is built"* shares only "phone" with a line about the same queue, so the true figure for "cites the right line" is lower still. The drift is a consistent +4…+6 lines, from the 2026-10-05 pass that inserted text into the queue.
* The register's own header is stale the same way: line 20-21 says bucket A is the queue at *"CLAUDE.md:1812-1849"*; the queue begins at **`:1818`**.

**Confidence:** Confirmed (3 hand-verified, 36 by sweep)
**Severity:** Medium (the claim text and its check are correct — only the provenance has drifted, so no reader is misled about the product; but "so the original can be read" is currently not true for 36 rows)
**Gap kind:** `drift`

### H3. CLAUDE.md says the "Delete older backups now" button is queued in the apps; the desktop half has been built and wired since 2026-10-01

**Where:** `CLAUDE.md:1809-1810`
**The claim:** *"`POST /api/backup/delete-older` (one card) is built on the backend - **the apps' "Delete older backups now" button after an Erase is queued** (owner, 2026-09-30)."*
**The reality:** the desktop button is built, wired and granted: `jarvis-desktop/src/settings.html:2132` (`<button ... id="bk-delete-older" ...>Delete older backups now</button>`), `jarvis-desktop/src/backup-settings.js:87` (`deleteOlder: $("bk-delete-older")`), `jarvis-desktop/src-tauri/src/backup.rs:53` (`DELETE_OLDER_PATH = "/api/backup/delete-older"`), granted at `jarvis-desktop/src-tauri/permissions/surfaces.toml:560`. `git log -S"bk-delete-older"` dates all of it to **`eabca34d`, 2026-10-01** — the day after the note. Register row A37 has this right (`built`, check `grep:jarvis-desktop/src/settings.html:Delete older backups now`); its **source line is wrong** (H2) and points at the hardening bullet, which is why nobody noticed the sentence it should cite says the opposite. The phone half is genuinely still open (A38 is `open`, and `Delete older backups now` appears nowhere under `jarvis-client/`), so **half the sentence is stale and half still holds** — and no register row covers the stale half.
**Confidence:** Confirmed
**Severity:** Medium (a built feature documented as queued; the phone half is correct, so a reader could reasonably conclude "not built anywhere")
**Gap kind:** `stale-comment`

### H4. `tools/check_invoke_grants.py`'s docstring says two dead buttons are "in this tree today"; both were fixed and the checker is green

**Where:** `tools/check_invoke_grants.py:9-17`
**The claim:** *"Two of them are in this tree today and are exactly what this script exists to print: `brain.js`'s "Hidden menus" button calls `open_fix_place`, which lives in `surfaces.toml` under the quickbar's own set. The Brain's capability never grants it, so the button was dead in the window that draws it. … `brain.js` calls the four `brain_quiz_cloud_*` commands, each of which has a generated permission file under permissions/autogenerated/ and no grant in any set at all: every window's call is refused."*
**The reality:** running the script prints *"305 command(s) invoked from 10 page(s); every one is granted by the window whose page calls it."* and exits **0**. `open_fix_place` is now granted to the Brain window — `jarvis-desktop/tests/plain-errors.mjs:405` asserts `holders("open_fix_place")` is exactly `["open-fix-place", "quickbar-surface"]`. `brain_quiz_cloud_*` no longer appears anywhere under `jarvis-desktop/` (grep for `brain_quiz_cloud_grade|brain_quiz_cloud_plan` finds nothing). The docstring's present tense is the only thing left of both bugs.
**Confidence:** Confirmed
**Severity:** Low (a stale comment on a checker — but this is the file that exists to stop "a control that never works", and it now teaches the reader a bug class with a wrong example)
**Gap kind:** `stale-comment`

### H5. 9 of the 55 `grep:` claim checks are satisfied by a comment, docstring or UI string — those rows assert prose, not behaviour

**Where:** `docs/CLAIMS.tsv` rows **A05, A07, A27, A28, B14, C09, C13, C17, C51** (and A34's match, `backend/run_suites.py:117`, is the sentence inside `counts()`'s own docstring)
**The claim:** `tools/check_claims.py:29-32`: *"`state` is `built` and the check PASSES - the claim still holds"*. The check is a plain substring search by design (`search()`, lines 165-190).
**The reality:** I classified the matched line for all 55 `grep:` rows. 46 match code. 9 match prose only. Example: **A28**, *"changing a thinking level needs no approval card"*, is held by `grep:backend/jarvis_thinking.py:without requiring an approval card`, which matches the **docstring** at `backend/jarvis_thinking.py:167` — delete the feature and edit the sentence, and the row stays green. Likewise **A27** matches a docstring (line 152), **B14** a comment (`jarvis_voices.py:385`), **C09** a CSS comment (`brain.css:551`), **C51** a JS docstring comment (`sayable.js:2`).

**This is a checking-strength gap, not a false claim** — I hand-verified the substance of four of the nine and all four hold: `jarvis_thinking.py:89` returns `{"everyday": DEFAULT, "second": DEFAULT, "third": DEFAULT}` with `set_level()` at 165; `jarvis_voices.py:419` really does handle the v1.0 pack (`"v1" (Kokoro v1.0)`); `galaxy-panel.js` is imported at `brain.js:303` and drawn.

**Confidence:** Confirmed
**Severity:** Medium (it is the difference between "machine-checked" and "machine-checked against a sentence"; every one of the nine is currently true, so nothing is wrong today)
**Gap kind:** `drift`

### H6. `backend/README.md`'s patch list omits 5 of the 124 patches that ship — including `thinking.patch` and `youtube.patch`

**Where:** `backend/README.md` (patch list); the README's own promise at `backend/README.md:11-12`
**The claim:** *"counted from the `$PATCHES` list in `scripts/apply-patches.ps1`, which refuses to run if a `.patch` file here is missing from it"*.
**The reality:** `backend/` holds **124** `.patch` files, `scripts/apply-patches.ps1`'s `$PATCHES` holds **124** entries, and the two sets are **identical** (no drift in either direction — the script is honest). But `backend/README.md` names only **119** distinct patches. Not mentioned anywhere in it: **`accounts.patch`, `thinking.patch`, `tutorials.patch`, `web-search-switch.patch`, `youtube.patch`**. All five are in `$PATCHES` (`apply-patches.ps1:490, 955, 1035, 1071, 1096`) and all five ship a module (`jarvis_accounts.py`, `jarvis_thinking.py`, `jarvis_tutorials.py`, `jarvis_youtube.py`). The newest unlisted one is the Accounts addresses work that the CHANGELOG's own 2026-10-06 top entry describes.
**Confidence:** Confirmed
**Severity:** Low–Medium (the patch stack is complete; only its prose index is behind — but this README is what apply-patches depends on being read)
**Gap kind:** `drift`

### H7. A "not built yet" block in `jarvis_projects.py` went stale the next day — a goal step's measure *is* built

**Where:** `backend/jarvis_projects.py:38-44`
**The claim:** *"GOALS: jarvis_goals.py is on main now, but the link is not built yet (cohesiveness audit, 2026-09-29): … The goals.db `project` column, `GET /api/goals?project=<id>`, and a goal step's measure ({"bench": ..., "target": ...}) are still to come - … Until then a goal id here is not checked against goals.db."*
**The reality:** the third clause is stale. `jarvis_goals.py` has had a goal step's measure since **2026-09-30** (`git log -S'"project", "bench"' -- backend/jarvis_goals.py` → `6d244a6a`, then `d96f1ba1`): the measure is parsed at `jarvis_goals.py:253-254`, validated and checked at `349-356`, `check_measure()` at `537-541`, and `_read_bench()` at `459-463` pulls the number out of `jarvis_projects` itself. The comment was written 2026-09-29 (`git log -S"the link is not built yet"` → `0d76fc9a`). **The other two clauses still hold**, and I checked each rather than assuming: the `goals` table has no `project` column (`jarvis_goals.py:163-171` — `id, text, plan, status, created, changed, checkin_job`) and the route (PATH at `:830`, `_goal_route` at `:834`) accepts only `<id>/(accept|step|stop)`, with no `project` query.
**Confidence:** Confirmed
**Severity:** Medium (the block opens with a blanket "the link is not built yet", which a reader will take as covering the measure that exists)
**Gap kind:** `stale-comment`

### H8. `test_shipped_modules.py` gives its reason for `jarvis_style` as "imported only by `test_tripwire.py`" — a test that has never existed

**Where:** `backend/test_shipped_modules.py:63`
**The claim:** *"the owner's PC does have it, and it is published in jarvis-backend/jarvis_style.py, imported only by test_tripwire.py"*.
**The reality:** no `test_tripwire.py` is in the tree. `git ls-files | Select-String tripwire` returns exactly one path, `jarvis-backend/jarvis_tripwire.py` — a **module**, not a test. `git log -S"test_tripwire"` shows the string arriving in the two 2026-10-06 publish commits (`0c5bc2f9`, `00429a92`), and it names no file that ever existed at any commit. The reason for keeping `jarvis_style` out of `$SHIPPED` may still be correct (`jarvis-backend/jarvis_style.py` does exist, and `jarvis_events.py` does probe it by name) — but the *evidence* it cites is a phantom.
**Confidence:** Confirmed
**Severity:** Low
**Gap kind:** `stale-comment`

### H9. 36 top-level documents are named nowhere in `docs/README.md` (a previous audit said 31 — the real figure is 36 today, and it is already recorded as open)

**Where:** `docs/README.md` (the index); `docs/CLAIMS.tsv` rows C49 and C50
**The claim:** `docs/README.md:31-32`: *"This page says which document is which."* — the page describes itself as the index of the documents.
**The reality:** there are **144 `docs/*.md`** files; **108** of them are named anywhere in `docs/README.md` (as a link or in backticks). **36 are not named at all** — including load-bearing ones: `HANDOFF-2026-10-04-audit-pass.md` (which `CLAUDE.md:2067` calls *"**start here in a new conversation**"*), `BUILD-QUEUE-2026-09-30.md`, `SCREEN-DESIGN.md`, `PROJECTS-DESIGN.md`, `CHATBOT-DRIVER-DESIGN.md`, `LIPSYNC.md`, `AUDIT-2026-09-28-REPO-REFS.md`, `MENU-VISIBILITY-DESIGN.md`, `PAIRING-DESIGN.md`. **This is not a hidden gap**: the register already records the index as incomplete — C49 (`the docs index covers the current load-bearing documents`, `open`) and C50 (`the docs index mentions the audit-reports directory at all`, `open`) both still fail, correctly. Reported here only to settle the count: **36, not 31**, by the count of names mentioned in the page.
**Confidence:** Confirmed
**Severity:** Low (already known and recorded as open; the one new fact is the number)
**Gap kind:** `drift`

---

## Checked and holds (so the owner knows how much of this is honest)

**The register, row by row — 109 of 111 definite rows held exactly as written.**

* `python tools/check_claims.py` really does evaluate all six kinds, refuses a malformed row, refuses an `unverifiable` row whose reason starts with a kind name, and fails **both** directions (`run_row` → `regressed`/`closed`, lines 420-423). Its claim is true; only the tree it reads is wrong (H1).
* **Every `built` row's check passes and every `open` row's check still fails.** I re-derived the 25 `open` rows' evidence directly and each gap is genuinely still open: no phone notification settings screen (A09), no "approvals waiting" widget source (A11-A14, A17), no lane failover (A29), no per-patch "reads original text" ratchet (A33), no "Restore to before" (A35), no stale-area check (A36), no phone "Delete older backups now" (A38), no prompt-injection detector (B16), no `/api/goals?project=` (H7), VERSION still `0.2.0` (C48), no CHANGELOG entry for the 2026-09-30 features (C47) — `CHANGELOG.md`'s newest numbered section is still *"## 0.2.0 - 26 September 2026"*, everything later sitting under *"## Not in a numbered version yet"*.
* **All 18 `file:` rows** point at files that exist **and are git-tracked** — `git ls-files` against each: **0 problems**. (The checker only stats the filesystem, so I added the git half myself; nothing in the register is "held" by untracked scratch.)
* **The one `no-file:` row (D01)** is true: `docs/SOURCE-BUNDLE.md` does not exist and is not tracked.
* **Both `number:` rows** target tracked files and read true: B18 (60,000 in `CLAUDE.md` vs `tools/shader_size.py`) and B19 (7,680 MiB in `docs/SECOND-CARD.md` vs `backend/jarvis_second_card.py`) — only B18's *source* line has drifted (H2).
* The 7 `unverifiable` rows name their reason and no check, as the format requires.
* **No `open` row is "still open" by accident.** An `open` row fails its check, and `check_grep` also returns "not found" when the *path itself* is missing (`search()`, lines 174-175) — so a row citing a deleted file would report "still a real gap" having looked at nothing. I tested all 25: **every one names a path that exists** (0 bad paths, 0 missing suites). The gap H1 describes does not extend here.

**Every wiring checker the brief named runs green, and each states its own blind spots.**

| Checker | Result | What it covers | What it does **not** |
|---|---|---|---|
| `tools/check_parity.py` | exit 0 | 250 desktop routes vs 222 phone; 212 ported, 35 deliberately not, **1 still to port** (`/api/retrieve`), 0 planned | 3 routes sit in the Brain's `READ_ROUTES` allow-list that no window asks for (`/api/initiative`, `/api/digest`, `/api/config`) — printed, not counted |
| `tools/check_command_acl.py` | exit 0 | 343 commands, `lib.rs`'s `generate_handler!` and `build.rs`'s `.commands(&[…])` agree exactly | it does not check sets or grants — that is the next row's job |
| `tools/check_invoke_grants.py` | exit 0 | 305 call sites across 10 pages, every one granted by its own window | 27 runtime-built command names and 37 multi-window modules, each listed with a reason |
| `tools/check_event_names.py` | exit 0 | 18 event names across both roads; reads and dispatches balance | 5 **recorded** breaks in the HUD's vendored page, printed loudly on every run and correctly not failing the exit code |

* **The gate-action / `_RISK` pairing is covered, not missing.** `backend/test_gate_risk_rows.py` runs **exit 0**, and the patch it checks, `backend/gate-risk-rows.patch`, is both on disk and in `$PATCHES` (`scripts/apply-patches.ps1:1108`). Its docstring is honest that it cannot prove the patch applies to the owner's real `jarvis_gate.py` from a checkout — which is why I did not report the `draft_email` / `create_joplin_note` duplicate-key rows as a gap: the repo itself writes down that Python keeps the last of two equal keys and that the patch removes the stale one.
* **Rule 4's own invariant holds where it says it does.** `backend/jarvis_speech.py:37-42` — *"`hear()` verifies the SPEAKER through `jarvis_voice` before it ever runs speech-to-text"* — is true of the code: `_transcribe()` is called at `jarvis_speech.py:2444`, and the owner check that can refuse (`if not verdict.is_owner:` at `:2411`) is **33 lines earlier**. Nothing transcribes a non-owner's clip.
* **No comment names a real missing test.** I extracted all 277 distinct `test_*.py` names mentioned in `backend/` sources; 17 are absent from the tree, and every one is either a runtime fixture the suite-runner tests write (`test_good.py`, `test_bad.py`, `test_x.py` — `test_suite_report.py:122`) or explicitly retired in its own sentence (`test_agent_wiring.py`, named at `test_mcp_wiring.py:5` as *"which no longer applied"*). H8 is the single exception, and it names a test that never existed rather than one that has gone.
* **`THIRD-PARTY-NOTICES.txt` (143 KB) names what it must**: "Built with Llama" (Llama ×3), Kokoro (×16), sherpa (×15), Tauri (×44), Ollama, 318 Apache references, the CC BY-NC licence, and the maker's own GitHub name `darknight11ish`.
* **`docs/README.md`'s own numbers are honest about drift.** It prints the two commands that measure them and says *"re-measure it rather than trusting the digits above"*. I re-ran both: **292 documents today** against the page's 290 (measured 2026-10-06). That is the page behaving exactly as it promises, not a gap.
* `tools/check_*.py` is internally consistent: **13 referenced, 13 present, 0 missing.**

---

## Limits of this pass, and what to run next

* **I did not read the two big lists whole.** `CLAUDE.md` (134 KB) was read only through `grep`, targeted line ranges around the citations above, and the same for `docs/JARVIS-API.md` and `backend/README.md` (18.7 KB of patch prose). The claim checks that point into those files were verified by running them, not by reading every sentence around them.
* **The 118-row re-derivation is a re-derivation of the *check*, not of the *feature*.** For the 18 `file:` rows the claim is "this file exists", which I confirmed plus git-tracking. For the 55 `grep:` rows I classified all 55 match sites and hand-verified the substance of 4; the remaining prose-matched rows (H5) are true today but are the rows most able to rot silently.
* **One environment note.** Every checker ran cleanly under this sandbox, including `check_claims.py`, whose `test:` rows use `subprocess.run(capture_output=True)` — the EPERM-on-piped-stdio problem warned about in the brief **did not occur** here, so no finding is weakened by it.
* **The two `test:` rows could not be proved either way from this worktree**, only disproved as regressions: I showed the failures come from an untracked file and an uncommitted edit, and that the base copy matches `HEAD`. Confirming B17 and D06 green needs a clean clone of `fa2b379f` — `git stash`/`worktree add` and re-run `python tools/check_claims.py`. That is the single most useful next command for this stream.
