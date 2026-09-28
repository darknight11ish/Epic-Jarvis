# Audit 09 - Optimization review (backend, desktop Rust, desktop windows)

Tree: `scratchpad/integ` (branch `audit-integration`, HEAD deaca649). Whole codebase, not only
the new work. Android was out of scope (another helper). Nothing in the repo was edited.

## The short answer

The code is already well tuned in most of the places this audit looked. Someone has already
fixed the obvious problems: the answer card redraws at most every 100 ms, the HUD page uses the
one Rust event stream, hidden faces stop drawing, most file reads are cached until the file
changes, and every list that could grow is capped. What is left is a set of **small-to-medium
wins**. None of them is a crisis.

The ones worth doing, ranked by gain for the risk:

| # | What | Gain (rough) | Risk | Evidence |
|---|---|---|---|---|
| 1 | Up to 3 separate "what can this model do" calls to Ollama (the program that runs the model) before the first word of a turn | 10-100 ms on the first turn after a minute idle | low | checked in code; needs timing on the PC |
| 2 | The desktop's CPU/memory sampler starts by listing every process, disk and network adapter, and keeps that list for the whole session | ~50-300 ms of startup work on one thread, a few MB held | low | checked in code; needs timing on the PC |
| 3 | Finished chatbot conversations (with their whole transcript) stay in the backend's memory until it restarts | slow memory growth; old transcripts linger | low | checked in code |
| 4 | Every settings read deep-copies the whole 1,459-line config | 0.22 ms per read (measured here); ~3-7 ms per voice clip / status call | low | measured here |
| 5 | Memory search holds the memory lock while it works out the question's "meaning numbers" | removes stalls when learning and a question overlap | low-medium | checked in code; memory rule applies |
| 6 | Nine backend modules each carry their own copy of the same "turn it on with a card" code | maintenance; a race fix lands once instead of nine times | medium | checked in code |
| 7 | `nvidia-smi` is started as a new program every 3 s while the widget shows | idle CPU; size unknown | medium | checked in code; needs timing on the PC |
| 8 | The widget's animal face draws at 30-60 frames a second on the same 8 GB card the model uses | unknown; maybe a little speed while answering | low | checked in code; needs timing on the PC |
| 9 | While an answer streams, the whole answer is re-parsed every 100 ms | noticeable only on very long answers | medium | checked in code; needs timing on the PC |
| 10 | Each desktop request builds a brand-new HTTP client (no connection reuse) | ~1 ms per request | low, but touches 63 call sites | checked in code |
| 11 | Spoken sentences travel from Rust to the page as base64 text | a few ms per sentence | low-medium | checked in code; needs timing |
| 12 | Dead code: 13 backend functions and 2 CSS rules nothing uses | tidiness only | low | checked in code |

"Safe small wins I'd apply" and "needs the owner's go-ahead" are listed at the end.

---

## Findings in detail

### 1. Several separate Ollama look-ups before the first word (backend) - low risk
**Checked in code; the time saved needs measuring on the PC.** From: main (before 2026-09-27).

Before a chat turn asks the model anything, `run_local_turn` asks Ollama about the model up to
four times, each through its own little cache:

- `backend/jarvis_agent.py:2161` `_model_waking()` - `GET /api/ps` on **every** turn, no cache
  (called at `jarvis_agent.py:5977`: `waking = bool((model_waking or _model_waking)(cur["url"], cur["model"]))`).
- `jarvis_agent.py:2551` `_context_length()` - `/api/ps`, then `/api/show`, cached 60 s (`_CTX_TTL = 60.0`, line 2526).
- `jarvis_agent.py:2564` `_model_can_use_tools()` - `/api/show`, its own 60 s cache (`_TOOLS_CACHE`).
- `jarvis_agent.py:4346` `_model_can_see_pictures()` - `/api/show` again, a third 60 s cache (`_SEES_CACHE`), picture turns only.

All three `/api/show` readers read the same `capabilities` field of the same reply. After a
minute of quiet (the normal case for a personal assistant) the first question pays for two to
three loopback calls in a row. `/api/show` makes Ollama read the model's file header, so it is
the slow one.

**Fix (code change):** one `_show(url, model)` cache that all three read, kept for ~10 minutes
and dropped when the model is switched or installed. `_lookup_context` can reuse the same
`/api/ps` reply `_model_waking` already fetched in that turn. Nothing about what the model is
offered changes.

### 2. The telemetry sampler lists everything at startup (desktop Rust) - low risk
**Checked in code; needs timing on the PC.** From: main.

`jarvis-desktop/src-tauri/src/lib.rs:455`:
```rust
let mut system = sysinfo::System::new_all();
```
`new_all()` reads every process, disk, network adapter and sensor. The loop only ever uses CPU
and memory (`commands.rs:2953-2954`: `system.refresh_cpu_usage(); system.refresh_memory();`).
It also runs *inside* an async task, so it holds up one of the async worker threads during
startup, while the backend supervisor and event stream are trying to start. The full process
list then stays in memory for the whole session, never refreshed. The same call is repeated on
the error path at `lib.rs:506`.

**Fix (code change, one line each):** `sysinfo::System::new()` (or `new_with_specifics` with CPU
and memory only). The first CPU reading is already taken 3 s later, so the widget shows the same
numbers.

### 3. Finished chatbot conversations are never let go (backend) - low risk
**Checked in code.** From: `claude/jarvis-ai-assistant-research-ff37vy` (chatbot compare).

`backend/jarvis_chatbot.py:745` `_SESSIONS: dict = {}` gets a new entry at lines 1536 and 1941.
The only place it is emptied is `_reset_for_tests()` (line 2107). Each session keeps
`transcript: list` (line 525) - every message to and from the outside chatbot. The same pattern
is in `backend/jarvis_chatbot_compare.py:132` `_COMPARES` (added at 523 and 833, cleared only in
`_reset_for_tests`, line 972).

Why it matters: the backend runs for days. Each finished conversation stays in memory until a
restart. That is slow growth, not a leak that will crash anything. It also means old transcripts
sit in memory longer than needed.

**Fix (code change):** when a session ends, keep only the newest few finished ones (the Brain
window reads "the one this window last showed, for its summary", so keep at least that one).

### 4. Every settings read copies the whole config (backend) - low risk
**Measured here.** From: main (the rebuilt config module).

`backend/rebuilt/jarvis_framework.py:212` `return deepcopy(_CACHE)`. The file is parsed only
when it changes (good). But every call still deep-copies the whole parsed
`jarvis-framework.toml` (1,459 lines). The docstring explains why: some tests change what they
are given. Measured with the shipped file and the scratchpad's Python: **0.22 ms per call**.

`jarvis_speech._cfg()` (33 call sites) and `rebuilt/jarvis_voice.py` (20) call it once *per
setting*. So one voice clip or one `/api/voice/status` pays for dozens of full copies: a few
milliseconds. That is small, but it is on the voice path.

**Fix (code change, additive):** add `setting(section, key, default)` to `jarvis_framework`. It
reads from the cache under the lock and copies only the one value it returns. Point `_cfg` in
`jarvis_speech.py` and `jarvis_voice.py` at it. `load_framework()` keeps its copy-every-time
rule, so the tests that change the dict are unaffected.

### 5. Memory search works out the question's meaning while holding the memory lock - low-medium risk
**Checked in code.** From: main. **Owner's rule applies:** a memory change must pass
`eval_memory.py` and `eval_learner.py`.

`backend/rebuilt/jarvis_memory.py:2379` takes the one global memory lock (`_LOCK = threading.RLock()`,
line 144):
```python
with _LOCK, closing(self._connect()) as c:
```
Then, inside that lock, line 2418 turns the question into its "meaning numbers" (an embedding)
with the local embedding model:
```python
qv = _embed_query(self.embedder, query)
```
That model runs on the processor. While it runs, anything else that needs memory waits (the
learner saving a fact, the Brain window listing facts, a second device asking). The embedding
does not need the database. `backfill_embeddings` (line 2213) likewise embeds up to 64 facts at a
time under the same lock, but that runs rarely (after the embedding model changes).

**Fix (code change):** compute `qv` before `with _LOCK`. The question text is known up front,
except when the entity layer adds names. In that case, compute it after the name lookup,
outside the lock, and take the lock again for the vector query. Ranking does not change. It
should still be run through the memory self-test before it is kept, as the rule says.

Related, low value: every memory operation opens a new SQLite connection and loads the
sqlite-vec add-on (`jarvis_memory.py:1326-1368`, 34 `_connect()` call sites). Measured here
without sqlite-vec: ~0.5 ms per open. Keep the current design unless the PC timing says
otherwise. It is simple, and it fixed a real bug (the comment at 1352 explains it).

### 6. Nine copies of the same "turn it on with a card" code (backend) - medium risk
**Checked in code.** From: main and several branches.

These modules each have their own `_PENDING` / `_WITHDRAWN` / `_LAST` / `_LATEST` state and
their own `_spawn`, `_finish`, `_decide`:
`jarvis_learning_switch.py`, `jarvis_watch_notify.py`, `jarvis_phone_notifications.py`,
`jarvis_chat_log.py`, `jarvis_search.py`, `jarvis_second_card.py`, `jarvis_voices.py`,
`jarvis_big_model.py`, `jarvis_speech.py`.

Measured with `difflib`: `_finish` in `jarvis_watch_notify.py:215` vs
`jarvis_phone_notifications.py:256` is 98% identical, and `_decide` is 98% identical (94% vs
`jarvis_learning_switch.py:119`). This is not a speed problem. It is a correctness-over-time
problem. `jarvis_learning_switch.py` has an extra `_SWITCH` lock for a race the red team found
("R5": an OFF pressed while the card waited was overwritten). Whether each of the other eight
copies has the same protection has to be checked one by one. With a shared helper, that fix
would live in one place.

**Fix: the owner's call.** A shared `jarvis_switch_card.py` (pending/withdrawn/last-outcome, the
tier check, the "was it withdrawn?" lock), used by all nine. This is approval code, so it needs
the full test suite and care. It is not a quick tidy-up.

### 7. A new `nvidia-smi` process every 3 seconds while the widget shows (desktop Rust) - medium risk
**Checked in code; the cost needs measuring on the PC.** From: main.

`lib.rs:82` `TELEMETRY_INTERVAL = 3 s`; each tick (while the widget is visible) calls
`commands.rs:2847` `sample_gpus()`, which runs `nvidia-smi` as a new program
(`Command::new("nvidia-smi")`, line 2852). Starting `nvidia-smi` on Windows loads the NVIDIA
management library each time. The widget is visible by default, so this runs all day.
Unverified cost: probably tens of milliseconds of CPU each time.

**Options (owner's call):** (a) keep one `nvidia-smi --query-gpu=... --loop-ms=3000` running and
read its lines; (b) use the NVIDIA library directly from Rust (a new dependency); (c) sample every
5-10 s instead of every 3 s. Measure first: Task Manager's CPU column for `nvidia-smi.exe` over a
minute.

### 8. The animal face draws continuously on the model's graphics card - low risk to try
**Checked in code; needs timing on the PC.** From: 3d-animal-mascot branch.

`jarvis-desktop/src/jarvis-visual-spec.json` `frame_rate.animals.rest_fps`: `auto_headroom: 60`,
`auto_no_headroom: 30`. The face is WebGL (drawn on the graphics card) in the widget, and in the
HUD and floating face when those are shown. The model also runs on that card (the RTX 2080
Super, 8 GB). The face already measures its own cost and slows down when frames get expensive
(`face-pace.js`). But nothing slows it down *because the model is busy*.

**What to do:** measure first. Ask the same question with the widget face showing and hidden,
and compare tokens per second (the speed record already shows it). If there is a real
difference, draw the face at 30 or 15 frames a second while an answer is being written. The
owner decides whether that matters.

### 9. The streaming answer is re-parsed in full every 100 ms (desktop page) - medium risk
**Checked in code; needs timing on the PC.** From: main.

`jarvis-desktop/src/main.js:710`:
```js
dom.answer.innerHTML = renderMarkdown(held ? held.buffer : state.buffer);
```
This is already throttled to one repaint per 100 ms (`STREAM_PAINT_MS`, line 691), and the
comment explains why. But the work per repaint still grows with the answer, so a very long
answer gets slower toward the end.

**Fix (code change, only if the PC shows it matters):** keep the finished paragraphs as they
are and re-render only the last, still-growing block. Code fences and lists make "finished" hard
to judge, which is why this is medium risk. Worth it only if a long answer visibly stutters.

### 10. A new HTTP client for every desktop request (desktop Rust) - low risk, wide change
**Checked in code.** From: main.

`jarvis-desktop/src-tauri/src/commands.rs:1618` `jarvis_client()` builds a fresh
`reqwest::Client` every time. It is called from 63 places in 18 files. Each new client has its
own empty connection pool, so no request reuses a connection. On loopback this costs about a
millisecond each time. It matters most for the voice path (`/api/voice/utterance`, `/api/voice/say`
once per sentence, `/api/voice/turn` during pauses).

**Fix (code change):** a few shared clients, one per timeout, kept in a `OnceLock`. Keep the
no-redirect and no-proxy settings exactly as they are, because they protect the token.
Mechanical, but touches many files.

### 11. Spoken sentences go through base64 (desktop Rust + page) - low-medium risk
**Checked in code; needs timing.** From: main.

`voice.rs:2908` `Ok(format!("data:audio/wav;base64,{}", BASE64.encode(&bytes)))`. Each sentence's
WAV grows by a third and is sent as text. The page then decodes it for playback, and again
(`trackFor(uri)`, `main.js:3515`) for the lip-sync chunk. Returning raw bytes
(`tauri::ipc::Response`) and playing a `Blob` URL would save a few ms per sentence. The speech
path is already well built: speech starts at the first comma (`speech-pieces.js`), and the next
sentence's sound is fetched while the current one plays (`prefetchNextClip`, `main.js:3528`).
So this is polish, not a fix.

**Not an optimization to make:** `jarvis_speech.hear()` checks the voice is the owner's
*before* turning it into words (module docstring, "ORDER MATTERS"). Running both at once would
be faster, and it would break a written rule ("a voice that is not the owner's is never turned
into words"). Leave it serial.

### 12. Dead code (checked: zero references anywhere in the repo)
I searched every `.py`, `.patch`, `.js`, `.mjs`, `.rs`, `.kt` and `.ps1` file for each name
(including quoted strings, for `getattr` use). Functions in `backend/rebuilt/` are **not**
listed, because the owner's own backend files, which are not in this repo, may call them.

| File:line | Name | Note |
|---|---|---|
| `backend/jarvis_chatbot_api.py:980` | `_card_money` | |
| `backend/jarvis_hardware.py:1427` | `_lane_key` | |
| `backend/jarvis_second_card.py:2014` / `2023` | `combined_lane_state`, `third_lane_state` | |
| `backend/jarvis_settings_registry.py:331` / `368` | `asks_first_targets`, `tool_targets` | the docstring says jarvis_quick uses it; jarvis_quick uses `find_asks_first_target` instead |
| `backend/jarvis_speed.py:777` | `SwitchSpeed.add_measured` | |
| `backend/jarvis_voices.py:2241` | `f5_card` | |
| `backend/jarvis_focus.py:682` | `waiting_line` | |
| `backend/jarvis_calendar.py:207`, `jarvis_email.py:141`, `jarvis_home.py:151` | `_configured` | three copies, none called |
| `backend/jarvis_speech.py:345` | `_sherpa_stt_paths` | kept on purpose "for anything that read the old name"; leave it |
| `jarvis-desktop/src/style.css:2202` | `.primer-unbound` | nothing adds this class |
| `jarvis-desktop/src/settings.css:958` | `.vt-choice-detail` | nothing adds this class |

Not dead, for the record: `backend/jarvis_app_workspace.py` is imported by nothing yet, because
it is app-builder milestone A and deliberately not wired up. All **249** Tauri commands have a
caller in the pages, every `.js`/`.css` file in `src/` is loaded by something, and the Rust
build allows unused code only for Windows-only items (`cfg_attr(not(windows), allow(dead_code))`).

### Smaller things (low gain; listed so nobody re-finds them)
- **The event resume point** (`stream.rs:535`, `1290-1311`) rewrites the whole settings store
  (`store.save()`) up to every 5 s while events arrive, synchronously, on the stream's task. A
  small file of its own would be lighter. Low.
- **`jarvis_manner._read_settings()`** (`jarvis_manner.py:178`) reads `manner.json` twice per turn
  (`current()` and `humor_enabled()`). Sub-millisecond. Low.
- **SQLite indexes:** the hot queries have them: `jobs(state, due)`, `conversations(updated)`,
  `turns` primary key, `marks(turn_id,id)`, `turn_items(item)`, `facts(valid_to, valid_from)`,
  `facts(created, retired_at)`, the entity tables. Unindexed: `facts.retired_by`
  (`jarvis_memory.py:2084, 2130, 2713`) and `facts.embedded` (2216, 2811). The facts table holds
  hundreds to a few thousand rows, so a full scan is well under a millisecond. Not worth an index
  migration.
- **History search** (`jarvis_chat_log.py:1150-1205`) decrypts every kept turn it looks at. That
  is required, because the history is encrypted. It is already capped by `SEARCH_SCAN_MAX` and
  `SEARCH_SECONDS`.
- **Word lists written twice** (desktop JS and phone Kotlin), for example `AVOID_PAUSE_WORDS` in
  `speech-pieces.js` and `SpeechText.kt`. Shared case files already keep them in step
  (`tests/fixtures/first-piece-cases.json`). Generating the lists themselves from one JSON, as
  `tools/gen_critters.py` does for the faces, would remove the second copy. Low; maintenance
  only.
- **Could not verify:** whether a timer/alarm command ("quick path", `schedule.patch:110`)
  runs before or after memory recall (`memory-prefix.patch`, near line 1751). The two hunks sit in
  `jarvis_hud.py`, which is on the owner's PC and not in this repo. By line numbers the quick
  path is in the request handler and recall is in a helper, so recall probably runs later, and a
  timer probably costs no memory search. **Unverified.** One timed "set a timer for 5 minutes"
  on the PC would settle it.

### Checked and already fine (no change needed)
- Answer repaint throttled to 100 ms, `.fresh` animation fixed (`main.js:678-735`).
- The HUD page's `EventSource` is redirected onto the Rust stream (`hud_bootstrap.js:114`), so
  there is one `/api/events` connection, not two.
- Faces are unloaded (`about:blank`) when hidden (`jarvis_hud.html:1073-1080`, `widget.js:528`),
  and `faces.html:5776` stops drawing when the page is hidden.
- Settings polls only while visible (`settings.js:1010-1030`). The screen-work, board and chatbot
  polls run only while something is live. The HUD's 30 s poll is a documented safety net.
- Lists that could grow are capped: Brain trace (300), speech timings, voice-flow rows,
  recent sayings, auto-learn hush list (500), manner temporaries.
- File hashes and settings files are cached until the file changes (speech VAD hash, wake word,
  voices, MCP, asks-first). The pairing token is cached (`token_store.rs:231`). Widget and
  floating settings are written only when they changed (`windows.rs:744`).
- Live, screen-watch and focus loops tick only while they are on. The tray animation repaints
  only when its pattern animates.
- The big data files (`jarvis_sky_places.py` 570 KB, `jarvis_wakebank.py` 930 KB,
  `jarvis_voicebank.py`) are imported only when first needed.
- Voice: speech starts at the first comma on both apps, the next sentence's sound is made while
  one plays, the engines warm up on first status, and Smart Turn trims the end-of-speech wait
  (`voice.rs:1039` asks after a 200 ms pause instead of the fixed 900 ms).

---

## Safe small wins I'd apply
1. **#2** `System::new_all()` → CPU+memory only (`lib.rs:455`, `506`).
2. **#3** Keep only the last few finished chatbot sessions and comparisons
   (`jarvis_chatbot.py:745`, `jarvis_chatbot_compare.py:132`).
3. **#1** One shared, longer-lived `/api/show` cache for the three capability look-ups in
   `jarvis_agent.py`.
4. **#4** An additive `jarvis_framework.setting(section, key, default)` used by `_cfg` in
   `jarvis_speech.py` and `rebuilt/jarvis_voice.py`.
5. **#12** Delete the zero-reference functions and the two CSS rules (not `_sherpa_stt_paths`).

## Needs the owner's go-ahead (or a timing on the PC first)
1. **#5** Embedding the question outside the memory lock. Small and should not change results,
   but the memory rule says run the self-test first.
2. **#6** One shared helper for the nine "turn it on with a card" copies. Approval code, so a
   proper refactor with the full test suite.
3. **#7** How the widget reads the graphics card (a long-running `nvidia-smi`, the NVIDIA
   library, or a slower tick). Measure `nvidia-smi.exe` CPU first.
4. **#8** Slowing the face while the model writes. Measure tokens per second with the face shown
   and hidden first.
5. **#9** Re-rendering only the last block of a streaming answer. Only if long answers visibly
   stutter.
6. **#10** Shared HTTP clients in Rust. Low risk but touches 63 call sites.
7. **#11** Binary audio instead of base64. Polish; time a sentence first.
