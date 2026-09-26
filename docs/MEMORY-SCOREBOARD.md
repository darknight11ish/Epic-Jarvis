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

It takes about 5-15 minutes. The first run downloads the re-ranker model once
(about 80 MB). None of your data is sent anywhere. When it finishes, it opens
the `jarvis-memory-eval` folder in your home folder
(`C:\Users\pcadmin\jarvis-memory-eval`). Send back the `.md` file in that
folder, and its numbers go in the table below.

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
