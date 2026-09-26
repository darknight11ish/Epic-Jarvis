# Cutting-edge audit, round 2, 2026-09-26: personality, presence, learning and making things

One slice of the owner's "What else can we add?" request: things that make
Jarvis feel alive and useful beyond chores - the face, a steady character,
teaching, languages, games, making pictures and sounds, long audio, a code
helper and "explain simply". Everything here is meant to run on this PC.

**Limits.** Research only: nothing was built, run or measured. Repo
`file:line` references were checked on 2026-09-26. huggingface.co, ollama.com
and arxiv.org are blocked here, and so is the GitHub API; GitHub `README` and
`LICENSE` files were read directly (raw files). Anything from a search
summary is marked *(search summary)*; what a project says about itself is
marked *(claim)*. Not repeated here: the "waking up" / "checking your voice"
face states and the small "fact saved" glint (`creativity-2026-09-25/experience.md`
§3.5), the manner setting (built), OCR, voices and wake word
(`CUTTING-EDGE-2026-09-26-voice-vision.md`), the model shortlist
(`CUTTING-EDGE-2026-09-26-engine.md` §8).

---

## In six lines, for the owner

1. **Cheapest wins first:** let Jarvis answer "who are you / what can you do /
   which model are you" from its own settings instead of letting the model
   make it up, and add an **"Explain simply"** switch and a **speaking-speed**
   setting. All small, no new downloads.
2. **The face already moves with Jarvis's voice** (loudness). It can also
   follow the *shape* of the sound (open vowels vs hissy "s" sounds) and have
   a little idle life, using what is already there. Real lip-sync only makes
   sense if a face with a mouth is ever designed.
3. **Games and role-play should run in a temporary chat.** Automatic learning
   saves facts from your own words, and nothing in it tells a game from real
   life - "I'm a dragon" could be saved as a fact about you.
4. **Learning:** "quiz me on this note", then Jarvis asks again on a smart
   schedule (the same maths Anki uses, free MIT code) using the one scheduler.
   Plus translation and language practice, typed first.
5. **Long audio you give it** (a podcast file, a lecture, a voice memo) can be
   turned into text and a summary on the PC with the parts Jarvis already
   has. Jarvis should never download from YouTube itself.
6. **Making pictures and music works locally in 2026 on the 12 GB card**, with
   licences that allow it (FLUX.2 klein 4B and ACE-Step are fully open). They
   are big to build and fight the long-conversation lane for memory - later.

---

## Ranked table

Card: CPU (the processor), 2080S (the 8 GB card now), 2060 (the 12 GB card
coming). Size: S = a day or so, M = a few days, L = a week or more.

| # | Idea | Why it matters | Size | Card | Rule risk |
|---|---|---|---|---|---|
| 1 | "About Jarvis" answered from settings, plus a "you told me" check | A steady character that cannot invent what it is, what it can reach or what you said | S | none | None - it tightens |
| 2 | "Explain simply" switch + speaking speed in both apps | You are learning; answers that define jargon first. Slower speech helps everyone | S | none | None (wording only, like manner) |
| 3 | Face follows the voice's shape, not only its loudness | Feels like it is *talking*, on all twenty faces, with no new model | S | CPU / phone | None |
| 4 | Idle life: a slow glance, dozing, a calmer look at night | The face feels present without asking for attention | S-M | CPU / phone | None, inside the flash limits |
| 5 | Games and small talk in a temporary chat | Fun without false facts being learned | S | 2080S | Low, if kept temporary |
| 6 | "Quiz me on this note" + smart review times (FSRS) | Remember what you study; uses your own notes | M | 2080S + CPU | Low: notes are outside text |
| 7 | Summarise an audio file you give it | Podcasts, lectures, voice memos, without uploading | M | CPU (+2080S for the summary) | Low: the transcript is outside text |
| 8 | "Translate this" | Everyday need; local keeps private text private | S (everyday model) / M (dedicated model) | 2080S / CPU / 2060 | None |
| 9 | Language practice (typed now, spoken later) | Conversation practice with gentle corrections | M | 2080S | Low, in a temporary chat |
| 10 | Code helper for a beginner: explain, never edit on its own | Understand errors and your own code | M | 2080S / 2060 | Low: reading only; edits would be cards |
| 11 | Make and edit pictures | "Draw a birthday card for Mum", "remove the background" | L | 2060 | Medium: files, other people's faces |
| 12 | Lip-sync mouth shapes | Only for a face with a mouth | M | CPU | None |
| 13 | Make music and sound effects | A focus-session loop, a custom alarm sound | M-L | 2060 (or CPU, small model) | Low |

---

## Details

### 1. "About Jarvis" from settings, and a "you told me" check (S)

- **What.** "Who are you / what model are you / what can you do / what do you
  know about me" answered without the model, from the settings "What can you
  reach?" already reads. And when an answer says "you told me" or "I remember"
  but no saved fact went into it, the app adds: "No saved fact was used in
  this answer."
- **Why.** Models drift from their instructions as a chat grows and start to
  mirror the user ([persona_drift](https://github.com/likenneth/persona_drift):
  within eight rounds on a large model). Jarvis already places its manner and
  spoken notes next to the newest question (`jarvis_agent.py:3191`), which is
  the right counter. The gap is self-description: the model is told only "You
  are Jarvis, a private assistant running entirely on this machine"
  (`jarvis-primary.Modelfile:160`), so "can you read my email?" is a guess.
- **Plugs into.** `jarvis_quick.py` (`match`, 608; `_run_reach`, 1420, reads
  `jarvis_reach.KINDS`, `jarvis_reach.py:692`). The check reads
  `injected_facts` from `X-Jarvis-Route` (`JARVIS-API.md` §4) in
  `answer-memory.js` and the phone's twin. Tightens rule 6 of ARCHITECTURE §2.

### 2. "Explain simply" and speaking speed (S)

- **What.** Beside "How Jarvis talks", a switch **Explain simply**: say what a
  thing is before naming it, short sentences, one example. Separate from
  Warm/Plain. And **Speaking speed** (slower / normal / faster).
- **Why.** It is the owner's own rule (`CLAUDE.md`, "Explain things simply"),
  for every answer. Speed exists only in the settings file (`tts_speed`,
  `jarvis_speech.py:1818`); neither app shows it (searched both).
- **Plugs into.** A second line in `jarvis_manner.py` (`NOTE`, 72), placed by
  `with_manner_note`, held by `test_manner.py`'s "wording only, every rule
  still applies". Custom voices take a speed too (`jarvis_voices.speak`, 1417).
  No card either way, like manner.

### 3. The face follows the voice's shape (S)

- **Exists.** Loudness drives every face: `voice.js` (`attachAnalyser`,
  297-335) and `Speaker.kt:276` (`Wav.rms`) feed `setSpeechLevel`
  (`faces.html:3282`, `FaceView.kt:80`; spec `faces-spec.js:1956-1971`).
- **New.** Split the same sound into bands: low (open vowels, "ah") and high
  (hiss, "s"). Openness drives the scale push as now; hiss adds fine ring
  detail. Most of what lip-sync gives an abstract face, with no model, on
  every voice. The Spectrum face (`faces.html:1298`) could show real bands.
- **Rules.** Movement, not brightness: inside the flash limits
  (`faces-spec.js:631-641`). Shared spec data, so both apps.

### 4. Idle life (S-M)

- **What.** Slow, non-repeating life when nothing happens: a glance (the Iris
  face, "It is looking back", `faces.html:2231`), dozing after a long quiet
  spell, a calmer look in the evening or quiet hours, a brief "perk up" when
  "Hey Jarvis" is heard.
- **Rules.** Idle is a steady "breathe" today (`state_rules.idle`). Keep the
  idle frame-rate savings (`state_fps`, `faces-spec.js:564`) and reduced
  motion (`JarvisTheme.kt:351`; `faces.html`). Never look like "approval".

### 5. Games and small talk, in a temporary chat (S)

- **What.** 20 questions, trivia, riddles, "would you rather", a story
  together - started by a **Play** button or "let's play", as a temporary chat.
- **Why temporary.** Automatic learning saves facts from the owner's own
  typed or said words (`jarvis_auto_learn.py:583`). I searched it and
  `jarvis_sensitive.py` for games or pretending and found nothing, so "I'm a
  pirate captain" in a game could become a fact. A temporary chat already
  recalls, learns and keeps nothing (`JARVIS-API.md` §4) - no new mechanism.
- **Rules.** Trivia can be wrong; the rules block still says what is a guess.
  Jarvis never plays a real person or company, never asks for personal
  details. No "want a riddle?" offers (or only via `jarvis_backoff`).

### 6. "Quiz me on this note" with smart review times (M)

- **What.** The owner picks a note; the local model writes 5-10 question
  cards; the owner keeps, edits or drops each. Jarvis asks them again, spaced
  out as they are remembered, using **FSRS** (the scheduling maths in Anki):
  [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs), **MIT**
  (LICENSE read). Obsidian plugins already do this with Ollama
  ([obsidian-quiz-generator](https://github.com/ECuiDev/obsidian-quiz-generator)).
- **Plugs into.** `jarvis_notes.plan`/`run` (`jarvis_notes.py:266`, 536) to
  read; a new kind on the one scheduler (`jarvis_schedule.register_kind`,
  313) for "N cards due" in Coming up; cards in their own small database,
  NOT memory.
- **Rules.** The note is outside text (it marks the turn). Quizzes run as a
  temporary chat, so answers are never learned. A new repeating kind asks
  once by default (ARCHITECTURE §12); whether reviews go without a card, like
  plain reminders since 2026-09-26, is the owner's call.

### 7. Summarise an audio file the owner gives (M)

- **What.** Drop a podcast, lecture or voice memo file on the Jarvis bar (or
  share it from the phone). The PC cuts it into speech pieces with Silero,
  turns them into text with Parakeet (both already there), and the everyday
  model summarises in slices.
- **Plugs into.** `jarvis_speech._speech_span` (380) and `_transcribe` (329)
  in a background job; the live 30-second cap (`max_seconds`, 944) stays.
  MP3/M4A needs a decoder such as ffmpeg (new dependency). Seconds on a big
  GPU *(search summary)*, minutes on the processor; unmeasured.
- **Rules.** Speech-to-text on the PC only. A recording is not the owner
  speaking live: its words are outside text, never learned. Parakeet v2 is
  English only (v3: 25 European languages, CC-BY-4.0, *search summary*).

### 8. "Translate this" (S, then M)

- **Now (S).** The everyday model (Qwen3 8B) with a fixed translation
  instruction and no tools; no download. Quality not measured here.
- **Later (M), a dedicated model** if quality is not enough:

| Model | Licence | Size | Notes |
|---|---|---|---|
| [Hy-MT2 1.8B](https://github.com/Tencent-Hunyuan/Hy-MT2) (Tencent, May 2026) | **Apache-2.0** (its `LICENSE.txt`, read) | 1.8B; GGUF for llama.cpp | 33 languages. "Surpasses ... Microsoft" *(claim)*. Its 1.25-bit file needs a special llama.cpp change (PR #22836, merge not checked) - use the normal GGUF |
| TranslateGemma 4B/12B (Google, Jan 2026) | Gemma Terms of Use (not open source; fine for personal use) | 4B fits 2080S beside nothing else, or CPU | 55 languages; in Ollama's library as `translategemma:4b` *(search summary)* |
| MADLAD-400 3B (Google) | Apache-2.0 *(search summary)* | 3B | 419 languages; needs a separate runtime (CTranslate2) |
| NLLB-200 (Meta) | **CC-BY-NC-4.0 - non-commercial only**; allowed under rule 5 | 600M-3.3B | 200 languages; older |

- **Rules.** Local only, so private text can be translated. Pasted text is
  outside text, as today. A dedicated model is an install, which is already
  an approval card (`/api/models/install`).

### 9. Language practice (M)

- **What.** "Let's practise French": a short conversation at the owner's
  level, one gentle correction per turn, new words added to item 6's list
  only when the owner picks them. Temporary chat, so nothing is learned.
- **Honest limit.** Typed practice works now. **Spoken practice does not:**
  Parakeet v2 hears English only, and Kokoro in sherpa-onnx speaks only
  English and Chinese *(search summary)*. It would need Parakeet v3 loaded
  just for practice (the voice report keeps v2 for everyday speed).

### 10. Code helper for a beginner (M)

- **What.** "Help me understand this": paste an error or name a file in a
  folder the owner chose; Jarvis explains in plain words (item 2), says what
  to try and where. It never edits by itself.
- **Plugs into.** `file_read` (`jarvis_agent.py:199`, 200 KB cap at 175);
  `ast-grep` to pull out only the relevant code (`ARCHITECTURE.md` §11).
  Any edit later: a full diff on a card, applied in a git worktree (§11, §3).
- **Model.** The everyday model first; on the 12 GB card `qwen2.5-coder:14b`
  (~9 GB, Apache-2.0 - its 3B size is research-only) *(search summary)*, or
  the already-planned Qwen 3.5 9B. Test before choosing.
- **No build at all:** VS Code's Continue extension can use the local Ollama;
  set `allowAnonymousTelemetry` to false (on by default, *search summary*).
  Code is files: rule 1, local only.

### 11. Make and edit pictures (L, 2060)

- **What.** "Draw a birthday card with a cat", "remove this photo's
  background". Saved to a Jarvis folder on the PC, shown in the app.

| Model | Licence | Memory | Notes |
|---|---|---|---|
| [FLUX.2 klein 4B](https://github.com/black-forest-labs/flux2) (Jan 2026) | **Apache-2.0** (README's table) | "fits in ~8GB VRAM" *(claim)*; ~13 GB full size *(search summary)* | Makes AND edits. The 9B is non-commercial |
| Z-Image-Turbo 6B (Alibaba) | code Apache-2.0 (LICENSE read); weights Apache-2.0 *(search summary)* | 14-16 GB full, ~6-8 GB squeezed *(search summary)* | Photo-real; text in images |
| SDXL-Turbo (Stability) | non-commercial research licence - fine under rule 5 | smaller | Older, 512 px |

- **Engine.** [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp)
  (MIT) runs FLUX.2 klein 4B and Z-Image from single files and can move parts
  to the processor (`docs/flux2.md`, read). Ollama's picture-making was
  macOS-only *(search summary)*.
- **Plugs into.** A sixth switch in `jarvis_second_card.FEATURES`
  (`jarvis_second_card.py:214`), on by one card; started on demand and
  stopped when idle, like the F5 "better voice".
- **Honest problems.** The 12 GB card is planned for the 14B long-conversation
  model (10.4 GiB, `MODEL-TOPOLOGY.md`): a picture means unloading it first,
  and the app must say so. Turing cards lack fast bf16 maths, which these
  models are shipped in. Neither checked.
- **Rules.** The owner's photos stay local. Refuse turning a real person's
  face into something or someone else. Overwriting an existing photo would be
  a card; saving a new file in Jarvis's folder is not.

### 12. Lip-sync mouth shapes (M, only with a mouth)

[HeadTTS](https://github.com/met4citizen/HeadTTS) (MIT) gives Kokoro mouth
shapes with timings, but it is a separate JavaScript Kokoro, English only,
fetching voices from huggingface.co unless copied locally.
[Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync) (MIT)
works on any recording, but real-time use is an open request (issue #135).
Jarvis's Kokoro call returns sound only (`jarvis_speech.py:1815`). **Only
worth it for a face with a mouth**; item 3 covers the abstract faces.

### 13. Music and sound effects (M-L)

[ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) (README: "licensed
under MIT"; weights' own page not read): songs with lyrics, "less than 4GB of
VRAM" *(claim)*, 8-12 GB for the full set-up by its own table; a Windows
package. Stable Audio 3.0 Small (May 2026, 459M, Stability Community licence,
for laptops and phones, *search summary*). Mostly fun (a focus-session loop,
an alarm sound). Low priority.

---

## Not for Jarvis, and why

- **Guessing the owner's mood from their voice** (e.g. emotion2vec, MIT).
  It infers a private, health-like state the owner never said; "personality
  guessing" was already left out (`RESEARCH-2026-09-24.md` §3). The face
  already reacts to how loud the owner is.
- **Downloading from YouTube or podcast sites** (yt-dlp and similar). A new
  way out of the PC (`ARCHITECTURE.md` §4) and against YouTube's terms.
  Item 7 takes files the owner gives it.
- **Photo-real talking heads or face swaps.** A face made from a real
  person's photo is a fake of that person.
- **A persona file the model rewrites** (like Meta Muse's `Soul.md`,
  `COMPETITORS-MUSE-2026-09-25.md`). The model would be changing its own
  instructions with no review.
- **Streaks and guilt nudges** ("you'll lose your 30-day streak!"). Offers
  are few and backed off (`jarvis_backoff.py`); guilt is not a helper's job.
- **Cloud picture, music or translation services** (Midjourney, Suno, Google
  Translate). Rule 1; local options exist.
- **Other people's voices copied for games.** Impersonation.
- **Quizzes made automatically from emails or web pages.** Outside text
  choosing what Jarvis does; the owner picks the note.

---

## Questions for the owner

Jarvis can play word games and small quizzes with you. To make sure a game
never saves a made-up "fact" about you, games would always start a temporary
chat, which remembers nothing.

- **Games always in a temporary chat** (recommended)
- **Normal chat, and I will correct mistakes myself**

Making pictures on the 12 GB card means the long-conversation model has to
step aside while a picture is made (about a minute, unmeasured).

- **Build it later, once the card is in and measured** (recommended)
- **Not interested in pictures**

---

## What I could not check

- No model here was run, so every speed and memory figure is a claim or a
  search summary. Nothing was tried on a Turing (RTX 20-series) card.
- Model pages on huggingface.co and ollama.com (licences of TranslateGemma,
  MADLAD-400, Stable Audio 3.0, Parakeet v3 are from search summaries).
- Whether sherpa-onnx's Kokoro can return timing for each sound (not in
  Jarvis's call; sherpa-onnx source not read).
- Whether the Continue extension's telemetry default is still "on".

## Sources

Read directly (README or LICENSE on GitHub): [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) · [Hy-MT2](https://github.com/Tencent-Hunyuan/Hy-MT2) · [flux2](https://github.com/black-forest-labs/flux2) · [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp) · [Z-Image](https://github.com/Tongyi-MAI/Z-Image) · [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) · [HeadTTS](https://github.com/met4citizen/HeadTTS) · [Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync) (and [issue #135](https://github.com/DanielSWolf/rhubarb-lip-sync/issues/135)) · [audiocraft weights licence](https://github.com/facebookresearch/audiocraft) (CC-BY-NC-4.0).

Search summaries only: [persona drift paper](https://arxiv.org/abs/2402.10962) and [code](https://github.com/likenneth/persona_drift) · [obsidian-quiz-generator](https://github.com/ECuiDev/obsidian-quiz-generator) · [TranslateGemma](https://blog.google/innovation-and-ai/technology/developers-tools/translategemma/) · [NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) · [MADLAD-400](https://github.com/google-research/google-research/tree/master/madlad_400) · [Parakeet v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) · [sherpa-onnx Kokoro](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html) · [SDXL-Turbo licence](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md) · [Ollama image generation](https://ollama.com/blog/image-generation) · [Stable Audio 3.0](https://stability.ai/news-updates/meet-stable-audio-3-the-model-family-built-for-artistic-experimentation-with-open-weight-models) · [Qwen2.5-Coder](https://qwenlm.github.io/blog/qwen2.5-coder-family/) · [Continue + Ollama telemetry](https://www.noze.it/en/insights/continue-ollama-on-prem/) · [emotion2vec](https://huggingface.co/emotion2vec/emotion2vec_plus_large).
