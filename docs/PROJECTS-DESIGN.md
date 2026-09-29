# Projects: design (2026-09-28)

Status: **build steps 1 and 2 built on the backend, and step 3 - the
screens in both apps - built (2026-09-28); see "Build notes" at the end.** For the owner's decision "Projects,
like Claude's Projects and more" (`CLAUDE.md`, 2026-09-28): both coding and
life projects, and Jarvis does real work on the PC with a card for every
change. Queued after the chatbot driver. Written by the studio's designer;
file references were checked in the source unless marked.

**Apps (2026-09-29):** an app Jarvis builds is a coding project whose tests
are its benchmarks - one list, not two. Its tasks, the merge card and pasting a
change in on the PC are in `docs/APPS-IN-PROJECTS-DESIGN.md` (backend built:
`jarvis_apps.py`, `docs/JARVIS-API.md` section 92); Jarvis writing the code
(step 5 and 7 below) still waits for the 12 GB card.

**In short:** a project is one place for one thing the owner is working on -
an app, or "run a half marathon". It holds instructions, files, chats,
goals, measurements ("benchmarks") and a work list. Jarvis can do real work
on the PC - change files and run tests - and every change asks first, with
a card showing exactly what will change.

## Three things to know first

- **Jarvis can already run commands, but that tool is not safe enough for
  projects.** `shell_exec` (`backend/jarvis_agent.py:804`, gate action
  `run_shell_on_host`, always asks) has no folder limit, no network block,
  runs through the shell (`shell=True`), and its time limit (at most 120 s)
  may not stop programs the command starts itself (known Python-on-Windows
  behaviour; not tested here). Projects need a new, fenced runner (§4).
- **This replaces an earlier "no".** The feasibility audit turned down a
  "code helper" (I60, `docs/FEASIBILITY-AUDIT-2026-09-26.md`: "an editor is
  a separate, risky decision"). The owner has now made that decision.
- **Jarvis has no file-writing tool today** (checked in `jarvis_agent.py`'s
  tool list). The edit tool (§4) is new.

## 1. What a project is

| Part | What it is | Built from |
|---|---|---|
| Name and instructions | "How Jarvis should work on this", in the owner's words, capped (~1,500 characters) | new `jarvis_projects.py`, `projects.db` |
| Files | one folder (coding) or none (life) | must already be on "Folders Jarvis may look in" (`jarvis_documents.py`); adding one is PC-only with one `change_own_config` card; no second list |
| Chats | ordinary chats tagged with the project | `jarvis_chat_log.py`: a `project` id column on `conversations` |
| Goals | the Goals feature | `jarvis_goals.py` (continuation branch) |
| Benchmarks | named measurements with dated results | new, in `projects.db` |
| Work list | a named to-do list | `jarvis_schedule.py` named lists |

**What the model sees in a project chat:** one SYSTEM line added on the PC
(the same way `with_cut_off_note` works, never echoed back to the app) with
the project's instructions, its notes (§2), the open goal steps, the latest
benchmark result ("tests: 41 of 45 passing, 3 Oct") and the usual recalled
facts. On the 8 GB card this must fit in about 8,000 tokens with about 3,450
left for reading (`jarvis_documents.py`'s docstring), so every part has a
hard size limit.

**How Goals attach - one extra field, no second goals system:**
`POST /api/goals` gains an optional `project` (a nullable column in
`goals.db`; `GET /api/goals?project=<id>` lists one project's goals). A step
may carry an optional measure, e.g. `{"bench": "tests", "target": 45}`. The
weekly check-in stays model-free and reads the latest result ("tests: 41 of
45, target 45"). Everything else is unchanged: at most 7 steps, one
`schedule_repeat` card per goal, each acting step its own card. Flag:
`MAX_GOALS = 20` counts all goals together and may need raising.

**Copied from Claude Projects** (general knowledge, not re-checked):
instructions, files as background, chats grouped per project, memory per
project. **Added:** goals, benchmarks with charts, a work list, and Jarvis
doing the work on the PC.

**Files, and the one gap.** Claude puts a project's files into what the
model reads; Jarvis cannot in 8K tokens. It reads the folder with the
existing `my_files` tool (find, search, read one part at a time), limited to
the project folder in project chats. `my_files` reads only `.md`, `.txt`,
`.csv` and PDF/Word/Excel/PowerPoint (`TEXT_KINDS`, `DOC_KINDS`); code files
(`.py`, `.rs`, `.kt`, `.js`) must be added as plain text. Hidden folders
such as `.git` stay unread.

## 2. Memory

- **Facts still come only from the owner's own typed or spoken words**
  (ARCHITECTURE §5). Project files, test and benchmark output and Gemini's
  replies are **outside text**: never learned, and reading them marks the
  chat, so note writes and web searches ask first as today.
- **A fact learned in a project chat gets a project label**
  (`meta.project = <id>`), like the "between us" label
  (`memory-shared.patch`), not a new way into `facts`. It is recalled only in
  that project's chats. Brain lists it under the project with Forget, Erase
  the words, and "Move to personal memory".
- **Project notes** are the owner's own pinned lines for one project ("the
  server uses port 8080") - like "Always keep in mind", per project, small,
  no card (the owner writes them).
- **Tested before kept:** new `eval_memory.py` cases prove a project fact
  never appears outside its project and personal recall gets no worse (the
  memory scoreboard rule).
- **Life numbers are project data in `projects.db`, not facts.** A benchmark
  about health or money (weight, savings) is sensitive - marked by
  `jarvis_sensitive` from its name, or by the owner. Its numbers stay on
  screen, are never read aloud, and never go into a web search or a chatbot.

## 3. Benchmarks

**Coding projects.** A benchmark is a name, one exact command, a way to read
its number, and a time limit. **Code reads the number, never the model**:
the exit code (pass/fail), a test summary Jarvis recognises (pytest, cargo
test), or a line the owner's script prints (`JARVIS_SCORE startup_ms=812`).
Each run stores when, the git save point, the number, pass/fail, how long it
took, and whether the chat model was busy (speed numbers are noisy then).
Each result shows "better or worse than last time", like
`eval_memory.py --against`.

**Life projects.** The owner logs a number by voice or tap ("I ran 5 km"),
only from their own words, answered without the model where possible (a
`jarvis_quick.py` pattern, "log 5 km run"). No card: the owner is writing
down their own number, like ticking off a to-do. Reminders ("log your
weight every Sunday") are plain repeating reminders (no card, 2026-09-26).

**A chart in both apps:** dated points, plus a target line when a goal step
has one.

**When a run asks first** (decided inside rule 4):
- **A card with the exact command** the first time it runs, and again
  whenever its words, folder or time limit change. The card shows where it
  runs, the time limit and whether the internet is blocked; approving saves
  the benchmark.
- **No card** for a later run of the same saved, unchanged command **when
  the owner starts it** (a tap or their own words) **inside the fence** (§4).
  Not an "always allow": the owner's press is the decision, about one named,
  fully known thing, like Stop or a timer; the fence keeps it inside the
  project folder with no internet; the code it runs was written by the owner
  or approved one change at a time.
- **Always a card** when the model asks for the run, the turn has read
  outside text, a schedule starts it, the fence cannot be used, or the run
  needs the internet (installing packages). Nothing may change files outside
  the project folder without a card.
- **For the rules guardian:** this is a new "no card" line next to
  `run_shell_on_host`, which stays in `HARD_LIMITS` and `MUST_ASK`
  (`jarvis_asks_first.py`) unchanged; this is a separate action.

## 4. Building

**How Jarvis changes code: a new tool, `project_edit`.** The model proposes
one change (a file plus text to find and replace, or a new file). The
backend turns it into a readable diff; the card shows the file name, removed
lines in red, added lines in green and a little surrounding code.
`describe()` shows the whole diff and never summarises it (§3). A change too
long for one card is refused ("ask for a smaller change"), never cut short.
Only inside the project folder; never `.git` or protected places
(`jarvis_agent._protected_path`). At most 5 cards per answer
(`CARDS_PER_TURN`).

**Which model writes the code:**
- **One card:** `jarvis-primary` (Qwen 3 8B, ~8K tokens). Honest limit:
  small changes to one part of one file - scripts, settings files, fixing
  one error.
- **Two cards:** a coding model on the 12 GB card. `docs/MODEL-TOPOLOGY.md`
  already names `qwen2.5-coder:7b-instruct-q4_K_M` at 16K (5.85 GiB). The
  model scout proposed `qwen3.5:9b` at 64K on the 2060 (~7.7 GiB,
  estimated) but did not cover coding models; newer ones (e.g. Qwen3-Coder
  30B-A3B, needing system memory) are **not checked**. Choose by a bake-off:
  a coding section in `tools/tool_eval` of small real edits whose tests must
  pass. Switching models costs about 6 s, so switch once per session.

**The fence - running code safely on Windows:**
- Jarvis starts the program directly (no `cmd /c` unless the card shows
  it), with the environment from `jarvis_child_env.inherited()` - no keys,
  no token.
- A **Windows job object** (a container for a group of processes): Stop or
  the time limit ends every program the run started at once; it also caps
  memory. 5 minutes by default, 30 at most.
- An **AppContainer** (Windows' own sandbox, the one Edge uses): no
  internet unless given; writes only to folders it is given - the project
  folder (write) and the tool's install folder (read). Tool caches (pip,
  cargo, npm) go to a git-ignored `.jarvis-cache` folder inside the project.
  **Not tested:** some tools refuse to run inside it; then the run is
  unfenced, the card says so, and every run asks.
- Git runs with hooks off (`-c core.hooksPath=` empty), so a git command
  never runs the project's own scripts.

**Undo, in plain words.** Git keeps save points of a folder. If the folder
is not a git folder yet, Jarvis asks once, with a card, to make it one. Each
approved change becomes one save point named after its card. **Undo** adds a
new save point that reverses the change (`git revert`), so nothing is lost;
it is the owner's own tap and needs no card. If a file has unsaved edits by
the owner, Jarvis leaves it alone and asks the owner to save first, or offers
a card to save them as "Your edits". `jarvis_undo` exists on the owner's PC
(ARCHITECTURE §10, unverified) - read it first and reuse it if it fits.

**Stopping.** Work sessions and benchmark runs are `jarvis_task_control`
tasks; Stop and "Stop everything" (`jarvis_stop_all.register`) close the job
object, ending everything the run started.

**How far Jarvis goes on its own: one step per request.** "Next step" means:
read what it needs; propose up to 5 changes, each with its own card; run the
tests (a card, or none if the owner started it); report back. Steps after
reading files or test output say so on their cards under "What shaped this
request". **No "keep going until the tests pass"** until the multi-step
safety tests pass (I05/I95) - that belongs with the plan card and is gated
the same way. Everything here asks one card per action and never batches,
so (like Goals) it does not wait on the plan card.

**Life projects:** plans are goals, reminders use the scheduler, notes go to
Obsidian/Logseq/Joplin as today (a card after outside text). Nothing new
acts on the world.

## 5. Help from outside

- **Web search** in a project chat follows today's rules; after project
  files were read, the search words get a card.
- **Gemini through the chatbot driver:** clean context, no files, no memory
  (`docs/CHATBOT-DRIVER-DESIGN.md` §3). By default only the question the
  owner typed goes out. Sending project content (a piece of code) bends rule
  1 - owner question 1.
- **Plug-in programs (MCP)** work in project chats as today (this PC only,
  read-only).

## 6. Both apps

| | PC | Phone |
|---|---|---|
| See projects, goals, work list, charts | yes | yes |
| Create a life project; edit instructions or notes; log a number | yes | yes |
| Create a coding project (add its folder) | yes | no - adding folders is already PC-only (`jarvis_documents.PC_ONLY`) |
| Approve a change card | yes | yes, full diff shown; the widget never approves one (it opens the app, as with email) |
| Start a saved benchmark | yes | yes (it runs on the PC) |
| Edit files by hand; edit a command's words | yes | no |

**ARCHITECTURE §8 ("One-sided on purpose"):** "Project folders and
benchmark commands are PC-only: folders already are, and a command's words
decide what runs on the PC." Run cards are risky (they run code): Windows
Hello on the PC, screen lock on the phone (`jarvis_owner_check.is_risky`).
Whether a git-undoable edit counts as risky depends on the risk table.

## 7. One card or two

- **Either:** life projects, goals, benchmarks, charts, running tests (the
  processor does that).
- **One card:** small code changes.
- **Two cards:** the coding model and longer project chats (the
  `long_context` lane). The coding model gets a "Your second graphics card"
  switch (one card to turn on), off until the 12 GB card is installed and
  measured. A benchmark that uses the graphics card competes with Jarvis's
  models, so the run records it.

## 8. How it fits

- No second goals, folders, notes or undo system.
- Card wording: "Change 1 file in 'Jarvis Desktop': src/main.js (+4, -2
  lines)"; "Run 'tests' in 'Jarvis Desktop': pytest -q, up to 5 minutes, no
  internet"; refusing costs "Nothing changes."
- "What asks first" gets a Projects group: `project_edit` and `project_run`
  always ask (`MUST_ASK`, `HARD_LIMITS`); fixed no-card rows: "Re-running a
  saved benchmark you start yourself", "Logging your own number", "Undo of
  Jarvis's change".
- API: a new section 88 in `docs/JARVIS-API.md` (59 is Goals, 87 the chatbot driver). No new row in
  `jarvis_reach.KINDS` unless question 1 is "yes".

## 9. Build plan (small testable steps)

1. `jarvis_projects.py`, `projects.db`, routes; the goal `project` field; the
   chat `project` column; `test_projects.py`. (Container.)
2. Life benchmarks: logging, chart data, the quick-command pattern,
   sensitive marking. (Container.)
3. Desktop page (Brain → Projects) with `tests/projects.mjs`; the phone
   screen (compiled in CI only).
4. Project chat context and project-labelled facts; new `eval_memory` cases.
   (Container; real numbers from the PC.)
5. `project_edit`: diff, card, save point, Undo, against a temporary git
   folder. (Container.)
6. The fence (job object + AppContainer, Windows-only), benchmark running
   and number reading. Logic tested here with a stand-in launcher; the real
   check is one PowerShell line on the PC.
7. Coding bake-off in `tool_eval`; the second-card coding switch. (PC.)
8. The feature audit (bugs, both apps, fit).

## The owner's answers (2026-09-28)

- **Sharing: a "Shareable" switch per project, off by default.** When on, a
  short piece of the project's files may go to a web search or the chatbot
  driver, shown word for word on the card first; never health or money
  numbers, memory, email or credentials. This bends rule 1 for that shown
  piece only; it needs a row in `jarvis_reach.KINDS` and ARCHITECTURE §4.
- **Order: projects, goals, benchmarks, charts and running tests first**
  (build steps 1-4 and 6); code writing (`project_edit`, steps 5 and 7)
  once the 12 GB card is installed and measured.

- **An automatic private mark can be removed by the owner, with a card
  first** (2026-09-28): the builder found `jarvis_sensitive` reads "5k" as
  money. To build with the Projects screens (step 3).

## 10. Questions for the owner (answered above)

1. **Sharing.** Jarvis could ask Gemini (or a web search) for help with your
   code, which means sending some project files off the PC and bends rule 1.
   - **Keep project files on the PC; only your typed question goes out**
     (recommended)
   - **A "Shareable" switch per project, off by default**: a short piece of
     the files may go, shown word for word on the card; never health or
     money numbers.
2. **Order.** Code writing on today's 8 GB card is limited to small changes.
   - **Life projects, goals and benchmarks first; code writing once the
     12 GB card is measured** (recommended)
   - **Everything at once, with limited code writing on the 8 GB card for
     now**

Not verified: what Claude Projects does today, whether dev tools run inside
an AppContainer, whether git is installed on the owner's PC, and
`jarvis_undo`.

## Build notes

### Steps 1 and 2 (2026-09-28, backend only)

**Built:** `backend/jarvis_projects.py` (shipped whole), `projects.db`,
`projects.patch` (one install block), `backend/test_projects.py`, and the
"log a number" sentences in `jarvis_quick.py`. Routes: `docs/JARVIS-API.md`
section 88 (59 is Goals on the continuation branch, 60 the chatbot
driver). Neither app calls them yet; `tools/check_parity.py` lists them
as `planned`.

What each part does, checked against the code it reuses:

- **Folder:** must be one of `jarvis_documents.folders()` ("Folders Jarvis
  may look in") or a folder inside one, exist, and not be
  `jarvis_documents.protected()`. Chosen on the PC only
  (`jarvis_owner_check.from_this_pc`, failing closed like
  `jarvis_documents._from_this_pc`); clearing it works from either app. A
  folder that later leaves the list shows as `"listed": false`.
- **Work list:** a named list checked by `jarvis_schedule.list_key` (one
  to three plain words, never the to-do list itself), one project per
  list, defaulting to the project's name when that is a valid list name.
  Items are added and read through the existing `/api/schedule` routes.
- **Shareable:** off by default; ON is one `change_own_config` card (the
  action "Folders Jarvis may look in" already uses, so `jarvis_gate.py`
  needed no new line); OFF is instant and withdraws a waiting card. The
  owner's answer did not say whether turning it on asks; every other
  switch that loosens a rule does, so it does here. Nothing is sent: the
  `jarvis_reach.KINDS` row and ARCHITECTURE §4 wait for the first real send.
- **Sensitive:** `jarvis_sensitive.topic()` alone missed "weight", "body
  weight", "resting heart rate", "calories" and "monthly spending"
  (checked), so a short benchmark word list runs first. `keep_on_screen`
  on the benchmark; the quick command's answer is `private`.
- **Coding benchmarks:** the command is kept word for word (PC only, 300
  characters, one line), `"runnable": false`; logging one by hand is
  refused.
- **Cards:** only Shareable ON. Creating, editing, deleting and logging
  are the owner's own taps or words.

**Waiting on the continuation branch (Goals):** a project keeps goal ids
on its own side. After `claude/jarvis-continuation-03kls1` merges: the
goals.db `project` column, `GET /api/goals?project=<id>`, and a goal
step's measure (`{"bench": ..., "target": ...}`), as §1 says. At that
merge, `goals.patch` and `projects.patch` anchor on the same lines of
`jarvis_hud.py`; whichever lands second must be re-anchored on the
other's block.

**Not built, and why:** the chat-history `project` column (step 4 -
nothing can set it until `/api/chat` carries a project id); the project
chat context and project-labelled facts (step 4); the apps (step 3);
running benchmarks (step 6); `project_edit` (steps 5 and 7). Backups
(`jarvis_backup.SOURCE_DBS`) and the data-health check do not include
`projects.db` yet - for the feature audit (step 8).

**For the owner (not decided here):** `jarvis_sensitive` reads "5k" as
money, so a benchmark named "5k time" is marked sensitive (money) and
kept on screen. The owner can take off their own mark but not one made
from the name. Should an automatic mark be clearable, and should
clearing it ask first (it would let a number be read aloud)?
**Answered 2026-09-28: yes, with a card first** - built in step 3, below.

### Step 3 (2026-09-28, both apps' screens)

**Built:** Brain -> Projects on the desktop (`projects.js`,
`projects-panel.js`, `projects.css`, `brain/projects.rs`) and on the phone
(`ProjectsPlate.kt`, `net/Projects.kt`), in the same words from one
contract file (`tools/gen_projects_cases.py`). `docs/JARVIS-API.md` 88.6
says what each shows. The chart is drawn by the apps (an inline SVG on the
desktop, a Compose Canvas on the phone) from the benchmark's own points,
with the scale both apps share.

**The owner's answer, built with it:** an automatic private mark comes off
with ONE `change_own_config` card (`POST .../unmark`); the owner's own
mark comes off at once. Renaming a benchmark or changing its unit checks
its name again.

**The feature audit (step 8's rule, run now for what exists):** backups
(`jarvis_backup.SOURCE_DBS`) and the data-health check now include
`projects.db`. See the CHANGELOG for the rest.

**Still not built:** the chat-history `project` column and project chat
context (step 4), `project_edit` (steps 5 and 7), running a benchmark
(step 6), the goals.db link (after the continuation branch merges).
