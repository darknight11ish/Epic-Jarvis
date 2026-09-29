"""jarvis_picture.py - the picture half of "screen safety": paint SOLID BLACK
over the secrets jarvis_secrets.py found, and hand on only a picture that has
been checked.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
no patch). The owner's "all three" of 2026-09-29 (CLAUDE.md), part 1.
jarvis_screen.clean_picture is the one door a screen picture goes through;
this is what is behind it.

WHAT `clean()` DOES
  1. The text reader (jarvis_ocr.read_text: the words AND where each sits) is
     run on the picture.
  2. jarvis_secrets.redact finds the secrets in ALL the words - before any
     cut to length - and says which words, and which boxes, to hide.
  3. The words handed on have each hidden run replaced by "[hidden]".
  4. With `want_png`, the picture is decoded, every box is filled with SOLID
     BLACK (never a blur), and a PNG is made. A picture the words of which
     have no positions, or that cannot be decoded, or whose size is not the
     size the words were read from, is NOT handed on: `png` is None and
     `png_why` says why. Fail closed.

`png` is the ONLY picture anything is allowed to show a picture model (a
second-card vision model, the CPU picture model). The original is never
passed on. When nothing was hidden the original bytes come back unchanged
(nothing to paint).

NOT DONE BY REGEX, SAID PLAINLY: a password shown with a show-password eye,
or in a box with nothing written beside it, has no shape a pattern can tell
from other words. See jarvis_secrets.py.

Pure Python: the PNG reader below is tiny and handles the pictures this PC
makes itself (jarvis_screen_win.png_from_bgra) at full speed and ordinary
PNGs slowly but correctly; a JPEG from the phone is decoded by Windows itself
(jarvis_ocr.read_lines(want_pixels=True)) or refused - never guessed at.
"""
from __future__ import annotations

import math
import struct
import zlib
from typing import Callable, Optional

import jarvis_secrets as sec

#: The most pixels the pure-Python PNG reader will take (a 4K screen is 8.3 M).
MAX_PIXELS = 20_000_000
#: A PNG that uses the row filters (this PC's own never does) is unpacked in
#: plain Python, which is slow; past this many pixels it is refused rather than
#: left to stall a look. A refusal is "cannot clean" - no picture - never a guess.
MAX_FILTERED_PIXELS = 2_500_000

NO_POSITIONS = "the words were read without their positions"
NOT_DECODED = "the picture could not be opened to paint on"
SIZE_DIFFERS = "the picture is not the size the words were read from"
NOT_CHECKED = sec.NOT_CHECKED


# --------------------------------------------------------------------------
#   A small PNG reader (8-bit, not interlaced) and the black box
# --------------------------------------------------------------------------

def decode_png(data: bytes) -> Optional[tuple]:
    """(BGRA bytearray, width, height) of an 8-bit, non-interlaced PNG, or
    None for anything else (or damage, or too many pixels)."""
    try:
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        pos, idat, plte, hdr = 8, [], b"", None
        while pos + 8 <= len(data):
            n, kind = struct.unpack(">I4s", data[pos:pos + 8])
            body = data[pos + 8:pos + 8 + n]
            if len(body) != n:
                return None
            pos += 12 + n
            if kind == b"IHDR":
                hdr = struct.unpack(">IIBBBBB", body)
            elif kind == b"PLTE":
                plte = body
            elif kind == b"IDAT":
                idat.append(body)
            elif kind == b"IEND":
                break
        if hdr is None or not idat:
            return None
        w, h, depth, ctype, _comp, _flt, interlace = hdr
        if depth != 8 or interlace != 0 or w <= 0 or h <= 0 or w * h > MAX_PIXELS:
            return None
        chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
        if chans is None or (ctype == 3 and len(plte) < 3):
            return None
        stride = w * chans
        expected = (stride + 1) * h
        # Unpack at most what the header says the picture holds (plus one byte to
        # see an excess): a small file that inflates to gigabytes is refused, not
        # unpacked (a "PNG bomb").
        d = zlib.decompressobj()
        raw = d.decompress(b"".join(idat), expected + 1)
        if len(raw) != expected:
            return None
        rows = _unfilter(raw, w, h, chans)
        if rows is None:
            return None
        out = bytearray(w * h * 4)
        n = w * h
        out[3::4] = b"\xff" * n
        if ctype == 2:
            out[0::4], out[1::4], out[2::4] = rows[2::3], rows[1::3], rows[0::3]
        elif ctype == 6:
            out[0::4], out[1::4], out[2::4], out[3::4] = rows[2::4], rows[1::4], rows[0::4], rows[3::4]
        elif ctype == 0:
            out[0::4], out[1::4], out[2::4] = rows, rows, rows
        elif ctype == 4:
            out[0::4], out[1::4], out[2::4], out[3::4] = rows[0::2], rows[0::2], rows[0::2], rows[1::2]
        else:                                      # palette: one table per colour
            pal = [plte[i:i + 3] for i in range(0, len(plte) - 2, 3)]
            tables = [bytes((pal[i][c] if i < len(pal) else 0) for i in range(256)) for c in (2, 1, 0)]
            out[0::4], out[1::4], out[2::4] = (rows.translate(t) for t in tables)
        return out, w, h
    except Exception:
        return None


def _unfilter(raw: bytes, w: int, h: int, bpp: int) -> Optional[bytearray]:
    """The picture's bytes with the PNG row filters undone (packed, no
    filter bytes). Filter 0 (what this PC writes) is a plain copy."""
    stride = w * bpp
    if w * h > MAX_FILTERED_PIXELS and any(raw[y * (stride + 1)] for y in range(h)):
        return None                                # filtered and big: too slow to unpack here
    out = bytearray(stride * h)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if f == 0:
            pass
        elif f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        else:
            return None
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def paint_black(bgra: bytearray, width: int, height: int, boxes) -> int:
    """Fill every box with SOLID BLACK, in place, clipped to the picture.
    Boxes are (left, top, right, bottom) in pixels, floats allowed; each is
    rounded OUT (down on the left and top, up on the right and bottom), so
    a box never covers less than it was asked to. Returns how many boxes
    touched the picture."""
    black = b"\x00\x00\x00\xff"
    painted = 0
    for box in boxes or []:
        l, t, r, b = box
        x0, x1 = max(0, int(math.floor(l))), min(width, int(math.ceil(r)))
        y0, y1 = max(0, int(math.floor(t))), min(height, int(math.ceil(b)))
        if x1 <= x0 or y1 <= y0:
            continue
        fill = black * (x1 - x0)
        for y in range(y0, y1):
            o = (y * width + x0) * 4
            bgra[o:o + len(fill)] = fill
        painted += 1
    return painted


def encode_png(bgra, width: int, height: int) -> bytes:
    import jarvis_screen_win
    return jarvis_screen_win.png_from_bgra(bytes(bgra), width, height)


# --------------------------------------------------------------------------
#   The whole thing
# --------------------------------------------------------------------------

def _fail(why: str, unchecked: bool = False) -> dict:
    return {"ok": False, "text": "", "left_out": 0, "hidden": 0, "kinds": [], "png": None,
            "png_why": why, "why": why, "unchecked": unchecked}


def clean(image: bytes, *, ocr: Callable, want_png: bool = False,
          reader_with_pixels: Optional[Callable] = None) -> dict:
    """Read the picture's words, hide the secrets in them, and (on request)
    paint them out of the picture. `ocr(image)` is jarvis_ocr.read_text's
    shape - {"ok", "text", "left_out", "lines"?, "size"?} - or a plain
    string. `reader_with_pixels(image)` (default: jarvis_ocr.read_lines with
    want_pixels) is only asked for when the picture is not a PNG this module
    can open itself.

    -> {"ok": the WORDS are usable, "text": the words with each hidden run
        replaced by "[hidden]" (not cut to length), "left_out": int (only
        for a reader that gave no positions), "hidden": how many runs were
        hidden, "kinds": which patterns fired (fixed ids, never a secret),
        "png": the cleaned PNG or None, "png_why": why there is none,
        "why": why not ok, "unchecked": True when the check itself could not
        run}. Never raises; nothing here writes to disk."""
    try:
        got = ocr(image)
    except Exception:
        got = {"ok": False}
    lines = None
    left = 0
    if isinstance(got, str):
        text_in = got
    elif isinstance(got, dict):
        if got.get("ok") is False:
            return _fail(str(got.get("why") or "the words could not be read"))
        lines = got.get("lines")
        text_in = str(got.get("text") or "")
        if not isinstance(lines, list):
            lines = None
            left = int(got.get("left_out") or 0)
        # (a list, even an empty one: an engine that gives positions and found no words -
        # there is nothing to hide, and `lines` are whole - the caller cuts the text itself)
    else:
        return _fail("the words could not be read")
    has_positions = lines is not None
    try:
        red = sec.check(lines if has_positions else text_in)
    except sec.Unchecked as exc:
        out = _fail("%s (%s)" % (NOT_CHECKED, exc), True)
        return out
    except Exception:
        return _fail(NOT_CHECKED, True)
    text = red.text if (has_positions or red.hidden) else text_in
    res = {"ok": True, "text": text, "left_out": left, "hidden": red.hidden,
           "kinds": red.kinds, "png": None, "png_why": "", "why": "", "unchecked": False}
    if not want_png:
        return res
    # ---- the picture ---------------------------------------------------
    if not has_positions:
        res["png_why"] = NO_POSITIONS
        return res
    if red.boxless:
        res["png_why"] = NO_POSITIONS
        return res
    if not red.hidden:
        res["png"] = bytes(image)             # nothing to hide: the picture as it was
        return res
    try:
        size = got.get("size") if isinstance(got, dict) else None
        dec = decode_png(bytes(image))
        if dec is None:
            more = (reader_with_pixels or _read_with_pixels)(image)
            px = more.get("pixels") if isinstance(more, dict) else None
            if px:
                dec = (bytearray(px[0]), px[1], px[2])
        if dec is None:
            res["png_why"] = NOT_DECODED
            return res
        bgra, w, h = dec
        if size and (int(size[0]), int(size[1])) != (w, h):
            res["png_why"] = SIZE_DIFFERS
            return res
        paint_black(bgra, w, h, red.boxes)
        res["png"] = encode_png(bgra, w, h)
    except Exception:
        res["png"] = None
        res["png_why"] = NOT_DECODED
    return res


def _read_with_pixels(image: bytes) -> dict:
    import jarvis_ocr
    return jarvis_ocr.read_lines(image, want_pixels=True)
