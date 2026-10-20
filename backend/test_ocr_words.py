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
import io
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


def _function_of(src: str, line_no: int) -> str:
    """The name of the function the given 1-based line sits in, or ""."""
    import ast
    best = ""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= line_no <= end:
                best = node.name
    return best


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
    # The rule is that the PICTURE is never written to disk, and it is checked
    # as that rule rather than as "this file may not open a file at all". The
    # second reader (2026-10-13) needs one legitimate write - the on/off
    # setting, in set_reader - and the measurement reads the pictures it is
    # pointed at from disk; neither is the picture on its way to a model.
    # What must never appear is a temp-file helper, or any file opened for
    # writing outside set_reader's own ".tmp" beside the settings file.
    check("nothing here makes a temporary file or a named temp file",
          not ({"tempfile", "NamedTemporaryFile", "mkstemp", "TemporaryDirectory"} & (names | mods)))
    check("the only file opened for writing is the settings file in set_reader",
          all(_function_of(src, i + 1) == "set_reader"
              for i, line in enumerate(src.splitlines())
              if re.search(r"""open\([^)]*["'][wa]""", line)),
          str([(i + 1, line.strip()) for i, line in enumerate(src.splitlines())
               if re.search(r"""open\([^)]*["'][wa]""", line)
               and _function_of(src, i + 1) != "set_reader"]))
    check("... and the settings file is written beside itself as a .tmp, then moved",
          "os.replace" in src and '".tmp"' in src)
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
    # The pywinrt packages are pinned Windows-only (`; sys_platform == "win32"`),
    # so this is a platform fact rather than a bug: present on the owner's PC,
    # absent on CI. It used to assert the off-Windows answer everywhere, so it
    # could only ever pass off Windows (2026-10-03).
    check("the in-process reader is there exactly when this is Windows",
          J.winrt_usable() == (os.name == "nt"), J.winrt_usable())
    import inspect
    check("the writer lets go of the picture's stream before Windows reads it (no closing it under us)",
          "detach_stream" in inspect.getsource(J._winrt_read))


def t_second_reader_switch():
    """The second reader (2026-10-13): OFF by default, and choosing it is all
    this file does - it never makes the reader itself mandatory."""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-ocr-switch-"))
    saved = J.settings_path
    J.settings_path = lambda: tmp / "ocr-reader.json"
    try:
        J._reset_for_tests()
        check("no settings file at all: Windows' own reader, and no complaint",
              J.reader() == {"reader": "windows", "why": ""}, J.reader())
        check("... and BOTH public answers agree it is the default",
              J._fresh_settings()["reader"] == "windows"
              and J.using_rapidocr() is False)

        got = J.set_reader("rapidocr")
        J._SETTINGS_CACHE.update({"at": 0.0})
        check("choosing RapidOCR writes it, and it reads back",
              got["reader"] == "rapidocr" and J._fresh_settings()["reader"] == "rapidocr"
              and J.using_rapidocr() is True, got)
        check("... as plain JSON an owner can read and edit",
              json.loads((tmp / "ocr-reader.json").read_text(encoding="utf-8"))
              == {"reader": "rapidocr"},
              (tmp / "ocr-reader.json").read_text(encoding="utf-8"))

        J.set_reader("windows")
        J._SETTINGS_CACHE.update({"at": 0.0})
        check("choosing Windows back is the same one call",
              J._fresh_settings()["reader"] == "windows" and J.using_rapidocr() is False)

        for bad in ("", "  ", "rapid", "openvino", None, 7):
            try:
                J.set_reader(bad)
                check(f"a reader that is not one of the two is refused: {bad!r}", False)
            except ValueError:
                check(f"a reader that is not one of the two is refused: {bad!r}", True)
        check("... and a refused choice left the file as it was",
              J._fresh_settings()["reader"] == "windows")
        check("a choice is matched case-insensitively and trimmed, as every other "
              "setting here is",
              J.set_reader("RapidOCR")["reader"] == "rapidocr"
              and J._fresh_settings()["reader"] == "rapidocr")
        J.set_reader("windows")

        # A damaged or hand-edited file: the default, never a third reader.
        for junk, why_part in (("{not json", "damaged"),
                               ("[1, 2]", "damaged"),
                               ('{"reader": 5}', "not one of"),
                               ('{"reader": "tesseract"}', "not one of")):
            (tmp / "ocr-reader.json").write_text(junk, encoding="utf-8")
            J._SETTINGS_CACHE.update({"at": 0.0})
            got = J._fresh_settings()
            check(f"a settings file holding {junk!r} falls back to Windows and says why",
                  got["reader"] == "windows" and why_part in got["why"], got)
        # A file that simply says nothing about the reader is not damage: the
        # default is Windows, and there is nothing to report.
        (tmp / "ocr-reader.json").write_text('{"other": true}', encoding="utf-8")
        J._SETTINGS_CACHE.update({"at": 0.0})
        check("a settings file that never mentions the reader is simply the default",
              J._fresh_settings() == {"reader": "windows", "why": ""},
              J._fresh_settings())

        # The file is read fresh: a change on disk is picked up.
        (tmp / "ocr-reader.json").write_text('{"reader": "rapidocr"}', encoding="utf-8")
        J._SETTINGS_CACHE.update({"at": 0.0})
        check("the file is the switch, not this process's memory",
              J._fresh_settings()["reader"] == "rapidocr")

        # And that it is a real dependency, pinned, and OFF in the tree.
        req = (HERE / "requirements.txt").read_text(encoding="utf-8")
        lock = (HERE / "requirements.lock").read_text(encoding="utf-8")
        check("rapidocr is a requirement, pinned exactly",
              re.search(r"^rapidocr==3\.10\.0\s", req, re.M) is not None, "not in requirements.txt")
        check("... locked with a hash",
              re.search(r"^rapidocr==3\.10\.0 \\\n\s+--hash=sha256:", lock, re.M) is not None)
        req_lines = [l.split("#", 1)[0].strip() for l in req.splitlines()]
        check("... and its [rtl] extra is NOT taken (the one that pulls python-bidi)",
              "rapidocr[rtl]" not in req and not any(l.startswith("python-bidi") for l in req_lines))
        check("... and no PyTorch is asked for anywhere by this change",
              not any(l.startswith(("torch", "paddle", "openvino", "tensorrt", "mnn"))
                      for l in req_lines))
    finally:
        J.settings_path = saved
        J._reset_for_tests()


def t_rapidocr_shapes():
    """RapidOCR's answer, turned into the one shape a reader here returns.
    Pure: stand-ins, so this runs with or without the package."""
    quad = [[10, 5], [50, 5], [50, 17], [10, 17]]
    got = J.lines_from_word_results(
        ("Hello there", "Second"),
        ((("Hello", 0.99, quad), ("there", 0.98, [[58, 5], [102, 5], [102, 17], [58, 17]])),
         (("Second", 0.5, [[10, 25], [60, 25], [60, 37], [10, 37]]),)))
    check("RapidOCR's word tuple becomes lines of positioned words",
          got == [{"text": "Hello there", "words": [
              {"text": "Hello", "left": 10.0, "top": 5.0, "width": 40.0, "height": 12.0},
              {"text": "there", "left": 58.0, "top": 5.0, "width": 44.0, "height": 12.0}]},
                  {"text": "Second", "words": [{"text": "Second", "left": 10.0, "top": 25.0,
                                                "width": 50.0, "height": 12.0}]}], str(got))
    check("... and it survives the normalizer, which is what every caller sees",
          J.normalize_lines(got) == got)

    # The tuple-not-list trap that cost a round on 2026-10-13: `word_results`
    # is a tuple of tuples, and normalize_lines' own `_one` (which exists to
    # undo PowerShell flattening a one-item LIST) turns a tuple into a single
    # item - so two lines of words became ONE word. These two pin that down.
    one = J.lines_from_word_results(("only",), ((("only", 1.0, quad),),))
    check("one line is one line, not one word",
          len(one) == 1 and one[0]["text"] == "only"
          and len(one[0]["words"]) == 1, str(one))
    two = J.lines_from_word_results(("a b", "c"), ((("a", 1.0, quad), ("b", 1.0, quad)),
                                                   (("c", 1.0, quad),)))
    check("two lines keep two sets of words, in order",
          [ln["text"] for ln in two] == ["a b", "c"]
          and [len(ln["words"]) for ln in two] == [2, 1], str(two))

    check("a word the engine gave no usable corners for keeps only its text",
          J.lines_from_word_results(("x y",), ((("x", 1.0, None), ("y", 1.0, [[1, 1], [2, 2]]),),))
          == [{"text": "x y", "words": [{"text": "x"}, {"text": "y"}]}])
    check("an engine that found nothing is lines=[], not a failure",
          J.lines_from_word_results((), ()) == [] and J.lines_from_word_results(None, None) == [])
    check("the line text is the engine's own, never rejoined from the words",
          J.lines_from_word_results(("a, b!",), ((("a", 1.0, quad),),))[0]["text"] == "a, b!")

    # The whole reader, end to end, with a stand-in engine.
    saved = (J._rapid_engine, J.using_rapidocr, J.settings_path)
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-ocr-rapid-"))

    class Fake:
        img = type("A", (), {"shape": (300, 400, 3)})()
        txts = ("Hello there",)
        word_results = ((("Hello", 0.9, quad), ("there", 0.8, [[58, 5], [102, 5], [102, 17], [58, 17]])),)

        def __call__(self, image):
            return self

    J._rapid_engine = lambda: Fake()
    J.using_rapidocr = lambda: True
    J.settings_path = lambda: tmp / "ocr-reader.json"
    J._reset_for_tests()
    try:
        got = J.read_lines(PNG)
        check("a read through RapidOCR comes back in the reader's own shape",
              got["ok"] is True and got["size"] == (400, 300)
              and got["lines"][0]["words"][1]["left"] == 58.0, str(got))
        check("... and says which reader answered", got["engine"] != J.ENGINE, got.get("engine"))
        check("read_text cuts it the same way whichever reader answered",
              J.read_text(PNG)["text"] == "Hello there")

        # An engine that raises: read_lines must say so plainly, remember it
        # rather than reload 31 MB of models per picture, and never let the
        # exception out (found by this test, 2026-10-13).
        J._rapid_engine = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        J._rapid_reset_for_tests()
        got = J.read_lines(PNG)
        check("a RapidOCR read that raises says so plainly and never raises out",
              got["ok"] is False and got["why"] == J.RAPIDOCR_BROKEN, str(got))
        check("... and is remembered, rather than loading the models again per picture",
              J.status()["available"] is False and J.status()["why"] == J.RAPIDOCR_BROKEN,
              J.status())
    finally:
        J._rapid_engine, J.using_rapidocr, J.settings_path = saved
        J._rapid_reset_for_tests()
        J._reset_for_tests()


def t_measurement_writes_nothing_of_the_owners():
    """The measurement must not change which reader the owner's Jarvis uses,
    and must not write into the owner's config folder AT ALL.

    This is not a hypothetical guard: the first version of compare_pictures
    called set_reader() on the real settings path, so simply MEASURING wrote
    ~/.openjarvis/ocr-reader.json and left it saying "rapidocr" - the act of
    measuring would have switched the owner's reader (found 2026-10-13)."""
    import tempfile
    real = Path(tempfile.mkdtemp(prefix="jarvis-ocr-owner-")) / "ocr-reader.json"
    real.write_text('{"reader": "windows"}', encoding="utf-8")
    saved_path = J.settings_path
    J.settings_path = lambda: real
    try:
        J._rapid_reset_for_tests()
        before = real.read_bytes()
        # Run the measurement over a file that is not a picture at all: both
        # readers' paths are taken, and the owner's file must be untouched.
        rep = J.compare_pictures([__file__])
        check("measuring a file that is not a picture is reported, not crashed",
              rep["pictures"][0].get("error") is None
              and rep["pictures"][0]["windows"]["ok"] is False
              and rep["pictures"][0]["rapidocr"]["ok"] is False,
              str(rep["pictures"][0])[:300])
        check("... and the owner's settings file is byte for byte what it was",
              real.read_bytes() == before, real.read_text(encoding="utf-8"))
        check("... and it still says Windows, which is what the owner chose",
              json.loads(real.read_text(encoding="utf-8"))["reader"] == "windows")
        check("... and the measurement left the real switch alone in memory too",
              J._fresh_settings()["reader"] == "windows", J._fresh_settings())
        check("... and the report itself names both readers",
              "Windows" in J.report_comparison(rep) and "RapidOCR" in J.report_comparison(rep))
    finally:
        J.settings_path = saved_path
        J._reset_for_tests()


def t_status_says_which_reader():
    """Both apps read this through GET /api/second-card, so it must name the
    reader in use and stay honest when the chosen one is not installed."""
    saved_path, saved_use, saved_usable = J.settings_path, J.using_rapidocr, J.rapidocr_usable
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-ocr-status-"))
    J.settings_path = lambda: tmp / "ocr-reader.json"
    try:
        J.set_reader("windows")
        J._reset_for_tests()
        st = J.status()
        check("with Windows chosen it names Windows' own reader",
              st["engine"] == J.ENGINE, st)

        J.set_reader("rapidocr")
        J.using_rapidocr = lambda: True
        J.rapidocr_usable = lambda: False
        st = J.status()
        check("with RapidOCR chosen but not installed: not available, named, and it "
              "says the one line that installs it",
              st["available"] is False and st["engine"] == J.RAPIDOCR
              and st["why"] == J.NO_RAPIDOCR, st)

        J.rapidocr_usable = lambda: True
        J._rapid_reset_for_tests()
        st = J.status()
        check("with RapidOCR installed: available, and the engine is the package's name "
              "before the first read (nothing is loaded to answer this)",
              st["available"] is True and st["engine"] == J.RAPIDOCR, st)
        check("nothing here loads a model just to answer a status question",
              "engine" not in J._RAPID, sorted(J._RAPID))
    finally:
        J.settings_path, J.using_rapidocr, J.rapidocr_usable = saved_path, saved_use, saved_usable
        J._rapid_reset_for_tests()
        J._reset_for_tests()


def t_rapidocr_real():
    """The REAL package, where it is installed. It draws its own picture with
    known words at known places, so the boxes can be checked against the truth
    rather than against RapidOCR agreeing with itself."""
    if not J.rapidocr_usable():
        print("skip  the rapidocr package is not installed here: the real engine is not run")
        return
    if os.name == "nt":
        # THE 2026-10-20 CRASH'S REGRESSION. Loading onnxruntime AFTER any
        # pywinrt package crashed this process with 0xC0000005
        # (STATUS_ACCESS_VIOLATION) inside onnxruntime's extension init; this
        # suite's own order - Windows-reader checks first, this real RapidOCR
        # read afterwards - is exactly that order, so the read at the end of
        # this function is the proof. This check names the guard that makes it
        # safe, and fails the moment the guard is removed.
        J.winrt_usable()
        check("onnxruntime is loaded before the WinRT reader's first package "
              "(loading it after the WinRT packages crashed 0xC0000005)",
              J._WINRT_SAFE_ONNX.get("ok") is True, J._WINRT_SAFE_ONNX)
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        print("skip  pillow is not installed here, so no picture can be drawn")
        return
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    img = Image.new("RGB", (900, 300), (255, 255, 255))
    d = ImageDraw.Draw(img)
    # Drawn at a known x; OCR's left edge is the left of the glyph, which for
    # this font and size starts a couple of pixels in.
    d.text((60, 40), "Hello there world", fill=(0, 0, 0), font=font)
    d.text((60, 120), "api_key sk-abc123", fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png = buf.getvalue()

    saved_path, saved_use = J.settings_path, J.using_rapidocr
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-ocr-real-"))
    J.settings_path = lambda: tmp / "ocr-reader.json"
    J.using_rapidocr = lambda: True
    J._rapid_reset_for_tests()
    try:
        got = J.read_lines(png)
    finally:
        J.settings_path, J.using_rapidocr = saved_path, saved_use
        J._rapid_reset_for_tests()
    if not got["ok"]:
        check("the real RapidOCR read the picture it was given", False, got["why"])
        return
    check("the real RapidOCR read the picture it was given", True)
    check("... and answered with the picture's own size", got["size"] == (900, 300), got["size"])
    words = [(w["text"], w) for ln in got["lines"] for w in ln["words"]]
    texts = [t for t, _w in words]
    check("... and found the words that were drawn",
          texts == ["Hello", "there", "world", "api_key", "sk-abc123"], str(texts))
    check("... and gave EVERY one of them a position",
          all(all(k in w for k in ("left", "top", "width", "height")) for _t, w in words),
          str(words))
    # The boxes must land where the words were drawn, which is the thing that
    # decides where a secret gets painted black. Line 1 starts at x=60, line 2
    # at x=60; a box more than a few pixels off means the reader is guessing.
    hello = words[0][1]
    check("... and the first word's box lands on the first word (drawn at x=60, y=40)",
          58 <= hello["left"] <= 64 and 36 <= hello["top"] <= 46, str(hello))
    api = [w for t, w in words if t == "api_key"][0]
    check("... and a later line's box lands on that line (drawn at x=60, y=120)",
          58 <= api["left"] <= 64 and 112 <= api["top"] <= 126, str(api))
    check("... and no word's box is wider than the picture",
          all(w["left"] >= 0 and w["left"] + w["width"] <= 900 for _t, w in words), str(words))


def t_rapidocr_pixels():
    """The black-out needs pixels for a picture that is not a PNG the backend
    can open itself (a phone's JPEG). RapidOCR's reader hands them back in the
    one shape jarvis_picture paints on, and they are the right way round."""
    try:
        from PIL import Image
    except Exception:
        print("skip  pillow is not installed here, so no picture can be drawn")
        return
    img = Image.new("RGB", (4, 2), (255, 255, 255))
    img.putpixel((0, 0), (255, 0, 0))       # pure red
    img.putpixel((1, 0), (0, 255, 0))       # pure green
    img.putpixel((2, 0), (0, 0, 255))       # pure blue
    buf = io.BytesIO()
    img.save(buf, "PNG")
    got = J.bgra_from_bytes(buf.getvalue())
    check("a picture becomes BGRA bytes and its size", got is not None
          and got[1] == 4 and got[2] == 2, str(got))
    if got:
        px = got[0]
        check("... with red, green and blue in the order jarvis_picture paints on "
              "(BGRA: a red pixel is 00 00 ff ff)",
              px[0:4] == bytes([0, 0, 255, 255])
              and px[4:8] == bytes([0, 255, 0, 255])
              and px[8:12] == bytes([255, 0, 0, 255]),
              f"{px[0:4].hex()} {px[4:8].hex()} {px[8:12].hex()}")
    check("... and rubbish is refused rather than guessed at",
          J.bgra_from_bytes(b"not a picture") is None
          and J.bgra_from_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20) is None)


def t_no_tools_import():
    """A shipped file must not import anything out of this repository: on the
    owner's PC the backend is there and this repository is not. The
    measurement therefore lives IN jarvis_ocr.py, and tools/ocr_bakeoff.py is
    the front door that imports IT, never the other way round."""
    import ast
    src = (HERE / "jarvis_ocr.py").read_text(encoding="utf-8")
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mods.add(n.module.split(".")[0])
    repo_only = {"ocr_bakeoff", "tools", "conftest"}
    check("the shipped reader imports nothing from tools/ or this repository",
          not (repo_only & mods), f"it imports {sorted(repo_only & mods)}")
    tools = sorted(p.name for p in (HERE.parent / "tools").glob("ocr_*.py"))
    check("the measurement's front door is in tools/ and imports the backend",
          "ocr_bakeoff.py" in tools, tools)
    front = (HERE.parent / "tools" / "ocr_bakeoff.py").read_text(encoding="utf-8")
    check("... and it points at backend/ or jarvis-backend/, never at itself",
          '"backend"' in front and "jarvis_ocr" in front)


def main():
    for fn in (t_shapes, t_order, t_read_text, t_powershell_script, t_hygiene,
               t_second_reader_switch, t_rapidocr_shapes, t_rapidocr_pixels,
               t_measurement_writes_nothing_of_the_owners, t_status_says_which_reader,
               t_rapidocr_real, t_no_tools_import):
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
