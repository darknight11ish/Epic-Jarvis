"""jarvis_ocr.py - reading the words in a picture, on this PC, with Windows'
own text recognition.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py).
No patch: jarvis_agent.py calls it, and jarvis_second_card.status() says
whether it works, for both apps.

THE OWNER'S DECISION (CLAUDE.md, 2026-09-26, the cutting-edge "Quick
wins"): "reading the text in a screenshot on the PC (marked as outside
text)". The feasibility audit's I14 adds HOW: the research's plan would
have put the words into the owner's own typed message, where they would
have counted as the owner's words. Here the BACKEND reads them and adds
them itself, as a part of its own that is outside text (jarvis_agent
with_picture_text): the conversation is marked as having read outside text,
the learner never sees them, and nothing an app sends can make them count
as the owner's.

WHEN. A picture in the newest message, on a turn answered by the model on
THIS PC (never a cloud lane - a turn with a picture never leaves the PC,
jarvis_router), when that model cannot see pictures and the second card's
picture model is not answering it. Automatic: there is no switch (the
feasibility audit's Overwhelm guardrail) - the marking says what happened.

HOW. Windows' built-in text recognition (Windows.Media.Ocr), no download of
any model and nothing that can reach the internet. Two ways in, tried in this
order:
  1. IN THIS PROGRAM (added 2026-09-29, screen safety): the `winrt` packages
     (pywinrt, MIT - backend/requirements.txt) call Windows' reader directly.
     No new program is started for each picture. The idea is that of the
     `winocr` package (MIT; a few lines: a picture goes into a Windows
     software bitmap, which the OcrEngine reads); the package itself is NOT
     used, above all not its `serve()`, which opens a web server open to
     the whole network.
  2. THROUGH WINDOWS POWERSHELL 5.1 (the way it always worked), when those
     packages are not installed or fail: the script is FIXED text below
     (_SCRIPT), started by its full system path (never a `powershell` found
     on PATH).
Either way the picture is handed over in memory - never written to disk - and
the answer is the lines of text it found AND where each word sits in the
picture (left, top, width, height, in pixels): the position is what lets
jarvis_secrets.py black out a secret. It uses the languages of the owner's
Windows profile; with none that Windows can read, it says so plainly
(NO_LANGUAGE).

HOW MUCH. At most MAX_CHARS characters - about 1,500 tokens by Jarvis's own
counter (3 characters a token, jarvis_agent.estimate_tokens) - and when
more was found, the part says how much was left out (the feasibility
audit's Hardware guardrail: on an 8 GB card a whole screen of text would
push the conversation out without telling anyone).

A SECOND READER, OFF BY DEFAULT (added 2026-10-13). Windows' reader above
stays the default and stays; a second one - RapidOCR (Apache-2.0), the
`rapidocr` package, whose ONNX models ship inside its wheel - can be chosen
instead, and is OFF until the owner turns it on with
`py -3 jarvis_ocr.py reader rapidocr`. WHY IT EXISTS: the docstring above
already admits the gap - PowerShell "gives no positions if its box-reading
step fails, and a picture then cannot be cleaned". RapidOCR always answers
with a box and a confidence for every word, so the black-out always has what
it needs. WHY IT IS OFF: nothing yet shows it BEATS Windows' own reader on
the owner's screen text, and this project does not ship an unmeasured
"better" (CLAUDE.md). `py -3 jarvis_ocr.py compare <pictures>` is the
measurement, and docs/MEASURED-2026-10-13-ocr-two-readers.md records what it
actually said. It runs on onnxruntime (already shipped here) - never
RapidOCR's PyTorch path - and takes no `[rtl]` extra, so python-bidi is not
pulled in.

NOT CHECKED HERE (no Windows in the dev container): the PowerShell half
itself, and the real Windows call. Everything around them - the picture read
out of the message, the cap, the words the model gets, the outside-text
marking, the choice of reader and the shape RapidOCR's answer is turned into
- is tested with a stand-in engine (backend/test_picture_text.py,
backend/test_ocr_words.py). The real rapidocr package IS exercised where it
is installed: backend/test_ocr_words.py reads a picture it draws itself and
checks each word's box lands where the word was drawn.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

ENGINE = "Windows' own text recognition"

#: The second reader (2026-10-13). OFF by default: nothing yet shows it beats
#: Windows' own reader on this owner's screen text (CLAUDE.md).
RAPIDOCR = "RapidOCR (onnxruntime)"

#: The two names WRITER accepts, and what the settings file holds.
READERS = ("windows", "rapidocr")
DEFAULT_READER = "windows"

#: About 1,500 tokens by jarvis_agent.estimate_tokens (3 characters a token).
MAX_CHARS = 4500

#: The biggest picture it reads, after base64 (the backend refuses a request
#: over 4 MiB anyway).
MAX_BYTES = 4 * 1024 * 1024

#: How long Windows gets to read one picture.
TIMEOUT_S = 30.0

NOT_WINDOWS = "Reading the words in a picture needs Windows' own text recognition, and this is not Windows."
NO_POWERSHELL = "Windows PowerShell was not found on this PC, so the words in a picture cannot be read."
NO_LANGUAGE = ("Windows has no text recognition for your language installed. In Settings -> Time & "
               "language -> Language & region, add your language again with its optional "
               "features (they include Optical character recognition), then restart Jarvis.")
#: Said by whichever reader could not read it. It does NOT name the reader:
#: Windows' name here would be a lie the moment RapidOCR is the one that
#: answered (and the reverse), and the app has no way to tell which is in use
#: from this sentence alone - POST /api/second-card says that separately.
TOO_BIG = "The picture is too big to read the words in."
FAILED = "Jarvis could not read the words in the picture."
TOO_SLOW = "Jarvis took too long to read the words in the picture."

#: Said when the chosen reader is RapidOCR and it is not installed here. The
#: one line that puts it there, and where the switch is.
NO_RAPIDOCR = ("RapidOCR is not installed on this PC, so the words in a picture cannot be read. "
               "Install it with: py -3 -m pip install -r backend\\requirements.txt")
#: Said when RapidOCR is installed but the models in its wheel will not load,
#: or a read raised. Cached for this process, as NO_LANGUAGE is.
RAPIDOCR_BROKEN = ("RapidOCR is installed but would not read the picture, so the words in a picture "
                   "cannot be read.")
#: RapidOCR's own ceiling: how long it gets with one picture. Generous on
#: purpose - the first read loads its three models - and NOT a measurement of
#: how long it takes: `py -3 jarvis_ocr.py compare <pictures>` prints that,
#: and docs/MEASURED-2026-10-13-ocr-two-readers.md records what it printed.
RAPIDOCR_TIMEOUT_S = 60.0
#: The most picture RapidOCR will be handed, in pixels. A 4K screen is 8.3 M;
#: a picture bigger than this is refused rather than left to eat the machine.
RAPIDOCR_MAX_PIXELS = 40_000_000

#: The one PowerShell script. Fixed text: nothing from the picture, the
#: model or an app is ever put into it. The picture comes on standard input.
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Say($o) { [Console]::Out.Write(($o | ConvertTo-Json -Compress -Depth 6)) }
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
  $null = [Windows.Foundation.IAsyncOperation`1, Windows.Foundation, ContentType = WindowsRuntime]
  $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
  $null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
  $awaiter = [WindowsRuntimeSystemExtensions].GetMember('GetAwaiter') | Where-Object { $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
  function Await($op, [Type]$type) { $awaiter.MakeGenericMethod($type).Invoke($null, @($op)).GetResult() }
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  if ($null -eq $engine) { Say @{ ok = $false; why = 'no_language' }; exit 0 }
  $ms = New-Object System.IO.MemoryStream
  [Console]::OpenStandardInput().CopyTo($ms)
  $ms.Position = 0
  $stream = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($ms)
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $max = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
  if ($decoder.PixelWidth -gt $max -or $decoder.PixelHeight -gt $max) { Say @{ ok = $false; why = 'too_big' }; exit 0 }
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $lines = @($result.Lines | ForEach-Object { $_.Text })
  $boxes = @()
  try {
    $boxes = @(foreach ($ln in $result.Lines) {
      $ws = @(foreach ($wd in $ln.Words) { $r = $wd.BoundingRect; @{ t = $wd.Text; x = [double]$r.X; y = [double]$r.Y; w = [double]$r.Width; h = [double]$r.Height } })
      @{ t = $ln.Text; w = $ws }
    })
  } catch { $boxes = @() }
  Say @{ ok = $true; lines = $lines; boxes = $boxes; width = [int]$bitmap.PixelWidth; height = [int]$bitmap.PixelHeight }
} catch {
  Say @{ ok = $false; why = 'failed'; error = $_.Exception.GetType().Name }
}
"""


def _powershell() -> Optional[str]:
    """Windows PowerShell 5.1 by its full system path, or None."""
    if os.name != "nt":
        return None
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    path = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return path if os.path.isfile(path) else None


#: What the last real read said about the engine, in this process: a PC with
#: no text-recognition language is said to be unable until Jarvis restarts.
_LAST: dict = {"why": ""}


# --------------------------------------------------------------------------
#   Which of the two readers answers (2026-10-13). A file beside every other
#   switch here (~/.openjarvis/ocr-reader.json), read fresh on every picture,
#   OFF unless it says otherwise - the same shape and the same fail-closed
#   direction as jarvis_screen_picture.settings(). Not an approval card: both
#   readers are local and neither loosens anything, so there is nothing for a
#   card to decide. It is a setting ON the PC, and it reaches no route of its
#   own: both apps already see which reader is in use through
#   jarvis_second_card._picture_text() (GET /api/second-card, `engine`).
# --------------------------------------------------------------------------

#: How long the settings file may be kept before it is read again, in seconds.
#: 0 means "read it every time", which is what the tests want.
_SETTINGS_TTL_S = 5.0
_SETTINGS_CACHE: dict = {"reader": DEFAULT_READER, "at": 0.0, "why": ""}

#: Set only while a measurement runs: the reader to answer with, WITHOUT
#: reading or writing the owner's settings file at all. None the rest of the
#: time, which is every moment Jarvis is actually working.
_MEASURE_OVERRIDE: Optional[str] = None


def _config_dir() -> Path:
    """The same folder the other switches here use, found the same way."""
    try:
        import jarvis_framework as fw
        return Path(fw.CONFIG_DIR)
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "ocr-reader.json"


def _read_settings() -> dict:
    """{"reader", "why"}. No file, or one that never had "reader": Windows -
    the default, and the only reader that was ever there before. A file that
    cannot be read, is not JSON, or names a reader that is not one of the two:
    Windows, and `why` says so. Never raises, and never guesses at a reader."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"reader": DEFAULT_READER, "why": ""}
    except OSError as exc:
        return {"reader": DEFAULT_READER,
                "why": f"the picture-reader settings file could not be read "
                       f"({type(exc).__name__}), so Windows' own reader is used"}
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {"reader": DEFAULT_READER,
                "why": "the picture-reader settings file is damaged, so Windows' own reader is "
                       "used. Turn the other one on again to rewrite it"}
    chosen = doc.get("reader", DEFAULT_READER)
    if not isinstance(chosen, str) or chosen.strip().lower() not in READERS:
        return {"reader": DEFAULT_READER,
                "why": f"the picture-reader settings file names a reader that is not one of "
                       f"{' or '.join(READERS)}, so Windows' own reader is used"}
    return {"reader": chosen.strip().lower(), "why": ""}


def reader() -> dict:
    """{"reader", "why"} - which reader answers the next picture. Cached for
    _SETTINGS_TTL_S so a screenful of pictures reads the file once."""
    if _MEASURE_OVERRIDE is not None:
        return {"reader": _MEASURE_OVERRIDE, "why": ""}
    now = time.monotonic()
    if _SETTINGS_TTL_S and now - float(_SETTINGS_CACHE.get("at") or 0.0) < _SETTINGS_TTL_S:
        return {"reader": _SETTINGS_CACHE["reader"], "why": _SETTINGS_CACHE.get("why", "")}
    got = _read_settings()
    _SETTINGS_CACHE.update({"reader": got["reader"], "why": got["why"], "at": now})
    return got


def set_reader(name: str) -> dict:
    """Write the switch. Refuses anything that is not one of READERS, so a
    typo can never leave the file naming a reader that does not exist."""
    want = str(name or "").strip().lower()
    if want not in READERS:
        raise ValueError(f"reader must be one of {' or '.join(READERS)}, not {name!r}")
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    # A plain file object rather than Path.write_text: this module's own test
    # forbids the writing helpers, because the PICTURE must never be written
    # to disk. The switch is not the picture, and this is the one place that
    # writes anything at all.
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"reader": want}, indent=1))
    os.replace(tmp, p)
    _SETTINGS_CACHE.update({"at": 0.0})
    return {"reader": want, "why": ""}


def using_rapidocr() -> bool:
    """Is the second reader the chosen one? Read fresh; never raises."""
    try:
        return reader()["reader"] == "rapidocr"
    except Exception:
        return False


class _NoRapid(Exception):
    """The rapidocr package is not installed (or would not load)."""


# --------------------------------------------------------------------------
#   The in-process reader (pywinrt) - the idea of the `winocr` package (MIT),
#   its few lines of Windows calls, without its server. NOT RUN in the
#   development container (no Windows): every name below is checked against
#   the packages' own type files (winrt-Windows.Media.Ocr 3.2.1,
#   winrt-Windows.Graphics.Imaging 3.2.1, winrt-Windows.Storage.Streams 3.2.1)
#   and backend/test_ocr_words.py drives everything around them with
#   stand-ins; the real calls are the owner's-PC test (backend/README.md).
# --------------------------------------------------------------------------

class _NoWinrt(Exception):
    """The pywinrt packages are not installed (or would not load)."""


_WINRT: dict = {}


def _winrt_modules() -> tuple:
    """(OcrEngine, BitmapDecoder, BitmapPixelFormat, BitmapAlphaMode,
    InMemoryRandomAccessStream, DataWriter, Buffer), imported once. Raises
    _NoWinrt when any of the six pywinrt packages is missing: the import of
    winrt.windows.foundation (and .collections, .globalization) is what makes
    Windows' asynchronous calls awaitable."""
    if "mods" in _WINRT:
        return _WINRT["mods"]
    if os.name != "nt" or _WINRT.get("missing"):
        raise _NoWinrt()
    try:
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapDecoder, BitmapPixelFormat
        from winrt.windows.storage.streams import Buffer, DataWriter, InMemoryRandomAccessStream
        import winrt.windows.foundation  # noqa: F401
        import winrt.windows.foundation.collections  # noqa: F401
        import winrt.windows.globalization  # noqa: F401
    except Exception:
        _WINRT["missing"] = True
        raise _NoWinrt()
    _WINRT["mods"] = (OcrEngine, BitmapDecoder, BitmapPixelFormat, BitmapAlphaMode,
                      InMemoryRandomAccessStream, DataWriter, Buffer)
    return _WINRT["mods"]


def winrt_usable() -> bool:
    """Are the pywinrt packages here? Cached; starts nothing."""
    try:
        _winrt_modules()
        return True
    except _NoWinrt:
        return False


def lines_from_result(result) -> list:
    """Windows' OcrResult (or anything shaped like it) as [{"text", "words":
    [{"text", "left", "top", "width", "height"}]}]. Pure: tested with
    stand-ins."""
    out = []
    for ln in result.lines:
        words = []
        for w in ln.words:
            r = w.bounding_rect
            words.append({"text": str(w.text), "left": float(r.x), "top": float(r.y),
                          "width": float(r.width), "height": float(r.height)})
        out.append({"text": str(ln.text), "words": words})
    return out


def _winrt_read(image: bytes, want_pixels: bool) -> dict:
    """{"ok", "lines", "size", ["pixels": (BGRA bytes, w, h)]} or {"ok":
    False, "why": "no_language"|"too_big"}. Raises _NoWinrt when the packages
    are missing, asyncio.TimeoutError when Windows is too slow, anything else
    when a Windows call fails (the caller then uses PowerShell)."""
    (OcrEngine, BitmapDecoder, BitmapPixelFormat, BitmapAlphaMode,
     InMemoryRandomAccessStream, DataWriter, Buffer) = _winrt_modules()

    async def go() -> dict:
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(image)
        await writer.store_async()
        writer.detach_stream()             # the writer must not close the picture's stream
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        w, h = int(decoder.pixel_width), int(decoder.pixel_height)
        limit = int(OcrEngine.max_image_dimension)
        if w > limit or h > limit:
            return {"ok": False, "why": "too_big"}
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return {"ok": False, "why": "no_language"}
        bitmap = await decoder.get_software_bitmap_converted_async(
            BitmapPixelFormat.BGRA8, BitmapAlphaMode.PREMULTIPLIED)
        result = await engine.recognize_async(bitmap)
        out = {"ok": True, "lines": lines_from_result(result), "size": (w, h)}
        if want_pixels:
            try:
                size = w * h * 4
                buf = Buffer(size)
                buf.length = size
                bitmap.copy_to_buffer(buf)
                out["pixels"] = (bytes(memoryview(buf))[:size], w, h)
            except Exception:
                pass                       # the picture then cannot be cleaned: fail closed
        return out

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(asyncio.wait_for(go(), TIMEOUT_S))
    finally:
        loop.close()


# --------------------------------------------------------------------------
#   The second reader: RapidOCR (Apache-2.0), the `rapidocr` package, which
#   bundles PaddleOCR's detection/recognition models converted to ONNX and
#   runs them on onnxruntime - the engine this project already ships. NEVER
#   RapidOCR's PyTorch path (requirements.txt records that this project
#   deliberately got off PyTorch), and NEVER its `[rtl]` extra, which pulls
#   python-bidi that nothing here needs. The models are INSIDE the wheel
#   (rapidocr/models/*.onnx), so this is offline after one install: checked
#   on 2026-10-13 with every socket call made to raise.
#
#   NOT RUN in the development container where it is not installed: the
#   import is inside a `try` and everything above it is stand-in-testable.
#   Where the package IS present (the owner's PC, and a machine that has run
#   `pip install rapidocr`), backend/test_ocr_words.py reads a picture it
#   draws itself and checks that every word box lands on the word.
# --------------------------------------------------------------------------

class _NoRapid(Exception):
    """The rapidocr package is not installed (or would not load)."""


#: {"cls": the RapidOCR class} once imported, or {"missing": True}.
_RAPID: dict = {}

#: The first read that failed, in this process: a wheel whose models will not
#: load is said to be broken until Jarvis restarts, rather than retried (and
#: made to load 20 MB of ONNX) for every picture.
_RAPID_LAST: dict = {"why": ""}

#: One picture at a time. onnxruntime is already thread-safe; this keeps a
#: screenful of pictures from loading three models at once.
_RAPID_LOCK = threading.Lock()

#: The two engine names RapidOCR offers that this project must never use, and
#: why: CLAUDE.md and backend/requirements.txt record that this project
#: deliberately got off PyTorch, and the others are not the shipped engine.
_FORBIDDEN_ENGINES = ("pytorch", "torch", "paddle", "openvino", "tensorrt", "mnn")


def _rapidocr_class():
    """rapidocr.RapidOCR, imported once. Raises _NoRapid when the package is
    not here. Nothing else of RapidOCR is imported: its CLI, its downloader
    and its visualiser are not used, so the visualiser's font - which is NOT
    in the wheel and which RapidOCR fetches from the internet on first use -
    is never asked for."""
    if "cls" in _RAPID:
        return _RAPID["cls"]
    if _RAPID.get("missing"):
        raise _NoRapid()
    try:
        from rapidocr import RapidOCR
    except Exception:
        _RAPID["missing"] = True
        raise _NoRapid()
    _RAPID["cls"] = RapidOCR
    return RapidOCR


def rapidocr_usable() -> bool:
    """Is the rapidocr package here? Cached; starts nothing, reads no model."""
    try:
        _rapidocr_class()
        return True
    except _NoRapid:
        return False


def _engine_type_enum():
    """RapidOCR's own EngineType, from wherever that version keeps it, or
    None. Its parameter checker refuses a plain string ("The value of
    Det.engine_type must be Enum Type"), so the name has to be its enum."""
    for where in ("rapidocr.utils.typings", "rapidocr.utils", "rapidocr"):
        try:
            mod = __import__(where, fromlist=["EngineType"])
            got = getattr(mod, "EngineType", None)
            if got is not None:
                return got
        except Exception:
            continue
    return None


def _rapid_engine():
    """The RapidOCR instance, built once and kept (its three models load on
    the first read). Raises _NoRapid, or anything the first load raises.

    The engine is onnxruntime, named out loud rather than left to RapidOCR's
    default, and then CHECKED on the built object: a later RapidOCR that moved
    its default would otherwise put this on torch or openvino without a word,
    and this project got off PyTorch on purpose."""
    if "engine" in _RAPID:
        return _RAPID["engine"]
    cls = _rapidocr_class()
    params = {
        "EngineConfig.onnxruntime.use_cuda": False,
        "EngineConfig.onnxruntime.use_dml": False,
        # A box AND a confidence for every word: the whole reason the second
        # reader exists.
        "Global.return_word_box": True,
        # Quiet: RapidOCR logs a line per model at INFO.
        "Global.log_level": "error",
    }
    enum = _engine_type_enum()
    if enum is not None:
        try:
            onnx = enum("onnxruntime")
        except Exception:
            onnx = None
        if onnx is not None:
            params["Det.engine_type"] = onnx
            params["Rec.engine_type"] = onnx
            params["Cls.engine_type"] = onnx
    eng = cls(params=params)
    for part in ("text_det", "text_rec", "text_cls"):
        got = _loaded_engine_type(getattr(eng, part, None))
        if got and any(bad in got for bad in _FORBIDDEN_ENGINES):
            raise RuntimeError(f"RapidOCR loaded {part} on {got!r}, which this project does not use")
    _RAPID["engine"] = eng
    return eng


def _loaded_engine_type(part) -> str:
    """The engine a detector/recogniser/classifier was built with, lowercased,
    or "" when it cannot be read. A part that has not been built yet (RapidOCR
    loads each one lazily) answers ""."""
    if part is None:
        return ""
    try:
        cfg = getattr(part, "cfg", None)
        for name in ("engine_type", "engine_name"):
            got = getattr(cfg, name, None) or getattr(part, name, None)
            if got is not None:
                return str(getattr(got, "value", got)).lower()
    except Exception:
        pass
    return ""


def rapidocr_engine_name() -> str:
    """Which onnxruntime provider the loaded engine actually uses, read from
    the engine itself - never assumed. "" when it is not loaded."""
    eng = _RAPID.get("engine")
    if eng is None:
        return ""
    try:
        inf = eng.text_rec.session.session.get_providers()
        for p in inf:
            if "CUDA" in p or "Dml" in p or "DML" in p:
                return "RapidOCR on the graphics card"
        return "RapidOCR on this PC's processor"
    except Exception:
        return "RapidOCR"


def _rect_from_quad(box) -> Optional[tuple]:
    """RapidOCR's four corner points, as (left, top, width, height) in the
    picture's own pixels - the shape Windows' reader already answers with, so
    jarvis_secrets.py needs no second idea of where a word is. None when the
    corners are not four usable numbers (a word then keeps only its text)."""
    try:
        pts = [(float(p[0]), float(p[1])) for p in box]
    except Exception:
        return None
    if len(pts) < 3:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if any(v != v or abs(v) >= 1e7 for v in xs + ys):
        return None
    left, top = min(xs), min(ys)
    return (left, top, max(xs) - left, max(ys) - top)


def _seq(v) -> list:
    """Any sequence, as a list. RapidOCR answers with TUPLES, not lists
    (`word_results` is a tuple with one tuple of (word, score, corners) per
    line), so normalize_lines' `_one` - which exists to undo PowerShell 5.1
    flattening a one-item LIST into the item - is the wrong tool here: it
    wraps a tuple as a single item and turns one line's words into a word.
    A tuple is a list as far as the code below is concerned."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def lines_from_word_results(txts, word_results) -> list:
    """RapidOCR's answer as the ONE shape a reader here returns:
    [{"text", "words": [{"text", "left", "top", "width", "height"}]}].

    `txts` is the line texts; `word_results` is one tuple of
    (word, confidence, four corner points) per line. The line's text is
    RapidOCR's own (not rejoined from the words, so punctuation it put on the
    line but not in a word box is not lost); each word keeps its position.
    A word whose corners are unusable keeps only its text - the same rule
    normalize_lines already applies, so a secret is still found in it.
    Pure: tested with stand-ins."""
    lines = _seq(txts)
    words_all = _seq(word_results)
    if len(words_all) != len(lines):
        words_all = [None] * len(lines)
    out = []
    for i, raw_text in enumerate(lines):
        words = []
        for w in _seq(words_all[i]):
            if isinstance(w, dict):
                text, box = _pick(w, "text", "t"), _pick(w, "box", "points")
            elif isinstance(w, (list, tuple)) and len(w) >= 2:
                text, box = w[0], (w[2] if len(w) >= 3 else None)
            else:
                continue
            t = " ".join(_CONTROL.sub(" ", str(text or "")).split())
            if not t:
                continue
            rect = _rect_from_quad(box)
            if rect is None:
                words.append({"text": t})
            else:
                words.append({"text": t, "left": rect[0], "top": rect[1],
                              "width": rect[2], "height": rect[3]})
        if isinstance(raw_text, str):
            text = " ".join(_CONTROL.sub(" ", raw_text).split())
        else:
            text = " ".join(w["text"] for w in words)
        if text or words:
            out.append({"text": text, "words": words})
    return out


def bgra_from_bytes(image: bytes) -> Optional[tuple]:
    """(BGRA bytes, width, height) of the picture, decoded here, or None for
    anything that is not an ordinary picture. BGRA is the one shape
    jarvis_picture.clean paints on, and it is exactly what Windows' reader
    already hands back - so a picture that is not a PNG jarvis_picture can
    open itself (a phone's JPEG) can still be cleaned with this reader."""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(io.BytesIO(bytes(image))) as im:
            im = im.convert("RGBA")
            w, h = im.size
            if w <= 0 or h <= 0 or w * h > RAPIDOCR_MAX_PIXELS:
                return None
            rgba = im.tobytes()
    except Exception:
        return None
    bgra = bytearray(len(rgba))
    bgra[0::4] = rgba[2::4]                 # B
    bgra[1::4] = rgba[1::4]                 # G
    bgra[2::4] = rgba[0::4]                 # R
    bgra[3::4] = rgba[3::4]                 # A
    return (bytes(bgra), w, h)


def _rapidocr_read(image: bytes, want_pixels: bool) -> dict:
    """{"ok", "lines", "size", ["pixels"]} or {"ok": False, "why": str}.
    Raises _NoRapid when the package is missing, asyncio.TimeoutError when it
    takes too long, and anything else when a read raises. The caller decides
    what each of those means."""
    eng = _rapid_engine()
    out: dict = {}

    def go():
        # BYTES, never a numpy array: RapidOCR converts bytes to its own BGR
        # array (checked 2026-10-13 - a red patch reads back as [0, 0, 255])
        # and hands an array through untouched, so bytes are the one input
        # whose channel order is known.
        try:
            out["result"] = eng(bytes(image))
        except BaseException as exc:        # carried to the caller, not printed
            # Without this the exception escapes a daemon thread and Python
            # prints a traceback nobody asked for, once per unreadable
            # picture. The engine is already built by here, so a raise is
            # about THIS picture and must not be remembered as "RapidOCR is
            # broken" - that is decided when the engine is built, above.
            out["error"] = exc

    if not _RAPID_LOCK.acquire(timeout=RAPIDOCR_TIMEOUT_S):
        raise asyncio.TimeoutError()
    try:
        t = threading.Thread(target=go, name="jarvis-rapidocr", daemon=True)
        t.start()
        t.join(RAPIDOCR_TIMEOUT_S)
        if t.is_alive():
            raise asyncio.TimeoutError()
    finally:
        _RAPID_LOCK.release()

    if out.get("error") is not None:
        return {"ok": False, "why": "failed"}
    res = out.get("result")
    if res is None:
        return {"ok": False, "why": "failed"}
    word_results = getattr(res, "word_results", None)
    txts = getattr(res, "txts", None)
    if txts is None:
        # Nothing found is not a failure: it is a picture with no words.
        return {"ok": True, "lines": [], "size": _rapid_size(res)}
    lines = lines_from_word_results(txts, word_results)
    got = {"ok": True, "lines": normalize_lines(lines), "size": _rapid_size(res)}
    if want_pixels:
        px = bgra_from_bytes(image)
        if px:
            got["pixels"] = px
    return got


def _rapid_size(res) -> Optional[tuple]:
    """(width, height) of the picture RapidOCR actually read, or None. Taken
    from the array RapidOCR kept, so it is the size the boxes are in."""
    img = getattr(res, "img", None)
    try:
        h, w = img.shape[:2]
        return (int(w), int(h))
    except Exception:
        return None


def status() -> dict:
    """{"available", "engine", "why"} - whether this PC can read the words in
    a picture, and WITH WHICH READER. For the apps, through GET
    /api/second-card. Never raises; starts nothing, loads no model."""
    if using_rapidocr():
        if _RAPID_LAST["why"]:
            return {"available": False, "engine": RAPIDOCR, "why": _RAPID_LAST["why"]}
        if not rapidocr_usable():
            return {"available": False, "engine": RAPIDOCR, "why": NO_RAPIDOCR}
        return {"available": True, "engine": rapidocr_engine_name() or RAPIDOCR, "why": ""}
    if os.name != "nt":
        return {"available": False, "engine": ENGINE, "why": NOT_WINDOWS}
    if _powershell() is None and not winrt_usable():
        return {"available": False, "engine": ENGINE, "why": NO_POWERSHELL}
    if _LAST["why"]:
        return {"available": False, "engine": ENGINE, "why": _LAST["why"]}
    return {"available": True, "engine": ENGINE, "why": ""}


def active_engine() -> str:
    """The name of the reader that WILL answer the next picture, for a
    measurement to label its own numbers with (tools/ocr_bakeoff.py). Never
    raises, and loads no model: before RapidOCR's first read this is the
    package's name, not the device it settles on."""
    try:
        if using_rapidocr():
            return rapidocr_engine_name() or RAPIDOCR
    except Exception:
        pass
    return ENGINE


def _run_powershell(image: bytes) -> tuple:
    """(returncode, stdout bytes). The picture on standard input only."""
    exe = _powershell()
    if exe is None:
        raise FileNotFoundError("powershell.exe")
    encoded = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")
    flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW
    # -EncodedCommand is not a script file, so the execution policy does not
    # apply to it and is left alone.
    out = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                         input=image, capture_output=True, timeout=TIMEOUT_S,
                         creationflags=flags)
    return out.returncode, out.stdout


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def tidy(lines) -> str:
    """The lines as one text: control characters out, blank lines out."""
    out = []
    for line in lines or []:
        if not isinstance(line, str):
            continue
        t = " ".join(_CONTROL.sub(" ", line).split())
        if t:
            out.append(t)
    return "\n".join(out)


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) < 1e7 else None


def _one(v) -> list:
    """A JSON value that is a list, or a lone item PowerShell 5.1 flattened
    out of a one-item list, as a list."""
    if isinstance(v, list):
        return v
    return [] if v is None else [v]


def _pick(d: dict, *keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def normalize_lines(lines, boxes=None) -> list:
    """Whatever an engine or a stand-in gave, as [{"text", "words": [{"text",
    "left", "top", "width", "height"}]}]. `lines` is a list of strings or of
    {"text", "words"} (or a lone string). `boxes` is PowerShell's parallel
    list [{"t", "w": [{"t", "x", "y", "w", "h"}]}], used only when it has the
    same number of lines. Control characters are taken out of every word
    here, so the words a secret is looked for in are the words a model
    would have seen. A word with no usable position keeps only its text."""
    raw = _one(lines)
    pos = _one(boxes)
    if len(pos) != len(raw):
        pos = []
    out = []
    for i, ln in enumerate(raw):
        words = []
        if isinstance(ln, dict):
            text = _pick(ln, "text", "t")
            src = _one(ln.get("words"))
        else:
            text, src = ln, []
        if not src and pos and isinstance(pos[i], dict):
            src = _one(pos[i].get("w"))
        for w in src:
            if not isinstance(w, dict):
                continue
            t = " ".join(_CONTROL.sub(" ", str(_pick(w, "text", "t") or "")).split())
            if not t:
                continue
            box = [_num(_pick(w, *k)) for k in (("left", "x"), ("top", "y"),
                                                ("width", "w"), ("height", "h"))]
            if None in box:
                words.append({"text": t})
            else:
                words.append({"text": t, "left": box[0], "top": box[1], "width": box[2],
                              "height": box[3]})
        if isinstance(text, str):
            text = " ".join(_CONTROL.sub(" ", text).split())
        else:
            text = " ".join(w["text"] for w in words)
        if text or words:
            out.append({"text": text, "words": words})
    return out


def _fail(why: str) -> dict:
    return {"ok": False, "lines": [], "size": None, "why": why}


def read_lines(image: bytes, *, runner: Optional[Callable[[bytes], tuple]] = None,
               want_pixels: bool = False) -> dict:
    """{"ok", "lines", "size", "why", "engine"[, "pixels"]}: every line of
    words in the picture, each word with its position, NOT cut to any length.
    `lines` is normalize_lines' shape; `size` is (width, height) or None;
    `pixels` (only when asked, and from either reader - Windows hands back the
    bitmap it read, RapidOCR's reader decodes the picture) is (BGRA bytes,
    width, height) of the picture. `engine` names the reader that answered, for
    a measurement to label its own numbers with; a caller that does not care
    can ignore it. Never raises; `why` is a plain sentence when ok is False.

    With a `runner` (tests), only that stand-in for PowerShell is used."""

    def ok(lines, size, pixels=None) -> dict:
        out = {"ok": True, "lines": lines, "size": size, "why": "",
               "engine": active_engine()}
        if pixels:
            out["pixels"] = pixels
        return out

    if not isinstance(image, (bytes, bytearray)) or not image:
        return _fail(FAILED)
    if len(image) > MAX_BYTES:
        return _fail(TOO_BIG)
    if runner is None:
        if using_rapidocr():
            try:
                got = _rapidocr_read(bytes(image), want_pixels)
            except _NoRapid:
                _RAPID_LAST["why"] = NO_RAPIDOCR
                return _fail(NO_RAPIDOCR)
            except asyncio.TimeoutError:
                return _fail(TOO_SLOW)
            except Exception:
                _RAPID_LAST["why"] = RAPIDOCR_BROKEN
                return _fail(RAPIDOCR_BROKEN)
            if got.get("ok") is not True:
                # _rapidocr_read answers a failure with a dict rather than an
                # exception (a result object that came back unusable), so this
                # has to be checked and not assumed.
                return _fail(FAILED)
            return ok(got["lines"], got.get("size"), got.get("pixels"))
        st = status()
        if not st["available"]:
            return _fail(st["why"])
        try:
            got = _winrt_read(bytes(image), want_pixels)
        except _NoWinrt:
            got = None
        except asyncio.TimeoutError:
            return _fail(TOO_SLOW)
        except Exception:
            got = None                     # a Windows call failed: PowerShell tries
        if got is not None:
            if got.get("ok") is True:
                return ok(normalize_lines(got["lines"]), got.get("size"), got.get("pixels"))
            if got.get("why") == "no_language":
                _LAST["why"] = NO_LANGUAGE
                return _fail(NO_LANGUAGE)
            return _fail(TOO_BIG if got.get("why") == "too_big" else FAILED)
    run = runner or _run_powershell
    try:
        code, raw = run(bytes(image))
    except subprocess.TimeoutExpired:
        return _fail(TOO_SLOW)
    except Exception:
        return _fail(FAILED)
    out = bytes(raw or b"").decode("utf-8-sig", "replace")
    # The one JSON line, even if Windows printed something around it.
    start, end = out.find("{"), out.rfind("}")
    try:
        got = json.loads(out[start:end + 1]) if 0 <= start < end else {}
    except ValueError:
        got = {}
    if not isinstance(got, dict) or got.get("ok") is not True:
        why = got.get("why") if isinstance(got, dict) else ""
        if why == "no_language":
            _LAST["why"] = NO_LANGUAGE
            return _fail(NO_LANGUAGE)
        return _fail(TOO_BIG if why == "too_big" else FAILED)
    size = None
    w, h = _num(got.get("width")), _num(got.get("height"))
    if w and h:
        size = (int(w), int(h))
    return ok(normalize_lines(got.get("lines"), got.get("boxes")), size)


def read_text(image: bytes, *, runner: Optional[Callable[[bytes], tuple]] = None) -> dict:
    """{"ok", "text", "left_out", "why", "lines", "size"}: the words in the
    picture, at most MAX_CHARS of them, and how many characters were left
    out. `lines` (and `size`) are the FULL reading with each word's position,
    for jarvis_screen.clean_picture: it looks for secrets in ALL of it before
    anything is cut to length - the cut must never leave half a secret in.
    Never raises; `why` is a plain sentence when ok is False."""
    got = read_lines(image, runner=runner)
    if not got["ok"]:
        return {"ok": False, "text": "", "left_out": 0, "why": got["why"]}
    text = tidy([ln["text"] for ln in got["lines"]])
    left = max(0, len(text) - MAX_CHARS)
    if left:
        text = text[:MAX_CHARS].rstrip()
    return {"ok": True, "text": text, "left_out": left, "why": "",
            "lines": got["lines"], "size": got["size"]}


_DATA_URI = re.compile(r"^data:image/(?:jpeg|jpg|png|bmp|gif|tiff);base64,([A-Za-z0-9+/=\s]+)$",
                       re.I)


def image_bytes(part) -> Optional[bytes]:
    """The picture in one image part of a chat message - the OpenAI-style
    `{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}`
    both apps send - or None. Only a data: address is read: a web address is
    never fetched."""
    if not isinstance(part, dict):
        return None
    url = part.get("image_url")
    if isinstance(url, dict):
        url = url.get("url")
    if not isinstance(url, str) and isinstance(part.get("image"), str):
        url = part["image"]
    if not isinstance(url, str) or len(url) > MAX_BYTES * 2:
        return None
    m = _DATA_URI.match(url.strip())
    if not m:
        return None
    try:
        return base64.b64decode(m.group(1), validate=False)
    except Exception:
        return None


def _reset_for_tests() -> None:
    _LAST["why"] = ""
    _RAPID_LAST["why"] = ""
    _SETTINGS_CACHE.update({"reader": DEFAULT_READER, "why": "", "at": 0.0})


def _rapid_reset_for_tests() -> None:
    """Forget the loaded RapidOCR engine and this process's "it is broken"
    note, so a test can drive the real package again. Not used while Jarvis
    runs: a broken wheel stays broken until it restarts, rather than being
    made to load 31 MB of ONNX once per picture."""
    _RAPID.pop("engine", None)
    _RAPID_LAST["why"] = ""


# --------------------------------------------------------------------------
#   The measurement: read the same pictures with BOTH readers and say what
#   each one actually said (2026-10-13). It lives HERE, in the shipped module,
#   and not in tools/: a shipped file must not import anything out of the
#   repository (`scripts/check-backend.ps1` walks the imports of everything
#   shipped and would fail on it), and the measurement has to be runnable on
#   the owner's PC, where only the backend exists. tools/ocr_bakeoff.py is a
#   thin front door onto this, so both spellings give the same numbers.
# --------------------------------------------------------------------------

def _measure_words(lines) -> list:
    """Every word, as (text, box or None). A line with no word boxes still
    counts: its text is split on spaces and each piece has no position -
    which is exactly the thing being measured."""
    out = []
    for ln in lines or []:
        if not isinstance(ln, dict):
            continue
        ws = ln.get("words") or []
        if ws:
            for w in ws:
                if isinstance(w, dict) and w.get("text"):
                    box = None
                    if all(k in w for k in ("left", "top", "width", "height")):
                        box = (w["left"], w["top"], w["width"], w["height"])
                    out.append((str(w["text"]), box))
        else:
            for piece in str(ln.get("text") or "").split():
                out.append((piece, None))
    return out


def _centre(box) -> tuple:
    return (box[0] + box[2] / 2.0, box[1] + box[3] / 2.0)


def _inside(a, b) -> bool:
    cx, cy = _centre(a)
    return b[0] <= cx <= b[0] + b[2] and b[1] <= cy <= b[1] + b[3]


def _boxes_agree(a, b) -> bool:
    """Do two boxes mean the same word in the same place? The centre of one
    inside the other, either way round - the loosest test that still means
    that, so it does not manufacture disagreement out of a pixel."""
    if a is None or b is None:
        return False
    return _inside(a, b) or _inside(b, a)


def _read_with(which: str, image: bytes) -> dict:
    """One reader's answer on one picture, and how long it took.

    The reader is chosen through _MEASURE_OVERRIDE for the length of the call,
    so a measurement NEVER reads or writes the owner's settings file and can
    never change which reader the owner's Jarvis uses. That is not
    hypothetical: the first version called set_reader() on the real settings
    path, so the mere act of measuring wrote ~/.openjarvis/ocr-reader.json and
    left it saying "rapidocr" (found and fixed 2026-10-13)."""
    global _MEASURE_OVERRIDE
    saved_override = _MEASURE_OVERRIDE
    try:
        _MEASURE_OVERRIDE = which
        _reset_for_tests()
        t0 = time.perf_counter()
        got = read_lines(bytes(image))
        secs = time.perf_counter() - t0
        engine = ((rapidocr_engine_name() or RAPIDOCR) if which == "rapidocr" else ENGINE)
    finally:
        _MEASURE_OVERRIDE = saved_override
        _reset_for_tests()
    return {"ok": bool(got.get("ok")), "why": got.get("why") or "", "engine": engine,
            "seconds": secs, "size": got.get("size"),
            "lines": len(got.get("lines") or []), "words": _measure_words(got.get("lines"))}


def _confidences(image: bytes) -> list:
    """RapidOCR's own per-word confidences for this picture, or []. Windows'
    own reader returns none through the pywinrt path, so this column is
    RapidOCR's alone - printed, never hidden."""
    try:
        _rapidocr_class()
        eng = _rapid_engine()
        res = eng(bytes(image))
    except Exception:
        return []
    vals = []
    for line in getattr(res, "word_results", None) or ():
        for w in line or ():
            if isinstance(w, (list, tuple)) and len(w) >= 2:
                c = w[1]
                if isinstance(c, (int, float)) and c == c:
                    vals.append(float(c))
    return vals


def compare_pictures(paths) -> dict:
    """Read every picture with BOTH readers. Returns the numbers; printing
    them is report_comparison's job. Nothing leaves this PC, and the owner's
    chosen reader is left exactly as it was found."""
    out = {"windows_engine": ENGINE, "rapidocr_engine": RAPIDOCR, "pictures": []}
    for p in paths:
        try:
            with open(p, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            out["pictures"].append({"path": str(p), "error": f"{type(exc).__name__}: {exc}"})
            continue
        win = _read_with("windows", raw)
        rap = _read_with("rapidocr", raw)
        rap["confidences"] = _confidences(raw)
        out["pictures"].append({"path": str(p), "windows": win, "rapidocr": rap})
    return out


def report_comparison(rep: dict) -> str:
    """The measurement as plain text, in the owner's language. It says what is
    a difference and refuses to say which reader is right."""
    import statistics
    out = [f"Picture readers compared: {len(rep['pictures'])} picture(s)",
           f"  A = {rep['windows_engine']}   (the default)",
           f"  B = {rep['rapidocr_engine']}", ""]
    total_both = total_same = total_checked = 0
    for d in rep["pictures"]:
        out.append(f"--- {d['path']}")
        if d.get("error"):
            out.append(f"  could not be read from disk ({d['error']})")
            out.append("")
            continue
        w, r = d["windows"], d["rapidocr"]
        for label, g in (("A windows ", w), ("B rapidocr", r)):
            if not g["ok"]:
                out.append(f"  {label}: COULD NOT READ - {g['why']}")
                continue
            confs = g.get("confidences") or []
            if confs:
                cs = (f", confidence mean {statistics.fmean(confs):.3f} "
                      f"min {min(confs):.3f}")
            else:
                cs = ", confidence: not given by this reader"
            pos = sum(1 for _t, b in g["words"] if b is not None)
            out.append(f"  {label}: {g['lines']} line(s), {len(g['words'])} word(s), "
                       f"{pos} with a position, {g['seconds']:.2f}s{cs}")
        if not (w["ok"] and r["ok"]):
            out.append("  agreement: not compared (one reader did not read it)")
            out.append("")
            continue
        a = {t.casefold(): b for t, b in w["words"]}
        b = {t.casefold(): bb for t, bb in r["words"]}
        both, only_a, only_b = sorted(set(a) & set(b)), sorted(set(a) - set(b)), sorted(set(b) - set(a))
        line = f"  agreement: {len(both)} word(s) both found"
        if only_a:
            line += f"; only A: {', '.join(only_a[:8])}"
        if only_b:
            line += f"; only B: {', '.join(only_b[:8])}"
        out.append(line)
        same = sum(1 for k in both if _boxes_agree(a[k], b[k]))
        checked = sum(1 for k in both if a[k] is not None and b[k] is not None)
        out.append(f"  positions: {same} of {checked} shared word(s) have both boxes on the "
                   f"same spot")
        out.append("")
        total_both += len(both)
        total_same += same
        total_checked += checked
    read_by_both = sum(1 for d in rep["pictures"]
                       if not d.get("error") and d["windows"]["ok"] and d["rapidocr"]["ok"])
    out += ["=== TOTALS ===",
            f"pictures read by both readers: {read_by_both}/{len(rep['pictures'])}",
            f"words both readers found: {total_both}",
            f"boxes agreeing on the same spot: {total_same} of {total_checked} comparable",
            "",
            "This says how the two readers DIFFER, not which one is right: neither is",
            "checked against a hand-typed answer here. Windows' reader gives no",
            "per-word confidence, so that column is RapidOCR's alone."]
    return "\n".join(out)


def _fresh_settings() -> dict:
    """Read the settings file now, ignoring the cache - for the command line,
    where the owner has just changed it."""
    _SETTINGS_CACHE.update({"at": 0.0})
    return reader()


_USAGE = """jarvis_ocr - which reader reads the words in a picture, and how they compare.

    py -3 jarvis_ocr.py                        which reader is in use
    py -3 jarvis_ocr.py reader                 the same
    py -3 jarvis_ocr.py reader windows         use Windows' own reader (the default)
    py -3 jarvis_ocr.py reader rapidocr        use RapidOCR instead
    py -3 jarvis_ocr.py compare <pictures>     read each picture with BOTH readers and report
                                               what they agreed on, with positions and confidence

`reader rapidocr` needs the rapidocr package: py -3 -m pip install -r backend\\requirements.txt
Nothing either reader does leaves this PC."""


def _cmd_reader(argv: list) -> int:
    if argv:
        try:
            got = set_reader(argv[0])
        except ValueError as exc:
            print(exc)
            return 2
        print(f"The picture reader is now: {got['reader']}")
        return 0
    got = _fresh_settings()
    if _RAPID_LAST["why"]:
        print(f"{got['reader']} (but: {_RAPID_LAST['why']})")
        return 0
    st = status()
    print(f"The picture reader is: {got['reader']}")
    print(f"  engine:    {st['engine']}")
    print(f"  available: {'yes' if st['available'] else 'no'}"
          + (f" - {st['why']}" if st["why"] else ""))
    if got["reader"] == "rapidocr" and not rapidocr_usable():
        print(f"  {NO_RAPIDOCR}")
    return 0


def _cmd_compare(argv: list) -> int:
    args = [a for a in argv if a != "--"]
    if not args:
        print("Give it one or more picture files: "
              "py -3 jarvis_ocr.py compare <picture> [<picture> ...]")
        return 2
    missing = [a for a in args if not os.path.isfile(a)]
    if missing:
        print("not a file: " + ", ".join(missing))
        return 2
    print(report_comparison(compare_pictures(args)))
    return 0


def main(argv=None) -> int:
    """The command line: the switch, and the measurement. Neither starts a
    model except `compare`, and nothing either does leaves this PC."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return _cmd_reader([])
    cmd, rest = args[0].lower(), args[1:]
    if cmd == "reader":
        return _cmd_reader(rest)
    if cmd == "compare":
        return _cmd_compare(rest)
    print(_USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
