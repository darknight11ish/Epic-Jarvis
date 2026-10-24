#!/usr/bin/env python3
"""Draw the PWA's own icons from the HUD's monochrome emblem.

The PWA icons are NOT the Windows `src-tauri/icons/` set: those are cut from
the emblem artwork (a scene with a circular bezel, `make-icons.py`) and are
device-window icons. A home-screen/manifest icon is a small square tile, and
the PWA needs three of them, under the names the static whitelist serves
(`/icons/jarvis-180.png`, `-192.png`, `-512.png`). So the same MARK is redrawn
here as simple geometry - the HUD's own `◈` glyph (U+25C8: an outer diamond
ring with a smaller filled diamond inside it, the mark the Studio rail shows
in `html[data-hud-shell="split-stage"] .rail .brand h1::before`) in the HUD's
ice accent on the deep-space well. No artwork is copied: two rotated squares
and two colours.

The 512 tile is the one a launcher may MASK (Android crops maskable icons to a
circle or rounded square), so its mark is drawn smaller and stays inside the
central 80% safe circle; the manifest lists that one PNG as
`purpose: "any maskable"`. The 180 and 192 tiles use the larger mark.

Colours are the HUD's own surface tokens, read from `tokens/themes.tokens.json`
so a palette change moves the icons with it (the same source `theme.css` is
generated from):

    background  themes.deep-space.surfaceSunken  #04070c
    ink         themes.deep-space.accent         #38f0ff

Regenerate (the committed PNGs are the source of truth for the manifest and
for the delivery copies in backend/static/):

    python3 scripts/make-pwa-icons.py

Pillow is the only dependency, and only for regenerating - nothing at build or
test time imports this file; the PNGs themselves are committed and tiny.
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
ICONS = SRC / "icons"

#: The HUD's own deep-space values (tokens/themes.tokens.json).
BACKGROUND = (4, 7, 12, 255)      # deep-space surfaceSunken  #04070c
INK = (56, 240, 255, 255)         # deep-space accent        #38f0ff

#: Rendered 4x and shrunk, so the diamond's edges are not a staircase.
SUPERSAMPLE = 4

#: The names `jarvis-backend/jarvis_hud.py`'s STATIC_ASSETS whitelist serves,
#: each size and the mark's half-width as a fraction of the canvas. 0.34 is the
#: normal mark; 0.22 keeps the maskable one inside the 80% safe circle.
PNGS = {
    "jarvis-180.png": (180, 0.34),
    "jarvis-192.png": (192, 0.34),
    "jarvis-512.png": (512, 0.22),
}


def draw_mark(size: int, radius_fraction: float) -> Image.Image:
    """One square icon: the deep-space well plus the ◈ mark in ice."""
    big = size * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), BACKGROUND)
    draw = ImageDraw.Draw(img)
    cx = cy = big / 2

    outer = radius_fraction * big
    inner = outer * 0.54
    stroke = max(1, int(round(big * 0.030)))

    def diamond(r):
        return [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]

    # ◈: an outer diamond RING with a smaller filled diamond inside it.
    draw.line(diamond(outer) + [diamond(outer)[0]], fill=INK, width=stroke,
              joint="curve")
    draw.polygon(diamond(inner), fill=INK)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    for name, (size, radius) in PNGS.items():
        path = ICONS / name
        img = draw_mark(size, radius)
        # A monochrome tile compresses to a few hundred bytes; keep it that way.
        img.save(path, "PNG", optimize=True)
        print(f"{path.relative_to(SRC)}  {size}x{size}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
