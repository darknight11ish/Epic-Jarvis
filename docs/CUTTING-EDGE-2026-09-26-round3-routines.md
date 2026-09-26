# Cutting-edge audit, round 3, 2026-09-26: routines, goals and planning

One slice of the owner's "what else can we add?": Jarvis doing useful
multi-step work safely - plans you approve, goals, routines in plain words,
watchers, a research helper, overnight jobs, and keeping approval cards
from wearing you down.

**Limits.** Research only: nothing was built, run or measured. Repo
`file:line` references were checked on 2026-09-26. arxiv.org is blocked here,
so papers were read only through search summaries, marked *(search summary)*.
GitHub READMEs and LICENSE files were read directly. What a project or vendor
says about itself is marked *(claim)*. **Not repeated here:** the first
outline of Goals and "Routines in plain words" (`creativity-2026-09-25/future.md`
ideas 3 and 7 - this page adds concrete designs), "a home that learns" and the
weekly journal (ideas 4-5), GitHub "tell me when CI finishes" and instant email
watching (`CUTTING-EDGE-2026-09-26-capabilities.md` items 3, 9), the overnight
memory tidy (`MEMORY-RESEARCH`), and from the parallel reports: the decision
ledger and value-level labels (`...-round2-trust.md` items 8, 10, 11), the
quote check under answers and news feeds (`...-round3-knowledge.md` items 1, 10).

---

## In six lines, for the owner

1. **One "plan card" is the key piece.** Jarvis shows every step of a job on one card. Safe steps run on your one yes. Risky steps (sending, anything that cannot be undone) ask again, one at a time, when their turn comes.
2. **Goals can start very simply:** "track: insulate the garage by 1 November" goes on Coming up with a weekly "done / still on it / stop". Plans written by the AI come later.
3. **Routines ("movie night") become a fixed, checked list of steps.** Saving one approves nothing. "Try it" shows what it would do without doing anything.
4. **Every step should say how to undo it** - or say plainly that it cannot be undone - before you approve.
5. **New "tell me when" sources:** a folder on this PC and your calendar. A web page you name is also possible, but you would have to allow it.
6. **A research helper and overnight jobs are possible,** but each needs one decision from you first (questions at the end).

---

## The ranked list

Size: S = one module plus tests; M = several files and a screen in both apps;
L = a new subsystem. Every idea is meant for both apps (Coming up / Brain).

| # | Idea | Why it matters | Size | Rule risk |
|---|---|---|---|---|
| 1 | **Plan card**: every step on one card; risky steps asked again at their moment | The base for routines, goals and research; fewer cards, no "approve all" | M | Medium - owner's call (Q1) |
| 2 | **Goals, stage 1**: on Coming up with a weekly check-in, no AI model | Useful at once; shows whether goals nag before AI planning is built | S-M | Low |
| 3 | **A slower Approve on risky cards** | A risky card cannot be approved in a blink | S | None (stricter) |
| 4 | **Routines compiled to a checked plan**, with "Try it" and a check after each step | "Movie night" in one sentence, checked by code, not trusted to the model | M | Low-Medium |
| 5 | **Undo on the card**; runs go on the existing undo shelf | You know before approving what can be taken back | M | Low (safer) |
| 6 | **More "tell me when" sources**: folder, calendar; a web page (your call) | Watching with no new permission (folder, calendar) | S-M each | Low; page: Medium |
| 7 | **Goals, stages 2-3**: AI drafts a short plan you edit; re-planning in the background | Turns goals into steps, on the second card or the big model | M | Low |
| 8 | **Night shift**: long jobs that only read and prepare, ready by morning | Uses the 12 GB card while you sleep; nothing acts unattended | M | Low-Medium (Q2) |
| 9 | **Research helper**: gathers, compares, checks its own quotes | "Compare these three heat pumps, with sources" | M-L | Medium (full pages need a new lane) |

---

## What Jarvis already has, and how these reuse it

Checked in the source today. Short version: **the one scheduler, the task
controls and the gate already do most of the hard parts.**

- **The one scheduler** (`backend/jarvis_schedule.py`): new kinds plug in with
  `register_kind` (`:313`); `on_fire` runs on its own thread (`:1523`); a kind
  can bring its own rule check, `silent`, `note()` and `plain_repeat` (`Kind`,
  `:220`); kinds load through `KIND_MODULES` (`:310`). Goals, timed routines,
  watchers and night jobs are all new **kinds**, as ARCHITECTURE §12 requires.
- **"Tell me when"** (`backend/jarvis_tellme.py`, registered at `:950`) is the
  watcher template: a minute-level `check_rule` (`:341`), the gate asked on
  every look (`_ok_to_read`, `:565`), an end date (`MAX_DAYS = 90`), and a match
  that **only notifies**, in the owner's words.
- **The initiative engine** (`backend/rebuilt/jarvis_initiative.py`): an empty
  check list (`:29`), a 30-minute heartbeat, findings in memory only. The
  scheduler's header gives four reasons it cannot host timed work
  (`jarvis_schedule.py:26-36`). **Register nothing new there**; its heartbeat
  can become one more scheduler kind later, as that header says.
- **Task controls** (`backend/jarvis_task_control.py`): Stop, Pause, notes,
  and Resume as a card built from each module's own `describe()`
  (`resume_card_text`, `:426`); `checkpoint()` (`:91`) is read before every
  step of the control loops (`jarvis_ui_control.run`, `:344`). **Stop
  everything** takes a stopper per job (`jarvis_stop_all.register`, `:108`).
- **Where a value came from**: `_TurnWatch._came_from_outside`
  (`backend/jarvis_agent.py:2563`) finds a card's values that appear in outside
  text but not in the owner's words; `shaped_by` (`:2607`) prints them.
- **Limits**: `CARDS_PER_TURN = 5` (`jarvis_agent.py:1508`); `NEEDS_A_PERSON`
  (`:1117`) lists the seven actions only a person's yes may run. A plan carries
  a digest of its requests and the run refuses if they changed
  (`jarvis_home._digest`, `:195`, used by `plan_services`, `:401`).
- **On the owner's PC only, contents unverified from here** (ARCHITECTURE §10):
  an undo shelf (`GET /api/undo`, `/api/undo/revert`; the phone's `UndoEntry`
  has `reversible` and `reason`, `jarvis-client/.../net/ApiModels.kt:510-517`),
  a send window ("hold", `/api/holds/cancel`, `JarvisApi.kt:1236-1242`), and a
  jobs list whose permissions are "frozen for its life" (`JobRecord`,
  `ApiModels.kt:561-572`). **Read those files on the PC before building ideas
  5 and 8**, and reuse them if they fit.

---

## The ideas in detail

### 1. The plan card (M)

**Plain words.** For a job with several steps, ONE card lists every step
exactly as that step's own card would show it. Your yes runs the safe steps. A
risky step - one that leaves the PC, cannot be undone, or is in
`NEEDS_A_PERSON` (email, shell, browser, another app) - never rides that yes:
it gets its own card when its turn comes, showing its final content.

**What is current.** The 2025 "design patterns" paper (IBM, Invariant Labs, ETH
Zurich, Google, Microsoft) names **plan-then-execute**: a fixed plan made from
the user's request alone, which text read later cannot change *(search
summary)*. Google DeepMind's CaMeL also tracks where every value came from
(Apache-2.0; "research artifact", read). Magentic-UI 0.1 (MIT, read) has
"co-planning" (edit the plan before it runs) and "action guards" ("sensitive
actions are only executed with explicit user approvals"). **Why bother:**
"Claude Code users approve 93% of permission prompts" (Anthropic, 2026-03-25,
read) *(claim)*. Many small cards teach people to approve without reading.

**Where it plugs in.** A new gate action (e.g. `run_plan`, tier `ask`), whose
`describe()` joins each step module's own `describe()` word for word, as
`resume_card_text` does. Each step keeps its `plan()` object and a digest; the
run reads `checkpoint()` before each step. Three rules, in code:
- **A step whose values were filled in from an earlier step's output** is
  asked again, with its `shaped_by` lines (CaMeL's idea, with Jarvis's own
  `_came_from_outside`; round2-trust item 10 makes those labels finer).
- **At most 8 steps, at most 3 risky**, so a plan never hits
  `CARDS_PER_TURN`. The plan card counts once.
- **A risky step waits while no app is connected** (rule 4). Nothing risky is
  asked on a stale link.

**Permission fit.** ARCHITECTURE §2 already allows "one decision about one
bounded set of things, every one of them shown in full". Nothing is granted
for later, and nothing risky rides a group. It is still a new kind of card,
so it is the owner's call (Q1).

### 2. Goals, stage 1 - on Coming up, no AI model (S-M)

**Plain words.** "track: insulate the garage by 1 November" shows on Coming up
with its date. Once a week (your day) it asks "done / still on it / stop". The
briefing gets one line: "Goals due this month: garage (5 weeks)".

**What is current.** OpenAI retired ChatGPT Pulse (overnight research guessed
from your chats) in June 2026 and moved people to scheduled tasks they set
themselves *(search summary)*. Gemini Spark's permissions are "off by
default" and it asks before sending or buying *(search summary)*. Both point
the same way: **goals you set, not goals guessed for you.**

**Where it plugs in.** A kind `goal` (`register_kind(..., has_text=True,
note=...)`); the words live in `schedule.db` like a reminder's; "stop
tracking" is immediate, one goal at a time. The fast path
(`jarvis_quick.match`, `jarvis_quick.py:608`) takes "track: ..." without the
model; the briefing line is built in code (`jarvis_briefing.py`).

**Permission fit.** Goals come from the owner's own words only - never from an
email or a chat Jarvis read. A health or money goal is sensitive: on screen,
not read aloud, generic words on a locked phone. A check-in reads nothing, so
"no card, like a plain reminder" matches the 2026-09-26 decision - but
`register_kind` asks by default, so write that choice down.

### 3. A slower Approve on risky cards (S)

Risky cards (`notice.weight: "heavy"`) keep Approve greyed out for about two
seconds, and until the whole text has been in view. A search summary of
Anthropic's study says people caught a planted dangerous command 13.6% of the
time *(search summary; not in the post read)*. It pairs with round2-trust's
decision ledger (item 8), which counts how fast cards are approved. Stricter
only; both apps; the notification rule (no Approve there) is unchanged.

### 4. Routines compiled to a checked plan (M)

Builds on `future.md` idea 7. What is new is **how a routine is checked**:
- **Compile.** The owner's sentence becomes tool calls, using Ollama's
  `format` schema (ARCHITECTURE §11). Each call is checked against its tool's
  schema before `plan()`, as the tool loop already does. The saved routine
  holds **literal values only**, plus typed blanks like goose recipes'
  `{{ minutes }}` (Apache-2.0, recipe reference read) that only the owner fills
  in ("movie night for 3 hours").
- **Checked by code when saved.** Listed tools only; no routine inside a
  routine; nothing aimed at Jarvis's own windows; locks, doors and other
  `_stands_alone` devices (`jarvis_home.py:184`) marked risky; at most 8 steps.
- **"Try it".** Runs `plan()` and `describe()` and reads each device's current
  state ("living room lights: on, 80%"). Nothing changes.
- **A check after each step**, like goose's `retry.checks`: read the device
  back; if it did not change, stop and say so.
- **Running it.** Say the phrase; the fast path catches it without the model.
  If every step would run without a card when asked on its own (a timer;
  lights with "Lights, plugs and fans without a card" on), the routine needs
  none. Otherwise, one plan card (idea 1).
- **On a timetable** ("weekdays at 7"): the plan card is raised at that time;
  unanswered, nothing happens. A routine that acts never runs by itself -
  Home Assistant's own automations are the place for that.

Inspiration: Home Assistant 2026.7's "purpose-specific triggers" ("you describe
what you want your home to react to", release notes read); Apple Shortcuts'
"Use Model" puts the model *inside* one step of a fixed list *(search
summary)* - the right way round.

### 5. Undo on the card (M)

**Plain words.** Before you approve, each step says how it can be taken back -
"undo: lights back to 80%" (read before acting), "undo: delete the timer",
"undo: remove the added lines (only if the note is unchanged)" - or plainly
"cannot be undone" (a sent email, a shell command). Afterwards, "Undo this
run" lists the reversals on ONE card, because reversing acts too.

**Honest limit.** Claude Code's checkpoints rewind its own file edits but not
what a shell command did *(search summary, docs)*. The same here: **Jarvis can
undo only what its own tools did, and only if nothing changed it since.**
LangGraph's "time travel" (MIT) replays the agent's state, not the world's.
Rollback papers (AgentRewind, arXiv 2608.14380; "Rollback the World",
2609.18304) *(search summary only)*.

**Where it plugs in.** An `undo` line in each step module's `plan()`. The wiki
already keeps `.versions` copies (`jarvis_wiki.py:134`). Runs go on the
owner's undo shelf and "hold" window if their shape fits (unverified, above).

### 6. More "tell me when" sources (S-M each)

Each is another source in `jarvis_tellme.py`: same card, same end date, and a
match still only notifies, in the owner's words.
- **A folder on this PC** ("tell me when a file lands in Scans"). Nothing
  leaves the PC. A look every minute is enough (`watchdog`, Apache-2.0, could
  make it instant). Only a count and the owner's name for the folder are
  shown; a file name is outside text.
- **The calendar** ("tell me when something is added for Friday"), through
  `calendar_read` at tier `auto`, as the briefing reads it.
- **A web page the owner names** ("when this page changes", "when the price is
  under £300") - the changedetection.io pattern (Apache-2.0, README read). It
  fetches the one address the owner typed: **a new named way out of the PC**
  (an ARCHITECTURE §4 row and a `jarvis_reach` row), so your call. Same shape
  as round3-knowledge's news feeds (item 10); decide them together.

Magentic-UI calls this a "Tell me When" task (MIT, 0.1 README read).

### 7. Goals, stages 2-3 (M)

- **Stage 2.** "Help me plan it" drafts at most 7 steps (an 8B model is weak at
  long plans, `future.md`). Each step has one type: *a thing you do* (text), *a
  reminder*, *a search* (its exact words), or *a routine step* (a plan card
  when due). You edit, then accept. **Accepting runs nothing.**
- **Stage 3.** Re-planning ("step 3 is overdue - split it?") on the second
  card's long lane or as a big-model "deep question" (acts on nothing, no card;
  `jarvis_big_model.py`, `JOBS` at `:168`), shown as an **offer** through
  `jarvis_backoff` (a new `OFFERS` kind that asks for nothing, `:163`).
  Magentic-UI's "plan gallery" (README) suggests keeping finished goal plans
  to reuse.

### 8. Night shift - long jobs that read and prepare (M)

**Plain words.** Jobs you queue for the night - research with searches you
already approved, wiki drafts, a goal re-plan, the journal draft - run on the
12 GB card and wait in the morning briefing as "Ready for you". Anything that
would *act* waits for your card in the morning.

**Where it plugs in.** A kind `night` whose `on_fire` takes the next queued
job, on `lane_for` (`jarvis_second_card.py:1250`) or the big model. Each
finished step is written to `schedule.db`, so a restart carries on from the
last one - DBOS Transact's idea (MIT, README read); copy the idea, not the
library (it brings its own cron scheduler). Permissions are frozen when the
job is queued, like the owner's jobs list ("approving something on Tuesday is
not approving it on Wednesday", `ApiModels.kt:567-571`). Each job registers
with Stop everything.

**A clash found in the code.** On standby the second card refuses Jarvis's own
background work (`_BACKGROUND`, `jarvis_second_card.py:1177`; checked at
`:1263`), but the big model has no such flag: "colibri only ever starts for a
job" (`jarvis_big_model.py:1328-1337`). A night job could start the big model
during standby hours. Decide first (Q2).

### 9. Research helper (M-L)

**Plain words.** "Compare these three heat pumps for noise and price, with
sources." ONE card shows the exact search words (up to about six); they go to
your chosen provider; Jarvis writes a comparison table. **Every claim carries
a short quote**, and code checks the quote really is in its source - the same
word-for-word check as round3-knowledge item 1. Unmatched lines say "not checked".

**What is current.** local-deep-researcher (MIT, read; last updated Aug 2025)
loops search, summarise, "reflect on knowledge gaps" - 3 times by default.
Local Deep Research (MIT, read) reports "~95% on SimpleQA" with a 27B model on a
3090 *(claim; not comparable with an 8B model)*. GPT Researcher (Apache-2.0),
STORM (MIT) and open_deep_research (MIT) are the same family.

**How Jarvis's rules change the loop.**
- **Next-round search words come from what was read**, so each round is a new
  card with the exact words (ARCHITECTURE §4). It never loops by itself; at
  night the next round waits for the morning.
- **The model that reads results gets no tools** (the "dual LLM" pattern;
  round2-trust item 11 builds that reader).
- **Whole pages** go beyond today's search lane (words out, short results
  back). Fetching result pages would be a new named way out. Without it, the
  helper works from snippets only, and the card says so.
- **Saving the report to notes** follows outside text, so it is a card.

---

## Not for Jarvis

| Idea | Seen in | Why not |
|---|---|---|
| "Always allow" / "don't ask again" for a routine, goal or plan | Magentic-UI's "how often it asks" *(search summary)*; OpenClaw (round 1) | Invariant 3: a standing grant for future, unnamed actions |
| A model decides which actions need you | Claude Code auto mode: 17% false negatives on real overeager actions *(claim, post read)* | A model approving is an auto-approve. A warning line at most |
| "You always approve this - loosen it?" | Agent UX advice | §12: an offer never asks to trust more (`NEVER_ASKS`) |
| A watcher that acts when it matches | IFTTT, Huginn (MIT) | A standing grant; a match only notifies |
| Goals guessed from email or chats | ChatGPT Pulse (retired) | Owner's own words only |
| Research that keeps searching by itself | Deep-research loops | Words taken from what it read must be on a card first |
| A second automation engine | n8n (Sustainable Use), Node-RED (Apache-2.0), Huginn, Temporal, DBOS (MIT) | One scheduler (§12); each flow is an unnamed way out |
| CaMeL or Dromedary as the runtime | Apache-2.0 / MIT | Research code; Dromedary archived 2026-09-23, "Not to be used in production". Copy the idea |
| Cloud background agents | Gemini Spark (Google Cloud VMs), ChatGPT scheduled tasks | Rule 1 |
| LangGraph as the agent framework | MIT | A large dependency for what the gate and task controls already do |
| Approving a plan's risky step by voice | - | The voice check cannot tell a recording from you (§3) |

---

## Two questions for the owner

**Q1. Plan cards.** A job with several steps could show them all on one card.
Safe steps run on that yes; risky ones ask again when their turn comes.
- **One plan card, risky steps asked again** (recommended)
- **Keep one card per step**

**Q2. Night jobs and standby.** Overnight jobs need the graphics card; standby
frees it.
- **Run night jobs only before standby starts** (recommended)
- **Let them run during standby hours**

Later, not urgent: may the research helper read whole web pages, and is
"tell me when a page changes" wanted (both are a new way out of the PC).

---

## Sources

Read directly (README, LICENSE or page):
[CaMeL code](https://github.com/google-research/camel-prompt-injection) (Apache-2.0) ·
[Dromedary](https://github.com/microsoft/dromedary) (MIT, archived) ·
[Magentic-UI / MagenticLite](https://github.com/microsoft/magentic-ui) and
[its 0.1 branch](https://github.com/microsoft/magentic-ui/tree/magentic-ui-0.1) (MIT) ·
[Anthropic: Claude Code auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode) ·
[goose recipe reference](https://github.com/block/goose/blob/main/documentation/docs/guides/recipes/recipe-reference.md) (Apache-2.0) ·
[Home Assistant 2026.7 notes](https://github.com/home-assistant/home-assistant.io/blob/current/source/_posts/2026-07-01-release-20267.markdown) ·
[local-deep-researcher](https://github.com/langchain-ai/local-deep-researcher) (MIT) ·
[Local Deep Research](https://github.com/LearningCircuit/local-deep-research) (MIT) ·
[changedetection.io](https://github.com/dgtlmoon/changedetection.io) (Apache-2.0) ·
[DBOS Transact](https://github.com/dbos-inc/dbos-transact-py) (MIT) ·
LICENSE files: [GPT Researcher](https://github.com/assafelovic/gpt-researcher) (Apache-2.0),
[STORM](https://github.com/stanford-oval/storm) (MIT),
[open_deep_research](https://github.com/langchain-ai/open_deep_research) (MIT),
[LangGraph](https://github.com/langchain-ai/langgraph) (MIT),
[watchdog](https://github.com/gorakhargosh/watchdog) (Apache-2.0),
[Huginn](https://github.com/huginn/huginn) (MIT),
[Node-RED](https://github.com/node-red/node-red) (Apache-2.0),
[Temporal](https://github.com/temporalio/temporal) (MIT).

Search summaries only:
[design patterns paper, arXiv 2506.08837](https://arxiv.org/abs/2506.08837) ·
[CaMeL paper, arXiv 2503.18813](https://arxiv.org/abs/2503.18813) ·
[AgentRewind, 2608.14380](https://arxiv.org/abs/2608.14380) ·
[Rollback-Induced Reflection, 2609.18304](https://arxiv.org/abs/2609.18304) ·
[Claude Code checkpointing](https://code.claude.com/docs/en/checkpointing) ·
[auto mode default, with the 13.6% figure](https://devops.com/anthropic-makes-claude-codes-auto-mode-the-default-betting-automation-beats-manual-review/) ·
[LangGraph time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel) ·
[OpenAI Agents SDK human-in-the-loop](https://openai.github.io/openai-agents-js/guides/human-in-the-loop/) ·
[ChatGPT scheduled tasks replace Pulse](https://itbrief.com.au/story/openai-expands-chatgpt-scheduled-tasks-with-new-hub) ·
[Gemini Spark help](https://support.google.com/gemini/answer/17094507) ·
[Apple Shortcuts "Use Model"](https://support.apple.com/guide/iphone/use-apple-intelligence-in-shortcuts-iph78c41eaf8/26/ios/26) ·
[DBOS SQLite, June 2026](https://www.dbos.dev/blog/new-in-dbos-june-2026).

Could not check: the owner's `jarvis_undo`, `jarvis_jobs` and `jarvis_hud`
(not in this repository); whether Magentic-UI 0.2 kept action guards and
"Tell me When" (its new README does not mention them); any paper's numbers.
