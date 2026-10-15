# Epic-Jarvis

**Your local-first, privacy-locked personal AI assistant for Windows 11 and Android.**

Epic-Jarvis combines a **Windows 11 Desktop Spotlight & Brain HUD** (`jarvis-desktop`, built with Tauri v2, Rust, and WebView2), a **Local Python Agent & Memory Backend** (`jarvis-backend`), and a **Native Android Companion App** (`jarvis-client`, built with Kotlin and Jetpack Compose). Your everyday conversations, memory, documents, voice, and personal data stay on your own hardware via **Ollama** and **ONNX Runtime**, with tightly budgeted, opt-in cloud escalation available when you want extra horsepower.

## The Four Non-Negotiable Guarantees

1. **Private by Architecture, Not Just Policy**: Anything touching your emails, local files, credentials, finances, or long-term memory is locked to your **local LLM** via automatic taint latches (`jarvis_gate.py`). Sensitive turns cannot leave your PC.
2. **Zero Public Tunnels**: Cross-device sync between your Windows 11 PC and your Android phone runs strictly over **localhost (`127.0.0.1`)**, **Tailscale**, or **NordVPN Meshnet**—never through public ingress tunnels (`ngrok`, Cloudflare Tunnel, or Tailscale Funnel).
3. **Fail-Closed Credential Vault & Scrubber**: Secrets live in a host-bound vault (`jarvis_vault.py`, backed by Windows Credential Manager) and are handled by name (`vault://...`). Values resolve only at the single outbound request header that authenticates with them and are scrubbed everywhere else (`jarvis_scrub.py`).
4. **Human-in-the-Loop Approval & 1-Click Undo**: Consequential actions follow **Plan → Describe → Gate → Run** (`jarvis_gate.py`). Approval cards never steal keyboard focus (so a stray `Enter` while typing can never auto-approve an action), wait up to 15 minutes, and record reversible before/after snapshots in `receipts.db` for **1-Click Undo** (`jarvis_receipts.py`).

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

## License

Released under the **MIT License**. See [LICENSE](LICENSE) and [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) for full third-party notices.
