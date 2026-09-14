#!/usr/bin/env python3
"""
Builds the adaptive launcher icon from the source artwork.

The source is a wide banner with the emblem centred in it, so this crops the
disc, drops the grey bezel, and turns the glow into a foreground layer with a
real alpha channel.

Two decisions worth knowing about:

**The bezel is discarded.** An adaptive icon's shape is chosen by the launcher
— circle, squircle, rounded square, teardrop — and a drawn ring fights that
mask: a circle inside a squircle reads as a small icon in a big frame. The glow
is the identity here; the bezel was the mock-up's frame.

**Alpha comes from luminance, and the colour is un-premultiplied.** This is
additive glow art on near-black. Android composites straight alpha
(`fg*a + bg*(1-a)`), so writing the original RGB against a partial alpha would
darken every mid-tone. Dividing the colour through by its own alpha makes the
composite reproduce the source exactly over black, and correctly over the
slightly-blue background layer.

    python3 tools/gen_launcher_icon.py <source.png>
"""
import pathlib
import sys

from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "jarvis-client/app/src/main/res"

# Measured off the source by radial luminance profile: the disc interior runs
# to r≈305 and the grey bezel sits at 306–324.
CENTRE = (703, 385)
CONTENT_R = 292

# An adaptive icon layer is 108dp; the launcher's mask shows about the middle
# 72dp and guarantees 66dp.
#
# 0.65 is measured, not chosen by eye. The artwork fills its own crop almost
# exactly — bright content reaches r=287 of a 292 half-width — so at 0.72 the
# atom spanned 77dp through a 72dp mask and the outer orbits were sliced off on
# the left and right. 0.65 lands the content at 69dp, inside the mask with
# about 1.5dp of clearance on each side.
LAYER_DP = 108
CONTENT_FRACTION = 0.65

# Alpha ramp. Below FLOOR is the disc's own dark ground and becomes fully
# transparent; above CEIL is core glow and becomes opaque.
LUM_FLOOR = 16.0
LUM_CEIL = 120.0

# A much higher window for the monochrome layer — see build_monochrome.
MONO_FLOOR = 100.0
MONO_CEIL = 190.0

DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def luminance(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def build_foreground(src: Image.Image) -> Image.Image:
    cx, cy = CENTRE
    crop = src.crop((cx - CONTENT_R, cy - CONTENT_R, cx + CONTENT_R, cy + CONTENT_R))
    crop = crop.convert("RGB")
    w, h = crop.size
    out = Image.new("RGBA", (w, h))
    sp, op = crop.load(), out.load()
    radius = w / 2.0

    for y in range(h):
        for x in range(w):
            r, g, b = sp[x, y]
            a = smoothstep((luminance(r, g, b) - LUM_FLOOR) / (LUM_CEIL - LUM_FLOOR))

            # Feather the last few percent of the crop so no square edge can
            # survive into the icon if the artwork changes.
            d = ((x - radius) ** 2 + (y - radius) ** 2) ** 0.5 / radius
            if d > 0.94:
                a *= max(0.0, 1.0 - (d - 0.94) / 0.06)

            if a <= 0.004:
                op[x, y] = (0, 0, 0, 0)
                continue
            # Un-premultiply, so compositing reproduces the source.
            op[x, y] = (
                min(255, int(r / a)),
                min(255, int(g / a)),
                min(255, int(b / a)),
                int(round(a * 255)),
            )
    return out


def build_monochrome(src: Image.Image) -> Image.Image:
    """Themed icons, Android 13+: one tint, flattened.

    Built from the source luminance rather than from the colour layer's alpha,
    because the two want opposite things. The colour layer keeps the nebula
    haze — that haze IS the glow. Flattened to a single tint the same haze
    becomes a grey smudge with the atom somewhere inside it, which is what the
    first attempt produced.

    So this throws the haze away and keeps only what survives as a shape: the
    orbit ellipses, the electrons and the core. A median pass first, because
    the artwork's star dust thresholds into confetti; then a dilate, because a
    one-pixel orbit line disappears entirely at 48dp on a phone.
    """
    cx, cy = CENTRE
    crop = src.crop((cx - CONTENT_R, cy - CONTENT_R, cx + CONTENT_R, cy + CONTENT_R))
    crop = crop.convert("RGB")
    w, h = crop.size
    sp = crop.load()
    radius = w / 2.0

    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            d = ((x - radius) ** 2 + (y - radius) ** 2) ** 0.5 / radius
            if d > 1.0:
                continue
            r, g, b = sp[x, y]
            a = smoothstep((luminance(r, g, b) - MONO_FLOOR) / (MONO_CEIL - MONO_FLOOR))
            mp[x, y] = int(round(a * 255))

    mask = mask.filter(ImageFilter.MedianFilter(3))
    mask = mask.filter(ImageFilter.MaxFilter(3))
    mask = mask.filter(ImageFilter.GaussianBlur(0.8))

    mono = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    mono.putalpha(mask)
    return mono


def emit(layer: Image.Image, name: str):
    for density, scale in DENSITIES.items():
        size = int(LAYER_DP * scale)
        content = int(round(size * CONTENT_FRACTION))
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        scaled = layer.resize((content, content), Image.LANCZOS)
        off = (size - content) // 2
        canvas.paste(scaled, (off, off), scaled)
        target = RES / f"mipmap-{density}"
        target.mkdir(parents=True, exist_ok=True)
        canvas.save(target / f"{name}.png", optimize=True)
        print(f"  mipmap-{density}/{name}.png  {size}x{size}")


def main():
    source = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not source or not source.exists():
        raise SystemExit(f"usage: {sys.argv[0]} <source.png>")
    src = Image.open(source)
    print(f"source {src.size} -> crop {CONTENT_R * 2}px at {CENTRE}")
    fg = build_foreground(src)
    emit(fg, "ic_launcher_foreground")
    emit(build_monochrome(src), "ic_launcher_monochrome")


if __name__ == "__main__":
    main()
