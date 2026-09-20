# What runs on the GPU, and how much context it gets

RTX 2080 Super, 8 GB, Turing sm75. Ryzen 9 3900X. Windows 11.

Read this if you are about to change models, change context length, or wonder
why a long conversation gets strange.

---

## The thing that is wrong right now

**The deployed context is 4096 tokens, and nothing in the codebase chose it.**

`jarvis_hud._build_payload` sends `model`, `messages`, `stream`, `temperature`
and `max_tokens`. Grep the file for `num_ctx` and there is no hit. It posts to
`JARVIS_URL/v1/chat/completions`, an OpenAI-compatible endpoint, and the
OpenAI compat surface has no field for context length — so there is no request
the HUD could send that would set it even if someone wanted to.

So Ollama picks. `server/sched.go`:

```go
func nextLowerAutoNumCtx(numCtx int) (int, bool) {
	switch {
	case numCtx > 32768: return 32768, true
	case numCtx > 4096:  return 4096, true
	default:             return 0, false
	}
}
```

An 8B Q4 at 32768 with an f16 cache needs about 9.8 GiB. It does not fit, so
the ladder drops to 4096, and 4096 is the bottom rung.

Two consequences, both currently live:

- **A 6,000-token prompt does not fit.** It is roughly 1.5× the window.
- **`max_tokens: 2048` eats half of what is left.** Ollama's compat layer maps
  `max_tokens` to `num_predict`, so at `num_ctx 4096` the usable prompt before
  llama.cpp starts shifting context mid-generation is about 2048 tokens.

Everything anyone has planned on this machine about context has been theory.

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
card. Without it, everything below reverts to the f16 columns.

---

## Setup

One time, in the environment — a Modelfile cannot express these:

```powershell
setx OLLAMA_KV_CACHE_TYPE q8_0
setx OLLAMA_KEEP_ALIVE -1
```

Then:

```powershell
ollama create jarvis-primary -f backend\jarvis-primary.Modelfile
```

`OLLAMA_KEEP_ALIVE=-1` is deliberate and is not the obvious choice. Ollama's
default is five minutes. With one resident model there is nothing an idle timer
can make room *for*; its only effect is a ~6 second stall on the first word
after you step away, which in the voice loop is the worst possible moment.

Do **not** set `OLLAMA_FLASH_ATTENTION` — to `0` or to `1`. Auto is correct;
forcing `1` removes llama.cpp's per-model fallback.

## Then verify, before trusting any of it

```powershell
$env:OLLAMA_DEBUG=1; ollama run jarvis-primary "hi"
```

Find the `llama-server` argv in the log and look for `--flash-attn`.

- Reads **auto** or **on** → you are running the configuration below.
- Reads **off** → `q8_0` KV is being silently ignored, the KV term is 2.25 GiB
  instead of 1.19 GiB, and `jarvis-primary` **spills into system RAM**, where
  it runs at roughly a fifth of the speed and nothing tells you. Take the
  fallback.

**Fallback if it reads off:** `qwen2.5:7b` at `num_ctx 16384` on a plain f16
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

`q8_0` is 34 bytes per 32 values — **1.0625** bytes per element, not 1.0. Worth
knowing because Ollama's own pre-flight estimator rounds it to 1.0, so it
under-counts a quantised cache by about 6%. On a 6.9 GiB ceiling at 16K that
is ~70 MiB of optimism.

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
| **DeepSeek-R1-Distill-Qwen-7B** | Qwen 3 8B's thinking mode covers the same ground from a model already loaded. Reasoning traces plus a strict JSON schema is also a known-bad pairing: the grammar forbids the `<think>` block the model is trained to emit first. |
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

**Keep the embedder on the CPU.** bge-small is ~130 MB through fastembed/ONNX.
On the GPU it would cost ~0.2 GiB *and* contend for the same SMs mid-utterance.
It is on the 3900X's 12 cores today; that is correct, and it is written down
here so it stays a decision rather than a default.

**`jarvis_persona.memory_top_k` is dead.** Personas declare 4, 6, 8, 10 or 16
and every one of them gets 5, because the number was hardcoded in the search
call. `memory-prefix.patch` lifts it to `MEMORY_K` / `JARVIS_MEMORY_K`, which
names it but does not yet read the persona. Honouring `memory_top_k=16` would
roughly triple the injected block, from ~100 to ~320 tokens — small in a 16K
window, and much cheaper than it was before that patch moved the block out of
the prefix.

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

The VRAM figures are arithmetic from published model geometry, shown above so
it can be checked. The one measured performance anchor — 59.8 tok/s for Llama
3.1 8B Q4_K_M on a 2080 Super — came second-hand and is not independently
confirmed. **Nothing here was benchmarked on your machine.** The verification
step exists for that reason.
