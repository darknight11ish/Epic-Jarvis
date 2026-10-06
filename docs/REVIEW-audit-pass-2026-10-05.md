# Review: branch `audit-pass-2026-10-05`

Reviewer: `next-auditpass-review`. Read-only. Nothing here merges anything, and
no pull request was opened.

Reviewed at `43f60139` (7 commits), against `origin/main` = `acf3ffbd` and
`origin/integration/backlog` = `1345b65d` (PR #79, unmerged).

---

## Verdict: superseded - close it, do not merge

Every one of the seven commits is already in `main`, byte for byte, arriving by
a different route (PR #47 `04ea68c7`, PR #48 `51de8e6d`, PR #49 `acf3ffbd`).
Merging this branch would not add the audit pass. It would **remove** part of
it: the branch is 38 commits behind `main`, so a merge computes as a net
*deletion* of 1,616 lines across 43 files.

```
$ git diff --shortstat origin/main origin/audit-pass-2026-10-05
 43 files changed, 266 insertions(+), 1616 deletions(-)
```

The one thing worth doing with this branch is what the owner can do in a
minute: nothing. There is no unique content to salvage - see "what the branch
uniquely adds" below, which is six one-line-or-smaller cosmetic variations,
each of which `main` already solved differently or better.

### The proof, one command per claim

Each branch commit has a twin in `main` with the same subject and the same
body, and the files each one touches are the *same blob* in both refs:

```
$ for f in <files touched by commit>; do
    git rev-parse origin/main:$f ; git rev-parse origin/audit-pass-2026-10-05:$f ; done
```

| branch commit | files | identical to main | main twin |
|---|---|---|---|
| `0d03c72b` voice gate | 16 | 14 | `76b21afc` |
| `ca997319` widget/notifications | 15 | **15** | `6a37a9a5` |
| `c0c99e7a` revive three features | 12 | 11 | `a9d8b3c5` |
| `3de8b7d5` 153 fake-skip tests | 80 | 67 | `c3607342` |
| `0667d224` four guards + install path | 10 | 9 | `93de4e39` |
| `ef24bb8e` audit pass recorded | 16 | **16** | `dee0b330` |
| `43f60139` wording | 14 | 13 | `f4eaf03f` |

The "identical" count is per *file*, and the misses are the branch being
*older*, not the branch being *different work*. `git merge-base --is-ancestor
origin/audit-pass-2026-10-05 origin/main` exits 1 - the branch is not an
ancestor, because its seven commits are independent copies with different
hashes. That is exactly why a careless merge is dangerous here: git sees no
relationship, so it treats the branch's stale older files as real edits.

Also worth knowing: the branch adds **no file that `main` does not already
have**.

```
$ git diff --name-status --diff-filter=A origin/main origin/audit-pass-2026-10-05
(no output)
```

---

## Per-commit verdict

| commit | claim | does the code do it | still needed on today's `main` | conflict risk |
|---|---|---|---|---|
| `0d03c72b` | blend with no voice print is refused (`BLEND_NO_PRINT`) | Yes - real code, real refusal, `blend_check` returns `_keep_blend(..., ok False, unchecked True)` | **No.** `backend/jarvis_voices.py` is the *same blob* in `main` (`1db7a84e`) | clean pre-#79; text conflict post-#79 via `jarvis_voices` siblings |
| `ca997319` | widget decides the card it painted; notification switches gate the posters; CSP `media-src` gains `data:` | Yes - `approval-target.js` (94 new lines) + a real `notifications.rs` (747 lines) + the CSP fix | **No.** All 15 files `IDENTICAL` to `main`, including `notifications.rs`, `approval-target.mjs`, `widget.js` | clean |
| `c0c99e7a` | three dead features revived (Grade this better, Brain hidden-menus button, What Jarvis can see); shared key is first-pair only; ntfy.sh no longer default | Yes on all three - grants added (`open-fix-place`, `brain-quiz-cloud`), button now delivers the place through `localStorage` then calls with `place: "settings"` | **No.** All three live in `main` (`capabilities/brain.json`, `brain.js`, `surfaces.toml`) | clean |
| `3de8b7d5` | 153 `check("SKIP...", True)` sites are now real `skip(why)` | **Yes and it is honest work** - see below | **No, and main went further.** 86 files define `skip()` in both refs; `main` then fixed what this commit left broken (Windows timer-tick folder names) | 13 test files conflict post-#79, all "keep main's" |
| `0667d224` | four new guards + install path | Yes - ran the guard here: `301 command(s) invoked from 10 page(s); every one is granted...` exit 0 | **No.** All four tools and `install-backend.ps1`, `measure-cards.ps1`, `README.md`, `INSTALL.md` are `IDENTICAL` to `main` | `.github/workflows/ci.yml` |
| `ef24bb8e` | audit pass and work order recorded (docs only) | Yes, docs only | **No.** All 16 files `IDENTICAL` to `main` | 4 docs files conflict post-#79, all because #79 adds to them |
| `43f60139` | wording: "Expired" -> "Timed out" everywhere; forced-colors block; 46em measure | Yes, but tiny | **No.** 13 of 14 files `IDENTICAL`; only `scripts/apply-patches.ps1` differs, and `main`'s is newer | clean |

### Nothing in this branch is "only a comment" or a renamed variable

That question was worth asking and the answer is no: every commit carries real
behaviour. `0667d224`'s guards are 2,177 lines of real checker; `ca997319`'s
`notifications.rs` is 747 lines with a real gate at each of the four posters;
`c0c99e7a` adds real capability grants. The defect is not emptiness, it is
duplication.

---

## The two big claims

### "153 fake-skip tests made honest" - **real, and already in `main`**

The claim is true, and the direction is the good one. Read the code, not the
message: each suite had a helper named `skip()` whose body called
`check("<string saying skip>", True)` - the condition was the constant `True`,
so the line printed as a pass and `run_suites.py` counted it as one.

`backend/test_chat_marks.py` before/after is the clearest single example:

```python
-def skip():
+def _no_crypto():
     if H.AESGCM is None:
-        check("SKIP - the cryptography package is not installed", True)
+        skip("the cryptography package is not installed")
         return True
     return False
```

A real `skip(why)` helper was added beside each suite's `check()`, `SKIPPED`
is its own list, `run_suites.py` aggregates skips separately, and the summary
line reads `N passed, N skipped, N failed`. **No check was quietly disabled:**
the decision "this machine cannot test this" is still made in exactly the same
place, and the body that follows it is still skipped by the same early
`return`.

Verification on the committed tree:

```
$ git grep -l "def skip(" origin/main -- backend | Measure-Object -Line   -> 86
$ git grep -l "def skip(" origin/audit-pass-2026-10-05 -- backend | ...   -> 86

$ git ls-tree -r --name-only origin/main -- backend | grep test_*.py | wc -l              -> 250
$ git ls-tree -r --name-only origin/audit-pass-2026-10-05 -- backend | ... | wc -l       -> 250
$ git ls-tree -r --name-only <merge-base> -- backend | ... | wc -l                       -> 249
```

Test-file count went **up** by one, not down: `backend/test_home_nav_row.py` is
new, and it is the same blob (`4cc3230b`) in both refs. Nothing was deleted to
make a number look better.

**Independent re-derivation of the count, and a correction to it.** My own
regex over the committed revision finds **141** sites matching
`check(<string>, True)`, not 153. My pattern is narrower than theirs (theirs is
an AST sweep, mine is a line regex and will miss a call split across lines or
written with a doubled quote style), so 141 is a floor, not a refutation - but
I could not reproduce 153 exactly. **Not established:** the exact figure 153.

**Where the branch is behind `main` on the same work.** `main`'s `c3607342` is
this commit, and then `1c3693e6` fixed a real bug the branch still has: a
throwaway folder named from `time.time_ns()` collides on Windows, because that
clock only moves on the system timer tick, so two calls in one tick get the
same name and the second `mkdir` dies with `WinError 183`. Example from
`backend/test_obsidian_notes.py`:

```python
main:   v = Path(tempfile.mkdtemp(dir=_TMP, prefix="vault"))
branch: v = _TMP / f"vault{time.time_ns()}"
```

`backend/test_backup.py`: `main` has 9 `mkdtemp` calls and the branch 3.
`backend/test_bind_wildcard.py`: `main` distinguishes "this machine's resolver
refuses the spelling" (`False`) from "cannot be asked" (`None`) and asserts
both; the branch collapses them to `None`. These are the branch's files being
older, and merging would put the timer-tick bug back into three suites.

### "Three dead features revived" - **real, dead, and live in `main` today**

Each one is named in the commit body, and each is genuinely present in `main`
now. The mechanism was the same every time: a page called a Tauri invoke that
no capability had granted to *that window*, the ACL refused it, and the refusal
was swallowed.

1. **"Grade this better"** (Brain -> quiz). Revived by granting
   `brain-quiz-cloud` to the `brain` window.
   `git show origin/main:jarvis-desktop/src-tauri/capabilities/brain.json`
   contains `"brain-quiz-cloud",`.

2. **The Brain's own "hidden menus" rail button.** Two faults: the `brain`
   capability had no `open-fix-place`, *and* the call asked for
   `place: "menu-visibility"`, which `open_fix_place` does not accept (it takes
   `settings`, `brain`, `history`). Revived by adding the grant and by
   delivering the place through `localStorage` (the way the Jarvis bar already
   did) before calling with `place: "settings"`. Present in `main`:
   `git show origin/main:jarvis-desktop/src/brain.js` has that handler with
   its comment; `permissions/surfaces.toml` in `main` defines the
   `open-fix-place` set.

3. **"What Jarvis can see"** (Settings -> Look at this / Watch with me), a
   privacy control. Revived by granting it to the window that calls it.

Corroboration from the guard itself. I ran it in my worktree at the branch's
tip:

```
$ python tools/check_invoke_grants.py
301 command(s) invoked from 10 page(s); every one is granted by the window whose page calls it.
26 call site(s) pass a name built at runtime, each listed in this script with its reason.
37 module(s) are loaded by more than one window, so their calls are judged only where the
window's own code reaches them (animal-shared.js, auto-learn.js, barge-in.js, briefing.js, ...)
[exit 0]
```

The commit's "10 errors to 0" is therefore confirmed at 0 today. **Not
established:** that the pre-fix count was exactly 10 - I did not reconstruct
the pre-fix tree to count it.

The other half of that commit also holds up: the shared pairing key is now a
first-pairing bootstrap (`first_pair_only`), and `alerts` no longer defaults to
the public `ntfy.sh` with a defaulted address. Both are in `main`.

---

## What the branch uniquely adds: nothing that matters

Files where the branch's content differs from `main`, and what the difference
actually is:

| file | branch vs main | real value |
|---|---|---|
| `backend/README.md` | 3-line wording: `jarvis_gate.py` named in prose instead of a markdown link | none - `main` also explains the file is owner-only |
| `scripts/apply-patches.ps1` | branch lacks the `-c core.autocrlf=false -c core.eol=lf` pin on its writing `git apply` | none; branch is older (`677844d6` added it) |
| `backend/_stack.py` | ratchet pinned `44` vs `main`'s `45`; branch also carries a long comment about a 116-vs-121-patch walk | none; the pin follows the patch stack, and the stack here is `main`'s |
| `jarvis-desktop/src/brain.js` | branch puts `tutorials` last in `VIEWS` and drops the `rail-tabs.mjs` cross-reference | none; `main`'s ordering matches the rail, and `rail-tabs.mjs` was retired for `a11y.mjs` |
| `backend/test_backup.py`, `test_obsidian_notes.py`, `test_bind_wildcard.py` (+10 more) | branch has `time.time_ns()` folder names; `main` has `tempfile.mkdtemp` | none; branch would reintroduce `WinError 183` |

`main` also has work this branch never had: `tools/check_same_tick_paths.py`
(523 lines) and `jarvis-desktop/tests/rail-tabs.mjs` (230 lines). The rewording
commit's "Expired -> Timed out" change *is* in `main` (`ApprovalCard.kt` is the
same blob) - it reached `main` through PR #47's own version of the commit.

---

## Conflict map against the POST-#79 world

Simulated, no writes, no checkout:

```
$ git merge-tree --write-tree origin/integration/backlog origin/audit-pass-2026-10-05
7fa967a06b2b009a9ba68735213d7a04d2049ce4
... 19 conflicted files ...
```

**16 conflicted files post-#79, against 4 pre-#79.**

```
$ git merge-tree --write-tree origin/integration/backlog origin/audit-pass-2026-10-05 2>&1 |
    Select-String "^CONFLICT \(content\): Merge conflict in (.+)$" | Sort-Object -Unique
16 files: .github/workflows/ci.yml, .gitignore, backend/_stack.py, backend/README.md,
backend/run_suites.py, backend/test_agent_plan_wiring.py, backend/test_bind_wildcard.py,
backend/test_briefing.py, backend/test_decks.py, backend/test_injection_cases.py,
backend/test_reach.py, backend/test_research.py, backend/test_task_control.py,
backend/test_tool_calling_wiring.py, docs/README.md, jarvis-desktop/src/brain.js

$ ... origin/main ...   ->  4 files: .github/workflows/ci.yml, backend/_stack.py,
                                backend/test_bind_wildcard.py, backend/test_tool_calling_wiring.py
```

So the dry-run warning was right in kind and understated in size: `ci.yml` does
not just conflict more, it drags twelve more files into conflict with it, and
`.gitignore` - named in the warning - only conflicts *after* #79 lands.

| file | ours (#79) vs theirs (branch) | severity | right resolution |
|---|---|---|---|
| `.github/workflows/ci.yml` | 58 added / 252 removed by theirs | **high** | keep #79's; the branch's copy is 996 lines vs 1106 and has **no `check_same_tick_paths` guard step at all** |
| `backend/README.md` | 6 / 203 | low-med | keep #79's |
| `docs/MEASURE-CARDS.md` | 8 / 227 | low-med | keep #79's (same file in `main` and branch; #79 adds to it) |
| `backend/run_suites.py` | 17 / 113 | low-med | keep #79's; the branch's skip machinery is identical to `main`'s |
| `backend/test_bind_wildcard.py` | 9 / 57 | medium | keep #79's - exactly the `False`/`None` distinction above |
| `docs/README.md` | 11 / 23 | low | keep #79's |
| `docs/MEASURED-2026-10-05-owner-pc.md` | 0 / 22 | low | keep #79's |
| `backend/_stack.py` | 4 / 27 | low | keep #79's ratchet |
| `jarvis-desktop/src/brain.js` | 8 / 31 | low | keep #79's |
| `backend/test_agent_plan_wiring.py` | 4 / 5 | trivial | keep #79's |
| `backend/test_briefing.py` | 4 / 5 | trivial | keep #79's |
| `backend/test_decks.py` | 4 / 4 | trivial | keep #79's |
| `backend/test_injection_cases.py` | 4 / 5 | trivial | keep #79's |
| `backend/test_research.py` | 4 / 5 | trivial | keep #79's |
| `backend/test_reach.py` | 1 / 29 | trivial | keep #79's |
| `backend/test_task_control.py` | 1 / 2 | trivial | keep #79's |
| `backend/test_tool_calling_wiring.py` | 1 / 1 | trivial | keep #79's |
| `docs/SESSION-HANDOFF-2026-10-05-audit-pass.md` | 0 / 10 | trivial | keep #79's |
| `.gitignore` | 0 added / 9 removed by theirs | trivial **only in git's eyes** | keep #79's - see the trap below |

Read the "right resolution" column as one instruction: **take `#79`'s side in
every one of the 19.** No audit-pass content is lost by doing so, because the
audit-pass content in all 19 is already in `main` and therefore already in
`#79`.

Three of those 19 (`docs/MEASURE-CARDS.md`, `docs/MEASURED-2026-10-05-owner-pc.md`,
`docs/SESSION-HANDOFF-2026-10-05-audit-pass.md`) are *not* in `git merge-tree`'s
conflict list: they auto-merge. I list them because they are the auto-merges
that need a human eye - each is a file where `main` and the branch are the
**same content** and `#79` adds ~22-227 lines on top, so an auto-merge silently
keeps `#79`'s additions and there is nothing to decide. They are in the table
for completeness, not because a conflict marker will appear.

### The one trap in this map: `.gitignore`

`.gitignore` conflicts while having **zero content difference** between `#79`
and the branch:

```
$ git rev-parse origin/integration/backlog:.gitignore     -> 846bfe7d
$ git rev-parse origin/audit-pass-2026-10-05:.gitignore   -> 1664346f
$ git merge-tree ... -> CONFLICT (content): Merge conflict in .gitignore
```

The whole "difference" is 9 comment lines `#79` adds above
`docs/SOURCE-BUNDLE.md`, next to lines the branch edits. It is trivial, but a
resolver who sees a `.gitignore` conflict and reaches for "take theirs" would
drop `#79`'s explanation of why the 13.5 MB generated bundle stopped being
tracked. Keep `#79`'s.

### Files that auto-merge, and why that is still fine

Everything else in the branch auto-merges, so the merge *looks* small: the
merged tree differs from `#79` by only 223 insertions across 21 files. Do not
read that as "harmless". `git merge-tree` is a line-level tool; it cannot tell
that the branch's `ci.yml` is an older *rewrite of the same lines*, so on this
branch the conflicts and the auto-merges are all the same anti-pattern -
bringing an old copy of a file on top of a newer one.

---

## Not established

- The exact figure **153** for the fake-skip sites. My own line-regex count over
  the committed revision is **141** (`3de8b7d5`'s own is an AST sweep, and I did
  not reproduce its pattern). 141 is a floor; 153 is unverified by me either way.
- The pre-fix count of **10** invoke-grant errors in `check_invoke_grants.py`. I
  confirmed it is 0 today; I did not rebuild the pre-fix tree to count the 10.
- Whether `test_blend_voices.py` reads "122 passed; 9 fail on the previous file"
  as the commit claims. I did not run that suite; `jarvis_voices.py` is
  byte-identical in both refs, so the claim is not load-bearing for the verdict.
- Whether the four **Windows-runner** claims in `ci.yml`'s comment blocks (runs
  37349552106, 37360119210, 37369387182) hold. Those runs are GitHub-side
  evidence I did not fetch; they also live in `main`'s copy, and are outside
  this review's question.
- I did not attempt to prove that no *other* branch in this repo duplicates this
  one. Only `audit-pass-2026-10-05` was reviewed.
