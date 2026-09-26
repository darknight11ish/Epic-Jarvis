# Cutting-edge audit, 2026-09-26: voice, hearing and seeing

One slice of the owner's "what can we add or refine" request: hearing, speaking,
the voice check, pictures and sounds.

**Limits.** Repo file:line references were checked on 2026-09-26. huggingface.co,
ollama.com, arxiv.org, kyutai.org, livekit.com, k2-fsa.github.io and wikipedia.org
are blocked here, so those pages were read only through search summaries,
marked *(search summary)*. What a project says about itself is marked *(claim)*.
**Nothing was run or measured for this report.** Numbers from earlier tests come
from `backend/README.md`. Not repeated here: the queued voice work (interrupting,
"One moment.", Kokoro on the graphics card), "Show me where to click"
(`COMPETITORS-*-2026-09-25.md`) and the "say these 3 words" check
(`RESEARCH-2026-09-24.md` §5).

---

## In six lines, for the owner

1. **Turning your speech into words is not the slow part.** Jarvis's
   speech-to-text model (Parakeet) is still one of the best fast ones in 2026.
   Leave it alone. The slow part is making Jarvis's voice, and that is already
   queued.
2. **The cheapest real upgrade is a better "Hey Jarvis" detector.** A new free
   tool (livekit-wakeword) trains a detector that plugs into the same parts
   Jarvis already uses. Its makers say it gives 100 times fewer false alarms.
   That claim was measured on a different phrase, so it needs testing on "Hey
   Jarvis".
3. **A new small voice, Pocket TTS, runs on the processor and can copy a
   voice.** It now works inside the voice library Jarvis already uses, so it is
   worth a timed test against ZipVoice and Kokoro.
4. **Pictures:** when the 12 GB card is in, one model (Qwen 3.5 9B) could handle
   both long conversations and pictures. Today's plan needs two models that
   take turns. Before the card arrives, Jarvis could still read the *text* in
   a screenshot, on the processor.
5. **Can Jarvis tell a recording of you from the real you? Still no.** In 2026,
   ready-made fake-voice detectors still guess close to chance on real-world
   fakes. The honest wording stays. The "say these words" check is still the
   real fix.
6. **"Talk and listen at the same time" models (like Moshi) are still not for
   Jarvis.** They need about 16 GB of graphics memory. They would also speak
   before Jarvis can check the answer, which gets around approval cards and
   the rule that sensitive answers stay on screen.

---

## Ranked table

"Card" means which part of the PC runs it: CPU (the processor), 2080S (the
8 GB card in the PC now) or 2060 (the 12 GB card that is coming). Size: S = a
day or so, M = a few days, L = a week or more.

| # | Idea | Why it matters | Size | Card | Rule risk |
|---|---|---|---|---|---|
| 1 | Read a screenshot's text on the processor (OCR, optical character recognition) | Screenshots are useless today (text-only model). The text alone answers many questions | S–M | CPU | Low. The text counts as outside text (taints the turn) |
| 2 | Better "Hey Jarvis" detector (livekit-wakeword) | Fewer false wake-ups (claim: 100×) and more of yours heard. The same model runs on the phone and the PC | M | trained on 2080S once; runs on CPU/phone | Low. Same licence situation as today |
| 3 | Pocket TTS as a third custom-voice engine, on the processor | Voice copying on the processor, audio starts in a fraction of a second (claim) | M | CPU | Low. Its consent terms match Jarvis's existing voice card |
| 4 | Second card: Qwen 3.5 9B for both "Longer conversations" and "Pictures" | One model instead of two that swap. Newer and better at pictures than qwen2.5vl:7b | S | 2060 | None new |
| 5 | Name hints for speech-to-text (Home Assistant device names, contact names) | "Turn off the Hue Ambiance lamp" is heard right | S–M | CPU | None. But a known bug: measure first |
| 6 | "Tell me when the smoke alarm goes off": recognising household sounds | Doorbell, alarm, baby, glass breaking. Fits "tell me when …" | M | CPU | **Medium.** It means listening all the time: needs a card, never keeps audio |
| 7 | Reading documents from photos (PaddleOCR-VL, a small document model) | Letters, bills, forms, tables, turned into clean text | M | 2060 (or 2080S by swapping) | Low. The content is outside text |
| 8 | Noise clean-up before speech-to-text (GTCRN) | Fewer wrong words from a far or noisy microphone | S | CPU | None, if it runs **after** the owner check |
| 9 | A neural speech detector in the apps, replacing the loudness trigger | Fewer recordings started by a fan or a TV; cleaner interrupting | M | CPU / phone | None (not speech-to-text) |
| 10 | A stronger voice-ID model (ReDimNet) | Only if your own measured numbers show the voice check letting others in | M | CPU | None |
| 11 | A better voice on the second card (CosyVoice 3, Qwen3-TTS, Chatterbox) | Emotion, better copies | L | 2060 | Competes with the long-conversation lane for memory |
| 12 | A fake-voice detector used only to make things *stricter* | Research only; see "Recording vs real voice" | M | CPU/GPU | Must never loosen anything |

---

## Details

### 1. Read a screenshot's text on the processor

- **What.** Alt+Shift+S attaches a screenshot. Today's model cannot see
  pictures, so the quickbar offers to send the words without it
  (`jarvis-desktop/src/main.js:1015-1036`, `vision.rs:191`). Instead, turn
  the screenshot's text into words locally and send that text with the
  question.
- **Options.** (a) **RapidOCR**: PaddleOCR's models run on ONNX Runtime (a
  library for running AI models), `pip install rapidocr onnxruntime`,
  Apache-2.0, English and Chinese by default ([repo](https://github.com/RapidAI/RapidOCR)).
  (b) **Windows' own OCR** (`Windows.Media.Ocr`): free, built in, no download.
  One search summary says it needs a "packaged" app; I have not checked this
  for Tauri. The newer Windows AI text reader needs an NPU (a special AI chip),
  and the 3900X PC has none (*search summary*, [Microsoft docs](https://learn.microsoft.com/en-us/windows/ai/apis/text-recognition)).
- **Where it plugs in.** Backend: where `jarvis_agent.newest_turn_has_image()`
  is checked (`backend/jarvis_agent.py:2902`, `:2931`). When no picture lane
  answers, turn the image part into a text part labelled "text read from your
  screenshot". Desktop: the notice in `main.js:1027` gets a third choice,
  "send the text I can read in it".
- **Rules.** The screenshot's text is **outside text**: it can hold an email or
  a web page. Mark the turn like a pasted message (tainted), so note-writing
  and searches ask first (CLAUDE.md, 2026-09-24). It stays on the PC (rule 1).
  The phone's photo picker (`net/ChatPicture.kt`) can use the same backend
  path, so both apps get it.
- **Value:** high, and it works now, without the second card. **Risk:** OCR
  loses layout. Tell the owner "Jarvis read the text only".

### 2. A better "Hey Jarvis" detector

- **What.** [livekit-wakeword](https://github.com/livekit/livekit-wakeword)
  (Apache-2.0 code, v0.2) keeps openWakeWord's front end: the same
  `melspectrogram.onnx` and `embedding_model.onnx`, and the same 16 × 96
  numbers Jarvis already computes (`backend/jarvis_wakeword.py:17-23`,
  `voice/OrtWakeModels.kt:65`). It replaces only the last small model with a
  "conv-attention" one, which pays attention to the order of the sounds.
  Their table (*claim*, on "hey livekit", 25 h of test audio): false alarms
  per hour 8.50 → 0.08, words heard 68.6% → 86.1%. They say the exported file
  is "fully compatible" with openWakeWord.
- **How.** Train "hey jarvis" once on the owner's PC. It needs a graphics card
  and synthetic voices made with Piper, the same source as `jarvis_wakebank.py`.
  Ship the new last model to `jarvis_wakeword.PHRASE_MODELS`
  (`jarvis_wakeword.py:137`) and to the phone's `OrtWakeModels.WAKE_FILE`
  (`OrtWakeModels.kt:88`). Check the input shape first, then re-run the
  project's own 110-clip test (`backend/README.md`, "What was measured here").
- **Watch for.** (a) The owner's personal verifier only runs when the first
  model scores ≥ 0.1 (`jarvis_wakeword.py` docstring). A new model changes when
  that happens, so re-measure both together. (b) Licence: the two front-end
  files are the same ones Jarvis already ships under CC BY-NC-SA. LiveKit's
  issue #89 asks the same question and has no answer yet. Nothing changes for
  a non-commercial build (rule 5). (c) The "stop" model
  (`jarvis_stopword.py`) sits on the same front end and could be retrained the
  same way later.
- **Value:** the wake word is the one voice part ARCHITECTURE §10 still lists
  as "not measured on real speech". Fewer false wake-ups also means fewer
  clips sent for the owner check.

### 3. Pocket TTS on the processor

- **What.** Kyutai's [Pocket TTS](https://github.com/kyutai-labs/pocket-tts):
  100M parameters, "~200ms to get the first audio chunk", "~6x real-time on a
  CPU of MacBook Air M4", 2.3–2.5× real time on a cloud x86 processor, audio
  comes out in pieces as it is made, and it copies a voice from a WAV file
  (*claims*, README). English plus five European languages.
- **Licence.** Code MIT. Weights CC-BY-4.0 *(search summary)*. The
  voice-copying weights sit behind a light, automatic sign-up where you promise
  "no voice cloning without the explicit, lawful consent" of the speaker. That
  is what Jarvis's `custom_voice` card already asks for
  (`backend/jarvis_voices.py:32-39`).
- **Why it is easy here.** sherpa-onnx (the voice library Jarvis already uses)
  has run Pocket TTS "for streaming voice cloning on CPU" since 1.12.24
  (its CHANGELOG), and its Python API has `OfflineTtsPocketModelConfig`
  (checked in `offline-tts-model-config.cc`). Jarvis is tested on 1.13.8. So
  this is a third engine beside ZipVoice in `jarvis_voices.py` (the ZipVoice
  section starts at `:775`; the engine choice is in `speak()`, `:1417`), with
  no PyTorch and no graphics card.
- **Risks.** An open sherpa-onnx issue (#3180, Feb 2026, no reply) says its
  Pocket voice "sounds different" from the original. Listen before
  choosing. The ~200 ms figure is from an Apple laptop, not the 3900X. Measure
  with `say_timings()` (`jarvis_speech.py:1922`), the same way ZipVoice was
  measured.

### 4. The second card: one model for long talks and pictures

- Today `jarvis_second_card.py:196-209` plans `qwen3:8b` at 32K for "Longer
  conversations" and a *separate* `qwen2.5vl:7b` for "Pictures". When both do
  not fit, a picture "unloads" the other (`:1693-1695`). `RESEARCH-2026-09-24.md`
  already recommends Qwen 3.5 9B (Apache-2.0) for the second card, and says it
  reads pictures.
- New since then *(search summaries)*: `qwen3.5:9b` is a 6.6 GB download on
  Ollama, takes text and pictures, and "outperforms Qwen3-VL" (the Qwen team's
  claim). Qwen3-VL 8B (Apache-2.0, Oct 2025, OCR in 32 languages, screen
  understanding) is the fallback, about 6.1 GB. Gemma 4 (Apache-2.0, April
  2026) also reads pictures in every size, and Ollama's own tool-call reader
  already knows it (`MODEL-TOPOLOGY.md`).
- **Suggestion.** When the card is in and measured, try `qwen3.5:9b` as
  `LONG_*` **and** `VISION_MODEL`. If it fits at 32K with a picture, the swap
  mode disappears. Nothing to do before the card is installed (CLAUDE.md).
  Update `pictureNoticeWords` (`main.js:1030`), which names qwen2.5vl.
- **Risk.** Picture tokens cost context. Newer Qwen versions (3.6, 3.8) came
  out in bigger sizes only, as far as the search shows; I did not check further.

### 5. Name hints for speech-to-text

- sherpa-onnx added "hotwords" (name hints) for NeMo models like Parakeet in
  PR #3077 (merged 2026-02-05). Jarvis could pass Home Assistant device names,
  contact names and voice names per clip (`_build_stt_engine`,
  `jarvis_speech.py:297-318`).
- **But:** issue #3267 (open since 2026-03-07) says the decoding mode that
  hotwords need "hallucinates or returns empty text ~20% of the time" with
  Parakeet. Build it behind a setting that is off by default, and measure with
  the 110-clip set first. If it fails, leave it.

### 6. Household sounds: "tell me when the smoke alarm goes off"

- **What.** A small "audio tagging" model names sounds from the AudioSet list
  (doorbell, smoke alarm, dog, baby crying, glass breaking). sherpa-onnx runs
  the CED models (5.5M–86M parameters; CED-Tiny is "faster than MobileNets on a
  single x86 CPU", *claim*; code GPL-3.0, weights licence not checked)
  ([CED](https://github.com/RicherMans/CED)). Google's YAMNet (Apache-2.0) is
  the cleaner licence if that matters.
- **Where.** A new kind on the one scheduler, like "tell me when …"
  (`jarvis_tellme.py`, `jarvis_schedule.register_kind`). A match only notifies,
  in the owner's words ("The smoke alarm went off"), exactly as
  `jarvis_tellme.py` does for email and devices.
- **Rules.** This makes Jarvis **listen to the room all the time**. Turning it
  on is a `change_own_config` card, the same as the wake word
  (`jarvis_speech.py:621`); turning it off is immediate. Sound in, a label
  out: no audio kept, never transcribed, never sent anywhere, PC microphone
  only. Say plainly that it is **not a safety device**. A real smoke alarm
  must not depend on it.
- **Value:** medium. A doorbell or washing machine is usually easier through
  Home Assistant, which `tellme` already watches.

### 7. Reading documents from photos

- [PaddleOCR-VL](https://github.com/PaddlePaddle/PaddleOCR) 1.5/1.6: 0.9B
  parameters, Apache-2.0. It claims 94.5% on OmniDocBench v1.5, "surpassing
  GPT-4o" (*claim*, Baidu). llama.cpp can run it *(search summary)*, and an
  Ollama request is open. It turns a photo of a letter, bill or table into
  clean text, which Qwen 3.5 can then answer questions about.
- Only worth adding if Qwen 3.5 9B turns out weak at documents: measure
  item 4 first. The content is outside text (taint), like item 1.

### 8. Noise clean-up (GTCRN)

- sherpa-onnx has a tiny speech-enhancement model (`OfflineSpeechDenoiser`,
  GTCRN). Put it before `_transcribe` (`jarvis_speech.py:329`), **after**
  the owner check (`:1633`). Cleaning before the check would change the voice
  print's numbers, and every limit in `MODEL_BARS`
  (`backend/rebuilt/jarvis_voice.py:736`) was measured on unprocessed audio.
  Test it on the 110-clip set; keep it only if the word error goes down.

### 9. A neural speech detector in the apps

- The desktop starts and ends a recording on loudness (`voice.rs:797-817`,
  a 900 ms hangover). The PC's Silero check only runs after the clip is sent.
  A neural detector in the app would stop a fan or a TV from starting a
  recording, and helps interrupting-by-talking.
- Options: **Silero VAD** (MIT, the one the PC already has, <1 ms per 30 ms
  chunk, *claim*) or **TEN VAD** (306 KB, Android builds). TEN claims Silero
  "suffers from a delay of several hundred milliseconds" at the end of speech
  (*claim*). Both are in sherpa-onnx (`TenVadModelConfig`, checked). TEN's
  licence is Apache-2.0 **plus conditions**: no use that "competes with
  Agora's offerings". Fine for a personal app, but not plain Apache.
- Not speech-to-text, so the phone rule is kept. Both apps must change
  together (`tools/check_parity.py`).

### 10. A stronger voice-ID model

- Jarvis already pairs CAM++ with TitaNet-Large (`backend/rebuilt/jarvis_voice.py:736-750`).
  [ReDimNet](https://github.com/IDRnD/redimnet) (MIT code, 1–15M parameters,
  top VoxCeleb results, ONNX export, a successor "ReDimNet2" from July 2026)
  is the one to try **only if** the owner's real "someone else" numbers are
  poor. Any new model needs its own measured limits (`GENERIC_BARS` exists for
  exactly this). Size M, value unknown until measured.

### 11. A better voice on the 12 GB card

| Model | Licence | Notes (all *claims*) |
|---|---|---|
| [Fun-CosyVoice 3](https://github.com/FunAudioLLM/CosyVoice) 0.5B | Apache-2.0 | Streams, "latency as low as 150ms", emotion and speed instructions, voice copying |
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) 0.6B/1.7B | Apache-2.0 | "as low as 97ms", copies from 3 s, instructions for tone. FlashAttention 2 is "recommended/required", and that **does not run on Turing** (`MODEL-TOPOLOGY.md`) |
| [Chatterbox](https://github.com/resemble-ai/chatterbox) Turbo 350M / Nano 110M | MIT | Laugh tags, an "exaggeration" dial, a watermark in every clip. Nano: "3x realtime on 8 cores" |
| [VoxCPM2](https://github.com/OpenBMB/VoxCPM) 2B | Apache-2.0 | ~8 GB of graphics memory: too big beside the long-conversation lane |
| F5-TTS (in Jarvis now) | code MIT, **weights CC-BY-NC** | Non-commercial is fine under rule 5; already in `THIRD-PARTY-NOTICES.txt` |

- **Catch.** The 2060 is already planned for the 7.69 GiB conversation lane,
  and F5 wants 3 GB (`jarvis_voices.py:151`). A second GPU voice fights for
  the same memory. Turing also has no fast bf16 (a number format many new
  models expect), so some of these may be slower or not work in fp16. Any
  choice replaces F5, not adds to it. Wait until the card is measured.

### 12. Recording vs real voice: the question the owner asked

- **Answer: no local model is good enough to trust in 2026.** Deepfake-Eval-2024
  (a CVPR 2026 workshop paper) found that open detectors lose about 48% AUC on
  real-world fake audio, many near "random guessing". Even after extra
  training, the best reached 86% accuracy *(search summary of the paper)*.
  This agrees with this project's own test (`RESEARCH-2026-09-24.md` §5: two
  detectors called about two thirds of real people fake).
- Newest candidates: NII's **AntiDeepfake** models (wav2vec2 / XLS-R, 300M–2B,
  **CC BY-NC-SA**, "research and educational purposes"), and XLS-R + SLS
  (EER 7.46% on In-the-Wild, *claim*). None of them catches a **replay** (a
  real recording of you played back). That needs microphone-array or airflow
  sensors, which the PC does not have.
- **If ever tried:** only as a way to make things *stricter* (a flagged
  hands-free turn is treated as "Only trust the talk button"), never to accept
  anything. Test it on Jarvis's own ZipVoice and F5 copies first: Jarvis can
  make its own test fakes. Keep the current wording. The "say these 3 words"
  check (RESEARCH §5) is still the real fix, and it is the owner's call.

---

## Checked, and Jarvis is already current

- **End-of-turn (Smart Turn).** v3.2 is still the latest on the project page
  (BSD-2, 8 MB, 23 languages). Jarvis ships v3.2 (`jarvis_turn.py`). Nothing
  to do.
- **Speech-to-text.** The top of the Open ASR leaderboard is now bigger models
  (Canary-Qwen 2.5B, about 5.6% word error; Granite Speech 4.1 2B, about
  5.3%, *search summaries*). They are GPU-sized for a small gain. Parakeet TDT
  0.6B v2 already got 109 of 110 test sentences right, in 0.09× real time
  (`backend/README.md`). Parakeet **v3** only adds European languages. Qwen3-ASR
  and Moonshine v2 are now in sherpa-onnx too. Moonshine was tried before and
  misheard "Jarvis".
- **Streaming speech-to-text** (words appear while you talk): NVIDIA's
  Nemotron streaming 0.6B (June 2026, OpenMDW-1.1, 80–1120 ms chunks) runs in
  sherpa-onnx on the processor. **Not worth it:** it would turn speech into
  words *before* the owner check. That breaks the one order in
  `jarvis_speech.py` that "must never move" (`:32-37`), for ~0.3 s saved.
- **VAD** (the speech detector): Silero is still the standard. See item 9 for
  the one change worth considering.

---

## Not for Jarvis, and why

- **Talk-and-listen-at-once models.** NVIDIA PersonaPlex-7B (built on Moshi,
  NVIDIA Open Model licence) needs about 16 GB+ *(search summary)*. Moshi is
  already rejected (ARCHITECTURE §11). LFM2.5-Audio-1.5B (Liquid, "lfm1.0"
  licence) is small enough, but it is a *second brain*: it would speak before
  Jarvis can check the answer. That gets around three things: the
  sensitive-answers-stay-on-screen rule (`jarvis_speech.py:1461-1500`), the
  owner check before any words (the model hears everything), and approval
  cards (these models are weak at tool calls). A 2026 paper, "A
  frontend-backend architecture for tool calls in full-duplex speech models",
  splits the job the way Jarvis would need (the talking model hands every
  action to a checker). Revisit only if an open model does that well on 12 GB.
- **Omni models as Jarvis's ears** (Gemma 4 E2B/E4B, Qwen2.5-Omni, Qwen3-Omni).
  They would hear speech with no owner check first, and Qwen3-Omni-30B is too
  big. The newest, Qwen3.8-Omni-Flash (18 Sep 2026), is **cloud-only, no
  weights**. That breaks rule 1.
- **Phone speech-to-text** of any kind (Moonshine, Parakeet on Android, Android
  dictation). Standing rule.
- **End-of-turn models that read the words** (like LiveKit's text turn
  detector). They need the words before the owner check on the PC, or
  speech-to-text on the phone. Smart Turn works on sound only, which is why it
  was chosen.
- **Music recognition like Shazam.** It needs an online database: AcoustID or
  Shazam gets a fingerprint of the room's sound. That is a new way out of the
  PC (ARCHITECTURE §4), for little value. Matching only against the owner's
  own music files would be local, but is not worth building.
- **Always-on camera, face recognition, "who is at my desk".** Faces of other
  people are "private details about other people" (CLAUDE.md). A camera that
  watches is a standing sensor with no single approval. Focus sessions already
  set the pattern: watch the screen, keep counts only.
- **Porcupine** wake word (already rejected: online licence check).
  **Supertonic 3** (repo archived 2026-09-09, no voice copying, OpenRAIL-M weights).

### If a camera is ever used

PC only, one picture per button press (the shape of Alt+Shift+S), a picture
turn that stays local (ARCHITECTURE §10) and counts as outside text. Never
continuous, never stored unless saved, never used to identify a person.

---

## Sources

Repo files are cited where used above. Web (read directly unless marked):
- sherpa-onnx [releases](https://github.com/k2-fsa/sherpa-onnx/releases) (v1.13.8, 2026-09-10) · [CHANGELOG](https://github.com/k2-fsa/sherpa-onnx/blob/master/CHANGELOG.md) · [TTS config source](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/python/csrc/offline-tts-model-config.cc) · issues [#3573](https://github.com/k2-fsa/sherpa-onnx/issues/3573), [#3267](https://github.com/k2-fsa/sherpa-onnx/issues/3267), [#3180](https://github.com/k2-fsa/sherpa-onnx/issues/3180) · PR [#3077](https://github.com/k2-fsa/sherpa-onnx/pull/3077)
- [Smart Turn](https://github.com/pipecat-ai/smart-turn) · Nemotron 3.5 streaming ([search summary](https://www.marktechpost.com/2026/06/06/nvidia-releases-nemotron-3-5-asr-a-600m-parameter-cache-aware-streaming-model-transcribing-40-language-locales-in-real-time/)) · leaderboard figures (search summaries: [Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks), [CodeSOTA](https://www.codesota.com/speech/stt-leaderboard))
- [livekit-wakeword](https://github.com/livekit/livekit-wakeword) and [issue #89](https://github.com/livekit/livekit-wakeword/issues/89) · [openWakeWord](https://github.com/dscripka/openWakeWord)
- [Pocket TTS](https://github.com/kyutai-labs/pocket-tts), weights licence ([search summary](https://huggingface.co/kyutai/pocket-tts)) · [Supertonic](https://github.com/supertone-inc/supertonic) · [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) · [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) · [Chatterbox](https://github.com/resemble-ai/chatterbox) · [VoxCPM](https://github.com/OpenBMB/VoxCPM)
- [PersonaPlex](https://github.com/NVIDIA/personaplex) · [liquid-audio](https://github.com/Liquid4All/liquid-audio) (search summary) · Qwen3.8-Omni-Flash ([search summary](https://www.marktechpost.com/2026/09/18/alibaba-qwen-releases-qwen3-8-omni-flash/)) · [full-duplex tool-calls paper](https://arxiv.org/abs/2609.19334) (title only)
- [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) · qwen3.5:9b ([search summary](https://ollama.com/library/qwen3.5:9b)) · [Qwen 3.5 small models](https://artificialanalysis.ai/articles/qwen3-5-small-models) (search summary) · Gemma 4 ([search summary](https://ollama.com/library/gemma4:e4b)) · [llama.cpp multimodal list](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- PaddleOCR-VL 1.5 ([search summary](https://ernie.baidu.com/blog/posts/paddleocr-vl-1.5/)) · [RapidOCR](https://github.com/RapidAI/RapidOCR) · [Windows text recognition](https://learn.microsoft.com/en-us/windows/ai/apis/text-recognition)
- [Silero VAD](https://github.com/snakers4/silero-vad) · [TEN VAD](https://github.com/TEN-framework/ten-vad) (LICENSE read) · [CED](https://github.com/RicherMans/CED) · [ReDimNet](https://github.com/IDRnD/redimnet)
- Deepfake-Eval-2024 ([search summary](https://openaccess.thecvf.com/content/CVPR2026W/APAI/papers/Chandra_Deepfake-Eval-2024_A_Multi-Modal_In-the-Wild_Benchmark_of_Deepfakes_Circulated_in_2024_CVPRW_2026_paper.pdf)) · [AntiDeepfake](https://github.com/nii-yamagishilab/AntiDeepfake) · [XLS-R + SLS](https://openreview.net/forum?id=acJMIXJg2u)
