# Memory research, 26 September 2026

You asked (2026-09-24): "Cutting-edge memory: research GitHub memory systems, copy the best, then build + audit." This page is the **research step only**. Nothing was built, and no code in Jarvis was changed.

**How it was checked.** I downloaded the current code of 15 memory projects from GitHub (all last updated between November 2025 and 25 September 2026) and read the parts that matter: how they save, update, search and forget. I read Jarvis's own memory code at commit `cd70a75`. Web search was used for dates and benchmark claims. Some things could not be checked; they are listed in section 8.

**A word on numbers.** Every score in this page is **the project's own claim** unless it says otherwise. Nothing was measured on your PC, and nothing new was measured here.

This builds on the earlier memory research (`docs/RESEARCH-2026-09-24.md` §3). Four of that page's ideas are now built: the memory self-test, "Always keep in mind", "who is my sister?" and questions about the past. Four were approved for later and are **still not built**: real "true from" dates, counting repeats, the overnight tidy, and a re-ranker. They come back below, with new evidence.

---

## 1. Summary

1. **Jarvis's memory is still safer than every project checked.** None of them asks you before saving. Most let the AI model rewrite or delete memories by itself. Jarvis does neither.
2. **The field has moved Jarvis's way.** mem0 (the most-used project) stopped letting its model update or delete memories in April 2026. It now only adds, like Jarvis's "retire, never delete".
3. **The best 2026 systems search four ways at once:** words, meaning, people/things, and time. Then a small checking model re-scores the results. Jarvis does the first three. It lacks the checking model and a time signal for ordinary questions.
4. **Best value next: a small re-ranker on the processor** (a "re-ranker" is a small model that re-reads the top results and re-orders them). It runs without the graphics card. Jarvis's existing download tool already includes one (80 MB, Apache-2.0 licence).
5. **Next best: a bigger self-test, "said again" counts, and real "true from" dates.** All three are small or medium, and need no new permission rules.
6. **The overnight tidy is still only an offer.** `jarvis_sleep.py` runs nothing. When it is built, it should only raise cards, as already decided.
7. **Several popular ideas are wrong for Jarvis.** Examples: the model writing its own memory, saving what the *assistant* said, summarising memories, graph-database servers, and data sent to the project makers by default. Section 7 says why.
8. **The benchmark scores cannot be compared with each other.** They use different tests, different AI models (usually big cloud ones) and different scoring. None was run with an 8B model on an 8 GB card.

---

## 2. The ranked list

Ranked by value for the effort. S = small (one module plus tests), M = medium (several files, maybe a line in both apps), L = large.

| # | Idea | Borrowed from (licence) | Size | Expected gain |
|---|---|---|---|---|
| 1 | **Re-ranker:** a small model on the processor re-checks the top ~20 facts before 5 go to the model | Hindsight's default set-up (MIT); the model is `ms-marco-MiniLM-L-6-v2` through fastembed (both Apache-2.0) | S | Finds reworded questions ("boss" for "manager"). Fewer wrong facts on "don't know" questions. **Unmeasured.** |
| 2 | **A bigger self-test:** questions that need two facts, questions about time, and a test of the *learner* (does it propose the right fact?) | LongMemEval's question types (MIT); HaluMem's finding that saving is the weak step | S-M | Every other change can be measured before it ships |
| 3 | **"Said again" counts:** when you repeat something Jarvis knows, record the date instead of throwing it away | Hindsight's "proof count" (MIT); mem0's duplicate check (Apache-2.0) | S | Shows which facts matter; feeds the tidy ("pin this?") and ties in search |
| 4 | **Real "true from" dates**, plus "older news never replaces newer news" | Graphiti (Apache-2.0); mem0's "observation date" rule (Apache-2.0) | M | "When did I move?" and "where did I live in May?" become right, not approximate |
| 5 | **Search hints:** a few extra search words per fact, stored in the index only, never shown and never sent to the model | A-MEM (MIT); MemPalace (MIT) | M | Helps the ~1 in 4 questions that share no words with the fact |
| 6 | **Date-closeness boost:** a question with a date prefers facts from near that date | MemPalace (MIT) | S | Better "what did I do last weekend?" answers |
| 7 | **The overnight tidy, cards only:** likely duplicates, likely contradictions, "is this still true?" | Letta sleep-time agents (Apache-2.0); LangMem's background manager (MIT); Graphiti's duplicate rules | M-L | Memory stays clean without the model changing anything by itself |
| 8 | **Your call: search your own past words** in chat history, only when you ask | MemPalace's "keep the exact words" design (MIT) | M | "What did I say about the boiler in August?" becomes answerable |

---

## 3. Each idea in more detail

### Idea 1. A re-ranker (S)

- **What it is.** Today search makes three lists (words, meaning, people) and merges them with a fixed formula (`rebuilt/jarvis_memory.py:1278`, `:1303`, `:1318`). A re-ranker reads the question and each candidate fact *together*, and scores how well the fact answers it. This is more accurate than the formula, because it reads both side by side.
- **Where from.** Hindsight (MIT) uses exactly this as its default: `cross-encoder/ms-marco-MiniLM-L-6-v2`, run locally (`hindsight_api/config.py:1270`). The same model ships in fastembed 0.8.1 as `Xenova/ms-marco-MiniLM-L-6-v2`: 0.08 GB, Apache-2.0. Jarvis already uses fastembed for meaning search (`rebuilt/jarvis_memory.py:421`). So this needs no new download tool. **I have not checked which fastembed version is on your PC.**
- **Fit with the rules.** It runs on the processor, on the PC, with no network after a one-time download. It only re-orders facts that search already found. It never adds, changes or hides a fact. `k` (5 facts) and both floors stay as they are. It could also add a third floor: drop a candidate the re-ranker scores very low.
- **Gain.** Hindsight ships a re-ranker as its default. MemPalace reports that its re-check step (done by a big model, not a small one) added its last few points (their claim). For Jarvis, it is **unmeasured**. It should be off until the self-test on your PC shows it helps.
- **Risks.** The small model is **English only**, like today's meaning model (`bge-small-en-v1.5`). The multilingual one in fastembed (`jina-reranker-v2-base-multilingual`) is 1.1 GB and licensed CC-BY-NC (non-commercial use only). That fits your non-commercial build, but it is a real licence condition. Speed on your processor is not measured; the estimate is tens of milliseconds for 20 short facts. A slow re-ranker must fall back to today's order, never block a chat.

### Idea 2. A bigger self-test (S-M)

- **What it is.** `backend/eval_memory.py` already asks 138 questions in 11 kinds (abstain, paraphrase, update, past, belief and more; `backend/eval/golden_questions.jsonl`). Two things are missing:
  - questions whose answer needs **two** facts ("where is my sister's wedding?" needs "sister = Priya" and "Priya's wedding is in Lisbon");
  - a test of the **learner**: made-up conversations, then a check that the 8B model proposes the right facts, keeps every "not", dates "last week" correctly, and turns a change into a correction card aimed at the right old fact.
- **Where from.** LongMemEval's five abilities (MIT; its scoring is already credited in `THIRD-PARTY-NOTICES.txt`). HaluMem (a 2025 benchmark) found that in every system it tested, *saving* was the weak step: under 60% of facts captured, and under half of updates done right. Its data was not used here.
- **Fit.** It uses made-up people only, on a scratch file. It never opens your memory. The learner test needs your PC's local model, so it runs there, not here.
- **Gain.** Every idea on this page can then be shown to help, or not, before it ships.
- **Risk.** Hand-written questions can be tuned to pass. Keep the "tune half / test half" split the self-test already uses.

### Idea 3. "Said again" counts (S)

- **What it is.** When the learner proposes something you already told Jarvis, `jarvis_intake.near_duplicate()` (`jarvis_intake.py:913`) drops it and adds 1 to a counter that is lost when the backend restarts. Instead, keep one small row per repeat: the fact's id, the date, and how it was said (typed or voice). **No words.**
- **Where from.** Hindsight's "observations" keep a proof count and quotes for each belief (MIT). Jarvis would copy only the count and dates, not the summary.
- **Fit.** Nothing is saved that was not already saved. It follows the same checks as learning (owner's own live words only). Erase removes nothing from these rows, because they hold only dates and ids. The history can still show "said 4 times", like Erase keeps dates today.
- **Uses.** (a) A tiny tie-break in search. (b) The tidy can offer "You have said this 5 times - keep it in mind?". That still needs your own tap to pin, as today. (c) Both apps can show "said 3 times, last on 12 Sep" under a fact.
- **Risk.** Low. The count must never make a fact harder to forget or correct.

### Idea 4. Real "true from" dates (M)

- **What it is.** Every fact already has two date pairs (`rebuilt/jarvis_memory.py:569-580`). But "true from" is always set to the moment of saving: `valid_from or now` (`:739`). The learner already writes real dates *into the words*: "I started yesterday" becomes "I started yesterday (2026-09-25)" (`jarvis_intake.anchor_dates`, `:492`; `learned_text`, `:521`). The idea: when a saved fact has a date **in the past**, also set "true from" to that date, using the same fixed date rules. No model involved.
- **Plus Graphiti's ordering rule** (`graphiti_core/utils/maintenance/edge_operations.py:538-573`, `:826-839`, Apache-2.0). If a correction is about an *earlier* time than the fact it would replace, it must not retire the newer fact. The card should say "this sounds older than what Jarvis knows".
- **Fit.** Corrections still always get a card (`jarvis_auto_learn.check_not_correction`, `:800`). This only puts better dates on the card and on the fact.
- **Gain.** "Where did I live in May?" (`jarvis_past.py`) then works from real dates, not from the day you mentioned it.
- **Risk.** **Never set a future date.** A fact that is "true from March" would be hidden until March. "I'm moving to Leeds in March" is true *now* as a plan. Past dates only. A wrong date is visible on the fact and can be edited, as today.

### Idea 5. Search hints (M)

- **What it is.** For each saved fact, the local model writes 3-6 extra search words on the learner's background thread. For example, "Owner's new manager is called Tom" gets "boss, supervisor, work". These words go in a separate search table only. They are **never** shown, never put in the prompt, never used to pick which fact a correction replaces (`find_one`, `:1365`), and never used for the sensitive-topic check.
- **Where from.** A-MEM builds meaning vectors from the fact *plus* model-written keywords (MIT). MemPalace adds made-up "User has mentioned: prefers X" entries at index time, and reports it fixed its weakest question type (MIT, their claim).
- **Fit.** Hints are made only from facts that are already saved, never from the conversation. A hint can only *add* a candidate, and the floors and re-ranker still judge the real words. **Erase must wipe the hints too**, because they come from the fact's words. Forget and correction retire them with the fact. The model call has the learner's usual checks: this PC only, loopback address, not a cloud model.
- **Gain.** The self-test found that about a quarter of answerable questions share no words with their fact (`backend/README.md`, "Memory wave 1"). Hints help word search there, even on day one before the meaning model has downloaded.
- **Risk.** A made-up hint can pull in a wrong fact, so measure it with the re-ranker on. It costs one short model call per saved fact, in the background.

### Idea 6. Date-closeness boost (S)

- **What it is.** Questions about the past already use a date *window* (`jarvis_past.when`, `recall` at `:328`). MemPalace (MIT) found a softer *boost* works better for questions where several facts match: facts near the question's date rank higher. It raised their time-question scores by several points (their claim).
- **Fit and risk.** It only re-orders. The fixed date parser stays; no model. It is best done after idea 4, so the dates are real.

### Idea 7. The overnight tidy, cards only (M-L)

- **What it is.** Today `jarvis_sleep.py` only records that you would like it (lines 16-22). The card in both apps says it is not built (JARVIS-API `/api/memory/sleep_time`). A first version, run by the one shared scheduler, would:
  - find likely duplicates between *stored* facts, using the same narrow rules as `near_duplicate`;
  - find likely contradictions: two current facts about the same person or thing with the same relation word ("lives in", "works at");
  - ask "Is this still true?" about old, time-bound facts ("is working on ...", a date now in the past);
  - raise any waiting "are these the same?" cards (`raise_merge_cards`, `:1918`);
  - fill in missing meaning vectors.
- **Where from.** Letta's sleep-time agents, LangMem's background memory manager, Hindsight's background consolidation. **All three change memory by themselves.** Jarvis would copy *when* they run (after the conversation, in the background), not *what* they are allowed to do.
- **Fit.** At most 5 cards a night, under the existing back-off (`jarvis_backoff.py`). No fact is retired or changed without your yes on that one fact, as `docs/ARCHITECTURE.md` §10 already says. Switching it on is a card (already built).
- **Risk.** Card fatigue. That is why there is a cap, and why dropping a card counts as "not now", never "no".

### Idea 8. Your call: search your own past words (M)

- **What it is.** MemPalace keeps the exact words of conversations and searches them directly. It reports 96.6% of the right sessions in the top 5 on LongMemEval, with no AI model involved (their claim, and a *finding* measure, not an *answer* measure). Jarvis already keeps an encrypted history of **your** turns only (`jarvis_chat_log.py`), tagged typed, voice, pasted and so on. A tool could search your own typed and voice turns, only when you ask ("what did I say about ..."). Results would appear on screen, and nothing would be saved to memory from them.
- **Why it is your call.** `docs/ARCHITECTURE.md` §5 says chat history "is not memory: nothing in it is recalled into a chat". This would change that rule. A search index over encrypted text also has to stay encrypted, or it breaks the "encrypted or not kept" rule.
- **Recommendation:** leave it until ideas 1-4 are built and measured.

---

## 4. What Jarvis already does well

These are from the real code. Each is something most or all of the projects above do **not** do.

| Jarvis feature | Where | How the others compare |
|---|---|---|
| **Nothing saved without a check.** Every fact is a proposal first. It is saved automatically only when a fixed list of checks passes, otherwise it becomes a card. | `jarvis_auto_learn.py` (checks at `:800`, `:903`, `:1008`, `:1084`, `:1125`) | None of the 15 has a review step. mem0, LangMem, A-MEM, Hindsight and Letta save straight away. |
| **Your own words only.** The learner reads your turns, never the assistant's, never tool output. Who started a turn is the backend's decision. | `jarvis_intake.owner_turns` (`:189`); ARCHITECTURE §5 "The learner" | mem0 made the *assistant's* words "first-class" in April 2026. MemPalace and Hindsight store both sides. |
| **Two date pairs, nothing deleted.** "When it was true" and "when Jarvis believed it". | `rebuilt/jarvis_memory.py:569-580`, `retire` `:805` | Only Graphiti has all four dates, and it needs a graph database server. mem0 keeps an edit log, not dates. |
| **Forget, and a real Erase.** Erase wipes the words from the file, including the word index, meaning vector, copies and names, and keeps the dates. | `erase` `:894` | mem0, LangMem and others delete rows. In the parts I read, none cleans the file afterwards (`secure_delete`, log truncation) the way Jarvis does. |
| **Words + meaning + people, merged, with floors.** Three lists, a word-share floor and a distance floor, so "what is my dog called?" does not get the cat. | `search` `:1207`; floors `:206`, `:248` | mem0 2026 does the same three signals, but adds scores together. Jarvis's rank merge (RRF) is the method Hindsight also uses. |
| **"Who is my sister?"** Names and aliases taken only from saved facts, word for word. Merging two names is always your card. | entity layer `:2500-2560`, `_entity_hits` `:1816` | mem0 finds names with spaCy (no model) but joins two names by itself when their meaning is 95% alike (`main.py:605-622`). Graphiti also joins names automatically. |
| **Sensitive topics wait for you**, in eight languages. Passwords, PINs, account and ID numbers *always* wait. | `jarvis_sensitive.py`, `always_asks` `:3278` | I found no sensitive-topic gate in any of the 15 (searched their READMEs and save code, not every file). |
| **Questions about the past** get old facts labelled "(no longer true since ...)". "What did I tell you in June" uses the belief dates. | `jarvis_past.py:328` | Graphiti and Hindsight filter by time. Only Jarvis separates "what was true" from "what I believed". |
| **Pinned facts, never rewritten.** Up to 1,200 characters, your tap only. | `pin` `:1520`, `PROFILE_LIMIT` `:2282` | Letta, MemoryOS and supermemory keep a similar list, but the model rewrites it. |
| **A right/wrong mark** can raise one "retire this?" card, never retire by itself. | `jarvis_feedback.py:346` | Nobody else ties answer feedback to a card. |
| **Dates shown to the model**, so an 18-month-old fact is not stated as today's news. | `memory-noise.patch`, `_dated_fact` | Copied from Khoj; now common. |

Honest limits of Jarvis today:
- **Meaning search is English only** (`bge-small-en-v1.5`, `:421`).
- **The relation words** in the people layer are English only.
- **Meaning search has never been measured on your PC.** The self-test here ran with words only, because the model cannot download in this container.

---

## 5. The projects, one by one

"Local on 8 GB?" asks whether it could run with nothing leaving the PC, using an 8B model on your card. "Last code" is the newest commit I downloaded.

| Project | Licence | Last code | How it stores | How it decides what to save / change | How it searches | Time and contradictions | Reported scores (their claim) | Local on 8 GB? |
|---|---|---|---|---|---|---|---|---|
| **mem0** | Apache-2.0 | 2026-09-25 | Vector store + a messages table | One model call; **add only** since April 2026; exact-text duplicate check | Meaning + word + entity boost, scores added | Time-aware search is **cloud-platform only** in the open code | LoCoMo 92.5, LongMemEval 94.4 (**cloud platform**, not the open code) | Partly: Ollama works, but its long prompt is hard for an 8B model. Telemetry is on unless `MEM0_TELEMETRY=false`. |
| **Graphiti / Zep** | Apache-2.0 | 2026-09-25 | Graph of entities and facts, four dates each | Several model calls per message; the model marks contradictions, dates decide which one expires | Words + meaning + graph walk; RRF, MMR or a checking model | Best in class | Zep paper: 63.8% vs mem0 49% on LongMemEval (2025) | Hard: needs Neo4j or FalkorDB; README warns small models give "incorrect output schemas". Telemetry on by default. |
| **Letta** (was MemGPT) | Apache-2.0 | 2026-09-25 | Now a git folder of memory text files ("MemFS"); code moved to `letta-ai/letta-code` | The model edits its own memory files; a background "reflection" helper tidies | The model reads files and searches its own history | Git history only | None checked | Yes (it has a local mode), but the model writes its own memory |
| **LangMem** | MIT | 2026-09-08 | LangGraph's store | Model decides create/update; **deletes off by default**; runs after a quiet period | Meaning search | None built in | None checked | Yes with Ollama; LangGraph needed |
| **A-MEM** | MIT | 2025-11-06 | ChromaDB notes with model-written keywords, tags, context | Model writes the extra fields and **rewrites older notes** ("memory evolution") | Meaning over fact + keywords | None | LoCoMo gains in the paper (numbers not checked) | Yes (Ollama, Llama-3.1-8B shown) |
| **MemoryOS** | Apache-2.0 | 2026-07-07 | Short, mid and long-term tiers; a model-written user profile | "Heat" = visits + length + recency moves things up a tier | Meaning search per tier | Recency only | +49% F1 on LoCoMo (relative to their baselines) | Yes, but it summarises and profiles |
| **MemOS** | Apache-2.0 | 2026-09-22 | Server: Neo4j + Qdrant; local plugin: **SQLite + FTS5 + vectors** | Model-driven, with "skill" learning | Hybrid words + meaning | Not checked | LoCoMo 88.83, LongMemEval 89.20 | Local plugin yes; it has the same shape as Jarvis's store |
| **Cognee** | Apache-2.0 | 2026-09-24 | Graph (embedded) + LanceDB | Model builds a knowledge graph ("cognify") | Graph + meaning | Not central | BEAM report only | Yes since v1.6 (2026-09-18). Telemetry on unless `TELEMETRY_DISABLED` is set. |
| **Hindsight** | MIT | 2026-09-25 | Embedded Postgres; facts, experiences, "observations" | Model extracts facts, entities, dates; background merges into observations with proof counts | **Words + meaning + graph + time, RRF, then a local re-ranker** | Time filter; observations refined, not overwritten | LongMemEval 91.4% → 94.6% (says reproduced by Virginia Tech) | Yes with Ollama; Postgres is heavy next to one SQLite file |
| **supermemory** | MIT (repo) | 2026-09-25 | Graph engine inside a "local" program | Not checkable (engine code not found in the repo) | Hybrid | "Static" and "dynamic" profile | "#1", 95% found in top 15 on LongMemEval | Says it runs offline with Ollama; not verified |
| **MemPalace** | MIT | 2026-09-24 | **Exact words** of sessions, local vector store | Keeps everything; adds made-up preference entries | Meaning + keyword, name and date boosts; optional model re-check | Date-closeness boost | 96.6% found in top 5 (a *finding* measure); openly flags its own "teaching to the test" | Yes: the base needs no model at all |
| **memU** | Apache-2.0 | 2026-09-21 | A "wiki" of memory files; local SQLite or cloud | Background task distils sessions and skills | Meaning (brute force in SQLite) | Not checked | None checked | Local mode exists; quick start is cloud-first |
| **txtai** | Apache-2.0 | (README only) | General search database (vectors, words, graph, SQL) | A toolkit, not a memory system | Hybrid | None | n/a | Yes, but Jarvis already has these pieces in SQLite |

Also checked only through search results: **EverMind/EverOS**, **ByteRover**, **OMEGA** (95.4% on LongMemEval, self-reported) and **LongMemEval-V2** (May 2026, uses Qwen3.5-9B as the reader). None of their code was read.

---

## 6. Benchmark numbers, and why they cannot be lined up

- **LoCoMo** (Snap, 2024): about 10 long, made-up two-person chats. Questions are single-hop, multi-hop, time and "no answer". Its data licence is **CC BY-NC 4.0** (non-commercial, credit required).
- **LongMemEval** (ICLR 2025, MIT): 500 questions in five abilities: finding information, joining sessions, time, updated facts, and saying "I don't know". Jarvis's self-test already borrows its scoring.
- **BEAM** (2026): memory at 1 to 10 million words; mem0 64.1 at 1M (their claim).
- **HaluMem** (2025): tests each memory *step* (saving, updating, answering). This is where every system tested looked weakest.

Why the scores do not compare:
- Some are **"finding" scores** (was the right session in the top 5?). Others are **"answer" scores** (did a judge model accept the answer?).
- Most use GPT-4o-class cloud models as reader and judge.
- mem0 says its numbers are from its paid platform, which has features not in the open code.

**No project published scores for an 8B model on an 8 GB card.** Jarvis's own self-test on your PC is the only number that will mean anything for Jarvis.

---

## 7. Not for Jarvis

| Popular idea | Who does it | Why it is wrong for Jarvis |
|---|---|---|
| The model updates or deletes memories by itself | Graphiti (auto-expires), LangMem, A-MEM ("memory evolution"), older mem0 | Breaks "no fact retired without your yes". mem0 itself moved away from it. |
| The model writes its own memory as a tool | Letta (edits its memory files; auto-allowed in `memory-write-allowance.ts`), LangMem's "manage memory" tool | This is how most published memory-poisoning attacks work (MINJA reports over 95% injection success in ideal conditions). Jarvis excludes it on purpose. |
| Saving what the **assistant** said | mem0 ("agent-generated facts are first-class"), MemPalace, Hindsight | The assistant's words carry quoted emails, web pages and recalled memories. Rule: your own words only. |
| Summarising memories into "observations", profiles or personas | Hindsight, MemoryOS, Letta, supermemory | Summaries drop words, most often "not". ARCHITECTURE §5: never compress facts. |
| Forgetting by "heat" or decay | MemoryOS | Hides facts without your decision. Recency as a small *tie-break* is fine; hiding is not. |
| A graph database or Postgres server | Graphiti (Neo4j required), MemOS server, Hindsight | Jarvis is one SQLite file, no extra servers to run. The entity layer already gives the useful part. |
| Data sent to the project makers by default | mem0 (`MEM0_TELEMETRY` defaults to True), Graphiti (`GRAPHITI_TELEMETRY_ENABLED` defaults to true), Cognee | Rule 1. Borrow designs, not these packages. |
| Asking the big model to re-check 20 results every question | MemPalace's optional re-rank, Hindsight's reflect | On an 8 GB card that is seconds of extra wait per question. A small re-ranker on the processor (idea 1) is the local equivalent. |
| Rewriting the assistant's own rules from feedback | LangMem's prompt optimiser | The model would rewrite Jarvis's rules. Feedback may only raise cards. |
| Hosted memory or a cloud "sync" | mem0 platform, supermemory, Letta Cloud, memU cloud | Rule 1. |

---

## 8. What I could not check

- **Web pages at mem0.ai could not be opened** (blocked here). mem0's README and code were read instead.
- **supermemory's engine code** was not found in its repository, so its method could not be checked.
- **No benchmark was re-run.** The scores above are claims. Hindsight says an outside group reproduced its numbers; I did not see that report.
- **No model could be downloaded here,** so the re-ranker's speed and gain are unmeasured. I also do not know which fastembed version is on your PC.
- **LongMemEval's dataset licence** was not checked; only its code licence (MIT) was.
- **The A-MEM, MemoryOS and HaluMem paper numbers** were taken from READMEs and search summaries, not from the papers.
- **Out of date elsewhere:** `docs/PEERS.md` (2026-09-15) says "Jarvis has valid_from / valid_to - valid time only". That is no longer true: `created` and `retired_at` were added later, and ARCHITECTURE §5 describes both. Also, Letta's code moved to `letta-ai/letta-code`; the old `letta-ai/letta` repository now holds only a pointer.

---

## 9. Your call

**Which to build first?**
- **Ideas 1-4 first, each measured by the self-test** (recommended). All four are small or medium, work on the PC for both apps, and need no new permission rules.
- **The overnight tidy first.** It is bigger, and it is more useful once "said again" counts and real dates exist.

**Searching your own past words (idea 8)** changes a written rule, so it waits for you. Recommended: leave it until 1-4 are done.

---

## Sources

Code read (shallow clones, 2026-09-26):
- mem0: https://github.com/mem0ai/mem0 (`mem0/memory/main.py`, `mem0/utils/scoring.py`, `mem0/configs/prompts.py`, `mem0/memory/telemetry.py`); benchmarks https://github.com/mem0ai/memory-benchmarks
- Graphiti: https://github.com/getzep/graphiti (`graphiti_core/utils/maintenance/edge_operations.py`, `search/search_config.py`, `telemetry/telemetry.py`, `pyproject.toml`)
- Letta: https://github.com/letta-ai/letta and https://github.com/letta-ai/letta-code (`src/permissions/memory-write-allowance.ts`, `src/skills/builtin/syncing-memory-filesystem/SKILL.md`)
- LangMem: https://github.com/langchain-ai/langmem (`src/langmem/knowledge/extraction.py`)
- A-MEM: https://github.com/agiresearch/A-mem, https://github.com/WujiangXu/A-mem-sys
- MemoryOS: https://github.com/BAI-LAB/MemoryOS (`memoryos-pypi/mid_term.py`)
- MemOS: https://github.com/MemTensor/MemOS
- Cognee: https://github.com/topoteretes/cognee (`cognee/shared/utils.py`, database configs)
- Hindsight: https://github.com/vectorize-io/hindsight (`hindsight-api-slim/hindsight_api/config.py`)
- supermemory: https://github.com/supermemoryai/supermemory
- MemPalace: https://github.com/milla-jovovich/mempalace (`README.md`, `benchmarks/BENCHMARKS.md`)
- memU: https://github.com/NevaMind-AI/memU
- txtai: https://github.com/neuml/txtai
- fastembed 0.8.1 (PyPI wheel, `fastembed/rerank/cross_encoder/onnx_text_cross_encoder.py`)
- LongMemEval: https://github.com/xiaowu0162/LongMemEval; LoCoMo: https://github.com/snap-research/locomo

Web (read through search results only):
- mem0 algorithm and benchmarks: https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm, https://mem0.ai/research, https://mem0.ai/blog/ai-memory-benchmarks-in-2026
- Letta sleep-time compute: https://www.letta.com/blog/sleep-time-compute/, https://docs.letta.com/guides/agents/architectures/sleeptime/
- Zep paper: https://arxiv.org/abs/2501.13956
- Hindsight: https://arxiv.org/pdf/2512.12818, https://aclanthology.org/2026.acl-demo.27/, https://hindsight.vectorize.io/blog/2026/08/11/open-source-agent-memory-systems
- LongMemEval-V2: https://arxiv.org/html/2605.12493v1; leaderboard: https://omegamax.co/benchmarks
- HaluMem: https://arxiv.org/abs/2511.03506, https://github.com/MemTensor/HaluMem
- Memory poisoning: https://arxiv.org/abs/2601.05504, https://arxiv.org/pdf/2604.16548
