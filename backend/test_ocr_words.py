"""test_ocr_words.py - jarvis_ocr.py reading the words in a picture WITH each
word's position, in this program (pywinrt) or through PowerShell.

    python3 backend/test_ocr_words.py

What it proves (screen safety, part 2, 2026-09-29):
  - the reader's answer, whatever shape (Windows' own objects, PowerShell's
    JSON with or without word boxes, a plain string, a stand-in), becomes
    one shape: lines of words, each with left, top, width, height; control
    characters are taken out of every word; a word with no usable position
    keeps only its text; PowerShell 5.1's one-item-list flattening is undone;
  - the in-process reader is tried first; when the packages are missing or a
    Windows call fails, PowerShell is used as it always was; "no language" and
    "too big" keep their plain messages and do NOT fall back; a slow one says
    so and does not start a second wait;
  - the position part of the PowerShell script runs (in PowerShell 7 here,
    if it is installed: the JSON it makes reads back into the same shape) and
    the whole script still parses;
  - `read_text` still cuts to 4,500 characters but hands on the FULL lines for
    the secret check;
  - the `winocr` package is not used, and above all nothing here can open a
    web server: no serve(), no uvicorn, no 0.0.0.0;
  - the six pywinrt packages are in requirements.txt and its hash lock, so
    the owner's next apply-patches.ps1 installs them.
Not run here: the real Windows calls (see jarvis_ocr.py's header and the
owner's-PC test in backend/README.md).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_ocr.py")

import jarvis_ocr as J  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def rect(x, y, w, h):
    return NS(x=x, y=y, width=w, height=h)


def ocr_result():
    def word(t, r):
        return NS(text=t, bounding_rect=r)
    return NS(lines=[NS(text="Hello there", words=[word("Hello", rect(10, 5, 40, 12)),
                                                   word("there", rect(58, 5, 44, 12))]),
                     NS(text="Second", words=[word("Second", rect(10, 25, 50, 12))])])


def t_shapes():
    got = J.lines_from_result(ocr_result())
    check("Windows' own result objects become lines of words with positions",
          got == [{"text": "Hello there", "words": [
              {"text": "Hello", "left": 10.0, "top": 5.0, "width": 40.0, "height": 12.0},
              {"text": "there", "left": 58.0, "top": 5.0, "width": 44.0, "height": 12.0}]},
                  {"text": "Second", "words": [{"text": "Second", "left": 10.0, "top": 25.0,
                                                "width": 50.0, "height": 12.0}]}], str(got))
    n = J.normalize_lines(got)
    check("that shape is stable", n == got)
    n = J.normalize_lines(["Hello\u0007 there", "", "Line  two"])
    check("plain strings: control characters and blank lines out, no words",
          [l["text"] for l in n] == ["Hello there", "Line two"] and all(l["words"] == [] for l in n), str(n))
    n = J.normalize_lines(["a b"], [{"t": "a b", "w": [{"t": "a", "x": 1, "y": 2, "w": 3, "h": 4},
                                                       {"t": "b", "x": 5, "y": 2, "w": 3, "h": 4}]}])
    check("PowerShell's parallel word boxes are joined to the lines",
          n[0]["words"][1] == {"text": "b", "left": 5.0, "top": 2.0, "width": 3.0, "height": 4.0}, str(n))
    n = J.normalize_lines(["a b", "c"], [{"t": "a b", "w": []}])
    check("... but only when there is one box list per line (else no positions, never wrong ones)",
          all(l["words"] == [] for l in n))
    n = J.normalize_lines("one line", {"t": "one line", "w": {"t": "one", "x": 1, "y": 1, "w": 2, "h": 2}})
    check("PowerShell 5.1 turns a one-item list into the item: undone",
          n[0]["words"] == [{"text": "one", "left": 1.0, "top": 1.0, "width": 2.0, "height": 2.0}], str(n))
    n = J.normalize_lines([{"text": "x", "words": [{"text": "x", "left": "no", "top": 1, "width": 2,
                                                    "height": 2}, {"text": "y\u0000z", "left": 1, "top": 1,
                                                                   "width": 1, "height": 1}]}])
    check("a word with a bad number keeps its text only; a word's control characters go",
          n[0]["words"][0] == {"text": "x"} and n[0]["words"][1]["text"] == "y z", str(n))
    check("nothing at all is nothing", J.normalize_lines(None) == [] and J.normalize_lines([]) == [])


def with_engine(winrt, ps=None, avail=True):
    """Run read_lines with stand-ins for the two readers and the availability."""
    saved = (J._winrt_read, J._run_powershell, J.status)
    calls = {"ps": 0, "winrt": 0}

    def w(image, want):
        calls["winrt"] += 1
        return winrt(image, want)

    def p(image):
        calls["ps"] += 1
        return ps(image) if ps else (0, json.dumps({"ok": True, "lines": ["from powershell"]}).encode())
    J._winrt_read, J._run_powershell = w, p
    J.status = lambda: {"available": avail, "engine": J.ENGINE, "why": "" if avail else "nope"}
    J._reset_for_tests()
    return saved, calls


def restore(saved):
    J._winrt_read, J._run_powershell, J.status = saved
    J._reset_for_tests()


def t_order():
    saved, calls = with_engine(lambda i, want: {"ok": True, "lines": J.lines_from_result(ocr_result()),
                                                "size": (400, 300), "pixels": (b"px", 400, 300)})
    try:
        got = J.read_lines(PNG, want_pixels=True)
    finally:
        restore(saved)
    check("the in-process reader is used first, and PowerShell is not started",
          got["ok"] and calls == {"ps": 0, "winrt": 1} and got["size"] == (400, 300)
          and got["lines"][0]["words"][0]["text"] == "Hello", str(got))
    check("... and the very pixels it read are handed back when asked", got.get("pixels") == (b"px", 400, 300))

    def missing(i, want):
        raise J._NoWinrt()
    saved, calls = with_engine(missing)
    try:
        got = J.read_lines(PNG)
    finally:
        restore(saved)
    check("without the pywinrt packages PowerShell is used, as it always was",
          got["ok"] and calls["ps"] == 1 and got["lines"][0]["text"] == "from powershell")

    def broken(i, want):
        raise RuntimeError("a Windows call failed")
    saved, calls = with_engine(broken)
    try:
        got = J.read_lines(PNG)
    finally:
        restore(saved)
    check("a Windows call that fails in-process: PowerShell tries", got["ok"] and calls["ps"] == 1)

    def slow(i, want):
        raise asyncio.TimeoutError()
    saved, calls = with_engine(slow)
    try:
        got = J.read_lines(PNG)
    finally:
        restore(saved)
    check("too slow: said so, and PowerShell is NOT started (that would double the wait)",
          got["ok"] is False and got["why"] == J.TOO_SLOW and calls["ps"] == 0)

    saved, calls = with_engine(lambda i, want: {"ok": False, "why": "no_language"})
    try:
        got = J.read_lines(PNG)
        again = J.status
    finally:
        why_after = J._LAST["why"]
        restore(saved)
    check("no text-recognition language: the plain sentence, no fallback, remembered until restart",
          got["why"] == J.NO_LANGUAGE and calls["ps"] == 0 and why_after == J.NO_LANGUAGE)
    saved, calls = with_engine(lambda i, want: {"ok": False, "why": "too_big"})
    try:
        got = J.read_lines(PNG)
    finally:
        restore(saved)
    check("too big: the plain sentence", got["why"] == J.TOO_BIG and calls["ps"] == 0)
    saved, calls = with_engine(lambda i, want: {"ok": False})
    try:
        got = J.read_lines(PNG)
    finally:
        restore(saved)
    check("anything else that is not ok: 'could not read', not a guess", got["why"] == J.FAILED)
    saved, calls = with_engine(lambda i, want: {"ok": True, "lines": []}, avail=False)
    try:
        got = J.read_lines(PNG)
    finally:
        restore(saved)
    check("a PC that cannot read at all says why and starts nothing",
          got["ok"] is False and got["why"] == "nope" and calls == {"ps": 0, "winrt": 0})
    check("nothing to read, and too big, are refused before any reader",
          J.read_lines(b"")["ok"] is False and J.read_lines(b"x" * (J.MAX_BYTES + 1))["why"] == J.TOO_BIG)

    saved, calls = with_engine(missing, ps=lambda i: (0, json.dumps(
        {"ok": True, "lines": ["Hello there"], "width": 400, "height": 300,
         "boxes": [{"t": "Hello there", "w": [{"t": "Hello", "x": 10, "y": 5, "w": 40, "h": 12},
                                              {"t": "there", "x": 58, "y": 5, "w": 44, "h": 12}]}]}).encode()))
    try:
        got = J.read_lines(PNG)
    finally:
        restore(saved)
    check("PowerShell's answer now carries word positions and the picture's size",
          got["size"] == (400, 300) and got["lines"][0]["words"][1]["left"] == 58.0, str(got))
    got = J.read_lines(PNG, runner=lambda b: (0, b'{"ok":true,"lines":["x"]}'))
    check("an older PowerShell answer (no boxes) still works: words without positions",
          got["ok"] and got["lines"] == [{"text": "x", "words": []}] and got["size"] is None)


def t_read_text():
    big = ["word " * 40] * 40                                # about 8,000 characters
    got = J.read_text(PNG, runner=lambda b: (0, json.dumps({"ok": True, "lines": big}).encode()))
    check("read_text still cuts the text to its limit and says how much was left out",
          got["ok"] and len(got["text"]) <= J.MAX_CHARS and got["left_out"] > 3000, str(got["left_out"]))
    check("... but hands on the FULL lines, for the secret check before any cut",
          sum(len(l["text"]) for l in got["lines"]) > 7000)
    got = J.read_text(PNG, runner=lambda b: (0, b'{"ok":false,"why":"no_language"}'))
    check("a failure keeps the old shape", got == {"ok": False, "text": "", "left_out": 0,
                                                    "why": J.NO_LANGUAGE})
    J._reset_for_tests()


PS_TEST = r"""
function Say($o) { [Console]::Out.Write(($o | ConvertTo-Json -Compress -Depth 6)) }
function W($t,$x,$y,$w,$h) { [pscustomobject]@{ Text=$t; BoundingRect=[pscustomobject]@{X=$x;Y=$y;Width=$w;Height=$h} } }
$result = [pscustomobject]@{ Lines = @(
  [pscustomobject]@{ Text='Hello there'; Words=@((W 'Hello' 10 5 40 12), (W 'there' 58.5 5 44 12)) },
  [pscustomobject]@{ Text='Second'; Words=@((W 'Second' 10 25 50 12)) } ) }
$bitmap = [pscustomobject]@{ PixelWidth = 400; PixelHeight = 300 }
""" + "\n"


def t_powershell_script():
    src = J._SCRIPT
    check("the script still asks for the words and their boxes, in one JSON line",
          "BoundingRect" in src and "boxes" in src and "PixelWidth" in src and "-Depth 6" in src)
    pwsh = shutil.which("pwsh") or ("/opt/pwsh/pwsh" if os.path.exists("/opt/pwsh/pwsh") else None)
    if not pwsh:
        print("skip  PowerShell 7 is not installed here: the script is not run")
        return
    cmd = ("$s = [Console]::In.ReadToEnd(); $errs = $null; $tok = $null; "
           "$null = [System.Management.Automation.Language.Parser]::ParseInput($s, [ref]$tok, [ref]$errs); "
           "Write-Output $errs.Count")
    r = subprocess.run([pwsh, "-NoProfile", "-Command", cmd], input=src, capture_output=True, text=True,
                       timeout=180)
    check("the whole script parses with no errors", r.stdout.strip() == "0", r.stdout + r.stderr[:300])
    # the part that makes the words and boxes, run against stand-in objects
    a = src.index("  $lines = @($result.Lines")
    b = src.index("\n", src.index("Say @{ ok = $true", a))
    body = src[a:b]
    r = subprocess.run([pwsh, "-NoProfile", "-Command", PS_TEST + body], capture_output=True, text=True,
                       timeout=180)
    try:
        got = json.loads(r.stdout)
    except ValueError:
        got = {}
    check("the box-making part of the script runs and writes JSON", got.get("ok") is True
          and got.get("width") == 400 and got.get("height") == 300, r.stdout[:300] + r.stderr[:300])
    lines = J.normalize_lines(got.get("lines"), got.get("boxes"))
    check("... which reads back as lines of positioned words",
          [w["text"] for w in lines[0]["words"]] == ["Hello", "there"]
          and lines[0]["words"][1]["left"] == 58.5 and lines[1]["words"][0]["height"] == 12.0, str(lines))


def t_hygiene():
    import ast
    src = (HERE / "jarvis_ocr.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names, mods, strings = set(), set(), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Attribute):
            names.add(n.attr)
        elif isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            strings.append(n.value)
    check("the winocr package is not imported and nothing here can start a web server",
          "winocr" not in mods and not ({"serve", "uvicorn", "fastapi"} & (names | mods))
          and not any("0.0.0.0" in x for x in strings))
    check("no network in the reader", not ({"socket", "urllib", "requests", "http"} & (names | mods)))
    check("the picture is never written to disk",
          not ({"open", "write_text", "tempfile", "NamedTemporaryFile", "mkstemp", "Path"} & (names | mods)))
    req = (HERE / "requirements.txt").read_text(encoding="utf-8").lower()
    lock = (HERE / "requirements.lock").read_text(encoding="utf-8").lower()
    six = ("winrt-windows.media.ocr", "winrt-windows.graphics.imaging", "winrt-windows.storage.streams",
           "winrt-windows.foundation", "winrt-windows.foundation.collections", "winrt-windows.globalization")
    check("the six pywinrt packages are in requirements.txt (Windows only)",
          all(re.search(r"^" + re.escape(p) + r"\s*;\s*sys_platform == \"win32\"", req, re.M) for p in six))
    check("... and locked with hashes", all(p.replace(".", "-") + "==" in lock for p in six))
    check("the imports name exactly those six",
          all(x in src for x in ("winrt.windows.media.ocr", "winrt.windows.graphics.imaging",
                                  "winrt.windows.storage.streams", "winrt.windows.foundation",
                                  "winrt.windows.foundation.collections", "winrt.windows.globalization")))
    check("off Windows the in-process reader is simply not there", J.winrt_usable() is False)
    import inspect
    check("the writer lets go of the picture's stream before Windows reads it (no closing it under us)",
          "detach_stream" in inspect.getsource(J._winrt_read))


def main():
    for fn in (t_shapes, t_order, t_read_text, t_powershell_script, t_hygiene):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            print("FAIL " + fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
