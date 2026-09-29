# Apps in Projects: design (2026-09-29)

Status: **designed, nothing built.** For the owner's decision (`CLAUDE.md`,
2026-09-28, "The app builder's projects join Projects"): *an app is a coding
project whose tests are its benchmarks - one list, not two.* This is the app
builder's **milestone B** (`docs/APP-BUILDER-DESIGN.md`), redrawn so that its
planned separate "Apps" screen becomes the Projects screen that already exists
in both apps. Written for three builders (backend, desktop, phone) who work in
parallel against the API frozen in section 7.

File references were read in the source on 2026-09-29. **Not verified** items
are marked "Not verified" and listed again in section 10.

**In short.** A Projects "coding" project can now be a *Jarvis-built app*. Its
files live in Jarvis's own `apps/<name>/` git folder (milestone A, unchanged).
On its Projects page the owner sees the app's latest saved version and its
open tasks, reads each task's whole change, and taps **Merge** - which raises
ONE risky approval card (`app_merge_change`) showing every file and the whole
comparison - or **Discard**. Nothing runs (running commands is milestone C).
The model tools that let Jarvis write the code are a second slice (B2), waiting
on one owner answer (question 1).

---

## 0. What exists today (checked)

| Piece | What it is | Where |
|---|---|---|
| Workspace (milestone A) | App folders `<settings folder>/apps/<name>/`, each a git repo with `main`; one git worktree per task; strict `<<<FILE>>>` blocks; `plan_merge()` -> card; `run_merge()` refuses if the task or `main` moved; `discard()`. "RUNS NOTHING." | `backend/jarvis_app_workspace.py:1-53, 130-132, 226-253, 275-291, 347-386, 389-401, 404-417, 424-501` |
| Card words | Already in `jarvis_card_words.TITLES`: "add its change to one of your apps" | `jarvis_card_words.py:142-143` |
| "What asks first" | `app_merge_change` is already in `HARD_LIMITS` and the "This PC and your phone" group; **not** in `MUST_ASK` | `jarvis_asks_first.py:293, 338` (`MUST_ASK` is `:306-316`) |
| Gate lines | **None.** `app_merge_change` is in no gate table and not in `jarvis-framework.toml`; the workspace says the gate's unknown-action rule asks meanwhile | `jarvis_app_workspace.py:74-77`; `grep` of the stacked `jarvis_gate.py` (`_stack.stand_in`) finds no `app_merge`; `rebuilt/jarvis-framework.toml` has `pair_device = "ask"` at `:366` but no app line |
| Projects store | `projects.db`; kinds `coding`/`life`; one `folder` (PC only, must be on "Folders Jarvis may look in"); Shareable; benchmarks; a command benchmark is words with `"runnable": false`; logging a number to a command benchmark is refused | `backend/jarvis_projects.py:107-127, 316-331, 471-500, 625-660, 776-830, 895-925`; routes `:1651-1769`; installer `:1781-1845` |
| Projects routes and screens | `/api/projects...` (JARVIS-API §88); desktop `projects.js`, `projects-panel.js`, `brain/projects.rs` (`projects_read`, `projects_write` with a fixed action list, `ACTIONS` at `projects.rs:60-`); phone `ProjectsPlate.kt`, `net/Projects.kt`, `JarvisRuntime.projectsRead/projectsWrite` (`:5445-5468`); contract `tools/gen_projects_cases.py` | as listed |
| Highest API section | **§90** (pairing). This design is **§91** (check again at merge). | `docs/JARVIS-API.md:13328` |

Two facts that shape everything below:

- **`apps/` cannot be a project `folder`, and must stay that way.** `check_folder`
  needs the folder to be on the documents list AND not `jarvis_documents.protected()`
  (`jarvis_projects.py:316-331`). `protected()` asks `jarvis_agent._protected_path`
  (`jarvis_documents.py:279-292`), which refuses anything inside the settings
  folder (`jarvis_agent.py:284-289`) and anything under `/.openjarvis/`
  (`:236`). So `apps/<name>` would be refused even if someone typed it onto the
  list. That refusal protects the token and settings next door; this design
  does not touch it.
- **Two different words "kind".** Projects' `kind` is `coding`/`life`
  (`jarvis_projects.py:128`); the workspace's `kind` is `web`/`android`
  (`jarvis_app_workspace.py:79`). In the API the second one is called **`type`**.

---

## 1. The data model join

**Decision: the project is the record the owner sees; the app folder is its
storage. One nullable column links them.**

- `projects` gets one new column, **`app TEXT`** - the folder name under
  `apps/` (checked by `jarvis_app_workspace.check_name`, so it is always
  `^[a-z0-9][a-z0-9-]{0,39}$`). A unique index (`WHERE app IS NOT NULL`) makes
  it one project per app.
- An **app project** is `kind = "coding"`, `app = <name>`, `folder = NULL`.
  A coding project has a `folder` (the owner's own repository, read with
  `my_files`, PC only) **or** an `app` (Jarvis's own folder), **never both**.
  No conversion either way ("make a new project", the same rule as `kind`,
  `jarvis_projects.py:_update`).
- The app's type (`web`/`android`) and title stay where they are today, in
  `apps/<name>/.jarvis-app.json` (`jarvis_app_workspace.py:245-246`). One
  source of truth; the project view reads it.
- Migration follows the existing pattern for `benchmarks.auto_cleared`
  (`jarvis_projects.py:_db`, the `PRAGMA table_info` + `ALTER TABLE` block):
  a `projects.db` from before this change gains the column on first open.
  Backups (`projects.db` is already in `jarvis_backup.SOURCE_DBS`, per
  PROJECTS-DESIGN "Step 3") restore into an older shape safely for the same
  reason.

### The folder question, resolved without a second list

| Question | Answer |
|---|---|
| Must an app's folder be on "Folders Jarvis may look in"? | **No, and it is never added.** An app project has no `folder`; `check_folder` is never called for it. There is still exactly one folders list. |
| Does this weaken a PC-only rule? | No. Choosing a folder stays PC-only (`jarvis_projects.py:_update`, `PC_ONLY_FOLDER`). An app project cannot be given a folder (400: "This project's files are its app.") and a folder project cannot be given an app. |
| How does Jarvis read an app's code, then? | Not through `my_files` (which would need the protected folder). Through a new read of **`main` only**, via `git ls-tree` / `git show main:<path>` (B2, section 4) - never a path on disk, so a symlink or `..` cannot lead out. |
| Does `apps/` get in the way of the owner's own use? | The owner may open `apps/<name>` in Explorer or an editor. `run_merge` already refuses if the folder has changes not saved in git (`jarvis_app_workspace.py:490-492`), which the card path reports in plain words (section 2). |

### Create from either side; delete; one list

- **From Projects (the normal way).** `POST /api/projects` with
  `{"name": "Notes app", "kind": "coding", "app": {"type": "web"}}`.
  The backend makes a folder name from the project's name (lower-case, runs of
  other characters become one dash, at most 40, `app` if that leaves nothing,
  then `-2`, `-3`... if taken), calls `jarvis_app_workspace.create_project`,
  then inserts the row. If the insert fails (limit, duplicate name), the folder
  **this call just created** is removed; no other folder is ever removed.
  No card (an empty folder in Jarvis's own folder; nothing runs -
  `jarvis_app_workspace.py:226-230`). From either app's API; the screens use the
  desktop (section 5).
- **From the app side (an app folder with no project).** An app folder can exist
  with no project: created by an earlier build, or its project was deleted.
  `GET /api/projects` lists these as `unlinked_apps`. Adopt one with
  `POST /api/projects {"kind": "coding", "app": {"adopt": "notes"}}` (name
  defaults to the app's title). Only a name that `list_projects()` reports
  (`jarvis_app_workspace.py:213-223`) and no project uses can be adopted.
  There is **no separate app list and no "Apps" screen**: an unlinked app is
  an offer inside Projects.
- **From chat (B2).** The model tool creates project and app together, through
  the same function.
- **Delete.** `POST /api/projects/<id>/delete` on an app project removes the
  record and its benchmarks, as today (`jarvis_projects.py:_delete`), **never
  the folder**. The answer carries `"app_kept": "<name>"`, the confirm wording
  says the files stay and can be added back, and the app appears under
  `unlinked_apps`. A merge card waiting for that project is withdrawn. Deleting
  an app's files is **not built**: it would be an irreversible delete of the
  owner's work and needs its own card (nothing is lost by waiting; the owner can
  delete the folder in Explorer).

---

## 2. Tasks and the merge card, inside a project

### 2.1 The rules

| Action | Card? | Who | Why |
|---|---|---|---|
| Create / adopt an app project | none | either app's API | Empty folder in Jarvis's own folder; nothing runs |
| Start a task | none | either app's API (screens: desktop) | An empty separate copy; nothing runs (`jarvis_app_workspace.py:275-291`) |
| Paste a change into a task (`<<<FILE>>>` blocks) | none | **PC only** (403 `pc_only`) | Lands only in the task's copy; a paste of code is "deep editing", which stays off the phone (CLAUDE.md standing rule); the owner decides at the merge |
| **Merge** a task into the app | **one card, `app_merge_change`, every time** | **either app**, approved on either | See 2.2 |
| Discard a task | none (the apps ask "are you sure?") | either app | Nothing reached `main`; a proposal is thrown away |

### 2.2 The gate action `app_merge_change`

**Tier `ask`, risky, decided on either device. Decision and reasons:**

- **Risky** = reversible `"no"` in the gate's risk table. `jarvis_owner_check.is_risky`
  says a card is risky when `reversible == "no"` or `reach == "outbound"` or
  it was raised (`jarvis_owner_check.py:147-169`); so this card asks **Windows
  Hello on the PC and the screen lock on the phone**, and "no lock, no risky
  approval" applies (`ARCHITECTURE.md` section 3, the 2026-09-25 decision).
  Honest reason for `"no"`: git keeps the old version, but **Jarvis has no Undo
  for a merge yet**, and the merged files become the code milestone C will
  build and run on the PC. Reach is `"local"`: nothing leaves the PC.
  If a later milestone adds a one-tap "put the app back to before this change"
  (a `git revert` on `main`), this entry can become `"yes"`; not now.
- **Not PC-only.** `pair_device` and the loosening cards are PC-only because
  they widen who or what may reach the PC (`jarvis_owner_check.py:PC_ONLY_ACTIONS`).
  A merge widens nothing: it only writes text files into a folder, and the
  owner sees the whole change first. The Projects design already lists "Approve a
  change card: PC yes, phone yes, full diff shown" (`PROJECTS-DESIGN.md` section 6).
  That row was never asked of the owner, so it is **open question 2**;
  the default here is both.
- **A "heavy" card.** The notice builder sets `weight: "heavy"` for
  `reversible == "no"` (`approval-notice.patch:64,78`), so the desktop
  widget's Approve opens the Jarvis bar instead of approving (`widget.js:955-`,
  `HEAVY_APPROVE_TITLE`) - right for a long diff. Not verified: that the
  phone's own widget and notification path treat this card the same way
  (`ApprovalWidget.kt`); a phone test must prove it (section 6).
- **Gate patch lines** (a new `backend/apps-in-projects.patch`, section 7):
  1. the risk table: `"app_merge_change": ("no", "local", "adds the change shown on the card to your app's files, exactly as shown; nothing is run; the older version stays in the app's git history, but there is no Undo button for it yet")` (same shape as `pair_device`, `devices.patch`);
  2. `_NO_RULE_FROM_DENIAL`: `"app_merge_change"` - a "no" must never become a
     standing rule (`devices.patch` does the same for `pair_device`);
  3. (B2 only) `_TOOL_ACTIONS`: `"app_propose_change": "app_merge_change"`, `"app_read": "auto"`.
- **Tier lines:** `app_merge_change = "ask"` in `rebuilt/jarvis-framework.toml`
  beside `pair_device` (`:366`), with the "must stay ask" comment; and add
  `"app_merge_change"` to `MUST_ASK` (`jarvis_asks_first.py:306`), because the
  new module, like `jarvis_projects.request_shareable`, refuses any tier but
  `ask` (`jarvis_projects.py:1454-1458`). It stays in `HARD_LIMITS`, where it
  already is (`:293`), so no app can loosen it.
- **Card words.** Title: the existing `TITLES` line. Body: exactly
  `jarvis_app_workspace.describe(plan)` (`:462-473`) - every changed file with
  `(+added -removed)`, "Nothing is run: this only changes the app's files.
  Saying no keeps the change aside, and your app stays as it is.", then the
  **whole** diff. A change over `MAX_CARD_DIFF_CHARS = 60_000`
  (`:86, 456-458`) is refused with "ask Jarvis to split it into smaller steps"
  and **no card is raised** (a card nobody can read is not a decision).
  One small edit to the workspace: a task remembers its `source`
  (`"jarvis"` or `"pasted"`), and for a pasted one `describe` adds the line
  "You pasted this change in on your PC." so the card never claims Jarvis
  wrote what the owner typed.
- **Detail sent to the gate:** `{"text": describe(plan), "what": "add one change to your app", "project": <project name>, "app": <folder name>, "files": n, "leaves_this_pc": False}` - the same key names `jarvis_projects._decide` uses (`:1400-1404`). The audit log gets counts only, already true (`plan.detail()`,
  `_audit`, `jarvis_app_workspace.py:437-440`).
- **Not verified:** that the owner's real `jarvis_gate.pending()` keeps a
  60,000-character `prompt`/`detail` whole on the queue row. The stack stand-in
  only shows `prompt[:500]` for the push doorbell (audit event, stand-in line 19),
  which is a notification, not the card. The builder must check with one
  PowerShell line on the PC (a merge of a large test task) before the owner
  relies on "the whole diff"; if the row cuts it, lower `MAX_CARD_DIFF_CHARS`
  to what fits rather than cut silently.

### 2.3 The merge flow (module `jarvis_apps.py`, section 7)

`POST .../app/tasks/<task>/merge`:

1. Resolve project -> app; 404 if not an app project or no such task.
2. **One card per app at a time** (keyed by app name, like Shareable's
   `_P_STATE`): a second request answers 409 "A card for this app is already
   waiting - answer it first." Also blocks paste and discard-with-card races.
3. `plan = plan_merge(app, task)`. If `plan.refused` -> **400 with that
   sentence, no card** ("this task has not changed anything yet", "too big to
   show on one card...", "that task is gone...").
4. Check `tier_of("app_merge_change") == "ask"` else 503 (as
   `jarvis_projects.py:1454-1458`).
5. Answer **202** `{"ok": true, "waiting": true, "message": ...}`; a thread
   raises the card through the gate with `describe(plan)`.
6. After the answer: reuse `jarvis_projects._person_said_yes` (one
   implementation of "a person, at tier ask, said yes" - `:1373-1379`). Only
   then, holding the module's switch lock, check the card was not withdrawn and
   call `run_merge(plan, approved=True)`. `run_merge` itself refuses if the task
   branch or `main` moved (`:485-489`), if the app folder has unsaved changes
   (`:490-492`), and on a conflict (`:493-499`); each becomes an outcome word.
7. The outcome is kept in memory as `merge.last` (like `shareable_last`):
   `merged`, `denied`, `timed_out`, `stale`, `unsaved`, `conflict`, `refused`,
   `withdrawn`, `failed`, each with a fixed plain sentence (table in 7.3).
   Nothing about what the card contained is kept.

Discard while a card waits withdraws it (same lock). **Stale link (rule 4):**
both apps hold Merge, Paste, Start task and Discard while the event stream is
stale (the clients enforce this today for Projects: `projects.rs` `held_on_stale`,
`Projects.heldOnStale`); the backend cannot know the stream's state, so this
is a client rule, tested in both apps.

---

## 3. "Tests are its benchmarks": now and later

**Built now (nearly nothing new - on purpose):**

- An app project may have the two kinds of benchmark it can already have:
  a **number** benchmark the owner logs by hand ("tests passing", "bundle size
  KB"; `add_benchmark` allows numbers on any project, `log` accepts them,
  `jarvis_projects.py:776-830, 895-925`) and a **command** benchmark kept as
  **words only**, `"runnable": false`, PC only to write
  (`:797-800`, `NOT_RUNNABLE`). No change to `jarvis_projects` benchmark code,
  the "better or worse" text, the chart, or the sensitive marking.
- The app plate shows, beside the benchmarks, the app's **current version**
  (short commit, subject, date) so a hand-logged number can be tied to a
  version by eye. Derived when read; not stored.
- The screen says, in one line under a command benchmark of an app project:
  "Jarvis cannot run this yet. Run it yourself and log the number." (one
  string in the shared `words`).

**Deliberately not built now:** running any command (milestone C: a card per
command, the fence, `--ignore-scripts`, time limit), reading a number from a
run, and storing the git save point with each result (needs a nullable
`results.ref` column when C lands; adding it now would be an empty field).
Hand-typing a number into a **command** benchmark stays refused
(`jarvis_projects.py:log`: "a command's results come from running it"), so a
number Jarvis later puts in the model's context ("tests: 41 of 45") always
came from a real run. When C lands, a run records `results.ref = main's commit`
and the merge card for a task may show "last run: 41 of 45 on the version this
task started from" (idea, not designed here).

---

## 4. How Jarvis proposes work (the model tools)

**Recommendation: this build (B1) is routes + card + screens + the PC
paste-in. The model tools are B2**, built in the same design but shipped only
after the owner answers question 1. Reasons, said plainly:

- The owner's Projects answer says "Jarvis writing code comes once the 12 GB
  card is installed and measured" (`PROJECTS-DESIGN.md` "The owner's answers",
  2026-09-28), while the app-builder decision the same day says local model
  first with no such wait. The audit asked exactly this and I found no
  recorded answer (`docs/audit-2026-09-28/02-continuity.md`, F3).
- B1 is still testable and useful without a model: tasks can be filled by the
  PC paste-in route, so the card, the staleness rule, both apps' screens and
  Windows Hello / screen-lock behaviour are all exercised for real.

**B2 design (so it is ready):**

| Tool | Gate action | What it does |
|---|---|---|
| `app_read` | `auto` (reads only) | `{"project": <name>, "path"?: <file>}`. No path: lists `main`'s files (at most 200). With a path: returns that file from `main` (`git show main:<path>`, at most 16 KB, text only; refuses `.env*`, `*.jks`, `*.keystore`, `id_rsa*`-like names). Never reads a worktree or a disk path. |
| `app_propose_change` | `app_merge_change` (via `gate_lookup_name`, like `propose_plan` -> `run_plan`, `jarvis_agent.py:1378-1394`) | `{"project": <name>, "title": <short>, "changes": <text of <<<FILE p>>>...<<<END>>> / <<<DELETE p>>> blocks>}`. `prepare()`: start a task (source `"jarvis"`), `parse_file_blocks`, `apply_change`, `plan_merge`; state = the plan; description = `describe(plan)`. `execute()`: `run_merge(plan, approved=True)`. If refused, denied or timed out, the task is discarded, so no draft piles up. |

Rules for `app_propose_change` (each is a test, section 6):

- **Refused outright, before `prepare()`**, at the same point as
  `send_email`/`propose_plan` (`jarvis_agent.py:1024-1052`, `_one_call`): the
  four signals `watch.tainted or watch.read or watch.provenance or
  watch.app_context` - **except** that `app_read` in this turn does not count.
  Reason, and it is a judgement call: every byte in `main` was shown on a
  merge card and approved, or written by the owner in a clean checkout; a
  Jarvis that could not read the app it is asked to change would be useless.
  The residual risk (a planted line inside an earlier approved file) is
  covered by the card showing the whole diff. **Reading any other tool's
  output (a web page, an email, a document) still refuses the proposal**, as
  with notes and plans. `app_read`'s own read still marks the turn for
  everything else (web search and note writes ask first afterwards), because
  `app_read` is not added to `_NOT_READING` (`jarvis_agent.py:3153`), while
  `app_propose_change` is (its result is Jarvis's own confirmation).
- Joins `NEEDS_A_PERSON` (`:1654-1665`) so no config file can make it `auto`.
- Counts against `CARDS_PER_TURN = 5` (`:2131`) like any card.
- Local model only for now: reading app files marks the conversation as having
  read files, and the existing router refuses a cloud offer on such a turn
  (rule 1; cloud help for app files is milestone E's own card). Not verified
  here; `test_router` must prove it for this tool.
- `TOOL_GROUPS` (`:3738-3763`): put both members in the existing `control`
  group (members cost no description tokens; a new group's name would add to
  `more_tools`' own text, which `propose_plan`'s comment says is near its
  300-token budget). Not verified: whether `test_tool_text.py`'s 300-token
  per-tool limit fits the two new schemas - trim descriptions as `propose_plan`
  needed.
- `jarvis_reach.TOOL_NAMES` (`jarvis_reach.py:92-`) gets a plain row for each;
  re-run `tools/gen_reach_cases.py`.
- The strict block format is the workspace's (`parse_file_blocks`, `:335-344`).
  Known weakness: the model must put code inside a JSON string argument. Measure
  it in the coding bake-off (`tools/tool_eval`, `PROJECTS-DESIGN.md` section 4)
  before trusting it.

---

## 5. Both apps' screens

Both add **one "App" section to a project's page** in Brain -> Projects; there
is no Apps screen. A project with `app = null` looks exactly as today.

**The App section shows** (all from `GET /api/projects/<id>`, `app` object):
type (web / native Android) and the app's title; "Latest version: <subject>,
<date>" and the count of saved versions; a line "Files: kept on this PC in
Jarvis's apps folder"; the **open tasks** (title, "3 files, +41 -2", a
"made before another change - may not fit" mark when `older_main`, "waiting for
your card" while a card waits); the last merge outcome sentence; and, in the
project list, a dot/label "App" and a count of open tasks.
**A task opens a Task view:** its files with counts, then the **whole
comparison**, then **Merge** and **Discard**. Merge says "Approve the card that
appears - it needs [Windows Hello | your fingerprint or PIN]." The card itself
appears in the Jarvis bar / phone approval queue like any other card; **these
pages never approve anything**.

| | Desktop | Phone |
|---|---|---|
| See app, tasks, versions, outcomes | yes | yes |
| Read a task's whole diff | yes: monospace, added lines green, removed red, in the Brain window | yes: `LazyColumn` of lines (the cap is 60,000 characters, about 1,500 lines), monospace, no wrap with sideways scroll, coloured by first character; it never builds the whole text as one `Text` |
| Tap Merge (raises the card) | yes | yes |
| Approve the card | yes, Jarvis bar, Windows Hello | yes, phone queue, screen lock; the widget never approves it (heavy) |
| Discard a task | yes, "are you sure?" | yes, "are you sure?" |
| Create an app project / adopt an unlinked app | yes (New project -> "An app Jarvis builds") | **no**: "Set on your PC" |
| Start a task, paste a change | yes (PC only) | **no** (nothing to paste; deep editing) |
| Write a benchmark's command | PC only (unchanged) | "Set on your PC" (unchanged) |

Under App lock or "Hide memory lists and chat history" the desktop hides the
whole `app` object exactly as it hides a project's private text
(`projects.rs`: `redact` when `crate::lock::private_hidden`), and the phone
blocks screenshots (CLAUDE.md, 2026-09-25) and hides the same. Code is the
owner's private work.

**Rows for `ARCHITECTURE.md` section 8 ("One-sided on purpose"):**

1. *Creating an app project and starting a task from the phone (the API allows
   both).* "Nothing on the phone can fill a task: pasting code is deep editing
   and stays off the phone. Jarvis's own writing (B2) works from chat on either
   app, and the phone reads, merges and discards what exists."
2. *Pasting a change into a task (`POST .../app/tasks/<task>/files`).* "PC only
   (403 `pc_only`): a paste of code is the owner's editing, not a setting; the
   phone has no place to write it. Lands only in the task's own copy; the
   merge card decides."
3. *Approving `app_merge_change` is on both apps* (not one-sided; say so to
   stop a later reader assuming PC-only like `pair_device`), pending question 2.

`tools/check_parity.py` entries: `/api/projects/{id}/app/tasks` ported;
`.../tasks/{task}` ported; `.../merge` ported; `.../discard` ported;
`.../files` **deliberate** (the desktop only; reason as row 2).

---

## 6. Tests, per piece

Backend (Python, plain `python3 test_x.py`, real git in a temp settings folder
like `test_app_workspace.py:36-`; skip only if git is missing):

- **`test_app_workspace.py` (extended):** `source` is stored and shown;
  `describe` adds the pasted line only for `pasted`; a `.env` block yields no
  diff entry and `apply_change` says so (today it returns
  `changed: len(checked)` even if `.gitignore` dropped the file:
  `jarvis_app_workspace.py:385-386` - a real small bug the audit should fix);
  a change equal to `main` -> plain refusal; open-task cap (10).
- **`test_projects.py` (extended):** an old `projects.db` gains `app` on open;
  `folder` and `app` are mutually exclusive both ways; `app` is not editable via
  `POST /api/projects/<id>`; delete keeps the folder and answers `app_kept`;
  MAX_PROJECTS counts app projects; adopt only of a real, unlinked app; failed
  insert removes only the folder just created (a pre-existing folder survives).
- **`test_apps_in_projects.py` (new):** slug rules and collisions; every route in
  section 7 with success and each error code; **PC-only** for `/files` (peer not
  local -> 403 `pc_only`), and not PC-only for merge/discard; merge raises exactly
  one card with `describe(plan)` word for word and detail keys as 2.2; `202`
  then outcome in `merge.last` for yes / no / timeout / tier not `ask` (503,
  no card) / gate raises / withdrawn by discard; a second merge while waiting
  is 409; **stale rule**: change `main` (merge another task) or the task
  between card and yes -> `stale`, nothing merged; unsaved change in the app
  folder -> `unsaved`; conflict -> `conflict` and `main` untouched; too-big diff
  -> 400 with no card; the audit log holds counts only (no path, no code);
  a fake token in the environment never reaches git (existing check, re-run
  through the new module).
- **`test_asks_first.py`, `test_card_words.py`, `test_gate_risk_words.py`,
  `test_gate_denial_rule.py`, `test_gate_stack_clean.py`, `test_patch_history.py`:**
  re-run after the patch; `app_merge_change` is in `MUST_ASK` and
  `HARD_LIMITS`, never switchable (`test_asks_first` already checks
  `SWITCHABLE` never meets `HARD_LIMITS`); `tools/gen_risky_approval_cases.py`
  gains a row proving the card is **risky** (`is_risky` true) and `tools/gen_asks_first_cases.py`
  is re-run for the new fixed row. `python3 tools/build_patch_history.py` after
  `git fetch --unshallow origin` (CLAUDE.md: shipped-red once).
- **B2 only, `test_agent_app_wiring.py` (new):** refused on each of the four
  taint signals separately; **allowed** when the only read was `app_read`;
  refused after `my_files`/web/email; card limit; blocks that try `..`,
  `.git`, device names, an absolute path -> refused before any file is written;
  a denied card discards the task; `app_read` cannot read `.env*` or a path
  outside `main`; router refuses a cloud offer after `app_read`.

Desktop: `tests/projects.mjs` extended against the shared fixture (app
section, task view, diff colouring, Merge/Discard held on a stale link,
Discard asks first, `redact` under private-hidden hides `app`); `projects.rs`
unit tests for the new `ACTIONS` and `write_path`, and for `redact` on `app`
(`cargo fmt`, `cargo check`/`clippy --target x86_64-pc-windows-msvc
--all-targets`, per CLAUDE.md; `cargo test` needs Windows).
Phone: `ProjectsTest.kt` for the new parsers and `heldOnStale`, diff line
colouring and paging (Kotlin compiles only in CI). `tools/check_parity.py`
clean. **The phone's widget/notification handling of a `heavy` card**: one test
each side.

---

## 7. Build order and the frozen API

Three builders can start at once: **B-backend** writes `jarvis_apps.py` and the
edits; **B-desktop** and **B-phone** code against the examples below, and run
against `projects-cases.json` when the backend regenerates it (step 1 of the
backend, first thing, so it is early).

### 7.1 The API (frozen)

All routes: token + origin (the installer wrapper, like
`jarvis_projects.install`, `:1781-1845`). Errors are
`{"ok": false, "error": "<a plain sentence>"}` with `400` (bad field, nothing to
merge, too big), `403` (`"pc_only": true`), `404` (no such project / app /
task), `409` (limit, name in use, a card already waiting, task cannot change
while a card waits), `503` (git not installed, tier not `ask`). A git problem
inside a request is a plain sentence, never a stack trace.

**Existing routes, changed:**

| Route | Change |
|---|---|
| `POST /api/projects` | body may add `"app": {"type": "web"\|"android"}` (new app) or `"app": {"adopt": "<folder name>"}`; only with `kind: "coding"` and no `folder` (400 otherwise); `here` not required. Answers `{"ok", "project": full}` |
| `GET /api/projects` | adds `"unlinked_apps": [{"name","type","title"}]`; each summary adds `"app": null \| {"name","type","tasks": <open count>,"merge_waiting": bool}` |
| `GET /api/projects/<id>` | `full` adds `"app"` (below) |
| `POST /api/projects/<id>` | `"app"` in the body -> 400 "An app is chosen when the project is made."; `"folder"` on an app project -> 400 "This project's files are its app." |
| `POST /api/projects/<id>/delete` | app project: also `"app_kept": "<name>"`; folder untouched; waiting card withdrawn |

**New routes** (`<id>` = project id, `<task>` = 12 hex characters):

| Route | Method | Body | Answers |
|---|---|---|---|
| `/api/projects/<id>/app/tasks` | POST | `{"title"}` (120 chars; at most 10 open tasks -> 409) | `{"ok", "task": summary}` |
| `/api/projects/<id>/app/tasks/<task>` | GET | - | `{"ok", "task": detail}` |
| `/api/projects/<id>/app/tasks/<task>/files` | POST | `{"blocks": "<<<FILE p>>>...<<<END>>>"}` (at most 2,000,000 characters); **PC only** | `{"ok", "task": detail}`; no blocks -> 400 "No <<<FILE>>> blocks were found."; card waiting -> 409 |
| `/api/projects/<id>/app/tasks/<task>/merge` | POST | `{}` | `202 {"ok", "waiting": true, "message"}` and ONE card; or `400` with why no card |
| `/api/projects/<id>/app/tasks/<task>/discard` | POST | `{}` | `{"ok", "discarded": true}`; withdraws a waiting card |

**Shapes.**

```
app (in full; null on a life project or a folder project):
{"name": "notes", "type": "web", "title": "Notes app",
 "git_ok": true, "said": "",
 "main": {"head": "a1b2c3d", "subject": "Jarvis: Add a dark mode", "at": 1759000000.0, "versions": 7},
 "tasks": [ task summary, ... ],            // open tasks, oldest first
 "merge": {"waiting": "a1b2c3d4e5f6" | null,
           "last": {"task": "...", "outcome": "merged", "message": "...", "at": 1759000100.0} | null}}
   // git missing: "git_ok": false, "said": "git is not installed on this PC ...", tasks [], main null

task summary:
{"task": "a1b2c3d4e5f6", "title": "Add a dark mode", "started": 1759000000.0,
 "source": "jarvis" | "pasted" | "empty", "files": 3, "added": 41, "removed": 2,
 "older_main": false,      // main has moved since the task began (meta.base != main)
 "waiting": false}

task detail: summary plus
{"list": [{"path": "src/App.tsx", "added": "40", "removed": "2"}, ...],   // as workspace.diff, strings
 "diff": "diff --git ...",    // whole text, at most 60,000 chars; "" when too big
 "too_big": false, "refused": ""}   // refused = the sentence plan_merge would give, or ""
```

`merge.last.outcome` and its fixed sentences (one table in `jarvis_apps.py`,
copied word for word into the shared `words` of the contract file):

| outcome | message |
|---|---|
| merged | "Added to your app." |
| denied | "Not added - you said no. The change is kept aside." |
| timed_out | "Not added - the card timed out. The change is kept aside." |
| stale | "Not added - the app or the change moved after the card was shown. Look at the new card." |
| unsaved | "Not added - the app's own folder has changes that are not saved in git." |
| conflict | "Not added - the change did not fit the app's newer version. Nothing was changed; discard it and ask again." |
| withdrawn | "Not added - the change was thrown away before you answered." |
| refused | "Not added." (plus the gate's reason, at most 200 characters, as `_finish` does) |
| failed | "Not added - something went wrong. Nothing was changed." |

### 7.2 Backend (one builder; container; tested here)

1. `tools/gen_projects_cases.py`: add the `app` answers and `words` to the shared
   fixture from a real run of the new module (regenerated fixtures early: the
   other two builders' tests bind to it).
2. `jarvis_app_workspace.py`: `start_task(..., source="jarvis")`, `source` and
   `base` in `list_tasks`, `MergePlan.source`, the pasted line in `describe`,
   `main_info(name)` (head, subject, time, count), fix `apply_change`'s
   `changed` count, `MAX_OPEN_TASKS`.
3. `jarvis_projects.py`: `app` column + unique index + migration; `create`
   (`app` new/adopt, cleanup on failure), views, `update`/`delete` rules, the
   `unlinked_apps` list. (Whole-file module: edit it directly, no patch.)
4. **`jarvis_apps.py`** (new, shipped whole; add to `_where.py:205-` beside
   `jarvis_app_workspace.py`, and to `scripts/apply-patches.ps1:936-` copy list):
   route parsing, task views, the card (`_decide` modelled on
   `jarvis_projects._decide`, `:1400-1428`), the merge/discard switch lock,
   in-memory pending/last state, `install()` (wraps `Handler` like
   `jarvis_projects.install`; its routes never overlap `jarvis_projects.parse_route`
   because `<id>/app` is a third path part the projects router returns `None`
   for, `jarvis_projects.py:1670-1689`).
5. `backend/apps-in-projects.patch`: hunk 1, `jarvis_hud.py`, an install block
   right after the projects block (`projects.patch`); hunks 2-3, `jarvis_gate.py`
   risk entry and `_NO_RULE_FROM_DENIAL` (context from `devices.patch`). Register
   in `scripts/apply-patches.ps1` **after** `projects.patch` and `devices.patch`;
   verify with `_stack.py`; then `build_patch_history.py`.
6. Tier and tables: `rebuilt/jarvis-framework.toml` line; `MUST_ASK`; the
   `fixed:app_tasks` row ("Start an app task, throw one away, or paste a change
   in on the PC" - no card - "Nothing runs and nothing reaches the app until you
   approve the merge card") in the Projects group of `jarvis_asks_first.py:329`;
   re-run the `tools/gen_*_cases.py` generators that changed.
7. `backend/README.md` entry; `docs/JARVIS-API.md` **§91**; flip the status line of
   `docs/APP-BUILDER-DESIGN.md` (milestone B split into B1/B2, "an 'Apps'
   screen" line replaced by "the Projects screen"); `docs/PROJECTS-DESIGN.md`
   pointer; `CHANGELOG`.
8. (B2, after question 1) `jarvis_app_workspace.read_main / list_main` plus the two
   tools, refusal function, tables, tests, and `apps-tools.patch` if
   `jarvis_agent.py` is a patch target on the owner's PC (it is a whole
   module in this repo: edit directly).

### 7.3 Desktop (one builder; Rust checked against the Windows target)

- `brain/projects.rs`: new `ACTIONS` (`app_task_start`, `app_task_files`,
  `app_task_merge`, `app_task_discard`) with their paths in `write_path`; `projects_read`
  gains reading one task (`.../app/tasks/<task>`); `held_on_stale` holds all four;
  `redact` hides `app` (and a task's `diff`) under `private_hidden`; the diff
  never enters a log; the page never names a URL (existing rule).
- `projects.js` (words, readers: `readApp`, `readTask`) and `projects-panel.js`
  (the App section, Task view, the "New project -> An app Jarvis builds" choice
  and the "Add an app I already have" list from `unlinked_apps`, the paste box for
  blocks, "are you sure?" on Discard and on Delete with the wording in section 1).
  Text only via `textContent` (existing rule, `projects-panel.js` header).
- `tests/projects.mjs`, new Rust tests, fixtures from step 7.2.1. Note for the
  builder: this container cannot fetch Playwright's browser (CLAUDE.md), so the
  page tests need a run on a machine that can.

### 7.4 Phone (one builder; Kotlin compiles only in CI)

- `net/Projects.kt`: parse `app`, `unlinked_apps` (ignored), task summary/detail,
  outcome sentences; `heldOnStale` covers merge and discard; `JarvisRuntime.projectsWrite`
  already takes `action`/`path`/`json`, so add only the action names.
- `ProjectsPlate.kt` (609 lines; do not grow it past readability: add
  `AppSection.kt` and `TaskDiffScreen.kt` beside it): the App section, task list,
  Task view with the paged diff, Merge, Discard ("are you sure?"); "Set on your
  PC" for create/paste; hidden and screenshot-blocked under App lock / "Hide
  memory lists" like the rest of Projects.
- `ProjectsTest.kt`; verify by eye against `AGENTS`-style rules in CLAUDE.md
  "How the Android apps get built"; confirmed only when CI compiles it.
- Prove (test) that the phone's approval widget and notification path do not
  approve this `heavy` card.

Order that unblocks everyone: backend 7.2.1-7.2.4 first (a day), while desktop
and phone build against section 7.1; then 7.2.5-7.2.7; desktop and phone finish
against the real fixture; the feature audit (section 8) last, as one pass.

---

## 8. The standing audit, done in advance

**Bugs (found by reading, to be proved by the tests above):**

1. `apply_change` returns `changed: len(checked)` after `git add -A` even when
   `.gitignore` silently dropped a written file (`.env`, `node_modules/`, `dist/`,
   `*.jks`): the owner sees a card missing a file Jarvis "wrote". Fix: report the
   diff's file count.
2. `run_merge` demands a clean app folder (`jarvis_app_workspace.py:490-492`); an
   owner who edits `apps/notes` in an editor gets `unsaved` on every merge. The
   sentence must say what to do ("save them in git or undo them first").
3. Two open tasks that touch the same file: the second merge conflicts after the
   first lands. `older_main` warns; `conflict` explains. Tested.
4. `list_tasks` only lists tasks whose folder exists (`:301`); a task whose folder
   was deleted by hand leaves a stray branch and metadata file. `discard` already
   tolerates it; the API's `discard` on a "gone" task must still clean up.
5. Every workspace call holds one global `RLock` while git runs (up to 60 s,
   `GIT_SECONDS`): a slow diff blocks a merge of another app. Acceptable for one
   owner; noted.
6. Path traps left open by `safe_path`: it refuses `.git`, `..`, devices, drive
   letters and outside-realpath (`:306-332`) but does not refuse `.gitattributes`
   or `.gitmodules`. With no owner git config and hooks off (`:182-206`) they do
   nothing today; when milestone C runs commands, revisit.

**Both apps:** the Projects screens are the one surface for both, so the audit
question is answered by the table in section 5; the three one-sided rows go to
`ARCHITECTURE.md` section 8; `tools/check_parity.py` must be clean.

**Fit with what is there:**
- One permission model: a new gate action in the same risk table, same
  `ask`/`MUST_ASK`/`HARD_LIMITS`, same card words, same owner-check rule
  (`is_risky`), one card at a time, no "always allow" (a merge is never
  standing; a denial makes no rule).
- Not a second projects list, folders list, goals system or diff viewer.
- **Goals:** an app project's goals attach exactly as any project's (unchanged).
- **Backups:** `projects.db` is in the backup (PROJECTS-DESIGN "Step 3"); **the
  `apps/` git folders are not.** An app's code lives only on this PC. See risks.
- **Shareable** stays a switch with nothing sent; app files are excluded from any
  future send until the owner decides (Shareable's card already says what may
  go). **Milestone E's "never cloud" flag** is not needed until E.
- **Rules 1-5:** nothing leaves the PC (rule 1); no network in git (no remote,
  `jarvis_app_workspace.py:38-39`); no keys (`git_env`, `:165-179`); the card is
  never auto-approved and never approved by voice or widget (rule 4); the whole
  feature is local files (rule 2, 5 unaffected).
- **Docs to update:** JARVIS-API §91, ARCHITECTURE §8 (rows above) and the
  "Where it lives" pointers, APP-BUILDER-DESIGN status, PROJECTS-DESIGN pointer,
  `backend/README.md`, CHANGELOG, the update guide (owner's 2026-09-28 rule:
  kept true after each merge), `docs/ARCHITECTURE.md` section 11 "Sandbox" row
  (still true; add "and the merge card now reaches it from Projects").

---

## 9. Risks, said plainly

1. **A merge is an approval of code that will one day run.** In B1 nothing runs
   it. The card is risky (Hello / screen lock) and heavy for this reason. When
   milestone C lets Jarvis run `npm`/Gradle in a task's copy, each command gets
   its own card; this design does not lower that bar.
2. **Reading a 60,000-character diff on a phone is hard.** The full text is
   shown, paged; a change that big is refused with "split it". If owners find
   phone approval of code too risky, question 2's other answer makes merge PC-only.
3. **Not verified:** the owner's real gate keeps a 60,000-character card whole;
   the phone's widget/notification treatment of a `heavy` card; the tool-token
   budget for two more tools; that `git worktree` behaves on the owner's Windows
   paths (`apps/.tasks/<name>-<id>` under a long settings path) - one PowerShell
   line on the PC after B1.
4. **An app's code is not in the locked backup.** Losing the PC loses the app.
   Adding app repositories (as a `git bundle`) to the backup changes what that
   locked file holds (rule 1 bent "for that one locked file only") - the owner's
   decision, not made here. Say it in the app section: "This app's files are only
   on this PC."
5. **Small model, small changes.** On the 8 GB card an 8B model writes small,
   single-file changes reliably at best (`PROJECTS-DESIGN.md` section 4). B2 must
   say so on the screen, not promise more.
6. **Adoption trust:** an unlinked app folder could have been edited by anything
   with the owner's Windows permissions. Adoption only links it; nothing is run;
   any later change still needs the card. Its git history is the owner's to read.
7. **Deleting a project does not delete the code**, on purpose. An owner may expect
   it to; the confirm sentence says otherwise.
8. **Stale approvals of a card raised then abandoned.** A card waiting when the
   backend restarts is gone (in-memory state, like Shareable); the task stays as a
   draft and can be merged again with a new card.

---

## 10. Open owner questions

**1. Jarvis writing the code on today's 8 GB card.** Your Projects answer says
code writing waits for the 12 GB card; your app-builder answer has no such wait.
Which applies to the tools that let Jarvis write an app's files?
- **Wait for the 12 GB card (recommended):** build the screens, the merge card
  and the PC paste-in now; add Jarvis's own writing once the card is measured.
- **Build it now, small changes only:** Jarvis writes single-file changes on the
  8 GB card today, and says plainly that it is limited.

**2. Approving an app change from the phone.** The card shows the whole change,
and approving needs your fingerprint or PIN. Should the phone be allowed to
approve it?
- **Yes, on both (recommended):** matches Projects' design; you read the full
  change on the phone first.
- **PC only:** the phone can look and discard, but only the PC (Windows Hello)
  approves a change.
