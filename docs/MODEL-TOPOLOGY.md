# What runs on the GPU, and how much context it gets

RTX 2060 12 GB (no monitor; holds the everyday model) and RTX 2080 Super,
8 GB (the monitor; runs the desktop), both Turing sm75. Ryzen 9 3900X.
Windows 11.

**Both cards are installed and measured** (2026-10-05,
[MEASURED-2026-10-05-owner-pc.md](MEASURED-2026-10-05-owner-pc.md)): an RTX
2060 12 GB with no monitor, which holds the everyday model, and the RTX 2080
Super 8 GB, which has the monitor and runs the desktop. Everything below the
next heading was worked out for the 2080 Super alone, before the second card
went in; see [The planned second card](#the-planned-second-card-rtx-2060-12-gb)
for what changes and for what is really measured.

Read this if you are about to change models, change context length, or wonder
why a long conversation gets strange.

**Also read [HARDWARE-PROFILES.md](HARDWARE-PROFILES.md)** (2026-09-24, a
design, calculated not measured). **Where the two disagree, it has the
current numbers.** It generalises this page to any 8 GB card and up to two
cards, and found that parts of this page are out of date against current
Ollama and llama.cpp source:

- llama.cpp now keeps an empty gap on each card - **1 GB by default**. The
  owner has decided on **0.75 GB** (HARDWARE-PROFILES section 5, decision 1),
  but nothing applies that yet, so today the default 1 GB is in force. With
  1 GB, the 16K budget below is calculated to be ~0.6 GiB over; at 0.75 GB
  the 8 GB card holds about 11,000 tokens of chat (calculated, not measured).
- `q8_0` with flash attention: llama.cpp now switches flash attention ON by
  itself for a `q8_0` cache when it is on "auto", and refuses to load the
  model when flash attention is forced off. The "silently ignored, then
  spills" failure this page used to warn about no longer happens. The
  verify step below has been updated to match.
- Ollama's own estimate now over-counts a `q8_0` cache rather than
  under-counting it.

Its section 3 lists each item with the evidence; section 2.2 cites the
llama.cpp lines for the flash-attention change.

*Since 2026-09-25* the desktop's Settings, "Hardware and models" (and the
phone's Brain, "Hardware") works this out for whatever cards the PC has, and
offers three setups made at the owner's 0.75 GB gap. Choosing one is what
applies the 0.75 GB (as `LLAMA_ARG_FIT_TARGET=768` in its one command);
until then the 1 GB default above stands. Its **Measure** button does the
check this page's "Then verify" section asks for (how much of the model is
on the card, and llama.cpp's own `offloaded N/M layers` line). Only the pair's
own measurement has been written into this page (2026-10-05, "The planned
second card" below); nothing else here has been rewritten from measurement.

---

## The deployed context, measured (2026-10-30)

**The deployed context is 16,384 tokens, and it is measured on the owner's PC,
not calculated** ([MEASURED-2026-10-30-CONTEXT.md](MEASURED-2026-10-30-CONTEXT.md)).
`OLLAMA_CONTEXT_LENGTH=16384` is set for the owner's Windows user; both of this
PC's Ollama servers report `context_length: 16384` for the model they hold, and
the runner's own command line carries `-c 16384`. At that size the everyday
model (`qwen3.5:9b`) reports 5.40 GiB and the 12 GB card still had 3,815 MiB
free, at 38-43 tokens/s.

This section used to say the deployed context was 4,096 and that nothing in the
request chose it. **The second half is still right; the first is not.** A local
chat turn posts to Ollama's own `OLLAMA_URL/v1/chat/completions`
(`ollama-direct.patch`; since `chat-stream.patch`, through
`jarvis_agent.run_local_turn`). That sends `model`, `messages`, `stream`,
`temperature`, `max_tokens` (1,024 unless the app asks otherwise),
`reasoning_effort: "none"` and, with tools on, `tools` - and the
OpenAI-compatible surface has no field for context length, so no request can
choose the size. What changed is the machine: the environment variable does,
which is one of the two routes "Setup" below describes. **A fresh install
without it still gets 4,096**, which is why the ladder is kept.

What the request side *can* do, and now does: ask Ollama what the loaded
model really has (`/api/ps`, then the Modelfile via `/api/show`, else 4,096)
and drop the oldest earlier turns to fit, leaving room for the answer. So a
model switched to from the phone, or a missing `jarvis-primary`, no longer
means Ollama silently cutting the start of the conversation. It does not make
the window any bigger - only the Modelfile or the environment does that.

So a machine with neither picks. `server/sched.go`:

```go
func nextLowerAutoNumCtx(numCtx int) (int, bool) {
	switch {
	case numCtx > 32768: return 32768, true
	case numCtx > 4096:  return 4096, true
	default:             return 0, false
	}
}
```

An 8B Q4 at 32768 with an f16 cache needs about 9.8 GiB. On a card where that
does not fit, the ladder drops to 4096, and 4096 is the bottom rung.

These are now measured rather than planned:

- **A 6,000-token prompt does not fit in 4,096, and the start is lost, silently.**
  Measured: a ~5,019-token prompt went to the runner as 2,050 tokens - half the
  window - and a marker placed at its start was gone, while the one at its end
  was still there.
- **The answer's allowance comes out of the same window.** Ollama's compat
  layer maps `max_tokens` to `num_predict`, and the answer stops at the window
  edge: a 15,403-token prompt at 16,384 produced 981 of a requested 1,024
  tokens, and a 3,112-token prompt at 4,096 produced 984.
- **16,384 costs 240 MiB more than 4,096 on this model**, because `qwen3.5:9b`
  keeps a cache only for its 8 full-attention layers. Decoding is unchanged
  between 4,096 and 16,384 (41-43 tokens/s); reading the prompt is what grows,
  at about 1,200 tokens/s.

**32,768 and 65,536 were measured on 2026-10-30 and are not recommended.**
Both loaded 100% on the GPUs (33/33 layers), neither spilled to the processor,
and both ends of a 30,329- and a 60,227-token prompt survived in the answer,
cold and warm. But decode fell from 41.9 tokens/s at 16,384 to 33.5 at 32,768
and 27.4 at 65,536, a cold 60,227-token prompt took 58.5 s to its first token,
and in the memory conditions measured both sizes were spread over both cards
(2.2-2.7 GiB of the monitor card's memory) because the 2060 did not have
enough free room at the moment each was requested - its own previous model and
the owner's other lane were using it. Nothing was deployed; the setting stays
16,384. The numbers, the control run and the caveats are in
[MEASURED-2026-10-30-CONTEXT.md](MEASURED-2026-10-30-CONTEXT.md).

---

## The correction that makes it fixable

The premise that shaped earlier thinking here — *"FlashAttention-2 does not
support Turing, Ampere or newer only"* — is true of the wrong library.

Dao-AILab's `flash-attn` PyPI package needs sm80+. **Ollama does not use it.**
Ollama runs llama.cpp, which has its own CUDA fused-attention kernels, and
`GGML_CUDA_CC_TURING` is `750`. Ollama's own gate, `ml/device.go`:

```go
func cudaFlashAttentionSupported(gpu DeviceInfo) bool {
	if gpu.Library != "CUDA" ||
		gpu.ComputeMajor < 6 ||
		(gpu.ComputeMajor == 7 && gpu.ComputeMinor == 2) {
		return false
	}
	...
	return gpu.DriverMajor >= 7
}
```

The 2080 Super is compute capability **7.5**. The only 7.x excluded is 7.2,
which is Jetson Xavier. It passes.

This matters because llama.cpp reaches the **`q8_0` KV cache** only through the
fused-attention path. With it, an 8B goes from 8K to 16–20K of context on this
card (before the empty gap described at the top; HARDWARE-PROFILES has the
current figure). Without it, a `q8_0` cache does not load at all.

---

## Setup

One time, in the environment — a Modelfile cannot express these:

```powershell
setx OLLAMA_KV_CACHE_TYPE q8_0; setx OLLAMA_KEEP_ALIVE -1; setx OLLAMA_CONTEXT_LENGTH 16384; Write-Host "Saved for new windows: close this one and Ollama, then start them again"
```

`OLLAMA_CONTEXT_LENGTH=16384` is what makes the deployed window 16,384
(measured 2026-10-30; [MEASURED-2026-10-30-CONTEXT.md](MEASURED-2026-10-30-CONTEXT.md)
has the numbers and the exact undo). Without it Ollama picks 4,096 for a model
whose own Modelfile names no `num_ctx`, which is the live everyday model
(`qwen3.5:9b`). 16,384 is the largest size measured on this PC: at it the
model takes 5.40 GiB and leaves 3,815 MiB of the 12 GB card free.

Then:

```powershell
ollama create jarvis-primary -f backend\jarvis-primary.Modelfile
```

`OLLAMA_KEEP_ALIVE=-1` is deliberate and is not the obvious choice. Ollama's
default is five minutes. With one resident model there is nothing an idle timer
can make room *for*; its only effect is a ~6 second stall on the first word
after you step away, which in the voice loop is the worst possible moment.

Do **not** set `OLLAMA_FLASH_ATTENTION` — to `0` or to `1`. Auto is correct:
with a `q8_0` cache, llama.cpp switches flash attention on by itself, and
forcing `0` makes the model refuse to load.

## Then verify, before trusting any of it

Send Jarvis one message, then run this one line in PowerShell. It only reads
Ollama's log file (the same check as HARDWARE-PROFILES section 4.7):

```powershell
Select-String -Path "$env:LOCALAPPDATA\Ollama\server.log" -Pattern 'offloaded \d+/\d+ layers to GPU|flash_attn|starting llama-server' | Select-Object -Last 4 | ForEach-Object { $_.Line }
```

What to look for:

- `enabling flash_attn since it is required for quantized V cache` → flash
  attention is on and the `q8_0` cache is in use. This is the configuration
  below.
- `quantized V cache requires flash_attn to be enabled`, and the model does
  not load → flash attention is forced off (usually `OLLAMA_FLASH_ATTENTION`
  set to `0`). Remove that setting and restart Ollama; if it still fails,
  take the fallback. This used to fail silently - the cache was ignored and
  the model spilled into system memory - but current llama.cpp refuses
  instead (HARDWARE-PROFILES section 2.2 has the source lines).
- `offloaded 37/37 layers to GPU` → the whole model is on the card. A
  smaller first number means part of it runs on the processor, about five
  times slower, with no other warning. With llama.cpp's 1 GB default gap,
  16K is calculated to do exactly that (HARDWARE-PROFILES section 3, item 1).

**Fallback if the `q8_0` cache will not load:** `qwen2.5:7b` at `num_ctx 16384` on a plain f16
cache — 5.85 GiB, no `q8_0` dependency. Qwen 2.5 7B has the cheapest KV cache
of anything considered here, **56 KiB/token**, less than half of Llama 3.1 8B
and less than a 3B, because it has only 4 KV heads across 28 layers. It is the
one 7–8B that reaches 16K without needing flash attention to be live.

---

## The budget

```
weights  Q4_K_M   8.190B params × 4.90 bpw / 8              = 4.67 GiB
KV       q8_0     2 × 36 × 8 × 128 × 1.0625 B × 16384       = 1.19 GiB
runtime  CUDA context ~330 MiB + compute buffer @ nb512     = 0.63 GiB
                                                              --------
                                                               6.48 GiB
ceiling  8 GiB card − ~1.1 GiB DWM and the Tauri shell       = 6.90 GiB
```

**This ceiling is out of date.** It leaves out llama.cpp's empty gap on the
card (1 GB by default; the owner's chosen 0.75 GB once applied) and the
per-process cost HARDWARE-PROFILES counts. With those, the room on this card
is 5.57 GiB at 1 GB, not 6.90, so 16K no longer fits. Use
[HARDWARE-PROFILES.md](HARDWARE-PROFILES.md) sections 3 and 8.1 for the
current room and context sizes; the arithmetic below is kept because the
per-model figures in it still hold.

`q8_0` is 34 bytes per 32 values — **1.0625** bytes per element, not 1.0.
Ollama's own pre-flight estimator used to round it to 1.0, under-counting a
quantised cache by about 6%. It no longer does: it now assumes `f16` and
over-counts (HARDWARE-PROFILES section 3, item 4).

### `num_batch 512` is not a tuning preference

`server/sched.go`:

```go
func generationBatchSurcharge(batch int) uint64 {
	switch {
	case batch >= llamaServerGenerationBatchLarge:   // 2048
		return 2 * format.GibiByte
	case batch >= llamaServerGenerationBatchMedium:  // 1024
		return 768 * format.MebiByte
	default:
		return 0
	}
}
```

Ollama's auto-batch reaches for 1024 or 2048 when it thinks there is headroom.
Either turns 6.48 GiB into a spill. The Modelfile pins it.

---

## Why one model and not two

The tempting shape is a big model for thinking and a small fast one for
routing. It does not fit, and the reason is not the weights.

**Each Ollama runner is a separate `llama-server` process with its own CUDA
context (~330 MiB) and its own compute buffer.** That is the term that kills
it.

| Primary | Router | Total | |
|---|---|---|---|
| Qwen 2.5 7B @ 8K q8_0 — 5.19 | Llama 3.2 3B @ 4K q8_0 — 2.58 | 7.77 | ✗ +0.87 |
| Qwen 3 8B @ 8K q8_0 — 5.58 | Llama 3.2 3B @ 2K q8_0 — 2.46 | 8.05 | ✗ +1.15 |
| Qwen 2.5 7B IQ4_XS @ 4K q8_0 — 4.54 | Llama 3.2 3B @ 2K q8_0 — 2.46 | 7.01 | ✗ +0.11 |
| **Qwen 3 8B @ 16K q8_0** | *nothing* | **6.48** | **✓** |

The near miss is the worst option on the page, not the best: it is over by
0.11 GiB and gets there by crippling the context of *both* models.

**The last row is the answer.** One 8B at 16K costs less VRAM than the pair and
gives more context than the 3B was being considered for. The 8B-versus-3B
dilemma was constructed on an f16 KV assumption that Turing does not force.

### And swapping is not a router

Qwen 3 8B, 5.01 GB on disk, over the 2080 Super's PCIe 3.0 ×16 link:

| | warm (page-cached) | cold (NVMe) |
|---|---|---|
| unload, read, upload, spawn, CUDA init | ~3.1 s | ~6.5 s |
| re-prefill 6,000 tokens on an empty KV | +3.1 s | +3.1 s |
| **before the first token** | **~6.2 s** | **~9.6 s** |

`jarvis_models.py`'s own docstring already says this — *"a swap on every
request, which is 5–15 seconds of silence each time"* — and the arithmetic
agrees with it. Six seconds is a scene change, not a route. Swap once per
session mode (conversation → code), never per request.

**Second model, on disk, switched deliberately:**
`qwen2.5-coder:7b-instruct-q4_K_M` at `num_ctx 16384`, 5.85 GiB at f16 KV. AST
work needs the whole file resident, so 16K is the floor.

---

## Ruled out, and why

| | |
|---|---|
| **Any 7B/8B at Q8_0** | Weights alone are 7.54–8.10 GiB, over the 6.90 ceiling before a single KV byte. Not close. If any planning table shows these as viable, that is the biggest error in it. |
| **Q5_K_M at 8B** | Costs 0.76 GiB over Q4_K_M and buys little that is measurable. On this card it is the quantisation that turns a working 16K into a spilling 8K. |
| **Phi-4-mini 3.8B** | The trap. 128 KiB/token — *identical* to Llama 3.1 8B (32 layers × 8 kv_heads × 128), plus a 200,064-token vocabulary inflating the embeddings. You pay 8B KV costs for 3.8B capability. Picking it "for context headroom" buys weight headroom, not context headroom. |
| **DeepSeek-R1-Distill-Qwen-7B** | Qwen 3 8B's thinking mode covers the same ground from a model already loaded. (This row used to add that thinking plus a strict JSON schema is a known-bad pairing because the grammar forbids the `<think>` block. That is out of date: current Ollama applies a `format` grammar only after the thinking has closed - `llm/llama_server.go`, the header comment and "A format on a thinking response applies after the closing string", read at Ollama `5f4b01e`, 2026-09-24, not run.) |
| **Gemma 3 4B** | 0.81 GiB of vision tower for a feature nothing uses, and multimodal force-disables context shift (`ctx_shift is not supported by multimodal`), so it hard-errors at the boundary instead of degrading. |
| **Ministral 8B** | Same KV cost as Qwen 3 8B with no compensating advantage. |

---

## Things worth knowing that are not model choices

**Quantisation does not threaten schema adherence.** Ollama's
`format: <schema>` compiles to GBNF and masks at the sampler, so a token that
would break the schema has probability zero however noisy the logits under it
are. Quantisation degrades *choice among valid continuations*, not *validity*.
The failure mode migrates rather than disappearing: from malformed JSON to
**well-formed JSON with a wrong argument value**, which `jarvis_structured.validate()`
cannot catch and `jarvis_gate` has to. That module's own comment already says
it — *"GRAMMAR-VALID IS NOT AUTHORISED"*.

**But tool calls are not held to a grammar.** All of the above is about
`format`. A tool call is different: for every model with Ollama's own
tool-call reader (Qwen 3, Qwen 3.5, Gemma 4, Ministral and others,
`model/parsers/parsers.go`), Ollama lets the model write freely and reads the
call out of the text afterwards; no grammar is applied while it writes. So a
**malformed tool call is possible** - arguments that are not JSON, a missing
field - and Qwen 3's reader does not check the call against the tool's
schema at all (`model/parsers/qwen3.go`, `parseQwen3ToolCall`: `_ = tools`).
When it cannot read the call it cancels the answer with "failed to parse
JSON: ..." (`server/routes.go`, `parserErr`). `jarvis_agent.py` checks every
call against its schema before anything is prepared, and asks once more when
Ollama cannot read one (`backend/README.md`, "Outside text in the tool
loop"). Read at Ollama `5f4b01e`, 2026-09-24, not run.

**The start every question shares is read ahead (2026-09-28).** Ollama
reuses the part of the last prompt a new one starts with, and every local
question starts with the Jarvis rules and the tool list (roughly 550 tokens
with only web search on, roughly 3,000 with every tool). Loading the model,
and on one card the background learner, threw that away. Now the warm-up
on waking and after each learning pass sends exactly that start with one
word of question and one of answer (`jarvis_agent.warm_prefix`;
`backend/README.md`, "Warm-up with words"). Not measured on the PC. One
thing could shrink it, not checked: Ollama gathers every system message
into one block (`template/template.go`, `collate()`), so if the model's
template prints that block before the tools, a spoken question or one with
recalled facts differs before the tool list and reuses only the rules. The
speed record's `cached_tokens` shows which.

**Keep the embedder on the CPU.** bge-small is ~130 MB on ONNX Runtime.
On the GPU it would cost ~0.2 GiB *and* contend for the same SMs mid-utterance.
It is on the 3900X's 12 cores today, and that is now enforced rather than
merely decided: the memory search loads its ONNX models with the CPU provider
only (`CPUExecutionProvider` is the one provider named in
`jarvis_memory.py`), so no graphics card is offered them at all.

**`jarvis_persona.memory_top_k` is dead.** Personas declare 4, 6, 8, 10 or 16
and every one of them gets 5, because the number was hardcoded in the search
call. `memory-prefix.patch` lifts it to `MEMORY_K` / `JARVIS_MEMORY_K`, which
names it but does not yet read the persona. Honouring `memory_top_k=16` would
roughly triple the injected block, from ~100 to ~320 tokens — small in a 16K
window, and much cheaper than it was before that patch moved the block out of
the prefix.

## Engine settings to try (written down, not applied)

Two settings of the engine inside Ollama (llama.cpp) that the research audit
(`docs/RESEARCH-AUDIT-2026-09-28.md` section 6, items 2 and 4) says are
worth measuring. **Neither is switched on.** Both are read by the engine
from the environment: Ollama starts it with its own environment, so any
`LLAMA_ARG_...` setting reaches it (the audit read this in Ollama's and
llama.cpp's source; it has not been tried on the PC). Jarvis already sets
one this way, `LLAMA_ARG_FIT_TARGET`, in the Hardware presets.

Measure before and after with the speed record's quick mode - it times
`jarvis-primary` alone (1st, 2nd and 3rd request after loading, words per
second, a note-tidying job, and how much is on the card) and adds one line
to `C:\Users\pcadmin\jarvis-model-tryout\speed-only.jsonl`, so before and
after sit next to each other. About 2 minutes; run it when Jarvis is idle,
from this repository's folder:

```powershell
py -3 tools\model_tryout\chat_tryout.py --speed-only; Write-Host "Added to $env:USERPROFILE\jarvis-model-tryout\speed-only.jsonl"
```

**1. Cap the engine's prompt memory in system RAM: `LLAMA_ARG_CACHE_RAM=3072`.**
The engine keeps recent prompts in the PC's main memory so a repeated start
(Jarvis's rules and tool list) is not read again. Its default allows 8 GB
per running copy, and Jarvis can run up to three copies (the main one, the
second card's, the big model's). 3072 caps each at 3 GB. What to watch: the
2nd and 3rd "first word" times should stay the same (if they grow, the cap
is too small), and the memory Ollama's programs use should drop. This one
line prints that memory (it only reads):

```powershell
"{0:N1} GB used by Ollama's programs" -f ((Get-Process -Name 'ollama*','llama*' -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum / 1GB)
```

This line reaches the **main** Ollama only. The copies Jarvis starts itself
- the second card's Ollama and the big model - are handed a fixed list of
settings (`jarvis_child_env.py`, checked 2026-09-28) that does not include
it; adding it there is a small code change for later, once the second card
is in. Switch it on (then quit Ollama - right-click its icon by the clock,
Quit Ollama - and start it again from the Start menu):

```powershell
[Environment]::SetEnvironmentVariable('LLAMA_ARG_CACHE_RAM', '3072', 'User'); Write-Host 'Saved for your Windows user. Quit Ollama and start it again.'
```

Undo: `[Environment]::SetEnvironmentVariable('LLAMA_ARG_CACHE_RAM', $null, 'User'); Write-Host 'Undone. Quit Ollama and start it again.'`

**2. "Guess ahead" without a second model: `LLAMA_ARG_SPEC_TYPE=ngram-mod`.**
While writing, the engine guesses the next few words from words already in
the conversation and checks them in one go - cheap (about 16 MB) and it
needs no draft model. It helps most when an answer repeats text it was given
(tidying a note, a summary); for a fresh answer it may do nothing or cost a
little. **Keep it only if words per second go up** in the speed record
(look at "words/s" and "tidying a note ... tokens/s"), and the answers still
read right. Like the first setting, it reaches the main Ollama only.

```powershell
[Environment]::SetEnvironmentVariable('LLAMA_ARG_SPEC_TYPE', 'ngram-mod', 'User'); Write-Host 'Saved for your Windows user. Quit Ollama and start it again.'
```

Undo: `[Environment]::SetEnvironmentVariable('LLAMA_ARG_SPEC_TYPE', $null, 'User'); Write-Host 'Undone. Quit Ollama and start it again.'`

Change one setting at a time, and measure after each, or you cannot tell
which one did what. Neither shows up in Ollama's log line of settings (they
are not passed as flags), so the speed record is the only proof either one
took effect - an unchanged record after a restart can also mean it was not
picked up. Send the `speed-only.jsonl` lines back.

**A hidden place settings can come from.** The same engine also reads
`%PROGRAMDATA%\llama.cpp\config.ini` and `%APPDATA%\llama.cpp\config.ini`
(the audit's item 3). Nothing in Jarvis writes them, and nothing in Jarvis
would show a setting that came from them, so the preflight
(`py -3 backend\selftest.py --preflight`) now warns when either exists, with
the settings' names and the one line that renames the file.

Trying other chat models, and other memory-search models, is
`tools/model_tryout/README.md`.

## The Qwen3.5-9B profile, and what was measured (2026-10-15)

Upgrade 3C adds a ready-to-build profile for **qwen3.5:9b**:
`tools/model_tryout/Modelfile.jarvis-qwen35-9b`. It sits in
`tools/model_tryout/` rather than a new `models/` folder because that folder is
where Modelfiles-for-models-being-tried already live (the tryout writes them
there), it needs no `$SHIPPED` entry and no `jarvis-backend/` twin, and
`backend/` is the patch directory where a second Modelfile would raise exactly
those questions. **Nothing points at it and nothing was switched** - the
backend keeps using what it uses.

**Everything the work order claimed about the model, checked against the
installed one rather than accepted:**

| claim | what was measured | verdict |
|---|---|---|
| installed under `.lmstudio\models\manifests\...` | present at `...\manifests\registry.ollama.ai\library\qwen3.5\9b`, and `qwen3.5:9b` is in `/api/tags` (6.55 GB, Q4_K_M, family qwen35) | **right** |
| 5.24 GB weights + 0.86 GB projector = 6.10 GB | the manifest's own layers: 5,629,109,120 B = **5.243 GiB**, projector 921,704,832 B = **0.858 GiB**, total **6.101 GiB** = 6.55 GB | **right - the unit is GiB** |
| 8 full-attention + 24 Gated DeltaNet recurrent layers | `qwen35.block_count` 32, `full_attention_interval` 4, and `attention.recurrent_layers` is True,True,True,False eight times -> 24 recurrent, 8 full attention | **right** |
| 0.27 GiB KV cache at 16K | 2 x 4 kv heads x 256 x **8 attention layers only** x 16384 tokens x 1.0625 B (q8_0) = 285,212,672 B = **0.266 GiB** | **right, at q8_0** |
| native vision + tools + thinking | `/api/show` capabilities `completion, vision, tools, thinking`, and a projector layer is present | **right** |
| `presence_penalty` default is 1.5 | `/api/show` parameters: `presence_penalty 1.5`, `temperature 1`, `top_k 20`, `top_p 0.95` | **right** |

Two things the work order did not say, both worth having:

- **A recurrent layer keeps no KV cache at all.** Counting all 32 blocks - what
  a dense model's arithmetic would do - gives 1.07 GiB at 16K, four times the
  real figure. That is why 0.27 GiB looks too small for a 9B model and is not.
- **`qwen3.5:9b` was installed and configured, but not resident.** While these
  were measured, `/api/ps` listed `qwen3:0.6b` on 11434 and
  `jarvis-primary:latest` (5.85 GiB) on the everyday lane's own Ollama at
  11436. The backend's `/api/models` "current" is a setting, not what is on a
  card. qwen3.5:9b itself was loaded nowhere.

### The measured line (2026-10-15T14:12:03)

`python tools/model_tryout/chat_tryout.py --speed-only`, with NEITHER engine
setting on (`LLAMA_ARG_CACHE_RAM` and `LLAMA_ARG_SPEC_TYPE` both null), so this
is the baseline row the two settings above are compared against:

    jarvis-primary: first word 10.49/0.03/0.03 s (1st/2nd/3rd request after
    loading), 29.0 words/s, 41.6 tokens/s, tidying a note 46.5 tokens/s,
    100% on the graphics card (5.85 GB)

The prompt was 3,838 tokens - Jarvis's rules and tool list, the "3,000-4,000"
quoted above - and the load itself was 7.58 s of that 10.49 s.

**The first request after loading takes 10.5 s and the next two take 0.03 s.**
That is llama.cpp issue #29513 exactly - *"Qwen3.5-4B: first request after load
is extremely slow (CUDA backend), warm performance is fine (**RTX 2060 /
sm_75**, b11206)"* - seen on this PC's own 2060, here on `jarvis-primary`
rather than on a Qwen3.5 model. It is the reason `jarvis_agent.warm_prefix`
exists, and the reason nothing had to be added for Upgrade 3C item 3: it
already runs once the model is loaded (`jarvis_power_switch.warm_up`, the path
that loads it, `jarvis_power_switch.py:521-526`).

The recorded line, verbatim:

```json
{"requests": [{"first_word_s": 10.49, "load_s": 7.58, "tokens_per_s": 41.4, "words_per_s": 28.9, "prompt_tokens": 3838}, {"first_word_s": 0.03, "load_s": 0.01, "tokens_per_s": 41.9, "words_per_s": 29.2, "prompt_tokens": 3838}, {"first_word_s": 0.03, "load_s": 0.01, "tokens_per_s": 41.4, "words_per_s": 28.9, "prompt_tokens": 3838}], "first_word_s": [10.49, 0.03, 0.03], "tokens_per_s": 41.6, "words_per_s": 29.0, "rewrite_tokens_per_s": 46.5, "prompt_tokens": 3838, "on_card_pct": 100, "size_gb": 5.85, "at": "2026-10-15T14:12:03", "model": "jarvis-primary", "settings_in_this_window": {"LLAMA_ARG_CACHE_RAM": null, "LLAMA_ARG_SPEC_TYPE": null}}
```

**What the measurement changed on the machine**, so nobody has to guess: the
timing loads `jarvis-primary` into the main Ollama (11434) and leaves it there,
which is the tool's own end state. GPU 0 (the 2060) went from 7,731 MiB to
11,917 MiB of 12,288. The everyday lane's own copy on 11436 was not disturbed,
and no setting and no model choice was changed. The result file landed in
`%TEMP%\jarvis-model-tryout\speed-only.jsonl` rather than the usual
`C:\Users\pcadmin\jarvis-model-tryout\`: that folder is outside the writable
area of the session that ran it, so `chat_tryout.run(..., out_root=...)` was
called instead of the command line. The same tool, the same measurement, a
different place for the line - and the command line to add it to the owner's
own file is the one printed in `tools/model_tryout/README.md`.

---

## The planned second card: RTX 2060 12 GB

The owner added one, alongside the 2080 Super, not instead of it. Recorded
2026-09-23. (The heading keeps the name the rest of the project links to; "the
planned card" is now the fitted one - see the next paragraph.)

**It is installed, and the pair has now been measured** (2026-10-05): both
cards are present; the everyday model is running on the 12 GB card, which
`nvidia-smi` calls GPU 0 (the 2080 SUPER is GPU 1 and runs the desktop); it is
**100% on the card** with nothing spilling to the processor. On 2026-10-05 its
context was still 4,096 while the 16,384 this page documents **fit** with room
to spare - and **on 2026-10-30 the deployed context really was 16,384, measured**
([MEASURED-2026-10-30-CONTEXT.md](MEASURED-2026-10-30-CONTEXT.md)), which is
what that 2026-10-05 measurement said to do
([MEASURED-2026-10-05-owner-pc.md](MEASURED-2026-10-05-owner-pc.md); re-measure
with `scripts\measure-cards.ps1`, described in
[MEASURE-CARDS.md](MEASURE-CARDS.md)). So the spill this page and
HARDWARE-PROFILES.md section 3 feared - the old one-card arithmetic that put
~4 of 37 layers on the processor - **does not happen on this machine.**

**Everything below is still the plan, and still calculated, not measured.**
The figures are published specs and the same arithmetic as the budget above,
and no second-card lane has been switched on yet.

**Why this card avoids the P100's problems (see the next section).** It is
the same generation as the 2080 Super: Turing, compute capability 7.5. So:
one driver branch for both cards, the same fast fused-attention kernels, the
same `q8_0` cache path, a fan, a normal PCIe power plug and display outputs.

| | 2080 Super | 2060 12 GB |
|---|---|---|
| memory | 8 GB | 12 GB |
| memory speed (published) | ~496 GB/s | ~336 GB/s |
| board power (published) | ~250 W | ~185 W |

**What it changes.** "Why one model and not two", below, is about one 8 GB
card: two runners on it do not fit. With a second card each model gets a card
to itself, so that argument stops applying. What the 12 GB could hold, by the
same arithmetic as "The budget", assuming no monitor is plugged into it:

```
Qwen 3 8B  Q4_K_M, q8_0 KV @ 32K   4.67 + 2.39 + 0.63   =  7.69 GiB  ✓
Qwen 3 14B Q4_K_M, q8_0 KV @ 16K   8.42 + 1.33 + 0.63   = 10.38 GiB  ✓
ceiling    12 GiB card, no display attached             ≈ 11.4 GiB
```

(14B KV: 2 × 40 layers × 8 kv_heads × 128 × 1.0625 B = 87,040 B per token.)

Speed: the 2060's memory is about two thirds as fast, so the same model will
generate noticeably slower on it than on the 2080 Super. A 14B model is also
roughly twice the bytes to read per token of an 8B. Expect the second card to
be the **bigger or longer-context lane, not the fast one**.

**The plan (updated 2026-09-24):**

- On the 2060, the longer-conversation lane is **Qwen 3 8B at 32K**
  (7.69 GiB), not the 14B at 16K above. The 14B fits on paper, but 16K is
  the same room the everyday model already has on the main card
  (`jarvis-primary`, 16,384 tokens), so a conversation too long for the
  main card would have been cut down on the 2060 just the same, only more
  slowly. The 8B at 32K has twice the room. (With the 1 GB gap llama.cpp
  keeps free, HARDWARE-PROFILES.md section 3 also puts the 14B at 16K
  slightly over 12 GB.) Measure on the real card before changing this.
- Keep the everyday 8B chat on one card, chosen by Ollama unless you pin one
  (**corrected 2026-10-05**). This line used to read "keep it on the 2080
  Super, where it is fastest". The machine says otherwise: the model is on
  the **12 GB 2060**, which is GPU 0, and the 2080 SUPER is GPU 1 and runs
  the desktop (`MEASURED-2026-10-05-owner-pc.md`). No speed comparison
  between these two cards has been measured on this PC, so this page does
  not make one. With `[compute] primary_gpu` empty, Jarvis does not pin a
  card at all and leaves the choice to Ollama; the Hardware screen's
  "Everyday chat runs on" setting is where you pin one, and it reports which
  card the model is really on rather than assuming one.
- Use the 2060 as the "second, larger-context lane" that
  `backend/jarvis_browser_control.py` says it is waiting for, and for any
  other long-context job. Browser control still stays switched off until that
  lane is actually running and has been measured.
- Splitting one model across both cards stays **off by default** - but since
  2026-09-27 it is a real, built choice, not merely "it works": "One bigger
  model on both cards" in `backend/jarvis_second_card.py`
  (`docs/JARVIS-API.md` §12). Turning it on ties up both cards (it cannot
  run beside the lanes above) and loads `qwen3:14b` at 32K - genuinely
  bigger than anything else in this file. Read from Ollama's and llama.cpp's
  actual source (§12 quotes it): the split is **by each card's free memory,
  not by its speed**, so with this pair most of the model lands on the
  bigger-but-slower 2060, and generation runs close to *its* pace, not
  merely "the slower card's pace for its share" as this line used to say.
  Not measured: the card is installed, but no split lane has been run on it.

**Two more users of that lane (2026-09-30, `docs/JARVIS-API.md` section 108, both
built OFF until that lane is measured).** "Study helper" sends the quiz's
question-writing and marking to the same `qwen3:8b` at 32K lane (nothing extra to fit: it is
the model "Longer conversations" already loads; not measured). "Referee suggestions" loads
**no model** today - it compares logged numbers with targets in code and raises a "tick it?"
card - so it takes none of the 12 GB; the later step that reads a project's changes would use
this lane's model. Marking with the 14B on both cards is not built.

**The alternative: an RTX 2080 Ti 11 GB.** Also Turing, compute capability
7.5, so everything above about drivers and the `q8_0` cache applies. Its
memory is the fastest of the three (about 616 GB/s published, against the
2080 Super's ~496 and the 2060's ~336), so it would generate faster than the
2060 - but it has 1 GB less, and that 1 GB is exactly what the 14B needs:

```
ceiling    11 GiB card, no display attached             ≈ 10.4 GiB
Qwen 3 14B Q4_K_M, q8_0 KV @ 16K   8.42 + 1.33 + 0.63   = 10.38 GiB  ✗ 0.02 spare
Qwen 3 14B Q4_K_M, q8_0 KV @ 12K   8.42 + 1.00 + 0.63   = 10.05 GiB  ~ 0.35 spare
Qwen 3 8B  Q4_K_M, q8_0 KV @ 32K   4.67 + 2.39 + 0.63   =  7.69 GiB  ✓ 2.7 spare
```

(12K: 87,040 B × 12,288 = 1.00 GiB.) 0.02 GiB is not a margin: Ollama's own
estimate under-counts a `q8_0` cache by about 6% (see "The budget"), which
alone is more than that. So on an 11 GB card Jarvis uses **Qwen 3 8B at 32K**
for the longer-conversation lane - twice the main card's context, same model
family, fast memory. The 14B at 12K would fit with little room and gives
less context than the main card's 8B at 16K, so it is not offered.

**Built, and switched off** (2026-09-24): `backend/jarvis_second_card.py`
gives every capable second card of 10 GB and up (the 2060 12 GB and a 2080 Ti
included) the same lane, Qwen 3 8B at 32K (`LONG_BIG` and `LONG_SMALL`,
which are now the same). It starts the second Ollama on that card, and does
nothing until the owner turns a switch on through an approval card. A
conversation moves to that lane only when the lane has more room than the
everyday model (`jarvis_agent.py`). It leaves
`OLLAMA_FLASH_ATTENTION` unset on that second Ollama too, for the reason in
"Setup" above. The owner's guide is [SECOND-CARD.md](SECOND-CARD.md).

**An 8 GB extra card (2026-09-30, calculated, not measured).** The floor is
now 7,680 MiB reported, so a second or third 8 GB card is used. The room
is the same sum as above - total, minus 0.60 GiB the desktop takes (1.10 with
a monitor on the card), minus the 0.75 GiB gap:

```
8,192 MiB card, no monitor   8.00 - 0.60 - 0.75 = 6.65 GiB room
8,192 MiB card, monitor      8.00 - 1.10 - 0.75 = 6.15 GiB room
Qwen 3 8B q8_0 KV @ 16K   4.67 + 1.20 + 0.30 + 0.33 = 6.50 GiB  fits no-monitor, 0.15 spare
Qwen 3 8B q8_0 KV @  8K   4.67 + 0.60 + 0.30 + 0.33 = 5.90 GiB  fits with a monitor, 0.25 spare
Qwen2.5-VL 7B      @  8K   5.59 + 0.23 + 0.63        = 6.45 GiB  fits no-monitor, 0.20 spare (5.59 is a guess)
```

16K is as far as an 8 GB card goes and it equals the main card's 16,384, so
"Longer conversations" (whose whole point is more room than the main card)
is **not offered** on an 8 GB card, and neither is "Browser control", which
needs it. Learning, the Wiki builder and Pictures are offered: they move work
OFF the main card. Pictures is refused when a monitor is on the card (6.45 >
6.15). Two 8 GB cards run two of these at the same time (second and third
lane). 16 GB (room 14.64) and 24 GB (room 22.64) get the same qwen3:8b at
32K plan as a 12 GB card; qwen3:14b at 32K (8.42 + 2.66 + 0.30 + 0.33 = 11.71
GiB) would fit them but is not switched on (see docs/SECOND-CARD.md).
Nothing here is measured: the extra card is installed, but no extra-card lane
has been run.

**Before and after installing:**

1. Check the power supply's label. The two cards plus the 3900X draw a lot
   together; a good 750 W unit is the comfortable size.
2. Plug the monitors into the 2080 Super, so Windows' desktop drawing stays
   off the 2060 and its full 12 GB is free for models.
3. The second slot on many motherboards runs slower (x4 or x8). That only
   slows loading a model, not answering, so it is fine.
4. After installing, run `nvidia-smi` in a terminal. Both cards should be
   listed, with the same driver version. Then redo "Then verify, before
   trusting any of it" above for whatever runs on the new card.

---

## The Coding preset's pooled lane, measured (2026-11-02, amended 2026-11-03 and 2026-11-07)

**Since 2026-11-07 this lane runs on all three cards.** The third card is
installed and measured: the preset asks for the same model at **49,152 tokens**
(the owner's Q2 ruling: the largest window that stays above 75 tok/s), loads
**16.17 GiB with zero spill** across the 2060 and both 2080 SUPERs, decodes at
**83.8 tokens a second** against 60.6 at 32,768 on two cards, and cold-loads in
**31.6 s** against 69.6 s. The 32,768-token row measured 84.93 tok/s, 15.10 GiB
and a 10.884 s load, and is kept as the alternative. The knob is
**`OLLAMA_SCHED_SPREAD=1` in the pooled server's child environment**. The
two-card record below is kept as history; the new measurement, every row
behind it, and what each preset does with the third card are in
`docs/MEASURED-2026-11-07-THREE-GPU.md`.

The Coding preset's model is `qwen3-coder-30b-a3b-ud-q3-k-xl`, about 14.8 GB of
GPU-resident memory. That fits no single card, so its lane is neither
11436 (2060) nor 11435 (2080 SUPER): it is ONE Ollama on **port 11450**,
started on demand by the preset apply with **no card pin**, so the engine sees
every installed card (`jarvis_model_lanes.start_pooled_lane`, reusing
`jarvis_big_coder`'s server, pause, load and restore). `docs/JARVIS-API.md`
§145.1 is the contract. The 2026-11-02 measurement below saw two cards because
two were installed then.

Measured on this PC on 2026-11-02, through that shipped path, with both lane
models paused first and put back afterwards:

| What | Measured |
|---|---|
| Cold load (the model's own `load_duration`) | **32.5 s** |
| Whole apply, pause and restores included | 69.9 s |
| Whole stop, both lane models reloaded | 59.1 s |
| Decode, three fixed coding prompts | **77.5 / 85.3 / 85.6 tok/s** (median 85.3) |
| The model in `/api/ps` | 15,609,312,049 B size, **the same in video memory: zero spill** |
| RTX 2060 while it ran | 11,899 of 12,288 MiB used |
| RTX 2080 SUPER while it ran | 7,674 of 8,192 MiB used |
| After the stop | `qwen3.5:9b ctx=196608` on 11436 and `qwen3:8b ctx=16384` on 11435, both zero spill |

**On 2026-11-02 the zero-spill context on this PC was 16,384, not 28,672.**
Measured as a ladder with every model unloaded, each rung a real cold load; the
whole ladder was measured again on 2026-11-03:

| `num_ctx` | Size | In video memory | Spilled |
|---|---|---|---|
| **32,768 (what the preset asked for then; history)** | **16,513.7 MiB** | **16,190.1 MiB** | **323.5 MiB** |
| 28,672 | 16,114 MiB | 15,902 MiB | **212 MiB** |
| 24,576 | 15,722 MiB | 15,514 MiB | **208 MiB** |
| 20,480 | 15,326 MiB | 15,123 MiB | **204 MiB** |
| 16,384 | 14,886 MiB | **14,886 MiB** | **0** |

**2026-11-03 (history, superseded 2026-11-07): the preset moved to 32,768 and
accepted the measured 323.5 MiB.**
Every rung above 16,384 spills (20,480 at 203.5 MiB, 24,576 at 207.5, 28,672 at
211.5), and 32,768 - the largest rung measured to load on this PC - loaded at
**16,513.7 MiB with 323.5 MiB in system RAM**, against 16,384 at 14,886.2 MiB
with none. Cold load was 36.0 s against 37.0 s, and decode was 80.36 against
79.88 tok/s median on the three prompts - inside this model's own run-to-run
noise. The 8 GB card is what runs out first (at 28,672 it was at 7,529 of
8,192 MiB; at 32,768, 7,591), which is why the spill jumps by 112 MiB rather
than growing smoothly. The owner accepted that measured cost, so:

- the preset asks for **32,768** (`jarvis_model_lanes.POOLED_CTX`; the preset
  records `context_measured = 32768`, `spill_gib = 0.3`, and keeps
  `context_zero_spill = 16384` as the historical fact);
- the pooled start passes `load_coder(..., allow_spill=...)` the one number
  **352 MiB** (`POOLED_SPILL_ALLOWANCE`) - the 323.5 MiB measurement
  (`POOLED_SPILL_MEASURED_MIB`) plus about 9%, so the same split reported
  slightly differently still loads, and nothing larger is accepted;
- **zero spill is still the rule by default and for every other caller.**
  `load_coder` with no allowance refuses any spill at all (unchanged), the
  big-coder mode's 28,672-token rung and its zero-spill check are unchanged,
  and a load that spills past the 352 MiB cap is refused (503) in the machine's
  own words, naming both the spill and the allowance.

The 2026-10-18 measurement's 28,672 rung was kept in `jarvis_big_coder.NUM_CTX`
until 2026-11-07, when the mode's own measured rung moved to 49,152. `OLLAMA_SCHED_SPREAD=1` was tried at 28,672
and did not change the split (212 MiB spilled, 68.4 tok/s). The whole
measurement, the method and the undo are in
`docs/MEASURED-2026-11-02-POOLED-LANE.md` - the 2026-11-02 numbers above, and
the 2026-11-03 amendment at its end. The extra 16,384 tokens the new window adds
over the old 16,384-token window were not filled by that measurement (every
prompt was 40-43 tokens), so a
genuinely long conversation that uses them is still unmeasured - the decode
speed of a nearly-full 32,768-token window was not measured either - and a
15-minute real coding test runs after this is deployed.

A sixth Ollama, or a model left loaded on port 11434 (Ollama's own default
server), does not need to be stopped: measured on the same day, that server's
model held no video memory when its process was idle, and freeing it changed
the 2060's used memory by 89 MiB.

### 2026-11-07: three cards, measured, and the lane uses them

The third card was installed and the whole preset matrix was measured again on
2026-11-07, each config on its own throwaway `ollama serve` on port 11451. The
decisive pair is the same model at the same 32,768-token window, measured the
same way on the same day:

| | Two cards (2060 + display 2080S) | Three cards (all) |
|---|---:|---:|
| Decode | 60.58 tok/s | **84.93 tok/s** |
| Cold load | 69.611 s | **10.884 s** |
| `/api/ps` size | 14.84 GiB | 15.10 GiB |
| Spilled | 0.0 GiB | **0.0 GiB** |
| Cards `nvidia-smi` saw | 0, 2 | **0, 1, 2** |

**The lane ships at 49,152 tokens:** 83.82 tok/s, 16.17 GiB, zero spill and a
31.561 s cold load - 1.3 % slower than the 32,768 row above and 1.07 GiB larger,
for 16,384 more tokens; both clear the 75 tok/s bar and the ruling asks for the
larger window.

The three-card split is real per card, not just an aggregate: after the cold
load `nvidia-smi` read **6,988 MiB** on the 2060, **4,537 MiB** on the headless
2080 SUPER and **5,717 MiB** on the display 2080 SUPER. On two cards the same
window put 9,360 MiB on the 2060 and 7,467 MiB on the display card, with the
headless card at 0.

- **The window ships at 49,152.** 32,768 measured 84.93 tok/s at 15.10 GiB with
  a 10.884 s cold load - 1.3 % faster for 1.07 GiB less - and is the recorded
  alternative; 49,152 clears the bar with 16,384 more tokens. 65,536 loaded at
  17.25 GiB with zero spill but decoded at **59.06 tok/s**, below the 75 tok/s
  bar, so it is not chosen.
  98,304 read 88.69 tok/s at 19.41 GiB and is recorded, not chosen; **131,072
  FAILED** (`server: server exited 4294967295`) and nothing is claimed about it.
- **`OLLAMA_SCHED_SPREAD=1` is what makes it fast, not what makes it fit.**
  Without it the same three cards were all used and the model decoded at
  **56.82 tok/s** instead of 84.93. That is different from the 2026-11-02
  two-card experiment above, where the variable did not change the split - on
  two cards there was nothing to spread.
- **The two-card control does not match this page's 2026-11-03 row, and the
  record says so.** Tonight's two-card run read **14.84 GiB and zero spill**
  against the 16,513.7 MiB / 323.5 MiB recorded above, and a 69.611 s cold load
  against 36.0 s. The measured page states plainly that it does **not** explain
  the difference; the older number stays here as history, and the claim the new
  work makes is the one it measured - zero spill on three cards.

**Every other preset keeps its measured single-card configuration.** The
everyday 9B measured **44.11 tok/s at a 262,144-token window on three cards**
(15.57 GiB, zero spill) against **42.01 tok/s at 196,608 on the 2060**, and it
stays on the 2060: an always-on model across all three cards is exactly the
pause the Coding preset's heavy mode exists to admit to, and 2.1 tokens a
second is not a reason to pay it. Fast measured **76.20 tok/s on the display
2080 SUPER against 65.85 across three cards**, so spreading it over the third
card would make it slower - but on the **headless 2080 SUPER alone** it read
**85.29 tok/s**, and the vision model read **63.35** there. A dedicated
headless-card lane is therefore a measured gain, and it is deferred because it
needs a new lane-start path on port 11438, not because the numbers are against
it. The measured page has every row, the failed rows and what was not measured.

**Measured but not shipped: the heavy presets.** `gemma4:31b-it-qat` fits -
18.81 GiB at 32,768, 18.53 GiB at 24,576 and 18.25 GiB at 16,384, all zero
spill - but decodes at **15.4-15.6 tok/s** with a 48-72 s cold load, and the
uncensored 27B fits at 17.38 GiB and reads **17.96 tok/s**. The pooled lane
still carries ONE fixed model, so `deep_think` and `creative` wait for the Wave
8 refactor; the measured page and the decision fragment say the same.

### The 2026-11-05 plan for the third GPU, and where the measurement left it

**The rows and numbers in this subsection are the plan's own best-effort
research, written down on 2026-11-05 so it lives in git instead of only in
untracked scratch notes.** Its rule was that no preset row changes until the
third card is physically installed and measured on this PC. **The card is now
installed and measured (2026-11-07)**, so this subsection records where that
left the plan:

- **What the measurement took:** the Coding preset's lane moved to all three
  cards, as the section above records. It did **not** take the plan's model
  change - the preset keeps `qwen3-coder-30b-a3b-ud-q3-k-xl` and widens it to
  49,152.
- **What it did not take:** `deep_think` and `creative` are **not** presets and
  nothing here is switched on. The pooled lane carries ONE fixed model, so
  parameterising it for three models is Wave 8 work. All three of the plan's
  models have now been measured on this PC - the 31B, the Q4 coder, and the
  uncensored 27B at 17.38 GiB and 17.96 tok/s - and none of them becomes a
  preset tonight. The measured page has the numbers.

Eight presets keep the model, card and window they have today; only Coding
changes lane and window, and no preset changes model tonight. The
quantisation is what each file reports to `ollama show`.

| Preset | Model and quantisation | Context | Lane | Planned change |
|---|---|---:|---|---|
| `general` | `qwen3.5:9b`, Q4_K_M | 196,608 | 2060 12 GB, port 11436 | none - unchanged |
| `general_uncensored` | Huihui 9B abliterated, Q4_K_M | 196,608 | 2060 12 GB, port 11436 | none - unchanged |
| `coding` | `qwen3-coder:30b-a3b-q4_K_M`, Q4_K_M | 32,768 | pooled, port 11450, all three cards | **the one model change** (option A); option B keeps today's `qwen3-coder-30b-a3b-ud-q3-k-xl` (file reports Q3_K_M) at 49,152 |
| `agentic_vision` | `qwen3.5:9b`, Q4_K_M | 16,384 | 2060 12 GB, port 11436 | none - unchanged |
| `fast` | `qwen3.5:4b`, Q4_K_M | 16,384 | 2080 SUPER, port 11435 | none - unchanged |
| `reflect` | `qwen3.5:9b`, Q4_K_M | 196,608 | 2060 12 GB, port 11436 | none - unchanged |
| `pictures` | `qwen3.5:9b`, Q4_K_M | 32,768 | 2060 12 GB, port 11436 | none - unchanged |
| `documents` | `qwen3.5:9b`, Q4_K_M | 196,608 | 2060 12 GB, port 11436 | none - unchanged |
| `browser` | `qwen3.5:9b`, Q4_K_M | 196,608 | 2060 12 GB, port 11436 | none - unchanged |
| `deep_think` (new) | `gemma4:31b-it-qat`, Q4_0 (as the file reports it) | 32,768 | pooled, port 11450, all three cards | new heavy preset; refuses until measured |
| `creative` (new) | `orcarouter/Qwen3.8-27B-Uncensored:q4_K_M`, Q4_K_M | 32,768 | pooled, port 11450, all three cards | new heavy preset; refuses until measured |

The arithmetic that makes the plan plausible is calculated, not measured. The
three cards give **23.45 GiB** of room by the formula above (28.00 total, minus
2.30 the desktop takes and 2.25 of fit gap); a second estimate from the one
real measurement is 22.65 GiB, and the plan treats 23.45 as the optimistic end.
At 32,768 the Q4 coder is calculated at **19.50 GiB**, `gemma4:31b-it-qat` at
**19.06 GiB** and the 27B at **18.21 GiB** - about 1.32, 1.46 and 1.75 GiB per
card. The owner's preference is at least 1.5 GiB/card: the Q3 tag at 49,152 is
the only rung that meets it (**17.72 GiB** calculated), and the plan still
recommends the Q4 coder at 32,768 because the owner asked for an upgrade and a
better quant keeps the measured window and work pattern.

**The measured decision of 2026-11-07 did not take that model change.** The
shipped Coding preset keeps the Q3 tag, moves the lane to three cards and
widens the window to 49,152: the Q4 build measured **87.47 tok/s at 19.52 GiB
with zero spill** at 32,768 and **93.08 tok/s at 20.60 GiB** at 49,152, but its
coding quality was never re-run on the 6/6 rubric (measured on the q3 weights),
so it is an unmeasured quality claim and not taken. The plan's option-B rung,
the Q3 tag at 49,152, is what ships: **83.82 tok/s at 16.17 GiB, zero spill**,
1.3 % slower than 32,768 and 1.07 GiB larger for 16,384 more tokens - and it
clears the 75 tok/s bar the ruling set.

**Neither app claims any of these figures.** `jarvis_presets.hardware_block()`'s
own `future_not_a_preset` line - which both apps render on their hardware plate -
still says the 27B is a future "max quality" experiment, "not a preset", and
"no figure is claimed until it is measured"; that line is deliberately left
exactly as it is. The numbers above are this plan's arithmetic, written down so
the research is not lost, and not something either app tells the owner.

**What must be measured before any of it is trusted, in this order:**

1. **The machine.** `nvidia-smi` must show three cards - 12,288 / 8,192 / 8,192
   MiB, one driver version, `display_active` on exactly one 2080 SUPER. If that
   is not what it says, stop.
2. **The pooled lane sees all three.** After a Coding apply, `/api/ps` and the
   server log's `offloaded N/N layers to GPU` must show the model spread over
   three cards; `nvidia-smi` per-card memory is the second proof.
3. **Every model must report `size == size_vram` - 100% on the cards.** A load
   that does not is a fail, and `load_coder` unloads it and says so in words.
   The one measured exception *was* the Coding window on two cards, allowed its
   323.5 MiB spill plus about 9% (352 MiB); since 2026-11-07 that same window
   measures **zero spill on three cards**, so on this PC every load must again
   be exact. The allowance stays in the code as the narrow rule it was, so a
   split reported slightly differently still loads.
4. **Decode speed** on the same three fixed coding prompts, reported as a
   median of three, for every new or changed model. Two of the plan's models
   now have a measured speed on this PC (the section above); the 27B has none,
   and this plan gives none.
5. **Cold load time** over the third card's link, timed with and without the
   third card in the pool.
6. **The 12 GB card still holds the 9B at 196,608 with the third card in the
   box**, because Windows may re-balance desktop memory across three adapters.
   That measured figure is 9.17 GiB; if it moves, every single-card row in the
   table above is affected.

The ladder is walked one cold load at a time, stopping at the first rung that
spills past 352 MiB: the Q4 coder at 32,768, then 49,152 only if the first
passed with room, then the Q3 tag at 49,152, then `gemma4:31b-it-qat` at
32,768, then the 27B at 32,768.

---

## The picture reader on the processor (one-card PCs, 2026-09-29)

The owner's decision of 2026-09-29: a PC with ONE graphics card may switch on a
slow "picture mode" for "Look at this" and "Watch with me" - a small picture
model, **MiniCPM-V 4.6** (OpenBMB, 1.3 B parameters, Apache-2.0), running on the
**processor**, so it uses **0 GB of graphics memory** and the everyday chat model
on the 8 GB card is not touched. It reverses the earlier "one card reads the
screen's words only", and it is **off by default**.

How it is kept off the card, and why it does not share the everyday Ollama:

- It runs in its own `ollama serve` on 127.0.0.1:11437 (this PC only; not
  11434, not 11435 or 11436, which are the second card's lane and the everyday
  lane's, and not 11438, the third card's own default) with
  `CUDA_VISIBLE_DEVICES=-1` (Ollama's own documented way to force the
  processor: "use an invalid GPU ID (e.g., "-1")", docs/gpu.md), `OLLAMA_VULKAN=0`,
  AMD's variables at -1, one model and one request at a time, and
  `OLLAMA_NO_CLOUD=1`. A separate process has no shared scheduler with the
  everyday one, so it cannot push the chat model off the card - which asking
  the everyday Ollama for `num_gpu 0` could not promise (unverified).
  Every request also says `num_gpu 0`, and after a look the copy is asked what
  it holds (`/api/ps`): any graphics memory in use stops it and says so.
- The model is downloaded by ONE PowerShell line the owner pastes
  (`ollama pull`, from Ollama's library); the backend never downloads
  anything. **Unverified:** the exact Ollama tag (`minicpm-v:4.6` is a guess
  from the scout's note - ollama.com could not be reached), its download size,
  whether Ollama's runner accepts it on the processor, and its speed. What was
  checked: llama.cpp has `docs/multimodal/minicpmv4.6.md` (a Qwen3.5-based
  1.3 B language model with a SigLIP vision tower and a window-attention
  merger).
- **Speed is not known until the owner measures it.** The same line then runs
  `py -3 jarvis_screen_picture.py --measure`, which uses a made-up picture (never
  the owner's screen) and prints seconds per look and Ollama's `prompt_eval_count`
  with and without the picture, and saves them; the setting shows that number
  and nothing else. Threads default to half of this PC's, so chat keeps the rest
  (`[screen_picture] threads`, unmeasured).
- If the model is missing, too slow (`timeout_s`, 240 s by default), or fails,
  the note beside the answer and the everyday model both say so, and the
  answer uses the words only.

---

## If you are thinking about a second card

A Tesla P100 has been suggested. **I would not buy one for this workload**, and
the reason is specific rather than general.

**The P100 cannot run quantised inference well.** GP100 (sm_60) is the one
Pascal chip with **no `DP4A` instruction**. llama.cpp's quantised matmul
kernels are built around the assumption that int8 is cheap and fp16 is not —
because the Pascal card that mattered commercially was the P40 (sm_61), which
has `__dp4a` and crippled fp16. GP100 is the exact inverse: full-rate fp16,
no DP4A. So on a P100 the Q4_K_M path falls back to emulation and cuBLAS, and
the one thing the card is genuinely good at goes unused. There is a
[community patch set](https://github.com/shinbunbun/llama-cpp-p100-patches)
that exists solely to work around this, which tells you how well it works out
of the box.

It also misses llama.cpp's fast fused-attention kernels: those need the Turing
MMA path (`GGML_CUDA_CC_TURING` is 750) and the P100 is 600. It passes
Ollama's flash-attention gate — which only excludes 7.2 — and then takes the
slower vector kernel.

The practical problems on top of that, all verified:

| | |
|---|---|
| **Power** | CPU/EPS 8-pin, **not** PCIe 8-pin. Needs an adapter cable. |
| **Cooling** | Passive heatsink with no fan. Designed for server chassis airflow. In a desktop it needs a bolt-on blower shroud or it throttles and then dies. |
| **Display** | No outputs at all. Compute only. |
| **Drivers** | Windows 11 drivers do exist. The risk is that NVIDIA installs **one** driver for all NVIDIA GPUs in a box: Pascal left the Game Ready branch in October 2025 (quarterly security updates only, to 2028) while your Turing card is on the current branch. Two cards on two support branches in one Windows install is the thing to verify before money changes hands, not after. |

**If you want more VRAM, buy one newer card, not this one.** A single 16GB
Ampere-or-later card gives you real tensor cores, the MMA attention path, DP4A,
one driver branch, a display output, a PCIe power connector and a fan. The
P100's 16GB of HBM2 at ~732 GB/s is genuinely fast memory attached to a chip
that cannot use it for the arithmetic this workload actually does.

The one case for a P100 is fp16 work — unquantised models, or training — where
its 2:1 FP16 rate is real and unusual for Pascal. That is not what Jarvis does.

## Sources

Every Ollama and llama.cpp claim above was read from source rather than
inferred:

- `nextLowerAutoNumCtx`, `generationBatchSurcharge` — [ollama/server/sched.go](https://github.com/ollama/ollama/blob/main/server/sched.go)
- `cudaFlashAttentionSupported` — [ollama/ml/device.go](https://github.com/ollama/ollama/blob/main/ml/device.go)
- Modelfile `SYSTEM` suppression — [ollama/server/routes.go](https://github.com/ollama/ollama/blob/main/server/routes.go)
- system-message re-collection on truncation — [ollama/server/prompt.go](https://github.com/ollama/ollama/blob/main/server/prompt.go)
- `GGML_CUDA_CC_TURING` — [llama.cpp/ggml/src/ggml-cuda/common.cuh](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-cuda/common.cuh)
- *2026-09-27, "One bigger model on both cards" (`docs/JARVIS-API.md` §12
  has the full quotes):* `selectLlamaServerPlacement`, `bestSingleGPUFit` —
  [ollama/server/sched.go](https://github.com/ollama/ollama/blob/main/server/sched.go);
  `appendMainGPUArgs` — [ollama/llm/llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go);
  `load_tensors`'s free-memory split — [llama.cpp/src/llama-model.cpp](https://github.com/ggml-org/llama.cpp/blob/master/src/llama-model.cpp),
  read at Ollama `16b4376a` (2026-09-26) / llama.cpp `b11081` = `161755f`.

The VRAM figures are arithmetic from published model geometry, shown above so
it can be checked. The one measured performance anchor — 59.8 tok/s for Llama
3.1 8B Q4_K_M on a 2080 Super — came second-hand and is not independently
confirmed. **Nothing here was benchmarked on your machine.** The verification
step exists for that reason.
