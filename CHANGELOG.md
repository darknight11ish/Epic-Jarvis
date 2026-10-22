# What changed

Newest first. One version number covers the desktop app, the phone app and
the backend files (the `VERSION` file). Builds made by GitHub add a build
number as the last part - `0.2.57` is a build of 0.2.

## Not in a numbered version yet

- **The desktop can answer a review card with typed words and see the PC's own mark, which only the phone could do before (2026-10-21, R2).** Slice 22B (2026-10-17) built the PC's side of the fading-card radar and the deterministic grader, and the phone drew them; the desktop's net layer read both shapes from the start but its window drew neither, and `docs/ARCHITECTURE.md` section 8 listed that as one-sided on purpose. The desktop now draws both: the deck list shows the same "Cards fading" rows the phone shows (the PC's own sentences, word for word), and the review card offers the phone's own two words - **"Show answer"** (unchanged: it sends nothing that was typed) and **"Mark my answer"** (sends the typed box's words to the PC's deterministic grader in that one reveal request, then shows the grader's own sentence word for word). The typed box still never leaves the window except on that tap, is never stored, and is dropped once the answer is shown. One route, one key set and one word list now serve both apps: every word comes from `tools/gen_decks_cases.py`'s shared fixture, and the Rust reveal body sends `answer` only when the box was not blank. Tests: `jarvis-desktop/tests/decks.mjs` holds the words against the fixture and, with Playwright, checks the radar rows, the withheld radar under Hide memory lists, the "Mark my answer" send and the PC's sentence on the revealed card; `jarvis-desktop/src-tauri/src/brain/decks.rs` unit-tests the request body; `cargo fmt`/`check`/`clippy -D warnings` are green. `tools/gen_decks_cases.py` regenerated both contract copies (desktop and phone), and its docstring plus the ARCHITECTURE section now say both apps draw these fields. No new dependency, no route change, no account/card.
- **PC help can now say how much graphics memory each program uses, because Windows knows and the driver will not say (2026-10-21, R5/Ruling 13).** nvidia-smi names the programs holding a card but answers `[N/A]` for every one of their memory amounts on this PC (measured 2026-10-17), so the graphics-card answer could only list the names. The probe first, as the ruling required: Windows' own performance counter `\GPU Process Memory(*)\Dedicated Usage` answers for the same PC as a **normal user, with no elevation**, through PDH in **0.783 s** - 63 instances over 43 PIDs, `dwm` 1,231.52 MiB, `explorer` 334.91 MiB summed across its processes - so the fallback is real, not theoretical. `jarvis_hardware.py` (+ twin) gains `wddm_process_memory()`: standard library only (ctypes/PDH), bounded at **2 s** (a counter that stops answering is abandoned, never waited on), cached for **30 s** (the same period `jarvis_compute.query_apps` uses), and it answers `readable: False` with a plain `why` rather than raising. `jarvis_pc_help.py` (+ twin) asks it only for the programs the driver left without an amount, marks such a number `used_source = "windows_wddm_counter"`, and the words say it is each program's **total across all the cards** - never one card's share, because Windows exposes no clean non-admin mapping from the counter's LUID/phys index to nvidia-smi's card number and a per-card figure would be a guess. **How it behaves when it cannot read** is unchanged and tested: the number stays empty and the existing "the driver does not report how much graphics memory each program uses" sentence is kept - never a made-up 0, never an estimate. Tests: `backend/test_hardware.py` (summed instances, malformed rows dropped, a timeout, a raising reader, the 30 s cache, and a live read that prints `skip` - never a pass - where the counter is absent) and `backend/test_pc_help.py` (the total-across-cards wording, the caveat said once, and the honest fallback when neither source has a number); 490 checks green across the affected suites at the desk, with the twins and the two base checkers. Docs: `docs/JARVIS-API.md` §84.3. No new dependency, no admin, no live write.
- **The README is rewritten for a first-time reader, and a checker keeps it honest (2026-10-21).** The top-level page was the one page no checker measured, and it had rotted in three ways at once: it named `jarvis_voice.py` as the voice pipeline's home after the shipped code had split into `jarvis_speech.py`, `jarvis_voice_flow.py` and `jarvis_voice_enroll.py`; it said **"The desktop installer is not published yet"** while the rolling `desktop-latest` release had been publishing a signed MSI and setup.exe for weeks; and it called two merged pull requests "in flight". It is now **eleven sections in the order a newcomer needs** - what Jarvis is, what you can do today, **Quick start moved up** (prerequisites, the one setup script, the model, the backend check, the published installer or a build from source, pairing the phone over Tailscale or Meshnet, the first chat, one developer check line), the five rules and their three approved exceptions, what asks first, what's new, feature highlights, honest limits, the repository map, where to read next, and the licence - with the **volatile measured counts dropped entirely** and the generated pages linked instead. Newer abilities are covered and the voice modules are named correctly. **New: `tools/check_readme_truth.py`**, wired into the `audit` job: it fails if any `jarvis_*.py`, `docs/*.md` or `scripts/*.ps1` the page names does not exist, if it names a pull-request number, or if any of the three phrases that had already rotted is back; it prints every reference it checked, so a reference that stopped matching cannot pass unnoticed. Docs: `README.md`; the checker's own docstring carries the why.
- **The big Jarvis window is editable now: press Edit HUD, then drag a card or use its own buttons (2026-10-22, H2 of the editable-HUD design).** The header of the big "Jarvis" window now has **[Edit HUD]**, and Settings -> The big HUD window has "Edit HUD in the window". In edit mode every panel card - the six Bento inspector cards, the three left-rail panels, the approvals queue and the Jarvis-bar button - gets a handle, up/down buttons, a direct **Move to: Left rail / Stage top / Right rail** selector, four size buttons **(S / M / L / Tall)**, **Fold** and **Hide**. Moving a card is the same edit whether you drag it, click the buttons or use the keyboard (arrow keys, Alt+arrows between regions, Shift+arrows for size, Enter to fold, H to hide, Escape to finish) - all three are proven to save the *same* layout. **Every dot is a real button**; the four protected cards (Waiting for you, Stop everything, the voice controls and the Jarvis-bar button) can be folded but never hidden or moved out of reach, and the approvals card still expands by itself when a card is waiting without rewriting your layout. Changes save themselves (400 ms debounce, flushed when you press Done or Escape), the editing bar says whether the PC actually kept it, Undo covers the session, and Reset to preset puts back the preset you chose in Settings. **Privacy and safety did not move:** the layout holds card positions and names, no private data, so there is no approval card; the app-lock, stale-link and approval rules are untouched; and this is the ONLY new permission the HUD page got (its own layout write, owner-approved), with Rust still validating every saved document. **Honest limits:** the main stage (conversation, Galaxy, the composer) is fixed in this slice; import/export of a layout (copy/paste JSON), custom presets and the non-hideable safety banners come in H3/H4; and touch drag on a real touch screen is NOT-TESTABLE here - the keyboard and button paths are the guaranteed alternatives. Tests: `jarvis-desktop/tests/hud-edit.mjs` (pure reducer: every action, protected refusals, 200 seeded actions all normalizer fixed points, the card/DOM map, and the measured 180-line drag budget) and `jarvis-desktop/tests/hud.mjs` (the real page: mount/exit, drag = click = keyboard, protected controls, derived approvals expand, debounce, DPR 1.5, reduced motion, no page errors). Docs: `docs/ARCHITECTURE.md` §8 and `docs/DECISIONS.md` (2026-10-22).
- **The test runner can no longer test live code by accident (2026-10-21, Ruling 11).** `JARVIS_BACKEND` is set for the owner's Windows account on this PC and points at the LIVE backend folder, and `backend/run_suites.py` used to read it whenever it was set - so a routine `python -B backend/run_suites.py`, the line the README and every agent runs, tested the live folder without anyone choosing that. It is now **hermetic by default**: the ambient variable is popped and a throwaway copy of the shipped modules is staged (exactly what CI runs), with one note line saying so. Two explicit live modes exist, each announced with a `LIVE MODE` banner: `--use-env-backend` (whatever `JARVIS_BACKEND` names) and `--backend-path DIR` (that folder outright - which the updater now passes, so an update's proof run can never be redirected by an environment variable). A missing value or a non-folder is refused in plain words, never silently replaced by a staged copy; `--state-env` is unchanged (it is the patcher's own subcommand, which sets the variable explicitly for its child). Tests: `backend/test_suites_env.py` - the canary proof bites, ten of its checks fail against the old runner and all 22 pass now. Docs: `backend/README.md`. No deploy needed.
- **The memory search now runs on ONNX Runtime directly, the vectors are unchanged, and Pillow 13.0.0 comes in with hashes (2026-10-21).** `backend/rebuilt/jarvis_memory.py` and its byte-identical twin `jarvis-backend/jarvis_memory.py` no longer hand their two models to the `fastembed` library: they run them on `onnxruntime` themselves, turn text into the models' numbers with `tokenizers`, and fetch a model from Hugging Face once with `huggingface-hub` - those three are now named in `backend/requirements.txt` and already pinned in both copies of `requirements.lock`. The models are the same two - `BAAI/bge-small-en-v1.5` for meaning and `Xenova/ms-marco-MiniLM-L-6-v2` for the re-ranker - and **the vectors are bit-identical, measured on this PC**: both models ran through fastembed and through the direct path over the same corpus, every float32 compared equal, so the model name the store keeps does not change and **no saved fact is embedded again**. The models a build can run are now static lists copied from fastembed 0.8.0 - `ONNX_EMBED_MODELS` (28: its embedding list without `jinaai/jina-embeddings-v3` and `Qdrant/clip-ViT-B-32-text`, which needed a model-specific recipe) and `ONNX_RERANK_MODELS` (6 cross-encoders) - plus `MODEL_PINS`, the SHA-256 pins for the two default models from the 2026-10-18 supply-chain audit (M8). `fastembed` leaves the lock with `loguru`, `mmh3`, `py-rust-stemmers` and `win32-setctime`, and `tools/model_tryout/memory_tryout.py` moves onto the direct path too: it lists the models from those two registries and loads each one through `jarvis_memory.OnnxEmbedder` / `OnnxReranker` before its run.

  **Pillow 13.0.0, and the lock's Python floor moves to 3.11.** Pillow 12.3.0 carries 24 known security advisories that only 13.0.0 fixes (no 12.x release does), and 13.0.0 has no Python 3.10 build, so the lock's coverage line moves to Python 3.11 and newer - the code itself still imports on 3.10, and only the pinned install needs 3.11 now. It is one deliberate exception to the lock's 7-day wait (13.0.0 was uploaded 2026-10-16, five days before the lock was made), taken the same way as the markitdown and rapidocr exceptions, with its published wheel hashes in the lock so `tools/check_python_advisories.py` goes green.

  **Said plainly:** the re-ranker's scores measured bit-identical on this PC too, but the two newer meaning models the tryout page used to name - `Qwen/Qwen3-Embedding-0.6B-Q` and `google/embeddinggemma-300m` - are **no longer available to a tryout**: they only arrived in fastembed 0.8.1, which the locked install never took, and the direct path runs fastembed 0.8.0's own list, which does not have them, so the tryout says so in plain words instead of failing. The parity claim is a measurement on this PC: the dev container cannot download the models, so there the proof is the hermetic recipe test (`backend/test_memory_onnx.py`) with the captured golden vectors (`backend/memory_embed_golden.json`, made by `tools/gen_memory_embed_golden.py` while fastembed was still installed), and `tools/check_onnx_parity.py` re-checks them against the direct path on the PC; `backend/test_pillow_pictures.py` is the Pillow-13 smoke test.
- **The Galaxy has three lenses now - Memory, Neural and Unified - and every dot in them is a real button (2026-10-21, Galaxy v2 slice G1).** The HUD window's brain map used to be one picture of whatever `GET /api/graph` returned. It now has a three-pill lens picker in its own header: **Neural** is the PC's capability graph (the local brain, the cloud lanes, the ability groups and the abilities the PC's own config enables), **Memory** is the saved facts, documents, knowledge entities and projects - drawn exactly as the PC sends it, so the PC's lock rules still redact it when the owner has hidden memory lists - and **Unified** shows both with a counts line that says which half is which. The counts are **computed from the graph payload**, never typed into the page (2 brains, 1 ability group, 2 abilities come from the nodes), and the lens is remembered like the theme and layout choices. Nothing is drawn only on the canvas any more: every dot is also a real focusable HTML `<button>` with an accessible label, so a keyboard or screen-reader user can Tab to a node, press Enter, and get the same inspector the mouse opens; arrow keys walk the nodes. The slice is **page-only** - no new backend route, no allow-list change, no Rust change, no new dependency - because the graph it splits was already read through the shell's fixed proxy. Honest limits: the Memory lens shows names and counts, not the per-entity facts list (Brain keeps that, and `/api/memory/entities` stays unreachable from this window), and the active lane/preset cannot be marked on a lens because `/api/presets` is not reachable either. It is the desktop HUD's alone - a phone has no HUD window and the memory graph stays off the phone. Tests: `jarvis-desktop/tests/hud.mjs` drives all three lenses over a stub graph, proves the counts follow the payload (a changed graph changes the words), Tab-reaches and opens a node in every lens, checks an empty Memory lens says so instead of inventing content, and reloads to prove the lens is kept; the five Brain-window `galaxy*.mjs` suites are untouched and still pass. Docs: `docs/ARCHITECTURE.md` §8 and `docs/DECISIONS.md` (2026-10-21).
- **The HUD now has its own Reminders tab, one click from the stage tabs, and it can add and act on the PC's real schedule (2026-10-21, owner-requested; Phase 1).** The owner asked for a dedicated Reminders menu in the HUD with real versatility. The scheduler already existed (`jarvis_schedule.py`: timers, alarms, reminders, to-do items, named lists and the one-job actions), and the Brain window already showed it as Coming up; the HUD had **no** reminders screen and its page holds **no pairing token**. Phase 1 is HUD page + Rust only, with **no backend or deploy change**: `GET /api/schedule` joins `hud_proxy.rs`'s fixed read list, and while App lock or "Hide memory lists" is on the HUD read gets the **same Rust word redaction the Brain window uses** (`brain::schedule::redact_list` - words blanked, kinds/times/counts kept, named lists become "hidden-1", so a page script cannot read round it). The new Studio stage tab and dock icon (plus the Cockpit Bento card and the Ambient rail) draw grouped sections - Just went off, Timers, Alarms, Reminders, To-do, each named list, other schedules - from the PC's own answer, with the when/repeat/list lines it sends. The Add form takes what to add, kind (reminder/timer/alarm/to-do), date and time or timer minutes, a repeat rule (once/daily/weekdays/weekly/custom days), a named list and optional notes, and sends ONE item through the new HUD-scoped `hud_schedule_add`; each row's existing actions (snooze after it fired, add time on a timer, pause/resume, done, delete) go through `hud_schedule_act`. Both commands are **held on a stale link** like the Brain's, raise **no approval card** (they only add or quieten), and the page's own POSTs stay refused by the bootstrap shim (audit M2). **Deliberately NOT here:** clearing a named list or any delete-all (Ruling 15 - the Brain keeps that), and editing an item's words/time/repeat, moving it between lists or reordering (Phase 2: they need backend actions and a rank column, so a later deploy - not faked in the page). Docs: `docs/ARCHITECTURE.md` §8. Tests: `jarvis-desktop/tests/hud.mjs` gained seven checks (the tab from keyboard and dock, the grouped rows, the lock rows never blank, the exact add bodies, each row action's id and do, a direct POST refused, the three byte-identical HUD copies and a read-only allowlist); the Rust suites cover the allowlist, the redaction and the form bodies.
- **Barge-in with echo cancellation gets a design and an off-by-default prototype, and nothing on the PC changes yet (2026-10-21, Voice Slice F).** The owner approved the whole Live & Voice program; its largest and riskiest slice is interrupting Jarvis on open speakers. The premise was checked against the real code first: `#660 F3`'s self-echo block (`jarvis_speech._SPEAKING_UNTIL`/`is_speaking`, `ECHO_TAIL_SECONDS = 0.25`) refuses the automatic path while Jarvis speaks, so today the only interruptions are the wake word, the word "stop" (the small stop-word model), and the shipped two-step barge-in path (500 ms of speech tells the bar to pause; the first 2 s go to the PC as `source=barge_in` and the owner print decides over a clip that still holds Jarvis's own voice when Windows' driver echo cancelling is not active - and that path's own Rust module says it has never run on Windows). This slice adds a **reference-subtraction** echo canceller: the PC knows the exact TTS PCM it generated, a small NLMS filter learns the echo path, and what is left is judged for 350 ms of speech-shaped sound plus the owner's voice check. It is **no-new-dependency** (numpy only), **off by default** (`[voice] aec_barge_in = false`), **not wired to anything** and **decision-only**: no playback is changed and no live voice module is touched. The phase-1 suite uses deterministic synthetic signals only - synthetic echo is cancelled by about 50 dB ERLE, a synthetic owner over it produces one `should_stop: true` decision 0.36 s after speech onset, a wrong speaker and a missing/raising owner check fail closed, and pure echo, white noise, a music-like chord and amplitude-modulated noise produce **zero** false cuts - and all of it is labelled SYNTHETIC. **Real open-speaker barge-in is NOT-MEASURED** until the owner's microphone and speakers are used, and the switch stays off until then; if those numbers are poor, speexdsp/WebRTC becomes a separate decision with a `requirements.lock` change. Docs: `docs/DESIGN-VOICE-BARGE-IN.md` and `docs/ARCHITECTURE.md` §8; tests: `backend/test_barge_in.py`.
- **A read-only flight price radar exists, off by default, and it is not a booking tool (2026-10-21, anti-surveillance price/flight stack, slice F1).** The owner approved the whole stack; F1 is the flight engine and the price history. `backend/jarvis_price_radar.py` (new shipped twin, no new dependencies) builds Google Flights' `tfs` parameter in pure Python adapted from the MIT `punitarani/fli` and `AWeirdDev/flights` projects - the suite stores their recorded golden tokens and proves **byte parity** - reads the public search page's inline `ds:1` payload with a tolerant parser that keeps prices as **integer whole cents** and answers `unavailable` rather than inventing one, and records a SQLite history (`price-radar.db`, versioned schema, #673 pragmas) with a last-known-good snapshot and stale-on-failure semantics copied from `jarvis_tellme`. A real change is outside text, latches `jarvis_gate.latch_taint(why="price_radar")`, and is worded in dollars with the approved footer and target/low notes. **The endpoint is UNOFFICIAL** (a public search page, not an API) and may break - said in the module, the config and the design doc - and **it is a price radar, NEVER a booking tool**: no cart, no seat hold, no checkout, no PNR path. Hard invariants, each tested: one read-only GET of one https host; no cookies/authorization/cache validators; a 403/429 is `blocked_by_site_challenge`, stale, one attempt, no retry; strict SSRF allowlist refusing loopback/RFC1918/link-local/CGNAT and redirects; no proxy support in F1; hard poll floor 300 s +/-30% seeded jitter. **Off by default** (`[price_radar] enabled = false` in both shipped toml copies); on is one card, off is immediate, and no check runs until on. **NO live request is made in the suite** and the endpoint's real payload is NOT-MEASURED until the owner enables it. Docs: `docs/DESIGN-PRICE-RADAR.md` and `docs/ARCHITECTURE.md` §8; tests: `backend/test_price_radar.py` (119 checks).
- **The owner check starts on the first second of voice, and Smart Turn's features are built as the audio arrives (2026-10-21, backend latency plumbing; part of the owner-approved Live & Voice program).** Two backend changes, no new dependencies, CPU only. (1) `jarvis_turn` gained an in-process fast path: `predict_pcm()` takes raw 16 kHz mono int16 PCM with no WAV encode, no base64 and no HTTP, and `TurnStream` builds Smart Turn's 80-band log-mel picture incrementally from the 32 ms VAD chunks (`MelStream`) instead of re-FFT'ing the whole 8 s window at end of turn - the cached raw frames are corrected for the window's mean/variance analytically, and the old `features()` is kept unchanged as the reference every incremental case is compared to (within 1e-2 on the (x+4)/4 picture; a caller whose chunks never align just gets the old cost back). The route also accepts raw int16 PCM bodies now (sniffed; old WAV clients and the desktop are unchanged), and the ONNX session stays cached and CPU-only. (2) `jarvis_speech.hear()` asks the same owner check on the clip's **first ~1.2 s of voice** (`[voice] early_verify_window`, default 1.2, 0 = off) and decides on it only when the score is at least `early_verify_margin` (0.06) past the bar one way; anything inside the band is re-checked on the full clip exactly as before, and a dead verifier falls back to the full clip rather than being trusted. **The privacy rule has not moved:** the words are still made beside the check and, when it says no, the worker is joined and its answer discarded unread - and a refusal still costs the transcription, so timing does not reveal verified-vs-unverified. `StreamingVerify` is the same rule for a caller that feeds chunks while the owner speaks; the desktop does not yet feed it that way. **No hardware latency is claimed:** **An early verdict is bound to one recording (Gemini's sign-off ruling 10.4):** each `hear()` builds and purges its window worker, `StreamingVerify` clears its worker/buffer in `verdict()`'s `finally:` and offers `abort()`, so a second utterance (or an aborted one) can never inherit the first's early verdict - three regression tests cover reuse and abort. the CAM++/Parakeet and Smart Turn times are test-mode stand-in numbers only (no weights, no microphone here), and the owner's spoken-sentence before/after stays NOT-MEASURED until his retrain and measurement. Tests: `backend/test_voice_parallel.py` (which check ran and on how much audio, borderline fallback, switch-off, worker failure, refusal cost kept, every unverified-clip sink, streaming end-of-speech wait), `backend/test_live.py`, `backend/test_turn.py` (incremental-vs-reference tolerance, end-of-turn frame counts, repeated-probe cost, raw-vs-WAV equality, bad raw input). Docs: `docs/JARVIS-API.md` (the route and the check), `docs/ARCHITECTURE.md`, and this entry.
- **The big Jarvis window now fits the window it is given, and says its status once (2026-10-21, field fix).** The owner's installed app exposed two defects. (1) The HUD came back at 815x691 although its declared minimum is 960x640, and its layout picker and right-hand controls were off-screen; the app remembers window sizes, and Windows accepts a programmatic resize below the minimum, so the saved size used to win. The restore path now clamps a restored size up to the declared minimum (`window_memory.rs`), and the HUD page itself wraps its stage header and drops the Cockpit to one column at 720 CSS px - because the app's own Text-size / Ctrl+= zoom shrinks the CSS viewport without changing the window, which is what made a 1580-wide window still look clipped. Measured: no horizontal overflow and all three layout pills inside the window at 960x640, 1280x820, and every CSS width from 466 to 1580 the zoom can produce; below 1080 the right Bento rail is the existing drawer, opened by the rail toggle. (2) The duplicate status lines were real, not a capture artifact: the page's boot-time row showed `ONLINE · LOCAL FIRST` and the shell's injected line showed `LINKED · LOCAL FIRST` directly beneath it. There is one row now, and it fits on one line in the 191px rail: `online · linked` (or `online · reconnecting`, `no model · linked`), with the full sentence `online · local first · linked` in the row's tooltip - the long form measures 204px and wrapped into two lines, which would have been the same defect inside one element. When the link is down the row says the link's own words alone (`offline · …`), because without a link nothing about the model is known. The shell pushes the link words to the page and only draws its old line for an older page that cannot take them (the live page is copied separately from the app). Everything keeps its id: the three layouts still switch and persist, the lane warning still shows, and the HUD's replace-confirm two-press cards still take two presses. Tests: `tests/hud.mjs` gained a one-row status check (both truths once, no second line, fallback line still drawn for an older page) and two window-size checks (960x640 and 1280x820: the picker and right rail reachable, no horizontal overflow, all three layouts switching and persisting); `window_memory.rs` gained four clamp tests.
- **The big Jarvis window now has three looks to choose from, and a pill in its own header to switch (2026-10-20).** The owner asked for "3 different UIs for the jarvis HUD in the settings... looking cutting edge while still being intuitive and effective". All three are the ONE HUD page, switched instantly between **Command Cockpit** (the default - navigation and the brain switcher on the left, the Jarvis core and conversation in the middle, Bento cards on the right: the live waiting-cards count with an "irreversible" warning when one cannot be undone, the second brain's four counts as clickable tiles that open the Galaxy map, and the last-turn numbers that stay out of the way until a turn has run), **Studio Split-Workspace** (a slim icon dock, the conversation on the left, and a live Inspector Stage on the right whose tabs show the real Galaxy map, the real approval cards, the real memory readouts and the real telemetry - side by side, nothing duplicated) and **Ambient Voice Core** (no sidebars: a 320px core with layered orbital rings, two floating glass pills carrying status/model/latency and the view switches plus the live approval badge, the latest exchange as a centred card with a "Show full history" drawer, and a centred composer). **Everything is built from what the window already had** - its two views, its approval cards, its telemetry and memory - so no Today, Memory or Vault screen is invented, every control keeps its own id, and the page's own tests still drive it. Two ways to choose: Settings -> "The big HUD window", and the layout pill in the HUD's header; both write the same per-computer preference (`hud-window.js`'s `jarvis.hud.layout`), exactly like the "Open the Jarvis bar" switch beside it - **cosmetic, no approval card, no Rust command, no backend route**, and an open HUD obeys a change made in Settings at once. The phone has no HUD window, so it has no row (`docs/ARCHITECTURE.md` §8). **Not tested here: how it looks** - a colour and spacing judgement needs the owner's screen, and the tool that finds flat grey regions needs the window on it, so both are NOT-TESTABLE; what is proven is that each mode switches and persists, keeps every id, and works (`tests/hud.mjs` drives send, tabs, the drawer, the badge and the tiles in all three; `tests/hud-window.mjs` covers the setting itself without a browser). The Jarvis bar's own redesign is a separate slice and is not touched here. Docs: `docs/DECISIONS.md` (2026-10-20) and `docs/ARCHITECTURE.md` §8.
- **Talking to Jarvis is about 140 ms quicker per clip, and a stranger's words are still thrown away (2026-10-20).** The owner chose all three voice-latency items on Gemini's work order; **two were already on `main` since 2026-09-24** and were deliberately not retuned (Smart Turn v3.2's early end-of-turn cut on the PC and the phone, and speech already starting at the first comma from the live token stream - the work order's own numbers for those are slower than what shipped). The one that was missing is now built: `jarvis_speech.hear()` used to run the owner-voice check (~140 ms of CAM++) and **then**, only if it passed, the transcription (~219 ms of Parakeet) - one after the other on every clip he speaks. They now run **beside each other on the same in-memory audio**, so a clip he speaks is ready ~140 ms sooner. **The privacy rule keeps its promise and only its wording moves**, from "verified before the words are made" to "verified before the words are used": when the check says no, the worker is joined, the transcript is discarded (`text = ""`) and it is never returned, logged, stored, learned from or sent to any model - no thread outlives the request. The costs are said plainly: a stranger's clip now costs one local transcription that is dropped unread; a **refused** clip answers a little later, not sooner (the discard waits for the worker it started, so a refusal costs the longer of the two steps - ~219 ms rather than ~140 ms); and the first clip after a restart may load the speech-to-text model before the check instead of after it (Live's Start pre-warms it). With no speech-to-text engine installed nothing is started at all, and the check-only path of a Live voice pause keeps the old serial order. **Not measured on real models here - NOT-TESTABLE:** this repository has no CAM++/Parakeet weights and no microphone, so the proof is the mechanism (a slow-stand-in test shows the transcription starting before the check ends and the call finishing in less than the two sleeps added, and spies on every sink show an unverified clip's marker word appearing in none of them) - `backend/test_voice_parallel.py`, plus the updated order tests in `test_live.py`, `test_talk_type.py` and `test_speech.py`. Reverting to the serial order reddens the overlap and discard checks; a version that returned the discarded words reddens the sink checks. Docs: `docs/JARVIS-API.md` section 5, and the dated decision in `docs/DECISIONS.md`.
- **The job list's background step runner was audited, and deliberately left switched off (2026-10-18).** `jarvis_tasks.JobList.tick()` - the method that would run one step of a job from the "Jobs that keep going after the chat ends" list - was recorded on 2026-10-15 as having **zero production callers**. This audit answers the question that record left open, with the code as evidence. **It is not a duplicate of `jarvis_jobs.run_due()`** (the Long Fuse background queue): `run_due()` runs whole jobs against the capability set frozen on their row, while `tick()` runs ONE step of a job whose steps were listed up front and whose executor and approver are supplied by the caller - two different queues, already drawn apart in `docs/AUDIT-JOB-LIST-2026-10-08.md`. **But it is not wired, because both halves of an honest caller are missing:** nothing in the program creates a job in this list (the plan card that would is still switched off, and the HUD routes only list and steer), and nothing can run a step in the background - the only real step executor is built inside a chat turn (`jarvis_agent._plan_step_dispatch`, from that turn's watcher, gate checker and output). Calling `tick()` from the one heartbeat with a stand-in runner would move rows while no tool ran, so the decision is recorded in the module's "WHO TICKS IT" docstring and `docs/ARCHITECTURE.md` instead of pretended in code. What the audit DID add is the guarantee a future wiring will rely on: `backend/test_tasks.py` now proves **two ticks - sequential or overlapping - can never run a step twice**, that a step, a card or an activity-ledger write that raises is contained so later ticks still work, and that the job list cannot start itself (no thread, no timer, and the one production heartbeat does not even import it). No behaviour changes: nothing new runs on the owner's PC.
- **The highlighted text is only accepted from the window whose privacy rules passed (2026-10-18).** The selection read checks the window in front against the screen's own Never-look rules (password managers, bank sites, private windows, the lock screen) before it reads anything - but the text itself comes from the FOCUSED control, and nothing proved those were the same window. A focus change in the few milliseconds between the check and the read could therefore hand the answer text from a window whose rules never ran, labelled with the old window's program. It now proves it: the focused control's own top-level window must be the window whose rules passed, and the window in front is read once more after the text is taken (so a tab or site change inside the same window is caught too). A mismatch is a plain refusal with no text. The backend checks this in `jarvis_ui_control.read_selection` with the existing `jarvis_screen.same_window()`; `backend/test_active_selection.py` gained the two mismatch cases (a focused control in another window, and a window that changes during the read) and keeps the read-after-check order test.

- **PC help now looks for four things that fail quietly, and says so in the same Check now (2026-10-17).** Pillar 28's silent-failure doctor runs inside `GET /api/pc/help` through one function, `diagnose_silent_failures()`: each finding adds its own warning section after the five answers - and only when it fires, so a healthy answer is still exactly the five sections both apps were built for. (1) **`digital_zero_mic`**: `jarvis_speech` remembers the **peak RMS** of the last three voice attempts, their input device and when (numbers only, in memory - never audio, and PC help never opens the microphone); three in a row at exactly 0.0 means a microphone that has gone digitally deaf - the state some PCs leave it in after sleep - not a quiet room, and the words name the device ("this PC's microphone" / "your phone's microphone") and say to unplug and replug it or restart. (2) **`wal_bloat`**: every `*.db-wal` in Jarvis's home folder (`$OPENJARVIS_HOME` honoured, else the config folder) is measured; one past **64 MiB** is named with its size, the words say the database is healthy and the writes have not been folded back, that a passive checkpoint would fold it back - offered with its exact safe statement from `safe_passive_checkpoint_statement()`, `PRAGMA wal_checkpoint(PASSIVE);`, which deletes nothing - and that PC help does **not** run one because it only reads; restarting Jarvis checkpoints it and nothing is deleted. (3) **`phone_unreachable`**: each paired phone with remote reach (a live device key; this tree has no separate "also on my phone" switch) is read for its last check-in; a week without one says its changes have not synced, that this PC cannot test Tailscale or Meshnet itself, and to open Jarvis on the phone on the same network and use it once. (4) **`ollama_wedged`**: one loopback `GET /api/ps` with a 2-second timeout tells the two silent failures apart - the process is not running (its TCP port refused) vs running but wedged (the port opened and `/api/ps` timed out) - and gives each its own fix ("open Ollama from the Start menu" vs "quit it from the icon by the clock and open it again"). Every check is deterministic and read-only, one that cannot read says nothing rather than inventing a failure, and the warning sections name no program so they are not private. Docs: `docs/JARVIS-API.md` §84.5 (the four ids, thresholds as `N_placeholder`, and what it deliberately does not do). Tests: `backend/test_pc_help.py` 168 passed, 0 failed (on top of #534's checks) - the meter, `diagnose_silent_failures()` returning id/title/words dicts, every boundary (3 vs 2 zero-RMS attempts, 65 MiB vs 10 MiB and exactly 64 MiB, stale vs healthy vs exactly-at-threshold peer, `/api/ps` timeout vs 200 OK), all four failing as four ordered sections, and every reader throwing as no section; `backend/test_devices.py` 349 passed, 0 failed. Both apps' `pc-help-cases.json` copies were regenerated with a healthy `silent_healthy` case (every case still has five sections, because their contract tests demand exactly those five), and every case carries the new `silent` key. **Bite-proved with 5 mutations, each red exactly where it should be:** the microphone threshold, the WAL limit, the phone staleness, the stopped-vs-wedged split, and the speech meter itself.
- **The update button now asks how hard it should work, and shows a progress bar that is real (2026-10-17).** "Update everything" used to be one fixed run: the patch program applied every patch and then ran every test suite one at a time, and the card could only say a count. Pressing it now offers **three paces** - **Fastest** (`max_speed`: 22 suites at once, nearly the whole PC), **Balanced** (`responsive`: 14 at once, the default and the recommended one) and **Safest** (`safe`: one at a time) - each with a plain sentence and an ETA **range**. All three run **exactly the same suites**; only the number in flight changes, and an unknown pace is refused before anything starts. The ETAs are honest by construction: the first run says **"first run - not measured yet"** and shows a wide range; after that each suite's own seconds are recorded in `<backend>\_jarvis-logs\update-timings.json`, the next estimate says **"from this PC's own times"**, and the range narrows. During a run the estimate is refined from the suites that have actually finished. The new **progress bar** is painted only from the update tool's own events: its fraction is completed work - patches applied, then finished suites **weighted by their recorded times** - so it never moves on a timer, never goes backwards within a pass, never reaches 100% before the final verdict, and holds its last real value if an event is missing. If a quick pace hits a problem (a failed or ambiguous suite, a crashed worker, or the live files not matching this repository), the update is **not trusted**: `tools/update_backend.py` puts every file back from the newest `_jarvis-backup-*` (copying, never deleting it), re-runs the patcher and **all** the same suites with one worker, and the card says so - **"quick check hit a problem - re-running the safe way, new ETA"** - with the bar starting a labelled **"second pass (safe mode)"**. The final honesty lines are unchanged: "ALL DONE - the backend is patched and proven", "DONE - no problems, but NOT fully proven", or "DONE WITH PROBLEMS", and "updated both halves" still needs both halves `ok`. The desktop only, on purpose: a phone cannot patch a PC's backend (`docs/ARCHITECTURE.md` §8). Written up in `docs/ONE-UPDATE-FOR-BOTH.md` §8; the tool's own suite is `backend/test_update_backend.py`, and the card's is `jarvis-desktop/tests/update-both.mjs`.

- **Jarvis Live no longer blames you when Android is what stopped it (2026-10-17).** The owner's Pixel 9 tapped Live, heard nothing, and its end screen said **"Jarvis Live ended - You ended it."** above "Android did not let Jarvis Live listen from the background." He had ended nothing. Two different events were sharing one sentence: Android refused the microphone foreground service (Android 14+ will not start one from the background), and the end that followed reached the PC with no reason, so it became `owner` - the PC's words for "You ended it." **The phone now says which failure it was:** Android's foreground-service refusal is `fgs_refused`, a missing microphone permission is `mic_permission`, anything else is `mic_stopped`, and the PC words each one with its own sentence; an end nobody explained is now `unknown` ("Live ended.") and **never** `owner`. The decision is one pure function (`LiveRules.stopForClasses`), so the phone's JVM tests run it without a device - there is no device fix claimed here, and no `adb`/`logcat` needed from the owner: **the next attempt will tell us on the end screen itself which refusal it was.** The shared table `live-cases.json` now carries every reason, the PC's words and the phone's own "listening stopped" line for it, plus the closed list of reasons an app may send; both the phone's JVM test and `backend/test_live.py` read the same entries, so a clean merge cannot leave the two sides wording one end differently. Docs: `docs/JARVIS-API.md` §63.1-63.2 and `docs/LIVE-DESIGN.md` §2.

- **A price rise that repeated used to vanish from the subscriptions answer - fixed, and both apps now test the same fixture (2026-10-17).** The radar added earlier that day compared the **latest two charges**: when the new price was charged a second time (a second month at it, or the new price billed twice in a week) the last two amounts were equal, so *9.99 -> 12.99 -> 12.99* reported **no rise at all**, even though the price had gone up by 3.00. The comparison is now against the **price before the latest charge** - the most recent charge at a different amount, **at least a whole billing cycle earlier** - so a repeated new price can never erase the rise that produced it (the third month still reports *+3.00*, and a fall is still never reported as a rise). **And the same review's second finding is fixed**: a different amount charged inside the *same* bill (a one-off rental beside the monthly subscription) no longer reads as a price rise, and when the newest bill day has several different amounts the merchant is not compared at all - a missed rise rather than a false alarm about your money. Second, the answer is now a case in the generated **cross-app contract** (`spending-cases.json`, table `subscriptions`): the desktop renderer and the phone's strict reader are tested against the same columns, order and figures - including that repeated-price rise and a double charge whose 11-digit account number is hidden to *[hidden]* - so the two apps cannot drift from the backend's numbers; the phone's list of "real tables" now reads seven. The bug was found in **Gemini's review** of the answer slice, not by the tests: they had checked a rise followed by a *different* amount, never a rise followed by the *same new* price. Tests: `backend/test_spending.py` is **765 passed, 0 failed**; section 11 is 16 test functions / 74 checks (the new ones pin the repeated price, the unchanged price, a rise back to a price seen before, and a different amount inside the same bill); the generator is run so both copies of the contract match; the desktop suite is 33/0 locally (and the phone suite reads the same JSON with a stricter parser). Bite-proved: reverting the comparison turns the new tests red, and changing one figure in the shared fixture turns the desktop contract check red.

- **The PC doctor now reads each graphics card's own state, and never mistakes rest for a fault (2026-10-17).** PC help's `gpu` and `heat` answers - and "why is my PC slow" when the processor and memory look calm - now name **every** card however many are installed: one, the two here today, or three when the planned second RTX 2080 SUPER arrives. Each card gets its own memory in use, how busy it is, and a plain state: resting, fine or warm, hot and slowing itself down, at its power limit (normal while working), or nearly full, with what to do about it (use a smaller model in Brain > Model, or turn a feature off). Two cards with the same name and size reuse the Hardware page's twin naming (`jarvis_profiles.card_label`): "on your monitor", "(headless)", and the card's own id tail when the monitor cannot say - never a bare identical name twice. **Measured, and the reason for the classifier:** at rest both cards here sit at P8/300 MHz, the RTX 2060 reports its power-cap reason `Active` while idle, and the RTX 2080 SUPER reports its idle reason `Active` - so `jarvis_hardware.card_state()` reads pstate + clocks + load, never one flag, and only the driver's own thermal slow-down reason is called "slowing itself down". **The one thing this PC's driver does not measure:** `nvidia-smi --query-compute-apps` names which programs hold a card but answers `[N/A]` for every amount (measured today, including the two `llama-server.exe` on the 2060) - so the words list the programs, say plainly that it cannot show amounts, cap the list at three names plus "and N more" (23 were on this PC's 2080 SUPER when measured), and label Windows' counter totals as "their total, not one card", never a per-card figure. **Under the hood:** `jarvis_compute.parse_apps`/`query_apps` (the same cached, never-raising shape as `query_cards`); `jarvis_hardware`'s health query grows `pstate`, the clocks, idle and power-cap fields with a five-shape refusal cascade for older drivers; `_card_row` gains `pci_id`/`index`/`used_gb`, and a card seen without Ollama's log keeps its PCI id (the planned pair of identical 2080 SUPERs can only be told apart by that id when the log is missing). **Tests:** `backend/test_hardware.py` 183 passed, 1 skipped - state classifier, idle-not-throttled, power-limit-is-normal, older-driver fallback, log-less identity; `backend/test_pc_help.py` 121 passed - 1/2/3-card readings, twin names, resting/hot/nearly-full words, `[N/A]` never becoming a number, per-card program lists with the cap. Both case generators were run for real and their `--check` is clean (desktop and phone fixtures byte-identical). **Bite-proved with 8 mutations, each red where it should be:** the hot sentence removed, the power-cap flag trusted, the idle flag trusted alone, pci id dropped without the log, the per-card loop cut to two cards, a missing amount printed as 0, identical cards no longer told apart, and three cards refused. No new module, no approval card (PC help only reads), nothing new stored, sent or learned. Docs: `docs/JARVIS-API.md` section 84.

- **You can ask Jarvis about your subscriptions now, and it reads them out of your own bank files (2026-10-17).** Pillar 10's first half merged that morning as a pure function with no way to reach it; this is its answer. Ask in chat - *"did any of my subscriptions go up?"*, *"was I charged twice?"* - and the `my_spending` tool's new `subscriptions` action reads every bank file that already has a saved layout (or one file by `path`), finds the shops that bill about once a month (26-35 days apart) or once a year (350-380), reports **the exact rise in cents** when the latest charge is higher than the one before it, and reports the same shop charging the same amount **twice within 6 days or fewer**. **Neither app needed a change**: the answer is the same table block the spending answer already uses (`What` / `How often` / `Last charged` / `Amount` / `Went up by`, one section per currency, the double charges as their own rows; the title is "Subscriptions and price rises", "Subscriptions" or "Charged twice" by what was found), so the desktop and the phone draw it with their ordinary renderer - private, never read aloud, never remembered, nothing new stored, sent or approved. The model still writes only ONE sentence round it and may quote only a figure the table shows; it is given each shop by its clean stem (a trailing store number or reference removed), never the raw description and never a charge date, and a sentence that invents a figure - or a year the table does not have - is dropped. A quiet radar says *"I found no subscriptions, price rises or double charges in your bank files."* rather than drawing an empty table. **Deliberately not here:** the pillar's mail half (trial-ending and delivery emails) - it belongs with the module that owns IMAP, `jarvis_email.py` (the handoff that asked for this slice named a `jarvis_mail.py` that does not exist in this repository). Docs: `docs/JARVIS-API.md` section 100.3 and `docs/FINANCE-DESIGN.md` section 11. Tests: `backend/test_spending.py` section 12 - 7 test functions and 38 checks: the strict block shape both apps enforce, the doubling found end to end through the real hiding path, the model's payload proven free of the table, dates and raw names, the invented figure and wrong year dropped, a quiet radar, and a whole scripted chat turn including the one-table-an-answer refusal. Bite-proved with 9 mutations, each reddening exactly its own checks.

- **The 2026-09-30 batch is finally in this file, three weeks after it shipped (recorded 2026-10-16).** `docs/JARVIS-API.md` §99 to §113 all landed on **2026-09-30** and **not one of them had an entry here** - the gap the 2026-10-04 feature review wrote down as *"No entry for §99-§114"* (`docs/FEATURE-REVIEW-2026-10-04.md:540`), and it stayed open because every pull request since added its own entry **above** it rather than going back for the missing ones. Recorded now, by section, with the API doc itself as the authority for each: **§99 chat tags, sections and "Fork from here"**; **§100 spending summaries from a bank CSV or Excel**; **§101 goal step locks and the finish-time range**; **§102 review decks and Spanish practice** (py-fsrs); **§103 retirement what-if**; **§104 overnight suggested tags** (cards only, off by default, up to three a night); **§105 the activity heatmap and balance chart**; **§106 the "New section here" divider**; **§107 topic controls** (include or exclude a topic in Jarvis's brain, four modes); **§108 the second card's Study helper and Referee switches** (built, switched off); **§109 menu visibility - "Show or hide menus"**; **§110 Fork a chat**; **§112 the YouTube captions quiz** (one card per link); **§113 "Grade this better"**, one quiz sent to a cloud AI service. What that batch's own docs say about it at the time is in `docs/HANDOFF-2026-09-30.md` and `docs/BUILD-QUEUE-2026-09-30.md`, both kept as the record of that night. **§111 is deliberately not here, and is not missing:** that number is reserved by `docs/GITHUB-TOOLS-DESIGN.md` for the GitHub tools, which that design still describes as *"designed, not built"* - there is no feature to write about, so the number stays free for it.

- **A sensitive answer stays on screen in the HUD too, and is not read aloud (2026-10-16).** The owner's decision, in his own words: *"Gate it - keep sensitive answers on screen in the HUD too."* The finding behind it, measured: the HUD window (`jarvis_hud.html`) reads **every** answer aloud with the browser's speech synthesis (`:2053` `voice.speak(full)`), and the only rule in front of that call was the bootstrap's local-voices-only wrapper (`hud_bootstrap.js` section 2e, which keeps Microsoft's "Online (Natural)" voices - which send the text to Microsoft to be spoken - out of the list). Nothing consulted `injected_sensitive`, `gate: "private"`, the question's privacy or the tools that ran. The HUD is the one surface that speaks **typed** answers (it has no voice input of its own; its mic button opens the Jarvis bar), so the setting *"Answers that use sensitive saved facts: Keep on screen"* - which reads with no typed/voice qualification - was true of the bar and false of the HUD.

  **What changed, and where.** `jarvis-desktop/src-tauri/src/hud_bootstrap.js` section 2e now wraps `speechSynthesis.speak` and refuses an answer whose route - the `X-Jarvis-Route` the HUD's own chat header already carries, `HudReply.route` - says `injected_sensitive` above 0, or `gate: "private"`. It is the Jarvis bar's own rule (`private-speech.js`: the sensitive check is the **first line** of `mayReadAloud`, and a PC that does not say how many facts were sensitive while `injected_facts` is above 0 fails closed), read off the same fact the page already draws its lane and gate from - not a new permission path, not a new setting, and one file. A route the window does not have (an older PC, a chat that failed) gates nothing, which is how the bar reads a missing route too. The local-voices-only check stays, in front of the same call; this gate does not replace it.

  **What he sees instead of hearing it:** the bar's own sentence, word for word - **"It's on your screen."** (`private-speech.js` `PRIVATE_LINE`) - drawn under the answer it is about (`hud-link.css` `.jarvis-kept`, `role="status"`, inherits the HUD's colours). No new owner-facing wording was written: the sentence already exists on every other surface for this exact fact.

  **The scope, said plainly, in the code and here.** The documented rule (`docs/JARVIS-API.md` §16 step 3) was written for a **voice** answer, and a typed question is otherwise allowed to be read aloud (`jarvis_voice.may_speak(private, origin="typed")` - "asked on your own device"). **That exception is removed in this one window, on his instruction, and nowhere else**: the bar, the widget and the phone are unchanged. A future reader must be able to see it was a decision, so the section comment in `hud_bootstrap.js` and `docs/DECISIONS.md` both say so in as many words.

  **Verified.** `tests/hud.mjs` gained two checks and is **66 checks, 0 failed**: one drives the real HUD window with `injected_sensitive: 1` (nothing reaches `speechSynthesis.speak`, the line is drawn **under the answer**, and the same answer with `injected_sensitive: 0` **is still spoken** - the control that says the gate did not kill HUD speech), and one drives it **once per route** over seven routes - facts-with-none-sensitive, one sensitive fact, a PC that does not send the count, no memory, the router's private gate, a route with nothing in it, and no route at all - holding each result against `private-speech.js`'s `usedSensitiveFact` plus the gate check, so the bootstrap's copy of the rule and the module's cannot drift. **Bite-proved**: with the gate disabled (`if (false && keptOnScreen(answerRoute))`), the first check fails with *"an answer that used a sensitive saved fact was read aloud in the room"* and the route table fails on exactly the sensitive route; with it restored, all 66 pass. `tests/private-speech.mjs` (28) and `tests/speech-pieces.mjs` (40) re-run green - the rule itself and the first-comma splitter are untouched. `tools/check_parity.py`, `tools/check_stale_twins.py`, `tools/check_docs_map.py` and `tools/check_claims.py` exit 0. **Not run: CI**, and nothing was driven on the owner's own machine - no audio was played and no window was opened on his screen.

- **NordLocker cannot encrypt the weekly snapshots, and the tool now refuses one instead of quietly writing into it (2026-10-16).** You asked for the weekly snapshots to be encrypted at rest with NordLocker, which is installed on the PC. **It cannot do that job, and this is measured rather than assumed.** Its vault `C:\Users\pcadmin\NordLocker_9019064` is not a locked disk: `fsutil reparsepoint query` reports tag `0x9000201a` (hydrate-on-open) and `0x9000301a` (hydrate-on-close) - Windows' own cloud-placeholder machinery, the same one OneDrive uses, and the reason `NordLocker.CloudFilter.dll` ships in the program folder. NordLocker also has no Windows service and no named driver, so nothing is left running to encrypt anything while its window is closed. **The test that decides it:** with NordLocker closed, a 40 MB file written into `NordLocker_9019064\My Files\` **consumed 42.03 MB of free space on `C:`** (131,066,798,080 bytes free before, 131,022,725,120 after) and `fsutil` said of that file *"The file or directory is not a reparse point"* - an ordinary local file, not a placeholder. Restarting NordLocker and waiting did **not** encrypt it. A real `SQLite format 3` file written the same way still began `53 51 4c 69 74 65 20 66 6f 72 6d 61 74 20 33 00` and still held its plaintext marker. **The locker folder is writable whether or not the app is running, so a weekly run pointed there would have SUCCEEDED, written your data in the clear, and reported OK** - the one outcome a backup must never produce quietly. So `tools/jarvis_data_backup.py` now **refuses a locker folder as its destination**, in code and before anything is written, with the alternative named in the refusal. The check sits in `check_destination`, the one function every destination goes through, so `--dest`, the folder you picked in the app and the built-in default are all covered by it - and the failure note a refused run writes cannot create the locker path either, because that note's own `mkdir` would otherwise undo the refusal it is recording. The weekly task also carries a **description** saying in plain words that the snapshot is **NOT** encrypted, so whoever finds `Jarvis Personal Data Backup` in Task Scheduler a year from now is not left to guess. **Nothing else changed:** the snapshots are still plain files in the folder you chose, the weekly run is still unsealed, and `--seal` with a passphrase is still how a hand-run is locked - an unattended run has nowhere safe to keep a passphrase. `docs/DATA-BACKUP.md` **replaces the sentence that recommended moving the snapshots into the locker** with the measurement and the four routes that remain (`--seal`, EFS on the folder, BitLocker, or leave it as it is), each with what it does and does not protect against, as your choice rather than this tool's. Checked by `backend/test_data_backup.py` (123 checks, 1 skipped on a one-drive PC): three real locker paths, the command line stopping before any snapshot is taken, the failure note, and an ordinary folder still working.

- **The card is answered where it is shown: the bar grows to it, the HUD answers it itself, and typing "i approve" works (2026-10-16).** The owner's report, in his own words: *"when i click open the card from the notification, it opens the jarvis bar with no additional information. it should open the card itself. i should also be able to approve any card from the jarvis hud directly on my desktop and not need the jarvis widget or jarvis bar to do so"*, and *"after i click open the card and type into the jarvis bar that i approve, nothing happens. i have no idea what happens"*. All three were real, and his screenshots show what he was looking at: the Jarvis bar **exactly one input row tall** floating over the HUD's card, whose own Approve and Deny were hidden by design - and, in the earlier one, **three** cards on that HUD each reading *"Timed out: Jarvis stopped waiting and refused it by itself."*, because the one surface he watches was the one surface he could not answer from.

  **1. The bar could never grow to the card it was opened for - and it is one CSS word plus a loop that could not close.** Rust collapses the quickbar to its base height every time it is summoned from hidden (`windows.rs`, `QUICKBAR_BASE_HEIGHT` = 80, `show_quickbar_unlocked`) and then emits `focus-input`; the page answers by asking Rust to size the window to what it measures (`main.js` `syncWindowHeight` -> `resize_quickbar`). `.shell { max-height: 100vh }` capped that measurement at the window's **own** height, so the page reported 80 back to Rust, Rust set 80, and the loop stopped there: the card - and the sticky footer holding Approve and Deny - sat outside an 80px window, and the stack's scroller had no height left to scroll in, so it could not be reached by scrolling either. The cap is now the window's own clamp, `max-height: 720px`, the same number `QUICKBAR_MAX_HEIGHT` holds - `tests/approval-reachable.mjs` reads both files and fails if they drift - so the element measures its content until the content is taller than any window may be, and past that the stack scrolls inside the clamp while the decision row stays pinned to its bottom edge, which is what the cap was added for in the first place. **Measured, on the unfixed tree:** the page's only `resize_quickbar` ask is `80`; `#stack` has `clientHeight` **0** against **244px** of card; the Approve button's rectangle is `93..123` of an 80px window and `document.elementFromPoint` at its centre returns **null**. Every other UI suite missed this because they open the page at a fixed viewport and leave it there, so `.shell` is free to measure its content and the bar looks like it grows; the new suite drives the loop the way Rust does, clamping each height the page asks for to 80..720 and resizing. **5 of its 5 checks fail on the unfixed tree and pass with the fix.** The visible change for the owner: the bar is no longer one input row - it grows to what it is showing (327px for the card in the test, 632px for the empty state's own primer), which is the size every screen inside it was written for.

  **2. The HUD answers its own card, through the one decision path (`hud-approvals`).** The page's own Approve and Deny are shown again (`hud-link.css` no longer hides them, and its *"Answer this in the Jarvis bar or the widget."* line is gone), and `hud_bootstrap.js` section 5 sends the click through **`decide_approval`** - the same Tauri command the Jarvis bar and the widget call - so the stale-link refusal, the cut-off refusal, Windows Hello for the card the settings say needs it and the App-lock rule all apply there unchanged. It is **one command, granted as its own set**: `permissions/surfaces.toml`'s new `hud-approvals` holds `allow-decide-approval` and nothing else (`capabilities/hud.json` gains it; no `amend_approval`, no bulk decide). The page's own handler is still stopped before it runs, and the fetch shim still refuses `/api/approve` and `/api/deny` whatever the link is doing, so the command is the only way a decision leaves that window. **App lock is enforced in the command, not by the button** (`commands.rs` `answer_approval` now names both windows the lock covers; `lock/rules.rs` gains `HUD_APPROVES_IN_BAR`): an Approve from the widget or the HUD while the lock is on opens the Jarvis bar - which asks Windows Hello - and is refused here. A refusal is written on the card in the command's own words rather than leaving a button that quietly does nothing. **`tests/hud.mjs` is 64 checks**, two of them rewritten for this: they drive a real card in the served page, prove the visible buttons call `decide_approval` with the card's own id and that the page's own POST still never reaches the backend, and prove a refusal lands on the card and leaves Approve pressable again. Both fail on the unfixed tree.

  **3. Typing the decision works, and nothing is inferred.** `jarvis-link.js` gains `typedDecision` (the whole message IS the decision: "approve", "i approve it", "deny", "deny it"...) and `typedMaybe` (it only sounds like one: "yes", "ok", "go ahead", "do it"). A decisive message goes through the same `decideApproval` the two buttons call, so the one-decision latch, the stale-link refusal and Windows Hello all apply; a message that only sounds like one - while a card is on screen - is answered with *"Nothing was decided. To answer the card, press Approve or Deny on it."* instead of being decided **or** being quietly sent to the model, which is what produced *"i have no idea what happens"*. An APPROVE on a card `quickActionable()` refuses (it carries `raised`, so something tried to rush the reader) is refused with words and takes the button; **Deny is never held**, because refusing costs a retry. A card that is not on screen - `Esc` puts one aside without deciding it - is never answered from a typed word: the bar says one is waiting and that typing decides nothing. **Nothing new is bound to a key**: it is the owner's own sentence, not `Esc` or `↵`, which the app removed from the decision path on purpose. `tests/decide.mjs` goes from 10 checks to **15**; its five new ones - including a CONTROL that an ordinary prompt still reaches the model while a card waits - all fail on the unfixed tree.

  **Run, and not run.** `cargo fmt --check`, `cargo check` and `cargo clippy -D warnings` against `x86_64-pc-windows-msvc`: clean. `cargo test --target x86_64-pc-windows-msvc`: **812 passed, 3 failed** - `crash_notes::tests::a_successful_write_really_lands_on_disk`, `crash_notes::tests::record_and_read_round_trip_and_keep_only_the_newest` and `commands::wiki_tests::only_a_real_jarvis_wiki_folder_is_opened`, which are the three `CLAUDE.md` already records as failing on this PC on unmodified `main` (`%TEMP%` refuses the write), and the window probe reported `SKIPPED` with `JARVIS_SKIP_WINDOW_TESTS=1`. Desktop suites: `approval-reachable` (5), `decide` (15), `hud` (64), `security` (29), plus `approvals-contract`, `card-words`, `bar-chrome`, `ia`, `hotkeys`, `updates`, `update-both`, `chat-thread`, `a11y`, `palette`, `tutorials`, `heavy-approve`, `inbox-tidy`, `form-review`, `chat-stream`, `blockers`, `composer`, `conversation`, `continuity`, `bar-face`, `focus`, `focus-outline`, `menu-visibility`, `hud-window`, `hud-prompt-window`, `a11y-forced-colors-and-focus`, `contrast`, `disabled` - all green. Project checkers: `tools/check_parity.py`, `tools/check_stale_twins.py`, `tools/check_vacuous_checks.py`, `tools/check_docs_map.py`, `tools/check_claims.py`, `backend/test_base_matches_repo.py` (30 passed) and `backend/test_base_regeneration.py` (36 passed) - all exit 0. **Not run: CI**, and nothing was driven on the owner's own machine - no card was raised, approved or denied there, and no window was opened on his screen. **One thing found and deliberately left alone: `APPROVE_WHERE`** (*"in the Jarvis bar, on the widget, or on your phone's Home screen"*) is now incomplete - the HUD is a fourth place a card can be answered - and that one sentence is duplicated in **17 files** (`jarvis-link.js`, `desktop-help.js`, `onboarding.html`, `first-run-settings.js`, two Rust sentences in `voice.rs`, and eight suites that pin the literal string). That sweep is a wording change with its own blast radius, so it is named here rather than half-done in this one.

- **The weekly snapshots are encrypted at rest now, and the key is the half that can lose them (2026-10-14).** This one is mostly a machine setting rather than code, and it is written down here because what it costs if it is forgotten is the owner's data. Windows **EFS** (Encrypting File System - Windows' own per-account file encryption) is now on for the two folders the personal-data backup writes to: `C:\Users\pcadmin\jarvis-data-snapshots`, which the Sunday 03:00 task uses, and `C:\Users\pcadmin\Documents\Jarvis Backups`, the folder he chose inside Jarvis. **230 paths in the first, 177 in the second, every one verified encrypted** - snapshots, the four older `.jbak` archives, and the folders themselves. Encrypted that way, the Sunday task needs no passphrase and was not changed at all. **The trap this hit is the reason there is a checker:** `cipher /e <folder>` sets an attribute on the *folder* so files written there later are encrypted, and does **not** touch the files already inside - so the one-command version leaves every existing snapshot plain while looking finished. Each folder therefore got `cipher /e` **and** `cipher /e /s:`, and the new `tools/check_snapshots_encrypted.py` reads the EFS attribute of the folder and of every file beneath it, fails naming the plain ones, and proves its own reader with `--self-test` (a plain file is never reported encrypted; on Windows `cipher /e` really does encrypt a file created afterwards). The weekly run was then rehearsed for real on both folders: a new snapshot landed, came out **encrypted with nothing in the tool knowing about EFS**, verified 19 databases and 604 rows, and a **restore from it returned the same 604 rows**. Nothing else was encrypted, deliberately: the live databases in `~/.openjarvis` are being written by the running app, and the program folders hold code. **The key is the risk and it is not handled by this change** - EFS ties the files to the owner's Windows account (`CN=pcadmin`, valid to 2126), so a lost profile or a Windows reinstall without the certificate exported first means the snapshots are gone rather than locked. `docs/SNAPSHOT-ENCRYPTION.md` carries the one-line export command he runs himself with his own password, where the `.pfx` lands, and that it must be kept **off this PC**. A **recovery agent** was considered and deliberately **not** set up: on a one-person PC it is a second copy of the same secret on the same disk, which protects nothing against the case that actually threatens these files. **And a folder chosen next month will NOT be encrypted by itself** - EFS is a property of a folder and nothing in Jarvis sets it, so the document says so plainly and gives the two commands and the checker line to run with the new path. `tools/jarvis_data_backup.py` was **not** modified (three other pieces of work hold it at once), so that gap is written down instead of half-fixed.
- **Jarvis restarts a dead model lane by itself now, and says so (2026-10-14).** The owner's decision, in his own words: *"Also restart the lane automatically when it dies."* **The defect it answers is the one he keeps living with:** his two lanes die **silently and repeatedly** - today at **08:19:11**, with both scheduled tasks still reporting `Result=0 State=Ready` while nothing was listening, the same failure this file records for 2026-10-13 (both lanes dead about five hours). PR #409 (merged) made both apps **say** it on a standing line and deliberately made that line **act on nothing**; the button on it waits for a press, and **there is nobody at a screen at 08:19.** So the BACKEND watches the lane itself and restarts it. **Where the check lives, and why there:** one daemon thread in `backend/jarvis_model_lanes.py`, armed at start-up by the install block `model-lanes.patch` adds (`watch_start()`, one line, deliberately **not** inside `install()` - so no test, and no other caller, can start a lane as a side effect of wiring the routes up). It is the backend rather than a desktop window because **the phone must get the same lane back**, and the phone is often the only thing looking at the PC. **It is cheap when everything is fine:** one loopback `GET /api/tags` on the lane's own port every **30 seconds** - no model call, no token, nothing generated. **The restart path is the SAME one action as the button**, not a second one: `start()`, which looks his own Windows logon task up on that PC by the stable half of its name and runs `["schtasks", "/run", "/tn", <name>]` as **argv, never a shell** - so his own port, card and context are used, because the task holds them. There is no `ollama serve` anywhere in it and no second way to start anything. **The limits, and what happens at the cap (the part that matters):** two down beats (about a minute) before the first automatic start, because one missed probe is not a dead lane; then at most **3 automatic starts in one episode**, with a **5-minute cooldown that doubles to 10** - the attempts land about a minute, six minutes and sixteen minutes after the lane died, far longer than the 90 seconds a lane is given to come up, so an attempt can never overlap the start it follows. An episode ends only after the lane has been **really back for 10 minutes**, not one lucky probe, so a lane that answers and dies again has flapped and does **not** get a fresh three attempts. **At the cap it STOPS:** the state goes back to plain `down`, `auto_capped` is true, and what remains is **exactly the standing warning PR #409 built**, with #418's Start button still offered to him, plus one plain sentence: *"Jarvis started the local model 3 times and it did not come up, so it has stopped trying. You can still start it yourself."* Nothing is started twice while a start is being watched (`start()`'s own refusals and the Task Scheduler's own "Running" are two more independent guards). **A deliberate stop cannot be told from a crash, and this does not pretend otherwise:** `schtasks` reports the same "Ready" whether the lane crashed or was closed on purpose, and there is no second signal on that PC that means "I meant that". So the answer is his own switch - `POST /api/model-lanes/auto` (new), `{"on": true|false}`, **one key and nothing else** so no client can aim it at another lane or at both, OFF immediate from either app, stored in his own config folder (`model-lanes.json`, never the toml) and **on by default because that is what he asked for**. **THE RESIDUAL RISK IS STATED PLAINLY, EVERYWHERE THIS IS WRITTEN DOWN: with the switch on, Jarvis will start a lane that was stopped on purpose, and will tell him it did.** **The tier decision, argued rather than inherited.** The house rule is the Docker one - *"starting a service gives Jarvis more, so it asks"* (`docker_service_start = "ask"`) - and this is deliberately **not** that case: what is started is not a new grant but the lane the chat is pointed at, the one this PC already starts by itself **at every logon, unattended, with no card and nobody asked**, so a card would be stricter than the machine's own behaviour; a card **could not be answered when it is needed anyway** (at 08:19 it would sit for its 900-second timeout, expire, leave the lane dead and be raised again on the next attempt - the defect plus a queue of expired cards); the act is bounded, reversible (OFF is one immediate press) and said (every restart is spoken about in both apps, in the backend's own words); and **nothing is auto-approved** - this path raises no card and answers no card, so rule 4 is untouched, and it calls the same `start()` his own press calls, so it can reach no action his press could not, starts only the lane the chat is on and never both, and clears no latch. Turning the switch back on raises no card either, for the same reason: **a card there would be stricter than the button it sits next to**, which does the identical `schtasks /run` in the same second. **Both apps, and the words come from one place.** The backend writes the sentence (`auto_note`, on `GET /api/model-lanes`) and each app **draws it verbatim and composes nothing** - the rule the approval notice already follows - so the Jarvis bar, the widget and the phone cannot come to three ways of saying one fact. Desktop: a new shared file `jarvis-desktop/src/lane-auto.js` (one rule, one DOM half, imported by both windows) draws it into its **own element outside the standing warning**, because that warning is hidden the moment the lane answers and *"the model went down and Jarvis started it again"* is news about a lane that is now **working**; Rust gains `commands.rs`'s `set_model_lane_auto`. Phone: Home's status line (`net/ModelLane.kt`, `JarvisRuntime.setLaneAuto`), with the switch's failure kept **apart** from the Start button's, so one press failing is never shown as the other's. All three read `/api/model-lanes` on the beat that already reads `/api/status`, **whether or not the warning is drawn** - one extra loopback read per beat on the PC, and no second timer anywhere; the phone used to read it only while the warning was up, which is exactly when this sentence can never be said. **A real turn never waits on any of this:** the watcher is its own daemon thread and the chat's path is untouched, so an answer that needs the lane fails exactly as it did before with the warning up while the restart happens behind it, and the lane is there for the *next* turn rather than making this one hang for ninety seconds. **The HUD window keeps only the standing line** - no button, no automatic line, no switch - for the reason it already had no button (`hud_proxy.rs` allows it exactly five reads and one `POST /api/chat`); this is written into `docs/ARCHITECTURE.md` §8 with the rest of the feature. **Verified, and what was not.** `backend/test_model_lanes.py` **159 passed, 0 failed**, up from 85 - the new checks drive every limit as arithmetic **and** through 200 real beats, prove a lane that answers is never started, prove nothing is started a second time while one is starting, prove the cap falls back to the plain warning with the button still there and no further attempt in the next hour, prove a flap is not a recovery, prove the switch's route refuses a body naming a lane or saying `"all"`, and prove by reading its own source that **`install()` arms no watcher** - which is what keeps every suite off his PC. `jarvis-desktop/tests/lane-auto.mjs` (**16 checks**, wired into `npm run test:ui`) holds the sentence drawn verbatim, the cap's fallback, the switch's two words and which way each press asks, a refusal that moves nothing, an older backend that offers **no switch at all**, and a CONTROL that this file never builds a sentence out of fields (`elapsed_s`, `why`, `message`). `./gradlew testDebugUnitTest --offline` **2,346 tests, 0 failures, 0 errors, 0 skipped**. `tools/check_parity.py` **exit 0** (`/api/model-lanes/auto` carried as `ported`, both apps calling it) and `check_feature_list.py` **5 passed, 0 failed** with a new entry in all three copies of `features.json`. `backend/jarvis_model_lanes.py` is carried to its `jarvis-backend/` twin, and `backend/model-lanes.patch` is re-taken through `tools/build_patch_history.py`: its hunk was re-measured by applying it to a synthetic `jarvis_hud.py` with the context at line **6828**, and it lands exactly after the block `pictures.patch` prints and exactly before the `# Before the main socket` line `plugin-loader.patch` anchors on - the two printed lines it anchors on are **byte-identical to before**, so the loader's hunk still matches. **Not done, said plainly:** no lane was started or killed on his PC to watch this happen - the loop is proved by its tests, not by his hardware - and no approval card was raised or approved anywhere. **And seven checks were RED ON THE BASE BRANCH before any of this work, for one reason: #418 inserted `model-lanes.patch` at the tail of the patch stack and did not carry that through the checks that pin the tail.** `backend/test_devices.py`, `test_gate_risk_rows.py`, `test_gate_touches.py`, `test_referee.py` and `test_screen_attach.py` each keep an allow-list of "patches written after me that touch no line I wrote", and `model-lanes.patch` was missing from all five; `backend/test_uncensored_optins.py` and `jarvis-desktop/tests/pictures.mjs` each pinned the loader's *old* neighbour or its *old* anchor line. All seven now name `model-lanes.patch` and the anchor the loader really has (`until jarvis_model_lanes.py is back`), each with the reason in the established pattern - measured, not guessed: every one of them was run on `feat/start-the-lane` **unmodified** first and failed there identically, so this is a fix to the branch's own state and not to anything this work broke. (`backend/test_gate_outcome.py` also fails in this checkout, identically on the base, for a `jarvis_gate` import the checkout does not have; it is not touched here.) Also stated because it was found while working: `backend/test_model_lanes.py`'s "no target lane is 'down'" check **failed on this PC before any of this work**, on `feat/start-the-lane` unmodified, because this machine's environment has `OLLAMA_URL` set and the check assumed it was absent; that check now reads the module the way a PC with none of the three sources set does, so the suite goes green at his desk as well as in CI.

- **The standing "the local model isn't running" line now offers one button, and it starts the lane by running the owner's own Windows task (2026-10-13).** The line itself landed earlier the same day and deliberately **did nothing**: the owner started his lanes, and the app said they were down. He has since decided it should offer one action. **What the action is:** not `ollama serve`, and not a command line built in an app - `POST /api/model-lanes/start` (new, `backend/model-lanes.patch`, `backend/jarvis_model_lanes.py`) runs **his own scheduled logon task**, looked up **on that PC** with `schtasks` and matched by the **stable half** of its name (`Jarvis Ollama - Everyday model`), because the card in brackets is exactly the half that changed under the 2026-10-10 accident that made a restart a silent no-op. The whole command is `schtasks /run /tn <that name>`, as argv, never a shell - so his own port, card and context are used, because the task holds them. **Which lane:** the one the **chat** uses, `OLLAMA_URL`'s port - 11436 on his PC, never Ollama's own 11434, and never a guessed one. **One lane, never both**: there is no `{"lane": ...}` and no `{"all": true}` in the API at all. **Starting a task is not the model arriving, and nothing here pretends it is.** `schtasks /run` returns as soon as the task is launched, so the PC watches that lane's own `/api/tags` every three seconds for up to **90 seconds**: the lane answering turns the state into `up` with how long it took, and never answering turns it into `down` with a plain sentence - and the standing line **stays standing**, in both apps. **Nothing is started twice**: not while the lane answers, not while a start is being watched, and not while the PC's own Task Scheduler says that task is already running (a 202 saying so, which then watches the lane instead, since it may simply be loading the model). **The tier decision, reasoned rather than inherited:** **no approval card**, because the gate exists to make *Jarvis* ask before it acts while this is a control the *owner* presses - and, decisively, **his own logon task already runs this exact command unattended at every logon**, so a card would only be stricter than the thing it duplicates and would teach him to approve without reading. It adds no reach (the only socket is `/api/tags` on loopback, which the chat already opens) and is refused outright when this PC has no such task, so there is nothing to approve; there is therefore no new tier line to loosen. Nothing bulk, nothing that approves in bulk, nothing that clears a rush latch. **Both apps.** Desktop: the Jarvis bar and the widget, drawn from one new file (`jarvis-desktop/src/lane-start.js`) so the two windows cannot come to different words, asking through Rust (`commands.rs` `read_model_lane` / `start_model_lane`) and watching on a two-second beat for at most 100 s - deliberately longer than the PC's own 90, so the PC's verdict is what he sees rather than the app giving up first. Phone: Home's status line, read **only while that line is drawn**, on the beat that already reads `/api/status`, so a healthy PC is never asked about its lanes and no second timer exists. Both offer the button only when the lane is down **and** the PC says a press would really do something (`can_start`): an up lane, a PC that did not say, and a PC with no such task all offer nothing. **The HUD window deliberately keeps the line and has no button**, written into `docs/ARCHITECTURE.md` §8: `jarvis_hud.html` runs under `hud_proxy.rs`, which allows it exactly five reads and one `POST /api/chat` so that a script in that page can call nothing else, and a route that starts a program is not something to add to that allow-list in passing. **Verified:** `backend/test_model_lanes.py` **85 passed, 0 failed** (and it never touches his lanes - every check injects its own probe, runner and task list, and one check reads the module's own source to prove a test cannot reach the real ones); `jarvis-desktop/tests/lane-start.mjs` **19 checks**, wired into `npm run test:ui` along with `lane-warning.mjs`, which was in no runner before; `./gradlew testDebugUnitTest --offline` **2,336 tests, 0 failures, 0 errors**; `cargo fmt --check`, `cargo check --target x86_64-pc-windows-msvc --all-targets` and `cargo clippy ... -- -D warnings` clean; `tools/check_parity.py`, `check_feature_list.py`, `check_plugins.py`, `check_stale_twins.py`, `backend/test_base_matches_repo.py`, `tools/check_docs_map.py` and `tools/check_vacuous_checks.py` all clean. **Not done, said plainly:** CI has not run for this pull request, because its base is a feature branch (`feat/a-dead-lane-says-so`) and `ci.yml` only runs for `pull_request: branches: [main]` - every check here was run by hand, and that is why they are listed one by one.

- **Both kinds of backup now go to ONE folder, and it is the one he chose (2026-10-14).** The locked `.jbak` archives have gone where the owner pointed them since 2026-09-27 (`folder` in `~/.openjarvis/backup.json`, set in Settings, Backups with Windows' own folder picker). The weekly personal-data snapshots added on 2026-10-13 did not: they wrote to `C:\Users\pcadmin\jarvis-data-snapshots`, a folder compiled into the tool. "Where are my backups" therefore had two answers, and the one he could change was not the one the timer used.

  **`folder` is now the single source of truth**, and `tools/jarvis_data_backup.py` reads that key **at run time** - the registered task's command line names no folder at all, so changing the setting changes where the next weekly snapshot lands (`--dest` still overrides one hand-run). Nothing new was added to the wire: no route, no card, no second setting. The tool never writes `backup.json` and never writes into `~/.openjarvis`.

  **The folder is checked before it is accepted, in the words he reads.** The desktop now checks the picked folder *before* raising the approval card - it must be there, Jarvis must be able to write into it (one empty probe file, removed at once), and it must not be inside `~/.openjarvis` or a program folder; a folder on another drive is allowed and comes back as a question naming the drive, asked before anything is sent. A refusal is shown on the panel, with the full path, and **no card is raised** - nothing was sent to the backend. The tool applies the same rules before it writes, and fails **loudly** in all three ways an unattended run can: exit code 2, the reason in plain words, and a `FAILED` `last-run.txt` - in the destination when it can hold one, and in `%LOCALAPPDATA%\JarvisDataBackup\` when the destination is the thing that has gone. A missing or unwritable folder can no longer leave the last good run's `OK` line standing.

  **What happened to what was already there: nothing, and it says so.** His four `.jbak` files stay in `Documents\Jarvis Backups`; the snapshots already in `jarvis-data-snapshots` stay there and are not moved or deleted (retention only ever looks in the folder the run itself writes to), and every run and `status` now prints the old folder and the number of snapshots still in it, so a destination change cannot make them invisible. The two retentions cannot eat each other - this tool deletes only `jarvis-snap-*`, the app's own deletes only `jarvis-backup-*`.

  **One step on the PC:** the weekly task points at the installed copy, so after this lands run `python "<checkout>\tools\jarvis_data_backup.py" install --register-task` to refresh it. Checked by `backend/test_data_backup.py` (110 checks, 1 skipped, including a folder inside the live data folder, a folder that has gone, an unwritable folder, and the task's own no-argument command line landing in the chosen folder). Docs: `docs/DATA-BACKUP.md`, `docs/JARVIS-API.md` §45.7, `docs/ARCHITECTURE.md` §8.

- **His personal data has a second copy now, taken by SQLite itself, verified, and on a weekly timer (2026-10-13).** 19 SQLite databases, his settings file and his voice-print - **1.26 MB** in `C:\Users\pcadmin\.openjarvis` - had exactly one copy each, the one Jarvis keeps open. Windows' File History has no backup target, the `Backup` tasks in Task Scheduler (`\Microsoft\Windows\AppListBackup\Backup`, `\Microsoft\Windows\CloudRestore\Backup`) are empty Windows placeholders, and the `_jarvis-backup-*` / `_jarvis-full-backup-*` folders are copies of the **program**. The one attempt that existed, `jarvis-data-2026-10-13-223631`, was made with a plain file copy, and measured against a real SQLite snapshot of the same minute it had lost **16 tables and 10 rows and 3 databases outright**: `digest.db`, `telemetry.db` and `traces.db` were missing entirely, and its `agents.db` was an **empty shell - 0 tables where the live database reads 6** - because `agents.db` is 4,096 bytes while the file beside it, `agents.db-wal`, is **115,392 bytes**. A SQLite database keeps recent writes in a write-ahead log and folds them back later; a plain copy takes the main file and leaves the log, so the whole database stayed behind. `traces.db` (78,312-byte log, 9 rows) and `telemetry.db` (28,872-byte log, 1 row) are the same shape. That copy is left where it is - something beats nothing - but it is not a snapshot and it cannot be verified.

  **How a snapshot is taken, and why it is safe while Jarvis runs.** Never `Copy-Item`. Each database is opened **read-only** with a 30-second `busy_timeout` and **`VACUUM INTO`** writes a fresh single-file copy, with SQLite folding the write-ahead log in; if `VACUUM INTO` refuses, the same connection falls back to the **online backup API** (the primitive `jarvis_backup.py` already uses) and the manifest records which method made each file. Measured with Jarvis running: **all 19 databases, `pragma integrity_check` "ok" for every one, row counts identical to the live source**. `-wal`, `-shm` and `-journal` files are never copied - a stale log beside a fresh database corrupts a restore rather than completing one. **Nothing is trusted:** every database in the snapshot is opened again and checked for `integrity_check`, for the same *set of tables* the live database had (which is what catches the empty shell, and nothing else does) and for no table holding fewer rows; a failure is retried once against a fresh reading, then kept as `<name>-INCOMPLETE`, reported, and **never counted as a backup**.

  **What this is not.** It does not replace `jarvis_backup.py`, which is a real, working, encrypted feature the owner has used - **four `.jbak` files** sit in `Documents\Jarvis Backups`, newest **2026-10-10 09:49**. That one cannot be put on a timer, and that is the whole reason this exists: it makes a fresh recovery code per backup and never stores it ("NEVER written to a file, a log, or the audit trail", its own source), so an unattended run would produce a locked file nobody could ever open. It also covers 12 of the 19 databases, excludes `approvals.db` (51 rows) on purpose, its `*.json` rule misses `speed.jsonl`, and its only `.toml` is `jarvis-framework.toml` in the program folder - so **`~/.openjarvis/config.toml`, the HUD's own settings (`jarvis_hud.py:89`, 10,923 characters), is in no backup of any kind.** This tool takes the personal data only, not the code, and the two sit side by side: 5 locked archives when he presses the button, 4 plain verified snapshots on a timer.

  **Retention is 4, weekly.** About a month of history: enough to walk back a bad write noticed a fortnight later, few enough not to pile up the way the code backups did (23 pruned by hand on 2026-10-13). Retention deletes only `jarvis-snap-*` entries of its own making - the suite puts his `.jbak` file and the older plain copy in the same folder, makes six snapshots beside them, and checks both survive. **The commands:** `python "$env:LOCALAPPDATA\JarvisDataBackup\jarvis_data_backup.py"` backs up now (it prints where the snapshot landed), `... status` shows what exists and the next run, `... verify` opens a snapshot and prints real row counts, `... restore --to-temp` puts one back into a spare folder. **Restoring was driven for real**, never over the live folder - the tool refuses any target inside it, in code: all 19 databases opened from the restore, every count matched its manifest, **607 rows in total** (`chat-history.db` 223, `schedule.db` 196, `feedback.db` 101, `approvals.db` 51, `memory.db` 22, `traces.db` 9, `knowledge.db` 3, `telemetry.db` 1, `arbiter.db` 1), and `agents.db` arrived with 6 tables where the plain copy had none.

  **The weekly task, and the part that matters most.** One per-user task, `Jarvis Personal Data Backup`, weekly Sunday 03:00, next run **10/18/2026 3:00:00 AM**, running **`pythonw.exe` so no window ever flashes**, registered with no elevation (run as `pcadmin`, `InteractiveToken`, no password stored - the same shape as his two existing `Jarvis Ollama` tasks) and **`StartWhenAvailable` true**, because at 03:00 his PC may well be asleep and without it a missed run is simply missed. Verified end to end by starting the task through Task Scheduler itself: **Last Result 0**, a verified snapshot of 19 databases and 607 rows, and `last-run.txt` in the backup folder to tell a working timer from a dead one. It points at the installed copy in `%LOCALAPPDATA%\JarvisDataBackup\`, **not** at a checkout - this repository is worked in many parallel worktrees on different branches, and a backup that stops because a branch changed is not a backup.

  **Encryption, the half that is safe to decide.** The live files are untouched - that decision is his and is not made. The archive can be sealed: `--seal` with a passphrase writes one `.jba` file (AES-256-GCM under an Argon2id-stretched key; the same construction as `jarvis_backup.py`'s `JBAK1` with a different magic, `JDBA1`, so the two cannot be confused). On his real data that produced **one 660,588-byte file** holding all 19 databases with no readable folder beside it, refusing in plain words without the passphrase and with the wrong one. Checked rather than assumed: `cryptography` 50.0.2 is installed and its Argon2id works, so **nothing is downloaded** - and there is no 7-Zip, GnuPG, OpenSSL, `age` or WinRAR on the machine, NordLocker is installed but has no command line, and `Compress-Archive` cannot password a file. The weekly run is deliberately **not** sealed: an unattended run has no passphrase, and the only place it could keep one is the same disk as the backup - the trade `jarvis_backup.py` refuses to make. The honest route to encrypted weekly snapshots is a NordLocker locker or another encrypted volume, and that stays his call.

  **Local only, and stated in the code.** The tool contains **no network call at all** - no `socket`, no `urllib`, no `http`, no `requests` - and `backend/test_data_backup.py` reads its own source and refuses those names, so a later "send it to the cloud" option cannot be added without that suite going red. It also **never writes into `~/.openjarvis`**: the destination and every restore target inside it are refused, and the suite asks for both, expects both refused, and checks the live folder is exactly as it was. `voice-models` (1.14 GB), `models` (64 MB) and `logs` (13 MB) are not copied, each named with its reason in every manifest so nothing is dropped in silence. Docs: `docs/DATA-BACKUP.md`. 62 checks, `python backend/test_data_backup.py`.

- **Two desktop test scripts that could not fail now can, and the two Settings jump rows that both read "The AI and its tools" now say what each one is (2026-10-14).** `jarvis-desktop/tests/shots.mjs` collected page errors and driver failures into a `PROBLEMS:` list, printed it, and exited 0 - so `npm run shots` read as a clean run with a scene visibly failing inside it. It now prints the same list and exits 1, and the count it prints is what it actually rendered rather than the length of the scene list. **On this PC it exits 1 on its first run, on a finding the old script had been reporting and swallowing:** scene `10-widget-approval` records `REQFAIL http://127.0.0.1:<port>/faces.html?mode=display&feed=parent&clip=circle`, and the browser's own error text for it is `net::ERR_ABORTED` - `widget.js:568` gives the widget's face frame that address only while the window is expanded and no approval is on screen (`show = state.expanded && !state.approval && ...`), so a pending approval clears the frame mid-request. The abort is left as it is deliberately: whether an aborted frame request should count as a problem or as noise is a decision, and not one to make quietly inside a fix about exit codes. `jarvis-desktop/tests/sheet.mjs` read whatever PNGs happened to be in `shots/<theme>/`, wrote a blank contact sheet when there were none, printed the path and exited 0. It now holds the folder to the scene list `shots.mjs` itself declares - so a shot that was never rendered, or one left behind by a scene that was renamed, fails by name - refuses an input that is not a real PNG, waits for every picture in the page to decode rather than sleeping on the clock, checks that one cell was drawn per shot and that every one is labelled with the state it is, and checks the sheet that came out is a real PNG, the width of the grid, and at least as tall as its tallest picture. Six checks, and it exits non-zero: a theme with no shots, a 23-byte file where a shot was, and a deleted shot each exit 1 and say which shot or which folder, while the committed shots pass 6/6 and exit 0. **Settings' "Jump to: → Rare" showed "The AI and its tools" twice** (the 2026-10-07 audit's E9, `docs/audit-2026-10-07/E-open-pull-requests.md`): the row holding Web search now reads **"Searching the web"**, and the row holding folders, spending, "Look at this", the headless browser and the two hand-offs reads **"The tools Jarvis uses"**. No link, band or order changed - it is the same 34 hrefs - and the words are the page's own vocabulary, not a new idea: "tools" is what the "What Jarvis can reach" card already calls what the AI model is offered. **And the label gutter is 108px, not 104px** (that audit's E10): "Where things are kept" measures 108.0px at `--text-xs` in Segoe UI, remeasured here and reproducing the audit's figure exactly, so the old 104px squeezed that one label and wrapped it onto a second line while its comment named the wrong label as the longest. The comment now names "Where things are kept" and says the fit has nothing to spare; the audit's own suggestion was about 116px for headroom, because the owner's PC resolves "Segoe UI Variable Display" first and its metrics differ, and this change uses the 108px it was asked for. **Verified:** `python tools/gen_settings_cases.py --check`, `node jarvis-desktop/tests/settings-catalogue.mjs` (28 toggle rows), `backend/test_settings_registry.py` (137 passed, 0 failed, including `t_jump_list_matches_the_page`), and every other check this change's pull request names. **Not verified:** the jump list has still never been seen rendered in a browser on the owner's PC, so the 4px is arithmetic on this container's Segoe UI, not a measurement of his screen. **DEF-002's desktop half was read and deliberately left alone** - `windows.rs:516` is `focus_quickbar_input` and has nothing to do with Settings, every line number in the register row has drifted (`show_settings` is now `:662`), and the tree already carries `af578c96`'s main-thread fix with its own reproduction note in `show_restored`; the row stays open, because that hang was not reproduced here.
- **Every action that changes something leaves a receipt, and one button puts it back (2026-10-14).** The idea is borrowed from BasedHardware/omi. Every other record in this backend says what Jarvis was ALLOWED to do (`approvals.db`) or what was SAID (`chat-history.db`); nothing said what an action actually CHANGED, so an action that was allowed, ran and turned out wrong left no way back except doing the opposite by hand. `backend/jarvis_receipts.py` is a new shipped module: one table, `action_receipts`, in **its own `receipts.db`** beside `goals.db` and `schedule.db` (WAL, a busy timeout, one connection per call - `JARVIS_RECEIPTS_DB` overrides it), holding `receipt_id`, `created_at`, `tool_name`, `summary`, the before and after snapshots, the name of the code that can put it back, and `undone_at`. **Deliberately not a table in `approvals.db`**: that file is one of the nine `jarvis_gate.py` refuses to let any tool modify, because the approval stamp lives in it, and receipts are written by the same call path as the action they record. The API is four plain functions plus one registration - `record(tool_name, summary, *, before=None, after=None, undo=None) -> str`, `undo(receipt_id) -> dict`, `recent(limit=20)`, `get(receipt_id)`, and `register_restorer(tool_name, fn)` for the code that applies a before snapshot. **`record()` is called BEFORE the change, never raises into the caller** (a receipt that cannot be written returns `""` and is audit-logged by name only - a receipt must never fail the action it was recording), and **nothing unscrubbed is ever written**: `jarvis_scrub.scrub_text` cleans the summary and every string in both snapshots, keys included, so a key or token in the words an action changed lands as `[redacted: ...]`; with no scrubber at all it writes nothing, the rule chat history already follows with no key. A snapshot over 8,000 characters is replaced by a note saying so rather than truncated, and Undo reads that note as "not enough to restore". **Undo is idempotent by one conditional `UPDATE ... WHERE receipt_id=? AND undone_at IS NULL` run BEFORE the reversal**, so a double tap, two screens or a retry cannot apply it twice; a second call is refused in plain words - *"this was already undone"* - a failed reversal releases the claim, and `undone_at` is set only when the reversal really ran. **Two ways back and the answer says which ran:** `"path": "callable"` (the zero-argument callable `record(undo=...)` was given, still held in this process) or `"path": "snapshot"` (a new process, which is the normal case - the store finds the restorer registered for that `tool_name`, or resolves the name in the row in its own `jarvis_` module, importing it when needed, and applies the snapshot); with neither it refuses rather than pretending, and marks nothing undone. **Two routes, and NO patch**: `GET /api/receipts` and `POST /api/receipts/<receipt_id>/undo` are installed by the module's own `install()` - the same origin and token checks, the same `_send`/JSON shape as `jarvis_news.py`, `jarvis_sources.py` and `jarvis_goals.py` - and `plugins/ready/receipts/plugin.json` names the module, so `jarvis_plugins.py` makes the call the patch would have made (`stack_order` 143, after every folder the old stack had). **Undo is a mutating action, so it goes through the one permission model**: ONE card, action `undo_action`, and the reversal runs only on the gate's own answer - a denied or timed-out card changes nothing at all, and at tier `ask` only an outcome of `"approved"` is a yes (`allowed` is not trusted as "a human decided": the gate returns `allowed=True` on tier `notify` and on tier `auto` with nobody in the loop). **One card per undo comes from the owner's own settings file, not from this module:** `undo_action` has no line in the shipped `[autonomy.tiers]`, so it takes `unknown_action_tier`, which that file says is "ask" - and the module deliberately does NOT read that table or force the tier, because `jarvis_gate.py`'s `_NO_RULE_FROM_DENIAL` requires every module that refuses to act on any tier but "ask" to be on the gate's own list, and joining it means editing `jarvis_gate.py`, which this feature is forbidden to touch. The tier table stays the single policy with one reader; the consequence, said plainly, is that a tier the owner ever writes there for `undo_action` is what happens. The receipt id is checked and the receipt's own state read BEFORE any card, so no card is ever raised for something that cannot be undone, and a receipt already undone is a plain 409 with no card; one card at a time. **`undo_action` is deliberately not in the gate's `_RISK` table and this feature adds no row for it** - a row means patching the gate, and the folder exists so a new route needs no patch - so the gate's own fail-closed rule classifies it as irreversible and outbound, which makes the Undo card risky (Windows Hello on the PC, the screen lock on the phone) and heavy: stricter than the action it undoes, which is the safe direction to be wrong in. It also has its own plain title and short summary in `jarvis_card_words.py` ("Jarvis wants to put back a change it made"), so the notification on a lock screen reads as words rather than as an action id - both apps' `card-words-cases.json` fixtures were regenerated from the one producer. `receipts.db` is in the locked backup (`jarvis_backup.SOURCE_DBS`, with every other database): a restore that put `goals.db` back while dropping the receipts for those rows would leave Undo pointing at changes the archive had already replaced. **One mutation is wired, on purpose and named:** `jarvis_goals.Goals.mark_step`, the everyday step tick - no card, one tap, often by voice, the easiest change here to make by accident. The receipt is written before the row changes, holding the whole row; the tick's result carries `"receipt_id"` (null when it could not be written); and Undo puts the plan back EXACTLY - the same `done_at`, the step that waited on it locked again - through `restore_row()`, registered at import so the snapshot path works after a restart. `jarvis_goals.py` imports `jarvis_receipts` lazily inside a `try` in both places, so a backend folder without the module still ticks steps. **Not wired, and said plainly:** goals create/accept/stop, everything in `jarvis_projects.py`, and every other mutating module - each needs its own honest reversal, and inventing one that does not truly reverse a change is worse than not offering the button. **Neither app has a screen for it yet** - no receipts list and no Undo button on either - which is the scope of this slice rather than a one-sided decision, and it is written into `docs/ARCHITECTURE.md` §8 with the reason; `tools/check_parity.py` cannot see it at all, because that tool scans the two apps' own source and a backend route no app calls is outside what it decides. **Verified:** `backend/test_receipts.py` is new (125 checks, no owner's PC: a receipt written and read back, a real goal tick reversed with the whole plan equal to what it was and the waiting step locked again, a second Undo refused with the counting callable run exactly once and a retry of an old receipt not clobbering a newer tick, an unknown id refused as a plain 404 with no card, a receipt that cannot be written not failing the tick, a snapshot holding no secret checked against the database's own bytes, the snapshot path after a restart, the card raised once for `undo_action` with a denied card changing nothing and `allowed`-at-`ask`-without-an-approval not reversing anything, the shipped settings file's own "ask" for that action read out of `rebuilt/jarvis-framework.toml`, and the two routes behind the origin and token checks) - and **it bites**: with `jarvis_receipts.py` taken away the suite cannot import (exit 1); with `jarvis_goals.py` back at HEAD, 11 checks fail (62 passed, 11 failed); with the two idempotence guards removed, 8 fail (114 passed, 8 failed). `plugins/ready/receipts/`, `tools/gen_plugin_catalogue.py` (a folder that replaces no patch is no longer pruned), `tools/check_plugins.py` (one new check that such a folder is sound and its module is copied in - 21 passed, 0 failed), `scripts/apply-patches.ps1` and `backend/_where.py` (the module joins the shipped list, so it reaches the PC), and `scripts/add-plugin.ps1`/`list-plugins.ps1` (they now read a folder that is not in the catalogue, verified in Windows PowerShell 5.1). `tools/gen_projects_cases.py` stands `uuid` in for `jarvis_receipts` too, because the goal a tick hands back now carries a receipt id and a fixture has to come out the same on every run (regenerated, and `--check` passes twice in a row). **One real defect was found and fixed on the way, and it was dead on `main`:** `scripts/list-plugins.ps1` assigned an array to `$core`, which is the `-Core` **[switch] parameter - PowerShell keeps a parameter's type, so the script failed every run, in 5.1 and in 7 alike**, with `Cannot convert value "System.Object[]" to type "System.Management.Automation.SwitchParameter"`; the `powershell-5` CI job only PARSES the scripts, so nothing caught it. The data variable is `$coreRows` now, and it is recorded as DEF-013 in `docs/defect-register.tsv`.

- **A dead model lane now says so, standing, in both apps - and the desktop had been asking the wrong port (2026-10-13).** The owner's Jarvis talks to his everyday Ollama lane on `http://127.0.0.1:11436` (`OLLAMA_URL` in his own environment; `jarvis_hud.py:74` reads exactly that variable), started by his scheduled logon tasks. **Both of his lanes were dead from about 16:30 until about 21:5x on 2026-10-13** - connection refused on 11436 and 11435, only one unrelated Ollama server alive on 11434 - and **the failure was silent**: the scheduled tasks still reported "last run 09:11, result 0", their logs simply stop, and both apps showed a normal, connected state. Jarvis admitted it only **after a question**, with the chat error `model_not_running`. **The fact was on the wire the whole time**: the backend's own `GET /api/status` carried `"ollama": false` from the first minute (`jarvis_hud.py:3206`, `_reachable(OLLAMA_URL + "/api/tags")` - the same address the chat itself uses). **What already existed and who ignored it, checked rather than assumed:** the desktop's HUD page read that field at boot and drew a "Demo data" banner from it, but it never read it again, so a window opened before 16:30 said nothing for the rest of the session; `check_server_health` - the only thing the widget's light and the bar's three dots are drawn from - **did not read the backend's field at all: it probed `http://127.0.0.1:11434` directly** (`commands.rs`, `lib.rs`'s `OLLAMA_URL`), a port his lane is not on, so even a fresh probe judged the wrong address; and the phone's `StatusInfo` (`ApiModels.kt:91`) had **no field for `ollama` at all**, so the phone parsed the route and threw the fact away.

  **The fix, both apps, one source of truth for the words.** `jarvis-desktop/src/lane-warning.js` (new) holds the rule - **only a plain `false` from the PC draws the line**; `true` and "the PC did not say" draw nothing - plus the one DOM half, imported by all three desktop surfaces, and `jarvis-client`'s `ModelWords.kt` (new) holds the phone's copy, with `ModelWordsTest` reading the desktop's sentence out of that file so the two cannot drift. **The desktop**: the Windows bar (`index.html`) and the widget (`widget.html`) draw a standing amber line - "The local model isn't running on your PC." with "Open Ollama on the PC, or run ollama serve there. This window will say when it is back." - and the HUD window draws the same line beside its own host verdict ("The PC is answering - Jarvis' own model server is not."). All three **ask again on a shared slow beat** (`startHealthBeat`, 90 s, skipped while the window is hidden and never stacked), because a lane dying publishes no event: the HUD's own 30 s page beat carries a re-read of the one field, and the shell pushes its stream verdict beside it (`hud_bootstrap.js` `tellLane`). `check_server_health` now **builds the Ollama row from the backend's own `/api/status` field instead of probing 11434**, so the app judges the lane where the chat does; an unreachable backend is an `Err` there rather than a report with an invented Ollama line, and an older backend with no such field reads as **unknown, which is not "down"** (`ollama_status`, four Rust tests). **The phone**: `StatusInfo.ollama` is a **nullable Boolean** - the null is load-bearing, and a non-boolean makes the whole read fail rather than become a warning - and Home's always-visible status line draws "Connected · Model not running" in amber, from `state.status?.ollama`, with `JarvisRuntime.refreshModelState()` on the same 90 s beat and never while the link is down. **It is its own state, not "Jarvis isn't connected"**: there the PC cannot be reached at all; here the PC is answering perfectly and only answers are missing, and the two are never written in each other's words. **Nothing acts**: no button, no card, no restart - the owner starts his lanes, and the apps tell him they are down. Whether an app should ever *offer* to start one is the owner's decision and is handed to him in the pull request, not built.

  **Verified, and what was not.** `jarvis-desktop/tests/lane-warning.mjs` (new, 15 checks, picked up by CI's "every suite in `tests/`" loop) covers the rule, the three DOM states, the beat and the wrong-port fix, and `tests/hud.mjs`'s existing no-server checks were extended for the new line; `backend/test_base_matches_repo.py` **20 passed, 0 failed** and `tools/check_stale_twins.py` **exit 0** (both `backend/jarvis_hud.html` and `jarvis-backend/jarvis_hud.html` were carried over - the HUD page is a checked twin of the desktop's copy); `tools/check_parity.py` **exit 0** after its now-dead `/api/tags` entry was removed (nothing calls it any more); `cargo fmt --check` and `cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings` **exit 0** on stable Rust 1.99.0; `cargo test --target x86_64-pc-windows-msvc` is **778 passed, 3 failed** - the three are `main`'s own known `%TEMP%` failures, named in `CLAUDE.md`; `./gradlew testDebugUnitTest --offline` is **2,323 tests, 0 failures, 0 skipped**; every other desktop JS suite passes. **Not measured on the owner's own machine**: no lane was killed and restarted here to watch the line appear and clear, so the 90 s beat and the clear-on-recovery are proved by the tests, not by his desktop.

- **"Speak up" was dead in both apps, and the patch that added it said it was not (2026-10-13).** The Brain's interruption-budget card could be read on the PC and the phone and **changed nowhere**: `POST /api/attention/settings` answered **`404 {"error": "not found"}` on a correctly patched install**. The route's handler was there - `jarvis_hud.py`'s `_desktop_action` has carried the `if route == "/api/attention/settings":` branch since `attention-settings.patch` - and the Handler's own dispatch tuple, the list holding `/api/models/switch` and `/api/attention/mute`, never named the route, so the request fell through to the HUD's 404 **before `_desktop_action` was ever called**. A route needs both halves and the patch wrote one; the neighbouring `limits-settings.patch` had the identical hole and was fixed on 2026-10-10, which is what this fix copies. Both apps post to exactly this path - the desktop's `set_attention_limits` in `jarvis-desktop/src-tauri/src/attention.rs` and the phone's `AttentionSettings.PATH` - so **raising the budget had never once worked from either app on any install built from this patch set**, and the desktop turned the 404 into *"Your PC's Jarvis does not have this setting yet - run apply-patches.ps1 on the PC"*, which was true of the machine and false of the code. The card could still be raised by asking in the chat box, which is how the field test reached it and why nothing on screen said anything was wrong. **The entry's PLACE inside the tuple is load-bearing, and that was measured rather than chosen:** written beside `/api/attention/mute`, where it reads best, it lands inside the remaining context of `limits-settings.patch`'s own tuple hunk - which runs next in the stack and whose context ends at the `/api/watch/remove` line - so that hunk can no longer match and `apply-patches.ps1` refuses the whole run with NOTHING HAS BEEN CHANGED; written after `/api/watch/remove`, both patches apply and both routes are reachable. `backend/test_attention_route.py` is new (54 checks): it stages the published base plus the three patches this feature lives in, reads the tuple's **value** out of the patched file with `ast`, drives the real `_desktop_action` through it, and **fails with 404 for this route when that one line is taken back out** - the failure it was written for, reproduced on purpose. `backend/test_attention_settings_route.py` passed all 74 of its checks throughout, because it calls `jarvis_arbiter.handle_post` directly and a test that cannot see the wiring cannot see it missing. `backend/_stack.py`'s ratchet moves 50 -> 51 for `jarvis_hud.py` (the new hunk invents the tuple's own lines, which only the owner's PC holds; `limits-settings.patch` correspondingly stops inventing its pre-image and leaves `by_patch`), and `backend/patch-history` records the patch version from before this edit so `apply-patches.ps1` recognises an install carrying it and takes it off. **A sweep of all 143 patches found no other route with this fault**: every other `if route ==` branch a patch adds either sits in the POST handler's own body, where no tuple is needed, or has its tuple entry from the same patch or the published base.
- **The app's own encrypted backup stopped leaving seven of his databases and his own settings file out of the archive (2026-10-13).** `backend/jarvis_backup.py` - the real, working feature he has used, four `.jbak` files in `Documents\Jarvis Backups`, newest 2026-10-10 09:49 - named **12 of the 19 SQLite databases** in `~/.openjarvis`. Measured against his own install rather than the brief: **`knowledge.db`** (6 tables, 3 rows) and **`traces.db`** (7 tables, 9 rows, holding the words he typed and the answer he was given) are his own content and now travel; **`approvals.db`**, excluded on purpose, was checked and the decision left alone. The other **five** - `agents.db`, `audit.db`, `digest.db`, `sync_state.db`, `telemetry.db` - are now named in the module in a `NOT_BACKED_UP` mapping **with a reason beside each** (empty template tables the modules recreate; a security trail rather than memory; generated digests; sync cursors whose staleness loses data; machine measurements whose writer is off by design), and a test fails if a database is in neither list. Two files were missing for a plainer reason still: the `*.json` glob cannot match **`config.toml`** (the HUD's own settings, 10.9 KB, in **no backup of any kind**) or **`speed.jsonl`** (24 KB), so `SETTINGS_NAMES` carries both under the same `settings/` prefix the JSON files already use, and one list (`_named_settings_entries`) is what may land in the settings folder, so a tampered archive cannot write an arbitrary file there.

  **`config.toml` was read line by line before it was added, and it holds no secret:** all 14 token/password/`app_secret`/`api_key` lines in it are **commented out and empty** (Telegram, Discord, Slack, WhatsApp, Teams, Matrix, Mattermost, Feishu, each followed by "Or set `<SERVICE>_TOKEN` env var"), the one mention of a real key says it comes from the **environment** (`VLLM_API_KEY`), the weather credentials are "in `credentials.toml` or the environment, not here" in the file's own words and neither file exists, `[server]` is `host = "127.0.0.1"` with the `0.0.0.0` line commented out, and the only non-comment matches are ordinary settings whose *names* contain the words (`max_tokens`, `secret_scanner`). `t_config_toml_holds_no_secret` now reads the real file and fails on a live secret-shaped line, so the day a token is pasted there it is announced rather than silently carried. **The `devices/` folder is deliberately NOT carried** and now says so: it holds a SHA-256 of each device's pairing token and is authorization state, so an old copy restored would re-authorize a phone he had removed - and `chatbot/api-money.json` (three spending numbers) is a **stated gap, not a decision**, since carrying it means letting the archive layout reach into subfolders.

  **The `-wal` trap, proved rather than assumed.** Measured on his PC: `agents.db` is 4,096 bytes beside a **115,392-byte** log, `traces.db` 4,096 beside **78,312**, `telemetry.db` 4,096 beside **28,872** - and a plain copy of the main file alone reads **0 tables** where the live database reads 6, 7 and 2. (The brief's own example was backwards: it named `agents.db` as the one whose *rows* live in the log, and that file has **0 rows** - `traces.db`, with 9 real rows behind its log, is the one that proves it.) This feature uses SQLite's online backup API, and the new `t_a_database_whose_rows_live_in_the_wal_is_captured_whole` builds a database whose 40 rows are **only** in the log and shows a plain copy cannot even read the table while the API returns every row and the schema - then deletes the sidecar files and reads it cold, so "self-contained" is measured and not asserted. The `-wal`/`-shm`/`-journal` files are never copied, on purpose: a stale log beside a fresh database is a way to corrupt a restore. `test_backup.py` went 171 -> **206 checks**; the module's docstring carries the full record of every name carried and refused, its card now names the knowledge and trace stores it replaces, and the lock, the folder, `KEEP=5`, the routes and the approval cards are all unchanged. `docs/DATA-BACKUP.md` describes the coverage that now exists.
- **Jarvis's own rules are now in front of the model on every question, including the lane the owner actually uses (2026-10-14).** The rules - "Say what is a guess and what is verified", "Never claim an action was taken that was not", who Jarvis is - are sent only when the request does not already start with a system message, because the model is expected to carry them itself; the owner's everyday model since 2026-10-10, **`qwen3.5:9b`**, is a plain pull from the library with none of its own (`ollama show qwen3.5:9b --system` prints nothing), so a fresh question went to it as the question and nothing else. Measured on his PC: **271 prompt tokens** with no tools offered, one question in it. The honesty rule was therefore not in front of the model on the lane he uses, and a reply that said it had changed a setting it had not changed went uncorrected except by the app's own backstop line. `jarvis_agent.with_rules_first()` now puts the rules at position 0 of every local turn, before trimming, from **one function** the main lane, the second card and the warm-up all call - so the two lanes cannot drift and a recalled-facts turn cannot end up with two competing system turns. **What it costs:** +340 prompt tokens a turn (**271 -> 611** with no tools, **1070 -> 1410** with the settings tool offered). **What it honestly did not do, measured with a control on the same lane:** it does not change tool calling - with `change_setting` offered the model called it in **35 of 35** runs both before and after - and the rate of claimed-but-undone answers moved from **3 of 80 to 1 of 80**, which is not a difference 80 runs can separate from chance. The field test's own bare order ("turn the light humour on") went from 1 claim in 10 to 0 in 10. Held by `backend/test_lane_prompt.py`, whose first check fails the moment the main lane loses the rules again. See `docs/JARVIS-API.md`, "The main lane hears the rules".

- **The desktop's whole Tauri stack moved up one generation, and one line was what held it back (2026-10-13).** Every crate of the Tauri 2.12 generation declares **Rust 1.90** as its minimum - read from crates.io's own per-version metadata, not assumed - so the single line `rust-version = "1.89"` in `jarvis-desktop/src-tauri/Cargo.toml` was the whole reason the app sat one generation behind. Raising it to `"1.90"` is what lets everything else move, and everything else moved with it, as one change: `tauri` 2.11.6 -> **2.12.3**, `tauri-build` 2.6.3 -> **2.7.2**, `tauri-plugin-updater` 2.11.0 -> **2.13.3** (three minors behind on the part that downloads and verifies updates, so it did not wait its turn), `notification` 2.4.0 -> **2.6.0**, `store` 2.4.4 -> **2.5.0**, `single-instance` 2.4.4 -> **2.5.3**, `clipboard-manager` 2.3.3 -> **2.4.2**, `global-shortcut` 2.3.2 -> **2.4.1**, `window-state` 2.4.1 -> **2.5.0**, `window-vibrancy` 0.6.0 -> **0.8.1**, and `wry` 0.55.1 -> 0.57.0 with `tao` 0.35.3 -> 0.37.1 following transitively. The JavaScript side was put back in step too: `@tauri-apps/cli` `^2.1.0` -> `^2.12.0` (2.12.2 in the lock), so the command-line tool and the Rust crate name the same generation.

  **Two pins this file recorded as "deliberate" were the same blocker, and each had a second half that still stands.** `tauri-plugin-window-state` was pinned exactly at `=2.4.1` for one reason only - 2.5.0 needs Rust 1.90 - so that pin is gone. The other half of that decision never depended on the pin: the plugin's default restores whether a window was **VISIBLE**, which would put the HUD on screen before Windows Hello while App lock is on. Re-read in 2.5.0's own `src/lib.rs` rather than assumed: `StateFlags::VISIBLE` is still there and `Default for StateFlags` is still `all()`. `window_memory.rs` still restricts the restore to size, position and maximised, and its two tests still hold - both were **run**, not just compiled, because this machine is a Windows host: `visibility_is_never_remembered` and `only_size_place_and_maximised_are_remembered` pass, 12 of 12 in that module. `window-vibrancy` was on 0.6 because `tauri 2.11.6` itself depends on `^0.6` and anything else compiles a **second copy** of the crate. That reasoning was right and it inverts: `tauri 2.12.3` depends on `window-vibrancy ^0.8.1` (again read from its published dependency list), so after the bump **staying on 0.6 is what would duplicate it**. The two had to move together, and they did - `Cargo.lock` holds exactly one `window-vibrancy`, 0.8.1.

  **The compiler found one coupling nobody had written down.** Our own `windows-sys` feature list had to gain `Win32_System_LibraryLoader`. `lock.rs`'s screenshot-exclusion probe uses `GetModuleHandleW`, which that feature gates, but this file never asked for it: it arrived by **feature unification** from `window-vibrancy 0.6.0`, which is on `windows-sys 0.59` and switches that feature on. `window-vibrancy 0.8.1` is on `windows-sys >= 0.60` instead, so it stopped arriving - the library still built and only the **test** target broke, which is exactly the kind of break `cargo check --all-targets` exists to catch. It is now declared where it is used; a feature of a crate already in the graph, not a new dependency, and `windows-sys` itself did not move.

  **What deliberately did not move, each for a reason a version number alone would violate:** `reqwest` stays 0.12 (native-tls/schannel on purpose, and re-checking the newer major's TLS story was explicitly left undone), `windows-sys` stays 0.59, `windows` stays 0.61 and `windows-future` stays 0.2 - still no second copy, because `windows 0.61.3` is still required by `tauri-winrt-notification 0.7.3` through `notify-rust` - and `image` (0.25.10), `serde` (1.0.229), `xcap` (0.9.8), `hound` (3.5.1) and `qrcodegen` (`=1.8.0`, exact) are untouched in the lock. One duplicate did appear and could not be avoided: `keyboard-types` is now both 0.7.0 (`global-hotkey 0.8.0`, through `tauri-plugin-global-shortcut` 2.4.1, the newest release there is) and 0.8.3 (`muda 0.20.0`, through `tauri` 2.12.3). The `reqwest` 0.12+0.13 pair and the four `windows` / five `windows-sys` copies were already there before this change.

  **Verified, and what was not.** `cargo fmt --check`, `cargo check --target x86_64-pc-windows-msvc --all-targets` and `cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings` all exit 0 on stable Rust **1.99.0** (newer than the 1.98 that caught the last clippy-only failure), and no Rust source needed changing for an API break - the Tauri 2.12 surface this app uses is unchanged. `THIRD-PARTY-NOTICES.txt` was regenerated for the new graph and `--check` passes. **One environment fault, stated plainly because it is not caused by this change:** this PC's `cl.exe` fails with `D8050` when cargo's `cc-rs` builds the C++ helper in `vswhom-sys 0.1.3`, a crate that is byte-identical in `main`'s lock and has nothing to do with Tauri; the same command compiles by hand under `vcvars64`, and an earlier successful build of it is still in `main`'s `target` directory. The Rust checks above were run with `CARGO_PROFILE_DEV_DEBUG=0`, which drops the `-Z7` flag that triggers it and changes nothing about the Rust code compiled. **One more coupling came out of CI rather than the compiler, and it is a two-file rule this project already runs on:** `jarvis-backend/rust-crates.lock` is a **byte-for-byte copy of `jarvis-desktop/src-tauri/Cargo.lock`** - it is one of the `BESIDE` inputs the published base is re-taken from, and `backend/test_base_regeneration.py` fails while the two differ, which is how CI's `audit` job found it. The bump had to refresh it too, and now does. **And `sonora` still needs Rust 1.91**, so it stays blocked - this move takes the floor to 1.90, not 1.91.

- **The uncensored opt-ins have a way in now, and it is a card (2026-10-11).** PR #231 built the owner's two halves of Decision 5 - the labelled list of abliterated models already on this PC, and the fiction/role-play lane - but nothing could turn either one on: the module was shipped and called by nobody, so there was no route, no switch, and no approval card. That was against this project's standing rule that **anything loosening a limit is off by default and turning it on raises a card**, and `jarvis_gate.py`'s tier table is where that rule lives. `uncensored-optins.patch` (in `apply-patches.ps1`'s list, in front of `plugin-loader.patch`, which stays last - another patch, `gate-touches.patch`, sits in front of the loader too, so this one is not its immediate neighbour and does not need to be - the loader's own hunk was re-anchored onto this block's printed lines, as `tools/check_plugins.py` derives) adds it: `uncensored_models_enable` and `fiction_roleplay_enable` join the gate's "acts only on tier ask" set with a `_RISK` row each (`"yes", "local"` - neither leaves this PC, and turning either off is instant), both `= "ask"` in `backend/rebuilt/jarvis-framework.toml`, and one `jarvis_optin_models.install()` block answers **`GET`/`POST /api/models/uncensored`** (JARVIS-API section 125). The module gained the card flow `jarvis_phone_notifications.py` already proves - OFF is instant and withdraws a waiting card, ON is ONE card on its own thread, and denied/timed out/refused/withdrawn change nothing - and **`local_only()`**, which refuses to offer a list or hand back an import body, before any card, when the address the models are served on is not this PC (rule 1, in code). Nothing is downloaded: the import is a local `.gguf` PATH handed to the EXISTING `/api/hardware/create` (`models_create`), and the module writes no TOML and adds no tool. Proved by `backend/test_uncensored_optins.py` (112 checks, fails 16 ways without the change) and by `test_optin_models.py` (92) for the naming and labelling rules; `test_card_words.py` gained the two plain titles and both apps' card-words fixtures were regenerated from the one producer. **The app controls are not built**: the route is the backend half, and the desktop's Brain → Model screen is where the switches belong.
- **Whether Jarvis thinks before answering is the owner's choice now, and one question can ask for it (2026-10-11).** The everyday model is becoming `qwen3.5:9b`, which thinks before it answers by default. Measured on this PC with `qwen3:8b`: thinking left on with a normal answer allowance spent **every token reasoning and returned an EMPTY answer on all three test questions** (`done_reason: "length"`, `content: ""`); with thinking off the same questions were answered correctly in 0.29 s, and `ornith:9b` behaves the same way. The thinking *level* setting already existed, but it never said **when** thinking happens - so that is now the owner's choice, in two plain words, in the same small `thinking.json` the levels live in: **"Only when I ask"** (ordinary answers are written straight away; Jarvis thinks on the questions the owner asks him to think about) and **"Always"** (every answer may think first, and the line beside it says so plainly: answers can take longer and thinking uses part of the conversation room). **A missing, empty, truncated or unreadable setting reads as "Only when I ask"**, which is the safe one, and the reason is written at the constant: falling back to "Always" would fall back to the exact fault this setting exists to prevent, and the owner would have no way to tell a wrong answer from no answer at all. **And one question can ask for thinking without changing the setting**: the **Think** key beside the phone's chat box sends `"think": true` with that turn and nothing else - one question, then it lets go, never stored, never written down, and never the reason a message fails to send or an answer comes back blank. Three rules outrank it, all of them tested: a **spoken** turn (a voice answer cannot wait for a long think), a model that **cannot think** at all, and the answer's own room - `REASONING_MIN_ANSWER_TOKENS` (PR #222's measured floor: thinking and the answer share one allowance) still wins, so a question asked for thinking about on a turn with too little room is answered directly rather than blankly. The key is drawn only on a PC that reports `capabilities.think_per_question`, so it is never a key that does nothing. `backend/test_thinking_when.py` (83 checks) proves the flag reaches **the request Ollama is really sent**, with the same question and the same level as its control; `backend/test_thinking.py` and `backend/test_reasoning_room.py` were updated for the new default rather than left claiming the old one. On the phone, `ThinkingChoiceTest.kt` holds the request field, the one-question rule and the two choices. **Not built here: the desktop half.** The field it must send, and where, is named in `docs/JARVIS-API.md` section 121.5 - one `think: true` on the chat body from its own key, exactly as the phone does.

- **The prompt coach has four settings now, and it knows which AI you are sending to (2026-10-09).** The owner's verdict on the single on/off switch was *"make sure it's effective and has multiple settings, including an enable and disable"*, and he chose the four: **when it speaks up** (only when the prompt is genuinely weak, or whenever it has anything to say), **how blunt it is** (a gentle nudge, or direct about what is wrong), **what it coaches on** (shape only - length and clarity - or content too), and **per-platform behaviour** (the phone the same as the PC, or quieter there). They sit beside the master switch in **Settings → Prompt coach** on both apps, **in the PC's own words**: `jarvis_prompt_coach.SETTINGS` is the one copy of every name and every line, handed to both apps through the same `GET /api/prompt/coach`, so a new choice appears in both by changing one Python tuple and neither app can invent or forget one. **Every one defaults to the behaviour the coach already had**, so turning the coach on cannot silently change its character, and all four apply at once with no approval card, for the same reason the switch has none. **And it now coaches for the AI the prompt is headed for**: the request names a `target` (a chatbot id, a website adapter, or a model name), and `jarvis_prompt_coach.DEFAULT_TARGETS` holds one row per AI - the local Ollama model, the six API services the chatbot driver can use (OpenAI's `gpt-5-mini`, DeepSeek, Mistral, Grok, OpenRouter, Groq) and the nine website adapters - each with what that one handles badly, what style suits it, and **the date it was last checked**. It stays current three ways: a service with no row is listed by `unknown_targets()` and **`backend/test_prompt_coach.py` fails while that list is not empty**; a row is added to the table; or the owner adds or corrects one in **`prompt-coach-targets.json`** in the settings folder, field by field, without a new build. **When Jarvis does not know the AI it SAYS SO** - in the app's words and in the model's own instructions, with an explicit "do not guess, do not describe how it behaves, do not invent a claim" - never a nearest-name guess. A row older than 180 days says so on screen and to the model. Everything the coach was fenced to do is unchanged: it still sends nothing, approves nothing, leaves the PC for nothing and keeps nothing. `backend/test_prompt_coach.py` grew 12 test functions, `jarvis-desktop/tests/prompt-coach.mjs` is new, and the phone has `PromptCoachTest.kt` (9 tests). **Nothing here has run against the real model**, so the advice's quality and its speed stay unmeasured - and **no test measures whether coaching HELPS**, only that it fires and that the settings change what it says. The audit, the four questions with their file-and-line evidence, and the two collisions it had to respect are in `docs/PROMPT-COACH-AUDIT-2026-10-09.md`; JARVIS-API section 120.7 to 120.9. **One real bug was found and fixed on the way**: the desktop's `set_prompt_coach` took three loose parameters, and Tauri binds a page's arguments POSITIONALLY, so picking a setting sent `enabled = "<the setting's name>"` - `tests/prompt-coach.mjs` caught it before it shipped, and the command now takes one `CoachChange` object.

- **Watches stops saying "nothing new" over a list it never read (2026-10-09).** The owner's screen said it plainly: the badge read **"Watches · 3 new"** while the block under it read **"Nothing new since you last marked the list read."** Two parts of one screen contradicting each other, and the reassuring half was the wrong one. `GET /api/watch/report` serves `{available, new, updated, count, topics, note}` and splits its rows by `kind` - the module's own consumer reads `peek["new"] + peek["updated"]` (`jarvis_watch.py:524`). **Both apps read `findings`/`items` instead, which the route has never served**, so every *successful* read came back as the empty list and the all-clear was drawn whatever the list held: a permanent false all-clear **on the success path**, not a failure path. It also greyed out **Mark these read** with rows waiting, and titled every row **"(repository)"** - the route names a repository **`repo`**, not `full_name`/`name`. And a repository with no licence file was drawn as a settled, green `licence: none stated`, because `jarvis_watch.py:492` sends exactly those two words and the filter tested only `^(none|unknown|null)$`, so the **"no permission to use it"** warning never appeared on the one screen whose job is saying what the owner may use. The shape is now verified against the running backend and the module's own source, and written down in JARVIS-API's `/api/watch/report` row. The desktop's fix reuses the `Watch.Report`/`reportOf` seam from #162 (cherry-picked, not re-invented) and reads the served shape inside it, keeping `findings`/`items` only as a tolerant fallback - **and a body with none of the four keys now reads as *unreadable*, never as empty**, so the screen says it could not read rather than guessing. The phone's `WatchTest` asserted the fiction too (`assertTrue(Watch.findings({"available":true}).isEmpty())`) and is corrected. **Why it survived so long:** the desktop's UI fixture was the hand-written literal `{"available": true, "findings": [...]}`, so the harness agreed with the client and disagreed with the backend, and no suite rendered the block at all. The fixture is now produced by running the real module (`tools/gen_watch_report_cases.py`, both apps' copies), and three checks fail if a client reads a key the backend does not serve: the new `tests/watch-report.mjs`, `WatchReportShapeTest`, and `backend/test_watch_notify.py`'s `t_the_report_fixture_is_fresh`. Proved red then green by restoring the old key mismatch in `brain.js`. 1,985 phone unit tests pass (0 failures, 0 skipped); `check_parity.py` exits 0. The backend's payload was deliberately **not** changed - the route is live on the owner's PC and the module's own consumer depends on it.
- **"Coach this": check a prompt before you send it, on both apps (2026-10-08).** The owner asked whether any open-source project would help them write better prompts, and whether it could be a feature they can turn on and off. It is: `backend/jarvis_prompt_coach.py`, off by default, with its switch in **Settings** on the PC and the phone. Press **Coach this** beside the box you type in and Jarvis reads what you wrote - not to answer it, but to say what is missing: a score out of ten, up to four gaps each with the smallest fix, the questions it would have to ask, and one rewritten version. You then press **Send mine** or **Send the suggestion**; **it never sends anything by itself and never changes your words unless you pick the rewritten one**, and a low score never stops you sending what you wrote. **None of the four libraries the suggestion came with is used**: `promptimal` needs an OpenAI key and has no local-model support, so it would have sent your typed words to OpenAI - rule 1 - and the other three are a pre-alpha research framework, an AGPL-3.0 web app (described as MIT) and a Node CLI for a different job. This does the work with the model already on the PC and **adds no dependency at all**. It never leaves the PC: the address is checked with `check_local_model()` before the request is built, and nothing is kept - no history, no fact, no count. The honest limit is in the app's own line under the switch: the model is small, so its advice is sometimes wrong. JARVIS-API section 120; the design, including the four rejections, is `docs/PROMPT-COACH-DESIGN.md`. **Nobody has run it against a real model yet**, so the quality of the advice and its speed are unmeasured.
- **The updater can now write down what it decided about each patch, and the owner answered the question the design note asked him (2026-10-08).** Step 1 of `docs/UPDATER-REDESIGN.md` section 5: give `scripts/apply-patches.ps1` `-StateJson "C:\somewhere\state.json"` and a run writes one entry per patch - `taken-off`, `taken-off-older-text`, `on-but-unstrippable` or `not-recognised` - with a `totals` object. Nothing else changes, and without the switch nothing is written and the run is what it was; **the file is written even when the result gate refuses**, which is the run that needs it most. Measured on a copy of the owner's backend: `taken-off 122, taken-off-older-text 2, on-but-unstrippable 2, not-recognised 0` of 126, agreeing patch for patch with the script's own prose. Two things that changes for step 5: the four patches the note found re-applied on top of themselves re-apply `ok` (so their doubling is invisible here, and step 5 remains the fix), and `tutorials.patch` and `screen-attach.patch` come off the strip and then will not go back on - the pair the gate refuses over. `backend/test_apply_outcomes.py`'s `t_mini_state_json_classifies_every_patch` is 13 checks and fails without the switch. Separately, `docs/UPDATER-REDESIGN.md` section 6 records the owner's answer to its question 1, in his own words **"Back it up and overwrite"**: when a file has hand-edits the patches cannot reproduce, his copy goes into the same `_jarvis-backup-<date>` folder the script already uses and the patched version replaces it, and the run must say so by name. That behaviour is step 4 and is **not built here** - it needs step 2's manifest before drift can even be detected. Questions 2, 3 and 4 stay open.
- **The phone shows how much the brain reached for, and never a word of it (2026-10-08).** `GET /api/retrieve` is the desktop HUD's "what the brain reached for" trace: it draws "7 recalled · 6 near" and then a panel whose rows are **the matched words themselves** - up to 150 characters of a saved fact, a document, or **every Logseq page read off disk** - which is exactly why the desktop wipes the whole route while "Windows Hello for memory lists and chat history" is on. It was the one route `tools/check_parity.py` still called `todo`, and the brief that handed the choice over is [docs/RETRIEVE-PORT-BRIEF.md](docs/RETRIEVE-PORT-BRIEF.md). The owner chose **"Just the number"** (not the actual lines, and not nothing), so the phone shows one quiet line beside "Used N memories": **"3 recalled · 2 near"** - the desktop's own two words with the words taken out. **The words never reach the phone at all**: the phone asks with `count=1`, and `backend/retrieve-count.patch` adds `_retrieve_counts()` to `jarvis_hud.py`, which runs the same scoring (so the numbers always agree with the desktop's own trace) and returns four keys and nothing else - `available`, `count_only`, `recalled`, `near` - with no `hits`, no `near` list, no id, no kind and no text. On a PC that has not been patched that same question would come back with the words, so **the phone sends nothing, not even the question**, unless `/api/version` reports the new `capabilities.retrieve_count`; and while the memory lists are hidden it asks for nothing and shows nothing, because the PC blanks this route itself in that state. `backend/test_retrieve_count.py` proves the patch applies to the real backend file with `git apply`, that the reply holds no word of a corpus full of them, and that the parity entry is registered and honest; `RetrieveCountTest.kt` proves the phone's count has nowhere to put a word. **The phone half is not compiled here** (no Android SDK), so CI's Gradle build is its first compile, and the route's ~500 ms per question on the owner's own data is from the 2026-10-07 audit, not re-measured. JARVIS-API section 120.

- **The job list: work that now outlives one chat turn, on both apps (2026-10-08).** Every turn Jarvis took was one chat turn with a hard 7-request ceiling, and nothing about it survived the turn ending - which is why "one card, several steps" sat switched off, Projects could not run a test suite, and the overnight tidy ran nothing. `backend/jarvis_tasks.py` is a small job list on the PC's own disk (`tasks.db`: tasks, runs, run-events, actions and a memo), reached by `GET /api/tasks` and steered by `POST /api/tasks/act` (pause, resume, cancel, retry) and `POST /api/tasks/input` (`tasks.patch`, JARVIS-API section 118). **Both apps show it on Brain -> Work**, under the jobs that were already there - the desktop through its read allowlist, one steering command and a permission, the phone through `net/Tasks.kt` and `TasksPlate.kt`. Neither can show a task title or a step's text, because the reply carries neither, and a generated fixture both clients read is what keeps them from drifting. Five protections came with it, copied in shape from OpenMuse ([the comparison](docs/COMPETITORS-OPENMUSE-2026-10-08.md)) and each with its own test: a **lease** so a crashed job is picked up again and never run twice at once (an interrupted step that ACTS goes to `blocked` with a question; one that only reads is simply done again); a **checkpoint after every step**, one step per tick, so a job never freezes the Jarvis bar; **`outcome_unknown`** for a send interrupted by a restart - never `failed`, which invites a retry, and never `succeeded`, which would be a guess; an **idempotency key**, so the same request twice makes one action; and a **decision bound to the words on the card**, so a card that changed under you cannot be approved. `owner-check.patch` proves WHO approved; this proves WHAT. The split is two functions: `from_plan()` hands an **approved** plan to the list, and `gate_ask()` is the only place the list and the gate meet, so every step still goes through the same gate as any ordinary tool call. A card nobody answered leaves the job waiting rather than killing it, and **stopping is never gated**. `backend/test_tasks.py` is 139 checks; the patch is rehearsed forwards and backwards on the text `task-control.patch` wrote. **Nothing here has run on the owner's PC** - the backend is not in this repository.
- **A job that stopped to ask now has something to answer (2026-10-08).** Found while wiring the phone: `JobList.status()` flagged a job as needing the owner only when it was `blocked` by an interrupted step, so a job that stopped to ask a question arrived as **"needs an answer" with nothing to answer** - a dead end that only ever shows up on a screen. Both states carry the question now, and each app shows it, with a box on the row that asked.
- **The address check learned the ranges that are not a destination, and NAT64 (2026-10-08).** Reading OpenMuse's own egress allowlist turned up two real holes in `jarvis_local_http.py`, the module that has pinned the address it checks at connect time since the 2026-09-27 security audit. It did not know about ranges the internet sets aside for things that are never a destination - `192.0.0.0/24`, the three TEST-NET blocks, the benchmarking block `198.18.0.0/15`, multicast `224.0.0.0/4`, reserved `240.0.0.0/4` (which holds `255.255.255.255`), IPv6 multicast `ff00::/8` and documentation `2001:db8::/32` - and it did not unwrap **NAT64** (`64:ff9b::/96`), where `127.0.0.1` is spelled `64:ff9b::7f00:1` and `ipaddress` reports no `.ipv4_mapped` for it, so a private address written that way was invisible to the check. Both are fixed, and the NAT64 range itself is deliberately **not** refused, because a NAT64 address carrying a genuinely public IPv4 is how an IPv6-only machine reaches the open internet. `backend/test_local_http.py` gained 16 checks, 82 in all.

- **"Look at this" can hand you the picture, so you can ask about a chart or an error message (2026-10-07).** The owner asked for a screenshot to attach to a question, and chose the one-action shape: **press the same Look at this key (Alt+Shift+S)** and **the cleaned picture of that one look lands in the question box**, with a thumbnail of exactly what will be sent, its shape and its size. Then type the question, or press the little × to bin the picture. **No new key, no new button, and no setting**: the existing key now also brings the picture back with it. Nothing is saved, and the picture is that ONE question's - it leaves the box once the question has gone, so a screenshot taken for a chart cannot quietly ride on the next, unrelated question. **The picture is the PC's own cleaned one**, never a raw screen grab: the same cleaner that already paints every password, key and card number SOLID BLACK, and every window on the "Never look at" list with them, decides what is in it - and if it cannot check the picture it hands back none at all, so the app says why in the watch strip and attaches nothing. This is **not** the old whole-monitor screenshot that key used to take and staple to the prompt, which knew nothing about that list and painted nothing black. The PC's route is `POST /api/screen {"do":"look","want":"picture"}` (`backend/jarvis_screen_attach.py`; JARVIS-API section 117). **Not run on your PC**: the picture itself is made by a Windows-only part, so every suite uses a made-up one, and how long the key takes on a real screen is unmeasured - the app waits up to 20 seconds for this look (4 seconds for an ordinary one).

- **Settings has a switch for the "Open the Jarvis bar" button in the big HUD window (2026-10-06).** The owner asked for that window's button to be replaced by a text box he could type into, and then chose: keep the button beside the box, and add a Settings option for whether the button shows there at all. The box is PR #85's work and is untouched; this is only the option, under **Settings → The big HUD window**, on the PC only. It is cosmetic, so it changes at once and raises no approval card: that computer's own choice, kept in its `localStorage` (`jarvis.hud.openBar`, `src/hud-window.js`), read by the injected bootstrap that draws the button. **On by default**, because that is the state the owner already approved - "the button stays in that window, beside the box" - so nothing changes for anyone who does not touch it. Off, the button is not drawn; the box, its Send and the microphone button are exactly as they were, and Alt+Space still opens the Jarvis bar. A change made while the window is open is obeyed at once through the usual `storage` event, and on the next load of the window where a browser does not deliver that event. The button-in-the-real-page check drives it (`tests/hud.mjs`), and because Playwright is not installed everywhere, `tests/hud-window.mjs` also runs the injected bootstrap itself in a hand-made DOM - both are for the packaged app, so nobody has clicked the switch on a real desktop run yet.

- **Settings' "Jump to:" list is grouped, so a setting can be found (2026-10-06).** The owner opened Settings and said "can you organize the jump to settings in the settings menu? This is really disorganized" - about forty links in eleven flat rows that did not say what any row was. Each link now sits under a short plain-English row inside the band it already belonged to: Everyday holds Start here, Your devices, Help, Look, Talk and voice, Schedules and This page; Rare holds On this PC, Voice and sound, The AI and its tools, More on this PC, The model and cards, Where things are kept and Keeping it up to date; What Jarvis does holds What Jarvis may do and About this build. Look and feel are unchanged - same card, same small muted labels, same link colour - and so is every link: the same 32 hrefs, in the same order, with the same words and the same card ids; the 33rd, `#chatbot-api-keys`, is the API-keys work landing in main underneath this one, and it sits in the More on this PC row beside Accounts, where the flat list had it; the 34th, `#hud-window`, is the HUD-button switch landing underneath this one in the same way, at the end of Everyday's This page row, where the flat list had it. No other link was added, removed, reworded or moved between bands. The grouping is the page's own: the three bands are its own three headings, and the short rows are the six groups `docs/ease-audit-2026-09-27/customize.md` proposed and `critic.md:199` kept as "the target order of the jump list" for both apps. The registry records no group and no order (only an id, its spoken names, `app` and `where`), and `jarvis_menus.py`'s groups are feature groups for the hide-a-menu list, so rather than give the backend a second, quieter opinion about where a card sits on one page, a new check holds the list to the page instead: `backend/test_settings_registry.py`'s `t_jump_list_matches_the_page` fails if a link is not a real card, is listed twice, is missing, or has floated to another band. Playwright is not installed on this machine, so `tests/ia.mjs` still exits without running a single check, and the list has not been seen rendered in a browser. `menu-visibility-settings.js` also hides a row whose every link is hidden.

- **The cloud lane asks the service for the service's own model now, not for
  its own lane name (2026-10-06).** The lane built the day before reached
  DeepSeek correctly - right address, right key, right limit - and then asked
  it for a model called `jarvis-escalate`, which no service has. The one line
  that resolves a lane had written the model it had just looked up onto the
  HUD's *parsed request* (`do_POST`'s own `body`) instead of onto the copy of
  the request that is actually sent, because inside that helper a bare `body`
  is the parsed request and the copy is a sibling function's local - so the
  escalation could never answer. The resolved model now goes on the very dict
  the request is built from: `_completions_url(lane, body)`, with `body` a
  parameter rather than a name read from around the function. That call is also
  the last line of `cloud-one-turn.patch`'s context, so that patch's copy of the
  line was re-anchored in the same change rather than left broken. No test here
  had caught it: lifting `_completions_url` out of the file to run it turns the
  enclosing name into a global, which is the wrong object by construction, so a
  new check runs the HUD's `_completions_url` and `_open` **where they really
  live** - pasted back inside a stand-in `do_POST` - and reads the JSON that
  would go out; a second, smaller check reads the same shape from the patch's
  own text, so it runs without the owner's file too.

- **The cloud escalation lane has a real transport now, and DeepSeek is behind it (2026-10-06).** "Try the cloud model" sent its one question to `JARVIS_URL`, the port of a program this setup never installed; a lane name such as `jarvis-escalate` now resolves to a real service and model through the same code the chatbot API keys use - DeepSeek's own pinned host over HTTPS, the key from Windows Credential Manager, the monthly money limit, and the answer-length cap - and a lane the limit cannot pay for is answered on this PC instead, so the offer can disappear rather than overspend. DeepSeek's address, current model names and worst-case (peak, cache-miss) prices were read from its own pricing page on 2026-10-06, so the limit stops early rather than late; the desktop's "LiteLLM" health light now reads the lane's real state, and "What Jarvis can reach" no longer reads lane names out of `litellm-proxy.yaml`. `docs/ACCOUNT-KEYS-DESIGN.md` section 5 says what to remove from the PC by hand.

- **Anything needing a key is settable in the app now (2026-10-06).** Settings
  has a new "Chatbot API keys" card for the six chatbot API services (OpenAI,
  DeepSeek, Mistral, xAI, OpenRouter, Groq): each key is typed on the PC and
  written straight into Windows Credential Manager from Rust, never over HTTP
  and never to the phone, exactly like the Accounts page's four secrets. The
  same card carries each service's monthly money limit and its price list,
  because a key with no limit leaves the service unusable: raising a limit is a
  loosening, so it gets one approval card and Windows Hello, while lowering one,
  removing one and correcting a price change at once with no card. Every default
  price says it is unverified and when it was written; every price says whether
  it is yours and the date you set it. `docs/ACCOUNT-KEYS-DESIGN.md` is the
  design.

- **The desktop tutorial no longer says the PC has one chat box
  (2026-10-06).** `backend/jarvis_tutorials.py` now teaches the big HUD
  window's own chat box and the **Open the Jarvis bar** button still beside it,
  and `jarvis-backend/` carries the same text.

- **Three comments that still described the HUD's box as opening the Jarvis bar now describe the reversal (2026-10-06).** `voice.rs`'s doc comment on `hud_open_bar`, the `hud-voice` set's comment in `permissions/surfaces.toml` and the matching line in `build.rs` all still said, in the present tense, that the PC has one chat box, so the HUD's own box opens it instead of chatting on its own - the rule the owner reversed when the box came back. They now say what the code does: the HUD's box is its own conversation, the button beside it opens the bar, and that window has no Temporary chat, no New conversation, no "Used in this answer" and no crisis panel. Comments only - no permission, command or behaviour changed.

- **Settings → Accounts now collects the server ADDRESSES, so email and Home Assistant work from the app itself (2026-10-06).** The card already held the four secrets (the IMAP username and password, the private calendar link, the Home Assistant token) in Windows Credential Manager - but no server address, so email answered "JARVIS_IMAP_HOST is not set - there is no mail server to read" and Home Assistant answered "not set up on this PC" unless the addresses were plain-text Windows environment variables. Eight addresses and one choice now have their own boxes (the mail server, its port and mailbox; the sending server, its port and how email is encrypted; the Home Assistant address; the calendar's CalDAV address); they are read from and written to the PC's own route and kept in `accounts.json` beside `web-search.json`, because an address is not a secret - it is a plain settings file, and the box shows what is saved. A key, password or token can never reach it: the route refuses every name but the eight. An environment variable you already set still wins, and the row says so.

- **One command installs Jarvis, and one command updates both halves
  (2026-10-06).** Setting Jarvis up was eight steps in order - copy the
  published backend, tell the PC where it is, let the patcher install the
  packages and write the settings file, deal with Ollama and the model, start
  it, then build and install the desktop app. `scripts\setup-jarvis.ps1` did
  the backend half in one command; it now finishes the job, installing the
  desktop app and running the live check, so a new PC is genuinely one
  command. `scripts\update-jarvis.ps1` is new: updating used to be two jobs
  that had to happen in a particular order - patch the backend, then rebuild
  and reinstall the desktop app - because an app updated alone spends its time
  saying "your PC's Jarvis cannot do that yet". It is that order as one
  command: stop Jarvis, get the newest code, patch the backend, update the
  desktop app, start Jarvis again, check it.

- **Neither of the two commands patches a backend by itself.** Each one
  patches by running `scripts\apply-patches.ps1`, unchanged - still the only
  thing that touches a backend, still rehearsing on a throwaway copy first.
  The install command hands the desktop half to the update command with a new
  `-SkipPatches` switch ("do not run the patch script this time"), so the
  patcher is not run twice on a first install. Where the desktop app is
  concerned the update command prefers the published signed installer and
  builds from this folder when there is none; when this folder IS a git
  checkout holding that release's commit or newer, it builds rather than
  downloading, so a branch's own newer build is never replaced by an older
  release. A folder that was unzipped rather than cloned has no history to
  compare, and the script says so instead of guessing.

- **Both commands are safe to run again, and both are honest about what they
  changed.** The update command keeps a log of its own output in `_jarvis-logs`
  inside the backend folder, and `apply-patches.ps1` keeps its own log of what
  it changed. Neither ever prints a token or a key. Both take `-Print`, which
  means "show me the plan and change nothing" - it writes no file, starts no
  process and installs nothing; it does make one read of the release page (a few
  hundred bytes, and it says so on screen) so the plan can say which route it
  would take. What stays by hand is printed on screen: the phone (INSTALL.md part
  3) and two switches in the desktop app's own Settings - "Let Jarvis Desktop
  start and stop Jarvis", and "Start Jarvis Desktop when Windows starts".

- **One limit of the desktop half, said on screen and in INSTALL.md.** When it
  downloads an installer it cannot check the signature published beside it -
  the small file that proves the installer is really this project's.
  PowerShell has no way to check that kind of signature, and the tool that
  makes it has no "check" command, so the script prints the file's SHA-256
  instead and says so in the plan as well as in the real run. The app's own
  Settings -> Updates button is the route that does check it; `-FromSource`
  builds the app from this folder and downloads nothing.

- **Checked rather than assumed (2026-10-06).** Both scripts parse under
  Windows PowerShell 5.1 and are ASCII-only outside comments;
  `backend\test_setup_script.py` grew from 23 to 30 checks for the new step
  (the install command must show the desktop step as a command and must not run
  it, and its `-SkipDesktop` guard must come before the call); a new
  `powershell-5` CI step runs the real scripts against stubs that record their
  arguments, including the release-vs-local build decision both ways; and
  `docs\CLAIMS.tsv` gains D07-D10.

- **The big HUD window has its own chat box again (2026-10-06).** This
  reverses the decision of 2026-09-28 that the desktop HUD's own box should
  open the Jarvis bar instead, "so the PC has one chat box". The box and its
  Send are shown and work exactly as the page always made them: type or press
  Enter, the answer streams in, and the window's own conversation is kept in
  History with its own id and the tag **HUD**. The **Open the Jarvis bar**
  button stays, now beside the box rather than instead of it, and the mic
  button is unchanged. What the box does not have - and the Jarvis bar does -
  is a **Temporary chat**, **New conversation**, the "Used in this answer"
  list and the crisis panel; those are now known limits of that window, not a
  reason to hide it. Only the packaged app was hiding it: the HUD page served
  on its own in a plain browser always showed its box, and still does. The
  suite's own check was inverted honestly rather than dropped - it now
  asserts the box and Send are *visible and working* (a message typed into
  them really reaches `/api/chat`), and still asserts the button exists and
  still asks the shell for `hud_open_bar`. Not yet typed in by hand on a real
  desktop run.

- **The phone's face photographs job was red because the runner had no sound
  library, not because anything here was broken (2026-10-06).** The job that
  renders the animal faces downloads Android's emulator and starts it. The
  download finished; the program would not start. The runner's own error said
  why: `libpulse.so.0: cannot open shared object file` - a sound library the
  emulator needs simply was not installed on the machine. So the job now
  installs `libpulse0` (the Ubuntu package that provides that one file) before
  it touches the emulator, and nothing else: the check that caught this - "the
  emulator exists but does not run" - is kept exactly as it was, and it still
  fails the step rather than reporting success. No test was weakened, no step
  removed, and the job still only renders; it cannot block a merge. Only a real
  run on GitHub can prove the emulator now starts.

- **Past approvals get their own screen on the phone.** The read-only list you
  asked for on 2026-09-27 was built and drawn inside the Inbox, and the
  approvals audit of 2026-09-30 found the one thing wrong with it: "It is only
  reachable via Inbox". The Inbox keeps its ACTIVITY row, which now opens a
  screen of its own (`jarvis-client/.../ui/screens/ApprovalsScreen.kt`) with
  the same fields the PC's Activity pane shows - what each card was, Approved /
  Denied / Timed out, when, and which device - and the same four filters.
  Nothing on it decides anything: no approve, deny, cancel, clear or re-open,
  no new permission, and no new way out of the PC. While "Hide memory lists and
  chat history" is on, the list hides behind the same Show as the phone's other
  history surfaces. With nothing decided yet it says "Nothing decided yet.",
  the PC's own words.

- **A full audit pass, recorded 2026-10-04 23:44 PDT (2026-10-05 06:44 UTC).**
  Twelve of fourteen read-only passes are complete and written up as five
  documents, indexed by `docs/AUDIT-PASS-2026-10-05.md`: a whole-project feature
  review, a comparison against Muse and ChatGPT "Dots" and the rest, a bug hunt
  across the backend, both clients and the Rust shell, a UI audit of both apps,
  and two deep audits (prompt injection end to end; dependencies and supply
  chain). Nothing in the product was changed - the pass only added documents.
  Two passes, disaster recovery and performance, were still running and are
  appended in a second commit. Headlines: the 12 GB card is installed and
  nothing is measured; fourteen of the worst defects are features or tests that
  silently do nothing (including **all spoken audio**, the "What Jarvis can see"
  privacy section, and 46 of 56 local UI suites); the live backend is exactly
  base + stack, with all 119 applied patches reverse-applying cleanly; and the
  rush latch that would catch "approve this now, before it expires" has no
  caller on Jarvis's own read path. The pass ends with eleven choice groups for
  the owner.
- **The "driven openly" rule is gone (2026-09-29, your decision).** You asked
  several times, after being told the risk each time, for stealth to be on for everything the
  new headless browser runs, so the old rule "nothing that hides that a
  program is driving, nothing that dodges a site's bot checks" no longer
  exists. The approval cards for chatbot websites no longer say "never hides
  that it is a program". What did not change: Jarvis never solves a captcha
  (it hands it to you, on the PC or with "Solve it here" on the phone), there
  is no proxy service, nothing private (email, files, passwords, memory) goes
  into a chat or a web page, every approval card still asks, and if someone
  asks Jarvis whether it is a bot it never says it is a person. The risk is
  real: a Gemini, ChatGPT or similar account could still be closed, and each
  card still says so; a spare account used only by Jarvis stays as advice. The
  browser window you see stays a plain, real browser (Jarvis adds no disguise
  to it) so you can take over at a captcha or sign-in. The new invisible
  browser (Obscura) with stealth is in the next entry. Where it is
  written: `CLAUDE.md` ("Stealth on for everything"), `docs/CHATBOT-DRIVER-DESIGN.md`.
- **A second browser with no window: the headless browser, Obscura (2026-09-29,
  both apps).** Jarvis's browser tool used to open only a browser window you
  can watch. It can now also choose **Obscura**, a small open-source browser with
  no window, for plain reading and quick lookups - per task: the visible window
  whenever you might need to sign in, pay or take over, the headless browser
  for simple reading (Settings, "Headless browser", picks which Jarvis prefers:
  Automatic, Always visible, or Headless). **Stealth is on for everything it
  runs** (your decision): it looks like an ordinary Chrome. That does **not**
  solve captchas, a site can still block or ban it, and signing in to a real
  account with any automated browser can get the account closed - so Jarvis
  never types a password with it and never solves a captcha, and at a captcha
  or a sign-in page it recognises it stops and tells you to ask again with the
  visible browser (a sign-in that starts with only a username or email box may
  not be recognised). **Off to
  start; turning it on is one approval card**; off is instant. Every page it
  opens and every click and box it fills is still listed on the same approval
  card as the visible browser's, and what it reads counts as outside text. It
  cannot reach your own network, uses no proxy, keeps no cookies, saves no files
  and opens no network port. You install it with **one PowerShell line** shown in
  Settings (Jarvis never downloads it itself): it downloads one named release,
  prints its checksums for you to compare and does not run it; a second command
  it prints checks it, and its checksum is then remembered and a different file
  is refused. It stops itself after 3 idle minutes, and the words it types and
  the addresses it opens are checked first. **A real Obscura has not been run yet** (nothing here
  could run a Windows program): `py -3 tools\check_obscura.py` is the real check.
  The chatbot driver and the support chats still use the visible browser, because
  they must hand a captcha to you in a window. Needs the new backend files
  (apply-patches.ps1 copies them) and the new desktop and phone builds.

- **Secrets in pictures you attach to a chat are covered with black too
  (2026-09-29, both apps).** Until now only "Look at this" and "Watch with me"
  had anything that looks like a key, password, card number, IBAN, crypto
  wallet, email or IP address painted solid black (never blurred) before a model
  looked. A picture you attach to a chat now gets the same, on the PC, before
  any model sees it - the second graphics card's picture model, the everyday
  model, or the words read for a model that cannot see. Nothing to hide: the
  picture goes on exactly as it was. A picture the PC cannot check (no text
  reader, a JPEG it cannot open) is NOT sent to any model, and the answer says
  so in words. The note beside the answer says how many places were covered
  (a number, never what they were). Both apps say, under the attachment:
  "Secrets in pictures you attach are covered with black boxes before Jarvis
  looks." Same limits as the screen: a password behind a show-password eye,
  tiny or stylised text and a QR code are not caught. "Photo to reminder" gets
  the same check on its words, so a proposed reminder never carries a key or a
  card number. Needs the new backend files (apply-patches.ps1 copies them) and
  the new desktop and phone builds. Not run on a real Windows PC yet.

- **Painted eyelids for the four animals (2026-09-29, both apps).** The red
  panda, pygmy owl, sea otter and monkey now have a lid of their own fur over
  the top of each eye, so the looks read at a glance: **waiting on you** a
  level, attentive lid; **something went wrong** a sloped, worried one;
  **dozing** a heavy, sleepy one. Idle, listening, thinking and talking have
  none, exactly as before. The lid eases in over about a second, never pops,
  adds no idle movement, is the same under calm motion and Still, and is left
  off entirely during a crisis-help answer (the animal stays neutral). It comes
  down as an animal nods off and lifts a little after the eyes open as it wakes.
  A blink still shuts the eye all the way, and a shut eye (asleep, mid-blink)
  keeps its dark line - the lid gives way to it. The robot has none. Painted in
  the shader's surface colouring, so it costs nothing per march step; the
  phone's shaders are still under 60,000 (panda 59,693, owl 52,064, otter
  55,018, monkey 59,602). Pictures in `docs/critters/eyelids/`; details in
  `docs/CRITTERS.md` "Painted eyelids". Needs the new desktop and phone
  builds; no backend change.

- **Three drawing fixes for the animal faces (2026-09-29, from the skeptical
  review).** (1) **The robot's eyes now show the colour of what Jarvis is
  doing.** They were coming out nearly white in every state (so listening
  and waiting on you looked the same pale pink); now listening is amber,
  waiting on you yellow, thinking violet, an error rose, idle cyan - the
  same colours the animals' orbs use. Both apps. The picture in
  `docs/critters/robot-states.png` was redrawn. (2) **Sharper animals on the
  PC:** the desktop draws each animal with 1.5 to 2 times more steps of its
  ray-marching than the phone can afford, which removes the dotted seam where
  the panda's tail crosses its cheek and the blue fringe round the monkey's
  head (wrongly drawn pixels against a very slow reference: panda 9,042 to
  289, monkey 3,481 to 46, owl 1,448 to 34, otter 2,822 to 4, robot 98 to 1).
  The phone's drawing is unchanged; the two now differ by a few edge pixels.
  Not measured here: how long a Windows graphics driver takes to build the
  longer shaders the first time a face opens - if a face is slow to appear,
  lower its number in `tools/gen_critters.py` (`DESKTOP_STEPS`). (3) **The
  owl's cream chest fades into the brown at the neck** instead of ending in a
  straight line. Needs the new desktop and phone builds; no backend change.

- **The animals move less when Jarvis is not being used, and never the
  same way twice (2026-09-29, both apps).** Three fixes from the skeptical
  review. (1) **Fewer small idle moves:** while you have not talked to
  Jarvis, typed, been given an answer or been asked something for five
  minutes, and your pointer (PC) or finger (phone) is not on the face, an
  animal does about one small thing (a tail flick, an ear turn, a stretch)
  in four - about 40 an hour instead of 155 to 190. Breathing and looking
  around are unchanged; the moves that remain are the same clips, only
  rarer, and they fade in and out over a couple of seconds when you come
  back. A face that has only just opened counts as used for its first five
  minutes; the Faces window always counts as used. (2) **Motion that does
  not repeat:** the five heads no longer sway together while talking (they
  were 86 to 91 percent alike; now about 5), breathing is uneven (each
  breath up to about 15 percent longer or shorter, never deeper than
  before), each small idle move differs a little in size (up to a quarter
  smaller) and length (0.8 to 1.25 times), and the owl's thinking head
  rolls half as far and turns to its orb now and then instead of all the
  time (it moved 87 percent of the time, now 19). Nothing moves faster or
  further than it did. (3) **Gestures land on the end of a sentence:** a
  nod used to peak about half a second after the sentence it marked, inside
  the next one. Both apps read each spoken clip before it plays, so they
  know where its sentences end and start the gesture early: it now peaks
  within a tenth of a second of the end, at every voice speed. A typed
  answer and the phone's own voice keep their old timing. Needs the new
  desktop and phone builds; no backend change.
- **A focus session shows the focus buddy, not a sleeping animal.** A focus
  session puts Jarvis on Quiet, and every screen drew Quiet as asleep, so the
  animal slept, woke to say "YouTube can wait" and dozed off again - the
  focus buddy never appeared. Now a Quiet that a focus session set shows the
  awake focus buddy on the PC's faces, the HUD, the tray icon and the phone;
  a Quiet you set by hand, and standby, stay asleep. The screen reader says
  Jarvis is working beside you and will not speak, except to name a
  distraction.

- **A still ring for errors, and a not-connected ring you can see.** On the
  four animals and the robot an error now also draws a thin, still ring with
  a gap at the bottom in the error colour, on both apps; it never moves, so
  it is fine under Still, calm motion and a serious moment. The
  "not connected" ring was so faint (1.65 : 1 against the background) that it
  looked like plain sleep from across a room; it is now a heavier, complete
  circle at about 4 : 1, and both rings stay readable on light and dark
  backgrounds. They differ by shape as well as colour (a gap or none, heavy
  or thin), so a colour-blind eye can tell them apart, and neither is the
  waiting-on-you clock.

- **The desktop tells a screen reader what the face shows, in the phone's
  words.** It used to say only "Jarvis isn't connected" (or a raw word like
  "banked"); the floating face, the widget and the face page now say the
  phone's eight sentences, plus not connected and a focus session.

- **The widget's sleeping Zs no longer get cut off.** In the widget's round
  120 px window the panda's and monkey's Zs poked out past the edge; they now
  stay inside it.

- **The docs pictures of the animals' eight states are redrawn.** The red
  panda's and pygmy owl's still showed a wave at "waiting on you" and a raised
  paw or wing at "error", removed on 2026-09-28. All five are redrawn from the
  current code and now show the error ring and the Zs.

- **A thumbs-down on a crisis-help answer no longer counts toward "suggest
  the bigger model".** Crisis messages were already never counted for the
  owner's own "that's wrong" words or for Jarvis struggling with a tool, but
  pressing the thumbs-down on the answer to a crisis message still added one
  to the "you corrected me" count. It no longer does. The backend keeps a
  short list of crisis-answer ids in memory only (ids, no words, nothing
  written to disk or to a log, gone when it restarts, oldest dropped after
  200), and the count skips any answer on it. Nothing else about the crisis
  help line changes. Needs `apply-patches.ps1` on the PC (`jarvis_agent.py`
  and `second-card-suggest.patch`).

- **The animals' new behaviours, on both apps.** Every animal and the robot
  now does what the six "Animal options" switches promised, each switch
  turning its own off: **listening nods** (a small nod in your pauses while
  you talk) and **gestures on Jarvis's sentence ends** (while it speaks
  aloud, its nods and paw lifts land where a sentence ends - a typed or
  quiet answer keeps the old timing); a **focus buddy** (in a focus session
  it works quietly beside you, and stretches when the session ends); a small
  **nod when a fact is saved** (never while App lock or "Hide memory lists
  and chat history" is on) and a **glow when a long answer is ready**;
  **petting** (on the PC stroke the Widget's face, or press, hold and stroke
  in the Faces window; on the phone a long press on the face, which does not
  open the Brain); **two cute idle moments** per face, taking turns after it
  has rested a while; a **goodbye and a hello** when you switch faces; and
  **seasonal touches** behind the face (off to start). "Keep the animal
  still" and serious moments switch every one off; calm motion makes them
  smaller - the focus buddy's pose included (it was drawn full size under
  calm; fixed). While Jarvis is waiting on you or something went wrong, a
  face switch is a quick gentle cross-fade, as in a serious moment (the
  animal used to bow and drop out of view). Also fixed in this batch:
  **the voice-speed fix** - the sentence-end finder missed almost every
  sentence end at the normal pace and faster (only 1 of 36 at the fastest),
  because sentences spoken back to back leave only about a tenth of a
  second of quiet; it now finds 25 to 34 of 36, and never one inside a
  sentence. **The options snap** - a face opened before the stored options
  were read eased in from the defaults, so a face set to Still moved for a
  moment; both apps now take them at once. On the PC the same now holds for
  a face switched back to after another, and for the seasonal touches. And
  on the PC, the sentence-end gestures
  now switch on when Jarvis's voice is first heard (they almost never did:
  the face turns to "speaking" as the text starts, before any sound), a
  face that has just opened waits its "rested a while" before a cute moment,
  and a stroke, a nod, a glow or a stretch is drawn at the full frame rate.
  Needs `apply-patches.ps1` on the PC for the new Petting wording
  (`jarvis_animal.py`). See `docs/CRITTERS.md`, "New behaviours".

- **A fifth face: the robot, on both apps.** From the owner's own picture:
  a small floating robot with a big white helmet, a glossy dark-blue visor
  with a glowing rim, ear pods with teal fins, an egg of a body with a teal
  shield, two mitten arms and no legs - it floats, with a soft shadow on
  the ground. No mouth and no orb: its glowing eyes carry the state's colour
  and its expression, and pulse with Jarvis's real voice. Now and then at
  rest it zips round inside its own picture (never out of it, never under
  "Keep the animal still", calm motion, a serious moment, a focus session or
  a petting hand), waves, or polishes its visor. It counts as an animal for
  every animal option and does everything the animals do - all eight
  states, powering down and booting up, the Zs, hello and goodbye, and the
  new behaviours. Its own voice under "Voice follows the face": Emma, two
  steps higher and a little faster (changeable in "Each animal's voice").
  The sky's switches now read "Show the sun and moon behind the face" and
  "Weather behind the face", so they fit the robot too. Pick it in the
  Faces window (PC) or Appearance (phone). Needs `apply-patches.ps1` on the
  PC for its voice and the new sky wording (`jarvis_voices.py`, `jarvis_sky.py`,
  `jarvis_reach.py`, `jarvis_quick.py`). See `docs/CRITTERS.md`, "Robot".

- **Animal options: every animal option in one place, on both apps, and
  Jarvis changes them when asked.** The desktop's Settings has a new
  "Animal options" card; the phone's Appearance has the same section. It
  holds "Keep the animal still", the sun, moon and weather (moved there),
  sharpness and frame rate (marked "on this computer" / "on this phone"),
  a button to the face's voice, and six switches for the new behaviours -
  listening nods, focus buddy, small acknowledgements, petting and cute
  idle moments (on to start) and seasonal touches (off). It covers every
  character face, the robot included. Those six are saved and shared, and
  the animals now do all six (see "The animals' new behaviours" above).
  **"Keep the animal still" and the
  switches are now shared**: kept on the PC, so a change on either device
  changes both (before, each device had its own Still - if either had it on,
  it stays on). Sharpness and frame rate stay per device. Say "keep the
  animal still", "stop the animal's nodding", "turn off the weather", "turn
  on the sun and moon" or "make the animal sharper" - answered at once,
  without the AI model; "make the animal sharper" changes only the device
  you asked from; switching the weather to Open-Meteo still shows its
  approval card first. Anything unclear gets a plain question back. Needs
  `apply-patches.ps1` on the PC (new: `jarvis_animal.py`, `animal.patch`).
  See `docs/JARVIS-API.md` section 93 and `docs/CRITTERS.md`, "Animal
  options".
- **An app Jarvis builds is now a project (the backend half).** In
  Projects, a coding project can be an app: its latest saved version and its
  open tasks show on its page. A task is one change kept as a separate copy
  of the app; open it, read the whole change, then **Merge** - ONE approval
  card lists every file and the whole change (Windows Hello on the PC, your
  fingerprint or PIN on the phone; never from a widget) - or **Discard**. On
  the PC you can paste a change in. A change too big for one card is refused
  with "ask Jarvis to split it". Nothing runs and Jarvis does not write the
  code yet (that waits for the 12 GB card). Deleting the project keeps the
  app's files; they can be added back. Also fixed: throwing away a task whose
  copy had been deleted by hand left its branch behind. Needs git. Not yet
  tried on your PC's real approval queue (`backend/README.md`, "Apps in
  Projects").
- **Chats: carry one on, see the whole thing, find it again.** Open any chat
  or Jarvis Live session in History and press **Continue this chat**: the
  Jarvis bar (PC) or Home (phone) picks it up where it stopped - the same
  chat, its newest kept messages, and its "read outside text" mark. The chat
  you are in now shows every earlier question and answer in a scrolling
  "Earlier in this chat" list, not just the last one. **Earlier chats** on
  Home and in the Jarvis bar (and "Chat history…" in the PC's tray) opens
  History. After 30 quiet minutes the next question starts a new chat, and a
  line says so. History marks each chat's kind - a Live session shows its
  length ("Live · 12 min · Today 14:05"), and "Show" can list Live sessions
  only, support chats, chats with other AIs or comparisons. **Chats Jarvis
  had with other AIs, and comparisons, are now kept in History** (encrypted,
  marked as outside text, never learned from or read aloud). A chat with a
  crisis moment is kept under the title "A difficult moment". Support chat
  records are never removed by "Delete conversations older than", start
  unticked in "Forget a time frame", and Delete asks once more. History: the
  list first (phone), dates with times and Today / Yesterday in both apps,
  answers without stray `**` and `#`, Copy on old answers, and "Forget a
  time frame…" at the top. The HUD window's own chat box now opens the
  Jarvis bar, so the PC has one chat box. Not yet tried on a real phone.

- **Fixed: chats that were not what they seemed** (the chat audit). Game and
  role-play chats were being kept in History although they are temporary -
  they are not any more, and both apps now say "This looks like a game or
  role-play, so it's a temporary chat". Deleting the chat you were in (from
  History, "Erase the words" with its chat, or "Forget a time frame") left
  its words going to Jarvis and brought it back under a new title - now a
  new chat starts and says why. "Move it here" in Jarvis Live on the phone
  carried on the wrong chat. "Erase the words" now names the chat it would
  also delete, and says plainly when there was none. Projects no longer
  promise that Jarvis reads a project's instructions in chats (it does not
  yet). The Brain's History and Projects status line no longer sits on
  "reading…". The phone's "Forget a time frame" and chatbot forms keep what
  you typed when you scroll or turn the phone; the phone now says when a
  temporary chat starts or ends, and "New conversation".

- **Solve it here: a captcha handed to your phone.** When a chatbot website
  or a customer-support chat that Jarvis is using stops at a captcha, a
  sign-in page or an "unusual activity" page, your phone now says so ("Gemini
  needs you") and offers **Solve it here**: a live picture of that one
  browser window on your PC, and your taps and typing passed back to it -
  only while Jarvis is paused there, never saved on either side. Jarvis never
  solves it for you. Some captchas refuse taps passed on this way; "Solve it
  on the PC instead" is always there, and the PC's Brain shows the same
  alert. Press Resume when it is done (Resume asks with a card, as always).
  Not yet tried against a real captcha.

- **Jarvis Live extras.** On the PC: a key to start or end Live, off until
  you pick one in Settings -> Shortcuts (Alt+Shift+L is free for it). On the
  phone: a Quick Settings tile (with the minutes left), the headset button
  (press to stop Jarvis talking, hold to turn the microphone off or on - it
  never approves anything), a "Live ended - Resume" notification for ten
  minutes, a Bluetooth headset's microphone used while one is connected (the
  Live screen says which microphone), "Talk about this in Live" in the Share
  sheet (the shared text is outside text and goes when you tap Send), and
  "End Live when" on the Security screen, like the PC's: when App lock would
  ask again (the default), or only when the phone's screen locks (asks for
  your fingerprint or PIN). Not yet tried on a real phone.

- **Chat with customer support for me.** Jarvis can chat with a company's
  customer support for you - Groupon first - in your name, in a browser
  window you can see on the PC. Fill in the company, what you want done and
  the details Jarvis may give (each one exactly as written) on either app's
  Brain; ONE approval card shows all of it and the company's terms risk
  (your real account could be closed). You open the chat on the help page
  yourself; Jarvis writes from there. **Every offer - a refund, a credit, a
  cancellation - gets its own card**, and nothing is accepted before you
  approve it; the app offers Decline, Say something else and Take over,
  never Accept. "Are you a bot?", identity checks (card digits, security
  questions, codes) and a detail not on the card are handed to you - Jarvis
  never claims to be a person and never sends a password, card number or ID
  number. The chat is kept in your encrypted chat history; Export on the PC
  saves a plain text copy. Not yet tried on Groupon's real site: run the
  read-only check first (backend/README.md, "Chat with customer support for
  me").

- **Forget a time frame.** Say or type "forget what you learned last
  week" or "delete my chats from 1 to 15 September", or open it yourself:
  the desktop's Brain -> History, or the phone's Brain. Jarvis lists every
  fact it saved in those days and every chat from them, each ticked; untick
  anything to keep and tap **Forget these**. One approval card lists
  everything, and you approve it by tapping - saying "yes" does nothing.
  The facts are forgotten, exactly like Forget, and the chats deleted; for
  **10 minutes one tap on Undo puts it all back** (the Undo is kept in
  memory only, so it also ends if Jarvis restarts). A chat that also has
  messages from other days is marked, because the whole chat goes. At most
  200 at once. If a date could mean two things ("on Monday" said on a
  Monday, "3/9"), Jarvis asks. Erasing a fact's words for good is still
  "Erase the words", one fact at a time. This is the one place Jarvis
  deletes many things at once. Not yet tried on your PC's real memory.

- **The money limit for chatbots with a key is now a hard stop.** Every
  message asks the service to keep its answer short enough to fit in what
  is left of your monthly limit (at most 8,000 word-pieces, fewer as the
  month is used), so one long answer cannot carry a month past it. An
  answer cut short says so under it in both apps: "Jarvis asked for a
  short answer so it stays within your limit; the rest was cut off." Each
  company calls this setting something different; each name was checked in
  that company's own code (OpenAI, Groq, OpenRouter, Mistral, and xAI from
  its own client program). **DeepSeek's could not be confirmed, so no cap
  is sent to DeepSeek** - it keeps the old check before each message. For
  every service except OpenAI, whether hidden "thinking" counts inside the
  cap is not stated, so Jarvis leaves room for it - a guess, so a month
  can still end slightly over there. See it per service with
  `cd "<your backend folder>"; py -3 jarvis_chatbot_api.py spent`. Not yet
  tried against the real services.

- **A monthly money limit for chatbots with a key.** Each service Jarvis
  reaches with an API key (OpenAI, DeepSeek, Mistral, xAI, OpenRouter,
  Groq) now needs a monthly limit before it is used - set on the PC with
  one line, for example
  `cd "<your backend folder>"; py -3 jarvis_chatbot_api.py limit openai 5`
  for $5 a month. Jarvis estimates each message's cost from the
  word-pieces the company reports and a price list, stops a service when
  its month reaches the limit, and checks before every message that it
  cannot go over. The approval card and both apps show "About $4.55 of
  $5.00 left this month for OpenAI", and "Used so far" adds "about $0.03".
  **The prices Jarvis starts with are not checked** (written from memory,
  no price page could be opened): see them with
  `py -3 jarvis_chatbot_api.py spent` and correct one with
  `py -3 jarvis_chatbot_api.py price openai <in> <out>`. It is an estimate,
  so a month can end slightly over. Limits and prices can only be set on
  the PC; the apps only show them. Not yet tried against the real services.

- **Jarvis Live, fixed after four reviews - and your three answers built.**
  - **After a crisis answer, Live gets more time.** It does not end at its
    time limit until at least 30 minutes after the last such answer, and
    it does not say "minutes left". It is quiet about it. You can still end
    it any time. Both apps.
  - **One "Interrupting Jarvis" setting** instead of two, for Live and
    everyday voice alike: "Interrupt by voice" (recommended), "By button
    only", or "Don't interrupt". On the PC: Settings -> Voice, where the old
    switch was. On the phone: the Readiness screen. Your old choice carries
    over (the old switch off becomes "Don't interrupt"; Live's "tap only"
    becomes "By button only").
  - **Remarks to someone else are not kept in chat history at all** (they
    were kept, marked "(not for Jarvis)"). An old one still in your history
    shows as "(not for Jarvis)".
  - **"End Live when"** (PC, Settings -> Voice): with App lock on, Live ends
    when App lock would ask again (the default), or only when Windows locks
    - the looser choice asks with an approval card. The phone keeps App
    lock's own rule.
  - **Clearer words:** "End Live" (not "Stop"), "Mic off" / "Mic on" (not
    "Mute"), "Listen anyway" during a call; every pause says what to do
    next; "your PC", never "your desktop"; when Live ends it says why, in
    a sentence, and says it aloud when it ended by itself.
  - **Fewer surprises:** "that's it" or "I'm done" in answer to a question
    no longer ends Live; only a card raised during Live pauses it (an old
    waiting card does not); tap buttons no longer come out garbled; typing
    counts as talking for the quiet timer; Esc on the PC hides the bar but
    keeps the conversation; a remark to someone else no longer wipes the
    answer (or the crisis help) off the screen.
  - **Easier to find:** the phone has a strip on Home while Live is on and
    a "Live" shortcut when you long-press the app icon; the PC's tray icon
    gets a red mark; "What asks first" lists "Start Jarvis Live - does it
    without asking" in both apps; Brain's old "Live" tab on the PC is now
    called "Now".
  - Said plainly: none of this has run on your PC or phone yet, and the
    phone's part is only compiled by GitHub.

- **Jarvis Live: talk back and forth, on the PC and the phone.** Press
  Live (the Jarvis bar, the tray, or Home -> Live on the phone) or say "Hey
  Jarvis, let's talk", then just talk - no "Hey Jarvis" before each
  sentence. Every sentence is still checked to be your voice on your PC
  before any words are made of it, and cards still need a tap (Jarvis stops
  listening while one waits). A sign shows the whole time ("Jarvis Live ·
  24 min left"), with Mute and Stop; on the phone a notification with End
  and Mute. It ends when you say "Okay Jarvis, that's all for now", press
  Stop, after 90 quiet seconds, or at 30 minutes ("give me twenty more
  minutes" adds time). After a spoken question, tap buttons ("Yes", "No")
  answer it; you can type too. It pauses itself during a phone or video
  call. Two new voice settings in both apps: "Jarvis Live" (how far it is
  trusted under "Only trust the talk button"; trusted fully by default) and
  "Interrupting Jarvis in Live" (by voice, or by tap only). Said plainly:
  it needs your voice trained first; very short replies ("yes") are still
  too short to check, so use the buttons; nothing has been timed on your
  PC; and **the camera part is built but switched off** until the second
  graphics card is in and passes the photo test.

- **Chatbot driver fixes, and a correction: every chatbot is reachable from
  both apps.** The entries below that say "still not usable from either
  app" are out of date: both apps' chatbot screens can start a
  conversation with any of the chatbots once it is set up (a website signed
  in, a key saved, or the model chosen). None has been tried against the
  real site or service yet. Fixed at the same time: a website window no
  longer reads an answer from a different chat you clicked while the first
  answer was coming; each site's self-check now asks two questions in the
  same chat, so a wrong guess about a site's chat address is caught by the
  check rather than mid-conversation; a site no longer shows "ready" after
  a sign-in window that was closed before you finished signing in (if you
  signed in to Gemini before this change, run
  `py -3 jarvis_chatbot_gemini.py sign-in` once more - it finishes at once
  if it is still signed in); the second AI on your PC no longer ends with a
  wrong "did not answer within 180 seconds" when it was only waiting for
  your own chat, and Stop now cancels its answer so the graphics card is
  freed; and a few words are now right (no "leaves this PC" or "(this PC)
  (this PC)" for the second AI on your PC, and the real reason when a
  key-based chatbot is not set up).

- **A new voice setting in both apps: "Answers about your screen after
  "Hey Jarvis"".** If you choose "Only trust the talk button" for
  hands-free, an answer about your screen to a question that starts with
  "Hey Jarvis" now stays on screen - written, not read aloud. This setting
  lets you allow reading those answers aloud anyway: "Read aloud" shows an
  approval card first; "Keep on screen" (the default) applies at once. With
  "Same as the talk button" it changes nothing, and the settings page says
  so. It is under Settings -> Voice on the PC, and Checks -> Voice check on
  the phone. Said plainly: Jarvis cannot look at your screen from either
  app yet, so for now the setting is stored and waiting.


- **Ask several chatbots and compare** (both apps, Brain -> "Talk to a
  chatbot for me"). Tick "Ask several and compare", pick two or more
  chatbots, type the goal once. One approval card lists every chatbot
  Jarvis would ask. Jarvis then talks to each one in turn, under the same
  limits and checks as a single conversation, and at the end writes one
  summary on your PC: where they agree, where they disagree (and who said
  what), the sources each gave (not checked by Jarvis), and which one
  dropped out and why. If one shows a captcha or a sign-in page, Jarvis
  leaves it out and carries on with the others. Pause, Resume and Stop act
  on the whole comparison. Up to 3 chatbots with one graphics card, 4 with
  two (you confirmed these numbers). Not yet tried against the real
  chatbot websites.
- **The chatbot chooser is a list you can read on a phone.** It used to be
  one row of buttons, and with sixteen chatbots most fell off the screen.
  Both apps now list them one per line under three headings - "Websites (a
  browser window on the PC)", "With a key (each message costs a little)",
  "On this PC" - with the reason under any that is not set up yet.
- **A conversation through a key shows what it used**: "Used so far: 3
  requests, 4,215 word-pieces (tokens), model gpt-5-mini" (per chatbot in a
  comparison). The card already said Jarvis would show this; neither app
  did.
- **"What Jarvis can reach" showed the chatbot ways out as Off** although
  both apps can start conversations: a switch the routes should have set
  was never set. Fixed.
- **The chatbot driver can now work eight more chatbot websites - still not
  usable from either app.** ChatGPT, Claude, Microsoft Copilot and
  Perplexity, plus DeepSeek, Grok, Le Chat (Mistral) and Meta AI (these
  last four picked as "other commonly used" websites - say if you want any
  left out). Each works exactly like Gemini: a browser window you can see,
  a steady typing pace, nothing hidden, and a stop to ask you at any
  captcha, sign-in or "unusual activity" page. Each has its own spare
  account, signed in once by hand, and each company's terms restrict
  automated use, so that account may be blocked or closed. Perplexity's
  listed sources are copied as text under its answer, never opened. How
  Jarvis finds each site's buttons could not be tried against the real
  sites: run each site's one-line self-check on the PC first
  (`backend/README.md`).

- **The rules for letting Jarvis look at your screen - not in the apps
  yet.** "Look at this" (one look when you ask) and "Watch with me" (a
  session you start and stop, 30 minutes unless you say otherwise, 2 hours
  at most) now have their rules written and tested on the PC side: Jarvis
  pauses on password boxes, on anything on your "Never look at" list
  (password managers and Windows sign-in to start with; adding is instant,
  taking something off asks with a card), on protected windows and on pages
  whose site it can't read; it checks just before and just after each
  picture and throws the picture away if either check fails; it keeps
  nothing it saw; and "Stop everything" ends a session. Answers about the
  screen will be read aloud unless a sensitive fact was used, like web
  search answers. There is no key, button or setting for it in either app
  yet, and the parts that read Windows itself are the next step.

- **A switch to turn off swiping on approval cards** (phone, Security).
  Swiping right to approve and left to deny stays on unless you turn it
  off; off, every card is decided with its buttons only. Turning it back on
  asks for your fingerprint or PIN.
- **The chatbot driver can also use a key, or a second AI on your PC -
  still not usable from either app.** With a key saved on the PC, Jarvis
  can hold its one-card conversation with ChatGPT (OpenAI), DeepSeek,
  Mistral, Grok, OpenRouter or Groq through each company's official API.
  The key stays in Windows Credential Manager and goes only to that
  company. Each message costs a little on that account; Jarvis shows the
  word-pieces (tokens) used, but there is no money limit yet. Or it can talk
  to another AI model on your own PC, where nothing leaves the PC: with one
  graphics card that is the same model Jarvis uses, with both cards any
  model you already have. How to save a key: `backend/README.md`.
- **The chatbot driver's Gemini part is written - still not usable from
  either app.** Jarvis can now open its own Gemini window (gemini.google.com,
  in a browser window you can see), type a question at a steady pace, and
  read back only the answer to it. (It used to promise it never hides that
  it is a program; you reversed that on 2026-09-29, see above.) At a captcha, a sign-in page or an "unusual activity" page it stops and
  asks you instead of trying to get past it. It uses its own browser profile,
  which you sign in to once, by hand, with the spare Google account. Before
  real use, run the one-line self-check on the PC (`backend/README.md`) - it
  sends "What is 2 plus 2?" and says PASS or FAIL for each step, because the
  way it finds Gemini's buttons could not be tested against the real site.
- **"Talk to a chatbot for me" now has its screens in both apps - but no
  chatbot can be reached yet.** On the PC it is a card in Brain -> Work; on
  the phone, a card in Brain. You choose the chatbot, type what Jarvis
  should find out (the card says these words are sent exactly as typed),
  set the most messages and minutes and any words it must never send, and
  Start asks for one approval card - nothing is sent before your yes. While
  it talks you see the conversation, with the chatbot's words marked
  "outside text", plus Pause, Resume and Stop; changing a limit asks a new
  card; the summary stays on screen at the end and is never read aloud. The
  phone also shows "Talking to Gemini, 3 of 5" with a Stop button. Gemini's
  part is still being built, so today Start says so and does nothing.
- **New: Projects in both apps.** Brain now has Projects on the PC and on
  the phone. Make a project, write how Jarvis should help with it and a
  few notes, and track numbers ("benchmarks") - log a number with a tap,
  see a small chart of your numbers over time with your target as a
  dashed line, and whether each one is better or worse than last time.
  Health and money numbers show "private - not read aloud". Deleting asks
  "are you sure?" first. A coding project's folder is chosen on the PC
  (from "Folders Jarvis may look in"); the phone says "Set on your PC" for
  that. The "Shareable" switch asks you with a card to turn on, and turns
  off at once.
- **New: take a wrong private mark off.** Jarvis sometimes marks a number
  private by mistake - it reads "5k time" as money. You can now remove
  that mark; because the numbers may then be read aloud, it asks you with
  one approval card first. A mark you added yourself comes off at once.
  Renaming the benchmark checks its name again.
- **Backups and the data-health check now include your projects**
  (`projects.db`). Before this, a backup would not have kept them.
- **The core of the chatbot driver - not usable yet.** The part of Jarvis
  that will hold a conversation with an AI chatbot for you (Gemini first)
  is written and tested on the PC side: one approval card per
  conversation, a check before every message so nothing private leaves,
  and stops at any captcha or sign-in page. There is no button for it in
  either app yet, and the Gemini part is not built.
- **Fixed: marking a crisis answer "wrong" counted toward "suggest the
  bigger model".** Crisis messages are never learned from and never
  counted; the thumbs-down on a crisis answer was the one place that still
  counted. It no longer does. A thumbs-down on any other answer counts as
  before.
- **Fixed (phone): "Use" on a model that cannot chat.** Brain › Model on the
  phone offered "Use" on memory-search models such as nomic-embed-text,
  which would leave Jarvis unable to answer. Like the desktop, their row now
  has no "Use" and says "for memory search only - it cannot chat". Both
  apps follow one shared table of cases, so they cannot drift apart.
- **New (phone): reconnects as soon as the network changes.** Walking out
  of Wi-Fi, or switching Tailscale on, used to leave the phone on a dead
  connection for up to about a minute and a half. Now it reconnects within
  a couple of seconds. Approving still waits until the link is trusted.
- **New (phone): "Tailscale (or Meshnet) is off on this phone".** When the
  link is down and the phone has no VPN running at all, Home and Checks
  say so under the link.
- **New (phone): Show token on the pairing screen.** The 43-character token no
  longer has to be typed blind. It starts hidden, is never saved anywhere
  new, and screenshots and screen recording are blocked while it is shown.
- **New (phone): "Background restart" is offered once after pairing.** A
  line on Home, in the same words as the Checks card, with "Keep link
  alive" and "Not now". It never comes back after either.
- **New (PC): the live check asks "Can your phone reach Jarvis?"**
  (`selftest.py --preflight`): is a phone address set, is it a Tailscale or
  Meshnet one, is Tailscale or Meshnet on this PC, is Jarvis listening
  there, and is there a Windows Firewall rule - each with the one line or
  the one setting that fixes it.
- **Docs: a Quick start at the top of `docs/INSTALL.md`** - the shortest
  way to a first typed chat, with the desktop app starting Jarvis, then
  pairing the phone.
- **Projects, first part (on the PC's side only - not in the apps yet).**
  Jarvis can now keep projects: a coding project (an app) or a life
  project ("run a half marathon"), each with its own instructions, a few
  notes, a to-do list and the goals it belongs to. A coding project's
  folder must already be one of "Folders Jarvis may look in", and is
  chosen on the PC. Each project can track numbers ("benchmarks"): say
  "I ran 5 km" or "log my weight as 72.5 kg" and Jarvis writes it down
  without the AI model and says whether it is better or worse than last
  time - but only when one of your projects tracks that number.
  Weight, heart rate, money and other health or money numbers stay on
  screen and are never read aloud. A "Shareable" switch per project
  starts off, and turning it on asks you with a card; nothing is ever
  sent by it yet. Running tests and Jarvis changing code come later. The
  screens in both apps are next.
- **Fixed (phone): "open help", "connection", "the morning briefing",
  "about" and "Jarvis's voices" opened Settings at the top.** Each now opens
  the phone's own place for it - Help, Checks, Brain or "Jarvis's voice" -
  and scrolls to it. A setting that only the PC app has (keyboard shortcuts,
  accounts and a few more) now says so in one line instead.
- **Fixed (phone): "Catching up…" explained properly.** An approval card
  said "Not connected to the desktop" even while the phone was connected and
  only catching up. It now says Jarvis is catching up with your PC and the
  decision waits until then. Checks calls this state "Catching up…" like
  Home (it said "Stale"), Home shows Retry next to it, and coming back to the
  app reconnects on its own. Approving still waits until the link is
  trusted again.
- **Fixed (phone): the "Brief me now" and "What did I miss?" app-icon
  shortcuts** opened Brain at the top. Each now asks its question on Home,
  as if you had typed it.
- **Fixed (phone): an answer made without the AI model** said "answered on
  this PC" on the phone. It now says "on your PC".
- **Answers from web search and home status are read aloud again when you
  ask by voice.** Before, any answer where Jarvis used a tool was kept on
  screen ("It's on your screen."), so a spoken question answered from the
  web was never spoken. Now only web search and home status (which is
  where the weather comes from) are read aloud. Email, calendar, notes,
  files, memory and any other tool still keep the answer on screen, and so
  does Jarvis not being sure which tool ran. Both apps follow one shared
  table of cases, so they cannot drift apart.
- **Fixed: one "Hey Jarvis" heard by both the phone and the PC.** Both
  used to answer, so you got two answers - and a timer or "next song" could
  happen twice. Or, after a plain "Hey Jarvis.", the second device used up
  the listening moment and your real question was thrown away. Now only the
  first copy is answered, the other device stays quiet, and each device
  listens for its own follow-up question. Your voice is still checked
  before any words are written down.
- **Fixed (desktop): Forget's "when did this stop being true?" box.** "Sept
  20" was saved as the year 2001; now a date with no year means the most
  recent one that has passed, a date in the future is refused, and a date it
  cannot read asks again instead of quietly dropping the Forget you said yes
  to.
- **Fixed (desktop): "Use" on a model that cannot chat.** Memory-search
  models such as nomic-embed-text say "for memory search only" instead.
- **Fixed (desktop): raw underscores in answers** - `_words_` now show in
  italics.
- **Fixed (desktop): putting one of two approval cards aside hid both.** The
  next card now shows, and the count of waiting cards is right.
- **Clearer (desktop): Erase's second question** says what OK and Cancel
  each do. Two small wording slips fixed in Hardware and Voices.
- **Fixed: typing the phone's pairing key exactly as the PC shows it.** The
  PC shows the key in groups of four with spaces, to make it easier to read.
  The phone kept those spaces, so the key was refused. The phone now drops
  them as you type, and the PC says to leave them out.
- **Fixed: "Tell me when this page changes" alerting when nothing visible
  changed.** It compared the whole page, including hidden codes that change
  on every visit. It now compares only the words you can see. Watches set up
  before this record the new kind once, quietly, instead of alerting.
- **Fixed: "Start with Windows" said on when Task Manager had it off.**
  Settings now reads Task Manager's Startup switch too, and turning it on in
  Jarvis turns that switch back on.
- **Clearer message** when the patch script is pointed at the wrong folder:
  it no longer sends you looking for "OpenJarvis", an unrelated project.

- **Sharper animals, and more frame-rate choices, on both apps.** Quality
  now reads **Lower, Balanced, High, Maximum**, each with a one-line note on
  what it costs (your saved choice still works). At Maximum the PC draws an
  animal at 2x2 samples per pixel and the phone at its full resolution -
  the edges go from visibly stepped to smooth (measured on the panda: edge
  error 9.4 -> 3.2 out of 255 on the PC; on the phone High is now 0.75 of
  full resolution instead of half, 23 -> 13). With Auto adjust on, an
  animal starts at High and goes up to Maximum by itself only when its
  frames are very cheap; it steps down Maximum, then 60 fps, then Balanced,
  then 30 fps, then Lower. Battery saver on the phone still overrides it
  all. **Frame rate** adds 30 and 90. When the screen cannot match a pick
  exactly it rounds up, never down: on a 144 Hz screen 90 draws 144, and
  120 on a 165 Hz screen draws 165.
  An animal at rest is drawn 60 times a second when there is room (else
  30), and smoothly at full rate while it stretches or scratches; picking a
  rate lifts its rest to that. The PC's widget, HUD and floating face now
  rest too (they drew every frame). Both apps show "fps · ms per frame ·
  animal resolution" (the Faces window's full-size view; the phone's Face
  editor). A small face skips its soft shadow. See `docs/CRITTERS.md`,
  "Resolution and frame rate".

- **A red panda face** - the first animal among Jarvis's faces, on the
  desktop and the phone. It sleeps when Jarvis is on standby, perks its ears
  and tilts its head when listening, gazes into a glowing orb when thinking,
  talks with Jarvis's voice, waves when an approval is waiting, and scratches
  its head at an error. The orb is your colour for each state. Drawn in 3D
  by the graphics card with no model file; see `docs/CRITTERS.md`.
- **A pygmy owl and a sea otter** join the panda, on both apps. The owl
  perches on a branch, turns its head to follow the room and waves a wing
  when something is waiting on you; the otter floats on its back in a
  little pool, taps a glowing pebble while it thinks and covers its eyes
  with its paws to sleep.
- **A monkey joins the animals**, on both apps - from the owner's own
  picture: warm brown fur, a big peach heart of a face, round ears, a tuft
  on top and a long curly tail. It hangs by one arm from a vine and swings
  gently, a little livelier than the other three; its banana is its orb and
  glows in your colour for each state. To sleep it climbs up and sits on the
  vine, tail curled round it. Its voice (with "Voice follows the face") is
  Michael, one step higher. See `docs/CRITTERS.md`.
- **The sun, the moon and the weather behind the animals**, on both apps,
  both off until you switch them on (Settings, Appearance, "Sun, moon and
  weather" on the PC; Appearance on the phone). Type your town once on the
  PC and the real sun rises, arcs over the animal and sets at the right
  times, and at night the moon shows in its real shape - worked out on your
  own devices, nothing sent anywhere. The weather adds soft rain, slow snow
  or wind, from your own Home Assistant or from Open-Meteo online (that one
  asks with an approval card first, because it sends your rough position).
  It stays dark and calm, dims when Jarvis sleeps, and holds still under
  reduced motion. See `docs/CRITTERS.md`, "The sky behind the animals".
- **Animal faces tidied after their audit:** no more see-through specks
  along the otter's outline against its pool; the owl's thinking orb now
  circles clear of its head, and its glow no longer shows through the face;
  no starburst of streaks on the owl's crown seen from above; the panda's
  tail no longer shades itself with a false shadow band.
- **The animals' mouths follow Jarvis's real voice.** Each spoken answer is
  read up front into a mouth track - how open, how wide ("ee"), how round
  ("oo"), shut in pauses and on m/b/p - and played in step with the sound
  you actually hear, on the PC (every window that shows a face) and the
  phone. When Jarvis answers without speaking (typed, Quiet mode, kept on
  screen), the animals keep their mouths shut. See `docs/LIPSYNC.md`.
- **Voice follows the face.** With the red panda, owl or otter showing,
  Jarvis's built-in voice becomes that animal's - its own voice, pace and a
  slightly higher pitch. A switch in both apps, on to start, right under
  "Jarvis's built-in voice"; it never asks first. A voice you recorded still
  wins.
- **Choose each animal's voice.** Under "Voice follows the face", the red
  panda, owl and otter each get their own row: pick any of the eleven
  built-in voices, make it deeper or higher, and choose Slower, Normal or
  Faster. **Try it** plays a short line in that voice; **Reset to its own
  voice** puts it back. The mouths still move in step with whatever you
  pick. It never asks first. Needs the patch script run again on the PC.
  **Try it** never plays over Jarvis: it waits while Jarvis is talking or
  listening, stops the moment you start a question, and says the same
  words on the PC and the phone. On the PC it plays in the Settings window,
  so the faces in the other windows stay still while it plays.
- **The animals move their bodies, calmly.** Each looks at something (often
  you) and holds the look, its head following its eyes part of the way;
  blinks, small weight shifts, the panda's tail swish, and a small idle
  happening about every 20 seconds. While speaking they lean in and gesture
  now and then - never busy. Built on published MIT work (Spring-It-On,
  TalkingHead, airi, ChatVRM), credited in THIRD-PARTY-NOTICES.txt. See
  `docs/CRITTERS.md`, "How they move".
- **Rising "Zs" while an animal sleeps.** On standby - by the schedule or by
  hand - small z's float up from beside its head, two or three at a time,
  on both apps. Not when Jarvis simply cannot be reached: then it is the
  hollow ring alone. With reduced (calm) motion, one still z instead.
- **The animals wake up and nod off**, on both apps. Leaving standby, each
  plays a short, calm wake-up (about two seconds): the panda opens its eyes
  with a slow double blink, stretches and perks its ears; the owl opens one
  eye, then the other, and ruffles its feathers; the otter rubs its eyes
  and stretches in the water. Going to standby, each nods off (about three
  seconds) before the Zs rise. The mouth never moves (no yawn); waking into
  an approval or an error, and with calm, serious or "Keep the animal
  still" on, only the eyes open or close. See `docs/CRITTERS.md`.
- **"Keep the animal still"**, off to start: the animal only breathes and
  blinks - no looking around, gestures or idle happenings. On the PC in
  Settings -> Appearance -> "Face on this computer"; on the phone in
  Appearance -> More options, under Motion. Each device keeps its own
  choice. No card.
- **Serious moments stay calm and plain.** While a crisis answer is being
  given or spoken, every animal face (the PC's widget, floating face and
  HUD, and the phone's Home) drops the gestures and tilts and simply
  listens; waiting on an approval is an attentive, still look (no wave),
  and an error a still, concerned one.
- **"Jarvis isn't connected" looks the same everywhere.** Every face shows
  standby with the same thin hollow ring on both apps (the PC's ring was
  nearly invisible and breathed; it is now the phone's fixed colour). The
  tray icon now goes to standby's colour when the link drops, and never
  shows the approval colour while approvals are blocked.
- **The PC notices a graphics card that cannot keep up** with a face and
  draws a flat version instead, trying the card again after a minute; the
  Faces window's gallery works from the keyboard (Tab, the arrow keys,
  Enter).
- **Sharper animals**: fewer see-through or stray specks along their
  outlines, measured against a slow exact render (`docs/CRITTERS.md`,
  "Drawing quality").

**New: watches**

- **"Tell me when a search shows something new."** Jarvis runs your search
  once a day (every 6 hours at most) through the search service you chose -
  never another one - and tells you when new results appear.
- **"Tell me when the price on <address> drops below X."** The price is read
  by plain code, not the AI, and shown under the watch so you can check it
  picked the right number. Jarvis never buys anything.
- **GitHub watches:** "tell me when CI fails (or finishes) on owner/repo" and
  "tell me when PR #12 on owner/repo merges". Read-only, using the GitHub key
  you already have. One line to add on the PC: `github_read = "auto"` under
  `[autonomy.tiers]` in `jarvis-framework.toml` (the refusal message names it).
- **A watch that stops working tells you once** (at most every 12 hours)
  instead of failing silently, and clears by itself when it works again.
- **Page watches ignore hidden page bytes**, so a page nobody changed no
  longer counts as changed (a fix ported from another branch).

**New: Brain upgrades**

- **Search what was said in your old chats**, in both apps' History - not
  just titles. Each match shows the words in place, and "Find in this chat"
  steps through them. The search runs on your PC; nothing is saved and
  nothing goes to the AI.
- **"History of this fact"** on the PC's Memory tab: every earlier wording,
  with the changed words marked. Erased words never come back.
- **Galaxy now shows the people and things Jarvis knows about.** Click a name
  to open "About <name>".
- **Fixed: Galaxy could show memory while "Windows Hello for memory lists"
  said it was hidden.** The HUD's copy is covered too. Galaxy's search now
  counts every match and says when nothing matches.

**New: reminders, your phone, and Lockdown**

- **"Remind me next time I talk about X."** When your own words later mention
  it, Jarvis brings it up in the chat. At most 3 times, never out loud if the
  topic is sensitive, gone after 90 days. No card.
- **"Ring my phone."** Said to Jarvis on the PC, your phone rings on its alarm
  sound - even on silent - with a Stop button, for at most 2 minutes. It never
  rings for an old message.
- **"Playing on your PC" on the phone's Home:** previous, play, pause, next.
- **Lockdown.** One tap (or "lockdown") makes everything that would leave the
  PC ask first, and anything that runs by itself stop. Turning it off is on
  the PC only, with a card and Windows Hello. Not yet covered: the ntfy push
  notice, which lives in your own `jarvis_gate.py`.

**New: smarter memory**

- **"Where did I put ...?"** Tell Jarvis "the passport is in the top
  drawer", then ask "where's my passport?" - it answers at once, without the
  AI model, and says when you told it. A newer place replaces the older one.
  ("Where's my phone?" still rings your phone.)
- **Facts keep "until" dates from your words** ("on holiday until 12
  October") and are never hidden by themselves when the date passes: Jarvis
  asks "Still true?" instead.
- **Overnight memory tidying now actually runs, cards only:** at most five
  "Still true?" or "Which is true now?" cards a night, using the AI on this
  PC only, and only while its switch is on. It never changes a fact by itself.
- **Deleting a chat offers to forget the facts it taught you**, with nothing
  ticked to start, and "are you sure?" before anything is forgotten.

**New: phone conveniences**

- **After a restart, a quiet "Hey Jarvis is off - tap to turn it back on"
  notice**, if listening was on before. Nothing opens the microphone by
  itself.
- **Three Quick Settings tiles you choose:** a focus session, a 10-minute
  timer, Brief me, Stop everything, or play/pause on the PC. Never Approve or
  Deny. Held while the connection catches up. Stop everything works even
  while the app is locked, like the PC's hotkey.
- **Notes for Android 17:** Jarvis's voice has its own volume slider, and
  Floating Jarvis may work as an app bubble (touch and hold the icon).
- **Install notes for 2027:** Google will require extra steps to install
  unverified apps by tapping the file; installing from the PC with adb stays
  allowed (docs/INSTALL.md).

**New: better voice (each off until measured on your PC)**

- **An optional second "hey Jarvis" check:** two detectors must agree before
  Jarvis wakes, for fewer false wake-ups. Off until you choose it, in both
  apps.
- **A newer speech detector (Silero VAD v6)** you can switch to after
  measuring it on your PC; today's stays the default.
- **A third voice-ID model (WeSpeaker ResNet221)** is ready but cannot be
  chosen until it is measured on your PC - in a first test it let other
  voices through more often than the one used today.

**New: Today cards**

- **Your own words on a Today section** in both apps (above Coming up), at a
  time and on the days you choose: "show gym bag on my Today page on Mondays
  at 7". Set by saying it or with a small form; no approval card; Delete is
  immediate.
- **The Today section also shows today's briefing** - weather, calendar,
  email and what is still to come - without reading anything new.

**New: photo to reminder**

- **Give Jarvis a screenshot, a picture file or a shared photo** of a flyer or
  ticket, and it suggests a reminder from the date and time it finds. Nothing
  is set up until you tap Add (or "Also on my phone"). The words are read on
  your PC, never by the AI model, and are not kept.
- **You can now say calendar dates:** "remind me on 12 October at 2pm to pay
  the deposit". A slashed date like 5/10 is read month first (May 10).

**New: PC help**

- **Ask "why is my PC slow?", "how full is my disk?", "what's using my graphics
  card?", "how hot is my graphics card?" or "when did my PC last restart?"**
  and get a plain answer at once, without the AI model. Also under Settings ->
  Hardware and models on the PC and Brain -> PC help on the phone. It only
  reads; program names never leave the PC and are not saved. Changing Windows
  settings (Night light, dark mode) is not built yet.

**New: widgets you describe**

- **Say or type what a small widget should show** - "my next 3 reminders and
  a 10-minute timer button" - and Jarvis makes a preview; tap Add to keep it.
  It is built from a fixed menu of five block kinds and eleven sources, never
  code, and plain code on the PC checks it. It shows on the phone's home
  screen (Jarvis widget 1-3) and in the desktop widget window, in place of
  the face. Its buttons are only the Quick Settings tile actions. Delete is
  instant. Email text, saved facts and web pages are never on the menu.

**New: smarter answers**

- **Big tool results (long files, emails, web pages) are shortened to their
  start and end** instead of being dropped, so Jarvis can still answer from
  them. In long answers that use many tools, older tool results are cleared
  to make room; your own words are never cut.
- **If Jarvis says it did something but nothing actually ran,** the answer
  now ends with "(Nothing was actually done - no action ran in this
  answer.)" - and says so aloud on voice.

**New: model tryouts (tools only - nothing switches by itself)**

- **Try other chat models overnight** against Jarvis's own: tools, learning,
  speed and how much fits on the graphics card, with a plain verdict for each
  (`tools/model_tryout/README.md`).
- **Try other memory-search models and re-rankers** with the memory
  self-test. New `JARVIS_MEMORY_EMBED_MODEL` / `JARVIS_MEMORY_RERANK_MODEL`
  switches; the defaults are unchanged.
- **The preflight check warns about a hidden llama.cpp `config.ini`,** and
  docs/MODEL-TOPOLOGY.md has two engine settings to try, with how to measure
  and undo each.

**New: bring in old chats from ChatGPT, Claude or Gemini**

- **Brain -> Memory on the PC: "Bring in chats from ChatGPT, Claude or
  Gemini".** Choose the export file; Jarvis reads it in the background and
  every possible fact waits for your yes, one card at a time. Nothing is
  saved by itself, and nothing leaves the PC.
- **Changed: importing reads only your own messages,** never the other
  assistant's replies - for all three services (Claude and Gemini imports
  used to read both sides).
- **Fixed:** a Google Takeout with Search activity in it no longer treats
  searches as Gemini chats.
- **DeepSeek chats can be brought in too**, and Jarvis reads imported chats
  better: a long chat is read in pieces the model can take in whole (the
  start of a long chat could be cut off before), with the date the chat
  happened and the facts Jarvis already keeps, the same way live learning
  does. Gemini's prompts are put back into conversations instead of being
  read one line at a time, without the "Prompted" in front, and "Gave
  feedback" lines are no longer taken as things you said. Claude's hidden
  reasoning and tool output are never read. If the AI model stops answering
  partway, the import pauses and nothing is lost.

**New: desktop polish**

- **Brain, Settings, Faces and the HUD reopen where you left them,** at the
  same size, and maximised if they were. App lock still asks Windows Hello
  before the HUD shows. A window whose screen was unplugged opens centred.
- **While Jarvis is clicking or typing on your screen,** the widget shows
  "Jarvis is working on your screen", a timer and a Stop button - the same
  as the Stop everything key.

**New: talk-to-type on the PC**

- **Hold Alt+Shift+T, speak, let go** - Jarvis types what you said into the
  program in front. Off by default; turning it on shows one approval card,
  turning it off is immediate. The voice check still comes first.
- **It never types into a password box, while Jarvis is locked, or into a
  window you switched to.** Your clipboard is put back afterwards, and the
  words stay out of Windows' clipboard history. The words are not kept.

**Fixed**

- **Desktop security update.** The desktop app's framework (Tauri) goes from
  2.11.5 to 2.11.6, which closes a published hole (GHSA-w28w-mhc8-qvjv) where
  one window of an app could read data queued for another window. Jarvis has
  several windows and streams chat answers that way, so it was affected.
- **Speech and memory-search models no longer report to Microsoft.** The
  library that runs them (ONNX Runtime) has its own usage reports switched on
  by default. Jarvis now switches them off before any model loads. One copy
  inside the speech engine can't be reached this way; Windows' own "Send
  optional diagnostic data" switch covers that one (docs/ARCHITECTURE.md §4).
- **A fact you forget no longer comes back by itself.** Jarvis re-reads the
  whole chat when it learns, so about a minute after you pressed Forget (or
  Erase), the same sentence could be saved again without asking. Now nothing
  is learned again from the lines it had already read in that chat, and if
  you say a forgotten fact again later, it waits for your yes.

**Faster**

- **A faster first answer after waking, and after a pause.** Jarvis now
  reads its rules and tool list into the model ahead of time - a one-word
  warm-up whose answer is thrown away and never recorded. It never loads the
  model by itself, never runs while you are asking something, and gives way
  the moment you do. To switch it off: `warm_prefix = false` under `[power]`
  in `jarvis-framework.toml`.
- **Jarvis speaks sooner.** Speech-to-text and the voice now use 4 processor
  threads instead of 2 on a PC with cores to spare (2 on a small one), which
  measured about 0.3 s sooner to the first sound. Your own `stt_threads` /
  `tts_threads` setting still wins.
- **The model's settings file explains the real memory check.** The notes in
  `backend/jarvis-primary.Modelfile` were out of date about flash attention.
  They now give the one PowerShell line that shows whether the whole model is
  on the graphics card ("offloaded 37/37").

**Smaller fixes**

- **The model tool test is fair to other models.** A model that loads with
  too short a conversation is skipped with a plain message saying how to fix
  it, `--repeat` saves the worst of several runs, and a model maker's own
  settings can be tried (`tools/tool_eval/README.md`).
- **The smartwatch setting says a ringing alarm may stay on the phone.**
  Watches often skip notifications that keep going until you stop them.

## 0.2.0 - 26 September 2026

The first numbered version. It gathers the work of the last few days.

**New things Jarvis can do**

- **Timers, alarms, reminders and to-do lists**, set by saying or typing
  them, answered without the AI model so they work even when it is busy or
  asleep. Plain repeating reminders and alarms need no approval card.
  "What did I miss?" sums up what went off while you were away.
- **Morning briefing**: today's calendar, new emails (how many, and from
  whom - or only how many, if you prefer), and what is coming up.
- **"Tell me when ..."**: an email from a named sender, or a device at home
  changing (the washing machine finishing). One approval card to set it up;
  a match only notifies you - urgent ones keep ringing on the phone until
  you look.
- **"Folders Jarvis may look in"**: add a folder on the PC (one approval
  card) and ask about the files in it - find them by name, search your notes,
  read PDF, Word, Excel and PowerPoint files a part at a time. "Bring in a
  Notion export" unzips your Notion export into one of those folders. What
  Jarvis reads there is never saved as a fact about you.
- **Instant "tell me when" for email**, and **"tell me if Alex hasn't
  replied by Friday"**.
- **Sending email**: one approval card per email, showing the exact
  recipients, subject and whole text. Never an "always allow".
- **Web search** with five providers to choose from (SearXNG on your own PC
  by default, DuckDuckGo, Exa, Tavily, Brave).
- **Google Calendar**, read-only, through its private link, set on the PC.
- **Focus sessions** on the PC: a timer plus Quiet, a spoken nudge when a
  distraction comes to the front, and a report at the end. Nothing leaves
  the PC, and what was on screen is never stored.
- **Stop everything**: Alt+Shift+X on the desktop, or the button on the
  phone, halts whatever Jarvis is doing at once.
- **A live check of the whole setup** (`selftest.py --preflight`): every
  real connection tested end to end, "N pass, N fail, N warn".
- **"What asks first"**, a page in both apps listing every action and
  whether it asks you, with switches to make things stricter.
- **Lights, plugs and fans without a card** - a setting, off by default.
  Locks, doors, alarms and covers always ask.
- **Memory**: Jarvis learns facts from your own words automatically, lists
  each one with Forget and "Erase the words", and still asks about
  sensitive topics. Chat history is kept on the PC, encrypted, with a switch
  to turn it off. "Who is my sister?" now works.
- **Voice**: "Hey Jarvis" on the PC and the phone, spoken-style answers that
  start at the first comma, interrupting by saying "stop", and a switch for
  the "I heard you" sound (off by default).
- **Warm or plain manner**, a setting in both apps.

**Safer**

- Both apps accept a Jarvis address on your own networks only (this PC, the
  home network, Tailscale, NordVPN Meshnet). A public tunnel is refused.
- The PC itself asks Windows Hello before a risky approval from the PC, and
  a risky approval needs a screen lock on the phone or Windows Hello on the
  PC.
- Plain `http://` to Home Assistant or the calendar only inside your own
  networks.
- Writing notes after Jarvis has read outside text (an email, a web page)
  asks first.
- App lock hides the approval widget's details on the PC, and blocks
  screenshots on the phone.
- Reading email now checks the mail server's certificate, as sending
  always did (it encrypted, but to whoever answered).

**Fixed**

- "What did I miss?" no longer lists every routine "tell me when" look as
  something that went off.
- A "tell me when" whose end date passed while the PC was asleep (or while
  it was paused) now simply ends, instead of looking one more time.
- On the two days a year the clocks change, the briefing's calendar covers
  the whole day, midnight to midnight.
- The "tell me when" approval card no longer ends by saying it sends
  nothing anywhere, which contradicted its own "How" line.
- Many smaller fixes from the bug audits of 19, 24 and 26 September
  (`docs/BUG-AUDIT-2026-09-26-*.md`).

**Packaging**

- One version number (0.2.0) for the desktop app, the phone app and the
  backend. Both About boxes show it, the maker (darknight11ish), the licence
  and a way to read the third-party notices.
- Complete third-party notices for the desktop (`THIRD-PARTY-NOTICES.txt`,
  regenerated by `tools/gen_notices.py`) and a new list inside the phone app.
- Phone and desktop downloads are published only from `main` and the
  working branch; shorter, plainer release notes with a checksum.

