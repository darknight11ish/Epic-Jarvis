# Integration evaluation: eight desktop-pet / assistant projects (2026-10-10)

**Bottom line first.** Of the eight projects, **one** has something worth taking,
and it is an *idea*, not code: hit-tested click-through for the floating face
window (from `AkshitIreddy/AI-Desktop-Pet`). Three are ruled out by one of
Jarvis's own five rules rather than by taste. Four are either something Jarvis
already does (with evidence in this repo) or would mean **replacing** the
ray-marched faces with Live2D or VRM — a rewrite of a shared two-app spec, not
an addition. Nothing here is worth a new dependency.

This was read-only research. Nothing was cloned into the repo, nothing was
installed, and no file in the repo was changed except this document. (No
inspection clone was needed, so no GUID temp directory was created either.)

---

## How this was checked

* Every repository was fetched through the GitHub API — existence, canonical
  name, licence, stars, size, created/updated/pushed dates, default branch — and
  then its `README.md`, `LICENSE` and (where a claim needed code) its file tree
  and named files were read from `raw.githubusercontent.com`.
* The brief's descriptions were treated as unverified claims. Where a claim does
  not hold, this document says so plainly.
* Every "Jarvis already has this" line cites a file in this repo. Two prior
  in-repo evaluations were found and reused rather than repeated: the
  README-level survey of open-source assistants
  (`docs/COMPETITORS-OPEN-SOURCE-2026-09-25.md`) and the code-level memory
  review (`docs/research-audit-2026-09-28/report-oss-agents.md`).

---

## The eight, at a glance

| # | Repo | Verified? | Licence | Already in Jarvis? | The one thing worth taking | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| 1 | [ChanceYu/CoPet](https://github.com/ChanceYu/CoPet) | Yes — real, MIT, 35★, last push 2026-07-15, ~155 MB | MIT | **Yes, the whole idea**: a face that reacts to agent state, in five faces | Nothing. Its pets are sprite sheets; sound packs fight the calm doctrine | **not worth it** | — |
| 2 | [AkshitIreddy/AI-Desktop-Pet](https://github.com/AkshitIreddy/AI-Desktop-Pet) (the brief's `convai-desktop-pet`) | Yes — renamed repo, MIT-by-README, 25★, last push 2026-09-30, ~11 MB | MIT file + "various licences" for the art | Partly: transparent always-on-top floating face | **Hit-tested click-through** so the floating face never swallows clicks | **borrow the idea** (the app itself conflicts: Convai cloud) | Small |
| 3 | [agentscope-ai/QwenPaw](https://github.com/agentscope-ai/QwenPaw) | Yes — real and large, Apache-2.0, 35.5k★, pushed 2026-10-10, ~128 MB | Apache-2.0 | Memory (Galaxy graph), faces that react to approvals, MCP bridge, pet-plugin shape | Nothing new. Its pet is a sprite atlas; the good ideas were already read | **conflicts with a rule** (`AUTO` approvals, chat relays, telemetry) | — |
| 4 | [Gentleman-Programming/gentle-dot](https://github.com/Gentleman-Programming/gentle-dot) | Yes — one day old, MIT, 100★, "early preview", no releases, ~8 MB | MIT | Floating indicator (rose ↔ Jarvis's floating face); gates outside the agent | Nothing. The memory is a **separate** trademarked product, not this repo | **conflicts with a rule** (Yolo mode; VPS deployment) | — |
| 5 | [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | Yes — 14k★, MIT code (+ Live2D terms), last push 2026-05-15, ~46 MB | MIT + Live2D sample-model terms | Echo cancellation and barge-in (`aec.rs`, `barge-in.js`); screen vision; pet-style window | Nothing that survives the voice-print rule | **conflicts with a rule**; adopting Live2D = replacing the faces | — |
| 6 | [semperai/amica](https://github.com/semperai/amica) | Yes — MIT, 1.6k★, last push 2026-09-22, ~194 MB, **Tauri v1** | MIT (assets separate) | Faces, lip-sync, emotion states — in Jarvis's own spec | Nothing that is not a second renderer | **not worth it** — would mean replacing the faces | — |
| 7 | [marcodenic/desk-ai](https://github.com/marcodenic/desk-ai) | Yes — but **no licence file at all**; 4★, last push 2025-10-25, ~20 MB | **None** (README claims MIT; no `LICENSE` in the tree, GitHub reports no licence) | NDJSON overlay stdin/stdout runner = Jarvis's MCP bridge; mini window = the HUD/widget | Nothing | **not worth it** (also ships a full auto-approve mode) | — |
| 8 | [Arunachalam-gojosaturo/Luna-ai](https://github.com/Arunachalam-gojosaturo/Luna-ai) | Yes — MIT, 3★, last push 2026-09-10, ~61 MB, Arch-Linux-first | MIT | Kokoro TTS (better: v1.0 pack, blends, phoneme timing) | Nothing | **not worth it** (Linux-only, cloud voice, AI-generated report filler) | — |

---

## What the brief got right, and what it did not

**Right:** every repository exists except one name. `AkshitIreddy/convai-desktop-pet`
is not a missing repo — GitHub's API redirects it to `AkshitIreddy/AI-Desktop-Pet`
(the project was renamed; the Windows installer is still called
`Convai-Desktop-Pets_…exe`), so the two names in the brief are the same project.
CoPet, desk-ai and AI-Desktop-Pet's feature lists are accurate almost word for
word. QwenPaw really does have a three-layer memory and a desktop pet.

**Wrong or overstated:**

1. **desk-ai's licence does not hold.** The README ends "MIT License – See
   [LICENSE](https://github.com/marcodenic/desk-ai/blob/main/LICENSE) for
   details", but there is **no `LICENSE` file** in the tree: the API returns
   `"license": null` and the root listing has none. Without a licence file the
   default is all rights reserved, so its code is not safely borrowable at all —
   the strongest single reason to skip it.
2. **Luna-ai's "Tauri + FastAPI" is true but misleading.** `src-tauri/` does
   exist, but the *desktop* is a PyQt6/QWebEngine launcher (`luna_desktop.py`)
   and the README's own platform line is Arch Linux, Hyprland and Wayland. Its
   voice input is **Groq Whisper** (cloud) with ElevenLabs as a fallback, and its
   long-term memory needs PostgreSQL + PGVector. Its tree also carries nine
   self-written `*_REPORT.md` files, a 33-byte `test.rs`, a stray `snapd` file
   and `generate_reports.py` — generated filler around real code.
3. **gentle-dot's "continuous engram memory" is not in the repository.** Memory
   is [Engram](https://github.com/Gentleman-Programming/gentle-ai), a **separate
   product** (`~/.engram`, port 7437) whose own README calls Engram™ a trademark
   of the author; the MIT licence covers the code only. Nothing about that
   memory can be borrowed from this repo.
4. **QwenPaw's pet is a plugin, and "MCP plugins" conflates two things.** The pet
   arrives as `plugins/bundle/qwenpaw-pet/` — a Qt window plus a FastAPI bridge
   on `127.0.0.1:8765` — and QwenPaw's MCP support is a separate feature. The
   desktop pet is real; the phrasing implies they are one system.
5. **QwenPaw also has an `AUTO` approval level** (`Tool Guard`'s
   STRICT / SMART / **AUTO** / OFF) and collects anonymous telemetry once per
   version — `qwenpaw init --defaults` accepts it without asking. Both matter
   under rules 1 and 3.
6. **amica is Tauri v1, not v2** (`@tauri-apps/cli ^1.6.2`), and it is a
   browser-first Next.js app with a desktop wrapper.
7. **Open-LLM-VTuber's "full-duplex with interruption" is achieved with echo
   cancellation**, which is exactly the reason Jarvis's own Live design refused
   full duplex: it skips the per-clip voice check (`CLAUDE.md`, "Jarvis Live":
   *"Not full-duplex (that skips the voice check)"*). Its licence is MIT for the
   code, but the bundled **Live2D sample models are under Live2D's own terms**
   (`LICENSE-Live2D.md`).

---

## The eight, one at a time

### 1. ChanceYu/CoPet — the closest miss, and still a no

**Verified.** MIT, 35★, created 2026-05-18, last pushed 2026-07-15 (about three
months idle), ~155 MB — most of which is pet GIF/spritesheet art and the README
banner. Built with Tauri, Rust and React; local-first, no telemetry; its event
server binds `127.0.0.1`, needs a bearer token and drops unknown payloads.

**What it is.** A desktop pet driven by *other* agents' hook files: it writes
JSON hooks into `~/.claude/settings.json`, `~/.cursor/hooks.json`,
`~/.codex/hooks.json` and five more, then reacts to prompts, tool use, waiting,
completion and errors with animations, speech bubbles and sound packs.

**Jarvis already has this** — in five faces instead of twenty sprite pets, and
with a far richer state contract: `docs/CRITTERS.md` (red panda, owl, otter,
monkey, robot), the shared spec in `jarvis-desktop/src/faces-spec.js` and
`jarvis-desktop/src/jarvis-visual-spec.json`, the drawing in
`jarvis-desktop/src/critter-*.js` / `critters-gen.js`, and the backend half in
`backend/jarvis_animal.py` (tests: `backend/test_animal.py`). Agent activity is
already surfaced (`jarvis-desktop/src/tool-updates.js`,
`thinking-module.js`, `tool-updates-settings.js`). Approval and error moments
already have their own poses — an attentive look instead of a wave at an
approval, a still ring on error (`CLAUDE.md`, 2026-09-28 and 2026-09-29).

**The only genuinely new thing** is sound: CoPet ships global and per-pet sound
packs, where Jarvis has exactly one cue, synthesised in JS
(`heardSoundUri()`, `jarvis-desktop/src/voice-flow.js:345`) behind a switch that
is off by default. Taking this would fight Jarvis's own restraint doctrine
("never busy or sporadic"; approval and error moments stay calm and still, and
the owner has repeatedly turned sounds *off* by default). Its pets are sprite
sheets, so its code would replace the shader faces rather than add to them.

**Verdict: not worth it.** Nothing here is a gap.

### 2. AkshitIreddy/AI-Desktop-Pet — one small idea; the app breaks rule 1

**Verified** (under both names, as above). 25★, created 2025-01-13, last pushed
2026-09-30, ~11 MB, Tauri 2 + React/TypeScript. The brief's four claims are all
true: one transparent overlay window hosts every pet; pets walk on and hide
behind the owner's real windows (native Rust window tracking and cursor
polling); clicking a pet opens a radial wheel of 8 skills chosen from 22; and
"everywhere you're not touching a pet, clicks pass straight through to your
apps".

**Why the app itself is out.** Its brain *is* Convai's cloud: the owner signs in
at convai.com, pastes an API key, and conversations (and screen frames, and on a
paid plan the long-term memory) run over Convai's WebRTC service. That is rule 1
— private things stay on the local model. Its characters are also third-party
fan art of commercial properties (Genshin Impact/miHoYo, Deadpool, SpongeBob,
Cartman) borrowed from DeviantArt shimeji artists, and the README's licence line
is "see `licenses/`", not a clean MIT.

**The one thing worth taking — the idea, not the code.** Jarvis's floating face
is a real, transparent, always-on-top window
(`jarvis-desktop/src/floating.html`, built at
`jarvis-desktop/src-tauri/src/windows.rs:1204-1234`, `skip_taskbar(true)` at
`:1217`, config in `jarvis-desktop/src/floating.js` and `floating-settings`). It
takes a click anywhere in its rectangle. **Jarvis has no click-through at all**:
`setIgnoreCursorEvents` / `set_ignore_cursor_events` appears nowhere in
`jarvis-desktop/src/*.js` or `jarvis-desktop/src-tauri/src/*.rs`. The borrowable
part is AI-Desktop-Pet's *shape*: keep the window ignoring the cursor, watch the
pointer in Rust, and switch it back to interactive only while the pointer is
over the drawn animal (their hit test is against the pet's own sprite bounds).
That is a small, self-contained piece of Rust plus a hit-test against the pose
Jarvis already computes — no dependency, no licence exposure, nothing from
Convai.

**Caveat, and why this needs the owner:** it collides with petting. The owner
decided on 2026-09-28 that stroking an animal makes it lean in, so the face must
stay clickable *where the animal is*. The safe version is therefore "pass clicks
through everywhere except on the animal itself", off by default, with petting
and drag unaffected. That is the question at the end of this document.

**Verdict: borrow the idea** (app as a whole: conflicts with rule 1).

### 3. agentscope-ai/QwenPaw — big, real, and already read once

**Verified.** Apache-2.0, 35,549★, created 2026-02-24, pushed 2026-10-10 (today),
~128 MB, Python + TypeScript. All four claims hold, including the three-layer
memory ("live working context, full verbatim history, and a self-evolving
personal knowledge base powered by [ReMe](https://github.com/agentscope-ai/ReMe)"),
inline tool-permission prompts (the TUI) and the desktop pet (the official
`qwenpaw-pet` plugin: a Qt floating window, a `127.0.0.1:8765` FastAPI bridge,
`pet.json` + a 1536×1872 spritesheet with named rows — idle, running-right/left,
waving, jumping, failed, waiting, running, review — and monkey patches on
`AgentRunner.query_handler` and the approval service).

**Jarvis already has, or has already read, every part of this.** The project was
surveyed on 2026-09-25 (`docs/COMPETITORS-OPEN-SOURCE-2026-09-25.md:42`, `:64`,
`:78`), where its messaging-relay design (DingTalk, Lark, WeChat, Telegram,
Discord, iMessage, QQ) was exactly the "capability with no call site" Jarvis
avoids. ReMe itself was read line by line on 2026-09-26/28 and its one useful
idea — open loops with a resolved record — was taken as an *emulate* target
(`docs/RESEARCH-2026-09-24.md:76`, `docs/RESEARCH-AUDIT-2026-09-28.md:319`).
Jarvis's memory already has the working context, a kept chat log
(`backend/jarvis_chat_log.py`, `backend/test_chat_log.py`), a fact graph — the
**Galaxy**, desktop-only by standing rule (`jarvis-desktop/src/galaxy-view.js`,
`galaxy-panel.js`, `docs/GALAXY-PANEL-DESIGN.md`) — a re-ranker, "said again"
counts and true-from dates (`backend/test_memory_rerank.py`,
`test_memory_said_again.py`, `test_memory_true_from.py`). A face that reacts to an
approval request is Jarvis's oldest animal behaviour.

**Why it is a rule conflict.** `Tool Guard` offers an **`AUTO`** approval level;
rule 3 is "no auto-approve anywhere", and `backend/test_gate_outcome.py`
asserts it in code. It ships
[anonymous telemetry](https://github.com/agentscope-ai/QwenPaw/blob/main/README.md)
accepted silently by `init --defaults` (Jarvis asserts its own absence:
`backend/test_telemetry_off.py`), a plugin marketplace that downloads code, and
a default pet spritesheet fetched from a CDN on first use. Its own extension
mechanism — injecting a directory into `sys.path` and monkey-patching internal
classes — is the pattern `docs/ARCHITECTURE.md` opens by warning about.

**Verdict: conflicts with a rule**, and the idea-space is already harvested.
Nothing to take.

### 4. Gentleman-Programming/gentle-dot — a day old, and the memory is not here

**Verified.** MIT, 100★, **created 2026-10-09** (the day before this evaluation)
and last pushed the same day; ~8 MB; "early preview", no published releases. The
brief's claims are broadly right: a small Node daemon runs an agent engine
(`gentle-shell --mode rpc`) as a child and translates its events into a
WebSocket protocol; a Tauri 2 app draws the "glowing rose" and owns the
shortcuts; connectors ask before anything that sends or changes; screen control
needs a native dialog per session and refuses password managers and System
Settings.

**Two things the brief implies that are not true of this repo.** The memory is
not here (above). And the design that protects the owner — "the session grant,
the panic stop, the blocklist and the risky-action dialogs live **outside** the
agent" — is a description of what Jarvis already does, in Rust:
`docs/ARCHITECTURE.md:1831` ("the webview is not a check. `decide_approval`
consults link staleness in Rust"), `jarvis-desktop/src-tauri/src/stream.rs`, plus
Jarvis's child-process environment allow-list (`backend/jarvis_child_env.py`,
which keeps the pairing token and every `*_KEY` out of a child program).

**Why it is a rule conflict.** It advertises **Yolo mode**, which "skips the
per-action questions for up to an hour" — rule 3's "nothing auto-approves" is
absolute, and rule 4's stale-stream rule has no equivalent in an agent that
decides for itself. It also ships a Docker/VPS deployment behind HTTPS, which is
the shape of a public endpoint Jarvis refuses (rule 2), and its default models
are cloud subscriptions. It is honest that its own safety is unfinished ("the
agent has a shell, and its shell commands are checked on a best-effort basis
only").

**Verdict: conflicts with a rule**, one day old, memory not present. Nothing to
take.

### 5. Open-LLM-VTuber — the best project in the list, and still a no

**Verified.** 14,031★, created 2023-11-24, last pushed 2026-05-15 (~5 months;
v2.0 is a planned rewrite and v1 is feature-frozen), ~46 MB, Python. Every claim
in the brief is accurate: Python + Live2D over a WebSocket; "voice interruption
without headphones (AI won't hear its own voice)"; pet mode with transparent
background, global top-most and **mouse click-through**; camera and screen
vision; and Live2D expressions mapped from backend emotions. Licence: MIT for
the code, with the bundled Live2D sample models under Live2D Inc.'s own terms.

**Two decisive conflicts with Jarvis's own decisions.**

1. **Interruption is echo cancellation, not endpointing.** Jarvis deliberately
   refused full duplex because it skips the voice-print check, and it already
   has the missing half built for its own half-duplex flow:
   `jarvis-desktop/src-tauri/src/aec.rs` (16 KB) and
   `jarvis-desktop/src/barge-in.js`. Adopting Open-LLM-VTuber's model would
   weaken a check the owner chose to keep — "the voice check still runs on every
   clip".
2. **Live2D would replace the faces, not add to them.** Jarvis's faces are
   ray-marched shaders drawn from one spec shared by the desktop and the phone
   (`docs/CRITTERS.md`, `jarvis-desktop/src/faces.html` at 403 KB,
   `faces-spec.js`, `jarvis-visual-spec.json`), picked in the Faces window, and
   each animal's mouth follows the real audio clip (`docs/LIPSYNC.md`). Live2D
   means a `.model3.json`, a Cubism SDK, an SDK licence, and a second rendering
   path on both apps — the shader work is thrown away. (Its README also warns
   that a remote microphone needs HTTPS and a reverse proxy, which is the
   closest thing in this list to a tunnel.)

**Verdict: conflicts with a rule; adopting it means rewriting the faces.**
Nothing to take.

### 6. semperai/amica — the one that would add avatars, at the price of the faces

**Verified.** MIT (the README excepts 3D models and images, which keep their
authors' licences), 1,611★, created 2023-10-29, last pushed 2026-09-22, ~194 MB.
The brief's claims hold, with one correction: `package.json` pins
`@pixiv/three-vrm ^3.1.2` and `three ^0.169.0` (so blinking, lip-sync and spring-
bone physics come from three-vrm), and it talks to llama.cpp, Ollama, LM Studio,
KoboldCpp, Oobabooga, OpenRouter and the ChatGPT API — but the Tauri wrapper is
**v1** (`@tauri-apps/cli ^1.6.2`), and the app is a Next.js 14 browser app with a
desktop shell.

**What it would cost.** A browser-first Next.js app is the "rewritten in a
framework" shape the desktop frontend rule forbids, and its dependency set is
heavy and partly off-PC by default (`@sentry/nextjs`, `@supabase/supabase-js`,
`twitter-api-v2`, `ws`, `@xenova/transformers`, cloud TTS options). Decisively:
`.vrm` avatars are a second renderer beside the shader faces, and Jarvis has
already solved the hard part better — its lip-sync is computed from the real
Kokoro clip (`docs/LIPSYNC.md`: level, open and wide per hundredth of a second)
rather than from VRM visemes. Jarvis's own animal-motion research already
borrowed from three-vrm's neighbourhood and credited the MIT sources it used
(`CHANGELOG.md:946` names TalkingHead, airi and ChatVRM).

**Verdict: not worth it.** If the owner ever wants user-importable 3D avatars,
this is the reference to read — but as a *new feature that replaces the faces*,
never as an integration.

### 7. marcodenic/desk-ai — no licence, stale, cloud-only

**Verified**, and its features are as described: Tauri + React 18, a Rust sidecar
binary over **NDJSON on stdin/stdout** (`rust-backend/src/ndjson.rs`), a 400px
Mini Mode, a workspace sandbox with confirmation before writes and shell
commands, and a status indicator for Offline/Idle/Thinking/Executing/Streaming.

**It is not usable code.** There is **no `LICENSE` file** in the repository (the
API reports no licence), so the README's MIT sentence is not a grant; the project
has been untouched since 2025-10-25 and has 4 stars; and it is cloud-only
(OpenAI and Anthropic keys, no local model anywhere).

**Jarvis already has the one interesting mechanism.** The sidecar-over-NDJSON
runner is what Jarvis's MCP bridge already is: `backend/jarvis_mcp.py` ("the
server runs as a child process on this PC and talks over its stdin/stdout, one
JSON message per line"), with 92 KB of implementation and 42 KB of tests
(`backend/test_mcp.py`) around the parts desk-ai does not have — installed-once
programs only, a full-path command with no PATH search, read-only tools first,
and every single call through the approval gate. The 400px mini view is a window
size, and Jarvis has both a HUD and a widget window
(`jarvis-desktop/src-tauri/tauri.conf.json`, labels `quickbar` and `widget`).
desk-ai also advertises a **"Full auto-approve mode"**, which rule 3 forbids.

**Verdict: not worth it** (no licence; also a rule conflict).

### 8. Arunachalam-gojosaturo/Luna-ai — real code under a heap of generated reports

**Verified** (canonical spelling `Luna-ai`), MIT, 3★, created 2026-03-11, last
pushed 2026-09-10, ~61 MB. Tauri does exist (`src-tauri/`), the backend is
FastAPI, and Kokoro-ONNX offline TTS and an autonomous Git/shell "Level 4
Developer Co-Pilot" are both real (`backend/voice/tts.py`,
`backend/agents/developer_copilot.py`, `git_agent.py`, `github_agent.py`).

**Why it is not a candidate.** It is built for Arch Linux, Hyprland and Wayland
(`luna-hypr`, PKGBUILD/AUR, PyQt6 `luna_desktop.py`), its voice *input* is Groq
Whisper in the cloud with ElevenLabs as a TTS fallback, and its memory needs
PostgreSQL + PGVector. Its tree is padded with nine AI-written `*_REPORT.md`
files, `generate_reports.py`, a 33-byte `test.rs`, a stray `snapd` file and a
committed `luna_chroma_db/` — the "generated filler" smell the brief asked about,
wrapped around genuine code. Its autonomous loop is also the opposite of the
owner's decision for Projects ("Jarvis does real work… **every change asks first
with a card**", `docs/PROJECTS-DESIGN.md`).

**Its Kokoro adds nothing.** Jarvis's is further ahead: `backend/jarvis_kokoro.py`
names the v1.0 pack and its 54 voices, matches every voice row against the real
`voices.bin`, pins the download by SHA-256, keeps the owner's old numeric choice
working, and adds two blended Jarvis voices; `backend/jarvis_mouth.py` gives
Kokoro's own phoneme durations to the mouths.

**Verdict: not worth it.** Nothing to take.

---

## What is actually worth doing (the whole of it)

1. **Click-through for the floating face, hit-tested on the animal.** Idea from
   AI-Desktop-Pet; no code taken, no dependency, no licence exposure. Evidence
   that Jarvis lacks it: no `set_ignore_cursor_events` / `setIgnoreCursorEvents`
   anywhere in `jarvis-desktop/src` or `jarvis-desktop/src-tauri/src`, and the
   floating window is built at `jarvis-desktop/src-tauri/src/windows.rs:1204`.
   Small effort, off by default, and it needs the owner's answer below because it
   touches petting.

That is the list. Everything else was already in Jarvis, would mean rewriting the
faces, or breaks one of the five rules — and saying so is the result.

---

## The owner's decisions

**Question 1 — the floating face and clicks.**

Today, the floating animal window takes every click that lands anywhere on it.
With click-through, clicks would pass through to whatever is behind, *except*
on the animal itself (so petting, dragging and the menu still work).

* **Add it, as a setting, off by default** (recommended) — the face stops
  getting in the way over a full-screen app; nothing about petting changes.
* **Leave the floating face as it is** — one less switch, and the window keeps
  behaving like an ordinary window.

**Question 2 — Live2D and VRM, now and later.**

Three of the eight projects offer a different way of drawing Jarvis: Live2D
(Open-LLM-VTuber) or 3D `.vrm` avatars (amica). Both replace the ray-marched
faces, not add to them, and the faces are one spec shared with the phone.

* **Keep the faces as they are; no Live2D or VRM importer** (recommended) — no
  second renderer, no SDK licence, no rewrite of a two-app spec.
* **Leave the door open for a VRM importer as a separate, later feature** —
  costs a new rendering path in every window and a second face picker, and the
  shader faces stay for everything else.
