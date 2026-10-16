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
4. **Human-in-the-loop approval & 1-click undo**: consequential actions follow **Plan → Describe → Gate → Run** (`jarvis_gate.py`). Approval cards never steal keyboard focus (so a stray `Enter` while typing can never auto-approve an action), wait up to 15 minutes, and record reversible before/after snapshots in `receipts.db` for **1-click undo** (`jarvis_receipts.py`).

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
| **Projects, Finance & Learning** | `coding` and `life` project workspaces with benchmarks, SHA-256 deduplicated bank CSV spending, real-money retirement projections, and **FSRS v6** (`fsrs==6.3.2`) flashcards. | `jarvis_projects.py`, `jarvis_spending.py`, `jarvis_retirement.py`, `jarvis_decks.py` |
| **Desktop, Browser & Phone Tools** | Opt-in CDP Accessibility-Tree browser driver, Windows UI Automation (`uiautomation`), ADB Android control, Docker management, and local SearXNG web search. | `jarvis_browser_control.py`, `jarvis_ui_control.py`, `jarvis_android_control.py` |

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

### 3. Dual-GPU Local AI, Opt-In Uncensored Models & Spend-Capped Cloud Lanes
* **Hardware-Aware Local Inference**: Separates your display GPU (e.g., 8 GB RTX 2080 Super running Windows 11 DWM + WebView2) from your dedicated headless AI GPU (e.g., 12 GB RTX 2060 running `Qwen 3.5 9B` or `Qwen 3 8B` in Ollama), with automatic prefix warming (`warm_prefix()`) on wake.
* **On-Disk Opt-In Models (`jarvis_optin_models.py`)**: Switch to local uncensored/abliterated GGUF models already on your drive without triggering any external downloads.
* **Smart Cloud Escalation with Whole-Cent Spend Caps (`jarvis_router.py`, `jarvis_auto_router.py`, `jarvis_chatbot_api.py`)**: Escalates complex, untainted coding or research turns to `jarvis-escalate` / `jarvis-critic`, extracts `reasoning_content` fallbacks automatically, and records every cent against your monthly cap (`jarvis_chatbot_api.money_check()`).

### 4. Verify-First Voice Pipeline
* **Speaker Verification Before Transcription (`jarvis_speech.py`)**: Every voice clip is verified against your voiceprint (**CAM++** for everyday speed, **TitaNet-Large** for strict verification, plus **WeSpeaker**) *before* speech-to-text runs. Unverified audio is never transcribed.
* **Local STT, TTS & Wake Word**: Uses **Silero VAD**, **openWakeWord** (`hey_jarvis` + custom `stop_head.bin`), **NeMo Parakeet TDT 0.6B** via `sherpa-onnx`, and **Kokoro-82M** (54 voices with lip-sync timing) plus **ZipVoice**, **F5-TTS**, and **Pocket TTS** for custom voice cloning (**Pocket TTS** is built and pinned but not switched on yet).

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
  and Undo all happen at once, with no card.
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
├── backend/            # 194 modules shipped whole (184 twins + 10 rebuilt), 143 patches & 328 test suites - measured 2026-10-15 on main at 6db0df06
├── jarvis-desktop/     # Windows 11 Tauri v2 (Rust + WebView2) Spotlight & HUD application
├── jarvis-client/      # Native Android companion app (Kotlin + Jetpack Compose, minSdk 33)
├── plugins/            # Dynamic plugin loader (loader/) & drop-in plugins (ready/)
├── tokens/             # W3C DTCG design tokens compiled to Desktop CSS & Android Compose
├── contract/           # Shared pairing words (pair-words.txt)
├── docker/searxng/     # Local privacy-preserving SearXNG metasearch container setup
├── scripts/            # PowerShell setup, update, backup, & patch-stack management scripts
├── tools/              # Static verifiers, code generators, & architectural audit checkers
└── docs/               # 387 design docs, API reference (JARVIS-API.md) & decision logs - measured 2026-10-15
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
