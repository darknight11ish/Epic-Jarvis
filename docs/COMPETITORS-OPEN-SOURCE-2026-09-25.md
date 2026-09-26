# Competitive audit: open-source and local-first assistants compared with Jarvis (task #75)

> **Status, 2026-09-25 (added when this report was saved to `docs/`).**
> Built since the report, from its list: timers, reminders and the to-do
> list answered without the AI model (Home Assistant's design, no code
> copied); one shared scheduler; "keep listening after a question" and
> "tell the model it was interrupted" (voice work); tool descriptions 16%
> shorter (not yet OpenClaw's lean mode / Tool Search); "who is my sister"
> (names and aliases). Being built: sleep mode, the morning briefing, and
> Leon's back-off rule. Still open: lean mode / Tool Search, chat-history
> search in the apps, QR pairing with per-device keys, a setup wizard that
> checks a real tool call, testing QwenPaw's Flash models in
> `tools/tool_eval/`, and a second copy of the backend files that live only
> on the owner's PC. The paths to `scratchpad/` below were the auditor's
> temporary clones; they no longer exist.

I only read the Epic-Jarvis repo and changed nothing in it (HEAD `6d90068`, `git status` clean). I made shallow, blobless, sparse clones in `scratchpad/compete/os/` and deleted them all afterwards. That folder is empty and the disk has 9.5 GB free.

**How far to trust this report**
- **Code I read myself:** OpenClaw, Hermes Agent, Home Assistant core (the voice parts), Open WebUI, AnythingLLM, goose, Jan, Leon, letta-code and Row-Bot. I read the parts that mattered and give file references below.
- **README or docs only:** QwenPaw, ZeroClaw and LM Studio (LM Studio is closed source, and its website is blocked from here, so that part comes from web-search summaries).
- **Star counts:** from GitHub search on 2026-09-25. The GitHub API itself is blocked (403).
- **"Active" dates:** the date of the last commit on each project's default branch.
- **Not measured:** no speed or accuracy figure here was measured. Anything marked **(unverified)** I did not check against a source.

---

## 0. Who the competitors are now

| Project | Stars | Licence | Last commit | What it is now |
|---|---|---|---|---|
| **OpenClaw** (new, Nov 2025) | 390k | MIT | 2026-09-24 | The 2026 breakout. A personal agent: a server on the PC ("gateway"), phone apps, Telegram/WhatsApp and similar, cron jobs, 5,400+ add-on skills (that number is the community list's own claim) |
| **Hermes Agent** (Nous Research) | 249k | MIT | 2026-09-24 | A self-improving agent. Messaging apps, cron, voice, memory files the model writes itself |
| Open WebUI | 153k | BSD-3 + branding clause | 2026-09-21 | Local chat front end. It now also has automations, a calendar, notifications and tool approval |
| Home Assistant core | 91k | Apache-2.0 | 2026-09-24 | Assist voice pipeline, timers, satellites. `wyoming-satellite` is archived; its replacement is `OHF-Voice/linux-voice-assistant` (632★) |
| openinterpreter | 68k | not rechecked | 2026-09-23 | **Now a Rust coding agent.** No longer a general assistant |
| AnythingLLM | 66k | MIT | 2026-09-24 | Local chat and document search, agents, scheduled jobs, automatic memory |
| goose (moved to `aaif-goose/goose`) | 55k | Apache-2.0 | 2026-09-24 | An agent for coding and general tasks |
| LibreChat (moved to `LibreChat-AI/LibreChat`) | 45k | MIT | 2026-09-23 | A multi-user chat app |
| Jan | 45k | Apache-2.0 | 2026-09-24 | A local chat app. It now has memory notes the model writes |
| Khoj | 37k | AGPL-3.0 | **2026-08-01** | Slowing down. PEERS.md says its cloud closed in April 2026, but its README still links the cloud app **(unverified either way)** |
| QwenPaw (new, Feb 2026) | 35k | Apache-2.0 | active | A personal agent aimed at Chinese chat apps. Ships its own small "Flash" 2B/4B/9B models "trained for agent tasks" (their claim) |
| ZeroClaw (new, Feb 2026) | 33k | MIT or Apache | active | A Rust agent runtime. By default medium-risk actions need approval and high-risk ones are blocked; a YOLO mode (approve everything) exists |
| Letta / letta-code | 25k / 3.4k | Apache-2.0 | 09-10 / 09-24 | Agents that rewrite their own memory. Letta's cloud is the default |
| Leon | 17.5k | MIT | 2026-09-24 | A 2.0 "developer preview" rewrite: agent modes, layered memory, a "proactive pulse" |
| LM Studio | closed (the `lms` CLI has 5.3k★) | proprietary | – | A local model app. Tool calls get a confirm dialog with "always allow". **LM Link** (Feb 2026) is private remote access built on Tailscale. Details from web search only (unverified) |
| OpenVoiceOS | ~300 per repo | Apache-2.0 | 2026-09-18 | A voice OS, small and alpha-stage |
| **Row-Bot** (new, Mar 2026) | 1.5k | Apache-2.0 | 2026-09-24 | **The closest match to Jarvis in spirit:** local-first, Ollama, local speech-to-text plus Kokoro, Tailscale Serve, a knowledge graph, workflows, a Windows overlay |

---

## 1. Scorecard

"Ahead / even / behind" means Jarvis compared with that project. **NfJ** means "not for Jarvis": copying it would break a rule.

| Area | Jarvis (evidence) | Competitors (evidence) | Verdict |
|---|---|---|---|
| **Conversation** | A local 8B with tools. Cloud only after a yes for that one question (ARCHITECTURE §11). The 16 tool descriptions take about 3,000 words of the model's working memory (RESEARCH-2026-09-24 §6). History cannot be searched (JARVIS-API §18.3 routes: list, get and delete only) | OpenClaw, Hermes, goose and LibreChat default to cloud frontier models. Hermes searches past sessions (FTS5). OpenClaw has a "lean mode" plus "Tool Search", which hide big tool descriptions from small models (`docs/gateway/local-models.md`) | **Behind** cloud-first projects on raw intelligence (chasing that is NfJ, rule 1). **Even** with Jan, LM Studio and Open WebUI on Ollama. **Behind** on history search and tool trimming |
| **Memory** | Saves automatically only from the owner's own live words. Sensitive topics wait for a card. Two dates on every fact. Forget, and "Erase the words". Pinned facts landed in `4fe0887` (ARCHITECTURE §5) | Everyone else lets the model write its own memory, or extracts it with no review. AnythingLLM also reads the **assistant's** replies (`server/jobs/helpers/memory-extraction-utils.js:114-128`). Row-Bot runs extraction every 2 h over chats (`memory_extraction.py`) and marks "needs_review" only afterwards (`memory_evolution.py:19`). Open WebUI gives the model add/update/delete tools (`tools/builtin.py:923-1053`). Hermes gives the model add/replace/remove on MEMORY.md (limit 2,200 characters). OpenClaw writes Markdown files and consolidates them in a background "dreaming" pass. Jan's model writes .md notes (`tauri-plugin-agent-tools/src/memory.rs`) | **Ahead of all.** Behind Row-Bot only on an entity graph and on "recall traces" (showing which memories an answer used). Both are already queued |
| **Voice** | "Hey Jarvis", an **owner voice check** (unique), Smart Turn, speech-to-text and speech on the PC, speaking from the first comma. First sound in about 2.5–4 s (an estimate, §11). Barge-in (interrupting by talking) is on the backend only. The follow-up window opens only after a bare "Hey Jarvis" (`backend/jarvis_speech.py:721-735`) | HA starts speaking once 60 characters have arrived (`assist_pipeline/default_pipeline.py:66, 644-696`). It plays an **acknowledge beep instead of a full reply** for local commands (lines 804-815, 1109-1114). It **keeps listening when its reply ends in "?"** (`conversation/chat_log.py:377-393`). Hermes has full-duplex barge-in and **tells the model it was interrupted** (`tools/tts_streaming.py:44-56`). OpenClaw's phone voice uses the phone's speech service or cloud realtime. None of them checks whose voice it is (I grepped HA, OpenClaw, Hermes and Row-Bot) | **Ahead** on privacy and safety. **Behind** HA and Hermes on conversational polish. Speed: behind cloud realtime (NfJ); against local pipelines, unmeasured |
| **Actions + safety** | One card per action, no approve-all. Tiers are fixed code, never the model's choice. Outside text raises the tier. Nothing acts on a stale link (ARCHITECTURE §2-3) | OpenClaw's command runner defaults to `security: full`, `ask: off` (`docs/tools/exec-approvals.md`), and has "allow-always" grants **including for cron jobs**. goose's default is still `Auto` (`crates/goose-provider-types/src/goose_mode.rs:23-25`). Open WebUI's `tool_approval_mode` defaults to `'full'`, i.e. no asking (`utils/middleware.py:3438`). AnythingLLM's scheduled jobs still auto-approve everything (`server/jobs/run-scheduled-job.js:76-83`). Hermes asks only for commands on a "dangerous" pattern list, and has YOLO, session grants and an LLM "guardian" (`tools/approval.py`); its cron default is deny (`approval_context.py:281-293`). Row-Bot defaults to Ask, but "Auto" is one click per thread and read-only actions are always allowed (`approval_policy.py`). Jan's default is ReadOnly | **Ahead of all** on safety. **Behind** OpenClaw and Hermes on breadth: sub-agents, code execution, many tools. OpenClaw's own docs say small models with tools reading untrusted content are "too high" a risk (`docs/gateway/security/prompt-injection.md`). An 8B is exactly that case, which is why Jarvis's cards are the right design |
| **Proactive / time-based** | **Nothing fires.** The initiative engine's "check list is EMPTY" (`backend/rebuilt/jarvis_initiative.py:29`). No timers or reminders | OpenClaw has automations, plus a heartbeat that runs a model turn every 30 min by default (`docs/gateway/heartbeat.md`). Hermes has cron. Open WebUI has repeating automations with a minimum interval (`routers/automations.py:69-86`). HA has timers (`intent/timers.py:841-1107`). Leon's pulse backs off each time the owner declines (`pulse-manager.ts:114-120`). LibreChat, AnythingLLM and Row-Bot all have schedules | **Behind everyone.** The biggest gap |
| **Integrations** | Home Assistant; calendar and email read-only; Obsidian, Logseq and Joplin; GitHub search; phone over adb; controlling Windows programs | OpenClaw: a skill hub, MCP, Gmail, Google Workspace. Hermes: MCP. HA: thousands of integrations **(count not checked)** | **Behind** on breadth. Jarvis's HA bridge makes smart-home devices roughly **even**. The MCP bridge in the queue closes part of the rest |
| **Privacy / control** | Three named ways out of the PC, each enforced in code. The desktop app's allow-list reaches only its own PC (loopback). No tunnel. History encrypted (§4, §18) | OpenClaw offers a public Tailscale Funnel (`docs/gateway/config-gateway.md:159`): **NfJ**. Hermes, QwenPaw and ZeroClaw connect through Telegram/WhatsApp and similar: **NfJ**. Letta's cloud is the default. Jan is local. LM Studio is local but closed | **Ahead of all** |
| **Setup / ease** | Built from source. The backend lives on the owner's PC, not in the repo. The earlier research found 15 places a beginner gets stuck | OpenClaw: an `openclaw onboard` wizard, signed Windows installers, and a hardware-aware model setup that checks a real tool call works before switching (`docs/gateway/local-models.md`). Hermes: a one-line PowerShell install. Row-Bot: a bundled installer. Jan and LM Studio: one-click | **Behind all** |
| **Mobile / multi-device** | A native Android app: approvals with fingerprint, widgets, assistant role, wake word, voice check. Pairing means typing a 43-character token | OpenClaw's Android app pairs with a QR code or setup code plus a confirm step. The setup token expires in 10 min, and the phone's commands stay off until the pairing is approved (`docs/gateway/pairing.md:85-93, 193-198`). HA has a companion app. LM Link is "a couple clicks" over Tailscale (unverified). Row-Bot has a web app with one-time invites. Hermes reaches the phone via Telegram or Termux | **Ahead** of Jan, LM Studio, Open WebUI, Leon and Khoj. **Behind** OpenClaw and HA on how easy pairing is |
| **Reliability / polish** | Many tests, but much is "not watched on real hardware" (the Windows toast, the second card, the big model). The updater is inert with no signing key. **The backend has "no second copy"** (§9) | Big user bases, signed releases. OpenClaw also has 8.6k open issues | **Behind** on proven-in-use. **Ahead** on test discipline |
| **Community / ecosystem** | One owner | Huge (OpenClaw's skill hub, Hermes plugins) | **Behind, by design.** Not worth chasing. Borrow through MCP and Home Assistant, carefully |

---

## 2. Where Jarvis is really ahead, and when a technical user would pick something else

**Ahead, with evidence:**
1. **Approvals.** Of the projects I read, only Jarvis has no approve-all and forces a card on every acting tool call. Everyone else defaults to auto-approving, uses a pattern list, or offers "always allow". The detail is in the scorecard row above.
2. **Memory safety.** No other project restricts automatic learning to the owner's own live words. AnythingLLM and Row-Bot learn from the assistant's replies too. Nobody else has two dates on a fact plus "Erase the words".
3. **The voice check.** No competitor checks that the voice belongs to the owner before acting.
4. **Egress and tunnels.** Every big newcomer (OpenClaw, Hermes, QwenPaw, ZeroClaw) is built around messaging relays. Jarvis's "nothing leaves the PC unless one of three named ways allows it" is unique.

**When a technical user would choose a competitor today:**
- **Reminders, scheduled briefings, "message me when X" →** OpenClaw or Hermes, accepting cloud models and weaker defaults.
- **A polished local chat with document search →** Open WebUI, AnythingLLM, Jan or LM Studio.
- **Voice around the house →** HA Assist with a Voice PE speaker.
- **A coding agent →** goose, openinterpreter or letta-code.
- **"Install it in 5 minutes" →** any of them.

---

## 3. The queue

### Verdict on each item

**Memory lane**
- Pinned facts: done in `4fe0887`. Hermes (MEMORY.md, 2,200-character limit) and OpenClaw (USER.md) prove the idea. **Strengthens an advantage.**
- "Who is my sister" (a names-and-aliases layer): **strengthens** memory quality. Row-Bot has an entity graph. Medium priority.
- Temporary chat + "used in this answer" with Forget: **closes a gap and strengthens an advantage.** Cheap. High.
- Overnight tidy: **matters little yet**, because automatic learning only started on 09-24 and there are few facts. When it is built, reuse Leon's back-off (see §4).
- Later ideas (true-from dates, counting repeats, a reranker): **matter little** for now.

**Graphics lane**
- Any-GPU support with 3 presets per hardware case: **over-invested.** There is one owner with known hardware (ARCHITECTURE §1), and `jarvis_second_card.py` already detects the second card. This is building for users who do not exist. It is the owner's call, since VIDEO-BRIEF lists it as "planned".
- Docker option: **over-invested, and possibly against a decision already taken.** ARCHITECTURE §11 says "Sandbox: Git worktrees, not Docker". If it means running the backend in Docker on Windows, that needs WSL2 with the graphics card, and OpenClaw's docs warn about a WSL2 + Ollama crash loop (`local-models.md`). **I could not tell from the queue which of the two is meant. Please say which.**
- Model advice that "learns the owner's choices": **matters little, and is risky.** "Learning" which tasks go to the cloud drifts toward a standing grant. §11 says ask each time. Keep it advice only.
- Real mouse + headless browser + vision clicking: **matters little until the second card.** It is a large attack surface, and an 8–9B model is unreliable at it.

**Voice lane**
- Barge-in in both apps, "One moment.", the "I heard you" sound: **closes a real gap.** HA has an acknowledge beep, Hermes has barge-in. High.
- Sleep mode: medium. Its schedule should be one use of the scheduler below, not a second scheduler.

**Small fixes lane**
- CI screenshot job, branch list, workflow updates: **matter little** to the owner.
- The 4 gate fixes and the scrubber: **strengthen an advantage.** Do them.
- MCP bridge: **closes a real gap** (ecosystem), but only if every MCP call goes through the gate as tier `ask` and the model never decides its own tier. goose's trust in MCP's `read_only_hint` is the thing to refuse (PEERS.md).
- The 2 script skills: I have no evidence either way.

**Security audit, then "more devices"**
- The audit **protects the lead.** Keep it.
- QR pairing with per-device keys: **closes a real gap** (OpenClaw and LM Link). High.

**Everyday abilities (queued after the lanes)**
- Timers, reminders, alarms, to-do, morning briefing, scheduled tasks: **the biggest gap.** Move to the top.
- Web search + weather: **closes a gap.** Every peer has it.
- Calendar events + email drafts: **closes a gap.** Medium.

**Local-AI extras**
- Voice memos to Obsidian: cheap, and uses what Jarvis already does well.
- "Ask my documents": a gap, but context is tight on 8 GB, so better after the second card.
- Quick text helper and "tidy my files": **matter little.** Tidying files also acts on files, which needs care.

**Other queued items**
- First-run setup: "Start Jarvis for me" is **high value and small.** The full checklist is medium.
- The second-card items: waiting for the card is correct.
- The "scaling" final audit: **matters little** for one owner.

### Missing things these projects treat as standard
1. **Follow-up listening when Jarvis asks a question** (HA's `continue_conversation`). Jarvis only reopens the microphone after a bare "Hey Jarvis".
2. **Telling the model it was interrupted** (Hermes).
3. **One scheduler shared by everything.** Reminders, briefings, the sleep schedule, the overnight tidy and watches all need one. Build it once, into the initiative engine and digest, as ARCHITECTURE §12 asks, rather than one scheduler per feature.
4. **Hiding tool descriptions from the 8B until needed** (OpenClaw's lean mode / Tool Search). Every new everyday ability adds tool text to a context that is already tight.
5. **Searching chat history in the apps**, owner-initiated. Nothing goes into the model, so it fits §5.
6. **A signing key, so the installer and updater work.** The owner generates it once (`jarvis-desktop/README.md`).
7. **(Not a competitor feature, but every competitor has it:) the whole backend under version control.** §9 says there is no second copy of 26 modules. Every competitor keeps its whole source in git. This is the biggest reliability risk I found. A private repo is the owner's call.

### Proposed top 10, in order
1. **Timers, reminders, alarms and to-do, with a fast path that skips the model.** The biggest gap, and it costs almost nothing on the graphics card.
2. **One scheduler, plus scheduled tasks and a morning briefing.** Each run may only read; anything that acts raises its own card. It fills the empty initiative engine, and sleep mode and the tidy reuse it.
3. **The voice lane, as queued, plus follow-up listening and the "interrupted" note.** This is where HA and Hermes feel better today.
4. **QR pairing with per-device keys, plus "Start Jarvis for me".** These remove the worst setup pains (the 43-character token, starting the backend by hand).
5. **Temporary chat, plus "used in this answer" with Forget.** Cheap, and it widens the memory lead.
6. **The security audit, the 4 gate fixes and the scrubber.** They protect the one thing no competitor has.
7. **Web search and weather, one approved question at a time.** Every peer has it. Waiting on the owner's choice of search provider.
8. **Trim or hide tool descriptions for the 8B.** It keeps items 1, 2 and 7 from crowding out the conversation.
9. **Calendar events and email drafts, never sent.**
10. **"Who is my sister"** (the names-and-aliases layer).

Next after these: voice memos to Obsidian; the MCP bridge through the gate; the full setup checklist; history search. Leave "ask my documents" and vision clicking for the second card. Park the any-GPU presets, Docker, model advice, file tidying and the text helper.

---

## 4. Top 5 "copy this" items (licences checked)

1. **Keep listening after a question** (HA, Apache-2.0).
   - Source: `homeassistant/components/conversation/chat_log.py` `continue_conversation` (lines ~377-393: the reply ends in "?", or the Greek and Chinese question marks), used in `assist_pipeline/default_pipeline.py:836`.
   - For Jarvis: open the existing follow-up window in `backend/jarvis_speech.py` (~720-735) when the spoken reply ends in a question. The owner voice check still runs on the follow-up clip. **S.**
2. **Fast path for simple commands, timers, and an acknowledge sound** (HA, Apache-2.0).
   - Sources: `prefer_local_intents` in `default_pipeline.py` (~752); the handlers in `intent/timers.py:841-1107` (start, cancel, add time, take time off, pause, resume, status); the "acknowledge instead of speaking" logic in `default_pipeline.py:804-815, 1109-1114`.
   - The `acknowledge.mp3` sound's own licence is not checked. **M.**
3. **Back off when the owner says no** (Leon, MIT).
   - Source: `server/src/core/pulse-manager.ts:106-126`.
   - How it works: at most 6 things waiting at once; no nudges within 2 minutes of an active conversation; each "no" silences that idea for 1 day, then 7, then 30. Similar ideas are matched by a fingerprint.
   - For Jarvis: use it for briefings, "still true?" cards and the initiative engine, so Jarvis never re-asks what the owner declined. Copy the design into Python. **S–M.**
4. **Tell the model it was interrupted** (Hermes, MIT).
   - Source: `tools/tts_streaming.py:44-56` (`SPEECH_INTERRUPTED_NOTE`, `mark_speech_interrupted` / `take_speech_interrupted`).
   - Jarvis must add the note through `jarvis_intake.jarvis_turn()`, so the learner never learns it (ARCHITECTURE §5). **S.**
5. **Tool Search / lean mode for a small model** (OpenClaw, MIT).
   - Source: `docs/gateway/local-models.md`, "Local model lean mode". It removes the largest tools and defers the others behind `tool_search` / `tool_describe` / `tool_call`.
   - For Jarvis: keep the card on the real call, and never let a search result pick a tier. **M.**

**Also worth reading (it confirms the queued pairing design):** OpenClaw's pairing. The setup token expires in 10 min, the phone's commands stay off until the pairing is approved on the server, and a valid code opens a confirm screen (`docs/gateway/pairing.md`, `docs/platforms/android.md`; MIT). Combine it with goose's code alphabet, as already planned.

**One model to test, not adopt:** QwenPaw's own "Flash" 4B and 9B models are claimed to be trained for agent tasks. They could be tried in `tools/tool_eval/`. **Model licence and quality are unverified.**

---

## A question for the owner

The queue has a "Docker option" in the graphics lane. Jarvis already decided on git worktrees, not Docker, for sandboxing (ARCHITECTURE §11). Running the backend in Docker on Windows would mean WSL2 with the graphics card, which OpenClaw's docs warn can crash-loop with Ollama.
- **Drop it for now** (recommended). One owner, one known PC.
- **Keep it, but say what it is for** (sandbox or packaging), so it can be checked against that decision.

Sources (web searches, for LM Studio only):
- [MCP in LM Studio (blog)](https://lmstudio.ai/blog/lmstudio-v0.3.17)
- [Use MCP Servers | LM Studio](https://lmstudio.ai/docs/app/mcp)
- [LM Link, Tailscale blog](https://tailscale.com/blog/lm-link-remote-llm-access)
- [LM Link, MarkTechPost](https://www.marktechpost.com/2026/02/25/tailscale-and-lm-studio-introduce-lm-link-to-provide-encrypted-point-to-point-access-to-your-private-gpu-hardware-assets/)
