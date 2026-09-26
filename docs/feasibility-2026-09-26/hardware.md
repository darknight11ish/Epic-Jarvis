# Feasibility audit - Hardware and speed reviewer (2026-09-26)

Read-only. Nothing in the repo was changed. Every code claim below was
checked in the file named, unless it says "not checked" or "estimate".

## The numbers every row is measured against

Plain words first: a **token** is a word or part of a word. The **context
window** is how many tokens the model can hold at once: the rules, the tool
descriptions, the saved facts, the conversation so far, and room for its
answer. **VRAM** is the graphics card's own memory.

1. **Today's real window is about 8,000 tokens, not 16,384.** The Modelfile
   still asks for 16,384 (`backend/jarvis-primary.Modelfile:90`). But
   `docs/HARDWARE-PROFILES.md` section 3 item 1 calculates that this does not
   fit on the card once llama.cpp's empty gap is counted. When it does not
   fit, about 4 of its 37 layers run on the processor, which is much slower.
   I ran Jarvis's own planner (`backend/jarvis_profiles.py`, `plan()` and
   `room()`) for one 8 GB RTX 2080 Super with the monitor plugged in. It
   gives **5.82 GiB of room**, and its "Smartest answers" setup is **"qwen3:8b,
   8K ... on the RTX 2080 SUPER"**. `backend/test_tool_text.py:4-5` says the
   same: "about 8,000 tokens of real room". None of this has been measured
   on the owner's PC.
2. **Where those 8,192 tokens go on a spoken turn today.** These counts use
   Jarvis's own cautious counter, `estimate_tokens`, at 3 characters a
   token:
   - 1,024 held back for the answer (Modelfile `:115`).
   - 300 for the rules (`_TEMPLATE_TOKENS`, `backend/jarvis_agent.py:2016`).
     The rules really measure 204 (`LANE_SYSTEM`; I measured it).
   - **Up to 3,067 for tool descriptions.** I measured this over all 23
     tools with `browser_control` left out. `browser_control` is never
     offered without the second card (`jarvis_agent.py:2829-2834`).
   - 139 for the "spoken answer" note (`SPOKEN_NOTE`; I measured it).
   - About 113 for the Warm manner line (R4-CHAR's figure, not re-measured).
   - About 100 for the five saved facts (`docs/MODEL-TOPOLOGY.md:318`).

   **That leaves about 3,450 tokens for the conversation.** One tool result
   can be up to 8,000 characters (`_MAX_TOOL_CONTENT_CHARS`,
   `jarvis_agent.py:2126`), which is 2,000 to 2,700 tokens. So one big
   result can take most of what is left.
3. **Speed anchors**, from `docs/MODEL-TOPOLOGY.md`. All are calculated or
   second-hand, not measured here:
   - **Re-reading text** (called "prefill"): about 1,900 tokens a second.
     That is 6,000 tokens in 3.1 s (`:257`). Re-reading a full 8K window
     takes about 4 s.
   - **Writing the answer**: about 60 tokens a second (`:472`,
     second-hand).
   - **Swapping one model out for another on the card**: 6.2 s when the
     file is already in the PC's memory, 9.6 s when it has to come off the
     disk (`:256-258`).
4. **The 8 GB card has no spare room at all.** It has 5.82 GiB of room, and
   the 8B model at 8K needs 5.57 GiB (HARDWARE-PROFILES 8.2). Any new model
   on this card means unloading chat, which costs the 6-10 s swap in item 3.
5. **The 12 GB card is not roomy either.** The planned long-conversation
   lane is `LONG_BIG = ("qwen3:8b", 32768, 7.69)`
   (`backend/jarvis_second_card.py`, just above `VISION_MODEL`). With no
   monitor and two programs using the card, it has 9.74 GiB of room
   (HARDWARE-PROFILES 8.1), so about 2 GiB is left beside that lane. The
   existing F5 "better voice" asks for 3,072 MB (`jarvis_voices.py:151`) and
   refuses to start when there is less (`:1107`). By this arithmetic, F5 and
   the long lane already cannot run at the same time.
6. **The processor is shared too.** Speech-to-text, the Kokoro and ZipVoice
   voices, the wake word, the meaning search and the new re-ranker all run
   on the 3900X processor. The big model (colibri) also runs on it. Jarvis
   sets **no thread limit or lower priority** for colibri: the settings it
   passes to colibri include no thread setting (`jarvis_big_model.py`,
   checked with a grep for `COLI_*`). **How much RAM the PC has is not
   written in any doc I searched**, so RAM costs below are per model, not
   checked against the PC.
7. **Only one request at a time.** The second card's Ollama is set to one
   request at a time (`OLLAMA_NUM_PARALLEL=1`, `jarvis_second_card.py:782`).
   ENG §8 says Ollama forces this for Qwen 3.5 too. So any background model
   job waits behind chat, and chat waits behind it. For the main Ollama I
   did not check this setting.

Verdicts: **build** (hardware supports it, or it saves hardware);
**build later** (it waits for the second card or for a measurement);
**don't build** (the cost is too high for what it gives);
**no objection** (no meaningful hardware cost).
"[2nd card]" marks ideas that must wait until the RTX 2060 is installed and
measured.

## 1. One row per idea

| id | verdict | reason | cost numbers |
|---|---|---|---|
| I01 | build | A model without tool support fails on every turn today. Checking once stops the wasted turn. | One `/api/show` call per model switch, a few milliseconds. 0 VRAM. |
| I02 | build | Free second lock behind rule 1. | 0 time, 0 VRAM. |
| I03 | build, **first** | It is the only way to measure the cost of I06, I07, I104-I107 and I129. Without it, every "saves tokens" claim stays a guess. | Numbers only. 0 cost. |
| I04 | build (measure first) | Runs only on a broken tool call, which is rare. | One extra request. If it changes the start of the prompt (for example, drops the tools), the whole window is re-read: about 4 s at 8K. Keep the start of the prompt identical so it can be reused. Not checked: whether Ollama accepts a form (`format`) and a tool list in the same request. |
| I05 | build | It is only a test, but it is the measuring stick for I06, I09 and I07. | Runs on the owner's PC only. It keeps the card busy for minutes; run it when Jarvis is idle. |
| I06 | build, **top hardware item** | Tool descriptions are the biggest single fixed cost in the 8K window. | Up to 3,067 estimated tokens today, which is **37% of 8K**. A core of about 6 tools is about 1,000, so it frees about 2,000. **Trap:** the tool list sits at the start of the prompt. Changing it mid-conversation stops Ollama reusing what it already read, which costs about 4 s at 8K each time. Keep the core list fixed, in a fixed order, and measure with I03. |
| I07 | build (after I06 and I03) | The owner chose it. It costs no VRAM, but it adds programs and tool text. | Each server is one more program: Python or Node, roughly 50-150 MB of RAM each (estimate). Its tools must be reachable only through I06's "more tools", with the same limit of 300 per tool (`test_tool_text.py`, `PER_TOOL`). Start each server when needed and stop it when idle. ENG notes community advice that about 14B is the smallest reliable size for this; test with I05 before trusting the 8B. |
| I08 | build later [2nd card] | Today's `qwen3:8b` has none of the extra layers this needs (ENG §7). An open Ollama bug can make answers about 10 times slower. | The extra layers also take VRAM, and the 8 GB card has none spare. Measure on the 2060 only, with I03's timings. |
| I09 | build (a test, not a switch) | **The cheapest way to get more context on today's card.** | Each model is a download of about 2.5-6 GB. The IQ4_XS version of the 8B needs about 0.4-0.6 GiB less VRAM. That is enough to go from 8K to 12K on the 2080 Super, perhaps 16K; see section 3 item 5 for the arithmetic. Qwen 3.5 needs much less memory per token of conversation (`jarvis_profiles.py`, `TEST_LATER`). Answer quality is unmeasured, so switch nothing until I05 and I32 pass. |
| I10 | build later [2nd card] | Ends the 6-10 s swap between the "long conversations" model and the "pictures" model. | `qwen3.5:9b` is a download of about 6.6 GB (VV §4, search summary). Its fit at 32K plus a picture must be measured on the 2060. |
| I11 | build later [2nd card] | Needs a model that can see pictures. On the 2080 Super it would unload chat. | Several seconds of model time per step. It can only run on the 2060 beside the long lane if the same model does both (I10). |
| I12 | build | Needed before the 2060 goes in: heat and power for both cards. | Checked: the desktop reads only the first card (`commands.rs:2617`), and the backend's list of card readings has no heat or power (`rebuilt/jarvis_compute.py:139`). The processor cost of reading them every few seconds is negligible. The field name `clocks_event_reasons` is not checked; older drivers call it `clocks_throttle_reasons`. |
| I13 | build (the 2080 Super part now; the 2060 part [2nd card]) | A lower power limit makes the card cooler and quieter at little speed cost (claimed). | A few minutes of model runs at 3 power levels. The limit resets at every restart. Jarvis is never made administrator. |
| I14 | build | Works today, with no graphics card. | Reading text from a picture (OCR) on the processor: about 0.3-1.5 s per screenshot (estimate, not measured). The model files are tens of MB. **Limit the text:** a full screen of text can be 500-2,000 tokens, more than the flat 1,000 a picture is counted at (`estimate_tokens`, `jarvis_agent.py:1995`). Cut it at about 1,500 tokens and say it was cut. The phone already caps a photo at 1.5 MB (`ChatPicture.kt:62`). |
| I15 | build | The owner chose it. Running it costs the same as today; training it is the cost. | Training needs a graphics card once, and the 8 GB card cannot hold it beside chat, so chat is off while it trains (length not checked). After that, it uses the same front end as today on the processor and the phone. Change in phone battery: unmeasured; measure an hour of hands-free listening before and after. |
| I16 | build | Processor only, 0 VRAM. | About 100M parameters. Claimed 2.3-2.5 times faster than real time on an x86 processor (VV §3), not measured on the 3900X. It shares cores with speech-to-text. Time it with `say_timings()`. |
| I17 | build later [2nd card] | Might not be needed: measure Kokoro on the 3900X first. | First sentence 1.3-1.6 s on the processor (measured in the dev container, not the owner's PC; ARCHITECTURE §11). On the graphics card: roughly 0.3 GiB of model plus about 0.33 GiB of GPU start-up memory for one more program (estimate). |
| I18 | no objection (behind an off switch) | The known bug (empty or made-up text) is the blocker, not the hardware. | The decoding mode it needs is slower than today's. Parakeet runs at 0.09 times real time (VV), so about +0.1-0.3 s per clip (estimate). |
| I19 | no objection | Small processor model, but the PC's microphone is always on. | CED-Tiny is 5.5M parameters. Roughly 1-2% of one core, all the time (estimate). 0 VRAM. |
| I20 | build later [2nd card] | 0.9B on the graphics card. On the 2080 Super it would unload chat for every document photo. | A 6-10 s swap each way on today's card. Only worth it if I10's model is weak at documents. |
| I21 | no objection | Tiny. | Milliseconds per clip. It must run after the owner's voice check. |
| I22 | build | It saves phone battery and data by not recording and sending clips started by a fan or TV. | Silero: under 1 ms per 30 ms of sound (claim), about 3% of one core while the microphone is open, next to the heavier wake-word model already running. Each false 30-second clip avoided is about 1 MB of audio not sent (16 kHz, 16-bit). |
| I23 | build later (only if the owner's numbers show a need) | Processor only, tiny. | 1-15M parameters. Needs its own measured limits. |
| I24 | build later [2nd card] | These voices and the 32K lane cannot sit on the 2060 together (see numbers item 5). | CosyVoice 0.5B plus PyTorch is roughly 1.5-2.5 GiB (estimate), plus one more program's start-up memory. That is more than the ~2 GiB left. Qwen3-TTS needs FlashAttention 2, which Turing cards cannot run (VV §11). Turing also has no fast bf16, a number format these models are made in. |
| I25 | don't build | Research says no reliable local detector exists, so it would cost processor time for nothing. | Not applicable. |
| I26 | no objection | No model. | 0. |
| I27 | build later [2nd card] | Needs a model that can see pictures. | The same as I11. |
| I28 | no objection | A setting. | 0. |
| I29 | build later [2nd card], low priority | FLUX.2 klein 4B "fits in ~8GB" (claim), but only ~2 GiB is free beside the long lane. | Every picture unloads the long lane (a 6-10 s reload) and takes about a minute to make (unmeasured). Turing has no fast bf16. It cannot be done on the 2080 Super beside chat. |
| I30 | don't build | Too much memory for a "mostly fun" feature. | ACE-Step's own table says 8-12 GB for the full setup (R2-PER §13), the whole 2060. Revisit only with a bigger card. |
| I31 | build (in progress) - change one default | Processor only, about 80 MB. | Scoring 20 facts takes roughly 20-80 ms on the 3900X (estimate). **But** the worktree waits up to **1.5 s** (`RERANK_BUDGET_S`, `rebuilt/jarvis_memory.py:504` in `agent-a4d69393e5376ccb0`) and is **on by default** (`:505`). MEM said "off until the self-test on your PC shows it helps". Suggest about 0.3 s on spoken turns. |
| I32 | build | A test. | Card time on the PC for minutes; run it when idle. |
| I33 | no objection | Database only. | 0. |
| I34 | no objection | Database only. | 0. |
| I35 | build later (after I31 is measured) | One model call per saved fact, on the main card, queued with chat. | About 1-3 s of model time per fact (estimate). Doing it for all existing facts means N calls; run it only when Jarvis is idle. |
| I36 | no objection | Arithmetic only. | 0. |
| I37 | build | The owner chose it. Cheap if the model only compares a few pairs. | Find candidate pairs with the meaning search on the processor first, then limit model calls (for example 50 a night, about 2-5 min of card time, estimate). Run it before standby starts, never during it. |
| I38 | build later (the owner said wait) | Small hardware cost. | Meaning-search entries on the processor, about 10 ms per turn (estimate). The index grows with the history. |
| I39 | build | No model, instant. | Everything's `es.exe` answers in under a second. Limit the results to about 20 names, to save tokens. |
| I40 | build | The owner chose it. Reading in slices is what keeps it inside 8K. | Turning a big PDF into text takes seconds to minutes on the processor. **Keep a slice at about 1,500 tokens or less.** |
| I41 | build later (after I40, I31) | The processor cost is fine; the folders are the owner's call. | First indexing: roughly 10-20 ms of processor time per chunk (estimate), so a few minutes per 10,000 chunks, run in the background. About 1.5 KB of disk per chunk (a 384-number entry). |
| I42 | build | Checking a quote is text matching on the processor. It replaces ContextCite, which is too heavy for 8 GB (R3-KNOW). | Near 0. The source list is shown to the owner, not sent to the model. |
| I43 | no objection | No model. | 0. |
| I44 | build later [2nd card or big model] | The wiki is written only by the second card's model or the big model (ARCHITECTURE, wiki builder). | Minutes per run on that lane. |
| I45 | no objection | A separate DuckDB process with a row limit. | Small RAM and processor cost. Limit the rows sent back so they fit the token budget. |
| I46 | build | Transcribing uses parts Jarvis already has. The summary must be done in slices. | At Parakeet's 0.09 times real time (VV), a 1-hour file takes about 5-6 min of processor time. A 1-hour transcript is about 13,000 tokens, more than the 8K window, so summarise part by part (several model calls, 1-3 min). Run it in the background and pause it during a voice turn. |
| I47 | no objection | Reads a small file. | 0. |
| I48 | no objection | Copies the browser's history file per question (tens of MB). | Small. |
| I49 | no objection | A little network traffic. | A few hundred KB a day. |
| I50 | no objection | Desktop drawing only. | A vault with thousands of pages could be heavy to draw. Load it bit by bit. |
| I51 | no objection | | 0. |
| I52 | no objection | | 0. |
| I53 | no objection | One network write. | 0. |
| I54 | no objection | | 0. |
| I55 | no objection | | 0. |
| I56 | no objection | Processor OCR (I14). | About 1-2 s per page (estimate). |
| I57 | no objection | One model call per quiz draft. | A few seconds. |
| I58 | build (the everyday-model version) | Needs no download. | A dedicated model later (Hy-MT2 1.8B) would unload chat on the 2080 Super, or run slowly on the processor. Wait for the second card before trying it. |
| I59 | no objection (typed) | Spoken practice would need Parakeet v3 loaded as well. | Roughly 1-2 GB more RAM for v3 (estimate), so spoken practice is later. |
| I60 | no objection, with limits | `file_read` allows 200,000 bytes (`jarvis_agent.py:176`), far more than the window. Results are cut to 8,000 characters (`:2126`). | Use `ast-grep` to pull out only the relevant code, as R2-PER says. A 14B coder model is [2nd card]. |
| I61 | no objection | One model call to write the plan. | 0 extra. |
| I62 | no objection | Checked in code. | 0. |
| I63 | no objection | No model. | 0. |
| I64 | build later [2nd card or big model] (stage 3) | Re-planning in the background competes with chat on the 8 GB card. | Minutes of card time. |
| I65 | no objection | | 0. |
| I66 | no objection | A folder watcher uses almost no processor time; checking the calendar is small. | 0. |
| I67 | no objection | | Check the page no more than hourly. Small data. |
| I68 | build | One connection that waits, instead of signing in every 5 minutes. Less work for the PC. | On the PC only; nothing on the phone. The waiting command must be renewed before the server drops it (about every 29 min is common; Gmail's limit not checked). |
| I69 | no objection | | 0. |
| I70 | no objection | | Check GitHub about once a minute, and only while a run is going. |
| I71 | build later [2nd card] | See "the processor is shared" above: a night job on colibri could take every core. Also the standby clash R3-ROUT found. | The 2060's board power is about 185 W while it works (MODEL-TOPOLOGY). Give colibri a thread limit or low priority first. |
| I72 | no objection, with limits | Search snippets eat the ~3,450 free tokens fast. | Use I105's short form, or slices. 30 s to 2 min per comparison (estimate). |
| I73 | build (as the owner queued it) | Reading notifications is cheap on the phone. Sending each one to the PC is the battery and data cost. | Keep notifications on the phone and send them to the PC only when the owner asks. That is the cheapest for battery and data, and it matches "only when asked". |
| I74 | build later [2nd card] | A week of chat is far more than 8K tokens. | The 32K lane holds it in a few passes; on the 8 GB card it takes 5-15 model calls (estimate). |
| I75 | build | One call to Home Assistant. | 0. |
| I76 | no objection | | 0. |
| I77 | no objection, with one limit | Do not paste the whole device list into every prompt. | 50 devices at about 8 tokens each is 400 tokens. Give it through `home_read` results only. |
| I78 | no objection | One small WebSocket client. | 0. |
| I79 | no objection | It reuses the voice check that already runs. | 0. |
| I80 | no objection | | 0. |
| I81 | no objection | | 0. |
| I82 | no objection, with one limit | Frigate must not run on the Jarvis PC's cards; there is no room. | 0 on Jarvis. Where Frigate would run is not checked. |
| I83 | no objection (showing it); the model half is [2nd card] | Showing a still costs nothing. Letting the model look needs the picture model. | 0 / a picture turn on the 2060. |
| I84 | build later (after I12) | The graphics-card readings leave out the processor and the rest of the PC. | `power.draw` covers the cards only; the 3900X is rated 105 W and is not counted. Say "graphics cards only", or use a Home Assistant smart plug. |
| I85 | no objection | | 0. |
| I86 | no objection | | 0. |
| I87 | no objection | | 0. |
| I88 | build later | Months of Home Assistant history is far too much for an 8K window. | Look for patterns in code on the processor, not with the model. [2nd card] if the model is needed. |
| I89 | no objection | | One small packet from the phone. |
| I90 | no objection | Saves power overnight. | The first answer after waking pays the slow cold load: about 9.6 s. Whether the wake timer works without an administrator prompt is not checked. |
| I91 | no objection | | 0. |
| I92 | no objection | | Listing updates takes seconds of processor time and a little data. |
| I93 | build | Phone only. Rings even with the PC off. | 0. |
| I94 | no objection | | 0. |
| I95 | build (run overnight) | It decides I104-I108. | 276 attack cases (6 templates times 46 goals in `backend/agentdojo_injections.json`, counted) plus 180 ordinary ones, each 1-3 model rounds. Roughly 30-75 min of card time per setting (estimate), hours for 5 settings. Chat is slow or unavailable while it runs. |
| I96 | no objection | | Seconds of processor time to encrypt. |
| I97 | build | Cheap, read-only checks. | The database check reads each whole database: seconds. Do it in the preflight, not at every start. |
| I98 | no objection | Ollama is a separate program, so the model stays loaded. | Restarting reloads the voice models on the processor: seconds. |
| I99 | no objection | | Small files. |
| I100 | no objection, with one limit | Small crash dumps only. A full dump of Ollama can include the memory-mapped model file (GBs). | Small dumps are MBs each. Keep 10 at most. |
| I101 | no objection | | Milliseconds. |
| I102 | no objection | | Negligible on either device. |
| I103 | no objection | | Negligible. |
| I104 | build | Pure code. | 0 model cost. |
| I105 | build later (if I95 shows a gain) | **It also saves context:** a 300-character form replaces an email that can run to thousands of tokens. | One extra model call per email or web read: about 1-3 s (estimate). |
| I106 | don't build | It re-runs the whole model before every card that follows outside text. | Doubles the time of those turns: about +3-8 s (estimate). Too slow for voice on the 8 GB card. Revisit only if I95 shows nothing else works. |
| I107 | build later (measure with I95 and I03) | Marking every word of outside text grows it. | It can roughly double the tokens that outside text takes up (estimate; not tested with Qwen's tokenizer), in the tightest part of the window. |
| I108 | build later (after I95) | Warning only, on the processor. | deberta-v3-base, about 184M parameters: roughly 50-200 ms per 512-token chunk and 200-700 MB of RAM (estimate). Prompt Guard 2 22M is much lighter, but its licence is not checked. |
| I109 | no objection | | 0. |
| I110 | no objection | | 0. |
| I111 | no objection | Updates take longer. | Disk space for a second copy of the backend, plus preflight model checks (minutes). |
| I112 | no objection | | 0. |
| I113 | no objection | | 0. |
| I114 | no objection | | 0. |
| I115 | no objection | | 0. |
| I116 | no objection | | 0. |
| I117 | no objection | No model call. | Refresh only while the page is on screen. |
| I118 | no objection | | 0. |
| I119 | build | The setup checklist should include "Measure" (does the model fit on the card?). | 0 extra. |
| I120 | no objection | Big files use I40's slices. | 0. |
| I121 | no objection, with one limit | A PDF is MBs of phone data. The PC refuses any request over 4 MiB (`MAX_BODY`, `backend/token-store.patch:5`). | Documents need their own upload route, not `/api/chat`. |
| I122 | no objection | | 0. |
| I123 | no objection | | 0. |
| I124 | no objection, with one limit | Use Android's own ticking countdown, not an update every second. | Battery: near 0 if done that way. On the PC, update the toast every 5-10 s. |
| I125 | no objection | | 0. |
| I126 | no objection | Update the widget when something happens, not on a timer. | Near 0. |
| I127 | no objection | | 0. |
| I128 | no objection | | 0. |
| I129 | build | Fix `_TEMPLATE_TOKENS` (`jarvis_agent.py:2016`) in the same change. | About +270 tokens, which is **3.3% of the real 8K**, not "1.6% of 16K". The rules come first and never change, so Ollama can reuse them from the second turn on: about 0 time cost. |
| I130 | no objection | About 90 tokens. Keep only if I133 shows a gain. | 1% of 8K. |
| I131 | build | Answers without the model, so each one saves a model turn. | Saves about 1-3 s each time. |
| I132 | no objection | Text check. | 0. |
| I133 | build (run when idle) | A test. | Minutes to an hour of card time. |
| I134 | build | One `/api/show` call. | 0. |
| I135 | no objection | | 0. |
| I136 | no objection | One style sentence. | About 30-60 tokens. |
| I137 | no objection | | Tens of tokens. |
| I138 | no objection, with the cap | The 900-character cap is about 300 tokens (R4-GROW), 3.7% of 8K. | Count it in the budget, the way the manner line already is (`jarvis_agent.py:3520-3522`). |
| I139 | no objection | | 0. |
| I140 | no objection | | 0. |
| I141 | no objection | | 0. |
| I142 | no objection | Ordinary saved facts. | 0 extra. |
| I143 | no objection | Inside I138's cap. | 0 extra. |
| I144 | no objection | It saves tokens and time. | Negative cost. |
| I145 | no objection | | 0. |
| I146 | no objection | | 0. |
| I147 | no objection | Splitting the sound into two bands in the app. | Almost no processor time or battery. |
| I148 | no objection | Keep the lower frame rate when idle (the report does). | Small. |
| I149 | no objection | Only if a face with a mouth exists. | Small. |
| I150 | no objection | Guidance only. | 0. |
| I151 | no objection | A check in code; that turn offers no tools, so its prompt is smaller. | Negative cost. |
| I152 | no objection | | 0. |
| I153 | no objection | | About 50 tokens. |
| I154 | no objection | | 0. |
| I155 | build later [2nd card] | A 14B judge on the 2060 means unloading the planned 32K lane. | Hours of card time per run. |

**Must wait for the second card:** I08, I10, I11, I17, I20, I24, I27, I29,
I44, I64 (stage 3), I71, I74, I155; also the model part of I58, I60 and I83,
and the 2060 part of I13. (I30 would too, but I recommend not building it.)

## 2. Objections for the other reviewers

1. **To Fit and Upkeep, on I06 (the short tool list).** I want the core
   list fixed, and in the same order every turn. The reason: each change to
   the tool list costs about 4 s of re-reading at 8K, because the tools sit
   at the start of the prompt. That is my understanding of Qwen's prompt
   layout; I did not check Ollama's copy of it. Fit may prefer a list that
   changes with each topic. Answer with I03's "reused" numbers before
   choosing. **Open question for Fit:** could "more tools" hand back its
   extra descriptions as a tool result, so the start of the prompt never
   changes? It depends on whether Ollama's Qwen reader accepts a call to a
   tool that was not in `tools`. MODEL-TOPOLOGY.md:302 says the Qwen 3
   reader ignores the tool list (`_ = tools`), but that was read, not run.
2. **To Security, on I106 (the masked re-run) and I105 (the reader pass).**
   I say don't build I106 on the 8 GB card: it adds 3-8 s to every card
   that follows outside text. If Security ranks it as the strongest
   defence, the answer is I95's numbers. I105 is the one I would pick
   first, because it also frees context.
3. **To Security and Rules, on I73.** My hardware choice is to keep
   notifications on the phone and send them to the PC only when the owner
   asks. Fit may object that "tell me when" matching lives on the PC
   (`jarvis_tellme.py`), so on-phone matching would copy that logic. The
   compromise: send only what matches the owner's chosen apps, and only
   when a "tell me when" rule or a question needs it.
4. **To Devil's advocate, on I09.** I rank the IQ4_XS test near the top,
   because it may give 12K-16K on today's card for no new hardware. The
   fair objection is a quality loss. The answer is I05 and I32 before any
   switch, and going back is a model switch.
5. **To Overwhelm, on background jobs.** I35, I37, I46, I74, I95, I105 and
   I133 all want the same card, and it takes one request at a time. I
   propose **one written rule, not a setting**: background model jobs run
   only when Jarvis has been idle for a few minutes, never during a voice
   turn, and never in standby hours (R3-ROUT's Q2). Overwhelm should
   confirm that needs no new switch.
6. **To Upkeep, on processor models.** I14, I15, I16, I19, I21, I22, I23,
   I31 and I108 each add a model file on the processor (tens to hundreds of
   MB of RAM each), a download and a pinned version. The PC's RAM is not
   written down anywhere I looked. Before adding more than two or three,
   ask the owner for it or read it in the preflight.
7. **To Fit, on I14 and I40 limits.** I want OCR text and document slices
   limited to about 1,500 tokens. Fit may want the whole text. On an 8K
   window with about 3,450 tokens free, the whole text pushes out the
   conversation without telling anyone.
8. **To everyone: no new model on the 2080 Super's card.** Room 5.82 GiB,
   chat needs 5.57. Any idea that says "or the 2080S by swapping" (I20,
   I58's dedicated model, VV table row 7) means chat goes silent for
   6-10 s both ways. Treat those as second-card ideas.
9. **To Fit and Devil's advocate, on the 2060's plans.** Even the 12 GB card
   holds only one big thing at a time beside the 32K lane: I24's voices,
   I29's pictures, I30's music, I155's 14B judge, and the existing F5 voice
   all need the space the lane uses. Somebody has to choose what the 2060
   is *for*, or every feature there becomes "unload the long lane first".
10. **To Rules, on I71 and colibri.** With no thread limit, a night job on
    the big model can slow the wake word and speech-to-text to a crawl if
    the owner speaks at night. Low priority for colibri, or "night jobs
    only when standby is off", should come first.
11. **To Devil's advocate, on I17.** I agree it may not be needed: measure
    Kokoro on the 3900X first. The only figure we have (1.3-1.6 s) comes
    from the dev container.
12. **To Fit, on I84.** "What did Jarvis cost today?" from the graphics
    card readings under-counts: it leaves out the processor. Either word it
    as "the graphics cards used ..." or use a smart plug through Home
    Assistant.

## 3. Wrong or out of date in the research reports

1. **ENG §6 says "~16% of the 16K window".** The real window on today's
   card is 8K. Evidence: `jarvis_profiles.plan()` gives "qwen3:8b, 8K" for
   the 2080 Super, and `test_tool_text.py:4-5` says "about 8,000 tokens of
   real room". Tool text is up to about 37% of it, not 16%. ENG's counts
   also differ from mine. It says 23 tools, 10,859 characters, about 2,700
   tokens. I measured 10,905 characters of tool descriptions, 3,612 by
   Jarvis's own counter. But `browser_control` is never offered without the
   second card (`jarvis_agent.py:2829-2834`), so today at most 22 are sent:
   9,268 characters, 3,067 counted. ENG's line numbers for `offered_tools`
   (2765-2784) are now 2817-2835.
2. **R4-CHAR (the token budget) says the character block costs "1.6% of
   16K".** Against the real 8K it is 3.3%. Its own source,
   `test_tool_text.py:4-5`, gives the 8,000 figure.
3. **R2-PER §11 says "The 12 GB card is planned for the 14B long-conversation
   model (10.4 GiB)".** That is out of date. The plan is `qwen3:8b` at
   32,768, 7.69 GiB (`LONG_BIG` in `jarvis_second_card.py`;
   `MODEL-TOPOLOGY.md:361-368`). The conclusion still holds, though:
   pictures must still unload the lane, because about 2 GiB is left, not
   the 8 GB FLUX claims to need.
4. **R4-WELL §8 says "the 14B model once the 12 GB card is in".** Also out
   of date for the same reason. A 14B appears only if the owner picks the
   two-card "Smartest answers" setup, which puts `qwen3:14b` at 16K on the
   2060 as *chat* (I ran `jarvis_profiles.plan()`). No 14B lane is planned.
5. **ENG §8, IQ4_XS "saves ~0.6 GiB".** That is calculated from the nominal
   bits per weight. Real files keep some layers larger, so the saving may be
   nearer 0.4 GiB. I could not check this, because huggingface.co is
   blocked. The benefit still holds. At 0.4 GiB saved: 5.72 GiB of room
   (5.82 less the planner's 0.10 margin) minus about 4.27 GiB of weights
   minus 0.30 GiB working memory leaves about 1.15 GiB. At 78,336 bytes a
   token, that is about 15,700 tokens, so 12K fits and 16K is borderline.
   At a 0.6 GiB saving, 16K fits.
6. **MEM idea 1 says the re-ranker "should be off until the self-test on your
   PC shows it helps".** The build in worktree `agent-a4d69393e5376ccb0` is
   **on by default** (`rebuilt/jarvis_memory.py:505`), with a 1.5 s wait
   (`:504`). MEM's own status line (`MEMORY-RESEARCH-2026-09-26.md:9`) says
   its real gain is still unmeasured. This is a mismatch for Fit and Rules
   to settle. My part is the 1.5 s, which is too long for a spoken turn.
7. **Several reports treat 16,384 as Jarvis's real context** (ENG §6, R4-CHAR,
   and the comment at `jarvis_second_card.py:171-172`). MODEL-TOPOLOGY.md's
   own header (lines 13-42 and 192-198) already says that budget is out of
   date and that nothing has been measured. Any feature sized as "small in a
   16K window" should be re-checked against 8K.
8. **R3-ROUT §8 cites `jarvis_second_card.py:1263`** for the standby check;
   it is at `:1264`. This is trivial, and its finding (the big model has no
   standby flag) is correct: `jarvis_big_model.py`'s `sleep()` docstring
   says colibri "only ever starts for a job".
9. **VV §11's "F5 wants 3 GB" is right, and it understates the problem.**
   By HARDWARE-PROFILES 8.1 and 8.2, the existing F5 voice cannot run
   beside the 32K lane on the 2060 today: it needs 7.36 + 3.0 = 10.36 GiB
   against 9.74 of room. So "better voice" and "longer conversations" are
   already either/or. The owner should hear that before the card arrives.
   This is calculated, not measured.
