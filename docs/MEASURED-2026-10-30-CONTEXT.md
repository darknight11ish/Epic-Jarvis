# The context window on the owner's PC, measured (2026-10-30)

**The question was "raise the deployed context from 4,096 to 8K or 16K", which
the 2026-10-30 competitiveness audit calls "the single biggest capability gap"
and asks for as a measured Modelfile change.**

**The answer is that it is already 16,384, and 16,384 is measured safe on this
PC.** The 4,096 in `MODEL-TOPOLOGY.md` was true when it was written; the owner
has since set `OLLAMA_CONTEXT_LENGTH=16384` for his Windows user, and the
machine, not the repository, is what changed. Nothing was raised by this work,
because there was nothing left to raise inside the range the brief allowed.

**Which tree was read:** a worktree of `origin/main` at `171d28616`, branch
`feat/context-8k-2026-10-30`. Paths below are repository-relative. Everything
marked "measured" was read from this machine on 2026-10-30 between 00:05 and
00:45 PDT, except the 32,768 and 65,536 rows, which were measured in a
follow-up run on the same machine between 01:51 and 01:55 PDT with the same rig
and method. Nothing was deployed by either run.

---

## 1. What is actually deployed

Four independent readings agree, and none of them is a document:

| what was read | what it said |
|---|---|
| `[Environment]::GetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH','User')` | **`16384`** |
| `/api/ps` on the main Ollama (11434) | `qwen3.5:9b … context_length 16384` |
| `/api/ps` on the everyday lane (11436) | `jarvis-primary:latest … context_length 16384` |
| the runner's own command line (`Get-CimInstance Win32_Process`) | `-c 16384` |

The same user environment holds the other two settings `MODEL-TOPOLOGY.md`
already asks for, also measured: `OLLAMA_KV_CACHE_TYPE=q8_0` and
`OLLAMA_KEEP_ALIVE=-1`. The runner line shows both taking effect:
`--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn auto`, and the log says
`enabling flash_attn since it is required for quantized V cache`.

**Which model the live chat uses.** `%USERPROFILE%\.openjarvis\model-state.json`
has `"current": "qwen3.5:9b"`, and the last recorded turn in
`%USERPROFILE%\.openjarvis\speed.jsonl` (2026-10-29 18:21, in the running HUD)
is `qwen3.5:9b`, 1,742 prompt tokens, **100% GPU**, **39.01 tokens/s**. The
everyday lane is port **11436** (`OLLAMA_URL` in the same user environment;
`jarvis_model_lanes.py:177` in the live backend). So the deployed model is
`qwen3.5:9b`, not `jarvis-primary` and not `qwen3:8b`.

**What the repository says, and why it is stale.** `docs/MODEL-TOPOLOGY.md`
line 54 said *"The deployed context is 4096 tokens unless `jarvis-primary` … is
the model loaded, and nothing in the request chooses it."* The second half is
still exactly right - a chat turn posts to Ollama's OpenAI-compatible endpoint,
which has no field for context size - but the size is no longer 4,096. It is
16,384, set by the environment variable, which is one of the two routes that
page's own Setup section describes (the other is the Modelfile). **A fresh
install without that variable still gets 4,096**, which is what the old
paragraph describes and why it is kept below.

---

## 2. How it was measured

- **Machine:** Windows 11, NVIDIA driver 617.42; RTX 2060 12 GB as GPU 0 (no
  monitor, holds the model) and RTX 2080 SUPER 8 GB as GPU 1 (the monitor);
  both compute capability 7.5. Ollama **0.40.12**.
- **Method:** `POST /api/generate` with a per-request
  `options: {num_ctx, num_predict, num_batch: 512}`, `stream: false`,
  `think: false`, `temperature: 0`. That changes only what is loaded for the
  probe; it writes no model, changes no Modelfile and touches no service.
- **Where:** the main Ollama on **11434**, against `qwen3.5:9b`. **The
  everyday lane on 11436 was not asked to generate anything and its resident
  model was not changed** - it is the owner's live lane.
- **Prompt length:** filler numbered lines, sized by `chars × 0.2422 = tokens`.
  That ratio was calibrated from one 12,052-character prompt that Ollama's own
  `prompt_eval_count` reported as 2,919 tokens, and every later run confirms it:
  the three ladder prompts came back as **3,100 / 7,197 / 15,391** tokens
  against targets of 3,000 / 7,000 / 15,000. The measured counts are quoted
  everywhere below; the estimate was only used to build them.
- **Cold vs warm:** the first request at a size loads the model (cold); the
  second reuses it and Ollama's prompt cache (warm). Each size was run twice.
- **The 32K/64K follow-up kept the same rig and request shape.** Prompt targets
  were 30,000 and 60,000 tokens (122,104 and 242,604 characters) and came back
  as **30,329** and **60,227**. Each prompt carried a marker at the very start
  and one at the very end, and asked for both markers plus a 200-line count, so
  the decode rate was measured over 300 tokens rather than a two-token answer.
  A 16,384 control run (1,046-token prompt) was made afterwards to see the
  card layout at the deployed size, and it left 11434 holding the model at
  16,384.
- **TTFT** is `total_duration - eval_duration`, straight from Ollama's own
  nanosecond fields, so it includes the load when there is one.
- **VRAM** is `nvidia-smi` read immediately after each response, while the
  model was still resident.

---

## 3. The numbers

`qwen3.5:9b`, RTX 2060 12 GB, `num_batch` 512. Two runs per size; the median is
of those two, so it sits between one cold and one warm run. The 4,096 / 8,192 /
16,384 rows are the original ladder, all on the 2060 alone; the 32,768 and
65,536 rows are the follow-up, and Ollama spread those over both cards (why is
below).

| `num_ctx` | prompt tokens (measured) | loaded? | on card | TTFT cold | TTFT warm (cache hit) | median TTFT | prefill tok/s cold | decode tok/s | model size | card after load (used / free) |
|---|---|---|---|---|---|---|---|---|---|---|
| **4,096** | 3,100 | yes | 100% GPU, 33/33 layers | 31.42 s | 0.30 s | 15.86 s | 1,211 | 41.5 (984 tok) | 5.54 GB (5.16 GiB) | 8,007 / 4,055 MiB |
| **8,192** | 7,197 | yes | 100% GPU | 31.01 s | 0.28 s | 15.65 s | 1,256 | 43.0 (512 tok) | 5.62 GB (5.23 GiB) | 8,079 / 3,983 MiB |
| **16,384** | 15,391 | yes | 100% GPU | 38.16 s | 0.47 s | 19.31 s | 1,202 | 38.3 (981 tok) / 43.0 (512 tok) | 5.80 GB (5.40 GiB) | 8,247 / 3,815 MiB |
| **32,768** | 30,329 | yes | 100% GPU, 33/33 layers, spread over both cards | 41.83 s | 0.31 s | 21.07 s | 1,885 | 33.5 (300 tok) / 31.4 (300 tok) | 6.73 GB (6.27 GiB) | 2060: 5,711 / 6,351 MiB; 2080 SUPER: 5,343 / 2,645 MiB |
| **65,536** | 60,227 | yes | 100% GPU, 33/33 layers, spread over both cards | 58.54 s | 0.49 s | 29.51 s | 1,571 | 27.4 (300 tok) / 25.7 (300 tok) | 7.84 GB (7.30 GiB) | 2060: 6,309 / 5,753 MiB; 2080 SUPER: 5,805 / 2,183 MiB |

Read the rows together and the important number is the last column:

- **Up to 16,384 the 12 GB card never comes close to full.** At 16,384 the
  everyday model holds 5.40 GiB and the card still had **3,815 MiB free**.
  Nothing spilled to the processor at any size: the runner's log reported
  `offloaded 33/33 layers to GPU` at every size (33 is this model's own layer
  count - it has 32 blocks plus the output layer), and `/api/ps` reported every
  byte of the model resident in VRAM (`size_vram` equal to `size`).
- **16,384 costs 240 MiB more than 4,096**, because `qwen3.5:9b` keeps a cache
  only for its 8 full-attention layers (the other 24 are recurrent and keep
  none). That is why the 4K-to-16K ladder is nearly flat in memory.
- **Decoding is flat up to 16,384 and falls above it**: 41-43 tokens/s at the
  three smaller sizes (the live turn recorded 39.01 on 2026-10-29), then 33.5
  at 32,768 and 27.4 at 65,536.
- **Prompt reading is the price, and it grows with the prompt**: 1,211 / 1,256
  / 1,202 tokens/s on one card for the ladder, so a 15,000-token prompt costs
  about 12.8 s of reading before the first token against 2.6 s for a
  3,000-token one. The bigger rows read at 1,885 and 1,571 tokens/s, which is
  faster, most likely because two cards were reading, so those two do not
  compare directly.
- **Cold load is 20-29 s for this model** (5.8 GB of weights, including the
  0.86 GiB vision projector), and it happens after a restart or a model
  switch, not on every turn. The warm rows are what a turn pays once the model
  is resident; the "cache hit" note matters because a real new turn re-reads
  only its new text.

### What 4,096 did to a long conversation

Two markers were put in one prompt, one at the very start and one at the very
end, and the model was asked to list the markers it could see.

| window | prompt sent | Ollama's own prompt count | what the model saw |
|---|---|---|---|
| **4,096** | ~5,019 tokens | **2,050** | only `MARKER-END-OMEGA` |
| **16,384** | ~15,022 tokens | **15,409** | `MARKER-BEGIN-ALPHA` **and** `MARKER-END-OMEGA` |

The runner's log records the 4,096 request arriving as `task.n_tokens = 2050` -
half the window - so the cut happened before the model ever saw the text. **At
4,096 a long conversation does not truncate its answer; it silently loses its
beginning.** At 16,384 the whole 15,409-token prompt was read.

### What the answer cap does at the window's edge

The PC asks for `max_tokens` 1,024 when an app asks for nothing. That allowance
comes out of the same window, and the window wins:

| window | prompt tokens | answer tokens requested | answer tokens produced | runner's last line |
|---|---|---|---|---|
| **4,096** | 3,112 | 1,024 | **984** | `n_tokens = 4095, truncated = 1` |
| **16,384** | 15,403 | 1,024 | **981** | `n_tokens = 16383, truncated = 1` |

Both stopped exactly at the window edge (3,112 + 984 = 4,096; 15,403 + 981 =
16,384). So a 15,000-token prompt at 16,384 leaves **981 of the 1,024 tokens**
the app asked for - the same proportion of loss the old 4,096 window gave a
3,000-token conversation. The lesson is not "16K removed the cap"; it is that
the cap is a *ceiling*, and the room left in the window is the real limit.

### What the bigger windows would change (32,768 and 65,536, measured 2026-10-30)

**They work, and they are not free.** Both sizes loaded every layer on a GPU
(33/33), neither spilled to the processor, neither failed, and both markers -
the one at the very start and the one at the very end of a 30,329- and a
60,227-token prompt - came back in the answer on the cold run and on the warm
one. The memory arithmetic was right: a bigger window fits. What it
costs is measurable:

- **A cold first token takes longer, and it is most of a minute at 64K**:
  41.8 s at 32K and 58.5 s at 64K, against 38.2 s for the 16K row's 15,391
  tokens (each includes the load: 25.6 s at 32K, 19.9 s at 64K, and 25-29 s for
  the 16K row). Reading the prompt itself ran at 1,885 tokens/s at 30K and
  1,571 at 60K.
- **Decoding is slower.** The same 300-token answer decoded at 33.5 tokens/s
  at 32K and 27.4 at 64K (warm: 31.4 and 25.7), against **41.9 tokens/s** in a
  16,384 control run made minutes later on the same machine. A 64K window is
  about a third slower per generated token.
- **The model was spread over both cards.** The runner's own log assigns
  **1,647.73 MiB** of model buffer, plus cache and compute, to the 2080 SUPER -
  the card driving the monitor - and **3,164.52 MiB** plus cache and compute to
  the 2060. That is about 2.2 GiB of the monitor card at 32K and 2.7 GiB at
  64K. After the 32K run the cards read 2060 5,711 / 6,351 MiB and 2080 SUPER
  5,343 / 2,645 MiB; after 64K, 6,309 / 5,753 and 5,805 / 2,183.
- **Why it split is room at request time, not the window size alone.** The 32K
  request arrived with the 2060 holding its old 16,384 model and about 2.5 GiB
  of the owner's everyday lane, so only **3,815 MiB** was free there against a
  32K allocation of 6,119 MiB (the runner's own buffer lines added up). The 64K
  request arrived with the 32K model still on the card: **6,351 MiB** free
  against 7,175 MiB needed. The 16,384 control arrived with 5,753 MiB free and
  about 5,279 MiB needed, so it stayed on the 2060 alone (`--split-mode none
  --main-gpu 0`). The runner's log then shows **11,213 MiB free** on the 2060
  after the old model unloaded - enough for the 64K allocation by that
  arithmetic - but whether Ollama would keep 64K on one card with the 2060
  otherwise empty was not run.
- **The 16,384 control run itself:** 1,046-token prompt, 23.7 s to first token
  (22.6 s of it the load), 41.9 tokens/s over a 32-token answer, all 33 layers
  on the 2060, and it left the machine in the state it was found in.

**What this means for the setting.** 16,384 stays the number to deploy. The
bigger windows are *safe* - no out-of-memory error, no CPU offload, no lost
marker - but they are measurably **worse in practice** on this PC: a fifth to a
third less decode speed (33.5 and 27.4 against 41.9 tokens/s), a cold first
token after nearly a minute, and, under the memory conditions the machine was
actually in, 2.2-2.7 GiB of the monitor card's memory. Safe and no worse is
what would justify raising it; this is safe and worse, so it is not
recommended, and nothing was raised.

---

## 4. What changed in the repository, and what did not

**Nothing in the repository can set the deployed context.** The variable lives
in the owner's Windows user environment (`HKCU\Environment`), and the brief for
this work said not to invent a repository knob for it. So the repository change
is the truth about the machine:

- `docs/MEASURED-2026-10-30-CONTEXT.md` - this document.
- `docs/MODEL-TOPOLOGY.md` - the "thing that is wrong right now" section now
  states the deployed 16,384 with the measurement, keeps the ladder explanation
  (what a fresh install still gets), and the Setup section now names
  `OLLAMA_CONTEXT_LENGTH` beside the two settings it already named.
- `backend/jarvis-primary.Modelfile` - the comment that said "the deployed
  context today is 4096 tokens" now says what is measured. **No `PARAMETER`
  line changed**: it already carried `num_ctx 16384`, and 16,384 is what the
  measurement supports.
- `docs/JARVIS-API.md` and `docs/ARCHITECTURE.md` - the two other sentences
  that still called the default 4,096 now say what is measured: a model whose
  own Modelfile names no `num_ctx`, on a PC where nothing sets it.
- `docs/README.md` - the document count, by one.
- `changelog.d/` and `decisions.d/` - one bullet each.
- `docs/CLAIMS.tsv` - one row recording the measured figure.

**What was deliberately not done:** no `ollama pull` or `rm`, no `ollama
create`, no Modelfile parameter change, no service restart, no configuration
write, and nothing was generated on the live lane (11436) - its `/api/ps` was
read twice to record which model it holds, and nothing there was changed.

**This follow-up changed three files and nothing else:** the two rows and the
new subsection in this document, the one-paragraph outcome in
`docs/MODEL-TOPOLOGY.md`, and the second row in `docs/CLAIMS.tsv`. No setting,
model, Modelfile or service was touched, and 11434 was left holding the model
at 16,384, the context it was found with.

---

## 5. The live setting: where it is, how to check it, how to undo it

This is for a fresh install, a new PC, or an undo. It is all outside the
repository; a run of these commands is what the current machine already had.

**Check it (read-only, one line):**

```powershell
[Environment]::GetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH','User'); (Invoke-RestMethod http://127.0.0.1:11434/api/ps).models | ForEach-Object { "$($_.name) ctx=$($_.context_length)" }
```

The first value is the setting; the second line is what the running server is
actually using. If they disagree, the server was started before the variable
was set.

**Set it to the measured-safe 16,384:**

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH','16384','User'); Write-Host 'Saved for your Windows user. Quit Ollama from the tray and start it again.'
```

Then quit Ollama (right-click its icon by the clock, **Quit Ollama**) and start
it again. The variable is read by the server when it starts, so nothing changes
until that restart. The everyday lane's own Ollama (11436) is started by
Jarvis, and it inherits the same user environment when it next starts.

**Undo (back to Ollama's own choice, which is 4,096 on this model):**

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH',$null,'User'); Write-Host 'Undone. Quit Ollama and start it again.'
```

**Why the number is 16,384 and not more.** It is the largest size that is
also no worse in practice. 32,768 and 65,536 were measured on 2026-10-30
(§3): both fit and both keep the whole prompt, but decode falls from 41.9 to
33.5 and 27.4 tokens/s, a cold 60,227-token prompt takes 58.5 s to its first
token, and in the memory conditions measured both sizes spread the model over
both cards. The cache grows by only about 240 MiB per 12,288 tokens, so memory
is not the obstacle; throughput and the monitor card are.

---

## 6. What was NOT measured

A skipped measurement is never a pass. These are open:

- **32,768 and 65,536 are no longer on this list**: both were measured on
  2026-10-30 between 01:51 and 01:55 PDT, and both are recorded in §3. What is
  still open *about them* is the next three bullets.
- **32K/64K with the 2060 free at load time.** The two runs were spread over
  both cards because the 2060 did not have enough free room at the moment each
  was requested - its own previous model and the owner's everyday lane were
  using it. Whether Ollama would keep either size on the 2060 alone when the
  card is free is inferred from the log's free-memory line and the buffer
  sizes; it was not run. The 11436 lane was deliberately not disturbed to
  create that condition.
- **32K/64K in real use.** Only `/api/generate` was exercised, once cold and
  once warm at each size. The GUI, the phone, the voice lane and a multi-turn
  conversation were not driven at either size.
- **Sustained use**: one request at a time, not a day of conversation. Whether
  Windows pages the model out under real multi-hour use was not observed, at
  16K or at the bigger sizes.
- **The GUI, the phone, the voice lane and multi-turn behaviour** were not
  driven. Only `/api/generate` was exercised.
- **The 2080 SUPER (8 GB) lane** was not measured for this model; the everyday
  model runs on the 2060. The second-card lanes on 11435 were not started or
  measured. (The 2080 SUPER did hold part of the model during the 32K/64K
  runs, because Ollama spread it there - that is not a measurement of the
  11435 lane.)
- **`qwen3:8b` / `jarvis-primary` at 8,192** were not measured as a ladder.
  `jarvis-primary` was observed loaded at 16,384 (6,278,736,772 B, 5.85 GiB),
  and one `qwen3:8b` request at 4,096 was used to calibrate the tokenizer; that
  is all.
- **The 196,608-token everyday lane** that some live modules describe
  (`jarvis_power_switch.py:59`, `jarvis_big_coder.py:129`) is **not what is
  running**: the server on 11436 was started plainly and reports 16,384. A
  server started with that setting was not measured.
- **Decode rate beyond 512-984 tokens**, and the exact shape of the prompt cut
  at 4,096 beyond "it kept 2,050 of ~5,019 and lost the start".

**What the measurement itself changed on the machine**, so nobody has to guess:
the main Ollama (11434) had a stale `qwen3:8b` loaded at 16,384 from an earlier
measurement tool; it was unloaded so the card could hold one model, and 11434
now holds `qwen3.5:9b` at 16,384 - the deployed model at the deployed context.
The everyday lane on 11436 was not asked anything, but its resident
`jarvis-primary` was paged out of VRAM by the probes and will load again on its
next use, exactly as it would after any model switch. No setting, file, model
or service was changed.

**The 32K/64K follow-up then reloaded 11434's model at 32,768, at 65,536 and
finally at 16,384 again**, so 11434 holds `qwen3.5:9b` at 16,384 now - the model
and context it was found with. The 11436 lane was still never asked anything;
its resident model's VRAM was paged out while the bigger models loaded and came
back afterwards (`/api/ps` on 11436 still reports `jarvis-primary:latest` at
16,384). One intermittent runner warning, `llama-server GPU discovery watchdog
timed out`, appeared on some loads (it did on the earlier 00:30 load too); each
load still reported `offloaded 33/33 layers to GPU` and every request returned
an answer. No setting, file, model or service was changed by this follow-up.

---

## 7. The one decision left for the owner

None is needed to keep 16,384 - it is already deployed and measured safe. The
question of going further has now been measured too (§3), so the choice is
informed rather than open:

- **Keep 16,384** (recommended). Measured safe, leaves the monitor card alone,
  38-43 tokens/s at the deployed size.
- **Deploy 32K or 64K anyway.** It is measured to work: 100% GPU, both ends of
  a 30K/60K prompt kept. Decode is a fifth to a third slower, a cold first
  token takes 42-59 s, and 2.2-2.7 GiB of the monitor card's memory is used in
  the conditions measured. Nothing was switched on by this work.
