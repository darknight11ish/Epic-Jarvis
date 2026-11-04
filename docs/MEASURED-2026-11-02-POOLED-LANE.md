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
| 28,672 | 16,114 MiB | 15,902 MiB | **212 MiB** |
| 24,576 | 15,722 MiB | 15,514 MiB | **208 MiB** |
| 20,480 | 15,326 MiB | 15,123 MiB | **204 MiB** |
| 16,384 | 14,886 MiB | **14,886 MiB** | **0** |

The same 212 MiB spill was reproduced with `OLLAMA_SCHED_SPREAD=1` on a server
of its own (68.4 tok/s on one prompt, with the spill), so it is not a
scheduling artefact and not a stale server: it is the split this PC's two cards
get today. Unloading the model on Ollama's own default server (11434) was
tried too and changed the 2060's used memory by 89 MiB - that server's model
holds no video memory while its process is idle, so it is not part of the
problem and the pooled lane does not touch it.

**Therefore the preset asks for 16,384** and the pooled start refuses (503, in
the machine's own words) rather than loading a model that spills. The
2026-10-18 number is still in `jarvis_big_coder.NUM_CTX` for that mode and was
not changed - what changed is which rung the PRESET asks for, and the reason is
this table.

**2026-11-03 amendment, below:** this paragraph records the 2026-11-02 state.
The preset has since moved to 20,480 with a measured, capped spill allowance -
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

## 2026-11-03 amendment: the pooled window becomes 20,480, with a measured allowance

The owner asked for the Coding preset's window to be 20,480 tokens rather than
16,384, and accepted the measured cost of doing so. This section is that
measurement, taken on this PC on 2026-11-03 16:07-16:17, read-only: no live
module and no settings file was edited, the Jarvis backend on 4719 and the
desktop app were not stopped or restarted, no approval card was raised or
answered, and no preset was switched.

**Method - the 2026-11-02 measurement above, reused.** Both rungs were loaded
through the shipped `jarvis_big_coder.load` on the pooled lane's own Ollama at
11450, with `/api/ps` empty on every server, one cold load per rung. The three
small fixed coding prompts from 2026-11-02 were reconstructed from their
description above (a `median(xs)` function; a bug fix for a function dividing by
`len(items)`; SQL for the two newest rows of `events`) and run through
`/api/generate` at `temperature 0`, `seed 42`, `num_predict 192`. Decode speed is
Ollama's own `eval_count / eval_duration`; memory is `/api/ps` (`size` against
`size_vram`) and `nvidia-smi`. The 16,384 control load was reproduced exactly:
**14,886.2 MiB with zero spill**, against the 2026-11-02 table's 14,886 MiB /
zero spill.

### The two windows, side by side

Model `qwen3-coder-30b-a3b-ud-q3-k-xl` on port 11450, one cold load per rung.

| | **16,384 (shipped then)** | **20,480** |
|---|---|---|
| Cold load, wall clock | **37.0 s** | **34.9 s** |
| Loaded size (`size`) | 14,886.2 MiB | 15,326.2 MiB |
| In video memory (`size_vram`) | 14,886.2 MiB | 15,122.7 MiB |
| **Spilled to system RAM** | **0.0 MiB** | **203.5 MiB** |
| Context `/api/ps` reports | 16,384 | 20,480 |
| Prompt 1 - `median(xs)` - prompt / output tokens | 40 / 101 | 40 / 101 |
| Prompt 1 - decode tok/s | 81.75 | 81.47 |
| Prompt 2 - empty-list fix - prompt / output tokens | 42 / 24 | 42 / 24 |
| Prompt 2 - decode tok/s | 78.69 | 79.08 |
| Prompt 3 - newest-2-rows SQL - prompt / output tokens | 43 / 14 | 43 / 14 |
| Prompt 3 - decode tok/s | 79.88 | 81.44 |
| **Median of the three** | **79.88 tok/s** | **81.44 tok/s** |
| Time to first token, p1 / p2 / p3 | 0.423 / 0.128 / 0.142 s | 0.347 / 0.139 / 0.133 s |
| GPU used during the runs | 2060 8,918 - 2080 7,606 MiB | 2060 9,252 - 2080 7,486 MiB |
| Unload to an empty `/api/ps` | 0.33 s | 0.32 s |
| Longer probe - 41-token prompt, ~333-token answer | **81.23 tok/s** (332 out) | **77.95 tok/s** (333 out) |

Every prompt named `num_ctx` in its own request. Without it, Ollama silently
reloads the model at its default 8,192 - the trap `jarvis_big_coder.load`
documents, and it was hit once in a discarded first pass here.

### What was accepted, and why

**The 203.5 MiB is real and is paid to system RAM.** It is 1.3% of the model,
and 20,480 is the only rung measured so far where any part of the model is
outside the two cards. Speed is not measurably worse: the three bench prompts
were 79.88 -> 81.44 tok/s median (2.0% faster), the 333-token probe was 81.23 ->
77.95 tok/s (4.0% slower), and all six generations pooled to about 80.4 vs 80.0
tok/s (0.5% slower). Two runs that were actually identical (both at 8,192, same
prompts, same model) had medians 7% apart, so a 2-4% difference is inside this
model's own run-to-run noise: **no speed cost this instrument can resolve.**
Cold load is the same (34.9 s against 37.0 s, noise) and first-token latency is
the same (0.13-0.44 s both). Nothing failed, timed out, or behaved differently
on load and unload.

**So the code now says so honestly, and the rule is narrow:**

- `jarvis_model_lanes.POOLED_CTX` is **20,480** and the Coding preset's own
  `context` is pinned to it by test.
- `jarvis_model_lanes.POOLED_SPILL_ALLOWANCE` is **224 MiB** - the 203.5 MiB
  measurement plus about 10%, so the same split reported slightly differently
  still loads. The pooled start passes it to
  `jarvis_big_coder.load_coder(..., allow_spill=...)`.
- **`allow_spill` is one number for one window.** `load_coder`'s default is
  `None`, which keeps the original rule exactly: ANY spill is refused. Every
  other caller - `jarvis_big_coder.start()` and its own mode included - passes
  no allowance, and the big-coder mode's 28,672-token rung is unchanged. A load
  that spills past the allowance is still refused and unloaded, and the refusal
  names both the actual spill and the allowance. A row that does not report
  `size`/`size_vram` is refused too, allowance or not.

**What is still unmeasured, and said plainly:** the extra 4,096 tokens were
never filled here - every prompt was 40-43 tokens, so the window was loaded but
not used. The KV cache grows with real context and part of it could also end up
in RAM in a genuinely long conversation; that was not measured, so whether the
window holds up when a 15-minute coding session fills it is still an open
question. A 15-minute real coding test runs after this change is deployed, and
its result is not claimed in advance.

**How this was measured.** Both rungs through the shipped
`jarvis_big_coder.load`/`ps` on 11450, memory from `/api/ps` and `nvidia-smi`,
with the three lane models evicted first (`keep_alive: 0`) because the 2026-11-02
ladder was taken on an otherwise empty PC. After the last unload the 11450 server
was stopped, nothing of the coding model was left loaded, and the three
everyday/lane models that were evicted were left unloaded on purpose so the
owner's everyday model reloads on its next turn. The measurement is read-only on
the owner's PC and is not a live coding session.
