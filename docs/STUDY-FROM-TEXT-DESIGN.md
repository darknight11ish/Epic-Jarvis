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

## 7. Questions for the owner

1. **Slice A first, with the grader tested before it is trusted?**
   Recommended: yes. (Slice B would then wait for Q2.)
2. **Reopen the 2026-09-26 "left out" decision for a YouTube caption fetch,**
   knowing it is against YouTube's terms, needs its own card per address, and may
   simply be blocked? Options: *yes, build Slice B after Slice A*; *no, keep
   YouTube out and use pasted transcripts only*.
3. **Should saved review decks (milestone 3) share the same quiz screen,** so
   there is one quiz system? Recommended: yes.

## 8. Not decided

Nothing above changes `CLAUDE.md`. If the owner answers Q1 and Q2, record the
decision there and in `docs/AUDIT-2026-09-28-REPO-REFS.md` §6.
