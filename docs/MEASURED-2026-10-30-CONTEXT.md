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
00:45 PDT; everything else says so instead of being guessed.

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
  everyday lane on 11436 was not probed and its resident model was not
  changed** - it is the owner's live lane.
- **Prompt length:** filler numbered lines, sized by `chars × 0.2422 = tokens`.
  That ratio was calibrated from one 12,052-character prompt that Ollama's own
  `prompt_eval_count` reported as 2,919 tokens, and every later run confirms it:
  the three ladder prompts came back as **3,100 / 7,197 / 15,391** tokens
  against targets of 3,000 / 7,000 / 15,000. The measured counts are quoted
  everywhere below; the estimate was only used to build them.
- **Cold vs warm:** the first request at a size loads the model (cold); the
  second reuses it and Ollama's prompt cache (warm). Each size was run twice.
- **TTFT** is `total_duration - eval_duration`, straight from Ollama's own
  nanosecond fields, so it includes the load when there is one.
- **VRAM** is `nvidia-smi` read immediately after each response, while the
  model was still resident.

---

## 3. The numbers

`qwen3.5:9b`, RTX 2060 12 GB, `num_batch` 512. Two runs per size; the median is
of those two, so it sits between one cold and one warm run.

| `num_ctx` | prompt tokens (measured) | loaded? | on card | TTFT cold | TTFT warm (cache hit) | median TTFT | prefill tok/s cold | decode tok/s | model size | card after load (used / free) |
|---|---|---|---|---|---|---|---|---|---|---|
| **4,096** | 3,100 | yes | 100% GPU, 33/33 layers | 31.42 s | 0.30 s | 15.86 s | 1,211 | 41.5 (984 tok) | 5.54 GB (5.16 GiB) | 8,007 / 4,055 MiB |
| **8,192** | 7,197 | yes | 100% GPU | 31.01 s | 0.28 s | 15.65 s | 1,256 | 43.0 (512 tok) | 5.62 GB (5.23 GiB) | 8,079 / 3,983 MiB |
| **16,384** | 15,391 | yes | 100% GPU | 38.16 s | 0.47 s | 19.31 s | 1,202 | 38.3 (981 tok) / 43.0 (512 tok) | 5.80 GB (5.40 GiB) | 8,247 / 3,815 MiB |

Read the three rows together and the important number is the last column:

- **The 12 GB card never comes close to full.** At 16,384 the everyday model
  holds 5.40 GiB and the card still had **3,815 MiB free**. Nothing spilled to
  the processor: the runner's log reported `offloaded 33/33 layers to GPU` at
  every size (33 is this model's own layer count - it has 32 blocks plus the
  output layer), and `/api/ps` reported every byte of the model resident in
  VRAM (`size_vram` equal to `size`).
- **16,384 costs 240 MiB more than 4,096**, because `qwen3.5:9b` keeps a cache
  only for its 8 full-attention layers (the other 24 are recurrent and keep
  none). That is why the ladder is nearly flat in memory.
- **Decoding does not slow down with context**: 41-43 tokens/s at every size,
  the same as the live turn's 39.01 tokens/s recorded on 2026-10-29.
- **Prompt reading is the price, and it is linear**: 1,211 / 1,256 / 1,202
  tokens/s, so a 15,000-token prompt costs about 12.8 s of reading before the
  first token, against 2.6 s for a 3,000-token one.
- **Cold load is 25-29 s for this model** (5.8 GB, including the 0.86 GiB
  vision projector), and it happens after a restart or a model switch, not on
  every turn. The warm rows are what a turn pays once the model is resident;
  the "cache hit" note matters because a real new turn re-reads only its new
  text.

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
write, and nothing on the live lane (11436) was probed.

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

**Why the number is 16,384 and not more.** It is the largest value this
measurement covered, and the brief for this work stopped there. The numbers
above suggest more is possible - the cache grows by about 240 MiB per 12,288
tokens for this model, and the card had 3.8 GiB free - but **32K and 64K were
not measured**, so they are not recommended here.

---

## 6. What was NOT measured

A skipped measurement is never a pass. These are open:

- **32,768 and 65,536** - not run at all. The memory arithmetic says they
  should fit; the arithmetic is not a measurement.
- **Sustained use**: one request at a time, not a day of conversation. Whether
  Windows pages the model out under real multi-hour use was not observed.
- **The GUI, the phone, the voice lane and multi-turn behaviour** were not
  driven. Only `/api/generate` was exercised.
- **The 2080 SUPER (8 GB) lane** was not measured for this model; the everyday
  model runs on the 2060. The second-card lanes on 11435 were not started or
  measured.
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

---

## 7. The one decision left for the owner

None is needed to keep 16,384 - it is already deployed and measured safe. If
the question is whether to go further, that is a new work block, because
nothing above measures it:

- **Keep 16,384** (recommended). Measured safe, costs 3,815 MiB of free VRAM,
  38-43 tokens/s.
- **Try 32K or 64K first, as a measurement, before deploying it.** The cache is
  small enough that it looks possible; the card has 3.8 GiB free at 16K.
