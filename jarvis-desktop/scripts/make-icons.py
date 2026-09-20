#!/usr/bin/env python3
"""Cut the Windows icon set out of the emblem artwork.

`tauri icon` cannot do this: the source art is a wide scene with the emblem
sitting inside it, and the icon is the emblem alone, circular. So the crop,
the mask and every size are done here, and `npm run icons` runs this instead.

The numbers below are measured, not guessed — `scripts/` has no state, so the
next person to regenerate these gets the same crop rather than eyeballing it
again. `CENTRE` and `RADIUS` are the emblem's grey bezel, found by walking rays
out from the middle until the luminance drops to the background:

    0deg r=321   90deg r=324   180deg r=323   270deg r=322
   45deg r=322  135deg r=323   225deg r=319   315deg r=319

322 lands on the bezel itself, so the circular mask cuts along a rim that is
already there rather than slicing through the artwork.

    python3 scripts/make-icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ICONS = HERE.parent / "src-tauri" / "icons"
SOURCE = ICONS / "source" / "jarvis-emblem.png"

CENTRE = (705, 384)
RADIUS = 322
#: Everything is cut from one high-resolution master so no size is a resize of
#: a resize. 1024 is four times the largest icon Windows asks for.
MASTER = 1024
#: The mask is drawn at this multiple and shrunk, because a hard ellipse at
#: 32px is a staircase and this is the size the taskbar actually shows.
SUPERSAMPLE = 4

PNGS = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "icon.png": 512,
    "StoreLogo.png": 50,
    "Square30x30Logo.png": 30,
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square89x89Logo.png": 89,
    "Square107x107Logo.png": 107,
    "Square142x142Logo.png": 142,
    "Square150x150Logo.png": 150,
    "Square284x284Logo.png": 284,
    "Square310x310Logo.png": 310,
}

# 16 is the notification area and 256 is the file-properties dialog; Windows
# picks from inside the .ico rather than scaling one of them.
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def master() -> Image.Image:
    art = Image.open(SOURCE).convert("RGBA")
    cx, cy = CENTRE
    disc = art.crop((cx - RADIUS, cy - RADIUS, cx + RADIUS, cy + RADIUS))

    side = disc.width
    mask = Image.new("L", (side * SUPERSAMPLE, side * SUPERSAMPLE), 0)
    ImageDraw.Draw(mask).ellipse(
        (0, 0, side * SUPERSAMPLE - 1, side * SUPERSAMPLE - 1), fill=255
    )
    mask = mask.resize((side, side), Image.LANCZOS)

    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.paste(disc, (0, 0), mask)
    return out.resize((MASTER, MASTER), Image.LANCZOS)


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"the emblem artwork is missing: {SOURCE}")
    base = master()
    for name, size in PNGS.items():
        base.resize((size, size), Image.LANCZOS).save(ICONS / name)
    base.resize((256, 256), Image.LANCZOS).save(
        ICONS / "icon.ico", format="ICO", sizes=ICO_SIZES
    )

    # The corners have to be clear or the mask silently did nothing and every
    # icon ships square.
    check = Image.open(ICONS / "32x32.png").convert("RGBA")
    if check.getpixel((0, 0))[3] != 0:
        raise SystemExit("the circular mask did not apply: 32x32 has an opaque corner")
    print(f"{len(PNGS)} PNGs and icon.ico written to {ICONS}")


if __name__ == "__main__":
    main()
