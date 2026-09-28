# Audit of the outside-project references, and of Gemini's review of them (2026-09-28)

**Read this before acting on any outside review of Jarvis's third-party
projects.** Two Gemini reviews on 2026-09-28 worked from a list of the GitHub
projects Jarvis names, without the code. Several of their findings were wrong. Each
claim below was checked against the file named. Don't bring the disproven
ones back without new evidence from the code.

## 1. Facts, with the evidence

| Fact | Evidence |
|---|---|
| The backend's web server is Python's standard library `http.server` (`ThreadingHTTPServer`), not FastAPI. Nothing in the repo uses FastAPI, Starlette, uvicorn or aiohttp. | `backend/loopback-too.patch` (`httpd = ThreadingHTTPServer((bind, HUD_PORT), Handler)`), `backend/README.md` ("`main()` opens one socket: `ThreadingHTTPServer((bind, HUD_PORT), Handler)`") |
| Rule 2's allowed addresses include the home network (10.x, 172.16-31.x, 192.168.x, `fc00::/7`, `.local`), as well as this PC and Tailscale/Meshnet (100.64.0.0/10). The owner added the home network on 2026-09-26. | `docs/ARCHITECTURE.md` §2 (the own-networks table), `CLAUDE.md` ("Decided 2026-09-26, after checking a Gemini audit finding") |
| The animal motion is Jarvis's own procedural maths. It has no spring solver and no third-party motion code (not Spring-It-On, not TalkingHead). Each pose is a pure function of the state and the clock. | `jarvis-desktop/src/critter-pose.js` header: "Nothing carries over from the last frame" |
| **Corrected 2026-09-28 (this audit was wrong first time):** Jarvis HAS a tool that runs commands the model writes: `shell_exec` runs one shell command through `subprocess` (`shell=True`), with the owner's full Windows permissions, after an approval card showing the exact command. Its environment is an allowlist with no keys, tokens or passwords. There is no sandbox. | `backend/jarvis_agent.py` (`_run_shell_exec`, `shell_env`), `backend/README.md`: "there is no sandbox" |
| No Temporal and no DBOS. There is one scheduler (`jarvis_schedule`). | Code search: no `temporalio` or `dbos` imports in `backend/` |
| ZipVoice is already used, for custom voices. | `backend/jarvis_voices.py`, `THIRD-PARTY-NOTICES.txt` |
| The PC already uses Silero VAD. The phone and the desktop app use a loudness rule to decide when you've stopped talking and when you're interrupting. The wake-up itself ("hey Jarvis") is done by the openWakeWord model, not by loudness. | `docs/ARCHITECTURE.md` §10 ("speech check (Silero VAD)"), `jarvis-client/.../voice/VoiceFlow.kt` (`trailingQuietMs`, `WakeClip.EndOfSpeech.threshold`), the desktop's `voice_flow.rs` (`trailing_quiet`) |
| espeak-ng (GPL-3.0) is not bundled in the desktop installer. It's installed on the PC by pip (`espeakng-loader`) and is optional. | `jarvis-desktop/src-tauri/tauri.conf.json` `resources` (only `LICENSE` and `THIRD-PARTY-NOTICES.txt`), `backend/requirements.txt` |
| Web search with DuckDuckGo (`ddgs`), SearXNG, Exa, Tavily and Brave is already built. Keys are in Windows Credential Manager. | `docs/ARCHITECTURE.md` (web search), `backend/jarvis_search.py` |
| The research notes already recorded, without any code using them: Honcho is AGPL, CED is GPL, KuzuDB and mcp-run-python are archived, Qwen3-TTS needs FlashAttention 2 (it won't run on the RTX 20-series), and audiocraft's weights are non-commercial. | `docs/CUTTING-EDGE-2026-09-26-*.md`, `docs/MEMORY-RESEARCH-2026-09-26.md` |

## 2. Findings from the review that are disproven

- "Replace bare `subprocess` execution of model-written Python with Monty." **Half right; this audit first said it was wrong.** The concern is real: `shell_exec` (above) runs approved commands with full permissions, and a command can be `python -c ...`. But Monty doesn't fix that: it runs only a subset of Python, not shell commands, so it can't replace `shell_exec`. What protects the owner today is the card with the exact command, the no-secrets environment, and the stale-stream block. Monty stays a candidate only for the narrow spreadsheet query box (`CUTTING-EDGE-2026-09-26-round3-knowledge.md`, idea 6).
- "Replace Temporal with DBOS." Neither is used. Adding DBOS's scheduler would break the one-scheduler rule. The research already chose to copy DBOS's resume-from-the-last-step *idea*, not the library.
- "espeak-ng DLLs in the installer risk GPL contagion." They aren't there. (Keep it that way: never add espeak-ng to the installer's resources.)
- "Add credits for TalkingHead and spring-motion code." Neither was used, so there is nothing to credit.
- "Silero on the phone eliminates TV false wakes." Wake-up is the wake-word model's job. Silero would change end-of-speech and interruption detection (milestone 1 below).
- Package names Gemini itself later withdrew as invented: `dioco-group/stream-parser`, `cskwork/pet-mochi`, `CodaCipher/v-lucent`.

## 3. Not verified (don't state these as fact)

- **Apple buying KùzuDB's team.** Gemini said this was "confirmed" but gave no source. Jarvis's own research confirms only that KuzuDB is archived (its README).
- **The licence on Inigo Quilez's articles.** iquilezles.org couldn't be reached from the container where this was written. The credits were added anyway (section 4); the build is non-commercial (rule 5).
- **Whether `steel-dev/steel-browser` exists and is maintained.** Not checked.
- **Prompt Guard 2's speed and accuracy on the owner's Ryzen 9 3900X.** Not measured.

## 4. Changes made with this audit

- Inigo Quilez credited with the article addresses beside his formulas: `jarvis-desktop/critters/common_head.sksl` (regenerated into `critters-gen.js` and the phone's `CritterShaders.kt` by `tools/gen_critters.py`), and the smooth minimum in the Nucleus face (`faces.html`, the phone's `Faces.kt`). The changes are comments only, and `tools/shader_size.py --check` still passes (red panda 59,426 of 60,000).
- `THIRD-PARTY-NOTICES.txt`: new hand-written sections for the faces' shape maths (Quilez) and the launch-video fonts (Inter, Fraunces; OFL 1.1). The phone's `NOTICES.txt` gets the Quilez entry. `tools/gen_notices.py --check` still passes.

## 5. Something the owner should know

On 2026-09-28 the owner decided the animals' motion should reuse proven open
motion logic (Spring-It-On, TalkingHead) rather than invent it. It wasn't
reused: the motion was written from scratch (section 1). It follows the calm,
slow, eased rules, and the two apps are tested to move identically, but it
isn't the reused code the decision asked for. It stays as it is unless the owner says otherwise.

## 6. Queued: three separate milestones, none started

Each is its own piece of work, doesn't depend on the others, and changes no
existing behaviour until it's switched on. Each gets the usual new-feature audit
(`CLAUDE.md`) when it's built.

### Milestone 1 - Silero speech detection in the apps (highest priority)

- **What.** Use the Silero VAD model (MIT, the same one the PC uses) in place
  of the loudness rule that decides when you've stopped talking and when
  you're interrupting a spoken answer (`VoiceFlow.kt`, `trailingQuietMs` and
  the interrupt flow). Wake-up stays with the wake-word model.
- **Why.** A TV or room noise is loud but isn't speech. The loudness rule can
  keep a recording going too long, or mistake noise for an interruption.
- **Limits.** The backend's voice contract doesn't change: the phone still
  sends a finished clip, and the PC's Silero still trims it. The desktop app
  uses the same loudness rule (`voice_flow.rs`), so either both apps get it or the
  one-sided reason goes in `ARCHITECTURE.md` §8. Measure first: count early
  cut-offs, late stops and false interruptions with a TV on, before and after.
  Keep the loudness rule as the fallback if the model fails to load.

### Milestone 2 - Prompt Guard 2 as a warning (evaluate first)

- **What.** A small classifier that flags hijack-like wording in outside text
  (emails, web pages, calendar entries) before it reaches the model. It only
  warns and never blocks: the existing rules (outside text is marked, risky
  actions ask first) stay the real boundary.
- **Before building.** The model is under the Llama 4 Community License and is
  gated: the owner has to ask Meta for access on Hugging Face. Then measure it on
  the owner's CPU with ONNX Runtime, on the 383 ordinary texts (false alarms)
  and the AgentDojo attack set (`backend/agentdojo_injections.json`). The
  fallback is `protectai/deberta-v3-base-prompt-injection-v2` (Apache-2.0),
  whose licence also still needs checking (`CUTTING-EDGE-2026-09-26-round2-trust.md`,
  idea 14).

### Milestone 3 - "Quiz me on my notes" with FSRS (deferred)

- **What.** Spaced-repetition quizzes from the owner's notes, scheduled with
  `py-fsrs` (MIT, pure Python).
- **When.** Only once a note-review screen is designed. It would be one new
  kind on the existing scheduler, not a second scheduler, and notes stay
  outside text (never learned as facts).

## 7. Rounds three and four (later on 2026-09-28)

Two more batches of suggestions from Gemini, checked the same way.

**Round three:**
- **FlashRank (re-ranking memory results):** already done another way.
  `backend/rebuilt/jarvis_memory.py` re-ranks with fastembed's cross-encoder
  `Xenova/ms-marco-MiniLM-L-6-v2` on the processor, after the fused keyword
  and meaning search (memory idea 1). A swap to FlashRank's bigger model
  would be a memory change, so it has to beat `eval_memory.py` first. The
  sample code Gemini gave also returns its "top 5" in the old order, not by
  score.
- **Monty with saved interpreter state:** see the corrected entry above.
- **Dyad:** only relevant to the app builder; its per-project rules file is
  taken as an idea (`docs/APP-BUILDER-DESIGN.md`, milestone D).
- **ShowUI (clicking by screenshot):** goes against Jarvis's design.
  `backend/jarvis_ui_control.py` clicks only named controls from Windows'
  accessibility tree, stops the moment anything changes, and never guesses
  pixel positions (`docs/UFO-SAFETY-DESIGN.md`). Mouse control also waits
  (owner, 2026-09-25).
- **Silero on the phone:** already milestone 1 (section 6). The phone sends
  one finished clip, not a stream. `WakeWordService.kt` exists; wake-up is
  still the wake-word model's job.
- **microWakeWord (kahrendt/microWakeWord, code Apache-2.0):** a candidate
  for the wake-word trial alongside livekit-wakeword. The licences of its
  trained models and training data haven't been checked; they decide whether
  it's really free of the non-commercial limit.

**Round four** (all tied to building apps, which the owner then chose to do,
in `docs/APP-BUILDER-DESIGN.md`):
- The "headless coding sub-engine" Gemini described didn't exist, and nothing
  in the backend used git worktrees. `ARCHITECTURE.md` section 11's "Sandbox:
  Git worktrees, not Docker" was a decision with no code behind it. It is now
  milestone A of the app builder. A worktree keeps changes apart; it is not a
  sandbox for running programs (the design doc says what is done instead).
- crawl4ai, RepoMapper/Aider RepoMap, bolt.diy, Roo Code and Plandex (AGPL):
  ideas only, placed in the design doc's milestones or its "not adopted"
  list.
- **Offline developer docs (Dash/Zeal docsets):** a candidate for later, not
  queued (owner, 2026-09-28).

