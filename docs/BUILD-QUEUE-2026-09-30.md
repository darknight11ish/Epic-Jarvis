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
