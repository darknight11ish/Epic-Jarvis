# Report 04 (audit), agent ad6e97de, 2026-09-29T08:25Z

> **What it was asked** (first 600 characters of the task): Repo /home/user/Epic-Jarvis at origin/main (79a36545). Do NOT edit files. Read CLAUDE.md (five non-negotiable rules + every dated owner decision) and docs/ARCHITECTURE.md §3, §4 (named ways out of the PC), §11. Then audit the code that landed on main in the last ~3 days (use `git log --since='4 days ago' --stat origin/main` and the merge commits for PRs #21-#28) against those rules: rule 1 (email/files/credentials/memory stay on local model; check every new outbound path: chatbot driver adapters, pairing, weather, MCP bridge, search providers, backups, notifications), rule 2 (no public tunnel;

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

RULES AUDIT of what landed on origin/main (79a36545), last ~4 days (713 commits, PRs #21-#28)

Bottom line: I found no break of the five rules and none of the standing bans. I found two small things worth the owner's attention, and a few limits on what I could check. I dropped every finding I could not prove with a file and line.

How I checked. I read CLAUDE.md, JARVIS-TODAY.md, ARCHITECTURE §4 and §11, then read the actual code (Python backend, phone Kotlin, desktop Rust/JS, manifest, Cargo, CI). "Verified" below means I read the code and quoted it. I could not compile anything (no Android or Windows build here).

## 1. Violations / bends, ranked (none is a rule break)

| # | Severity | What | Verdict |
|---|---|---|---|
| 1 | Low (docs gap) | The phone checks GitHub for a newer app version, ON by default. `jarvis-client/.../data/ClientSettings.kt:262` reads `prefs.getBoolean(KEY_UPDATE_CHECKS, true)`. The request is `net/UpdateCheck.kt` `URL = "https://api.github.com/repos/darknight11ish/Epic-Jarvis/releases/tags/client-latest"`. It sends nothing private (no token, no header, no Jarvis data), has a switch, and the code is careful (no redirects). But ARCHITECTURE §4 says "These lanes leave the machine. Nothing else may", and §4 has no row for it (its GitHub rows are tool-updates and "tell me when"). I found no owner decision for it (commit 6efeecfd, 2026-09-24). | NEEDS THE OWNER: either add a §4 row or make it off by default. It only reveals the phone's IP address and that Jarvis is installed. |
| 2 | Low (privacy hygiene, not a written rule) | Phone notifications the owner allows are stored in plain, unencrypted phone storage. `data/CapturedNotifications.kt` says "private SharedPreferences file", capped at 200 rows and 7 days. Chat history on the PC is encrypted, but these are not. It is app-private, and `allowBackup="false"` is set in the manifest. Nothing leaves the phone, so rule 1 holds. Redaction and the 7-day cap are as the owner's 2026-09-26 decision. | NEEDS THE OWNER (optional): encrypt it like the token (`TokenStore.kt` already uses the Android Keystore). |
| 3 | Very low (unverified impact) | `data/OwnNetwork.kt` `ownHost()` returns true for any single-word host name (`'.' !in h`). A name like `intranet` passes the "own network" check. On the phone the second check (`PhoneAddress`, `.ts.net` / `.nord` / localhost for plain http) covers it. I did not test the desktop's equivalent (`commands.rs` `own_network_host`). | Only a note. Probably intended (Tailscale short names). |

Nothing else rose to a finding.

## 2. Bends of a rule that are recorded as owner decisions (not violations)
- **Locked backup file** (`backend/jarvis_backup.py` docstring): bends rule 1 for one encrypted file. Checked and fine: AES-256-GCM with an Argon2id key from the recovery code, refuses to write anything unencrypted, and explicitly excludes the pairing token and every API key (they live in Credential Manager). The device registry is in a subfolder that the `*.json` glob never reaches, so a restore cannot bring back a removed key.
- **Chatbot driver (Gemini, 8 other websites, 6 API services, local second AI, compare, support chats)**: loosens rule 4 and the ARCHITECTURE §11 "ask each time" rule, as decided 2026-09-27/28. Guardrails I confirmed:
  - `jarvis_chatbot.py:934` `last_check` runs before every send. It blocks secrets, one-time codes, emails, phone numbers, addresses, never-send words, private topics and repeats of saved facts, and it fails closed.
  - Replies are marked outside text and never learned from.
  - The driver is not model-callable (no "chatbot" hit in `jarvis_agent.py`), so only the owner's app tap starts it.
  - Gate action `chatbot_session` is tier ask, risky (`outbound`), in `HARD_LIMITS` and `MUST_ASK`.
  - Every adapter says "No stealth plug-in" (there is no captcha solver or bot-detection dodging in code).
- **Support chats** (`support_chat`, `support_offer`): both ask, both risky and outbound. The code has a bot-question detector (`jarvis_support.py:404`) that hands the question to the owner. The disclosure line is dropped as decided 2026-09-28.
- **Forget a time frame** (`memory_forget_range`): one card listing many items is an owner-recorded exception to "no bulk".
- **Compare (up to 3 AIs on one card, 4 on two)** (`jarvis_chatbot_compare.py:98`) and **one smart-home card for several devices**: recorded.
- **Plug-in programs (MCP)** (`jarvis_mcp.py:126`): `CARD_EVERY_START = False` (the card is asked when a plug-in is new or has changed, as decided). Every tool use always asks, because `jarvis_agent.py:6499` refuses when `outside_program` is set. Only stdio transport is accepted, so no network servers.
- **Talk-to-type on the PC** (`talk_type.rs`, `jarvis_speech.py:2161`): the words are worked out on the PC only, the PC refuses the clip while the switch is off, and turning it on raises a card.
- **Open-Meteo weather**: the card names the exact rounded position and applies to that position only (`jarvis_sky.py:61-65`, default `"weather": "off"`).

## 3. Checked and fine

**Rule 1 (private data stays local)**
- Every outbound host I found in the backend is either in §4 or reached only through a card: search providers, IMAP/SMTP, Google calendar link, Home Assistant, Open-Meteo, api.github.com, PyPI, crates.io, ntfy, the chatbot and API hosts, and news/page feeds.
- ntfy is used only by the gate's push and sends a "doorbell" text (`_safe_detail`). The "tell me when" alerts (`jarvis_tellme.py`) go on the local event bus, not to ntfy.
- DuckDuckGo search is pinned to `backend="duckduckgo"`.
- Second local AI refuses `-cloud` / `:cloud` models. `OLLAMA_NO_CLOUD=1` is set in `jarvis_second_card.py:1390` and `jarvis_profiles.py`.
- The desktop's vendored HUD page (`hud_bootstrap.js`) deletes the browser speech recogniser, because it uploads audio from outside the CSP. It also limits spoken replies to local voices, so Microsoft's online "Natural" voices cannot receive text. The phone's `Speaker.kt:545` excludes network voices too.
- Photo-to-reminder, screenshot reading and history import are on the PC. History import reads only the owner's own turns. Every fact from an imported chat waits for a yes.
- The desktop CSP `connect-src` is loopback only. There are no shell/fs/http/opener permissions in the capabilities JSONs.

**Rule 2 (no public tunnel, address allow-list)**
- Phone: `OwnNetwork.kt` and `PhoneAddress.kt` allow only `.ts.net`, `.nord`, own-network suffixes and private ranges, and the phone's plain-http domains are limited to those.
- Desktop: `commands.rs` `require_base_allowed` / `base_from` refuse a bad address and return an empty base, with no fallback to this PC. The desktop's own calls (`sidecar.rs`, `voice.rs`) go through `jarvis_headers`, which enforces this.
- Pairing is mesh-only: `jarvis_devices.py:1438` `claim` and `Pairing.kt` accept only `.ts.net` / `.nord`.
- The QR code is drawn in Rust with `qrcodegen`, and the phone reads it with zxing. No online QR service, no Google ML Kit.
- I found no ngrok, cloudflared or funnel code.

**Rule 3 (API keys)**
- Chatbot API keys are in Windows Credential Manager only, one entry per service. There is no environment variable and no route to save one (`jarvis_chatbot_api.py:55-70, 360-400`).
- Each key is registered with `jarvis_scrub` and attached only to the preset's pinned https host, and `_request` re-checks `endpoint_problem` on every call.
- Redirects are refused. Errors never quote the provider's text.
- Search keys use the same store. HA, IMAP and the calendar link use `jarvis_token_store.resolve_secret`. The GitHub token is an environment variable, kept out of cards, audit and log.
- Device keys (`jdk1.`): the registry stores a SHA-256 only (`jarvis_devices.py` docstring), and `jarvis_scrub` knows the key's shape. The phone's key is Keystore-encrypted (`TokenStore.kt`).
- Grep of `Log.` / `println!` / `console.*` in the phone and desktop code found no token, key, secret or pairing-code logging. The one `eprintln!` (`devices.rs:412`) prints a fixed sentence plus an error.
- The chatbot money limit refuses use with a key but no limit ("NO LIMIT, NO CONVERSATION").

**Rule 4 (never auto-approve, stale stream, risky approvals)**
- Phone: `JarvisRuntime.decide` (~line 3130) calls `decisionBlocker` and `LinkWords.decisionBlocked` (stale or disconnected) itself. `actionBlocker()` is used 81 times. Every new mutation I read has it: chatbot start/limits/resume, compare start, support start/answer, live start/extend/carry-on, Solve-it-here start/input, third-card assign, forget-range, projects, focus. Stop, Undo and "End" are deliberately never held.
- The approval widget and the notification only Deny (`ApprovalWidget.kt`, `EventService.kt`). Approve opens the app.
- Signed approvals: `MainActivity.approveItem` runs the risky path (fingerprint signature) before `decideDetached`.
- Desktop: `link().stale` refusals appear in `commands.rs`, `backup.rs`, `asks_first.rs`, `devices.rs`, and the `brain/chatbot.rs`, `support.rs`, `forget_range.rs`, `projects.rs` and `goals.rs` command files. Talk-to-type also checks a live stream before opening the microphone.
- Backend: `PC_ONLY_ACTIONS` (`jarvis_owner_check.py:125`) holds loosen, enable-tool, restore-backup, pair-device, unretire-key and register-approval-key (always Windows Hello, from this PC only). `is_risky` fails safe: an unclassified action or missing `risk` counts as risky.
- New gate actions have `_RISK` entries in their patches: `chatbot_session`, `support_chat`, `support_offer`, `run_plan` (all outbound, so risky), `memory_forget_range` (reversible "no", so risky), `pair_device`, `phone_notifications_read`, `second_card_third_assign`, `app_merge_change`. All are in `HARD_LIMITS` / `MUST_ASK` and set to `"ask"` in `backend/rebuilt/jarvis-framework.toml`. Actions with no toml line (`run_plan`, `phone_notifications_read`) fall to `unknown_action_tier = "ask"`.
- `propose_plan`, `send_email`, `draft_email`, `control_computer`, `control_phone`, `home_control` and `shell_exec` are in `NEEDS_A_PERSON` (`jarvis_agent.py:1654`), so an auto/notify tier is never enough. The plan card's dispatcher does the real per-tool gate check on every step (`test_agent_plan_wiring.py`, per CLAUDE.md).
- No inbox-tidy gate action exists anywhere in the code (correct: "not built yet").
- App merge (`jarvis_apps.py:_decide`) refuses unless the gate answered tier ask AND a person said yes.

**Rule 5 (non-commercial, sideloaded)**
- No Play, Store, fastlane or winget publishing in `.github/workflows`. The maker is `darknight11ish` in `Cargo.toml`.
- New components are credited in THIRD-PARTY-NOTICES.txt: qrcodegen, zxing, GeoNames, Smart Turn, Silero, Pocket TTS, sherpa-onnx, Kokoro, TalkingHead, Handy, microWakeWord, LoCoMo. colibri is not listed, but `jarvis_big_model.py` says "No colibri code was copied" (it only talks to `coli serve` on 127.0.0.1), so no notice is due.
- Desktop `tauri-plugin-updater` has an empty `pubkey`, so the auto-update stays off. It has been there since 2026-09-14 and §10 records it.

**Standing bans**
- The phone has no speech-to-text: `JarvisRecognitionServiceStub.kt` only returns errors. Smart Turn on the phone (`voice/SmartTurn.kt`, `OrtTurnModel`) uses Whisper-style audio features only to detect a pause, not to transcribe, and it is the owner's decision of 2026-09-28. Words are worked out on the PC.
- No model catalogue and no memory graph on the phone. The only "graph" hits are a disclaimer and a note-folder setting. Nothing edits `jarvis-framework.toml` from the phone (`NoteCapture.kt` only tells the owner to edit it on the PC).
- No control clears a rush latch or approves in bulk. `widgets.rs:559-563` explicitly tests that `approve_all` and `clear_latch` are refused. `InboxScreen.kt:56` says "There is no control that clears a rush latch."
- `X-Jarvis-Client: hud`: the phone's `authed()` (`JarvisApi.kt:319`) sets it and the pairing POST sets it (`:604-620`). The desktop's `jarvis_headers` (`commands.rs:1634`) sets it, and all `.post`/`.get` calls I saw use it. The only exception is the GitHub update check (finding 1), which is not a Jarvis request.
- Token never logged (see rule 3).

**Off by default, confirmed in code**
- Plan card: `jarvis_plan.enabled()` (`jarvis_plan.py:392`) needs a real `tool_eval_results.json` with at least 90% multi-step and zero carried injections. No such file is committed. Because the results path is relative to the module's own folder (`_results_path`), it also fails closed on a PC where the backend lives elsewhere.
- Phone notifications (`jarvis_phone_notifications.py:195-209` defaults to off, with a card to turn on). Humour (`jarvis_manner.py:87` `HUMOR_DEFAULT = False`). "I heard you" sound (phone `ClientSettings.kt:92` false, desktop `voice-flow.js:274` needs `"on"`). Weather and sky (`jarvis_sky.py:284`). Live camera (`jarvis_live.py`: false until the 12 GB card is in and a photo test passes). Third-card assign (default none, card to assign, `second_card_third_assign` in `MUST_ASK`). Talk-to-type (off until a card). Lights without a card (`lights_on()` fails to off). Cloud lanes (still none configured).

## 4. What I could not verify
- `jarvis_gate.py`, `jarvis_router.py` and the model-install handler live outside this repo (ARCHITECTURE §9), so I judged them only by the patches and by tests in this repo. In particular I could not confirm that `/api/models/install` refuses a typed `-cloud` model reference; `jarvis_hardware.py` does not mention it. Worth a quick check on the owner's real file.
- I did not build or run any Kotlin, Rust or PowerShell here. Everything is a code read.
- 713 commits is more than I could review line by line. I sampled by area (every new outbound path, every key handler, every new gate action, every new phone/desktop mutation) rather than diffing all files, so a defect in code outside those paths is not ruled out.

Key files: /home/user/Epic-Jarvis/CLAUDE.md, /home/user/Epic-Jarvis/docs/ARCHITECTURE.md (§4 at line 613), /home/user/Epic-Jarvis/backend/jarvis_chatbot.py, jarvis_chatbot_api.py, jarvis_devices.py, jarvis_owner_check.py, jarvis_asks_first.py, jarvis_agent.py, jarvis_plan.py, jarvis_backup.py, jarvis_mcp.py, /home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/net/UpdateCheck.kt, data/ClientSettings.kt, data/CapturedNotifications.kt, data/OwnNetwork.kt, JarvisRuntime.kt.
