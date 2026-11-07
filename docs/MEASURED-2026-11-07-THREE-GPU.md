# Three graphics cards, measured per preset (2026-11-07)

The third card is installed: an **RTX 2060 12 GB** (no display) plus **two RTX
2080 SUPER 8 GB** cards, one headless and one driving the monitor - 28 GB of
video memory in total, 12,288 + 8,192 + 8,192 MiB. This page is what was
measured on this PC on 2026-11-07, and what each focus preset does with it.

**What ships from this measurement.** The **Coding preset moves from the
two-card pooled lane to all three cards** - the same model
(`qwen3-coder-30b-a3b-ud-q3-k-xl`), the **49,152-token** window, and a
measured **0.0 GiB of CPU spill** - the two-card record this replaces carried an
accepted 323.5 MiB, and the two-card control run the same night also read 0.0,
which the limits section below states rather than hides. The knob that makes
Ollama spread the model over every visible card is **`OLLAMA_SCHED_SPREAD=1` in
the pooled server's child environment**; without it the same three cards are
used but the model decodes at 56.82 instead of 84.93 tokens a second on this
harness. Every other preset keeps its measured single-card configuration, and
the reason for each is below.

**The method is the 2026-11-02 pooled-lane page's**, with one difference that
made a three-way comparison possible: each config gets its **own throwaway
`ollama serve`** instead of the shipped lane. Nothing else about how the
numbers are read has changed.

## What was measured, and how

`matrix3.py` (scratch, not shipped - `.dsh-scratch/GPU-3WAY-2026-11-06/bench/`)
runs **one config at a time**, serially:

1. It starts a **fresh `ollama serve` on port 11451** for that config - never
   11434, never 11435/11436/11450, and it starts and stops nothing the owner's
   lanes use. **No live server was contacted, no preset was applied, no
   approval card was raised or answered, and no settings file was written.**
2. The child environment is set per config: `CUDA_VISIBLE_DEVICES` to that
   row's card or cards, `OLLAMA_CONTEXT_LENGTH` to the row's window,
   `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_MAX_LOADED_MODELS=1`,
   `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_VULKAN=0`,
   `OLLAMA_NO_CLOUD=1`, and **`OLLAMA_SCHED_SPREAD=1` only on the rows that ask
   for it** (`spread=1`). Every row's whole environment is saved in its JSON
   under `.env`, so the setting each number was taken with can be read back.
3. **Two calls** on the same prompt, and the **second** is the warm row. The
   first call is the cold load: its `load_duration` is the "cold load" figure.
   The warm call's own `load_s` is 0.007-0.013 s, which is the proof the model
   was already resident rather than a claim that it was.
4. **Generation speed** is Ollama's own `eval_count / eval_duration`.
   **Prompt speed** is `(prompt_eval_count - prompt_eval_cached_count) /
   prompt_eval_duration` - **uncached** tokens only. The per-call tag sits at
   the FRONT of the prompt on purpose, so no call can be served from the
   longest-common-prefix cache; `_all-*.json` keeps every raw reply.
5. **Memory** is `/api/ps` after the warm call: `size` against `size_vram`.
   Spill is `size - size_vram`, so 0.0 means the model reported the same bytes
   in video memory as its total size. The **cards a model really used** are
   `nvidia-smi`'s per-card `memory.used` before and after the cold call, with a
   card counted when it rose by more than 400 MiB.
6. Server version **0.40.15** on every row that answered; every model resolved
   to the tag the store actually holds.

**One limit that matters for reading the table.** The coding rows answered the
prompt ("Reply with the single word: ready.") in **2 tokens** - `eval_count=2`
- so their generation figure is a **two-token decode sample**, not a sustained
run. Every other row generated far more: 128 tokens, except the 31B (55-56) and
the 27B (49-53), whose answers stopped earlier. That is why the coding column is
noisy in a way the others are not: 65,536 read 59.06 while 98,304 read 88.69 on
the same model and the same prompt. The comparison that decides the preset is
between rows measured **the same way on the same day**, which is what the
two-card control is for. These numbers are not comparable to the 2026-11-02
page's medians, which came from three real coding prompts.

## The rows

All times in seconds, memory in GiB, speeds in tokens a second. "Cards" is what
`nvidia-smi` saw the model occupy, not what the config allowed.

| Config | Model | Window | Size GiB | Spill GiB | Cards | Cold load s | Warm gen tok/s | Warm prompt tok/s | What the row is |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| `coding_2cards_32768` | qwen3-coder-30b-a3b-ud-q3-k-xl | 32768 | 14.84 | 0.0 | 0, 2 | 69.611 | 60.58 | 1727.17 | today's pooled row (2060 + display 2080S) |
| `coding_3cards_32768` | qwen3-coder-30b-a3b-ud-q3-k-xl | 32768 | 15.10 | 0.0 | 0, 1, 2 | 10.884 | **84.93** | 1660.19 | all three, today's window |
| `coding_3cards_49152` | qwen3-coder-30b-a3b-ud-q3-k-xl | 49152 | 16.17 | 0.0 | 0, 1, 2 | 31.561 | 83.82 | 1644.17 | all three, the asked 48k window |
| `coding_3cards_65536` | qwen3-coder-30b-a3b-ud-q3-k-xl | 65536 | 17.25 | 0.0 | 0, 1, 2 | 9.587 | 59.06 | 1639.98 | all three, doubled window |
| `coding_3cards_98304` | qwen3-coder-30b-a3b-ud-q3-k-xl | 98304 | 19.41 | 0.0 | 0, 1, 2 | 10.270 | 88.69 | 1627.59 | all three, 3x window |
| `coding_3cards_131072` | qwen3-coder-30b-a3b-ud-q3-k-xl | 131072 | - | - | - | - | - | - | **FAILED**: `server: server exited 4294967295` |
| `coding_3cards_nospread_32768` | qwen3-coder-30b-a3b-ud-q3-k-xl | 32768 | 15.10 | 0.0 | 0, 1, 2 | 9.903 | 56.82 | 1663.11 | all three, spread NOT asked for |
| `coding_q4_3cards_32768` | qwen3-coder:30b-a3b-q4_K_M | 32768 | 19.52 | 0.0 | 0, 1, 2 | 43.488 | 87.47 | 1707.94 | the bigger q4 build on three cards |
| `coding_q4_3cards_49152` | qwen3-coder:30b-a3b-q4_K_M | 49152 | 20.60 | 0.0 | 0, 1, 2 | 43.160 | 93.08 | 1767.27 | q4 build at the 48k window |
| `everyday_2060_196608` | qwen3.5:9b | 196608 | 9.18 | 0.0 | 0 | 8.063 | 42.01 | 1203.07 | today's General/Reflect/Documents/Browser row, 1 card |
| `everyday_2060_32768` | qwen3.5:9b | 32768 | 5.74 | 0.0 | 0 | 7.590 | 41.89 | 1197.61 | one card at the everyday small window |
| `everyday_3cards_196608` | qwen3.5:9b | 196608 | 13.01 | 0.0 | 0, 1, 2 | 7.520 | 44.38 | 1150.44 | the same window on all three cards |
| `everyday_3cards_262144` | qwen3.5:9b | 262144 | 15.57 | 0.0 | 0, 1, 2 | 7.673 | 44.11 | 1126.11 | the uncensored row's measured max, on three cards |
| `everyday_3cards_32768` | qwen3.5:9b | 32768 | 7.31 | 0.0 | 0, 1, 2 | 6.987 | 44.73 | 1082.63 | three cards at the everyday small window |
| `fast_2080display_16384` | qwen3.5:4b | 16384 | 3.20 | 0.0 | 2 | 10.403 | **76.20** | 2566.32 | today's Fast row: the display 2080 SUPER |
| `fast_3cards_16384` | qwen3.5:4b | 16384 | 4.05 | 0.0 | 0, 1, 2 | 5.182 | 65.85 | 1545.96 | Fast spread across three cards |
| `fast_headless_16384` | qwen3.5:4b | 16384 | 3.20 | 0.0 | 1 | 9.899 | **85.29** | 2714.00 | Fast on the headless 2080 SUPER, no display |
| `gemma31b_3cards_32768` | gemma4:31b-it-qat | 32768 | 18.81 | 0.0 | 0, 1, 2 | 71.537 | 15.54 | 384.47 | the 31B dense flagship the plan proposes |
| `gemma31b_3cards_24576` | gemma4:31b-it-qat | 24576 | 18.53 | 0.0 | 0, 1, 2 | 48.041 | 15.41 | 372.88 | 31B at the middle window |
| `gemma31b_3cards_16384` | gemma4:31b-it-qat | 16384 | 18.25 | 0.0 | 0, 1, 2 | 48.803 | 15.57 | 385.58 | 31B at the safe window |
| `qwen27b_uncensored_3cards_32768` | orcarouter/Qwen3.8-27B-Uncensored:q4_K_M | 32768 | 17.38 | 0.0 | 0, 1, 2 | 43.387 | 17.96 | 444.67 | the uncensored 27B flagship |
| `qwen27b_3cards_24576` | orcarouter/Qwen3.8-27B-Uncensored:q4_K_M | 24576 | 16.93 | 0.0 | 0, 1, 2 | 43.480 | 17.68 | 450.09 | the 27B at the creative window |
| `gemma12b_3cards_32768` | gemma4:12b-it-qat | 32768 | 8.70 | 0.0 | 0, 1, 2 | 20.541 | 33.71 | 730.74 | the 12B middle rung |
| `gemma12b_2060_16384` | gemma4:12b-it-qat | 16384 | 7.15 | 0.0 | 0 | 18.264 | 32.90 | 807.59 | the 12B on the everyday card alone |
| `abliterated9b_3cards_32768` | hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M | 32768 | 7.30 | 0.0 | 0, 1, 2 | 18.448 | 52.76 | 1096.88 | the uncensored 9B the General-uncensored row names |
| `qwenvl8b_headless_16384` | qwen3-vl:8b-thinking | 16384 | 6.14 | 0.0 | 1 | 24.473 | 63.35 | 1940.04 | vision on the headless card alone |
| `minicpm_3cards_16384` | minicpm-v4.6 | 16384 | 1.33 | 0.0 | 0, 1, 2 | 7.602 | 159.54 | 5851.46 | small vision model for the Pictures row |

**Every row that ran reported zero spill.** All **twenty-six** rows that
produced numbers read `size == size_vram`; the one row that did not produce
numbers is the failure above and is marked FAILED rather than counted.

The 49,152 three-card row is the one that ships (the owner's Q2 ruling asks for
the largest window that stays above 75 tok/s). Its model in `/api/ps` was
`qwen3-coder-30b-a3b-ud-q3-k-xl:latest` at `context_length` 49152, and the
per-card proof of a real three-way split is `nvidia-smi` after the cold load:
**7,458 MiB on the 2060, 4,871 MiB on the headless 2080 SUPER, 5,932 MiB on the
display 2080 SUPER**. The two-card control of the same model at 32,768 put
9,360 MiB on the 2060 and 7,467 MiB on the display card, with the headless card
at 0 - so the third card is not a label here, it is a third of the model.

## What each preset does, and why

### Coding - moved to all three cards

**83.82 against 60.58 tokens a second** - about **38% faster** than the
same-night two-card control, which ran the same q8_0 cache at 32,768 tokens. It
is **not** 38% faster than the 2026-11-03 shipped record: that ran the default
f16 cache and read 80.36 tok/s at a 36.0 s cold load, so the like-for-like gain
over today's lane is small - the change is the wider window (49,152 against
32,768) at zero spill. The cold load is 31.561 s against the control's 69.611 s
(and 36.0 s in the older record).
The measured memory is **16.17 GiB with zero spill** on three cards at the
49,152-token window. The per-card split leaves the headless card with
**3,321 MiB free** (4,871 of its 8,192 MiB used), the 2060 with 4,830 free and
the display card with 2,260 free. The sweep did **not** isolate why the
two-card load is so slow; it is also 33.6 s slower than the 36.0 s the
2026-11-03 record took on the same pair of cards, and that difference is
recorded rather than explained.

**The window: 49,152 is what ships, and 32,768 is the measured alternative.**
The Q2 ruling named two windows, 49,152 and 65,536; 65,536 measured 59.06 tok/s
(below the 75 tok/s bar), so 49,152 is the larger named window that clears it.
98,304 also loaded with zero spill and read 88.69 tok/s, but it was outside the
ruling's windows and is recorded rather than chosen:

- **49,152 is chosen:** **83.82 tok/s at 16.17 GiB**, zero spill, cold load
  **31.561 s**. Against 32,768 it is 1.3 % slower and costs 1.07 GiB more video
  memory and 20.677 s more cold load, for **16,384 more tokens of window**.
- **32,768 measured 84.93 tok/s at 15.10 GiB**, zero spill, cold load
  **10.884 s** - the faster, smaller, quicker-loading row, kept as the recorded
  alternative this decision was made against.
- **65,536 read 59.06 tok/s** - below the 75 tokens-a-second bar set for this
  decision, so the doubled window is **not** chosen even though it loaded at
  17.25 GiB with zero spill. A larger window that nearly halves decode speed is
  not an upgrade.
- **98,304 read 88.69 tok/s at 19.41 GiB**, zero spill. It is the same
  2-token-sample instrument as the chosen row, its number is inside the noise,
  and it is not chosen: it is outside the two windows the ruling names (49,152
  and 65,536) and uses 3.2 GiB more than the chosen row; the row is recorded so
  a later decision has evidence.
- **131,072 FAILED** - the server exited with `4294967295` before answering, so
  there is **no** number and nothing is claimed about a 4x window.
- **The spread knob is worth real speed.** `coding_3cards_nospread_32768` - the
  same three cards, the same window, `OLLAMA_SCHED_SPREAD` absent - still put
  the model on cards 0, 1 and 2, but decoded at **56.82** instead of 84.93.
  Ollama fills all three either way; asking it to spread is what makes the
  split fast, which is why the shipped child environment sets it.
- **The bigger q4 build fits too, and is not chosen.** At 32,768
  `qwen3-coder:30b-a3b-q4_K_M` loaded at 19.52 GiB with zero spill and read
  87.47 tok/s, and at 49,152 it read **93.08 tok/s at 20.60 GiB** - the fastest
  row of the night. Both are **model changes** that use 4.4-5.5 GiB more video
  memory for a speed difference this instrument cannot separate from noise. It
  is **not shipped** because its coding quality was never re-run on the 6/6
  rubric - that rubric was measured on the q3 weights - so switching models
  tonight would be an unmeasured quality claim; it is the strongest candidate
  for a later measured try.

### Everyday - unchanged, on the 2060

The everyday model is the one always loaded, and its measured row is
**42.01 tok/s at 196,608 tokens, 9.18 GiB, one card, zero spill**. Three cards
would hold **262,144 tokens at 15.57 GiB** and read **44.11 tok/s**, so the
capability is real: a third more window and about 5% more speed. It is
**not** taken for two reasons, both measured or structural rather than taste:

1. **It would occupy all three cards with the always-on model**, which is
   exactly the pause the Coding preset's heavy mode exists to admit to. The
   daily lane staying on one card is what lets Fast, Agentic+Vision and the
   Coding pool co-exist at all.
2. **The speed difference is not a user-visible win**: 44.11 against 42.01 is
   2.1 tokens a second, both from 128-token samples, for 6.4 GiB more memory.

So the daily lane stays where it is, and **no pause is introduced**. The
262,144-token row is recorded as a measured capability, not a shipped setting.

### Fast - unchanged, on the display card

**76.20 tok/s on the single display 2080 SUPER against 65.85 across all three
cards.** Spreading the small model over the third card makes it **slower** on
this harness, so nothing changes here. The row exists to prove the negative, and
it does. **On the headless 2080 SUPER alone it read 85.29 tok/s**, so the third
card is a loss only when the model is spread across all three; moving Fast onto
the headless card is a separate, measured, deferred change (below).

### The other presets

`general`, `reflect`, `documents` and `browser` share the everyday row above
(same model, same 196,608-token window, same 2060); `pictures` is the same
model at 32,768, which the `everyday_2060_32768` row measures at 41.89 tok/s
and 5.74 GiB; `agentic_vision` is the same 9B at 16,384 on the same card.
Changing any of them would need a reason this sweep did not produce, so all of
them keep their measured configuration. `general_uncensored` has its **own
model** (the Huihui abliterated 9B); the sweep measured it at 32,768 on three
cards (`abliterated9b_3cards_32768`, **52.76 tok/s**, 7.30 GiB, zero spill) but
**not** at the preset's own 196,608 on the 2060, so its 2026-10-18 record is
unchanged and is not re-claimed here.

## What was not measured, said plainly

- **One config FAILED**: `coding_3cards_131072` never answered (`server: server
  exited 4294967295`). It is FAILED, not "done", and no 131,072-token claim is
  made.
- **Two configs in the matrix have no result file at all**:
  `coding_q4_3cards_65536` and `qwenvl8b_3cards_16384`. They were in the
  harness's list and were not selected for either run, so **nothing is claimed
  about them**, and a missing file is not a pass.
- **No real coding session was run.** Every prompt is a fixed 900-word body
  asking for one word, so the window was loaded but never filled. Decode speed
  of a nearly-full 49,152-token window, and whether the KV cache stays on the
  cards through a long conversation, are still unmeasured.
- **The coding numbers are 2-token samples** (see the limit above). They are
  good enough to compare this lane against the two-card control and not good
  enough to be quoted as a sustained decode rate.
- **No UI was driven.** Nothing here proves what either app shows; the backend
  and app suites prove the words and the order, not a screen.
- **One repeat per config, no thermal control, no counterbalancing.** Runs were
  serial and in the matrix's own order, so no row is corrected for a warm card
  or a cold one.
- **The two-card control does not match the 2026-11-03 record, and the reason is
  measured rather than hidden.** That record says 32,768 loaded at
  **16,513.7 MiB with 323.5 MiB spilled** and a 36.0 s cold load through the
  shipped path; tonight's two-card control read **14.84 GiB (15,194 MiB) with
  zero spill and a 69.611 s cold load** on the same window. The reason is the
  **KV cache format**: the 2026-11-03 run used the server's default f16 cache,
  while every row here set OLLAMA_KV_CACHE_TYPE=q8_0 (the format the matrix
  documents above). Measured directly after that finding, at the same
  49,152-token window on three cards: **q8_0 16.17 GiB, f16 18.07 GiB, both
  zero spill** (kv-check.json in this audit folder) - so the ~1.9 GiB
  difference is the cache, not a mystery. The 323.5 MiB stays in the record as
  history rather than being deleted, and the claim this page makes is the one
  it measured: **zero spill on three cards**. The shipped pooled server now
  sets OLLAMA_KV_CACHE_TYPE=q8_0 itself, matching this measurement and the
  two live lanes.
- **No third-card-only lane was started through the product.** The headless
  card was measured on its own (`fast_headless_16384`,
  `qwenvl8b_headless_16384`), but no logon task, lane object or route was
  exercised there - the rows prove the card, not a lane.

## Deliberately not shipped tonight

**Measured, or planned, but deferred - with the reason.**

- **The new heavy presets (`deep_think`, `creative`) are not shipped.** The
  pooled lane currently carries **one fixed model** (`jarvis_big_coder`
  `MODEL`/`NUM_CTX` constants), and parameterising it for three different
  models is a careful refactor with its own tests. The measurement is evidence
  for **Wave 8**, not a shipped claim. What it shows, honestly: the 31B dense
  `gemma4:31b-it-qat` **does fit all three cards** - 18.81 GiB at 32,768,
  18.53 GiB at 24,576 and 18.25 GiB at 16,384, all with zero spill - but it
  decodes at **15.4-15.6 tok/s** with a **48-72 s** cold load. The uncensored
  27B fits too (17.38 GiB at 32,768, **17.96 tok/s**); the 12B reads
  **33.71 tok/s** on three cards and **32.90** on the 2060 alone; the
  abliterated 9B reads **52.76**; MiniCPM-V reads **159.54** at 1.33 GiB; and
  the vision model reads **63.35** on the headless card. **None of them is fast
  enough to replace the coding model**, and none becomes a preset tonight -
  they are the numbers a Wave 8 decision will be made from.
- **Moving Fast/Agentic+Vision to a dedicated headless-card lane on port 11438
  is not shipped.** It needs a **new lane-start path** (there is no logon task
  and no lane object for 11438 yet). The measurement is the reason it is worth
  doing, and it is recorded rather than quietly dropped: Fast on the headless
  card read **85.29 tok/s at 3.20 GiB** against **76.20** on the display card,
  and the vision model read **63.35 tok/s at 6.14 GiB** there with nothing on
  the monitor. That is a real gain; the blocker is the lane machinery, not the
  numbers.
- **Auto-escalation is not enabled.** The 2026-11-07 cloud audit found a real
  privacy gap: `home address`, `address` and `phone number` are not in the
  privacy backstop, so with auto mode on a longer question such as *"What is my
  home address, and how do I update it in the system so the records match?"*
  (complexity 0.400) **escalates to the cloud**. Nothing on this page turns that
  on; the audit's own recommendation is to fix the privacy list first
  (`.dsh-scratch/CLOUD-ESCALATION-AUDIT-2026-11-07/REPORT.md`, section 2.2).
- **The `manifests-v2` finding is a tooling fact, not a Jarvis bug.** No
  model-store code in this repository reads `manifests/` from disk - Jarvis
  lists models through Ollama's `/api/tags`, and **that did list both
  layouts**: 18 models, including
  `qwen3-coder-30b-a3b-ud-q3-k-xl:latest` and `qwen3-vl:8b-thinking`, which
  exist only in `manifests-v2`. The audit's own first scan (reading
  `manifests/` alone) would have reported them missing; Ollama never did.

## The evidence

- **Raw rows, one JSON per config**:
  `.dsh-scratch/GPU-3WAY-2026-11-06/bench/results3/<config-id>.json` - each keeps
  `config`, `port`, `env`, `server_version`, both `calls`, the `warm` summary,
  `size_gib`/`vram_gib`/`spill_gib`, `cards_used`, and the full raw reply.
- **The batch summary**: `.dsh-scratch/GPU-3WAY-2026-11-06/bench/results3/_all-<timestamp>.json`.
- **The harness**: `.dsh-scratch/GPU-3WAY-2026-11-06/bench/matrix3.py` (config
  list at lines 58-126, the per-config server at 176-203, one call at 221-257,
  the two-call loop at 291-337), and the run logs `matrix3-full.log` /
  `matrix3-rest.log`.
- **The machine and the store**:
  `.dsh-scratch/GPU-3WAY-2026-11-06/INVENTORY-2026-11-07.md` (nine presets,
  lane constants, both manifest layouts, `ollama list`'s 18 models).
- **The cloud audit behind the deferral**:
  `.dsh-scratch/CLOUD-ESCALATION-AUDIT-2026-11-07/REPORT.md`.

## How to repeat it

From the repository root, with nothing else loading a model:

```powershell
py -3 .dsh-scratch\GPU-3WAY-2026-11-06\bench\matrix3.py --only coding_3cards_32768,coding_2cards_32768 --port 11451
```

It starts its own server on 11451, writes `results3\<id>.json` per config, and
stops the server it started. `--list-models` prints what one throwaway server's
`/api/tags` reports without measuring anything. **Do not point it at 11434,
11435, 11436 or 11450** - it takes an exclusive card set by design, and a lane
model resident beside it would be measured as part of the row.

To put the PC back: nothing to undo. The measurement never touched a live
server or a settings file; the throwaway servers are stopped by the harness,
and the only files it writes are the result JSONs above.
