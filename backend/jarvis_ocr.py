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

HOW. Windows' built-in text recognition (Windows.Media.Ocr), through
Windows PowerShell 5.1, which every Windows 10 and 11 PC has: no download,
no Python package, nothing to pin, and nothing that can reach the internet.
The script is FIXED text below (_SCRIPT), started by its full system path
(never a `powershell` found on PATH), handed the picture on standard input
- never written to disk - and it prints one line of JSON: the lines of text
it found. It uses the languages of the owner's Windows profile; with none
that Windows can read, it says so plainly (NO_LANGUAGE).

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
function Say($o) { [Console]::Out.Write(($o | ConvertTo-Json -Compress -Depth 3)) }
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
  Say @{ ok = $true; lines = $lines }
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


def status() -> dict:
    """{"available", "engine", "why"} - whether this PC can read the words in
    a picture. For the apps, through GET /api/second-card. Never raises;
    starts nothing."""
    if os.name != "nt":
        return {"available": False, "engine": ENGINE, "why": NOT_WINDOWS}
    if _powershell() is None:
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


def read_text(image: bytes, *, runner: Optional[Callable[[bytes], tuple]] = None) -> dict:
    """{"ok", "text", "left_out", "why"}: the words in the picture, at most
    MAX_CHARS of them, and how many characters were left out. Never raises;
    `why` is a plain sentence when ok is False."""
    if not isinstance(image, (bytes, bytearray)) or not image:
        return {"ok": False, "text": "", "left_out": 0, "why": FAILED}
    if len(image) > MAX_BYTES:
        return {"ok": False, "text": "", "left_out": 0, "why": TOO_BIG}
    if runner is None:
        st = status()
        if not st["available"]:
            return {"ok": False, "text": "", "left_out": 0, "why": st["why"]}
    run = runner or _run_powershell
    try:
        code, raw = run(bytes(image))
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "", "left_out": 0, "why": TOO_SLOW}
    except Exception:
        return {"ok": False, "text": "", "left_out": 0, "why": FAILED}
    try:
        got = json.loads(bytes(raw or b"").decode("utf-8-sig", "replace").strip() or "{}")
    except ValueError:
        got = {}
    if not isinstance(got, dict) or got.get("ok") is not True:
        why = got.get("why") if isinstance(got, dict) else ""
        if why == "no_language":
            _LAST["why"] = NO_LANGUAGE
            return {"ok": False, "text": "", "left_out": 0, "why": NO_LANGUAGE}
        return {"ok": False, "text": "", "left_out": 0,
                "why": TOO_BIG if why == "too_big" else FAILED}
    lines = got.get("lines")
    text = tidy(lines if isinstance(lines, list) else [lines])
    left = max(0, len(text) - MAX_CHARS)
    if left:
        text = text[:MAX_CHARS].rstrip()
    return {"ok": True, "text": text, "left_out": left, "why": ""}


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
