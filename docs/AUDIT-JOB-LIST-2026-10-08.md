# Audit: the job list (2026-10-08)

Standing instruction (`CLAUDE.md`, "Every new feature gets its own audit,
without being asked"): a feature lands with its own audit. This is that audit
for the job list - `backend/jarvis_tasks.py`, its patch, and both apps'
surfaces (JARVIS-API section 118). It covers the three things the instruction
names: bugs in the new code, both apps, and fit with what is already there.

Read-only. Nothing in this document changes code; every fix it names was made
before it was written, and each one has a test that holds it.

## 1. Bugs

**Seven real defects were found. All seven are fixed, and each has a test.**
The last four are the ones this audit is for - found by testing the feature
against something real rather than against itself.

| # | What was wrong | How it showed | Fixed by |
|---|---|---|---|
| 1 | A `running` job whose `lease_until` was left at 0 by a crash was never recovered - `tick()` skipped it, because "no lease" read as "not my business" | `test_tasks.py`, first run | the recovery path treats a missing or past lease with `running` as a dead process |
| 2 | Run receipts were opened at every claim and never closed, so the activity list showed jobs that "finished" by dying | `test_tasks.py`, first run | one tick is one run: `_end_run()` closes it on every way out |
| 3 | The lease was held across steps, so a three-step job took three minutes (one lease each) instead of three ticks | `test_tasks.py`, first run | the lease is given back at each checkpoint, through the same compare-and-set |
| 4 | `gate_ask()` passed the gate's `outcome` word straight through, so `allowed=False` with a word like "approved" would have been **logged and displayed as a run** | `test_tasks.py` | `allowed` now outranks the word; a refusal can never read as approval |
| 5 | `status()` sent the question only for a job `blocked` by an interrupted step, so a job that stopped to ask arrived as "needs an answer" **with nothing to answer** | the phone plate's own test | both states that need the owner carry it, and nothing else does |
| 6 | The desktop heading and counts were **invisible**: `rows()` clears the container before painting, and the heading was appended before that call, so it was silently wiped | the DOM half of `tests/job-list.mjs` - which had never run, because Playwright was absent until it was run against today's `main` | the heading goes in after `rows()` (and on both early-return paths) |
| 7 | **`tasks.patch` did not apply to the real `jarvis_hud.py`** - it passed the `_skeleton` stand-in rehearsal, then failed against the real file because a later patch (`note-capture.patch`) had inserted a route between the lines the stand-in laid side by side | rehearsing against `jarvis-backend/jarvis_hud.py` | the patch is now **generated from the real file** (`tools/gen_tasks_patch.py`), and `test_tasks.py` rehearses it against that same real file: apply, reverse, byte for byte |

**Number 7 is the important one.** It is the exact failure mode
`backend/_skeleton.py` warns about in its own docstring ("What it cannot say:
whether the rest of the real file matches, or whether another patch applied
between them changed those lines"). Until 2026-10-08 there was no way to check,
because the Python program lived only on the owner's PC. `jarvis-backend/` is
now a copy of that program in this repository, so the weak rehearsal was
replaced rather than kept alongside a stronger one. The weak one would have
gone on passing for ever.

## 2. Both apps

- **Desktop**: Brain -> Work, under the Long Fuse jobs (`brain/routes.rs`,
  `brain_task_act`, `allow-brain-task-act` in the `brain-act` set,
  `renderTaskList()` in `brain.js`, plus the answer box).
- **Phone**: Brain -> Work -> jobs, in an item of its own so the list shows
  when there are no Long Fuse jobs (`net/Tasks.kt`, `JarvisRuntime`,
  `TasksPlate.kt`, plus the answer box), guarded by the same
  `brain.work.jobs` menu entry.
- **`tools/check_parity.py` is clean**, and all three routes are `ported`
  rather than left unclassified: `/api/tasks`, `/api/tasks/act`,
  `/api/tasks/input`. Nothing here is one-sided, so `ARCHITECTURE.md` §8 needs
  no entry.
- The Kotlin is **not compiled in this checkout** (no Gradle or Android SDK),
  so the phone half is CI's. The desktop half now genuinely runs here,
  including the DOM checks.

## 3. Fit with what is already there

**The same permission model.** Every step of every job goes through the one
gate, and there is no second path: the job list never imports `jarvis_gate`, and
`test_tasks.py` asserts that. The only place the two meet is `gate_ask()`, which
hands the step to the gate that already exists and reports what came back;
`allowed is True` is the only thing that lets a step run. Resume and Retry
**re-queue** and approve nothing; Pause and Cancel are immediate. A test asserts
that no steering route touches the gate, `owner_check` or `approved=True`.

**The same shapes.** No new setting, no new card kind, no new menu entry - the
job list rides the "Background jobs" entry both apps already have. Its wording
follows the house style ("needs you", "step 2 of 3"), and its failure sentences
match `TaskControl`'s and `PcHelp`'s.

**Is it a duplicate of the Long Fuse jobs?** This was the one real fit
question, and it is worth writing down because the two are easy to confuse:
`/api/jobs` (`jarvis_jobs.py`, "Long Fuse") is work the *desktop* runs, one job
per intention, with a frozen capability set; `/api/tasks` is the durable queue
this feature adds, where the steps are enumerated up front, each step raises its
own approval card, and the list survives a restart. They are different things
with similar names, which is exactly why both apps put them in **one card,
under one heading pair** - `renderJobs()` paints the Long Fuse rows and then
appends the job list - and why section 118 says so plainly. Not a duplicate; a
naming hazard, handled by putting them side by side rather than apart.

**Docs updated**: `JARVIS-API.md` §118 (with the real-file rehearsal recorded),
`CHANGELOG.md`, `docs/README.md`, `CLAUDE.md`'s decision record, and the
published base (`jarvis-backend/`, which the repo's own claim D06 checks).

**What was removed rather than carried**: the plugin catalogue. It was part of
the plug-and-play work on the branch this started from, and it does not exist on
`main` - so the entries the generator used to write are gone, and the patch and
module are registered in `apply-patches.ps1` alone. Nothing is lost: that is
what `main` looks like now.

## 4. What this audit did NOT verify

Said plainly, because the project's rule is that nothing is claimed that is not
true:

- **No real device has ever drawn these screens.** The Kotlin is
  uncompiled here; the desktop DOM is now exercised, the phone's is not.
- **No live backend has run this code.** `jarvis-backend/` is a copy of the
  program, not the owner's running PC with its own databases and settings.
- **`apply-patches.ps1` has not been run end to end** against the owner's real
  backend folder - the rehearsal proves the patch matches the file this
  repository holds, which is the strongest check available here and not the
  same thing as installing it.
- **The plan card is still switched off.** The split is built and tested
  (`from_plan`, `gate_ask`), but nothing enqueues a job from a turn until that
  card's measured safety test passes and the owner turns it on. The job list
  today is reachable and steerable; it is not yet fed.
- **`waiting_input` has no producer.** The wire carries the question and both
  apps draw the box and send the answer, but no job stops to ask yet - that
  arrives with the form-filling work.
