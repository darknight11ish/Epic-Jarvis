# Report 60 (audit), agent a3aa6aee, 2026-09-30T08:49Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first; beginner owner, plain words; verify each claim with file:line + quote; 'not checked' honestly; change no files). The owner asks: 'Does the memory and storage of Jarvis need a review? Can it be efficiently managed currently? Can it compress anything automatically to save space?' YOUR PART = Jarvis's MEMORY (the facts it learns and recalls): docs/ARCHITECTURE.md section 5, docs/MEMORY-RESEARCH-2026-09-26.md, docs/MEMORY-SCOREBOARD.md, backend/rebuilt/jarvis_memory.py, jarvis_entities.py, jarvis_tidy.py (overnight tidy), jarvis_auto

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

MEMORY AUDIT (facts store). Read-only; only my own throwaway script in the scratchpad was run.

BOTTOM LINE: memory is small and well managed for safety. It is NOT managed for space, but that does not matter yet. A normal owner has hundreds to a few thousand facts, which is 1-5 MB. No compression is worth doing now.

(1) HOW A FACT IS STORED (backend/rebuilt/jarvis_memory.py)
- `facts` table (line 1422): text, source, created, valid_from, valid_to, retired_at, retired_by, embedded, meta (JSON), plus erased_at. Two indexes.
- `facts_fts` (line 1482): FTS5 external-content index (porter stemmer). It stores no second copy of the text.
- `facts_vec` (line 1499): sqlite-vec `vec0`, `float[dim]` (float32). Default model is BAAI/bge-small-en-v1.5 (line 469), which I believe is 384 dimensions. That is 1,536 bytes per fact.
- Small side tables: profile (pins, ids only), entities, entity_aliases, fact_entities, fact_repeats ("said again", no words), tidy_cards.
- MEASURED with sqlite-vec 0.1.9, a copy of the schema, 384-dim random vectors and 9-word facts. This is the same layout, not the real Jarvis store: no real embedder, no entity rows, and the PC's real facts and meta will differ.

| Facts | File | Per fact | Vector-only search | Word-only search |
|---|---|---|---|---|
| 1k | 1.9 MB | 1,925 B | 1.1 ms | 0.4 ms |
| 10k | 18.5 MB | 1,851 B | 6.7 ms | 3.1 ms |
| 100k | 182 MB | 1,820 B | 66 ms | 28 ms |

- The vector is about 85% of the file (154 of 182 MB at 100k). The text table is about 10%, and the FTS index about 3%.
- Search is brute force: a straight scan of every vector, with no index (line 2427). Linear in the number of facts, and quick up to 100k.
- The chat history is a separate encrypted file (backend/jarvis_chat_log.py). Its size is not in this estimate.

(2) IS IT EFFICIENTLY MANAGED?
- **Duplicates.** There is no near-duplicate merge for facts. Saying the same thing again adds a "said again" row (`fact_repeats`) via `find_one` (line 2657). Entity merges use Jaccard 0.9 (line 4456) and ask with a card. So a re-worded fact can be stored twice; I did not test how often that happens.
- **Superseded and forgotten facts are kept forever.** The `retired_at` / `retired_by` columns exist on purpose, so history stays readable. Retiring only sets dates (line 1816); it does NOT delete the vector. A retired fact keeps its 1.5 KB vector and its FTS entry.
  - Real finding: the vector search takes the top 50 first and drops retired facts afterwards (line 2427 onward, filter after). Old versions of a fact sit very close to the new one, so they can use up candidate slots. I did not measure how much this hurts recall.
- **Erase** (line ~2003) is done properly: it uses `secure_delete`, removes the vector and FTS words, then runs an FTS 'optimize' and a WAL checkpoint (`_scrub_file`, line 3785). There is NO VACUUM in the memory store. Only the chat log vacuums (jarvis_chat_log.py:764). Erased rows leave free pages inside the file, so it does not shrink.
- **Consolidation, summarising and decay:** none, and this is deliberate. ARCHITECTURE §5 (line 1319) says "Never compress facts or transcripts", because summaries drop the word "not". The research report rejects observation/summary memory for the same reason. The recall rules say "no fact added, dropped, hidden or faded".
- **Cap:** I found no cap on total facts (I only grepped, not a full read). The only cap is the pinned facts, 1,200 characters (`PROFILE_LIMIT`).
- **Prompt budget:** recall injects 5 facts per turn (`JARVIS_MEMORY_K`, default 5, jarvis_quick.py:3216) plus at most 1,200 characters of pins. The re-ranker looks at the top ~20 and is off until measured. Prompt cost stays constant however big the store grows.
- **Overnight tidy** (backend/jarvis_tidy.py): off by default, cards only. It does two things a night. "Still true?" asks about facts whose own words gave a passed end date. "Which is true now?" asks the local model about possible contradictions. Accepting a card only ends a fact as history. It never deletes, merges or compacts, so it reduces contradictions, not size or clutter.

(3) COMPRESSION OPTIONS (per fact; a 384-dim vector is 1,536 B)
- **float16 vectors:** saves 768 B, about 40% of the file. Recall risk is very low, but sqlite-vec vec0 has no float16 column type. It would need int8, or storing float16 blobs and doing the maths yourself (a bigger change).
- **int8 vectors:** vec0 supports it. Saves about 1,150 B per fact, about 62% of the file (about 113 MB at 100k). It needs a quantisation step and must be measured with eval_memory.py before it is kept. That is the owner's rule.
- **Binary (bit) vectors:** about 96% smaller. Recall is usually clearly worse, so only useful as a first pass followed by re-scoring.
- **Fewer dimensions (Matryoshka):** I believe bge-small is not trained for it, so this is not safe. nomic-embed-text is, but switching model means re-embedding everything. Not checked.
- **Drop vectors of retired facts:** saves 1.5 KB per retired fact and removes the crowding problem above. Risk: "what did I believe in June" searches then use words only. The fix is to embed on demand, and it is small. Not measured.
- **Compress the text (zlib):** the text is only about 10% of the file. It also breaks FTS/erase simplicity and the "no compression" rule. Not worth it.
- **Content-less FTS:** already external-content. Nothing to save.
- **VACUUM after erases:** recovers free pages. Cheap and safe, with no recall effect.
- **SQLite page compression:** there is no built-in option, and I did not check extensions. Not recommended.

(4) GAPS
- Neither app shows memory size. `status()` (line 2805) returns counts only (facts, current, retired, erased, entities) and no bytes. I grepped for "memory size" / "db_size" in both apps and the backend and found nothing.
- Nothing shows what takes space (vectors vs. text vs. retired facts).
- Nothing on this store's file-size limits.

RANKED SMALLEST SAFE CHANGES (payoff / safety)
1. Add `db_bytes`, `retired_with_vector` and free-page counts to `status()`, and show one line in Brain > Memory on both apps. Saves nothing itself, but makes the size visible. Zero risk. Both apps need it, per the parity rule.
2. VACUUM (or `incremental_vacuum`) once after an erase, at most hourly like the chat log. Recovers erased space. Safe.
3. Delete the vectors of retired facts and re-embed when "as it was" search needs them. Saves 1.5 KB per retired fact and may improve recall. Gate it on eval_memory.py.
4. int8 vectors. Saves about 60% of the file. Only worth it past roughly 50k facts, and only if eval_memory.py does not get worse.
5. A soft "your memory is large" note at, say, 50k facts. No auto-deletion.

OWNER DECISIONS (recommendation first)
A. Show memory size in Brain (facts, disk MB, retired count)?
   - Yes, one line in both apps (recommended)
   - Leave alone
B. Retired facts keep their meaning-search vectors today. Drop them?
   - Not now; measure first with eval_memory.py (recommended)
   - Drop them
C. Squeeze vectors (int8)?
   - No, files are small (recommended)
   - Try and measure it

NOT CHECKED: a real memory.db (none in this repo); the real embedder's dimension and speed; the re-ranker's numbers on the PC (docs/MEMORY-SCOREBOARD.md shows no real-model row yet, only "not run yet"); the tests and eval_memory.py (not run, since fastembed is not installed here); the desktop and phone memory panes beyond a grep for size.
