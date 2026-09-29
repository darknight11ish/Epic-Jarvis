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
API is designed in `docs/CHATBOT-DRIVER-DESIGN.md`; the owner chose Gemini's website instead, and "Talk to a chatbot for me" is built (JARVIS-API §87; one card per conversation; the driver core `jarvis_chatbot.py`, `/api/chatbot/*` routes and both apps' screens) and reaches: nine chatbot websites in a visible window with a spare account each (the old "driven openly, nothing that hides it" rule was reversed by the owner on 2026-09-29: the headless browser runs with stealth on and the visible browser is a plain real browser, the visible browser stays the default, Jarvis still never solves a captcha) (Gemini, ChatGPT, Claude, Copilot, Perplexity, DeepSeek, Grok, Le Chat, Meta AI; shared base `jarvis_chatbot_web.py`), six services by API key (`jarvis_chatbot_api.py`, OpenAI-style: OpenAI, DeepSeek, Mistral, xAI, OpenRouter, Groq), and a second local AI on the PC (`jarvis_chatbot_local.py`). None is tried against the real sites yet. "Ask several and compare" is built too (`jarvis_chatbot_compare.py`, one card, one summary; up to 3 chatbots on one card, 4 on two - confirmed by the owner). The API services have a monthly money limit each, set on the PC (`py -3 jarvis_chatbot_api.py limit|price|spent`; an estimate from an UNVERIFIED default price list; no limit = not used; JARVIS-API §87.4.1). Customer-support chats are built too (`jarvis_support.py` + `jarvis_support_widget.py`, JARVIS-API §65; Groupon first, a typed help page for any other company; ONE card listing every detail Jarvis may give, ONE card per offer, "are you a bot?" and identity checks handed to the owner, no opening AI line; kept in the encrypted history) - not yet tried against Groupon's real site. **"Solve it here"** (2026-09-28, `jarvis_handoff.py`, JARVIS-API §87.8): a conversation or support chat paused at a captcha, sign-in or "unusual activity" page alerts the phone, which can show a live picture of that one PC browser window and pass the owner's taps and typing to it - only while paused there, never saved; the desktop shows the same alert. A cloud turn carries only the owner's newest words, never private,
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
history on the PC with History search in the apps (words searched on the PC
for the screen only, §71 - no index). **After the chat audit (2026-09-28,
JARVIS-API §18.6, both apps):** every History row has a kind (chat, live,
support, chatbot, compare; no "imported" - §85's import only proposes
facts) and an empty `project` column; "Show" filters by kind; "Continue
this chat" carries a chat or Live session on in the Jarvis bar / on Home
(same conversation id, newest kept messages that fit, taint carried); the
whole current conversation is a scrolling thread; a new conversation after
30 quiet minutes; "Earlier chats" links; chatbot chats and comparisons kept
(outside text, never learned from); crisis chats titled "A difficult
moment"; support records never auto-deleted and unticked in Forget a time
frame; the HUD's chat box opens the Jarvis bar. Not built, proposals only:
rename, pin, archive, branching, edit-and-resend, wider word search.
**"Forget a time frame"**
(2026-09-28, `jarvis_forget_range.py`, JARVIS-API §64, both apps; merged): a checked list of the facts saved
and chats from some days, ONE card (`memory_forget_range`), forgotten as
Forget does, 10 minutes of Undo; also by voice ("forget what you learned
last week" fills in the list - never removes anything).

**Voice** (all speech work happens on the PC; the phone never does
speech-to-text) - "Hey Jarvis" (openWakeWord; livekit-wakeword candidate),
the owner voice check before any words exist, Silero VAD, Smart Turn v3.2,
Parakeet speech-to-text (sherpa-onnx), Kokoro text-to-speech (v0.19's
voices, or v1.0's - a 350 MB one-line install, pinned in
`jarvis_kokoro.py`; the choice is saved by NAME, a **Hear it** button on
every voice in both apps, British voices asked for British English on v1.0;
**Ashby and Clara**, two blended voices made for Jarvis by one owner-run line
into a pinned copy of the pack's voice file, checked against the owner's voice
print, never for an animal; JARVIS-API §94, §94.7), custom voices (ZipVoice on the processor, F5 on
the second card; Pocket TTS built, off), speaking from the first comma,
spoken-style answers, "stop" and barge-in, "One moment", "I heard you". **Jarvis Live** (2026-09-28,
`jarvis_live.py`, JARVIS-API §63, `docs/LIVE-DESIGN.md`): a back-and-forth
conversation started and ended by the owner, both apps (badge and tray on the
PC, Live screen and notification on the phone), the voice check on every
clip, cards pause it, Mic off, calls pause it, side talk ignored and not
kept in history, tap buttons, more time after a crisis turn, the
`hands_free_live` and (PC only) `live_end` settings, one "Interrupting
Jarvis" setting for Live and ordinary voice, a Home strip and an app-icon
shortcut on the phone, Brain's "Now" tab (renamed from "Live"); the camera
is built OFF until the 12 GB card passes `jarvis_live_photo_test.py`.
Reviewed and fixed 2026-09-28 (`docs/studio-2026-09-28/live-review-*.md`).
**Live extras** (2026-09-28, branch `studio-captcha-live-extras`): a PC
hotkey (off until picked, Alt+Shift+L suggested), and on the phone a Quick
Settings tile, the headset button (press = stop talking, hold = mic off/on,
never approves), "Live ended - Resume" for 10 minutes, a Bluetooth headset
microphone preferred, "Talk about this in Live" from Share, and the phone's
own "End Live when" on Security (`voice/LiveExtras.kt`, JARVIS-API 63.4).
Details: `backend/jarvis_speech.py`, `jarvis_voices.py`, `docs/WAKE-WORD.md`.

**Everyday tools** - timers, alarms, reminders, to-do lists, one shared
scheduler; morning briefing; "tell me when" (email, devices, web pages);
email read, drafts, send (one card per email), tidy by voice (archive, star, mark read, Trash: one card listing every email, Undo 10 min, no permanent delete; built, untried on a real mailbox); web search (SearXNG default,
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
sea otter - with "voice follows the face" and lip-sync (`docs/CRITTERS.md`,
merged into `main` by PR #20 and into this branch). Phone: `jarvis-client/` (Compose):
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
- **Three animal faces and "voice follows the face"** - merged into `main`
  (PR #20) and into this branch. The owner's 2026-09-28 decision (offer the
  voice once, switch off by default, the otter not on "Sky") was NOT applied
  there as of 2026-09-28 10:30 UTC (`FACE_VOICE_DEFAULT = True`, the otter
  still speaker "4"); the owner asked the mascot session to fix it. That branch also has
  **real lip-sync**: the animals' mouths follow Jarvis's voice through a
  mouth track carried in the WAV, timed by Kokoro itself per sentence, on both apps (fixes the studio's finding
  that the desktop mouth ran on a made-up rhythm).
- On this branch (`claude/jarvis-ai-assistant-research-ff37vy`): the
  chatbot driver (core, websites, API services, second local AI; API §87),
  customer-support chats (`jarvis_support.py`, API §65),
  Projects steps 1-2 (`jarvis_projects.py`, API §88), the phone's
  "Swipe to approve or deny" switch, and **"Look at this" / "Watch with me"**
  (2026-09-29, API §62 and §96; `jarvis_screen.py`, `jarvis_screen_win.py`,
  `screen.patch`): on the PC the Look at this key, the bar's Watch button, an
  always-on-top badge, a tray row and a Never look at list; on the phone the
  assistant gesture (words only, off by default, Security switch "Let Jarvis
  read this phone's screen"), "Watch this phone with me" (Android screen
  sharing, one picture per question, needs Usage access) and the PC's
  watching shown on Home with Stop. Words only on one graphics card - no model
  is shown a picture. The Windows readers and the phone's Android parts have
  not run on a real machine yet. The voice setting "Answers about your screen
  after "Hey Jarvis"" (`hands_free_screen`) is in both apps. **Screen safety**
  (2026-09-29, API §62.13; `jarvis_secrets.py`, `jarvis_secret_rules.py`,
  `jarvis_picture.py`): anything that looks like a key, token, password or card
  number is hidden (`[hidden]`, and painted solid black in a picture) before a
  look's words or a picture are used - the PC's and the phone's alike; the
  PC's picture is taken with every Never look at window, private browser
  window and Jarvis window painted black; a private browser window in front is
  a pause; the text reader runs inside Jarvis (pywinrt) with word positions.
  Not run on a real PC yet. **Pictures the owner attaches to a chat are cleaned
  the same way** (2026-09-29, "Yes, clean them too"; `jarvis_chat_picture.py`,
  JARVIS-API §36): before any model sees one, secrets are painted solid black;
  nothing to hide - it goes on untouched; one that cannot be checked is
  withheld and the answer says so.
- **Third graphics card: its own lane, off by default** - on
  `claude/jarvis-continuation-03kls1` (2026-09-28, 5cc47a9c): a third
  NVIDIA card is detected, and one of the five second-card features can be
  moved onto it with its own approval card (`second_card_third_assign`); a
  third copy of Ollama on its own port. The owner asked that session for
  it; research here still plans for one or two cards unless told otherwise.
- **Reading phone notifications (the safe version)** - built on
  `claude/jarvis-continuation-03kls1` (638464b1: backend switch + phone).
- **The plan card is wired into the tool list** there too (7675da4d,
  `propose_plan`, gate `run_plan`), still switched off until a passing
  `tool_eval_results.json` exists.
- **GitHub's `main` merged into this branch (2026-09-28, `studio-merge-main`):**
  PRs #22 and #24 - talk-to-type (API §72), watches (§70), the Brain
  upgrades and history search (§71), remind me next time (§73), ring my
  phone (§74), Lockdown (§75), where did I put (§77), until-dates and the
  overnight tidy (§78), deleting a chat offers to forget its facts (§79),
  better voice (§80), phone conveniences (§81), Today cards (§82), photo to
  reminder (§83), PC help (§84), bring in old chats (§85), widgets you
  describe (§86), model tryouts, desktop polish. Read those sections before
  proposing anything near them.
- **Built 2026-09-28:** Jarvis Live (`docs/LIVE-DESIGN.md`; voice
  conversation plus a camera kept off until the 12 GB card passes a photo
  test; four reviews and their fixes, branch `studio-live-fixes`), the money
  limit and its hard stop (answer-length caps), Compare, the screen-answers
  voice setting. `docs/studio-2026-09-28/gemini-live-comparison.md` compares
  Live with Gemini Live. Not built from the Live reviews' ideas: a pocket
  mode (the hotkey, tile, "Resume" notification, headset button, Bluetooth
  microphone and share-to-Live were built later the same day - see Voice).

## Decided but not built yet (don't propose these as new)

The animals' mouths timed by Kokoro v1.0 itself (built for v0.19
only); blended voices; the
12 GB card's long-context lane; the memory re-ranker bake-off; the
feasibility audit's small items. (Talk-to-type, the Today page, the
overnight tidy, review cards only, QR pairing with per-device keys and Goals are
built and on main; the plan card is built and switched off until its
safety test passes.) The owner's full list of
decisions is in `CLAUDE.md`.
