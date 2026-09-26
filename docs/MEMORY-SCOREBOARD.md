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

What is not known yet, and waits for the PC run:
- **Whether the re-ranker helps at all.** On the build machine it could only
  run as a word-overlap stand-in, which proves that it is wired in, not that
  it helps. It is switched on today; see the open question in
  `docs/OWNER-QUESTIONS-2026-09-27.md`.
- **How well the real 8B model picks facts out of a conversation.** The
  learner cases above use a stand-in for the model's one judgement call (is
  this a sensitive topic?). `--learner-model` runs the real one.
