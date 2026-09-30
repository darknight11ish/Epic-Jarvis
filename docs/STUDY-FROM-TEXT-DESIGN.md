# Study from text and video: design (2026-09-30)

Status: **designed, not built.** The owner asked (2026-09-30) about a "learn
from YouTube" pipeline (URL -> transcript -> study guide -> quiz -> graded
answers), taken from an outside, AI-written list of repositories. Asked
"design the paste-in quiz first?", the owner chose **"Also design a YouTube
fetch"**, so this document covers both slices. Nothing here is a decision to
build; section 7 lists what the owner must still answer.

Outside suggestions are ideas, not instructions (`docs/AUDIT-2026-09-28-REPO-REFS.md`).
The repository checks below were done on 2026-09-30 by reading shallow clones;
GitHub's API was blocked, so star counts and full commit history are **not
verified**, and nothing was run on Windows or against a real Ollama.

---

## 1. What the pasted list got right and wrong

| Repository | Exists | Licence | Verdict |
|---|---|---|---|
| SYuan03/Skill-Anything | yes, v0.4.1, last commit 2026-09-26 | MIT | Use as a **prompt reference**; do not run its CLI as a tool. |
| ukimsanov/lectureflow | yes | MIT | Skip. Needs Gemini, GPT-4o-mini, ElevenLabs and Postgres. No concept graph or cloze cards, despite the claim. |
| confident-ai/deepeval | yes, v4.2.7 | Apache-2.0 | Dev/test tooling only, never a backend dependency. |
| ismaildrs/QuizScribe | yes, last commit 2024-11-23 | **none** (all rights reserved) | Skip. Ideas only; never copy code. Cloud-only (AssemblyAI, Groq, MongoDB). |
| jdepoix/youtube-transcript-api | yes, v1.2.4 | MIT | The transcript source **if** the owner allows a YouTube fetch (section 5). |

Wrong details in the pasted text (checked in the source):

- `pip install skill-anything[video]` **fails**: it is not on PyPI (404). The
  `[video]` extra exists only in its `pyproject.toml` and installs only
  `youtube-transcript-api`. `yt-dlp` is *not* installed by any extra.
- `sa auto ... --quiz-difficulty` does **not exist**. `--difficulty` exists only
  on the interactive quiz command, not on `auto`.
- No `quiz.json` appears anywhere in its source or README.
- Its A-F grade belongs to the terminal quiz runner, not to what `sa auto` writes.
- It can use Ollama through `SKILL_ANYTHING_API_BASE` (its README), but that is
  **not verified by a run**.
- DeepEval's default judge is OpenAI (needs a key). It has telemetry, switched
  off with `DEEPEVAL_TELEMETRY_OPT_OUT=1`. It can use a local Ollama judge. An
  8B judge gives noisy scores.

## 2. Where this collides with rules and past decisions

- **Rule 1.** The owner's typed answers plus what they studied are personal
  study data. They go to the local model only. A cloud judge (DeepEval's
  default) is out.
- **No YouTube fetch by default.** `docs/CUTTING-EDGE-2026-09-26-round2-personality.md`
  (lines 39, 264-266) put "downloading from YouTube" under *left out*: a new
  way out of the PC (ARCHITECTURE §4) and against YouTube's terms.
  `backend/test_documents.py` fails the build if MarkItDown's audio or YouTube
  parts appear in `requirements.txt`. Section 5 is the owner's request to
  reopen this; it needs the owner's explicit yes (section 7, Q1).
- **One tool table, one permission model.** No tool that shells out to `sa`:
  its own network access and dependency tree would be a second execution path
  and a card could not show what leaves the PC. Jarvis's own reader and local
  model do the work.
- **One quiz system, not two.** "Quiz me on my notes" is audit milestone 3
  (FSRS, `py-fsrs`, MIT; its own small database, not memory; a kind on the one
  scheduler). A video quiz is the same feature with a different source of text.
- **Quizzes are a temporary chat**, marked outside text, so nothing in them is
  learned as a fact. A grade is **never** saved as a fact about the owner
  ("weak at X"), and there is no streak or guilt line.
- **Both apps.** The quiz screen needs a phone and a desktop version, or a
  written reason in ARCHITECTURE §8. Quizzes are neither a model catalogue nor
  a memory graph, so no standing phone rule blocks them.

## 3. Slice A: "Quiz me on this text" (recommended first)

Source of text: only what the owner **pastes or opens as a file** (a transcript
they copied, a note, a PDF or Word file through the documents feature,
`backend/jarvis_documents.py`). No new way out of the PC.

Flow, in plain words:

1. The owner says "quiz me on this" and gives the text.
2. Jarvis starts a **temporary chat** and marks the text as outside text.
3. The local model writes 5 questions, mixing kinds (recall, explain-why,
   apply-to-a-situation). Each question is tied to the passage it came from.
4. The owner types an answer to each question, one at a time.
5. The local model marks the answer **against the source passage only**, giving
   one of `Got it`, `Partly`, `Not yet`, plus one plain sentence. No number is
   shown as if it were exact.
6. At the end: a short summary of what to look at again. Nothing is saved
   unless the owner taps "Keep these questions" (milestone 3's review deck).

Design choices:

- **No DeepEval, no Bloom's rubric library.** A fixed rubric of three plain
  levels (Remember / Understand / Apply) goes in the prompt. No new dependency.
- **The grader must be measured before it is trusted**, the way memory changes
  are (`backend/eval_memory.py`, `eval_learner.py`): a small test set of
  question, source passage, correct answer and wrong answer, and the grader must
  separate them. Small models grade unreliably, so until it passes, the marks
  are labelled "Jarvis's guess" in the app.
- **Where a "test tool" is useful.** DeepEval with a local Ollama judge and
  telemetry off may be used by the *developer* in a `tools/`-style script to
  compare graders. It is not shipped or installed by the app.
- **Gate action.** Reading pasted text needs no card (the owner's own words).
  Saving a deck to review later is milestone 3's card. No new way out of the PC.
- **Voice.** Questions and marks are ordinary answers: read aloud only if the
  existing rules for outside-text answers allow it (they currently keep
  document answers on screen).

## 4. Slice A build pieces

Backend (patches, since the real backend lives outside this repo): a
`jarvis_quiz.py` module (write questions, mark answers, no model call outside
the existing local lane), a route pair in `docs/JARVIS-API.md`, a test file with
the grader test set. Desktop: a Quiz page reachable from Brain. Phone: the same,
built on the Compose screens pattern used by Goals. `tools/check_parity.py`
must be clean. The feature audit (bugs, both apps, fit) runs with it, as always.

## 5. Slice B: reading a YouTube transcript (only if the owner says yes)

What it would be: the owner pastes a YouTube link; Jarvis fetches the
**caption text only** (no video, no audio) with `youtube-transcript-api` (MIT,
no API key, unofficial), then runs Slice A on it.

What the owner must accept, plainly:

- It is **against YouTube's terms** (the library reads captions the site does
  not offer as an official service). The 2026-09-26 research said so. Your
  non-commercial status does not change it. It fetches from your own home
  connection, so the realistic risk is being blocked, but that is not verified:
  the library was not run live, and YouTube often blocks data-centre addresses.
- It fails on videos without captions. No speech-to-text on the phone, ever
  (a client must not do speech-to-text); turning audio into text on the PC would
  be a separate, larger step and is **not** part of this design.
- It is a **new named way out of the PC** (ARCHITECTURE §4), with its own gate
  action, tier `ask`.

How it would follow the rules if allowed:

- **One card per address**, like the approved "news headlines / tell me when
  this page changes" feature: the card shows the exact link and says "Jarvis
  will fetch this video's caption text from YouTube". Nothing else is sent.
  The link itself tells YouTube which video the owner is studying; the card says so.
- Read-only. Never follows other links. Never acts on what it reads.
- The transcript is **outside text**: marked, never learned as a fact, never
  read into memory, quizzes in a temporary chat.
- Not from a turn that already read email, files, notes or memory (the card
  would be misleading). The fetch sends only the video id.
- The library is added to `requirements.txt` as a **pinned** MIT dependency, with
  an entry in `THIRD-PARTY-NOTICES.txt`. The `test_documents.py` ban on
  MarkItDown's YouTube parts stays as it is; that test needs a matching
  allowance only for this library, written deliberately.
- Failure is said plainly: "No captions for this video", or "YouTube refused the
  request". No silent fallback to another site.
- Skill-Anything's code is MIT and may be borrowed for study-guide prompts with
  its notice added to `THIRD-PARTY-NOTICES.txt`. Its CLI is not run.

## 6. Ideas kept and dropped from the pasted list

- Kept: timestamped outline (from caption timestamps), study-guide sections,
  scenario and comparison question kinds, Anki-style export later (milestone 3).
- Dropped: `sa` as a tool, lectureflow (cloud), QuizScribe (no licence, cloud),
  DeepEval in the running app, `--quiz-difficulty` (does not exist),
  A-F letter grades (a letter grade from a small model is false precision).
- Not verified: what installing `skill-anything[video]` from git pulls in beyond
  `youtube-transcript-api`; whether `youtube-transcript-api` works from the
  owner's own PC today.

## 7. Owner's answers (2026-09-30)

The owner said any rule can change if the change is worth it, and answered:

1. **YouTube captions: allowed, one card per link.** Built after Slice A. The
   owner accepts that it breaks YouTube's terms and may be blocked. This
   reverses the 2026-09-26 "left out" decision for caption text only (never
   video or audio downloads).
2. **Grading: local first, cloud on request.** The local model grades by
   default. A "grade this better" button may send that one quiz to a cloud
   model, only after a card lists exactly what leaves the PC (the questions,
   the owner's answers, the source passages). This bends rule 1 for that card
   only, the way the locked backup and the app builder's cloud-help offer do.
   Never with email, files, credentials or memory in it; never after the
   quiz was built from such text. Cloud keys follow rule 3.

Still open, and small: whether saved review decks (milestone 3) share this
quiz screen (recommended: yes), and the cloud grader's monthly money limit
(reuse the chatbot driver's per-service limit).

## 8. Next step

Build Slice A, then Slice B, then the cloud button, each with its own feature
audit. Nothing is built yet.

## 9. The second graphics card (owner, 2026-09-30)

The owner is adding the RTX 2060 12 GB and said a study feature may need it,
**built but switched off until the card is installed and measured**. This is
the same rule every second-card feature already follows
(`docs/MODEL-TOPOLOGY.md`, "The planned second card"; `FEATURES` in
`backend/jarvis_second_card.py`).

What the second card would add (all unmeasured; the card is not installed):

1. **A "Study helper" switch**, a sixth in the second-card list (id `study`,
   needs nothing else). On: quiz questions are written and answers marked by
   the second card's model, so a quiz never slows the everyday chat, and the
   local grader can be the bigger model ("One bigger model on both cards",
   `qwen3:14b`) instead of the 8B. This is the answer to "the local grader is
   noisy": try the bigger local model before offering the cloud button. It
   is the same switch pattern as the five others: off by default, turning it on
   raises an approval card that names the card and the model, turning it off
   is immediate.
2. **Spoken practice and audio lectures** (later, its own switch, needs
   `study`): a multilingual speech-to-text engine on the PC for a spoken
   Spanish exercise or an audio file the owner gives Jarvis. Jarvis's speech
   engine today (sherpa-onnx, on the processor, 0 GB of graphics memory)
   hears English only, but the same file already offers SenseVoice
   (multilingual): try that first, measured on Jarvis's own Spanish clips.
   `faster-whisper` is only a fallback if SenseVoice is not good enough,
   because a second engine is a second thing to keep safe
   (`backend/jarvis_speech.py`). The phone still does no speech-to-text.
   On the 12 GB card, an 8B at 32K (7.69 GiB) plus a small speech model is
   about 9 GiB by arithmetic, under the ~11.4 GiB ceiling; **not measured**.
3. **What the second card does not change:** downloading video or audio from
   YouTube (yt-to-anki's clips). More graphics memory is not the reason it is
   refused; the owner's answer was captions only. A graph database (graphiti)
   also stays out.

The corrected hardware line for the pasted list: Jarvis's everyday model is
Qwen 3 8B at 16K (about 6.5 GiB on the 8 GB card, with about 6.9 GiB usable),
not qwen2.5:7b, so nothing should share the 2080 Super with a speech model.
Anything new that needs graphics memory waits for the second card.

Building `study` means, as for the other switches: a backend patch and test,
a row in both apps' "Second graphics card" section, a `docs/JARVIS-API.md`
entry, and `tools/check_parity.py` clean. It comes after Slice A, because the
switch has nothing to switch until the quiz module exists.

## 10. Second Gemini list, checked (2026-09-30)

All nine repos exist (shallow clones read; star counts unverified). Verdicts:

| Project | Licence | Verdict |
|---|---|---|
| py-fsrs (`fsrs` 6.3.2) | MIT | **Use** for milestone 3. Tiny, pure Python. The optional optimizer needs torch: leave it out. |
| fabric | MIT | **Copy prompts as text**, keeping the notice: `create_quiz`, `create_flash_cards`, `extract_wisdom` (in `data/patterns/`). Its own program and YouTube fetch are not used. |
| openlingo | MIT | Ideas only: needs Postgres and cloud models, uses SM-2 not FSRS. Its nine exercise kinds become question kinds in the quiz. Its word lists have their own source licences, not checked. |
| Lute v3 | MIT | Ideas only. It has **no** automatic verb linking (parents are set by hand); familiarity levels 1-5 are real. |
| yt-to-anki | **GPL-3.0** | Ideas only (clean-room route if ever wanted); also media download is refused. |
| graphiti | Apache-2.0 | Skip: needs a graph database, telemetry on by default. |
| srs-benchmark | none | Skip: a research harness on a public dataset, not for personal logs. |
| faster-whisper | MIT | Optional fallback only; no measured VRAM figure for "small" exists in its README. Jarvis's own speech engine goes first (section 9). |
| yt-dlp | Unlicense | Not used: it downloads media. |

False claims in the pasted list: openlingo's `src/lib/ai/tools/` (it is one file,
`lib/ai/tools.ts`); fabric's `create_study_guide` (does not exist; use
`summarize_lecture` or write our own); Lute "links durmió to dormir
automatically"; the "small float16" memory figure.

## 11. Slice A contract (frozen 2026-09-30; builders work from this)

Owner went ahead 2026-09-30: three builders at once (backend, desktop, phone),
on the current branch, no pull request yet. It will be **JARVIS-API section 98**.

**Rules it must keep.** No card (the owner's own pasted words, the local model
only, nothing leaves the PC). The text is **outside text**. The quiz module never
calls the learner or memory and writes nothing to disk: a session lives in memory
only, and ends on `finish`, `stop`, a PC restart, or 60 minutes without use. A
grade is never a fact about the owner. No streak, no letter grade, no number
shown as exact. Chat history is not touched. Under "Hide memory lists and chat
history" the quiz page hides its questions and answers like the "Used" list does.
Send `X-Jarvis-Client: hud`. The phone does no speech-to-text: answers are typed.

**Routes** (backend `backend/jarvis_quiz.py`, installed like `jarvis_goals.install`):

| Route | Body | Answer |
|---|---|---|
| `POST /api/quiz` | `{"text": str, "count": 1-10 (default 5), "title": str?}` | `{"ok": true, "quiz": Quiz}` |
| `GET /api/quiz/{id}` | - | `{"ok": true, "quiz": Quiz}` |
| `POST /api/quiz/{id}/answer` | `{"n": int, "answer": str}` | `{"ok": true, "mark": Mark, "quiz": Quiz}` |
| `POST /api/quiz/{id}/finish` | `{}` | `{"ok": true, "summary": Summary}` and the session is deleted |
| `POST /api/quiz/{id}/stop` | `{}` | `{"ok": true}` and the session is deleted |

`Quiz` = `{"id": str, "title": str, "grader_verified": bool, "questions": [Question], "answered": int}`.
`Question` = `{"n": 1.., "kind": "recall"|"explain"|"apply", "prompt": str, "mark": Mark|null}`.
The source passage is NOT in `Question` until it is answered.
`Mark` = `{"level": "got_it"|"partly"|"not_yet", "comment": str, "passage": str}`.
`Summary` = `{"counts": {"got_it": int, "partly": int, "not_yet": int}, "again": [n, ...]}`.
`counts` are the answered questions only; `again` lists, in question order, every answered question not marked `got_it` AND every question left unanswered (owner, 2026-09-30).
Limits: `text` 200-20000 characters, `answer` 1-2000, `count` 1-10, 3 open quizzes.
`grader_verified` is `false` until the grader test set (`backend/quiz_grader_cases.json`)
has passed on this PC; while false, every app shows "Jarvis's guess" beside a mark.

**Errors** (`{"ok": false, "error": <code>, "message": <plain words>}`): `text_too_short`,
`text_too_long`, `bad_count`, `too_many_quizzes`, `not_found`, `bad_question`,
`already_answered`, `answer_empty`, `answer_too_long`, `model_unavailable`
(plain message, word for word in both apps: `The model on this PC did not answer. Nothing was changed - try again in a moment.`). A Keep (JARVIS-API section 102) is the one thing that saves anything from a quiz, so the intro says "unless you choose Keep"; a Spanish quiz's Keep sheet shows the Spanish crisis notice too.
On a stale link the apps hold the buttons, like Goals (rule 4).

**Shared words** (both apps, word for word):
- Page title: `Quiz me on a text`
- Intro: `Paste some text and Jarvis writes a few questions about it. Your answers are marked by the model on this PC. Nothing is saved unless you choose Keep, nothing is learned, and nothing leaves this PC.`
- Start button: `Write questions`
- Answer button: `Check my answer`
- Marks: `Got it` / `Partly` / `Not yet`; label `Jarvis's guess` (while `grader_verified` is false)
- Finish: `Finish` ; stop: `Stop and forget this quiz`
- Summary heading: `Look at these again`; empty: `Nothing to look at again.`
- Outside-text line: `This text is treated as outside text: Jarvis never learns facts from it.`

**Files.** Backend: `backend/jarvis_quiz.py`, `backend/quiz.patch` (one hunk installing it,
like `goals.patch`; then run `python3 tools/build_patch_history.py` after `git fetch --unshallow origin`),
`backend/test_quiz.py`, `backend/quiz_grader_cases.json`, JARVIS-API §98,
`tools/check_parity.py` entries. Desktop: `jarvis-desktop/src/quiz.js` (+ its place in Brain),
`src-tauri/src/brain/quiz.rs`, `tests/quiz.mjs`. Phone: `net/Quiz.kt`,
`ui/screens/QuizPlate.kt`, `QuizTest.kt`. One builder owns each group; builders do
not edit each other's files, and do not run `git commit`.

### Crisis answers (owner, 2026-09-30: "Check every quiz answer now")

An answer that the chat's English crisis check flags gets no mark: the answer response carries `crisis: true` and `message`, and both apps show that message (the backend's text - `jarvis_wellbeing.reply()` - never a copy in an app) calmly in place of a mark, keep the question open for another answer, and keep no copy of the typed words. English only; a Spanish list is a later, separately tested step. See JARVIS-API 98.4.

### Shared words added by the builders (audit fixes, 2026-09-30)

Both apps say these word for word too (desktop `src/quiz.js`, phone `net/Quiz.kt`):

- Kind labels: `Remember` / `Explain why` / `Apply`
- Progress line: `Question 2 of 5 · 1 answered`, or `All 5 answered` when nothing is left
- Paste count line: `0 / 20,000 characters · at least 200 needed` (the count is of the trimmed text, as the PC checks it; `· too long` past 20,000, and the paste is never cut short)
- Answer count line: `12 / 2000 characters`
- Summary counts line: `2 Got it · 1 Partly · 0 Not yet` (no percentage, no grade)
- Summary list: one line per question to look at again, `3. <the question's words>` (skipped questions included, no extra label); `(hidden)` in place of the words while the private lists are hidden
- Close button after the summary: `Close`
- A PC without the feature: `Your PC's Jarvis does not have Quiz yet - run apply-patches.ps1 on the PC.`
- Placeholders and small labels: `Paste the text here`, `Type your answer`, `From the text`, `Next question`
- While the private lists are hidden, `Finish` and `Stop and forget this quiz` stay available in both apps (they show only numbers); questions, answers, comments and passages are hidden.

## 12. Third Gemini list, checked (2026-09-30)

All five repos exist (shallow clones read; star counts unverified).

| Project | Licence | Verdict |
|---|---|---|
| educhain | MIT | **Skip the library**: installing it resolves 181 packages (chromadb, playwright, kubernetes...). Its prompt templates and question schemas may be copied with the notice. |
| substudy | Apache-2.0 | Skip: last commit 2024-05, a command-line tool (not a library), needs ffmpeg, its transcribe/translate call OpenAI. Slicing audio by subtitle timing is easy to write ourselves if ever wanted, in the backend, never in the Rust shell. |
| freelingo | **AGPL-3.0** | Ideas only (no code). Docker + Postgres + Redis; SM-2, not FSRS; has streaks (refused). |
| mispronunciation repo | Apache-2.0 | Ideas only. **English only** (not Spanish); uses Modal, HuggingFace and Groq clouds; weights not included. espeak/phonemizer is GPL-3 (run as a separate program only). |
| repeater | Apache-2.0 | Best fit, but not run beside Jarvis (a second scheduler; it checks GitHub for updates daily). Its `Q:` / `A:` / `C:` Markdown card format and the `fsrs` idea inform milestone 3. |

False claims in the pasted list: educhain uses LangChain's parser, not
"Instructor"; there is no ChatOllama in it (you add it yourself);
`difficulty_level` is not a parameter of the method shown; freelingo has no top
`src/`; repeater is Rust only (no Go); the pronunciation repo is not
fine-tuned by its author and is not Spanish.

The pasted "pipeline assembly" was pasted twice; its download steps
(yt-dlp, faster-whisper on a downloaded stream) stay refused (section 7).


## 13. Slice contract (frozen 2026-09-30): Study helper and Referee suggestions

The owner's decisions of 2026-09-30: **Study helper = yes** (section 9 above); **Referee suggestions = yes,
built switched off, propose-only**. Both are the second graphics card's sixth and seventh switches, built OFF
until the 12 GB card is installed and measured. Backend built (`backend/jarvis_second_card.py`,
`backend/jarvis_referee.py`, `backend/referee.patch`; `docs/JARVIS-API.md` section 108 is the full account).
**No new route.** This section is what the two apps build against; the words below are the backend's own and
both apps say them word for word.

### 13.1 The switch rows (`GET /api/second-card`, `features[]`)

`features[]` now has seven rows in this order: `long_context`, `vision`, `learning`, `browser_control`,
`wiki`, `study`, `referee`. The two new rows, exactly as the backend sends them.

A one-card PC (the same `why` as every other switch; nothing can be turned on):

```json
{"id": "study", "name": "Study helper", "what": "Quiz questions are written, and your answers marked, on the second card, so a quiz never slows the everyday chat. The text you paste and the answers you type stay on this PC.", "enabled": false, "active": false, "available": false, "needs": [], "model": null, "model_installed": null, "memory_gib": null, "why": "Needs a capable second graphics card: only one graphics card found (the NVIDIA GeForce RTX 2080 SUPER)."}
{"id": "referee", "name": "Referee suggestions", "what": "When a goal step's number reaches your target, Jarvis asks \"This looks done - tick it?\" on a card that shows the numbers. Only your tap ticks it: Jarvis never ticks a step by itself and never runs a test. Today it compares numbers on this PC and loads no model.", "enabled": false, "active": false, "available": false, "needs": [], "model": null, "model_installed": null, "memory_gib": null, "why": "Needs a capable second graphics card: only one graphics card found (the NVIDIA GeForce RTX 2080 SUPER)."}
```

A capable second card, everything off (the default):

```json
{"id": "study", "name": "Study helper", "what": "Quiz questions are written, and your answers marked, on the second card, so a quiz never slows the everyday chat. The text you paste and the answers you type stay on this PC.", "enabled": false, "active": false, "available": false, "needs": [], "model": "qwen3:8b", "model_installed": true, "memory_gib": 7.69, "why": "Off."}
{"id": "referee", "name": "Referee suggestions", "what": "When a goal step's number reaches your target, Jarvis asks \"This looks done - tick it?\" on a card that shows the numbers. Only your tap ticks it: Jarvis never ticks a step by itself and never runs a test. Today it compares numbers on this PC and loads no model.", "enabled": false, "active": false, "available": false, "needs": [], "model": null, "model_installed": null, "memory_gib": null, "why": "Off."}
```

Both on and working (main switch on, the model installed; `referee` needs no lane, so it is `available`
whenever it is `active`):

```json
{"id": "study", "name": "Study helper", "what": "Quiz questions are written, and your answers marked, on the second card, so a quiz never slows the everyday chat. The text you paste and the answers you type stay on this PC.", "enabled": true, "active": true, "available": true, "needs": [], "model": "qwen3:8b", "model_installed": true, "memory_gib": 7.69, "why": "Working: qwen3:8b on the NVIDIA GeForce RTX 2060, with room for 32,768 tokens of conversation."}
{"id": "referee", "name": "Referee suggestions", "what": "When a goal step's number reaches your target, Jarvis asks \"This looks done - tick it?\" on a card that shows the numbers. Only your tap ticks it: Jarvis never ticks a step by itself and never runs a test. Today it compares numbers on this PC and loads no model.", "enabled": true, "active": true, "available": true, "needs": [], "model": null, "model_installed": null, "memory_gib": null, "why": "Working: it compares the numbers you log with your targets on this PC and loads no model, so it uses none of the card's memory yet."}
```

While a card waits, `pending` lists the id and the row's `why` is `Off. A card to turn it on is waiting for your answer.`
Other `why` texts are the existing ones (`On, but the main second-card switch is off.`, `On, but qwen3:8b is not
installed yet. Install it (Brain, Models, or 'ollama pull qwen3:8b' in a terminal) and it starts working.`, `On, but
it cannot run: ... Your choice is kept; it works again once a capable second card is back.`). For `referee` the
model and lane texts never appear: it has no model, so `model`, `model_installed` and `memory_gib` are `null`
even on a capable PC. `third.assignable` never lists `referee`.

### 13.2 POST bodies and answers (the existing route, unchanged)

`POST /api/second-card`, header `X-Jarvis-Client: hud`, body `{"feature": "study" | "referee", "enabled": true | false}`.

| Situation | Status | Body |
|---|---|---|
| OFF | 200 | `{"ok": true, "enabled": false, "pending": false, "message": "\"Study helper\" is off."}` (or `"\"Referee suggestions\" is off."`) |
| ON, a card is raised | 200 | `{"ok": true, "enabled": false, "pending": true, "message": "Approve the card on your PC or phone to turn it on. Nothing changes until you do."}` |
| ON, already on | 200 | `{"ok": true, "enabled": true, "pending": false, "message": "\"Study helper\" is already on."}` |
| unknown id | 400 | `{"error": "there is no second-card feature called 'x'"}` |
| the main switch is off | 400 | `{"error": "Turn on the second graphics card itself first (the main switch), then this one."}` |
| a card for it is already waiting | 409 | `{"error": "a card to turn on \"Study helper\" is already waiting - approve or deny that one"}` |
| "One bigger model on both cards" is on | 409 | `{"error": "\"Study helper\" cannot be turned on: \"One bigger model on both cards\" is on, and needs both cards to itself. Turn that off first."}` (`referee` is not blocked by it, and never blocks it) |
| no capable second card | 503 | `{"error": "\"Study helper\" cannot be turned on: <the reason>."}` |
| the gate line is not `ask` | 503 | `{"error": "second_card_enable is tier '<tier>' in jarvis-framework.toml; turning this on needs a person to say yes, so it must be 'ask'"}` |
| `{"feature": "third", "assign": "referee"}` | 400 | `{"error": "\"Referee suggestions\" loads no model, so there is nothing to move to the third card."}` |

The apps send only what they already send for the five older switches; the errors are shown as the backend
words them. On a stale link the switches are held (rule 4), as for the other five.

### 13.3 The enable cards (action `second_card_enable`, tier `ask`; the card is shown by the existing approval screens)

Study helper (`<card>` is the detected card's name, memory and id):

```
Turn on "Study helper" on the second graphics card?

What it does: Quiz questions are written, and your answers marked, on the second card, so a quiz never slows the everyday chat. The text you paste and the answers you type stay on this PC.

Which card: the NVIDIA GeForce RTX 2060 (12 GB, id GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23).
Which model: qwen3:8b, with room for 32,768 tokens - about 7.7 GB of the card's 12 GB.

Jarvis starts a second copy of Ollama that uses only that card and listens on 127.0.0.1:11435 - this PC only, not your network or the internet. Nothing leaves this PC.

If you did not just ask for this, say no.

If you say no: nothing changes. This keeps working the way it does today, on the NVIDIA GeForce RTX 2080 SUPER.
```

Referee suggestions:

```
Turn on "Referee suggestions"?

What it does: When a goal step's number reaches your target, Jarvis asks "This looks done - tick it?" on a card that shows the numbers. Only your tap ticks it: Jarvis never ticks a step by itself and never runs a test. Today it compares numbers on this PC and loads no model.

Which card: the NVIDIA GeForce RTX 2060 (12 GB, id GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23) - it must be there to switch this on, because the later version (reading a project's changes) will use its model.
Which model: none yet. Nothing is loaded and no second copy of Ollama is started for this. Nothing leaves this PC.

How it asks: at most a few cards a day, one at a time, never while you are in a focus session or Jarvis is in Quiet or Standby. Each card shows the numbers and says "a suggestion from a number, not a check". Your tap ticks the step, the same as ticking it yourself, and you can untick it at once. It never runs a test, and it only looks at your own goals.

If you did not just ask for this, say no.

If you say no: nothing changes. Goal steps are ticked only by you, as today.
```

### 13.4 The "This looks done" card (action `referee_tick`, tier `ask`, reversible and local: not a risky approval)

Raised by the backend only, at most 3 in 24 hours, never during a focus session, Quiet, Standby or mid-chat.
It arrives as an ordinary approval card (`GET /api/pending`); the apps need no new screen for it. Words, exactly:

```
This looks done - tick it?

Goal: "run a 5k"
Step: "get under 30 minutes"
Evidence: "5k time" is now 29.5 min, and your target is 30 min (lower is better).

This is a suggestion from a number, not a check. Jarvis only compared the latest number you logged with your target. It did not run a test, and it cannot tell whether the work is really finished - only you can say that.

If you say yes: this step is ticked, the same as if you had ticked it yourself. You can untick it at once in Goals.
If you say no: nothing changes, and Jarvis will not ask about this step again for a day, then a week, then a month.
```

For a health or money number the block `This number is private (health or money): it is shown on this screen only and is never read aloud or sent anywhere.` is added before the "If you say yes" line, and the
gate `detail` carries `"keep_on_screen": true`. The card's title on lock screens and in the approval widget is
built from the action's plain words (`jarvis_card_words.py`): `tick a goal step whose number reached its target`.
**Yes** ticks the step (the PC sets `done_at`); **No** and a timeout change nothing. Undo is the ordinary
untick, `POST /api/goals/<id>/step` with `{"id": "<step id>", "done": false}`. How it ended
(`ticked`, `denied`, `timed_out`, `stale`, `withdrawn`, `refused`, `failed`) is kept on the PC in words
(`jarvis_referee.status()`), and no route serves it: the Goals screen simply shows the step ticked or not.
"What asks first" lists `referee_tick` under "Timers and reminders" (never loosenable).

### 13.5 What each app must build

**Nothing new for the switches.** Both apps build their second-card list from `features[]` (the desktop from
`status.features` in `settings.js`, `scPaint`; the phone from `SecondCard.switches(status)`), and the Rust
shell passes `GET /api/second-card` through unchanged, so **Study helper and Referee suggestions appear
in both apps with no code change**, with their names, `what`, `why` and the ordinary card flow. Checked by
reading; no app was run against a real PC.

Edits that are needed, exactly:

1. **Phone test** `jarvis-client/app/src/test/java/com/jarvis/client/SecondCardContractTest.kt`: the lists
   `listOf("long_context", "vision", "learning", "browser_control", "wiki")` at the test
   ``all eight cases are read, with the five features in the PC's order`` (line ~60) and at
   ``combined - its own row, not one of the five features...`` (line ~207) become
   `listOf("long_context", "vision", "learning", "browser_control", "wiki", "study", "referee")`
   (rename the first test to "seven features"). The regenerated `second-card-cases.json` (desktop and phone
   copies, additions only) already has the two rows in all eight cases; the case count is still eight.
2. **Desktop model line** `jarvis-desktop/src/settings.js`, `scModelLine` (it needs `scPaint`'s `detected` passed in): for a feature with `model === null`
   on a PC where `status.detected.capable === true` (only `referee`), show no model line and no memory line.
   Today it would print "The model is chosen once a capable second card is found." under Referee
   suggestions on a capable PC, which is wrong. (The phone already shows no model line for `model: null`.)
3. Optional, both apps' checklist text ("five switches" -> "seven") wherever it is written in words.

The apps do **not** read `referee`'s outcome and show no second screen for it. If the apps ever show the
`keep_on_screen` mark, note that whether the gate's `/api/pending` row passes `detail.keep_on_screen` on is in
the owner's `jarvis_gate.py`, which this repository does not hold - **not checked**.

### 13.6 What is not built (follow-ups, written down)

* **The diff candidate.** "This looks done" for a coding task from its change summary, using the second card's
  model, labelled "a guess by the small model, not a check". A goal step can only follow a number today, and
  `jarvis_apps.py`'s per-task summary has nothing to be linked to, so only the number candidate is built.
* **Marking with the bigger local model** (`qwen3:14b`, "One bigger model on both cards"): out of scope for
  `study`. It ties up both cards, so it could not run beside the quiz's lane.
* The quiz's grader has not been run on the second card's model; marks made there stay "Jarvis's guess".
* Nothing has run on the real second card.

## 14. Slice contract (frozen 2026-09-30): YouTube captions

Slice B, built on the backend (2026-09-30); the apps build from this. The owner's rules (section 7, answer 1): **allowed, one card per link, caption text only**; it breaks YouTube's terms and may be blocked and the owner accepts that; never video or audio. API: `docs/JARVIS-API.md` section 112 (109 and 111 are reserved by the build queue, 110 is taken). Backend: `backend/jarvis_youtube.py`, `backend/youtube.patch`, the hook `jarvis_quiz.start_outside`, `backend/test_youtube.py`. **Not tried against the real YouTube** (network policy in the build container): the first real try on the owner's PC is `py -3 -c "from youtube_transcript_api import YouTubeTranscriptApi as Y; print(len(Y().fetch('dQw4w9WgXcQ')))"` after `apply-patches.ps1` installs the package.

**Where it lives.** A second block on the existing "Quiz me on a text" page in both apps (not a new page): under the paste box, a link field and a button. The result is the ordinary quiz screen. No new Brain entry. The desktop's Rust reads/writes through new commands in `src-tauri/src/brain/quiz.rs` (or a sibling `youtube.rs`); the phone in `net/Quiz.kt` / a new `net/YouTube.kt`. **Builders do not edit `jarvis_youtube.py`, `youtube.patch` or the gate.**

**The flow (both apps identical).**
1. The owner pastes a link and presses **Read the captions and write questions**. The app sends `POST /api/youtube/quiz` `{url, count}` (count from the same question-count control the text quiz has; `language` is not offered in the first version). The app does NOT check the link itself beyond "not empty": the PC's refusal message is shown as is.
2. On **202** the app shows `request.message` ("Waiting for your yes on the approval card.") and **polls `GET /api/youtube/{id}` about every 2 seconds** (stop polling at any end state or when the page closes). The card itself is an ordinary approval (`/api/pending`), decided in the apps' existing approval screens - a **risky approval** (Windows Hello / phone screen lock), never by voice, never from the widget's Approve on the phone without the lock. The desktop widget sends this card's Approve to the Jarvis bar, as for email.
3. States: `waiting` -> `fetching` -> `writing` -> `ready`. On `ready` the app opens `request.quiz` as the ordinary quiz (all of section 98 unchanged; answering uses `/api/quiz/{id}/answer`). On `denied`, `timed_out`, `withdrawn`, `refused` or `failed` the app shows `request.message` and offers the link field again. A **Cancel** button (`POST /api/youtube/{id}/cancel`) is shown only in `waiting`; it is never held on a stale link.
4. `request.truncated` true: show `request.message` above the questions (it already says the quiz covers only the first part).
5. A quiz with `provenance: "outside"` shows the **outside line** (below) in place of "This text is treated as outside text..." and a small label `From YouTube captions`. Answer marking, Finish, Stop and the crisis message are exactly the text quiz's.

**Rules for the apps.**
* **Rule 4 / stale link:** the start button is held (greyed, with the app's usual "waiting for a live link" words) on a stale link. Polling, Cancel and reading a finished quiz are not held.
* **Under "Hide memory lists and chat history":** the link field's text, `request.link` and the quiz's words are hidden like the text quiz's; the state message and Cancel stay. Never keep the pasted link anywhere on the app side (not in a saved draft, not in a log, not in a notification). Clear the field once the card is raised.
* **App lock (desktop):** the page is behind the lock like the rest of Quiz.
* **Never** put the link or a video id into a notification, a toast, a widget line or the desktop tray. Approval-card titles are the PC's words (`Jarvis wants to fetch the caption text of a YouTube video for a quiz`); an app does not build a card text itself.
* **A PC without the feature** answers `GET /api/youtube` with 404 (or 503): show "Your PC's Jarvis does not have YouTube quizzes yet - run apply-patches.ps1 on the PC." and hide the block. Do not probe by starting a request.
* **Speech:** questions and marks are ordinary answers; none is read aloud (outside text). The crisis message (section 98.4) is shown as for a text quiz.
* **Keep (section 102):** unchanged in the apps. See the open question below.

**Shared words (both apps, word for word; the PC also sends them in `GET /api/youtube`).**
* Block title: `Quiz me on a YouTube video`
* Intro: `Paste a YouTube link and Jarvis reads the video's captions (the words shown as subtitles), then quizzes you on them. It asks with a card first, every time.`
* The terms line (shown under the link field, always visible, not behind a tap): `This breaks YouTube's terms and may be blocked. Only the caption text is fetched - never the video or its sound. The link tells YouTube which video you are studying.`
* Outside line (during and after the quiz): `The captions are treated as outside text: Jarvis never learns facts from them. Your answers are marked by the model on this PC.`
* Link field placeholder: `Paste a YouTube video link`
* Start button: `Read the captions and write questions`
* Cancel: `Cancel`
* Small label on the quiz: `From YouTube captions`
* Missing feature: `Your PC's Jarvis does not have YouTube quizzes yet - run apply-patches.ps1 on the PC.`
* State messages come from the PC (`request.message`); for reference: `waiting`: Waiting for your yes on the approval card. `fetching`: Reading the captions from YouTube... `writing`: Writing the questions... `ready`: Ready. `denied`: You said no, so nothing was fetched. `timed_out`: Nobody answered the card in time, so nothing was fetched. `withdrawn`: You cancelled before the card was answered, so nothing was fetched. `refused`: The card could not be answered, so nothing was fetched. `failed`: Could not make a quiz from that video.
* Every refusal and failure message comes from the PC (section 112.2); the apps never rewrite it and never show an error code.

**Wire shapes (frozen).** `POST /api/youtube/quiz` `{"url": str, "count": 1-10?, "title": str?, "language": str?}` -> 202 `{"ok": true, "waiting": true, "request": Request, "message": str}`; `GET /api/youtube/{id}` -> `{"ok": true, "request": Request}`; `POST /api/youtube/{id}/cancel` `{}` -> `{"ok": true, "request": Request}`; `GET /api/youtube` -> `{"ok": true, "available": true, "title", "intro", "terms", "outside", "limits": {"link", "text", "count_min", "count_max"}, "latest": Request | null}`. `Request` = `{"id", "state": "waiting"|"fetching"|"writing"|"ready"|"denied"|"timed_out"|"withdrawn"|"refused"|"failed", "message", "link", "truncated", "minutes", "error", "quiz": Quiz | null, "provenance": "outside", "source": "youtube"}`. `Quiz` gains, only for these quizzes, `"provenance": "outside"` and `"source": "youtube"` (additive; a text or Spanish quiz has neither key). Errors are `{"ok": false, "error", "message"}` with the codes in section 112.2. **Decode leniently:** ignore unknown keys and unknown `state` values (treat an unknown state as still working, and stop after 3 minutes with the PC's last message).

**Fixtures.** The words above and a set of example `Request` shapes are for `tools/gen_youtube_cases.py` (not written yet; the first app builder writes it, in the pattern of `gen_decks_cases.py`, and both apps' tests read the file). Until then the shapes here are the contract.

**Parity.** `tools/check_parity.py` lists `/api/youtube`, `/api/youtube/quiz`, `/api/youtube/{id}` and `/api/youtube/{id}/cancel` as `planned`. The app builder moves them to `ported` (with the file names) when built. Nothing about this feature is deliberately one-sided.

**Open question for the owner (not decided; built the careful way meanwhile).** A kept question copies its **passage**, which here is caption text, into the review deck as the owner's own tap. Captions are outside text; the deck is not memory and is never learned from, so the backend allows it. If the owner would rather a video's questions could not be kept, the change is one line in `jarvis_quiz.finish` (refuse Keep when `provenance == "outside"`). Until told otherwise, Keep works and the deck row shows the same `From YouTube captions` label is NOT carried (the deck has no source field) - so a kept card's passage looks like any other. That is the known gap.

**What is not in this slice.** A model tool or chat door for it (`jarvis_agent.py` untouched, so "quiz me on this video" in chat is not yet understood); playlists; a timestamped outline; choosing a caption language in the apps; Spanish-mode practice from captions; the cloud "grade this better" button; any audio or video download (refused for good, section 9); the second-card "Study helper" for this quiz (it uses whatever lane the quiz uses).

**Known limits, said plainly.** Never run against the real site here. YouTube may refuse this PC's address (`youtube_refused`), change how captions are served (`youtube_failed`), or close nothing of the owner's - no account or cookie is involved. An auto-generated caption is used when no human-made one exists, and can be wrong; the quiz is marked against it anyway.
