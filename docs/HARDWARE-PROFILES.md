# Hardware profiles: any 8 GB card, up to two cards and 24 GB

**Status: built 2026-09-25 (section 7 says what, and where the build differs
from this design); still nothing measured on a real PC.** Written
2026-09-24. Every memory figure is *calculated, not measured* until the
Hardware screen's Measure has a row for it (section 4.7). Nothing changes on
the owner's PC until a setup is chosen there, and then only one approval
card at a time.

---

## The short version

**What it is for.** Today Jarvis is hand-tuned for one card, the RTX 2080
Super (8 GB), and the second-card features are hand-tuned for one planned
card, the RTX 2060 12 GB. This design makes Jarvis work out a sensible setup
for **any single 8 GB card, and any pair of cards up to 24 GB in total**,
and offer it to you as three choices in plain words:

- **Fastest answers** - a smaller, quicker everyday model.
- **Smartest answers** - the biggest everyday model your cards can hold,
  even if that makes answers slower.
- **Most features** - a balanced everyday model, plus pictures and long
  conversations wherever there is room left over.

Jarvis finds your cards by itself, shows the three choices with a memory bar
for each card, and says what each choice switches off and why. **Nothing
changes until you pick one**, and picking one raises the same approval cards
you already know (model install, model switch). Settings Ollama reads at
start-up are shown as one PowerShell line for you to run. Nothing is applied
silently.

**Five things I found in Ollama's and llama.cpp's source that change the
plan.** Said plainly, most important first. Section 3 has the detail and the
evidence for each.

1. **Ollama no longer decides how much fits - llama.cpp does, and it keeps
   1 GB of every card empty on purpose.** Ollama now runs llama.cpp's own
   server program, which checks free memory at load time and, if a model
   would leave less than 1 GB free, quietly moves part of the model to the
   processor (much slower). By that rule, today's `jarvis-primary` (Qwen 3
   8B with room for 16,384 tokens - a token is a word or part of a word)
   **probably does not fully fit on the
   2080 Super** - my arithmetic says it is about 0.6 GB over, which would put
   roughly 4 of its 37 layers on the processor. This is calculated, not
   measured; section 4.7 has the two-line check.
2. **Pinning your everyday Ollama to one card with `CUDA_VISIBLE_DEVICES`
   is probably not enough.** Ollama for Windows also reaches cards through a
   second route (Vulkan). That route ignores `CUDA_VISIBLE_DEVICES`, and
   Ollama puts a model on whichever card has the *most free memory*, not the
   fastest - so with the 2060 fitted, everyday chat could land on the 2060
   anyway. The fix is one more setting (`OLLAMA_VULKAN=0`) in the same
   one-line command. Read from source, not tested.
3. **The compact conversation-memory format (`q8_0`) now either works or
   fails loudly - it is no longer "silently ignored".** MODEL-TOPOLOGY.md's
   verify step says an "off" reading means the setting was ignored and the
   model spills. In today's code, llama.cpp switches flash attention on by
   itself when the compact format is asked for, and if flash attention has
   been forced off, the model refuses to load. That also means the
   second-card switch `[second_card] flash_attention = "off"` would stop the
   second card from loading anything.
4. **One big card needs no second Ollama.** On a single 16 or 24 GB card,
   the extra models (pictures, long conversations) can sit beside everyday
   chat in the *same* Ollama. The second-card module today only works with a
   *second physical card*, so a PC with one big card gets none of those
   features. Two cards still want two Ollamas (Ollama's own "which model to
   unload" choice ignores which card a model is on).
5. **Two older numbers are now wrong, in opposite directions.** Ollama's
   own memory estimate now *over*-counts the compact format (it assumes the
   uncompressed size), not under-counts it by 6%. And the 12 GB plan for the
   second card (Qwen 3 14B with room for 16,384) is about 0.03 GB over once
   llama.cpp's 1 GB gap is counted; 12,288 fits.

**What I would like you to decide** is in section 5: four short questions.

---

## Contents

1. [What I checked, and where it came from](#1-what-i-checked-and-where-it-came-from)
2. [Findings from source](#2-findings-from-source)
3. [What this means for today's setup](#3-what-this-means-for-todays-setup)
4. [The design](#4-the-design)
5. [Decisions for the owner](#5-decisions-for-the-owner)
6. [Risks and unknowns](#6-risks-and-unknowns)
7. [Build plan](#7-build-plan)
8. [Appendix: every number used](#8-appendix-every-number-used)

---

## 1. What I checked, and where it came from

Read from source, shallow clones made 2026-09-24:

| Source | Commit | Notes |
|---|---|---|
| `github.com/ollama/ollama` | `b2da9e4` (2026-09-23) | main branch. `LLAMA_CPP_VERSION` says it builds llama.cpp **`b11081`**. |
| `github.com/ggml-org/llama.cpp` | tag `b11081` = `161755f` (2026-09-21) | the version Ollama builds. Also master `9710a32` for two files noted as such. |
| `github.com/QwenLM/Qwen3` | `7a2f61f` | `Qwen3_Technical_Report.pdf`, page 3, Table 1. |
| Model `config.json` copies | see 2.8 | **huggingface.co, ollama.com, learn.microsoft.com and docs.nvidia.com are all blocked from here** (the proxy refused the connection). Each model's `config.json` was read from a copy in a public GitHub repository instead, named in 2.8. A copy can differ from the original; I say where that matters. |
| `github.com/amd/gaia` | `f136d1c` | how AMD's own tool reads a card's memory on Windows. |
| `MicrosoftDocs/win32` (via GitHub code search) | `e103fa4` | `Win32_VideoController.AdapterRAM` is a `uint32`. |

File references below are `repo:path:line` at those commits. Ollama paths
are relative to the Ollama repo; llama.cpp paths are at `b11081` unless they
say master.

**What I could not do here:** run Ollama, run anything on a GPU, read
ollama.com (so no real download sizes and no real model tags), read NVIDIA's
or Microsoft's own documentation pages, or run the PowerShell lines through
`/opt/pwsh` (the sandbox refused to start `pwsh`; the lines in this document
were checked by reading, for PowerShell 5.1).

---

## 2. Findings from source

### 2.1 How Ollama finds graphics cards on Windows

**How it looks.** Ollama no longer has its own NVIDIA or AMD detection
code. At start-up it runs llama.cpp's server program briefly, once per
bundled back-end folder (CUDA 12, CUDA 13, ROCm, Vulkan), reads the list of
devices it prints, and stops it (`discover/llama_server.go:26-41`, `:55-67`;
the loop over folders is `discover/runner.go:81-124`). A Windows-only probe
then fills in details from the drivers directly (`discover/native_probe_windows.go:28-58`:
`nvcuda`, the HIP runtime, `nvml.dll` for the NVIDIA driver version).

**Which cards count**, and what removes one:

| Card family | Route | Gate, from source |
|---|---|---|
| NVIDIA | CUDA | The CUDA build must contain the card's architecture, else it logs `skipping CUDA device — compute capability not in compiled architectures` (`discover/llama_server.go:290-300`). Windows CUDA 12 build: `50-virtual;52-virtual;60-virtual;61-virtual;70;75;80;86;89;90;90a;120`; Windows CUDA 13 build: `75-virtual;80-virtual;86-virtual;89-virtual;100-virtual;120-virtual` (`llama/server/CMakePresets.json:79`, `:111`). So **Pascal (GTX 10xx, 6.1) runs only on the CUDA 12 build, as just-in-time compiled code**, and needs driver 570 or newer (`docs/gpu.mdx:6-7`; `discover/cuda_compat.go:64-72`). Turing and newer are in both. |
| AMD | ROCm (HIP) | Windows builds target `gfx1030;gfx1100;gfx1101;gfx1102;gfx1150;gfx1151;gfx1200;gfx1201` (`llama/server/CMakePresets.json:192`, preset `rocm_v7_1_windows`, which the release uses: `.github/workflows/release.yaml:148-151`, `scripts/build_windows.ps1:743-744`). A card whose `gfx` target has no matching rocBLAS kernels is dropped with `dropping ROCm device — no rocblas support for gfx target` (`discover/amd.go:445-476`). An old AMD driver logs `AMD driver is too old` (`discover/amd.go:478-487`). **RX 7600 is `gfx1102`: supported. RX 6600 is `gfx1032`: not in the list, so it falls to Vulkan.** Ollama's own docs table for Windows lists only RX 7000 cards (`docs/gpu.mdx:81-84`), while the build also includes `gfx1030` (RX 6800/6900 class) - the docs and the build disagree; I did not verify which a real install honours. |
| Intel Arc | Vulkan only | No SYCL/oneAPI build exists in the tree (searched the presets, build scripts and Go code). Vulkan is built into the Windows release (`.github/workflows/release.yaml:154-156`) and on by default (`envconfig/config.go:234`, `:363`; `docs/gpu.mdx:141-146`). |
| Any card | Vulkan | Also picks up NVIDIA and AMD cards. A Vulkan entry that duplicates a CUDA or ROCm card (same PCI id, or same name and similar memory) is dropped in favour of CUDA/ROCm (`ml/device.go:180-227`, `:379-390`; `discover/runner.go:209-251`). **A card hidden from CUDA is not a duplicate of anything, so its Vulkan entry stays** - see 2.3. |
| Integrated GPUs | any | Dropped unless allowed (`discover/runner.go:382-412`, message `dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1`). |

**What Ollama logs.** One line per usable card, at normal (INFO) level,
sorted in the order the scheduler prefers them (`discover/types.go:19-46`):

```
inference compute id=0 filter_id=GPU-... library=CUDA compute=7.5 name=CUDA0
  description="NVIDIA GeForce RTX 2080 SUPER" libdirs=cuda_v13 driver=13.0
  pci_id=0000:0a:00.0 type=discrete total="8.0 GiB" available="6.9 GiB"
```

(Field names from `discover/types.go:32-45`; the values above are made up.)
For AMD, `compute` is the `gfx` name (`ml/device.go:95-101`). Right after
it, Ollama logs `vram-based default context` with `total_vram` and
`default_num_ctx` (`server/routes.go:2096-2115`), and, if you set a
card-hiding variable, `user overrode visible devices` (`discover/runner.go:709-728`).

**Where the log is on Windows:** `%LOCALAPPDATA%\Ollama\server.log`
(`app/server/server_windows.go:19`). Ollama's own desktop app reads the
`inference compute` lines out of that file the same way this design
proposes to (`app/server/server.go:301-310`).

**No API lists the cards.** The routes are `server/routes.go:1927-1980`;
none returns devices. The closest is `/api/ps`, which reports, per loaded
model, `size`, `size_vram` and `context_length` (`api/types.go:854-863`) -
`size_vram` smaller than `size` means part of the model is on the processor.
(`/api/experimental/model-recommendations` exists but fetches a list from
ollama.com and is not about your hardware: `server/model_recommendations.go:23`,
`:373-408`. Jarvis must not use it.)

**Card ids.** Ollama's own ids are plain numbers in list order
(`discover/llama_server.go:321-323`). When you set `CUDA_VISIBLE_DEVICES`
to a card's `GPU-...` id, Ollama carries that exact text through to the
program it starts (`discover/runner.go:589-610`), so the id works, as
`docs/gpu.mdx:42-46` recommends. Vulkan accepts numbers only
(`envconfig/config.go:360`).

### 2.2 Flash attention and the compact conversation memory (KV cache)

*Plain words first:* the "KV cache" is the model's memory of the
conversation so far. `q8_0` stores it in about half the space. llama.cpp
can only read `q8_0` through its "flash attention" routine.

**What Ollama does.** `OLLAMA_FLASH_ATTENTION` unset means "auto" when every
card passes Ollama's gate, "off" when one does not; set to 1 or 0 it forces
on or off (`llm/llama_server.go:599-625`). The gate (`ml/device.go:273-304`):
CUDA needs compute capability 6.0 or more, excluding 7.2 (Jetson Xavier);
ROCm, Vulkan, Metal and CPU always pass. `OLLAMA_KV_CACHE_TYPE` is passed
straight through as `--cache-type-k/--cache-type-v`
(`llm/server.go:109`, `llm/llama_server.go:396-399`) - **one setting for
every model in that Ollama** (`docs/faq.mdx:356-358`). Default is `f16`
(`envconfig/config.go:319`).

**What llama.cpp then does** (`src/llama-context.cpp`, b11081):

- Asked for a compact (`q8_0`) cache with flash attention on "auto", it
  **forces flash attention on** and logs `enabling flash_attn since it is
  required for quantized V cache` (`:3732-3736`).
- With flash attention forced **off**, it **refuses to create the model's
  context** - `quantized V cache requires flash_attn to be enabled`
  (`:3737-3741`; also `:465`). The model does not load. It is **not**
  silently ignored any more.
- On plain "auto" (no compact cache) it test-runs the routine and switches
  it off if the card cannot do it (`:41`, `:548`, `:556`). That safety check
  is skipped when the compact cache has forced it on.

**Per architecture** (CUDA kernels: `ggml/src/ggml-cuda/fattn.cu`):

| Cards | Flash attention path | `q8_0` KV | Recommendation |
|---|---|---|---|
| Pascal 6.1 (GTX 1070/1080) | generic "tile"/"vector" kernels, no tensor cores (`fattn.cu:704`; Turing path starts at `:626`, `GGML_CUDA_CC_TURING` = 750 at `ggml/src/ggml-cuda/common.cuh:53`) | supported (`fattn.cu:513`) | `q8_0`, best effort. Slower kernels; measure. |
| Turing 7.5 (RTX 20, GTX 16) | tensor-core ("MMA") kernels | supported | `q8_0` |
| Ampere 8.x, Ada 8.9, Blackwell 12.0 | tensor-core kernels (Ada and newer use a vector kernel for one-word-at-a-time decoding) | supported | `q8_0` |
| AMD RDNA3 via ROCm (RX 7000) | same CUDA code compiled for HIP; tile or WMMA kernels | supported (same code) | `q8_0`, best effort (not tested here) |
| AMD RDNA2 `gfx1030` via ROCm | tile kernels | supported | `q8_0`, best effort |
| AMD RX 6600/6700, Intel Arc (Vulkan) | Vulkan supports flash attention with `q8_0` **only if the driver offers two GPU features ("subgroup shuffle" and "subgroup vote") or cooperative matrices** (`ggml/src/ggml-vulkan/ggml-vulkan.cpp:15034-15060`) | depends on the driver | **`f16` by default.** Because `q8_0` forces flash attention on and skips the safety test, a card without those features would run that step on the processor - slow, with no message. Offer `q8_0` as "try it, and Jarvis measures". |
| NVIDIA below 6.0 (Maxwell) | Ollama forces flash attention off | **`q8_0` makes the model fail to load** | `f16` only |

MODEL-TOPOLOGY.md's advice not to set `OLLAMA_FLASH_ATTENTION` still holds.

### 2.3 Two cards: where Ollama puts a model

*Plain words:* with two cards visible to one Ollama, Ollama picks the card
with the **most free memory** that the model fits on, not the fastest one.

From `server/sched.go`:

- Cards are grouped by route (CUDA, ROCm, Vulkan) (`:983`, `ml/device.go:132-151`);
  a model never spans two routes.
- If a model has `main_gpu` set, Ollama uses that position in the list
  (`:988-1011`, `:1044-1063`; the option is `api/types.go:592`).
- Otherwise, unless `OLLAMA_SCHED_SPREAD` is set, it tries each card on its
  own and takes the one with the most free memory where the model's
  *predicted* size is at most **80%** of that card's free memory
  (`:1014-1031`, `:1065-1089`). Discrete cards beat integrated ones.
- If no single card fits, it gives the whole route group to llama.cpp,
  which spreads the layers over the cards (`:1033-1035`). With
  `OLLAMA_SCHED_SPREAD=1` it always does that (`:1014`; `envconfig/config.go:228`).
- A model placed on one card is started with only that card visible and
  `--split-mode none --main-gpu 0` (`:1038-1042`, `llm/llama_server.go:644-650`,
  `ml/device.go:335-354`).

**Why pinning by `CUDA_VISIBLE_DEVICES` alone is probably not enough.** With
the everyday Ollama pinned to the 2080 Super's id, CUDA sees one card - but
the Vulkan route still lists the 2060, and since the 2060 is now hidden from
CUDA its Vulkan entry is not a duplicate and is kept (2.1). Ollama's
predicted size for `jarvis-primary` is 6.92 GiB (2.5), more than 80% of the
2080 Super's free memory and less than 80% of the 2060's - so, by this
reading of the code, **chat would be placed on the 2060 through Vulkan**.
I have not run it. The remedy is `OLLAMA_VULKAN=0` for Ollama on an
all-NVIDIA PC (`envconfig/config.go:234`; the Vulkan folder is then skipped:
`discover/runner.go:108`). The same applies to the second Ollama: today
`lane_env` *removes* `GGML_VK_VISIBLE_DEVICES` (`backend/jarvis_second_card.py:566-569`)
rather than switching Vulkan off, so the second Ollama can see the 2080
Super through Vulkan too.

*Since then (2026-09-24): fixed.* `lane_env` now sets `OLLAMA_VULKAN=0`
for the second Ollama, and `pin_command` (the one-line command for the
everyday Ollama) sets it too, beside `CUDA_VISIBLE_DEVICES`. Both are in
`backend/jarvis_second_card.py`. Still not run on a real two-card PC.

**Two cards, one Ollama, or two Ollamas?** One Ollama *can* hold model A on
card 0 and model B on card 1 using `main_gpu`, but not reliably:

- `main_gpu` is a position in Ollama's list, not a card id (`sched.go:1044-1063`),
  and list order is whatever the drivers report.
- When a new model needs room, Ollama picks what to unload **without
  looking at which card it is on** - the code says so itself: "In the future
  we can enhance the algorithm to be smarter about picking the optimal runner
  to unload" (`sched.go:1679-1708`, comment at `:1691`). Loading the
  pictures model onto card 1 could unload everyday chat from card 0.

**Conclusion:** two cards → two Ollamas, each pinned by the card's id (what
`jarvis_second_card` does today, plus `OLLAMA_VULKAN=0`). One card of any
size → one Ollama.

### 2.4 Two models on one card

- `OLLAMA_MAX_LOADED_MODELS` unset means **3 per card** (`sched.go:87`,
  `:285-296`; `docs/faq.mdx:334`). (The FAQ's note that Windows Radeon cards
  default to 1, `docs/faq.mdx:338`, is not reflected anywhere in the current
  scheduler code.)
- Each loaded model is its **own llama.cpp process**, so each has its own
  CUDA start-up cost (MODEL-TOPOLOGY.md's 0.33 GiB, which I could not
  re-measure).
- Before loading a second model beside one already loaded, Ollama checks
  **its own prediction plus a batch surcharge against 80% of the card's free
  memory**, and unloads something first if it does not fit (`sched.go:549-575`).
  Its prediction is pessimistic (2.5), so a pair that really fits can still
  fail this check - and then Ollama unloads **the other model, which on a
  single card is usually everyday chat**. What it unloads first: models with
  the shortest keep-alive (`sched.go:1572-1593`), so a lane model with
  `keep_alive 30m` goes before chat with `-1` - but if chat is the only
  thing loaded, chat goes.
- **So every co-resident pair must pass Ollama's 80% check too**, not only
  the real arithmetic. The planner in section 4 checks both.

### 2.5 How much memory a model takes - two estimates, and which one decides

*Plain words:* there is no single "estimate" any more. Ollama makes a rough
guess to choose a card and to decide what to unload; llama.cpp then measures
properly and decides how much of the model goes on the card.

**Ollama's guess** - `PredictServerVRAM`, `llm/llama_server.go:2785-2804`:

```
model file size  +  2 (K and V) × layers × kv_heads × (embedding ÷ heads) × context × 2 bytes
```

- It counts the **file size** and an **uncompressed (`f16`) cache**, and
  nothing else: no compute buffer, no CUDA start-up, no picture reader when
  that is a separate file.
- It **ignores `OLLAMA_KV_CACHE_TYPE`**, so with `q8_0` it over-counts the
  cache by 2 ÷ 1.0625 ≈ **1.88×**. (MODEL-TOPOLOGY.md and
  `vram-estimate.patch` say it rounds `q8_0` to 1.0 byte and under-counts by
  6%. That described older code; it is now the other way round.)
- Its head size is `embedding ÷ heads`, which is wrong for models where
  that is not the real head size: Qwen 3 4B (2560 ÷ 32 = 80, real 128) and
  Spark-X2.5-4B (2560 ÷ 16 = 160, real 256).
- It counts every layer at full length, so it badly over-counts models that
  mostly use a short "sliding window" (Spark-X2.5-4B: 5.16 GiB predicted
  against 3.30 GiB calculated at 32K).
- `num_parallel` multiplies the context (`sched.go:798-800`; default 1:
  `envconfig/config.go:277`). The batch surcharge - 768 MiB at
  `num_batch` ≥ 1024, 2 GiB at ≥ 2048 (`sched.go:911-920`) - is added only
  in the 80% checks; Ollama's automatic batch reaches for 1024 above 4,096
  context unless the card is a CUDA card of 8 GiB or less with flash
  attention off (`sched.go:827-873`). **`num_batch 512` in the Modelfile is
  still worth pinning**; it also sets the real batch (`-b` and `-ub`:
  `llm/llama_server.go:593-595`).

**llama.cpp's fit** - the one that actually decides. Ollama passes the
context (`-c`, always: `llm/llama_server.go:378`) and, unless the Modelfile
sets `num_gpu`, lets llama.cpp choose how many layers go on the card
(`llm/llama_server.go:405-413`, and the file's header comment at `:13-14`).
llama.cpp's "fit" (on by default: `common/common.h:476`, `--fit`/`LLAMA_ARG_FIT`
at `common/arg.cpp:2876`) measures the real weights, cache (in its real
format) and compute buffers against the card's **free memory right now**,
and keeps a **margin of 1024 MiB free on every card**
(`common/common.h:481`; `LLAMA_ARG_FIT_TARGET` at `common/arg.cpp:2915`;
Ollama lists both variables in `envconfig/config.go:322-323`). If the model
would eat into that margin and the context was set (it always is), fit
**moves layers to the processor** until the margin is kept
(`common/fit.cpp:354`, `:386`). The result is logged as
`offloaded N/M layers to GPU` (`src/llama-model.cpp:1846`), which Ollama
also parses (`llm/llama_server.go:2845-2848`) and reflects in `/api/ps`
(`llm/llama_server.go:2745-2783`).

- If `num_gpu` is set in the Modelfile and the model does not fit, fit
  gives up (`common/fit.cpp:464`) and the load runs out of memory instead -
  a loud failure rather than a quiet slowdown. (I have not checked what the
  Windows NVIDIA driver does when CUDA runs out of memory; there is a driver
  setting that can let it borrow system memory instead. Unverified.)
- For picture models Ollama raises the margin to *(picture reader size +
  1 GiB)*, because the picture reader is loaded outside fit's accounting
  (`llm/llama_server.go:706-745`), and keeps the picture reader on the
  processor if a card has less free memory than that (`:683-704`).
- Ollama also forces at least 1,024 picture tokens per image for Qwen-VL
  models (`llm/llama_server.go:1038-1047`), so **every picture costs at
  least 1,024 tokens of context**.

**Is MODEL-TOPOLOGY.md's arithmetic consistent with this?** Its
*weights + cache + runtime* sum is the right shape and is what fit measures.
What it lacks is the **1 GiB margin**. Its "ceiling 8 GiB − 1.1 GiB = 6.90"
should now be "8 GiB − 1.1 − 0.33 (CUDA) − 1.0 (margin) = 5.57 GiB for the
model" (section 4.2).

**Default context without a Modelfile** is now set by the total memory of
all cards Ollama can see: 4,096 under 23 GiB, 32,768 from 23 GiB, 262,144
from 47 GiB (`server/routes.go:2096-2115`). An unpinned 8+16 or 12+12 PC
therefore gets 32,768 by default. `OLLAMA_CONTEXT_LENGTH` overrides it
(`envconfig/config.go:230`). `nextLowerAutoNumCtx` (`sched.go:922-931`),
which MODEL-TOPOLOGY.md quotes, is now used only when a load has already run
out of memory and the context was automatic (`sched.go:654-668`, `:762-788`).
A Modelfile context larger than the model's own maximum is cut down to that
maximum (`llm/server.go:102-107`).

### 2.6 The desktop's own share of the card (the Windows compositor)

**No figure is documented in either source.** Neither Ollama nor llama.cpp
reserves anything for Windows' desktop drawing (DWM):

- `OLLAMA_GPU_OVERHEAD` (default 0, `envconfig/config.go:305`) and Ollama's
  457 MiB "minimum memory" per card (`ml/device.go:107-115`) are, in the
  current code path, used **only** in a log line (`sched.go:620-630`) and in
  choosing the default context tier (`routes.go:2102`). **Setting
  `OLLAMA_GPU_OVERHEAD` no longer keeps any memory free.** The lever that
  does is `LLAMA_ARG_FIT_TARGET`.
- Both Ollama and llama.cpp work from the card's **free memory at load
  time**, which already has the desktop's share taken out. So nothing needs
  reserving *for what is already there*; the risk is the desktop, a browser
  or a game growing **after** the model has loaded. The 1 GiB margin is what
  absorbs that.

MODEL-TOPOLOGY.md's "~1.1 GiB DWM and the Tauri shell" and
`jarvis_second_card.py`'s "about 0.6 GiB kept by the driver" on a card with
no monitor are not sourced anywhere I could find. This design keeps them as
**placeholders** and replaces them with a measurement (4.1): free memory
with Jarvis's windows open and no model loaded.

### 2.7 Reading the cards without `nvidia-smi` (AMD, Intel)

- **`Win32_VideoController.AdapterRAM` is a 32-bit number**
  (`MicrosoftDocs/win32: desktop-src/CIMWin32Prov/win32-videocontroller.md`,
  the property list shows `uint32 AdapterRAM;`), so it cannot show more than
  4 GB. Do not use it for sizing.
- **The registry value `HardwareInformation.qwMemorySize`** under the
  display-adapter class key
  `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000`,
  `\0001`, ... holds the real size as a 64-bit number. AMD's own GAIA tool
  reads exactly this, with the comment "unlike Win32_VideoController.AdapterRAM
  which caps at 4 GB" (`amd/gaia: src/gaia/device.py:66-67`, key at `:84`,
  value at `:96-99`), and so does Firefox (`widget/windows/GfxInfo.cpp`,
  found by GitHub code search; line not pinned). It gives **total** memory
  only - not free memory, not which card drives the monitor.
- **PowerShell 5.1 can read it in one line** (checked by reading, not run -
  see section 1):

  ```powershell
  Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' -ErrorAction SilentlyContinue | Where-Object { $_.'HardwareInformation.qwMemorySize' } | ForEach-Object { '{0}  {1:N1} GB  {2}' -f $_.DriverDesc, ($_.'HardwareInformation.qwMemorySize' / 1GB), $_.MatchingDeviceId }
  ```

  It prints one line per card on the screen; nothing is written anywhere.
  (Some older drivers may store the size in a different form; unverified.)
- **Which card drives the monitor:** `nvidia-smi` reports `display_active`
  for NVIDIA cards (Jarvis already reads it: `backend/rebuilt/jarvis_compute.py:138`).
  For other cards I found no documented, reliable one-liner.
  `Win32_VideoController`'s `CurrentHorizontalResolution` is filled in for
  an adapter that is showing a picture, which is a reasonable hint but
  **unverified**. The measured route is better: the card whose free memory
  is lower with nothing loaded is the one drawing the desktop.

### 2.8 The models: shapes and sizes

Architecture numbers come from each model's `config.json`, read from
**copies in public GitHub repositories** (huggingface.co is blocked here).
Qwen 3's layer and head counts are also confirmed by Qwen's own technical
report (Table 1, page 3: 4B 36 layers 32/8 heads, 8B 36 layers 32/8,
14B 40 layers 40/8; context "128K", which the Qwen docs explain is with
YaRN; "the maximum context length in pre-training for Qwen3 models is
32,768 tokens", `QwenLM/Qwen3: docs/source/inference/transformers.md:170`).

| Model (Ollama name assumed) | Source of `config.json` | Layers | KV heads × head size | Max context (config) | Picture reader |
|---|---|---|---|---|---|
| `qwen3:4b` | `bojieli/ai-infra-book@15c8c08: calculations/configs/models/flux2-klein-4b/text_encoder/config.json:10,12,53,56-58` - FLUX.2-klein's text encoder, which has Qwen 3 4B's shape (a stand-in, labelled) | 36 | 8 × 128 | 40,960 | - |
| `qwen3:8b` | `bojieli/ai-infra-book@15c8c08: calculations/configs/models/qwen3-8b/config.json:9,11,14,17-19` | 36 | 8 × 128 | 40,960 | - |
| `qwen3:14b` | `bojieli/ai-infra-book@15c8c08: references/framework-history/2026-09-09/rlboost-recovery/qwen3-14b-config.json:9,11,14,17-19` | 40 | 8 × 128 | 40,960 | - |
| `qwen2.5vl:3b` | `tenstorrent/tt-metal@c87cf14: models/tt_transformers/model_params/Qwen2.5-VL-3B-Instruct/config.json:14,20-22,32-35` | 36 | 2 × 128 | 128,000 | 32 blocks, width 1280 |
| `qwen2.5vl:7b` | `bojieli/ai-infra-book@15c8c08: calculations/configs/models/qwen-image-2512/text_encoder/config.json:10,17-19,104,113,117` - Qwen-Image's text encoder, a Qwen2.5-VL-7B-shaped model (a stand-in, labelled) | 28 | 4 × 128 | 128,000 | 32 blocks, width 1280 |
| `llama3.2:3b` | `tenstorrent/tt-metal@c87cf14: .../Llama-3.2-3B-Instruct/config.json:13,15,18,21-23,34` | 28 | 8 × 128 | 131,072 | - |
| Spark-X2.5-4B | `click6067-ship-it/fitllm-engine@4a60290: test/fixtures/day0/spark-x2.5-4b.config.json:16,19,21,60,63-65,78,79,82` | 36, of which **9 full + 27 sliding-window (512)** - counted from its `layer_types` | 4 × **256** | 1,048,576 | - |

The Qwen 3 `40,960` is what Ollama will cap the context at
(`llm/server.go:102-107`), assuming Ollama's GGUF carries the same value
(unverified - ollama.com is blocked).

**Spark-X2.5-4B** is supported by the llama.cpp Ollama builds (`spark2_5`
at `src/llama-arch.cpp:151` in b11081; conversion in master
`conversion/spark2_5.py:12-47`). It uses a gated GELU feed-forward
(master `src/models/spark2-5.cpp:45-48`, `:122-127`), which is how I counted
its parameters. llama.cpp keeps the sliding-window layers' cache at
`window + batch`, padded to 256 cells, not the full context
(`src/llama-kv-cache-iswa.cpp:73`), and Ollama does not ask for the full-size
version (no `--swa-full` anywhere in its Go code; llama.cpp's default is off,
`common/common.h:572`). **I could not verify** the "Ollama ≥ 0.34.1" claim
(Ollama's source says version `0.0.0`; release tags are not in a shallow
clone), whether Ollama has a tag for it, or how well it calls tools.

**Tool calling.** Ollama has its own tool-call parser for Qwen 3
(`model/parsers/qwen3.go:30-31`, `:47`; registered at
`model/parsers/parsers.go:56`) and for Qwen3-VL (`parsers.go:66-68`). Models
without one go through llama.cpp's own chat-template handling
(`llm/llama_server.go:3-6`). Which parser a given ollama.com model uses is
set in its published manifest, which I could not read. ~~So: Qwen 3 is the
best-supported tool-calling family in this Ollama by source; nothing else
on the list is verified.~~ **Out of date (checked 2026-09-24 at Ollama
`5f4b01e`, by reading, not running):** Ollama now also has its own readers
for `qwen3.5`, `gemma4` and `ministral` (`model/parsers/parsers.go`). The
Qwen 3.5 one hands the call to the Qwen3-Coder reader, which converts each
argument to the type the tool's schema asks for
(`model/parsers/qwen3coder.go`, `parseToolCall` / `parseValue`) - more
forgiving than Qwen 3's, which checks nothing against the schema. How well
each model *picks* tools is still unmeasured. Qwen3-VL (4B/8B) would be the natural pictures
model *with* tools if its ollama.com manifest uses the `qwen3-vl` parser -
worth checking on the PC before choosing it over Qwen2.5-VL.

**Sizes** - parameters counted from the shapes above, then
*parameters × 4.90 bits ÷ 8* for Q4_K_M (MODEL-TOPOLOGY.md's figure), plus
the picture reader at 2 bytes per parameter (assumed `f16`). **All
computed; none read from ollama.com.**

| Model | Parameters (computed) | Download (computed) | Weights on card | Picture reader | Cache per token, `q8_0` | Cache per token, `f16` |
|---|---|---|---|---|---|---|
| qwen3:4b | 4.02 B | 2.46 GB | 2.29 GiB | - | 78,336 B | 147,456 B |
| qwen3:8b | 8.19 B | 5.02 GB | 4.67 GiB | - | 78,336 B | 147,456 B |
| qwen3:14b | 14.77 B | 9.05 GB | 8.42 GiB | - | 87,040 B | 163,840 B |
| qwen2.5vl:3b | 3.09 B + 0.67 B | 3.22 GB | 1.76 GiB | 1.24 GiB | 19,584 B | 36,864 B |
| qwen2.5vl:7b | 7.62 B + 0.68 B | 6.01 GB | 4.34 GiB | 1.26 GiB | 30,464 B | 57,344 B |
| llama3.2:3b | 3.21 B | 1.97 GB | 1.83 GiB | - | 60,928 B | 114,688 B |
| Spark-X2.5-4B | 4.11 B | 2.52 GB | 2.34 GiB | - | 19,584 B + 57 MiB fixed | 36,864 B + 108 MiB fixed |

Cache per token = 2 (K and V) × layers × KV heads × head size × bytes
(1.0625 for `q8_0`, 2 for `f16`). For Spark only the 9 full layers grow; the
fixed part is 27 × 2 × 4 × 256 × 1,024 cells × 1.0625 B.

Two things the table shows that the brief did not expect:

- **Qwen 3 4B's cache is exactly as big per token as Qwen 3 8B's** (same 36
  layers, 8 KV heads, 128). The 4B saves weights, not context.
- **Llama 3.2 3B is a poor long-context choice**: 60,928 B per token is 78%
  of Qwen 3 8B's, for a much weaker model, with no tool parser in Ollama.
  The long-context lane below uses Qwen 3 (up to 40,960), and Spark-X2.5-4B
  is the one to evaluate for more (it is about a quarter of Qwen 3's cost
  per token).

---

## 3. What this means for today's setup

Each item: what is written today, what the source says now, and what to do.

| # | Written today | What the source says now | Consequence |
|---|---|---|---|
| 1 | `jarvis-primary` at 16,384 is 6.48 GiB against a 6.90 GiB ceiling (MODEL-TOPOLOGY.md, "The budget"). | llama.cpp keeps 1 GiB free (2.5). 4.67 + 1.20 + 0.30 = 6.17 GiB of model needs 6.17 + 1.10 + 0.33 + 1.00 = **8.60 GiB of an 8.0 GiB card**. | **Calculated: about 0.6 GiB over, so fit would put ~4 of 37 layers on the processor** (a layer is ~0.16 GiB: 4.67 ÷ 36 weights + 1.20 ÷ 36 cache). Check with 4.7. If confirmed: 8,192 lands exactly on the limit (5.57 of 5.57); 6,144 fits; or lower the margin (decision 1). |
| 2 | "Run the one command" pins the everyday Ollama with `CUDA_VISIBLE_DEVICES` (SECOND-CARD.md). | Vulkan still sees the other card (2.3). | Add `OLLAMA_VULKAN=0` to that line, and make the second Ollama set it too instead of removing `GGML_VK_VISIBLE_DEVICES` (`jarvis_second_card.py:566-569`). |
| 3 | "Reads off → `q8_0` KV is being silently ignored ... spills" (MODEL-TOPOLOGY.md:124-127). Verify with `OLLAMA_DEBUG=1` (`:118`). | Off + `q8_0` = the model **fails to load** (2.2). The `starting llama-server` line with the full command is logged at normal level (`llm/llama_server.go:436`), so `OLLAMA_DEBUG` is not needed. | Replace the verify step with 4.7's. `[second_card] flash_attention = "off"` (`jarvis_second_card.py:583-584`) should be refused while the lane uses `q8_0`. |
| 4 | Ollama's estimator "rounds `q8_0` to 1.0, under-counts by ~6%" (MODEL-TOPOLOGY.md:148-151; `vram-estimate.patch`). | It now assumes `f16` and over-counts by ~1.88× (2.5). | Harmless for a single model; it matters for co-resident models and two-card placement (2.3, 2.4). The Jarvis estimator should model *both*: llama.cpp's fit (real) and Ollama's guess (the gate). |
| 5 | 12 GB second card: `qwen3:14b` at 16,384, "10.38 GiB, fits, 1 GiB spare" (`jarvis_second_card.py:157`). | With the 1 GiB margin: 10.10 + 0.60 (no monitor) + 0.33 + 1.00 = 12.03 of 12.0. | 0.03 GiB over by calculation - use 12,288 (9.77 GiB) until measured. The 11 GB → 8B at 32,768 conclusion still holds (7.36 GiB, 1.7 GiB to spare). |
| 6 | "Plug the monitors into the 2080 Super" (MODEL-TOPOLOGY.md, install step 2), and the main card is "the one your monitor is plugged into" (`jarvis_compute.py:258-285`). | With the 1 GiB margin, the monitor's share on the 8 GB card is what squeezes chat to 6,144 (section 4.4, case 8 + 12). With the monitor on the 2060 instead, chat on the 2080 Super gets 12,288, and the 2060's lane drops from 14B to 8B. | Worth measuring both ways. Either way, **"main card = the card with the monitor" must go**: the main card should be the fastest one (4.1), or moving a cable silently moves chat to the slower card. |
| 7 | The second-card features need a *second* card of ≥ 10 GB (`jarvis_second_card.py:133-139`, `:400-422`, `:478`). | One 16 or 24 GB card can hold chat plus pictures in one Ollama (2.4). | Generalise to "spare capacity" (4.3). |
| 8 | "Turing is the floor" for the second card (`jarvis_second_card.py`, docstring). | Pascal runs `q8_0` through slower kernels; it does not fail (2.2). | Keep Turing as the floor for *recommended* lanes; allow Pascal as "best effort" rather than "not capable". |

*Since then (2026-09-24):* row 2 is fixed - `pin_command` and `lane_env`
both set `OLLAMA_VULKAN=0` now. Row 3's refusal is built: `[second_card]
flash_attention = "off"` stops the second Ollama from starting, with a
sentence saying why (`_flash_refusal`). Row 5 is superseded: a 12 GB second
card now gets `qwen3:8b` with 32,768 tokens (7.69 GiB), not `qwen3:14b`, so
that the lane has more room than the everyday model (`LONG_BIG` in
`jarvis_second_card.py`). The table above is kept as it was written.

---

## 4. The design

### 4.1 Detection

**Plain words:** Jarvis asks, in this order, the sources that know most
about your cards, and says which one it used.

| Order | Source | Gives | When |
|---|---|---|---|
| 1 | Ollama's own log: the `inference compute` lines in `%LOCALAPPDATA%\Ollama\server.log` (2.1) | exactly the cards **Ollama will use**, their route (CUDA/ROCm/Vulkan), generation (`compute`), driver, PCI id, total and **free** memory at Ollama's start-up, and the `user overrode visible devices` line | always first; it is the ground truth for "what can Ollama use". Read the most recent start-up block only. |
| 2 | `nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.free,compute_cap,display_active --format=csv,noheader,nounits` (already in `jarvis_compute.py:138`) | the `GPU-...` id (needed to pin), which card has the monitor, **live** free memory | NVIDIA cards |
| 3 | Registry `HardwareInformation.qwMemorySize` (2.7) | name and total memory of every card, any vendor | AMD/Intel, or to cross-check |
| 4 | `Win32_VideoController` | names only (its memory field stops at 4 GB) | last resort; never for sizing |

Ollama's log sees each card only as Ollama sees it (a card Ollama dropped
is missing), so Jarvis joins sources 1-3 by PCI id or name + memory and
shows **every** card, with the reason a card is not used - taken from
Ollama's own log lines where they exist (`dropping ROCm device ...`,
`skipping CUDA device ...`, `NVIDIA driver too old`, `dropping integrated
GPU`).

**Which card is fastest.** Words per second depend mostly on memory speed.
Jarvis keeps a small built-in table of published memory speeds for common
cards (labelled "published spec", e.g. 2080 Ti ~616, 2080 Super ~496,
2060 12 GB ~336 GB/s - MODEL-TOPOLOGY.md's figures) and, when both cards are
known, uses it; otherwise, and always once both cards are in, **measures**:
the same short prompt on each card, recorded by the speed recorder (4.7).
`[compute] primary_gpu` in the toml still overrides everything. "The card
with the monitor" stops being a rule.

**The desktop's share (display reserve).** Measured, not assumed: free
memory on each card with Jarvis's windows open and **no model loaded**
(Ollama idle, or source 2), taken as `total − free`. Until measured, the
placeholders are 1.10 GiB for the monitor card and 0.60 GiB for a card with
no monitor (today's figures, unsourced).

**What "capable" means, per role:**

| Role | Needs |
|---|---|
| Everyday chat | a card Ollama uses (source 1), with room for `qwen3:4b` at ≥ 8,192 (3.14 GiB, see 8.2). Below that: processor only, said plainly. |
| Compact cache (`q8_0`) | NVIDIA ≥ 6.0 except 7.2: yes. ROCm: yes, best effort. Vulkan: "try it" (2.2). NVIDIA < 6.0: no. |
| Long-context lane | room for a model with **more** context than chat already has; otherwise the lane adds nothing and is not offered |
| Pictures lane | room for `qwen2.5vl:3b` at 8,192 (3.65 GiB), either beside chat or by swapping |
| Background learning, wiki | use the long-context lane's model when it runs; otherwise the chat model while chat is idle (as today) |
| Browser control | the long-context lane (unchanged) |
| colibri's CUDA tier | a card with **no** lane on it, Turing or newer, and a source-built colibri (BIG-MODEL.md; unchanged, off by default) |

### 4.2 The per-card budget

```
room for models (GiB) = total
                      − desktop share        (measured; else 1.10 with monitor, 0.60 without)
                      − 0.33 × processes     (one per loaded model; CUDA start-up, MODEL-TOPOLOGY)
                      − fit margin           (1.00, llama.cpp default; LLAMA_ARG_FIT_TARGET)
                      − 0.10 cushion         (this design's rounding allowance)

model need (GiB)      = weights + picture reader
                      + context × cache bytes per token (by KV type; + Spark's fixed part)
                      + compute buffer       (0.25 for 3-4B, 0.30 for 7-8B, 0.35 for 14B; placeholders)
                      + 0.25 per picture model (encoding one picture; placeholder)
```

And, for a second model on the same card in the same Ollama, **Ollama's
gate** (2.4) must also pass:

```
file size + f16 cache (Ollama's formula, 2.5)  ≤  0.8 × (total − desktop share − 0.33 − first model's need)
```

KV type by route: CUDA ≥ 6.0 → `q8_0`; ROCm → `q8_0`; Vulkan → `f16`
(offer `q8_0` as a measured experiment); CUDA < 6.0 → `f16`.

Worked, for the owner's 2080 Super today: 8.00 − 1.10 − 0.33 − 1.00 =
**5.57 GiB** of room, 5.47 after the cushion. Per-card rooms for every case
are in 8.1.

### 4.3 Roles and placement: "spare capacity", not "second card"

**Plain words:** chat goes first, on the fastest card, sized by the preset.
Whatever room is left - on that card or on another - is *spare capacity*,
and the other features go there, biggest useful first.

**Placement, in order:**

1. **Chat** on the fastest card (4.1). Model and context by preset (4.4).
   The chat card's Ollama is the everyday one on port 11434.
2. **With two cards**, the other card runs a second Ollama (port 11435,
   pinned by id, `OLLAMA_VULKAN=0`, `OLLAMA_MAX_LOADED_MODELS=1`) - as today.
   Its lanes take turns there, one model at a time, as today. It gets a
   long-context model only if that gives **more** context than chat has.
3. **With one card**, lanes go **inside the everyday Ollama**, beside chat,
   only if both the real budget and Ollama's gate pass (4.2). Otherwise
   pictures are offered **by swapping**: a picture question unloads chat,
   answers, and chat reloads on the next message (seconds each way;
   unmeasured - MODEL-TOPOLOGY.md's 6-10 s figure is for an 8B). The owner
   sees that before choosing it.
4. **Background learning and the wiki** follow the long-context lane, else
   the chat model (today's behaviour).
5. **colibri's CUDA tier** only on a card with no lane (unchanged).
6. **Never split one model across two cards by default** (unchanged; it
   runs at the slower card's pace).

**How many Ollamas:**

| Hardware | Everyday Ollama | Second Ollama |
|---|---|---|
| One card, any size | one, sees that card | none. Lanes are extra models in the same Ollama. |
| Two cards | one, pinned to the chat card | one, pinned to the other card, started and stopped by Jarvis (as today) |

**Changes to `jarvis_second_card.py`** (keep the file, the feature ids, the
five switches, the main switch, the approval card `second_card_enable` at
tier `ask`, "off never asks", `lane_for()` returning `None` meaning "as
before", `GET/POST /api/second-card` and both apps' contract - generalise
only *where* a lane runs):

- `Lane.url` may now be the **everyday** Ollama (single-card case) as well
  as the second one. Callers already treat a `Lane` as opaque.
- Detection: take cards and placement from the new planner (4.4) instead of
  "a second card of ≥ 10 GB, Turing or newer" (`:133-139`, `:400-482`).
  A single card with spare capacity becomes "capable" for the lanes that fit.
- Models and context: from the planner, not the fixed `LONG_BIG` /
  `LONG_SMALL` (`:157-158`).
- In the single-card case, lanes need their own Modelfile-made models
  (`jarvis-long`, `jarvis-vision`) that carry `num_ctx`, because the
  everyday Ollama's `OLLAMA_CONTEXT_LENGTH` cannot differ per model and the
  `/v1` chat endpoint cannot set it (MODEL-TOPOLOGY.md). `generate()`'s
  `options.num_ctx` must then equal the Modelfile's, or Ollama reloads the
  model.
- `lane_env`: set `OLLAMA_VULKAN=0` for NVIDIA lanes instead of only removing
  `GGML_VK_VISIBLE_DEVICES` (`:566-569`); refuse `flash_attention = "off"`
  while `OLLAMA_KV_CACHE_TYPE=q8_0` (`:583-584`).
- `pin_command` / `main_pin`: add `OLLAMA_VULKAN=0` on all-NVIDIA PCs, and
  check the `user overrode visible devices` line in Ollama's log as well as
  the user setting.
  *Since then (2026-09-24):* the `OLLAMA_VULKAN=0` parts and the
  `flash_attention = "off"` refusal are done. `main_pin` does not read
  Ollama's log yet: it still checks `CUDA_VISIBLE_DEVICES` and `nvidia-smi`
  only. It does not check `OLLAMA_VULKAN` either, so someone who ran the
  older one-setting command is still told the everyday Ollama is pinned.
- The status text says "spare capacity on the <card>" rather than "the
  second card" when the lane is on the chat card.

### 4.4 The recommendation table

How to read it:

- **Chat / Long context / Pictures:** model, context (K = 1,024 tokens),
  KV type, and the card. The number after the model is its *need* in GiB
  from section 8.2, where the sum is written out.
- **Memory:** per card, `models + fixed = total of card`, where *fixed* =
  desktop share + 0.33 per process + 1.00 margin. Bars are 16 blocks.
- **Pairs:** the table assumes the **first** card listed is the faster one.
  If the other is faster, swap them (the planner does). Where two lanes
  share a card they take turns, so the bar shows the bigger of the two.
- Everything is **calculated, not measured**.

#### One card

**8 GB** (room 5.57 GiB) - *the owner's PC today*

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K, q8_0 - 4.94 | chat itself (32K) | off | `███████████████░` 4.94 + 2.43 = 7.37 / 8 | Pictures off: they would share the card with chat. |
| Smartest answers | qwen3:8b, **6K**, q8_0 - 5.42 | - | off | `████████████████` 5.42 + 2.43 = 7.85 / 8 | Only 6K of conversation: the 8B's weights (4.67) plus the 1 GB gap leave little room. See decision 1 (0.5 GB gap gives 12K). |
| Most features | qwen3:4b, 32K, q8_0 - 4.94 | chat itself (32K) | qwen2.5vl:3b by **swapping** (needs 3.65 alone) | `███████████████░` 4.94 + 2.43 = 7.37 / 8 | Pictures unload chat while they run. 8B chat does not leave room for anything. |

**10 GB** (room 7.57; an 11 GB card has 8.57 and gets the same rows)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | off | `████████████░░░░` 4.94 + 2.43 = 7.37 / 10 | Pictures off (share the card). |
| Smartest answers | qwen3:8b, 32K - 7.36 | chat (32K) | off | `████████████████` 7.36 + 2.43 = 9.79 / 10 | 14B does not fit (9.44 at 8K > 7.47). |
| Most features | qwen3:8b, 32K - 7.36 | chat (32K) | qwen2.5vl:3b by swapping | `████████████████` 9.79 / 10 | Pictures and 8B chat do not fit together, even at 8K (5.57 + 3.65 = 9.22 > 7.24, the room for two models). |

(11 GB: same models, bars 7.37 / 11 and 9.79 / 11.)

**12 GB** (room 9.57)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | off | `██████████░░░░░░` 7.37 / 12 | Pictures off (share the card). |
| Smartest answers | qwen3:14b, 8K - 9.44 | - | off | `████████████████` 9.44 + 2.43 = 11.87 / 12 | 14B gets only 8K. |
| Most features | qwen3:8b, 32K - 7.36 | chat (32K) | qwen2.5vl:3b by swapping | `█████████████░░░` 9.79 / 12 | Even 8B at 8K + pictures is 0.08 over (5.57 + 3.65 + 0.10 > 9.24). |

**16 GB** (room 13.57; 13.24 with two processes)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | off | `███████░░░░░░░░░` 7.37 / 16 | Pictures off by choice (fastest = nothing else loaded). |
| Smartest answers | qwen3:14b, 32K - 11.43 | chat (32K) | off | `██████████████░░` 11.43 + 2.43 = 13.86 / 16 | Pictures do not fit beside the 14B. |
| Most features | qwen3:8b, 32K - 7.36 | chat (32K) | qwen2.5vl:3b, 8K, **beside chat** - 3.65 | `██████████████░░` 11.01 + 2.76 = 13.77 / 16 | No separate long lane: chat has 32K already. (Alternative: 8B at 16K + qwen2.5vl:7b = 12.55; both pass Ollama's gate.) Ollama's gate: 3.28 ≤ 0.8 × 7.21. |

**24 GB** (room 21.57)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | off | `█████░░░░░░░░░░░` 7.37 / 24 | By choice. |
| Smartest answers | qwen3:14b, 32K - 11.43 | chat (32K) | off (would fit: see Most features) | `█████████░░░░░░░` 13.86 / 24 | Kept to chat only so nothing competes. |
| Most features | qwen3:8b, 32K - 7.36 | chat (32K) | qwen2.5vl:7b, 8K, beside chat - 6.38 | `███████████░░░░░` 13.75 + 2.76 = 16.51 / 24 | A 14B wiki lane beside both **fails Ollama's gate** (10.92 predicted > 0.8 × 8.50), so Ollama would unload chat to load it. ~6 GiB left idle until measured. Ollama's gate for pictures: 6.04 ≤ 0.8 × 15.21. |

#### Two cards

**8 + 8 GB, monitor on one of them** (chat on the one **without** the
monitor: room 6.07; the other: 5.57)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (no-monitor card) | chat (32K) | qwen2.5vl:3b, 8K - 3.65 (monitor card) | A `██████████████░░` 4.94 + 1.93 = 6.87 / 8 · B `████████████░░░░` 3.65 + 2.43 = 6.08 / 8 | Long lane off: the other card cannot beat chat's 32K. |
| Smartest answers | qwen3:8b, 12K - 5.87 | qwen3:4b, 32K - 4.94 | qwen2.5vl:3b, 8K - 3.65 | A `████████████████` 5.87 + 1.93 = 7.80 / 8 · B `███████████████░` 4.94 + 2.43 = 7.37 / 8 | Long context and pictures take turns on B. |
| Most features | same as Smartest | | | | Same: 8B is both the smartest and the balanced chat here. |

**8 + 10 GB, monitor on the 8** (A room 5.57, B 8.07)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (8 GB) | chat (32K) | qwen2.5vl:7b, 8K - 6.38 (10 GB) | A 7.37 / 8 `███████████████░` · B 6.38 + 1.93 = 8.31 / 10 `█████████████░░░` | Long lane off (cannot beat 32K). |
| Smartest answers | qwen3:8b, 32K - 7.36 (**10 GB, slower card**) | chat (32K) | qwen2.5vl:3b, 8K - 3.65 (8 GB) | A 3.65 + 2.43 = 6.08 / 8 · B 7.36 + 1.93 = 9.29 / 10 | Chat moves to the slower card to get 32K instead of 6K. |
| Most features | qwen3:8b, 6K - 5.42 (8 GB) | qwen3:8b, 32K - 7.36 (10 GB) | qwen2.5vl:7b, 8K - 6.38 (10 GB) | A 7.85 / 8 `████████████████` · B 9.29 / 10 `███████████████░` | Long context and pictures take turns on B. Chat only 6K: see decision 1, or put the monitor on the 10 GB (next table). |

**8 + 10 GB, monitor on the 10** (A 6.07, B 7.57)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | qwen2.5vl:7b, 8K - 6.38 | A 4.94 + 1.93 = 6.87 / 8 · B 6.38 + 2.43 = 8.81 / 10 | Long lane off. |
| Smartest answers | qwen3:8b, 12K - 5.87 | qwen3:8b, 32K - 7.36 | qwen2.5vl:7b, 8K - 6.38 | A 7.80 / 8 `████████████████` · B 9.79 / 10 `████████████████` | Lanes take turns on B. |
| Most features | same as Smartest | | | | |

**8 + 11 GB** - the same rows as 8 + 10 (the 11 GB card has 1 GiB more;
none of the chosen models needs it). **If the 11 GB card is an RTX 2080 Ti,
it is the faster card** (616 vs 496 GB/s published), so chat moves to it:
with the monitor on the 8 GB, *Fastest* = qwen3:4b 32K on the 11 GB + pictures
qwen2.5vl:3b on the 8 GB; *Smartest* and *Most features* = qwen3:8b 32K on
the 11 GB (7.36 + 1.93 = 9.29 / 11) + qwen2.5vl:3b on the 8 GB
(3.65 + 2.43 = 6.08 / 8); no long lane (chat already has 32K).

**8 + 12 GB, monitor on the 8** - *the planned 2080 Super + 2060 12 GB* (A 5.57, B 10.07)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (2080 Super) | chat (32K) | qwen2.5vl:7b, 8K - 6.38 (2060) | A 7.37 / 8 · B 6.38 + 1.93 = 8.31 / 12 | Long lane off (cannot beat 32K). |
| Smartest answers | qwen3:14b, 12K - 9.77 (**2060, slower**) | qwen3:4b, 32K - 4.94 (2080 Super) | qwen2.5vl:3b, 8K - 3.65 (2080 Super) | A 4.94 + 2.43 = 7.37 / 8 · B 9.77 + 1.93 = 11.70 / 12 | Chat on the slower card: biggest model, noticeably slower words (~2/3 the memory speed, plus twice the bytes per word). |
| Most features | qwen3:8b, 6K - 5.42 (2080 Super) | qwen3:14b, 12K - 9.77 (2060) | qwen2.5vl:7b, 8K - 6.38 (2060) | A `████████████████` 7.85 / 8 · B `████████████████` 11.70 / 12 | Lanes take turns on the 2060. Chat only 6K (decision 1 gives 12K). |

*Since then (2026-09-24):* the code does not follow this row. Presets are
not built, so the everyday model is still `jarvis-primary` with 16,384
tokens, and a 14B lane with 12K would have **less** room than that. The
code now moves a long conversation to the second card only when the lane
has more room than the everyday model (`jarvis_agent.py`, the
`long_context` choice), and plans `qwen3:8b` with 32K for a 12 GB card
(`LONG_BIG` in `jarvis_second_card.py`) - the "monitor on the 12" row
below. This row only makes sense together with its own 6K chat.

**8 + 12 GB, monitor on the 12** (A 6.07, B 9.57)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | qwen2.5vl:7b, 8K - 6.38 | A 6.87 / 8 · B 6.38 + 2.43 = 8.81 / 12 | Long lane off. |
| Smartest answers | qwen3:14b, 8K - 9.44 (slower card) | qwen3:4b, 32K - 4.94 (8 GB) | qwen2.5vl:3b, 8K - 3.65 (8 GB) | A 4.94 + 1.93 = 6.87 / 8 · B 9.44 + 2.43 = 11.87 / 12 | As above; 14B only 8K here. |
| Most features | qwen3:8b, **12K** - 5.87 | qwen3:8b, 32K - 7.36 | qwen2.5vl:7b, 8K - 6.38 | A 7.80 / 8 · B 7.36 + 2.43 = 9.79 / 12 | Lanes take turns. Twice the chat context of the monitor-on-the-8 layout, at the cost of 14B → 8B in the long lane. |

**8 + 16 GB, monitor on the 8** (A 5.57, B 14.07)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | qwen2.5vl:7b, 8K - 6.38 | A 7.37 / 8 · B 8.31 / 16 `████████░░░░░░░░` | Long lane off. |
| Smartest answers | qwen3:14b, 32K - 11.43 (16 GB) | chat (32K) | qwen2.5vl:3b, 8K - 3.65 (8 GB) | A 6.08 / 8 · B 11.43 + 1.93 = 13.36 / 16 | If the 16 GB card is also the faster one (likely for a newer card), this is simply the best layout. |
| Most features | qwen3:8b, 6K - 5.42 (8 GB) | qwen3:14b, 16K - 10.10 (16 GB) | qwen2.5vl:7b, 8K - 6.38 (16 GB) | A 7.85 / 8 · B 10.10 + 1.93 = 12.03 / 16 | Lanes take turns (together 16.48 > 14.07). |

**8 + 16 GB, monitor on the 16** (A 6.07, B 13.57)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | qwen2.5vl:7b, 8K - 6.38 | A 6.87 / 8 · B 8.81 / 16 | Long lane off. |
| Smartest answers | qwen3:14b, 32K - 11.43 (16 GB) | chat (32K) | qwen2.5vl:3b, 8K - 3.65 (8 GB) | A 3.65 + 1.93 = 5.58 / 8 · B 11.43 + 2.43 = 13.86 / 16 | As above. |
| Most features | qwen3:8b, 12K - 5.87 | qwen3:14b, 16K - 10.10 | qwen2.5vl:7b, 8K - 6.38 | A 7.80 / 8 · B 10.10 + 2.43 = 12.53 / 16 | Lanes take turns. |

**12 + 12 GB, monitor on one of them** (chat on the one without: 10.07; other 9.57)

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 | chat (32K) | qwen2.5vl:7b, 8K - 6.38 | A 6.87 / 12 · B 8.81 / 12 | Long lane off. |
| Smartest answers | qwen3:14b, 12K - 9.77 | qwen3:8b, 32K - 7.36 | qwen2.5vl:7b, 8K - 6.38 | A 9.77 + 1.93 = 11.70 / 12 · B 7.36 + 2.43 = 9.79 / 12 | Lanes take turns on B. |
| Most features | qwen3:8b, 32K - 7.36 | chat (32K) | qwen2.5vl:7b, 8K - 6.38 | A 7.36 + 1.93 = 9.29 / 12 · B 8.81 / 12 | Long lane off (cannot beat 32K); B holds pictures, learning and wiki use chat's model. |

#### Other single 8 GB cards and below

**GTX 1070 / 1080, 8 GB (Pascal)** - same arithmetic as "8 GB" above, same
three rows (4B 32K / 8B 6K / 4B 32K + swapped pictures), all **best
effort**: flash attention runs on the slower kernels (2.2), Ollama must use
its CUDA 12 build (just-in-time compiled for this card, driver ≥ 570 -
2.1). Expect noticeably fewer words per second than a 2080 Super; nothing
here says how many.

**RX 7600, 8 GB (ROCm)** - same three rows as "8 GB", **best effort**
(ROCm path compiled for `gfx1102`; the 0.33 GiB start-up cost is a CUDA
figure and unmeasured for ROCm).

**RX 6600, 8 GB (Vulkan)** and **Intel Arc, 8 GB (Vulkan)** - `f16` cache by
default (2.2), so context costs twice as much:

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 16K, **f16** - 4.79 | chat (16K) | off | `██████████████░░` 4.79 + 2.43 = 7.22 / 8 | 32K at f16 would need 7.04. |
| Smartest answers | qwen3:4b, 16K, f16 - 4.79 | chat (16K) | off | same | 8B does not get 8K at f16 (6.10 > 5.47). |
| Most features | qwen3:4b, 16K, f16 - 4.79 | chat (16K) | qwen2.5vl:3b by swapping | same | After a measured `q8_0` test passes, these become the "8 GB" rows. |

**6 GB** (room 3.57) - what degrades, honestly:

| Preset | Chat | Long context | Pictures | Memory | Off, and why |
|---|---|---|---|---|---|
| Fastest answers | qwen3:4b, 12K - 3.44 | chat (12K) | **off** | `████████████████` 3.44 + 2.43 = 5.87 / 6 | 8B cannot load at all (weights 4.67 > 3.57). |
| Smartest answers | same | | | | There is nothing bigger that fits. |
| Most features | same | | **off** | | Even the small picture model does not fit alone (3.58 at 4K > 3.47). |

So on 6 GB: one small model, 12K of conversation, no pictures, no lanes;
learning and wiki share the chat model. Honest and usable, but the
smallest of everything.

#### The presets as built, at the owner's 0.75 GB gap

*Added 2026-09-25, when the presets were built.* The tables above were
worked out by hand at llama.cpp's default 1 GB gap, before the owner chose
0.75 GB (decision 1). `backend/jarvis_profiles.py` reproduces every row
above at 1 GB (`backend/test_profiles.py` checks each one), and the table
below is its output at 0.75 GB, the gap the presets use. It is written by
`tools/gen_hardware_cases.py` from `backend/fixtures/hardware_cases.json`,
so it cannot drift from the code. The reasons ("off, and why") are in the
fixture and on the Hardware screen, not repeated here.

<!-- hardware-cases:begin (tools/gen_hardware_cases.py writes this; do not edit) -->

Generated from `backend/fixtures/hardware_cases.json` - the planner's own output at the owner's 0.75 GB gap. Calculated, not measured. "(rec.)" marks the recommended preset.

**10 GB** (`one_10gb`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (10 GB card) | chat itself | off | `███████████░░░░░` 4.94 + 2.18 = 7.12 / 10 |
| Smartest answers | qwen3:8b, 32K - 7.36 (10 GB card) | chat itself | off | `███████████████░` 7.36 + 2.18 = 9.54 / 10 |
| Most features (rec.) | qwen3:8b, 32K - 7.36 (10 GB card) | chat itself | qwen2.5vl:3b, 8K - 3.66 (10 GB card, by swapping with chat) | `███████████████░` 7.36 + 2.18 = 9.54 / 10 |

**11 GB** (`one_11gb`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (11 GB card) | chat itself | off | `██████████░░░░░░` 4.94 + 2.18 = 7.12 / 11 |
| Smartest answers | qwen3:8b, 32K - 7.36 (11 GB card) | chat itself | off | `██████████████░░` 7.36 + 2.18 = 9.54 / 11 |
| Most features (rec.) | qwen3:8b, 32K - 7.36 (11 GB card) | chat itself | qwen2.5vl:3b, 8K - 3.66 (11 GB card, by swapping with chat) | `██████████████░░` 7.36 + 2.18 = 9.54 / 11 |

**12 GB** (`one_12gb`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (12 GB card) | chat itself | off | `█████████░░░░░░░` 4.94 + 2.18 = 7.12 / 12 |
| Smartest answers | qwen3:14b, 8K - 9.44 (12 GB card) | off | off | `███████████████░` 9.44 + 2.18 = 11.62 / 12 |
| Most features (rec.) | qwen3:8b, 32K - 7.36 (12 GB card) | chat itself | qwen2.5vl:3b, 8K - 3.66 (12 GB card, by swapping with chat) | `█████████████░░░` 7.36 + 2.18 = 9.54 / 12 |

**16 GB** (`one_16gb`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (16 GB card) | chat itself | off | `███████░░░░░░░░░` 4.94 + 2.18 = 7.12 / 16 |
| Smartest answers | qwen3:14b, 32K - 11.43 (16 GB card) | chat itself | off | `██████████████░░` 11.43 + 2.18 = 13.61 / 16 |
| Most features (rec.) | qwen3:8b, 32K - 7.36 (16 GB card) | chat itself | qwen2.5vl:3b, 8K - 3.66 (16 GB card, beside chat) | `██████████████░░` 11.02 + 2.51 = 13.53 / 16 |

**24 GB** (`one_24gb`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (24 GB card) | chat itself | off | `█████░░░░░░░░░░░` 4.94 + 2.18 = 7.12 / 24 |
| Smartest answers | qwen3:14b, 32K - 11.43 (24 GB card) | chat itself | off | `█████████░░░░░░░` 11.43 + 2.18 = 13.61 / 24 |
| Most features (rec.) | qwen3:8b, 32K - 7.36 (24 GB card) | chat itself | qwen2.5vl:7b, 8K - 6.39 (24 GB card, beside chat) | `███████████░░░░░` 13.75 + 2.51 = 16.26 / 24 |

**6 GB** (`one_6gb`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 12K - 3.44 (6 GB card) | chat itself | off | `███████████████░` 3.44 + 2.18 = 5.62 / 6 |
| Smartest answers (rec.) | qwen3:4b, 12K - 3.44 (6 GB card) | chat itself | off | `███████████████░` 3.44 + 2.18 = 5.62 / 6 |
| Most features | qwen3:4b, 12K - 3.44 (6 GB card) | chat itself | qwen2.5vl:3b, 8K - 3.66 (6 GB card, by swapping with chat) | `████████████████` 3.66 + 2.18 = 5.84 / 6 |

**8 GB - the owner's PC today** (`one_8gb`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (RTX 2080 SUPER) | chat itself | off | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |
| Smartest answers (rec.) | qwen3:8b, 8K - 5.57 (RTX 2080 SUPER) | off | off | `███████████████░` 5.57 + 2.18 = 7.75 / 8 |
| Most features | qwen3:4b, 32K - 4.94 (RTX 2080 SUPER) | chat itself | qwen2.5vl:3b, 8K - 3.66 (RTX 2080 SUPER, by swapping with chat) | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |

**An older 8 GB NVIDIA card (Maxwell, before GTX 10)** (`one_8gb_maxwell`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 16K f16 - 4.79 (Quadro M5000) | chat itself | off | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |
| Smartest answers (rec.) | qwen3:4b, 16K f16 - 4.79 (Quadro M5000) | chat itself | off | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |
| Most features | qwen3:4b, 16K f16 - 4.79 (Quadro M5000) | chat itself | qwen2.5vl:3b, 8K f16 - 3.79 (Quadro M5000, by swapping with chat) | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |

**GTX 1080, 8 GB (Pascal)** (`one_8gb_pascal`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (GTX 1080) | chat itself | off | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |
| Smartest answers (rec.) | qwen3:8b, 8K - 5.57 (GTX 1080) | off | off | `███████████████░` 5.57 + 2.18 = 7.75 / 8 |
| Most features | qwen3:4b, 32K - 4.94 (GTX 1080) | chat itself | qwen2.5vl:3b, 8K - 3.66 (GTX 1080, by swapping with chat) | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |

**RX 7600, 8 GB (ROCm)** (`one_8gb_rocm`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (RX 7600) | chat itself | off | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |
| Smartest answers (rec.) | qwen3:8b, 8K - 5.57 (RX 7600) | off | off | `███████████████░` 5.57 + 2.18 = 7.75 / 8 |
| Most features | qwen3:4b, 32K - 4.94 (RX 7600) | chat itself | qwen2.5vl:3b, 8K - 3.66 (RX 7600, by swapping with chat) | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |

**RX 6600, 8 GB (Vulkan)** (`one_8gb_vulkan_amd`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 16K f16 - 4.79 (RX 6600) | chat itself | off | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |
| Smartest answers (rec.) | qwen3:4b, 16K f16 - 4.79 (RX 6600) | chat itself | off | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |
| Most features | qwen3:4b, 16K f16 - 4.79 (RX 6600) | chat itself | qwen2.5vl:3b, 8K f16 - 3.79 (RX 6600, by swapping with chat) | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |

**Intel Arc, 8 GB (Vulkan)** (`one_8gb_vulkan_intel`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 16K f16 - 4.79 (Arc A750) | chat itself | off | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |
| Smartest answers (rec.) | qwen3:4b, 16K f16 - 4.79 (Arc A750) | chat itself | off | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |
| Most features | qwen3:4b, 16K f16 - 4.79 (Arc A750) | chat itself | qwen2.5vl:3b, 8K f16 - 3.79 (Arc A750, by swapping with chat) | `██████████████░░` 4.79 + 2.18 = 6.97 / 8 |

**12 + 12 GB, monitor on one of them** (`two_12_12`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (12 GB card A) | chat itself | qwen2.5vl:7b, 8K - 6.39 (12 GB card B) | `█████████░░░░░░░` 4.94 + 1.68 = 6.62 / 12 · `███████████░░░░░` 6.39 + 2.18 = 8.57 / 12 |
| Smartest answers | qwen3:14b, 16K - 10.10 (12 GB card A) | qwen3:8b, 32K - 7.36 (12 GB card B, taking turns) | qwen2.5vl:7b, 8K - 6.39 (12 GB card B, taking turns) | `████████████████` 10.10 + 1.68 = 11.78 / 12 · `█████████████░░░` 7.36 + 2.18 = 9.54 / 12 |
| Most features (rec.) | qwen3:8b, 32K - 7.36 (12 GB card A) | chat itself | qwen2.5vl:7b, 8K - 6.39 (12 GB card B) | `████████████░░░░` 7.36 + 1.68 = 9.04 / 12 · `███████████░░░░░` 6.39 + 2.18 = 8.57 / 12 |

**RTX 2080 SUPER + RTX 2060 12 GB, monitor on the 2060** (`two_2080s_2060_mon12`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (RTX 2080 SUPER) | chat itself | qwen2.5vl:7b, 8K - 6.39 (RTX 2060) | `█████████████░░░` 4.94 + 1.68 = 6.62 / 8 · `███████████░░░░░` 6.39 + 2.18 = 8.57 / 12 |
| Smartest answers | qwen3:14b, 8K - 9.44 (RTX 2060) | qwen3:4b, 32K - 4.94 (RTX 2080 SUPER, taking turns) | qwen2.5vl:3b, 8K - 3.66 (RTX 2080 SUPER, taking turns) | `█████████████░░░` 4.94 + 1.68 = 6.62 / 8 · `███████████████░` 9.44 + 2.18 = 11.62 / 12 |
| Most features (rec.) | qwen3:8b, 16K - 6.17 (RTX 2080 SUPER) | qwen3:8b, 32K - 7.36 (RTX 2060, taking turns) | qwen2.5vl:7b, 8K - 6.39 (RTX 2060, taking turns) | `████████████████` 6.17 + 1.68 = 7.85 / 8 · `█████████████░░░` 7.36 + 2.18 = 9.54 / 12 |

**RTX 2080 SUPER + RTX 2060 12 GB, monitor on the 2080 SUPER - the planned pair** (`two_2080s_2060_mon8`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (RTX 2080 SUPER) | chat itself | qwen2.5vl:7b, 8K - 6.39 (RTX 2060) | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 · `███████████░░░░░` 6.39 + 1.68 = 8.07 / 12 |
| Smartest answers | qwen3:14b, 16K - 10.10 (RTX 2060) | qwen3:4b, 32K - 4.94 (RTX 2080 SUPER, taking turns) | qwen2.5vl:3b, 8K - 3.66 (RTX 2080 SUPER, taking turns) | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 · `████████████████` 10.10 + 1.68 = 11.78 / 12 |
| Most features (rec.) | qwen3:8b, 8K - 5.57 (RTX 2080 SUPER) | qwen3:14b, 16K - 10.10 (RTX 2060, taking turns) | qwen2.5vl:7b, 8K - 6.39 (RTX 2060, taking turns) | `███████████████░` 5.57 + 2.18 = 7.75 / 8 · `████████████████` 10.10 + 1.68 = 11.78 / 12 |

**RTX 2080 SUPER + RTX 2080 Ti (11 GB, the faster), monitor on the 8** (`two_2080s_2080ti`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (RTX 2080 Ti) | chat itself | qwen2.5vl:3b, 8K - 3.66 (RTX 2080 SUPER) | `██████████░░░░░░` 4.94 + 1.68 = 6.62 / 11 · `████████████░░░░` 3.66 + 2.18 = 5.84 / 8 |
| Smartest answers | qwen3:8b, 32K - 7.36 (RTX 2080 Ti) | chat itself | qwen2.5vl:3b, 8K - 3.66 (RTX 2080 SUPER) | `█████████████░░░` 7.36 + 1.68 = 9.04 / 11 · `████████████░░░░` 3.66 + 2.18 = 5.84 / 8 |
| Most features (rec.) | qwen3:8b, 32K - 7.36 (RTX 2080 Ti) | chat itself | qwen2.5vl:3b, 8K - 3.66 (RTX 2080 SUPER) | `█████████████░░░` 7.36 + 1.68 = 9.04 / 11 · `████████████░░░░` 3.66 + 2.18 = 5.84 / 8 |

**8 + 10 GB, monitor on the 10** (`two_8_10_mon10`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (8 GB card) | chat itself | qwen2.5vl:7b, 8K - 6.39 (10 GB card) | `█████████████░░░` 4.94 + 1.68 = 6.62 / 8 · `██████████████░░` 6.39 + 2.18 = 8.57 / 10 |
| Smartest answers | qwen3:8b, 16K - 6.17 (8 GB card) | qwen3:8b, 32K - 7.36 (10 GB card, taking turns) | qwen2.5vl:7b, 8K - 6.39 (10 GB card, taking turns) | `████████████████` 6.17 + 1.68 = 7.85 / 8 · `███████████████░` 7.36 + 2.18 = 9.54 / 10 |
| Most features (rec.) | qwen3:8b, 16K - 6.17 (8 GB card) | qwen3:8b, 32K - 7.36 (10 GB card, taking turns) | qwen2.5vl:7b, 8K - 6.39 (10 GB card, taking turns) | `████████████████` 6.17 + 1.68 = 7.85 / 8 · `███████████████░` 7.36 + 2.18 = 9.54 / 10 |

**8 + 10 GB, monitor on the 8** (`two_8_10_mon8`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (8 GB card) | chat itself | qwen2.5vl:7b, 8K - 6.39 (10 GB card) | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 · `█████████████░░░` 6.39 + 1.68 = 8.07 / 10 |
| Smartest answers | qwen3:8b, 8K - 5.57 (8 GB card) | qwen3:8b, 32K - 7.36 (10 GB card, taking turns) | qwen2.5vl:7b, 8K - 6.39 (10 GB card, taking turns) | `███████████████░` 5.57 + 2.18 = 7.75 / 8 · `██████████████░░` 7.36 + 1.68 = 9.04 / 10 |
| Most features (rec.) | qwen3:8b, 8K - 5.57 (8 GB card) | qwen3:8b, 32K - 7.36 (10 GB card, taking turns) | qwen2.5vl:7b, 8K - 6.39 (10 GB card, taking turns) | `███████████████░` 5.57 + 2.18 = 7.75 / 8 · `██████████████░░` 7.36 + 1.68 = 9.04 / 10 |

**8 + 11 GB, monitor on the 8 (the 11 GB card slower)** (`two_8_11_mon8`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (8 GB card) | chat itself | qwen2.5vl:7b, 8K - 6.39 (11 GB card) | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 · `████████████░░░░` 6.39 + 1.68 = 8.07 / 11 |
| Smartest answers | qwen3:8b, 8K - 5.57 (8 GB card) | qwen3:8b, 32K - 7.36 (11 GB card, taking turns) | qwen2.5vl:7b, 8K - 6.39 (11 GB card, taking turns) | `███████████████░` 5.57 + 2.18 = 7.75 / 8 · `█████████████░░░` 7.36 + 1.68 = 9.04 / 11 |
| Most features (rec.) | qwen3:8b, 8K - 5.57 (8 GB card) | qwen3:8b, 32K - 7.36 (11 GB card, taking turns) | qwen2.5vl:7b, 8K - 6.39 (11 GB card, taking turns) | `███████████████░` 5.57 + 2.18 = 7.75 / 8 · `█████████████░░░` 7.36 + 1.68 = 9.04 / 11 |

**8 + 16 GB, monitor on the 16** (`two_8_16_mon16`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (8 GB card) | chat itself | qwen2.5vl:7b, 8K - 6.39 (16 GB card) | `█████████████░░░` 4.94 + 1.68 = 6.62 / 8 · `█████████░░░░░░░` 6.39 + 2.18 = 8.57 / 16 |
| Smartest answers | qwen3:14b, 32K - 11.43 (16 GB card) | chat itself | qwen2.5vl:3b, 8K - 3.66 (8 GB card) | `███████████░░░░░` 3.66 + 1.68 = 5.34 / 8 · `██████████████░░` 11.43 + 2.18 = 13.61 / 16 |
| Most features (rec.) | qwen3:8b, 16K - 6.17 (8 GB card) | qwen3:8b, 32K - 7.36 (16 GB card, taking turns) | qwen2.5vl:7b, 8K - 6.39 (16 GB card, taking turns) | `████████████████` 6.17 + 1.68 = 7.85 / 8 · `██████████░░░░░░` 7.36 + 2.18 = 9.54 / 16 |

**8 + 16 GB, monitor on the 8** (`two_8_16_mon8`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (8 GB card) | chat itself | qwen2.5vl:7b, 8K - 6.39 (16 GB card) | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 · `████████░░░░░░░░` 6.39 + 1.68 = 8.07 / 16 |
| Smartest answers | qwen3:14b, 32K - 11.43 (16 GB card) | chat itself | qwen2.5vl:3b, 8K - 3.66 (8 GB card) | `████████████░░░░` 3.66 + 2.18 = 5.84 / 8 · `█████████████░░░` 11.43 + 1.68 = 13.11 / 16 |
| Most features (rec.) | qwen3:8b, 8K - 5.57 (8 GB card) | qwen3:14b, 16K - 10.10 (16 GB card, taking turns) | qwen2.5vl:7b, 8K - 6.39 (16 GB card, taking turns) | `███████████████░` 5.57 + 2.18 = 7.75 / 8 · `████████████░░░░` 10.10 + 1.68 = 11.78 / 16 |

**8 + 8 GB, monitor on one of them** (`two_8_8`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (8 GB card A) | chat itself | qwen2.5vl:3b, 8K - 3.66 (8 GB card B) | `█████████████░░░` 4.94 + 1.68 = 6.62 / 8 · `████████████░░░░` 3.66 + 2.18 = 5.84 / 8 |
| Smartest answers | qwen3:8b, 16K - 6.17 (8 GB card A) | qwen3:4b, 32K - 4.94 (8 GB card B, taking turns) | qwen2.5vl:3b, 8K - 3.66 (8 GB card B, taking turns) | `████████████████` 6.17 + 1.68 = 7.85 / 8 · `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |
| Most features (rec.) | qwen3:8b, 16K - 6.17 (8 GB card A) | qwen3:4b, 32K - 4.94 (8 GB card B, taking turns) | qwen2.5vl:3b, 8K - 3.66 (8 GB card B, taking turns) | `████████████████` 6.17 + 1.68 = 7.85 / 8 · `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |

**RTX 2080 SUPER + RX 7600 (the second card not NVIDIA)** (`two_8_rx7600`)

| Preset | Chat | Long context | Pictures | Memory |
|---|---|---|---|---|
| Fastest answers | qwen3:4b, 32K - 4.94 (RTX 2080 SUPER) | chat itself | off | `██████████████░░` 4.94 + 2.18 = 7.12 / 8 |
| Smartest answers | qwen3:8b, 8K - 5.57 (RTX 2080 SUPER) | off | off | `███████████████░` 5.57 + 2.18 = 7.75 / 8 |
| Most features (rec.) | qwen3:8b, 8K - 5.57 (RTX 2080 SUPER) | off | off | `███████████████░` 5.57 + 2.18 = 7.75 / 8 |

<!-- hardware-cases:end -->

### 4.5 Applying a preset

**Plain words:** you press **Use this**. Jarvis shows exactly what will
happen, then asks you with the same approval cards as today, one at a time.
Anything Ollama only reads when it starts is a line you run yourself.

Step by step:

1. **Preview.** The preset screen lists, in order: models to download (with
   computed sizes), models to create (`jarvis-chat`, `jarvis-long`,
   `jarvis-vision` from generated Modelfiles), the switch, the lanes to turn
   on, and whether Ollama needs a restart.
2. **Downloads:** one `POST /api/models/install` approval card per missing
   model - the existing card, tier `ask`, nothing downloads until approved.
3. **Creating the tuned models:** a new action `models_create`, tier `ask`,
   one card per Modelfile, showing the Modelfile's text. (Today's
   `jarvis-primary` is made by hand with `ollama create`.)
4. **Switching chat:** the existing `POST /api/models/switch` card.
5. **Lanes:** the existing `second_card_enable` card per feature.
6. **Start-up settings:** Jarvis generates **one PowerShell line**
   (5.1-safe) for the detected cards, shown with a Copy button. For the
   planned 2080 Super + 2060 it would be (the id is made up; Jarvis fills in
   the real one):

   ```powershell
   [Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User'); [Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '-1', 'User'); [Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', 'GPU-3f2a9c1e-7b1d-4e8a-9c55-0d4b2e6a8f10', 'User'); [Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', '0', 'User'); Write-Host 'Saved 4 settings for your Windows user (nothing was written to a file). Now quit Ollama (right-click its icon by the clock, then Quit Ollama) and start it again from the Start menu.'
   ```

   Rules for the generator: only `[Environment]::SetEnvironmentVariable(...,
   'User')` and one `Write-Host`; no `??`, no `?.`, no `&&`; values
   validated against a fixed pattern (`GPU-[0-9a-f-]+`, `q8_0|f16`,
   integers); only these variable names: `OLLAMA_KV_CACHE_TYPE`,
   `OLLAMA_KEEP_ALIVE`, `CUDA_VISIBLE_DEVICES`, `OLLAMA_VULKAN`, and - only
   if decision 1 says so - `LLAMA_ARG_FIT_TARGET`. A matching undo line
   (each set to `$null`) is always shown beside it. Single-card PCs get no
   `CUDA_VISIBLE_DEVICES`. AMD/Intel PCs get no `OLLAMA_VULKAN`.
   To check what is set, one line (prints only):

   ```powershell
   foreach ($n in 'OLLAMA_KV_CACHE_TYPE','OLLAMA_KEEP_ALIVE','CUDA_VISIBLE_DEVICES','OLLAMA_VULKAN','LLAMA_ARG_FIT_TARGET') { '{0} = {1}' -f $n, [Environment]::GetEnvironmentVariable($n, 'User') }
   ```

**What needs an Ollama restart:** any of those variables (Ollama reads them
once, at start-up - `envconfig` is read from the process environment).
**What does not:** installing, creating or switching models; lanes (Jarvis
starts and stops the second Ollama itself). Jarvis notices a pending restart
by comparing the user settings with the `user overrode visible devices`
and `starting llama-server ... --cache-type-k` lines in Ollama's log, and
says "Ollama has not picked this up yet - restart it" until they match.

**Nothing applies silently (rule 4).** There is no combined "approve all"
card - each step is its own card, in order, and the preset screen shows
which are done. That keeps clear of CLAUDE.md's "never build a control that
... approves in bulk". If the owner declines one, the steps after it wait.

### 4.6 What you see

**Desktop, Settings → "Hardware and models"** (replaces and contains
today's "Second graphics card" section):

1. **Your cards** - one row per card: name, memory, generation, route
   (CUDA/ROCm/Vulkan), monitor yes/no, which source said so, and for an
   unused card, why (in Ollama's words, translated).
2. **Now running** - the current layout with memory bars, marked
   "Custom (your own setup)" when it matches no preset, and **"measured"**
   or **"calculated, not measured"**.
3. **Three choices** - Fastest answers / Smartest answers / Most features,
   each a card with: one sentence, the models, context in plain words
   ("remembers about 24 pages of conversation" - an estimate, labelled),
   memory bars, "what is off, and why", and **Use this**. The recommended one
   is marked **(recommended)**, with one sentence saying why.
4. **The one command** - the generated line and its undo line, with Copy.
5. **Details** (collapsed) - every number with its arithmetic, as in 8.2.
6. The existing five lane switches stay, under "Extra features".

**Phone (Mind → "Hardware")**: your cards (names and memory only), the
current preset and whether it is measured, the recommended preset, and
**Apply**, which asks the PC to start the steps in 4.5 - each still an
approval card the owner answers on the PC or the phone. The phone shows
the PowerShell line as text to read, not to run.

**Keeping the phone from becoming a model catalogue** (CLAUDE.md): the phone
receives **three preset ids with their summaries**, generated on the PC for
*this* PC's cards - never a list of models that could be installed, never a
search, never a model picker. It cannot compose a preset or choose a
different model; the typed-name install box that already exists is
unchanged. The API returns preset contents as display text plus opaque ids,
so a future client cannot turn it into a browser either.

### 4.7 Measuring

Everything above is labelled **"calculated, not measured"** until the speed
recorder (`backend/jarvis_speed.py`) has rows for that exact preset on
that exact hardware (keyed by a fingerprint: card names + total memory +
Ollama version + preset).

After a preset is applied, Jarvis offers **Measure** (one button, one short
prompt per role, `kind: "bench"` rows as today) and records:

- words per second and time to first word (already recorded);
- **how much of the model is on the card**: `size_vram ÷ size` from
  `/api/ps` (`api/types.go:854-863`) - anything under 100% is a red warning,
  "part of the model is on the processor";
- from Ollama's log: `offloaded N/M layers to GPU`, and whether
  `enabling flash_attn since it is required for quantized V cache` appeared;
- free memory on each card with the models loaded (source 2).

The two-line check for today's setup, before anything else is built (prints
only; reads Ollama's log file):

```powershell
Select-String -Path "$env:LOCALAPPDATA\Ollama\server.log" -Pattern 'offloaded \d+/\d+ layers to GPU|flash_attn|starting llama-server' | Select-Object -Last 4 | ForEach-Object { $_.Line }
```

Run it after sending Jarvis one message. `offloaded 37/37` means the whole
of Qwen 3 8B is on the card. A smaller first number means item 1 in section
3 is real. (37 = 36 layers + the output layer, as llama.cpp counts them;
check the second number rather than trusting mine.)

```powershell
Select-String -Path "$env:LOCALAPPDATA\Ollama\server.log" -Pattern 'inference compute|vram-based default context|user overrode visible devices' | Select-Object -Last 6 | ForEach-Object { $_.Line }
```

This one shows what Ollama found at start-up, including each card's free
memory (`available`) - which is the measured desktop share for 4.1.

### 4.8 Migrating from today's hand-tuned 2080 Super

- **Nothing changes until the owner picks a preset.** Today's layout
  (`jarvis-primary`, `q8_0`, keep-alive −1, second-card switches off) is
  shown as **"Custom (your own setup)"**, with its calculated bar - which,
  by item 1 of section 3, will show it slightly over - and the Measure
  button.
- The second-card switches keep working exactly as now until a preset is
  applied; their stored state (`second_card.json` or equivalent) is read,
  not rewritten.
- `jarvis-primary` stays installed. A preset creates new names
  (`jarvis-chat`, ...) rather than overwriting it, so going back is a
  model switch.
- The one-command line in SECOND-CARD.md is superseded by the generated one
  (it adds `OLLAMA_VULKAN=0`); the old line keeps working as it does today.
  *Since then (2026-09-24):* the line SECOND-CARD.md shows (`pin_command`)
  already adds `OLLAMA_VULKAN=0`, without waiting for presets.

---

## 5. Decisions for the owner - DECIDED 2026-09-24

The owner answered all four. The build follows these; the options that were
offered are kept below each answer.

**1. The empty gap on each graphics card: 0.75 GB** (the owner's own middle
choice). llama.cpp's default is 1 GB (`common/common.h:481`,
1024 MiB per device). With the arithmetic of section 4.4 (8B chat grows
~0.075 GiB per 1,000 tokens of context; desktop share + CUDA start-up ~1.43
GiB), the 8 GB card holds about **11,000** tokens of chat at 0.75 GB, against
~6,000 at 1 GB and ~12-14,000 at 0.5 GB. **Calculated, not measured:** the
presets use 0.75 GB, the measuring step (4.7) confirms it on the owner's PC,
and a preset that does not fit when measured drops to the next context size
rather than spilling onto the processor.
(Offered: keep 1 GB and measure first; lower to 0.5 GB now.)

**2. AMD and Intel cards: best effort, marked "not tested".** Detected and
given safe settings (f16 cache on Vulkan, section 2.2), with every preset on
those cards labelled untested.
(Offered: full support, same as NVIDIA.)

**3. Ollama's Vulkan route: switched off on all-NVIDIA PCs, in the same
one-line command** (`OLLAMA_VULKAN=0`; the default is on,
`envconfig/config.go:234`). The second-card lane's environment must set it
too, not just remove `GGML_VK_VISIBLE_DEVICES` (a bug in today's
`jarvis_second_card.py`, on the bug audit's fix list).
*Since then (2026-09-24): fixed* - `lane_env` and `pin_command` both set
`OLLAMA_VULKAN=0`.
(Offered: leave it on.)

**4. Spark-X2.5-4B: test later**, once the second card is installed and
measured, against the Qwen choice; not in any preset until then.
(Offered: not at all.)

---

## 6. Risks and unknowns

**Not measured, and the table depends on them:**

- The desktop share (1.10 / 0.60 GiB), the CUDA start-up cost (0.33 GiB),
  and the compute buffers (0.25-0.35 GiB) - all carried over from earlier
  docs or assumed. The 8 GB rows are the most sensitive: ±0.3 GiB moves 8B
  chat between 4K and 12K.
- The picture models' real sizes (the picture reader is assumed `f16`) and
  the memory to encode one picture (0.25 GiB placeholder).
- Swap time for pictures on one card.
- Whether Pascal, ROCm and Vulkan run `q8_0` at a useful speed.

**Read from source but not run:**

- Vulkan placing chat on the 2060 despite `CUDA_VISIBLE_DEVICES` (2.3).
- The 1 GiB fit margin pushing today's `jarvis-primary` partly onto the
  processor (section 3, item 1).
- What Windows' NVIDIA driver does when CUDA runs out of memory (it may
  borrow system memory rather than fail).

**Could not verify at all from here:**

- Real download sizes, tags and tool-call parsers of the models on
  ollama.com (blocked). Qwen 3 4B's and Qwen2.5-VL-7B's shapes were read from
  other models that share them (2.8).
- Whether a released Ollama for Windows honours `gfx1030` (the build says
  yes, the docs table says only RX 7000).
- Spark-X2.5-4B's minimum Ollama version, quality and tool use.
- A reliable one-liner for "which non-NVIDIA card drives the monitor".
- `nvidia-smi`'s `display_active` meaning under Windows (Jarvis already
  relies on it; this design stops relying on it for choosing the main card).

**Design risks:**

- Ollama changes fast (this code is two days old). The planner must read
  Ollama's version and treat an unknown one as "calculated with older
  rules - measure".
- A preset is a promise about memory. Anything else using the card (a game,
  a browser with hardware video) can break it after the fact; the measured
  check must be repeatable at any time, not once.
- Two Ollamas mean two sets of settings. The second is Jarvis's; the first
  is the owner's. A mismatch (say, the owner removes `OLLAMA_VULKAN=0`) must
  show on the Hardware screen, not only in a log.

---

## 7. Build plan

Order matters: the measurement first, because it may change the numbers.

1. **Measure today's setup (no code).** The owner runs the two lines in 4.7
   and pastes the output. This confirms or kills section 3, item 1, and
   gives the real desktop share.
2. **`backend/jarvis_hardware.py`** (new, standard library only) - detection
   (4.1): parse Ollama's `server.log` start-up block, `nvidia-smi` (reuse
   `jarvis_compute.query_cards`), the registry one-liner via
   `reg query`/`winreg`, join by PCI id; the "fastest card" rule; the
   measured desktop share. Never raises; `simulated` like `jarvis_compute`.
3. **`backend/jarvis_profiles.py`** (new, pure functions, no I/O) - the
   model table (8.2), the budget formula (4.2) including Ollama's gate, and
   `plan(cards, preset) -> Layout`. Constants in one place, each with the
   source string that the Details view shows.
4. **Golden tests: `backend/test_profiles.py`** - every case in 4.4 × three
   presets, as a fixture file `backend/fixtures/hardware_cases.json`
   (input cards → expected models, contexts, cards, bars ± 0.01 GiB, and
   the "off" reasons). The table in this document is generated from the
   same fixture, so doc and code cannot drift. Plus: Ollama's gate
   rejecting 14B beside chat on 24 GB; 6 GB refusing pictures; Vulkan → f16;
   Maxwell → f16 and no `q8_0`.
5. **Detection tests: `backend/test_hardware.py`** - replayed `server.log`
   blocks (NVIDIA pair, ROCm, Vulkan-only, a dropped `gfx1032`, an
   "overrode visible devices" line), `nvidia-smi` CSV, registry output.
   All made-up values, labelled so.
6. **PowerShell generator** in `jarvis_profiles.py`, with tests that every
   generated line parses under `/opt/pwsh` (`[Parser]::ParseInput`), has no
   PowerShell-7-only operators, uses only the allowed names and patterns,
   and has an undo line.
7. **Generalise `jarvis_second_card.py`** (4.3) - keep ids, switches,
   approval model and API; placement from the planner; `OLLAMA_VULKAN=0`;
   refuse flash off with `q8_0`; single-card lanes inside the everyday
   Ollama. Existing `test_second_card.py` and
   `test_phone_second_card_contract.py` must pass unchanged, plus new
   single-card tests.
8. **API** - `GET /api/hardware` (cards, current layout, three presets,
   recommended, the generated line, measured/calculated),
   `POST /api/hardware/apply {"preset": "fast"|"smart"|"features"}` (starts
   4.5; returns the step list; each step raises its own card),
   `POST /api/hardware/measure`. New action `models_create`, tier `ask`.
   Contract fixtures `docs/reference/hardware-*.json` shared by both apps,
   with a test on each side (as for the second card).
9. **Desktop** - Settings "Hardware and models" (4.6), folding in today's
   "Second graphics card" section. Rust checked with the Windows-target
   `cargo check`/`clippy` per CLAUDE.md.
10. **Phone** - the Hardware plate on Mind (4.6), from the fixture;
    `ApiContractTest` entries for the three routes. CI is the only compiler
    for it (CLAUDE.md).
11. **Docs** - MODEL-TOPOLOGY.md's stale items (section 3) rewritten from
    the measured numbers; SECOND-CARD.md's one command replaced by the
    generated one; INSTALL.md 1.7 pointed at the Hardware screen.

### 7.1 What was built (2026-09-25), and where it differs

Built: steps 2-10, and 11 as far as it can go without a measurement. Step 1
(the owner's two lines, section 4.7) has not been run, so nothing below is
measured. Where the build differs from the design above, it says so here
rather than quietly:

- **Steps 2-6.** `backend/jarvis_hardware.py` (detection, the steps, making a
  model, measuring) and `backend/jarvis_profiles.py` (the arithmetic, the
  presets, the one line; no I/O). `backend/test_profiles.py` replays **every
  row of section 4.4 at 1 GB** and gets it (model, context, card, lanes, how
  they share, each card's bar within 0.01 GB); the golden file at the owner's
  0.75 GB is `backend/fixtures/hardware_cases.json`, and the table in 4.4
  ("The presets as built") is generated from it. PowerShell 7 parses every
  generated line, with no PowerShell-7-only token in any (the sandbox let the
  test suite start `/opt/pwsh/pwsh` this time).
- **The planner's rules, read out of the 4.4 tables** (the throwaway script
  that made them was not committed): chat contexts come from 4K, 6K, 8K,
  12K, 16K and 32K; an 8B or 14B needs at least 6K, the 4B 8K; "long
  conversations" means at least 12K; the long lane on another card tries
  14B at 16K, 12K, 8K, then 8B and 4B at 32K, and must beat chat's context -
  **so a 14B lane never gets more than 16K even where 32K would fit (8 + 16
  GB)**, as the tables have it; Smartest keeps chat on the faster card when
  the biggest model gets at least 8K there. The picture reader counts its
  patch layer (the tables' 3.65 is 3.66 here - within the 0.01 the tests
  allow).
- **Detection.** `Win32_VideoController` (source 4) is not read: its memory
  field stops at 4 GB and the registry already gives the names. The
  "fastest card" is published speed where both are known (only the three
  cards MODEL-TOPOLOGY.md gives figures for), then a card Jarvis's settings
  are made for (NVIDIA, RTX 20 or newer) before a best-effort one, then the
  newer generation, then more room. **The measured "same prompt on each card"
  comparison is not built.** `jarvis_compute.primary()` (the monitor rule)
  is unchanged: it still decides where the second card's lanes go when no
  setup is chosen, so today's behaviour does not move.
- **Applying (4.5).** The design has the PC start the steps. The download
  and switch cards belong to the owner's own `jarvis_hud.py`, which this
  repository cannot call into, so **each step is one button in the app that
  posts that step's own route and body, read from the PC's answer** (the
  Rust and the Kotlin refuse anything else). Only the next step has a
  button; there is still no "approve all". The recommended setup is
  "Most features" when its everyday model is the 8B or bigger, else
  "Smartest answers" (the design did not say; the owner can ignore it).
- **One card, lanes inside the everyday Ollama (4.3)**: built. With a setup
  chosen, `jarvis_second_card.py` takes its lanes from the planner; with
  none chosen it is exactly as before (its old tests pass unchanged).
- **The contract files** are `jarvis-desktop/tests/fixtures/hardware-cases.json`
  and the phone's byte-for-byte copy, as for the second card, not
  `docs/reference/`. The phone reads them in the JVM test
  `HardwareContractTest.kt`; the emulator's `ApiContractTest.kt` has four new
  entries for the routes (headers, the choice's body, a refused route never
  sent, a refusal's own sentence) - those run only in CI.
- **The desktop's section** sits above "Second graphics card" rather than
  swallowing it: the five switches keep their own section, named as before.
- **Not built:** reading Ollama's version to warn about "calculated with
  older rules" (the version is shown and keys the measurements, nothing
  more); the measured desktop share for a non-NVIDIA card with nothing
  loaded (Ollama's own start-up reading is used). Qwen 3.5 (research,
  2026-09-24) is listed beside Spark-X2.5 as "test later", in no preset.

---

## 8. Appendix: every number used

### 8.1 Room per card

`room = total − desktop share − 0.33 × processes − 1.00` (then −0.10
cushion when planning). Desktop share: 1.10 with the monitor, 0.60 without
(placeholders, 4.1).

| Card | Monitor, 1 model | Monitor, 2 models | No monitor, 1 model | No monitor, 2 models |
|---|---|---|---|---|
| 6 GB | 3.57 | 3.24 | - | - |
| 8 GB | 5.57 | 5.24 | 6.07 | 5.74 |
| 10 GB | 7.57 | 7.24 | 8.07 | 7.74 |
| 11 GB | 8.57 | 8.24 | 9.07 | 8.74 |
| 12 GB | 9.57 | 9.24 | 10.07 | 9.74 |
| 16 GB | 13.57 | 13.24 | 14.07 | 13.74 |
| 24 GB | 21.57 | 21.24 | - | - |

"GB" on a card's box is taken as GiB here (an 8 GB card reports 8,192 MiB).
Real cards can report slightly less; the measured figure replaces this.

### 8.2 Model needs (GiB)

`weights (+ picture reader) + context × cache per token + compute (+ 0.25 picture)`,
`q8_0` unless marked. Ollama's guess (2.5) alongside, because it decides
co-residence.

| Model @ context | Sum | Need | Ollama's guess |
|---|---|---|---|
| qwen3:4b @ 8K | 2.29 + 0.60 + 0.25 | 3.14 | 3.00 |
| qwen3:4b @ 12K | 2.29 + 0.90 + 0.25 | 3.44 | - |
| qwen3:4b @ 16K | 2.29 + 1.20 + 0.25 | 3.74 | 3.70 |
| qwen3:4b @ 32K | 2.29 + 2.39 + 0.25 | 4.94 | 5.11 |
| qwen3:4b @ 16K f16 | 2.29 + 2.25 + 0.25 | 4.79 | - |
| qwen3:8b @ 6K | 4.67 + 0.45 + 0.30 | 5.42 | - |
| qwen3:8b @ 8K | 4.67 + 0.60 + 0.30 | 5.57 | 5.80 |
| qwen3:8b @ 12K | 4.67 + 0.90 + 0.30 | 5.87 | - |
| qwen3:8b @ 16K | 4.67 + 1.20 + 0.30 | 6.17 | 6.92 |
| qwen3:8b @ 32K | 4.67 + 2.39 + 0.30 | 7.36 | 9.17 |
| qwen3:8b @ 8K f16 | 4.67 + 1.12 + 0.30 | 6.10 | - |
| qwen3:14b @ 8K | 8.42 + 0.66 + 0.35 | 9.44 | 9.67 |
| qwen3:14b @ 12K | 8.42 + 1.00 + 0.35 | 9.77 | - |
| qwen3:14b @ 16K | 8.42 + 1.33 + 0.35 | 10.10 | 10.92 |
| qwen3:14b @ 32K | 8.42 + 2.66 + 0.35 | 11.43 | 13.42 |
| qwen2.5vl:3b @ 4K | 1.76 + 1.24 + 0.07 + 0.25 + 0.25 | 3.58 | 3.14 |
| qwen2.5vl:3b @ 8K | 1.76 + 1.24 + 0.15 + 0.25 + 0.25 | 3.65 | 3.28 |
| qwen2.5vl:7b @ 8K | 4.34 + 1.26 + 0.23 + 0.30 + 0.25 | 6.38 | 6.04 |
| llama3.2:3b @ 32K | 1.83 + 1.86 + 0.25 | 3.94 | 5.33 |
| Spark-X2.5-4B @ 32K | 2.34 + 0.60 + 0.06 + 0.30 | 3.30 | 5.16 |
| Spark-X2.5-4B @ 128K | 2.34 + 2.39 + 0.06 + 0.30 | 5.09 | - |

Cache term = tokens × bytes per token ÷ 1024³, e.g. qwen3:8b @ 16K:
16,384 × 78,336 = 1,283,457,024 B = 1.20 GiB. Ollama's guess = computed
file size + tokens × 2 × layers × KV heads × (embedding ÷ heads) × 2 B.

### 8.3 What moved from MODEL-TOPOLOGY.md, and what did not

Kept: the Q4_K_M rate (4.90 bits), 1.0625 bytes for `q8_0`, the 0.33 GiB
CUDA start-up and ~0.30 GiB compute buffer at `num_batch 512` (not
re-measured), `num_batch 512` pinned, `OLLAMA_FLASH_ATTENTION` left unset,
`OLLAMA_KEEP_ALIVE=-1` for chat, no Q8_0 weights at 7-8B, the P100 advice.
Changed: the 1 GiB margin (2.5), the direction of Ollama's estimate error
(2.5), "off" meaning a failed load (2.2), the main-card rule (4.1).

The throwaway script that produced sections 4.4 and 8 lived in a scratch
folder and is not committed; step 4 of the build plan replaces it with a
tested one.
