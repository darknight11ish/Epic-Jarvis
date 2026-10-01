# Topic controls: include or exclude topics in Jarvis's brain (design, 2026-09-30)

Status: **backend and both apps built 2026-09-30** (a first audit's fixes are in). The owner asked
(2026-09-30): "add the ability to adjust the brain of Jarvis to include or exclude
different topics". The backend (JARVIS-API section 107) is built and tested; the
last section of this file, **"Slice contract (frozen)"**, is what the apps are
built against and wins over anything above it where they differ (its last part
lists the differences). Everything below about existing code was read in the files
named, on 2026-09-30; what was not checked is in section 13, and what the build
found is at the end of the contract.

## In short

- Every saved fact is filed under **one topic**. There are ready-made topics
  (Work, Health, Money, Family, Hobbies, Projects, Ideas) plus the owner's own.
  Anything not yet sorted sits in **Unsorted**.
- Each topic has a **mode**, and the app offers all four whenever the owner
  changes it (the owner asked for this: "Give me the options when I do it"):
  **Learn and use** (normal) / **Use, but don't learn** / **Learn, but don't
  use** / **Off** (neither; facts are kept, not deleted).
- "Don't learn" is enforced **before a fact is saved**. "Don't use" is enforced
  **inside the search that picks facts for an answer**, so every reader is
  covered by default and a new reader added later cannot leak by forgetting.
- Making a **private** topic (Health, Money, or any topic the owner marks
  private) more permissive asks with a card. Anything stricter is immediate.
- The sensitive-topics rules do not move. A topic mode is an extra filter in
  front of them: "Learn and use" on Health does **not** let health facts skip
  the owner's yes.
- Facts already saved are sorted by fixed rules (no model), shown in small
  batches for the owner to check, and nothing about answers changes until the
  owner moves a topic off "Learn and use".
- Honest limit: how well the sorting guesses is **not measured yet**. A
  fact wrongly filed under a topic that is on can still appear in answers.

## 1. What the owner decided, and what this is not

Owner's answers (2026-09-30):

- Topics are "ready-made topics plus your own": a starter list the owner can
  rename, add to and delete. Each fact sits under ONE topic. Facts already
  stored are sorted, and shown for the owner to check.
- What switching a topic off does: "Give me the options when I do it". So every
  topic has the four-mode picker, offered at the moment of change.
- Any rule here can be changed by the owner if worth it (the questions in
  section 12 are exactly those).

What this is **not**:

- Not chat tags. Tags label whole chats in History (`docs/CHAT-TAGS-DESIGN.md`).
  Topics filter what Jarvis learns and uses. Section 2 says how they differ.
- Not a new way to save or send anything anywhere. Nothing leaves the PC
  (rule 1). No cloud model is involved in sorting.
- Not the memory graph. The Galaxy stays desktop-only (CLAUDE.md standing rule).

## 2. Topics and chat tags: two things, one look

| | Topic (this design) | Chat tag (CHAT-TAGS-DESIGN) |
|---|---|---|
| Sticks to | a saved **fact** | a whole **chat** in History |
| Changes behaviour? | Yes: learning and answers | No: organising only |
| Who files it | rules first, model may suggest, owner corrects | only the owner, never automatic |
| Stored | `memory.db` (plain, like the facts) | sealed in `chat-history.db` |

**Recommendation: share the look, keep the identities apart.**

- Share the eight colour slots and the icon list (one fixture, so both features
  use the same checked contrast). Topics need three icons the tag list lacks
  (`heart`, `coin`, `people`); add them to the shared list in
  `tools/gen_history_cases.py`, which owns the palette. Do not copy the palette.
- Where names overlap (Work, Projects, Ideas) use the same colour and icon, so
  the eye learns one meaning. Health, Money, Family and Hobbies get their own.
- Do **not** link them. Filing a chat under the tag "Work" does not file the
  facts learned there under the topic "Work". Reason: tags are sealed, applied
  afterwards, and never touch memory (CHAT-TAGS §3); linking would leak tag
  names into memory or topics into chat history. A later idea (section 11): a
  chat's tag as a **hint** to the classifier, never automatic.

## 3. Data

### 3.1 Where it lives, and what is true about protection

`memory.db` is a plain SQLite file: `MemoryStore._connect()` calls
`sqlite3.connect(self.path, ...)` with no cipher, and I found no sealing code in
`rebuilt/jarvis_memory.py` (searched for encrypt, seal, sqlcipher). Fact text
is therefore stored in plain form in that file (whether Windows disk encryption
covers it is not checked). Chat tags are sealed only because the chat history
file is; this is why `CHAT-TAGS-DESIGN` seals them.

Topic names are the owner's words, so they are as private as the facts. Stored
**in `memory.db` too**, plain, like the fact text beside them: sealing the
names while the facts sit in the clear next to them protects nothing, and a
second file would split the backup. This is said in the app's help, not hidden.
If `memory.db` is ever encrypted, topics move with it. No second copy of a
topic name is written anywhere else (not in the settings JSON, not in logs;
audit lines carry the topic **id** only).

### 3.2 Tables (ids only where possible, the shape `profile` and `fact_repeats` use)

```
topics        id INTEGER PK, name TEXT (1-24 chars, unique ignoring case),
              colour 0-7, icon TEXT, mode TEXT ("both"|"use_only"|"learn_only"|"off"),
              private INTEGER (0/1), words TEXT (owner's optional keywords, <= 20),
              ord INTEGER, system INTEGER (1 = Unsorted), created REAL
fact_topics   fact_id INTEGER PK, topic_id INTEGER, alt_topic_id INTEGER NULL,
              how TEXT ("rule"|"model"|"owner"|"new"), checked INTEGER (0/1),
              assigned REAL
topic_skips   topic_id, day, n      (a COUNT of facts not saved; no words)
```

- **Limits:** 16 topics plus Unsorted. Unsorted has id 1, cannot be deleted or
  renamed, and has a mode (default "Learn and use").
- **Starter list** (created on first read): Work (blue, briefcase), Health
  (rose, heart, **private**), Money (amber, coin, **private**), Family
  (teal, people), Hobbies (green, music), Projects (violet, folder), Ideas
  (teal, lightbulb). Every starter mode is "Learn and use", so **on the day the
  feature ships nothing about learning or answers changes** (tested, section 9).
- One topic per fact (`fact_id` is the key). When a fact fits two topics, the
  stricter one wins and the other is kept as `alt_topic_id` (an id, no words) so
  the check list can say "Jarvis filed this under Work; it also fits Family".
- `private` survives rename (it belongs to the id). Only the owner sets it on a
  topic of their own; setting it is immediate, clearing it is a card.
- Erase keeps the row: the topic id is a label, not words, like `meta.kind`
  (ARCHITECTURE §5, `ERASE_KEEPS_META`). Forget changes nothing here.
- Deleting a fact never deletes a topic; deleting a topic never deletes a fact
  (section 3.4).
- Why a table and not `meta.topic` in the fact's JSON: the use filter must run
  **inside candidate selection** with an index; JSON matching on every candidate
  row is slower and easy to forget. A table also backs up and exports with the
  file (section 10).

### 3.3 Who assigns a fact's topic, and when

`backend/jarvis_topics.py` (new, shipped whole) exposes `classify(text)` ->
`(topic_id, how, sure, alt)`. Three layers, cheapest first, like
`jarvis_sensitive.py`:

1. **Sensitive patterns, no model.** `jarvis_sensitive.patterns(text)` already
   finds health and money in eight languages. Health -> Health, money -> Money,
   both `sure`. Credentials and identity numbers get no topic here (they always
   wait for the owner's yes, `always_asks`); they stay in Unsorted and keep their
   `meta.sensitive` label. This is the natural first signal.
2. **Keyword rules, no model.** Small word lists per starter topic, plus the
   owner's own `words` for their topics. Family reuses the relation words
   `jarvis_sensitive` already knows. Projects also matches the names in
   `jarvis_projects`. **English only in v1** (the sensitive lists cover eight
   languages, these do not). A fact in another language falls to Unsorted; the
   design says so plainly in the app help and section 13.
3. **The local model as a suggestion**, only when layers 1-2 found nothing, on
   the learner's own local model (loopback, not a cloud model, the same checks
   `jarvis_sensitive.learner_model()` makes), one short call with a random data
   tag, JSON only, "unsure" allowed. Stored as `how="model"`, `checked=0`, shown
   in the check list as "Jarvis guessed". The model can only choose among topic
   names it is given; it can never create a topic, change a mode, or move a fact
   **out of** a topic that layer 1 or 2 chose. Unsure, no answer, or a timeout is
   Unsorted (with the "unsure" flag from section 4.3).

Timing: layers 1-2 run when a proposal is made (`jarvis_intake.propose`, before
the queue), because "don't learn" needs the answer before saving. Layer 3 runs
after saving, on the background pass, and only for facts still in Unsorted. The
owner's own tap ("File under...") always wins and sets `how="owner"`,
`checked=1`.

### 3.4 Existing facts (back-fill) and the check list

- On first start with the feature, a background job runs layers 1-2 over every
  current fact and writes labels only: `how="rule"`, `checked=0`. It never edits,
  retires or hides a fact, and never calls a model. It is one job on the one
  scheduler, paced like the overnight tidy. Layer 3 over old facts is a separate
  opt-in switch ("Let Jarvis's local model help sort"), off to start, at most 20
  facts a night, and the first time it is turned on it is an ordinary switch (it
  reads the owner's own facts with the local model, as the learner already does,
  so no card; a note in the app says so).
- **Unchecked labels still count.** If they did not, Off would leak every fact
  the owner had not yet reviewed. The app says so: "Jarvis sorted 212 of your
  230 facts by guessing from the words. Check them so switching a topic off works
  as you expect."
- **"Check these"** is a list of unchecked facts in batches of 10, grouped by
  the suggested topic: one tap "These are right" per batch, or change any single
  fact. The owner's confirm is a tap on a list they can see (no card), the same
  spirit as the overnight tidy: **the job proposes, the owner decides, and memory
  is never changed by itself** (only labels, and labels do nothing while every
  topic is on "Learn and use").
- Deleting a topic asks **where its facts go** (pick a topic; "Unsorted" is
  offered only if Unsorted is at least as strict). Otherwise a deleted Off topic
  would let its facts fall into a looser mode and leak. Moving facts to a looser
  topic follows the loosening rule in section 5.

## 4. The four modes and where each is enforced

A mode is two switches: **learn** and **use**.

| Mode | Plain words for the app | learn | use |
|---|---|---|---|
| `both` | Learn and use. Jarvis remembers new things about this and uses them in answers. | yes | yes |
| `use_only` | Use, but don't learn. Jarvis keeps what it knows and uses it, but saves nothing new. | no | yes |
| `learn_only` | Learn, but don't use. Jarvis keeps learning quietly, but leaves this out of its answers. | yes | no |
| `off` | Off. Jarvis neither learns nor uses this. What it knows is kept, not deleted, and comes back when you switch it on. | no | no |

If a fact had two topics the effective mode is the AND of both (stricter wins).

### 4.1 "Don't learn" (learn = no): at intake, before saving

- `jarvis_intake.propose` classifies each proposed fact with layers 1-2. If the
  topic is `sure` and its mode has learn = no, the proposal is **dropped before
  it reaches the review queue** and `topic_skips` counts one. No card, no
  nagging; the topic row shows "3 things not saved this week" (a count, never
  words).
- `jarvis_auto_learn.after_pass` **re-checks** at save time (defence in depth,
  because the queue can hold older proposals), before the sensitive gate.
- The write door, `MemoryStore.add(...)`, gets an optional `topic=` and records
  the assignment in the same transaction. A fact from an explicit "Remember: ..."
  or a card the owner accepts is the owner's yes and is saved; if its topic has
  learn = no, the card or reply says so first ("You set Work to not learn. Save
  this one anyway?"). One fact, one yes, no standing change.
- Order of gates for a new fact: topic learn switch, then the existing chain
  (`check_sensitive`, always-ask patterns, grounded, and so on). A topic can only
  add a "no"; it never removes an existing one.
- Never loosens the "owner's own words only" rule: outside text is still never
  learned, whatever the mode.

### 4.2 "Don't use" (use = no): inside the search, before the cut to k

Filtering the final list would shrink the answer (5 facts minus 2 blocked = 3).
The block goes into **candidate selection** (word search, meaning search, the
entity list, "who is this person", places), so the best allowed facts fill the
slots. Implementation shape: `MemoryStore.search(..., topics="use")` is the
**default**; a caller that must see everything says `topics="all"` and is
listed in the table below. Default-deny means a reader added next year is
filtered without anyone remembering to. When no topic has use = no, the filter
is skipped entirely (fast path, byte-identical results).

### 4.3 When Jarvis is unsure

The rule follows the sensitive-topic rule: **unsure stays in the more protected
class.** Concretely, "sure" means a layer 1 or 2 hit that names one topic.
"Maybe" means the classifier found no topic, found two, or the only signal is a
model guess.

- **Learn side:** a "maybe" fact that could belong to a topic with learn = no
  (a weak keyword, a model guess, a tie with such a topic) is **not saved
  automatically and not dropped silently**. It becomes an ordinary card whose
  reason line says "This might be about Work, which you set to not learn."
  (reason text for `auto_reason`, as the other checks do). Capped at 5 such cards
  a day so a chatty topic cannot flood the queue (over the cap: dropped, counted).
- **Use side:** a fact whose only assignment is a model guess or a "maybe" hit
  on a topic with use = no is **left out of answers** until checked, and shows in
  the check list as "Held back: might be about Work". Leaving out a needed fact is
  a smaller harm than leaking a fact the owner asked to exclude, and the answer
  can say how many were held back (section 4.5).
- A plain Unsorted fact with no signal at all follows the **Unsorted** mode,
  which is "Learn and use" unless the owner changed it. This is the honest gap:
  an unrecognised work fact is not held back by "Work: Off" (section 13).
- The mapping never touches sensitive handling: `meta.sensitive`, read-aloud and
  web-search asking-first work exactly as today, whatever the topic.

### 4.4 Every code path that reads facts (must-honour list)

Found by searching `backend/` for the store's readers and `FROM facts`
(2026-09-30). **Use** = its output can reach a model, a screen or a voice, so it
must honour use = no. **Protective** = it reads facts only to protect the owner
(duplicates, leaks, corrections) and never shows the text to a model or answer,
so it must see everything (`topics="all"`); making it blind would create leaks.

| Reader (file) | What it does | Rule |
|---|---|---|
| Chat recall: `jarvis_past.recall` -> `store.search` (patches `memory-prefix`, `past-recall`) | facts in every local answer | **must-honour** (the default) |
| Past labels (`jarvis_past`, retired facts) | "no longer true" recall | **must-honour** |
| Entity list and "who is this": `search(entities=True)`, `_linked_facts`, `_who_facts` | third recall list, one step out | **must-honour**, filtered in the candidate SQL |
| Pinned list: `with_profile` (`memory-profile.patch`) | facts read with every question | **must-honour**; a pin in a blocked topic is not injected, the pin row stays and shows "paused: Work is off" (owner question 5) |
| Re-ranker, said-again tie-break | reorder the top 20 | inherit: they only reorder what search returned |
| Tool `memory_search` (`jarvis_agent._run_memory_search`) | model asks for facts | **must-honour**; goes through the same recall |
| "Where is my passport?" fast path (`jarvis_places.lookup`, own `SELECT ... FROM facts`) | answers without a model | **must-honour**; it has its own SQL, so it needs its own filter |
| Morning briefing "Facts saved automatically" (`jarvis_briefing._auto_facts_section`, via `jarvis_auto_learn.list_auto`) | lists new fact text | **must-honour**: leave out `learn_only` and `off` facts; the count too |
| Overnight tidy (`jarvis_tidy.current_facts`, own SQL) | local model compares numbered facts | **must-honour** for Off (a model reads them); `learn_only` facts are out too, they are "not used" |
| Learner's candidate facts (`jarvis_intake.candidates`) | shows stored facts to the learner's local model to spot corrections | Off facts excluded; the rest allowed. Closest call in this table: to be re-read line by line in the build (section 13) |
| "Used in this answer" (`used_view`), "Where this came from" | words of ids an answer used | ids come from injection so they are already clean; if the topic was switched off **later**, show "a memory from a topic you have since switched off", no words |
| Brain lists, Galaxy, "Saved automatically", fact history, export (`/api/memory/facts`, `entities`, `auto`) | the owner's own view | owner's view, see 4.6 |
| Forget, Erase, forget-a-time-frame (`saved_between`) | the owner acts on facts | **must see all**, including Off facts (section 4.6) |
| Chatbot leak check (`jarvis_chatbot.py:596`), web-search "would repeat a saved fact" (`jarvis_search`, `fact_topic`), duplicate / forgotten / contradiction checks (`jarvis_auto_learn`, `jarvis_intake`), `find_one`, `said_again`, entity merge cards | protect against leaks and duplicates | **protective: `topics="all"`**. Never shows text to a model |
| Goals (`jarvis_goals`), plan card (`jarvis_plan`), wiki builder, initiative engine (`rebuilt/jarvis_initiative`), projects | none found reading facts today | nothing to filter now; the guard test (section 9) fails the build if one starts |
| Cloud lane | a turn that leaves the local lane already drops the whole FACTS block | unchanged |
| Temporary chat | recalls nothing | unchanged, already stricter |

### 4.5 Telling the owner something was left out

The chat route gains one number, `topics_left_out` (in `X-Jarvis-Route`, like
`injected_ids`): how many facts the topic filter kept out of this answer's
candidates. Both apps may show "Left out 2 facts because of your topic settings"
in the "Used" area. It is a count only. It exists so a missing fact is
explainable instead of mysterious, and so a wrong sort can be noticed.

### 4.6 Lists, Galaxy, Forget and Erase

- **Recommendation: an Off topic's facts are hidden from the ordinary lists**,
  and its row shows "41 facts kept, hidden" with a "Show them" button that opens
  them greyed with a label. Reason: Off should feel off (the Brain and Galaxy can
  be seen over a shoulder), and the count keeps them findable.
  `learn_only` facts stay visible (tag: "not used in answers"): the owner turned
  learning on and will want to see it work. `use_only` facts are shown as normal.
- Galaxy (desktop only): a person or thing linked only to hidden facts is
  hidden; one linked to visible facts shows only those. "About <name>" lists
  visible facts only.
- **Forget and "Erase the words" always work**, including on hidden facts (via
  "Show them"), and "Forget a time frame" lists them too. Off never blocks the
  owner from removing something.
- Switching a topic back on needs nothing else: the facts were never moved.

## 5. Approvals

Aligned with `jarvis_auto_learn.py` (request function, one newest card, withdrawn
by the opposite change, LAST_WORDS style outcomes): **looser asks, stricter is
immediate.**

| Change | Result |
|---|---|
| Any mode to a stricter one (fewer things on), any topic | immediate, no card |
| Loosening a **private** topic (Health, Money, or one the owner marked private) | **one card** (`topic_loosen`, tier ask) |
| Loosening any other topic | immediate (owner question 4) |
| Clearing the "private" mark | one card |
| Rename, colour, icon, reorder, add a topic, edit a topic's words | immediate |
| Moving a ticked batch of facts out of a private topic into a looser one | one card listing the count |
| Moving a single fact by the owner's own tap | immediate |
| Deleting a topic | a confirm in the app, and the "where do its facts go" choice |

The card names the topic and says what changes in plain words, for example:
"Turn Health back on for answers? Jarvis will use your health facts again. They
are still kept on screen and not read aloud, and new health facts still wait for
your yes unless 'Also remember sensitive topics automatically' is on." So the
owner's example (Health to "Learn and use" without sensitive auto-learning) is
allowed, asks once, and does **not** weaken the sensitive gate.

Other rules:

- Ordinary tier `ask`, same as `learning_sensitive_enable`. No Windows Hello
  requirement (nothing leaves the PC and it is a memory switch, not an
  approval-bypass). If the owner wants it PC-only, that is one line in
  `PC_ONLY_ACTIONS`.
- **Never a loosening from outside text** (mail, web, files, tool output,
  pasted or shared text, a chatbot). The voice and chat door acts only on the
  newest typed or spoken words (`newest_own_words`), and only when the turn read
  no outside text.
- Held on a stale link (rule 4), like every change. Reads are not held.
- **Undo is just another change**: it goes through the same rule. Undoing the
  owner's own tightening on a private topic therefore asks with a card, which is
  slightly annoying and closes a loophole.
- "What asks first" gets one new row in `jarvis_reach.py` / `jarvis_asks_first.py`
  ("Turning a private topic back on"), listed with its "make stricter" switch
  where one applies. It is not in the short "may be loosened from an app" list.

### The voice and chat door (`jarvis_settings_registry.py`, second door)

A new setting kind, "topic mode", that calls the **exact** function the picker
calls (no parallel path). Because the owner wants the options offered:

- Unambiguous phrases apply at once when stricter: "stop using my work topic"
  -> Learn, but don't use; "don't learn about money" -> Use, but don't learn.
  Reply: "Done: Work is Learn, but don't use. You can change it in Brain."
- Ambiguous phrases ("switch off / pause / hide my work topic") **open the
  picker instead of guessing**: the reply sets `open_brain: "topics"` with the
  topic id, the app shows the four options, nothing changes until the owner taps
  (the same tap-to-finish shape CHAT-TAGS §5 uses for older chats).
- A looser phrase ("use my health topic again") goes through the same card as
  the picker. Unknown topic name: Jarvis lists the topics that exist.
- New route fields need the desktop whitelist (`commands.rs` route keys and its
  test) and the phone's `ChatSession.kt` reader, as chat tags do.
- **Per-chat override (later):** "for this chat, leave out Work". A stricter-only
  map held in memory by `conversation_id`, like `jarvis_manner.set_temporary`;
  no card, gone at restart. Not in v1 (section 11).

## 6. The screens (both apps)

Location: **Brain -> Memory**, a new "Topics" section beside "What Jarvis
remembers" / "Saved automatically". Same wording in both apps from one shared
fixture (section 8).

Each topic row: colour + icon + name (never colour alone), fact count, and the
current mode as a small button with its plain name. Tapping the mode opens the
**picker with the four modes**, the current one marked, and a line built from a
preview: "12 things Jarvis knows about Work will be left out of answers." (via
`GET /api/topics/preview`). Private topics show "Private" and, when the choice
is looser, "This will ask for your OK first."

Below the rows: **Unsorted** (its own row, same picker), **"Check these (38)"**
(the review list, section 3.4), and **"Add a topic"**. Rename / colour / delete
are in each row's menu. Names are limited to 24 characters; errors are one plain
sentence per code.

Beginner wording (owner is a beginner developer; no jargon): "A topic is a
folder for things Jarvis knows. Pick what Jarvis may do with each folder."
Skip counts read "3 new things not saved since Monday". Nothing says "classifier".

- **Hide memory lists and chat history / App lock:** topic **names are the
  owner's words**, so they are hidden with the other memory lists (the Rust side
  calls `lock::private_hidden` like tags); rows then show "Topic 1, 41 facts,
  mode" only, and the check list is hidden entirely. Phone screenshots stay
  blocked while either lock is on, as today.
- **Screen reader:** "Work, 41 facts, Use but don't learn, button: change mode".
  The picker is a radio list with each mode's sentence as its description.
- **Desktop:** Brain -> Memory (`topics.js`, `brain.js` / `brain.html`), the
  Galaxy honours hiding (4.6). **Phone:** Topics rows, picker, "Check these" and
  add/rename/delete only. The phone shows fact words in the check list the same
  way it already shows the "Saved automatically" list (under the same hide rule).
  Not on the phone: the Galaxy (standing rule) and editing a topic's **words**
  (typing long lists is deep configuration; desktop only; recorded in
  ARCHITECTURE §8 "One-sided on purpose").

## 7. Routes (JARVIS-API section 107, reserved; no other number)

| Route | Body | Notes |
|---|---|---|
| `GET /api/topics` | - | topics + counts + mode + `private` + `unchecked` + skip counts; names redacted client-side while lists are hidden |
| `POST /api/topics` | `{op: "add"\|"rename"\|"style"\|"move"\|"words"\|"private"\|"delete", ...}` | delete takes `move_to`; `private` false is a card |
| `POST /api/topics/mode` | `{id, mode}` | 200 applied, or **202 `{waiting: true}`** when a card is raised; the newest card wins |
| `GET /api/topics/preview` | `?id=&mode=` | `{affected, pinned, needs_card}`; no fact words |
| `GET /api/topics/review` | `?after=&limit=` | unchecked facts with their suggested topic; a memory list (hidden while lists are hidden) |
| `POST /api/topics/file` | `{ids: [..], topic_id, confirm?: true}` | file, or just confirm; a looser move out of a private topic is a card |
| chat route header | `topics_left_out: int` | count only |

Errors follow the tags style: `bad_name`, `name_taken`, `too_many_topics`,
`bad_colour`, `bad_icon`, `topic_not_found`, `bad_mode`, `no_delete_unsorted`,
`bad_request`. Routes go through a shipped-whole module and its whitelist
(`jarvis_brain_reads.py` style) or a patch; run
`python3 tools/build_patch_history.py` after any patch edit (after
`git fetch --unshallow`). Add rows to `tools/check_parity.py`.

## 8. Files and modules

Backend (the real backend is outside this repo; these are patches plus shipped
modules): `jarvis_topics.py` (registry, `classify`, modes, request/card, handlers,
back-fill job), `topics.patch` (hooks below), `rebuilt/jarvis_memory.py` (tables,
`add(topic=)`, `search(topics=)`), `jarvis_intake.py` (drop before queue),
`jarvis_auto_learn.py` (re-check, reason text, list_auto filter),
`jarvis_places.py` and `jarvis_tidy.py` (own SQL filters), `jarvis_briefing.py`,
`jarvis_settings_registry.py` + `jarvis_quick.py` grammar (+
`tools/gen_sayable_cases.py`), `jarvis_asks_first.py` / `jarvis_reach.py` (one
row, then `tools/gen_reach_cases.py` and `gen_asks_first_cases.py`),
`tools/gen_topics_cases.py` (wording, mode sentences, palette, icons; writes both
apps' fixture copies), `tools/gen_history_cases.py` (three new icons).
Desktop: `topics.js`, `brain.js`/`brain.html`/`brain.css` (Memory tab section),
`galaxy-view.js` (hidden facts), `src-tauri/src/brain/topics.rs`, `routes.rs`
allowlist, `commands.rs` route keys, `lock/rules.rs`, capability and permission
tomls. Phone: `net/Topics.kt`, `ui/screens/TopicsPlate.kt` (with
`AutoLearnPlate`, `MemoryCountsPlate`), `JarvisApi.kt`, `JarvisRuntime.kt`,
`net/ChatSession.kt`, `TopicsContractTest.kt` reading the shared fixture.

Every phone Kotlin change is unverified until CI compiles it (no local Android
build here, see CLAUDE.md).

## 9. Tests, and the memory self-test

The rule stands: a memory change is kept only if it does not make the numbers
worse (`backend/eval_memory.py`, `backend/eval_learner.py`, numbers from the
owner's PC, written on `docs/MEMORY-SCOREBOARD.md` after each change).

- **Parity run (must be identical):** with every topic on "Learn and use",
  `eval_memory.py` must reproduce the scoreboard numbers exactly, at 0 / 100 /
  1,000 / 10,000 filler, because the filter is skipped. Any difference is a bug.
- **Topic-off runs:** give the persona's facts a `topic` field. With Work set
  to Off (and again to "Learn, but don't use"): (a) **leak count must be 0**: no
  Work fact in any question's top-k, including the entity and "who is" lists and
  the past-recall path; (b) recall@5 for questions about topics that are ON must
  not get worse; (c) questions whose only answer is a Work fact must return
  nothing ("don't know" counts as right). Also time the 10,000-filler run with and
  without a blocked topic (the filter is an indexed join, not a scan; unmeasured).
- **Learner test:** new cases in `eval_learner.py`: a Work fact with Work on
  "Use, but don't learn" produces no proposal and no save; a "maybe" fact makes a
  card with the reason line; "Remember: ..." on a no-learn topic asks first; the
  sensitive gate still applies in every mode.
- **Guard test (`test_topics_leaks.py`):** walks the backend source for every
  call of the readers in 4.4 and every `FROM facts` outside the memory module and
  fails if one is not in an allowlist saying `use` or `all`. This is what makes
  the table above a checked list rather than a promise.
- **Unit tests (`test_topics.py`):** modes and the AND rule, limits, starter list,
  stale-link hold, the card path (newest wins, withdrawn by the opposite change,
  outcomes), no loosening from outside text, delete-with-destination, erase keeps
  the topic row, backup restore keeps modes. Plus `test_settings_registry.py`,
  `test_asks_first.py`, `test_card_words.py` rows; both apps read the shared
  fixture; `tools/check_parity.py` clean.
- **Classification accuracy is NOT measured yet, and this design does not
  pretend otherwise.** Before the classifier is trusted for "Off" the build adds
  a labelled set (`backend/topic_cases/`, the shape of `backend/sensitive_cases`)
  and reports per topic: how often an Off-topic fact was filed under a topic that
  is on (the number that matters: a leak), and how often an on-topic fact was held
  back. Health and Money should be strong because they reuse the measured
  sensitive lists; Work, Family, Hobbies, Projects and Ideas are keyword guesses
  and will be weaker. Model-layer numbers come from the owner's PC only.

## 10. Risks

- **Silent leaks through an unlisted read path.** Answer: default-deny in
  `search`, a guard test, and `topics_left_out`. Residual: a reader with its own
  SQL (`places`, `tidy`, `auto_learn`) must be edited by hand; the guard test is
  what catches a miss.
- **Wrong sort hides a needed fact.** Held-back facts appear in the check list;
  the answer can say how many were left out; Off is reversible. Wrong sort the
  other way (an Off-topic fact filed as an on topic) still leaks; the owner's
  check list and the measured leak rate are the defence, and the app says the
  sorting is a guess.
- **The model deciding topics.** Rule: it suggests, the owner corrects. It can
  never create topics, change modes or loosen anything, and a rule-made
  assignment beats it.
- **Bulk trust.** "These are right" on a batch confirms guesses in one tap;
  batches are 10 and grouped so a bad group is visible.
- **Performance.** Unblocked: zero cost (skipped). Blocked: one indexed
  subquery per candidate query. Back-fill and model help are paced background
  jobs. Numbers are measured at 10,000 facts, not yet.
- **Backups and export.** The locked backup and `/api/memory/export` contain
  everything, topics and modes included, as they do fact text. No change to that
  bend of rule 1; the app already says erased facts stay in older backups. Modes
  are settings that ride with the file. Export gains a topic column.
- **Names as private text.** Hidden under "Hide memory lists"; never logged; never
  in an audit line, event or route header (ids and counts only).
- **Owner confusion:** four modes are a lot. Mitigations: plain sentences, the
  live preview line, and the picker showing only consequences, not jargon.

## 11. Turned down / later

- **Turned down:** using a cloud model to sort topics (rule 1); a "topics graph"
  or topic tree on the phone (standing rule); letting Jarvis create or rename
  topics by itself; letting a topic mode bypass or replace the sensitive gate;
  auto-confirming the check list; fact text in `X-Jarvis-Route`.
- **Later:** per-chat "for this chat, leave out Work" (stricter-only, in memory);
  a chat's tag as a hint to the classifier (never automatic, never sealed data
  written into memory); non-English keyword lists; a topic-aware overnight tidy
  card ("12 unsorted facts look like Work"); "Between us" and pins per topic;
  a topic filter on the briefing's other sections; multi-topic facts (the owner
  chose one topic per fact); topic-based auto-forget.

## 12. Owner's questions

Ask two at a time; recommendation first.

1. **When Jarvis is not sure a new fact belongs to a topic you turned off
   learning for:**
   - **Ask you with a card** (recommended): nothing is lost and nothing is saved
     by mistake, at the cost of an occasional card.
   - Save it under Unsorted: fewer cards, but a Work fact could slip in.
2. **Health and Money, coming back on:**
   - **Ask with a card** (recommended): they are your private topics; the card
     is the same kind you already see for sensitive learning.
   - Never ask: switching any topic back on is instant.
3. **A topic that is Off, in your lists:**
   - **Hidden, with a "Show them" button** (recommended).
   - Shown greyed with a label.
4. **Turning a normal topic (like Work) back on:**
   - **Instant** (recommended).
   - A card every time, like Health.
5. **A fact you pinned ("always keep in mind") in a topic that is Off:**
   - **The topic wins: not used until the topic is back on** (recommended).
   - The pin wins.

## 13. Not verified

- Nothing was run. No code was written. The container has no Windows, no Ollama
  and no Android build.
- **Classification accuracy is unknown.** No labelled topic set exists. The
  English-only keyword lists are untested. An unrecognised fact lands in Unsorted
  and is not held back by another topic being Off.
- I confirmed that `MemoryStore._connect()` opens `memory.db` with plain
  `sqlite3.connect` and that I found no sealing code by searching
  `rebuilt/jarvis_memory.py`. I did not check disk-level encryption on the
  owner's PC, or the owner's real `jarvis_hud.py` (outside this repo), where the
  chat route and some readers live; `topics.patch` hooks there are written
  against the patches' context, as with every other patch here.
- The reader table (4.4) comes from searching this repo. `jarvis_briefing`'s
  section was read but where `list_auto`'s rows are consumed was not traced end
  to end. The initiative engine, goals, plan card and wiki builder showed no fact
  reads in my search; that is "not found", not "proved none". The guard test in
  section 9 is what would prove it.
- `jarvis_intake.candidates` and the intake lines that gather existing fact
  text (`~774`, `~1208`, `~1268`) need a line-by-line read in the build to
  decide, for each, whether text reaches a model (then Off filters it) or only
  compares (then protective).
- Card wording, the exact keyword lists and the three new icons are proposals.
  No performance figure exists for the blocked-topic search.
- The interaction with the pinned list, past-recall labels and the entity layer's
  merge cards was reasoned from the code and the architecture notes, not run.
- `JARVIS-API` §107 is reserved by the request; I did not check other open
  branches for a clash beyond `docs/BUILD-QUEUE-2026-09-30.md`.


## Slice contract (frozen)

Written 2026-09-30, after the backend was built. **This is what the two apps are built against.** It describes what the backend does today (`backend/jarvis_topics.py`, the rebuilt `jarvis_memory.py`, `topics.patch`; `docs/JARVIS-API.md` section 107 has the same shapes in prose). Where it differs from the design above, this section wins; the differences are listed at the end. A shape changes only together with the backend, `tools/gen_topics_cases.py` (which writes the shared fixture `topics-cases.json` into both apps) and this section.

### C1. Who builds what

| Piece | Backend (done) | Desktop app | Phone app |
|---|---|---|---|
| Brain -> Memory -> **Topics** section: rows, the four-choice picker, "Check these", "Show them", add / rename / colour / reorder / delete | routes below | `topics.js`, `brain.html` / `brain.js` / `brain.css` (Memory tab), `src-tauri/src/brain/topics.rs` (+ `routes.rs` allowlist, `capabilities/brain.json`, `permissions/*.toml`) | `net/Topics.kt`, `ui/screens/TopicsPlate.kt` (with `AutoLearnPlate` / `MemoryCountsPlate`), `net/JarvisApi.kt`, `JarvisRuntime.kt` |
| "Left out N facts because of your topic settings" in the "Used" area, from `topics_left_out` in the chat route header | `X-Jarvis-Route` field | reader in `commands.rs` (route keys + its test) | `net/ChatSession.kt` |
| The picker opened by asking Jarvis ("switch off my work topic") | `open_brain: "topics"`, `topic_id` in the route header | same whitelist as above | same reader as above |
| A topic-question card ("This might be about Work, which you set to not learn.") | pending row gains `topic_ask: true` | relabel its two buttons | relabel its two buttons |
| Lists: the "not used in answers" tag, pins "paused", "Used" for a switched-off topic, `topics_hidden` | fields below | the existing lists | the existing lists |
| Keyword editing (`words`) | route takes it | **yes** (add / edit dialog) | **no**: shows `Keywords are set on your PC.` (deep configuration; ARCHITECTURE.md section 8) |
| The Galaxy | `GET /api/memory/entities` already leaves out people linked only to an Off topic's facts | nothing to do | **none** (standing rule) |
| Tests | `test_topics.py`, `test_topics_leaks.py`, `eval_topics.py`, learner cases | `tests/topics.mjs` reading `tests/fixtures/topics-cases.json`; Rust unit tests | `TopicsContractTest.kt` reading `contract/topics-cases.json` |
| `tools/check_parity.py` | the seven `/api/topics*` rows are `planned` | each app that calls a route lets its row become `ported` | same |

Every phone Kotlin change is unverified until CI compiles it (no local Android build here).

### C2. Shapes (exact)

`Topic` (a row of `topics`):

```json
{"id": 2, "name": "Work", "colour": 0, "icon": "briefcase", "mode": "both",
 "private": false, "words": ["standup"], "ord": 1, "system": false, "created": 1790000000.0,
 "facts": 41, "unchecked": 3, "hidden": false, "skipped_week": 0}
```

`mode` is one of `both`, `use_only`, `learn_only`, `off`. `hidden` is true exactly when `mode` is `off`. `facts` counts facts in use (a Forgotten or erased one is not counted); `unchecked` is how many of them Jarvis sorted by guessing and the owner has not checked (always 0 for Unsorted); `skipped_week` is how many new things were not saved for this topic in the last 7 days (a count - never words). Unsorted is `{"id": 1, "system": true, "name": "Unsorted", ...}` and is always first; the others follow in `ord`.

`GET /api/topics` -> `200`:

```json
{"ok": true, "topics": [Topic, ...], "unchecked": 38, "facts": 230, "sorted": 212,
 "model_help": false, "backfill": {"done": true, "remaining": 0},
 "limits": {"max_topics": 16, "name_max": 24, "words_max": 20, "batch": 10, "colours": 8,
            "icons": ["briefcase", "book", "home", "folder", "lightbulb", "star", "flag", "wrench", "leaf", "music", "heart", "coin", "people"]},
 "modes": [{"id": "both", "name": "Learn and use", "sentence": "..."}, ...],
 "waiting": null,
 "last": null}
```

`waiting` is `{"topic": <id>, "kind": "mode" | "private_clear" | "delete" | "file"}` while one approval card is up, else `null`. `last` is `{"outcome": "applied" | "denied" | "timed_out" | "refused" | "withdrawn" | "failed", "why": str, "at": float, "message": str}` for the most recent card, else `null`; show `message` (it is the PC's own sentence). `unchecked` is the sum over topics other than Unsorted; `sorted` is `facts` minus Unsorted's.

Every successful write answers `200` with the same body as `GET /api/topics` plus `"id"` (the topic touched) and, per route: `"changed": bool` (mode), `"deleted": id`, `"filed": n`, `"confirmed": n`. A write that raised a card answers **`202 {"ok": true, "waiting": true, "id": <topic>, "kind": <kind>, "message": "Waiting for your approval."}`**: nothing has changed yet. After a 202 the app shows `words.waiting` on that topic, then reads `GET /api/topics` every 2 seconds (and whenever its approvals list changes) until `waiting` is `null`, shows `last.message`, and redraws.

Requests (all JSON, all `POST` are held on a stale link):

| route | body | notes |
|---|---|---|
| `POST /api/topics` | `{"op": "add", "name": str, "colour"?: 0-7, "icon"?: str, "words"?: [str], "private"?: bool}` | 200 with `"id"` = the new topic. Colour defaults to the next slot, icon to `folder`. |
| | `{"op": "rename", "id", "name"}` | |
| | `{"op": "style", "id", "colour"?, "icon"?}` | |
| | `{"op": "move", "id", "before": id \| null}` | reorder; `null` = last |
| | `{"op": "words", "id", "words": [str]}` | desktop only |
| | `{"op": "private", "id", "private": bool}` | `true` at once; `false` -> 202 + card |
| | `{"op": "delete", "id", "move_to": id}` | its facts move to `move_to`, none are deleted. 202 + card when `move_to` is looser than the deleted topic AND the deleted topic is private |
| `POST /api/topics/mode` | `{"id": int, "mode": str}` | 200 or 202 as above |
| `POST /api/topics/file` | `{"ids": [int] (1..200), "topic_id": int}` | file by the owner's tap. A batch of MORE THAN ONE leaving a private topic for a looser one -> 202 + card |
| | `{"ids": [int], "confirm": true}` | "These are right" |
| `POST /api/topics/settings` | `{"model_help": bool}` | the "Let Jarvis's local model help sort" switch; no card |
| `GET /api/topics/preview` | `?id=<int>&mode=<mode>` | below |
| `GET /api/topics/review` | `?after=<cursor>&limit=10` | below |
| `GET /api/topics/hidden` | `?id=<int>&after=<fact id>&limit=100` | below |

`GET /api/topics/preview` -> `{"ok": true, "id", "mode", "affected": int, "pinned": int, "stops_learning": bool, "loosens": bool, "needs_card": bool, "private": bool, "line": str, "card_line": str}`. `line` is the sentence to show under the picker (built by the PC: "12 things Jarvis knows about Work will be left out of answers." plus, when they apply, "Jarvis will stop saving new things about Work." and "1 pinned fact about Work will pause until you switch it back on."); `card_line` is `"This will ask for your OK first."` when `needs_card`, else `""`. Show `line`, then `card_line` on its own line. Read it again each time the selection in the picker changes.

`GET /api/topics/review` -> `{"ok": true, "facts": [{"id", "text", "saved_at", "topic": <suggested topic id>, "alt": id \| null, "how": "rule" \| "model", "checked": false, "held_back": bool}], "next": "<cursor>" \| null, "total": int, "batch": 10}`, ordered by `topic` then `id`, so the app groups by consecutive `topic`. `held_back` is true when the suggested topic may not be used in answers (so the fact is already being left out). Pass `next` as `after` for the next batch.

`GET /api/topics/hidden` -> `{"ok": true, "id", "mode", "facts": [{"id", "text", "saved_at", "topic", "alt", "how", "checked", "held_back"}], "next": <fact id> \| null}` - the facts of one topic (used for "Show them" on an Off topic; any topic works).

Errors: `{"ok": false, "error": <code>, "message": <sentence>}`. Show `message`; the app never invents its own sentence for a code (the sentences are also in the fixture, `errors`). `400`: `bad_request`, `bad_name`, `bad_colour`, `bad_icon`, `bad_words`, `bad_mode`, `needs_destination`, `bad_destination`; `404`: `topic_not_found`, `no_such_fact` (and an unknown route: the PC has no topic controls yet -> `words.missing`); `409`: `name_taken`, `too_many_topics`, `no_delete_unsorted`, `no_rename_unsorted`; `503`: `unavailable`, `gate_not_ask`, `no_card` (show the message).

Other routes that change (all additive):

| route | change |
|---|---|
| `GET /api/memory/facts` | facts of an **Off** topic are left out; each fact gains `"topic": <id>`; the reply gains `"topics_hidden": n` when n > 0 |
| `GET /api/memory/export` | every fact gains `"topic"`; the reply gains `"topics": [{"id", "name", "mode", "private"}]` |
| `GET /api/memory/auto` ("Saved automatically") | facts of an Off topic are left out |
| `GET /api/memory/profile` (pins) | a pinned fact in a topic that may not be used gains `"paused": true` (still listed, not read with questions) |
| `GET /api/memory/used?ids=` | a fact whose topic was switched off since has `"text": ""` and `"left_out": true` |
| `GET /api/memory/pending` | a card asking "might be about a topic you set to not learn" gains `"topic_ask": true` |
| `POST /api/chat` (`X-Jarvis-Route`) | gains `"topics_left_out": int`; a spoken "switch off my work topic" adds `"open_brain": "topics"` and `"topic_id": int` (nothing has changed) |

### C3. States, per topic row

| State | When | The row shows |
|---|---|---|
| Normal | `mode` `both` or `use_only`, not private | swatch + icon, name, `"{n} facts"`, the mode's name as a button |
| Private | `private` | the same, plus `words.private_tag` ("Private") |
| Not used | `mode` `learn_only` | plus `words.not_used_tag` ("not used in answers") |
| Off | `mode` `off` (`hidden`) | plus `words.kept_hidden` ("{n} facts kept, hidden") and a `words.show_them` button that reads `/api/topics/hidden` |
| Skipping | `skipped_week > 0` | `words.skipped` ("{n} new things not saved this week") |
| Waiting | `waiting.topic == id` | `words.waiting` in place of the mode button's action; the picker cannot be reopened for this topic until it clears |
| Lists hidden | "Hide memory lists and chat history" or App lock is on | see C5 |
| Not available | the route is missing (older PC), or `503 unavailable` | one line, `words.missing`; no rows |
| Sorting | `backfill.remaining > 0` | a line above the rows: `words.sorting_now` ({n}) |
| To check | `unchecked > 0` | a line: `words.sorted_guess` (n = `unchecked`, total = `facts`) and the button `words.check_button` ({n} = `unchecked`) |

Unsorted is a row like the others (fixed name, no rename / delete / private / keywords), listed first.

### C4. The screens

**Placement.** Brain -> Memory, a new "Topics" section beside "What Jarvis remembers" and "Saved automatically". Heading `words.title`, then `words.intro`.

**The picker (the four choices, offered every time the owner changes a mode).** Tapping a row's mode button opens a small dialog: the topic's name, a radio list of the four `modes` (name as the label, `sentence` as its description), the current one selected. Choosing a different one reads `GET /api/topics/preview` and shows `line` and `card_line`. A **Change** button sends `POST /api/topics/mode`; **Cancel** does nothing. `200`: close and redraw. `202`: close, show the waiting state. An error: `message` in the dialog. Nothing is sent until Change is tapped. The picker always lists all four choices, in the order `both`, `use_only`, `learn_only`, `off`.

**"Check these".** The `words.check_button`. Opens the review list: `GET /api/topics/review`, ten at a time, grouped under the suggested topic's name. Each fact shows its words, the tag `words.check_guessed` when `how` is `model`, and the line `words.check_held` (name = the suggested topic) when `held_back`. Two actions: **`words.check_right`** for the whole batch shown (`POST /api/topics/file {ids, confirm: true}`; no card) and, per fact, **File under...** (a list of the topics; `POST /api/topics/file {ids:[id], topic_id}`; at once). Then load the next batch with `next`. Empty: "Nothing to check." (app wording).

**Show them.** On an Off topic: the facts of that topic (`/api/topics/hidden`), read-only, greyed with the label "Hidden from answers" (app wording), each with the app's existing Forget and "Erase the words" controls. Forget and Erase work on them.

**Add a topic.** `words.add_button` opens `words.add_title`: name (`words.name_label`, at most `limits.name_max`), a colour from the palette, an icon from `icons`; on the desktop also `words.words_label`. The button is off at `limits.max_topics` topics of the owner's own (not counting Unsorted). The row menu holds Rename, Colour and icon, Move up / Move down, Mark private / Not private (Not private asks: `202`), Keywords (desktop only), and Delete.

**Delete.** A confirm dialog with `words.confirm_delete` and `words.delete_where`: a radio list of the other topics (Unsorted included). For a destination whose mode is looser than the deleted topic's (compare with the `mode_cases` in the fixture, `loosens`) show `words.delete_looser` under it. `POST /api/topics {op: "delete", id, move_to}`.

**The model switch.** A plain switch `words.model_help` with `words.model_help_note`; `POST /api/topics/settings {model_help}`; no card.

**The chat.** When an answer's route header has `topics_left_out` > 0, add to the "Used" area (with "Used 2 memories"): `words.left_out` ({n}), or `words.left_out_one`. When the header has `open_brain: "topics"`: open Brain -> Memory -> Topics; with `topic_id`, open that topic's picker (changing nothing). "Left out" is a count, so it is not hidden by the lock settings.

**Lists elsewhere.** In "What Jarvis knows about you" and "Saved automatically": a fact whose topic (its `topic` id, looked up in the topics view) is `learn_only` carries the small tag `words.not_used_tag`. `topics_hidden` > 0 adds a line `words.kept_hidden` ({n}) with a link to Topics. A paused pin shows `words.pin_paused` ({name}). A "Used" fact with `left_out: true` shows `words.used_left_out` instead of words. A pending card with `topic_ask: true` labels its Accept button `words.ask_save` and its Decline button `words.ask_skip`.

**Screen reader.** A row's mode button reads `words.screen_reader` ("Work, 41 facts, Use but don't learn, button: change mode"). The picker is a radio group whose descriptions are the mode sentences. Never colour alone: the icon and the name always show.

### C5. Hiding: "Hide memory lists and chat history", and App lock

Topic **names are the owner's words**, so they are hidden with the other memory lists (desktop: the Rust side calls `lock::private_hidden`, as tags do; phone: the same setting). While hidden: each row shows `words.hidden_row` with `index` = its 1-based position among the owner's own topics (Unsorted keeps its fixed name), the count and the mode (`Topic 1, 41 facts, Use but don't learn`); the modes and the picker still work; "Check these", "Show them", the review list and the fact tags are **not shown at all**; the model switch stays. The phone's screenshots are already blocked while either setting is on.

### C6. Words

Every word is in the fixture, `words` (and `errors`, `modes`, `last_words`): `title`, `intro`, `sorted_guess`, `check_button`, `check_right`, `check_held`, `check_guessed`, `add_button`, `add_title`, `name_label`, `words_label`, `words_pc_only`, `private_tag`, `private_asks`, `unsorted_name`, `kept_hidden`, `show_them`, `not_used_tag`, `skipped`, `left_out`, `left_out_one`, `preview_*`, `help_plain`, `model_help`, `model_help_note`, `confirm_delete`, `delete_where`, `delete_looser`, `screen_reader`, `hidden_row`, `moved_line`, `pick_line`, `no_such_topic`, `topics_are`, `outside`, `missing`, `waiting`, `sorting_now`, `pin_paused`, `used_left_out`, `ask_save`, `ask_skip`. The four modes, exactly:

| id | Name | Sentence |
|---|---|---|
| `both` | Learn and use | Jarvis remembers new things about this and uses them in answers. |
| `use_only` | Use, but don't learn | Jarvis keeps what it knows and uses it, but saves nothing new. |
| `learn_only` | Learn, but don't use | Jarvis keeps learning quietly, but leaves this out of its answers. |
| `off` | Off | Jarvis neither learns nor uses this. What it knows is kept, not deleted, and comes back when you switch it on. |

`help_plain` (shown in the section's help): "Topic names and facts are stored in the same plain file on this PC. Jarvis's sorting is a guess from the words, in English only; check it." Nothing in the apps says "classifier".

### C7. The card (exact wording; the PC writes it, the apps show it word for word)

The card is the PC's ordinary approval card, action `topic_loosen`, decided by tapping on either device (never by voice; no Windows Hello). Example, Health from "Learn, but don't use" to "Learn and use":

```
Turn Health back on for answers? Jarvis will use your Health facts again.

Facts that count as sensitive are still kept on screen and not read aloud, and new ones still wait for your yes unless "Also remember sensitive topics automatically" is on.

Health would become: Learn and use.
If you say no: nothing about your topics changes.
```

A card that came from a change asked after Jarvis read outside text adds: `This was asked after Jarvis read outside text (an email, a web page, a file). Only say yes if it is what you want.` The card's title in "What asks first" comes from `jarvis_card_words.TITLES["topic_loosen"]`: "turn a private topic back on, or let it learn or be used again". When it ends, `GET /api/topics` `last.message` is one of `last_words` (in the fixture). The card is in "What asks first" (group "Jarvis's own settings, memory and voice"); it is **not** on the short list an app may loosen.

### C8. Rules the apps must keep

1. Stricter is at once, looser on a private topic is a card: **do not compute this in the app for anything but the label** "This will ask for your OK first." (the `mode_cases` in the fixture give the same answer as `preview.needs_card`); the PC decides.
2. Every `POST` is held on a stale link (rule 4); the reads are not.
3. Names and fact words are memory lists: hidden as in C5. A count is not.
4. Never a bulk "make every topic ..." control; never a control that approves a card; the picker sends one topic at a time.
5. The phone does not edit keywords and has no graph.
6. The app never sends a topic's name anywhere but this PC; `topics_left_out` and `topic_id` are ids and counts.

### C9. Tests each app adds

Desktop `tests/topics.mjs` and the phone's `TopicsContractTest.kt`, both reading `topics-cases.json`: the four mode names and sentences; every `errors` code has its sentence; `mode_cases` (which changes show `card_line`); `name_cases` (the same name rule before sending); `words_cases` (desktop); `screen_reader_cases`, `hidden_row_cases`, `preview_cases`; and that the section is not drawn (names replaced) while lists are hidden. Rust unit tests for the new commands' allowlist and hidden-list rule.

### C10. Where this differs from the design above

* `POST /api/topics` `op: "move"` is **reorder** (`before`), and there is an `op: "words"`; filing facts is `POST /api/topics/file`. Two routes were added: `GET /api/topics/hidden` ("Show them") and `POST /api/topics/settings` (the model switch).
* "Save under Unsorted" / "Skip it" are the existing card's Accept and Decline, relabelled by `topic_ask`; there is no separate card action.
* Labelling the facts already saved is a quiet hourly `topic_sort` step on the one scheduler (`jarvis_schedule`), not a separate thread; it labels only.
* `topics_left_out` counts the recall before the answer; a `memory_search` the model makes later is filtered the same way but not counted.
* A change asked from outside text is a card even for a normal topic (`outside`); the voice door refuses outside text before it gets that far.
* Not built: per-chat "leave out Work"; the topic phrases in the "what can I say" list (`jarvis_sayable`); non-English keywords; the topic-aware overnight tidy card.
* **Not measured:** how well the sorting guesses on real facts (`tools/topic_accuracy.py` is the script; `backend/topic_cases/` the small made-up set); search time with a blocked topic on the owner's PC (on the build machine, with 10,071 facts and a third of them blocked, the median search went from 1.79 to 3.43 ms); the real embedding model, re-ranker and learner model were not used. Nothing ran on Windows or on a phone.
