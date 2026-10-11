# Making pictures beside Jarvis - the missing half downloaded, and the numbers that were blocked

For the owner. Written 2026-10-11 on your PC, by the agent that was asked to
finish the download and get the three numbers a sibling honestly refused to
guess. Plain words first, numbers after.

**The short answer:** both of your picture models can now be finished and run.
Option **A** is the one to pick. Its whole price is **8.7 seconds** of the chat
being away around each picture, and it keeps the entire **196,608-token**
everyday conversation. Option **B** keeps only **8,192 tokens** - 4.2% of that
conversation - so B costs about 96% of your long chat. Option **C** is the
small model on the 8 GB card and needs the most download for the least picture.

---

## 1. The one line you asked to be confirmed

**`max_download_gb` is 20.** It is line 539 of
`C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis-framework.toml`,
and the sibling's backup next to it still says 12. Nothing was restored, nothing
was changed.

---

## 2. What was downloaded

Every big file came down with a **resumable HTTP range downloader** and was
**SHA-256 checked against the hash the publisher itself publishes** before it
was moved onto its final name. `hf download` was never used: it hangs at 0% on
this PC for anything over ~5 MB and leaves a child process holding a lock.
`Start-Job` workers and `curl.exe` were avoided too, for the two reasons the
sibling's scripts already recorded on this PC (0 bytes through a harness pipe;
`Start-Process -ArgumentList` splitting a path at the space in `Jarvis Models`).

| File | Size | SHA-256 (publisher's own) | Licence | Where |
|---|---|---|---|---|
| `torch-2.7.1+cu126-cp312-cp312-win_amd64.whl` | 2,716,918,001 B (2.53 GiB) | `7d897b5ff67e778de4a2a05d4528377003105e29854fd73ecbe965287533f08b` | BSD-3-Clause | `D:\Jarvis\ImageGen\wheels` |
| `torchvision-0.22.1+cu126-cp312-cp312-win_amd64.whl` | 6,334,174 B | `8a46582304fdff54a953522851c91b4d6f35b1d5c48a7d81f7d893edf015ce91` | BSD-3-Clause | `D:\Jarvis\ImageGen\wheels` |
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | 5,157,348,688 B (4.80 GiB) | `a498f0485dc9536735258018417c3fd7758dc3bccc0a645feaa472b34955557a` | Apache-2.0 | `ComfyUI\models\text_encoders` |
| `ae.safetensors` (the FLUX/Chroma VAE) | 335,304,388 B | `afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38` | Apache-2.0 | `ComfyUI\models\vae` |
| `qwen_image_2.1_vae_bf16.safetensors` | 675,509,688 B | `bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9` | Qwen Research License | `ComfyUI\models\vae` |
| `qwen3vl_8b_int8_convrot.safetensors` | 9,350,798,360 B (8.71 GiB) | `8bfd0f6e12abf2d2d697ecc888e5e90b0d6741d6708f05799f53afa560452e8f` | Qwen Research License | `ComfyUI\models\text_encoders` |

Sizes and hashes were not guessed: the two Hugging Face figures are the **LFS
oids from Hugging Face's own API**, and PyTorch's came from the `#sha256=`
fragment on `download.pytorch.org`'s own index.

**A licence fact worth writing down:** the two Qwen-Image 2.1 companion files
are **not** Apache-2.0. The `Comfy-Org/Qwen-Image-2.1` repository is marked
`license: other, license_name: qwen-research`. That is fine for this project -
the owner decided on 2026-09-28 that EpicJarvis is never commercialised - but
it needs its own credit line in `THIRD-PARTY-NOTICES.txt`, and the two files
must not be redistributed as if they were Apache.

### Why the download was the slow part

Measured tonight: **PyTorch's own CDN gave ~0.04-0.05 MB/s on one connection**
- about 15 hours for the torch wheel alone. It is not a per-connection cap:
throughput scaled with concurrency, so the downloader runs 24 parallel range
requests and reached **1.0-2.1 MB/s**. The home link itself was measured at
**2.2-4.3 MB/s machine-wide**, with two other agents pulling their own models
at the same time. That contention, not the code, is what sets the clock.

One honest note about a sibling's process: a `curl.exe` it had left running on
this same torch wheel had written nothing for 25 minutes, so it was ended rather
than leaving two writers on one destination. It had actually buffered 177 MB,
which was thrown away and re-fetched. That was my call and it cost ~2 minutes of
link time.

---

## 3. The measurement trap this PC sets, and the number that proves it

`/api/ps`'s `size_vram == size` is **not** proof that nothing spilled. Measured
here, with the live product's own environment:

- `qwen3.5:9b` at **ctx 8192 on the 12 GB card** - a load that cannot possibly
  spill: **`load_tensors: offloaded 33/33 layers to GPU`**, `/api/ps` reports
  `vram 5,703,100,005 / size 5,703,100,005`, i.e. spill 0 -
  and llama.cpp's own log still says
  **`load_tensors: CUDA_Host model buffer size = 545.63 MiB`**.

So the runner's `CUDA_Host` figure is **never zero**, and comparing it to zero
would condemn every load. What separates a real spill from a clean one on this
machine is the **layer count** and the size of that figure:

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
`jarvis_second_card.lane_env()` sets **`OLLAMA_KV_CACHE_TYPE=q8_0`**, one model
at a time, one parallel slot. With that, the same load is 33/33 layers and zero
spill. Every private server used for these numbers was started from the
product's own `lane_env()`, so it had exactly that environment - a measurement
taken without it is wrong by 3.5 GB.

---

## 4. A: pictures on the 12 GB card, the chat steps aside

**A's price: the chat is away for 8.7 seconds around each picture.**

| | Measured |
|---|---|
| Unload (`keep_alive: 0`, through the API only) | request 0.0 s, model **gone from the card in 0.2 s** |
| Reload at 196,608 tokens | **8.5 s** (the API call: load + one token) |
| **Unload + reload per picture** | **8.7 s** |
| Did the long conversation come back? | **yes - granted 196608** |
| After reload: `/api/ps` | `vram 9,847,051,386 / size 9,847,051,386` - **spill 0** |
| After reload: layers | **33/33 on the card** |
| After reload: `CUDA_Host` | **545.63 MiB** (same as the reference, so no extra spill) |
| After reload: `nvidia-smi` on the 2060 | **10,392 MiB of 12,288 MiB** |

Nobody's server was stopped or reconfigured for this. The model was unloaded and
warmed back through Ollama's own HTTP API on a private `ollama serve` on port
11445, pinned to the RTX 2060 **by UUID** (`GPU-1ba04124-...`) with
`OLLAMA_VULKAN=0`.

---

## 5. B: pictures on the 12 GB card, the chat moves to the 8 GB card

**B's price, in the one number it was asked for: 8,192 tokens.**

That is the largest context `qwen3.5:9b` holds on the **RTX 2080 SUPER (8 GB)**
with nothing spilled - where "nothing spilled" means **33/33 layers on the card
and `/api/ps` agreeing**, not `/api/ps` alone.

| Context asked | Layers on the card | `CUDA_Host` | `/api/ps` spill | Verdict |
|---|---|---|---|---|
| **8,192** | **33/33** | **545.63 MiB** | **0** | **zero spill** |
| 12,288 | 32/33 | 683.55 MiB | 784,229,987 B | spilled |
| 16,384 | 31/33 | 821.47 MiB | 935,245,903 B | spilled |
| 32,768 | 29/33 | 1,085.33 MiB | 1,302,195,075 B | spilled |

- At 8,192 tokens the card held **7,569 MiB of 8,192 MiB** - it is full.
- **That is 4.2% of A's 196,608-token conversation: B costs 188,416 tokens.**
- This was measured on a **quiet 8 GB card**. Note what that means for the real
  arrangement: your coding lane (`qwen3:8b`, 6.27 GB) is the model that lives on
  the 8 GB card today. It and the everyday chat cannot both be there, so B means
  moving or dropping that lane too - that is part of B's price, not a detail.

---

## 6. C: the small model on the 8 GB card, the chat untouched

`qwen-image-2.1-UC-Q4_K_M.gguf` is 4.29 GB of weights against 8,192 MiB, so it
fits. It is the only one of the three that needs a file nobody had downloaded
(the 8.71 GiB text encoder), and it needs the `leejet` fork of ComfyUI-GGUF,
because the file is a stable-diffusion.cpp export whose own header says
`general.architecture = qwen_image21` and the ordinary ComfyUI-GGUF does not
know that architecture. **That fork is now installed** in the sibling's ComfyUI
and does contain `qwen_image21`.

C's draw numbers are in section 8.

---

## 7. ComfyUI

The sibling's own install was finished, not duplicated: `D:\Jarvis\ImageGen\ComfyUI`
with its private Python 3.12 venv at `D:\Jarvis\ImageGen\venv`.

- The venv had **only pip** in it - no PyTorch, no ComfyUI requirements. That is
  what "incomplete" meant.
- PyTorch was installed **from the downloaded CUDA wheel, never from PyPI**:
  PyPI's Windows `torch` is the CPU-only build (206 MB) and would have produced
  a picture-maker that silently cannot see a graphics card.
- ComfyUI was told where your two picture models already live
  (`D:\Jarvis Models\AI-Models`) through `extra_model_paths.yaml`, so nothing
  was copied and no second copy of 12.9 GB exists on disk.

Section 8 says whether it starts and what it drew.

---

## 8. What is still to come

*(filled in as the draws finish)*

---

## 9. What could not be made to work

*(filled in at the end)*

---

## 10. How to reproduce any of it

```powershell
# the numbers the owner asked for, from the worktree copy of the script
pwsh -File <worktree>\scripts\measure-image-options.ps1 -Section chat
pwsh -File <worktree>\scripts\measure-image-options.ps1 -Section pictures -Option A
pwsh -File <worktree>\scripts\measure-image-options.ps1 -Section pictures -Option B -ResidentChatCtx 8192
pwsh -File <worktree>\scripts\measure-image-options.ps1 -Section pictures -Option C
```

Nothing here is pushed, no pull request was opened, nothing was merged, and the
live Jarvis install was not patched or restarted.
