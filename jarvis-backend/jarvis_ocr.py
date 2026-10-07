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

NOT CHECKED HERE (no Windows in the dev container): the PowerShell half
itself. Everything around it - the picture read out of the message, the
cap, the words the model gets, the outside-text marking - is tested with a
stand-in engine (backend/test_picture_text.py).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
from typing import Callable, Optional

ENGINE = "Windows' own text recognition"

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
TOO_BIG = "The picture is too big for Windows' text recognition."
FAILED = "Windows could not read the words in the picture."
TOO_SLOW = "Windows took too long to read the words in the picture."

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


def status() -> dict:
    """{"available", "engine", "why"} - whether this PC can read the words in
    a picture. For the apps, through GET /api/second-card. Never raises;
    starts nothing."""
    if os.name != "nt":
        return {"available": False, "engine": ENGINE, "why": NOT_WINDOWS}
    if _powershell() is None and not winrt_usable():
        return {"available": False, "engine": ENGINE, "why": NO_POWERSHELL}
    if _LAST["why"]:
        return {"available": False, "engine": ENGINE, "why": _LAST["why"]}
    return {"available": True, "engine": ENGINE, "why": ""}


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
    """{"ok", "lines", "size", "why"[, "pixels"]}: every line of words in the
    picture, each word with its position, NOT cut to any length. `lines` is
    normalize_lines' shape; `size` is (width, height) or None; `pixels`
    (only when asked, and only from the in-process reader) is (BGRA bytes,
    width, height) of the very bitmap the words were read from. Never
    raises; `why` is a plain sentence when ok is False.

    With a `runner` (tests), only that stand-in for PowerShell is used."""
    if not isinstance(image, (bytes, bytearray)) or not image:
        return _fail(FAILED)
    if len(image) > MAX_BYTES:
        return _fail(TOO_BIG)
    if runner is None:
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
                out = {"ok": True, "lines": normalize_lines(got["lines"]),
                       "size": got.get("size"), "why": ""}
                if got.get("pixels"):
                    out["pixels"] = got["pixels"]
                return out
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
    return {"ok": True, "lines": normalize_lines(got.get("lines"), got.get("boxes")),
            "size": size, "why": ""}


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
