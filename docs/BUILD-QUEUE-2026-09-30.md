# Build queue, set 2026-09-30

The owner said any rule can be changed if the change is worth it, and ticked
every item below. Each item is designed first (`docs/*-DESIGN.md`), built for
both apps where it makes sense, then given its own feature audit. API section
numbers are reserved here so parallel builders do not collide (next free after
98 = quiz).

| # | Item | Design doc | JARVIS-API § | Needs first |
|---|---|---|---|---|
| 0 | Quiz audit fixes (in progress) | STUDY-FROM-TEXT-DESIGN | 98 | - |
| 1 | Chat tags + sections in History; then "Fork from here" | CHAT-TAGS-DESIGN | 99 | 0 (shared files) |
| 2 | Spending summaries from bank CSV/Excel files | FINANCE-DESIGN | 100 | - |
| 3 | Goal step locks (`needs`) + "about N to M weeks" range + step `done_at` | GOALS-PROGRESS-DESIGN | 101 | - |
| 4 | Review decks (py-fsrs) and typed Spanish practice (quiz modes) | QUIZ-DECKS-DESIGN | 102 | 0 |
| 5 | Retirement what-if calculator | FINANCE-DESIGN | 103 | 2 |
| 6 | Overnight suggested tags, cards only, off by default | CHAT-TAGS-DESIGN | 104 | 1 |
| 7 | Activity heatmap and owner-defined balance chart (hand SVG, no streaks) | GOALS-PROGRESS-DESIGN | 105 | 3 |
| 8 | Galaxy "facts behind this dot" panel; manual "new section here" marker | CHAT-TAGS-DESIGN | 106 | 1 |
| later | YouTube captions (Slice B), cloud "grade this better", Study helper switch (second card) | STUDY-FROM-TEXT-DESIGN | 107+ | 0, 4 |

Standing limits that hold for every item (from the checks of 2026-09-30):
- Numbers shown to the owner come from CODE, never from the model.
- Money and health figures stay on screen: never read aloud, remembered, sent to
  a web search or a chatbot; hidden under "Hide memory lists"; account numbers
  and passwords in a file are hidden before anything is shown.
- No streaks, no guilt, no wilting; an empty day looks neutral.
- No outside JavaScript library in the desktop (no bundler): charts and layouts
  are hand-drawn SVG (phone: Compose Canvas). Nothing stored as SQL to run.
- Nothing to a cloud lane; no bank connections; no new server or port.
- Forecasts say "about N to M weeks" and "not enough numbers yet" under 5 points;
  "never reached" is its own answer (the argmax pitfall was reproduced).

## Owner's answers on the design docs (2026-09-30)

- Spending answers appear **in the chat as a small table**, in both apps (no Spending page yet).
  The question and one sentence are kept in chat history, not the table.
- The heatmap shades a day for a sensitive (health or money) number **without naming it**.
- Other open questions in FINANCE-DESIGN, GOALS-PROGRESS-DESIGN and QUIZ-DECKS-DESIGN use the
  recommended answer (first option) unless the owner says otherwise.

## Second-card list, checked (Gemini, 2026-09-30)

Facts: voice runs on the processor (0 GB of graphics memory), not on the card; lanes are a
second `ollama serve` on its own port pinned by card UUID, not a "worker on port 4720"; the
paths `backend/workers/`, `src/views/*.jsx`, `App.jsx` do not exist; `DeepSeek-R1-Distill-Qwen-8B`
is not a real model name; beautiful-skill-tree is **GPL-3.0** (not MIT; no sound effects);
X6 is MIT (not Apache) and framework-free (UMD `x6.min.js`, 583 KB); emerge is a Python CLI
with static HTML output (no Rust support); ComfyUI is GPL-3.0 (run beside only; no login;
keep on 127.0.0.1 with API nodes off); SDXL-Turbo is a non-commercial licence (fine under rule 5).
Verdicts: "Referee" = a propose-only "looks done - tick it?" card switch on the second card
(only if the owner wants it; the model never writes a tick or VERIFIED); screenshot notes wait for
app-builder milestone C and reuse the existing Pictures model; ComfyUI/badges wait for the "making
pictures" plan (badges for ticked steps only, never streaks); the skill tree is already the
step-locks item; X6 is optional later if the plain rows are not enough.

## Added 2026-09-30 (later)

| # | Item | Design doc | JARVIS-API § |
|---|---|---|---|
| 9 | Topic controls for Jarvis's brain: per-topic mode (Learn and use / Use but don't learn / Learn but don't use / Off), starter topics plus own | TOPIC-CONTROLS-DESIGN | 107 |
| 10 | "Looks done? Tick it?" second-card switch (propose-only, off by default) | BUILD-QUEUE (this note) | - |

Owner's answers on topic controls (2026-09-30): an unsure fact for a "don't learn" topic **asks
with a card** (save under Unsorted, or skip); turning **Health or Money back on raises one card**.
The other questions in TOPIC-CONTROLS-DESIGN use the recommended answer (off-topic facts hidden
with "Show them"; turning a normal topic on is instant; a pinned fact in an Off topic: the topic wins).

## Menu and section visibility (owner, 2026-09-30)

| # | Item | Design doc | JARVIS-API § |
|---|---|---|---|
| 11 | Collapse settings sections; hide whole feature menus; easy unhide, in both apps | MENU-VISIBILITY-DESIGN (to write) | 108 if a backend route is needed |

Owner's answers: **hiding only tidies the menu** - the feature keeps working if the owner asks
Jarvis (nothing is turned off, nothing is lost, no card needed either way). **One "Show or hide
menus" list in Settings** with a switch per menu, a small "N hidden - Show" line where they were,
and "show the Finance menu" by asking Jarvis. Sections can also be collapsed to a single line.
Safety-critical areas can never be hidden: approvals, security and App lock, "What asks first",
connection/stale-link status, crisis help, Stop everything. Deep links (open_settings / open_brain)
to a hidden menu must still work by opening it for that visit.

## Final step: cohesiveness audit (owner, 2026-09-30)

| # | Item |
|---|---|
| 12 | When ALL current work is done and nothing needs the owner's opinion, run a **cohesiveness audit**: how well the new additions (quiz, decks and Spanish practice, chat tags and fork, spending summaries, retirement what-if, goal locks and forecast, heatmap and balance chart, topic controls, menu visibility, referee switch, Galaxy panel, suggested tags) fit into Jarvis as ONE product, and the best way to integrate them. Covers: overlapping or duplicated screens and words, one shared look (palette, icons, wording), navigation and where each thing lives, the menu-visibility groups, settings patterns, the one permission model and scheduler, memory/privacy consistency (screen-only money and health, topic modes), both apps' parity, performance and startup cost, docs (ARCHITECTURE, JARVIS-API, README) and the update guide, and a ranked list of integration fixes. Reported in plain words with choices for the owner as multiple choice. |

## Final sequence (owner, 2026-09-30)

When ALL current work is finished and nothing needs the owner's opinion:
1. Check that nothing conflicts with the two other pull requests: **#38** (merged 2026-09-30 08:08Z:
   "Fill a form, show me the picture, then a separate Submit card", 51 files, branch ccr-31741289-lqx1wr)
   and **#39** (open, being tested, expected to merge in about 45 minutes from the owner's message:
   "Audit fixes: 8 GB extra cards, screen safety, settings, backups, time, update script, phone and
   desktop hardening", 100+ files, branch ccr-a9b557ac-cpnbwx). Re-fetch #39's file list and main's
   head at that time; bring main into this branch (merge, never rewrite history), fix conflicts,
   regenerate fixtures, re-run every check.
2. Create ONE pull request from ccr-b74ab13f-f0mhut into main, and **merge it once all checks pass**
   (explicitly authorised by the owner 2026-09-30; this overrides "no pull request unless asked" for
   this one PR). Follow the repo's PR template if it has one. Do not merge on red checks.
3. Then run a **full bug audit only on the recent changes from these 3 PRs** (#38, #39 and this one).
4. The cohesiveness audit (item 12) still runs when nothing needs the owner.

## GitHub tools: update and add (owner, 2026-09-30)

The owner asked whether Jarvis could use the local models to update GitHub tools
already integrated, or add new repos after testing them first. Chose **"Full: add
and update"**. Not built. Design first (`docs/GITHUB-TOOLS-DESIGN.md`), brought back
before building. Ground rules for the design: nothing installs without a card showing
exactly what changes plus test results; tests run in a throwaway copy first; licence
and maintenance are checked by code, not only by the model; the fetch is a named way
out of the PC carrying no private data (rule 1); the coding step waits for the 12 GB
card. Queued after menu visibility.
Pull request step (owner, 2026-09-30): **yes, open only.** After a tool add or update
passes its tests, one card (full diff, test results, the pull request text, "sends this
to GitHub") then Jarvis pushes a branch and opens a pull request on the Jarvis repo.
Jarvis never merges; the owner presses Merge. Uses a fine-grained GitHub key limited to
that one repo (code write + pull requests only), stored under rule 3. Part of
`docs/GITHUB-TOOLS-DESIGN.md`.

Owner answers, 2026-09-30 (design docs): **Galaxy panel on the PC, plus a plain "People and
things" list on the phone (no map)** - this bends the "no memory graph on the phone" rule for a
list only, hidden under "Hide memory lists". **"New section here" marker: divider only** (Jarvis
still reads the whole chat). Overnight tags: `docs/OVERNIGHT-TAGS-DESIGN.md` (edits ARCHITECTURE §5
in the same PR). GitHub tools: `docs/GITHUB-TOOLS-DESIGN.md` written; its 3 owner questions pending.
