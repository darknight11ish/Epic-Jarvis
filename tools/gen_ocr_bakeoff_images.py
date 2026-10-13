#!/usr/bin/env python3
"""gen_ocr_bakeoff_images.py - draw the small set of pictures the two-reader
measurement is run on.

    py -3 tools/gen_ocr_bakeoff_images.py

Writes four files into backend/test_files/ocr-bakeoff/ and prints their paths.
They are committed, so nobody has to run this to repeat the measurement; run it
to change or re-make them.

WHY THEY ARE DRAWN RATHER THAN COLLECTED
========================================
The measurement is about the owner's screen text, and this repository has no
picture of the owner's screen - there are none, and the owner has not supplied
any. Drawing the pictures here means the measurement is reproducible by anyone
and can say exactly what was drawn, which is what lets its report name the
words each reader got right (docs/MEASURED-2026-10-13-ocr-two-readers.md says
plainly that this makes the result about SYNTHETIC text, not the owner's).

The four are chosen for the shapes real screen text takes: an ordinary dialog,
text with a secret in it (what the black-out exists for), small low-contrast
text (the hard case), and a JPEG (what a phone screenshot arrives as).
"""
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - the message is the point
    print("This needs pillow: py -3 -m pip install -r backend\\requirements.txt")
    raise SystemExit(2)

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "backend" / "test_files" / "ocr-bakeoff"


def font(size: int):
    """A monospaced face if Windows has one, else whatever Pillow has."""
    for name in ("consola.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/" + name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw(path: Path, size, lines, *, fg=(0, 0, 0), bg=(255, 255, 255),
         fsize=28, jpeg=False) -> Path:
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    f = font(fsize)
    y = 30
    for line in lines:
        d.text((40, y), line, fill=fg, font=f)
        y += int(fsize * 2.1)
    img.save(path, **({"quality": 88} if jpeg else {}))
    return path


def main(out_dir=None) -> int:
    out = Path(out_dir) if out_dir else OUT
    out.mkdir(parents=True, exist_ok=True)
    draw(out / "dialog.png", (880, 340), [
        "Delete this file?",
        "This will remove report-final.docx",
        "from your Documents folder.",
        "Cancel            Delete",
    ])
    # A secret on screen: the case jarvis_secrets.py exists to black out.
    draw(out / "secret-key.png", (980, 300), [
        "Settings",
        "API key: sk-live-9f4a2b7c8d1e3f5a",
        "Endpoint: https://api.example.com/v2",
    ])
    # Small and low-contrast: the hard case for any reader.
    draw(out / "small-grey.png", (760, 300), [
        "System information",
        "Build 26100.1  Kernel 10.0.26100",
        "Installed 2026-04-11  Uptime 6d 4h",
    ], fg=(90, 90, 90), fsize=18)
    # A JPEG, not a PNG: what a phone screenshot arrives as.
    draw(out / "phone-photo.jpg", (900, 360), [
        "Two-factor code",
        "Your code is 481-902",
        "It expires in 10 minutes.",
    ], jpeg=True)
    for p in sorted(out.iterdir()):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
