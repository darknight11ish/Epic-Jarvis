# What Jarvis already is (read this before researching anything)

Every studio agent reads this first. It exists so no agent spends an hour
on the web finding something Jarvis already has, or re-reading a project an
earlier report already covered. **Looking for a newer version, a better
option or an update to something listed here is welcome; rediscovering it
is not.** When in doubt, `grep -ril <topic> docs backend jarvis-desktop/src
jarvis-client` before searching the web.

Snapshot: 2026-09-27. The code is the truth; if this page disagrees with
it, say so in your report.

## The hardware Jarvis is built for: one OR two graphics cards

- **One card works fully.** Today that is an RTX 2080 Super, 8 GB, Turing
  (compute capability 7.5: no FP8, no bf16 tensor cores, no FlashAttention
  2). The chat model, and nothing else big, lives on it.
- **A second card is being added:** an RTX 2060, 12 GB. It is the "second
  lane" - long conversations, pictures, the learner, voice copying, and
  anything that needs a bigger or second model. Features MAY require two
  cards, as long as they say so and a one-card PC still works without them.
  Nothing that depends on the second card is switched on until it is
  installed and measured (`docs/SECOND-CARD.md`, `docs/MODEL-TOPOLOGY.md`,
  `docs/BIG-MODEL.md`, `docs/HARDWARE-PROFILES.md`).
- Processor: Ryzen 3900X, 12 cores, mostly idle while the card thinks.
  Windows 11. Ollama runs the models.
- **Every suggestion should say which it needs: one card, two cards, or
  either** - and what it costs in graphics memory on each.

## Built (by area, with where to look)

**Brain and routing** - Ollama, `jarvis-primary` (Qwen 3 8B, Modelfile in
`backend/`). `jarvis_router.py`: local by default. **Cloud lanes exist in
the code, one question at a time after the owner's yes** (ARCHITECTURE §11;
"Try the cloud model" in both apps on the continuation branch) - **but no
lane is configured on the owner's PC**: the lane list comes from
`litellm-proxy.yaml`, which `backend/README.md` (~line 2339) says does not
exist there, so every turn is local. Talking to an outside AI through its
API is designed in `docs/CHATBOT-DRIVER-DESIGN.md`; the owner chose Gemini's website instead, and "Talk to a chatbot for me" (the driver core, `/api/chatbot/*` routes and both apps' screens, one card per conversation) is built but reaches no chatbot yet - the Gemini adapter is not built (JARVIS-API §60). A cloud turn carries only the owner's newest words, never private,
tainted or picture turns (ARCHITECTURE §4). Big-model switch across both
cards (`jarvis_big_model.py`). Simple commands answered without the model
(`jarvis_quick.py`). Short tool list with more on request; MCP bridge for
local plug-ins (`jarvis_mcp.py`). Tool tests: `tools/tool_eval/`.

**Memory** - facts learned automatically from the owner's own words, two
dates per fact, Forget and "Erase the words", pinned facts ("Always keep in
mind"), people and aliases, "Used in this answer", temporary chat. Search:
fastembed bge-small-en-v1.5 + sqlite-vec + FTS5/bm25, a MiniLM re-ranker
(off until measured). Self-tests: `backend/eval_memory.py`,
`backend/eval_learner.py`, `docs/MEMORY-SCOREBOARD.md`. Encrypted chat
history on the PC with History search in the apps.

**Voice** (all speech work happens on the PC; the phone never does
speech-to-text) - "Hey Jarvis" (openWakeWord; livekit-wakeword candidate),
the owner voice check before any words exist, Silero VAD, Smart Turn v3.2,
Parakeet speech-to-text (sherpa-onnx), Kokoro v0.19 text-to-speech (11
voices, `speaker` setting), custom voices (ZipVoice on the processor, F5 on
the second card; Pocket TTS built, off), speaking from the first comma,
spoken-style answers, "stop" and barge-in, "One moment", "I heard you".
Details: `backend/jarvis_speech.py`, `jarvis_voices.py`, `docs/WAKE-WORD.md`.

**Everyday tools** - timers, alarms, reminders, to-do lists, one shared
scheduler; morning briefing; "tell me when" (email, devices, web pages);
email read, drafts, send (one card per email); web search (SearXNG default,
DuckDuckGo, Exa, Tavily, Brave); Google Calendar read-only; Home Assistant;
folders and documents (PDF, Word, Excel, PowerPoint, Notion export); notes
(Obsidian, Logseq, Joplin); screenshot text reading (Windows OCR); music
and video control; focus sessions; Windows UI control plans
(`jarvis_ui_control.py`, `docs/UFO-SAFETY-DESIGN.md`); backups with a
recovery code; live preflight check; "stop everything" hotkey; Projects
(2026-09-28: projects, notes, benchmarks with charts, in Brain on both
apps - `jarvis_projects.py`, `docs/PROJECTS-DESIGN.md`; running tests and
Jarvis writing code are later steps).

**Safety** - one permission model and approval cards (ARCHITECTURE §3),
named ways out of the PC (§4), Windows Hello for risky approvals, App lock,
own-networks-only addresses, prompt-injection tests (AgentDojo cases),
"What asks first" page.

**Apps** - desktop: Tauri 2 (`jarvis-desktop/`), HUD, Brain, Settings,
widget, floating face, 20 faces plus three animals - red panda, pygmy owl,
sea otter - with "voice follows the face" (`docs/CRITTERS.md`, on the
mascot branch until merged). Phone: `jarvis-client/` (Compose):
widgets, quick tile, share target, assistant role (no speech-to-text),
"Also on my phone", floating Jarvis.

## Already researched - read the report, don't redo it

| Topic | Read first |
|---|---|
| Closed-source competitors | `docs/COMPETITORS-COMMERCIAL-2026-09-25.md`, `COMPETITORS-MUSE-2026-09-25.md`, `COMPARISON.md` |
| Open-source competitors | `docs/COMPETITORS-OPEN-SOURCE-2026-09-25.md`, `PEERS.md` |
| Models, engine, cards | `docs/CUTTING-EDGE-2026-09-26-engine.md`, `MODEL-TOPOLOGY.md`, `SECOND-CARD.md`, `BIG-MODEL.md` |
| Voice and vision | `docs/CUTTING-EDGE-2026-09-26-voice-vision.md`, `WAKE-WORD.md` |
| Memory | `docs/MEMORY-RESEARCH-2026-09-26.md`, `MEMORY-REVIEW-2026-09-27.md` |
| Everything else in the cutting-edge rounds | `docs/CUTTING-EDGE-2026-09-26-*.md` |
| Bugs, UI, ease of use, security | `docs/BUG-AUDIT-*`, `UI-AUDIT-*`, `EASE-OF-USE-AUDIT-2026-09-27.md`, `SECURITY-PRIVACY-DEPS-AUDIT-2026-09-27.md` |
| The studio review of 2026-09-27 | `docs/STUDIO-REVIEW-2026-09-27.md` (when written) |

Already weighed and rejected, with reasons in those reports: unstructured
(telemetry), docling (PyTorch, revisit on 12 GB), RapidOCR (downloads from
modelscope.cn), APScheduler (duplicates the scheduler), LlamaFirewall,
python-spake2, Android Auto and a Wear OS app (Google services), Moonshine
and Parakeet Realtime EOU (speech-to-text before the voice check),
full-duplex voice models (skip the voice check and cards), GPL audio tools
(Rubber Band, Pedalboard, Praat, SoX).

## Built on other branches, not merged yet (check before building)

- **Goals** (backend, phone and desktop screens) and **"one card, several
  steps" - the plan card, built and switched off** - on
  `claude/jarvis-continuation-03kls1`.
- **Three animal faces and "voice follows the face"** - on
  `claude/jarvis-3d-animal-mascot-8dr0tb`. The owner's 2026-09-28 decision
  (offer the voice once, switch off by default, the otter not on "Sky") was
  not yet applied there as of 2026-09-28 02:07 UTC. That branch also has
  **real lip-sync**: the animals' mouths follow Jarvis's voice through a
  mouth track carried in the WAV, on both apps (fixes the studio's finding
  that the desktop mouth ran on a made-up rhythm).
- On this branch (`claude/jarvis-ai-assistant-research-ff37vy`): the
  chatbot driver core (`jarvis_chatbot.py`, API §60) and Projects steps 1-2
  (`jarvis_projects.py`, API §61).

## Decided but not built yet (don't propose these as new)

QR pairing with per-device keys; talk-to-type on the PC (one card to switch
on); reading phone notifications (safe version); the Today page; the plan
card; Kokoro v1.0 and a voice picker with samples; animal voices; the
12 GB card's long-context lane; the memory re-ranker bake-off and overnight
tidy; the feasibility audit's small items. The owner's full list of
decisions is in `CLAUDE.md`.
