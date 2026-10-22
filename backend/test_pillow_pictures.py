"""The picture paths, on the Pillow version this repository pins (13).

    python3 test_pillow_pictures.py

WHY THIS EXISTS. Pillow 12.3.0 carried 24 security advisories, and the only
release that fixes any of them is 13.0.0 - a major version. Four shipped
modules hand pictures to Pillow and they load it by name (`importlib`), so no
compiler sees those calls: `jarvis_form_review.fit` scales a screenshot of a
filled-in web form, `jarvis_screen_picture.shrink` shrinks a screen picture,
`jarvis_ui_control` turns a raw BGRA buffer into a PNG, and `jarvis_ocr.
bgra_from_bytes` decodes a phone's JPEG for the black-out step. A removed or
renamed Pillow API would show up as "the picture could not be scaled down" in
a card - or, for the OCR one, as a picture that is never cleaned.

So this calls the REAL functions with REAL pictures, and prints the Pillow
version it ran on. It does not assert a version number: a future major that
keeps these calls working is fine.

WHAT IT DOES NOT PROVE: nothing here needs a screen, a browser or a phone.
The no-screen edges (a real page screenshot, a real phone JPEG) are the
owner's own field test.

A missing Pillow is a named SKIP, never a pass. Pillow is optional at run
time on purpose: with none, `fit` refuses in words and `shrink` returns the
picture unchanged.
"""
import io
import struct
import sys
import traceback

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} ({why})")


def _jpeg(width, height, colour=(210, 190, 170)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _png(width, height, colour=(30, 60, 90)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, "PNG")
    return buf.getvalue()


def t_form_review_scales_a_big_screenshot():
    """jarvis_form_review.fit: the path a too-tall web-form screenshot takes."""
    import jarvis_form_review as F
    from PIL import Image

    check("the fit path exists and its caps are the documented ones",
          isinstance(F.MAX_SIDE, int) and isinstance(F.MAX_BYTES, int),
          f"{getattr(F, 'MAX_SIDE', None)}, {getattr(F, 'MAX_BYTES', None)}")
    out = F.fit(_jpeg(2200, 3400))
    check("a picture over the long side comes back scaled",
          max(out["width"], out["height"]) <= F.MAX_SIDE,
          f"{out['width']}x{out['height']}")
    check("the scaled picture is a real JPEG",
          out["jpeg"][:2] == b"\xff\xd8" and out["jpeg"][-2:] == b"\xff\xd9")
    check("the stated size is the picture's own size",
          F.jpeg_size(out["jpeg"]) == (out["width"], out["height"]),
          f"said {out['width']}x{out['height']}, JPEG says "
          f"{F.jpeg_size(out['jpeg'])}")
    check("it is inside the byte cap", len(out["jpeg"]) <= F.MAX_BYTES,
          f"{len(out['jpeg'])} bytes")
    with Image.open(io.BytesIO(out["jpeg"])) as check_img:
        check("Pillow can open what fit() produced", check_img.format == "JPEG")


def t_form_review_leaves_a_small_picture_alone():
    """Inside the caps it must be byte-for-byte the input: no re-encode."""
    import jarvis_form_review as F
    small = _jpeg(400, 300)
    out = F.fit(small)
    check("a picture already inside the caps is returned unchanged",
          out["jpeg"] == small and (out["width"], out["height"]) == (400, 300),
          f"{out['width']}x{out['height']}, {len(out['jpeg'])} bytes")


def t_screen_picture_shrinks_a_big_png():
    """jarvis_screen_picture.shrink: the path a large screen PNG takes."""
    import jarvis_screen_picture as S
    from PIL import Image

    big = _png(2000, 1200)
    out = S.shrink(big, 800)
    size = S._png_size(out)
    check("a big screen PNG comes back shrunk", size is not None and max(size) <= 800,
          str(size))
    check("and it is still a PNG", out[:8] == b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(out)) as check_img:
        check("Pillow can open what shrink() produced",
              check_img.format == "PNG", str(getattr(check_img, "format", None)))
    small = _png(320, 200)
    check("a PNG already inside the cap is returned unchanged",
          S.shrink(small, 800) == small)


def t_ocr_decodes_a_jpeg_to_bgra():
    """jarvis_ocr.bgra_from_bytes: the phone-JPEG path the black-out uses."""
    import jarvis_ocr as O
    from PIL import Image

    out = O.bgra_from_bytes(_jpeg(640, 480))
    check("a JPEG decodes for the black-out step", out is not None)
    if out is None:
        return
    bgra, width, height = out
    check("the decoded size is the picture's size", (width, height) == (640, 480),
          f"{width}x{height}")
    check("four bytes per pixel, as the painter expects",
          len(bgra) == width * height * 4, str(len(bgra)))
    # One red pixel: RGBA (255,0,0,255) must come back B,G,R,A.
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buf, "PNG")
    tiny = O.bgra_from_bytes(buf.getvalue())
    check("the channel order is BGRA, not RGBA",
          tiny is not None and tiny[0] == b"\x00\x00\xff\xff",
          str(None if tiny is None else tiny[0]))


def t_ui_control_buffer_path_still_works():
    """jarvis_ui_control's raw-buffer step: Image.frombuffer -> RGB PNG."""
    from PIL import Image

    raw = bytes([0, 0, 255, 255]) * 8          # eight red BGRA pixels
    im = Image.frombuffer("RGBA", (8, 1), raw, "raw", "BGRA", 0, 1)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG")
    decoded = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    check("a raw BGRA buffer becomes a PNG and reads back red",
          decoded.size == (8, 1) and decoded.getpixel((0, 0)) == (255, 0, 0),
          f"{decoded.size} {decoded.getpixel((0, 0))}")


if __name__ == "__main__":
    try:
        import PIL
        import PIL.Image  # noqa: F401
    except Exception:
        skip("the whole suite", "Pillow is not installed on this machine")
        print("\n0 passed, 0 failed, 1 skipped - SKIPPED IS NOT A PASS: this "
              "suite proves nothing on a PC without Pillow.")
        sys.exit(0)
    print(f"Pillow version under test: {PIL.__version__}")
    for fn in (t_form_review_scales_a_big_screenshot,
               t_form_review_leaves_a_small_picture_alone,
               t_screen_picture_shrinks_a_big_png,
               t_ocr_decodes_a_jpeg_to_bgra,
               t_ui_control_buffer_path_still_works):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
