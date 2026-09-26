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

- **What.** Questions about Jarvis itself - "who are you", "what model are
  you", "what can you do", "what do you know about me" - answered without the
  model, from the same settings "What can you reach?" already uses. And when
  an answer says "you told me" / "you mentioned" / "I remember" but no saved
  fact went into that answer, the app adds one line: "No saved fact was used
  in this answer."
- **Why.** Models drift away from their instructions as a chat grows, and
  start to mirror the user (the "persona drift" study, below: noticeable within
  eight rounds on a large model). Jarvis already fights this the right way -
  the manner and spoken notes sit next to the newest question
  (`jarvis_agent.py:3191`, `with_manner_note`), not only at the top. The
  remaining gap is self-description: the model is told only "You are Jarvis,
  a private assistant running entirely on this machine"
  (`backend/jarvis-primary.Modelfile:160`), so "can you read my email?" is
  a guess.
- **Plugs into.** `jarvis_quick.py` (`match`, line 608; `_run_reach`, line
  1420 already answers "what can you reach?" from `jarvis_reach.KINDS`,
  line 692). The check uses `injected_facts` from the `X-Jarvis-Route` header
  (`JARVIS-API.md` §4) in `answer-memory.js` and the phone's equivalent.
- **Rules.** Tightens rule 6 ("nothing is claimed that is not true"). Both
  apps. Source: [persona_drift](https://github.com/likenneth/persona_drift)
  (paper 2402.10962; read through its GitHub page and search summary).

### 2. "Explain simply" and speaking speed (S)

- **What.** A switch in both apps' settings, beside "How Jarvis talks":
  **Explain simply** - say what a thing is before using its name, short
  sentences, one example. It is separate from Warm/Plain (plain AND simple is
  fine). And a **Speaking speed** choice (slower / normal / faster).
- **Why.** It is the owner's own standing rule for how things are explained
  (`CLAUDE.md`, "Explain things simply"), made available for every answer.
  Speed already exists but only in the settings file: `tts_speed` in `[voice]`
  (`jarvis_speech.py:1818`); no app shows it (searched both apps for it).
- **Plugs into.** A second line in `jarvis_manner.py` (`NOTE`, line 72;
  placed by `with_manner_note`), same "wording only, every rule still
  applies" test as `test_manner.py`. Speed: a setting both apps write.
- **Rules.** Wording only; no card either way, like manner. Check custom
  voices take a speed too (`jarvis_voices.speak`, line 1417, has `speed`).

### 3. The face follows the voice's shape (S)

- **What exists.** Loudness already drives every face: the desktop measures
  it in `voice.js` (`attachAnalyser`, lines 297-335) and the phone in
  `Speaker.kt:276` (`Wav.rms`), both into `setSpeechLevel`
  (`faces.html:3282`; `FaceView.kt:80`). The spec calls this out as the
  audit's biggest finding, now fixed (`faces-spec.js:1956-1971`).
- **What is new.** The same analyser can split the sound into two or three
  bands: low energy (open vowels: "ah") and high energy (hiss: "s", "sh").
  Feed "openness" to the scale push (as now) and "hiss" to a fine sparkle or
  ring detail. That is most of what lip-sync gives an abstract face, for no
  model and on every voice (Kokoro, custom voices, the phone fallback). The
  Spectrum face ("Frequency, standing up", `faces.html:1298`) could show the
  real bands.
- **Rules.** None. Must stay inside the photosensitivity limits
  (`faces-spec.js:631-641`: max 3 opposing changes a second): movement, not
  brightness flashes. The spec is shared data, so both apps get it.

### 4. Idle life (S-M)

- **What.** Small, slow, non-repeating behaviour when nothing is happening:
  a glance (the Iris face - "It is looking back", `faces.html:2231` - is
  made for this), dozing after a long quiet spell (slower, dimmer, like
  standby but lighter), a calmer palette in the evening or in quiet hours,
  and a brief "perk up" when "Hey Jarvis" was heard.
- **Why.** Every consumer assistant that feels alive does this; Jarvis's idle
  is a steady "breathe" pattern today (`faces-spec.js`, `state_rules.idle`).
- **Rules.** Keep the idle frame-rate savings (`state_fps`, line 564) and
  "reduced motion" (both apps honour it: `JarvisTheme.kt:351`,
  `prefers-reduced-motion` in `faces.html`). No new state, no attention
  grabbing: idle must never look like "approval" (the knock-at-the-door ring).

### 5. Games and small talk, in a temporary chat (S)

- **What.** "Let's play 20 questions", trivia, riddles, "would you rather",
  a word of the day, a short story together. A **Play** button (or "let's
  play ...") that starts a *temporary chat*.
- **Why it must be temporary.** Automatic learning saves facts from the
  owner's own typed or said words (`jarvis_auto_learn.py:583`). I searched
  it and `jarvis_sensitive.py` for anything about games or pretending and
  found nothing, so "I'm a pirate captain" in a game is the owner's own words
  and could become a fact. A temporary chat already recalls nothing, learns
  nothing and keeps nothing (`JARVIS-API.md` §4, `temporary-chat.patch`) -
  exactly right for play, with no new mechanism.
- **Rules.** Trivia from an 8B model can be wrong: the rules block still makes
  it say what is a guess. No game may involve Jarvis pretending to be a real
  person or company, or asking the owner for personal details. Offers such as
  "want a riddle?" go through `jarvis_backoff.may_offer` (line 313) with a
  declared kind, or better, are never offered at all.

### 6. "Quiz me on this note" with smart review times (M)

- **What.** The owner picks a note (Obsidian); the local model writes 5-10
  question-and-answer cards; the owner keeps, edits or drops each. Jarvis then
  asks them again on a schedule that spaces reviews out as you remember them,
  using **FSRS** (Free Spaced Repetition Scheduler, the algorithm in Anki).
  Quiz by voice or in either app; "how did I do this week?".
- **Source.** [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs),
  **MIT** (LICENSE read). Obsidian plugins already do the card-writing with
  Ollama ([obsidian-quiz-generator](https://github.com/ECuiDev/obsidian-quiz-generator))
  - proof it works with local models, not code to take.
- **Plugs into.** Reading the note: `jarvis_notes.plan`/`run`
  (`jarvis_notes.py:266`, `536`). Review times: a new kind on the one
  scheduler (`jarvis_schedule.register_kind`, line 313), `silent` with its
  own "N cards due" line in Coming up - not a timer of its own
  (`ARCHITECTURE.md` §12). Cards in their own small database, NOT memory.
- **Rules.** A note is outside text (notes search marks the turn), so card
  writing happens in a marked turn; that only matters if it writes back to
  the vault, which then needs the note-write card. Quiz answers are not facts
  about the owner: run the quiz as a temporary chat so nothing is learned.
  Repeating reviews: the owner's decision on repeats applies - a plain
  reminder repeat has no card (2026-09-26), but this kind reads notes, so by
  the rule in §12 it asks once, like the briefing.

### 7. Summarise an audio file the owner gives (M)

- **What.** Drop a file (MP3/WAV/M4A of a podcast, lecture or voice memo) on
  the Jarvis bar, or share it from the phone. The PC cuts it into speech
  pieces with Silero (already there), turns them into text with Parakeet
  (already there), then the everyday model writes a summary in slices.
- **Plugs into.** `jarvis_speech._speech_span` (line 380) and `_transcribe`
  (line 329). The live 30-second cap (`max_seconds`, line 944) is for talking
  and stays; a file goes through a new background job, not the voice route.
  Decoding MP3/M4A needs a decoder (e.g. ffmpeg) - a new dependency.
- **Speed.** A 30-minute podcast in "a handful of seconds" on a 24 GB GPU
  *(search summary)*; on the processor it will be minutes. Unmeasured here.
- **Rules.** Speech-to-text runs on the PC, never on the phone (standing
  rule). The recording is not the owner speaking live, so its words are
  outside text: they mark the conversation and are never learned as facts.
  Parakeet v2 is English only; v3 adds 25 European languages (CC-BY-4.0,
  *search summary*) - see item 9.

### 8. "Translate this" (S, then M)

- **Now (S).** The everyday model (Qwen3 8B) translates common languages
  reasonably. A fast path: "translate ... into Spanish" goes to the model with
  a fixed translation instruction, no tools. No download.
- **Later (M), a dedicated model** if quality is not enough:

| Model | Licence | Size | Notes |
|---|---|---|---|
| [Hy-MT2 1.8B](https://github.com/Tencent-Hunyuan/Hy-MT2) (Tencent, May 2026) | **Apache-2.0** (its `LICENSE.txt`, read) | 1.8B; GGUF for llama.cpp | 33 languages. "Surpasses ... Microsoft" *(claim)*. Its smallest 1.25-bit file needs a llama.cpp change not yet merged (README) - use the normal GGUF |
| TranslateGemma 4B/12B (Google, Jan 2026) | Gemma Terms of Use (not open source; fine for personal use) | 4B fits 2080S beside nothing else, or CPU | 55 languages; in Ollama's library as `translategemma:4b` *(search summary)* |
| MADLAD-400 3B (Google) | Apache-2.0 *(search summary)* | 3B | 419 languages; needs a separate runtime (CTranslate2) |
| NLLB-200 (Meta) | **CC-BY-NC-4.0 - non-commercial only**; allowed under rule 5 | 600M-3.3B | 200 languages; older |

- **Rules.** Local only, so private text can be translated. Pasted text is
  outside text, as today. A dedicated model is an install, which is already
  an approval card (`/api/models/install`).

### 9. Language practice (M)

- **What.** "Let's practise French": a short conversation at the owner's
  level, one gentle correction per turn, and new words sent to the item 6
  review list (the owner's own choice per word).
- **Honest limits.** Typed practice works with the everyday model. **Spoken
  practice does not work yet:** Parakeet v2 hears English only, and Kokoro in
  sherpa-onnx speaks only English and Chinese *(search summary; the original
  Kokoro has more languages)*. Spoken practice needs Parakeet v3 (25 European
  languages, CC-BY-4.0) - a change the voice report advised against for
  English speed, so it would be a second model loaded only for practice.
- **Rules.** Temporary chat (nothing learned). The voice check still runs
  first.

### 10. Code helper for a beginner (M)

- **What.** A "Help me understand this" mode: paste an error, or point at a
  file in a folder the owner chose, and Jarvis explains in plain words
  (item 2's style), says what to try, and says which file and line. It never
  edits by itself.
- **Plugs into.** `file_read` exists (`jarvis_agent.py:199`, capped at
  200 KB, line 175); `ast-grep` is the chosen way to pull out only the
  relevant code (`ARCHITECTURE.md` §11, measured 54,490 -> 1,088 bytes).
  Changing code, if ever wanted: a diff on a card, applied in a git worktree
  (also §11) - the four steps of §3.
- **Model.** The everyday model to start. On the 12 GB card,
  `qwen2.5-coder:14b` (~9 GB, **Apache-2.0**; note its 3B size is under a
  research-only licence) *(search summary)*; Qwen 3.5 9B (Apache-2.0) is
  already the 12 GB card's planned model and may be good enough - test first.
- **No build at all:** VS Code's Continue extension can use the local Ollama
  directly. It sends usage data by default; set `allowAnonymousTelemetry`
  to false *(search summary)*.
- **Rules.** Code is files: rule 1, local only. Never offered to a cloud lane.

### 11. Make and edit pictures (L, 2060)

- **What.** "Draw a birthday card with a cat", "make this photo black and
  white", "remove the background". Saved to a Jarvis folder on the PC and
  shown in the app.
- **Options** (none measured on Turing cards):

| Model | Licence | Memory | Notes |
|---|---|---|---|
| [FLUX.2 klein 4B](https://github.com/black-forest-labs/flux2) (Jan 2026) | **Apache-2.0** (README) | "fits in ~8GB VRAM" *(claim)*; ~13 GB at full size *(search summary)* | Makes AND edits pictures. Its 9B sibling is non-commercial |
| Z-Image-Turbo 6B (Alibaba) | **Apache-2.0** (repo LICENSE read) | 14-16 GB full; ~6-8 GB squeezed *(search summary)* | Photo-real; good at text in images |
| SDXL-Turbo (Stability) | Stability non-commercial / community licence - fine under rule 5 | smaller | Older, 512 px |

- **Engine.** [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp)
  (**MIT**) runs FLUX.2 klein 4B and Z-Image from single files, with a
  "move parts to the processor" option (`docs/flux2.md`, read). Ollama's own
  picture-making exists but was macOS-only *(search summary)*.
- **Plugs into.** A sixth switch in `jarvis_second_card.FEATURES`
  (`jarvis_second_card.py:214`), turned on by one card like the others; run
  on demand and stopped when idle, like the F5 "better voice".
- **Honest problems.** (1) The 12 GB card is planned for the 14B
  long-conversation model (10.4 GiB, `MODEL-TOPOLOGY.md`): both cannot be
  loaded at once, so making a picture means unloading it first, and the app
  should say so. (2) Turing cards have no fast bf16 maths; these models are
  usually shipped in bf16 and may need 16-bit or squeezed files. Unchecked.
- **Rules.** Editing the owner's photo stays local (rule 1). Refuse editing
  a real person's face into something else or into someone else - "private
  details about other people", and it is how fakes are made. Saving to
  Jarvis's own folder is not writing the owner's files; overwriting an
  existing photo would be a card.

### 12. Lip-sync mouth shapes (M, only with a mouth)

- [HeadTTS](https://github.com/met4citizen/HeadTTS) (**MIT**) gives Kokoro
  timing for each sound and "visemes" (mouth shapes). It uses a different
  Kokoro build from the one Jarvis runs through sherpa-onnx, runs in
  JavaScript, is English only, and by default loads voices from
  huggingface.co - which would have to be a local copy.
- [Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync)
  (**MIT**) works from any recorded voice and the text, but is built for
  recordings; real-time use is an open request (its issue #135).
- Jarvis's call to Kokoro gets only sound back (`jarvis_speech.py:1815`).
  **Worth it only if the owner wants a face with a mouth**; item 3 gives most
  of the effect for the current abstract faces.

### 13. Music and sound effects (M-L)

- [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) (**MIT**, LICENSE
  read): songs with lyrics in 50+ languages, "less than 4GB of VRAM"
  *(claim)*; its own table suggests 8-12 GB for the full set-up. Has a
  Windows package. Its XL version needs 12 GB with tricks, 20 GB without.
- Stable Audio 3.0 Small / Small-SFX (May 2026, 459M): Stability Community
  licence (free under $1M revenue); made for laptops and phones *(search
  summary)*.
- **Value** is mostly fun: a calm loop for a focus session, a custom alarm
  sound, a birthday song. Output saved locally. Low priority.

---

## Not for Jarvis, and why

- **Guessing the owner's mood from their voice** (e.g. emotion2vec, MIT).
  It infers a private, health-like state that the owner never said - memory
  and behaviour must come from the owner's own words. The research on
  "personality guessing" was already left out (`RESEARCH-2026-09-24.md` §3).
  The face already reacts to how loud the owner is, which is enough.
- **Downloading from YouTube or podcast sites** (yt-dlp and similar). A new
  way out of the PC (`ARCHITECTURE.md` §4) and against YouTube's terms.
  Item 7 takes files the owner gives it.
- **Photo-real talking heads or face swaps** (a moving human face made from a
  photo). Too close to impersonation; a face made from a real person's photo
  is a fake of that person.
- **A persona file the model rewrites** (like Meta Muse's `Soul.md`,
  `COMPETITORS-MUSE-2026-09-25.md`). The model would be changing its own
  instructions with no review.
- **Companion-style emotional bonding, streaks and guilt nudges**
  ("you'll lose your 30-day streak!"). Nudges are offers; Jarvis's offers are
  few and backed off (`jarvis_backoff.py`), and making someone feel bad to
  keep them engaged is not a helper's job.
- **Cloud picture, music or translation services** (Midjourney, Suno, Google
  Translate). Rule 1; local options exist.
- **Voices copied from other people for games** (a celebrity, a friend). Voice
  cards already refuse the owner's own voice (`jarvis_voices.py`); someone
  else's is impersonation.
- **Flashcards or quizzes made from emails or web pages automatically.**
  Outside text choosing what Jarvis does; the owner picks the note.

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

- Persona drift: https://github.com/likenneth/persona_drift ; https://arxiv.org/abs/2402.10962 (search summary)
- FSRS: https://github.com/open-spaced-repetition/py-fsrs (LICENSE: MIT) ; https://github.com/ECuiDev/obsidian-quiz-generator
- Translation: https://github.com/Tencent-Hunyuan/Hy-MT2 (LICENSE.txt: Apache-2.0) ; https://blog.google/innovation-and-ai/technology/developers-tools/translategemma/ ; https://arxiv.org/pdf/2601.09012 ; https://huggingface.co/facebook/nllb-200-distilled-600M ; https://github.com/google-research/google-research/tree/master/madlad_400
- Speech: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 (search summary) ; https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html (search summary)
- Pictures: https://github.com/black-forest-labs/flux2 (README) ; https://github.com/leejet/stable-diffusion.cpp (LICENSE: MIT; docs/flux2.md) ; https://github.com/Tongyi-MAI/Z-Image (LICENSE: Apache-2.0) ; https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md ; https://ollama.com/blog/image-generation (search summary)
- Music: https://github.com/ace-step/ACE-Step-1.5 (README, LICENSE: MIT) ; https://stability.ai/news-updates/meet-stable-audio-3-the-model-family-built-for-artistic-experimentation-with-open-weight-models (search summary) ; https://github.com/facebookresearch/audiocraft (LICENSE_weights: CC-BY-NC-4.0)
- Lip-sync: https://github.com/met4citizen/HeadTTS (README, LICENSE: MIT) ; https://github.com/DanielSWolf/rhubarb-lip-sync (README, LICENSE: MIT) ; https://github.com/DanielSWolf/rhubarb-lip-sync/issues/135
- Code helper: https://qwenlm.github.io/blog/qwen2.5-coder-family/ (search summary) ; https://www.noze.it/en/insights/continue-ollama-on-prem/ (search summary)
- Emotion from voice (not used): https://huggingface.co/emotion2vec/emotion2vec_plus_large (search summary)
