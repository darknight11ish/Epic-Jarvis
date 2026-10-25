# The education tab — design for the owner's approval

**Status: DESIGN ONLY. Nothing here is built.** This document is written for
the owner to read and decide on. No code, no lesson text and no screen has
been changed to produce it.

**What it is for, in one paragraph.** Jarvis can do about 129 things. There is
already a teaching system — 23 tutorials, 20 questions and answers, and a
record of how far he has read — and it works. What is missing is not lessons.
It is a way in, and a way to know what he has not been taught yet. This
document says exactly what exists today, with numbers taken from the files, and
then proposes the smallest thing that would fix it.

**Where the numbers came from.** Every count below was measured in a worktree
of `origin/main` at commit `64c4580c` (`docs/education-tab-design`), by reading
the files named beside it. Where a number comes from a file, the file is named.
Where it was counted by hand rather than by a tool, it says so.

---

## 1. Short answer for the owner

- **The lessons already exist and they are good.** 23 tutorials, 111 steps,
  20 answers to common questions, written from how the app really behaves. On
  the PC they are one tab in the Brain window; on the phone they are one card
  on the Brain screen. Nothing needs replacing.
- **They are not hidden — they are just not offered.** On the PC the tab is
  visible by default in Brain's own list. The problem is that you have to open
  Brain first, and nothing on a fresh install ever says "there are lessons
  here". On the phone it is three taps into Brain, and it is not offered
  either.
- **Coverage is the real gap.** Of the 129 features in `features.json`, **66
  are taught** by a tutorial step or an FAQ answer and **63 are not**. Whole
  areas are untaught: the Model page, money and health, the home's lights and
  locks, and most of what the Brain's own pages do.
- **"Progress" today is a bookmark, not a measure.** It records which step you
  reached, so you can resume. It does not record that you can *do* the thing,
  and nothing anywhere shows you a total. That is the honest description; the
  design below replaces it with something better rather than a percentage.
- **Two things are actually broken**, and both are small: the PC's "Show me"
  button cannot find three of the ten controls it names, and the phone is
  missing one control name the lessons ask for. Details in §5.

---

## 2. What already exists — the real numbers

This is the part that matters most, because it is what must **not** be rebuilt.

### 2.1 The catalogue, on the PC

The lessons are data, not code, and they live in one place: the backend module
`backend/jarvis_tutorials.py`. Both apps read it over the network, so the two
can never teach different things.

Counted by loading the module and walking `CATALOGUE` (a script, not a guess):

| | Count |
|---|---|
| Tutorials | **23** |
| Steps in total | **111** |
| Of the 23: `section: "both"` (shown in both apps) | **6** |
| `section: "pc"` (PC only) | **11** |
| `section: "phone"` (phone only) | **6** |
| FAQ questions | **20** |
| Steps that name a real control to point at (`point`) | **17 of 111** |
| `where` lines across tutorials and FAQ | **131** (87 carry a `breadcrumb`) |

Steps per tutorial run from **4 to 5**. `docs/TUTORIALS-DESIGN.md` says "4–8
steps and two minutes"; the real range is tighter than that.

### 2.2 The 23 tutorials, and what each one teaches

This is the enumeration asked for. `where` is not repeated here — it is in the
file — but what each tutorial is *for* is.

**Section `both` — shown in both apps (6):**

| id | Title | What it teaches | Steps |
|---|---|---|---|
| `intro` | What Jarvis is | It runs on your PC; private things never leave it; it asks before it acts; what you can ask for; the five rules | 5 |
| `talking` | Talking to it | The talk button; "Hey Jarvis"; what the voice check does and does not prove; Jarvis Live; read aloud vs staying on screen | 5 |
| `asks-first` | What asks first | What a card says; the one list of every action; loosening asks and tightening does not; what never asks; voice never approves | 5 |
| `memory` | What Jarvis remembers | Facts from your own words only; what waits for a yes; Forget vs Erase the words; erasing does not reach backups; "true from" dates | 5 |
| `records` | Records, history and what is kept | Chat history is kept encrypted on the PC; the approval list is read-only; Forget a time frame; the audit log | 4 |
| `when-something-is-wrong` | When something is wrong | An error is a still mark; "Jarvis isn't connected"; the model slow or asleep; stopping mid-action; the self-harm answer | 5 |

**Section `pc` — the desktop app (11):**

| id | Title | What it teaches | Steps |
|---|---|---|---|
| `brain` | Brain, the one settings place | Brain is pages not a list; where memory lives; where the rules live; where the work lives; Settings is a separate window | 5 |
| `focus-sessions` | Focus sessions | Timer plus Quiet; what it watches and never stores; the controls; by voice; how it ends | 5 |
| `timers-reminders` | Timers, reminders and the schedule | "Coming up"; most of it needs no card; what still asks once; a late alarm does not pretend; standby schedule vs Standby | 5 |
| `projects` | Projects, goals and benchmarks | What a project is; benchmarks; goals; the Shareable switch, off by default; what is ready and what waits for the second card | 5 |
| `notes-and-wiki` | Notes and the wiki | The three note apps; when a note asks first; the wiki reads one folder; what the wiki needs to run | 4 |
| `documents-and-search` | Documents, folders and search | You choose the folders; asking about a document; a Notion export; a note after reading asks first | 4 |
| `screens-and-pictures` | Screens and pictures | "Look at this" is one look; "Watch with me" is a session; where it pauses; what is kept; reading pictures and Picture mode; ask for a picture | 6 |
| `home-calendar-email` | Home, calendar and email | Calendar read-only; Home Assistant; reading and sending email; the card says when it read something; the morning briefing | 5 |
| `faces` | The faces | Five faces; what the expressions mean; a voice per face; Animal options; serious moments stay plain | 5 |
| `backups` | Backups and recovery | One locked file; the recovery code is shown once; what a lost code means; restoring and the preview; a limit worth knowing | 5 |
| `pc-at-a-glance` | The desktop at a glance | The HUD; the Jarvis bar; approval cards and the widget; Stop everything; Brain | 5 |

**Section `phone` — the Android app (6):**

| id | Title | What it teaches | Steps |
|---|---|---|---|
| `phone-talking` | Talking on the phone | Hold to speak; slide away to cancel; the words are worked out on the PC; stopping it; it still needs the link | 5 |
| `phone-approvals` | Approval cards on the phone | The card comes to Home; buttons or a swipe; the fingerprint for risky ones; nothing is decided for you; turning swipe back on | 5 |
| `phone-notifications` | Notifications and alerts | An approval arrives as a notification; urgent alerts keep ringing; a late alarm does not pretend; showing them on a watch; letting Jarvis read notifications | 5 |
| `phone-stays-on-pc` | What stays on the PC | The phone is a window not a second Jarvis; speech-to-text stays on the PC; the voice print stays on the PC; screenshots are blocked when they should be; nothing leaves your own devices | 5 |
| `phone-live` | Live on the phone | What Live is; the Quick Settings tile; the headset button; the controls on the Live screen; ending and coming back | 5 |
| `phone-pairing` | Pairing your phone | Both devices on the same private network; scan the code or type the short one; one key per device; what the phone does not do | 4 |

### 2.3 The FAQ

20 questions, in four groups: privacy and rules; everyday use; when something
is wrong; setup and upkeep. Each has an answer and a `where` line. The FAQ is
in `FAQ` in the same module, and its 20 answers overlap the tutorials heavily —
which is why §4 counts a feature as taught if *either* covers it.

### 2.4 What each app draws, in code

**PC.** The panel is `jarvis-desktop/src/tutorials.js` — a Brain tab, not its
own window. `jarvis-desktop/src/brain.html:99` draws the rail button
(`id="tab-tutorials"`, label **"Tutorials and the FAQ"**), and
`brain.html:895-898` is the view (`id="view-tutorials"`, `id="tutorials-root"`).
`brain.js:63` imports it and `brain.js:1257-1263` calls it when the view opens.
Three Tauri commands bridge it — `get_tutorials`, `mark_tutorial`, `get_faq` in
`jarvis-desktop/src-tauri/src/tutorials.rs`, registered at
`src-tauri/src/lib.rs:1095-1097`, granted by the `brain-tutorials` surface.

**Phone.** The plate is
`jarvis-client/.../ui/screens/TutorialsPlate.kt` (the composable is
`TutorialsSection()`), called once, from `BrainScreen.kt:1334-1338`, inside
`if (menus.shows("brain.model.tutorials"))`. The data layer is
`.../net/Tutorials.kt`, the three calls are in `net/JarvisApi.kt:2670-2684`, and
the wrappers in `JarvisRuntime.kt:2134-2153`. `ui/MenuPlaces.kt:145` maps the
plate key `"tutorials"` to the menu id `brain.model.tutorials`.

**Tests that cover it** (all green on `origin/main`):

| Suite | Cases | What it proves |
|---|---|---|
| `backend/test_tutorials.py` | 443 lines, 303 checks (per `docs/HANDOFF-2026-10-05-tutorials-and-ci.md:25`) | The catalogue is well-formed; progress round-trips; a version bump re-offers; skip is reversible; no card is raised |
| `jarvis-desktop/tests/tutorials.mjs` | **27** `check(...)` cases (28 matches for `check(`, one of which is the function's own definition at line 32) | Ordering, resume, wording, the FAQ search, and that every `point` names a declared control |
| `jarvis-desktop/tests/onboarding.mjs` | **18** `check(...)` cases | The separate first-run walkthrough |
| `jarvis-desktop/tests/faq.mjs` | **17** `check(...)` cases | The FAQ's two halves, labels, and that the old Settings card is gone |
| `jarvis-client/.../TutorialsTest.kt` | **13** `@Test` methods | Parsing, resume, wording parity, the `point` resolution |
| `tools/check_tutorial_places.py` | 1 run | Every breadcrumb piece in all 131 `where` lines is a name the apps really have |

**The handoff's own counts have moved.** `docs/HANDOFF-2026-10-05-tutorials-and-ci.md:30`
says `tests/tutorials.mjs` is 17 checks and `:24` says the catalogue held 7
tutorials; the file now holds 27 cases and the catalogue 23. That is expected
drift, not a fault — but it is why every number in this document was
re-measured rather than copied.

### 2.5 The `where`-line checker, and what it can and cannot do

`tools/check_tutorial_places.py` (926 lines) is the guard that was built after
an agent invented three button names in one draft. On `origin/main` it reads
**131 `where` lines, 87 with a breadcrumb, 206 name-shaped pieces**, and every
one is a name the desktop's generated menu catalogue, its HTML headings and
buttons, its JS labels, or the phone's menu catalogue, screen names and plate
titles really contain. It is not a spelling checker: it collects the real names
from the apps' own source and demands an exact match (only case, whitespace and
one trailing `s` are folded).

**It is honest about five things it deliberately does not check** (its own
lines 94-118), and two of them matter here:

1. A `where` line with **no** `->` in it is a sentence, and is not checked at
   all. Its own docstring names the proof: the phrase *"tap to talk, on the
   phone"* was wrong and this check could not see it.
2. It does **not** check that a real name is in the right app or on the right
   screen.

So the checker answers "does this name exist anywhere in either app?" — which
is exactly the mistake it was built for — and nothing more. §9 says what that
means for a bigger curriculum.

---

## 3. What is actually reachable today

The owner's request came from not seeing a tutorial. This section traces the
real path on each app, and says plainly whether it is findable.

### 3.1 The desktop — reachable, one window deep, never offered

The Brain window's own rail is the list of pages. Quoted from
`jarvis-desktop/src/brain.html:55-104`, the rail in order is:

```
Memory · History · Model · Work · Projects · Tutorials and the FAQ · [Advanced → Galaxy, Now, Trust, Watch]
```

`brain.html:98-104` is the Tutorials button. Its own comment at
`brain.html:92-97` is worth quoting in full, because it settles the
"hidden by default" question:

> `<!-- Tutorials is an everyday tab, not one of the four behind`
> `"Advanced", so it sits above that group — and in the same`
> `order as VIEWS in brain.js, which is the order the arrows,`
> `Home and End walk. Landing on a tab this list does not have`
> `is what left the rail with no tab stop at all (d41a0de8`
> `named the view and never drew the button). -->`

And the menu catalogue agrees. `jarvis-desktop/src/menu-catalog.js:1373-1394`
has `brain.tab.tutorials` with `"apps": ["desktop"]`, `"kind": "tab"`, and
`"names": ["tutorials", "tutorials and the faq", "faq", "the faq",
"frequently asked questions"]`. The `"hide": true` field there is **not**
"hidden" — `backend/jarvis_menus.py:89` says `hide: bool = True  # False: never
hideable` — it means *this entry may be hidden by the owner*, and a `False`
would mean the opposite. Nothing is hidden unless the owner hides it
(`jarvis-desktop/src/menu-visibility.js:122-128` only adds an id to the hidden
set when it is actually chosen).

So: **the tab is visible, in the everyday group, and it is the same depth as
Memory.** Three ways in, all real:

1. Open Brain from the tray, click the 6th tab.
2. Press Ctrl+K and type "tutorials" or "help" — the palette resolves those
   names (`menu-catalog.js:2894-2896` maps `"tutorial"`, `"tutorials"` and
   `"tutorials and the faq"` all to `brain.tab.tutorials`).
3. The palette's own **Help** row. `jarvis-desktop/src/palette.js:160` and
   `:346-362` say Help is no longer a Settings card; since 2026-10-08 it opens
   this Brain tab.

**The gap is not reachability. It is that nothing ever says the lessons are
there.** Verified:

- The first-run walkthrough does **not** offer them.
  `jarvis-desktop/src-tauri/capabilities/onboarding.json` grants the onboarding
  window only `theme-read` and `onboarding-surface` — not the tutorial
  commands. `ONBOARDING_VERSION = 2` is in
  `src-tauri/src/commands.rs:633`, and `finish_onboarding` is the only writer
  of that marker (`commands.rs:671`). There is no first-run hook that opens or
  offers the tutorials panel.
- The "Set up Jarvis" card, which is what a new owner meets, offers
  **"Read the FAQ"** — and that button is wired to `goToCard("faq")`
  (`jarvis-desktop/src/first-run-settings.js:494`), which looks for an element
  with `id="faq"` in **settings.html**. That card was removed on 2026-10-08:
  `jarvis-desktop/src/settings.js:952-954` says the "Help and FAQ" card moved
  to the Brain's tab, and `jarvis-desktop/tests/faq.mjs:133` asserts
  *"settings.html no longer has the Help and FAQ card at all"*. So the one
  first-run button that says "here is help" points at an id that no longer
  exists in the document it searches.

**This is the likeliest answer to "why did he not see one."** The lessons are
one click away and the app never mentions them.

### 3.2 The phone — reachable, three taps deep, also never offered

The phone's plate is a card on the **Brain** screen, not a screen of its own:
`BrainScreen.kt:1334` is `if (menus.shows("brain.model.tutorials"))
plate("tutorials", drawn = { true })`. In the shared catalogue
(`jarvis-desktop/src/menu-catalog.js:1890-1909`) `brain.model.tutorials` has
`"apps": ["phone"]`, `"kind": "card"`, and `"parent": null` — so it hangs off
no other menu, which is why it is drawn at the top level of Brain.

The path: **open the app → Brain → the "Tutorials and the FAQ" card.** When
paired. `docs/ANDROID-TOUR-2026-10-09.md:299-310` records that `BRAIN` is one
of the 12 screens replaced by the pairing takeover when the phone is not
paired, and lists the 16 screens: `CHECKS`, `FAQ`, `SECURITY` and `SETTINGS`
are the only four reachable unpaired. **So on an unpaired phone the tutorials
are unreachable entirely.** The FAQ is not: `Screen.FAQ` →
`FaqScreen` (`MainActivity.kt:2865`), and `OpenPlace.kt:124-126` sends "faq" to
`Screen.FAQ`.

Also verified, because it is a plausible place to look: the phone's **Help**
screen and the Brain's tutorial card are two different things. `FaqScreen.kt` is
`Screen.FAQ` ("Help"); `brain.tab.tutorials` is marked `"apps": ["desktop"]` in
the catalogue, so the phone never draws it, and the phone reaches the tutorial
catalogue only through the Brain card.

**A real limitation, stated plainly:** this audit read the Kotlin source. There
is no Android SDK in this container (`CLAUDE.md`, "How the Android apps get
built"), so nothing here was run on a phone. The reachability claim is a
reading of `BrainScreen.kt`, `MenuPlaces.kt` and the catalogue — not a tap on
real hardware.

### 3.3 The four other teaching screens on the phone

The brief listed nine phone files. What each is, and whether it is a lesson:

| File | What it is | A lesson? |
|---|---|---|
| `TutorialsPlate.kt` | The tutorials and FAQ card on Brain | **Yes** — this is the one |
| `FaqScreen.kt` | `Screen.FAQ`, "Help" — the FAQ plus an About card | Yes, the same answers |
| `ReadinessScreen.kt` | `Screen.CHECKS`, "Platform checks" — 15 diagnostic cards | No — it diagnoses, it does not teach |
| `ProgressPlate.kt` | Activity grid and balance chart on Brain | No — a report |
| `StepsPlate.kt` | The tool loop's live steps | No — a status readout |
| `QuizPlate.kt` | Quiz deck block on Brain | No — a revision feature, not a lesson about Jarvis |
| `PcHelpPlate.kt` | Five plain answers about the PC | Adjacent — not the tutorial catalogue |
| `SupportPlate.kt` | "Deal with customer support for me" | No — a feature |
| `MenuVisibilityPlate.kt` | Show or hide menus | No — a setting |

So the phone has **two** teaching surfaces, not nine. Good to know before
anyone proposes adding more.

---

## 4. Coverage against reality — 66 of 129 taught

`features.json` holds **129 entries** in **9 groups**. It exists in three
copies and they are byte-identical (71,222 bytes each; `check_feature_list.py`
asserts it):

- `features/features.json`
- `jarvis-desktop/src/features.json`
- `jarvis-client/app/src/main/assets/features.json`

Each entry has `id`, `group`, `title`, `what`, `where`, `asks`, `limit`,
`surface` and `covers`. **`covers` is not a tutorial link.** It names the menu
or route ids a feature is reachable through — `settings.prompt-coach`,
`brain.tab.tutorials` and so on — and `tools/check_feature_list.py` uses it to
prove no feature is orphaned. **There is no link anywhere between a feature and
a tutorial.** That absence is the machine-detectable shape of §4's gap, and §10
is how this design closes it.

Group sizes: The PC itself 31 · Talking 25 · Memory 17 · Notes and files 14 ·
Home 10 · Phone 10 · Safety 10 · Screen and pictures 7 · Money and health 5.
Surface: `both` 99 · `desktop` 19 · `phone` 11.

**How "taught" was decided.** This is the least mechanical number in this
document and it should be read as such. Each of the 129 features was compared
by hand against the 23 tutorials' step titles and bodies and the 20 FAQ answers,
and marked taught only where a step or answer actually addresses that feature.
A word-overlap script was tried first and thrown away: it passed 115 of 129 by
matching on words like "model" and "settings", which is the same crying-wolf
failure `check_tutorial_places.py` describes at its own line 84. The
conservative hand count is below. **It is a judgement, not a measurement** — the
counts of the tutorials and the features are measurements; the mapping is not.

| | Count |
|---|---|
| Features **taught** (a tutorial step or FAQ answer covers it) | **66** |
| Features **not taught anywhere** | **63** (49%) |

Not taught, by group, with the group's total:

| Group | Untaught | Of |
|---|---|---|
| The PC itself | **15** | 31 |
| Talking | **13** | 25 |
| Memory | **9** | 17 |
| Notes and files | **6** | 14 |
| Home | **6** | 10 |
| Screen and pictures | **4** | 7 |
| Safety | **4** | 10 |
| Money and health | **3** | 5 |
| Phone | **3** | 10 |

**The whole areas that are untaught** — these are the ones worth naming,
because they are not one-off gaps:

- **The Model page, almost entirely (15 of 31 in "The PC itself").** No lesson
  covers Models, Compute, Skills, "Memory on the Model page", Hardware and
  models, The big model (slow), Check for tool updates, What this backend
  supports, Limits and frequency, Hang and crash notes, Starting Jarvis for
  you, The settings file and the logs, or Set up Jarvis. `second-card` is
  mentioned once, inside `projects`, as "waits for the second card".
- **Money and health (3 of 5).** Spending summaries, Retirement what-if, and
  Chatbot keys and a monthly money limit have no lesson. Only "health and money
  facts wait for your yes" and crisis help are covered.
- **The home beyond status (4 of 6 untaught).** Lights, plugs and fans; Locks,
  doors, alarms and covers; Weather and the sky; Save a draft to your Drafts
  folder; Tidy the inbox by voice; News headlines. "Ask how the house is" and
  the calendar/email reads are covered.
- **Two of the ten Safety features.** `trust` (content risk and the audit
  chain), `rush-latch` (a warning when text tried to rush you), plus
  `captcha-handoff` and `app-lock`.
- **Memory's lists (9 of 17).** Covered: the tab, facts saved by itself, facts
  waiting for a yes, the learning switches, the wiki, "what did I believe on
  this date", history, Forget a time frame. **Not covered:** what Jarvis knows
  about you, People and things, Always keep in mind, Between us, Topics, Deep
  questions, Bring in old chats, Chat tags, Galaxy.
- **Everyday controls nobody teaches.** Talk-to-type, Custom voices, Voice
  training, Interrupt Jarvis while it talks, Short answers, Prompt coach,
  Today, Widgets you describe, Background jobs, What Jarvis is doing right now,
  How much Jarvis may interrupt you.

**And the reverse, which matters too.** Several tutorials carry real weight —
`home-calendar-email` maps to 7 features, `talking` and `memory` to 6 each —
while `timers-reminders`, `focus-sessions`, `backups`, `phone-approvals` and
`when-something-is-wrong` map to one each despite being 4-5 steps long. That is
not automatically wrong (a step can be worth having without covering a whole
feature), but it says the curriculum was written area by area rather than
against the feature list.

---

## 5. What "progress" means now

### 5.1 The mechanism, exactly

One JSON file, on the PC, in the config folder: `tutorials.json`
(`backend/jarvis_tutorials.py:49`, `PROGRESS_NAME`, written by `_save()` at
`:1087-1099` via a temp file and `os.replace`, so a half-written file cannot
happen). One record per tutorial:

```json
{"memory": {"state": "in_progress", "step": 3, "version": 1, "at": 1790000000.0}}
```

- `state` is `in_progress`, `done` or `skipped` (`STATES`, line 59). **No
  record at all means not started** — the module's own comment: *"No record at
  all means not started, which is the honest default — a tutorial nobody opened
  is not 'skipped'."* `not_started` is also what clears a record, and it is
  what "Show this one again" posts (`mark()`, lines 1195-1204).
- `step` is where to resume. `one()` at `:1135-1153` sets `changed` when the
  recorded `version` is lower than the catalogue's, and `due` when there is no
  record or the steps changed — so a tutorial whose words were edited is
  offered again rather than counted done on words the owner never read.
- The routes are `GET /api/tutorials`, `GET /api/tutorials/progress`,
  `POST /api/tutorials/progress` and `GET /api/faq`. The POST raises **no
  approval card**, deliberately: *"a card per 'Next' would be absurd"*
  (`:1183`). It is documented as an exception in `docs/JARVIS-API.md` §114 and
  listed as `ported` in `tools/check_parity.py:114`.

`read()` at `:1162-1169` also computes `counts` — `done`, `due`, `total` —
across the tutorials it was asked for. **So a total already exists in the
backend and is already sent to both apps.** What does not exist is anything
that draws it. `jarvis-desktop/src/tutorials.js` draws per-tutorial state
(`stateWords`, `:164-173`) and a `LABELS.due` badge, but no total; the phone's
`TutorialsPlate.kt` likewise.

Answering the brief's four sub-questions directly:

| Question | Answer |
|---|---|
| Is completion recorded? | Yes, per tutorial, as a state plus a step. Not per step. |
| Per app or per device? | **Neither — per PC.** It is one file on the PC, shared. Finishing "Memory" on the phone ticks it on the PC. It is not per person either, because there is one owner. |
| Does it survive a reinstall? | It lives in the config folder (`OPENJARVIS_CONFIG_DIR`), so it survives reinstalling **the apps**. Reinstalling or wiping the PC's Jarvis loses it — unless it is inside a backup, and nothing says it is. |
| Can he see it? | Per tutorial: yes — "Done / In progress / Skipped / Not started", and "Continue at step N". A total: no. Nothing draws `counts`. |

### 5.2 What progress should mean — and what it should not

The mechanism above is a **bookmark**. It is honest and it is useful (resume is
the feature the owner asked for and it works), but it measures *reading*, not
*ability*. Three specific falsehoods a completion model would tell him:

1. **"Done" is set by pressing Next on the last step.** `nextIndex()` in
   `tutorials.js:143-144` returns null past the end, and that null is what marks
   it done. Pressing Next five times marks a tutorial done without reading it.
2. **A `skipped` tutorial and an unopened one look the same in a total.** The
   backend keeps them apart (`not_started` vs `skipped`) and the app shows them
   apart; any "X of 23" figure would destroy that distinction.
3. **Reading a lesson is not knowing how to use the thing.** This is the same
   failure the project already refuses elsewhere: `CLAUDE.md` records that
   *"BLOCKED and NOT-TESTABLE are never counted as passes"* and that only a
   feature driven on real hardware is a PASS. A "100% complete" badge earned by
   clicking Next is exactly the claim that rule exists to stop.

The research points the same way. Mastery-based schemes that reward *time in*
rather than *demonstrated outcome* are documented to invite procrastination
rather than learning ([Mastery Learning in CS1 — An Invitation to
Procrastinate?](https://dl.acm.org/doi/pdf/10.1145/3430665.3456321)), and
measures of self-assessment diverge from demonstrated mastery — learners mark
themselves competent well before they can do the thing ([Measuring Student
Self-Assessment against Viva-Demonstrated Mastery in a Large First-Year
Programming Course](https://arxiv.org/html/2609.38951v1)). Reward systems that
sit *outside* the activity are the ones shown to undermine intrinsic motivation
([Reward Undermines Intrinsic
Motivation](https://link.springer.com/content/pdf/10.1007/978-3-032-26816-7_21.pdf));
what supports it is autonomy, competence and relatedness
([a heuristic design toolkit for web conferencing software based on
self-determination
theory](https://www.sciencedirect.com/science/article/abs/pii/S0920548923001125)).

### 5.3 The proposed progress model

**One word, then four states, then one number that is allowed to be small.**

1. **What a lesson records does not change.** `state`, `step`, `version`, `at`
   in `tutorials.json` stays exactly as it is. Nothing already written breaks,
   nothing already recorded is lost, and the phone and PC stay in step.
2. **A lesson can be *used*, not only read.** The catalogue grows one optional
   field on a tutorial: `try` — the one real action the lesson is about, named
   the way `point` already names a control, plus the app's own way of noticing
   it happened. Examples: *send one message in the Jarvis bar*; *decide one
   approval card*; *make one backup*. The app sees it because the app is
   already doing the thing.
3. **A new state, and only one: `used`.** A tutorial is `used` when the owner
   has read it **and** the thing it teaches has actually happened — not
   simulated, not clicked through, actually done on the running app. A lesson
   with no `try` can never reach `used`; it can only reach `done`. That is
   deliberate: it keeps the state honest instead of universal.
4. **The one number is "things you have not met yet", and it counts down.**
   Not a percentage, not a bar to fill. The page says: *"You have met 66 of the
   129 things Jarvis does. 63 to go — 12 of them are behind the second
   graphics card."* It is derived, not stored, and it never grows when he
   learns something new.
5. **Nothing is lost by skipping.** A `skipped` lesson counts as *met and
   declined*, and the page says so in those words. That is information, not a
   failure mark.
6. **A lesson is re-offered when its words change** — already built
   (`changed_since` / `due`). Keep it. An `used` record whose tutorial's version
   rose goes back to `done`, not to `used`, because the words he demonstrated
   it against are not the words on screen any more.

### 5.4 What I would deliberately not build

Each of these is refused for a reason, not for taste.

| Not built | Why |
|---|---|
| **A completion percentage** | It rewards skipping. A percentage is the number that goes up fastest by clicking Next through the shortest lessons, and this project already refuses to count an unreached row as a pass. |
| **Streaks, and "don't lose your streak"** | A streak is pressure with a deadline attached. The owner is one person teaching himself about his own tool; there is no third party to be accountable to, and a broken streak is a small punishment for using his own software less. Reward design outside the activity is what the research links to lost intrinsic motivation. |
| **Badges for clicking** | A badge for "opened the tutorials page" teaches nothing and is a lie about what he can do. |
| **An interruption nudge** — "you haven't finished Memory" | The tutorials' own design already decided this: the intro is *offered once* and never a modal, and *"nothing else ever pops up"* (`docs/TUTORIALS-DESIGN.md:174`, and its §6 question 2). That stands. |
| **A leaderboard, sharing, or anything that leaves the PC** | There is nobody to share with, and rule 1 keeps the owner's learning about himself on his own machine. |
| **Timing how long he spends** | It converts a lesson into a task, and it measures the wrong thing. |
| **Locking a lesson behind another one** | He built this tool. Gating his own documentation is a strange way to say so. See §7 for the ordered path, which *suggests* order without enforcing it. |

**Engagement, honestly, is not the problem to solve.** The ethos here is
already plain: no dark patterns, no fake urgency, no pressure. The literature on
ethical persuasive design says the test is whether the design serves the user's
own goal or the system's
([Designing Ethical and Trustworthy Persuasive
Technologies](https://dl.acm.org/doi/fullHtml/10.1145/3701571.3703385);
[Exploring Ethics and Trust in Persuasive
Technologies](https://open.library.ubc.ca/media/download/pdf/24/1.0449435/3)).
The owner's goal is *"know how my own tool works"*. So the design's job is to
make the lessons **findable and honest**, and then get out of the way. If it has
to be made engaging, it is the wrong design.

---

## 6. Both apps — what each teaches, and why

The split already exists and is already right. `section` is `pc`, `phone` or
`both`, and `SECTIONS = ("pc", "phone", "both")` in the module. This design
keeps it and adds no new split.

**Stated rule for this feature:** *the lesson about a control lives on the app
that owns the control.* A PC hotkey is taught on the PC; Android's notification
shade is taught on the phone; anything about what Jarvis knows, remembers or
decides is taught on **both**, because it is the same on both and it is the
PC's answer either way.

**One exception, and it is the phone being deliberately limited.** The phone
teaches *what it does not do* (`phone-stays-on-pc`, 5 steps: no speech-to-text,
no voice print, no memory copy, screenshots blocked, nothing public). It is a
lesson whose whole content is a limitation. That is the honest shape: the phone
is a window, not a second Jarvis.

**What this needs in writing.** Per `CLAUDE.md`'s audit rule, a one-sided
decision needs a reason in `docs/ARCHITECTURE.md` §8, "One-sided on purpose"
(which begins at `ARCHITECTURE.md:2093`), and `tools/check_parity.py` must
agree. It already does: the three routes are `ported`
(`check_parity.py:113-115`), and `check_parity.py` exits 0 on `origin/main`.

**The one asymmetry this design proposes to keep, and to write down:**

> **The education tab is a PC-side place with a phone-side reader.** The
> curriculum, the ordering, the "not met yet" count and the per-lesson `try`
> wiring are the desktop's; the phone reads the same catalogue, shows the
> `phone` and `both` sections, and records progress through the same two
> routes. The phone does not get its own curriculum editor, its own ordering,
> or a way to mark a `try` it cannot observe.

The reason is a standing limit, already in `CLAUDE.md`: the phone is a remote,
not a second brain — it renders, it decides one thing at a time, and it does not
hold its own copy of state. A curriculum is state. If the owner approves this
design, the paragraph above goes into `docs/ARCHITECTURE.md` §8 verbatim and
`check_parity.py` gets no new route (the two existing ones already carry it).

**One caution on `try` and the phone.** A `try` the phone cannot observe must
not be shown as something to do there, or the phone will show a control that
never lights up. The mechanism already exists and should be reused unchanged:
`point`'s per-app `null`, which the design note calls *"the mechanism that stops
a phone user being told to press a hotkey"* (`docs/TUTORIALS-DESIGN.md:406`).
`try` gets the same shape: `{"desktop": "...", "phone": null}`.

---

## 7. A beginner's path through 129 features

Handing anyone 129 things is not teaching. The order below is **suggested, not
enforced** — nothing is locked (§5.4), and every lesson stays openable in any
order. What the path actually does is decide what the **education tab puts
first**, and what it does not mention until it is relevant.

**Stage 0 — "it is on and it is mine" (before anything else, ~5 minutes).**
What Jarvis is, where it runs, and the five rules. This is `intro`. Nothing else
makes sense first, because everything else assumes he knows his words stay on
his PC.

**Stage 1 — "I can use it" (the first week).** The things he will touch every
day, in the order he will touch them:

1. `talking` — the three ways in, and what the voice check does and does not prove.
2. `asks-first` — why it keeps asking. This is the lesson that removes
   frustration; it should come before anything that raises cards.
3. `memory` — what it learns, and how to take it back.
4. `pc-at-a-glance` — which window is which, and the key that stops everything.
5. `timers-reminders` — the most-used feature that needs no approval.

**Stage 2 — "it is set up the way I want" (~the second week).** Where things
live, so he stops hunting:

6. `brain` — Brain is pages, and Settings is separate.
7. `faces` — how it looks.
8. `records` — what is written down and how to see it.
9. `when-something-is-wrong` — the three things he will actually see.

**Stage 3 — "the parts I have switched on".** Each lesson appears when its
feature is on, not before. This is where §4's 63 untaught features live:

10. `notes-and-wiki`, `documents-and-search`, `screens-and-pictures` — once he
    has added a folder or a note app.
11. `home-calendar-email` — once an account or Home Assistant is connected.
12. `projects`, `focus-sessions` — the work features.
13. `backups` — once he has something he would hate to lose. Before that it is
    abstract.

**Stage 4 — the phone.** Only once it is paired, because before that most of
the phone's screens do not exist for him (`ANDROID-TOUR-2026-10-09.md:299-310`):
`phone-pairing`, then `phone-talking`, `phone-approvals`,
`phone-notifications`, `phone-stays-on-pc`, `phone-live`.

**The lessons that can wait, and why.** The 15 untaught "PC itself" features
are mostly *setup* and *diagnosis* (Compute, Hardware and models, The big
model, What this backend supports, Limits and frequency, Crash notes, Starting
Jarvis for you). They matter when something is wrong or when he wants to change
the hardware — not on day one, and teaching them early would be 15 lessons
about a machine he has not used yet. Money and health is the same: spending
summaries and retirement are relevant when there is a reason to look.

**How someone who is not a beginner skips ahead.** Four ways, all cheap:

1. **The list is not a wizard.** Every lesson is openable from the tab, in any
   order, today. Keep that. The `orderedPath` is a suggested sequence drawn
   *above* the full list, never a gate in front of it.
2. **"Already know this" on each lesson.** One control, next to "Show this one
   again", that writes `skipped` with a `skip_reason: "knew it"`. It then reads
   as *met and declined* and stops appearing in "not met yet". Honest, and one
   click.
3. **A search box across the curriculum.** `tutorials.js` already has a
   searchable FAQ (`LABELS.search`, `:339`); the same input searches step
   titles and bodies, so "how do I stop it" finds it without knowing which
   lesson it is in.
4. **The count is a jump list, not a score.** "63 to go" opens the list it is
   counting, filtered, so the number is a door rather than a nag.

---

## 8. How a new feature gets a lesson — so this does not rot

`CLAUDE.md` already makes every new feature carry its own audit, without being
asked. This design attaches the lesson to that audit rather than creating a
second ritual. **Three lines, in three places that already exist:**

1. **A new feature must carry either a lesson or a written reason there is
   none.** The audit's existing third part ("Fit with what is already there")
   already asks whether docs were updated. This adds one item to it: *which
   lesson teaches it, or why teaching it is not useful.* Many honest answers
   are "none" — a diagnostic card, a settings row, a developer tool. What is
   not an answer is silence.
2. **The link is machine-checkable, and that is the point.** A feature's
   `covers` list already names the menus and routes it is reachable through. It
   gains the lessons that teach it, in the same list. `tools/check_feature_list.py`
   already proves every `covers` id is real and that no feature is orphaned
   (its rule 1 and rule 2, quoted in §4), so a lesson id in that list is checked
   by machinery that is **already running in CI**. A new feature with neither a
   lesson nor an exemption becomes a red check, not a note nobody reads.
3. **The exemption is a list with reasons, like every other one here.** The
   project's own pattern, used at least four times (`INTERNAL` in
   `check_feature_list.py`, `PHONE_LACKS` in `check_registry_phone.py`,
   `KNOWN_DRIFT` in `check_tutorial_places.py`, the never-hideable list in
   `jarvis_menus.py`): a short list, each entry with a reason, printed on every
   run, and a stale entry is itself an error. Reuse it. It cannot quietly absorb
   a real gap, because an entry that *stops* being needed fails the check.

**The thing that makes this stick, and the thing that does not.** Writing a
rule in a document does not make it stick — `CLAUDE.md`'s own history records a
"not yet built" queue that outlived the build, and `docs/HANDOFF-2026-10-05`
records ten tutorial steps that sent the owner to things that do not exist
because the reason for suppressing them had expired. What does stick is a
checker that runs on every pull request. So the goal is: **the lesson link is in
`check_feature_list.py`, and the curriculum is in `check_tutorial_places.py`.**

---

## 9. Does the existing checker carry a bigger curriculum?

**Partly. It is the right tool and it needs help in three places — one of which
is already failing.**

### 9.1 What it would carry well

A bigger curriculum multiplies exactly the risk it was built for: a `where`
line naming a name that does not exist. 131 lines today, 206 judged pieces; at
three times the size it reads roughly 400 lines and 600 pieces and costs
nothing (it is a few seconds). Its anti-crying-wolf design is sound and should
not be touched: exact matching after normalisation, no substring search, no
fuzzy match, and the rejected-set measured and written down (its own lines
84-92).

### 9.2 Where it cannot carry the load

**(a) 44 of the 131 `where` lines are unjudged, and the most confident mistakes
live there.** 87 of 131 carry a breadcrumb; 44 do not, and a line with no `->`
is skipped entirely. The checker's own docstring names the proof and the harm:
*"a wrong name written that way — 'tap to talk, on the phone' — is not caught by
this check."* It also does not check that a real name is in the right app. So it
catches *invented names in breadcrumbs* and nothing else.

**(b) It has no notion of a `try`.** §5.3's `try` field names a real action, and
nothing would check that the action is one the app can actually observe. An
invented `try` is the same class of lie as an invented button, one level up: not
"that button exists" but "we will notice when you use it".

**(c) It cannot see inside a lesson's prose.** A step's `body` is free text. If a
step says "click Approve on the card" and the card's button is now called
something else, no check in this repository can see it — `body` is not read by
any checker. Today that is a small exposure across 111 steps.

**And one thing is already failing, which is the evidence for all three.** The
phone's `CONTROL_POINTS` registry (`jarvis-client/.../net/Tutorials.kt:175-182`)
declares **six** controls: `approval-card`, `talk-button`, `pairing`,
`notifications`, `live-tile`, `phone-pc-only`. The catalogue asks the phone to
point at **`asks-first`**, twice — `intro` step 2 and `talking` step 1 — and
`asks-first` is **not in the phone's registry**. On the desktop the equivalent
mismatch is caught by `jarvis-desktop/tests/tutorials.mjs:175-199`, which reads
the real catalogue and asserts every `"desktop": "..."` name is declared. The
phone's own `TutorialsTest.kt:197-233` checks that test's **own inline fixture**
(`"""{"id": "talking", ...}"""`), not the real catalogue, so the real catalogue
can drift from the phone's registry and nothing fails. `tools/check_tutorial_places.py`
does not look at `point` at all — it reads `where`, `CATALOGUE` and `FAQ`, and
its docstring's list of what it checks does not mention `point`.

That is **one real defect**, and it is exactly the one-sided gap `CLAUDE.md`'s
audit rule is about. It is found by reading two files and comparing; it is
reported here, not fixed, because this document is a design.

**(d) The desktop's "Show me" cannot reach three of the ten controls it names.**
This one is a second real defect and it needs care, so here is the evidence.
`CONTROL_POINTS` in `jarvis-desktop/src/tutorials.js:88-104` has five
`{ selector }` entries pointing at this document:

```
"prompt-field":    { selector: "#prompt-field" },
"approval-card":   { selector: "#approval" },
"brain-memory":    { selector: "#view-memory" },
"brain-tutorials": { selector: "#tutorials-root" },
"brain-about":     { selector: "#memory-about" },
```

`pointAt()` (`:234-249`) does `doc.querySelector(entry.selector)` on the
document the panel is drawn in. The comment at `:89-90` says *"This window - the
Jarvis bar (index.html), which is where the Brain panel and this panel both
live."* **But the Brain panel is drawn in `brain.html`.** `brain.html:1022` is
`<script type="module" src="brain.js">`, and `brain.js:63` imports `tutorials.js`
and `brain.js:1262` calls `showTutorials($("tutorials-root"))` — and
`id="tutorials-root"` is in `brain.html:898`. Searched across
`jarvis-desktop/src/*.html`:

- `id="prompt-field"` is in **`index.html:80`**
- `id="approval"` is in **`index.html:653`**
- `id="view-memory"`, `id="memory-about"` and `id="tutorials-root"` are in
  **`brain.html`**

So for `prompt-field` and `approval-card` — the two most-reached controls in the
whole curriculum — `querySelector` on the Brain document finds nothing and
`pointAt` returns `LABELS.noPoint` ("Nothing on this screen to point at for this
step"). The tutorial's own design note lists the desktop's controls as `#prompt`
and `#approval` against "the prompt field and the palette" and "the approval
card", so these are the intended showcase cases
(`docs/TUTORIALS-DESIGN.md:419-427`).

Why no test caught it: `jarvis-desktop/tests/tutorials.mjs:201-221` builds a
`markup` string by **concatenating `index.html` and `brain.html`** and then
asserts `markup.includes('id="prompt-field"')`. It proves the id exists *in one
of the two files*; it cannot tell that it is in the wrong one. The check's own
name — *"a control in this window is a selector that really matches the
markup"* — is the thing it does not establish.

`{ file, id, label }` entries are handled honestly: `pointAt:238` returns
"other window" rather than pretending. So the fix is the existing pattern, not a
new one — `prompt-field` and `approval-card` should be declared the way
`hotkeys`, `faces` and `hud-talk` already are, or moved to a window that can
reach them.

**I could not verify the runtime behaviour**, and I will not overstate it: this
container has no built Jarvis desktop app and no Windows GUI session to click
in, so the claim is a reading of `brain.js`, `brain.html`, `index.html` and
`tutorials.js` — the code paths and the DOM each one runs against. What I can
say without qualification is the file-level fact: those two ids are not in
`brain.html`. **The owner can settle it in ten seconds**: open Brain → Tutorials
→ the intro's step 4 ("Things you can ask for today") and press **Show me**. If
it says *"Nothing on this screen to point at for this step"*, the fault is real.

### 9.3 What the checker needs, in order of value

1. **A `point`/`try` registry check that reads the REAL catalogue on both apps.**
   The desktop already has it; the phone needs the same check reading
   `jarvis_tutorials.py` rather than an inline fixture. This is the defect in
   §9.2(c) and it is about twenty lines.
2. **The "same document" check for `{ selector }` entries.** One line of the
   test changes from one concatenated `markup` string to a per-file map: a
   selector that lives in `index.html` is only valid if the panel is drawn
   there. This is §9.2(d).
3. **Extend `check_tutorial_places.py` to read `body`, but only for control
   names it can be sure about** — a quoted control name, a `#anchor`-shaped name,
   or the same breadcrumb shape it already judges. **Do not** widen it to match
   names inside sentences: its own measurement (14,287 quoted strings in the two
   apps) shows that set swallows real drift, which is the failure it must not
   have. If it cannot be done without crying wolf, do not do it — that is this
   checker's own stated standard, and it is the right one.

**What should not change.** The `KNOWN_DRIFT` pattern — a keyed list, each entry
with a reason and a fix location, printed on every run, stale entries an error —
is exactly right for a bigger curriculum and should be used more, not replaced.

---

## 10. Honesty — teaching "built but off"

Jarvis ships features that are off by default, and at least one that is
measured as not proven better. A lesson that implies otherwise is a lie in the
most trusted voice the app has. Four rules, and where each is already written
down:

1. **A lesson says the switch's real state, in the present tense.** Not "you can
   turn on X" but "X is off until you turn it on, here". The catalogue already
   does this well in places — `projects` step 5 is *"What is ready, and what is
   still coming"*, and `screens-and-pictures` step 5 says Picture mode *"is off
   by default"*. That is the register to hold.
2. **"Built but off" and "not built" are different sentences, and both are
   allowed.** `screens-and-pictures` step 5 already models it: *"The fuller
   picture understanding is still coming, and it waits for the second card to be
   measured."* The launch-video rule states the same distinction —
   *"Mark anything built-but-off as 'ready' and anything designed-but-not-built
   as 'next'"* (`CLAUDE.md`).
3. **The second card's lane gets one honest line, everywhere it comes up.**
   `CLAUDE.md`: *"The second card is installed but its features are not
   measured"* and *"do not switch a feature on until that feature is measured;
   every feature that uses the second card keeps its own switch, off until the
   owner turns it on."* A lesson about the wiki, picture understanding, the
   long-context lane or "Jarvis writing code by itself" must carry that
   sentence, because all four wait on it.
4. **A feature measured as not proven better says so in the lesson.** RapidOCR
   is the case the brief names. A lesson must not say it is better, and must not
   quietly omit that it was measured — the honest sentence is short: *"this was
   measured against the built-in reader, and it was not clearly better; it is
   available, not recommended."* **I could not verify RapidOCR's measurement
   numbers from this worktree** — I did not find the measurement document, and I
   am not going to quote a figure I have not read. Whoever writes that lesson
   should take the sentence from the measurement itself.

**A fifth rule, about the curriculum rather than a feature.** §7's "63 to go"
must count only features that are *on*, or say how many of them are off. A
number that includes features the owner has deliberately not enabled is a
number that nags him about his own choices.

---

## 11. Accessibility

Not an afterthought here, because the phone already treats it as a
requirement and the desktop mostly does:

- **Every lesson is reachable by keyboard.** The Brain rail is a real tablist
  (`role="tab"`, `aria-controls`, `tabindex` managed —
  `brain.html:56-104`), and `brain.html:92-97` records that the rail order
  exists so the arrow keys, Home and End walk it. A new education tab must be
  in that list, or it will be the exact bug that comment describes
  (`d41a0de8`: "named the view and never drew the button").
- **The phone's plates use headings, not styled text.** `TutorialsPlate.kt:201`
  is `Kicker(Tutorials.FAQ_HEADING, Modifier.semantics { heading() })`. Keep
  that idiom for the new controls.
- **No colour-only meaning.** The `point` highlight is a class plus a
  `scrollIntoView`; it must not be the only signal that a step has a target —
  the "Show me" button's presence is the text signal, and that is correct today.
- **Plain words, short sentences, jargon explained on first use.** This is
  `CLAUDE.md`'s "Explain things simply", and it is a content requirement on
  every new lesson, not a style note.
- **A lesson states its own length.** `minutes` is already in the catalogue and
  already drawn. Keep it.

---

## 12. The smallest useful slice

What I would build first, in order, each step useful on its own. Roughly in
dependency order — **not** the order of the sections above.

**A. Say the lessons exist (highest value per line of code).**

1. Fix the first-run card's **"Read the FAQ"** button
   (`first-run-settings.js:494`): `goToCard("faq")` looks for an id that no
   longer exists in `settings.html`. Point it at the Brain's Tutorials tab, the
   way the palette's Help row already does.
2. Add **one line** to the "Set up Jarvis" card: *"There are lessons for every
   part of Jarvis in Brain → Tutorials and the FAQ."* A sentence, not a button
   that opens a new window.

**B. Fix the two defects, because a lesson that lies is worse than no lesson.**

3. Bind **`asks-first`** in the phone's `CONTROL_POINTS`, and add the
   phone-side check that reads the real catalogue (§9.2(c)).
4. Declare `prompt-field` and `approval-card` the way `hotkeys` and `faces`
   already are, or move them to a reachable window — and change
   `tests/tutorials.mjs:201-221` to a per-file map so it can tell the two
   documents apart (§9.2(d)).

**C. Make the curriculum honest about what it has not taught.**

5. Add the **feature → lesson link** to `features.json`'s `covers` and the
   matching rule to `tools/check_feature_list.py` (§8). No new lesson text; this
   is the machinery that makes the gap visible and keeps it from growing.
6. Draw the **"met / not met" line once**, at the top of the Tutorials tab:
   *"You have met 66 of the 129 things Jarvis does. 63 to go."* The backend
   already computes `counts` (`jarvis_tutorials.py:1162-1169`); this draws it.

**D. Then, and only then, write lessons.** Content is the expensive part, and
§4's table is the order: the Model page first (15 features), then money and
health, then the home's devices, then memory's lists. At 4-5 steps each this is
**roughly 12 to 15 new tutorials**, and it is writing, not code.

**What is deliberately NOT in the first slice:** `try` and the `used` state
(§5.3). It is the right model, and it is the biggest piece of machinery in this
document — a new catalogue field, a new state, per-app observation on the phone
that cannot be verified from this container, and a new check. Build it once
there are lessons worth grading, not before. **The proposal is that §5.3's
`used` state is designed now and built later**, and that until then the honest
report stays per-tutorial ("Done / In progress / Skipped / Not started"), with
no total claimed as mastery.

---

## 13. The owner's calls

Only two, and both are genuinely his.

---

### Question 1 — How much of this should I build?

The lessons already exist. The question is whether to spend the work on making
them findable and honest, or on writing the 63 missing ones, or both.

- **Findable and honest first (recommended).** Ship §12's A, B and C: the
  first-run pointer, the two fixes, the feature-to-lesson link, and the
  "met / not met" line. Write no new lessons yet. Weeks of work saved if the
  answer to Question 2 changes the shape.
- **Lessons first.** Leave the machinery as it is and write the 12-15 missing
  tutorials. Faster to "everything is documented", but nothing will say which
  lesson covers which feature, so the same 63 gaps will reappear next feature.
- **Both, in one go.** The whole of §12 including D. Most complete, and the
  longest before anything is visible.

**Recommendation: findable and honest first.** The owner's own report is that he
could not find the teaching — that is the complaint, and it is the cheapest
thing here to fix.

---

### Question 2 — Should a lesson be able to say "he can actually do this"?

Today "Done" means he pressed Next to the end. §5.3 proposes a second,
stronger state that says he has also *used* the thing the lesson is about.

- **Design it now, build it later (recommended).** The model is written down in
  §5.3 and nothing is built in the first slice. Keeps the first slice small, and
  does not commit to per-app observation on the phone that cannot be tested
  here.
- **Build it with the first slice.** The strongest signal, and the most
  machinery: a new catalogue field, a new state, and two apps to wire it into.
- **Do not do it at all.** Keep "Done" as a bookmark and never claim more. The
  simplest, and it means the app cannot ever tell him what he has actually
  learned.

**Recommendation: design it now, build it later.** A record that says "read" is
honest. A record that says "can do" is only worth having if the app can really
tell the difference — and that is worth getting right rather than shipping
first.

---

## 14. What I checked, and what I could not

**Checked, against these files in the worktree at `origin/main` `64c4580c`:**

| Claim | Where it was read |
|---|---|
| 23 tutorials, 111 steps, 6 both / 11 pc / 6 phone, 20 FAQ, 17 steps with a `point` | Counted by loading `backend/jarvis_tutorials.py` and walking `CATALOGUE` and `FAQ` |
| 129 features in 9 groups, three byte-identical copies | `features/features.json`, `jarvis-desktop/src/features.json`, `jarvis-client/app/src/main/assets/features.json`; `tools/check_feature_list.py` |
| The desktop tab is visible, in the everyday group, 6th | `jarvis-desktop/src/brain.html:55-104`; `menu-catalog.js:1373-1394`; `jarvis_menus.py:89`; `menu-visibility.js:122-128` |
| Three desktop routes in, including the palette's Help row | `palette.js:160`, `:346-362`; `menu-catalog.js:2894-2896` |
| Onboarding does not offer the tutorials | `capabilities/onboarding.json`; `commands.rs:633`, `:671`, `:730` |
| The first-run "Read the FAQ" button targets a removed card | `first-run-settings.js:494`; `settings.js:952-954`; `tests/faq.mjs:133` |
| The phone's plate is called once, from Brain | `BrainScreen.kt:1334-1338`; `MenuPlaces.kt:145`; `menu-catalog.js:1890-1909` |
| Progress is one file on the PC, shared, no card | `jarvis_tutorials.py:49`, `:59`, `:1087-1099`, `:1135-1153`, `:1162-1169`, `:1178-1224` |
| `counts` exists and nothing draws it | `jarvis_tutorials.py:1165-1167`; `tutorials.js:164-173`; `TutorialsPlate.kt` |
| The phone's registry lacks `asks-first`, and its test uses a fixture | `net/Tutorials.kt:175-182`; `TutorialsTest.kt:197-233`; `tests/tutorials.mjs:175-199` |
| `#prompt-field` and `#approval` are in `index.html`, not `brain.html` | `index.html:80`, `:653`; `brain.html:895-898`, `:1022`; `brain.js:63`, `:1262`; `tutorials.js:88-104`, `:234-249`; `tests/tutorials.mjs:201-221` |
| Test counts: 27 / 18 / 17 / 13 | Counted `check(...)` in `tests/tutorials.mjs`, `tests/onboarding.mjs`, `tests/faq.mjs` and `@Test` in `TutorialsTest.kt` (the handoff's older figures are cited and corrected in §2.4) |
| The checker's real numbers and its five stated gaps | `tools/check_tutorial_places.py` run, and its lines 72-134 and 918-921 |
| Parity already lists all three routes as ported and exits 0 | `tools/check_parity.py:113-115`, run |

**Could not check, and it is stated rather than glossed:**

1. **The phone, on a phone.** No Android SDK here, so every Kotlin claim is a
   reading of source. `docs/ANDROID-TOUR-2026-10-09.md` is the last real-device
   evidence and it is dated 2026-10-09.
2. **The desktop at run time.** No built app and no GUI session, so §9.2(d) is
   a code-path reading, with the ten-second check for the owner written into
   that section.
3. **RapidOCR's measurement.** Not found in this worktree, so §10 rule 4 names
   the honest sentence without quoting a number.
4. **The 66 / 63 coverage split is a hand judgement, not a measurement**, and is
   labelled as one in §4. The tutorial count, the step count and the feature
   count are measurements; the mapping between them is not.
5. **`docs/LEARNING-RESEARCH-2026-09-23.md` and
   `docs/EXPERIENTIAL-LEARNING-DESIGN.md` are about a different subject** — how
   *Jarvis* learns from experience — not how the owner learns Jarvis. They were
   read and they inform nothing here except one principle, that a claim must be
   measured before it is repeated.

---

## 15. One note on the way in, for whoever builds this

`docs/TUTORIALS-DESIGN.md` is **532 lines and contains two designs**: the first
(built 2026-10-05) and an interactive revision (2026-10-10) that reverses one
decision in the first and says so at its own line 329. Both are current — the
second adds `point` to the first, it does not replace it. A reader who takes the
first section's *"Not live click-along walkthroughs"* (line 41) as the state of
the world will be wrong, and a reader who takes the second as the whole design
will miss the catalogue and the routes.

This document is meant to be read after both, not instead of them. Section 2
here is the summary; those two files are the record.
