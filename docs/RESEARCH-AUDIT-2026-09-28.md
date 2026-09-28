# Research audit: Jarvis next to its competitors and to GitHub, 2026-09-28

The owner asked for a full research audit covering four things:

- every feature Jarvis has, including work still on other sessions' branches;
- how those features compare with commercial assistants and open-source
  projects on GitHub;
- what could be added or improved on the phone, the desktop, or the whole
  program;
- ways to make it faster or lighter.

A second request, added the same day, asked for a look at Jarvis's **Brain**
(the screen, and the memory behind it) against projects that already have
something like it finished. That is section 8.

Everything here is research. Nothing in the apps or the backend was changed.

## How far to trust this

- **Jarvis's side was checked in the code.** Every "Jarvis does / does not
  do X" below was read in the repository, at `main` (commit `9cdb056`) or on
  the four unmerged branches listed in section 9. The claims the
  recommendations rest on were checked a second time by the main session,
  line by line. Those are marked **(checked)**.
- **Other open-source projects: mostly their real code.** GitHub's web
  pages and API were blocked, but downloading a project (`git clone`)
  worked. So for open-source projects the helpers read the actual code.
  Each claim says whether it came from code, a README, or only a search
  result.
- **Commercial assistants: search summaries only.** Every page at OpenAI,
  Google, Apple and the others was blocked. Treat each fact about them as
  "a news summary says so".
- **Nothing was run on the owner's PC or phone.** The timings in section 7
  come from a test machine with 4 processor cores and no graphics card. The
  direction and rough size will hold on the owner's PC; the exact numbers
  will not.
- **Seven helper agents did the digging, and two more did the Brain
  audit.** Their full notes are in [`research-audit-2026-09-28/`](research-audit-2026-09-28/).
  Those notes are terse and technical; this page is the plain-words version.

---

## 0. The short answer

1. **Jarvis is still ahead on trust, and the gap has widened.** In the last
   two months the big assistants added:
   - usage caps and fees (Siri AI has daily limits; Gmail and Docs "Live"
     are paid);
   - memory you cannot fully see (ChatGPT's new memory has no list you can
     audit, and deleting a chat keeps what it learned);
   - always-on screen reading (Siri's onscreen awareness cannot be blocked);
   - a keystroke-and-click timeline (ChatGPT for Mac).

   Jarvis has none of these problems. Its main weakness is still everyday
   reach. The competitors now watch things for you ("tell me when the
   price drops", "tell me when CI finishes") and brief you each morning in
   your own words.
2. **Six things are worth fixing soon, and each is small** (section 1).
   The most important:
   - a security update for the desktop app's framework;
   - checking whether the main model actually fits on the 8 GB card;
   - switching off data reporting to Microsoft in one of the speech
     libraries;
   - three speed fixes that cut 0.3 to 3 seconds of waiting.
3. **The best new ideas are small and fit the rules** (section 3):
   - "tell me when a search shows something new";
   - GitHub watches;
   - "where did I put…";
   - "remind me next time I talk about X";
   - a notification when a watch breaks;
   - "ring my phone";
   - media buttons for the PC on the phone.
4. **GitHub has a lot to borrow, mostly as ideas.** OpenClaw and Hermes
   (both MIT licence, so their code may be copied) have finished versions
   of things Jarvis lacks:
   - shortening big tool results instead of dropping them;
   - "remind me next time";
   - grouping failed watches into one notice;
   - catching "I've done it" when nothing was done.

   Handy (MIT) has a finished version of talk-to-type (typing what you say
   into the program in front), which the owner already decided to build.
5. **Speed: the Python code is not the slow part.** A warm turn spends only
   4-15 ms in Jarvis's own code before the model starts (measured). The
   waiting comes from three places:
   - the model re-reading the conversation after its short-term memory was
     thrown away;
   - voice running on only 2 of the 12 processor cores;
   - on the development side, CI (the GitHub test run) taking 22 minutes a
     push, where it could take about 7.

---

## 1. Fix soon: problems found, each checked in the code

Ranked by how much they matter. None needs the second graphics card.

### 1.1 Security update for the desktop app's framework (Tauri 2.11.5 → 2.11.6)

- **What:** Tauri is the framework the desktop app is built on. A
  published security advisory (GHSA-w28w-mhc8-qvjv) says that in versions
  before 2.11.6, one window of an app could read data queued for another
  window.
- **Why Jarvis is affected:** Jarvis streams chat answers this way. See
  `ipc::Channel` in `commands.rs:1708` and `hud_proxy.rs:215`. It also has
  several windows. **(checked: `Cargo.lock` has tauri 2.11.5)**
- **Fix:** in `jarvis-desktop/src-tauri`, run
  `cargo update -p tauri --precise 2.11.6`. According to the helper,
  2.11.6 needs no newer Rust. This was not re-checked.
- **Effort:** a few minutes, plus the usual CI run.

### 1.2 Does the main model fit on the 8 GB card?

- **What:** `backend/jarvis-primary.Modelfile` plans for 16,384 tokens of
  conversation, with a memory ceiling of "~6.90 GiB" (lines 6, 41, 90).
  **(checked)** The project's own `docs/HARDWARE-PROFILES.md:44` works out
  that this is "about 0.6 GB over". If so, about 4 of the model's 37
  layers run on the processor, which is much slower. Nobody has looked on
  the PC.
- **What to do:**
  1. Press **Measure** on the Hardware screen, or read the model log, to
     see how many layers are on the card.
  2. If fewer than 37 of 37, choose one of three fixes:
     - a smaller conversation length (12,288);
     - a slightly smaller build of the same model (Qwen3 8B IQ4_XS, which
       saves about 0.6 GB);
     - the existing preset setting `LLAMA_ARG_FIT_TARGET=768`.
  3. Then correct the Modelfile's out-of-date notes. Its check step (lines
     59-78) still says to look for flash attention being "off". Ollama now
     sets it to "auto", and "off" now fails to load instead of quietly
     spilling.
- **Why it matters:** if the model spills, this is the biggest speed
  improvement available.

### 1.3 Switch off ONNX Runtime's data reporting

- **What:** ONNX Runtime is the library that runs the speech models on the
  PC. Its own privacy page says its data reporting (telemetry) is "ON by
  default in the official builds", and on Windows the data "may be
  periodically sent to Microsoft servers".
- **Evidence:** Jarvis never switches it off. A search of the whole
  repository finds no `disable_telemetry_events` or
  `ORT_DISABLE_TELEMETRY`. **(checked)** The PC uses onnxruntime 1.30.0
  (`backend/requirements.lock:1146`). The phone is already fine.
- **Not checked:** what the events contain, and whether the copy bundled
  inside sherpa-onnx obeys the switch.
- **Why it matters:** rule 1 says nothing private leaves the PC. Even if
  the events are harmless, Jarvis should turn them off and say so.
- **Fix:** call the "disable telemetry" switch once at startup, wherever
  ONNX Runtime is first loaded. Then check on the PC whether any events
  still go out.

### 1.4 The voice check lets in too many other voices

- **What:** the code's own note says the small voice-ID model "at 0.35 …
  let in more than half of the other speakers' clips". **(checked:
  `backend/rebuilt/jarvis_voice.py:734`)** The stronger model already
  offered lets in 3%. Better free models now exist in the same file format
  Jarvis already uses:
  - WeSpeaker's ResNet221 and ResNet293 (95-114 MB);
  - ReDimNet2, for later.

  WeSpeaker's published error rate is 0.57%, against 0.80% for the small
  model. Those numbers are for long clips, not Jarvis's 1.5-2 second ones.
- **What to do:** add one of these as a choice beside the two existing
  ones. Measure it on the owner's 110 recorded clips, and only then give it
  its own strictness settings.

### 1.5 Three speed fixes the owner will feel

| What | Evidence | Gain | Effort |
|---|---|---|---|
| **Voice uses only 2 processor cores.** The owner can raise it today with no code change: set `tts_threads` and `stt_threads` to 4 in the `[voice]` settings. | `backend/jarvis_speech.py:171-175` defaults to 2 **(checked)**. On the test machine, going from 2 to 4 threads made a short spoken phrase 1.13 s → 0.86 s, a sentence 2.51 s → 1.80 s, and speech-to-text 0.45 s → 0.36 s (measured). | About 0.3-0.4 s sooner to Jarvis's first sound. | Setting now; change the default later. |
| **Warm-up sends no words**, so the first question after Jarvis wakes re-reads the whole instructions and tool list. | `jarvis_power_switch.py:230-234` sends only the model name **(checked)**. Jarvis's own comments put the tool list at 3,000-3,600 tokens and a re-read at "3-4 s at 8K". | Up to 3-4 s off the first question after waking. | Small: warm up with the real system message, the tool list and "hi", one word of output, twice. |
| **The background learner throws away the chat's short-term memory.** 45 s after the owner stops talking, the learner uses the same model with a different prompt. Ollama keeps only one conversation's working memory on this card, so the next question re-reads the whole chat. | `extraction-wiring.patch`; `jarvis_sensitive.py:3008`, `:3055`. | Estimated 1-3 s off the first question after a pause. | Medium: after each learning pass, quietly re-send the last chat prompt. It fixes itself once the 12 GB card takes the learner. |

**How to confirm the third one on the PC.** Run the PowerShell line below.
It prints the last 40 answers and writes nothing. If the "reused" number
drops to near 0 after a pause, and "first word" gets longer, the learner
is the cause.

`$f = Join-Path $env:USERPROFILE ".openjarvis\speed.jsonl"; Get-Content $f -Tail 40 | ForEach-Object { $r = $_ | ConvertFrom-Json; if ($r.prompt_tokens) { "{0}  prompt {1}  reused {2}  first word {3} ms" -f ([DateTimeOffset]::FromUnixTimeSeconds([int64]$r.at).LocalDateTime), $r.prompt_tokens, $r.cached_tokens, $r.first_word_ms } }`

It reads the file from the `.openjarvis` folder in the owner's user
folder. If `OPENJARVIS_CONFIG_DIR` is set, the file is in that folder
instead, and the line needs that path.

### 1.6 Smaller things found on the way

- **Ringing alarms would not reach a Gadgetbridge watch.** Gadgetbridge
  (the Google-free way to put phone notifications on a watch) skips
  "ongoing" notifications. Jarvis's ringing alarm is ongoing
  (`ScheduleNotifier.kt:195`). **(checked)** So with the watch setting on,
  the alarm would never reach the watch. Fix: post a second, plain "Alarm"
  notice, or say so on the setting.
- **The model tool test is unfair to models other than Qwen.**
  `tools/tool_eval/ollama_tool_eval.py:158-161` uses Qwen's own settings
  for every model. **(checked)** Models named on the command line also load
  at Ollama's default 4,096 tokens, which is shorter than Jarvis's
  instructions. Fix this before any model bake-off (section 6).
- **Two branches use the same API section numbers.**
  - The research branch uses §60-62 for the chatbot driver, Projects and
    the screen.
  - The continuation branch uses §59-61 for Goals, the plan card and phone
    notifications.

  Merging both will clash in `docs/JARVIS-API.md`. Renumber one before the
  second merge.
- **`JARVIS-TODAY.md` is out of date in about seven places.** Other
  sessions read this status page first. For example:
  - it lists Projects and the chatbot driver as built, but they are only
    on the research branch;
  - it says the phone notifications feature is not built, but it is, on
    the continuation branch;
  - there is no `studio-live` branch.

  Details are in the inventory notes.
- **Phone addresses: `main`'s CLAUDE.md and `main`'s code disagree.**
  `main`'s CLAUDE.md (2026-09-27) says home-network addresses are allowed
  on the phone. The code refuses them (`PhoneAddress.kt`). The research
  branch's CLAUDE.md reverses the decision to match the code, so this
  resolves itself when that branch merges.

---

## 2. What competitors shipped since the 2026-09-25 reports

All of this comes from search summaries. The full list with dates and links
is in `research-audit-2026-09-28/report-commercial.md`.

| Company | What is new (July to 28 Sept) | What it means for Jarvis |
|---|---|---|
| **OpenAI (ChatGPT)** | "Work" replaced agent mode. Its cloud browser stays signed in to your accounts. "Scheduled" replaced Pulse, and added monitoring and event-triggered tasks (Gmail, Slack, GitHub). New memory ("Dreaming V3") has no list you can audit, and deleting a chat keeps what it learned. Mac "Computer History" (a keystroke-and-click timeline). Lockdown Mode. Voice can use apps, with approvals on screen. | Watches and event triggers are the big gap (ideas 1-2). Lockdown is a good idea (idea 10). The memory changes widen Jarvis's lead. |
| **Google (Gemini)** | Google Assistant is being retired on phones from 4 Sept. Daily Brief became free in the US. Gmail/Docs/Keep "Live" (paid). Gemini 3.8 Live. Gemini for Windows opens with **Alt+Space**, the same as Jarvis's quickbar. Pixel 11 "Device help". | Add one FAQ line about the Alt+Space clash: Jarvis already detects it and Settings can change the key. "PC help" (idea 8). |
| **Apple (Siri)** | iOS 27 Siri AI beta: a Siri app with synced history and auto-delete, a camera mode, **daily usage caps and a future fee**. The EFF says onscreen awareness cannot be blocked. | Jarvis leads on both. |
| **Microsoft (Copilot)** | A "super app" (25 Sept) with an always-on "Autopilot" agent, reportedly built on OpenClaw and billed by usage. Windows' own local AI needs an RTX 30-series card or newer, **so the owner's cards are excluded**. | Jarvis runs where Microsoft's local AI will not. |
| **Anthropic (Claude)** | Voice can use connectors. Background computer use on Mac: it never takes the mouse pointer and shows a status line. | Idea: a "Jarvis is working on your screen, 0:42, Stop" line during screen actions. |
| **Meta (Muse)** | Muse on the glasses with a wake word, a keychain device in December, computer use on the Mac. Training on chats is still on by default. | Nothing to copy. |
| **Others** | Alexa "Update Me When" (its price alerts can buy by themselves). Samsung One UI 9 custom "Now Brief" cards. Perplexity recurring background assistants. OpenAI's device delayed to 2027. Always-listening pendants (Omi, Plaud, Bee). | Price and change watches, without the buying (idea 1). Today-page cards (idea 6). Pendants stay out: always listening breaks the voice check. |

**Where Jarvis leads now:**

- no caps, tiers or usage bills;
- it runs on the owner's older cards;
- memory the owner can list, forget and erase, learned only from the
  owner's own words;
- it looks at the screen only when asked, saves nothing, and pauses on
  password boxes;
- approvals by tap only: never "always allow", never auto-buy;
- timers and alarms work without the AI model;
- "Where this came from" plus a quote check (on the research branch).
  Perplexity only just shipped something similar, for businesses.

---

## 3. New ideas, ranked: all fit the five rules

"Card" in this table means an approval card. "Graphics" says whether the
idea needs the second graphics card; "either" means it works with one card
or two. Effort: S = hours, M = a day or two, L = more.

| # | Idea | Where it comes from | Apps | Card? | Graphics | Effort |
|---|---|---|---|---|---|---|
| 1 | **"Tell me when a search shows something new"**, and "tell me when this price drops below X". A daily search of the owner's own words through the chosen search provider. The price is read by plain code, not the AI. It never buys. It first needs the page-watch fix: watches compare the raw page, so a changed ad triggers a false alert (`jarvis_tellme.py`). | Alexa, ChatGPT | Both | One per watch | either | S-M |
| 2 | **GitHub watches**: "tell me when CI finishes or fails, or the PR merges". Read-only. It uses the GitHub key Jarvis already has (`jarvis_reach.py:100`). Useful to this owner, since every phone change waits about 15 minutes for CI. | ChatGPT event tasks | Both | One per watch | either | S-M |
| 3 | **"Remind me next time I talk about X."** Matched by plain code against the owner's own words only. Fires at most 3 times and expires after 90 days. | OpenClaw `standing-intents.ts` (MIT) | Both | No (like a one-time reminder) | either | S-M |
| 4 | **"Where did I put …"** From the owner's own words ("the passport is in the top drawer"). A newer place replaces the older one, using the existing "true from" dates. Answered without the AI. Needs learner test cases for things that move. | Android "Remembered" | Both | No | either | S |
| 5 | **Tell the owner once when a watch breaks.** Today "Could not look: …" is only written under the watch; nothing notifies (`jarvis_tellme.py:1057-1069`) **(checked)**. So an urgent "tell me when" can be dead for days. Group the same failure, hold back repeats, and clear it by itself on the next good run. | Hermes `cron/incidents.py` (MIT) | Both | No | either | S |
| 6 | **Today page cards in the owner's own words**, with a time and days. Only from sources the briefing already reads. Extends the Today page already decided on. | Samsung Now Brief, Gemini Daily Brief | Both | No | either | S-M |
| 7 | **"Ring my phone."** Answered on the PC without the AI; the phone rings on the alarm channel, even on silent, with Stop and a time-out. | KDE Connect (GPL, so the idea only) | Both | No | either | S-M |
| 8 | **"Playing on your PC" buttons on the phone**: play, pause, next, greyed out when the link is stale. The routes already exist (`/api/media`), but no app screen uses them. | KDE Connect (idea only) | Phone | No (decided 2026-09-27) | either | S-M |
| 9 | **Deleting a chat also offers to forget the facts it taught.** The opposite direction ("also delete the chat it came from") already exists. | The complaint about ChatGPT's memory | Both | "Are you sure?" | either | S |
| 10 | **"Lockdown"**: one tap makes every way out of the PC ask first, or stop. Going stricter is instant. Undoing it uses the existing PC-only loosening: a card plus Windows Hello. | ChatGPT Lockdown Mode | Both | Only to undo | either | S |
| 11 | **Photo or screenshot → a proposed reminder or event.** Uses the existing Windows text reading; the text counts as outside text; Jarvis only proposes. | Siri Visual Intelligence | Both | Proposal only | either | S-M |
| 12 | **"PC help"**: why is it slow, how full is the disk, what is using the graphics card. Read-only. Any change (night light, Focus Assist) behind a card. | Pixel 11 Device help | PC (answers readable on the phone) | For changes | either | M |
| 13 | **Import from ChatGPT**, with a Brain button. Today `import_history.py` handles Claude and Gemini exports only, from the command line. Every fact still goes through review one at a time. | Gemini and Claude import tools | Both | Review queue | either (best overnight) | S |
| 14 | **"Hey Jarvis is off since the phone restarted: tap to turn it back on."** The phone's wake word is deliberately not started at boot (`WakeWordService`), so after a restart it is silently off. | Dicio (GPL, so the idea only) | Phone | No | either | S |
| 15 | **Quick Settings tiles the owner chooses** from a safe list: Start focus, 10-minute timer, Brief me, Stop everything, PC play/pause. Never an Approve tile. | Home Assistant app (Apache) | Phone | No | either | S-M |
| 16 | **Windows remember their size and place** (Brain, Settings, HUD), using Tauri's window-state plugin, version 2.4.1. **Careful:** by default it also restores whether a window was visible, which could show the HUD before Windows Hello when App lock is on. Restrict it to size and position. | tauri-plugin-window-state (MIT/Apache) | PC | No | either | S |
| 17 | **"Jarvis is working on your screen, 0:42, Stop"** status line during Windows screen actions. | Claude background computer use | PC | n/a | either | S |

**Owner's call, not ranked:**

- **"Wake my PC" from the phone (Wake-on-LAN).** This sends a small
  network packet that wakes a sleeping PC. It only works on the home
  Wi-Fi. That sits awkwardly with the 2026-09-28 decision that the phone
  talks only over Tailscale or Meshnet.
- **Framing hints for the Live camera**, like Gemini's Guided Vision. This
  needs both cards.

---

## 4. From GitHub: what to copy, what to emulate, what to skip

**Copy** means the licence (MIT, Apache or BSD) lets Jarvis reuse the
code, with a notice. **Emulate** means use the idea only; this is always
the case for GPL or AGPL code. Every project below was downloaded and its
code read, unless marked.

### Worth taking

| Project (licence, last change) | What to take | Where it goes in Jarvis | Verdict |
|---|---|---|---|
| **Handy** (MIT, 2026-09-28) | A finished **talk-to-type** in a Tauri app, built on the same Silero and Parakeet speech tools Jarvis uses. Its `paste_tx/windows.rs` pastes via the clipboard, waits for proof the other program read it, then puts back what the owner had copied. It never overwrites a newer copy, and keeps the text out of Windows clipboard history. Also a filler-word list ("um", "uh"). **Missing:** it does not refuse password boxes; Jarvis must. | a new `talk_type.rs`, and `hotkeys.rs` | **Copy** (M) |
| **OpenClaw** (MIT, 09-27) | Shortening big tool results: keep the first and last 1,500 characters, and clear old results once the context is half full. Also "remind me next time" (`standing-intents.ts`), a "no fake progress" test, "forgotten stays forgotten", and a scoring recipe for which facts deserve a "Pin this?" or "Still true?" card. | `jarvis_agent.py` (`_tool_content`, `fit_messages`), `jarvis_schedule.py`, the learner tests | **Copy / emulate** |
| **Hermes Agent** (MIT, 09-27) | Grouping failed watches into one notice (`cron/incidents.py`). Shortening that keeps every word the owner said and only trims Jarvis's old answers, plus a recall test for it. A "reader" call that reads a long email with no tools and returns a short extract. **Do not copy** its auto-approve for sub-agents, or its background memory writer. | `jarvis_tellme.py`, context trimming, a new `eval_context.py` | **Copy / emulate** |
| **nanobot** (MIT, 09-28) | `normalize_tool_result()` and `maybe_persist_tool_result()`: tidy code for shortening tool results. | `jarvis_agent.py` | **Copy** (S) |
| **ReMe** (Apache, 09-26) | An "open loops" record: follow-up topics with a confidence score, and resolved ones suppressed for good. Every suggestion is either shown or dropped with a written reason. | the decided "promises become reminder offers" | **Emulate** (M) |
| **Home Assistant Android** (Apache) | The owner-chosen tile pattern, and a "What's new" screen grouped New / Improved / Fixed, where each item opens its setting. | phone tiles; the "What's new" screen the setup audit proposed | **Copy / emulate** |
| **OpenHuman** (GPL-3, 09-28) | The closest shape to Jarvis's desktop (Rust + Tauri). Its memory lookup is skipped unless a message both "owns and asks" (`memory/auto_recall/gate.rs`). | memory recall | **Idea only**, and only if the memory self-test agrees |
| **KDE Connect**, **Dicio** (GPL) | "Ring my phone", media buttons, and the tap-to-restart wake-word notice. | ideas 7, 8, 14 | **Idea only** |

### Checked and skipped (reason in brackets)

- **Memory and agents:**
  - mem0 (its OpenMemory app has been deleted from the repo);
  - Letta, Leon and nanobot's memory (the AI writes its own memory);
  - Hindsight (needs Postgres);
  - Graphiti (needs Neo4j);
  - Memobase (quiet since January);
  - goose (its new AI safety guard lets the action through when the guard
    fails);
  - screenpipe (now under a commercial licence);
  - n8n (would be a second scheduler);
  - Agent-S (too big for 8 GB);
  - Khoj (AGPL, and slowing down).
- **Apps:**
  - Google AI Edge Gallery ("Always allow" is its main button, and it
    added Firebase Analytics on 09-25);
  - PocketPal (a model catalogue, and a leaderboard that uploads results);
  - Dicio's notification reading (no list of allowed apps);
  - Easer (lets other apps act as the owner);
  - Home Assistant's power-menu controls (they switch devices from the
    lock screen with no card);
  - Material 3 Expressive (still experimental);
  - Whispering (now AGPL; Handy does the same job under MIT).
- **Voice:**
  - wyoming-satellite (deprecated), Rhasspy 3 (quiet since 2023), Willow
    (hardware only);
  - Orpheus and Sesame CSM (built on Llama weights);
  - MOSS-TTS-Nano (not licensed for redistribution);
  - AASIST (a spoof detector, quiet since 2022; no detector reliably
    catches a replayed recording).
- **LiveKit's local end-of-turn model:** its licence allows it only inside
  LiveKit's own framework.

---

## 5. Voice

What is already current: Smart Turn v3.2, sherpa-onnx 1.13.8, Kokoro v1.0
(the upgrade already decided), openWakeWord 0.6.0, and livekit-wakeword
0.2.1. Jarvis already interrupts the way LiveKit does: it needs 0.5 s of
speech to count, pauses first, and carries on after a false interruption.

| # | Improvement | What it gives | Licence | Graphics | Effort |
|---|---|---|---|---|---|
| 1 | **Newer speech detector: Silero VAD v4 → v6.** The file Jarvis downloads is v4; its own label says so. v6 uses a layout sherpa-onnx already handles, and Jarvis already sends the right window size (`jarvis_speech.py:363`). So the swap is a new file plus a new checksum. v6 claims 16% fewer errors in noise (search result). Re-measure the voice-check bars on the 110 clips afterwards. | Fewer missed or false starts | MIT | processor | S |
| 2 | **A stronger voice-ID model** (see 1.4) | Safety | Apache | processor | S-M |
| 3 | **A second "Hey Jarvis" detector: microWakeWord's `hey_jarvis`** (52 KB, Windows packages exist). Wake only when both detectors agree. The earlier "ESP32 only" rejection was wrong; its PC package exists. It publishes no false-alarm numbers, so it must be measured. | Fewer false wake-ups | Apache | processor | S-M |
| 4 | **Start answering early, but hold it.** When Smart Turn first thinks the owner has finished, start the model, but play nothing. Use the result if the turn really ended; throw it away if the owner keeps talking. The first tool call ends the guess, so no tool ever runs and no card ever appears on a guess. Voice check and speech-to-text still come first. LiveKit and Pipecat both ship this. | Lower delay before Jarvis answers | ideas (Apache / BSD) | either | M |
| 5 | **VibeVoice-Realtime-0.5B** as a bake-off voice on the second card. It claims about 200 ms to the first sound and real time on a Turing card. Its voices are fixed, so it cannot copy a voice, which is safer. On Turing it falls back to a slower path with a quality warning. | Speed and naturalness | MIT | 12 GB card | L |
| 6 | **Chatterbox Nano** as a voice-copying engine on the processor (claims 3x faster than real time on 8 cores). Every clip carries a hidden watermark, so Jarvis could refuse clips that carry it. **Unchecked:** whether the watermark survives being played through a speaker and back into a microphone. | Naturalness | MIT | processor | M |
| 7 | **"Too short to judge" per clip** (WeSpeaker's new U³-xi scoring) instead of a fixed 1.5-2 s minimum. Research-grade: only after #2, and never loosen anything without the owner. | Fewer "say a bit more" refusals | Apache | processor | L |

**Also:**

- **Stop an alarm with the wake word.** In Home Assistant, saying the wake
  word while a timer rings stops the timer instead of starting a question.
  Worth checking that Jarvis does the same.
- **Pocket TTS** has a newer version (3.3.0, 2026-09-24) than the one
  built. Recheck it before its bake-off.
- **Still no, for the same reasons:**
  - full-duplex voice models (they skip the voice check and the cards);
  - speech-to-text before the voice check;
  - GPL audio tools.

  One new variant of streaming speech-to-text keeps the rule, but a
  stranger speaking mid-sentence could be transcribed for up to 2 seconds.
  That is the owner's call, and should wait until after #4.

---

## 6. Models and the engine

### A small model bake-off on the 8 GB card

**Fix the tool test first (1.6).** Then wrap each candidate with Jarvis's
own instructions and 16K of conversation, and run three tests:

- the tool test, three times over;
- the memory self-test and learner test;
- the speed record.

Keep a candidate only if it ties or beats Jarvis's current model on tools
(within 10 points counts as a tie) and does not lower the learner test.

| Candidate | Download | Why try it |
|---|---|---|
| `jarvis-primary` (Qwen3 8B) | 5.0 GB | the baseline |
| `lfm2.5:8b` (Liquid) | 5.2 GB | Only 1.5 billion of its 8.3 billion parameters work on each word, so it could be much faster. Makers' scores: IFEval 91.8, BFCL v4 48.5. |
| `granite4.2:8b` (IBM, Apache) | 5.3 GB | Makers' scores: BFCL v4 52.4. Ollama has no Granite-specific tool reader, so it must be tested. |
| `granite4.2:3b` | not checked | the same makers' tool score as the 8B, at a third of the size |
| `qwen3.5:4b` | not checked | A known bug makes its first request after loading slow on Turing cards (llama.cpp #29513). |

**Ruled out for the 8 GB card:** qwen3.5:9b, gemma4 (both sizes),
gpt-oss-20b, and the new 27-30B dense models. They do not fit, or their
"thinking" cannot be switched off.

### Engine settings worth measuring

1. **Warm-up with real words** (1.5).
2. **Cap each Ollama's prompt memory in system RAM**
   (`LLAMA_ARG_CACHE_RAM=3072`). The engine's default is 8 GB of system
   RAM per copy, and Jarvis can run up to three copies.
3. **Warn in the preflight check if a llama.cpp `config.ini` exists** in
   `%PROGRAMDATA%\llama.cpp` or `%APPDATA%\llama.cpp`. Ollama's engine
   reads settings from them, a hidden place for a setting to come from.
4. **Try `LLAMA_ARG_SPEC_TYPE=ngram-mod`**, a cheap form of "guess ahead"
   that needs no second model. Keep it only if words per second go up.
5. **Memory search models.** Upgrade fastembed from 0.8.0 to 0.8.1
   (`requirements.lock:407`, **checked**) to get two stronger search
   models: Qwen3-Embedding-0.6B and EmbeddingGemma. Bake them off against
   today's bge-small, and bake off the re-rankers MiniLM-L-12 and
   jina-turbo. Costs:
   - each search takes about 20x more processor time;
   - the whole memory store must be re-indexed;
   - every change must beat `eval_memory.py`, as the owner's rule says.
6. **For the 12 GB card, when it is in:** qwen3.5:9b with its built-in
   "guess ahead" layers, and for the big lane, Nemotron 3.5 Lightning
   against Qwen3.6-35B-A3B.

**Not now:** ExLlamaV3 (it would replace Ollama), vLLM or SGLang (no real
Turing support), DFlash guess-ahead (it measured slower in practice), and a
separate "router" model.

---

## 7. Speed and upkeep: what the code audit measured

**Fine already (measured):**

| Step | Time |
|---|---|
| Memory search | 3-5 ms at 1,000 facts |
| Opening the memory database | 0.4 ms |
| Settings file | 0.2 ms |
| Quick-command check | 0.1 ms |

The prompt order already suits Ollama's reuse of repeated text. The phone
holds no wake locks and runs no timed jobs, and its release build is
already shrunk.

**Worth doing:**

| # | What | Evidence | Gain | Effort |
|---|---|---|---|---|
| 1 | **Run the desktop page tests four at a time in CI** | They take 21 of CI's 22 minutes, and mostly wait. Measured here: 401 s one at a time, 119 s four at a time, no failures. | CI from about 22 to about 7 minutes a push | S |
| 2 | **Stop running CI twice per commit.** Every branch push runs it, and the same commit runs again for its pull request (`ci.yml:8-22`, **checked**). | Runs 380 and 381 were the same commit, 22 minutes each | Half the CI minutes. Owner's call: a branch with no pull request would get no CI, though a draft pull request is enough. | S |
| 3 | Learner and warm-up fixes | see 1.5 | 1-4 s | S-M |
| 4 | Voice threads | see 1.5 | 0.3-0.4 s | S |
| 5 | **The desktop starts `nvidia-smi` every 3 seconds, all day** (`lib.rs:76`, **checked**). It stops only while the widget is hidden, and the widget shows by default. | About 28,800 program starts a day. The code's comment says the cost is "nothing in practice"; the helper doubts that; not measured. | Less background load | S-M: read the card through NVIDIA's library instead, or sample every 10 s when idle |
| 6 | **Phone battery away from home.** When the PC is out of reach, the phone retries forever, at most every 30 s. It never checks whether it has any network at all (`EventStream.kt:275-293`). | About 2,880 attempts a day away from home (estimate) | Battery | M: pause while offline, and slow down after about 10 failures. Sending the keep-alive signal less often would mean waiting longer before the link counts as "stale", which is rule 4, so that part is the owner's call. |
| 7 | **The phone app is compiled three times per CI run**, and backend-only changes also run the phone emulator | about 3 min 20 s each (measured) | about 3 minutes a run | S-M |
| 8 | **15 test-case files are kept as two identical copies** (phone and desktop) | byte-compared | less to keep in step | S |
| 9 | **The first chat after a backend start** spends about 0.2-0.3 s loading code (`jarvis_sensitive` alone is 123 ms). Load it at startup, the way voice already warms up. | measured | first turn | S |
| 10 | The phone decrypts its pairing key from the Android Keystore on every request (29 places). Keep it in memory for the life of the app, never logged. | read | small | S |

**Upkeep, a longer-term suggestion (owner's call).** The backend is 82
patch files (8,458 lines) plus a 13,748-line README, and 57 commits in two
weeks changed a patch. Nine newer features use a better shape: a one-line
hook plus a whole module that CI can test. Building every new feature that
way, and slowly moving old ones over, turns code that only the owner's PC
can test into code GitHub can test.

---

## 8. Jarvis's Brain next to projects that have one finished

*(Filled in below from the two Brain audits.)*

---

## 9. Where every feature stands

The full table has 257 rows, one per feature, each checked in the code. It
is in `research-audit-2026-09-28/inventory.md`.

| Status | Count |
|---|---|
| Built on `main` | 195 |
| Built but switched off, waiting for the second card or a measurement | 13 |
| Built only on an unmerged branch | 27 |
| Decided, not built yet | 18 |
| Designed on paper only | 4 |

**Unmerged branches (as of this morning):**

| Branch | Commits | What is on it |
|---|---|---|
| `claude/jarvis-ai-assistant-research-ff37vy` | 109 | The chatbot driver and "compare", Projects, the screen rules, the money limit, the Jarvis Live design |
| `claude/jarvis-continuation-03kls1` | 19 | Goals, the plan card, the third graphics card, "Try the cloud model", reading phone notifications |
| `claude/jarvis-3d-animal-mascot-8dr0tb` | 19 | Three animal faces, "voice follows the face", real lip-sync |
| `claude/peaceful-volta-tr1x60` | 1 | Keeps Jarvis's rules first on turns with no tools |

**Half-built.** These exist in the code but cannot be used from the apps
yet:

- `/api/feedback/counts` and `/api/email/drafting` have no screen;
- `/api/skills/suggestions` has no caller, and nothing feeds it;
- there is no screen to see or remove news feeds;
- the overnight-tidy switch runs nothing yet;
- Bubble mode still lacks Android's `MessagingStyle`;
- on the continuation branch, the plan card is locked until a tool-test
  results file exists, and Goals never calls the model;
- on the research branch, the "screen answers" voice setting exists but
  nothing looks at the screen yet.

**On one app only, with no reason written in ARCHITECTURE §8.** Each needs
either a line in §8 or the missing half:

- the phone's quick-settings tile;
- the phone's quick-link widget;
- the phone as a share target;
- the phone as Android's assistant app;
- the phone's Checks and crash screens;
- the desktop's retrieval list (`/api/retrieve`).

---

## 10. Platform changes coming

| What | When | Action |
|---|---|---|
| **Android 17's own volume slider for assistants** | now | Jarvis already plays as assistant audio, so it gets its own slider. Say so in Voice settings. |
| **Android 17 app bubbles** (long-press the app icon → Bubble) | now | Might make Floating Jarvis's Bubble mode work with no code. Try it on the Pixel. |
| **Android 17 background sound limits** | when Jarvis moves to Android's version 37 rules (targetSdk 37); fine at 36 today | Sound from the background service started at boot would be muted. Plan for it. |
| **Android developer verification** | Google-certified phones worldwide in 2027; four countries from 2026-09-30 | Installing an unverified app by tapping the file will need a one-time 24-hour wait. Installing with adb from the PC stays allowed. GrapheneOS is likely unaffected (not verified). Add a note to `docs/INSTALL.md` and `docs/GRAPHENEOS.md`. |
| **Tauri 3** | alpha only | Do not move yet. |
| **Glance 1.2** (phone widgets) | stable since 2026-08-26 | Already queued. |
| **Ollama 0.40** | release candidate | It converts older model files on first load (not qwen3). Test any Qwen 3.5 candidate on the Ollama version the owner will keep. |

---

## 11. Questions for the owner

See the reply that came with this document. The questions are kept short
there, one or two at a time.
