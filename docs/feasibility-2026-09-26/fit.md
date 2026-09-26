# Feasibility audit - the Fit reviewer (2026-09-26)

**My question:** does each idea plug into how Jarvis is already built, or
fight it? What must come first? Does it copy or clash with something Jarvis
already has?

Read-only. Everything I say about Jarvis's code I checked in the file and
cite as `path:line` (paths from the repo root, `/home/user/Epic-Jarvis`).
Where I did not check, I say "not checked". Research-report claims I did not
re-check are marked "(per <report>)".

## What "fits" means here - the six things every idea must plug into

A plain-words key, because the table leans on these names:

1. **The gate and its cards** (`plan()` -> `describe()` -> a person ->
   `run()`), one mechanism for everything that acts or leaves the PC
   (`docs/ARCHITECTURE.md:149-176`). A feature with its own approval flow is
   "the design is wrong" (`:151-153`).
2. **The one scheduler** (`backend/jarvis_schedule.py:313-341`,
   `register_kind`). Anything that happens at a time is a *kind* of job on
   it, never its own timer thread (`docs/ARCHITECTURE.md:1542-1555`). A new
   kind that repeats asks with one card by default unless it is declared
   `plain_repeat` (`:1547-1550`).
3. **"Tell me when"** (`backend/jarvis_tellme.py`). Today it has exactly two
   sources, `email` and `home` (`backend/jarvis_tellme.py:295-340`). New
   "tell me when" ideas are new *sources* of this one kind.
4. **Offers** (`backend/jarvis_backoff.py`). Anything Jarvis offers
   unasked must be declared in `OFFERS` (`:163-170`) with what it asks for,
   and only two kinds of ask exist today (`MAY_ASK`, `:154-159`). At most
   three offers waiting (`docs/ARCHITECTURE.md:1379-1386`).
5. **"What Jarvis can reach"** (`backend/jarvis_reach.py`, labels at
   `:88-110`). Every new way out of the PC needs a row there and in the
   egress table (`docs/ARCHITECTURE.md:419-431`).
6. **Both apps**, with a written reason in `docs/ARCHITECTURE.md` §8
   "One-sided on purpose" (`:1086-1129`) for anything on one side only. Any
   phone change costs a ~15-minute CI round trip (CLAUDE.md, "How the
   Android apps get built").

Also relevant, checked:
- The backend has **23 model tools today** (`backend/jarvis_agent.py:643-949`,
  counted by `grep '^    "[a-z_]*": Tool('`). Roughly 15 ideas below add
  more. That is why the short tool list (I06) must come first.
- **Three modules already on the owner's PC, not in this repo, overlap ideas
  here:** `jarvis_undo` (the undo shelf, `/api/undo`, `/api/undo/revert`),
  `jarvis_ledger` (`/api/ledger`, "Audit chain") and `jarvis_watch` (the
  GitHub watchlist, `/api/watch`). Their shape is "unverified from here"
  (`docs/ARCHITECTURE.md:1491-1498`; `docs/JARVIS-API.md:1042-1043,1202-1204`;
  `jarvis-client/app/src/main/java/com/jarvis/client/net/Watch.kt:13-30`).
  Nothing that extends them can be designed until someone reads those files
  on the owner's PC.
- **Memory ideas 1-4 (I31-I34) are merged now.** `git merge-base
  --is-ancestor` says all five commits (`9abdd68`, `c33b5f0`, `d2d8831`,
  `eee9b03`, `a1b133e`) are in HEAD (`1381e6a`, "Merge branch
  'worktree-agent-a4d69393e5376ccb0'"). The master list says "not merged";
  that is out of date (section 3).

## 1. The verdict table

Verdicts: **build** (fits, and nothing it depends on is missing),
**build later** (fits, but something must come first, or the second card),
**don't build** (fights the design, or copies something already there),
**no objection** (already done, or nothing to review from my side).

| id | verdict | reason (fit) | guardrails / cost numbers |
|---|---|---|---|
| I01 | build | The chat code already calls Ollama's `/api/show` for the context length (`backend/jarvis_agent.py:1974`), and the desktop already reads `/api/show`'s `capabilities` list for pictures (`jarvis-desktop/src-tauri/src/vision.rs:78-90`). Add a "tools" check at the same call. Do it FIRST: I06 and I07 assume tools work. | Fail closed: unknown capability = say "cannot tell", do not send tools. Cache with the existing `_CTX_CACHE`. |
| I02 | build | Two Ollamas: the second is started by Jarvis through `jarvis_child_env` (allowlisted environment, `backend/jarvis_child_env.py:1-30`) so the setting is added there; the everyday one is started by the owner, so it is one more item in the existing one-line PowerShell pattern (Hardware screen). Add a preflight check. | Must not break `/api/models/install` (test the install path, as ENG says). Preflight WARN if unset. |
| I03 | build | Numbers only, added to the timings Jarvis already records (`speed-record.patch`, `jarvis_speed.py`; not checked in detail). No new surface needed beyond preflight. | Counts only, never prompt text. |
| I04 | build | Changes the ONE existing retry for a broken tool call (asserted by `backend/test_injection_cases.py:18-19`, "gets exactly one retry"), it does not add a second path. The chat posts to Ollama's OpenAI-style endpoint (`backend/jarvis-primary.Modelfile:10-13`); whether that endpoint accepts a schema-constrained answer in the owner's Ollama version is **not checked** - if not, the retry must use the native `/api/chat` `format` (the route ARCHITECTURE §11 chose, `docs/ARCHITECTURE.md:1515`). | Retry still goes through schema check and the gate; still exactly one retry; the existing test must stay green. |
| I05 | build | `tools/tool_eval/` (`ollama_tool_eval.py`, `jarvis_tool_cases.py`) already exists; add cases there. Make it the ONE harness for I95 and I133 too (see objections). | PC only; no CI model. |
| I06 | build | 23 tools now (`backend/jarvis_agent.py:643-949`), ~15 more proposed below. Must land before I07 and before any idea that adds a tool (I39, I40, I45, I47, I51, I53, I54, I66, I76, I91...). The "more tools" tool must still respect `[tools].enabled` (what `jarvis_reach` reports, `docs/ARCHITECTURE.md:465-471`) - lean mode hides tools, it must never enable one. | A tool fetched "on request" is the same tool with the same gate; `NEEDS_A_PERSON` (`jarvis_agent.py:1169-1177`) unchanged; skill discovery counts tool names (`jarvis_skill_discovery.py:5-12`) and must not count the "more tools" step as a routine step. |
| I07 | build | Owner chose. A draft exists and is **stdio only** (`docs/designs/mcp-draft-2026-09-23/jarvis_mcp.py:238-240` refuses any other transport). So HA's and Logseq's HTTP MCP servers (I77, I52 later) do not fit it as written - owner must decide what "local" means (master list note 5). The draft carries its own inherited-environment list (`jarvis_mcp.py:164`) written before `jarvis_child_env.py`; unify on `jarvis_child_env` so a server never gets the pairing token. Every server needs a `jarvis_reach` row. Depends on I01, I06. | Card to start each server; pinned versions; read-only tools first; results are outside text through the existing `_TurnWatch` (`jarvis_agent.py:2659-2684`); stop on Stop everything. |
| I08 | build later | One Modelfile line; measure first because of the open slowdown bug (per ENG). 12 GB card first. | Cost claim 1.5-2x faster, risk 10x slower (per ENG, not checked). Revert = one line. |
| I09 | build | A measurement, not a switch; fits the Hardware screen's existing Measure (`/api/hardware/measure`, `docs/ARCHITECTURE.md:1279-1292`). Each model is a download through the existing install card. | IQ4_XS frees ~0.6 GiB (per ENG). No default changes without the owner choosing. |
| I10 | build later | The second card already has separate "Longer conversations" and "Pictures" switches, each with its own model (`backend/jarvis_second_card.py:214-222`). One model for both is a change to that table, not a new system. Whether `lane_for()` handles two features naming the same model: **not checked**. Waits for the card (CLAUDE.md line 68). | Qwen 3.5 9B on 12 GB (per ENG/VV); must be measured with the card in. |
| I11 | build later | Fights the core of `jarvis_ui_control.py`: it clicks *named* controls from the accessibility tree and, before each step, re-checks it is "still the same control it was at plan time" (`backend/jarvis_ui_control.py:1-31`). A pixel pointer has no name to re-check. Only after I27 proves the pointer accurate, and only with a re-check (fresh screenshot, same crop) before the click. | Card shows the crop; one plan, one card, stop on any change; 12 GB card. |
| I12 | build | Real bug-shaped gap: the desktop keeps only the first `nvidia-smi` line (`jarvis-desktop/src-tauri/src/commands.rs:2617`). The backend's hardware code already enumerates cards (`backend/jarvis_hardware.py:22`, via `jarvis_compute.query_cards`; per-card fields not checked). Both apps' Hardware screens and the widget. | nvidia-smi `--query-gpu` is local; no egress. |
| I13 | build later | Fits the existing "one PowerShell line the owner pastes" pattern (desktop-only Copy, `docs/ARCHITECTURE.md:1113`). Jarvis never elevated - matches the rejected list. 2060 part waits for the card. | Jarvis only measures and prints; the owner runs the admin line. |
| I14 | build | Owner chose. Text from a picture is already an outside-text source (`picture_caption` provenance, `docs/ARCHITECTURE.md:186-190`; `docs/ARCHITECTURE.md:846-847`). OCR output takes the same tag. Both apps send pictures to the PC already. | Tainted turn; never learned; on the processor. |
| I15 | build | Owner chose. Replaces the last model of `jarvis_wakeword.py` and the phone's spotter (`jarvis-client/.../voice/WakeSpotter.kt`), both on ONNX Runtime (`backend/requirements.txt` `onnxruntime` line). The shared wake test bank (`tools/gen_wakebank.py`) must be regenerated. | Re-measure false wakes on real speech (still unmeasured, `docs/ARCHITECTURE.md:1454-1459`). |
| I16 | build | Owner chose. A third engine inside `jarvis_voices.py` beside ZipVoice and F5 (`docs/ARCHITECTURE.md:1513`, "Custom voices"). It needs sherpa-onnx 1.12.24 or newer (per VV), but `backend/requirements.txt` pins no version for `sherpa-onnx` - add a floor. | Same consent card as today's custom voices; the "sounds like the owner" refusal stays. |
| I17 | build later | A second-card feature, competing with I10 and I24 for the same 12 GB. | Measure with the card in. |
| I18 | build later | Fits the voice settings pattern (off by default). Needs name lists: HA device names (exist in `jarvis_home`) and contacts (I54, not built). | Measured first; known ~20% empty/invented output (per VV). |
| I19 | build later | The PC mic is already open all the time when hands-free is on (`docs/ARCHITECTURE.md:1143`, "the desktop's listener is always listening"), so a sound classifier can ride that stream; it would be a third `tellme` source ("sound"). Low priority. | Card to turn on; no audio kept; "not a safety device". |
| I20 | build later | Only if I10's model is weak at documents. Output is outside text like I14. | 12 GB card. |
| I21 | build later | Must sit after the voice check so its measured limits hold (per VV). Small. | Kept only if word errors drop. |
| I22 | build later | The desktop's recording trigger is loudness, and Silero on the PC then decides (`jarvis-desktop/src-tauri/src/voice.rs:59-66`), so Silero is already Jarvis's VAD - this moves a VAD to the two front ends too. Same audio front end as I15: do one measured round, not two. | Not speech-to-text, so the phone rule holds; TEN VAD licence has extra terms (per VV). |
| I23 | build later | Only if the owner's own numbers show others getting in. New thresholds in the existing voice check. | Own measured limits. |
| I24 | build later | Replaces F5 (the existing second-card voice, `backend/jarvis_f5_worker.py`), does not add to it. | 12 GB card; competes with long-conversation lane. |
| I25 | don't build | Research says no local detector is reliable and none catches a replay (per VV). Adds a model on every hands-free turn for no dependable signal. I26 is the real fix. | - |
| I26 | build later | Fits the existing "Only trust the talk button" hands-free setting (CLAUDE.md, 2026-09-24). Owner's call. Must never become a way to approve by voice (`docs/ARCHITECTURE.md:412-415`). | Words shown, never spoken. |
| I27 | build later | Acts on nothing, so no card. Needs a picture model (second card's Pictures switch). Should come before I11. | 12 GB card. |
| I28 | build | The setting exists but no app shows it: `tts_speed` read at `backend/jarvis_speech.py:1818` and `backend/jarvis_voices.py:251-252`; no hit in either app's source. Add to both apps' voice settings. | No card (shows/trusts nothing more). |
| I29 | build later | A second-card feature switch like the others (`jarvis_second_card.py:214`), with its card; the long-conversation model must step aside (per R2-PER). Large new dependency (stable-diffusion.cpp). | 12 GB card; "refuse face swaps of real people". |
| I30 | don't build | Mostly fun; a large download and GPU time for a focus loop or alarm sound. Poor value for the upkeep. | - |
| I31 | no objection | Merged (commit `9abdd68` in HEAD). | fastembed downloads its re-ranker on first use (`backend/requirements.txt`, fastembed line) - Security may want that pinned. |
| I32 | no objection | Merged (`c33b5f0`). | - |
| I33 | no objection | Merged (`d2d8831`). | - |
| I34 | no objection | Merged (`eee9b03`). | - |
| I35 | build later | After I32's self-test numbers say recall needs it. "Erase the words" deletes the fact's word-search row and meaning vector (`docs/JARVIS-API.md:1216`); hints stored in the index must be deleted by the same erase, or Erase breaks its promise. | Hints never shown, never sent to the model. |
| I36 | build | Do NOT write a second date parser: `jarvis_past.py` already turns "in June", "last year", "back in 2025" into a time window with no model (`backend/jarvis_past.py:19-25`). Reuse it for the boost. | Re-orders only. |
| I37 | build | Owner chose, after I31-I34 (now merged). A kind on the one scheduler (`register_kind` names the tidy as a planned kind, `jarvis_schedule.py:323-326`). Today the offer only records a wish (`jarvis_backoff.py:164-166`; `rebuilt/jarvis_sleep.py`); the tidy needs its offer re-declared. Its cards should be memory review items in the existing review pane (`/api/memory/pending`, `docs/ARCHITECTURE.md:1213-1218`), not a new card type. "5 cards a night" must be squared with the back-off's "at most three offers waiting". | Never changes memory by itself (CLAUDE.md line 328). |
| I38 | build later | Owner decided it waits (CLAUDE.md line 329-330). It also collides with `jarvis_past.py`, which already routes "what did I say / tell you ..." to MEMORY as of that date (`backend/jarvis_past.py:21-23`). One router must decide which store answers. | Changes ARCHITECTURE §5's "history is not memory" (`docs/ARCHITECTURE.md:836-838`). |
| I39 | build | Fits as a read tool. Must reuse `file_read`'s refusal list (`backend/jarvis_agent.py:207-229`) so protected folders' names are not listed either. Needs ONE list of "folders the owner allows", shared with I40, I41, I45, I66 and I120 - not five. `es.exe` first; the MCP route only after I07. | Local model only; outside text; never Everything's network server. |
| I40 | build | Owner chose. Must NOT use the name `documents` in `memory.db`: that table is "read by two code paths, created by none", and OpenJarvis's indexer makes one with that exact name (`docs/ARCHITECTURE.md:1477-1481`). Its own file. | Only MarkItDown's document extras (its audio part sends to Google, per R3-KNOW). Outside text. |
| I41 | build later | After I40. Reuses what memory already ships: fastembed, sqlite-vec and the re-ranker (`backend/requirements.txt`). Own file, never memory. | Nothing indexed by default; `.ssh`, `.env`, browser profiles always out (same list as I39). |
| I42 | build | Extends "Used in this answer", which both apps already have for memory (`/api/memory/used`, `docs/ARCHITECTURE.md:883-885`; desktop `memory-used.js`), and the tool loop already knows what was read this turn (`_TurnWatch.read`, `jarvis_agent.py:2665-2668`). The quote check is shared with I44 and I72. | Built from what tools returned, never from the model's claim. |
| I43 | build later | Clean fit: the existing `append_obsidian_daily` action and the fast path. Low priority. | Jarvis never fetches the page. |
| I44 | build later | The wiki builder is "not run against a real model yet" (`docs/ARCHITECTURE.md:1255`). Measure what exists first. Fixes go through the existing `wiki_update` card. | Second card or big model. |
| I45 | build later | New dependency (DuckDB) in a child process: start it through `jarvis_child_env` so it inherits nothing secret. | One file the owner named; read-only; row cap; query shown. |
| I46 | build later | Long CPU job next to live voice: must use the existing task controls (Stop, Pause, Stop everything - `docs/ARCHITECTURE.md:218-227`) and never run while a voice turn is live. New binary dependency (ffmpeg). Shares code with voice memos. | Outside text; never learned; never a live meeting. |
| I47 | build later | `file_read` refuses browser profile folders on purpose (`backend/jarvis_agent.py:212-214`, added in commit `1ce1dac`). Bookmarks need their own narrow reader of one file, never a loosened `file_read`. | Titles are outside text; nothing kept. |
| I48 | don't build | Same clash as I47, deeper (history is far more private), and it copies the phone-notifications pattern (I73), which is not built yet. Revisit only after I73 is built and audited. | - |
| I49 | build later | A new way out of the PC: a row in `jarvis_reach` and ARCHITECTURE §4. Replaces the briefing's "not available" line (`backend/jarvis_briefing.py:117-118`). Decide together with I67 as ONE "fetch a fixed address on a schedule" lane, not two. | Headlines only; one card per feed. |
| I50 | build later | The "Open in Obsidian" button is trivial and fits. The galaxy layer is desktop-only like the memory graph (`docs/ARCHITECTURE.md:1097`). | - |
| I51 | build later | Fits a real gap: daily-note date formats Jarvis cannot compute are refused today (`docs/ARCHITECTURE.md:1442-1446`). Whether the Obsidian CLI needs the Obsidian app running: not checked. | A fixed list of read commands; never `eval`. |
| I52 | build | The "detect a database graph and say so" half only (S). The dry-run half uses Logseq's HTTP MCP server, which the stdio-only draft refuses (`jarvis_mcp.py:238-240`) - don't build that half unless the owner allows HTTP MCP on 127.0.0.1. | - |
| I53 | build | Owner chose. The first WRITE to the mailbox: today email is read-only (`EXAMINE`, `BODY.PEEK`, "No STORE, COPY, MOVE", `backend/jarvis_tellme.py:55-63`). A new gate action and card words (`jarvis_card_words.TITLES`); the "owner's own accounts" egress row already covers the IMAP host. | Draft only, never sent; open question: card after outside text only, or always. |
| I54 | build later | Desktop-only needs a §8 row. Adds one line to the existing send card (`jarvis_email_send`). | Never learned as facts. |
| I55 | don't build | Only useful with a non-Google calendar; the owner's calendar is Google's private link, read-only (CLAUDE.md 2026-09-25). Revisit if that changes. | - |
| I56 | build later | Needs I14 (OCR) and I40. A note write after outside text already raises a card (`docs/ARCHITECTURE.md:184-195`) - no new rule needed. | Outside text. |
| I57 | build later | A new scheduler kind: "a new kind asks by default" (`docs/ARCHITECTURE.md:1547-1550`), so whether review reminders are `plain_repeat` must be decided. Quizzes in the existing temporary chat. Keep FSRS out of any "streak" (see section 3). | Owner-picked notes only. |
| I58 | build | A fixed instruction line placed like the manner line (`docs/ARCHITECTURE.md:940-946`), no new parts. | Local model only when the text is private. |
| I59 | build later | Typed works in the temporary chat already; spoken needs a multilingual speech model on the PC (today's is English only, per R2-PER). | Never on the phone (no phone STT). |
| I60 | build later | Reads through `file_read`; any edit needs a diff card that does not exist yet. | Never edits by itself. |
| I61 | build later | Matches ARCHITECTURE's own test of "approve-all": one decision about a bounded set, every one shown in full, is allowed (`docs/ARCHITECTURE.md:102-110`), and `jarvis_research` and `jarvis_ui_control` already work this way (`backend/jarvis_ui_control.py:33-40`). But ONLY for steps whose exact arguments are known when the card is shown. A step whose arguments come from an earlier step's result must get its own card. Counts against `CARDS_PER_TURN = 5` (`jarvis_agent.py:1560`). After I06. | ≤8 steps, ≤3 risky; risky steps asked again; nothing on a stale link. |
| I62 | build later | Would duplicate **skills**: Jarvis already offers to save a repeated tool chain as a SKILL.md, through the `modify_own_code` card, and running it still asks step by step (`backend/jarvis_skill_discovery.py:1-17`). A "routine" must BE a skill, one concept, one screen. After I61. | Never runs by itself; "Try it" dry run. |
| I63 | build | A new scheduler kind plus a briefing line; fits cleanly. Declare it `plain_repeat` in writing if the weekly check has no card (the report says so too). | Owner's words only. |
| I64 | build later | After I63. Offering re-plans needs a new declared offer kind (`jarvis_backoff.py:163-170`). Stage 3 needs the second card or big model. | Accepting a plan runs nothing. |
| I65 | build later | There is already an undo shelf (`GET /api/undo`, `POST /api/undo/revert`, both apps: `docs/JARVIS-API.md:1042,1202`), served by the owner's `jarvis_undo.py`, which is NOT in this repo and whose shape is unconfirmed (`docs/JARVIS-API.md:1204`). Extend it; do not build a second undo. Read the owner's file first. | Undo only what Jarvis's own tools did. |
| I66 | build | Two new `tellme` sources beside `email` and `home` (`jarvis_tellme.py:295-340`). Calendar reads go through `jarvis_calendar`. A folder must be looked at by the kind's own check (polling), not a new always-on file-watcher thread, to stay on the one scheduler. | Same card, end date, a match only notifies. |
| I67 | build later | New egress lane; decide with I49 (one lane). | One typed address; its own card. |
| I68 | build | Owner chose - but IDLE is a different shape from everything on the scheduler: one long-open connection instead of "a look every 5 minutes, each look through the gate" (`jarvis_tellme.py:36-50,71-81`). The connection must be owned by the tellme kind (closed on the job's end date, on Standby and on Stop everything), and each fetch after the server's nudge still passes the gate as `email_read`. Python 3.12's `imaplib` has no IDLE (per CAP), so a new dependency or hand-written loop. | From line only, PEEK, as today. |
| I69 | build | Same email source, inverse match with a deadline. Tiny inside I68's work. | Notifies only. |
| I70 | build later | Overlaps TWO things: the owner's GitHub watchlist (`jarvis_watch`, `Watch.kt:13-30`, not in repo) and `tellme`. The creativity audit already said "merge, not a second tab" (`docs/creativity-2026-09-25/usefulness.md:211-213,476-479`). Also `github_search` is in `NEEDS_A_PERSON` (`jarvis_agent.py:1170`); a repeated look needs its own read-only action at `auto`. | Read-only token, sent to GitHub only (rule 3). |
| I71 | build later | Second card; the standby clash is real (`jarvis_big_model.py:1328-1337`: "colibri only ever starts for a job"; the second card has a background flag, per R3-ROUT). Depends on I72, I74, I64 existing. | Acts only after a morning card. |
| I72 | build later | Must BE `jarvis_research` + `web_search`, the reference implementation for enumerated searches (`docs/ARCHITECTURE.md:174-176`), not a new module. Quote check shared with I42. | One card with the exact search words; no loop. |
| I73 | build later | Owner chose, queued after the four groups and the security audit (CLAUDE.md line 358-365). New phone-to-PC route; capture is phone-only (needs a §8 row); feeds `tellme` as a source. | As the owner's decision lists. |
| I74 | build later | Summarising "what the owner worked on and decided" means the model reads chat history - the same rule change as I38 (`docs/ARCHITECTURE.md:836-838`, history is "not a source the learner reads from"). Waits on that decision. | Saved after a card. |
| I75 | build | Owner chose. `jarvis_home` has two shapes today: read a state (`plan_states`, `backend/jarvis_home.py:236`) and act (`/api/services`, through `home_control`, which needs a person). `weather.get_forecasts` is a service call that only reads, so it needs a third, tiny shape: an allowlist of exactly that one service, never through `home_control`. Replaces `backend/jarvis_briefing.py:338`. | Tier `auto` like `home_read`; forecast is outside text; `jarvis_reach` HA row updated. |
| I76 | build later | A logbook read beside `plan_states`; fits `home_read`. | Outside text. |
| I77 | don't build | As proposed it relies on HA's MCP server over HTTP, which the stdio-only draft refuses (`jarvis_mcp.py:238-240`), and HA's MCP list has no entity ids (per R3-HOME). Do it later through I78's client instead. | - |
| I78 | build later | New dependency (WebSocket client). The card fits "several devices on one card", but that card allows at most ten devices (`docs/ARCHITECTURE.md:112-119`), so a room with more must be refused or split. | Locks, doors, alarms, covers still alone. |
| I79 | build later | "Which room a request came from" needs to know which device sent it - today every device uses the one pairing token (`docs/ARCHITECTURE.md:256-258`). After I102. | Only ever quieter/narrower. |
| I80 | build later | After I78. | - |
| I81 | build | Docs plus one preflight WARN; no new mechanism. | - |
| I82 | build | Already possible: the `home` source watches ANY one entity for a state (`jarvis_tellme.py:310-336`), so a "person detected" sensor turning `on` works today. Only a phrase in `jarvis_quick` and a word in `STATE_WORDS`. | Labels only; no picture. |
| I83 | build later | Needs a picture path PC -> app that never touches disk, and the local picture model (second card). | Own card; never face recognition. |
| I84 | build later | After I12. | - |
| I85 | build later | Reuse "What did I miss?" (`docs/ARCHITECTURE.md:1374-1378`) for the summary. The one offered card is an offer: new `OFFERS` kind (`jarvis_backoff.py:163`). | Nothing switches by itself. |
| I86 | build later | Briefing lines from `home_read`; fits. | Car locks/covers alone. |
| I87 | build later | Named lists already live in the scheduler (`docs/ARCHITECTURE.md:1371-1373`): mirror them, never a second shopping list. Writing to HA is `home_control` (needs a person) unless a second "without a card" setting like the lights one (`docs/ARCHITECTURE.md:121-136`). | Owner's choice of card-per-add or one setting. |
| I88 | don't build | An HA automation Jarvis helps create then acts by itself for ever, with no card - the "watcher that acts when it matches" on the reports' own not-for-Jarvis list, just hosted in HA. `NEVER_ASKS` also forbids an offer to "turn on a setting that ... trusts more" (`jarvis_backoff.py:142-151`). If ever wanted: show the owner the YAML to paste into HA themselves. | - |
| I89 | build later | With the PC off, the backend is off - and the phone today talks ONLY to the backend. So either the phone sends the wake packet itself on home Wi-Fi (no key, fits), or it holds an HA token (keys are entered on the PC only today, `docs/ARCHITECTURE.md:1117`). Recommend home-Wi-Fi only. | Never a router port-forward. |
| I90 | don't build | The PC is Jarvis's only clock: "the phone hears of a job going off only while it is connected" (`docs/ARCHITECTURE.md:1315-1316`). A sleeping PC breaks every kind on the scheduler, and "standby" already means something else (model unloaded). I93 covers "ring with the PC off". Admin prompt unverified (per R3-HOME). | - |
| I91 | build | The "Lights, plugs and fans without a card" pattern (`backend/jarvis_asks_first.py`; `docs/ARCHITECTURE.md:121-136`) fits exactly: off by default, one card to turn on. Both apps. | Never after outside text. |
| I92 | build later | Listing is a new egress row; each update fits the existing Windows Hello at the backend (`jarvis_owner_check.py`). | Never "update all". |
| I93 | build | Owner chose. Phone-only by nature: §8 row. | Warn about two alarms. |
| I94 | build later | Phone-only (§8 row); the owner's tap is the send. Low priority. | Never reads SMS. |
| I95 | build | Extends what exists: AgentDojo attacks are already in `backend/agentdojo_injections.json` and run against a scripted fake model in `backend/test_injection_cases.py:1-25`. Add the real-model run to `tools/tool_eval` (one harness with I05). Must come before I104-I108. | PC only. |
| I96 | build | Restore fits card + Windows Hello at the backend (`jarvis_owner_check.py`). New dependency (`age`). Must say plainly that Erase cannot reach old backups. | Not cloud; key handling is Security's call. |
| I97 | build | Adds WARN lines to the existing live preflight (`selftest.py --preflight`, `docs/ARCHITECTURE.md:1430-1438`). | Read-only, never fixes. |
| I98 | build | Belongs in the desktop's `sidecar.rs`, which already tracks the backend process exiting (`jarvis-desktop/src-tauri/src/sidecar.rs:147-185`) - not a Windows service (rejected by R2-TRU). | Max 3 restarts in 10 min. |
| I99 | build | Scrub with the existing `jarvis_scrub.py` before any sharing. | Newest 10, on the PC. |
| I100 | build later | Owner's call; dumps can hold the token. | - |
| I101 | build later | After I96 exists (a cleared TPM would lose history). | - |
| I102 | build | Owner chose. Foundation for I103, I112, I79 and I119's pairing step. Replaces the single token (`docs/ARCHITECTURE.md:256-258`) and changes how `jarvis_owner_check` places a request. | Large; its own audit. |
| I103 | build | Owner chose, inside I102 (`docs/APPROVAL-GAP-DESIGN.md`). | - |
| I104 | build later | Half exists: cards already say which values "came from what Jarvis read, not from you" (`jarvis_agent.py:2615-2684`). The new part is per-tool sensitive-argument names that make the card heavy. After I95. | Stricter only. |
| I105 | build later | Only if I95 shows fewer attacker cards (the report's own condition). | - |
| I106 | build later | Doubles the model calls before a card after outside text (answer time). After I95. | Label only. |
| I107 | build later | After I95 (may hurt reading). | - |
| I108 | build later | Plug into the existing planted-instruction check (`jarvis_intake.injection_flags`, `jarvis_agent.py:2300`, shown on the card at `:2676-2678`) as a second signal, never a new warning line. After I95. | Warning only; licence unchecked. |
| I109 | build later | A ledger already exists: the Brain's Trust tab reads `/api/ledger` (owner's `jarvis_ledger.py`, `docs/ARCHITECTURE.md:1491-1498`) and the gate writes `gate.approved` lines to the audit log (`jarvis_skill_discovery.py:24-31`). Count from those, not a third store. | Counts only; never changes a tier. |
| I110 | build | All Approve surfaces: the Jarvis bar, the widget (not under App lock), the phone card and its swipe (`docs/ARCHITECTURE.md:396-402`). One shared case table like the card words. | Stricter only. |
| I111 | build later | `backend/requirements.txt` pins nothing today (only `ddgs>=9.16.0`), so hash-pinning is a real change to how the owner installs; builds on `apply-patches.ps1`'s backup/`-Revert` (per R2-TRU). | Staged; one command back. |
| I112 | build later | After I102. | - |
| I113 | build | Notification half done in the unmerged worktree (`e372eb7`, not in HEAD); lock-screen widget half is small. Merge the worktree first. | - |
| I114 | build | Small, both apps. | - |
| I115 | build | Reuse the secret patterns Jarvis already has (`jarvis_sensitive.py`, `jarvis_mail_mask.py`) inside `jarvis_chat_log` before encryption; do not write a third list. | Model still sees it this turn, locally. |
| I116 | build | Serve the list from `jarvis_quick` on the PC so both apps show the same words (the shared-cases pattern, `tools/gen_*_cases.py`). | Fills the box, never sends. |
| I117 | build later | Would be the fourth place showing "what's next" (briefing, Coming up, "What did I miss?"). Only as a view over the briefing's builder, which the report proposes. | Never an Approve. |
| I118 | build later | After I117; writes through `append_obsidian_daily`. | Owner's words only. |
| I119 | build later | The desktop already has an onboarding window (`jarvis-desktop/src/onboarding.html`, `src-tauri/capabilities/onboarding.json`): evolve it. Its "pair your phone (QR)" step needs I102. | - |
| I120 | build later | Fits the existing "shared" tag (`docs/ARCHITECTURE.md:186-190`); documents need I40. | Waits for Enter. |
| I121 | build later | New upload route; after I40. | "shared" tag. |
| I122 | build | Focus already goes Quiet and back (`backend/jarvis_focus.py:81-85`). Reading Windows' Focus state: API not checked. | Read only; never starts Windows Focus. |
| I123 | build later | Phone permission; ties to focus. | Alarms/urgent through. |
| I124 | build later | Focus already counts down in both apps; timers get the same. Android 16 Live Update on the phone. | - |
| I125 | build | Small; no `shortcuts.xml` today (per master list). | Meets App lock. |
| I126 | build later | Widget work; counts only. | Off the lock screen. |
| I127 | build | Small checks in both test suites. | - |
| I128 | don't build | Large packaging change to the installer and updater (`update.rs`, `desktop-release.yml`) for a beginner-maintained app. | - |
| I129 | build | The rules live in TWO places held equal by a test: the Modelfile's `SYSTEM` (`backend/jarvis-primary.Modelfile:160-167`) and `LANE_SYSTEM` (`jarvis_agent.py:3317-3340`). Change both, and fix the flat allowance `_TEMPLATE_TOKENS = 300` (`jarvis_agent.py:2016`, used at `:3000`, `:3509`) in the same change. The owner must re-run `ollama create`, so I134 goes with it. | Outside text cannot change it. |
| I130 | build later | After I133. | - |
| I131 | build | `jarvis_quick` already answers "what can you reach?" without the model (`backend/jarvis_quick.py:41-44,752-754`). Add identity questions there. | Fixed text. |
| I132 | build | Uses the existing "Used in this answer" data (`/api/memory/used`). | - |
| I133 | build | One harness with I05 and I95 (three reports propose three scripts). | PC only. |
| I134 | build | Pairs with I129; a preflight check (`selftest.py --preflight`). | WARN only. |
| I135 | build | The card words are one table already (`jarvis_card_words.TITLES`, `tools/gen_card_words_cases.py`); the test reads it. | - |
| I136 | build later | Fold into I138. The phone hard-codes two manners (`jarvis-client/.../net/Manner.kt:26`, and returns null for anything else, `:84`), while the desktop draws the PC's list (`jarvis-desktop/src/manner-settings.js:86-104`). A third preset is a phone release. | No card. |
| I137 | build later | After I133 shows no harm. | Never on cards. |
| I138 | build later | Grows `jarvis_manner.py` (`MANNERS = (WARM, PLAIN)`, `:44-47`). Same phone hard-coding as I136. After I145. | One style line, capped by a test. |
| I139 | build later | With I138. | - |
| I140 | build later | Reuse automatic learning's live-turn checks (`jarvis_auto_learn.py:554-771`: source, taint, pasted), not a copy. After I138. | Undo in Brain. |
| I141 | build later | Needs a new declared offer kind (`jarvis_backoff.py:163-170`). | - |
| I142 | build later | Ordinary memory with a label; whether the store has a label field: not checked. | Forget/Erase as usual. |
| I143 | build later | After I138-I142. Reuse `check_instruction` (`jarvis_auto_learn.py:791`) to refuse rule words. | The one place owner text becomes an instruction. |
| I144 | build | Focus state is already known on the PC; one line like the manner line. | Saved setting untouched. |
| I145 | build later | The owner's `jarvis_persona.py` is not in this repo (checked: not in `backend/`). Must be read before I137/I138. | - |
| I146 | build later | The temporary chat exists; little to build. | Temporary chat. |
| I147 | build later | Face code in both apps. | Flash limits. |
| I148 | build later | Same. | Never looks like approval. |
| I149 | don't build | No face with a mouth exists. | - |
| I150 | no objection | Guidance only. | - |
| I151 | build | Reuse the self-harm patterns already in `jarvis_sensitive.py` (`:192`, `:282`) - one list, not a third. "No tools offered" is a hook in `run_local_turn`; the fixed message is words both apps show. | Never contacts anyone; logs nothing. |
| I152 | build | Add words to `_PRIVATE_TERMS` (`backend/rebuilt/jarvis_router.py:70-106`) - a rebuilt file - or with no code at all through the owner's `[privacy] never_leaves_device` list, which the router reads (`:108-151`). Checked: no mood or self-harm word there today. | A backstop; cloud still needs the owner's yes per question. |
| I153 | build later | Prompt wording; after I133. | - |
| I154 | build | A rule in the learner and a skip in the automatic-learning checks. | No mood log. |
| I155 | don't build | Duplicates I133 and needs a 14B judge on the 12 GB card. Revisit only if I133 shows gaps. | - |


**Counts** (155 ids): build 55, build later 85, don't build 10, no objection 5.

## 2. Objections for the other reviewers

Stated so they can be answered.

1. **To Hardware:** I said "build" to I09, I14, I16 and I36 as if the
   processor had room. Voice, the re-ranker (I31, merged) and OCR all run on
   the processor. If you measure that stacking them lengthens the answer
   time, I16 and I14 move to "build later".
2. **To Rules:** I61 (the plan card). I read ARCHITECTURE's own test of
   "approve-all" (`docs/ARCHITECTURE.md:102-110`) as allowing it when every
   step's exact arguments are on the card. CLAUDE.md line 105 says "never ...
   approves in bulk". If you read "in bulk" more strictly than ARCHITECTURE
   does, I61 becomes "don't build", and so does I62.
3. **To Rules / Security:** I07 and the HTTP question. I kept the MCP
   bridge stdio-only because that is what the draft does. If the owner allows
   HTTP on 127.0.0.1 (Logseq), I52's second half fits; HA's MCP over the
   home network (I77) I would still refuse, because it has no entity ids.
4. **To Security:** I68 (instant email). A long-open login to the mailbox
   is a new standing connection. I said "build" because the owner chose it;
   if you find the open connection cannot be tied to Stop everything and
   Standby, it should fall back to the 5-minute look.
5. **To Security:** I82 (someone at the door) - I said it already works.
   If you think a person sensor needs its own rule (for example urgent only
   with a card), say so; the fit is there either way.
6. **To Overwhelm:** I counted 55 "build". Many are small, but I117 (Today),
   I116 (things you can say), I124 (countdown), I125 (shortcuts) and I126
   (widget) are all new places to look. I only objected to I117 as a fourth
   copy; you may want to cut more.
7. **To Overwhelm / Rules:** three ideas add new "without a card" or offer
   kinds: I91 (media), I87 (HA to-do), I85/I64/I141 (offers). Each is a new
   line on "What asks first" or a new `OFFERS` kind. I think each fits the
   pattern; you may want a cap.
8. **To Upkeep:** I136/I138 (presets) need a phone release because the phone
   hard-codes the manner list. Consider making the phone draw the PC's list
   first (like the desktop), so later presets need no CI round trip.
9. **To Upkeep:** I111 (hash-pinned packages). Nothing is pinned today; I
   rate it "build later", but the pinning half may be cheap and worth doing
   before I16, I40, I45 and I07 each add a dependency.
10. **To Devil's advocate:** I82, I91, I28 and I131 are my "cheap wins". If
    you think any is hype, argue the value; the fit is not in doubt.
11. **To everyone:** I65, I70 and I109 cannot be designed from this repo:
    each extends a module that exists only on the owner's PC (`jarvis_undo`,
    `jarvis_watch`, `jarvis_ledger`). Someone must read those files first,
    or we risk building a second undo, a second watchlist and a second
    ledger.
12. **To Hardware:** I10, I17, I24, I29, I71 all want the 12 GB card at
    once. Fit-wise each is a second-card feature switch; which of them get
    the memory is your call.

## 3. Wrong or out of date in the research and the master list

1. **Memory ideas 1-4 are merged, not "in a worktree, not merged".** The
   master list (note 1, and I31-I34's status) says they are unmerged. HEAD
   is `1381e6a` "Merge branch 'worktree-agent-a4d69393e5376ccb0' into
   claude/admiring-ritchie-5urg5h", and `git merge-base --is-ancestor`
   confirms `9abdd68`, `c33b5f0`, `d2d8831`, `eee9b03` and `a1b133e` are all
   in HEAD. So the owner's condition for the overnight tidy ("after 1-4") is
   met in code; only the measuring part is left. (`e372eb7`, the notification
   commit, is still NOT in HEAD - that part of the master list is right; its
   worktree branch holds 13 commits not yet in HEAD.)
2. **The reports' "no streaks" rule versus a feature already built.** R2-PER
   (`docs/CUTTING-EDGE-2026-09-26-round2-personality.md:272`) and R4-GROW
   (`...round4-growth.md:303`) list streaks as not-for-Jarvis. The focus
   report card already has one: `streak_of()` and "Streak: N clean sessions
   in a row." / "The streak starts again ..." (`backend/jarvis_focus.py:652,
   702-704`). Neither report mentions it. Either the rule has an exception
   for focus, or the focus streak should go - the owner's call, not mine.
3. **R2-TRU #8 (the ledger) misses the existing ledger.** It proposes a new
   decision ledger (`docs/CUTTING-EDGE-2026-09-26-round2-trust.md:178-184`)
   and does not mention `/api/ledger` (the Brain's Trust tab, owner's
   `jarvis_ledger.py`) or the audit log's `gate.approved` lines. (grep of
   that report for `ledger`/`audit log` finds only its own proposal.)
4. **CAP #9 (GitHub "tell me when") misses the GitHub watchlist.** No
   mention of `jarvis_watch` or `/api/watch` in the capabilities report
   (grep). The creativity audit had already flagged the naming clash and
   said to merge (`docs/creativity-2026-09-25/usefulness.md:211-213`).
5. **R3-HOME #8 ("tell me when someone is at the door") is sold as new,
   size S.** It already works through the existing `home` source
   (`backend/jarvis_tellme.py:310-336`). To be fair, R3-HOME itself notes
   that tellme "already watches ONE HA entity" (`...round3-home.md:198`); the
   master list still sizes it as a new feature.
6. **CAP #10 and #12 plan HTTP MCP servers the draft refuses.** The draft
   rejects any transport but stdio with an error
   (`docs/designs/mcp-draft-2026-09-23/jarvis_mcp.py:238-240`). The master
   list's note 5 raises the conflict; the evidence is that line.
7. **I104 is described as new; half of it is built.** Cards already list
   values that "came from what Jarvis read, not from you"
   (`backend/jarvis_agent.py:2615-2684`). What R2-TRU adds is the per-tool
   list of which arguments are sensitive.
8. **VV's Pocket TTS needs sherpa-onnx 1.12.24+ (per VV), but
   `backend/requirements.txt` has no version for sherpa-onnx.** Not wrong in
   the report, but the report does not say the requirement must change.
9. **Checked and found right** (so no one re-checks them): the desktop
   reads only the first graphics card (`commands.rs:2617`); the briefing's
   weather line (`jarvis_briefing.py:117-118,338`); `_TEMPLATE_TOKENS = 300`
   (`jarvis_agent.py:2016`, used `:3000`, `:3509`); the owner's decision line
   numbers in CLAUDE.md (343, 347, 351, 353, 356, 358); R3-ROUT's standby
   clash (`jarvis_big_model.py:1328-1337` says colibri only starts for a
   job, with no standby refusal in `sleep()`'s docstring - I did not trace
   `lane_for` in full); `file_read`'s refusal list (`jarvis_agent.py:
   207-224`).

## Build order, from the fit side

1. Merge the open worktree (`e372eb7` and its 12 siblings) so nothing below
   is built on a stale base.
2. I01 -> I02 -> I06 (tool check, cloud lock, short tool list), then I05 +
   I95 + I133 as ONE test harness, then I07.
3. Owner-chosen quick wins that need nothing: I75, I93, I14, I53, I68(+I69).
4. I40 before I39, I41, I56, I120, I121 (one allowed-folders list).
5. I129 with I134; I131, I151, I152, I154.
6. I102 (+I103) before I79, I112, I119.
7. Read the owner's `jarvis_undo`, `jarvis_ledger`, `jarvis_watch`,
   `jarvis_persona` before I65, I109, I70, I137/I138.
8. Second-card items (I08, I10, I17, I24, I27, I29, I71, I83) after the
   card is in and measured.
