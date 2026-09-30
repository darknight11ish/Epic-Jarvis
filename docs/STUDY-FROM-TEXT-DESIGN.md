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
(plain message: the local model did not answer; nothing was changed).
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
