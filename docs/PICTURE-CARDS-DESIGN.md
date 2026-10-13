# Which card draws the pictures - design

The owner's decision of 2026-10-10, in his own words: three ways of running an
image generator alongside Jarvis, to be tried and measured one at a time.

## The problem in one paragraph

Both cards are Turing (compute 7.5). The everyday chat runs on the 12 GB
RTX 2060 and fills most of it. A picture-maker wants that same card, because
the only big picture model on this PC needs 8.6 GB of weights and the other
card has only 8 GB. Two things cannot sit on one card, so something has to
give - and there are exactly three sensible ways to give.

## The three ways

| | What it does | What it costs |
|---|---|---|
| **A** | Picture-maker on the 12 GB card; the everyday chat is unloaded before a draw and warmed back after | A few seconds of chat reload per picture; the long conversation is kept |
| **B** | Picture-maker on the 12 GB card; the everyday chat moves to the 8 GB card and stays resident | The conversation shrinks to whatever the 8 GB card holds with no spill |
| **C** | The small picture model on the 8 GB card; the chat is untouched | The pictures come from the smaller model |

Every one of them is **off** until the owner turns it on. That is not caution
for its own sake: `CLAUDE.md` says a feature that uses the second card keeps
its own switch, off until *that feature* is measured, and this project has
already produced one 7x-wrong number by running two models on these cards at
once.

## What the module owns, and what it deliberately does not

- **Owns**: the choice of card, the pinning, the chat's unload/move/reload, and
  the measurement of "how long a conversation fits with no spill".
- **Does not own**: drawing a picture, saving it, listing it, or any route
  under `/api/pictures`. That is `jarvis_pictures.py` (JARVIS-API §123). Two
  modules owning one prefix is how a route quietly stops working.
- **Does not own**: the settings *page*. A row in `settings.html` is the
  desktop app's surface; the honest way to try A, B or C today is
  `Start-Pictures.ps1 -Option A|B|C`, which writes the same switch the route
  writes.

## Pinning, and the mistake already made here

`CUDA_VISIBLE_DEVICES` alone does **not** pin an Ollama model: it falls back
to its Vulkan engine and lands on the other card. That mistake has already
produced wrong measurements in this project. So:

- Cards are found by `nvidia-smi` and **ranked by their own reported memory** -
  "big" is the 12 GB card whatever index it happens to have today.
- Any program this module starts is given the card's **UUID**, never a number.
- Where ComfyUI is started, the card is pinned **twice**: `CUDA_VISIBLE_DEVICES`
  to the UUID, and ComfyUI's own `--cuda-device 0` (its argument is the index
  among the *visible* devices, so with one exposed it is 0).
- Where a measurement server is started (port 11440), it also gets
  `OLLAMA_VULKAN=0`, and it is stopped when the measurement ends. Jarvis's own
  servers are never stopped, reconfigured or pinned by this work.

## What is measured, and what each number means

- **Weights against real memory** - the file size against `memory.total`, which
  answers "does it fit at all" and nothing more. It is deliberately not called
  a speed or a fit-for-a-draw.
- **Seconds per picture** - three runs at one fixed resolution and one fixed
  seed, and the *median* is reported with all three runs beside it.
- **Peak VRAM** - sampled from `nvidia-smi` during the run, on the card the
  process was actually pinned to, checked against `nvidia-smi
  --query-compute-apps` so the answer is the card, not the hope.
- **The chat's behaviour** - A: unloaded and reloaded, with the seconds for
  each; B: the largest `num_ctx` where `/api/ps` shows `size_vram == size`
  (zero spill), which is the price of B in one number; C: that the chat lane
  was not touched at all.
- **One GPU-heavy thing at a time** - every GPU section refuses to run while a
  model it did not expect is resident on either card, and says which one.

## Known limits, written down rather than hidden

- Neither picture model can run alone: each needs a text encoder and a VAE that
  are not on this PC yet. Both are named, with sizes, in
  `.dsh-scratch/android-verify/image-gen/THREE-WAYS-COMPARISON.md`.
- `qwen-image-2.1`'s GGUF is a stable-diffusion.cpp export whose architecture
  (`qwen_image21`) today's `ComfyUI-GGUF` does not recognise; the publisher
  names the `leejet` fork.
- The speed numbers are not measured yet. The comparison says so plainly and
  gives the two commands that produce them.
