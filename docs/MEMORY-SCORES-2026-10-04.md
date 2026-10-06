# Memory scores — 2026-10-04

The project's own rule (CLAUDE.md, 2026-09-26): *"Every memory or learning
change must beat the memory self-test (`backend/eval_memory.py`) and the
learner test (`backend/eval_learner.py`) before it is kept... Numbers from
the real model come from the owner's PC (one PowerShell line), and are
written on a memory scoreboard page after each change."*

This is that page for the 2026-10-04 audit pass.

## What was run

```powershell
cd "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
$env:PYTHONIOENCODING = "utf-8"
py -3 backend\eval_memory.py                      # before (2,267 s)
py -3 backend\eval_memory.py --against "<the run above>.json"   # after (2,529 s)
```

- Machine: Windows AMD64, Python 3.12.10, the owner's PC.
- Embedder: **BAAI/bge-small-en-v1.5** — real meaning *and* words (not the
  hash stand-in).
- Floors in use: word floor **0.1** (`JARVIS_MEMORY_MIN_WORD_SHARE`),
  distance floor **1.0** (`JARVIS_MEMORY_MAX_DISTANCE`).
- Reports: `~/jarvis-memory-eval/memory-eval-20261004-104724.md` (before) and
  `...-113308.md` (after); raw transcripts in
  `dshwork/audit-2026-10-04/eval-memory-before.txt` and `-after.txt`.

## What changed in this pass

`jarvis_intake.near_duplicate()` now compares **dates aside** — `shape(undated(text))`
instead of `shape(text)` — the way its sibling `_repeats_of()` has always
compared. Reason and evidence: see
[HANDOFF-2026-10-04-audit-pass.md](HANDOFF-2026-10-04-audit-pass.md) §1.2. It
changed which **review-queue cards** are created, not how anything is
searched or ranked. Nothing else in memory was touched (the other memory
change in this pass, `MemoryStore.erase()`'s VACUUM, is about what bytes are
left in `memory.db`, not about retrieval).

## The numbers

`--against` compared **124 rows; every one is "unchanged"** — no recall@5,
no "replaced came back", no "time: wrong version" and no learner kind moved
in either direction. There is no "WORSE" line, so by the project's own rule
the change is kept.

| Filler | Facts | Recall@5 (word floor off -> on) | Don't-know: none returned | Learner kinds wrong |
|---|---|---|---|---|
| neutral | 71 | 95.7% -> 94.7% | 5.3% -> 5.3% | 0 |
| neutral | 1,071 | 89.4% -> 88.3% | 2.6% -> 2.6% | 0 |
| neutral | 10,071 | 88.3% -> 87.2% | 0.0% -> 0.0% | 0 |
| same-topic | 71 | 95.7% -> 94.7% | 5.3% -> 5.3% | 0 |
| same-topic | 1,071 | 92.6% -> 91.5% | 5.3% -> 5.3% | 0 |
| same-topic | 10,071 | 89.4% -> 88.3% | 5.3% -> 5.3% | 0 |

(Values identical before and after the change; the left-to-right arrow is
the eval's own "word floor off -> on" comparison, not this pass.)

Learner half, before -> after (all identical): reads 6/6, remember 4/4,
dates 8/8, gate 37/37, said-again 14/14, true-from 12/12, moves 10/10,
true-until 12/12, topic 13/13, tidy where-questions 0 wrong, topics 0 leaks.
**The real learner (`jarvis_extract.propose` through the real model) was not
asked for** — that half needs `--learner-model qwen3:8b`; see "Not proved".

## Open finding 5.1: the relevance floor, measured

The handoff's finding 5.1 was: on this machine an off-topic question can pull
in the owner's bank, medication or car. Measured here with the real embedder,
sweeping `JARVIS_MEMORY_MAX_DISTANCE` (from the after-run report; `Don't
know: none returned` = the share of questions memory cannot answer for which
**no** wrong fact came back):

| Filler | Facts | Distance 0.9 | 1.0 (in use) | 1.1 | 1.2 |
|---|---|---|---|---|---|
| neutral | 71 | recall 89.4%, none 39.5% | recall 97.9%, none 5.3% | recall 97.9%, **none 0.0%** | recall 97.9%, none 0.0% |
| neutral | 1,071 | recall 87.2%, none 31.6% | recall 91.5%, none 2.6% | recall 91.5%, **none 0.0%** | recall 91.5%, none 0.0% |
| same-topic | 71 | — | recall 97.9%, none 5.3% | recall 97.9%, **none 0.0%** | — |

**Read the TABLE above, not the sentence that used to be here (corrected
2026-10-06).** The sentence said 1.1 "returns no wrong fact at all" while 1.0
"returns one for ~5% of unanswerable questions", which is the opposite of what
the column says. Taken as written - "none returned" meaning the share of
unanswerable questions for which **no** wrong fact came back - the table reads
39.5 % at 0.9, 5.3 % at 1.0 and **0.0 % at 1.1**: a *looser* floor hands back a
wrong fact *more* often, and the build-machine scoreboard says the same in
words ("Don't know" questions still get 1.47 wrong facts each,
`docs/MEMORY-SCOREBOARD.md:87-88`). On that reading, moving to 1.1 would make
the confabulation worse.

So the change is deliberately **not taken in this pass** - and not only
because the numbers disagree with themselves:

`eval_memory.py` chooses the floor on the **tune half only**
(`choose_distance()`, "Allowed: a distance that finds every right fact the
loosest one tried finds... Chosen: of those, the one with the fewest 'don't
know' facts"), and on the tune half it chose **1.0**. Moving to 1.1 because
of the held-out numbers is exactly the peek that the tune/test split exists
to prevent; it is how a number gets tuned to one golden set and then fails on
the owner's real memory. The honest next step is a **bigger golden set**
(more unanswerable questions), re-choosing 1.0/1.1/1.2 on the tune half with
the real embedder — not a one-line change made on the strength of the test
half. Recorded here so the next pass starts from the measurement instead of
re-deriving it.

## Not proved

- The real learner was **not** run (no `--learner-model`): the model half of
  `eval_learner.py` needs this PC's Ollama and `jarvis_extract.py`, and the
  default run deliberately asks no model. Every model-free learner kind is
  0 wrong, before and after.
- The `--against` comparison covers the main self-test and the learner
  kinds the report tabulates; timings are not compared (by design).
- The distance-floor question above is measured, not decided: the change is
  the owner's to make, and it needs the bigger golden set first.
