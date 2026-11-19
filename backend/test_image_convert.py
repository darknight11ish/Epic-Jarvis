"""test_image_convert.py - pictures into ONE PDF, or one picture into another
format, with one approval card per new file.

    python3 backend/test_image_convert.py

What it proves, and each one is a way the feature could quietly change a file:

  1. THE PDF IS LOSSLESS. A JPEG put into a produced PDF still has its OWN
     bytes inside that PDF, byte for byte - this is the whole reason the
     feature uses img2pdf instead of Pillow's PDF writer, and the check looks
     for the input bytes in the output rather than trusting the docs.
  2. ONE PDF, SEVERAL PICTURES, IN ORDER. Two pictures of different shapes
     produce one file with two pages, and page 1 is the first picture.
  3. THE TRUTH ABOUT QUALITY. A PNG with transparency saved as JPEG is
     flattened onto WHITE and the sentence the owner reads says so; the same
     sentence says JPEG is LOSSY and the copy is not identical. A lossless
     target says lossless instead. One card's words say the same before the
     yes.
  4. A NON-PICTURE IS REFUSED BY CONTENT, NOT BY NAME. A text file called
     `photo.png` is refused in one plain sentence and nothing is written.
  5. NOTHING IS EVER OVERWRITTEN. An existing `a.pdf` is left with its exact
     old bytes, the new file gets a numbered name ("a (2).pdf") and the card
     says so; a target the caller named explicitly that already exists is
     REFUSED; and a file that appears at the chosen name while the card is up
     is refused too.
  6. THE SOURCES ARE NEVER CHANGED. Every source picture's sha256 is the same
     after the conversion as before it, and prepare() writes nothing at all.
  7. THE GATE. The tool maps `convert` to its OWN action (`convert_images`),
     both shipped settings copies carry that action's "ask" line, the
     published gate carries its tool->action and risk rows, and the module's
     prepare() refuses outright if the tier was loosened from "ask" - so a new
     file cannot be written with nobody asked.
  8. THE CHILD BOUNDARY. The conversion runs in a separate Python program
     (`-I -B -c`) with a scrubbed environment (a planted secret does not
     travel), a wall-clock timeout and a bounded answer, and the child program
     imports no network module.

Run:  python3 backend/test_image_convert.py
Needs Pillow, img2pdf and pikepdf - all in backend/requirements.txt, and CI
installs the versions backend/requirements.lock pins.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_image_convert.py", "jarvis_agent.py")

import jarvis_image_convert as M  # noqa: E402
import jarvis_agent as AG  # noqa: E402

try:
    from PIL import Image
except Exception:                                             # noqa: BLE001
    Image = None
try:
    import pikepdf
except Exception:                                             # noqa: BLE001
    pikepdf = None

PASSED, FAILED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-image-convert-"))


def check(name, cond, detail=""):
    ok = bool(cond)
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jpeg(name="a.jpg", size=(120, 60), color=(200, 30, 30), dpi=72):
    p = TMP / name
    im = Image.new("RGB", size, color)
    im.save(p, "JPEG", dpi=(dpi, dpi), quality=95)
    return p


def png(name="b.png", size=(60, 120), color=(20, 60, 200), mode="RGB"):
    p = TMP / name
    Image.new(mode, size, color).save(p, "PNG")
    return p


def png_transparent(name="alpha.png", size=(16, 16)):
    p = TMP / name
    Image.new("RGBA", size, (0, 0, 0, 0)).save(p, "PNG")
    return p


#: The folder-list seam: every path in this suite's own temp folder counts as
#: "on the owner's list", the same fake jarvis_documents.allowed_path that
#: test_media_read.py uses. The real rule is jarvis_documents' own and is not
#: re-implemented here.
_FAKE_ROOTS = None


class Allowed:
    def __enter__(self):
        import jarvis_documents as DOCS
        self.docs, self.old = DOCS, DOCS.allowed_path
        root = str(TMP)

        def allowed(path, roots=None):
            real = os.path.abspath(str(path))
            try:
                inside = os.path.commonpath(
                    [os.path.normcase(real), os.path.normcase(root)]) == os.path.normcase(root)
            except ValueError:
                return None
            return (real, root) if inside else None

        DOCS.allowed_path = allowed
        return self

    def __exit__(self, *exc):
        self.docs.allowed_path = self.old
        return False


def as_ask():
    """Run with the tier reader answering "ask" (what the shipped file says)."""
    class T:
        def __enter__(self):
            self.old = M._tier
            M._tier = lambda action: "ask"
            return self

        def __exit__(self, *exc):
            M._tier = self.old
            return False
    return T()


def convert(args):
    """prepare() then convert() as the agent does after the card said yes."""
    with Allowed(), as_ask():
        state, card = M.prepare(args)
    result = M.convert(state)
    return state, card, result


# ---------------------------------------------------------------------------
#   1 + 2. The PDF: the JPEG's own bytes, and several pictures in order
# ---------------------------------------------------------------------------


def t_a_jpegs_own_bytes_are_inside_the_pdf():
    if Image is None or pikepdf is None:
        check("Pillow and pikepdf are installed (the PDF checks need both)", False)
        return
    src = jpeg(size=(200, 100), dpi=72)
    _, card, result = convert({"action": "convert", "to": "pdf",
                               "paths": [str(src)]})
    check("the PDF conversion succeeded", result.get("ok") is True, result)
    if not result.get("ok"):
        return
    raw = src.read_bytes()
    pdf = Path(result["path"]).read_bytes()
    check("the produced file is a PDF", pdf[:5] == b"%PDF-", pdf[:16])
    check("the input JPEG's bytes are INSIDE the PDF, byte for byte",
          raw in pdf, f"{len(raw)} bytes looked for in {len(pdf)}")
    check("the card said the JPEG goes in byte for byte",
          "byte for byte" in card.lower(), card)
    check("the result said the same thing",
          "byte for byte" in str(result.get("said", "")).lower(), result.get("said"))


def t_two_pictures_make_one_pdf_with_two_pages_in_order():
    if Image is None or pikepdf is None:
        check("Pillow and pikepdf are installed (the page checks need both)", False)
        return
    wide = jpeg("wide.jpg", size=(160, 40), color=(10, 200, 10))
    tall = png("tall.png", size=(40, 160), color=(200, 10, 10))
    _, _, result = convert({"action": "convert", "to": "pdf",
                            "paths": [str(wide), str(tall)]})
    check("two pictures make one PDF", result.get("ok") is True, result)
    if not result.get("ok"):
        return
    with pikepdf.open(result["path"]) as pdf:
        pages = len(pdf.pages)
        box0 = [float(x) for x in pdf.pages[0].MediaBox]
        box1 = [float(x) for x in pdf.pages[1].MediaBox]
    check("the PDF has exactly two pages", pages == 2, pages)
    check("page 1 is the FIRST picture (wide), page 2 the second (tall)",
          (box0[2] - box0[0]) > (box0[3] - box0[1])
          and (box1[3] - box1[1]) > (box1[2] - box1[0]),
          (box0, box1))


# ---------------------------------------------------------------------------
#   3. The truth about quality, and flattening for JPEG
# ---------------------------------------------------------------------------


def t_a_transparent_png_to_jpeg_is_flattened_onto_white_and_says_so():
    if Image is None:
        check("Pillow is installed (the picture checks need it)", False)
        return
    src = png_transparent(size=(16, 16))
    before = sha(src)
    _, card, result = convert({"action": "convert", "to": "jpeg",
                               "paths": [str(src)]})
    check("the PNG-to-JPEG conversion succeeded", result.get("ok") is True, result)
    check("the source PNG was not changed", sha(src) == before)
    if not result.get("ok"):
        return
    said = str(result.get("said", ""))
    check("the sentence says the transparent parts were flattened onto white",
          "flattened onto white" in said.lower(), said)
    check("the card said it too", "flattened onto white" in card.lower(), card)
    check("the sentence says JPEG is LOSSY", "lossy" in said.lower(), said)
    check("the sentence says the copy is not identical",
          "not identical" in said.lower(), said)
    with Image.open(result["path"]) as im:
        rgb = im.convert("RGB")
        corner = rgb.getpixel((0, 0))
    check("the transparent corner is white in the JPEG, not black",
          all(abs(c - 255) <= 12 for c in corner), corner)


def t_a_lossless_target_says_lossless_and_keeps_every_pixel():
    if Image is None:
        check("Pillow is installed (the picture checks need it)", False)
        return
    src = png("exact.png", size=(20, 20), color=(12, 34, 56))
    _, card, result = convert({"action": "convert", "to": "tiff",
                               "paths": [str(src)]})
    check("the PNG-to-TIFF conversion succeeded", result.get("ok") is True, result)
    if not result.get("ok"):
        return
    check("the sentence says the target is lossless",
          "lossless" in str(result.get("said", "")).lower(), result.get("said"))
    check("the card says the target is lossless", "lossless" in card.lower(), card)
    with Image.open(src) as a, Image.open(result["path"]) as b:
        check("every pixel is the same in the lossless copy",
              list(a.convert("RGB").getdata()) == list(b.convert("RGB").getdata()))


def t_the_output_folder_check_asks_about_the_folder_itself():
    """The destination does not exist yet, so the folder rule is asked about
    the FOLDER. A probe file name inside it would be a bug waiting to happen:
    jarvis_documents.allowed_path refuses any path with a hidden component, so
    a dot-prefixed probe would refuse every conversion."""
    seen = []
    with Allowed() as fake:
        import jarvis_documents as DOCS
        old = DOCS.allowed_path

        def spy(path, roots=None):
            seen.append(str(path))
            return old(path, roots)

        DOCS.allowed_path = spy
        try:
            allowed = M._inside_listed(str(TMP))
        finally:
            DOCS.allowed_path = old
    check("a folder on the list is accepted for the new file", allowed is True)
    check("... and the rule was asked about the FOLDER itself",
          bool(seen) and os.path.abspath(seen[-1]) == os.path.abspath(str(TMP)),
          seen[-1:] if seen else seen)
    check("... never about a made-up file name inside it (a dot-prefixed probe "
          "would be refused by the hidden-folder rule)",
          all(os.path.basename(x) != ".jarvis-convert-probe" for x in seen), seen)


# ---------------------------------------------------------------------------
#   4. Not a picture, whatever the name says
# ---------------------------------------------------------------------------


def t_a_text_file_called_png_is_refused():
    fake = TMP / "pretend.png"
    fake.write_bytes(b"this is not a picture, it is a text file\n")
    with Allowed(), as_ask():
        try:
            M.prepare({"action": "convert", "to": "pdf", "paths": [str(fake)]})
        except ValueError as exc:
            said = str(exc)
            check("a non-picture called .png is refused in one plain sentence",
                  "not a picture" in said.lower(), said)
            check("the refusal does not invent a card",
                  "approve" not in said.lower() and "card" not in said.lower(), said)
        else:
            check("a non-picture called .png is refused in one plain sentence", False)
    check("... and nothing new appeared beside it",
          sorted(p.name for p in TMP.glob("pretend*")) == ["pretend.png"],
          sorted(p.name for p in TMP.glob("pretend*")))


# ---------------------------------------------------------------------------
#   5. Never overwrite
# ---------------------------------------------------------------------------


def t_an_existing_target_is_never_overwritten():
    if Image is None:
        check("Pillow is installed (the picture checks need it)", False)
        return
    src = jpeg("keep.jpg", size=(30, 30))
    old = TMP / "keep.pdf"
    old.write_bytes(b"%PDF-1.4\nOLD FILE, MUST SURVIVE\n")
    _, card, result = convert({"action": "convert", "to": "pdf",
                               "paths": [str(src)]})
    check("the conversion still succeeded", result.get("ok") is True, result)
    check("the existing file's bytes are untouched",
          old.read_bytes() == b"%PDF-1.4\nOLD FILE, MUST SURVIVE\n", old.read_bytes()[:40])
    check("the card says the name was taken and a new one was used",
          "already exists" in card.lower() and "new name" in card.lower(), card)
    new = Path(str(result.get("path") or ""))
    check("the new file got the numbered name \"keep (2).pdf\"",
          new.name == "keep (2).pdf", new.name)
    check("the new file is a real PDF", new.read_bytes()[:5] == b"%PDF-", new.name)


def t_an_explicit_existing_target_is_refused():
    if Image is None:
        check("Pillow is installed (the picture checks need it)", False)
        return
    src = jpeg("named.jpg", size=(10, 10))
    taken = TMP / "taken.pdf"
    taken.write_bytes(b"taken")
    with Allowed(), as_ask():
        try:
            M.prepare({"action": "convert", "to": "pdf", "paths": [str(src)],
                       "out": str(taken)})
        except ValueError as exc:
            check("a path the caller named that already exists is REFUSED",
                  "already a file" in str(exc).lower()
                  or "already there" in str(exc).lower(), str(exc))
        else:
            check("a path the caller named that already exists is REFUSED", False)
    check("the named file still holds its old bytes", taken.read_bytes() == b"taken")


def t_a_file_that_appears_while_the_card_is_up_is_refused():
    if Image is None:
        check("Pillow is installed (the picture checks need it)", False)
        return
    src = jpeg("race.jpg", size=(10, 10))
    with Allowed(), as_ask():
        state, card = M.prepare({"action": "convert", "to": "pdf",
                                 "paths": [str(src)]})
    Path(state["out"]).write_bytes(b"someone else wrote here first")
    result = M.convert(state)
    check("a target that appeared while the card was up is refused",
          result.get("ok") is False, result)
    check("... and the file that appeared is NOT replaced",
          Path(state["out"]).read_bytes() == b"someone else wrote here first")
    check("the refusal says nothing was overwritten",
          "overwritten" in str(result.get("error", "")).lower(), result.get("error"))


# ---------------------------------------------------------------------------
#   6. The sources are only ever read
# ---------------------------------------------------------------------------


def t_prepare_writes_nothing_and_convert_never_changes_a_source():
    if Image is None:
        check("Pillow is installed (the picture checks need it)", False)
        return
    src = jpeg("readonly.jpg", size=(24, 24))
    before = sha(src)
    listing = sorted(p.name for p in TMP.iterdir())
    with Allowed(), as_ask():
        state, card = M.prepare({"action": "convert", "to": "png",
                                 "paths": [str(src)]})
    after = sorted(p.name for p in TMP.iterdir())
    check("prepare() wrote nothing at all", listing == after,
          (listing[-3:], after[-3:]))
    result = M.convert(state)
    check("the picture conversion succeeded", result.get("ok") is True, result)
    check("the source picture's bytes are unchanged", sha(src) == before)
    check("the result says the original is not changed",
          "original" in str(result.get("said", "")).lower(), result.get("said"))


# ---------------------------------------------------------------------------
#   7. The gate: its own ask action, and a belt under the card
# ---------------------------------------------------------------------------


def t_the_conversion_is_asked_under_its_own_ask_action():
    check("the module's action name is convert_images",
          M.ACTION == "convert_images", M.ACTION)
    check("the tool names the same action",
          getattr(AG, "FILES_CONVERT_ACTION", "") == M.ACTION,
          getattr(AG, "FILES_CONVERT_ACTION", None))
    tool = AG.TOOLS["my_files"]
    check("my_files offers the convert action",
          "convert" in tool.parameters["properties"]["action"]["enum"])
    check("... and its gate lookup name is the conversion action, not file_read",
          tool.gate_lookup_name({"action": "convert"}) == M.ACTION,
          tool.gate_lookup_name({"action": "convert"}))
    check("... while every other action of the tool still asks under file_read",
          tool.gate_lookup_name({"action": "read"}) == "file_read",
          tool.gate_lookup_name({"action": "read"}))
    args, problem = AG.check_call("my_files",
                                  {"action": "convert", "to": "pdf",
                                   "paths": [str(TMP / "x.jpg")]},
                                  {"my_files"}, AG.TOOLS)
    check("check_call accepts the convert shape", problem is None and isinstance(args, dict),
          problem)
    for path in (REPO / "backend" / "rebuilt" / "jarvis-framework.toml",
                 REPO / "jarvis-backend" / "jarvis-framework.toml"):
        text = path.read_text(encoding="utf-8")
        check(f"{path.parent.parent.name}/{path.name} carries the action's ask line",
              "convert_images" in text and
              any(line.split("=")[-1].strip() == '"ask"'
                  for line in text.splitlines() if line.startswith("convert_images")),
              [line for line in text.splitlines() if line.startswith("convert_images")])
    gate = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the published gate maps the action name to itself",
          '"convert_images": "convert_images"' in gate)
    check("the published gate carries the action's own risk row",
          '"convert_images": ("yes", "local"' in gate)
    check("the published gate keeps a denial about that one file",
          gate.count('"convert_images"') >= 4, gate.count('"convert_images"'))


def t_a_loosened_tier_is_refused_before_anything_is_done():
    if Image is None:
        check("Pillow is installed (the picture checks need it)", False)
        return
    src = jpeg("loose.jpg", size=(10, 10))
    before = sha(src)
    with Allowed():
        old = M._tier
        M._tier = lambda action: "auto"
        try:
            try:
                M.prepare({"action": "convert", "to": "pdf", "paths": [str(src)]})
            except ValueError as exc:
                said = str(exc)
                check("a loosened tier is refused, so a file write cannot be cardless",
                      "ask" in said.lower() and "refused" in said.lower(), said)
            else:
                check("a loosened tier is refused, so a file write cannot be cardless",
                      False)
        finally:
            M._tier = old
    check("nothing was made while the tier was loosened",
          sorted(p.name for p in TMP.glob("loose*")) == ["loose.jpg"],
          sorted(p.name for p in TMP.glob("loose*")))
    check("the source is untouched", sha(src) == before)


# ---------------------------------------------------------------------------
#   8. The child-program boundary
# ---------------------------------------------------------------------------


def t_the_child_gets_a_scrubbed_environment_and_a_clock():
    os.environ["JARVIS_TEST_LEAKED_SECRET"] = "do-not-pass-me-on"
    try:
        env = M._child_env()
    finally:
        os.environ.pop("JARVIS_TEST_LEAKED_SECRET", None)
    check("the child's environment is scrubbed: a planted secret does not travel",
          "JARVIS_TEST_LEAKED_SECRET" not in env, sorted(env)[:8])
    check("the child's environment still carries what Windows needs to start",
          not env or any(name.upper() in ("PATH", "SYSTEMROOT", "WINDIR")
                         for name in env), sorted(env)[:8])
    check("the child program imports no network module",
          not any(word in M._CHILD for word in ("http", "urllib", "socket", "requests")),
          [w for w in ("http", "urllib", "socket", "requests") if w in M._CHILD])

    seen = {}

    class FakeProc:
        returncode = 0
        stdout = b'{"ok": true, "pages": 1}'

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["timeout"] = kwargs.get("timeout")
        seen["env"] = kwargs.get("env")
        seen["input"] = kwargs.get("input")
        return FakeProc()

    old = M.subprocess.run
    M.subprocess.run = fake_run
    try:
        doc = M._run_child({"kind": "pdf", "inputs": [], "out": os.devnull})
    finally:
        M.subprocess.run = old
    check("the child is a separate, isolated Python program (-I -B -c)",
          seen["argv"][:4] == [sys.executable, "-I", "-B", "-c"], seen["argv"][:4])
    check("the child is given a wall-clock timeout",
          float(seen["timeout"] or 0) == M.CHILD_TIMEOUT, seen["timeout"])
    check("the child is given the scrubbed environment",
          isinstance(seen["env"], dict)
          and "JARVIS_TEST_LEAKED_SECRET" not in seen["env"], sorted((seen["env"] or {}))[:8])
    check("the child's answer is read back as JSON", doc.get("pages") == 1, doc)


def t_a_missing_part_is_a_plain_refusal_not_a_crash():
    old = M._pillow
    M._pillow = lambda: (_ for _ in ()).throw(M.Refused(M.NO_PILLOW))
    try:
        try:
            M.sniff(str(TMP / "whatever.png"))
        except M.Refused as exc:
            check("a missing picture library is one plain refusal",
                  "Pillow" in str(exc) and "nothing was" in str(exc), str(exc))
        else:
            check("a missing picture library is one plain refusal", False)
    finally:
        M._pillow = old


def main() -> int:
    functions = [t_a_jpegs_own_bytes_are_inside_the_pdf,
                 t_two_pictures_make_one_pdf_with_two_pages_in_order,
                 t_a_transparent_png_to_jpeg_is_flattened_onto_white_and_says_so,
                 t_a_lossless_target_says_lossless_and_keeps_every_pixel,
                 t_a_text_file_called_png_is_refused,
                 t_the_output_folder_check_asks_about_the_folder_itself,
                 t_an_existing_target_is_never_overwritten,
                 t_an_explicit_existing_target_is_refused,
                 t_a_file_that_appears_while_the_card_is_up_is_refused,
                 t_prepare_writes_nothing_and_convert_never_changes_a_source,
                 t_the_conversion_is_asked_under_its_own_ask_action,
                 t_a_loosened_tier_is_refused_before_anything_is_done,
                 t_the_child_gets_a_scrubbed_environment_and_a_clock,
                 t_a_missing_part_is_a_plain_refusal_not_a_crash]
    for fn in functions:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
