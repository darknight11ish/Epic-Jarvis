# Creativity audit: where Jarvis could be in 6-12 months (the "big swings" lens)

Written 2026-09-25. Read only: nothing in the repo was changed.

**How far to trust this.** Every claim about Jarvis names the file I read it
in. Claims about what is possible on local hardware come from pages I list at
the end, split into "read the page itself" and "only saw a search summary".
Many sites are blocked here (huggingface.co, home-assistant.io and qwen.ai all
refused me), so several outside facts are summary-only and marked that way.
Anything I am guessing at is marked **(speculation)**.

---

## 0. The short answer

- **Jarvis's future is not "a smaller ChatGPT". It is "the assistant that is
  allowed to read everything, because nothing it reads can leave".** A cloud
  assistant has to ask you to upload your notes, your email and your home's
  sensor history, and most people should say no. Jarvis already has all three
  on the same PC, with a gate in front of every way out (ARCHITECTURE §4).
  The best big ideas all lean on that.
- **The second card is the turning point.** Today one 8 GB card does chat and
  everything else waits its turn. With the 12 GB RTX 2060, Jarvis gets a
  second "mind" that can think in the background (read, summarise, look at
  pictures) without slowing chat. Almost all the plumbing for that is already
  built and switched off (`backend/jarvis_second_card.py`, `docs/SECOND-CARD.md`).
  What is missing is the *reasons to use it*. This report is mostly those
  reasons.
- **My top three:** (1) "Ask my own stuff" - one question across your notes,
  your wiki and (if you decide so) your own past chats; (2) Local eyes -
  Jarvis sees your screen and your phone's photos, and shows you where to
  click instead of clicking; (3) Goals with one card per step - you give
  Jarvis a goal, it proposes a plan, and every step that acts asks first.
- **The biggest trap:** things that look like progress but break the rules -
  an "always allow" for routines, a screen recorder, a family mode where
  other voices can give orders, fine-tuning on your data. Section 4.
- **One honest caution up front:** most of what Jarvis already has is marked
  "Not run on the owner's PC" (ARCHITECTURE §10, item after item). The
  biggest single win in the next month is not a new idea. It is installing
  the second card, running what is built, and measuring it. Every idea below
  is safer to start once that is done.

---

## 1. Jarvis's unfair advantages

These are things the big cloud assistants **cannot** copy without changing
their business, not just things Jarvis happens to have.

| # | Advantage | Why a cloud assistant cannot match it | Evidence in the repo | How to lean in harder |
|---|---|---|---|---|
| 1 | **It may read the most private things, because they never leave.** | Uploading your whole vault, inbox and home history to a company is a trust problem no policy fixes. Meta's Muse, for example, asks for passport photos and bank links, and reviewers called that "a guise to upload more data" (COMPETITORS-MUSE §2, from summaries). | ARCHITECTURE §4 (only named lanes leave the PC); `test_obsidian_notes.py` proves note search reaches the local model only. | Build features whose *whole point* is reading private material: section 2, ideas 1, 5, 6. |
| 2 | **One card per action, no approve-all, ever.** | Every big competitor has "always allow" (Muse, ChatGPT app permissions) or auto-approves (OpenClaw, goose, Open WebUI defaults - COMPETITORS-OPEN-SOURCE §1). | ARCHITECTURE §2 invariant 3; `test_gate_outcome.t_there_is_still_no_approve_all`. | Make *bigger* things possible under the same rule: a plan of several named steps is one decision (ARCHITECTURE §2, "What no approve-all actually means"). Ideas 3 and 7. |
| 3 | **Memory only from the owner's own words, with dates and "Erase the words".** | Cloud assistants learn from connected apps and email by design; "forget" is "to the best of its ability" (Muse, summary). | ARCHITECTURE §5; `jarvis_auto_learn.py`, `jarvis_past.py`, `memory-erase.patch`. | A life timeline built from those dated facts (idea 5), never from outside text. |
| 4 | **It knows it is you.** A voice check on every spoken turn. | None of the open-source peers checks whose voice it is (COMPETITORS-OPEN-SOURCE §1, grepped); cloud voices do not either. | `jarvis_voice_enroll.py`, "one voice print per microphone". | Use the same tech the other way round: notice when someone *else* is in the room, for privacy (idea 8). |
| 5 | **It lives next to your real home and your real PC.** | Cloud agents work in their own remote computer, not yours (COMPETITORS-COMMERCIAL §2). | `jarvis_home.py` (Home Assistant), `jarvis_ui_control.py` (Windows programs), `jarvis_android_control.py` (the phone over adb). | Learn from the home's own history, locally (idea 4). |
| 6 | **No caps, no subscription, no training on you, spare hardware for slow thinking.** | Cloud tiers ration background work. | `jarvis_big_model.py` (a huge model streamed from the SSD for jobs nobody waits on). | Give the slow lanes real overnight jobs: journal, wiki, guardian (ideas 5, 6). |

**Not an advantage** (the commercial audit said this too, and I agree): the
animated face, and "works on any GPU" for a one-owner product.

---

## 2. Big ideas

### 2.1 The long list (17)

One line each. **Bold** = made the top 8.

1. **"Ask my own stuff"** - one question over your notes, wiki and (your call) past chats.
2. **Local eyes** - "what's on my screen?", "show me where to click", photos from the phone.
3. **Goals with one card per step** - a goal becomes a plan; Jarvis nudges, each action asks.
4. **A home that learns** - notices routines in Home Assistant's own history and offers an automation, as a card.
5. **The weekly journal** - Sunday evening, a page in Obsidian: what you worked on, decided, and changed your mind about.
6. **The private guardian** - checks emails, shared text and screenshots for scams, locally; hides one-time codes.
7. **Routines in plain words** - "movie night" = a fixed list of steps, shown whole on one card each time.
8. **Room awareness** - notice a voice that is not yours, and keep private answers on screen.
9. "Internet off" switch - one tap closes every way out; Jarvis keeps working. (Small; good, but more everyday than bold. Also on the "what can Jarvis reach right now" list in COMPETITORS-MUSE §1.)
10. Wake my PC from the phone - through Home Assistant, which is usually always on (HA's `wake_on_lan.send_magic_packet` service exists; I read its source). (Everyday lens; flagged for the other agents.)
11. A second opinion from the second card - the second model reads each card and adds one line: "this does not match what you asked". Never approves. (Risky: see 4.)
12. Redacted cloud help - the local model rewrites a hard question without private details, the card shows the exact words sent. (Extends the existing per-question cloud offer in `jarvis_router.choose()`.)
13. Jarvis's own report card - after any model change, re-run the memory self-test (`backend/eval/golden_*.jsonl`) and the tool test (`tools/tool_eval/`) and show the difference.
14. Follow-me presence - a laptop and a second phone, conversation hand-off between devices. Waits on per-device keys (queued task "more devices").
15. Voice memos to the vault - speak while walking, the PC turns it into text and a note. Already queued (COMPETITORS-COMMERCIAL §3 "Voice memos into Obsidian").
16. Household mode - per-person voice prints and permissions. **Not recommended**; see section 4.
17. A tiny model on the phone for when the PC is off. **Not recommended now**; see section 4.

### 2.2 The best 8, in detail

Sizes: S = days, M = a week or two, L = several weeks, XL = a month or more,
all with CI round trips for the phone.

---

#### Idea 1. "Ask my own stuff" (a local second brain)

- **What it is.** You ask "what was I thinking about the garage conversion?"
  and Jarvis answers from *your* material - your Obsidian vault, the wiki
  pages it built, your dated facts - quoting where each piece came from, with
  a link to open the note. Later, if you choose, from your own past chats too.
- **Why only Jarvis can do it well.** It means reading everything you ever
  wrote. Only something that cannot send it anywhere should be allowed to.
- **What exists already.**
  - Note search over the vault as a plain folder: `backend/jarvis_notes.py`.
  - The wiki builder, turning dropped documents into linked pages:
    `backend/jarvis_wiki.py`, `docs/SECOND-CARD.md` "Wiki builder".
  - "What did I believe in June?": `backend/jarvis_past.py`.
  - Deep questions on the big model: `backend/jarvis_big_model.py`.
  - Chat history, encrypted: `backend/jarvis_chat_log.py`. **But**
    ARCHITECTURE §5 says plainly: "nothing in it is recalled into a chat, and
    it is not a source the learner reads from on its own." So past chats are
    off the table unless you decide otherwise (question 1 below).
- **What the second card changes.** Everything. Answering from 20 notes at
  once needs room; today's chat model has about 16,000 tokens (probably less,
  HARDWARE-PROFILES §0 item 1). The second card's lane has 32,768
  (SECOND-CARD.md table), and a Qwen 3.5 9B there could hold far more
  (RESEARCH-2026-09-24 §6: "64,000 words' worth ... perhaps 128,000", which is
  arithmetic, not measured). It also means a slow "read everything" job never
  slows chat.
- **Size.** M for notes and wiki; +S for past chats if you allow it; L for
  PDFs and scans (needs idea 2's picture model).
- **Rules it touches.** Rule 1: everything is read by the local model only.
  Memory rule of 2026-09-24: notes and documents are read to *answer*, never
  *learned* as facts - the same line `jarvis_notes.py` already keeps. Nothing
  acts, so no card per question. If chats are included, only owner-called
  (you ask), never slipped into every answer.
- **Biggest risk.** Confidently wrong answers stitched from old notes. The
  answer must show its sources and dates, and say "I did not find anything"
  rather than guess.

---

#### Idea 2. Local eyes

- **What it is.** Three uses of a picture-reading model, all on the PC:
  1. "What's on my screen?" / "what does this error mean?" from a screenshot.
  2. **"Show me where to click"** - Jarvis draws a highlight and says the
     step; *you* click. It acts on nothing, so it needs no card, and it is
     perfect for a beginner learning a new program (idea taken from Copilot
     Vision, COMPETITORS-COMMERCIAL §4, item 4).
  3. Photos from the phone: a receipt, a letter, a whiteboard, a plant -
     read on the PC, and optionally dropped into the wiki's Sources.
- **Why only Jarvis can do it well.** Screens and photos are full of private
  things (bank tabs, letters, faces). Cloud vision means uploading them.
- **What exists already.**
  - The screenshot quickbar and its "can the model see?" check: `vision.rs`
    (ARCHITECTURE §10, "A picture-capable local model").
  - The phone already sends pictures: `jarvis-client/.../net/ChatPicture.kt`.
  - Pictures never go to the cloud: `jarvis_router.choose()` keeps any turn
    with an image local (ARCHITECTURE §10).
  - The "Pictures" switch, built and off, sends picture turns to
    `qwen2.5vl:7b` on the second card (`jarvis_second_card.py`).
  - Clicking named buttons, one approved plan at a time:
    `backend/jarvis_ui_control.py`. "Show me where" can reuse its reading of
    the Windows accessibility tree to find the button *without* clicking.
  - The wiki cannot read PDFs or pictures yet (SECOND-CARD.md, "Using it", step 2).
- **What the second card changes.** It is the whole feature. The 8 GB card
  cannot hold a picture model next to chat. Qwen 3.5 small models read
  pictures natively (Qwen's own README: the 3.5 family "outperforms Qwen3-VL
  models across ... visual understanding"; the 9B and 4B came out 2026-03-02;
  llama.cpp "supports the Qwen3.5 open model series (text & vision)" - read
  directly). One 9B could do chat-length, pictures and learning on the 2060
  (RESEARCH-2026-09-24 §6, not measured).
- **Size.** S for "what's on my screen" once the card is in (it is mostly
  switched on already); M for "show me where to click"; M for photo-to-wiki.
- **Rules it touches.** Rule 1 (pictures stay local, already enforced).
  Rule 4: "show me where" never clicks; real clicking stays
  `jarvis_ui_control`'s plan-and-card path, and never on Jarvis's own windows
  (ARCHITECTURE §2, security audit M3). Not a screen recorder: only a
  screenshot you take (screenpipe stays rejected, ARCHITECTURE §11).
- **Biggest risk.** Small models are unsure where things are on a busy
  screen. Published scores for small models finding a named button on
  professional software screens are under 50% (ScreenSpot-Pro, search
  summary only). So "show me where" should prefer the accessibility tree
  (exact) and fall back to the picture model only with "I think it is here".
  Also: text in a screenshot is outside text and must mark the turn like an
  email does **(my inference; check how the quickbar marks it today)**.

---

#### Idea 3. Goals with one card per step

- **What it is.** You say "I want to get the garage insulated before
  winter." Jarvis writes a short plan (steps, rough dates) that *you* edit
  and accept. Then it keeps the goal on "Coming up", nudges politely at
  sensible times, and when a step needs acting (search for installers, draft
  an email, add a calendar entry) that step is its own card.
- **Why only Jarvis can do it well.** A good plan needs your calendar, notes,
  budget facts and history together. Muse has a Goals view, but it lives in
  Meta's cloud and grants "always allow" (COMPETITORS-MUSE §2).
- **What exists already.** A surprising amount:
  - Plans as a bounded list of named steps with `plan()`/`describe()`/`run()`,
    in three modules (`docs/AUTONOMY-PROPOSALS.md` §2).
  - Pause, stop and "add a note" while a task runs:
    `backend/jarvis_task_control.py`, `task-control.patch`.
  - The one scheduler and "Coming up": `backend/jarvis_schedule.py`.
  - Polite offers with a back-off (1, 7, then 30 days after a "no"):
    `backend/jarvis_backoff.py`.
  - The initiative engine, running with an **empty** check list:
    `backend/rebuilt/jarvis_initiative.py` ("the check list is EMPTY until
    someone registers one"). A goal check-in is exactly the kind of check it
    was built for, but ARCHITECTURE §12 says new timed things must be a kind
    on the one scheduler, so it should be that, not the engine's timer.
- **What the second card changes.** Planning and re-planning in the
  background, with the long lane's room for the goal's whole history, without
  touching chat speed.
- **Size.** L.
- **Rules it touches.** No auto-approve: accepting a goal approves *nothing*
  that acts; each acting step is its own card. Anything that repeats (a
  weekly check-in) is one `schedule_repeat` card. Offers go through
  `jarvis_backoff.may_offer()`. Nothing leaves the PC except through the
  existing lanes, each with its own card.
- **Biggest risk.** Nagging. An 8B model is also weak at long plans. Keep
  plans short (at most ~7 steps), editable, and make "stop tracking this
  goal" one tap and immediate.

---

#### Idea 4. A home that learns

- **What it is.** With your yes, Jarvis reads Home Assistant's own history
  on your network, notices patterns ("the hall light goes on around 22:40 on
  weekdays, and off at 23:10"), and offers **one** automation at a time as a
  card that shows the exact rule it would add. No means never offered again.
- **Why only Jarvis can do it well.** A home's sensor history says when you
  sleep, leave and come back. It is exactly the data that must not go to a
  cloud. Home Assistant can already use a local model through Ollama (search
  summaries only - the HA site was blocked), but it does not watch your
  habits and suggest rules on its own **(as far as I could check)**.
- **What exists already.**
  - Reading HA states (tier `auto`) and calling one service (tier `ask`):
    `backend/jarvis_home.py`, `plan_states()` and `plan_service()`.
  - The "notice a repeated pattern, offer it once" shape already exists for
    tool chains: `backend/jarvis_skill_discovery.py`. Same idea, new source.
  - Home Assistant's history route is `/api/history/period`
    (`homeassistant/components/history/http.py` - I read the source).
    `jarvis_home.py` does not call it today (I grepped).
- **What the second card changes.** Pattern-spotting can be plain counting
  (no model at all, which I would prefer). The second card helps write the
  plain-words explanation and the rule text in the background.
- **Size.** M for "notice and tell you"; +M for creating the automation in
  HA (the way to create one through HA's API is **not verified here**).
- **Rules it touches.** Reading history is a new read of the owner's own
  account: switching it on should be one card, like other settings that
  widen what Jarvis sees. Creating an automation is acting in the physical
  world: one card, showing the full rule. Offers use the back-off. Plain
  `http://` to HA only inside your own networks (the 2026-09-25 decision).
- **Biggest risk.** A bad automation that runs forever *inside HA*, outside
  Jarvis's cards. The card must say plainly "this will run by itself in Home
  Assistant from now on", and never suggest locks, alarms, garage doors or
  heating (those need a person every time).

---

#### Idea 5. The weekly journal

- **What it is.** Every Sunday evening (your choice), Jarvis drafts one page:
  what you worked on, what you decided, reminders you finished or dropped,
  facts it learned about you this week and the ones that changed ("you said
  you moved the gym day to Thursday"). You read it in the app and press
  "Save to Obsidian". Over months it becomes a diary nobody else ever sees.
- **Why only Jarvis can do it well.** It needs your chats, calendar, to-dos
  and learned facts together. That is the most private summary imaginable.
- **What exists already.**
  - The scheduler and its first later kind, the briefing, put together in
    code: `backend/jarvis_schedule.py`, `backend/jarvis_briefing.py`.
  - Dated facts, including replaced ones: ARCHITECTURE §5, `jarvis_past.py`.
  - Writing to today's daily note: `backend/jarvis_note_capture.py`.
  - The rule that note-writing after outside text waits for a yes (CLAUDE.md,
    2026-09-24). The journal reads calendar titles, which are outside text,
    so the save is a card - which fits "Save to Obsidian" anyway.
- **What the second card changes.** It writes the summary in the background
  on the long lane (or the big model, overnight) instead of stealing chat's card.
- **Size.** M.
- **Rules it touches.** Repeating = one `schedule_repeat` card. Using past
  chats needs question 1's answer; without it, the journal uses facts,
  to-dos and calendar only. Sensitive facts shown, never read aloud.
- **Biggest risk.** A summary that invents things. Each line should link to
  where it came from, and it must be a draft you approve, never written
  straight into the vault.

---

#### Idea 6. The private guardian

- **What it is.** Jarvis looks at new emails, shared text and screenshots for
  scam signs ("this 'bank' link goes to a different site", "urgent payment",
  "this asks you to read out a code") and tells you, quietly. It also hides
  one-time codes and reset links wherever Jarvis shows email text.
- **Why only Jarvis can do it well.** Checking every email means reading
  every email. A local model can do that without anyone else seeing it.
- **What exists already.**
  - Reading email without marking it read: `backend/jarvis_email.py`.
  - Planted-instruction checks, measured here at 33 of 46 attack goals with
    no false alarms on 383 ordinary items (RESEARCH-2026-09-24 §4).
  - A content-risk module on the owner's PC only (`jarvis_content_risk`,
    ARCHITECTURE §10 - contents unverified from here).
  - The suggestion to hide one-time codes in email previews
    (`jarvis_email.py:250-271`, COMPETITORS-MUSE §6 item 2).
- **What the second card changes.** A background checker that reads each new
  email as it arrives, without waiting for the chat model to be free.
- **Size.** S for hiding codes; M for scam warnings.
- **Rules it touches.** It only reads and warns; it never deletes, moves or
  replies. Warnings go through the event bus with the same "never while
  tainted" care as push notices (ARCHITECTURE §4, ntfy row). A warning that
  names a sender stays off the lock screen.
- **Biggest risk.** False alarms train you to ignore it; misses give false
  comfort. It must say "this looks risky because ...", never "this is safe".

---

#### Idea 7. Routines in plain words

- **What it is.** "When I say 'movie night', dim the living room lights to 20%,
  pause the music, and set a 2-hour timer." Jarvis turns that into a fixed
  list of steps and saves it. Each time you say "movie night", you see **one
  card with every step written out** and say yes once.
- **Why only Jarvis can do it well.** Cloud routines run without asking. A
  routine that shows its steps each time is safe to make much more powerful.
- **What exists already.**
  - Saving a skill file after one card (`modify_own_code`):
    `backend/jarvis_skill_discovery.py`.
  - Instant plain-sentence answers without the model: `backend/jarvis_quick.py`
    (so "movie night" could start without waiting for the model).
  - HA actions and timers, each already a gated action: `jarvis_home.py`,
    `jarvis_schedule.py`.
  - ARCHITECTURE §2: "Approving eight enumerated, printed search queries for
    one audit is one decision." A printed routine is the same shape.
- **What the second card changes.** Little. This one does not need it, which
  makes it a good thing to build while waiting for the card.
- **Size.** M.
- **Rules it touches.** The key point: **saving a routine approves nothing.**
  Every run is its own card listing every step. A timer inside it needs no
  card on its own, but as part of a routine it rides the routine's card.
  A routine may not contain another routine, may not repeat on its own
  (a repeat is a `schedule_repeat` card), and never touches Jarvis's own
  approval screens.
- **Biggest risk.** The temptation, later, to add "don't ask me for this one
  again". That is an approve-all. The answer must stay no.

---

#### Idea 8. Room awareness (instead of a household mode)

- **What it is.** The voice check already scores every voice against yours.
  Room awareness uses the *other* result: "a voice that is not yours was
  heard in the last few minutes." While that is true, answers that use
  private material stay on screen instead of being read aloud, and the
  phone's lock-screen notices say less. It changes no permissions; it only
  makes Jarvis more discreet.
- **Why only Jarvis can do it well.** Only an assistant that already checks
  whose voice it is can notice that someone else is there, and do it
  without sending audio anywhere.
- **What exists already.**
  - The "someone else" calibration: another person's clips scored against
    yours and dropped (`backend/jarvis_voice_enroll.py`, mode `calibrate`).
  - One voice print per microphone (same file, citing `jarvis_voice.py`).
  - The "keep private answers on screen" logic in both apps:
    `jarvis-desktop/src/private-speech.js` and the phone's `voice/PrivateAloud.kt`.
  - sherpa-onnx, which Jarvis already uses, lists speaker identification and
    speaker diarization (telling speakers apart) among its features (its
    README, read directly).
- **What the second card changes.** Nothing needed; this runs on the
  processor like the rest of voice.
- **Size.** M.
- **Rules it touches.** It keeps no recording and no print of the other
  person (only "someone else, at 14:02"), which matters for rule 1 and for
  the other person's privacy. It must never *grant* anything; it can only
  make Jarvis more careful. Turning it off is immediate; turning it on
  should be a card, like the other voice settings that change what is
  spoken.
- **Biggest risk.** Jarvis only hears speech that reaches it after the wake
  word or talk button, so it will miss people who stay quiet. It must be
  described as "fewer surprises", never as "Jarvis knows who is in the room".

---

## 3. Stepping stones for the top three

The smallest first step for each that is useful **on its own**, even if
nothing after it is ever built.

1. **"Ask my own stuff" → "Where did I write about...?"** A search over the
   vault and the wiki that lists matching notes with dates and one line each,
   and opens the note - no model answer at all. It works on today's 8 GB
   card, cannot hallucinate, and later becomes the "sources" list under the
   model's answer. (Pair it with the already-suggested search of chat history
   in the apps, COMPETITORS-OPEN-SOURCE §3 item 5, which also uses no model.)
2. **Local eyes → "What's on my screen?"** The day the second card is in and
   measured, approve the Pictures switch, and make the quickbar's screenshot
   question the headline test. This is mostly built (`vision.rs`,
   `jarvis_second_card.py`); the first step is running it and measuring
   speed and quality on the real card. Also worth testing then: whether one
   Qwen 3.5 9B can replace the two-model swap (RESEARCH-2026-09-24 §6).
3. **Goals → one goal on "Coming up".** You type "track: insulate the garage,
   by 1 November". It shows on Coming up with the date and a "done / still
   on it / stop" choice once a week (one `schedule_repeat` card to set up).
   No model planning at all. Planning with the model, and step cards, come
   after you have used the plain version for a few weeks.

---

## 4. What NOT to chase

| Shiny idea | Why not |
|---|---|
| **Household / family mode** (per-person voice prints and permissions) | ARCHITECTURE §1: "One owner... no multi-tenancy". The voice print "decides who may talk to Jarvis" (`jarvis_voice_enroll.py`). Letting a second voice give orders changes who Jarvis obeys, and memory is "the owner's own words only". Room awareness (idea 8) gets the useful part - discretion - without any of that. If the owner ever wants it, it is a new product decision, not a feature. |
| **"Always allow" for routines, goals or trusted actions** | Invariant 3. Every competitor that has it had trouble with it (COMPETITORS-MUSE §2; COMPETITORS-OPEN-SOURCE §1). |
| **Recording the screen all the time** (Recall-style) | Already rejected (screenpipe, ARCHITECTURE §11; RESEARCH §7). Screenshots on request only. |
| **Fine-tuning a model on your chats** | Ruled out in the config (LEARNING-RESEARCH §1, citing `jarvis-framework.toml:924-931`). On a 2060 it is also slow and hard for a beginner, and a model trained on your chats is a copy of them you cannot "Erase the words" from. |
| **A clicking agent that runs by itself on the screen** | UFO-style loops are a standing grant (docs/UFO-SAFETY-DESIGN.md). Small models are also unreliable at finding buttons (idea 2's risk). "Show me where to click" gives most of the value. |
| **A model on the phone for when the PC is off** | The phone may not do speech-to-text (CLAUDE.md), so it would be typing only; private memory would have to be copied to the phone; and it would be a second brain to keep in step. Waking the PC through Home Assistant (list item 10) solves the real problem more simply. **(Partly speculation - worth revisiting if phones get much stronger.)** |
| **Real-time "talk over each other" voice models** | moshi rejected: "8 GB cards cannot run it" (ARCHITECTURE §11). Speaking at the first comma and barge-in get most of the feel. |
| **A second model that approves or "vets" cards** | It is fine as a *warning line* (list item 11). The moment its "looks fine" is shown prominently, you stop reading cards - invariant 6 ("the owner stops checking"). I would build it only as warnings, if at all. |
| **Chasing big-cloud integrations** (shopping, bookings, 56 connectors) | Muse's first two weeks (blocked by Amazon, stalled purchases) show how brittle it is, and each connector is a new way out. MCP later, gated, is the safer road (EXTRACTION-RESEARCH; COMPETITORS-OPEN-SOURCE §3). |
| **Running a 14B as everyday chat on the 2060** | It would be on the slower card: "noticeably slower words" (HARDWARE-PROFILES §4.4, "8 + 12 GB"). Keep fast chat on the 2080 Super, as MODEL-TOPOLOGY already says. |

---

## 5. Questions for the owner (two)

**Question 1.** Today Jarvis keeps your past chats on the PC but never uses
them to answer. Should "Ask my own stuff" be allowed to search them - only
when you ask it to, never on its own?

- **Yes, only when I ask** (recommended: your chats are your own words, and
  they never leave the PC)
- **No, notes and the wiki only**

**Question 2.** When the second card goes in, which big thing should it be
used for first?

- **Seeing: screenshots and phone photos** (recommended: mostly built, easy
  to test, and useful every day)
- **Reading: "Ask my own stuff" over the whole vault**

---

## 6. Sources

**Read directly (the page or file itself):**
- Qwen's README on GitHub, `raw.githubusercontent.com/QwenLM/Qwen3.5/main/README.md`
  (it now describes Qwen3.8; release dates for Qwen3.5 9B/4B on 2026-03-02,
  llama.cpp support for Qwen3.5 text and vision).
- Home Assistant source on GitHub: `components/history/http.py`
  (`/api/history/period`), `components/wake_on_lan/services.yaml`
  (`send_magic_packet`), `components/ai_task/services.yaml`
  (`generate_data`, `generate_image`).
- sherpa-onnx README on GitHub (speaker identification, diarization, verification).

**Only saw search summaries (pages blocked or not opened):**
- Qwen3.5-9B model card and VRAM figures (huggingface.co and canirun.ai; blocked or not opened).
- Home Assistant's Ollama integration page and 2026 guides about Ollama with Home Assistant (home-assistant.io blocked).
- MCP 2026-07-28 specification (stateless core) - blog.modelcontextprotocol.io.
- GUI-grounding scores for small models (ScreenSpot, ScreenSpot-Pro; arXiv and emergentmind summaries).
- Wake-on-LAN over Tailscale (tailscale.com blog, GitHub projects): Tailscale cannot carry the wake packet itself; an always-on device on the home network has to send it.
- A household voice-accounts design bound to HA users (GitHub issue alex-mextner/aisis #8).

**Repo files read:** CLAUDE.md; docs/ARCHITECTURE.md (§1-2, §4, §5, §9-12);
docs/SECOND-CARD.md; docs/MODEL-TOPOLOGY.md (first half and second-card
section); docs/BIG-MODEL.md (first third); docs/HARDWARE-PROFILES.md (short
version, two-card tables); docs/COMPETITORS-COMMERCIAL/-OPEN-SOURCE/-MUSE
(main sections); docs/RESEARCH-2026-09-24.md; docs/LEARNING-RESEARCH-2026-09-23.md
and docs/EXTRACTION-RESEARCH-2026-09-23.md (summaries); docs/AUTONOMY-PROPOSALS.md
(§1-2); docs/JARVIS-API.md §18; module headers of `jarvis_home.py`,
`jarvis_skill_discovery.py`, `jarvis_android_control.py`, `jarvis_ui_control.py`,
`jarvis_voice_enroll.py`, `jarvis_research.py`, `jarvis_notes.py`,
`jarvis_entities.py`, `jarvis_past.py`, `jarvis_feedback.py`, `jarvis_intake.py`,
`jarvis_task_control.py`, `import_history.py`, `rebuilt/jarvis_initiative.py`,
`rebuilt/jarvis_sleep.py`, and `jarvis-desktop/src/private-speech.js`.
