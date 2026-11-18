"""jarvis_image_convert.py - pictures into ONE PDF, or ONE picture into another
picture format, on this PC, with one approval card per file written.

WHAT IT IS FOR

The owner's question of 2026-11-18: *"Can Jarvis convert certain formats of
files to other formats? like to pdf from an image and so forth?"* The research
lane settled the two answers this module implements, and they are deliberately
different tools for two different jobs:

  * IMAGES -> ONE PDF uses `img2pdf`. It is the only honest writer for this:
    for a JPEG (and a JPEG-2000, and a non-interlaced PNG, and a
    CCITT-Group-4 TIFF) it copies the picture's OWN compressed bytes straight
    into the PDF, so the file grows by the PDF container only - a few hundred
    bytes - and NOT ONE PIXEL is re-encoded. Pillow's own `save(..., "PDF")`
    is the trap this module exists to avoid: it re-encodes RGB through its
    JPEG encoder, defaults the page to 72 dpi, and turns a palette image into
    raw hex. That is exactly the "silently changed my file" failure the owner
    told us to never ship. The suite proves the claim the only way that means
    anything: it looks for the input JPEG's bytes inside the produced PDF.
  * ONE PICTURE -> ANOTHER FORMAT uses Pillow, which is already installed
    (13.0.0, pinned, HPND). PNG / JPEG / WebP / AVIF / TIFF are offered. The
    owner-facing sentence says the truth about each target: PNG and TIFF are
    lossless, JPEG, WebP and AVIF are NOT, and the copy is a re-encode. A
    picture with transparency that is asked to become a JPEG is flattened
    onto WHITE, and the sentence says so, because JPEG cannot store
    transparency. The source file is never touched.

WHAT IS MEASURED AND SAFE HERE

  * One file WRITTEN per call, and it is always a NEW name: the target is
    opened with `O_CREAT | O_EXCL`, so even if something appears at that name
    while the approval card is up, the write fails and nothing is overwritten.
    A name that already exists gets a numbered sibling (`photo (2).pdf`, the
    same rule the phone uploader and the Notion importer use) when the tool
    chose the name itself; a path the owner named explicitly that already
    exists is REFUSED rather than renamed behind their back.
  * Sources are checked by SNIFFED CONTENT (Pillow opens the file and reads
    its header), not by extension. A text file called `photo.png` is refused
    in one plain sentence.
  * Every source must be inside a folder on "Folders Jarvis may look in", the
    same `jarvis_documents.allowed_path()` rule every reader uses, and the
    same "Protected from Jarvis" keep-out (`write=True` for the output, so a
    read-only folder refuses to gain a file).
  * Bounded: at most MAX_IMAGES pictures, MAX_IMAGE_BYTES per picture,
    MAX_TOTAL_BYTES for one PDF, MAX_PIXELS per picture; a 120-second clock
    on the child and a 64 KB cap on what it may say back.

THE CHILD-PROGRAM BOUNDARY

The conversion itself runs in a SEPARATE Python program (`sys.executable -I
-B -c`, the same pattern `jarvis_documents._default_convert` uses for
MarkItDown), never in the backend process:

  * it gets a scrubbed environment (`jarvis_child_env.inherited()`): no
    token, key or Jarvis setting is passed on;
  * its inputs are the explicit file names, its output is one temporary file
    in the destination folder, and it returns one small JSON line;
  * `img2pdf` and `pikepdf` (and Pillow) are imported THERE, so a broken or
    missing install is one plain refusal instead of a half-imported backend;
  * the parent then writes the destination with O_EXCL and deletes the
    temporary file. There is no path on which the child can replace an
    existing file.

A missing dependency is a plain refusal, never a silent skip: `img2pdf`
(and `pikepdf`, which it uses to assemble the PDF) for the PDF half, Pillow
for the picture half. All three are in backend/requirements.txt with the
pinned versions backend/requirements.lock holds.

THE PERMISSION MODEL

Writing a file is an "ask" card, one card per conversion. The tool this
module backs (`my_files` action `convert`) asks the gate under its own action
name, `convert_images`, whose "ask" line ships in both copies of
`jarvis-framework.toml` and whose risk row is in the published base
(`jarvis-backend/jarvis_gate.py`). `prepare()` refuses outright if that line
has been loosened from "ask" - a belt under the card, the same shape
`jarvis_send_file.py` uses - so a hand-edited settings file cannot make a
file write cardless. Nothing here raises a card of its own, serves a route or
approves anything: the ordinary tool-call gate is the only yes.

HONEST LIMITS

  * A PDF's page size follows each picture's own DPI (img2pdf's default
    layout); no paper size, margin, page numbering or PDF/A is offered.
  * A JPEG's EXIF orientation is honoured with `rotation=ifvalid`: a photo
    whose EXIF orientation is a valid value is rotated LOSSLESSLY by
    img2pdf; an INVALID orientation value 0 (some Android and Canon cameras)
    is treated as no rotation instead of failing the whole PDF.
  * A JPEG bigger than 65535 pixels on a side is refused by the PDF format
    itself; `prepare()` refuses it plainly rather than letting the child fail.
  * The lossless claim is about the PDF path only. Picture-to-picture
    conversion to JPEG/WebP/AVIF re-encodes, at quality 90; the sentence the
    owner reads says "lossy" and "not identical".
  * It never changes a source picture, never deletes anything, and never
    writes outside a listed folder.

Standard library plus the two optional parts named above (imported only
inside the child or, for the content sniff, by name). No network, no model,
no token, no route, no card of its own.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

#: The gate action one conversion is asked under. The shipped settings file
#: (both copies) carries `convert_images = "ask"`; the base gate's _RISK row
#: is what makes its card say what really happens. Kept here so the agent's
#: own lookup name and the settings line cannot drift.
ACTION = "convert_images"

#: One PDF may hold at most this many pictures, in the order given.
MAX_IMAGES = 20
#: One source picture's size on disk.
MAX_IMAGE_BYTES = 100 * 1024 * 1024
#: All the pictures of ONE PDF together.
MAX_TOTAL_BYTES = 400 * 1024 * 1024
#: One source picture's pixel count (a decompression-bomb guard as well as a
#: memory guard): 200 megapixels is far more than any phone camera makes.
MAX_PIXELS = 200_000_000
#: The PDF format itself cannot place a picture wider or taller than this.
MAX_SIDE = 65535
#: A conversion that takes longer than this is stopped and nothing is written.
CHILD_TIMEOUT = 120.0
#: What the child may send back at most (one small JSON line).
MAX_CHILD_BYTES = 64 * 1024

#: Pictures the PDF writer takes. The CONTENT is what decides; the extension
#: is only used to pick the new file's name, never to accept or refuse.
#: Pillow's own list is the one that can read them; a format it cannot open is
#: refused by the sniff.
PICTURE_HINT = (".jpg", ".jpeg", ".jfif", ".png", ".tif", ".tiff", ".webp",
                ".avif", ".bmp", ".gif", ".jp2", ".j2k", ".jpx", ".heic")

#: The picture-to-picture targets, keyed by the name the model says.
#: name -> (suffix of the new file, Pillow's format name, lossy?)
TARGETS = {
    "png":  (".png",  "PNG",  False),
    "jpeg": (".jpg",  "JPEG", True),
    "jpg":  (".jpg",  "JPEG", True),
    "webp": (".webp", "WEBP", True),
    "avif": (".avif", "AVIF", True),
    "tiff": (".tiff", "TIFF", False),
    "tif":  (".tiff", "TIFF", False),
}

#: What each target's own name is, in a sentence ("as a JPEG").
FORMAT_WORDS = {"png": "PNG", "jpeg": "JPEG", "jpg": "JPEG", "webp": "WebP",
                "avif": "AVIF", "tiff": "TIFF", "tif": "TIFF"}

#: Lossy targets are re-encoded at this quality (90 of 100).
QUALITY = 90

#: One refused compression of a lossy target. The owner must never be told a
#: re-encode is lossless - it is not, and that is the whole point of saying it.
LOSSY_WORDS = ("{fmt} is a LOSSY format: the picture is re-encoded at quality "
               "{quality}, so the copy is not identical to the original - it is "
               "a close approximation, not the same pixels.")
LOSSLESS_WORDS = ("{fmt} is a lossless format: every pixel is stored exactly, so "
                  "this copy loses no detail. (A detail the original JPEG had "
                  "already lost cannot be put back.)")
FLATTEN_WORDS = ("The transparent parts are flattened onto WHITE, because {fmt} "
                 "cannot store transparency.")

NO_IMG2PDF = ("This PC has no image-to-PDF part installed (img2pdf), so no PDF "
              "was made and nothing was written.")
NO_PILLOW = ("This PC has no picture reader installed (Pillow), so the picture "
             "was not converted and nothing was written.")
NOT_A_PICTURE = ("That file is not a picture, whatever its name says, so nothing "
                 "was converted and nothing was written.")
NOT_ASKED = ("This conversion writes a new file, so it runs only on an approval "
             "card; the \"What asks first\" line for it is {tier!r} instead of "
             "\"ask\", so it was refused and nothing was written.")
EXISTS_MEANWHILE = ("Something appeared at {path} while the approval card was up, "
                    "so nothing was written and nothing was overwritten.")
CHANGED_MEANWHILE = ("{path} changed while the approval card was up, so nothing "
                     "was written.")
NO_SOURCES = ("Say which pictures to use - their full paths, or one path for one "
              "picture.")
TOO_MANY = ("One PDF takes at most {n} pictures, so nothing was converted.")
ONE_PICTURE = ("One picture at a time is converted to another picture format; for "
               "several pictures at once, ask for a PDF instead.")
NOT_AN_IMAGE_FILE = ("\"{name}\" is not there any more, so nothing was converted.")
TOO_BIG = ("\"{name}\" is bigger than this converter's {mb} MB limit for one "
           "picture, so nothing was converted.")
TOO_MANY_PIXELS = ("\"{name}\" is {pixels:,} pixels, over this converter's "
                   "{limit:,} pixel limit, so nothing was converted.")
TOO_WIDE = ("\"{name}\" is {side} pixels on one side, and a PDF cannot hold a "
            "picture wider or taller than {limit}, so nothing was converted.")
TOTAL_BIG = ("Those pictures add up to more than this converter's {mb} MB limit "
             "for one PDF, so nothing was converted.")
NOT_IN_A_FOLDER = ("\"{name}\" is not inside a folder on your list, so nothing "
                   "was converted.")
PROTECTED = ("{said}")
FOLDER_GONE = ("The folder \"{folder}\" is not there any more, so nothing was "
               "converted.")
CANNOT_WRITE = ("Jarvis cannot write into \"{folder}\", so nothing was converted.")
ALREADY_THERE = ("There is already a file at {path}, so nothing was written and "
                 "nothing was overwritten.")
BAD_TARGET = ("\"{to}\" is not a picture format this PC can write; it can write "
              "PNG, JPEG, WebP, AVIF or TIFF, or make a PDF from pictures.")
NO_TARGET = ("Say what to convert it to: pdf, png, jpeg, webp, avif or tiff.")
SAME_PLACE = ("The new file would be the same file as \"{name}\", and Jarvis "
              "never writes over a picture - choose another name or format.")
TOO_MANY_NAMES = ("Give full paths for the pictures, not names - \"{name}\" is "
                  "not a path Jarvis can find.")
CHILD_FAILED = ("The converter could not read {what} (it may be damaged, or a "
                "format this PC cannot open), so nothing was written.")
CHILD_FAILED_PDF = ("The converter could not make a PDF from {what} (a picture may "
                    "be damaged, or in a format the PDF writer cannot read), so "
                    "nothing was written.")
CHILD_TIMEOUT_WORDS = ("The converter took longer than {seconds} seconds and was "
                       "stopped, so nothing was written.")
CHILD_ANSWER = ("The converter did not answer in a way Jarvis can read, so nothing "
                "was written.")
CHILD_TOO_LOUD = ("The converter produced more than this reader allows, so nothing "
                  "was written.")
WRITE_FAILED = ("The new file could not be written ({why}), so nothing was written "
                "and nothing was overwritten.")
NOT_A_PICTURE_OUT = ("The converter wrote something that is not a readable picture, "
                     "so it was deleted and nothing was kept.")
NOT_A_PDF_OUT = ("The converter wrote something that is not a PDF, so it was "
                 "deleted and nothing was kept.")


class Refused(ValueError):
    """One plain sentence, and nothing else. A ValueError so the agent's
    prepare() contract - which turns a ValueError into a tool result the model
    can read and retry from - needs no second exception class."""


# --------------------------------------------------------------------------
#   The child program: the ONLY place img2pdf/Pillow are imported for work
# --------------------------------------------------------------------------

#: The whole child program. It reads one JSON job from argv[1], writes exactly
#: one file (the temporary path it is given), and prints one JSON line. It
#: never sees a Jarvis setting, never opens a network connection and never
#: touches a file the job did not name.
_CHILD = r'''
import json, os, sys

def _say(**kw):
    sys.stdout.write(json.dumps(kw, ensure_ascii=True) + "\n")
    sys.stdout.flush()

def _main():
    job = json.loads(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2]:
        sys.path.insert(0, sys.argv[2])
    out = job["out"]
    try:
        if job["kind"] == "pdf":
            import img2pdf
            with open(out, "wb") as fh:
                fh.write(img2pdf.convert(list(job["inputs"]),
                                         rotation=img2pdf.Rotation.ifvalid))
            try:
                import pikepdf
                with pikepdf.open(out) as pdf:
                    pages = len(pdf.pages)
            except Exception:
                pages = 0
            _say(ok=True, pages=pages)
            return
        from PIL import Image
        with Image.open(job["input"]) as im:
            im.load()
            target = job["format"]
            flatten = bool(job.get("flatten"))
            if flatten:
                base = Image.new("RGB", im.size, (255, 255, 255))
                if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
                    im = im.convert("RGBA")
                    base.paste(im, mask=im.split()[-1])
                else:
                    base.paste(im.convert("RGB"))
                out_im = base
            else:
                out_im = im
            kwargs = {}
            if target in ("JPEG", "WEBP", "AVIF"):
                kwargs["quality"] = int(job.get("quality") or 90)
            if target == "JPEG" and flatten is False:
                out_im = out_im.convert("RGB")
            out_im.save(out, target, **kwargs)
        _say(ok=True, bytes=os.path.getsize(out))
    except Exception as exc:
        _say(ok=False, error=type(exc).__name__)

_main()
'''


def _child_env() -> dict:
    """A scrubbed environment: the project's own child allow-list when it is
    there, otherwise the few names Windows needs. No token, key or Jarvis
    setting is passed on."""
    try:
        import jarvis_child_env
        return jarvis_child_env.inherited()
    except Exception:                                         # noqa: BLE001
        keep = {}
        for name in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
                     "USERPROFILE", "LOCALAPPDATA"):
            value = os.environ.get(name)
            if value:
                keep[name] = value
        return keep


def _user_site() -> str:
    """The per-user packages folder, when this Python uses one: `-I` leaves it
    out, and img2pdf may have been installed there."""
    try:
        import site
        if site.ENABLE_USER_SITE:
            p = site.getusersitepackages()
            return p if isinstance(p, str) and os.path.isdir(p) else ""
    except Exception:                                         # noqa: BLE001
        pass
    return ""


def _run_child(job: dict) -> dict:
    """Run the conversion once, bounded, and read its one JSON line back."""
    args = [sys.executable, "-I", "-B", "-c", _CHILD,
            json.dumps(job, ensure_ascii=True)]
    us = _user_site()
    if us:
        args.append(us)
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(args, capture_output=True, timeout=CHILD_TIMEOUT,
                              env=_child_env(), input=b"",
                              cwd=os.path.dirname(sys.executable) or None,
                              creationflags=flags)
    except subprocess.TimeoutExpired:
        raise Refused(CHILD_TIMEOUT_WORDS.format(seconds=int(CHILD_TIMEOUT)))
    except Exception as exc:                                  # noqa: BLE001
        raise Refused(f"The converter could not start ({type(exc).__name__}), so "
                      f"nothing was written.")
    out = proc.stdout or b""
    if len(out) > MAX_CHILD_BYTES:
        raise Refused(CHILD_TOO_LOUD)
    try:
        doc = json.loads(out.decode("ascii", "replace"))
    except Exception:                                         # noqa: BLE001
        raise Refused(CHILD_ANSWER)
    if not isinstance(doc, dict):
        raise Refused(CHILD_ANSWER)
    return doc


# --------------------------------------------------------------------------
#   What a file really is - sniffed, never believed from its name
# --------------------------------------------------------------------------


def _pillow():
    """Pillow, or a plain refusal. Imported by name every time, so a backend
    that starts without it still starts."""
    try:
        from PIL import Image
        return Image
    except Exception:                                         # noqa: BLE001
        raise Refused(NO_PILLOW)


def sniff(path: str) -> dict:
    """{format, width, height, pixels, mode, alpha} for a real picture.

    The CONTENT decides: Pillow opens the file and reads its header. A text
    file called `photo.png` raises Refused(NOT_A_PICTURE). Nothing is decoded
    here beyond the header (`verify()` only checks the structure), so a huge
    or crafted file cannot make this expensive; the pixel count is capped
    before the child is ever started.
    """
    Image = _pillow()
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            fmt = str(im.format or "").upper()
            width, height = int(im.size[0]), int(im.size[1])
            mode = str(im.mode or "")
            alpha = bool(mode in ("RGBA", "LA", "PA", "RGBa", "La")
                         or (mode in ("P", "L", "RGB") and "transparency" in im.info))
    except Refused:
        raise
    except Exception:                                         # noqa: BLE001
        raise Refused(NOT_A_PICTURE)
    if width <= 0 or height <= 0:
        raise Refused(NOT_A_PICTURE)
    return {"format": fmt, "width": width, "height": height,
            "pixels": width * height, "mode": mode, "alpha": alpha}


# --------------------------------------------------------------------------
#   Where the file is - the owner's existing folder and protection rules
# --------------------------------------------------------------------------


def _allowed(path: str):
    """jarvis_documents.allowed_path for one existing path, as every reader
    here uses it; a refusal when it is outside the owner's listed folders."""
    try:
        import jarvis_documents as DOCS
    except Exception as exc:                                  # noqa: BLE001
        raise Refused(f"The folder list could not be read ({type(exc).__name__}), "
                      f"so nothing was converted.")
    try:
        got = DOCS.allowed_path(path)
    except Exception as exc:                                  # noqa: BLE001
        raise Refused(f"The folder list could not be read ({type(exc).__name__}), "
                      f"so nothing was converted.")
    if not got:
        raise Refused(NOT_IN_A_FOLDER.format(name=os.path.basename(path)))
    return got[0]


def _protection():
    """jarvis_protection, or None when that module is not on this backend.
    Looked up by name, the same way jarvis_notes_edit.py does, so a backend
    without the list behaves exactly as it did before."""
    try:
        import importlib
        return importlib.import_module("jarvis_protection")
    except Exception:                                         # noqa: BLE001
        return None


def _refusal_for_write(path: str) -> str:
    """The "Protected from Jarvis" answer for a path about to be WRITTEN."""
    P = _protection()
    if P is None:
        return ""
    try:
        return str(P.path_refusal(path, write=True) or "")
    except Exception:                                         # noqa: BLE001
        return ""


def _tier(action: str) -> str:
    """The tier `What asks first` has for the card; unreadable answers "ask"."""
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception:                                         # noqa: BLE001
        return "ask"


def _folder_of(path: str) -> str:
    return os.path.dirname(os.path.abspath(path))


def _inside_listed(folder: str) -> bool:
    """Is this folder itself inside one of the owner's listed folders? The
    output file does not exist yet, so `allowed_path` is asked about the
    FOLDER - which is a real path - rather than about a made-up file name
    inside it. (A probe named with a leading dot would be refused by
    `allowed_path`'s own hidden-folder rule, so there is no probe at all.)"""
    try:
        import jarvis_documents as DOCS
        return bool(DOCS.allowed_path(os.path.abspath(folder)))
    except Exception:                                         # noqa: BLE001
        return False


def _new_name(folder: str, stem: str, suffix: str) -> str:
    """A NEW file name in `folder`: `stem+suffix` when free, otherwise
    `stem (2)+suffix`, `stem (3)+suffix`... The same numbering the phone
    uploader and the Notion importer use. This never returns a name that is
    there NOW; O_EXCL at write time is what keeps it true afterwards."""
    first = os.path.join(folder, stem + suffix)
    if not os.path.exists(first):
        return first
    for n in range(2, 1000):
        cand = os.path.join(folder, f"{stem} ({n}){suffix}")
        if not os.path.exists(cand):
            return cand
    raise Refused(f"Every numbered name beside \"{stem}{suffix}\" is taken, so "
                  f"nothing was written.")


# --------------------------------------------------------------------------
#   The words: exactly what the card promises, and exactly what happened
# --------------------------------------------------------------------------


def _sources_words(paths: list) -> str:
    names = [os.path.basename(p) for p in paths]
    if len(names) == 1:
        return f"\"{names[0]}\""
    return ", ".join(f"\"{n}\"" for n in names[:-1]) + f" and \"{names[-1]}\""


def _pdf_copy_truth(sniffs: list) -> str:
    """The sentence about what happens to the pictures' own bytes.

    img2pdf copies a JPEG's (and a JPEG-2000's) compressed stream into the PDF
    as it is; a PNG and a TIFF are stored with lossless packing. So the claim
    is per-format and it is true of every picture named."""
    direct = [s for s in sniffs if s["format"] in ("JPEG", "JPEG2000")]
    if direct and len(direct) == len(sniffs):
        return ("The JPEG pictures go into the PDF BYTE FOR BYTE - nothing is "
                "re-encoded, so no pixel changes.")
    if direct:
        return ("The JPEG pictures go into the PDF byte for byte (nothing is "
                "re-encoded); the others are stored with lossless compression, so "
                "no detail is lost either way.")
    return ("The pictures are stored with lossless compression inside the PDF, so "
            "no detail is lost.")


def _card_pdf(paths: list, sniffs: list, out: str, wanted: str) -> str:
    words = [f"Make ONE PDF from {len(paths)} picture"
             f"{'s' if len(paths) != 1 else ''}, with the pages in the order "
             f"given ({_sources_words(paths)})."]
    if out != wanted:
        words.append(f"\"{os.path.basename(wanted)}\" already exists, so the new "
                     f"file gets a new name: \"{out}\". Nothing is overwritten.")
    else:
        words.append(f"The new file is \"{out}\".")
    words.append(_pdf_copy_truth(sniffs))
    page_sides = "; ".join(f"{s['width']}x{s['height']}" for s in sniffs[:MAX_IMAGES])
    words.append(f"Page sizes follow the pictures' own DPI ({page_sides} pixels).")
    words.append("Nothing that already exists is changed.")
    return " ".join(words)


def _card_picture(src: str, to: str, out: str, wanted: str, sniffed: dict,
                  flatten: bool) -> str:
    fmt = FORMAT_WORDS.get(to, to.upper())
    words = [f"Save a copy of \"{os.path.basename(src)}\" as {fmt}."]
    if out != wanted:
        words.append(f"\"{os.path.basename(wanted)}\" already exists, so the new "
                     f"file gets a new name: \"{out}\". Nothing is overwritten.")
    else:
        words.append(f"The new file is \"{out}\".")
    if TARGETS[to][2]:
        words.append(LOSSY_WORDS.format(fmt=fmt, quality=QUALITY))
    else:
        words.append(LOSSLESS_WORDS.format(fmt=fmt))
    if flatten:
        words.append(FLATTEN_WORDS.format(fmt=fmt))
    if sniffed["alpha"] and not flatten:
        words.append(f"The picture's transparency is kept ({fmt} can store it).")
    words.append("The original picture is not changed.")
    return " ".join(words)


# --------------------------------------------------------------------------
#   prepare(): work out exactly what would happen, then say it - no write
# --------------------------------------------------------------------------


def _sources(args: dict) -> list:
    raw = args.get("paths")
    if isinstance(raw, str):
        raw = [raw]
    if raw is None:
        single = args.get("path")
        raw = [single] if isinstance(single, str) and single.strip() else []
    if not isinstance(raw, (list, tuple)):
        raise Refused(NO_SOURCES)
    paths = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise Refused(NO_SOURCES)
        text = item.strip()
        if not text:
            continue
        paths.append(text)
    if not paths:
        raise Refused(NO_SOURCES)
    # A bare file NAME (no folder) cannot be checked against a folder list and
    # could mean anything; refuse it as not-a-path rather than invent one.
    for text in paths:
        head, tail = os.path.split(text)
        if not head and tail:
            raise Refused(TOO_MANY_NAMES.format(name=tail))
    if len(paths) > MAX_IMAGES:
        raise Refused(TOO_MANY.format(n=MAX_IMAGES))
    return paths


def _checked_source(path: str) -> tuple:
    """(real path, sniffed) for one picture, with every bound applied."""
    real = _allowed(path)
    if not os.path.isfile(real):
        raise Refused(NOT_AN_IMAGE_FILE.format(name=os.path.basename(path)))
    try:
        size = os.path.getsize(real)
    except OSError as exc:                                    # noqa: BLE001
        raise Refused(f"\"{os.path.basename(path)}\" could not be read "
                      f"({type(exc).__name__}), so nothing was converted.")
    if size > MAX_IMAGE_BYTES:
        raise Refused(TOO_BIG.format(name=os.path.basename(path),
                                     mb=MAX_IMAGE_BYTES // (1024 * 1024)))
    sniffed = sniff(real)
    if sniffed["pixels"] > MAX_PIXELS:
        raise Refused(TOO_MANY_PIXELS.format(name=os.path.basename(path),
                                             pixels=sniffed["pixels"],
                                             limit=MAX_PIXELS))
    if max(sniffed["width"], sniffed["height"]) > MAX_SIDE:
        raise Refused(TOO_WIDE.format(name=os.path.basename(path),
                                      side=max(sniffed["width"], sniffed["height"]),
                                      limit=MAX_SIDE))
    try:
        stat = os.stat(real)
    except OSError as exc:                                    # noqa: BLE001
        raise Refused(f"\"{os.path.basename(path)}\" could not be read "
                      f"({type(exc).__name__}), so nothing was converted.")
    return real, sniffed, {"size": int(stat.st_size), "mtime": float(stat.st_mtime)}


def prepare(args: dict, *, tier_of: Optional[Callable[[str], str]] = None):
    """(state, the card's words) for one conversion, or a plain refusal.

    Reads the files, the folder list and the protection list; raises ValueError
    with ONE plain sentence when it cannot go ahead, which the agent turns into
    a tool result the model can read and retry from. NOTHING is written here
    and no card is raised here - `convert()` runs only after the ordinary
    approval card has said yes.
    """
    action = str(args.get("action") or "").strip().lower()
    if action != "convert":
        raise ValueError("say convert, and what to convert the picture to")
    tier = (tier_of or _tier)(ACTION)
    if tier != "ask":
        # A BELT under the card, the same shape jarvis_send_file.py uses: a
        # file write must be asked every time, whatever a hand-edited
        # settings file says.
        raise ValueError(NOT_ASKED.format(tier=tier))
    to = str(args.get("to") or "").strip().lower()
    if not to:
        raise Refused(NO_TARGET)
    if to != "pdf" and to not in TARGETS:
        raise Refused(BAD_TARGET.format(to=to))
    sources = _sources(args)
    checked = [_checked_source(p) for p in sources]
    if to != "pdf" and len(checked) != 1:
        raise Refused(ONE_PICTURE)
    if to == "pdf":
        total = sum(c[2]["size"] for c in checked)
        if total > MAX_TOTAL_BYTES:
            raise Refused(TOTAL_BIG.format(mb=MAX_TOTAL_BYTES // (1024 * 1024)))
    first_real = checked[0][0]
    folder = _folder_of(first_real)
    if not os.path.isdir(folder):
        raise Refused(FOLDER_GONE.format(folder=folder))
    if not _inside_listed(folder):
        raise Refused(NOT_IN_A_FOLDER.format(name=os.path.basename(first_real)))
    if not os.access(folder, os.W_OK):
        raise Refused(CANNOT_WRITE.format(folder=folder))
    stem = Path(first_real).stem
    if to == "pdf":
        wanted = os.path.join(folder, stem + ".pdf")
        suffix = ".pdf"
    else:
        suffix = TARGETS[to][0]
        wanted = os.path.join(folder, stem + suffix)
    named = args.get("out") or args.get("output")
    if isinstance(named, str) and named.strip():
        out = os.path.abspath(named.strip())
        if not os.path.isdir(os.path.dirname(out)):
            raise Refused(FOLDER_GONE.format(folder=os.path.dirname(out)))
        if not _inside_listed(os.path.dirname(out)):
            raise Refused(NOT_IN_A_FOLDER.format(name=os.path.basename(out)))
        if os.path.exists(out):
            raise Refused(ALREADY_THERE.format(path=out))
        if os.path.normcase(out) in {os.path.normcase(c[0]) for c in checked}:
            raise Refused(SAME_PLACE.format(name=os.path.basename(out)))
        wanted = out
        out = wanted
    else:
        # `wanted` stays the FIRST choice (stem + suffix): convert() and the
        # card compare it with the name actually chosen, so a taken name makes
        # the sentence say "already exists ... a new name" rather than quietly
        # presenting the numbered file as the only plan.
        out = _new_name(folder, stem, suffix)
    said = _refusal_for_write(out)
    if said:
        raise Refused(said)
    flatten = False
    card = ""
    if to == "pdf":
        state = {"kind": "pdf", "paths": [c[0] for c in checked],
                 "out": out, "wanted": wanted,
                 "checks": [c[2] for c in checked],
                 "sniffs": [{"format": c[1]["format"]} for c in checked]}
        card = _card_pdf([c[0] for c in checked],
                         [c[1] for c in checked], out, wanted)
    else:
        sniffed = checked[0][1]
        # A JPEG cannot store transparency, so asking for JPEG IS asking for
        # the flatten; the card and the result both say "white" in words.
        flatten = bool(sniffed["alpha"]) and to in ("jpeg", "jpg")
        state = {"kind": "picture", "paths": [checked[0][0]], "to": to,
                 "out": out, "wanted": wanted, "checks": [checked[0][2]],
                 "sniffs": [{"format": sniffed["format"]}],
                 "flatten": flatten, "quality": QUALITY}
        card = _card_picture(checked[0][0], to, out, wanted, sniffed, flatten)
    return state, card


# --------------------------------------------------------------------------
#   convert(): after the card said yes - write exactly one NEW file
# --------------------------------------------------------------------------


def _write_new(final: str, temp: str) -> None:
    """Copy the child's temporary file to the destination, creating it with
    O_EXCL so an existing file can NEVER be replaced. The temporary file is
    always removed."""
    try:
        fd = os.open(final, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    except FileExistsError:
        raise Refused(EXISTS_MEANWHILE.format(path=final))
    except OSError as exc:                                    # noqa: BLE001
        raise Refused(WRITE_FAILED.format(why=type(exc).__name__))
    try:
        with os.fdopen(fd, "wb") as dest, open(temp, "rb") as src:
            while True:
                block = src.read(1024 * 1024)
                if not block:
                    break
                dest.write(block)
            dest.flush()
            try:
                os.fsync(dest.fileno())
            except OSError:
                pass
    except Exception as exc:                                  # noqa: BLE001
        try:
            os.unlink(final)
        except OSError:
            pass
        raise Refused(WRITE_FAILED.format(why=type(exc).__name__))
    finally:
        try:
            os.unlink(temp)
        except OSError:
            pass


def _temp_in(folder: str) -> str:
    fd, temp = tempfile.mkstemp(prefix=".jarvis-convert-", suffix=".tmp",
                                dir=folder)
    os.close(fd)
    return temp


def _unchanged(state: dict) -> bool:
    """Were the sources still exactly as the card showed them? False when one
    changed, vanished or grew past its bound - then nothing is written."""
    if len(state.get("paths") or []) != len(state.get("checks") or []):
        return False
    for path, check in zip(state["paths"], state["checks"]):
        try:
            st = os.stat(path)
        except OSError:
            return False
        if int(st.st_size) != int(check.get("size") or -1):
            return False
        if abs(float(st.st_mtime) - float(check.get("mtime") or 0.0)) > 0.001:
            return False
    return True


def _verify_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def _verify_picture(path: str) -> bool:
    Image = _pillow()
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:                                         # noqa: BLE001
        return False


def convert(state: dict, *, run_child: Optional[Callable[[dict], dict]] = None) -> dict:
    """Do the one conversion the card approved, and say exactly what happened.

    Always returns a dict, never raises: {"ok": True, "path", "words"/"said",
    ...} on success, {"ok": False, "error"} with ONE plain sentence otherwise.
    The source pictures are only ever READ; the destination is opened with
    O_EXCL so no existing file can be replaced.
    """
    if not isinstance(state, dict) or state.get("kind") not in ("pdf", "picture"):
        return {"ok": False, "error": "that conversion could not be worked out, "
                                      "so nothing was written."}
    out = str(state.get("out") or "")
    if not out:
        return {"ok": False, "error": "that conversion could not be worked out, "
                                      "so nothing was written."}
    if not _unchanged(state):
        return {"ok": False, "path": out,
                "error": CHANGED_MEANWHILE.format(path="a picture")}
    if os.path.exists(out):
        return {"ok": False, "path": out, "error": EXISTS_MEANWHILE.format(path=out)}
    folder = _folder_of(out)
    try:
        temp = _temp_in(folder)
    except OSError as exc:                                    # noqa: BLE001
        return {"ok": False, "error": WRITE_FAILED.format(why=type(exc).__name__)}
    run = run_child or _run_child
    try:
        if state["kind"] == "pdf":
            try:
                doc = run({"kind": "pdf", "inputs": list(state["paths"]),
                           "out": temp})
            except Refused as exc:
                return {"ok": False, "path": out, "error": str(exc)}
            except Exception:                                 # noqa: BLE001
                return {"ok": False, "path": out,
                        "error": CHILD_FAILED_PDF.format(what="those pictures")}
            if not doc.get("ok"):
                return {"ok": False, "path": out,
                        "error": CHILD_FAILED_PDF.format(what="those pictures")}
            pages = int(doc.get("pages") or 0)
            _write_new(out, temp)
            if not _verify_pdf(out):
                try:
                    os.unlink(out)
                except OSError:
                    pass
                return {"ok": False, "error": NOT_A_PDF_OUT}
            names = _sources_words(list(state["paths"]))
            truth = _pdf_copy_truth([{"format": s.get("format")}
                                     for s in state.get("sniffs") or []])
            return {"ok": True, "path": out, "pages": pages, "files": len(state["paths"]),
                    "what": "one PDF",
                    "said": (f"Made \"{out}\" - one PDF with {pages} page"
                             f"{'s' if pages != 1 else ''} from {names}. {truth} "
                             f"Nothing that already existed was changed."),
                    "words": (f"Made \"{out}\" from {names}.")}
        to = str(state.get("to") or "")
        spec = TARGETS.get(to)
        if spec is None:
            return {"ok": False, "error": BAD_TARGET.format(to=to)}
        fmt = FORMAT_WORDS.get(to, to.upper())
        try:
            doc = run({"kind": "picture", "input": state["paths"][0], "out": temp,
                       "format": spec[1], "quality": QUALITY,
                       "flatten": bool(state.get("flatten"))})
        except Refused as exc:
            return {"ok": False, "path": out, "error": str(exc)}
        except Exception:                                     # noqa: BLE001
            return {"ok": False, "path": out,
                    "error": CHILD_FAILED.format(what="that picture")}
        if not doc.get("ok"):
            return {"ok": False, "path": out,
                    "error": CHILD_FAILED.format(what="that picture")}
        _write_new(out, temp)
        if not _verify_picture(out):
            try:
                os.unlink(out)
            except OSError:
                pass
            return {"ok": False, "error": NOT_A_PICTURE_OUT}
        truth = (LOSSY_WORDS.format(fmt=fmt, quality=QUALITY)
                 if spec[2] else LOSSLESS_WORDS.format(fmt=fmt))
        flatten_words = (f" {FLATTEN_WORDS.format(fmt=fmt)}"
                         if state.get("flatten") else "")
        return {"ok": True, "path": out, "what": f"one {fmt} picture",
                "said": (f"Saved \"{out}\" - a copy of "
                         f"\"{os.path.basename(state['paths'][0])}\" as {fmt}. "
                         f"{truth}{flatten_words} The original picture is not "
                         f"changed."),
                "words": f"Saved \"{out}\"."}
    finally:
        try:
            if os.path.exists(temp):
                os.unlink(temp)
        except OSError:
            pass


def _reset_for_tests() -> None:
    """Nothing is held between calls; the name exists for the suites' habit."""
    return None
