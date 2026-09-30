# Goals that show progress: design (2026-09-30)

Status: **parts A and B: backend built 2026-09-30 (JARVIS-API §101), screens
next, from the "Slice contract (frozen)" at the end of this file; part C:
backend built 2026-09-30 (JARVIS-API §105), screens next, from the "Progress
contract (frozen)" at the very end.** The owner ticked three things on 2026-09-30
(build queue items 3 and 7, `docs/BUILD-QUEUE-2026-09-30.md`): (A) goal steps
that are locked until the steps or numbers they depend on are done, (B) a
finish-time range on the benchmark chart, (C) an activity heatmap and a
balance chart of the owner's own choosing. Nothing here is built. Section 11
lists what I did not check, and section 10 is the questions for the owner.

## In short

- **A. Step locks.** A step can say "do these steps first". Until they are
  ticked (by hand, or because their number reached its target) the step shows
  greyed. Plain code decides; no SQL is stored or run. Max 7 steps stays.
- **B. Finish range.** A straight line through the recent numbers, drawn as a
  wide dashed band, worded "about N to M weeks". Under 5 numbers it says "not
  enough numbers yet". "Never reached at this pace" is its own answer.
- **C. Heatmap and balance chart.** 12 weeks of days shaded by how much the
  owner did; a radar of axes the owner picks, each against its own target. No
  streak, no red, no single score.
- Everything is drawn by hand (SVG on the PC, Compose Canvas on the phone).
  No outside library. Numbers come from code, never the model.

## 1. What exists today (read from the files, 2026-09-30)

- **Goals** (`backend/jarvis_goals.py`, JARVIS-API §59): `goals.db`, one row
  per goal, `plan` is a JSON list of `{step, by, done}`, at most 7 steps
  (`MAX_STEPS`). `mark_step(goal_id, index, done)` flips one tick, no card.
  `next_open_step` returns the first undone step; the weekly check-in note
  quotes it. The check-in calls no model. Steps are found by position only.
- **Projects** (`backend/jarvis_projects.py`, §88): `projects.db` with
  `projects`, `benchmarks` (`name, kind, unit, better, target, command`,
  owner mark, `auto_cleared`) and `results` (`value, at, source, logged`).
  `GET .../benchmarks/<bid>?points=N` returns dated points oldest first.
  `auto_sensitive()` marks health and money numbers `keep_on_screen`.
- **Charts**: desktop `projects-panel.js chart()` builds an SVG by hand from
  `chartGeometry()`; phone `ProjectsPlate.kt Chart` draws the same on a
  Compose Canvas from `Projects.chartGeometry`. Both are tested against
  `tools/gen_projects_cases.py`, whose `chart_scale()` is the one reference.
- **Neither module puts anything on the event stream** (checked: no publish
  call in either file). Both apps read `/api/goals` and `/api/projects` when
  a screen opens and after their own action. There is no local WebSocket on
  the desktop and this design adds none (see section 8).

## 2. Rules this design keeps

- Numbers shown come from code (`docs/BUILD-QUEUE-2026-09-30.md`). No model
  writes a forecast, a percentage or a shade.
- No streaks, no guilt, no wilting, no red for zero
  (`docs/CRITTERS.md` "never guilt or streaks";
  `docs/CUTTING-EDGE-2026-09-26-round2-personality.md` "Streaks and guilt
  nudges" left out).
- Health and money numbers: screen only. Never read aloud, remembered, sent
  to a web search or a chatbot; hidden under "Hide memory lists and chat
  history" (desktop: the Windows Hello gate Goals already uses).
- No outside JavaScript library on the desktop (no bundler). No stored SQL.
  No new server, port or way out of the PC. Nothing to a cloud lane.

## 3. Part A: step locks

### 3.1 The shape of a step

Today `{step, by, done}`. It becomes:

| Field | Meaning | Old plans |
|---|---|---|
| `id` | short stable name, `"s1"` to `"s9"`, given by the PC | given on first read, by position |
| `step`, `by`, `done` | as today | unchanged |
| `done_at` | when it was ticked (seconds since 1970) or `null` | `null` = "unknown" |
| `needs` | list of step `id`s that must be met first, at most 3 | `[]` |
| `measure` | `null` or `{"project": id, "bench": id}`: the step is met when that number reaches its target | `null` |

Why a stable `id` and not the position: the owner can reorder steps in the
edit box; a `needs` written as "step 2" would then point at the wrong step.

**A benchmark as a prerequisite** is done by giving the prerequisite step a
`measure`, not by a second kind of link. Example: step 1 "Get the 5 km time
under 30 min" has `measure` = the "5k time" benchmark; step 2 "Enter the
race" has `needs: ["s1"]`. This answers the owner's "both": step 1 is met
when the number reaches the benchmark's own target **or** when the owner
ticks it by hand. Hand tick is always the fallback (the benchmark may be
logged late, or the owner may just know).

### 3.2 The rules, all plain code

- A step is **met** if `done` is true, or its `measure` benchmark has a
  target and its latest number has reached it (`better: higher` means
  latest >= target, `lower` means latest <= target). A benchmark with no
  target or no `better` cannot be a `measure`; saving says so in a sentence.
- A step is **locked** if it is not met and any `needs` step is not met.
  Locked steps show greyed, with "after: <the step it waits for>".
- **Reaching a target never ticks the step for the owner.** It shows as
  "reached (number)", counts as met, and leaves `done` and `done_at` alone.
  Only the owner's tap writes a tick (rule 4 in spirit: the app does not
  decide for the owner that something is finished).
- **Ticking a locked step by hand is refused** with a plain sentence ("Do
  <step> first, or tick it here if it is already done."). No "unlock anyway"
  button: it would be a bypass for the one thing the owner asked for.
- **Unticking (Undo of a tick)** clears that step's `done_at`. A later step
  that is already done stays done (nothing cascades); it just shows "after
  <step> (open again)". No card, immediate, like ticking.
- **Cycles**: on save (create, accept, edit) the PC walks the `needs` graph
  with a depth-first search. A step that needs itself, a loop (s1 needs s2,
  s2 needs s1), a `needs` naming a step that does not exist, or more than 3
  `needs` are all refused with a sentence naming the steps. Nothing is
  stored on a refusal.
- **Deleting a step** in the editor removes it from every other step's
  `needs`, and the editor says so before saving.

### 3.3 Does the 7-step limit change?

**No, keep 7** (recommendation, Q1). Reasons: the creativity doc's named
risk is a long plan and an 8B model that is weak at long plans; the drawing
below stays a few rows; cycle checks and screen reading stay trivial. Locks
make a plan more useful at the same length, not longer.

### 3.4 What a lock means for the weekly check-in

`next_open_step` becomes: the first step, in the owner's order, that is not
met and not locked. The note reads as today ("still on track for X?").
If every unmet step is locked (only possible by a hand-unticked
prerequisite), the note says "Waiting on <the first prerequisite that is
itself open>". If a step is met by its number but not ticked, the note says
"<step>: the number reached its target - tick it when you are ready."

One optional **neutral pace line** may be added, for a goal whose next step
has a `measure` and whose forecast (Part B) is a real range: "At this pace,
about 6 to 9 weeks." It is a fact line, never an alert, never in a card or a
notification of its own, absent when the answer is "not enough numbers yet"
or "never reached" (those show on the chart only). It is **left out for a
sensitive benchmark** because the check-in note is shown in Coming up on
both apps.

### 3.5 How it draws, in both apps, without a library

At most 7 nodes with at most 3 links each. That is a list, not a graph
layout problem. **dagre and elkjs are not needed** and are not used
(section 9). Two drawings, the second optional:

1. **Indented rows (the main one).** Steps in the owner's order. A locked
   step is greyed (lower contrast, still readable), with a small padlock
   glyph drawn as text and a line "after: Get the 5 km time under 30 min".
   A met-by-number step shows a target mark and "number reached". Desktop:
   plain DOM rows in `goals.js`. Phone: a `Column` in `GoalsPlate.kt`.
2. **A tiny SVG "shape" (optional, Q2).** Steps as small boxes in columns
   by depth (depth = longest chain of `needs` above it, 0 to 2 in practice),
   short elbow lines between them. Positions come from one function shared
   by both apps and written in the contract file. Screen readers get the
   rows, not the picture (the picture is `aria-hidden`).

Greyed is never the only signal (colour-blind and screen-reader users): the
row also says "locked, after <step>" in words.

## 4. Part B: finish-time range

### 4.1 Where it shows

On the existing benchmark chart, only. No card, no notification, no "goal
is slipping" message (section 9). Not spoken.

### 4.2 The method: a straight line and its honest spread

Choice: **a straight-line fit (least squares) over recent points, with the
range taken from the uncertainty of the line's slope**. Bootstrap (resample
the points many times) is refused here: with 5 to 12 points there are very
few different resamples, it needs random numbers (tests would need a fixed
seed and would still wobble), and it looks more precise than it is. The
straight line needs no numpy: about 25 lines of plain Python, checkable by
hand.

Steps, all in `backend/jarvis_progress.py` (new):

1. Take the last up to 12 numbers from the last 90 days. Convert times to
   days. Need **at least 5 numbers on at least 3 different days spread over
   at least 7 days**; otherwise the answer is `not_enough` ("not enough
   numbers yet", plus "N more needed").
2. Fit `value = a + b * day`. Residual spread `s = sqrt(SSE / (n - 2))`,
   slope error `se = s / sqrt(Sxx)`. Slope range `b +/- t * se` with a
   small fixed table of t-values for 3 to 10 degrees of freedom
   (about the 80% range; the words never say "80%" or "likely" as a
   probability, only "about").
3. Anchor on the **line's own value at the last date** (not the raw last
   point, which is noisy). Days to the target = `(target - anchor) / slope`
   for the low slope and for the high slope; the two give the range.
4. Round outwards: low end down, high end up, to whole weeks, at least 1.
   Under a week: "less than a week". Over 104 weeks: "more than 2 years".

Honesty about tiny data, in the words the screen shows: "A straight line
through your last N numbers. It is a rough guess, not a promise." The range
gets wider automatically when the numbers are scattered.

### 4.3 The answers (one state each, never blended)

| State | When | Words (sketch) |
|---|---|---|
| `no_target` | benchmark has no target or no `better` | "Set a target to see a pace." |
| `reached` | latest already at or past target | "You have reached your target." |
| `not_enough` | under 5 numbers, or too few days | "Not enough numbers yet - 3 more, on different days." |
| `range` | improving line, both ends finite | "About 6 to 9 weeks at this pace." |
| `open_ended` | central line improves, but the slope range includes flat or backwards | "About 6 weeks or more - your numbers are too scattered to say how much more." |
| `never` | central slope flat or moving away from the target | "Not reached at this pace." |

`never` is **its own answer**, never a huge number of weeks and never a
default value. **The argmax pitfall** (reproduced 2026-09-30): numpy's
`np.argmax` on a yes/no array returns 0 when nothing is true, which reads as
"reached on day 0". This design uses a closed-form answer and no
"find the first true" search. Where a search is ever needed it must be
`next((i for i, ok in enumerate(flags) if ok), None)` and `None` means
`never`. The edge-case table (section 7) has a test for exactly this.

### 4.4 Drawing it (chart geometry shared by both apps)

Added to the existing chart, nothing removed:

- The straight line from the first used point to the target, **dashed**.
- A **wide dashed band** around it: a translucent shape between the line for
  the slow slope and the line for the fast slope, from the last date out to
  where they cross the target level.
- On the target line, a bracket from the early to the late crossing, and the
  words beside the chart (not on the picture only).
- The x range grows to the right to fit the band. If the band would need
  more than 3 times the length of the data, it stops at the edge with an
  arrow and the words carry the rest.

The backend sends the numbers (the line's two ends, the band's corner
values, the crossing dates, the state and the words). The apps only map
dates and values to pixels, using a new `forecastGeometry` beside
`chartGeometry`, written the same way in JS and Kotlin and tested against
new `forecast` cases in the projects contract file (section 6). Screen
reader text: the chart's existing summary plus the forecast sentence, e.g.
"5k time: 9 numbers. Latest: 31.2 min. About 6 to 9 weeks at this pace."

### 4.5 Sensitive benchmarks

A health or money benchmark still gets the line and band (they are the
owner's own screen), but with `keep_on_screen` carried over: never in the
check-in note, never in a chat answer, hidden under Hide memory lists.

## 5. Part C: heatmap and balance chart (queue item 7)

Both live in **Brain -> Projects** (desktop: `projects-panel.js`; phone:
`ProjectsPlate.kt`), one small "Progress" section at the top. Not a
floating widget (section 8).

### 5.1 Activity heatmap

- About **12 weeks** of days, Monday first, one column per week, seven rows.
  Cell = one day. Future days are not drawn.
- Shade = **count of things done that day**: steps ticked (`done_at`) plus
  numbers logged (`results.at`, by the date the number is for; a backfilled
  number appears on its own date). Five levels: 0, 1, 2, 3-4, 5 or more.
- **Empty days are neutral**: the same soft outline and surface colour as
  the page, never red, never a cross, never a "missed" mark. One hue, steps
  of lightness, with a text pattern in the tooltip ("3 things on 12 Oct").
- **No streak counter, no "longest run", no "days in a row", no percentage
  of days active.** The only words: "Last 12 weeks: 23 things on 14 days."
- Steps ticked before `done_at` existed have no date and do not appear
  (said in one line on first view; not guessed).
- Each cell has an accessible name; the whole grid is a table with a
  "week of 6 Oct" row header, so a screen reader can walk it.
- Drawing: desktop SVG `<rect>` cells; phone Compose `Canvas` `drawRoundRect`.
  Cell 14 px, gap 3 px; the same geometry function in both apps.
- Sensitive numbers count as anything else here, but only as a count: the
  cell never names the benchmark. Screen-only and hidden under Hide memory
  lists like everything else on the screen.

### 5.2 Balance chart (radar)

- The **owner picks the axes** from their own benchmarks and goals: 3 to 8
  (fewer than 3 is not a shape). Each axis has a label the owner may
  rename ("Fitness", "Garage").
- Each spoke = **that axis's latest number against its own target**, from
  the first number logged to the target: `(latest - first) / (target -
  first)`, kept between 0 and 1, full ring = target reached. A goal axis =
  steps met out of steps. The **labelled value is printed at each spoke**
  ("72.5 of 70 kg", "3 of 5 steps"). An axis with no numbers yet shows a
  dot in the centre labelled "no numbers yet", not a zero, not red.
- **Never one overall score**, never an average, never the area read out.
  (The area of a radar depends on the order of axes; it is not a fair
  total.) A plain list under the picture repeats every axis with its value:
  that is also the screen-reader text.
- Sensitive axes: allowed (the owner chose them), screen-only, hidden under
  Hide memory lists, never spoken, never searched, never sent. The route is
  not a model tool and nothing in `jarvis_agent.py` may import the module
  (a test checks it).
- Drawing: SVG polygon and rings (desktop), Compose `Canvas` path (phone).
  Spoke angles and ring radii are one shared function in the contract.

## 6. Schema, files, routes

### 6.1 Storage

- `goals.db`: **no column change for A**; the plan JSON gains the step
  fields above. Old steps read with defaults; ids are written the next time
  the plan is saved. No migration script, no data lost. (If the Goals
  `project` column from `PROJECTS-DESIGN.md` §1 lands first, it is a
  separate nullable column added by the guarded `ALTER TABLE` used
  elsewhere; nothing here depends on it: `measure` carries its own project
  id.)
- `mark_step` gains `done_at = now` on tick, `null` on untick.
- `projects.db`: one new small table, created if missing:
  `balance_axes (position INTEGER, kind TEXT, project TEXT, ref TEXT,
  label TEXT)`, at most 8 rows. Kind `bench` (ref = benchmark id) or `goal`
  (ref = goal id). Deleting a benchmark or goal removes its axis.
- Privacy of `done_at`: **dates only, no words**. The audit log gets ids and
  counts, never a step's text or a number, as today.

### 6.2 New and changed files

| File | Change |
|---|---|
| `backend/jarvis_progress.py` (new) | pure functions: `step_states()`, `check_cycles()`, `forecast()`, `activity()`, `balance()`; no I/O of its own beyond calling the two stores |
| `backend/jarvis_goals.py` | plan cleaning takes `id/needs/measure/done_at`; `mark_step` refuses locked ticks; `next_open_step` skips locked |
| `backend/jarvis_projects.py` | benchmark GET answer gains `forecast`; axis table |
| `backend/goals.patch`, `projects.patch` | route additions only (regenerate history: `python3 tools/build_patch_history.py` after `git fetch --unshallow origin`) |
| `tools/gen_projects_cases.py` | new `forecast`, `activity` and `balance` cases and their words |
| desktop | `goals.js` (rows, locks), `projects.js` (`forecastGeometry`, heatmap and radar geometry), `projects-panel.js` (drawing), `src-tauri/src/brain/goals.rs` and `projects.rs` (pass the new fields through) |
| phone | `net/Goals.kt`, `net/Projects.kt` (parsers and geometry), `ui/screens/GoalsPlate.kt`, `ProjectsPlate.kt` |

### 6.3 Routes (JARVIS-API sections reserved: 101 for A+B, 105 for C)

**§101 (Goal step locks and finish range)**

| Route | Change |
|---|---|
| `GET /api/goals`, `/api/goals/<id>` | each step also answers `id`, `done_at`, `needs`, `measure`, and computed `state`: `open`, `locked`, `met_by_number`, `done`, plus `waiting_on` (step ids) and `reached_words` |
| `POST /api/goals`, `/accept` | `plan` steps may carry `needs` and `measure`; refusals (cycle, unknown step, no target, more than 3) are `400` with a sentence |
| `POST /api/goals/<id>/step` | `{"index"` or `"id", "done"}`; `409` with a sentence when the step is locked |
| `GET /api/projects/<pid>/benchmarks/<bid>` | gains `forecast: {state, words, weeks_low, weeks_high, line, band, cross_low_at, cross_high_at, used, needed}` |

**§105 (Progress: heatmap and balance)**

| Route | Method | Answers |
|---|---|---|
| `/api/progress/activity?weeks=12` | GET | `{"ok", "days": [{"date", "count"}], "total", "days_active", "words"}` (weeks 4 to 26) |
| `/api/progress/balance` | GET | `{"ok", "axes": [{"label", "kind", "value_words", "fraction" or null, "keep_on_screen"}]}` |
| `/api/progress/balance` | POST | `{"axes": [{"kind", "ref", "label"?}]}` (3 to 8). No card: the owner's own display choice |

All are token + origin like the other routes. `check_parity.py` gets one
line per new route (`ported`), with the two apps' names.

## 7. Test plan

- `backend/test_goal_locks.py`: met/locked/open for each combination; a
  hand tick meets a `measure` step whose number has not arrived; a reached
  number meets it without changing `done` or `done_at`; cycle cases (self,
  two-step loop, three-step loop, unknown id, four `needs`); locked tick
  refused; untick clears `done_at` and leaves a later done step alone;
  deleting a step cleans `needs`; old plan JSON (no ids) still loads; the
  check-in note for locked, all-locked and number-reached cases; no pace
  line for a sensitive benchmark.
- `backend/test_forecast.py`: the edge-case table below, plus determinism
  (same numbers, same words), no `numpy` import, no `argmax` in the file.
- `backend/test_progress_views.py`: heatmap counts by date; empty day is
  count 0 and carries no "missed" word; balance axis math; no streak word
  in any string the module sends (a word list check).
- No-leak test: `jarvis_progress` is not imported by `jarvis_agent.py`, not
  in the tool table, and no sensitive value reaches `jarvis_search` or the
  chat context.
- Both apps: contract tests read `projects-cases.json` (desktop
  `tests/*.mjs`, phone `ProjectsTest` / `GoalsTest`): forecast geometry,
  heatmap cell positions, radar spoke points, the words list, word for word.
  `python3 tools/gen_projects_cases.py --check` and
  `python3 tools/check_parity.py` must be clean.
- Kotlin cannot be compiled here (CI only); Rust checked against the
  Windows target as CLAUDE.md says.

**Forecast edge cases** (better = lower, target 70, one point per week
unless noted):

| Case | Numbers | Expected state |
|---|---|---|
| 0 points | none | `not_enough` (needs 5) |
| 3 points | 80, 79, 78 | `not_enough`, "2 more" |
| 5 points, same day | five numbers on one day | `not_enough` (needs 3 different days over a week) |
| Falling trend, steady | 80, 79, 78, 77, 76 | `range`, about 6 weeks centre; both ends finite |
| Falling, scattered | 80, 76, 79, 75, 78, 74 | `open_ended` or a wide `range`, never a narrow one |
| Flat trend | 75, 75, 75, 75, 75 | `never` |
| Rising when lower is better | 72, 73, 74, 75, 76 | `never` |
| Target already reached | last number 69 | `reached` (no forecast drawn) |
| Never true on a grid | trend crosses nothing in range | `never`, not "0 weeks" (argmax regression test) |
| No target / no `better` | either missing | `no_target` |
| Very slow | 80, 79.99, 79.98, 79.97, 79.96 | "more than 2 years" wording, or `never` per Q3 |

## 8. Both apps, and the questions the owner may ask

- **Parity.** Locks, forecast, heatmap and balance chart are built for
  desktop and phone. Nothing is left one-sided. Goals and Projects are
  already `ported` in `tools/check_parity.py`; new routes get the same.
- **No local WebSocket.** The desktop gets data the way it does today: the
  Rust side calls `/api/goals` and `/api/projects` (and the new `/api/progress`
  routes) and hands JSON to the window. Goals and Projects publish nothing on
  the single `/api/events` stream today, so the panels refresh when opened
  and after the owner's own action. A live refresh on tick or log would mean
  one new event name; not proposed here.
- **A floating widget?** Not proposed. It would need: (1) a decision that a
  widget may show numbers at all (under App lock the desktop widget shows
  only a short title today); (2) the same Hide-memory redaction inside the
  widget; (3) on the phone, a home-screen widget cannot be hidden from
  screenshots the way the app can. Health and money shading on a widget is
  the hardest part. Brain -> Projects avoids all three.
- **Feature audit** (CLAUDE.md, standing): bugs verified against source;
  both apps; same approval model (nothing here needs a card: all are the
  owner's own ticks, picks and reads); same wording set (contract `words`);
  `docs/JARVIS-API.md` §101 and §105, `docs/ARCHITECTURE.md` if a new data
  path appears (none does), `backend/README.md` patch list, and
  `THIRD-PARTY-NOTICES.txt` (nothing to add: no library).

## 9. Ideas turned down, and why

- **React Flow / xyflow.** Needs React and a bundler; the desktop has neither.
  Seven boxes do not need a graph editor.
- **dagre / elkjs.** Layout engines for large graphs. At 7 nodes and depth
  0 to 2 a 10-line depth count does the job. Not needed.
- **cal-heatmap.** No radial or polar mode, needs d3, and looks dormant
  (not re-verified today). A grid of 84 squares is a small loop.
- **Chart.js / d3.** Outside JavaScript, no bundler, and the existing
  charts already work by hand.
- **The wilting / fog biome** (the world gets sad when goals slip). It is
  guilt by another name, and the phone's face shaders have no room: the red
  panda is at 59,426 of 60,000 by the owner's figure (`docs/CRITTERS.md`
  lists 59,693 at one point; not re-measured today).
- **"Goal is slipping" alert cards.** A card for a missed pace is nagging,
  and on tiny data it would often be wrong.
- **Monte Carlo P50/P85/P95.** False precision. Five to twelve numbers do not
  support three percentile lines.
- **A pasted `criteria_eval_sql` idea.** Refused: it stores code as data and
  runs it. Prerequisites are two fixed fields, checked by plain code.

## 10. Owner's questions

**Q1. How many steps may a plan have?** Locks make plans more useful without
making them longer.
- **Keep 7** (recommended).
- Raise to 10.

**Q2. Show the little step diagram as well as the rows?**
- **Rows only for now** (recommended): simplest, easiest for screen readers.
- Rows plus a small diagram.

**Q3. For a target more than 2 years away at the current pace, say...**
- **"More than 2 years at this pace"** (recommended).
- "Not reached at this pace", the same as a flat trend.

**Q4. Should numbers you log for health or money shade the heatmap?**
- **Yes, as a plain count, screen-only** (recommended): the day is shaded, the
  benchmark is never named.
- No, leave sensitive benchmarks out of the heatmap.

**Q5. Add the one neutral pace line to the weekly check-in?**
- **Yes, non-sensitive benchmarks only** (recommended).
- No, the range stays on the chart only.

## 11. Not verified

- Whether the Goals `project` column, `GET /api/goals?project=` and the
  step-benchmark link from `PROJECTS-DESIGN.md` §1 have merged. In this
  checkout they have not: `goals.db` has no `project` column and §88 says
  "still to come". This design does not need them (`measure` carries its own
  project id), but the two would touch the same plan JSON and the same patch
  lines, so whichever lands second must be re-anchored.
- `grep` found no event-bus publish in `jarvis_goals.py` or
  `jarvis_projects.py`; I did not read `jarvis_hud.py` (not in this repo).
- The t-value table and the "3 days over 7 days" minimum are my choice; they
  need trying on real logged numbers on the owner's PC before the words are
  trusted. Nothing has been run.
- Red panda shader size of 59,426 is the owner's figure; `CRITTERS.md` shows
  other numbers from earlier. `tools/shader_size.py` was not run.
- cal-heatmap being dormant and having no polar mode is from memory, not
  re-checked today.
- Kotlin and Rust were not compiled; there is no Android build here, and
  nothing in this document has been built.


## Slice contract (frozen)

Written 2026-09-30, after the backend for parts A and B was built and tested
(`backend/jarvis_goals.py`, `backend/jarvis_forecast.py`,
`backend/jarvis_projects.py`; `docs/JARVIS-API.md` section 101). Two builders
(desktop, phone) build the screens from this alone. **Where this file and
the design above differ, this section wins.** Real answers of the real code,
in named situations, are in `projects-cases.json` (desktop:
`jarvis-desktop/tests/fixtures/`, phone:
`jarvis-client/app/src/test/resources/contract/`; byte-identical, made by
`python3 tools/gen_projects_cases.py`, checked by `--check` and by
`backend/test_projects.py`). Read it before writing a parser.

### What changed from the design text above

- The forecast fields are `low_weeks` / `high_weeks` (not `weeks_low`), and the
  band and line are sent as finished points (below), already stopped at the
  drawing's edge. `forecast` lives in `jarvis_forecast.py`, not
  `jarvis_progress.py` (that name is left for part C).
- The forecast is on `GET /api/projects/<pid>/benchmarks/<bid>?points=N`
  only (any N >= 1), not on the project read or the list.
- Q1 to Q5 use the recommended answers: 7 steps, rows only (no diagram),
  "More than 2 years at this pace.", the pace line for non-private benchmarks.
- There is no route to edit an already-accepted goal's plan (there never was):
  locks and measures are set in the draft, before Accept, through `POST
  /api/goals` and `POST /api/goals/<id>/accept`. No new route exists in this
  slice, so `tools/check_parity.py` needs no new line.

### 1. The step (Goals)

Sent by `GET /api/goals` and `GET /api/goals/<id>` and every goal answer:

```
step = {
  "id": "s1".."s9",              // stable; send it back unchanged on every save
  "step": str, "by": str, "done": bool,
  "done_at": number|null,        // seconds since 1970; null = not done, or unknown
  "needs": [id, ...],            // 0..3 ids of other steps in this plan
  "measure": null | {"project": 32hex, "bench": 32hex},
  // computed by the PC - ignored if sent back:
  "state": "open" | "locked" | "met_by_number" | "done",
  "waiting_on": [id, ...],       // needs that are not met; also present on a "done" step
  "lock_words": str,             // "" | 'after: "Get quotes", "Pick one"' | 'after: "X" (open again)'
  "reached": bool, "reached_words": str,  // "The number reached its target: 29.5 min (target 30 min)."
  "measure_name": str, "measure_gone": bool, "measure_sensitive": bool
}
limits = {"text", "steps": 7, "goals", "by", "needs": 3}
words  = goal_words      // in projects-cases.json too
```

Rules the apps must show, not decide: **met** = `state` in (`done`,
`met_by_number`). **Locked** = `state == "locked"`. An app never works out a
state itself. `met_by_number` is NOT a tick: show it as "reached", keep the
tick button (the owner still ticks it). The tick button of a `locked` step is
shown but disabled with the `lock_words` beside it; if it is pressed anyway
(stale screen) the PC answers 409 (below) and the app shows its `error`.

**Saving a plan** (`POST /api/goals {"text", "plan"}` and `POST
/api/goals/<id>/accept {"plan"}`): send every step as `{"id", "step", "by",
"done", "needs", "measure"}` (a new step: no `id`). The PC answers `400
{"ok": false, "error": <sentence>}` and stores nothing for: itself/unknown/
more than 3/circle needs, and a `measure` for a benchmark that does not exist
or has no target. Show the sentence as is. The editor must, before saving,
remove a deleted step's id from every other step's `needs` and say so; the PC
does not clean it for the app.

**Ticking**: `POST /api/goals/<id>/step` with `{"id": "s2", "done": true}` (or
`{"index": 1, "done": true}`). Locked: `409 {"ok": false, "locked": true,
"error": 'Do "Get quotes" first, or tick it if it is already done.',
"waiting_on": ["s1"]}`. Untick (the Undo) is always allowed: it clears
`done_at` and changes no other step; a later step stays `done` and then reads
`lock_words` = `after: "..." (open again)`. Success answers `{"ok": true,
"goal": ...}` as before. No card for any of it.

**Words** (`goal_words` in the fixture; the apps' own list must equal it key
for key and word for word - `{step}` `{steps}` `{latest}` `{target}` `{name}`
are filled in by the PC, so an app normally shows `lock_words`,
`reached_words` and `error` as sent and needs only the fixed labels):
`locked` = "locked" (the small padlock label next to the step),
`after` = "after: {steps}", `after_open_again`, `reached`, `reached_tick`,
`waiting_on`, `measure_gone` = "The number this step follows is gone - tick it
by hand.", and the refusals. Show `measure_gone` when `measure_gone` is true.

### 2. Goals panels (both apps): what each builds

- **Rows, in the owner's order** (no diagram). Each row: tick control, step
  words, `by`, then one small line: `lock_words` for a locked or reopened
  step; `reached_words` when `reached`; the measure's `measure_name` as "Follows:
  <name>" when there is a `measure`. A locked row is greyed (lower contrast,
  text still readable) with the words "locked" and the `lock_words`; greyed is
  never the only signal. A screen reader hears: "<step>, locked, after: <steps>".
  `measure_sensitive`: hide `measure_name` and `reached_words` under "Hide
  memory lists and chat history" (desktop: the same Windows Hello gate Goals
  uses), exactly as the private lists hide.
- **Needs editor** (in the draft editor, before Accept; not on an accepted
  goal): per step, a "Do these first" picker over the OTHER steps (up to 3;
  the fourth is refused by the PC with the sentence, and the picker should
  stop at 3), and a "Follows a number" picker over the life benchmarks
  (`GET /api/projects` then each project's benchmarks with a `target`).
  Deleting a step removes its id from the others' `needs`.
  Desktop: `jarvis-desktop/src/goals.js` (+ `brain.js`, `src-tauri/src/brain/
  goals.rs` passes JSON through unchanged). Phone: `net/Goals.kt` (parse the
  new fields with defaults, unknown keys ignored), `ui/screens/GoalsPlate.kt`.
- Coming up's check-in note needs no work: the PC sends it whole.

### 3. The forecast (Projects benchmark chart)

`GET /api/projects/<pid>/benchmarks/<bid>?points=N` -> `benchmark.forecast`
(absent on a read without `points`, and from an older PC: draw nothing then):

```
forecast = {
  "state": "no_target"|"reached"|"not_enough"|"range"|"open_ended"|"never",
  "words": str,          // SHOW AS SENT, never rebuild
  "basis": str,          // "" unless range/open_ended: 'A straight line through your last N numbers. It is a rough guess, not a promise.'
  "low_weeks": int|null, "high_weeks": int|null,   // range: both; open_ended: low only (105 = "more than 2 years")
  "over_two_years": bool, "why": ""|"scattered"|"long",
  "used": int, "needed": int,                       // not_enough: how many more numbers
  "first_at","last_at","horizon_at": number|null,   // seconds; horizon = last + 3 x (last - first)
  "cross_low_at","cross_at","cross_high_at": number|null,  // null = past the edge / open
  "line": null | {"from": {"at","value"}, "to": {"at","value"}, "clipped": bool},
  "band": null | {"from": {"at","value"},
                  "fast": {"at","value","clipped"},
                  "slow": {"at","value","clipped","open"}}
}
```

`line` and `band` are non-null only for `range` and `open_ended`. Nothing is
drawn for the other four states; just the `words` (below the chart, where the
"Target" caption is).

**The words, sentence by sentence** (`forecast_words` in the fixture is the
list; the apps show `words`): no_target "Set a target to see a pace."; reached
"You have reached your target."; not_enough "Not enough numbers yet - N more
needed." or "...they need to be on at least 3 different days, spread over a
week or more."; range "About 6 to 9 weeks at this pace." / "About 6 weeks at
this pace." / "Less than a week at this pace."; open_ended "About N weeks or
more - your numbers are too scattered to say how much more." / "...it could
take more than 2 years." / "More than 2 years at this pace."; never "Not
reached at this pace." **`never` is its own answer: never draw or say "0
weeks" for it, never fill a default** (the argmax pitfall).

**Drawing** (`forecast_cases[*].extent` is the worked answer; test against it):

- The chart's existing y-scale rule (`chart_scale`) is unchanged but its input
  becomes: every number, the target, and, when `line` exists, these values as
  well: `line.from.value`, `line.to.value`, `band.from.value`,
  `band.fast.value`, `band.slow.value`. The x range runs from the first number
  to the largest of: the last number, `line.to.at`, `band.fast.at`,
  `band.slow.at` (so the picture grows to the right; never wider than
  `horizon_at`). `tools/gen_projects_cases.py forecast_extent()` is the one
  reference: `{"x": [lo, hi], "y": [lo, hi]}`.
- Dashed straight line: `line.from` to `line.to`.
- Band: a translucent filled triangle `band.from`, `band.fast`, `band.slow`, its
  outline dashed. On the target level a bracket from `cross_low_at` to
  `cross_high_at` when both exist. A `clipped: true` end gets a small arrow
  pointing right; `slow.open` means "no upper end": arrow, no bracket end.
- Colours: the chart's existing accent at low opacity for the band; the target
  line and everything else as today. No red. A health/money benchmark
  (`keep_on_screen`) draws the same, on its own screen only.
- Nothing on the event stream, no notification, no card, not spoken, never
  put into a chat answer.

**Screen-reader text** for the chart = the existing `chart_summary` sentence,
then a space, then `forecast.words` when a forecast exists:
"5 numbers. Latest: 76 min. About 6 weeks at this pace."
(`forecast_cases[*].summary` is the worked answer.) The dashed picture itself is
`aria-hidden` on the desktop and has no content description on the phone.

**Which app builds what.** Desktop: `projects.js` (a `forecastExtent` beside
`chartGeometry`, parsing), `projects-panel.js` (the line, band, bracket, the
words line, the summary), `tests/projects.mjs` (compare with `forecast_cases`).
Phone: `net/Projects.kt` (parse `forecast` with defaults, `forecastExtent`
beside `Projects.chartGeometry`), `ui/screens/ProjectsPlate.kt` (Canvas: dashed
line, band path, bracket, arrow, words), `ProjectsTest.kt` (compare with
`forecast_cases`). Rust `brain/projects.rs` passes JSON through unchanged
(its test already checks every real read is passed on unchanged).

### 4. Not part of this slice

The activity heatmap and the balance chart (part C, queue item 7, section
105); a plan editor for an accepted goal; any new route. The pace line in the
weekly check-in is the PC's and needs no screen.


## Progress contract (frozen)

Written 2026-09-30, after the backend for part C was built and tested
(`backend/jarvis_progress.py`, `backend/progress.patch`,
`backend/test_progress.py`, `docs/JARVIS-API.md` section 105). Two builders
(desktop, phone) build the screens from this alone. **Where this and the design
text above differ, this wins.** The real answers of the real code, in named
situations, are in `progress-cases.json` (desktop: `jarvis-desktop/tests/
fixtures/`, phone: `jarvis-client/app/src/test/resources/contract/`;
byte-identical, made by `python3 tools/gen_progress_cases.py`, checked by
`--check` and by `backend/test_progress.py`). Read it before writing a parser.
Its keys: `words`, `levels`, `shading`, `limits`, `heat_grid`, `radar_constants`,
`radar_worked` (five worked polygons), `heat.{empty,one_day,mixed_levels,
dst_weekend,private_number}` (each a real activity answer plus `rects` and
`size`), `balance.{nothing_picked,three_areas,five_areas_mixed,
target_reached_private,after_a_benchmark_is_deleted}` (each a real balance
answer plus `radar`) and `refusals`.

### What changed from the design text above

- Routes are exactly the two in section 6.3 (`/api/progress/activity`,
  `/api/progress/balance`); the answers carry more than 6.3 lists: every day
  has `col`, `row`, `level` and `words`; the answer has `columns`, `summary`,
  `keep_on_screen`, `hidden_words`. The apps never work a shade, a column or a
  sentence out themselves.
- The heatmap has **no per-day private marker.** A private (health or money)
  number is counted like any other and the day is shaded; the whole answer says
  `keep_on_screen: true` when any private item is in the window. That is the
  owner's answer of 2026-09-30 ("shades a day without naming it").
- A goal axis is steps DONE out of steps (a step met by its number, not
  ticked, is not counted). Goals stay off a chart until accepted.
- A balance chart with fewer than 3 areas left (a benchmark was deleted) keeps
  them, `drawable: false`: show `words` ("Pick at least 3 to see the chart.")
  and the list, no picture.
- Days are the PC's local days (its time zone, with daylight saving for that
  date). A phone in another time zone sees the PC's days, on purpose.

### 1. The JSON (see section 105.1 to 105.3 for every key)

```
GET /api/progress/activity?weeks=12     weeks 4..26 (12 if left out)
{"ok", "available", "title": "Activity", "weeks",
 "from": "2026-07-27", "to"/"today": "2026-10-14",
 "columns": [{"col": 0, "label": "Week of 27 Jul"}, ...],
 "days": [{"date", "col": 0..weeks-1, "row": 0..6 (0 = Monday), "count", "level": 0..4,
           "words": "3 things on 12 Oct" | "Nothing on 12 Oct"}, ...],   // oldest first, ends today
 "total", "days_active", "empty": bool,
 "words": "Last 12 weeks: 23 things on 14 days." | "Nothing here yet. ...",
 "note": "Steps ticked before this was added have no date, so they are not shown.",
 "summary": "Activity, last 12 weeks. <words>", "levels": [...],
 "keep_on_screen": bool, "hidden_words": "Hidden while memory lists and chat history are hidden."}

GET  /api/progress/balance
{"ok", "available", "title": "Balance",
 "axes": [{"label" (<=24), "short" (<=12, with "..."), "name", "kind": "bench"|"goal", "ref",
           "project", "state": "progress"|"reached"|"no_numbers"|"no_target"|"no_steps",
           "value_words": "72.5 of 70 kg", "fraction": 0..1 | null, "keep_on_screen": bool}],
 "drawable": bool (>= 3 axes), "min": 3, "max": 8, "max_label": 24,
 "words": ""|"Nothing picked yet."|"Pick at least 3 to see the chart.",
 "summary": "Balance chart, 3 areas. Running: 12.5 of 20 km. ... No overall score.",
 "choices": [{"kind", "ref", "project", "project_name", "name", "picked": bool, "keep_on_screen": bool}],
 "keep_on_screen": bool, "hidden_words": "..."}

POST /api/progress/balance   {"axes": [{"kind", "ref", "label"?}]}    3..8 items, or [] to clear
  -> 200 the same answer as the GET       -> 400 {"ok": false, "error": <sentence, show as sent>}
```

Parsers ignore keys they do not know and give a missing key its empty value (an
older PC has no such route: a `404` means "draw nothing", the section is simply
not shown). A refused POST changes nothing; keep the editor open with the
sentence beside it. No card ever. Nothing is on the event stream: read when the
Projects screen opens and after the app's own POST; no polling.

### 2. The words

The fixed labels are `words` in the fixture (both apps' own list must equal it
key for key, word for word): `heat_title` "Activity", `heat_under`, `heat_undated`
(shown once, small, under the grid), `balance_title` "Balance", `balance_under`,
`balance_edit` "Choose what to show", `balance_save` "Save the chart",
`balance_clear` "Clear the chart", `balance_rename` "Name on the chart",
`balance_limit`, `no_choices`, `hidden`, `private`. `{weeks}` `{things}` `{days}`
`{date}` `{n}` `{items}` are filled in by the PC: the apps show `words`,
`summary`, `value_words`, the day `words` and the refusal sentence **as sent**,
and never build them. No streak, "in a row", "longest", "missed", percentage,
average or "score" word may appear in an app's own strings either
(`FORBIDDEN_WORDS` in `jarvis_progress.py` is the list).

### 3. Heatmap geometry and colour

- Grid: cell 14, gap 3, so `x = col * 17`, `y = row * 17`, size 14; total
  `width = weeks * 17 - 3`, `height = 116` (`heat_grid`, and `heat.*.rects` are the
  worked answer per day). The grid is drawn in the answer's order; future days
  do not exist, so the last column may be short. Desktop: an SVG `<rect rx="3">`
  per day. Phone: `drawRoundRect` (corner 3 dp) on a Compose `Canvas`; a dp is
  a px in the fixture's units.
- Fill: level 0 has **no fill**, only a 1 px outline in the border-strong token
  over the panel surface: neutral, never red, never a cross. Levels 1 to 4 lay the
  accent over the surface at `shading.alpha` = 0.22, 0.42, 0.66, 0.92 (the
  generator asserts neighbouring steps differ by at least 0.20 so the ladder holds
  in every theme). Desktop: `rgb(var(--accent-rgb) / <alpha>)` on `var(--surface-2)`,
  outline `var(--border-strong)`. Phone: `LocalAccent.current.copy(alpha = ...)` on
  `chrome.surface2`, outline `chrome.hairlineStrong`. These are existing tokens, so
  both themes (light and dark) keep the app's own accent contrast; level 4 is
  the accent itself. No new colour is added and **no red anywhere**.
- A small legend under the grid: five swatches only, no words but the level
  wording from the tooltip. (No "less" or "more" label is required.)
- Tooltip/hover and long-press/tap on a cell: the day's `words`. The line under
  the grid is `words`; `heat_undated` beside it in the small tone. When `empty`,
  show `words` (the empty sentence) and still draw the grid, all neutral.

### 4. Balance geometry and colour

- Box `size` 260 square, centre (130, 130), outer ring radius 80. Spoke `i` of
  `n` points at angle `-90 degrees + i * 360 / n` (first spoke straight up, then
  clockwise). Rings at 25%, 50%, 75%, 100% of the radius (`radar_constants.rings`);
  the outer ring is the **target**. A vertex is at `radius * fraction` along its
  spoke; `fraction: null` puts the vertex at the centre and draws a small hollow
  circle (radius 4) there. Labels: at radius 94 plus the `dy` and `anchor` in
  `radar_worked[*].labels` (`short` text, the value words on a second line in the
  smaller tone). `radar[*]` in every `balance.*` case and `radar_worked.*` are the
  worked answers (rounded to 2 places; tests allow 0.01).
- Colour: rings `var(--border)` / `chrome.hairline`, the outer (target) ring dashed
  `var(--warn)` / `chrome.warnMark` (the same as the benchmark chart's target
  line - amber, not red), spokes `var(--border)`, polygon fill accent at 0.20
  with an accent 2 px outline, vertex dots accent radius 3, labels
  `var(--text-muted)` / `chrome.textMid`, value words `var(--text)` / `chrome.textHi`.
  A private area draws the same as any other on the owner's own screen.
- Under the picture, always: **the list**, one row per axis (`label`, `value_words`,
  and `private` in small type when `keep_on_screen`), then nothing else. **No
  total, no average, no area, no score line.** Rows are not sorted or ranked.
- Editor ("Choose what to show"): every `choices` row as a check row (its
  `project_name` beside the name); up to 8 checked (the 9th is disabled); a name
  field (`balance_rename`, max 24) for each checked row; Save enabled at 3 to 8
  checked, or at 0 checked as "Clear the chart"; the PC's refusal sentence is shown
  as sent. No card.

### 5. Screen-reader text

- Heatmap: a table. Caption = `summary`. One row per week (row header =
  `columns[i].label`, "Week of 6 Oct"), seven cells Monday to Sunday, each cell's
  text = that day's `words` (a day after today has no cell). The SVG squares are
  `aria-hidden`; the table is visually hidden. Phone: the `Canvas` has
  `contentDescription = summary`, and each week is one focusable row with the
  description "Week of 6 Oct: " followed by its days' `words` joined with ". ".
- Balance: the picture is `aria-hidden` / has no content description of its own;
  the list under it is the text, and the figure's caption/label is `summary`.
  A `no_numbers` row reads "<label>: no numbers yet".

### 6. Hide memory lists and chat history

- When the setting is on: an answer with `keep_on_screen: true` is not drawn at
  all; show only `hidden_words` in its place (heatmap and balance separately).
  On the desktop this is the same Windows Hello gate Goals uses to reveal; on
  the phone the section is simply replaced and screenshots are already blocked by
  the same setting.
- The balance picker: a `choices` row with `keep_on_screen` shows "(hidden)" in
  place of its name and cannot be ticked while the setting is on.
- Nothing from either section is ever spoken, put in a notification, sent in a
  chat answer or a search, or written to disk by an app. Not cached.

### 7. Which app builds what

Both live in **Brain -> Projects**, a "Progress" section at the top of the
Projects screen (not a floating widget, not the Home screen).
- **Desktop** builds: `jarvis-desktop/src/progress.js` (parsing, `heatRects`,
  `radar` geometry, the word list), `src/projects-panel.js` (the section and
  the editor), `src/brain.css`, `src-tauri/src/brain/progress.rs` (three pass-through
  commands - read activity, read balance, save balance - with their permission
  files and the allow-list entries), `tests/progress.mjs` (against
  `progress-cases.json`: words, rects, radar, and that no forbidden word appears).
- **Phone** builds: `net/Progress.kt` (parsers with defaults, `heatRects`,
  `radar`, the word list), `ui/screens/ProgressPlate.kt` (hosted at the top of
  `ProjectsPlate`), `JarvisRuntime.kt` and `net/JarvisApi.kt` methods,
  `src/test/.../ProgressTest.kt` (same comparisons).
- **Both:** when each app calls the two routes, flip them in `tools/check_parity.py`
  from `planned` to `ported`. The POST buttons are held on a stale link (rule 4);
  a read shows the last answer with the app's usual stale marking.

### 8. Not part of this slice

A floating widget; a per-day list of what was done (the grid shows counts only,
by design); editing a goal's plan; any streak, goal-slipping alert or "weekly
score"; a radar for a single project's coding tests (a coding benchmark can be
an area only if it is a logged number with a target).
