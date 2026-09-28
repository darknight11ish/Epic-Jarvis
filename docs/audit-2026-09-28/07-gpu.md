# Audit 7 - how much graphics-card work the new features add (2026-09-28)

Tree: `scratchpad/integ` (branch `audit-integration`, HEAD deaca649). Every
number marked **estimate** is worked out from the code, not measured; there
is no NVIDIA card or Windows here. The one-line PowerShell at the end
measures it on the PC.

## The answer first

- **The AI model is still the only big user of the RTX 2080 Super.** The
  animal faces and the third-card work add little memory next to it. The
  faces add an estimated **10-60 MB** of card memory for the small faces
  (widget, HUD, floating face) and up to **~200-250 MB** only while the big
  face in the Faces window is shown at "Maximum" on a large, sharp screen.
  The Jarvis windows themselves (WebView2, the Edge engine inside the app)
  probably use **~150-400 MB** whatever face is worn. (All **estimates**.)
- **The third-graphics-card work costs the 2080 Super nothing.** Its Ollama
  copy is pinned to the third card only, with the Vulkan route switched off.
  It also only runs on a PC with three capable cards; the owner has one
  today.
- **Why a small amount still matters: the model is already at the edge.**
  `jarvis-primary` still asks for 16,384 tokens of context
  (`backend/jarvis-primary.Modelfile:119`). HARDWARE-PROFILES works out that
  this is already about 0.6 GB too much for an 8 GB card, which puts about 4
  of the model's 37 layers on the processor, unless a smaller setup was
  chosen in Settings. llama.cpp (the engine inside Ollama) sizes the model by
  the card's **free memory at the moment it loads**. So face memory taken
  **before** the model loads means fewer layers fit on the card. Face memory
  taken **after** eats into the 1 GB of spare room llama.cpp keeps.
- **The faces use the same card as the AI model.** They are drawn by the
  Edge engine on the card the screen is plugged into, which is the 2080
  Super.
- **Faces do not go fully idle while they are on screen.** A resting animal
  is drawn 30-60 times a second, all day, while the widget is open or the HUD
  or floating face is showing. When a window is hidden or minimised, the
  browser stops drawing (the Faces window also stops itself). **Needs a real
  try:** I could not confirm that the app tells the Edge engine a minimised
  window is hidden.
- **There is a watchdog**, and it is a good one. It asks the graphics card
  how long each face frame took, falls back to a flat drawing after 3 slow
  frames (or 1 very slow one), and tries the card again after 1 to 16
  minutes. But it only checks whether the *face* keeps up. It cannot see
  whether the face is slowing the *AI model*.

## Findings

### 7.1 A shader that fills the whole face asks for 4x anti-aliasing and a depth buffer it never uses (medium, checked in code, mascot branch)

- **What's wrong:** the shared WebGL canvas that draws every animal is
  created with `antialias:true, depth:true`
  (`jarvis-desktop/src/faces.html:547-551`). An animal is one triangle that
  covers the whole canvas, and the pass turns the depth test off
  (`faces.html:756`, `GPU.pass`). So the 4x multisample colour buffer and
  the depth buffer smooth nothing and are never read. They only cost memory.
- **How much (estimate):** Chromium usually gives an anti-aliased WebGL
  canvas 4 samples. That is about 4 x (4 bytes colour + 4 bytes depth) +
  about 12 bytes for the finished picture and its copies, so **about 40 bytes
  per traced pixel instead of about 12**. The trace size is capped at
  `desktop_max_px` 2400 (`face-pace.js:37`), and Maximum traces 2x2 samples
  per screen pixel (`faces.html:5591`). A 1200-pixel face at Maximum is a
  2400 x 2400 trace:
  - with the extra buffers, **~230 MB**;
  - with them removed, **~70 MB**.

  The widget's 120-pixel face (`widget.css:410`) is a few MB either way.
- **Why it matters:** this is the one part of the faces' memory that can
  reach hundreds of MB, and it comes out of the room the model needs.
- **Fix (code change, small):** the mesh faces (Nucleus and the others) do
  use depth, so give the animals their own context. Or create the shared one
  without multisampling and add a depth *renderbuffer* only for `mesh()`. The
  smallest safe version is to keep one context but set `antialias:false`
  (the animals smooth their own outline in the shader, `common_tail.sksl:70`
  onward), then check the mesh faces for jagged edges in `tests/faces.mjs`.
  Owner's call only if the mesh faces look worse.

### 7.2 Auto quality climbs the always-on faces to "Maximum" (4x the pixels) whenever the card is idle (low, checked in code)

- **What's wrong:** display mode (the widget, the HUD and the floating face)
  calls the Auto ladder with the top set to `"max"`
  (`faces.html:6500`, `FacePace.decide(..., "max", ...)`; the Faces window likewise at `:5370`). It climbs there
  whenever a face frame takes under a quarter of its time
  (`face-pace.js:41`). On a 2080 Super that is nearly always true, so the
  small faces will usually trace at 2x2 samples.
- **Why it matters:** the card cost is small in absolute terms. An
  **estimate** for a 120-240 px face: under 1 ms of card time a frame. But it
  runs all day, and the frame cost the ladder judges is the face's own. It
  never sees that Ollama is sharing the card. The owner asked for "sharp
  animals on capable hardware", so this is as designed, and I only flag it.
- **Fix (owner's call):** cap display mode at `"high"` while an answer is
  being written (the `thinking`/`speaking` state), or leave it.

### 7.3 While Jarvis talks, the animal is drawn at the screen's full rate, at the same moment the model is still writing (low, checked in code; the effect needs a real try)

- `FacePace.restFps` returns 0 for any state other than `idle`/`approval`,
  which means "every frame" (`face-pace.js:84-96`). The desktop starts
  speaking at the first comma of the answer (`main.js:3400-3411`), so for
  most of an answer both of these happen together:
  - Ollama is writing the rest of the answer on the card;
  - the face is drawn at 60-144 frames a second on the same card.
- **Estimate:** a face frame is short (well under a millisecond at widget
  size), so words per second should drop by a few percent at most. Only the
  measurement below can say.
- **How to see it:** Brain -> Model already shows words per second and "N%
  of the conversation reused" (milestone 7). Ask the same question with the
  face hidden and then showing, and compare.

### 7.4 Idling: good in the Faces window, and relies on the browser elsewhere (low, needs a real try)

- The Faces window cancels its drawing loop when hidden
  (`faces.html:5776-5778`).
- The widget unloads the face frame entirely when it is collapsed, when a
  card is showing, or when "Your widget" replaces the face
  (`widget.js:516-530`). The HUD unloads its face while the Galaxy view is up
  (`jarvis_hud.html:1064`).
- Display mode's own loop (`faces.html:6541-6594`) has **no** visibility
  check. It relies on the browser stopping frames for a hidden page. That is
  standard browser behaviour, but it depends on Tauri/WebView2 marking a
  minimised or hidden window as hidden. I found no code in `src-tauri` that
  does this itself (no `SetIsVisible`/`TrySuspend`). **Needs a real try:**
  step 1 of the measurement below, run with the HUD minimised, answers it.
- While shown and resting, an animal is drawn 30-60 times a second
  (`face-pace.js:84-96`: "headroom" 60, else 30). Standby is 15 and "banked"
  is 2. This keeps the card out of its lowest power state. **Estimate:** a
  few to ~20 W more than a blank desktop. The `power_W` column below measures
  it.

### 7.5 A second "warm-up" can load a different model onto the card (medium, checked in code, continuation branch)

Reported in full under audit 3 (finding 3.2). Pressing Jarvis Live loads
`JARVIS_MODEL` or else `jarvis-primary` (`backend/jarvis_agent.py:4748`). It
does not ask which model chat actually uses. If the owner switched models
from the phone, pressing Live can load a **second** 8B onto an 8 GB card that
has no room for two. It also sets a 30-minute unload timer
(`keep_alive: "30m"`, `:4752`), against MODEL-TOPOLOGY's advice to keep the
model loaded forever.

### 7.6 The third-card work: no cost on the 2080 Super (checked in code, continuation branch)

- The third lane starts its own Ollama with these settings
  (`jarvis_second_card.py` docstring, lines 110-160, and around 300):
  - `CUDA_VISIBLE_DEVICES=<that card's id>` and `OLLAMA_VULKAN=0`;
  - `OLLAMA_HOST=127.0.0.1:11436`, loopback only, on its own port;
  - `OLLAMA_MAX_LOADED_MODELS=1` and `NUM_PARALLEL=1`.
- CUDA creates its working area only on the cards it is allowed to see, so
  this process uses no 2080 Super memory.
- Its screen section is hidden unless a capable third card is detected
  (`settings.js:1948`).
- The "one bigger model on both cards" mode is different. It deliberately
  uses both cards, so it is not free on the 2080. It is off by default and
  asks with a card first (unchanged from before today).

### 7.7 The phone (for completeness)

- The phone draws animals with Android's own shader engine (AGSL/Skia,
  `CritterFaces.kt`). It traces at 0.4, 0.5, 0.75 or 1.0 of the screen's
  resolution for Lower, Balanced, High and Maximum (`FaceBudget.kt:80-91`).
- Auto may climb to Maximum, but not in Battery saver and not while the phone
  is warm.
- It does not touch the PC's card. `docs/CRITTERS.md` says plainly that
  phone cost is "not yet measured on a real phone".

## What each face costs, by the numbers in the code (estimates)

| Surface | Size on screen | Traced at High / Maximum (1.5x display scale) | Card memory for the face (current settings) |
|---|---|---|---|
| Widget | 120 px (`widget.css:410`) | 180 / 360 px | ~1-5 MB |
| HUD | 232 px (`jarvis_hud.html:204`) | 348 / 696 px | ~5-20 MB |
| Floating face | window-sized | depends | ~5-30 MB |
| Faces window, big face | up to the window | up to 2400 px (cap) | up to ~230 MB (~70 MB after fix 7.1) |
| WebView2 itself, all Jarvis windows | - | - | ~150-400 MB (general Chromium figure, **unverified** for this app) |

Work per pixel: an animal's ray takes up to 36 steps (panda, monkey) or 48
(owl, otter) to find the surface (`MARCH_STEPS`, `critters/*.sksl`). The
shading then adds a 4-sample normal and a 10-step soft shadow
(`common_tail.sksl:20-23`). The shadow is skipped under 200 px
(`face-pace.js:45`).

## Measure it on the PC: one line

Paste into PowerShell (works in the 5.1 that comes with Windows). It asks you
to press Enter three times:

1. Hide the face (collapse the widget, close the HUD and floating face).
2. Show the face you use.
3. Keep the face showing and ask Jarvis a question at the same moment.

Each step records about one minute, once a second, for every NVIDIA card:
how busy it is, its memory, its power, and how much card memory the Jarvis
windows (`msedgewebview2`) and Ollama each hold. At the end of each step it
also copies Ollama's latest "offloaded N/M layers to GPU" line, which says
whether the whole model is on the card.

```powershell
$d = "$env:USERPROFILE\jarvis-gpu-test"; New-Item -ItemType Directory -Force -Path $d | Out-Null; $f = Join-Path $d ("gpu-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".csv"); "phase,time,card,gpu_busy_pct,card_mem_used_MiB,card_mem_total_MiB,power_W,jarvis_windows_MiB,ollama_MiB" | Set-Content -Path $f -Encoding UTF8; foreach ($p in @("1-face-hidden", "2-face-showing", "3-face-showing-while-Jarvis-answers")) { Read-Host "Step $p - get it ready, then press Enter (records for about 1 minute)" | Out-Null; for ($i = 0; $i -lt 30; $i++) { $w = 0; $o = 0; $wp = @(Get-Process -Name msedgewebview2 -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }); $op = @(Get-Process -Name ollama*, llama* -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }); try { foreach ($s in (Get-Counter -Counter "\GPU Process Memory(*)\Dedicated Usage" -ErrorAction Stop).CounterSamples) { if ($s.InstanceName -match "pid_(\d+)_") { $id = [int]$Matches[1]; if ($wp -contains $id) { $w += $s.CookedValue } elseif ($op -contains $id) { $o += $s.CookedValue } } } } catch { $w = $null; $o = $null }; $t = Get-Date -Format "HH:mm:ss"; foreach ($line in @(nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits)) { "$p,$t," + ($line -replace "\s", "") + "," + $(if ($null -eq $w) { "n/a" } else { [math]::Round($w / 1MB) }) + "," + $(if ($null -eq $o) { "n/a" } else { [math]::Round($o / 1MB) }) | Add-Content -Path $f -Encoding UTF8 }; Start-Sleep -Seconds 1 }; $log = "$env:LOCALAPPDATA\Ollama\server.log"; if (Test-Path $log) { $last = Select-String -Path $log -Pattern "offloaded \d+/\d+ layers to GPU" | Select-Object -Last 1; if ($last) { "$p,note,Ollama says: " + ($last.Line -replace ",", " ") | Add-Content -Path $f -Encoding UTF8 } } }; Write-Host "Done. The results are in $f"; explorer $d
```

**Where the file lands:** `C:\Users\<you>\jarvis-gpu-test\gpu-<date>-<time>.csv`.
The folder opens by itself at the end. Send that `.csv` file back.

How to read it:

- Compare step 2 with step 1 in `card_mem_used_MiB` and `jarvis_windows_MiB`.
  The difference is what the face costs in card memory.
- Compare `gpu_busy_pct` and `power_W` the same way.
- In step 3, look at the words-per-second line in Brain -> Model for that
  answer.
- If the `note` line says fewer layers than the total (for example 33/37),
  part of the model is on the processor.

How I tested the command:

- It parses in PowerShell 7 here with 0 errors, and it is one line.
- It ran end to end with stand-ins for `nvidia-smi`, `Get-Counter`,
  `Get-Process` and `Read-Host`. It wrote 30 rows per card per step, with
  `n/a` when the counters were unavailable, plus the three `note` lines.
- I checked it for things that only work in PowerShell 7: no `??`, no
  ternary `? :`, no `&&`.

What it cannot show:

- It was **not run against a real card**.
- On a Windows installed in another language, the counter name
  `\GPU Process Memory(*)\Dedicated Usage` is translated. The two
  per-process columns then read `n/a`, and the `nvidia-smi` columns still
  work.
- The per-process columns add up memory on **all** cards, not just the 2080.
