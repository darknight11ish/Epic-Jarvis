# Model tryouts

Two tools that try other AI models against the ones Jarvis uses now, on your
PC, and say plainly whether each is worth switching to. **They never switch
anything.** Jarvis keeps its chat model (`jarvis-primary`) and its memory
search models until you decide otherwise. You chose this on 2026-09-28; the
candidates come from the research audit (`docs/RESEARCH-AUDIT-2026-09-28.md`,
section 6).

Each verdict follows a rule written down **before** anything was measured,
so a lucky number cannot move the goalposts.

Run every line below from this repository's folder (the one with `backend`
and `tools` in it). Change the `JARVIS_BACKEND` folder if your Jarvis lives
somewhere else.

## 1. Chat models (overnight)

Tries `lfm2.5:8b`, `granite4.2:8b`, `granite4.2:3b` and `qwen3.5:4b` against
`jarvis-primary`. Paste this one line when you do not need Jarvis for the
night - it takes **about 6 to 11 hours**, and Jarvis answers slowly or not
at all until it ends:

```powershell
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 tools\model_tryout\chat_tryout.py --pull; Write-Host "Results saved in $env:USERPROFILE\jarvis-model-tryout (the newest chat-... folder, file results.txt)"
```

What it does, for each model:

1. Downloads it if it is not here yet (`--pull`; about 3-5 GB each).
2. Wraps it the way `jarvis-primary` is wrapped: `jarvis-primary`'s own
   rules (its SYSTEM block, word for word), 16,384 tokens of conversation,
   and the same batch size (512) that keeps an 8 GB card from spilling. The
   sampling values (how adventurous its word choice is) are the ones the
   model's own download sets - the closest thing to the maker's advice the
   PC can read - and the file says so. It then makes it as
   `jarvis-cand-<name>` (`ollama create`).
3. Times it: the 1st request after loading, then the 2nd and 3rd (one known
   bug makes the first one slow on this kind of card), each with Jarvis's
   rules and tool list in front, like a real question. Words per second, and
   how much of the model fits on the graphics card.
4. Runs the tool test three times (`tools/tool_eval`) and keeps the worst.
5. Runs the learner test (does it pick the right facts out of a chat).

**The verdict.** "Worth trying" = its tool test is no more than 10 points
below `jarvis-primary`'s (or better), AND its learner test is not lower.
Anything else is "not worth it", with the reason. Speed and "on card" are
shown, not judged - read them yourself: "On card" under 100% means part of
the model runs on the processor, which is much slower.

At the end it deletes the `jarvis-cand-*` models it made (`--keep` keeps
them) and loads `jarvis-primary` back onto the card. Stopping it with Ctrl+C
cleans up the same way. If the PC crashed mid-run, this removes what was
left: `py -3 tools\model_tryout\chat_tryout.py --clean`

It refuses to start while the graphics card is busy (Jarvis answering, a
game). Other options: `--quick` (one tool-test run, about a third of the
time), `--models qwen3.5:4b` (only that one), `--jarvis-sampling` (give
every model Jarvis's own 0.7 / 0.8).

**Send back** `results.txt` from the newest `chat-...` folder in
`C:\Users\pcadmin\jarvis-model-tryout`. Switching to a "worth trying"
model is a separate decision, made later with an approval card, like any
model switch.

## 2. Memory search models

Two kinds of model help Jarvis find a saved fact. The **meaning model**
turns facts and questions into numbers, so "what should I cook?" finds
"Owner is vegetarian" (today: `BAAI/bge-small-en-v1.5`). The **re-ranker**
reads the question with each of the top facts and puts the best first
(today: `Xenova/ms-marco-MiniLM-L-6-v2`, switched off until it is shown to
help).

Tried here: the meaning models `Qwen/Qwen3-Embedding-0.6B-Q` and
`google/embeddinggemma-300m`, and the re-rankers
`Xenova/ms-marco-MiniLM-L-12-v2` and `jinaai/jina-reranker-v1-turbo-en`.

### 2a. First, the newer fastembed (only for the two meaning models)

The two new meaning models need **fastembed 0.8.1** (fastembed is the
library that runs these models on the processor). Jarvis's locked package
list (`backend/requirements.lock`) still says 0.8.0, on purpose: it only
takes a release once it is 7 days old, so a hijacked release has time to
be noticed, and 0.8.1 came out on 22 September 2026 - it is old enough from
**30 September 2026**. Until the list is remade, this one line installs just
fastembed 0.8.1 (nothing else changes; the file is checked against its
published fingerprint first, and 0.8.1 asks for exactly the same other
packages as 0.8.0):

```powershell
Set-Content -Path "$env:TEMP\fastembed-0.8.1.txt" -Value 'fastembed==0.8.1 --hash=sha256:b4f4043080af36ee820d22d2d3034df635c1a8b9764e5d2a642bc7aeb1d0e749'; py -3 -m pip install --no-deps --require-hashes -r "$env:TEMP\fastembed-0.8.1.txt"; Write-Host "Done. fastembed 0.8.1 is installed for py -3 (the list it came from is in your TEMP folder)."
```

Without it, the tryout still runs the re-rankers and says which models it
skipped. `apply-patches.ps1` leaves 0.8.1 in place (it installs from
`requirements.txt`, which names no version).

### 2b. The tryout

About **1 to 3 hours** (longer the first time: each model downloads once,
about 1.1 GB and 1.2 GB for the two meaning models). It uses made-up facts
in a temporary folder, never your memory, and the graphics card is not used,
so Jarvis keeps working (a little slower while it runs). **Run
`apply-patches.ps1` first**: the switches it uses are new in
`jarvis_memory.py`.

```powershell
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 tools\model_tryout\memory_tryout.py; Write-Host "Results saved in $env:USERPROFILE\jarvis-model-tryout (the newest memory-... folder, file results.txt)"
```

**The verdicts.** A meaning model is "worth trying" if, on the hardest test
(1,071 facts about the same things), each at its own best distance floor,
it finds the right fact at least 2 points more often than bge-small, brings
back no more wrong facts for questions memory cannot answer, no more old
versions, and one search takes at most 250 ms (a spoken answer waits for
it). A re-ranker "helps" if it adds at least 1 point of recall or 0.02 of
MRR (the right fact nearer the top), brings back no more old versions, and
finishes within 1.5 seconds (Jarvis does not wait longer). The results end
with ready-made rows for `docs/MEMORY-SCOREBOARD.md`.

### 2c. Switching for real - only after the tryout says so

Nothing above changes Jarvis. If you decide to switch, these are the
settings (each one line; quit Jarvis from the tray and start it again
afterwards):

- A meaning model - use the model's exact name and the distance floor the
  tryout printed for it:
  `[Environment]::SetEnvironmentVariable('JARVIS_MEMORY_EMBED_MODEL', 'Qwen/Qwen3-Embedding-0.6B-Q', 'User'); [Environment]::SetEnvironmentVariable('JARVIS_MEMORY_MAX_DISTANCE', '0.9', 'User'); Write-Host 'Saved. Quit Jarvis from the tray and start it again.'`
  **Jarvis then works out every saved fact's numbers again** with the new
  model - never a mix of old and new (the store notices the model changed,
  even when the numbers have the same length). Until that has finished,
  facts are still found by their words. A name the installed fastembed does
  not have is refused in plain words and bge-small is kept.
  **One thing the tryout does not measure:** the learner's "is this the same
  fact said twice?" check also compares facts with the meaning model, and
  its cut-off (`NEAR_DUP_MIN` in `jarvis_intake.py`) was set for bge-small.
  Another model scores closeness differently, so ask for that cut-off to be
  checked before switching for good.
  To undo: `[Environment]::SetEnvironmentVariable('JARVIS_MEMORY_EMBED_MODEL', $null, 'User'); [Environment]::SetEnvironmentVariable('JARVIS_MEMORY_MAX_DISTANCE', $null, 'User'); Write-Host 'Undone. Quit Jarvis from the tray and start it again.'`
  (Jarvis then works the numbers out again with bge-small.)
- A re-ranker: `[Environment]::SetEnvironmentVariable('JARVIS_MEMORY_RERANK_MODEL', 'Xenova/ms-marco-MiniLM-L-12-v2', 'User'); [Environment]::SetEnvironmentVariable('JARVIS_MEMORY_RERANK', '1', 'User'); Write-Host 'Saved. Quit Jarvis from the tray and start it again.'`
  To undo: the same line with `$null` in place of each value.

## Test the tools without a model

`python3 backend/test_model_tryout.py` runs both tools against a stand-in
Ollama and made-up results (no model, no network). It proves the rules,
the clean-up and the refusals - it says nothing about which model is
better. Only the runs on the PC can say that.
