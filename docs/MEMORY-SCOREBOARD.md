# Memory scoreboard

The owner decided on 2026-09-26 that every memory or learning change must beat
these numbers before it is kept (CLAUDE.md). This page records them after each
change, so progress can be seen instead of taken on trust.

- **Search** (`backend/eval_memory.py`): does Jarvis find the right fact? 71
  made-up facts, buried under 0 to 10,071 filler facts.
- **Learning** (`backend/eval_learner.py`, run by the same command): do the
  right facts get saved, and the wrong ones (pasted text, links, jokes, a
  dropped "not") stay out?

No real data of the owner's is used. The test builds a made-up person in a
temporary file and deletes it afterwards.

## How to run it on the PC (one line)

Open PowerShell in this repository's folder (the one with `backend` and
`scripts` in it) and paste:

```powershell
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 backend\eval_memory.py --learner-model qwen3:8b; explorer "$env:USERPROFILE\jarvis-memory-eval"
```

**Run `apply-patches.ps1` first** (docs/INSTALL.md), if you have not since
you last updated this folder. The test measures the memory code that is in
your Jarvis folder (the one `JARVIS_BACKEND` names), not the copy in this
repository, so an older copy there gives older numbers
(`backend/eval_memory.py`, `_load_memory`).

It takes about 5-15 minutes. The first run downloads the re-ranker model once
(about 80 MB). None of your data is sent anywhere. When it finishes, it opens
the `jarvis-memory-eval` folder in your home folder
(`C:\Users\pcadmin\jarvis-memory-eval`). Send back the `.md` file in that
folder, and its numbers go in the table below.

**Trying other memory-search models** (a different meaning model or
re-ranker, 2026-09-28): `tools/model_tryout/README.md`, section 2. It runs
this same self-test once per model, never switches anything, and ends with
rows in this table's format ("Tryout: ...").

## The numbers

"Words only" means the search that does not use the meaning model. It is all
the build machine can run: it cannot download models. The real numbers, with
meaning search, the real re-ranker and the real learner model, come only from
the PC run above.

| Date | Change | Where measured | recall@5 (71 facts) | Two-fact questions | Time questions (wrong old versions) | Learner cases |
|---|---|---|---|---|---|---|
| 2026-09-26 | Before memory ideas 1, 3, 4 (bigger test only) | build machine, words only | 78.7% | 6/10 | 8/10 (4 wrong) | 33/33 of the old cases |
| 2026-09-26 | Ideas 1-4 (re-ranker as a stand-in, "said again", "true from" dates) | build machine, words only | 78.7% | 6/10 | 9/10 (0 wrong) | +12/12 "said again", +8/8 "true from" |
| - | Ideas 1-4, real models | **the PC - not run yet** | - | - | - | - |
| 2026-09-27 | The memory review's fixes (docs/MEMORY-REVIEW-2026-09-27.md: bugs B1-B15 and B17; improvements I1, I3-I7, I12, I13 kept, I2 not kept) | build machine, words only | **80.9%** (79.8-77.7% at 171-1,071 facts) | **7/10** | **10/10 (0 wrong)** - wrong now also counts a newer fact handed over unlabelled: 3 before the fixes | **80/80** (27 new cases; 60/80 before the fixes) |
| 2026-09-27 | Re-run after the later learning and memory changes: "passing moods are not facts" in the learner's instructions (I154), crisis messages never learned (I151), "Between us" and the "From now on" / humour settings (docs/QUALITY-AUDIT-2026-09-27.md, section 8) | build machine, words only | 80.9% (unchanged) | 7/10 (unchanged) | 10/10, 0 wrong (unchanged) | 80/80 (unchanged) |
| 2026-09-28 | Smarter memory dates: "true until" end dates (a label, never a hide), "Where did I put ...?" (a newer place replaces the older one; answered without the model), "put / placed / stored ..." read as a change by "true from", and the overnight tidy's "Which is true now?" finder (docs/JARVIS-API.md sections 77-79) | build machine, words only | 80.9% (unchanged; 79.8-77.7% at 171-1,071, unchanged) | 7/10 (unchanged) | 10/10, 0 wrong (unchanged) | 80/80 of the old cases (unchanged) **+10/10 "things that move" +12/12 "true until"** |
| 2026-09-30 | Topic controls (docs/TOPIC-CONTROLS-DESIGN.md, JARVIS-API section 107): a mode per topic, kept out of the search itself; every topic on "Learn and use" | build machine, words only | 80.9% (unchanged; 79.8-77.7% at 171-1,071, unchanged) | 7/10 (unchanged) | 10/10, 0 wrong (unchanged) | 103/103 of the old cases (unchanged) **+13/13 "topic" cases** |

The 2026-09-28 row, in words: every number the self-test compares was the
same before and after (the run with `--against` the one before: 110 numbers
unchanged, none better, none worse). The new parts, measured for the first
time:

- **"Where did I put ...?"**: 13/13 questions answered right through the
  real fast path, and 0 older places given (the passport moved, the glasses
  moved, winter coats moved three times - one of them older news, which
  stays history).
- **"Which is true now?"** (the overnight tidy): with a stand-in model that
  always answers right, precision **1.0** (20 of 20 pairs raised were real
  conflicts) and recall **1.0** (20 of 20 found), 0 of 20 "both can be true"
  pairs raised. The owner's bar was precision 0.8: met. This measures the
  finder - which older facts it puts in front of the model, and whether it
  reads the numbers back right - **not the model**. What the real 8B model
  gets right comes only from the PC run with `--learner-model` (the same
  line as always; it now runs the finder with the real model too).

The last row before it says only that nothing measurable here got worse. It **cannot**
say whether I154 helps: that change is to the words the real learner model
reads, and on the build machine the learner is a stand-in that never reads
them. Only the PC run with `--learner-model` measures it.

The 2026-09-27 row in words: "my boss" and "my GP" are now found (recall@5
+2.2 points at every size); "What phone did I have in June?" is found (time
questions 9 -> 10/10, and 8 -> 9/10 with 171 and 1,071 facts about the same
things); a fact that became true later is labelled, never handed over as the
answer for then (3 wrong versions -> 0); "for whose wedding?" gets the fact
saying who Priya is (two-fact questions 6 -> 7/10). "Don't know" questions
still get 1.47 wrong facts each at 71 facts (2.37 at 1,071 same-topic) -
unchanged, and still the biggest weakness. The sensitive-topic check catches
26 of 26 new probe lines ("I tried to kill myself", "I'm sleeping rough",
"I'm being stalked") - 16 before - with no new false alarms and no change
on its four older test sets. backend/README.md, "The memory review's fixes",
has every number.

What only the PC run can settle about the 2026-09-27 changes:
- **Whether "boss"/"GP" (I1) still adds anything with meaning search on** -
  the meaning model may already find them.
- **The distance floor** (`JARVIS_MEMORY_MAX_DISTANCE`, still 1.0): the self-
  test now chooses it on half the questions, as chat recall runs, and
  reports it on the other half (I6) - but only where meaning search runs.
- **The re-ranker with "one step out" (I13):** with the word-overlap
  stand-in re-ordering, the extra fact is not added (two-fact 7 -> 6/10 on
  the re-ranked line). The real re-ranker may order it either way.
- **Skipping the re-ranker when five facts or fewer are found (I2)** was not
  kept: with the stand-in it made recall@1 and MRR slightly worse, and the
  time it would save shows only on the PC.
- **How often the real learner model leaves out "replaces"** - the new
  contradiction check (B5) catches it either way; the PC run says how often
  it is needed.
- **Whether your speech-to-text writes "3" or "three"** (I3).
- **The models' folder (B17):** empty `%TEMP%`, restart, and
  `/api/memory/status` should still show meaning search on (and the
  re-ranker, when it is switched on), with no download. Your own backend
  start-up is outside this repository and was not checked.

What is not known yet, and waits for the PC run:
- **Whether the re-ranker helps at all.** On the build machine it could only
  run as a word-overlap stand-in, which proves that it is wired in, not that
  it helps. **It is OFF by default until the PC run shows it helps**
  (2026-09-26, your rule). The self-test above measures it anyway (the
  "reranked" line). If that line beats the one without it, turn it on with
  one line, then restart Jarvis:
  `[Environment]::SetEnvironmentVariable('JARVIS_MEMORY_RERANK', '1', 'User'); Write-Host 'Done. Quit Jarvis from the tray and start it again.'`
- **How well the real 8B model picks facts out of a conversation.** The
  learner cases above use a stand-in for the model's one judgement call (is
  this a sensitive topic?). `--learner-model` runs the real one.


### Topic controls, 2026-09-30 (memory change: kept only because no number moved)

The rule (CLAUDE.md, 2026-09-26): a memory change is kept only if it does not make the numbers worse.
This change puts a filter inside the search (`MemoryStore.search(topics="use")`, the default), so it had
to be proved harmless when nothing is switched off, and proved to work when something is.

**With every topic on "Learn and use"** (how it ships; `eval_memory.py --words-only --sizes 0,100,1000`,
before and after): every level of the main self-test is identical - recall@1 / recall@5 (73.4 / 72.3 /
72.3 % neutral, 73.4 / 71.3 / 70.2 % same-topic, with the word floor; 80.9 / 79.8 / 79.8 and 80.9 / 78.7
/ 77.7 % with the entity layer), MRR, "replaced came back", past / as-of found, the bigger test (7/10
two-fact, 10/10 or 9/10 time, 0 wrong versions), don't-know numbers, the floor sweeps, the "where did I
put" and tidy parts, and all 103 older learner cases (the run with `--against` the earlier one reports
nothing worse). The new part (`backend/eval_topics.py`) also checks, at every size, that the facts a
chat turn recalls with topics seeded and every topic on are **exactly** those of a memory with no topic
tables: same facts, same order, same scores.

**With Work switched off, and with Work on "Learn, but don't use"** (made-up person, Work = 8 of the 71
facts; the run with Work on shows 35 Work facts reaching answers, so a zero is not a test that cannot
fail):

| Filler | Facts | Work facts in answers, Work on | Leaks, Work off | Leaks, Work "don't use" | Pinned Work fact leaks | Recall@5 on questions about topics that stay on (117) | Work-only questions with no Work fact back |
|---|---|---|---|---|---|---|---|
| 0 | 71 | 35 | **0** | **0** | no | 100 -> 100 | 11/11 |
| 100 | 171 | 35 | **0** | **0** | no | 98 -> 98 | 11/11 |
| 1,000 | 1,071 | 35 | **0** | **0** | no | 97 -> 97 | 11/11 |

Search time (p50, ms), Work off, Work only 8 facts: 1.43 -> 1.44 at 71 facts, 1.41 -> 1.37 at 171,
1.77 -> 1.62 at 1,071, 2.00 -> 2.19 at 10,071 (p95 6.05 -> 6.49) - inside the run-to-run noise. With a
BIG blocked topic (a third of 10,071 facts, 3,362, filed under Work and switched off) the search costs
more: p50 1.79 -> 3.43 ms, p95 4.99 -> 6.36 ms (words only, one build-machine run). That is the price of
working out which facts are blocked on every search; it is a few milliseconds, not measured on the
owner's PC, and a cache of the blocked set is the obvious next step if it ever matters.

**The learner** (`eval/learner_cases.jsonl`, kind `topic`): 13/13 - a fact sure to belong to a topic set
to "don't learn" is dropped before the queue and nothing is saved; a fact that only might belong to it
is a card with the reason; `Remember:` on it asks first; a topic on "Learn, but don't use" still
learns; with no topic switched off nothing differs; the sensitive gate still applies in every mode.
Older learner kinds: 6/6, 4/4, 8/8, 37/37, 14/14, 12/12, 10/10, 12/12 (unchanged).

**Not measured, said plainly.** How well the sorting rules guess on REAL facts: the made-up set
(`backend/topic_cases/`, 94 facts, and the 33 labelled facts of the self-test) is small, English, and
was written alongside the rules, so its numbers flatter them (Work, Family, Money, Projects filed right
in every case; Hobbies 9/14, Ideas 3/8, Health 11/12 - the misses are left Unsorted or filed under a
neighbour). Run `tools/topic_accuracy.py` on the PC, with your own lines added. The real embedding
model, the real re-ranker and the real learner model were not used (words only).

### LoCoMo "link two facts" questions (milestone 13, added 2026-09-28)

A separate test: `python backend/eval_memory.py --locomo` (on the PC, with
the real models). It asks 169 multi-hop questions over 5 of LoCoMo's long
made-up chats (`backend/fixtures/locomo_multihop.json`, CC BY-NC 4.0, test
data only). One stored item is one line of chat, not a saved fact, so these
numbers **can't be compared** with the table above or with published LoCoMo
scores. "Found all" = every chat line the question relies on came back.

| Date | Search | Where measured | Found any @5 | Found all @5 | nDCG@5 | Found all @10 |
|---|---|---|---|---|---|---|
| 2026-09-28 | plain | build machine, words only | 45.0% | 9.5% | 0.238 | 18.9% |
| 2026-09-28 | with the entity layer (how chat recall runs) | build machine, words only | 32.0% | 3.6% | 0.124 | 11.8% |
| 2026-09-28 | entity layer + "too common to help" cut (OFF by default) | build machine, words only | 42.6% | 8.3% | 0.218 | 18.9% |
| - | both, real models | **the PC - not run yet** | - | - | - | - |

**Worth knowing:** on this data, words only, the entity layer made every
number worse, in every one of the five chats. The cause was found by the
effectiveness audit (`docs/audit-2026-09-28/03-effectiveness.md`, 3.1): a
person named in most of the chat lines ("Caroline", in 291 of 419) brings
back only their newest lines as a third list, pushing the relevant ones out
of the top 5. A cut that skips a name linked to more than max(20, 5% of all
facts) is built, **switched off** (`JARVIS_MEMORY_ENTITY_COMMON_CUT=1`, or
`eval_memory.py --common-cut` for one run). With it on, words only, LoCoMo
went back up (above) and the main self-test (0/100/1,000 filler) was
unchanged. It stays off until the PC run shows no number getting worse
(`docs/UPDATE-AND-CHECK-2026-09-28.md` has the one-line command). This is
the baseline milestone 5 (multi-hop memory) has to beat.

### "Said again" as a tie-breaker (milestone 12, added 2026-09-28, OFF)

Switched on only with `JARVIS_MEMORY_SAID_AGAIN_TIEBREAK=1`. It reorders only
facts that scored exactly the same, putting the one said more often first;
it never adds, drops or hides a fact (`backend/README.md`, "Said again").

| Date | Where measured | Result |
|---|---|---|
| 2026-09-28 | build machine, words only, re-ranker off, 71 to 10,071 facts | **No change**: 0 questions reordered at every size, every number identical (recall@5 80.9% at 71 facts, 79.8% at 10,071). The 6 exact ties involving a repeated fact already had it first. |
| - | the PC, real models | **not run yet** - ties should be commoner with meaning search on, so only this run can say whether it helps. It stays off unless this run improves a number. |

