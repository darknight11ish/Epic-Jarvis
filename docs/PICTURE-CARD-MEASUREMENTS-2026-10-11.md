# Making pictures beside Jarvis - the missing half downloaded, and the numbers that were blocked

For the owner. Written 2026-10-11 on your PC, by the agent asked to finish the
download and get the three numbers a sibling honestly refused to guess.

**The short answer.** Both of your picture models can run now. **Option A is the
one to pick**: it draws a real 1024x1024 picture in a **median 274.4 seconds**
(4.6 minutes), uses **10,531 MiB of the 12 GB card**, and its whole price is
**8.7 seconds** of the everyday chat being away around each picture - with the
entire **196,608-token** conversation kept. **Option B** draws the same pictures
in a median **319.1 seconds** but costs you all but **8,192 tokens** (4.2%) of
that conversation. **Option C** is the small model on the 8 GB card: a median
**620.9 seconds** (10.3 minutes) per picture, and it needs the coding lane off
the 8 GB card to fit.

---

## 1. The one line you asked to be confirmed

**`max_download_gb` is 20.** Line 539 of
`C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis-framework.toml`.
The sibling's backup beside it still says 12. Nothing was restored, nothing was
changed.

---

## 2. What was downloaded - all six files, every hash checked

Every big file came down with a **resumable HTTP range downloader** and was
**SHA-256 checked against the hash the publisher itself publishes** before it
was moved onto its final name. `hf download` was never used: it hangs at 0% on
this PC for anything over ~5 MB and leaves a child process holding a lock.
`Start-Job` workers and `curl.exe` were avoided for the two reasons the
sibling's own scripts recorded here (0 bytes through a harness pipe;
`Start-Process -ArgumentList` splitting a path at the space in `Jarvis Models`).

| File | Size | SHA-256 | Licence | State |
|---|---|---|---|---|
| `torch-2.7.1+cu126-cp312-cp312-win_amd64.whl` | 2,716,918,001 | `7d897b5f…f08b` | BSD-3-Clause | **downloaded, hash OK** |
| `torchvision-0.22.1+cu126-cp312-cp312-win_amd64.whl` | 6,334,174 | `8a465823…ce91` | BSD-3-Clause | **downloaded, hash OK** |
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | 5,157,348,688 | `a498f048…557a` | Apache-2.0 | **downloaded, hash OK** |
| `ae.safetensors` (FLUX/Chroma VAE) | 335,304,388 | `afc8e282…9e38` | Apache-2.0 | **downloaded, hash OK** |
| `qwen_image_2.1_vae_bf16.safetensors` | 675,509,688 | `bb21f747…b7c9` | Qwen Research License | **downloaded, hash OK** |
| `qwen3vl_8b_int8_convrot.safetensors` | 9,350,798,360 | `8bfd0f6e…2e8f` | Qwen Research License | **downloaded, hash OK** |

The full hashes are in `D:\Jarvis\ImageGen\logs\fetch-needs.log`, each on its
own `DONE … sha256=… OK` line. Sizes and hashes were not guessed: the Hugging
Face figures are the **LFS oids from Hugging Face's own API**, and PyTorch's
came from the `#sha256=` fragment on `download.pytorch.org`'s own index.

**A licence fact worth writing down:** the two Qwen-Image 2.1 companion files
are **not** Apache-2.0. `Comfy-Org/Qwen-Image-2.1` is marked
`license: other, license_name: qwen-research`. That is fine for this project -
the owner decided on 2026-09-28 that EpicJarvis is never commercialised - but
it needs its own credit line in `THIRD-PARTY-NOTICES.txt`, and the files must
not be redistributed as if they were Apache.

**Nothing is still missing for either picture model.** `fetch-needs.ps1` ended
with `FETCH-NEEDS FINISHED` and all six files in place.

### Why the download took hours

**PyTorch's own CDN gave ~0.04-0.05 MB/s on one connection** - about 15 hours
for the torch wheel. It is not a per-connection cap: throughput scaled with
concurrency, so the downloader ran 24 parallel range requests and reached
**1.0-2.1 MB/s**. The home link measured **2.2-4.3 MB/s machine-wide**, with two
other agents pulling their own models at the same time. That contention, not the
code, set the clock.

One honest note: a sibling's `curl.exe` on this same torch wheel had written
nothing for 25 minutes, so it was ended rather than leaving two writers on one
destination. It turned out to have buffered 177 MB, which was discarded and
re-fetched. That was my call and it cost about two minutes of link time.

---

## 3. The measurement trap this PC sets, and the number that proves it

`/api/ps`'s `size_vram == size` is **not** proof that nothing spilled. Measured
here, with the live product's own environment:

- `qwen3.5:9b` at **ctx 8192 on the 12 GB card** - a load that cannot spill:
  **`load_tensors: offloaded 33/33 layers to GPU`**, `/api/ps` says
  `vram 5,703,100,005 / size 5,703,100,005` (spill 0) - and llama.cpp's own log
  still says **`load_tensors: CUDA_Host model buffer size = 545.63 MiB`**.

So that figure is **never zero**, and testing it against zero would condemn
every load. What separates a clean load from a spilled one here is the **layer
count**, and then the size of the figure:

| Load | Layers on the card | `CUDA_Host model buffer` | `/api/ps` spill |
|---|---|---|---|
| ctx 8192, 12 GB card (cannot spill) | **33/33** | **545.63 MiB** | 0 bytes |
| ctx 8192, 8 GB card (B's price) | **33/33** | **545.63 MiB** | 0 bytes |
| ctx 196608, 12 GB card (A's reload) | **33/33** | **545.63 MiB** | 0 bytes |
| ctx 12288, 8 GB card | 32/33 | 683.55 MiB | 784,229,987 bytes |
| ctx 16384, 8 GB card | 31/33 | 821.47 MiB | 935,245,903 bytes |
| ctx 32768, 8 GB card | 29/33 | 1,085.33 MiB | 1,302,195,075 bytes |

**And the environment changes the answer by 3.5 GB.** The same 196,608-token
load with Ollama's default (f16) KV cache keeps **23 of 33 layers** on the host
and spills **3,796,201,634 bytes**. The live product does not use the default:
`jarvis_second_card.lane_env()` sets **`OLLAMA_KV_CACHE_TYPE=q8_0`**, one model,
one parallel slot. With that, the same load is 33/33 and zero spill. Every
private server used here was started from the product's own `lane_env()`, so it
had exactly that environment. A measurement taken without it is wrong by 3.5 GB.

---

## 4. A - pictures on the 12 GB card, the chat steps aside

| | Measured |
|---|---|
| **A picture is produced** | **yes** - `D:\Jarvis\ImageGen\logs\owner-pictures\jarvis-optionA_00002_.png` (also `…00003_`, `…00004_`; the same folder) |
| Seconds per picture, 1024x1024, seeds 12345/12346/12347 | 316.3 / 274.1 / 274.4 s → **median 274.4 s** |
| Peak VRAM, sampled from `nvidia-smi` during each run | **10,499 / 10,531 / 10,531 MiB of 12,288 MiB** |
| Unload (`keep_alive: 0`, through the API only) | model **gone from the card in 0.2 s** |
| Reload at 196,608 tokens | **8.5 s** |
| **A's price: the chat is away for** | **8.7 s around each picture** |
| Did the long conversation survive? | **yes - granted 196608**, `/api/ps` `vram 9,847,051,386 / size 9,847,051,386` → **spill 0**, **33/33 layers on the card** |
| The card afterwards | **10,392 MiB of 12,288 MiB** |

ComfyUI's own log for the run (the equivalent of the `CUDA_Host` line for a
picture run - there is no llama.cpp in a picture run, so the honest evidence is
ComfyUI's own load accounting plus `nvidia-smi`):

```
[INFO] Total VRAM 12288 MB, total RAM 32688 MB
[INFO] Device: cuda:0 NVIDIA GeForce RTX 2060 : cudaMallocAsync
[INFO] CLIP/text encoder model load device: cuda:0, offload device: cpu, current: cpu, dtype: torch.float16
[INFO] Requested to load PixArtTEModel_
[INFO] loaded completely; 9781.80 MB usable, 4667.39 MB loaded, full load: True
[INFO] Requested to load Chroma
[INFO] loaded completely; 9520.30 MB usable, 8774.96 MB loaded, full load: True
[INFO] loaded completely; 716.53 MB usable, 319.75 MB loaded, full load: True
```

So on the 12 GB card the T5 text encoder (**4,667 MB**) and the Chroma model
(**8,775 MB**) each load **completely** - ComfyUI swaps one out for the other -
and the peak `nvidia-smi` saw was **10,531 of 12,288 MiB**.

**Machine state when measured:** the owner's own everyday lane held the 2060
(`qwen3.5:9b`, ctx 196608, 9,847,051,386 bytes, zero spill). No other model was
resident on either card (`/api/ps` on 11430-11460 and `nvidia-smi
--query-compute-apps` both checked immediately before). The lane was unloaded
through **its own HTTP API** - no server was stopped or reconfigured - and put
back **exactly as found**, proved from `/api/ps` afterwards.

---

## 5. B - pictures on the 12 GB card, the chat moved to the 8 GB card

| | Measured |
|---|---|
| **A picture is produced** | **yes** - `…\owner-pictures\jarvis-optionB_00001_.png`, `…00002_`, `…00003_` |
| Seconds per picture, seeds 12345/12346/12347 | 363.5 / 278.7 / 319.1 s → **median 319.1 s** |
| Peak VRAM on the 12 GB card | **12,052 / 10,563 / 10,531 MiB of 12,288 MiB** |
| **B's price: the chat's zero-spill context on the 8 GB card** | **8,192 tokens** |
| Of A's 196,608-token conversation | **4.2% kept - 188,416 tokens lost** |
| The chat, resident on the 8 GB card during every draw | 33/33 layers, `CUDA_Host 545.63 MiB`, `/api/ps` spill **0**, `nvidia-smi` **7,289 of 8,192 MiB** |

The ladder on the 8 GB card, where "nothing spilled" means **every layer on the
card and `/api/ps` agreeing**:

| Context asked | Layers on the card | `CUDA_Host` | `/api/ps` spill | Verdict |
|---|---|---|---|---|
| **8,192** | **33/33** | **545.63 MiB** | **0** | **zero spill** |
| 12,288 | 32/33 | 683.55 MiB | 784,229,987 B | spilled |
| 16,384 | 31/33 | 821.47 MiB | 935,245,903 B | spilled |
| 32,768 | 29/33 | 1,085.33 MiB | 1,302,195,075 B | spilled |

B was measured **with the chat really resident on the 8 GB card during the
draws** - not as A wearing B's name.

Two things B's price does not yet include, both real:

1. **Your coding lane lives on the 8 GB card.** `qwen3:8b` (6.27 GB) is the
   model that sits there today. It and the everyday chat cannot both be on
   8,192 MiB, so B means moving or dropping that lane as well.
2. B's pictures are **the same pictures as A's** (same model, same seeds - the
   files are byte-identical), drawn **45 seconds slower** at the median, while
   costing 96% of the long conversation.

---

## 6. C - the small model on the 8 GB card, the chat untouched

| | Measured |
|---|---|
| **A picture is produced** | **yes** - `…\owner-pictures\jarvis-optionC_00001_.png`, `…00002_`, `…00003_` |
| Seconds per picture, seeds 12345/12346/12347 | 620.9 / 637.7 / 577.0 s → **median 620.9 s** (10.3 min) |
| Peak VRAM on the 8 GB card | **7,306 / 7,387 / 7,154 MiB of 8,192 MiB** |
| Model | `qwen-image-2.1-UC-Q4_K_M.gguf` (4.29 GB), 25 steps, cfg 1, euler, simple |
| Runtime | `UnetLoaderGGUF` from the **leejet** ComfyUI-GGUF fork - the ordinary one cannot read `general.architecture = qwen_image21` |
| The everyday chat | **untouched** - `qwen3.5:9b` at 196,608 tokens stayed on the 12 GB card, spill 0, throughout |

ComfyUI's own log for C:

```
[INFO] Total VRAM 8192 MB, total RAM 32688 MB
[INFO] Device: cuda:0 NVIDIA GeForce RTX 2080 SUPER : cudaMallocAsync
[INFO] Requested to load QwenImage21TEModel_
[INFO] loaded completely;  8917.48 MB loaded, full load: True
[INFO] CLIP/text encoder model load device: cpu, offload device: cpu, current: cpu, dtype: torch.float16
[INFO] Requested to load QwenImage21
[INFO] loaded completely; 5519.96 MB usable, 4487.23 MB loaded, full load: True
[INFO] loaded completely; 4666.88 MB usable, 644.19 MB loaded, full load: True
```

That is the honest shape of C: the **8,917 MB Qwen3-VL text encoder runs on the
processor**, not on the card (`--lowvram`), and only the **4,487 MB** picture
model sits in the 8 GB of VRAM. That is why C's pictures take **2.3x as long as
A's**.

**And the catch:** the 8 GB card is where your **coding lane** (`qwen3:8b`
@16384, 6.27 GB) lives. ComfyUI could not have loaded there beside it. For this
measurement the coding lane's model was unloaded through **its own API** and put
back **exactly as found** (ctx 16384, `vram 6,270,348,164 / size 6,270,348,164`,
zero spill, proved from `/api/ps`). So "the chat is untouched" is true of the
**everyday** chat and not of the coding lane - C's real price is the coding
lane, not the everyday one.

---

## 7. ComfyUI: does it start?

**Yes.** `D:\Jarvis\ImageGen\ComfyUI` starts on the venv the sibling made
(`D:\Jarvis\ImageGen\venv`), serves its HTTP API on `127.0.0.1:8188`, loads both
models' kits and draws. What the sibling's install was missing, and what was
finished:

| Was missing | Now |
|---|---|
| PyTorch (the wheels folder held a 0-byte `torch` wheel) | **torch 2.7.1+cu126 + torchvision 0.22.1+cu126**, installed **from the downloaded CUDA wheel, never from PyPI** - PyPI's Windows `torch` is the CPU-only build (206 MB) and would have given a picture-maker that cannot see a graphics card |
| ComfyUI's whole `requirements.txt` | installed (transformers 5.19.0, safetensors, comfy-kitchen 0.2.37, scipy, av, SQLAlchemy, spacy-free set, the frontend package, …) |
| The `leejet/ComfyUI-GGUF` fork | cloned into `custom_nodes` - it does contain `qwen_image21` |
| Its own `gguf` package | **gguf 0.19.0** - without it the fork failed to import and every option-C graph was refused with `Node 'UnetLoaderGGUF' not found` |
| A way for ComfyUI to see your models where they live | `extra_model_paths.yaml` pointing at `D:\Jarvis Models\AI-Models` - **nothing was copied**; no second 12.9 GB copy exists |

**One deliberate gap, said plainly:** `comfyui-workflow-templates==0.11.78` was
**left out** of the install. It pulls **481 MB** of preview pictures for the web
UI's template browser (media-api/video/image/other/assets-01/assets-02), none of
which a draw uses, and the link gives 0.1-2 MB/s. ComfyUI still starts and still
serves the normal web page, but it prints a loud red error about that one
package on every start. To close it when the link is free:

```powershell
D:\Jarvis\ImageGen\venv\Scripts\python.exe -m pip install comfyui-workflow-templates==0.11.78
```

### The one thing that would have poisoned every number

**ComfyUI's `main.py` line 107 overwrites `CUDA_VISIBLE_DEVICES`** with the
number given to `--cuda-device`:

```python
elif args.cuda_device is not None:
    os.environ['CUDA_VISIBLE_DEVICES'] = str(args.cuda_device)
```

So the sibling's `Start-Pictures.ps1`, which passes `--cuda-device 0` *and*
pins by UUID, has its UUID pin thrown away - and on this PC, without
`CUDA_DEVICE_ORDER`, **CUDA numbers the cards fastest-first, so index 0 is the
RTX 2080 SUPER, not nvidia-smi's device 0 (the RTX 2060)**. Measured three ways
before writing the fix:

| Setting | Which card torch really got |
|---|---|
| `CUDA_VISIBLE_DEVICES=0` | **RTX 2080 SUPER** (wrong card) |
| `CUDA_VISIBLE_DEVICES=<2060 uuid>` | RTX 2060 |
| `CUDA_VISIBLE_DEVICES=0` + `CUDA_DEVICE_ORDER=PCI_BUS_ID` | RTX 2060 |

The first attempt at option A really did draw on the **8 GB** card with 3.5 GB
offloaded to RAM, at 30-70 seconds per step, while its log said
`loaded partially; 5418.30 MB usable, 5237.23 MB loaded, 3537.73 MB offloaded`.
That number was thrown away rather than reported. The measurement script now
sets `CUDA_DEVICE_ORDER=PCI_BUS_ID`, passes the card's **nvidia-smi index**, and
then **reads ComfyUI's own log back** (`Device: cuda:0 NVIDIA GeForce RTX 2060`)
and refuses to measure if it is not the card the run is for.

Two smaller traps found the same way, both now closed in the script:

- **ComfyUI caches an identical seed.** With one fixed seed, runs 2 and 3
  answered out of its execution cache in **0.5 s** and the "median of three"
  became 0.5 s. Each run now uses its own seed (12345/12346/12347).
- **`[int](3/2)` is 2, not 1** (PowerShell rounds .5 to even), so the median of
  three runs landed on the *largest* value. A's median is **274.4 s**, not the
  316.3 the first pass printed. Fixed with a floor.
- **An orphaned ComfyUI held port 8188** from the first attempt, so the next
  run's `/system_stats` was answered by the *other* process on the *other* card.
  The script now refuses to measure when something else holds port 8188.

---

## 8. The table you asked for

| | **A** pictures 12 GB, chat steps aside | **B** pictures 12 GB, chat to 8 GB | **C** small pictures 8 GB, chat untouched |
|---|---|---|---|
| Model | Chroma1-HD int8 | Chroma1-HD int8 | Qwen-Image 2.1 Q4_K_M |
| Card the picture ran on | **RTX 2060 (12 GB)**, proved from ComfyUI's own log | **RTX 2060 (12 GB)** | **RTX 2080 SUPER (8 GB)** |
| **A picture is produced?** | **yes** | **yes** | **yes** |
| Where | `…\owner-pictures\jarvis-optionA_00002_…00004_.png` | `…jarvis-optionB_00001_…00003_.png` | `…jarvis-optionC_00001_…00003_.png` |
| **Seconds per picture (median of 3)** | **274.4 s** | **319.1 s** | **620.9 s** |
| All three runs | 316.3 / 274.1 / 274.4 | 363.5 / 278.7 / 319.1 | 620.9 / 637.7 / 577.0 |
| **Peak VRAM** | **10,531 MiB of 12,288** | **12,052 MiB of 12,288** | **7,387 MiB of 8,192** |
| What the chat does | off the card for **8.7 s** per picture | lives on the 8 GB card | everyday chat untouched |
| The chat's context | **196,608 tokens kept** | **8,192 tokens (4.2%)** | **196,608 tokens kept** |
| The other lane's cost | nothing else moved | the coding lane leaves the 8 GB card | the coding lane leaves the 8 GB card |

All the pictures are in **`D:\Jarvis\ImageGen\logs\owner-pictures\`** (copied out
of ComfyUI's `output` folder), and each run's raw rows are in
`D:\Jarvis\ImageGen\logs\image-options-pictures-*.csv`.

Recommended: **A**. B costs 96% of the long conversation for pictures that are
the same but 45 seconds slower at the median. C is 2.3x slower than A and needs
the coding lane off its card.

---

## 9. What could not be made to work, and the honest caveats

1. **`max_download_gb` stays 20** - confirmed, untouched.
2. **The owner's two lanes were already stopped when I started measuring**, and
   **I did not stop them.** At 22:08 both were up; by 22:24 both were gone. The
   live install's own configuration explains it: `jarvis_second_card._read_switches()`
   reports `master: False` and every feature off, so those lanes are the
   second-card feature lanes and the product's own reconcile stops them.
   `asleep()` is False. Later another agent restarted them, and at various
   points 11436 held `qwen3.5:9b` at **ctx 2048** with an expiry in **2319**.
   Whatever state I found, I unloaded only the one lane standing on the card a
   draw needed, **through that lane's own HTTP API**, and put it back at the
   same model and the same context, proved from `/api/ps`. The final state is
   the one the brief describes: **11435 `qwen3:8b` @16384 on the 2080 Super,
   11436 `qwen3.5:9b` @196608 on the 2060, zero spill on both.**
3. **The `CUDA_Host model buffer size` line does not exist for a picture run.**
   It is llama.cpp's line, and ComfyUI has no llama.cpp in it. The picture runs
   are reported instead with ComfyUI's own load accounting and the sampled
   `nvidia-smi` peak (section 4), and the line is reported where it does exist -
   for the chat loads (section 3).
4. **`comfyui-workflow-templates` was deliberately not installed** (481 MB of
   template previews). ComfyUI starts and draws; it prints a red error about
   that package. One command fixes it (section 7).
5. **B's peak (12,052 MiB) is higher than A's (10,531 MiB)** and I cannot fully
   explain it - the same model ran on the same card. It was the first run of the
   set in both cases, so it includes the text encoder load; the other two B runs
   landed at 10,563 and 10,531, in line with A. Written down rather than
   smoothed over.
6. **C's text encoder ran on the processor**, so C's 10.3 minutes per picture is
   mostly CPU, not the card. A faster C would need the text encoder somewhere
   else; on an 8 GB card there is nowhere else for it to go.
7. **Nothing here is switched on.** The three picture switches in the live
   install were not turned on and not touched; these are measurements, not a
   configuration change. The live install was not patched, not restarted, and no
   token was printed, logged or written anywhere.

---

## 10. How to reproduce any of it

```powershell
# from the worktree: .dsh-scratch/imggen-measure
pwsh -File scripts\measure-image-options.ps1 -Section chat
pwsh -File scripts\measure-image-options.ps1 -Section pictures -Option A
pwsh -File scripts\measure-image-options.ps1 -Section pictures -Option B -ResidentChatCtx 8192
pwsh -File scripts\measure-image-options.ps1 -Section pictures -Option C
```

Nothing was pushed, no pull request was opened, nothing was merged, and this
work lives on the branch `feat/imggen-measure`.
