# The first real picture *through Jarvis*: preflight, runbook, and what was wrong

Written 2026-10-11, against a fresh checkout of `origin/main` = **5f382aff**,
with the graph defect fixed on this branch. Verified against the owner's PC
itself: paths, sizes, safetensors headers, ComfyUI's own source, ports, and the
live backend's routes. Nothing was started, loaded, unloaded or drawn.

## 0. The correction to the record, first

**"No picture has ever been drawn" is not true as stated.** Ten 1024x1024 PNGs
exist in `D:\Jarvis\ImageGen\ComfyUI\output` (`jarvis-optionA_00001_..00004_`,
`jarvis-optionB_00001_..00003_`, `jarvis-optionC_00001_..00003_`, 988 KB-1.98 MB,
2026-10-11 01:11-02:44, copies in `logs\owner-pictures\`). They are real
pictures, drawn on this machine - by the measurement script.
**None went through Jarvis and none has a sidecar**, and
`C:\Users\pcadmin\Pictures\Jarvis` does not exist. So the honest sentence is
**"no picture has ever been drawn *through Jarvis*"** - which is what this
runbook is for. Do not delete those files.

Two other things are written down here and NOT fixed, because neither is in this
repository - both are the owner's own setup under `D:\Jarvis\ImageGen\`:

* **The two workflow JSONs name files that are not on this PC.**
  `D:\Jarvis\ImageGen\workflows\chroma1-hd-t2i.json` asks ComfyUI for
  `Chroma1-HD-fp8_scaled_rev2.safetensors` and
  `t5xxl_flan_latest_float8_e4m3fn_scaled_stochastic.safetensors`;
  `qwen-image-2.1-t2i.json` (inside its `Text to Image (Qwen Image 2.1)`
  subgraph) asks for `qwen_image_2.1_int8_convrot.safetensors`,
  `qwen3vl_8b_int8_convrot.safetensors` and
  `qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot.safetensors`. The disk has
  different quantisations and no prompt-enhancer file at all. **Cost:** anyone
  who loads one of these in the ComfyUI window gets "value not in list" and no
  picture. They are the publishers' templates, not this PC's files;
  `scripts/measure-image-options.ps1` (in the repository) builds its own graph
  for exactly that reason, and so does `backend/jarvis_pictures.py` now.
* **`D:\Jarvis\ImageGen\Start-Pictures.ps1`'s switch-writing step is inert.**
  Step 5 of that script runs only `if (Test-Path (Join-Path $root
  'backend\jarvis_picture_card.py'))` - and `D:\Jarvis\ImageGen\backend\` does
  not exist - so it prints "(the backend's switch file is not here ...)" and
  starts ComfyUI anyway. **Cost:** running the script does *not* turn the
  picture switch on or record which of the three ways (A/B/C) was chosen; the
  switch has to be set separately (step 3 below), and if you skip that you get
  a running ComfyUI and a refusal from the route. The script also never frees
  the card a lane is holding - that is only in
  `scripts/measure-image-options.ps1` (step 1a below).

## 1. The chain on disk (all byte-exact, re-verified)

| File | Bytes | Path |
|---|---|---|
| `Chroma1-HD-int8-convrot-simple.safetensors` | 9,201,358,564 | `D:\Jarvis Models\AI-Models` |
| `qwen-image-2.1-UC-Q4_K_M.gguf` | 4,604,558,112 | `D:\Jarvis Models\AI-Models` |
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | 5,157,348,688 | `...\ComfyUI\models\text_encoders` |
| `qwen3vl_8b_int8_convrot.safetensors` | 9,350,798,360 | `...\ComfyUI\models\text_encoders` |
| `ae.safetensors` | 335,304,388 | `...\ComfyUI\models\vae` |
| `qwen_image_2.1_vae_bf16.safetensors` | 675,509,688 | `...\ComfyUI\models\vae` |

ComfyUI is installed (`main.py`, venv), its GGUF node is present
(`custom_nodes\ComfyUI-GGUF`), `--cuda-device` exists (`comfy/cli_args.py:77`),
and `extra_model_paths.yaml` points `diffusion_models`/`unet`/`checkpoints` at
`D:/Jarvis Models/AI-Models`, which exists. **The three "missing" items are all
still true**: ComfyUI is not running, neither `pictures.json` nor
`picture-card.json` exists anywhere under `C:\Users\pcadmin` (so the switch has
never been on), and stable-diffusion.cpp is not installed (no `sd-server.exe`).

## 2. The switch, and the graph the route posts

* `enabled` in `pictures.json`, **default false** (`backend/jarvis_pictures.py`
  `DEFAULTS`); `runtime` also starts `null`.
* Turn it on: `POST /api/pictures/settings` with
  `{"action":"runtime","runtime":"comfyui"}` then `{"action":"enabled","on":true}`
  - **no approval card** (module docstring), **PC-only** (the route refuses
  without `pc_only=True`). The desktop's Settings -> Pictures does the same.
* Draw: `POST /api/pictures` (`{"prompt": "..."}`, optional
  `"settings": {"model","steps","width","height","guidance","negative"}` and
  `"seed"`), and `GET /api/pictures/file?id=` for one picture.
* **Which graph:** decided by the MODEL FILE, from
  `jarvis_picture_card.IMAGE_MODELS`. With no model named - which is what both
  apps send - the recommended way's model is used (Chroma1-HD), and the sidecar
  records it. A model this PC has no record of is refused in one plain sentence
  before the drawing program is contacted.
  * Chroma1-HD: `UNETLoader` + `CLIPLoader(type="chroma")` + `VAELoader`, the
    publisher's own graph (T5TokenizerOptions, ModelSamplingAuraFlow shift 1.0,
    CFGGuider 3.8, BetaSamplingScheduler 26 steps, 1152x1152).
  * Qwen-Image 2.1 GGUF: `UnetLoaderGGUF` + `CLIPLoader(type="qwen_image")` +
    `VAELoader`, Comfy-Org's graph (TextEncodeQwenImage21 with its own latent,
    KSampler 25 steps, cfg 1.0, 1024x1024).
  Both are the recipes `scripts/measure-image-options.ps1:487-528` drew real
  pictures with, node for node.

## 3. The runbook - one picture, in order

Only steps 1 and 4 touch a card;

**Step 0 (no GPU).** `pwsh -File D:\Jarvis\ImageGen\Start-Pictures.ps1 -Option A -WhatIfOnly`
-> both cards ranked, `weights fit`, `-WhatIfOnly: nothing was started.`

**Step 1 (GPU taken here). Free the 12 GB card, then start ComfyUI.**
```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:11436/api/generate `
  -ContentType application/json `
  -Body '{"model":"qwen3.5:9b","prompt":"","keep_alive":0}'
pwsh -File D:\Jarvis\ImageGen\Start-Pictures.ps1 -Option A
```
Expected: `main.py --port 8188 --listen 127.0.0.1 --cuda-device 0`,
`CUDA_VISIBLE_DEVICES = GPU-...`, `ComfyUI will answer on http://127.0.0.1:8188`;
`logs\comfy-A.log` shows `Device: cuda:0 NVIDIA GeForce RTX 2060 ...`.
The card is held from here until the window is closed (~1-2 min start-up, then
idle).

**Step 2 (no GPU).** `Invoke-RestMethod http://127.0.0.1:8188/system_stats`
-> JSON with the card's name and `vram_total`.

**Step 3 (no GPU). Turn the switch on.**
```powershell
$t = (py -3 jarvis_token_store.py show).Trim()      # from the live backend folder
$h = @{ "X-Jarvis-Token" = $t; "X-Jarvis-Client" = "hud" }
$b = @{ ContentType = "application/json"; Headers = $h }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:4719/api/pictures/settings @b -Body '{"action":"runtime","runtime":"comfyui"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:4719/api/pictures/settings @b -Body '{"action":"enabled","on":true}'
```
Expected: `ok:true, changed:"runtime"`, then `ok:true, enabled:true,
changed:"enabled"`. **Cannot be done until the backend carries
`jarvis_pictures.py`** (`GET /api/pictures` is 404 on 4719 today - the
deployment is the Lead's, not this branch's).

**Step 4 (GPU; 274.4 s measured median - allow 10 minutes). Draw one.**
```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:4719/api/pictures @b -Body (@{
  prompt = "a red panda sitting on a mossy rock, soft morning light"
} | ConvertTo-Json)
```
Expected: `ok:true`, `name` like `2026-10-11-140509-a-red-panda-sitting-on-a.png`,
`path`, `seconds`, `bytes`, `model` = `Chroma1-HD-int8-convrot-simple.safetensors`,
and `words: "Drawn in N seconds and saved as ..."`. **With this branch's graph
fix and the backend deployment, this step is expected to succeed.**

**Step 5 (no GPU). Prove it.** See section 5.

## 4. What will contend with the cards

| lane | model | ctx | size = vram | card now |
|---|---|---|---|---|
| 11436 | `qwen3.5:9b` | 196,608 | 9,847,051,386 B | RTX 2060 12 GB - 10,387/12,288 MiB used, **1,901 MiB free** |
| 11435 | `qwen3:8b` | 16,384 | 6,270,348,164 B | RTX 2080 SUPER 8 GB - 7,397/8,192 MiB used, **795 MiB free** |

Chroma1-HD alone is 8.57 GiB, so **A/B need lane 11436 unloaded** (measured chat
reload 8.5 s; A's whole price 8.7 s of chat-away per picture, all 196,608 tokens
kept). The measured option C run peaked 7,306/8,192 MiB and did unload lane
11435, putting it back exactly: **10.3 minutes per picture, coding lane off the
8 GB card, long chat untouched**. Nothing on the feature path frees a lane for
you - the draw route has no lane logic; only the measurement script does.

## 5. What proves the picture is Jarvis's own work

A new PNG in `%USERPROFILE%\Pictures\Jarvis` (which does not exist yet) named
`YYYY-MM-DD-HHMMSS-<slug>.png`, **with its `.json` sidecar beside it**
(`"jarvis_pictures": 1`, prompt, seed, runtime, model, settings, `made_at`,
`seconds`), the `POST` reply's `path` matching it, ComfyUI's log naming the
loaders and `Prompt executed`, and
`nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid` showing
the python process on the pinned card.

**One thing that looks like success but is not:** a picture in
`D:\Jarvis\ImageGen\ComfyUI\output\` - that is ComfyUI's own `SaveImage`, and
ten are already there from the measurement runs; none went through Jarvis and
none has a sidecar. (Near-miss two: a reply whose `"model"` is `""`.)
