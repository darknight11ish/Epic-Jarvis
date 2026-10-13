# MEASURED, 2026-10-13: the two picture readers, side by side

**A measurement, not a benchmark, and not a verdict.** It says how Windows' own
text recognition and RapidOCR differ on four pictures this repository draws
itself. It does **not** say which one is right, and it is **not** the owner's
screen text. Both of those limits are spelled out below, because the whole
point of this file is that the second reader may not ship as "better".

The reader is **OFF by default**. Nothing here changes that.

## What was run

```
py -3 backend/jarvis_ocr.py compare backend/test_files/ocr-bakeoff/*.png \
                                       backend/test_files/ocr-bakeoff/*.jpg
```

(the same numbers as `py -3 tools/ocr_bakeoff.py <pictures>`; that is a front
door onto the same code.)

- **A** = Windows' own text recognition, `Windows.Media.Ocr`, through the
  six `winrt-*` packages (the default).
- **B** = RapidOCR, the `rapidocr` package **3.10.0**, on **onnxruntime**.
- Machine: this PC, Windows, Python 3.12, processor only. RapidOCR's engine
  reported itself as *"RapidOCR on this PC's processor"*.
- The four pictures are **synthetic**: `tools/gen_ocr_bakeoff_images.py`
  draws them, so anyone can reproduce the run. They are **not the owner's
  screen pictures** - there are none of those in this repository, and the
  owner has not supplied any.

## The output, verbatim

```
Picture readers compared: 4 picture(s)
  A = Windows' own text recognition   (the default)
  B = RapidOCR (onnxruntime)

--- backend/test_files/ocr-bakeoff/dialog.png
  A windows : 5 line(s), 14 word(s), 14 with a position, 0.07s, confidence: not given by this reader
  B rapidocr: 5 line(s), 13 word(s), 13 with a position, 2.28s, confidence mean 1.000 min 1.000
  agreement: 10 word(s) both found; only A: docx, report-final.; only B: report-final.docx
  positions: 10 of 10 shared word(s) have both boxes on the same spot

--- backend/test_files/ocr-bakeoff/secret-key.png
  A windows : 3 line(s), 6 word(s), 6 with a position, 0.02s, confidence: not given by this reader
  B rapidocr: 3 line(s), 6 word(s), 6 with a position, 0.93s, confidence mean 1.000 min 1.000
  agreement: 5 word(s) both found; only A: sk-1ive-9f4a2b7c8d1e3f5a; only B: sk-live-9f4a2b7c8d1e3f5a
  positions: 5 of 5 shared word(s) have both boxes on the same spot

--- backend/test_files/ocr-bakeoff/small-grey.png
  A windows : 3 line(s), 11 word(s), 11 with a position, 0.02s, confidence: not given by this reader
  B rapidocr: 3 line(s), 11 word(s), 11 with a position, 0.79s, confidence mean 0.998 min 0.983
  agreement: 10 word(s) both found; only A: ah; only B: 4h
  positions: 10 of 10 shared word(s) have both boxes on the same spot

--- backend/test_files/ocr-bakeoff/phone-photo.jpg
  A windows : 3 line(s), 11 word(s), 11 with a position, 0.02s, confidence: not given by this reader
  B rapidocr: 3 line(s), 11 word(s), 11 with a position, 0.74s, confidence mean 1.000 min 1.000
  agreement: 10 word(s) both found
  positions: 10 of 10 shared word(s) have both boxes on the same spot

=== TOTALS ===
pictures read by both readers: 4/4
words both readers found: 35
boxes agreeing on the same spot: 35 of 35 comparable
```

(Timings move by a second or so between runs and mean nothing beyond "A is
much faster here". The first RapidOCR read in a process also loads its three
models, about a second.)

## What this DOES show

1. **Both readers read all four pictures, and neither lost a position.** Every
   word either found came with a box. 35 words were found by both, and on all
   35 the two boxes land on the same spot. So on this set the *positions* do
   not differ - which is the thing the second reader exists for.
2. **The two readers disagreed on four words, and on two of them RapidOCR read
   what was actually drawn:**
   - `report-final.docx` was drawn as one word; Windows split it into
     `report-final.` + `docx`, RapidOCR kept it whole.
   - `sk-live-9f4a2b7c8d1e3f5a` was drawn with a lower-case `l`; **Windows read
     the `l` as a digit `1`** (`sk-1ive-...`), RapidOCR read it correctly.
   - `4h` (in "Uptime 6d 4h") was read as `ah` by Windows, `4h` by RapidOCR.
   - On the 18px grey text both readers got every word right.
3. **RapidOCR gives a confidence per word** (mean 0.998-1.000, lowest 0.983 on
   the grey text). **Windows' own reader gives none at all** through the
   pywinrt path, so that column is RapidOCR's alone and the two cannot be
   compared on it.
4. **Windows' own reader is much faster here**: 0.02-0.07 s against
   RapidOCR's 0.74-2.28 s on the processor, an order of magnitude.

## What this does NOT show - read this before trusting anything above

- **It is not the owner's screen text.** These are four synthetic pictures with
  clean, high-contrast, horizontal text. Real screen text is smaller, busier,
  often over a picture, and sometimes rotated. Nothing here has been measured on
  the owner's own screenshots, because there are none in this repository.
- **Neither reader is checked against a hand-typed answer.** The comparison
  reports *agreement* and *difference*. Where they differ, this file says what
  was drawn only because the picture was drawn by a script that also says what
  it drew - that is evidence about these four pictures and no others. "RapidOCR
  read the key right here" is not "RapidOCR is more accurate".
- **Four pictures is not a sample.** One word going each way is a coincidence
  as much as a signal.
- **The timing is a single run on the processor, not a benchmark.** It was not
  repeated, and the graphics card was not used (RapidOCR's ONNX runtime is
  pinned to the processor here).
- **Windows' own reader has no per-word confidence**, so "which reader is more
  confident" cannot be asked at all.
- **The real gap the brief named was NOT reached.** The reason the second reader
  exists is that Windows' PowerShell fallback "gives no positions if its
  box-reading step fails, and a picture then cannot be cleaned". On this PC the
  in-process pywinrt reader answered, so **the fallback never ran** and this
  measurement says nothing about the case that motivated the work.

## What it means for the switch

The feature stays **off**. What was measured is agreement, not superiority:
on these four pictures both readers gave a position for every word, and while
RapidOCR read three hard words that Windows got wrong, it is roughly ten times
slower and the set is four pictures the repository draws itself. That is a
reason to keep the reader available and off, which is exactly what shipped.

**To turn it on** (after `py -3 -m pip install -r backend\requirements.txt`):

```
py -3 jarvis_ocr.py reader rapidocr
```

and back with `py -3 jarvis_ocr.py reader windows`. `py -3 jarvis_ocr.py`
alone prints which reader is in use and whether it works. Both apps show the
same thing on the Hardware screen, through `GET /api/second-card`.

**To measure on the owner's own pictures**, with real screenshots in a folder:

```
py -3 jarvis_ocr.py compare C:\path\to\screenshots\*.png
```
