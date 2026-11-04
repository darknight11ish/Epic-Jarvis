# The Coding preset's pooled both-card lane, measured (2026-11-02)

The owner asked for the Coding focus preset to be usable, and accepted that
measuring it may evict the Live/Fast models and slow Live while it ran. This
page is what was measured, on this PC, through the shipped path - not a
simulation and not a re-implementation - and how to repeat it or undo it.

**The contract is `docs/JARVIS-API.md` §145.1.** The code is
`jarvis_model_lanes.start_pooled_lane` / `stop_pooled_lane`, which reuse
`jarvis_big_coder`'s server, pause, load and restore. The preset is
`jarvis_presets.by_id("coding")`.

## What was run

`start_pooled_lane(gate=...)` with a gate that allows (the owner accepted this
measurement in advance; no approval card was raised or answered by the
measurement itself), then three fixed small coding prompts through
`/api/generate` with `temperature 0`, `seed 42`, `num_predict 192`, then
`stop_pooled_lane()`. `nvidia-smi` was read on both cards before, after the
load and after the runs, and `/api/ps` was read on 11434, 11435, 11436 and
11450 at each step.

The three prompts were: a `median(xs)` function; a bug fix for a function that
divides by `len(items)`; and a SQL query returning the two newest rows of
`events`.

## The numbers

| What | Measured |
|---|---|
| Cold load (the model's own `load_duration`) | **32.5 s** |
| Whole apply: card, announcement, server, pause, load, prove | **69.9 s** |
| Whole stop: unload, server stop, both lane models back, proved | **59.1 s** |
| Decode on the three prompts | **77.5 / 85.3 / 85.6 tokens a second** (median **85.3**) |
| Tokens generated / read per prompt | 93 / 42 / 20 generated, 39 / 49 / 35 read |
| The model in `/api/ps` | 15,609,312,049 B size, **the same in video memory - zero spill** |
| RTX 2060 while it ran | **11,899** of 12,288 MiB used |
| RTX 2080 SUPER while it ran | **7,674** of 8,192 MiB used |
| After the stop | `qwen3.5:9b ctx=196608` on 11436 and `qwen3:8b ctx=16384` on 11435, both zero spill |
| 11450 afterwards | not answering - the server this apply started was stopped |

Short outputs make a decode figure noisy, which is why all three are quoted and
the median is named as a median rather than as a benchmark result. The
2026-10-18 figure for the same model (76.2 tok/s median on a larger prompt set,
at 28,672 tokens) is in the same range and is not contradicted by these.

## The context ladder: 28,672 no longer fits this PC

The 2026-10-18 measurement recorded 28,672 tokens as the largest context with
zero spill. Re-measured on 2026-11-02, with the two lane models paused and
`/api/ps` showing empty on every server, each rung a real cold load (~33 s):

| `num_ctx` | `size` | `size_vram` | Spilled |
|---|---|---|---|
| 32,768 | 16,513.7 MiB | 16,190.1 MiB | **323.5 MiB** |
| 28,672 | 16,114 MiB | 15,902 MiB | **212 MiB** |
| 24,576 | 15,722 MiB | 15,514 MiB | **208 MiB** |
| 20,480 | 15,326 MiB | 15,123 MiB | **204 MiB** |
| 16,384 | 14,886 MiB | **14,886 MiB** | **0** |

The 28,672, 24,576 and 20,480 rows are the 2026-11-02 run; the 32,768 row was
measured on 2026-11-03, on the same PC and through the same shipped path, and it
agrees with the others on 16,384 (14,886.2 MiB, zero spill). **The preset now
asks for the 32,768 row** - every rung above 16,384 spills, and 16,384 is still
the largest rung that loads with none in video memory.

The same 212 MiB spill was reproduced with `OLLAMA_SCHED_SPREAD=1` on a server
of its own (68.4 tok/s on one prompt, with the spill), so it is not a
scheduling artefact and not a stale server: it is the split this PC's two cards
get today. Unloading the model on Ollama's own default server (11434) was
tried too and changed the 2060's used memory by 89 MiB - that server's model
holds no video memory while its process is idle, so it is not part of the
problem and the pooled lane does not touch it.

**Therefore, from 2026-11-02 until the amendment below, the preset asked for
16,384** and the pooled start refused (503, in the machine's own words) rather
than loading a model that spills. The 2026-10-18 number is still in
`jarvis_big_coder.NUM_CTX` for that mode and was not changed - what changed is
which rung the PRESET asks for, and the reason is this table.

**2026-11-03 amendment, below:** this paragraph records the 2026-11-02 state.
The preset has since moved to 32,768 with a measured, capped spill allowance -
read the amendment at the end of this page before relying on the numbers above.

## The state of the PC afterwards

The measurement evicted both lane models (that is the feature's own cost, and
the card says so before it happens). Afterwards:

- 11436 answered again with `qwen3.5:9b` at `ctx=196608` and **zero spill** -
  the everyday model the owner's chat uses;
- 11435 was left **empty**, which is how it was found (the restore had loaded
  `qwen3:8b` there, because that is the lane's configured model; the
  measurement unloaded it again so nothing was left more loaded than before);
- 11434 still answered with its own `qwen3.5:9b` at `ctx=16384`;
- 11450 had no server at all;
- the owner's backend on 8765 answered 200 throughout, and no Jarvis or Ollama
  process was killed or restarted.

**Known difference, said plainly:** `stop_pooled_lane` restores BOTH lane
models, because that is the contract `jarvis_big_coder.LANES` states ("the two
lanes come back exactly as they were"). If the owner had deliberately unloaded
one of them, stopping the Coding preset will load it again. The measurement
undid that by hand to leave the PC as it was found; the feature does not know
what was there before, and that is a limitation rather than a claim.

## What was not tested here

- No person drove the desktop or phone UI against a real card. The desktop and
  phone suites prove the words and that the row is offered; the backend suites
  prove the order, the refusals and the restores against fakes.
- The "VRAM cannot be freed" refusal was exercised by unit test, not by
  deliberately holding a card hostage.
- A third card is not present on this PC, so nothing is claimed about one.
- Long coding sessions, and the chat's own quality on the 30B, were not
  measured here; the model's 6/6 coding-rubric result is the 2026-10-18 record.
- The background learner's behaviour while the preset is applied was reasoned
  from the code, not driven: it talks to `OLLAMA_URL` (the everyday lane), so
  its pass cannot load the 30B and proposes nothing until another preset is
  applied (JARVIS-API §145.1 says the same). It was not measured, and no claim
  is made that it fails fast.

## How to repeat it

The measurement script is scratch, not shipped. It does this, in order:

1. record `nvidia-smi`, `/api/ps` on 11434/11435/11436;
2. `start_pooled_lane(gate=allow)`, timing it;
3. read `/api/ps` on 11450 and `nvidia-smi`; run the three prompts;
4. `stop_pooled_lane()`, timing it;
5. read `/api/ps` on 11434/11435/11436 and 11450 again, and `nvidia-smi`.

## Undo

There is nothing to undo in the code: the lane exists only while the preset is
applied, and applying any preset that is not heavy stops it. To put the PC back
after a measurement: `POST /api/big-coder {"action":"stop"}` stops the same
server by the same code. If an earlier backend process left a server
answering on 11450, its model is what holds the cards; unload it with
`OLLAMA_HOST=127.0.0.1:11450 ollama stop qwen3-coder-30b-a3b-ud-q3-k-xl` (in
PowerShell: `$env:OLLAMA_HOST="127.0.0.1:11450"; ollama stop
qwen3-coder-30b-a3b-ud-q3-k-xl`). Nothing else needs undoing.

## 2026-11-03 amendment: the pooled window becomes 32,768, with a measured allowance

The owner asked for the Coding preset's window to be 32,768 tokens - the largest
rung measured to load on this PC - rather than 16,384, and accepted the measured
cost of doing so. This section is that measurement, taken on this PC on
2026-11-03, read-only: no live module and no settings file was edited, the Jarvis
backend on 4719 and the desktop app were not stopped or restarted, no approval
card was raised or answered, and no preset was switched.

*Numbering note, same day:* the first version of this amendment recorded the
owner's first choice, 20,480 tokens. The owner then chose the top of the measured
ladder, 32,768, so this section now describes that choice. 20,480, 24,576 and
28,672 stay in the table as real measured rungs; they are history, not the
chosen window.

**Method - the 2026-11-02 measurement above, reused.** Each rung was loaded
through the shipped `jarvis_big_coder.load` on the pooled lane's own Ollama at
11450, with `/api/ps` empty on every server, one cold load per rung. The three
small fixed coding prompts from 2026-11-02 were reconstructed from their
description above (a `median(xs)` function; a bug fix for a function dividing by
`len(items)`; SQL for the two newest rows of `events`) and run through
`/api/generate` at `temperature 0`, `seed 42`, `num_predict 192`. Decode speed is
Ollama's own `eval_count / eval_duration`; memory is `/api/ps` (`size` against
`size_vram`) and `nvidia-smi`. The 16,384 control load was reproduced exactly:
**14,886.2 MiB with zero spill**, against the 2026-11-02 table's 14,886 MiB /
zero spill. The 20,480 rung was measured in the morning (the first version of
this amendment) and 24,576, 28,672 and 32,768 in the afternoon, through the same
harness: `.dsh-scratch/CODING-TAKEOVER-2026-11-03/WINDOW-20480.md` and
`WINDOW-HIGHER-RUNGS.md`, raw output in `measure-hi-raw.log`.

### The ladder, all five rungs

Model `qwen3-coder-30b-a3b-ud-q3-k-xl` on port 11450, one cold load per rung,
with `OLLAMA_KV_CACHE_TYPE=q8_0` already set in the owner's environment - the
cheapest KV cache Ollama offers, so there is no further room to find in the
cache.

| `num_ctx` | `size` | `size_vram` | Spilled |
|---|---|---|---|
| 16,384 | 14,886.2 MiB | 14,886.2 MiB | **0** |
| 20,480 | 15,326.2 MiB | 15,122.7 MiB | **203.5 MiB** |
| 24,576 | 15,721.9 MiB | 15,514.4 MiB | **207.5 MiB** |
| 28,672 | 16,113.6 MiB | 15,902.1 MiB | **211.5 MiB** |
| **32,768 (the preset asks for this one)** | **16,513.7 MiB** | **16,190.1 MiB** | **323.5 MiB** |

Cold load and decode median on the same three prompts, per rung: 16,384 37.0 s /
79.88 tok/s; 20,480 34.9 s / 81.44; 24,576 34.3 s / 82.25; 28,672 35.1 s /
81.46; 32,768 36.0 s / 80.36. The RTX 2060 was at 8,918 / 9,252 / 9,704 / 10,102
/ 10,308 MiB of 12,288 and the RTX 2080 SUPER at 7,606 / 7,486 / 7,504 / 7,529 /
7,591 of 8,192 while those runs ran.

Per-prompt detail for the chosen 32,768 rung: decode **78.28 / 80.90 / 80.36**
tokens a second, time to first token **0.467 / 0.135 / 0.121 s**. Prompt-eval on
a 40-token prompt was **89.56 / 401.89 / 441.31** tokens a second - small-sample
and noisy, so no claim is made from it. The 16,384 and 20,480 rows come from the
same day's earlier run; the two runs agree exactly on 16,384.

Every prompt named `num_ctx` in its own request. Without it, Ollama silently
reloads the model at its default 8,192 - the trap `jarvis_big_coder.load`
documents, and it was hit once in a discarded first pass here.

### What was accepted, and why

**The 323.5 MiB is real and is paid to system RAM.** It is 323.5 of the
16,513.7 MiB the model occupies, and it is the price of the largest window that
loads on this PC. Speed is not measurably worse: the decode median is 80.36
against 79.88 tokens a second at 16,384, and two runs that were actually
identical (both at 8,192, same prompts, same model) had medians 7% apart in the
2026-11-02 measurement, so that difference is inside this model's own
run-to-run noise: **no speed cost this instrument can resolve.** Cold load is the same (36.0 s
against 37.0 s; the load time is mostly reading 12.9 GB from disk) and
first-token latency is 0.12-0.47 s. Nothing failed, timed out, or behaved
differently on load and unload.

**The jump is the 8 GB card running out first.** At 28,672 the RTX 2080 SUPER
was already at 7,529 of 8,192 MiB and the spill was 211.5 MiB; at 32,768 it is at
7,591 and the spill jumps by 112 MiB to 323.5 - one more slab of the model goes
to system RAM rather than growing smoothly. The longer ~333-token probe the
earlier run did is 81.23 tok/s at 16,384 against 77.95 at 20,480 (4% slower);
the 32,768 rung was not put through that probe.

**So the code now says so honestly, and the rule is narrow:**

- `jarvis_model_lanes.POOLED_CTX` is **32,768** and the Coding preset's own
  `context` is pinned to it by test. Its `context_measured` is 32,768,
  `spill_gib` is 0.3, and `context_zero_spill` stays **16,384** - that really was
  the zero-spill ceiling, kept as the historical fact.
- `jarvis_model_lanes.POOLED_SPILL_ALLOWANCE` is **352 MiB** - the 323.5 MiB
  measurement (`POOLED_SPILL_MEASURED_MIB`) plus about 9%, so the same split
  reported slightly differently still loads. The pooled start passes it to
  `jarvis_big_coder.load_coder(..., allow_spill=...)`.
- **`allow_spill` is one number for one window.** `load_coder`'s default is
  `None`, which keeps the original rule exactly: ANY spill is refused. Every
  other caller - `jarvis_big_coder.start()` and its own mode included - passes
  no allowance, and the big-coder mode's 28,672-token rung is unchanged. A load
  that spills past the allowance is still refused and unloaded, and the refusal
  names both the actual spill and the allowance. A row that does not report
  `size`/`size_vram` is refused too, allowance or not.

**Above 16,384 every rung spills.** 20,480 was measured at 203.5 MiB, 24,576 at
207.5, 28,672 at 211.5 and 32,768 at 323.5; there is no rung between 16,384 and
the top that loads with nothing in system RAM. The first version of this
amendment said "20,480 is the only rung measured so far where any part of the
model is outside the two cards" - that was wrong even then, and this paragraph
is the correction.

**What is still unmeasured, and said plainly:** the extra tokens were never
filled here - every prompt was 40-43 tokens, so the window was loaded but not
used. The KV cache grows with real context and part of it could also end up in
RAM in a genuinely long conversation; that was not measured, so whether the
window holds up when a 15-minute coding session fills it is still an open
question, and the decode speed of a nearly-full 32,768-token window was not
measured either. A 15-minute real coding test runs after this change is deployed,
and its result is not claimed in advance. The measurement also evicted the three
standing lane models, which is the feature's own documented cost; they cold-load
again (about 10 s) on the next turn.

**How this was measured.** Each rung through the shipped
`jarvis_big_coder.load`/`ps` on 11450, memory from `/api/ps` and `nvidia-smi`,
with the three lane models evicted first (`keep_alive: 0`) because the 2026-11-02
ladder was taken on an otherwise empty PC. After the last unload the 11450 server
was stopped, nothing of the coding model was left loaded, and the three
everyday/lane models that were evicted were left unloaded on purpose so the
owner's everyday model reloads on its next turn. The measurement is read-only on
the owner's PC and is not a live coding session.
