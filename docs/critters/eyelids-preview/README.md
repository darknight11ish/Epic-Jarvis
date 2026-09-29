# Painted eyelids: a PREVIEW, not part of the app yet

This branch (`eyelids-preview`) is a prototype for the owner to look at. The
main branch does not have it.

**What it is.** The animals' eyes can only squash up and down, so an error
reads as a wink. This paints a lid of the surrounding fur over the top of
each eye, with a thin darker crease along its edge, and the lid can slope
(the inner end up is a worried look). It is worked out in the shader's
surface colouring (`eyeLid` in `jarvis-desktop/critters/common_head.sksl`),
once per pixel on the eyes only, not in the distance function, so the march
does not pay for it. One new shader value, `uLid` (how far down, and the slope).

**What it is NOT.** It is not wired to the animals' poses. Nothing sets
`uLid` in the running app, and no golden file changed. The pictures here were
made by `render-lids.mjs` (in this folder), which sets `uLid` by hand:

| state | lid down | slope |
|---|---|---|
| idle | 0 | - |
| waiting on you | 0.2 | level (steady, attending) |
| error | 0.42 | 1 (inner end up: worried) |
| dozing ("keeping things for later") | 0.55 | level (heavy) |

With `uLid` 0 the pictures are unchanged: the phone's shader was compared with
the main branch's through Skia over 48 pictures per animal, 0 pixels different.

**Sizes** (phone copy, limit 60,000): panda 59,678 (main: 59,729), monkey
59,587 (main: 59,728), owl 52,049 (main: 51,945), otter 55,003 (main: 54,898).
The lid costs about 110 in each. The panda and monkey paid for it with exact
rewrites of shape code that runs in every march step, which change no pixel:
the panda's legs and head no longer build a mirrored copy of the point first,
and the monkey's torso no longer adds a zero vector.

Pictures: `eyelids-before-after-300.png` (heads, 300 px) and
`eyelids-before-after-120.png` (whole animals, 120 px). The otter is small.
