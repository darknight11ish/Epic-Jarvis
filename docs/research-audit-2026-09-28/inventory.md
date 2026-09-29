# Jarvis feature inventory (2026-09-28)

Read-only research. Base: `origin/main` 9cdb056. Branches read with `git show` / `git diff origin/main...`.

**Status:** MAIN = built on main · OFF = built on main but switched off / waiting on hardware or a measurement · BRANCH:res / BRANCH:cont / BRANCH:mascot / BRANCH:volta = built only on `claude/jarvis-ai-assistant-research-ff37vy` / `claude/jarvis-continuation-03kls1` / `claude/jarvis-3d-animal-mascot-8dr0tb` / `claude/peaceful-volta-tr1x60` · DESIGNED = design doc only · DECIDED = owner decided, not built.
**Apps:** PC = desktop app only · Phone = Android only · Both · BE = backend only (no app screen; reached by chat/voice or a PC command line).
**Ev:** c = checked in code this session (file exists / grep / route caller / parity tool) · d = from docs, CLAUDE.md or commit messages only.

`tools/check_parity.py` on main: desktop 128 routes, phone 108, ported 107, deliberately not ported 18, still to port 1 (`/api/retrieve`), phone-only 1 (`/api/notifications/watch`), "No undecided drift" (c).

---

## 1. Brain, models, routing

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| Local chat model | Qwen 3 8B as `jarvis-primary` in Ollama; every turn local by default | MAIN | Both | `backend/jarvis-primary.Modelfile`, `rebuilt/jarvis_router.py` | c |
| Tool-using chat loop | Model can call tools (local lane only), steps shown in Brain → Live | MAIN | Both | `backend/jarvis_agent.py` (25 tools in `TOOLS`) | c |
| Short tool list + `more_tools` | Only a few tool descriptions sent; more on request | MAIN | BE | `jarvis_agent.TOOL_GROUPS`, API §37 | c |
| Answered without the model | Timers, lists, "who are you", news, media, settings etc. by fixed rules | MAIN | Both | `backend/jarvis_quick.py` | c |
| Cloud lane, one question after a yes | Router only *offers* a cloud lane; yes carries newest words only, never private/tainted/picture turns | MAIN (no lane configured on owner's PC) | BE | `rebuilt/jarvis_router.py`, ARCH §11; `backend/README.md` ~l.2339 | c |
| "Try the cloud model" button | One-tap yes for one question, beside "Not now" | BRANCH:cont | Both (not widget) | `cloud-say-yes.patch`, `net/CloudOffer.kt` | c |
| `OLLAMA_NO_CLOUD=1` + Ollama cloud models treated as not local | Second lock behind rule 1 | MAIN | BE | backend README "Ollama's cloud models" | d |
| Model switch / install / roll back | Between installed models; install by typed name; each an approval card | MAIN | Both | `/api/models/switch`, `/install`; `BrainScreen.kt` `ModelsPlate` | c |
| Model catalogue browsing | Not on the phone by rule; desktop reads installed list only | MAIN (by rule, none) | — | CLAUDE.md | d |
| Brain → Model remembers last list offline | Cached last `/api/models` read shown with a dated banner | BRANCH:cont | Both | `models-cache.js`, `net/ModelsCache.kt` | c |
| Speed record per answer | "Jarvis got slow" numbers | MAIN | Both | `jarvis_speed.py`, `/api/models` `speed` | c |
| GPU offload note | How much of the model is off the card | MAIN | Both | `gpu-offload.patch` | c |
| Hardware screen + three setups | Detect cards, presets for any GPU, one PowerShell line, Measure | MAIN | Both (details PC) | `jarvis_hardware.py`, `jarvis_profiles.py`, API §20 | c |
| Second graphics card: 5 switches | Longer conversations, Pictures, Learning, Browser control, Wiki builder on 12 GB card | OFF (card not installed) | Both | `jarvis_second_card.py`, API §12 | c |
| One bigger model on both cards | Combined lane | OFF | Both | `jarvis_second_card.py` | c |
| Keep everyday chat on main card | Second-card setting | OFF | PC (Settings) | settings.html | c |
| Suggest the bigger model | Counts struggles/corrections; crisis turns excluded | MAIN | Both | `second-card-suggest.patch`, API §12.1 | c |
| Crisis thumbs-down not counted toward bigger model | Joins crisis flag and turn id | BRANCH:res (248227a) | BE | `second-card-suggest.patch` | d |
| Third graphics card lane | Move one 2nd-card feature onto a 3rd card, own card + own Ollama | BRANCH:cont, OFF | Both | `jarvis_second_card.py` `_THIRD_LANE` | c |
| Big model (slow) + Deep questions | colibri on CPU/SSD answers one careful question in background | OFF (switch, card) | Both | `jarvis_big_model.py`, `deep.js`, API §14 | c |
| Pictures in chat | Attach picture; text model can't see it → OCR words added | MAIN | Both | `vision.rs`, `ChatPicture.kt`, API §36 | c |
| Picture understanding (qwen2.5vl on 2nd card) | Pictures switch | OFF | Both | ARCH §10 | d |
| Making pictures on 12 GB card | Swapped in when asked | DECIDED | — | CLAUDE.md 2026-09-27 | c (absent) |
| Long-context lane on 12 GB card | Longer conversations first | OFF / DECIDED detail after measuring | Both | SECOND-CARD.md | d |
| Rules-first prompt on no-tool turns | Keeps Jarvis rules first when no tools enabled (fix) | BRANCH:volta | BE | `rules-first-relay.patch` | c |
| Skills: installed list, scan verdicts, remove | Brain → Skills | MAIN | Both | `/api/skills`, `/api/skills/decide` | c |
| Skill discovery ("offer a routine as a skill") | Notices repeated routine, offers once | MAIN (half: suggestions route has no app caller) | BE | `jarvis_skill_discovery.py`, `skill-suggest.patch` | c |
| Compute plan | GPU/VRAM plan read-only | MAIN | Both | `/api/compute` | c |

## 2. Memory & learning

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| Automatic learning (owner's own words only) | Facts saved without a per-fact yes | MAIN | Both | `jarvis_auto_learn.py`, API §19 | c |
| Sensitive topics wait for a yes | Health, money, secrets, others' private details | MAIN | Both | `jarvis_sensitive.py` | c |
| "Also remember sensitive topics automatically" | Setting, off; on = card | MAIN | Both | API §19.1 | c |
| Passwords/PINs/account/ID numbers always ask | Even with the setting on | MAIN | BE | `jarvis_sensitive.py` | d |
| Everyday facts about people save automatically, treated as normal | "my sister likes jazz" | MAIN | Both | CLAUDE 2026-09-26 | d |
| Background learning switch (on = card) | Learner on/off | MAIN | Both | `jarvis_learning_switch.py` | c |
| Memory review queue (accept/deny cards) | Proposals with injection flags, correction cards, retire cards | MAIN | Both | `jarvis_intake.py`, `/api/memory/pending` | c |
| "Saved automatically" list + Forget (are you sure) | Both apps | MAIN | Both | API §19.5 | c |
| "Erase the words" (+ "Also delete the chat it came from") | Wipes text for good, keeps dates | MAIN | Both (phone: auto list only) | `memory-erase.patch` | c |
| Always keep in mind (pinned facts, 1,200 chars) | Pin/unpin | MAIN | Both (phone pins from auto list) | `/api/memory/profile` | c |
| Between us (shared jokes, nicknames) | Owner's tap only; used in Warm manner | MAIN | Both | API §48 | c |
| "Used in this answer" / "Jarvis remembered N things" | Which facts an answer used, with Forget | MAIN | Both | `/api/memory/used`, `memory-used.js`, `MemoryUsed.kt` | c |
| Retrieval trace in HUD | Which facts an answer reached for | MAIN (desktop HUD only, "todo" for phone) | PC | `/api/retrieve` (check_parity "todo") | c |
| People and things (entities, aliases, "are these the same?" card) | Linking facts to names | MAIN | PC (by rule) | `memory-entities.patch`, `jarvis_entities.py` | c |
| Memory graph (Galaxy) | Visual graph | MAIN | PC (by rule) | `/api/graph`, brain.html `tab-galaxy` | c |
| Full fact list "What Jarvis knows about you" + filter, edit, export | Deep memory editing | MAIN | PC (by rule) | `/api/memory/edit`, `/export` | c |
| What did I believe on this date? | As-of view | MAIN | Both | `/api/memory/facts?known_at`, `MemoryAsOfPlate` | c |
| Past questions get past facts | Recall of facts that used to be true | MAIN | BE | `jarvis_past.py` | c |
| Real "true from" dates (bitemporal) | Older news never replaces newer | MAIN | BE | `bitemporal.patch`, API §34 | c |
| "Said again" counts | Repeated facts counted | MAIN | Both | API §34.1 | d |
| Memory re-ranker (MiniLM) | Re-rank top ~20 facts | OFF (env `JARVIS_MEMORY_RERANK`, until self-test shows it helps) | BE | `rebuilt/jarvis_memory.py`, MEMORY-SCOREBOARD | c |
| Re-ranker drops weak facts | Only if the PC's self-test shows it helps | DECIDED | — | CLAUDE 2026-09-27 | d |
| Memory self-test + learner test + scoreboard | `eval_memory.py`, `eval_learner.py`, scoreboard page | MAIN | BE | `docs/MEMORY-SCOREBOARD.md` | c |
| Search: fastembed bge-small + sqlite-vec + FTS5 | Hybrid recall | MAIN | BE | `rebuilt/jarvis_memory.py`, `jarvis_recall.py` | d |
| Right/wrong mark on answers + "retire this?" card | Feedback on facts | MAIN (counts route unused) | Both | `jarvis_feedback.py`, `/api/feedback/mark` | c |
| Correction phrases ("that's wrong") | Counted as corrections | MAIN | BE | CLAUDE re-check | d |
| Temporary chat | Nothing kept or learned | MAIN | Both (quickbar, not HUD) | API §4 | d |
| Games and role-play → temporary chat automatically | | MAIN | BE | `games-temporary.patch` | c |
| "Remember: ..." verbatim, "remember_off" | | MAIN | Both | API §4 | d |
| Chat history, encrypted on PC, with switch | Incl. voice transcripts | MAIN | Both | `jarvis_chat_log.py`, API §18 | c |
| History view + search box | Title-only filter of loaded list (not a word search) | MAIN | Both | `HistoryScreen.kt`, `brain.js` | c |
| Search owner's past chat *words* | Waits until memory 1-4 measured | DECIDED (waiting) | — | CLAUDE 2026-09-26 | d |
| Overnight memory tidy | Offer card only; switching on records the wish, runs nothing | DESIGNED/DECIDED (offer built) | Both (offer) | `rebuilt/jarvis_sleep.py`, ARCH §10 | d |
| Import old Claude/Gemini export into review queue | PC command | MAIN | BE | `backend/import_history.py` | c |
| Wiki builder | Documents → linked Obsidian pages by 2nd-card model | OFF | Both | `jarvis_wiki.py`, API §13 | c |
| Hide memory lists and chat history | Setting; phone blocks screenshots while on | MAIN | Both | `security-settings.js`, `Security.kt` | c |
| Memory counts ("What Jarvis remembers") | Shared words fixture | MAIN | Both (store path PC only) | `MemoryCounts.kt`, `memory-words.js` | c |
| Memory review team / ideas after 1-4 | | DECIDED | — | CLAUDE 2026-09-26 | d |

## 3. Voice

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| Push to talk / talk button | Clip recorded on device, words worked out on PC | MAIN | Both | `/api/voice/utterance`, `VoiceButton.kt` | c |
| Phone tap-to-talk, stops at a pause | Instead of only hold | DECIDED | Phone | CLAUDE (res) 2026-09-28 | c (absent) |
| "Hey Jarvis" wake word (openWakeWord) | On = card | MAIN | Both | `jarvis_wakeword.py`, `WakeSpotter.kt` | c |
| Newer detector (livekit-wakeword) | Candidate, no switch | OFF (bake-off) | BE | `jarvis_wakeword.py`, `jarvis_bakeoff.py` | c |
| Owner voice check (speaker verification) + stricter check | Before any words exist | MAIN | Both | `rebuilt/jarvis_voice.py`, API §16 | c |
| Train my voice (12 sentences, per mic, "someone else" check) | One card | MAIN | Both | `jarvis_voice_enroll.py`, `VoiceTrainingScreen.kt` | c |
| How strict / how often to repeat | Voice settings | MAIN | Both | settings.html "How strict" | c |
| Private answers asked by voice (memory / sensitive facts) | Kept on screen by default; setting allows aloud (card) | MAIN | Both | `private-speech.js`, `PrivateAloud.kt` | c |
| Hands-free trust ("Same as talk button" / "Only trust talk button") | Stricter immediate; looser = card | MAIN | Both | API §16 | c |
| Answers using web search/weather/home read aloud | Replaces "any tool keeps it on screen" | BRANCH:res (fefb41e) | Both | `test_private_aloud.py` | d |
| Screen answers after "Hey Jarvis" setting | `hands_free_screen`/`screen_aloud` | BRANCH:res | Both | `VoiceStrict.kt`, `voice-settings.js` | c |
| One "Hey Jarvis" heard by two devices answered once | Per-mic listening window | BRANCH:res (dfcd00f) | BE | commit msg | d |
| "Listening" sound after bare "Hey Jarvis" | Part of "I heard you" switch | DECIDED | Both | CLAUDE (res) | d |
| Silero VAD + Smart Turn ("finished or paused?") | Phone runs Smart Turn itself | MAIN | Both | `jarvis_turn.py`, `SmartTurn.kt` | c |
| Parakeet speech-to-text (PC only) | Client never does STT | MAIN | BE | `jarvis_speech.py` | c |
| Kokoro v0.19 TTS, 11 built-in voices, picker | No card | MAIN | Both | `jarvis_speech.py` l.1803, `jarvis_voices.py` | c |
| Kokoro v1.0 + "Hear it" samples | Voice saved by name | DECIDED | Both | CLAUDE (res) | c (absent) |
| Speaking speed Slower/Normal/Faster | | MAIN | Both | settings.html | c |
| Custom voices (ZipVoice, CPU) | Add/switch each a card; owner-like voice refused | MAIN | Both | `jarvis_voices.py`, API §15 | c |
| The better voice (F5-TTS on 2nd card) | | OFF | Both | `jarvis_f5_worker.py` | c |
| Pocket TTS (faster voice copying) | No switch, bake-off | OFF | BE | `jarvis_voices.py` | c |
| Voice bake-off tool | Measures candidates on owner's PC | MAIN | BE (PC tool) | `jarvis_bakeoff.py` | c |
| Spoken-style answers for voice turns | Short, no lists | MAIN | BE | `jarvis_agent.SPOKEN_NOTE` | d |
| Speak from first comma, one sentence ahead | | MAIN | Both | `speech-pieces.js`, `SpeechText.kt`, `SpeechAhead.kt` | c |
| "Stop" word + barge-in + echo cancelling | Interrupt by talking | MAIN | Both | `jarvis_stopword.py`, `barge-in.js`, `aec.rs` | c |
| "One moment." clip | When a tool starts | MAIN | Both | `/api/voice/moment` | c |
| "I heard you" sound (switch, off) | | MAIN | Both | API §17.5 | d |
| Keep listening after a question | Phone opens mic itself | MAIN | Both | API §17.6 | d |
| Tell the model it was interrupted | | MAIN | BE | API §17.7 | d |
| Spoken approval-card lines | Jarvis says a card is waiting | MAIN | Both | `jarvis_card_words.py`, `CardVoice.kt` | c |
| Timer said aloud when done | | MAIN | PC (§8 reason) | ARCH §8 | d |
| Phone as Android assistant (assist gesture) | No STT on phone | MAIN | Phone | `assistant/JarvisVoiceInteractionService.kt` | c |
| Phone wake-word service | Foreground listener | MAIN | Phone | `service/WakeWordService.kt` | c |
| Talk-to-type on PC | Hold key, speak, typed into front app; one card to switch on | DECIDED | PC | CLAUDE (res) 2026-09-27 | c (absent) |
| Jarvis Live (voice conversation + phone camera) | No wake word between turns; camera off until 12 GB photo test | DESIGNED | Both | `docs/LIVE-DESIGN.md` (res) | c (doc only) |
| Voice delay panel (`flow.summary`) | Only via command line | MAIN (no app screen) | BE | ARCH §8 | d |

## 4. Everyday tools

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| One scheduler: timers, alarms, reminders, to-do | Without the model; no card for one-off or plain repeats | MAIN | Both | `jarvis_schedule.py`, `jarvis_quick.py`, API §21 | c |
| Snooze, "cancel that", named lists | | MAIN | Both | API §21.9 | d |
| Coming up list, "Just went off" | | MAIN | Both | `coming-up.js`, `ComingUpPlate.kt` | c |
| Late alarm >10 min = silent "missed" notice | | MAIN | Both | `ScheduleNotifier.kt` `missedWords` | c |
| Ringing until seen (urgent alerts, alarms) | Phone notification | MAIN | Phone mainly | API §30.5 | d |
| "Also on my phone" | Hand alarm/event to phone's own Clock/Calendar | MAIN | Phone (§8) | `net/AlsoOnPhone.kt` | c |
| Standby schedule ("sleep mode") | Wakes only if schedule put it to sleep | MAIN | Both | `jarvis_standby_schedule.py` | c |
| Power: Active / Quiet / Standby | Set from apps | MAIN | Both | `jarvis_power_switch.py`, API §11 | c |
| Morning briefing | Count + senders (setting: count only), calendar, weather from HA, news; one card | MAIN | Both | `jarvis_briefing.py`, API §22 | c |
| "What did I miss?" | | MAIN | Both | API §22.9 | d |
| Back-off for offers | Not now → quiet 1/7/30 days | MAIN | BE | `jarvis_backoff.py` | c |
| News headlines (RSS/Atom) + "read me the news" | One card per feed; chat-only management | MAIN | BE (chat) | `jarvis_news.py`, API §46 | c |
| Tell me when (email sender, device state) | One card; match only notifies | MAIN | Both | `jarvis_tellme.py`, API §30 | c |
| Tell me when this page changes | One card per address, read-only | MAIN | BE/Both | API §30.3.1 | d |
| Instant email (IDLE) + "hasn't replied by ..." | | MAIN | BE | API §30.7 | d |
| Email read + one-time codes hidden | IMAP, read-only | MAIN | BE (tool) | `jarvis_email.py`, `jarvis_mail_mask.py` | c |
| Send email (one card per email, full text) | Tool off unless enabled | MAIN | Both (card, settings) | `jarvis_email_send.py`, API §26 | c |
| Save email draft (card every time) | Settings route has no screen | MAIN | Both (card) | `jarvis_email_draft.py`, API §40 | c |
| Inbox tidy by voice (archive/star/read/Trash, card + Undo) | | DECIDED | — | CLAUDE (res) 2026-09-28 | c (absent) |
| Web search: SearXNG default, DuckDuckGo, Exa, Tavily, Brave | Ships on (`tools.enabled=["web_search"]` in rebuilt toml) | MAIN | Both (keys PC only) | `jarvis_search.py`, API §23 | c |
| When a search asks first + "Ask before every web search" | | MAIN | Both | `asks-first.patch`, API §23.3 | c |
| Google Calendar read (CalDAV + private iCal link) | Read-only | MAIN | BE (tool) | `jarvis_calendar.py`, API §22.8 | c |
| Home Assistant read / control | Control per card | MAIN | BE (tool) | `jarvis_home.py` | c |
| Several devices on one card | Locks/doors/alarms/covers own card | MAIN | BE | `test_home_several.py` | c |
| Lights, plugs, fans without a card (setting, off) | | MAIN | Both | API §33 | d |
| Plain http only inside own networks (HA, calendar) | | MAIN | BE | `test_own_network_cases.py` | c |
| Notes search (Obsidian, Logseq, Joplin) | | MAIN | BE (tool) | `jarvis_notes.py` | c |
| Note capture `#log`/`#joplin`/`#obs`, Alt+Shift+N, widget buttons | After outside text → card | MAIN | Both | `jarvis_note_capture.py`, `NoteCapture.kt` | c |
| Folders Jarvis may look in (PDF, Word, Excel, PowerPoint) | `my_files` tool | MAIN | Both (adding folder PC) | `jarvis_documents.py`, API §35 | c |
| Bring in my Notion export | Imported = outside text | MAIN | PC | `/api/folders/import` | c |
| Words in a picture (Windows OCR) | Marked outside text | MAIN | BE | `jarvis_ocr.py`, API §36 | c |
| Music/video control ("pause", "next song") | No card, owner's words only | MAIN | BE (chat) | `jarvis_media.py`, API §47 | c |
| Focus sessions | Timer + Quiet, names distraction, report card (no streak) | MAIN | Both (watching PC only) | `jarvis_focus.py`, API §31 | c |
| Briefer during focus | | MAIN | BE | API §31.8 | d |
| Crisis help line (988, 911) | Never learned or counted | MAIN | BE | `jarvis_wellbeing.py`, API §38 | c |
| Calculator | Tool | MAIN | BE | `jarvis_agent` `calculator` | c |
| GitHub research / Watch topics | "Has someone built this?", watch list | MAIN | Both | `jarvis_research.py`, `/api/watch*` | c |
| "Where this came from" + quote check | Sources under an answer | MAIN | Both | `jarvis_sources.py`, API §55 | c |
| Things you can say / "What can you do?" | Fixed list bundled in apps | MAIN | Both | `jarvis_sayable.py`, API §41 | c |
| "Who are you?" fixed answer | | MAIN | BE | `jarvis_identity.py`, API §54 | c |
| Open / adjust any setting by voice or chat | | MAIN | Both | `jarvis_settings_registry.py`, API §58 | c |
| Projects (name, instructions, notes, benchmarks, charts, Shareable switch) | Brain on both apps; coding runs later | BRANCH:res | Both (folder/command PC) | `jarvis_projects.py`, API §61(res) | c |
| Jarvis writing code in Projects | After 12 GB card | DECIDED | — | CLAUDE (res) | d |
| Today page | Next / Waiting / Done today | DESIGNED (queued creativity #10) | — | `CUTTING-EDGE-...-round2-experience.md` §4 | d |
| Reading phone notifications (safe version) | Off; on = card; allow-list, SMS/banking blocked, codes redacted | BRANCH:cont | Phone (§8 row) | `PhoneNotificationListenerService.kt`, API §61(cont) | c |
| Feasibility audit's 31 small items | Many done (I97, I98, I114, I115, I125, I144...); rest queued | MAIN partial / DECIDED | — | `FEASIBILITY-AUDIT-2026-09-26.md` | d |

## 5. Agents, automation, screen control

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| Brain → Live steps | Tool starts/finishes (no private reasoning) | MAIN | Both | `step` event, `StepsPlate.kt` | c |
| Task controls: pause / stop / add a note | Notes need unlock under App lock | MAIN | Both | `jarvis_task_control.py`, API §11 | c |
| Stop everything | Alt+Shift+X on PC; button on phone | MAIN | Both | `jarvis_stop_all.py`, API §28 | c |
| Computer control (Windows UI, UFO-style plans) | `control_computer`, needs a person | MAIN (tool off unless enabled) | BE | `jarvis_ui_control.py`, `docs/UFO-SAFETY-DESIGN.md` | c |
| Phone control (tap around the paired phone) | `control_phone` | MAIN (off unless enabled) | BE | `jarvis_android_control.py` | c |
| Browser control (one tab, step by step) | `browser_control`; 2nd-card switch | MAIN/OFF | BE | `jarvis_browser_control.py` | c |
| Run shell / read files | `shell_exec`, `file_read` | MAIN (off unless enabled) | BE | `jarvis_agent.py` | c |
| MCP plug-in programs (local only, card per add/version change) | Reached via `more_tools` | MAIN | BE (settings file) | `jarvis_mcp.py`, API §37 | c |
| Background jobs + Undo shelf | Cancel, revert | MAIN | Both | `/api/jobs`, `/api/undo` (routes on owner's PC only) | c |
| Findings ("What Jarvis noticed on its own") | Initiative engine | MAIN | Phone list; PC HUD transient | `rebuilt/jarvis_initiative.py` | c |
| Digest / Attention (interruption) budget | | MAIN | Both | `/api/digest`, `attention.rs`, `InboxScreen.kt` | c |
| Tool & behaviour test suite | Multi-step + injection suites | MAIN | BE | `tools/tool_eval/` | c |
| Goals (plan the owner edits, weekly check-in, card per acting step) | | BRANCH:cont | Both | `jarvis_goals.py`, `goals.js`, `GoalsPlate.kt`, API §59(cont) | c |
| Plan card ("one card, several steps") | Wired as `propose_plan`/`run_plan`; unlocks only with passing `tool_eval_results.json`; no UI | BRANCH:cont, OFF | BE | `jarvis_plan.py`, `plan-gate.patch`, API §60(cont) | c |
| Talk to a chatbot for me (9 websites, 6 APIs, 2nd local AI) | One card per conversation; none tried for real | BRANCH:res | Both (sign-in/keys PC) | `jarvis_chatbot*.py`, API §60(res) | c |
| Ask several and compare | ≤3 chatbots one card, 4 on two | BRANCH:res | Both | `jarvis_chatbot_compare.py` | c |
| API money limit per service + hard stop (answer-length caps) | Unverified default price list | BRANCH:res | PC (CLI) | `jarvis_chatbot_api.py`, faa3be7 | c |
| Customer-support chats (details card, card per offer) | | DESIGNED | — | `docs/CHATBOT-DRIVER-DESIGN.md` (res) | d |
| Look at this / Watch with me (screen) | Rules only (steps 1-2): pause rules, never-look list; no Windows readers, route or screens | BRANCH:res (partial) | BE | `jarvis_screen.py`, `jarvis_front.py`, API §62(res) | c |
| Prompt-injection detector (Prompt Guard 2 vs guard-small, keep winner) | Adds a warning only | DECIDED | BE | CLAUDE (res) | c (absent) |
| Plan card switched on after multi-step safety tests | | DECIDED | — | CLAUDE 2026-09-27 | d |

## 6. Safety & approvals

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| One permission model, approval cards (auto/notify/ask) | Gate on owner's PC | MAIN | Both | ARCH §3 (`jarvis_gate.py` not in repo) | d |
| Never auto-approve; no approve-all; stale stream blocks acting | | MAIN | Both | `no-auto-approve.patch`, `commands.rs decide_approval` | c |
| One card on every screen; card words, titles, spoken lines | | MAIN | Both | `jarvis_card_words.py`, API §3 | c |
| Approval expiry + notice (how the card ended) | | MAIN | Both | `approval-expiry.patch`, `approval-notice.patch` | c |
| Windows Hello for risky PC approvals (backend itself) | Approval-gap step 1 | MAIN | PC | `jarvis_owner_check.py`, `owner-check.patch` | c |
| No lock, no risky approval | | MAIN | Both | owner-check / `BiometricGate.kt` | d |
| Phone Keystore key per risky approval (step 2) | With "more devices" | DECIDED | Phone | `APPROVAL-GAP-DESIGN.md` | d |
| QR pairing + short typed code + per-device keys | Card on PC first | DECIDED | Both | CLAUDE 2026-09-24 | c (absent) |
| Activity: past approvals | Title, outcome, when, device | MAIN | Both | `GateHistory.kt`, API §42 | c |
| What asks first page (make stricter; PC loosens short safe list with card + Hello) | | MAIN | Both (loosen PC) | `jarvis_asks_first.py`, API §32 | c |
| Offer a reading tool to the model from PC (card + Hello) | | MAIN | PC | `/api/asks_first/tools`, API §43 | c |
| What Jarvis can reach | Written by code | MAIN | Both | `jarvis_reach.py`, API §24 | c |
| Named ways out of the PC (egress) | | MAIN | BE | ARCH §4, `test_gate_egress.py` | c |
| Own-networks-only server address (desktop refuses & stops; phone mesh names only) | | MAIN | Both | `OwnNetwork.kt`, `PhoneAddress.kt` | c |
| App lock (desktop Hello / phone biometric), HUD & widget locked, task notes covered | | MAIN | Both | `lock.rs`, `Security.kt`, ARCH §8 | c |
| Screenshots blocked while locked / hiding lists | | MAIN | Phone (desktop undecided, owner's call) | `SecurityRules.blockScreenCapture` | c |
| Swipe to approve or deny (switch) | | BRANCH:res | Phone | `Security.swipeDecides` | d |
| Pairing token + account secrets in Credential Manager | | MAIN | PC | `jarvis_token_store.py`, `account_secrets.rs`, API §44 | c |
| Log scrub | Keys/tokens out of logs | MAIN | BE | `jarvis_scrub.py` | c |
| Outside-text / taint rule (notes after outside text ask) | | MAIN | BE | `jarvis_agent.py` | c |
| Prompt-injection tests (AgentDojo cases) | | MAIN | BE | `agentdojo_injections.json`, `test_injection_cases.py` | c |
| Paste guard | Masks pasted passwords before history | MAIN | BE | `jarvis_paste_guard.py`, API §50 | c |
| Private copy | Copied answer kept out of clipboard history/sync | MAIN | Both (different mechanisms) | `clipboard_privacy.rs`, `PrivateClipboard.kt` | c |
| Embedding guard, degrade filter, memory safety | | MAIN | BE | patches | c |

## 7. Desktop app UI (Tauri)

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| Jarvis bar (quickbar) | Chat, voice, cards, temporary chat, picture attach | MAIN | PC | `index.html`, `main.js` | c |
| HUD window | Backend's own page via Rust proxy; locked under App lock | MAIN | PC | `jarvis_hud.html`, `hud_proxy.rs` | c |
| Brain window tabs | Memory, History, Faculties, Work, Galaxy, Live, Trust, Watch | MAIN | PC | `brain.html` | c |
| Settings (Everyday / Rare / What Jarvis does) | ~40 sections | MAIN | PC | `settings.html` | c |
| Approval widget | Approve matches Jarvis bar's | MAIN | PC | `widget.html` | c |
| Floating face (Alt+Shift+F) | Always-on-top face, never clickable | MAIN | PC | `floating.html`, API §57 | c |
| Tray icon with Power row | | MAIN | PC | `tray.rs` | c |
| Global hotkeys (Shortcuts settings) | Clash wording fixed | MAIN | PC | `hotkeys.rs` | c |
| Faces window + face tuning + Portable output | 20 faces | MAIN | PC | `faces.html`, `jarvis-visual-spec.json` | c |
| 3-screen walkthrough | First run | MAIN | PC | `onboarding.html` | c |
| FAQ | | MAIN | Both | settings.html, `FaqScreen.kt` | c |
| Starts/stops backend, restart watchdog, hang/crash notes | | MAIN | PC | `sidecar.rs`, `crash_notes.rs` | c |
| Autostart, logs, "Show me where" | | MAIN | PC | `autostart.rs` | c |
| Windows toasts | | MAIN | PC | `winrt_toast.rs` | c |
| App updater | Wired; nothing published (no signing key) | OFF | PC | `update.rs`, ARCH §10 | c |
| Plain error words (shared list) | | MAIN | Both | `plain_errors.rs`, `PlainErrors.kt` | c |
| Themes follow system; HUD uses app theme | | MAIN | PC | `system_theme.rs`, `theme.css` | c |
| Markdown answers (_italic_ fixed) | | MAIN (+res fix) | PC | `markdown.js` | c |
| Check for tool updates | One card ever | MAIN | PC | `jarvis_tool_updates.py`, API §53 | c |
| Goals / Projects / Chatbot screens | | BRANCH:cont / res | PC | `goals.js`, `projects.js`, `chatbot.js` | c |
| Putting a card aside shows next waiting | | BRANCH:res (66bb9c4) | PC | commit | d |

## 8. Phone app UI (jarvis-client)

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| Home (face, chat, cards, Stop everything) | | MAIN | Phone | `HomeScreen.kt` | c |
| Brain screen (renamed from Mind) | Attention, jobs, memory review, wiki, as-of, models, 2nd card, deep, compute, skills, backend | MAIN | Phone | `BrainScreen.kt` | c |
| Inbox (brief, shelf, jobs) | | MAIN | Phone | `InboxScreen.kt` | c |
| Pairing screen (+ Show token on res) | | MAIN (+BRANCH:res) | Phone | `PairingScreen.kt`, `PairingKey.kt` | c |
| Readiness / Checks screen | Cleartext, notifications, Doze checks | MAIN | Phone | `PlatformReadiness.kt`, `ReadinessScreen.kt` | c |
| Settings / Appearance / Security / Voice / Voices / Voice check / Train | | MAIN | Phone | `ui/screens/*` | c |
| Face editor + phone layout settings | Per device, never synced | MAIN | Phone | `FaceEditor.kt`, `AppearanceStore.kt` | c |
| Approval widget (Review, no Approve) | | MAIN | Phone | `widget/ApprovalWidget.kt` | c |
| Quick-link widget (link state + Mic) | | MAIN | Phone | `widget/QuickLinkWidget.kt` | c |
| Quick-settings tile (link state, mute interruptions) | | MAIN | Phone | `service/LinkTileService.kt` | c |
| Share target (SEND text/picture) | Shared = outside text | MAIN | Phone | AndroidManifest SEND | c |
| App-icon shortcuts | | MAIN | Phone | `res/xml/shortcuts.xml` | c |
| Floating Jarvis (Bubble / Overlay) | Bubble may not show: no MessagingStyle | MAIN (half) | Phone | `FloatingAvatar.kt`, `WakeWordService.kt` l.625 | c |
| Event service, approval & schedule notifications, boot receiver | | MAIN | Phone | `service/*` | c |
| Smartwatch notifications setting | Off; on = card | MAIN | Phone | `/api/notifications/watch` | c |
| Haptic tick on releasing talk button | | MAIN | Phone | ARCH §8 | d |
| Crash screen / crash log | | MAIN | Phone | `CrashScreen.kt` | c |
| Update checker | | MAIN | Phone | `platform/UpdateChecker.kt` | c |
| Network-change reconnect, "Tailscale is off" line, keep-alive offer | | BRANCH:res | Phone | `NetworkWatch.kt`, `LinkWords.kt` | c |
| Goals / Projects / Chatbot plates, chatbot ongoing notification | | BRANCH:cont / res | Phone | `GoalsPlate.kt`, `ProjectsPlate.kt`, `ChatbotPlate.kt`, `ChatbotNotifier.kt` | c |
| Phone notifications plate | | BRANCH:cont | Phone | `PhoneNotificationsPlate.kt` | c |

## 9. Setup, ops, backup, preflight

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| apply-patches.ps1 (patches + shipped modules) | | MAIN | PC | `scripts/apply-patches.ps1` | c |
| Live preflight "N pass, N fail, N warn" | | MAIN | BE | `backend/selftest.py --preflight`, API §29 | c |
| Data health in preflight | Read-only, WARN never fix | MAIN | BE | `jarvis_data_health.py`, API §49 | c |
| Phone-reach preflight check | | BRANCH:res | BE | ddcd0c8 | d |
| Backups: one locked file, recovery code, restore with card + Hello | | MAIN | PC (phone status only) | `jarvis_backup.py`, API §45 | c |
| Accounts (IMAP, calendar link, HA token) into Credential Manager | | MAIN | PC | API §44 | c |
| Tool updates check | | MAIN | PC | API §53 | c |
| Patch history, CI, phone APK via `client-latest` | | MAIN | — | `tools/build_patch_history.py`, workflows | d |
| Quick start in INSTALL.md | | BRANCH:res | — | docs/INSTALL.md | d |
| Parity checker, command ACL checker, advisories check | | MAIN | — | `tools/check_*.py` | c |

## 10. Personality & faces

| Feature | What it is | Status | Apps | Key ref | Ev |
|---|---|---|---|---|---|
| Manner: Warm and brief / Plain | | MAIN | Both | `jarvis_manner.py`, API §27 | c |
| "From now on ..." applied at once with Undo | | MAIN | Both | API §27.4 | d |
| Humour switch (off) | Never on cards/errors/serious | MAIN | Both | API §27.5, settings.html "Humour" | c |
| 20 faces, shared visual spec, appearance sync | | MAIN | Both | `jarvis-visual-spec.json` (20 faces), `appearance.patch` | c |
| Faces keep state under App lock | | MAIN | Both | CLAUDE 2026-09-27 | d |
| Red panda, pygmy owl, sea otter faces | Shaders, both apps | BRANCH:mascot | Both | `jarvis-desktop/critters/*.sksl`, `CritterFaces.kt` | c |
| Voice follows the face | Built ON by default (`FACE_VOICE_DEFAULT = True`) | BRANCH:mascot | Both | `jarvis_voices.py` l.504, `face-voice.js` | c |
| Real lip-sync (Kokoro mouth track in WAV) | | BRANCH:mascot | Both | `jarvis_mouth.py`, `lipsync.js`, `LipSync.kt` | c |
| Offer animal voice once; switch starts off; otter not "Sky" (speaker 4) | | DECIDED (not applied on branch) | Both | CLAUDE (res) 2026-09-28 | c |
| Calm serious moments (no wave on approval, concerned on error, neutral in crisis) | Approval pose still "waves" in code | DECIDED | Both | mascot CLAUDE; `critter-pose.js` l.136 | c |
| Not connected = asleep + hollow ring; rising Zs on standby; "Still" option | | DECIDED | Both | mascot CLAUDE 2026-09-28 | c (not found) |
| Animal voices from Kokoro blends only, pass not-owner check | | DECIDED | BE | CLAUDE (res) | d |

---

## (a) One-sided features with no reason written in ARCHITECTURE §8 "One-sided on purpose"

Checked by grepping `docs/ARCHITECTURE.md` (whole file) for each.

- Phone quick-settings tile (`LinkTileService.kt`) - no row. (c)
- Phone quick-link home-screen widget (`QuickLinkWidget.kt`) - no row (only the approval widget is mentioned). (c)
- Phone share target (SEND intent) - no row. (c)
- Phone as Android's assistant app (ASSIST / VoiceInteractionService) - no row. (c)
- Phone Readiness/Checks screen and crash screen - no row (desktop has preflight + crash notes, listed as PC-only, but the phone's own versions are not). (c)
- Desktop HUD retrieval trace (`/api/retrieve`) - marked "todo" in `check_parity.py`, not in §8 or JARVIS-API. (c)
- Phone "Findings" list vs desktop HUD transient cards - HAS a row (not a gap). (c)
- Branch: phone "Show token", network reconnect - res branch adds a §8 row (ok). "Try the cloud model" off the widget - cont adds a row (ok). Phone notifications - cont adds a row (ok).
- Branch (res): the Look-at-this screen hotkeys row replaced; nothing to flag.

## (b) Decided but not built

1. QR pairing + typed code + per-device keys ("more devices"); phone Keystore half of the approval gap.
2. Talk-to-type on the PC (one card to switch on).
3. Inbox tidy by voice (archive/star/read/Trash; card + Undo).
4. Prompt-injection detector bake-off (Prompt Guard 2 vs guard-small).
5. Phone tap-to-talk stopping at a pause.
6. Kokoro v1.0 voice pack + "Hear it" samples (voice saved by name).
7. "Listening" sound after a bare "Hey Jarvis" (inside "I heard you").
8. Animal faces: offer voice once / switch starts off / otter off "Sky"; calm serious moments; hollow-ring asleep; rising Zs on standby; "Still" option.
9. 12 GB card: long-context lane details, making pictures, Projects code-writing, full chatbot driver (two-card version).
10. Memory: overnight tidy (offer only), re-ranker dropping weak facts (if measured), searching past chat words (waits), memory review team.
11. Plan card switched ON (after multi-step safety tests); its UI.
12. Customer-support chats (DESIGNED).
13. Jarvis Live (DESIGNED; camera off until 12 GB photo test).
14. Looking at the screen: Windows readers, route, app screens, badge (DESIGNED; rules only built on res).
15. Today page (DESIGNED/queued, not an owner decision in CLAUDE.md).
16. Remaining feasibility-audit small items; screenshot blocking on the desktop (owner's call, undecided).
17. Bubble mode's MessagingStyle redesign (written down, not built).

## (c) Half-built

- `/api/retrieve`: desktop HUD only, undocumented, phone "todo". (c)
- `/api/feedback/counts`: route exists, neither app shows it (API §6 table "not built"). (c)
- `/api/skills/suggestions`: route, no app caller; README: "Skill notes: counted, but nothing feeds them yet". (c)
- `/api/email/drafting`: settings route, no screen in either app (API §40.5). (c)
- `/api/news*`, `/api/media*`: routes with no app caller - by design (chat fast path), but no screen to see/remove feeds. (c)
- `/api/config`: in the Brain allow-list, no window asks; writes answer 501. (c)
- Floating Jarvis Bubble mode: shortcut added, `MessagingStyle` missing, so the bubble may never appear (`WakeWordService.kt` l.625 comment). (c)
- Overnight tidy: offer card and switch exist; switching on runs nothing. (d)
- Desktop updater: wired, nothing published. (c)
- Built-but-off without a switch: memory re-ranker (env var), livekit wake word, Pocket TTS - waiting on owner-PC measurements. (c)
- Second card (5 switches + combined), big model, F5 voice, wiki builder: built, OFF until hardware. (c)
- Branch cont: plan card wired but locked (no `tool_eval_results.json`), no UI; third card untested on hardware, its Playwright checks never executed; Goals calls no model. (c/d)
- Branch res: screen feature has a voice setting in both apps (`hands_free_screen`) but no way to look at the screen yet; chatbot driver never tried against real sites; money-limit price list unverified. (c/d)
- Branch mascot: owner's 2026-09-28 face decisions not applied (see (b)8). (c)

## Discrepancies with JARVIS-TODAY.md

1. Lists Projects and the chatbot driver under "Built" areas; relative to main they are BRANCH:res only (it does say so further down). (c)
2. Says the money-limit hard stop is "being built" on `studio-money-hardstop`; it is merged into the res branch (faa3be7, e337ff3). (c)
3. Says Jarvis Live is "being built" on `studio-live`; no such remote branch - only `docs/LIVE-DESIGN.md` exists. (c)
4. Lists the plan card both as "built and switched off" (cont) and under "Decided but not built yet". Code: built, wired, OFF. (c)
5. Lists "reading phone notifications (safe version)" as decided-not-built; it is built on cont (638464b). (c)
6. Its decided-not-built list omits inbox tidy by voice, the injection-detector bake-off, phone tap-to-talk, the listening sound, and the mascot 2026-09-28 decisions. (c)
7. "History search in the apps" is a title-only filter of the loaded list, not a search of chat words. (c)
8. Not in JARVIS-TODAY but worth knowing: main's CLAUDE.md (2026-09-27) says "Phone: allow home-network addresses", but main's code refuses them (`PhoneAddress.kt`); res branch's CLAUDE.md reverses the decision to match the code. (c)
9. API section numbers collide: res uses §60 = chatbot, §61 = Projects, §62 = screen; cont uses §59 = Goals, §60 = plan card, §61 = phone notifications. A merge will conflict. (c)
10. Mascot branch as of its last commit (05:13 UTC) still has `FACE_VOICE_DEFAULT = True` and the otter on speaker "4" - JARVIS-TODAY's note still holds. (c)
11. `origin/claude/jarvis-audit-competitors-vyqpt1` exists but is fully merged (0 commits ahead) - not missing work. (c)
