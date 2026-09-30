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
