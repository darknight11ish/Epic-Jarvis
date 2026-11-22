# PM5 — the production executor: an in-process scheduler tick owned by the Rust HUD

**STATUS: NEXT BUILD - NOT STARTED.** Nothing in this document is built. There
is no tick loop, no tick route, no Run Step dispatch and no new state on disk;
no code, route, card, permission or behaviour changed on `main` for it. This is
the design Gemini's ruling 6 (2026-11-21) asked for, written down before any of
it is built so the build has a contract to meet and the next audit has
something to check it against.

**The record.** The decision itself is a `decisions.d/` fragment:
`2026-11-21-pm5-executor-is-a-hud-owned-tick.md`. Where this note and the
fragment disagree, the fragment is the decision and this note is the design.

## 1. The ruling, in one paragraph

**PM5's production executor is an in-process scheduler tick owned by the Rust
HUD, backed by persistent state on disk so steps survive app restarts.**
(Concretely: the thing that decides *when* the next step runs is a timer inside
the always-running desktop process — the Tauri app that owns the HUD window and
the tray — not a Windows scheduled task, not a separate service, and not a
second scheduler inside the Python backend. The thing that decides *how* one
step runs is the existing `jarvis_tasks.JobList.tick()`, reused as it is.)

## 2. What this replaces

PM3 (2026-11-20) built the plan store's link to `jarvis_tasks.py` and deferred
the Run Step dispatch, on evidence: `JobList.tick()` had **no production
caller** and **no background step executor** — its own "WHO TICKS IT" audit in
`backend/jarvis_tasks.py`, and `docs/ARCHITECTURE.md` §8 and §10 say so — and
wiring it with a stand-in runner would move rows while nothing ran. That is
recorded in `docs/DECISIONS.md` ("the Run Step dispatch is deliberately
deferred", 2026-11-20) and in `docs/JARVIS-API.md` §88.9.

**This ruling defines the missing executor, so the "no executor is defined"
state is superseded:** the blocker is no longer "there is no honest background
executor to hand `tick()`". There now is a decided shape for one — this note.
What is still not built is the executor itself and the dispatch that enqueues a
job from a work item; both are PM5's build, and the audit trail said so before
anything was written.

## 3. Why the Rust HUD owns the clock

Four reasons, and each is a property of the desktop process rather than of the
Python backend:

1. **The HUD is the always-on local orchestrator.** The desktop app is what
   starts with Windows and stays in the notification area; `jarvis-desktop/README.md`'s
   own words: *"Started by Windows at login, or by a notification's Deny
   button, the HUD is built but stays hidden until you open it from the tray
   (`build_hud_window` in `src-tauri/src/lib.rs`)"*. Its Rust side already runs
   an always-on loop that makes backend calls whether or not a window is open
   (`spawn_telemetry_loop`, `TELEMETRY_INTERVAL` in `lib.rs`), so an in-process
   tick is not a new kind of resident thing — it is the same pattern the house
   already keeps.
2. **Immediate cancellation.** Stop is never gated and must be immediate:
   `request_stop()` in `jarvis_tasks.py` sets a flag and the next `guard()`
   raises, and `Pause`/`Cancel` through `POST /api/tasks/act` are already
   immediate (`JARVIS-API.md` §118.2-118.3). When the timer lives in the same
   process as the button, cancelling does not wait for another scheduler's
   cycle, a service manager, or an OS task to wake up — the loop asks for the
   stop before its next tick and stops scheduling.
3. **Live progress streaming to phone clients.** The phone already reads job
   state through `GET /api/tasks` and step events through the one existing
   `GET /api/events` stream; the desktop's Rust side already holds the pairing
   token and makes the backend calls itself (`hud_proxy.rs`, `commands.rs`).
   A tick driven and reported by that same process can publish each step's
   progress on the shapes both apps already parse, with no new channel and no
   new thing for the phone to learn.
4. **No OS task-scheduler overhead.** No Windows Task Scheduler entry, no
   registered task, no separate Windows service, no install-time permission
   and no elevation; nothing to configure, and nothing that keeps running after
   the owner quits the app. The tick lives and dies with the HUD, which is the
   lifetime the owner already knows.

## 4. One tick, end to end

This is the shape the build must keep. The exact names of the new route and
the interval are not frozen here (see §7); the order and the owners are.

1. **The Rust HUD owns a timer.** A loop in `jarvis-desktop/src-tauri` wakes on
   its own interval while the app is running (the `spawn_telemetry_loop`
   pattern: `tauri::async_runtime::spawn`, no thread of its own, no window
   required). The interval is short enough that a due step is not late by a
   noticeable amount, and it is the HUD's choice, not the job's.
2. **It calls the backend's tick door.** One loopback call, with the token the
   Rust side already holds (never from a webview — the HUD page holds no
   token), asking the backend to work the job list a little. This is a new
   small door on the existing `/api/tasks` contract, or the existing read's
   first-call `boot_once()` recovery extended with it; the build names it and
   `docs/JARVIS-API.md` §118.3 freezes it.
3. **`jarvis_tasks.JobList.tick()` does the work.** Unchanged: at most **one
   step of each of at most `MAX_IN_FLIGHT` (3) tasks**, then return. A step
   that needs its own card asks through the caller's `ask` and the task parks
   in `waiting_approval`; a finished step is checkpointed to disk before the
   next step is considered; the lease is given back at the checkpoint.
4. **The answer says what happened.** `tick()`'s report (`claimed`, `steps`,
   `waiting`, `finished`, `deferred`, `recovered`) is what the caller learns,
   and the `run_events` rows it wrote are what both apps read. No second log.
5. **The next tick is the next call.** There is no queue of timers: the HUD's
   loop wakes, calls once, and sleeps again. A tick that fails to reach the
   backend changes nothing — the state on disk still says what is true, and the
   next tick picks it up.

**What it is not.** It is not `jarvis_jobs.run_due()` (that queue runs its own
frozen handler registry whole; `jarvis_tasks` runs one step of an enumerated
job list), and it is not a second scheduler for timed things — the briefing,
timers, reminders and the overnight tidy stay kinds on the one clock
(`jarvis_schedule.register_kind`, `backend/jarvis_schedule.py`). A job that
must happen *at a time* is still enqueued by the scheduler's `on_fire`.

## 5. The invariants it must keep

These are the acceptance contract for the build; each one is either already
proved by `backend/test_tasks.py` and must be preserved, or is new and must be
proved by PM5's own tests.

1. **One step at a time per task.** A claim writes `lease_id`/`lease_until`
   through a compare-and-set, so two claimers cannot both win; one tick runs at
   most one step of a task; the lease is given back at each checkpoint so the
   next step is not delayed to the lease's end. A second tick, sequential or
   overlapping, never runs a finished step again. `MAX_IN_FLIGHT` stays 3 — the
   PC is also answering the owner, running the model on its card and listening
   for the wake word.
2. **The owner's approval cards are untouched.** Every acting step still raises
   its own card when its turn comes, through the one gate; approving a job
   never approves a step; the card is bound to the words shown (the hash
   check); a real "no" stops the job at that step and keeps the steps before
   it; a card nobody answered (`timed_out`) is **not** a no — the job returns
   to the queue and asks again. Rule 4 still holds: nothing acts while the
   event stream is stale. PM5 adds no card class and no batching.
3. **No new permission.** No new gate action, no `_RISK`/`_TOOL_ACTIONS`/
   `_NO_RULE_FROM_DENIAL` row, no new Windows Hello path, no new route exposed
   to the phone beyond the existing `/api/tasks`/`/api/events` shapes, and the
   HUD page still holds no token. The tick is the owner's own PC working the
   job list he already approved; it grants nothing.
4. **A failed step leaves honest state.** A raising step fails *that job*, never
   the tick; the state, the error and the feed say what failed. An action that
   might have left the machine is `outcome_unknown` — never `failed` (which
   invites a retry) and never `succeeded` (which would be a guess) — with words
   telling the owner to check the other side. An interrupted acting step puts
   the job in `blocked` with a question; an interrupted read-only step is done
   again. Rows never move while nothing ran.
5. **Progress reaches the phone over the existing event stream/API shape.**
   Step start/finish/waiting/failure are the existing `run_events` and the
   existing `/api/tasks` payload and `/api/events` events — no new channel, no
   new phone parser, no task title or step text added to the counted payload
   the phone already refuses to show. Live progress means the phone sees step N
   of M change while the job runs, not after it ends.
6. **Restart recovery from disk.** Two processes can restart independently, and
   both cases must be honest. The backend's first `GET /api/tasks` already runs
   `boot_once()` (startup recovery plus interrupted-run reconciliation); a
   `running` job whose lease has run out is the signature of a process that
   died mid-step and is handled by the existing `_recover_leases` / `startup()`
   rules. A HUD restart simply resumes calling; a step that was mid-flight on
   disk is judged by the same rules, never assumed done and never silently
   retried.
7. **The existing `jarvis_tasks.tick()` semantics are reused, not re-invented.**
   PM5 does not add a scheduler inside `jarvis_tasks.py`, does not change the
   order or the card rules, and does not write a second executor. The executor
   and the approver the tick needs are still supplied by its caller; PM5's job
   is to supply a real one — the same tool path a chat turn uses, lifted so it
   can run without holding a turn — not to rewrite the engine.

## 6. The acceptance tests PM5 will owe

The names are the ruling's; each one is a test that must exist and must be
able to fail. A skipped check is never a pass here, and neither is a test that
only proves the loop runs.

| Test | What it must prove |
|---|---|
| **start** | Pressing Run Step on a ready work item enqueues exactly ONE `jarvis_tasks` job (one event, no second job on a second press while it runs), and the first tick claims it and runs exactly one step; nothing runs before the tick. |
| **cancel** | Stop/Pause/`Cancel` takes effect before the next step — no wait for a cycle — and never mid-card; the job is left in the state the module's own sentence says, no further step runs, and a cancel while a step is executing ends honestly (stopped, not failed). |
| **survive-restart** | Killing the HUD mid-run and restarting it resumes from the checkpoint (a finished step is never re-run); killing the backend mid-run is recovered by `boot_once()`; an action that might have left the machine becomes `outcome_unknown`, not retried; at most one step runs after either restart. Two ticks (sequential or overlapping) still cannot run a step twice. |
| **progress** | Every finished step is on disk (checkpoint, `done`, `at`) before the next step is considered, and the event written carries the step index, tool and state the existing shapes expect. |
| **live-progress** | A phone reading `/api/events` sees step start/finish/waiting/failure while the job is running, on the existing event shape, with no new route and no new parser; a stale stream still blocks acting. |
| **phone-read** | `GET /api/tasks` shows the job's state, `step N of M` and the owner-needed cases exactly as today, and the PM3 projection on the plan read moves `in_progress` / `waiting_approval` / `in_review` as the job moves — never straight to `done`. |
| **failure-honesty** | A raising step fails that job only and the tick continues; a denied card is not a timeout; a timed-out card parks and asks again; an interrupted action is `outcome_unknown` with the check-the-other-side words; nothing reports a success that did not happen and no row moves while nothing ran. |

The existing proofs in `backend/test_tasks.py` (leases, checkpoint ordering,
outcome_unknown, memo, idempotency, shown-hash decisions) stay as they are; PM5
adds what is genuinely new — the clock, the door, the end-to-end path through
the desktop process, and the Run Step dispatch above them.

## 7. The state store is ruled: `jarvis_tasks` SQLite (Gemini 5.1, 2026-11-21)

**Where does the persistent state live, and what is its schema?**

Answered by Gemini's ruling 5.1 of 2026-11-21 22:22 PT: **Candidate A**. All
PM5 scheduler and step state lives in the **existing `jarvis_tasks` SQLite
database** — its `tasks`, `runs`, `run_events`, `actions`, `memo` and `control`
tables — **plus one `scheduler_tick` control row**. One SQLite store guarantees
atomic restart recovery, automatic `jarvis_backup.py` coverage, and zero
split-brain between the Rust HUD and the Python executor.

The facts the state has to hold, and where each one lives under the ruling:
(a) each job's steps, finished results and next step index → `tasks`/`runs`;
(b) the lease/running marker per job → the store's existing lease columns;
(c) the waiting-card and question state → `actions`/`memo` as today;
(d) the `outcome_unknown` and idempotency facts for actions → `actions`;
(e) the stop/pause flags → `control`; (f) the run history and feed →
`run_events`; and (g) whatever the tick loop itself needs to be honest across a
restart (its last tick, whether it is paused, whether it should refuse to
resume) → **the one `scheduler_tick` row in `control`**. That single row is the
whole schema change: no new table, no new database file, and no Rust-owned state
file.

Candidate B (a Rust-owned state file beside the desktop's other state) is
**rejected**: the authoritative job state stays in `tasks.db` under either
shape, so B would keep the tick's own facts in a second place and invite exactly
the drift and the two-copies-of-one-truth risk it was supposed to answer. The
HUD's tick is stateless except for its timer, and the only thing it owns on disk
is the `scheduler_tick` row it reads and writes through the store.

What the build must keep now that the store is ruled: `jarvis_tasks.tick()`
stays the only executor and the only writer of job state, the phone reads
progress through the existing API shapes only, the owner's private job words
stay inside the store rather than moving to a new plain-text file, and a restart
of either process is recovered honestly rather than replayed.

**The store question is answered, so the build may start** from Candidate A.
Anything the build finds that would need a second store, a second copy of
progress, or a schema change outside that one `control` row comes back to the
record first — building the wrong store is still how a second copy of the truth
gets made.

## 8. What this note does not do

- **It builds nothing.** No tick loop, no route, no Run Step dispatch, no
  state file, no schema. `docs/ARCHITECTURE.md` §8's "not built" list stays
  true for the *build*; what changes is that a design now exists.
- **It adds no card, no permission and no route.** No gate row, no setting, no
  switch, no `X-Jarvis-Client` change.
- **It does not define PM4's Run Step button or the plan read.** PM3's bridge
  route (`POST /api/projects/<id>/sync`, read-only) and PM4's plan read are
  unchanged; the button is PM5's build once the executor exists.
- **It does not touch the existing executor's contract.** §118 of
  `docs/JARVIS-API.md` stays the frozen contract; when the build lands it is
  extended (the tick door and the enqueue path) rather than rewritten.

## 9. What gets updated when it is built

For the next session, so nothing has to be rediscovered:

- `docs/JARVIS-API.md` — the tick door and the enqueue path in a new §118
  sub-section (or a new section if the contract is bigger than one door), with
  the frozen request/response shapes.
- `docs/ARCHITECTURE.md` — §8's "not built" row for the background executor
  and Run Step, and the plan-store section's deferred-dispatch paragraph,
  become the build record; the §8 one-sidedness row for the Run Step button
  names the phone's half or says why the desktop is the only door.
- `docs/PROJECTS-DESIGN.md` — a PM5 build note, in the same shape as PM2's,
  PM3's and PM4's.
- `backend/jarvis_tasks.py` — only if the build has to supply a new caller
  contract; its "WHO TICKS IT" docstring stops saying "no production caller"
  and says what calls it and when.
- The decisions record — §7 is answered in the record
  (`decisions.d/2026-11-21-the-22-22-rulings-are-applied.md`), and when the
  build lands this note is marked built rather than left as "next build"
  forever.
