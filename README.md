# Epic-Jarvis

**Your local-first, privacy-locked personal AI assistant for Windows 11 and Android.**

Epic-Jarvis combines a **Windows 11 Desktop Spotlight & Brain HUD** (`jarvis-desktop`, built with Tauri v2, Rust, and WebView2), a **Local Python Agent & Memory Backend** (`jarvis-backend`), and a **Native Android Companion App** (`jarvis-client`, built with Kotlin and Jetpack Compose). Your everyday conversations, memory, documents, voice, and personal data stay on your own hardware via **Ollama** and **ONNX Runtime**, with tightly budgeted, opt-in cloud escalation available when you want extra horsepower.

## The five rules that are not negotiable

These are not features. They are the promises the whole program is built
around, and every change is checked against them. They are in the owner's own
words, because the exact wording is part of the decision.

1. Anything touching email, files, credentials or stored memory stays on the
   local model. The app sends none of it anywhere.
2. The app never opens a public tunnel. No ngrok, no Cloudflare Tunnel, no
   Tailscale Funnel, no "share my Jarvis".
3. API keys are allowed in the app - the owner reversed the old blanket ban
   on 2026-09-17, to unblock things like a GitHub API integration. Any key
   still gets the same care the pairing token already gets: never logged,
   sent only to the one service it authenticates against, and kept out of
   anything the app writes to disk in plain text.
4. The app never auto-approves anything, and blocks acting when the event
   stream is stale.
5. Non-commercial build. Sideloaded via adb, never listed on Play.
   The owner said on 2026-09-28 that EpicJarvis **will never be
   commercialized**. So a non-commercial licence (CC BY-NC, CC BY-NC-SA) is
   no reason to avoid or replace a part - don't raise "it blocks selling
   Jarvis" as a concern. Everything else those licences ask still applies:
   credit in THIRD-PARTY-NOTICES.txt, share-alike, no redistribution
   against their terms.

> **Three approved exceptions exist, and each is named and bounded.** Rule 1 is
> bent for exactly two things in what ships today.
>
> - A project's **"Shareable"** switch — **off by default**, approved by you
>   each time it is used, and it never carries health or money numbers, memory,
>   email or credentials — may send a short piece of that project's files,
>   shown word for word on its card first, to a web search or a chatbot.
> - The **locked backup file** may be saved into a folder your cloud service
>   syncs. It is a locked copy of what Jarvis knows — which is exactly why its
>   recovery code matters so much.
>
> Rule 4 is bent for exactly one thing: one approval covers a whole chatbot
> conversation, and Jarvis may then keep asking questions on its own, inside the
> limits you set (see [What asks first](#what-asks-first)). Nothing else in
> these five rules is loosened anywhere.

## How the five rules are enforced

The rules above are the promises; this is the machinery behind them, so a
reader can check them rather than take them on trust.

1. **Private by architecture, not just policy**: anything touching your emails, local files, credentials, finances, or long-term memory is locked to your **local LLM** via automatic taint latches (`jarvis_gate.py`). Sensitive turns cannot leave your PC.
2. **Zero public tunnels**: cross-device sync between your Windows 11 PC and your Android phone runs strictly over **localhost (`127.0.0.1`)**, **Tailscale**, or **NordVPN Meshnet** — never through public ingress tunnels (`ngrok`, Cloudflare Tunnel, or Tailscale Funnel).
3. **Fail-closed credential vault & scrubber**: secrets live in a host-bound vault (`jarvis_vault.py`, backed by Windows Credential Manager) and are handled by name (`vault://...`). Values resolve only at the single outbound request header that authenticates with them, and are scrubbed everywhere else (`jarvis_scrub.py`).
4. **Human-in-the-loop approval & 1-click undo**: consequential actions follow **Plan → Describe → Gate → Run** (`jarvis_gate.py`). Approval cards never steal keyboard focus (so a stray `Enter` while typing can never auto-approve an action), wait up to 15 minutes, and record reversible before/after snapshots in `receipts.db` for **1-click undo** (`jarvis_receipts.py`). While the connection is catching up, **Deny still works** and only Approve waits - refusing is never held.

## Major Features at a Glance

| Area | What Jarvis Does | Core Modules & Surfaces |
| :--- | :--- | :--- |
| **Desktop Spotlight & Brain HUD** | Instant `Alt+Space` Quickbar (`750×80`) with live step progress (`#progress-line`) plus a `1280×820` HUD with an interactive 3D Galaxy Brain Graph, approval cards, and drawers. | `jarvis-desktop/`, `jarvis_hud.py`, `brain.js`, `galaxy-view.js` |
| **Android Companion App** | Native Kotlin + Jetpack Compose app with 1,296-word passphrase / QR pairing, remote voice, notifications, encrypted backups, and phone captcha/sign-in hand-off. | `jarvis-client/`, `jarvis_devices.py`, `jarvis_handoff.py` |
| **Bitemporal Second Brain** | Learns facts from your own words automatically, tracks when facts were true (`valid_from` / `valid_to`), and lists every learned fact in both apps with a **Forget ("Are you sure?")** button. | `jarvis_memory.py`, `bitemporal.patch`, `jarvis_forget_range.py` |
| **"Write Like Me" Voiceprint** | Learns your sentence rhythm, contraction rate, and phrasing across registers while stripping all names, dates, amounts, paths, and numbers—100% local-only. | `jarvis_voiceprint.py`, `plugins/ready/voiceprint/`, `manner.js` |
| **Skills & Self-Improvement** | Compatible with the open `SKILL.md` standard: progressive disclosure, `/skill` commands, security scanning (`scan_text`), routine discovery, and approval-gated edits. | `jarvis_skills.py`, `jarvis_skill_hub.py`, `jarvis_skill_discovery.py` |
| **Hybrid Local + Cloud Routing** | Runs 8B/9B models locally on your GPU (`Qwen 3.5 9B` / `Qwen 3 8B` + local opt-in abliterated models) with complexity/latency routing to spend-capped cloud lanes. | `jarvis_models.py`, `jarvis_router.py`, `jarvis_auto_router.py`, `jarvis_chatbot_api.py` |
| **Voice & Speaker Verification** | Verify-first, transcribe-second pipeline: **CAM++** (everyday) & **TitaNet-Large** (strict) speaker verification, plus **WeSpeaker**, before **Parakeet TDT** STT, **Kokoro** / **ZipVoice** / **Pocket TTS**, and `openWakeWord`. | `jarvis_speech.py`, `jarvis_voice.py`, `jarvis_kokoro.py` |
| **Projects, Finance & Learning** | `coding` and `life` project workspaces with benchmarks, SHA-256 deduplicated bank CSV spending, a subscription and price-rise radar in whole cents, real-money retirement projections, and **FSRS v6** (`fsrs==6.3.2`) flashcards. | `jarvis_projects.py`, `jarvis_spending.py`, `jarvis_retirement.py`, `jarvis_decks.py` |
| **Desktop, Browser & Phone Tools** | Opt-in CDP Accessibility-Tree browser driver, Windows UI Automation (`uiautomation`), ADB Android control, Docker management, and local SearXNG web search. | `jarvis_browser_control.py`, `jarvis_ui_control.py`, `jarvis_android_control.py` |
| **PC Health & N-GPU Doctor** | Names every graphics card's own memory, use and state - resting, working, warm, hot, at its power limit, or nearly full - and answers heat and "why is my PC slow" without calling rest a fault. Both apps show the same answers through PC help. | `jarvis_pc_help.py`, `jarvis_hardware.py`, `jarvis_compute.py` |

## What's new (October 2026)

The newest work, grouped by what it changes for you. Everything described as a
feature you can use is on `main` and reachable from both apps unless the bullet
says otherwise. Anything built but not reachable yet says so in its own bullet.

- **Your money: a subscriptions and price-rise radar, and two bugs in it
  fixed.** Ask in chat *"did any of my subscriptions go up?"* or *"was I
  charged twice?"* and Jarvis reads the bank files that already have a saved
  layout. It finds shops billing about once a month (26-35 days) or once a
  year (350-380), reports the **exact rise in whole cents**, and reports the
  same shop charging the same amount twice within six days. It reuses the
  spending answer's table block, so both apps draw it with no new screen. The
  two fixes: a rise billed again at the same new price no longer hides the
  rise, and a different amount inside one bill (a one-off charge beside a
  subscription) is no longer read as a price rise. Both apps are tested
  against one generated contract, so they cannot disagree about the numbers.
  The mail half (trial-ending and delivery emails) is not built. Links:
  [FINANCE-DESIGN](docs/FINANCE-DESIGN.md) §11,
  [JARVIS-API](docs/JARVIS-API.md) §100.3.
- **Approvals: refusing is never held, even while the connection catches up.**
  The rule both apps already promised is now true on all four surfaces: Deny
  works on the bar, the widget, the HUD and the phone (its home-screen widget
  and a notification too), while Approve still waits for the link to catch up.
  A stale-but-connected phone widget shows the last known cards **with** Deny;
  only a link that is gone hides it. A stale Deny cannot approve anything (it
  sends `approved: false`), and a late one is refused by the server's existing
  expired/duplicate answer. Links: [ARCHITECTURE](docs/ARCHITECTURE.md) §3,
  [the desktop test](jarvis-desktop/tests/deny-on-stale.mjs).
- **Jarvis Live names the real reason it stopped, instead of blaming you.**
  When Android refused the microphone foreground service, or the microphone
  permission was missing, the end screen used to say *"You ended it."* The
  phone now sorts the failure into its own kind and the PC gives each kind its
  own plain sentence; an end nobody explained reads "Live ended." and never
  "You ended it." Both sides read one shared table, so their words cannot
  drift. No device fix is claimed - the next attempt on the phone will show on
  the end screen which refusal it was. Links:
  [LIVE-DESIGN](docs/LIVE-DESIGN.md) §2,
  [JARVIS-API](docs/JARVIS-API.md) §63.1-63.2.
- **Graphics cards: one, two or three, and twin cards are told apart.** Every
  GPU sentence works on **one card, the two installed today, or three** -
  three is never required. Two cards with the same name are called "on your
  monitor" and "(headless)", or by their own id tail when the monitor cannot
  separate them. The big 30B model's 28,672-token figure is the setting
  **measured on two cards**; it is not raised for a third card until a
  measurement on this PC says it fits. PC help's `gpu`, `heat` and "why is my
  PC slow" answers now read each card's own state (`pstate` + clocks + load),
  so a resting card is never called throttled, and each card's memory is
  reported. Links: [MODEL-TOPOLOGY](docs/MODEL-TOPOLOGY.md),
  [MEASURED-2026-10-05-owner-pc.md](docs/MEASURED-2026-10-05-owner-pc.md),
  [JARVIS-API](docs/JARVIS-API.md) §84.
- **Study decks: a memory-strength radar, a spoken-answer grader, and a
  reversible voice review.** The flashcard module (`jarvis_decks.py`) can now
  name the topics whose cards have dropped below 75% memory strength, weakest
  first, in one plain sentence per topic; grade a spoken answer against the
  card with no model at all (empty or "I don't know" is Again, and a misheard
  answer is never marked Easy, because Easy waits longest before the card
  comes back); and record a voice review as a receipt, so the existing Undo
  puts the card back exactly - even after a restart. **This is the backend
  half only: no route and no app screen yet**, so it does not change what you
  can do in either app today. Links: [JARVIS-API](docs/JARVIS-API.md) §102,
  [decks module](backend/jarvis_decks.py).
- **Built, tested, and not reachable from either app yet: a local data sandbox
  and a file time machine.** The **data sandbox** (`jarvis_sandbox_exec.py`)
  is for the day a small local model writes a small Python script for data or
  maths. A strict allowlist refuses any import that could reach the network or
  start another program, the script runs in a separate scrubbed Python
  process, and only a result stamped with a per-run secret code comes back.
  Five seconds and 64 KiB of output are hard limits; **memory is not bounded
  on Windows yet**. The **file guardian** (`jarvis_file_guardian.py`) keeps
  the bytes an overwrite would destroy in the folders Jarvis may change: one
  compressed copy per distinct content, a size-limited diff, a 250 MB limit
  that never prunes a pinned copy, and a restore that asks the existing Undo
  card and writes a new receipt so the restore itself can be undone. Neither
  is wired into a route, a chat tool, a card or a screen; wiring them in is a
  separate decision. Links:
  [sandbox module](backend/jarvis_sandbox_exec.py),
  [guardian module](backend/jarvis_file_guardian.py).
- **Two ratchets against tests that measure the wrong thing.** One refuses a
  test that asserts on a production module's **source text**; the other
  refuses one that pins a **line number or a slice** of source. Both walk the
  `ast` rather than matching text, both record today's debt as a ceiling that
  may only go down, and both run in CI. Links:
  [check_no_source_pins.py](tools/check_no_source_pins.py),
  [check_position_pins.py](tools/check_position_pins.py).
- **In flight, not in this build (17 October 2026).** Two open pull requests
  are not merged: the clipboard time-machine backend (#536) and the red-team
  decision lab (#538). **Planned, not built:** the flashcard coach's phone
  screen; a third graphics card is planned but not installed, so every
  three-card case in the tests is an injected reading; the sandbox's Windows
  memory cap and the wiring of the sandbox, the file guardian and the
  study-deck additions into an app or a tool are follow-up slices; the
  voice-scribe pillar waits for your answers to three privacy questions.

## Feature Highlights in Detail

### 1. Desktop Quickbar, Galaxy HUD & Emergency Stop
* **Spotlight Quickbar (`Alt+Space`)**: Appears over any application with live bounded-step progress (`What Jarvis is doing right now, one bounded step at a time`), push-to-talk microphone capture, and quick commands (`jarvis_quick.py`).
* **Galaxy Brain Graph (`Win+Shift+J`)**: Visualizes your active entities, relationships, and retired historical facts (`brain.js`, `galaxy-view.js`), with the picture bounded to a fixed maximum number of dots, chosen by how many facts name each one—so the same list always draws the same Galaxy.
* **Emergency "Stop Everything" Kill-Switch (`Alt+Shift+X`)**: Immediately closes any held push-to-talk microphone stream in-process, halts active capture feeds, and aborts running backend tasks.

### 2. Bitemporal Memory, Encrypted Backups & "Write Like Me"
* **Bitemporal Fact Store (`jarvis_memory.py`)**: Contradicted or updated facts are retired with a `valid_to` timestamp rather than overwritten—preserving a complete timeline of what changed and when.
* **Owner-Words-Only Learning & Safe Chat Import (`import_history.py`)**: Imports archives from ChatGPT, Claude, Gemini, and DeepSeek while filtering strictly to **your** messages so assistant outputs never pollute your memory.
* **"Write Like Me" Voiceprint (`jarvis_voiceprint.py`)**: Builds an inspectable stylometric profile from your calibration answers and writing samples (`voiceprint.db`), guarded by `jarvis_scrub` and full **List + Forget-with-confirm** controls.
* **Encrypted Backups (`jarvis_backup.py`)**: Protects personal data backups with Argon2id / Windows Credential Manager, and restoring one always needs Windows Hello on the PC.

### 3. Local AI on One, Two or Three Cards, Opt-In Uncensored Models & Spend-Capped Cloud Lanes
* **Hardware-Aware Local Inference**: Separates your display GPU (an 8 GB RTX 2080 SUPER running Windows 11 DWM + WebView2) from your dedicated headless AI GPU (a 12 GB RTX 2060 running `Qwen 3.5 9B` or `Qwen 3 8B` in Ollama), with automatic prefix warming (`warm_prefix()`) on wake. The same code runs on **one card, the two installed today, or three**; two identical cards are told apart by role ("on your monitor" / "(headless)") and, if the monitor cannot separate them, by their own id tail - never by a bare duplicated name.
* **Honest Card Figures & Health**: The big 30B model's 28,672-token setting is the figure measured on two cards, and it is not raised for a third card until measured there. PC help's `gpu`, `heat` and "why is my PC slow" answers are per card, read `pstate` + clocks + load so rest is not called a fault, and say plainly when this PC's driver will not report per-program memory (`[N/A]`).
* **On-Disk Opt-In Models (`jarvis_optin_models.py`)**: Switch to local uncensored/abliterated GGUF models already on your drive without triggering any external downloads.
* **Smart Cloud Escalation with Whole-Cent Spend Caps (`jarvis_router.py`, `jarvis_auto_router.py`, `jarvis_chatbot_api.py`)**: Escalates complex, untainted coding or research turns to `jarvis-escalate` / `jarvis-critic`, extracts `reasoning_content` fallbacks automatically, and records every cent against your monthly cap (`jarvis_chatbot_api.money_check()`).

### 4. Verify-First Voice Pipeline
* **Speaker Verification Before Transcription (`jarvis_speech.py`)**: Every voice clip is verified against your voiceprint (**CAM++** for everyday speed, **TitaNet-Large** for strict verification, plus **WeSpeaker**) *before* speech-to-text runs. Unverified audio is never transcribed.
* **Local STT, TTS & Wake Word**: Uses **Silero VAD**, **openWakeWord** (`hey_jarvis` + custom `stop_head.bin`), **NeMo Parakeet TDT 0.6B** via `sherpa-onnx`, and **Kokoro-82M** (54 voices with lip-sync timing) plus **ZipVoice**, **F5-TTS**, and **Pocket TTS** for custom voice cloning (**Pocket TTS** is built and pinned but not switched on yet).
* **Jarvis Live says why it stopped (`jarvis_live.py`)**: Android's foreground-service refusal, a missing microphone permission and a stopped microphone each get their own plain sentence on the end screen, and an end nobody explained is "Live ended." - never "You ended it." Both apps read one shared case table, so their words cannot drift.

### 5. Unified Design System & Living UI
* **Single-Source W3C DTCG Tokens (`tokens/themes.tokens.json`)**: Ten color families compiled via `tools/tokens/build.mjs` into three Desktop themes (`deep-space`, `paper`, `high-contrast`) and three Android themes (`reactor`, `daylight`, `contrast`), verified for WCAG AA/AAA contrast (`themecheck.mjs` & `contrast.mjs`).
* **Procedural Seasonal Sky & Animated Companions**: Dynamic astronomical sky/season calculations (`sky.js`, `season.js`) and animated critters (`faces.html`, `CritterShaders.kt`) that automatically pause rendering when windows are hidden.

## What asks first

**Jarvis never acts without a card for anything that leaves the PC or touches
private things.** It asks, you decide — on the PC or on the phone. Rule 4 above
is the short version. One qualification, said plainly: **a card can cover a whole
job, not just a single message.** When you approve a chatbot conversation, Jarvis
may then follow up with that AI *on its own*, inside the limits you set — that is
the one place rule 4 is deliberately loosened.

- Every action that is not completely safe raises **one approval card**.
  Nothing runs until you answer, and there is no "approve all" control
  anywhere.
- **Risky** cards need Windows Hello on the PC, or your screen lock on the
  phone. With no lock set up, the card is refused until you set one up. This
  narrows a real gap without closing it — see [Honest limits](#honest-limits).
- **Stopping is never held back.** Stop everything, Cancel on a job, muting
  and Undo all happen at once, with no card. The same is true of refusing an
  approval card: Deny works even while the connection is catching up - only
  Approve waits.
- **Outside text raises the bar.** In a turn that has read an email, a page, a
  file or other outside text, note writes, web searches and smart-home
  switches ask first.
- The named ways out of the PC — sending email, the chatbot driver,
  Open-Meteo weather, a web search that could repeat something private — each
  get their own card, and each card says what will leave the PC.

The full list, in plain words, is **Settings → What asks first** in both apps.
It also has "make stricter" switches, and a short safe list the PC may loosen
— each change costing one card plus Windows Hello. Nothing outside that list
can be loosened from an app.

## Repository Structure

```text
Epic-Jarvis/
├── jarvis-backend/     # Canonical patched Python backend & HUD server (http://localhost:4719)
├── backend/            # 205 modules shipped whole (195 twins + 10 rebuilt), 147 patches & 356 test suites - measured 2026-10-17 on main at 7ddb5b8c
├── jarvis-desktop/     # Windows 11 Tauri v2 (Rust + WebView2) Spotlight & HUD application
├── jarvis-client/      # Native Android companion app (Kotlin + Jetpack Compose, minSdk 33)
├── plugins/            # Dynamic plugin loader (loader/) & drop-in plugins (ready/)
├── tokens/             # W3C DTCG design tokens compiled to Desktop CSS & Android Compose
├── contract/           # Shared pairing words (pair-words.txt)
├── docker/searxng/     # Local privacy-preserving SearXNG metasearch container setup
├── scripts/            # PowerShell setup, update, backup, & patch-stack management scripts
├── tools/              # Static verifiers, code generators, & architectural audit checkers
└── docs/               # 388 design docs, API reference (JARVIS-API.md) & decision logs - measured 2026-10-17 on main at 7ddb5b8c
```

## Quick Start (Windows 11)

1. **Install Prerequisites**: Windows 11 (64-bit), [Ollama](https://ollama.com/), Python 3.12, Node.js 18+, and Rust (stable MSVC).
2. **Run Backend Setup**:
   ```powershell
   ./scripts/setup-jarvis.ps1
   ```
3. **Launch Desktop App**:
   ```powershell
   cd jarvis-desktop
   npm install
   npm run tauri dev
   ```
4. **Verify Everything Locally**:
   ```powershell
   Remove-Item Env:JARVIS_BACKEND -ErrorAction SilentlyContinue
   python -B backend/run_suites.py
   python tools/check_no_source_pins.py
   python tools/check_position_pins.py
   python tools/check_defect_register.py
   python tools/check_claims.py
   python tools/check_docs_map.py
   python tools/check_event_names.py
   python tools/check_command_acl.py
   python tools/check_stale_twins.py
   ```

## Honest limits

This project's habit is to say what is not done. One of its own architecture
rules is that **nothing is claimed that is not true**. The short list:

- **The desktop installer is not published yet.** Settings → Updates says
  "Not set up yet", and the desktop app has to be built from source until
  somebody makes the update signing key (about ten minutes, in
  [`docs/INSTALL.md`](docs/INSTALL.md)). The update command falls back to
  building it.
- **The second graphics card is installed and measured, but its features are
  not.** It offers seven switches (longer conversations, pictures, background
  learning, browser control, the wiki builder, the study helper, referee
  suggestions); **every one is off, and each needs its own approval card**.
  That includes the camera in Jarvis Live, which stays off until the card is
  in and a photo test passes.
- **A third graphics card is planned, not installed.** The hardware sentences
  already work on one, two or three cards, but every three-card case in the
  tests is an injected reading, not a real machine. The big 30B model's
  28,672-token setting is the figure measured on two cards and is not raised
  for a third card until it is measured there.
- **PC help cannot show how much graphics memory each program uses on this
  PC.** The driver reports `[N/A]` for every process, so the answer lists
  which programs hold each card, says plainly that it cannot show the
  amounts, and caps the list. A genuinely hot card has not been produced in
  testing either - the heat classification is driven by injected readings,
  so it is honest arithmetic, not a measured throttle.
- **Three backend slices are built, tested, and not wired to anything you can
  use yet.** The local data sandbox, the file guardian and the study-deck
  additions (memory-strength radar, spoken-answer grader) have no route, chat
  tool, card or screen, so they change nothing you can do today; wiring them
  in is a separate decision. The sandbox's five-second and 64 KiB limits are
  hard, but **its memory is not capped on Windows**, so a badly behaved script
  can still make the PC struggle until the five seconds are up. The file
  guardian has only ever snapshotted temporary test folders, never a real
  project or vault.
- **Jarvis Live's new stop reasons are tested, not field-measured.** No device
  fix is claimed: the phone's classification and both sides' words are tested
  in the project's own harnesses without a phone, and the next attempt on the
  phone will show on its own end screen which refusal it hit.
- **Everyday chat has a small memory: about 4,096 tokens** of conversation.
  Longer talks get strange before they get long, and the bigger figures for
  what fits on each card are still worked out on paper — none of them is
  measured.
- **The wake word has not been tried on a real voice.** It was tested against
  made-up (synthesised) speech, 44 of 44 heard; what it does with a real
  person, a television or a phone's battery is unmeasured.
- **Some things are deliberately absent.** No always-on screen watching with a
  history (Recall-style). No phone calls for urgent alerts — a call would send
  private text to an outside voice company. No approve-all anywhere, and no
  control that clears the "text tried to rush you" warning. The phone does no
  speech-to-text, has no model catalogue to browse, and no deep config
  editing. Jarvis does not change Windows settings (Night light, dark mode,
  Focus Assist) — PC help only reads. The model's private reasoning is not
  shown, on purpose: it can quote your email and files.
- **Built, but never tried for real.** The chatbot website conversations, the
  chatbot API conversations, the comparison of several AIs, the
  customer-support chat and the hidden browser are each labelled "not yet
  tried for real" in the project's own notes. The job list says "nothing here
  has run on the owner's PC". The inbox tidy has been tried against a stand-in
  mail server, never a real mailbox. Nobody has listened to a v1.0 voice yet.
  The prompt coach and other newer pieces say in their own notes that nobody
  has measured how good their advice is.
- **The approval gap is narrowed, not closed.** The PC's own backend now asks
  Windows Hello for risky approvals, and stamps each real approval so a row
  written straight into the database does not count. A program written
  specifically to attack Jarvis can still get around it.
- **The updater's own log is not scrubbed.** `backend.log` is (passwords,
  keys and the pairing key are taken out), but `jarvis-desktop.log` is not, and
  neither catches everything — read one before sending it anywhere.
- **A token in Windows Credential Manager can still be read by any program
  running as you.** What changed is that it no longer sits on disk as readable
  text.
- **`Alt+Space` can lose the race at startup.** Every startup program asks for
  its shortcuts at once, so being present after a reboot is not the same as
  owning the key. The tray icon's "Show or hide the Jarvis bar" is the way in
  when that happens.
- **Do not run a downloaded OpenJarvis copy.** It writes into the same
  `%USERPROFILE%\.openjarvis\` folder as Jarvis.
- **`docs/INSTALL.md` → "Known rough edges"** is the fuller, live list. Read
  it before reporting a problem.

## License

Released under the **MIT License** — see [LICENSE](LICENSE), and
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) for every third-party part
and its own terms, including wake-word models that are non-commercial use only.
The build is non-commercial and sideloaded only (rule 5 above); the MIT licence
covers the code in this repository, not the parts it borrows.
