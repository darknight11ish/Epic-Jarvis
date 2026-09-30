# Report 05 (audit), agent ad1de788, 2026-09-29T08:44Z

> **What it was asked** (first 600 characters of the task): Repo /home/user/Epic-Jarvis at origin/main (79a36545). Read CLAUDE.md fully first (it has the rules and owner decisions), then docs/ARCHITECTURE.md (esp. §4, §8 'One-sided on purpose'), docs/JARVIS-API.md headings. Do NOT edit files. Run the owner's standing three-part audit as a COHESIVENESS check over the features that landed together in the last few days on main: QR-code pairing + per-device keys (docs/PAIRING-DESIGN.md, JARVIS-API §90), the chatbot driver (adapters, compare, support chats, money limit), the plan card (jarvis_plan / propose_plan, switched off), phone notifications, Jarvis L

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

# Cohesion audit of main at 79a36545 (QR pairing/per-device keys, chatbot driver, plan card, phone notifications, Live, screen, Forget-a-time-frame, third card, Models cache, Goals, talk-to-type, projects, apps in projects)

## Headline
No hard conflicts turned up. I found no duplicate gate action, route, setting or card title. There is only one scheduler. The Lockdown, App lock, Stop everything, per-device key and read-aloud rules held wherever I traced them. What I did find is one real data-loss gap (Goals are left out of backups), one unfinished link between Projects and Goals, and a cluster of stale docs. All are plain fixes except two owner-call items (F3, F5).

Files were not edited. Two things were touched by my own commands and undone: `git checkout docs/SOURCE-BUNDLE.md`, because `gen_source_bundle.py` has no `--check` and rewrote it; and a throwaway venv in the scratchpad, made to fix this container's broken `cryptography` package. The working tree was briefly showing edits to `brain.js` and `projects-panel.js` that did not come from me. They are gone now, and `git status` is clean.

## What I ran
- `python3 tools/check_parity.py`. Clean: "No undecided drift". Every phone-only route has a reason, and I confirmed the reasons in ARCHITECTURE §8 for pair/*, approval-key, approve/challenge, chatbot/handoff/*, notifications/phone, notifications/watch.
- `--check` on the `tools/gen_*_cases.py` fixtures. All that support it pass, except six that need `numpy`, or a native library this container lacks (`gen_forget_range`, `gen_history`, `gen_memory_words`, `gen_phone_voice`, `gen_voice_status`, `gen_voice_training`). Those I could not run here. `gen_palette` and `gen_source_bundle` have no `--check`. They run as a write, and the palette came out identical. `build_patch_history --check` is up to date. `gen_notices --check` is up to date.
- The backend test suite (`backend/test_*.py`), using a venv with a working `cryptography`. Everything passes except tests that need the owner's own files, which are not in the repo (`jarvis_hud.py`, `jarvis_gate.py`, `jarvis_memory.py`, `jarvis_events.py`, `jarvis_models.py`). That covers `test_documents_honesty`, `test_events_pump`, `test_extraction_wiring`, `test_gate_egress`, `test_memory_pane`, `test_memory_prefix`, `test_voice_503`, and the "No module named jarvis_x" failures. These are environment failures, not code bugs. CI is where they run.
- `tools/check_command_acl.py`. Clean (269 commands agree).
- `tools/shader_size.py --check`. All shaders are under the limit.
- Rust: `cargo fmt --check` and `cargo clippy --target x86_64-pc-windows-msvc --all-targets -D warnings`. Both clean.
- I started the desktop `node tests/*.mjs` suite but killed it. Playwright tests hang here (no Chromium), so I did not get a result. Kotlin and Android I only read.

## Findings, worst first

### F1 (medium, plain fix): Goals are not in the locked backup, so a restore can leave an unremovable orphan
- **Evidence.**
  - `backend/jarvis_backup.py:212` has `SOURCE_DBS = ("memory.db", "chat-history.db", "schedule.db", "feedback.db", "projects.db")`, described as "The real databases this backend has today".
  - `backend/jarvis_goals.py:140` keeps goals in `goals.db`, which is not on that list.
  - `jarvis_data_health.py` (the preflight) also checks memory, chat-history and projects, but not goals.
  - `projects.db` was added by the same kind of audit on 2026-09-28. Goals (2026-09-27) was missed then.
- **What goes wrong.** A restore brings back `schedule.db`, including a "goal_checkin" job. That job's text is the goal's own words. But `goals.db` is not restored, so no goal owns the job any more. The apps then give it no Pause or Delete: `Schedule.actionsOf` in `net/Schedule.kt:618` returns an empty list for `goal_checkin`, and CLAUDE.md says "Stop tracking, on the goal" is the only way to remove it. So the owner sees a weekly check-in they cannot delete from either app.
- **Plain words.** The backup saves the reminders list but forgets the Goals list. After a restore you get "ghost" check-ins that nothing can turn off.
- **Fix.**
  - Add `goals.db` to `SOURCE_DBS`.
  - Add it to the preflight's data-health check.
  - Add a test that fails when a `jarvis_*.py` opens a new `*.db` that is not on the backup list. That would catch the third one.
  - Also decide whether an orphan check-in should be deletable in Coming up.

### F2 (medium-low, plain fix): Projects still keeps a private list of goal ids that no screen can use
- **Evidence.**
  - CLAUDE.md says a project has goals "built on the Goals feature ... not a second goals system".
  - `backend/jarvis_projects.py:38-44` still says "jarvis_goals.py exists only on the continuation branch" and stores raw ids "not checked against goals.db".
  - `docs/JARVIS-API.md:13742-13756` says the same, and "Numbered 61: ... 60 the chatbot driver". Both are wrong now: §60 is the plan card, §61 is phone notifications, and Goals is on main.
  - Grep for "goals" in `Projects.kt`, `ProjectsPlate.kt`, `projects-panel.js` and `brain/projects.rs` finds nothing. Neither app can set or show a project's goals.
  - `jarvis_goals.py` has no `project` column or filter.
- **Plain words.** Both features are built, but the link between them is not, and the docs still say the other half is on another branch.
- **Fix.** Either build the link (project column, `GET /api/goals?project=`, a "Goals" line in the project view on both apps), or write down that it is deferred and update §88.
- **Owner's call?** Only the "when". The decision to build it on Goals is already written.

### F3 (medium, owner's call to confirm): Goals check-in no longer asks a card, but CLAUDE.md, the README and the script comment still say it does
- **Evidence.**
  - CLAUDE.md (Goals entry, near line 1020) says accepting raises "the same ONE `schedule_repeat` card".
  - `backend/README.md`'s `goals.patch` row and the `scripts/apply-patches.ps1:971` comment say the same.
  - The code says the opposite: `jarvis_goals.py:414` `KIND_OPTIONS ... plain_repeat=True` ("with NO card (the owner, 2026-09-28)"). JARVIS-API §59 and ARCHITECTURE line ~1446 also say "no card".
- **Why it matters.** The owner's written no-card list (2026-09-26 approvals audit) names only plain reminders, alarms and the standby schedule, and says the briefing and "tell me when" keep their card. I could not find the "2026-09-28" owner decision anywhere in CLAUDE.md. It may be a fair extension, since the check-in reads nothing and acts on nothing. But it should be recorded, not implied.
- **Fix.** Add one line to CLAUDE.md recording (or reversing) the no-card decision, and correct the README row and the script comment.

### F4 (low-medium, plain fix): the "What asks first" page says it lists every action, but no-card features have no rows
- **Evidence.**
  - The page docstring at `backend/jarvis_asks_first.py:1-2` says "every action Jarvis can take".
  - The rows exist for Live, Solve it here, Projects and app tasks, plus timers and repeats.
  - There is no row for Goals (draft, accept and its weekly check-in, tick, stop). Grep "goal" in `jarvis_asks_first.py` finds nothing.
  - There is none for Today cards, "Between us", "remind me next time", "ring my phone", history import or photo-to-reminder either. Focus is also absent.
  - The existing review comment says starting Live got a row because the page promises every action.
  - `fixed:repeats` (line 393) names only "repeating reminder or alarm, or the standby schedule".
- **Fix.** Add one plain "no card" row each, at least for Goals and its check-in, since that one is new. No test currently catches a missing row for a no-card action.

### F5 (low, owner's call): four separate "plan" mechanisms
- **Evidence.** The plan card `propose_plan` (gate `run_plan`), `jarvis_ui_control_plan`, `jarvis_android_control_plan` and `jarvis_research_plan` all exist. The maps are in `plan-gate.patch:30` and `ui-control-wiring.patch:32`. Each has its own card wording and risk logic.
- **Why it is only low.** The plan card is switched off, and all four go through the one gate. The wiring test `test_agent_plan_wiring.py` shows the plan card's steps get the real per-tool gate check.
- **Why the owner should know.** CLAUDE.md's "ONE scheduler" and "one permission model" spirit says to consider merging them later. It is not urgent.

### F6 (low, plain fix): stale internal references in docs and status pages
- `docs/JARVIS-API.md:13733-13742` and `:13740`, `:13872` say "see 61.6", "(61.4)" and "Numbered 61". Those sections are §88.x now.
- `.claude/agents/JARVIS-TODAY.md:195-200` lists "QR pairing with per-device keys" and the plan card as "not built". Both are built (§90, §91, `propose_plan`). It also lists the third card, Goals and phone notifications as "on other branches, not merged", but they are on main now.
- `backend/README.md` has no row for `plan-gate.patch`, `jarvis_plan.py` or `jarvis_phone_notifications.py`. `phone-notifications.patch` appears only in passing, inside the `brain-reads.patch` row. All of them are copied and applied by `scripts/apply-patches.ps1`, so nothing is broken, only undocumented.
- `docs/SOURCE-BUNDLE.md` is about 4,000 lines behind the tree (missing `SignedApproval.kt`, `ApprovalKey.kt`, `AppSection.kt`, `TaskDiffScreen.kt` and others). It is not enforced by CI. `docs/JARVIS-API.md` §62 is honest that screen viewing is backend-only.
- Trivial wording drift: desktop `goals.js` says "Say what you want to get done, below." and the phone's `Goals.kt` says "...get done below." (comma). Goals has no shared fixture.
- `backend/patch-history` skipped a corrupt old `wellbeing.patch` version. That is harmless, since it says it could never have applied.

## Part 2, both apps: PASS
- `check_parity.py` is clean.
- The one-sided items are all written in ARCHITECTURE §8 (pairing start/claim/collect, signed approvals, handoff, phone notifications, watch notifications, talk-to-type, screen keys).
- Screen viewing ("Look at this") and Kokoro v1.0 are correctly not built, and the docs say so. Inbox tidy is designed but not built.
- The PC-only App-lock, hidden-lists and Lockdown behaviour is present in both apps for Goals, Projects, Forget-range, Support and the Chatbot plate.
- The Alt+Shift+S "Look at this" plan does not clash with the current "Attach a screen capture" key. `SCREEN-DESIGN.md:20` explicitly says it is renamed, not doubled.

## Part 3, fit: PASS with F1-F4
- **One scheduler.** Only `jarvis_schedule` runs a loop for repeat jobs. Kinds are added with `register_kind` (briefing, focus, next-time, tidy, today, goal, tellme, standby). Live and Screen have their own tick loops for their sessions (a running session, not scheduled jobs). Forget-range uses a `threading.Timer` for its 10-minute Undo, held in memory. Neither is a second scheduler.
- **Gate actions.** No duplicates across patches except the expected layered `schedule_repeat` edits. `HARD_LIMITS` and `MUST_ASK` include every new action (`second_card_third_assign`, `chatbot_session`, `support_chat`, `support_offer`, `memory_forget_range`, `pair_device`, `unretire_shared_key`, `register_approval_key`, `run_plan`, `phone_notifications_read`, `app_merge_change`). `test_card_words`, `test_asks_first`, `test_reach` and `test_gate_risk_words` pass (`test_card_words`: 108 passed).
- **Risky rule.** The phone, desktop and backend risky-approval rules match, driven by `tools/gen_risky_approval_cases.py`.
- **Approval cards.**
  - Notification and widget can only Deny.
  - Signed approvals only apply to risky cards from another device.
  - The QR-pairing, approval-key and unretire cards need Windows Hello and the PC (`PC_ONLY_ACTIONS`).
- **Lockdown.**
  - It covers the driver (run-time checks, `stop_for_lockdown`) and support chats (they reuse the driver), plus the online weather and cloud models. The local second AI is deliberately exempt (kind `local`). The ntfy push gap is written down.
  - No newly added way out is missing from it. The one open gap is the ntfy push (`docs/JARVIS-API.md` §75.2 "Not covered", owner's `jarvis_gate.py`).
- **Read-aloud.** Chatbot, support and compare answers are "never read aloud" in the docs. Screen and camera are a named exception. Nothing conflicts.
- **Crisis handling.** It was checked in the driver, support, Live and next-time code paths. Goals and Projects hold owner-typed lists, not chat turns, so the crisis-turn rule does not apply to them.
- **Stop everything.** Focus, Live and Screen register with `jarvis_stop_all`. The chatbot driver stops through `jarvis_task_control` and `_stopped_since`. Talk-to-type stops with it.
- **The phone's Solve-it-here screen** holds input on a stale link (rule 4).
- **Claims match code.**
  - Money limit and Compare caps: 3 chatbots on one card, 4 on two (`MAX_AIS`).
  - Screen 30/120 minutes.
  - Forget-range Undo 600 s.
  - 10 open app tasks.
  - `FACE_VOICE_DEFAULT = False`; the otter uses speaker "3" ("Sky" is not used).
- **JARVIS-API routes vs code.** They match (I checked `import_chats`, the projects app routes and the pairing routes). The section numbers 66-69 and 76 are simply unused, and nothing references them.

## Checked and fine
Parity tool; fixtures (`gen_*_cases --check` where supported); no duplicate gate/route/settings-file/toml section; one scheduler; Lockdown coverage; per-device key and signed-approval flow (§90-§91) against ARCHITECTURE §3; PC-only actions; risky-rule agreement; App lock and hidden lists on the new plates; Stop everything registrations; the third card lane routing (`lane_for` handles `third_feature`); patches all copied by `apply-patches.ps1`; every `jarvis_*.py` copied by the script; Rust fmt and clippy on the Windows target; backend tests (aside from files not in the repo).

## Only read, not run
The Kotlin, the desktop UI tests (hung without Chromium), the fixtures that need `numpy`, and anything Windows-only.

## Owner's call
F3 (record or reverse the Goals no-card decision) and F5 (whether to consolidate the plan mechanisms later). F1, F2, F4 and F6 are plain fixes. For F2, only the timing of building the link is the owner's.
