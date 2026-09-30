# Report 24 (outside-suggestion-check), agent a6c3fee6, 2026-09-30T04:54Z

> **What it was asked** (first 600 characters of the task): The owner asked: "Can Jarvis help me with educational topics? Learning things from YouTube, and learning Spanish?" Gemini suggested these repos: open-spaced-repetition/py-fsrs and fsrs-rs (FSRS scheduler), ukimsanov/lectureflow (YouTube lecture -> concepts/quizzes/cloze cards), kamui-fin/yt-to-anki (subtitle sentence + audio clip + frame cards), bjsi/incremental-everything (incremental video, SuperMemo-style plugin), kirill-markin/flashcards-open-source-app (MCP review endpoints). Gemini also proposed a pipeline: YouTube ingest (yt-dlp + ffmpeg) -> cards with audio/frame -> FSRS scheduling in 

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Short answer: Jarvis can already help with learning through ordinary chat. It has no flashcard, YouTube or Spanish-tutor code. FSRS quizzes are queued but deferred. I would use py-fsrs, borrow ideas from two other repos, and skip the rest. I could not check any repo's licence, because GitHub access was refused ("GitHub access to this repository is not enabled for this session").

**1. What Jarvis does today (checked)**
- Chat explanations, web search (SearXNG, DuckDuckGo, Exa, Tavily and Brave, in `backend/jarvis_search.py`), and Jarvis reading your own PDFs, Word files and notes. `backend/test_documents.py` line 24 says the document reader uses MarkItDown "document parts of MarkItDown only; requirements.txt never names [all], audio or YouTube".
- Voice in and out. The PC's speech-to-text is sherpa-onnx with NeMo Parakeet TDT 0.6B v2, described in `backend/jarvis_speech.py` as "English". It is not Whisper: a config naming faster-whisper is refused. Text-to-speech is Kokoro (`backend/jarvis_kokoro.py`).
- The Kokoro pack is "kokoro-multi-lang-v1_0", 54 voices. So Spanish voices exist in the file. The code marks them "every non-English voice: Jarvis speaks English", so they are not offered. Turning Spanish on is a change, not a switch. Spanish speech-to-text is not there either.
- Games and quizzes already run as a temporary chat (CLAUDE.md, "Games and role-play run in a temporary chat").
- I grepped `backend/` for yt-dlp, YouTube, flashcard and Anki. There is no such code. The only YouTube hits are the focus-session site list and a test that keeps MarkItDown's YouTube part out.

**2. Already decided or queued**
- `docs/AUDIT-2026-09-28-REPO-REFS.md`, milestone 3: "Quiz me on my notes" with py-fsrs (MIT, pure Python). It is deferred until a note-review screen is designed. It would be one new kind on the existing scheduler, and notes stay outside text.
- `docs/CUTTING-EDGE-2026-09-26-round2-personality.md`, idea 6, has the design. The model writes 5-10 cards, the owner keeps or drops each, the cards live in their own small database (not memory), and the quiz runs as a temporary chat.
- `docs/FEASIBILITY-AUDIT-2026-09-26.md` marked it "No" ("A daily-prompt machine and a new dependency"). The later milestone 3 entry replaced that.
- Quizzes made automatically from emails or web pages were refused (`docs/feasibility-2026-09-26/00-ideas.md`, line 1047).

**3. The repos**
Licences: not checked for any of them. I have not confirmed any of these repos exists beyond the audit doc naming py-fsrs.
- **py-fsrs**: use it. It is the queued plan, and the audit doc says MIT.
- **fsrs-rs**: skip. It is Rust, and the Python library does the same job.
- **lectureflow**: borrow the idea only (lecture to concepts to cloze cards). I have not looked at its code.
- **yt-to-anki**: borrow the idea only (subtitle sentence plus a clip). Its audio and frame clips need downloaded video.
- **incremental-everything**: skip. It is a SuperMemo-style plugin for another app.
- **flashcards-open-source-app (MCP endpoints)**: skip. It would be a second scheduler or tool layer, and MCP is limited to local programs on this PC.
- **yt-dlp** (Gemini's pipeline): downloading YouTube video breaks YouTube's terms. It also needs a new named way out of the PC in ARCHITECTURE §4, which needs the owner's OK and a card. Rule 1 is fine, since a public video is not private data. A safer start is for the owner to paste a transcript, or for Jarvis to read a caption file they save. That fits the existing document reader.
- No rule breaks: rule 5 allows non-commercial licences. Docker is not needed.

**4. Smallest first slice**
1. Learning by chat needs nothing new. Ask Jarvis to explain a topic or run a Spanish drill in a temporary chat.
2. Build the queued "Quiz me on this note" (milestone 3, without a review screen at first). The owner picks a note and the local model drafts cards. The owner approves them on a card. py-fsrs schedules them on the one scheduler.
3. For YouTube: the owner pastes the transcript into a note, and the note becomes the quiz source. That means no downloader, no new way out of the PC, and no terms problem.
4. For Spanish: text drills first (words and translations by typing). Spoken Spanish is a separate decision. It needs Spanish speech recognition, because Parakeet v2 is English-only. It also needs Jarvis to stop forcing English on Kokoro's Spanish voices.

**Owner decision:** do step 2 and 3 first (recommended), or wait for the note-review screen?
