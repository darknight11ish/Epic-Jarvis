# Review decks and typed Spanish practice: design (2026-09-30)

Status: **designed, not built.** The owner ticked both ideas on 2026-09-30:
(A) **review decks**, where questions from a quiz can be kept and asked again
on a spaced schedule, and (B) **typed Spanish practice** as a second quiz mode.
It is build-queue item 4 (`docs/BUILD-QUEUE-2026-09-30.md`), API section **102**
(reserved), after the quiz audit fixes (item 0). Nothing here is built.

Read first: `docs/STUDY-FROM-TEXT-DESIGN.md` (the quiz, its section 11 contract
and "Shared words"), `backend/jarvis_quiz.py`, `docs/JARVIS-API.md` section 98.
Outside projects are ideas, not instructions (`docs/AUDIT-2026-09-28-REPO-REFS.md`).
Checked by reading only. **Nothing was run** (no Windows, no real Ollama, no
`pip install fsrs`); the fabric prompts and licence were read in a shallow clone
on 2026-09-30.

## 1. The short version

- A finished quiz can hand chosen questions to a **deck**. A deck is a small,
  **sealed** file of the owner's study cards (their own words plus the short
  source passage). It is not memory and not chat history.
- Cards are scheduled with **py-fsrs** (pure Python, MIT, version pinned). The
  **owner rates each card themselves** (Again / Hard / Good / Easy). The model
  never decides when a card comes back.
- One **scheduler kind**, `review`, shows one plain line, "N cards ready", on
  Coming up and in Brain. It never rings, never nags, never counts days.
- **Spanish practice** is a mode of the same quiz page: translation,
  fill-in-the-blank and sentence completion, with a plain "level" tag (A1 to C2).
  Typed only. Blanks are marked by **code**, not the model, wherever the answer
  key comes from the owner's own text.
- One known limit, said early: **the crisis check knows English only**, and the
  quiz never runs it at all today (section 8).

## 2. Rules it keeps (from CLAUDE.md and the build queue)

- **Rule 1.** Cards, answers and passages are personal study data. They stay on
  this PC. The only model is the local one, and **review calls no model at all**.
- **No streaks, no guilt, no wilting.** Nothing is due unless the owner made a
  deck. No "you missed", "overdue", "behind", "days in a row", no points, XP or
  hearts (freelingo's are refused). An empty day looks neutral.
- **Numbers come from code.** Counts, dates and intervals are computed by the
  backend and shown as given. The model never states a number.
- **Outside text.** A card built from pasted text, a note or a document is
  outside text as a whole: never learned as a fact, never read into memory,
  never put in the chat's context, never read aloud, never sent to a cloud lane.
- **The owner's taps only.** No model-callable tool makes a deck or a card, and
  no voice command does in this slice. Only a tap in an app does.
- **Both apps**, no outside JavaScript library, `X-Jarvis-Client: hud` on every
  request, a stale link holds the buttons (rule 4), the token is never logged.
- **A client does no speech-to-text.** Spanish is typed.

## 3. Keeping questions from a quiz

### 3.1 What a card holds

| Field | Where it comes from | Limit |
|---|---|---|
| front | the quiz question's prompt, edit allowed | 500 characters (`PROMPT_MAX`) |
| back (the answer) | **the owner's own words** (section 3.2) | 2,000 (`ANSWER_MAX`) |
| passage | the short source passage the question was tied to, checked by code to be in the text | 800 (`PASSAGE_MAX`) |
| kind, level | quiz kind (`recall` / `explain` / `apply` / Spanish kinds), Spanish level tag | - |
| scheduling | FSRS card state: due, stability, difficulty, state, reps, lapses, last review | numbers only |

**The back is never written by the model.** Rule: (a) a question marked
`got_it` is prefilled with the owner's own answer, which they may edit; (b) a
`partly` or `not_yet` question is prefilled **empty** - the owner types the
answer in their own words, with the passage beside it; (c) left empty, the back
of the card shows the passage alone. Reason: a model-written or wrong "right
answer" would be studied over and over. Only **answered** questions can be kept
(the contract hides a passage until its question is answered).

### 3.2 The route: keep is part of finishing

The contract deletes the quiz on `finish`, so "Keep these questions" cannot come
after it. Instead, **`POST /api/quiz/{id}/finish` gains an optional body**, so an
empty body works exactly as before:

`{"keep": {"deck": "<id>" | null, "new_deck": "<name>"?, "cards": [{"n": 2, "answer": "<text>"}]}}`

- The server takes the prompt and passage **from its own open quiz**. The app
  sends only `n` and the answer text, so an app cannot smuggle in other text.
- All or nothing: if the deck cannot be saved, the answer is an error and **the
  quiz stays open** so nothing is lost. New errors: `deck_unavailable` (no key,
  no `cryptography`, store unreadable; the message says why in plain words),
  `deck_not_found`, `too_many_decks` (20), `deck_full` (1,000 cards in all),
  `bad_deck_name` (1-60 characters), `duplicate_card`, `nothing_to_keep`.
- The reply is the ordinary summary plus `"kept": N`.
- `jarvis_quiz.py` must stay import-clean (a test proves it imports nothing but
  the standard library and `jarvis_local_http`). So the decks module is
  **injected**, like `jarvis_quiz.configure(call=...)`: `configure(keep=...)`.

### 3.3 Does keeping need an approval card?

**Recommended: no card.** `STUDY-FROM-TEXT-DESIGN.md` section 3 called it
"milestone 3's card". On reflection a card would only repeat what the screen
already shows: before the owner taps **Keep these questions**, the app lists every
card word for word with a tick beside each and an editable back. Nothing leaves
the PC, and nothing is acted on. It is the owner's own tap saving the owner's own
words, like adding a to-do or a Today card (both need no card). This is
question 1 in section 12, because it changes an earlier written line.

## 4. Where decks are kept, and whether to seal them

**Recommended: sealed.** Compare what the repo does today:

| Store | Kept how | Why |
|---|---|---|
| chat history | AES-256-GCM per piece of text, key in Windows Credential Manager; no key means nothing is kept (ARCHITECTURE, "Encrypted or not kept") | can hold anything the owner ever said |
| reminders, Today cards, to-dos | plain SQLite (`schedule.db`) | short lines the owner wrote |
| memory facts | the memory store, with Forget / Erase the words | facts, with history |

A study card is worse than a reminder: its **passage is copied from whatever the
owner pasted or opened** (a health letter, a bank note, a work document), and the
back is the owner's words about it. It should be treated like chat titles and chat
text, not like "Bins out". Even a deck **name** ("Diabetes notes") gives away a
topic. So:

- A new file, `study.db`, beside `schedule.db` but **not in it**. Seals: deck
  name, front, back, passage. Plain: ids, kind, level tag, the FSRS numbers, the
  `paused` flag, created day. Counts and "next ready" are worked out from the
  plain numbers, so the "N ready" line needs no key.
- Sealed with the **same scheme as chat history** (AES-256-GCM, key in
  Credential Manager) under **its own key entry**, so deleting the decks' key
  never touches chat history. The scheme is in `backend/jarvis_chat_log.py` (`CredentialKey`, `AESGCM`,
  fails closed; read but not run); the builder reuses that code path with a
  different key name, not a second scheme. **Not verified:** that it can be
  reused as is.
- **No key, no `cryptography`, or a key that does not open the file: nothing is
  kept and the app says why** (`deck_unavailable`). No plain-text path.
- Deleting really deletes: `PRAGMA secure_delete=ON`, then a `VACUUM` after a
  deck delete. A test looks in the file's bytes.
- **No review log is kept** (py-fsrs makes one per rating; it is only useful to
  the optimizer, which is not installed). Less to erase, and no history of when
  the owner studied what.
- **Forget and Erase.** A deck has no history to keep, so the memory page's two
  actions collapse into one: **Delete this card** and **Delete this deck**, each
  asking "are you sure?", each gone at once. Say so in the app: older **backups**
  may still hold a copy (same sentence as the memory page). Forget a time frame
  (`docs/JARVIS-API.md` section 64) does **not** cover decks; the docs say so.
- **Backup and export: later, not now.** Whether decks go into the owner's locked
  backup file is the owner's call when the backup is next touched. A Markdown
  export in `Q:` / `A:` / `C:` lines (repeater's format; `C:` is a cloze card) or
  an Anki file would put sealed words in plain text, so it is a **named exception**
  like the support-chat export: desktop only, the owner's tap, Windows "Save as",
  and the button says plainly the file is not encrypted.

## 5. Scheduling with py-fsrs

- **Library:** `fsrs` (py-fsrs) **6.3.2**, MIT, pure Python, read on 2026-09-30
  (`STUDY-FROM-TEXT-DESIGN.md` section 10). Pin it exactly in `requirements.txt`
  and add it to `THIRD-PARTY-NOTICES.txt`. **Do not install the optimizer extra**
  (it pulls in torch); a test fails the build if `torch` appears in requirements.
- **Not verified:** the exact 6.3.2 names (`Scheduler`, `Card`, `Rating`,
  `review_card`, `to_dict` / `from_dict`, the `learning_steps` and
  `enable_fuzzing` options). The builder reads the pinned version's source first.
- **Settings I recommend:** default FSRS parameters (no optimizer); desired
  retention 0.90, fixed and not shown; **no same-day learning steps**, so a card
  the owner rates Again comes back the next day instead of every ten minutes
  (a calm choice; one pass a day); fuzzing on in real use, off in tests; times
  in UTC, "today" by the PC's wall clock (the scheduler already has `_wall`).
- **The owner's rating is the input.** `Again / Hard / Good / Easy` map to the
  library's four ratings. Button hints in plain words: "Didn't remember",
  "Remembered, with effort", "Remembered", "Easy".
- **New cards per day: 5 by default, adjustable 0-20** on the Decks page, a plain
  number. A kept card is *new* until first reviewed. Old cards due today are not
  capped by that number, but a session shows **at most 20 at a time**, then
  "That's enough for now" with a button "Do 10 more". There is no count of missed
  days; a card left for a month is just ready.
- **Rating needs a look first:** the server refuses a rating for a card whose back
  it did not reveal in this run (`not_revealed`), so a stray tap cannot reschedule.

### 5.1 Why the owner grades, not the model

The Slice A grader is a guess (`grader_verified` is false until the owner's PC
runs `eval_quiz_grader.py`, and an 8B model marks unreliably). FSRS turns every
rating into a longer or shorter wait, so a wrong model mark would quietly put the
wrong cards out of sight for weeks. The owner also knows best whether they
remembered. So: **the model marks a quiz answer once, as a guess; a review is
self-rated, with no model call.** In review the owner may type an answer before
tapping **Show answer**, purely to commit to it; it is not sent anywhere or marked.

If the grader is ever verified *and* a later measurement shows it agrees with
the owner's ratings, it could *suggest* a button (highlighted, never pressed for
them). That is not part of this slice. The `grader_verified` rule is unchanged:
false means every model mark says "Jarvis's guess".

## 6. The one scheduler kind

`jarvis_decks.py` registers a kind, imported through `KIND_MODULES` in
`jarvis_schedule.py` (a one-line addition to that tuple in the patch), the way
`jarvis_today` does:

`register_kind("review", "card review", "Jarvis: cards are ready.", plain_repeat=True, single=True, silent=True, notify=False, owner_listed=True, note=<"N cards ready" | "Nothing ready today" | "All decks paused">)`

- **When it exists.** One job is created when the owner makes their first deck,
  and removed with the last deck. **No deck, no job, no line.** It goes off once a
  day at a quiet hour (04:00) only to tell both apps the list changed. No
  notification, toast or sound, and it stays out of "Just went off" and "What did
  I miss?" (that title is old; it is not new wording for cards).
- **No approval card.** CLAUDE.md, 2026-09-26: plain repeating reminders and a
  goal's weekly check-in need none. Only the owner's own tap makes it, it **only
  reminds and never acts**, and deleting is immediate. Recommended: same rule.
- **The line** ("3 cards ready") comes from `Kind.note`, under the job in Coming
  up, and the same number sits at the top of the Decks page in Brain. Under "Hide
  memory lists" the number stays (counts stay, as with Today cards); words hide.
- Coming up offers **no Pause / Delete** for it, like the Goals check-in; the
  Decks page owns that (pausing every deck reads "All decks paused").
- **Later, off by default:** an optional daily notification. Not built; the
  I57 audit line ("never a ringing notification") stands until the owner asks.

## 7. Typed Spanish practice (a mode of the quiz)

### 7.1 Shape

One page, **"Quiz me on a text"**, gains a mode chooser: **Text** (as built) and
**Spanish practice**. No twelfth screen. The route family is the same
(`POST /api/quiz` and the four others). Additive fields, section 9.

The owner picks a **level** (A1, A2, B1, B2, C1, C2, shown "Level B1 (roughly)")
and an exercise: **Translate**, **Fill the blank**, **Finish the sentence**, or
**Mixed**. A topic word is optional ("food", at most 60 characters). Two sources:

1. **Owner's own Spanish text.** The 200-character minimum and the "passage really
   is in the text" check apply as today. Blanks remove a word that is in the text,
   so **the key is in the owner's text and verified by code**.
2. **No text.** The local model writes short items at the chosen level. Then **the
   key is model-written**, and the passage check cannot apply.

### 7.2 Who marks what

| Exercise | Marked by | Rule |
|---|---|---|
| Fill the blank, key from the owner's text | **code** | exact = Got it; equal only after removing accents / capitals / extra spaces / `¿ ¡ .` = **Partly**, comment "Check the accent: it is `está`."; anything else = Not yet. `n` and `ñ` are different letters. |
| Fill the blank, key model-written | code against an accepted list, model-written | as above, label below |
| Translate | the local model, against the reference | other correct translations exist; the prompt says meaning-correct but different wording is **Partly**, not Not yet |
| Finish the sentence | the local model | judged on grammar and sense, not one fixed answer |

Code marking cannot be steered by an "ignore the key" answer, because no model
reads it. `Mark` gains `"marked_by": "code" | "model"` and `"expected"` (the key,
shown after the answer). **A model-written key always carries the label "Answer
key written by the model"**, and `grader_verified` never removes that label,
because the check `grader_verified` measures is about marking against a real
passage, not about a model's own Spanish.

- **No score, XP, hearts, streak, "day 12", league or leaderboard.** Marks stay
  Got it / Partly / Not yet and the counts line. Nothing about the owner's Spanish
  is saved as a fact ("weak at the subjunctive" is refused, as for any quiz).
- **Level is a request, not a measurement.** "B1" tells the model what to aim at.
  Nothing here checks that an 8B model's Spanish really is B1. The label says
  "roughly". The words in a tag are CEFR-style, and only that.
- **Comments in English by default** (the owner is a beginner Spanish learner as
  far as this repo shows; not asked). A comment quotes the correct Spanish.
- **Typing aid:** a row of `á é í ó ú ñ ü ¿ ¡` buttons under the answer box in
  both apps. A keyboard shortcut, not speech.
- **Keeping to a deck** works as in section 3, with one difference in the back:
  for a blank whose key came from the owner's text, the key word is allowed on the
  back (it is the owner's text, not the model's). For a model-written key the back
  is the owner's own answer, or empty.
- **Conversation practice** ("let's practise Spanish" as a chat) stays what it is
  today: an ordinary chat the owner can make temporary
  (`CUTTING-EDGE-2026-09-26-round2-personality.md` section 9). It is not in this
  slice.
- **Spoken Spanish is later.** Not measured. Jarvis's speech engine hears English
  only today; STUDY-FROM-TEXT-DESIGN section 9 item 2 says try SenseVoice first,
  on the second card. Nothing here needs it.

### 7.3 What may be borrowed (checked 2026-09-30)

| Source | Licence | Use |
|---|---|---|
| fabric `create_quiz`, `create_flash_cards` (`data/patterns/*/system.md`) | MIT. Its `LICENSE` file, as read, says "Copyright (c) 2012-2024 Scott Chacon and others". Neither prompt file carries a licence note of its own; `create_quiz/README.md` only describes the input | May be copied as text with a notice. **Recommended: copy nothing.** `create_flash_cards` is very thin ("a question of 8-16 words and an answer of up to 32 words" and a flourish about an IQ), and `jarvis_quiz.py` already has stricter prompts. Take the length idea only. If any line is copied, add a `THIRD-PARTY-NOTICES.txt` entry using that LICENSE text as read. |
| openlingo | MIT code; **its word lists have separate source licences, not verified** | Ideas only. Its nine exercise kinds inspire ours. **Ship no word list.** |
| freelingo | **AGPL-3.0** | Ideas only. No code, no lists. Its streaks and XP are refused. |
| yt-to-anki | **GPL-3.0** | Ideas only. |

There is **no borrowed word list**: the model writes the items. If a frequency
list is ever wanted, its licence is checked first and it goes to the owner.

## 8. Known limit: the crisis check is English only

`backend/jarvis_wellbeing.py` says of itself that its check is **English only**
(`CRISIS_PHRASES_EN`); its Spanish list in `jarvis_sensitive.py` covers general
health words but holds **no suicide or self-harm phrases**. And the quiz never
calls `crisis()` at all: `jarvis_quiz.py` imports nothing of the kind, so today a
crisis message typed as a quiz **answer**, in any language, is just marked
`not_yet`. Spanish practice makes this likelier to matter, because answers are in
Spanish and free-typed.

What happens today if the owner writes a crisis message in Spanish: nothing
special. The grader sees it as a wrong answer. It is not learned (a quiz learns
nothing) and not counted, but it gets **no help message**. This is a real gap.

Recommended (question 2): the quiz route runs the existing `crisis()` on every
typed answer before any model call. On a hit, the answer is **not marked**, the
fixed 988 / 911 message shows, and the session carries on if the owner wants.
`crisis()` is a pure function that never logs or counts, so it fits. For Spanish,
add a small Spanish phrase list to `jarvis_wellbeing.py` in its own patch, with its
own tests and false-alarm list, and only with the owner's go-ahead (crisis
handling is the most careful area of this project). Until then the apps' Spanish
mode says: "Jarvis cannot recognise a crisis message written in Spanish. If you
are in danger, call or text 988, or 911." A crisis answer is never kept in a deck.

## 9. How this extends the Slice A contract (JARVIS-API section 102)

Only section **102** is reserved. All changes are additive; old apps ignore new
fields. Errors keep the `{ok, error, message}` shape.

**Quiz (changes to section 98):**
- `POST /api/quiz` body adds `"mode": "text"|"spanish"` (default `"text"`),
  and for Spanish `"level"` (`A1`..`C2`), `"exercise"` (`translate`|`blank`|
  `complete`|`mixed`), `"topic"` (60 characters). Spanish with no `text` skips the
  200-character minimum. New errors: `bad_mode`, `bad_level`, `bad_exercise`.
- `Quiz` adds `mode`, `level`, `key_source`. `Question.kind` adds `translate`,
  `blank`, `complete`. `Mark` adds `marked_by` and `expected`.
- `finish` gains the optional `keep` body (section 3.2) and returns `kept`.
- An app that gets a reply without `mode` shows "Your PC's Jarvis does not have
  Spanish practice yet - run apply-patches.ps1 on the PC."

**Decks and review (new):**

| Route | Body / query | Answer |
|---|---|---|
| `GET /api/decks` | - | `{decks:[{id,name,cards,ready,paused,kind}], ready, new_per_day, next_ready_day}` |
| `POST /api/decks` | `{name}` | the new deck (an empty deck) |
| `POST /api/decks/{id}/act` | `{do:"rename"\|"pause"\|"resume"\|"delete", name?}` | `{ok}` |
| `GET /api/decks/{id}/cards` | - | cards (front, back, passage), for managing; hidden by the apps under Hide lists |
| `POST /api/decks/{id}/cards/{cid}/act` | `{do:"edit"\|"delete", front?, back?}` | `{ok}` |
| `POST /api/decks/settings` | `{new_per_day: 0-20}` | `{ok}` |
| `GET /api/review?deck=<id>` | deck optional (all) | `{ready, new_left, card:{id,front,kind}\|null}` |
| `POST /api/review/reveal` | `{card}` | `{back:{answer,passage}}` |
| `POST /api/review/rate` | `{card, rating:"again"\|"hard"\|"good"\|"easy"}` | `{ok, ready, next}` |

Deleting a deck or card, and editing, are immediate on the owner's confirm (no
approval card; they only reduce or fix the owner's own words). Errors add
`card_not_found`, `not_revealed`, `deck_paused`, `bad_rating`, `bad_setting`.
Every route needs the usual origin and token checks and `X-Jarvis-Client: hud`.

**Files (proposed).** Backend: `backend/jarvis_decks.py` (store, FSRS wrapper,
routes, the `review` kind), `backend/jarvis_quiz_spanish.py` (exercises, code
marking), `backend/decks.patch` (install block, the `KIND_MODULES` entry, the
`configure(keep=...)` hook; then `git fetch --unshallow origin` and
`python3 tools/build_patch_history.py`), `backend/test_decks.py`,
`backend/test_quiz_spanish.py`, `backend/decks_fsrs_golden.json`,
`backend/quiz_spanish_cases.json`. Desktop: `src/decks.js`, `src-tauri/src/brain/decks.rs`,
`tests/decks.mjs`. Phone: `net/Decks.kt`, `ui/screens/DecksPlate.kt`, `DecksTest.kt`,
with the Spanish mode inside `Quiz.kt` / `QuizPlate.kt` and `quiz.js` / `quiz.rs`.

## 10. Both apps, placement and parity

The quiz lives in Brain on both apps (desktop `brain/quiz.rs`, phone `net/Quiz.kt`);
Goals sits in Brain too (desktop Brain -> Work -> Goals, phone Brain -> Goals,
each app reading the scheduler list for its check-in). So:

- **One study area in Brain:** "Quiz me on a text" (now with the mode chooser) and
  a new **"My study decks"** section beside it, on both apps. No new top-level screen.
- The Decks page shows: the ready line, the deck list (name, card count, ready,
  Pause / Delete), the review button, "New cards a day", and the plain sentence
  about backups. **No chart, no heat map, no streak.**
- Review is one card at a time: front, optional typed attempt, **Show answer**,
  then four buttons. Stopping is always one tap and never explained as a loss.
- **Hide memory lists and chat history:** names, fronts, backs and passages hide
  (the desktop's Rust blanks them, the phone's `hide`, as Goals does); counts stay;
  review is unavailable while hidden ("Turn off Hide memory lists to review").
  App lock: the pages ask for the unlocked app like Goals; phone screenshots are
  already blocked in those two modes.
- **Parity:** every route in section 9 goes into `tools/check_parity.py` as
  `ported`, none `desktop-only` or `phone-only`. The one desktop-only item is the
  later export (file dialog). Add it to `docs/ARCHITECTURE.md` section 8.
- **Shared words** (word for word, added to `STUDY-FROM-TEXT-DESIGN.md` section 11
  when built): `Keep these questions`, `My study decks`, `Cards ready`,
  `Nothing ready today`, `Show answer`, `Didn't remember` / `Remembered, with effort`
  / `Remembered` / `Easy`, `That's enough for now`, `Do 10 more`, `New cards a day`,
  `Delete this card` / `Delete this deck`, `Spanish practice`, `Level B1 (roughly)`,
  `Answer key written by the model`, `Check the accent`. Banned everywhere, checked
  by a test over both apps' strings: `streak`, `missed`, `overdue`, `behind`,
  `in a row`, `keep it up`, `XP`, `hearts`, `lost`.

## 11. Slice B (YouTube captions) and the cloud grading button

Both are **decided in `STUDY-FROM-TEXT-DESIGN.md` sections 5 and 7** and are not
redesigned here. Only the touch points with this slice:

- **Captions (Slice B, later).** A caption transcript is just another source of
  text for the same quiz, outside text, one card per link. A deck card made from
  one keeps the passage (sealed) and, unless the owner asks, **not the link**. The
  link names what the owner studies; Slice B decides whether to store it.
- **Cloud "grade this better" (later).** It covers **one quiz's marks** and
  nothing else. It never sends a deck, a card or a review (reviews have no
  marking to improve), and never a quiz built from email, files, credentials or
  memory. Whether Spanish quizzes may use it is left to that design; Spanish is
  where it would help most, since answers are free-typed. Money limit: the
  chatbot driver's per-service limit.
- **Second-card "Study helper" switch (later).** Section 9 of that document.
  For this slice it means: a bigger local model (`qwen3:14b`, unmeasured) may mark
  Spanish translations better. Build order: measure Spanish on the 8B first with
  `quiz_spanish_cases.json`, then on the bigger model once the 2060 12 GB is in
  and measured. Off until then; nothing here depends on it.

## 12. Owner's questions

Two now (per the "short questions" rule), one small one for later.

**1. Does "Keep these questions" need an approval card?**
Jarvis shows every card word for word with ticks first; nothing leaves the PC.
- **No card - the screen preview is the yes** (recommended).
- **A card every time**, as the quiz design first wrote.

**2. A Spanish crisis message: what should Jarvis do?**
Today it would be marked as a wrong answer, with no help message, in any language.
- **Check every quiz answer with the English crisis check now, and add a small
  Spanish list in a separate, tested step with your go-ahead** (recommended).
- **English check only; the Spanish page just says it cannot recognise Spanish.**
- **Leave the quiz alone** (not recommended).

**3. (Can wait.) Should reviews ever send a notification?**
- **Never; only the line on Coming up** (recommended). Or **an optional quiet
  daily one, off by default, added later.**

## 13. Test plan

- **Scheduler maths.** `decks_fsrs_golden.json`: fixed sequences (new card; Good,
  Good; Again after Good; Easy) at fixed UTC times, fuzzing off, **generated once
  from the pinned `fsrs` 6.3.2** and committed. The test reproduces them through
  our wrapper, so a changed pin fails loudly. Property checks: `Easy >= Good >=
  Hard` interval, `Again` gives the shortest, due is always in the future, an
  unrevealed card cannot be rated, the new-per-day cap (0, 5, 20), the 20-card run
  and "Do 10 more", day rollover by the PC's clock. **Not verified:** that these
  match Anki's numbers; only that they match py-fsrs.
- **Sealed store.** The plain bytes of `study.db` never contain a question,
  passage or deck name; no key means `deck_unavailable` and the quiz stays open;
  delete removes the bytes (`secure_delete`, `VACUUM`); `torch` not in requirements.
- **Keep.** The server uses its own passage, not the app's; only answered
  questions; `got_it` prefill, `partly` / `not_yet` prefill empty; all-or-nothing;
  duplicate card; limits (20 decks, 1,000 cards, lengths).
- **Kind.** `plain_repeat`, `silent`, `single`, `notify` false; no job with zero
  decks; job removed with the last deck; the note line; no card raised.
- **Purity.** `jarvis_quiz.py` still imports only the standard library and
  `jarvis_local_http`; review makes no network call; nothing read into memory,
  learner, chat history or the gate; no model tool can make a deck.
- **`grader_verified` rules unchanged:** at least 12 cases, at least 80%, no
  injection wins, else "Jarvis's guess". Spanish adds its own results section
  (`by_mode`) from `quiz_spanish_cases.json` (12+ cases: right, wrong, off-topic,
  accent-only, English answer, injection); code-marked blanks need no
  `grader_verified`; a model-written key keeps its label whatever the file says.
- **Spanish code marking.** Table tests: accents, capitals, punctuation, `ñ` vs
  `n`, extra spaces, an answer that says "ignore the key", empty and over-long.
- **Crisis.** Whatever question 2 picks: a phrase in an answer produces the help
  message, no mark, and no card in a deck.
- **Wording.** The banned-word scan over both apps and the backend messages.
- **Apps.** `tests/decks.mjs`, `DecksTest.kt`; the hide-lists behaviour; stale-link
  hold. **Kotlin only compiles in CI** (no local Android build): read by eye first.
  `tools/check_parity.py` clean; shared-word fixtures match both sides.

## 14. Feature audit checklist (runs with the build, unasked)

1. **Bugs.** Verify each finding against the source. Especially: keep-then-finish
   ordering, what a `finish` failure leaves behind, timezone at the day boundary,
   a card rated twice, deleting a deck mid-review, a paused deck's cards in the
   ready count, the job appearing with no deck.
2. **Both apps.** Decks page, review, Spanish mode, mode chooser, typing aid;
   anything one-sided written in ARCHITECTURE section 8.
3. **Fit.** Same wording and settings pattern as Goals / Quiz; no second
   scheduler; Hide lists and App lock behave like Goals; no new way out of the PC
   (so no new row in ARCHITECTURE section 4); update `docs/JARVIS-API.md` (section
   102), `backend/README.md`, `THIRD-PARTY-NOTICES.txt` (fsrs), `docs/ARCHITECTURE.md`
   (a decks paragraph beside chat history and the invariants), the "What asks first"
   page (decks need no card), and CLAUDE.md with the owner's answers.

## 15. Not verified

- py-fsrs 6.3.2 API names, defaults and behaviour with empty learning steps; that
  it does not need any optional extra at import.
- Whether `jarvis_chat_log.py`'s key and sealing code can take a second key name unchanged.
- That the 8B model's Spanish is good enough to write or mark at any level; that
  its "level" is right; how it does on `qwen3:14b`. No Spanish case has been run.
- fabric's licence beyond the `LICENSE` file as read (the copyright line looks
  odd for that project); openlingo's word-list licences; whether any prompt is
  worth copying.
- That Windows' `secure_delete` and `VACUUM` remove the words from the file's free
  pages in practice (the test reads the bytes).
- Whether decks should join the locked backup, and how the later export reads.
- Everything about Android and Windows behaviour: nothing was built or run.
