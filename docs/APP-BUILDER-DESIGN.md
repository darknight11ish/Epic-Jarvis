# The app builder - design and milestones (2026-09-28)

**Status: milestone A is built (`backend/jarvis_app_workspace.py`), and
nothing is switched on.** It has no tool, no API route and no screen yet,
so the owner cannot use it until milestone B.

## What the owner decided (2026-09-28)

- **Jarvis may build apps and write code for the owner.**
- **Both kinds of app:** web apps (React + Vite, wrapped for Android with
  Capacitor) and native Android apps (Kotlin).
- **Local model first, cloud only when Jarvis is stuck.** Jarvis works on
  the local model. If it can't get a step right after a set number of tries,
  it may *offer* to ask a cloud model. That offer is an approval card
  listing exactly which files and error text would leave the PC. This
  loosens rule 1 for app project files only, one card per offer. It never
  covers email, notes, memory, chat history, settings or keys.

## The permission model

Jarvis uses the same four steps as every other action (ARCHITECTURE section
3): plan, describe, gate, run.

| Action | Card? | Why |
|---|---|---|
| Create an empty app project | No | An empty folder inside Jarvis's own `apps` folder; nothing runs. |
| Write files in a task's copy | No | They land only in that task's separate copy (a git worktree) and nothing runs them. The owner decides at the merge. |
| Bring a task's change into the app (merge) | **Yes**, every time | The card lists every file and shows the full before/after comparison. If anything changes after the card was built, the merge is refused. |
| Run a command (npm, npx, Gradle) | **Yes**, every command (milestone C) | See the warning below. |
| Ask a cloud model for help | **Yes**, every time (milestone E) | Shows the exact files and error text that would be sent, and to which provider. |
| Install an app on the phone | **Yes** (milestone G) | Sideloading is rule 5's route. |

### Warning: a git worktree is not a sandbox

`ARCHITECTURE.md` section 11 says "Sandbox: Git worktrees, not Docker". A
worktree keeps **changes** apart until they are approved. It doesn't stop a
**program** from doing things: `npm install` runs other people's install
scripts, and a Gradle build runs build code, both with the owner's Windows
permissions. So:

- every command gets its own card, showing the exact command;
- `npm install` runs with `--ignore-scripts` by default. Allowing a
  package's install scripts is a separate card that names the packages;
- commands run with the same allowlisted environment as `shell_exec`
  (`jarvis_child_env`: never a key, token or password), inside the task's
  copy, with a time limit;
- the stale-event-stream rule (rule 4) blocks all of this, as it does every
  other action.

## Milestones

Each milestone can be built and tested on its own. The first one the owner
can see (B) gets the usual new-feature audit (`CLAUDE.md`).

- **A. Workspace - BUILT.** `jarvis_app_workspace.py`: app projects under
  `<settings folder>/apps/`, a separate copy per task, Jarvis's file changes
  read from a strict format (`<<<FILE path>>> ... <<<END>>>`), and a merge
  card that shows the whole change and refuses if anything moved since. It
  runs nothing. git gets no secrets and none of the owner's own git settings.
  Tested by `backend/test_app_workspace.py`.
- **B. Wiring.** The gate actions (`app_merge_change`, later
  `app_run_command`) in `jarvis_gate.py`'s risk table, through a patch;
  local-lane tools in `jarvis_agent.py`; API routes; and an "Apps" screen in
  both apps showing projects, tasks and the merge card. This is the first
  milestone the owner can see.
- **C. Running commands.** A short list of allowed commands per kind of app,
  each on its own card: `npm install --ignore-scripts`, `npm run build`,
  `npx cap sync android`, `gradlew assembleDebug`. It runs only in a task's
  copy. The PC needs Node.js, and for Android a JDK and the Android SDK; the
  owner installs these, and the setup guide says how.
- **D. Planning first.** Before any code, Jarvis asks what the app is for
  and writes a short plan (`PLAN.md`) and rules file (`AI_RULES.md`) into
  the project. Those arrive through the same merge card, so the owner
  approves the plan before Jarvis starts on the code. (The idea follows
  Roo Code's "Architect mode" and Dyad's `AI_RULES.md`; no code is copied.)
  A map of the project's files and functions, so a small model sees only
  what matters, is a candidate here (the idea behind Aider's RepoMap and
  RepoMapper; nothing chosen yet).
- **D2. Trial: aider as the coding engine (queued 2026-09-28).** aider
  (Aider-AI/aider, formerly paul-gauthier/aider, Apache-2.0) edits code in
  a git repository and can use the local Ollama model. It includes a project
  map (RepoMap), which is milestone D's candidate idea. The trial runs it
  ONLY inside a task's copy, locked down: it doesn't suggest or run shell
  commands, doesn't use "yes to everything" (which would auto-approve and
  break rule 4), sends no analytics, uses no cloud model (milestone E's card
  is the only way to the cloud), and gets the same no-secrets environment as
  git. Every one of those settings must be checked against aider's own
  documentation and tested before the trial counts. Its commits stay on the
  task's branch, so the merge card still decides. It's kept only if it
  does better than Jarvis's own file blocks on the same small tasks.
- **E. Cloud help when stuck.** Jarvis counts failed tries on the same
  step (a build error that keeps coming back). After the limit (3 to start;
  the owner may change it), it offers a card: which provider, which files,
  the exact error text, and that these app files will leave the PC. Excluded
  always: `.env` files, signing keys, and anything that looks like a secret.
  A project can be marked "never cloud".
- **F. Native Android projects.** A Kotlin template and a Gradle build
  (milestone C's card). Slower builds, and harder for a small model; the
  12 GB card helps.
- **G. Put it on the phone.** Install the debug APK on the paired phone with
  adb, behind a card. Never the Play Store (rule 5).

## Not adopted, and why

These tools were suggested (Gemini, 2026-09-28) and looked at:

- **bolt.diy, Dyad:** whole app-builder programs. Jarvis takes only their
  ideas: strict file blocks, and a rules file per project.
- **Plandex:** AGPL; ideas only.
- **Microsoft agent-framework, agno:** each brings its own approvals,
  checkpoints and memory. Jarvis has one permission model (`jarvis_gate`) and
  one scheduler, and the 8 GB card runs one model at a time.
- **BuilderIO agent-native:** a TypeScript app framework. The app builder's
  screen belongs inside Jarvis's own windows, which use no outside libraries.
- **crawl4ai:** a web crawler. Reading one page is already possible;
  crawling whole sites would be a new way out of the PC, so any use would
  need a card per address.
- **Offline developer docs (Dash/Zeal docsets):** a candidate for later,
  searched like "Folders Jarvis may look in" and treated as outside text.

## Known limits

- A small local model will write small apps better than large ones. That is
  why the cloud step (E) and the 12 GB card matter.
- A merge card can hold up to 60,000 characters of diff. Anything bigger is
  refused with "split it into smaller steps", because a card nobody can read
  isn't a real decision.
