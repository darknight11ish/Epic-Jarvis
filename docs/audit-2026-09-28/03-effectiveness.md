# Audit 3 - do the new features actually work, do what they promise, and stay simple? (2026-09-28)

Tree: `scratchpad/integ` (HEAD deaca649), with the new work being
`9cdb0567..HEAD`.

How I checked: for each feature I followed the chain from the screen, to the
app's request, to the route, to the backend module, to the model or tool.

- Routes: I grepped every route named in JARVIS-API sections 56-89 against
  the backend modules, the desktop (JS and Rust) and the phone (Kotlin).
- Tests: I read the merge helper's test results (`ui3.txt`, 118 desktop page
  tests "ok"; `suites3.txt`, backend 170 passed, 6 failed, all six already
  known).
- The memory self-tests: I re-ran them myself, words only, in a copy under
  `scratchpad/a03`.

Nothing here ran on Windows, with the real models, or on a phone.

## The answer first

- **Almost every new feature is fully wired.** Every route I checked has a
  backend handler, a desktop caller and a phone caller, apart from the ones
  left out on purpose and written down (details in the table). I found no
  stubs or TODOs posing as features.
- **Several features are built but not usable yet, and they say so
  honestly:**
  - the plan card;
  - "said again";
  - the better-voice models;
  - the app builder;
  - "Look at this / Watch with me";
  - the Live camera;
  - the chatbot websites (none tried against the real sites).
- **The biggest real problem is memory.** The "entity layer" (linking facts
  to people and things) is **on by default in every chat's recall**. On the
  LoCoMo test it makes recall *worse*: "found all @5" falls from 9.5% to
  3.6%. I found why and reproduced it (finding 3.1). A small change recovers
  most of the loss and does not change the main memory self-test at 0, 100
  or 1,000 filler facts.
- **One real bug on the voice path:** pressing Jarvis Live warms up the
  wrong model when the owner has switched models (finding 3.2).
- **Much still can't be judged without the PC**, because the measuring tools
  exist but have no results yet:
  - the real-model memory numbers, LoCoMo, "said again" and the re-ranker;
  - the tool test that unlocks the plan card;
  - the model tryouts;
  - the Live timings.

## Findings

### 3.1 The entity layer makes multi-step memory recall worse, and it is on in real chats (medium, checked in code and reproduced; main branch memory code, measured by the continuation branch's milestone 13)

- **What's wrong:** LoCoMo is a public test set of long made-up chats. On
  it, recall with the entity layer is worse than plain search on every
  number:

  | | found-any @5 | found-all @5 | nDCG@5 |
  |---|---|---|---|
  | plain search | 45.0% | 9.5% | 0.238 |
  | with the entity layer | 32.0% | 3.6% | 0.124 |

  The layer is **on** by default: `_ENTITY_RECALL` reads
  `JARVIS_MEMORY_ENTITIES`, default `"1"`
  (`backend/rebuilt/jarvis_memory.py:4389`). Chat recall asks for it
  (`search(entities=True)`).
- **Why it happens (checked):**
  1. `search()` adds a third list to the ranking: every fact linked to a
     person the question names (`jarvis_memory.py:2444-2452`), from
     `_linked_facts` (`:3274-3300`). That list is sorted only by "how many of
     the named people it mentions, then newest"
     (`ORDER BY n DESC, fe.fact_id DESC`). It has no link to what the
     question is actually about.
  2. It counts as much as the word list in the fusion (both use 1/(60+rank)).
  3. So when a question names someone who appears in most of the memory,
     the newest facts about that person push the relevant ones out of the
     top 5. I checked this on LoCoMo chat 1 (script `scratchpad/a03/backend/probe.py`):
     - "Caroline" is linked to **291 of 419** chat lines, and "Melanie" to
       255;
     - "What did Caroline research?" found the right line with plain search
       and lost it with the layer. Its top result became an unrelated recent
       line, `Caroline said, "Glad you agree, Caroline. ..."`.
  4. The no-model linker also makes entities out of words that start a
     sentence: "Wow" is linked to 30 lines and "Glad" to 19.
  5. The existing guard, `ALIAS_MAX_ENTITIES = 2` (`:4394`), stops one
     alias that points at many people. Nothing stops **one person linked to
     most of the facts**.
- **Why it matters for the owner (not only for the test):** the owner's
  memory will have a few people mentioned constantly (a partner, a sister, a
  child). Every question naming them gets the same newest-first flood. The
  main self-test never shows this, because its 20 people questions each name
  someone with only a few facts, and its filler facts name nobody.
- **Tried in a copy (not in the repo):** I skipped any entity linked to more
  than max(20, 5% of all facts) in `_linked_facts`
  (`scratchpad/a03/backend/probe2.py`, `probe3.py`):
  - LoCoMo with the entity layer: found-all @5 went 3.6% -> **8.3%**,
    found-any @5 32.0% -> 42.6%, found-all @10 11.8% -> 18.9% (plain search
    is 9.5% / 45.0% / 18.9%);
  - the main self-test (words only, 0/100/1,000 filler) was **unchanged**:
    recall@5 80.9/79.8/79.8 neutral and 80.9/78.7/77.7 same-topic, people
    20/20, two-fact questions 7, MRR identical.
- **Fix (code change, but the owner's rule applies):**
  - put a "too common to help" cut in `_linked_facts`;
  - optionally ignore a sentence-opening capitalised word that is not a
    known name.

  Under the 2026-09-26 rule, it is kept only if the PC run of
  `eval_memory.py` and `--locomo` shows no number getting worse. Until then,
  the scoreboard's note "Nobody has looked into why yet" can be replaced with
  the cause above.

### 3.2 Pressing Jarvis Live warms the wrong model after a model switch, and shortens how long the model stays loaded (medium, checked in code, continuation branch cfff8d5b)

- **What's wrong:**
  - `jarvis_live._default_warm` calls `jarvis_agent.warm_everyday()` with
    no arguments (`backend/jarvis_live.py:555-564`). That function loads
    `os.environ.get("JARVIS_MODEL") or "jarvis-primary"`
    (`backend/jarvis_agent.py:4748`).
  - Every other warm-up asks which model chat really uses. The waking
    warm-up uses `jarvis_power_switch.chat_model()`
    (`jarvis_power_switch.py:305-320`, "from the owner's jarvis_models ...
    else JARVIS_MODEL"), and `warm_after_waking` checks the last turn's model
    (`jarvis_agent.py:5505-5519`).
  - It also sends `"keep_alive": "30m"` (`:4752`).
- **Why it matters:**
  - Switching models from the phone is allowed (owner, 2026-09-18). After a
    switch, pressing Live loads a *second* model onto an 8 GB card that
    MODEL-TOPOLOGY says has room for one. Ollama must then throw one out.
    The first Live answer, the moment the warm-up exists to speed up, can be
    *slower*, not faster.
  - The 30-minute timer also replaces MODEL-TOPOLOGY's
    `OLLAMA_KEEP_ALIVE=-1` for that model until the next chat request. That
    request comes through `/v1`, which has no keep-alive field, so it resets
    to the setting. (This reset rule is from how Ollama works; I did not run
    it.)
- **Fix (code change, small):** in `_default_warm`, pass the model chat
  uses, for example `jarvis_agent.warm_everyday(model=jarvis_power_switch.chat_model())`.
  Drop `keep_alive`, or send `-1`, so the owner's own setting is kept.
  Better still, reuse `warm_prefix` with the last turn's settings, which also
  reads the rules and tool list ahead of time (the "warm-up with words"
  commit 7ec2a830 already does this for waking).

### 3.3 "What asks first" lists an app-builder card for a feature that cannot be reached yet (low, checked in code, main branch 6d8a1b75)

- `app_merge_change` ("Add its change to one of your apps") was added to
  both apps' "What asks first" lists. But `jarvis_app_workspace.py` is, in
  its own commit's words, "not wired to any tool, route or screen yet"
  (2e2df224).
- A beginner reading the list will look for an "apps" feature that does not
  exist.
- **Fix:** hide the row until milestone B wires it, or add "(coming later)".
  It's the owner's call which.

### 3.4 Jarvis Live refuses short replies, which makes a "conversation" hard to keep going (low, by the owner's choice; checked in code and docs)

- Every Live clip must be at least 2 seconds at Very strict, the default,
  which is about 1.4 s of words (`jarvis_live.py` docstring, "WHAT IT CANNOT
  DO"; LIVE-DESIGN §"Four things").
- "What time is it?" or "yes" gets "Didn't catch that - say a bit more".
  The owner chose to keep this (answer 4). The apps offer Yes/No tap
  buttons.
- It is a correct safety trade-off, but a beginner will feel it as "Live
  doesn't hear me".
- **Suggestion (owner's call):** say it once, on the first Live start:
  "Short answers like 'yes' need a tap - Live needs about two seconds of
  your voice to check it's you."

### 3.5 The chatbot drivers are a long setup for a beginner, and none has been tried against a real site (medium for usefulness, not a bug; checked in code and docs, research branch)

- Before any website chatbot works, the owner must, per site:
  1. install Playwright by a command: `INSTALL_LINE` in
     `jarvis_chatbot_web.py:143` is
     `py -3 -m pip install playwright; py -3 -m playwright install chromium`;
  2. create a spare account;
  3. run `py -3 jarvis_chatbot_<site>.py sign-in` on the PC, then `check`
     (ARCHITECTURE §8).

  It is all PowerShell, none of it is in the apps, and the design's
  selectors are unchecked on the nine real sites (JARVIS-API §87).
- "Ask several and compare" asks the chatbots **one after another**, each
  with its own several rounds of follow-ups written by the everyday model.
  So a comparison of 3 chatbots is several minutes of the main model's time.
- **Suggestion:**
  - one "Set up chatbots" line in Settings that shows the exact one-line
    commands with a copy button;
  - say the expected time on the compare card.

## Every new feature, rated

Ratings: **works** (every link present and tested), **works partly**,
**doesn't work**, or **can't tell without the PC / phone**. "Tests" means the
repo's own tests pass in the combined tree (desktop `ui3.txt`, backend
`suites3.txt`).

| Feature (branch) | Chain checked | Goal met? | Efficient? | Simple? | Measured by | Rating |
|---|---|---|---|---|---|---|
| **Jarvis Live** (continuation) | Bar button and tray, then `POST /api/voice/live`, then `jarvis_live.Session`. Clips go to `/api/voice/utterance?source=live`, then `hear()` (speech found, owner check, then speech-to-text), then the words go back to the app, which sends the chat turn marked `live:true`, which gets the spoken-style note, with speech from the first comma (`main.js:3400-3411`, `speech-pieces.js`). Phone has the same. | Yes, as designed: no wake word between turns, cards by tap only, voice check on every clip. | Each step is sensible. Designed estimate 2-3.5 s on the PC, 2.3-4 s on the phone (LIVE-DESIGN §4, **unmeasured**). The warm-up bug (3.2). | Many states ("Muted", "Paused: other voices", "Waiting for your tap", "say a bit more"), each in plain words. Short-reply refusals (3.4). | `jarvis_voice_flow.py --measure` exists; **no PC result**. | **Works partly**: fix 3.2; timing can't be told without the PC. |
| **"Speech starts at the first comma"** (earlier, used by Live) | `nextSpeechPiece` cuts the first piece at `,;:` once 10 or more characters are in (`speech-pieces.js:33-37`). Live holds speech only while the answer could still be "[not for me]". | Yes. | Yes. Kokoro's first sound took about 1.23 s in the container. | Nothing to set. | `tests/speech-pieces.mjs` passes. | **Works** (real latency needs the PC). |
| **3D animal faces** (4 animals, wake/sleep, still, crisis pose) (mascot) | Faces window or Settings, then `jarvis.faceTuning` (local), then `faces.html` critterFace, then a WebGL shader (`critters/*.sksl`), with a flat-drawing fallback through the GPU watchdog. Phone: `CritterFaces.kt`. | Yes. | See audit 7: the always-on faces rest at 30-60 fps, and the MSAA/depth buffers are wasted. | One settings place ("one place for every animal option", owner). | `faces.mjs` fails only on the known https-in-a-comment check. `face-watchdog.mjs` and `face-pace.mjs` pass. | **Works** (speed on the real card unmeasured). |
| **Lip-sync / mouths timed by Kokoro** (mascot) | The PC sends each sentence's mouth track in the WAV (`jarvis_mouth.py`), then `lipsync.js`, then the face uniform `uMouth`. | Yes. | The track is computed once per clip. | Nothing to set. | `lipsync.mjs` and `voice-mouth.mjs` pass. There is a 3,286-line corpus test (commit 044b120e). | **Works**. |
| **Voice follows the face** (mascot) | `jarvis_voices.FACE_VOICES`, then the TTS voice per animal, with a switch in both apps. | Yes, but the default is against the owner's decision (already known: `FACE_VOICE_DEFAULT = True`, `jarvis_voices.py:531`). | - | - | `test_voices.py` passes. | **Works partly** (the default is wrong; already known). |
| **Sun, moon and weather behind the animals** (mascot) | `GET/POST /api/sky`, then `jarvis_sky.py`, then `sky-feed.js`, with 2D canvas drawing (`faces.html:1326`). | Yes. | A 2D canvas; cheap. | A settings row. | `sky.mjs` passes. | **Works**. |
| **Chatbot drive and "ask several and compare"** (research) | Brain -> Work, then `/api/chatbot/*` (`jarvis_chatbot_routes.py`), then the core, then the website adapters (Playwright) / API adapters / local model. Phone has the same. | Built as decided. | Sequential. The local "second AI" correctly refuses another model on one card (`jarvis_chatbot_local.py` docstring). | Setup is PowerShell, per site (3.5). | Tests against fake pages only. **No real site tried.** | **Can't tell without the PC**; the websites are unproven. |
| **"Try the cloud model"** (main) | Offer shown, then the owner's yes, then `X-Jarvis-Route` `cloud_yes`, then `cloud-say-yes.patch`, then `jarvis_router.choose(owner_said_yes)`. Phone has the same. | Yes: a one-question yes. | - | One tap. | `cloud-offer.mjs` and `test_cloud_say_yes.py` pass. | **Works**. |
| **Third graphics card** (continuation) | Settings row (hidden unless a capable third card), then `POST /api/second-card` `third_assign` with a card, then a third Ollama pinned to that card. | Yes. | Zero cost on the main card (audit 7.6). | Hidden until relevant. | `second-card.mjs` passes. | **Can't tell** (no third card exists). |
| **Plan card, "one card, several steps"** (main) | `propose_plan` tool, then `_propose_plan_refusal`, then `jarvis_plan.enabled()`, which reads `tool_eval_results.json`. | Off by design until the tool test passes. | It is offered to the model only if it is in `[tools].enabled` (`offered_tools`, `jarvis_agent.py:3630`), and no default config adds it, so it costs no prompt tokens. | Nothing tells the owner that, after the test passes, it must also be added to `[tools].enabled`. | `tools/tool_eval/ollama_tool_eval.py`: **no results file in the repo**. | **Doesn't work yet (on purpose)**. |
| **Reading phone notifications** (continuation) | Phone listener, then `GET /api/notifications/watch` (`jarvis_watch_notify.py`). Phone-only by nature. | Yes, the safe version. | - | Off by default, with a card. | `test_watch_notify.py` passes. | **Can't tell without the phone**. |
| **Projects** (research) | Both apps' screens, then `/api/projects`, then `jarvis_projects.py`. | Yes. | - | - | `projects.mjs` passes. | **Works** (tests). |
| **Goals** (main) | `/api/goals`, then `jarvis_goals.py`, one card per acting step. Both apps. | Yes. | - | - | `goals.mjs` passes. | **Works** (tests). |
| **Forget a time frame** (competitors) | Both apps, then `GET .../forget_range/preview`, then `POST` (one card), then `/undo` within 10 min (`jarvis_forget_range.py:90-93`). | Yes. | - | A ticked list, 1 card, Undo. | `forget-range.mjs` passes. `test_forget_range.py` fails in the combined tree (known merge issue). | **Works** (check the merge failure). |
| **Search what was said, a fact's history, Galaxy** (competitors) | `/api/history/search`, `/api/memory/fact-history`, `/api/graph` (desktop). The phone has search, and fact history is desktop-only. | Yes. | - | - | `galaxy.mjs` and `fact-history.mjs` pass. `test_brain_reads.py` fails (known). | **Works** (tests). |
| **Talk-to-type** (competitors) | Hold a key, then the PC microphone, then `/api/voice/utterance?source=talk_to_type`, then typing into the program in front. One card to turn on. | Yes. | - | - | Tests pass. The microphone clash with Live is already known. | **Can't tell without the PC**. |
| **Watches (search, price, GitHub)** (competitors) | `POST /api/schedule/add` `tellme`, then `jarvis_tellme` plain-code checks. **No model call** (JARVIS-API §70). | Yes. | Good: fingerprints only, sensible intervals. | One card per watch. | `test_tellme_watches.py` passes. | **Works** (tests). |
| **Lockdown, "ring my phone", next-time reminders** (competitors) | `/api/asks_first/tier`, `/api/media`, `/api/schedule`. Both apps. | Yes. | - | - | Tests pass. | **Works** (tests). |
| **Today cards** (competitors) | `/api/schedule` + `/api/briefing`. Both apps. | Yes. | - | - | `today.mjs` passes. | **Works** (tests). |
| **Widgets you describe** (competitors) | `/api/widgets/*`, then a checked description from a fixed menu, never code. Both apps. The widget re-reads once a minute while on screen (`widget.js BOARD_READ_MS = 60000`). | Yes. | A 1-minute re-read is fine. | - | `widget-board.mjs` passes. | **Works** (tests). |
| **Photo to reminder** (competitors) | `POST /api/photo/scan`, then Windows text recognition, then the plain-code date parser. **No model** (`jarvis_photo_remind.py` docstring). | Yes. | Very. | One tap to add. | Stand-in reader only. `test_photo_remind.py` fails (known). | **Can't tell without the PC** (real text recognition). |
| **PC help** (competitors) | `GET /api/pc/help`. Both apps. | Yes. | - | - | `pc-help.mjs` passes. | **Works** (tests). |
| **Import chats from ChatGPT / Claude / Gemini** (competitors) | Desktop file picker, then `/api/memory/import_chats/start` (PC only, written in ARCH §8). Facts become review cards. | Yes. | - | - | `history-import.mjs` passes. `test_history_import.py` fails (known). | **Works** (tests). |
| **Better voice** (second detector, Silero v6, third voice-ID) (competitors) | Two settings on `/api/voice/enroll`, plus status fields. Each is off or not the default until measured by `jarvis_bakeoff.py`. | Honest: nothing switches by itself. | - | "Blocked" words say what is missing. | `jarvis_bakeoff.py`: **no PC results**. | **Can't tell without the PC**. |
| **Model tryouts** (competitors) | `tools/model_tryout/chat_tryout.py` and `memory_tryout.py`. They never switch anything. | Yes. | An overnight run of 6-11 hours, said plainly. It builds candidates at 16,384 context, the same as `jarvis-primary`, which HARDWARE-PROFILES calculates is over an 8 GB card, so "on card" may read under 100% for every model, `jarvis-primary` included. | One PowerShell line. | **No results yet**. | **Can't tell without the PC**. |
| **Smarter answers** (trim big results, clear old ones, catch "I've done it") (competitors) | `clear_old_tool_results` (`jarvis_agent.py:2835`) keeps cleared results cleared, so the prompt changes as little as possible. | Yes. | Deliberately cache-friendly. | Invisible. | `tool_eval` case `long_result`, **no PC result**. | **Works** (tests). |
| **Rules-first relay / warm-up with words** (main, PR #21) | `with_spoken_note` never goes first (`jarvis_agent.py:4758-4775`). `warm_prefix` on waking. | Yes. | Yes. | Invisible. | `test_warm_prefix.py` passes. | **Works**. |
| **App builder workspace** (main, milestone A) | Module only; "not wired to any tool, route or screen". | Not owner-visible yet. | - | See 3.3. | `test_app_workspace.py`. | **Doesn't work yet (on purpose)**. |
| **Looking at the screen** (continuation, §62) | Backend only, "not in the apps yet". | Not owner-visible. | - | - | Tests. | **Doesn't work yet (on purpose)**. |

## The memory milestones

- **Milestone 7, prompt-cache on screen:**
  - Chain: `/v1/chat/completions` usage, then `speed.jsonl` (`cached_tokens`,
    `prompt_tokens`), then `jarvis_speed.reused_percent`, then the Brain ->
    Model line "N% of the conversation reused, not read again", in both
    apps.
  - I confirmed Ollama's OpenAI layer really sends
    `prompt_tokens_details.cached_tokens` from `PromptEvalCachedCount`: I
    read `openai/openai.go` from Ollama's main branch today, lines 76-81 and
    265-270.
  - **Works partly:** turns with no tools enabled are relayed without asking
    for usage, so they show no number. The commit says so plainly.
  - It is a display only. It measures how much of each prompt Ollama reused,
    and it has **no PC numbers yet**.
- **Milestone 12, "said again" as a tie-breaker:**
  - It sits in `search()` after the re-ranker
    (`jarvis_memory.py:2501-2505`, `_said_again_ties`). It only reorders
    facts whose scores are exactly equal, and it is **off**
    (`JARVIS_MEMORY_SAID_AGAIN_TIEBREAK`).
  - Words-only result: no change at any size (MEMORY-SCOREBOARD).
  - It is expected to matter only with meaning search on the PC. **Can't
    tell without the PC.**
  - Correctly left off, with no screen or setting to confuse anyone.
- **Milestone 13, the 169 LoCoMo questions:**
  - `eval_memory.py --locomo` (`:1165-1340`) stores each chat line as one
    fact and scores found-any, found-all and nDCG at 5 and 10. It runs
    twice, without and with the entity layer. No re-ranker, no chat model.
  - **I reproduced the scoreboard's numbers exactly** (9.5% / 3.6%, words
    only). The PC run (real embedder) has **not been done**.
  - It measured something real straight away: finding 3.1.

## What would settle the "can't tell" rows (all on the PC, one line each, already written in the repo)

1. Memory:
   `py -3 backend\eval_memory.py --learner-model qwen3:8b`, then the same
   with `--locomo` (MEMORY-SCOREBOARD).
2. The tool test that unlocks the plan card:
   `py -3 tools\tool_eval\ollama_tool_eval.py --models jarvis-primary`
   (tools/tool_eval/README.md:29).
3. Voice timings: `jarvis_voice_flow.py --measure` (LIVE-DESIGN §4).
4. Graphics card: the one-line command in `07-gpu.md`.
